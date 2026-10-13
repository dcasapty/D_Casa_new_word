# ruff: noqa: F821  (`env` lo inyecta `odoo-bin shell`)
"""Datos de la prueba de integración de Juan (scripts/integracion_juan.sh). Se ejecuta con `odoo-bin shell`.

Solo para la base temporal de esa prueba, que se borra al terminar. Crea:

* algunos productos PUBLICADOS con precio, existencias y foto (y uno sin publicar, que el asistente no debe ver);
* una vendedora (usuario interno del equipo de ventas) y la clave del administrador, que llegan por variables
  de entorno generadas al momento (nunca están en el repositorio);
* `web.base.url` = https://dcasapty.com, como en producción (el entrypoint la congela): de ahí salen las URL
  de los adjuntos y de las fotos, y el puente de WhatsApp solo acepta ese dominio.
"""
import os

from odoo import Command

CLAVE_ADMIN = os.environ['INTEGRACION_CLAVE_ADMIN']
CLAVE_VENDEDORA = os.environ['INTEGRACION_CLAVE_VENDEDORA']
# Un PNG de 1×1 píxel: la foto de los productos de prueba.
PNG = b'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='

parametros = env['ir.config_parameter'].sudo()
parametros.set_param('web.base.url', 'https://dcasapty.com')
parametros.set_param('web.base.url.freeze', 'True')

env.ref('base.user_admin').write({'login': 'admin', 'password': CLAVE_ADMIN})
vendedora = env['res.users'].search([('login', '=', 'vendedora_integra')])
if vendedora:   # la base se reutilizó: solo cambia la clave de esta corrida
    vendedora.write({'password': CLAVE_VENDEDORA})
else:
    vendedora = env['res.users'].with_context(no_reset_password=True).create({
        'name': 'Vendedora Integración', 'login': 'vendedora_integra', 'password': CLAVE_VENDEDORA,
        'group_ids': [Command.set([env.ref('base.group_user').id, env.ref('sales_team.group_sale_salesman').id])],
    })

if env['product.template'].search_count([('default_code', '=', 'INT-CAMA-Q')]):
    env.cr.commit()
    print('Los productos de la prueba ya existían (base reutilizada).')
    raise SystemExit(0)

itbms = env['brian.herramientas']._b_itbms_venta()
categoria = env['product.public.category'].create({'name': 'Dormitorio Integración'})
almacen = env['stock.warehouse'].search([], limit=1)
base = {'type': 'consu', 'is_storable': True, 'sale_ok': True, 'is_published': True,
        'taxes_id': [Command.set(itbms.ids)], 'public_categ_ids': [Command.set(categoria.ids)]}
Plantilla = env['product.template']
productos = {
    'INT-CAMA-Q': Plantilla.create({**base, 'name': 'Cama Roble Queen Integración', 'default_code': 'INT-CAMA-Q',
                                    'list_price': 349.99, 'dcasa_medidas': 'Ancho × Largo: 160 × 200 cm',
                                    'description_sale': 'Cama de roble con cabecera.', 'image_1920': PNG}),
    'INT-CAMA-M': Plantilla.create({**base, 'name': 'Cama Matrimonial Integración', 'default_code': 'INT-CAMA-M',
                                    'list_price': 249.99, 'image_1920': PNG}),
    'INT-SOFA': Plantilla.create({**base, 'name': 'Sofá Gris Integración', 'default_code': 'INT-SOFA',
                                  'list_price': 800.0, 'image_1920': PNG}),
    'INT-SECRETO': Plantilla.create({**base, 'name': 'Borrador Interno Integración', 'default_code': 'INT-SECRETO',
                                     'list_price': 10.0, 'is_published': False}),
}
for codigo, cantidad in (('INT-CAMA-Q', 25), ('INT-CAMA-M', 3), ('INT-SECRETO', 9)):   # el sofá queda en 0: «agotado»
    env['stock.quant']._update_available_quantity(
        productos[codigo].product_variant_id, almacen.lot_stock_id, cantidad)

env.cr.commit()
print(f'Datos de la prueba de integración listos (vendedora id {vendedora.id}, {len(productos)} productos).')
