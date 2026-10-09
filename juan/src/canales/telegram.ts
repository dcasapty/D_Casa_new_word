// Telegram: el canal de PRUEBAS (clientas de prueba y avisos). El webhook se registra con un
// secreto (`secret_token`) que Telegram devuelve en la cabecera `X-Telegram-Bot-Api-Secret-Token`.
//
// Un archivo de Telegram NO se puede abrir con su file_id: hay que pedir `getFile` y bajarlo de una URL
// que lleva el token del bot adentro. Esa URL nunca sale de aquí (ni a Odoo ni al modelo): se descargan
// los bytes y el motor los guarda con su propia URL temporal y firmada.

import type { Env } from "../env";
import { tokensIguales } from "../seguridad";
import {
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
}

export interface TgUpdate {
  update_id: number;
  message?: TgMensaje;
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
      return { imagenes: true, documentos: true, ventana24h: false, maxTexto: MAX_TEXTO };
    },

    configurado(env: Env): boolean {
      return !!env.TELEGRAM_BOT_TOKEN_JUAN && !!env.TELEGRAM_WEBHOOK_SECRET_JUAN;
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

      const entrante: Entrante = {
        canal: "telegram",
        id_externo: String(msg.chat.id),
        id_mensaje: `tg:${msg.chat.id}:${msg.message_id}`,
        nombre: msg.from?.first_name,
        // «/start» es el saludo de Telegram: para el bot es un «hola».
        texto: comando === "/start" ? "Hola" : texto || undefined,
        adjuntos,
        ts: msg.date * 1000,
      };
      if (!entrante.texto && adjuntos.length === 0) return nada(ok200());
      return { respuesta: ok200(), entrantes: [entrante] };
    },

    async enviar(_canal: CanalId, salida: Saliente, env: Env): Promise<ResultadoEnvio> {
      const token = env.TELEGRAM_BOT_TOKEN_JUAN;
      if (!token) throw new Error("Falta TELEGRAM_BOT_TOKEN_JUAN");
      const chat = salida.para;
      const ids: string[] = [];
      for (let i = 0; i < salida.burbujas.length; i++) {
        if (i > 0) await dormir(salida.esperaMs ?? 1000);
        const r = await llamar(token, "sendMessage", { chat_id: chat, text: salida.burbujas[i] });
        if (r.message_id !== undefined) ids.push(`tg:${chat}:${r.message_id}`);
      }
      for (const m of salida.medios) {
        const esFoto = m.tipo === "imagen";
        const r = await llamar(token, esFoto ? "sendPhoto" : "sendDocument", {
          chat_id: chat,
          [esFoto ? "photo" : "document"]: m.url,
          ...(m.pie ? { caption: m.pie.slice(0, 1000) } : {}),
        });
        if (r.message_id !== undefined) ids.push(`tg:${chat}:${r.message_id}`);
      }
      return { ids };
    },

    async escribiendo(_canal: CanalId, para: string, env: Env): Promise<void> {
      if (env.TELEGRAM_BOT_TOKEN_JUAN) await llamar(env.TELEGRAM_BOT_TOKEN_JUAN, "sendChatAction", { chat_id: para, action: "typing" }).catch(() => {});
    },

    async salud(canal: CanalId, env: Env): Promise<SaludCanal> {
      return { configurado: this.configurado(env, canal), conectado: null };
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
