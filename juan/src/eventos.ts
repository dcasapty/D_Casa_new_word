// Palomitas (enviado, entregado, leído, no llegó) y reacciones del cliente → Odoo (`POST /dcasa/juan/v1/eventos`). Sin Cloudflare.
//
// No son mensajes: no pasan por el Durable Object, no despiertan al bot, no cuentan para la ventana de 24 h ni para los
// seguimientos. El webhook ya le contestó 200 a Meta (o a Telegram) cuando esto corre (`ctx.waitUntil`, rutas.ts).
//
// Qué se le contesta a Meta si Odoo está caído (decisión del 2026-11-07): 200 igual. Un 500 haría que Meta reenviara el aviso (y los
// mensajes que vinieran en el mismo lote) durante horas mientras Odoo no vuelva, con el webhook marcado como fallando, por algo que
// solo pinta una palomita; los mensajes del cliente ya están a salvo en el Durable Object antes del 200. Lo que se pierde es a lo
// más una palomita, y la siguiente la corrige (leído le gana a entregado, que le gana a enviado). Por eso aquí se reintenta lo que
// alcanza mientras dura `waitUntil` (Odoo dormido despierta en unos 10 s) y nada más.
//
// Un id que Odoo todavía no conoce (`desconocidos`) casi siempre es la respuesta del asistente que se está registrando en ese mismo
// momento (la palomita de «enviado» llega en un segundo): se vuelve a mandar una o dos veces. Un Odoo viejo (sin la ruta) contesta
// 404 y no se insiste: el mensaje del cliente nunca dependió de esto.

import type { EventoCanal } from "./canales/tipos";
import { OdooError, type RespuestaEventos } from "./odoo/cliente";

/** Esperas antes de reintentar cuando Odoo no contestó (está despertando, o hubo un corte). Caben en los 30 s de `waitUntil`. */
export const ESPERAS_SI_ODOO_FALLA_MS = [2_000, 6_000];
/** Esperas antes de volver a mandar lo que Odoo no reconoció (la respuesta del asistente se registra en paralelo). */
export const ESPERAS_SI_ES_DESCONOCIDO_MS = [5_000, 10_000];
/** Una tanda nunca es más grande que esto (lo que acepta Odoo). */
export const MAX_POR_TANDA = 100;

export interface DepsEventos {
  enviar(eventos: EventoCanal[]): Promise<RespuestaEventos>;
  dormir(ms: number): Promise<void>;
  log?(nivel: "info" | "warn", mensaje: string): void;
}

export interface ResultadoEventos {
  /** Cuántos llegaron a Odoo (aplicados o no: un aviso repetido no cambia nada y está bien). */
  entregados: number;
  /** Cuántos no se pudieron entregar (Odoo caído todo el rato, o un Odoo viejo). */
  perdidos: number;
  /** Odoo no tiene la ruta (todavía no se desplegó el Odoo nuevo). */
  odooViejo: boolean;
}

const esPasajero = (e: unknown) => !(e instanceof OdooError) || e.reintentable;

/** Manda una tanda con reintentos si Odoo falla. Devuelve lo que contestó Odoo, o null si no se pudo. */
async function mandar(lote: EventoCanal[], d: DepsEventos): Promise<RespuestaEventos | "viejo" | null> {
  for (let intento = 0; ; intento++) {
    try {
      return await d.enviar(lote);
    } catch (e) {
      if (e instanceof OdooError && (e.estado === 404 || e.estado === 405)) return "viejo";
      if (!esPasajero(e) || intento >= ESPERAS_SI_ODOO_FALLA_MS.length) {
        d.log?.("warn", `no se pudieron entregar ${lote.length} palomita(s) o reacción(es) a Odoo: se pierden (los mensajes no): ${String(e).slice(0, 200)}`);
        return null;
      }
      await d.dormir(ESPERAS_SI_ODOO_FALLA_MS[intento]);
    }
  }
}

export async function entregarEventos(eventos: EventoCanal[], d: DepsEventos): Promise<ResultadoEventos> {
  const resultado: ResultadoEventos = { entregados: 0, perdidos: 0, odooViejo: false };
  let pendientes = eventos.slice(0, MAX_POR_TANDA);
  resultado.perdidos += eventos.length - pendientes.length;
  for (let vuelta = 0; pendientes.length > 0; vuelta++) {
    const r = await mandar(pendientes, d);
    if (r === "viejo") {
      d.log?.("info", "Odoo todavía no tiene la ruta de palomitas y reacciones (/eventos): se ignoran hasta que se despliegue");
      resultado.odooViejo = true;
      resultado.perdidos += pendientes.length;
      return resultado;
    }
    if (r === null) {
      resultado.perdidos += pendientes.length;
      return resultado;
    }
    const desconocidos = new Set((Array.isArray(r.desconocidos) ? r.desconocidos : []).filter((x): x is string => typeof x === "string"));
    const otraVez = pendientes.filter((e) => desconocidos.has(e.id_mensaje));
    resultado.entregados += pendientes.length - otraVez.length;
    if (otraVez.length === 0) return resultado;
    if (vuelta >= ESPERAS_SI_ES_DESCONOCIDO_MS.length) {
      // De un mensaje que Odoo no conoce (de antes de esta versión, o mandado por fuera de Juan): se ignora sin ruido.
      resultado.entregados += otraVez.length;
      return resultado;
    }
    await d.dormir(ESPERAS_SI_ES_DESCONOCIDO_MS[vuelta]);
    pendientes = otraVez;
  }
  return resultado;
}
