/**
 * El menú del celular: UNA sola lista con todo.
 *
 * Odoo trae en el celular un menú de dos caras: al tocar las tres rayas muestra las secciones de la app abierta y, con
 * el botón «Todas las aplicaciones», la lista de apps. En el Inicio (que no tiene secciones) esa primera cara salía
 * vacía, solo con la palabra «Inicio», y no había nada que tocar: parecía una subcarpeta sin salida (reporte de la dueña
 * del 2026-11-11).
 *
 * Aquí el cajón muestra siempre lo mismo que la barra lateral de la computadora (barra_lateral.js), con sus mismas
 * reglas: todas las aplicaciones, y debajo de la que está abierta, sus secciones. Tocar una aplicación la abre y cierra
 * el menú; la flecha de la derecha despliega sus secciones sin salir de donde se está. Arriba, siempre a la vista
 * aunque la lista se deslice, quedan «Inicio» y «Buscar». Nada más que aprender.
 */
import { onMounted, useRef, useState } from "@odoo/owl";
import { NavBar } from "@web/webclient/navbar/navbar";
import { DcasaBarraLateral } from "./barra_lateral";

const MENU_DEL_INICIO = "dcasa_interfaz.menu_dcasa_inicio";

export class DcasaMenuCelular extends DcasaBarraLateral {
    static template = "dcasa_interfaz.MenuCelular";
    static props = { alCerrar: Function };

    setup() {
        super.setup();
        // Qué aplicación está desplegada. Sin elegir (undefined): la que está abierta. null: ninguna.
        this.cajon = useState({ desplegada: undefined });
        this.raiz = useRef("raiz");
        // Si la aplicación abierta queda abajo en la lista (y sus secciones, fuera de la vista), el menú abre ya en ella.
        onMounted(() => {
            const activa = this.raiz.el?.querySelector(".o_dcasa_cajon_item.o_activa");
            const caja = this.raiz.el?.closest(".o_burger_menu_content");
            if (!activa || !caja) {
                return;
            }
            const deLaCaja = caja.getBoundingClientRect();
            const deLaActiva = activa.getBoundingClientRect();
            if (deLaActiva.bottom > deLaCaja.bottom) {
                const fijo = this.raiz.el.querySelector(".o_dcasa_cajon_fijo");
                caja.scrollTop += deLaActiva.top - deLaCaja.top - (fijo ? fijo.offsetHeight : 0) - 8;
            }
        });
    }

    /** El Inicio va aparte, fijo arriba: es a donde más se vuelve y no debe quedar escondido al deslizar la lista. */
    get inicio() {
        return this.apps.find((app) => app.xmlid === MENU_DEL_INICIO) || null;
    }

    get otrasApps() {
        return this.apps.filter((app) => app.xmlid !== MENU_DEL_INICIO);
    }

    estaDesplegada(app) {
        const elegida = this.cajon.desplegada;
        return elegida === undefined ? this.esAppActual(app) : elegida === app.id;
    }

    /** La flecha: muestra u oculta las secciones de una aplicación, sin abrirla. Solo una a la vez. */
    desplegar(app) {
        this.cajon.desplegada = this.estaDesplegada(app) ? null : app.id;
    }

    /** Tocar una aplicación la abre (su pantalla principal) y cierra el menú. */
    elegirApp(app, ev) {
        this.abrir(app, ev);
        // Entrar a una app no elige una sección: se marca la que corresponda a su pantalla.
        this.state.elegido = null;
    }

    /** Abrir cualquier pantalla del menú lo cierra (salvo que se haya pedido «en otra pestaña»). */
    abrir(item, ev) {
        super.abrir(item, ev);
        if (!ev || ev.defaultPrevented) {
            this.props.alCerrar();
        }
    }

    buscar() {
        this.props.alCerrar();
        super.buscar();
    }
}

NavBar.components = { ...NavBar.components, DcasaMenuCelular };
