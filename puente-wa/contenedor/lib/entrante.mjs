// @ts-check
// Del mensaje de Baileys al JSON del contrato con Juan.
//
// Baileys no deja una URL para bajar el archivo «después»: la nota de voz o la
// foto se descarga aquí, en el momento, o se pierde (lección del 23-sep-2026 en el
// CRM de origen). Viaja en base64 dentro del JSON (`medio.base64`).

import { construirWebhook } from "./contrato.mjs";
import { celularDeJid } from "./numeros.mjs";
import { LIMITE_ENTRANTE, mimeLimpio, nombreSeguro } from "./medios.mjs";
import { contenidoDe } from "./propios.mjs";

/** Clases que son un archivo para descargar. */
const CLASES_CON_ARCHIVO = new Set(["imagen", "audio", "documento", "video"]);

/** Nombre por defecto de cada clase de archivo cuando WhatsApp no trae uno. */
const NOMBRE_BASE = { imagen: "imagen", audio: "nota-de-voz", documento: "documento", video: "video" };

/**
 * El número del cliente en la forma del contrato: E.164 sin «+». Si el chat es
 * un identificador `@lid` y WhatsApp no deja ver el teléfono, se entrega el jid
 * completo (`…@lid`): sigue siendo una llave estable para Juan y `/api/enviar`
 * sabe contestarle.
 *
 * @param {string[]} candidatos  Nombres que se conocen del chat (jid, jid alterno, mapeados).
 * @returns {{ de: string, jid: string } | null}
 */
export function elegirDe(candidatos) {
  const limpios = candidatos.filter(Boolean);
  for (const c of limpios) {
    const celular = celularDeJid(c);
    if (celular) return { de: celular, jid: `${celular}@s.whatsapp.net` };
  }
  const lid = limpios.find((c) => c.endsWith("@lid"));
  if (lid) return { de: lid, jid: lid };
  return null;
}

/**
 * Arma el JSON para Juan a partir de un mensaje de Baileys.
 *
 * @param {any} msg
 * @param {{
 *   propio: boolean,
 *   candidatos: string[],
 *   descargarMedio: (msg: any) => Promise<Uint8Array>,
 *   ahora?: number,
 * }} p
 * @returns {Promise<{ payload: Record<string, unknown>, sinMedio: boolean } | null>}  null = no hay nada que entregar.
 */
export async function armarEntrante(msg, { propio, candidatos, descargarMedio, ahora = Date.now() }) {
  const contenido = contenidoDe(msg);
  if (contenido.clase === null) return null;

  const destino = elegirDe(candidatos);
  if (!destino) return null;

  const idMensaje = String(msg.key?.id ?? "");
  if (!idMensaje) return null;
  const ts = (Number(msg.messageTimestamp?.toNumber?.() ?? msg.messageTimestamp ?? 0) || 0) * 1000 || ahora;

  /** @type {string} */
  let tipo;
  /** @type {string | null} */
  let texto = contenido.texto?.trim() ? contenido.texto.trim() : null;
  /** @type {{ base64: string, mime: string, nombre: string } | null} */
  let medio = null;
  /** @type {{ motivo: string, mime?: string, bytes?: number } | null} */
  let medioOmitido = null;

  if (CLASES_CON_ARCHIVO.has(contenido.clase)) {
    tipo = contenido.clase;
    const clase = /** @type {"imagen" | "audio" | "documento" | "video"} */ (contenido.clase);
    const mime = mimeLimpio(contenido.mime) || "application/octet-stream";
    if (contenido.tamano > LIMITE_ENTRANTE[clase]) {
      medioOmitido = { motivo: "tamano", mime, bytes: contenido.tamano };
    } else {
      try {
        const bytes = await descargarMedio(msg);
        if (bytes.length > LIMITE_ENTRANTE[clase]) {
          medioOmitido = { motivo: "tamano", mime, bytes: bytes.length };
        } else {
          const nombre = nombreSeguro(contenido.nombre, mime, NOMBRE_BASE[clase]);
          medio = { base64: Buffer.from(bytes).toString("base64"), mime, nombre };
        }
      } catch {
        medioOmitido = { motivo: "descarga_fallida", mime };
      }
    }
  } else {
    // Texto, o algo que no es un archivo (ubicación, contacto, sticker propio):
    // todo viaja como texto. Un sticker que escribe la vendedora no trae texto, pero
    // SÍ significa que una persona tomó la conversación: se avisa igual.
    tipo = "texto";
    if (contenido.clase === "sticker") texto = "Sticker enviado desde el teléfono";
  }

  if (tipo === "texto" && !texto) return null;

  const payload = construirWebhook({
    idMensaje,
    de: destino.de,
    // El nombre que trae WhatsApp es el de quien ESCRIBE: en un mensaje propio es
    // el de la dueña, no el del cliente.
    nombre: propio ? null : (typeof msg.pushName === "string" && msg.pushName.trim() ? msg.pushName.trim() : null),
    tipo,
    texto,
    medio,
    medioOmitido,
    ts,
    propio,
    jid: destino.jid,
  });
  return { payload, sinMedio: medio === null && CLASES_CON_ARCHIVO.has(contenido.clase) };
}
