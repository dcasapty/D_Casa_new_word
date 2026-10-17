from lxml import etree

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
        self.assertEqual(set(pagos.mapped('name')), {'Transferencia bancaria', 'Yappy', 'Pago en la tienda'})
        for pago in pagos:
            self.assertIn('WhatsApp', str(pago.with_context(lang='es_419').pending_msg))
        # Cada uno con su propio método: si no, la tienda juntaría Yappy y transferencia en una opción.
        self.assertEqual(len(pagos.payment_method_ids), 3)
        self.assertEqual(set(pagos.payment_method_ids.mapped('name')),
                         {'Transferencia bancaria', 'Yappy', 'Pago en la tienda'})

    def test_no_hay_pago_contra_entrega(self):
        """Decisión de la dueña (2026-10-17): el mueble se entrega pagado completo; se paga en la tienda."""
        cod = self.env.ref('delivery.payment_provider_cod')
        mensaje = str(cod.with_context(lang='es_419').pending_msg)
        self.assertEqual(cod.with_context(lang='es_419').name, 'Pago en la tienda')
        self.assertNotIn('al recibir', mensaje)
        self.assertIn('pagado completo', mensaje)

    def test_el_pedido_hecho_agradece_con_tuteo(self):
        """La voz de la marca es de tú: «¡Gracias por tu compra!», no «Gracias por su orden.» de Odoo."""
        vista = self.env.ref('website_sale.confirmation')
        for idioma in ('es_419', 'en_US'):
            arco = etree.tostring(vista.with_context(lang=idioma)._get_combined_arch(), encoding='unicode')
            self.assertIn('¡Gracias por tu compra!', arco)
            self.assertNotIn('Gracias por su orden.', arco)
            self.assertNotIn('Thank you for your order.', arco)

    def test_copias_viejas_de_la_portada_se_corrigen(self):
        vista = self.env['ir.ui.view'].create({
            'name': 'Copia vieja FAQ', 'type': 'qweb', 'key': 'website_dcasa.prueba_faq_vieja',
            'website_id': self.website.id,
            'arch_db': '<t t-name="website_dcasa.prueba_faq_vieja"><div>'
                       '<p>Sí, llegamos a todo el país. Cuéntanos tu zona por WhatsApp y te decimos costo y fecha '
                       'de entrega.</p><p>Transferencia bancaria, Yappy, o pagas al recibir o en la tienda. '
                       'Escríbenos y te explicamos la que mejor te sirve.</p></div></t>',
        })
        self.assertEqual(self.env['website']._dcasa_corregir_textos(), 1)
        arch = vista.with_context(lang='es_419').arch_db
        self.assertNotIn('todo el país', arch)
        self.assertNotIn('al recibir', arch)
        self.assertIn('La Chorrera, Arraiján, Capira, Panamá y Colón', arch)
        self.assertEqual(self.env['website']._dcasa_corregir_textos(), 0, 'Se puede volver a correr')

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
