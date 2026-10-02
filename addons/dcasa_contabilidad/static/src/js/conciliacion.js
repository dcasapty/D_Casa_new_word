/**
 * «Conciliación bancaria»: a la izquierda lo que llegó del banco sin explicar; a la
 * derecha las facturas y pagos que lo explican (sugeridos primero) o una cuenta para
 * comisiones y cargos. Un clic concilia; todo se puede deshacer.
 */
import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { dinero, fecha } from "./formato";

export class DcasaConciliacion extends Component {
    static template = "dcasa_contabilidad.Conciliacion";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        const params = this.props.action?.params || {};
        this.state = useState({
            diarios: [],
            diario: params.journal_id || null,
            lineas: [],
            linea: null,
            candidatos: [],
            reglas: [],
            elegidos: {},
            busqueda: "",
            cuentas: [],
            cuenta: "",
            etiqueta: "",
            modo: "facturas",
            cargando: true,
            trabajando: false,
        });
        this.dinero = dinero;
        this.fecha = fecha;
        onWillStart(async () => {
            this.state.cuentas = await this.orm.call("dcasa.conciliacion", "cuentas_rapidas", []);
            await this.cargarDiarios();
            if (params.aviso) {
                this.notification.add(params.aviso, { type: params.aviso_tipo || "success", sticky: params.aviso_tipo === "warning" });
            }
        });
    }

    async cargarDiarios() {
        this.state.diarios = await this.orm.call("dcasa.conciliacion", "diarios", []);
        if (!this.state.diario && this.state.diarios.length) {
            const conPendientes = this.state.diarios.find((d) => d.pendientes);
            this.state.diario = (conPendientes || this.state.diarios[0]).id;
        }
        await this.cargarLineas();
    }

    async cargarLineas() {
        this.state.cargando = true;
        this.state.lineas = this.state.diario
            ? await this.orm.call("dcasa.conciliacion", "pendientes", [this.state.diario])
            : [];
        this.state.cargando = false;
        const siguiente = this.state.lineas.find((l) => l.id === this.state.linea?.id) || this.state.lineas[0];
        await this.elegirLinea(siguiente || null);
    }

    async elegirDiario(id) {
        this.state.diario = id;
        this.state.linea = null;
        await this.cargarLineas();
    }

    async elegirLinea(linea) {
        this.state.linea = linea;
        this.state.elegidos = {};
        this.state.busqueda = "";
        this.state.cuenta = "";
        this.state.etiqueta = linea ? linea.concepto : "";
        this.state.modo = "facturas";
        this.state.reglas = linea ? await this.orm.call("dcasa.conciliacion", "reglas", [linea.id]) : [];
        await this.cargarCandidatos();
    }

    async aplicarRegla(regla) {
        this.state.trabajando = true;
        try {
            const r = await this.orm.call("dcasa.conciliacion", "aplicar_regla", [this.state.linea.id, regla.id]);
            this.notification.add(
                regla.tercero
                    ? `Tercero asignado: ${regla.tercero}.`
                    : r.conciliado
                      ? `Conciliado con la regla «${regla.nombre}».`
                      : "Regla aplicada: lo que falta sigue pendiente.",
                { type: "success" }
            );
            await this.cargarDiarios();
        } finally {
            this.state.trabajando = false;
        }
    }

    reglasDeConciliacion() {
        this.action.doAction("account.action_account_reconcile_model");
    }

    async cargarCandidatos() {
        if (!this.state.linea) {
            this.state.candidatos = [];
            return;
        }
        this.state.candidatos = await this.orm.call("dcasa.conciliacion", "candidatos", [this.state.linea.id], {
            busqueda: this.state.busqueda || null,
        });
        // Lo sugerido (monto y referencia o cliente) queda marcado de entrada.
        const sugeridos = this.state.candidatos.filter((c) => c.sugerido);
        if (sugeridos.length === 1 && !Object.keys(this.state.elegidos).length) {
            this.state.elegidos[sugeridos[0].id] = true;
        }
    }

    buscar(ev) {
        this.state.busqueda = ev.target.value;
        clearTimeout(this._espera);
        this._espera = setTimeout(() => this.cargarCandidatos(), 250);
    }

    cambiarModo(modo) {
        this.state.modo = modo;
    }

    alternar(candidato) {
        this.state.elegidos[candidato.id] = !this.state.elegidos[candidato.id];
    }

    get idsElegidos() {
        return Object.keys(this.state.elegidos)
            .filter((id) => this.state.elegidos[id])
            .map(Number);
    }

    get sumaElegidos() {
        return this.state.candidatos
            .filter((c) => this.state.elegidos[c.id])
            .reduce((total, c) => total + c.pendiente, 0);
    }

    get diferencia() {
        return this.state.linea ? Math.round((this.state.linea.pendiente - this.sumaElegidos) * 100) / 100 : 0;
    }

    get diarioActual() {
        return this.state.diarios.find((d) => d.id === this.state.diario);
    }

    async conciliar() {
        const linea = this.state.linea;
        const conCuenta = this.state.modo === "cuenta";
        if (conCuenta && !this.state.cuenta) {
            this.notification.add("Elige la cuenta donde va este movimiento.", { type: "warning" });
            return;
        }
        if (!conCuenta && !this.idsElegidos.length) {
            this.notification.add("Marca la factura o el pago que corresponde.", { type: "warning" });
            return;
        }
        this.state.trabajando = true;
        try {
            const r = await this.orm.call("dcasa.conciliacion", "conciliar", [linea.id], {
                apunte_ids: conCuenta ? [] : this.idsElegidos,
                cuenta_id: conCuenta ? Number(this.state.cuenta) : null,
                etiqueta: this.state.etiqueta || null,
            });
            this.notification.add(
                r.conciliado ? "Conciliado." : "Conciliado en parte: lo que falta sigue pendiente.",
                { type: "success" }
            );
            this.state.linea = null;
            await this.cargarDiarios();
        } finally {
            this.state.trabajando = false;
        }
    }

    async automatico() {
        this.state.trabajando = true;
        try {
            const n = await this.orm.call("dcasa.conciliacion", "automatico", [this.state.diario]);
            this.notification.add(
                n ? `${n} movimientos conciliados solos.` : "No hubo coincidencias seguras: revisa uno por uno.",
                { type: n ? "success" : "info" }
            );
            await this.cargarDiarios();
        } finally {
            this.state.trabajando = false;
        }
    }

    importar() {
        this.action.doAction("dcasa_contabilidad.accion_importar_extracto", {
            additionalContext: { default_journal_id: this.state.diario },
        });
    }

    nuevoMovimiento() {
        this.action.doAction(
            {
                type: "ir.actions.act_window",
                name: "Movimiento bancario",
                res_model: "account.bank.statement.line",
                views: [[false, "form"]],
                target: "new",
                context: { default_journal_id: this.state.diario },
            },
            { onClose: () => this.cargarDiarios() }
        );
    }

    verConciliados() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Movimientos conciliados",
            res_model: "account.bank.statement.line",
            domain: [
                ["journal_id", "=", this.state.diario],
                ["is_reconciled", "=", true],
            ],
            views: [
                [false, "list"],
                [false, "form"],
            ],
        });
    }
}

registry.category("actions").add("dcasa_conciliacion", DcasaConciliacion);
