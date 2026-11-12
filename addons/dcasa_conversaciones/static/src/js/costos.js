/**
 * «Costos de IA»: cuánto se gastó este mes, el tope, la proyección («terminarás el mes en…») y el desglose por día y por
 * modelo. El gasto lo lee Odoo del Worker (GET /odoo/salud y /odoo/costos); aquí solo se muestra.
 *
 * «Pagar» (pedido de la dueña, 2026-11-12): arriba, «Por pagar a Meta» y un botón «Pagar» con una sola confirmación;
 * el saldo vuelve a $0 y empieza a contar de nuevo. Debajo, «Último pago» con «Deshacer». Las cuentas y el libro de
 * pagos los lleva el servidor (panel_calculos.py, pagos_ia.py); aquí solo se muestra y se confirma.
 */
import { Component, onMounted, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { EncabezadoJuan } from "./resumen";
import { mensajeDeError, numero } from "./utilidades";

const FORMATO_USD = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 });
const FORMATO_USD_FINO = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 4 });
const FORMATO_DIA = new Intl.DateTimeFormat("es-PA", { day: "numeric", month: "short", timeZone: "UTC" });

// Lo que dice el servidor cuando lo visto ya no es el saldo de ahora (pantalla vieja u otro «Pagar» a la vez).
const SALDO_CAMBIO = "El saldo cambió";

/**
 * La única confirmación de «Pagar»: sin campos. Si Juan (el Worker) no responde, no se registra nada y lo dice ahí
 * mismo. Si el saldo cambió, se cierra y la pantalla trae la cifra de ahora (``alCambiar``).
 */
export class DialogoPagar extends Component {
    static template = "dcasa_conversaciones.DialogoPagar";
    static components = { Dialog };
    static props = { saldo: Number, texto: String, alPagar: Function, alCambiar: Function, close: Function };

    setup() {
        this.orm = useService("orm");
        this.state = useState({ error: "", pagando: false });
    }

    async pagar() {
        if (this.state.pagando) {
            return;
        }
        this.state.pagando = true;
        this.state.error = "";
        try {
            await this.orm.call("dcasa.juan.panel", "pagar_ia", [this.props.saldo]);
            this.props.close();
            await this.props.alPagar();
        } catch (error) {
            const mensaje = mensajeDeError(error);
            if (mensaje.startsWith(SALDO_CAMBIO)) {
                this.props.close();
                await this.props.alCambiar();
                return;
            }
            this.state.error = mensaje;
            this.state.pagando = false;
        }
    }
}

/** «Deshacer» el último pago, con una sola confirmación (por si se tocó sin querer también aquí). */
export class DialogoDeshacer extends Component {
    static template = "dcasa_conversaciones.DialogoDeshacer";
    static components = { Dialog };
    static props = { pagoId: Number, pregunta: String, alDeshacer: Function, close: Function };

    setup() {
        this.orm = useService("orm");
        this.state = useState({ error: "", deshaciendo: false });
    }

    async deshacer() {
        if (this.state.deshaciendo) {
            return;
        }
        this.state.deshaciendo = true;
        this.state.error = "";
        try {
            await this.orm.call("dcasa.juan.panel", "deshacer_pago_ia", [this.props.pagoId]);
            this.props.close();
            await this.props.alDeshacer();
        } catch (error) {
            this.state.error = mensajeDeError(error);
            this.state.deshaciendo = false;
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

    /** «Por pagar a Meta» y el último pago (vienen con costos(), cuando el Worker contestó). */
    get pagos() {
        return this.d?.pagos || null;
    }

    pagar() {
        const saldo = this.pagos?.saldo;
        if (!saldo || saldo <= 0) {
            return;
        }
        this.dialog.add(DialogoPagar, {
            saldo,
            texto: this.usd(saldo),
            alPagar: async () => {
                this.notification.add("Listo: el saldo volvió a $0 y empieza a contar de nuevo.", { type: "success" });
                await this.cargar();
            },
            alCambiar: async () => {
                this.notification.add("El saldo cambió mientras tanto: esta es la cifra de ahora. Si ya le pagaste a Meta, vuelve a tocar «Pagar».", {
                    type: "warning",
                });
                await this.cargar();
            },
        });
    }

    deshacer() {
        const p = this.pagos;
        const ultimo = p?.ultimo;
        if (!ultimo) {
            return;
        }
        const despues = p.saldo_si_se_deshace === null || p.saldo_si_se_deshace === undefined ? "" : ` El saldo vuelve a ${this.usd(p.saldo_si_se_deshace)}.`;
        this.dialog.add(DialogoDeshacer, {
            pagoId: ultimo.id,
            pregunta: `¿Deshacer el pago de ${this.usd(ultimo.monto)} del ${ultimo.dia}?${despues}`,
            alDeshacer: async () => {
                this.notification.add("Pago deshecho: el saldo volvió a como estaba.", { type: "success" });
                await this.cargar();
            },
        });
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
