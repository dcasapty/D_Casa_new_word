"""Barandas de costo: depuración y reporte de tamaños mensuales (ronda 4, costos-y-limpieza §5).

Dos acciones planificadas (``data/ir_cron_data.xml``), ambas el día 1 de madrugada:

* ``_cron_depurar``: borra lo que nadie va a volver a mirar y que hace crecer la base
  (la base pesa = el contenedor ``basic`` deja de alcanzar):

  - **adjuntos huérfanos**: ``ir.attachment`` con ``res_model``/``res_id`` cuyo registro
    ya no existe (padres borrados por ``ON DELETE CASCADE`` de PostgreSQL o por SQL
    directo: el ORM no ve a los hijos y sus archivos se quedan). Nunca toca los de campos
    binarios (``res_field``), los de modelos protegidos (contabilidad, localización,
    libro de Socios, registro de Brian), los de modelos que ya no están instalados (no
    se puede saber si el registro existe) ni los que alguna tabla referencia por llave
    foránea (``message_main_attachment_id``, PDF de factura, relaciones de mensajes…);
  - **correos fallidos** (``mail.mail`` en excepción) de más de N días, salvo los de
    documentos protegidos.

  Lo que Odoo ya depura solo NO se repite aquí: visitantes del sitio
  (``website.visitor``, ``website.visitor.live.days`` = 60), sesiones (``dcasa_sesiones``,
  7 días), bus, notificaciones leídas, adjuntos del compositor de correo, bundles viejos.

* ``_cron_reporte_tamanos``: tamaño de la base, las 10 tablas más grandes, los bytes de
  adjuntos por modelo y la memoria real del contenedor (``dcasa_base/memoria.py``). Lo
  escribe en el log (``DCASA_METRICA``) y en ``ir.logging``
  (Ajustes → Técnico → Registros), y avisa (``DCASA_ALERTA``) si la base pasa del umbral:
  con ~1 GB el disco de 4 GB de ``basic`` ya no alcanza.

* ``_cron_vigilar_recursos`` (cada hora): disco del contenedor, memoria real (cgroup) y
  tamaño de la base contra sus umbrales, y si el kernel mató algún proceso (``oom_kill``)
  desde la última revisión. Cada aviso (``DCASA_ALERTA``) va al log, a ``ir.logging`` y,
  si ``dcasa_seguridad`` está instalado y hay administradores vinculados al Telegram de
  Brian, a Telegram (``_avisar_operacion``); el mismo aviso no se repite por Telegram antes
  de ``dcasa.alerta.silencio_h`` horas.

* ``_ajustar_crons_odoo`` (``data/crons_odoo.xml``, en cada instalación o actualización de
  ``dcasa_base``): apaga o espacia las acciones planificadas de Odoo que no aplican a D'CASA
  (``CRONS_ODOO``; motivos en docs/OPERACION.md). Idempotente: solo escribe lo que difiere
  y nunca toca los crons propios (``dcasa_*``).

Umbrales en ``ir.config_parameter`` (ver ``PARAMETROS``); ``docker/entrypoint.sh`` los fija
desde variables ``DCASA_ALERTA_*`` si vienen. Todos los métodos son privados (``_``): no se
pueden llamar por RPC (test_superficie_rpc).
"""
import json
import logging
import shutil
from datetime import timedelta

from odoo import api, fields, models, tools
from odoo.tools import SQL

from .. import memoria

_logger = logging.getLogger(__name__)

# Parámetro → valor por defecto. Se leen en cada ejecución: cambiarlos no exige reiniciar.
PARAMETROS = {
    # Un adjunto huérfano más nuevo que esto se deja (puede ser una subida a medias).
    'dcasa.limpieza.adjuntos_dias': 7,
    # Correos en excepción más viejos que esto se borran.
    'dcasa.limpieza.correos_fallidos_dias': 90,
    # Modelos extra que la depuración no toca nunca (separados por coma).
    'dcasa.limpieza.modelos_protegidos': '',
    # Aviso cuando la base pasa de esto (GB). El límite práctico de basic es ~1 GB.
    'dcasa.reporte.alerta_gb': 0.7,
    # Aviso cuando el disco del contenedor (data_dir de Odoo; PostgreSQL vive al lado) pasa de este %.
    'dcasa.alerta.disco_pct': 80,
    # Aviso cuando la memoria en uso real (cgroup: current menos caché de archivos) pasa de este %
    # del límite de memoria del contenedor.
    'dcasa.alerta.memoria_pct': 90,
    # Horas sin repetir el mismo aviso por Telegram (en el log y en ir.logging queda siempre).
    'dcasa.alerta.silencio_h': 24,
}

# Acciones planificadas de Odoo que no aplican a D'CASA: xmlid → valores que se fijan en cada
# instalación/actualización de dcasa_base, si el cron existe (los módulos sobrantes se
# desinstalan en el arranque). Motivos en docs/OPERACION.md → «Acciones planificadas de Odoo
# que se apagan o espacian». Si la tienda activa la función (p. ej. crea un servidor de correo
# entrante o enciende la asignación de iniciativas), Odoo vuelve a encender su cron solo.
CRONS_ODOO = {
    # Correo entrante (fetchmail): no hay servidor de correo entrante.
    'mail.ir_cron_mail_gateway_action': {'active': False},
    # Manda estadísticas anónimas de la instalación a Odoo S.A. cada semana.
    'mail.ir_cron_module_update_notification': {'active': False},
    # Asignación de iniciativas por reglas de equipo: D'CASA no usa reglas.
    'crm.ir_cron_crm_lead_assign': {'active': False},
    # Probabilidad predictiva de las iniciativas: con pocas iniciativas basta una vez por semana.
    'crm.website_crm_score_cron': {'interval_number': 1, 'interval_type': 'weeks'},
    # Enriquecer iniciativas con IAP (servicio de pago de Odoo).
    'crm_iap_enrich.ir_cron_lead_enrichment': {'active': False},
    # Correo digest de KPI a los usuarios.
    'digest.ir_cron_digest_scheduler_action': {'active': False},
    # Recordatorio por correo a usuarios invitados que no se registraron.
    'auth_signup.ir_cron_auth_signup_send_pending_user_reminder': {'active': False},
    # Recordatorios de calendario por correo: el calendario no se usa (menú oculto).
    'calendar.ir_cron_scheduler_alarm': {'active': False},
    # SMS y correo postal (IAP): servicios de pago que no se usan.
    'sms.ir_cron_sms_scheduler_action': {'active': False},
    'snailmail.snailmail_print': {'active': False},
    # Correo de carrito abandonado: el CTA de D'CASA es WhatsApp y la opción está apagada en
    # Ajustes del sitio (apagada, el cron no manda nada): basta revisarlo una vez al día.
    'website_sale.ir_cron_send_availability_email': {'interval_number': 1, 'interval_type': 'days'},
}

# Nunca se depura nada de estos modelos (legal / reglas del programa de Socios / auditoría).
MODELOS_PROTEGIDOS = frozenset({
    'dcasa.movimiento',  # libro de puntos: no se borra (regla 3 de Socios)
    'dcasa.compra',
    'dcasa.canje',
    'brian.accion',  # registro de auditoría de Brian
})
PREFIJOS_PROTEGIDOS = ('account.', 'l10n_')

TAMANO_LOTE = 1000
GB = 1024 ** 3


class DcasaMantenimiento(models.AbstractModel):
    _name = 'dcasa.mantenimiento'
    _description = "D'CASA: depuración y reporte de tamaños mensuales"

    # ------------------------------------------------------------------ parámetros

    def _parametro(self, clave, tipo=int):
        valor = self.env['ir.config_parameter'].sudo().get_param(clave)
        defecto = PARAMETROS[clave]
        if valor in (None, False, ''):
            return defecto
        try:
            return tipo(valor)
        except (TypeError, ValueError):
            _logger.warning('Parámetro %s inválido (%r): uso %r', clave, valor, defecto)
            return defecto

    def _modelos_protegidos(self):
        extra = self._parametro('dcasa.limpieza.modelos_protegidos', str)
        return MODELOS_PROTEGIDOS | {m.strip() for m in extra.split(',') if m.strip()}

    def _es_protegido(self, modelo, protegidos):
        return modelo in protegidos or modelo.startswith(PREFIJOS_PROTEGIDOS)

    # ------------------------------------------------------------------ depuración

    @api.model
    def _cron_depurar(self):
        resumen = self._depurar()
        mensaje = 'DCASA_LIMPIEZA ' + ' '.join(f'{k}={v}' for k, v in resumen.items())
        _logger.info(mensaje)
        self._registrar('dcasa.limpieza', 'INFO', mensaje, '_cron_depurar')
        return resumen

    @api.model
    def _depurar(self):
        adjuntos, bytes_liberados = self._depurar_adjuntos_huerfanos()
        correos = self._depurar_correos_fallidos()
        return {
            'adjuntos_huerfanos': adjuntos,
            'bytes_liberados': bytes_liberados,
            'correos_fallidos': correos,
        }

    @api.model
    def _adjuntos_huerfanos(self):
        """Ids de ``ir.attachment`` que apuntan a un registro que ya no existe."""
        cr = self.env.cr
        corte = fields.Datetime.now() - timedelta(days=self._parametro('dcasa.limpieza.adjuntos_dias'))
        protegidos = self._modelos_protegidos()
        cr.execute("""
            SELECT DISTINCT res_model FROM ir_attachment
             WHERE res_model IS NOT NULL AND res_id IS NOT NULL AND res_id <> 0 AND res_field IS NULL
        """)
        huerfanos = []
        for (nombre,) in cr.fetchall():
            if self._es_protegido(nombre, protegidos):
                continue
            modelo = self.env.registry.get(nombre)
            # Sin modelo (módulo desinstalado), abstracto o vista SQL: no se puede comprobar.
            if modelo is None or modelo._abstract or not modelo._auto or not modelo._table:
                continue
            cr.execute(SQL(
                """
                SELECT a.id FROM ir_attachment a
                 WHERE a.res_model = %s AND a.res_id IS NOT NULL AND a.res_id <> 0
                   AND a.res_field IS NULL AND a.create_date < %s
                   AND NOT EXISTS (SELECT 1 FROM %s r WHERE r.id = a.res_id)
                """,
                nombre, corte, SQL.identifier(modelo._table),
            ))
            huerfanos.extend(fila[0] for fila in cr.fetchall())
        return self._sin_referencias(huerfanos)

    @api.model
    def _sin_referencias(self, ids):
        """Quita los ids que alguna tabla referencia por llave foránea (p. ej. el PDF de una factura)."""
        if not ids:
            return []
        cr = self.env.cr
        cr.execute("""
            SELECT cl.relname, att.attname
              FROM pg_constraint c
              JOIN pg_class cl ON cl.oid = c.conrelid
              JOIN pg_attribute att ON att.attrelid = c.conrelid AND att.attnum = c.conkey[1]
             WHERE c.contype = 'f' AND c.confrelid = 'ir_attachment'::regclass
               AND array_length(c.conkey, 1) = 1
        """)
        referenciados = set()
        for tabla, columna in cr.fetchall():
            cr.execute(SQL(
                'SELECT DISTINCT %s FROM %s WHERE %s = ANY(%s)',
                SQL.identifier(columna), SQL.identifier(tabla), SQL.identifier(columna), ids,
            ))
            referenciados.update(fila[0] for fila in cr.fetchall())
        return [i for i in ids if i not in referenciados]

    @api.model
    def _depurar_adjuntos_huerfanos(self):
        ids = self._adjuntos_huerfanos()
        total = bytes_liberados = 0
        adjuntos = self.env['ir.attachment'].sudo()
        for inicio in range(0, len(ids), TAMANO_LOTE):
            lote = adjuntos.browse(ids[inicio:inicio + TAMANO_LOTE]).exists()
            bytes_liberados += sum(lote.mapped('file_size'))
            total += len(lote)
            lote.unlink()
        return total, bytes_liberados

    @api.model
    def _depurar_correos_fallidos(self):
        if 'mail.mail' not in self.env:
            return 0
        dias = self._parametro('dcasa.limpieza.correos_fallidos_dias')
        corte = fields.Datetime.now() - timedelta(days=dias)
        protegidos = self._modelos_protegidos()
        correos = self.env['mail.mail'].sudo().search([
            ('state', '=', 'exception'),
            ('create_date', '<', corte),
        ])
        correos = correos.filtered(lambda m: not (m.model and self._es_protegido(m.model, protegidos)))
        cantidad = len(correos)
        correos.unlink()
        return cantidad

    # ------------------------------------------------------------------ reporte

    @api.model
    def _cron_reporte_tamanos(self):
        datos = self._medir_tamanos()
        # Memoria real del contenedor (anónima vs caché, RSS/PSS de Odoo y PostgreSQL, OOM):
        # el panel de Cloudflare no distingue la caché de páginas (ver dcasa_base/memoria.py).
        datos['memoria'] = memoria.medir()
        mensaje = 'DCASA_METRICA ' + json.dumps(datos, ensure_ascii=False, sort_keys=True)
        _logger.info(mensaje)
        self._registrar('dcasa.reporte_tamanos', 'INFO', mensaje, '_cron_reporte_tamanos')
        umbral = self._parametro('dcasa.reporte.alerta_gb', float)
        if datos['base_bytes'] > umbral * GB:
            texto = self._texto_alerta_base(datos['base_bytes'], umbral)
            datos['alerta'] = 'DCASA_ALERTA ' + texto
            self._alertar('base', texto, 'dcasa.reporte_tamanos')
        oom = (datos['memoria']['cgroup'].get('eventos') or {}).get('oom_kill')
        if oom:
            self._alertar('oom', f'el kernel mató {oom} proceso(s) por falta de memoria (oom_kill) '
                                 'desde que arrancó el contenedor', 'dcasa.reporte_tamanos')
        return datos

    @api.model
    def _texto_alerta_base(self, base_bytes, umbral):
        return (f'la base pesa {base_bytes / GB:.2f} GB (umbral {umbral:g} GB): '
                'sacar adjuntos a R2 o subir de tipo de contenedor (basic ≈ 1 GB máx.)')

    # ------------------------------------------------------------------ alertas

    @api.model
    def _alertar(self, clave, texto, nombre='dcasa.alerta'):
        """Deja ``DCASA_ALERTA`` en el log y en ir.logging y lo manda por Telegram.

        ``clave`` identifica el aviso (``base``, ``disco``, ``memoria``, ``oom``): el mismo no
        se vuelve a mandar por Telegram antes de ``dcasa.alerta.silencio_h`` horas (el log y
        ir.logging lo reciben siempre). Devuelve ``True`` si se mandó.
        """
        alerta = 'DCASA_ALERTA ' + texto
        _logger.warning(alerta)
        self._registrar(nombre, 'WARNING', alerta, '_alertar')
        icp = self.env['ir.config_parameter'].sudo()
        marca = f'dcasa.alerta.enviada.{clave}'
        ultima = fields.Datetime.to_datetime(icp.get_param(marca) or None)
        silencio = timedelta(hours=self._parametro('dcasa.alerta.silencio_h', float))
        if ultima and fields.Datetime.now() - ultima < silencio:
            return False
        if not self._avisar_operacion(texto):
            return False
        icp.set_param(marca, fields.Datetime.to_string(fields.Datetime.now()))
        return True

    @api.model
    def _avisar_operacion(self, texto):
        """Canal de avisos de operación: el Telegram de Brian a los administradores vinculados,
        que ``dcasa_seguridad`` ofrece en ``res.users._dcasa_avisar_operacion``. Sin ese módulo
        (o sin nadie vinculado) no hay canal y devuelve ``False``."""
        avisar = getattr(self.env['res.users'], '_dcasa_avisar_operacion', None)
        if avisar is None:
            return False
        return bool(avisar(f"D'CASA · {texto}"))

    @api.model
    def _ruta_disco(self):
        """El disco que se llena en el contenedor: el data_dir de Odoo (PostgreSQL vive al lado)."""
        return tools.config['data_dir']

    @api.model
    def _medir_recursos(self):
        datos = {'memoria': memoria.medir()}
        try:
            uso = shutil.disk_usage(self._ruta_disco())
            datos['disco'] = {'total': uso.total, 'usado': uso.used, 'libre': uso.free,
                              'pct': round(100 * uso.used / uso.total, 1) if uso.total else None}
        except OSError:
            datos['disco'] = {'pct': None}
        cg = datos['memoria']['cgroup']
        en_uso = pct = None
        if cg.get('current') is not None:
            en_uso = cg['current'] - (cg.get('file') or 0)
            if cg.get('max'):
                pct = round(100 * en_uso / cg['max'], 1)
        datos['memoria_pct'] = pct
        datos['memoria_en_uso'] = en_uso
        self.env.cr.execute('SELECT pg_database_size(current_database())')
        datos['base_bytes'] = self.env.cr.fetchone()[0]
        return datos

    @api.model
    def _cron_vigilar_recursos(self):
        """Cada hora: disco, memoria, tamaño de la base y OOM contra sus umbrales."""
        datos = self._medir_recursos()
        _logger.info('DCASA_METRICA %s', json.dumps(
            {k: datos[k] for k in ('disco', 'memoria_pct', 'memoria_en_uso', 'base_bytes')}, sort_keys=True))
        alertas = []
        disco_pct = self._parametro('dcasa.alerta.disco_pct', float)
        if datos['disco'].get('pct') is not None and datos['disco']['pct'] >= disco_pct:
            alertas.append(('disco', f"el disco del contenedor va al {datos['disco']['pct']:.0f} % "
                                     f"(umbral {disco_pct:g} %): quedan {datos['disco']['libre'] / GB:.2f} GB"))
        memoria_pct = self._parametro('dcasa.alerta.memoria_pct', float)
        if datos['memoria_pct'] is not None and datos['memoria_pct'] >= memoria_pct:
            cg = datos['memoria']['cgroup']
            alertas.append(('memoria', f"la memoria en uso va al {datos['memoria_pct']:.0f} % del límite "
                                       f"(umbral {memoria_pct:g} %): {datos['memoria_en_uso'] / GB:.2f} de "
                                       f"{cg['max'] / GB:.2f} GB"))
        umbral_gb = self._parametro('dcasa.reporte.alerta_gb', float)
        if datos['base_bytes'] > umbral_gb * GB:
            alertas.append(('base', self._texto_alerta_base(datos['base_bytes'], umbral_gb)))
        oom = (datos['memoria']['cgroup'].get('eventos') or {}).get('oom_kill') or 0
        icp = self.env['ir.config_parameter'].sudo()
        visto = int(icp.get_param('dcasa.alerta.oom_visto') or 0)
        if oom > visto:
            alertas.append(('oom', f'el kernel mató {oom - visto} proceso(s) por falta de memoria (oom_kill) '
                                   'desde la última revisión'))
        if oom != visto:  # también baja a 0 cuando el contenedor arrancó de nuevo
            icp.set_param('dcasa.alerta.oom_visto', str(oom))
        datos['alertas'] = {clave: self._alertar(clave, texto) for clave, texto in alertas}
        return datos

    # ------------------------------------------------------------------ crons de Odoo

    @api.model
    def _ajustar_crons_odoo(self):
        """Apaga o espacia las acciones planificadas de Odoo que no aplican (``CRONS_ODOO``).

        Se llama desde ``data/crons_odoo.xml`` en cada instalación o actualización. Devuelve
        {xmlid: 'ajustado' | 'ya estaba' | 'no existe'}.
        """
        resultado = {}
        for xmlid, valores in CRONS_ODOO.items():
            cron = self.env.ref(xmlid, raise_if_not_found=False)
            if not cron or cron._name != 'ir.cron':
                resultado[xmlid] = 'no existe'
                continue
            cron = cron.sudo().with_context(active_test=False)
            cambios = {campo: valor for campo, valor in valores.items() if cron[campo] != valor}
            if cambios:
                cron.write(cambios)
                resultado[xmlid] = 'ajustado'
            else:
                resultado[xmlid] = 'ya estaba'
        ajustados = sorted(x for x, r in resultado.items() if r == 'ajustado')
        if ajustados:
            _logger.info("Crons de Odoo ajustados para D'CASA: %s", ', '.join(ajustados))
        return resultado

    @api.model
    def _medir_tamanos(self):
        cr = self.env.cr
        cr.execute('SELECT pg_database_size(current_database())')
        base = cr.fetchone()[0]
        cr.execute("""
            SELECT c.relname, pg_total_relation_size(c.oid)
              FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE c.relkind = 'r' AND n.nspname = current_schema()
             ORDER BY 2 DESC LIMIT 10
        """)
        tablas = dict(cr.fetchall())
        cr.execute("""
            SELECT COALESCE(res_model, '(sin modelo)'), COUNT(*), COALESCE(SUM(file_size), 0)
              FROM ir_attachment GROUP BY 1 ORDER BY 3 DESC
        """)
        adjuntos = {modelo: {'n': n, 'bytes': int(b)} for modelo, n, b in cr.fetchall()}
        return {'base_bytes': base, 'tablas_top10': tablas, 'adjuntos_por_modelo': adjuntos}

    # ------------------------------------------------------------------ registro

    @api.model
    def _registrar(self, nombre, nivel, mensaje, funcion):
        """Deja la línea en ir.logging (Ajustes → Técnico → Registros) para verla sin la consola."""
        self.env['ir.logging'].sudo().create({
            'name': nombre,
            'type': 'server',
            'dbname': self.env.cr.dbname,
            'level': nivel,
            'message': mensaje,
            'path': __name__,
            'func': funcion,
            'line': '0',
        })
