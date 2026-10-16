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
    mis_cotizaciones: "fa-user-o",
    web: "fa-globe",
    por_cobrar: "fa-clock-o",
    entregas: "fa-truck",
    socios: "fa-star",
};

const PERIODOS = [
    { clave: "hoy", nombre: "Hoy" },
    { clave: "semana", nombre: "Esta semana" },
    { clave: "mes", nombre: "Este mes" },
    { clave: "rango", nombre: "Un rango" },
];

export class DcasaInicio extends Component {
    static template = "dcasa_interfaz.Inicio";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.menu = useService("menu");
        this.periodos = PERIODOS;
        this.state = useState({
            datos: null,
            periodo: "hoy",
            desde: "",
            hasta: "",
            errorRango: "",
            cargandoVentas: false,
        });
        onWillStart(() => this.cargar());
    }

    async cargar() {
        this.state.datos = await this.orm.call("dcasa.tablero", "obtener_datos", []);
    }

    get apps() {
        return this.menu.getApps().filter((app) => app.xmlid !== "dcasa_interfaz.menu_dcasa_inicio");
    }

    get hoyIso() {
        const ahora = new Date();
        const mes = String(ahora.getMonth() + 1).padStart(2, "0");
        const dia = String(ahora.getDate()).padStart(2, "0");
        return `${ahora.getFullYear()}-${mes}-${dia}`;
    }

    /** Cambia el periodo de las ventas (Hoy · Esta semana · Este mes) y pide solo esa tarjeta al servidor. */
    async cambiarPeriodo(periodo) {
        this.state.periodo = periodo;
        this.state.errorRango = "";
        if (periodo === "rango") {
            if (!this.state.desde || !this.state.hasta) {
                this.state.desde = this.state.desde || this.hoyIso;
                this.state.hasta = this.state.hasta || this.hoyIso;
            }
            return this.aplicarRango();
        }
        await this.cargarVentas(periodo);
    }

    async aplicarRango() {
        if (!this.state.desde || !this.state.hasta || this.state.desde > this.state.hasta) {
            this.state.errorRango = "Escribe un rango válido: «desde» no puede ser después de «hasta».";
            return;
        }
        this.state.errorRango = "";
        await this.cargarVentas("rango", this.state.desde, this.state.hasta);
    }

    async cargarVentas(periodo, desde = false, hasta = false) {
        this.state.cargandoVentas = true;
        try {
            this.state.datos.ventas = await this.orm.call("dcasa.tablero", "ventas_del_periodo", [periodo, desde, hasta]);
        } catch (error) {
            this.state.errorRango = error?.data?.message || "No se pudieron cargar las ventas.";
        } finally {
            this.state.cargandoVentas = false;
        }
    }

    variacion(pct) {
        const numero = new Intl.NumberFormat("es-PA", { maximumFractionDigits: 1 }).format(Math.abs(pct));
        return `${pct >= 0 ? "+" : "−"}${numero} %`;
    }

    /** «hace 3 días» para las listas de cotizaciones y entregas. */
    espera(dias) {
        if (!dias) {
            return "de hoy";
        }
        return dias === 1 ? "hace 1 día" : `hace ${dias} días`;
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
        this.abrirLista(c.accion);
    }

    /** Abre la lista que explica una cifra o un aviso. */
    abrirLista(a) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: a.name,
            res_model: a.res_model,
            domain: a.domain,
            // Una lista puede pedir su vista (p. ej. la de facturas, con los montos sin ITBMS).
            views: [
                [a.vista_lista || false, "list"],
                [false, "form"],
            ],
        });
    }

    /** Abre una cotización o una entrega concreta (las filas de las listas del Inicio). */
    abrirRegistro(modelo, id) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: modelo,
            res_id: id,
            views: [[false, "form"]],
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

    /** «¿Qué necesito hacer?»: la Guía del negocio (módulo dcasa_guia). */
    abrirGuia() {
        // Por su menú, para que la barra de arriba y la de la izquierda digan «Guía» y no «Inicio».
        const menu = this.menu.getAll().find((m) => m.xmlid === "dcasa_guia.menu_guia");
        if (menu) {
            this.menu.selectMenu(menu);
        } else {
            this.action.doAction("dcasa_guia.accion_guia", { clearBreadcrumbs: true });
        }
    }

    /** Un acceso directo del Inicio: abre su pantalla (en la vista que dice el servidor, p. ej. lista). */
    abrirAtajo(atajo) {
        this.action.doAction(atajo.accion, atajo.vista ? { viewType: atajo.vista } : {});
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
