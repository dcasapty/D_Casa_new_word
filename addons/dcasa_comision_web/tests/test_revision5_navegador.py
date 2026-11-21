"""Quinta revisión adversarial, bloqueante 1: en Chrome, con clics de verdad (tours de ``static/tests/tours``), el
recorrido COMPLETO con el que Gerencia o Nómina encienden el cobro desde la pantalla:

* «Nueva versión» → porcentaje 12 → agregar a dos personas a «Quiénes reciben» (60 / 40) → «Guardar», como Nómina y
  como Gerencia (la primera versión, la que enciende el cobro);
* «Quiénes reciben» → «Cambiar quiénes reciben» → cambiar lo que le toca a una persona y a otra cambiarla por una nueva
  → «Guardar» (una versión nueva con las personas de hoy ya escritas).

Antes del arreglo (``edit="1"`` en la sublista de ``reglas_views.xml``) las tres pruebas caían: «Agregar una línea» abría
un diálogo con «Reglas» obligatorio que no se podía llenar y las filas precargadas no se podían tocar. Las pruebas de
las rondas 3 y 4 (``test_version_nueva_navegador``) solo guardan una versión en pausa, sin reparto, y por eso nadie lo vio.

Control: sin ese atributo «Agregar una línea» vuelve a abrir un diálogo (con «Reglas» obligatorio) en vez de una fila en
la propia lista. Si algún día Odoo deja de comportarse así, el control cae y avisa que el atributo ya no hace falta."""
# ruff: noqa: E501
from odoo import Command
from odoo.tests import HttpCase, new_test_user, tagged

CONTROL_SIN_EDIT = """
(async () => {
    const esperar = async (fn, que, intentos = 200) => {
        for (let i = 0; i < intentos; i++) {
            const r = fn();
            if (r) { return r; }
            await new Promise((ok) => setTimeout(ok, 100));
        }
        throw new Error('No apareció: ' + que);
    };
    (await esperar(() => document.querySelector('.o_control_panel button[name=action_nueva_version]'), 'Nueva versión')).click();
    await esperar(() => document.querySelector('.o_form_view [name=reparto_ids]'), 'la sublista «Quiénes reciben»');
    (await esperar(() => document.querySelector('.o_form_view [name=reparto_ids] .o_field_x2many_list_row_add a'),
                   '«Agregar una línea»')).click();
    await new Promise((ok) => setTimeout(ok, 1500));
    const dialogo = document.querySelector('.modal-dialog');
    const enLinea = document.querySelector('.o_form_view [name=reparto_ids] .o_data_row.o_selected_row');
    console.log('diálogo=' + !!dialogo + ' fila en la propia lista=' + !!enLinea);
    if (enLinea || !dialogo) {
        throw new Error('CONTROL: sin edit="1" «Agregar una línea» debía abrir un diálogo (no una fila en la lista): '
                        + 'el atributo ya no hace falta o la prueba no vigila nada');
    }
    console.log('test successful');
})();
"""


@tagged('post_install', '-at_install')
class TestNuevaVersionConRepartoEnElNavegador(HttpCase):

    def preparar(self):
        company = self.env.company
        for nombre in ('Ana Tour', 'Beto Tour', 'Carla Cambio'):
            self.env['hr.employee'].create({'name': nombre, 'company_id': company.id, 'wage': 1200,
                                            'contract_date_start': '2029-01-01'})
        # Quien aprueba las liquidaciones: alguien de Nómina que no cobra (sin esto no se guarda una versión con reparto).
        new_test_user(self.env, login='rev5_tour_aprueba', name='Aprueba tour', groups='base.group_user,dcasa_nomina.group_nomina')
        new_test_user(self.env, login='rev5_tour_nomina', name='Nómina tour', groups='base.group_user,dcasa_nomina.group_nomina')
        new_test_user(self.env, login='rev5_tour_gerencia', name='Gerencia tour', groups='base.group_user,dcasa_base.group_gerencia')

    def comprobar_version_12(self):
        version = self.env['dcasa.web.reglas'].search([('porcentaje', '=', 12.0)])
        self.assertEqual(len(version), 1, 'Guardar no dejó la versión')
        self.assertEqual(sorted(version.reparto_ids.mapped('porcentaje')), [40.0, 60.0])
        self.assertEqual(sorted(version.reparto_ids.mapped('empleado_id.name')), ['Ana Tour', 'Beto Tour'])
        self.assertEqual(version.estado, 'vigente')

    def test_nomina_guarda_una_version_con_porcentaje_y_reparto_desde_la_pantalla(self):
        self.preparar()
        self.start_tour('/odoo/action-dcasa_comision_web.accion_reglas', 'dcasa_comision_web_nueva_version_con_reparto',
                        login='rev5_tour_nomina', timeout=150)
        self.comprobar_version_12()

    def test_gerencia_guarda_una_version_con_porcentaje_y_reparto_desde_la_pantalla(self):
        self.preparar()
        self.start_tour('/odoo/action-dcasa_comision_web.accion_reglas', 'dcasa_comision_web_nueva_version_con_reparto',
                        login='rev5_tour_gerencia', timeout=150)
        self.comprobar_version_12()

    def test_cambiar_quienes_reciben_guarda_una_version_nueva_con_las_personas_cambiadas(self):
        self.preparar()
        empleados = {e.name: e for e in self.env['hr.employee'].search([('name', 'in', ['Ana Tour', 'Beto Tour'])])}
        primera = self.env['dcasa.web.reglas'].create({
            'company_id': self.env.company.id, 'porcentaje': 10.0, 'tarifa_fija': 25.0, 'reparto_ids': [
                Command.create({'empleado_id': empleados['Ana Tour'].id, 'porcentaje': 60.0}),
                Command.create({'empleado_id': empleados['Beto Tour'].id, 'porcentaje': 40.0})]})
        self.start_tour('/odoo/action-dcasa_comision_web.accion_quienes_reciben', 'dcasa_comision_web_cambiar_quienes_reciben',
                        login='rev5_tour_nomina', timeout=150)
        nueva = self.env['dcasa.web.reglas'].search([('numero', '>', primera.numero)])
        self.assertEqual(len(nueva), 1, 'Guardar no dejó la versión nueva')
        self.assertEqual({r.empleado_id.name: r.porcentaje for r in nueva.reparto_ids}, {'Ana Tour': 50.0, 'Carla Cambio': 50.0})
        self.assertEqual((nueva.porcentaje, nueva.tarifa_fija), (10.0, 25.0), 'lo demás viene de la versión de hoy')
        self.assertEqual(nueva.estado, 'vigente')
        primera.invalidate_recordset()
        self.assertEqual(sorted(primera.reparto_ids.mapped('porcentaje')), [40.0, 60.0], 'la versión vieja queda igual')

    def test_control_sin_el_edit_agregar_una_linea_abre_un_dialogo_que_no_se_puede_llenar(self):
        """Quita el ``edit="1"`` con una vista heredada (el estado de antes del arreglo) y comprueba que Odoo vuelve a
        marcar la sublista como no editable: «Agregar una línea» abre un diálogo y no una fila. Por eso las tres pruebas
        de arriba caían."""
        self.env['ir.ui.view'].create({
            'name': 'control sin edit', 'model': 'dcasa.web.reglas',
            'inherit_id': self.env.ref('dcasa_comision_web.reglas_form').id,
            'arch': '<xpath expr="//field[@name=\'reparto_ids\']/list" position="attributes"><attribute name="edit"/></xpath>'})
        new_test_user(self.env, login='rev5_tour_control', name='Nómina control', groups='base.group_user,dcasa_nomina.group_nomina')
        self.browser_js('/odoo/action-dcasa_comision_web.accion_reglas', CONTROL_SIN_EDIT, login='rev5_tour_control', timeout=120)
