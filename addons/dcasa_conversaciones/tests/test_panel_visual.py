"""Contrato visual de la pantalla de Conversaciones de Juan y sus hermanas (Resumen, Costos de IA, Conexiones).

Mismo método que el contrato de la cabecera del sitio (``website_dcasa/tests/test_contrato_visual.py``), medido en
Chrome y a dos anchos (escritorio 1440 y celular 390):

1. **Estilos computados (bloqueante)**: no dependen del motor de dibujo ni de las fuentes del sistema.
   * Sistema plano: ningún degradado ni sombra dramática (sombras de más de 16 px de desenfoque o 8 px de caída).
   * El amarillo de la marca (#FED00F) solo sobre azul marino: nunca texto amarillo sobre fondo claro, nunca un
     fondo amarillo rodeado de blanco.
   * Contraste del texto de al menos 4,5:1 (3:1 en texto grande).
   * Foco visible con el teclado de verdad (Tab) en cada control de la pantalla.
2. **Píxeles contra las referencias** (``tests/referencia/panel-*.webp``, sin pérdida): tolerancia
   ``DCASA_TOLERANCIA_VISUAL`` (1,5 % local, 6 % en CI) de píxeles con una diferencia > 40/255. Se regeneran A
   PROPÓSITO con ``scripts/actualizar_referencias_visuales_juan.sh`` (``DCASA_REFERENCIAS_VISUALES=regenerar``).

Para que los píxeles no dependan del reloj, la prueba fija ``Date.now`` del navegador en un instante (10 de marzo de
2026, 10:00 en Panamá) y fecha los mensajes de ejemplo respecto a él.

Además, con ``DCASA_CAPTURAS_JUAN=<carpeta>`` la prueba ``test_capturas_para_la_duena`` deja una captura WebP de cada
pantalla (escritorio y celular) para mostrársela a la dueña; sin esa variable se salta.
"""
import base64
import contextlib
import io
import json
import logging
import os
import pathlib
import random
from datetime import datetime
from unittest.mock import patch

from PIL import Image, ImageChops

from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import ChromeBrowser, save_test_file

from .common import COSTOS, SALUD
from .test_panel_interfaz import (
    ACCION,
    ACCION_CONEXIONES,
    ACCION_COSTOS,
    ACCION_RESUMEN,
    GERENTE,
    VENDEDORA,
    PanelUiCase,
    png,
)

_logger = logging.getLogger(__name__)

REFERENCIAS = pathlib.Path(__file__).parent / 'referencia'
VAR_REGENERAR = 'DCASA_REFERENCIAS_VISUALES'       # =regenerar → reescribe las referencias
VAR_TOLERANCIA = 'DCASA_TOLERANCIA_VISUAL'         # % de píxeles distintos tolerado
VAR_CAPTURAS = 'DCASA_CAPTURAS_JUAN'               # carpeta donde dejar las capturas para la dueña
UMBRAL_PIXEL = 40                                  # diferencia por canal (0-255) que cuenta como distinto
TOLERANCIA_LOCAL, TOLERANCIA_CI = 1.5, 6.0
# El escritorio se guarda y compara a la mitad de resolución (basta para ver una columna movida o un color
# distinto y pesa 4 veces menos); el celular, a tamaño real.
REDUCCION = {1440: 2, 390: 1}

VENTANAS = ((1440, 900), (390, 844))
# 10 de marzo de 2026, 10:00 en Panamá (UTC-5): los mensajes de ejemplo se fechan respecto a este instante.
FIJO = datetime(2026, 3, 10, 15, 0)
FIJO_JS = 'Date.UTC(2026, 2, 10, 15, 0)'

# Qué se mira: (nombre, ruta, usuario, pasos en el navegador, selector que dice «ya cargó»).
VISTAS = (
    ('lista', ACCION, VENDEDORA, '', '.o_dcj_fila'),
    ('hilo', ACCION, VENDEDORA, 'await abrirConversacion("Karen");', '.o_dcj_fila'),
    ('conexiones', ACCION_CONEXIONES, GERENTE, '', '.o_dcj_p_canal'),
)

# Deja la página quieta y determinista: sin animaciones, sin barras de desplazamiento, fuentes e imágenes cargadas.
PREPARAR = """
    (async () => {
        const estilo = document.createElement('style');
        estilo.setAttribute('data-dcasa-contrato-visual', '');
        estilo.textContent = `
            *, *::before, *::after { animation: none !important; transition: none !important; caret-color: transparent !important; }
            html, .o_dcj, .o_dcj *, .o_dcj_p, .o_dcj_p * { scrollbar-width: none; }
            ::-webkit-scrollbar { display: none; }
            .o_dcj_p_chequeo code { color: transparent !important; }
            .o_brian_lanzador { display: none !important; }
        `;
        document.head.appendChild(estilo);
        const fotos = [...document.querySelectorAll('.o_dcj img, .o_dcj_p img')];
        await Promise.race([
            Promise.all([document.fonts.ready, ...fotos.filter((img) => !img.complete).map(
                (img) => new Promise((ok) => { img.onload = ok; img.onerror = ok; }))]),
            new Promise((ok) => setTimeout(ok, 15000)),
        ]);
        window.scrollTo(0, 0);
        await new Promise((ok) => requestAnimationFrame(() => requestAnimationFrame(ok)));
        return true;
    })()
"""

# Ayudas para manejar la pantalla desde el protocolo (las mismas que usan las pruebas de interfaz).
AYUDAS = """
    window.__dcj = {
        esperar: async (fn, que, ms = 20000) => {
            const inicio = performance.now();
            while (performance.now() - inicio < ms) {
                const r = fn();
                if (r) { return r; }
                await new Promise((ok) => setTimeout(ok, 100));
            }
            throw new Error('Conversaciones: no apareció ' + que);
        },
        aqui: (selector, texto) => [...document.querySelectorAll(selector)].find((e) => !texto || e.textContent.includes(texto)),
    };
    window.abrirConversacion = async (nombre) => {
        const fila = await __dcj.esperar(() => __dcj.aqui('.o_dcj_fila', nombre), 'la conversación de ' + nombre);
        fila.click();
        await __dcj.esperar(() => document.querySelector('.o_dcj_hilo_cuerpo .o_dcj_burbuja'), 'las burbujas del hilo');
    };
    true
"""

# Lo que se audita en cada pantalla: devuelve la lista de faltas al contrato (vacía = todo bien).
AUDITAR = """
    (() => {
        const raiz = document.querySelector('.o_dcj, .o_dcj_p');
        const rgba = (s) => {
            const m = (s || '').match(/[\\d.]+/g);
            return m ? [+m[0], +m[1], +m[2], m.length > 3 ? +m[3] : 1] : [0, 0, 0, 0];
        };
        const luz = ([r, g, b]) => {
            const f = (c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); };
            return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
        };
        const razon = (a, b) => { const x = luz(a), y = luz(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
        const mezclar = (encima, debajo) => encima[3] >= 1 ? encima.slice(0, 3)
            : encima.slice(0, 3).map((v, i) => v * encima[3] + debajo[i] * (1 - encima[3]));
        // Color del fondo que se ve detrás del elemento (mezcla las capas translúcidas hasta dar con una opaca).
        const fondoDe = (el) => {
            const capas = [];
            for (let e = el; e; e = e.parentElement) {
                const c = rgba(getComputedStyle(e).backgroundColor);
                if (c[3] > 0) { capas.push(c); if (c[3] >= 1) { break; } }
            }
            return capas.reverse().reduce((base, c) => mezclar(c, base), [255, 255, 255]);
        };
        const opacidadDe = (el) => { let o = 1; for (let e = el; e; e = e.parentElement) { o *= +getComputedStyle(e).opacity; } return o; };
        const visible = (el) => {
            const cs = getComputedStyle(el), r = el.getBoundingClientRect();
            return cs.display !== 'none' && cs.visibility !== 'hidden' && r.width > 0 && r.height > 0;
        };
        const nombre = (el) => el.tagName.toLowerCase() + (typeof el.className === 'string' && el.className.trim()
            ? '.' + el.className.trim().split(/\\s+/).slice(0, 2).join('.') : '');
        const AMARILLO = [254, 208, 15];
        const esAmarillo = (c) => Math.abs(c[0] - AMARILLO[0]) < 8 && Math.abs(c[1] - AMARILLO[1]) < 12 && Math.abs(c[2] - AMARILLO[2]) < 30;
        const faltas = [];
        const elementos = [raiz, ...raiz.querySelectorAll('*')];
        const sombra = /(rgba?\\([^)]*\\))\\s+(-?[\\d.]+)px\\s+(-?[\\d.]+)px\\s+([\\d.]+)px(?:\\s+(-?[\\d.]+)px)?/g;
        for (const el of elementos) {
            if (!visible(el) || el.closest('svg')) { continue; }
            for (const pseudo of [null, '::before', '::after']) {
                const cs = getComputedStyle(el, pseudo);
                if (pseudo && (cs.content === 'none' || cs.content === 'normal')) { continue; }
                if ((cs.backgroundImage || '').includes('gradient')) { faltas.push('degradado en ' + nombre(el) + (pseudo || '')); }
                if (cs.textShadow && cs.textShadow !== 'none') { faltas.push('sombra de texto en ' + nombre(el)); }
                for (const m of (cs.boxShadow || '').matchAll(sombra)) {
                    const [, color, , y, desenfoque] = m;
                    if (+desenfoque > 16 || Math.abs(+y) > 8 || rgba(color)[3] > 0.3) {
                        faltas.push('sombra dramática en ' + nombre(el) + ': ' + m[0]);
                    }
                }
            }
            const cs = getComputedStyle(el);
            const color = rgba(cs.color), fondoPropio = rgba(cs.backgroundColor);
            // El amarillo de la marca solo sobre azul marino.
            const tieneTexto = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
            if (tieneTexto && esAmarillo(color) && luz(fondoDe(el)) > 0.1) { faltas.push('texto amarillo sobre fondo claro en ' + nombre(el)); }
            if (el !== raiz && fondoPropio[3] > 0.5 && esAmarillo(fondoPropio)) {
                const padre = fondoDe(el.parentElement);
                if (luz(padre) > 0.1) { faltas.push('fondo amarillo sobre fondo claro en ' + nombre(el)); }
            }
            if (el.matches('.fa') && esAmarillo(color) && luz(fondoDe(el)) > 0.1) { faltas.push('ícono amarillo sobre fondo claro en ' + nombre(el)); }
            // Contraste del texto.
            if (tieneTexto && !el.disabled && !el.closest('[disabled], [aria-hidden=true], .o_dcj_solo_lector, .o_dcj_p_chequeo code')) {
                const grande = parseFloat(cs.fontSize) >= 24 || (parseFloat(cs.fontSize) >= 18.66 && +cs.fontWeight >= 700);
                const fondo = fondoDe(el);
                const texto = mezclar([color[0], color[1], color[2], color[3] * opacidadDe(el)], fondo);
                const r = razon(texto, fondo);
                if (r < (grande ? 3 : 4.5) - 0.01) { faltas.push('contraste ' + r.toFixed(2) + ':1 en ' + nombre(el) + ' «' + el.textContent.trim().slice(0, 24) + '»'); }
            }
        }
        return faltas;
    })()
"""

# El elemento enfocado ahora mismo, para verificar el foco visible.
FOCO = """
    (() => {
        const el = document.activeElement;
        if (!el || el === document.body) { return null; }
        const cs = getComputedStyle(el);
        return {
            nombre: el.tagName.toLowerCase() + (typeof el.className === 'string' ? '.' + el.className.trim().split(/\\s+/).slice(0, 2).join('.') : ''),
            texto: (el.getAttribute('aria-label') || el.textContent || el.placeholder || '').trim().slice(0, 30),
            dentro: !!el.closest('.o_dcj, .o_dcj_p, .o_dcj_capa'),
            visible: el.matches(':focus-visible'),
            contorno: cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) >= 2,
            sombra: cs.boxShadow !== 'none',
        };
    })()
"""

CAJA = """
    (() => {
        const el = document.querySelector('.o_dcj, .o_dcj_p');
        const r = el.getBoundingClientRect();
        return { x: r.left, y: r.top, width: r.width, height: Math.min(r.height, innerHeight - r.top) };
    })()
"""


def qr_de_ejemplo():
    """Un dibujo con pinta de código QR (NO es uno de verdad: solo para que la captura de Conexiones se vea completa)."""
    azar = random.Random(7)
    modulos, escala = 29, 7
    cuadricula = [[azar.random() < .5 for _ in range(modulos)] for _ in range(modulos)]
    for x0, y0 in ((0, 0), (modulos - 7, 0), (0, modulos - 7)):
        for y in range(-1, 8):
            for x in range(-1, 8):
                if 0 <= x0 + x < modulos and 0 <= y0 + y < modulos:
                    anillo = max(abs(x - 3), abs(y - 3))
                    cuadricula[y0 + y][x0 + x] = anillo in (0, 1, 3) and 0 <= x < 7 and 0 <= y < 7
    imagen = Image.new('RGB', (modulos * escala, modulos * escala), 'white')
    for y, fila in enumerate(cuadricula):
        for x, negro in enumerate(fila):
            if negro:
                imagen.paste((0, 0, 0), (x * escala, y * escala, (x + 1) * escala, (y + 1) * escala))
    salida = io.BytesIO()
    imagen.save(salida, 'PNG')
    return 'data:image/png;base64,' + base64.b64encode(salida.getvalue()).decode()


def _comparar(referencia, actual, umbral=UMBRAL_PIXEL):
    """% de píxeles cuya diferencia máxima por canal supera `umbral`, y la máscara de esos píxeles."""
    diff = ImageChops.difference(referencia.convert('RGB'), actual.convert('RGB'))
    r, g, b = diff.split()
    maximo = ImageChops.lighter(ImageChops.lighter(r, g), b)
    mascara = maximo.point(lambda v: 255 if v > umbral else 0)
    distintos = mascara.histogram()[255]
    return 100.0 * distintos / (mascara.width * mascara.height), mascara


@tagged('post_install', '-at_install')
class TestContratoVisualJuan(PanelUiCase):
    _medido = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ahora = FIJO

    def setUp(self):
        super().setUp()
        self.rutas = {('GET', '/odoo/salud'): (SALUD, 200), ('GET', '/odoo/costos'): (COSTOS, 200),
                      ('GET', '/odoo/qr'): ({'ok': True, 'estado': 'necesita_qr', 'edad_s': 3, 'qr': (
                          'data:image/png;base64,' + base64.b64encode(png((0, 0, 0), (64, 64))).decode())}, 200)}

    # ------------------------------------------------------------------ Chrome
    @contextlib.contextmanager
    def _chrome(self, ancho, alto, usuario, reloj_fijo=True):
        """Chrome headless como en ``HttpCase.browser_js`` pero devolviendo el navegador para evaluar código con
        resultado, pulsar teclas y pedir capturas. Viewport fijo, reloj fijo (salvo ``reloj_fijo=False``) y
        movimiento reducido."""
        self.browser_size = f'{ancho}x{alto}'
        browser = ChromeBrowser(self, headless=True)
        with self.allow_requests(browser=browser), contextlib.ExitStack() as atexit:
            atexit.callback(self._wait_remaining_requests)
            atexit.enter_context(browser.cleanup)
            if 'bus.bus' in self.env.registry:    # igual que browser_js: el websocket del bus en tests
                from odoo.addons.bus.websocket import CloseCode, WebsocketConnectionHandler, _kick_all  # noqa: PLC0415
                atexit.callback(_kick_all, CloseCode.KILL_NOW)
                atexit.enter_context(patch.object(
                    WebsocketConnectionHandler, 'websocket_allowed', return_value=True))
            self.authenticate(usuario, usuario, browser=browser)
            self.cr.flush()
            self.cr.clear()
            browser._websocket_request('Emulation.setEmulatedMedia', params={
                'features': [{'name': 'prefers-reduced-motion', 'value': 'reduce'}]})
            # El reloj del navegador, quieto en el instante de los datos de ejemplo.
            if reloj_fijo:
                browser._websocket_request('Page.addScriptToEvaluateOnNewDocument', params={'source': f"""
                (() => {{
                    const fijo = {FIJO_JS};
                    const Original = Date;
                    class Fijo extends Original {{
                        constructor(...args) {{ if (args.length) {{ super(...args); }} else {{ super(fijo); }} }}
                        static now() {{ return fijo; }}
                    }}
                    window.Date = Fijo;
                }})();
            """})
            yield browser

    def _evaluar(self, browser, expresion, timeout=60):
        res = browser._websocket_request('Runtime.evaluate', params={
            'expression': expresion, 'awaitPromise': True, 'returnByValue': True}, timeout=timeout)
        resultado = res['result']
        self.assertNotEqual(resultado.get('subtype'), 'error', f'JavaScript falló: {res}')
        if res.get('exceptionDetails'):
            self.fail(f'JavaScript falló: {json.dumps(res["exceptionDetails"], default=str)[:600]}')
        return resultado.get('value')

    def _sin_lecturas(self):
        """Abrir un hilo marca como leída la conversación: cada vista empieza con todo sin leer, como el primer día."""
        self.env['dcasa.conversacion.lectura'].sudo().search([]).unlink()
        self.env.flush_all()

    def _abrir(self, browser, ruta, pasos, listo):
        """Abre la pantalla, hace los pasos, y la deja quieta para medir y capturar."""
        browser.navigate_to(self.base_url() + ruta, wait_stop=True)
        self.assertTrue(browser._wait_ready('odoo.isReady'), f'{ruta} no terminó de cargar')
        self._evaluar(browser, AYUDAS)
        self._evaluar(browser, f'(async () => {{ await __dcj.esperar(() => document.querySelector("{listo}"), "{listo}"); '
                               f'{pasos} return true; }})()', timeout=90)
        self.assertTrue(self._evaluar(browser, PREPARAR, timeout=90))

    def _capturar(self, browser, caja, formato='png'):
        datos = browser._websocket_request('Page.captureScreenshot', params={
            'format': formato, 'captureBeyondViewport': False,
            'clip': {'x': caja['x'], 'y': caja['y'], 'width': caja['width'], 'height': caja['height'], 'scale': 1},
        }, timeout=60)['data']
        return Image.open(io.BytesIO(base64.b64decode(datos))).convert('RGB')

    def _tab(self, browser, veces):
        """Pulsa Tab de verdad (evento de teclado del protocolo) y devuelve el elemento enfocado tras cada pulsación."""
        enfocados = []
        for _ in range(veces):
            for tipo in ('rawKeyDown', 'keyUp'):
                browser._websocket_request('Input.dispatchKeyEvent', params={
                    'type': tipo, 'key': 'Tab', 'code': 'Tab', 'windowsVirtualKeyCode': 9, 'nativeVirtualKeyCode': 9})
            enfocados.append(self._evaluar(browser, FOCO))
        return enfocados

    def _medir_todo(self):
        if TestContratoVisualJuan._medido is not None:
            return TestContratoVisualJuan._medido
        self.datos_de_ejemplo()
        medido = {}
        for ancho, alto in VENTANAS:
            for nombre, ruta, usuario, pasos, listo in VISTAS:
                self._sin_lecturas()
                with self._chrome(ancho, alto, usuario) as browser:
                    self._abrir(browser, ruta, pasos, listo)
                    faltas = self._evaluar(browser, AUDITAR)
                    caja = self._evaluar(browser, CAJA)
                    captura = self._capturar(browser, caja)
                    excepcion = browser._result.done() and browser._result.exception()
                    self.assertFalse(excepcion, f'{nombre} a {ancho}px: error de JavaScript en la página: {excepcion}')
                    self.assertFalse(browser.had_failure, f'{nombre} a {ancho}px: console.error en la página')
                    reduccion = REDUCCION[ancho]
                    medido[nombre, ancho] = {'faltas': faltas, 'captura': captura.reduce(reduccion) if reduccion > 1 else captura}
        TestContratoVisualJuan._medido = medido
        return medido

    # ------------------------------------------------------------------ 1. estilos computados (bloqueante)
    def test_01_sistema_plano_amarillo_sobre_azul_y_contraste(self):
        medido = self._medir_todo()
        for (nombre, ancho), datos in medido.items():
            with self.subTest(pantalla=nombre, ancho=ancho):
                self.assertFalse(datos['faltas'], f'{nombre} a {ancho}px rompe el contrato de la marca:\n' + '\n'.join(datos['faltas']))

    def test_02_foco_visible_con_el_teclado_de_verdad(self):
        self.datos_de_ejemplo()
        for ancho, alto in VENTANAS:
            for nombre, ruta, usuario, pasos, listo in VISTAS:
                self._sin_lecturas()
                with self.subTest(pantalla=nombre, ancho=ancho), self._chrome(ancho, alto, usuario) as browser:
                    self._abrir(browser, ruta, pasos, listo)
                    self._evaluar(browser, 'document.body.focus(); document.activeElement.blur(); true')
                    enfocados = [f for f in self._tab(browser, 45) if f and f['dentro']]
                    self.assertGreaterEqual(len({(f['nombre'], f['texto']) for f in enfocados}), 5,
                                            f'Tab debería recorrer varios controles de {nombre}: {enfocados}')
                    for f in enfocados:
                        self.assertTrue(f['visible'], f'{nombre}: Tab dejó un control sin :focus-visible: {f}')
                        self.assertTrue(f['contorno'] or f['sombra'],
                                        f'{nombre}: el foco no se ve en {f["nombre"]} «{f["texto"]}»')

    # ------------------------------------------------------------------ 2. píxeles (tolerancia)
    def test_03_capturas_de_referencia(self):
        medido = self._medir_todo()
        regenerar = os.environ.get(VAR_REGENERAR, '').lower() == 'regenerar'
        tolerancia = float(os.environ.get(VAR_TOLERANCIA)
                           or (TOLERANCIA_CI if os.environ.get('CI') else TOLERANCIA_LOCAL))
        if regenerar:
            REFERENCIAS.mkdir(exist_ok=True)
        for (nombre, ancho), datos in medido.items():
            imagen = datos['captura']
            archivo = REFERENCIAS / f'panel-{nombre}-{ancho}.webp'
            if regenerar:
                imagen.save(archivo, 'WEBP', lossless=True, method=6)
                _logger.info('Referencia visual escrita: %s (%sx%s)', archivo, *imagen.size)
                continue
            with self.subTest(pantalla=nombre, ancho=ancho):
                self.assertTrue(archivo.exists(), f'falta {archivo.name}: córrela con '
                                'scripts/actualizar_referencias_visuales_juan.sh y súbela en el mismo commit')
                referencia = Image.open(archivo).convert('RGB')
                if referencia.size != imagen.size:
                    self._guardar(nombre, ancho, imagen)
                    self.fail(f'{archivo.name}: la pantalla cambió de tamaño: referencia {referencia.size}, '
                              f'ahora {imagen.size}. Si es a propósito, regenera las referencias.')
                distintos, mascara = _comparar(referencia, imagen)
                _logger.info('Contrato visual Juan %s @%s: %.2f %% de píxeles distintos', nombre, ancho, distintos)
                if distintos > tolerancia:
                    self._guardar(nombre, ancho, imagen, mascara)
                self.assertLessEqual(distintos, tolerancia, f'{archivo.name}: {distintos:.2f} % de píxeles '
                                     f'distintos (> {tolerancia} %). Si el cambio es a propósito, regenera '
                                     'las referencias en el mismo commit (docs/OPERACION.md).')

    def _guardar(self, nombre, ancho, imagen, mascara=None):
        """Deja la captura actual (y la máscara de diferencias) junto a las capturas de Odoo."""
        for sufijo, img in (('actual', imagen), ('diff', mascara)):
            if img is None:
                continue
            buf = io.BytesIO()
            img.save(buf, 'PNG')
            save_test_file(f'panel_{nombre}_{ancho}_{sufijo}'.replace('-', '_'), buf.getvalue(),
                           'visual_', logger=_logger, document_type='Contrato visual de Juan',
                           directory='contrato_visual')

    # ------------------------------------------------------------------ Capturas para la dueña
    def test_capturas_para_la_duena(self):
        """Una captura WebP (con la barra de Odoo) de cada pantalla, a escritorio y a celular. Solo con la variable
        ``DCASA_CAPTURAS_JUAN``; usa el catálogo real que trae la base."""
        carpeta = os.environ.get(VAR_CAPTURAS)
        if not carpeta:
            self.skipTest(f'Sin {VAR_CAPTURAS}: las capturas para la dueña no se generan.')
        carpeta = pathlib.Path(carpeta)
        carpeta.mkdir(parents=True, exist_ok=True)
        self.ahora = fields.Datetime.now()     # para la dueña: datos de hoy y reloj del navegador de verdad
        self.rutas['GET', '/odoo/qr'] = ({'ok': True, 'estado': 'necesita_qr', 'edad_s': 3, 'qr': qr_de_ejemplo()}, 200)
        self.datos_de_ejemplo()
        # Con las etiquetas de verdad de la tienda, no con la de prueba.
        real = self.env['dcasa.conversacion.etiqueta'].search([('name', '=', 'Pidió precio')], limit=1)
        if real:
            self.marta.sudo().etiqueta_ids = real
            self.etiqueta.sudo().unlink()
        fotos_del_mes = self.env['dcasa.juan.panel']._ahora_local().date()
        for dia in range(1, fotos_del_mes.day):
            self.env['dcasa.juan.costo.dia']._guardar(fotos_del_mes.replace(day=dia), round(dia * 0.35, 2))
        buscar = 'await buscarEnElCatalogo("cama");'
        escritorio = (
            ('conversaciones', ACCION, VENDEDORA, '', '.o_dcj_fila'),
            ('hilo', ACCION, VENDEDORA, 'await abrirConversacion("Karen");', '.o_dcj_fila'),
            ('catalogo', ACCION, VENDEDORA, 'await abrirConversacion("Karen");' + buscar, '.o_dcj_fila'),
            ('cotizacion', ACCION, VENDEDORA, 'await abrirConversacion("Karen"); await abrirCotizacion();', '.o_dcj_fila'),
            ('resumen', ACCION_RESUMEN, GERENTE, '', '.o_dcj_p_dato'),
            ('costos', ACCION_COSTOS, GERENTE, '', '.o_dcj_p_gigante'),
            ('conexiones', ACCION_CONEXIONES, GERENTE, 'await mostrarQr();', '.o_dcj_p_canal'),
        )
        ayudas = AYUDAS + """;
            window.buscarEnElCatalogo = async (texto) => {
                __dcj.aqui('.o_dcj_herramienta', 'Foto del catálogo').click();
                const entrada = await __dcj.esperar(() => document.querySelector('.o_dcj_hoja input[type=search]'), 'el buscador');
                entrada.value = texto;
                entrada.dispatchEvent(new Event('input', { bubbles: true }));
                await __dcj.esperar(() => document.querySelectorAll('.o_dcj_producto img').length >= 2, 'productos del catálogo');
                await new Promise((ok) => setTimeout(ok, 1500));
            };
            window.abrirCotizacion = async () => {
                __dcj.aqui('.o_dcj_herramienta', 'Cotización').click();
                await __dcj.esperar(() => document.querySelector('.o_dcj_hoja'), 'la cotización');
                // Si ya hay una abierta (la de la captura anterior), esa es la que se ve.
                await __dcj.esperar(() => document.querySelector('.o_dcj_hoja input[type=search]')
                                          || __dcj.aqui('.o_dcj_hoja', 'Enviar el PDF'), 'la cotización cargada');
                if (__dcj.aqui('.o_dcj_hoja', 'Enviar el PDF')) { await new Promise((ok) => setTimeout(ok, 1200)); return; }
                const entrada = document.querySelector('.o_dcj_hoja input[type=search]');
                entrada.value = 'cama';
                entrada.dispatchEvent(new Event('input', { bubbles: true }));
                await __dcj.esperar(() => document.querySelectorAll('.o_dcj_producto').length >= 2, 'productos');
                const botones = document.querySelectorAll('.o_dcj_producto button');
                botones[0].click(); botones[0].click();
                await __dcj.esperar(() => document.querySelector('.o_dcj_linea'), 'una línea de la cotización');
                __dcj.aqui('.o_dcj_hoja_pie button', 'Crear el borrador').click();
                await __dcj.esperar(() => __dcj.aqui('.o_dcj_hoja', 'Enviar el PDF'), 'el borrador listo para enviar');
                await new Promise((ok) => setTimeout(ok, 1200));
            };
            window.mostrarQr = async () => {
                __dcj.aqui('button', 'Mostrar el QR').click();
                await __dcj.esperar(() => document.querySelector('.o_dcj_p_qr_imagen img'), 'el QR');
            };
            true
        """
        celular = tuple(v for v in escritorio if v[0] != 'conversaciones') + (
            ('lista', ACCION, VENDEDORA, '', '.o_dcj_fila'),
            ('ficha', ACCION, VENDEDORA,
             'await abrirConversacion("Karen"); document.querySelector(".o_dcj_boton_ficha").click();'
             ' await __dcj.esperar(() => document.querySelector(".o_dcj_ficha .o_dcj_cliente"), "la ficha");',
             '.o_dcj_fila'),
        )
        for ancho, alto, vistas in ((1440, 900, escritorio), (390, 844, celular)):
            for nombre, ruta, usuario, pasos, listo in vistas:
                self._sin_lecturas()
                with self.subTest(pantalla=nombre, ancho=ancho), self._chrome(ancho, alto, usuario, False) as browser:
                    browser.navigate_to(self.base_url() + ruta, wait_stop=True)
                    self.assertTrue(browser._wait_ready('odoo.isReady'))
                    self._evaluar(browser, ayudas)
                    self._evaluar(browser, f'(async () => {{ await __dcj.esperar(() => document.querySelector("{listo}"), "{listo}"); '
                                           f'{pasos} return true; }})()', timeout=120)
                    self._evaluar(browser, PREPARAR, timeout=90)
                    imagen = self._capturar(browser, {'x': 0, 'y': 0, 'width': ancho, 'height': alto})
                    destino = carpeta / f'juan-panel-{nombre}-{"escritorio" if ancho > 600 else "celular"}.webp'
                    imagen.save(destino, 'WEBP', quality=84, method=6)
                    _logger.info('Captura para la dueña: %s (%s bytes)', destino, destino.stat().st_size)
