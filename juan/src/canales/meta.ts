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
  type MedioSaliente,
  type Saliente,
  type SaludCanal,
  EnvioParcialError,
  MAX_FOTO_DE_PERFIL_BYTES,
  sinNegritas,
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

/** De dónde sirve Meta las fotos de perfil: solo ahí se baja (la dirección viene de Meta, pero no se confía a ciegas). */
const SERVIDORES_DE_FOTO = /(^|\.)(fbsbx\.com|fbcdn\.net|cdninstagram\.com)$/i;

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

const texto = (v: unknown): string => (typeof v === "string" ? v.trim() : "");
/** Un nombre que se puede mostrar: sin caracteres de control y de 100 letras como mucho. */
const limpiarNombre = (n: string): string => n.replace(/[\u0000-\u001f\u007f]/g, "").trim().slice(0, 100);

/** Lo más grande que Messenger acepta como adjunto subido. */
export const MAX_ADJUNTO_MESSENGER_BYTES = 25 * 1024 * 1024;
/** Lo más grande que Instagram acepta como foto (documentación de Meta: png o jpeg, hasta 8 MB). */
export const MAX_FOTO_INSTAGRAM_BYTES = 8 * 1024 * 1024;

export function crearMeta(op: OpcionesMeta = {}): AdaptadorCanal {
  const f: typeof fetch = op.fetch ?? ((...a) => fetch(...a));
  const dormir = op.dormir ?? ((ms: number) => new Promise<void>((r) => setTimeout(r, ms)));

  async function publicar(env: Env, init: { headers: Record<string, string>; body: BodyInit }): Promise<string | undefined> {
    const token = env.META_PAGE_TOKEN;
    if (!token) throw new Error("Falta META_PAGE_TOKEN");
    const r = await f(urlGraph(env, "me/messages"), { method: "POST", headers: { ...init.headers, authorization: `Bearer ${token}` }, body: init.body });
    const j = (await r.json().catch(() => ({}))) as { message_id?: string; error?: { message?: string; code?: number } };
    // Fuera de la ventana de 24 h, sin permiso o con un destinatario inválido, Meta contesta con un error concreto.
    if (!r.ok || j.error) throw new Error(`meta send ${r.status}: ${j.error?.message ?? "sin detalle"} (código ${j.error?.code ?? "?"})`);
    return j.message_id;
  }

  const enviarUno = (env: Env, cuerpo: Record<string, unknown>) =>
    publicar(env, { headers: { "content-type": "application/json" }, body: JSON.stringify(cuerpo) });

  /**
   * Juan baja el archivo (la URL firmada de Odoo) para SUBÍRSELO a Meta: con `payload.url` Meta tenía que bajarlo él mismo desde
   * dcasapty.com y respondía «(#100) Error al subir el producto» (2026-11-09 en Messenger y 2026-11-10 en Instagram: el texto
   * salía y la foto no). Messenger lo sube en la misma llamada (`filedata`); Instagram, antes, por la Attachment Upload API
   * (`enviarFotoInstagram`). Si Juan no logra bajarlo, se manda por URL como antes (nunca peor que antes).
   */
  async function bajarParaSubir(m: MedioSaliente, canal: "messenger" | "instagram"): Promise<{ bytes: ArrayBuffer; mime: string } | null> {
    const maximo = canal === "instagram" ? MAX_FOTO_INSTAGRAM_BYTES : MAX_ADJUNTO_MESSENGER_BYTES;
    const demasiado = canal === "instagram" ? "la foto pasa de 8 MB (límite de Instagram)" : "el archivo pasa de 25 MB (límite de Messenger)";
    let archivo: Response;
    try {
      archivo = await f(m.url);
    } catch (e) {
      console.warn(`[juan] ${canal}: no se pudo bajar el archivo para subirlo; va por URL:`, String(e).slice(0, 200));
      return null;
    }
    if (!archivo.ok) {
      console.warn(`[juan] ${canal}: el archivo respondió HTTP ${archivo.status}; va por URL`);
      return null;
    }
    if (Number(archivo.headers.get("content-length") ?? 0) > maximo) throw new Error(demasiado);
    const bytes = await archivo.arrayBuffer();
    if (bytes.byteLength > maximo) throw new Error(demasiado);
    if (bytes.byteLength === 0) return null;
    const mime = m.mime || archivo.headers.get("content-type")?.split(";")[0]?.trim() || (m.tipo === "imagen" ? "image/jpeg" : "application/octet-stream");
    return { bytes, mime };
  }

  async function enviarSubiendo(env: Env, destino: { id: string }, m: MedioSaliente, archivo: { bytes: ArrayBuffer; mime: string }): Promise<string | undefined> {
    const imagen = m.tipo === "imagen";
    const cuerpo = new FormData();
    cuerpo.append("recipient", JSON.stringify(destino));
    cuerpo.append("messaging_type", "RESPONSE");
    cuerpo.append("message", JSON.stringify({ attachment: { type: imagen ? "image" : "file", payload: { is_reusable: false } } }));
    cuerpo.append("filedata", new Blob([archivo.bytes], { type: archivo.mime }), m.nombre || (imagen ? "foto.jpg" : "archivo"));
    return publicar(env, { headers: {}, body: cuerpo }); // (sin content-type: lo pone FormData con su «boundary»)
  }

  // Instagram no documenta `is_reusable` en el envío: solo `url` (Messenger sí lo acepta).
  const porUrl = (env: Env, destino: { id: string }, m: MedioSaliente, canal: "messenger" | "instagram") =>
    enviarUno(env, {
      recipient: destino,
      messaging_type: "RESPONSE",
      message: { attachment: { type: m.tipo === "imagen" ? "image" : "file", payload: canal === "instagram" ? { url: m.url } : { url: m.url, is_reusable: true } } },
    });

  /**
   * Instagram: la foto se sube primero a Meta (`me/message_attachments` con `platform=instagram`, multipart con `filedata`) y se
   * manda con el `attachment_id` que devuelve (la Send API de Instagram acepta `payload.attachment_id`). Devuelve null si Meta no
   * aceptó la subida: entonces va por URL como antes. Lo que dijo Meta queda en el registro, sin datos de nadie.
   */
  async function subirFotoInstagram(env: Env, m: MedioSaliente, archivo: { bytes: ArrayBuffer; mime: string }): Promise<string | null> {
    const token = env.META_PAGE_TOKEN;
    if (!token) return null;
    try {
      const cuerpo = new FormData();
      cuerpo.append("platform", "instagram");
      cuerpo.append("message", JSON.stringify({ attachment: { type: "image", payload: { is_reusable: true } } }));
      cuerpo.append("filedata", new Blob([archivo.bytes], { type: archivo.mime }), m.nombre || (archivo.mime === "image/png" ? "foto.png" : "foto.jpg"));
      const r = await f(urlGraph(env, "me/message_attachments"), { method: "POST", headers: { authorization: `Bearer ${token}` }, body: cuerpo });
      const j = (await r.json().catch(() => ({}))) as { attachment_id?: unknown; error?: { message?: string; code?: number } };
      if (r.ok && typeof j.attachment_id === "string" && j.attachment_id) return j.attachment_id;
      console.warn(`[juan] instagram: Meta no aceptó la foto subida (HTTP ${r.status}, código ${j.error?.code ?? "?"}): ${(j.error?.message ?? "sin detalle").slice(0, 160)}; va por URL`);
      return null;
    } catch (e) {
      console.warn("[juan] instagram: no se pudo subir la foto; va por URL:", (e instanceof Error ? e.message : String(e)).slice(0, 160));
      return null;
    }
  }

  async function enviarFotoInstagram(env: Env, destino: { id: string }, m: MedioSaliente): Promise<string | undefined> {
    const archivo = await bajarParaSubir(m, "instagram");
    const adjunto = archivo ? await subirFotoInstagram(env, m, archivo) : null;
    if (!adjunto) return porUrl(env, destino, m, "instagram");
    return enviarUno(env, { recipient: destino, messaging_type: "RESPONSE", message: { attachment: { type: "image", payload: { attachment_id: adjunto } } } });
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
      // Como WhatsApp Cloud: se contesta 200 cuando cada mensaje ya quedó guardado (`guardarAntes`, rutas.ts). Los archivos de
      // Messenger e Instagram llegan como `url` (no hay nada que bajar con credenciales antes de guardarlos).
      return { respuesta: json({ ok: true }), entrantes: eventosDeMeta(cuerpo, Date.now()), guardarAntes: true };
    },

    async enviar(canal: CanalId, salida: Saliente, env: Env): Promise<ResultadoEnvio> {
      const ids: string[] = [];
      const destino = { id: salida.para };
      const cap = canal === "instagram" ? CAPACIDADES.instagram : CAPACIDADES.messenger;
      let burbujas = 0;
      let medios = 0;
      try {
        for (let i = 0; i < salida.burbujas.length; i++) {
          if (i > 0) await dormir(salida.esperaMs ?? 1000);
          const id = await enviarUno(env, { recipient: destino, messaging_type: "RESPONSE", message: { text: sinNegritas(salida.burbujas[i]) } });
          burbujas++;
          if (id) ids.push(id);
        }
        for (const m of salida.medios) {
          if (m.tipo === "documento" && !cap.documentos) {
            medios++;
            continue;
          }
          if (!env.META_PAGE_TOKEN) throw new Error("Falta META_PAGE_TOKEN");
          let id: string | undefined;
          if (canal === "instagram") {
            id = await enviarFotoInstagram(env, destino, m); // aquí solo llegan imágenes: Instagram no admite documentos
          } else {
            const archivo = await bajarParaSubir(m, "messenger");
            id = archivo ? await enviarSubiendo(env, destino, m, archivo) : await porUrl(env, destino, m, "messenger");
          }
          medios++;
          if (id) ids.push(id);
        }
      } catch (e) {
        // Lo que ya salió no se repite: quien reintente manda solo lo que falta.
        if (burbujas + medios > 0) throw new EnvioParcialError(e instanceof Error ? e.message : String(e), { burbujas, medios, ids });
        throw e;
      }
      return { ids };
    },

    async nombreDePerfil(canal: CanalId, para: string, env: Env): Promise<string | null> {
      const token = env.META_PAGE_TOKEN;
      if (!token || !/^\d{5,30}$/.test(para)) return null;
      const cabeceras = { headers: { authorization: `Bearer ${token}` } };
      const ig = canal === "instagram";
      const deGraph = async (ruta: string): Promise<Record<string, unknown> | null> => {
        const r = await f(urlGraph(env, ruta), cabeceras);
        const j = (await r.json().catch(() => null)) as (Record<string, unknown> & { error?: { code?: number } }) | null;
        if (!r.ok || !j || j.error) {
          // Sin datos de nadie: solo qué consulta y qué código dio Meta (para saber qué permiso falta).
          console.warn(`[juan] ${canal}: el nombre no salió de ${ruta.split("?")[0].replace(/\d{5,}/, ":id")} (HTTP ${r.status}, código ${j?.error?.code ?? "?"})`);
          return null;
        }
        return j;
      };
      // 1) El perfil (Messenger: nombre y apellido; Instagram: nombre o @usuario). Meta lo da solo con el permiso «Business Asset User
      //    Profile Access» (revisión de la app) o a quien tiene rol en la app.
      const perfil = await deGraph(`${para}?fields=${ig ? "name,username" : "first_name,last_name"}`);
      const delPerfil = ig
        ? texto(perfil?.name) || (texto(perfil?.username) ? `@${texto(perfil?.username)}` : "")
        : [texto(perfil?.first_name), texto(perfil?.last_name)].filter(Boolean).join(" ");
      if (limpiarNombre(delPerfil)) return limpiarNombre(delPerfil);
      // 2) Sin ese permiso: la conversación de la página con esa persona trae sus participantes (Messenger: `name`; Instagram:
      //    `username`), con los permisos de mensajes que ya tiene la llave de la página.
      const conv = await deGraph(`me/conversations?platform=${ig ? "instagram" : "messenger"}&user_id=${para}&fields=participants`);
      const datos = (conv?.data as { participants?: { data?: { id?: string; name?: string; username?: string }[] } }[] | undefined) ?? [];
      const quien = datos.flatMap((c) => c.participants?.data ?? []).find((p) => p.id === para);
      const deLaConversacion = ig ? (texto(quien?.username) ? `@${texto(quien?.username)}` : texto(quien?.name)) : texto(quien?.name);
      return limpiarNombre(deLaConversacion) || null;
    },

    async fotoDePerfil(_canal: CanalId, para: string, env: Env): Promise<{ bytes: Uint8Array; mime: string } | null> {
      const token = env.META_PAGE_TOKEN;
      if (!token || !/^\d{5,30}$/.test(para)) return null;
      const r = await f(urlGraph(env, `${para}?fields=profile_pic`), { headers: { authorization: `Bearer ${token}` } });
      if (!r.ok) return null;
      const j = (await r.json().catch(() => null)) as { profile_pic?: string } | null;
      let url: URL;
      try {
        url = new URL(j?.profile_pic ?? "");
      } catch {
        return null;
      }
      if (url.protocol !== "https:" || !SERVIDORES_DE_FOTO.test(url.hostname)) return null;
      const foto = await f(url.toString(), { redirect: "error" });
      if (!foto.ok) return null;
      const bytes = new Uint8Array(await foto.arrayBuffer());
      if (bytes.length === 0 || bytes.length > MAX_FOTO_DE_PERFIL_BYTES) return null;
      const mime = (foto.headers.get("content-type") ?? "image/jpeg").split(";")[0].trim().toLowerCase();
      return { bytes, mime: mime.startsWith("image/") ? mime : "image/jpeg" };
    },

    async escribiendo(_canal: CanalId, para: string, env: Env): Promise<void> {
      await enviarUno(env, { recipient: { id: para }, sender_action: "typing_on" }).catch(() => {});
    },

    async salud(canal: CanalId, env: Env): Promise<SaludCanal> {
      return { configurado: this.configurado(env, canal), faltan: this.faltantes(env, canal), conectado: null };
    },
  };
}
