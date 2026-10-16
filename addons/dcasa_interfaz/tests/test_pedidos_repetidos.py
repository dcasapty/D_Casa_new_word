"""Pedidos que parecen repetidos (capturas de la dueña, 2026-10-16: S00062 y S00063 de la misma clienta, el mismo día,
por el mismo total y con 5 minutos de diferencia). Se avisa en el pedido antes de confirmarlo y en el Inicio de quien
controla la tienda; no se bloquea nada (puede ser una compra de verdad igual)."""
from datetime import timedelta

from odoo.tests import tagged

from .test_inicio_por_rol import VentasCommon


@tagged('post_install', '-at_install')
class TestPedidosRepetidos(VentasCommon):

    def test_el_pedido_avisa_si_el_cliente_ya_tiene_otro_igual_hoy(self):
        primero = self.pedido(cantidad=2)
        segundo = self.pedido(cantidad=2, confirmar=False)
        self.assertEqual(segundo.dcasa_posible_repetido, primero.name)
        self.assertIn(segundo.name, primero.dcasa_posible_repetido)
        distinto = self.pedido(cantidad=3, confirmar=False)
        self.assertFalse(distinto.dcasa_posible_repetido, 'otro total no es repetido')
        otro_cliente = self.env['sale.order'].create({
            'partner_id': self.env['res.partner'].create({'name': 'Otro cliente repetido'}).id,
            'order_line': [(0, 0, {'product_id': self.producto.id, 'product_uom_qty': 2})]})
        self.assertFalse(otro_cliente.dcasa_posible_repetido, 'otro cliente no es repetido')
        segundo.action_cancel()
        # El aviso se calcula al abrir el pedido (no se guarda): se vuelve a leer como lo haría la pantalla.
        (primero | segundo).invalidate_recordset(['dcasa_posible_repetido'])
        self.assertFalse(segundo.dcasa_posible_repetido, 'un pedido cancelado no avisa')
        self.assertNotIn(segundo.name, primero.dcasa_posible_repetido or '', 'ni cuenta para los demás')

    def test_un_pedido_de_otro_dia_no_es_repetido(self):
        primero = self.pedido(cantidad=2)
        primero.date_order = primero.date_order - timedelta(days=1)
        segundo = self.pedido(cantidad=2, confirmar=False)
        self.assertFalse(segundo.dcasa_posible_repetido)

    def test_gerencia_ve_los_repetidos_en_el_inicio(self):
        uno, dos = self.pedido(cantidad=4), self.pedido(cantidad=4)
        self.pedido(cantidad=5)
        repetidos = self.env['sale.order']._dcasa_pedidos_repetidos(self.hoy - timedelta(days=30))
        self.assertIn(uno, repetidos)
        self.assertIn(dos, repetidos)
        datos = self.env['dcasa.tablero'].with_user(self.gerencia).obtener_datos()
        aviso = next(a for a in datos['atencion'] if a['clave'] == 'pedidos_repetidos')
        self.assertGreaterEqual(aviso['cuenta'], 2)
        self.assertIn(uno.id, aviso['accion']['domain'][0][2])
        # La vendedora no ve la franja de la tienda.
        propios = self.env['dcasa.tablero'].with_user(self.vendedora).obtener_datos()['atencion']
        self.assertNotIn('pedidos_repetidos', [a['clave'] for a in propios])
