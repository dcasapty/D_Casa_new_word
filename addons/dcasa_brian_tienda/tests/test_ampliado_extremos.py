# ruff: noqa: E501  (JavaScript del navegador embebido en texto)
"""Casos extremos del chat de Andrés que abre ampliado en la computadora (revisión independiente, 2026-11-19;
static/src/js/brian_tienda.js: ``esEscritorio``, ``leerTamano``, ``guardarTamano``, ``abreAmpliado``).

Valores raros en ``dcasa.brian.tamano``, cuota llena, umbral exacto de alto y ancho, zoom al 200 %, la ventana que se
redimensiona con el chat abierto y cerrar y volver a abrir de inmediato.
"""
import json

from odoo.tests import tagged

from .test_navegador import ESPERAR, TAMANO, NavegadorCase


@tagged('post_install', '-at_install')
class TestAndresAmpliadoCasosExtremos(NavegadorCase):

    def _js(self, codigo):
        return '(async () => {' + TAMANO.replace('/*ESPERAR*/', ESPERAR) + codigo + '})()'

    def _pagina(self, browser, codigo, ruta='/'):
        browser.navigate_to(self.base_url() + ruta, wait_stop=True)
        return self.evaluar(browser, self._js(codigo), timeout=180)

    def test_valores_raros_en_la_marca_no_rompen_ni_cuentan_como_normal(self):
        """Solo «normal» (exacto) achica. Cualquier otra cosa en la marca (basura de otra versión, de otra pestaña o a
        propósito) se trata como «sin elegir»: abre ampliado y nunca falla."""
        raros = ['ampliado', 'normal ', ' normal', 'NORMAL', 'Normal', '"normal"', '{"a":1}', '__proto__', '', '0', 'null',
                 'undefined', '<img src=x onerror=window.__xss=1>', 'x'.ljust(50000, 'x')]
        with self.chrome(1440, 900, movil=False) as browser:
            for valor in raros:
                with self.subTest(valor=valor[:20]):
                    browser.navigate_to(self.base_url() + '/', wait_stop=True)
                    self.evaluar(browser, f'sessionStorage.clear(); localStorage.setItem("dcasa.brian.tamano", {json.dumps(valor)}); 1')
                    r = self._pagina(browser, """
                        await abrir();
                        return { estado: estado(), sinXss: window.__xss === undefined,
                                 imgInyectada: !!document.querySelector('img[src="x"]') };""")
                    self.assertTrue(r['sinXss'])
                    self.assertFalse(r['imgInyectada'])
                    self.assertTrue(r['estado']['ampliado'], f'la marca {valor[:20]!r} no es «normal» exacto: abre ampliado')
            # Y el exacto sí achica.
            browser.navigate_to(self.base_url() + '/', wait_stop=True)
            self.evaluar(browser, 'sessionStorage.clear(); localStorage.setItem("dcasa.brian.tamano", "normal"); 1')
            r = self._pagina(browser, "await abrir(); return estado();")
            self.assertFalse(r['ampliado'], '«normal» exacto sí deja el chat chico')
            self.assertFalse(browser.had_failure, 'ni un console.error en la página')

    def test_cuota_llena_o_escritura_bloqueada_no_rompe_el_boton(self):
        with self.chrome(1440, 900, movil=False) as browser:
            r = self._pagina(browser, """
                // Lee bien, pero guardar ESTA marca falla como con la cuota llena (lo demás de la página guarda normal).
                const guardar = Storage.prototype.setItem;
                Storage.prototype.setItem = function (clave, valor) {
                    if (clave === 'dcasa.brian.tamano') { throw new DOMException('Quota', 'QuotaExceededError'); }
                    return guardar.call(this, clave, valor);
                };
                await abrir();
                const r = { alAbrir: estado() };
                await tocarTamano();
                r.achicado = estado();
                await tocarTamano();
                r.ampliado = estado();
                r.sinMarca = marca();
                r.campo = !!document.querySelector('#o_dcbt_texto') && !document.querySelector('#o_dcbt_texto').disabled;
                return r;""")
            self.assertFalse(browser.had_failure, 'ni un console.error en la página')
        self.assertTrue(r['alAbrir']['ampliado'])
        self.assertFalse(r['achicado']['ampliado'], 'el botón achica aunque no pueda guardar')
        self.assertTrue(r['ampliado']['ampliado'])
        self.assertIsNone(r['sinMarca'])
        self.assertTrue(r['campo'])

    def test_umbral_de_alto_y_ancho_y_zoom_al_200(self):
        """1024×600 es computadora (ampliado, y cabe); 1024×599, 1023×700 y el zoom al 200 % de una pantalla de
        1440×900 (720×450 de pantalla CSS) no. En todas el panel cabe y el campo de escribir se ve entero."""
        casos = ((1024, 600, True), (1024, 599, False), (1023, 700, False), (720, 450, False), (1280, 600, True),
                 (2560, 1440, True))
        for ancho, alto, ampliado in casos:
            with self.subTest(ancho=ancho, alto=alto), self.chrome(ancho, alto, movil=False) as browser:
                r = self._pagina(browser, """
                    await abrir();
                    const campo = document.querySelector('#o_dcbt_texto').getBoundingClientRect();
                    const cuerpo = panel().getBoundingClientRect();
                    return { estado: estado(), campoVisible: campo.bottom <= innerHeight + 1 && campo.top >= 0 && campo.width > 50,
                             cabezaVisible: cuerpo.top >= 0, ancho: innerWidth, alto: innerHeight,
                             scrollLado: document.documentElement.scrollWidth > innerWidth + 1 };""")
                self.assertEqual(r['estado']['ampliado'], ampliado)
                self.assertTrue(r['estado']['dentro'], f'el panel cabe en {ancho}×{alto}: {r["estado"]}')
                self.assertTrue(r['campoVisible'], f'el campo de escribir se ve entero en {ancho}×{alto}')
                self.assertTrue(r['cabezaVisible'])
                self.assertFalse(r['scrollLado'])

    def test_redimensionar_con_el_chat_abierto(self):
        """1440 → 1000 (sigue ampliado y cabe) → 700 (vuelve al normal) → 1440 (se queda normal: no se ensancha solo)."""
        with self.chrome(1440, 900, movil=False) as browser:
            browser.navigate_to(self.base_url() + '/', wait_stop=True)
            self.evaluar(browser, self._js("await abrir(); return estado();"))
            pasos = []
            for ancho, alto in ((1000, 800), (700, 800), (1440, 900), (1024, 600), (800, 500)):
                browser._websocket_request('Emulation.setDeviceMetricsOverride', params={
                    'width': ancho, 'height': alto, 'deviceScaleFactor': 1, 'mobile': False})
                pasos.append((ancho, alto, self.evaluar(browser, self._js("await esperar(700); return estado();"))))
            self.assertFalse(browser.had_failure, 'ni un console.error en la página')
        por_ancho = {(a, h): e for a, h, e in pasos}
        self.assertTrue(por_ancho[(1000, 800)]['ampliado'])
        self.assertTrue(por_ancho[(1000, 800)]['dentro'], 'a 1000 px, ampliado, cabe')
        self.assertFalse(por_ancho[(700, 800)]['ampliado'], 'a 700 px vuelve al tamaño normal')
        self.assertFalse(por_ancho[(1440, 900)]['ampliado'], 'al volver a 1440 no se ensancha solo')
        for clave, estado in por_ancho.items():
            self.assertTrue(estado['abierto'], f'el chat sigue abierto a {clave}')
            self.assertTrue(estado['dentro'], f'el panel cabe a {clave}: {estado}')

    def test_cerrar_y_abrir_de_inmediato_no_deja_el_chat_oculto_ni_a_medias(self):
        with self.chrome(1440, 900, movil=False) as browser:
            r = self._pagina(browser, """
                await abrir();
                // Cierra con la X y vuelve a tocar la burbuja a los 100 ms (la animación de cerrar dura 340 ms).
                panel().querySelector('.o_dcbt_cab_boton[aria-label="Cerrar el chat"]').click();
                await esperar(100);
                document.querySelector('button.o_dcbt_burbuja').click();
                await esperar(1500);
                const p = panel();
                return { oculto: p.hidden, ampliado: p.classList.contains('o_dcbt_ampliado'), abierto: !p.hidden,
                         burbujaOculta: document.querySelector('button.o_dcbt_burbuja').hidden,
                         expandido: document.querySelector('button.o_dcbt_burbuja').getAttribute('aria-expanded') };""")
        self.assertFalse(r['oculto'], f'si se vuelve a abrir mientras termina de cerrar, el chat queda abierto: {r}')
