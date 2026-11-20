"""La pantalla de una versión nueva de las reglas no se guarda sola (``static/src/js/version_sin_guardado_solo.js``).

Una versión guardada no se edita ni se borra: si Odoo la guardara sola al salir de la página o al cambiar de pestaña,
quedarían versiones de más para siempre. Se prueba en el navegador con un usuario de Nómina."""
from odoo.tests import HttpCase, new_test_user, tagged

CODIGO = """
(async () => {
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
    const escribir = async () => {
        const entrada = await esperar(
            () => document.querySelector('.o_form_view [name=porcentaje] input'), 'el porcentaje');
        entrada.focus();
        entrada.value = '5';
        entrada.dispatchEvent(new Event('input', { bubbles: true }));
        entrada.dispatchEvent(new Event('change', { bubbles: true }));
        await new Promise((ok) => setTimeout(ok, 400));
    };
    const antes = await cuantas();
    // 1. Se cambia de pestaña del navegador con la versión a medio escribir.
    await esperar(() => document.querySelector('.o_list_view'), 'la lista de reglas');
    const nueva = await esperar(() => document.querySelector('.o_control_panel button[name=action_nueva_version]'),
                                'el botón «Nueva versión»');
    nueva.click();
    await escribir();
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'hidden' });
    document.dispatchEvent(new Event('visibilitychange'));
    await new Promise((ok) => setTimeout(ok, 1500));
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'visible' });
    if ((await cuantas()) !== antes) { throw new Error('Cambiar de pestaña guardó una versión'); }
    // 2. Se sale de la pantalla (la migaja de pan) sin tocar «Guardar».
    const migaja = await esperar(() => document.querySelector('.o_breadcrumb .breadcrumb-item:not(.active) a, '
        + '.o_breadcrumb .o_back_button'), 'la migaja de pan');
    migaja.click();
    await esperar(() => document.querySelector('.o_list_view'), 'volver a la lista');
    await new Promise((ok) => setTimeout(ok, 1500));
    if ((await cuantas()) !== antes) { throw new Error('Salir de la pantalla guardó una versión'); }
    console.log('test successful');
})();
"""


@tagged('post_install', '-at_install')
class TestVersionNuevaNoSeGuardaSola(HttpCase):

    def test_ni_al_cambiar_de_pestana_ni_al_salir_se_guarda_una_version(self):
        new_test_user(self.env, login='nomina_version_nueva', name='Nómina versión nueva',
                      groups='base.group_user,dcasa_nomina.group_nomina')
        self.browser_js('/odoo/action-dcasa_comision_web.accion_reglas', CODIGO, login='nomina_version_nueva',
                        timeout=120)
