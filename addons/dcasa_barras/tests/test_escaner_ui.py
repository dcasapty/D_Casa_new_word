"""La pantalla «Escáner» en un navegador de verdad: se escribe el código, sale el producto y se cuenta."""
from odoo.tests import HttpCase, tagged

from .comun import BarrasCommon

CODIGO = """
(async () => {
    const esperar = async (fn, que, ms = 20000) => {
        const inicio = Date.now();
        while (Date.now() - inicio < ms) {
            const r = fn();
            if (r) { return r; }
            await new Promise((ok) => setTimeout(ok, 100));
        }
        throw new Error("Escáner: no apareció " + que);
    };
    const boton = (texto) => [...document.querySelectorAll(".o_dcasa_escaner button")]
        .find((b) => b.textContent.trim() === texto);
    const escribir = (el, valor) => {
        el.value = valor;
        el.dispatchEvent(new Event("input", { bubbles: true }));
    };
    const campo = await esperar(() => document.querySelector(".o_dcasa_escaner_texto"), "el cuadro del lector");
    const falla = (texto) => { throw new Error("Escáner: " + texto); };
    if (document.activeElement !== campo) { falla("el cuadro debe tener el foco al abrir"); }

    // Consultar: el lector escribe el código y termina con Enter.
    escribir(campo, "ZZT-CAMA-1");
    campo.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
    const nombre = await esperar(() => document.querySelector(".o_dcasa_ficha_nombre"), "la tarjeta del producto");
    if (!nombre.textContent.includes("Zzcama de prueba")) { falla("producto equivocado " + nombre.textContent); }
    const precio = document.querySelector(".o_dcasa_ficha_precio").textContent;
    if (!precio.includes("$349.99 + ITBMS")) { falla("precio " + precio); }
    if (document.querySelector(".o_dcasa_total_cifra").textContent.trim() !== "12") { falla("existencias"); }
    if (document.querySelector(".o_dcasa_ficha").textContent.includes("77.77")) { falla("salió el costo"); }
    if (document.activeElement !== campo || campo.value !== "") { falla("el cuadro debe quedar vacío y con foco"); }

    // Un código que no existe avisa.
    escribir(campo, "NO-EXISTE-999");
    campo.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
    const aviso = await esperar(() => document.querySelector(".o_dcasa_msg_aviso"), "el aviso de código no encontrado");
    if (!aviso.textContent.includes("NO-EXISTE-999")) { falla("aviso " + aviso.textContent); }

    // Contar: se escribe lo contado, se ve la diferencia y se confirma.
    escribir(campo, "ZZT-CAMA-1");
    campo.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
    await esperar(() => document.querySelector(".o_dcasa_ficha_nombre"), "la tarjeta otra vez");
    boton("Contar").click();
    const cantidad = await esperar(() => document.querySelector(".o_dcasa_cantidad"), "el campo de cantidad");
    escribir(cantidad, "9");
    boton("Revisar").click();
    const confirmar = await esperar(() => document.querySelector(".o_dcasa_confirmar"), "la confirmación");
    if (!confirmar.textContent.includes("-3")) { falla("la diferencia debe ser -3: " + confirmar.textContent); }
    boton("Confirmar conteo").click();
    await esperar(() => document.querySelector(".o_dcasa_msg_ok"), "el aviso de conteo guardado");
    if (document.querySelector(".o_dcasa_total_cifra").textContent.trim() !== "9") {
        falla("no se actualizó la cifra");
    }

    // Precio (pedido de la dueña, 2026-10-16): en «Contar», Gerencia de Ventas lo cambia ahí mismo y confirma.
    const precioNuevo = await esperar(() => document.querySelector(".o_dcasa_precio_nuevo"), "el campo del precio");
    escribir(precioNuevo, "399.5");
    boton("Revisar precio").click();
    const verPrecio = await esperar(() => document.querySelector(".o_dcasa_precio .o_dcasa_confirmar"),
                                    "la confirmación del precio");
    if (!verPrecio.textContent.includes("$349.99") || !verPrecio.textContent.includes("$399.50")) {
        falla("la confirmación del precio debe decir antes y después: " + verPrecio.textContent);
    }
    boton("Guardar precio").click();
    await esperar(() => document.querySelector(".o_dcasa_ficha_precio")?.textContent.includes("$399.50 + ITBMS"),
                  "el precio nuevo en la tarjeta");
    // La cámara del celular, además de la pistola: el botón sale si el navegador deja usar la cámara.
    if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia
            && !document.querySelector(".o_dcasa_camara")) {
        falla("falta el botón de la cámara");
    }
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
"""

CODIGO_PARECIDO = """
(async () => {
    const esperar = async (fn, que, ms = 20000) => {
        const inicio = Date.now();
        while (Date.now() - inicio < ms) {
            const r = fn();
            if (r) { return r; }
            await new Promise((ok) => setTimeout(ok, 100));
        }
        throw new Error("Escáner: no apareció " + que);
    };
    const boton = (texto) => [...document.querySelectorAll(".o_dcasa_escaner button")]
        .find((b) => b.textContent.trim() === texto);
    const escribir = (el, valor) => {
        el.value = valor;
        el.dispatchEvent(new Event("input", { bubbles: true }));
    };
    const campo = await esperar(() => document.querySelector(".o_dcasa_escaner_texto"), "el cuadro del lector");
    const falla = (texto) => { throw new Error("Escáner: " + texto); };
    const enter = () => campo.dispatchEvent(
        new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
    const espera = (ms) => new Promise((ok) => setTimeout(ok, ms));

    // Dos escaneos seguidos, sin esperar la respuesta del primero: gana el último y ninguno se pierde sin avisar.
    escribir(campo, "ZZT-CAMA-1");
    enter();
    escribir(campo, "ZZT-ZAP-1");
    enter();
    await esperar(() => (document.querySelector(".o_dcasa_ficha_nombre") || {}).textContent?.includes("Zzzapatera"),
                  "la tarjeta del último escaneo");
    await espera(800);
    if (!document.querySelector(".o_dcasa_ficha_nombre").textContent.includes("Zzzapatera")) {
        falla("la respuesta del primer escaneo pisó la del último");
    }

    // Un código parecido (otros símbolos) se avisa y no se puede contar hasta confirmar que es ese producto.
    escribir(campo, "zzt_sofa_31");
    enter();
    await esperar(() => document.querySelector(".o_dcasa_parecido"), "el aviso de código parecido");
    boton("Contar").click();
    await esperar(() => document.querySelector(".o_dcasa_ficha .o_dcasa_nota"), "la nota de confirmar el producto");
    if (document.querySelector(".o_dcasa_cantidad")) {
        falla("no se debe poder contar sin confirmar que es ese producto");
    }
    boton("Sí, es este").click();
    const cantidad = await esperar(() => document.querySelector(".o_dcasa_cantidad"), "el campo de cantidad");
    if (document.querySelector(".o_dcasa_parecido")) { falla("el aviso debe irse al confirmar"); }

    // La cantidad: solo números con punto y, en unidades enteras, sin decimales.
    escribir(cantidad, "1,200");
    boton("Revisar").click();
    let error = await esperar(() => document.querySelector(".o_dcasa_msg_error"), "el error por la coma");
    if (!error.textContent.includes("sin comas")) { falla("mensaje " + error.textContent); }
    escribir(cantidad, "3.5");
    boton("Revisar").click();
    await esperar(() => (document.querySelector(".o_dcasa_msg_error") || {}).textContent?.includes("enteras"),
                  "el error por decimales");
    escribir(cantidad, "5");
    boton("Revisar").click();
    const confirmar = await esperar(() => document.querySelector(".o_dcasa_confirmar"), "la confirmación");
    if (!confirmar.textContent.includes("WH/Stock")) { falla("la confirmación debe decir dónde se contó"); }
    await espera(100);
    if (document.activeElement.textContent.trim() !== "Confirmar conteo") { falla("el foco debe estar en Confirmar"); }
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
"""


CODIGO_ASIGNAR = """
(async () => {
    const esperar = async (fn, que, ms = 20000) => {
        const inicio = Date.now();
        while (Date.now() - inicio < ms) {
            const r = fn();
            if (r) { return r; }
            await new Promise((ok) => setTimeout(ok, 100));
        }
        throw new Error("Asignar: no apareció " + que);
    };
    const boton = (texto) => [...document.querySelectorAll(".o_dcasa_escaner button")]
        .find((b) => b.textContent.trim() === texto);
    const escribir = (el, valor) => {
        el.value = valor;
        el.dispatchEvent(new Event("input", { bubbles: true }));
    };
    const enter = (el) => el.dispatchEvent(
        new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
    const falla = (texto) => { throw new Error("Asignar: " + texto); };
    const espera = (ms) => new Promise((ok) => setTimeout(ok, ms));
    // Otra persona (u otra pestaña) hace algo por su lado: se llama al servidor sin pasar por esta pantalla.
    const llamar = async (modelo, metodo, args) => {
        const r = await fetch(`/web/dataset/call_kw/${modelo}/${metodo}`, {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ jsonrpc: "2.0", method: "call",
                                   params: { model: modelo, method: metodo, args, kwargs: {} } }),
        });
        const j = await r.json();
        if (j.error) { throw new Error(JSON.stringify(j.error).slice(0, 300)); }
        return j.result;
    };
    const campo = await esperar(() => document.querySelector(".o_dcasa_escaner_texto"), "el cuadro del lector");
    const codigoEnPantalla = (esperado, que) => esperar(
        () => (document.querySelector(".o_dcasa_etiqueta_codigo") || {}).textContent?.trim() === esperado,
        que);
    const elegir = async (nombre, buscado) => {
        const caja = await esperar(
            () => document.querySelector(".o_dcasa_busqueda_producto"), "la búsqueda del producto");
        escribir(caja, buscado);
        enter(caja);
        (await esperar(() => [...document.querySelectorAll(".o_dcasa_opciones_etiqueta .o_dcasa_opcion")]
            .find((o) => o.textContent.includes(nombre)), "el producto " + nombre + " en la lista")).click();
        return esperar(() => document.querySelector(".o_dcasa_asignar_confirmar"), "la confirmación");
    };

    // Se escanea la etiqueta del rollo (el lector puede escribirla en minúsculas) y todavía no es de nadie.
    boton("Asignar").click();
    await esperar(() => document.querySelector(".o_dcasa_asignar_guia"), "la guía de Asignar");
    escribir(campo, "dc9500");
    enter(campo);
    const codigo = await esperar(() => document.querySelector(".o_dcasa_etiqueta_codigo"), "el número de la etiqueta");
    if (codigo.textContent.trim() !== "DC9500") { falla("el número debe salir en mayúsculas: " + codigo.textContent); }
    if (!document.querySelector(".o_dcasa_etiqueta_cabecera").textContent.includes("Sin producto")) {
        falla("una etiqueta nueva no es de ningún producto");
    }
    if (campo.value !== "") { falla("el cuadro del lector debe quedar vacío"); }

    // El foco pasa a la búsqueda del producto. Si el lector escribe OTRA etiqueta ahí, es un escaneo, no un nombre.
    const busqueda = await esperar(
        () => document.querySelector(".o_dcasa_busqueda_producto"), "la búsqueda del producto");
    await espera(150);
    if (document.activeElement !== busqueda) { falla("el foco debe pasar a la búsqueda del producto"); }
    escribir(busqueda, "dc9501");
    enter(busqueda);
    await codigoEnPantalla("DC9501", "la etiqueta escaneada dentro de la búsqueda");
    if (document.querySelector(".o_dcasa_busqueda_producto").value !== "") { falla("la búsqueda debe quedar vacía"); }
    escribir(campo, "dc9500");
    enter(campo);
    await codigoEnPantalla("DC9500", "volver a la primera etiqueta");

    // Producto elegido: el foco queda en el cuadro del lector (un escaneo no confirma nada).
    const confirmar = await elegir("Zzmesa A", "zzmesa a");
    if (!confirmar.textContent.includes("DC9500")) {
        falla("la confirmación debe decir la etiqueta: " + confirmar.textContent);
    }
    await espera(150);
    if (document.activeElement !== campo) { falla("el foco debe quedar en el cuadro del lector"); }
    if (!campo.placeholder.includes("Enter para asignar")) { falla("el cuadro debe decir que Enter asigna"); }
    escribir(campo, "dc9502");
    enter(campo);
    await codigoEnPantalla("DC9502", "otra etiqueta escaneada en la confirmación");
    const libre = await llamar("dcasa.barras", "etiqueta", ["DC9500"]);
    if (libre.estado !== "libre") { falla("escanear otra etiqueta no debe asignar la anterior: " + libre.estado); }

    // De nuevo: ahora Enter con el cuadro vacío asigna.
    escribir(campo, "DC9500");
    enter(campo);
    await codigoEnPantalla("DC9500", "la etiqueta otra vez");
    await elegir("Zzmesa A", "zzmesa a");
    await espera(150);
    enter(campo);
    const ok = await esperar(() => document.querySelector(".o_dcasa_msg_ok"), "el aviso de etiqueta asignada");
    if (!ok.textContent.includes("DC9500")) { falla("aviso " + ok.textContent); }
    if (document.querySelector(".o_dcasa_etiqueta_cabecera")) {
        falla("después de asignar la pantalla queda lista para la siguiente");
    }

    // La misma etiqueta otra vez: ya es de ese producto. Se pasa a otro producto a propósito.
    escribir(campo, "DC9500");
    enter(campo);
    const dueno = await esperar(
        () => document.querySelector(".o_dcasa_ficha_dueno"), "el producto dueño de la etiqueta");
    if (!dueno.textContent.includes("Zzmesa A")) { falla("dueño " + dueno.textContent); }
    if (!document.querySelector(".o_dcasa_etiqueta_cabecera").textContent.includes("Ya asignada")) { falla("estado"); }
    boton("Pasarla a otro producto").click();
    const confirmar2 = await elegir("Zzmesa B", "zzmesa b");
    if (!confirmar2.textContent.includes("Zzmesa A") || !confirmar2.textContent.includes("sin etiqueta")) {
        falla("debe avisar que el anterior se queda sin etiqueta: " + confirmar2.textContent);
    }

    // Mientras la persona mira la confirmación, otra persona pasa la etiqueta a «Zzmesa C»: el clic no se la quita.
    const antes = await llamar("dcasa.barras", "etiqueta", ["DC9500"]);
    const c = (await llamar("dcasa.barras", "buscar_por_nombre", ["zzmesa c"]))[0];
    await llamar("dcasa.barras", "asignar_etiqueta",
                 ["DC9500", c.id, { estado: antes.estado, dueno_id: antes.producto.id }]);
    boton("Asignar etiqueta").click();
    const aviso = await esperar(() => document.querySelector(".o_dcasa_asignar_confirmar .o_dcasa_parecido"),
                                "la pregunta de que la etiqueta cambió");
    if (!aviso.textContent.includes("Zzmesa C")) { falla("debe decir quién la tiene ahora: " + aviso.textContent); }
    if (document.querySelector(".o_dcasa_msg_ok")) { falla("no debió asignar sin que la persona viera el cambio"); }
    boton("Sí, asignarla").click();
    await esperar(() => (document.querySelector(".o_dcasa_msg_ok") || {}).textContent?.includes("Zzmesa C"),
                  "el aviso de etiqueta pasada");

    // Quitar la etiqueta: pide confirmar en un cuadro y deja el número retirado.
    escribir(campo, "DC9500");
    enter(campo);
    await esperar(() => document.querySelector(".o_dcasa_ficha_dueno"), "el dueño nuevo");
    boton("Quitar la etiqueta").click();
    const quitar = await esperar(() => [...document.querySelectorAll(".modal-footer button")]
        .find((b) => b.textContent.trim() === "Sí, quitarla"), "el cuadro de confirmar");
    quitar.click();
    await esperar(() => (document.querySelector(".o_dcasa_msg_ok") || {}).textContent?.includes("retirada"),
                  "el aviso de etiqueta quitada");

    // Retirada: en Asignar avisa que estuvo retirada y en Consultar dice que ya no es de ningún producto.
    escribir(campo, "DC9500");
    enter(campo);
    await esperar(() => document.querySelector(".o_dcasa_aviso_retirada"), "el aviso de etiqueta retirada");
    boton("Consultar").click();
    escribir(campo, "DC9500");
    enter(campo);
    const retirada = await esperar(() => document.querySelector(".o_dcasa_msg_aviso"), "el aviso al consultar");
    if (!retirada.textContent.includes("retirada")) {
        falla("al consultar debe decir que está retirada: " + retirada.textContent);
    }

    // Al volver a Asignar no queda la etiqueta de antes a medias.
    boton("Asignar").click();
    await esperar(() => document.querySelector(".o_dcasa_asignar_guia"), "la guía de Asignar otra vez");
    if (document.querySelector(".o_dcasa_etiqueta_cabecera")) { falla("no debe quedar la etiqueta de antes"); }
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
"""

CODIGO_SIN_ASIGNAR = """
(async () => {
    const esperar = async (fn, que, ms = 20000) => {
        const inicio = Date.now();
        while (Date.now() - inicio < ms) {
            const r = fn();
            if (r) { return r; }
            await new Promise((ok) => setTimeout(ok, 100));
        }
        throw new Error("Escáner: no apareció " + que);
    };
    await esperar(() => document.querySelector(".o_dcasa_escaner_texto"), "el cuadro del lector");
    const modos = [...document.querySelectorAll(".o_dcasa_modo")].map((b) => b.textContent.trim());
    if (modos.join(",") !== "Consultar,Contar") { throw new Error("Escáner: la Vendedora ve las pestañas " + modos); }
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
"""


# El lector escribe la dirección del QR de un documento: con permiso se abre el documento; sin permiso, un aviso.
CODIGO_DOCUMENTO = """
(async () => {
    const esperar = async (fn, que, ms = 30000) => {
        const inicio = Date.now();
        while (Date.now() - inicio < ms) {
            const r = fn();
            if (r) { return r; }
            await new Promise((ok) => setTimeout(ok, 100));
        }
        throw new Error("Escáner (documento): no apareció " + que);
    };
    const escribir = (el, valor) => {
        el.value = valor;
        el.dispatchEvent(new Event("input", { bubbles: true }));
    };
    const campo = await esperar(() => document.querySelector(".o_dcasa_escaner_texto"), "el cuadro del lector");
    const falla = (texto) => { throw new Error("Escáner (documento): " + texto); };
    const leer = (url) => {
        escribir(campo, url);
        campo.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
    };
    if (__PERMITIDO__) {
        leer("__URL__");
        const formulario = await esperar(() => document.querySelector(".o_form_view"), "el formulario del documento");
        await esperar(() => formulario.textContent.includes("__NOMBRE__"), "el nombre del documento en el formulario");
        if (document.querySelector(".o_dcasa_escaner")) { falla("el Escáner debía cerrarse al abrir el documento"); }
    } else {
        leer("__URL__");
        const aviso = await esperar(() => document.querySelector(".o_dcasa_msg_error"), "el aviso de sin permiso");
        if (!aviso.textContent.includes("No tienes permiso")) { falla("aviso " + aviso.textContent); }
        if (document.body.textContent.includes("__NOMBRE__")) { falla("salió el número del documento"); }
        if (document.querySelector(".o_form_view")) { falla("no debía abrir nada"); }
        // Y un producto se sigue escaneando como siempre.
        leer("ZZT-CAMA-1");
        await esperar(() => document.querySelector(".o_dcasa_ficha_nombre"), "la tarjeta del producto");
    }
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
"""


# La cámara (2026-10-19): en el iPhone el diálogo de Odoo salía en blanco. Una cámara de mentira (un lienzo verde) y
# se mira que el video se ve: tiene tamaño, nada lo tapa en el centro y nada lo esconde.
CODIGO_CAMARA = """
(async () => {
    const esperar = async (fn, que, ms = 20000) => {
        const inicio = Date.now();
        while (Date.now() - inicio < ms) {
            const r = fn();
            if (r) { return r; }
            await new Promise((ok) => setTimeout(ok, 100));
        }
        throw new Error("Cámara: no apareció " + que);
    };
    const falla = (texto) => { throw new Error("Cámara: " + texto); };
    const lienzo = document.createElement("canvas");
    lienzo.width = 640;
    lienzo.height = 480;
    const pincel = lienzo.getContext("2d");
    const pintar = () => {
        pincel.fillStyle = "rgb(0, 170, 70)";
        pincel.fillRect(0, 0, 640, 480);
        pincel.fillStyle = "rgb(" + (Date.now() % 255) + ", 0, 0)";
        pincel.fillRect(0, 0, 8, 8);
    };
    pintar();
    setInterval(pintar, 50);
    navigator.mediaDevices.getUserMedia = async () => lienzo.captureStream(20);

    (await esperar(() => document.querySelector(".o_dcasa_escaner .o_dcasa_camara"), "el botón de la cámara")).click();
    const video = await esperar(() => document.querySelector(".o-barcode-modal video"), "el video");
    await esperar(() => document.querySelector(".o-barcode-modal .o_crop_overlay") && video.readyState >= 2
                  && !video.paused, "la imagen de la cámara");
    await new Promise((ok) => setTimeout(ok, 300));
    const caja = video.getBoundingClientRect();
    const cuerpo = document.querySelector(".o-barcode-modal .modal-body").getBoundingClientRect();
    // Guarda su proporción: llena el diálogo a lo ancho o a lo alto, nunca queda en cero.
    if (caja.width < 100 || caja.height < 100
            || (caja.width < 0.9 * cuerpo.width && caja.height < 0.9 * cuerpo.height)) {
        falla(`el video no se ve: ${caja.width}×${caja.height} de ${cuerpo.width}×${cuerpo.height}`);
    }
    const encima = document.elementFromPoint(caja.left + caja.width / 2, caja.top + caja.height / 2);
    if (encima !== video) { falla("algo tapa el centro del video: " + (encima && encima.outerHTML.slice(0, 120))); }
    for (let el = video; el && el !== document.body; el = el.parentElement) {
        const estilo = getComputedStyle(el);
        if (estilo.opacity === "0" || estilo.visibility === "hidden" || estilo.display === "none") {
            falla("escondido por " + el.className);
        }
    }
    for (const atributo of ["playsinline", "muted", "autoplay"]) {
        if (!video.hasAttribute(atributo)) { falla("al video le falta " + atributo); }
    }
    if (!video.muted || !video.playsInline) { falla("el video debe estar silenciado y dentro de la página (iOS)"); }
    const recuadro = document.querySelector(".o-barcode-modal .o_crop_overlay");
    const despues = getComputedStyle(recuadro, "::after");
    if (getComputedStyle(recuadro).mixBlendMode !== "normal" || despues.backgroundColor !== "rgba(0, 0, 0, 0)") {
        falla("el recuadro no debe pintar blanco encima de la imagen");
    }
    if (getComputedStyle(document.querySelector(".o-barcode-modal .modal-body")).backgroundColor
            === "rgb(255, 255, 255)") {
        falla("el fondo del lector no debe ser blanco");
    }
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
"""


@tagged('post_install', '-at_install')
class TestEscanerEnElNavegador(HttpCase, BarrasCommon):

    def _factura_con_qr(self):
        """Una factura de cliente publicada y la dirección de su QR (Inventario no lee facturas)."""
        cliente = self.env['res.partner'].create({'name': 'CLIENTE DEL QR'})
        factura = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': cliente.id, 'invoice_date': '2026-10-14',
            'invoice_line_ids': [(0, 0, {'product_id': self.cama.id, 'quantity': 1, 'price_unit': 10.0})]})
        factura.action_post()
        base = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        return factura, f'{base}/dcasa/doc/FAC/{factura.name}'

    def test_el_qr_de_un_documento_abre_el_documento(self):
        factura, url = self._factura_con_qr()
        codigo = CODIGO_DOCUMENTO.replace('__PERMITIDO__', 'true').replace('__URL__', url) \
            .replace('__NOMBRE__', factura.name)
        self.browser_js('/odoo/action-dcasa_barras.accion_escaner', codigo, ready='odoo.isReady',
                        login='admin', timeout=120)

    def test_el_qr_de_un_documento_sin_permiso_solo_avisa(self):
        factura, url = self._factura_con_qr()
        codigo = CODIGO_DOCUMENTO.replace('__PERMITIDO__', 'false').replace('__URL__', url) \
            .replace('__NOMBRE__', factura.name)
        self.browser_js('/odoo/action-dcasa_barras.accion_escaner', codigo, ready='odoo.isReady',
                        login='barras_vendedora', timeout=120)

    def test_escanear_y_contar(self):
        self.browser_js('/odoo/action-dcasa_barras.accion_escaner', CODIGO, ready='odoo.isReady',
                        login='admin', timeout=120)
        self.assertEqual(self.existencia(self.cama), 9)
        self.cama.invalidate_recordset()
        self.assertEqual(self.cama.list_price, 399.5, 'el precio cambiado desde «Contar»')

    def test_el_menu_esta_en_inventario_para_quien_lo_usa(self):
        menu = self.env.ref('dcasa_barras.menu_dcasa_escaner')
        self.assertEqual(menu.parent_id, self.env.ref('stock.menu_stock_root'))
        self.assertEqual(menu.group_ids, self.env.ref('stock.group_stock_user'))
        self.assertEqual(self.env.ref('dcasa_barras.menu_dcasa_barras_asignacion').group_ids,
                         self.env.ref('stock.group_stock_manager'))

    def test_escaneos_seguidos_codigo_parecido_y_cantidad_mal_escrita(self):
        self.producto('Zzsofa de prueba', 'ZZT-SOFA-3-1', precio=10, unidades=2)
        self.browser_js('/odoo/action-dcasa_barras.accion_escaner', CODIGO_PARECIDO, ready='odoo.isReady',
                        login='admin', timeout=120)

    def test_asignar_etiqueta_pasarla_quitarla_y_el_aviso_de_retirada(self):
        a = self.producto('Zzmesa A de etiqueta', 'ZZT-ETQ-A', precio=50)
        b = self.producto('Zzmesa B de etiqueta', 'ZZT-ETQ-B', precio=60)
        c = self.producto('Zzmesa C de etiqueta', 'ZZT-ETQ-C', precio=70)
        self.browser_js('/odoo/action-dcasa_barras.accion_escaner', CODIGO_ASIGNAR, ready='odoo.isReady',
                        login='admin', timeout=240)
        for producto in (a, b, c):
            producto.invalidate_recordset()
        self.assertEqual((a.barcode, b.barcode, c.barcode), (False, False, False), 'al final la etiqueta quedó quitada')
        acciones = self.env['dcasa.barras.etiqueta'].search([('codigo', '=', 'DC9500')], order='id')
        self.assertEqual([(f.accion, f.producto_id) for f in acciones],
                         [('asignada', a), ('retirada', a), ('asignada', c), ('retirada', c),
                          ('asignada', b), ('retirada', b)])
        self.assertFalse(self.env['dcasa.barras.etiqueta'].search([('codigo', 'in', ('DC9501', 'DC9502'))]),
                         'las etiquetas que solo se escanearon no se asignaron')

    def test_la_vendedora_no_ve_la_pestana_de_asignar(self):
        self.browser_js('/odoo/action-dcasa_barras.accion_escaner', CODIGO_SIN_ASIGNAR, ready='odoo.isReady',
                        login='barras_vendedora', timeout=120)

    def test_la_camara_se_ve_en_el_celular_y_en_la_compu(self):
        for ancho in ('390x844', '1440x900'):
            with self.subTest(ancho=ancho):
                self.browser_size = ancho
                self.browser_js('/odoo/action-dcasa_barras.accion_escaner', CODIGO_CAMARA, ready='odoo.isReady',
                                login='admin', timeout=120)
