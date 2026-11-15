# ruff: noqa: E501  (JavaScript del navegador embebido en texto)
"""La página de verdad en Chrome, con el Worker simulado (tests/worker_simulado.py): la burbuja a 360, 390, 430 y
1366 px, el chat de punta a punta (saludo, tarjetas de Odoo, «te lo puse en el carrito», la ubicación, las estrellas),
la ventana ampliada, Esc, el foco, que no tape la barra de la ficha ni «Pregunta por este mueble por WhatsApp» y el
movimiento reducido."""
import contextlib
import os
from datetime import datetime
from unittest.mock import patch

import pytz

from odoo import Command
from odoo.addons.dcasa_envios.tests.common import importar
from odoo.tests import common as comun
from odoo.tests import new_test_user, tagged
from odoo.tests.common import TEST_CURSOR_COOKIE_NAME, ChromeBrowser

from .common import TOKEN_ODOO, TOKEN_WORKER, TiendaCase
from .worker_simulado import WorkerSimulado

ALTO = 800
DE_DIA = ('saludando', 'con_laptop', 'escritorio', 'busto_estrella', 'bolsita', 'mapa', 'cinta_metrica', 'corazon',
          'burbuja_chat', 'cinco_estrellas', 'fidelidad', 'asomado_burbuja', 'cama', 'cocina', 'marco_foto')
COSTA = (8.9415, -79.8415)    # Costa Inventada, del fixture sintético de envíos

ESPERAR = """
    const esperar = (ms) => new Promise((ok) => setTimeout(ok, ms));
    const hasta = async (fn, que, ms = 20000) => {
        const t0 = Date.now();
        while (Date.now() - t0 < ms) { const v = fn(); if (v) { return v; } await esperar(100); }
        throw new Error('No llegó: ' + que);
    };
    const caja = (el) => { const r = el.getBoundingClientRect(); return { x: r.left, y: r.top, ancho: r.width, alto: r.height, derecha: r.right, abajo: r.bottom }; };
    const globos = () => [...document.querySelectorAll('#o_dcbt_panel .o_dcbt_globo')].map((g) => g.textContent);
    const chip = (texto) => [...document.querySelectorAll('#o_dcbt_panel .o_dcbt_chip')].find((c) => c.textContent.includes(texto));
    await hasta(() => document.readyState === 'complete' && document.querySelector('button.o_dcbt_burbuja'), 'la burbuja');
"""

CHAT = """(async () => {
    /*ESPERAR*/
    const res = { errores: [] };
    const burbuja = document.querySelector('button.o_dcbt_burbuja');
    burbuja.click();
    await hasta(() => globos().some((g) => g.includes('Hola, soy Brian. ¿Qué buscas hoy?')), 'el saludo');
    res.saludos = globos().filter((g) => g.includes('Hola, soy Brian')).length;
    res.expandido = burbuja.getAttribute('aria-expanded');
    (await hasta(() => chip('Colchones'), 'las sugerencias del saludo')).click();
    const tarjeta = await hasta(() => document.querySelector('#o_dcbt_panel .o_dcbt_tarjeta'), 'las tarjetas');
    res.tarjeta = tarjeta.querySelector('h3').textContent;
    res.precio = tarjeta.querySelector('.o_dcbt_precio').textContent;
    res.imagen = tarjeta.querySelector('img') ? tarjeta.querySelector('img').getAttribute('src') : null;
    res.ver = tarjeta.querySelector('.o_dcbt_btn_ver').getAttribute('href');
    tarjeta.querySelector('[data-paso="1"]').click();          // 2
    tarjeta.querySelector('[data-agregar]').click();
    await hasta(() => document.querySelector('#o_dcbt_panel [data-carrito] .o_dcbt_linea_carrito'), 'el carrito');
    res.listo = globos().filter((g) => g.startsWith('Listo, te puse 2 en el carrito')).length;
    res.navbar = (document.querySelector('.my_cart_quantity') || {}).textContent;
    // Brian propone (el visitante lo pidió) y la página lo aplica en Odoo y le cuenta el resultado.
    const escribir = (texto) => {
        const campo = document.querySelector('#o_dcbt_texto');
        campo.value = texto;
        campo.dispatchEvent(new Event('input', { bubbles: true }));
        document.querySelector('#o_dcbt_panel .o_dcbt_composer').requestSubmit();
    };
    escribir('Ponlo en el carrito, por favor');
    await hasta(() => globos().some((g) => g === 'Listo, te lo puse en el carrito. Gracias por escogernos.'), 'el «listo» de Brian');
    await hasta(() => [...document.querySelectorAll('[data-carrito] .o_dcbt_carrito_total')].some((t) => t.textContent.includes('3 artículos')), 'el carrito con 3');
    res.total = [...document.querySelectorAll('[data-carrito] .o_dcbt_carrito_total strong')].pop().textContent;
    res.pdf = document.querySelector('#o_dcbt_panel a[href$="cotizacion.pdf"]') ? true : false;
    // El envío con la ubicación del teléfono.
    (await hasta(() => chip('envío'), 'la sugerencia del envío')).click();
    await hasta(() => chip('Usar mi ubicación actual'), 'el botón de la ubicación');
    res.privacidad = !!document.querySelector('#o_dcbt_panel .o_dcbt_privacidad');
    chip('Usar mi ubicación actual').click();
    const envio = await hasta(() => document.querySelector('#o_dcbt_panel .o_dcbt_envio_texto'), 'el envío');
    res.envio = envio.textContent;
    res.lugar = envio.parentElement.querySelector('h3').textContent;
    // Las estrellas.
    escribir('Gracias, Brian');
    (await hasta(() => document.querySelector('#o_dcbt_panel .o_dcbt_estrella[data-estrellas="5"]'), 'las estrellas')).click();
    await hasta(() => globos().some((g) => g.includes('Gracias por calificarme')), 'las gracias');
    // La ventana ampliada (en el celular, la cuadrícula) y Esc: primero vuelve al tamaño normal, después cierra.
    document.querySelector('#o_dcbt_panel .o_dcbt_cab_boton[aria-pressed]').click();
    await esperar(500);
    const panel = document.querySelector('#o_dcbt_panel');
    res.ampliado = { clase: panel.classList.contains('o_dcbt_ampliado'), ancho: panel.getBoundingClientRect().width,
                     vitrina: document.querySelectorAll('#o_dcbt_panel .o_dcbt_vitrina_grid .o_dcbt_tarjeta').length };
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    await esperar(400);
    res.trasPrimerEsc = { abierto: !panel.hidden, ampliado: panel.classList.contains('o_dcbt_ampliado') };
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    await hasta(() => panel.hidden, 'que se cierre');
    await esperar(400);
    res.foco = document.activeElement === document.querySelector('button.o_dcbt_burbuja');
    res.sinScrollDeLado = document.documentElement.scrollWidth <= innerWidth;
    return res;
})()""".replace('/*ESPERAR*/', ESPERAR)

BURBUJA = """(async () => {
    /*ESPERAR*/
    const burbuja = document.querySelector('button.o_dcbt_burbuja');
    await esperar(2200);   // la burbuja entra y, si venía de otra página, cambia de pose
    const m = window.odoo.loader.modules.get('@dcasa_brian_tienda/js/brian_tienda');
    const raiz = document.querySelector('#o_dcasa_brian');
    const horario = JSON.parse(raiz.dataset.horario);
    const pagina = m.tipoDePagina(location.pathname);
    const res = {
        pantalla: innerWidth, alto: innerHeight, burbuja: { ...caja(burbuja), ancho: burbuja.offsetWidth }, tipo: pagina.tipo,
        aparteAlCargar: burbuja.classList.contains('o_dcbt_aparte'),
        pose: burbuja.querySelector('img.o_dcbt_img_pose:not(.o_dcbt_saliendo)').dataset.pose,
        esperada: m.poseDePagina(pagina, m.esDeNoche(horario), location.pathname).pose,
        etiqueta: burbuja.getAttribute('aria-label'), sinScrollDeLado: document.documentElement.scrollWidth <= innerWidth,
    };
    const barra = document.querySelector('#o_wsale_cta_wrapper');
    if (barra && getComputedStyle(barra).position === 'fixed') {
        res.barra = caja(barra);
    }
    const wa = document.querySelector('.o_dcasa_wa_producto');
    if (wa) {
        // Se lleva «Pregunta por este mueble por WhatsApp» justo detrás de la burbuja: la burbuja se hace a un lado.
        const b = burbuja.getBoundingClientRect();
        window.scrollBy(0, wa.getBoundingClientRect().top - (b.top + b.height / 2) + wa.getBoundingClientRect().height / 2);
        await esperar(500);
        res.wa = caja(wa);
        res.aparte = burbuja.classList.contains('o_dcbt_aparte');
        const r = burbuja.getBoundingClientRect();
        res.tapaVisible = !res.aparte && r.left < res.wa.derecha && r.right > res.wa.x && r.top < res.wa.abajo && r.bottom > res.wa.y;
        window.scrollBy(0, wa.getBoundingClientRect().bottom + 40);   // el botón ya pasó: la burbuja vuelve
        await esperar(500);
        res.vuelve = !burbuja.classList.contains('o_dcbt_aparte');
    }
    return res;
})()""".replace('/*ESPERAR*/', ESPERAR)

QUIETO = """(async () => {
    /*ESPERAR*/
    document.querySelector('button.o_dcbt_burbuja').click();
    await hasta(() => globos().some((g) => g.includes('Hola, soy Brian')), 'el saludo');
    await esperar(300);
    const delChat = (a) => a.effect && a.effect.target && a.effect.target.closest && a.effect.target.closest('#o_dcasa_brian');
    return { animaciones: document.getAnimations().filter((a) => a.playState === 'running' && delChat(a)).map((a) => a.animationName || 'waapi'),
             reducido: matchMedia('(prefers-reduced-motion: reduce)').matches };
})()""".replace('/*ESPERAR*/', ESPERAR)

PURAS = """(() => {
    const m = window.odoo.loader.modules.get('@dcasa_brian_tienda/js/brian_tienda');
    const pose = (tipo, extra = {}, ruta = '') => m.poseDePagina({ tipo, producto_id: null, categoria: null, ...extra }, false, ruta).pose;
    const horario = { inicio: '09:00', fin: '18:00', dias: [0, 1, 2, 3, 4, 5, 6], zona: 'America/Panama', fin_domingo: '17:00' };
    return {
        poses: { inicio: pose('inicio'), catalogo: pose('catalogo'), ficha: pose('ficha'), carrito: pose('carrito'),
                 socios: pose('socios'), visitanos: pose('visitanos'), foto: pose('foto'), otra: pose('otra'),
                 colchones: pose('categoria', { categoria: 'Colchones' }), cocina: pose('categoria', {}, '/shop/category/cocina-9'),
                 oficina: pose('categoria', { categoria: 'Oficina' }), salas: pose('categoria', { categoria: 'Salas' }),
                 noche: m.poseDePagina({ tipo: 'inicio' }, true).pose },
        noche: [m.esDeNoche(horario, new Date('2026-11-13T15:00:00Z')), m.esDeNoche(horario, new Date('2026-11-14T02:00:00Z')),
                m.esDeNoche(horario, new Date('2026-11-15T22:30:00Z'))],
        urls: [m.urlPropia('/shop/x-1'), m.urlPropia('javascript:alert(1)'), m.urlPropia('https://malo.example.com/x'),
               m.urlPropia('https://dcasapty.com/shop/x-2'), m.urlPropia('//malo.example.com/x')],
        precio: m.partirPrecio('$278.00 + ITBMS'),
        wa: m.mensajeWhatsApp({ lineas: [{ cantidad: 2, nombre: 'Colchón' }] }),
        // La pose por sección: entre las páginas salen las 15 de día (el Inicio solo, también); dormido, nunca.
        cobertura: {
            inicio: [...m.posesDeSecciones('inicio')],
            todas: [...new Set(['inicio', 'catalogo', 'ficha', 'carrito', 'visitanos'].flatMap((t) => [...m.posesDeSecciones(t)]))],
            durmiendo: Object.keys(m.SECCIONES).some((t) => m.posesDeSecciones(t).has('durmiendo')),
        },
        activa: (() => {
            const cama = { pose: 'cama', orden: 2 }, cocina = { pose: 'cocina', orden: 3 }, sala = { pose: 'corazon', orden: 1 };
            const pose = (s) => (s ? s.pose : null);
            return [pose(m.seccionActiva(new Set([cocina, cama]), new Set(), 'corazon')),
                    pose(m.seccionActiva(new Set([cama, cocina]), new Set([cama]), 'cama')),
                    pose(m.seccionActiva(new Set([cama, cocina]), new Set([cama, cocina]), 'cocina')),
                    pose(m.seccionActiva(new Set([sala]), new Set(), 'corazon'))];
        })(),
        minimo: m.MIN_ENTRE_CAMBIOS_MS,
        enInicio: m.seccionesDeLaPagina(m.tipoDePagina('/'), '/').map((s) => [s.pose, s.orden]),
    };
})()"""

# Baja por la página deteniéndose donde se le pide y anota cada cambio de pose de la burbuja cerrada (con su hora).
BAJAR = """
    const cajaPose = document.querySelector('button.o_dcbt_burbuja .o_dcbt_pose');
    const actual = () => { const i = cajaPose.querySelector('img.o_dcbt_img_pose:not(.o_dcbt_saliendo)'); return i ? i.dataset.pose : null; };
    const cambios = [];
    let ultima = actual();
    new MutationObserver(() => { const a = actual(); if (a && a !== ultima) { ultima = a; cambios.push([Date.now(), a]); } }).observe(cajaPose, { childList: true });
    const ir = async (sel, ms) => {
        const el = document.querySelector(sel);
        if (!el) { throw new Error('No está la sección ' + sel); }
        const r = el.getBoundingClientRect();
        window.scrollTo(0, Math.max(1, scrollY + r.top + Math.min(r.height, 200) / 2 - innerHeight * 0.475));
        await esperar(ms);
    };
    const minimo = () => Math.min(...cambios.slice(1).map((c, i) => c[0] - cambios[i][0]), 99999);
"""

POSE_EN_EL_INICIO = """(async () => {
    /*ESPERAR*/
    /*BAJAR*/
    await esperar(3200);
    const res = { quieta: cambios.length, alLlegar: actual() };
    // Pasa rápido por dos secciones y se detiene en Socios: cuenta donde se detiene.
    await ir('.o_dcasa_beneficios', 200);
    await ir('.o_dcasa_categorias .o_dcasa_section_head', 200);
    await ir('.o_dcasa_socios_band', 3200);
    res.trasPasarRapido = cambios.map((c) => c[1]);
    // Dos seguidas: la segunda espera el mínimo entre cambios.
    await ir('.o_dcasa_galeria', 900);
    await ir('.o_dcasa_ayuda .o_dcasa_steps', 3400);
    await ir('.o_dcasa_visita_franja', 3200);
    res.cambios = cambios.map((c) => c[1]);
    res.minimo = minimo();
    res.sinScrollDeLado = document.documentElement.scrollWidth <= innerWidth;
    return res;
})()""".replace('/*ESPERAR*/', ESPERAR).replace('/*BAJAR*/', BAJAR)

POSE_EN_LA_FICHA = """(async () => {
    /*ESPERAR*/
    /*BAJAR*/
    await esperar(3200);
    const res = { quieta: cambios.length, alLlegar: actual() };
    await ir('.o_wsale_product_details_content_section_price', 1500);   // las fotos, fijas al lado, ya están
    res.alMoverse = cambios.map((c) => c[1]);
    // Con el chat abierto no cambia; al cerrarlo, se pone al día con la sección donde quedó (el pie).
    document.querySelector('button.o_dcbt_burbuja').click();
    await hasta(() => !document.querySelector('#o_dcbt_panel').hidden, 'el chat abierto');
    const antes = cambios.length;
    await ir('#bottom, footer', 3200);
    res.conElChatAbierto = cambios.length - antes;
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    await hasta(() => document.querySelector('#o_dcbt_panel').hidden, 'que se cierre');
    await esperar(3200);
    res.alCerrar = actual();
    res.minimo = minimo();
    return res;
})()""".replace('/*ESPERAR*/', ESPERAR).replace('/*BAJAR*/', BAJAR)

NOCHE_CHAT = """(async () => {
    /*ESPERAR*/
    const chat = window.__dcasaBrian;
    const poses = [];
    const original = chat.pose.bind(chat);
    chat.pose = (p) => { poses.push(p); return original(p); };
    const burbuja = (document.querySelector('button.o_dcbt_burbuja img.o_dcbt_img_pose:not(.o_dcbt_saliendo)') || {}).dataset;
    document.querySelector('button.o_dcbt_burbuja').click();
    await hasta(() => globos().some((g) => g.includes('Hola, soy Brian')) && globos().length >= 2, 'el saludo');
    let pase = null;
    try { pase = JSON.parse(sessionStorage.getItem('dcasa.brian.pase')); } catch (e) { pase = null; }
    return { burbuja: burbuja ? burbuja.pose : null, globos: globos(), poses, noche: pase && pase.noche,
             avisar: pase && pase.avisar_cerrado };
})()""".replace('/*ESPERAR*/', ESPERAR)

NOCHE_BURBUJA = """(async () => {
    /*ESPERAR*/
    /*BAJAR*/
    await esperar(3200);
    const alLlegar = actual();
    await ir('.o_wsale_product_details_content_section_price', 1500);
    return { alLlegar, cambios: cambios.map((c) => c[1]) };
})()""".replace('/*ESPERAR*/', ESPERAR).replace('/*BAJAR*/', BAJAR)

SIN_CAMBIOS = """(async () => {
    /*ESPERAR*/
    /*BAJAR*/
    await esperar(2500);
    const alLlegar = actual();
    for (const sel of ['#product_details', '#bottom, footer', '.o_wsale_product_images']) {
        await ir(sel, 2800);
    }
    return { alLlegar, cambios: cambios.map((c) => c[1]), ahora: actual() };
})()""".replace('/*ESPERAR*/', ESPERAR).replace('/*BAJAR*/', BAJAR)


class NavegadorCase(TiendaCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        gerencia = new_test_user(cls.env, login='zzbt_ger_nav', name='ZZBT Gerencia Nav',
                                 groups='base.group_user,dcasa_base.group_gerencia')
        importar(cls.env, gerencia)
        cls.env['dcasa.envio.tarifa'].search([], limit=1).with_user(gerencia).action_aprobar()
        # Los colchones del catálogo de ejemplo saldrían antes en «Colchones»: el chat de prueba ve solo los suyos.
        cls.env['product.template'].search([('name', 'ilike', 'colch'), ('id', '!=', cls.colchon.id)]).write(
            {'is_published': False})

    def setUp(self):
        super().setUp()
        if comun.websocket is None:
            # Sin websocket-client (el CI) Odoo salta cada navegador; sin esto, lo que se afirma después de los subtests
            # (p. ej. cuántas ubicaciones recibió el Worker) fallaría sin que el navegador haya corrido.
            self.skipTest('websocket-client module is not installed')
        self.worker = WorkerSimulado(TOKEN_WORKER, self.base_url(), TOKEN_ODOO,
                                     cookie_odoo=lambda: f'{TEST_CURSOR_COOKIE_NAME}={self.http_request_key}')
        puerto = self.worker.iniciar()
        self.addCleanup(self.worker.detener)
        entorno = patch.dict(os.environ, {'JUAN_URL': f'http://127.0.0.1:{puerto}'})
        entorno.start()
        self.addCleanup(entorno.stop)

    @contextlib.contextmanager
    def chrome(self, ancho, alto=ALTO, movil=True, reducido=False):
        self.browser_size = f'{ancho}x{alto}'
        browser = ChromeBrowser(self, headless=True)
        with self.allow_requests(browser=browser), contextlib.ExitStack() as atexit:
            atexit.callback(self._wait_remaining_requests)
            atexit.enter_context(browser.cleanup)
            self.authenticate(None, None, browser=browser)
            self.cr.flush()
            self.cr.clear()
            browser._websocket_request('Emulation.setDeviceMetricsOverride', params={
                'width': ancho, 'height': alto, 'deviceScaleFactor': 2 if movil else 1, 'mobile': movil})
            if movil:
                browser._websocket_request('Emulation.setTouchEmulationEnabled', params={'enabled': True})
            if reducido:
                browser._websocket_request('Emulation.setEmulatedMedia', params={
                    'features': [{'name': 'prefers-reduced-motion', 'value': 'reduce'}]})
            browser._websocket_request('Browser.grantPermissions', params={
                'permissions': ['geolocation'], 'origin': self.base_url()})
            browser._websocket_request('Emulation.setGeolocationOverride', params={
                'latitude': COSTA[0], 'longitude': COSTA[1], 'accuracy': 30})
            yield browser

    def evaluar(self, browser, expresion, timeout=120):
        res = browser._websocket_request('Runtime.evaluate', params={
            'expression': expresion, 'awaitPromise': True, 'returnByValue': True}, timeout=timeout)
        resultado = res['result']
        self.assertFalse(res.get('exceptionDetails'), f'JavaScript falló: {res}')
        self.assertNotEqual(resultado.get('subtype'), 'error', f'JavaScript falló: {res}')
        return resultado.get('value')


@tagged('post_install', '-at_install')
class TestChatEnElNavegador(NavegadorCase):

    def revisar_chat(self, r, ancho):
        self.assertEqual(r['saludos'], 1, 'Brian se presenta una sola vez')
        self.assertEqual(r['expandido'], 'true')
        self.assertEqual(r['tarjeta'], 'ZZBT Colchón Queen', 'la tarjeta sale de buscar_productos de Odoo')
        self.assertEqual(r['precio'], '$278.00+ ITBMS')
        self.assertEqual(r['ver'], self.colchon.website_url)
        self.assertEqual(r['listo'], 1)
        self.assertEqual(r['navbar'], '2', 'el globo del carrito de la cabecera se pone al día')
        self.assertEqual(r['total'], '$834.00')
        self.assertTrue(r['pdf'])
        self.assertTrue(r['privacidad'])
        self.assertEqual(r['lugar'], 'Costa Inventada')
        self.assertIn('Costa Inventada', r['envio'])
        self.assertTrue(r['ampliado']['clase'])
        self.assertGreaterEqual(r['ampliado']['vitrina'], 1, 'la cuadrícula con los productos de la conversación')
        if ancho >= 1000:
            self.assertGreater(r['ampliado']['ancho'], 900)
        self.assertEqual(r['trasPrimerEsc'], {'abierto': True, 'ampliado': False})
        self.assertTrue(r['foco'], 'al cerrar, el foco vuelve a la burbuja')
        self.assertTrue(r['sinScrollDeLado'])

    def test_el_chat_de_punta_a_punta_en_el_celular_y_la_computadora(self):
        for ancho, movil in ((390, True), (1366, False)):
            with self.subTest(ancho=ancho), self.chrome(ancho, 844 if movil else 768, movil=movil) as browser:
                antes = self.env['dcasa.brian.tienda.calificacion'].sudo().search_count([])
                ubicaciones = self.worker.ubicaciones
                browser.navigate_to(self.base_url() + '/', wait_stop=True)
                r = self.evaluar(browser, CHAT)
                self.revisar_chat(r, ancho)
                self.assertEqual(self.env['dcasa.brian.tienda.calificacion'].sudo().search_count([]), antes + 1)
                self.assertEqual(self.worker.ubicaciones, ubicaciones + 1, 'la ubicación llegó al Worker una vez')
        # La ubicación nunca llegó a guardarse, y lo que preguntó el chat no queda en la auditoría de Brian.
        self.assertFalse(self.env['brian.accion'].sudo().search([('herramienta', '=', 'juan_cotizar_envio')]))
        self.assertFalse([c for c in self.worker.recibidos if 'ubicacion' in c])

    def test_las_funciones_de_la_pagina(self):
        with self.chrome(390) as browser:
            browser.navigate_to(self.base_url() + '/', wait_stop=True)
            self.evaluar(browser, '(async () => { ' + ESPERAR + ' return true; })()')
            r = self.evaluar(browser, PURAS)
        self.assertEqual(r['poses'], {
            'inicio': 'asomado_burbuja', 'catalogo': 'con_laptop', 'ficha': 'marco_foto', 'carrito': 'bolsita',
            'socios': 'fidelidad', 'visitanos': 'mapa', 'foto': 'marco_foto', 'otra': 'asomado_burbuja',
            'colchones': 'cama', 'cocina': 'cocina', 'oficina': 'escritorio', 'salas': 'con_laptop',
            'noche': 'durmiendo'})
        dia = set(DE_DIA)
        self.assertEqual(set(r['cobertura']['todas']), dia, 'entre el Inicio, el catálogo, la ficha, el carrito y Visítanos')
        self.assertEqual(set(r['cobertura']['inicio']), dia, 'el Inicio, la página más larga, pasa por todas')
        self.assertFalse(r['cobertura']['durmiendo'], 'dormido es solo de noche')
        self.assertEqual(r['activa'], ['cama', 'cocina', None, None])
        self.assertEqual(r['minimo'], 2500)
        en_inicio = [p for p, _orden in r['enInicio']]
        self.assertEqual(en_inicio[0], 'asomado_burbuja', 'arriba, la de la página')
        self.assertEqual([o for _p, o in r['enInicio']], list(range(len(en_inicio))))
        for pose in ('saludando', 'con_laptop', 'cama', 'cocina', 'escritorio', 'fidelidad', 'marco_foto', 'cinta_metrica',
                     'burbuja_chat', 'mapa'):
            self.assertIn(pose, en_inicio, 'secciones que el Inicio siempre tiene')
        # 10:00 a. m. de un viernes (abierto), 9:00 p. m. del viernes (cerrado), 5:30 p. m. del domingo (cerrado).
        self.assertEqual(r['noche'], [False, True, True])
        self.assertEqual(r['urls'], ['/shop/x-1', None, None, '/shop/x-2', None])
        self.assertEqual(r['precio'], ['$278.00', '+ ITBMS'])
        self.assertEqual(r['wa'], "Hola D'CASA, vengo del chat de la web. Tengo en el carrito: 2 × Colchón.")


@tagged('post_install', '-at_install')
class TestBurbujaEnLaPagina(NavegadorCase):

    def test_la_burbuja_a_360_390_430_y_1366(self):
        rutas = ('/', '/shop', self.colchon.website_url, '/shop/cart')
        for ancho, movil in ((360, True), (390, True), (430, True), (1366, False)):
            for ruta in rutas:
                with self.subTest(ancho=ancho, ruta=ruta), self.chrome(ancho, movil=movil) as browser:
                    browser.navigate_to(self.base_url() + ruta, wait_stop=True)
                    m = self.evaluar(browser, BURBUJA)
                    b = m['burbuja']
                    self.assertEqual(m['pose'], m['esperada'], 'la pose del tipo de página (o dormido de noche)')
                    self.assertEqual(m['etiqueta'], 'Abrir el chat de la tienda')
                    self.assertGreaterEqual(b['ancho'], 56)
                    if not m['aparteAlCargar']:   # apartada (un botón de la página quedaría debajo) no cuenta
                        self.assertGreaterEqual(b['x'], 0)
                        self.assertLessEqual(b['derecha'], m['pantalla'])
                        self.assertLessEqual(b['abajo'], m['alto'])
                    self.assertTrue(m['sinScrollDeLado'])
                    if m.get('barra'):
                        self.assertLessEqual(b['abajo'], m['barra']['y'] - 4,
                                             'no tapa la barra de «Agregar al carrito» de la ficha')
                    if 'aparte' in m:
                        self.assertFalse(m['tapaVisible'], 'nunca tapa «Pregunta por este mueble por WhatsApp»')
                        if movil:
                            self.assertTrue(m['aparte'])
                            self.assertTrue(m['vuelve'])

    def test_con_movimiento_reducido_quieto(self):
        with self.chrome(390, reducido=True) as browser:
            browser.navigate_to(self.base_url() + '/', wait_stop=True)
            r = self.evaluar(browser, QUIETO)
        self.assertTrue(r['reducido'])
        self.assertEqual(r['animaciones'], [], 'nada del chat se mueve')


@tagged('post_install', '-at_install')
class TestConElEditor(TiendaCase):
    """La administradora con el editor del sitio (la trampa del error 500 del lote 1). En producción nadie tiene el
    editor (dcasa_interfaz se lo quita a todos): aquí se le da a propósito para abrir el modo edición."""

    def test_la_administradora_abre_el_sitio_en_modo_edicion(self):
        admin = self.env.ref('base.user_admin')
        admin.group_ids = [Command.link(self.env.ref('website.group_website_designer').id)]
        self.start_tour(self.env['website'].get_client_action_url('/'), 'dcasa_brian_tienda_editor', login='admin',
                        timeout=180)


@tagged('post_install', '-at_install')
class TestPoseAlBajar(NavegadorCase):
    """La burbuja cerrada sigue a la sección que el visitante tiene en pantalla (pedido de la dueña, 2026-11-14): un
    cambio cada 2,5 s como mucho, donde se detiene; ni con el chat abierto, ni de noche, ni con movimiento reducido."""

    def setUp(self):
        super().setUp()
        # De día a cualquier hora (si no, de noche el robot duerme y no cambia: la prueba dependería de la hora).
        self.env['dcasa.juan.ajustes'].obtener().write({
            'horario_inicio': 0.0, 'horario_fin': 23.98, 'horario_fin_domingo': 0.0, 'dia_domingo': True,
            'dia_lunes': True, 'dia_martes': True, 'dia_miercoles': True, 'dia_jueves': True, 'dia_viernes': True,
            'dia_sabado': True})
        self.env.registry.clear_cache('templates')   # Odoo guarda la portada (con el horario) una hora

    def test_en_el_inicio_sigue_a_la_seccion_donde_se_detiene(self):
        with self.chrome(390) as browser:
            browser.navigate_to(self.base_url() + '/', wait_stop=True)
            r = self.evaluar(browser, POSE_EN_EL_INICIO)
        self.assertEqual((r['quieta'], r['alLlegar']), (0, 'asomado_burbuja'), 'sin moverse, la de la página')
        self.assertEqual(r['trasPasarRapido'], ['fidelidad'], 'al pasar rápido, cuenta donde se detiene')
        self.assertEqual(r['cambios'], ['fidelidad', 'marco_foto', 'cinta_metrica', 'mapa'])
        self.assertGreaterEqual(r['minimo'], 2400, 'nunca dos cambios en menos de 2,5 s')
        self.assertTrue(r['sinScrollDeLado'])

    def test_en_la_ficha_y_con_el_chat_abierto(self):
        with self.chrome(1366, 768, movil=False) as browser:
            browser.navigate_to(self.base_url() + self.colchon.website_url, wait_stop=True)
            r = self.evaluar(browser, POSE_EN_LA_FICHA)
        self.assertEqual((r['quieta'], r['alLlegar']), (0, 'marco_foto'))
        self.assertEqual(r['alMoverse'], ['bolsita'], 'el precio y «Agregar al carrito»')
        self.assertEqual(r['conElChatAbierto'], 0, 'con el chat abierto la burbuja no cambia')
        self.assertEqual(r['alCerrar'], 'saludando', 'al cerrarlo, la del pie, donde quedó')
        self.assertGreaterEqual(r['minimo'], 2400)

    def test_de_noche_dormido_y_con_movimiento_reducido_quieto(self):
        with self.chrome(390, reducido=True) as browser:
            browser.navigate_to(self.base_url() + self.colchon.website_url, wait_stop=True)
            r = self.evaluar(browser, SIN_CAMBIOS)
        self.assertEqual((r['alLlegar'], r['cambios'], r['ahora']), ('marco_foto', [], 'marco_foto'))
        # De noche: hoy (hora de Panamá) cerrado. La ficha no se guarda en la memoria de páginas de Odoo.
        hoy = datetime.now(pytz.timezone('America/Panama')).isoweekday() % 7   # 0 = domingo, como el JS
        campos = ['dia_domingo', 'dia_lunes', 'dia_martes', 'dia_miercoles', 'dia_jueves', 'dia_viernes', 'dia_sabado']
        self.env['dcasa.juan.ajustes'].obtener().write({c: i != hoy for i, c in enumerate(campos)})
        with self.chrome(390) as browser:
            browser.navigate_to(self.base_url() + self.colchon.website_url, wait_stop=True)
            r = self.evaluar(browser, SIN_CAMBIOS)
        self.assertEqual((r['alLlegar'], r['cambios'], r['ahora']), ('durmiendo', [], 'durmiendo'))


@tagged('post_install', '-at_install')
class TestBrianDeNoche(NavegadorCase):
    """Los dos interruptores de la noche (Sitio web › Brian de la tienda; pedido de la dueña, 2026-11-15): de fábrica,
    Brian saluda como de día (no dice que no hay vendedoras) y el robot de la burbuja duerme."""

    def setUp(self):
        super().setUp()
        # Hoy (hora de Panamá) cerrado. Se prueba en la ficha: Odoo no la guarda en su memoria de páginas.
        hoy = datetime.now(pytz.timezone('America/Panama')).isoweekday() % 7   # 0 = domingo, como el JS
        campos = ['dia_domingo', 'dia_lunes', 'dia_martes', 'dia_miercoles', 'dia_jueves', 'dia_viernes', 'dia_sabado']
        self.env['dcasa.juan.ajustes'].obtener().write({c: i != hoy for i, c in enumerate(campos)})

    def test_el_saludo_de_noche_con_y_sin_aviso(self):
        cerrada = 'Ahora la tienda está cerrada'
        with self.chrome(1366, 768, movil=False) as browser:
            browser.navigate_to(self.base_url() + self.colchon.website_url, wait_stop=True)
            r = self.evaluar(browser, NOCHE_CHAT)
        self.assertEqual((r['noche'], r['avisar']), (True, False), 'el pase dice la verdad y que no hay que avisar')
        self.assertEqual(r['burbuja'], 'durmiendo', 'el robot de la burbuja sí duerme')
        self.assertEqual(r['globos'][:2], ['Hola, soy Brian. ¿Qué buscas hoy?', 'Con gusto te ayudo a encontrar tu '
                         'mueble, ver precios, calcular el envío o dejarte el carrito listo.'], 'saluda como de día')
        self.assertFalse([g for g in r['globos'] if cerrada in g])
        self.assertNotIn('durmiendo', r['poses'], 'el avatar del chat no se duerme')
        self.env['ir.config_parameter'].sudo().set_param('dcasa_brian_tienda.avisar_cerrado', 'True')
        with self.chrome(1366, 768, movil=False) as browser:
            browser.navigate_to(self.base_url() + self.colchon.website_url, wait_stop=True)
            r = self.evaluar(browser, NOCHE_CHAT)
        self.assertEqual((r['noche'], r['avisar']), (True, True))
        self.assertTrue(r['globos'][1].startswith(cerrada), r['globos'])
        self.assertIn('durmiendo', r['poses'], 'con el aviso, el avatar se duerme mientras escribe')

    def test_la_burbuja_de_noche_con_y_sin_dormir(self):
        with self.chrome(1366, 768, movil=False) as browser:
            browser.navigate_to(self.base_url() + self.colchon.website_url, wait_stop=True)
            r = self.evaluar(browser, NOCHE_BURBUJA)
        self.assertEqual((r['alLlegar'], r['cambios']), ('durmiendo', []), 'de fábrica duerme y no cambia al bajar')
        self.env['ir.config_parameter'].sudo().set_param('dcasa_brian_tienda.dormir_de_noche', 'False')
        with self.chrome(1366, 768, movil=False) as browser:
            browser.navigate_to(self.base_url() + self.colchon.website_url, wait_stop=True)
            r = self.evaluar(browser, NOCHE_BURBUJA)
        self.assertEqual((r['alLlegar'], r['cambios']), ('marco_foto', ['bolsita']), 'como de día')
