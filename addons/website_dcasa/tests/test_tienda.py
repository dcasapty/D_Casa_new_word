from odoo.exceptions import ValidationError
from odoo.tests import HttpCase, TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestTiendaConfigurada(TransactionCase):
    """Auditoría de UX: un cliente puede pagar, elegir la entrega y escribir su dirección de Panamá."""

    def setUp(self):
        super().setUp()
        self.website = self.env.ref('website.default_website')

    def test_sitio_en_espanol(self):
        espanol = self.env['res.lang']._lang_get('es_419')
        self.assertEqual(self.website.default_lang_id, espanol)
        self.assertEqual(self.website.language_ids, espanol)

    def test_pagos_sin_pasarela(self):
        pagos = self.env['payment.provider'].search([('state', '=', 'enabled'), ('is_published', '=', True)])
        self.assertEqual(set(pagos.mapped('name')), {'Transferencia bancaria', 'Yappy', 'Pago al recibir o en tienda'})
        for pago in pagos:
            self.assertIn('WhatsApp', str(pago.with_context(lang='es_419').pending_msg))
        # Cada uno con su propio método: si no, la tienda juntaría Yappy y transferencia en una opción.
        self.assertEqual(len(pagos.payment_method_ids), 3)
        self.assertEqual(set(pagos.payment_method_ids.mapped('name')),
                         {'Transferencia bancaria', 'Yappy', 'Pago al recibir o en tienda'})

    def test_entregas_sin_envio_gratis_inventado(self):
        entregas = self.env['delivery.carrier'].search([('is_published', '=', True)])
        self.assertEqual(len(entregas), 2)
        self.assertTrue(all(entregas.mapped('allow_cash_on_delivery')))
        self.assertEqual(entregas.filtered('dcasa_por_cotizar').mapped('name'),
                         ['Entrega a domicilio: te cotizamos por WhatsApp'])
        self.assertFalse(self.env.ref('delivery.free_delivery_carrier').active)

    def test_direccion_de_panama(self):
        self.assertFalse(self.env.ref('base.pa').zip_required)
        self.assertFalse(self.env.ref('website_sale.address_b2b').active)

    def test_se_puede_repetir(self):
        antes = (self.env['payment.provider'].search_count([]), self.env['delivery.carrier'].search_count([]))
        self.website._dcasa_configurar_tienda()
        despues = (self.env['payment.provider'].search_count([]), self.env['delivery.carrier'].search_count([]))
        self.assertEqual(antes, despues)

    def test_whatsapp_valido(self):
        with self.assertRaises(ValidationError):
            self.website.dcasa_whatsapp_number = 'llámame'
        self.website.dcasa_whatsapp_number = '6026-1919'
        self.assertTrue(self.website._dcasa_whatsapp_url().startswith('https://wa.me/50760261919?'))


@tagged('post_install', '-at_install')
class TestCheckoutEnLaWeb(HttpCase):

    def test_ficha_con_whatsapp_primero(self):
        producto = self.env['product.template'].create({'name': 'Mesa prueba', 'list_price': 50, 'is_published': True})
        html = self.url_open(producto.website_url).text
        self.assertLess(html.index('o_dcasa_wa_producto'), html.index('id="add_to_cart"'))
        self.assertIn('lang="es', html)

    def test_sin_boton_flotante_en_el_carrito(self):
        self.assertIn('o_dcasa_wa_float', self.url_open('/').text)
        self.assertNotIn('o_dcasa_wa_float', self.url_open('/shop/cart').text)
