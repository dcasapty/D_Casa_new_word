"""«Este cliente lo atiende Ana. ¿Lo tomas tú?» y «Clientes que cambiaron de mano», en Chrome de verdad (aprobado por la
dueña el 2026-11-12). Beto (vendedora) le escribe al cliente que atiende Ana (vendedora, «Disponible»: con la regla de
estar activa en 0, como en las demás pruebas del panel, cuenta como activa): la pantalla pregunta antes. En la
computadora (1366) y en el celular (390, botones de 44 px y nada de costado). Gerencia, como siempre: sin pregunta."""
from datetime import timedelta

from odoo import fields
from odoo.tests import new_test_user, tagged

from .test_panel_caja_celular import MEDIR
from .test_panel_interfaz import GERENTE, VENDEDORA, PanelUiCase
from .test_reparto_pantalla import ACCION_REPARTO

BETO = 'juan_ui_beto'

PREGUNTA = """
const enviar = () => document.querySelector(".o_dcj_enviar");
const dialogo = () => document.querySelector(".o_dcj_toma");
const esperarPregunta = async () => {
    const d = await esperar(dialogo, "la pregunta «¿Lo tomas tú?»");
    const titulo = d.querySelector("#o_dcj_toma_titulo").textContent.trim();
    if (titulo !== "Este cliente lo atiende Ana Vendedora. ¿Lo tomas tú?") {
        throw new Error("la pregunta dice: " + titulo);
    }
    const botones = [...d.querySelectorAll("button")].map((b) => b.textContent.trim()).join("|");
    if (botones !== "Sí, lo tomo|Dejarle una nota a Ana|Cancelar") { throw new Error("los botones: " + botones); }
    await pausa(150);
    if (document.activeElement !== d.querySelector(".o_dcj_toma_cancelar")) {
        throw new Error("el foco empieza en «Cancelar»");
    }
    return d;
};
const cerrada = () => esperar(() => !dialogo(), "que la pregunta se cierre");
const TOMO = "Beto Vendedor tomó el cliente que atendía Ana Vendedora.";
"""


class TomaUiCase(PanelUiCase):

    def setUp(self):
        super().setUp()
        self.beto = new_test_user(self.env, login=BETO, name='Beto Vendedor',
                                  groups='base.group_user,sales_team.group_sale_salesman')
        (self.vendedora | self.beto).write({'dcasa_disponible': True, 'dcasa_fuera_del_reparto': False})
        self.karen = self.registrar('Hola, ¿tienen camas queen?', '50761000001', minutos=20, nombre='Karen Pérez')
        self.karen._poner_en_humano(usuario=self.vendedora)
        self.registrar('¿Me la entregan el sábado?', '50761000001', minutos=2)

    def de_beto(self, conv):
        return self.env['dcasa.mensaje'].search_count([('conversacion_id', '=', conv.id), ('autor', '=', 'vendedora'),
                                                       ('usuario_id', '=', self.beto.id), ('tipo', '=', 'mensaje')])


@tagged('post_install', '-at_install')
class TestTomarElClienteDeOtraEnElNavegador(TomaUiCase):
    browser_size = '1366x768'

    def test_cancelar_no_hace_nada_y_dejarle_una_nota_no_le_escribe_al_cliente(self):
        self.navegador(PREGUNTA + """
(async () => {
    await abrirConversacion("Karen Pérez");
    const texto = await esperar(() => document.querySelector("#o_dcj_texto"), "la caja");
    await escribir(texto, "Hola, te atiendo yo");
    enviar().click();
    let d = await esperarPregunta();
    d.querySelector(".o_dcj_toma_cancelar").click();
    await cerrada();
    if (document.querySelector("#o_dcj_texto").value !== "Hola, te atiendo yo") {
        throw new Error("«Cancelar» no borra lo escrito");
    }
    // Esc y tocar fuera también cancelan.
    enviar().click();
    await esperarPregunta();
    escape();
    await cerrada();
    enviar().click();
    d = await esperarPregunta();
    document.querySelector(".o_dcj_capa_toma").click();
    await cerrada();
    if (aqui(".o_dcj_burbuja", "Hola, te atiendo yo")) { throw new Error("no debía salir nada al cliente"); }
    // «Dejarle una nota a Ana»: la caja pasa a «Nota» con lo escrito y la mención; nada sale.
    enviar().click();
    d = await esperarPregunta();
    d.querySelector(".o_dcj_toma_nota").click();
    await cerrada();
    await esperar(() => document.querySelector(".o_dcj_caja.o_nota"), "la caja en modo nota");
    const nota = document.querySelector("#o_dcj_texto").value;
    if (nota !== "@Ana Vendedora Hola, te atiendo yo") { throw new Error("la nota dice: " + nota); }
    await pausa(200);
    if (document.activeElement !== document.querySelector("#o_dcj_texto")) {
        throw new Error("el foco vuelve a la caja");
    }
    enviar().click();
    await esperar(() => aqui(".o_dcj_burbuja", "Hola, te atiendo yo")?.querySelector(".o_dcj_burbuja_privada"),
        "la nota en el hilo");
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
""", login=BETO)
        self.env.invalidate_all()
        self.assertEqual(self.de_beto(self.karen), 0, 'Al cliente no le salió nada')
        self.assertFalse(self.al_worker('/odoo/enviar'))
        self.assertEqual(self.karen.asignada_a, self.vendedora, 'Sigue con Ana')
        nota = self.env['dcasa.mensaje'].search([('conversacion_id', '=', self.karen.id), ('tipo', '=', 'nota')])
        self.assertEqual(nota.mencion_ids, self.vendedora, 'A Ana le llega el aviso de la mención')

    def test_si_lo_tomo_envia_y_queda_dicho_en_el_hilo(self):
        self.navegador(PREGUNTA + """
(async () => {
    await abrirConversacion("Karen Pérez");
    await escribir(await esperar(() => document.querySelector("#o_dcj_texto"), "la caja"), "Hola, te atiendo yo");
    enviar().click();
    const d = await esperarPregunta();
    d.querySelector(".o_dcj_toma_si").click();
    await cerrada();
    await esperar(() => aqui(".o_dcj_burbuja", "Hola, te atiendo yo"), "lo que le escribió al cliente");
    await esperar(() => aqui(".o_dcj_aviso_sistema", TOMO), "el aviso en el hilo");
    await esperar(() => document.querySelector(".o_dcj_barra")?.textContent.includes("Atiendes tú"),
        "que ya lo atiende él");
    if (document.querySelector("#o_dcj_texto").value) { throw new Error("la caja queda vacía después de enviar"); }
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
""", login=BETO)
        self.env.invalidate_all()
        self.assertEqual(self.de_beto(self.karen), 1)
        self.assertEqual(len(self.al_worker('/odoo/enviar')), 1)
        self.assertEqual(self.karen.asignada_a, self.beto)
        tomada = self.env['dcasa.reparto'].search([('conversacion_id', '=', self.karen.id), ('regla', '=', 'tomada')])
        self.assertEqual((tomada.anterior_id, tomada.forma), (self.vendedora, 'escribir'))

    def test_atender_tambien_pregunta(self):
        # La pausa de Ana venció: la barra ofrece «Atender» (el asistente volvió a contestar, pero sigue a su nombre).
        self.karen.sudo().pausada_hasta = fields.Datetime.now() - timedelta(minutes=1)
        self.navegador(PREGUNTA + """
(async () => {
    await abrirConversacion("Karen Pérez");
    const atender = await esperar(() => aqui(".o_dcj_barra button", "Atender"), "el botón «Atender»");
    atender.click();
    const d = await esperarPregunta();
    d.querySelector(".o_dcj_toma_si").click();
    await esperar(() => aqui(".o_dcj_aviso_sistema", TOMO), "el aviso en el hilo");
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
""", login=BETO)
        self.env.invalidate_all()
        self.assertEqual(self.karen.asignada_a, self.beto)

    def test_gerencia_escribe_sin_pregunta_como_siempre(self):
        self.navegador(PREGUNTA + """
(async () => {
    await abrirConversacion("Karen Pérez");
    await escribir(await esperar(() => document.querySelector("#o_dcj_texto"), "la caja"), "Hola, soy de Gerencia");
    enviar().click();
    await esperar(() => aqui(".o_dcj_burbuja", "Hola, soy de Gerencia"), "lo que le escribió al cliente");
    await pausa(300);
    if (dialogo()) { throw new Error("a Gerencia no se le pregunta"); }
    if (aqui(".o_dcj_aviso_sistema", "tomó el cliente que atendía")) {
        throw new Error("Gerencia no deja el aviso nuevo");
    }
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
""", login=GERENTE)

    def test_atiende_de_la_ficha_pregunta_y_pasarselo_a_otra_no_se_puede(self):
        """Revisión adversarial (2026-11-12): el selector «Atiende» de la ficha también pregunta; pasárselo a otra
        persona no se puede mientras Ana trabaja (el selector vuelve a decir Ana). Y la barra no ofrece «Devolver»:
        ofrece «Atender»; «Cerrar» explica por qué no."""
        self.navegador(PREGUNTA + """
(async () => {
    await abrirConversacion("Karen Pérez");
    const barra = await esperar(() => document.querySelector(".o_dcj_barra"), "la barra de quién atiende");
    if (!barra.textContent.includes("La atiende Ana Vendedora")) { throw new Error("la barra: " + barra.textContent); }
    const botonDeLaBarra = barra.querySelector("button");
    if (botonDeLaBarra.textContent.trim() !== "Atender") {
        throw new Error("al cliente de otra se le ofrece «Atender», no «Devolver»: " + botonDeLaBarra.textContent);
    }
    document.querySelector('[aria-label="Cerrar la conversación"]').click();
    await esperar(() => aqui(".o_notification", "no puedes cerrar la conversación"), "por qué no se puede cerrar");
    document.querySelector(".o_dcj_boton_ficha").click();
    const selector = await esperar(() => document.querySelector("#o_dcj_asignar"), "«Atiende» en la ficha");
    const opcion = (nombre) => [...selector.options].find((o) => o.textContent.includes(nombre)).value;
    const ana = opcion("Ana Vendedora");
    if (selector.value !== ana) { throw new Error("la ficha dice que la atiende Ana"); }
    // A otra persona: no se puede, y el selector vuelve a Ana.
    selector.value = opcion("Gema Gerente");
    selector.dispatchEvent(new Event("change", { bubbles: true }));
    await esperar(() => aqui(".o_notification", "Pídeselo a Ana Vendedora o a Gerencia"), "por qué no se puede");
    await esperar(() => selector.value === ana, "que el selector vuelva a Ana");
    // A sí mismo: la misma pregunta. «Cancelar» lo deja como estaba.
    selector.value = opcion("Beto Vendedor");
    selector.dispatchEvent(new Event("change", { bubbles: true }));
    let d = await esperarPregunta();
    d.querySelector(".o_dcj_toma_cancelar").click();
    await cerrada();
    await esperar(() => selector.value === ana, "que el selector vuelva a Ana al cancelar");
    // «Sí, lo tomo».
    selector.value = opcion("Beto Vendedor");
    selector.dispatchEvent(new Event("change", { bubbles: true }));
    d = await esperarPregunta();
    d.querySelector(".o_dcj_toma_si").click();
    await cerrada();
    await esperar(() => aqui(".o_dcj_aviso_sistema", TOMO), "el aviso en el hilo");
    await esperar(() => document.querySelector("#o_dcj_asignar").value === opcion("Beto Vendedor"), "Atiende: Beto");
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
""", login=BETO)
        self.env.invalidate_all()
        self.assertEqual((self.karen.asignada_a, self.karen.estado), (self.beto, 'humano'))
        tomada = self.env['dcasa.reparto'].search([('conversacion_id', '=', self.karen.id), ('regla', '=', 'tomada')])
        self.assertEqual((tomada.anterior_id, tomada.forma), (self.vendedora, 'asignar'))
        self.assertFalse(self.al_worker('/odoo/enviar'), 'Asignarse el cliente no le escribe nada')


@tagged('post_install', '-at_install')
class TestTomarElClienteDeOtraEnElCelular(TomaUiCase):
    browser_size = '390x844'
    touch_enabled = True

    def test_la_pregunta_cabe_con_botones_de_44_px_y_si_lo_tomo_envia(self):
        self.navegador(MEDIR + PREGUNTA + """
(async () => {
    if (window.innerWidth !== 390) { throw new Error("el celular debe medir 390 px y mide " + window.innerWidth); }
    await abrirLaDe("Karen");
    await escribir(document.querySelector("#o_dcj_texto"), "Hola, te atiendo yo");
    tocar(enviar());
    const d = await esperarPregunta();
    await pausa(300);
    const r = rect(d);
    if (r.left < -0.5 || r.right > window.innerWidth + 0.5 || r.bottom > window.innerHeight + 0.5 || r.top < 0) {
        throw new Error("la pregunta no cabe: " + JSON.stringify(r));
    }
    if (Math.abs(r.bottom - window.innerHeight) > 2) { throw new Error("en el celular la pregunta sube desde abajo"); }
    for (const b of d.querySelectorAll("button")) {
        const rb = rect(b);
        if (rb.height < 43.5) { throw new Error("«" + b.textContent.trim() + "» mide " + rb.height + " px de alto"); }
        if (rb.width < r.width - 40) { throw new Error("«" + b.textContent.trim() + "» ocupa el ancho: " + rb.width); }
    }
    if (document.documentElement.scrollWidth > window.innerWidth + 1) { throw new Error("se sale de costado"); }
    tocar(d.querySelector(".o_dcj_toma_si"));
    await cerrada();
    await esperar(() => aqui(".o_dcj_aviso_sistema", TOMO), "el aviso en el hilo");
    sinDesborde("después de tomarlo");
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
""", login=BETO)
        self.env.invalidate_all()
        self.assertEqual(self.karen.asignada_a, self.beto)

    def test_en_el_celular_la_barra_ofrece_atender_y_atiende_pregunta(self):
        self.navegador(MEDIR + PREGUNTA + """
(async () => {
    await abrirLaDe("Karen");
    const boton = document.querySelector(".o_dcj_barra button");
    if (!boton.textContent.trim().startsWith("Atender")) { throw new Error("la barra ofrece: " + boton.textContent); }
    if (corto() !== "Ana Vendedora") { throw new Error("quién atiende, en corto: " + corto()); }
    sinChicos("con la barra del cliente de otra");
    tocar(document.querySelector(".o_dcj_boton_ficha"));
    const selector = await esperar(() => document.querySelector("#o_dcj_asignar"), "«Atiende» en la ficha");
    selector.value = [...selector.options].find((o) => o.textContent.includes("Beto Vendedor")).value;
    selector.dispatchEvent(new Event("change", { bubbles: true }));
    const d = await esperarPregunta();
    for (const b of d.querySelectorAll("button")) {
        if (rect(b).height < 43.5) { throw new Error("«" + b.textContent.trim() + "» mide " + rect(b).height + " px"); }
    }
    if (document.documentElement.scrollWidth > window.innerWidth + 1) { throw new Error("se sale de costado"); }
    tocar(d.querySelector(".o_dcj_toma_si"));
    await cerrada();
    const elegida = () => [...selector.options].find((o) => o.selected)?.textContent || "";
    await esperar(() => selector.isConnected && elegida().includes("Beto"), "Atiende: Beto");
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
""", login=BETO)
        self.env.invalidate_all()
        self.assertEqual(self.karen.asignada_a, self.beto)


@tagged('post_install', '-at_install')
class TestCambiosDeManoEnElNavegador(TomaUiCase):
    """El bloque «Clientes que cambiaron de mano» de la pantalla Reparto: Gerencia lo ve; la vendedora, no."""

    def setUp(self):
        super().setUp()
        self.ajustes.reparto_modo = 'parejo'
        self.env['dcasa.conversacion'].with_user(self.beto).enviar_respuesta(
            self.karen.id, 'Hola, te atiendo yo', tomar_de=self.vendedora.id)

    def test_gerencia_ve_el_bloque_en_la_computadora_y_en_el_celular(self):
        codigo = """
(async () => {
    const bloque = await esperar(() => document.querySelector(".o_dcj_reparto_cambios"),
        "el bloque de clientes que cambiaron de mano");
    if (!bloque.querySelector("h2").textContent.includes("Clientes que cambiaron de mano")) {
        throw new Error("el título");
    }
    const fila = await esperar(() => aqui(".o_dcj_reparto_cambios_tabla tbody tr", "Karen Pérez"), "la fila de Karen");
    for (const parte of ["Ana Vendedora", "Beto Vendedor", "Lo tomó al escribirle"]) {
        if (!fila.textContent.includes(parte)) {
            throw new Error("falta «" + parte + "» en la fila: " + fila.textContent);
        }
    }
    if (document.documentElement.scrollWidth > window.innerWidth + 1) { throw new Error("se sale de costado"); }
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
"""
        for tamano in ('1366x768', '390x844'):
            with self.subTest(tamano=tamano):
                self.browser_size = tamano
                self.navegador(codigo, url=ACCION_REPARTO, login=GERENTE)

    def test_la_vendedora_no_lo_ve(self):
        self.navegador("""
(async () => {
    await esperar(() => document.querySelector(".o_dcj_reparto_mias"), "lo suyo");
    if (document.querySelector(".o_dcj_reparto_cambios")) { throw new Error("la vendedora no ve quién tomó a quién"); }
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
""", url=ACCION_REPARTO, login=VENDEDORA)
