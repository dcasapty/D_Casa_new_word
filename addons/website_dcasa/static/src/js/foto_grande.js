/**
 * La foto de la ficha en grande, también con el dedo (lote 1 de la web, aprobado por la dueña el 2026-11-13).
 *
 * El visor es el de Odoo («Zoom al hacer clic», website_sale): se abre al tocar la foto, se cambia de foto con las
 * flechas o las miniaturas y se acerca con la rueda del ratón o tocando la foto. Aquí se le suma:
 *
 *   · Un botón con la lupa sobre la foto (views/buscador_templates.xml): dice que la foto se puede ver en grande y la
 *     abre (la que se está mirando del carrusel).
 *   · En el visor, con el dedo: dos dedos acercan y alejan (hasta 4 veces) y, ya acercada, un dedo mueve la foto. Un
 *     toque acerca bastante más que el de Odoo (pensado para el ratón), y otro toque la deja como estaba.
 *
 * Nada de esto cambia el visor en la computadora.
 */
import { onMounted, onWillUnmount } from "@odoo/owl";
import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";
import { patch } from "@web/core/utils/patch";
import { ProductImageViewer } from "@website_sale/js/components/website_sale_image_viewer";

export const ESCALA_MAXIMA = 4;
/** Un toque en el visor lleva la foto a 2,5 veces (Odoo: 1,3, pensado para el ratón). */
export const PASO_TOQUE = 1.5;
const VENTANA_TOQUE_MS = 700;

const distancia = (a, b) => Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);

/** El botón de la lupa sobre la foto: abre el visor con la foto que se está mirando. */
export class DcasaVerEnGrande extends Interaction {
    static selector = ".o_dcasa_ver_grande";
    dynamicContent = {
        _root: { "t-on-click": this.abrir },
    };

    abrir() {
        const carrusel = this.el.closest("#o-carousel-product");
        const foto = carrusel?.querySelector(".carousel-item.active .product_detail_img")
            || carrusel?.querySelector(".product_detail_img");
        foto?.click();
    }
}

registry.category("public.interactions").add("website_dcasa.ver_en_grande", DcasaVerEnGrande);

patch(ProductImageViewer.prototype, {
    setup() {
        super.setup();
        this.dcasaGesto = null;
        this.dcasaToque = 0;
        const manejadores = {
            touchstart: (ev) => this.dcasaAlTocar(ev),
            touchmove: (ev) => this.dcasaAlMover(ev),
            touchend: (ev) => this.dcasaAlSoltar(ev),
            touchcancel: (ev) => this.dcasaAlSoltar(ev),
        };
        let zona = null;
        onMounted(() => {
            zona = this.imageContainerRef.el?.closest(".o_wsale_image_viewer_image");
            for (const [evento, manejador] of Object.entries(manejadores)) {
                zona?.addEventListener(evento, manejador, { passive: evento === "touchend" || evento === "touchcancel" });
            }
        });
        onWillUnmount(() => {
            for (const [evento, manejador] of Object.entries(manejadores)) {
                zona?.removeEventListener(evento, manejador);
            }
        });
    },

    dcasaAlTocar(ev) {
        if (ev.touches.length === 2) {
            ev.preventDefault();
            this.dcasaGesto = {
                tipo: "pellizco",
                distancia: distancia(ev.touches[0], ev.touches[1]) || 1,
                escala: this.state.imageScale,
            };
        } else if (ev.touches.length === 1) {
            const dedo = ev.touches[0];
            this.dcasaGesto = {
                tipo: this.state.imageScale > 1 ? "mover" : "toque",
                x: dedo.clientX - this.imageTranslate.x,
                y: dedo.clientY - this.imageTranslate.y,
                inicioX: dedo.clientX,
                inicioY: dedo.clientY,
                movio: false,
            };
        }
    },

    dcasaAlMover(ev) {
        const gesto = this.dcasaGesto;
        if (!gesto) {
            return;
        }
        if (gesto.tipo === "pellizco" && ev.touches.length === 2) {
            ev.preventDefault();
            const escala = (gesto.escala * distancia(ev.touches[0], ev.touches[1])) / gesto.distancia;
            this.state.imageScale = Math.min(ESCALA_MAXIMA, Math.max(1, escala));
        } else if (ev.touches.length === 1) {
            const dedo = ev.touches[0];
            gesto.movio ||= Math.hypot(dedo.clientX - gesto.inicioX, dedo.clientY - gesto.inicioY) > 8;
            if (gesto.tipo === "mover") {
                ev.preventDefault();
                this.imageTranslate.x = dedo.clientX - gesto.x;
                this.imageTranslate.y = dedo.clientY - gesto.y;
                this.updateImage();
            }
        }
    },

    dcasaAlSoltar(ev) {
        if (ev.touches.length) {
            return;
        }
        const gesto = this.dcasaGesto;
        // Un toque sin mover: el «clic» que sigue lo trata Odoo (acercar o volver); que acerque como para el dedo.
        this.dcasaToque = gesto && gesto.tipo !== "pellizco" && !gesto.movio ? Date.now() : 0;
        if (this.state.imageScale <= 1) {
            this.imageTranslate = { x: 0, y: 0 };
            this.updateImage();
        }
        this.dcasaGesto = null;
    },

    zoomIn(step = undefined) {
        const delDedo = this.dcasaToque && Date.now() - this.dcasaToque < VENTANA_TOQUE_MS;
        this.dcasaToque = 0;
        super.zoomIn(delDedo ? PASO_TOQUE : step);
        this.state.imageScale = Math.min(ESCALA_MAXIMA, this.state.imageScale);
    },
});
