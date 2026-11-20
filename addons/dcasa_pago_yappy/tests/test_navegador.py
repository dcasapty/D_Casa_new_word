"""El JavaScript del botón de Yappy en Chrome de verdad, con el elemento ``<btn-yappy>`` SIMULADO.

El paquete real de Yappy (~545 KB de un tercero, con reCAPTCHA y Firebase) no se carga en las pruebas: antes de elegir
la fila se define en la página un ``btn-yappy`` falso con lo documentado (un ``div.yappy-button`` que al pulsarse se
apaga solo y dispara ``eventClick``; el método ``eventPayment``; los eventos ``eventSuccess``, ``eventError`` e
``isYappyOnline``). El servidor de Yappy también es el falso. Se comprueba lo que importa:

* el script de Yappy no se pide hasta que se elige «Yappy», y se pide UNA vez (con el anfitrión del entorno);
* clic → llamada a NUESTRA ruta → ``eventPayment`` con exactamente ``{transactionId, token, documentName}``;
* si falla, el botón se tira y se pone uno nuevo (y se puede reintentar);
* ``isYappyOnline = false`` y ``eventError`` antes de pagar dicen el motivo y no rehacen el botón en bucle;
* ``eventSuccess`` NO marca nada: la transacción sigue esperando el aviso firmado;
* si el script no carga, mensaje claro con «Escríbenos por WhatsApp».
"""
import time

from odoo.addons.website_dcasa.tests.chrome_movil import ALTO, ChromeMovilCase
from odoo.addons.website_dcasa.tests.test_pago_visual import CLAVE, CORREO, PagoVisualDatos
from odoo.tests import tagged

from .common import YappyFalso, entorno

AGREGAR_AL_CARRITO = """
    (async () => {
        const r = await fetch('/shop/cart/add', {method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({jsonrpc: '2.0', method: 'call', id: 1,
                params: {product_template_id: %(plantilla)s, product_id: %(producto)s, quantity: 1}})});
        return (await r.json()).error ? 'error' : 'ok';
    })()
"""

# Un btn-yappy de mentira con el aspecto y los eventos documentados. ``window.__yappy`` recuerda lo que pasa.
PREPARAR_EL_FALSO = """
    (() => {
        window.__yappy = {elementos: [], pagos: [], scripts: [], falla_el_script: %(falla_el_script)s};
        class FalsoYappy extends HTMLElement {
            connectedCallback() {
                this.innerHTML = '<div class="yappy-button ecommerce">Pagar con Yappy (simulado)</div>';
                this.querySelector('.yappy-button').addEventListener('click', () => {
                    this.isButtonLoading = true;
                    this.querySelector('.yappy-button').classList.add('disable-btn');
                    this.dispatchEvent(new CustomEvent('eventClick'));
                });
                window.__yappy.elementos.push(this);
            }
            eventPayment(datos) { window.__yappy.pagos.push(datos); }
        }
        const original = document.head.appendChild.bind(document.head);
        document.head.appendChild = (nodo) => {
            if (nodo.tagName === 'SCRIPT' && /yappy/.test(nodo.src || '')) {
                window.__yappy.scripts.push(nodo.src);
                if (window.__yappy.falla_el_script) {
                    setTimeout(() => nodo.dispatchEvent(new Event('error')), 20);
                } else {
                    setTimeout(() => {
                        if (!customElements.get('btn-yappy')) { customElements.define('btn-yappy', FalsoYappy); }
                    }, 20);
                }
                return nodo;
            }
            return original(nodo);
        };
        return 'listo';
    })()
"""

ESPERAR = """
    const esperar = (ms) => new Promise((ok) => setTimeout(ok, ms));
    const hasta = async (condicion, intentos = 100) => {
        for (let i = 0; i < intentos && !condicion(); i++) { await esperar(50); }
        return !!condicion();
    };
"""

ELEGIR_YAPPY = ESPERAR + """
    return (async () => {
        for (let i = 0; i < 100 && document.body.getAttribute('is-ready') !== 'true'; i++) { await esperar(50); }
        await esperar(500);
        const radios = [...document.querySelectorAll('input[name="o_payment_radio"]')];
        const yappy = radios.find((r) => r.dataset.providerCode === 'yappy');
        const otro = radios.find((r) => r.dataset.providerCode !== 'yappy');
        const antes = window.__yappy.scripts.length;
        otro.click();
        await esperar(300);
        const conOtro = window.__yappy.scripts.length;
        const botonOdoo = document.querySelector('button[name="o_payment_submit_button"]');
        const odooVisibleConOtro = !botonOdoo.classList.contains('d-none');
        yappy.click();
        const montado = await hasta(() => document.querySelector('.o_dcasa_yappy_boton btn-yappy') ||
                                          !document.querySelector('.o_dcasa_yappy_sin_script').hidden, 100);
        await esperar(400);            // Odoo termina de abrir la fila después de que el botón se pone
        const caja = yappy.closest('[name="o_payment_option"]').querySelector('.o_dcasa_yappy');
        return {
            scriptsAntes: antes, scriptsConOtro: conOtro, scriptsDespues: window.__yappy.scripts,
            odooVisibleConOtro, odooOcultoConYappy: botonOdoo.classList.contains('d-none'),
            montado: !!document.querySelector('.o_dcasa_yappy_boton btn-yappy'),
            tema: document.querySelector('btn-yappy')?.getAttribute('theme'),
            celular: caja.querySelector('input[name="o_dcasa_yappy_celular"]').value,
            cajaVisible: caja.getClientRects().length > 0,
            scriptDeLaCaja: caja.dataset.yappyScript,
            rol: caja.querySelector('.o_dcasa_yappy_boton').getAttribute('role'),
            tab: caja.querySelector('.o_dcasa_yappy_boton').getAttribute('tabindex'),
            sinScriptVisible: !caja.querySelector('.o_dcasa_yappy_sin_script').hidden,
            whatsapp: caja.querySelector('.o_dcasa_yappy_whatsapp').getAttribute('href'),
        };
    })();
"""

PULSAR = ESPERAR + """
    return (async () => {
        const antes = window.__yappy.pagos.length;
        const elemento = document.querySelector('btn-yappy');
        elemento.querySelector('.yappy-button').click();
        await hasta(
            () => window.__yappy.pagos.length > antes || !document.querySelector('.o_dcasa_yappy_mensaje').hidden, 120);
        await esperar(300);
        const mensaje = document.querySelector('.o_dcasa_yappy_mensaje');
        const actual = document.querySelector('btn-yappy');
        return {
            pagos: window.__yappy.pagos, mensaje: mensaje.hidden ? '' : mensaje.textContent.trim(),
            tipoDelMensaje: mensaje.dataset.tipo, elementos: window.__yappy.elementos.length,
            elViejoSigueEnLaPagina: elemento.isConnected, hayBotonNuevo: !!actual && actual !== elemento,
            apagado: actual ? actual.querySelector('.yappy-button').classList.contains('disable-btn') : null,
        };
    })();
"""


@tagged('post_install', '-at_install')
class TestElBotonDeYappyEnElNavegador(PagoVisualDatos, ChromeMovilCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.preparar_pago()
        cls.proveedor = cls.env.ref('dcasa_pago_yappy.payment_provider_yappy')
        cls.proveedor.write({'state': 'test', 'is_published': True})
        cls.env.ref('dcasa_pago_yappy.payment_method_yappy').sudo().active = True
        cls.cliente.phone = '+507 6000-0505'
        cls.producto_id, cls.plantilla_id = cls.producto.id, cls.producto.product_tmpl_id.id

    def setUp(self):
        super().setUp()
        self.addCleanup(entorno().start().stop)

    def _hasta_el_pago(self, browser, falla_el_script='false'):
        self.authenticate(CORREO, CLAVE, browser=browser)
        browser.navigate_to(self.base_url() + '/shop', wait_stop=True)
        self.assertTrue(browser._wait_ready(), '/shop no terminó de cargar')
        self.assertEqual(self._evaluar(browser, AGREGAR_AL_CARRITO % {
            'plantilla': self.plantilla_id, 'producto': self.producto_id}), 'ok')
        browser.navigate_to(self.base_url() + '/shop/payment', wait_stop=True)
        self.assertTrue(browser._wait_ready(), '/shop/payment no terminó de cargar')
        self._correr(browser, ESPERAR + """
            return (async () => {
                await hasta(() => document.body.getAttribute('is-ready') === 'true', 200);
                await esperar(400);
                return 1;
            })();""")
        self.assertEqual(self._evaluar(browser, PREPARAR_EL_FALSO % {'falla_el_script': falla_el_script}), 'listo')
        return self.env['sale.order'].sudo().search(
            [('partner_id', '=', self.cliente.id), ('website_id', '=', self.website.id)], order='id desc', limit=1)

    def _correr(self, browser, codigo):
        return self._evaluar(browser, '(() => {' + codigo + '})()')

    def _elegir(self, browser):
        return self._correr(browser, ELEGIR_YAPPY)

    def _pulsar(self, browser):
        return self._correr(browser, PULSAR)

    def _transacciones(self, orden):
        self.env.invalidate_all()
        return self.env['payment.transaction'].sudo().search([('sale_order_ids', 'in', orden.ids)], order='id')

    # ---------------------------------------------------------------------------------------------------------------

    def test_el_script_se_pide_solo_al_elegir_yappy_una_vez_y_el_boton_va_con_su_celular(self):
        with self._chrome_movil(390) as browser:
            self._hasta_el_pago(browser)
            estado = self._elegir(browser)
        self.assertEqual(estado['scriptsAntes'], 0, 'al abrir el paso de pago no se pide nada de Yappy')
        self.assertEqual(estado['scriptsConOtro'], 0, 'elegir otro método tampoco')
        self.assertEqual(len(estado['scriptsDespues']), 1, 'al elegir Yappy se pide UNA vez')
        self.assertEqual(estado['scriptsDespues'][0], 'https://bt-cdn-uat.yappycloud.com/v1/cdn/web-component-btn-yappy.js',
                         'en «Modo de prueba» el script del servidor de pruebas de Yappy')
        self.assertEqual(estado['scriptDeLaCaja'], estado['scriptsDespues'][0])
        self.assertTrue(estado['montado'], 'el botón de Yappy se puso')
        self.assertEqual(estado['tema'], 'dark', 'el tema de Yappy que cumple contraste AA con margen')
        self.assertTrue(estado['odooVisibleConOtro'], 'con otro método, el botón «Pagar» de Odoo sigue')
        self.assertTrue(estado['odooOcultoConYappy'], 'con Yappy elegido paga el botón de Yappy, no el de Odoo')
        self.assertEqual(estado['celular'], '6000 0505', 'viene escrito con el celular del pedido')
        self.assertTrue(estado['cajaVisible'])
        self.assertEqual((estado['rol'], estado['tab']), ('button', '0'), 'accesible con teclado')
        self.assertFalse(estado['sinScriptVisible'])

    def test_clic_llama_a_nuestra_ruta_y_despues_a_eventPayment_con_los_tres_valores(self):
        with self._chrome_movil(390) as browser, YappyFalso() as yappy:
            orden = self._hasta_el_pago(browser)
            self._elegir(browser)
            resultado = self._pulsar(browser)
        self.assertEqual(len(resultado['pagos']), 1)
        self.assertEqual(set(resultado['pagos'][0]), {'transactionId', 'token', 'documentName'},
                         'a eventPayment solo van esos tres valores')
        self.assertEqual(resultado['tipoDelMensaje'], 'info')
        self.assertIn('Abre tu app de Yappy', resultado['mensaje'])
        self.assertEqual(len(yappy.llamadas), 2, 'nuestro servidor hizo los dos POST')
        txs = self._transacciones(orden)
        self.assertEqual(len(txs), 1)
        self.assertEqual(txs.state, 'pending', 'el botón de Yappy no marca nada')
        self.assertEqual(txs.dcasa_yappy_celular, '60000505')
        self.assertEqual(txs.operation, 'online_direct')

    def test_eventSuccess_no_marca_ningun_pago(self):
        with self._chrome_movil(390) as browser, YappyFalso():
            orden = self._hasta_el_pago(browser)
            self._elegir(browser)
            self._pulsar(browser)
            self._correr(browser, """
                document.querySelector('btn-yappy').dispatchEvent(
                    new CustomEvent('eventSuccess', {detail: 'TX-DEL-NAVEGADOR'}));
                return 'ok';""")
            time.sleep(2.5)         # el navegador pasa a «Estado del pago» y pregunta; nada lo marca pagado
        txs = self._transacciones(orden)
        self.assertEqual(txs.state, 'pending', 'solo el aviso firmado de Yappy paga un pedido')
        self.assertFalse(txs.payment_id)
        self.assertNotEqual(orden.state, 'sale')

    def test_si_algo_falla_el_boton_se_tira_y_se_puede_reintentar(self):
        with self._chrome_movil(390) as browser, YappyFalso() as yappy:
            orden = self._hasta_el_pago(browser)
            self._elegir(browser)
            yappy.no_registrados.add('60000505')
            falla = self._pulsar(browser)
            self.assertEqual(falla['pagos'], [])
            self.assertEqual(falla['tipoDelMensaje'], 'error')
            self.assertIn('no está registrado en Yappy', falla['mensaje'])
            self.assertTrue(falla['hayBotonNuevo'], 'el botón que falló se tira y se pone uno nuevo')
            self.assertFalse(falla['elViejoSigueEnLaPagina'])
            self.assertFalse(falla['apagado'], 'el botón nuevo nace limpio (sin disable-btn)')
            yappy.no_registrados.clear()
            bien = self._pulsar(browser)
        self.assertEqual(len(bien['pagos']), 1, 'el reintento funciona')
        txs = self._transacciones(orden)
        self.assertEqual(txs.mapped('state'), ['error', 'pending'], 'cada intento fue su propia transacción')

    def test_un_celular_malo_se_dice_antes_de_crear_nada_y_el_boton_se_rehace(self):
        with self._chrome_movil(390) as browser, YappyFalso() as yappy:
            orden = self._hasta_el_pago(browser)
            self._elegir(browser)
            self._correr(
                browser, "document.querySelector('input[name=\"o_dcasa_yappy_celular\"]').value = '123'; return 1;")
            resultado = self._pulsar(browser)
        self.assertEqual(resultado['pagos'], [])
        self.assertIn('Escribe el celular de tu app de Yappy', resultado['mensaje'])
        self.assertTrue(resultado['hayBotonNuevo'])
        self.assertEqual(yappy.llamadas, [])
        self.assertFalse(self._transacciones(orden), 'sin transacción: el intento ni empezó')

    def test_yappy_fuera_de_linea_dice_por_que_y_no_rehace_el_boton_en_bucle(self):
        with self._chrome_movil(390) as browser, YappyFalso():
            self._hasta_el_pago(browser)
            self._elegir(browser)
            estado = self._correr(browser, ESPERAR + """
                return (async () => {
                    const boton = document.querySelector('btn-yappy');
                    boton.dispatchEvent(new CustomEvent('isYappyOnline', {detail: false}));
                    boton.dispatchEvent(new CustomEvent('eventError', {detail: 'Failed to fetch'}));
                    await esperar(600);
                    const mensaje = document.querySelector('.o_dcasa_yappy_mensaje');
                    const sin = document.querySelector('.o_dcasa_yappy_sin_script');
                    return {mensaje: mensaje.textContent.trim(), tipo: mensaje.dataset.tipo,
                            elementos: window.__yappy.elementos.length,
                            mismo: document.querySelector('btn-yappy') === boton, sinVisible: !sin.hidden,
                            whatsapp: sin.querySelector('.o_dcasa_yappy_whatsapp').href,
                            motivoVisible: !sin.querySelector('p').hidden};
                })();""")
        self.assertIn('Yappy no está disponible', estado['mensaje'], 'se dice POR QUÉ el botón está apagado')
        self.assertNotIn('no se completó', estado['mensaje'], 'nadie intentó pagar: no es un pago fallido')
        self.assertEqual(estado['elementos'], 1, 'sin bucle: el botón no se rehizo')
        self.assertTrue(estado['mismo'])
        self.assertTrue(estado['sinVisible'], 'el camino alterno a la vista')
        self.assertIn('wa.me', estado['whatsapp'])
        self.assertFalse(estado['motivoVisible'], 'no dice «no cargó» si lo que pasa es que Yappy está fuera de línea')

    def test_un_error_despues_de_pagar_dice_que_paso_y_deja_reintentar(self):
        with self._chrome_movil(390) as browser, YappyFalso():
            self._hasta_el_pago(browser)
            self._elegir(browser)
            self._pulsar(browser)
            estado = self._correr(browser, ESPERAR + """
                return (async () => {
                    const viejo = document.querySelector('btn-yappy');
                    viejo.dispatchEvent(new CustomEvent('eventError', {detail: 'CANCELLED'}));
                    await esperar(400);
                    const mensaje = document.querySelector('.o_dcasa_yappy_mensaje');
                    return {mensaje: mensaje.textContent.trim(), nuevo: document.querySelector('btn-yappy') !== viejo,
                            elementos: window.__yappy.elementos.length};
                })();""")
        self.assertIn('Cancelaste el pago en la app de Yappy', estado['mensaje'])
        self.assertTrue(estado['nuevo'])
        self.assertEqual(estado['elementos'], 2)

    def test_si_el_script_no_carga_hay_mensaje_con_whatsapp_y_se_puede_reintentar(self):
        with self._chrome_movil(390) as browser:
            self._hasta_el_pago(browser, falla_el_script='true')
            estado = self._elegir(browser)
            despues = self._correr(browser, ESPERAR + """
                return (async () => {
                    window.__yappy.falla_el_script = false;
                    document.querySelector('.o_dcasa_yappy_reintentar').click();
                    const ok = await hasta(() => document.querySelector('.o_dcasa_yappy_boton btn-yappy'), 100);
                    return {montado: !!ok, scripts: window.__yappy.scripts.length,
                            sinVisible: !document.querySelector('.o_dcasa_yappy_sin_script').hidden};
                })();""")
        self.assertFalse(estado['montado'], 'sin script no hay botón')
        self.assertTrue(estado['sinScriptVisible'], 'se le dice con palabras que no cargó')
        self.assertIn('wa.me', estado['whatsapp'], 'y se le ofrece «Escríbenos por WhatsApp»')
        self.assertTrue(despues['montado'], '«Volver a intentarlo» pide el script otra vez y pone el botón')
        self.assertEqual(despues['scripts'], 2)
        self.assertFalse(despues['sinVisible'])

    def test_el_teclado_enter_en_la_caja_pulsa_el_boton_de_yappy(self):
        with self._chrome_movil(390) as browser, YappyFalso() as yappy:
            self._hasta_el_pago(browser)
            self._elegir(browser)
            resultado = self._correr(browser, ESPERAR + """
                return (async () => {
                    const caja = document.querySelector('.o_dcasa_yappy_boton');
                    caja.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true, cancelable: true}));
                    await hasta(() => window.__yappy.pagos.length > 0, 120);
                    return {pagos: window.__yappy.pagos.length};
                })();""")
        self.assertEqual(resultado['pagos'], 1)
        self.assertEqual(len(yappy.llamadas), 2)

    def test_la_validacion_del_celular_del_navegador_es_la_misma_del_servidor(self):
        from odoo.addons.dcasa_pago_yappy.models import yappy_api as api  # noqa: PLC0415
        casos = ['6000 0101', '6000-0101', '+507 6000-0101', '507 60000101', '00507 6000 0101', '123', '1000 0101',
                 '0000 0101', 'abcdefgh', '+1 6000 0101', '60000101 ', '', '6' * 41, '(6000) 0101']
        with self._chrome_movil(390) as browser:
            self._hasta_el_pago(browser)
            desde_js = self._evaluar(browser, """
                (async () => {
                    const modulo = odoo.loader.modules.get('@dcasa_pago_yappy/interactions/payment_form');
                    return __CASOS__.map((c) => modulo.celularDeYappy(c));
                })()""".replace('__CASOS__', repr(casos).replace("'", '"')))
        self.assertEqual(desde_js, [api.celular_de_yappy(caso) for caso in casos])

    def test_en_el_celular_la_fila_y_el_boton_caben_sin_arrastrar_la_pagina_de_lado(self):
        """Un solo Chrome, dos anchos: se cambia el tamaño de la pantalla emulada y se vuelve a medir (un segundo Chrome
        en la misma prueba se quedaba sin arrancar el JavaScript de la página en una base recién instalada)."""
        with self._chrome_movil(360) as browser:
            self._hasta_el_pago(browser)
            self._elegir(browser)
            for ancho in (360, 390):
                with self.subTest(ancho=ancho):
                    if ancho != 360:
                        browser._websocket_request('Emulation.setDeviceMetricsOverride', params={
                            'width': ancho, 'height': ALTO, 'deviceScaleFactor': 2, 'mobile': True})
                    medidas = self._correr(browser, ESPERAR + """
                        return (async () => {
                            const caja = document.querySelector('.o_dcasa_yappy');
                            // La caja se abre con una animación: se mide cuando el campo ya tiene su alto.
                            await hasta(() => caja.querySelector('input').getBoundingClientRect().height > 0, 100);
                            await esperar(400);
                            const r = caja.getBoundingClientRect();
                            const campo = caja.querySelector('input').getBoundingClientRect();
                            const ocultos = [];
                            for (let nodo = caja; nodo && nodo !== document.body; nodo = nodo.parentElement) {
                                const estilo = getComputedStyle(nodo);
                                const sinCaja = nodo.getClientRects().length === 0;
                                if (estilo.display === 'none' || estilo.visibility === 'hidden' || sinCaja) {
                                    ocultos.push(nodo.tagName + '.' + nodo.className);
                                }
                            }
                            return {desplazable: document.documentElement.scrollWidth, ancho: innerWidth,
                                    cajaDerecha: r.right, campoAlto: campo.height, campoAncho: campo.width,
                                    tamanoLetra: parseFloat(getComputedStyle(caja.querySelector('input')).fontSize),
                                    ocultos: ocultos};
                        })();""")
                    self.assertEqual(medidas['ancho'], ancho)
                    self.assertLessEqual(medidas['desplazable'], ancho + 1)
                    self.assertLessEqual(medidas['cajaDerecha'], ancho)
                    self.assertGreaterEqual(medidas['campoAlto'], 47.5, f'campo de 48 px: {medidas}')
                    self.assertGreaterEqual(medidas['tamanoLetra'], 16, 'con 16 px el celular no hace zoom al escribir')
        self.assertGreater(ALTO, 0)

    # --------------------------------------------------------------------------------------------------------------
    # La ventana de Yappy y lo que pasa a su alrededor (medido con el componente REAL el 2026-11-20; aquí, con una
    # ventana simulada que tiene la misma estructura y las mismas reglas de posición: un ``<dialog open>`` con
    # ``position: fixed; z-index: 10`` junto al botón, dentro de la misma caja, y un fondo ``fixed; z-index: 5``).
    # --------------------------------------------------------------------------------------------------------------

    def test_la_ventana_de_yappy_queda_por_encima_del_resumen_fijo_y_cabe_en_un_celular_acostado(self):
        with self._chrome_movil(1280) as browser:
            self._hasta_el_pago(browser)
            self._elegir(browser)
            self._correr(browser, """
                const estilo = document.createElement('style');
                estilo.textContent = '.yp-dialogo{width:min(90%,580px);height:590px;padding:0;border:0;' +
                    'position:fixed;inset:0;z-index:10;background:#f9fdff}' +
                    '.yp-fondo{width:100vw;height:100vh;background:#000;opacity:.3;z-index:5;position:fixed;inset:0}';
                document.head.appendChild(estilo);
                document.querySelector('btn-yappy').insertAdjacentHTML('afterbegin',
                    '<div class="yappy-backdrop yp-fondo"></div>');
                document.querySelector('.o_dcasa_yappy_boton').insertAdjacentHTML('beforeend',
                    '<app-dialog><dialog class="yp-dialogo" open><div class="close-icon">x</div>' +
                    'Completa el pago en Yappy</dialog></app-dialog>');
                return 1;""")
            en_la_computadora = self._correr(browser, ESPERAR + """
                return (async () => {
                    await esperar(300);
                    const d = document.querySelector('dialog').getBoundingClientRect();
                    const p = document.querySelector('.o_total_card').getBoundingClientRect();
                    const x1 = Math.max(d.left, p.left), x2 = Math.min(d.right, p.right);
                    const y1 = Math.max(d.top, p.top), y2 = Math.min(d.bottom, p.bottom);
                    const dueño = (x, y) => { const e = document.elementFromPoint(x, y);
                        return !!(e && (e.closest('app-dialog') || e.classList.contains('yappy-backdrop'))); };
                    return {cruce: [x2 - x1, y2 - y1], enElCruce: dueño((x1 + x2) / 2, (y1 + y2) / 2),
                            esquinaDeCerrar: dueño(d.right - 30, d.top + 30),
                            cabecera: dueño(100, 20), ancho: innerWidth};
                })();""")
            browser._websocket_request('Emulation.setDeviceMetricsOverride', params={
                'width': 844, 'height': 390, 'deviceScaleFactor': 2, 'mobile': True})
            acostado = self._correr(browser, ESPERAR + """
                return (async () => {
                    await esperar(400);
                    const d = document.querySelector('dialog').getBoundingClientRect();
                    return {arriba: d.top, abajo: d.bottom, alto: innerHeight};
                })();""")
        self.assertEqual(en_la_computadora['ancho'], 1280)
        self.assertGreater(en_la_computadora['cruce'][0], 20,
                           f'la prueba necesita que el resumen cruce la ventana: {en_la_computadora}')
        self.assertTrue(en_la_computadora['enElCruce'],
                        'el resumen fijo de la derecha NO puede tapar la ventana de Yappy')
        self.assertTrue(en_la_computadora['esquinaDeCerrar'],
                        'la esquina del botón de cerrar de Yappy tiene que poder pulsarse')
        self.assertTrue(en_la_computadora['cabecera'], 'ni la cabecera de la tienda queda sin oscurecer')
        self.assertGreaterEqual(acostado['arriba'], 0, 'en un celular acostado la ventana no se corta por arriba')
        self.assertLessEqual(acostado['abajo'], acostado['alto'], 'ni por abajo')
