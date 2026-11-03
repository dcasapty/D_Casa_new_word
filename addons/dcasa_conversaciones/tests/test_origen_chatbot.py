"""El origen «Chatbot» (pedido de la dueña, 2026-11-03: «las facturas creadas por Juan deberían decir, en el Inicio o en
todo lado, que son por el chatbot»): la cotización que arma Juan, su factura y la fila del Inicio."""
from datetime import timedelta

from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from ..models.sale_origen import hoy_en_panama
from .test_cotizacion_automatica import CotizarCase


@tagged('post_install', '-at_install')
class TestOrigenChatbot(CotizarCase):

    def test_la_cotizacion_de_juan_y_su_factura_son_del_chatbot(self):
        self.cotizar({'codigo': 'ZZ-CAMA'})
        (orden,) = self.ordenes()
        self.assertEqual(orden.dcasa_origen, 'chatbot')
        # Una vendedora la toma, la cambia y la confirma: sigue siendo del chatbot.
        orden.write({'user_id': self.env.user.id})
        orden.action_confirm()
        self.assertEqual(orden.dcasa_origen, 'chatbot')
        factura = orden._create_invoices()
        factura.action_post()
        self.assertEqual(factura.dcasa_origen, 'chatbot')

    def test_la_que_crea_una_vendedora_desde_el_chat_es_de_la_vendedora(self):
        orden = self.env['sale.order'].create({'partner_id': self.conv.partner_id.id})
        self.assertEqual(orden.dcasa_origen, 'vendedora')

    def test_al_actualizar_se_marcan_las_de_antes(self):
        """Las cotizaciones que Juan armó antes de que existiera el origen quedan «Chatbot» al actualizar el módulo."""
        self.cotizar({'codigo': 'ZZ-CAMA'})
        (orden,) = self.ordenes()
        self.env.cr.execute("UPDATE sale_order SET dcasa_origen = 'vendedora' WHERE id = %s", [orden.id])
        orden.invalidate_recordset(['dcasa_origen'])
        self.assertEqual(orden.dcasa_origen, 'vendedora')
        self.env['sale.order']._dcasa_marcar_origen_chatbot()
        orden.invalidate_recordset(['dcasa_origen'])
        self.assertEqual(orden.dcasa_origen, 'chatbot')

    def test_el_inicio_pone_la_cotizacion_del_chatbot_en_su_panel_y_dice_chatbot(self):
        self.cotizar({'codigo': 'ZZ-CAMA'})
        (orden,) = self.ordenes()
        orden.date_order = '2020-01-01 12:00:00'   # la más antigua: sale primero en la lista del Inicio
        hoy = self.env['dcasa.tablero']._ahora_en_panama().date()
        filas = self.env['dcasa.tablero']._lista_de_cotizaciones(hoy, en_linea=True)['filas']
        fila = next(f for f in filas if f['id'] == orden.id)
        self.assertEqual(fila['origen'], 'Chatbot')
        tienda = self.env['dcasa.tablero']._lista_de_cotizaciones(hoy)['filas']
        self.assertNotIn(orden.id, [f['id'] for f in tienda], 'Va en su propio panel, no con las de la tienda')


@tagged('post_install', '-at_install')
class TestCotizacionesQueVencen(CotizarCase):
    """Decisión de la dueña (2026-11-03): las cotizaciones del chatbot y de la web que nadie confirmó se cancelan
    solas a los 3 días (Gerencia lo cambia en Ajustes de Juan). No se borran y las de las vendedoras no se tocan.
    Manda su «válida hasta» (lo que dice el PDF); la revisión adversarial pidió también: reabrir le da sus días otra
    vez, un carrito tocado hace poco no se cancela, un apartado de la web tampoco."""

    def vencer(self, orden, dias=1, tocada_hace_horas=24):
        """Su «válida hasta» pasó hace ``dias`` días y nadie la tocó en ``tocada_hace_horas`` horas."""
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE sale_order SET validity_date = %s, write_date = now() at time zone 'UTC' - %s * interval '1 hour' "
            "WHERE id = %s", [hoy_en_panama() - timedelta(days=dias), tocada_hace_horas, orden.id])
        orden.invalidate_recordset(['validity_date', 'write_date'])

    @staticmethod
    def notas(orden):
        return ' '.join(str(m.body or '') for m in orden.message_ids)

    def de_juan(self, codigo='ZZ-CAMA'):
        self.cotizar({'codigo': codigo})
        return self.ordenes()[-1:]

    def cron(self):
        return self.env['sale.order']._cron_dcasa_cancelar_vencidas()

    def web(self):
        return self.env['sale.order'].create({
            'partner_id': self.conv.partner_id.id, 'website_id': self.env['website'].search([], limit=1).id,
            'order_line': [(0, 0, {'product_id': self.cama.product_variant_id.id, 'product_uom_qty': 1})]})

    def test_viene_en_3_dias_y_la_cotizacion_dice_valida_hasta(self):
        self.assertEqual(self.ajustes.cotizacion_dias_abierta, 3)
        self.assertEqual(self.de_juan().validity_date, hoy_en_panama() + timedelta(days=3))
        self.assertEqual(self.web().validity_date, hoy_en_panama() + timedelta(days=3))

    def test_pasada_su_fecha_se_cancela_sola_con_su_nota_y_no_se_borra(self):
        vieja = self.de_juan()
        self.vencer(vieja)
        nueva = self.de_juan('ZZ-SOFA')
        self.assertEqual(self.cron(), 1)
        self.assertEqual(vieja.state, 'cancel')
        self.assertIn(nueva.state, ('draft', 'sent'), 'la nueva sigue en su plazo')
        self.assertTrue(vieja.exists(), 'se cancela, nunca se borra')
        self.assertIn('Se canceló sola', self.notas(vieja))
        self.assertIn('del chatbot', self.notas(vieja))

    def test_si_una_vendedora_mueve_la_fecha_manda_la_fecha(self):
        orden = self.de_juan()
        self.vencer(orden)
        orden.validity_date = hoy_en_panama() + timedelta(days=5)
        self.vencer(orden, dias=-5)       # la fecha nueva, sin tocar en 24 h
        self.cron()
        self.assertIn(orden.state, ('draft', 'sent'))

    def test_reabrirla_le_da_sus_dias_otra_vez(self):
        orden = self.de_juan()
        self.vencer(orden)
        self.cron()
        self.assertEqual(orden.state, 'cancel')
        orden.action_draft()
        self.assertEqual(orden.validity_date, hoy_en_panama() + timedelta(days=3))
        self.cron()
        self.assertEqual(orden.state, 'draft', 'no la vuelve a cancelar en la siguiente corrida')

    def test_la_que_alguien_toco_hace_poco_no_se_cancela(self):
        """Un carrito de la web que el cliente está llenando ahora mismo."""
        carrito = self.web()
        self.vencer(carrito, tocada_hace_horas=2)
        self.cron()
        self.assertEqual(carrito.state, 'draft')

    def test_la_de_una_vendedora_no_se_toca(self):
        orden = self.env['sale.order'].with_user(self.vendedora).create({
            'partner_id': self.conv.partner_id.id,
            'order_line': [(0, 0, {'product_id': self.cama.product_variant_id.id, 'product_uom_qty': 1})]})
        self.assertEqual(orden.dcasa_origen, 'vendedora')
        self.vencer(orden, dias=10)
        self.cron()
        self.assertEqual(orden.state, 'draft')

    def test_una_de_la_web_vencida_se_cancela_salvo_con_un_pago_en_curso(self):
        web = self.web()
        proveedor = self.env['payment.provider'].search([('payment_method_ids', '!=', False)], limit=1)
        if not proveedor:
            self.skipTest('No hay un proveedor de pago para crear la transacción.')
        tx = self.env['payment.transaction'].create({
            'provider_id': proveedor.id, 'payment_method_id': proveedor.payment_method_ids[:1].id,
            'amount': web.amount_total, 'currency_id': web.currency_id.id, 'partner_id': web.partner_id.id,
            'reference': 'TEST-VENCE-WEB-1', 'sale_order_ids': [Command.set(web.ids)]})
        tx._set_pending()
        self.vencer(web, dias=2)
        self.cron()
        self.assertEqual(web.state, 'draft', 'con una transferencia por confirmar no se cancela')
        tx._set_canceled()
        self.vencer(web, dias=2)
        self.cron()
        self.assertEqual(web.state, 'cancel')
        self.assertIn('de la web', self.notas(web))

    def test_un_apartado_de_la_web_sigue_su_propio_vencimiento(self):
        web = self.web()
        if 'dcasa_apartado_vence' not in web._fields:
            self.skipTest('Sin website_dcasa no hay apartados.')
        web.dcasa_apartado_vence = hoy_en_panama() + timedelta(days=7)
        self.vencer(web, dias=2)
        self.cron()
        self.assertEqual(web.state, 'draft')

    def test_con_0_dias_nunca_se_cancelan_y_mas_de_60_no_se_acepta(self):
        orden = self.de_juan()
        self.vencer(orden, dias=30)
        self.ajustes.cotizacion_dias_abierta = 0
        self.assertEqual(self.cron(), 0)
        self.assertIn(orden.state, ('draft', 'sent'))
        with self.assertRaises(ValidationError):
            self.ajustes.cotizacion_dias_abierta = 61
