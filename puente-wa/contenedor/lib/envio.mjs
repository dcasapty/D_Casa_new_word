// @ts-check
// Enviar una respuesta por WhatsApp con ritmo humano.
//
// Una «respuesta» es una secuencia: burbujas de texto, luego imágenes y
// documentos con su pie, y los restos de pies largos. Entre una y otra se
// respeta el ritmo (ritmo.mjs); antes de cada texto se muestra «escribiendo…».
// El socket de Baileys llega inyectado, así que esto se prueba con un doble.

import { esperaEntreBurbujas, pausaMedio, pausaPensar, tiempoEscribiendo } from "./ritmo.mjs";

/**
 * Un medio ya descargado y comprobado, listo para mandar.
 * @typedef {{ tipo: "imagen" | "documento", bytes: Uint8Array, mime: string, nombre: string, pie?: string, restoPie: string[] }} MedioListo
 *
 * @typedef {{
 *   sock: any,
 *   jid: string,
 *   burbujas: string[],
 *   medios: MedioListo[],
 *   generarId: (userId?: string) => string,
 *   registro: { anotar(id: string, ahora?: number): void },
 *   ritmo: import("./ritmo.mjs").Ritmo,
 *   dormir: (ms: number) => Promise<void>,
 *   azar: () => number,
 *   ultimoEntrante?: { key: any } | null,
 *   alEnviar?: (id: string, contenido: any) => void,
 * }} Peticion
 */

/**
 * Manda todo, en orden. Si algo falla a mitad, devuelve lo que SÍ salió (ids)
 * para que quien llama no repita lo ya enviado.
 *
 * @param {Peticion} p
 * @returns {Promise<{ ok: boolean, ids: string[], enviados: { chunks: number, medios: number }, error?: string }>}
 */
export async function enviarSecuencia(p) {
  const { sock, jid, ritmo, dormir, azar } = p;
  /** @type {string[]} */
  const ids = [];
  const enviados = { chunks: 0, medios: 0 };

  /** @type {({ clase: "texto", texto: string } | { clase: "medio", medio: MedioListo })[]} */
  const items = [
    ...p.burbujas.map((texto) => /** @type {const} */ ({ clase: "texto", texto })),
    ...p.medios.flatMap((medio) => [
      /** @type {const} */ ({ clase: "medio", medio }),
      ...medio.restoPie.map((texto) => /** @type {const} */ ({ clase: "texto", texto })),
    ]),
  ];

  /**
   * Presencia («escribiendo…», leído): adorno. Si falla no se pierde la respuesta.
   * @param {() => Promise<unknown>} f
   */
  const sinFallar = async (f) => {
    try {
      await f();
    } catch {
      /* la presencia nunca bloquea un mensaje */
    }
  };

  try {
    for (const [k, item] of items.entries()) {
      if (k === 0) {
        // La persona «lee» antes de contestar.
        if (p.ultimoEntrante?.key) await sinFallar(() => sock.readMessages([p.ultimoEntrante?.key]));
        await sinFallar(() => sock.presenceSubscribe(jid));
        await dormir(pausaPensar(azar, ritmo));
      } else {
        await dormir(esperaEntreBurbujas(azar, ritmo));
      }

      /** @type {any} */
      let contenido;
      if (item.clase === "texto") {
        await sinFallar(() => sock.sendPresenceUpdate("composing", jid));
        await dormir(tiempoEscribiendo(item.texto, azar, ritmo));
        await sinFallar(() => sock.sendPresenceUpdate("paused", jid));
        contenido = { text: item.texto };
      } else {
        await dormir(pausaMedio(azar, ritmo));
        const m = item.medio;
        contenido =
          m.tipo === "imagen"
            ? { image: m.bytes, mimetype: m.mime, ...(m.pie ? { caption: m.pie } : {}) }
            : { document: m.bytes, mimetype: m.mime, fileName: m.nombre, ...(m.pie ? { caption: m.pie } : {}) };
      }

      // El id se genera y se anota ANTES de enviar: es lo que distingue el eco de
      // este mensaje de una respuesta escrita por una persona desde el teléfono.
      const messageId = p.generarId(sock.user?.id);
      p.registro.anotar(messageId);
      await sock.sendMessage(jid, contenido, { messageId });
      ids.push(messageId);
      if (item.clase === "texto") enviados.chunks += 1;
      else enviados.medios += 1;
      p.alEnviar?.(messageId, item.clase === "texto" ? contenido : null);
    }
    return { ok: true, ids, enviados };
  } catch (e) {
    return { ok: false, ids, enviados, error: e instanceof Error ? e.message : String(e) };
  }
}
