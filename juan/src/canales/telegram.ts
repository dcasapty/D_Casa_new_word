// Telegram: el canal de PRUEBAS (clientas de prueba y avisos). El webhook se registra con un
// secreto (`secret_token`) que Telegram devuelve en la cabecera `X-Telegram-Bot-Api-Secret-Token`.
//
// Un archivo de Telegram NO se puede abrir con su file_id: hay que pedir `getFile` y bajarlo de una URL
// que lleva el token del bot adentro. Esa URL nunca sale de aquí (ni a Odoo ni al modelo): se descargan
// los bytes y el motor los guarda con su propia URL temporal y firmada.
//
// Citas, reenviados y reacciones (2026-11-07): `reply_to_message` (y `quote`, si el cliente eligió un pedazo) trae el mensaje
// citado CON su texto; `forward_origin` (o el viejo `forward_date`) dice que es reenviado; `message_reaction` llega solo si el
// webhook se registró con `allowed_updates` que lo incluya (docs/JUAN_CANALES.md §2) y sale como evento, nunca como mensaje.
// Telegram no les da a los bots «entregado» ni «leído»: en Telegram no hay palomitas.

import type { Env } from "../env";
import { tokensIguales } from "../seguridad";
import {
  faltantesDe,
  ok200,
  type AdaptadorCanal,
  type AdjuntoEntrante,
  type Capacidades,
  type CanalId,
  type Entrante,
  type MedioSaliente,
  type ResultadoEnvio,
  type ResultadoWebhook,
  type Saliente,
  type SaludCanal,
  EnvioParcialError,
  MAX_FOTO_DE_PERFIL_BYTES,
  sinNegritas,
} from "./tipos";

const API = "https://api.telegram.org";

interface TgArchivo {
  file_id: string;
  file_name?: string;
  mime_type?: string;
}

export interface TgMensaje {
  message_id: number;
  from?: { id: number; first_name?: string; is_bot?: boolean };
  chat: { id: number; type: string };
  date: number;
  text?: string;
  caption?: string;
  voice?: TgArchivo;
  audio?: TgArchivo;
  photo?: (TgArchivo & { width: number; height: number })[];
  document?: TgArchivo;
  video?: TgArchivo;
  /** El mensaje que el cliente citó (de este mismo chat). */
  reply_to_message?: Omit<TgMensaje, "reply_to_message">;
  /** El pedazo que el cliente eligió del mensaje citado, si eligió uno. */
  quote?: { text?: string };
  /** Reenviado (Bot API 7); los clientes viejos mandan `forward_date`. */
  forward_origin?: { type?: string };
  forward_date?: number;
}

type TgReaccion = { type: "emoji"; emoji: string } | { type: string; emoji?: string };

export interface TgUpdate {
  update_id: number;
  message?: TgMensaje;
  message_reaction?: {
    chat: { id: number; type: string };
    message_id: number;
    user?: { id: number; is_bot?: boolean };
    date: number;
    old_reaction?: TgReaccion[];
    new_reaction?: TgReaccion[];
  };
}

/** Lo que se ve de un mensaje citado: su texto, o qué era si no tenía texto. */
function textoDeCitado(m: Omit<TgMensaje, "reply_to_message">, elegido?: string): string | undefined {
  const texto = (elegido ?? m.text ?? m.caption ?? "").trim();
  if (texto) return texto.slice(0, 300);
  if (m.photo?.length) return "Foto";
  if (m.voice || m.audio) return "Audio";
  if (m.video) return "Video";
  if (m.document) return "Documento";
  return undefined;
}

/** `tg:<chat>:<id>` → el id del mensaje, si es de ese chat (para citarlo al responder). */
function idDeMensajeTelegram(id: string | undefined, chat: string): number | undefined {
  const m = id ? /^tg:(-?\d+):(\d+)$/.exec(id) : null;
  return m && m[1] === chat ? Number(m[2]) : undefined;
}

export interface OpcionesTelegram {
  fetch?: typeof fetch;
  dormir?: (ms: number) => Promise<void>;
}

const MAX_TEXTO = 4000;

export function crearTelegram(op: OpcionesTelegram = {}): AdaptadorCanal {
  const f: typeof fetch = op.fetch ?? ((...a) => fetch(...a));
  const dormir = op.dormir ?? ((ms: number) => new Promise<void>((r) => setTimeout(r, ms)));

  async function llamar(token: string, metodo: string, cuerpo: Record<string, unknown>): Promise<{ message_id?: number }> {
    const r = await f(`${API}/bot${token}/${metodo}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(cuerpo),
    });
    const j = (await r.json().catch(() => ({}))) as { ok?: boolean; description?: string; result?: { message_id?: number } };
    // El motivo viene en `description` (chat not found, bot was blocked by the user...). Nunca lleva el token.
    if (!r.ok || j.ok === false) throw new Error(`telegram ${metodo} ${r.status}: ${j.description ?? "sin detalle"}`);
    return j.result ?? {};
  }

  function descargable(token: string, a: TgArchivo, tipo: AdjuntoEntrante["tipo"], nombre?: string): AdjuntoEntrante {
    return {
      tipo,
      mime: a.mime_type,
      nombre: nombre ?? a.file_name,
      obtener: async () => {
        const info = await f(`${API}/bot${token}/getFile?file_id=${encodeURIComponent(a.file_id)}`);
        const j = (await info.json().catch(() => null)) as { ok?: boolean; result?: { file_path?: string } } | null;
        const ruta = j?.ok ? j.result?.file_path : undefined;
        if (!ruta) return null;
        const r = await f(`${API}/file/bot${token}/${ruta}`);
        if (!r.ok) return null;
        return { bytes: new Uint8Array(await r.arrayBuffer()), mime: a.mime_type ?? r.headers.get("content-type") ?? undefined };
      },
    };
  }

  return {
    canales: ["telegram"],
    ruta: "/webhooks/telegram",

    capacidades(): Capacidades {
      return { imagenes: true, documentos: true, ventana24h: false, maxTexto: MAX_TEXTO, pie: true };
    },

    faltantes(env: Env): string[] {
      return faltantesDe({ TELEGRAM_BOT_TOKEN_JUAN: !!env.TELEGRAM_BOT_TOKEN_JUAN, TELEGRAM_WEBHOOK_SECRET_JUAN: !!env.TELEGRAM_WEBHOOK_SECRET_JUAN });
    },

    configurado(env: Env): boolean {
      return this.faltantes(env, "telegram").length === 0;
    },

    async recibir(req: Request, env: Env): Promise<ResultadoWebhook> {
      const nada = (respuesta: Response): ResultadoWebhook => ({ respuesta, entrantes: [] });
      if (req.method !== "POST") return nada(new Response("método no permitido", { status: 405 }));
      // Falla cerrado: sin secreto configurado no entra nadie.
      const secreto = env.TELEGRAM_WEBHOOK_SECRET_JUAN;
      if (!secreto || !tokensIguales(req.headers.get("x-telegram-bot-api-secret-token") ?? "", secreto)) {
        return nada(new Response("no autorizado", { status: 401 }));
      }
      let update: TgUpdate;
      try {
        update = (await req.json()) as TgUpdate;
      } catch {
        return nada(ok200());
      }
      // Una reacción del cliente (solo si el webhook pidió `message_reaction`): un evento, no un mensaje.
      const reaccion = update.message_reaction;
      if (reaccion) {
        if (reaccion.chat?.type !== "private" || !reaccion.user || reaccion.user.is_bot) return nada(ok200());
        // Telegram deja varias por persona (las de pago, emojis propios): vale el último emoji normal; ninguno = la quitó.
        const nuevas = reaccion.new_reaction ?? [];
        const emoji = [...nuevas].reverse().find((r) => r.type === "emoji" && typeof r.emoji === "string")?.emoji ?? "";
        if (nuevas.length > 0 && !emoji) return nada(ok200());
        const chat = String(reaccion.chat.id);
        return {
          respuesta: ok200(),
          entrantes: [],
          eventos: [{ tipo: "reaccion", canal: "telegram", id_externo: chat, id_mensaje: `tg:${chat}:${reaccion.message_id}`, emoji: emoji.slice(0, 32), ts: reaccion.date * 1000 }],
        };
      }
      const msg = update.message;
      // Botones, ediciones, altas en grupos: nada que contestar. Siempre 200 (un error haría reintentar a Telegram).
      if (!msg || msg.chat.type !== "private" || msg.from?.is_bot) return nada(ok200());
      const token = env.TELEGRAM_BOT_TOKEN_JUAN ?? "";

      const texto = (msg.text ?? msg.caption ?? "").trim();
      const comando = texto.toLowerCase().split(/[\s@]/)[0];
      // /miid: el chat_id de quien escribe (sirve para ALERTA_TELEGRAM_CHAT_ID). Cada quien ve solo el suyo.
      if (comando === "/miid" && token) {
        await llamar(token, "sendMessage", { chat_id: msg.chat.id, text: `Tu chat id es: ${msg.chat.id}` }).catch(() => {});
        return nada(ok200());
      }

      const adjuntos: AdjuntoEntrante[] = [];
      if (msg.photo?.length) adjuntos.push(descargable(token, msg.photo[msg.photo.length - 1], "imagen"));
      if (msg.voice) adjuntos.push(descargable(token, msg.voice, "audio"));
      if (msg.audio) adjuntos.push(descargable(token, msg.audio, "audio"));
      if (msg.document) adjuntos.push(descargable(token, msg.document, "documento"));
      if (msg.video) adjuntos.push(descargable(token, msg.video, "video"));

      const citado = msg.reply_to_message;
      const entrante: Entrante = {
        canal: "telegram",
        id_externo: String(msg.chat.id),
        id_mensaje: `tg:${msg.chat.id}:${msg.message_id}`,
        nombre: msg.from?.first_name,
        // «/start» es el saludo de Telegram: para el bot es un «hola».
        texto: comando === "/start" ? "Hola" : texto || undefined,
        adjuntos,
        ts: msg.date * 1000,
        ...(citado?.message_id !== undefined
          ? { cita: { id: `tg:${msg.chat.id}:${citado.message_id}`, ...(textoDeCitado(citado, msg.quote?.text) ? { texto: textoDeCitado(citado, msg.quote?.text) } : {}), deLaTienda: !!citado.from?.is_bot } }
          : {}),
        ...(msg.forward_origin || msg.forward_date ? { reenviado: "una" as const } : {}),
      };
      if (!entrante.texto && adjuntos.length === 0) return nada(ok200());
      return { respuesta: ok200(), entrantes: [entrante] };
    },

    async enviar(_canal: CanalId, salida: Saliente, env: Env): Promise<ResultadoEnvio> {
      const token = env.TELEGRAM_BOT_TOKEN_JUAN;
      if (!token) throw new Error("Falta TELEGRAM_BOT_TOKEN_JUAN");
      const chat = salida.para;
      const ids: string[] = [];
      let burbujas = 0;
      let medios = 0;
      // «Responder» desde Odoo: el primer mensaje cita al del cliente (si ya no existe, sale igual, sin la cita).
      const citado = idDeMensajeTelegram(salida.responderA, chat);
      let cita: Record<string, unknown> = citado !== undefined ? { reply_parameters: { message_id: citado, allow_sending_without_reply: true } } : {};
      const usarCita = () => {
        const c = cita;
        cita = {};
        return c;
      };
      try {
        for (let i = 0; i < salida.burbujas.length; i++) {
          if (i > 0) await dormir(salida.esperaMs ?? 1000);
          const r = await llamar(token, "sendMessage", { chat_id: chat, text: sinNegritas(salida.burbujas[i]), ...usarCita() });
          burbujas++;
          if (r.message_id !== undefined) ids.push(`tg:${chat}:${r.message_id}`);
        }
        for (const m of salida.medios) {
          const esFoto = m.tipo === "imagen";
          const pie = { ...(m.pie ? { caption: sinNegritas(m.pie).slice(0, 1000) } : {}), ...usarCita() };
          let r: { message_id?: number };
          try {
            r = await llamar(token, esFoto ? "sendPhoto" : "sendDocument", { chat_id: chat, [esFoto ? "photo" : "document"]: m.url, ...pie });
          } catch (e) {
            // Telegram baja la foto por su cuenta. Si responde «400» (no la acepta como foto: formato, tamaño o proporciones; o no pudo
            // abrir la dirección), se prueba como ARCHIVO, que es más permisivo. Un 429 o un corte de red no se maquillan: se reintenta.
            if (!esFoto || !/ 400: /.test(e instanceof Error ? e.message : String(e))) throw e;
            try {
              r = await llamar(token, "sendDocument", { chat_id: chat, document: m.url, ...pie });
            } catch (e2) {
              throw new Error(`${e instanceof Error ? e.message : String(e)} | como archivo: ${e2 instanceof Error ? e2.message : String(e2)}`);
            }
          }
          medios++;
          if (r.message_id !== undefined) ids.push(`tg:${chat}:${r.message_id}`);
        }
      } catch (e) {
        // Lo que ya salió no se repite: quien reintente manda solo lo que falta.
        if (burbujas + medios > 0) throw new EnvioParcialError(e instanceof Error ? e.message : String(e), { burbujas, medios, ids });
        throw e;
      }
      return { ids };
    },

    async fotoDePerfil(_canal: CanalId, para: string, env: Env): Promise<{ bytes: Uint8Array; mime: string } | null> {
      const token = env.TELEGRAM_BOT_TOKEN_JUAN;
      if (!token || !/^\d{1,20}$/.test(para)) return null;
      const lista = await f(`${API}/bot${token}/getUserProfilePhotos?user_id=${para}&limit=1`);
      const j = (await lista.json().catch(() => null)) as { ok?: boolean; result?: { photos?: { file_id: string; width: number; file_size?: number }[][] } } | null;
      // La primera foto viene en varios tamaños, de menor a mayor: la más grande que no pase de 400 px (alcanza para un avatar).
      const tamanos = j?.ok ? j.result?.photos?.[0] : undefined;
      if (!tamanos?.length) return null;
      const elegida = [...tamanos].reverse().find((t) => t.width <= 400) ?? tamanos[0];
      const info = await f(`${API}/bot${token}/getFile?file_id=${encodeURIComponent(elegida.file_id)}`);
      const ji = (await info.json().catch(() => null)) as { ok?: boolean; result?: { file_path?: string } } | null;
      const ruta = ji?.ok ? ji.result?.file_path : undefined;
      if (!ruta) return null;
      const r = await f(`${API}/file/bot${token}/${ruta}`);
      if (!r.ok) return null;
      const bytes = new Uint8Array(await r.arrayBuffer());
      if (bytes.length === 0 || bytes.length > MAX_FOTO_DE_PERFIL_BYTES) return null;
      return { bytes, mime: "image/jpeg" };
    },

    async escribiendo(_canal: CanalId, para: string, env: Env): Promise<void> {
      if (env.TELEGRAM_BOT_TOKEN_JUAN) await llamar(env.TELEGRAM_BOT_TOKEN_JUAN, "sendChatAction", { chat_id: para, action: "typing" }).catch(() => {});
    },

    async salud(canal: CanalId, env: Env): Promise<SaludCanal> {
      return { configurado: this.configurado(env, canal), faltan: this.faltantes(env, canal), conectado: null };
    },
  };
}

/** Para avisos a una persona (el cron de salud): un mensaje de texto a un chat. Nunca lanza. */
export async function avisarPorTelegram(env: Env, chatId: string, texto: string, f: typeof fetch = fetch): Promise<boolean> {
  const token = env.TELEGRAM_BOT_TOKEN_JUAN;
  if (!token || !chatId) return false;
  try {
    const r = await f(`${API}/bot${token}/sendMessage`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ chat_id: chatId, text: texto }),
    });
    return r.ok;
  } catch {
    return false;
  }
}

export type { MedioSaliente };
