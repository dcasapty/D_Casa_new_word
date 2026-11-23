"""La pantalla «Movimiento» en un navegador de verdad, a tamaño celular (390×844) y computadora (1440×900).

* Gerencia: los botones de periodo y de comparación, el resumen con dinero, las listas (los que más venden, bajaron, se
  enfriaron, quietos), una fila con sus cifras exactas, «Elegir fechas», el enlace del Excel con lo que se está viendo,
  los enlaces de ida y vuelta con Rotación, el gráfico, sin scroll de costado y con scroll hacia abajo.
* Rol Marketing: llega desde el botón «Comparar periodos» de la pantalla Marketing y no ve un solo dólar.
"""
from datetime import timedelta

from odoo.tests import HttpCase, tagged

from .test_movimiento import MovimientoDatos

AYUDAS_JS = r"""
    const esperar = async (fn, que, ms = 25000) => {
        const inicio = Date.now();
        while (Date.now() - inicio < ms) {
            const r = fn();
            if (r) { return r; }
            await new Promise((ok) => setTimeout(ok, 100));
        }
        throw new Error("Movimiento: no apareció " + que);
    };
    const pausa = (ms) => new Promise((ok) => setTimeout(ok, ms));
    const falla = (texto) => { throw new Error("Movimiento: " + texto); };
    const quieta = () => !document.querySelector(".o_dcasa_mk_actualizando");
    const plano = (el) => el.textContent.replace(/\s+/g, " ").trim();
    const filas = () => [...document.querySelectorAll(".o_dcasa_mv_fila")].map((f) => f.querySelector(".o_dcasa_mk_nombre strong").textContent.trim());
    const sinScrollDeCostado = (que) => {
        if (document.documentElement.scrollWidth > window.innerWidth + 1) { falla("scroll de costado en " + que); }
        for (const el of document.querySelectorAll(".o_dcasa_mk_contenido, .o_dcasa_mv_fila, .o_dcasa_mv_resumen, .o_dcasa_mv_periodos, .o_dcasa_mv_grafico")) {
            if (el.scrollWidth > el.clientWidth + 1) { falla("algo se sale de costado en " + que + ": " + el.className); }
        }
    };
    const escribir = (entrada, valor) => {
        entrada.value = valor;
        entrada.dispatchEvent(new Event("input", { bubbles: true }));
    };
    const poner = (entrada, valor) => {
        entrada.value = valor;
        entrada.dispatchEvent(new Event("change", { bubbles: true }));
    };
    const chipDe = (zona, texto) => [...document.querySelectorAll(zona + " .o_dcasa_mk_chip")]
        .find((c) => c.textContent.trim().replace(/\s+/g, " ").startsWith(texto));
    const vista = (texto) => chipDe(".o_dcasa_mv_vistas", texto);
"""  # noqa: E501

GERENCIA_JS = """
(async () => {
""" + AYUDAS_JS + r"""
    await esperar(() => document.querySelector(".o_dcasa_mv .o_dcasa_ro_cuerpo"), "la pantalla de Movimiento");
    if (document.querySelector(".o_dcasa_mv h1").textContent.trim() !== "Movimiento") { falla("el título"); }
    // Los botones de periodo y de comparación.
    const periodos = [...document.querySelectorAll(".o_dcasa_mv_periodo .o_dcasa_mk_chip")].map((c) => c.textContent.trim());
    const esperados = ["Últimos 7 días", "Últimos 15 días", "Últimos 30 días", "Últimos 60 días", "Últimos 90 días", "Este mes", "Mes pasado", "Elegir fechas"];
    if (periodos.join("|") !== esperados.join("|")) { falla("los periodos: " + periodos.join("|")); }
    const contras = [...document.querySelectorAll(".o_dcasa_mv_contra .o_dcasa_mk_chip")].map((c) => c.textContent.trim());
    if (contras.join("|") !== ["El periodo de justo antes", "El mismo periodo del año pasado", "Elegir fechas"].join("|")) { falla("las comparaciones: " + contras.join("|")); }
    if (chipDe(".o_dcasa_mv_periodo", "Últimos 30 días").getAttribute("aria-pressed") !== "true") { falla("abre en 30 días"); }
    const rango = plano(document.querySelector(".o_dcasa_mv_rango"));
    if (!rango.includes("Este periodo:") || !rango.includes("Comparado con:") || !rango.includes("(30 días)")) { falla("el rango: " + rango); }
    // El resumen con dinero.
    const resumen = plano(document.querySelector(".o_dcasa_mv_resumen"));
    for (const texto of ["Unidades vendidas", "Pedidos (facturas)", "Productos que se vendieron", "Vendido (sin ITBMS)", "Antes:"]) {
        if (!resumen.includes(texto)) { falla("falta en el resumen: " + texto); }
    }
    // El gráfico: dos líneas con camino.
    const lineas = [".o_dcasa_mv_linea_este", ".o_dcasa_mv_linea_otro"].map((s) => document.querySelector(s));
    if (lineas.some((l) => !l || !(l.getAttribute("d") || "").startsWith("M"))) { falla("el gráfico no dibuja las dos líneas"); }
    // Los productos de la prueba, en «Los que más venden».
    escribir(document.querySelector(".o_dcasa_ro_buscar_texto"), "ZZMV");
    await esperar(() => quieta() && filas().length === 4, "los 4 que venden");
    if (filas().join("|") !== ["ZZMV SUBE", "ZZMV DESPIERTA", "ZZMV IGUAL", "ZZMV BAJA"].join("|")) { falla("la lista de los que venden: " + filas().join("|")); }
    const sube = document.querySelector(".o_dcasa_mv_fila");
    for (const texto of ["Subió", "Este periodo", "6 u. · 2 ped.", "Antes", "2 u. · 1 ped.", "+4 u. · +200 %", "Existencias", "Alcanza para", "25 días",
                         "Vendido este periodo", "$60.00", "Vendido antes", "$20.00", "Sin foto"]) {
        if (!plano(sube).includes(texto)) { falla("falta en la fila de ZZMV SUBE: " + texto + " → " + plano(sube)); }
    }
    if (vista("Los que más venden").getAttribute("aria-pressed") !== "true") { falla("«Los que más venden» no está elegido"); }
    // Las otras listas.
    vista("Los que bajaron").click();
    await esperar(() => quieta() && filas().join("|") === "ZZMV BAJA", "la lista de los que bajaron");
    if (!plano(document.querySelector(".o_dcasa_mv_fila")).includes("−3 u. · −75 %")) { falla("el cambio de ZZMV BAJA: " + plano(document.querySelector(".o_dcasa_mv_fila"))); }
    vista("Se enfriaron").click();
    await esperar(() => quieta() && filas().join("|") === "ZZMV ENFRIA", "la lista de los que se enfriaron");
    const enfria = plano(document.querySelector(".o_dcasa_mv_fila"));
    for (const texto of ["Se enfrió", "−3 u. · −100 %", "Capital parado"]) {
        if (!enfria.includes(texto)) { falla("falta en la fila de ZZMV ENFRIA: " + texto + " → " + enfria); }
    }
    vista("Quietos con existencias").click();
    await esperar(() => quieta() && filas().join("|") === "ZZMV QUIETO", "la lista de los quietos");
    if (!plano(document.querySelector(".o_dcasa_mv_sirve")).includes("Rotación")) { falla("la frase de para qué sirve la lista"); }
    // «Elegir fechas»: hasta tener las cuatro, no pide nada y lo dice.
    chipDe(".o_dcasa_mv_periodo", "Elegir fechas").click();
    await esperar(() => document.querySelector(".o_dcasa_mv_desde"), "las fechas de «Este periodo»");
    await esperar(() => document.querySelector(".o_dcasa_mv_faltan"), "el aviso de que faltan fechas");
    poner(document.querySelector(".o_dcasa_mv_desde"), "__DESDE__");
    poner(document.querySelector(".o_dcasa_mv_hasta"), "__HASTA__");
    await esperar(() => quieta() && !document.querySelector(".o_dcasa_mv_faltan"), "que pida con las dos fechas");
    if (!plano(document.querySelector(".o_dcasa_mv_rango")).includes("(6 días)")) { falla("el rango con fechas: " + plano(document.querySelector(".o_dcasa_mv_rango"))); }
    // El año pasado.
    chipDe(".o_dcasa_mv_periodo", "Últimos 30 días").click();
    chipDe(".o_dcasa_mv_contra", "El mismo periodo del año pasado").click();
    await esperar(() => quieta() && chipDe(".o_dcasa_mv_periodo", "Últimos 30 días").getAttribute("aria-pressed") === "true"
                  && chipDe(".o_dcasa_mv_contra", "El mismo periodo del año pasado").getAttribute("aria-pressed") === "true"
                  && document.querySelector(".o_dcasa_mv_excel").getAttribute("href").includes("contra=anio"), "30 días contra el año pasado");
    await esperar(() => document.querySelector(".o_dcasa_mv_sin_ventas"), "el aviso de que no hubo ventas el año pasado");
    // El Excel lleva lo que se ve.
    const url = new URL(document.querySelector(".o_dcasa_mv_excel").getAttribute("href"), location.origin);
    const dato = (k) => url.searchParams.get(k);
    if (url.pathname !== "/dcasa/movimiento/excel" || dato("periodo") !== "30" || dato("contra") !== "anio" || dato("texto") !== "ZZMV" || dato("vista") !== "quietos") {
        falla("el enlace del Excel: " + url);
    }
    // Ida y vuelta con Rotación.
    document.querySelector(".o_dcasa_mv_a_rotacion").click();
    await esperar(() => document.querySelector(".o_dcasa_ro:not(.o_dcasa_mv) .o_dcasa_ro_cuerpo"), "la pantalla de Rotación");
    document.querySelector(".o_dcasa_ro_a_movimiento").click();
    await esperar(() => document.querySelector(".o_dcasa_mv .o_dcasa_ro_cuerpo"), "la pantalla de Movimiento otra vez");
    chipDe(".o_dcasa_mv_contra", "El periodo de justo antes").click();
    await esperar(() => quieta() && !document.querySelector(".o_dcasa_mv_sin_ventas") && filas().length, "la lista con el periodo de justo antes");
    sinScrollDeCostado("Movimiento");
    // Baja con scroll (Odoo le pone `overflow: hidden` a todo `.o_action`).
    const pagina = document.querySelector(".o_dcasa_mk");
    if (!["auto", "scroll"].includes(getComputedStyle(pagina).overflowY)) { falla("la página no tiene scroll"); }
    pagina.scrollTop = 300;
    await pausa(50);
    if (pagina.scrollTop === 0) { falla("la página no baja con scroll"); }
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
"""  # noqa: E501

MARKETING_JS = """
(async () => {
""" + AYUDAS_JS + r"""
    // Desde la pantalla Marketing, el botón lleva a Movimiento.
    const boton = await esperar(() => document.querySelector(".o_dcasa_mk_boton_movimiento"), "el botón «Comparar periodos»");
    boton.click();
    await esperar(() => document.querySelector(".o_dcasa_mv .o_dcasa_ro_cuerpo"), "la pantalla de Movimiento");
    // Sin dinero: ni importes ni capital; sí unidades y pedidos.
    const todo = plano(document.querySelector(".o_dcasa_mv"));
    if (/\$\s*\d/.test(todo)) { falla("sale dinero para el rol Marketing: " + (todo.match(/\$\s*[\d,.]+/) || [])[0]); }
    for (const texto of ["Vendido (sin ITBMS)", "Vendido este periodo", "Capital parado"]) {
        if (todo.includes(texto)) { falla("sale «" + texto + "» sin dinero"); }
    }
    for (const texto of ["Unidades vendidas", "Pedidos (facturas)", "Productos que se vendieron"]) {
        if (!todo.includes(texto)) { falla("falta «" + texto + "»"); }
    }
    escribir(document.querySelector(".o_dcasa_ro_buscar_texto"), "ZZMV");
    await esperar(() => quieta() && filas().length === 4, "los 4 que venden");
    const fila = plano(document.querySelector(".o_dcasa_mv_fila"));
    for (const texto of ["Este periodo", "Antes", "Cambio", "Existencias", "Alcanza para", "Última venta"]) {
        if (!fila.includes(texto)) { falla("falta en la fila: " + texto); }
    }
    // El orden por capital no existe sin dinero.
    const ordenes = [...document.querySelectorAll(".o_dcasa_ro_orden option")].map((o) => o.value);
    if (ordenes.includes("capital")) { falla("ordenes con dinero: " + ordenes); }
    if (!document.querySelector(".o_dcasa_mv_excel")) { falla("falta el Excel"); }
    sinScrollDeCostado("Movimiento sin dinero");
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
"""  # noqa: E501

TAMANOS = ('390x844', '1440x900')


@tagged('post_install', '-at_install')
class TestMovimientoEnElNavegador(MovimientoDatos, HttpCase):

    def setUp(self):
        super().setUp()
        self.gerencia.write({'password': 'zzmk_gerencia'})
        self.marketing_rol.write({'password': 'zzmk_rol_marketing'})

    def test_gerencia_en_celular_y_computadora(self):
        guion = (GERENCIA_JS.replace('__DESDE__', str(self.hoy - timedelta(days=10)))
                 .replace('__HASTA__', str(self.hoy - timedelta(days=5))))
        for tamano in TAMANOS:
            with self.subTest(tamano=tamano):
                self.browser_size = tamano
                self.browser_js('/odoo/action-dcasa_marketing.accion_movimiento', guion, ready='odoo.isReady',
                                login='zzmk_gerencia', timeout=240)

    def test_el_rol_marketing_llega_desde_marketing_y_no_ve_dinero(self):
        for tamano in TAMANOS:
            with self.subTest(tamano=tamano):
                self.browser_size = tamano
                self.browser_js('/odoo/action-dcasa_marketing.accion_marketing', MARKETING_JS, ready='odoo.isReady',
                                login='zzmk_rol_marketing', timeout=240)

    def test_el_excel_solo_para_quien_entra(self):
        import io  # noqa: PLC0415

        from openpyxl import load_workbook  # noqa: PLC0415

        self.authenticate('zzmk_gerencia', 'zzmk_gerencia')
        respuesta = self.url_open('/dcasa/movimiento/excel?periodo=30&contra=anterior&vista=todos&texto=ZZMV')
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.headers['Content-Type'],
                         'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        self.assertIn('attachment', respuesta.headers['Content-Disposition'])
        hoja = load_workbook(io.BytesIO(respuesta.content))['Comparación']
        self.assertEqual({c.value for c in hoja['A'] if c.value and str(c.value).startswith('ZZMV')},
                         {'ZZMV SUBE', 'ZZMV BAJA', 'ZZMV IGUAL', 'ZZMV DESPIERTA', 'ZZMV ENFRIA', 'ZZMV QUIETO'})
        self.authenticate('zzmk_vendedora', 'zzmk_vendedora')
        # La vendedora no entra: Odoo contesta 403 al AccessError del servidor.
        from odoo.tools import mute_logger  # noqa: PLC0415
        with mute_logger('odoo.http'):
            self.assertEqual(self.url_open('/dcasa/movimiento/excel?vista=todos').status_code, 403)
