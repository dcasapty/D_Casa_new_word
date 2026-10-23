"""«Armar combo cama + colchón» en un navegador de verdad, a tamaño celular y computadora: armar, cambiar el colchón y
quitar el combo, sin scroll de lado. Y la página que ve el cliente (el enlace de la cotización) dice «Combo»."""
import re
from html import unescape

from odoo import Command
from odoo.addons.dcasa_catalogo.catalogo import atributo_tamano
from odoo.tests import HttpCase, new_test_user, tagged

CODIGO = """
(async () => {
    const esperar = async (fn, que, ms = 20000) => {
        const inicio = Date.now();
        while (Date.now() - inicio < ms) {
            const r = fn();
            if (r) { return r; }
            await new Promise((ok) => setTimeout(ok, 100));
        }
        throw new Error("Armar combo: no apareció " + que);
    };
    const falla = (texto) => { throw new Error("Armar combo: " + texto); };
    const tarjetas = (clase) => [...document.querySelectorAll(clase)];
    const tarjeta = (clase, texto) => tarjetas(clase).find((t) => t.textContent.includes(texto));
    const sinScrollDeLado = (donde) => {
        const raiz = document.documentElement;
        if (raiz.scrollWidth > window.innerWidth + 1) {
            falla(`scroll de lado en ${donde}: ${raiz.scrollWidth} > ${window.innerWidth}`);
        }
        const panel = document.querySelector(".o_dcasa_armar_combo");
        if (panel && panel.scrollWidth > panel.clientWidth + 1) {
            falla(`el panel se sale de lado en ${donde}: ${panel.scrollWidth} > ${panel.clientWidth}`);
        }
    };

    // 1. El botón está junto a «Agregar un producto» y abre el panel en el paso de la cama.
    const boton = await esperar(() => [...document.querySelectorAll(".o_dcasa_btn_armar_combo")]
        .find((b) => b.offsetParent !== null), "el botón «Armar combo»");
    boton.click();
    const buscador = await esperar(() => document.querySelector(".o_dcasa_combo_buscar"), "el buscador de camas");
    buscador.value = "ZZNAV KING";
    buscador.dispatchEvent(new Event("input", { bubbles: true }));
    const cama = await esperar(() => tarjeta(".o_dcasa_combo_tarjeta_cama", "CAMA ZZNAV KING"), "la cama buscada");
    if (!cama.textContent.includes("King") || !cama.textContent.includes("disponible")) {
        falla("la tarjeta de la cama debe decir medida y existencia: " + cama.textContent);
    }
    sinScrollDeLado("las camas");
    cama.click();

    // 2. Solo los colchones de su medida y con existencia, con precio normal, en combo y el ahorro.
    await esperar(() => tarjeta(".o_dcasa_combo_tarjeta_colchon", "COLCHON ZZNAV CON PRECIO"), "los colchones king");
    const nombres = tarjetas(".o_dcasa_combo_tarjeta_colchon").map((t) => t.textContent).join(" | ");
    if (nombres.includes("COLCHON ZZNAV QUEEN")) { falla("salió un colchón de otra medida"); }
    if (nombres.includes("COLCHON ZZNAV AGOTADO")) { falla("salió un colchón sin existencia"); }
    const conPrecio = tarjeta(".o_dcasa_combo_tarjeta_colchon", "COLCHON ZZNAV CON PRECIO");
    if (!conPrecio.textContent.includes("300.00") || !conPrecio.textContent.includes("260.00")
            || !conPrecio.textContent.includes("Ahorra")) {
        falla("el colchón debe mostrar precio normal, en combo y ahorro: " + conPrecio.textContent);
    }
    if (!tarjeta(".o_dcasa_combo_tarjeta_colchon", "COLCHON ZZNAV SIN PRECIO").textContent
            .includes("Sin precio en combo")) {
        falla("el colchón sin precio en combo debe decirlo");
    }
    sinScrollDeLado("los colchones");
    conPrecio.click();

    // 3. El combo queda en la cotización, con su total y lo que ahorra el cliente.
    const combo = await esperar(() => document.querySelector(".o_dcasa_combo_card"), "el combo agregado");
    if (!combo.textContent.includes("Ahorra") || !combo.textContent.includes("40.00")) {
        falla("el combo debe decir cuánto ahorra: " + combo.textContent);
    }
    if (!combo.textContent.includes("660.00")) { falla("el total del combo debe ser 660.00: " + combo.textContent); }
    sinScrollDeLado("el combo");

    // 4. Cambiar el colchón: el que tiene ahora sale marcado y no se puede volver a escoger.
    combo.querySelector(".o_dcasa_combo_cambiar_colchon").click();
    const actual = await esperar(() => document.querySelector(".o_dcasa_combo_tarjeta_colchon.o_actual"),
                                 "el colchón actual marcado");
    if (!actual.disabled) { falla("el colchón actual no debe poder escogerse otra vez"); }
    tarjeta(".o_dcasa_combo_tarjeta_colchon", "COLCHON ZZNAV SIN PRECIO").click();
    await esperar(() => document.querySelector(".o_dcasa_combo_card")?.textContent.includes("COLCHON ZZNAV SIN PRECIO"),
                  "el colchón nuevo en el combo");
    if (!document.querySelector(".o_dcasa_combo_card").textContent.includes("sin precio en combo")) {
        falla("el combo con un colchón sin precio en combo debe decir que va a precio normal");
    }

    // 5. Quitar el combo y cerrar.
    document.querySelector(".o_dcasa_combo_quitar").click();
    await esperar(() => !document.querySelector(".o_dcasa_combo_card")
                  && document.querySelector(".o_dcasa_combo_vacio"), "el panel sin combos");
    document.querySelector(".o_dcasa_combo_listo").click();
    await esperar(() => !document.querySelector(".o_dcasa_armar_combo"), "que se cierre el panel");
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
"""

ARMAR_Y_DEJAR = """
(async () => {
    const esperar = async (fn, que, ms = 20000) => {
        const inicio = Date.now();
        while (Date.now() - inicio < ms) {
            const r = fn();
            if (r) { return r; }
            await new Promise((ok) => setTimeout(ok, 100));
        }
        throw new Error("Armar combo: no apareció " + que);
    };
    (await esperar(() => [...document.querySelectorAll(".o_dcasa_btn_armar_combo")]
        .find((b) => b.offsetParent !== null), "el botón")).click();
    // Con el catálogo real cargado hay cientos de camas: se busca la de la prueba, como lo haría la vendedora.
    const buscador = await esperar(() => document.querySelector(".o_dcasa_combo_buscar"), "el buscador de camas");
    buscador.value = "ZZNAV KING";
    buscador.dispatchEvent(new Event("input", { bubbles: true }));
    (await esperar(() => [...document.querySelectorAll(".o_dcasa_combo_tarjeta_cama")]
        .find((t) => t.textContent.includes("CAMA ZZNAV KING")), "la cama")).click();
    (await esperar(() => [...document.querySelectorAll(".o_dcasa_combo_tarjeta_colchon")]
        .find((t) => t.textContent.includes("COLCHON ZZNAV CON PRECIO")), "el colchón")).click();
    await esperar(() => document.querySelector(".o_dcasa_combo_card"), "el combo");
    document.querySelector(".o_dcasa_combo_listo").click();
    // La cotización se vuelve a leer al cerrar: las dos líneas, con la marca «Combo».
    await esperar(() => [...document.querySelectorAll(".o_dcasa_combo_texto")]
        .some((el) => el.textContent.includes("ahorras $40.00")), "la marca «Combo · ahorras» en la línea");
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
"""


@tagged('post_install', '-at_install')
class TestArmarComboEnElNavegador(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        itbms = cls.env.company.account_sale_tax_id
        ubicacion = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1).lot_stock_id
        _atributo, _valores = atributo_tamano(cls.env)
        base = {'type': 'consu', 'is_storable': True, 'taxes_id': [Command.set(itbms.ids)]}

        def producto(nombre, precio, existencias, combo=0.0):
            variante = cls.env['product.product'].create({**base, 'name': nombre, 'list_price': precio})
            if combo:
                variante.dcasa_precio_combo = combo
            if existencias:
                cls.env['stock.quant'].with_context(inventory_mode=True).create({
                    'product_id': variante.id, 'location_id': ubicacion.id,
                    'inventory_quantity': existencias})._apply_inventory()
            return variante
        cls.cama = producto('CAMA ZZNAV KING', 400.0, 4)
        cls.con_precio = producto('COLCHON ZZNAV CON PRECIO KING', 300.0, 3, combo=260.0)
        cls.sin_precio = producto('COLCHON ZZNAV SIN PRECIO KING', 280.0, 2)
        cls.agotado = producto('COLCHON ZZNAV AGOTADO KING', 250.0, 0, combo=200.0)
        cls.otra_medida = producto('COLCHON ZZNAV QUEEN', 240.0, 5, combo=200.0)
        cls.vendedora = new_test_user(cls.env, login='combo_nav_vendedora', groups='dcasa_base.group_vendedora')
        cls.cliente = cls.env['res.partner'].create({'name': 'CLIENTE DE PRUEBA COMBOS NAVEGADOR'})

    def _orden(self):
        return self.env['sale.order'].with_user(self.vendedora).create({'partner_id': self.cliente.id})

    def test_armar_cambiar_y_quitar_en_celular_y_computadora(self):
        for tamano in ('390x844', '1440x900'):
            with self.subTest(tamano=tamano):
                self.browser_size = tamano
                orden = self._orden()
                self.browser_js(f'/odoo/sales/{orden.id}', CODIGO, ready='odoo.isReady',
                                login='combo_nav_vendedora', timeout=180)
                self.assertFalse(orden.order_line, 'Se quitó el combo: la cotización queda vacía')

    def test_el_combo_queda_en_la_cotizacion_con_su_precio(self):
        orden = self._orden()
        self.browser_js(f'/odoo/sales/{orden.id}', ARMAR_Y_DEJAR, ready='odoo.isReady',
                        login='combo_nav_vendedora', timeout=180)
        colchon = orden.order_line.filtered(lambda ln: ln.product_id == self.con_precio)
        self.assertEqual((colchon.price_unit, colchon.dcasa_combo_cama_id.product_id), (260.0, self.cama))

    def test_la_pagina_del_cliente_dice_combo_y_el_descuento_en_su_renglon(self):
        """Como el papel (decisión de la dueña, 2026-10-23): el colchón a su precio normal y debajo «Descuento combo
        cama + colchón −$40.00»."""
        orden = self.env['sale.order'].create({
            'partner_id': self.cliente.id,
            'order_line': [Command.create({'product_id': p.id}) for p in (self.cama, self.con_precio)]})
        respuesta = self.url_open(orden.get_portal_url())
        self.assertEqual(respuesta.status_code, 200)
        texto = ' '.join(unescape(re.sub(r'<[^>]+>', ' ', respuesta.text)).replace('\xa0', ' ').split())
        self.assertEqual(texto.count('Combo cama + colchón'), 2, 'Las dos piezas')
        self.assertIn('Descuento combo cama + colchón −$ 40.00', texto)
        self.assertIn('$ 300.00', texto, 'El colchón a su precio normal')
        self.assertNotIn('ahorras', texto)
