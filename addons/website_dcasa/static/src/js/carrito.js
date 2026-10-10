/**
 * «Cargando…» del sitio: que se vea que el toque se recibió y que no se pueda repetir mientras tanto
 * (pedido de la dueña: al tocar «Agregar al carrito» no pasaba nada visible y se podía tocar varias veces).
 *
 * Medido en Chrome: «Agregar al carrito» llama al servidor (0,7 s en una máquina local; más en el servidor),
 * el aviso de «agregado» llega al final y, mientras tanto, el botón seguía activo: cada toque era una unidad
 * más en el carrito.
 *
 *   · Agregar al carrito (ficha y tarjetas de la tienda: el JS de Odoo): el botón muestra el cargador de
 *     Odoo desde el primer toque, queda bloqueado hasta que el servidor contesta y los toques repetidos no
 *     hacen nada. Un lector de pantalla oye «Agregando al carrito…».
 *   · Agregar de las tarjetas de la portada (un formulario normal, sin JavaScript de Odoo): igual, y si la
 *     persona vuelve atrás desde el carrito el botón regresa a su estado (no queda girando).
 *   · Barra fina arriba mientras se abre otra página o se envía un formulario (la tienda puede tardar un
 *     momento en despertar): nadie se queda mirando una pantalla quieta sin saber si pasó algo.
 *
 * Todo se deshace al destruirse la interacción y el editor del sitio no lo carga (interacciones públicas).
 */
import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";
import { patch } from "@web/core/utils/patch";
import { addLoadingEffect } from "@web/core/utils/ui";
import { WebsiteSale } from "@website_sale/interactions/website_sale";

/** Si el servidor no contesta en este tiempo, el botón se libera de todos modos. */
export const TOPE_OCUPADO_MS = 20000;
const REGION = "o_dcasa_estado_carrito";

/** Texto para lectores de pantalla (una sola región «status» en toda la página). */
export function anunciar(texto) {
    let region = document.getElementById(REGION);
    if (!region) {
        region = document.createElement("div");
        region.id = REGION;
        region.className = "visually-hidden";
        region.setAttribute("role", "status");
        region.setAttribute("aria-live", "polite");
        document.body.appendChild(region);
    }
    region.textContent = texto;
}

/**
 * Pone el botón en «cargando» (cargador de Odoo, deshabilitado) y devuelve la función que lo deja como estaba.
 * Devuelve `null` si ya estaba ocupado: quien llama no debe repetir la acción.
 * @param {HTMLElement} boton
 * @returns {Function|null}
 */
export function ocupar(boton) {
    if (!boton || boton.dataset.dcasaOcupado) {
        return null;
    }
    boton.dataset.dcasaOcupado = "1";
    boton.setAttribute("aria-busy", "true");
    const quitarCargador = addLoadingEffect(boton);
    let liberado = false;
    const liberar = () => {
        if (liberado) {
            return;
        }
        liberado = true;
        clearTimeout(seguro);
        quitarCargador();
        boton.removeAttribute("aria-busy");
        delete boton.dataset.dcasaOcupado;
    };
    const seguro = setTimeout(liberar, TOPE_OCUPADO_MS);
    return liberar;
}

/**
 * ¿Tocar este enlace abre OTRA página del mismo sitio en esta misma pestaña? (Entonces se muestra la barra.)
 * No: clic con Ctrl/Cmd/Shift/Alt o botón que no es el principal, pestaña nueva, descarga, menús y pestañas de
 * Bootstrap, otro sitio, esquemas que no son http(s), la misma página (incluidas las anclas #).
 * @param {HTMLAnchorElement|null} enlace
 * @param {{button?: number, metaKey?: boolean, ctrlKey?: boolean, shiftKey?: boolean, altKey?: boolean}} ev
 * @param {Location} [ubicacion]
 */
export function esNavegacionNueva(enlace, ev, ubicacion = location) {
    if (!enlace || ev.button !== 0 || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey) {
        return false;
    }
    if (enlace.target === "_blank" || enlace.hasAttribute("download") || enlace.dataset.bsToggle) {
        return false;
    }
    let destino;
    try {
        destino = new URL(enlace.href, ubicacion.href);
    } catch {
        return false;
    }
    if (destino.origin !== ubicacion.origin || !/^https?:$/.test(destino.protocol)) {
        return false;
    }
    return !(destino.pathname === ubicacion.pathname && destino.search === ubicacion.search);
}

patch(WebsiteSale.prototype, {
    async onClickAdd(ev) {
        const boton = ev.currentTarget;
        const liberar = ocupar(boton);
        if (!liberar) {
            return; // ya se está agregando: el toque repetido no suma otra unidad
        }
        anunciar("Agregando al carrito…");
        try {
            return await super.onClickAdd(...arguments);
        } finally {
            liberar();
        }
    },
});

/** «Agregar» de las tarjetas de la portada y de Black Weekend: un formulario normal que va a /shop/cart. */
export class DcasaAgregarDirecto extends Interaction {
    static selector = 'form[action="/dcasa/carrito/agregar"]';
    dynamicContent = {
        _root: { "t-on-submit": this.alEnviar },
        _window: { "t-on-pageshow.noUpdate": this.alVolver },
    };

    alEnviar(ev) {
        if (this.liberar) {
            ev.preventDefault(); // ya se envió: un segundo envío sumaría otra unidad
            return;
        }
        const boton = this.el.querySelector('button[type="submit"]');
        // Después del envío (no durante el evento): deshabilitar el botón dentro del propio «submit» no debe
        // poder cancelar el formulario en ningún navegador.
        setTimeout(() => {
            this.liberar = ocupar(boton) || (() => {});
        });
        this.liberar = () => {};
        anunciar("Agregando al carrito…");
    }

    /** Volver atrás desde el carrito (o el caché de páginas del navegador): el botón no puede quedar girando. */
    alVolver(ev) {
        if (ev.persisted && this.liberar) {
            this.liberar();
            this.liberar = null;
        }
    }
}

/**
 * Barra de progreso fina arriba, mientras se abre otra página. Solo enlaces y formularios normales del mismo
 * sitio; se quita al volver desde el caché (pageshow) o a los 15 s por si la navegación nunca ocurre
 * (una descarga, un enlace que el navegador abre aparte).
 */
export class DcasaProgreso extends Interaction {
    static selector = "#wrapwrap";
    dynamicContent = {
        _document: {
            "t-on-click.noUpdate": this.alTocarEnlace,
            "t-on-submit.noUpdate": this.alEnviarFormulario,
        },
        _window: { "t-on-pageshow.noUpdate": this.quitar },
    };

    start() {
        this.registerCleanup(() => this.quitar());
    }

    alTocarEnlace(ev) {
        const enlace = ev.target.closest?.("a[href]");
        if (esNavegacionNueva(enlace, ev)) {
            this.arrancarSiSigue(ev);
        }
    }

    alEnviarFormulario(ev) {
        this.arrancarSiSigue(ev);
    }

    /** Otros manejadores corren antes y pueden cancelar la navegación (un menú, un modal): se revisa después. */
    arrancarSiSigue(ev) {
        setTimeout(() => {
            if (!ev.defaultPrevented) {
                this.arrancar();
            }
        });
    }

    arrancar() {
        document.documentElement.classList.add("o_dcasa_navegando");
        clearTimeout(this.vence);
        this.vence = setTimeout(() => this.quitar(), 15000);
    }

    quitar() {
        clearTimeout(this.vence);
        document.documentElement.classList.remove("o_dcasa_navegando");
    }
}

const interacciones = registry.category("public.interactions");
interacciones.add("website_dcasa.agregar_directo", DcasaAgregarDirecto);
interacciones.add("website_dcasa.progreso", DcasaProgreso);
