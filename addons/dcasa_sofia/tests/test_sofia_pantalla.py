"""La pantalla de Sofía en el navegador (2026-11-06, la dueña: «Sofía puede mejorar mucho, sobre todo la interfaz
visual»). Solo la interfaz: qué propone, los permisos y lo que hace cada botón no cambian (ver ``test_sofia.py``).

* Lo urgente arriba: secciones «Hoy sin falta», «Hoy» y «Cuando puedas», en ese orden, la primera en azul.
* Filtro rápido por tipo y, para Gerencia, por vendedora, con conteos que cuadran con las tarjetas.
* «Todo al día» cuando no queda nada, y «Listo por aquí» (con «Ver todo») cuando el filtro se quedó vacío.
* Al aprobar o descartar la pantalla no salta: la tarjeta dice lo que pasó en su lugar, del mismo alto, y después se
  cierra despacio.
* El bug de siempre: la pantalla baja con la rueda del ratón y con el dedo (eventos de verdad por el protocolo de
  Chrome, no ``scrollTop``), y los filtros se quedan a la vista.
"""
import contextlib
import json
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.addons.dcasa_contactos.tests.test_fijo_y_copiar_navegador import COMUN
from odoo.addons.dcasa_conversaciones.models import crm_reglas as CRM
from odoo.tests import HttpCase, new_test_user, tagged
from odoo.tests.common import ChromeBrowser

AZUL = 'rgb(19, 64, 177)'   # #1340B1


@tagged('post_install', '-at_install')
class TestPantallaDeSofia(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['dcasa.juan.ajustes'].obtener().reparto_activa_minutos = 0
        grupos = 'base.group_user,sales_team.group_sale_salesman'
        cls.ana = new_test_user(cls.env, login='ana_pantalla', password='ana_pantalla', name='Ana Pantalla',
                                groups=grupos)
        cls.bea = new_test_user(cls.env, login='bea_pantalla', password='bea_pantalla', name='Bea Pantalla',
                                groups=grupos)
        cls.sin_nada = new_test_user(cls.env, login='nada_pantalla', password='nada_pantalla', name='Nada Pantalla',
                                     groups=grupos)
        cls.gerente = new_test_user(cls.env, login='ger_pantalla', password='ger_pantalla', name='Gerencia Pantalla',
                                    groups='base.group_user,sales_team.group_sale_manager')
        numero = iter(range(5001, 5100))

        def cliente(nombre, vendedora=None, temperatura=CRM.CALIENTE, canal='whatsapp_qr', horas=5, estado='bot',
                    autor='bot'):
            celular = f'5076000{next(numero)}'
            partner = cls.env['res.partner'].create({
                'name': nombre, 'phone': f'+{celular}', 'email': f'{celular}@example.com'})
            ultimo = fields.Datetime.now() - timedelta(hours=horas)
            conv = cls.env['dcasa.conversacion'].create({
                'canal': canal, 'id_externo': celular, 'partner_id': partner.id, 'estado': estado,
                'ultimo_mensaje_cliente': ultimo, 'ultimo_mensaje_autor': autor, 'ultima_actividad': ultimo,
                'asignada_a': vendedora.id if vendedora and estado == 'humano' else False})
            lead = cls.env['crm.lead'].with_context(dcasa_auto=True).create({
                'name': 'WhatsApp (QR): juego de comedor', 'type': 'opportunity', 'partner_id': partner.id,
                'user_id': vendedora.id if vendedora else False, 'dcasa_temperatura': temperatura})
            conv.oportunidad_id = lead
            conv.seguimiento_proximo = False
            return conv

        # Ana: una que espera respuesta (hoy sin falta), calientes y tibios, y una para llamar.
        cliente('Rosa Espera', cls.ana, estado='humano', autor='cliente', horas=3)
        for nombre in ('Carla Caliente', 'Diego Caliente', 'Elena Caliente'):
            cliente(nombre, cls.ana)
        for nombre in ('Fabio Tibio', 'Gina Tibia'):
            cliente(nombre, cls.ana, temperatura=CRM.TIBIO)
        cliente('Hugo Messenger', cls.ana, canal='messenger', horas=30)
        # Bea: dos.
        cliente('Irene Bea', cls.bea)
        cliente('Jaime Bea', cls.bea, temperatura=CRM.TIBIO)
        # Sin vendedora (Gerencia la reparte).
        cliente('Karla Sin Vendedora')
        cls.env['dcasa.sofia'].sudo()._analizar('boton')

    def pendientes(self, usuario):
        return self.env['dcasa.sofia.propuesta'].with_user(usuario).search([('estado', '=', 'pendiente')])

    # ------------------------------------------------------------------ Lo urgente arriba

    def test_lo_urgente_arriba_y_bien_distinto(self):
        codigo = '(async () => {' + COMUN + """
            await esperar(() => document.querySelector('.o_sofia_tarjeta'), 'las tarjetas');
            sinErrores();
            const secciones = [...document.querySelectorAll('.o_sofia_seccion')];
            const orden = secciones.map((s) => [...s.classList].find((c) => /^o_sofia_s[0-9]$/.test(c)));
            if (orden[0] !== 'o_sofia_s3' || orden.join() !== [...orden].sort().reverse().join()) {
                throw new Error('Las secciones no van de lo urgente a lo que puede esperar: ' + orden.join());
            }
            const titulo = secciones[0].querySelector('.o_sofia_seccion_titulo');
            if (!titulo.textContent.includes('Hoy sin falta')) {
                throw new Error('La primera sección no es «Hoy sin falta»: ' + titulo.textContent);
            }
            if (getComputedStyle(titulo).backgroundColor !== 'AZUL') {
                throw new Error('«Hoy sin falta» no se distingue: ' + getComputedStyle(titulo).backgroundColor);
            }
            const cuenta = Number(titulo.querySelector('.o_sofia_seccion_cuenta').textContent);
            if (cuenta !== secciones[0].querySelectorAll('.o_sofia_tarjeta').length) {
                throw new Error('El número de «Hoy sin falta» no cuadra con sus tarjetas');
            }
            const espera = [...secciones[0].querySelectorAll('.o_sofia_tarjeta')]
                .find((t) => t.textContent.includes('Rosa Espera'));
            if (!espera || espera.dataset.tipo !== 'contestar') {
                throw new Error('Quien espera respuesta no está en «Hoy sin falta»');
            }
            // El resumen de arriba dice cuántas hay de cada prioridad.
            const resumen = document.querySelector('.o_sofia_resumen .o_sofia_r3');
            if (!resumen || Number(resumen.querySelector('strong').textContent) !== cuenta) {
                throw new Error('El resumen no dice cuántas son para hoy sin falta');
            }
            // El mensaje se lee como en el chat y se edita con «Editar».
            const conMensaje = document.querySelector('.o_sofia_tarjeta[data-tipo="escribir"]');
            if (!conMensaje.querySelector('.o_sofia_burbuja') || conMensaje.querySelector('textarea')) {
                throw new Error('El mensaje no se muestra para leer');
            }
            conMensaje.querySelector('.o_sofia_editar').click();
            await esperar(() => conMensaje.querySelector('textarea.o_sofia_mensaje'), 'la caja para editar');
            // La acción principal es la grande; «Descartar» va aparte, abajo.
            const principal = conMensaje.querySelector('.o_sofia_botones .o_sofia_principal');
            if (!principal || principal.dataset.accion !== 'chat') {
                throw new Error('La acción principal no es abrir el chat');
            }
            if (conMensaje.querySelector('.o_sofia_botones .o_sofia_descartar')
                    || !conMensaje.querySelector('.o_sofia_pie .o_sofia_descartar')) {
                throw new Error('«Descartar» está junto a las acciones principales');
            }
            sinErrores();
            console.log('test successful');
        })();""".replace('AZUL', AZUL)
        self.browser_js('/odoo/sofia', codigo, login='ana_pantalla', timeout=120)

    # ------------------------------------------------------------------ Filtros con conteos

    def test_filtro_por_tipo_y_por_vendedora_con_conteos(self):
        codigo = '(async () => {' + COMUN + """
            await esperar(() => document.querySelector('.o_sofia_tarjeta'), 'las tarjetas');
            sinErrores();
            const tarjetas = () => [...document.querySelectorAll('.o_sofia_tarjeta')];
            const chipsTipo = () => [...document.querySelectorAll('.o_sofia_chip[data-tipo]')];
            const chipsPara = () => [...document.querySelectorAll('.o_sofia_chip[data-para]')];
            const cuenta = (chip) => Number(chip.querySelector('.o_sofia_cuenta').textContent);
            const total = tarjetas().length;
            const todo = chipsTipo().find((c) => c.dataset.tipo === 'todas');
            if (cuenta(todo) !== total || todo.getAttribute('aria-pressed') !== 'true') {
                throw new Error(`«Todo» dice ${cuenta(todo)} y hay ${total}`);
            }
            const tipos = chipsTipo().filter((c) => c.dataset.tipo !== 'todas').map((c) => c.dataset.tipo);
            for (const tipo of ['contestar', 'escribir', 'llamar', 'asignar']) {
                if (!tipos.includes(tipo)) { throw new Error('Falta el filtro ' + tipo + ': ' + tipos.join()); }
            }
            let suma = 0;
            for (const tipo of tipos) {
                const chip = chipsTipo().find((c) => c.dataset.tipo === tipo);
                const n = cuenta(chip);
                suma += n;
                chip.click();
                await esperar(() => chip.getAttribute('aria-pressed') === 'true' && tarjetas().length === n
                              && tarjetas().every((t) => t.dataset.tipo === tipo), `solo las de ${tipo} (${n})`);
            }
            if (suma !== total) { throw new Error(`Los tipos suman ${suma} y hay ${total}`); }
            todo.click();
            await esperar(() => tarjetas().length === total, 'todas otra vez');
            // Por vendedora (Gerencia): cada una con su número; sus tarjetas dicen para quién son.
            const personas = chipsPara().filter((c) => c.dataset.para !== 'todas');
            const nombres = personas.map((c) => c.querySelector('.o_sofia_chip_nombre').textContent);
            for (const nombre of ['Ana Pantalla', 'Bea Pantalla', 'Sin vendedora']) {
                if (!nombres.includes(nombre)) { throw new Error('Falta ' + nombre + ': ' + nombres.join()); }
            }
            for (const nombre of ['Ana Pantalla', 'Bea Pantalla']) {
                const chip = chipsPara().find((c) => c.querySelector('.o_sofia_chip_nombre').textContent === nombre);
                const n = cuenta(chip);
                chip.click();
                await esperar(() => chip.getAttribute('aria-pressed') === 'true' && tarjetas().length === n
                              && tarjetas().every((t) => t.querySelector('.o_sofia_para_quien').textContent
                                  .includes('Para ' + nombre)), `solo las de ${nombre} (${n})`);
                // Los números por tipo son los de ella.
                const deElla = cuenta(chipsTipo().find((c) => c.dataset.tipo === 'todas'));
                if (deElla !== n) { throw new Error(`Con ${nombre}, «Todo» dice ${deElla} y ella tiene ${n}`); }
            }
            // Tipo y vendedora a la vez: el número de cada vendedora es el de ese tipo.
            const elegido = (chips, clave) => chips().find((c) => c.getAttribute('aria-pressed') === 'true')
                ?.dataset[clave];
            chipsPara().find((c) => c.dataset.para === 'todas').click();
            await esperar(() => elegido(chipsPara, 'para') === 'todas', 'todo el equipo');
            chipsTipo().find((c) => c.dataset.tipo === 'escribir').click();
            await esperar(() => elegido(chipsTipo, 'tipo') === 'escribir'
                          && tarjetas().every((t) => t.dataset.tipo === 'escribir'), 'solo «Escribirle»');
            const ana = chipsPara().find((c) => c.querySelector('.o_sofia_chip_nombre').textContent === 'Ana Pantalla');
            const anaEscribir = tarjetas().filter((t) => t.textContent.includes('Para Ana Pantalla')).length;
            if (cuenta(ana) !== anaEscribir) {
                throw new Error(`Con «Escribirle», Ana dice ${cuenta(ana)} y tiene ${anaEscribir}`);
            }
            sinErrores();
            console.log('test successful');
        })();"""
        self.browser_js('/odoo/sofia', codigo, login='ger_pantalla', timeout=120)

    def test_la_vendedora_no_ve_el_filtro_de_vendedoras(self):
        codigo = '(async () => {' + COMUN + """
            await esperar(() => document.querySelector('.o_sofia_tarjeta'), 'las tarjetas');
            if (document.querySelector('.o_sofia_chip[data-para]')) {
                throw new Error('La vendedora ve el filtro por vendedora');
            }
            if (!document.body.textContent.includes('Irene Bea')) { throw new Error('No ve lo suyo'); }
            const ajenas = ['Rosa Espera', 'Carla Caliente', 'Karla Sin Vendedora'];
            const ve = (n) => document.body.textContent.includes(n);
            if (ajenas.some(ve) || document.querySelector('.o_sofia_para_quien')) {
                throw new Error('La vendedora ve lo de otra');
            }
            const todo = document.querySelector('.o_sofia_chip[data-tipo="todas"] .o_sofia_cuenta');
            if (Number(todo.textContent) !== document.querySelectorAll('.o_sofia_tarjeta').length) {
                throw new Error('El número de «Todo» no cuadra');
            }
            sinErrores();
            console.log('test successful');
        })();"""
        self.browser_js('/odoo/sofia', codigo, login='bea_pantalla', timeout=120)

    # ------------------------------------------------------------------ Estados vacíos

    def test_todo_al_dia(self):
        """Sin nada pendiente: «Todo al día», sin filtros que no sirven."""
        codigo = '(async () => {' + COMUN + """
            const vacio = await esperar(() => document.querySelector('.o_sofia_al_dia'), '«Todo al día»');
            if (!vacio.textContent.includes('Todo al día') || !vacio.textContent.includes('No tienes nada pendiente')) {
                throw new Error('No dice que está todo al día: ' + vacio.textContent);
            }
            if (document.querySelector('.o_sofia_filtros') || document.querySelector('.o_sofia_tarjeta')) {
                throw new Error('Sin nada pendiente sobran los filtros');
            }
            sinErrores();
            console.log('test successful');
        })();"""
        self.browser_js('/odoo/sofia', codigo, login='nada_pantalla', timeout=120)

    def test_al_terminar_queda_todo_al_dia(self):
        """Bea descarta sus dos tarjetas: cada una dice «Descartada» en su lugar y al final queda «Todo al día»."""
        self.assertEqual(len(self.pendientes(self.bea)), 2)
        codigo = '(async () => {' + COMUN + """
            await esperar(() => document.querySelectorAll('.o_sofia_tarjeta').length === 2, 'sus dos tarjetas');
            for (let i = 0; i < 2; i++) {
                document.querySelector('.o_sofia_tarjeta .o_sofia_descartar').click();
                const hecha = await esperar(() => document.querySelector('.o_sofia_hecha.o_descartada'),
                                            'la tarjeta descartada en su lugar');
                if (!hecha.textContent.includes('Descartada')) {
                    throw new Error('No dice que se descartó: ' + hecha.textContent);
                }
                await esperar(() => !document.querySelector('.o_sofia_hecha'), 'que se cierre');
            }
            await esperar(() => document.querySelector('.o_sofia_al_dia'), '«Todo al día»');
            sinErrores();
            console.log('test successful');
        })();"""
        self.browser_js('/odoo/sofia', codigo, login='bea_pantalla', timeout=120)
        self.assertFalse(self.pendientes(self.bea))
        self.assertEqual(set(self.env['dcasa.sofia.propuesta'].sudo().search([
            ('usuario_id', '=', self.bea.id)]).mapped('estado')), {'descartada'})

    def test_filtro_vacio_ofrece_ver_todo(self):
        """Gerencia filtra «Llamarlo», lo resuelve y la pantalla dice «Listo por aquí» con «Ver todo»."""
        codigo = '(async () => {' + COMUN + """
            await esperar(() => document.querySelector('.o_sofia_tarjeta'), 'las tarjetas');
            const total = document.querySelectorAll('.o_sofia_tarjeta').length;
            document.querySelector('.o_sofia_chip[data-tipo="llamar"]').click();
            await esperar(() => document.querySelectorAll('.o_sofia_tarjeta').length === 1, 'solo «Llamarlo»');
            document.querySelector('.o_sofia_tarjeta .o_sofia_descartar').click();
            const vacio = await esperar(() => document.querySelector('.o_sofia_filtro_vacio'), '«Listo por aquí»');
            if (!vacio.textContent.includes('«Llamarlo»')) {
                throw new Error('No dice qué filtro quedó vacío: ' + vacio.textContent);
            }
            const chip = document.querySelector('.o_sofia_chip[data-tipo="llamar"]');
            if (!chip || chip.querySelector('.o_sofia_cuenta').textContent !== '0') {
                throw new Error('El filtro elegido debe quedarse (en 0) para que la tira no salte');
            }
            const verTodo = vacio.querySelector('.o_sofia_ver_todo');
            if (!verTodo.textContent.includes(String(total - 1))) {
                throw new Error('«Ver todo» no dice cuántas quedan: ' + verTodo.textContent);
            }
            verTodo.click();
            await esperar(() => document.querySelectorAll('.o_sofia_tarjeta').length === total - 1, 'todas otra vez');
            sinErrores();
            console.log('test successful');
        })();"""
        self.browser_js('/odoo/sofia', codigo, login='ger_pantalla', timeout=120)

    # ------------------------------------------------------------------ No salta al aprobar

    def test_al_aprobar_no_salta_la_pantalla(self):
        """Ana crea la tarea de llamar a uno y descarta otro: la tarjeta de abajo NO se mueve mientras la resuelta dice
        lo que pasó (nada nuevo queda bajo el dedo); después la lista se cierra despacio."""
        codigo = '(async () => {' + COMUN + """
            const pausa = (ms) => new Promise((ok) => setTimeout(ok, ms));
            await esperar(() => document.querySelector('.o_sofia_tarjeta'), 'las tarjetas');
            const pantalla = document.querySelector('.o_action.o_sofia');
            const probar = async (tarjeta, boton, clase, dice) => {
                const lista = [...tarjeta.parentElement.children];
                const siguiente = lista[lista.indexOf(tarjeta) + 1]
                    || tarjeta.closest('.o_sofia_seccion').nextElementSibling;
                if (!siguiente) { throw new Error('La tarjeta elegida no tiene nada debajo'); }
                const alto = tarjeta.getBoundingClientRect().height;
                const antes = siguiente.getBoundingClientRect().top;
                const scroll = pantalla.scrollTop;
                tarjeta.querySelector(boton).click();
                const hecha = await esperar(() => document.querySelector('.o_sofia_hecha.' + clase), 'la resuelta');
                if (!hecha.textContent.includes(dice)) { throw new Error('No dice lo que pasó: ' + hecha.textContent); }
                for (const espera of [0, 800]) {
                    await pausa(espera);
                    const ahora = siguiente.getBoundingClientRect().top;
                    if (Math.abs(ahora - antes) > 2 || Math.abs(pantalla.scrollTop - scroll) > 2) {
                        throw new Error(`La pantalla saltó: la de abajo pasó de ${antes} a ${ahora}`);
                    }
                    if (Math.abs(hecha.getBoundingClientRect().height - alto) > 2) {
                        throw new Error('La resuelta no guardó el alto de la tarjeta');
                    }
                }
                await esperar(() => !document.body.contains(hecha), 'que la resuelta se cierre');
                const despues = siguiente.getBoundingClientRect().top;
                if (despues > antes - alto + 20) {
                    throw new Error(`La lista no se cerró: la de abajo pasó de ${antes} a ${despues}`);
                }
            };
            const llamar = document.querySelector('.o_sofia_tarjeta[data-tipo="llamar"]');
            await probar(llamar, '.o_sofia_accion[data-accion="tarea"]', 'o_listo', 'Tarea creada');
            const primera = document.querySelector('.o_sofia_tarjeta');
            await probar(primera, '.o_sofia_descartar', 'o_descartada', 'Descartada');
            sinErrores();
            console.log('test successful');
        })();"""
        self.browser_js('/odoo/sofia', codigo, login='ana_pantalla', timeout=120)
        propuestas = self.env['dcasa.sofia.propuesta'].sudo().search([('usuario_id', '=', self.ana.id)])
        self.assertEqual(propuestas.filtered(lambda p: p.tipo == 'llamar').estado, 'aplicada')
        self.assertEqual(len(propuestas.filtered(lambda p: p.estado == 'descartada')), 1)

    # ------------------------------------------------------------------ El scroll (rueda y dedo de verdad)

    @contextlib.contextmanager
    def _chrome(self, ancho, alto, usuario, tactil=False):
        """Chrome como en ``browser_js``, pero devolviendo el navegador para mandarle eventos de verdad."""
        self.browser_size = f'{ancho}x{alto}'
        self.touch_enabled = tactil
        browser = ChromeBrowser(self, headless=True)
        with self.allow_requests(browser=browser), contextlib.ExitStack() as atexit:
            atexit.callback(self._wait_remaining_requests)
            atexit.enter_context(browser.cleanup)
            if 'bus.bus' in self.env.registry:    # igual que browser_js: el websocket del bus en pruebas
                from odoo.addons.bus.websocket import CloseCode, WebsocketConnectionHandler, _kick_all  # noqa: PLC0415
                atexit.callback(_kick_all, CloseCode.KILL_NOW)
                atexit.enter_context(patch.object(WebsocketConnectionHandler, 'websocket_allowed', return_value=True))
            self.authenticate(usuario, usuario, browser=browser)
            self.cr.flush()
            self.cr.clear()
            if tactil:
                browser._websocket_request('Emulation.setTouchEmulationEnabled', params={
                    'enabled': True, 'maxTouchPoints': 5})
                browser._websocket_request('Emulation.setDeviceMetricsOverride', params={
                    'mobile': True, 'width': ancho, 'height': alto, 'deviceScaleFactor': 2})
            yield browser

    def _js(self, browser, expresion, timeout=60):
        res = browser._websocket_request('Runtime.evaluate', params={
            'expression': f'(async () => await ({expresion}))()', 'awaitPromise': True, 'returnByValue': True},
            timeout=timeout)
        if res.get('exceptionDetails'):
            self.fail(f'JavaScript falló: {json.dumps(res["exceptionDetails"], default=str)[:600]}')
        return res['result'].get('value')

    def _abrir(self, browser):
        browser.navigate_to(self.base_url() + '/odoo/sofia', wait_stop=True)
        self.assertTrue(browser._wait_ready('odoo.isReady'), 'Sofía no terminó de cargar')
        self._js(browser, """(async () => {
            for (let i = 0; i < 150 && !document.querySelector('.o_sofia_tarjeta'); i++) {
                await new Promise((ok) => setTimeout(ok, 100));
            }
            await new Promise((ok) => setTimeout(ok, 500));
            return true;
        })()""", timeout=90)

    MEDIR = """(() => {
        const p = document.querySelector('.o_action.o_sofia');
        const f = document.querySelector('.o_sofia_filtros').getBoundingClientRect();
        const caja = p.getBoundingClientRect();
        return {scroll: p.scrollTop, alto: p.scrollHeight, visible: p.clientHeight, ancho: p.scrollWidth,
                anchoVisible: p.clientWidth, paginaAncha: document.documentElement.scrollWidth > innerWidth,
                desborde: getComputedStyle(p).overflowY, filtrosArriba: f.top - caja.top, filtrosAbajo: f.bottom,
                arriba: caja.top};
    })()"""

    def test_baja_con_la_rueda_en_la_computadora(self):
        with self._chrome(1366, 768, 'ger_pantalla') as browser:
            self._abrir(browser)
            antes = self._js(browser, self.MEDIR)
            self.assertIn(antes['desborde'], ('auto', 'scroll'), 'Sofía tiene que bajar con scroll')
            self.assertGreater(antes['alto'], antes['visible'] + 100, 'la prueba necesita una pantalla más alta')
            for _ in range(4):
                browser._websocket_request('Input.dispatchMouseEvent', params={
                    'type': 'mouseWheel', 'x': 800, 'y': 600, 'deltaX': 0, 'deltaY': 400})
            self._js(browser, 'new Promise((ok) => setTimeout(ok, 600))')
            despues = self._js(browser, self.MEDIR)
            self.assertGreater(despues['scroll'], antes['scroll'] + 300, f'la rueda no baja la pantalla: {despues}')
            # Los filtros (al lado) se quedan a la vista mientras se baja.
            self.assertTrue(0 <= despues['filtrosArriba'] <= 40, f'los filtros se fueron: {despues}')

    def test_baja_con_el_dedo_en_el_celular(self):
        with self._chrome(390, 844, 'ana_pantalla', tactil=True) as browser:
            self._abrir(browser)
            antes = self._js(browser, self.MEDIR)
            self.assertIn(antes['desborde'], ('auto', 'scroll'), 'Sofía tiene que bajar con el dedo')
            self.assertFalse(antes['paginaAncha'], 'en el celular la página no debe correrse de lado')
            self.assertLessEqual(antes['ancho'], antes['anchoVisible'], 'nada se sale por el costado')
            # El dedo: tocar, arrastrar hacia arriba y soltar (Input.synthesizeScrollGesture no mueve nada en Chrome
            # sin pantalla; los toques sí, y con overflow hidden no bajan: la prueba distingue el bug).
            toque = lambda tipo, puntos: browser._websocket_request(   # noqa: E731
                'Input.dispatchTouchEvent', params={'type': tipo, 'touchPoints': puntos})
            toque('touchStart', [{'x': 195, 'y': 700}])
            for paso in range(1, 21):
                toque('touchMove', [{'x': 195, 'y': 700 - paso * 25}])
            toque('touchEnd', [])
            self._js(browser, 'new Promise((ok) => setTimeout(ok, 600))')
            despues = self._js(browser, self.MEDIR)
            self.assertGreater(despues['scroll'], antes['scroll'] + 200, f'el dedo no baja la pantalla: {despues}')
            # La tira de filtros se queda pegada arriba.
            self.assertLessEqual(abs(despues['filtrosArriba']), 2, f'la tira de filtros se fue: {despues}')

    # ------------------------------------------------------------------ Los botones con el puntero encima

    def test_los_botones_blancos_se_leen_con_el_puntero_encima(self):
        """La dueña (2026-11-07): «cuando paso el puntero se pone todo en blanco… así con todos los botones de Sofía,
        excepto los que tienen fondo azul». El estilo fijaba el fondo blanco y Bootstrap ponía el texto blanco al pasar
        el puntero. Con un movimiento de ratón de verdad (protocolo de Chrome), cada botón blanco de una tarjeta tiene
        que seguir leyéndose: azul sobre blanco en reposo, blanco sobre azul con el puntero encima."""
        with self._chrome(1366, 768, 'ana_pantalla') as browser:
            self._abrir(browser)
            botones = self._js(browser, """(() => {
                const todos = [...document.querySelectorAll('.o_sofia_botones .btn-outline-primary')]
                    .filter((b) => b.offsetParent);
                todos.forEach((b, i) => b.setAttribute('data-prueba-hover', String(i)));
                return todos.length;
            })()""")
            self.assertGreater(botones, 0, 'la prueba necesita al menos un botón blanco en una tarjeta')
            for i in range(min(botones, 6)):
                caja = self._js(browser, f"""(() => {{
                    const b = document.querySelector('[data-prueba-hover="{i}"]');
                    b.scrollIntoView({{block: 'center'}});
                    const r = b.getBoundingClientRect();
                    const s = getComputedStyle(b);
                    return {{x: r.left + r.width / 2, y: r.top + r.height / 2, texto: b.textContent.trim(),
                             color: s.color, fondo: s.backgroundColor}};
                }})()""")
                self.assertEqual((caja['color'], caja['fondo']), (AZUL, 'rgb(255, 255, 255)'),
                                 f'«{caja["texto"]}» en reposo: azul sobre blanco')
                browser._websocket_request('Input.dispatchMouseEvent', params={
                    'type': 'mouseMoved', 'x': caja['x'], 'y': caja['y']})
                self._js(browser, 'new Promise((ok) => setTimeout(ok, 300))')
                encima = self._js(browser, f"""(() => {{
                    const b = document.querySelector('[data-prueba-hover="{i}"]');
                    const s = getComputedStyle(b);
                    return {{hover: b.matches(':hover'), color: s.color, fondo: s.backgroundColor}};
                }})()""")
                self.assertTrue(encima['hover'], f'el puntero no quedó sobre «{caja["texto"]}»')
                self.assertNotEqual(encima['color'], encima['fondo'],
                                    f'«{caja["texto"]}» se borra con el puntero encima: {encima}')
                self.assertEqual((encima['color'], encima['fondo']), ('rgb(255, 255, 255)', AZUL),
                                 f'«{caja["texto"]}» con el puntero encima: blanco sobre azul')
                browser._websocket_request('Input.dispatchMouseEvent', params={'type': 'mouseMoved', 'x': 2, 'y': 2})
