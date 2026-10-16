"""La categoría «Envíos» del menú, marcada «En desarrollo» (pedido del jefe, 2026-10-16)."""
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestEnvios(TransactionCase):

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

    def test_todo_el_personal_ve_la_categoria(self):
        vendedora = new_test_user(self.env, login='vend_envios', groups='base.group_user,dcasa_base.group_vendedora')
        menus = self.env['ir.ui.menu'].with_user(vendedora).load_menus(False)
        xmlids = {m['xmlid'] for m in menus.values() if isinstance(m, dict) and m.get('xmlid')}
        self.assertIn('dcasa_contabilidad.menu_envios_root', xmlids)
        self.assertIn('dcasa_contabilidad.menu_envios_en_desarrollo', xmlids)
