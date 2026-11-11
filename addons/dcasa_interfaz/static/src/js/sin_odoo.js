/**
 * Odoo sin distracciones para D'CASA.
 *
 *  · Nada de «Enterprise» ni ventanas de compra: esas opciones dicen «En desarrollo»
 *    (las construimos nosotros) y no hacen nada al tocarlas.
 *  · Listas vacías sin datos de ejemplo borrosos, videos ni «Pruebe con un ejemplo»:
 *    un mensaje corto y claro, que solo invita a tocar «Nuevo» donde ese botón existe,
 *    y que también sale en las listas cuya acción no trae texto de ayuda (antes quedaban
 *    con cuatro renglones en blanco).
 *  · Menú de usuario sin enlaces a odoo.com; ventanas con el nombre D'CASA.
 */
import { useSubEnv } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { registry } from "@web/core/registry";
import { Dialog } from "@web/core/dialog/dialog";
import { View } from "@web/views/view";
import { ActionHelper } from "@web/views/action_helper";
import { ListRenderer } from "@web/views/list/list_renderer";
import { KanbanRenderer } from "@web/views/kanban/kanban_renderer";
import { UpgradeBooleanField } from "@web/webclient/settings_form_view/fields/upgrade_boolean_field";
import { SaleActionHelper } from "@sale/js/sale_action_helper/sale_action_helper";
import { StockActionHelper } from "@stock/views/stock_empty_list_help";

patch(UpgradeBooleanField.prototype, {
    async onChange() {
        this.props.record.update({ [this.props.name]: false });
        this.env.services.notification.add(
            "Esta función la estamos desarrollando a la medida de D'CASA.",
            { title: "En desarrollo", type: "info" }
        );
    },
});

patch(View.prototype, {
    async loadView(props) {
        await super.loadView(props);
        // Sin registros de ejemplo borrosos detrás del mensaje de lista vacía.
        this.componentProps.useSampleModel = false;
    },
});

// ¿La pantalla tiene botón «Nuevo»? La lista y las tarjetas se lo dicen al mensaje de «no hay nada» (que es su hijo).
// Las gráficas, tablas dinámicas y demás vistas nunca lo tienen: ahí el mensaje no lo menciona.
patch(ListRenderer.prototype, {
    setup() {
        super.setup();
        useSubEnv({ dcasaPuedeCrear: () => Boolean(this.props.activeActions?.create) });
    },
    get showNoContentHelper() {
        // Odoo solo avisa «no hay nada» si la acción trae un texto de ayuda; sin él, la lista quedaba con cuatro
        // renglones en blanco. Las listas de dentro de un formulario (líneas de la cotización) siguen como estaban.
        const { model } = this.props.list;
        return super.showNoContentHelper || (!this.isX2Many && !model.useSampleModel && !model.hasData());
    },
});
patch(KanbanRenderer.prototype, {
    setup() {
        super.setup();
        useSubEnv({ dcasaPuedeCrear: () => Boolean(this.props.archInfo?.activeActions?.create) });
    },
});

export const TEXTO_VACIO_CON_NUEVO = "Toca «Nuevo» para crear el primero, o revisa los filtros de la búsqueda.";
export const TEXTO_VACIO_SIN_NUEVO = "Cuando haya algo, sale aquí. Si esperabas verlo, revisa los filtros de la búsqueda.";

const listaVacia = {
    get showDefaultHelper() {
        // La ayuda propia de D'CASA (su párrafo lleva la clase `o_dcasa_ayuda`) sí se muestra: dice qué hacer en esa
        // lista. Todas las demás (videos, «Pruebe con un ejemplo») se cambian por el mensaje sobrio de abajo.
        return !(this.props.noContentHelp || "").includes("o_dcasa_ayuda");
    },
    get title() {
        return "Aquí todavía no hay nada";
    },
    get description() {
        return this.env.dcasaPuedeCrear?.() ? TEXTO_VACIO_CON_NUEVO : TEXTO_VACIO_SIN_NUEVO;
    },
};
patch(ActionHelper.prototype, listaVacia);
// Ventas e Inventario traen su propia ayuda (video, «Pruebe con un ejemplo»): la misma sobria.
for (const Ayuda of [SaleActionHelper, StockActionHelper]) {
    Ayuda.template = "web.ActionHelper";
    patch(Ayuda.prototype, listaVacia);
}

Dialog.defaultProps = { ...Dialog.defaultProps, title: "D'CASA" };

const menuUsuario = registry.category("user_menuitems");
for (const clave of ["documentation", "support", "shortcuts", "odoo_account"]) {
    if (menuUsuario.contains(clave)) {
        menuUsuario.remove(clave);
    }
}
