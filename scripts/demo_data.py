# ruff: noqa: F821  (`env` lo inyecta `odoo-bin shell`)
"""Datos de demostración para la previsualización (se ejecuta con `odoo-bin shell`).

Solo para bases de prueba: productos de la factura real INV/2026/00821 y socios
de ejemplo marcados como «Demo». Nunca se corre contra la base de producción.
"""
import base64
import io
import os

from PIL import Image, WebPImagePlugin  # noqa: F401  (Odoo limita los formatos de PIL; se registra WebP)

from odoo.tools.misc import file_path

# Catálogo SOLO para la previsualización: fotos de producto que trae Odoo y precios
# marcados «(demo)» en el nombre. Nada de esto va a producción ni es precio real.
CATALOGO_DEMO = [
    # (nombre, precio, categoría, imagen en product/static/img, orden en la portada)
    ('Sofá tapizado turquesa (demo)', 499.0, 'salas', 'product_product_d01-image.jpg', 1),
    ('Sofá capitoné arena (demo)', 549.0, 'salas', 'product_product_d01b-image.jpg', 2),
    ('Sofá de cuero cognac (demo)', 699.0, 'salas', 'product_product_d01c-image.jpg', 3),
    ('Comedor para 10 puestos (demo)', 899.0, 'comedores', 'product_product_46-image.jpg', 4),
    ('Silla tapizada petróleo (demo)', 69.0, 'comedores', 'product_product_11-image.jpg', 6),
    ('Silla tapizada gris (demo)', 69.0, 'comedores', 'product_product_11b-image.jpg', 8),
    ('Cómoda de madera espiga (demo)', 329.0, 'recamaras', 'product_product_10-image.jpg', 7),
    ('Aparador de roble (demo)', 379.0, 'recamaras', 'product_product_6-image.jpg', 9),
    ('Juego de terraza 4 puestos (demo)', 599.0, 'exteriores', 'dining_table.png', 5),
    ('Mesa consola de vidrio (demo)', 219.0, 'salas', 'product_product_8_glass-image.jpg', 10),
    ('Lámpara articulada negra (demo)', 59.0, 'decoracion', 'product_lamp.png', 11),
    ('Canasta organizadora azul (demo)', 19.0, 'decoracion', 'product_product_7-image.png', 12),
]


def imagen_b64(ruta, recorte_cuadrado=False):
    """Imagen en base64 (JPEG). Con recorte, se centra en un cuadrado (fotos de ambiente)."""
    try:
        with open(ruta, 'rb') as f:
            im = Image.open(f)
            im.load()
    except (OSError, ValueError):
        return False  # PIL sin soporte para el formato: el producto queda sin foto
    im = im.convert('RGBA')
    fondo = Image.new('RGB', im.size, 'white')
    fondo.paste(im, mask=im.getchannel('A'))
    im = fondo
    if recorte_cuadrado:
        lado = min(im.size)
        x, y = (im.width - lado) // 2, (im.height - lado) // 2
        im = im.crop((x, y, x + lado, y + lado))
    salida = io.BytesIO()
    im.save(salida, 'JPEG', quality=85)
    return base64.b64encode(salida.getvalue())

if env['res.partner'].search_count([('name', '=like', 'Demo %')]):
    print('Los datos de demostración ya existen.')
else:
    company = env.ref('base.main_company')
    tax = company.account_sale_tax_id
    Categ = env.ref
    # Productos y precios reales de la factura INV/2026/00821 (foto de ambiente de la categoría).
    productos = [
        ('COLCHON DULCESUENOS SEMI RESORTE Q (A)', 'DSRSOQ', 171.97, 'colchones'),
        ('CAMA QUEEN GREY CON ESTANTES', '1062010735N', 158.02, 'recamaras'),
    ]
    Product = env['product.product']
    creados = Product
    for nombre, codigo, precio, categoria in productos:
        creados |= Product.create({
            'name': nombre, 'default_code': codigo, 'type': 'consu', 'invoice_policy': 'order',
            'list_price': precio, 'taxes_id': [(6, 0, tax.ids)], 'is_published': True,
            'public_categ_ids': [(6, 0, [Categ(f'website_dcasa.public_category_{categoria}').id])],
            'image_1920': imagen_b64(file_path(f'website_dcasa/static/src/img/cat-{categoria}.webp'),
                                     recorte_cuadrado=True),
            'website_sequence': 20,
        })

    for nombre, precio, categoria, imagen, orden in CATALOGO_DEMO:
        Product.create({
            'name': nombre, 'type': 'consu', 'list_price': precio, 'taxes_id': [(6, 0, tax.ids)],
            'is_published': True,
            'public_categ_ids': [(6, 0, [Categ(f'website_dcasa.public_category_{categoria}').id])],
            'image_1920': imagen_b64(file_path(f'product/static/img/{imagen}')),
            'website_sequence': orden,
        })

    Partner = env['res.partner']
    padrino = Partner.create({'name': 'Demo Ana', 'phone': '6555-1234'})
    padrino._dcasa_asegurar_ficha()
    padrino._dcasa_guardar_pin('482915')
    cliente = Partner.create({'name': 'Demo Eric', 'phone': '6123-4567', 'vat': '2-723-510',
                              'city': 'La Chorrera', 'country_id': env.ref('base.pa').id})
    cliente._dcasa_asegurar_ficha()
    cliente._dcasa_asignar_padrino(padrino)

    orden = env['sale.order'].create({
        'partner_id': cliente.id,
        'order_line': [(0, 0, {'product_id': p.id, 'product_uom_qty': 1}) for p in creados],
    })
    orden.action_confirm()
    factura = orden._create_invoices()
    factura.action_post()
    env['account.payment.register'].with_context(
        active_model='account.move', active_ids=factura.ids).create({})._create_payments()

    website = env.ref('website.default_website')
    website.logo = company.logo
    if os.environ.get('PREVIEW_URL'):
        env['ir.config_parameter'].sudo().set_param('web.base.url', os.environ['PREVIEW_URL'])
        env['ir.config_parameter'].sudo().set_param('web.base.url.freeze', 'True')
    print(f'Demo lista: factura {factura.name} ({factura.amount_total}), '
          f'socio {padrino.dcasa_socio_codigo} con {padrino.dcasa_saldo} puntos.')
env.cr.commit()
