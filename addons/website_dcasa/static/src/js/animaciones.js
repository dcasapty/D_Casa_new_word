/**
 * Animaciones del sitio D'CASA (mismo sistema que BYS y Safetory).
 *
 * El CSS (bloque «Animaciones» de dcasa.scss) define el estado inicial y las
 * variantes; aquí solo se decide CUÁNDO se revela cada cosa:
 *   · [data-anim]           un bloque que entra al verse (izquierda, derecha, escala);
 *   · [data-anim-cascada]   un contenedor cuyos hijos entran escalonados;
 *   · [data-titular]        un titular que entra palabra a palabra.
 * Lo que está sobre el pliegue (el hero) usa [data-anim-entrada], que es CSS
 * puro y no espera a este archivo.
 *
 * NO SE ANIMA DENTRO DEL EDITOR. El constructor de Odoo carga la página en un
 * iframe: ahí no se añade la clase `o_dcasa_anim`, así que nada se esconde y
 * el titular no se trocea (el editor guardaría los trozos). Tampoco con
 * `prefers-reduced-motion`.
 *
 * Cada elemento se revela una vez y se deja de mirar. Con IntersectionObserver,
 * no escuchando el scroll: el navegador ya sabe qué está a la vista.
 */
const raiz = document.documentElement;
const enEditor = window.self !== window.top || document.body?.classList.contains("editor_enable");
const reducido = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function trocearTitular(titular) {
    if (titular.dataset.troceado) {
        return;
    }
    titular.dataset.troceado = "1";
    // El texto entero sigue disponible para lectores de pantalla.
    titular.setAttribute("aria-label", titular.textContent.trim().replace(/\s+/g, " "));
    const palabras = titular.textContent.trim().split(/\s+/);
    titular.textContent = "";
    palabras.forEach((palabra, i) => {
        const caja = document.createElement("span");
        caja.className = "o_dcasa_palabra";
        caja.setAttribute("aria-hidden", "true");
        const dentro = document.createElement("span");
        dentro.textContent = palabra;
        dentro.style.setProperty("--i", i);
        caja.appendChild(dentro);
        titular.appendChild(caja);
        if (i < palabras.length - 1) {
            titular.appendChild(document.createTextNode(" "));
        }
    });
}

function iniciar() {
    if (enEditor || reducido || !("IntersectionObserver" in window)) {
        return;
    }
    const elementos = document.querySelectorAll("[data-anim], [data-anim-cascada], [data-titular]");
    if (!elementos.length) {
        return;
    }
    // Lo que ya está a la vista al cargar no se esconde para volver a enseñarlo.
    const alto = window.innerHeight;
    const observador = new IntersectionObserver(
        (entradas) => {
            for (const entrada of entradas) {
                if (entrada.isIntersecting) {
                    entrada.target.classList.add("anim-dentro");
                    observador.unobserve(entrada.target);
                }
            }
        },
        { rootMargin: "0px 0px -10% 0px", threshold: 0 }
    );
    for (const el of elementos) {
        if (el.getBoundingClientRect().top < alto * 0.9) {
            el.classList.add("anim-dentro");
            continue;
        }
        if (el.hasAttribute("data-titular")) {
            trocearTitular(el);
        }
        observador.observe(el);
    }
    raiz.classList.add("o_dcasa_anim");
}

// Cabecera de vidrio: se compacta al bajar (con histéresis para no parpadear en el umbral).
function cabecera() {
    const header = document.querySelector("header#top");
    if (!header) {
        return;
    }
    // El hero se mete debajo de la cabecera (el vidrio flota sobre la foto): necesita su alto.
    const medir = () => {
        if (!header.classList.contains("o_header_affixed")) {
            raiz.style.setProperty("--dcasa-header-h", `${header.offsetHeight}px`);
        }
    };
    medir();
    window.addEventListener("resize", medir, { passive: true });
    let compacta = false;
    const revisar = () => {
        const y = window.scrollY;
        if (!compacta && y > 40) {
            compacta = true;
            raiz.classList.add("o_dcasa_scrolled");
        } else if (compacta && y < 12) {
            compacta = false;
            raiz.classList.remove("o_dcasa_scrolled");
        }
    };
    window.addEventListener("scroll", revisar, { passive: true });
    revisar();
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
        iniciar();
        cabecera();
    });
} else {
    iniciar();
    cabecera();
}
