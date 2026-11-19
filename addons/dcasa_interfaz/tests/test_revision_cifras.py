# ruff: noqa: E501  (JavaScript del navegador embebido en texto)
"""Revisión independiente (2026-11-19): ataques a ``cifras_que_suben.js`` y a la tarjeta de cobros de Por día.

* Valores raros (NaN, Infinity, texto, enormes, negativos) y texto con HTML en prefijo y sufijo: nada se interpreta
  como HTML y nada lanza.
* Fugas: cada cuadro pedido se dispara o se cancela (con cifras que cambian, que salen de la pantalla y ``parar``).
* Inicio igual: el algoritmo de ``subirCifras`` de antes (32cc9b28) y el del módulo dan los mismos números a cada
  cuadro en las secuencias del Inicio; las diferencias que haya se listan.
* La tarjeta de cobros en el navegador con un diario con HTML en el nombre y clics seguidos en Día/Semana/Quincena/Mes.
"""
import re
from datetime import timedelta
from pathlib import Path

from odoo.tests import HttpCase, TransactionCase, tagged

from .test_cifras_que_suben import ESPIAR_JS
from .test_pantallas_navegador import COMUN_JS, PantallasMixin

# El algoritmo de inicio.js::subirCifras de la producción anterior (32cc9b28), tal cual, para compararlo.
VIEJO_JS = r"""
    class Viejo {
        constructor(dinero) { this.dinero = dinero; this.cifrasPintadas = new WeakMap(); this.subidas = new Map(); }
        subirCifras(raiz, browser) {
            const quieto = false;
            for (const el of raiz.querySelectorAll(".o_dcasa_sube")) {
                const hasta = Number(el.dataset.valor);
                const desde = this.cifrasPintadas.get(el) || 0;
                if (!Number.isFinite(hasta) || hasta === desde) { continue; }
                this.cifrasPintadas.set(el, hasta);
                this.dejarDeSubir(el, browser);
                if (quieto) { continue; }
                const pintar = el.dataset.formato === "moneda" ? (valor) => this.dinero(valor)
                    : (valor) => new Intl.NumberFormat("en-US").format(Math.round(valor));
                const empieza = browser.performance.now();
                const paso = (ahora) => {
                    const avance = Math.min(1, Math.max(0, (ahora - empieza) / 700));
                    if (avance >= 1 || !el.isConnected) { this.dejarDeSubir(el, browser); return; }
                    el.dataset.sube = pintar(desde + (hasta - desde) * (1 - (1 - avance) ** 3));
                    this.subidas.set(el, browser.requestAnimationFrame(paso));
                };
                el.dataset.sube = pintar(desde);
                this.subidas.set(el, browser.requestAnimationFrame(paso));
            }
        }
        dejarDeSubir(el, browser) {
            if (this.subidas.has(el)) { browser.cancelAnimationFrame(this.subidas.get(el)); this.subidas.delete(el); }
            delete el.dataset.sube;
        }
    }
"""

RELOJ_JS = r"""
    await esperar(() => odoo.loader.modules.has('@web/core/browser/browser'), 'browser');
    const { browser } = odoo.loader.modules.get('@web/core/browser/browser');
    // Un reloj y unos cuadros de animación a mano: la prueba decide cuándo pasa cada milisegundo.
    const falso = { t: 0, cola: new Map(), n: 0, vivos: new Set() };
    const real = { performance: browser.performance, raf: browser.requestAnimationFrame, caf: browser.cancelAnimationFrame };
    browser.performance = { now: () => falso.t };
    browser.requestAnimationFrame = (cb) => { const id = ++falso.n; falso.cola.set(id, cb); falso.vivos.add(id); return id; };
    browser.cancelAnimationFrame = (id) => { falso.cola.delete(id); falso.vivos.delete(id); };
    const avanzar = (ms) => {
        falso.t += ms;
        const cbs = [...falso.cola.entries()];
        falso.cola.clear();
        for (const [id, cb] of cbs) { falso.vivos.delete(id); cb(falso.t); }
    };
    const restaurar = () => { browser.performance = real.performance; browser.requestAnimationFrame = real.raf; browser.cancelAnimationFrame = real.caf; };
"""


FUENTES = Path(__file__).resolve().parents[1] / 'static' / 'src'


@tagged('post_install', '-at_install')
class TestRevisionCifrasEstatico(TransactionCase):

    def test_el_texto_final_se_escribe_como_lo_escribe_la_subida(self):
        """Una cifra «entero» que sube pone las comas de miles (``1,500``); si el texto final de la plantilla es el
        número crudo (``1500``), al terminar de subir el número cambia de forma. El texto final tiene que salir con
        el mismo formato que la subida (``numero(...)``)."""
        crudas = []
        for archivo in sorted((FUENTES / 'xml').glob('*.xml')):
            if archivo.name == 'inicio.xml':
                continue    # el Inicio escribe sus cifras con su propia función (cifra(c))
            xml = archivo.read_text(encoding='utf-8')
            for etiqueta in re.finditer(r'<(?:strong|span|small)[^>]*\bo_dcasa_sube\b[^>]*data-formato="entero"[^>]*/?>', xml):
                salida = re.search(r't-out="([^"]+)"', etiqueta.group(0))
                if salida and 'numero(' not in salida.group(1):
                    crudas.append(f'{archivo.name}: t-out="{salida.group(1)}"')
        self.assertEqual(crudas, [], 'cifras «entero» cuyo texto final no lleva el formato de la subida (comas de miles)')


@tagged('post_install', '-at_install')
class TestRevisionCifrasModulo(HttpCase):

    def test_valores_raros_y_html_en_prefijo_y_sufijo(self):
        codigo = '(async () => {' + COMUN_JS + ESPIAR_JS + r"""
            const modulo = '@dcasa_interfaz/js/cifras_que_suben';
            await esperar(() => odoo.loader.modules.has(modulo), 'el módulo de las cifras que suben');
            const { CifrasQueSuben, escribirCifra } = odoo.loader.modules.get(modulo);
            const errores = [];
            window.addEventListener('error', (ev) => errores.push(String(ev.message)));
            window.addEventListener('unhandledrejection', (ev) => errores.push(String(ev.reason)));
            const dinero = (v) => (v < 0 ? '-' : '') + '$' + Math.abs(v).toFixed(2);
            const raiz = document.createElement('div');
            document.body.appendChild(raiz);
            const cifra = (crudo, formato, texto, extra = {}) => {
                const el = document.createElement('strong');
                el.className = 'o_dcasa_sube';
                if (formato) { el.dataset.formato = formato; }
                if (crudo !== undefined) { el.dataset.valor = crudo; }
                Object.assign(el.dataset, extra);
                el.textContent = texto;
                raiz.appendChild(el);
                return el;
            };
            const vistos = [];
            const ojo = new MutationObserver((cambios) => { for (const c of cambios) { const t = c.target.getAttribute('data-sube'); if (t !== null) { vistos.push(t); } } });
            ojo.observe(raiz, { attributes: true, attributeFilter: ['data-sube'], subtree: true });
            const cifras = new CifrasQueSuben(dinero);
            const crudos = ['NaN', 'Infinity', '-Infinity', 'null', 'undefined', '', ' ', '1e400', '-5', '1e21', '0x10', '1,5', '0', '-0',
                            'abc', 'true', '١٢٣', '1e-9', '9007199254740993', '-1e21'];
            const filas = [];
            for (const crudo of crudos) {
                for (const formato of ['moneda', 'entero', 'unidades', 'decimal', undefined]) {
                    filas.push([cifra(crudo, formato, 'FINAL-' + crudo + '-' + formato, formato === 'decimal' ? { decimales: 'abc' } : {}), crudo, formato]);
                }
            }
            cifras.subir(raiz);
            await pausa(900);
            for (const [el, crudo, formato] of filas) {
                if (el.hasAttribute('data-sube')) { falla(`quedó a medias: ${crudo}/${formato}: ${el.dataset.sube}`); }
                if (el.textContent !== 'FINAL-' + crudo + '-' + formato) { falla('el texto real cambió: ' + el.textContent); }
            }
            const malos = vistos.filter((t) => /NaN|undefined|Infinity|null/.test(t));
            if (malos.length) { falla('números a medias con basura: ' + malos.slice(0, 5).join(' | ')); }
            if (cifras.cuadros.size) { falla('cuadros pendientes: ' + cifras.cuadros.size); }

            // --- HTML en prefijo y sufijo: texto, nunca HTML ---
            const xss = cifra('100', 'decimal', 'FINAL', {
                decimales: '1', prefijo: '<img src=x onerror="window.__xss=1">', sufijo: '</strong><script>window.__xss=2</script>' });
            cifras.subir(raiz);
            const medio = xss.dataset.sube;
            if (!medio.includes('<img src=x onerror="window.__xss=1">')) { falla('el prefijo debía quedar como texto: ' + medio); }
            if (raiz.querySelector('img, script') || window.__xss !== undefined) { falla('el HTML del prefijo se interpretó'); }
            await pausa(900);
            if (xss.hasAttribute('data-sube')) { falla('terminó a medias'); }
            if (raiz.querySelector('img, script') || window.__xss !== undefined) { falla('el HTML se interpretó al terminar'); }
            ojo.disconnect();

            // --- Ni una raiz vacía, ni parar dos veces, ni «moneda» sin la función de dinero ---
            cifras.subir(null); cifras.subir(undefined); cifras.parar(); cifras.parar();
            const sinDinero = new CifrasQueSuben();
            const el2 = cifra('1234.5', 'moneda', '$1234.50');
            sinDinero.subir(raiz);
            await pausa(900);
            if (el2.hasAttribute('data-sube') || el2.textContent !== '$1234.50') { falla('sin dinero() rompió la cifra'); }
            // --- Negativas: de -50 a 50 pasa por 0 sin «-$0.00» fijo ni basura ---
            const neg = cifra('-50', 'moneda', '-$50.00');
            cifras.subir(raiz);
            await pausa(900);
            neg.dataset.valor = '50'; neg.textContent = '$50.00';
            const espia = espiar(neg);
            cifras.subir(raiz);
            await pausa(900);
            espia.fin();
            if (espia.vistos.length < 3 || espia.vistos.some((t) => /NaN|undefined/.test(t))) { falla('de negativo a positivo: ' + espia.vistos.join(' | ')); }
            if (errores.length) { falla('errores en la página: ' + errores.join(' | ')); }
            raiz.remove();
        """ + "console.log('test successful'); })();"
        self.browser_js('/odoo/action-dcasa_interfaz.action_dcasa_inicio', codigo, login='admin', timeout=120)

    def test_cada_cuadro_pedido_se_dispara_o_se_cancela(self):
        codigo = '(async () => {' + COMUN_JS + RELOJ_JS + r"""
            const modulo = '@dcasa_interfaz/js/cifras_que_suben';
            await esperar(() => odoo.loader.modules.has(modulo), 'el módulo');
            const { CifrasQueSuben } = odoo.loader.modules.get(modulo);
            const dinero = (v) => '$' + v.toFixed(2);
            const raiz = document.createElement('div');
            document.body.appendChild(raiz);
            const cifras = new CifrasQueSuben(dinero);
            const hacer = (n) => {
                const els = [];
                for (let i = 0; i < n; i++) {
                    const el = document.createElement('span');
                    el.className = 'o_dcasa_sube'; el.dataset.formato = 'moneda'; el.dataset.valor = String(100 + i); el.textContent = dinero(100 + i);
                    raiz.appendChild(el); els.push(el);
                }
                return els;
            };
            try {
                const els = hacer(300);
                cifras.subir(raiz); avanzar(100);
                els.forEach((el, i) => { if (i % 2) { el.dataset.valor = String(5000 + i); el.textContent = dinero(5000 + i); } });
                cifras.subir(raiz); avanzar(100);
                els.forEach((el, i) => { if (i % 3 === 0) { el.remove(); } });
                cifras.subir(raiz); avanzar(100);
                els.forEach((el, i) => { if (i % 5 === 0 && el.isConnected) { el.dataset.valor = 'NaN'; } });
                cifras.subir(raiz);
                if (cifras.cuadros.size !== falso.vivos.size) { throw new Error(`cuadros del módulo ${cifras.cuadros.size} ≠ cuadros vivos ${falso.vivos.size}`); }
                for (let i = 0; i < 20; i++) { avanzar(50); }
                if (falso.vivos.size || cifras.cuadros.size) { throw new Error(`tras 1 s quedan cuadros: ${falso.vivos.size}/${cifras.cuadros.size}`); }
                for (const el of raiz.querySelectorAll('.o_dcasa_sube')) {
                    if (el.hasAttribute('data-sube')) { throw new Error('una cifra quedó a medias tras terminar'); }
                }
                // parar() en pleno vuelo.
                const otras = hacer(50);
                cifras.subir(raiz); avanzar(120);
                cifras.parar();
                if (falso.vivos.size || cifras.cuadros.size) { throw new Error(`tras parar quedan cuadros: ${falso.vivos.size}/${cifras.cuadros.size}`); }
                if (otras.some((el) => el.hasAttribute('data-sube'))) { throw new Error('tras parar, una cifra quedó a medias'); }
                // Y se puede volver a usar.
                otras[0].dataset.valor = '9'; otras[0].textContent = dinero(9);
                cifras.subir(raiz); avanzar(100); avanzar(700);
                if (otras[0].hasAttribute('data-sube') || falso.vivos.size) { throw new Error('no se pudo reusar tras parar'); }
            } finally {
                restaurar();
                raiz.remove();
            }
        """ + "console.log('test successful'); })();"
        self.browser_js('/odoo/action-dcasa_interfaz.action_dcasa_inicio', codigo, login='admin', timeout=120)

    def test_el_inicio_de_antes_y_el_modulo_dan_los_mismos_numeros_a_cada_cuadro(self):
        """El Inicio no debe cambiar: con las secuencias que el Inicio vive (abrir, cambiar de periodo cuando la subida
        ya terminó, volver al mismo valor, un valor que no cambia) el algoritmo de antes y el módulo dan EXACTAMENTE
        los mismos números a cada cuadro.

        La ÚNICA diferencia, aceptada a propósito (2026-11-19): si el valor cambia a MITAD de una subida, el código de
        antes saltaba al valor al que iba la subida anterior y volvía a subir desde ahí; el módulo sigue desde el número
        que se veía (más suave, sin saltos). La prueba la fija: esa secuencia SÍ difiere, y difiere así y no de otra
        manera."""
        codigo = '(async () => {' + COMUN_JS + RELOJ_JS + VIEJO_JS + r"""
            const modulo = '@dcasa_interfaz/js/cifras_que_suben';
            await esperar(() => odoo.loader.modules.has(modulo), 'el módulo');
            const { CifrasQueSuben } = odoo.loader.modules.get(modulo);
            const dinero = (v) => '$' + v.toFixed(2);
            const crear = (formato) => {
                const raiz = document.createElement('div');
                document.body.appendChild(raiz);
                const el = document.createElement('span');
                el.className = 'o_dcasa_sube'; el.dataset.formato = formato;
                raiz.appendChild(el);
                return { raiz, el };
            };
            const poner = (el, valor, formato) => { el.dataset.valor = String(valor); el.textContent = formato === 'moneda' ? dinero(valor) : String(valor); };
            const correr = (formato, pasos) => {
                const A = crear(formato), B = crear(formato);
                const viejo = new Viejo(dinero), nuevo = new CifrasQueSuben(dinero);
                const tabla = [];
                let t = 0;
                for (const [en, valor] of pasos) {
                    while (t < en) { avanzar(16); t += 16; tabla.push([t, A.el.dataset.sube ?? null, B.el.dataset.sube ?? null]); }
                    poner(A.el, valor, formato); poner(B.el, valor, formato);
                    viejo.subirCifras(A.raiz, browser); nuevo.subir(B.raiz);
                    tabla.push([t, A.el.dataset.sube ?? null, B.el.dataset.sube ?? null]);
                }
                for (let i = 0; i < 60; i++) { avanzar(16); t += 16; tabla.push([t, A.el.dataset.sube ?? null, B.el.dataset.sube ?? null]); }
                A.raiz.remove(); B.raiz.remove();
                return tabla;
            };
            const diferencias = (tabla) => tabla.filter(([, a, b]) => a !== b);
            const resultados = {};
            try {
                for (const formato of ['moneda', 'entero']) {
                    // Lo que vive el Inicio: abrir, cambiar de periodo ya asentada la cifra, volver, y que no cambie.
                    resultados['sin_cambio_a_medias_' + formato] = diferencias(correr(formato, [[0, 1500.5], [1000, 1500.5], [1200, 320], [2400, 1500.5], [3600, 0], [4800, 77]])).length;
                    resultados['primera_en_cero_' + formato] = diferencias(correr(formato, [[0, 0], [100, 0], [200, 50]])).length;
                    resultados['negativa_' + formato] = diferencias(correr(formato, [[0, -40], [1000, 25]])).length;
                    // Cambia a mitad de una subida: la ÚNICA diferencia aceptada (el módulo sigue desde el número que se veía).
                    const tabla = correr(formato, [[0, 1000], [300, 5]]);
                    resultados['a_medias_' + formato] = diferencias(tabla).length;
                    const k = tabla.findIndex(([, a, b]) => a !== b);
                    if (k < 1) { throw new Error('el cambio a mitad de una subida debía diferir: ' + formato); }
                    const anteriorFormateado = formato === 'moneda' ? dinero(1000) : '1,000';
                    if (tabla[k][1] !== anteriorFormateado) {
                        throw new Error(`el código de antes saltaba al valor anterior (${anteriorFormateado}): ${tabla[k][1]}`);
                    }
                    if (tabla[k][2] !== tabla[k - 1][2] || tabla[k][2] === tabla[k][1]) {
                        throw new Error(`el módulo sigue desde el número que se veía (${tabla[k - 1][2]}): ${tabla[k][2]}`);
                    }
                    // Pasada la interrupción, las dos terminan igual: nada queda a medias y el texto es el mismo.
                    const ultimo = tabla[tabla.length - 1];
                    if (ultimo[1] !== null || ultimo[2] !== null) { throw new Error('quedó a medias al terminar: ' + JSON.stringify(ultimo)); }
                }
            } finally { restaurar(); }
            console.log('REVISION_INICIO ' + JSON.stringify(resultados));
            const iguales = Object.entries(resultados).filter(([k]) => !k.startsWith('a_medias')).filter(([, n]) => n !== 0);
            if (iguales.length) { throw new Error('el Inicio cambió de números: ' + JSON.stringify(iguales)); }
            const aMedias = Object.entries(resultados).filter(([k]) => k.startsWith('a_medias')).filter(([, n]) => n === 0);
            if (aMedias.length) { throw new Error('la diferencia aceptada (cambio a mitad de una subida) desapareció: ' + JSON.stringify(aMedias)); }
        """ + "console.log('test successful'); })();"
        self.browser_js('/odoo/action-dcasa_interfaz.action_dcasa_inicio', codigo, login='admin', timeout=120)


@tagged('post_install', '-at_install')
class TestRevisionTarjetaDeCobros(PantallasMixin, HttpCase):
    """La tarjeta «Cobrado por forma de pago» de Por día en Chrome: texto con HTML y clics seguidos."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.malo = cls.env['account.journal'].create({'name': '<img src=x onerror=window.__xss=1>', 'type': 'bank',
                                                      'code': 'RVXS'})
        cls.otro = cls.env['account.journal'].create({'name': 'Efectivo revision nav', 'type': 'cash', 'code': 'RVEF'})
        # Un cobro hoy, otro hace dos días (puede caer en otra semana o mes: sirve para cambiar las cifras) y otro hace 40.
        for monto, atras, diario in ((120.0, 0, cls.malo), (80.0, 0, cls.otro), (55.0, 2, cls.otro), (300.0, 40, cls.malo)):
            pago = cls.env['account.payment'].create({
                'payment_type': 'inbound', 'partner_type': 'customer', 'partner_id': cls.cliente.id, 'amount': monto,
                'date': cls.hoy - timedelta(days=atras), 'journal_id': diario.id})
            pago.action_post()

    def test_diario_con_html_y_clics_seguidos_en_los_cuatro_periodos(self):
        codigo = '(async () => {' + COMUN_JS + ESPIAR_JS + r"""
            const errores = [];
            window.addEventListener('error', (ev) => errores.push(String(ev.message)));
            await esperar(() => document.querySelector('.o_dcasa_pd_cobros'), 'la tarjeta de cobros');
            const tarjetas = () => [...document.querySelectorAll('.o_dcasa_pd_cobros')].filter((t) => t.offsetParent !== null);
            await esperar(() => tarjetas().length === 1 && !tarjetas()[0].classList.contains('o_cargando'), 'una sola tarjeta a la vista', 60);
            if (window.__xss !== undefined) { throw new Error('el nombre del diario se ejecutó como HTML'); }
            if (document.querySelector('.o_dcasa_pd_cobros img[src="x"], .o_dcasa_cf_ficha img')) { throw new Error('hay un <img> metido por el nombre del diario'); }
            const fichas = () => [...tarjetas()[0].querySelectorAll('.o_dcasa_cf_ficha .o_dcasa_cf_forma')].map((f) => f.textContent);
            if (!fichas().includes('<img src=x onerror=window.__xss=1>')) { throw new Error('el nombre debía verse como texto: ' + fichas().join(' | ')); }
            const periodo = () => tarjetas()[0].querySelector('.o_dcasa_pd_cobros_periodo').textContent.trim();
            const activo = () => tarjetas()[0].querySelector('.o_dcasa_periodo.o_activo').textContent.trim();
            // Clics seguidos, sin esperar a ninguna respuesta: el último manda.
            const botones = () => Object.fromEntries([...tarjetas()[0].querySelectorAll('.o_dcasa_periodo')].map((b) => [b.textContent.trim(), b]));
            botones()['Semana'].click(); botones()['Quincena'].click(); botones()['Mes'].click(); botones()['Día'].click(); botones()['Semana'].click();
            await esperar(() => !tarjetas()[0].classList.contains('o_cargando'), 'que termine de cargar', 60);
            await pausa(800);
            if (activo() !== 'Semana' || !/^Semana del /i.test(periodo())) { throw new Error('el último clic debía ganar: ' + activo() + ' / ' + periodo()); }
            botones()['Mes'].click(); botones()['Día'].click();
            await esperar(() => !tarjetas()[0].classList.contains('o_cargando'), 'que termine de cargar', 60);
            await pausa(800);
            if (activo() !== 'Día' || !/^Hoy, /i.test(periodo())) { throw new Error('el último clic debía ganar (2): ' + activo() + ' / ' + periodo()); }
            const total = tarjetas()[0].querySelector('.o_dcasa_cf_total .o_dcasa_cf_monto').textContent;
            if (total !== '$200.00') { throw new Error('hoy se cobraron 120 + 80: ' + total); }
            // Cambiar de día con un periodo largo elegido y volver: nada se queda cargando ni con error.
            botones()['Mes'].click();
            await pausa(900);
            if (tarjetas()[0].querySelector('.o_dcasa_error')) { throw new Error('error en la tarjeta: ' + tarjetas()[0].querySelector('.o_dcasa_error').textContent); }
            sinScrollDeCostado('cobros');
            if (errores.length) { throw new Error('errores en la página: ' + errores.join(' | ')); }
        """ + "console.log('test successful'); })();"
        self.browser_size = '1440x900'
        self.browser_js('/odoo/action-dcasa_interfaz.accion_facturado_por_dia', codigo, login='gerencia_rol', timeout=180)
