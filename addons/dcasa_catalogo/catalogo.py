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

_logger = logging.getLogger(__name__)

MODULO = 'dcasa_catalogo'
TAMANOS = ['Twin', 'Full', 'Queen', 'King']

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


def categoria_web(env, clave):
    return env.ref(CATEGORIA_WEB.get(clave, f'website_dcasa.public_category_{clave}'))


def tamano_del_nombre(nombre):
    """«Cama king» es de un solo tamaño, King: así aparece al filtrar la tienda por tamaño."""
    m = re.search(r'\b(twin|full|queen|king)\b', nombre, re.I)
    return m.group(1).capitalize() if m else None


def cargar_catalogo(env):
    """Crea los productos que falten. Lo que ya existe (por su xmlid) no se toca."""
    company = env.ref('base.main_company')
    env = env(context=dict(env.context, allowed_company_ids=company.ids, lang='es_419'))
    impuesto = itbms_de_venta(env, company)
    atributo, valores = atributo_tamano(env)
    Template = env['product.template']
    creados = 0
    for item in leer_catalogo():
        xmlid = xmlid_de(item['codigo'])
        if env.ref(f'{MODULO}.{xmlid}', raise_if_not_found=False):
            continue
        precios = item['precios']
        tamanos = [t for t in TAMANOS if t in precios]
        unico = None if tamanos else tamano_del_nombre(item['nombre'])
        base = min(precios.values())
        fotos = item['fotos']
        vals = {
            'name': item.get('nombre_web') or item['nombre'],
            'type': 'consu',
            'is_storable': True,
            'allow_out_of_stock_order': True,  # existencias sin confirmar: se confirma por WhatsApp
            'list_price': base,
            'taxes_id': [(6, 0, impuesto.ids)],
            'categ_id': env.ref(CATEGORIA_INTERNA[item['categoria']]).id,
            'public_categ_ids': [(6, 0, categoria_web(env, item['categoria']).ids)],
            'website_sequence': item['orden'] * 10,
            'is_published': bool(fotos),
        }
        if not tamanos:
            vals['default_code'] = item['codigo']
        if item.get('combo'):
            vals['dcasa_combo'] = item['combo']
        if item.get('medidas'):
            vals['dcasa_medidas'] = item['medidas']
        if fotos:
            vals['image_1920'] = foto_b64(fotos[0])
            vals['product_template_image_ids'] = [
                (0, 0, {'name': f"{item['nombre']} ({i})", 'image_1920': foto_b64(foto)})
                for i, foto in enumerate(fotos[1:], start=2)
            ]
        if tamanos or unico:
            vals['attribute_line_ids'] = [(0, 0, {
                'attribute_id': atributo.id,
                'value_ids': [(6, 0, [valores[t].id for t in (tamanos or [unico])])],
            })]
        producto = Template.create(vals)
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
