/**
 * «Resumen» de Juan: los números del día (o de 7 y 30 días) con lo que Odoo ya guarda. Sin cifras inventadas: lo que
 * no se puede calcular se muestra como «—».
 */
import { Component, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { dolares, mensajeDeError, numero } from "./utilidades";

export const PERIODOS = [
    { id: "hoy", nombre: "Hoy" },
    { id: "7_dias", nombre: "7 días" },
    { id: "30_dias", nombre: "30 días" },
];

/** La barra de arriba de Resumen, Costos y Conexiones: título y a dónde ir. */
export class EncabezadoJuan extends Component {
    static template = "dcasa_conversaciones.Encabezado";
    static props = ["*"];

    setup() {
        this.action = useService("action");
        this.refNav = useRef("nav");
        // En el celular la barra se desliza de lado: la pantalla actual queda a la vista.
        onMounted(() => {
            const nav = this.refNav.el;
            const activa = nav?.querySelector(".o_activa");
            if (nav && activa) {
                nav.scrollLeft = activa.offsetLeft - (nav.clientWidth - activa.offsetWidth) / 2;
            }
        });
        this.secciones = [
            { id: "conversaciones", nombre: "Conversaciones", accion: "dcasa_conversaciones.accion_conversaciones", icono: "fa-comments-o" },
            { id: "resumen", nombre: "Resumen", accion: "dcasa_conversaciones.accion_resumen", icono: "fa-tachometer" },
            { id: "reparto", nombre: "Reparto", accion: "dcasa_conversaciones.accion_reparto", icono: "fa-balance-scale" },
            { id: "costos", nombre: "Costos de IA", accion: "dcasa_conversaciones.accion_costos", icono: "fa-usd", gerencia: true },
            { id: "conexiones", nombre: "Conexiones", accion: "dcasa_conversaciones.accion_conexiones", icono: "fa-plug", gerencia: true },
        ];
    }

    get visibles() {
        return this.secciones.filter((s) => !s.gerencia || this.props.esGerencia);
    }

    ir(seccion) {
        if (seccion.id !== this.props.actual) {
            this.action.doAction(seccion.accion);
        }
    }
}

export class ResumenJuan extends Component {
    static template = "dcasa_conversaciones.Resumen";
    static components = { EncabezadoJuan };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.periodos = PERIODOS;
        this.numero = numero;
        this.dolares = dolares;
        this.state = useState({ periodo: "hoy", datos: null, cargando: true, error: null, personas: null });
        onMounted(() => {
            this.cargar();
            this.reloj = setInterval(() => this.cargar(true), 60_000);
        });
        onWillUnmount(() => clearInterval(this.reloj));
    }

    async cargar(silencioso = false) {
        if (!silencioso) {
            this.state.cargando = true;
        }
        const periodo = this.state.periodo;
        try {
            const datos = await (silencioso ? this.orm.silent : this.orm).call("dcasa.juan.panel", "resumen", [periodo]);
            if (periodo === this.state.periodo) {
                this.state.datos = datos;
                this.state.error = null;
            }
            // Cómo le fue a cada persona: solo lo ve Gerencia. Si falla, el resto del Resumen sigue igual.
            if (datos.es_gerencia) {
                try {
                    const personas = await this.orm.silent.call("dcasa.juan.panel", "por_persona", [periodo]);
                    if (periodo === this.state.periodo) {
                        this.state.personas = personas;
                    }
                } catch {
                    this.state.personas = null;
                }
            } else {
                this.state.personas = null;
            }
        } catch (error) {
            if (!silencioso) {
                this.state.error = mensajeDeError(error);
            }
        } finally {
            this.state.cargando = false;
        }
    }

    elegir(periodo) {
        this.state.periodo = periodo;
        this.cargar();
    }

    get nombreDelPeriodo() {
        return { hoy: "de hoy", "7_dias": "de los últimos 7 días", "30_dias": "de los últimos 30 días" }[this.state.periodo];
    }

    get porcentajeSinHumano() {
        const d = this.state.datos;
        return d && d.conversaciones ? Math.round((d.resueltas_sin_humano / d.conversaciones) * 100) : null;
    }

    /** «37 min», «2 h 5 min»: minutos que lleva esperando un cliente. */
    minutosEnTexto(m) {
        if (m === null || m === undefined) {
            return "—";
        }
        return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h${m % 60 ? ` ${m % 60} min` : ""}`;
    }

    irAConversaciones() {
        this.action.doAction("dcasa_conversaciones.accion_conversaciones");
    }
}

registry.category("actions").add("dcasa_juan_resumen", ResumenJuan);
