"""El origen «Chatbot» (pedido de la dueña, 2026-11-03: «las facturas creadas por Juan deberían decir, en el Inicio o en
todo lado, que son por el chatbot»): la cotización que arma Juan, su factura y la fila del Inicio."""
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged

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

    def test_el_inicio_dice_chatbot_en_la_cotizacion_abierta(self):
        self.cotizar({'codigo': 'ZZ-CAMA'})
        (orden,) = self.ordenes()
        orden.date_order = '2020-01-01 12:00:00'   # la más antigua: sale primero en la lista del Inicio
        hoy = self.env['dcasa.tablero']._ahora_en_panama().date()
        filas = self.env['dcasa.tablero']._lista_de_cotizaciones(hoy)['filas']
        fila = next(f for f in filas if f['id'] == orden.id)
        self.assertEqual(fila['origen'], 'Chatbot')


@tagged('post_install', '-at_install')
class TestCotizacionesQueVencen(CotizarCase):
    """Decisión de la dueña (2026-11-03): las cotizaciones del chatbot y de la web que nadie confirmó se cancelan
    solas a los 3 días (Gerencia lo cambia en Ajustes de Juan). No se borran y las de las vendedoras no se tocan."""

    def envejecer(self, orden, dias):
        self.env.cr.execute("UPDATE sale_order SET create_date = now() at time zone 'UTC' - %s * interval '1 day' "
                            "WHERE id = %s", [dias, orden.id])
        orden.invalidate_recordset(['create_date'])

    @staticmethod
    def notas(orden):
        return ' '.join(str(m.body or '') for m in orden.message_ids)

    def de_juan(self):
        self.cotizar({'codigo': 'ZZ-CAMA'})
        return self.ordenes()[-1:]

    def test_viene_en_3_dias_y_la_cotizacion_dice_valida_hasta(self):
        self.assertEqual(self.ajustes.cotizacion_dias_abierta, 3)
        orden = self.de_juan()
        self.assertEqual(orden.validity_date, fields.Date.context_today(orden) + timedelta(days=3))

    def test_pasados_los_dias_se_cancela_sola_con_su_nota_y_no_se_borra(self):
        vieja = self.de_juan()
        self.envejecer(vieja, 4)
        self.cotizar({'codigo': 'ZZ-SOFA'})
        nueva = self.ordenes()[-1:]
        self.envejecer(nueva, 2)
        self.assertEqual(self.env['sale.order']._cron_dcasa_cancelar_vencidas(), 1)
        self.assertEqual(vieja.state, 'cancel')
        self.assertIn(nueva.state, ('draft', 'sent'), 'la de hace 2 días sigue abierta')
        self.assertTrue(vieja.exists(), 'se cancela, nunca se borra')
        self.assertIn('Se canceló sola', self.notas(vieja))
        self.assertIn('del chatbot', self.notas(vieja))

    def test_la_de_una_vendedora_no_se_toca(self):
        orden = self.env['sale.order'].create({'partner_id': self.conv.partner_id.id, 'order_line': [
            (0, 0, {'product_id': self.cama.product_variant_id.id, 'product_uom_qty': 1})]})
        self.envejecer(orden, 10)
        self.env['sale.order']._cron_dcasa_cancelar_vencidas()
        self.assertEqual(orden.state, 'draft')

    def test_una_de_la_web_vencida_se_cancela_salvo_con_un_pago_en_curso(self):
        web = self.env['sale.order'].create({
            'partner_id': self.conv.partner_id.id, 'website_id': self.env['website'].search([], limit=1).id,
            'order_line': [(0, 0, {'product_id': self.cama.product_variant_id.id, 'product_uom_qty': 1})]})
        self.envejecer(web, 5)
        clase = type(self.env['sale.order'])
        with patch.object(clase, '_dcasa_pago_en_curso', return_value=True):
            self.env['sale.order']._cron_dcasa_cancelar_vencidas()
        self.assertEqual(web.state, 'draft', 'con una transferencia por confirmar no se cancela')
        self.env['sale.order']._cron_dcasa_cancelar_vencidas()
        self.assertEqual(web.state, 'cancel')
        self.assertIn('de la web', self.notas(web))

    def test_con_0_dias_nunca_se_cancelan_y_mas_de_60_no_se_acepta(self):
        orden = self.de_juan()
        self.envejecer(orden, 30)
        self.ajustes.cotizacion_dias_abierta = 0
        self.assertEqual(self.env['sale.order']._cron_dcasa_cancelar_vencidas(), 0)
        self.assertIn(orden.state, ('draft', 'sent'))
        with self.assertRaises(ValidationError):
            self.ajustes.cotizacion_dias_abierta = 61
