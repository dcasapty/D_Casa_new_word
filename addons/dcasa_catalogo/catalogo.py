"""Carga del catálogo real (data/catalogo.json) en productos de Odoo.

El JSON y las fotos los genera ``scripts/importar_catalogo.py`` desde el Excel de la
empresa: aquí no se escribe ni se calcula ningún precio, solo se copian. Los precios del
Excel son SIN ITBMS («+ITBMS»): el producto lleva el ITBMS 7 % que se suma al precio.
"""
import base64
import json
import logging
import re

from odoo.addons.dcasa_base import archivar_itbms_incluido, itbms_de_venta
from odoo.tools.misc import file_open

from .reglas import (  # noqa: F401 (API del módulo)
    TAMANOS,
    categoria_de_nombre,
    precio_terminado_en_99,
    tamano_del_nombre,
)

_logger = logging.getLogger(__name__)

MODULO = 'dcasa_catalogo'

# Categoría del JSON → categoría interna (inventario/contabilidad).
CATEGORIA_INTERNA = {
    'salas': 'dcasa_base.product_category_salas',
    'recamaras': 'dcasa_base.product_category_recamaras',
    'colchones': 'dcasa_base.product_category_colchones',
    'zapateras': 'dcasa_catalogo.product_category_zapateras',
    'organizacion': 'dcasa_catalogo.product_category_organizacion',
    'oficina': 'dcasa_catalogo.product_category_oficina',
    'muebles_tv': 'dcasa_base.product_category_salas',
}
# Categoría del JSON → categoría de la tienda web (las demás son website_dcasa.public_category_<clave>).
CATEGORIA_WEB = {
    'muebles_tv': 'dcasa_catalogo.public_category_muebles_tv',
}


def leer_catalogo():
    with file_open(f'{MODULO}/data/catalogo.json', 'rb') as archivo:
        return json.load(archivo)


def xmlid_de(codigo):
    """``1062010734/5/6N`` → ``producto_1062010734_5_6n``."""
    return 'producto_' + re.sub(r'[^a-z0-9]+', '_', codigo.lower()).strip('_')


def foto_b64(nombre):
    with file_open(f'{MODULO}/static/img/productos/{nombre}', 'rb') as archivo:
        return base64.b64encode(archivo.read())


def pasar_a_itbms_que_se_suma(env):
    """Bases cargadas antes del 2026-10-01: el catálogo pasa del «ITBMS incluido» al que se suma.

    Los precios del Excel son sin ITBMS (decisión de la dueña): el ``list_price`` ya es la
    cifra correcta y no se toca; solo cambia el impuesto. Un producto cuyo impuesto la
    dueña cambió a mano (ya no es solo el «incluido» de la carga) se deja como está.
    La tienda pasa a mostrar el precio sin ITBMS («+ ITBMS») y, si el impuesto incluido
    queda sin uso, se archiva. Devuelve cuántos productos se corrigieron.
    """
    company = env.ref('base.main_company')
    venta = itbms_de_venta(env, company)
    ids = env['ir.model.data'].search([('module', '=', MODULO), ('model', '=', 'product.template')]).mapped('res_id')
    productos = env['product.template'].with_context(active_test=False).browse(ids).exists()
    corregidos = productos.filtered(lambda p: p.taxes_id and all(
        t.price_include and t.type_tax_use == 'sale' and t.amount == venta.amount for t in p.taxes_id))
    if venta and corregidos:
        corregidos.taxes_id = [(6, 0, venta.ids)]
    env['website'].search([]).show_line_subtotals_tax_selection = 'tax_excluded'
    archivar_itbms_incluido(env, company)
    _logger.info('Catálogo D\'CASA: %s productos pasan al ITBMS que se suma al precio.', len(corregidos))
    return len(corregidos)


def atributo_tamano(env):
    Atributo = env['product.attribute']
    atributo = Atributo.search([('name', '=', 'Tamaño')], limit=1) or Atributo.create({
        'name': 'Tamaño', 'create_variant': 'always', 'display_type': 'radio',
    })
    valores = {}
    for orden, nombre in enumerate(TAMANOS, start=1):
        valor = atributo.value_ids.filtered(lambda v, n=nombre: v.name == n)[:1]
        valores[nombre] = valor or env['product.attribute.value'].create({
            'name': nombre, 'attribute_id': atributo.id, 'sequence': orden,
        })
    return atributo, valores


def atributo_color(env, nombres):
    """Atributo «Color» (crea variantes) con los valores pedidos: {nombre: valor}."""
    Atributo = env['product.attribute']
    atributo = Atributo.search([('name', '=', 'Color'), ('create_variant', '=', 'always')], limit=1)
    atributo = atributo or Atributo.create({'name': 'Color', 'create_variant': 'always', 'display_type': 'radio'})
    valores = {}
    for nombre in nombres:
        valor = atributo.value_ids.filtered(lambda v, n=nombre: v.name.lower() == n.lower())[:1]
        valores[nombre] = valor or env['product.attribute.value'].create({
            'name': nombre, 'attribute_id': atributo.id,
        })
    return atributo, valores


def _poner_fotos_de_color(producto, item, atributo):
    """Cada variante de color con su foto (la primera) y su galería (las demás), y su referencia."""
    por_color = {nombre.lower(): fotos for nombre, fotos in item['colores'].items()}
    for variante in producto.product_variant_ids:
        color = variante.product_template_attribute_value_ids.filtered(
            lambda v: v.attribute_id == atributo).product_attribute_value_id.name
        fotos = por_color.get(color.lower()) or []
        vals = {'default_code': f"{item['codigo']}-{re.sub(r'[^A-Z0-9]+', '-', color.upper()).strip('-')}"}
        if fotos:
            vals['image_variant_1920'] = foto_b64(fotos[0])
            vals['product_variant_image_ids'] = [
                (0, 0, {'name': f"{item['nombre']} {color} ({i})", 'image_1920': foto_b64(foto)})
                for i, foto in enumerate(fotos[1:], start=2)
            ]
        variante.write(vals)


def categoria_web(env, clave):
    return env.ref(CATEGORIA_WEB.get(clave, f'website_dcasa.public_category_{clave}'))


def valores_producto_nuevo(env, nombre, precio, impuesto, clave_categoria=None, tamano=None):
    """Lo que lleva un producto nuevo de D'CASA (lo usan esta carga y la importación de Brian).

    Inventariable, existencias sin confirmar (la web deja comprar igual), ``list_price`` SIN
    ITBMS con el «ITBMS 7%» que se suma, categoría interna y de la tienda según la clave de
    ``reglas.CATEGORIAS`` y, si es de un solo tamaño, la línea de atributo «Tamaño» (para el
    filtro de la tienda). La publicación la decide quien llama.
    """
    vals = {
        'name': nombre,
        'type': 'consu',
        'is_storable': True,
        'allow_out_of_stock_order': True,  # existencias sin confirmar: se confirma por WhatsApp
        'list_price': precio,
        'taxes_id': [(6, 0, impuesto.ids)],
    }
    if clave_categoria in CATEGORIA_INTERNA:
        vals['categ_id'] = env.ref(CATEGORIA_INTERNA[clave_categoria]).id
        vals['public_categ_ids'] = [(6, 0, categoria_web(env, clave_categoria).ids)]
    if tamano in TAMANOS:
        atributo, valores = atributo_tamano(env)
        vals['attribute_line_ids'] = [(0, 0, {
            'attribute_id': atributo.id, 'value_ids': [(6, 0, valores[tamano].ids)]})]
    return vals


def _ficha_y_fotos(item):
    """Combo, medidas y fotos de la plantilla: la primera es la principal, el resto va a la galería."""
    vals = {}
    if item.get('combo'):
        vals['dcasa_combo'] = item['combo']
    if item.get('medidas'):
        vals['dcasa_medidas'] = item['medidas']
    fotos = item['fotos']
    if fotos:
        vals['image_1920'] = foto_b64(fotos[0])
        vals['product_template_image_ids'] = [
            (0, 0, {'name': f"{item['nombre']} ({i})", 'image_1920': foto_b64(foto)})
            for i, foto in enumerate(fotos[1:], start=2)
        ]
    return vals


def cargar_catalogo(env):
    """Crea los productos que falten. Lo que ya existe (por su xmlid) no se toca.

    Tampoco se crea un código que ya está en Odoo sin ser de esta carga (p. ej. lo cargó Brian
    desde el Excel del proveedor): no se duplica ni se pisa; queda en el registro.
    Los pedidos nuevos (``item['pedido']``) entran igual que la carga inicial; un código con
    varios colores (``item['colores']``) es un producto con variantes de «Color», cada una con
    su foto y el mismo precio.
    """
    company = env.ref('base.main_company')
    env = env(context=dict(env.context, allowed_company_ids=company.ids, lang='es_419'))
    impuesto = itbms_de_venta(env, company)
    atributo, valores = atributo_tamano(env)
    Template = env['product.template']
    Variante = env['product.product'].with_context(active_test=False)
    creados = 0
    for item in leer_catalogo():
        xmlid = xmlid_de(item['codigo'])
        if env.ref(f'{MODULO}.{xmlid}', raise_if_not_found=False):
            continue
        if Variante.search_count([('default_code', '=', item['codigo'])], limit=1):
            _logger.warning('Catálogo D\'CASA: %s ya existe en Odoo (no es de esta carga): no se crea.',
                            item['codigo'])
            continue
        precios = item['precios']
        tamanos = [t for t in TAMANOS if t in precios]
        unico = None if tamanos else tamano_del_nombre(item['nombre'])
        base = min(precios.values())
        fotos = item['fotos']
        vals = valores_producto_nuevo(env, item.get('nombre_web') or item['nombre'], base, impuesto,
                                      item['categoria'], unico)
        vals.update({
            'website_sequence': item['orden'] * 10,
            'is_published': bool(fotos),
        })
        colores = item.get('colores') or {}
        if not tamanos and not colores:
            vals['default_code'] = item['codigo']
        vals.update(_ficha_y_fotos(item))
        if tamanos:
            vals['attribute_line_ids'] = [(0, 0, {
                'attribute_id': atributo.id,
                'value_ids': [(6, 0, [valores[t].id for t in tamanos])],
            })]
        if colores:
            color, valores_color = atributo_color(env, list(colores))
            vals.setdefault('attribute_line_ids', []).append((0, 0, {
                'attribute_id': color.id,
                'value_ids': [(6, 0, [valores_color[c].id for c in colores])],
            }))
        producto = Template.create(vals)
        if colores:
            _poner_fotos_de_color(producto, item, color)
        if tamanos:
            for ptav in producto.attribute_line_ids.product_template_value_ids:
                ptav.price_extra = precios[ptav.name] - base
            for variante in producto.product_variant_ids:
                tamano = variante.product_template_attribute_value_ids.name
                variante.default_code = f"{item['codigo']}-{tamano.upper()}"
        env['ir.model.data'].create({
            'module': MODULO, 'name': xmlid, 'model': 'product.template',
            'res_id': producto.id, 'noupdate': True,
        })
        creados += 1

    # La tienda muestra la cifra del Excel (sin ITBMS) con «+ ITBMS»; el carrito suma el impuesto.
    env['website'].search([]).show_line_subtotals_tax_selection = 'tax_excluded'
    _logger.info('Catálogo D\'CASA: %s productos nuevos.', creados)
    return creados


def actualizar_catalogo(env):
    """Lleva los productos ya cargados a las fichas nuevas sin pisar lo que la dueña cambió.

    Solo toca un dato si sigue como lo dejó la carga anterior: el nombre si es el del Excel,
    las medidas y el combo si están vacíos, la categoría si sigue la original.
    """
    atributo, valores = atributo_tamano(env)
    salas = env.ref('website_dcasa.public_category_salas')
    for item in leer_catalogo():
        producto = env.ref(f'{MODULO}.{xmlid_de(item["codigo"])}', raise_if_not_found=False)
        if not producto:
            continue
        cambios = {}
        if producto.name == item['nombre'] and item.get('nombre_web'):
            cambios['name'] = item['nombre_web']
        if item.get('medidas') and not producto.dcasa_medidas:
            cambios['dcasa_medidas'] = item['medidas']
        if item.get('combo') and not producto.dcasa_combo:
            cambios['dcasa_combo'] = item['combo']
            if str(producto.description_ecommerce or '') == f'<p>{item["combo"]}</p>':
                cambios['description_ecommerce'] = False
        if item['categoria'] in CATEGORIA_WEB and producto.public_categ_ids == salas:
            cambios['public_categ_ids'] = [(6, 0, categoria_web(env, item['categoria']).ids)]
        unico = tamano_del_nombre(item['nombre'])
        if unico and len(item['precios']) == 1 and not producto.attribute_line_ids:
            cambios['attribute_line_ids'] = [(0, 0, {
                'attribute_id': atributo.id, 'value_ids': [(6, 0, valores[unico].ids)]})]
        if cambios:
            producto.write(cambios)


# --- Black Weekend ------------------------------------------------------------------------------

# Selección de la dueña (2026-10-02) entre sus 39 gráficas de «up media/115.png … 153.png»:
# (código del producto o de la variante destacada, gráfica de la que salió). El orden es el de la
# lista. Los precios NO están aquí: la web muestra los del catálogo (website_dcasa/models/black_weekend.py).
BLACK_WEEKEND = [
    ('888K', '115.png'),
    ('908K-NEGRO', '118.png'),
    ('803K', '122.png'),
    ('809Q', '123.png'),
    ('822F', '126.png'),
    ('825K', '129.png'),
    ('6220Q', '133.png'),
    ('6877F', '132.png'),
    ('Y0200100', '134.png'),
    ('Y0300300-LTSC07', '141.png'),  # el producto aparte del pedido ($129.99), no el Y0300300 anterior
    ('HK-BF-022-N-K-1-W', '153.png'),
    ('N-F10018-Q-BK', '151.png'),
]


def marcar_black_weekend(env):
    """Marca los productos de Black Weekend por su código (``default_code`` de la variante).

    Idempotente: deja la marca, el orden (10, 20, …) y, si el código es de una variante de color
    (908K-NEGRO), esa variante como la destacada. No quita la marca a otros productos (la dueña
    puede sumar más desde Odoo). Un código que no está se anota en el registro y se sigue.
    Devuelve cuántos productos quedaron marcados.
    """
    Variante = env['product.product'].with_context(active_test=False)
    marcados = 0
    for orden, (codigo, _grafica) in enumerate(BLACK_WEEKEND, start=1):
        variante = Variante.search([('default_code', '=', codigo)], limit=1)
        if not variante:
            _logger.warning('Black Weekend: el código %s no está en el catálogo: no se marca.', codigo)
            continue
        producto = variante.product_tmpl_id
        vals = {'dcasa_black_weekend': True, 'dcasa_bw_orden': orden * 10}
        vals['dcasa_bw_variante_id'] = variante.id if producto.product_variant_count > 1 else False
        cambios = {k: v for k, v in vals.items()
                   if (producto[k].id if k == 'dcasa_bw_variante_id' else producto[k]) != v}
        if cambios:
            producto.write(cambios)
        marcados += 1
    _logger.info('Black Weekend: %s productos marcados.', marcados)
    return marcados


# --- Existencias de prueba (solo staging) ------------------------------------------------------

PARAM_STOCK_PRUEBA = 'dcasa_catalogo.stock_prueba'


# Nombres del Excel que la dueña corrigió después de cargarlos: (código, nombre anterior, tamaño
# anterior, nombre nuevo, tamaño nuevo). El código y las medidas no cambian.
CORRECCIONES_DE_NOMBRE = [
    # 2026-10-02: es la Base Queen de su gráfica 153.png; el Excel LTSC-07 decía «King – blanco».
    ('HK-BF-022-N-K-1-W', 'Cama tapizada King – blanco', 'King', 'Cama tapizada Queen – blanco', 'Queen'),
]


def corregir_nombres(env):
    """Aplica ``CORRECCIONES_DE_NOMBRE`` a los productos ya cargados (idempotente).

    El nombre solo se cambia si sigue como lo dejó la carga (si la dueña lo editó, se respeta). El
    tamaño de la línea de atributo se cambia si sigue con el anterior: Odoo crea la variante nueva
    y archiva la vieja, así que el código pasa a la nueva (las ventas viejas siguen apuntando a la
    archivada).
    """
    _atributo, valores = atributo_tamano(env)
    corregidos = 0
    for codigo, nombre_viejo, tamano_viejo, nombre_nuevo, tamano_nuevo in CORRECCIONES_DE_NOMBRE:
        producto = env.ref(f'{MODULO}.{xmlid_de(codigo)}', raise_if_not_found=False)
        if not producto:
            continue
        if producto.name == nombre_viejo:
            producto.name = nombre_nuevo
            corregidos += 1
        linea = producto.attribute_line_ids.filtered(
            lambda lin, v=valores[tamano_viejo]: lin.attribute_id.name == 'Tamaño' and lin.value_ids == v)
        if linea:
            vieja = producto.product_variant_ids[:1]
            linea.value_ids = [(6, 0, valores[tamano_nuevo].ids)]
            nueva = producto.product_variant_ids[:1]
            if vieja != nueva and vieja.default_code == codigo:
                vieja.default_code = False
                nueva.default_code = codigo
    return corregidos


def stock_de_prueba(env):
    """Unidades de prueba por producto (``dcasa_catalogo.stock_prueba``); vacío, 0 o inválido = apagado.

    Lo fija docker/entrypoint.sh desde DCASA_STOCK_PRUEBA: 10 en staging, siempre 0 en producción.
    """
    valor = env['ir.config_parameter'].sudo().get_param(PARAM_STOCK_PRUEBA) or '0'
    try:
        return max(int(float(valor)), 0)
    except ValueError:
        return 0


def aplicar_stock_prueba(env):
    """Pone las unidades de prueba en el almacén principal a los productos que nunca tuvieron stock.

    Solo productos inventariables, sin lote/serie, con existencias 0 y SIN ningún movimiento de
    inventario: un conteo real (o una venta) nunca se pisa. Usa el ajuste de inventario de Odoo
    (``stock.quant._apply_inventory``), que deja su movimiento: por eso es idempotente (la
    segunda vez ya tienen movimiento). Devuelve cuántos productos recibieron existencias.
    """
    cantidad = stock_de_prueba(env)
    if cantidad <= 0:
        return 0
    company = env.ref('base.main_company')
    env = env(context=dict(env.context, allowed_company_ids=company.ids))
    almacen = env['stock.warehouse'].search([('company_id', '=', company.id)], limit=1)
    if not almacen:
        return 0
    productos = env['product.product'].search([
        ('is_storable', '=', True), ('tracking', '=', 'none'),
        ('company_id', 'in', [False, company.id]),
    ])
    con_movimientos = {
        producto.id for [producto] in env['stock.move'].sudo().with_context(active_test=False)._read_group(
            [('product_id', 'in', productos.ids)], ['product_id'])
    }
    sin_stock = productos.filtered(
        lambda p: p.id not in con_movimientos and p.with_company(company).qty_available == 0)
    if not sin_stock:
        return 0
    Quant = env['stock.quant'].with_context(inventory_mode=True)
    quants = Quant.browse()
    for producto in sin_stock:
        quants |= Quant.create({
            'product_id': producto.id,
            'location_id': almacen.lot_stock_id.id,
            'inventory_quantity': cantidad,
        })
    quants._apply_inventory()
    _logger.info('Existencias de prueba: %s productos con %s unidades en %s.',
                 len(sin_stock), cantidad, almacen.lot_stock_id.complete_name)
    return len(sin_stock)
