"""La Actividad (mensajes y notas) de los formularios arranca oculta y se muestra con un botón."""
import os

from odoo.tests import HttpCase, new_test_user, tagged
from odoo.tools import file_path


@tagged('post_install', '-at_install')
class TestActividadOculta(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.vendedora = new_test_user(cls.env, login='vendedora_actividad',
                                      groups='base.group_user,sales_team.group_sale_salesman')

    def test_el_codigo_de_la_pantalla_oculta_el_panel_y_ofrece_el_boton(self):
        """Sin navegador: lo que dice el código (para que un cambio sin querer salte aunque no haya Chromium)."""
        with open(file_path('dcasa_interfaz/static/src/js/actividad.js'), encoding='utf-8') as archivo:
            js = archivo.read()
        self.assertIn('export const actividad = reactive({ visible: leerGuardado() })', js)
        self.assertIn('return "NONE"', js)
        self.assertIn('"SIDE_CHATTER"', js)
        with open(file_path('dcasa_interfaz/static/src/xml/actividad.xml'), encoding='utf-8') as archivo:
            xml = archivo.read()
        self.assertIn('o_dcasa_actividad_boton', xml)
        self.assertIn('control-panel-additional-actions', xml)

    def test_en_el_navegador_arranca_oculta_y_el_boton_la_muestra(self):
        if os.environ.get('DCASA_SIN_NAVEGADOR'):
            self.skipTest('sin navegador')
        self.browser_js('/odoo/action-sale.action_quotations_with_onboarding/new', """
(async () => {
    const esperar = async (cond, que) => {
        for (let i = 0; i < 100; i++) {
            const r = cond();
            if (r) { return r; }
            await new Promise((s) => setTimeout(s, 100));
        }
        throw new Error('No apareció: ' + que);
    };
    try { window.localStorage.removeItem('dcasa.actividad_visible'); } catch (e) { /* sin almacenamiento */ }
    await esperar(() => document.querySelector('.o_form_view .o_form_sheet'), 'el formulario de la cotización');
    const boton = await esperar(() => document.querySelector('.o_dcasa_actividad_boton'), 'el botón Actividad');
    if (document.querySelector('.o-mail-Chatter')) { throw new Error('la actividad debe arrancar oculta'); }
    if (boton.classList.contains('active')) { throw new Error('el botón no debe verse pulsado si está oculta'); }
    boton.click();
    await esperar(() => document.querySelector('.o-mail-Chatter'), 'el panel de actividad tras pulsar el botón');
    if (window.localStorage.getItem('dcasa.actividad_visible') !== '1') { throw new Error('no recordó la elección'); }
    document.querySelector('.o_dcasa_actividad_boton').click();
    await esperar(() => !document.querySelector('.o-mail-Chatter'), 'que se oculte otra vez');
    if (window.localStorage.getItem('dcasa.actividad_visible') !== '0') { throw new Error('no recordó que la ocultó'); }
    console.log('test successful');
})();
""", login='vendedora_actividad')

    def test_en_el_celular_la_cabecera_del_formulario_va_en_un_renglon(self):
        """Auditoría visual del 2026-11-11: «Nuevo», el engranaje, «Actividad» y las flechas no cabían juntos y la
        cabecera ocupaba dos renglones (128 px de 664). En el celular «Actividad» va solo con su ícono (conserva su
        nombre para los lectores de pantalla) y todo queda en un renglón; en la computadora se ve la palabra."""
        if os.environ.get('DCASA_SIN_NAVEGADOR'):
            self.skipTest('sin navegador')
        cliente = self.env['res.partner'].create({'name': 'Cliente Cabecera Celular'})
        cuerpo = r"""
(async () => {
    const esperar = async (cond, que) => {
        for (let i = 0; i < 100; i++) {
            const r = cond();
            if (r) { return r; }
            await new Promise((s) => setTimeout(s, 100));
        }
        throw new Error('No apareció: ' + que);
    };
    await esperar(() => document.querySelector('.o_form_view .o_form_sheet'), 'el formulario');
    const boton = await esperar(() => document.querySelector('.o_dcasa_actividad_boton'), 'el botón Actividad');
    const texto = boton.querySelector('.o_dcasa_actividad_texto');
    if (boton.getAttribute('aria-label') !== 'Actividad') { throw new Error('el botón debe llamarse Actividad'); }
    const celular = window.innerWidth < 768;
    if (celular === (getComputedStyle(texto).display !== 'none')) {
        throw new Error(celular ? 'en el celular va solo el ícono' : 'en la computadora se ve la palabra');
    }
    const cabecera = document.querySelector('.o_form_view .o_control_panel').getBoundingClientRect();
    const nuevo = document.querySelector('.o_form_button_create').getBoundingClientRect();
    const flechas = document.querySelector('.o_control_panel .o_pager').getBoundingClientRect();
    if (flechas.width < 1 || flechas.right > window.innerWidth + 1) { throw new Error('las flechas deben verse'); }
    if (Math.abs((flechas.top + flechas.bottom) / 2 - (nuevo.top + nuevo.bottom) / 2) > 12) {
        throw new Error(`las flechas bajaron a otro renglón: ${Math.round(flechas.top)} y ${Math.round(nuevo.top)}`);
    }
    if (celular && cabecera.height > 80) { throw new Error('la cabecera mide ' + Math.round(cabecera.height) + 'px'); }
    // La ficha del contacto en el celular: la foto chica y el nombre con espacio para leerse.
    const foto = document.querySelector('.o_field_contact_image img');
    const nombre = document.querySelector('.o_form_sheet h1 .o_input');
    if (celular && foto && foto.getBoundingClientRect().width > 80) {
        throw new Error('la foto mide ' + Math.round(foto.getBoundingClientRect().width) + 'px en el celular');
    }
    if (celular && nombre && nombre.clientWidth < 220) {
        throw new Error('el nombre solo tiene ' + nombre.clientWidth + 'px');
    }
    console.log('test successful');
})();
"""
        for tamano in ('390x844', '1366x768'):
            with self.subTest(tamano=tamano):
                self.browser_size = tamano
                self.browser_js(f'/odoo/action-base.action_partner_form/{cliente.id}', cuerpo, login='admin')
