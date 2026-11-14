/**
 * «Brian de la tienda»: la burbuja con el robot y el chat de ventas (docs/BRIAN_TIENDA.md; contrato en
 * scratchpad/brian_tienda/contrato.md y contrato_cambios.md). Lleva a la web real el prototipo v2 que aprobó la dueña.
 *
 *   · La burbuja reemplaza la de WhatsApp. Sin JS es un enlace a WhatsApp; con JS abre el chat. Su pose sale del tipo
 *     de página (al llegar a otra página cambia de la pose anterior a la nueva con su propia transición), y al bajar o
 *     subir sigue a la sección que el visitante tiene en pantalla (``SECCIONES``: entre todas las páginas salen las 15
 *     poses de día; un cambio cada 2,5 s como mucho, con ``IntersectionObserver``). De noche duerme. Se hace a un lado si fuera a tapar un botón de la página; en la ficha del celular sube sobre la barra de
 *     «Agregar al carrito».
 *   · Funciona sobre páginas guardadas en el borde: nada viene personalizado en el HTML. Al abrir, el JS pide un token
 *     CSRF fresco (/dcasa/borde/csrf), el pase (POST /dcasa/brian/v1/pase) y el carrito (GET /dcasa/brian/v1/carrito).
 *   · Los mensajes van DIRECTO al Worker de Juan (POST {worker}/tienda/v1/mensaje, «Authorization: Pase …»). El modelo
 *     nunca toca el carrito: si Brian propone agregar, la página lo aplica en Odoo con la sesión del visitante y le
 *     cuenta el resultado (accion confirmar_carrito). Los precios y totales que se ven salen de Odoo.
 *   · La ubicación (navigator.geolocation) solo se pide al tocar «Usar mi ubicación actual» y viaja solo en ese turno.
 *   · Lo conversado se recuerda en ESTE navegador (sessionStorage, se borra al cerrar la pestaña) para que el chat siga
 *     igual al pasar de página; Odoo no guarda la conversación.
 *   · Accesible: foco, Esc para cerrar, aria-*; con movimiento reducido, quieto.
 *
 * Todo el texto que llega del Worker se pinta con textContent (nunca como HTML) y los enlaces e imágenes solo pueden
 * ser de este mismo sitio (o wa.me para WhatsApp).
 *
 * Ojo: nada de plantillas de texto con comillas invertidas dentro de otra; el minificador de Odoo les come los
 * espacios del borde («abramos(atendemos», «2×Colchón»). Se arma con «+» (lo revisa test_ajustes.py).
 */
import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";

// ---------------------------------------------------------------------------------------------------------------------
// Datos fijos
// ---------------------------------------------------------------------------------------------------------------------

export const POSES = [
    "saludando", "con_laptop", "escritorio", "busto_estrella", "bolsita", "mapa", "cinta_metrica", "corazon",
    "burbuja_chat", "cinco_estrellas", "fidelidad", "durmiendo", "asomado_burbuja", "cama", "cocina", "marco_foto",
];
const ENCUADRADOS = new Set(["cama", "escritorio"]); // traen fondo o son anchos: llenan el círculo
/** La transición con que entra cada pose dentro del chat (las mismas del prototipo). */
const TRANS_DE_POSE = {
    saludando: "pop", con_laptop: "sacudida", escritorio: "cruce", busto_estrella: "estrella", bolsita: "salto",
    mapa: "pendulo", cinta_metrica: "estira", corazon: "latido", burbuja_chat: "desliza", cinco_estrellas: "giro",
    fidelidad: "volteo", durmiendo: "sueno", asomado_burbuja: "pop", cama: "volteo", cocina: "desliza",
    marco_foto: "enfoque",
};
/** La pose de la burbuja según el tipo de página, y la transición con que llega. */
const PAGINAS = {
    inicio: { pose: "asomado_burbuja", trans: "pop" },
    catalogo: { pose: "con_laptop", trans: "sacudida" },
    colchones: { pose: "cama", trans: "volteo" },
    cocina: { pose: "cocina", trans: "desliza" },
    escritorios: { pose: "escritorio", trans: "cruce" },
    categoria: { pose: "con_laptop", trans: "sacudida" },
    ficha: { pose: "marco_foto", trans: "enfoque" },    // arriba están las fotos; las medidas, más abajo
    carrito: { pose: "bolsita", trans: "salto" },
    socios: { pose: "fidelidad", trans: "giro" },
    visitanos: { pose: "mapa", trans: "pendulo" },
    foto: { pose: "marco_foto", trans: "enfoque" },
    noche: { pose: "durmiendo", trans: "sueno" },
    otra: { pose: "asomado_burbuja", trans: "pop" },
};
const INICIO = ["Colchones", "Salas", "¿Cuánto cuesta el envío?", "Formas de pago"];
const SIGUE_TRAS_AGREGAR = ["¿Cuánto cuesta el envío?", "Formas de pago", "Seguir viendo"];
const DISPO = { disponible: ["o_dcbt_dispo_ok", "Disponible"], pocas: ["o_dcbt_dispo_pocas", "Quedan pocas"], agotado: ["o_dcbt_dispo_agotado", "Agotado"] };
const MAX_TEXTO = 500;
const MAX_CANTIDAD = 20;
const MAX_HISTORIAL = 80;
const PLAZO_WORKER_MS = 30000;
const PLAZO_UBICACION_MS = 8000;
const CLAVE_CHAT = "dcasa.brian.chat";
const CLAVE_PASE = "dcasa.brian.pase";
const CLAVE_POSE = "dcasa.brian.pose";
const RUTA = "/dcasa/brian/v1";
/** Botones de la página que la burbuja nunca tapa (se hace a un lado mientras estén debajo). */
const NO_TAPAR = '.o_dcasa_wa_producto, #add_to_cart, a.btn[href*="wa.me"], a.btn[href^="/whatsapp"], [name="website_sale_main_button"], .o_dcasa_brian_no_tapar';

const TRAZO = 'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"';
const ICO = {
    wa: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2.8a9.2 9.2 0 0 0-7.9 13.9L2.8 21.2l4.6-1.2A9.2 9.2 0 1 0 12 2.8z" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linejoin="round"/><path fill="currentColor" d="M8.7 7.4c.2-.4.4-.4.7-.4h.6c.2 0 .4 0 .6.5l.8 1.9c.1.2.1.4 0 .6l-.5.7c-.2.2-.2.4-.1.6.5.8 1.1 1.5 1.8 2.1.7.6 1.4 1 2.1 1.3.2.1.4.1.6-.1l.7-.8c.2-.2.4-.2.6-.1l1.9.9c.3.1.4.3.4.5 0 .5-.2 1.2-.7 1.6-.6.4-1.3.6-2.1.5-1.4-.2-2.8-.9-4.2-2-1.4-1.1-2.4-2.4-3-3.8-.4-.9-.5-1.7-.3-2.5.1-.6.3-1.1.6-1.5z"/></svg>',
    carrito: `<svg ${TRAZO}><path d="M2.5 4h2.6l2.3 10.4a1.6 1.6 0 0 0 1.6 1.3h8.3a1.6 1.6 0 0 0 1.5-1.2L20.8 8H6.1"/><circle cx="9.5" cy="19.6" r="1.4" fill="currentColor" stroke="none"/><circle cx="17" cy="19.6" r="1.4" fill="currentColor" stroke="none"/></svg>`,
    camion: `<svg ${TRAZO}><path d="M2.5 6h11v9.5h-11zM13.5 9.5h4l3.5 3.7v2.3h-7.5"/><circle cx="7" cy="17.5" r="1.9" fill="currentColor"/><circle cx="17" cy="17.5" r="1.9" fill="currentColor"/></svg>`,
    pin: `<svg ${TRAZO}><path d="M12 21s-6.5-5.8-6.5-11a6.5 6.5 0 0 1 13 0c0 5.2-6.5 11-6.5 11z"/><circle cx="12" cy="10" r="2.3"/></svg>`,
    menos: `<svg ${TRAZO}><path d="M6 12h12"/></svg>`,
    mas: `<svg ${TRAZO}><path d="M12 6v12M6 12h12"/></svg>`,
    izq: `<svg ${TRAZO}><path d="m14.5 5.5-6.5 6.5 6.5 6.5"/></svg>`,
    der: `<svg ${TRAZO}><path d="m9.5 5.5 6.5 6.5-6.5 6.5"/></svg>`,
    ampliar: `<svg ${TRAZO}><path d="M14 4h6v6M10 20H4v-6M20 4l-6.5 6.5M4 20l6.5-6.5"/></svg>`,
    reducir: `<svg ${TRAZO}><path d="M4 14h6v6M20 10h-6V4M13.5 10.5 20 4M10.5 13.5 4 20"/></svg>`,
    escudo: `<svg ${TRAZO}><path d="M12 3 19 6v5.5c0 4.3-2.9 7.9-7 9.5-4.1-1.6-7-5.2-7-9.5V6z"/><path d="m9 12 2.2 2.2L15.2 10"/></svg>`,
    cerrar: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m5.5 9 6.5 6.5L18.5 9"/></svg>',
    enviar: '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M3.4 20.3 21 12.6c.6-.3.6-1 0-1.3L3.4 3.7c-.6-.3-1.2.3-1 .9L4.7 11 13 12l-8.3 1-2.3 6.4c-.2.6.4 1.2 1 .9z"/></svg>',
    check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg>',
    pdf: `<svg ${TRAZO}><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M12 11v6m-2.8-2.6L12 17l2.8-2.6"/></svg>`,
    aviso: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7.5V13"/><circle cx="12" cy="16.6" r=".7" fill="currentColor"/></svg>',
    mira: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="2.4" fill="currentColor" stroke="none"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/></svg>',
    lapiz: `<svg ${TRAZO}><path d="M4 20h4L19 9l-4-4L4 16z"/><path d="m13.5 6.5 4 4"/></svg>`,
    estrella: '<svg viewBox="0 0 24 24" aria-hidden="true"><path class="o_dcbt_relleno" d="m12 3.2 2.7 5.5 6 .9-4.4 4.2 1 6-5.3-2.8-5.3 2.8 1-6-4.4-4.2 6-.9z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>',
};

const B = "cubic-bezier(.22, 1, .36, 1)";
/** Cada transición: cómo sale la pose vieja, cómo entra la nueva y, en algunas, qué hace el círculo entero. */
const TRANS = {
    pop: { sale: [{ transform: "scale(1)", opacity: 1 }, { transform: "scale(.3)", opacity: 0 }], ds: 160,
        entra: [{ transform: "scale(.2)", opacity: 0 }, { transform: "scale(1.18)", opacity: 1, offset: 0.55 }, { transform: "scale(.93)", offset: 0.78 }, { transform: "scale(1)", opacity: 1 }], de: 560, retardo: 120 },
    volteo: { sale: [{ transform: "perspective(240px) rotateY(0deg)" }, { transform: "perspective(240px) rotateY(90deg)" }], ds: 200, easeS: "ease-in",
        entra: [{ transform: "perspective(240px) rotateY(-90deg)" }, { transform: "perspective(240px) rotateY(14deg)", offset: 0.7 }, { transform: "perspective(240px) rotateY(0deg)" }], de: 420, retardo: 200, easeE: "ease-out" },
    estira: { origen: "50% 100%", sale: [{ transform: "scale(1, 1)", opacity: 1 }, { transform: "scale(1.35, .25)", opacity: 0 }], ds: 200, easeS: "ease-in",
        entra: [{ transform: "scale(1.35, .25)", opacity: 0 }, { transform: "scale(.82, 1.22)", opacity: 1, offset: 0.45 }, { transform: "scale(1.08, .92)", offset: 0.7 }, { transform: "scale(.98, 1.02)", offset: 0.86 }, { transform: "scale(1, 1)", opacity: 1 }], de: 640, retardo: 180, easeE: "ease-out" },
    desliza: { sale: [{ transform: "translateY(0)", opacity: 1 }, { transform: "translateY(-115%)", opacity: 0 }], ds: 320,
        entra: [{ transform: "translateY(115%)" }, { transform: "translateY(-7%)", offset: 0.7 }, { transform: "translateY(0)" }], de: 480, retardo: 40 },
    cruce: { sale: [{ transform: "scale(1)", opacity: 1, filter: "blur(0px)" }, { transform: "scale(1.4)", opacity: 0, filter: "blur(3px)" }], ds: 420, easeS: "ease-out",
        entra: [{ transform: "scale(.7)", opacity: 0 }, { transform: "scale(1)", opacity: 1 }], de: 460, retardo: 0 },
    sacudida: { caja: [{ transform: "rotate(0deg)" }, { transform: "rotate(-16deg)", offset: 0.12 }, { transform: "rotate(14deg)", offset: 0.26 }, { transform: "rotate(-12deg)", offset: 0.4 }, { transform: "rotate(10deg)", offset: 0.54 }, { transform: "rotate(-6deg)", offset: 0.7 }, { transform: "rotate(3deg)", offset: 0.85 }, { transform: "rotate(0deg)" }], dc: 760,
        sale: [{ opacity: 1 }, { opacity: 0 }], ds: 120, retardoSale: 260, entra: [{ opacity: 0 }, { opacity: 1 }], de: 120, retardo: 300 },
    salto: { sale: [{ transform: "translateY(0)", opacity: 1 }, { transform: "translateY(120%)", opacity: 0 }], ds: 220, easeS: "ease-in",
        entra: [{ transform: "translateY(-130%)" }, { transform: "translateY(0)", offset: 0.5 }, { transform: "translateY(-16%)", offset: 0.68 }, { transform: "translateY(0)", offset: 0.82 }, { transform: "translateY(-5%)", offset: 0.92 }, { transform: "translateY(0)" }], de: 720, retardo: 160, easeE: "linear" },
    giro: { caja: [{ transform: "rotate(0deg) scale(1)" }, { transform: "rotate(180deg) scale(.82)", offset: 0.5 }, { transform: "rotate(360deg) scale(1)" }], dc: 680, easeC: "cubic-bezier(.6, 0, .3, 1)",
        sale: [{ opacity: 1 }, { opacity: 0 }], ds: 140, retardoSale: 220, entra: [{ opacity: 0 }, { opacity: 1 }], de: 140, retardo: 280 },
    pendulo: { origen: "50% -30%", sale: [{ transform: "rotate(0deg)", opacity: 1 }, { transform: "rotate(-75deg)", opacity: 0 }], ds: 260, easeS: "ease-in",
        entra: [{ transform: "rotate(60deg)", opacity: 0 }, { transform: "rotate(-18deg)", opacity: 1, offset: 0.45 }, { transform: "rotate(10deg)", offset: 0.65 }, { transform: "rotate(-4deg)", offset: 0.82 }, { transform: "rotate(0deg)", opacity: 1 }], de: 860, retardo: 160, easeE: "ease-out" },
    enfoque: { sale: [{ transform: "scale(1)", opacity: 1 }, { transform: "scale(.6)", opacity: 0 }], ds: 200,
        entra: [{ transform: "scale(1.9)", opacity: 0, filter: "blur(8px)" }, { transform: "scale(1)", opacity: 1, filter: "blur(0px)" }], de: 540, retardo: 140, flash: true },
    sueno: { sale: [{ transform: "translateY(0)", opacity: 1 }, { transform: "translateY(14%)", opacity: 0 }], ds: 650, easeS: "ease-in-out",
        entra: [{ transform: "translateY(-10%) scale(.96)", opacity: 0 }, { transform: "translateY(0) scale(1)", opacity: 1 }], de: 950, retardo: 380, easeE: "ease-in-out" },
    latido: { sale: [{ opacity: 1, transform: "scale(1)" }, { opacity: 0, transform: "scale(.8)" }], ds: 160,
        entra: [{ transform: "scale(.6)", opacity: 0 }, { transform: "scale(1.22)", opacity: 1, offset: 0.3 }, { transform: "scale(.96)", offset: 0.5 }, { transform: "scale(1.12)", offset: 0.68 }, { transform: "scale(1)", opacity: 1 }], de: 780, retardo: 120, easeE: "ease-out" },
    estrella: { sale: [{ transform: "rotate(0deg) scale(1)", opacity: 1 }, { transform: "rotate(160deg) scale(.3)", opacity: 0 }], ds: 220, easeS: "ease-in",
        entra: [{ transform: "rotate(-200deg) scale(.3)", opacity: 0 }, { transform: "rotate(12deg) scale(1.1)", opacity: 1, offset: 0.7 }, { transform: "rotate(0deg) scale(1)", opacity: 1 }], de: 600, retardo: 160 },
};
/** En reposo: un movimiento leve cada tanto (con la burbuja cerrada). */
const REPOSO = {
    sacudida: { k: [{ rotate: "0deg" }, { rotate: "-12deg", offset: 0.15 }, { rotate: "11deg", offset: 0.3 }, { rotate: "-9deg", offset: 0.45 }, { rotate: "7deg", offset: 0.6 }, { rotate: "-3deg", offset: 0.8 }, { rotate: "0deg" }], d: 700 },
    saludo: { k: [{ rotate: "0deg" }, { rotate: "-14deg", offset: 0.25 }, { rotate: "9deg", offset: 0.5 }, { rotate: "-5deg", offset: 0.75 }, { rotate: "0deg" }], d: 1100 },
    flotar: { k: [{ translate: "0 0" }, { translate: "0 -8px", offset: 0.3 }, { translate: "0 0", offset: 0.6 }, { translate: "0 -4px", offset: 0.8 }, { translate: "0 0" }], d: 1800, e: "ease-in-out" },
    brinco: { k: [{ translate: "0 0", scale: "1 1" }, { translate: "0 0", scale: "1.1 .88", offset: 0.2 }, { translate: "0 -12px", scale: ".92 1.08", offset: 0.45 }, { translate: "0 0", scale: "1.06 .94", offset: 0.7 }, { translate: "0 0", scale: "1 1" }], d: 800 },
    latido: { k: [{ scale: "1" }, { scale: "1.12", offset: 0.2 }, { scale: "1", offset: 0.4 }, { scale: "1.08", offset: 0.6 }, { scale: "1" }], d: 900 },
};

// ---------------------------------------------------------------------------------------------------------------------
// Funciones puras (se prueban en el navegador: tests/test_navegador.py)
// ---------------------------------------------------------------------------------------------------------------------

/** El tipo de página para la pose y para el Worker (contrato §2, «pagina»). */
export function tipoDePagina(ruta, doc = document) {
    const r = (ruta || "/").replace(/\/+$/, "") || "/";
    const pagina = { tipo: "otra", producto_id: null, categoria: null };
    if (r === "/" || /^\/[a-z]{2}(?:_[A-Z]{2})?$/.test(r)) {
        pagina.tipo = "inicio";
    } else if (doc.querySelector("#product_detail")) {
        pagina.tipo = "ficha";
        const campo = doc.querySelector('#product_detail input[name="product_id"]');
        const id = Number(campo && campo.value);
        pagina.producto_id = Number.isInteger(id) && id > 0 ? id : null;
    } else if (r.startsWith("/shop/cart")) {
        pagina.tipo = "carrito";
    } else if (r.startsWith("/shop/foto")) {
        pagina.tipo = "foto";
    } else if (r.startsWith("/shop/category/")) {
        pagina.tipo = "categoria";
        const nombre = doc.querySelector(".o_wsale_breadcrumb li.active, .o_wsale_breadcrumb .breadcrumb-item.active, h1");
        pagina.categoria = nombre ? nombre.textContent.trim().slice(0, 80) || null : null;
    } else if (r === "/shop" || r.startsWith("/shop/page/")) {
        pagina.tipo = "catalogo";
    } else if (r.startsWith("/socios")) {
        pagina.tipo = "socios";
    } else if (r.startsWith("/visitanos")) {
        pagina.tipo = "visitanos";
    }
    return pagina;
}

export function normalizar(texto) {
    return String(texto || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

/** La pose de la burbuja: la del tipo de página (las categorías con la suya) o, de noche, dormido. */
export function poseDePagina(pagina, noche, ruta = "") {
    if (noche) {
        return PAGINAS.noche;
    }
    if (pagina.tipo === "categoria") {
        const pista = normalizar(`${ruta} ${pagina.categoria || ""}`);
        if (/colchon/.test(pista)) {
            return PAGINAS.colchones;
        }
        if (/cocina|comedor/.test(pista)) {
            return PAGINAS.cocina;
        }
        if (/oficina|escritorio/.test(pista)) {
            return PAGINAS.escritorios;
        }
        return PAGINAS.categoria;
    }
    return PAGINAS[pagina.tipo] || PAGINAS.otra;
}

// ---------------------------------------------------------------------------------------------------------------------
// La pose por sección (pedido de la dueña, 2026-11-14: «que el ícono vaya cambiando con el scroll»)
// ---------------------------------------------------------------------------------------------------------------------

/** Lo mínimo entre dos cambios de pose de la burbuja, y lo que tiene que quedarse quieta una sección para contar. */
export const MIN_ENTRE_CAMBIOS_MS = 2500;
const ESTABLE_MS = 450;
/** La franja de la ventana que decide «la sección que tienes en pantalla»: del 45 % al 50 % de la altura. */
const FRANJA = "-45% 0px -50% 0px";
/** Los productos del catálogo van pasando por estas poses de a cuatro (sin repetir la de al lado). */
const CICLO_CATALOGO = ["corazon", "busto_estrella", "bolsita", "escritorio", "cocina", "con_laptop"];
const POR_TRAMO = 4;

function poseDeTema(texto, otra) {
    const t = normalizar(texto);
    if (/colchon|dormir|recamara|cama/.test(t)) {
        return "cama";
    }
    if (/cocina|comedor|estante|organizacion/.test(t)) {
        return "cocina";
    }
    if (/oficina|escritorio/.test(t)) {
        return "escritorio";
    }
    if (/zapatera/.test(t)) {
        return "bolsita";
    }
    return otra;
}
const atributo = (el, sel, nombre) => (el && el.querySelector(sel) ? el.querySelector(sel).getAttribute(nombre) || "" : "");
const temaDeCarrusel = (el) => poseDeTema((el.closest("section") ? el.closest("section").getAttribute("aria-label") || "" : "") + " " + (el.textContent || ""), "busto_estrella");
const temaDeTarjeta = (el) => poseDeTema(atributo(el, "img", "src") + " " + (el.textContent || ""), "corazon");
const PIE = { sel: "#bottom, footer", pose: "saludando" };

/**
 * Las secciones de cada tipo de página y su pose, de arriba abajo (las que existen en website_dcasa y website_sale;
 * ninguna inventada). ``pose``: el nombre, ``null`` = la de la página, o una función ``(elemento, i)`` con ``poses`` (las
 * que puede dar). Si varias cruzan la franja a la vez (una fila de tarjetas, dos columnas), van pasando una por una
 * mientras sigan ahí (``seccionActiva``).
 */
export const SECCIONES = {
    inicio: [
        { sel: ".o_dcasa_hero", pose: null },
        { sel: ".o_dcasa_beneficios", pose: "saludando" },
        { sel: ".o_dcasa_bw", pose: "busto_estrella" },
        { sel: ".o_dcasa_categorias .o_dcasa_section_head", pose: "con_laptop" },
        { sel: ".o_dcasa_categorias .o_dcasa_cat", pose: temaDeTarjeta, poses: ["corazon", "cama", "bolsita", "cocina", "escritorio"] },
        { sel: ".o_dcasa_rail .o_dcasa_section_head", pose: temaDeCarrusel, poses: ["busto_estrella", "cama", "cocina", "escritorio", "bolsita"] },
        { sel: ".o_dcasa_rail .o_dcasa_rail_track", pose: "bolsita" },
        { sel: ".o_dcasa_split", pose: "corazon" },
        { sel: ".o_dcasa_socios_band", pose: "fidelidad" },
        { sel: ".o_dcasa_resenas", pose: "cinco_estrellas" },
        { sel: ".o_dcasa_galeria", pose: "marco_foto" },
        { sel: ".o_dcasa_ayuda .o_dcasa_steps", pose: "cinta_metrica" },
        { sel: ".o_dcasa_ayuda .o_dcasa_faq", pose: "burbuja_chat" },
        { sel: ".o_dcasa_visita_franja", pose: "mapa" },
        PIE,
    ],
    catalogo: [
        { sel: ".o_dcasa_sin_resultados", pose: "burbuja_chat" },
        { sel: "#products_grid .oe_product", pose: (el, i) => (i < POR_TRAMO ? null : CICLO_CATALOGO[(Math.floor(i / POR_TRAMO) - 1) % CICLO_CATALOGO.length]), poses: CICLO_CATALOGO },
        { sel: "#o_wsale_pager", pose: "burbuja_chat" },
        { sel: "#bottom, footer", pose: "burbuja_chat" },
    ],
    ficha: [
        { sel: ".o_wsale_product_images", pose: null },
        { sel: ".o_wsale_product_details_content_section_price, .o_wsale_product_details_content_section_cta", pose: "bolsita" },
        { sel: ".o_wsale_product_details_content_section_specs, .o_wsale_product_details_content_section_accordion, #product_full_description:not(.oe_empty)", pose: "cinta_metrica" },
        { sel: ".o_wsale_product_details_content_section_contact", pose: "burbuja_chat" },
        { sel: "#dcasa-opiniones", pose: "cinco_estrellas" },
        { sel: ".o_wsale_alternative_products", pose: "corazon" },
        PIE,
    ],
    carrito: [
        { sel: ".o_wsale_accessory_products", pose: "corazon" },
        PIE,
    ],
    visitanos: [
        { sel: ".o_dcasa_hero", pose: null },
        { sel: ".o_dcasa_visita_direccion, .o_dcasa_visita_lista", pose: "saludando" },
        { sel: ".o_dcasa_visita_horario", pose: "busto_estrella" },
        { sel: ".o_dcasa_visita_aviso", pose: "burbuja_chat" },
        { sel: ".o_dcasa_mapa", pose: "mapa" },
        PIE,
    ],
    socios: [PIE],
    otra: [PIE],
};
SECCIONES.categoria = SECCIONES.catalogo;

/** Todas las poses que puede dar un tipo de página (la suya y las de sus secciones). */
export function posesDeSecciones(tipo, ruta = "") {
    const propia = poseDePagina({ tipo }, false, ruta).pose;
    const poses = new Set([propia]);
    for (const regla of SECCIONES[tipo] || []) {
        for (const p of typeof regla.pose === "function" ? regla.poses : [regla.pose || propia]) {
            poses.add(p);
        }
    }
    return poses;
}

/** Los elementos de las secciones de esta página con su pose, en el orden de la página. */
export function seccionesDeLaPagina(pagina, ruta = "", doc = document) {
    const propia = poseDePagina(pagina, false, ruta).pose;
    const vistos = new Set();
    const lista = [];
    for (const regla of SECCIONES[pagina.tipo] || SECCIONES.otra) {
        doc.querySelectorAll(regla.sel).forEach((el, i) => {
            if (vistos.has(el)) {
                return;
            }
            const p = typeof regla.pose === "function" ? regla.pose(el, i) : regla.pose;
            vistos.add(el);
            lista.push({ el, pose: POSES.includes(p) && p !== "durmiendo" ? p : propia });
        });
    }
    lista.sort((a, b) => (a.el.compareDocumentPosition(b.el) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1));
    lista.forEach((s, orden) => {
        s.orden = orden;
    });
    return lista;
}

/**
 * De las secciones que cruzan la franja, la que toca ahora (o ``null``: se queda como está): la primera, en el orden de
 * la página, que todavía no se mostró desde que entró a la franja y con otra pose que la de ahora. Así una fila de
 * tarjetas o dos columnas van pasando por sus poses mientras el visitante se detiene ahí, y la burbuja no vuelve atrás.
 * ``mostradas``: las que ya salieron (se olvidan al salir de la franja).
 */
export function seccionActiva(visibles, mostradas = new Set(), poseActual = null) {
    let activa = null;
    for (const s of visibles) {
        if (mostradas.has(s) || s.pose === poseActual) {
            continue;
        }
        if (!activa || s.orden < activa.orden) {
            activa = s;
        }
    }
    return activa;
}

/** ¿Es fuera del horario de Ajustes de Juan? (hora de Panamá). ``horario``: {inicio, fin, dias, zona, fin_domingo}. */
export function esDeNoche(horario, fecha = new Date()) {
    try {
        const partes = new Intl.DateTimeFormat("en-US", {
            timeZone: (horario && horario.zona) || "America/Panama", hour: "numeric", minute: "numeric", weekday: "short", hourCycle: "h23",
        }).formatToParts(fecha);
        const v = (t) => (partes.find((p) => p.type === t) || {}).value;
        const dia = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].indexOf(v("weekday"));
        const minutos = (Number(v("hour")) % 24) * 60 + Number(v("minute"));
        const aMin = (hhmm, defecto) => {
            const m = /^(\d{1,2}):(\d{2})$/.exec(String(hhmm || ""));
            return m ? Number(m[1]) * 60 + Number(m[2]) : defecto;
        };
        const dias = Array.isArray(horario && horario.dias) ? horario.dias : [0, 1, 2, 3, 4, 5, 6];
        if (!dias.includes(dia)) {
            return true;
        }
        const inicio = aMin(horario && horario.inicio, 9 * 60);
        const fin = dia === 0 && horario && horario.fin_domingo ? aMin(horario.fin_domingo, 17 * 60) : aMin(horario && horario.fin, 18 * 60);
        return minutos < inicio || minutos >= fin;
    } catch {
        return false;
    }
}

/** Una dirección de este mismo sitio (o ``null``): lo que manda el Worker nunca puede llevar a otro lado. */
export function urlPropia(valor, origen = window.location.origin) {
    if (typeof valor !== "string" || !valor) {
        return null;
    }
    try {
        const url = new URL(valor, origen);
        const propio = new URL(origen);
        if (!/^https?:$/.test(url.protocol)) {
            return null;
        }
        if (url.origin === propio.origin) {
            return url.pathname + url.search + url.hash;
        }
        // La ficha que Odoo da con la dirección pública del sitio (dcasapty.com) también es de aquí.
        if (/^(?:www\.)?dcasapty\.com$/.test(url.hostname) && url.protocol === "https:") {
            return url.pathname + url.search;
        }
        return null;
    } catch {
        return null;
    }
}

/** «$278.00 + ITBMS» → ["$278.00", "+ ITBMS"]. */
export function partirPrecio(texto) {
    const t = String(texto || "").trim();
    const m = /^(.*?)\s*(\+\s*ITBMS)$/i.exec(t);
    return m ? [m[1], "+ ITBMS"] : [t, ""];
}

/** El mensaje que va escrito en WhatsApp: lo del Worker o, si no, lo del carrito (sin datos personales). */
export function mensajeWhatsApp(carrito, extra) {
    let texto = "Hola D'CASA, vengo del chat de la web.";
    const lineas = (carrito && carrito.lineas) || [];
    if (lineas.length) {
        texto += " Tengo en el carrito: " + lineas.map((l) => `${l.cantidad} × ${l.nombre}`).join("; ") + ".";
    }
    if (extra) {
        texto += " " + extra;
    }
    return texto.slice(0, 600);
}

function leerAlmacen(clave) {
    try {
        const crudo = window.sessionStorage.getItem(clave);
        return crudo ? JSON.parse(crudo) : null;
    } catch {
        return null;
    }
}

function guardarAlmacen(clave, valor) {
    try {
        if (valor === null) {
            window.sessionStorage.removeItem(clave);
        } else {
            window.sessionStorage.setItem(clave, JSON.stringify(valor));
        }
    } catch {
        // Sin sessionStorage (ventana privada estricta): el chat funciona igual, solo no se recuerda al cambiar de página.
    }
}

const reducir = () => window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const esCelular = () => window.matchMedia && window.matchMedia("(max-width: 767.98px)").matches;
const pausa = (ms) => new Promise((r) => setTimeout(r, reducir() ? 0 : ms));
const entero = (v) => (Number.isInteger(v) ? v : null);

function el(tag, attrs, ...hijos) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
        if (v === false || v === null || v === undefined) {
            continue;
        }
        if (k === "class") {
            n.className = v;
        } else if (k === "text") {
            n.textContent = v;
        } else if (k === "html") {
            n.innerHTML = v; // solo íconos fijos de este archivo, nunca texto del Worker ni del visitante
        } else if (k.startsWith("on")) {
            n.addEventListener(k.slice(2), v);
        } else {
            n.setAttribute(k, v === true ? "" : v);
        }
    }
    for (const h of hijos) {
        if (h !== null && h !== undefined && h !== false) {
            n.append(h);
        }
    }
    return n;
}
const ico = (nombre, clase) => el("span", { class: clase || "o_dcbt_ico", html: ICO[nombre], "aria-hidden": "true" });

// ---------------------------------------------------------------------------------------------------------------------
// El chat
// ---------------------------------------------------------------------------------------------------------------------

export class ChatBrian {
    constructor(raiz) {
        this.raiz = raiz;
        this.rutaPoses = raiz.dataset.poses || "/dcasa_brian_tienda/static/src/img/poses/";
        this.whatsapp = /^\d{8,15}$/.test(raiz.dataset.whatsapp || "") ? raiz.dataset.whatsapp : "";
        try {
            this.horario = JSON.parse(raiz.dataset.horario || "null");
        } catch {
            this.horario = null;
        }
        this.ruta = window.location.pathname;
        this.pagina = tipoDePagina(this.ruta);
        this.noche = esDeNoche(this.horario);
        this.estado = {
            abierto: false, saludado: false, ampliado: false, pausa: false, pose: this.noche ? "durmiendo" : "saludando",
            autor: null, posePrevia: null, vistos: [], carrito: null, carritoCambio: false,
        };
        this.historial = [];
        this.cola = Promise.resolve();
        this.limpiezas = [];
        this.token = null;
    }

    // ------------------------------------------------------------------ arranque y limpieza

    iniciar() {
        const enlace = this.raiz.querySelector(".o_dcbt_burbuja");
        // Sin JS la burbuja es un enlace a WhatsApp; con JS, el botón que abre el chat.
        this.burbuja = el("button", {
            type: "button", class: "o_dcbt_burbuja", "aria-label": "Abrir el chat de la tienda", "aria-expanded": "false",
            "aria-controls": "o_dcbt_panel", title: "Chat de la tienda",
        });
        this.burbujaPose = el("span", { class: "o_dcbt_pose", "aria-hidden": "true" });
        this.burbuja.append(this.burbujaPose);
        if (enlace) {
            this.enlace = enlace;
            enlace.replaceWith(this.burbuja);
        } else {
            this.raiz.append(this.burbuja);
        }
        this.escuchar(this.burbuja, "click", () => this.abrir());
        this.ponerPoseDeBurbuja();
        this.escuchar(document, "keydown", (ev) => this.alTeclado(ev));
        this.vigilarBotonesDeLaPagina();
        this.vigilarSecciones();
        const guardado = leerAlmacen(CLAVE_CHAT);
        if (guardado && Array.isArray(guardado.historial) && guardado.historial.length) {
            this.restaurado = guardado;
            if (guardado.abierto && !esCelular()) {
                this.abrir({ sinAnimar: true });
            }
        }
        if (!reducir()) {
            const id = setTimeout(() => {
                this.reposo();
                this.intervaloReposo = setInterval(() => this.reposo(), 7000);
            }, 3400);
            this.limpiezas.push(() => {
                clearTimeout(id);
                clearInterval(this.intervaloReposo);
            });
        }
    }

    destruir() {
        for (const fn of this.limpiezas.splice(0)) {
            try {
                fn();
            } catch {
                // nada: limpiar nunca rompe la página
            }
        }
        document.documentElement.classList.remove("o_dcbt_abierto");
        if (this.panel) {
            this.panel.remove();
        }
        // Al detenerse (p. ej. el editor del sitio) vuelve el enlace a WhatsApp de la página sin JS.
        if (this.enlace && this.burbuja && this.burbuja.isConnected) {
            this.burbuja.replaceWith(this.enlace);
        }
    }

    escuchar(objetivo, evento, fn, opciones) {
        objetivo.addEventListener(evento, fn, opciones);
        this.limpiezas.push(() => objetivo.removeEventListener(evento, fn, opciones));
    }

    // ------------------------------------------------------------------ poses

    imgPose(pose) {
        const nombre = POSES.includes(pose) ? pose : "saludando";
        const i = new Image();
        i.src = `${this.rutaPoses}${nombre}.webp`;
        i.alt = "";
        i.draggable = false;
        i.decoding = "async";
        i.width = 256;
        i.height = 256;
        i.className = "o_dcbt_img_pose" + (ENCUADRADOS.has(nombre) ? " o_dcbt_encuadrado" : "");
        i.dataset.pose = nombre;
        return i;
    }

    cajaPose(clase, pose) {
        const caja = el("span", { class: `o_dcbt_pose ${clase || ""}`.trim(), "aria-hidden": "true" });
        caja.append(this.imgPose(pose));
        return caja;
    }

    cambiarPose(caja, pose, tipo) {
        const vieja = caja.querySelector("img.o_dcbt_img_pose:not(.o_dcbt_saliendo)");
        if (vieja && vieja.dataset.pose === pose) {
            return;
        }
        caja.querySelectorAll("img.o_dcbt_saliendo, .o_dcbt_flash").forEach((n) => n.remove());
        if (caja.getAnimations) {
            caja.getAnimations().forEach((a) => a.cancel());
        }
        const nueva = this.imgPose(pose);
        if (!vieja || reducir() || !caja.animate) {
            caja.querySelectorAll("img.o_dcbt_img_pose").forEach((n) => n.remove());
            caja.append(nueva);
            return;
        }
        vieja.getAnimations().forEach((a) => a.cancel());
        const t = TRANS[tipo] || TRANS.cruce;
        vieja.classList.add("o_dcbt_saliendo");
        vieja.style.transformOrigin = nueva.style.transformOrigin = t.origen || "50% 50%";
        caja.append(nueva);
        if (t.caja) {
            caja.animate(t.caja, { duration: t.dc, easing: t.easeC || "ease-in-out" });
        }
        const quitar = () => vieja.remove();
        vieja.animate(t.sale, { duration: t.ds, delay: t.retardoSale || 0, easing: t.easeS || "ease-in", fill: "forwards" }).finished.then(quitar, quitar);
        nueva.animate(t.entra, { duration: t.de, delay: t.retardo || 0, easing: t.easeE || B, fill: "backwards" });
        if (t.flash) {
            const f = el("span", { class: "o_dcbt_flash" });
            caja.append(f);
            const fuera = () => f.remove();
            f.animate([{ opacity: 0 }, { opacity: 0.85, offset: 0.2 }, { opacity: 0 }], { duration: 420, delay: t.retardo || 0 }).finished.then(fuera, fuera);
        }
    }

    /** La burbuja llega con la pose de la página anterior y cambia a la de esta con su transición. */
    ponerPoseDeBurbuja() {
        const destino = poseDePagina(this.pagina, this.noche, this.ruta);
        const previa = leerAlmacen(CLAVE_POSE);
        guardarAlmacen(CLAVE_POSE, destino.pose);
        this.poseBurbuja = destino.pose;
        this.ultimoCambio = Date.now();
        if (previa && POSES.includes(previa) && previa !== destino.pose && !reducir()) {
            this.burbujaPose.append(this.imgPose(previa));
            this.ultimoCambio += 1500;   // el cambio de llegada cuenta para el mínimo entre cambios
            const id = setTimeout(() => this.cambiarPose(this.burbujaPose, destino.pose, destino.trans), 1500);
            this.limpiezas.push(() => clearTimeout(id));
        } else {
            this.burbujaPose.append(this.imgPose(destino.pose));
        }
    }

    // ------------------------------------------------------------------ la pose que sigue a la sección en pantalla

    /** Al bajar o subir, la burbuja cerrada toma la pose de la sección que cruza la franja de la ventana (``SECCIONES``).
     * Sin cálculos en cada evento de scroll: ``IntersectionObserver``. Empieza cuando el visitante se mueve (al llegar,
     * la de la página). De noche (dormido) y con movimiento reducido, quieta como siempre. */
    vigilarSecciones() {
        if (this.noche || reducir() || !window.IntersectionObserver) {
            return;
        }
        const secciones = seccionesDeLaPagina(this.pagina, this.ruta);
        if (!secciones.length) {
            return;
        }
        const porElemento = new Map(secciones.map((s) => [s.el, s]));
        this.visibles = new Set();
        this.mostradas = new Set();
        const observador = new window.IntersectionObserver((entradas) => {
            for (const e of entradas) {
                const s = porElemento.get(e.target);
                if (e.isIntersecting) {
                    this.visibles.add(s);
                } else {
                    this.visibles.delete(s);
                    this.mostradas.delete(s);
                }
            }
            this.programarPoseDeSeccion();
        }, { rootMargin: FRANJA, threshold: 0 });
        secciones.forEach((s) => observador.observe(s.el));
        const alMoverse = () => {
            if (!this.seMovio) {
                this.seMovio = true;
                this.programarPoseDeSeccion();
            }
        };
        this.escuchar(window, "scroll", alMoverse, { passive: true });
        this.limpiezas.push(() => {
            observador.disconnect();
            clearTimeout(this.relojSeccion);
        });
    }

    /** La pose de la sección en pantalla, cuando toca: la sección tiene que quedarse un momento (al pasar rápido, cuenta
     * donde se detiene) y entre dos cambios pasan al menos ``MIN_ENTRE_CAMBIOS_MS``. */
    programarPoseDeSeccion() {
        clearTimeout(this.relojSeccion);
        const activa = this.seMovio && this.laQueToca();
        if (!activa) {
            return;
        }
        const espera = Math.max(ESTABLE_MS, this.ultimoCambio + MIN_ENTRE_CAMBIOS_MS - Date.now());
        this.relojSeccion = setTimeout(() => this.ponerPoseDeSeccion(), espera);
    }

    /** Las que ya tienen la pose de ahora cuentan como mostradas (si no, al cambiar volvería a ellas). */
    laQueToca() {
        if (!this.visibles) {
            return null;
        }
        for (const s of this.visibles) {
            if (s.pose === this.poseBurbuja) {
                this.mostradas.add(s);
            }
        }
        return seccionActiva(this.visibles, this.mostradas, this.poseBurbuja);
    }

    ponerPoseDeSeccion() {
        const activa = this.laQueToca();
        if (!activa) {
            return;
        }
        // Con el chat abierto o la burbuja apartada no cambia: al cerrarse o volver, se pone al día (``programar…``).
        if (this.estado.abierto || this.burbuja.hidden || this.burbuja.classList.contains("o_dcbt_aparte") || reducir()) {
            return;
        }
        if (Date.now() - this.ultimoCambio < MIN_ENTRE_CAMBIOS_MS) {
            this.programarPoseDeSeccion();
            return;
        }
        this.burbuja.getAnimations().forEach((a) => a.cancel());   // el reposo no va encima de una transición
        this.poseBurbuja = activa.pose;
        this.ultimoCambio = Date.now();
        for (const s of this.visibles) {
            if (s.pose === activa.pose) {
                this.mostradas.add(s);
            }
        }
        guardarAlmacen(CLAVE_POSE, activa.pose);   // la página siguiente llega con esta
        this.cambiarPose(this.burbujaPose, activa.pose, TRANS_DE_POSE[activa.pose]);
        this.programarPoseDeSeccion();   // si en la franja queda otra (una fila, dos columnas), le toca después
    }

    /** La pose de Brian dentro del chat (el avatar de la cabecera y de los mensajes nuevos). */
    pose(p) {
        if (!POSES.includes(p) || this.estado.pose === p) {
            return;
        }
        this.estado.pose = p;
        if (this.cabPose) {
            this.cambiarPose(this.cabPose, p, TRANS_DE_POSE[p]);
        }
    }

    reposo() {
        if (this.estado.abierto || this.burbuja.hidden || reducir() || !this.burbuja.animate || this.burbuja.classList.contains("o_dcbt_aparte")) {
            return;
        }
        if (Date.now() - (this.ultimoCambio || 0) < 1800) {
            return;   // está cambiando de pose: el reposo, en la vuelta siguiente
        }
        const actual = this.burbujaPose.querySelector("img.o_dcbt_img_pose:not(.o_dcbt_saliendo)");
        const dormido = actual && actual.dataset.pose === "durmiendo";
        const turnos = ["sacudida", "flotar", "saludo", "brinco", "sacudida", "latido"];
        this.reposoN = (this.reposoN || 0) + 1;
        const tipo = dormido ? "flotar" : turnos[(this.reposoN - 1) % turnos.length];
        const r = REPOSO[tipo];
        this.burbuja.animate(r.k, { duration: dormido ? r.d * 1.8 : r.d, easing: r.e || "ease-in-out" });
        if (!this.yaAbrio && this.reposoN <= 3) {
            this.burbuja.classList.remove("o_dcbt_halo");
            void this.burbuja.offsetWidth;
            this.burbuja.classList.add("o_dcbt_halo");
        }
    }

    // ------------------------------------------------------------------ la burbuja y la página

    /** Sube la burbuja sobre la barra fija de la ficha (celular) y la aparta de los botones que taparía. */
    vigilarBotonesDeLaPagina() {
        let pendiente = false;
        const revisar = () => {
            pendiente = false;
            this.acomodarBurbuja();
        };
        const programar = () => {
            if (!pendiente) {
                pendiente = true;
                window.requestAnimationFrame(revisar);
            }
        };
        this.escuchar(window, "scroll", programar, { passive: true });
        this.escuchar(window, "resize", programar, { passive: true });
        const barra = document.querySelector("#o_wsale_cta_wrapper");
        if (barra && window.ResizeObserver) {
            const observador = new window.ResizeObserver(programar);
            observador.observe(barra);
            this.limpiezas.push(() => observador.disconnect());
        }
        programar();
    }

    acomodarBurbuja() {
        const barra = document.querySelector("#o_wsale_cta_wrapper");
        let abajo = "";
        if (barra && window.getComputedStyle(barra).position === "fixed" && barra.offsetHeight) {
            abajo = `${Math.ceil(barra.getBoundingClientRect().height) + 12}px`;
        }
        if (abajo) {
            this.raiz.style.setProperty("--o-dcbt-abajo", abajo);
        } else {
            this.raiz.style.removeProperty("--o-dcbt-abajo");
        }
        if (this.estado.abierto || this.burbuja.hidden) {
            return;
        }
        // Dónde está la burbuja sin moverse (su transform no cuenta): esquina de abajo a la derecha de la ventana.
        const estilo = window.getComputedStyle(this.burbuja);
        const lado = this.burbuja.offsetWidth;
        const ancho = document.documentElement.clientWidth;
        const alto = window.innerHeight;
        const derecha = ancho - (parseFloat(estilo.right) || 0);
        const fondo = alto - (parseFloat(estilo.bottom) || 0);
        const caja = { left: derecha - lado - 8, right: derecha + 8, top: fondo - lado - 8, bottom: fondo + 8 };
        let tapa = false;
        for (const boton of document.querySelectorAll(NO_TAPAR)) {
            if (this.raiz.contains(boton)) {
                continue;
            }
            const r = boton.getBoundingClientRect();
            if (r.width && r.height && r.left < caja.right && r.right > caja.left && r.top < caja.bottom && r.bottom > caja.top) {
                tapa = true;
                break;
            }
        }
        const estaba = this.burbuja.classList.contains("o_dcbt_aparte");
        this.burbuja.classList.toggle("o_dcbt_aparte", tapa);
        if (estaba && !tapa) {
            this.programarPoseDeSeccion();   // vuelve con la pose de la sección donde quedó
        }
    }

    // ------------------------------------------------------------------ el panel

    armarPanel() {
        if (this.panel) {
            return;
        }
        this.cabPose = this.cajaPose("o_dcbt_avatar_cab", this.estado.pose);
        this.cabPunto = el("span", { class: "o_dcbt_punto" });
        this.cabTexto = el("span", { text: "Asistente de la tienda" });
        this.cabWa = el("a", {
            class: "o_dcbt_cab_boton", href: this.urlWhatsApp(), target: "_blank", rel: "noopener",
            "aria-label": "Escríbenos por WhatsApp (se abre en otra pestaña)", html: ICO.wa,
        });
        this.btnAmpliar = el("button", { type: "button", class: "o_dcbt_cab_boton", "aria-pressed": "false", "aria-label": esCelular() ? "Ver los productos en cuadrícula" : "Ampliar el chat", html: ICO.ampliar });
        this.btnCerrar = el("button", { type: "button", class: "o_dcbt_cab_boton", "aria-label": "Cerrar el chat", html: ICO.cerrar });
        const cab = el("header", { class: "o_dcbt_cab" }, this.cabPose,
            el("div", { class: "o_dcbt_cab_textos" }, el("h2", { id: "o_dcbt_titulo", text: "D'CASA" }), el("p", { class: "o_dcbt_cab_estado" }, this.cabPunto, this.cabTexto)),
            this.cabWa, this.btnAmpliar, this.btnCerrar);
        this.aviso = el("p", { class: "o_dcbt_aviso", role: "status", hidden: true });
        this.lista = el("div", { class: "o_dcbt_mensajes", role: "log", "aria-live": "polite", "aria-label": "Conversación" },
            el("div", { class: "o_dcbt_intro" }, this.cajaPose("o_dcbt_avatar_intro", "asomado_burbuja"),
                el("p", { class: "o_dcbt_intro_nombre", text: "D'CASA Panamá" }), el("p", { class: "o_dcbt_intro_sub", text: "Muebles y colchones · La Chorrera" })),
            el("p", { class: "o_dcbt_dia" }, el("span", { text: "Hoy" })));
        this.verificando = el("p", { class: "o_dcbt_verificando", hidden: true }, ico("escudo"), el("span", { text: "Conexión segura…" }));
        this.cajaTurnstile = el("div", { class: "o_dcbt_turnstile", hidden: true });
        this.campo = el("textarea", { id: "o_dcbt_texto", name: "texto", rows: "1", placeholder: "Escribe tu mensaje…", enterkeyhint: "send", maxlength: String(MAX_TEXTO) });
        this.btnEnviar = el("button", { type: "submit", class: "o_dcbt_enviar", "aria-label": "Enviar", disabled: true, html: ICO.enviar });
        this.form = el("form", { class: "o_dcbt_composer", autocomplete: "off" },
            el("label", { class: "visually-hidden", for: "o_dcbt_texto", text: "Escribe tu mensaje" }), this.campo, this.btnEnviar);
        this.vitrinaGrid = el("div", { class: "o_dcbt_vitrina_grid" });
        this.vitrinaPie = el("div", { class: "o_dcbt_vitrina_pie" });
        const volver = el("button", { type: "button", class: "o_dcbt_volver o_dcbt_solo_cel" }, ico("izq"), el("span", { text: "Chat" }));
        this.vitrina = el("aside", { class: "o_dcbt_vitrina", "aria-label": "Productos de la conversación" },
            el("div", { class: "o_dcbt_vitrina_cab" }, volver, el("h3", { text: "Productos de esta conversación" })), this.vitrinaGrid, this.vitrinaPie);
        this.velo = el("div", { class: "o_dcbt_velo", "aria-hidden": "true" });
        this.panel = el("div", { id: "o_dcbt_panel", class: "o_dcbt_panel", role: "dialog", "aria-labelledby": "o_dcbt_titulo", hidden: true },
            cab,
            el("div", { class: "o_dcbt_panel_cuerpo" },
                el("div", { class: "o_dcbt_chat_col" }, el("div", { class: "o_dcbt_cuerpo" }, this.aviso, this.lista), this.verificando, this.cajaTurnstile, this.form),
                this.vitrina),
            this.velo);
        this.raiz.append(this.panel);

        this.escuchar(this.btnCerrar, "click", () => this.cerrar());
        this.escuchar(this.btnAmpliar, "click", () => this.ampliar(!this.estado.ampliado));
        this.escuchar(volver, "click", () => this.ampliar(false));
        this.escuchar(this.campo, "input", () => {
            this.autoAlto();
            this.btnEnviar.disabled = !this.campo.value.trim() || this.estado.pausa;
        });
        this.escuchar(this.campo, "keydown", (ev) => {
            if (ev.key === "Enter" && !ev.shiftKey && !ev.isComposing) {
                ev.preventDefault();
                this.form.requestSubmit();
            }
        });
        this.escuchar(this.btnEnviar, "pointerdown", (ev) => {
            if (document.activeElement === this.campo) {
                ev.preventDefault(); // en el celular no se cierra el teclado
            }
        });
        this.escuchar(this.form, "submit", (ev) => {
            ev.preventDefault();
            const texto = this.campo.value.trim().slice(0, MAX_TEXTO);
            if (!texto || this.estado.pausa) {
                return;
            }
            this.campo.value = "";
            this.autoAlto();
            this.btnEnviar.disabled = true;
            this.campo.placeholder = "Escribe tu mensaje…";
            this.enviar({ texto, mostrar: texto });
        });
        this.escuchar(this.panel, "click", (ev) => this.alTocarPanel(ev));
        const vv = window.visualViewport;
        const ajustar = () => this.ajustarAlto();
        if (vv) {
            this.escuchar(vv, "resize", ajustar);
            this.escuchar(vv, "scroll", ajustar);
        }
        this.escuchar(window, "resize", ajustar);
        this.escuchar(window, "offline", () => this.estadoCab());
        this.escuchar(window, "online", () => this.estadoCab());
        this.estadoCab();
    }

    estadoCab(texto, apagado) {
        if (!this.cabTexto) {
            return;
        }
        const sinRed = navigator.onLine === false;
        const fijo = this.estado.pausa ? "En pausa por hoy" : null;
        this.cabTexto.textContent = texto || fijo || (sinRed ? "Sin conexión" : "Asistente de la tienda");
        this.cabPunto.classList.toggle("o_dcbt_apagado", Boolean(apagado || fijo || (!texto && sinRed)));
    }

    ajustarAlto() {
        if (!this.panel) {
            return;
        }
        const vv = window.visualViewport;
        const alto = vv ? vv.height : window.innerHeight;
        this.panel.style.setProperty("--o-dcbt-vv-alto", `${alto}px`);
        this.panel.style.setProperty("--o-dcbt-vv-arriba", `${vv ? vv.offsetTop : 0}px`);
        this.panel.classList.toggle("o_dcbt_teclado", Boolean(vv) && window.innerHeight - alto > 120);
        if (this.estado.abierto && !this.estado.ampliado) {
            this.lista.scrollTop = this.lista.scrollHeight;
        }
    }

    autoAlto() {
        this.campo.style.height = "auto";
        this.campo.style.height = `${Math.min(Math.max(this.campo.scrollHeight + 2, 48), 128)}px`;
    }

    geometria() {
        const rb = this.burbuja.getBoundingClientRect();
        const rp = this.panel.getBoundingClientRect();
        const cx = rb.left + rb.width / 2 - rp.left;
        const cy = rb.top + rb.height / 2 - rp.top;
        return { cx, cy, r0: rb.width / 2, R: Math.hypot(Math.max(cx, rp.width - cx), Math.max(cy, rp.height - cy)) + 4 };
    }

    abrir({ sinAnimar = false } = {}) {
        if (this.estado.abierto) {
            return;
        }
        this.armarPanel();
        if (this.restaurado) {
            this.restaurar(this.restaurado);
            this.restaurado = null;
        }
        this.estado.abierto = true;
        this.yaAbrio = true;
        this.burbuja.classList.remove("o_dcbt_halo", "o_dcbt_aparte");
        this.burbuja.classList.add("o_dcbt_ya_entro");
        this.burbuja.setAttribute("aria-expanded", "true");
        this.panel.hidden = false;
        if (esCelular()) {
            document.documentElement.classList.add("o_dcbt_abierto");
        }
        this.ajustarAlto();
        if (!sinAnimar && !reducir() && this.panel.animate) {
            const g = this.geometria();
            this.panel.animate([{ clipPath: `circle(${g.r0}px at ${g.cx}px ${g.cy}px)` }, { clipPath: `circle(${g.R}px at ${g.cx}px ${g.cy}px)` }], { duration: 480, easing: B });
            this.velo.animate([{ opacity: 1 }, { opacity: 1, offset: 0.3 }, { opacity: 0 }], { duration: 480, easing: "ease-out" });
            this.burbuja.classList.add("o_dcbt_abriendo");
            this.animBurbuja = this.burbuja.animate([{ opacity: 1, transform: "scale(1)" }, { opacity: 0, transform: "scale(1.25)" }], { duration: 220, easing: "ease-in", fill: "forwards" });
            this.animBurbuja.finished.then(() => {
                this.burbuja.classList.remove("o_dcbt_abriendo");
                if (this.estado.abierto) {
                    this.burbuja.hidden = true;
                }
            }).catch(() => this.burbuja.classList.remove("o_dcbt_abriendo"));
        } else {
            this.burbuja.hidden = true;
        }
        this.alFinal();
        if (!sinAnimar) {
            if (window.matchMedia("(hover: hover) and (pointer: fine)").matches && !this.campo.disabled) {
                this.campo.focus({ preventScroll: true });
            } else {
                this.btnCerrar.focus({ preventScroll: true });
            }
        }
        this.guardar();
        this.saludar();
    }

    cerrar() {
        if (!this.estado.abierto) {
            return;
        }
        this.estado.abierto = false;
        this.guardar();
        this.burbuja.setAttribute("aria-expanded", "false");
        document.documentElement.classList.remove("o_dcbt_abierto");
        if (this.animBurbuja) {
            this.animBurbuja.cancel();
            this.animBurbuja = null;
        }
        this.burbuja.hidden = false;
        const terminar = () => {
            this.panel.hidden = true;
            if (this.estado.ampliado) {
                this.ampliar(false, true);
            }
            if (!reducir() && this.burbuja.animate) {
                this.burbuja.animate([{ opacity: 0, transform: "scale(.7)" }, { opacity: 1, transform: "scale(1.06)", offset: 0.7 }, { opacity: 1, transform: "scale(1)" }], { duration: 320, easing: B });
            }
            this.burbuja.focus({ preventScroll: true });
            this.acomodarBurbuja();
            this.programarPoseDeSeccion();
            if (this.estado.carritoCambio && this.pagina.tipo === "carrito") {
                window.location.reload(); // la página del carrito se pone al día con lo que cambió en el chat
            }
        };
        if (reducir() || !this.panel.animate) {
            terminar();
            return;
        }
        this.burbuja.style.opacity = "0";
        const g = this.geometria();
        const animVelo = this.velo.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 200, fill: "forwards" });
        const fin = () => {
            animVelo.cancel();
            this.burbuja.style.opacity = "";
            terminar();
        };
        this.panel.animate([{ clipPath: `circle(${g.R}px at ${g.cx}px ${g.cy}px)` }, { clipPath: `circle(${g.r0}px at ${g.cx}px ${g.cy}px)` }], { duration: 340, easing: "cubic-bezier(.5, 0, .75, 0)" }).finished.then(fin, fin);
    }

    alTeclado(ev) {
        if (ev.key !== "Escape" || !this.estado.abierto) {
            return;
        }
        if (this.estado.ampliado) {
            this.ampliar(false);
        } else {
            this.cerrar();
        }
    }

    ampliar(si, sinAnimar = false) {
        if (this.estado.ampliado === si || !this.panel) {
            return;
        }
        const antes = this.panel.getBoundingClientRect();
        this.estado.ampliado = si;
        this.panel.classList.toggle("o_dcbt_ampliado", si);
        this.btnAmpliar.setAttribute("aria-pressed", String(si));
        this.btnAmpliar.setAttribute("aria-label", si ? "Volver al tamaño normal" : esCelular() ? "Ver los productos en cuadrícula" : "Ampliar el chat");
        this.btnAmpliar.innerHTML = si ? ICO.reducir : ICO.ampliar;
        this.pintarVitrina();
        if (sinAnimar || reducir() || !this.panel.animate) {
            if (!si) {
                this.alFinal();
            }
            return;
        }
        if (!esCelular()) {
            const despues = this.panel.getBoundingClientRect();
            this.panel.animate([{ width: `${antes.width}px`, height: `${antes.height}px` }, { width: `${despues.width}px`, height: `${despues.height}px` }], { duration: 380, easing: B });
            if (si) {
                this.vitrina.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 420, delay: 120, fill: "backwards" });
            }
        } else {
            const nodo = si ? this.vitrina : this.panel.querySelector(".o_dcbt_chat_col");
            nodo.animate([{ transform: si ? "translateX(30%)" : "translateX(-30%)", opacity: 0 }, { transform: "none", opacity: 1 }], { duration: 300, easing: B });
            if (!si) {
                this.alFinal();
            }
        }
    }

    // ------------------------------------------------------------------ pintar mensajes

    alFinal() {
        if (this.lista) {
            this.lista.scrollTo({ top: this.lista.scrollHeight, behavior: reducir() ? "auto" : "smooth" });
        }
    }

    filaBrian(contenido, clase) {
        const seguida = this.estado.autor === "brian" && this.estado.posePrevia === this.estado.pose;
        const fila = el("div", { class: ["o_dcbt_fila o_dcbt_de_brian o_dcbt_entra", seguida ? "o_dcbt_seguida" : "", clase || ""].filter(Boolean).join(" ") });
        fila.append(this.cajaPose("o_dcbt_avatar", this.estado.pose), contenido);
        this.lista.append(fila);
        this.estado.autor = "brian";
        this.estado.posePrevia = this.estado.pose;
        this.alFinal();
        return fila;
    }

    globo(texto) {
        return this.filaBrian(el("p", { class: "o_dcbt_globo", text: String(texto || "").slice(0, 2000) }));
    }

    cliente(texto) {
        const fila = el("div", { class: "o_dcbt_fila o_dcbt_del_cliente o_dcbt_entra" }, el("p", { class: "o_dcbt_globo", text: texto }));
        this.lista.append(fila);
        this.estado.autor = "cliente";
        this.alFinal();
        return fila;
    }

    escribiendo() {
        const antes = [this.estado.autor, this.estado.posePrevia];
        const fila = this.filaBrian(el("div", { class: "o_dcbt_globo o_dcbt_escribiendo" }, el("i"), el("i"), el("i"), el("span", { class: "visually-hidden", text: "Brian está escribiendo" })));
        return () => {
            fila.remove();
            [this.estado.autor, this.estado.posePrevia] = antes;
        };
    }

    chips(opciones, conIconos = {}) {
        const validas = (opciones || []).filter((o) => typeof o === "string" && o.trim()).slice(0, 6);
        if (!validas.length) {
            return;
        }
        const cont = el("div", { class: "o_dcbt_chips o_dcbt_entra", role: "group", "aria-label": "Respuestas rápidas" });
        for (const texto of validas) {
            cont.append(el("button", { type: "button", class: "o_dcbt_chip", "data-chip": texto.slice(0, 80) }, conIconos[texto] ? ico(conIconos[texto]) : null, el("span", { text: texto.slice(0, 80) })));
        }
        this.lista.append(cont);
        this.alFinal();
    }

    quitarChips() {
        this.lista.querySelectorAll(".o_dcbt_chips").forEach((c) => c.remove());
    }

    lineaPrivacidad() {
        this.lista.append(el("p", { class: "o_dcbt_privacidad o_dcbt_entra" }, ico("escudo"), el("span", { text: "Tu ubicación solo se usa para calcular el envío y no se guarda." })));
        this.alFinal();
    }

    mostrarAviso(texto) {
        this.aviso.textContent = texto;
        this.aviso.hidden = false;
        clearTimeout(this.avisoT);
        this.avisoT = setTimeout(() => {
            this.aviso.hidden = true;
        }, 4200);
    }

    // ------------------------------------------------------------------ tarjetas de productos

    selectorCantidad(valor, datos, maximo = MAX_CANTIDAD) {
        return el("div", { class: "o_dcbt_paso", role: "group", "aria-label": "Cantidad" },
            el("button", { type: "button", "data-paso": "-1", ...datos, "aria-label": "Uno menos", disabled: valor <= 1, html: ICO.menos }),
            el("output", { text: String(valor), "aria-live": "polite" }),
            el("button", { type: "button", "data-paso": "1", ...datos, "aria-label": "Uno más", disabled: valor >= maximo, html: ICO.mas }));
    }

    enCarrito(productoId) {
        const lineas = (this.estado.carrito && this.estado.carrito.lineas) || [];
        return lineas.find((l) => l.producto_id === productoId) || null;
    }

    botonAgregar(producto) {
        const en = this.enCarrito(producto.producto_id);
        const b = el("button", { type: "button", class: `o_dcbt_btn o_dcbt_btn_agregar ${en ? "o_dcbt_btn_hecho" : "o_dcbt_btn_azul"}`, "data-agregar": String(producto.producto_id) });
        if (en) {
            b.append(ico("check"));
        }
        b.append(el("span", { text: en ? `En tu carrito (${en.cantidad})` : "Agregar al carrito" }));
        return b;
    }

    tarjeta(producto) {
        const [clase, etiqueta] = DISPO[producto.disponibilidad] || DISPO.disponible;
        const url = urlPropia(producto.url) || urlPropia(producto.ruta);
        const [precio, mas] = partirPrecio(producto.precio_texto);
        const ver = url ? el("a", { class: "o_dcbt_btn o_dcbt_btn_borde o_dcbt_btn_ver", href: url, "aria-label": `Ver ${producto.nombre}`, text: "Ver" }) : null;
        const info = el("div", { class: "o_dcbt_tarjeta_info" },
            DISPO[producto.disponibilidad] ? el("span", { class: `o_dcbt_dispo ${clase}`, text: etiqueta }) : null,
            el("h3", { text: producto.nombre }),
            precio ? el("p", { class: "o_dcbt_precio" }, el("strong", { text: precio }), mas ? el("small", { text: mas }) : null) : null);
        if (producto.disponibilidad === "agotado") {
            info.append(el("div", { class: "o_dcbt_tarjeta_fila" },
                el("a", { class: "o_dcbt_btn o_dcbt_btn_borde o_dcbt_btn_preguntar", href: this.urlWhatsApp(`Quiero preguntar por: ${producto.nombre}.`), target: "_blank", rel: "noopener" }, ico("wa"), el("span", { text: "Preguntar" })),
                ver));
        } else if (producto.agregable && producto.producto_id) {
            info.append(el("div", { class: "o_dcbt_tarjeta_fila" }, this.selectorCantidad(1, { "data-tarjeta": "1" }), ver), this.botonAgregar(producto));
        } else if (url) {
            info.append(el("div", { class: "o_dcbt_tarjeta_fila" },
                el("a", { class: "o_dcbt_btn o_dcbt_btn_azul o_dcbt_btn_agregar", href: url, text: "Elegir en la ficha" })));
        }
        const imagen = urlPropia(producto.imagen);
        return el("article", { class: "o_dcbt_tarjeta", role: "listitem", "data-producto": String(producto.producto_id || ""), "data-cant": "1" },
            el("div", { class: "o_dcbt_tarjeta_foto" }, imagen ? el("img", { src: imagen, alt: producto.nombre, width: "240", height: "150", loading: "lazy" }) : null), info);
    }

    /** Lo que se puede pintar de un producto que mandó el Worker (todo validado; sin nombre, no se pinta). */
    static productoValido(p) {
        if (!p || typeof p !== "object" || typeof p.nombre !== "string" || !p.nombre.trim()) {
            return null;
        }
        return {
            producto_id: entero(p.producto_id) && p.producto_id > 0 ? p.producto_id : null,
            plantilla_id: entero(p.plantilla_id) && p.plantilla_id > 0 ? p.plantilla_id : null,
            nombre: p.nombre.trim().slice(0, 160),
            precio_texto: typeof p.precio_texto === "string" ? p.precio_texto.slice(0, 40) : "",
            disponibilidad: ["disponible", "pocas", "agotado"].includes(p.disponibilidad) ? p.disponibilidad : null,
            imagen: typeof p.imagen === "string" ? p.imagen : null,
            url: typeof p.url === "string" ? p.url : null,
            ruta: typeof p.ruta === "string" ? p.ruta : null,
            agregable: p.agregable === true && entero(p.producto_id) > 0,
        };
    }

    carrusel(productos) {
        const lista = (productos || []).map(ChatBrian.productoValido).filter(Boolean).slice(0, 12);
        if (!lista.length) {
            return;
        }
        this.productos = this.productos || new Map();
        const c = el("div", { class: "o_dcbt_carrusel", role: "list", "aria-label": "Productos" });
        for (const p of lista) {
            this.productos.set(String(p.producto_id || p.plantilla_id || p.nombre), p);
            c.append(this.tarjeta(p));
            const clave = String(p.producto_id || p.plantilla_id || p.nombre);
            if (!this.estado.vistos.includes(clave)) {
                this.estado.vistos.push(clave);
            }
        }
        const caja = el("div", { class: "o_dcbt_carrusel_caja" }, c);
        if (lista.length > 1) {
            const flecha = (dir) => el("button", {
                type: "button", class: `o_dcbt_flecha ${dir < 0 ? "o_dcbt_flecha_izq" : "o_dcbt_flecha_der"}`, "aria-label": dir < 0 ? "Ver los anteriores" : "Ver más productos",
                html: dir < 0 ? ICO.izq : ICO.der, onclick: () => c.scrollBy({ left: dir * 246, behavior: reducir() ? "auto" : "smooth" }),
            });
            const izq = flecha(-1);
            const der = flecha(1);
            const actualizar = () => {
                izq.hidden = c.scrollLeft < 8;
                der.hidden = c.scrollLeft + c.clientWidth >= c.scrollWidth - 8;
            };
            c.addEventListener("scroll", actualizar, { passive: true });
            caja.append(izq, der);
            window.requestAnimationFrame(actualizar);
        }
        this.filaBrian(caja, "o_dcbt_ancha");
        this.pintarVitrina();
    }

    // ------------------------------------------------------------------ tarjetas de una sola cosa

    pintarCarritoCard(card) {
        const carrito = this.estado.carrito || { lineas: [], cantidad_total: 0 };
        const hijos = [el("p", { class: "o_dcbt_carrito_cab" }, ico("check", "o_dcbt_check"), el("span", { text: "En tu carrito" }))];
        if (!carrito.lineas.length) {
            hijos.push(el("p", { class: "o_dcbt_carrito_vacio", text: "Tu carrito está vacío." }));
        }
        for (const l of carrito.lineas) {
            const imagen = urlPropia(l.imagen);
            hijos.push(el("div", { class: "o_dcbt_linea_carrito" },
                imagen ? el("img", { src: imagen, alt: "", width: "58", height: "42" }) : el("span"),
                el("p", { class: "o_dcbt_carrito_nombre", text: l.nombre }),
                el("div", { class: "o_dcbt_linea_controles" }, this.selectorCantidad(l.cantidad, { "data-linea": String(l.producto_id) }),
                    el("button", { type: "button", class: "o_dcbt_quitar", "data-quitar": String(l.producto_id), text: "Quitar", "aria-label": `Quitar ${l.nombre}` }),
                    el("span", { class: "o_dcbt_linea_precio", text: partirPrecio(l.subtotal_texto)[0] }))));
        }
        if (carrito.lineas.length) {
            const n = carrito.cantidad_total;
            const [total, mas] = partirPrecio(carrito.total_texto);
            hijos.push(el("div", { class: "o_dcbt_carrito_total" }, el("span", { text: `${n} ${n === 1 ? "artículo" : "artículos"}` }), el("span", null, el("strong", { text: total }), mas ? el("small", { text: ` ${mas}` }) : null)),
                el("div", { class: "o_dcbt_carrito_botones" },
                    el("a", { class: "o_dcbt_btn o_dcbt_btn_azul", href: "/shop/cart" }, ico("carrito"), el("span", { text: "Ver mi carrito" })),
                    el("a", { class: "o_dcbt_btn o_dcbt_btn_borde", href: `${RUTA}/carrito/cotizacion.pdf`, download: "cotizacion-dcasa.pdf" }, ico("pdf"), el("span", { text: "Descargar cotización (PDF)" }))));
        }
        card.replaceChildren(...hijos);
    }

    tarjetaCarrito() {
        const card = el("div", { class: "o_dcbt_card", "data-carrito": "" });
        this.pintarCarritoCard(card);
        this.filaBrian(card);
    }

    tarjetaEnvio(bloque) {
        const texto = typeof bloque.texto === "string" ? bloque.texto : "";
        if (!texto) {
            return;
        }
        this.filaBrian(el("div", { class: "o_dcbt_card" },
            el("p", { class: "o_dcbt_envio_eti" }, ico("camion"), el("span", { text: "Envío desde la tienda" })),
            typeof bloque.lugar === "string" && bloque.lugar ? el("h3", { text: bloque.lugar.slice(0, 120) }) : null,
            el("p", { class: "o_dcbt_envio_texto", text: texto.slice(0, 1200) }),
            el("p", { class: "o_dcbt_osm", text: "Datos de mapas © colaboradores de OpenStreetMap" })));
    }

    urlWhatsApp(extra, mensaje) {
        if (!this.whatsapp) {
            return "/whatsapp";
        }
        const texto = typeof mensaje === "string" && mensaje.trim() ? mensaje.trim().slice(0, 600) : mensajeWhatsApp(this.estado.carrito, extra);
        return `https://wa.me/${this.whatsapp}?text=${encodeURIComponent(texto)}`;
    }

    tarjetaWA(bloque = {}) {
        const numero = this.whatsapp ? `+${this.whatsapp.replace(/^507(\d{4})(\d{4})$/, "507 $1-$2")}` : "";
        this.filaBrian(el("div", { class: "o_dcbt_wa_card" },
            el("a", { class: "o_dcbt_btn o_dcbt_btn_azul o_dcbt_btn_grande", href: this.urlWhatsApp(null, bloque.mensaje), target: "_blank", rel: "noopener" }, ico("wa"), el("span", { text: "Escríbenos por WhatsApp" })),
            numero ? el("p", { class: "o_dcbt_wa_num" }, el("span", { text: numero }), el("span", { text: " · se abre en otra pestaña" })) : null));
    }

    tarjetaEstrellas() {
        const fila = el("div", { class: "o_dcbt_estrellas", role: "group", "aria-label": "Califica la atención" });
        for (let i = 1; i <= 5; i++) {
            fila.append(el("button", { type: "button", class: "o_dcbt_estrella", "data-estrellas": String(i), "aria-label": `${i} ${i === 1 ? "estrella" : "estrellas"}`, html: ICO.estrella }));
        }
        this.filaBrian(el("div", { class: "o_dcbt_card" }, fila));
    }

    tarjetaFicha(url, texto) {
        const destino = urlPropia(url);
        if (destino) {
            this.filaBrian(el("div", { class: "o_dcbt_wa_card" }, el("a", { class: "o_dcbt_btn o_dcbt_btn_borde o_dcbt_btn_grande", href: destino, text: texto || "Ver la ficha" })));
        }
    }

    // ------------------------------------------------------------------ la vitrina (chat ampliado)

    pintarVitrina() {
        if (!this.estado.ampliado || !this.vitrinaGrid) {
            this.pintarPieVitrina();
            return;
        }
        const vistos = this.estado.vistos.map((clave) => this.productos && this.productos.get(clave)).filter(Boolean);
        if (!vistos.length) {
            const vacia = el("div", { class: "o_dcbt_vitrina_vacia" }, this.cajaPose("", "con_laptop"), el("p", { text: "Aquí verás, en cuadrícula, los productos que te muestre Brian." }));
            const chips = el("div", { class: "o_dcbt_chips", style: "margin:0;justify-content:center" });
            for (const t of ["Colchones", "Salas"]) {
                chips.append(el("button", { type: "button", class: "o_dcbt_chip", "data-chip": t, text: t }));
            }
            vacia.append(chips);
            this.vitrinaGrid.replaceChildren(vacia);
        } else {
            this.vitrinaGrid.replaceChildren(...vistos.map((p) => this.tarjeta(p)));
        }
        this.pintarPieVitrina();
    }

    pintarPieVitrina() {
        if (!this.vitrinaPie) {
            return;
        }
        const carrito = this.estado.carrito;
        if (!carrito || !carrito.lineas.length) {
            this.vitrinaPie.replaceChildren(el("span", { class: "o_dcbt_resumen", text: "Tu carrito está vacío." }));
            return;
        }
        const n = carrito.cantidad_total;
        const [total, mas] = partirPrecio(carrito.total_texto);
        this.vitrinaPie.replaceChildren(
            el("span", { class: "o_dcbt_resumen" }, `${n} ${n === 1 ? "artículo" : "artículos"} · `, el("strong", { text: total }), mas ? el("small", { text: ` ${mas}` }) : null),
            el("a", { class: "o_dcbt_btn o_dcbt_btn_azul", href: "/shop/cart" }, ico("carrito"), el("span", { text: "Ver mi carrito" })),
            el("a", { class: "o_dcbt_btn o_dcbt_btn_borde", href: `${RUTA}/carrito/cotizacion.pdf`, download: "cotizacion-dcasa.pdf" }, ico("pdf"), el("span", { text: "Cotización (PDF)" })));
    }

    // ------------------------------------------------------------------ el carrito (el de Odoo, con la sesión del visitante)

    ponerCarrito(carrito, salta) {
        if (!carrito || !Array.isArray(carrito.lineas)) {
            return;
        }
        this.estado.carrito = carrito;
        const n = Number(carrito.cantidad_total) || 0;
        try {
            window.sessionStorage.setItem("website_sale_cart_quantity", String(n));
        } catch {
            // nada
        }
        for (const globo of document.querySelectorAll(".my_cart_quantity")) {
            globo.textContent = String(n);
            globo.classList.toggle("d-none", n === 0);
            if (salta && n && !reducir()) {
                globo.animate([{ transform: "scale(.4)" }, { transform: "scale(1.25)", offset: 0.6 }, { transform: "scale(1)" }], { duration: 500, easing: B });
            }
        }
        if (n) {
            document.querySelectorAll("li.o_wsale_my_cart").forEach((li) => li.classList.remove("d-none"));
        }
        if (this.panel) {
            this.panel.querySelectorAll("[data-agregar]").forEach((b) => {
                const p = this.productos && this.productos.get(b.dataset.agregar);
                if (p) {
                    b.replaceWith(this.botonAgregar(p));
                }
            });
            this.lista.querySelectorAll("[data-carrito]").forEach((card) => this.pintarCarritoCard(card));
            this.pintarPieVitrina();
            this.cabWa.href = this.urlWhatsApp();
        }
    }

    carritoParaWorker() {
        const c = this.estado.carrito;
        if (!c || !c.lineas.length) {
            return null;
        }
        return { lineas: c.lineas.slice(0, 20).map((l) => ({ producto_id: l.producto_id, nombre: l.nombre, cantidad: l.cantidad })), total_texto: c.total_texto };
    }

    async cargarCarrito() {
        const r = await this.odoo("GET", `${RUTA}/carrito`);
        if (r.ok && r.carrito) {
            this.ponerCarrito(r.carrito, false);
        }
    }

    // ------------------------------------------------------------------ la red: Odoo

    async csrf(forzar = false) {
        if (this.token && !forzar) {
            return this.token;
        }
        try {
            // Las páginas guardadas en el borde traen el token de otra sesión: uno fresco de la de este visitante.
            const r = await fetch("/dcasa/borde/csrf", { credentials: "same-origin", cache: "no-store", headers: { Accept: "application/json" } });
            if (r.ok) {
                const datos = await r.json();
                if (datos && datos.csrf_token) {
                    this.token = datos.csrf_token;
                    if (window.odoo) {
                        window.odoo.csrf_token = datos.csrf_token;
                    }
                    return this.token;
                }
            }
        } catch {
            // sin dcasa_tienda_borde o sin red: el de la página
        }
        this.token = (window.odoo && window.odoo.csrf_token) || "";
        return this.token;
    }

    async odoo(metodo, ruta, cuerpo, reintento = true) {
        try {
            const opciones = { method: metodo, credentials: "same-origin", cache: "no-store", headers: { Accept: "application/json" } };
            if (metodo === "POST") {
                opciones.headers["Content-Type"] = "application/json";
                opciones.headers["X-CSRF-Token"] = await this.csrf();
                opciones.body = JSON.stringify(cuerpo || {});
            }
            const r = await fetch(ruta, opciones);
            const datos = await r.json().catch(() => ({}));
            if (r.status === 403 && datos && datos.motivo === "csrf" && reintento) {
                await this.csrf(true);
                return this.odoo(metodo, ruta, cuerpo, false);
            }
            return datos && typeof datos === "object" ? datos : { ok: false, motivo: "fallo" };
        } catch {
            return { ok: false, motivo: "red" };
        }
    }

    // ------------------------------------------------------------------ el pase (y Turnstile, si el sitio lo tiene)

    async asegurarPase(forzar = false) {
        const guardado = leerAlmacen(CLAVE_PASE);
        const ahora = Date.now() / 1000;
        if (!forzar && guardado && guardado.pase && guardado.vence - ahora > 120) {
            return guardado;
        }
        guardarAlmacen(CLAVE_PASE, null);
        this.verificando.hidden = false;
        try {
            let turnstile = "";
            if (this.raiz.dataset.turnstile) {
                turnstile = await this.tokenTurnstile();
            }
            const r = await this.odoo("POST", `${RUTA}/pase`, { turnstile });
            if (!r.ok || typeof r.pase !== "string" || typeof r.worker !== "string") {
                return { ok: false, motivo: r.motivo || "fallo" };
            }
            const pase = { ok: true, pase: r.pase, worker: r.worker.replace(/\/+$/, ""), vence: ahora + (Number(r.vence_en) || 1800), noche: Boolean(r.noche), horario_texto: typeof r.horario_texto === "string" ? r.horario_texto : "" };
            guardarAlmacen(CLAVE_PASE, pase);
            return pase;
        } finally {
            this.verificando.hidden = true;
        }
    }

    tokenTurnstile() {
        const clave = this.raiz.dataset.turnstile;
        return new Promise((resolver) => {
            let listo = false;
            const fin = (token) => {
                if (!listo) {
                    listo = true;
                    this.cajaTurnstile.hidden = true;
                    this.cajaTurnstile.replaceChildren();
                    resolver(token || "");
                }
            };
            const pintar = () => {
                try {
                    this.cajaTurnstile.hidden = false;
                    window.turnstile.render(this.cajaTurnstile, { sitekey: clave, callback: fin, "error-callback": () => fin(""), "expired-callback": () => fin("") });
                } catch {
                    fin("");
                }
            };
            setTimeout(() => fin(""), 20000);
            if (window.turnstile) {
                pintar();
                return;
            }
            const script = document.createElement("script");
            script.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
            script.async = true;
            script.onload = pintar;
            script.onerror = () => fin("");
            document.head.append(script);
        });
    }

    // ------------------------------------------------------------------ la red: el Worker

    async worker(cuerpo, reintento = true) {
        const pase = await this.asegurarPase();
        if (!pase.ok) {
            return pase;
        }
        const control = window.AbortController ? new AbortController() : null;
        const plazo = setTimeout(() => control && control.abort(), PLAZO_WORKER_MS);
        try {
            const r = await fetch(`${pase.worker}/tienda/v1/mensaje`, {
                method: "POST", mode: "cors", credentials: "omit", cache: "no-store", signal: control ? control.signal : undefined,
                headers: { Authorization: `Pase ${pase.pase}`, "Content-Type": "application/json" },
                body: JSON.stringify(cuerpo),
            });
            const datos = await r.json().catch(() => ({ ok: false, motivo: "fallo" }));
            if ((r.status === 401 || datos.motivo === "pase") && reintento) {
                guardarAlmacen(CLAVE_PASE, null); // con un pase rechazado, uno nuevo y otra vez (una sola)
                const nuevo = await this.asegurarPase(true);
                if (!nuevo.ok) {
                    return nuevo;
                }
                return this.worker(cuerpo, false);
            }
            return datos && typeof datos === "object" ? datos : { ok: false, motivo: "fallo" };
        } catch {
            return { ok: false, motivo: "fallo" };
        } finally {
            clearTimeout(plazo);
        }
    }

    // ------------------------------------------------------------------ la conversación

    enCola(fn) {
        this.cola = this.cola.then(fn).catch(() => {});
        return this.cola;
    }

    /** Un turno: el visitante dice o toca algo y Brian contesta. ``mostrar``: lo que sale en el globo del visitante. */
    enviar({ texto = null, accion = null, ubicacion = null, mostrar = null }) {
        if (this.estado.pausa) {
            this.mostrarAviso("Por hoy el chat está en pausa. Escríbenos por WhatsApp.");
            return Promise.resolve();
        }
        if (this.estado.ampliado && esCelular()) {
            this.ampliar(false);
        }
        this.quitarChips();
        const fila = mostrar ? this.cliente(mostrar) : null;
        if (mostrar) {
            this.anotar({ tipo: "cliente", texto: mostrar });
        }
        return this.enCola(() => this.turno({ texto, accion, ubicacion }, fila));
    }

    async turno(datos, fila) {
        if (navigator.onLine === false) {
            this.fallo(fila, datos);
            return;
        }
        const quitar = this.escribiendo();
        const cuerpo = { texto: datos.texto, accion: datos.accion, pagina: this.pagina, carrito: this.carritoParaWorker(), ubicacion: datos.ubicacion };
        const r = await this.worker(cuerpo);
        quitar();
        if (!r.ok) {
            this.sinRespuesta(r.motivo, fila, datos);
            return;
        }
        await this.pintarRespuesta(r);
        this.anotar({ tipo: "respuesta", datos: r });
    }

    async pintarRespuesta(r, restaurando = false) {
        if (typeof r.pose === "string") {
            this.pose(r.pose);
        }
        const propuestas = [];
        let primero = true;
        for (const b of Array.isArray(r.bloques) ? r.bloques.slice(0, 20) : []) {
            if (!b || typeof b !== "object") {
                continue;
            }
            if (!primero && !restaurando && b.tipo === "texto") {
                await pausa(260);
            }
            primero = false;
            if (b.tipo === "texto" && typeof b.texto === "string" && b.texto.trim()) {
                this.globo(b.texto);
            } else if (b.tipo === "productos") {
                this.carrusel(b.productos);
            } else if (b.tipo === "proponer_carrito") {
                propuestas.push(b);
            } else if (b.tipo === "sugerencias") {
                if (typeof b.texto === "string" && b.texto.trim()) {
                    this.globo(b.texto);
                }
                this.chips(b.opciones);
            } else if (b.tipo === "ubicacion") {
                if (typeof b.texto === "string" && b.texto.trim()) {
                    this.globo(b.texto);
                }
                this.chips(["Usar mi ubicación actual", "Es otra dirección"], { "Usar mi ubicación actual": "mira", "Es otra dirección": "lapiz" });
                this.lineaPrivacidad();
            } else if (b.tipo === "envio") {
                this.tarjetaEnvio(b);
            } else if (b.tipo === "whatsapp") {
                this.tarjetaWA(b);
            } else if (b.tipo === "calificar") {
                this.tarjetaEstrellas();
            } else if (b.tipo === "carrito") {
                this.tarjetaCarrito();
            }
        }
        if (Array.isArray(r.chips)) {
            this.chips(r.chips);
        }
        if (!restaurando) {
            for (const propuesta of propuestas.slice(0, 1)) {
                await this.aplicarPropuesta(propuesta);
            }
        }
    }

    /** Brian propuso agregar (porque el visitante lo pidió o confirmó): se aplica en Odoo y se le cuenta qué pasó. */
    async aplicarPropuesta(b) {
        const productoId = entero(b.producto_id);
        const cantidad = entero(b.cantidad);
        if (!productoId || productoId <= 0 || !cantidad || cantidad < 1 || cantidad > MAX_CANTIDAD) {
            return;
        }
        const r = await this.odoo("POST", `${RUTA}/carrito/agregar`, { producto_id: productoId, cantidad });
        const resultado = r.ok ? "ok" : "error";
        if (r.ok) {
            this.estado.carritoCambio = true;
            this.ponerCarrito(r.carrito, true);
        }
        const quitar = this.escribiendo();
        const respuesta = await this.worker({ texto: null, accion: { tipo: "confirmar_carrito", producto_id: productoId, cantidad, resultado }, pagina: this.pagina, carrito: this.carritoParaWorker(), ubicacion: null });
        quitar();
        if (respuesta.ok) {
            await this.pintarRespuesta({ ...respuesta, bloques: (respuesta.bloques || []).filter((x) => x && x.tipo !== "proponer_carrito") });
            this.anotar({ tipo: "respuesta", datos: { ...respuesta, bloques: (respuesta.bloques || []).filter((x) => x && x.tipo !== "proponer_carrito") } });
        } else if (r.ok) {
            this.globo("Listo, te lo puse en el carrito. Gracias por escogernos.");
            this.anotar({ tipo: "brian", texto: "Listo, te lo puse en el carrito. Gracias por escogernos." });
        }
        if (r.ok) {
            this.tarjetaCarrito();
            this.anotar({ tipo: "carrito" });
        } else if (r.motivo === "elegir" && r.url) {
            this.tarjetaFicha(r.url, "Elegir en la ficha");
            this.anotar({ tipo: "ficha", url: r.url });
        }
    }

    /** «Agregar al carrito» de una tarjeta: lo pidió el visitante; Odoo lo aplica y la página lo cuenta (sin IA). */
    async agregarDesdeTarjeta(producto, cantidad) {
        const texto = "Agregar al carrito: " + (cantidad > 1 ? cantidad + " × " : "") + producto.nombre;
        this.quitarChips();
        this.cliente(texto);
        this.anotar({ tipo: "cliente", texto });
        await this.enCola(async () => {
            const r = await this.odoo("POST", `${RUTA}/carrito/agregar`, { producto_id: producto.producto_id, cantidad });
            if (r.ok) {
                this.estado.carritoCambio = true;
                this.ponerCarrito(r.carrito, true);
                this.pose("bolsita");
                const frase = cantidad > 1 ? `Listo, te puse ${cantidad} en el carrito. Gracias por escogernos.` : "Listo, te lo puse en el carrito. Gracias por escogernos.";
                this.globo(frase);
                this.tarjetaCarrito();
                this.chips(SIGUE_TRAS_AGREGAR);
                this.anotar({ tipo: "brian", texto: frase, pose: "bolsita" }, { tipo: "carrito" }, { tipo: "chips", opciones: SIGUE_TRAS_AGREGAR });
            } else if (r.motivo === "elegir" && r.url) {
                const frase = "Ese mueble tiene opciones para elegir (medida, color o combo): escógela en su ficha y lo agregas desde ahí.";
                this.globo(frase);
                this.tarjetaFicha(r.url, "Elegir en la ficha");
                this.anotar({ tipo: "brian", texto: frase }, { tipo: "ficha", url: r.url });
            } else {
                const frase = r.motivo === "apagado" ? "Ahora el chat no puede agregar al carrito. Escríbenos por WhatsApp y te ayudamos." : "No pude ponerlo en el carrito. Inténtalo otra vez, o escríbenos por WhatsApp y te ayudamos.";
                this.globo(frase);
                this.tarjetaWA({ mensaje: mensajeWhatsApp(this.estado.carrito, `Quiero: ${producto.nombre}.`) });
                this.anotar({ tipo: "brian", texto: frase }, { tipo: "whatsapp", mensaje: mensajeWhatsApp(this.estado.carrito, `Quiero: ${producto.nombre}.`) });
            }
        });
    }

    async cambiarCantidad(productoId, cantidad) {
        const r = await this.odoo("POST", `${RUTA}/carrito/cantidad`, { producto_id: productoId, cantidad: Math.max(0, Math.min(MAX_CANTIDAD, cantidad)) });
        if (r.ok) {
            this.estado.carritoCambio = true;
            this.ponerCarrito(r.carrito, false);
        } else {
            this.mostrarAviso("No pude cambiar la cantidad. Inténtalo otra vez.");
        }
    }

    pedirUbicacion() {
        return new Promise((resolver) => {
            if (!navigator.geolocation) {
                resolver(null);
                return;
            }
            let listo = false;
            const fin = (valor) => {
                if (!listo) {
                    listo = true;
                    resolver(valor);
                }
            };
            setTimeout(() => fin(null), PLAZO_UBICACION_MS);
            try {
                navigator.geolocation.getCurrentPosition(
                    // Con tres decimales (unos 100 m) alcanza para el lugar de entrega más cercano.
                    (p) => fin({ lat: Math.round(p.coords.latitude * 1000) / 1000, lon: Math.round(p.coords.longitude * 1000) / 1000 }),
                    () => fin(null),
                    { enableHighAccuracy: false, timeout: PLAZO_UBICACION_MS - 1000, maximumAge: 300000 });
            } catch {
                fin(null);
            }
        });
    }

    async usarUbicacion() {
        this.quitarChips();
        this.cliente("Usar mi ubicación actual");
        this.anotar({ tipo: "cliente", texto: "Usar mi ubicación actual" });
        const ubicacion = await this.pedirUbicacion();
        if (!ubicacion) {
            const frase = "No pude usar tu ubicación. Escríbeme el barrio, el PH o un punto de referencia que te quede cerca.";
            this.globo(frase);
            this.anotar({ tipo: "brian", texto: frase });
            this.campo.placeholder = "Barrio, PH o un punto de referencia";
            return;
        }
        // La ubicación viaja solo en este turno: no se guarda en la página ni en el historial.
        await this.enviar({ ubicacion });
    }

    otraDireccion() {
        this.quitarChips();
        this.cliente("Es otra dirección");
        const frase = "Claro. Escríbeme el barrio, el PH o un punto de referencia que te quede cerca; no necesito la dirección exacta.";
        this.pose("mapa");
        this.globo(frase);
        this.anotar({ tipo: "cliente", texto: "Es otra dirección" }, { tipo: "brian", texto: frase, pose: "mapa" });
        this.campo.placeholder = "Barrio, PH o un punto de referencia";
        this.campo.focus({ preventScroll: true });
    }

    async calificar(estrellas) {
        const texto = `${estrellas} ${estrellas === 1 ? "estrella" : "estrellas"}`;
        // Odoo guarda solo el número y la fecha; el Worker da las gracias.
        this.odoo("POST", `${RUTA}/calificar`, { estrellas });
        await this.enviar({ accion: { tipo: "calificar", estrellas }, mostrar: texto });
    }

    fallo(fila, datos) {
        if (!fila) {
            this.mostrarAviso("No me llegó tu mensaje, inténtalo otra vez.");
            return;
        }
        fila.classList.add("o_dcbt_fallida");
        const aviso = el("p", { class: "o_dcbt_fallo o_dcbt_entra", role: "alert" }, ico("aviso"), el("span", { text: "No me llegó tu mensaje, inténtalo otra vez." }));
        aviso.append(el("button", {
            type: "button", class: "o_dcbt_reintentar", text: "Reintentar", onclick: () => {
                aviso.remove();
                fila.classList.remove("o_dcbt_fallida");
                this.enCola(() => this.turno(datos, fila));
            },
        }));
        fila.after(aviso);
        this.alFinal();
    }

    /** Lo que se le dice al visitante cuando no hay respuesta de Brian (siempre amable y con WhatsApp). */
    sinRespuesta(motivo, fila, datos) {
        const pausaDelDia = ["tope_dia", "presupuesto"].includes(motivo);
        const apagado = motivo === "apagado";
        if (["fallo", "red"].includes(motivo) || !motivo) {
            this.fallo(fila, datos);
            return;
        }
        const textos = {
            apagado: "Ahora el chat no está disponible. Escríbenos por WhatsApp y te atiende una persona.",
            tope: "Hay muchos chats abiertos desde tu conexión. Inténtalo en un rato o escríbenos por WhatsApp.",
            tope_red: "Hay muchos mensajes desde tu conexión. Inténtalo en un rato o escríbenos por WhatsApp.",
            tope_sesion: "Gracias por escribirnos. Por ahora llegamos al límite de mensajes; en un rato seguimos, o escríbenos por WhatsApp.",
            tope_dia: "Gracias por escribirnos. Por hoy ya no puedo seguir. Escríbenos por WhatsApp y te atiende una persona.",
            presupuesto: "Gracias por escribirnos. Por hoy ya no puedo seguir. Escríbenos por WhatsApp y te atiende una persona.",
            verificacion: "No pude comprobar que la conexión es segura. Inténtalo otra vez o escríbenos por WhatsApp.",
            pase: "No pude comprobar que la conexión es segura. Inténtalo otra vez o escríbenos por WhatsApp.",
        };
        this.pose("burbuja_chat");
        this.globo(textos[motivo] || textos.verificacion);
        this.tarjetaWA();
        if (pausaDelDia || apagado) {
            this.estado.pausa = true;
            this.campo.disabled = true;
            this.campo.value = "";
            this.campo.placeholder = apagado ? "El chat no está disponible" : "Por hoy el chat está en pausa";
            this.btnEnviar.disabled = true;
            this.estadoCab(apagado ? "No disponible" : "En pausa por hoy", true);
        }
    }

    saludar() {
        if (this.estado.saludado) {
            return;
        }
        this.estado.saludado = true;
        this.enCola(async () => {
            const cargando = this.cargarCarrito();
            if (this.historial.length) {
                await cargando;
                return; // la conversación sigue (vino de otra página): Brian no se vuelve a presentar
            }
            const pase = await this.asegurarPase();
            await cargando;
            if (!pase.ok) {
                if (["fallo", "red"].includes(pase.motivo) || !pase.motivo) {
                    // Sin conexión con Odoo: lo dice, ofrece WhatsApp y al volver a abrir lo intenta otra vez.
                    this.estado.saludado = false;
                    this.pose("burbuja_chat");
                    this.globo("Ahora no me puedo conectar. Inténtalo en un momento o escríbenos por WhatsApp.");
                    this.tarjetaWA();
                    return;
                }
                this.sinRespuesta(pase.motivo, null, null);
                return;
            }
            const noche = pase.noche;
            this.noche = noche;
            this.pose(noche ? "durmiendo" : "saludando");
            const quitar = this.escribiendo();
            await pausa(700);
            quitar();
            const saludo = "Hola, soy Brian. ¿Qué buscas hoy?";
            const segundo = noche
                ? "Ahora la tienda está cerrada, pero yo te ayudo con gusto. Si necesitas a una vendedora, te responde por WhatsApp en cuanto abramos" + (pase.horario_texto ? " (atendemos " + pase.horario_texto + ")" : "") + "."
                : "Con gusto te ayudo a encontrar tu mueble, ver precios, calcular el envío o dejarte el carrito listo.";
            this.pose("saludando");
            this.globo(saludo);
            await pausa(500);
            this.globo(segundo);
            this.chips(INICIO);
            this.anotar({ tipo: "brian", texto: saludo, pose: "saludando" }, { tipo: "brian", texto: segundo }, { tipo: "chips", opciones: INICIO });
        });
    }

    // ------------------------------------------------------------------ toques dentro del panel

    alTocarPanel(ev) {
        const objetivo = ev.target.closest("button");
        if (!objetivo || objetivo.classList.contains("o_dcbt_reintentar") || objetivo.classList.contains("o_dcbt_flecha")) {
            return;
        }
        if (objetivo.dataset.chip) {
            const valor = objetivo.dataset.chip;
            if (valor === "Usar mi ubicación actual") {
                this.usarUbicacion();
            } else if (valor === "Es otra dirección") {
                this.otraDireccion();
            } else {
                this.enviar({ accion: { tipo: "chip", valor }, mostrar: valor });
            }
            return;
        }
        if (objetivo.dataset.paso) {
            const d = Number(objetivo.dataset.paso);
            if (objetivo.dataset.tarjeta) {
                const t = objetivo.closest(".o_dcbt_tarjeta");
                const v = Math.min(MAX_CANTIDAD, Math.max(1, Number(t.dataset.cant) + d));
                t.dataset.cant = String(v);
                const paso = objetivo.closest(".o_dcbt_paso");
                paso.querySelector("output").textContent = String(v);
                paso.querySelector('[data-paso="-1"]').disabled = v <= 1;
                paso.querySelector('[data-paso="1"]').disabled = v >= MAX_CANTIDAD;
            } else if (objetivo.dataset.linea) {
                const linea = this.enCarrito(Number(objetivo.dataset.linea));
                if (linea) {
                    this.cambiarCantidad(linea.producto_id, Math.max(1, linea.cantidad + d));
                }
            }
            return;
        }
        if (objetivo.dataset.quitar) {
            this.cambiarCantidad(Number(objetivo.dataset.quitar), 0);
            return;
        }
        if (objetivo.dataset.agregar) {
            const producto = this.productos && this.productos.get(objetivo.dataset.agregar);
            const t = objetivo.closest(".o_dcbt_tarjeta");
            if (producto) {
                this.agregarDesdeTarjeta(producto, Number(t && t.dataset.cant) || 1);
            }
            return;
        }
        if (objetivo.dataset.estrellas) {
            const n = Number(objetivo.dataset.estrellas);
            const grupo = objetivo.closest(".o_dcbt_estrellas");
            if (grupo.dataset.listo) {
                return;
            }
            grupo.dataset.listo = "1";
            grupo.querySelectorAll(".o_dcbt_estrella").forEach((s, i) => {
                s.classList.toggle("o_dcbt_activa", i < n);
                s.disabled = true;
            });
            this.calificar(n);
        }
    }

    // ------------------------------------------------------------------ lo conversado, en este navegador

    anotar(...entradas) {
        this.historial.push(...entradas);
        if (this.historial.length > MAX_HISTORIAL) {
            this.historial.splice(0, this.historial.length - MAX_HISTORIAL);
        }
        this.guardar();
    }

    guardar() {
        guardarAlmacen(CLAVE_CHAT, { historial: this.historial, abierto: this.estado.abierto, pausa: this.estado.pausa, guardado: Date.now() });
    }

    /** Vuelve a pintar lo conversado al llegar a otra página (sin animaciones ni llamadas). */
    restaurar(guardado) {
        if (Date.now() - (guardado.guardado || 0) > 2 * 3600 * 1000) {
            guardarAlmacen(CLAVE_CHAT, null); // como el Worker: a las 2 horas sin actividad se olvida
            return;
        }
        this.historial = guardado.historial.slice(-MAX_HISTORIAL);
        this.estado.saludado = true;
        for (const e of this.historial) {
            if (!e || typeof e !== "object") {
                continue;
            }
            if (e.tipo === "cliente" && typeof e.texto === "string") {
                this.cliente(e.texto);
            } else if (e.tipo === "brian" && typeof e.texto === "string") {
                if (e.pose) {
                    this.pose(e.pose);
                }
                this.globo(e.texto);
            } else if (e.tipo === "respuesta" && e.datos) {
                this.pintarRespuesta(e.datos, true);
            } else if (e.tipo === "carrito") {
                this.tarjetaCarrito();
            } else if (e.tipo === "chips") {
                this.chips(e.opciones);
            } else if (e.tipo === "ficha") {
                this.tarjetaFicha(e.url, "Elegir en la ficha");
            } else if (e.tipo === "whatsapp") {
                this.tarjetaWA({ mensaje: e.mensaje });
            }
        }
        // Lo que ya se calificó no se vuelve a calificar; las sugerencias viejas no se repiten (solo las últimas).
        this.lista.querySelectorAll(".o_dcbt_estrellas").forEach((g) => {
            g.dataset.listo = "1";
            g.querySelectorAll("button").forEach((b) => (b.disabled = true));
        });
        const chips = this.lista.querySelectorAll(".o_dcbt_chips");
        chips.forEach((c, i) => i < chips.length - 1 && c.remove());
        this.lista.querySelectorAll(".o_dcbt_entra").forEach((n) => n.classList.remove("o_dcbt_entra"));
        if (guardado.pausa) {
            this.estado.pausa = true;
            this.campo.disabled = true;
            this.campo.placeholder = "Por hoy el chat está en pausa";
            this.estadoCab();
        }
    }
}

// ---------------------------------------------------------------------------------------------------------------------
// La interacción del sitio (no corre en el editor)
// ---------------------------------------------------------------------------------------------------------------------

export class BrianTienda extends Interaction {
    static selector = "#o_dcasa_brian";

    start() {
        this.chat = new ChatBrian(this.el);
        this.chat.iniciar();
        window.__dcasaBrian = this.chat; // para las pruebas y las capturas
    }

    destroy() {
        if (this.chat) {
            this.chat.destruir();
            this.chat = null;
        }
    }
}

registry.category("public.interactions").add("dcasa_brian_tienda.chat", BrianTienda);
