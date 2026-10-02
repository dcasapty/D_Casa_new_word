/**
 * Token CSRF fresco en las páginas que sirvió la caché del borde (edge/src/tienda/paginas.ts).
 *
 * Esa página es la misma para todo visitante anónimo: el token CSRF que trae (en `odoo.csrf_token`
 * y en los `<input name="csrf_token">`) es de la sesión con la que el borde la pidió, no de la de
 * quien la ve. Antes de que se use, se pide uno de esta sesión a `/dcasa/borde/csrf`:
 *
 *   · al tocar o enfocar cualquier cosa dentro de un formulario (llega antes del clic de enviar,
 *     y sirve también a los formularios de Odoo que envían por JS con `odoo.csrf_token`);
 *   · y, como garantía, se detiene el envío de un formulario POST con token hasta tenerlo.
 *
 * Solo actúa si la página vino del borde: el Worker manda `Server-Timing: dcasa-borde`. Si el
 * navegador no expone Server-Timing, actúa igual (pedir un token de más no rompe nada). En las
 * páginas que dibuja Odoo para quien tiene sesión no hace nada.
 */
const RUTA = "/dcasa/borde/csrf";
const MARCA = "dcasa-borde";

function servidaPorElBorde() {
    try {
        const navegacion = performance.getEntriesByType("navigation")[0];
        if (navegacion && Array.isArray(navegacion.serverTiming)) {
            return navegacion.serverTiming.some((metrica) => metrica.name === MARCA);
        }
    } catch {
        // Sin Navigation Timing: se asume que sí.
    }
    return true;
}

let pedido = null;
let listo = false;

export function refrescarCsrf() {
    if (!pedido) {
        pedido = fetch(RUTA, {
            credentials: "same-origin",
            cache: "no-store",
            headers: { Accept: "application/json" },
        })
            .then((respuesta) => (respuesta.ok ? respuesta.json() : null))
            .then((datos) => {
                const token = datos && datos.csrf_token;
                if (token) {
                    if (window.odoo) {
                        window.odoo.csrf_token = token;
                    }
                    for (const campo of document.querySelectorAll('input[name="csrf_token"]')) {
                        campo.value = token;
                    }
                }
                listo = true;
                return token || null;
            })
            .catch(() => {
                pedido = null; // sin red: se reintenta en la próxima interacción
                return null;
            });
    }
    return pedido;
}

function dentroDeFormulario(evento) {
    const objetivo = evento.target;
    return objetivo instanceof Element && objetivo.closest("form");
}

if (typeof document !== "undefined" && servidaPorElBorde()) {
    for (const tipo of ["pointerdown", "touchstart", "focusin", "keydown"]) {
        document.addEventListener(
            tipo,
            (evento) => {
                if (!listo && dentroDeFormulario(evento)) {
                    refrescarCsrf();
                }
            },
            { capture: true, passive: true }
        );
    }
    document.addEventListener(
        "submit",
        (evento) => {
            const formulario = evento.target;
            if (
                listo ||
                !(formulario instanceof HTMLFormElement) ||
                (formulario.getAttribute("method") || "get").toLowerCase() !== "post" ||
                !formulario.querySelector('input[name="csrf_token"]')
            ) {
                return;
            }
            evento.preventDefault();
            evento.stopImmediatePropagation();
            const boton = evento.submitter;
            refrescarCsrf().then(() => {
                listo = true; // con o sin token nuevo: no volver a detenerlo
                try {
                    formulario.requestSubmit(boton || undefined);
                } catch {
                    formulario.submit(); // navegador viejo o botón que no es de este formulario
                }
            });
        },
        { capture: true }
    );
}
