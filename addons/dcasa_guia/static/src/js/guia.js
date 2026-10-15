/**
 * «Guía»: ¿Qué necesitas hacer hoy?
 *
 * Una pantalla para quien administra el negocio sin saber en qué menú está cada cosa: escribe lo que quiere lograr
 * o escoge un tema, lee en palabras sencillas qué va a lograr al llegar a la pantalla y la abre con «Llévame ahí».
 * El catálogo viene de dcasa.guia.obtener (ya filtrado por lo que la persona puede abrir) y el buscador de
 * dcasa.guia.buscar (sin tildes). Arriba van «Lo que tú más usas» (si hay datos) y «En tu puesto lo que más se usa».
 * «Llévame ahí» lo hace el servicio dcasa_guia_ruta (abre, anota el uso y deja la cinta de «Estás haciendo»).
 * «Preguntarle a Brian» abre su panel con la pregunta escrita (sin enviarla).
 */
import { Component, onMounted, onWillStart, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { browser } from "@web/core/browser/browser";
import { destinoPrincipal } from "./guia_ruta";

const ESPERA_BUSQUEDA = 200;

export class DcasaGuia extends Component {
    static template = "dcasa_guia.Guia";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.ruta = useService("dcasa_guia_ruta");
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
        this.raiz = useRef("raiz");
        this.tareaPedida = null;
        // Ya estás en la Guía: la cinta de «Estás haciendo» sobra.
        this.ruta.descartar();
        onWillStart(() => this.cargar());
        onMounted(() => this.mostrarTareaPedida());
    }

    async cargar() {
        this.state.datos = await this.orm.call("dcasa.guia", "obtener", []);
        this.state.cargando = false;
        this.abrirTareaPedida();
    }

    /** «Volver a la Guía» desde la cinta: la Guía llega con la tarea que la persona estaba haciendo ya abierta. */
    abrirTareaPedida() {
        const contexto = (this.props.action && this.props.action.context) || {};
        const pedida = contexto.dcasa_guia_tarea;
        if (!pedida) {
            return;
        }
        const tarea = this.categorias.flatMap((c) => c.tareas).find((t) => t.id === pedida);
        if (tarea) {
            this.state.categoria = tarea.categoria;
            this.state.abierta = tarea.id;
            this.tareaPedida = tarea.id;
        }
    }

    /** La tarea pedida queda a la vista (la lista puede ser larga) y con el foco, para quien usa el teclado. */
    mostrarTareaPedida() {
        const raiz = this.raiz.el;
        const fila = this.tareaPedida && raiz && raiz.querySelector(`[data-tarea="${this.tareaPedida}"]`);
        this.tareaPedida = null;
        if (fila) {
            fila.scrollIntoView({ block: "center" });
            const cabeza = fila.querySelector(".o_dcasa_guia_tarea_cabeza");
            if (cabeza) {
                cabeza.focus({ preventScroll: true });
            }
        }
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

    /** Lo que la persona más usa: solo cuando hay datos suficientes (lo decide el servidor). */
    get masUsadas() {
        return this.state.datos.mas_usadas || [];
    }

    /** Lo curado para su puesto, sin repetir lo que ya sale arriba en «Lo que tú más usas». */
    get delPuesto() {
        const usadas = new Set(this.masUsadas.map((t) => t.id));
        return (this.state.datos.puesto || []).filter((t) => !usadas.has(t.id));
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

    /** A dónde lleva el «Llévame ahí» de una tarea (su pantalla, o la del primer paso que tenga una). */
    destinoDe(tarea) {
        return destinoPrincipal(tarea);
    }

    /** «Llévame ahí»: abre la pantalla justa en un clic. `indice`: nulo = la tarea; un número = ese paso. */
    llevame(tarea, indice = null) {
        return this.ruta.llevar(tarea, indice);
    }

    textoVeces(veces) {
        return veces === 1 ? "Lo usaste 1 vez" : `Lo usaste ${veces} veces`;
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
