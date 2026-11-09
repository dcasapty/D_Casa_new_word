"""El enlace para choferes en el navegador, como lo abre un chofer en su celular (sin usuario de Odoo).

* A 390 px: busca, ve el precio y la ruta, y en ningún lado la palabra «km»; 16 px de margen y sin scroll de lado.
* El bug de siempre («antes de crear una nueva página piensa en el bug de que no se puede hacer scroll»): la página baja
  con el dedo y con la rueda de verdad (eventos por el protocolo de Chrome, no ``scrollTop``).
* «Usar mi ubicación»: con permiso, los lugares más cercanos con su distancia; sin permiso, lo dice en palabras
  sencillas."""
import contextlib
import json

from odoo.tests import HttpCase, tagged
from odoo.tests.common import ChromeBrowser

from ..controllers import choferes as ruta
from ..motor import choferes
from .test_choferes import ChoferesComun

ESPERAR = """
    const esperar = async (fn, que, intentos = 150) => {
        for (let i = 0; i < intentos; i++) {
            const r = fn();
            if (r) { return r; }
            await new Promise((ok) => setTimeout(ok, 100));
        }
        throw new Error('No apareció: ' + que);
    };
    const lugares = () => [...document.querySelectorAll('.lugar')];
    const escribir = (texto) => {
        const q = document.querySelector('.q');
        q.value = texto;
        q.dispatchEvent(new Event('input', { bubbles: true }));
    };
"""

MEDIR = """(() => {
    const raiz = document.scrollingElement;
    const q = document.querySelector('.q').getBoundingClientRect();
    return {scroll: window.scrollY, alto: raiz.scrollHeight, visible: window.innerHeight,
            ancho: raiz.scrollWidth, anchoVisible: window.innerWidth, izquierda: q.left,
            derecha: window.innerWidth - q.right, desborde: getComputedStyle(document.body).overflowY,
            desbordeHtml: getComputedStyle(document.documentElement).overflowY};
})()"""


@tagged('post_install', '-at_install')
class TestChoferesEnElNavegador(ChoferesComun, HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.preparar(cls.env)
        cls.tarifa_g.action_aprobar()

    def setUp(self):
        super().setUp()
        ruta.reiniciar_limite()
        self.addCleanup(ruta.reiniciar_limite)

    @contextlib.contextmanager
    def _chrome(self, ancho, alto, tactil=False):
        """Chrome como en ``browser_js`` pero sin sesión (el chofer no tiene usuario), devolviendo el navegador para
        mandarle toques y la rueda de verdad."""
        self.browser_size = f'{ancho}x{alto}'
        self.touch_enabled = tactil
        browser = ChromeBrowser(self, headless=True)
        with self.allow_requests(browser=browser), contextlib.ExitStack() as atexit:
            atexit.callback(self._wait_remaining_requests)
            atexit.enter_context(browser.cleanup)
            self.cr.flush()
            self.cr.clear()
            if tactil:
                browser._websocket_request('Emulation.setTouchEmulationEnabled', params={
                    'enabled': True, 'maxTouchPoints': 5})
                browser._websocket_request('Emulation.setDeviceMetricsOverride', params={
                    'mobile': True, 'width': ancho, 'height': alto, 'deviceScaleFactor': 2})
            browser.navigate_to(f'{self.base_url()}/envios/choferes/{self.token}', wait_stop=True)
            yield browser

    def _js(self, browser, expresion, timeout=60):
        res = browser._websocket_request('Runtime.evaluate', params={
            'expression': f'(async () => {{ {ESPERAR} return await ({expresion}); }})()', 'awaitPromise': True,
            'returnByValue': True}, timeout=timeout)
        if res.get('exceptionDetails'):
            self.fail(f'JavaScript falló: {json.dumps(res["exceptionDetails"], default=str)[:600]}')
        return res['result'].get('value')

    def _buscar_muchos(self, browser):
        """Busca «ensayo» (8 lugares) y devuelve lo que se lee en la página."""
        return self._js(browser, """(async () => {
            escribir('ensayo');
            await esperar(() => lugares().length === 8, 'los 8 lugares de «ensayo»');
            await new Promise((ok) => setTimeout(ok, 300));
            return {texto: document.body.innerText,
                    precios: lugares().map((l) => (l.querySelector('.precio') || {}).textContent),
                    mapas: lugares().map((l) => l.querySelector('a.mapa').href),
                    estado: document.querySelector('.estado').textContent};
        })()""")

    def test_en_el_celular_busca_ve_el_precio_sin_km_y_baja_con_el_dedo(self):
        with self._chrome(390, 844, tactil=True) as browser:
            villa = self._js(browser, """(async () => {
                escribir('vla prueba');
                await esperar(() => lugares().length && lugares()[0].textContent.includes('Villa Prueba'),
                              'Villa Prueba');
                const l = lugares()[0];
                return {nombre: l.querySelector('.nombre').textContent, zona: l.querySelector('.zona').textContent,
                        precio: l.querySelector('.precio').textContent, mapa: l.querySelector('a.mapa').textContent,
                        rel: l.querySelector('a.mapa').rel};
            })()""")
            self.assertEqual(villa, {'nombre': 'Villa Prueba', 'zona': 'Barrio Prueba · La Chorrera', 'precio': '$15',
                                     'mapa': 'Ver en Google Maps', 'rel': 'noopener noreferrer'})
            leido = self._buscar_muchos(browser)
            self.assertNotRegex(leido['texto'], r'(?i)\bkm\b|kil[oó]metro', 'el chofer no ve kilómetros')
            self.assertTrue(all(p and p.startswith('$') for p in leido['precios']), leido['precios'])
            self.assertTrue(all(m.startswith('https://www.google.com/maps/dir/') for m in leido['mapas']))
            self.assertEqual(leido['estado'], '8 lugares')
            antes = self._js(browser, MEDIR)
            self.assertLessEqual(antes['ancho'], antes['anchoVisible'], f'hay scroll de lado: {antes}')
            self.assertGreaterEqual(antes['izquierda'], 15, f'sin 16 px de margen: {antes}')
            self.assertGreaterEqual(antes['derecha'], 15, f'sin 16 px de margen: {antes}')
            self.assertNotIn('hidden', (antes['desborde'], antes['desbordeHtml']), 'nada de overflow: hidden')
            self.assertGreater(antes['alto'], antes['visible'] + 300, f'falta una página más alta: {antes}')
            # El dedo: tocar, arrastrar hacia arriba y soltar.
            toque = lambda tipo, puntos: browser._websocket_request(   # noqa: E731
                'Input.dispatchTouchEvent', params={'type': tipo, 'touchPoints': puntos})
            toque('touchStart', [{'x': 195, 'y': 760}])
            for paso in range(1, 21):
                toque('touchMove', [{'x': 195, 'y': 760 - paso * 25}])
            toque('touchEnd', [])
            self._js(browser, 'new Promise((ok) => setTimeout(ok, 600))')
            despues = self._js(browser, MEDIR)
            self.assertGreater(despues['scroll'], antes['scroll'] + 200, f'el dedo no baja la página: {despues}')

    def test_en_la_computadora_baja_con_la_rueda(self):
        with self._chrome(1366, 768) as browser:
            self._buscar_muchos(browser)
            antes = self._js(browser, MEDIR)
            self.assertGreater(antes['alto'], antes['visible'] + 300, f'falta una página más alta: {antes}')
            for _vez in range(4):
                browser._websocket_request('Input.dispatchMouseEvent', params={
                    'type': 'mouseWheel', 'x': 683, 'y': 500, 'deltaX': 0, 'deltaY': 400})
            self._js(browser, 'new Promise((ok) => setTimeout(ok, 600))')
            despues = self._js(browser, MEDIR)
            self.assertGreater(despues['scroll'], antes['scroll'] + 300, f'la rueda no baja la página: {despues}')
            self.assertLessEqual(despues['ancho'], despues['anchoVisible'])

    def test_usar_mi_ubicacion(self):
        with self._chrome(390, 844, tactil=True) as browser:
            cerca = self._js(browser, """(async () => {
                Object.defineProperty(navigator, 'geolocation', {configurable: true, value: {
                    getCurrentPosition: (ok) => ok({coords: {latitude: 8.9011, longitude: -79.8011}})}});
                document.querySelector('.ubicacion').click();
                await esperar(() => lugares().length === 3, 'los 3 lugares más cercanos');
                return lugares().map((l) => [l.querySelector('.nombre').textContent,
                                             l.querySelector('.distancia').textContent,
                                             l.querySelector('.precio').textContent]);
            })()""")
            self.assertEqual(cerca, [['Villa Prueba', 'a 10 m de ti', '$15'],
                                     ['Villa Prueba II', 'a 20 m de ti', '$15'],
                                     ['Hospital del Ejemplo', 'a 160 m de ti', '$15']])
            lejos = self._js(browser, """(async () => {
                Object.defineProperty(navigator, 'geolocation', {configurable: true, value: {
                    getCurrentPosition: (ok) => ok({coords: {latitude: 9.3, longitude: -79.0}})}});
                document.querySelector('.ubicacion').click();
                const estado = () => document.querySelector('.estado').textContent;
                return await esperar(() => !lugares().length && estado().includes('No hay') && estado(),
                                     'el aviso de nada cerca');
            })()""")
            self.assertEqual(lejos, choferes.NADA_CERCA)
            for codigo, texto in ((1, 'No diste permiso'), (2, 'No pudimos saber dónde estás'),
                                  (3, 'Tu ubicación tardó demasiado')):
                with self.subTest(codigo=codigo):
                    leido = self._js(browser, f"""(async () => {{
                        Object.defineProperty(navigator, 'geolocation', {{configurable: true, value: {{
                            getCurrentPosition: (ok, mal) => mal({{code: {codigo}}})}}}});
                        document.querySelector('.ubicacion').click();
                        const estado = () => document.querySelector('.estado').textContent;
                        return await esperar(() => estado().includes({json.dumps(texto)})
                                                   && !document.querySelector('.ubicacion').disabled && estado(),
                                             'el aviso');
                    }})()""")
                    self.assertIn('busca el lugar por nombre', leido)
