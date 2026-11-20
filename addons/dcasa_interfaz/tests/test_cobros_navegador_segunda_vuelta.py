# ruff: noqa: E501  (JavaScript del navegador embebido en texto)
"""rv_web, segunda vuelta (2026-11-20): la tarjeta «Cobrado por forma de pago» con respuestas que llegan en desorden
(«el último gana»), el selector accesible y la tarjeta cuando lo cobrado no carga."""
from datetime import timedelta
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import HttpCase, tagged

from .test_cifras_que_suben import ESPIAR_JS
from .test_pantallas_navegador import COMUN_JS, PantallasMixin


@tagged('post_install', '-at_install')
class TestRvWeb2TarjetaDeCobros(PantallasMixin, HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.banco2 = cls.env['account.journal'].create({'name': 'Banco rv_web2', 'type': 'bank', 'code': 'RV2B'})
        primero = cls.hoy.replace(day=1)
        for monto, dia in ((120.0, cls.hoy), (45.0, primero)):
            cls.env['account.payment'].create({
                'payment_type': 'inbound', 'partner_type': 'customer', 'partner_id': cls.cliente.id, 'amount': monto,
                'date': dia, 'journal_id': cls.banco2.id}).action_post()
        lunes = cls.hoy - timedelta(days=cls.hoy.weekday())
        cls.semana_igual_que_mes = lunes <= primero

    def test_respuestas_en_desorden_el_ultimo_clic_gana_y_el_selector_es_accesible(self):
        if self.semana_igual_que_mes:
            self.skipTest('hoy la semana y el mes cuentan lo mismo: la prueba no distinguiría')
        codigo = '(async () => {' + COMUN_JS + ESPIAR_JS + r"""
            const errores = [];
            window.addEventListener('error', (ev) => errores.push(String(ev.message)));
            const tarjetas = () => [...document.querySelectorAll('.o_dcasa_pd_cobros')].filter((t) => t.offsetParent !== null);
            await esperar(() => tarjetas().length === 1 && !tarjetas()[0].classList.contains('o_cargando'), 'la tarjeta', 60);
            const botones = () => Object.fromEntries([...tarjetas()[0].querySelectorAll('.o_dcasa_periodo')].map((b) => [b.textContent.trim(), b]));
            // --- El selector: botones normales con aria-pressed, en un grupo (nada de role="radio" sin flechas) ---
            const grupo = tarjetas()[0].querySelector('.o_dcasa_cf_periodos');
            if (grupo.getAttribute('role') !== 'group') { falla('el grupo debía ser role=group: ' + grupo.getAttribute('role')); }
            if (grupo.querySelector('[role="radio"]')) { falla('quedó un role=radio sin teclas de flecha'); }
            for (const [nombre, b] of Object.entries(botones())) {
                if (b.tagName !== 'BUTTON' || b.type !== 'button') { falla(nombre + ' no es un botón'); }
                if (!['true', 'false'].includes(b.getAttribute('aria-pressed'))) { falla(nombre + ' sin aria-pressed'); }
                if (b.hasAttribute('aria-checked')) { falla(nombre + ' conserva aria-checked'); }
            }
            const pulsados = Object.entries(botones()).filter(([, b]) => b.getAttribute('aria-pressed') === 'true').map(([n]) => n);
            igual(pulsados, ['Día'], 'solo «Día» pulsado al abrir');
            // --- Respuestas que llegan en desorden: la de «Semana» tarda 2,5 s y la de «Mes» llega enseguida ---
            const { browser } = odoo.loader.modules.get('@web/core/browser/browser');
            const original = browser.XMLHttpRequest;
            browser.XMLHttpRequest = class extends original {
                send(cuerpo) {
                    if (typeof cuerpo === 'string' && cuerpo.includes('"periodo":"semana"')) { setTimeout(() => super.send(cuerpo), 2500); }
                    else { super.send(cuerpo); }
                }
            };
            try {
                botones()['Semana'].click();
                await pausa(100);
                botones()['Mes'].click();
                await esperar(() => /^Mes de /i.test(tarjetas()[0].querySelector('.o_dcasa_pd_cobros_periodo').textContent.trim()), 'la respuesta de «Mes»', 60);
                const totalMes = tarjetas()[0].querySelector('.o_dcasa_cf_total .o_dcasa_cf_monto').textContent;
                await pausa(3500);       // llega la vieja de «Semana»: se descarta
                const periodo = tarjetas()[0].querySelector('.o_dcasa_pd_cobros_periodo').textContent.trim();
                if (!/^Mes de /i.test(periodo)) { falla('la respuesta vieja de «Semana» pisó a «Mes»: ' + periodo); }
                igual(tarjetas()[0].querySelector('.o_dcasa_cf_total .o_dcasa_cf_monto').textContent, totalMes, 'el total no cambió con la respuesta vieja');
                if (tarjetas()[0].classList.contains('o_cargando')) { falla('la tarjeta se quedó atenuada'); }
                igual(Object.entries(botones()).filter(([, b]) => b.getAttribute('aria-pressed') === 'true').map(([n]) => n), ['Mes'], 'solo «Mes» pulsado');
            } finally {
                browser.XMLHttpRequest = original;
            }
            if (errores.length) { falla('errores en la página: ' + errores.join(' | ')); }
        """ + "console.log('test successful'); })();"
        self.browser_size = '1440x900'
        self.browser_js('/odoo/action-dcasa_interfaz.accion_facturado_por_dia', codigo, login='gerencia_rol', timeout=180)

    def test_si_lo_cobrado_no_carga_la_tarjeta_lo_dice_y_se_recupera(self):
        """La primera llamada a lo cobrado falla al abrir la pantalla: la tarjeta lo dice (no deja un hueco) y, cuando el
        servidor vuelve, cualquier recarga de la pantalla la llena."""
        estado = {'fallos': 2}   # al abrir se pide dos veces: la de elegir el día y la de reintentar si falló
        tablero = self.env.registry['dcasa.tablero']
        original = tablero._cobros_del_periodo

        def _cobros(modelo, dia, periodo, hoy):
            if estado['fallos'] > 0:
                estado['fallos'] -= 1
                raise UserError('Falla de prueba de lo cobrado')
            return original(modelo, dia, periodo, hoy)

        codigo = '(async () => {' + COMUN_JS + ESPIAR_JS + r"""
            const tarjetas = () => [...document.querySelectorAll('.o_dcasa_pd_cobros')].filter((t) => t.offsetParent !== null);
            await esperar(() => tarjetas().length === 1 && tarjetas()[0].querySelector('.o_dcasa_error'), 'el aviso de que no cargó', 60);
            const aviso = tarjetas()[0].querySelector('.o_dcasa_error');
            if (aviso.getAttribute('role') !== 'alert') { falla('el aviso debía ser role=alert'); }
            if (!aviso.textContent.includes('Falla de prueba de lo cobrado')) { falla('el aviso dice por qué: ' + aviso.textContent); }
            if (tarjetas()[0].querySelector('.o_dcasa_cf_ficha')) { falla('sin datos no debía haber fichas'); }
            // El calendario y el detalle del día siguen funcionando sin lo cobrado.
            if (!document.querySelector('.o_dcasa_pd_celda')) { falla('el calendario debía verse'); }
            document.querySelector('.o_dcasa_pd_base_confirmado').click();   // otra carga de la pantalla
            // Mientras la pantalla recarga la tarjeta puede no estar en el árbol un instante: esperar, no fallar.
            await esperar(() => tarjetas()[0] && !tarjetas()[0].querySelector('.o_dcasa_error') && tarjetas()[0].querySelector('.o_dcasa_cf_total'), 'se recupera', 60);
        """ + "console.log('test successful'); })();"
        self.browser_size = '1440x900'
        with patch.object(tablero, '_cobros_del_periodo', _cobros):
            self.browser_js('/odoo/action-dcasa_interfaz.accion_facturado_por_dia', codigo, login='gerencia_rol', timeout=180)
