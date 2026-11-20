"""El origen de una venta online lo escribe el carrito real de la tienda (``website._create_cart``): nace en la web y
queda anotado quién lo abrió. Tener ``website_id`` no basta (revisión adversarial, 2026-11-19; la definición única está
en ``dcasa_base``, ``models/venta_online.py``)."""
from odoo import Command
from odoo.addons.website_sale.tests.common import MockRequest
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestOrigenDelCarrito(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env.ref('website.default_website')

    def abrir_carrito(self, usuario):
        """El carrito que abre ``usuario`` en la tienda, por el mismo camino que la página y el chat de Andrés."""
        website = self.website.with_user(usuario)
        with MockRequest(website.env, website=website):
            return website._create_cart()

    def test_el_carrito_de_un_visitante_nace_en_la_web_y_anota_quien_lo_abrio(self):
        publico = self.env.ref('base.public_user')
        carrito = self.abrir_carrito(publico)
        self.assertEqual(carrito.website_id, self.website)
        self.assertTrue(carrito.dcasa_nacio_en_web and carrito.dcasa_venta_online)
        self.assertFalse(carrito.dcasa_via_andres or carrito.dcasa_llevada_por_vendedora)
        self.assertEqual(carrito.dcasa_creada_por_id, publico)
        self.assertTrue(carrito.dcasa_creada_por_id.share)

    def test_el_carrito_que_abre_alguien_del_equipo_tambien_nace_en_la_web_y_queda_a_su_nombre(self):
        persona = new_test_user(self.env, login='zz_carrito_equipo',
                                groups='base.group_user,sales_team.group_sale_salesman')
        carrito = self.abrir_carrito(persona)
        self.assertTrue(carrito.dcasa_nacio_en_web and carrito.dcasa_venta_online)
        self.assertEqual(carrito.dcasa_creada_por_id, persona)
        self.assertFalse(carrito.dcasa_creada_por_id.share, 'así Gerencia ve quién teclea pedidos de la página')

    def test_un_pedido_creado_con_website_id_fuera_del_carrito_no_nace_en_la_web(self):
        cliente = self.env['res.partner'].create({'name': 'Cliente carrito falso'})
        producto = self.env['product.product'].create({'name': 'MUEBLE CARRITO FALSO', 'type': 'consu'})
        for contexto in ({}, {'default_website_id': self.website.id}):
            with self.subTest(contexto=contexto):
                orden = self.env['sale.order'].with_context(**contexto).create({
                    'partner_id': cliente.id, 'website_id': self.website.id,
                    'order_line': [Command.create({'product_id': producto.id, 'product_uom_qty': 1})]})
                self.assertFalse(orden.dcasa_nacio_en_web or orden.dcasa_venta_online or orden.dcasa_creada_por_id)
