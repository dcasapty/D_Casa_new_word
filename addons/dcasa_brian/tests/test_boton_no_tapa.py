"""El botón flotante de Brian no tapa nada en las pantallas propias (2026-11-06).

En Conversaciones, en computadora, el botón azul de abajo a la derecha tapaba «Enviar» y «Nota interna». Se comprueba
por geometría, en el navegador y en dos tamaños de computadora: el rectángulo del botón no se cruza con el de ningún
botón, enlace o campo de la pantalla (lo que se VE de cada uno: recortado por su contenedor con scroll).

* Conversaciones: con la conversación abierta, y también con la ficha del cliente abierta (arriba y abajo de su scroll).
* Sofía, Camila y Envíos: bajan con scroll; abajo del todo, nada queda debajo del botón (lo último siempre sube por
  encima de él).
* Y Brian no se esconde: el botón sigue visible, redondo y dentro de la ventana.

Las pantallas de módulos que ``dcasa_brian`` no exige se saltan si no están instaladas (en el CI se instala todo).
"""
from datetime import timedelta

from odoo import fields
from odoo.tests import HttpCase, tagged

TAMANOS = ('1366x768', '1024x768')

COMUN = """
const esperar = async (fn, que, ms = 30000) => {
    const inicio = Date.now();
    while (Date.now() - inicio < ms) {
        const r = fn();
        if (r) { return r; }
        await new Promise((ok) => setTimeout(ok, 100));
    }
    throw new Error("Brian: no apareció " + que);
};
const pausa = (ms) => new Promise((ok) => setTimeout(ok, ms));
const INTERACTIVOS = "button, a[href], input:not([type=hidden]), textarea, select, [role=button], label";
// Lo que se ve de un elemento: su rectángulo recortado por cada contenedor que corta (scroll u overflow oculto).
const visible = (el) => {
    const r = el.getBoundingClientRect();
    let caja = { left: r.left, top: r.top, right: r.right, bottom: r.bottom };
    for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
        const o = getComputedStyle(p);
        if (/(auto|scroll|hidden|clip)/.test(o.overflowX + o.overflowY)) {
            const q = p.getBoundingClientRect();
            caja = { left: Math.max(caja.left, q.left), top: Math.max(caja.top, q.top),
                     right: Math.min(caja.right, q.right), bottom: Math.min(caja.bottom, q.bottom) };
        }
    }
    return caja;
};
const boton = () => {
    const fab = document.querySelector(".o_brian_lanzador");
    if (!fab) { throw new Error("Brian: no está el botón flotante"); }
    const estilo = getComputedStyle(fab);
    const f = fab.getBoundingClientRect();
    if (estilo.display === "none" || estilo.visibility === "hidden" || +estilo.opacity === 0 || f.width < 40
        || f.left < 0 || f.top < 0 || f.right > innerWidth || f.bottom > innerHeight) {
        throw new Error("Brian: el botón flotante tiene que seguir a la vista");
    }
    return f;
};
const revisar = (donde) => {
    const f = boton();
    const tocados = [];
    for (const el of document.querySelectorAll(".o_action_manager :is(" + INTERACTIVOS + ")")) {
        const estilo = getComputedStyle(el);
        if (estilo.display === "none" || estilo.visibility === "hidden") { continue; }
        const r = visible(el);
        if (r.right - r.left > 0 && r.bottom - r.top > 0
            && r.left < f.right && r.right > f.left && r.top < f.bottom && r.bottom > f.top) {
            const nombre = el.textContent || el.getAttribute("aria-label") || el.className || el.tagName;
            tocados.push(nombre.trim().slice(0, 40) + " "
                + JSON.stringify([r.left, r.top, r.right, r.bottom].map(Math.round)));
        }
    }
    if (tocados.length) {
        const caja = JSON.stringify([f.left, f.top, f.right, f.bottom].map(Math.round));
        throw new Error("Brian: en " + donde + " el botón " + caja + " tapa: " + tocados.join(" | "));
    }
};
const alFondo = async () => {
    for (const el of document.querySelectorAll(".o_action_manager, .o_action_manager *")) {
        if (el.scrollHeight > el.clientHeight + 2 && /(auto|scroll)/.test(getComputedStyle(el).overflowY)) {
            el.scrollTop = el.scrollHeight;
        }
    }
    await pausa(300);
};
"""


@tagged('post_install', '-at_install')
class TestBotonNoTapa(HttpCase):

    def _instalado(self, modulo):
        return self.env['ir.module.module']._get(modulo).state == 'installed'

    def _correr(self, url, codigo, tamano):
        self.browser_size = tamano
        self.browser_js(url, COMUN + '(async () => {\n' + codigo + '\nconsole.log("test successful");\n})()'
                        '.catch((e) => console.error(e.message || e));', ready='odoo.isReady', login='admin',
                        timeout=120)

    def _conversacion(self):
        admin = self.env.ref('base.user_admin')
        ahora = fields.Datetime.now()
        cliente = self.env['res.partner'].create({'name': 'Cliente Geometría Brian', 'phone': '+507 6000-9911'})
        conversacion = self.env['dcasa.conversacion'].sudo().create({
            'canal': 'whatsapp_qr', 'id_externo': '50760009911', 'partner_id': cliente.id, 'estado': 'humano',
            'ultimo_mensaje_cliente': ahora, 'ultimo_mensaje_autor': 'cliente', 'ultima_actividad': ahora,
            'asignada_a': admin.id})
        for i, (autor, texto) in enumerate((('cliente', 'Hola, ¿tienen el juego de sala en L?'),
                                            ('bot', '¡Hola! Sí, lo tenemos. ¿Para qué zona sería la entrega?'),
                                            ('cliente', 'Para Vista Alegre. ¿Cuánto cuesta el envío?'))):
            self.env['dcasa.mensaje'].sudo().create({
                'conversacion_id': conversacion.id, 'id_mensaje': f'geometria.{i}', 'tipo': 'mensaje',
                'direccion': 'entrante' if autor == 'cliente' else 'saliente', 'autor': autor, 'texto': texto,
                'estado_envio': 'recibido' if autor == 'cliente' else 'enviado',
                'ts': ahora - timedelta(minutes=30 - i)})
        return conversacion

    def test_conversaciones_enviar_y_la_ficha_quedan_libres(self):
        if not self._instalado('dcasa_conversaciones'):
            self.skipTest('dcasa_conversaciones no está instalado')
        self._conversacion()
        codigo = """
const fila = await esperar(() => [...document.querySelectorAll(".o_dcj_filas li")]
    .find((li) => /Cliente Geometría Brian/.test(li.textContent)), "la conversación en la lista");
(fila.querySelector("button, a, [role=button]") || fila.firstElementChild).click();
const enviar = await esperar(() => document.querySelector(".o_dcj_caja .o_dcj_enviar"), "el botón Enviar");
await pausa(500);
revisar("Conversaciones");
const e = enviar.getBoundingClientRect(), f = boton();
if (e.right > f.left) { throw new Error("Brian: «Enviar» debe quedar a la izquierda del botón"); }
// La ficha del cliente, a la derecha: arriba y abajo de su scroll.
[...document.querySelectorAll(".o_dcj button")].find((b) => /Cliente/.test(b.textContent)).click();
await esperar(() => document.querySelector(".o_dcj_ficha_abierta .o_dcj_ficha_cuerpo .o_dcj_tarjeta"), "la ficha");
await pausa(500);
revisar("la ficha del cliente");
await alFondo();
revisar("la ficha del cliente, abajo");
"""
        for tamano in TAMANOS:
            with self.subTest(tamano=tamano):
                self._correr('/odoo/action-dcasa_conversaciones.accion_conversaciones', codigo, tamano)

    def test_sofia_camila_y_envios_terminan_libres(self):
        pantallas = []
        if self._instalado('dcasa_sofia'):
            conversacion = self._conversacion() if self._instalado('dcasa_conversaciones') else None
            admin = self.env.ref('base.user_admin')
            for i in range(8):   # que baje con scroll
                self.env['dcasa.sofia.propuesta'].sudo().create({
                    'clave': f'geometria:{i}', 'tipo': 'contestar', 'prioridad': 3, 'usuario_id': admin.id,
                    'conversacion_id': conversacion.id if conversacion else False,
                    'partner_id': conversacion.partner_id.id if conversacion else False,
                    'titulo': f'Contéstale: espera respuesta ({i})', 'motivo': 'Te escribió hoy y espera respuesta.'})
            pantallas.append(('Sofía', '/odoo/sofia', '.o_sofia .o_sofia_tarjeta'))
        if self._instalado('dcasa_camila'):
            pantallas.append(('Camila', '/odoo/camila', '.o_camila button'))
        if self._instalado('dcasa_envios'):
            pantallas.append(('Envíos', '/odoo/envios', '.o_dcasa_envios .o_de_cuerpo'))
        if not pantallas:
            self.skipTest('Sofía, Camila y Envíos no están instalados')
        for nombre, url, espera in pantallas:
            codigo = f"""
await esperar(() => document.querySelector({espera!r}), "la pantalla de {nombre}");
await pausa(800);
await alFondo();
revisar("{nombre}, abajo");
"""
            for tamano in TAMANOS:
                with self.subTest(pantalla=nombre, tamano=tamano):
                    self._correr(url, codigo, tamano)

    def test_la_regla_vive_en_el_panel_de_brian(self):
        """La reserva es del botón: solo mientras se ve (computadora y panel cerrado) y sin tocar los otros módulos."""
        from odoo.tools.misc import file_path
        with open(file_path('dcasa_brian/static/src/scss/brian_panel.scss'), encoding='utf-8') as archivo:
            scss = archivo.read()
        self.assertIn('body:has(.o_brian_lanzador:not(.o_brian_oculto))', scss)
        self.assertIn('.o_dcj:not(.o_dcj_ficha_abierta) .o_dcj_caja { padding-right: $brian-hueco-ancho; }', scss)
        for pantalla in ('o_sofia', 'o_camila', 'o_dcasa_envios'):
            self.assertIn(pantalla, scss)
