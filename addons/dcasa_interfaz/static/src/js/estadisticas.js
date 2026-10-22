/**
 * «Estadísticas › Resumen»: cómo van las ventas en gráficas simples y planas (barras por día, por tipo de producto,
 * por vendedora y lo más vendido), cada número con una frase que dice qué es. Las cifras salen de
 * dcasa.tablero.estadisticas (las mismas bases del Inicio); el servidor exige Gerencia o administrador.
 */
import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { FormatoMixin } from "./por_dia";

const PERIODOS = [
    { clave: "semana", nombre: "Esta semana" },
    { clave: "mes", nombre: "Este mes" },
    { clave: "mes_pasado", nombre: "Mes pasado" },
    { clave: "tres_meses", nombre: "Últimos 3 meses" },
    { clave: "anio", nombre: "Este año" },
    { clave: "rango", nombre: "Elegir fechas" },
];

export class DcasaEstadisticas extends FormatoMixin(Component) {
    static template = "dcasa_interfaz.Estadisticas";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.periodos = PERIODOS;
        this.state = useState({
            opciones: null,
            datos: null,
            periodo: "mes",
            base: "facturado",
            desde: "",
            hasta: "",
            cargando: false,
            error: "",
        });
        onWillStart(async () => {
            this.state.opciones = await this.orm.call("dcasa.tablero", "opciones_por_dia", []);
            await this.cargar();
        });
    }

    get hoy() {
        return this.state.opciones?.hoy || "";
    }

    get esPedido() {
        return this.state.base === "confirmado";
    }

    get detalleBase() {
        const base = (this.state.opciones?.bases || []).find((b) => b.clave === this.state.base);
        return base ? base.detalle : "";
    }

    async cargar() {
        this.state.cargando = true;
        this.state.error = "";
        try {
            this.state.datos = await this.orm.call("dcasa.tablero", "estadisticas", [], {
                periodo: this.state.periodo,
                desde: this.state.periodo === "rango" ? this.state.desde : false,
                hasta: this.state.periodo === "rango" ? this.state.hasta : false,
                base: this.state.base,
            });
        } catch (error) {
            this.state.error = error?.data?.message || "No se pudieron cargar las estadísticas.";
        } finally {
            this.state.cargando = false;
        }
    }

    async cambiarPeriodo(clave) {
        this.state.periodo = clave;
        if (clave === "rango") {
            if (!this.state.desde || !this.state.hasta) {
                this.state.hasta = this.hoy;
                this.state.desde = this.hoy.slice(0, 8) + "01";
            }
        }
        await this.cargar();
    }

    async aplicarRango() {
        if (!this.state.desde || !this.state.hasta || this.state.desde > this.state.hasta) {
            this.state.error = "Escribe un rango válido: «desde» no puede ser después de «hasta».";
            return;
        }
        await this.cargar();
    }

    async cambiarBase(clave) {
        if (clave !== this.state.base) {
            this.state.base = clave;
            await this.cargar();
        }
    }

    // ------------------------------------------------------------------
    // Gráficas
    // ------------------------------------------------------------------

    maximo(filas, campo = "sin_itbms") {
        return Math.max(1, ...filas.map((f) => f[campo] || 0));
    }

    /** El alto (barras) o el ancho (filas) de una barra, de 0 a 100 %; lo negativo (devoluciones) no tiene barra. */
    medida(valor, maximo) {
        if (!valor || valor <= 0) {
            return 0;
        }
        return Math.max(3, Math.round((valor / maximo) * 100));
    }

    /** Cada cuántas barras se escribe la etiqueta de abajo (para que no se amontonen en el celular). */
    get paso() {
        const n = this.state.datos?.barras.filas.length || 0;
        return n <= 12 ? 1 : Math.ceil(n / 8);
    }

    etiquetaVisible(indice, total) {
        return indice % this.paso === 0 || indice === total - 1;
    }

    get mejorBarra() {
        const filas = this.state.datos?.barras.filas || [];
        return filas.reduce((mejor, f) => (f.sin_itbms > (mejor?.sin_itbms || 0) ? f : mejor), null);
    }

    /** Una barra abre «Por día» en ese día (o en ese mes), con la misma base. */
    abrirBarra(fila) {
        const contexto = { dcasa_base: this.state.base, dcasa_mes: fila.mes };
        if (this.state.datos.barras.por === "dia") {
            contexto.dcasa_dia = fila.clave;
        }
        this.action.doAction("dcasa_interfaz.accion_facturado_por_dia", { additionalContext: contexto });
    }

    abrirPorDia() {
        this.action.doAction("dcasa_interfaz.accion_facturado_por_dia", {
            additionalContext: { dcasa_base: this.state.base },
        });
    }

    abrirAccion(xmlid) {
        this.action.doAction(xmlid);
    }

    abrirInicio() {
        this.action.doAction("dcasa_interfaz.action_dcasa_inicio", { clearBreadcrumbs: true });
    }

    abrirProducto(p) {
        this.abrirDocumento("product.template", p.id);
    }
}

registry.category("actions").add("dcasa_estadisticas", DcasaEstadisticas);
