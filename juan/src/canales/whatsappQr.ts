// WhatsApp por QR, vía el puente (`puente-wa/`, Baileys). Contrato en docs/JUAN.md:
//
//   Puente → Worker:  POST /webhooks/whatsapp-qr
//     {id_mensaje, de, nombre, tipo:"texto|imagen|audio|documento|video", texto?,
//      medio?:{url_temporal|base64, mime, nombre}, ts, propio:false}
//     `propio:true` = la vendedora escribió desde el teléfono: se registra como `vendedora` y el bot se calla.
//   Worker → Puente:  POST /api/enviar  {para, chunks:[texto...], medios?:[{tipo, url, nombre?, mime?, pie?}]}
//     (1 s entre burbujas lo pone el puente). GET /api/estado dice si está conectado o pide QR.
//
// Es un canal NO oficial (Baileys): el número puede ser bloqueado. Decisión de la dueña, con mitigaciones:
// ritmo conservador de envío, seguimientos limitados y el adaptador de la Cloud API listo como plan B.

import type { Env } from "../env";
import { tokenDelPuente, tokenParaCabecera, tokensIguales } from "../seguridad";
import {
  aMilisegundos,
  faltantesDe,
  json,
  type AdaptadorCanal,
  type AdjuntoEntrante,
  type Capacidades,
  type CanalId,
  type Entrante,
  type ResultadoEnvio,
  type ResultadoWebhook,
  type Saliente,
  type SaludCanal,
  type TipoAdjunto,
} from "./tipos";

interface EntranteDelPuente {
  id_mensaje?: string;
  de?: string | null;
  nombre?: string | null;
  tipo?: string | null;
  texto?: string | null;
  medio?: { url_temporal?: string; base64?: string; mime?: string; nombre?: string } | null;
  /** El puente no pudo adjuntar el archivo (muy grande, descarga fallida): el mensaje igual llega, con el motivo. */
  medio_omitido?: { motivo?: string; mime?: string; bytes?: number } | null;
  ts?: number | string;
  propio?: boolean;
}

/** Estados, grupos, canales y bots de Meta no son un cliente escribiéndole al negocio. */
export function esChatDeUnaPersona(jid: string | null | undefined): boolean {
  const j = (jid ?? "").trim();
  return !!j && !j.endsWith("@broadcast") && !j.endsWith("@g.us") && !j.endsWith("@newsletter") && !j.endsWith("@bot");
}

/** `50760261919@s.whatsapp.net` → `50760261919`. Un `…@lid` se conserva entero: es lo único con lo que se puede contestar. */
export function idExternoDeJid(jid: string): string {
  const j = jid.trim();
  const m = /^(\d+)(?::\d+)?@(?:s\.whatsapp\.net|c\.us)$/.exec(j);
  if (m) return m[1];
  return j.replace(/^\+/, "");
}

const TIPOS: Record<string, TipoAdjunto> = { imagen: "imagen", image: "imagen", audio: "audio", documento: "documento", document: "documento", video: "video" };

const SIN_ARCHIVO: Record<string, string> = {
  sticker: "(el cliente mandó un sticker)",
  ubicacion: "(el cliente mandó una ubicación)",
  contacto: "(el cliente mandó un contacto)",
};

function decodificarBase64(b64: string): Uint8Array | null {
  try {
    return Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
  } catch {
    return null;
  }
}

export interface OpcionesWhatsappQr {
  fetch?: typeof fetch;
}

export function crearWhatsappQr(op: OpcionesWhatsappQr = {}): AdaptadorCanal {
  const f: typeof fetch = op.fetch ?? ((...a) => fetch(...a));

  function aEntrante(c: EntranteDelPuente, ahora: number): Entrante | null {
    const jid = (c.de ?? "").trim();
    if (!jid || !c.id_mensaje || !esChatDeUnaPersona(jid)) return null;
    const idExterno = idExternoDeJid(jid);
    const adjuntos: AdjuntoEntrante[] = [];
    const tipo = TIPOS[(c.tipo ?? "").toLowerCase()];
    if (tipo && c.medio) {
      const a: AdjuntoEntrante = { tipo, mime: c.medio.mime, nombre: c.medio.nombre };
      const bytes = c.medio.base64 ? decodificarBase64(c.medio.base64) : null;
      if (bytes) a.bytes = bytes;
      else if (c.medio.url_temporal) {
        // La URL temporal del puente se descarga ahora: mañana ya no existe.
        const url = c.medio.url_temporal;
        a.url = url;
        a.obtener = async () => {
          const r = await f(url);
          return r.ok ? { bytes: new Uint8Array(await r.arrayBuffer()), mime: c.medio?.mime ?? r.headers.get("content-type") ?? undefined } : null;
        };
      }
      adjuntos.push(a);
    } else if (tipo && c.medio_omitido) {
      // Un video o una foto demasiado pesada: el puente no la pudo traer pero SÍ llegó un archivo. Sin esto el mensaje se perdía
      // (ni texto ni adjunto) y la clienta se quedaba sin respuesta; así queda registrado y una vendedora sabe que había un archivo.
      adjuntos.push({ tipo, mime: c.medio_omitido.mime });
    }
    let texto = (c.texto ?? "").trim() || undefined;
    if (!texto && adjuntos.length === 0) texto = SIN_ARCHIVO[(c.tipo ?? "").toLowerCase()];
    if (!texto && adjuntos.length === 0) return null; // reacciones, ediciones, borrados: nada que contestar
    return {
      canal: "whatsapp_qr",
      id_externo: idExterno,
      id_mensaje: c.id_mensaje,
      nombre: c.nombre?.trim() || undefined,
      celular: /^\d{8,15}$/.test(idExterno) ? idExterno : undefined,
      texto,
      adjuntos,
      ts: aMilisegundos(c.ts, ahora),
      propio: c.propio === true,
    };
  }

  function llamarAlPuente(env: Env, ruta: string, init: RequestInit = {}): Promise<Response> {
    if (!env.PUENTE) throw new Error("Falta el binding PUENTE (el puente de WhatsApp por QR)");
    if (!env.WA_TOKEN) throw new Error("Falta WA_TOKEN");
    // Por service binding: Cloudflare rechaza (error 1042) que un Worker llame a otro de la misma cuenta por su URL pública.
    return env.PUENTE.fetch(`https://puente${ruta}`, {
      ...init,
      headers: { "content-type": "application/json", ...(init.headers ?? {}), "x-wa-token-b64": tokenParaCabecera(env.WA_TOKEN) },
    });
  }

  return {
    canales: ["whatsapp_qr"],
    ruta: "/webhooks/whatsapp-qr",

    capacidades(): Capacidades {
      return { imagenes: true, documentos: true, ventana24h: false, maxTexto: 3500, pie: true };
    },

    faltantes(env: Env): string[] {
      // PUENTE es un service binding (no un secreto): se declara en wrangler.jsonc cuando el puente ya existe.
      return faltantesDe({ PUENTE: !!env.PUENTE, WA_TOKEN: !!env.WA_TOKEN });
    },

    configurado(env: Env): boolean {
      return this.faltantes(env, "whatsapp_qr").length === 0;
    },

    async recibir(req: Request, env: Env): Promise<ResultadoWebhook> {
      const nada = (respuesta: Response): ResultadoWebhook => ({ respuesta, entrantes: [] });
      if (req.method !== "POST") return nada(new Response("método no permitido", { status: 405 }));
      // Falla cerrado: sin WA_TOKEN un token vacío NO abre la puerta.
      if (!env.WA_TOKEN || !tokensIguales(tokenDelPuente(req), env.WA_TOKEN)) return nada(new Response("no autorizado", { status: 401 }));
      let cuerpo: unknown;
      try {
        cuerpo = await req.json();
      } catch {
        // 400 y no 200: el puente lo anota. Un mensaje que se pierde en silencio es peor que un error visible.
        return nada(new Response("no se pudo leer el mensaje", { status: 400 }));
      }
      const ahora = Date.now();
      const lista = (Array.isArray(cuerpo) ? cuerpo : [cuerpo]) as EntranteDelPuente[];
      const entrantes = lista.map((c) => aEntrante(c, ahora)).filter((e): e is Entrante => e !== null);
      // `esperar`: se contesta DESPUÉS de guardar el mensaje, para que el puente reintente si algo falla.
      return { respuesta: json({ ok: true, recibidos: entrantes.length }), entrantes, esperar: true };
    },

    async enviar(_canal: CanalId, salida: Saliente, env: Env): Promise<ResultadoEnvio> {
      if (!esChatDeUnaPersona(salida.para)) {
        // Mandarle texto a `status@broadcast` es PUBLICAR un estado con el número del negocio.
        throw new Error(`whatsapp_qr: ${salida.para} no es el chat de una persona; no se envía.`);
      }
      const r = await llamarAlPuente(env, "/api/enviar", {
        method: "POST",
        body: JSON.stringify({
          para: salida.para,
          chunks: salida.burbujas,
          ...(salida.medios.length
            ? { medios: salida.medios.map((m) => ({ tipo: m.tipo, url: m.url, nombre: m.nombre, mime: m.mime, pie: m.pie })) }
            : {}),
        }),
      });
      if (!r.ok) throw new Error(`puente /api/enviar → ${r.status} ${(await r.text().catch(() => "")).slice(0, 200)}`);
      return { ids: [] };
    },

    async salud(_canal: CanalId, env: Env): Promise<SaludCanal> {
      const faltan = this.faltantes(env, "whatsapp_qr");
      if (faltan.length > 0) return { configurado: false, faltan, conectado: null };
      try {
        const r = await llamarAlPuente(env, "/api/estado", { method: "GET" });
        if (!r.ok) return { configurado: true, faltan: [], conectado: false, detalle: `el puente contestó ${r.status}` };
        const j = (await r.json().catch(() => ({}))) as Record<string, unknown>;
        const texto = String(j.conexion ?? j.estado ?? "");
        const conectado = typeof j.conectado === "boolean" ? j.conectado : /^(conectad[ao]|open|connected)$/i.test(texto);
        return { configurado: true, faltan: [], conectado, detalle: texto || undefined };
      } catch (e) {
        return { configurado: true, faltan: [], conectado: false, detalle: String(e instanceof Error ? e.message : e).slice(0, 120) };
      }
    },
  };
}
