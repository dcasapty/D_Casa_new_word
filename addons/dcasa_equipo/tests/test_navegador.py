"""La pantalla «Alta del equipo» en un navegador de verdad (Chrome sin cabeza): se pega, se lee, se crea."""
from odoo.tests import HttpCase, tagged

CODIGO = """
(async () => {
    const esperar = async (condicion, que, ms = 20000) => {
        const desde = Date.now();
        while (Date.now() - desde < ms) {
            const r = condicion();
            if (r) { return r; }
            await new Promise((ok) => setTimeout(ok, 100));
        }
        throw new Error("no apareció: " + que);
    };
    const boton = (texto) => [...document.querySelectorAll("button")].find((b) => b.textContent.trim() === texto);
    const cuadro = await esperar(() => document.querySelector(".o_form_view textarea"), "el cuadro de la lista");
    if (document.querySelector(".modal")) { throw new Error("debe ser una página, no una ventana emergente"); }
    cuadro.value = "Persona Navegador | navegador@equipo-prueba.test | Ventas | Cargo | Vendedora";
    cuadro.dispatchEvent(new Event("input", { bubbles: true }));
    cuadro.dispatchEvent(new Event("change", { bubbles: true }));
    (await esperar(() => boton("Leer lista"), "el botón «Leer lista»")).click();
    await esperar(() => document.querySelectorAll(".o_data_row").length === 1, "la fila leída");
    (await esperar(() => boton("Crear al equipo"), "el botón «Crear al equipo»")).click();
    await esperar(() => /Creado/.test((document.querySelector(".o_data_row") || {}).textContent || ""),
                  "la fila en estado Creado");
    if (document.querySelector(".modal")) { throw new Error("no debe salir ninguna ventana emergente"); }
    console.log("test successful");
})();
"""


@tagged('post_install', '-at_install')
class TestAltaEnElNavegador(HttpCase):

    def test_pegar_leer_y_crear(self):
        self.browser_js('/odoo/action-dcasa_equipo.action_dcasa_equipo_alta', CODIGO, ready='odoo.isReady',
                        login='admin', timeout=120)
        usuario = self.env['res.users'].sudo().search([('login', '=', 'navegador@equipo-prueba.test')])
        self.assertEqual(len(usuario), 1)
        self.assertEqual(usuario.state, 'new', "sin invitación")
        self.assertEqual(usuario.employee_ids.department_id.name, 'Ventas')
        self.assertTrue(usuario.has_group('dcasa_base.group_vendedora'))
