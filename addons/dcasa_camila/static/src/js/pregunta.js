/**
 * El cuadro de las novedades en la venta (Camila etapa 1b) no se cierra con Escape: hay que contestarlo (la X tampoco se
 * muestra, camila.scss). Así no se pierde lo que seguía, como «Imprimir documentos» después de pagar. La venta o el pago
 * ya quedaron hechos antes de que salga.
 */
import { Dialog } from "@web/core/dialog/dialog";
import { patch } from "@web/core/utils/patch";

patch(Dialog.prototype, {
    onEscape() {
        if (this.modalRef?.el?.querySelector(".o_dcasa_camila_pregunta")) {
            return;
        }
        return super.onEscape(...arguments);
    },
});
