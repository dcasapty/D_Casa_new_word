"""Las fotos y Marketing en un navegador de verdad, a tamaño celular (390×844) y computadora (1440×900).

* Ficha del producto: tocar la foto abre el visor grande; zoom con botones y pellizcando; pasar de foto con la flecha
  y deslizando; reemplazar con un archivo; girar; recortar (Cropper.js de Odoo); poner como principal; la galería:
  subir varias a la vez, ordenar con las flechas y arrastrando (computadora), quitar con confirmación; al cerrar, la
  ficha muestra la foto nueva. Sin scroll de costado.
* Quien no puede editar el producto (bodega) solo ve y descarga.
* Lista de Productos y Escáner: la foto también se abre en grande.
* Marketing: las secciones, el periodo, la categoría y «Fotos» (buscar por código, Enter abre la galería, subir).
"""
from odoo.tests import HttpCase, tagged

from .comun import MarketingCommon, foto

AYUDAS_JS = r"""
    const esperar = async (fn, que, ms = 25000) => {
        const inicio = Date.now();
        while (Date.now() - inicio < ms) {
            const r = fn();
            if (r) { return r; }
            await new Promise((ok) => setTimeout(ok, 100));
        }
        throw new Error("Fotos: no apareció " + que);
    };
    const pausa = (ms) => new Promise((ok) => setTimeout(ok, ms));
    const falla = (texto) => { throw new Error("Fotos: " + texto); };
    const dialogo = () => document.querySelector(".o_dialog:not(.o_inactive_modal) .o_dcasa_fotos");
    const boton = (texto, raiz = dialogo()) => [...(raiz || document).querySelectorAll("button, a")]
        .find((b) => b.textContent.trim().replace(/\s+/g, " ") === texto);
    const mensajeOk = (texto) => esperar(
        () => [...document.querySelectorAll(".o_dcasa_fotos_mensaje_ok")].find((m) => m.textContent.includes(texto)),
        "el aviso «" + texto + "»");
    const contador = () => (document.querySelector(".o_dcasa_fotos_contador") || {})
        .textContent?.replace(/\s+/g, " ").trim();
    const escala = () => {
        const m = /scale\(([\d.]+)\)/.exec(document.querySelector(".o_dcasa_fotos_grande").getAttribute("style"));
        return m ? parseFloat(m[1]) : 1;
    };
    const archivo = (nombre, color, ancho = 320, alto = 240) => new Promise((ok) => {
        const lienzo = document.createElement("canvas");
        lienzo.width = ancho;
        lienzo.height = alto;
        const g = lienzo.getContext("2d");
        g.fillStyle = color;
        g.fillRect(0, 0, ancho, alto);
        lienzo.toBlob((b) => ok(new File([b], nombre, { type: "image/jpeg" })), "image/jpeg", 0.92);
    });
    const poner = (entrada, archivos) => {
        const dt = new DataTransfer();
        for (const a of archivos) { dt.items.add(a); }
        entrada.files = dt.files;
        entrada.dispatchEvent(new Event("change", { bubbles: true }));
    };
    const puntero = (el, tipo, id, x, y, extra = {}) => el.dispatchEvent(new PointerEvent(tipo, {
        pointerId: id, clientX: x, clientY: y, bubbles: true, cancelable: true, pointerType: "touch",
        isPrimary: id === 1, button: 0, buttons: 1, ...extra }));
    const sinScrollDeCostado = (que) => {
        if (document.documentElement.scrollWidth > window.innerWidth + 1) { falla("scroll de costado en " + que); }
        for (const el of document.querySelectorAll(".o_dcasa_fotos_raiz, .o_dcasa_mk_contenido")) {
            if (el.scrollWidth > el.clientWidth + 1) { falla("algo se sale de costado en " + que); }
        }
    };
"""

FICHA_JS = """
(async () => {
""" + AYUDAS_JS + r"""
    const foto = await esperar(() => document.querySelector(".o_form_view .o_dcasa_foto_boton"), "la foto de la ficha");
    const srcAntes = foto.querySelector("img").getAttribute("src");
    foto.click();
    await esperar(() => document.querySelector(".o_dcasa_fotos_grande"), "el visor grande");
    await esperar(() => contador() === "1 de 3", "«1 de 3»");
    // El visor ocupa casi toda la pantalla.
    const caja = dialogo().getBoundingClientRect();
    if (caja.width < window.innerWidth * 0.9 || caja.height < window.innerHeight * 0.85) {
        falla("el visor debe ser casi de pantalla completa: " + caja.width + "x" + caja.height);
    }
    sinScrollDeCostado("el visor");
    for (const texto of ["Reemplazar", "Recortar", "Girar", "Quitar", "Descargar"]) {
        if (!boton(texto)) { falla("falta la acción " + texto); }
    }
    if (!boton("Es la principal") || !boton("Es la principal").disabled) {
        falla("la principal no se vuelve a elegir");
    }
    // Zoom: botón, pellizco y doble toque.
    document.querySelector('.o_dcasa_fotos_zoom button[aria-label="Acercar"]').click();
    await esperar(() => escala() > 1.4, "el zoom con el botón");
    document.querySelector('.o_dcasa_fotos_zoom button[aria-label="Alejar"]').click();
    await esperar(() => escala() === 1, "volver a 1");
    const escenario = document.querySelector(".o_dcasa_fotos_escenario");
    const r = escenario.getBoundingClientRect();
    const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    puntero(escenario, "pointerdown", 1, cx - 40, cy);
    puntero(escenario, "pointerdown", 2, cx + 40, cy);
    puntero(escenario, "pointermove", 2, cx + 120, cy);
    await esperar(() => escala() > 1.9, "el pellizco agranda");
    puntero(escenario, "pointerup", 2, cx + 120, cy);
    puntero(escenario, "pointerup", 1, cx - 40, cy);
    escenario.dispatchEvent(new MouseEvent("dblclick", { bubbles: true }));
    await esperar(() => escala() === 1, "el doble toque vuelve a 1");
    // Pasar de foto: flecha y deslizar.
    document.querySelector(".o_dcasa_fotos_flecha_der").click();
    await esperar(() => contador() === "2 de 3", "la flecha pasa a la 2");
    puntero(escenario, "pointerdown", 7, cx + 100, cy);
    puntero(escenario, "pointermove", 7, cx - 60, cy);
    puntero(escenario, "pointerup", 7, cx - 60, cy);
    await esperar(() => contador() === "3 de 3", "deslizar pasa a la 3");
    // Reemplazar la 3 con un archivo.
    poner(document.querySelector(".o_dcasa_fotos_raiz input[type=file]:not([multiple]):not([capture])"),
          [await archivo("nueva.jpg", "#FED00F", 400, 300)]);
    await mensajeOk("reemplazada");
    // Girar.
    boton("Girar").click();
    await mensajeOk("girada");
    // Recortar (Cropper.js de Odoo) en cuadrado.
    boton("Recortar").click();
    await esperar(() => document.querySelector(".cropper-container .cropper-crop-box"), "el recortador");
    boton("Cuadrada").click();
    await pausa(300);
    boton("Guardar recorte").click();
    await mensajeOk("recortada");
    await esperar(() => document.querySelector(".o_dcasa_fotos_grande") && contador() === "3 de 3",
                  "de vuelta al visor");
    // Poner como principal.
    boton("Hacer principal").click();
    await mensajeOk("principal");
    await esperar(() => contador() === "1 de 3", "la principal es la 1");
    // La galería: subir varias, ordenar, quitar.
    boton("Todas").click();
    await esperar(() => document.querySelectorAll(".o_dcasa_fotos_tarjeta").length === 3, "las 3 tarjetas");
    sinScrollDeCostado("la galería");
    poner(document.querySelector(".o_dcasa_fotos_raiz input[type=file][multiple]"),
          [await archivo("a.jpg", "#1340B1"), await archivo("b.jpg", "#0B1F52")]);
    await mensajeOk("2 fotos subidas");
    await esperar(() => document.querySelectorAll(".o_dcasa_fotos_tarjeta").length === 5, "las 5 tarjetas");
    const claves = () => [...document.querySelectorAll(".o_dcasa_fotos_tarjeta")].map((t) => t.dataset.clave);
    let antes = claves();
    document.querySelectorAll('.o_dcasa_fotos_tarjeta button[aria-label="Mover después"]')[1].click();
    await mensajeOk("orden quedó guardado");
    let ahora = claves();
    if (ahora[1] !== antes[2] || ahora[2] !== antes[1]) { falla("la flecha no cambió el orden: " + ahora); }
    if (window.innerWidth > 800) {
        // Arrastrar la 4 encima de la 1 (computadora): queda segunda, justo después de la principal.
        antes = claves();
        const tarjetas = document.querySelectorAll(".o_dcasa_fotos_tarjeta");
        const origen = tarjetas[3].querySelector(".o_dcasa_fotos_tarjeta_foto");
        const ro = origen.getBoundingClientRect();
        const ox = ro.left + ro.width / 2, oy = ro.top + ro.height / 2;
        const raton = { pointerType: "mouse" };
        puntero(origen, "pointerdown", 11, ox, oy, raton);
        puntero(document, "pointermove", 11, ox + 20, oy + 20, raton);
        await pausa(100);
        puntero(document, "pointermove", 11, ox - 200, oy - 100, raton);
        await pausa(100);
        tarjetas[0].dispatchEvent(new PointerEvent("pointerenter", { pointerId: 11, pointerType: "mouse" }));
        await pausa(100);
        puntero(document, "pointerup", 11, ox - 200, oy - 100, { ...raton, buttons: 0 });
        await mensajeOk("orden quedó guardado");
        await esperar(() => claves().join() === [antes[0], antes[3], antes[1], antes[2], antes[4]].join(),
                      "la 4 en el segundo lugar: " + antes);
    }
    // Quitar la última, con confirmación.
    const quitar = [...document.querySelectorAll('.o_dcasa_fotos_tarjeta button[aria-label="Quitar"]')].pop();
    quitar.click();
    const si = await esperar(() => boton("Sí, quitarla", document.querySelector(".modal:not(.o_inactive_modal)")),
                             "la confirmación de quitar");
    si.click();
    await mensajeOk("se quitó");
    await esperar(() => document.querySelectorAll(".o_dcasa_fotos_tarjeta").length === 4, "las 4 tarjetas");
    // Ver una desde la galería y cerrar: la ficha muestra la foto nueva.
    document.querySelectorAll(".o_dcasa_fotos_tarjeta_foto")[1].click();
    await esperar(() => contador() === "2 de 4", "la 2 en grande");
    boton("Cerrar") ? boton("Cerrar").click() : document.querySelector(".o_dcasa_fotos_cerrar").click();
    await esperar(() => !document.querySelector(".o_dcasa_fotos"), "la ventana cerrada");
    await esperar(() => document.querySelector(".o_form_view .o_dcasa_foto_boton img").getAttribute("src") !== srcAntes,
                  "la ficha con la foto nueva");
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
"""

SOLO_VER_JS = """
(async () => {
""" + AYUDAS_JS + r"""
    const foto = await esperar(() => document.querySelector(".o_form_view .o_dcasa_foto_boton"), "la foto de la ficha");
    foto.click();
    await esperar(() => document.querySelector(".o_dcasa_fotos_grande"), "el visor grande");
    if (!dialogo().textContent.includes("Solo puedes verlas")) { falla("debe decir que solo puede verlas"); }
    for (const texto of ["Reemplazar", "Recortar", "Girar", "Quitar", "Hacer principal"]) {
        if (boton(texto)) { falla("quien no edita el producto no debe ver " + texto); }
    }
    if (!boton("Descargar")) { falla("descargar sí"); }
    boton("Todas").click();
    await esperar(() => document.querySelectorAll(".o_dcasa_fotos_tarjeta").length === 2, "las tarjetas");
    if (document.querySelector(".o_dcasa_fotos_subir, .o_dcasa_fotos_tarjeta_botones")) {
        falla("sin subir ni botones de ordenar");
    }
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
"""

LISTA_JS = """
(async () => {
""" + AYUDAS_JS + r"""
    const buscar = await esperar(() => document.querySelector(".o_searchview_input"), "el buscador de la lista");
    buscar.value = "ZZMK-NAV-SOFA";
    buscar.dispatchEvent(new Event("input", { bubbles: true }));
    await pausa(300);
    buscar.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
    const fila = await esperar(() => [...document.querySelectorAll(".o_data_row")]
        .find((f) => f.textContent.includes("ZZMK SOFÁ DEL NAVEGADOR")), "la fila del producto");
    fila.querySelector(".o_dcasa_foto_boton").click();
    await esperar(() => document.querySelector(".o_dcasa_fotos_grande"), "el visor desde la lista");
    if (document.querySelector(".o_form_view")) { falla("tocar la foto no abre el producto"); }
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
"""

ESCANER_JS = """
(async () => {
""" + AYUDAS_JS + r"""
    const campo = await esperar(() => document.querySelector(".o_dcasa_escaner_texto"), "el cuadro del lector");
    campo.value = "ZZMK-NAV-SOFA";
    campo.dispatchEvent(new Event("input", { bubbles: true }));
    campo.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
    const foto = await esperar(() => document.querySelector(".o_dcasa_ficha_foto_boton"), "la foto en el Escáner");
    foto.click();
    await esperar(() => contador() === "1 de 2", "el visor desde el Escáner");
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
"""

MARKETING_JS = """
(async () => {
""" + AYUDAS_JS + r"""
    const raiz = await esperar(() => document.querySelector(".o_dcasa_mk_rejilla"), "Marketing");
    const titulos = [...document.querySelectorAll(".o_dcasa_mk_seccion h2")].map((h) => h.textContent.trim());
    for (const t of ["Stock", "Más vendidos", "Mayor movimiento", "Más quietos", "Fotos"]) {
        if (!titulos.some((x) => x.startsWith(t))) { falla("falta la sección " + t + ": " + titulos); }
    }
    sinScrollDeCostado("Marketing");
    // Baja con scroll: Odoo le pone `overflow: hidden` a todo `.o_action` (la dueña, 23 oct: «no se puede hacer
    // scroll»).
    const pagina = document.querySelector(".o_dcasa_mk");
    if (!["auto", "scroll"].includes(getComputedStyle(pagina).overflowY)) { falla("la página no tiene scroll"); }
    if (pagina.scrollHeight <= pagina.clientHeight + 1) { falla("todo cabe sin bajar: la prueba no mide el scroll"); }
    pagina.scrollTop = 300;
    await pausa(50);
    if (pagina.scrollTop === 0) { falla("la página no baja con scroll"); }
    pagina.scrollTop = 0;
    // Periodo.
    boton("15 días", document).click();
    await esperar(() => document.querySelector(".o_dcasa_mk_rango").textContent.includes("Últimos 15 días"), "15 días");
    // Categoría de la prueba: el stock y lo vendido son de ella.
    const chip = await esperar(() => [...document.querySelectorAll(".o_dcasa_mk_categorias .o_dcasa_mk_chip")]
        .find((c) => c.textContent.includes("ZZMK Categoría de prueba")), "la categoría de la prueba");
    chip.click();
    await esperar(() => document.querySelector(".o_dcasa_mk_stock h2").textContent.includes("ZZMK Categoría de prueba")
                  && !document.querySelector(".o_dcasa_mk_actualizando"), "el stock de la categoría");
    await esperar(() => document.querySelector(".o_dcasa_mk_vendidos").textContent.includes("ZZMK SOFÁ DEL NAVEGADOR"),
                  "lo más vendido de la categoría");
    if (!document.querySelector(".o_dcasa_mk_quietos").textContent.includes("ZZMK SILLA SIN FOTO")) {
        falla("la silla con stock y sin ventas es de los quietos");
    }
    // Ir a «Fotos» con el índice y buscar por código: Enter abre su galería.
    boton("Fotos", document.querySelector(".o_dcasa_mk_indice")).click();
    const buscar = document.querySelector(".o_dcasa_mk_buscar_texto");
    await esperar(() => [...document.querySelectorAll(".o_dcasa_mk_lista_fotos .o_dcasa_mk_fila")]
        .some((f) => f.textContent.includes("ZZMK SILLA SIN FOTO") && f.textContent.includes("Sin foto")),
        "la silla marcada «Sin foto»");
    buscar.value = "ZZMK-NAV-SILLA";
    buscar.dispatchEvent(new Event("input", { bubbles: true }));
    buscar.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
    await esperar(() => dialogo() && document.querySelector(".o_dcasa_fotos_subir"), "la galería para subir");
    poner(document.querySelector(".o_dcasa_fotos_raiz input[type=file][multiple]"),
          [await archivo("silla.jpg", "#1340B1")]);
    await mensajeOk("quedó subida");
    document.querySelector(".o_dcasa_fotos_cerrar").click();
    await esperar(() => [...document.querySelectorAll(".o_dcasa_mk_lista_fotos .o_dcasa_mk_fila")]
        .some((f) => f.textContent.includes("ZZMK SILLA SIN FOTO") && f.textContent.includes("1 foto")),
        "la silla ya con 1 foto");
    sinScrollDeCostado("Marketing al final");
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
"""

TAMANOS = ('390x844', '1440x900')


@tagged('post_install', '-at_install')
class TestFotosEnElNavegador(MarketingCommon, HttpCase):

    def setUp(self):
        super().setUp()
        self.gerencia.write({'password': 'zzmk_gerencia'})
        # El nombre se guarda en MAYÚSCULAS (F5): la pantalla (interna) lo muestra así.
        self.sofa = self.producto('ZZMK Sofá del navegador', 'ZZMK-NAV-SOFA', stock=6, con_foto=True, extras=2)
        self.silla = self.producto('ZZMK Silla sin foto', 'ZZMK-NAV-SILLA', stock=4)
        self.env['product.product'].flush_model()

    def url_ficha(self, accion='sale.product_template_action'):
        return f'/odoo/action-{accion}/{self.sofa.id}'

    def test_ver_y_editar_las_fotos_desde_la_ficha(self):
        for tamano in TAMANOS:
            with self.subTest(tamano=tamano):
                self.sofa.product_template_image_ids.unlink()
                self.sofa.image_1920 = False
                self.sofa.dcasa_fotos_subir([{'nombre': 'a', 'datos': foto(color=(19, 64, 177))},
                                             {'nombre': 'b', 'datos': foto(color=(200, 30, 30))},
                                             {'nombre': 'c', 'datos': foto(color=(30, 160, 60))}])
                self.browser_size = tamano
                self.browser_js(self.url_ficha(), FICHA_JS, ready='odoo.isReady', login='zzmk_gerencia', timeout=240)
                fotos = self.sofa.dcasa_fotos()['fotos']
                self.assertEqual(len(fotos), 4, 'tres, más dos subidas, menos una quitada')
                self.assertEqual(fotos[0]['clave'], 'principal')

    def test_quien_no_puede_editar_el_producto_solo_ve(self):
        self.bodega.write({'password': 'zzmk_bodega'})
        self.sofa.product_template_image_ids[1:].unlink()
        self.browser_size = '390x844'
        self.browser_js(self.url_ficha('stock.product_template_action_product'), SOLO_VER_JS, ready='odoo.isReady',
                        login='zzmk_bodega', timeout=120)
        self.assertEqual(len(self.sofa.dcasa_fotos()['fotos']), 2, 'nada cambió')

    def test_la_foto_de_la_lista_y_del_escaner_se_abre_en_grande(self):
        self.sofa.product_template_image_ids[1:].unlink()
        self.browser_size = '1440x900'
        self.browser_js('/odoo/action-sale.product_template_action', LISTA_JS, ready='odoo.isReady',
                        login='zzmk_gerencia', timeout=120)
        self.browser_js('/odoo/action-dcasa_barras.accion_escaner', ESCANER_JS, ready='odoo.isReady',
                        login='zzmk_gerencia', timeout=120)

    def test_marketing_en_celular_y_computadora(self):
        for tamano in TAMANOS:
            with self.subTest(tamano=tamano):
                if self.silla.image_1920:
                    self.silla.dcasa_fotos_quitar('principal')
                self.facturar(self.sofa, 2, dias_atras=1)
                self.browser_size = tamano
                self.browser_js('/odoo/action-dcasa_marketing.accion_marketing', MARKETING_JS, ready='odoo.isReady',
                                login='zzmk_gerencia', timeout=180)
                self.assertTrue(self.silla.image_1920, 'la foto quedó subida a la silla')
