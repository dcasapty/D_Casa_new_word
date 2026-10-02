"""ir.attachment con el contenido en R2 (``ir_attachment.location = r2``).

Se engancha en los puntos que Odoo deja para otros almacenes (``_storage``, ``_get_path``,
``_file_read``, ``_file_write``, ``_file_delete``) sin tocar vendor/odoo. Todo es privado
(prefijo ``_``): nada de esto se puede llamar por RPC (dcasa_base/tests/test_superficie_rpc.py).

Garantías:
* Escritura: si R2 falla, se lanza un error y la transacción se deshace: nunca queda una
  fila que apunte a un objeto que no se subió. (Un objeto subido de una transacción que
  luego se deshizo queda huérfano: lo recoge el GC.)
* Lectura: un error de R2 se lanza (nunca se confunde con «archivo vacío», que en una
  migración o una copia escribiría b'' encima del dato bueno). Solo un objeto que no existe
  devuelve b'' (como Odoo con un archivo que falta en el filestore), con log de error.
* Borrado: NUNCA síncrono. Una restauración de la base a un punto anterior vuelve a
  referenciar objetos «borrados»; los recoge ``_dcasa_r2_gc`` pasada la ventana de respaldos.
"""
import contextlib
import contextvars
import logging
from datetime import datetime, timedelta

import psycopg2

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.http import Stream
from odoo.tools import split_every

from .. import r2

_logger = logging.getLogger(__name__)

# Almacén forzado durante una migración. Es una variable de contexto de Python (no el
# contexto de Odoo, que llega del cliente por RPC): nadie puede elegirla desde fuera.
_ALMACEN_FORZADO = contextvars.ContextVar('dcasa_adjuntos_almacen', default=None)

PARAM_DIAS = 'dcasa_adjuntos_r2.dias_retencion'
PARAM_GC_ULTIMA = 'dcasa_adjuntos_r2.gc_ultima_corrida'
# Por defecto 45 días: más que la retención más larga de respaldos de la base
# (pg_dump diario, RESPALDO_DUMP_DIAS = 30; pgBackRest, RESPALDO_RETENCION_DIAS = 7).
DIAS_RETENCION = 45
DIAS_RETENCION_MINIMO = 31
# Si el GC no corrió en este tiempo, sus marcas de «huérfano desde» no son de fiar
# (pudo haber referencias que no vio): se reinicia la cuenta.
GC_HUECO_MAXIMO = timedelta(days=3)

_avisado_sin_credenciales = False


@contextlib.contextmanager
def almacen_forzado(almacen):
    token = _ALMACEN_FORZADO.set(almacen)
    try:
        yield
    finally:
        _ALMACEN_FORZADO.reset(token)


class IrAttachment(models.Model):
    _inherit = 'ir.attachment'

    # ------------------------------------------------------------------ almacén
    @api.model
    def _dcasa_r2_conf(self):
        return r2.configuracion()

    @api.model
    def _dcasa_r2_cliente(self):
        conf = self._dcasa_r2_conf()
        if not conf:
            raise r2.ErrorR2('No hay credenciales de R2 para los adjuntos (DCASA_ADJUNTOS_R2_*).')
        return r2.cliente(conf), conf['bucket']

    @api.model
    def _storage(self):
        global _avisado_sin_credenciales  # noqa: PLW0603 - aviso una vez por proceso
        almacen = _ALMACEN_FORZADO.get() or super()._storage()
        if almacen == 'r2' and not self._dcasa_r2_conf():
            if not _avisado_sin_credenciales:
                _avisado_sin_credenciales = True
                _logger.warning('ir_attachment.location = r2 pero no hay credenciales de R2 '
                                '(DCASA_ADJUNTOS_R2_*): los adjuntos nuevos se guardan en la base.')
            return 'db'
        return almacen

    @api.model
    def _get_storage_domain(self):
        if self._storage() == 'r2':
            # Lo que está en la base, o en un filestore local (que en el contenedor no persiste).
            return Domain('db_datas', '!=', False) | (
                Domain('store_fname', '!=', False) & Domain('store_fname', 'not =like', r2.ESQUEMA + '%'))
        return super()._get_storage_domain()

    @api.model
    def _get_path(self, bin_data, sha):
        if self._storage() == 'r2':
            return r2.fname_de(sha), None
        return super()._get_path(bin_data, sha)

    # --------------------------------------------------------- leer / escribir
    @api.model
    def _file_read(self, fname, size=None):
        if not r2.es_r2(fname):
            return super()._file_read(fname, size)
        return self._dcasa_r2_leer(fname, size=size)

    @api.model
    def _file_write(self, bin_value, checksum):
        if self._storage() != 'r2':
            return super()._file_write(bin_value, checksum)
        fname = r2.fname_de(checksum)
        self._dcasa_r2_subir(fname, bin_value)
        return fname

    @api.model
    def _file_delete(self, fname):
        if r2.es_r2(fname):
            # Nada síncrono: ver _dcasa_r2_gc (consistencia con la restauración a un punto).
            return
        return super()._file_delete(fname)

    @api.model
    def _dcasa_r2_subir(self, fname, datos):
        """Sube SIEMPRE (también si ya existe): así LastModified marca el último uso del
        contenido y el GC no borra algo que una fila reciente volvió a referenciar."""
        clave = r2.clave_de(fname)
        try:
            cliente, bucket = self._dcasa_r2_cliente()
            cliente.put_object(Bucket=bucket, Key=clave, Body=datos, ContentType='application/octet-stream')
        except Exception as error:
            _logger.error('Adjuntos en R2: no se pudo subir %s (%d bytes): %s %s',
                          clave, len(datos), r2.codigo_error(error) or type(error).__name__, error)
            raise UserError(self.env._(
                'No se pudo guardar el archivo en el almacenamiento (R2). No se guardó nada: '
                'inténtalo de nuevo en unos minutos.')) from error
        r2.cache.guardar(clave, datos)

    @api.model
    def _dcasa_r2_leer(self, fname, size=None, estricto=False):
        """Contenido de un objeto. Error de R2 → excepción. Objeto inexistente → b'' con log
        de error (o excepción si ``estricto``: la migración nunca escribe un vacío encima)."""
        clave = r2.clave_de(fname)
        datos = r2.cache.obtener(clave)
        if datos is None:
            parcial = bool(size) and size > 0
            argumentos = {'Range': f'bytes=0-{size - 1}'} if parcial else {}
            try:
                cliente, bucket = self._dcasa_r2_cliente()
                respuesta = cliente.get_object(Bucket=bucket, Key=clave, **argumentos)
                datos = respuesta['Body'].read()
            except Exception as error:
                codigo = r2.codigo_error(error)
                if codigo in r2.NO_EXISTE and not estricto:
                    _logger.error('Adjuntos en R2: falta el objeto %s (¿se restauró la base sin el '
                                  'prefijo adjuntos/ del bucket?)', clave)
                    return b''
                _logger.error('Adjuntos en R2: no se pudo leer %s: %s %s',
                              clave, codigo or type(error).__name__, error)
                raise UserError(self.env._(
                    'No se pudo leer un archivo del almacenamiento (R2). Inténtalo de nuevo en unos minutos.'
                )) from error
            if parcial:
                return datos
            if r2.sha1(datos) != r2.checksum_de(clave):
                _logger.error('Adjuntos en R2: el contenido de %s no coincide con su sha1', clave)
                if estricto:
                    raise UserError(self.env._('El archivo %s en R2 está dañado.', clave))
                return datos
            r2.cache.guardar(clave, datos)
        return datos[:size] if size else datos

    def _to_http_stream(self):
        self.ensure_one()
        if not r2.es_r2(self.store_fname):
            return super()._to_http_stream()
        # El Stream de Odoo para store_fname es un archivo local (os.stat): aquí van los bytes.
        datos = self.raw or b''
        return Stream(
            type='data',
            data=datos,
            size=len(datos),
            mimetype=self.mimetype,
            download_name=self.name,
            etag=self.checksum,
            public=self.public,
            last_modified=self.write_date,
        )

    # ------------------------------------------------------------- migración
    @api.model
    def _dcasa_r2_migrar(self, destino='r2', lote=100, desde_id=0, estricto=False):
        """Mueve un lote de adjuntos binarios al almacén ``destino`` (``r2`` o ``db``),
        en orden de id a partir de ``desde_id``. Devuelve ``(procesados, ultimo_id, fallidos)``.

        Lee el origen verificando el sha1 y nunca escribe vacío si el origen falla: ese
        adjunto se salta con log de error (``estricto``: se lanza el error) y se sigue.
        No hace commit: lo hace quien lo llama (_dcasa_r2_migrar_todo / el cron).
        """
        if destino not in ('r2', 'db'):
            raise ValueError(destino)
        if not self._dcasa_r2_conf():
            raise UserError(self.env._('No hay credenciales de R2 (DCASA_ADJUNTOS_R2_*): no se puede migrar.'))
        Adjunto = self.sudo().with_context(prefetch_fields=False, active_test=False)
        with almacen_forzado(destino):
            dominio = Domain.AND([
                Adjunto._get_storage_domain(),
                [('type', '=', 'binary'), ('id', '>', desde_id)],
                ['|', ('res_field', '=', False), ('res_field', '!=', False)],
            ])
            adjuntos = Adjunto.search(dominio, order='id', limit=lote)
            fallidos = 0
            for adjunto in adjuntos:
                try:
                    datos = adjunto._dcasa_r2_origen()
                except UserError:
                    if estricto:
                        raise
                    fallidos += 1
                    _logger.error('Adjuntos en R2: el adjunto %s no se migró a %s (origen ilegible)',
                                  adjunto.id, destino)
                    continue
                adjunto.write({'raw': datos, 'mimetype': adjunto.mimetype})
            self.env.flush_all()
        ultimo = adjuntos[-1].id if adjuntos else desde_id
        return len(adjuntos), ultimo, fallidos

    def _dcasa_r2_origen(self):
        """Bytes actuales del adjunto, verificados contra su checksum."""
        self.ensure_one()
        if r2.es_r2(self.store_fname):
            return self._dcasa_r2_leer(self.store_fname, estricto=True)
        datos = self.raw or b''
        if self.checksum and r2.sha1(datos) != self.checksum:
            _logger.error('Adjuntos: el adjunto %s no coincide con su checksum (%s)', self.id, self.store_fname)
            raise UserError(self.env._('El adjunto %s no coincide con su checksum.', self.id))
        return datos

    @api.model
    def _dcasa_r2_migrar_todo(self, destino='r2', lote=100, confirmar=True, estricto=False):
        """Migra todo, lote a lote. Con ``confirmar`` hace commit por lote (cron o shell).
        Lo usa el cron (_dcasa_r2_cron_migrar) en las dos direcciones."""
        Cron = self.env['ir.cron']
        desde = 0
        total = fallidos_total = 0
        while True:
            procesados, desde, fallidos = self._dcasa_r2_migrar(destino, lote=lote, desde_id=desde, estricto=estricto)
            if not procesados:
                break
            total += procesados - fallidos
            fallidos_total += fallidos
            if confirmar and Cron._commit_progress(procesados) <= 0:
                break  # se acabó el tiempo del cron: sigue en la próxima corrida
        if total or fallidos_total:
            _logger.info('Adjuntos: %d migrados a %s, %d con error', total, destino, fallidos_total)
        return total, fallidos_total

    @api.model
    def _dcasa_r2_cron_migrar(self, confirmar=True):
        """Cron: deja cada adjunto donde dice ``ir_attachment.location``.

        * ``r2`` (con credenciales): sube a R2 lo que sigue en la base.
        * ``db`` con credenciales (``DCASA_ADJUNTOS=db``, emergencia): trae a la base lo
          que está en R2. Sin credenciales (CI, desarrollo) no hace nada.
        """
        almacen = self._storage()
        if almacen == 'r2':
            return self._dcasa_r2_migrar_todo('r2', confirmar=confirmar)
        if almacen == 'db' and self._dcasa_r2_conf():
            self.env.cr.execute('SELECT 1 FROM ir_attachment WHERE store_fname LIKE %s LIMIT 1', [r2.ESQUEMA + '%'])
            if self.env.cr.fetchone():
                return self._dcasa_r2_migrar_todo('db', confirmar=confirmar)
        return 0, 0

    # ---------------------------------------------------------- recolección
    @api.model
    def _dcasa_r2_dias_retencion(self):
        valor = self.env['ir.config_parameter'].sudo().get_param(PARAM_DIAS, DIAS_RETENCION)
        try:
            dias = int(valor)
        except (TypeError, ValueError):
            dias = DIAS_RETENCION
        if dias < DIAS_RETENCION_MINIMO:
            _logger.warning('%s = %s es menor que la ventana de respaldos: se usan %d días',
                            PARAM_DIAS, valor, DIAS_RETENCION_MINIMO)
            dias = DIAS_RETENCION_MINIMO
        return dias

    @api.model
    def _dcasa_r2_gc(self, confirmar=True, ahora=None):
        """Borra en R2 los objetos de adjuntos/ que llevan más de N días (por defecto 45)
        sin referencia Y sin escribirse. Por qué así (y no al desvincular):

        La base se puede restaurar a cualquier punto cubierto por los respaldos (pgBackRest,
        7 días; pg_dump, 30). Esa base vieja apunta a los objetos que tenía entonces: si se
        hubieran borrado al desvincular, sus fotos y PDF quedarían rotos. Por eso un objeto
        solo se borra si (a) ninguna fila lo referencia hoy, (b) el GC lo viene viendo sin
        referencia desde hace N días (tabla dcasa.adjunto.r2.huerfano) y (c) su LastModified
        también tiene más de N días (cada escritura del mismo contenido lo vuelve a subir).
        Con N mayor que la retención de respaldos, ningún punto restaurable lo referencia.
        """
        conf = self._dcasa_r2_conf()
        if not conf:
            _logger.info('Adjuntos en R2: sin credenciales, no hay nada que recolectar')
            return
        cliente, bucket = self._dcasa_r2_cliente()
        dias = self._dcasa_r2_dias_retencion()
        ahora = ahora or fields.Datetime.now()
        corte = ahora - timedelta(days=dias)

        # 1. Listar fuera del candado (puede tardar).
        objetos = {}
        try:
            for pagina in cliente.get_paginator('list_objects_v2').paginate(Bucket=bucket, Prefix=r2.PREFIJO):
                for objeto in pagina.get('Contents') or ():
                    modificado = objeto['LastModified']
                    if isinstance(modificado, datetime) and modificado.tzinfo:
                        modificado = modificado.replace(tzinfo=None) - (modificado.utcoffset() or timedelta())
                    objetos[objeto['Key']] = modificado
        except Exception as error:
            _logger.error('Adjuntos en R2: GC no pudo listar el bucket: %s %s', r2.codigo_error(error), error)
            return

        # 2. Como el GC del filestore de Odoo: el LOCK debe ser lo primero de la transacción,
        #    para ver las filas que confirmaron las transacciones que esperó.
        cr = self.env.cr
        if confirmar:
            cr.commit()
            cr.execute("SET LOCAL lock_timeout TO '10s'")
            try:
                cr.execute('LOCK ir_attachment IN SHARE MODE')
            except psycopg2.errors.LockNotAvailable:
                cr.rollback()
                _logger.info('Adjuntos en R2: GC aplazado (ir_attachment ocupada)')
                return
        else:
            cr.execute('LOCK ir_attachment IN SHARE MODE')
        self.env.invalidate_all()

        borrados = self._dcasa_r2_gc_aplicar(cliente, bucket, objetos, ahora, corte)
        if confirmar:
            cr.commit()
        return borrados

    @api.model
    def _dcasa_r2_gc_aplicar(self, cliente, bucket, objetos, ahora, corte):
        Huerfano = self.env['dcasa.adjunto.r2.huerfano'].sudo()
        icp = self.env['ir.config_parameter'].sudo()
        ultima = fields.Datetime.to_datetime(icp.get_param(PARAM_GC_ULTIMA) or False)
        if not ultima or ultima < ahora - GC_HUECO_MAXIMO or ultima > ahora:
            # Sin corridas recientes no sabemos desde cuándo nadie usa cada objeto.
            Huerfano.search([]).unlink()

        marcas = {h.clave: h for h in Huerfano.search([])}
        referenciadas = set()
        for claves in split_every(self.env.cr.IN_MAX, list(objetos)):
            self.env.cr.execute('SELECT store_fname FROM ir_attachment WHERE store_fname IN %s',
                                [tuple(r2.ESQUEMA + clave for clave in claves)])
            referenciadas.update(fila[0][len(r2.ESQUEMA):] for fila in self.env.cr.fetchall())

        a_borrar, nuevas, conocidas = [], [], set()
        for clave, modificado in objetos.items():
            marca = marcas.get(clave)
            if clave in referenciadas:
                continue
            conocidas.add(clave)
            if not marca:
                nuevas.append({'clave': clave, 'visto_desde': ahora})
            elif marca.visto_desde <= corte and modificado <= corte:
                a_borrar.append(clave)
        # Marcas que ya no aplican: el objeto volvió a usarse o ya no existe.
        Huerfano.browse([m.id for c, m in marcas.items() if c not in conocidas]).unlink()
        Huerfano.create(nuevas)

        borrados = []
        for claves in split_every(1000, a_borrar):
            try:
                respuesta = cliente.delete_objects(
                    Bucket=bucket, Delete={'Objects': [{'Key': c} for c in claves], 'Quiet': True})
            except Exception as error:
                _logger.error('Adjuntos en R2: GC no pudo borrar %d objetos: %s %s',
                              len(claves), r2.codigo_error(error), error)
                continue
            errores = {e.get('Key') for e in respuesta.get('Errors') or ()}
            for error in respuesta.get('Errors') or ():
                _logger.error('Adjuntos en R2: GC no pudo borrar %s: %s', error.get('Key'), error.get('Code'))
            borrados.extend(c for c in claves if c not in errores)
        if borrados:
            Huerfano.search([('clave', 'in', borrados)]).unlink()
        icp.set_param(PARAM_GC_ULTIMA, fields.Datetime.to_string(ahora))
        _logger.info('Adjuntos en R2: GC revisó %d objetos, %d sin referencia, %d borrados (ventana %s)',
                     len(objetos), len(conocidas), len(borrados), corte)
        return borrados
