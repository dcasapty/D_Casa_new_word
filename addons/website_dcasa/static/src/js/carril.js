/**
 * Carriles de la portada (v3, 2026-11-15): «Lo más buscado» y «Para dormir mejor» van en una sola fila que se
 * desliza. Esto suma lo que el carril solo no tiene:
 *   · las flechas (computadora): avanzan una «página» de tarjetas y se apagan en las orillas;
 *   · la línea de avance bajo el carril: cuánto se recorrió y que hay más.
 * Las dos nacen escondidas en la plantilla y solo aparecen si hay algo que deslizar. Sin JavaScript el carril se
 * desliza igual (con el dedo, la rueda o el teclado al pasar de una tarjeta a otra).
 */
import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";

const reducido = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;
let siguienteId = 0;

export class DcasaCarril extends Interaction {
    static selector = ".o_dcasa_rail";
    dynamicContent = {
        ".o_dcasa_carril_flecha": { "t-on-click": this.alFlecha },
        ".o_dcasa_rail_track": { "t-on-scroll.noUpdate": this.medir },
        _window: { "t-on-resize.noUpdate": this.medir },
    };

    start() {
        this.pista = this.el.querySelector(".o_dcasa_rail_track");
        this.flechas = this.el.querySelector(".o_dcasa_carril_flechas");
        this.avance = this.el.querySelector(".o_dcasa_carril_avance");
        if (!this.pista) {
            return;
        }
        // Las flechas dicen qué carril mueven (dos carriles en la misma página: cada uno con su id).
        if (!this.pista.id) {
            this.pista.id = `o_dcasa_carril_${++siguienteId}`;
        }
        for (const flecha of this.el.querySelectorAll(".o_dcasa_carril_flecha")) {
            flecha.setAttribute("aria-controls", this.pista.id);
        }
        this.medir();
        // Las fotos que llegan tarde cambian el ancho total: se vuelve a medir.
        if ("ResizeObserver" in window) {
            this.observador = new ResizeObserver(() => this.medir());
            this.observador.observe(this.pista);
            this.registerCleanup(() => this.observador.disconnect());
        }
        this.registerCleanup(() => {
            this.flechas?.setAttribute("hidden", "");
            this.avance?.setAttribute("hidden", "");
        });
    }

    /** Cuánto se ve, cuánto hay y dónde va: enciende o apaga flechas y línea. */
    medir() {
        const { scrollLeft, scrollWidth, clientWidth } = this.pista;
        const recorrido = scrollWidth - clientWidth;
        const hayMas = recorrido > 2;
        this.flechas?.toggleAttribute("hidden", !hayMas);
        this.avance?.toggleAttribute("hidden", !hayMas);
        if (!hayMas) {
            return;
        }
        const [atras, adelante] = this.el.querySelectorAll(".o_dcasa_carril_flecha");
        if (atras) {
            atras.disabled = scrollLeft <= 2;
        }
        if (adelante) {
            adelante.disabled = scrollLeft >= recorrido - 2;
        }
        if (this.avance) {
            this.avance.style.setProperty("--avance-ancho", (clientWidth / scrollWidth).toFixed(4));
            this.avance.style.setProperty("--avance", Math.min(1, Math.max(0, scrollLeft / recorrido)).toFixed(4));
        }
    }

    /** Una «página» de tarjetas: lo que se ve, menos un poco para que la última asome otra vez. */
    alFlecha(ev) {
        const sentido = Number(ev.currentTarget.dataset.carril) || 1;
        const tarjeta = this.pista.querySelector(".o_dcasa_rail_item");
        const paso = tarjeta ? tarjeta.getBoundingClientRect().width : 0;
        const pagina = Math.max(paso, this.pista.clientWidth - paso / 2);
        this.pista.scrollBy({ left: sentido * pagina, behavior: reducido() ? "auto" : "smooth" });
    }
}

registry.category("public.interactions").add("website_dcasa.carril", DcasaCarril);
