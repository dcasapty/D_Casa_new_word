"""Las cifras que suben, en todas las pantallas de métricas (pedido de la dueña, 2026-11-19: «todo lo que son nuestras
métricas y estadísticas debería tener esa animación»).

* El módulo compartido (``static/src/js/cifras_que_suben.js``) se prueba en el navegador con elementos de verdad: la
  cifra sube desde 0 y termina en su valor; al cambiar, sube desde donde estaba; si no cambió, no se anima; si cambia a
  medias, sigue desde el número que se veía; con «reducir movimiento» no se mueve; una cifra que sale de la pantalla no
  deja cuadros pendientes.
* El texto de la etiqueta es SIEMPRE el valor final (el número a medias va en ``data-sube``): las pruebas y los lectores
  de pantalla nunca ven un número a medias.
* Cada pantalla que marca cifras tiene su ``t-ref="raiz"`` (sin él, la animación se apaga en silencio).
* Estadísticas, Valor del inventario y el Inicio de siempre suben al abrir y al cambiar.
"""
import json
import re
from datetime import timedelta
from pathlib import Path

from odoo import Command
from odoo.tests import HttpCase, TransactionCase, tagged

from .test_pantallas_navegador import COMUN_JS, PantallasMixin

FUENTES = Path(__file__).resolve().parents[1] / 'static' / 'src'

# Mira cada vez que cambia el número a medias de una cifra («data-sube»): lo que de verdad se vio en pantalla.
ESPIAR_JS = r"""
    const monto = (texto) => Number(String(texto).replace(/[^0-9.-]/g, ''));
    const espiar = (el) => {
        const vistos = [];
        const ojo = new MutationObserver(() => {
            const texto = el.getAttribute('data-sube');
            if (texto !== null) { vistos.push(texto); }
        });
        ojo.observe(el, { attributes: true, attributeFilter: ['data-sube'] });
        return { vistos, fin: () => ojo.disconnect() };
    };
    const pausa = (ms) => new Promise((ok) => setTimeout(ok, ms));
    const falla = (mensaje) => { throw new Error(mensaje); };
"""


@tagged('post_install', '-at_install')
class TestCifrasQueSubenCodigo(TransactionCase):
    """Sin navegador: lo que no puede perderse del código compartido."""

    def test_cada_pantalla_con_cifras_que_suben_tiene_su_referencia(self):
        """Sin ``t-ref="raiz"`` en la raíz de la pantalla, el hook no encuentra las cifras y no sube ninguna."""
        revisadas = 0
        for archivo in sorted((FUENTES / 'xml').glob('*.xml')):
            xml = archivo.read_text(encoding='utf-8')
            for plantilla in re.finditer(r'<t t-name="([^"]+)">(.*?)</t>\s*(?=<t t-name=|</templates>)', xml, re.S):
                nombre, cuerpo = plantilla.groups()
                # Las raíces de la pantalla (el armazón gris que se ve mientras llegan las cifras no cuenta).
                raices = [r for r in re.findall(r'<div[^>]*class="[^"]*\bo_action\b[^"]*"[^>]*>', cuerpo)
                          if 'o_dcasa_arranque' not in r]
                if 'o_dcasa_sube' not in cuerpo or not raices:
                    continue
                revisadas += 1
                for raiz in raices:
                    self.assertIn('t-ref="raiz"', raiz, f'{archivo.name} › {nombre}: la raíz lleva t-ref')
        self.assertGreaterEqual(revisadas, 6, 'Inicio, Por día, Estadísticas, Inventario, Reponer, Movimientos')

    def test_cada_pantalla_con_cifras_que_suben_usa_el_modulo_compartido(self):
        por_dia = (FUENTES / 'js' / 'por_dia.js').read_text(encoding='utf-8')
        self.assertIn('useCifrasQueSuben({ raiz: this.raiz, dinero: (valor) => this.dinero(valor) })', por_dia)
        for pantalla in ('estadisticas', 'valor_inventario'):
            js = (FUENTES / 'js' / f'{pantalla}.js').read_text(encoding='utf-8')
            self.assertIn('FormatoMixin(Component)', js, pantalla)
            self.assertIn('super.setup();', js, f'{pantalla}: sin esto el mixin no pone las cifras')
        for pantalla in ('inicio', 'reponer', 'movimientos'):
            js = (FUENTES / 'js' / f'{pantalla}.js').read_text(encoding='utf-8')
            self.assertRegex(js, r'useCifrasQueSuben\(\{ raiz: this\.raiz', pantalla)
        # La subida vive en un solo sitio: ninguna pantalla trae su propia copia.
        for archivo in (FUENTES / 'js').glob('*.js'):
            if archivo.name == 'cifras_que_suben.js':
                continue
            texto = archivo.read_text(encoding='utf-8')
            self.assertNotIn('requestAnimationFrame(paso)', texto, f'{archivo.name} trae su propia subida de cifras')
            self.assertNotIn('data-sube', texto.replace('«data-sube»', ''), archivo.name)

    def test_el_selector_de_cobros_son_botones_normales_con_aria_pressed(self):
        """Un «radio» de verdad pide las flechas del teclado; el selector no las trae, así que son botones normales
        (Tab y Enter o espacio los manejan solos) con ``aria-pressed``."""
        xml = (FUENTES / 'xml' / 'por_dia.xml').read_text(encoding='utf-8')
        selector = xml[xml.index('o_dcasa_cf_periodos'):xml.index('o_dcasa_cf_pista')]
        self.assertIn('role="group"', selector)
        self.assertIn('t-att-aria-pressed=', selector)
        self.assertNotIn('role="radio', selector)
        self.assertNotIn('aria-checked', selector)

    def test_el_modulo_compartido_cuida_el_movimiento_y_las_fugas(self):
        js = (FUENTES / 'js' / 'cifras_que_suben.js').read_text(encoding='utf-8')
        self.assertIn('prefers-reduced-motion: reduce', js)
        self.assertIn('DURACION_SUBIDA = 700', js, 'la misma duración que el Inicio')
        self.assertIn('1 - (1 - avance) ** 3', js, 'la misma curva que el Inicio')
        self.assertIn('cancelAnimationFrame', js)
        self.assertIn('onWillUnmount(() => cifras.parar())', js, 'al desmontar se cancelan los cuadros pendientes')
        self.assertIn('!el.isConnected', js, 'una cifra que salió de la pantalla no sigue pidiendo cuadros')

    def test_ninguna_pantalla_pone_numeros_a_medias_en_el_texto(self):
        """El texto de cada cifra es el valor final: ``data-valor`` y ``t-out`` salen del mismo dato en la plantilla."""
        for archivo in sorted((FUENTES / 'xml').glob('*.xml')):
            xml = archivo.read_text(encoding='utf-8')
            for etiqueta in re.finditer(r'<(?:strong|span|small)[^>]*\bo_dcasa_sube\b[^>]*/?>', xml):
                abierta = etiqueta.group(0)
                self.assertIn('data-valor', abierta, f'{archivo.name}: {abierta[:90]}')
                self.assertIn('t-out=', abierta, f'{archivo.name}: {abierta[:90]} (el texto es el valor final)')


@tagged('post_install', '-at_install')
class TestCifrasQueSubenEnElNavegador(HttpCase):
    """El módulo compartido, con elementos de verdad en una pantalla de Odoo."""

    def test_el_modulo_en_el_navegador(self):
        codigo = '(async () => {' + COMUN_JS + ESPIAR_JS + r"""
            const modulo = '@dcasa_interfaz/js/cifras_que_suben';
            await esperar(() => odoo.loader.modules.has(modulo), 'el módulo de las cifras que suben');
            const { CifrasQueSuben, escribirCifra, DURACION_SUBIDA } = odoo.loader.modules.get(modulo);
            const { browser } = odoo.loader.modules.get('@web/core/browser/browser');
            igual(DURACION_SUBIDA, 700, 'la misma duración del Inicio');
            const dinero = (v) => '$' + Math.abs(v).toFixed(2);

            // --- Cómo se escribe cada formato ---
            const probar = (atributos, valor) => {
                const el = document.createElement('span');
                Object.assign(el.dataset, atributos);
                return escribirCifra(el, valor, dinero);
            };
            igual(probar({ formato: 'moneda' }, 12.5), '$12.50', 'moneda');
            igual(probar({ formato: 'entero' }, 12345.6), '12,346', 'entero, con la coma de miles');
            igual(probar({}, 7.4), '7', 'sin formato, entero');
            igual(probar({ formato: 'unidades' }, 3.456), '3.46', 'unidades, hasta 2 decimales');
            igual(probar({ formato: 'unidades' }, 3), '3', 'unidades, sin decimales de más');
            igual(probar({ formato: 'decimal', decimales: '1', prefijo: '▲ ', sufijo: ' %' }, 12.34), '▲ 12.3 %',
                  'decimal con lo que lo rodea');

            // --- Una cifra que aparece sube desde 0, y el texto real no se toca ---
            const raiz = document.createElement('div');
            document.body.appendChild(raiz);
            const cifra = (valor, formato = 'moneda') => {
                const el = document.createElement('strong');
                el.className = 'o_dcasa_sube';
                el.dataset.formato = formato;
                el.dataset.valor = String(valor);
                el.textContent = formato === 'moneda' ? dinero(valor) : String(valor);
                raiz.appendChild(el);
                return el;
            };
            const cifras = new CifrasQueSuben(dinero);
            const dinamica = cifra(1000);
            const ojo = espiar(dinamica);
            cifras.subir(raiz);
            igual(dinamica.dataset.sube, '$0.00', 'arranca en 0');
            igual(dinamica.textContent, '$1000.00', 'el texto real es el valor final desde el primer momento');
            await esperar(() => !dinamica.hasAttribute('data-sube'), 'termina de subir', 60);
            ojo.fin();
            const subida = ojo.vistos.map(monto);
            if (subida.length < 3) { falla('se esperaban valores a medias: ' + subida.join(', ')); }
            if (subida.some((v, i) => i && v < subida[i - 1])) { falla('sube sin bajar: ' + subida.join(', ')); }
            // Al final el número ya redondea al valor (999.998 se ve «1000.00»): nunca pasa de él, sí llega.
            if (subida.some((v) => v < 0 || v > 1000.005)) { falla('dentro de 0 y el valor: ' + subida.join(', ')); }
            igual(dinamica.textContent, '$1000.00', 'termina en su valor');
            if (cifras.cuadros.size) { throw new Error('quedaron cuadros pendientes'); }

            // --- Si el valor no cambió, no se anima ---
            cifras.subir(raiz);
            await pausa(120);
            if (dinamica.hasAttribute('data-sube')) { throw new Error('se animó una cifra que no cambió'); }

            // --- Al cambiar, sube (o baja) desde donde estaba ---
            dinamica.dataset.valor = '400';
            dinamica.textContent = dinero(400);
            const baja = espiar(dinamica);
            cifras.subir(raiz);
            igual(dinamica.dataset.sube, '$1000.00', 'arranca en el valor anterior, no en 0');
            await esperar(() => !dinamica.hasAttribute('data-sube'), 'termina de bajar', 60);
            baja.fin();
            const bajada = baja.vistos.map(monto);
            if (bajada.length < 3 || bajada.some((v, i) => i && v > bajada[i - 1])) {
                throw new Error('baja sin subir: ' + bajada.join(', '));
            }

            // --- Si cambia a medias, sigue desde el número que se veía (sin saltos) ---
            dinamica.dataset.valor = '1';
            dinamica.textContent = dinero(1);
            cifras.subir(raiz);                                 // 400 → 1
            await pausa(180);
            const aMedias = monto(dinamica.dataset.sube);
            dinamica.dataset.valor = '5000';
            dinamica.textContent = dinero(5000);
            cifras.subir(raiz);                                 // a medias, ahora hacia 5000
            const sigue = monto(dinamica.dataset.sube);
            if (!(sigue > 1 && sigue < 400) || Math.abs(sigue - aMedias) > 120) {
                throw new Error(`debía seguir desde ${aMedias} y empezó en ${sigue}`);
            }
            await esperar(() => !dinamica.hasAttribute('data-sube'), 'llega a 5000', 60);

            // --- Lo que no es un número (una raya) se deja quieto, y vuelve a subir desde 0 ---
            const raya = cifra('null');
            raya.textContent = '—';
            cifras.subir(raiz);
            if (raya.hasAttribute('data-sube')) { throw new Error('una raya no se anima'); }
            raya.dataset.valor = '50';
            raya.textContent = dinero(50);
            cifras.subir(raiz);
            igual(raya.dataset.sube, '$0.00', 'de una raya a un número: sube desde 0');
            await esperar(() => !raya.hasAttribute('data-sube'), 'termina', 60);

            // --- Una cifra que sale de la pantalla no deja cuadros pendientes ---
            const fugaz = cifra(900);
            cifras.subir(raiz);
            if (!cifras.cuadros.has(fugaz)) { throw new Error('debía estar subiendo'); }
            fugaz.remove();
            await esperar(() => cifras.cuadros.size === 0, 'sin cuadros pendientes tras quitarla', 30);

            // --- «Parar» (al desmontar la pantalla) cancela todo y deja cada cifra con su valor ---
            const a = cifra(300);
            const b = cifra(700, 'entero');
            cifras.subir(raiz);
            if (cifras.cuadros.size !== 2) { throw new Error('dos cifras subiendo: ' + cifras.cuadros.size); }
            cifras.parar();
            igual(cifras.cuadros.size, 0, 'parar cancela los cuadros');
            if (a.hasAttribute('data-sube') || b.hasAttribute('data-sube')) {
                throw new Error('al parar, ninguna cifra queda con el número a medias');
            }
            const visto = a.dataset.sube;
            await pausa(100);
            igual(a.dataset.sube, visto, 'ya no se mueve');

            // --- Con «reducir movimiento» no se mueve nada ---
            const original = browser.matchMedia;
            browser.matchMedia = (consulta) => (/prefers-reduced-motion:\s*reduce/.test(consulta)
                ? { matches: true, media: consulta } : original(consulta));
            try {
                const quietaEl = cifra(250);
                const quieta = espiar(quietaEl);
                cifras.subir(raiz);
                quietaEl.dataset.valor = '600';
                quietaEl.textContent = dinero(600);
                cifras.subir(raiz);
                await pausa(150);
                quieta.fin();
                igual(quieta.vistos, [], 'sin movimiento: nunca un número a medias');
                igual(cifras.cuadros.size, 0, 'sin movimiento: ningún cuadro pedido');
                igual(quietaEl.textContent, '$600.00', 'el texto es el valor final');
                // Y, al volver el movimiento, la cifra parte de donde quedó (no de 0).
                browser.matchMedia = original;
                quietaEl.dataset.valor = '900';
                quietaEl.textContent = dinero(900);
                cifras.subir(raiz);
                igual(quietaEl.dataset.sube, '$600.00', 'parte del último valor');
                await esperar(() => !quietaEl.hasAttribute('data-sube'), 'termina', 60);
            } finally {
                browser.matchMedia = original;
            }
            raiz.remove();
        """ + "console.log('test successful'); })();"
        self.browser_js('/odoo/action-dcasa_interfaz.action_dcasa_inicio', codigo, login='admin', timeout=120)


@tagged('post_install', '-at_install')
class TestCifrasEnLasPantallas(PantallasMixin, HttpCase):
    """Estadísticas, Valor del inventario y el Inicio de siempre, con sus cifras subiendo de verdad."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Una factura del mes pasado: «Mes pasado» da otra cifra y la de este mes tiene desde dónde bajar.
        antes = cls.hoy.replace(day=1) - timedelta(days=1)
        factura = cls.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': cls.cliente.id, 'invoice_date': antes.replace(day=3),
            'invoice_user_id': cls.vendedora.id,
            'invoice_line_ids': [Command.create({'product_id': cls.mesa.id, 'quantity': 3, 'price_unit': 100.0})]})
        factura.action_post()

    def test_estadisticas_suben_al_abrir_y_al_cambiar_de_periodo(self):
        codigo = '(async () => {' + COMUN_JS + ESPIAR_JS + r"""
            await esperar(() => document.querySelector('.o_dcasa_es_ventas'), 'Estadísticas');
            await esperar(() => !document.querySelector('[data-sube]'), 'las cifras quietas');
            const ventas = () => document.querySelector('.o_dcasa_es_ventas .o_dcasa_pd_valor');
            const marcadas = [...document.querySelectorAll('.o_dcasa_es_numeros .o_dcasa_sube')];
            // Los cuatro números (ventas, facturas, ticket y unidades) y el total con ITBMS de la frase de ventas.
            igual(marcadas.length, 5, 'los números del periodo suben');
            for (const el of marcadas) {
                if (el.textContent.includes('—')) { continue; }
                if (!Number.isFinite(Number(el.dataset.valor))) { falla('sin data-valor: ' + el.textContent); }
            }
            if (!document.querySelector('.o_dcasa_es_vendedoras .o_dcasa_sube')) { falla('por vendedora sube'); }
            if (!document.querySelector('.o_dcasa_es_tipos .o_dcasa_sube')) { falla('por tipo sube'); }
            const antes = monto(ventas().textContent);
            const ojo = espiar(ventas());
            document.querySelector('.o_dcasa_es_periodo_mes_pasado').click();
            const cargando = () => document.querySelector('.o_dcasa_es_cuerpo.o_cargando');
            await esperar(() => monto(ventas().textContent) !== antes && !cargando(), 'las ventas del mes pasado');
            await esperar(() => !ventas().hasAttribute('data-sube'), 'termina de moverse', 60);
            ojo.fin();
            const despues = monto(ventas().textContent);
            const vistos = ojo.vistos.map(monto);
            if (vistos.length < 3) { falla('se esperaban valores a medias: ' + vistos.join(', ')); }
            if (Math.abs(vistos[0] - antes) > 0.005) { falla(`debía partir de ${antes} y partió de ${vistos[0]}`); }
            const entre = (v) => v >= Math.min(antes, despues) - 0.005 && v <= Math.max(antes, despues) + 0.005;
            if (!vistos.every(entre)) { falla('fuera de rango: ' + vistos.join(', ')); }
            if (despues !== 300) { falla('las ventas del mes pasado son 3 × $100: ' + despues); }
            // Al volver al mes, sube otra vez (y el texto de la etiqueta nunca fue un número a medias).
            document.querySelector('.o_dcasa_es_periodo_mes').click();
            await esperar(() => monto(ventas().textContent) === antes && !cargando(), 'este mes otra vez');
            await esperar(() => !document.querySelector('[data-sube]'), 'las cifras quietas');
        """ + "console.log('test successful'); })();"
        for tamano in ('1440x900', '390x844'):
            with self.subTest(tamano=tamano):
                self.browser_size = tamano
                self.browser_js('/odoo/action-dcasa_interfaz.accion_estadisticas', codigo, login='gerencia_rol',
                                timeout=120)

    def test_valor_del_inventario_sube_y_actualizar_sin_cambios_no_anima(self):
        codigo = '(async () => {' + COMUN_JS + ESPIAR_JS + r"""
            await esperar(() => document.querySelector('.o_dcasa_vi_costo'), 'Valor del inventario');
            await esperar(() => !document.querySelector('[data-sube]'), 'las cifras quietas');
            const costo = () => document.querySelector('.o_dcasa_vi_costo .o_dcasa_pd_valor');
            igual(costo().classList.contains('o_dcasa_sube'), true, 'el valor al costo sube');
            igual(document.querySelectorAll('.o_dcasa_es_numeros .o_dcasa_sube').length, 4, 'los cuatro números suben');
            if (!document.querySelector('.o_dcasa_vi_tipo .o_dcasa_sube')) { falla('por tipo sube'); }
            // «Actualizar» trae las mismas cifras: no hay nada que animar.
            const ojo = espiar(costo());
            const antes = costo().textContent;
            document.querySelector('.o_dcasa_vi_actualizar').click();
            await esperar(() => !document.querySelector('.o_dcasa_es_cuerpo.o_cargando'), 'actualizado');
            await pausa(300);
            ojo.fin();
            igual(ojo.vistos, [], 'sin cambios no se anima');
            igual(costo().textContent, antes, 'la cifra es la misma');
        """ + "console.log('test successful'); })();"
        for tamano in ('1440x900', '390x844'):
            with self.subTest(tamano=tamano):
                self.browser_size = tamano
                self.browser_js('/odoo/action-dcasa_interfaz.accion_valor_inventario', codigo, login='gerencia_rol',
                                timeout=120)

    def test_una_pantalla_nueva_sube_desde_cero(self):
        """De Estadísticas a «Valor del inventario»: la pantalla que se abre sube sus cifras desde 0 hasta su valor."""
        codigo = '(async () => {' + COMUN_JS + ESPIAR_JS + r"""
            await esperar(() => document.querySelector('.o_dcasa_es_enlace_inventario'), 'el enlace al inventario');
            await esperar(() => !document.querySelector('[data-sube]'), 'las cifras quietas');
            const vistos = [];
            const ojo = new MutationObserver((cambios) => {
                for (const c of cambios) {
                    const texto = c.target.getAttribute('data-sube');
                    if (texto !== null && c.target.closest('.o_dcasa_vi_costo')) { vistos.push(texto); }
                }
            });
            ojo.observe(document.body, { attributes: true, attributeFilter: ['data-sube'], subtree: true });
            document.querySelector('.o_dcasa_es_enlace_inventario').click();
            await esperar(() => document.querySelector('.o_dcasa_vi_costo'), 'Valor del inventario');
            await esperar(() => !document.querySelector('[data-sube]'), 'las cifras quietas', 60);
            ojo.disconnect();
            const final = document.querySelector('.o_dcasa_vi_costo .o_dcasa_pd_valor').textContent;
            if (monto(final) > 0) {
                igual(vistos[0], '$0.00', 'la cifra aparece en 0 y sube');
                if (vistos.length < 3) { falla('se esperaban valores a medias: ' + vistos.join(', ')); }
            }
            if (monto(vistos[vistos.length - 1]) > monto(final)) { falla('sube hasta el valor, no más'); }
        """ + "console.log('test successful'); })();"
        self.browser_size = '1440x900'
        self.browser_js('/odoo/action-dcasa_interfaz.accion_estadisticas', codigo, login='gerencia_rol', timeout=120)

    def test_por_dia_el_resumen_sube_al_cambiar_de_base_vendedora_y_mes(self):
        """Por día: el total del resumen sube (o baja) desde el valor anterior al cambiar la base, la vendedora o el
        mes; si el cambio no mueve la cifra, no se anima."""
        gerencia = self.env['dcasa.tablero'].with_user(self.gerencia)
        mes_pasado = (self.hoy.replace(day=1) - timedelta(days=1)).strftime('%Y-%m')

        def total(**filtros):
            return gerencia.por_dia(**filtros)['total']['sin_itbms']
        esperado = {'facturado': total(base='facturado'), 'vendido': total(base='confirmado'),
                    'otra': total(base='facturado', vendedor=self.otra.id),
                    'mes_pasado': total(mes=mes_pasado, base='facturado')}
        self.assertEqual(esperado['mes_pasado'], 300.0, 'la factura del mes pasado: 3 × $100')
        self.assertNotEqual(esperado['facturado'], esperado['mes_pasado'])
        codigo = '(async () => {' + COMUN_JS + ESPIAR_JS + r"""
            const ESPERADO = __ESPERADO__;
            const total = () => document.querySelector('.o_dcasa_pd_total .o_dcasa_pd_valor');
            const cargando = () => document.querySelector('.o_cargando');
            const clic = (selector) => () => document.querySelector(selector).click();
            await esperar(() => total(), 'el total del mes');
            await esperar(() => !total().hasAttribute('data-sube') && !cargando(), 'el total quieto');
            igual(monto(total().textContent), ESPERADO.facturado, 'el total de Facturado');
            const paso = async (que, accion, esperado) => {
                const antes = monto(total().textContent);
                const ojo = espiar(total());
                accion();
                await pausa(120);
                await esperar(() => !cargando() && !total().hasAttribute('data-sube'), que, 60);
                await pausa(60);
                ojo.fin();
                igual(monto(total().textContent), esperado, que + ': el valor final');
                const vistos = ojo.vistos.map(monto);
                if (antes === esperado) {
                    igual(vistos, [], que + ': si no cambió, no se anima');
                    return;
                }
                if (vistos.length < 3) { falla(que + ': se esperaban valores a medias: ' + vistos.join(', ')); }
                if (Math.abs(vistos[0] - antes) > 0.005) { falla(`${que}: debía partir de ${antes}: ${vistos[0]}`); }
                const lo = Math.min(antes, esperado) - 0.005, hi = Math.max(antes, esperado) + 0.005;
                if (!vistos.every((v) => v >= lo && v <= hi)) { falla(que + ': fuera de rango: ' + vistos.join(', ')); }
                const sube = esperado > antes;
                if (vistos.some((v, i) => i && (sube ? v < vistos[i - 1] : v > vistos[i - 1]))) {
                    falla(que + ': no es parejo: ' + vistos.join(', '));
                }
            };
            await paso('Vendido', clic('.o_dcasa_pd_base_confirmado'), ESPERADO.vendido);
            await paso('Facturado', clic('.o_dcasa_pd_base_facturado'), ESPERADO.facturado);
            const lista = document.querySelector('.o_dcasa_pd_vendedora');
            const cambio = (el, valor) => {
                el.value = valor;
                el.dispatchEvent(new Event('change', { bubbles: true }));
            };
            await paso('otra vendedora', () => cambio(lista, '__OTRA__'), ESPERADO.otra);
            await paso('todo el equipo', () => cambio(lista, ''), ESPERADO.facturado);
            const mes = document.querySelector('.o_dcasa_pd_mes_select');
            await paso('el mes pasado', () => cambio(mes, '__MES__'), ESPERADO.mes_pasado);
        """.replace('__ESPERADO__', json.dumps(esperado)).replace('__OTRA__', str(self.otra.id)).replace(
            '__MES__', mes_pasado) + "console.log('test successful'); })();"
        for tamano in ('1440x900', '390x844'):
            with self.subTest(tamano=tamano):
                self.browser_size = tamano
                self.browser_js('/odoo/action-dcasa_interfaz.accion_facturado_por_dia', codigo, login='gerencia_rol',
                                timeout=180)

    def test_el_inicio_sigue_subiendo_sus_cifras(self):
        """El Inicio usa el mismo módulo y se ve igual: las cifras marcadas de siempre suben; el texto es el final."""
        codigo = '(async () => {' + COMUN_JS + ESPIAR_JS + r"""
            await esperar(() => document.querySelector('.o_dcasa_ventas_valor .o_dcasa_sube'), 'las ventas del Inicio');
            await esperar(() => !document.querySelector('[data-sube]'), 'las cifras quietas');
            const ventas = () => document.querySelector('.o_dcasa_cifra_ventas_hoy .o_dcasa_sube');
            igual(ventas().dataset.formato, 'moneda', 'las ventas son dinero');
            const antes = monto(ventas().textContent);
            if (!(antes > 0)) { falla('el Inicio debía traer las ventas de hoy: ' + antes); }
            if (!document.querySelector('.o_dcasa_ganancia_valor.o_dcasa_sube')) { falla('la ganancia sube'); }
            // Cambiar de vendedora: de todo el equipo a otra persona (sin ventas): baja desde donde estaba.
            const ojo = espiar(ventas());
            const lista = document.querySelector('.o_dcasa_vendedora_select');
            lista.value = '__OTRA__';
            lista.dispatchEvent(new Event('change', { bubbles: true }));
            const cargando = () => document.querySelector('.o_dcasa_ventas_cuerpo.o_cargando');
            await esperar(() => monto(ventas().textContent) === 0 && !cargando(), 'las ventas de la otra persona');
            await esperar(() => !ventas().hasAttribute('data-sube'), 'termina de bajar', 60);
            ojo.fin();
            const vistos = ojo.vistos.map(monto);
            if (vistos.length < 3) { falla('se esperaban valores a medias: ' + vistos.join(', ')); }
            if (Math.abs(vistos[0] - antes) > 0.005) { falla(`debía partir de ${antes} y partió de ${vistos[0]}`); }
            if (vistos.some((v, i) => i && v > vistos[i - 1])) { falla('baja sin subir: ' + vistos.join(', ')); }
        """.replace('__OTRA__', str(self.otra.id)) + "console.log('test successful'); })();"
        for tamano in ('1440x900', '390x844'):
            with self.subTest(tamano=tamano):
                self.browser_size = tamano
                self.browser_js('/odoo/action-dcasa_interfaz.action_dcasa_inicio', codigo, login='gerencia_rol',
                                timeout=120)
