"""El panel de Bodega en un navegador de verdad, a tamaño tablet: buscar, abrir por QR, marcar y validar."""
import json

from odoo.tests import HttpCase, tagged

from .bodega_comun import BodegaCommon

AYUDAS = """
    const esperar = async (fn, que, ms = 20000) => {
        const inicio = Date.now();
        while (Date.now() - inicio < ms) {
            const r = fn();
            if (r) { return r; }
            await new Promise((ok) => setTimeout(ok, 100));
        }
        throw new Error("Bodega: no apareció " + que);
    };
    const falla = (texto) => { throw new Error("Bodega: " + texto); };
    const boton = (texto, dentro = document) => [...dentro.querySelectorAll(".o_dcasa_bodega button")]
        .find((b) => b.textContent.replace(/\\s+/g, " ").trim().startsWith(texto));
    const escribir = (el, valor) => {
        el.value = valor;
        el.dispatchEvent(new Event("input", { bubbles: true }));
    };
    const enter = (el) => el.dispatchEvent(
        new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
    const tarjetas = () => [...document.querySelectorAll(".o_dcasa_bodega_tarjeta")];
    const tarjeta = (nombre) => tarjetas().find((t) => t.dataset.entrega === nombre);
    const linea = (texto) => [...document.querySelectorAll(".o_dcasa_bodega_linea")]
        .find((l) => l.querySelector(".o_dcasa_bodega_linea_nombre").textContent.includes(texto));
    const sinScrollDeLado = () => {
        const raiz = document.querySelector(".o_dcasa_bodega");
        if (raiz.scrollWidth > raiz.clientWidth + 1) {
            falla("hay scroll de lado: " + raiz.scrollWidth + " > " + raiz.clientWidth);
        }
    };
"""

TABLET = """
(async () => {
    __AYUDAS__
    const D = __DATOS__;
    const campo = await esperar(() => document.querySelector(".o_dcasa_bodega_texto"), "el cuadro del lector");
    await esperar(() => tarjeta(D.envio) && tarjeta(D.flete) && tarjeta(D.retiro), "las tarjetas");
    if (document.activeElement !== campo) { falla("el cuadro debe tener el foco para el lector"); }
    sinScrollDeLado();
    const filtros = ["Para despachar (envío)", "Para retirar en tienda", "Listas para salir", "Esperando producto"];
    for (const texto of filtros) {
        if (!boton(texto)) { falla("falta el filtro " + texto); }
    }
    const envio = tarjeta(D.envio);
    for (const texto of ["CLIENTE DE PRUEBA ENVIO", D.pedido_envio, "Envío a domicilio", "Lista para salir",
                         "ZZCAMA DE PRUEBA"]) {
        if (!envio.textContent.includes(texto)) { falla("a la tarjeta le falta " + texto); }
    }
    if (!tarjeta(D.retiro).textContent.includes("Retira en la tienda")) { falla("el retiro no dice que se retira"); }

    // Retiro en tienda: solo las de retiro.
    boton("Para retirar en tienda").click();
    await esperar(() => !tarjeta(D.envio) && tarjeta(D.retiro), "solo las de retiro");
    boton("Todas").click();
    await esperar(() => tarjeta(D.envio), "todas otra vez");

    // Buscar por cliente (sin tildes ni mayúsculas).
    escribir(campo, "cliente de prueba retiro");
    await esperar(() => tarjetas().length === 1 && tarjeta(D.retiro), "la búsqueda por cliente");
    campo.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    await esperar(() => tarjetas().length >= 3, "la lista sin búsqueda");

    // Un pedido sin pago ni abono no sale en la lista y su QR lo dice (decisión de la dueña, 2026-10-22).
    if (tarjeta(D.sin_pago)) { falla("salió una entrega sin pago ni abono"); }
    escribir(campo, D.qr_sin_pago);
    enter(campo);
    const sinPago = await esperar(() => document.querySelector(".o_dcasa_bodega_msg_error"), "el aviso sin pago");
    if (!sinPago.textContent.includes("todavía no tiene pago ni abono: no se entrega")) {
        falla("aviso sin pago: " + sinPago.textContent);
    }
    if (document.querySelector(".o_dcasa_bodega_titulo_entrega")) { falla("abrió una entrega sin pago"); }

    // El QR de la nota de entrega (lector tipo teclado: escribe la dirección y Enter) abre esa entrega.
    escribir(campo, D.qr_envio);
    enter(campo);
    await esperar(() => document.querySelector(".o_dcasa_bodega_titulo_entrega")?.textContent === D.envio,
                  "la entrega abierta por su QR");
    if (!document.body.innerText.includes("6000-0001")) { falla("falta el teléfono del cliente"); }
    sinScrollDeLado();
    const lector = await esperar(() => document.activeElement?.id === "o_dcasa_bodega_lector" && document.activeElement,
                                 "el foco en el cuadro de productos");

    // Escanear un producto lo marca; uno que no es de la entrega avisa.
    escribir(lector, "ZZT-CAMA-1");
    enter(lector);
    await esperar(() => linea("ZZCAMA").querySelector(".o_dcasa_bodega_cifra")?.textContent.includes("1 de 2"),
                  "la cama marcada con el lector");
    escribir(lector, "ZZT-ZAP-1");
    enter(lector);
    await esperar(() => document.querySelector(".o_dcasa_bodega_msg_error")?.textContent
        .includes("no es de esta entrega"), "el aviso de producto equivocado");
    linea("ZZCAMA").querySelector(".o_dcasa_bodega_mas_uno").click();
    await esperar(() => linea("ZZCAMA").classList.contains("o_dcasa_bodega_linea_lista"), "la cama completa");
    boton("Marcar", linea("ZZMESA")).click();
    await esperar(() => linea("ZZMESA").classList.contains("o_dcasa_bodega_linea_lista"), "la mesa marcada");
    boton("Validar entrega").click();
    const exito = await esperar(() => document.querySelector(".o_dcasa_bodega_exito"), "el aviso de éxito");
    if (!exito.textContent.includes(D.envio) || !exito.textContent.includes("entregada completa")) {
        falla("éxito: " + exito.textContent);
    }
    if (!boton("Imprimir nota de entrega")) { falla("falta imprimir la nota"); }
    await esperar(() => !tarjeta(D.envio) && tarjeta(D.flete), "la lista sin la entrega validada");

    // A medias: se marca una de dos camas y pregunta en sencillo.
    tarjeta(D.flete).querySelector(".o_dcasa_bodega_abrir").click();
    await esperar(() => document.querySelector(".o_dcasa_bodega_titulo_entrega")?.textContent === D.flete,
                  "la entrega del flete");
    linea("ZZCAMA").querySelector(".o_dcasa_bodega_mas_uno").click();
    boton("Validar entrega").click();
    const pregunta = await esperar(() => document.querySelector(".o_dcasa_bodega_confirmar"), "la pregunta");
    for (const texto of ["¿Entregar solo lo marcado?", "marcaste 1 de 2", "pendiente"]) {
        if (!pregunta.textContent.includes(texto)) { falla("a la pregunta le falta " + texto); }
    }
    boton("Volver", pregunta).click();
    await esperar(() => !document.querySelector(".o_dcasa_bodega_confirmar"), "cerrar la pregunta");
    boton("Validar entrega").click();
    boton("Sí, entregar solo lo marcado", await esperar(() => document.querySelector(".o_dcasa_bodega_confirmar"),
                                                         "la pregunta otra vez")).click();
    const exito2 = await esperar(() => document.querySelector(".o_dcasa_bodega_exito")?.textContent.includes(D.flete)
                                 && document.querySelector(".o_dcasa_bodega_exito"), "el éxito a medias");
    if (!exito2.textContent.includes("quedó pendiente en")) { falla("éxito a medias: " + exito2.textContent); }
    if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia
            && !document.querySelector(".o_dcasa_bodega_camara")) {
        falla("falta el botón de la cámara");
    }
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
"""

TAMANOS = """
(async () => {
    __AYUDAS__
    const D = __DATOS__;
    await esperar(() => tarjeta(D.envio), "las tarjetas");
    sinScrollDeLado();
    tarjeta(D.envio).querySelector(".o_dcasa_bodega_abrir").click();
    await esperar(() => document.querySelector(".o_dcasa_bodega_titulo_entrega"), "la entrega");
    sinScrollDeLado();
    const validar = boton("Validar entrega");
    const caja = validar.getBoundingClientRect();
    if (caja.bottom > window.innerHeight + 1 || caja.height < 56) {
        falla("«Validar entrega» debe verse abajo y ser grande: " + JSON.stringify(caja));
    }
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
"""


@tagged('post_install', '-at_install')
class TestBodegaEnElNavegador(HttpCase, BodegaCommon):

    def codigo(self, plantilla):
        datos = {
            'envio': self.entrega_envio.name, 'retiro': self.entrega_retiro.name, 'flete': self.entrega_flete.name,
            'pedido_envio': self.pedido_envio.name,
            'qr_envio': f'{self.base_url()}/dcasa/doc/ENT/{self.entrega_envio.name}',
        }
        if getattr(self, 'entrega_sin_pago', None):
            datos.update(sin_pago=self.entrega_sin_pago.name,
                         qr_sin_pago=f'{self.base_url()}/dcasa/doc/ENT/{self.entrega_sin_pago.name}')
        return plantilla.replace('__AYUDAS__', AYUDAS).replace('__DATOS__', json.dumps(datos))

    def test_en_la_tablet_busca_abre_por_qr_marca_y_valida(self):
        _pedido, self.entrega_sin_pago = self.venta(self.cliente_sin, [(self.mesa, 1)], pago=0)
        self.browser_size = '820x1180'
        self.touch_enabled = True
        self.browser_js('/odoo/bodega', self.codigo(TABLET), ready='odoo.isReady', login='bodega_trabajador',
                        timeout=180)
        self.assertEqual(self.entrega_envio.state, 'done')
        self.assertEqual(self.entrega_flete.state, 'done')
        pendiente = self.entrega_flete.backorder_ids
        self.assertEqual(len(pendiente), 1)
        self.assertEqual(sum(pendiente.move_ids.mapped('product_uom_qty')), 1)
        nota = self.entrega_envio.message_ids.filtered(lambda m: 'panel de Bodega' in (m.body or ''))
        self.assertEqual(nota.author_id, self.bodeguero.partner_id)

    def test_en_tablet_acostada_celular_y_computadora_sin_scroll_de_lado(self):
        for tamano in ('1180x820', '390x844', '1440x900'):
            with self.subTest(tamano=tamano):
                self.browser_size = tamano
                self.browser_js('/odoo/bodega', self.codigo(TAMANOS), ready='odoo.isReady',
                                login='bodega_trabajador', timeout=120)

    def test_el_qr_con_la_camara_del_telefono_abre_la_entrega_en_bodega(self):
        """La cámara normal del teléfono abre /dcasa/doc/ENT/… y, para quien usa Inventario, llega al panel con esa
        entrega abierta (decisión de la dueña, 2026-10-22)."""
        codigo = """
        (async () => {
            __AYUDAS__
            const D = __DATOS__;
            await esperar(() => document.querySelector(".o_dcasa_bodega_titulo_entrega")?.textContent === D.retiro,
                          "la entrega de la dirección");
            console.log("test successful");
        })().catch((e) => console.error(e.message || e));
        """.replace('__AYUDAS__', AYUDAS).replace('__DATOS__', json.dumps({'retiro': self.entrega_retiro.name}))
        self.browser_js(f'/dcasa/doc/ENT/{self.entrega_retiro.name}', codigo, ready='odoo.isReady',
                        login='bodega_trabajador', timeout=120)
