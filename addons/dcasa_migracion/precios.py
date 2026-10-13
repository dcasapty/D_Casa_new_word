"""Carga de los precios de proveedor (precios_proveedor.csv, ya leído por ``reglas.filas_precios_proveedor``).

Cada fila dice cuánto cobra un proveedor por un producto. Hace falta que el proveedor (proveedores.csv) y el producto
(productos.csv) ya estén cargados: se buscan por su número del sistema anterior y por su código. Si el producto tiene
varias medidas (variantes), el precio queda en la medida del código; si no, en el producto. Volver a cargar no repite
nada y NO cambia un precio que ya existe para ese proveedor, producto y cantidad mínima.
"""
import logging

import psycopg2

from odoo.exceptions import AccessError, UserError, ValidationError

from .contactos import MODULO, _motivo, xmlid_contacto

_logger = logging.getLogger(__name__)


def cargar_precios_proveedor(env, filas):
    """Devuelve ``{'creados': [(proveedor, codigo)], 'ya_estaban': [(proveedor, codigo)],
    'con_error': [(proveedor, codigo, motivo)]}``. No hace commit."""
    Info = env['product.supplierinfo']
    Variante = env['product.product'].with_context(active_test=False)
    resumen = {'creados': [], 'ya_estaban': [], 'con_error': []}
    for fila in filas:
        id_viejo, codigo = fila['id_proveedor_viejo'], fila['codigo']
        proveedor = env['ir.model.data']._xmlid_to_res_id(
            f'{MODULO}.{xmlid_contacto(id_viejo)}', raise_if_not_found=False)
        if not proveedor:
            resumen['con_error'].append(
                (id_viejo, codigo, 'el proveedor no está cargado: carga primero proveedores.csv'))
            continue
        variante = Variante.search([('default_code', '=', codigo)], limit=1)
        if not variante:
            resumen['con_error'].append(
                (id_viejo, codigo, 'no hay un producto con ese código: carga primero los productos'))
            continue
        plantilla = variante.product_tmpl_id
        valores = {
            'partner_id': proveedor, 'product_tmpl_id': plantilla.id, 'min_qty': fila['cantidad_minima'],
            'price': fila['precio'],
        }
        if plantilla.product_variant_count > 1:
            valores['product_id'] = variante.id
        existente = Info.with_context(active_test=False).search([
            ('partner_id', '=', proveedor), ('product_tmpl_id', '=', plantilla.id),
            ('product_id', '=', valores.get('product_id', False)), ('min_qty', '=', fila['cantidad_minima'])], limit=1)
        if existente:
            resumen['ya_estaban'].append((id_viejo, codigo))
            continue
        try:
            with env.cr.savepoint():
                Info.create(valores)
        except (ValidationError, UserError, AccessError, psycopg2.Error) as error:
            resumen['con_error'].append((id_viejo, codigo, _motivo(error)))
            continue
        resumen['creados'].append((id_viejo, codigo))
    _logger.info('Carga de precios de proveedor: %s creados, %s ya estaban, %s con error.',
                 len(resumen['creados']), len(resumen['ya_estaban']), len(resumen['con_error']))
    return resumen
