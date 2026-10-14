/**
 * La caja de respuesta (abajo del hilo): Atender / Devolver con el vencimiento a la vista, escribir, adjuntar con
 * vista previa, respuestas rápidas con «/», «Sugerir», foto del catálogo, cotización y notas internas.
 * Es compacta a propósito (docs/JUAN_ODOO.md, «Tamaños probados»): una franja, una línea de escribir con las
 * herramientas como íconos, y el menú «Más» para lo menos usado. Lo demás aparece solo cuando hace falta.
 */
import { Component, onMounted, onPatched, useExternalListener, useRef, useState } from "@odoo/owl";
import { atajoEnCurso, coincideConNombre, cuando, enCuanto, hora, iconoDeArchivo, mencionEnCurso, mensajeDeError, tamano } from "./utilidades";

// Hasta dónde crece la caja de texto (unas 4 líneas); el SCSS la limita además a una parte del alto de la ventana.
const ALTO_MAXIMO = 100;
// Lo mismo que el servidor: entre 1 minuto y 30 días desde ahora (con un margen para que no rebote por segundos).
const MIN_PROGRAMADO_MS = 90_000;
const MAX_PROGRAMADO_MS = 30 * 24 * 3600 * 1000;

export class CajaRespuesta extends Component {
    static template = "dcasa_conversaciones.Caja";
    static props = { almacen: Object };

    setup() {
        this.almacen = useState(this.props.almacen);
        this.local = useState({
            devolviendo: false,
            notaParaElBot: "",
            enviando: false,
            sugiriendo: false,
            avisos: [],
            opcion: 0,
            rapidasAbiertas: false,
            programando: false,
            cursor: 0,
            masAbierto: false,
        });
        this.refCaja = useRef("caja");
        this.refTexto = useRef("texto");
        this.refArchivo = useRef("archivo");
        this.refMas = useRef("mas");
        this._enfocar = null; // qué enfocar cuando termine de pintarse (el menú «Más», la fecha de programar)
        // Un clic fuera del menú «Más» lo cierra.
        useExternalListener(window, "mousedown", (ev) => {
            if (this.local.masAbierto && !this.refMas.el?.contains(ev.target)) {
                this.local.masAbierto = false;
            }
        });
        this.iconoDeArchivo = iconoDeArchivo;
        this.tamano = tamano;
        this.cuando = (iso) => cuando(iso, this.almacen.ahora);
        this.esTactil = window.matchMedia?.("(pointer: coarse)")?.matches;
        this._conversacion = null;
        onMounted(() => this.ajustarAlto());
        onPatched(() => {
            this.ajustarAlto();
            if (this._conversacion !== this.almacen.seleccionadaId) {
                this._conversacion = this.almacen.seleccionadaId;
                this.local.devolviendo = false;
                this.local.avisos = [];
                this.local.rapidasAbiertas = false;
                this.local.masAbierto = false;
                this.local.programando = !!this.borrador.programarPara;
            }
            this.enfocarLoPendiente();
        });
    }

    /** Cuando algo se acaba de abrir (el menú «Más», la fecha de programar), el foco va a su primer control. */
    enfocarLoPendiente() {
        const destino = this._enfocar;
        this._enfocar = null;
        if (destino === "menu") {
            this.refMas.el?.querySelector("[role=menuitem]:not([disabled])")?.focus();
        } else if (destino === "fecha") {
            this.refCaja.el?.querySelector(".o_dcj_programar input")?.focus();
        }
    }

    /** ¿Hay algo para mostrar entre la franja y la línea de escribir? (si no, esa zona ni existe) */
    get hayExtras() {
        return !!(
            this.almacen.programados.length ||
            this.local.devolviendo ||
            this.borrador.adjuntos.length ||
            (this.esNota && this.mencionadas.length) ||
            this.programando ||
            this.local.avisos.length
        );
    }

    // --- El menú «Más» -------------------------------------------------------------------------------

    alternarMas() {
        this.local.masAbierto = !this.local.masAbierto;
        this._enfocar = this.local.masAbierto ? "menu" : null;
    }

    cerrarMas(devolverElFoco) {
        this.local.masAbierto = false;
        if (devolverElFoco) {
            this.refMas.el?.querySelector(".o_dcj_mas_boton")?.focus();
        }
    }

    /** Esc cierra y devuelve el foco al botón; Tab cierra; las flechas recorren las opciones. */
    alTeclearMas(ev) {
        if (!this.local.masAbierto) {
            return;
        }
        if (ev.key === "Escape") {
            ev.preventDefault();
            ev.stopPropagation();
            this.cerrarMas(true);
        } else if (ev.key === "Tab") {
            this.cerrarMas(false);
        } else if (["ArrowDown", "ArrowUp", "Home", "End"].includes(ev.key)) {
            const opciones = [...this.refMas.el.querySelectorAll("[role=menuitem]:not([disabled])")];
            if (!opciones.length) {
                return;
            }
            ev.preventDefault();
            const i = opciones.indexOf(document.activeElement);
            const n = opciones.length;
            const destino =
                ev.key === "Home" ? 0 : ev.key === "End" ? n - 1 : ev.key === "ArrowDown" ? (i + 1) % n : i < 0 ? n - 1 : (i - 1 + n) % n;
            opciones[destino].focus();
        }
    }

    programarDesdeElMenu() {
        this.alternarProgramar();
        this.local.masAbierto = false;
        if (this.programando) {
            this._enfocar = "fecha";
        } else {
            this.refTexto.el?.focus();
        }
    }

    get borrador() {
        return this.almacen.borrador;
    }

    get c() {
        return this.almacen.conversacion;
    }

    get esNota() {
        return this.borrador.modo === "nota";
    }

    get limite() {
        return this.esNota ? this.almacen.limites.nota : this.almacen.limites.respuesta;
    }

    get subiendo() {
        return this.borrador.adjuntos.some((a) => a.estado === "subiendo");
    }

    get listos() {
        return this.borrador.adjuntos.filter((a) => a.estado === "listo");
    }

    get puedeEnviar() {
        if (this.local.enviando || this.subiendo || !this.c || this.programadaInvalida) {
            return false;
        }
        const texto = this.borrador.texto.trim();
        if (this.esNota) {
            return texto.length > 0 && texto.length <= this.limite;
        }
        return (texto.length > 0 || this.listos.length > 0) && texto.length <= this.limite;
    }

    // --- Programar un mensaje para más tarde ---------------------------------------------------------

    /** La fecha y hora elegidas como las entiende el navegador (hora local de quien escribe), o null. */
    get fechaProgramada() {
        const valor = this.borrador.programarPara;
        const fecha = valor ? new Date(valor) : null;
        return fecha && !Number.isNaN(fecha.getTime()) ? fecha : null;
    }

    /** Con el selector abierto hay que elegir una hora válida; si no, Enviar espera (no manda «ya» por descuido). */
    get programadaInvalida() {
        if (!this.programando) {
            return false;
        }
        const fecha = this.fechaProgramada;
        if (!fecha) {
            return true;
        }
        const falta = fecha.getTime() - Date.now();
        return falta < MIN_PROGRAMADO_MS || falta > MAX_PROGRAMADO_MS;
    }

    /** Lo que la caja manda al servidor: la hora en UTC (ISO), o null para enviar ya. */
    get programarIso() {
        return this.programando && this.fechaProgramada ? this.fechaProgramada.toISOString() : null;
    }

    get programando() {
        return !this.esNota && (this.local.programando || !!this.borrador.programarPara);
    }

    /** Para el campo de fecha: la hora más temprana que se acepta, en la hora local del navegador. */
    get minimoProgramable() {
        return this.formatoLocal(new Date(Date.now() + MIN_PROGRAMADO_MS));
    }

    formatoLocal(fecha) {
        const pad = (n) => String(n).padStart(2, "0");
        return `${fecha.getFullYear()}-${pad(fecha.getMonth() + 1)}-${pad(fecha.getDate())}T${pad(fecha.getHours())}:${pad(fecha.getMinutes())}`;
    }

    alternarProgramar() {
        this.local.programando = !this.local.programando;
        if (!this.local.programando) {
            this.borrador.programarPara = "";
            this.refTexto.el?.focus();
        }
    }

    /** Atajos: «en 1 hora» y «mañana a las 8:00 a. m.». */
    programarEn(opcion) {
        const fecha = new Date();
        if (opcion === "hora") {
            fecha.setHours(fecha.getHours() + 1);
        } else {
            fecha.setDate(fecha.getDate() + 1);
            fecha.setHours(8, 0, 0, 0);
        }
        this.borrador.programarPara = this.formatoLocal(fecha);
    }

    puedeCancelar(m) {
        return m.usuario?.id === this.almacen.usuario.id || this.almacen.usuario.es_gerencia;
    }

    cancelarProgramado(m) {
        return this.almacen.cancelarProgramado(m.id);
    }

    // --- Quién atiende ----------------------------------------------------------------------------

    /** Lo que dice la barra de arriba de la caja: quién contesta y hasta cuándo. */
    get barra() {
        const c = this.c;
        if (!c) {
            return null;
        }
        if (c.estado === "cerrada") {
            return { clase: "cerrada", texto: "Conversación cerrada. Si escribes, se reabre y la atiendes tú.", boton: "Atender" };
        }
        if (c.estado === "humano" && !c.bot_atiende) {
            const vence = c.pausada_hasta
                ? `El asistente vuelve a las ${hora(c.pausada_hasta)} (${enCuanto(c.pausada_hasta, this.almacen.ahora)})`
                : "El asistente no contesta hasta que se la devuelvas";
            const quien = c.asignada_a && c.asignada_a.id !== this.almacen.usuario.id ? `La atiende ${c.asignada_a.nombre}. ` : "Atiendes tú. ";
            return { clase: "humano", texto: `${quien}${vence}.`, boton: "Devolver al asistente", devolver: true };
        }
        return { clase: "bot", texto: "Atiende el asistente. Si escribes, la atiendes tú y él se calla.", boton: "Atender", punto: true };
    }

    async alBotonDeLaBarra() {
        const barra = this.barra;
        if (barra.devolver) {
            this.local.devolviendo = true;
            this.local.notaParaElBot = "";
            return;
        }
        await this.almacen.tomar();
    }

    async confirmarDevolver() {
        const nota = this.local.notaParaElBot.trim();
        this.local.devolviendo = false;
        await this.almacen.devolver(nota);
    }

    // --- Escribir -----------------------------------------------------------------------------------

    ajustarAlto() {
        const el = this.refTexto.el;
        if (el) {
            el.style.height = "auto";
            el.style.height = `${Math.min(el.scrollHeight + 2, ALTO_MAXIMO)}px`;
        }
    }

    alEscribir(ev) {
        this.ajustarAlto();
        if (!this.esNota && ev?.target?.value) {
            this.almacen.avisarQueEscribo(); // las demás personas ven «Ana está escribiendo…» (a una nota interna no)
        }
        this.local.opcion = 0;
        this.local.cursor = ev?.target?.selectionStart ?? this.borrador.texto.length;
    }

    // --- Menciones con «@» (solo en notas internas) -----------------------------------------------

    /** Hoy en la hora del navegador (AAAA-MM-DD): la fecha más temprana que se puede dar a una tarea. */
    get hoy() {
        return new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
    }

    get mencionActual() {
        return this.esNota ? mencionEnCurso(this.borrador.texto, this.local.cursor) : null;
    }

    get opcionesMencion() {
        const m = this.mencionActual;
        if (!m) {
            return [];
        }
        return this.almacen.equipo.filter((u) => u.id !== this.almacen.usuario.id && coincideConNombre(u.nombre, m.filtro));
    }

    /** Quiénes siguen mencionadas de verdad: si se borró el «@Nombre» del texto, ya no se le avisa. */
    get mencionadas() {
        const texto = this.borrador.texto;
        return this.almacen.equipo.filter((u) => this.borrador.menciones.includes(u.id) && texto.includes(`@${u.nombre}`));
    }

    elegirMencion(u) {
        const m = this.mencionActual;
        if (!m) {
            return;
        }
        const texto = this.borrador.texto;
        const despues = texto.slice(this.local.cursor);
        const insertado = `@${u.nombre} `;
        this.borrador.texto = `${texto.slice(0, m.desde)}${insertado}${despues.replace(/^\s/, "")}`;
        if (!this.borrador.menciones.includes(u.id)) {
            this.borrador.menciones.push(u.id);
        }
        this.local.cursor = m.desde + insertado.length;
        this.local.opcion = 0;
        const el = this.refTexto.el;
        if (el) {
            el.focus();
            // Con t-model el valor se pinta después: el cursor se pone al terminar el repintado.
            Promise.resolve().then(() => el.setSelectionRange(this.local.cursor, this.local.cursor));
        }
        this.ajustarAlto();
    }

    alMoverElCursor(ev) {
        this.local.cursor = ev.target.selectionStart ?? this.borrador.texto.length;
    }

    cambiarModo(modo) {
        this.borrador.modo = modo;
        this.local.rapidasAbiertas = false;
        this.refTexto.el?.focus();
    }

    // --- Respuestas rápidas con «/» -----------------------------------------------------------------

    get opcionesRapidas() {
        const filtro = atajoEnCurso(this.borrador.texto);
        if (this.esNota || (filtro === null && !this.local.rapidasAbiertas)) {
            return [];
        }
        const buscado = filtro === null ? "" : filtro;
        return this.almacen.rapidas.filter((r) => r.atajo.slice(1).startsWith(buscado));
    }

    get hayRapidas() {
        return !this.esNota && (atajoEnCurso(this.borrador.texto) !== null || this.local.rapidasAbiertas);
    }

    abrirRapidas() {
        this.cambiarModo("respuesta");
        if (!this.borrador.texto) {
            this.borrador.texto = "/";
        } else {
            this.local.rapidasAbiertas = !this.local.rapidasAbiertas;
        }
        this.local.opcion = 0;
        this.refTexto.el?.focus();
    }

    async elegirRapida(r) {
        try {
            const texto = await this.almacen.textoDeRapida(r.atajo);
            // Escribiendo «/hor» se reemplaza lo escrito; desde el botón se agrega debajo de lo que ya había.
            const previo = this.borrador.texto.trim();
            this.borrador.texto = previo && atajoEnCurso(previo) === null ? `${this.borrador.texto.trimEnd()}\n${texto}` : texto;
            this.local.rapidasAbiertas = false;
        } catch (error) {
            this.almacen.notification.add(mensajeDeError(error), { type: "danger" });
        }
        this.refTexto.el?.focus();
        this.ajustarAlto();
    }

    alTeclear(ev) {
        const personas = this.opcionesMencion;
        if (this.mencionActual) {
            if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
                ev.preventDefault();
                const n = Math.max(personas.length, 1);
                this.local.opcion = (this.local.opcion + (ev.key === "ArrowDown" ? 1 : n - 1)) % n;
                return;
            }
            if ((ev.key === "Enter" || ev.key === "Tab") && personas.length && !ev.shiftKey) {
                ev.preventDefault();
                this.elegirMencion(personas[Math.min(this.local.opcion, personas.length - 1)]);
                return;
            }
            if (ev.key === "Escape") {
                ev.preventDefault();
                ev.stopPropagation();
                this.local.cursor = 0;   // cierra la lista sin borrar lo escrito
                return;
            }
        }
        const opciones = this.opcionesRapidas;
        if (this.hayRapidas) {
            if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
                ev.preventDefault();
                const n = Math.max(opciones.length, 1);
                this.local.opcion = (this.local.opcion + (ev.key === "ArrowDown" ? 1 : n - 1)) % n;
                return;
            }
            if ((ev.key === "Enter" || ev.key === "Tab") && opciones.length && !ev.shiftKey) {
                ev.preventDefault();
                this.elegirRapida(opciones[Math.min(this.local.opcion, opciones.length - 1)]);
                return;
            }
            if (ev.key === "Escape") {
                ev.preventDefault();
                ev.stopPropagation();
                this.local.rapidasAbiertas = false;
                if (atajoEnCurso(this.borrador.texto) !== null) {
                    this.borrador.texto = "";
                }
                return;
            }
        }
        if (ev.key === "Enter" && !ev.isComposing) {
            const conControl = ev.ctrlKey || ev.metaKey;
            if (conControl || (!ev.shiftKey && !this.esTactil)) {
                ev.preventDefault();
                this.enviar();
            }
        }
    }

    // --- Archivos -----------------------------------------------------------------------------------

    elegirArchivos() {
        this.refArchivo.el?.click();
    }

    alElegirArchivos(ev) {
        const archivos = [...ev.target.files];
        ev.target.value = "";
        this.almacen.agregarArchivos(archivos);
    }

    alPegar(ev) {
        const archivos = [...(ev.clipboardData?.files || [])];
        if (archivos.length) {
            ev.preventDefault();
            this.almacen.agregarArchivos(archivos);
        }
    }

    // --- Enviar -------------------------------------------------------------------------------------

    async enviar() {
        if (!this.puedeEnviar) {
            return;
        }
        this.local.enviando = true;
        const texto = this.borrador.texto.trim();
        try {
            const r = this.esNota
                ? await this.almacen.agregarNota(texto, this.mencionadas.map((u) => u.id), this.mencionadas.length ? this.borrador.tareaPara : "")
                : await this.almacen.enviar(texto, this.listos.map((a) => a.id), this.programarIso);
            if (r) {
                const modo = this.borrador.modo;
                this.almacen.vaciarBorrador();
                this.borrador.modo = modo;
                this.local.avisos = [];
                this.local.programando = false;
            }
        } finally {
            this.local.enviando = false;
            this.refTexto.el?.focus();
            this.ajustarAlto();
        }
    }

    // --- Sugerir ------------------------------------------------------------------------------------

    async sugerir() {
        if (this.local.sugiriendo) {
            return;
        }
        this.local.sugiriendo = true;
        this.local.avisos = [];
        try {
            const r = await this.almacen.sugerir();
            this.cambiarModo("respuesta");
            this.borrador.texto = r.texto;
            this.local.avisos = r.avisos.length ? r.avisos : ["Es un borrador: léelo, ajústalo y envíalo tú."];
            this.ajustarAlto();
        } catch (error) {
            this.almacen.notification.add(mensajeDeError(error), { type: "danger", sticky: false });
        } finally {
            this.local.sugiriendo = false;
        }
    }

    abrirCatalogo() {
        this.almacen.abrirPanel("catalogo");
    }

    abrirCotizacion() {
        this.almacen.abrirPanel("cotizacion");
    }
}
