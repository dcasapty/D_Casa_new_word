/**
 * Ficha de la tienda: la etiqueta «Disponible», «Quedan pocas» o «Agotado» de la medida elegida.
 *
 * Odoo pide la información de la combinación al abrir la ficha y cada vez que se cambia de medida o color; el servidor
 * manda la etiqueta ya decidida (dcasa_catalogo/models/product.py, la regla de dcasa_base) y aquí solo se pinta. Así
 * una ficha guardada en el borde muestra la disponibilidad de ahora. Nunca llega ni se muestra el número.
 */
import { patch } from "@web/core/utils/patch";
import { WebsiteSale } from "@website_sale/interactions/website_sale";

export function pintarDisponibilidad(contenedor, combinacion) {
    const etiqueta = contenedor?.querySelector(".o_dcasa_disponibilidad");
    if (!etiqueta || !combinacion?.dcasa_disponibilidad) {
        return;
    }
    etiqueta.dataset.estado = combinacion.dcasa_disponibilidad;
    etiqueta.querySelector(".o_dcasa_disponibilidad_texto").textContent = combinacion.dcasa_disponibilidad_texto;
}

patch(WebsiteSale.prototype, {
    _onChangeCombination(ev, parent, combination) {
        super._onChangeCombination(...arguments);
        pintarDisponibilidad(parent, combination);
    },
});
