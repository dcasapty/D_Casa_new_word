/**
 * Barra lateral de D'CASA: la navegación principal de Odoo, a la izquierda.
 *
 * Buenas prácticas aplicadas (Apple HIG «Sidebars», guías de paneles admin):
 *  · Ícono + texto; se colapsa a solo íconos y recuerda la preferencia.
 *  · Máximo dos niveles a la vista: las apps y las secciones de la app abierta
 *    (los grupos de secciones se despliegan en su lugar).
 *  · Accesible: <nav> con nombre, aria-current en lo activo, aria-expanded en lo que
 *    se despliega, foco visible y enlaces reales (Ctrl/⌘ + clic abre en otra pestaña).
 *  · Búsqueda global a un clic (la paleta de comandos, Ctrl+K).
 */
import { Component, useState } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { router } from "@web/core/browser/router";
import { useBus, useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { WebClient } from "@web/webclient/webclient";

const CLAVE = "dcasa.barra_lateral.colapsada";

function leerPreferencia() {
    try {
        return browser.localStorage.getItem(CLAVE) === "1";
    } catch {
        return false;
    }
}

export class DcasaBarraLateral extends Component {
    static template = "dcasa_interfaz.BarraLateral";
    static props = {};

    setup() {
        this.menu = useService("menu");
        this.action = useService("action");
        this.command = useService("command");
        this.state = useState({ colapsada: leerPreferencia(), abiertos: {}, version: 0 });
        this.aplicarAncho();
        const refrescar = () => this.state.version++;
        useBus(this.env.bus, "MENUS:APP-CHANGED", refrescar);
        useBus(this.env.bus, "ACTION_MANAGER:UI-UPDATED", refrescar);
    }

    get apps() {
        this.state.version;
        return this.menu.getApps();
    }

    get appActual() {
        this.state.version;
        return this.menu.getCurrentApp();
    }

    get accionActual() {
        this.state.version;
        // La acción abierta según la dirección (/odoo/action-552 o /odoo/ventas): es lo que el
        // usuario ve y comparte, y no depende de detalles internos del gestor de acciones.
        const actual = this.env.services.action.currentController?.action?.id;
        if (actual) {
            return actual;
        }
        const enRuta = router.current?.action;
        return typeof enRuta === "number" ? enRuta : Number(enRuta) || undefined;
    }

    esAppActual(app) {
        return this.appActual?.id === app.id;
    }

    secciones(app) {
        return this.menu.getMenuAsTree(app.id).childrenTree || [];
    }

    esActiva(item) {
        return Boolean(item.actionID) && item.actionID === this.accionActual;
    }

    contieneActiva(seccion) {
        return (seccion.childrenTree || []).some((hijo) => this.esActiva(hijo) || this.contieneActiva(hijo));
    }

    abierto(seccion) {
        const elegido = this.state.abiertos[seccion.id];
        return elegido === undefined ? this.contieneActiva(seccion) : elegido;
    }

    alternar(seccion) {
        this.state.abiertos[seccion.id] = !this.abierto(seccion);
    }

    enlace(item) {
        return item.actionID ? `/odoo/action-${item.actionID}` : "/odoo";
    }

    icono(app) {
        const data = app.webIconData;
        if (!data || data.startsWith("data:") || data.startsWith("/")) {
            return data;
        }
        return `data:${app.webIconDataMimetype || "image/svg+xml"};base64,${data.replace(/\s/g, "")}`;
    }

    abrir(item, ev) {
        // Ctrl/⌘ + clic o clic del medio: el navegador abre el enlace en otra pestaña.
        if (ev && (ev.ctrlKey || ev.metaKey || ev.shiftKey || ev.button === 1)) {
            return;
        }
        ev?.preventDefault();
        this.menu.selectMenu(item);
    }

    buscar() {
        this.command.openMainPalette({});
    }

    alternarBarra() {
        this.state.colapsada = !this.state.colapsada;
        try {
            browser.localStorage.setItem(CLAVE, this.state.colapsada ? "1" : "0");
        } catch {
            // Sin almacenamiento (modo privado): la preferencia dura la sesión.
        }
        this.aplicarAncho();
    }

    aplicarAncho() {
        document.body.classList.toggle("o_dcasa_barra_colapsada", this.state.colapsada);
    }
}

WebClient.components = { ...WebClient.components, DcasaBarraLateral };

patch(WebClient.prototype, {
    setup() {
        super.setup();
        document.body.classList.add("o_dcasa_con_barra");
    },
});
