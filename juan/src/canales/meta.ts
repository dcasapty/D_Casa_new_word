// Messenger e Instagram (Meta oficial). Una sola app de Meta cubre ambos: el webhook trae el mismo formato
// (`entry[].messaging[]`) y el envío es la Send API (`graph.facebook.com/<versión>/me/messages`) con el token de la Página.
//
//   · GET  /webhooks/meta  → verificación (hub.verify_token = META_VERIFY_TOKEN; se devuelve hub.challenge)
//   · POST /webhooks/meta  → firma `X-Hub-Signature-256` (HMAC-SHA256 del cuerpo con META_APP_SECRET), siempre
//   · Solo se puede escribir dentro de las 24 h del último mensaje del cliente (messaging_type RESPONSE).
//   · `is_echo` = lo escribió la Página (una persona desde la bandeja de Meta, o este mismo bot): `propio:true`.

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

interface MetaEvento {
  sender?: { id?: string };
  recipient?: { id?: string };
  timestamp?: number;
  message?: {
    mid?: string;
    text?: string;
    is_echo?: boolean;
    attachments?: { type?: string; payload?: { url?: string } }[];
  };
}

interface MetaCuerpo {
  object?: string;
  entry?: { id?: string; messaging?: MetaEvento[] }[];
}

export interface OpcionesMeta {
  fetch?: typeof fetch;
  dormir?: (ms: number) => Promise<void>;
}

const TIPOS_ADJUNTO: Record<string, AdjuntoEntrante["tipo"]> = { image: "imagen", audio: "audio", video: "video", file: "documento" };

/** Convierte un POST de Meta en 0..N mensajes (un POST puede traer varios). */
export function eventosDeMeta(cuerpo: MetaCuerpo, ahora: number): Entrante[] {
  const canal: CanalId = cuerpo.object === "instagram" ? "instagram" : "messenger";
  const salida: Entrante[] = [];
  for (const entrada of cuerpo.entry ?? []) {
    for (const ev of entrada.messaging ?? []) {
      const m = ev.message;
      // Recibos de entrega/lectura, postbacks y reacciones no traen `message`.
      if (!m) continue;
      const eco = m.is_echo === true;
      // En un eco, el cliente es el DESTINATARIO.
      const cliente = eco ? ev.recipient?.id : ev.sender?.id;
      if (!cliente) continue;
      const adjuntos: AdjuntoEntrante[] = [];
      let texto = m.text?.trim() || undefined;
      for (const a of m.attachments ?? []) {
        const tipo = TIPOS_ADJUNTO[a.type ?? ""];
        if (tipo && a.payload?.url) adjuntos.push({ tipo, url: a.payload.url });
        else if (a.type === "location") texto ??= "(el cliente mandó una ubicación)";
        else if (a.type === "fallback" && !texto) texto = "(el cliente compartió un enlace)";
      }
      if (!texto && adjuntos.length === 0) continue;
      salida.push({
        canal,
        id_externo: String(cliente),
        id_mensaje: m.mid ?? `meta:${cliente}:${ev.timestamp ?? ahora}`,
        texto,
        adjuntos,
        ts: aMilisegundos(ev.timestamp, ahora),
        propio: eco,
      });
    }
  }
  return salida;
}

const CAPACIDADES: Record<"messenger" | "instagram", Capacidades> = {
  messenger: { imagenes: true, documentos: true, ventana24h: true, maxTexto: 1900 },
  // Instagram no admite documentos y su texto es más corto.
  instagram: { imagenes: true, documentos: false, ventana24h: true, maxTexto: 950 },
};

export function crearMeta(op: OpcionesMeta = {}): AdaptadorCanal {
  const f: typeof fetch = op.fetch ?? ((...a) => fetch(...a));
  const dormir = op.dormir ?? ((ms: number) => new Promise<void>((r) => setTimeout(r, ms)));

  async function enviarUno(env: Env, cuerpo: Record<string, unknown>): Promise<string | undefined> {
    const token = env.META_PAGE_TOKEN;
    if (!token) throw new Error("Falta META_PAGE_TOKEN");
    const r = await f(urlGraph(env, "me/messages"), {
      method: "POST",
      headers: { "content-type": "application/json", authorization: `Bearer ${token}` },
      body: JSON.stringify(cuerpo),
    });
    const j = (await r.json().catch(() => ({}))) as { message_id?: string; error?: { message?: string; code?: number } };
    // Fuera de la ventana de 24 h, sin permiso o con un destinatario inválido, Meta contesta con un error concreto.
    if (!r.ok || j.error) throw new Error(`meta send ${r.status}: ${j.error?.message ?? "sin detalle"} (código ${j.error?.code ?? "?"})`);
    return j.message_id;
  }

  return {
    canales: ["messenger", "instagram"],
    ruta: "/webhooks/meta",

    capacidades(canal: CanalId): Capacidades {
      return canal === "instagram" ? CAPACIDADES.instagram : CAPACIDADES.messenger;
    },

    faltantes(env: Env): string[] {
      return faltantesDe({ META_PAGE_TOKEN: !!env.META_PAGE_TOKEN, META_APP_SECRET: !!env.META_APP_SECRET, META_VERIFY_TOKEN: !!env.META_VERIFY_TOKEN });
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

      // La firma se calcula sobre el cuerpo CRUDO: se lee como texto antes de interpretarlo.
      const crudo = await req.text();
      if (!(await firmaMetaValida(crudo, req.headers.get("x-hub-signature-256"), env.META_APP_SECRET))) {
        return nada(new Response("firma inválida", { status: 401 }));
      }
      let cuerpo: MetaCuerpo;
      try {
        cuerpo = JSON.parse(crudo) as MetaCuerpo;
      } catch {
        return nada(ok200());
      }
      return { respuesta: json({ ok: true }), entrantes: eventosDeMeta(cuerpo, Date.now()) };
    },

    async enviar(canal: CanalId, salida: Saliente, env: Env): Promise<ResultadoEnvio> {
      const ids: string[] = [];
      const destino = { id: salida.para };
      const cap = canal === "instagram" ? CAPACIDADES.instagram : CAPACIDADES.messenger;
      for (let i = 0; i < salida.burbujas.length; i++) {
        if (i > 0) await dormir(salida.esperaMs ?? 1000);
        const id = await enviarUno(env, { recipient: destino, messaging_type: "RESPONSE", message: { text: salida.burbujas[i] } });
        if (id) ids.push(id);
      }
      for (const m of salida.medios) {
        if (m.tipo === "documento" && !cap.documentos) continue;
        const id = await enviarUno(env, {
          recipient: destino,
          messaging_type: "RESPONSE",
          message: { attachment: { type: m.tipo === "imagen" ? "image" : "file", payload: { url: m.url, is_reusable: true } } },
        });
        if (id) ids.push(id);
      }
      return { ids };
    },

    async escribiendo(_canal: CanalId, para: string, env: Env): Promise<void> {
      await enviarUno(env, { recipient: { id: para }, sender_action: "typing_on" }).catch(() => {});
    },

    async salud(canal: CanalId, env: Env): Promise<SaludCanal> {
      return { configurado: this.configurado(env, canal), faltan: this.faltantes(env, canal), conectado: null };
    },
  };
}
