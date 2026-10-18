/**
 * Píxel de Meta con consentimiento (docs/META_EVENTOS.md, diseño §5.3).
 *
 * El servidor solo escribe `data-dcasa-meta-pixel="<id>"` en el layout cuando el píxel está encendido, es producción,
 * la política de privacidad tiene la sección de Meta, el sitio muestra el aviso de cookies y quien visita no es del
 * personal. Sin ese atributo este archivo no hace nada con Meta.
 *
 *   · Mientras la persona no acepte las cookies opcionales (cookie `website_cookies_bar` con `optional: true`, o el
 *     evento `optionalCookiesAccepted` del aviso de Odoo) los eventos esperan en una cola en memoria: no se carga
 *     `fbevents.js` ni se llama a `fbq`. Si elige «Solo las necesarias», la cola se descarta.
 *   · Al aceptar: se carga `fbevents.js`, `fbq('set', 'autoConfig', false, id)` (sin clics ni datos de la página
 *     por cuenta de Meta), `fbq('init', id)`, `PageView` y se reproduce la cola con sus `eventID`.
 *     Si `window.fbq` ya existe (las pruebas definen uno falso), no se pide nada a la red.
 *   · Cada evento lleva `eventID` = `<evento>-<uuid4>` (contrato 2.4) y los `content_ids` son ids de variante
 *     (`product.product`), los mismos del catálogo y de la Conversions API (contrato 2.1).
 *   · El píxel NUNCA manda `Purchase`: la compra la reporta el servidor cuando la factura queda pagada.
 *
 * Además, aunque el píxel esté apagado: «Preferencias de cookies» del pie (borra la elección y vuelve a abrir el
 * aviso) y la casilla de consentimiento del checkout (la guarda el servidor en el pedido).
 */
import { rpc } from "@web/core/network/rpc";

const COOKIE_AVISO = "website_cookies_bar";
const URL_FBEVENTS = "https://connect.facebook.net/en_US/fbevents.js";
const MAX_BUSQUEDA = 100;
const SELECTOR_WHATSAPP = 'a[href*="wa.me/"], a[href^="/whatsapp"]';
const FORMULARIO_AGREGAR = 'form[action="/dcasa/carrito/agregar"][data-dcasa-meta-id]';
const EVENTOS_DE_PAGINA = ["InitiateCheckout", "AddPaymentInfo"];

/** Estado del píxel en esta página (uno solo, aunque el archivo se evalúe en varias interacciones). */
export const estado = { pixelId: null, listo: false, rechazado: false, cola: [] };

/** `true` aceptó las opcionales · `false` eligió «Solo las necesarias» · `null` todavía no eligió. */
export function leerConsentimiento() {
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

function uuid4() {
    if (window.crypto?.randomUUID) {
        return window.crypto.randomUUID();
    }
    const bytes = window.crypto.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export function nuevoEventId(evento) {
    return `${evento}-${uuid4()}`;
}

/** Manda (o deja en la cola hasta el consentimiento) un evento estándar. Devuelve su `eventID`. */
export function rastrear(evento, datos = {}) {
    if (evento === "Purchase" || !estado.pixelId || estado.rechazado) {
        return null;
    }
    const eventID = nuevoEventId(evento);
    if (estado.listo) {
        window.fbq("track", evento, datos, { eventID });
    } else {
        estado.cola.push([evento, datos, eventID]);
    }
    return eventID;
}

/** El cargador estándar de Meta, sin `<noscript>`. No pide nada a la red si `fbq` ya existe. */
function instalarCargador() {
    if (window.fbq) {
        return;
    }
    const fbq = function () {
        fbq.callMethod ? fbq.callMethod.apply(fbq, arguments) : fbq.queue.push(arguments);
    };
    window.fbq = fbq;
    if (!window._fbq) {
        window._fbq = fbq;
    }
    fbq.push = fbq;
    fbq.loaded = true;
    fbq.version = "2.0";
    fbq.queue = [];
    const script = document.createElement("script");
    script.async = true;
    script.src = URL_FBEVENTS;
    if (script.dataset.needCookiesApproval) {
        // El vigilante de terceros de Odoo (cookie_watcher.js) lee la cookie del aviso, que Odoo escribe DESPUÉS del
        // evento «aceptar»: la persona ya aceptó, así que se usa la misma vía que el vigilante usa para soltarlo.
        delete script.dataset.needCookiesApproval;
        delete script.dataset.nocookieSrc;
        script._src = URL_FBEVENTS;
    }
    document.head.appendChild(script);
}

/** Con el consentimiento: carga el píxel, `init`, `PageView` y la cola, en ese orden. */
export function activar() {
    if (estado.listo || !estado.pixelId || estado.rechazado) {
        return;
    }
    instalarCargador();
    // Sin la «configuración automática» de Meta: el píxel no manda por su cuenta los clics de los botones ni los datos
    // de la página (solo los eventos de aquí, los que dice el aviso). Va ANTES de `init`, como pide Meta.
    window.fbq("set", "autoConfig", false, estado.pixelId);
    window.fbq("init", estado.pixelId);
    window.fbq("track", "PageView", {}, { eventID: nuevoEventId("PageView") });
    estado.listo = true;
    for (const [evento, datos, eventID] of estado.cola.splice(0)) {
        window.fbq("track", evento, datos, { eventID });
    }
}

export function rechazar() {
    estado.rechazado = true;
    estado.cola.length = 0;
}

function numero(texto) {
    const valor = Number.parseFloat(texto);
    return Number.isFinite(valor) ? valor : 0;
}

/** Productos agregados por el carrito de Odoo (`add_to_cart_event`, el mismo enganche del seguimiento nativo). */
export function alAgregarAlCarrito(ev) {
    const items = (Array.isArray(ev.detail) ? ev.detail : []).filter((item) => item && item.dcasa_meta_id);
    if (!items.length) {
        return;
    }
    rastrear("AddToCart", {
        content_type: "product",
        content_ids: items.map((item) => String(item.dcasa_meta_id)),
        contents: items.map((item) => ({ id: String(item.dcasa_meta_id), quantity: numero(item.quantity) || 1 })),
        value: Math.round(items.reduce((suma, item) => suma + numero(item.price) * (numero(item.quantity) || 1), 0) * 100) / 100,
        currency: items[0].currency,
    });
}

/** «Agregar» de un clic de la portada y de Black Weekend (formulario normal hacia /dcasa/carrito/agregar). */
function alEnviarFormulario(ev) {
    const forma = ev.target?.closest?.(FORMULARIO_AGREGAR);
    if (!forma || ev.defaultPrevented) {
        return; // un segundo envío cancelado no suma otra unidad: tampoco otro evento
    }
    const id = forma.dataset.dcasaMetaId;
    rastrear("AddToCart", {
        content_type: "product",
        content_ids: [id],
        contents: [{ id, quantity: 1 }],
        value: numero(forma.dataset.dcasaMetaValor),
        currency: forma.dataset.dcasaMetaMoneda,
    });
}

function alTocar(ev) {
    if (ev.target?.closest?.(SELECTOR_WHATSAPP)) {
        rastrear("Contact");
    }
}

/** Los eventos que dibuja la página misma: ficha, búsqueda, checkout y confirmación. */
function eventosDeLaPagina() {
    const ficha = document.querySelector("#product_detail[data-dcasa-meta-id]");
    if (ficha) {
        rastrear("ViewContent", {
            content_type: "product",
            content_ids: [ficha.dataset.dcasaMetaId],
            value: numero(ficha.dataset.dcasaMetaValor),
            currency: ficha.dataset.dcasaMetaMoneda,
        });
    }
    const busqueda = new URLSearchParams(window.location.search).get("search");
    if (busqueda && window.location.pathname.startsWith("/shop")) {
        rastrear("Search", { search_string: busqueda.trim().slice(0, MAX_BUSQUEDA) });
    }
    const nodo = document.getElementById("dcasa-meta-datos");
    if (nodo) {
        try {
            const { evento, datos } = JSON.parse(nodo.textContent);
            if (EVENTOS_DE_PAGINA.includes(evento)) {
                rastrear(evento, datos);
            }
        } catch {
            // datos ilegibles: no se manda nada
        }
    }
}

export function iniciarPixel() {
    const raiz = document.querySelector("[data-dcasa-meta-pixel]");
    const pixelId = raiz?.dataset.dcasaMetaPixel;
    if (!pixelId || !/^\d{5,20}$/.test(pixelId) || estado.pixelId) {
        return;
    }
    estado.pixelId = pixelId;
    const consentimiento = leerConsentimiento();
    if (consentimiento === true) {
        activar();
    } else if (consentimiento === false) {
        rechazar();
    } else {
        document.addEventListener("optionalCookiesAccepted", activar);
        document.addEventListener("optionalCookiesDenied", rechazar);
    }
    if (estado.rechazado) {
        return;
    }
    eventosDeLaPagina();
    // add_to_cart_event no burbujea: se escucha en la fase de captura.
    document.addEventListener("add_to_cart_event", alAgregarAlCarrito, true);
    document.addEventListener("submit", alEnviarFormulario);
    document.addEventListener("click", alTocar, true);
}

/** Borra una cookie en esta ruta y en los dominios donde Meta y Odoo la ponen. */
function borrarCookie(nombre) {
    const partes = window.location.hostname.split(".");
    const dominios = [""];
    for (let i = 0; i < partes.length - 1; i++) {
        dominios.push(`; domain=.${partes.slice(i).join(".")}`);
    }
    for (const dominio of dominios) {
        document.cookie = `${nombre}=; Max-Age=0; path=/${dominio}`;
    }
}

/** «Preferencias de cookies» (pie): borra la elección y las cookies de Meta y vuelve a abrir el aviso. */
function alPedirPreferencias(ev) {
    const enlace = ev.target?.closest?.("a.o_dcasa_cookies_preferencias");
    if (!enlace) {
        return;
    }
    ev.preventDefault();
    for (const nombre of [COOKIE_AVISO, "_fbp", "_fbc"]) {
        borrarCookie(nombre);
    }
    window.location.reload();
}

/** La casilla de consentimiento del checkout: la guarda el servidor (desmarcada de fábrica). */
async function alCambiarCasilla(ev) {
    const casilla = ev.target;
    if (casilla?.id !== "dcasa_meta_consentimiento_compra") {
        return;
    }
    try {
        const respuesta = await rpc("/dcasa/meta/consentimiento-compra", { acepta: casilla.checked });
        if (!respuesta?.ok) {
            casilla.checked = false;
        }
    } catch {
        casilla.checked = false;
    }
}

function iniciar() {
    iniciarPixel();
    document.addEventListener("click", alPedirPreferencias);
    document.addEventListener("change", alCambiarCasilla);
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", iniciar, { once: true });
} else {
    iniciar();
}
