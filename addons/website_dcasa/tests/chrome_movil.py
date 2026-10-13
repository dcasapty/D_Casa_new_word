"""Chrome headless con el teléfono emulado, para las pruebas del sitio en el celular (test_movil, test_carrito)."""
import contextlib
from unittest.mock import patch

from odoo.tests import HttpCase
from odoo.tests.common import ChromeBrowser

ALTO = 800


class ChromeMovilCase(HttpCase):
    """Base de pruebas que abren Chrome como un teléfono (viewport móvil con toque). No define pruebas."""

    @contextlib.contextmanager
    def _chrome_movil(self, ancho):
        """Chrome headless con el teléfono emulado (viewport móvil con toque), como un iPhone chico."""
        self.browser_size = f'{ancho}x{ALTO}'
        browser = ChromeBrowser(self, headless=True)
        with self.allow_requests(browser=browser), contextlib.ExitStack() as atexit:
            atexit.callback(self._wait_remaining_requests)
            atexit.enter_context(browser.cleanup)
            if 'bus.bus' in self.env.registry:
                from odoo.addons.bus.websocket import CloseCode, WebsocketConnectionHandler, _kick_all  # noqa: PLC0415
                atexit.callback(_kick_all, CloseCode.KILL_NOW)
                atexit.enter_context(patch.object(
                    WebsocketConnectionHandler, 'websocket_allowed', return_value=True))
            self.authenticate(None, None, browser=browser)
            self.cr.flush()
            self.cr.clear()
            browser._websocket_request('Emulation.setDeviceMetricsOverride', params={
                'width': ancho, 'height': ALTO, 'deviceScaleFactor': 2, 'mobile': True})
            browser._websocket_request('Emulation.setTouchEmulationEnabled', params={'enabled': True})
            yield browser

    def _evaluar(self, browser, expresion, timeout=90):
        res = browser._websocket_request('Runtime.evaluate', params={
            'expression': expresion, 'awaitPromise': True, 'returnByValue': True}, timeout=timeout)
        resultado = res['result']
        self.assertNotEqual(resultado.get('subtype'), 'error', f'JavaScript falló: {res}')
        return resultado.get('value')
