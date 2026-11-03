/**
 * La lista de conversaciones (columna izquierda): filtros, búsqueda y carga de 30 en 30 al bajar.
 */
import { Component, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { ANCHO_LISTA_MAX, ANCHO_LISTA_MIN, ANCHO_LISTA_NORMAL } from "./almacen";
import { colorDeEtiqueta, horaDeLista, iconoDeCanal, iniciales } from "./utilidades";

/** Con las flechas del teclado el borde se mueve de a tanto. */
const PASO_CON_TECLADO = 20;

const ESTADOS = [
    { id: "", nombre: "Todos los estados" },
    { id: "necesita_atencion", nombre: "Necesita atención" },
    { id: "bot", nombre: "Con el asistente" },
    { id: "humano", nombre: "Con una vendedora" },
    { id: "cerrada", nombre: "Cerradas" },
];
const ESPERA_BUSQUEDA = 300;
const CERCA_DEL_FINAL = 240;

export class ListaConversaciones extends Component {
    static template = "dcasa_conversaciones.Lista";
    static props = { almacen: Object };

    setup() {
        this.almacen = useState(this.props.almacen);
        this.local = useState({ filtros: false, busqueda: this.almacen.filtros.busqueda, arrastrando: false });
        this.refLista = useRef("lista");
        this.refColumna = useRef("columna");
        this.anchoMin = ANCHO_LISTA_MIN;
        this.anchoMax = ANCHO_LISTA_MAX;
        this.anchoNormal = ANCHO_LISTA_NORMAL;
        this.estados = ESTADOS;
        this.iconoDeCanal = iconoDeCanal;
        this.iniciales = iniciales;
        this.horaDeLista = (iso) => horaDeLista(iso, this.almacen.ahora);
        this.colorDeEtiqueta = colorDeEtiqueta;
        onMounted(() => {
            this.temporizador = null;
        });
        onWillUnmount(() => {
            clearTimeout(this.temporizador);
            this.terminarArrastre?.();
        });
    }

    /** El ancho que se ve ahora (el de la columna en pantalla; lo que eligió la persona puede no caber). */
    get anchoActual() {
        return this.almacen.anchoLista || ANCHO_LISTA_NORMAL;
    }

    /** Arrastrar el borde: la lista sigue al puntero y, al soltar, el ancho queda recordado en este navegador. */
    empezarArrastre(ev) {
        if (ev.button !== undefined && ev.button !== 0) {
            return;
        }
        const columna = this.refColumna.el;
        if (!columna) {
            return;
        }
        ev.preventDefault();
        const izquierda = columna.getBoundingClientRect().left;
        const tirador = ev.currentTarget;
        try {
            tirador.setPointerCapture?.(ev.pointerId);
        } catch {
            /* sin captura del puntero: se escucha en el documento igual */
        }
        this.local.arrastrando = true;
        document.body.classList.add("o_dcj_arrastrando_ancho");
        const mover = (e) => this.almacen.ponerAnchoLista(e.clientX - izquierda);
        const soltar = () => this.terminarArrastre?.();
        this.terminarArrastre = () => {
            document.removeEventListener("pointermove", mover);
            document.removeEventListener("pointerup", soltar);
            document.removeEventListener("pointercancel", soltar);
            document.body.classList.remove("o_dcj_arrastrando_ancho");
            this.local.arrastrando = false;
            this.terminarArrastre = null;
            this.almacen.recordarAnchoLista();
        };
        document.addEventListener("pointermove", mover);
        document.addEventListener("pointerup", soltar);
        document.addEventListener("pointercancel", soltar);
    }

    anchoConTeclado(ev) {
        const pasos = { ArrowLeft: -PASO_CON_TECLADO, ArrowRight: PASO_CON_TECLADO };
        if (ev.key in pasos) {
            ev.preventDefault();
            this.almacen.ponerAnchoLista(this.anchoActual + pasos[ev.key], true);
        } else if (ev.key === "Home" || ev.key === "End") {
            ev.preventDefault();
            this.almacen.ponerAnchoLista(ev.key === "Home" ? ANCHO_LISTA_MIN : ANCHO_LISTA_MAX, true);
        }
    }

    get hayFiltros() {
        return this.almacen.filtrosActivos > 0 || this.almacen.filtros.busqueda.trim() !== "";
    }

    estadoVisual(c) {
        if (c.necesita_atencion) {
            return { texto: "Necesita atención", clase: "atencion" };
        }
        if (c.estado === "cerrada") {
            return { texto: "Cerrada", clase: "cerrada" };
        }
        if (c.estado === "humano") {
            return { texto: "Una vendedora", clase: "humano" };
        }
        return { texto: "Asistente", clase: "bot" };
    }

    /** Cuánto lleva esperando un cliente a quien una persona debe contestar: { texto, urgente } o null. */
    esperaDe(c) {
        if (!c.esperando_desde) {
            return null;
        }
        const minutos = Math.max(0, Math.floor((this.almacen.ahora - Date.parse(c.esperando_desde)) / 60000));
        const umbral = this.almacen.limites?.espera_aviso_minutos || 0;
        const texto = minutos < 1 ? "Acaba de escribir" : minutos < 60 ? `Espera ${minutos} min` : `Espera ${Math.floor(minutos / 60)} h`;
        return { texto, urgente: umbral > 0 && minutos >= umbral };
    }

    /** «Ana» o «Ana +1»: quién más tiene abierta esa conversación (y si le está escribiendo al cliente). */
    viendo(c) {
        const gente = this.almacen.quienVe(c.id);
        if (!gente.length) {
            return null;
        }
        return {
            texto: gente.length > 1 ? `${gente[0].nombre} +${gente.length - 1}` : gente[0].nombre,
            escribe: gente.some((g) => g.escribiendo),
            titulo: gente.map((g) => `${g.nombre}${g.escribiendo ? " está escribiéndole al cliente" : " la tiene abierta"}`).join(" · "),
        };
    }

    quienDijo(c) {
        const autor = c.ultimo_mensaje?.autor;
        return autor === "bot" ? "Asistente: " : autor === "vendedora" ? "Tú o una vendedora: " : "";
    }

    textoUltimo(c) {
        return c.ultimo_mensaje?.texto || "Sin mensajes todavía";
    }

    alBuscar(ev) {
        this.local.busqueda = ev.target.value;
        clearTimeout(this.temporizador);
        this.temporizador = setTimeout(() => this.almacen.cambiarFiltro("busqueda", this.local.busqueda), ESPERA_BUSQUEDA);
    }

    borrarBusqueda() {
        this.local.busqueda = "";
        clearTimeout(this.temporizador);
        this.almacen.cambiarFiltro("busqueda", "");
    }

    alElegirEtiqueta(ev) {
        this.almacen.cambiarFiltro("etiqueta_id", Number(ev.target.value) || 0);
    }

    limpiar() {
        this.local.busqueda = "";
        this.almacen.limpiarFiltros();
    }

    alDesplazar() {
        const el = this.refLista.el;
        if (el && el.scrollHeight - el.scrollTop - el.clientHeight < CERCA_DEL_FINAL) {
            this.almacen.cargarMas();
        }
    }

    /** Flecha arriba/abajo pasa de una conversación a otra sin soltar el teclado. */
    alTeclear(ev) {
        if (ev.key !== "ArrowDown" && ev.key !== "ArrowUp") {
            return;
        }
        const filas = [...this.refLista.el.querySelectorAll(".o_dcj_fila")];
        const i = filas.indexOf(document.activeElement);
        if (i < 0) {
            return;
        }
        const destino = filas[ev.key === "ArrowDown" ? i + 1 : i - 1];
        if (destino) {
            ev.preventDefault();
            destino.focus();
        }
    }
}
