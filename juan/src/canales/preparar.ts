// Un mensaje entrante antes de pasar a la conversación. Lo usan el Worker (rutas.ts, al atender un webhook) y el Durable Object
// (al rescatar un mensaje que se guardó crudo con `guardarAntes` y que el Worker no alcanzó a atender). Sin Cloudflare.
//
// Ubicación (2026-11-25, docs/UBICACION.md): un enlace de mapa con coordenadas en el texto de la clienta se vuelve su `ubicacion`
// (origen «enlace») y en el texto queda una frase sin coordenadas. La copia de rescate (`crudoDe`) nunca guarda un punto.

import { quitarCoordenadasDelTexto, ubicacionDelTexto } from "../motor/enlacesMapa";
import type { AdjuntoEntrante, Entrante } from "./tipos";
import { crearUbicacion } from "./ubicacion";

export const MAX_ADJUNTO_BYTES = 12 * 1024 * 1024;
const PLAZO_DESCARGA_MS = 15_000;

/** Los mensajes de la clienta (no lo que escribe la tienda, ni un comentario público) son los que pueden traer su punto de entrega. */
const esDeLaClienta = (e: Entrante) => !e.propio && !e.comentario;

/**
 * Resuelve las descargas pendientes (Telegram, Cloud API) y deja el mensaje como datos planos. Si el texto de la clienta trae un enlace
 * de mapa con su punto (motor/enlacesMapa.ts; los cortos de Google se siguen con `fetch`), el punto sale como `ubicacion` (si el canal
 * no trajo ya una) y el enlace se cambia en el texto por una frase sin coordenadas: el modelo nunca las ve.
 */
export async function prepararEntrante(e: Entrante, op: { fetch?: typeof fetch } = {}): Promise<Entrante> {
  // El enlace se sigue mientras bajan los archivos (los dos tienen su propio plazo).
  const delTextoP = esDeLaClienta(e) && e.texto ? ubicacionDelTexto(e.texto, { fetch: op.fetch }) : Promise.resolve(null);
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
  const delTexto = await delTextoP;
  if (!delTexto?.coordenadas) return { ...e, adjuntos };
  const ubicacion = e.ubicacion ?? (e.ubicacion_omitida ? null : crearUbicacion(delTexto.coordenadas.lat, delTexto.coordenadas.lon, "enlace"));
  return { ...e, adjuntos, texto: delTexto.texto, ...(ubicacion ? { ubicacion } : {}) };
}

/**
 * El mensaje tal cual llegó, para guardarlo (SQLite del Durable Object, por RPC): solo datos planos, sin funciones ni bytes.
 * Un archivo queda como su `url` o su `ref`, con los que se puede volver a pedir.
 *
 * SIN el punto de entrega: las coordenadas nunca se guardan en el Durable Object. La ubicación del canal queda como `ubicacion_omitida`
 * y un enlace de mapa con coordenadas escritas se cambia por la frase (uno corto queda: no las trae y el rescate lo vuelve a seguir). Si
 * el mensaje se atiende desde ahí (el Worker se cayó antes), el modelo sabe que la clienta la compartió y se la pide otra vez.
 */
export function crudoDe(e: Entrante): Entrante {
  const delTexto = esDeLaClienta(e) && e.texto !== undefined ? quitarCoordenadasDelTexto(e.texto) : null;
  const omitida = e.ubicacion?.origen ?? e.ubicacion_omitida ?? (delTexto?.coordenadas ? "enlace" : undefined);
  return {
    canal: e.canal,
    id_externo: e.id_externo,
    id_mensaje: e.id_mensaje,
    ...(e.nombre !== undefined ? { nombre: e.nombre } : {}),
    ...(e.celular !== undefined ? { celular: e.celular } : {}),
    ...(e.texto !== undefined ? { texto: delTexto ? delTexto.texto : e.texto } : {}),
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
    // La cita y el «reenviado» también se guardan: si el Worker se cae, el rescate los conoce igual.
    ...(e.cita ? { cita: { id: e.cita.id, ...(e.cita.texto !== undefined ? { texto: e.cita.texto } : {}), ...(e.cita.deLaTienda !== undefined ? { deLaTienda: e.cita.deLaTienda } : {}) } } : {}),
    ...(e.reenviado ? { reenviado: e.reenviado } : {}),
    // Un comentario de una publicación (Facebook o Instagram): sus datos son texto plano, se guardan tal cual.
    ...(e.comentario ? { comentario: { ...e.comentario } } : {}),
    ...(omitida && esDeLaClienta(e) ? { ubicacion_omitida: omitida } : {}),
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
