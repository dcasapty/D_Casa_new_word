"""La pantalla «Conversaciones» en un navegador de verdad (Chromium): abrir la lista, abrir un hilo, tomar y devolver,
enviar texto, adjuntar un archivo, buscar y enviar una foto del catálogo, la vista de celular (390 px) y las otras
pantallas. Mismo patrón que las pantallas OWL de Brian y de la conciliación (browser_js con código inline)."""
import base64
import io
import itertools
import os
from datetime import timedelta
from unittest.mock import patch

from PIL import Image

from odoo import Command, fields
from odoo.exceptions import AccessError
from odoo.tests import HttpCase, new_test_user, tagged

from .common import COSTOS, SALUD, TOKEN_ODOO, TOKEN_WORKER, URL_WORKER, respuesta_http

ACCION = '/odoo/action-dcasa_conversaciones.accion_conversaciones'
ACCION_RESUMEN = '/odoo/action-dcasa_conversaciones.accion_resumen'
ACCION_COSTOS = '/odoo/action-dcasa_conversaciones.accion_costos'
ACCION_CONEXIONES = '/odoo/action-dcasa_conversaciones.accion_conexiones'
_contador = itertools.count(1)
VENDEDORA = 'juan_ui_vendedora'
GERENTE = 'juan_ui_gerente'

# Ayudas para el código que corre en el navegador. Igual que en las pruebas de Brian: esperar a que algo pase.
ESPERAR = """
const esperar = async (fn, que, ms = 20000) => {
    const inicio = Date.now();
    while (Date.now() - inicio < ms) {
        const r = fn();
        if (r) { return r; }
        await new Promise((ok) => setTimeout(ok, 100));
    }
    throw new Error("Conversaciones: no apareció " + que);
};
const aqui = (selector, texto) => [...document.querySelectorAll(selector)].find((e) => !texto || e.textContent.includes(texto));
const pausa = (ms = 80) => new Promise((ok) => setTimeout(ok, ms));
const escribir = async (el, valor) => {
    el.focus();
    el.value = valor;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    await pausa(60);
};
const escape = () => (document.activeElement || document.body).dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
const tecla = (el, key, extra = {}) => el.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true, ...extra }));
const archivo = (nombre, tipo, bytes) => new File([new Uint8Array(bytes)], nombre, { type: tipo });
const PDF = [37, 80, 68, 70, 45, 49, 46, 52, 10, 37, 37, 69, 79, 70];
const PNG = Uint8Array.from(atob("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="), (c) => c.charCodeAt(0));
const abrirConversacion = async (nombre) => {
    const fila = await esperar(() => aqui(".o_dcj_fila", nombre), "la conversación de " + nombre);
    fila.click();
    await esperar(() => document.querySelector(".o_dcj_hilo_cuerpo .o_dcj_burbuja"), "las burbujas del hilo");
};
"""


def png(color=(19, 64, 177), tamano=(64, 48)):
    salida = io.BytesIO()
    Image.new('RGB', tamano, color).save(salida, 'PNG')
    return salida.getvalue()


def foto(color=(19, 64, 177), tamano=(1600, 1200)):
    return base64.b64encode(png(color, tamano))


class PanelUiCase(HttpCase):
    """Base de las pruebas con navegador: usuarios con clave, conversaciones de ejemplo y un Worker falso."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.vendedora = new_test_user(cls.env, login=VENDEDORA, name='Ana Vendedora',
                                      groups='base.group_user,sales_team.group_sale_salesman')
        cls.gerente = new_test_user(cls.env, login=GERENTE, name='Gema Gerente',
                                    groups='base.group_user,sales_team.group_sale_manager')
        cls.ajustes = cls.env['dcasa.juan.ajustes'].obtener()
        cls.etiqueta = cls.env['dcasa.conversacion.etiqueta'].create({'name': 'Zzpidió precio', 'color': 5})
        cls.ahora = fields.Datetime.now()

    def setUp(self):
        super().setUp()
        entorno = patch.dict(os.environ, {'JUAN_URL': URL_WORKER, 'JUAN_WORKER_TOKEN': TOKEN_WORKER,
                                          'JUAN_ODOO_TOKEN': TOKEN_ODOO, 'DCASA_PIN_PEPPER': 'pimienta-de-prueba'})
        entorno.start()
        self.addCleanup(entorno.stop)
        self.llamadas = []
        self.rutas = {}
        parche = patch('requests.request', side_effect=self._worker)
        parche.start()
        self.addCleanup(parche.stop)

    def _worker(self, metodo, url, **kw):
        """El Worker de mentira: contesta bien a todo (o lo que diga ``self.rutas``) y anota lo que Odoo le mandó."""
        ruta = url.removeprefix(URL_WORKER)
        self.llamadas.append((metodo, ruta, kw.get('json')))
        if (metodo, ruta) in self.rutas:
            cuerpo, estado = self.rutas[metodo, ruta]
            return respuesta_http(cuerpo, estado)
        if ruta == '/odoo/enviar':
            return respuesta_http({'ok': True, 'id_mensaje': f'wamid.ui.{next(_contador)}'})
        if ruta == '/odoo/sugerir':
            return respuesta_http({'ok': True, 'texto': 'Claro, con gusto te ayudo con la cama queen.', 'avisos': []})
        return respuesta_http({'ok': True})

    def al_worker(self, ruta, metodo='POST'):
        return [j for m, r, j in self.llamadas if r == ruta and m == metodo]

    # --- Datos ----------------------------------------------------------------------------------

    def registrar(self, texto, id_externo, autor='cliente', canal='whatsapp_qr', minutos=0, nombre=None,
                  adjuntos=()):
        conv, mensaje, _creado = self.env['dcasa.conversacion']._registrar_mensaje({
            'canal': canal, 'id_externo': id_externo, 'id_mensaje': f'wamid.ui.{next(_contador)}',
            'direccion': 'entrante' if autor == 'cliente' else 'saliente', 'autor': autor, 'texto': texto,
            'ts': self.ahora - timedelta(minutes=minutos), 'nombre': nombre, 'celular': None, 'adjuntos': [],
        })
        for nombre_adjunto, contenido, mime in adjuntos:
            adjunto = self.env['ir.attachment'].create({
                'name': nombre_adjunto, 'raw': contenido, 'mimetype': mime, 'res_model': 'dcasa.mensaje',
                'res_id': mensaje.id})
            mensaje.with_context(dcasa_mensaje_sistema=True).sudo().adjunto_ids = [Command.link(adjunto.id)]
        return conv

    def datos_de_ejemplo(self):
        self.karen = self.registrar('Hola, ¿tienen camas queen?', '50761000001', minutos=30, nombre='Karen Pérez')
        self.registrar('Sí, tenemos varias. ¿Para cuántas personas?', '50761000001', autor='bot', minutos=29)
        self.registrar('Para dos. ¿Cuánto cuesta la gris?', '50761000001', minutos=5)
        self.registrar('Mira cómo se ve mi cuarto', '50761000001', minutos=4,
                       adjuntos=[('cuarto.png', png(), 'image/png')])
        self.luis = self.registrar('Buenas tardes', '777001', canal='telegram', minutos=300, nombre='Luis Mora')
        self.luis.sudo().estado = 'cerrada'
        self.marta = self.registrar('Quiero apartar un sofá', '50761000003', minutos=60, nombre='Marta Ríos')
        self.marta.with_user(self.vendedora).action_atender()
        self.marta.sudo().etiqueta_ids = self.etiqueta

    def producto_de_ejemplo(self):
        impuesto = self.env['brian.herramientas']._b_itbms_venta()
        categoria = self.env['product.public.category'].create({'name': 'Zzdormitorio'})
        cama = self.env['product.template'].create({
            'name': 'Zzcama Roble Queen', 'default_code': 'ZZ-CAMA', 'list_price': 349.99, 'standard_price': 123.45,
            'type': 'consu', 'is_storable': True, 'sale_ok': True, 'is_published': True,
            'taxes_id': [Command.set(impuesto.ids)], 'public_categ_ids': [Command.set(categoria.ids)],
            'dcasa_medidas': 'Ancho × Largo: 160 × 200 cm', 'image_1920': foto(),
            'product_template_image_ids': [Command.create({'name': 'Lado', 'image_1920': foto((200, 30, 30))}),
                                           Command.create({'name': 'Detalle', 'image_1920': foto((30, 200, 30))})]})
        almacen = self.env['stock.warehouse'].search([], limit=1)
        self.env['stock.quant']._update_available_quantity(cama.product_variant_id, almacen.lot_stock_id, 7777)
        return cama

    def navegador(self, codigo, url=ACCION, login=VENDEDORA, timeout=120):
        self.browser_js(url, ESPERAR + codigo, ready='odoo.isReady', login=login, timeout=timeout)


@tagged('post_install', '-at_install')
class TestPanelEnElNavegador(PanelUiCase):

    def test_la_lista_muestra_las_conversaciones_con_su_estado(self):
        self.datos_de_ejemplo()
        self.navegador("""
(async () => {
    await esperar(() => document.querySelectorAll(".o_dcj_fila").length >= 3, "las conversaciones en la lista");
    const nombres = [...document.querySelectorAll(".o_dcj_nombre")].map((e) => e.textContent.trim());
    for (const n of ["Karen Pérez", "Luis Mora", "Marta Ríos"]) {
        if (!nombres.includes(n)) { throw new Error("falta " + n + " en la lista: " + nombres.join("|")); }
    }
    const karen = aqui(".o_dcj_fila", "Karen");
    if (!karen.querySelector(".o_dcj_no_leidos") || !/3/.test(karen.querySelector(".o_dcj_no_leidos").textContent)) {
        throw new Error("Karen debe tener 3 mensajes sin leer");
    }
    if (!karen.querySelector(".o_dcj_punto_verde")) { throw new Error("el asistente atiende a Karen: punto verde"); }
    if (!aqui(".o_dcj_fila", "Luis").textContent.includes("Cerrada")) { throw new Error("Luis está cerrada"); }
    const marta = aqui(".o_dcj_fila", "Marta");
    if (!marta.textContent.includes("Ana Vendedora") || !marta.textContent.includes("Zzpidió precio")) {
        throw new Error("Marta: la atiende Ana y tiene su etiqueta: " + marta.textContent);
    }
    if (!marta.textContent.includes("Necesita atención")) { throw new Error("Marta espera respuesta: necesita atención"); }
    if (marta.querySelector(".o_dcj_punto_verde")) { throw new Error("a Marta no la atiende el asistente"); }
    if (!karen.querySelector(".o_dcj_canal .fa-whatsapp")) { throw new Error("ícono del canal"); }
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
""")

    def test_abrir_un_hilo_burbujas_fotos_y_visor(self):
        self.datos_de_ejemplo()
        self.navegador("""
(async () => {
    await abrirConversacion("Karen");
    const clases = [...document.querySelectorAll(".o_dcj_hilo_cuerpo .o_dcj_burbuja")].map((e) =>
        [...e.classList].find((c) => /^o_dcj_burbuja_(cliente|bot|vendedora|nota)$/.test(c)));
    if (clases.join(",") !== "o_dcj_burbuja_cliente,o_dcj_burbuja_bot,o_dcj_burbuja_cliente,o_dcj_burbuja_cliente") {
        throw new Error("autores de las burbujas: " + clases.join(","));
    }
    if (!document.querySelector(".o_dcj_dia")) { throw new Error("falta el separador de día"); }
    const hilo = aqui(".o_dcj_hilo_cabecera");
    if (!hilo.textContent.includes("Karen Pérez")) { throw new Error("cabecera del hilo"); }
    // La foto: miniatura, clic para ampliar, Esc para cerrar.
    const boton = await esperar(() => document.querySelector(".o_dcj_foto_boton"), "la miniatura de la foto");
    if (!boton.querySelector("img").getAttribute("src").includes("/web/image/")) { throw new Error("la miniatura usa /web/image"); }
    boton.click();
    const visor = await esperar(() => document.querySelector(".o_dcj_visor"), "el visor");
    if (document.activeElement !== visor.querySelector("button[aria-label^='Cerrar']")) { throw new Error("el foco entra al visor"); }
    escape();
    await esperar(() => !document.querySelector(".o_dcj_visor"), "el visor cerrado con Esc");
    // Al abrirla se marcó como leída: el contador se va.
    await esperar(() => !aqui(".o_dcj_fila", "Karen").querySelector(".o_dcj_no_leidos"), "el contador de no leídos en cero");
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
""")
        lectura = self.env['dcasa.conversacion.lectura'].sudo().search([
            ('conversacion_id', '=', self.karen.id), ('usuario_id', '=', self.vendedora.id)])
        self.assertTrue(lectura, 'Abrir el hilo lo marca como leído para quien lo abrió')

    def test_atender_y_devolver_con_nota(self):
        self.datos_de_ejemplo()
        self.navegador("""
(async () => {
    await abrirConversacion("Karen");
    const barra = () => document.querySelector(".o_dcj_barra");
    if (!barra().textContent.includes("Atiende el asistente")) { throw new Error("al abrir atiende el asistente"); }
    barra().querySelector("button").click();
    await esperar(() => barra().textContent.includes("Atiendes tú"), "la barra «Atiendes tú»");
    const texto = barra().querySelector(".o_dcj_barra_texto").textContent;
    if (!/vuelve a las \\d{1,2}:\\d{2}/.test(texto) || !/\\(en /.test(texto)) { throw new Error("falta el vencimiento visible: " + texto); }
    await esperar(() => aqui(".o_dcj_aviso_sistema", "tomó la conversación"), "el aviso del sistema en el hilo");
    // Devolver pide una nota opcional.
    aqui(".o_dcj_barra button", "Devolver").click();
    const nota = await esperar(() => document.querySelector("#o_dcj_nota_bot"), "la nota para el asistente");
    await escribir(nota, "ya quedó la visita del sábado");
    aqui(".o_dcj_devolver button", "Devolver al asistente").click();
    await esperar(() => barra().textContent.includes("Atiende el asistente") && !document.querySelector(".o_dcj_devolver"), "devuelta al asistente");
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
""")
        self.assertEqual((self.karen.estado, self.karen.nota_para_el_bot), ('bot', 'ya quedó la visita del sábado'))
        de_karen = [j for j in self.al_worker('/odoo/estado') if j['id_externo'] == '50761000001']
        self.assertEqual([j['estado'] for j in de_karen], ['humano', 'bot'])
        self.assertEqual(de_karen[1]['nota_para_el_bot'], 'ya quedó la visita del sábado')

    def test_enviar_un_texto_con_enter(self):
        self.datos_de_ejemplo()
        self.navegador("""
(async () => {
    await abrirConversacion("Karen");
    const caja = document.querySelector("#o_dcj_texto");
    const enviar = document.querySelector(".o_dcj_enviar");
    if (!enviar.disabled) { throw new Error("Enviar está desactivado con la caja vacía"); }
    await escribir(caja, "Claro que sí, Karen. Te cuento.");
    if (enviar.disabled) { throw new Error("Enviar se activa al escribir"); }
    tecla(caja, "Enter");
    const burbuja = await esperar(() => aqui(".o_dcj_burbuja_vendedora", "Claro que sí, Karen"), "mi burbuja");
    if (!burbuja.textContent.includes("Ana Vendedora")) { throw new Error("la burbuja lleva mi nombre"); }
    await esperar(() => caja.value === "", "la caja vacía después de enviar");
    await esperar(() => document.querySelector(".o_dcj_barra").textContent.includes("Atiendes tú"), "ahora la atiendo yo");
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
""")
        (envio,) = self.al_worker('/odoo/enviar')
        self.assertEqual((envio['texto'], envio['canal'], envio['id_externo']),
                         ('Claro que sí, Karen. Te cuento.', 'whatsapp_qr', '50761000001'))
        self.assertEqual(self.karen.estado, 'humano')

    def test_mayus_enter_salta_de_linea_y_no_envia(self):
        self.datos_de_ejemplo()
        self.navegador("""
(async () => {
    await abrirConversacion("Karen");
    const caja = document.querySelector("#o_dcj_texto");
    await escribir(caja, "Primera línea");
    tecla(caja, "Enter", { shiftKey: true });
    await pausa(300);
    if (aqui(".o_dcj_burbuja_vendedora")) { throw new Error("Mayús + Enter no envía"); }
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
""")
        self.assertFalse(self.al_worker('/odoo/enviar'))

    def test_adjuntar_con_el_boton_y_arrastrando_con_vista_previa(self):
        self.datos_de_ejemplo()
        self.navegador("""
(async () => {
    await abrirConversacion("Karen");
    // 1. Con el botón (el selector de archivos).
    const entrada = document.querySelector("input[type=file]");
    let lista = new DataTransfer();
    lista.items.add(archivo("lista.pdf", "application/pdf", PDF));
    entrada.files = lista.files;
    entrada.dispatchEvent(new Event("change", { bubbles: true }));
    const pdf = await esperar(() => document.querySelector(".o_dcj_previa_listo"), "el PDF subido");
    if (!pdf.textContent.includes("lista.pdf") || !pdf.querySelector(".fa-file-pdf-o")) { throw new Error("vista previa del PDF"); }
    // 2. Arrastrando una foto sobre el hilo: aparece la zona para soltar y luego la vista previa con miniatura.
    const hilo = document.querySelector(".o_dcj_hilo");
    lista = new DataTransfer();
    lista.items.add(archivo("cuarto.png", "image/png", PNG));
    hilo.dispatchEvent(new DragEvent("dragenter", { dataTransfer: lista, bubbles: true, cancelable: true }));
    await esperar(() => document.querySelector(".o_dcj_soltar"), "la zona para soltar");
    hilo.dispatchEvent(new DragEvent("drop", { dataTransfer: lista, bubbles: true, cancelable: true }));
    await esperar(() => !document.querySelector(".o_dcj_soltar"), "la zona para soltar cerrada");
    await esperar(() => document.querySelectorAll(".o_dcj_previa_listo").length === 2, "las dos vistas previas");
    if (!aqui(".o_dcj_previa", "cuarto.png").querySelector("img")) { throw new Error("la foto tiene miniatura"); }
    // 3. Algo que no se puede mandar se rechaza con un aviso, sin romper nada.
    lista = new DataTransfer();
    lista.items.add(archivo("virus.exe", "application/x-msdownload", [77, 90, 0, 0]));
    entrada.files = lista.files;
    entrada.dispatchEvent(new Event("change", { bubbles: true }));
    await esperar(() => document.querySelector(".o_notification"), "el aviso de archivo rechazado");
    if (document.querySelectorAll(".o_dcj_previa").length !== 2) { throw new Error("el .exe no debe quedar en la caja"); }
    // 4. Quitar una vista previa y enviar con texto.
    aqui(".o_dcj_previa", "lista.pdf").querySelector("button").click();
    await esperar(() => document.querySelectorAll(".o_dcj_previa").length === 1, "el PDF quitado");
    await escribir(document.querySelector("#o_dcj_texto"), "Así se ve en tu cuarto");
    document.querySelector(".o_dcj_enviar").click();
    const burbuja = await esperar(() => aqui(".o_dcj_burbuja_vendedora", "Así se ve en tu cuarto"), "mi burbuja con la foto");
    await esperar(() => burbuja.querySelector(".o_dcj_foto_boton img"), "la foto dentro de mi burbuja");
    await esperar(() => !document.querySelector(".o_dcj_previa"), "las vistas previas vacías");
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
""")
        (envio,) = self.al_worker('/odoo/enviar')
        (adjunto,) = envio['adjuntos']
        self.assertEqual((adjunto['tipo'], adjunto['nombre'], adjunto['mime']), ('imagen', 'cuarto.png', 'image/png'))
        self.assertRegex(adjunto['url'], r'/dcasa/adjunto/\d+/\d+/[0-9a-f]{64}/cuarto\.png$')
        # Lo que se quitó de la caja no se queda guardado en el servidor.
        self.assertFalse(self.env['ir.attachment'].sudo().search([('name', '=', 'lista.pdf')]))

    def test_enviar_un_documento(self):
        self.datos_de_ejemplo()
        self.navegador("""
(async () => {
    await abrirConversacion("Karen");
    const entrada = document.querySelector("input[type=file]");
    const lista = new DataTransfer();
    lista.items.add(archivo("cotizacion.pdf", "application/pdf", PDF));
    entrada.files = lista.files;
    entrada.dispatchEvent(new Event("change", { bubbles: true }));
    await esperar(() => document.querySelector(".o_dcj_previa_listo"), "el PDF subido");
    document.querySelector(".o_dcj_enviar").click();
    const enlace = await esperar(() => document.querySelector(".o_dcj_burbuja_vendedora .o_dcj_documento a"), "el documento en mi burbuja");
    if (!enlace.textContent.includes("cotizacion.pdf") || !enlace.getAttribute("href").includes("/web/content/")) {
        throw new Error("enlace de descarga del documento");
    }
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
""")
        (envio,) = self.al_worker('/odoo/enviar')
        self.assertEqual(envio['adjuntos'][0]['tipo'], 'documento')
        self.assertNotIn('texto', envio)

    def test_notas_internas_con_otro_color_y_sin_salir_por_el_canal(self):
        self.datos_de_ejemplo()
        self.navegador("""
(async () => {
    await abrirConversacion("Karen");
    aqui(".o_dcj_modo button", "Nota interna").click();
    const caja = document.querySelector("#o_dcj_texto");
    await esperar(() => caja.placeholder.includes("el cliente no la ve"), "el modo nota");
    await escribir(caja, "Pide descuento: preguntar a Gerencia");
    document.querySelector(".o_dcj_enviar").click();
    const nota = await esperar(() => aqui(".o_dcj_burbuja_nota", "Pide descuento"), "la nota en el hilo");
    if (!nota.textContent.includes("Nota interna") || !nota.textContent.includes("El cliente no la ve")) { throw new Error("rótulo de la nota"); }
    if (getComputedStyle(nota).borderTopStyle !== "dashed") { throw new Error("la nota tiene borde punteado"); }
    if (document.querySelector(".o_dcj_barra").textContent.includes("Atiendes tú")) { throw new Error("una nota no toma la conversación"); }
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
""")
        self.assertFalse(self.al_worker('/odoo/enviar'), 'Una nota interna nunca sale por el canal')
        self.assertEqual(self.karen.estado, 'bot')
        self.assertTrue(self.karen.mensaje_ids.filtered(lambda m: m.tipo == 'nota'))

    def test_mencionar_con_arroba_en_una_nota_avisa_a_la_companera(self):
        self.datos_de_ejemplo()
        self.navegador("""
(async () => {
    await abrirConversacion("Karen");
    aqui(".o_dcj_modo button", "Nota interna").click();
    const caja = document.querySelector("#o_dcj_texto");
    await esperar(() => caja.placeholder.includes("@"), "el modo nota con la pista del @");
    await escribir(caja, "Revisa esto @Gem");
    await esperar(() => aqui(".o_dcj_menciones .o_dcj_rapida", "Gema Gerente"), "la lista con Gema");
    if (aqui(".o_dcj_menciones .o_dcj_rapida", "Ana Vendedora")) { throw new Error("no se ofrece a quien escribe"); }
    tecla(caja, "Enter");
    await esperar(() => caja.value.includes("@Gema Gerente "), "la mención en la caja: " + caja.value);
    const aviso = await esperar(() => document.querySelector(".o_dcj_tarea"), "el aviso de a quién se le avisa");
    if (!aviso.textContent.includes("Gema Gerente")) { throw new Error("dice a quién: " + aviso.textContent); }
    if (document.querySelector(".o_dcj_menciones")) { throw new Error("la lista se cierra al elegir"); }
    if (!document.querySelector("#o_dcj_texto") || document.activeElement !== caja) { throw new Error("el foco vuelve a la caja"); }
    document.querySelector(".o_dcj_enviar").click();
    const nota = await esperar(() => aqui(".o_dcj_burbuja_nota", "Revisa esto"), "la nota en el hilo");
    await esperar(() => nota.textContent.includes("Mencionó a Gema Gerente") || aqui(".o_dcj_burbuja_nota", "Mencionó a Gema Gerente"), "«Mencionó a» en la nota");
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
""")
        (nota,) = self.karen.mensaje_ids.filtered(lambda m: m.tipo == 'nota')
        self.assertEqual(nota.mencion_ids, self.gerente)
        self.assertFalse(self.al_worker('/odoo/enviar'), 'Una nota nunca sale por el canal')

    def test_respuestas_rapidas_con_barra(self):
        self.datos_de_ejemplo()
        self.navegador("""
(async () => {
    await abrirConversacion("Karen");
    const caja = document.querySelector("#o_dcj_texto");
    await escribir(caja, "/hor");
    const opcion = await esperar(() => aqui(".o_dcj_rapida", "/horario"), "la respuesta rápida /horario");
    if (aqui(".o_dcj_rapida", "/ubicacion")) { throw new Error("el filtro deja solo lo que empieza con /hor"); }
    tecla(caja, "Enter");
    await esperar(() => caja.value.length > 10 && !caja.value.startsWith("/"), "el texto de /horario en la caja");
    if (!caja.value.startsWith("Karen") || !caja.value.includes("p. m.")) { throw new Error("lleva el nombre del cliente y el horario: " + caja.value); }
    if (document.querySelector(".o_dcj_rapidas")) { throw new Error("el menú se cierra al elegir"); }
    // Esc cierra el menú y borra el atajo a medias.
    await escribir(caja, "/");
    await esperar(() => document.querySelectorAll(".o_dcj_rapida").length >= 3, "todas las rápidas con solo /");
    tecla(caja, "Escape");
    await esperar(() => !document.querySelector(".o_dcj_rapidas"), "el menú cerrado con Esc");
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
""")

    def test_sugerir_deja_el_borrador_en_la_caja_sin_enviar(self):
        self.datos_de_ejemplo()
        self.navegador("""
(async () => {
    await abrirConversacion("Karen");
    aqui(".o_dcj_herramienta", "Sugerir").click();
    const caja = document.querySelector("#o_dcj_texto");
    await esperar(() => caja.value.includes("Claro, con gusto te ayudo"), "el borrador en la caja");
    if (!document.querySelector(".o_dcj_sugerencia")) { throw new Error("aviso de que es un borrador"); }
    if (aqui(".o_dcj_burbuja_vendedora")) { throw new Error("Sugerir no envía nada"); }
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
""")
        self.assertFalse(self.al_worker('/odoo/enviar'))
        self.assertEqual(len(self.al_worker('/odoo/sugerir')), 1)

    def test_sugerir_sin_el_bot_conectado_lo_dice_con_claridad(self):
        self.datos_de_ejemplo()
        with patch.dict(os.environ, {'JUAN_URL': '', 'JUAN_WORKER_TOKEN': ''}):
            self.navegador("""
(async () => {
    await esperar(() => document.querySelector(".o_dcj_aviso"), "el aviso de arriba");
    if (!document.querySelector(".o_dcj_aviso").textContent.includes("Falta conectar el bot")) { throw new Error("aviso: Falta conectar el bot"); }
    await abrirConversacion("Karen");
    aqui(".o_dcj_herramienta", "Sugerir").click();
    const aviso = await esperar(() => aqui(".o_notification", "Falta conectar el bot"), "el aviso al pedir una sugerencia");
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
""")

    def test_filtros_y_busqueda(self):
        self.datos_de_ejemplo()
        self.navegador("""
(async () => {
    await esperar(() => document.querySelectorAll(".o_dcj_fila").length === 3, "las tres conversaciones");
    const filas = () => [...document.querySelectorAll(".o_dcj_fila .o_dcj_nombre")].map((e) => e.textContent.trim());
    const buscar = document.querySelector("input[type=search]");
    await escribir(buscar, "Marta");
    await esperar(() => filas().join() === "Marta Ríos", "la búsqueda por nombre");
    await escribir(buscar, "apartar un sofá");
    await esperar(() => filas().join() === "Marta Ríos", "la búsqueda por texto del mensaje");
    await escribir(buscar, "");
    await esperar(() => filas().length === 3, "la lista completa");
    // Las tres tienen mensajes del cliente sin leer; al abrir la de Karen ya no.
    (aqui(".o_dcj_fila", "Karen")).click();
    await esperar(() => document.querySelector(".o_dcj_hilo_cuerpo .o_dcj_burbuja"), "el hilo de Karen");
    await esperar(() => !aqui(".o_dcj_fila", "Karen").querySelector(".o_dcj_no_leidos"), "Karen leída");
    aqui(".o_dcj_chip", "Sin leer").click();
    await esperar(() => filas().join() === "Luis Mora,Marta Ríos" || filas().join() === "Marta Ríos,Luis Mora", "solo las sin leer");
    aqui(".o_dcj_chip", "Sin leer").click();
    aqui(".o_dcj_chip", "Mías").click();
    await esperar(() => filas().join() === "Marta Ríos", "solo las mías");
    aqui(".o_dcj_chip", "Mías").click();
    aqui(".o_dcj_chip", "Más filtros").click();
    await esperar(() => document.querySelectorAll(".o_dcj_mas_filtros select").length === 3, "los filtros extra");
    const [canal, estado, etiqueta] = document.querySelectorAll(".o_dcj_mas_filtros select");
    canal.value = "telegram"; canal.dispatchEvent(new Event("change", { bubbles: true }));
    await esperar(() => filas().join() === "Luis Mora", "el filtro de canal");
    canal.value = ""; canal.dispatchEvent(new Event("change", { bubbles: true }));
    estado.value = "humano"; estado.dispatchEvent(new Event("change", { bubbles: true }));
    await esperar(() => filas().join() === "Marta Ríos", "el filtro de estado");
    estado.value = ""; estado.dispatchEvent(new Event("change", { bubbles: true }));
    etiqueta.value = [...etiqueta.options].find((o) => o.textContent.includes("Zzpidió precio")).value;
    etiqueta.dispatchEvent(new Event("change", { bubbles: true }));
    await esperar(() => filas().join() === "Marta Ríos", "el filtro de etiqueta");
    aqui(".o_dcj_enlace", "Quitar filtros").click();
    await esperar(() => filas().length === 3, "sin filtros otra vez");
    await escribir(buscar, "zzznadaquecoincida");
    await esperar(() => aqui(".o_dcj_vacio", "No hay conversaciones con esos filtros"), "el mensaje de sin resultados");
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
""")

    def test_la_ficha_del_cliente_etiquetas_y_asignacion(self):
        self.datos_de_ejemplo()
        self.navegador("""
(async () => {
    await abrirConversacion("Karen");
    const ficha = await esperar(() => document.querySelector(".o_dcj_ficha .o_dcj_cliente h3"), "la ficha del cliente");
    if (ficha.textContent.trim() !== "Karen Pérez") { throw new Error("nombre en la ficha"); }
    const etiqueta = await esperar(() => aqui(".o_dcj_etiqueta_boton", "Zzpidió precio"), "las etiquetas de la ficha");
    etiqueta.click();
    await esperar(() => aqui(".o_dcj_etiqueta_boton", "Zzpidió precio").getAttribute("aria-pressed") === "true", "etiqueta puesta");
    await esperar(() => aqui(".o_dcj_fila", "Karen").textContent.includes("Zzpidió precio"), "la etiqueta en la lista");
    const asignar = document.querySelector("#o_dcj_asignar");
    asignar.value = [...asignar.options].find((o) => o.textContent.includes("Gema Gerente")).value;
    asignar.dispatchEvent(new Event("change", { bubbles: true }));
    await esperar(() => aqui(".o_dcj_aviso_sistema", "asignó la conversación"), "el aviso de la asignación");
    // Sin oportunidad: el botón la crea.
    aqui(".o_dcj_ficha button", "Crear oportunidad").click();
    await esperar(() => aqui(".o_dcj_ficha .o_dcj_enlace_fila", "Karen") || aqui(".o_dcj_ficha .o_dcj_enlace_fila"), "la oportunidad en la ficha");
    if (!aqui(".o_dcj_ficha", "Qué sabe el asistente de esta persona")) { throw new Error("falta «qué sabe el asistente»"); }
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
""")
        self.assertIn(self.etiqueta.id, self.karen.etiqueta_ids.ids)
        self.assertEqual(self.karen.asignada_a, self.gerente)
        self.assertTrue(self.karen.oportunidad_id)

    def test_foto_del_catalogo_buscar_y_enviar_con_su_pie(self):
        self.datos_de_ejemplo()
        self.cama = self.producto_de_ejemplo()
        self.navegador("""
(async () => {
    await abrirConversacion("Karen");
    aqui(".o_dcj_herramienta", "Foto del catálogo").click();
    const dialogo = await esperar(() => document.querySelector(".o_dcj_hoja[role=dialog]"), "el buscador de fotos");
    const buscar = dialogo.querySelector("input[type=search]");
    if (document.activeElement !== buscar) { throw new Error("el foco entra al buscador"); }
    await escribir(buscar, "zzcama");
    const producto = await esperar(() => aqui(".o_dcj_producto", "Zzcama Roble Queen"), "el producto encontrado");
    const texto = producto.textContent;
    if (!texto.includes("$349.99 + ITBMS")) { throw new Error("precio + ITBMS: " + texto); }
    if (!texto.includes("DISPONIBLE")) { throw new Error("disponibilidad como etiqueta: " + texto); }
    if (!texto.includes("160 × 200 cm") || !texto.includes("ZZ-CAMA")) { throw new Error("medidas y código: " + texto); }
    if (/7777|7,777|123\\.45/.test(dialogo.textContent)) { throw new Error("jamás la cantidad ni el costo"); }
    if (!producto.querySelector("img").getAttribute("src").startsWith("/dcasa/img/")) { throw new Error("miniatura WebP al ancho justo"); }
    aqui(".o_dcj_producto button", "Enviar foto").click();
    await esperar(() => !document.querySelector(".o_dcj_hoja"), "el buscador cerrado");
    const burbuja = await esperar(() => aqui(".o_dcj_burbuja_vendedora", "Zzcama Roble Queen"), "la foto en el hilo");
    await esperar(() => burbuja.querySelector(".o_dcj_foto_boton img"), "la imagen dentro de la burbuja");
    if (!burbuja.textContent.includes("$349.99 + ITBMS") || !burbuja.textContent.includes("Medidas: Ancho × Largo: 160 × 200 cm")) {
        throw new Error("el pie armado: " + burbuja.textContent);
    }
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
""")
        (envio,) = self.al_worker('/odoo/enviar')
        (adjunto,) = envio['adjuntos']
        self.assertEqual((adjunto['tipo'], adjunto['mime']), ('imagen', 'image/jpeg'))
        self.assertTrue(envio['texto'].startswith('Zzcama Roble Queen\n$349.99 + ITBMS\nMedidas:'))
        self.assertTrue(envio['texto'].endswith(self.cama.website_url))

    def test_foto_del_catalogo_galeria_varias_fotos(self):
        self.datos_de_ejemplo()
        self.producto_de_ejemplo()
        self.navegador("""
(async () => {
    await abrirConversacion("Karen");
    aqui(".o_dcj_herramienta", "Foto del catálogo").click();
    await escribir(await esperar(() => document.querySelector(".o_dcj_hoja input[type=search]"), "el buscador"), "ZZ-CAMA");
    await esperar(() => aqui(".o_dcj_producto", "Zzcama"), "el producto");
    aqui(".o_dcj_producto button", "Galería (3)").click();
    await esperar(() => document.querySelectorAll(".o_dcj_galeria_foto").length === 3, "las tres fotos de la galería");
    const fotos = [...document.querySelectorAll(".o_dcj_galeria_foto")];
    if (fotos.filter((f) => f.getAttribute("aria-pressed") === "true").length !== 1) { throw new Error("la principal viene elegida"); }
    fotos[1].click(); fotos[2].click();
    await esperar(() => aqui(".o_dcj_hoja_pie button", "Enviar 3 fotos"), "el botón de enviar tres fotos");
    aqui(".o_dcj_hoja_pie button", "Enviar 3 fotos").click();
    await esperar(() => !document.querySelector(".o_dcj_hoja"), "la galería cerrada");
    const burbuja = await esperar(() => aqui(".o_dcj_burbuja_vendedora", "Zzcama"), "las fotos en el hilo");
    await esperar(() => burbuja.querySelectorAll(".o_dcj_foto_boton img").length === 3, "las tres imágenes");
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
""")
        (envio,) = self.al_worker('/odoo/enviar')
        self.assertEqual(len(envio['adjuntos']), 3)

    def test_foto_del_catalogo_revisar_antes_la_deja_en_la_caja(self):
        self.datos_de_ejemplo()
        self.producto_de_ejemplo()
        self.navegador("""
(async () => {
    await abrirConversacion("Karen");
    aqui(".o_dcj_herramienta", "Foto del catálogo").click();
    await escribir(await esperar(() => document.querySelector(".o_dcj_hoja input[type=search]"), "el buscador"), "zzcama");
    await esperar(() => aqui(".o_dcj_producto", "Zzcama"), "el producto");
    aqui(".o_dcj_producto .o_dcj_enlace", "Revisar antes").click();
    await esperar(() => !document.querySelector(".o_dcj_hoja"), "el buscador cerrado");
    const caja = document.querySelector("#o_dcj_texto");
    await esperar(() => caja.value.startsWith("Zzcama Roble Queen"), "el pie en la caja");
    await esperar(() => document.querySelector(".o_dcj_previa_listo"), "la foto en la caja");
    if (aqui(".o_dcj_burbuja_vendedora")) { throw new Error("todavía no se envió nada"); }
    await escribir(caja, caja.value + "\\nTe la dejo apartada");
    document.querySelector(".o_dcj_enviar").click();
    await esperar(() => aqui(".o_dcj_burbuja_vendedora", "Te la dejo apartada"), "enviada");
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
""")
        (envio,) = self.al_worker('/odoo/enviar')
        self.assertIn('Te la dejo apartada', envio['texto'])
        self.assertEqual(len(envio['adjuntos']), 1)

    def test_el_buscador_sin_resultados_lo_dice(self):
        self.datos_de_ejemplo()
        self.navegador("""
(async () => {
    await abrirConversacion("Karen");
    aqui(".o_dcj_herramienta", "Foto del catálogo").click();
    await escribir(await esperar(() => document.querySelector(".o_dcj_hoja input[type=search]"), "el buscador"), "zzzninguno");
    await esperar(() => aqui(".o_dcj_hoja", "No encuentro"), "el mensaje de sin resultados");
    escape();
    await esperar(() => !document.querySelector(".o_dcj_hoja"), "el buscador cerrado con Esc");
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
""")

    def test_cotizacion_crear_borrador_desde_el_catalogo(self):
        self.datos_de_ejemplo()
        cama = self.producto_de_ejemplo()
        self.navegador("""
(async () => {
    await abrirConversacion("Karen");
    aqui(".o_dcj_herramienta", "Cotización").click();
    await esperar(() => aqui(".o_dcj_hoja", "no tiene una cotización abierta"), "no hay cotización abierta");
    await escribir(document.querySelector(".o_dcj_hoja input[type=search]"), "zzcama");
    const producto = await esperar(() => aqui(".o_dcj_producto", "Zzcama"), "el producto");
    producto.querySelector("button").click();
    producto.querySelector("button").click();
    await esperar(() => aqui(".o_dcj_linea", "Zzcama") && aqui(".o_dcj_linea output").textContent === "2", "la línea con cantidad 2");
    aqui(".o_dcj_hoja_pie button", "Crear el borrador").click();
    await esperar(() => aqui(".o_dcj_hoja", "Enviar el PDF"), "el borrador creado, listo para enviar");
    if (!aqui(".o_dcj_hoja", "Borrador")) { throw new Error("la cotización dice Borrador"); }
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
""")
        orden = self.env['sale.order'].search([('partner_id', '=', self.karen.partner_id.id)])
        self.assertEqual((orden.state, orden.order_line.product_uom_qty, orden.order_line.product_id.product_tmpl_id),
                         ('draft', 2.0, cama), 'Un borrador, nunca confirmado')

    def test_tiempo_real_un_mensaje_nuevo_aparece_solo(self):
        self.datos_de_ejemplo()
        self.navegador("""
(async () => {
    await abrirConversacion("Karen");
    const antes = document.querySelectorAll(".o_dcj_burbuja").length;
    // Llega un mensaje del cliente por la API del Worker (como en producción).
    const r = await fetch("/dcasa/juan/v1/mensaje", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: "Bearer __TOKEN__" },
        body: JSON.stringify({ canal: "whatsapp_qr", id_externo: "50761000001", id_mensaje: "wamid.tiempo.real.1",
            direccion: "entrante", autor: "cliente", texto: "¿Siguen ahí? Me urge saber", ts: new Date().toISOString() }),
    });
    if (!r.ok) { throw new Error("la API de Juan respondió " + r.status); }
    await esperar(() => aqui(".o_dcj_burbuja_cliente", "Me urge saber"), "el mensaje nuevo, sin recargar", 30000);
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
""".replace("__TOKEN__", TOKEN_ODOO))



@tagged('post_install', '-at_install')
class TestPanelEnElCelular(PanelUiCase):
    """La vista de celular (390 px): una columna a la vez, la caja de respuesta fija abajo y botones de 44 px."""
    browser_size = '390x844'
    touch_enabled = True

    def test_una_columna_a_la_vez_caja_fija_y_botones_de_44_px(self):
        self.datos_de_ejemplo()
        self.navegador("""
(async () => {
    if (window.innerWidth !== 390) { throw new Error("el celular debe medir 390 px y mide " + window.innerWidth); }
    const hay = (sel) => {
        const el = document.querySelector(sel);
        return !!el && getComputedStyle(el).display !== "none" && el.getBoundingClientRect().width > 0;
    };
    const sinDesborde = (donde) => {
        const raiz = document.querySelector(".o_dcj");
        if (document.documentElement.scrollWidth > window.innerWidth + 1 || raiz.scrollWidth > raiz.clientWidth + 1) {
            throw new Error("desborde horizontal " + donde + ": " + document.documentElement.scrollWidth + " > " + window.innerWidth);
        }
    };
    // Botones, selectores y cajas con menos de 44 px (los enlaces de texto dentro de una frase no cuentan).
    const chicos = () => [...document.querySelectorAll(".o_dcj button, .o_dcj select, .o_dcj input:not([type=file]), .o_dcj textarea")]
        .filter((e) => !e.classList.contains("o_dcj_enlace") && getComputedStyle(e).visibility !== "hidden")
        .map((e) => [e, e.getBoundingClientRect()])
        .filter(([e, r]) => r.width > 0 && r.height > 0 && (r.width < 43.5 || r.height < 43.5))
        .map(([e, r]) => e.className + " [" + (e.getAttribute("aria-label") || e.textContent.trim().slice(0, 20)) + "] " + Math.round(r.width) + "x" + Math.round(r.height));

    // 1. Al abrir solo se ve la lista.
    await esperar(() => document.querySelectorAll(".o_dcj_fila").length === 3, "las tres conversaciones");
    if (!hay(".o_dcj_lista") || hay(".o_dcj_hilo") || hay(".o_dcj_ficha")) { throw new Error("al abrir solo debe verse la lista"); }
    sinDesborde("en la lista");
    let chicas = chicos();
    if (chicas.length) { throw new Error("en la lista, menos de 44 px: " + chicas.join(" | ")); }
    const fila = aqui(".o_dcj_fila", "Karen");
    if (fila.getBoundingClientRect().height < 64) { throw new Error("la fila de la lista es muy baja para el pulgar"); }

    // 2. Al tocar una conversación solo se ve el hilo, con la caja fija abajo.
    fila.click();
    await esperar(() => document.querySelector(".o_dcj_hilo_cuerpo .o_dcj_burbuja"), "las burbujas del hilo");
    if (hay(".o_dcj_lista") || !hay(".o_dcj_hilo") || hay(".o_dcj_ficha")) { throw new Error("al abrir un hilo solo debe verse el hilo"); }
    sinDesborde("en el hilo");
    const caja = document.querySelector(".o_dcj_caja");
    const antes = caja.getBoundingClientRect();
    const cuerpo = document.querySelector(".o_dcj_hilo_cuerpo");
    cuerpo.scrollTop = 0;
    window.scrollTo(0, 400);
    await pausa(120);
    const despues = caja.getBoundingClientRect();
    if (Math.abs(antes.top - despues.top) > 1 || Math.abs(antes.bottom - despues.bottom) > 1) { throw new Error("la caja de respuesta se movió al desplazar"); }
    if (window.innerHeight - despues.bottom > 4 || despues.bottom > window.innerHeight + 1) {
        throw new Error("la caja de respuesta debe quedar pegada abajo: bottom=" + despues.bottom + " de " + window.innerHeight);
    }
    if (document.documentElement.scrollHeight > window.innerHeight + 1) { throw new Error("la página entera se desplaza: la caja no sería fija"); }
    if (despues.height > window.innerHeight * 0.5) { throw new Error("la caja ocupa más de la mitad de la pantalla"); }
    chicas = chicos();
    if (chicas.length) { throw new Error("en el hilo, menos de 44 px: " + chicas.join(" | ")); }
    // Las burbujas no se salen de la pantalla.
    for (const b of document.querySelectorAll(".o_dcj_burbuja")) {
        const r = b.getBoundingClientRect();
        if (r.right > window.innerWidth || r.left < 0) { throw new Error("una burbuja se sale de la pantalla"); }
    }

    // 3. La ficha se abre como otra pantalla y se vuelve al hilo.
    document.querySelector(".o_dcj_boton_ficha").click();
    await esperar(() => hay(".o_dcj_ficha") && !hay(".o_dcj_hilo"), "la ficha a pantalla completa");
    sinDesborde("en la ficha");
    await esperar(() => document.querySelector(".o_dcj_ficha .o_dcj_cliente h3"), "la ficha del cliente");
    chicas = chicos();
    if (chicas.length) { throw new Error("en la ficha, menos de 44 px: " + chicas.join(" | ")); }
    document.querySelector(".o_dcj_volver_ficha").click();
    await esperar(() => hay(".o_dcj_hilo") && !hay(".o_dcj_ficha"), "volver de la ficha al hilo");

    // 4. «Volver» regresa a la lista.
    document.querySelector(".o_dcj_volver").click();
    await esperar(() => hay(".o_dcj_lista") && !hay(".o_dcj_hilo"), "volver a la lista");
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
""")

    def test_el_catalogo_es_una_hoja_que_sube_desde_abajo(self):
        self.datos_de_ejemplo()
        self.producto_de_ejemplo()
        self.navegador("""
(async () => {
    await abrirConversacion("Karen");
    const herramienta = (texto) => [...document.querySelectorAll(".o_dcj_herramienta")].find((e) => (e.getAttribute("aria-label") || "").includes(texto) || e.textContent.includes(texto));
    herramienta("Foto").click();
    const hoja = await esperar(() => document.querySelector(".o_dcj_hoja"), "la hoja del catálogo");
    const r = hoja.getBoundingClientRect();
    if (r.width < window.innerWidth - 1 || r.bottom < window.innerHeight - 1) { throw new Error("la hoja debe ocupar todo el ancho y pegarse abajo"); }
    if (document.documentElement.scrollWidth > window.innerWidth + 1) { throw new Error("desborde horizontal con la hoja abierta"); }
    await escribir(hoja.querySelector("input[type=search]"), "zzcama");
    await esperar(() => aqui(".o_dcj_producto", "Zzcama Roble Queen"), "el producto");
    for (const b of hoja.querySelectorAll("button")) {
        const c = b.getBoundingClientRect();
        if (c.width > 0 && (c.height < 43.5 || c.width < 43.5) && !b.classList.contains("o_dcj_enlace")) {
            throw new Error("botón de menos de 44 px en la hoja: " + (b.getAttribute("aria-label") || b.textContent.trim()) + " " + Math.round(c.width) + "x" + Math.round(c.height));
        }
    }
    escape();
    await esperar(() => !document.querySelector(".o_dcj_hoja"), "cerrar la hoja con Esc");
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
""")

    def test_resumen_costos_y_conexiones_caben_en_el_celular(self):
        self.datos_de_ejemplo()
        self.rutas = {('GET', '/odoo/salud'): (SALUD, 200), ('GET', '/odoo/costos'): (COSTOS, 200)}
        for url, listo in ((ACCION_RESUMEN, '.o_dcj_p_dato'), (ACCION_COSTOS, '.o_dcj_p_gigante'),
                           (ACCION_CONEXIONES, '.o_dcj_p_canal')):
            with self.subTest(url=url):
                self.navegador("""
(async () => {
    await esperar(() => document.querySelector("__LISTO__"), "la pantalla");
    await pausa(200);
    if (document.documentElement.scrollWidth > window.innerWidth + 1) {
        throw new Error("desborde horizontal: " + document.documentElement.scrollWidth + " > " + window.innerWidth);
    }
    const chicos = [...document.querySelectorAll(".o_dcj_p button")].filter((b) => !b.classList.contains("o_dcj_enlace"))
        .filter((b) => { const r = b.getBoundingClientRect(); return r.width > 0 && (r.height < 43.5 || r.width < 43.5); })
        .map((b) => b.textContent.trim() + " " + Math.round(b.getBoundingClientRect().width) + "x" + Math.round(b.getBoundingClientRect().height));
    if (chicos.length) { throw new Error("botones de menos de 44 px: " + chicos.join(" | ")); }
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
""".replace('__LISTO__', listo), url=url, login=GERENTE)


@tagged('post_install', '-at_install')
class TestPantallasDeJuan(PanelUiCase):
    """Resumen, Costos de IA y Conexiones, con el Worker de mentira."""

    def setUp(self):
        super().setUp()
        self.rutas = {
            ('GET', '/odoo/salud'): (SALUD, 200),
            ('GET', '/odoo/costos'): (COSTOS, 200),
            ('GET', '/odoo/qr'): ({'ok': True, 'estado': 'necesita_qr', 'edad_s': 3,
                                   'qr': 'data:image/png;base64,' + base64.b64encode(png((0, 0, 0), (64, 64))).decode()},
                                  200),
        }

    def sin_bot(self):
        """Odoo sin dirección ni clave del Worker."""
        parche = patch.dict(os.environ, {'JUAN_URL': '', 'JUAN_WORKER_TOKEN': ''})
        parche.start()
        self.addCleanup(parche.stop)

    def test_resumen_los_seis_numeros_y_los_periodos(self):
        self.datos_de_ejemplo()
        self.navegador("""
(async () => {
    await esperar(() => document.querySelectorAll(".o_dcj_p_dato").length === 6, "las seis tarjetas");
    const titulos = [...document.querySelectorAll(".o_dcj_p_dato h2")].map((e) => e.textContent.trim());
    const esperados = ["Mensajes", "Clientes únicos", "Resueltas sin una persona", "Oportunidades creadas", "Ventas atribuidas", "Primera respuesta"];
    if (titulos.join("|") !== esperados.join("|")) { throw new Error("tarjetas distintas: " + titulos.join("|")); }
    for (const v of document.querySelectorAll(".o_dcj_p_valor")) {
        if (!v.textContent.trim()) { throw new Error("una tarjeta sin valor"); }
    }
    if (aqui("body", "Falta conectar el bot")) { throw new Error("con el bot conectado no debe decir que falta conectarlo"); }
    const valorDe = (titulo) => aqui(".o_dcj_p_dato", titulo).querySelector(".o_dcj_p_valor").textContent.trim();
    if (!/^\\$[\\d,]+\\.\\d\\d$/.test(valorDe("Ventas atribuidas"))) { throw new Error("las ventas deben verse en dólares: " + valorDe("Ventas atribuidas")); }
    // Cambiar de periodo vuelve a pedir los números.
    aqui(".o_dcj_p_segmento button", "30 días").click();
    await esperar(() => aqui(".o_dcj_p_segmento button", "30 días").getAttribute("aria-pressed") === "true", "el periodo de 30 días");
    await esperar(() => Number(valorDe("Mensajes").replace(/[^0-9]/g, "")) >= 5, "los mensajes de 30 días");
    // Una vendedora no ve Costos ni Conexiones en la barra.
    const nav = [...document.querySelectorAll(".o_dcj_p_nav_boton")].map((e) => e.textContent.trim());
    if (nav.join("|") !== "Conversaciones|Resumen") { throw new Error("la barra de la vendedora: " + nav.join("|")); }
    aqui(".o_dcj_p_nav_boton", "Conversaciones").click();
    await esperar(() => document.querySelector(".o_dcj_lista"), "volver a Conversaciones desde el Resumen");
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
""", url=ACCION_RESUMEN)

    def test_resumen_sin_el_bot_conectado_lo_dice(self):
        self.sin_bot()
        self.datos_de_ejemplo()
        self.navegador("""
(async () => {
    await esperar(() => aqui(".o_dcj_p_aviso", "Falta conectar el bot"), "el aviso de que falta el bot");
    await esperar(() => document.querySelectorAll(".o_dcj_p_dato").length === 6, "los números de Odoo siguen ahí");
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
""", url=ACCION_RESUMEN)
        self.assertEqual(self.llamadas, [], 'sin Worker configurado no se sale a ninguna parte')

    def fotos_de_costos_del_mes(self):
        """Una foto del acumulado por cada día anterior de este mes: así el desglose por día tiene con qué pintarse."""
        hoy = self.env['dcasa.juan.panel']._ahora_local().date()
        for dia in range(1, hoy.day):
            self.env['dcasa.juan.costo.dia']._guardar(hoy.replace(day=dia), round(dia * 0.35, 2))

    def test_costos_gasto_tope_proyeccion_dia_y_modelo(self):
        self.fotos_de_costos_del_mes()
        self.navegador("""
(async () => {
    await esperar(() => document.querySelector(".o_dcj_p_gigante"), "el gasto del mes");
    const texto = (sel) => (document.querySelector(sel) || { textContent: "" }).textContent.replace(/\\s+/g, " ").trim();
    if (texto(".o_dcj_p_gigante") !== "$12.34") { throw new Error("gasto: " + texto(".o_dcj_p_gigante")); }
    if (!texto(".o_dcj_p_hero").includes("$30.00")) { throw new Error("el tope no aparece: " + texto(".o_dcj_p_hero")); }
    const medidor = document.querySelector(".o_dcj_p_medidor");
    if (!medidor || medidor.getAttribute("role") !== "meter" || Number(medidor.getAttribute("aria-valuenow")) !== 12.34) { throw new Error("el medidor del tope"); }
    // El estado va con ícono y palabra, nunca solo color.
    const estado = document.querySelector(".o_dcj_p_estado");
    if (!estado.querySelector("i.fa") || !estado.textContent.trim()) { throw new Error("el estado del tope sin ícono o sin texto"); }
    if (!/terminarás el mes en|Todavía es pronto/.test(texto(".o_dcj_p_frase"))) { throw new Error("falta la proyección: " + texto(".o_dcj_p_frase")); }
    // Por modelo, del más caro al más barato.
    const modelos = [...document.querySelectorAll(".o_dcj_p_modelos li")].map((e) => e.querySelector(".o_dcj_p_modelo_nombre").textContent.trim());
    if (modelos.join("|") !== "claude-sonnet-5-5|claude-haiku-4-5") { throw new Error("modelos: " + modelos.join("|")); }
    // Aviso del modelo sin precio que manda el Worker.
    if (!aqui(".o_dcj_p_aviso", "muse-spark-1.3")) { throw new Error("falta el aviso del modelo sin precio"); }
    // Por día: columnas y la misma información como tabla.
    await esperar(() => document.querySelectorAll(".o_dcj_p_columna").length >= 1, "las columnas por día");
    aqui(".o_dcj_p_tarjeta_cabecera button", "Ver como tabla").click();
    await esperar(() => document.querySelector("table.o_dcj_p_tabla"), "la tabla por día");
    if (!document.querySelector("table.o_dcj_p_tabla tbody tr")) { throw new Error("la tabla por día está vacía"); }
    // Ningún valor de clave en la página.
    if (document.body.textContent.includes("__TOKEN__")) { throw new Error("se coló un token en la página"); }
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
""".replace('__TOKEN__', TOKEN_WORKER), url=ACCION_COSTOS, login=GERENTE)
        # Se pidió el estado y el gasto por modelo, nada más.
        self.assertEqual({r for m, r, _j in self.llamadas}, {'/odoo/salud', '/odoo/costos'})

    def test_costos_sin_el_bot_conectado_dice_falta_conectar_el_bot(self):
        self.sin_bot()
        self.navegador("""
(async () => {
    const aviso = await esperar(() => document.querySelector(".o_dcj_p_sin_conectar"), "el aviso de que falta conectar");
    if (!aviso.textContent.includes("Falta conectar el bot")) { throw new Error("texto del aviso: " + aviso.textContent); }
    const faltan = [...aviso.querySelectorAll("code")].map((e) => e.textContent).join(",");
    if (faltan !== "JUAN_URL,JUAN_WORKER_TOKEN") { throw new Error("solo los nombres de lo que falta: " + faltan); }
    if (document.querySelector(".o_dcj_p_gigante")) { throw new Error("sin bot no hay cifras inventadas"); }
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
""", url=ACCION_COSTOS, login=GERENTE)

    def test_conexiones_estado_de_cada_canal_qr_y_confirmaciones(self):
        self.navegador("""
(async () => {
    await esperar(() => document.querySelectorAll(".o_dcj_p_canal").length === 5, "los cinco canales");
    const canal = (nombre) => aqui(".o_dcj_p_canal", nombre);
    const chip = (nombre) => canal(nombre).querySelector(".o_dcj_p_chip").textContent.replace(/\\s+/g, " ").trim();
    if (chip("WhatsApp (QR)") !== "Desconectado") { throw new Error("WhatsApp QR: " + chip("WhatsApp (QR)")); }
    if (chip("Telegram") !== "Faltan claves") { throw new Error("Telegram: " + chip("Telegram")); }
    if (chip("Messenger") !== "Apagado") { throw new Error("Messenger: " + chip("Messenger")); }
    for (const c of document.querySelectorAll(".o_dcj_p_chip")) {
        if (!c.querySelector("i.fa")) { throw new Error("un estado sin ícono (solo color)"); }
    }
    // Solo los NOMBRES de las claves que faltan.
    const claves = [...canal("Telegram").querySelectorAll("code")].map((e) => e.textContent).join(",");
    if (claves !== "TELEGRAM_BOT_TOKEN_JUAN,TELEGRAM_WEBHOOK_SECRET_JUAN") { throw new Error("claves de Telegram: " + claves); }
    if (!aqui(".o_dcj_p_tarjeta", "Claves que faltan en el Worker").textContent.includes("META_AI_API_KEY")) { throw new Error("falta META_AI_API_KEY en la lista"); }
    if (!aqui(".o_dcj_p_aviso", "Hay cosas por revisar")) { throw new Error("falta el aviso general"); }

    // El QR.
    aqui("button", "Mostrar el QR para vincular").click();
    const imagen = await esperar(() => document.querySelector(".o_dcj_p_qr_imagen img"), "el código QR");
    if (!imagen.src.startsWith("data:image/png;base64,") || !imagen.alt) { throw new Error("el QR debe ser una imagen con texto alternativo"); }
    await esperar(() => aqui(".o_dcj_p_qr", "Esperando que lo escanees"), "el estado del QR");
    aqui("button", "Ocultar el QR").click();
    await esperar(() => !document.querySelector(".o_dcj_p_qr"), "ocultar el QR");

    // Reiniciar: pide confirmación y cancelar no hace nada.
    aqui(".o_dcj_p_acciones button", "Reiniciar").click();
    await esperar(() => aqui(".modal .modal-title", "Reiniciar el puente"), "la confirmación de reiniciar");
    aqui(".modal-footer button", "Cancelar").click();
    await esperar(() => !document.querySelector(".modal"), "cerrar la confirmación");
    await pausa(300);
    // Confirmar sí lo hace.
    aqui(".o_dcj_p_acciones button", "Reiniciar").click();
    await esperar(() => aqui(".modal .modal-title", "Reiniciar el puente"), "la confirmación otra vez");
    aqui(".modal-footer button", "Reiniciar").click();
    await esperar(() => aqui(".o_notification", "Se pidió reiniciar"), "el aviso de que se reinició");

    // Desvincular: botón rojo, pide confirmación con otro texto.
    await esperar(() => !document.querySelector(".modal"), "sin diálogos abiertos");
    aqui(".o_dcj_p_acciones button", "Desvincular").click();
    await esperar(() => aqui(".modal .modal-title", "Desvincular el número"), "la confirmación de desvincular");
    const rojo = document.querySelector(".modal-footer .btn-danger");
    if (!rojo || !rojo.textContent.includes("Sí, desvincular")) { throw new Error("el botón de desvincular debe ser rojo y claro"); }
    aqui(".modal-footer button", "No, dejarlo conectado").click();
    await esperar(() => !document.querySelector(".modal"), "cancelar desvincular");
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
""", url=ACCION_CONEXIONES, login=GERENTE)
        self.assertEqual(len(self.al_worker('/odoo/reiniciar')), 1, 'se reinició una sola vez (la primera se canceló)')
        self.assertEqual(self.al_worker('/odoo/desvincular'), [], 'cancelar la confirmación no desvincula')
        self.assertTrue(self.al_worker('/odoo/qr', 'GET'))
        # Quedó la nota en el historial de los ajustes (quién y cuándo).
        notas = self.ajustes.message_ids.filtered(lambda m: 'reinició el puente' in (m.body or ''))
        self.assertTrue(notas)

    def test_conexiones_desvincular_confirmado_llama_al_puente(self):
        self.navegador("""
(async () => {
    await esperar(() => document.querySelector(".o_dcj_p_acciones"), "las acciones de WhatsApp");
    aqui(".o_dcj_p_acciones button", "Desvincular").click();
    await esperar(() => document.querySelector(".modal-footer .btn-danger"), "la confirmación");
    document.querySelector(".modal-footer .btn-danger").click();
    await esperar(() => aqui(".o_notification", "desvinculado"), "el aviso de que quedó desvinculado");
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
""", url=ACCION_CONEXIONES, login=GERENTE)
        self.assertEqual(len(self.al_worker('/odoo/desvincular')), 1)

    def test_conexiones_y_costos_no_son_para_una_vendedora(self):
        """Los menús de gerencia no aparecen y el servidor tampoco contesta."""
        panel = self.env['dcasa.juan.panel'].with_user(self.vendedora)
        for metodo in ('costos', 'conexiones', 'qr', 'reiniciar_puente', 'desvincular_puente'):
            with self.subTest(metodo=metodo), self.assertRaises(AccessError):
                getattr(panel, metodo)()
