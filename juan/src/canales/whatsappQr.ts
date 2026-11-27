// WhatsApp por QR, vía el puente (`puente-wa/`, Baileys). Contrato en docs/JUAN.md:
//
//   Puente → Worker:  POST /webhooks/whatsapp-qr
//     {id_mensaje, de, nombre, tipo:"texto|imagen|audio|documento|video", texto?,
//      medio?:{url_temporal|base64, mime, nombre}, ts, propio:false}
//     `propio:true` = la vendedora escribió desde el teléfono: se registra como `vendedora` y el bot se calla.
//     Ubicación (2026-11-25, docs/UBICACION.md): `ubicacion?:{lat, lon, nombre?, direccion?}` (la que compartió la clienta) o
//     `ubicacion_omitida:true` (la traía, pero el puente la guardó para reintentar y ahí nunca guarda coordenadas). Un puente de antes
//     la manda como texto («Ubicación compartida: lat, lon (lugar)»): se reconoce igual y las coordenadas salen del texto.
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
  EnvioParcialError,
  MAX_FOTO_DE_PERFIL_BYTES,
} from "./tipos";
import { crearUbicacion, TEXTO_UBICACION_COMPARTIDA, TEXTO_UBICACION_ILEGIBLE, TEXTO_UBICACION_PROPIA, type UbicacionEntrante } from "./ubicacion";

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
  /** La ubicación que compartió la clienta (📎 › Ubicación, o la de tiempo real). Se valida aquí: el puente puede ser de otra versión. */
  ubicacion?: { lat?: unknown; lon?: unknown; nombre?: unknown; direccion?: unknown } | null;
  /** La traía, pero el puente la guardó en su cola de pendientes sin coordenadas: hay que pedírsela otra vez. */
  ubicacion_omitida?: boolean;
}

/** Cómo mandaba la ubicación un puente de antes del 2026-11-25: como texto, CON las coordenadas. */
const UBICACION_COMO_TEXTO = /^Ubicación compartida: (?:(-?\d+(?:\.\d+)?), (-?\d+(?:\.\d+)?)|sin coordenadas)(?: \(([\s\S]*)\))?$/;

/**
 * La ubicación de un mensaje del puente y el texto que lo reemplaza (sin coordenadas). `null` = el mensaje no es una ubicación. Uno
 * `propio` (la tienda compartió una ubicación desde el teléfono) no es el punto de entrega de nadie: solo el texto.
 */
export function ubicacionDelPuente(c: Pick<EntranteDelPuente, "ubicacion" | "ubicacion_omitida" | "texto" | "propio">): { texto: string; ubicacion?: UbicacionEntrante; omitida?: true } | null {
  const propio = c.propio === true;
  if (c.ubicacion && typeof c.ubicacion === "object") {
    if (propio) return { texto: TEXTO_UBICACION_PROPIA };
    const u = crearUbicacion(c.ubicacion.lat, c.ubicacion.lon, "whatsapp", { nombre: c.ubicacion.nombre, direccion: c.ubicacion.direccion });
    return u ? { texto: TEXTO_UBICACION_COMPARTIDA, ubicacion: u } : { texto: TEXTO_UBICACION_ILEGIBLE };
  }
  if (c.ubicacion_omitida === true) return propio ? { texto: TEXTO_UBICACION_PROPIA } : { texto: TEXTO_UBICACION_COMPARTIDA, omitida: true };
  const viejo = UBICACION_COMO_TEXTO.exec((c.texto ?? "").trim());
  if (!viejo) return null;
  if (propio) return { texto: TEXTO_UBICACION_PROPIA };
  const lugar = (viejo[3] ?? "").split(", ");
  const u = viejo[1] !== undefined ? crearUbicacion(viejo[1], viejo[2], "whatsapp", { nombre: lugar[0], direccion: lugar.slice(1).join(", ") }) : null;
  return u ? { texto: TEXTO_UBICACION_COMPARTIDA, ubicacion: u } : { texto: TEXTO_UBICACION_ILEGIBLE };
}

/**
 * Lo que el puente alcanzó a mandar antes de fallar (`{enviados:{chunks, medios}, ids}`), o null si no salió nada.
 * `chunks` cuenta también los restos de un pie largo, que van DESPUÉS de sus archivos: aquí solo importan las burbujas propias.
 */
function enviadoSegunElPuente(cuerpo: string, salida: Saliente): { burbujas: number; medios: number; ids: string[] } | null {
  let j: { enviados?: { chunks?: unknown; medios?: unknown }; ids?: unknown } | null;
  try {
    j = JSON.parse(cuerpo) as typeof j;
  } catch {
    return null;
  }
  const n = (v: unknown) => (typeof v === "number" && Number.isFinite(v) && v > 0 ? Math.floor(v) : 0);
  const burbujas = Math.min(n(j?.enviados?.chunks), salida.burbujas.length);
  const medios = Math.min(n(j?.enviados?.medios), salida.medios.length);
  if (burbujas + medios === 0) return null;
  return { burbujas, medios, ids: Array.isArray(j?.ids) ? j.ids.filter((x): x is string => typeof x === "string") : [] };
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
  ubicacion: TEXTO_UBICACION_ILEGIBLE,
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
    // El punto de entrega va aparte (a Odoo): el texto que se guarda y que ve el modelo nunca lleva las coordenadas.
    const deUbicacion = ubicacionDelPuente(c);
    let texto = deUbicacion?.texto ?? ((c.texto ?? "").trim() || undefined);
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
      ...(deUbicacion?.ubicacion ? { ubicacion: deUbicacion.ubicacion } : {}),
      ...(deUbicacion?.omitida ? { ubicacion_omitida: "whatsapp" as const } : {}),
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
      if (!r.ok) {
        const texto = await r.text().catch(() => "");
        const mensaje = `puente /api/enviar → ${r.status} ${texto.slice(0, 200)}`;
        // El puente dice qué alcanzó a salir (`enviados`, `ids`): eso no se repite al reintentar.
        const parcial = enviadoSegunElPuente(texto, salida);
        throw parcial ? new EnvioParcialError(mensaje, parcial) : new Error(mensaje);
      }
      return { ids: [] };
    },

    async fotoDePerfil(_canal: CanalId, para: string, env: Env): Promise<{ bytes: Uint8Array; mime: string } | null> {
      if (!esChatDeUnaPersona(para)) return null;
      const r = await llamarAlPuente(env, "/api/foto-perfil", { method: "POST", body: JSON.stringify({ para }) });
      // 404 = sin foto o no la deja ver: lo normal. Cualquier otra cosa es un fallo que el motor anota.
      if (r.status === 404) return null;
      if (!r.ok) throw new Error(`puente /api/foto-perfil → ${r.status}`);
      const j = (await r.json().catch(() => null)) as { ok?: boolean; mime?: string; base64?: string } | null;
      if (!j?.ok || typeof j.base64 !== "string" || !j.base64 || j.base64.length > Math.ceil((MAX_FOTO_DE_PERFIL_BYTES * 4) / 3) + 8) return null;
      let binario: string;
      try {
        binario = atob(j.base64);
      } catch {
        return null;
      }
      const bytes = Uint8Array.from(binario, (c) => c.charCodeAt(0));
      return bytes.length > 0 && bytes.length <= MAX_FOTO_DE_PERFIL_BYTES ? { bytes, mime: typeof j.mime === "string" && j.mime ? j.mime : "image/jpeg" } : null;
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
