"""Del CRM y de Contactos al chat del cliente, y el CRM sin el filtro «Mi flujo» (pedido de la dueña, 2026-11-03)."""
import json
from datetime import timedelta

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import JuanCase
from .test_panel_interfaz import PanelUiCase


@tagged('post_install', '-at_install')
class TestAbrirElChat(JuanCase):

    def setUp(self):
        super().setUp()
        self.conv = self.conversacion(nombre='Cliente del chat', id_externo='50765550001')
        self.cliente = self.conv.partner_id
        self.Lead = self.env['crm.lead']

    def test_el_flujo_del_crm_abre_sin_el_filtro_mi_flujo(self):
        accion = self.env['crm.team'].with_user(self.vendedora).action_your_pipeline()
        self.assertNotIn('search_default_assigned_to_me', accion['context'])
        self.assertNotIn('search_default_assigned_to_me', self.env.ref('crm.crm_lead_action_pipeline').context)
        self.assertEqual(accion['context'].get('default_type'), 'opportunity')
        buscador = self.env['crm.lead'].get_view(self.env.ref('crm.view_crm_case_opportunities_filter').id,
                                                  'search')['arch']
        self.assertIn('name="assigned_to_me"', buscador, 'El filtro sigue en el buscador para quien lo quiera')

    def test_la_oportunidad_con_conversacion_abre_su_chat(self):
        lead = self.Lead.create({'name': 'Quiere un sofá', 'type': 'opportunity', 'partner_id': self.cliente.id})
        self.conv.sudo().oportunidad_id = lead
        lead = lead.with_user(self.vendedora)
        self.assertEqual(lead.dcasa_chat_id, self.conv)
        accion = lead.action_dcasa_abrir_chat()
        self.assertEqual((accion['type'], accion['tag']), ('ir.actions.client', 'dcasa_conversaciones'))
        self.assertEqual(accion['params'], {'conversacion_id': self.conv.id})

    def test_si_la_oportunidad_no_tiene_conversacion_usa_la_mas_reciente_del_cliente(self):
        otra = self.conversacion(nombre='Cliente del chat', id_externo='777555', canal='telegram')
        otra.sudo().partner_id = self.cliente
        otra.sudo().ultima_actividad = self.conv.ultima_actividad + timedelta(hours=1)
        lead = self.Lead.create({'name': 'Sin chat propio', 'type': 'opportunity', 'partner_id': self.cliente.id})
        self.assertEqual(lead.with_user(self.vendedora).dcasa_chat_id, otra)

    def test_sin_conversaciones_no_hay_boton_y_el_metodo_lo_dice(self):
        nadie = self.Partner.create({'name': 'Sin chats'})
        lead = self.Lead.create({'name': 'Llamó por teléfono', 'type': 'opportunity', 'partner_id': nadie.id})
        self.assertFalse(lead.dcasa_chat_id)
        with self.assertRaisesRegex(UserError, 'todavía no tiene conversaciones'):
            lead.action_dcasa_abrir_chat()
        with self.assertRaisesRegex(UserError, 'todavía no tiene conversaciones'):
            nadie.with_user(self.vendedora).action_dcasa_ver_conversaciones()

    def test_desde_contactos_lleva_al_chat_del_cliente(self):
        accion = self.cliente.with_user(self.vendedora).action_dcasa_ver_conversaciones()
        self.assertEqual((accion['tag'], accion['params']), ('dcasa_conversaciones', {'conversacion_id': self.conv.id}))

    def test_las_vistas_tienen_el_boton(self):
        formulario = self.env['crm.lead'].get_view(view_type='form')['arch']
        kanban = self.env['crm.lead'].get_view(self.env.ref('crm.crm_case_kanban_view_leads').id, 'kanban')['arch']
        for arch in (formulario, kanban):
            self.assertIn('action_dcasa_abrir_chat', arch)


@tagged('post_install', '-at_install')
class TestAbrirElChatEnElNavegador(PanelUiCase):

    def test_abrir_el_chat_desde_contactos_deja_la_conversacion_a_la_vista(self):
        self.datos_de_ejemplo()
        accion = self.marta.partner_id.with_user(self.vendedora).action_dcasa_ver_conversaciones()
        self.navegador(f"""
(async () => {{
    await esperar(() => document.querySelectorAll(".o_dcj_fila").length >= 3, "la lista");
    await odoo.__WOWL_DEBUG__.root.env.services.action.doAction({json.dumps(accion)});
    await esperar(() => (document.querySelector(".o_dcj_hilo_cabecera h2") || {{}}).textContent === "Marta Ríos",
                  "el chat de Marta a la vista");
    console.log("test successful");
}})().catch((e) => console.error(e.message || e));
""")
