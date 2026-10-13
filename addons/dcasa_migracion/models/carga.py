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

from .. import catalogo, contactos, documentos, informe, precios, reglas

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
    archivo_ventas = fields.Binary('ventas_pendientes.csv', attachment=False)
    nombre_ventas = fields.Char()
    archivo_ventas_lineas = fields.Binary('ventas_pendientes_lineas.csv', attachment=False)
    nombre_ventas_lineas = fields.Char()
    archivo_compras = fields.Binary('compras_pendientes.csv', attachment=False)
    nombre_compras = fields.Char()
    archivo_compras_lineas = fields.Binary('compras_pendientes_lineas.csv', attachment=False)
    nombre_compras_lineas = fields.Char()
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
                      'archivo_precios', 'archivo_ventas', 'archivo_ventas_lineas', 'archivo_compras',
                      'archivo_compras_lineas'):
            resumen.update(hashlib.sha256(self._bytes(campo)).digest())
        resumen.update(b'precios' if self.actualizar_precios else b'sin-precios')
        return resumen.hexdigest()

    def _textos(self):
        """Los textos de los archivos subidos (``{nombre: texto}``, solo los que hay), o un error claro."""
        campos = {'clientes': 'archivo_clientes', 'proveedores': 'archivo_proveedores',
                  'productos': 'archivo_productos', 'inventario': 'archivo_inventario',
                  'precios': 'archivo_precios', 'ventas': 'archivo_ventas', 'ventas_lineas': 'archivo_ventas_lineas',
                  'compras': 'archivo_compras', 'compras_lineas': 'archivo_compras_lineas'}
        try:
            textos = {nombre: reglas.texto_de_bytes(self._bytes(campo)) for nombre, campo in campos.items()
                      if self[campo]}
        except reglas.ErrorDeArchivo as error:
            raise UserError(str(error)) from error
        if 'inventario' in textos and 'productos' not in textos:
            raise UserError(self.env._('Subiste inventario.csv sin productos.csv. Las existencias se cargan con los '
                                       'productos: sube los dos.'))
        for cabecera, lineas in (('ventas', 'ventas_lineas'), ('compras', 'compras_lineas')):
            if (cabecera in textos) != (lineas in textos):
                raise UserError(self.env._(
                    'Las órdenes pendientes van en dos archivos: %(cabecera)s_pendientes.csv y '
                    '%(cabecera)s_pendientes_lineas.csv. Sube los dos.', cabecera=cabecera))
        if not textos:
            raise UserError(self.env._(
                'Sube al menos un archivo: clientes.csv, proveedores.csv, productos.csv (con inventario.csv), '
                'precios_proveedor.csv o las ventas y compras pendientes.'))
        return textos

    def _leer(self, textos):
        """Lee todos los archivos (un error de archivo se avisa antes de tocar nada). ``{nombre: (filas, errores)}``."""
        try:
            leidos = {}
            for nombre, lector in (('clientes', reglas.filas_clientes), ('proveedores', reglas.filas_proveedores),
                                   ('precios', reglas.filas_precios_proveedor)):
                if nombre in textos:
                    leidos[nombre] = lector(textos[nombre])
            if 'ventas' in textos:
                leidos['ventas'] = reglas.filas_ventas_pendientes(textos['ventas'], textos['ventas_lineas'])
            if 'compras' in textos:
                leidos['compras'] = reglas.filas_compras_pendientes(textos['compras'], textos['compras_lineas'])
            # Leer productos aquí, antes de abrir el savepoint: así un número mal escrito corta con su fila.
            if 'productos' in textos:
                reglas.filas_catalogo(textos['productos'], textos.get('inventario'))
        except reglas.ErrorDeArchivo as error:
            raise UserError(str(error)) from error
        return leidos

    def _aplicar(self, textos, leidos):
        """Hace la carga en el orden que importa (contactos, productos, precios de proveedor y, al final, las ventas
        y compras abiertas, que usan a los contactos y a los productos). ``{parte del informe: resumen}``."""
        def con_errores_de_filas(nombre, resumen):
            resumen['con_error'] = list(leidos[nombre][1]) + resumen['con_error']
            return resumen

        salida = {}
        for nombre, rol in (('clientes', 'cliente'), ('proveedores', 'proveedor')):
            if nombre in leidos:
                salida[nombre] = con_errores_de_filas(
                    nombre, contactos.cargar_contactos(self.env, leidos[nombre][0], rol))
        if 'productos' in textos:
            salida['catalogo'], salida['avisos'] = catalogo.cargar_catalogo(
                self.env, textos['productos'], textos.get('inventario'), self.actualizar_precios)
        if 'precios' in leidos:
            salida['precios'] = con_errores_de_filas(
                'precios', precios.cargar_precios_proveedor(self.env, leidos['precios'][0]))
        if 'ventas' in leidos:
            ordenes = leidos['ventas'][0]
            salida['ventas'] = con_errores_de_filas('ventas', documentos.cargar_ventas_por_facturar(self.env, ordenes))
            salida['entregas'] = documentos.entregas_pendientes(self.env, ordenes)
        if 'compras' in leidos:
            ordenes = leidos['compras'][0]
            salida['compras_por_recibir'] = con_errores_de_filas(
                'compras', documentos.cargar_compras_por_recibir(self.env, ordenes))
            salida['compras_por_facturar'] = documentos.cargar_compras_por_facturar(self.env, ordenes)
        return salida

    def _correr(self, ensayo):
        """Lee los archivos y carga dentro de un savepoint; en el ensayo el savepoint se deshace. Devuelve el informe
        en HTML."""
        textos = self._textos()
        leidos = self._leer(textos)
        salida = {}
        inicio = time.monotonic()
        try:
            with self.env.cr.savepoint():
                salida = self._aplicar(textos, leidos)
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
            ventas=salida.get('ventas'), entregas=salida.get('entregas'),
            compras_por_recibir=salida.get('compras_por_recibir'),
            compras_por_facturar=salida.get('compras_por_facturar'),
            con_existencias='inventario' in textos, segundos=time.monotonic() - inicio)
