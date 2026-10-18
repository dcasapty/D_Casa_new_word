"""El píxel en Chrome de verdad (diseño §5.5.8). Un `fbq` falso, definido antes de que cargue la página, anota cada
llamada en sessionStorage (sobrevive a la navegación). Ninguna petición sale a Meta: las de fuera del sitio pasan por
``fetch_proxy`` y aquí se anotan para comprobar que nadie pidió nada a facebook sin consentimiento.

* Sin aceptar las cookies: no se llama a nada ni se pide fbevents.js.
* Al aceptar: init, PageView y después lo que esperaba en la cola (ViewContent con el id de la variante).
* Con las cookies aceptadas: AddToCart por los dos caminos, Search, Contact (WhatsApp) e InitiateCheckout.
* Nunca Purchase.
"""
import contextlib
import json
import re
from unittest.mock import patch

from odoo import Command
from odoo.addons.website_dcasa.models.black_weekend import PARAM_ACTIVO, PARAM_FIN, PARAM_INICIO
from odoo.tests import tagged
from odoo.tests.common import HOST, ChromeBrowser

from .test_render import SitioMetaCase

FBQ_FALSO = """
(() => {
    const clave = 'dcasaFbqFalso';
    const guardar = (args) => {
        try {
            const lista = JSON.parse(sessionStorage.getItem(clave) || '[]');
            lista.push(args);
            sessionStorage.setItem(clave, JSON.stringify(lista));
        } catch (e) { /* about:blank */ }
    };
    window.fbq = function () { guardar(Array.from(arguments)); };
})();
"""
ESPERAR_LISTA = """
    const esperar = (ms) => new Promise((ok) => setTimeout(ok, ms));
    for (let i = 0; i < 200 && document.body.getAttribute('is-ready') !== 'true'; i++) { await esperar(50); }
    await esperar(400);
    const llamadas = () => JSON.parse(sessionStorage.getItem('dcasaFbqFalso') || '[]');
"""
RE_EVENT_ID = r'^{}-[0-9a-f]{{8}}-[0-9a-f]{{4}}-4[0-9a-f]{{3}}-[89ab][0-9a-f]{{3}}-[0-9a-f]{{12}}$'
ACEPTADAS = json.dumps({'required': True, 'optional': True}, separators=(',', ':'))


@tagged('post_install', '-at_install')
class TestPixelNavegador(SitioMetaCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ICP.set_param(PARAM_ACTIVO, '1')       # la tarjeta de Black Weekend de la portada lleva el formulario
        cls.ICP.set_param(PARAM_INICIO, '')
        cls.ICP.set_param(PARAM_FIN, '')
        categoria = cls.env.ref('website_dcasa.public_category_recamaras')
        cls.lampara = cls.env['product.template'].create({
            'name': 'LAMPARA META NAVEGADOR', 'list_price': 49.99, 'is_published': True, 'type': 'consu',
            'is_storable': False, 'sale_ok': True, 'taxes_id': [Command.clear()],
            'public_categ_ids': [Command.set(categoria.ids)], 'dcasa_black_weekend': True})

    def setUp(self):
        super().setUp()
        self.externas = []
        self.encender_pixel()

    def fetch_proxy(self, url):
        self.externas.append(url)
        if 'connect.facebook.net' in url:
            return self.make_fetch_proxy_response('/* fbevents de prueba: no hace nada */')
        return super().fetch_proxy(url)

    @contextlib.contextmanager
    def _chrome(self, fbq_falso=True, aceptadas=False, login=None, clave=None):
        browser = ChromeBrowser(self, headless=True)
        with self.allow_requests(browser=browser), contextlib.ExitStack() as atexit:
            atexit.callback(self._wait_remaining_requests)
            atexit.enter_context(browser.cleanup)
            if 'bus.bus' in self.env.registry:
                from odoo.addons.bus.websocket import CloseCode, WebsocketConnectionHandler, _kick_all  # noqa: PLC0415
                atexit.callback(_kick_all, CloseCode.KILL_NOW)
                atexit.enter_context(patch.object(
                    WebsocketConnectionHandler, 'websocket_allowed', return_value=True))
            self.authenticate(login, clave or login, browser=browser)
            self.cr.flush()
            self.cr.clear()
            if fbq_falso:
                browser._websocket_request('Page.addScriptToEvaluateOnNewDocument', params={'source': FBQ_FALSO})
            if aceptadas:
                browser.set_cookie('website_cookies_bar', ACEPTADAS, '/', HOST)
            yield browser

    def _abrir(self, browser, ruta):
        browser.navigate_to(self.base_url() + ruta, wait_stop=True)
        self.assertTrue(browser._wait_ready(), f'{ruta} no terminó de cargar')

    def _evaluar(self, browser, expresion, timeout=90):
        res = browser._websocket_request('Runtime.evaluate', params={
            'expression': expresion, 'awaitPromise': True, 'returnByValue': True}, timeout=timeout)
        resultado = res['result']
        self.assertNotEqual(resultado.get('subtype'), 'error', f'JavaScript falló: {res}')
        return resultado.get('value')

    def _sin_facebook(self):
        self.assertFalse([u for u in self.externas if 'facebook' in u], 'Nadie le pidió nada a Meta')

    def _nunca_purchase(self, llamadas):
        self.assertFalse([c for c in llamadas if len(c) > 1 and c[1] == 'Purchase'], 'El píxel nunca manda Purchase')

    def _eventos(self, llamadas, nombre):
        return [c for c in llamadas if c[:2] == ['track', nombre]]

    # ------------------------------------------------------------------

    def test_sin_aceptar_no_se_llama_nada_y_al_aceptar_pageview_y_viewcontent(self):
        variante = self.variante_mostrada()
        with self._chrome() as browser:
            self._abrir(browser, self.sofa.website_url)
            r = self._evaluar(browser, '(async () => {' + ESPERAR_LISTA + """
                const antes = llamadas();
                const scripts = [...document.scripts].filter((s) => (s.src || '').includes('facebook')).length;
                const pixel = document.querySelector('[data-dcasa-meta-pixel]')?.dataset.dcasaMetaPixel;
                const boton = document.querySelector('#cookies-consent-all');
                if (!boton) { return { sinAviso: true, antes, pixel }; }
                boton.click();
                await esperar(300);
                return { antes, scripts, pixel, despues: llamadas() };
            })()""")
        self.assertFalse(r.get('sinAviso'), f'No apareció el aviso de cookies: {r}')
        self.assertEqual(r['pixel'], self.ICP.get_param('dcasa_meta.pixel_id'))
        self.assertEqual(r['antes'], [], 'Sin aceptar las cookies no se llama a fbq')
        self.assertEqual(r['scripts'], 0)
        despues = r['despues']
        self.assertEqual(despues[0], ['set', 'autoConfig', False, r['pixel']],
                         'Sin la configuración automática de Meta (ni clics ni datos de la página), antes de init')
        self.assertEqual(despues[1], ['init', r['pixel']])
        self.assertEqual(despues[2][:2], ['track', 'PageView'])
        self.assertRegex(despues[2][3]['eventID'], RE_EVENT_ID.format('PageView'))
        vista = self._eventos(despues, 'ViewContent')
        self.assertEqual(len(vista), 1)
        self.assertEqual(vista[0][2]['content_ids'], [str(variante.id)])
        self.assertEqual(vista[0][2]['content_type'], 'product')
        self.assertEqual(vista[0][2]['value'], 400.0)
        self.assertRegex(vista[0][3]['eventID'], RE_EVENT_ID.format('ViewContent'))
        self.assertLess(despues.index(vista[0]), len(despues))
        self._nunca_purchase(despues)
        self._sin_facebook()

    def test_solo_las_necesarias_descarta_la_cola(self):
        with self._chrome() as browser:
            self._abrir(browser, self.sofa.website_url)
            r = self._evaluar(browser, '(async () => {' + ESPERAR_LISTA + """
                document.querySelector('#cookies-consent-essential').click();
                await esperar(300);
                document.querySelector('a[href*="wa.me/"], a[href^="/whatsapp"]')?.addEventListener(
                    'click', (ev) => ev.preventDefault(), { once: true });
                document.querySelector('a[href*="wa.me/"], a[href^="/whatsapp"]')?.click();
                await esperar(200);
                return llamadas();
            })()""")
        self.assertEqual(r, [], 'Con «Solo las necesarias» no se llama a fbq nunca')
        self._sin_facebook()

    def test_con_las_cookies_aceptadas_agregar_buscar_y_whatsapp(self):
        variante_bw = self.lampara.product_variant_id
        with self._chrome(aceptadas=True) as browser:
            # Portada: «Agregar» de la tarjeta de Black Weekend (formulario normal) y el botón de WhatsApp.
            self._abrir(browser, '/')
            portada = self._evaluar(browser, '(async () => {' + ESPERAR_LISTA + """
                const forma = document.querySelector('form[action="/dcasa/carrito/agregar"][data-dcasa-meta-id]');
                if (!forma) { return { sinFormulario: true }; }
                document.addEventListener('submit', (ev) => ev.preventDefault());
                document.addEventListener('click', (ev) => {
                    if (ev.target.closest('a')) { ev.preventDefault(); }
                }, true);
                forma.querySelector('button[type=submit]').click();
                await esperar(100);
                document.querySelector('a[href*="wa.me/"], a[href^="/whatsapp"]').click();
                await esperar(100);
                return { id: forma.dataset.dcasaMetaId, llamadas: llamadas() };
            })()""")
            self.assertFalse(portada.get('sinFormulario'), 'La portada no trae el formulario «Agregar» con el id')
            # Tienda con búsqueda: Search y «Agregar al carrito» de Odoo (add_to_cart_event).
            self._abrir(browser, '/shop?search=' + 'MESA META RENDER'.replace(' ', '+'))
            tienda = self._evaluar(browser, '(async () => {' + ESPERAR_LISTA + """
                const boton = document.querySelector('#products_grid .o_wsale_product_btn .a-submit');
                if (!boton) { return { sinBoton: true, llamadas: llamadas() }; }
                boton.click();
                for (let i = 0; i < 100; i++) {
                    if (llamadas().some((c) => c[1] === 'AddToCart' && c[2].content_ids[0] === MESA)) { break; }
                    await esperar(100);
                }
                return { llamadas: llamadas() };
            })()""".replace('MESA', json.dumps(str(self.mesa.id))))
        self.assertEqual(portada['id'], str(variante_bw.id))
        llamadas = tienda['llamadas']
        self.assertEqual(llamadas[0][:3], ['set', 'autoConfig', False])
        self.assertEqual(llamadas[1][0], 'init')
        agregados = self._eventos(llamadas, 'AddToCart')
        self.assertEqual(agregados[0][2]['content_ids'], [str(variante_bw.id)])
        self.assertEqual(agregados[0][2]['contents'], [{'id': str(variante_bw.id), 'quantity': 1}])
        self.assertRegex(agregados[0][3]['eventID'], RE_EVENT_ID.format('AddToCart'))
        self.assertEqual(len(self._eventos(llamadas, 'Contact')), 1, 'El clic en WhatsApp es un Contact')
        busqueda = self._eventos(llamadas, 'Search')
        self.assertEqual(busqueda[0][2], {'search_string': 'MESA META RENDER'})
        self.assertFalse(tienda.get('sinBoton'), 'La tienda no trae el botón «Agregar al carrito»')
        self.assertEqual(len(agregados), 2, f'AddToCart por los dos caminos: {agregados}')
        self.assertEqual(agregados[1][2]['content_ids'], [str(self.mesa.id)])
        self.assertEqual(agregados[1][2]['contents'][0]['id'], str(self.mesa.id))
        self._nunca_purchase(llamadas)
        self._sin_facebook()

    def test_initiate_checkout_con_los_ids_del_carrito(self):
        with self._chrome(aceptadas=True, login=self.cliente.login, clave='clave-cliente-meta-123') as browser:
            # El carrito se llena desde el mismo navegador (dentro de Chrome no se puede usar el opener de la prueba).
            self._abrir(browser, '/shop')
            self._evaluar(browser, '''(async () => {
                const r = await fetch('/shop/cart/add', {method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({jsonrpc: '2.0', method: 'call', params: {
                        product_template_id: PLANTILLA, product_id: VARIANTE, quantity: 2}})});
                return (await r.json()).result ? true : false;
            })()'''.replace('PLANTILLA', str(self.mesa.product_tmpl_id.id)).replace('VARIANTE', str(self.mesa.id)))
            self._abrir(browser, '/shop/checkout')
            r = self._evaluar(browser, '(async () => {' + ESPERAR_LISTA + """
                return { llamadas: llamadas(), pagina: location.pathname };
            })()""")
        self.assertEqual(r['pagina'], '/shop/checkout')
        inicio = self._eventos(r['llamadas'], 'InitiateCheckout')
        self.assertEqual(len(inicio), 1)
        self.assertEqual(inicio[0][2]['content_ids'], [str(self.mesa.id)])
        self.assertEqual(inicio[0][2]['num_items'], 2)
        self.assertEqual(inicio[0][2]['value'], 240.0)
        self._nunca_purchase(r['llamadas'])

    def test_sin_fbq_falso_el_pixel_solo_se_pide_despues_de_aceptar(self):
        with self._chrome(fbq_falso=False) as browser:
            self._abrir(browser, self.sofa.website_url)
            antes = self._evaluar(browser, '(async () => {' + ESPERAR_LISTA + """
                return {
                    fbq: typeof window.fbq,
                    scripts: [...document.scripts].filter((s) => (s.src || '').includes('facebook')).length,
                };
            })()""")
            externas_antes = list(self.externas)
            despues = self._evaluar(browser, """(async () => {
                const esperar = (ms) => new Promise((ok) => setTimeout(ok, ms));
                document.querySelector('#cookies-consent-all').click();
                for (let i = 0; i < 50 && !window.fbq; i++) { await esperar(100); }
                await esperar(500);
                return (window.fbq?.queue || []).map((a) => Array.from(a).slice(0, 2));
            })()""")
        self.assertEqual(antes, {'fbq': 'undefined', 'scripts': 0}, 'Sin aceptar no existe fbq ni el script')
        self.assertFalse([u for u in externas_antes if 'facebook' in u], 'Sin aceptar no se pidió nada a Meta')
        self.assertTrue([u for u in self.externas if re.search(r'connect\.facebook\.net/.+/fbevents\.js', u)],
                        f'Al aceptar se pide fbevents.js aunque el vigilante de Odoo esté activo: {self.externas}')
        self.assertEqual(despues[0], ['set', 'autoConfig'])
        self.assertEqual(despues[1], ['init', self.ICP.get_param('dcasa_meta.pixel_id')])
        self.assertIn(['track', 'PageView'], despues)
        self.assertIn(['track', 'ViewContent'], despues)
