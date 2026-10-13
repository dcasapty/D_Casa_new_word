"""Ola 2 · «Ana está viendo» / «Ana está escribiendo…»: dos personas no le contestan a la vez al mismo cliente."""
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.service.model import call_kw
from odoo.tests import new_test_user, tagged

from .common import JuanCase


@tagged('post_install', '-at_install')
class TestPresencia(JuanCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.beto = new_test_user(cls.env, login='juan_beto', name='Beto Vendedor',
                                 groups='base.group_user,sales_team.group_sale_salesman')

    def setUp(self):
        super().setUp()
        self.conv = self.conversacion(nombre='Karen', id_externo='50761000001')
        self.otra = self.conversacion(nombre='Luis', id_externo='50761000002')
        self.ana = self.Conversacion.with_user(self.vendedora)
        self.beto_panel = self.Conversacion.with_user(self.beto)
        self.avisos = []
        parche = patch.object(type(self.env['res.users']), '_bus_send',
                              lambda usuario, canal, carga: self.avisos.append((usuario.id, canal, carga)))
        parche.start()
        self.addCleanup(parche.stop)

    def test_se_ve_quien_tiene_abierta_la_conversacion_y_uno_mismo_no_se_ve(self):
        self.assertEqual(self.ana.presencia(self.conv.id), {'presencia': {}})
        mapa = self.beto_panel.presencia(self.conv.id)['presencia']
        self.assertEqual(mapa, {self.conv.id: [{'usuario_id': self.vendedora.id, 'escribiendo': False}]})
        # Ana ve a Beto en el siguiente pulso; a sí misma nunca.
        self.assertEqual(self.ana.presencia(self.conv.id)['presencia'],
                         {self.conv.id: [{'usuario_id': self.beto.id, 'escribiendo': False}]})

    def test_escribiendo_dura_pocos_segundos(self):
        self.ana.presencia(self.conv.id, True)
        visto = self.beto_panel.presencia(self.conv.id)['presencia'][self.conv.id]
        self.assertTrue(visto[0]['escribiendo'])
        with patch.object(fields.Datetime, 'now', return_value=fields.Datetime.now() + timedelta(seconds=9)):
            visto = self.beto_panel.presencia(self.conv.id)['presencia'][self.conv.id]
        self.assertFalse(visto[0]['escribiendo'], 'Sin otro aviso al teclear, deja de decir escribiendo')

    def test_quien_dejo_de_dar_pulsos_desaparece(self):
        self.ana.presencia(self.conv.id)
        with patch.object(fields.Datetime, 'now', return_value=fields.Datetime.now() + timedelta(seconds=60)):
            self.assertEqual(self.beto_panel.presencia(self.conv.id)['presencia'], {})

    def test_cambiar_de_conversacion_o_cerrar_la_pantalla(self):
        self.ana.presencia(self.conv.id)
        self.ana.presencia(self.otra.id)
        mapa = self.beto_panel.presencia(None)['presencia']
        self.assertEqual(list(mapa), [self.otra.id])
        self.ana.presencia(None)   # tiene la pantalla abierta pero ninguna conversación
        self.assertEqual(self.beto_panel.presencia(None)['presencia'], {})

    def test_cada_pulso_avisa_a_las_demas_pantallas_solo_con_ids(self):
        self.ana.presencia(self.conv.id)
        self.ana.presencia(self.otra.id, True)
        ultimos = [(u, c) for u, canal, c in self.avisos if canal == 'dcasa_conversaciones/evento']
        self.assertTrue(ultimos)
        self.assertNotIn(self.vendedora.id, [u for u, _c in ultimos], 'No se avisa a quien dio el pulso')
        _usuario, carga = ultimos[-1]
        self.assertEqual(carga, {'evento': 'presencia', 'usuario_id': self.vendedora.id,
                                 'conversacion_id': self.otra.id, 'anterior': self.conv.id, 'escribiendo': True})
        for _u, c in ultimos:
            self.assertFalse({'texto', 'nombre'} & set(c), 'Por el bus viajan solo ids')

    def test_una_fila_por_persona(self):
        for _ in range(3):
            self.ana.presencia(self.conv.id)
        self.assertEqual(self.env['dcasa.presencia'].sudo().search_count([('usuario_id', '=', self.vendedora.id)]), 1)

    def test_valida_lo_que_recibe(self):
        for malo in (-1, 'x', 99999999):
            with self.subTest(malo=malo), self.assertRaises(UserError):
                self.ana.presencia(malo)
        with self.assertRaises(UserError):
            self.ana.presencia(self.conv.id, 'si')

    def test_solo_el_equipo_de_ventas(self):
        for usuario in (self.interno, self.portal):
            with self.assertRaises(AccessError):
                call_kw(self.env(user=usuario)['dcasa.conversacion'], 'presencia', [self.conv.id, False], {})

    def test_el_mantenimiento_borra_lo_de_hace_mas_de_un_dia(self):
        self.ana.presencia(self.conv.id)
        with patch.object(fields.Datetime, 'now', return_value=fields.Datetime.now() + timedelta(hours=25)):
            self.assertEqual(self.env['dcasa.presencia']._limpiar(), 1)
        self.assertFalse(self.env['dcasa.presencia'].sudo().search([]))

    def test_borrar_la_conversacion_borra_su_presencia(self):
        self.ana.presencia(self.otra.id)
        self.otra.sudo().unlink()
        self.assertFalse(self.env['dcasa.presencia'].sudo().search([('conversacion_id', '!=', False)]))
