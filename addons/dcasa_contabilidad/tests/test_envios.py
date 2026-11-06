"""La categoría «Envíos» del menú (pedido del jefe, 2026-10-16). Nació «En desarrollo»; con ``dcasa_envios``
instalado (2026-11-06) ese item se apaga y queda la calculadora (sus pruebas están en ``dcasa_envios``)."""
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestEnvios(TransactionCase):

    def _con_calculadora(self):
        return self.env['ir.module.module'].search_count([('name', '=', 'dcasa_envios'), ('state', '=', 'installed')])

    def test_envios_es_una_categoria_del_menu_con_su_seccion_en_desarrollo(self):
        raiz = self.env.ref('dcasa_contabilidad.menu_envios_root')
        hijo = self.env.ref('dcasa_contabilidad.menu_envios_en_desarrollo')
        self.assertEqual(raiz.name, 'Envíos')
        self.assertFalse(raiz.parent_id, 'es una aplicación del menú, con su ícono')
        self.assertTrue(raiz.web_icon_data, 'lleva su ícono')
        self.assertEqual(hijo.parent_id, raiz)
        self.assertEqual(hijo.name, 'En desarrollo')
        self.assertEqual(hijo.action.tag, 'dcasa_en_desarrollo')
        self.assertEqual(hijo.action.params, {'clave': 'envios'})
        self.assertEqual(hijo.active, not self._con_calculadora(),
                         'con la calculadora instalada, «En desarrollo» se apaga')

    def test_todo_el_personal_ve_la_categoria(self):
        vendedora = new_test_user(self.env, login='vend_envios', groups='base.group_user,dcasa_base.group_vendedora')
        menus = self.env['ir.ui.menu'].with_user(vendedora).load_menus(False)
        xmlids = {m['xmlid'] for m in menus.values() if isinstance(m, dict) and m.get('xmlid')}
        self.assertIn('dcasa_contabilidad.menu_envios_root', xmlids)
        if self._con_calculadora():
            self.assertIn('dcasa_envios.menu_envios_calculadora', xmlids)
            self.assertNotIn('dcasa_contabilidad.menu_envios_en_desarrollo', xmlids)
        else:
            self.assertIn('dcasa_contabilidad.menu_envios_en_desarrollo', xmlids)
