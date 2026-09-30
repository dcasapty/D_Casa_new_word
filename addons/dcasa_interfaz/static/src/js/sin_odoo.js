/**
 * Odoo sin distracciones para D'CASA.
 *
 *  · Nada de «Enterprise» ni ventanas de compra: esas opciones dicen «En desarrollo»
 *    (las construimos nosotros) y no hacen nada al tocarlas.
 *  · Listas vacías sin datos de ejemplo borrosos, videos ni «Pruebe con un ejemplo»:
 *    un mensaje corto y claro.
 *  · Menú de usuario sin enlaces a odoo.com; ventanas con el nombre D'CASA.
 */
import { patch } from "@web/core/utils/patch";
import { registry } from "@web/core/registry";
import { Dialog } from "@web/core/dialog/dialog";
import { View } from "@web/views/view";
import { ActionHelper } from "@web/views/action_helper";
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

const listaVacia = {
    get showDefaultHelper() {
        return true;
    },
    get title() {
        return "Aquí todavía no hay nada";
    },
    get description() {
        return "Toca «Nuevo» para crear el primero, o revisa los filtros de la búsqueda.";
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
