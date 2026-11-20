/**
 * La pantalla de una versión nueva de las reglas de la comisión no se guarda sola.
 *
 * Una versión guardada no se edita ni se borra (decisión de Gerencia): cada guardado es una versión más para siempre.
 * Odoo guarda solo un formulario con cambios cuando se sale de la página, cuando se cambia de pestaña del navegador y
 * cuando se cierra, y eso dejaba versiones de más sin que nadie hubiera tocado «Guardar». Aquí solo se guarda con el
 * botón: si se sale sin guardar, lo escrito se descarta (el navegador avisa antes de cerrar la pestaña).
 */
import { registry } from "@web/core/registry";
import { formView } from "@web/views/form/form_view";
import { FormController } from "@web/views/form/form_controller";

export class ReglasFormController extends FormController {
    beforeVisibilityChange() {
        // No guardar al cambiar de pestaña del navegador.
    }

    async beforeLeave() {
        // No guardar al salir de la pantalla: una versión nueva se guarda solo con el botón.
    }

    async beforeUnload(ev) {
        if (this.model.root.isNew && this.model.root.dirty) {
            ev.preventDefault();
            ev.returnValue = "Unsaved changes";
        }
    }
}

registry.category("views").add("dcasa_reglas_form", {
    ...formView,
    Controller: ReglasFormController,
});
