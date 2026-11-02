/**
 * «Valor del inventario» (Inventario › Valor del inventario, Estadísticas y el Inicio de Gerencia): la mercancía de hoy
 * al costo y a precio de venta sin ITBMS, por tipo, dónde está el dinero y lo que falta cargar. Las cifras salen de
 * dcasa.tablero.valor_del_inventario; el servidor exige Gerencia o administrador.
 */
import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { FormatoMixin } from "./por_dia";

export class DcasaValorInventario extends FormatoMixin(Component) {
    static template = "dcasa_interfaz.ValorInventario";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ opciones: null, datos: null, cargando: false, error: "" });
        onWillStart(() => this.cargar());
    }

    async cargar() {
        this.state.cargando = true;
        this.state.error = "";
        try {
            const datos = await this.orm.call("dcasa.tablero", "valor_del_inventario", []);
            this.state.opciones = { moneda: datos.moneda };
            this.state.datos = datos;
        } catch (error) {
            this.state.error = error?.data?.message || "No se pudo calcular el valor del inventario.";
        } finally {
            this.state.cargando = false;
        }
    }

    get hayAvisos() {
        const avisos = this.state.datos?.avisos;
        return Boolean(avisos && (avisos.sin_costo.cuantos || avisos.sin_precio.cuantos || avisos.negativos.cuantos));
    }

    productosTexto(cuantos) {
        return `${this.numero(cuantos)} ${cuantos === 1 ? "producto" : "productos"}`;
    }

    maximo(filas, campo) {
        return Math.max(1, ...filas.map((f) => f[campo] || 0));
    }

    /** El ancho de una barra, de 0 a 100 %; lo que no suma (cero o negativo) no tiene barra. */
    medida(valor, maximo) {
        if (!valor || valor <= 0) {
            return 0;
        }
        return Math.max(3, Math.round((valor / maximo) * 100));
    }
}

registry.category("actions").add("dcasa_valor_inventario", DcasaValorInventario);
