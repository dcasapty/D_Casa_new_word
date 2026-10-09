/**
 * Ayudas de la pantalla «Conversaciones»: horas de Panamá, tamaños, íconos, colores de etiqueta y errores.
 * Todo es puro (sin Odoo ni OWL) para poder probarlo aparte.
 */

export const ZONA = "America/Panama";

const FORMATO_HORA = new Intl.DateTimeFormat("es-PA", { timeZone: ZONA, hour: "numeric", minute: "2-digit", hour12: true });
const FORMATO_DIA = new Intl.DateTimeFormat("en-CA", { timeZone: ZONA, year: "numeric", month: "2-digit", day: "2-digit" });
const FORMATO_DIA_LARGO = new Intl.DateTimeFormat("es-PA", { timeZone: ZONA, weekday: "long", day: "numeric", month: "long" });
const FORMATO_DIA_CORTO = new Intl.DateTimeFormat("es-PA", { timeZone: ZONA, weekday: "short" });
const FORMATO_FECHA = new Intl.DateTimeFormat("es-PA", { timeZone: ZONA, day: "2-digit", month: "2-digit", year: "2-digit" });
const UN_DIA = 24 * 3600 * 1000;

const aFecha = (iso) => (iso instanceof Date ? iso : new Date(iso));

/** «9:45 a. m.» en la hora de Panamá, sin importar dónde esté la persona. */
export function hora(iso) {
    return iso ? FORMATO_HORA.format(aFecha(iso)).replace(/ /g, " ") : "";
}

/** «2026-10-09»: el día de Panamá de ese instante (sirve para agrupar y comparar días). */
export function claveDia(iso) {
    return FORMATO_DIA.format(aFecha(iso));
}

/** «Hoy», «Ayer» o «miércoles 7 de octubre». */
export function etiquetaDia(iso, ahora = Date.now()) {
    const dia = claveDia(iso);
    if (dia === claveDia(ahora)) {
        return "Hoy";
    }
    if (dia === claveDia(ahora - UN_DIA)) {
        return "Ayer";
    }
    const texto = FORMATO_DIA_LARGO.format(aFecha(iso));
    return texto.charAt(0).toUpperCase() + texto.slice(1);
}

/** Para la lista: la hora si es de hoy, «Ayer», el día de la semana si es de esta semana, y si no, la fecha. */
export function horaDeLista(iso, ahora = Date.now()) {
    if (!iso) {
        return "";
    }
    const dia = claveDia(iso);
    if (dia === claveDia(ahora)) {
        return hora(iso);
    }
    if (dia === claveDia(ahora - UN_DIA)) {
        return "Ayer";
    }
    if (ahora - aFecha(iso).getTime() < 6 * UN_DIA) {
        const corto = FORMATO_DIA_CORTO.format(aFecha(iso)).replace(".", "");
        return corto.charAt(0).toUpperCase() + corto.slice(1);
    }
    return FORMATO_FECHA.format(aFecha(iso));
}

/** «en 1 h 20 min», «en 35 min», «en menos de 1 min» o «ya venció». */
export function enCuanto(iso, ahora = Date.now()) {
    const ms = aFecha(iso).getTime() - ahora;
    if (ms <= 0) {
        return "ya venció";
    }
    const minutos = Math.ceil(ms / 60000);
    if (minutos < 2) {
        return "en menos de 1 min";
    }
    if (minutos < 60) {
        return `en ${minutos} min`;
    }
    const horas = Math.floor(minutos / 60);
    const resto = minutos % 60;
    if (horas < 48) {
        return resto ? `en ${horas} h ${resto} min` : `en ${horas} h`;
    }
    return `en ${Math.round(horas / 24)} días`;
}

/** «jueves 8:00 a. m.», «hoy 3:45 p. m.»: cuándo pasa algo, para frases como «Seguimiento 1 pendiente para…». */
export function cuando(iso, ahora = Date.now()) {
    if (!iso) {
        return "";
    }
    const dia = claveDia(iso);
    if (dia === claveDia(ahora)) {
        return `hoy ${hora(iso)}`;
    }
    if (dia === claveDia(ahora + UN_DIA)) {
        return `mañana ${hora(iso)}`;
    }
    return `${etiquetaDia(iso, ahora).toLowerCase()} ${hora(iso)}`;
}

/** 1536 → «1.5 KB». */
export function tamano(bytes) {
    if (!bytes) {
        return "";
    }
    if (bytes < 1024) {
        return `${bytes} B`;
    }
    if (bytes < 1024 * 1024) {
        return `${(bytes / 1024).toFixed(bytes < 10240 ? 1 : 0)} KB`;
    }
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/** 1250.5 → «1,250.5» (puntos de Socios). */
export function numero(valor) {
    return valor === null || valor === undefined ? "" : new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(valor);
}

/** 349.99 → «$349.99». */
export function dolares(valor) {
    return valor === null || valor === undefined
        ? ""
        : new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(valor);
}

/** «Ana María Pérez» → «AM». */
export function iniciales(nombre) {
    const palabras = String(nombre || "")
        .split(/[\s·]+/)
        .filter((p) => /^[\p{L}\p{N}]/u.test(p));
    return (palabras.slice(0, 2).map((p) => p[0]).join("") || "?").toUpperCase();
}

/** El ícono (Font Awesome 4) de cada canal. */
export const ICONO_DE_CANAL = {
    whatsapp_qr: "fa-whatsapp",
    whatsapp_cloud: "fa-whatsapp",
    telegram: "fa-telegram",
    messenger: "fa-comments",
    instagram: "fa-instagram",
};

export function iconoDeCanal(canal) {
    return ICONO_DE_CANAL[canal] || "fa-comment";
}

/** El ícono de un documento según su tipo. */
export function iconoDeArchivo(mime, nombre) {
    const texto = `${mime || ""} ${nombre || ""}`.toLowerCase();
    if (texto.includes("pdf")) {
        return "fa-file-pdf-o";
    }
    if (/word|\.docx?\b/.test(texto)) {
        return "fa-file-word-o";
    }
    if (/excel|spreadsheet|\.xlsx?\b|\.csv\b/.test(texto)) {
        return "fa-file-excel-o";
    }
    if (texto.includes("image")) {
        return "fa-file-image-o";
    }
    return "fa-file-o";
}

/**
 * Los 12 colores de etiqueta de Odoo (0 a 11), en la paleta de D'CASA: fondos suaves con texto oscuro, todos con
 * contraste AA. Ninguno es amarillo (el amarillo de la marca nunca toca el blanco).
 */
export const COLORES_DE_ETIQUETA = [
    { fondo: "#ECF0F6", texto: "#44506A" },
    { fondo: "#FBE4E4", texto: "#8A1C1C" },
    { fondo: "#FDE9D9", texto: "#8A3B0A" },
    { fondo: "#EFE6D0", texto: "#5C4300" },
    { fondo: "#DCEEF8", texto: "#0B4F73" },
    { fondo: "#E4ECFD", texto: "#0F3591" },
    { fondo: "#DDF2E6", texto: "#13663B" },
    { fondo: "#D9F1EF", texto: "#0C625C" },
    { fondo: "#EBE4F8", texto: "#4B2A8C" },
    { fondo: "#F9E1EE", texto: "#8A1F5B" },
    { fondo: "#0B1F52", texto: "#FFFFFF" },
    { fondo: "#CBD3E1", texto: "#0E1A33" },
];

export function colorDeEtiqueta(numero) {
    return COLORES_DE_ETIQUETA[Number.isInteger(numero) && numero >= 0 && numero < 12 ? numero : 0];
}

/** El texto del error de un llamado al servidor (el mensaje en español que dejó el servidor, si lo hay). */
export function mensajeDeError(error) {
    return (
        error?.data?.message ||
        (typeof error?.message === "string" && !/^(RPC_ERROR|Error)$/.test(error.message) ? error.message : "") ||
        "No se pudo completar. Inténtalo otra vez."
    );
}

/** Une los mensajes nuevos con los que ya había (por id, sin repetir) y los deja del más viejo al más nuevo. */
export function fusionarMensajes(actuales, nuevos) {
    const porId = new Map();
    for (const m of actuales) {
        porId.set(m.id, m);
    }
    for (const m of nuevos) {
        porId.set(m.id, m);
    }
    return [...porId.values()].sort((a, b) => a.id - b.id);
}

/** Si hay un hueco entre lo que ya había y el tramo nuevo (llegaron más mensajes de los que caben en un tramo). */
export function hayHueco(actuales, tramoNuevo, hayMasAntes) {
    if (!actuales.length || !tramoNuevo.length || !hayMasAntes) {
        return false;
    }
    return tramoNuevo[0].id > actuales[actuales.length - 1].id;
}

/** Arma lo que pinta el hilo: separadores de día y mensajes, uno detrás de otro. */
export function elementosDelHilo(mensajes, ahora = Date.now()) {
    const elementos = [];
    let ultimoDia = null;
    for (const m of mensajes) {
        const dia = claveDia(m.ts);
        if (dia !== ultimoDia) {
            elementos.push({ clase: "dia", clave: `dia-${dia}`, texto: etiquetaDia(m.ts, ahora) });
            ultimoDia = dia;
        }
        elementos.push({ clase: "mensaje", clave: `m-${m.id}`, m });
    }
    return elementos;
}

/** Texto de la respuesta rápida que se está escribiendo: «/hor» → «hor»; `null` si no es un atajo. */
export function atajoEnCurso(texto) {
    const coincide = /^\/([a-z0-9_-]{0,30})$/i.exec(texto || "");
    return coincide ? coincide[1].toLowerCase() : null;
}

/** Cuántas horas/minutos hay hasta que el asistente vuelva (para la barra de «Atiendes tú»). */
export function pausaRestante(pausadaHasta, ahora = Date.now()) {
    return pausadaHasta ? enCuanto(pausadaHasta, ahora) : null;
}
