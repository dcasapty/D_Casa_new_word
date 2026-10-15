"""«Llévame ahí» en un navegador de verdad: el botón abre la pantalla justa, los pasos y la cinta, el uso por
persona, lo que una vendedora no puede abrir no se le ofrece, y todo se ve bien en el computador y en el celular."""
import json
from unittest import mock

from odoo import Command, api
from odoo.addons.dcasa_guia.models import guia as G
from odoo.exceptions import UserError
from odoo.tests import HttpCase, tagged
from odoo.tools import mute_logger

# Funciones de ayuda del navegador (se pegan al principio de cada prueba).
AYUDAS = """
const espera = (ms) => new Promise((ok) => setTimeout(ok, ms));
const esperar = async (fn, que, ms = 40000) => {
    const inicio = Date.now();
    while (Date.now() - inicio < ms) {
        const r = fn();
        if (r) { return r; }
        await espera(100);
    }
    throw new Error("Llévame ahí: no apareció " + que);
};
const falla = (texto) => { throw new Error("Llévame ahí: " + texto); };
const tarea = (id) => document.querySelector(`.o_dcasa_guia_tarea[data-tarea="${id}"]`);
const botonDe = (id) => {
    const t = tarea(id);
    return t && t.querySelector(".o_dcasa_guia_llevame_tarea");
};
const escribir = (el, valor) => {
    el.value = valor;
    el.dispatchEvent(new Event("input", { bubbles: true }));
};
const cinta = () => document.querySelector(".o_dcasa_guia_cinta");
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
const enLaGuia = () => esperar(() => document.querySelector(".o_dcasa_guia_tarea"), "la Guía");
// Volver a la Guía por la barra lateral (sin recargar la página).
const guiaPorLaBarra = async () => {
    const enlace = [...document.querySelectorAll(".o_dcasa_barra a")].find((a) => a.textContent.trim() === "Guía");
    if (!enlace) { falla("la barra lateral no tiene el enlace a la Guía"); }
    enlace.click();
    await esperar(() => !cinta(), "que se quite la cinta al volver a la Guía");
    await enLaGuia();
};
const llevarA = async (id, ruta) => {
    const boton = botonDe(id);
    if (!boton) { falla("la tarea " + id + " no tiene botón Llévame ahí"); }
    boton.click();
    await esperar(cinta, "la cinta de «Estás haciendo» (" + id + ")");
    if (ruta) {
        await esperar(() => location.pathname === ruta, "la ruta " + ruta + " (estás en " + location.pathname + ")");
    }
};
"""

CIERRE = """
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
"""


def codigo(cuerpo, **reemplazos):
    """El programa del navegador: ayudas + cuerpo, con los valores de Python ya puestos."""
    for clave, valor in reemplazos.items():
        cuerpo = cuerpo.replace(f'__{clave}__', json.dumps(valor))
    return '(async () => {\n' + AYUDAS + cuerpo + CIERRE


# --- Las pruebas del navegador ---------------------------------------------------------------------------------

DESDE_LA_TARJETA = """
const RUTAS = __RUTAS__;
await enLaGuia();

// Cada tarjeta de arriba lleva su botón, que se lee con el nombre de la tarea.
const tarjetas = [...document.querySelectorAll(".o_dcasa_guia_rapido .o_dcasa_guia_tarea")];
if (tarjetas.length < 5) { falla("faltan las tarjetas de «En tu puesto»: " + tarjetas.length); }
for (const t of tarjetas) {
    const botones = t.querySelectorAll(".o_dcasa_guia_llevame_tarea");
    if (botones.length !== 1) { falla("cada tarjeta lleva un solo botón: " + t.dataset.tarea); }
    if (!botones[0].textContent.includes("Llévame ahí")) { falla("el botón debe decir Llévame ahí"); }
    const titulo = t.querySelector(".o_dcasa_guia_tarea_titulo").textContent.trim();
    if (!botones[0].getAttribute("aria-label").includes(titulo)) { falla("el botón debe leerse con «" + titulo + "»"); }
}

// Un clic: la pantalla del menú y la cinta abajo.
await llevarA("cobros-hoy", RUTAS["cobros-hoy"]);
const barra = cinta();
if (!barra.textContent.includes("Estás haciendo:") || !barra.textContent.includes("Ver cuánto dinero entró hoy")) {
    falla("la cinta debe decir qué haces: " + barra.textContent);
}
if (barra.getAttribute("role") !== "region") { falla("la cinta es una región con nombre"); }
const caja = barra.getBoundingClientRect();
if (Math.abs(caja.bottom - innerHeight) > 1) {
    falla("la cinta va pegada abajo: " + caja.bottom + " de " + innerHeight);
}
if (caja.left < 60) {
    falla("la cinta empieza donde empieza el contenido, no debajo de la barra lateral: " + caja.left);
}
const reservado = parseFloat(getComputedStyle(document.querySelector(".o_action_manager")).paddingBottom);
if (Math.abs(reservado - barra.offsetHeight) > 1) { falla("debe reservar su alto abajo del contenido: " + reservado); }

// «Volver a la Guía»: la Guía con esa tarea abierta, sin cinta.
[...barra.querySelectorAll("button")].find((b) => b.textContent.trim() === "Volver a la Guía").click();
await enLaGuia();
await esperar(() => tarea("cobros-hoy") && tarea("cobros-hoy").classList.contains("o_abierta"),
              "la tarea abierta al volver");
if (cinta()) { falla("al volver a la Guía la cinta se quita"); }
if (document.activeElement !== tarea("cobros-hoy").querySelector(".o_dcasa_guia_tarea_cabeza")) {
    falla("el foco queda en la tarea que estabas haciendo");
}
const abierta = tarea("cobros-hoy");
if (abierta.querySelectorAll(".o_dcasa_guia_llevame_tarea").length !== 1) {
    falla("abierta, la tarea muestra su botón una sola vez (abajo, con «Dónde queda»)");
}
if (!abierta.textContent.includes("Dónde queda")) { falla("falta «Dónde queda»"); }

// Desde un resultado del buscador: «cobrar a un cliente» abre un formulario nuevo de pago.
escribir(document.querySelector(".o_dcasa_guia_buscar"), "cobrar a un cliente");
const resultado = await esperar(() => document.querySelector(".o_dcasa_guia_tarea[data-tarea='cobrar-cliente']"),
                                "el resultado «Registrar el cobro de un cliente»");
const botonResultado = await esperar(() => resultado.querySelector(".o_dcasa_guia_llevame_tarea"), "su botón");
botonResultado.click();
await esperar(() => document.querySelector(".o_form_view"), "el formulario nuevo");
await esperar(() => location.pathname.endsWith("/new"), "la ruta de un registro nuevo: " + location.pathname);
await esperar(cinta, "la cinta tras abrir el formulario nuevo");
if (!cinta().textContent.includes("Registrar el cobro de un cliente")) { falla("la cinta del formulario nuevo"); }
// La «x» la cierra.
cinta().querySelector(".o_dcasa_guia_cinta_cerrar").click();
await esperar(() => !cinta(), "que la «x» cierre la cinta");
if (document.documentElement.style.getPropertyValue("--dc-cinta-alto")) { falla("sin cinta no se reserva lugar"); }
"""

CON_PASOS = """
const RUTAS = __RUTAS__;
await enLaGuia();
escribir(document.querySelector(".o_dcasa_guia_buscar"), "declaración de renta");
const renta = await esperar(() => document.querySelector(".o_dcasa_guia_tarea.o_abierta[data-tarea='renta']"),
                            "la declaración de renta, abierta (es el único resultado)");
const pasos = [...renta.querySelectorAll(".o_dcasa_guia_pasos > li")];
if (pasos.length !== RUTAS.length) { falla("pasos " + pasos.length + " de " + RUTAS.length); }
pasos.forEach((paso, i) => {
    const boton = paso.querySelector(".o_dcasa_guia_paso_ir");
    if (Boolean(boton) !== Boolean(RUTAS[i])) {
        falla("el paso " + (i + 1) + (RUTAS[i] ? " debe tener su Llévame ahí" : " no tiene pantalla (instrucción)"));
    }
    if (!RUTAS[i] && !paso.classList.contains("o_sin_pantalla")) {
        falla("un paso sin pantalla se marca como instrucción");
    }
    if (boton && !boton.getAttribute("aria-label").includes("paso " + (i + 1) + " de " + pasos.length)) {
        falla("el botón del paso se lee con su número");
    }
});

// El paso 3 lleva a su pantalla y la cinta dice dónde vas y cuál sigue.
pasos[2].querySelector(".o_dcasa_guia_paso_ir").click();
await esperar(cinta, "la cinta del paso 3");
await esperar(() => location.pathname === RUTAS[2],
              "la ruta del paso 3 " + RUTAS[2] + " (estás en " + location.pathname + ")");
let texto = cinta().textContent;
if (!texto.includes("Paso 3 de " + pasos.length) || !texto.includes("Siguiente: Revisa quién te debe.")) {
    falla("la cinta del paso 3: " + texto);
}
// «Llévame ahí» de la cinta: el paso siguiente.
cinta().querySelector(".o_dcasa_guia_cinta_siguiente_ir").click();
await esperar(() => location.pathname === RUTAS[3],
              "la ruta del paso 4 " + RUTAS[3] + " (estás en " + location.pathname + ")");
await esperar(() => cinta().textContent.includes("Paso 4 de " + pasos.length), "la cinta pasa al paso 4");
if (!cinta().textContent.includes("Siguiente: Revisa a quién le debes.")) {
    falla("la cinta del paso 4: " + cinta().textContent);
}

// Volver: la Guía con «Preparar la declaración de renta» abierta.
[...cinta().querySelectorAll("button")].find((b) => b.textContent.trim() === "Volver a la Guía").click();
await esperar(() => tarea("renta") && tarea("renta").classList.contains("o_abierta"), "la renta abierta al volver");
if (cinta()) { falla("al volver la cinta se quita"); }
const todos = tarea("renta").querySelectorAll(".o_dcasa_guia_paso_ir").length;
if (todos !== RUTAS.filter(Boolean).length) { falla("los pasos con pantalla vuelven a tener su botón"); }

// Un paso con pantalla seguido de uno que se hace allí mismo: «Ya lo hice» avanza sin salir.
const ultimo = pasos.length - 2;
tarea("renta").querySelectorAll(".o_dcasa_guia_paso_ir")[ultimo].click();
await esperar(() => cinta() && cinta().textContent.includes("Paso " + (ultimo + 1) + " de"),
              "la cinta del paso " + (ultimo + 1));
if (!cinta().querySelector(".o_dcasa_guia_cinta_avanzar")) {
    falla("el paso siguiente no tiene pantalla: la cinta ofrece «Ya lo hice»");
}
const ruta = location.pathname;
cinta().querySelector(".o_dcasa_guia_cinta_avanzar").click();
await esperar(() => cinta().textContent.includes("Paso " + pasos.length + " de " + pasos.length),
              "la cinta avanza al último paso");
if (location.pathname !== ruta) { falla("«Ya lo hice» no cambia de pantalla"); }
if (!cinta().textContent.includes("último paso")) { falla("la cinta avisa que es el último paso"); }
if (cinta().querySelector(".o_dcasa_guia_cinta_avanzar, .o_dcasa_guia_cinta_siguiente_ir")) {
    falla("no hay paso siguiente");
}
"""

SE_VA_SOLA = """
const RUTAS = __RUTAS__;
await enLaGuia();
await llevarA("resumen", RUTAS["resumen"]);
// Dentro de la misma pantalla, la cinta se queda.
await espera(800);
if (!cinta()) { falla("la cinta sigue mientras estás en la pantalla de la tarea"); }
// Otra pantalla distinta (Conversaciones, por la barra lateral): la cinta se va sola.
const otra = [...document.querySelectorAll(".o_dcasa_barra a")].find((a) => a.textContent.trim() === "Conversaciones");
if (!otra) { falla("la barra lateral no tiene Conversaciones"); }
otra.click();
await esperar(() => location.pathname !== RUTAS["resumen"], "que cambie la pantalla");
await esperar(() => !cinta(), "que la cinta se vaya al salir de las pantallas de la tarea");
"""

USO_POR_PERSONA = """
await enLaGuia();
// Dos veces cada una: de la tarjeta (menú) y de formularios nuevos.
const tareasUsadas = ["ventas-hoy", "cliente-nuevo", "cotizacion-nueva"];
for (const id of [...tareasUsadas, ...tareasUsadas]) {
    await llevarA(id);
    await guiaPorLaBarra();
}
// El servidor confirma lo que anotó (sin que la pantalla lo haya esperado).
const datos = await esperar(async () => {
    const d = await llamar("dcasa.guia", "obtener", []);
    return d.mas_usadas.length === 3 ? d : null;
}, "que el servidor anote los tres usos");
const vistos = Object.fromEntries(datos.mas_usadas.map((t) => [t.id, t.veces]));
if (JSON.stringify(vistos) !== JSON.stringify({ "ventas-hoy": 2, "cliente-nuevo": 2, "cotizacion-nueva": 2 })) {
    falla("el servidor contó " + JSON.stringify(vistos));
}
// La pantalla muestra «Lo que tú más usas» antes de «En tu puesto…».
await guiaPorLaBarra();
const mias = await esperar(() => document.querySelector(".o_dcasa_guia_mias"), "la sección «Lo que tú más usas»");
const titulos = [...document.querySelectorAll(".o_dcasa_guia_rapido h2")].map((h) => h.textContent.trim());
if (titulos[0] !== "Lo que tú más usas" || titulos[1] !== "En tu puesto lo que más se usa") {
    falla("el orden: " + titulos);
}
if (mias.querySelectorAll(".o_dcasa_guia_tarea").length !== 3) { falla("deben salir las 3 tareas más usadas"); }
const cuentas = [...mias.querySelectorAll(".o_dcasa_guia_tarea_veces")];
if (!cuentas.every((v) => v.textContent.includes("Lo usaste 2 veces"))) {
    falla("cada una dice cuántas veces la usaste");
}
// Lo usado no se repite abajo, en «En tu puesto».
const puesto = document.querySelector(".o_dcasa_guia_puesto");
if (puesto.querySelector("[data-tarea='ventas-hoy'], [data-tarea='cliente-nuevo'], [data-tarea='cotizacion-nueva']")) {
    falla("lo que ya sale arriba no se repite en «En tu puesto»");
}
"""

SIN_USO_ES_SOLO_LO_CURADO = """
await enLaGuia();
if (document.querySelector(".o_dcasa_guia_mias")) { falla("sin uso propio no hay «Lo que tú más usas»"); }
const titulos = [...document.querySelectorAll(".o_dcasa_guia_rapido h2")].map((h) => h.textContent.trim());
if (titulos.join("|") !== "En tu puesto lo que más se usa") { falla("solo lo curado: " + titulos); }
"""

VENDEDORA = """
await enLaGuia();
// Su puesto: lo que le toca, y nada de Gerencia.
const rol = document.querySelector(".o_dcasa_guia_rol");
if (!rol || !rol.textContent.includes("Vendedora")) { falla("el puesto debe decir Vendedora"); }
const ids = [...document.querySelectorAll(".o_dcasa_guia_puesto .o_dcasa_guia_tarea")].map((t) => t.dataset.tarea);
if (!ids.includes("cotizacion-nueva") || !ids.includes("cobrar-cliente")) { falla("faltan sus tareas: " + ids); }
for (const ajena of ["resumen", "itbms", "cierre-mes", "banco-conciliar", "ganancias", "facturas-vencidas", "renta"]) {
    if (ids.includes(ajena) || tarea(ajena)) { falla("una vendedora no ve " + ajena); }
}
// Ni buscándolo: no hay botón que lleve a contabilidad.
escribir(document.querySelector(".o_dcasa_guia_buscar"), "declaración de renta");
await esperar(() => document.querySelector(".o_dcasa_guia_vacio"), "el aviso de que no hay nada para ella");
if (tarea("renta")) { falla("la renta no sale en la búsqueda de una vendedora"); }
// Cada «Llévame ahí» de lo que sí ve abre una pantalla que ella puede abrir.
escribir(document.querySelector(".o_dcasa_guia_buscar"), "");
await esperar(() => document.querySelector(".o_dcasa_guia_puesto"), "la Guía otra vez");
await llevarA("ventas-hoy");
"""

CON_UN_FALLO = """
const RUTAS = __RUTAS__;
await enLaGuia();
// El servidor protesta al anotar el uso: el botón lleva igual y no sale ningún error en pantalla.
await llevarA("cobros-hoy", RUTAS["cobros-hoy"]);
if (document.querySelector(".o_notification, .modal")) {
    falla("un fallo al anotar el uso no debe avisarle a la persona");
}
await espera(500);
"""

CELULAR = """
const RUTAS = __RUTAS__;
await enLaGuia();
const sinDesborde = (que) => {
    if (document.documentElement.scrollWidth > innerWidth) {
        falla("hay scroll horizontal (" + que + "): " + document.documentElement.scrollWidth);
    }
    const guia = document.querySelector(".o_dcasa_guia");
    if (guia && guia.scrollWidth > guia.clientWidth + 1) { falla("la Guía se desborda (" + que + ")"); }
};
sinDesborde("inicio");
for (const boton of document.querySelectorAll(".o_dcasa_guia_rapido .o_dcasa_guia_llevame")) {
    const caja = boton.getBoundingClientRect();
    if (caja.height < 36 || caja.right > innerWidth) {
        falla("el botón es chico o se sale: " + caja.height + " " + caja.right);
    }
}
// Un paso, con la cinta abajo y sin cortarse.
escribir(document.querySelector(".o_dcasa_guia_buscar"), "declaración de renta");
const renta = await esperar(() => document.querySelector(".o_dcasa_guia_tarea.o_abierta[data-tarea='renta']"),
                            "la renta");
sinDesborde("pasos");
renta.querySelectorAll(".o_dcasa_guia_paso_ir")[2].click();
await esperar(cinta, "la cinta en el celular");
await esperar(() => location.pathname === RUTAS[2], "la ruta del paso 3");
await espera(600);
const caja = cinta().getBoundingClientRect();
if (caja.left < 0 || caja.right > innerWidth + 1) {
    falla("la cinta se sale del ancho: " + caja.left + " " + caja.right);
}
if (Math.abs(caja.bottom - innerHeight) > 1) {
    falla("la cinta va pegada abajo: " + caja.bottom + " de " + innerHeight);
}
if (caja.height > innerHeight * 0.25) {
    falla("la cinta debe ser discreta, no más de un cuarto de la pantalla: " + caja.height);
}
for (const boton of cinta().querySelectorAll("button")) {
    const b = boton.getBoundingClientRect();
    if (b.width < 28 || b.height < 28 || b.right > innerWidth + 1 || b.bottom > innerHeight + 1) {
        falla("un botón de la cinta se sale o es chico: " + boton.textContent.trim() + " " + b.width + "x" + b.height);
    }
}
sinDesborde("cinta");
cinta().querySelector(".o_dcasa_guia_cinta_cerrar").click();
await esperar(() => !cinta(), "cerrar la cinta en el celular");
"""


@tagged('post_install', '-at_install')
class TestLlevameEnElNavegador(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        grupos = [cls.env.ref('base.group_user').id, cls.env.ref('dcasa_base.group_vendedora').id]
        cls.vendedora = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Llévame Vendedora', 'login': 'llevame_vend', 'password': 'llevame_vend',
            'group_ids': [Command.set(grupos)],
        })
        cls.Uso = cls.env['dcasa.guia.uso']

    def ruta_de_menu(self, xmlid):
        """La dirección que toma el navegador al abrir ese menú (``/odoo/action-123`` o la ruta propia de la acción)."""
        accion = self.env.ref(xmlid).action
        return '/odoo/' + (accion.path or f'action-{accion.id}')

    def rutas_de_pasos(self, tarea_id):
        tarea = G.buscar_tarea(tarea_id)
        return [self.ruta_de_menu(p['destino']['menu']) if p.get('destino') else None for p in tarea['pasos']]

    def abrir_la_guia(self, codigo_js, login='admin', timeout=180):
        self.browser_js('/odoo/action-dcasa_guia.accion_guia', codigo_js, ready='odoo.isReady', login=login,
                        timeout=timeout)

    def test_desde_la_tarjeta_y_el_buscador_abre_la_pantalla_justa_y_deja_la_cinta(self):
        rutas = {'cobros-hoy': self.ruta_de_menu('dcasa_base.menu_dcasa_cobros_hoy')}
        self.abrir_la_guia(codigo(DESDE_LA_TARJETA, RUTAS=rutas))

    def test_cada_paso_con_pantalla_tiene_su_boton_y_la_cinta_los_sigue(self):
        rutas = self.rutas_de_pasos('renta')
        self.assertEqual(len(rutas), 7)
        self.assertEqual([r is None for r in rutas], [False] * 6 + [True], 'el último paso es una instrucción')
        self.abrir_la_guia(codigo(CON_PASOS, RUTAS=rutas))

    def test_la_cinta_se_va_sola_al_salir_de_las_pantallas_de_la_tarea(self):
        rutas = {'resumen': self.ruta_de_menu('dcasa_contabilidad.menu_resumen')}
        self.abrir_la_guia(codigo(SE_VA_SOLA, RUTAS=rutas))

    def test_el_uso_se_cuenta_por_persona_y_sale_lo_que_tu_mas_usas(self):
        self.abrir_la_guia(codigo(USO_POR_PERSONA), login='llevame_vend')
        propio = {f.tarea: f.veces for f in self.Uso.sudo().search([('user_id', '=', self.vendedora.id)])}
        self.assertEqual(propio, {'ventas-hoy': 2, 'cliente-nuevo': 2, 'cotizacion-nueva': 2})
        admin = self.env.ref('base.user_admin')
        self.assertFalse(self.Uso.sudo().search([('user_id', '=', admin.id)]), 'El uso de ella no es de nadie más')

    def test_sin_uso_propio_solo_sale_lo_curado(self):
        self.abrir_la_guia(codigo(SIN_USO_ES_SOLO_LO_CURADO), login='llevame_vend')

    def test_la_vendedora_no_ve_lo_de_gerencia_ni_buscandolo(self):
        self.abrir_la_guia(codigo(VENDEDORA), login='llevame_vend')

    def test_si_anotar_el_uso_falla_el_boton_lleva_igual(self):
        @api.model
        def fallar(modelo, tarea_id):
            raise UserError('El libro de uso no responde')

        rutas = {'cobros-hoy': self.ruta_de_menu('dcasa_base.menu_dcasa_cobros_hoy')}
        with mock.patch.object(type(self.env['dcasa.guia']), 'registrar_uso', fallar), \
                mute_logger('odoo.http', 'odoo.addons.dcasa_guia.models.guia'):
            self.abrir_la_guia(codigo(CON_UN_FALLO, RUTAS=rutas))
        self.assertFalse(self.Uso.sudo().search([]), 'Con el fallo no se anotó nada, y nadie lo notó')

    def test_en_el_celular_todo_cabe_y_la_cinta_es_discreta(self):
        self.browser_size = '390x844'
        rutas = self.rutas_de_pasos('renta')
        self.abrir_la_guia(codigo(CELULAR, RUTAS=rutas))
