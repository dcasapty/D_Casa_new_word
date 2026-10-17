"""Mi cuenta en el celular (390 px), medido en Chrome con el teléfono emulado: ninguna pantalla se sale del ancho, la
barra de secciones queda fija abajo con sus 4 botones de al menos 48 px, el botón flotante de WhatsApp no la tapa y
los campos de la entrada no hacen que el iPhone acerque la pantalla."""
from odoo.addons.website_dcasa.tests.chrome_movil import ChromeMovilCase
from odoo.tests import tagged

from .common import MiCuentaComun

ANCHO = 390

MEDIR = """
    (async () => {
        const esperar = (ms) => new Promise((ok) => setTimeout(ok, ms));
        for (let i = 0; i < 100 && document.body.getAttribute('is-ready') !== 'true'; i++) { await esperar(50); }
        await esperar(300);
        const anchos = [];
        const alto = document.body.scrollHeight;
        for (let y = 0; y <= alto; y += 500) {
            window.scrollTo(0, y);
            await esperar(40);
            anchos.push([y, document.documentElement.clientWidth, document.documentElement.scrollWidth]);
        }
        window.scrollTo(0, 0);
        const nav = document.querySelector('.o_dcasa_mc_nav');
        const flotante = document.querySelector('.o_dcasa_wa_float');
        const botones = nav ? [...nav.querySelectorAll('a')].map((a) => {
            const caja = a.getBoundingClientRect();
            return [a.textContent.trim(), Math.round(caja.height), Math.round(caja.width)];
        }) : [];
        const campos = [...document.querySelectorAll('input:not([type=hidden]), select, textarea')]
            .filter((el) => el.getBoundingClientRect().width > 0)
            .map((el) => [el.name || el.id, parseFloat(getComputedStyle(el).fontSize)]);
        return {
            anchos,
            nav: nav ? { posicion: getComputedStyle(nav).position,
                         abajo: Math.round(innerHeight - nav.getBoundingClientRect().bottom) } : null,
            botones,
            flotante: flotante ? getComputedStyle(flotante).display : 'none',
            camposChicos: campos.filter(([, px]) => px < 16),
            h1: document.querySelectorAll('h1').length,
        };
    })()
"""


@tagged('post_install', '-at_install')
class TestMiCuentaMovil(MiCuentaComun, ChromeMovilCase):

    def setUp(self):
        super().setUp()
        self.preparar()
        self.sesion_extra = None

    def authenticate(self, user, password, **kwargs):
        # El Chrome del celular entra como visitante; para ver la cuenta se le da la sesión del PIN (celular + PIN).
        if user is None and self.sesion_extra and 'session_extra' not in kwargs:
            kwargs['session_extra'] = {'dcasa_socio': dict(self.sesion_extra)}
        return super().authenticate(user, password, **kwargs)

    def _medir(self, ruta):
        with self._chrome_movil(ANCHO) as browser:
            browser.navigate_to(self.base_url() + ruta, wait_stop=True)
            self.assertTrue(browser._wait_ready(), f'{ruta} no terminó de cargar')
            return self._evaluar(browser, MEDIR)

    def _sin_desborde(self, ruta, medida):
        self.assertGreater(len(medida['anchos']), 1, f'{ruta}: la página se recorrió')
        for y, cliente, desplazable in medida['anchos']:
            self.assertEqual(cliente, ANCHO, f'{ruta} y={y}: el ancho de la pantalla cambió')
            self.assertLessEqual(desplazable, cliente + 1,
                                 f'{ruta} y={y}: la página mide {desplazable}px y la pantalla {cliente}px')
        self.assertEqual(medida['h1'], 1, f'{ruta}: un solo h1')

    def test_entrada_en_el_celular(self):
        medida = self._medir('/mi-cuenta')
        self._sin_desborde('/mi-cuenta', medida)
        self.assertIsNone(medida['nav'], 'Sin sesión no hay barra de secciones')
        self.assertEqual(medida['camposChicos'], [], 'Campos de menos de 16 px: el iPhone acerca la pantalla')

    def test_cada_pantalla_cabe_y_la_barra_va_abajo(self):
        self.sesion_extra = {'id': self.socia.id, 'huella': self.socia._dcasa_huella_pin(self.socia)}
        for ruta in ('/mi-cuenta', '/mi-cuenta/compras', f'/mi-cuenta/compras/{self.pedido.id}',
                     f'/mi-cuenta/facturas/{self.suelta.id}', '/mi-cuenta/puntos', '/mi-cuenta/datos'):
            with self.subTest(ruta=ruta):
                medida = self._medir(ruta)
                self._sin_desborde(ruta, medida)
                self.assertEqual(medida['nav'], {'posicion': 'fixed', 'abajo': 0}, f'{ruta}: barra fija abajo')
                self.assertEqual([texto for texto, _alto, _ancho in medida['botones']],
                                 ['Inicio', 'Compras', 'Puntos', 'Mis datos'])
                for texto, alto, ancho in medida['botones']:
                    self.assertGreaterEqual(min(alto, ancho), 48, f'{ruta}: «{texto}» mide {ancho}x{alto}')
                self.assertEqual(medida['flotante'], 'none', f'{ruta}: el WhatsApp flotante taparía la barra')
