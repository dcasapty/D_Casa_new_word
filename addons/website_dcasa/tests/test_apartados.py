"""Apartados de la tienda sin reclamar: vencen a los 7 días y el inventario vuelve a estar libre (lo pidió la dueña)."""
from datetime import datetime, timedelta
from unittest.mock import patch

from freezegun import freeze_time

from odoo import Command, fields
from odoo.tests import TransactionCase, new_test_user, tagged

HOY = datetime(2026, 10, 9, 15, 0)


@tagged('post_install', '-at_install')
class TestApartadosDeLaTienda(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env.ref('website.default_website')
        cls.Orden = cls.env['sale.order']
        cls.cliente = cls.env['res.partner'].create({'name': 'Cliente de la tienda', 'phone': '+507 6000-0000'})
        cls.producto = cls.env['product.product'].create({
            'name': 'Cama de prueba (apartados)', 'type': 'consu', 'is_storable': True, 'list_price': 100.0,
            'taxes_id': [Command.clear()]})
        almacen = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1)
        cls.ubicacion = almacen.lot_stock_id
        cls.env['stock.quant']._update_available_quantity(cls.producto, cls.ubicacion, 5.0)
        cls.vendedora = new_test_user(
            cls.env, login='apartados_vendedora', name='Vendedora Apartados',
            groups='base.group_user,sales_team.group_sale_salesman_all_leads,stock.group_stock_user')

    def pedido(self, web=True, cantidad=2):
        return self.Orden.create({
            'partner_id': self.cliente.id, 'website_id': self.website.id if web else False,
            'order_line': [Command.create({'product_id': self.producto.id, 'product_uom_qty': cantidad})]})

    def reservado(self):
        quant = self.env['stock.quant'].search([
            ('product_id', '=', self.producto.id), ('location_id', '=', self.ubicacion.id)])
        return sum(quant.mapped('reserved_quantity'))

    def despues(self, dias):
        return freeze_time(HOY + timedelta(days=dias))

    # --- Se marca la fecha ----------------------------------------------------------------------------------

    def test_pago_al_recibir_confirma_sola_reserva_y_recibe_fecha(self):
        """La tienda confirma sola el pedido (superusuario/público): reserva inventario y empieza a contar."""
        with freeze_time(HOY):
            orden = self.pedido()
            orden.action_confirm()
            self.assertEqual(orden.state, 'sale')
            self.assertEqual(orden.dcasa_apartado_vence, fields.Date.to_date('2026-10-16'))
            self.assertEqual(self.reservado(), 2.0, 'El inventario queda apartado')

    def test_transferencia_o_yappy_deja_cotizacion_enviada_con_fecha(self):
        with freeze_time(HOY):
            orden = self.pedido()
            orden.action_quotation_sent()
            self.assertEqual(orden.state, 'sent')
            self.assertEqual(orden.dcasa_apartado_vence, fields.Date.to_date('2026-10-16'))
            self.assertEqual(self.reservado(), 0.0, 'Una cotización no reserva inventario')

    def test_un_pedido_que_no_es_de_la_web_no_recibe_fecha(self):
        with freeze_time(HOY):
            orden = self.pedido(web=False)
            orden.action_confirm()
            self.assertFalse(orden.dcasa_apartado_vence)

    def test_los_dias_son_un_ajuste_y_cero_lo_apaga(self):
        parametros = self.env['ir.config_parameter'].sudo()
        with freeze_time(HOY):
            parametros.set_param('website_dcasa.apartado_dias', '3')
            orden = self.pedido()
            orden.action_quotation_sent()
            self.assertEqual(orden.dcasa_apartado_vence, fields.Date.to_date('2026-10-12'))
            parametros.set_param('website_dcasa.apartado_dias', '0')
            otra = self.pedido()
            otra.action_quotation_sent()
            self.assertFalse(otra.dcasa_apartado_vence, '0 = apagado')
            parametros.set_param('website_dcasa.apartado_dias', 'mucho')
            self.assertEqual(self.Orden._dcasa_dias_de_apartado(), 7, 'Un valor roto vuelve al estándar')

    def test_si_la_vendedora_confirma_es_decision_suya_y_no_se_anula_sola(self):
        with freeze_time(HOY):
            orden = self.pedido()
            orden.action_quotation_sent()
            self.assertTrue(orden.dcasa_apartado_vence)
            orden.with_user(self.vendedora).action_confirm()
            self.assertFalse(orden.dcasa_apartado_vence)
        with self.despues(30):
            self.assertEqual(self.Orden._dcasa_cron_vencer_apartados(), 0)
        self.assertEqual(orden.state, 'sale')

    # --- Vence ----------------------------------------------------------------------------------------------

    def test_vencido_se_anula_la_entrega_y_el_inventario_queda_libre(self):
        with freeze_time(HOY):
            orden = self.pedido()
            orden.action_confirm()
            entrega = orden.picking_ids
            self.assertEqual(self.reservado(), 2.0)
        with self.despues(8):
            self.assertEqual(self.Orden._dcasa_cron_vencer_apartados(), 1)
        self.assertEqual(orden.state, 'cancel')
        self.assertEqual(entrega.state, 'cancel')
        self.assertEqual(self.reservado(), 0.0, 'El inventario volvió a quedar libre')
        notas = orden.message_ids.mapped('body')
        self.assertTrue(any('Apartado vencido' in str(n) for n in notas))

    def test_cotizacion_de_la_web_vencida_tambien_se_anula(self):
        with freeze_time(HOY):
            orden = self.pedido()
            orden.action_quotation_sent()
        with self.despues(8):
            self.assertEqual(self.Orden._dcasa_cron_vencer_apartados(), 1)
        self.assertEqual(orden.state, 'cancel')

    def test_el_ultimo_dia_todavia_vale(self):
        with freeze_time(HOY):
            orden = self.pedido()
            orden.action_confirm()
        with self.despues(7):          # vence el día 7: ese día todavía se puede reclamar
            self.assertEqual(self.Orden._dcasa_cron_vencer_apartados(), 0)
        self.assertEqual(orden.state, 'sale')
        with self.despues(8):
            self.assertEqual(self.Orden._dcasa_cron_vencer_apartados(), 1)

    def test_si_la_vendedora_extiende_la_fecha_no_se_anula(self):
        with freeze_time(HOY):
            orden = self.pedido()
            orden.action_confirm()
            orden.dcasa_apartado_vence = fields.Date.to_date('2026-10-30')
        with self.despues(8):
            self.assertEqual(self.Orden._dcasa_cron_vencer_apartados(), 0)
        self.assertEqual(orden.state, 'sale')
        with self.despues(22):
            self.assertEqual(self.Orden._dcasa_cron_vencer_apartados(), 1)

    def test_el_carrito_sin_terminar_no_se_toca(self):
        with freeze_time(HOY):
            carrito = self.pedido()      # borrador: nadie lo apartó
        with self.despues(40):
            self.assertEqual(self.Orden._dcasa_cron_vencer_apartados(), 0)
        self.assertEqual(carrito.state, 'draft')

    # --- Lo que ya se reclamó nunca se anula solo ---------------------------------------------------------

    def test_con_factura_publicada_no_se_anula(self):
        with freeze_time(HOY):
            orden = self.pedido()
            orden.action_confirm()
            orden._create_invoices().action_post()
        with self.despues(30):
            self.assertEqual(self.Orden._dcasa_cron_vencer_apartados(), 0)
        self.assertEqual(orden.state, 'sale')
        self.assertFalse(orden.dcasa_apartado_vence, 'Deja de vigilarse')

    def test_con_la_entrega_hecha_no_se_anula(self):
        with freeze_time(HOY):
            orden = self.pedido()
            orden.action_confirm()
            entrega = orden.picking_ids
            entrega.move_ids.quantity = 2.0
            entrega.with_context(skip_backorder=True, skip_sms=True).button_validate()
            self.assertEqual(entrega.state, 'done')
        with self.despues(30):
            self.assertEqual(self.Orden._dcasa_cron_vencer_apartados(), 0)
        self.assertEqual(orden.state, 'sale')

    def test_con_un_pago_hecho_no_se_anula(self):
        with freeze_time(HOY):
            orden = self.pedido()
            orden.action_quotation_sent()
            proveedor = self.env['payment.provider'].search([('code', '=', 'custom')], limit=1)
            metodo = proveedor.payment_method_ids[:1]
            tx = self.env['payment.transaction'].create({
                'provider_id': proveedor.id, 'payment_method_id': metodo.id, 'amount': orden.amount_total,
                'currency_id': orden.currency_id.id, 'partner_id': self.cliente.id, 'reference': 'TEST-APARTADO-1',
                'sale_order_ids': [Command.set(orden.ids)]})
            tx._set_done()
        with self.despues(30):
            self.assertEqual(self.Orden._dcasa_cron_vencer_apartados(), 0)
        self.assertEqual(orden.state, 'sent')

    def test_un_fallo_en_un_pedido_no_detiene_a_los_demas(self):
        with freeze_time(HOY):
            malo, bueno = self.pedido(), self.pedido(cantidad=1)
            malo.action_quotation_sent()
            bueno.action_quotation_sent()
        original = type(malo)._action_cancel

        def cancelar(registros):
            if registros == malo:
                raise ValueError('falla de prueba')
            return original(registros)

        with self.despues(8), self.assertLogs('odoo.addons.website_dcasa.models.sale_order', level='ERROR'):
            with patch.object(type(malo), '_action_cancel', cancelar):
                self.assertEqual(self.Orden._dcasa_cron_vencer_apartados(), 1)
        self.assertEqual(malo.state, 'sent')
        self.assertEqual(bueno.state, 'cancel')

    def test_hay_una_tarea_programada_cada_noche(self):
        cron = self.env.ref('website_dcasa.ir_cron_dcasa_vencer_apartados')
        self.assertTrue(cron.active)
        self.assertEqual((cron.interval_number, cron.interval_type), (1, 'days'))
