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
import { Component, onWillUnmount, useState } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { router } from "@web/core/browser/router";
import { useBus, useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { WebClient } from "@web/webclient/webclient";

const CLAVE = "dcasa.barra_lateral.modo";
// Espera antes de recoger la barra al salir el mouse (evita que se cierre por un roce).
const ESPERA_RECOGER = 350;
const ESPERA_ABRIR = 120;

function leerModo() {
    try {
        return browser.localStorage.getItem(CLAVE) === "fija" ? "fija" : "auto";
    } catch {
        return "auto";
    }
}

export class DcasaBarraLateral extends Component {
    static template = "dcasa_interfaz.BarraLateral";
    static props = {};

    setup() {
        this.menu = useService("menu");
        this.action = useService("action");
        this.command = useService("command");
        // Menús especiales del sitio web (propiedades, SEO, editor HTML…): se abren como ventanas.
        this.menusSitio = this.env.services.website_custom_menus || null;
        this.state = useState({ modo: leerModo(), encima: false, abiertos: {}, version: 0, elegido: null });
        this.aplicarAncho();
        const refrescar = () => this.state.version++;
        useBus(this.env.bus, "MENUS:APP-CHANGED", refrescar);
        useBus(this.env.bus, "ACTION_MANAGER:UI-UPDATED", refrescar);
        const sistemaSitio = registry.category("website_systray");
        useBus(sistemaSitio, "CONTENT-UPDATED", refrescar);
        useBus(sistemaSitio, "EDIT-WEBSITE", refrescar);
        onWillUnmount(() => clearTimeout(this.temporizador));
    }

    /** En modo automático la barra es una franja de íconos que se abre sola al acercar el mouse. */
    get expandida() {
        return this.state.modo === "fija" || this.state.encima;
    }

    get colapsada() {
        return !this.expandida;
    }

    entrar() {
        if (this.state.modo !== "auto") {
            return;
        }
        clearTimeout(this.temporizador);
        this.temporizador = setTimeout(() => (this.state.encima = true), ESPERA_ABRIR);
    }

    salir() {
        if (this.state.modo !== "auto") {
            return;
        }
        clearTimeout(this.temporizador);
        this.temporizador = setTimeout(() => (this.state.encima = false), ESPERA_RECOGER);
    }

    recoger() {
        clearTimeout(this.temporizador);
        this.state.encima = false;
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
        this.state.version;
        const arbol = this.menu.getMenuAsTree(app.id).childrenTree || [];
        if (this.menusSitio && app.xmlid === "website.menu_website_configuration") {
            // Igual que la barra de Odoo: solo los menús del sitio que aplican a la página abierta.
            return this.menusSitio.addCustomMenus(arbol).filter((s) => s.childrenTree.length || s.actionID);
        }
        return arbol;
    }

    esEspecial(item) {
        return Boolean(this.menusSitio && item.xmlid && this.menusSitio.get(item.xmlid));
    }

    esActiva(item) {
        if (!item.actionID || item.actionID !== this.accionActual || this.esEspecial(item)) {
            return false;
        }
        // Varios menús pueden compartir la acción: se marca el que el usuario eligió.
        const elegido = this.state.elegido;
        return !elegido || elegido.actionID !== item.actionID || elegido.id === item.id;
    }

    contieneActiva(seccion) {
        return (seccion.childrenTree || []).some((hijo) => this.esActiva(hijo) || this.contieneActiva(hijo));
    }

    abierto(seccion) {
        const elegido = this.state.abiertos[seccion.id];
        return elegido === undefined ? this.contieneActiva(seccion) : elegido;
    }

    alternar(seccion, hermanos = []) {
        const abrir = !this.abierto(seccion);
        if (abrir) {
            // Acordeón: al abrir un grupo se recogen sus hermanos.
            for (const otro of hermanos) {
                if (otro.id !== seccion.id) {
                    this.state.abiertos[otro.id] = false;
                }
            }
        }
        this.state.abiertos[seccion.id] = abrir;
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
        if (this.esEspecial(item)) {
            this.menusSitio.open(item);
        } else {
            this.state.elegido = { id: item.id, actionID: item.actionID };
            this.menu.selectMenu(item);
        }
        // En modo automático, elegir una pantalla recoge la barra.
        if (this.state.modo === "auto" && !(item.childrenTree && item.childrenTree.length) && item.actionID) {
            this.recoger();
        }
    }

    abrirApp(app, ev) {
        // Sin mouse (pantalla táctil) o con la barra recogida: tocar la app la despliega.
        if (this.state.modo === "auto" && !this.state.encima && ev && ev.pointerType === "touch") {
            ev.preventDefault();
            this.state.encima = true;
            return;
        }
        this.abrir(app, ev);
        // Entrar a una app no elige una sección: se marca la que corresponda a su acción.
        this.state.elegido = null;
    }

    buscar() {
        this.command.openMainPalette({});
    }

    alternarBarra() {
        this.state.modo = this.state.modo === "fija" ? "auto" : "fija";
        this.state.encima = false;
        try {
            browser.localStorage.setItem(CLAVE, this.state.modo);
        } catch {
            // Sin almacenamiento (modo privado): la preferencia dura la sesión.
        }
        this.aplicarAncho();
    }

    aplicarAncho() {
        // En modo automático el contenido deja solo el espacio de la franja de íconos;
        // la barra abierta por el mouse flota encima sin mover la pantalla.
        document.body.classList.toggle("o_dcasa_barra_colapsada", this.state.modo === "auto");
    }
}

WebClient.components = { ...WebClient.components, DcasaBarraLateral };

patch(WebClient.prototype, {
    setup() {
        super.setup();
        document.body.classList.add("o_dcasa_con_barra");
    },
});
