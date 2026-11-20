"""La pantalla de una versión nueva de las reglas no se guarda sola (``static/src/js/version_sin_guardado_solo.js``).

Una versión guardada no se edita ni se borra: si Odoo la guardara sola al salir de la página o al cambiar de pestaña,
quedarían versiones de más para siempre. Se prueba en el navegador con un usuario de Nómina.

La prueba tiene que CAER sin el parche (cuarta revisión adversarial, 2026-11-20): el dato que se escribe es algo que de
verdad se puede guardar (el motivo del cambio; el resto de la versión nueva viene vacío y es una pausa válida). Antes
se escribía un porcentaje de 5 sin reparto, que no se puede guardar con o sin parche: la prueba pasaba siempre. El
control vuelve a registrar el formulario normal de Odoo (sin el parche) y exige que ahí SÍ se guarde sola una versión
al cambiar de pestaña: si algún día ese control dejara de caer, la prueba ya no vigila nada."""
from datetime import timedelta

from odoo import fields
from odoo.tests import HttpCase, new_test_user, tagged

PRELUDIO = """
const esperar = async (fn, que, intentos = 200) => {
    for (let i = 0; i < intentos; i++) {
        const r = fn();
        if (r) { return r; }
        await new Promise((ok) => setTimeout(ok, 100));
    }
    throw new Error('No apareció: ' + que);
};
const cuantas = async () => {
    const r = await fetch('/web/dataset/call_kw/dcasa.web.reglas/search_count', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            jsonrpc: '2.0', method: 'call',
            params: { model: 'dcasa.web.reglas', method: 'search_count', args: [[]], kwargs: {} } }) });
    return (await r.json()).result;
};
const escribir = async (campo, valor, soltar = false) => {
    const entrada = await esperar(() => document.querySelector('.o_form_view [name=' + campo + '] input'), campo);
    entrada.focus();
    entrada.value = valor;
    entrada.dispatchEvent(new Event('input', { bubbles: true }));
    entrada.dispatchEvent(new Event('change', { bubbles: true }));
    if (soltar) {
        // Como quien termina de escribir y toca otra cosa: el formulario ya muestra «Guardar» y «Descartar».
        entrada.dispatchEvent(new FocusEvent('blur', { bubbles: false }));
        entrada.dispatchEvent(new FocusEvent('focusout', { bubbles: true }));
        entrada.blur();
    }
    await new Promise((ok) => setTimeout(ok, 400));
};
const nuevaVersion = async () => {
    await esperar(() => document.querySelector('.o_list_view'), 'la lista de reglas');
    const nueva = await esperar(() => document.querySelector('.o_control_panel button[name=action_nueva_version]'),
                                'el botón «Nueva versión»');
    nueva.click();
};
"""

# Vuelve a registrar el formulario normal de Odoo en lugar del que no se guarda solo: es «sin el parche».
SIN_PARCHE = """
const { registry } = odoo.loader.modules.get('@web/core/registry');
const { formView } = odoo.loader.modules.get('@web/views/form/form_view');
registry.category('views').add('dcasa_reglas_form', formView, { force: true });
"""

RECORRIDO = """
const antes = await cuantas();
await nuevaVersion();
await escribir('motivo', 'cambio a medias');
// 1. Se cambia de pestaña del navegador con la versión a medio escribir.
Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'hidden' });
document.dispatchEvent(new Event('visibilitychange'));
await new Promise((ok) => setTimeout(ok, 1500));
Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'visible' });
const trasPestana = await cuantas();
// 2. Se sale de la pantalla (la migaja de pan) sin tocar «Guardar».
const migaja = await esperar(() => document.querySelector('.o_breadcrumb .breadcrumb-item:not(.active) a, '
    + '.o_breadcrumb .o_back_button'), 'la migaja de pan');
migaja.click();
await esperar(() => document.querySelector('.o_list_view'), 'volver a la lista');
await new Promise((ok) => setTimeout(ok, 1500));
const trasSalir = await cuantas();
console.log('versiones: antes=' + antes + ' tras_pestana=' + trasPestana + ' tras_salir=' + trasSalir);
if (%(se_guarda_sola)s) {
    if (trasPestana === antes && trasSalir === antes) {
        throw new Error('CONTROL: sin el parche tampoco se guardó sola: la prueba no detecta la falla');
    }
} else {
    if (trasPestana !== antes) { throw new Error('Cambiar de pestaña guardó una versión'); }
    if (trasSalir !== antes) { throw new Error('Salir de la pantalla guardó una versión'); }
}
console.log('test successful');
"""

GUARDAR_Y_DESCARTAR = """
const antes = await cuantas();
await nuevaVersion();
await escribir('motivo', 'pausa de prueba', true);
(await esperar(() => document.querySelector('.o_form_button_save'), 'Guardar')).click();
await new Promise((ok) => setTimeout(ok, 1500));
const trasGuardar = await cuantas();
if (trasGuardar !== antes + 1) { throw new Error('Guardar no guardó: antes=' + antes + ' después=' + trasGuardar); }
const migaja = await esperar(() => document.querySelector('.o_breadcrumb .breadcrumb-item:not(.active) a, '
    + '.o_breadcrumb .o_back_button'), 'la migaja de pan');
migaja.click();
await nuevaVersion();
await escribir('motivo', 'esto se descarta', true);
(await esperar(() => document.querySelector('.o_form_button_cancel'), 'Descartar')).click();
await new Promise((ok) => setTimeout(ok, 1000));
if ((await cuantas()) !== trasGuardar) { throw new Error('Descartar guardó una versión'); }
console.log('test successful');
"""

# Una versión que todavía no rige se anula con su motivo: se escribe el motivo en el formulario (una versión guardada
# no se edita, pero el motivo de la anulación sí) y se toca «Anular». Sin esto la pantalla dejaba un botón que no se
# podía usar.
ANULAR = """
await esperar(() => document.querySelector('.o_form_view'), 'el formulario de la versión');
const leer = async () => {
    const r = await fetch('/web/dataset/call_kw/dcasa.web.reglas/read', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            jsonrpc: '2.0', method: 'call',
            params: { model: 'dcasa.web.reglas', method: 'read',
                      args: [[%(id)s], ['anulada', 'motivo_anulacion']], kwargs: {} } }) });
    return (await r.json()).result[0];
};
if ((await leer()).anulada) { throw new Error('La versión ya estaba anulada'); }
const campo = document.querySelector('.o_form_view [name=porcentaje] input');
if (campo) { throw new Error('Una versión guardada no se edita: el porcentaje no se debe poder escribir'); }
// El edit="1" de la sublista «Quiénes reciben» es solo para una versión nueva: en una guardada no se agrega a nadie.
if (document.querySelector('.o_form_view [name=reparto_ids] .o_field_x2many_list_row_add a')) {
    throw new Error('Una versión guardada no se edita: no se debe poder agregar a nadie a «Quiénes reciben»');
}
await escribir('motivo_anulacion', 'se puso con el año equivocado', true);
(await esperar(() => document.querySelector('button[name=action_anular]'), 'el botón Anular')).click();
(await esperar(() => document.querySelector('.modal-footer .btn-primary'), 'la confirmación')).click();
await new Promise((ok) => setTimeout(ok, 2000));
const despues = await leer();
if (!despues.anulada) { throw new Error('Anular no anuló la versión: ' + JSON.stringify(despues)); }
if (despues.motivo_anulacion !== 'se puso con el año equivocado') { throw new Error('No guardó el motivo'); }
console.log('test successful');
"""


def codigo(cuerpo, sin_parche=False, **valores):
    cuerpo = cuerpo % valores if valores else cuerpo
    return '(async () => {' + PRELUDIO + (SIN_PARCHE if sin_parche else '') + cuerpo + '})();'


@tagged('post_install', '-at_install')
class TestVersionNuevaNoSeGuardaSola(HttpCase):

    def navegar(self, login, js):
        new_test_user(self.env, login=login, name='Nómina versión nueva',
                      groups='base.group_user,dcasa_nomina.group_nomina')
        self.browser_js('/odoo/action-dcasa_comision_web.accion_reglas', js, login=login, timeout=120)

    def test_con_el_parche_ni_al_cambiar_de_pestana_ni_al_salir_se_guarda_una_version(self):
        self.navegar('nomina_version_nueva', codigo(RECORRIDO, se_guarda_sola='false'))

    def test_control_sin_el_parche_el_mismo_cambio_si_se_guarda_solo(self):
        """Lo que hace la prueba de arriba útil: con el formulario normal de Odoo, el MISMO recorrido guarda una versión
        sola. Si esto deja de pasar, la prueba de arriba ya no vigila nada."""
        self.navegar('nomina_version_nueva_control', codigo(RECORRIDO, sin_parche=True, se_guarda_sola='true'))

    def test_guardar_con_el_boton_y_descartar_siguen_funcionando(self):
        self.navegar('nomina_version_nueva_guardar', codigo(GUARDAR_Y_DESCARTAR))

    def test_una_version_que_todavia_no_rige_se_anula_con_su_motivo_desde_la_pantalla(self):
        version = self.env['dcasa.web.reglas'].create({
            'company_id': self.env.company.id, 'porcentaje': 0.0,
            'rige_desde': fields.Datetime.now() + timedelta(days=10), 'motivo': 'puesta con el año equivocado'})
        new_test_user(self.env, login='nomina_version_anular', name='Nómina anula',
                      groups='base.group_user,dcasa_nomina.group_nomina')
        self.browser_js(f'/odoo/action-dcasa_comision_web.accion_reglas/{version.id}',
                        codigo(ANULAR, id=version.id), login='nomina_version_anular', timeout=120)
        version.invalidate_recordset()
        self.assertTrue(version.anulada)
