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
