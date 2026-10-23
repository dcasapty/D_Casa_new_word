/**
 * Escáner: tocar la foto del producto escaneado la abre en grande (y, a quien puede editar el producto, le deja
 * cambiarla ahí mismo). Al cerrar, si cambió, la tarjeta pide la foto nueva.
 */
import { patch } from "@web/core/utils/patch";
import { DcasaEscaner } from "@dcasa_barras/js/escaner";
import { abrirFotos } from "./fotos_dialogo";

patch(DcasaEscaner.prototype, {
    verFotosDeLaFicha() {
        const ficha = this.state.ficha;
        if (!ficha || !ficha.plantilla_id) {
            return;
        }
        abrirFotos(this.dialog, {
            plantillaId: ficha.plantilla_id,
            alCambiar: () => {
                ficha.imagen = `${ficha.imagen.split("?")[0]}?v=${Date.now()}`;
            },
        });
    },
});
