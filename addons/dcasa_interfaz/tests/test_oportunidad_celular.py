"""La oportunidad del CRM en el celular: sin el «en» suelto al lado del monto (auditoría visual del 2026-11-11).

En la computadora el formulario de Odoo se lee de corrido: «$ 0.00 en 0.00 %». En el celular la probabilidad baja a su
propio renglón, con su rótulo, y el «en» quedaba colgando al lado del monto. De paso se mira que el «Ctrl K» de la
barra lateral no vuelva a medir menos de 11.5 px (medía 10.9)."""
import os

from odoo.tests import HttpCase, tagged

from .test_inicio_por_rol import ESPERAR_JS


@tagged('post_install', '-at_install')
class TestOportunidadEnElCelular(HttpCase):

    def test_el_conector_solo_se_ve_donde_se_lee_de_corrido(self):
        if os.environ.get('DCASA_SIN_NAVEGADOR'):
            self.skipTest('sin navegador')
        oportunidad = self.env['crm.lead'].create({'name': 'Oportunidad en el celular', 'type': 'opportunity'})
        codigo = '(async () => {' + ESPERAR_JS + """
            const fila = await esperar(() => document.querySelector('.o_lead_opportunity_form .o_form_sheet h2'),
                                       'el renglón del monto');
            const monto = await esperar(() => fila.querySelector('[name="expected_revenue"]'), 'el ingreso esperado');
            const atajo = document.querySelector('.o_dcasa_barra kbd');
            if (atajo && parseFloat(getComputedStyle(atajo).fontSize) < 11.5) {
                throw new Error('el «Ctrl K» de la barra se lee muy chico: ' + getComputedStyle(atajo).fontSize);
            }
            if (fila.querySelector('[name="recurring_revenue"]')) {     // con ingresos recurrentes lo resuelve Odoo
                console.log('test successful');
                return;
            }
            const conector = [...fila.querySelectorAll(':scope > div:first-child span.opacity-50')];
            if (!conector.length) { throw new Error('Odoo cambió el formulario: no está el conector del monto'); }
            const probabilidad = fila.querySelector('[name="probability"]').getBoundingClientRect();
            const deCorrido = Math.abs(probabilidad.top - monto.getBoundingClientRect().top) < 30;
            const seVe = conector.some((c) => c.getBoundingClientRect().width > 0);
            if (window.innerWidth < 576 && deCorrido) {
                throw new Error('en el celular se esperaba la probabilidad en su propio renglón');
            }
            if (seVe !== deCorrido) {
                throw new Error(deCorrido ? 'en un renglón debe leerse «monto en probabilidad»'
                    : 'el conector queda colgando: la probabilidad va en otro renglón');
            }
            if (document.documentElement.scrollWidth > window.innerWidth + 1) {
                throw new Error('la página se sale de lado');
            }
            console.log('test successful');
        })();"""
        for tamano in ('390x844', '1366x768'):
            with self.subTest(tamano=tamano):
                self.browser_size = tamano
                self.browser_js(f'/odoo/action-crm.crm_lead_action_pipeline/{oportunidad.id}', codigo, login='admin')
