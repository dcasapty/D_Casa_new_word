/**
 * «Guía»: ¿Qué necesitas hacer hoy?
 *
 * Una pantalla para quien administra el negocio sin saber en qué menú está cada cosa: escribe lo que quiere lograr
 * o escoge un tema, lee en palabras sencillas qué va a lograr al llegar a la pantalla y la abre con un botón.
 * El catálogo viene de dcasa.guia.obtener (ya filtrado por lo que la persona puede abrir) y el buscador de
 * dcasa.guia.buscar (sin tildes). «Preguntarle a Brian» abre su panel con la pregunta escrita (sin enviarla).
 */
import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { browser } from "@web/core/browser/browser";

const ESPERA_BUSQUEDA = 200;

export class DcasaGuia extends Component {
    static template = "dcasa_guia.Guia";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.menu = useService("menu");
        this.notification = useService("notification");
        this.state = useState({
            cargando: true,
            datos: null,
            categoria: null, // clave de la categoría abierta
            abierta: null, // id de la tarea desplegada
            consulta: "",
            resultados: null, // null = sin búsqueda; lista = resultados
            buscando: false,
        });
        this.temporizador = null;
        this.envio = 0;
        onWillStart(() => this.cargar());
    }

    async cargar() {
        this.state.datos = await this.orm.call("dcasa.guia", "obtener", []);
        this.state.cargando = false;
    }

    // ------------------------------------------------------------------
    // Lo que se ve
    // ------------------------------------------------------------------

    get categorias() {
        return this.state.datos.categorias;
    }

    get categoriaAbierta() {
        return this.categorias.find((c) => c.clave === this.state.categoria);
    }

    /** Las tareas de la categoría abierta, agrupadas por subtema (en el orden del catálogo). */
    get grupos() {
        const categoria = this.categoriaAbierta;
        if (!categoria) {
            return [];
        }
        const grupos = [];
        for (const tarea of categoria.tareas) {
            let grupo = grupos.find((g) => g.nombre === tarea.grupo);
            if (!grupo) {
                grupo = { nombre: tarea.grupo, tareas: [] };
                grupos.push(grupo);
            }
            grupo.tareas.push(tarea);
        }
        return grupos;
    }

    get hayBrian() {
        return Boolean(this.env.services.dcasa_brian);
    }

    nombreDeCategoria(tarea) {
        const categoria = this.categorias.find((c) => c.clave === tarea.categoria);
        return categoria ? categoria.titulo : "";
    }

    // ------------------------------------------------------------------
    // Navegación dentro de la Guía
    // ------------------------------------------------------------------

    abrirCategoria(clave) {
        this.state.categoria = clave;
        this.state.abierta = null;
        this.limpiarBusqueda();
    }

    volver() {
        this.state.categoria = null;
        this.state.abierta = null;
    }

    alternar(tarea) {
        this.state.abierta = this.state.abierta === tarea.id ? null : tarea.id;
    }

    // ------------------------------------------------------------------
    // Buscar
    // ------------------------------------------------------------------

    alEscribir(ev) {
        const texto = ev.target.value;
        this.state.consulta = texto;
        browser.clearTimeout(this.temporizador);
        if (!texto.trim()) {
            this.limpiarBusqueda(false);
            return;
        }
        this.temporizador = browser.setTimeout(() => this.buscar(texto), ESPERA_BUSQUEDA);
    }

    async buscar(texto) {
        const mio = ++this.envio;
        this.state.buscando = true;
        try {
            const resultados = await this.orm.call("dcasa.guia", "buscar", [texto]);
            if (mio === this.envio) {
                this.state.resultados = resultados;
                this.state.abierta = resultados.length === 1 ? resultados[0].id : null;
            }
        } finally {
            if (mio === this.envio) {
                this.state.buscando = false;
            }
        }
    }

    limpiarBusqueda(borrarTexto = true) {
        browser.clearTimeout(this.temporizador);
        this.envio++;
        if (borrarTexto) {
            this.state.consulta = "";
        }
        this.state.resultados = null;
        this.state.buscando = false;
    }

    // ------------------------------------------------------------------
    // Llegar a la pantalla
    // ------------------------------------------------------------------

    /** Abre el destino de una tarea o de un paso: un menú (con filtros opcionales) o un formulario nuevo. */
    abrir(destino) {
        if (!destino) {
            return;
        }
        if (destino.tipo === "menu") {
            const menu = this.menu.getMenu(destino.menu_id);
            if (!menu || !menu.actionID) {
                this.notification.add("Esa pantalla no está disponible ahora.", { type: "warning" });
                return;
            }
            this.action.doAction(menu.actionID, {
                clearBreadcrumbs: true,
                additionalContext: destino.contexto || {},
                onActionReady: () => this.menu.setCurrentMenu(menu),
            });
        } else if (destino.tipo === "nuevo") {
            this.action.doAction({
                type: "ir.actions.act_window",
                res_model: destino.modelo,
                views: [[false, "form"]],
                context: destino.contexto || {},
            });
        }
    }

    /** Abre el panel de Brian con la pregunta escrita; la persona decide si la envía. */
    preguntarABrian(texto) {
        const brian = this.env.services.dcasa_brian;
        if (brian && brian.preguntar) {
            brian.preguntar(texto);
        }
    }

    preguntaDe(tarea) {
        return tarea.brian || `¿Cómo hago esto? ${tarea.titulo}`;
    }
}

registry.category("actions").add("dcasa_guia", DcasaGuia);
