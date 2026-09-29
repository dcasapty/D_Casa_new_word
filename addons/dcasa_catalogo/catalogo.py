"""Carga del catálogo real (data/catalogo.json) en productos de Odoo.

El JSON y las fotos los genera ``scripts/importar_catalogo.py`` desde el Excel de la
empresa: aquí no se escribe ni se calcula ningún precio, solo se copian.
"""
import base64
import json
import logging
import re

from markupsafe import Markup, escape

from odoo.tools.misc import file_open

_logger = logging.getLogger(__name__)

MODULO = 'dcasa_catalogo'
IMPUESTO_INCLUIDO = 'ITBMS 7% incluido'
TAMANOS = ['Twin', 'Full', 'Queen', 'King']

# Categoría del JSON → categoría interna (inventario/contabilidad).
CATEGORIA_INTERNA = {
    'salas': 'dcasa_base.product_category_salas',
    'recamaras': 'dcasa_base.product_category_recamaras',
    'colchones': 'dcasa_base.product_category_colchones',
    'zapateras': 'dcasa_catalogo.product_category_zapateras',
    'organizacion': 'dcasa_catalogo.product_category_organizacion',
    'oficina': 'dcasa_catalogo.product_category_oficina',
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


def impuesto_incluido(env, company):
    """El ITBMS de venta de la empresa, pero con el precio que ya lo incluye.

    Los precios del Excel son precio final (con ITBMS): con este impuesto la tienda, la
    cotización y la factura muestran exactamente esa cifra.
    """
    base = company.account_sale_tax_id
    if not base or base.price_include:
        return base
    Tax = env['account.tax'].with_company(company)
    existente = Tax.search([
        ('company_id', '=', company.id), ('type_tax_use', '=', 'sale'),
        ('amount_type', '=', base.amount_type), ('amount', '=', base.amount),
        ('price_include_override', '=', 'tax_included'),
    ], limit=1)
    return existente or base.copy({'name': IMPUESTO_INCLUIDO, 'price_include_override': 'tax_included'})


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


def cargar_catalogo(env):
    """Crea los productos que falten. Lo que ya existe (por su xmlid) no se toca."""
    company = env.ref('base.main_company')
    env = env(context=dict(env.context, allowed_company_ids=company.ids, lang='es_419'))
    impuesto = impuesto_incluido(env, company)
    atributo, valores = atributo_tamano(env)
    Template = env['product.template']
    creados = 0
    for item in leer_catalogo():
        xmlid = xmlid_de(item['codigo'])
        if env.ref(f'{MODULO}.{xmlid}', raise_if_not_found=False):
            continue
        precios = item['precios']
        tamanos = [t for t in TAMANOS if t in precios]
        base = min(precios.values())
        fotos = item['fotos']
        vals = {
            'name': item['nombre'],
            'type': 'consu',
            'is_storable': True,
            'allow_out_of_stock_order': True,  # existencias sin confirmar: se confirma por WhatsApp
            'list_price': base,
            'taxes_id': [(6, 0, impuesto.ids)],
            'categ_id': env.ref(CATEGORIA_INTERNA[item['categoria']]).id,
            'public_categ_ids': [(6, 0, env.ref(f"website_dcasa.public_category_{item['categoria']}").ids)],
            'website_sequence': item['orden'] * 10,
            'is_published': bool(fotos),
        }
        if not tamanos:
            vals['default_code'] = item['codigo']
        if item.get('combo'):
            vals['description_ecommerce'] = Markup('<p>%s</p>') % escape(item['combo'])
        if fotos:
            vals['image_1920'] = foto_b64(fotos[0])
            vals['product_template_image_ids'] = [
                (0, 0, {'name': f"{item['nombre']} ({i})", 'image_1920': foto_b64(foto)})
                for i, foto in enumerate(fotos[1:], start=2)
            ]
        if tamanos:
            vals['attribute_line_ids'] = [(0, 0, {
                'attribute_id': atributo.id,
                'value_ids': [(6, 0, [valores[t].id for t in tamanos])],
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

    # La tienda muestra el precio con ITBMS, igual que el Excel y la etiqueta en la tienda física.
    env['website'].search([]).show_line_subtotals_tax_selection = 'tax_included'
    _logger.info('Catálogo D\'CASA: %s productos nuevos.', creados)
    return creados
