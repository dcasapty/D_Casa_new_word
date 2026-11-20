/**
 * Portada (2026-11-16): el hero en carrusel y la sección «de cine» (models/portada.py, views/homepage_templates.xml).
 *
 *   · DcasaVitrina  el FONDO del hero: las fotos se funden unas en otras, en orden al azar, cada --vitrina-tiempo.
 *                   El visitante no maneja nada (no hay flechas, barras, pausa ni deslizar): es un fondo, no un
 *                   carrusel que se recorre. El zoom lento es del CSS y no para nunca; con movimiento reducido no
 *                   cambia de foto. Sin JavaScript se ve la primera, quieta.
 *   · DcasaCine     las cintas de fotos corren solas con CSS; aquí solo el botón de pausa (WCAG 2.2.2) y la pausa
 *                   mientras el dedo está apoyado en ellas.
 *
 * Como las demás Interactions del sitio, no corren en el editor y lo que agregan lo quitan al destruirse.
 */
import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";

const reducido = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/**
 * El fondo del hero (la dueña, 2026-11-17): las fotos se funden unas en otras, en orden al azar, sin que el visitante
 * maneje nada. No hay flechas, ni barras, ni pausa, ni deslizar: es un fondo, no un carrusel que se recorre.
 * El zoom lento lo hace el CSS y no para nunca; aquí solo se decide cuándo cambiar de foto.
 * Con movimiento reducido no cambia nunca: se queda la primera.
 */
export class DcasaVitrina extends Interaction {
    static selector = ".o_dcasa_vitrina";

    setup() {
        this.fotos = [...this.el.querySelectorAll(".o_dcasa_vitrina_foto")];
        this.total = this.fotos.length;
        this.actual = Math.max(0, this.fotos.findIndex((foto) => foto.classList.contains("is-activa")));
        // Orden al azar, empezando por la que ya se está viendo (es la que el navegador precargó: el LCP no cambia).
        this.orden = barajar(this.fotos.map((_, i) => i).filter((i) => i !== this.actual));
        this.paso = 0;
        this.temporizador = null;
    }

    start() {
        const raiz = document.documentElement;
        // Mientras el hero se ve, el botón flotante de WhatsApp espera fuera (el texto ya trae el suyo).
        this.mirador = new IntersectionObserver((entradas) => {
            for (const entrada of entradas) {
                raiz.classList.toggle("o_dcasa_vitrina_a_la_vista", entrada.isIntersecting);
            }
        }, { threshold: 0.25 });
        this.mirador.observe(this.el);
        this.registerCleanup(() => {
            this.mirador.disconnect();
            raiz.classList.remove("o_dcasa_vitrina_a_la_vista");
        });
        // La limpieza se registra UNA vez (no con cada cambio de foto: a 2 s por foto serían unas 1800 por hora).
        this.registerCleanup(() => this.parar());
        if (this.total > 1 && !reducido()) {
            this.programar();
        }
    }

    destroy() {
        this.parar();
    }

    parar() {
        if (this.temporizador) {
            this.services.timer?.clearTimeout?.(this.temporizador);
            clearTimeout(this.temporizador);
            this.temporizador = null;
        }
    }

    programar() {
        this.parar();
        const ms = tiempoDeLaVitrina(this.el);
        this.temporizador = setTimeout(() => this.siguiente(), ms);
    }

    siguiente() {
        if (!this.orden.length) {
            // Otra vuelta, barajada de nuevo y sin repetir la que se está viendo de primera.
            this.orden = barajar(this.fotos.map((_, i) => i).filter((i) => i !== this.actual));
        }
        const proxima = this.orden.shift();
        this.fotos[this.actual]?.classList.remove("is-activa");
        this.fotos[proxima]?.classList.add("is-activa");
        this.actual = proxima;
        this.programar();
    }
}

/** Una copia barajada (Fisher-Yates). */
export function barajar(lista) {
    const copia = [...lista];
    for (let i = copia.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [copia[i], copia[j]] = [copia[j], copia[i]];
    }
    return copia;
}

/**
 * Lo que dura cada foto, en milisegundos, leído de `--vitrina-tiempo`: la plantilla lo escribe en el hero con los
 * segundos que Gerencia eligió en el panel (3 de fábrica; website_dcasa/models/portada.py) y las pruebas lo cambian
 * para acortarlo. Sin valor legible, los 3 segundos de fábrica.
 */
export function tiempoDeLaVitrina(el) {
    const valor = getComputedStyle(el).getPropertyValue("--vitrina-tiempo").trim();
    const numero = parseFloat(valor);
    if (!numero || Number.isNaN(numero)) {
        return 3000;
    }
    return valor.endsWith("ms") ? numero : numero * 1000;
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
