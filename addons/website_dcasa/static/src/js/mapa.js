/**
 * El mapa de Google en Visítanos, sin cookies de Google sin permiso (lote 2 de la web, aprobado por la dueña).
 *
 * La página trae un recuadro con «Ver el mapa» y la dirección del mapa en `data-dcasa-mapa`; el <iframe> de Google se
 * pone solo:
 *   · al abrir la página, si quien visita ya aceptó las cookies opcionales en el aviso del sitio (la cookie
 *     `website_cookies_bar` con `optional: true`, la misma que lee el píxel de Meta, dcasa_meta_eventos);
 *   · si las acepta después en el aviso (evento `optionalCookiesAccepted` de Odoo);
 *   · o cuando toca «Ver el mapa».
 * La decisión se toma en el navegador: la página es la misma para todos (la guarda el borde). Solo se carga una
 * dirección de mapas de Google (`/maps/embed`).
 */
import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";

const MAPA_PERMITIDO = /^https:\/\/www\.google\.com\/maps\/embed\?/;

/** `true` aceptó las cookies opcionales · `false` eligió «Solo las necesarias» · `null` todavía no eligió. */
export function aceptoCookiesOpcionales() {
    const encontrado = document.cookie.match(/(?:^|;\s*)website_cookies_bar=([^;]*)/);
    if (!encontrado) {
        return null;
    }
    for (const texto of [encontrado[1], decodeURIComponent(encontrado[1])]) {
        try {
            const valor = JSON.parse(texto);
            return Boolean(valor && valor.optional === true);
        } catch {
            // se prueba la otra forma
        }
    }
    return null;
}

export class DcasaMapa extends Interaction {
    static selector = "[data-dcasa-mapa]";
    dynamicContent = {
        ".o_dcasa_mapa_ver": { "t-on-click": this.cargar },
    };

    start() {
        if (aceptoCookiesOpcionales() === true) {
            this.cargar();
        } else {
            this.addListener(document, "optionalCookiesAccepted", () => this.cargar());
        }
    }

    cargar() {
        const direccion = this.el.dataset.dcasaMapa || "";
        if (this.el.querySelector("iframe") || !MAPA_PERMITIDO.test(direccion)) {
            return;
        }
        const mapa = document.createElement("iframe");
        mapa.src = direccion;
        mapa.title = this.el.dataset.dcasaMapaTitulo || "Mapa";
        mapa.loading = "lazy";
        mapa.allowFullscreen = true;
        mapa.referrerPolicy = "strict-origin-when-cross-origin";
        this.el.appendChild(mapa);
        this.el.classList.add("o_dcasa_mapa_cargado");
    }
}

registry.category("public.interactions").add("website_dcasa.mapa", DcasaMapa);
