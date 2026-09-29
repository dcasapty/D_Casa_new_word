# ruff: noqa: F821  (`env` lo inyecta `odoo-bin shell`)
"""Datos de demostración para la previsualización (se ejecuta con `odoo-bin shell`).

Solo para bases de prueba: socios de ejemplo marcados como «Demo» y una factura con
dos productos del catálogo real (dcasa_catalogo). Nunca se corre contra producción.
"""
import os

if env['res.partner'].search_count([('name', '=like', 'Demo %')]):
    print('Los datos de demostración ya existen.')
else:
    company = env.ref('base.main_company')
    # Dos productos reales del catálogo, sin tamaños (una sola variante), para la factura demo.
    creados = env['product.template'].search(
        [('is_published', '=', True)], order='id').filtered(lambda t: t.product_variant_count == 1)[:2].product_variant_id

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
