/**
 * Actividad (el panel de mensajes y notas de la derecha de los formularios): oculta por defecto.
 *
 * Odoo la pone al lado de cada formulario (cotización, factura, ficha…) y roba un buen pedazo de la pantalla para
 * mostrar «Creando un nuevo registro…» y cosas que casi nadie lee. Aquí arranca oculta y un botón «Actividad» arriba
 * la muestra u oculta. Lo que cada quien elige se recuerda en su navegador (localStorage), igual para todos los
 * formularios; si el navegador no deja guardar, simplemente vuelve a empezar oculta.
 *
 * Solo cambia dónde se pinta el panel (``mailLayout``): los mensajes, notas y seguidores siguen existiendo.
 */
import { reactive, useState } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";
import { FormRenderer } from "@web/views/form/form_renderer";

export const CLAVE_ACTIVIDAD = "dcasa.actividad_visible";

function leerGuardado() {
    try {
        return browser.localStorage.getItem(CLAVE_ACTIVIDAD) === "1";
    } catch {
        return false; // sin almacenamiento (ventana privada, bloqueado): oculta
    }
}

/** El estado compartido por todos los formularios abiertos: ``visible`` (oculta por defecto). */
export const actividad = reactive({ visible: leerGuardado() });

export function alternarActividad() {
    actividad.visible = !actividad.visible;
    try {
        browser.localStorage.setItem(CLAVE_ACTIVIDAD, actividad.visible ? "1" : "0");
    } catch {
        // no se pudo recordar: vale para esta pantalla
    }
}

patch(FormRenderer.prototype, {
    setup() {
        super.setup(...arguments);
        this.dcasaActividad = useState(actividad);
    },
    /** El panel solo se pinta (al lado o abajo) si la persona lo pidió; el visor de adjuntos («COMBO») no se toca. */
    mailLayout() {
        const disposicion = super.mailLayout(...arguments);
        if (!this.dcasaActividad.visible && (disposicion === "SIDE_CHATTER" || disposicion === "BOTTOM_CHATTER")) {
            return "NONE";
        }
        return disposicion;
    },
});

patch(FormController.prototype, {
    setup() {
        super.setup(...arguments);
        this.dcasaActividad = useState(actividad);
    },
    /** ¿Este formulario tiene panel de actividad? (el botón solo sale donde hay algo que mostrar). */
    get dcasaHayActividad() {
        return !this.env.inDialog && !!this.archInfo?.xmlDoc?.querySelector("chatter");
    },
    dcasaAlternarActividad() {
        alternarActividad();
    },
});
