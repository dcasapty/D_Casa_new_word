// Las rutas del Worker, sin Cloudflare: reciben sus dependencias y se prueban con Request/Response de Node.
//
//   GET  /health                      → "ok" (sin datos)
//   *    /webhooks/<canal>            → cada adaptador de canales/ verifica su origen y traduce
//   GET  /media/<conv>/<id>?exp&sig   → archivo temporal del cliente, firmado, para que Odoo lo descargue
//   POST /odoo/enviar                 → una vendedora escribe desde Odoo
//   POST /odoo/estado                 → tomar o devolver la conversación
//   POST /odoo/seguimiento            → redactar y enviar el seguimiento n.º 1 o 2
//   GET  /odoo/salud                  → estado del Worker
//   (las cuatro de /odoo/* con Authorization: Bearer <JUAN_WORKER_TOKEN>, en tiempo constante)

import { canalActivo, type Config } from "./config";
import { adaptadorPorRuta } from "./canales";
import { TODOS_LOS_CANALES, type AdaptadorCanal, type CanalId, type Entrante, json } from "./canales/tipos";
import type { Env } from "./env";
import type { ResultadoIngest, ResultadoSeguimiento, SolicitudEnviar, SolicitudSeguimiento } from "./motor/conversacion";
import { nombreDeConversacion, verificarUrlMedio } from "./motor/mediosUrl";
import { informeDeSalud } from "./salud";
import { bearerValido } from "./seguridad";

/** Lo que las rutas necesitan de una conversación (el stub del Durable Object o un doble en las pruebas). */
export interface ConversacionApi {
  ingest(e: Entrante): Promise<ResultadoIngest>;
  enviarVendedora(s: SolicitudEnviar): Promise<{ ok: true; id_mensaje: string }>;
  fijarEstado(s: { estado: "humano" | "bot"; pausada_hasta?: string | number | null }): Promise<{ ok: true }>;
  seguimiento(s: SolicitudSeguimiento): Promise<ResultadoSeguimiento>;
  leerMedio(id: string): Promise<{ bytes: Uint8Array; mime: string; nombre: string | null } | null>;
}

export interface DepsRutas {
  adaptadores: readonly AdaptadorCanal[];
  config(): Promise<Config>;
  conversacion(canal: CanalId, idExterno: string): ConversacionApi;
  gastoMes(mes: string): Promise<number>;
  ahora(): number;
  /** Para que un webhook responda de inmediato y el trabajo siga después. */
  esperarDespues(trabajo: Promise<unknown>): void;
}

const MAX_ADJUNTO_BYTES = 12 * 1024 * 1024;
const PLAZO_DESCARGA_MS = 15_000;

const esCanal = (v: unknown): v is CanalId => typeof v === "string" && (TODOS_LOS_CANALES as readonly string[]).includes(v);
const esObjeto = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
const error = (mensaje: string, status: number) => json({ ok: false, error: mensaje }, status);

/** Resuelve las descargas pendientes (Telegram, Cloud API) y deja el mensaje como datos planos. */
async function prepararEntrante(e: Entrante): Promise<Entrante> {
  const adjuntos = await Promise.all(
    e.adjuntos.map(async (a) => {
      const limpio = { tipo: a.tipo, mime: a.mime, nombre: a.nombre, url: a.url, bytes: a.bytes };
      if (!limpio.bytes && a.obtener) {
        try {
          const r = await Promise.race([a.obtener(), new Promise<null>((res) => setTimeout(() => res(null), PLAZO_DESCARGA_MS))]);
          if (r && r.bytes.byteLength > 0 && r.bytes.byteLength <= MAX_ADJUNTO_BYTES) {
            limpio.bytes = r.bytes;
            limpio.mime ??= r.mime;
          }
        } catch (err) {
          console.warn("[juan] no se pudo descargar el archivo del cliente:", String(err).slice(0, 200));
        }
      }
      return limpio;
    }),
  );
  return { ...e, adjuntos };
}

async function entregar(e: Entrante, d: DepsRutas): Promise<void> {
  // Un canal apagado en Odoo no atiende ni registra: el webhook responde 200 y listo.
  const cfg = await d.config();
  if (!canalActivo(cfg, e.canal)) return;
  const listo = await prepararEntrante(e);
  await d.conversacion(listo.canal, listo.id_externo).ingest(listo);
}

export async function manejar(req: Request, env: Env, d: DepsRutas): Promise<Response> {
  const url = new URL(req.url);
  const ruta = url.pathname.replace(/\/+$/, "") || "/";

  if (ruta === "/health") return new Response("ok", { status: 200 });

  const adaptador = adaptadorPorRuta(ruta, d.adaptadores);
  if (adaptador) return webhook(adaptador, req, env, d);

  if (ruta.startsWith("/media/")) return media(ruta, url, req, env, d);
  if (ruta.startsWith("/odoo/")) return odoo(ruta, req, env, d);

  return new Response("no encontrado", { status: 404 });
}

async function webhook(adaptador: AdaptadorCanal, req: Request, env: Env, d: DepsRutas): Promise<Response> {
  let r;
  try {
    r = await adaptador.recibir(req, env);
  } catch (e) {
    console.error(`[juan] webhook ${adaptador.ruta}:`, e instanceof Error ? e.message : String(e));
    return new Response("error", { status: 500 });
  }
  if (r.entrantes.length === 0) return r.respuesta;

  const trabajo = (async () => {
    for (const e of r.entrantes) await entregar(e, d);
  })();
  if (r.esperar) {
    // El puente QR necesita un error HTTP para reintentar: se responde cuando el mensaje ya está guardado.
    try {
      await trabajo;
    } catch (e) {
      console.error(`[juan] no se pudo guardar el mensaje de ${adaptador.ruta}:`, e instanceof Error ? e.message : String(e));
      return new Response("no se pudo guardar el mensaje", { status: 500 });
    }
    return r.respuesta;
  }
  // Telegram y Meta reintentan si tardamos: se responde ya y el mensaje se atiende después.
  d.esperarDespues(trabajo.catch((e) => console.error(`[juan] ${adaptador.ruta}:`, e instanceof Error ? e.message : String(e))));
  return r.respuesta;
}

async function media(ruta: string, url: URL, req: Request, env: Env, d: DepsRutas): Promise<Response> {
  if (req.method !== "GET") return new Response("método no permitido", { status: 405 });
  const [, , clave, id] = ruta.split("/");
  if (!clave || !id || !/^[a-f0-9]{16,64}$/.test(id)) return new Response("no encontrado", { status: 404 });
  const veredicto = await verificarUrlMedio(env.JUAN_WORKER_TOKEN ?? "", clave, id, url.searchParams.get("exp"), url.searchParams.get("sig"), d.ahora());
  if (veredicto === "firma") return new Response("firma inválida", { status: 403 });
  if (veredicto === "vencida") return new Response("vencida", { status: 410 });
  const nombre = nombreDeConversacion(clave);
  const corte = nombre?.indexOf(":") ?? -1;
  if (!nombre || corte < 1) return new Response("no encontrado", { status: 404 });
  const canal = nombre.slice(0, corte);
  if (!esCanal(canal)) return new Response("no encontrado", { status: 404 });
  const archivo = await d.conversacion(canal, nombre.slice(corte + 1)).leerMedio(id);
  if (!archivo) return new Response("ya no está", { status: 404 });
  return new Response(archivo.bytes, {
    headers: {
      "content-type": archivo.mime,
      "cache-control": "private, max-age=600",
      "x-content-type-options": "nosniff",
      ...(archivo.nombre ? { "content-disposition": `inline; filename*=UTF-8''${encodeURIComponent(archivo.nombre)}` } : {}),
    },
  });
}

async function odoo(ruta: string, req: Request, env: Env, d: DepsRutas): Promise<Response> {
  // Sin token configurado ni siquiera se prueba el de la petición: falla cerrado.
  if (!env.JUAN_WORKER_TOKEN) return error("JUAN_WORKER_TOKEN no está configurado", 503);
  if (!bearerValido(req, env.JUAN_WORKER_TOKEN)) return error("no autorizado", 401);

  if (ruta === "/odoo/salud") {
    if (req.method !== "GET") return error("método no permitido", 405);
    const informe = await informeDeSalud({ env, adaptadores: d.adaptadores, config: d.config, gastoMes: d.gastoMes, ahora: d.ahora });
    return json(informe);
  }

  if (req.method !== "POST") return error("método no permitido", 405);
  let cuerpo: unknown;
  try {
    cuerpo = await req.json();
  } catch {
    return error("el cuerpo debe ser JSON", 400);
  }
  if (!esObjeto(cuerpo)) return error("el cuerpo debe ser un objeto JSON", 400);
  if (!esCanal(cuerpo.canal)) return error("canal inválido", 400);
  if (typeof cuerpo.id_externo !== "string" || !cuerpo.id_externo.trim()) return error("falta id_externo", 400);
  const canal = cuerpo.canal;
  const idExterno = cuerpo.id_externo.trim();
  const conv = d.conversacion(canal, idExterno);

  try {
    if (ruta === "/odoo/enviar") {
      if (cuerpo.autor !== undefined && cuerpo.autor !== "vendedora") return error("autor debe ser «vendedora»", 400);
      const texto = typeof cuerpo.texto === "string" ? cuerpo.texto : undefined;
      const adjuntos = Array.isArray(cuerpo.adjuntos) ? cuerpo.adjuntos.filter(esObjeto) : [];
      if (!texto?.trim() && adjuntos.length === 0) return error("hay que mandar texto o adjuntos", 400);
      for (const a of adjuntos) if (typeof a.url !== "string" || !/^https:\/\//i.test(a.url)) return error("cada adjunto necesita una url https", 400);
      const adaptador = d.adaptadores.find((a) => a.canales.includes(canal));
      if (!adaptador || !adaptador.configurado(env, canal)) return error(`el canal ${canal} no está configurado en el Worker`, 502);
      return json(
        await conv.enviarVendedora({
          texto,
          adjuntos: adjuntos.map((a) => ({
            tipo: String(a.tipo ?? "documento"),
            url: a.url as string,
            nombre: typeof a.nombre === "string" ? a.nombre : undefined,
            mime: typeof a.mime === "string" ? a.mime : undefined,
          })),
        }),
      );
    }

    if (ruta === "/odoo/estado") {
      if (cuerpo.estado !== "humano" && cuerpo.estado !== "bot") return error("estado debe ser «humano» o «bot»", 400);
      const hasta = cuerpo.pausada_hasta;
      return json(
        await conv.fijarEstado({
          estado: cuerpo.estado,
          pausada_hasta: typeof hasta === "string" || typeof hasta === "number" ? hasta : null,
        }),
      );
    }

    if (ruta === "/odoo/seguimiento") {
      if (typeof cuerpo.conversacion_id !== "number") return error("falta conversacion_id", 400);
      if (cuerpo.numero !== 1 && cuerpo.numero !== 2) return error("numero debe ser 1 o 2", 400);
      const ctx = esObjeto(cuerpo.contexto) ? cuerpo.contexto : {};
      const r = await conv.seguimiento({
        conversacion_id: cuerpo.conversacion_id,
        numero: cuerpo.numero,
        contexto: {
          interes: typeof ctx.interes === "string" ? ctx.interes : undefined,
          ultimo_mensaje_ts: typeof ctx.ultimo_mensaje_ts === "string" || typeof ctx.ultimo_mensaje_ts === "number" ? ctx.ultimo_mensaje_ts : undefined,
        },
      });
      return json(r, r.ok ? 200 : 502);
    }
  } catch (e) {
    console.error(`[juan] ${ruta}:`, e instanceof Error ? e.message : String(e));
    return error(e instanceof Error ? e.message.slice(0, 300) : "error", 502);
  }

  return error("no encontrado", 404);
}
