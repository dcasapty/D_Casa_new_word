/**
 * «Costos de IA»: cuánto se gastó este mes, el tope, la proyección («terminarás el mes en…») y el desglose por día y por
 * modelo. El gasto lo lee Odoo del Worker (GET /odoo/salud y /odoo/costos); aquí solo se muestra.
 *
 * Pagos (pedido de la dueña, 2026-11-12): «Registrar pago» anota que Meta ya cobró. No borra nada: marca un corte, y
 * arriba sale «Consumido desde el último pago». Las cuentas las hace el servidor (panel_calculos.py, pagos_ia.py).
 */
import { Component, onMounted, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { EncabezadoJuan } from "./resumen";
import { mensajeDeError, numero, ZONA } from "./utilidades";

const FORMATO_USD = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 });
const FORMATO_USD_FINO = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 4 });
const FORMATO_DIA = new Intl.DateTimeFormat("es-PA", { day: "numeric", month: "short", timeZone: "UTC" });

/** «AAAA-MM-DDTHH:MM» de este momento en la zona del negocio (lo que pide un <input type="datetime-local">). */
export function ahoraEnLaZona(zona = ZONA, fecha = new Date()) {
    try {
        const partes = Object.fromEntries(
            new Intl.DateTimeFormat("en-CA", { timeZone: zona, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" })
                .formatToParts(fecha)
                .map((p) => [p.type, p.value])
        );
        return `${partes.year}-${partes.month}-${partes.day}T${partes.hour}:${partes.minute}`;
    } catch {
        return "";
    }
}

/** El diálogo «Registrar pago»: cuándo cobró Meta (por defecto ahora), cuánto (opcional) y una nota. */
export class DialogoPagoIa extends Component {
    static template = "dcasa_conversaciones.DialogoPagoIa";
    static components = { Dialog };
    static props = { zona: { type: String, optional: true }, ahoraLocal: { type: String, optional: true }, alGuardar: Function, close: Function };

    setup() {
        this.orm = useService("orm");
        this.maximo = ahoraEnLaZona(this.props.zona || ZONA) || this.props.ahoraLocal || "";
        // Si no la toca, se manda «ahora» (null) y el servidor le pide el corte al Worker en ese momento.
        this.state = useState({ fecha: this.maximo, tocada: false, monto: "", nota: "", error: "", guardando: false });
    }

    cambiarFecha(ev) {
        this.state.fecha = ev.target.value;
        this.state.tocada = true;
    }

    async guardar(ev) {
        ev?.preventDefault();
        if (this.state.guardando) {
            return;
        }
        const texto = String(this.state.monto ?? "").trim().replace(",", ".");
        const monto = texto ? Number(texto) : null;
        if (texto && (!Number.isFinite(monto) || monto <= 0)) {
            this.state.error = "Lo que cobró Meta tiene que ser un número mayor que 0 (o déjalo vacío).";
            return;
        }
        if (this.state.tocada && !this.state.fecha) {
            this.state.error = "Elige el día y la hora en que cobró Meta.";
            return;
        }
        this.state.guardando = true;
        this.state.error = "";
        try {
            const resultado = await this.orm.call("dcasa.juan.panel", "registrar_pago_ia", [], {
                fecha: this.state.tocada ? this.state.fecha : null,
                monto,
                nota: this.state.nota.trim() || null,
            });
            this.props.close();
            await this.props.alGuardar(resultado);
        } catch (error) {
            this.state.error = mensajeDeError(error);
            this.state.guardando = false;
        }
    }
}

/** Anular un pago mal anotado: pide el motivo (queda en la historia). */
export class DialogoAnularPago extends Component {
    static template = "dcasa_conversaciones.DialogoAnularPago";
    static components = { Dialog };
    static props = { pago: Object, alGuardar: Function, close: Function };

    setup() {
        this.orm = useService("orm");
        this.state = useState({ motivo: "", error: "", guardando: false });
    }

    async anular(ev) {
        ev?.preventDefault();
        if (this.state.guardando) {
            return;
        }
        if (!this.state.motivo.trim()) {
            this.state.error = "Escribe por qué lo anulas: queda en la historia.";
            return;
        }
        this.state.guardando = true;
        this.state.error = "";
        try {
            await this.orm.call("dcasa.juan.panel", "anular_pago_ia", [this.props.pago.id, this.state.motivo.trim()]);
            this.props.close();
            await this.props.alGuardar();
        } catch (error) {
            this.state.error = mensajeDeError(error);
            this.state.guardando = false;
        }
    }
}

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
        this.dialog = useService("dialog");
        this.notification = useService("notification");
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

    /** Los pagos anotados (vienen en todas las respuestas de costos(), también sin Worker). */
    get pagos() {
        return this.d?.pagos || null;
    }

    registrarPago() {
        this.dialog.add(DialogoPagoIa, {
            zona: this.pagos?.zona || ZONA,
            ahoraLocal: this.pagos?.ahora_local || "",
            alGuardar: async (r) => {
                this.notification.add(r.exacto ? "Pago registrado. Desde ahora se cuenta lo consumido desde este pago." : `Pago registrado. ${r.corte}`, {
                    type: r.exacto ? "success" : "warning",
                });
                await this.cargar();
            },
        });
    }

    anularPago(pago) {
        this.dialog.add(DialogoAnularPago, {
            pago,
            alGuardar: async () => {
                this.notification.add("Pago anulado: queda en la lista con su motivo y ya no cuenta.", { type: "success" });
                await this.cargar();
            },
        });
    }

    /** Cuánto cobró Meta de más o de menos que lo calculado (en palabras, sin signos). */
    textoDiferencia(pago) {
        if (pago.diferencia === null || pago.diferencia === undefined) {
            return "—";
        }
        if (Math.abs(pago.diferencia) < 0.005) {
            return "Igual";
        }
        return pago.diferencia > 0 ? `${this.usd(pago.diferencia)} de más` : `${this.usd(-pago.diferencia)} de menos`;
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
