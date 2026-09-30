/**
 * «Inicio»: cómo va el día en D'CASA, en una pantalla.
 *
 * Las cifras vienen de dcasa.tablero.obtener_datos (respetan los permisos de quien mira)
 * y cada una abre la lista que la explica. Debajo, los accesos del día a día y las apps.
 */
import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const ICONOS = {
    ventas_hoy: "fa-shopping-bag",
    cobrado_hoy: "fa-money",
    cotizaciones: "fa-file-text-o",
    web: "fa-globe",
    por_cobrar: "fa-clock-o",
    entregas: "fa-truck",
    socios: "fa-star",
};

export class DcasaInicio extends Component {
    static template = "dcasa_interfaz.Inicio";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.menu = useService("menu");
        this.state = useState({ datos: null });
        onWillStart(() => this.cargar());
    }

    async cargar() {
        this.state.datos = await this.orm.call("dcasa.tablero", "obtener_datos", []);
    }

    get apps() {
        return this.menu.getApps().filter((app) => app.xmlid !== "dcasa_interfaz.menu_dcasa_inicio");
    }

    get maxSemana() {
        return Math.max(1, ...this.state.datos.semana.map((d) => d.monto));
    }

    icono(cifra) {
        return ICONOS[cifra.clave] || "fa-circle";
    }

    dinero(valor) {
        const { simbolo, antes } = this.state.datos.moneda;
        const numero = new Intl.NumberFormat("en-US", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        }).format(valor || 0);
        return antes ? `${simbolo}${numero}` : `${numero} ${simbolo}`;
    }

    cifra(c) {
        return c.formato === "moneda" ? this.dinero(c.valor) : new Intl.NumberFormat("en-US").format(c.valor);
    }

    abrirCifra(c) {
        const a = c.accion;
        this.action.doAction({
            type: "ir.actions.act_window",
            name: a.name,
            res_model: a.res_model,
            domain: a.domain,
            views: [
                [false, "list"],
                [false, "form"],
            ],
        });
    }

    iconoApp(app) {
        const data = app.webIconData;
        if (!data || data.startsWith("data:") || data.startsWith("/")) {
            return data;
        }
        return `data:${app.webIconDataMimetype || "image/svg+xml"};base64,${data.replace(/\s/g, "")}`;
    }

    abrirApp(app) {
        this.menu.selectMenu(app);
    }

    nuevo(modelo, contexto = {}) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: modelo,
            views: [[false, "form"]],
            context: contexto,
        });
    }

    catalogo() {
        this.action.doAction("sale.product_template_action");
    }

    abrirProducto(p) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "product.template",
            res_id: p.id,
            views: [[false, "form"]],
        });
    }

    verTienda() {
        window.open("/shop", "_blank");
    }
}

registry.category("actions").add("dcasa_inicio", DcasaInicio);
