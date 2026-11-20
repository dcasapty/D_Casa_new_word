"""La cotización que arma Juan y el cliente paga cuenta como venta online (decisión de Gerencia, 2026-11-20), siempre
que ninguna vendedora haya intervenido: la misma comprobación de siempre (¿una vendedora le escribió al cliente por el
chat de Juan en los 30 días anteriores?). El origen lo marca la herramienta real de Juan, con la llave interna: ni un
campo ni un contexto que alguien mande lo marcan (revisión adversarial, 2026-11-19)."""
from datetime import timedelta

from odoo import Command, fields
from odoo.addons.dcasa_conversaciones.tests.test_cotizacion_automatica import CotizarCase
from odoo.exceptions import UserError
from odoo.tests import tagged


@tagged('post_install', '-at_install')
class TestCotizacionDeJuan(CotizarCase):

    def cotizada(self, conv=None):
        """La cotización que arma la herramienta ``cotizar`` de Juan (como el usuario del asistente, por la API)."""
        self.cotizar({'codigo': 'ZZ-SOFA', 'cantidad': 1}, conv=conv)
        return self.ordenes(conv)[-1]

    def escribe_la_vendedora(self, hace_dias):
        self.registrar('Te mando el enlace de la tienda', autor='vendedora', id_externo=self.conv.id_externo,
                       ts=fields.Datetime.now() - timedelta(days=hace_dias))

    def test_la_cotizacion_que_arma_juan_nace_por_un_flujo_digital_y_es_online_si_nadie_la_lleva(self):
        orden = self.cotizada()
        self.assertTrue(orden.dcasa_nacio_en_web, 'la herramienta de Juan marca el origen')
        self.assertTrue(orden.dcasa_venta_online)
        self.assertFalse(orden.dcasa_via_andres or orden.dcasa_creada_por_id, 'nadie abrió un carrito: lo armó Juan')
        orden.action_confirm()
        self.assertFalse(orden.dcasa_llevada_por_vendedora)
        self.assertTrue(orden.dcasa_venta_online, 'el cliente la pagó sin que una vendedora interviniera')

    def test_con_un_mensaje_de_una_vendedora_en_treinta_dias_es_de_ella_y_no_es_online(self):
        self.escribe_la_vendedora(hace_dias=3)
        orden = self.cotizada()
        self.assertTrue(orden.dcasa_nacio_en_web and orden.dcasa_venta_online, 'sin confirmar, nadie la llevó aún')
        orden.action_confirm()
        self.assertTrue(orden.dcasa_llevada_por_vendedora)
        self.assertFalse(orden.dcasa_venta_online)

    def test_un_mensaje_de_hace_mas_de_treinta_dias_no_cuenta(self):
        self.escribe_la_vendedora(hace_dias=45)
        orden = self.cotizada()
        orden.action_confirm()
        self.assertFalse(orden.dcasa_llevada_por_vendedora)
        self.assertTrue(orden.dcasa_venta_online)

    def test_una_cotizacion_que_arma_una_persona_en_ventas_no_es_online(self):
        """Un pedido tecleado por una persona, aunque diga que viene de la conversación y traiga ``website_id``."""
        sitio = self.env['website'].search([], limit=1)
        orden = self.env['sale.order'].with_user(self.vendedora).create({
            'partner_id': self.conv.partner_id.id, 'origin': 'Conversación Karen', 'website_id': sitio.id,
            'dcasa_nacio_en_web': True, 'dcasa_venta_online': True,
            'order_line': [Command.create({'product_id': self.sofa.product_variant_id.id, 'product_uom_qty': 1})]})
        self.assertFalse(orden.dcasa_nacio_en_web or orden.dcasa_venta_online)
        orden.action_confirm()
        self.assertFalse(orden.dcasa_venta_online)

    def test_el_origen_de_la_cotizacion_de_juan_no_se_marca_a_mano(self):
        orden = self.cotizada()
        tecleada = self.env['sale.order'].create({'partner_id': orden.partner_id.id})
        with self.assertRaisesRegex(UserError, 'lo pone el sistema'):
            tecleada.sudo().write({'dcasa_nacio_en_web': True})
        self.assertFalse(tecleada.dcasa_venta_online)
