# ruff: noqa: F821  (`env` lo inyecta `odoo-bin shell`)
"""Datos de demostración para la previsualización (se ejecuta con `odoo-bin shell`).

Solo para bases de prueba: productos de la factura real INV/2026/00821 y socios
de ejemplo marcados como «Demo». Nunca se corre contra la base de producción.
"""
import os

if env['res.partner'].search_count([('name', '=like', 'Demo %')]):
    print('Los datos de demostración ya existen.')
else:
    company = env.ref('base.main_company')
    tax = company.account_sale_tax_id
    Categ = env.ref
    productos = [
        ('COLCHON DULCESUENOS SEMI RESORTE Q (A)', 'DSRSOQ', 171.97, 'website_dcasa.public_category_colchones'),
        ('CAMA QUEEN GREY CON ESTANTES', '1062010735N', 158.02, 'website_dcasa.public_category_recamaras'),
    ]
    Product = env['product.product']
    creados = Product
    for nombre, codigo, precio, categoria in productos:
        creados |= Product.create({
            'name': nombre, 'default_code': codigo, 'type': 'consu', 'invoice_policy': 'order',
            'list_price': precio, 'taxes_id': [(6, 0, tax.ids)], 'is_published': True,
            'public_categ_ids': [(6, 0, [Categ(categoria).id])],
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
