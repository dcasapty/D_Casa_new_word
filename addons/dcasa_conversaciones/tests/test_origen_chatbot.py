"""El origen «Chatbot» (pedido de la dueña, 2026-11-03: «las facturas creadas por Juan deberían decir, en el Inicio o en
todo lado, que son por el chatbot»): la cotización que arma Juan, su factura y la fila del Inicio."""
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
