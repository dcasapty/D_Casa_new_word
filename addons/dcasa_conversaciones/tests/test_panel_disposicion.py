"""La disposición COMPACTA de la pantalla «Conversaciones» en las computadoras de trabajo de la tienda (laptops de 1366 × 768,
1280 × 720, 1440 × 900, 1536 × 864, 1024 × 768 y monitores de 1920 × 1080).

Lo que se vigila: **la conversación (los mensajes) es siempre lo más grande y lo único que importa para desplazarse**.
La ficha del cliente nace cerrada (y se abre con «Cliente»), la lista puede reducirse a las fotos, la caja de respuesta es
una franja y una línea (herramientas como íconos + menú «Más»), los avisos son de una línea y la barra del hilo no se parte.

Se mide en Chrome de verdad (getBoundingClientRect), con una conversación larga, y por separado el contrato de los archivos
(``static/src``) para que nadie le quite lo colapsable sin darse cuenta. Cuadra con ``docs/JUAN_ODOO.md``, «Tamaños probados».
"""
import pathlib
import re

from odoo.tests import TransactionCase, tagged

from . import test_panel_visual as visual
from .test_panel_interfaz import ACCION, VENDEDORA, PanelUiCase

FUENTES = pathlib.Path(__file__).resolve().parent.parent / 'static' / 'src'

# Las computadoras de trabajo (ancho, alto) de la ventana del navegador. El alto de 640 es el de una laptop de 1366 × 768 con la
# barra de tareas y la barra del navegador: lo realista.
LAPTOPS = ((1366, 768), (1366, 640), (1280, 720), (1440, 900), (1536, 864), (1024, 768), (1920, 1080))
# Qué parte del alto útil (lo que queda bajo la barra de Odoo) debe ocupar, como mínimo, el contenedor de los mensajes.
MINIMO_DEL_HILO = 0.55

MEDIR = """
(() => {
    const r = (el) => { if (!el) { return null; } const b = el.getBoundingClientRect(); return {x: b.left, y: b.top, w: b.width, h: b.height, b: b.bottom}; };
    const visible = (sel) => { const el = document.querySelector(sel); if (!el) { return false; } const b = el.getBoundingClientRect(); const cs = getComputedStyle(el);
        return cs.display !== 'none' && cs.visibility !== 'hidden' && b.width > 0 && b.height > 0; };
    const cuerpo = document.querySelector('.o_dcj_hilo_cuerpo');
    const raiz = document.querySelector('.o_dcj');
    return {
        viewport: [innerWidth, innerHeight],
        raiz: r(raiz), lista: r(document.querySelector('.o_dcj_lista')), hilo: r(document.querySelector('.o_dcj_hilo')),
        ficha: visible('.o_dcj_ficha') ? r(document.querySelector('.o_dcj_ficha')) : null,
        cabecera: r(document.querySelector('.o_dcj_hilo_cabecera')), mensajes: r(cuerpo), caja: r(document.querySelector('.o_dcj_caja')),
        aviso: r(document.querySelector('.o_dcj_aviso')), barra: r(document.querySelector('.o_dcj_barra')),
        resumen: r(document.querySelector('.o_dcj_resumen')), resumir: r(document.querySelector('.o_dcj_resumir')),
        scroll: cuerpo ? {alto: cuerpo.scrollHeight, visible: cuerpo.clientHeight, arriba: cuerpo.scrollTop} : null,
        paginaDesplaza: document.documentElement.scrollHeight > innerHeight + 1 || document.documentElement.scrollWidth > innerWidth + 1,
        desborde: raiz ? raiz.scrollWidth > raiz.clientWidth + 1 : null,
        fichaAbierta: document.querySelector('.o_dcj_boton_ficha')?.getAttribute('aria-expanded') === 'true',
    };
})()
"""

# Deja la ficha como se pide (abierta o cerrada) usando el botón «Cliente».
PONER_FICHA = """
(async (abierta) => {
    const boton = document.querySelector('.o_dcj_boton_ficha');
    if ((boton.getAttribute('aria-expanded') === 'true') !== abierta) { boton.click(); }
    await new Promise((ok) => setTimeout(ok, 350));
    return true;
})(%s)
"""

PAUSA = '(async () => { await new Promise((ok) => setTimeout(ok, %d)); return true; })()'

# Botones, selectores y cajas con menos de 44 px (los enlaces de texto dentro de una frase no cuentan).
CHICOS = """
(() => [...document.querySelectorAll('.o_dcj button, .o_dcj select, .o_dcj input:not([type=file]), .o_dcj textarea')]
    .filter((e) => !e.classList.contains('o_dcj_enlace') && !e.classList.contains('o_dcj_foto_boton') && getComputedStyle(e).visibility !== 'hidden')
    .map((e) => [e, e.getBoundingClientRect()])
    .filter(([e, r]) => r.width > 0 && r.height > 0 && (r.width < 43.5 || r.height < 43.5))
    .map(([e, r]) => e.className + ' [' + (e.getAttribute('aria-label') || e.textContent.trim().slice(0, 20)) + '] ' + Math.round(r.width) + 'x' + Math.round(r.height)))()
"""


class DisposicionCase(PanelUiCase):
    """Chrome con el tamaño que se pida, la conversación larga y un par de ayudas para medir."""
    _chrome = visual.TestContratoVisualJuan._chrome
    _evaluar = visual.TestContratoVisualJuan._evaluar

    def conversacion_larga(self, mensajes=45):
        """Una conversación de ~90 mensajes (para que el hilo tenga qué desplazar) y otras dos para la lista."""
        for i in range(mensajes):
            minutos = 700 - i * 10
            self.registrar(f'Pregunta {i} del cliente sobre una cama queen en gris para dos personas', '50761000099',
                           minutos=minutos, nombre='Zzlarga Prueba')
            self.registrar(f'Respuesta {i} del asistente con los detalles que se pidieron', '50761000099', autor='bot',
                           minutos=minutos - 1)
        self.registrar('Quiero apartar un sofá', '50761000098', minutos=20, nombre='Zzotra Persona')
        self.registrar('Buenas tardes', '777009', canal='telegram', minutos=40, nombre='Zzmas Gente')
        larga = self.env['dcasa.conversacion'].search([('id_externo', '=', '50761000099')])
        ultimo = self.env['dcasa.mensaje'].search([('conversacion_id', '=', larga.id)], order='id desc', limit=1)
        larga.sudo().write({
            'resumen_ia': '• Busca una cama queen en gris para dos personas.\n• Pregunta por el precio y la entrega.',
            'resumen_ia_en': self.ahora, 'resumen_ia_hasta_id': ultimo.id})
        return larga

    def abrir(self, browser, abrir_conversacion=True):
        browser.navigate_to(self.base_url() + ACCION, wait_stop=True)
        self.assertTrue(browser._wait_ready('odoo.isReady'), 'Conversaciones no terminó de cargar')
        self._evaluar(browser, visual.AYUDAS)
        paso = 'await abrirConversacion("Zzlarga");' if abrir_conversacion else ''
        self._evaluar(browser, '(async () => { await __dcj.esperar(() => document.querySelector(".o_dcj_fila"), "la lista");'
                               f' {paso} await new Promise((ok) => setTimeout(ok, 400)); return true; }})()', timeout=90)

    def medir(self, browser):
        return self._evaluar(browser, MEDIR)

    def ficha(self, browser, abierta):
        self._evaluar(browser, PONER_FICHA % ('true' if abierta else 'false'))

    def pausa(self, browser, ms=300):
        self._evaluar(browser, PAUSA % ms)

    def rueda(self, browser, x, y, dy):
        """Gira la rueda del ratón (de verdad, por el protocolo) sobre un punto de la pantalla."""
        browser._websocket_request('Input.dispatchMouseEvent', params={
            'type': 'mouseWheel', 'x': x, 'y': y, 'deltaX': 0, 'deltaY': dy})
        self.pausa(browser, 400)

    def sin_errores(self, browser, donde):
        excepcion = browser._result.done() and browser._result.exception()
        self.assertFalse(excepcion, f'{donde}: error de JavaScript en la página: {excepcion}')
        self.assertFalse(browser.had_failure, f'{donde}: console.error en la página')


@tagged('post_install', '-at_install')
class TestDisposicionDeEscritorio(DisposicionCase):

    def test_01_la_conversacion_es_lo_mas_grande_a_cada_resolucion(self):
        """Con la ficha abierta y la caja con todos sus botones, los mensajes ocupan al menos 55 % del alto útil."""
        self.conversacion_larga()
        for ancho, alto in LAPTOPS:
            with self.subTest(pantalla=f'{ancho}x{alto}'), self._chrome(ancho, alto, VENDEDORA, reloj_fijo=False) as browser:
                self.abrir(browser)
                for abierta in (False, True):
                    self.ficha(browser, abierta)
                    m = self.medir(browser)
                    donde = f'{ancho}x{alto}, ficha {"abierta" if abierta else "cerrada"}'
                    self.assertEqual(m['fichaAbierta'], abierta, donde)
                    self.assertGreaterEqual(m['mensajes']['h'], MINIMO_DEL_HILO * m['raiz']['h'],
                                            f'{donde}: los mensajes miden {m["mensajes"]["h"]:.0f} px de {m["raiz"]["h"]:.0f} '
                                            f'útiles (se pide al menos {MINIMO_DEL_HILO:.0%})')
                    # La caja con todos sus botones y la franja: baja. La barra del hilo: una sola fila.
                    self.assertLessEqual(m['caja']['h'], 130, f'{donde}: la caja de respuesta vacía mide {m["caja"]["h"]:.0f} px')
                    self.assertLessEqual(m['cabecera']['h'], 60, f'{donde}: la barra del hilo se partió en varias filas')
                    self.assertFalse(m['paginaDesplaza'], f'{donde}: se desplaza la página, no el hilo')
                    self.assertFalse(m['desborde'], f'{donde}: desborde horizontal')
                    # El hilo tiene qué desplazar y quedó abajo, en el último mensaje.
                    self.assertGreater(m['scroll']['alto'], m['scroll']['visible'], donde)
                    self.assertLess(m['scroll']['alto'] - m['scroll']['visible'] - m['scroll']['arriba'], 90, f'{donde}: no bajó al último mensaje')
                self.sin_errores(browser, f'{ancho}x{alto}')

    def test_02_el_hilo_se_desplaza_con_la_ficha_la_caja_y_el_menu_abiertos(self):
        self.conversacion_larga()
        with self._chrome(1366, 768, VENDEDORA, reloj_fijo=False) as browser:
            self.abrir(browser)
            self.ficha(browser, True)
            # Todo lo que ocupa lugar en la caja a la vez: texto de varias líneas, programar y el menú «Más».
            self._evaluar(browser, """(async () => {
                const caja = document.querySelector('#o_dcj_texto');
                caja.value = 'Una línea\\nOtra línea\\nUna tercera\\nY una cuarta';
                caja.dispatchEvent(new Event('input', {bubbles: true}));
                document.querySelector('.o_dcj_mas_boton').click();
                await __dcj.esperar(() => __dcj.aqui('.o_dcj_menu_item', 'Programar'), 'Programar en el menú');
                __dcj.aqui('.o_dcj_menu_item', 'Programar').click();
                await __dcj.esperar(() => document.querySelector('.o_dcj_programar'), 'la fila de programar');
                document.querySelector('.o_dcj_mas_boton').click();
                return true; })()""")
            self.pausa(browser)
            m = self.medir(browser)
            self.assertGreaterEqual(m['mensajes']['h'], 0.40 * m['raiz']['h'],
                                    f'con todo abierto los mensajes miden {m["mensajes"]["h"]:.0f} px de {m["raiz"]["h"]:.0f}')
            self.assertFalse(m['paginaDesplaza'])
            # La rueda sobre los mensajes los desplaza (con la ficha abierta, a su izquierda).
            x = m['mensajes']['x'] + m['mensajes']['w'] / 2
            y = m['mensajes']['y'] + m['mensajes']['h'] / 2
            antes = m['scroll']['arriba']
            self.rueda(browser, x, y, -500)
            despues = self.medir(browser)['scroll']['arriba']
            self.assertLess(despues, antes - 100, 'la rueda del ratón no desplazó el hilo con la ficha y la caja abiertas')
            # La rueda sobre la ficha desplaza la ficha, no el hilo.
            f = m['ficha']
            self.rueda(browser, f['x'] + f['w'] / 2, f['y'] + f['h'] / 2, 300)
            self.assertEqual(self.medir(browser)['scroll']['arriba'], despues, 'la ficha movió el hilo')
            self.sin_errores(browser, 'desplazamiento')

    def test_03_la_ficha_nace_cerrada_en_laptop_abierta_en_pantalla_amplia_y_se_recuerda(self):
        self.conversacion_larga()
        # Laptop: cerrada hasta que se pide; lo que se elija se recuerda al volver.
        with self._chrome(1366, 768, VENDEDORA, reloj_fijo=False) as browser:
            self.abrir(browser)
            m = self.medir(browser)
            self.assertFalse(m['fichaAbierta'], 'la ficha debe nacer cerrada en 1366 × 768')
            self.assertIsNone(m['ficha'], 'la ficha cerrada no ocupa lugar')
            ancho_sin_ficha, alto_de_los_mensajes = m['hilo']['w'], m['mensajes']['h']
            self.ficha(browser, True)
            m = self.medir(browser)
            self.assertTrue(m['ficha'] and 300 <= m['ficha']['w'] <= 340, f'la ficha abierta mide {m["ficha"]}')
            self.assertLess(m['hilo']['w'], ancho_sin_ficha)
            self.assertEqual(m['mensajes']['h'], alto_de_los_mensajes, 'abrir la ficha no le quita altura a los mensajes')
            guardado = self._evaluar(browser, 'Object.entries(localStorage).filter(([k]) => k.startsWith("dcasa.conversaciones.ficha"))')
            self.assertEqual([v for _, v in guardado], ['abierta'], f'se recuerda por persona: {guardado}')
            self.abrir(browser)          # como volver otro día
            self.assertTrue(self.medir(browser)['fichaAbierta'], 'la ficha abierta se recuerda')
            self.ficha(browser, False)
            self.abrir(browser)
            self.assertFalse(self.medir(browser)['fichaAbierta'], 'la ficha cerrada se recuerda')
            # Esc dentro de la ficha la cierra y devuelve el foco al botón «Cliente».
            self.ficha(browser, True)
            self._evaluar(browser, 'document.querySelector(".o_dcj_volver_ficha").focus(); '
                                   'document.activeElement.dispatchEvent(new KeyboardEvent("keydown", {key: "Escape", bubbles: true})); true')
            self.pausa(browser)
            self.assertFalse(self.medir(browser)['fichaAbierta'])
            self.assertTrue(self._evaluar(browser, 'document.activeElement === document.querySelector(".o_dcj_boton_ficha")'))
        # Pantalla amplia: nace abierta, al lado del hilo, y también se puede cerrar y recordar.
        with self._chrome(1920, 1080, VENDEDORA, reloj_fijo=False) as browser:
            self.abrir(browser)
            m = self.medir(browser)
            self.assertTrue(m['fichaAbierta'] and m['ficha'], 'en 1920 × 1080 la ficha nace abierta')
            self.assertGreaterEqual(m['hilo']['w'], 1000)
            self.ficha(browser, False)
            self.abrir(browser)
            self.assertFalse(self.medir(browser)['fichaAbierta'], 'quien la cierra en pantalla amplia la encuentra cerrada')
            self.sin_errores(browser, 'ficha')

    def test_04_sin_almacenamiento_en_el_navegador_todo_funciona(self):
        """Ventana privada o datos bloqueados: localStorage lanza error; la pantalla abre, la ficha y la lista responden."""
        self.conversacion_larga()
        with self._chrome(1366, 768, VENDEDORA, reloj_fijo=False) as browser:
            browser._websocket_request('Page.addScriptToEvaluateOnNewDocument', params={'source': """
                Object.defineProperty(window, 'localStorage', { get() { throw new DOMException('bloqueado', 'SecurityError'); } });
            """})
            self.abrir(browser)
            self.ficha(browser, True)
            self.assertTrue(self.medir(browser)['fichaAbierta'])
            self._evaluar(browser, 'document.querySelector(".o_dcj_lista_toggle").click(); true')
            self.pausa(browser)
            self.assertLess(self.medir(browser)['lista']['w'], 100)
            self.sin_errores(browser, 'sin almacenamiento')

    def test_05_la_lista_se_reduce_a_las_fotos_y_se_recuerda(self):
        self.conversacion_larga()
        with self._chrome(1366, 768, VENDEDORA, reloj_fijo=False) as browser:
            self.abrir(browser)
            m = self.medir(browser)
            self.assertTrue(280 <= m['lista']['w'] <= 330, f'la lista ancha mide {m["lista"]["w"]}')
            self._evaluar(browser, 'document.querySelector(".o_dcj_lista_toggle").click(); true')
            self.pausa(browser)
            reducida = self.medir(browser)
            self.assertLessEqual(reducida['lista']['w'], 80)
            self.assertGreater(reducida['hilo']['w'], m['hilo']['w'] + 200, 'al reducir la lista el hilo gana ancho')
            filas = self._evaluar(browser, """[...document.querySelectorAll('.o_dcj_fila')].map((f) => ({
                nombre: f.getAttribute('aria-label') || '', titulo: f.title, ancho: f.getBoundingClientRect().width,
                cuerpo: getComputedStyle(f.querySelector('.o_dcj_fila_cuerpo')).display}))""")
            self.assertTrue(filas and all(f['nombre'] and f['titulo'] and f['cuerpo'] == 'none' for f in filas),
                            f'cada foto debe tener su nombre (aria-label y tooltip): {filas}')
            # Una foto abre su conversación.
            self._evaluar(browser, '(() => { const f = [...document.querySelectorAll(".o_dcj_fila")].find((x) => x.getAttribute("aria-label").includes("Zzotra")); f.click(); return true; })()')
            self._evaluar(browser, '__dcj.esperar(() => document.querySelector(".o_dcj_hilo_cabecera h2")?.textContent.includes("Zzotra"), "el hilo de Zzotra")')
            self.abrir(browser, abrir_conversacion=False)     # volver otro día: sigue reducida
            self.assertLessEqual(self.medir(browser)['lista']['w'], 80)
            self._evaluar(browser, 'document.querySelector(".o_dcj_lista_toggle").click(); true')
            self.pausa(browser)
            self.assertGreaterEqual(self.medir(browser)['lista']['w'], 280)
            self.sin_errores(browser, 'lista reducida')

    def test_06_con_poco_ancho_la_ficha_abierta_reduce_la_lista_y_el_hilo_no_baja_de_550_px(self):
        """Entre 1100 y 1250 px la lista nace ancha; con la ficha abierta ya no caben las dos: la lista se reduce a las fotos."""
        self.conversacion_larga()
        with self._chrome(1200, 768, VENDEDORA, reloj_fijo=False) as browser:
            self.abrir(browser)
            sola = self.medir(browser)
            self.assertGreaterEqual(sola['lista']['w'], 280, 'sin la ficha, la lista nace ancha')
            self.ficha(browser, True)
            m = self.medir(browser)
            self.assertLessEqual(m['lista']['w'], 80, 'con la ficha abierta y poco ancho, la lista se reduce a las fotos')
            self.assertGreaterEqual(m['hilo']['w'], 550, f'el hilo mide {m["hilo"]["w"]}')
            self.assertEqual(m['mensajes']['h'], sola['mensajes']['h'])
            self.assertFalse(self._evaluar(browser, '!!document.querySelector(".o_dcj_lista_toggle")'),
                             'forzada por la ficha, la lista no ofrece su botón')
            self.ficha(browser, False)
            self.assertGreaterEqual(self.medir(browser)['lista']['w'], 280, 'al cerrar la ficha la lista vuelve a su ancho')
            self.sin_errores(browser, '1200 px')

    def test_07_las_herramientas_son_iconos_con_nombre_y_el_menu_mas_se_maneja_con_el_teclado(self):
        self.conversacion_larga()
        with self._chrome(1366, 768, VENDEDORA, reloj_fijo=False) as browser:
            self.abrir(browser)
            botones = self._evaluar(browser, """[...document.querySelectorAll('.o_dcj_herramientas .o_dcj_herramienta')].map((b) => ({
                nombre: b.getAttribute('aria-label') || '', titulo: b.title, ancho: b.getBoundingClientRect().width,
                alto: b.getBoundingClientRect().height, icono: !!b.querySelector('.fa')}))""")
            nombres = [b['nombre'] for b in botones]
            for esperado in ('Adjuntar', 'Foto del catálogo', 'Cotización', 'Respuestas rápidas', 'Sugerir', 'Más acciones'):
                self.assertTrue(any(esperado in n for n in nombres), f'falta el botón «{esperado}»: {nombres}')
            for b in botones:
                self.assertTrue(b['titulo'] and b['icono'], f'cada herramienta tiene ícono y tooltip: {b}')
                self.assertLessEqual(b['ancho'], 48, f'una herramienta es solo ícono (sin texto al lado): {b}')
            # «Más»: se abre con el botón; el foco entra a la primera opción; Esc cierra y devuelve el foco; un clic fuera también.
            r = self._evaluar(browser, """(async () => {
                const boton = document.querySelector('.o_dcj_mas_boton');
                const salida = {cerrado: boton.getAttribute('aria-expanded'), roles: boton.getAttribute('aria-haspopup')};
                boton.click();
                await __dcj.esperar(() => document.querySelector('.o_dcj_menu'), 'el menú Más');
                const menu = document.querySelector('.o_dcj_menu'), caja = menu.getBoundingClientRect();
                salida.abierto = boton.getAttribute('aria-expanded');
                salida.rol = menu.getAttribute('role');
                salida.opciones = [...menu.querySelectorAll('[role=menuitem]')].map((o) => o.textContent.trim());
                salida.dentro = caja.left >= 0 && caja.right <= innerWidth && caja.top >= 0 && caja.bottom <= innerHeight;
                salida.foco = document.activeElement.getAttribute('role');
                document.activeElement.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));
                await new Promise((ok) => setTimeout(ok, 150));
                salida.cerroConEsc = !document.querySelector('.o_dcj_menu');
                salida.focoAlCerrar = document.activeElement === boton;
                boton.click();
                await __dcj.esperar(() => document.querySelector('.o_dcj_menu'), 'el menú otra vez');
                document.querySelector('.o_dcj_hilo_cuerpo').dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
                await new Promise((ok) => setTimeout(ok, 150));
                salida.cerroConClic = !document.querySelector('.o_dcj_menu');
                return salida; })()""")
            self.assertEqual((r['cerrado'], r['abierto'], r['roles'], r['rol']), ('false', 'true', 'menu', 'menu'), r)
            self.assertIn('Programar el envío', r['opciones'])
            self.assertTrue(r['dentro'] and r['foco'] == 'menuitem' and r['cerroConEsc'] and r['focoAlCerrar'] and r['cerroConClic'], r)
            self.sin_errores(browser, 'menú Más')

    def test_08_avisos_y_barras_de_una_sola_linea(self):
        """El aviso de arriba, la franja de la caja, el resumen plegado y la barra del hilo no pasan de una línea."""
        self.conversacion_larga()
        for ancho, alto in ((1366, 768), (1024, 768)):
            with self.subTest(pantalla=f'{ancho}x{alto}'), self._chrome(ancho, alto, VENDEDORA, reloj_fijo=False) as browser:
                self.abrir(browser)
                m = self.medir(browser)
                if m['aviso']:
                    self.assertLessEqual(m['aviso']['h'], 40, 'el aviso de arriba debe ser de una línea')
                self.assertLessEqual(m['barra']['h'], 44, 'la franja de quién atiende debe ser de una línea')
                self.assertTrue(m['resumen'], 'hay un resumen guardado')
                self.assertLessEqual(m['resumen']['h'], 40, 'el resumen nace plegado, en una línea')
                self.assertLessEqual(m['cabecera']['h'], 60)
                # Todo lo de la barra del hilo está en la misma fila.
                filas = self._evaluar(browser, """[...document.querySelectorAll('.o_dcj_hilo_cabecera > *')]
                    .filter((e) => e.getBoundingClientRect().width > 0).map((e) => Math.round(e.getBoundingClientRect().top))""")
                self.assertLessEqual(max(filas) - min(filas), 16, f'la barra del hilo se partió en filas: {filas}')
                # El resumen se despliega a pedido y se pliega de nuevo.
                self._evaluar(browser, 'document.querySelector(".o_dcj_resumen_titulo").click(); true')
                self.pausa(browser)
                abierto = self.medir(browser)['resumen']['h']
                self.assertGreater(abierto, m['resumen']['h'] + 20)
                self.assertLessEqual(abierto, 300)
                self.sin_errores(browser, 'avisos')

    def test_09_la_caja_no_pasa_de_una_parte_de_la_pantalla_aunque_se_abra_todo(self):
        """Programar + texto largo + devolver al asistente: la caja tiene tope y sus partes largas se desplazan por dentro."""
        self.conversacion_larga()
        with self._chrome(1366, 640, VENDEDORA, reloj_fijo=False) as browser:
            self.abrir(browser)
            self._evaluar(browser, """(async () => {
                const caja = document.querySelector('#o_dcj_texto');
                caja.value = Array.from({length: 12}, (_, i) => 'Línea ' + i).join('\\n');
                caja.dispatchEvent(new Event('input', {bubbles: true}));
                document.querySelector('.o_dcj_mas_boton').click();
                await __dcj.esperar(() => __dcj.aqui('.o_dcj_menu_item', 'Programar'), 'Programar');
                __dcj.aqui('.o_dcj_menu_item', 'Programar').click();
                await __dcj.esperar(() => document.querySelector('.o_dcj_programar'), 'programar');
                __dcj.aqui('.o_dcj_barra button', 'Devolver').click();
                await __dcj.esperar(() => document.querySelector('.o_dcj_devolver'), 'devolver');
                return true; })()""")
            self.pausa(browser)
            m = self.medir(browser)
            self.assertLessEqual(m['caja']['h'], 0.5 * m['raiz']['h'], f'la caja ocupa {m["caja"]["h"]:.0f} de {m["raiz"]["h"]:.0f} px útiles')
            self.assertGreaterEqual(m['mensajes']['h'], 0.30 * m['raiz']['h'])
            texto = self._evaluar(browser, '(() => { const t = document.querySelector("#o_dcj_texto"); return {alto: t.getBoundingClientRect().height, sigue: t.scrollHeight > t.clientHeight}; })()')
            self.assertLessEqual(texto['alto'], 110, 'la caja de texto crece hasta un máximo')
            self.assertTrue(texto['sigue'], 'pasado el máximo, el texto se desplaza dentro de la caja')
            self.sin_errores(browser, 'caja a tope')


@tagged('post_install', '-at_install')
class TestDisposicionDeCelular(DisposicionCase):
    """390 × 844: una pantalla a la vez, la caja compacta, el menú «Más» dentro de la pantalla y todo a 44 px."""

    def test_la_caja_compacta_y_el_menu_mas_caben_en_el_celular(self):
        self.conversacion_larga()
        with self._chrome(390, 844, VENDEDORA, reloj_fijo=False) as browser:
            self.abrir(browser)
            m = self.medir(browser)
            self.assertIsNone(m['ficha'], 'en celular la ficha es otra pantalla')
            self.assertLessEqual(m['caja']['h'], 0.35 * m['viewport'][1], f'la caja mide {m["caja"]["h"]:.0f} px')
            self.assertGreaterEqual(m['mensajes']['h'], 0.45 * m['raiz']['h'], f'los mensajes miden {m["mensajes"]["h"]:.0f} px')
            self.assertFalse(m['paginaDesplaza'] or m['desborde'])
            self.assertEqual(self._evaluar(browser, CHICOS), [], 'botones de menos de 44 px en el hilo')
            # Menú «Más» y la fila de programar abiertos: nada se sale de la pantalla ni baja de 44 px.
            r = self._evaluar(browser, """(async () => {
                document.querySelector('.o_dcj_mas_boton').click();
                await __dcj.esperar(() => document.querySelector('.o_dcj_menu'), 'el menú Más');
                const caja = document.querySelector('.o_dcj_menu').getBoundingClientRect();
                const salida = {dentro: caja.left >= 0 && caja.right <= innerWidth && caja.top >= 0};
                __dcj.aqui('.o_dcj_menu_item', 'Programar').click();
                await __dcj.esperar(() => document.querySelector('.o_dcj_programar'), 'programar');
                await new Promise((ok) => setTimeout(ok, 200));
                return salida; })()""")
            self.assertTrue(r['dentro'], 'el menú «Más» se sale de la pantalla')
            self.assertEqual(self._evaluar(browser, CHICOS), [], 'botones o campos de menos de 44 px con programar abierto')
            self.assertFalse(self.medir(browser)['paginaDesplaza'])
            self.sin_errores(browser, 'celular')


@tagged('post_install', '-at_install')
class TestContratoDeLosArchivos(TransactionCase):
    """Lo colapsable vive en los archivos de ``static/src``: si alguien lo quita, estas pruebas avisan."""

    def leer(self, ruta):
        return (FUENTES / ruta).read_text(encoding='utf-8')

    def test_la_ficha_es_colapsable_y_se_abre_con_un_boton_cliente(self):
        hilo, ficha, scss = self.leer('xml/hilo.xml'), self.leer('xml/ficha.xml'), self.leer('scss/panel.scss')
        boton = re.search(r'<button[^>]*o_dcj_boton_ficha[^>]*>.*?</button>', hilo, re.S).group(0)
        for atributo in ('aria-expanded', 'aria-controls="o_dcj_ficha"', 'aria-label=', 'title='):
            self.assertIn(atributo, boton)
        self.assertIn('Cliente', boton)
        self.assertIn('id="o_dcj_ficha"', ficha)
        # Cerrada no ocupa lugar ni recibe el foco; abierta, al lado desde 1024 px y encima en tablet.
        self.assertIn('visibility: hidden', scss)
        self.assertRegex(scss, r'@media \(min-width: 1024px\)')
        self.assertIn('o_dcj_ficha_abierta', scss)

    def test_los_limites_de_pantalla_de_js_y_de_scss_son_los_mismos(self):
        js, scss = self.leer('js/preferencias.js'), self.leer('scss/panel.scss')
        for consulta in ('(max-width: 767.98px)', '(min-width: 1024px)'):
            self.assertIn(consulta, js)
            self.assertIn(consulta, scss, f'{consulta} está en preferencias.js pero no en panel.scss')
        # Los demás límites (1500 × 800, 1250, 1100) solo deciden el valor inicial: viven en JS y se documentan allí.
        for consulta in ('(min-width: 1500px) and (min-height: 800px)', '(min-width: 1250px)', '(max-width: 1100px)'):
            self.assertIn(consulta, js)

    def test_las_preferencias_no_se_caen_sin_almacenamiento(self):
        js = self.leer('js/preferencias.js')
        for funcion in ('leerPreferencia', 'guardarPreferencia'):
            cuerpo = re.search(rf'export function {funcion}\(.*?\n}}', js, re.S).group(0)
            self.assertIn('try {', cuerpo, f'{funcion} debe envolver localStorage en try/catch')
            self.assertIn('catch', cuerpo)

    def test_la_caja_es_compacta_con_iconos_con_nombre_y_menu_mas(self):
        caja, scss = self.leer('xml/caja.xml'), self.leer('scss/panel.scss')
        self.assertIn('aria-haspopup="menu"', caja)
        self.assertIn('role="menu"', caja)
        self.assertIn('role="menuitem"', caja)
        botones = re.findall(r'<button[^>]*class="o_dcj_herramienta[^"]*"[^>]*>', caja)
        self.assertGreaterEqual(len(botones), 6, 'Adjuntar, Foto, Cotización, Rápidas, Sugerir y Más')
        for boton in botones:
            self.assertIn('title=', boton, f'sin tooltip: {boton}')
            self.assertIn('aria-label=', boton, f'sin aria-label: {boton}')
        self.assertIn('rows="1"', caja, 'la caja de texto nace de una sola línea')
        self.assertRegex(scss, r'max-height: min\(100px, 14vh\)')
        self.assertIn('@container caja', scss)

    def test_los_avisos_son_de_una_linea_y_el_resumen_nace_plegado(self):
        scss, conversaciones, hilo = self.leer('scss/panel.scss'), self.leer('xml/conversaciones.xml'), self.leer('xml/hilo.xml')
        aviso = re.search(r'\.o_dcj \.o_dcj_aviso \{(.*?)\n\}', scss, re.S).group(1)
        self.assertIn('white-space: nowrap', aviso, 'el aviso de arriba es de una línea')
        self.assertIn('text-overflow: ellipsis', aviso)
        self.assertIn('t-att-title="aviso.titulo', conversaciones, 'el aviso completo sale al pasar el mouse')
        self.assertIn('o_dcj_resumen_titulo', hilo)
        self.assertRegex(scss, r'\.o_dcj_resumen_cuerpo \{ display: none;')

    def test_respeta_la_marca_y_el_movimiento_reducido(self):
        scss = self.leer('scss/panel.scss')
        self.assertNotRegex(scss, r'(linear|radial)-gradient', 'sistema plano: sin degradados')
        self.assertIn('prefers-reduced-motion: reduce', scss)
        self.assertIn(':focus-visible', scss)
        self.assertIn('transition: transform 160ms', scss, 'la ficha de tablet se desliza (y se detiene con movimiento reducido)')
        # Nada fijo en píxeles que dependa de la caja: el aviso de mensajes nuevos ya no usa un `bottom` mágico.
        self.assertNotRegex(scss, r'\.o_dcj_nuevos \{[^}]*bottom: \d+px')
