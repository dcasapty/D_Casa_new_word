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
    const campo = await esperar(() => document.querySelector(".o_dcasa_escaner_texto"), "el cuadro del lector");

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

    // El foco pasa a la búsqueda del producto; se elige el producto y se confirma con Enter en el botón.
    const busqueda = await esperar(
        () => document.querySelector(".o_dcasa_busqueda_producto"), "la búsqueda del producto");
    await espera(150);
    if (document.activeElement !== busqueda) { falla("el foco debe pasar a la búsqueda del producto"); }
    escribir(busqueda, "zzmesa a");
    enter(busqueda);
    const opcion = await esperar(() => [...document.querySelectorAll(".o_dcasa_opciones_etiqueta .o_dcasa_opcion")]
        .find((o) => o.textContent.includes("Zzmesa A")), "el producto en la lista");
    opcion.click();
    const confirmar = await esperar(() => document.querySelector(".o_dcasa_asignar_confirmar"), "la confirmación");
    if (!confirmar.textContent.includes("DC9500")) {
        falla("la confirmación debe decir la etiqueta: " + confirmar.textContent);
    }
    await espera(150);
    if (document.activeElement.textContent.trim() !== "Asignar etiqueta") {
        falla("el foco debe estar en Asignar etiqueta");
    }
    boton("Asignar etiqueta").click();
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
    const busqueda2 = await esperar(() => document.querySelector(".o_dcasa_busqueda_producto"), "la búsqueda otra vez");
    escribir(busqueda2, "zzmesa b");
    enter(busqueda2);
    (await esperar(() => [...document.querySelectorAll(".o_dcasa_opciones_etiqueta .o_dcasa_opcion")]
        .find((o) => o.textContent.includes("Zzmesa B")), "el otro producto")).click();
    const confirmar2 = await esperar(() => document.querySelector(".o_dcasa_asignar_confirmar"), "la confirmación 2");
    if (!confirmar2.textContent.includes("Zzmesa A") || !confirmar2.textContent.includes("sin etiqueta")) {
        falla("debe avisar que el anterior se queda sin etiqueta: " + confirmar2.textContent);
    }
    boton("Asignar etiqueta").click();
    const ok2 = await esperar(() => (document.querySelector(".o_dcasa_msg_ok") || {}).textContent?.includes("Zzmesa A"),
                              "el aviso de etiqueta pasada");
    if (!ok2) { falla("aviso de pasarla"); }

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


@tagged('post_install', '-at_install')
class TestEscanerEnElNavegador(HttpCase, BarrasCommon):

    def test_escanear_y_contar(self):
        self.browser_js('/odoo/action-dcasa_barras.accion_escaner', CODIGO, ready='odoo.isReady',
                        login='admin', timeout=120)
        self.assertEqual(self.existencia(self.cama), 9)

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
        self.browser_js('/odoo/action-dcasa_barras.accion_escaner', CODIGO_ASIGNAR, ready='odoo.isReady',
                        login='admin', timeout=180)
        a.invalidate_recordset()
        b.invalidate_recordset()
        self.assertEqual((a.barcode, b.barcode), (False, False), 'al final la etiqueta quedó quitada')
        acciones = self.env['dcasa.barras.etiqueta'].search([('codigo', '=', 'DC9500')], order='id')
        self.assertEqual([(f.accion, f.producto_id) for f in acciones],
                         [('asignada', a), ('retirada', a), ('asignada', b), ('retirada', b)])
