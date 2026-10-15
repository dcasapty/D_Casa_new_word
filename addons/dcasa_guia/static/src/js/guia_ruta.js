/**
 * «Llévame ahí»: llevar a la persona a la pantalla justa en un clic, desde cualquier parte de la Guía.
 *
 * El servicio `dcasa_guia_ruta` hace tres cosas, y nada más:
 *  1. Abre el destino (un menú con sus filtros, o un formulario nuevo).
 *  2. Anota, sin esperar y sin que pueda fallar hacia afuera, que la persona usó ese «Llévame ahí»
 *     (dcasa.guia.registrar_uso): de ahí sale «Lo que tú más usas».
 *  3. Deja una cinta pequeña y descartable abajo de la pantalla de destino: «Estás haciendo: …», el paso siguiente y
 *     «Volver a la Guía».
 *
 * La cinta es un componente aparte, registrado en `main_components` (la forma normal de Odoo para cosas que viven fuera
 * de las pantallas): NO se mete dentro de ninguna vista ni formulario de Odoo, así que no puede romper ninguna
 * pantalla; si ella fallara, Odoo solo la quita. Se va sola cuando la persona sale de las pantallas de la tarea o
 * vuelve a la Guía, o cuando la cierra con la «x». Lo único que escribe fuera de sí misma es una variable de estilo
 * (`--dc-cinta-alto`) para que la hoja de estilos le reserve su lugar abajo del contenido.
 */
import { Component, markRaw, reactive, useEffect, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const ACCION_GUIA = "dcasa_guia.accion_guia";
const MENU_GUIA = "dcasa_guia.menu_guia";

/** A dónde lleva el «Llévame ahí» de la tarjeta: su pantalla, o la del primer paso que tenga una. */
export function destinoPrincipal(tarea) {
    if (tarea.destino) {
        return tarea.destino;
    }
    const paso = (tarea.pasos || []).find((p) => p.destino);
    return paso ? paso.destino : null;
}

export const guiaRutaServicio = {
    dependencies: ["action", "menu", "notification", "orm"],
    start(env, { action, menu, notification, orm }) {
        const estado = reactive({ cinta: null });
        // Los avisos de uso salen uno tras otro: así dos clics seguidos no se pisan en el servidor.
        let cola = Promise.resolve();
        // Mientras el propio servicio navega, los avisos de "cambió la pantalla" no son de la persona.
        let navegando = false;

        /** Anota el uso. Fire-and-forget: nadie lo espera y un error solo queda en la consola. */
        function anotarUso(tareaId) {
            cola = cola
                .then(() => orm.silent.call("dcasa.guia", "registrar_uso", [tareaId]))
                .catch((error) => console.warn("Guía: no se pudo anotar el uso", error));
        }

        /** Abre un destino del catálogo. Devuelve true si lo abrió. */
        async function abrir(destino) {
            if (destino.tipo === "menu") {
                const elMenu = menu.getMenu(destino.menu_id);
                if (!elMenu || !elMenu.actionID) {
                    notification.add("Esa pantalla no está disponible ahora.", { type: "warning" });
                    return false;
                }
                await action.doAction(elMenu.actionID, {
                    clearBreadcrumbs: true,
                    additionalContext: destino.contexto || {},
                    onActionReady: () => menu.setCurrentMenu(elMenu),
                });
                return true;
            }
            if (destino.tipo === "nuevo") {
                await action.doAction({
                    type: "ir.actions.act_window",
                    res_model: destino.modelo,
                    views: [[false, "form"]],
                    context: destino.contexto || {},
                });
                return true;
            }
            return false;
        }

        /** Las pantallas de la tarea: mientras la persona esté en una de ellas, la cinta se queda. */
        function pantallasDe(tarea) {
            const ids = new Set();
            const modelos = new Set();
            const destinos = [tarea.destino, ...(tarea.pasos || []).map((p) => p.destino)];
            for (const destino of destinos) {
                if (destino && destino.tipo === "menu") {
                    const elMenu = menu.getMenu(destino.menu_id);
                    if (elMenu && elMenu.actionID) {
                        ids.add(elMenu.actionID);
                    }
                } else if (destino && destino.tipo === "nuevo") {
                    modelos.add(destino.modelo);
                }
            }
            return { ids, modelos };
        }

        function esDeLaTarea(accionActual, pantallas) {
            return Boolean(
                (accionActual.id && pantallas.ids.has(accionActual.id)) ||
                    (accionActual.res_model && pantallas.modelos.has(accionActual.res_model))
            );
        }

        /** Tras llegar: apunta también la pantalla real (un menú puede terminar en otra acción). */
        function recordarLlegada(pantallas) {
            const actual = action.currentController && action.currentController.action;
            if (actual && actual.id) {
                pantallas.ids.add(actual.id);
            }
        }

        function descartar() {
            estado.cinta = null;
        }

        /** Cada vez que Odoo cambia de pantalla: si la persona ya salió de las de la tarea, la cinta se va. */
        function alCambiarDePantalla() {
            if (!estado.cinta || navegando) {
                return;
            }
            try {
                const actual = action.currentController && action.currentController.action;
                if (!actual || actual.tag === "dcasa_guia" || !esDeLaTarea(actual, estado.cinta.pantallas)) {
                    descartar();
                }
            } catch (error) {
                descartar();
            }
        }
        env.bus.addEventListener("ACTION_MANAGER:UI-UPDATED", alCambiarDePantalla);

        /**
         * El «Llévame ahí». `indice`: nulo = el botón de la tarea; un número = el botón de ese paso.
         * `contar: false` para el paso siguiente que se abre desde la cinta (ya es la misma tarea en marcha).
         */
        async function llevar(tarea, indice = null, { contar = true } = {}) {
            const destino = indice === null ? destinoPrincipal(tarea) : (tarea.pasos[indice] || {}).destino;
            if (!destino) {
                return false;
            }
            if (contar) {
                anotarUso(tarea.id);
            }
            navegando = true;
            try {
                if (!(await abrir(destino))) {
                    return false;
                }
                const pantallas = markRaw(pantallasDe(tarea));
                recordarLlegada(pantallas);
                estado.cinta = { tarea: markRaw(tarea), indice, pantallas };
            } finally {
                navegando = false;
            }
            return true;
        }

        return {
            estado,
            llevar,
            descartar,
            /** Pasa al paso siguiente sin ir a ninguna pantalla (un paso que se hace en la que ya estás). */
            avanzar() {
                if (estado.cinta) {
                    estado.cinta.indice = (estado.cinta.indice ?? -1) + 1;
                }
            },
            /** «Volver a la Guía»: la Guía con esta tarea abierta. */
            async volverALaGuia(tareaId) {
                const contexto = tareaId ? { dcasa_guia_tarea: tareaId } : {};
                const laGuia = menu.getAll().find((m) => m.xmlid === MENU_GUIA);
                descartar();
                await action.doAction(ACCION_GUIA, {
                    clearBreadcrumbs: true,
                    additionalContext: contexto,
                    onActionReady: laGuia ? () => menu.setCurrentMenu(laGuia) : undefined,
                });
            },
        };
    },
};

registry.category("services").add("dcasa_guia_ruta", guiaRutaServicio);

/** La cinta: «Estás haciendo: …», el paso siguiente y «Volver a la Guía». Discreta y descartable. */
export class GuiaCinta extends Component {
    static template = "dcasa_guia.Cinta";
    static props = {};

    setup() {
        this.ruta = useService("dcasa_guia_ruta");
        this.estado = useState(this.ruta.estado);
        this.cintaRef = useRef("cinta");
        // La cinta va fija abajo: se le avisa a la hoja de estilos cuánto mide para que reserve ese lugar abajo del
        // contenido y no tape lo último de la pantalla. Es lo único que se escribe fuera del componente.
        useEffect(
            (cinta) => {
                if (!cinta) {
                    return;
                }
                const raiz = document.documentElement;
                const medir = () => raiz.style.setProperty("--dc-cinta-alto", `${cinta.offsetHeight}px`);
                medir();
                const observador = new ResizeObserver(medir);
                observador.observe(cinta);
                return () => {
                    observador.disconnect();
                    raiz.style.removeProperty("--dc-cinta-alto");
                };
            },
            () => [this.cintaRef.el]
        );
    }

    get cinta() {
        return this.estado.cinta;
    }

    get pasos() {
        return this.cinta.tarea.pasos || [];
    }

    /** El paso que la persona está haciendo (0 = el primero); nulo si llegó por el botón de la tarea. */
    get actual() {
        return this.cinta.indice;
    }

    get siguiente() {
        const indice = this.actual === null ? null : this.actual + 1;
        return indice !== null && indice < this.pasos.length ? this.pasos[indice] : null;
    }

    get esUltimo() {
        return this.actual !== null && this.actual === this.pasos.length - 1 && this.pasos.length > 1;
    }

    irAlSiguiente() {
        this.ruta.llevar(this.cinta.tarea, this.actual + 1, { contar: false });
    }
}

registry.category("main_components").add("dcasa_guia.Cinta", { Component: GuiaCinta });
