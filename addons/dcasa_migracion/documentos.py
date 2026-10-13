"""Carga de lo que quedó a medias en el sistema anterior (``reglas.filas_ventas_pendientes`` y
``reglas.filas_compras_pendientes``): tres cargas distintas, cada una con lo que falta por hacer y nada más.

* **Ventas por facturar** → una factura de cliente en BORRADOR por orden, solo con las cantidades que faltaban por
  facturar. En borrador no tiene número, no va a la DGI y no suma puntos de Socios: quien factura la revisa y la
  publica, y recién ahí sale con el número que sigue en la numeración nueva.
* **Compras por recibir** → una orden de compra CONFIRMADA por orden, solo con las cantidades que faltaban por recibir:
  al recibir la mercancía entra al inventario. Si ya estaba facturada en el sistema anterior, la nota de la orden lo
  dice para no facturarla otra vez.
* **Compras por facturar** → una factura de proveedor en BORRADOR por orden, con las cantidades recibidas y aún sin
  factura. Se registra con el número del proveedor (``referencia_proveedor``); si el archivo no lo trae, queda vacío
  y en el informe.
* Las ventas **por entregar** no se cargan: se listan para entregarlas o rehacerlas a mano (el inventario de
  ``inventario.csv`` ya cuenta esa mercancía como existente).

Todo es idempotente: cada documento guarda el número de la orden vieja como id externo (``__import__``, igual que los
contactos) y volver a cargar el mismo archivo no repite nada. El cliente o proveedor y los productos se buscan por su
número y su código del sistema anterior: hay que cargarlos antes. Cada orden va en su propio savepoint.
"""
import logging
import re

import psycopg2

from odoo.addons.dcasa_base import itbms_de_venta
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import float_compare, plaintext2html

from .contactos import MODULO, _motivo, xmlid_contacto
from .precios import _producto

_logger = logging.getLogger(__name__)

TOLERANCIA = 0.01
ERRORES = (ValidationError, UserError, AccessError, psycopg2.Error)
AVISOS = ('sin_producto', 'total_distinto', 'sin_referencia', 'ya_facturadas')


def _xmlid(prefijo, numero_orden):
    return f'{prefijo}_' + re.sub(r'[^A-Za-z0-9_]', '_', numero_orden)


def _documento_ya_cargado(env, modelo, nombre):
    """El documento que ya se cargó con ese id externo, o vacío. Un id externo que apunta a algo borrado se limpia."""
    id_documento = env['ir.model.data']._xmlid_to_res_id(f'{MODULO}.{nombre}', raise_if_not_found=False)
    documento = env[modelo].browse(id_documento).exists() if id_documento else env[modelo]
    if id_documento and not documento:
        env['ir.model.data'].search([('module', '=', MODULO), ('name', '=', nombre)]).unlink()
    return documento


def _registrar(env, nombre, documento):
    env['ir.model.data'].create({
        'module': MODULO, 'name': nombre, 'model': documento._name, 'res_id': documento.id, 'noupdate': True})


def _contacto(env, id_viejo):
    return env['ir.model.data']._xmlid_to_res_id(f'{MODULO}.{xmlid_contacto(id_viejo)}', raise_if_not_found=False)


def _nombre_del_contacto(env, id_viejo):
    ficha = env['res.partner'].browse(_contacto(env, id_viejo)).exists()
    return ficha.name if ficha else f'n.º {id_viejo}'


def _linea(env, fila, cantidad, campo_cantidad, impuesto_sin_producto):
    """``(valores, con_producto)`` de una línea. Con producto, el nombre y los impuestos son los del producto; sin él
    (código que no existe aquí, servicio suelto) la línea lleva el nombre del archivo y el impuesto por defecto."""
    _, variante = _producto(env, fila)
    valores = {campo_cantidad: cantidad, 'price_unit': fila['precio'], 'discount': fila['descuento']}
    if variante:
        valores['product_id'] = variante.id
        return valores, True
    valores['name'] = fila['nombre'] or fila['codigo'] or 'Producto del sistema anterior'
    if impuesto_sin_producto:
        valores['tax_ids'] = [(6, 0, impuesto_sin_producto.ids)]
    return valores, False


def _resumen():
    return {'creados': [], 'ya_estaban': [], 'sin_pendiente': [], 'con_error': [], **{clave: [] for clave in AVISOS}}


def _recorrer(env, ordenes, modelo, prefijo, columna, resumen, crear, rol, archivo):
    """Pasa por cada orden con algo pendiente en ``columna`` y deja que ``crear(orden, contacto, lineas, avisos)``
    arme el documento. ``crear`` corre dentro de un savepoint: si falla, solo esa orden queda como error y sus avisos
    no se cuentan."""
    for orden in ordenes:
        numero = orden['numero']
        nombre = _xmlid(prefijo, numero)
        if _documento_ya_cargado(env, modelo, nombre):
            resumen['ya_estaban'].append(numero)
            continue
        lineas = [fila for fila in orden['lineas'] if float_compare(fila[columna], 0, precision_digits=4) > 0]
        if not lineas:
            resumen['sin_pendiente'].append(numero)
            continue
        contacto = _contacto(env, orden['id_contacto'])
        if not contacto:
            resumen['con_error'].append(
                (numero, f'el {rol} n.º {orden["id_contacto"]} no está cargado: carga primero {archivo}'))
            continue
        avisos = {clave: [] for clave in AVISOS}
        try:
            with env.cr.savepoint():
                documento = crear(orden, contacto, lineas, avisos)
                _registrar(env, nombre, documento)
        except ERRORES as error:
            resumen['con_error'].append((numero, _motivo(error)))
            continue
        resumen['creados'].append(numero)
        for clave, valores in avisos.items():
            resumen[clave].extend(valores)


def _completa(orden, columna):
    """Todas las líneas se facturan completas: el total del documento debe coincidir con el de la orden vieja."""
    return all(float_compare(fila[columna], fila['cantidad'], precision_digits=4) == 0 for fila in orden['lineas'])


def _comparar_total(avisos, orden, columna, documento):
    if orden['total'] is not None and _completa(orden, columna) \
            and abs(documento.amount_total - orden['total']) > TOLERANCIA:
        avisos['total_distinto'].append((orden['numero'], orden['total'], documento.amount_total))


def entregas_pendientes(env, ordenes):
    """Las ventas con mercancía por entregar (no se cargan): ``[(numero, cliente, [(producto, cantidad)])]``."""
    pendientes = []
    for orden in ordenes:
        faltan = [(fila['codigo'] or fila['nombre'], fila['pend_entregar']) for fila in orden['lineas']
                  if float_compare(fila['pend_entregar'], 0, precision_digits=4) > 0]
        if faltan:
            pendientes.append((orden['numero'], _nombre_del_contacto(env, orden['id_contacto']), faltan))
    return pendientes


def cargar_ventas_por_facturar(env, ordenes):
    """Facturas de cliente en borrador. Devuelve ``creados``, ``ya_estaban``, ``sin_pendiente`` (números de orden),
    ``con_error`` (``(numero, motivo)``), ``sin_producto`` (``(numero, producto)``: línea sin producto enlazado) y
    ``total_distinto`` (``(numero, total del archivo, total aquí)``). No hace commit."""
    Factura = env['account.move'].with_context(tracking_disable=True, mail_create_nolog=True, mail_notrack=True)
    impuesto = itbms_de_venta(env, env.company)
    resumen = _resumen()

    def crear(orden, cliente, lineas, avisos):
        valores_lineas = []
        for fila in lineas:
            valores, con_producto = _linea(env, fila, fila['pend_facturar'], 'quantity', impuesto)
            if not con_producto:
                avisos['sin_producto'].append((orden['numero'], fila['codigo'] or fila['nombre']))
            valores_lineas.append((0, 0, valores))
        factura = Factura.create({
            'move_type': 'out_invoice', 'partner_id': cliente, 'invoice_origin': orden['numero'],
            'narration': plaintext2html(f'Orden de venta {orden["numero"]} del sistema anterior, por facturar.'),
            'invoice_line_ids': valores_lineas})
        _comparar_total(avisos, orden, 'pend_facturar', factura)
        return factura

    _recorrer(env, ordenes, 'account.move', 'dcasa_venta', 'pend_facturar', resumen, crear, 'cliente',
             'clientes.csv')
    _logger.info('Carga de ventas por facturar: %s creadas, %s ya estaban, %s sin pendiente, %s con error.',
                 len(resumen['creados']), len(resumen['ya_estaban']), len(resumen['sin_pendiente']),
                 len(resumen['con_error']))
    return resumen


def cargar_compras_por_recibir(env, ordenes):
    """Órdenes de compra confirmadas con lo que falta recibir. Mismo resumen que ``cargar_ventas_por_facturar`` más
    ``ya_facturadas`` (números de orden que el sistema anterior ya había facturado, total o parcialmente). Odoo no
    confirma una orden con líneas sin producto: esa orden queda en ``con_error`` hasta que el producto exista."""
    Orden = env['purchase.order'].with_context(tracking_disable=True, mail_create_nolog=True, mail_notrack=True)
    resumen = _resumen()

    def crear(orden, proveedor, lineas, avisos):
        valores_lineas, sin_producto = [], []
        for fila in lineas:
            valores, con_producto = _linea(env, fila, fila['pend_recibir'], 'product_qty', None)
            if not con_producto:
                sin_producto.append(fila['codigo'] or fila['nombre'])
            valores_lineas.append((0, 0, valores))
        if sin_producto:
            raise UserError(f'estos productos no están cargados: {", ".join(sin_producto)}. Cárgalos primero '
                            f'(productos.csv) y vuelve a cargar: una orden de compra no se confirma sin producto')
        notas = [f'Orden de compra {orden["numero"]} del sistema anterior: solo lo que faltaba por recibir.']
        if any(fila['facturada'] > 0 for fila in orden['lineas']):
            notas.append('Ya tenía factura del proveedor en el sistema anterior: al recibirla, NO la factures otra '
                         'vez.')
            avisos['ya_facturadas'].append(orden['numero'])
        valores = {'partner_id': proveedor, 'origin': orden['numero'], 'partner_ref': orden['referencia'] or False,
                   'note': plaintext2html('\n'.join(notas)), 'order_line': valores_lineas}
        if orden['fecha']:
            valores['date_order'] = orden['fecha']
        compra = Orden.create(valores)
        compra.button_confirm()
        return compra

    _recorrer(env, ordenes, 'purchase.order', 'dcasa_compra', 'pend_recibir', resumen, crear, 'proveedor',
              'proveedores.csv')
    _logger.info('Carga de compras por recibir: %s creadas, %s ya estaban, %s sin pendiente, %s con error.',
                 len(resumen['creados']), len(resumen['ya_estaban']), len(resumen['sin_pendiente']),
                 len(resumen['con_error']))
    return resumen


def cargar_compras_por_facturar(env, ordenes):
    """Facturas de proveedor en borrador con lo recibido y sin factura. Mismo resumen que
    ``cargar_ventas_por_facturar`` más ``sin_referencia`` (órdenes cuyo archivo no trae el número del proveedor)."""
    Factura = env['account.move'].with_context(tracking_disable=True, mail_create_nolog=True, mail_notrack=True)
    impuesto = env.company.account_purchase_tax_id
    resumen = _resumen()

    def crear(orden, proveedor, lineas, avisos):
        valores_lineas = []
        for fila in lineas:
            valores, con_producto = _linea(env, fila, fila['pend_facturar'], 'quantity', impuesto)
            if not con_producto:
                avisos['sin_producto'].append((orden['numero'], fila['codigo'] or fila['nombre']))
            valores_lineas.append((0, 0, valores))
        if not orden['referencia']:
            avisos['sin_referencia'].append(orden['numero'])
        factura = Factura.create({
            'move_type': 'in_invoice', 'partner_id': proveedor, 'ref': orden['referencia'] or False,
            'invoice_origin': orden['numero'],
            'narration': plaintext2html(f'Orden de compra {orden["numero"]} del sistema anterior, por facturar.'),
            'invoice_line_ids': valores_lineas})
        _comparar_total(avisos, orden, 'pend_facturar', factura)
        return factura

    _recorrer(env, ordenes, 'account.move', 'dcasa_factura_compra', 'pend_facturar', resumen, crear,
             'proveedor', 'proveedores.csv')
    _logger.info('Carga de compras por facturar: %s creadas, %s ya estaban, %s sin pendiente, %s con error.',
                 len(resumen['creados']), len(resumen['ya_estaban']), len(resumen['sin_pendiente']),
                 len(resumen['con_error']))
    return resumen
