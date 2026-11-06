/**
 * El tablero de Marketing y Camila (etapa 2, pedido de la dueña): «Crear campaña con estos» en cada sección (más stock,
 * más vendidos, mayor movimiento, más quietos) abre Camila con un borrador nuevo armado con esos productos. El
 * servidor solo deja los que se pueden ofrecer (en tienda, con foto y publicados) y la IA escribe el texto según el
 * tema; nunca envía.
 */
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { DcasaMarketing } from "@dcasa_marketing/js/marketing";
import { mensajeDeError } from "@dcasa_conversaciones/js/utilidades";

patch(DcasaMarketing.prototype, {
    setup() {
        super.setup(...arguments);
        this.avisosCamila = useService("notification");
    },

    async crearCampanaCamila(tema, filas) {
        const productos = (filas || []).map((fila) => fila.id);
        if (!productos.length) {
            return;
        }
        try {
            const panel = await this.orm.call("dcasa.camila", "nueva", [{ tema, productos }]);
            await this.action.doAction({
                type: "ir.actions.client",
                tag: "dcasa_camila.panel",
                name: "Camila",
                params: { campana_id: panel.campana && panel.campana.id },
            });
        } catch (error) {
            this.avisosCamila.add(mensajeDeError(error), { type: "danger" });
        }
    },
});
