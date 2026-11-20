"""El pago en el celular (pedido de Gerencia: «los clientes pagan desde el celular»): en Chrome con el teléfono emulado,
el botón de pagar se ve SIN deslizar, a todo el ancho, de 52 px o más, y cae en la zona del pulgar (la parte de abajo
de la pantalla); la página no se arrastra de lado; el resumen del pedido va plegable ARRIBA con el monto.

Lo que se mide es lo que vería una persona: la caja real de cada elemento en Chrome, no el código de la plantilla."""
import os
from unittest.mock import patch

from odoo.tests import tagged

from .chrome_movil import ALTO, ChromeMovilCase
from .test_pago_visual import CLAVE, CORREO, PagoVisualDatos

ANCHOS = (360, 390)
ZONA_DEL_PULGAR = 0.6      # el centro del botón cae en el 40 % de abajo de la pantalla

AGREGAR_AL_CARRITO = """
    (async () => {
        const r = await fetch('/shop/cart/add', {method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({jsonrpc: '2.0', method: 'call', id: 1,
                params: {product_template_id: %(plantilla)s, product_id: %(producto)s, quantity: 1}})});
        return (await r.json()).error ? 'error' : 'ok';
    })()
"""

MEDIR = """
    (async () => {
        const esperar = (ms) => new Promise((ok) => setTimeout(ok, ms));
        for (let i = 0; i < 100 && document.body.getAttribute('is-ready') !== 'true'; i++) { await esperar(50); }
        await esperar(600);
        const caja = (el) => {
            const r = el.getBoundingClientRect();
            return {arriba: r.top, abajo: r.bottom, izquierda: r.left, derecha: r.right,
                    ancho: r.width, alto: r.height};
        };
        const botones = [...document.querySelectorAll('button[name="o_payment_submit_button"]')]
            .filter((b) => b.getClientRects().length && getComputedStyle(b).visibility !== 'hidden');
        const resumen = document.querySelector('.o_dcasa_pago_resumen_toggle');
        const cabecera = document.querySelector('.o_dcasa_pago_cabecera');
        return {
            ancho: innerWidth, alto: innerHeight, desplazable: document.documentElement.scrollWidth,
            visibles: botones.length,
            boton: botones[0] ? Object.assign(caja(botones[0]), {
                texto: botones[0].textContent.replace(/\\s+/g, ' ').trim(), apagado: botones[0].disabled,
                fuente: getComputedStyle(botones[0]).fontFamily}) : null,
            resumen: resumen ? Object.assign(caja(resumen), {
                texto: resumen.textContent.replace(/\\s+/g, ' ').trim()}) : null,
            cabecera: cabecera ? caja(cabecera) : null,
            avisos: !!document.querySelector('.o_dcasa_anuncios'),
        };
    })()
"""

ELEGIR_UN_METODO = """
    (async () => {
        const esperar = (ms) => new Promise((ok) => setTimeout(ok, ms));
        const radio = document.querySelector('input[name="o_payment_radio"]');
        radio.click();
        const boton = [...document.querySelectorAll('button[name="o_payment_submit_button"]')]
            .find((b) => b.getClientRects().length);
        for (let i = 0; i < 50 && boton.disabled; i++) { await esperar(100); }   // el JavaScript de Odoo lo enciende
        await esperar(300);
        const fila = radio.closest('[name="o_payment_option"]');
        const r = boton.getBoundingClientRect();
        const ayuda = fila.querySelector('.o_dcasa_pago_ayuda');
        return {
            elegido: radio.checked, apagado: boton.disabled, arriba: r.top, abajo: r.bottom, alto: innerHeight,
            filaResaltada: getComputedStyle(fila).boxShadow !== 'none',
            ayudaVisible: ayuda ? ayuda.getClientRects().length > 0 : null,
        };
    })()
"""

ELEGIR_TILOPAY = """
    (async () => {
        const esperar = (ms) => new Promise((ok) => setTimeout(ok, ms));
        const visibles = () => [...document.querySelectorAll('.o_dcasa_pago_nota[data-dcasa-proveedor="tilopay"]')]
            .filter((n) => n.getClientRects().length).map((n) => n.textContent.replace(/\\s+/g, ' ').trim());
        const radios = [...document.querySelectorAll('input[name="o_payment_radio"]')];
        const tilopay = radios.find((r) => r.dataset.providerCode === 'tilopay');
        const otro = radios.find((r) => r.dataset.providerCode !== 'tilopay');
        const antes = visibles();
        tilopay.click();
        await esperar(700);
        const conTilopay = visibles();
        const fila = tilopay.closest('[name="o_payment_option"]');
        const ayuda = fila.querySelector('.o_dcasa_pago_ayuda');
        const iconos = [...fila.querySelectorAll('.o_dcasa_pago_iconos img')].map((i) => i.getAttribute('src'));
        const ayudaDentro = !!ayuda && ayuda.getClientRects().length > 0;
        otro.click();
        await esperar(700);
        return {antes, conTilopay, conOtro: visibles(),
                filaConIconos: iconos.length === 2 && iconos.every((s) => s.startsWith('/payment/static/img/')),
                ayudaDentro};
    })()
"""


@tagged('post_install', '-at_install')
class TestPagoEnElCelular(PagoVisualDatos, ChromeMovilCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.preparar_pago()

    def _hasta_el_pago(self, browser):
        self.authenticate(CORREO, CLAVE, browser=browser)
        browser.navigate_to(self.base_url() + '/shop', wait_stop=True)
        self.assertTrue(browser._wait_ready(), '/shop no terminó de cargar')
        self.assertEqual(self._evaluar(browser, AGREGAR_AL_CARRITO % {
            'plantilla': self.producto.product_tmpl_id.id, 'producto': self.producto.id}), 'ok')
        browser.navigate_to(self.base_url() + '/shop/payment', wait_stop=True)
        self.assertTrue(browser._wait_ready(), '/shop/payment no terminó de cargar')
        return self.env['sale.order'].search(
            [('partner_id', '=', self.cliente.id), ('website_id', '=', self.website.id)], order='id desc', limit=1)

    def test_el_boton_de_pagar_se_ve_sin_deslizar_y_cae_en_la_zona_del_pulgar(self):
        for ancho in ANCHOS:
            with self.subTest(ancho=ancho), self._chrome_movil(ancho) as browser:
                orden = self._hasta_el_pago(browser)
                medidas = self._evaluar(browser, MEDIR)
                self.assertEqual(medidas['ancho'], ancho)
                self.assertLessEqual(medidas['desplazable'], ancho + 1,
                                     f'la página mide {medidas["desplazable"]}px: se arrastraría de lado')
                self.assertFalse(medidas['avisos'], 'sin la barra de avisos de la tienda')
                self.assertIsNotNone(medidas['cabecera'], 'cabecera mínima')
                self.assertLessEqual(medidas['cabecera']['arriba'], 1, 'la cabecera mínima va arriba de todo')
                # Un solo botón primario a la vista, entero dentro de la pantalla (sin deslizar).
                self.assertEqual(medidas['visibles'], 1, 'un solo botón primario a la vista')
                boton = medidas['boton']
                self.assertTrue(boton['texto'].startswith('Pagar'), boton['texto'])
                self.assertGreaterEqual(boton['arriba'], 0, 'el botón entra por arriba')
                self.assertLessEqual(boton['abajo'], ALTO, 'el botón se ve sin deslizar')
                self.assertGreaterEqual(boton['alto'], 51.5, 'alto de 52 px')
                self.assertGreaterEqual(boton['ancho'], ancho - 2 * 24, 'a todo el ancho de la pantalla')
                self.assertGreaterEqual((boton['arriba'] + boton['abajo']) / 2, ALTO * ZONA_DEL_PULGAR,
                                       'el botón está en la zona del pulgar (abajo)')
                self.assertIn('Inter', boton['fuente'], 'el botón va en la letra del cuerpo, no en la del titular')
                # El resumen plegable, arriba, con el monto.
                resumen = medidas['resumen']
                self.assertIsNotNone(resumen)
                self.assertLess(resumen['arriba'], ALTO / 2, 'el resumen va arriba')
                self.assertIn('Ver resumen del pedido', resumen['texto'])
                self.assertIn(f'{orden.amount_total:.2f}', resumen['texto'].replace(',', ''))
                self.assertGreaterEqual(resumen['alto'], 44, 'área táctil de 44 px o más')

    def test_al_elegir_un_metodo_el_boton_se_enciende_y_la_fila_se_resalta(self):
        with self._chrome_movil(390) as browser:
            self._hasta_el_pago(browser)
            estado = self._evaluar(browser, ELEGIR_UN_METODO)
            self.assertTrue(estado['elegido'])
            self.assertFalse(estado['apagado'], 'con un método elegido el botón se enciende')
            self.assertLessEqual(estado['abajo'], estado['alto'], 'el botón sigue a la vista')
            self.assertTrue(estado['filaResaltada'], 'la fila elegida se resalta con su borde azul')

    def test_la_linea_de_seguridad_de_tilopay_solo_sale_con_tilopay_elegido(self):
        metodo = self.env.ref('dcasa_pago_tilopay.payment_method_tilopay', raise_if_not_found=False)
        if not metodo:
            self.skipTest('dcasa_pago_tilopay no está instalado')
        proveedor = self.env.ref('dcasa_pago_tilopay.payment_provider_tilopay')
        proveedor.write({'state': 'test', 'is_published': True})
        metodo.sudo().active = True
        claves_inventadas = {
            'TILOPAY_API_KEY': 'LLAVE-DE-PRUEBA-0001-NO-ES-REAL',
            'TILOPAY_API_USER': 'USUARIO-DE-PRUEBA-0002-NO-ES-REAL',
            'TILOPAY_API_PASSWORD': 'CLAVE-DE-PRUEBA-0003-NO-ES-REAL', 'TILOPAY_ENTORNO': 'prueba'}
        with patch.dict(os.environ, claves_inventadas), self._chrome_movil(390) as browser:
            self._hasta_el_pago(browser)
            estado = self._evaluar(browser, ELEGIR_TILOPAY)
        self.assertEqual(estado['antes'], [], 'sin elegir nada, ninguna línea de seguridad a la vista')
        self.assertEqual(len(estado['conTilopay']), 1, 'con Tilopay elegido, una sola línea a la vista (la de abajo)')
        self.assertEqual(
            estado['conTilopay'][0], "Pagas en la página segura de Tilopay; D'CASA nunca ve los datos de tu tarjeta.")
        self.assertEqual(estado['conOtro'], [], 'con otro método elegido, la línea se va')
        self.assertTrue(estado['filaConIconos'], 'la fila de Tilopay lleva los íconos de Visa y Mastercard')
        self.assertTrue(estado['ayudaDentro'], 'la ayuda de Tilopay se ve DENTRO de su fila cuando está elegida')
