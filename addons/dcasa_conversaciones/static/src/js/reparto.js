/**
 * «Reparto»: cómo se están repartiendo las conversaciones que Juan le pasa al equipo.
 * Cada vendedora ve SOLO lo suyo («Mis conversaciones de hoy»); Gerencia ve a todo el equipo y puede sacar a alguien del
 * reparto (vacaciones, ausencia) sin quitarle ningún permiso, o encender el reparto parejo. Todas las cuentas salen del
 * servidor (dcasa.juan.panel.reparto): aquí solo se muestran.
 */
import { Component, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { EncabezadoJuan, PERIODOS } from "./resumen";
import { hora, mensajeDeError, numero } from "./utilidades";

const MODELO = "dcasa.juan.panel";
/** La misma clave con la que Conversaciones recuerda cuál tenía abierta: así «Abrir» deja el hilo a la vista. */
const CLAVE_ABIERTA = "dcasa.conversaciones.abierta";

export const ESTADOS_DE_PERSONA = {
    disponible: { clase: "ok", icono: "fa-check-circle", texto: "Disponible" },
    no_disponible: { clase: "apagado", icono: "fa-pause-circle-o", texto: "No disponible" },
    fuera: { clase: "alerta", icono: "fa-plane", texto: "No recibe" },
    interviene: { clase: "listo", icono: "fa-hand-paper-o", texto: "Interviene, no recibe" },
};

export class RepartoJuan extends Component {
    static template = "dcasa_conversaciones.Reparto";
    static components = { EncabezadoJuan };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.periodos = PERIODOS;
        this.numero = numero;
        this.estados = ESTADOS_DE_PERSONA;
        this.state = useState({ periodo: "hoy", datos: null, cargando: true, error: null, ocupado: false });
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
            const datos = await (silencioso ? this.orm.silent : this.orm).call(MODELO, "reparto", [periodo]);
            if (periodo === this.state.periodo) {
                this.state.datos = datos;
                this.state.error = null;
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

    get d() {
        return this.state.datos;
    }

    get esGerencia() {
        return !!this.d?.es_gerencia;
    }

    get nombreDelPeriodo() {
        return { hoy: "hoy", "7_dias": "en los últimos 7 días", "30_dias": "en los últimos 30 días" }[this.state.periodo];
    }

    get titulo() {
        if (this.esGerencia) {
            return "Reparto";
        }
        return this.state.periodo === "hoy" ? "Mis conversaciones de hoy" : "Mis conversaciones";
    }

    get subtitulo() {
        return this.esGerencia
            ? "Cómo reparte Juan las conversaciones que pasa a una persona, " + this.nombreDelPeriodo + "."
            : "Las que Juan te pasó " + this.nombreDelPeriodo + " y los clientes que te esperan ahora.";
    }

    /** El día siguiente a hoy («2026-10-15»): lo más pronto que alguien puede volver al reparto. */
    get manana() {
        if (!this.d?.hoy) {
            return "";
        }
        const [a, m, dia] = this.d.hoy.split("-").map(Number);
        return new Date(Date.UTC(a, m - 1, dia + 1)).toISOString().slice(0, 10);
    }

    /** El número más alto de «recibidas», para dibujar las barras de cada persona. */
    get maximo() {
        return Math.max(1, ...(this.d?.equipo || []).map((p) => p.recibidas));
    }

    ancho(persona) {
        return Math.round((persona.recibidas / this.maximo) * 100);
    }

    /** «hace 5 min», «hace 2 h», «ayer 4:10 p. m.» o «—»: cuándo fue la última que le tocó. */
    cuando(iso) {
        if (!iso) {
            return "—";
        }
        const minutos = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
        if (minutos < 1) {
            return "ahora mismo";
        }
        if (minutos < 60) {
            return `hace ${minutos} min`;
        }
        if (minutos < 24 * 60) {
            const h = Math.floor(minutos / 60);
            return `hace ${h} h`;
        }
        const dias = Math.floor(minutos / (24 * 60));
        return `hace ${dias} ${dias === 1 ? "día" : "días"}`;
    }

    horaDe(iso) {
        return hora(iso);
    }

    minutosEnTexto(m) {
        if (m === null || m === undefined) {
            return "—";
        }
        return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h${m % 60 ? ` ${m % 60} min` : ""}`;
    }

    /** «20/10/2026» desde «2026-10-20» (sin pasar por zonas horarias: es solo un día). */
    fecha(iso) {
        const [a, m, d] = String(iso).split("-");
        return `${d}/${m}/${a}`;
    }

    get frasePareja() {
        const dif = this.d?.diferencia;
        if (dif === null || dif === undefined) {
            return "";
        }
        if (dif <= 1) {
            return "Va parejo: entre quien más y quien menos recibió hay " + (dif === 0 ? "ninguna de diferencia" : "una de diferencia") + ".";
        }
        return `Entre quien más y quien menos recibió hay ${dif} de diferencia. Si alguien estuvo "No disponible" o fuera del reparto, es normal.`;
    }

    // --- Acciones de Gerencia ------------------------------------------------------------------------------

    async _hacer(llamada, aviso) {
        if (this.state.ocupado) {
            return;
        }
        this.state.ocupado = true;
        try {
            await llamada();
            if (aviso) {
                this.notification.add(aviso, { type: "success" });
            }
            await this.cargar(true);
        } catch (error) {
            this.notification.add(mensajeDeError(error), { type: "danger" });
        } finally {
            this.state.ocupado = false;
        }
    }

    sacar(persona) {
        return this._hacer(
            () => this.orm.call(MODELO, "fijar_fuera_del_reparto", [persona.usuario_id, true, null]),
            `${persona.nombre} ya no recibe conversaciones del asistente. Conserva todos sus permisos.`
        );
    }

    volver(persona) {
        return this._hacer(
            () => this.orm.call(MODELO, "fijar_fuera_del_reparto", [persona.usuario_id, false, null]),
            `${persona.nombre} vuelve a recibir conversaciones.`
        );
    }

    /** Cambia el día en que vuelve (vacío = hasta que Gerencia la vuelva a meter). */
    cambiarRegreso(persona, ev) {
        const valor = ev.target.value || null;
        return this._hacer(
            () => this.orm.call(MODELO, "fijar_fuera_del_reparto", [persona.usuario_id, true, valor]),
            valor ? `${persona.nombre} vuelve el ${this.fecha(valor)}.` : `${persona.nombre} no recibe hasta que la vuelvas a meter.`
        );
    }

    encender() {
        return this._hacer(
            () => this.orm.call(MODELO, "fijar_modo_reparto", ["parejo"]),
            "Listo: desde ahora Juan reparte parejo."
        );
    }

    apagar() {
        return this._hacer(
            () => this.orm.call(MODELO, "fijar_modo_reparto", ["manual"]),
            "Reparto apagado: las conversaciones que Juan pase las toma quien quiera."
        );
    }

    async abrirAjustes() {
        this.action.doAction(await this.orm.call("dcasa.juan.ajustes", "action_abrir", []));
    }

    // --- Navegación ----------------------------------------------------------------------------------------

    abrirConversacion(fila) {
        try {
            window.sessionStorage.setItem(CLAVE_ABIERTA, String(fila.conversacion_id));
        } catch {
            /* sin almacenamiento: se abre Conversaciones sin la conversación a la vista */
        }
        this.action.doAction("dcasa_conversaciones.accion_conversaciones");
    }

    irAConversaciones() {
        this.action.doAction("dcasa_conversaciones.accion_conversaciones");
    }
}

registry.category("actions").add("dcasa_juan_reparto", RepartoJuan);
