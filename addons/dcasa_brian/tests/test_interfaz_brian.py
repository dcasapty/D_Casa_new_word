"""Interfaz de Brian en el panel: el bundle la incluye y funciona en el navegador."""
from odoo.addons.dcasa_brian.models.proveedores import fijar_guion
from odoo.tests import HttpCase, tagged

ARCHIVOS = (
    'dcasa_brian/static/src/js/brian_servicio.js',
    'dcasa_brian/static/src/js/brian_panel.js',
    'dcasa_brian/static/src/js/brian_markdown.js',
    'dcasa_brian/static/src/xml/brian_panel.xml',
    'dcasa_brian/static/src/scss/brian_panel.scss',
)

# Espera a que una condición se cumpla (o falla con un mensaje claro).
ESPERAR = """
const esperar = async (fn, que, ms = 20000) => {
    const inicio = Date.now();
    while (Date.now() - inicio < ms) {
        const r = fn();
        if (r) { return r; }
        await new Promise((ok) => setTimeout(ok, 100));
    }
    throw new Error("Brian: no apareció " + que);
};
"""


@tagged('post_install', '-at_install')
class TestInterfazBrian(HttpCase):

    def setUp(self):
        super().setUp()
        self.env['ir.config_parameter'].sudo().set_param('dcasa_brian.proveedor', 'prueba')

    def test_bundle_backend_incluye_la_interfaz(self):
        rutas = {ruta for _addon, ruta, *_ in self.env['ir.asset']._get_asset_paths('web.assets_backend', {})}
        rutas |= {ruta.lstrip('/') for ruta in list(rutas)}
        for archivo in ARCHIVOS:
            self.assertTrue(any(r.endswith(archivo) for r in rutas), f'{archivo} no está en web.assets_backend')

    def test_chat_en_el_navegador(self):
        """Ctrl + J abre el panel, se escribe, Brian responde y el markdown es seguro."""
        fijar_guion([
            '**Hola**, soy Brian.\n\n| Producto | Estado |\n|---|---|\n| Sofá | Agotado |\n\n'
            '- uno\n- dos\n\n<img src=x onerror="window.brianInyectado=1">'
        ])
        codigo = ESPERAR + """
(async () => {
    await esperar(() => document.querySelector(".o_brian_lanzador"), "el botón flotante");
    // Ctrl + J abre el panel y pone el foco en la caja de texto.
    document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "j", ctrlKey: true, bubbles: true }));
    const panel = await esperar(() => document.querySelector(".o_brian_panel.o_brian_visible"), "el panel");
    const texto = await esperar(() => document.activeElement?.classList.contains("o_brian_texto")
        && document.activeElement, "el foco en la caja de texto");
    await esperar(() => panel.querySelector(".o_brian_chip"), "las sugerencias");
    texto.value = "¿Cómo va el día?";
    texto.dispatchEvent(new Event("input", { bubbles: true }));
    await new Promise((ok) => setTimeout(ok, 50));
    texto.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
    await esperar(() => panel.querySelector(".o_brian_burbuja_usuario"), "el mensaje del usuario");
    const respuesta = await esperar(() => panel.querySelector(".o_brian_burbuja_brian"), "la respuesta de Brian");
    if (!respuesta.querySelector("strong") || respuesta.querySelector("strong").textContent !== "Hola") {
        throw new Error("Brian: no se pintaron las negritas");
    }
    if (!respuesta.querySelector(".o_brian_tabla td") || !respuesta.querySelector("ul li")) {
        throw new Error("Brian: no se pintaron la tabla o la lista");
    }
    if (respuesta.querySelector("img") || window.brianInyectado) {
        throw new Error("Brian: se inyectó HTML desde la respuesta");
    }
    if (!respuesta.textContent.includes("<img")) {
        throw new Error("Brian: el HTML de la respuesta debe verse como texto");
    }
    // Esc cierra y el foco vuelve fuera del panel.
    document.activeElement.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    await esperar(() => !document.querySelector(".o_brian_panel.o_brian_visible"), "el panel cerrado");
    // El botón flotante también lo abre, con la conversación intacta.
    document.querySelector(".o_brian_lanzador").click();
    await esperar(() => document.querySelector(".o_brian_panel.o_brian_visible .o_brian_burbuja_brian"),
        "la conversación al reabrir");
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
"""
        self.browser_js('/odoo', codigo, ready="odoo.isReady", login='admin', timeout=120)
        conversacion = self.env['brian.conversacion'].search([], order='id desc', limit=1)
        self.assertTrue(conversacion, 'El chat debió crear una conversación')

    def test_sin_clave_muestra_aviso_y_sigue_usable(self):
        self.env['ir.config_parameter'].sudo().set_param('dcasa_brian.proveedor', 'anthropic')
        codigo = ESPERAR + """
(async () => {
    const boton = await esperar(() => document.querySelector(".o_brian_lanzador"), "el botón flotante");
    boton.click();
    const panel = await esperar(() => document.querySelector(".o_brian_panel.o_brian_visible"), "el panel");
    const aviso = await esperar(() => panel.querySelector(".o_brian_aviso"), "el aviso de clave");
    if (!/Ajustes\\s›\\sBrian/.test(aviso.textContent)) {
        throw new Error("Brian: el aviso debe decir dónde configurar la clave");
    }
    if (!panel.querySelector(".o_brian_texto") || !panel.querySelector(".o_brian_chip")) {
        throw new Error("Brian: el panel debe seguir usable sin clave");
    }
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
"""
        self.browser_js('/odoo', codigo, ready="odoo.isReady", login='admin', timeout=90)
