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
    { clave: "estado_resultados", nombre: "Estado de resultados", icono: "fa-line-chart" },
    { clave: "balance_general", nombre: "Balance general", icono: "fa-balance-scale" },
    { clave: "balance_comprobacion", nombre: "Balance de comprobación", icono: "fa-check-square-o" },
    { clave: "libro_mayor", nombre: "Libro mayor", icono: "fa-book" },
    { clave: "itbms", nombre: "ITBMS", icono: "fa-percent" },
    { clave: "analitica", nombre: "Analítica", icono: "fa-pie-chart" },
];

export class DcasaReportesContables extends Component {
    static template = "dcasa_contabilidad.Reportes";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.reportes = REPORTES;
        const params = this.props.action?.params || {};
        this.state = useState({
            reporte: params.reporte || "estado_resultados",
            periodo: "mes",
            desde: null,
            hasta: null,
            borradores: false,
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
        if (this.state.reporte !== "balance_general") {
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
            },
        });
    }

    claseMonto(valor) {
        return valor < 0 ? "o_dc_negativo" : "";
    }
}

registry.category("actions").add("dcasa_reportes_contables", DcasaReportesContables);
