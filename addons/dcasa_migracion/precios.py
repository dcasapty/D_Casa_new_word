"""Carga de los precios de proveedor (precios_proveedor.csv, ya leído por ``reglas.filas_precios_proveedor``).

Cada fila dice cuánto cobra un proveedor por un producto. Hace falta que el proveedor (proveedores.csv) y el producto
(productos.csv) ya estén cargados: se buscan por su número del sistema anterior y por su código (o, si la fila no
trae código, por el nombre exacto). Si el producto tiene varias medidas (variantes), el precio queda en la medida del
código; si no, en el producto. Un precio 0 quiere decir «no se registró» y no se carga. Volver a cargar no repite nada
y NO cambia un precio que ya existe para ese proveedor, producto y cantidad mínima.
"""
import logging

import psycopg2

from odoo.exceptions import AccessError, UserError, ValidationError

from .contactos import MODULO, _motivo, xmlid_contacto

_logger = logging.getLogger(__name__)


def _producto(env, fila):
    """``(plantilla, variante)`` del producto de la fila, o ``(None, None)``: por código y, sin código, por nombre
    exacto (solo si hay uno)."""
    if fila['codigo']:
        variante = env['product.product'].with_context(active_test=False).search(
            [('default_code', '=', fila['codigo'])], limit=1)
        return (variante.product_tmpl_id, variante) if variante else (None, None)
    plantillas = env['product.template'].with_context(active_test=False).search([('name', '=', fila['nombre'])])
    if len(plantillas) == 1:
        return plantillas, plantillas.product_variant_ids[:1]
    return None, None


def cargar_precios_proveedor(env, filas):
    """Devuelve ``{'creados': [(proveedor, producto)], 'ya_estaban': [...], 'omitidos': [...], 'con_error':
    [(proveedor, producto, motivo)]}``. ``omitidos`` son los de precio 0. No hace commit."""
    Info = env['product.supplierinfo']
    moneda_de_la_empresa = env.company.currency_id
    resumen = {'creados': [], 'ya_estaban': [], 'omitidos': [], 'con_error': []}
    for fila in filas:
        id_viejo = fila['id_proveedor_viejo']
        producto = fila['codigo'] or fila['nombre']
        if not fila['precio']:
            resumen['omitidos'].append((id_viejo, producto))
            continue
        proveedor = env['ir.model.data']._xmlid_to_res_id(
            f'{MODULO}.{xmlid_contacto(id_viejo)}', raise_if_not_found=False)
        if not proveedor:
            resumen['con_error'].append(
                (id_viejo, producto, 'el proveedor no está cargado: carga primero proveedores.csv'))
            continue
        plantilla, variante = _producto(env, fila)
        if not plantilla:
            motivo = ('no hay un producto con ese código' if fila['codigo']
                      else 'no hay un solo producto con ese nombre')
            resumen['con_error'].append((id_viejo, producto, f'{motivo}: carga primero los productos'))
            continue
        moneda = moneda_de_la_empresa
        if fila['moneda'] and fila['moneda'].upper() != moneda_de_la_empresa.name:
            moneda = env['res.currency'].with_context(active_test=False).search(
                [('name', '=', fila['moneda'].upper())], limit=1)
            if not moneda:
                resumen['con_error'].append((id_viejo, producto, f'no conozco la moneda {fila["moneda"]}'))
                continue
        valores = {
            'partner_id': proveedor, 'product_tmpl_id': plantilla.id, 'min_qty': fila['cantidad_minima'],
            'price': fila['precio'], 'currency_id': moneda.id, 'discount': fila['descuento'], 'delay': fila['plazo'],
            'date_start': fila['desde'], 'date_end': fila['hasta'],
        }
        if plantilla.product_variant_count > 1 and variante:
            valores['product_id'] = variante.id
        existente = Info.with_context(active_test=False).search([
            ('partner_id', '=', proveedor), ('product_tmpl_id', '=', plantilla.id),
            ('product_id', '=', valores.get('product_id', False)), ('min_qty', '=', fila['cantidad_minima'])], limit=1)
        if existente:
            resumen['ya_estaban'].append((id_viejo, producto))
            continue
        try:
            with env.cr.savepoint():
                Info.create(valores)
        except (ValidationError, UserError, AccessError, psycopg2.Error) as error:
            resumen['con_error'].append((id_viejo, producto, _motivo(error)))
            continue
        resumen['creados'].append((id_viejo, producto))
    _logger.info('Carga de precios de proveedor: %s creados, %s ya estaban, %s sin precio, %s con error.',
                 len(resumen['creados']), len(resumen['ya_estaban']), len(resumen['omitidos']),
                 len(resumen['con_error']))
    return resumen
