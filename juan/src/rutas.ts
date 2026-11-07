// Las rutas del Worker, sin Cloudflare: reciben sus dependencias y se prueban con Request/Response de Node.
//
//   GET  /health                      → "ok" (sin datos)
//   GET  /salud                       → público: qué NOMBRES de secretos faltan y el estado de cada canal (sin valores)
//   *    /webhooks/<canal>            → cada adaptador de canales/ verifica su origen y traduce
//   GET  /media/<conv>/<id>?exp&sig   → archivo temporal del cliente, firmado, para que Odoo lo descargue
//   POST /odoo/enviar                 → una vendedora escribe desde Odoo
//   POST /odoo/estado                 → tomar o devolver la conversación
//   POST /odoo/seguimiento            → redactar y enviar el seguimiento n.º 1 o 2
//   POST /odoo/olvidar                → borrar la copia de trabajo de una conversación (cuando Odoo la elimina)
//   GET  /odoo/salud                  → estado del Worker
//   (las cuatro de /odoo/* con Authorization: Bearer <JUAN_WORKER_TOKEN>, en tiempo constante)

import { canalActivo, CONFIG_POR_DEFECTO, type Config } from "./config";
import { adaptadorPorRuta } from "./canales";
import { crudoDe, prepararEntrante } from "./canales/preparar";
import { TODOS_LOS_CANALES, type AdaptadorCanal, type CanalId, type Entrante, type EventoCanal, json } from "./canales/tipos";
import type { Env } from "./env";
import { entregarEventos } from "./eventos";
import type { RespuestaEventos } from "./odoo/cliente";
import type { ResultadoIngest, ResultadoSeguimiento, SolicitudEnviar, SolicitudSeguimiento } from "./motor/conversacion";
import { nombreDeConversacion, verificarUrlMedio } from "./motor/mediosUrl";
import { rutasDelPanel } from "./odoo-panel";
import { informeDeSalud, informePublico, secretosGeneralesFaltantes } from "./salud";
import { bearerValido } from "./seguridad";

/** Lo que las rutas necesitan de una conversación (el stub del Durable Object o un doble en las pruebas). */
export interface ConversacionApi {
  ingest(e: Entrante): Promise<ResultadoIngest>;
  /**
   * Guarda el mensaje crudo (webhooks de Meta, antes del 200). `nuevo: false` = ya se había recibido (un reintento de Meta).
   * `pendiente` = sigue en la bandeja sin que nadie lo atienda: el Worker lo atiende (los repetidos se reconocen adentro).
   */
  guardarRecibido(e: Entrante): Promise<{ nuevo: boolean; pendiente: boolean }>;
  enviarVendedora(s: SolicitudEnviar): Promise<{ ok: true; id_mensaje: string }>;
  fijarEstado(s: { estado: "humano" | "bot"; pausada_hasta?: string | number | null; nota_para_el_bot?: string | null }): Promise<{ ok: true }>;
  seguimiento(s: SolicitudSeguimiento): Promise<ResultadoSeguimiento>;
  leerMedio(id: string): Promise<{ bytes: Uint8Array; mime: string; nombre: string | null } | null>;
  olvidar(): Promise<{ ok: true; mensajes: number }>;
}

export interface DepsRutas {
  adaptadores: readonly AdaptadorCanal[];
  config(): Promise<Config>;
  conversacion(canal: CanalId, idExterno: string): ConversacionApi;
  gastoMes(mes: string): Promise<number>;
  modelosSinPrecio?(mes: string): Promise<string[]>;
  leerSalud?(clave: string): Promise<{ json: string; ts: number } | null>;
  ahora(): number;
  /** Para que un webhook responda de inmediato y el trabajo siga después. */
  esperarDespues(trabajo: Promise<unknown>): void;
  /** Palomitas y reacciones a Odoo, en una tanda (`POST /eventos`). Sin esto (pruebas viejas) se ignoran. */
  eventos?(eventos: EventoCanal[]): Promise<RespuestaEventos>;
  /** Pausa entre reintentos de los eventos (las pruebas la ponen en 0). */
  dormir?(ms: number): Promise<void>;
}

/**
 * Webhooks de Meta: Meta pide contestar en 5 segundos o menos (developers.facebook.com/docs/messenger-platform/webhooks, «Webhook
 * Performance Requirements»; la guía de WhatsApp Cloud no da cifra y reintenta hasta 7 días). Antes del 200 solo se espera:
 *   · la configuración de Odoo, como mucho `PLAZO_CONFIG_WEBHOOK_MS`: casi siempre está en caché (60 s); si Odoo tarda, el mensaje se
 *     guarda igual y si el canal está encendido se decide después (el Worker o el rescate del Durable Object);
 *   · guardar en el Durable Object, como mucho `PLAZO_GUARDAR_MS` para todo el lote: si no confirma a tiempo, 500 y Meta reintenta
 *     (si sí alcanzó a guardarlo, el reintento lo reconoce y lo atiende sin duplicarlo).
 * Juntos quedan por debajo de los 5 s.
 */
const PLAZO_CONFIG_WEBHOOK_MS = 1_000;
const PLAZO_GUARDAR_MS = 3_000;

const esCanal = (v: unknown): v is CanalId => typeof v === "string" && (TODOS_LOS_CANALES as readonly string[]).includes(v);
const esObjeto = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
const error = (mensaje: string, status: number) => json({ ok: false, error: mensaje }, status);

async function entregar(e: Entrante, d: DepsRutas): Promise<void> {
  // Un canal apagado en Odoo no atiende ni registra: el webhook responde 200 y listo. (Un mensaje de Meta que ya se guardó crudo
  // y aquí no pasa — canal apagado o configuración desconocida — lo decide el rescate del Durable Object: ver `guardarAntes`.)
  const cfg = await d.config();
  if (!canalActivo(cfg, e.canal)) return;
  const listo = await prepararEntrante(e);
  await d.conversacion(listo.canal, listo.id_externo).ingest(listo);
}

export async function manejar(req: Request, env: Env, d: DepsRutas): Promise<Response> {
  const url = new URL(req.url);
  const ruta = url.pathname.replace(/\/+$/, "") || "/";

  if (ruta === "/health") return new Response("ok", { status: 200 });

  if (ruta === "/salud") {
    if (req.method !== "GET") return error("método no permitido", 405);
    return json(await informePublico({ env, adaptadores: d.adaptadores, config: d.config, gastoMes: d.gastoMes, modelosSinPrecio: d.modelosSinPrecio, leerSalud: d.leerSalud, ahora: d.ahora }));
  }

  const adaptador = adaptadorPorRuta(ruta, d.adaptadores);
  if (adaptador) return webhook(adaptador, req, env, d);

  if (ruta.startsWith("/media/")) return media(ruta, url, req, env, d);
  if (ruta.startsWith("/odoo/")) return odoo(ruta, req, env, d);

  return new Response("no encontrado", { status: 404 });
}

/**
 * Telegram es el canal de PRUEBAS del equipo, no una puerta abierta: cualquiera que conozca el @ del bot podría escribirle, gastar la IA
 * y crear oportunidades. Solo pasan los chats de la lista de Odoo (el equipo con Brian vinculado y los que se agreguen a mano). Se filtra
 * ANTES de atender el mensaje: no se descarga nada, no se transcribe, no se lee ninguna imagen, no se llama a la IA. Los demás canales
 * no se tocan.
 *
 * Si la lista no se pudo leer (Odoo dormido y ninguna copia reciente: `CargadorConfig` entrega entonces la configuración de fábrica) NO se
 * descarta el mensaje de un chat que quizá sí está permitido: se devuelve `null` y el webhook contesta 503 para que Telegram lo reintente
 * cuando Odoo despierte.
 */
async function soloLosPermitidos(entrantes: Entrante[], d: DepsRutas): Promise<Entrante[] | null> {
  if (!entrantes.some((e) => e.canal === "telegram")) return entrantes;
  const cfg = await d.config().catch(() => null);
  if (!cfg || cfg === CONFIG_POR_DEFECTO) return null;
  if (cfg.telegram_abierto) return entrantes; // la dueña lo abrió a propósito (Ajustes de Juan)
  const permitidos = new Set<string>(cfg.telegram_chats);
  const pasan = entrantes.filter((e) => e.canal !== "telegram" || permitidos.has(String(e.id_externo)));
  const descartados = entrantes.length - pasan.length;
  if (descartados > 0) console.warn(`[juan] telegram: ${descartados} mensaje(s) de chats que no están en la lista de Odoo: se ignoran`);
  return pasan;
}

/**
 * Palomitas y reacciones: a Odoo DESPUÉS de contestar, en una tanda. No pasan por el Durable Object ni por la IA. Solo las de un canal
 * encendido en Odoo y, en Telegram, las de un chat permitido (si la lista no se puede leer, se sueltan: no son mensajes).
 */
async function despacharEventos(eventos: EventoCanal[] | undefined, d: DepsRutas): Promise<void> {
  if (!eventos?.length || !d.eventos) return;
  const cfg = await d.config().catch(() => null);
  const conocida = cfg !== null && cfg !== CONFIG_POR_DEFECTO;
  const permitidos = conocida && !cfg.telegram_abierto ? new Set<string>(cfg.telegram_chats) : null;
  const pasan = eventos.filter((e) => {
    if (conocida && !canalActivo(cfg, e.canal)) return false;
    if (e.canal !== "telegram") return true;
    return conocida && (cfg.telegram_abierto || permitidos!.has(String(e.id_externo)));
  });
  if (pasan.length === 0) return;
  const enviar = d.eventos;
  const dormir = d.dormir ?? ((ms: number) => new Promise<void>((r) => setTimeout(r, ms)));
  await entregarEventos(pasan, {
    enviar: (lote) => enviar(lote),
    dormir,
    log: (nivel, mensaje) => console[nivel](`[juan] ${mensaje}`),
  });
}

async function webhook(adaptador: AdaptadorCanal, req: Request, env: Env, d: DepsRutas): Promise<Response> {
  let r;
  try {
    r = await adaptador.recibir(req, env);
  } catch (e) {
    console.error(`[juan] webhook ${adaptador.ruta}:`, e instanceof Error ? e.message : String(e));
    return new Response("error", { status: 500 });
  }
  // Las palomitas y reacciones nunca frenan ni cambian la respuesta al canal (ni la de los mensajes del mismo aviso).
  if (r.eventos?.length) d.esperarDespues(despacharEventos(r.eventos, d).catch((e) => console.error(`[juan] eventos ${adaptador.ruta}:`, e instanceof Error ? e.message : String(e))));
  const entrantes = await soloLosPermitidos(r.entrantes, d);
  if (entrantes === null) return new Response("la lista de chats permitidos no está disponible: reintenta", { status: 503 });
  if (entrantes.length === 0) return r.respuesta;
  if (r.guardarAntes) return guardarYContestar(adaptador, r.respuesta, entrantes, d);

  const trabajo = (async () => {
    for (const e of entrantes) await entregar(e, d);
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
  // Telegram reintenta si tardamos: se responde ya y el mensaje se atiende después.
  d.esperarDespues(trabajo.catch((e) => console.error(`[juan] ${adaptador.ruta}:`, e instanceof Error ? e.message : String(e))));
  return r.respuesta;
}

/** La configuración de Odoo si llega a tiempo; null si tarda más que `plazoMs` o falla. */
async function configAlVuelo(d: DepsRutas, plazoMs: number): Promise<Config | null> {
  let reloj: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([d.config(), new Promise<null>((res) => (reloj = setTimeout(() => res(null), plazoMs)))]);
  } catch {
    return null;
  } finally {
    clearTimeout(reloj);
  }
}

/**
 * Webhooks de Meta (WhatsApp Cloud, Messenger, Instagram). Meta reintenta solo lo que no recibió 200, así que el 200 sale cuando
 * cada mensaje ya quedó guardado en su Durable Object (`guardarRecibido`: rápido, sin descargas ni IA). Si alguno no se pudo
 * guardar: 500 y Meta reintenta el lote (lo ya guardado se reconoce por su id y no se atiende dos veces). Lo lento — descargar
 * archivos, transcribir, leer imágenes, la ráfaga, la IA y la respuesta — sigue después de contestar, como siempre; si el Worker no
 * alcanza a hacerlo, la alarma del Durable Object lo atiende desde la bandeja.
 */
async function guardarYContestar(adaptador: AdaptadorCanal, respuesta: Response, entrantes: Entrante[], d: DepsRutas): Promise<Response> {
  const cfg = await configAlVuelo(d, PLAZO_CONFIG_WEBHOOK_MS);
  // Solo un «apagado» seguro descarta (no registra, como siempre). Sin configuración (tarda, o Odoo no contestó y no hay copia) se
  // guarda igual: un canal que arranca apagado parecería apagado y el mensaje se perdería.
  const conocida = cfg !== null && cfg !== CONFIG_POR_DEFECTO;
  const aGuardar = entrantes.filter((e) => !conocida || canalActivo(cfg, e.canal));
  if (aGuardar.length === 0) return respuesta;

  // Conversaciones distintas a la vez (un lote grande no alarga la respuesta); dentro de una misma, en el orden del lote, y si uno
  // falla los que siguen de esa persona tampoco se guardan (el reintento de Meta los trae en orden). Un solo plazo para todo el lote.
  let reloj: ReturnType<typeof setTimeout> | undefined;
  const plazo = new Promise<never>((_, rechazar) => {
    reloj = setTimeout(() => rechazar(new Error(`el Durable Object no confirmó el guardado en ${PLAZO_GUARDAR_MS / 1000} s`)), PLAZO_GUARDAR_MS);
  });
  plazo.catch(() => {});
  const filas = new Map<string, Promise<unknown>>();
  let guardados: PromiseSettledResult<{ nuevo: boolean; pendiente: boolean }>[];
  try {
    guardados = await Promise.allSettled(
      aGuardar.map((e) => {
        const clave = `${e.canal}:${e.id_externo}`;
        const turno = (filas.get(clave) ?? Promise.resolve()).then(() => Promise.race([d.conversacion(e.canal, e.id_externo).guardarRecibido(crudoDe(e)), plazo]));
        filas.set(clave, turno);
        return turno;
      }),
    );
  } finally {
    clearTimeout(reloj);
  }
  // Se atiende lo nuevo y también lo ya guardado que sigue esperando sin que nadie lo atienda (la respuesta del primer intento se
  // perdió en la red DESPUÉS de guardarlo): sin esto esperaría al rescate. Los repetidos se reconocen adentro: no se contestan dos veces.
  const aAtender = aGuardar.filter((_, i) => {
    const g = guardados[i];
    return g.status === "fulfilled" && g.value.pendiente;
  });
  if (aAtender.length > 0) {
    d.esperarDespues(
      (async () => {
        // Uno que falla no frena a los demás; el que falló sigue en la bandeja y lo atiende el rescate.
        for (const e of aAtender) {
          await entregar(e, d).catch((err) => console.error(`[juan] ${adaptador.ruta}:`, err instanceof Error ? err.message : String(err)));
        }
      })(),
    );
  }
  const fallos = guardados.filter((g): g is PromiseRejectedResult => g.status === "rejected");
  if (fallos.length > 0) {
    const motivo = fallos[0].reason;
    console.error(`[juan] no se pudo guardar ${fallos.length} mensaje(s) de ${adaptador.ruta}; Meta reintentará:`, motivo instanceof Error ? motivo.message : String(motivo));
    return new Response("no se pudo guardar el mensaje", { status: 500 });
  }
  return respuesta;
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
  if (!env.JUAN_WORKER_TOKEN) {
    return json(
      {
        ok: false,
        error: "JUAN_WORKER_TOKEN no está configurado en este Worker: pégalo en Cloudflare (Settings → Variables and Secrets) con el mismo valor que en Odoo.",
        secretos_faltantes: secretosGeneralesFaltantes(env),
      },
      503,
    );
  }
  if (!bearerValido(req, env.JUAN_WORKER_TOKEN)) return error("no autorizado", 401);

  const delPanel = await rutasDelPanel(ruta, req, env, d); if (delPanel) return delPanel; // el panel de Odoo: odoo-panel*.ts

  if (ruta === "/odoo/salud") {
    if (req.method !== "GET") return error("método no permitido", 405);
    const informe = await informeDeSalud({ env, adaptadores: d.adaptadores, config: d.config, gastoMes: d.gastoMes, modelosSinPrecio: d.modelosSinPrecio, leerSalud: d.leerSalud, ahora: d.ahora });
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
      // La llave que impide mandar dos veces lo mismo cuando Odoo reintenta (opcional: un Odoo viejo no la manda).
      const idEnvio = cuerpo.id_envio;
      if (idEnvio !== undefined && (typeof idEnvio !== "string" || !/^[\w.:-]{1,120}$/.test(idEnvio))) return error("id_envio inválido", 400);
      // «Responder» desde Odoo (opcional): el id en el canal del mensaje del cliente que se cita. Uno raro se ignora (sale sin cita).
      const respondeA = typeof cuerpo.responde_a === "string" && /^[\x21-\x7e]{1,255}$/.test(cuerpo.responde_a) ? cuerpo.responde_a : undefined;
      const adaptador = d.adaptadores.find((a) => a.canales.includes(canal));
      if (!adaptador || !adaptador.configurado(env, canal)) return error(`el canal ${canal} no está configurado en el Worker`, 502);
      return json(
        await conv.enviarVendedora({
          id_envio: idEnvio,
          ...(respondeA ? { responde_a: respondeA } : {}),
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
          // Al devolver la conversación, Odoo puede dejarle una nota al bot (docs/JUAN.md → «Contrato verificado»).
          nota_para_el_bot: typeof cuerpo.nota_para_el_bot === "string" ? cuerpo.nota_para_el_bot : null,
        }),
      );
    }

    if (ruta === "/odoo/olvidar") return json(await conv.olvidar());

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
