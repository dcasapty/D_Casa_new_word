"""Apartados de la tienda sin reclamar: vencen a los 7 días y el inventario vuelve a estar libre (lo pidió la dueña)."""
from datetime import datetime, timedelta
from unittest.mock import patch

from freezegun import freeze_time

from odoo import Command, fields
from odoo.addons.website_dcasa.models.sale_order import RESUMEN_DEL_AVISO
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tools.safe_eval import safe_eval

HOY = datetime(2026, 10, 9, 15, 0)


@tagged('post_install', '-at_install')
class TestApartadosDeLaTienda(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env.ref('website.default_website')
        cls.Orden = cls.env['sale.order']
        cls.cliente = cls.env['res.partner'].create({'name': 'Cliente de la tienda', 'phone': '+507 6000-0000',
                                                     'email': 'cliente.tienda@example.com'})
        cls.producto = cls.env['product.product'].create({
            'name': 'Cama de prueba (apartados)', 'type': 'consu', 'is_storable': True, 'list_price': 100.0,
            'taxes_id': [Command.clear()]})
        almacen = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1)
        cls.ubicacion = almacen.lot_stock_id
        cls.env['stock.quant']._update_available_quantity(cls.producto, cls.ubicacion, 5.0)
        cls.vendedora = new_test_user(
            cls.env, login='apartados_vendedora', name='Vendedora Apartados',
            groups='base.group_user,sales_team.group_sale_salesman_all_leads,stock.group_stock_user')

    def pedido(self, web=True, cantidad=2, vendedora=None):
        valores = {
            'partner_id': self.cliente.id, 'website_id': self.website.id if web else False,
            'order_line': [Command.create({'product_id': self.producto.id, 'product_uom_qty': cantidad})]}
        if vendedora:
            valores['user_id'] = vendedora.id
        return self.Orden.create(valores)

    def avisos(self, orden):
        return orden.activity_ids.filtered(lambda a: a.summary == RESUMEN_DEL_AVISO)

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

    # --- Apartados a mano (botón «Apartar») -------------------------------------------------------------------

    def test_el_boton_aparta_a_mano_con_los_mismos_dias(self):
        with freeze_time(HOY):
            orden = self.pedido(web=False)
            orden.action_quotation_sent()
            self.assertFalse(orden.dcasa_apartado_vence, 'Hecho a mano es una venta normal hasta que se aparta')
            orden.with_user(self.vendedora).action_dcasa_apartar()
            self.assertEqual(orden.dcasa_apartado_vence, fields.Date.to_date('2026-10-16'))

    def test_un_pedido_hecho_a_mano_sin_el_boton_no_vence_nunca(self):
        with freeze_time(HOY):
            orden = self.pedido(web=False)
            orden.with_user(self.vendedora).action_confirm()
        with self.despues(60):
            self.assertEqual(self.Orden._dcasa_cron_vencer_apartados(), 0)
        self.assertEqual(orden.state, 'sale')

    def test_el_boton_pide_enviar_o_confirmar_antes(self):
        orden = self.pedido(web=False)
        with self.assertRaises(UserError):
            orden.with_user(self.vendedora).action_dcasa_apartar()
        self.assertFalse(orden.dcasa_apartado_vence)

    def test_con_cero_dias_el_boton_explica_que_no_vence(self):
        self.env['ir.config_parameter'].sudo().set_param('website_dcasa.apartado_dias', '0')
        orden = self.pedido(web=False)
        orden.action_quotation_sent()
        with self.assertRaises(UserError):
            orden.with_user(self.vendedora).action_dcasa_apartar()

    def test_el_boton_no_cambia_una_fecha_que_ya_existe(self):
        with freeze_time(HOY):
            orden = self.pedido()
            orden.action_quotation_sent()
        with self.despues(3):
            orden.with_user(self.vendedora).action_dcasa_apartar()
        self.assertEqual(orden.dcasa_apartado_vence, fields.Date.to_date('2026-10-16'))

    def test_si_la_vendedora_confirma_un_apartado_a_mano_la_fecha_se_queda(self):
        """Lo contrario de un pedido de la web: la fecha la puso ella misma, confirmar no la borra."""
        with freeze_time(HOY):
            orden = self.pedido(web=False)
            orden.action_quotation_sent()
            orden.with_user(self.vendedora).action_dcasa_apartar()
            orden.with_user(self.vendedora).action_confirm()
            self.assertEqual(orden.state, 'sale')
            self.assertEqual(orden.dcasa_apartado_vence, fields.Date.to_date('2026-10-16'))
            self.assertEqual(self.reservado(), 2.0)
        with self.despues(7):
            self.assertEqual(self.Orden._dcasa_cron_vencer_apartados(), 0)
        with self.despues(8):
            self.assertEqual(self.Orden._dcasa_cron_vencer_apartados(), 1)
        self.assertEqual(orden.state, 'cancel')
        self.assertEqual(self.reservado(), 0.0, 'El inventario volvió a quedar libre')

    def test_la_vendedora_puede_borrar_la_fecha_de_un_apartado_a_mano(self):
        """Si el cliente llegó y la venta es firme, ella borra la fecha y nada se anula solo."""
        with freeze_time(HOY):
            orden = self.pedido(web=False)
            orden.with_user(self.vendedora).action_confirm()
            orden.with_user(self.vendedora).action_dcasa_apartar()
            orden.with_user(self.vendedora).dcasa_apartado_vence = False
        with self.despues(30):
            self.assertEqual(self.Orden._dcasa_cron_vencer_apartados(), 0)
        self.assertEqual(orden.state, 'sale')

    def test_dias_que_le_quedan(self):
        with freeze_time(HOY):
            orden = self.pedido()
            orden.action_quotation_sent()
            self.assertEqual(orden.dcasa_apartado_dias, 7)
            self.assertEqual(self.pedido().dcasa_apartado_dias, 0, 'Sin fecha no cuenta días')
        with self.despues(6):
            orden.invalidate_recordset(['dcasa_apartado_dias'])
            self.assertEqual(orden.dcasa_apartado_dias, 1)
        with self.despues(9):
            orden.invalidate_recordset(['dcasa_apartado_dias'])
            self.assertEqual(orden.dcasa_apartado_dias, -2)

    # --- La lista «Apartados por vencer» ----------------------------------------------------------------------

    def test_la_lista_trae_los_apartados_de_la_tienda_y_los_de_a_mano_y_nada_mas(self):
        with freeze_time(HOY):
            tienda = self.pedido()
            tienda.action_quotation_sent()
            a_mano = self.pedido(web=False)
            a_mano.action_quotation_sent()
            a_mano.with_user(self.vendedora).action_dcasa_apartar()
            venta_normal = self.pedido(web=False)
            venta_normal.action_quotation_sent()
            carrito = self.pedido()
            anulado = self.pedido()
            anulado.action_quotation_sent()
            anulado._action_cancel()
            accion = self.env.ref('website_dcasa.action_dcasa_apartados')
            encontrados = self.Orden.search(safe_eval(accion.domain))
            self.assertIn(tienda, encontrados)
            self.assertIn(a_mano, encontrados)
            self.assertNotIn(venta_normal, encontrados)
            self.assertNotIn(carrito, encontrados)
            self.assertNotIn(anulado, encontrados)

    def test_el_menu_cuelga_de_hoy_y_la_lista_y_el_boton_existen(self):
        menu = self.env.ref('website_dcasa.menu_dcasa_apartados')
        self.assertEqual(menu.parent_id, self.env.ref('dcasa_base.menu_dcasa_hoy'))
        accion = self.env.ref('website_dcasa.action_dcasa_apartados')
        vista = self.Orden.get_view(self.env.ref('website_dcasa.view_apartados_list').id, 'list')
        self.assertIn('dcasa_apartado_dias', vista['arch'])
        formulario = self.Orden.get_view(self.env.ref('sale.view_order_form').id, 'form')
        self.assertIn('action_dcasa_apartar', formulario['arch'])
        self.assertEqual(accion.res_model, 'sale.order')

    # --- Aviso a la vendedora (el aviso al cliente lo manda ella) ----------------------------------------------

    def test_la_vendedora_recibe_el_aviso_cuando_faltan_dos_dias(self):
        with freeze_time(HOY):
            orden = self.pedido(vendedora=self.vendedora)
            orden.action_quotation_sent()          # vence el 16
        with self.despues(4):                      # 13: faltan 3 días
            self.assertEqual(self.Orden._dcasa_avisar_apartados_por_vencer(), 0)
            self.assertFalse(self.avisos(orden))
        with self.despues(5):                      # 14: faltan 2 días
            self.Orden._dcasa_cron_vencer_apartados()
            aviso = self.avisos(orden)
            self.assertEqual(len(aviso), 1)
            self.assertEqual(aviso.user_id, self.vendedora)
            self.assertEqual(aviso.date_deadline, fields.Date.to_date('2026-10-16'))
            self.assertIn(orden.name, str(aviso.note))
            self.assertIn('+507 6000-0000', str(aviso.note), 'La nota trae el teléfono para avisarle')
        with self.despues(6):                      # 15: no se repite
            self.assertEqual(self.Orden._dcasa_avisar_apartados_por_vencer(), 0)
            self.assertEqual(len(self.avisos(orden)), 1)

    def test_si_ella_marca_el_aviso_como_hecho_no_vuelve_a_salir(self):
        with freeze_time(HOY):
            orden = self.pedido(vendedora=self.vendedora)
            orden.action_quotation_sent()
        with self.despues(5):
            self.Orden._dcasa_avisar_apartados_por_vencer()
            self.avisos(orden).action_done()
            self.assertFalse(self.avisos(orden))
        with self.despues(6):
            self.assertEqual(self.Orden._dcasa_avisar_apartados_por_vencer(), 0)
            self.assertFalse(self.avisos(orden))

    def test_si_mueve_la_fecha_el_aviso_viejo_se_quita_y_llega_otro_a_su_hora(self):
        with freeze_time(HOY):
            orden = self.pedido(vendedora=self.vendedora)
            orden.action_quotation_sent()
        with self.despues(5):
            self.Orden._dcasa_avisar_apartados_por_vencer()
            self.assertEqual(len(self.avisos(orden)), 1)
            orden.dcasa_apartado_vence = fields.Date.to_date('2026-10-30')
        with self.despues(6):
            self.assertEqual(self.Orden._dcasa_avisar_apartados_por_vencer(), 0)
            self.assertFalse(self.avisos(orden), 'El aviso de la fecha vieja ya no vale')
        with self.despues(19):                     # 28: faltan 2 días para el 30
            self.assertEqual(self.Orden._dcasa_avisar_apartados_por_vencer(), 1)
            self.assertEqual(self.avisos(orden).date_deadline, fields.Date.to_date('2026-10-30'))

    def test_un_pedido_anulado_o_reclamado_pierde_el_aviso(self):
        with freeze_time(HOY):
            anulado = self.pedido(vendedora=self.vendedora)
            anulado.action_quotation_sent()
            cobrado = self.pedido(vendedora=self.vendedora, cantidad=1)
            cobrado.action_confirm()
        with self.despues(5):
            self.assertEqual(self.Orden._dcasa_avisar_apartados_por_vencer(), 2)
            anulado._action_cancel()
            cobrado._create_invoices().action_post()     # reclamado: ya hay factura publicada
            self.Orden._dcasa_avisar_apartados_por_vencer()
            self.assertFalse(self.avisos(anulado))
            self.assertFalse(self.avisos(cobrado))
            self.assertFalse(cobrado.dcasa_apartado_vence, 'Lo reclamado deja de vigilarse y sale de la lista')
            encontrados = self.Orden.search(safe_eval(self.env.ref('website_dcasa.action_dcasa_apartados').domain))
            self.assertNotIn(cobrado, encontrados)

    def test_un_pedido_ya_reclamado_no_recibe_aviso(self):
        with freeze_time(HOY):
            orden = self.pedido(vendedora=self.vendedora)
            orden.action_confirm()
            orden._create_invoices().action_post()
        with self.despues(5):
            self.assertEqual(self.Orden._dcasa_avisar_apartados_por_vencer(), 0)

    def test_sin_vendedora_no_hay_aviso_pero_el_pedido_sigue_en_la_lista(self):
        with freeze_time(HOY):
            orden = self.pedido()
            orden.action_quotation_sent()
            orden.user_id = False
        with self.despues(5):
            self.assertEqual(self.Orden._dcasa_avisar_apartados_por_vencer(), 0)
            self.assertFalse(orden.activity_ids)
            encontrados = self.Orden.search(safe_eval(self.env.ref('website_dcasa.action_dcasa_apartados').domain))
            self.assertIn(orden, encontrados)

    def test_un_fallo_en_los_avisos_no_impide_anular_los_vencidos(self):
        with freeze_time(HOY):
            orden = self.pedido(vendedora=self.vendedora)
            orden.action_quotation_sent()
        with self.despues(8), self.assertLogs('odoo.addons.website_dcasa.models.sale_order', level='ERROR'):
            with patch.object(type(orden), '_dcasa_avisar_apartados_por_vencer', side_effect=ValueError('falla')):
                self.assertEqual(self.Orden._dcasa_cron_vencer_apartados(), 1)
        self.assertEqual(orden.state, 'cancel')
