"""Entregas de prueba para el panel de Bodega (todo inventado: CLIENTE DE PRUEBA…)."""
from odoo import Command
from odoo.tests import new_test_user

from .comun import BarrasCommon

BASE = 'https://erp.example.com'   # el QR se reconoce con cualquier dominio (dcasa_invoice/models/documento.py)


class BodegaCommon(BarrasCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Bodega = cls.env['dcasa.bodega']
        # Quien trabaja en bodega: solo Inventario (usuario), sin Ventas ni Facturación.
        cls.bodeguero = new_test_user(cls.env, login='bodega_trabajador', groups='stock.group_stock_user')
        # Caja: además lee facturas y pedidos (el QR de una factura le abre su entrega).
        cls.caja = new_test_user(
            cls.env, login='bodega_caja',
            groups='stock.group_stock_user,sales_team.group_sale_salesman_all_leads,account.group_account_invoice')
        cls.mesa = cls.producto('Zzmesa de prueba', 'ZZT-MESA-9', barcode='ZZT-MESA-9-BAR', unidades=5)
        servicio = cls.env['product.product'].create({'name': 'Zz entrega de prueba', 'type': 'service'})
        Carrier = cls.env['delivery.carrier']
        cls.metodo_retiro = Carrier.create({
            'name': 'Zz retiro de prueba', 'product_id': servicio.id, 'delivery_type': 'fixed', 'fixed_price': 0,
            'dcasa_es_retiro': True})
        cls.metodo_envio = Carrier.create({
            'name': 'Zz envío de prueba', 'product_id': servicio.id, 'delivery_type': 'fixed', 'fixed_price': 0})
        cls.flete = cls.env.ref('dcasa_invoice.product_flete', raise_if_not_found=False) or \
            cls.env['product.product'].search([('default_code', '=', 'DCASA-FLETE')], limit=1)
        cls.cliente_envio = cls.cliente('CLIENTE DE PRUEBA ENVIO', telefono='6000-0001', calle='Calle de prueba 1')
        cls.cliente_retiro = cls.cliente('CLIENTE DE PRUEBA RETIRO')
        cls.cliente_flete = cls.cliente('CLIENTE DE PRUEBA FLETE')
        cls.cliente_sin = cls.cliente('CLIENTE DE PRUEBA SIN METODO')
        cls.pedido_envio, cls.entrega_envio = cls.venta(
            cls.cliente_envio, [(cls.cama, 2), (cls.mesa, 1)], metodo=cls.metodo_envio)
        cls.pedido_retiro, cls.entrega_retiro = cls.venta(cls.cliente_retiro, [(cls.mesa, 1)], metodo=cls.metodo_retiro)
        cls.pedido_flete, cls.entrega_flete = cls.venta(cls.cliente_flete, [(cls.cama, 2), (cls.flete, 1)])
        cls.pedido_sin, cls.entrega_sin = cls.venta(cls.cliente_sin, [(cls.zapatera, 1)])

    @classmethod
    def cliente(cls, nombre, telefono=False, calle=False):
        return cls.env['res.partner'].create({
            'name': nombre, 'phone': telefono, 'street': calle, 'city': 'La Chorrera' if calle else False})

    @classmethod
    def venta(cls, cliente, lineas, metodo=False):
        """Un pedido confirmado y su entrega."""
        pedido = cls.env['sale.order'].create({
            'partner_id': cliente.id,
            'carrier_id': metodo.id if metodo else False,
            'order_line': [Command.create({'product_id': producto.id, 'product_uom_qty': cantidad, 'price_unit': 50.0})
                           for producto, cantidad in lineas],
        })
        pedido.action_confirm()
        return pedido, pedido.picking_ids.filtered(lambda e: e.picking_type_code == 'outgoing')

    def tarjetas(self, usuario=None):
        return {t['id']: t for t in self.Bodega.with_user(usuario or self.bodeguero).pendientes()['entregas']}

    def marcas(self, entrega, cantidades):
        """``cantidades``: {producto: n}; lo que no se nombra, 0."""
        return [{'id': m.id, 'cantidad': cantidades.get(m.product_id, 0)} for m in entrega.move_ids]
