/**
 * «Armar combo cama + colchón» (pedido de la dueña, 2026-10-22).
 *
 * Panel que se abre encima de la cotización: escoges la cama (buscador con foto, medida, precio y existencia) y te
 * muestra los colchones de su medida con existencia, con su precio normal, su precio en combo y el ahorro. Un toque y
 * se agregan las dos líneas. Arriba, los combos que ya tiene la cotización: cambiar la cama, cambiar el colchón o
 * quitarlo. Todas las reglas (medida, precio en combo, existencias, tope) viven en el servidor
 * (dcasa_catalogo/models/combo_armable.py); aquí solo se pinta y se llama.
 */
import { Component, onWillStart, useRef, useState } from "@odoo/owl";
import { formatCurrency } from "@web/core/currency";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { debounce } from "@web/core/utils/timing";

export class DcasaArmarCombo extends Component {
    static template = "dcasa_catalogo.ArmarCombo";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.ordenId = this.props.action?.params?.order_id || this.props.action?.context?.active_id;
        this.buscador = useRef("buscador");
        this.state = useState({
            cargando: true,
            trabajando: false,
            panel: null,
            paso: "inicio",
            modo: { tipo: "nuevo" },
            texto: "",
            medida: "",
            camas: [],
            hayMas: false,
            cama: null,
            colchones: [],
            agotados: 0,
            todos: false,
            faltaMedida: false,
            cantidad: 1,
            aviso: "",
        });
        this.buscarConPausa = debounce(() => this.buscarCamas(), 250);
        onWillStart(async () => {
            await this.cargarPanel();
            if (!this.tieneAlgo) {
                await this.irACamas({ tipo: "nuevo" });
            }
            this.state.cargando = false;
        });
    }

    // ------------------------------------------------------------------
    // Datos
    // ------------------------------------------------------------------

    async llamar(metodo, args = [], kwargs = {}) {
        return this.orm.call("sale.order", metodo, [[this.ordenId], ...args], kwargs);
    }

    async cargarPanel() {
        this.state.panel = await this.llamar("dcasa_combo_panel");
    }

    get tieneAlgo() {
        const p = this.state.panel;
        return Boolean(p && (p.combos.length || p.camas_solas.length || p.colchones_sueltos.length));
    }

    get editable() {
        return Boolean(this.state.panel?.orden.editable);
    }

    dinero(monto) {
        return formatCurrency(monto || 0, this.state.panel?.orden.moneda_id);
    }

    unidades(n) {
        if (n === null || n === undefined) {
            return "";
        }
        const entero = Math.round(n);
        if (entero <= 0) {
            return "Agotado";
        }
        return entero === 1 ? "1 disponible" : `${entero} disponibles`;
    }

    cantidadTexto(n) {
        return Number.isInteger(n) ? String(n) : String(Math.round(n * 100) / 100);
    }

    // ------------------------------------------------------------------
    // Pasos
    // ------------------------------------------------------------------

    async irACamas(modo) {
        this.state.modo = modo;
        this.state.paso = "cama";
        this.state.aviso = "";
        this.state.cama = null;
        this.state.cantidad = 1;
        await this.buscarCamas();
        setTimeout(() => this.buscador.el?.focus(), 50);
    }

    async irAColchones(cama, modo) {
        if (modo) {
            this.state.modo = modo;
        }
        this.state.cama = cama;
        this.state.paso = "colchon";
        this.state.todos = false;
        this.state.aviso = "";
        await this.cargarColchones();
    }

    volverAlInicio() {
        this.state.paso = "inicio";
        this.state.modo = { tipo: "nuevo" };
        this.state.cama = null;
    }

    async buscarCamas() {
        const respuesta = await this.llamar("dcasa_combo_camas", [], {
            texto: this.state.texto,
            medida: this.state.medida,
        });
        this.state.camas = respuesta.camas;
        this.state.hayMas = respuesta.hay_mas;
    }

    onTexto(ev) {
        this.state.texto = ev.target.value;
        this.buscarConPausa();
    }

    async elegirMedida(medida) {
        this.state.medida = medida;
        await this.buscarCamas();
    }

    async cargarColchones() {
        const respuesta = await this.llamar("dcasa_combo_colchones", [this.state.cama.id], { todos: this.state.todos });
        this.state.cama = { ...this.state.cama, ...respuesta.cama };
        this.state.colchones = respuesta.colchones;
        this.state.agotados = respuesta.agotados;
        this.state.faltaMedida = respuesta.falta_medida;
    }

    async verTodos() {
        this.state.todos = !this.state.todos;
        await this.cargarColchones();
    }

    cambiarCantidad(delta) {
        this.state.cantidad = Math.min(20, Math.max(1, this.state.cantidad + delta));
    }

    /** La cama del panel. Al cambiar la cama de un combo, si el colchón ya es de su medida se cambia de una vez. */
    async elegirCama(cama) {
        const modo = this.state.modo;
        if (modo.tipo === "cambiar_cama") {
            const colchon = modo.combo.colchones[0];
            if (!colchon || colchon.medida === cama.medida) {
                await this.guardar("dcasa_combo_cambiar", [modo.combo.cama.linea_id], { cama_id: cama.id },
                                   "Listo: cambiamos la cama del combo.");
                return;
            }
        }
        await this.irAColchones(cama);
    }

    async elegirColchon(colchon) {
        const modo = this.state.modo;
        if (modo.tipo === "nuevo") {
            await this.guardar("dcasa_combo_agregar", [], {
                cama_id: this.state.cama.id, colchon_id: colchon.id, cantidad: this.state.cantidad,
            }, "Listo: agregamos el combo a la cotización.");
        } else if (modo.tipo === "colchon_para") {
            await this.guardar("dcasa_combo_agregar", [], { colchon_id: colchon.id, cama_linea_id: modo.linea.linea_id },
                               "Listo: agregamos el colchón a la cama.");
        } else if (modo.tipo === "cambiar_colchon") {
            await this.guardar("dcasa_combo_cambiar", [modo.combo.cama.linea_id], {
                colchon_id: colchon.id, colchon_linea_id: modo.combo.colchones[0]?.linea_id || false,
            }, "Listo: cambiamos el colchón del combo.");
        } else if (modo.tipo === "cambiar_cama") {
            await this.guardar("dcasa_combo_cambiar", [modo.combo.cama.linea_id], {
                cama_id: this.state.cama.id, colchon_id: colchon.id,
                colchon_linea_id: modo.combo.colchones[0]?.linea_id || false,
            }, "Listo: cambiamos la cama y el colchón del combo.");
        }
    }

    cambiarCama(combo) {
        return this.irACamas({ tipo: "cambiar_cama", combo });
    }

    cambiarColchon(combo) {
        return this.irAColchones({ id: combo.cama.id, ...combo.cama }, { tipo: "cambiar_colchon", combo });
    }

    colchonPara(linea) {
        return this.irAColchones({ id: linea.id, ...linea }, { tipo: "colchon_para", linea });
    }

    quitar(combo) {
        return this.guardar("dcasa_combo_quitar", [combo.cama.linea_id], {}, "Quitamos el combo de la cotización.");
    }

    quitarColchon(colchon) {
        return this.guardar("dcasa_combo_quitar", [false], { colchon_linea_id: colchon.linea_id },
                            "Quitamos el colchón de la cotización.");
    }

    async guardar(metodo, args, kwargs, aviso) {
        if (this.state.trabajando) {
            return;
        }
        this.state.trabajando = true;
        try {
            this.state.panel = await this.llamar(metodo, args, kwargs);
            this.volverAlInicio();
            this.state.aviso = aviso;
        } finally {
            this.state.trabajando = false;
        }
    }

    esActual(colchon) {
        const modo = this.state.modo;
        return modo.tipo === "cambiar_colchon" && modo.combo.colchones.some((c) => c.id === colchon.id);
    }

    get tituloColchones() {
        const medida = this.state.cama?.medida;
        const paso = this.state.modo.tipo === "nuevo" || this.state.modo.tipo === "cambiar_cama" ? "2. " : "";
        return medida ? `${paso}Escoge el colchón ${medida}` : `${paso}Escoge el colchón`;
    }

    get tituloCamas() {
        return this.state.modo.tipo === "cambiar_cama" ? "Escoge la cama nueva" : "1. Escoge la cama";
    }

    /** En un combo nuevo o al cambiar la cama, el paso 2 vuelve a la cama; si no, a los combos. */
    get eligeCama() {
        return ["nuevo", "cambiar_cama"].includes(this.state.modo.tipo);
    }

    volverDesdeColchones() {
        return this.eligeCama ? this.irACamas(this.state.modo) : this.volverAlInicio();
    }

    cerrar() {
        return this.action.doAction({ type: "ir.actions.act_window_close" });
    }
}

registry.category("actions").add("dcasa_armar_combo", DcasaArmarCombo);
