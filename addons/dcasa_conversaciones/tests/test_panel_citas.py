"""La burbuja con cita, «Reenviado», la reacción del cliente, las palomitas y «Responder», en un Chromium de verdad.

Pedido de la dueña (2026-11-07): ver a qué mensaje se refiere el cliente cuando dice «este», si lo reenvió, cómo reaccionó y
si el mensaje se entregó o se leyó. Se prueba también que todo llegue en vivo (sin recargar), que «Responder» cite el
mensaje al enviar y que el chat siga bajando con la rueda y con el dedo a 390 px (el error de siempre: pantallas que no
bajan). Con ``DCASA_CAPTURAS_CITAS=<carpeta>`` deja las capturas para la dueña (datos de prueba). Números de mentira.
"""
import base64
import contextlib
import json
import os
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from odoo.tests import tagged
from odoo.tests.common import ChromeBrowser

from .common import TOKEN_ODOO
from .test_panel_interfaz import ACCION, VENDEDORA, PanelUiCase
from .test_panel_visual import AUDITAR, AYUDAS

CLIENTE = '50760001111'
VAR_CAPTURAS = 'DCASA_CAPTURAS_CITAS'
MOTIVO_24H = ('Pasaron más de 24 horas desde el último mensaje del cliente: WhatsApp solo deja escribirle con una '
              'plantilla aprobada.')


@tagged('post_install', '-at_install')
class TestCitasEnElNavegador(PanelUiCase):

    # ------------------------------------------------------------------ Datos de prueba
    def mensaje(self, texto, id_mensaje, autor='cliente', minutos=0, **extra):
        conv, mensaje, _creado = self.env['dcasa.conversacion']._registrar_mensaje({
            'canal': 'whatsapp_cloud', 'id_externo': CLIENTE, 'id_mensaje': id_mensaje,
            'direccion': 'entrante' if autor == 'cliente' else 'saliente', 'autor': autor, 'texto': texto,
            'ts': self.ahora - timedelta(minutes=minutos), 'nombre': 'Valeria Prueba', 'celular': None, 'adjuntos': [],
            **extra})
        return conv, mensaje

    def de_la_vendedora(self, conv, texto, id_canal):
        mensaje = conv._crear_mensaje_de_odoo(texto, usuario=self.vendedora)
        return mensaje.sudo()._marcar_enviado(id_canal, partes=[{'id_canal': id_canal, 'tipo': 'texto', 'texto': texto}])

    def evento(self, tipo, id_mensaje, minutos, **extra):
        return {'tipo': tipo, 'canal': 'whatsapp_cloud', 'id_externo': CLIENTE, 'id_mensaje': id_mensaje,
                'ts': self.ahora - timedelta(minutes=minutos), **extra}

    def datos_citas(self):
        self.conv, _ = self.mensaje('Hola, busco una cama queen', 'wamid.ui.c1', minutos=50)
        _conv, self.bot = self.mensaje('Tenemos la Cama Queen Milán y la Cama Roble.\n¿Cuál te gusta más?',
                                       'bot-ui-1', autor='bot', minutos=49, partes=[
                                           {'id_canal': 'wamid.ui.b1', 'tipo': 'texto',
                                            'texto': 'Tenemos la Cama Queen Milán y la Cama Roble.'},
                                           {'id_canal': 'wamid.ui.b2', 'tipo': 'texto', 'texto': '¿Cuál te gusta más?'}])
        _conv, self.esta = self.mensaje('esta', 'wamid.ui.c3', minutos=40, cita={'id_canal': 'wamid.ui.b1'})
        self.mensaje('Mira esta promo: cama king con cajones, ¿la tienen?', 'wamid.ui.c4', minutos=35,
                     reenviado='muchas')
        self.mensaje('¿y este otro?', 'wamid.ui.c5', minutos=20, cita={'id_canal': 'wamid.de.hace.meses'})
        # Lo que escribe la vendedora sale con la hora de ahora (en orden, después de lo del cliente).
        self.v1 = self.de_la_vendedora(self.conv, 'Sí, la tenemos en gris y en beige.', 'wamid.ui.v1')
        self.v2 = self.de_la_vendedora(self.conv, 'Te mando la foto en un momento.', 'wamid.ui.v2')
        self.v3 = self.de_la_vendedora(self.conv, 'Con gusto, aquí estoy para lo que necesites.', 'wamid.ui.v3')
        self.v4 = self.de_la_vendedora(self.conv, 'Hola, ¿pudiste ver las fotos?', 'wamid.ui.v4')
        Mensaje = self.env['dcasa.mensaje']
        Mensaje._aplicar_eventos([
            self.evento('estado', 'wamid.ui.b1', 48, estado='leido'),
            self.evento('estado', 'wamid.ui.b2', 48, estado='leido'),
            self.evento('estado', 'wamid.ui.v1', 0, estado='enviado'),
            self.evento('estado', 'wamid.ui.v2', 0, estado='entregado'),
            self.evento('estado', 'wamid.ui.v3', 0, estado='leido'),
            self.evento('reaccion', 'wamid.ui.v3', 0, emoji='❤️'),
            self.evento('estado', 'wamid.ui.v4', 0, estado='fallido', error=MOTIVO_24H),
        ])
        # Una conversación de Telegram: ahí los bots no reciben «entregado» ni «leído», así que no hay palomitas.
        self.registrar('Hola desde Telegram', '777002', canal='telegram', minutos=300, nombre='Tomás Telegram')

    # ------------------------------------------------------------------ Lo que se ve
    def test_cita_reenviado_reaccion_y_palomitas_en_las_burbujas(self):
        self.datos_citas()
        self.navegador("""
(async () => {
    await abrirConversacion("Valeria");
    const burbuja = (texto) => [...document.querySelectorAll(".o_dcj_burbuja")].find((b) => b.querySelector(".o_dcj_burbuja_texto")?.textContent.trim() === texto);
    // La cita: quién lo dijo y JUSTO la burbuja citada (Juan respondió en dos).
    const esta = burbuja("esta");
    const cita = esta.querySelector("button.o_dcj_cita");
    if (!cita) { throw new Error("falta la cita sobre «esta»"); }
    if (cita.querySelector(".o_dcj_cita_quien").textContent.trim() !== "Juan") { throw new Error("la cita es de Juan: " + cita.textContent); }
    if (cita.querySelector(".o_dcj_cita_texto").textContent.trim() !== "Tenemos la Cama Queen Milán y la Cama Roble.") { throw new Error("la cita dice: " + cita.textContent); }
    if (esta.querySelector(".o_dcj_cita").compareDocumentPosition(esta.querySelector(".o_dcj_burbuja_texto")) !== Node.DOCUMENT_POSITION_FOLLOWING) {
        throw new Error("la cita va ARRIBA del texto");
    }
    // Un clic lleva al original (y lo marca un momento).
    cita.click();
    await esperar(() => document.querySelector(".o_dcj_burbuja_bot.o_dcj_resaltado"), "el mensaje citado, resaltado");
    // Lo que no está en el historial lo dice.
    const perdida = burbuja("¿y este otro?").querySelector(".o_dcj_cita_perdida");
    if (!perdida || !perdida.textContent.includes("Mensaje que no está en el historial")) { throw new Error("falta «Mensaje que no está en el historial»"); }
    // Reenviado muchas veces.
    const reenviado = burbuja("Mira esta promo: cama king con cajones, ¿la tienen?").querySelector(".o_dcj_reenviado");
    if (!reenviado || reenviado.textContent.trim() !== "Reenviado muchas veces" || !reenviado.querySelector(".fa-share")) { throw new Error("falta «Reenviado muchas veces» con su ícono"); }
    // La reacción del cliente, en la esquina de la burbuja.
    const reaccion = burbuja("Con gusto, aquí estoy para lo que necesites.").querySelector(".o_dcj_reaccion");
    if (!reaccion || reaccion.textContent.trim() !== "❤️") { throw new Error("falta la reacción ❤️"); }
    if (getComputedStyle(reaccion).position !== "absolute") { throw new Error("la reacción va en la esquina"); }
    // Las palomitas: ✓ enviado, ✓✓ gris entregado, ✓✓ azul leído, ⚠ no llegó (con el motivo).
    const palomita = (texto) => burbuja(texto).querySelector(".o_dcj_palomitas");
    const enviado = palomita("Sí, la tenemos en gris y en beige.");
    const entregado = palomita("Te mando la foto en un momento.");
    const leido = palomita("Con gusto, aquí estoy para lo que necesites.");
    const fallido = palomita("Hola, ¿pudiste ver las fotos?");
    const checks = (p) => p.querySelectorAll(".fa-check").length;
    if (!enviado.classList.contains("o_dcj_palomitas_enviado") || checks(enviado) !== 1) { throw new Error("enviado: una palomita"); }
    if (!entregado.classList.contains("o_dcj_palomitas_entregado") || checks(entregado) !== 2) { throw new Error("entregado: dos palomitas"); }
    if (!leido.classList.contains("o_dcj_palomitas_leido") || checks(leido) !== 2) { throw new Error("leído: dos palomitas"); }
    const gris = getComputedStyle(entregado).color, azul = getComputedStyle(leido).color;
    if (gris === azul || azul !== "rgb(19, 64, 177)") { throw new Error("leído va en el azul de la marca y entregado en gris: " + gris + " / " + azul); }
    if (!fallido.querySelector(".fa-exclamation-triangle") || !fallido.textContent.includes("No llegó") || !fallido.title.includes("24 horas")) {
        throw new Error("no llegó: ícono, palabra y el motivo al pasar el mouse: " + fallido.title);
    }
    if (!leido.title.startsWith("Leído")) { throw new Error("al pasar el mouse dice «Leído» y la hora: " + leido.title); }
    // Los mensajes del cliente no llevan palomitas.
    if (burbuja("esta").querySelector(".o_dcj_palomitas")) { throw new Error("un mensaje del cliente no lleva palomitas"); }
    // En Telegram no hay palomitas.
    aqui(".o_dcj_fila", "Tomás").click();
    await esperar(() => aqui(".o_dcj_burbuja_texto", "Hola desde Telegram"), "el hilo de Telegram");
    if (document.querySelector(".o_dcj_palomitas")) { throw new Error("Telegram no da palomitas"); }
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
""")

    def test_responder_cita_el_mensaje_del_cliente_y_sale_con_la_cita(self):
        self.datos_citas()
        self.navegador("""
(async () => {
    await abrirConversacion("Valeria");
    const esta = [...document.querySelectorAll(".o_dcj_burbuja_cliente")].find((b) => b.querySelector(".o_dcj_burbuja_texto")?.textContent.trim() === "esta");
    const boton = esta.querySelector(".o_dcj_responder");
    if (!boton) { throw new Error("falta «Responder» en el mensaje del cliente"); }
    if (getComputedStyle(boton).opacity !== "0") { throw new Error("«Responder» aparece solo al pasar el mouse o con el teclado"); }
    if (document.querySelector(".o_dcj_burbuja_bot .o_dcj_responder, .o_dcj_burbuja_vendedora .o_dcj_responder")) {
        throw new Error("«Responder» va en los mensajes del cliente");
    }
    boton.focus();
    await esperar(() => getComputedStyle(boton).opacity === "1", "«Responder» visible con el foco");
    boton.click();
    const citando = await esperar(() => document.querySelector(".o_dcj_citando"), "la cita arriba de la caja");
    if (!citando.textContent.includes("Respondes a Cliente") || !citando.textContent.includes("esta")) { throw new Error("la caja dice a qué respondes: " + citando.textContent); }
    const caja = document.querySelector("#o_dcj_texto");
    await esperar(() => document.activeElement === caja, "el foco en la caja de texto");
    await escribir(caja, "Sí, esa es la Cama Queen Milán.");
    tecla(caja, "Enter");
    await esperar(() => !document.querySelector(".o_dcj_citando"), "que la cita se vaya al enviar");
    const nueva = await esperar(() => [...document.querySelectorAll(".o_dcj_burbuja_vendedora")].find((b) => b.textContent.includes("Sí, esa es la Cama Queen Milán.")), "la respuesta en el hilo");
    const cita = nueva.querySelector(".o_dcj_cita");
    if (!cita || !cita.textContent.includes("Cliente") || !cita.textContent.includes("esta")) { throw new Error("la respuesta muestra la cita: " + nueva.textContent); }
    // Quitar una cita antes de enviar.
    const otra = [...document.querySelectorAll(".o_dcj_burbuja_cliente .o_dcj_responder")][0];
    otra.click();
    await esperar(() => document.querySelector(".o_dcj_citando"), "otra cita");
    document.querySelector(".o_dcj_citando button[aria-label='Quitar la cita']").click();
    await esperar(() => !document.querySelector(".o_dcj_citando"), "la cita quitada");
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
""")
        enviado = self.al_worker('/odoo/enviar')[-1]
        self.assertEqual(enviado['responde_a'], 'wamid.ui.c3', 'la cita sale al canal con el id del mensaje del cliente')
        self.assertEqual(enviado['texto'], 'Sí, esa es la Cama Queen Milán.')

    def test_palomitas_y_reaccion_llegan_en_vivo_sin_recargar(self):
        self.datos_citas()
        self.navegador("""
(async () => {
    await abrirConversacion("Valeria");
    const burbuja = (texto) => [...document.querySelectorAll(".o_dcj_burbuja")].find((b) => b.querySelector(".o_dcj_burbuja_texto")?.textContent.trim() === texto);
    const antes = document.querySelectorAll(".o_dcj_burbuja").length;
    const ts = new Date().toISOString();
    const r = await fetch("/dcasa/juan/v1/eventos", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: "Bearer __TOKEN__" },
        body: JSON.stringify({ eventos: [
            { tipo: "estado", canal: "whatsapp_cloud", id_externo: "__CLIENTE__", id_mensaje: "wamid.ui.v1", estado: "leido", ts },
            { tipo: "reaccion", canal: "whatsapp_cloud", id_externo: "__CLIENTE__", id_mensaje: "wamid.ui.v2", emoji: "👍", ts },
        ] }),
    });
    if (!r.ok) { throw new Error("la API de Juan respondió " + r.status); }
    await esperar(() => burbuja("Sí, la tenemos en gris y en beige.").querySelector(".o_dcj_palomitas_leido"), "la palomita azul, sin recargar", 8000);
    await esperar(() => burbuja("Te mando la foto en un momento.").querySelector(".o_dcj_reaccion")?.textContent.includes("👍"), "la reacción, sin recargar", 8000);
    if (document.querySelectorAll(".o_dcj_burbuja").length !== antes) { throw new Error("una palomita o una reacción no es un mensaje nuevo"); }
    if (document.querySelector(".o_dcj_nuevos")) { throw new Error("no es «1 mensaje nuevo»"); }
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
""".replace("__TOKEN__", TOKEN_ODOO).replace("__CLIENTE__", CLIENTE))

    # ------------------------------------------------------------------ Chrome con eventos de verdad (rueda, dedo)
    @contextlib.contextmanager
    def _chrome(self, ancho, alto, usuario=VENDEDORA, tactil=False, escala=1):
        """Chrome como en ``browser_js`` pero devolviendo el navegador, para la rueda, el dedo y las capturas."""
        self.browser_size = f'{ancho}x{alto}'
        self.touch_enabled = tactil
        browser = ChromeBrowser(self, headless=True)
        with self.allow_requests(browser=browser), contextlib.ExitStack() as atexit:
            atexit.callback(self._wait_remaining_requests)
            atexit.enter_context(browser.cleanup)
            if 'bus.bus' in self.env.registry:
                from odoo.addons.bus.websocket import CloseCode, WebsocketConnectionHandler, _kick_all  # noqa: PLC0415
                atexit.callback(_kick_all, CloseCode.KILL_NOW)
                atexit.enter_context(patch.object(WebsocketConnectionHandler, 'websocket_allowed', return_value=True))
            self.authenticate(usuario, usuario, browser=browser)
            self.cr.flush()
            self.cr.clear()
            if tactil:
                browser._websocket_request('Emulation.setTouchEmulationEnabled', params={'enabled': True, 'maxTouchPoints': 5})
            browser._websocket_request('Emulation.setDeviceMetricsOverride', params={
                'mobile': tactil, 'width': ancho, 'height': alto, 'deviceScaleFactor': escala})
            yield browser

    def _js(self, browser, expresion, timeout=60):
        res = browser._websocket_request('Runtime.evaluate', params={
            'expression': expresion, 'awaitPromise': True, 'returnByValue': True}, timeout=timeout)
        if res.get('exceptionDetails'):
            self.fail(f'JavaScript falló: {json.dumps(res["exceptionDetails"], default=str)[:600]}')
        return res['result'].get('value')

    def _abrir(self, browser):
        self.avisos_anteriores_ya_viejos()
        browser.navigate_to(self.base_url() + ACCION, wait_stop=True)
        self.assertTrue(browser._wait_ready('odoo.isReady'), 'Conversaciones no terminó de cargar')
        self._js(browser, AYUDAS)
        self._js(browser, '(async () => { await abrirConversacion("Valeria"); '
                          'await new Promise((ok) => setTimeout(ok, 600)); return true; })()', timeout=90)

    MEDIR = """(() => {
        const h = document.querySelector('.o_dcj_hilo_cuerpo');
        return {scroll: h.scrollTop, alto: h.scrollHeight, visible: h.clientHeight, desborde: getComputedStyle(h).overflowY,
                paginaAncha: document.documentElement.scrollWidth > innerWidth};
    })()"""

    def _arriba(self, browser):
        self._js(browser, '(() => { const h = document.querySelector(".o_dcj_hilo_cuerpo"); h.scrollTop = 0; '
                          'return new Promise((ok) => setTimeout(() => ok(true), 400)); })()')

    def test_el_chat_baja_con_la_rueda_y_cumple_la_marca(self):
        self.datos_citas()
        with self._chrome(1440, 520) as browser:
            self._abrir(browser)
            self._arriba(browser)
            antes = self._js(browser, self.MEDIR)
            self.assertIn(antes['desborde'], ('auto', 'scroll'))
            self.assertGreater(antes['alto'], antes['visible'] + 80, 'la prueba necesita un hilo más alto que la ventana')
            caja = self._js(browser, 'JSON.parse(JSON.stringify(document.querySelector(".o_dcj_hilo_cuerpo").getBoundingClientRect()))')
            for _ in range(4):
                browser._websocket_request('Input.dispatchMouseEvent', params={
                    'type': 'mouseWheel', 'x': caja['x'] + caja['width'] / 2, 'y': caja['y'] + caja['height'] / 2,
                    'deltaX': 0, 'deltaY': 300})
            self._js(browser, 'new Promise((ok) => setTimeout(() => ok(true), 600))')
            despues = self._js(browser, self.MEDIR)
            self.assertGreater(despues['scroll'], antes['scroll'] + 80, f'la rueda no baja el chat: {despues}')
            # La marca: sistema plano, amarillo solo sobre azul, contraste (mismo contrato que test_panel_visual).
            faltas = self._js(browser, AUDITAR)
            self.assertFalse(faltas, 'Las burbujas nuevas rompen el contrato de la marca:\n' + '\n'.join(faltas))

    def test_celular_responder_con_el_dedo_apretado_y_el_chat_baja_con_el_dedo(self):
        self.datos_citas()
        with self._chrome(390, 844, tactil=True, escala=2) as browser:
            self._abrir(browser)
            self.assertFalse(self._js(browser, self.MEDIR)['paginaAncha'], 'en el celular nada se corre de lado')
            toque = lambda tipo, puntos: browser._websocket_request(   # noqa: E731
                'Input.dispatchTouchEvent', params={'type': tipo, 'touchPoints': puntos})
            # El dedo baja (y sube) el chat: arrastrar sobre las burbujas, incluidas las del cliente.
            self._arriba(browser)
            antes = self._js(browser, self.MEDIR)
            toque('touchStart', [{'x': 120, 'y': 520}])
            for paso in range(1, 16):
                toque('touchMove', [{'x': 120, 'y': 520 - paso * 20}])
            toque('touchEnd', [])
            self._js(browser, 'new Promise((ok) => setTimeout(() => ok(true), 700))')
            despues = self._js(browser, self.MEDIR)
            self.assertGreater(despues['scroll'], antes['scroll'] + 100, f'el dedo no baja el chat: {despues}')
            # Dedo apretado sobre «esta» (sin moverlo): aparece «Responder»; tocarlo deja la cita en la caja.
            punto = self._js(browser, """(() => {
                const b = [...document.querySelectorAll('.o_dcj_burbuja_cliente')].find((x) => x.querySelector('.o_dcj_burbuja_texto')?.textContent.trim() === 'esta');
                b.scrollIntoView({block: 'center'});
                const r = b.getBoundingClientRect();
                return {x: r.left + 30, y: r.top + r.height / 2};
            })()""")
            self._js(browser, 'new Promise((ok) => setTimeout(() => ok(true), 300))')
            toque('touchStart', [punto])
            self._js(browser, 'new Promise((ok) => setTimeout(() => ok(true), 800))')
            toque('touchEnd', [])
            boton = self._js(browser, """(() => {
                const b = document.querySelector('.o_dcj_burbuja_cliente.o_acciones .o_dcj_responder');
                if (!b) { return null; }
                const r = b.getBoundingClientRect();
                return {x: r.left + r.width / 2, y: r.top + r.height / 2, alto: r.height, derecha: r.right, opacidad: getComputedStyle(b).opacity};
            })()""")
            self.assertTrue(boton, 'con el dedo apretado aparece «Responder»')
            self.assertEqual(boton['opacidad'], '1')
            self.assertGreaterEqual(boton['alto'], 44, 'en el celular el botón se toca fácil (44 px, como los demás)')
            self.assertLessEqual(boton['derecha'], 390, '«Responder» cabe en la pantalla')
            toque('touchStart', [{'x': boton['x'], 'y': boton['y']}])
            toque('touchEnd', [])
            citando = self._js(browser, """(async () => {
                for (let i = 0; i < 40 && !document.querySelector('.o_dcj_citando'); i++) { await new Promise((ok) => setTimeout(ok, 100)); }
                return document.querySelector('.o_dcj_citando')?.textContent || '';
            })()""")
            self.assertIn('Respondes a Cliente', citando)
            self.assertFalse(self._js(browser, self.MEDIR)['paginaAncha'])

    # ------------------------------------------------------------------ Capturas para la dueña (datos de prueba)
    def test_capturas_para_la_duena(self):
        carpeta = os.environ.get(VAR_CAPTURAS)
        if not carpeta:
            self.skipTest(f'solo con {VAR_CAPTURAS}=<carpeta>')
        destino = Path(carpeta)
        destino.mkdir(parents=True, exist_ok=True)
        self.datos_citas()

        def foto(browser, nombre):
            datos = browser._websocket_request('Page.captureScreenshot', params={'format': 'png'}, timeout=60)['data']
            (destino / f'{nombre}.png').write_bytes(base64.b64decode(datos))

        quieto = """(async () => {
            const e = document.createElement('style');
            e.textContent = '*, *::before, *::after { transition: none !important; animation: none !important; caret-color: transparent !important; } .o_brian_lanzador { display: none !important; }';
            document.head.appendChild(e);
            await document.fonts.ready;
            return true;
        })()"""
        responder = """(async () => {
            const b = [...document.querySelectorAll('.o_dcj_burbuja_cliente')].find((x) => x.querySelector('.o_dcj_burbuja_texto')?.textContent.trim() === 'esta');
            b.scrollIntoView({block: 'center'});
            b.classList.add('o_acciones');
            await new Promise((ok) => setTimeout(ok, 300));
            return true;
        })()"""
        citar = """(async () => {
            const b = [...document.querySelectorAll('.o_dcj_burbuja_cliente')].find((x) => x.querySelector('.o_dcj_burbuja_texto')?.textContent.trim() === 'esta');
            b.querySelector('.o_dcj_responder').click();
            const caja = document.querySelector('#o_dcj_texto');
            caja.value = 'Sí, esa es la Cama Queen Milán.';
            caja.dispatchEvent(new Event('input', {bubbles: true}));
            await new Promise((ok) => setTimeout(ok, 400));
            b.classList.remove('o_acciones');
            return true;
        })()"""
        enviar = """(async () => {
            document.querySelector('.o_dcj_enviar').click();
            for (let i = 0; i < 50 && document.querySelector('.o_dcj_citando'); i++) { await new Promise((ok) => setTimeout(ok, 100)); }
            const h = document.querySelector('.o_dcj_hilo_cuerpo');
            h.scrollTop = h.scrollHeight;
            await new Promise((ok) => setTimeout(ok, 600));
            return true;
        })()"""
        with self._chrome(1440, 900, escala=2) as browser:
            self._abrir(browser)
            self._js(browser, quieto)
            self._arriba(browser)
            foto(browser, 'computadora_1_cita_reenviado_y_palomitas')
            self._js(browser, '(async () => { const h = document.querySelector(".o_dcj_hilo_cuerpo"); h.scrollTop = h.scrollHeight; '
                              'await new Promise((ok) => setTimeout(ok, 400)); return true; })()')
            foto(browser, 'computadora_2_reaccion_y_no_llego')
            self._js(browser, responder)
            foto(browser, 'computadora_3_boton_responder')
            self._js(browser, citar)
            foto(browser, 'computadora_4_respondes_a_cliente')
            self._js(browser, enviar)
            foto(browser, 'computadora_5_respuesta_con_cita')
        with self._chrome(390, 844, tactil=True, escala=2) as browser:
            self._abrir(browser)
            self._js(browser, quieto)
            self._arriba(browser)
            foto(browser, 'celular_1_cita_y_reenviado')
            self._js(browser, '(async () => { const h = document.querySelector(".o_dcj_hilo_cuerpo"); h.scrollTop = h.scrollHeight; '
                              'await new Promise((ok) => setTimeout(ok, 400)); return true; })()')
            foto(browser, 'celular_2_palomitas_reaccion_y_no_llego')
            self._js(browser, responder)
            foto(browser, 'celular_3_dedo_apretado_responder')
            self._js(browser, citar)
            foto(browser, 'celular_4_respondes_a_cliente')
