"""El asistente «Cargar datos del sistema anterior» (Ajustes), solo para administradores.

Dos botones: «Revisar» corre la carga completa y la DESHACE (muestra qué pasaría) y «Cargar» la hace. «Cargar» solo
funciona si se revisó antes con exactamente los mismos archivos y opciones: así no se carga a ciegas. Los archivos
se quedan en la tabla temporal del asistente (que Odoo vacía sola), nunca como adjuntos ni en el repositorio.
"""
import base64
import hashlib
import logging
import time

from odoo import fields, models
from odoo.exceptions import AccessError, UserError

from .. import catalogo, contactos, informe, precios, reglas

_logger = logging.getLogger(__name__)


class _Deshacer(Exception):
    """Para salir del savepoint del ensayo y que Odoo deshaga todo lo que se hizo dentro."""


class DcasaMigracionCarga(models.TransientModel):
    _name = 'dcasa.migracion.carga'
    _description = "Cargar datos del sistema anterior (asistente)"

    archivo_clientes = fields.Binary('clientes.csv', attachment=False)
    nombre_clientes = fields.Char()
    archivo_proveedores = fields.Binary('proveedores.csv', attachment=False)
    nombre_proveedores = fields.Char()
    archivo_productos = fields.Binary('productos.csv', attachment=False)
    nombre_productos = fields.Char()
    archivo_inventario = fields.Binary('inventario.csv', attachment=False)
    nombre_inventario = fields.Char()
    archivo_precios = fields.Binary('precios_proveedor.csv', attachment=False)
    nombre_precios = fields.Char()
    actualizar_precios = fields.Boolean(
        'También cambiar precio y costo de los productos que ya existen', default=False,
        help='Apagado (lo normal): de un producto que ya existe solo cambian las existencias; su precio y su costo se '
             'quedan como están aquí. Encendido: precio y costo pasan a ser los del archivo.')
    huella_revisada = fields.Char(readonly=True, copy=False)
    informe = fields.Html(readonly=True, sanitize=False)

    # ------------------------------------------------------------------
    # Botones
    # ------------------------------------------------------------------

    def action_revisar(self):
        """Corre la carga y la deshace: solo muestra el informe de lo que pasaría."""
        self.ensure_one()
        self._exigir_administrador()
        resultado = self._correr(ensayo=True)
        self.write({'informe': resultado, 'huella_revisada': self._huella()})
        return self._reabrir()

    def action_cargar(self):
        """Hace la carga. Exige haber revisado antes los mismos archivos."""
        self.ensure_one()
        self._exigir_administrador()
        if not self.huella_revisada or self.huella_revisada != self._huella():
            raise UserError(self.env._(
                'Antes de cargar, pulsa «Revisar» con estos mismos archivos y mira el informe. '
                'Si cambiaste un archivo o una casilla, hay que revisar otra vez.'))
        resultado = self._correr(ensayo=False)
        self.write({'informe': resultado, 'huella_revisada': False})
        return self._reabrir()

    # ------------------------------------------------------------------
    # Por dentro (privado: nada de esto se puede llamar por RPC)
    # ------------------------------------------------------------------

    def _exigir_administrador(self):
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(self.env._('Solo los administradores pueden cargar los datos del sistema anterior.'))

    def _reabrir(self):
        return {
            'type': 'ir.actions.act_window', 'name': self.env._('Cargar datos del sistema anterior'),
            'res_model': self._name, 'res_id': self.id, 'view_mode': 'form', 'target': 'new',
        }

    def _bytes(self, campo):
        valor = self[campo]
        return base64.b64decode(valor) if valor else b''

    def _huella(self):
        """Resume los archivos y las casillas: si algo cambia, la revisión anterior ya no vale."""
        resumen = hashlib.sha256()
        for campo in ('archivo_clientes', 'archivo_proveedores', 'archivo_productos', 'archivo_inventario',
                      'archivo_precios'):
            resumen.update(hashlib.sha256(self._bytes(campo)).digest())
        resumen.update(b'precios' if self.actualizar_precios else b'sin-precios')
        return resumen.hexdigest()

    def _textos(self):
        """Los textos de los archivos subidos (``{nombre: texto}``, solo los que hay), o un error claro."""
        campos = {'clientes': 'archivo_clientes', 'proveedores': 'archivo_proveedores',
                  'productos': 'archivo_productos', 'inventario': 'archivo_inventario',
                  'precios': 'archivo_precios'}
        try:
            textos = {nombre: reglas.texto_de_bytes(self._bytes(campo)) for nombre, campo in campos.items()
                      if self[campo]}
        except reglas.ErrorDeArchivo as error:
            raise UserError(str(error)) from error
        if 'inventario' in textos and 'productos' not in textos:
            raise UserError(self.env._('Subiste inventario.csv sin productos.csv. Las existencias se cargan con los '
                                       'productos: sube los dos.'))
        if not textos:
            raise UserError(self.env._(
                'Sube al menos un archivo: clientes.csv, proveedores.csv, productos.csv (con inventario.csv) o '
                'precios_proveedor.csv.'))
        return textos

    def _correr(self, ensayo):
        """Lee los archivos (un error de archivo se avisa antes de tocar nada) y carga dentro de un savepoint; en el
        ensayo el savepoint se deshace. Devuelve el informe en HTML. El orden importa: contactos, productos y, al
        final, los precios de proveedor (que usan a los dos)."""
        textos = self._textos()
        try:
            leidos = {}
            for nombre, lector in (('clientes', reglas.filas_clientes), ('proveedores', reglas.filas_proveedores)):
                if nombre in textos:
                    leidos[nombre] = lector(textos[nombre])
            if 'precios' in textos:
                leidos['precios'] = reglas.filas_precios_proveedor(textos['precios'])
            # Leer productos aquí, antes de abrir el savepoint: así un número mal escrito corta con su fila.
            if 'productos' in textos:
                reglas.filas_catalogo(textos['productos'], textos.get('inventario'))
        except reglas.ErrorDeArchivo as error:
            raise UserError(str(error)) from error

        salida = {}
        inicio = time.monotonic()
        try:
            with self.env.cr.savepoint():
                for nombre, rol in (('clientes', 'cliente'), ('proveedores', 'proveedor')):
                    if nombre in leidos:
                        filas, errores_de_filas = leidos[nombre]
                        resumen = contactos.cargar_contactos(self.env, filas, rol)
                        resumen['con_error'] = list(errores_de_filas) + resumen['con_error']
                        salida[nombre] = resumen
                if 'productos' in textos:
                    salida['catalogo'], salida['avisos'] = catalogo.cargar_catalogo(
                        self.env, textos['productos'], textos.get('inventario'), self.actualizar_precios)
                if 'precios' in leidos:
                    filas, errores_de_filas = leidos['precios']
                    resumen = precios.cargar_precios_proveedor(self.env, filas)
                    resumen['con_error'] = list(errores_de_filas) + resumen['con_error']
                    salida['precios'] = resumen
                if ensayo:
                    raise _Deshacer
        except _Deshacer:
            # Odoo guarda en memoria qué ficha tiene cada id externo (lo consultan los precios de proveedor): tras
            # deshacer el ensayo esa memoria apuntaría a fichas que ya no existen.
            self.env.registry.clear_cache()
        _logger.info('Carga del sistema anterior (%s) hecha por el usuario %s.',
                     'ensayo' if ensayo else 'real', self.env.uid)
        return informe.informe_html(
            ensayo, clientes=salida.get('clientes'), proveedores=salida.get('proveedores'),
            catalogo=salida.get('catalogo'), avisos=salida.get('avisos'), precios=salida.get('precios'),
            con_existencias='inventario' in textos, segundos=time.monotonic() - inicio)
