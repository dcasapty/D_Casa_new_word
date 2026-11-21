/**
 * Quinta revisión adversarial, bloqueante 1: el recorrido COMPLETO con el que Gerencia o Nómina encienden el cobro
 * desde la pantalla, con clics de verdad (como los de una persona) y no con llamadas al servidor.
 *
 * Antes de arreglarlo, «Agregar una línea» en «Quiénes reciben» no dejaba agregar a nadie (la sublista salía como no
 * editable porque nadie tiene permiso de escribir el reparto), y sin reparto el servidor no guarda una versión con
 * porcentaje ni tarifa. Las pruebas de las rondas 3 y 4 solo guardaban una versión en pausa (0 %, sin reparto) y nunca
 * agregaban a nadie, por eso nadie lo vio.
 */
import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("dcasa_comision_web_nueva_version_con_reparto", {
    url: "/odoo/action-dcasa_comision_web.accion_reglas",
    steps: () => [
        { trigger: ".o_control_panel button[name=action_nueva_version]", run: "click" },
        { trigger: ".o_form_view [name=porcentaje] input", run: "edit 12" },
        // Primera persona: Ana, 60 %.
        { trigger: ".o_form_view .o_field_x2many_list_row_add a", run: "click" },
        { trigger: ".o_form_view [name=reparto_ids] .o_data_row.o_selected_row [name=empleado_id] input", run: "edit Ana Tour" },
        { trigger: ".o-autocomplete--dropdown-item:contains('Ana Tour')", run: "click" },
        { trigger: ".o_form_view [name=reparto_ids] .o_data_row.o_selected_row [name=porcentaje] input", run: "edit 60" },
        // Segunda persona: Beto, 40 %.
        { trigger: ".o_form_view .o_field_x2many_list_row_add a", run: "click" },
        { trigger: ".o_form_view [name=reparto_ids] .o_data_row.o_selected_row [name=empleado_id] input", run: "edit Beto Tour" },
        { trigger: ".o-autocomplete--dropdown-item:contains('Beto Tour')", run: "click" },
        { trigger: ".o_form_view [name=reparto_ids] .o_data_row.o_selected_row [name=porcentaje] input", run: "edit 40" },
        { trigger: ".o_form_button_save", run: "click" },
        // Guardada: ya tiene número (solo una versión guardada lo muestra) y el formulario quedó limpio.
        { trigger: ".o_form_view [name=numero]" },
        { trigger: ".o_form_view:not(.o_form_dirty)" },
    ],
});

registry.category("web_tour.tours").add("dcasa_comision_web_cambiar_quienes_reciben", {
    url: "/odoo/action-dcasa_comision_web.accion_quienes_reciben",
    steps: () => [
        // «Quiénes reciben» → «Cambiar quiénes reciben»: abre una versión nueva con las personas de hoy ya escritas.
        { trigger: ".o_control_panel button[name=action_cambiar_quienes_reciben]", run: "click" },
        { trigger: ".o_form_view [name=reparto_ids] .o_data_row:nth-child(2)" },
        // Ana baja de 60 % a 50 %.
        { trigger: ".o_form_view [name=reparto_ids] .o_data_row:nth-child(1) td[name=porcentaje]", run: "click" },
        { trigger: ".o_form_view [name=reparto_ids] .o_data_row.o_selected_row [name=porcentaje] input", run: "edit 50" },
        // Beto sale y entra Carla con el otro 50 %.
        { trigger: ".o_form_view [name=reparto_ids] .o_data_row:nth-child(2) td[name=empleado_id]", run: "click" },
        { trigger: ".o_form_view [name=reparto_ids] .o_data_row.o_selected_row [name=empleado_id] input", run: "edit Carla Cambio" },
        { trigger: ".o-autocomplete--dropdown-item:contains('Carla Cambio')", run: "click" },
        { trigger: ".o_form_view [name=reparto_ids] .o_data_row.o_selected_row [name=porcentaje] input", run: "edit 50" },
        { trigger: ".o_form_button_save", run: "click" },
        { trigger: ".o_form_view [name=numero]" },
        { trigger: ".o_form_view:not(.o_form_dirty)" },
    ],
});
