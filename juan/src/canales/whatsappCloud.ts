// WhatsApp Cloud API (oficial, Meta). Es el WhatsApp de la tienda desde el 2026-11-02 (docs/LEEME_PRIMERO.md); antes era el plan B.
// Se enciende en Odoo (`canales_activos.whatsapp_cloud = true`) con estos datos cargados: WHATSAPP_PHONE_NUMBER_ID (variable),
// WHATSAPP_CLOUD_TOKEN, META_APP_SECRET y META_VERIFY_TOKEN (secretos). Apagado, el webhook responde 200 y no hace nada.
//
//   · GET  /webhooks/whatsapp-cloud → verificación (hub.verify_token = META_VERIFY_TOKEN)
//   · POST /webhooks/whatsapp-cloud → firma X-Hub-Signature-256 con META_APP_SECRET; el 200 sale cuando el mensaje ya está
//     guardado (`guardarAntes`, rutas.ts): Meta solo reintenta lo que no recibió 200.
//   · Texto libre solo dentro de las 24 h del último mensaje del cliente (después hace falta una plantilla aprobada).
//   · Con «coexistencia» (la app WhatsApp Business sigue en el teléfono) lo que la vendedora escribe llega como eco
//     (`smb_message_echoes`) y se trata como `propio:true`. NO VERIFICADO contra la documentación de Meta: el proxy de
//     la ronda 7 bloqueó developers.facebook.com. Revisar la forma exacta del eco antes de activar.
//   · Citas y reenviados (2026-11-07): `messages[].context` trae `{from, id}` del mensaje citado y/o `forwarded` /
//     `frequently_forwarded`. Viajan con el mensaje (`Entrante.cita`, `Entrante.reenviado`).
//   · Reacciones (`type: "reaction"`, `reaction: {message_id, emoji}`; sin emoji = la quitó) y recibos (`statuses`: sent,
//     delivered, read, failed) NO son mensajes del cliente: salen como `eventos` (rutas.ts los manda a Odoo después del
//     200) y nunca despiertan al bot. Las reacciones que la tienda deja desde el teléfono (ecos) se ignoran.
//   · «Responder» desde Odoo: el primer mensaje que sale lleva `context: {message_id}`; si Meta lo rechaza (un 4xx: el
//     citado es muy viejo o no existe), sale otra vez sin la cita: nunca se deja de enviar por la cita.

import type { Env } from "../env";
import { firmaMetaValida, tokensIguales } from "../seguridad";
import { urlGraph } from "./graph";
import {
  aMilisegundos,
  faltantesDe,
  json,
  ok200,
  type AdaptadorCanal,
  type AdjuntoEntrante,
  type Capacidades,
  type CanalId,
  type Entrante,
  type EstadoDeEntrega,
  type EventoCanal,
  type ResultadoEnvio,
  type ResultadoWebhook,
  type Saliente,
  type SaludCanal,
  EnvioParcialError,
} from "./tipos";

interface WaMensaje {
  from?: string;
  to?: string;
  id?: string;
  timestamp?: string;
  type?: string;
  text?: { body?: string };
  button?: { text?: string };
  interactive?: { button_reply?: { title?: string }; list_reply?: { title?: string } };
  image?: { id?: string; caption?: string; mime_type?: string };
  audio?: { id?: string; mime_type?: string };
  video?: { id?: string; caption?: string; mime_type?: string };
  document?: { id?: string; caption?: string; filename?: string; mime_type?: string };
  sticker?: { id?: string; mime_type?: string; animated?: boolean };
  /** El mensaje citado (`id`) y si es reenviado. */
  context?: { from?: string; id?: string; forwarded?: boolean; frequently_forwarded?: boolean };
  reaction?: { message_id?: string; emoji?: string };
}

/** Un recibo de entrega o lectura de un mensaje que mandamos. */
interface WaRecibo {
  id?: string;
  status?: string;
  timestamp?: string;
  recipient_id?: string;
  errors?: { code?: number; title?: string; message?: string; error_data?: { details?: string } }[];
}

interface WaCambio {
  field?: string;
  value?: {
    contacts?: { profile?: { name?: string }; wa_id?: string }[];
    messages?: WaMensaje[];
    message_echoes?: WaMensaje[];
    statuses?: WaRecibo[];
  };
}

const ESTADOS_DE_META: Record<string, EstadoDeEntrega> = { sent: "enviado", delivered: "entregado", read: "leido", failed: "fallido" };

/** Los errores de entrega que más se ven, en palabras de la tienda; los demás van con el texto de Meta y su código. */
const ERRORES_CONOCIDOS: Record<number, string> = {
  131047: "Pasaron más de 24 horas desde el último mensaje del cliente: WhatsApp solo deja escribirle con una plantilla aprobada.",
  131026: "WhatsApp no pudo entregarlo: puede que ese número no tenga WhatsApp o no pueda recibir el mensaje.",
};

/** El motivo de un «no llegó», corto y sin datos de nadie (Meta no los pone ahí). */
export function motivoDeMeta(r: WaRecibo): string | undefined {
  const e = r.errors?.[0];
  if (!e) return undefined;
  if (e.code !== undefined && ERRORES_CONOCIDOS[e.code]) return ERRORES_CONOCIDOS[e.code];
  const texto = [e.title ?? e.message, e.error_data?.details].filter(Boolean).join(": ");
  return `${texto || "WhatsApp no lo pudo entregar"}${e.code !== undefined ? ` (código ${e.code})` : ""}`.slice(0, 200);
}

/** Un error de la Graph API al enviar, con su código HTTP (para saber si vale la pena reintentar sin la cita). */
class ErrorDeEnvio extends Error {
  constructor(
    mensaje: string,
    readonly estado: number,
    /** El `error.code` de Meta, si lo dijo. */
    readonly codigo?: number,
  ) {
    super(mensaje);
  }
}

/**
 * Meta rechazó el `context.message_id` (el citado es muy viejo, de otro chat o ya no existe): «Invalid parameter» (100) o «Parameter
 * value is not valid» (131009), siempre con un 400. Solo entonces se sabe que no salió nada y se puede mandar otra vez sin cita: un 408
 * (se cortó esperando) o cualquier otro rechazo pudo haber salido, o va a fallar igual sin cita (revisión 2026-11-07).
 */
const CODIGOS_DE_CITA_RECHAZADA = new Set([100, 131009]);

interface WaCuerpo {
  object?: string;
  entry?: { id?: string; changes?: WaCambio[] }[];
}

export interface OpcionesWhatsappCloud {
  fetch?: typeof fetch;
  dormir?: (ms: number) => Promise<void>;
}

const CAPACIDADES: Capacidades = { imagenes: true, documentos: true, ventana24h: true, maxTexto: 3500, pie: true };

export function crearWhatsappCloud(op: OpcionesWhatsappCloud = {}): AdaptadorCanal {
  const f: typeof fetch = op.fetch ?? ((...a) => fetch(...a));
  const dormir = op.dormir ?? ((ms: number) => new Promise<void>((r) => setTimeout(r, ms)));

  /** media_id → URL (con Bearer) → bytes (con Bearer). */
  async function descargar(env: Env, mediaId: string, mime?: string): Promise<{ bytes: Uint8Array; mime?: string } | null> {
    const token = env.WHATSAPP_CLOUD_TOKEN;
    if (!token) return null;
    const meta = await f(urlGraph(env, encodeURIComponent(mediaId)), { headers: { authorization: `Bearer ${token}` } });
    if (!meta.ok) return null;
    const info = (await meta.json().catch(() => ({}))) as { url?: string; mime_type?: string };
    if (!info.url) return null;
    const r = await f(info.url, { headers: { authorization: `Bearer ${token}` } });
    if (!r.ok) return null;
    return { bytes: new Uint8Array(await r.arrayBuffer()), mime: info.mime_type ?? mime };
  }

  /** Un archivo entrante. `ref` (el media_id) deja que el Durable Object lo vuelva a pedir si el Worker no alcanzó a bajarlo. */
  function descargable(env: Env, mediaId: string, tipo: AdjuntoEntrante["tipo"], mime?: string, nombre?: string): AdjuntoEntrante {
    return { tipo, mime, nombre, ref: mediaId, obtener: () => descargar(env, mediaId, mime) };
  }

  function aEntrante(env: Env, m: WaMensaje, nombre: string | undefined, propio: boolean, ahora: number): Entrante | null {
    const cliente = propio ? m.to : m.from;
    if (!cliente || !m.id) return null;
    const adjuntos: AdjuntoEntrante[] = [];
    let texto: string | undefined;
    switch (m.type) {
      case "text":
        texto = m.text?.body;
        break;
      case "button":
        texto = m.button?.text;
        break;
      case "interactive":
        texto = m.interactive?.button_reply?.title ?? m.interactive?.list_reply?.title;
        break;
      case "image":
        if (m.image?.id) adjuntos.push(descargable(env, m.image.id, "imagen", m.image.mime_type));
        texto = m.image?.caption;
        break;
      case "audio":
        if (m.audio?.id) adjuntos.push(descargable(env, m.audio.id, "audio", m.audio.mime_type));
        break;
      case "video":
        if (m.video?.id) adjuntos.push(descargable(env, m.video.id, "video", m.video.mime_type));
        texto = m.video?.caption;
        break;
      case "document":
        if (m.document?.id) adjuntos.push(descargable(env, m.document.id, "documento", m.document.mime_type, m.document.filename));
        texto = m.document?.caption;
        break;
      case "location":
        texto = "(el cliente mandó una ubicación)";
        break;
      case "sticker":
        // El equipo lo ve en el chat de Odoo (pedido de la dueña, 2026-11-03); al modelo le basta saber que fue un sticker.
        if (m.sticker?.id) adjuntos.push({ ...descargable(env, m.sticker.id, "imagen", m.sticker.mime_type ?? "image/webp", "sticker.webp"), sticker: true });
        texto = "(el cliente mandó un sticker)";
        break;
      default:
        break;
    }
    texto = texto?.trim() || undefined;
    if (!texto && adjuntos.length === 0) return null;
    const ctx = m.context;
    const citado = typeof ctx?.id === "string" && ctx.id ? ctx.id.slice(0, 255) : undefined;
    const reenviado = ctx?.frequently_forwarded ? "muchas" : ctx?.forwarded ? "una" : undefined;
    return {
      canal: "whatsapp_cloud",
      id_externo: cliente,
      id_mensaje: m.id,
      nombre,
      celular: /^\d{8,15}$/.test(cliente) ? cliente : undefined,
      texto,
      adjuntos,
      ts: aMilisegundos(m.timestamp, ahora),
      propio,
      // `context.from` es el número que mandó el citado: si no es el del cliente, lo mandó la tienda.
      ...(citado && !propio ? { cita: { id: citado, ...(ctx?.from ? { deLaTienda: ctx.from !== cliente } : {}) } } : {}),
      ...(reenviado && !propio ? { reenviado } : {}),
    };
  }

  /** Una reacción del cliente a un mensaje (suyo o nuestro). Sin emoji = la quitó. No es un mensaje: es un evento. */
  function aReaccion(m: WaMensaje, ahora: number): EventoCanal | null {
    const objetivo = m.reaction?.message_id;
    // Meta manda texto; un aviso mal formado (número, objeto) no rompe el lote entero.
    if (typeof m.from !== "string" || !m.from || typeof objetivo !== "string" || !objetivo) return null;
    const emoji = typeof m.reaction?.emoji === "string" ? m.reaction.emoji.trim().slice(0, 32) : "";
    return { tipo: "reaccion", canal: "whatsapp_cloud", id_externo: m.from, id_mensaje: objetivo.slice(0, 255), emoji, ts: aMilisegundos(m.timestamp, ahora) };
  }

  /** Un recibo (enviado, entregado, leído, no llegó) de un mensaje nuestro. «deleted», «warning» y otros se ignoran. */
  function aEstado(r: WaRecibo, ahora: number): EventoCanal | null {
    const estado = r.status ? ESTADOS_DE_META[r.status] : undefined;
    if (!estado || typeof r.id !== "string" || !r.id || typeof r.recipient_id !== "string" || !r.recipient_id) return null;
    const error = estado === "fallido" ? motivoDeMeta(r) : undefined;
    return { tipo: "estado", canal: "whatsapp_cloud", id_externo: r.recipient_id, id_mensaje: r.id.slice(0, 255), estado, ts: aMilisegundos(r.timestamp, ahora), ...(error ? { error } : {}) };
  }

  async function enviarUno(env: Env, cuerpo: Record<string, unknown>): Promise<string | undefined> {
    const token = env.WHATSAPP_CLOUD_TOKEN;
    const numero = env.WHATSAPP_PHONE_NUMBER_ID;
    if (!token || !numero) throw new Error("WhatsApp Cloud: faltan WHATSAPP_CLOUD_TOKEN o WHATSAPP_PHONE_NUMBER_ID");
    const r = await f(urlGraph(env, `${numero}/messages`), {
      method: "POST",
      headers: { "content-type": "application/json", authorization: `Bearer ${token}` },
      body: JSON.stringify({ messaging_product: "whatsapp", recipient_type: "individual", ...cuerpo }),
    });
    const j = (await r.json().catch(() => ({}))) as { messages?: { id?: string }[]; error?: { message?: string; code?: number } };
    // Fuera de la ventana de 24 h Meta rechaza el texto libre y pide una plantilla: el motivo viene en el error.
    if (!r.ok || j.error) {
      const codigo = typeof j.error?.code === "number" ? j.error.code : undefined;
      throw new ErrorDeEnvio(`whatsapp cloud ${r.status}: ${j.error?.message ?? "sin detalle"} (código ${codigo ?? "?"})`, r.ok ? 400 : r.status, codigo);
    }
    return j.messages?.[0]?.id;
  }

  /**
   * El primer mensaje de un «Responder»: con la cita. Si Meta rechaza justo la cita (400 con código 100 o 131009: el citado es muy viejo
   * o ya no existe), se manda otra vez sin cita: ese rechazo no deja salir nada, así que no se duplica. Todo lo demás no se maquilla.
   */
  async function enviarConCita(env: Env, cuerpo: Record<string, unknown>, citado: string | undefined): Promise<string | undefined> {
    if (!citado) return enviarUno(env, cuerpo);
    try {
      return await enviarUno(env, { ...cuerpo, context: { message_id: citado } });
    } catch (e) {
      if (!(e instanceof ErrorDeEnvio) || e.estado !== 400 || e.codigo === undefined || !CODIGOS_DE_CITA_RECHAZADA.has(e.codigo)) throw e;
      console.warn("[juan] whatsapp cloud: no aceptó la cita; sale sin ella:", e.message.slice(0, 200));
      return enviarUno(env, cuerpo);
    }
  }

  return {
    canales: ["whatsapp_cloud"],
    ruta: "/webhooks/whatsapp-cloud",

    capacidades(): Capacidades {
      return CAPACIDADES;
    },

    faltantes(env: Env): string[] {
      return faltantesDe({
        WHATSAPP_CLOUD_TOKEN: !!env.WHATSAPP_CLOUD_TOKEN,
        WHATSAPP_PHONE_NUMBER_ID: !!env.WHATSAPP_PHONE_NUMBER_ID,
        META_APP_SECRET: !!env.META_APP_SECRET,
        META_VERIFY_TOKEN: !!env.META_VERIFY_TOKEN,
      });
    },

    configurado(env: Env, canal: CanalId): boolean {
      return this.faltantes(env, canal).length === 0;
    },

    async recibir(req: Request, env: Env): Promise<ResultadoWebhook> {
      const nada = (respuesta: Response): ResultadoWebhook => ({ respuesta, entrantes: [] });
      if (req.method === "GET") {
        const q = new URL(req.url).searchParams;
        const esperado = env.META_VERIFY_TOKEN;
        if (q.get("hub.mode") === "subscribe" && esperado && tokensIguales(q.get("hub.verify_token") ?? "", esperado)) {
          return nada(new Response(q.get("hub.challenge") ?? "", { status: 200 }));
        }
        return nada(new Response("no autorizado", { status: 403 }));
      }
      if (req.method !== "POST") return nada(new Response("método no permitido", { status: 405 }));

      const crudo = await req.text();
      if (!(await firmaMetaValida(crudo, req.headers.get("x-hub-signature-256"), env.META_APP_SECRET))) {
        return nada(new Response("firma inválida", { status: 401 }));
      }
      let cuerpo: WaCuerpo;
      try {
        cuerpo = JSON.parse(crudo) as WaCuerpo;
      } catch {
        return nada(ok200());
      }
      const ahora = Date.now();
      const entrantes: Entrante[] = [];
      const eventos: EventoCanal[] = [];
      for (const entrada of cuerpo.entry ?? []) {
        for (const cambio of entrada.changes ?? []) {
          const v = cambio.value;
          if (!v) continue;
          const nombres = new Map<string, string>();
          for (const c of v.contacts ?? []) if (c.wa_id && c.profile?.name) nombres.set(c.wa_id, c.profile.name);
          for (const m of v.messages ?? []) {
            if (m.type === "reaction") {
              const r = aReaccion(m, ahora);
              if (r) eventos.push(r);
              continue;
            }
            const e = aEntrante(env, m, m.from ? nombres.get(m.from) : undefined, false, ahora);
            if (e) entrantes.push(e);
          }
          for (const m of v.message_echoes ?? []) {
            if (m.type === "reaction") continue; // la tienda reaccionó desde el teléfono: no es del cliente
            const e = aEntrante(env, m, undefined, true, ahora);
            if (e) entrantes.push(e);
          }
          // Los recibos de entrega y lectura (las palomitas): eventos, no mensajes.
          for (const r of v.statuses ?? []) {
            const e = aEstado(r, ahora);
            if (e) eventos.push(e);
          }
        }
      }
      // `guardarAntes`: el 200 sale cuando cada mensaje ya quedó guardado en su Durable Object (rutas.ts). Meta solo reintenta si no
      // recibe 200: contestar antes de guardar perdía el mensaje si el Worker o el Durable Object fallaban justo después. Los
      // eventos no esperan: van a Odoo después del 200 (perder una palomita no es perder un mensaje).
      return { respuesta: json({ ok: true }), entrantes, guardarAntes: true, ...(eventos.length ? { eventos } : {}) };
    },

    descargar(ref: string, env: Env) {
      return descargar(env, ref);
    },

    async enviar(_canal: CanalId, salida: Saliente, env: Env): Promise<ResultadoEnvio> {
      const ids: string[] = [];
      let burbujas = 0;
      let medios = 0;
      // La cita («Responder» desde Odoo) va solo en el primer mensaje que sale.
      let citado = salida.responderA;
      const enviar = async (cuerpo: Record<string, unknown>) => {
        const id = await enviarConCita(env, cuerpo, citado);
        citado = undefined;
        if (id) ids.push(id);
      };
      try {
        for (let i = 0; i < salida.burbujas.length; i++) {
          if (i > 0) await dormir(salida.esperaMs ?? 1000);
          await enviar({ to: salida.para, type: "text", text: { preview_url: false, body: salida.burbujas[i] } });
          burbujas++;
        }
        for (const m of salida.medios) {
          await enviar(
            m.tipo === "imagen"
              ? { to: salida.para, type: "image", image: { link: m.url, ...(m.pie ? { caption: m.pie.slice(0, 1000) } : {}) } }
              : { to: salida.para, type: "document", document: { link: m.url, ...(m.nombre ? { filename: m.nombre } : {}), ...(m.pie ? { caption: m.pie.slice(0, 1000) } : {}) } },
          );
          medios++;
        }
      } catch (e) {
        // Lo que ya salió no se repite: quien reintente manda solo lo que falta (antes se reenviaba todo y el cliente veía dos veces
        // la primera burbuja).
        if (burbujas + medios > 0) throw new EnvioParcialError(e instanceof Error ? e.message : String(e), { burbujas, medios, ids });
        throw e;
      }
      return { ids };
    },

    async salud(canal: CanalId, env: Env): Promise<SaludCanal> {
      return { configurado: this.configurado(env, canal), faltan: this.faltantes(env, canal), conectado: null };
    },
  };
}
