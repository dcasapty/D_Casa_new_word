// WhatsApp Cloud API (oficial, Meta). Adaptador COMPLETO pero APAGADO: es el plan B si bloquean el número del QR.
// Se enciende en Odoo (`canales_activos.whatsapp_cloud = true`) cuando la dueña tenga la cuenta de Meta Business
// verificada y estos datos cargados: WHATSAPP_PHONE_NUMBER_ID (variable), WHATSAPP_CLOUD_TOKEN, META_APP_SECRET y
// META_VERIFY_TOKEN (secretos). Mientras tanto el webhook responde 200 y no hace nada.
//
//   · GET  /webhooks/whatsapp-cloud → verificación (hub.verify_token = META_VERIFY_TOKEN)
//   · POST /webhooks/whatsapp-cloud → firma X-Hub-Signature-256 con META_APP_SECRET
//   · Texto libre solo dentro de las 24 h del último mensaje del cliente (después hace falta una plantilla aprobada).
//   · Con «coexistencia» (la app WhatsApp Business sigue en el teléfono) lo que la vendedora escribe llega como eco
//     (`smb_message_echoes`) y se trata como `propio:true`. NO VERIFICADO contra la documentación de Meta: el proxy de
//     la ronda 7 bloqueó developers.facebook.com. Revisar la forma exacta del eco antes de activar.

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
  type ResultadoEnvio,
  type ResultadoWebhook,
  type Saliente,
  type SaludCanal,
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
}

interface WaCambio {
  field?: string;
  value?: {
    contacts?: { profile?: { name?: string }; wa_id?: string }[];
    messages?: WaMensaje[];
    message_echoes?: WaMensaje[];
  };
}

interface WaCuerpo {
  object?: string;
  entry?: { id?: string; changes?: WaCambio[] }[];
}

export interface OpcionesWhatsappCloud {
  fetch?: typeof fetch;
  dormir?: (ms: number) => Promise<void>;
}

const CAPACIDADES: Capacidades = { imagenes: true, documentos: true, ventana24h: true, maxTexto: 3500 };

export function crearWhatsappCloud(op: OpcionesWhatsappCloud = {}): AdaptadorCanal {
  const f: typeof fetch = op.fetch ?? ((...a) => fetch(...a));
  const dormir = op.dormir ?? ((ms: number) => new Promise<void>((r) => setTimeout(r, ms)));

  /** Un archivo entrante: media_id → URL (con Bearer) → bytes (con Bearer). */
  function descargable(env: Env, mediaId: string, tipo: AdjuntoEntrante["tipo"], mime?: string, nombre?: string): AdjuntoEntrante {
    return {
      tipo,
      mime,
      nombre,
      obtener: async () => {
        const token = env.WHATSAPP_CLOUD_TOKEN;
        if (!token) return null;
        const meta = await f(urlGraph(env, encodeURIComponent(mediaId)), { headers: { authorization: `Bearer ${token}` } });
        if (!meta.ok) return null;
        const info = (await meta.json().catch(() => ({}))) as { url?: string; mime_type?: string };
        if (!info.url) return null;
        const r = await f(info.url, { headers: { authorization: `Bearer ${token}` } });
        if (!r.ok) return null;
        return { bytes: new Uint8Array(await r.arrayBuffer()), mime: info.mime_type ?? mime };
      },
    };
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
        texto = "(el cliente mandó un sticker)";
        break;
      default:
        break;
    }
    texto = texto?.trim() || undefined;
    if (!texto && adjuntos.length === 0) return null;
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
    };
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
    if (!r.ok || j.error) throw new Error(`whatsapp cloud ${r.status}: ${j.error?.message ?? "sin detalle"} (código ${j.error?.code ?? "?"})`);
    return j.messages?.[0]?.id;
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
      for (const entrada of cuerpo.entry ?? []) {
        for (const cambio of entrada.changes ?? []) {
          const v = cambio.value;
          if (!v) continue;
          const nombres = new Map<string, string>();
          for (const c of v.contacts ?? []) if (c.wa_id && c.profile?.name) nombres.set(c.wa_id, c.profile.name);
          // Los recibos de entrega/lectura vienen en `statuses` y se ignoran.
          for (const m of v.messages ?? []) {
            const e = aEntrante(env, m, m.from ? nombres.get(m.from) : undefined, false, ahora);
            if (e) entrantes.push(e);
          }
          for (const m of v.message_echoes ?? []) {
            const e = aEntrante(env, m, undefined, true, ahora);
            if (e) entrantes.push(e);
          }
        }
      }
      return { respuesta: json({ ok: true }), entrantes };
    },

    async enviar(_canal: CanalId, salida: Saliente, env: Env): Promise<ResultadoEnvio> {
      const ids: string[] = [];
      for (let i = 0; i < salida.burbujas.length; i++) {
        if (i > 0) await dormir(salida.esperaMs ?? 1000);
        const id = await enviarUno(env, { to: salida.para, type: "text", text: { preview_url: false, body: salida.burbujas[i] } });
        if (id) ids.push(id);
      }
      for (const m of salida.medios) {
        const id = await enviarUno(
          env,
          m.tipo === "imagen"
            ? { to: salida.para, type: "image", image: { link: m.url, ...(m.pie ? { caption: m.pie.slice(0, 1000) } : {}) } }
            : { to: salida.para, type: "document", document: { link: m.url, ...(m.nombre ? { filename: m.nombre } : {}), ...(m.pie ? { caption: m.pie.slice(0, 1000) } : {}) } },
        );
        if (id) ids.push(id);
      }
      return { ids };
    },

    async salud(canal: CanalId, env: Env): Promise<SaludCanal> {
      return { configurado: this.configurado(env, canal), faltan: this.faltantes(env, canal), conectado: null };
    },
  };
}
