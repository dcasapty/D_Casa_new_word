// Lo que comparten las dos puertas de Meta para Messenger e Instagram: leer el aviso (`entry[].messaging[]`, el mismo formato en
// las dos) y la maquinaria de envío (texto, fotos con sus tres caminos, PDF, nombre y foto del cliente, «escribiendo…»).
//
//   · La página (meta.ts): `graph.facebook.com` con META_PAGE_TOKEN (Messenger Platform, Messenger e Instagram).
//   · Instagram por inicio de sesión de Instagram (instagramLogin.ts): `graph.instagram.com` con la llave de Instagram.
//
// Lo único que cambia entre las dos es la `PuertaMeta`: a qué anfitrión se habla, con qué llave y qué pide cada API.

import type { Env } from "../env";
import { tokensIguales } from "../seguridad";
import type { Llavero } from "./instagramLlave";
import {
  aMilisegundos,
  type AdjuntoEntrante,
  type CanalId,
  type Entrante,
  type ResultadoEnvio,
  type MedioSaliente,
  type Saliente,
  EnvioParcialError,
  enlaceDeMedio,
  MAX_FOTO_DE_PERFIL_BYTES,
  sinNegritas,
} from "./tipos";

export interface MetaEvento {
  sender?: { id?: string };
  recipient?: { id?: string };
  timestamp?: number;
  message?: {
    mid?: string;
    text?: string;
    is_echo?: boolean;
    /** Instagram por inicio de sesión de Instagram: un mensaje de prueba a la propia cuenta (no es de un cliente). */
    is_self?: boolean;
    attachments?: { type?: string; payload?: { url?: string } }[];
  };
}

/** Un cambio de la página o de la cuenta (`entry[].changes[]`): aquí llegan los COMENTARIOS (Facebook `feed`, Instagram `comments`). */
export interface MetaCambio {
  field?: string;
  value?: Record<string, unknown>;
}

export interface MetaCuerpo {
  object?: string;
  entry?: { id?: string; time?: number; messaging?: MetaEvento[]; changes?: MetaCambio[] }[];
}

export interface OpcionesMeta {
  fetch?: typeof fetch;
  dormir?: (ms: number) => Promise<void>;
  /** Dónde vive la llave renovada de Instagram (por defecto, el Durable Object `Global`). */
  llavero?: Llavero;
  ahora?: () => number;
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

/** La verificación del webhook (GET): `hub.verify_token` igual a META_VERIFY_TOKEN → se devuelve `hub.challenge`. */
export function respuestaDeVerificacion(req: Request, esperado: string | undefined): Response {
  const q = new URL(req.url).searchParams;
  if (q.get("hub.mode") === "subscribe" && esperado && tokensIguales(q.get("hub.verify_token") ?? "", esperado)) {
    return new Response(q.get("hub.challenge") ?? "", { status: 200 });
  }
  return new Response("no autorizado", { status: 403 });
}

const texto = (v: unknown): string => (typeof v === "string" ? v.trim() : "");
/** Un nombre que se puede mostrar: sin caracteres de control y de 100 letras como mucho. */
const limpiarNombre = (n: string): string => n.replace(/[\u0000-\u001f\u007f]/g, "").trim().slice(0, 100);

/** Lo más grande que Messenger acepta como adjunto subido. */
export const MAX_ADJUNTO_MESSENGER_BYTES = 25 * 1024 * 1024;
/** Lo más grande que Instagram acepta como foto (documentación de Meta: png o jpeg, hasta 8 MB). */
export const MAX_FOTO_INSTAGRAM_BYTES = 8 * 1024 * 1024;
/** Lo más grande que Instagram por inicio de sesión de Instagram acepta como archivo (documentación de Meta: pdf, hasta 25 MB). */
export const MAX_PDF_INSTAGRAM_BYTES = 25 * 1024 * 1024;

/** Por dónde habla la maquinaria con Meta. */
export interface PuertaMeta {
  /** La URL de una ruta de la Graph API (`me/messages`, `<id>?fields=…`). */
  url(env: Env, ruta: string): string;
  /** La llave con que se habla (null/undefined = falta). */
  llave(env: Env): Promise<string | undefined>;
  /** El nombre del secreto, para el error «Falta …». */
  secreto: string;
  /** La Send API de la página pide `messaging_type: RESPONSE`; la de Instagram con inicio de sesión no lo documenta. */
  messagingType: boolean;
  /** Instagram por inicio de sesión de Instagram admite PDF (`file`); por la página, no (el enlace va en el texto). */
  pdfEnInstagram: boolean;
  /** Meta rechazó la llave al enviar (código 190): la puerta lo anota para /salud. Nunca lanza. */
  rechazoDeLlave?(env: Env, motivo: string): Promise<void>;
  /** Un envío salió bien con la llave vigente (para borrar un «rechazada» anterior). Nunca lanza. */
  llaveFunciono?(env: Env): Promise<void>;
}

/** Meta rechazó la LLAVE (vencida, revocada, inválida): código 190 o 102. */
const rechazoDeLlave = (codigo: unknown) => Number(codigo) === 190 || Number(codigo) === 102;

export interface MaquinaMeta {
  enviar(canal: "messenger" | "instagram", salida: Saliente, env: Env): Promise<ResultadoEnvio>;
  nombreDePerfil(canal: "messenger" | "instagram", para: string, env: Env): Promise<string | null>;
  fotoDePerfil(para: string, env: Env): Promise<{ bytes: Uint8Array; mime: string } | null>;
  escribiendo(para: string, env: Env): Promise<void>;
  /** La respuesta privada a un comentario (`me/messages` con `recipient: {comment_id}`): UNA por comentario, dentro de 7 días. */
  responderEnPrivado(idComentario: string, texto: string, env: Env): Promise<{ id?: string; destinatario?: string }>;
  /** La respuesta pública debajo de un comentario: Facebook `/{comment-id}/comments`, Instagram `/{ig-comment-id}/replies`. */
  responderEnPublico(red: "facebook" | "instagram", idComentario: string, texto: string, env: Env): Promise<{ id?: string }>;
  /** El texto y el enlace de una publicación (Facebook `message,permalink_url`; Instagram `caption,permalink`). null = no se pudo. */
  publicacion(red: "facebook" | "instagram", idPublicacion: string, env: Env): Promise<{ texto?: string; enlace?: string } | null>;
}

export function maquinaMeta(op: OpcionesMeta, puerta: PuertaMeta): MaquinaMeta {
  const f: typeof fetch = op.fetch ?? ((...a) => fetch(...a));
  const dormir = op.dormir ?? ((ms: number) => new Promise<void>((r) => setTimeout(r, ms)));
  const falta = () => new Error(`Falta ${puerta.secreto}`);
  /** El cuerpo de un mensaje de respuesta, con `messaging_type` si la puerta lo pide. */
  const respuesta = (cuerpo: { recipient: { id: string }; message: unknown }) => (puerta.messagingType ? { recipient: cuerpo.recipient, messaging_type: "RESPONSE", message: cuerpo.message } : cuerpo);

  async function publicar(env: Env, init: { headers: Record<string, string>; body: BodyInit }): Promise<string | undefined> {
    const token = await puerta.llave(env);
    if (!token) throw falta();
    const r = await f(puerta.url(env, "me/messages"), { method: "POST", headers: { ...init.headers, authorization: `Bearer ${token}` }, body: init.body });
    const j = (await r.json().catch(() => ({}))) as { message_id?: string; error?: { message?: string; code?: number } };
    // Fuera de la ventana de 24 h, sin permiso o con un destinatario inválido, Meta contesta con un error concreto.
    if (!r.ok || j.error) {
      const error = `meta send ${r.status}: ${j.error?.message ?? "sin detalle"} (código ${j.error?.code ?? "?"})`;
      if (rechazoDeLlave(j.error?.code)) await puerta.rechazoDeLlave?.(env, error.replace(/^meta send /, "HTTP ").slice(0, 160)).catch(() => {});
      throw new Error(error);
    }
    await puerta.llaveFunciono?.(env).catch(() => {});
    return j.message_id;
  }

  const enviarUno = (env: Env, cuerpo: Record<string, unknown>) =>
    publicar(env, { headers: { "content-type": "application/json" }, body: JSON.stringify(cuerpo) });

  /**
   * Juan baja el archivo (la URL firmada de Odoo) para SUBÍRSELO a Meta: con `payload.url` Meta tenía que bajarlo él mismo desde
   * dcasapty.com y respondía «(#100) Error al subir el producto» (2026-11-09 en Messenger y 2026-11-10 en Instagram: el texto
   * salía y la foto no). Messenger lo sube en la misma llamada (`filedata`); Instagram prueba eso y dos caminos más
   * (`enviarFotoInstagram`). Si Juan no logra bajarlo, se manda por URL como antes (nunca peor que antes).
   */
  async function bajarParaSubir(m: MedioSaliente, canal: string, maximo: number, demasiado: string): Promise<{ bytes: ArrayBuffer; mime: string } | null> {
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
    if (puerta.messagingType) cuerpo.append("messaging_type", "RESPONSE");
    cuerpo.append("message", JSON.stringify({ attachment: { type: imagen ? "image" : "file", payload: { is_reusable: false } } }));
    cuerpo.append("filedata", new Blob([archivo.bytes], { type: archivo.mime }), m.nombre || (imagen ? "foto.jpg" : "archivo"));
    return publicar(env, { headers: {}, body: cuerpo }); // (sin content-type: lo pone FormData con su «boundary»)
  }

  // Instagram no documenta `is_reusable` en el envío: solo `url` (Messenger sí lo acepta).
  const porUrl = (env: Env, destino: { id: string }, m: MedioSaliente, canal: "messenger" | "instagram") =>
    enviarUno(
      env,
      respuesta({
        recipient: destino,
        message: { attachment: { type: m.tipo === "imagen" ? "image" : "file", payload: canal === "instagram" ? { url: m.url } : { url: m.url, is_reusable: true } } },
      }),
    );

  const motivo = (e: unknown) => (e instanceof Error ? e.message : String(e)).slice(0, 160);
  /** Un motivo de Meta en corto para Odoo (que guarda 200 letras): sin «meta send 400:» y con el código entre corchetes. */
  const corto = (m: string) => m.replace(/^meta send \d+: /, "").replace(/^HTTP \d+ /, "").replace(/ \(código ([^)]*)\)$/, " [$1]").slice(0, 46);
  const resumir = (fallos: string[]) =>
    fallos.map((x) => {
      const i = x.indexOf(": ");
      return `${x.slice(0, i)}: ${corto(x.slice(i + 2))}`;
    });

  /** Sube la foto aparte (`me/message_attachments`, `platform=instagram`) y devuelve su `attachment_id`, o null (con el motivo en `fallos`). */
  async function subirFotoInstagram(env: Env, m: MedioSaliente, archivo: { bytes: ArrayBuffer; mime: string }, fallos: string[]): Promise<string | null> {
    const token = await puerta.llave(env);
    if (!token) return null;
    try {
      const cuerpo = new FormData();
      cuerpo.append("platform", "instagram");
      cuerpo.append("message", JSON.stringify({ attachment: { type: "image", payload: { is_reusable: true } } }));
      cuerpo.append("filedata", new Blob([archivo.bytes], { type: archivo.mime }), m.nombre || (archivo.mime === "image/png" ? "foto.png" : "foto.jpg"));
      const r = await f(puerta.url(env, "me/message_attachments"), { method: "POST", headers: { authorization: `Bearer ${token}` }, body: cuerpo });
      const j = (await r.json().catch(() => ({}))) as { attachment_id?: unknown; error?: { message?: string; code?: number } };
      if (r.ok && typeof j.attachment_id === "string" && j.attachment_id) return j.attachment_id;
      fallos.push(`aparte: HTTP ${r.status} ${(j.error?.message ?? "sin attachment_id").slice(0, 120)} (código ${j.error?.code ?? "?"})`);
      return null;
    } catch (e) {
      fallos.push(`aparte: ${motivo(e)}`);
      return null;
    }
  }

  /**
   * Instagram (2026-11-10: el texto salía y la foto no, «(#100) Error al subir el producto»). Se prueba, en orden, hasta que uno
   * sale: (1) subir y enviar en la MISMA llamada, como Messenger (la documentación de Meta lo da para Instagram: `me/messages` con
   * `filedata`); (2) subir aparte y mandar con `attachment_id`; (3) por URL, como antes. Un rechazo de Meta no deja salir nada, así
   * que probar el siguiente no duplica. Si ninguno sale, el error dice qué contestó Meta a cada intento: se ve en Odoo («Por qué
   * no salió») sin tener que abrir los registros.
   */
  async function enviarFotoInstagram(env: Env, destino: { id: string }, m: MedioSaliente): Promise<string | undefined> {
    const fallos: string[] = [];
    const archivo = await bajarParaSubir(m, "instagram", MAX_FOTO_INSTAGRAM_BYTES, "la foto pasa de 8 MB (límite de Instagram)");
    if (archivo) {
      try {
        return await enviarSubiendo(env, destino, m, archivo);
      } catch (e) {
        fallos.push(`envío: ${motivo(e)}`);
      }
      const adjunto = await subirFotoInstagram(env, m, archivo, fallos);
      if (adjunto) {
        try {
          return await enviarUno(env, respuesta({ recipient: destino, message: { attachment: { type: "image", payload: { attachment_id: adjunto } } } }));
        } catch (e) {
          fallos.push(`attachment_id: ${motivo(e)}`);
        }
      }
    } else {
      fallos.push("bajar: Juan no pudo bajar la foto de Odoo");
    }
    try {
      const id = await porUrl(env, destino, m, "instagram");
      if (fallos.length) console.warn("[juan] instagram: la foto salió por URL después de:", fallos.join(" · "));
      return id;
    } catch (e) {
      fallos.push(`URL: ${motivo(e)}`);
      console.warn("[juan] instagram: Meta no aceptó la foto:", fallos.join(" · "));
      // En corto para Odoo («Por qué no salió» guarda 200 letras): cada intento con lo que dijo Meta.
      throw new Error(`Instagram no aceptó la foto · ${resumir(fallos).join(" · ")}`.slice(0, 200));
    }
  }

  /**
   * Un PDF por Instagram con inicio de sesión de Instagram (Meta: `file`, solo pdf, hasta 25 MB). Se prueba (1) subirlo en el mismo
   * envío y (2) por URL; si Meta no lo acepta (o no es un PDF, o pasa de 25 MB), sale como hoy por la página: el enlace en el texto.
   */
  async function enviarPdfInstagram(env: Env, destino: { id: string }, m: MedioSaliente): Promise<string | undefined> {
    const fallos: string[] = [];
    const pareceSer = /application\/pdf/i.test(m.mime ?? "") || /\.pdf$/i.test(m.nombre ?? "") || /\.pdf$/i.test(urlSinConsulta(m.url));
    let archivo: { bytes: ArrayBuffer; mime: string } | null = null;
    let grande = false;
    try {
      archivo = await bajarParaSubir(m, "instagram", MAX_PDF_INSTAGRAM_BYTES, "el PDF pasa de 25 MB (límite de Instagram)");
    } catch (e) {
      grande = true;
      fallos.push(`bajar: ${motivo(e)}`);
    }
    const esPdf = archivo ? archivo.mime === "application/pdf" || pareceSer : pareceSer;
    if (!grande && esPdf) {
      if (archivo) {
        try {
          return await enviarSubiendo(env, destino, { ...m, nombre: m.nombre || "documento.pdf" }, { ...archivo, mime: "application/pdf" });
        } catch (e) {
          fallos.push(`envío: ${motivo(e)}`);
        }
      }
      try {
        const id = await porUrl(env, destino, m, "instagram");
        if (fallos.length) console.warn("[juan] instagram: el PDF salió por URL después de:", fallos.join(" · "));
        return id;
      } catch (e) {
        fallos.push(`URL: ${motivo(e)}`);
      }
    } else if (!esPdf) {
      fallos.push("tipo: Instagram solo acepta PDF");
    }
    // Como hoy por la página: el enlace en el texto (el cliente lo abre igual).
    console.warn("[juan] instagram: el documento va como enlace:", fallos.join(" · "));
    try {
      return await enviarUno(env, respuesta({ recipient: destino, message: { text: enlaceDeMedio(m) } }));
    } catch (e) {
      fallos.push(`enlace: ${motivo(e)}`);
      throw new Error(`Instagram no aceptó el documento · ${resumir(fallos).join(" · ")}`.slice(0, 200));
    }
  }

  /** Un POST a la Graph API con la llave de la puerta. Si Meta contesta con error, lanza con su mensaje y su código (y anota un rechazo de llave). */
  async function graphPost(env: Env, ruta: string, init: { headers: Record<string, string>; body: BodyInit }): Promise<Record<string, unknown>> {
    const token = await puerta.llave(env);
    if (!token) throw falta();
    const r = await f(puerta.url(env, ruta), { method: "POST", headers: { ...init.headers, authorization: `Bearer ${token}` }, body: init.body });
    const j = (await r.json().catch(() => ({}))) as Record<string, unknown> & { error?: { message?: string; code?: number } };
    if (!r.ok || j.error) {
      const error = `meta ${r.status}: ${j.error?.message ?? "sin detalle"} (código ${j.error?.code ?? "?"})`;
      if (rechazoDeLlave(j.error?.code)) await puerta.rechazoDeLlave?.(env, error.replace(/^meta /, "HTTP ").slice(0, 160)).catch(() => {});
      throw new Error(error);
    }
    await puerta.llaveFunciono?.(env).catch(() => {});
    return j;
  }

  return {
    async enviar(canal, salida, env) {
      const ids: string[] = [];
      const destino = { id: salida.para };
      const docs = canal === "messenger" || puerta.pdfEnInstagram;
      let burbujas = 0;
      let medios = 0;
      try {
        for (let i = 0; i < salida.burbujas.length; i++) {
          if (i > 0) await dormir(salida.esperaMs ?? 1000);
          const id = await enviarUno(env, respuesta({ recipient: destino, message: { text: sinNegritas(salida.burbujas[i]) } }));
          burbujas++;
          if (id) ids.push(id);
        }
        for (const m of salida.medios) {
          if (m.tipo === "documento" && !docs) {
            medios++;
            continue;
          }
          if (!(await puerta.llave(env))) throw falta();
          let id: string | undefined;
          if (canal === "instagram") {
            id = m.tipo === "documento" ? await enviarPdfInstagram(env, destino, m) : await enviarFotoInstagram(env, destino, m);
          } else {
            const archivo = await bajarParaSubir(m, "messenger", MAX_ADJUNTO_MESSENGER_BYTES, "el archivo pasa de 25 MB (límite de Messenger)");
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

    async nombreDePerfil(canal, para, env) {
      if (!/^\d{5,30}$/.test(para)) return null;
      const token = await puerta.llave(env);
      if (!token) return null;
      const cabeceras = { headers: { authorization: `Bearer ${token}` } };
      const ig = canal === "instagram";
      const deGraph = async (ruta: string): Promise<Record<string, unknown> | null> => {
        const r = await f(puerta.url(env, ruta), cabeceras);
        const j = (await r.json().catch(() => null)) as (Record<string, unknown> & { error?: { code?: number } }) | null;
        if (!r.ok || !j || j.error) {
          // Sin datos de nadie: solo qué consulta y qué código dio Meta (para saber qué permiso falta).
          console.warn(`[juan] ${canal}: el nombre no salió de ${ruta.split("?")[0].replace(/\d{5,}/, ":id")} (HTTP ${r.status}, código ${j?.error?.code ?? "?"})`);
          return null;
        }
        return j;
      };
      // 1) El perfil (Messenger: nombre y apellido; Instagram: nombre o @usuario). Por la página, Meta lo da solo con el permiso
      //    «Business Asset User Profile Access» (revisión de la app) o a quien tiene rol en la app.
      const perfil = await deGraph(`${para}?fields=${ig ? "name,username" : "first_name,last_name"}`);
      const delPerfil = ig
        ? texto(perfil?.name) || (texto(perfil?.username) ? `@${texto(perfil?.username)}` : "")
        : [texto(perfil?.first_name), texto(perfil?.last_name)].filter(Boolean).join(" ");
      if (limpiarNombre(delPerfil)) return limpiarNombre(delPerfil);
      // 2) Sin ese permiso: la conversación con esa persona trae sus participantes (Messenger: `name`; Instagram: `username`), con los
      //    permisos de mensajes que ya tiene la llave.
      const conv = await deGraph(`me/conversations?platform=${ig ? "instagram" : "messenger"}&user_id=${para}&fields=participants`);
      const datos = (conv?.data as { participants?: { data?: { id?: string; name?: string; username?: string }[] } }[] | undefined) ?? [];
      const quien = datos.flatMap((c) => c.participants?.data ?? []).find((p) => p.id === para);
      const deLaConversacion = ig ? (texto(quien?.username) ? `@${texto(quien?.username)}` : texto(quien?.name)) : texto(quien?.name);
      return limpiarNombre(deLaConversacion) || null;
    },

    async fotoDePerfil(para, env) {
      if (!/^\d{5,30}$/.test(para)) return null;
      const token = await puerta.llave(env);
      if (!token) return null;
      const r = await f(puerta.url(env, `${para}?fields=profile_pic`), { headers: { authorization: `Bearer ${token}` } });
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

    async escribiendo(para, env) {
      await enviarUno(env, { recipient: { id: para }, sender_action: "typing_on" }).catch(() => {});
    },

    // ── Comentarios de publicaciones (2026-11-12) ──
    // Meta: developers.facebook.com/documentation/business-messaging/messenger-platform/discovery/private-replies (Facebook),
    // …/instagram-messaging/features/private-replies (Instagram por la página) y …/instagram-platform/private-replies (Instagram por
    // inicio de sesión de Instagram). La respuesta privada es la Send API con `recipient: {comment_id}` y devuelve
    // `{recipient_id, message_id}`; se manda sin `messaging_type` (así la documenta Meta).

    async responderEnPrivado(idComentario, texto, env) {
      if (!ID_DE_COMENTARIO.test(idComentario)) throw new Error("id de comentario inválido");
      const j = await graphPost(env, "me/messages", {
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ recipient: { comment_id: idComentario }, message: { text: sinNegritas(texto) } }),
      });
      return { id: textoDe(j.message_id) || undefined, destinatario: textoDe(j.recipient_id) || undefined };
    },

    async responderEnPublico(red, idComentario, texto, env) {
      if (!ID_DE_COMENTARIO.test(idComentario)) throw new Error("id de comentario inválido");
      // Formulario (como `?message=` de la documentación): la Graph API lo acepta en las dos puertas.
      const j = await graphPost(env, `${idComentario}/${red === "facebook" ? "comments" : "replies"}`, {
        headers: { "content-type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({ message: sinNegritas(texto) }).toString(),
      });
      return { id: textoDe(j.id) || undefined };
    },

    async publicacion(red, idPublicacion, env) {
      if (!ID_DE_COMENTARIO.test(idPublicacion)) return null;
      const token = await puerta.llave(env).catch(() => undefined);
      if (!token) return null;
      try {
        const r = await f(puerta.url(env, `${idPublicacion}?fields=${red === "facebook" ? "message,permalink_url" : "caption,permalink"}`), { headers: { authorization: `Bearer ${token}` } });
        const j = (await r.json().catch(() => null)) as Record<string, unknown> | null;
        if (!r.ok || !j || j.error) {
          console.warn(`[juan] ${red}: no se pudo leer la publicación comentada (HTTP ${r.status})`);
          return null;
        }
        const dicho = textoDe(red === "facebook" ? j.message : j.caption).replace(/[\u0000-\u0008\u000b-\u001f\u007f]/g, "").slice(0, 600);
        const enlace = enlaceDeMeta(red === "facebook" ? j.permalink_url : j.permalink);
        return { ...(dicho ? { texto: dicho } : {}), ...(enlace ? { enlace } : {}) };
      } catch (e) {
        console.warn(`[juan] ${red}: no se pudo leer la publicación comentada:`, String(e).slice(0, 120));
        return null;
      }
    },
  };
}

/** Los ids de Meta de comentarios y publicaciones: cifras, letras, `_` y `:` (Facebook los escribe «página_publicación»). */
const ID_DE_COMENTARIO = /^[A-Za-z0-9_.:-]{1,128}$/;
const textoDe = (v: unknown): string => (typeof v === "string" ? v.trim() : typeof v === "number" ? String(v) : "");

/**
 * Un enlace que da Meta a una publicación: solo https de Facebook o Instagram (nunca otra dirección), hasta 500 letras. Se mira como lo
 * mira un navegador (WHATWG `URL`) y además se rechaza lo que solo sirve para engañar: «\» (el navegador la toma como «/»), espacios o
 * controles, usuario o clave antes del anfitrión, y puerto. Lo que sale es la forma normalizada.
 */
export function enlaceDeMeta(v: unknown): string | undefined {
  if (typeof v !== "string" || v.length > 500 || /[\\\s\u0000-\u001f\u007f]/.test(v)) return undefined;
  try {
    const u = new URL(v);
    if (u.protocol !== "https:" || u.username || u.password || u.port) return undefined;
    return /(^|\.)(facebook\.com|instagram\.com|fb\.com|fb\.me)$/i.test(u.hostname) ? u.toString() : undefined;
  } catch {
    return undefined;
  }
}

function urlSinConsulta(url: string): string {
  try {
    return new URL(url).pathname;
  } catch {
    return url.split("?")[0];
  }
}
