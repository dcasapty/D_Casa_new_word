// @ts-check
// Qué hacer con cada mensaje que Baileys entrega: ¿es de un cliente, lo escribió
// una persona desde el teléfono del negocio, lo mandó el propio puente (eco), o
// no es nada que atender (estados, grupos, historial viejo, reacciones…)?
//
// Heredado del CRM de Baby Caleb (puente-wa/contenedor/propios.mjs) y ampliado:
// ahora también clasifica el contenido (texto, imagen, audio, documento, video…)
// para el contrato con Juan. Vive aparte del socket para probarse sin abrir uno.
//
// Lo que manda el bot contra lo que manda una persona: los dos salen del mismo
// número y los dos le llegan a Baileys como `fromMe`. La diferencia la pone el
// bot: cada envío lleva un id que se genera ANTES de mandarlo y se anota aquí.
// Tiene que ser antes: Baileys emite el eco de lo enviado en el mismo tick en que
// termina `sendMessage`, y anotar el id que devuelve llegaría tarde a su eco.

import { esChatDeUnaPersona, sinDispositivo } from "./numeros.mjs";

/** Cuánto se recuerda un envío del bot. El eco llega en milisegundos; tras un reinicio, en minutos. */
const RECORDAR_ENVIOS_MS = 2 * 60 * 60 * 1000;
const TOPE_DE_ENVIOS = 2000;

/** El registro de ids que mandó el bot. Se poda solo; no crece con los días. */
export function crearRegistroDeEnvios() {
  /** @type {Map<string, number>} */
  const enviados = new Map();
  /**
   * @param {string} id
   * @param {number} ahora
   */
  function anotar(id, ahora = Date.now()) {
    enviados.set(id, ahora);
    for (const [k, t] of enviados) {
      if (ahora - t > RECORDAR_ENVIOS_MS || enviados.size > TOPE_DE_ENVIOS) enviados.delete(k);
      else break;
    }
  }
  return {
    anotar,
    /** Carga ids que el Worker recuerda (sobreviven a un reinicio del contenedor). */
    cargar(/** @type {{ id: string, ts: number }[]} */ lista) {
      for (const { id, ts } of [...lista].sort((a, b) => a.ts - b.ts)) anotar(id, ts);
    },
    tiene: (/** @type {string} */ id) => enviados.has(id),
    get tamano() {
      return enviados.size;
    },
  };
}

/**
 * Cuánto de viejo puede ser un mensaje propio para contar. Al reconectar,
 * WhatsApp entrega (como `append`) lo que la dueña mandó mientras el contenedor
 * estaba caído: eso sí cuenta, si es reciente. Lo de hace horas no pausa nada.
 */
export const RESPUESTA_VIGENTE_MS = 15 * 60 * 1000;

/** Un mensaje de un cliente más viejo que esto no se contesta (historial). */
export const ENTRANTE_VIGENTE_MS = 24 * 60 * 60 * 1000;

/**
 * El contenido del mensaje, sin las envolturas de «temporal» o «ver una vez».
 * @param {any} msg
 * @returns {any}
 */
function interior(msg) {
  const m = msg?.message ?? {};
  return m.ephemeralMessage?.message ?? m.viewOnceMessage?.message ?? m.viewOnceMessageV2?.message ?? m;
}

/**
 * El nombre del tipo de mensaje de Baileys (`conversation`, `imageMessage`…), o null.
 * @param {any} msg
 */
export function tipoDe(msg) {
  return (
    Object.keys(interior(msg)).find(
      (k) => k !== "messageContextInfo" && k !== "senderKeyDistributionMessage",
    ) ?? null
  );
}

/**
 * Texto o leyenda del mensaje, sin envolturas.
 * @param {any} msg
 */
export function textoDe(msg) {
  const m = interior(msg);
  return (
    m.conversation ??
    m.extendedTextMessage?.text ??
    m.imageMessage?.caption ??
    m.videoMessage?.caption ??
    m.documentMessage?.caption ??
    m.documentWithCaptionMessage?.message?.documentMessage?.caption ??
    null
  );
}

/**
 * Los `Long` de protobuf, números o textos → número (0 si no se puede).
 * @param {any} x
 */
function aNumero(x) {
  if (x === null || x === undefined) return 0;
  if (typeof x === "object" && typeof x.toNumber === "function") return x.toNumber();
  const n = Number(x);
  return Number.isFinite(n) ? n : 0;
}

/**
 * @typedef {{
 *   clase: "texto" | "imagen" | "audio" | "documento" | "video" | "sticker" | "ubicacion" | "contacto" | null,
 *   texto: string | null,
 *   mime: string | null,
 *   nombre: string | null,
 *   tamano: number,
 * }} Contenido
 */

/**
 * Qué trae el mensaje, en las clases que entiende el contrato con Juan (más tres
 * que no son archivos: sticker, ubicación y contacto). `clase: null` = no es
 * nada que atender (reacción, borrado, edición, aviso del protocolo…).
 *
 * @param {any} msg
 * @returns {Contenido}
 */
export function contenidoDe(msg) {
  const m = interior(msg);
  /** @type {Contenido} */
  const vacio = { clase: null, texto: null, mime: null, nombre: null, tamano: 0 };

  if (m.conversation) return { ...vacio, clase: "texto", texto: m.conversation };
  if (m.extendedTextMessage) return { ...vacio, clase: "texto", texto: m.extendedTextMessage.text ?? "" };

  if (m.imageMessage) {
    const i = m.imageMessage;
    return { ...vacio, clase: "imagen", texto: i.caption ?? null, mime: i.mimetype ?? "image/jpeg", tamano: aNumero(i.fileLength) };
  }
  if (m.audioMessage) {
    const a = m.audioMessage;
    return { ...vacio, clase: "audio", mime: a.mimetype ?? "audio/ogg", tamano: aNumero(a.fileLength) };
  }
  const doc = m.documentMessage ?? m.documentWithCaptionMessage?.message?.documentMessage;
  if (doc) {
    return {
      ...vacio,
      clase: "documento",
      texto: doc.caption ?? null,
      mime: doc.mimetype ?? "application/octet-stream",
      nombre: doc.fileName ?? null,
      tamano: aNumero(doc.fileLength),
    };
  }
  if (m.videoMessage) {
    const v = m.videoMessage;
    return { ...vacio, clase: "video", texto: v.caption ?? null, mime: v.mimetype ?? "video/mp4", tamano: aNumero(v.fileLength) };
  }
  if (m.stickerMessage) return { ...vacio, clase: "sticker" };

  const ubicacion = m.locationMessage ?? m.liveLocationMessage;
  if (ubicacion) {
    const lat = ubicacion.degreesLatitude;
    const lon = ubicacion.degreesLongitude;
    const sitio = [ubicacion.name, ubicacion.address].filter(Boolean).join(", ");
    const coords = typeof lat === "number" && typeof lon === "number" ? `${lat}, ${lon}` : "sin coordenadas";
    return { ...vacio, clase: "ubicacion", texto: `Ubicación compartida: ${coords}${sitio ? ` (${sitio})` : ""}` };
  }
  if (m.contactMessage || m.contactsArrayMessage) {
    const nombre = m.contactMessage?.displayName ?? m.contactsArrayMessage?.displayName ?? null;
    return { ...vacio, clase: "contacto", texto: `Contacto compartido${nombre ? `: ${nombre}` : ""}` };
  }
  return vacio;
}

/**
 * @typedef {{ accion: "entrante" | "propio" } | { accion: "ignorar", motivo: string }} Decision
 */

/**
 * La decisión para cada mensaje de un evento `messages.upsert`.
 *
 *   · estados, difusiones, grupos, canales y bots de Meta → ignorar
 *   · `fromMe` → eco del propio puente (ignorar) o una persona desde el teléfono
 *     (`propio`), solo si es reciente
 *   · de otros: solo en vivo (`notify`); `append` es historial que llega al
 *     reconectar y contestarlo sería responder mensajes viejos
 *   · sin contenido que atender, stickers y mensajes de más de 24 h → ignorar
 *
 * @param {any} msg
 * @param {string} type  `notify` o `append` (Baileys).
 * @param {{ enviados: { tiene(id: string): boolean }, yo?: (string | null | undefined)[], ahora?: number }} ctx
 * @returns {Decision}
 */
export function decidirUpsert(msg, type, ctx) {
  const ahora = ctx.ahora ?? Date.now();
  const id = msg?.key?.id;
  if (!id) return { accion: "ignorar", motivo: "sin_id" };
  if (!esChatDeUnaPersona(msg.key.remoteJid)) return { accion: "ignorar", motivo: "no_es_chat" };

  if (msg.key.fromMe) {
    if (ctx.enviados.tiene(id)) return { accion: "ignorar", motivo: "eco_del_bot" };
    const propios = (ctx.yo ?? []).filter(Boolean).map((j) => sinDispositivo(j));
    if (propios.includes(sinDispositivo(msg.key.remoteJid))) return { accion: "ignorar", motivo: "nota_personal" };
    if (contenidoDe(msg).clase === null) return { accion: "ignorar", motivo: "sin_contenido" };
    const ts = aNumero(msg.messageTimestamp) * 1000;
    if (ts && ahora - ts > RESPUESTA_VIGENTE_MS) return { accion: "ignorar", motivo: "propio_viejo" };
    return { accion: "propio" };
  }

  if (type !== "notify") return { accion: "ignorar", motivo: "historial" };
  const contenido = contenidoDe(msg);
  if (contenido.clase === null) return { accion: "ignorar", motivo: "sin_contenido" };
  if (contenido.clase === "sticker") return { accion: "ignorar", motivo: "sticker" };
  const ts = aNumero(msg.messageTimestamp) * 1000;
  if (ts && ahora - ts > ENTRANTE_VIGENTE_MS) return { accion: "ignorar", motivo: "viejo" };
  return { accion: "entrante" };
}
