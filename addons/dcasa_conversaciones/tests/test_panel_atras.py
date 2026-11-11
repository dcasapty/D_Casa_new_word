"""El «atrás» del teléfono dentro de Conversaciones (reporte de la dueña, 2026-11-11).

En el celular la pantalla muestra una cosa a la vez (lista, chat, ficha) y abre las fotos encima; para el navegador todo
era una sola página, así que el gesto de «atrás» del iPhone sacaba a la persona de Conversaciones en vez de volver del
chat a la lista. Ahora cada cosa abierta es un paso del historial: «atrás» cierra la de más arriba y la pantalla no se
vuelve a cargar. En la computadora no cambia nada.
"""
from odoo.tests import tagged

from .test_panel_interfaz import PanelUiCase

ATRAS_JS = """
    const columna = () => {
        const clases = document.querySelector(".o_dcj")?.className || "";
        return (clases.match(/o_dcj_ver_(\\w+)/) || [])[1] || "FUERA";
    };
    const enColumna = (cual) => esperar(() => columna() === cual,
                                        "la columna «" + cual + "» (se ve «" + columna() + "»)");
    const atras = async () => { history.back(); await pausa(250); };
    const laMisma = (donde) => {
        if (document.querySelector(".o_dcj")?.dataset.marca !== "misma") {
            throw new Error("la pantalla se volvió a cargar " + donde + " (debía solo cerrar lo de arriba)");
        }
    };
"""


@tagged('post_install', '-at_install')
class TestAtrasEnElCelular(PanelUiCase):
    browser_size = '390x844'
    touch_enabled = True

    def test_atras_cierra_lo_de_arriba_y_no_saca_de_la_pantalla(self):
        self.datos_de_ejemplo()
        self.navegador(ATRAS_JS + """
(async () => {
    await esperar(() => document.querySelectorAll(".o_dcj_fila").length >= 3, "las tres conversaciones");
    // Para que haya «una pantalla anterior»: de aquí a los contactos y de vuelta a Conversaciones.
    const acciones = odoo.__WOWL_DEBUG__.root.env.services.action;
    await acciones.doAction("base.action_partner_form");
    await esperar(() => document.querySelector(".o_action_manager .o_view_controller"), "los contactos");
    await pausa(300);
    await acciones.doAction("dcasa_conversaciones.accion_conversaciones");
    await esperar(() => document.querySelectorAll(".o_dcj_fila").length >= 3, "Conversaciones otra vez");
    await pausa(300);
    document.querySelector(".o_dcj").dataset.marca = "misma";
    const ruta = location.pathname;

    // 1. Del chat, «atrás» vuelve a la lista.
    await abrirConversacion("Karen Pérez");
    await enColumna("hilo");
    await esperar(() => history.state?.dcasaPaso === 1, "el paso del chat en el historial");
    await atras();
    await enColumna("lista");
    laMisma("al volver del chat");
    if (location.pathname !== ruta) { throw new Error("«atrás» sacó de Conversaciones: " + location.pathname); }

    // 2. Con una foto abierta, «atrás» cierra la foto y deja el chat.
    await abrirConversacion("Karen Pérez");
    await enColumna("hilo");
    (await esperar(() => document.querySelector(".o_dcj_foto_boton"), "la foto del chat")).click();
    await esperar(() => document.querySelector(".o_dcj_visor"), "la foto ampliada");
    await pausa(150);
    await atras();
    await esperar(() => !document.querySelector(".o_dcj_visor"), "que «atrás» cierre la foto");
    if (columna() !== "hilo") { throw new Error("tras cerrar la foto se sigue en el chat y se ve: " + columna()); }

    // 3. Con la ficha del cliente abierta, «atrás» vuelve al chat; otro «atrás», a la lista.
    document.querySelector(".o_dcj_boton_ficha").click();
    await enColumna("ficha");
    await pausa(150);
    await atras();
    await enColumna("hilo");
    await atras();
    await enColumna("lista");
    laMisma("al volver de la ficha y del chat");

    // 4. Volver con la flecha de la pantalla quita su paso: el siguiente «atrás» ya sale a la pantalla anterior.
    await abrirConversacion("Karen Pérez");
    await enColumna("hilo");
    document.querySelector(".o_dcj_volver").click();
    await enColumna("lista");
    await pausa(500);
    laMisma("al volver con la flecha");
    await atras();
    await esperar(
        () => !document.querySelector(".o_dcj") && document.querySelector(".o_action_manager .o_view_controller"),
        "la pantalla anterior (los contactos) al dar «atrás» desde la lista; se ve " + location.pathname);
    console.log("test successful");
})();
""")

    def test_al_recargar_desde_la_lista_no_reabre_el_chat_que_se_dejo(self):
        self.datos_de_ejemplo()
        self.navegador(ATRAS_JS + """
(async () => {
    await esperar(() => document.querySelectorAll(".o_dcj_fila").length >= 3, "las tres conversaciones");
    await abrirConversacion("Karen Pérez");
    await enColumna("hilo");
    if (!sessionStorage.getItem("dcasa.conversaciones.abierta")) {
        throw new Error("con el chat a la vista se recuerda cuál es");
    }
    document.querySelector(".o_dcj_volver").click();
    await enColumna("lista");
    await esperar(() => !sessionStorage.getItem("dcasa.conversaciones.abierta"),
                  "que, de vuelta en la lista, ya no se recuerde un chat abierto");
    console.log("test successful");
})();
""")


@tagged('post_install', '-at_install')
class TestAtrasEnLaComputadora(PanelUiCase):
    browser_size = '1366x768'

    def test_en_la_computadora_abrir_un_chat_no_toca_el_historial(self):
        self.datos_de_ejemplo()
        self.navegador("""
(async () => {
    await esperar(() => document.querySelectorAll(".o_dcj_fila").length >= 3, "las tres conversaciones");
    const antes = history.length;
    await abrirConversacion("Karen Pérez");
    await pausa(400);
    if (history.length !== antes || history.state?.dcasaPaso) {
        throw new Error("en la computadora el chat va al lado de la lista: no se agregan pasos al historial");
    }
    if (!sessionStorage.getItem("dcasa.conversaciones.abierta")) {
        throw new Error("se recuerda la conversación abierta");
    }
    console.log("test successful");
})();
""")
