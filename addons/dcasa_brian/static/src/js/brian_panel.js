/**
 * Brian en el panel: botón flotante + panel lateral de chat, en todas las pantallas.
 *
 * Consume la API de `brian.conversacion` (ver el docstring de models/conversacion.py):
 *   estado_proveedor(), mis_conversaciones(), nueva(), historial(id),
 *   enviar([[id], texto], {adjunto_ids, contexto}),
 *   confirmar_accion([[id], accion_id]) / rechazar_accion([[id], accion_id]).
 *
 * Los adjuntos se suben como ir.attachment (res_model='brian.conversacion', res_id=id)
 * y viajan por id. Todo error se muestra como notificación: si el núcleo falla, el resto
 * del backend sigue funcionando.
 */
import { Component, onMounted, useEffect, useRef, useState } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { router } from "@web/core/browser/router";
import { registry } from "@web/core/registry";
import { getDataURLFromFile } from "@web/core/utils/urls";
import { useBus, useService } from "@web/core/utils/hooks";
import { parsearMarkdown } from "./brian_markdown";

const MODELO = "brian.conversacion";
const MAX_ADJUNTO = 15 * 1024 * 1024;
const AVISO_SIN_CLAVE =
    "Brian aún no tiene su clave de IA; pídele a quien administra el sistema que la configure en Ajustes\u00a0›\u00a0Brian.";

const ESTADOS_ACCION = {
    por_confirmar: { texto: "Necesita tu confirmación", icono: "fa-hand-paper-o" },
    enviando: { texto: "Procesando…", icono: "fa-circle-o-notch fa-spin" },
    hecha: { texto: "Hecha", icono: "fa-check" },
    rechazada: { texto: "Cancelada", icono: "fa-ban" },
    error: { texto: "No se pudo hacer", icono: "fa-exclamation-triangle" },
    bloqueada: { texto: "Bloqueada por las reglas", icono: "fa-lock" },
};

/** Sugerencias rápidas según la pantalla (solo preguntas: nada de cifras inventadas). */
const SUGERENCIAS = [
    {
        si: (c) => c.vista === "dcasa_inicio",
        chips: ["¿Cómo va el día?", "¿Qué hay por cobrar?", "¿Qué pedidos web están pendientes?"],
    },
    {
        si: (c) => c.modelo === "account.move",
        chips: ["¿Qué facturas están por cobrar?", "¿Qué facturas vencen esta semana?", "Resumen de cobros de hoy"],
    },
    {
        si: (c) => c.modelo === "account.payment" || c.modelo === "account.bank.statement.line",
        chips: ["¿Qué pagos entraron hoy?", "¿Qué facturas están por cobrar?"],
    },
    {
        si: (c) => ["product.template", "product.product"].includes(c.modelo),
        chips: ["Busca productos agotados", "¿Qué productos tienen poco inventario?", "Crea un producto nuevo"],
    },
    {
        si: (c) => ["stock.quant", "stock.picking", "stock.move"].includes(c.modelo),
        chips: ["¿Qué entregas están pendientes?", "Busca productos agotados"],
    },
    {
        si: (c) => c.modelo === "sale.order",
        chips: ["¿Cómo van las ventas de hoy?", "¿Qué cotizaciones faltan por confirmar?", "Crea una cotización"],
    },
    {
        si: (c) => c.modelo === "res.partner",
        chips: ["¿Qué clientes me deben?", "Busca un cliente por su celular", "Crea un cliente nuevo"],
    },
    {
        si: (c) => c.modelo && c.modelo.startsWith("dcasa."),
        chips: ["¿Cómo va el programa Socios?", "Busca un socio por su celular"],
    },
    {
        si: (c) => c.modelo === "res.users",
        chips: ["¿Quién tiene acceso de administrador?", "¿Qué usuarios están activos?"],
    },
];
const SUGERENCIAS_BASE = ["¿Cómo va el día?", "¿Qué puedes hacer?", "Explícame esta pantalla"];

function nombreHerramienta(nombre) {
    const s = String(nombre || "").replace(/_/g, " ");
    return s.charAt(0).toUpperCase() + s.slice(1);
}

function fechaCorta(iso) {
    if (!iso) {
        return "";
    }
    const texto = String(iso).replace(" ", "T");
    const d = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(texto) ? texto : texto + "Z");
    if (isNaN(d)) {
        return "";
    }
    const hoy = new Date();
    if (d.toDateString() === hoy.toDateString()) {
        return d.toLocaleTimeString("es-PA", { hour: "numeric", minute: "2-digit" });
    }
    return d.toLocaleDateString("es-PA", { day: "2-digit", month: "2-digit", year: "numeric" });
}

function mensajeDeError(error) {
    const data = error?.data;
    if (data?.name && /UserError|AccessError|ValidationError/.test(data.name) && data.message) {
        return data.message;
    }
    return "Brian no está disponible en este momento. Intenta de nuevo en un rato.";
}

export class BrianPanel extends Component {
    static template = "dcasa_brian.Brian";
    static props = {};

    setup() {
        this.brian = useService("dcasa_brian");
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.ui = useService("ui");
        this.panelRef = useRef("panel");
        this.entradaRef = useRef("entrada");
        this.mensajesRef = useRef("mensajes");
        this.archivoRef = useRef("archivo");
        this.lanzadorRef = useRef("lanzador");
        this.state = useState({
            cargado: false,
            proveedor: null,
            vista: "chat",
            conversaciones: [],
            cargandoLista: false,
            conversacionId: null,
            titulo: "",
            mensajes: [],
            pensando: false,
            texto: "",
            adjuntos: [],
            arrastrando: false,
            version: 0,
        });
        this.abierto = useState(this.brian.estado);
        this.contadorLocal = 0;
        useBus(this.env.bus, "ACTION_MANAGER:UI-UPDATED", () => this.state.version++);

        // Foco: al abrir, a la caja de texto; al cerrar, de vuelta a donde estaba.
        let primeraVez = true;
        useEffect(
            (abierto) => {
                if (abierto) {
                    if (!this.state.cargado) {
                        this.cargarInicio();
                    }
                    browser.setTimeout(() => this.entradaRef.el?.focus(), 30);
                } else if (!primeraVez) {
                    const previo = this.brian.focoPrevio;
                    const visible = (el) => el && document.body.contains(el) && el.offsetParent !== null;
                    const destino = [previo, this.lanzadorRef.el, document.querySelector(".o_brian_systray_btn")].find(
                        (el) => el !== document.body && visible(el)
                    );
                    destino?.focus?.();
                }
                primeraVez = false;
            },
            () => [this.abierto.abierto]
        );
        useEffect(
            () => {
                const el = this.mensajesRef.el;
                if (el) {
                    el.scrollTop = el.scrollHeight;
                }
            },
            () => [this.state.mensajes.length, this.state.pensando, this.state.vista]
        );
        onMounted(() => this.ajustarAltura());
    }

    // --- Pantalla actual ------------------------------------------------------------

    get contexto() {
        this.state.version;
        const c = this.action.currentController;
        if (!c) {
            return {};
        }
        const accion = c.action || {};
        const props = c.props || {};
        const ruta = router.current || {};
        const modelo = props.resModel || accion.res_model || undefined;
        let resId = typeof props.resId === "number" ? props.resId : undefined;
        if (modelo && ruta.model === modelo && typeof ruta.resId === "number") {
            resId = ruta.resId;
        }
        const vista = c.view?.type || props.type || (accion.type === "ir.actions.client" ? accion.tag : undefined);
        return {
            modelo,
            res_id: vista === "form" ? resId : undefined,
            vista,
            accion: accion.display_name || accion.name || accion.tag || undefined,
            accion_id: typeof accion.id === "number" ? accion.id : undefined,
            nombre: c.displayName || undefined,
        };
    }

    get sugerencias() {
        const c = this.contexto;
        const regla = SUGERENCIAS.find((r) => r.si(c));
        const chips = regla ? [...regla.chips] : [...SUGERENCIAS_BASE];
        if (c.res_id && !chips.includes("Resume este registro")) {
            chips.unshift("Resume este registro");
        }
        return chips.slice(0, 4);
    }

    get lugar() {
        const c = this.contexto;
        return c.nombre || c.accion || "";
    }

    get sinClave() {
        return this.state.proveedor && this.state.proveedor.configurado === false;
    }

    get avisoSinClave() {
        return AVISO_SIN_CLAVE;
    }

    get estadoTexto() {
        const p = this.state.proveedor;
        if (!p) {
            return "Asistente de D'CASA";
        }
        if (!p.configurado) {
            return "Sin clave de IA";
        }
        return p.modelo ? `Listo · ${p.modelo}` : "Listo para ayudarte";
    }

    // --- Datos ------------------------------------------------------------------------

    async llamar(metodo, args = [], kwargs = {}) {
        try {
            return await this.orm.silent.call(MODELO, metodo, args, kwargs);
        } catch (error) {
            this.notification.add(mensajeDeError(error), { type: "danger", title: "Brian" });
            throw error;
        }
    }

    async cargarInicio() {
        this.state.cargado = true;
        try {
            this.state.proveedor = await this.llamar("estado_proveedor");
        } catch {
            this.state.cargado = false;
        }
    }

    async asegurarConversacion() {
        if (!this.state.conversacionId) {
            const conv = await this.llamar("nueva", [], { canal: "chat" });
            this.state.conversacionId = conv.id;
            this.state.titulo = conv.titulo || "";
        }
        return this.state.conversacionId;
    }

    async verHistorial() {
        this.state.vista = "historial";
        this.state.cargandoLista = true;
        try {
            this.state.conversaciones = (await this.llamar("mis_conversaciones", [], { limite: 30 })) || [];
        } catch {
            this.state.conversaciones = [];
        } finally {
            this.state.cargandoLista = false;
        }
    }

    async abrirConversacion(conv) {
        try {
            const r = await this.llamar("historial", [conv.id]);
            this.state.conversacionId = conv.id;
            this.state.titulo = r?.conversacion?.titulo || conv.titulo || "";
            this.state.mensajes = r?.mensajes || [];
            if (r?.estado) {
                this.state.proveedor = r.estado;
            }
            this.state.adjuntos = [];
            this.state.vista = "chat";
            this.enfocar();
        } catch {
            // Ya se notificó.
        }
    }

    nuevaConversacion() {
        this.state.conversacionId = null;
        this.state.titulo = "";
        this.state.mensajes = [];
        this.state.adjuntos = [];
        this.state.texto = "";
        this.state.vista = "chat";
        this.ajustarAltura();
        this.enfocar();
    }

    volverAlChat() {
        this.state.vista = "chat";
        this.enfocar();
    }

    /** Agrega los mensajes nuevos y reemplaza por id los que cambiaron (p. ej. una tarjeta). */
    aplicarRespuesta(r) {
        for (const m of r?.mensajes || []) {
            const i = this.state.mensajes.findIndex((x) => x.id === m.id);
            if (i >= 0) {
                this.state.mensajes.splice(i, 1, m);
            } else {
                this.state.mensajes.push(m);
            }
        }
        if (r?.conversacion?.titulo) {
            this.state.titulo = r.conversacion.titulo;
        }
        if (r && r.ok === false && r.error) {
            this.state.mensajes.push({ id: `local-${++this.contadorLocal}`, rol: "assistant", error: true, texto: r.error });
        }
    }

    // --- Enviar ----------------------------------------------------------------------

    async enviar(textoForzado) {
        const texto = (typeof textoForzado === "string" ? textoForzado : this.state.texto).trim();
        const adjuntos = this.state.adjuntos.filter((a) => a.id);
        if (this.state.pensando || this.state.adjuntos.some((a) => a.subiendo) || (!texto && !adjuntos.length)) {
            return;
        }
        const local = {
            id: `local-${++this.contadorLocal}`,
            rol: "user",
            texto,
            adjuntos: adjuntos.map((a) => ({ id: a.id, nombre: a.nombre, mimetype: a.mimetype })),
            local: true,
        };
        this.state.mensajes.push(local);
        this.state.texto = "";
        this.state.adjuntos = [];
        this.state.pensando = true;
        this.ajustarAltura();
        try {
            const id = await this.asegurarConversacion();
            const r = await this.llamar("enviar", [[id], texto], {
                adjunto_ids: adjuntos.map((a) => a.id),
                contexto: this.contexto,
            });
            this.quitarLocal(local.id, (r?.mensajes || []).some((m) => m.rol === "user"));
            this.aplicarRespuesta(r);
        } catch {
            // Se devuelve lo escrito para no perderlo.
            this.quitarLocal(local.id, true);
            this.state.texto = texto;
            this.state.adjuntos = adjuntos;
        } finally {
            this.state.pensando = false;
            this.ajustarAltura();
            this.enfocar();
        }
    }

    quitarLocal(id, quitar) {
        if (quitar) {
            const i = this.state.mensajes.findIndex((m) => m.id === id);
            if (i >= 0) {
                this.state.mensajes.splice(i, 1);
            }
        }
    }

    usarSugerencia(texto) {
        this.enviar(texto);
    }

    alTeclear(ev) {
        if (ev.key === "Enter" && !ev.shiftKey && !ev.isComposing) {
            ev.preventDefault();
            this.enviar();
        }
    }

    alEscribir() {
        this.ajustarAltura();
    }

    alTeclaPanel(ev) {
        if (ev.key === "Escape") {
            ev.stopPropagation();
            ev.preventDefault();
            if (this.state.vista === "historial") {
                this.volverAlChat();
            } else {
                this.brian.cerrar();
            }
        }
    }

    ajustarAltura() {
        const el = this.entradaRef.el;
        if (el) {
            el.style.height = "auto";
            el.style.height = Math.min(el.scrollHeight, 160) + "px";
        }
    }

    enfocar() {
        browser.setTimeout(() => this.entradaRef.el?.focus(), 0);
    }

    // --- Adjuntos ----------------------------------------------------------------------

    elegirArchivo() {
        this.archivoRef.el?.click();
    }

    async alElegirArchivo(ev) {
        await this.adjuntar([...(ev.target.files || [])]);
        ev.target.value = "";
    }

    alArrastrar(ev) {
        if ([...(ev.dataTransfer?.types || [])].includes("Files")) {
            ev.preventDefault();
            this.state.arrastrando = true;
        }
    }

    alSalirArrastre(ev) {
        if (!this.panelRef.el?.contains(ev.relatedTarget)) {
            this.state.arrastrando = false;
        }
    }

    async alSoltar(ev) {
        ev.preventDefault();
        this.state.arrastrando = false;
        await this.adjuntar([...(ev.dataTransfer?.files || [])]);
    }

    async alPegar(ev) {
        const archivos = [...(ev.clipboardData?.files || [])];
        if (archivos.length) {
            ev.preventDefault();
            await this.adjuntar(archivos);
        }
    }

    async adjuntar(archivos) {
        if (!archivos.length) {
            return;
        }
        let id;
        try {
            id = await this.asegurarConversacion();
        } catch {
            return;
        }
        await Promise.all(archivos.map((archivo) => this.subir(archivo, id)));
        this.enfocar();
    }

    async subir(archivo, conversacionId) {
        if (archivo.size > MAX_ADJUNTO) {
            this.notification.add(`«${archivo.name}» pesa más de 15 MB. Prueba con un archivo más liviano.`, {
                type: "warning",
                title: "Brian",
            });
            return;
        }
        const adjunto = {
            clave: `a-${++this.contadorLocal}`,
            nombre: archivo.name || "archivo",
            mimetype: archivo.type,
            subiendo: true,
            vista: archivo.type?.startsWith("image/") ? URL.createObjectURL(archivo) : null,
        };
        this.state.adjuntos.push(adjunto);
        const enLista = () => this.state.adjuntos.find((a) => a.clave === adjunto.clave);
        try {
            const dataUrl = await getDataURLFromFile(archivo);
            const [id] = await this.orm.silent.create("ir.attachment", [
                {
                    name: adjunto.nombre,
                    datas: dataUrl.split(",")[1] || "",
                    mimetype: archivo.type || undefined,
                    res_model: MODELO,
                    res_id: conversacionId,
                },
            ]);
            const a = enLista();
            if (a) {
                a.id = id;
                a.subiendo = false;
            }
        } catch (error) {
            this.quitarAdjunto(adjunto);
            this.notification.add(
                error?.data?.message || `No se pudo adjuntar «${adjunto.nombre}». Intenta de nuevo.`,
                { type: "danger", title: "Brian" }
            );
        }
    }

    quitarAdjunto(adjunto) {
        const i = this.state.adjuntos.findIndex((a) => a.clave === adjunto.clave);
        if (i >= 0) {
            const [a] = this.state.adjuntos.splice(i, 1);
            if (a.vista) {
                URL.revokeObjectURL(a.vista);
            }
        }
    }

    // --- Mensajes ----------------------------------------------------------------------

    markdown(texto) {
        return parsearMarkdown(texto);
    }

    fecha(iso) {
        return fechaCorta(iso);
    }

    nombreHerramienta(nombre) {
        return nombreHerramienta(nombre);
    }

    estadoAccion(confirmacion) {
        return ESTADOS_ACCION[confirmacion?.estado] || ESTADOS_ACCION.por_confirmar;
    }

    /**
     * Botones «abrir» de un mensaje: `mensaje.abrir` (objeto o lista) o `herramientas[].abrir`,
     * con la forma {modelo, res_id | dominio, titulo} o {url, titulo}.
     */
    enlacesAbrir(mensaje) {
        const lista = [];
        const sumar = (a) => lista.push(...(Array.isArray(a) ? a : [a]));
        if (mensaje.abrir) {
            sumar(mensaje.abrir);
        }
        for (const h of mensaje.herramientas || []) {
            if (h.abrir) {
                sumar(h.abrir);
            }
        }
        return lista.filter((a) => a && (a.modelo || /^(https:\/\/|\/(?!\/))/.test(a.url || "")));
    }

    abrirRegistro(destino) {
        if (!destino.modelo) {
            browser.open(destino.url, "_blank", "noopener");
            return;
        }
        const accion = {
            type: "ir.actions.act_window",
            res_model: destino.modelo,
            name: destino.titulo || undefined,
            target: "current",
        };
        if (destino.res_id) {
            accion.res_id = destino.res_id;
            accion.views = [[false, "form"]];
        } else {
            accion.domain = destino.dominio || [];
            accion.views = [
                [false, "list"],
                [false, "form"],
            ];
        }
        this.action.doAction(accion).catch(() => {
            this.notification.add("No pude abrir esa pantalla.", { type: "warning", title: "Brian" });
        });
        if (this.ui.isSmall) {
            this.brian.cerrar();
        }
    }

    async resolverAccion(mensaje, metodo) {
        const conf = mensaje.confirmacion;
        if (!conf || conf.estado !== "por_confirmar" || !this.state.conversacionId) {
            return;
        }
        conf.estado = "enviando";
        this.state.pensando = metodo === "confirmar_accion";
        try {
            const r = await this.llamar(metodo, [[this.state.conversacionId], conf.accion_id]);
            // Por si el servidor no devuelve la tarjeta; si la devuelve, manda su estado.
            conf.estado = metodo === "confirmar_accion" ? (r?.ok === false ? "error" : "hecha") : "rechazada";
            this.aplicarRespuesta(r);
        } catch {
            conf.estado = "por_confirmar";
        } finally {
            this.state.pensando = false;
        }
    }

    confirmar(mensaje) {
        return this.resolverAccion(mensaje, "confirmar_accion");
    }

    rechazar(mensaje) {
        return this.resolverAccion(mensaje, "rechazar_accion");
    }
}

/** Botón de Brian en la barra superior (útil en el celular). */
export class BrianSystray extends Component {
    static template = "dcasa_brian.Systray";
    static props = {};

    setup() {
        this.brian = useService("dcasa_brian");
        this.abierto = useState(this.brian.estado);
    }
}

registry.category("main_components").add("dcasa_brian.Panel", { Component: BrianPanel });
registry.category("systray").add("dcasa_brian.Systray", { Component: BrianSystray }, { sequence: 5 });
