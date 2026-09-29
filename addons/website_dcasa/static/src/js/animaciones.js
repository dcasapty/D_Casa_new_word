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
    // ¿La píldora está encima de la foto oscura del hero? Entonces vidrio claro y texto blanco.
    const hero = document.querySelector(".o_dcasa_hero");
    const sobreFoto = () => {
        if (!hero) {
            return false;
        }
        const piso = header.getBoundingClientRect().bottom;
        const foto = hero.getBoundingClientRect();
        return foto.top < piso && foto.bottom > piso;
    };
    let compacta = false;
    const revisar = () => {
        raiz.classList.toggle("o_dcasa_nav_sobre_foto", sobreFoto());
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

// Vidrio líquido: refracción donde el navegador la soporta y la gota que sigue al puntero.
function vidrioLiquido() {
    const chromium = navigator.userAgentData?.brands?.some((b) => b.brand === "Chromium");
    if (chromium && window.CSS?.supports?.("backdrop-filter", "url(#a)")) {
        raiz.classList.add("o_dcasa_refraccion");
    }
    if (reducido) {
        document.querySelectorAll(".o_dcasa_filtros animate").forEach((a) => a.remove());
    }
    const menu = document.querySelector("header#top #top_menu");
    if (!menu) {
        return;
    }
    const gota = document.createElement("span");
    gota.className = "o_dcasa_gota";
    gota.setAttribute("aria-hidden", "true");
    menu.prepend(gota);
    const moverA = (enlace) => {
        if (!enlace) {
            gota.classList.remove("is-visible");
            return;
        }
        const caja = menu.getBoundingClientRect();
        const r = enlace.getBoundingClientRect();
        gota.style.setProperty("--gota-x", `${r.left - caja.left}px`);
        gota.style.setProperty("--gota-ancho", `${r.width}px`);
        // Un pellizco al arrancar: la gota se estira y vuelve, como un líquido.
        gota.style.setProperty("--gota-estirar", "0.82");
        setTimeout(() => gota.style.setProperty("--gota-estirar", "1"), 180);
        gota.classList.add("is-visible");
    };
    // «Visítanos» es un ancla de la portada: Odoo lo marca activo en «/», pero no es una página.
    menu.querySelectorAll(".nav-link[href='/#visitanos']").forEach((a) => {
        a.classList.remove("active");
        a.removeAttribute("aria-current");
    });
    const activo = () => menu.querySelector(".nav-link.active");
    menu.querySelectorAll(".nav-link").forEach((enlace) => {
        enlace.addEventListener("mouseenter", () => moverA(enlace));
        enlace.addEventListener("focus", () => moverA(enlace));
    });
    menu.addEventListener("mouseleave", () => moverA(activo()));
    window.addEventListener("resize", () => moverA(activo()), { passive: true });
    // Tras las fuentes (el ancho de los enlaces cambia al cargar Oswald).
    (document.fonts?.ready || Promise.resolve()).then(() => moverA(activo()));
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
        iniciar();
        cabecera();
        vidrioLiquido();
    });
} else {
    iniciar();
    cabecera();
    vidrioLiquido();
}
