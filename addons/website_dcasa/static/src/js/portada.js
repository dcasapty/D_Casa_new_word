/**
 * Portada (2026-11-16): el hero en carrusel y la sección «de cine» (models/portada.py, views/homepage_templates.xml).
 *
 *   · DcasaVitrina  el carrusel del hero. Enciende las barras, la pausa y las flechas (nacen escondidas: sin
 *                   JavaScript se ve la primera diapositiva). El avance automático lo marca la barra activa: una
 *                   animación CSS que se llena en --vitrina-tiempo; al terminar, pasa a la siguiente. Así, pausar es
 *                   solo pausar esa animación (puntero encima, foco dentro o el botón de pausa) y con movimiento
 *                   reducido no avanza nunca (la barra no se anima). Con el dedo, deslizar la foto cambia de producto.
 *   · DcasaCine     las cintas de fotos corren solas con CSS; aquí solo el botón de pausa (WCAG 2.2.2) y la pausa
 *                   mientras el dedo está apoyado en ellas.
 *
 * Como las demás Interactions del sitio, no corren en el editor y lo que agregan lo quitan al destruirse.
 */
import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";

const reducido = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Distancia mínima (px) de un deslizamiento horizontal para cambiar de diapositiva. */
export const DESLIZAR_MINIMO = 40;

/**
 * Índice de la diapositiva que sigue (o la anterior con paso -1), dando la vuelta en las orillas.
 * @param {number} actual
 * @param {number} paso
 * @param {number} total
 */
export function vecina(actual, paso, total) {
    return total ? (((actual + paso) % total) + total) % total : 0;
}

export class DcasaVitrina extends Interaction {
    static selector = ".o_dcasa_vitrina";
    dynamicContent = {
        ".o_dcasa_vitrina_barra": { "t-on-click": this.alBarra },
        ".o_dcasa_vitrina_boton[data-paso]": { "t-on-click": this.alPaso },
        ".o_dcasa_vitrina_pausa": {
            "t-on-click": this.alternarPausa,
            "t-att-aria-pressed": () => String(this.pausada),
            "t-att-aria-label": () => (this.pausada ? "Reanudar el carrusel" : "Pausar el carrusel"),
        },
        ".o_dcasa_vitrina_barras": { "t-on-animationend.noUpdate": this.alLlenarBarra },
        _root: {
            "t-att-class": () => ({
                "is-viva": this.viva,
                "is-quieta": this.viva && this.quieta,
                "is-pausada": this.pausada,
                "is-encima": this.encima,
                "is-con-foco": this.conFoco,
            }),
        },
    };

    setup() {
        this.fotos = [...this.el.querySelectorAll(".o_dcasa_vitrina_foto")];
        this.textos = [...this.el.querySelectorAll(".o_dcasa_vitrina_texto")];
        this.barras = [...this.el.querySelectorAll(".o_dcasa_vitrina_barra")];
        this.vivo = this.el.querySelector(".o_dcasa_vitrina_textos");
        this.total = this.fotos.length;
        this.actual = Math.max(0, this.fotos.findIndex((foto) => foto.classList.contains("is-activa")));
        // Las clases del contenedor se aplican antes de start(): se decide aquí.
        this.viva = this.total > 1;
        this.quieta = reducido();
        this.pausada = false;
        this.encima = false;
        this.conFoco = false;
    }

    start() {
        if (!this.viva) {
            return;
        }
        const controles = this.el.querySelectorAll(".o_dcasa_vitrina_barras, .o_dcasa_vitrina_botones");
        controles.forEach((el) => el.removeAttribute("hidden"));
        this.registerCleanup(() => controles.forEach((el) => el.setAttribute("hidden", "")));

        // Pausa mientras el ratón está encima o el foco adentro (el dedo no: un toque no es «estar encima»).
        this.addListener(this.el, "pointerenter", (ev) => {
            if (ev.pointerType === "mouse") {
                this.encima = true;
            }
        });
        this.addListener(this.el, "pointerleave", () => {
            this.encima = false;
        });
        this.addListener(this.el, "focusin", () => {
            this.conFoco = true;
        });
        this.addListener(this.el, "focusout", (ev) => {
            if (!this.el.contains(ev.relatedTarget)) {
                this.conFoco = false;
            }
        });

        // Deslizar la foto con el dedo. Un deslizamiento no es un clic: el enlace de la foto no se abre.
        const marco = this.el.querySelector(".o_dcasa_vitrina_fotos");
        this.addListener(marco, "pointerdown", (ev) => {
            this.inicio = ev.pointerType === "mouse" ? null : { x: ev.clientX, y: ev.clientY };
            this.deslizo = false;
        });
        this.addListener(marco, "pointerup", (ev) => {
            if (!this.inicio) {
                return;
            }
            const dx = ev.clientX - this.inicio.x;
            const dy = ev.clientY - this.inicio.y;
            this.inicio = null;
            if (Math.abs(dx) >= DESLIZAR_MINIMO && Math.abs(dx) > Math.abs(dy)) {
                this.deslizo = true;
                this.ir(vecina(this.actual, dx < 0 ? 1 : -1, this.total), true);
            }
        });
        this.addListener(marco, "pointercancel", () => {
            this.inicio = null;
        });
        this.addListener(
            marco,
            "click",
            (ev) => {
                if (this.deslizo) {
                    ev.preventDefault();
                    this.deslizo = false;
                }
            },
            { capture: true }
        );

        this.registerCleanup(() => {
            this.vivo?.setAttribute("aria-live", "off");
        });
    }

    alBarra(ev) {
        this.ir(Number(ev.currentTarget.dataset.ir) || 0, true);
    }

    alPaso(ev) {
        this.ir(vecina(this.actual, Number(ev.currentTarget.dataset.paso) || 1, this.total), true);
    }

    alternarPausa() {
        this.pausada = !this.pausada;
    }

    /** La barra activa terminó de llenarse: toca la siguiente (solo si de verdad corría el avance). */
    alLlenarBarra(ev) {
        const barra = this.barras[this.actual];
        if (!this.viva || this.quieta || !barra || !barra.contains(ev.target)) {
            return;
        }
        this.ir(vecina(this.actual, 1, this.total), false);
    }

    /**
     * Muestra la diapositiva `indice`. `porQuien`: si la cambió quien visita, el lector de pantalla anuncia la nueva
     * (aria-live «polite»); mientras avanza sola, no interrumpe («off»).
     */
    ir(indice, porQuien) {
        if (indice === this.actual || !this.fotos[indice]) {
            return;
        }
        for (const lista of [this.fotos, this.textos]) {
            lista[this.actual]?.classList.remove("is-activa");
            lista[indice]?.classList.add("is-activa");
        }
        this.barras[this.actual]?.removeAttribute("aria-current");
        this.barras[indice]?.setAttribute("aria-current", "true");
        this.actual = indice;
        this.vivo?.setAttribute("aria-live", porQuien ? "polite" : "off");
        // La que sigue se pide ya: cuando le toque, está lista.
        const proxima = this.fotos[vecina(indice, 1, this.total)]?.querySelector("img");
        if (proxima && proxima.loading === "lazy") {
            proxima.loading = "eager";
        }
    }
}

export class DcasaCine extends Interaction {
    static selector = ".o_dcasa_cine";
    dynamicContent = {
        ".o_dcasa_cine_pausa": {
            "t-on-click": this.alternar,
            "t-att-aria-pressed": () => String(this.pausada),
        },
        ".o_dcasa_cine_pausa span": {
            "t-out": () => (this.pausada ? "Mover las fotos" : "Pausar las fotos"),
        },
        _root: { "t-att-class": () => ({ "is-pausada": this.pausada, "is-tocada": this.tocada }) },
    };

    setup() {
        this.pausada = false;
        this.tocada = false;
    }

    start() {
        if (reducido()) {
            return;
        }
        const boton = this.el.querySelector(".o_dcasa_cine_pausa");
        boton?.removeAttribute("hidden");
        this.registerCleanup(() => boton?.setAttribute("hidden", ""));
        // Con el dedo apoyado en las fotos, se quedan quietas (y siguen un momento después de soltar).
        const cintas = this.el.querySelector(".o_dcasa_cine_cintas");
        this.addListener(cintas, "pointerdown", (ev) => {
            if (ev.pointerType !== "mouse") {
                clearTimeout(this.soltar);
                this.tocada = true;
            }
        });
        const alSoltar = () => {
            clearTimeout(this.soltar);
            this.soltar = setTimeout(() => {
                this.tocada = false;
                this.updateContent();
            }, 1500);
        };
        this.addListener(cintas, "pointerup", alSoltar);
        this.addListener(cintas, "pointercancel", alSoltar);
        this.registerCleanup(() => clearTimeout(this.soltar));
    }

    alternar() {
        this.pausada = !this.pausada;
    }
}

const interacciones = registry.category("public.interactions");
interacciones.add("website_dcasa.vitrina", DcasaVitrina);
interacciones.add("website_dcasa.cine", DcasaCine);
