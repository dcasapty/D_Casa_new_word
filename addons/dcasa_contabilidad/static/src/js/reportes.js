/**
 * «Reportes contables»: estado de resultados, balance general, balance de comprobación,
 * libro mayor, ITBMS y analítica en una sola pantalla, con atajos de periodo, detalle
 * hasta el asiento y exportación a Excel y PDF. Los datos vienen de dcasa.reporte.contable.
 */
import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { dinero, fecha } from "./formato";

const REPORTES = [
    { clave: "resumen", nombre: "Resumen", icono: "fa-tachometer" },
    { clave: "estado_resultados", nombre: "Estado de resultados", icono: "fa-line-chart" },
    { clave: "balance_general", nombre: "Balance general", icono: "fa-balance-scale" },
    { clave: "flujo_efectivo", nombre: "Flujo de efectivo", icono: "fa-exchange" },
    { clave: "por_cobrar", nombre: "Por cobrar", icono: "fa-hourglass-half" },
    { clave: "por_pagar", nombre: "Por pagar", icono: "fa-truck" },
    { clave: "balance_comprobacion", nombre: "Balance de comprobación", icono: "fa-check-square-o" },
    { clave: "libro_mayor", nombre: "Libro mayor", icono: "fa-book" },
    { clave: "itbms", nombre: "ITBMS", icono: "fa-percent" },
    { clave: "analitica", nombre: "Analítica", icono: "fa-pie-chart" },
];
const SOLO_CORTE = ["balance_general", "por_cobrar", "por_pagar"];
const COMPARABLES = ["estado_resultados", "balance_general", "flujo_efectivo"];

export class DcasaReportesContables extends Component {
    static template = "dcasa_contabilidad.Reportes";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.reportes = REPORTES;
        const params = this.props.action?.params || {};
        this.state = useState({
            reporte: params.reporte || "resumen",
            periodo: "mes",
            desde: null,
            hasta: null,
            borradores: false,
            comparar: "",
            datos: null,
            cargando: true,
            abiertas: {},
            busqueda: "",
        });
        this.dinero = (v) => dinero(v, this.state.datos?.moneda);
        this.fecha = fecha;
        onWillStart(async () => {
            this.periodos = await this.orm.call("dcasa.reporte.contable", "periodos", []);
            this.usarPeriodo(this.periodos[0], false);
            await this.cargar();
        });
    }

    get titulo() {
        return REPORTES.find((r) => r.clave === this.state.reporte).nombre;
    }

    /** Reportes «a una fecha» (saldo al corte) en vez de «de un periodo». */
    get alCorte() {
        return SOLO_CORTE.includes(this.state.reporte);
    }

    get comparable() {
        return COMPARABLES.includes(this.state.reporte);
    }

    get comparando() {
        return Boolean(this.comparable && this.state.datos?.comparado);
    }

    pct(valor) {
        if (valor === null || valor === undefined) {
            return "—";
        }
        return `${valor > 0 ? "+" : ""}${valor.toLocaleString("en-US")} %`;
    }

    /** Totales finales del comparativo: [nombre, actual, anterior]. */
    get totalesComparativo() {
        const d = this.state.datos;
        const claves = {
            estado_resultados: [
                ["Utilidad bruta", "utilidad_bruta"],
                ["Utilidad operativa", "utilidad_operativa"],
                ["Utilidad neta", "utilidad_neta"],
            ],
            balance_general: [
                ["Total activo", "activo"],
                ["Total pasivo y patrimonio", "pasivo_y_patrimonio"],
            ],
            flujo_efectivo: [
                ["Efectivo al inicio", "efectivo_inicial"],
                ["Variación del efectivo", "variacion"],
                ["Efectivo al final", "efectivo_final"],
            ],
        }[d.reporte];
        const actual = d.resumen || d.totales;
        const anterior = d.comparado.resumen || d.comparado.totales || {};
        return claves.map(([nombre, clave]) => {
            const a = actual[clave] || 0;
            const b = anterior[clave] || 0;
            return { nombre, actual: a, anterior: b, variacion: a - b, pct: b ? Math.round(((a - b) / Math.abs(b)) * 1000) / 10 : null };
        });
    }

    cambiarComparar(ev) {
        this.state.comparar = ev.target.value;
        this.cargar();
    }

    /** Del resumen al detalle: cada tarjeta lleva a su reporte o pantalla. */
    irA(destino) {
        if (destino === "bancos" || destino === "conciliacion") {
            this.action.doAction("dcasa_contabilidad.accion_conciliacion");
        } else if (destino === "borradores") {
            this.action.doAction({
                type: "ir.actions.act_window",
                name: "Borradores",
                res_model: "account.move",
                domain: [["state", "=", "draft"]],
                views: [
                    [false, "list"],
                    [false, "form"],
                ],
            });
        } else {
            const reporte = { ventas: "estado_resultados", utilidad: "estado_resultados" }[destino] || destino;
            this.cambiarReporte(reporte);
        }
    }

    abrirBanco(banco) {
        this.action.doAction({
            type: "ir.actions.client",
            tag: "dcasa_conciliacion",
            params: { journal_id: banco.id },
        });
    }

    abrirDocumentos(fila) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: fila.nombre,
            res_model: "account.move.line",
            domain: [["id", "in", fila.documentos.map((d) => d.id)]],
            views: [
                [false, "list"],
                [false, "form"],
            ],
        });
    }

    get cuentasMayor() {
        const cuentas = this.state.datos?.cuentas || [];
        const q = this.state.busqueda.trim().toLowerCase();
        return q ? cuentas.filter((c) => `${c.codigo} ${c.nombre}`.toLowerCase().includes(q)) : cuentas;
    }

    usarPeriodo(periodo, recargar = true) {
        this.state.periodo = periodo.clave;
        this.state.desde = periodo.desde;
        this.state.hasta = periodo.hasta;
        if (recargar) {
            this.cargar();
        }
    }

    cambiarFecha(campo, ev) {
        this.state[campo] = ev.target.value || null;
        this.state.periodo = null;
        this.cargar();
    }

    cambiarReporte(clave) {
        if (clave !== this.state.reporte) {
            this.state.reporte = clave;
            this.state.abiertas = {};
            this.state.busqueda = "";
            this.cargar();
        }
    }

    alternarBorradores() {
        this.state.borradores = !this.state.borradores;
        this.cargar();
    }

    async cargar() {
        this.state.cargando = true;
        this.state.datos = await this.orm.call("dcasa.reporte.contable", "obtener", [this.state.reporte], {
            desde: this.state.desde,
            hasta: this.state.hasta,
            borradores: this.state.borradores,
            comparar: this.comparable ? this.state.comparar || null : null,
        });
        this.state.cargando = false;
    }

    alternarCuenta(id) {
        this.state.abiertas[id] = !this.state.abiertas[id];
    }

    abrirApuntes(fila, extra = []) {
        if (!fila.id) {
            return;
        }
        const dominio = [
            ["account_id", "=", fila.id],
            ["parent_state", "in", this.state.borradores ? ["posted", "draft"] : ["posted"]],
            ["date", "<=", this.state.datos.hasta],
            ...extra,
        ];
        if (!this.alCorte) {
            dominio.push(["date", ">=", this.state.datos.desde]);
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            name: `${fila.codigo} ${fila.nombre}`,
            res_model: "account.move.line",
            domain: dominio,
            views: [
                [false, "list"],
                [false, "form"],
            ],
        });
    }

    abrirAsiento(linea) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "account.move",
            res_id: linea.asiento_id,
            views: [[false, "form"]],
        });
    }

    abrirImpuesto(fila) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: fila.nombre,
            res_model: "account.move.line",
            domain: [
                "|",
                ["tax_line_id", "=", fila.id],
                ["tax_ids", "in", [fila.id]],
                ["parent_state", "=", "posted"],
                ["date", ">=", this.state.datos.desde],
                ["date", "<=", this.state.datos.hasta],
            ],
            views: [
                [false, "list"],
                [false, "form"],
            ],
        });
    }

    abrirAnalitica(fila) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: fila.nombre,
            res_model: "account.analytic.line",
            domain: [
                [fila.columna, "=", fila.id],
                ["date", ">=", this.state.datos.desde],
                ["date", "<=", this.state.datos.hasta],
            ],
            views: [
                [false, "list"],
                [false, "form"],
            ],
        });
    }

    excel() {
        const q = new URLSearchParams({
            reporte: this.state.reporte,
            desde: this.state.desde || "",
            hasta: this.state.hasta || "",
            borradores: this.state.borradores ? "1" : "0",
            comparar: this.comparable ? this.state.comparar : "",
        });
        window.location = `/dcasa/contabilidad/excel?${q}`;
    }

    pdf() {
        this.action.doAction({
            type: "ir.actions.report",
            report_type: "qweb-pdf",
            report_name: "dcasa_contabilidad.reporte_contable",
            report_file: "dcasa_contabilidad.reporte_contable",
            data: {
                reporte: this.state.reporte,
                desde: this.state.desde,
                hasta: this.state.hasta,
                borradores: this.state.borradores,
                comparar: this.comparable ? this.state.comparar || null : null,
            },
        });
    }

    claseMonto(valor) {
        return valor < 0 ? "o_dc_negativo" : "";
    }
}

registry.category("actions").add("dcasa_reportes_contables", DcasaReportesContables);
