"""La pantalla «Rotación» en un navegador de verdad, a tamaño celular (390×844) y computadora (1440×900).

* Gerencia: las ocho barras por días sin vender, buscar los productos de la prueba, cambiar de «sin vender 90 días o
  más» a «30 días o más», la simulación de rebaja (con cifras exactas), el enlace del Excel con lo que se está viendo,
  sin scroll de costado y con scroll hacia abajo.
* Rol Marketing: llega desde el botón de la pantalla Marketing y ve unidades y días, sin dinero y sin simulación.
"""
from odoo.tests import HttpCase, tagged

from .test_rotacion import RotacionDatos

AYUDAS_JS = r"""
    const esperar = async (fn, que, ms = 25000) => {
        const inicio = Date.now();
        while (Date.now() - inicio < ms) {
            const r = fn();
            if (r) { return r; }
            await new Promise((ok) => setTimeout(ok, 100));
        }
        throw new Error("Rotación: no apareció " + que);
    };
    const pausa = (ms) => new Promise((ok) => setTimeout(ok, ms));
    const falla = (texto) => { throw new Error("Rotación: " + texto); };
    const quieta = () => !document.querySelector(".o_dcasa_mk_actualizando");
    const plano = (el) => el.textContent.replace(/\s+/g, " ").trim();
    const filas = () => [...document.querySelectorAll(".o_dcasa_ro_fila")].map((f) => f.querySelector(".o_dcasa_mk_nombre strong").textContent.trim());
    const sinScrollDeCostado = (que) => {
        if (document.documentElement.scrollWidth > window.innerWidth + 1) { falla("scroll de costado en " + que); }
        for (const el of document.querySelectorAll(".o_dcasa_mk_contenido, .o_dcasa_ro_fila, .o_dcasa_ro_barra, .o_dcasa_ro_resumen")) {
            if (el.scrollWidth > el.clientWidth + 1) { falla("algo se sale de costado en " + que + ": " + el.className); }
        }
    };
    const escribir = (entrada, valor) => {
        entrada.value = valor;
        entrada.dispatchEvent(new Event("input", { bubbles: true }));
    };
    const chip = (texto) => [...document.querySelectorAll(".o_dcasa_ro_lista .o_dcasa_mk_chips .o_dcasa_mk_chip")]
        .find((c) => c.textContent.trim().replace(/\s+/g, " ").startsWith(texto));
"""  # noqa: E501

GERENCIA_JS = """
(async () => {
""" + AYUDAS_JS + r"""
    await esperar(() => document.querySelector(".o_dcasa_ro .o_dcasa_ro_cuerpo"), "la pantalla de Rotación");
    if (document.querySelector(".o_dcasa_ro h1").textContent.trim() !== "Rotación") { falla("el título"); }
    const barras = () => [...document.querySelectorAll(".o_dcasa_ro_barra")];
    if (barras().length !== 8) { falla("son 8 grupos y hay " + barras().length); }
    for (const nombre of ["Menos de 30 días", "30 a 59 días", "60 a 89 días", "90 a 179 días", "180 días o más",
                          "Nunca vendido", "Llegó hace poco", "Pedido abierto"]) {
        if (!barras().some((b) => b.textContent.includes(nombre))) { falla("falta el grupo " + nombre); }
    }
    // El resumen con dinero.
    const resumen = plano(document.querySelector(".o_dcasa_ro_resumen"));
    for (const texto of ["Capital en inventario", "Parado 90 días o más", "Productos ancla"]) {
        if (!resumen.includes(texto)) { falla("falta en el resumen: " + texto); }
    }
    // Los productos de la prueba. Abre en «90 días o más sin vender».
    escribir(document.querySelector(".o_dcasa_ro_buscar_texto"), "ZZRO");
    await esperar(() => quieta() && filas().length === 3, "los 3 de 90 días o más");
    const vistos = filas().sort().join("|");
    if (vistos !== ["ZZRO CIENTO OCHENTA", "ZZRO NOVENTA", "ZZRO NUNCA"].sort().join("|")) { falla("la lista de 90 o más: " + vistos); }
    const nunca = [...document.querySelectorAll(".o_dcasa_ro_fila")].find((f) => f.textContent.includes("ZZRO NUNCA"));
    for (const texto of ["Nunca vendido", "Última venta", "Nunca", "Capital parado", "$120.00", "Precio · margen", "$100.00 · 40 %"]) {
        if (!plano(nunca).includes(texto)) { falla("falta en la fila de ZZRO NUNCA: " + texto + " → " + plano(nunca)); }
    }
    // Cambiar a «30 días o más sin vender».
    chip("30 días o más sin vender").click();
    await esperar(() => quieta() && filas().length === 5, "los 5 de 30 días o más");
    // La simulación: 20 % → entran 800, el costo es 600, quedan 200 (25 %), ninguno bajo el costo.
    escribir(document.querySelector(".o_dcasa_ro_rebaja"), "20");
    const simulacion = await esperar(() => document.querySelector(".o_dcasa_ro_simulacion"), "la simulación");
    await esperar(() => quieta() && plano(document.querySelector(".o_dcasa_ro_simulacion")).includes("$800.00"), "800");
    for (const texto of ["20 % de descuento", "$800.00", "$600.00", "$200.00", "25 %", "ninguno se vendería perdiendo dinero",
                         "no cambia ningún precio"]) {
        if (!plano(document.querySelector(".o_dcasa_ro_simulacion")).includes(texto)) {
            falla("falta en la simulación: " + texto + " → " + plano(document.querySelector(".o_dcasa_ro_simulacion")));
        }
    }
    const sesenta = [...document.querySelectorAll(".o_dcasa_ro_fila")].find((f) => f.textContent.includes("ZZRO SESENTA"));
    if (!plano(sesenta).includes("Con 20 %") || !plano(sesenta).includes("$80.00 · 25 %")) { falla("el precio rebajado: " + plano(sesenta)); }
    // 50 % queda por debajo del costo.
    escribir(document.querySelector(".o_dcasa_ro_rebaja"), "50");
    await esperar(() => quieta() && document.querySelector(".o_dcasa_ro_simulacion")
                  && plano(document.querySelector(".o_dcasa_ro_simulacion")).includes("se venderían perdiendo dinero"), "bajo el costo");
    if (!document.querySelector(".o_dcasa_ro_fila").textContent.includes("Bajo el costo")) { falla("la fila no dice «Bajo el costo»"); }
    escribir(document.querySelector(".o_dcasa_ro_rebaja"), "20");
    await esperar(() => quieta() && plano(document.querySelector(".o_dcasa_ro_simulacion")).includes("$800.00"), "800 otra vez");
    // El Excel lleva lo que se ve.
    const url = new URL(document.querySelector(".o_dcasa_ro_excel").getAttribute("href"), location.origin);
    const dato = (k) => url.searchParams.get(k);
    if (url.pathname !== "/dcasa/rotacion/excel" || dato("vista") !== "mas_de_30" || dato("texto") !== "ZZRO" || dato("rebaja") !== "20") {
        falla("el enlace del Excel: " + url);
    }
    // Tocar una barra elige ese grupo.
    barras().find((b) => b.textContent.includes("Nunca vendido")).click();
    await esperar(() => quieta() && filas().length === 1 && filas()[0] === "ZZRO NUNCA", "solo el que nunca se vendió");
    if (chip("Nunca vendidos").getAttribute("aria-pressed") !== "true") { falla("el botón «Nunca vendidos» no quedó elegido"); }
    // Sin vender, la categoría y la lista vacía.
    escribir(document.querySelector(".o_dcasa_ro_buscar_texto"), "ZZRO-NO-EXISTE");
    await esperar(() => quieta() && document.querySelector(".o_dcasa_mk_vacio"), "el aviso de lista vacía");
    escribir(document.querySelector(".o_dcasa_ro_buscar_texto"), "");
    await esperar(() => quieta() && document.querySelector(".o_dcasa_ro_fila"), "la lista otra vez");
    sinScrollDeCostado("Rotación");
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
    // Desde la pantalla Marketing, el botón lleva a Rotación.
    const boton = await esperar(() => document.querySelector(".o_dcasa_mk_boton_rotacion"), "el botón «Rotación del inventario»");
    boton.click();
    await esperar(() => document.querySelector(".o_dcasa_ro .o_dcasa_ro_cuerpo"), "la pantalla de Rotación");
    // Sin dinero: ni capital, ni costos, ni simulación; sí unidades y días.
    const todo = plano(document.querySelector(".o_dcasa_ro"));
    if (/\$\s*\d/.test(todo)) { falla("sale dinero para el rol Marketing: " + (todo.match(/\$\s*[\d,.]+/) || [])[0]); }
    if (document.querySelector(".o_dcasa_ro_rebaja")) { falla("el rol Marketing no simula rebajas"); }
    for (const texto of ["Capital en inventario", "Capital parado", "Precio · margen"]) {
        if (todo.includes(texto)) { falla("sale «" + texto + "» sin dinero"); }
    }
    for (const texto of ["Con existencias", "Sin vender 90 días o más", "Productos ancla"]) {
        if (!todo.includes(texto)) { falla("falta «" + texto + "»"); }
    }
    escribir(document.querySelector(".o_dcasa_ro_buscar_texto"), "ZZRO");
    await esperar(() => quieta() && filas().length === 3, "los 3 de 90 días o más");
    const fila = plano(document.querySelector(".o_dcasa_ro_fila"));
    for (const texto of ["Existencias", "Última venta", "Vendidas 30 · 60 · 90 días", "Alcanza para"]) {
        if (!fila.includes(texto)) { falla("falta en la fila: " + texto); }
    }
    // El orden por capital no existe sin dinero.
    const ordenes = [...document.querySelectorAll(".o_dcasa_ro_orden option")].map((o) => o.value);
    if (ordenes.includes("capital") || ordenes.includes("margen")) { falla("ordenes con dinero: " + ordenes); }
    if (!document.querySelector(".o_dcasa_ro_excel")) { falla("falta el Excel"); }
    sinScrollDeCostado("Rotación sin dinero");
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
"""  # noqa: E501

TAMANOS = ('390x844', '1440x900')


@tagged('post_install', '-at_install')
class TestRotacionEnElNavegador(RotacionDatos, HttpCase):

    def setUp(self):
        super().setUp()
        self.gerencia.write({'password': 'zzmk_gerencia'})
        self.marketing_rol.write({'password': 'zzmk_rol_marketing'})

    def test_gerencia_en_celular_y_computadora(self):
        for tamano in TAMANOS:
            with self.subTest(tamano=tamano):
                self.browser_size = tamano
                self.browser_js('/odoo/action-dcasa_marketing.accion_rotacion', GERENCIA_JS, ready='odoo.isReady',
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
        respuesta = self.url_open('/dcasa/rotacion/excel?vista=mas_de_90&texto=ZZRO&rebaja=20')
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.headers['Content-Type'],
                         'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        self.assertIn('attachment', respuesta.headers['Content-Disposition'])
        hoja = load_workbook(io.BytesIO(respuesta.content))['Rotación']
        self.assertEqual({c.value for c in hoja['A'] if c.value and str(c.value).startswith('ZZRO')},
                         {'ZZRO NOVENTA', 'ZZRO CIENTO OCHENTA', 'ZZRO NUNCA'})
        self.authenticate('zzmk_vendedora', 'zzmk_vendedora')
        # La vendedora no entra: Odoo contesta 403 al AccessError del servidor.
        from odoo.tools import mute_logger  # noqa: PLC0415
        with mute_logger('odoo.http'):
            self.assertEqual(self.url_open('/dcasa/rotacion/excel?vista=mas_de_90').status_code, 403)
