/**
 * «Costos de IA»: cuánto se gastó este mes, el tope, la proyección («terminarás el mes en…») y el desglose por día y por
 * modelo. El gasto lo lee Odoo del Worker (GET /odoo/salud y /odoo/costos); aquí solo se muestra.
 */
import { Component, onMounted, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { EncabezadoJuan } from "./resumen";
import { mensajeDeError, numero } from "./utilidades";

const FORMATO_USD = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 });
const FORMATO_USD_FINO = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 4 });
const FORMATO_DIA = new Intl.DateTimeFormat("es-PA", { day: "numeric", month: "short", timeZone: "UTC" });

const ESTADOS_DEL_TOPE = {
    bien: { clase: "bien", icono: "fa-check-circle", texto: "Vas bien" },
    en_riesgo: { clase: "riesgo", icono: "fa-exclamation-triangle", texto: "Vas a pasar el tope" },
    alcanzado: { clase: "alcanzado", icono: "fa-exclamation-circle", texto: "Tope alcanzado" },
    sin_tope: { clase: "sin_tope", icono: "fa-info-circle", texto: "Sin tope" },
};

export class CostosJuan extends Component {
    static template = "dcasa_conversaciones.Costos";
    static components = { EncabezadoJuan };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.usd = (v) => (v === null || v === undefined ? "—" : FORMATO_USD.format(v));
        this.usdFino = (v) => FORMATO_USD_FINO.format(v);
        this.numero = numero;
        this.state = useState({ datos: null, cargando: true, error: null, tabla: false, marcado: null });
        onMounted(() => this.cargar());
    }

    async cargar() {
        this.state.cargando = true;
        try {
            this.state.datos = await this.orm.call("dcasa.juan.panel", "costos", []);
            this.state.error = null;
        } catch (error) {
            this.state.error = mensajeDeError(error);
        } finally {
            this.state.cargando = false;
        }
    }

    get d() {
        return this.state.datos;
    }

    get estado() {
        return ESTADOS_DEL_TOPE[this.d?.estado_del_tope] || ESTADOS_DEL_TOPE.sin_tope;
    }

    /** Porcentaje del tope usado, para la barra (tope de 100). */
    get llenado() {
        const p = this.d?.porcentaje_del_tope;
        return p === null || p === undefined ? 0 : Math.min(100, Math.max(0, p));
    }

    get frase() {
        const d = this.d;
        if (!d) {
            return "";
        }
        if (d.proyeccion_usd === null) {
            return "Todavía es pronto para proyectar el mes: hace falta al menos un día de datos.";
        }
        const base = `Si sigues a este ritmo, terminarás el mes en ${this.usd(d.proyeccion_usd)}`;
        if (!d.tope_usd) {
            return `${base}.`;
        }
        if (d.estado_del_tope === "alcanzado") {
            return `${base}. Ya llegaste al tope de ${this.usd(d.tope_usd)}: el asistente sigue contestando, pero con el modelo económico.`;
        }
        return d.proyeccion_usd > d.tope_usd
            ? `${base}, ${this.usd(d.proyeccion_usd - d.tope_usd)} por encima del tope de ${this.usd(d.tope_usd)}. Al llegar al tope baja al modelo económico; nunca se queda sin contestar.`
            : `${base}, dentro del tope de ${this.usd(d.tope_usd)}.`;
    }

    // --- Columnas por día (una sola serie, azul de la marca) -------------------------------------------

    get dias() {
        const d = this.d;
        if (!d) {
            return [];
        }
        const conocidos = new Map(d.por_dia.map((x) => [x.fecha, x.usd]));
        const [anio, mes] = d.mes.split("-").map(Number);
        const hasta = d.dia_del_mes;
        const lista = [];
        for (let dia = 1; dia <= hasta; dia++) {
            const fecha = `${anio}-${String(mes).padStart(2, "0")}-${String(dia).padStart(2, "0")}`;
            lista.push({ fecha, dia, usd: conocidos.has(fecha) ? conocidos.get(fecha) : null, texto: FORMATO_DIA.format(new Date(Date.UTC(anio, mes - 1, dia))) });
        }
        return lista;
    }

    get maximoDia() {
        const valores = this.dias.map((x) => x.usd || 0);
        return Math.max(0.01, ...valores);
    }

    get hayDatosPorDia() {
        return this.dias.some((x) => x.usd !== null);
    }

    alturaDe(dia) {
        return dia.usd === null ? 0 : Math.max(dia.usd > 0 ? 2 : 0, Math.round((dia.usd / this.maximoDia) * 100));
    }

    get diaMasCaro() {
        const con = this.dias.filter((x) => x.usd !== null && x.usd > 0);
        return con.length ? con.reduce((a, b) => (b.usd > a.usd ? b : a)) : null;
    }

    // --- Por modelo ----------------------------------------------------------------------------------

    get maximoModelo() {
        return Math.max(0.0001, ...(this.d?.por_modelo || []).map((m) => m.usd));
    }

    anchoDe(modelo) {
        return Math.max(modelo.usd > 0 ? 1.5 : 0, (modelo.usd / this.maximoModelo) * 100);
    }

    marcar(clave) {
        this.state.marcado = clave;
    }

    irAConexiones() {
        this.action.doAction("dcasa_conversaciones.accion_conexiones");
    }
}

registry.category("actions").add("dcasa_juan_costos", CostosJuan);
