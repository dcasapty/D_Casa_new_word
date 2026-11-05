/**
 * Sofía, la asistente del CRM: muestra lo que propone y deja aprobarlo o descartarlo en un clic.
 * Todo se decide en el servidor (dcasa.sofia): quién ve qué, qué se puede hacer y si todavía hace falta. Aquí solo se
 * muestra, se edita el mensaje antes de enviarlo y se llama a la acción que la persona elige.
 */
import { Component, onMounted, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { mensajeDeError } from "@dcasa_conversaciones/js/utilidades";

const MODELO = "dcasa.sofia";
/** Por aquí pasa el mensaje a la pantalla de Conversaciones, UNA sola vez (ver conversaciones.js). No viaja en la acción:
 * quedaría guardado en la dirección y volvería a aparecer al recargar. */
export const CLAVE_MENSAJE_PARA_EL_CHAT = "dcasa.sofia.mensaje_para_el_chat";
const VIGENCIA_DEL_MENSAJE = 2 * 60 * 1000;

export const GRUPOS = [
    { clave: "todas", nombre: "Todo" },
    { clave: "escribir", nombre: "Escribirles" },
    { clave: "datos", nombre: "Datos de clientes" },
    { clave: "mantener", nombre: "Cotizaciones y llamadas" },
    { clave: "repartir", nombre: "Repartir", soloGerencia: true },
];

const BOTONES = {
    chat: { texto: "Abrir el chat", conMensaje: "Abrir el chat con este mensaje", clase: "btn-primary", icono: "fa-comments" },
    enviar: { texto: "Enviar ya", clase: "btn-secondary", icono: "fa-paper-plane" },
    tarea: { texto: "Crear tarea", clase: "btn-secondary", icono: "fa-calendar-check-o" },
    guardar: { texto: "Guardar en su ficha", clase: "btn-primary", icono: "fa-check" },
    asignar: { texto: "Asignar", clase: "btn-primary", icono: "fa-user-plus" },
};

const SIN_VENDEDORA = "__sin__";

export class SofiaPanel extends Component {
    static template = "dcasa_sofia.Panel";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.grupos = GRUPOS;
        this.state = useState({
            datos: null,
            cargando: true,
            revisando: false,
            error: null,
            grupo: "todas",
            para: "todas",
            textos: {},
            ocupada: null,
        });
        onMounted(() => (this.props.action?.params?.analizar ? this.analizar() : this.cargar()));
    }

    async cargar() {
        this.state.cargando = true;
        try {
            this.poner(await this.orm.call(MODELO, "panel", []));
        } catch (error) {
            this.state.error = mensajeDeError(error);
        } finally {
            this.state.cargando = false;
        }
    }

    async analizar() {
        this.state.revisando = true;
        try {
            this.poner(await this.orm.call(MODELO, "analizar", []));
        } catch (error) {
            this.notification.add(mensajeDeError(error), { type: "warning" });
            if (!this.state.datos) {
                await this.cargar();
            }
        } finally {
            this.state.revisando = false;
            this.state.cargando = false;
        }
    }

    /** Pone los datos nuevos sin perder lo que alguien estaba editando en un mensaje. */
    poner(datos) {
        const textos = {};
        for (const p of datos.propuestas) {
            textos[p.id] = p.id in this.state.textos ? this.state.textos[p.id] : p.mensaje;
        }
        this.state.textos = textos;
        this.state.datos = datos;
        this.state.error = null;
    }

    get d() {
        return this.state.datos;
    }

    get esGerencia() {
        return !!this.d?.es_gerencia;
    }

    get gruposVisibles() {
        return this.grupos.filter((g) => !g.soloGerencia || this.esGerencia);
    }

    get delaPersona() {
        const todas = this.d?.propuestas || [];
        if (!this.esGerencia || this.state.para === "todas") {
            return todas;
        }
        if (this.state.para === SIN_VENDEDORA) {
            return todas.filter((p) => !p.para_id && p.grupo !== "repartir");
        }
        return todas.filter((p) => String(p.para_id) === this.state.para);
    }

    get propuestas() {
        const grupo = this.state.grupo;
        return this.delaPersona.filter((p) => grupo === "todas" || p.grupo === grupo);
    }

    cuantas(grupo) {
        return this.delaPersona.filter((p) => grupo === "todas" || p.grupo === grupo).length;
    }

    get personas() {
        const vistas = new Map();
        let sinVendedora = 0;
        for (const p of this.d?.propuestas || []) {
            if (p.para_id) {
                vistas.set(String(p.para_id), p.para);
            } else if (p.grupo !== "repartir") {
                sinVendedora++;
            }
        }
        const lista = [...vistas].map(([id, nombre]) => ({ id, nombre })).sort((a, b) => a.nombre.localeCompare(b.nombre));
        if (sinVendedora) {
            lista.push({ id: SIN_VENDEDORA, nombre: "Sin vendedora" });
        }
        return lista;
    }

    get omitidas() {
        return Object.values(this.d?.omitidas || {}).reduce((total, n) => total + n, 0);
    }

    boton(propuesta, accion) {
        const base = BOTONES[accion] || { texto: accion, clase: "btn-secondary", icono: "fa-check" };
        let texto = base.texto;
        if (accion === "chat" && propuesta.mensaje) {
            texto = base.conMensaje;
        } else if (accion === "asignar" && propuesta.destino) {
            texto = `Asignar a ${propuesta.destino}`;
        } else if (accion === "tarea" && propuesta.tipo === "llamar") {
            texto = "Crear tarea: llamarlo";
        }
        return { ...base, texto };
    }

    /** Cuántas líneas necesita la caja del mensaje para verse completo (sin pasar de 12). */
    filas(texto) {
        const lineas = (texto || "").split("\n").reduce((total, linea) => total + Math.max(1, Math.ceil(linea.length / 90)), 0);
        return Math.min(12, Math.max(3, lineas));
    }

    editable(propuesta) {
        return !!propuesta.mensaje && propuesta.acciones.some((a) => ["chat", "enviar", "tarea"].includes(a));
    }

    elegirGrupo(clave) {
        this.state.grupo = clave;
    }

    elegirPersona(ev) {
        this.state.para = ev.target.value;
    }

    quitar(propuesta) {
        this.d.propuestas = this.d.propuestas.filter((p) => p.id !== propuesta.id);
        delete this.state.textos[propuesta.id];
    }

    async aplicar(propuesta, accion) {
        if (this.state.ocupada) {
            return;
        }
        this.state.ocupada = propuesta.id;
        try {
            const texto = propuesta.mensaje ? this.state.textos[propuesta.id] ?? "" : null;
            const respuesta = await this.orm.call(MODELO, "aplicar", [propuesta.id, accion], { texto });
            this.quitar(propuesta);
            this.notification.add(respuesta.resultado, { type: respuesta.ya_no_hace_falta ? "warning" : "success" });
            if (respuesta.texto && respuesta.conversacion_id) {
                try {
                    window.sessionStorage.setItem(CLAVE_MENSAJE_PARA_EL_CHAT, JSON.stringify({
                        conversacion_id: respuesta.conversacion_id,
                        texto: respuesta.texto,
                        vence: Date.now() + VIGENCIA_DEL_MENSAJE,
                    }));
                } catch {
                    // Sin almacenamiento del navegador el chat abre igual, sin el mensaje escrito.
                }
            }
            if (respuesta.accion) {
                await this.action.doAction(respuesta.accion);
            }
        } catch (error) {
            this.notification.add(mensajeDeError(error), { type: "danger" });
        } finally {
            this.state.ocupada = null;
        }
    }

    async descartar(propuesta) {
        if (this.state.ocupada) {
            return;
        }
        this.state.ocupada = propuesta.id;
        try {
            const respuesta = await this.orm.call(MODELO, "descartar", [propuesta.id]);
            this.quitar(propuesta);
            this.notification.add(respuesta.resultado, { type: "info" });
        } catch (error) {
            this.notification.add(mensajeDeError(error), { type: "danger" });
        } finally {
            this.state.ocupada = null;
        }
    }

    abrirOportunidad(propuesta) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "crm.lead",
            res_id: propuesta.lead_id,
            views: [[false, "form"]],
            target: "current",
        });
    }
}

registry.category("actions").add("dcasa_sofia.panel", SofiaPanel);
