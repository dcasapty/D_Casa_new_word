"""Carga del inventario del sistema anterior (capturas del 2026-10-02, 535 productos).

El CSV es la transcripción de «up media/inventario-anterior/pagina-*.webp» (doble lectura;
copia en ``data/inventario_anterior.csv``). Reglas de la dueña (LEEME del inventario):

* La llave es el **código** (``default_code``); sin código, el nombre exacto. Mismo código =
  mismo producto: solo se actualizan existencias, costo y precio si cambiaron; nombre y fotos no
  se tocan. Código nuevo = producto nuevo (categoría por palabras del nombre, precio SIN ITBMS
  como el resto del catálogo, publicado en la web solo si tiene foto).
* «A la mano» es el stock: entra como ajuste de inventario (``stock.quant._apply_inventory``).
  Negativo → 0 y a la lista para conteo físico.
* «COMBO … + COLCHÓN» entra como producto sin publicar. «Descuento», «Propinas» y
  «X COLCHÓN … PARA COMBO» no se importan.
* Idempotente: la segunda corrida no crea nada ni deja movimientos de inventario.
"""
import base64
import logging
import os
import re

from odoo.addons.dcasa_base import itbms_de_venta
from odoo.modules.module import get_module_path
from odoo.tools import float_compare
from odoo.tools.misc import file_open

from .catalogo import MODULO, valores_producto_nuevo
from .reglas import (
    TAMANOS,
    categoria_de_inventario,
    filas_inventario,
    foto_por_codigo,
    tamano_del_nombre,
)

_logger = logging.getLogger(__name__)

CSV_INVENTARIO = f'{MODULO}/data/inventario_anterior.csv'
CARPETA_FOTOS = 'static/img/productos'


def leer_inventario_anterior():
    """Filas del CSV que trae el módulo (ver ``reglas.filas_inventario``)."""
    with file_open(CSV_INVENTARIO, 'r') as archivo:
        return filas_inventario(archivo.read())


def fotos_del_modulo():
    """Nombres de archivo de ``static/img/productos`` (las fotos que viajan con el módulo)."""
    carpeta = os.path.join(get_module_path(MODULO), CARPETA_FOTOS)
    return sorted(os.listdir(carpeta)) if os.path.isdir(carpeta) else []


def _foto_b64(nombre):
    with file_open(f'{MODULO}/{CARPETA_FOTOS}/{nombre}', 'rb') as archivo:
        return base64.b64encode(archivo.read())


def xmlid_inventario(llave):
    """``N-F10018-F-BK`` → ``inventario_anterior_n_f10018_f_bk`` (también vale un nombre)."""
    return 'inventario_anterior_' + re.sub(r'[^a-z0-9]+', '_', llave.lower()).strip('_')


def _buscar(env, fila):
    """La variante que ya es este producto: por xmlid de una carga anterior, por código o, sin
    código, por nombre exacto. Vacío si no está."""
    Variante = env['product.product'].with_context(active_test=False)
    plantilla = env.ref(f'{MODULO}.{xmlid_inventario(fila["llave"])}', raise_if_not_found=False)
    if plantilla:
        return plantilla.product_variant_ids[:1]
    if fila['codigo']:
        variante = Variante.search([('default_code', '=', fila['codigo'])], limit=1)
        return variante or _variante_por_tamano(Variante, fila)
    plantilla = env['product.template'].with_context(active_test=False).search(
        [('name', '=', fila['nombre'])], limit=1)
    return plantilla.product_variant_ids[:1]


def _variante_por_tamano(Variante, fila):
    """El catálogo guarda los tamaños como variantes con código ``CODIGO-FULL``; el inventario
    anterior trae el código a secas y el tamaño en el nombre («… TAMAÑO FULL»). Si todas las
    variantes ``CODIGO-<tamaño>`` son de un mismo producto y el nombre dice el tamaño, es esa."""
    tamano = tamano_del_nombre(fila['nombre'])
    if not tamano:
        return Variante
    tamanos = {t.upper() for t in TAMANOS}
    candidatas = Variante.search([('default_code', '=like', f"{fila['codigo']}-%")]).filtered(
        lambda v: v.default_code[len(fila['codigo']) + 1:].upper() in tamanos)
    if not candidatas or len(candidatas.product_tmpl_id) != 1:
        return Variante
    return candidatas.filtered(lambda v: v.default_code.upper() == f"{fila['codigo']}-{tamano}".upper())[:1]


def _actualizar(env, variante, fila):
    """Precio y costo si cambiaron (nada más). Devuelve los campos tocados."""
    cambios = []
    precio = fila['precio']
    if precio is not None and float_compare(variante.lst_price, precio, precision_digits=2):
        plantilla = variante.product_tmpl_id
        ptav = variante.product_template_attribute_value_ids[:1]
        if plantilla.product_variant_count > 1 and ptav:
            # Producto con variantes: se mueve el extra de esta variante, no el precio de todas.
            ptav.price_extra = ptav.price_extra + (precio - variante.lst_price)
        else:
            plantilla.list_price = precio
        cambios.append('precio')
    costo = fila['costo']
    if costo is not None and float_compare(variante.standard_price, costo, precision_digits=2):
        variante.standard_price = costo
        cambios.append('costo')
    return cambios


def _crear(env, fila, impuesto, foto):
    """Producto nuevo con las reglas del catálogo; publicado solo con foto y si no es combo."""
    vals = valores_producto_nuevo(env, fila['nombre'], fila['precio'] or 0.0, impuesto,
                                  categoria_de_inventario(fila), tamano_del_nombre(fila['nombre']))
    vals.update({
        'standard_price': fila['costo'] or 0.0,
        'is_published': bool(foto) and fila['clase'] != 'combo',
    })
    if fila['codigo']:
        vals['default_code'] = fila['codigo']
    if foto:
        vals['image_1920'] = _foto_b64(foto)
    plantilla = env['product.template'].create(vals)
    env['ir.model.data'].create({
        'module': MODULO, 'name': xmlid_inventario(fila['llave']), 'model': 'product.template',
        'res_id': plantilla.id, 'noupdate': True,
    })
    return plantilla.product_variant_ids[:1]


def _ajustar_stock(env, variante, ubicacion, existencias):
    """Ajuste de inventario a ``existencias`` en la ubicación; nada si ya está así."""
    actual = variante.with_context(location=ubicacion.id).qty_available
    if not float_compare(actual, existencias, precision_digits=2):
        return False
    env['stock.quant'].with_context(inventory_mode=True).create({
        'product_id': variante.id,
        'location_id': ubicacion.id,
        'inventory_quantity': existencias,
    })._apply_inventory()
    return True


def cargar_inventario_anterior(env, filas, fotos=None):
    """Aplica las filas del inventario anterior (``reglas.filas_inventario``) a Odoo.

    ``fotos`` es {código: archivo de static/img/productos}; por defecto, las que empiezan por el
    código. Devuelve un resumen con las llaves de cada grupo: ``creados``, ``actualizados`` (con
    algún cambio de precio, costo o existencias), ``sin_cambios``, ``negativos`` (entraron en 0),
    ``combos``, ``omitidos``, ``repetidos`` (segunda aparición de una llave: no se aplica),
    ``con_foto`` y ``sin_foto`` (de los creados). Idempotente: la segunda vez todo cae en ``sin_cambios``.
    """
    company = env.ref('base.main_company')
    env = env(context=dict(env.context, allowed_company_ids=company.ids, lang='es_419'))
    impuesto = itbms_de_venta(env, company)
    almacen = env['stock.warehouse'].search([('company_id', '=', company.id)], limit=1)
    ubicacion = almacen.lot_stock_id
    if fotos is None:
        fotos = foto_por_codigo({f['codigo'] for f in filas if f['codigo']}, fotos_del_modulo())
    resumen = {k: [] for k in ('creados', 'actualizados', 'sin_cambios', 'negativos', 'combos',
                               'omitidos', 'repetidos', 'con_foto', 'sin_foto')}
    vistas = set()
    for fila in filas:
        llave = fila['llave']
        if fila['clase'] == 'omitir':
            resumen['omitidos'].append(llave)
            continue
        if llave in vistas:
            _logger.warning('Inventario anterior: %s repetido en el CSV (fila %s): solo entra la primera.',
                            llave, fila['fila'])
            resumen['repetidos'].append(llave)
            continue
        vistas.add(llave)
        existencias = fila['a_la_mano']
        if existencias is not None and existencias < 0:
            resumen['negativos'].append(llave)
            existencias = 0.0
        if fila['clase'] == 'combo':
            resumen['combos'].append(llave)
        variante = _buscar(env, fila)
        if variante:
            cambios = _actualizar(env, variante, fila)
        else:
            foto = fotos.get(fila['codigo']) if fila['codigo'] else None
            variante = _crear(env, fila, impuesto, foto)
            resumen['creados'].append(llave)
            if fila['clase'] != 'combo':
                resumen['con_foto' if foto else 'sin_foto'].append(llave)
            cambios = None
        if existencias is not None and ubicacion and _ajustar_stock(env, variante, ubicacion, existencias):
            if cambios is not None:
                cambios.append('existencias')
        if cambios is not None:
            resumen['actualizados' if cambios else 'sin_cambios'].append(llave)
    _logger.info('Inventario anterior: %s creados, %s actualizados, %s sin cambios, %s negativos en 0, '
                 '%s combos sin publicar, %s omitidos, %s repetidos.',
                 len(resumen['creados']), len(resumen['actualizados']), len(resumen['sin_cambios']),
                 len(resumen['negativos']), len(resumen['combos']), len(resumen['omitidos']),
                 len(resumen['repetidos']))
    return resumen
