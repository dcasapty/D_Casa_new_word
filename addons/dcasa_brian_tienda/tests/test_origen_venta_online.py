"""Lo que Andrés vende y el cliente paga sin más intervención es venta online (definición única en ``dcasa_base``; desde
el 2026-11-20 si una vendedora atiende y cierra, es de ella): el carrito que arma el chat de la tienda nace en la web,
queda marcado «pasó por Andrés» y anota quién lo abrió. Prueba de punta a punta, por las rutas de verdad."""
from odoo.tests import new_test_user, tagged

from .common import RAIZ, TiendaCase


@tagged('post_install', '-at_install')
class TestOrigenVentaOnline(TiendaCase):

    def agregar(self, plantilla, cantidad=1):
        return self.post('carrito/agregar', {'producto_id': plantilla.product_variant_id.id, 'cantidad': cantidad})

    def ultimo_pedido(self):
        return self.env['sale.order'].sudo().search([('website_id', '!=', False)], order='id desc', limit=1)

    def test_el_carrito_de_andres_de_un_visitante_nace_en_la_web_y_pasa_por_andres(self):
        self.assertTrue(self.agregar(self.colchon, 2).json()['ok'])
        pedido = self.ultimo_pedido()
        self.assertTrue(pedido.dcasa_nacio_en_web and pedido.dcasa_via_andres and pedido.dcasa_venta_online)
        self.assertEqual(pedido.dcasa_creada_por_id, self.env.ref('base.public_user'))
        self.assertFalse(pedido.dcasa_llevada_por_vendedora)

    def test_el_carrito_de_andres_de_un_cliente_con_cuenta_anota_su_usuario(self):
        cliente = new_test_user(self.env, login='zzbt_origen', password='zzbt_origen', name='ZZBT Cliente Origen',
                                groups='base.group_portal')
        self.authenticate('zzbt_origen', 'zzbt_origen')
        self.assertTrue(self.agregar(self.colchon).json()['ok'])
        pedido = self.ultimo_pedido()
        self.assertTrue(pedido.dcasa_nacio_en_web and pedido.dcasa_via_andres)
        self.assertEqual(pedido.dcasa_creada_por_id, cliente)
        self.assertTrue(pedido.dcasa_creada_por_id.share, 'un cliente no es del equipo: no sale en la vigilancia')

    def test_un_carrito_que_ya_existia_y_toca_andres_queda_marcado(self):
        self.agregar(self.colchon)
        pedido = self.ultimo_pedido()
        pedido.sudo()._dcasa_escribir_marca(dcasa_via_andres=False)
        self.assertFalse(pedido.dcasa_via_andres)
        self.post('carrito/cantidad', {'producto_id': self.colchon.product_variant_id.id, 'cantidad': 3})
        self.assertTrue(pedido.dcasa_via_andres and pedido.dcasa_venta_online,
                        f'{RAIZ}: queda marcado y sigue siendo online')
