// Un mensaje entrante antes de pasar a la conversación. Lo usan el Worker (rutas.ts, al atender un webhook) y el Durable Object
// (al rescatar un mensaje que se guardó crudo con `guardarAntes` y que el Worker no alcanzó a atender). Sin Cloudflare.

import type { AdjuntoEntrante, Entrante } from "./tipos";

export const MAX_ADJUNTO_BYTES = 12 * 1024 * 1024;
const PLAZO_DESCARGA_MS = 15_000;

/** Resuelve las descargas pendientes (Telegram, Cloud API) y deja el mensaje como datos planos. */
export async function prepararEntrante(e: Entrante): Promise<Entrante> {
  const adjuntos = await Promise.all(
    e.adjuntos.map(async (a) => {
      const limpio = { tipo: a.tipo, mime: a.mime, nombre: a.nombre, url: a.url, bytes: a.bytes, ...(a.sticker ? { sticker: true } : {}) };
      if (!limpio.bytes && a.obtener) {
        let reloj: ReturnType<typeof setTimeout> | undefined;
        try {
          const r = await Promise.race([a.obtener(), new Promise<null>((res) => (reloj = setTimeout(() => res(null), PLAZO_DESCARGA_MS)))]);
          if (r && r.bytes.byteLength > 0 && r.bytes.byteLength <= MAX_ADJUNTO_BYTES) {
            limpio.bytes = r.bytes;
            limpio.mime ??= r.mime;
          }
        } catch (err) {
          console.warn("[juan] no se pudo descargar el archivo del cliente:", String(err).slice(0, 200));
        } finally {
          clearTimeout(reloj);
        }
      }
      return limpio;
    }),
  );
  return { ...e, adjuntos };
}

/**
 * El mensaje tal cual llegó, para guardarlo (SQLite del Durable Object, por RPC): solo datos planos, sin funciones ni bytes.
 * Un archivo queda como su `url` o su `ref`, con los que se puede volver a pedir.
 */
export function crudoDe(e: Entrante): Entrante {
  return {
    canal: e.canal,
    id_externo: e.id_externo,
    id_mensaje: e.id_mensaje,
    ...(e.nombre !== undefined ? { nombre: e.nombre } : {}),
    ...(e.celular !== undefined ? { celular: e.celular } : {}),
    ...(e.texto !== undefined ? { texto: e.texto } : {}),
    adjuntos: e.adjuntos.map((a) => {
      const c: AdjuntoEntrante = { tipo: a.tipo };
      if (a.mime !== undefined) c.mime = a.mime;
      if (a.nombre !== undefined) c.nombre = a.nombre;
      if (a.url !== undefined) c.url = a.url;
      if (a.ref !== undefined) c.ref = a.ref;
      if (a.sticker) c.sticker = true;
      return c;
    }),
    ts: e.ts,
    ...(e.propio !== undefined ? { propio: e.propio } : {}),
  };
}

/** Lo guardado con `crudoDe`, de vuelta: cada archivo con `ref` se vuelve a pedir con `descargar` (el adaptador del canal). */
export function entranteDeCrudo(c: Entrante, descargar?: (ref: string) => Promise<{ bytes: Uint8Array; mime?: string } | null>): Entrante {
  return {
    ...c,
    adjuntos: (c.adjuntos ?? []).map((a) => {
      const ref = a.ref;
      return ref && descargar && !a.bytes ? { ...a, obtener: () => descargar(ref) } : a;
    }),
  };
}
