/**
 * El hilo de la conversación (columna central): burbujas por autor, fotos y documentos, notas internas, avisos del
 * sistema, carga hacia atrás de 50 en 50, arrastrar y soltar archivos, y la caja de respuesta abajo.
 */
import { Component, onMounted, onPatched, onWillPatch, onWillUnmount, useRef, useState } from "@odoo/owl";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { useService } from "@web/core/utils/hooks";
import { CajaRespuesta } from "./caja";
import {
    colorDeEtiqueta,
    cuando,
    elementosDelHilo,
    hora,
    iconoDeArchivo,
    iconoDeCanal,
    iniciales,
    tamano,
} from "./utilidades";

const CERCA_DEL_FONDO = 90;
const CERCA_DEL_TOPE = 140;
// El asistente espera ~15 s a que el cliente termine de escribir; en ese rato se ve «preparando la respuesta».
const VENTANA_ESPERA_MS = 20_000;
// Cuando el Worker avisa que empezó a escribir, se ve «escribiendo» hasta que avise que terminó (o pase este tiempo).
const VENTANA_ESCRIBIENDO_MS = 60_000;

export class Burbuja extends Component {
    static template = "dcasa_conversaciones.Burbuja";
    static props = { m: Object, almacen: Object, nombreCliente: String };

    setup() {
        this.almacen = useState(this.props.almacen);
        this.hora = hora;
        this.tamano = tamano;
        this.iconoDeArchivo = iconoDeArchivo;
    }

    get autor() {
        const m = this.props.m;
        if (m.tipo === "nota") {
            return `Nota interna · ${m.usuario?.nombre || "una vendedora"}`;
        }
        if (m.autor === "cliente") {
            return this.props.nombreCliente;
        }
        if (m.autor === "bot") {
            return "Asistente";
        }
        return m.usuario?.nombre || "Vendedora (desde el teléfono)";
    }

    get clase() {
        const m = this.props.m;
        return m.tipo === "nota" ? "nota" : m.autor;
    }

    get imagenes() {
        return this.props.m.adjuntos.filter((a) => a.tipo === "imagen");
    }

    get documentos() {
        return this.props.m.adjuntos.filter((a) => a.tipo !== "imagen");
    }

    get estadoDeEnvio() {
        const m = this.props.m;
        if (m.estado_envio === "por_enviar") {
            return { clase: "pendiente", texto: "Por enviar: se reintenta solo", reintentar: true };
        }
        if (m.estado_envio === "fallido") {
            return { clase: "fallido", texto: `No se pudo enviar${m.error ? `: ${m.error}` : ""}`, reintentar: true };
        }
        return null;
    }

    abrirImagen(adjunto) {
        const todas = this.almacen.mensajes.flatMap((m) => m.adjuntos.filter((a) => a.tipo === "imagen"));
        const indice = Math.max(0, todas.findIndex((a) => a.id === adjunto.id));
        this.almacen.abrirVisor(
            todas.map((a) => ({ id: a.id, url: a.url, miniatura: a.miniatura, nombre: a.nombre })),
            indice
        );
    }
}

export class HiloConversacion extends Component {
    static template = "dcasa_conversaciones.Hilo";
    static components = { Burbuja, CajaRespuesta };
    static props = { almacen: Object };

    setup() {
        this.almacen = useState(this.props.almacen);
        this.dialog = useService("dialog");
        this.local = useState({ arrastrando: false, resumenDe: null });
        this.refCuerpo = useRef("cuerpo");
        this.elementosDelHilo = (mensajes) => elementosDelHilo(mensajes, this.almacen.ahora);
        this.iconoDeCanal = iconoDeCanal;
        this.iniciales = iniciales;
        this.colorDeEtiqueta = colorDeEtiqueta;
        this.cuando = (iso) => cuando(iso, this.almacen.ahora);
        this._conversacionVista = null;
        this._primerId = null;
        this._ultimoId = null;
        this._arrastresAnidados = 0;

        onWillPatch(() => {
            const el = this.refCuerpo.el;
            if (el) {
                this._alturaAntes = el.scrollHeight;
                this._cercaDelFondo = el.scrollHeight - el.scrollTop - el.clientHeight < CERCA_DEL_FONDO;
            }
        });
        onPatched(() => this.acomodarElDesplazamiento());
        onMounted(() => this.acomodarElDesplazamiento());
        onWillUnmount(() => (this._arrastresAnidados = 0));
    }

    /** Al abrir una conversación, al fondo; al traer mensajes viejos, sin saltar; con uno nuevo, al fondo si ya estabas ahí. */
    acomodarElDesplazamiento() {
        const el = this.refCuerpo.el;
        const mensajes = this.almacen.mensajes;
        if (!el) {
            return;
        }
        const primero = mensajes[0]?.id ?? null;
        const ultimo = mensajes[mensajes.length - 1]?.id ?? null;
        if (this._conversacionVista !== this.almacen.seleccionadaId && mensajes.length) {
            this._conversacionVista = this.almacen.seleccionadaId;
            el.scrollTop = el.scrollHeight;
        } else if (this._primerId !== null && primero !== null && primero < this._primerId) {
            el.scrollTop += el.scrollHeight - (this._alturaAntes || 0);
        } else if (ultimo !== this._ultimoId && (this._cercaDelFondo || this.esMio(mensajes[mensajes.length - 1]))) {
            el.scrollTop = el.scrollHeight;
        }
        if (el.scrollHeight - el.scrollTop - el.clientHeight < CERCA_DEL_FONDO && this.almacen.nuevosSinVer) {
            this.almacen.nuevosSinVer = 0;
        }
        this._primerId = primero;
        this._ultimoId = ultimo;
    }

    esMio(m) {
        return !!m && m.autor === "vendedora" && m.usuario?.id === this.almacen.usuario.id;
    }

    alDesplazar() {
        const el = this.refCuerpo.el;
        if (!el) {
            return;
        }
        if (el.scrollTop < CERCA_DEL_TOPE) {
            this.almacen.cargarAntes();
        }
        if (this.almacen.nuevosSinVer && el.scrollHeight - el.scrollTop - el.clientHeight < CERCA_DEL_FONDO) {
            this.almacen.nuevosSinVer = 0;
        }
    }

    irAlFondo() {
        const el = this.refCuerpo.el;
        if (el) {
            el.scrollTop = el.scrollHeight;
        }
        this.almacen.nuevosSinVer = 0;
    }

    get nombreDelCliente() {
        return this.almacen.conversacion?.nombre || "Cliente";
    }

    /**
     * Lo que se ve debajo del último mensaje mientras el asistente trabaja: «escribiendo» (el Worker lo avisó de verdad) o,
     * antes de eso, «preparando la respuesta» (el cliente acaba de escribir y el asistente espera a que termine).
     */
    get escribiendo() {
        const c = this.almacen.conversacion;
        if (!c || !c.bot_atiende || !this.almacen.bot.conectado || !this.almacen.bot.encendido) {
            return null;
        }
        const aviso = this.almacen.escribiendoBot[c.id] || 0;
        if (aviso && this.almacen.ahora - aviso < VENTANA_ESCRIBIENDO_MS) {
            return "El asistente está escribiendo…";
        }
        const ultimo = this.almacen.mensajes.filter((m) => m.tipo === "mensaje").at(-1);
        if (ultimo && ultimo.autor === "cliente" && this.almacen.ahora - new Date(ultimo.ts).getTime() < VENTANA_ESPERA_MS) {
            return "El asistente está preparando la respuesta…";
        }
        return null;
    }

    /** ¿Se ofrece «Resumir»? Con la función encendida y una conversación con algo que leer. */
    get puedeResumir() {
        return this.almacen.resumenActivo && this.almacen.mensajes.filter((m) => m.tipo === "mensaje").length >= 4;
    }

    /** El resumen guardado, en líneas, con cuándo se hizo y si ya no cubre los mensajes nuevos. */
    get resumen() {
        const r = this.almacen.resumen;
        if (!r) {
            return null;
        }
        return {
            lineas: r.texto.split("\n").map((l) => l.replace(/^•\s*/, "").trim()).filter(Boolean),
            cuando: r.generado_en ? this.cuando(r.generado_en) : "",
            desactualizado: r.vigente === false,
        };
    }

    /** Las otras personas que tienen abierta esta conversación: «Ana está viendo esta conversación». */
    get presencia() {
        const gente = this.almacen.quienVe(this.almacen.seleccionadaId);
        if (!gente.length) {
            return null;
        }
        const escriben = gente.filter((g) => g.escribiendo).map((g) => g.nombre);
        const nombres = (lista) => (lista.length > 1 ? `${lista.slice(0, -1).join(", ")} y ${lista.at(-1)}` : lista[0]);
        if (escriben.length) {
            return { texto: `${nombres(escriben)} ${escriben.length > 1 ? "están escribiéndole" : "está escribiéndole"} al cliente…`, escribe: true };
        }
        const verbo = gente.length > 1 ? "están viendo" : "está viendo";
        return { texto: `${nombres(gente.map((g) => g.nombre))} ${verbo} esta conversación`, escribe: false };
    }

    get subtitulo() {
        const c = this.almacen.conversacion;
        const ficha = this.almacen.ficha;
        const partes = [c?.canal_nombre];
        if (ficha?.cliente?.celular) {
            partes.push(ficha.cliente.celular);
        }
        return partes.filter(Boolean).join(" · ");
    }

    get estadoDelHeader() {
        const c = this.almacen.conversacion;
        if (!c) {
            return null;
        }
        if (c.necesita_atencion) {
            return { clase: "atencion", texto: "Necesita atención" };
        }
        if (c.estado === "cerrada") {
            return { clase: "cerrada", texto: "Cerrada" };
        }
        if (c.estado === "humano") {
            return { clase: "humano", texto: c.asignada_a ? `Atiende ${c.asignada_a.nombre}` : "Con una vendedora" };
        }
        return { clase: "bot", texto: "Atiende el asistente" };
    }

    volver() {
        this.almacen.volverALaLista();
    }

    /** «Cliente»: abre o cierra la ficha (al lado en pantallas amplias, encima en las demás, otra pantalla en celular). */
    abrirFicha() {
        this.almacen.alternarFicha();
    }

    /** El resumen nace plegado en una línea (en cada conversación) para no quitarle espacio a los mensajes. */
    get resumenAbierto() {
        return this.local.resumenDe === this.almacen.seleccionadaId;
    }

    alternarResumen() {
        this.local.resumenDe = this.resumenAbierto ? null : this.almacen.seleccionadaId;
    }

    async cerrarConversacion() {
        await this.almacen.cerrar();
    }

    /** Solo Gerencia. Siempre con confirmación: borra la conversación, sus mensajes y archivos, y lo que el bot recuerda. */
    confirmarEliminar() {
        const nombre = this.almacen.conversacion?.nombre || "esta persona";
        this.dialog.add(ConfirmationDialog, {
            title: "¿Eliminar esta conversación?",
            body: `Se borra la conversación con ${nombre}, con sus mensajes y archivos, y el asistente deja de recordarla. No se puede deshacer. La oportunidad y la ficha del cliente se quedan.`,
            confirmLabel: "Sí, eliminar",
            confirmClass: "btn-danger",
            cancelLabel: "No, dejarla",
            confirm: () => this.almacen.eliminar(),
            cancel: () => {},
        });
    }

    // --- Arrastrar y soltar archivos ---------------------------------------------------------------

    llevaArchivos(ev) {
        return [...(ev.dataTransfer?.types || [])].includes("Files");
    }

    alEntrarConArchivos(ev) {
        if (this.llevaArchivos(ev)) {
            ev.preventDefault();
            this._arrastresAnidados++;
            this.local.arrastrando = true;
        }
    }

    alPasarConArchivos(ev) {
        if (this.llevaArchivos(ev)) {
            ev.preventDefault();
            ev.dataTransfer.dropEffect = "copy";
        }
    }

    alSalirConArchivos(ev) {
        if (this.llevaArchivos(ev)) {
            this._arrastresAnidados = Math.max(0, this._arrastresAnidados - 1);
            if (!this._arrastresAnidados) {
                this.local.arrastrando = false;
            }
        }
    }

    alSoltarArchivos(ev) {
        if (!this.llevaArchivos(ev)) {
            return;
        }
        ev.preventDefault();
        this._arrastresAnidados = 0;
        this.local.arrastrando = false;
        this.almacen.agregarArchivos([...ev.dataTransfer.files]);
    }
}
