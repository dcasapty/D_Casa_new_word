"""El asistente «Cargar datos del sistema anterior» (Ajustes), solo para administradores.

Dos botones: «Revisar» corre la carga completa y la DESHACE (muestra qué pasaría) y «Cargar» la hace. «Cargar» solo
funciona si se revisó antes con exactamente los mismos archivos y opciones: así no se carga a ciegas. Los archivos
se quedan en la tabla temporal del asistente (que Odoo vacía sola), nunca como adjuntos ni en el repositorio.
"""
import base64
import copy
import hashlib
import logging
import time

from odoo import fields, models
from odoo.exceptions import AccessError, UserError

from .. import (
    catalogo,
    combos,
    contactos,
    documentos,
    historial,
    informe,
    precios,
    reglas,
    reglas_combos,
    reglas_historial,
)

_logger = logging.getLogger(__name__)


def _pendientes_del_commit(cr):
    """Foto de lo que Odoo tiene anotado para el momento del commit (``precommit`` y ``postcommit``)."""
    def copia(valor):
        return copy.copy(valor) if isinstance(valor, (dict, set, list)) else valor
    return [(cola, list(cola._funcs), {clave: (valor, copia(valor)) for clave, valor in cola.data.items()})
            for cola in (cr.precommit, cr.postcommit)]


def _devolver_pendientes_del_commit(pendientes):
    """Deja lo anotado para el commit como estaba antes del ensayo.

    Deshacer un savepoint deshace la base, pero NO lo que Odoo dejó anotado para después del commit: p. ej. el
    aumento del rango de cliente de cada ficha (``res.partner._increase_rank``). Si se queda anotado, al terminar la
    petición Odoo busca fichas que el ensayo ya deshizo y falla con «Registro faltante»."""
    for cola, funciones, datos in pendientes:
        cola._funcs.clear()
        cola._funcs.extend(funciones)
        for clave in [k for k in cola.data if k not in datos]:
            del cola.data[clave]
        for clave, (original, copia) in datos.items():
            cola.data[clave] = original
            if isinstance(original, dict):
                original.clear()
                original.update(copia)
            elif isinstance(original, set):
                original.clear()
                original.update(copia)
            elif isinstance(original, list):
                original[:] = copia


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
    archivo_facturas_clientes = fields.Binary('facturas_clientes.csv', attachment=False)
    nombre_facturas_clientes = fields.Char()
    archivo_facturas_clientes_lineas = fields.Binary('facturas_clientes_lineas.csv', attachment=False)
    nombre_facturas_clientes_lineas = fields.Char()
    archivo_facturas_proveedores = fields.Binary('facturas_proveedores.csv', attachment=False)
    nombre_facturas_proveedores = fields.Char()
    archivo_facturas_proveedores_lineas = fields.Binary('facturas_proveedores_lineas.csv', attachment=False)
    nombre_facturas_proveedores_lineas = fields.Char()
    archivo_pagos = fields.Binary('pagos.csv', attachment=False)
    nombre_pagos = fields.Char()
    archivo_combos = fields.Binary('combos.csv', attachment=False)
    nombre_combos = fields.Char()
    corregir_cama_por_nombre = fields.Boolean(
        'Corregir la cama por el código del nombre', default=False,
        help='Apagado (lo normal): los combos se cargan tal cual viene en combos.csv y los que no coinciden con su '
             'nombre solo se marcan en el informe. Encendido: si la cama del archivo no es la del código que dice el '
             'nombre del combo (p. ej. «… BLACK 908KBK» con la cama 908KBE) y existe un producto con ese código, se '
             'usa ese.')
    armar_combos_desde_nombre = fields.Boolean(
        'Armar los combos desde su nombre', default=False,
        help='Lee el nombre de cada combo («COMBO CAMA … + COLCHÓN …»), busca su cama y su colchón en el catálogo y '
             'arma los combos donde hay un solo producto posible. Los dudosos y los que no se encuentran solo se '
             'listan en el informe: nunca adivina. Sirve para empezar a vender mientras llega combos.csv.')
    actualizar_precios = fields.Boolean(
        'También cambiar precio y costo de los productos que ya existen', default=False,
        help='Apagado (lo normal): de un producto que ya existe solo cambian las existencias; su precio y su costo se '
             'quedan como están aquí. Encendido: precio y costo pasan a ser los del archivo (y el precio de un combo '
             'que ya existe, el de combos.csv).')
    huella_revisada = fields.Char(readonly=True, copy=False)
    informe = fields.Html(readonly=True, sanitize=False)

    # ------------------------------------------------------------------
    # Botones
    # ------------------------------------------------------------------

    def action_revisar(self):
        """Corre la carga y la deshace: solo muestra el informe de lo que pasaría."""
        self.ensure_one()
        self._exigir_administrador()
        resultado, _faltan = self._correr(ensayo=True)
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
        resultado, faltan = self._correr(ensayo=False)
        # Si quedan documentos por cargar, la revisión sigue valiendo: «Cargar» retoma donde se quedó.
        self.write({'informe': resultado, 'huella_revisada': self.huella_revisada if faltan else False})
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
                      'archivo_compras_lineas', 'archivo_facturas_clientes', 'archivo_facturas_clientes_lineas',
                      'archivo_facturas_proveedores', 'archivo_facturas_proveedores_lineas', 'archivo_pagos',
                      'archivo_combos'):
            resumen.update(hashlib.sha256(self._bytes(campo)).digest())
        resumen.update(b'precios' if self.actualizar_precios else b'sin-precios')
        resumen.update(b'combos-por-nombre' if self.armar_combos_desde_nombre else b'sin-combos-por-nombre')
        resumen.update(b'corregir-cama' if self.corregir_cama_por_nombre else b'sin-corregir-cama')
        return resumen.hexdigest()

    def _textos(self):
        """Los textos de los archivos subidos (``{nombre: texto}``, solo los que hay), o un error claro."""
        campos = {'clientes': 'archivo_clientes', 'proveedores': 'archivo_proveedores',
                  'productos': 'archivo_productos', 'inventario': 'archivo_inventario',
                  'precios': 'archivo_precios', 'ventas': 'archivo_ventas', 'ventas_lineas': 'archivo_ventas_lineas',
                  'compras': 'archivo_compras', 'compras_lineas': 'archivo_compras_lineas',
                  'facturas_clientes': 'archivo_facturas_clientes',
                  'facturas_clientes_lineas': 'archivo_facturas_clientes_lineas',
                  'facturas_proveedores': 'archivo_facturas_proveedores',
                  'facturas_proveedores_lineas': 'archivo_facturas_proveedores_lineas', 'pagos': 'archivo_pagos',
                  'combos': 'archivo_combos'}
        try:
            textos = {nombre: reglas.texto_de_bytes(self._bytes(campo)) for nombre, campo in campos.items()
                      if self[campo]}
        except reglas.ErrorDeArchivo as error:
            raise UserError(str(error)) from error
        if 'inventario' in textos and 'productos' not in textos:
            raise UserError(self.env._('Subiste inventario.csv sin productos.csv. Las existencias se cargan con los '
                                       'productos: sube los dos.'))
        for cabecera, lineas in (('ventas', 'ventas_lineas'), ('compras', 'compras_lineas'),
                                 ('facturas_clientes', 'facturas_clientes_lineas'),
                                 ('facturas_proveedores', 'facturas_proveedores_lineas')):
            if (cabecera in textos) != (lineas in textos):
                archivo = cabecera + ('_pendientes' if cabecera in ('ventas', 'compras') else '')
                raise UserError(self.env._(
                    'Este grupo va en dos archivos: %(archivo)s.csv y %(archivo)s_lineas.csv. Sube los dos.',
                    archivo=archivo))
        if not textos and not self.armar_combos_desde_nombre:
            raise UserError(self.env._(
                'Sube al menos un archivo: clientes.csv, proveedores.csv, productos.csv (con inventario.csv), '
                'precios_proveedor.csv, combos.csv, las ventas y compras pendientes, las facturas del año o los pagos '
                '(o marca «Armar los combos desde su nombre»).'))
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
            for rol, nombre in (('cliente', 'facturas_clientes'), ('proveedor', 'facturas_proveedores')):
                if nombre in textos:
                    leidos[nombre] = reglas_historial.filas_facturas(textos[nombre], textos[nombre + '_lineas'], rol)
            if 'pagos' in textos:
                leidos['pagos'] = reglas_historial.filas_pagos(textos['pagos'])
            if 'combos' in textos:
                leidos['combos'] = reglas_combos.filas_combos(textos['combos'])
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
        tratados = self.env['product.template'].browse()
        if 'combos' in leidos:
            salida['combos'], tratados = combos.cargar_combos(
                self.env, leidos['combos'][0], self.actualizar_precios, self.corregir_cama_por_nombre)
            salida['combos']['con_error'] = list(leidos['combos'][1]) + salida['combos']['con_error']
        if self.armar_combos_desde_nombre:
            salida['combos_nombre'] = combos.armar_desde_nombre(self.env, tratados)
        if 'ventas' in leidos:
            ordenes = leidos['ventas'][0]
            salida['ventas'] = con_errores_de_filas('ventas', documentos.cargar_ventas_por_facturar(self.env, ordenes))
            salida['entregas'] = documentos.entregas_pendientes(self.env, ordenes)
        if 'compras' in leidos:
            ordenes = leidos['compras'][0]
            salida['compras_por_recibir'] = con_errores_de_filas(
                'compras', documentos.cargar_compras_por_recibir(self.env, ordenes))
            salida['compras_por_facturar'] = documentos.cargar_compras_por_facturar(self.env, ordenes)
        if {'facturas_clientes', 'facturas_proveedores', 'pagos'} & set(leidos):
            segundos = None if self.env.context.get('dcasa_documentos_por_tanda') else historial.SEGUNDOS_POR_TANDA
            salida['historial'] = historial.cargar_historial(self.env, leidos, historial.Presupuesto(
                segundos=segundos, documentos=self.env.context.get('dcasa_documentos_por_tanda')))
        return salida

    def _correr(self, ensayo):
        """Lee los archivos y carga dentro de un savepoint; en el ensayo el savepoint se deshace. Devuelve ``(informe en
        HTML, documentos que faltan por cargar)``: si faltan, hay que pulsar «Cargar» otra vez."""
        textos = self._textos()
        leidos = self._leer(textos)
        salida = {}
        inicio = time.monotonic()
        pendientes = _pendientes_del_commit(self.env.cr) if ensayo else None
        try:
            with self.env.cr.savepoint():
                salida = self._aplicar(textos, leidos)
                if ensayo:
                    raise _Deshacer
        except _Deshacer:
            # Odoo guarda en memoria qué ficha tiene cada id externo (lo consultan los precios de proveedor): tras
            # deshacer el ensayo esa memoria apuntaría a fichas que ya no existen. Igual con lo que dejó anotado para
            # el commit (ver _devolver_pendientes_del_commit).
            self.env.registry.clear_cache()
            _devolver_pendientes_del_commit(pendientes)
        _logger.info('Carga del sistema anterior (%s) hecha por el usuario %s.',
                     'ensayo' if ensayo else 'real', self.env.uid)
        html = informe.informe_html(
            ensayo, clientes=salida.get('clientes'), proveedores=salida.get('proveedores'),
            catalogo=salida.get('catalogo'), avisos=salida.get('avisos'), precios=salida.get('precios'),
            ventas=salida.get('ventas'), entregas=salida.get('entregas'),
            compras_por_recibir=salida.get('compras_por_recibir'),
            compras_por_facturar=salida.get('compras_por_facturar'), historial=salida.get('historial'),
            combos=salida.get('combos'), combos_nombre=salida.get('combos_nombre'),
            con_existencias='inventario' in textos, segundos=time.monotonic() - inicio)
        return html, salida.get('historial', {}).get('faltan', 0)
