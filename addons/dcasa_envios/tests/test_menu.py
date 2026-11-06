"""El menú «Envíos»: sin «En desarrollo», con Calculadora (primero, para todos), Lugares y Tarifa (Gerencia)."""
from pathlib import Path

from odoo.addons.dcasa_guia.models import guia as G
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestMenuEnvios(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.vendedora = new_test_user(cls.env, login='vend_menu_env',
                                      groups='base.group_user,dcasa_base.group_vendedora')
        cls.caja = new_test_user(cls.env, login='caja_menu_env', groups='base.group_user,dcasa_base.group_caja')
        cls.gerencia = new_test_user(cls.env, login='ger_menu_env', groups='base.group_user,dcasa_base.group_gerencia')

    def menus_de(self, usuario):
        menus = self.env['ir.ui.menu'].with_user(usuario).load_menus(False)
        return {m['xmlid']: m for m in menus.values() if isinstance(m, dict) and m.get('xmlid')}

    def test_el_menu_envios_ya_no_dice_en_desarrollo(self):
        raiz = self.env.ref('dcasa_contabilidad.menu_envios_root')
        self.assertFalse(self.env.ref('dcasa_contabilidad.menu_envios_en_desarrollo').active)
        hijos = raiz.child_id.sorted('sequence')
        self.assertEqual(hijos.mapped('name'), ['Calculadora', 'Lugares', 'Tarifa'])
        calculadora = self.env.ref('dcasa_envios.menu_envios_calculadora')
        self.assertEqual(calculadora.action, self.env.ref('dcasa_envios.accion_calculadora'))
        self.assertEqual(calculadora.action.tag, 'dcasa_envios.calculadora')
        self.assertEqual(calculadora.action.path, 'envios')

    def test_cada_quien_ve_lo_suyo(self):
        for usuario in (self.vendedora, self.caja):
            menus = self.menus_de(usuario)
            with self.subTest(usuario=usuario.login):
                self.assertIn('dcasa_envios.menu_envios_calculadora', menus)
                self.assertIn('dcasa_envios.menu_envios_lugares', menus)
                self.assertNotIn('dcasa_envios.menu_envios_tarifa', menus)
                raiz = menus['dcasa_contabilidad.menu_envios_root']
                primero = menus['dcasa_envios.menu_envios_calculadora']
                self.assertEqual(raiz['children'][0], primero['id'], 'Envíos abre la calculadora')
        self.assertIn('dcasa_envios.menu_envios_tarifa', self.menus_de(self.gerencia))

    def test_la_pantalla_esta_registrada_y_baja_con_scroll(self):
        raiz = Path(__file__).resolve().parents[1] / 'static' / 'src'
        js = (raiz / 'js' / 'calculadora.js').read_text()
        self.assertIn('registry.category("actions").add("dcasa_envios.calculadora"', js)
        plantilla = (raiz / 'xml' / 'calculadora.xml').read_text()
        self.assertIn('<div class="o_action o_dcasa_envios">', plantilla)
        scss = (raiz / 'scss' / 'calculadora.scss').read_text()
        self.assertIn('.o_web_client > .o_action_manager > .o_dcasa_envios.o_action {', scss)
        self.assertIn('Datos de mapas © colaboradores de OpenStreetMap (ODbL) y GeoNames (CC BY 4.0)', plantilla)

    def test_la_guia_lleva_a_la_calculadora_y_a_la_tarifa(self):
        tareas = {t['id']: t for t in G.cargar_catalogo()['tareas']}
        self.assertEqual(tareas['envio-cuanto-cuesta']['destino'], {'menu': 'dcasa_envios.menu_envios_calculadora'})
        self.assertEqual(tareas['envio-tarifa']['destino'], {'menu': 'dcasa_envios.menu_envios_tarifa'})
        if 'dcasa.guia' not in self.env:
            self.skipTest('dcasa_guia no está instalado en esta base')
        Guia = self.env['dcasa.guia']
        de_vendedora = {t['id'] for t in Guia.with_user(self.vendedora).buscar('cuanto cuesta el envio')}
        self.assertIn('envio-cuanto-cuesta', de_vendedora)
        self.assertNotIn('envio-tarifa', {t['id'] for t in Guia.with_user(self.vendedora).buscar('tarifa de envio')})
        self.assertIn('envio-tarifa', {t['id'] for t in Guia.with_user(self.gerencia).buscar('tarifa de envio')})
