"""Contrato visual de la cabecera y del hero (pedido de la dueña: «que este navbar nunca más se
vuelva a dañar»). Fija, medido en Chrome y a dos anchos (1440 y 390), el diseño aprobado
(docs/auditoria/ronda6/diseno.md §8):

* Píldora de vidrio líquido (`.o_main_nav::before`): desenfoque + saturación, tinte blanco al 62 %
  (claro, sobre fondo claro) o negro al 26 % (ahumado, sobre foto), filos de luz, esquinas suaves (16 px);
  los mismos valores en TODAS las páginas del mismo tipo; hamburguesa visible en el celular.
* Portada sin placa: texto blanco directo sobre la foto, velo negro plano del 35-50 %, halo fino en
  el texto y ningún elemento con fondo detrás del titular.
* Portada con el carrusel de productos (models/portada.py, 2026-11-16): el texto blanco sobre el negro del
  hero, sin placa (nada azul ni navy, ningún fondo detrás del titular); la foto de estudio entera, sin velo ni
  filtro, en su marco de esquinas suaves, que empieza debajo de la píldora (la píldora ahumada nunca queda sobre
  el gris claro de una foto) y no se monta sobre el texto.
* Capturas de referencia («golden») en tests/referencia/, comparadas con tolerancia.

Dos niveles:
1. Estilos computados (bloqueante): no dependen del motor de dibujo ni de las fuentes del sistema.
2. Píxeles contra las referencias (tolerancia `DCASA_TOLERANCIA_VISUAL`, 1.5 % por defecto, de píxeles
   con una diferencia > 40/255). Las referencias se regeneran A PROPÓSITO con
   `scripts/actualizar_referencias_visuales.sh` (ver docs/OPERACION.md). Si la comparación resulta
   frágil en CI (otra versión de Chrome, otro rasterizado), se sube la tolerancia por variable de
   entorno sin tocar el contrato de estilos.
"""
import base64
import contextlib
import io
import json
import logging
import os
import pathlib
import re
from unittest.mock import patch

from PIL import Image, ImageChops, ImageDraw

from odoo.addons.website_dcasa.models.black_weekend import PARAM_ACTIVO, PARAM_FIN, PARAM_INICIO
from odoo.tests import HttpCase, tagged
from odoo.tests.common import ChromeBrowser, save_test_file

_logger = logging.getLogger(__name__)

REFERENCIAS = pathlib.Path(__file__).parent / 'referencia'
VAR_REGENERAR = 'DCASA_REFERENCIAS_VISUALES'       # =regenerar → reescribe las referencias
VAR_TOLERANCIA = 'DCASA_TOLERANCIA_VISUAL'         # % de píxeles distintos tolerado (manda sobre los defectos)
UMBRAL_PIXEL = 40                                  # diferencia por canal (0-255) que cuenta como distinto
# Tolerancias por defecto: 1.5 % en local (mismo Chromium que generó las referencias). En CI (variable
# CI=true, GitHub Actions) el Chrome del runner rasteriza texto y desenfoque distinto: el borde de cada
# letra ya suma 1-2 % de la cabecera sin cambio de diseño, así que ahí se afloja y el contrato de
# estilos computados (test_01/test_02, bloqueante) es el que garantiza el diseño.
TOLERANCIA_LOCAL, TOLERANCIA_CI = 1.5, 6.0
# Las referencias van SIN pérdida (la compresión con pérdida sola ya movía el 3 % de los píxeles de
# los bordes del texto por encima del umbral). El hero (una foto grande) se guarda y compara a la
# mitad de resolución: basta para ver una placa, un velo distinto o un texto movido, y pesa 4 veces menos.
REDUCCION = {'cabecera': 1, 'hero': 2}

# Anchos: escritorio y celular (iPhone 12/13/14).
VENTANAS = ((1440, 900), (390, 844))

# El contrato: la píldora aprobada por la dueña (v2.3 / ronda 6 v3).
VIDRIO_CLARO = {'fondo': 'rgba(255, 255, 255, 0.62)', 'borde': 'rgba(255, 255, 255, 0.7)',
                'texto': 'rgb(27, 34, 51)'}
VIDRIO_AHUMADO = {'fondo': 'rgba(0, 0, 0, 0.26)', 'borde': 'rgba(255, 255, 255, 0.38)',
                  'texto': 'rgb(255, 255, 255)'}
RADIO_PILDORA = '16px'                             # 1rem: esquinas suaves como el logo (dueña, 2026-10-17)
VELO_MIN, VELO_MAX = .35, .50
# Fondos que jamás van detrás del titular de la portada (placa navy/azul, decisión de la dueña).
AZUL, NAVY = (19, 64, 177), (14, 42, 107)

# Página → tipo de vidrio al abrir (claro sobre fondo claro, ahumado sobre foto o fondo oscuro).
TIPO_DE_VIDRIO = {'portada': 'ahumado', 'portada-carrusel': 'ahumado', 'tienda': 'claro', 'ficha': 'claro',
                  'socios': 'ahumado', 'black-weekend': 'ahumado'}

# Deja la página quieta y determinista antes de medir o capturar: sin animaciones ni transiciones,
# entradas ya terminadas, barra de scroll oculta, fuentes e imágenes cargadas, cabecera medida.
PREPARAR = """
    (async () => {
        const estilo = document.createElement('style');
        estilo.setAttribute('data-dcasa-contrato-visual', '');
        estilo.textContent = `
            *, *::before, *::after { animation: none !important; transition: none !important;
                                     caret-color: transparent !important; }
            [data-anim-entrada] > *, .o_dcasa_anim [data-anim], .o_dcasa_anim [data-anim-cascada] > *,
            .o_dcasa_anim [data-titular] .o_dcasa_palabra > span { opacity: 1 !important; transform: none !important; }
            html { scrollbar-width: none; }
            ::-webkit-scrollbar { display: none; }
        `;
        document.head.appendChild(estilo);
        const modulo = '@website_dcasa/js/animaciones';
        const conFoto = !!document.querySelector('.o_dcasa_hero, .o_dcasa_fondo_oscuro');
        const listo = () => odoo.loader?.modules?.has(modulo)
            && document.body.getAttribute('is-ready') === 'true'
            && (!conFoto || document.documentElement.classList.contains('o_dcasa_nav_medida'));
        for (let i = 0; i < 600 && !listo(); i++) {
            await new Promise((ok) => setTimeout(ok, 50));
        }
        // Fuentes propias y las fotos de lo que se captura (las imágenes diferidas de más abajo no
        // cargan sin desplazar la página: no se esperan). Tope de 15 s por si una no termina.
        const fotos = [...document.querySelectorAll('header#top img, .o_dcasa_hero img, .o_dcasa_fondo_oscuro img')];
        await Promise.race([
            Promise.all([document.fonts.ready, ...fotos.filter((img) => !img.complete).map(
                (img) => new Promise((ok) => { img.onload = ok; img.onerror = ok; }))]),
            new Promise((ok) => setTimeout(ok, 15000)),
        ]);
        document.querySelector('.o_dcasa_filtros')?.pauseAnimations?.();
        window.scrollTo(0, 0);
        await new Promise((ok) => requestAnimationFrame(() => requestAnimationFrame(ok)));
        return listo();
    })()
"""

# Lo que se mide. Devuelve un objeto plano (se evalúa con returnByValue).
MEDIR = """
    (() => {
        const cs = (el, pseudo) => getComputedStyle(el, pseudo);
        const rect = (el) => {
            const r = el.getBoundingClientRect();
            return { x: r.left, y: r.top, width: r.width, height: r.height };
        };
        const visible = (el) => !!el && cs(el).display !== 'none' && cs(el).visibility !== 'hidden'
            && el.getBoundingClientRect().width > 0 && el.getBoundingClientRect().height > 0;
        const nombre = (el) => el.tagName.toLowerCase() + (typeof el.className === 'string' && el.className.trim()
            ? '.' + el.className.trim().split(/\\s+/).join('.') : '');
        const html = document.documentElement.classList;
        const cabecera = document.querySelector('header#top');
        // Odoo pinta dos barras (escritorio y celular, .o_header_mobile): se mide la visible.
        const nav = [...cabecera.querySelectorAll('.o_main_nav')].find(visible);
        const antes = cs(nav, '::before');
        const enlace = document.querySelector('#top_menu .nav-link:not(.active)');
        const menu = document.querySelector('#top_menu');
        // Hamburguesa: en Odoo 19 es un button.nav-link con el icono .navbar-toggler-icon.
        const icono = nav.querySelector('.navbar-toggler-icon');
        const hamburguesa = icono && icono.closest('button');
        const cta = nav.querySelector('.btn_cta');
        const res = {
            ancho: innerWidth,
            html: { refraccion: html.contains('o_dcasa_refraccion'), sobreFoto: html.contains('o_dcasa_nav_sobre_foto'),
                    medida: html.contains('o_dcasa_nav_medida') },
            pildora: {
                content: antes.content,
                backdropFilter: antes.backdropFilter || antes.webkitBackdropFilter || 'none',
                fondo: antes.backgroundColor,
                fondoImagen: antes.backgroundImage,
                borde: antes.borderTopColor,
                bordeAncho: antes.borderTopWidth,
                radio: antes.borderTopLeftRadius,
                radioNav: cs(nav).borderTopLeftRadius,
                filos: (antes.boxShadow.match(/inset/g) || []).length,
                sombra: antes.boxShadow,
                position: antes.position,
                alto: Math.round(rect(nav).height),
                ancho: Math.round(rect(nav).width),
            },
            menu: { visible: visible(menu), color: enlace ? cs(enlace).color : null,
                    fuente: enlace ? cs(enlace).fontFamily : null,
                    mayusculas: enlace ? cs(enlace).textTransform : null },
            hamburguesa: { visible: visible(hamburguesa), color: hamburguesa ? cs(hamburguesa).color : null,
                           filtroIcono: icono ? cs(icono).filter : null },
            cta: cta ? { visible: visible(cta), fondo: cs(cta).backgroundColor, color: cs(cta).color,
                         radio: cs(cta).borderTopLeftRadius, texto: cta.textContent.trim() } : null,
            logo: !!nav.querySelector('.navbar-brand img[src*="logo-200.webp"]'),
            cabecera: rect(cabecera),
        };
        const hero = document.querySelector('.o_dcasa_hero:not(.o_dcasa_hero_compacto)');
        const detrasDe = (el) => {
            const r = el.getBoundingClientRect();
            const puntos = [[r.left + 2, r.top + 2], [r.right - 2, r.top + 2], [r.left + 2, r.bottom - 2],
                            [r.right - 2, r.bottom - 2], [r.left + r.width / 2, r.top + r.height / 2]];
            const detras = [];
            for (const [x, y] of puntos) {
                for (const otro of document.elementsFromPoint(x, y)) {
                    if (el.contains(otro)) {
                        continue;
                    }
                    detras.push({ sel: nombre(otro), fondo: cs(otro).backgroundColor, imagen: cs(otro).backgroundImage,
                                  esHero: otro === hero });
                    if (otro === hero) {
                        break;
                    }
                }
            }
            return detras;
        };
        if (hero && hero.classList.contains('o_dcasa_hero_vitrina')) {
            const marco = hero.querySelector('.o_dcasa_vitrina_fotos');
            const img = hero.querySelector('.o_dcasa_vitrina_foto.is-activa img');
            const texto = hero.querySelector('.o_dcasa_hero_texto');
            const titulo = hero.querySelector('.o_dcasa_display');
            const sub = hero.querySelector('.o_dcasa_hero_sub');
            const kicker = hero.querySelector('.o_dcasa_hero_texto > .o_dcasa_kicker');
            const piso = Math.max(...[...cabecera.querySelectorAll('.o_main_nav')].filter(visible)
                .map((n) => n.getBoundingClientRect().bottom));
            const a = texto.getBoundingClientRect(), b = marco.getBoundingClientRect();
            res.vitrina = {
                rect: rect(hero),
                fondo: cs(hero).backgroundColor,
                opacidadFoto: parseFloat(cs(img).opacity),
                opacidadDiapositiva: parseFloat(cs(img.closest('.o_dcasa_vitrina_foto')).opacity),
                filtroFoto: cs(img).filter,
                mezclaFoto: cs(img).mixBlendMode,
                marcoImagen: cs(marco).backgroundImage,
                marcoRadio: cs(marco).borderTopLeftRadius,
                capas: ['::before', '::after'].flatMap((p) => [cs(marco, p).content, cs(texto, p).content]),
                fotoBajoPildora: b.top >= piso,
                textoSobreFoto: a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top,
                textoFondo: cs(texto).backgroundColor,
                textoImagen: cs(texto).backgroundImage,
                colores: { titulo: cs(titulo).color, sub: cs(sub).color, kicker: kicker ? cs(kicker).color : null },
                detras: detrasDe(titulo),
            };
        } else if (hero) {
            const img = hero.querySelector('.o_dcasa_hero_media img');
            const media = img.parentElement;
            const texto = hero.querySelector('.o_dcasa_hero_texto');
            const titulo = hero.querySelector('.o_dcasa_display');
            const sub = hero.querySelector('.o_dcasa_hero_sub');
            const kicker = hero.querySelector('.o_dcasa_kicker');
            const r = titulo.getBoundingClientRect();
            const puntos = [[r.left + 2, r.top + 2], [r.right - 2, r.top + 2], [r.left + 2, r.bottom - 2],
                            [r.right - 2, r.bottom - 2], [r.left + r.width / 2, r.top + r.height / 2]];
            const detras = [];
            // De arriba abajo hasta el hero: lo que hay debajo de él (fondo de la página) queda tapado
            // por su negro opaco y no cuenta.
            for (const [x, y] of puntos) {
                for (const el of document.elementsFromPoint(x, y)) {
                    if (titulo.contains(el) || el === img) {
                        continue;
                    }
                    detras.push({ sel: nombre(el), fondo: cs(el).backgroundColor, imagen: cs(el).backgroundImage,
                                  esHero: el === hero });
                    if (el === hero) {
                        break;
                    }
                }
            }
            const a = texto.getBoundingClientRect(), b = img.getBoundingClientRect();
            res.hero = {
                rect: rect(hero),
                fondo: cs(hero).backgroundColor,
                opacidadFoto: parseFloat(cs(img).opacity),
                filtroFoto: cs(img).filter,
                mezclaFoto: cs(img).mixBlendMode,
                mediaFondo: cs(media).backgroundImage,
                mediaPos: cs(media).position,
                capas: ['::before', '::after'].flatMap((p) => [cs(media, p).content, cs(texto, p).content]),
                textoFondo: cs(texto).backgroundColor,
                textoImagen: cs(texto).backgroundImage,
                textoSombra: cs(texto).boxShadow,
                textoBorde: cs(texto).borderTopStyle,
                colores: { titulo: cs(titulo).color, sub: cs(sub).color, kicker: cs(kicker).color },
                halo: { titulo: cs(titulo).textShadow, sub: cs(sub).textShadow, kicker: cs(kicker).textShadow },
                detras,
                textoSobreFoto: a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top,
            };
        }
        return res;
    })()
"""


def _cama_de_estudio(cabecero):
    """Foto 3:4 de una cama como las del catálogo (fondo de estudio claro), dibujada: el contrato no depende del
    catálogo real."""
    imagen = Image.new('RGB', (900, 1200), (226, 226, 224))
    dibujo = ImageDraw.Draw(imagen)
    dibujo.rectangle((0, 900, 900, 1200), fill=(206, 206, 204))           # piso
    dibujo.rectangle((150, 380, 750, 760), fill=cabecero)                 # cabecero
    dibujo.rectangle((90, 640, 810, 900), fill=(245, 245, 243))           # colchón y edredón
    dibujo.rectangle((90, 880, 810, 930), fill=cabecero)                  # base
    for x in (120, 760):
        dibujo.rectangle((x, 930, x + 24, 1010), fill=(30, 30, 30))       # patas
    salida = io.BytesIO()
    imagen.save(salida, 'JPEG', quality=92)
    return base64.b64encode(salida.getvalue())


def _rgba(color):
    """'rgb(1, 2, 3)' / 'rgba(1, 2, 3, 0.5)' → (1, 2, 3, alfa)."""
    numeros = re.findall(r'[\d.]+', color or '')
    if len(numeros) == 3:
        return (*(int(float(n)) for n in numeros), 1.0)
    if len(numeros) == 4:
        return (*(int(float(n)) for n in numeros[:3]), float(numeros[3]))
    return None


def _comparar(referencia, actual, umbral=UMBRAL_PIXEL):
    """% de píxeles cuya diferencia máxima por canal supera `umbral`, y la máscara de esos píxeles."""
    diff = ImageChops.difference(referencia.convert('RGB'), actual.convert('RGB'))
    r, g, b = diff.split()
    maximo = ImageChops.lighter(ImageChops.lighter(r, g), b)
    mascara = maximo.point(lambda v: 255 if v > umbral else 0)
    distintos = mascara.histogram()[255]
    return 100.0 * distintos / (mascara.width * mascara.height), mascara


@tagged('post_install', '-at_install')
class TestContratoVisual(HttpCase):
    # Medidas y capturas por (página, ancho): se toman una sola vez por clase (cada apertura de
    # Chrome cuesta segundos) y las comparten los tres tests.
    _medido = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        param = cls.env['ir.config_parameter'].sudo()
        param.set_param(PARAM_ACTIVO, '1')
        param.set_param(PARAM_INICIO, '')
        param.set_param(PARAM_FIN, '')
        recamaras = cls.env.ref('website_dcasa.public_category_recamaras')
        cls.producto = cls.env['product.template'].create({
            'name': 'Cama del contrato visual', 'list_price': 99.99, 'is_published': True,
            'public_categ_ids': [(6, 0, recamaras.ids)], 'dcasa_black_weekend': True,
        })
        cls.paginas = {'portada': '/', 'portada-carrusel': '/', 'tienda': '/shop', 'ficha': cls.producto.website_url,
                       'socios': '/socios', 'black-weekend': '/promociones'}
        # Dos camas «de estudio» dibujadas (fondo gris claro, cabecero y colchón) para el carrusel de la portada.
        cls.Diapositiva = cls.env['dcasa.portada.diapositiva']
        cls.camas_carrusel = cls.env['product.template'].browse()
        for nombre, cabecero in (('Cama queen negra del contrato visual', (28, 28, 30)),
                                 ('Cama king rosada del contrato visual', (214, 128, 150))):
            cls.camas_carrusel |= cls.env['product.template'].create({
                'name': nombre, 'list_price': 159.99, 'is_published': True,
                'public_categ_ids': [(6, 0, recamaras.ids)], 'image_1920': _cama_de_estudio(cabecero),
            })

    # ------------------------------------------------------------------ Chrome
    @contextlib.contextmanager
    def _chrome(self, ancho, alto):
        """Chrome headless como en HttpCase.browser_js, pero devolviendo el navegador para evaluar
        código con resultado y pedir capturas. Viewport fijo y prefers-reduced-motion: reduce
        (emulado por el protocolo) para que la página sea determinista."""
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
            self.authenticate(None, None, browser=browser)
            self.cr.flush()
            self.cr.clear()
            browser._websocket_request('Emulation.setEmulatedMedia', params={
                'features': [{'name': 'prefers-reduced-motion', 'value': 'reduce'}]})
            yield browser

    def _evaluar(self, browser, expresion, timeout=60):
        res = browser._websocket_request('Runtime.evaluate', params={
            'expression': expresion, 'awaitPromise': True, 'returnByValue': True}, timeout=timeout)
        resultado = res['result']
        self.assertNotEqual(resultado.get('subtype'), 'error', f'JavaScript falló: {res}')
        return resultado.get('value')

    def _capturar(self, browser, caja, alto_ventana):
        """PNG del recorte `caja` (px CSS), acotado a la ventana."""
        alto = min(caja['height'], alto_ventana - caja['y'])
        datos = browser._websocket_request('Page.captureScreenshot', params={
            'format': 'png', 'captureBeyondViewport': False,
            'clip': {'x': caja['x'], 'y': caja['y'], 'width': caja['width'], 'height': alto, 'scale': 1},
        }, timeout=60)['data']
        return Image.open(io.BytesIO(base64.b64decode(datos))).convert('RGB')

    def _medir_todo(self):
        if TestContratoVisual._medido is not None:
            return TestContratoVisual._medido
        medido = {}
        for ancho, alto in VENTANAS:
            for nombre, ruta in self.paginas.items():
                # La campaña encendida solo para su página: con campaña, el menú suma «Promociones» en todas, y el
                # contrato de las demás es la cabecera de todos los días (campaña del sitio, 2026-11-15).
                encendida = '1' if nombre == 'black-weekend' else '0'
                self.env['ir.config_parameter'].sudo().set_param(PARAM_ACTIVO, encendida)
                # El carrusel de la portada solo para su página; las demás, con el hero de siempre.
                self.Diapositiva.search([]).unlink()
                if nombre == 'portada-carrusel':
                    for orden, producto in enumerate(self.camas_carrusel, start=1):
                        self.Diapositiva.create({'product_tmpl_id': producto.id, 'sequence': orden})
                self.env.flush_all()
                with self._chrome(ancho, alto) as browser:
                    browser.navigate_to(self.base_url() + ruta, wait_stop=True)
                    self.assertTrue(browser._wait_ready(), f'{ruta} no terminó de cargar')
                    self.assertTrue(self._evaluar(browser, PREPARAR, timeout=90),
                                    f'{ruta} a {ancho}px: la cabecera no llegó a medirse (JS del sitio)')
                    medidas = self._evaluar(browser, MEDIR)
                    capturas = {'cabecera': self._capturar(browser, medidas['cabecera'], alto)}
                    if medidas.get('hero') or medidas.get('vitrina'):
                        caja = (medidas.get('hero') or medidas['vitrina'])['rect']
                        capturas['hero'] = self._capturar(browser, caja, alto)
                    capturas = {parte: img.reduce(REDUCCION[parte]) for parte, img in capturas.items()}
                    excepcion = browser._result.done() and browser._result.exception()
                    self.assertFalse(excepcion, f'{ruta} a {ancho}px: error de JavaScript en la página: {excepcion}')
                    self.assertFalse(browser.had_failure, f'{ruta} a {ancho}px: console.error en la página')
                    _logger.info('Contrato visual %s @%s: %s', nombre, ancho, json.dumps(medidas['pildora']))
                    medido[nombre, ancho] = {'medidas': medidas, 'capturas': capturas}
        TestContratoVisual._medido = medido
        return medido

    # ------------------------------------------------------------------ 1. estilos (bloqueante)
    def test_01_pildora_de_vidrio_liquido_en_todas_las_paginas(self):
        medido = self._medir_todo()
        for ancho, _alto in VENTANAS:
            firmas, tintes = {}, {}
            for nombre in self.paginas:
                m = medido[nombre, ancho]['medidas']
                p, tipo = m['pildora'], TIPO_DE_VIDRIO[nombre]
                with self.subTest(pagina=nombre, ancho=ancho):
                    self._revisar_pildora(m, tipo, ancho)
                # Firma común a todo el sitio (geometría y filtro) y tinte por tipo de fondo.
                firmas[nombre] = {k: v for k, v in p.items() if k not in ('fondo', 'borde', 'sombra', 'filos')}
                tintes.setdefault(tipo, {})[nombre] = {
                    'fondo': p['fondo'], 'borde': p['borde'], 'sombra': p['sombra'], 'filos': p['filos'],
                    'texto': m['menu']['color'], 'hamburguesa': m['hamburguesa']['color'],
                    'refraccion': m['html']['refraccion'], 'cta': m['cta'],
                }
            with self.subTest(ancho=ancho, regla='misma píldora en todas las páginas'):
                base = firmas['tienda']
                for nombre, firma in firmas.items():
                    self.assertEqual(firma, base, f'la píldora de {nombre} difiere de la tienda a {ancho}px')
            for tipo, por_pagina in tintes.items():
                with self.subTest(ancho=ancho, regla=f'mismo vidrio {tipo}'):
                    valores = list(por_pagina.values())
                    for nombre, tinte in por_pagina.items():
                        self.assertEqual(tinte, valores[0], f'el vidrio {tipo} de {nombre} difiere a {ancho}px')

    def _revisar_pildora(self, m, tipo, ancho):
        """El contrato de la píldora en una página, a un ancho."""
        p = m['pildora']
        esperado = VIDRIO_AHUMADO if tipo == 'ahumado' else VIDRIO_CLARO
        self.assertEqual(m['ancho'], ancho, 'viewport fijo')
        self.assertNotIn(p['content'], ('none', 'normal'), 'la píldora (::before) existe')
        self.assertEqual(p['position'], 'absolute')
        filtro = p['backdropFilter']
        self.assertIn('blur(', filtro, f'sin desenfoque: {filtro}')
        self.assertIn('saturate(', filtro, f'sin saturación: {filtro}')
        if m['html']['refraccion']:
            self.assertIn('url(', filtro, 'con o_dcasa_refraccion el filtro lleva url(#dcasa-liquido)')
            self.assertIn('blur(3px)', filtro)
        else:
            self.assertEqual(filtro, 'blur(16px) saturate(2.1) brightness(1.08)')
        self.assertEqual(p['fondo'], esperado['fondo'], f'tinte del vidrio {tipo}')
        alfa = _rgba(p['fondo'])[3]
        self.assertTrue(.55 <= alfa <= .70 if tipo == 'claro' else .20 <= alfa <= .35,
                        f'alfa del vidrio {tipo} fuera de rango: {alfa}')
        self.assertEqual(p['fondoImagen'], 'none', 'sin degradados (sistema plano)')
        self.assertEqual(p['borde'], esperado['borde'])
        self.assertEqual(p['bordeAncho'], '1px')
        self.assertEqual(p['radio'], RADIO_PILDORA, 'esquinas suaves del vidrio')
        self.assertEqual(p['radioNav'], RADIO_PILDORA, 'esquinas suaves del nav')
        self.assertGreaterEqual(p['filos'], 2, f'filos de luz (inset): {p["sombra"]}')
        self.assertEqual(m['menu']['color'], esperado['texto'], f'color del menú sobre el vidrio {tipo}')
        # Sobre foto o fondo oscuro, la cabecera nace y queda ahumada (medida por el observador).
        self.assertEqual(m['html']['sobreFoto'], tipo == 'ahumado')
        self.assertTrue(m['html']['medida'] or tipo == 'claro')
        self.assertTrue(m['logo'], 'logo WebP de D\'CASA en la píldora')
        # Sin «Escríbenos» en la píldora (decisión de la dueña, 2026-11-15: «puede irse… ya está en el pie»; la
        # portada lleva una sección pequeña de contacto antes de Visítanos).
        self.assertIsNone(m['cta'], 'sin botón «Escríbenos» en la píldora')
        if ancho >= 992:
            self.assertTrue(m['menu']['visible'], 'menú visible en escritorio')
            self.assertFalse(m['hamburguesa']['visible'], 'sin hamburguesa en escritorio')
            self.assertIn('Oswald', m['menu']['fuente'])
            self.assertEqual(m['menu']['mayusculas'], 'uppercase')
        else:
            self.assertTrue(m['hamburguesa']['visible'], 'hamburguesa visible en el celular')
            self.assertFalse(m['menu']['visible'], 'en el celular el menú va plegado')
            if tipo == 'ahumado':
                self.assertIn('invert(1)', m['hamburguesa']['filtroIcono'] or '', 'hamburguesa blanca sobre la foto')
            else:
                self.assertEqual(m['hamburguesa']['filtroIcono'], 'none', 'hamburguesa en tinta sobre fondo claro')

    def test_02b_portada_con_carrusel_sin_placa_y_la_foto_entera(self):
        medido = self._medir_todo()
        for ancho, _alto in VENTANAS:
            v = medido['portada-carrusel', ancho]['medidas'].get('vitrina')
            with self.subTest(ancho=ancho):
                self.assertTrue(v, 'con productos elegidos, la portada abre con el carrusel (.o_dcasa_hero_vitrina)')
                self.assertEqual(v['fondo'], 'rgb(0, 0, 0)', 'el negro de siempre del hero')
                self.assertEqual(v['opacidadFoto'], 1.0, 'la foto de estudio sin velo')
                self.assertEqual(v['opacidadDiapositiva'], 1.0)
                self.assertEqual(v['filtroFoto'], 'none')
                self.assertEqual(v['mezclaFoto'], 'normal')
                self.assertEqual(v['marcoImagen'], 'none', 'sin degradado sobre la foto')
                self.assertEqual(v['marcoRadio'], RADIO_PILDORA, 'esquinas suaves como la píldora')
                for capa in v['capas']:
                    self.assertIn(capa, ('none', 'normal'), 'ninguna capa ::before/::after sobre la foto o el texto')
                self.assertTrue(v['fotoBajoPildora'], 'la píldora ahumada nunca sobre el gris claro de la foto')
                self.assertFalse(v['textoSobreFoto'], 'el texto no se monta sobre la foto de estudio')
                self.assertEqual(v['textoFondo'], 'rgba(0, 0, 0, 0)', 'el bloque de texto no tiene fondo (sin placa)')
                self.assertEqual(v['textoImagen'], 'none')
                for cual, color in v['colores'].items():
                    if color is not None:     # el antetítulo no sale en el celular
                        self.assertEqual(color, 'rgb(255, 255, 255)', f'{cual} blanco')
                for el in v['detras']:
                    rgba = _rgba(el['fondo'])
                    if el['esHero']:
                        self.assertEqual(rgba[:3], (0, 0, 0))
                        continue
                    self.assertEqual(rgba[3], 0.0, f'{el["sel"]} tiene fondo detrás del titular: {el["fondo"]}')
                    self.assertNotIn(rgba[:3], (AZUL, NAVY), f'{el["sel"]} azul/navy detrás del titular')
                    self.assertEqual(el['imagen'], 'none', f'{el["sel"]} con imagen o degradado detrás del titular')

    def test_02_hero_de_la_portada_sin_placa(self):
        medido = self._medir_todo()
        for ancho, _alto in VENTANAS:
            h = medido['portada', ancho]['medidas'].get('hero')
            with self.subTest(ancho=ancho):
                self.assertTrue(h, 'la portada abre con el hero (.o_dcasa_hero)')
                velo = 1 - h['opacidadFoto']
                self.assertTrue(VELO_MIN - 1e-6 <= velo <= VELO_MAX + 1e-6, f'velo fuera de 35-50 %: {velo:.2f}')
                self.assertEqual(h['fondo'], 'rgb(0, 0, 0)', 'velo negro plano')
                self.assertEqual(h['filtroFoto'], 'none')
                self.assertEqual(h['mezclaFoto'], 'normal')
                self.assertEqual(h['mediaFondo'], 'none', 'sin degradado sobre la foto')
                self.assertEqual(h['mediaPos'], 'absolute', 'la foto va detrás del texto')
                for capa in h['capas']:
                    self.assertIn(capa, ('none', 'normal'), 'ninguna capa ::before/::after sobre la foto o el texto')
                self.assertEqual(h['textoFondo'], 'rgba(0, 0, 0, 0)', 'el bloque de texto no tiene fondo (sin placa)')
                self.assertEqual(h['textoImagen'], 'none')
                self.assertEqual(h['textoSombra'], 'none')
                self.assertEqual(h['textoBorde'], 'none')
                self.assertTrue(h['textoSobreFoto'], 'el texto se superpone a la foto')
                for cual, color in h['colores'].items():
                    self.assertEqual(color, 'rgb(255, 255, 255)', f'{cual} blanco')
                for cual, halo in h['halo'].items():
                    self.assertNotEqual(halo, 'none', f'{cual} sin halo de contraste')
                    self.assertLessEqual(len(halo.split('),')), 2, f'{cual}: el halo es fino (máx. 2 sombras)')
                # Detrás del titular solo hay la foto y el hero negro: ninguna placa ni fondo de color.
                for el in h['detras']:
                    rgba = _rgba(el['fondo'])
                    if el['esHero']:
                        self.assertEqual(rgba[:3], (0, 0, 0))
                        continue
                    self.assertEqual(rgba[3], 0.0, f'{el["sel"]} tiene fondo detrás del titular: {el["fondo"]}')
                    self.assertNotIn(rgba[:3], (AZUL, NAVY), f'{el["sel"]} azul/navy detrás del titular')
                    self.assertEqual(el['imagen'], 'none', f'{el["sel"]} con imagen o degradado detrás del titular')

    # ------------------------------------------------------------------ 2. píxeles (tolerancia)
    def test_03_capturas_de_referencia(self):
        medido = self._medir_todo()
        regenerar = os.environ.get(VAR_REGENERAR, '').lower() == 'regenerar'
        tolerancia = float(os.environ.get(VAR_TOLERANCIA)
                           or (TOLERANCIA_CI if os.environ.get('CI') else TOLERANCIA_LOCAL))
        if regenerar:
            REFERENCIAS.mkdir(exist_ok=True)
        for (nombre, ancho), datos in medido.items():
            for parte, imagen in datos['capturas'].items():
                archivo = REFERENCIAS / f'{parte}-{nombre}-{ancho}.webp'
                if regenerar:
                    imagen.save(archivo, 'WEBP', lossless=True, method=6)
                    _logger.info('Referencia visual escrita: %s (%sx%s)', archivo, *imagen.size)
                    continue
                with self.subTest(parte=parte, pagina=nombre, ancho=ancho):
                    self.assertTrue(archivo.exists(), f'falta {archivo.name}: córrela con '
                                    'scripts/actualizar_referencias_visuales.sh y súbela en el mismo commit')
                    referencia = Image.open(archivo).convert('RGB')
                    if referencia.size != imagen.size:
                        self._guardar(nombre, ancho, parte, imagen)
                        self.fail(f'{archivo.name}: la {parte} cambió de tamaño: referencia {referencia.size}, '
                                  f'ahora {imagen.size}. Si es a propósito, regenera las referencias.')
                    distintos, mascara = _comparar(referencia, imagen)
                    _logger.info('Contrato visual %s/%s @%s: %.2f %% de píxeles distintos',
                                 parte, nombre, ancho, distintos)
                    if distintos > tolerancia:
                        self._guardar(nombre, ancho, parte, imagen, mascara)
                    self.assertLessEqual(distintos, tolerancia, f'{archivo.name}: {distintos:.2f} % de píxeles '
                                         f'distintos (> {tolerancia} %). Si el cambio es a propósito, regenera '
                                         'las referencias en el mismo commit (docs/OPERACION.md).')
        if regenerar:
            _logger.info('Referencias visuales regeneradas: %s',
                         ', '.join(sorted(p.name for p in REFERENCIAS.glob('*.webp'))))

    def _guardar(self, nombre, ancho, parte, imagen, mascara=None):
        """Deja la captura actual (y la máscara de diferencias) junto a las capturas de Odoo."""
        for sufijo, img in (('actual', imagen), ('diff', mascara)):
            if img is None:
                continue
            buf = io.BytesIO()
            img.save(buf, 'PNG')
            save_test_file(f'{parte}_{nombre}_{ancho}_{sufijo}'.replace('-', '_'), buf.getvalue(),
                           'visual_', logger=_logger, document_type='Contrato visual', directory='contrato_visual')
