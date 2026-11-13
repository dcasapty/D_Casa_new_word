// Los COMENTARIOS de las publicaciones de D'CASA en Facebook e Instagram (2026-11-12). Llegan por los mismos webhooks que los mensajes,
// pero en `entry[].changes[]` (no en `messaging[]`):
//
//   · Facebook (la página, webhook `/webhooks/meta`, objeto `page`): campo `feed` con `item: "comment"` y `verb: "add"`; trae
//     `comment_id`, `post_id`, `parent_id` (la publicación, o el comentario de arriba si es una respuesta), `from {id, name}` (el id es
//     el PSID: el mismo de Messenger), `message` y `created_time` (segundos). Permisos: `pages_manage_metadata`, `pages_read_engagement`
//     (y para contestar `pages_manage_engagement` y `pages_messaging`).
//     developers.facebook.com/documentation/pages-api/webhooks-for-pages · …/pages-api/comments-mentions
//   · Instagram (por la página en `/webhooks/meta`, o por inicio de sesión de Instagram en `/webhooks/instagram`; objeto `instagram`):
//     campo `comments`; trae el id del comentario (`id`, o `comment_id` en otro ejemplo de Meta: se aceptan los dos), `from {id,
//     username}` (el id es el IGSID de quien comentó), `text`, `media {id}` y `parent_id` si es una respuesta. No trae la hora del
//     comentario: se usa `entry.time`. developers.facebook.com/documentation/instagram-platform/webhooks/examples
//
// Aquí solo se LEEN y se filtran: se ignoran los de la propia página o cuenta (sus respuestas también llegan como comentario), los
// editados o borrados, los ocultos, los vacíos (una foto o un sticker) y los de hace más de 7 días (Meta ya no deja la respuesta privada).
// Lo que se contesta y cómo lo decide el motor (motor/conversacion.ts → `recibirComentario`, y motor/comentarios.ts).

import { enlaceDeMeta, type MetaCuerpo } from "./metaComun";
import { aMilisegundos, type ComentarioEntrante, type Entrante } from "./tipos";

/** Meta deja la respuesta privada hasta 7 días después del comentario; con una hora de margen para no llegar tarde. */
export const VIDA_DE_UN_COMENTARIO_MS = 7 * 24 * 3600_000 - 3600_000;

/** El id de quien comenta: el PSID (Facebook) o el IGSID (Instagram), solo cifras (es la llave de su conversación en Odoo). */
const ID_DE_PERSONA = /^\d{3,30}$/;
const ID_DE_META = /^[A-Za-z0-9_.:-]{1,128}$/;
const USUARIO_DE_INSTAGRAM = /^[A-Za-z0-9._]{1,30}$/;
const MAX_TEXTO = 2000;

/** Por qué se dejó de lado un comentario del aviso (para el registro del Worker; nunca con datos de la persona). */
export interface IgnoradosDeComentarios {
  propios: number;
  /** En publicaciones de OTRA página o cuenta suscrita a la app (no de D'CASA). */
  ajenos: number;
  viejos: number;
  /** Editados, borrados, ocultos, sin texto, en vivo o con ids raros. */
  otros: number;
}

export interface OpcionesDeComentarios {
  /** La puerta por la que llegó el aviso (y por la que se contesta). */
  puerta: ComentarioEntrante["puerta"];
  /** Los ids de la propia página o cuenta (además del `entry.id` de cada entrada). */
  propios?: ReadonlySet<string>;
  /**
   * Las cuentas de D'CASA (la página y su Instagram): solo se atienden los avisos cuyo `entry.id` sea una de ellas (otra página suscrita
   * a la misma app no entra). Sin esto se atiende cualquiera (la segunda puerta ya filtra antes con `soloDeLaCuenta`).
   */
  cuentas?: ReadonlySet<string>;
  /** El usuario de Instagram de D'CASA (sin @), si se sabe: sus comentarios no se contestan. */
  usuarioPropio?: string;
}

const texto = (v: unknown): string => (typeof v === "string" ? v.trim() : typeof v === "number" ? String(v) : "");
const objeto = (v: unknown): Record<string, unknown> => (v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : {});
const limpio = (t: string) => t.replace(/[\u0000-\u0008\u000b-\u001f\u007f]/g, "").trim();

/** Los comentarios de un aviso de Meta, ya traducidos a `Entrante` con su `comentario`. Nunca lanza. */
export function comentariosDeMeta(cuerpo: MetaCuerpo, ahora: number, op: OpcionesDeComentarios): { entrantes: Entrante[]; ignorados: IgnoradosDeComentarios } {
  const ignorados: IgnoradosDeComentarios = { propios: 0, ajenos: 0, viejos: 0, otros: 0 };
  const entrantes: Entrante[] = [];
  const red = cuerpo.object === "page" ? "facebook" : cuerpo.object === "instagram" ? "instagram" : null;
  if (!red) return { entrantes, ignorados };
  for (const entrada of cuerpo.entry ?? []) {
    const cuenta = texto(entrada.id);
    if (op.cuentas && !op.cuentas.has(cuenta)) {
      ignorados.ajenos += (entrada.changes ?? []).filter((c) => c.field === "feed" || c.field === "comments").length;
      continue;
    }
    for (const cambio of entrada.changes ?? []) {
      const v = objeto(cambio.value);
      const c = red === "facebook" ? deFacebook(cambio.field, v, ahora) : deInstagram(cambio.field, v);
      if (!c) {
        if (cambio.field === (red === "facebook" ? "feed" : "comments") && (red === "instagram" || v.item === "comment")) ignorados.otros++;
        continue;
      }
      if (c.autor === cuenta || op.propios?.has(c.autor) || (c.usuario && op.usuarioPropio && c.usuario.toLowerCase() === op.usuarioPropio.toLowerCase())) {
        ignorados.propios++;
        continue;
      }
      const ts = c.ts ?? aMilisegundos(entrada.time, ahora);
      if (ahora - ts > VIDA_DE_UN_COMENTARIO_MS) {
        ignorados.viejos++;
        continue;
      }
      const comentario: ComentarioEntrante = {
        red,
        puerta: op.puerta,
        id: c.id,
        ...(c.padre ? { padre: c.padre } : {}),
        ...(c.publicacion ? { publicacion: c.publicacion } : {}),
        ...(c.enlace ? { enlace: c.enlace } : {}),
        ...(c.usuario ? { usuario: c.usuario } : {}),
      };
      entrantes.push({
        canal: red === "facebook" ? "messenger" : "instagram",
        id_externo: c.autor,
        id_mensaje: `comentario:${red}:${c.id}`,
        ...(c.nombre ? { nombre: c.nombre } : {}),
        texto: c.texto,
        adjuntos: [],
        ts,
        comentario,
      });
    }
  }
  return { entrantes, ignorados };
}

interface Leido {
  id: string;
  autor: string;
  nombre?: string;
  usuario?: string;
  texto: string;
  padre?: string;
  publicacion?: string;
  enlace?: string;
  ts?: number;
}

/** Facebook, campo `feed`: solo un comentario nuevo (`item: comment`, `verb: add`), visible y con texto. */
function deFacebook(campo: unknown, v: Record<string, unknown>, ahora: number): Leido | null {
  if (campo !== "feed" || v.item !== "comment" || v.verb !== "add" || v.is_hidden === true) return null;
  const id = texto(v.comment_id);
  const de = objeto(v.from);
  const autor = texto(de.id);
  const dicho = limpio(texto(v.message)).slice(0, MAX_TEXTO);
  if (!ID_DE_META.test(id) || !ID_DE_PERSONA.test(autor) || !dicho) return null;
  const publicacion = texto(v.post_id);
  const padre = texto(v.parent_id);
  const nombre = limpio(texto(de.name)).slice(0, 100);
  const creado = v.created_time;
  return {
    id,
    autor,
    texto: dicho,
    ...(nombre ? { nombre } : {}),
    ...(ID_DE_META.test(publicacion) ? { publicacion } : {}),
    // `parent_id` es la publicación si el comentario es de primer nivel; si es otro comentario, es una respuesta.
    ...(ID_DE_META.test(padre) && padre !== publicacion ? { padre } : {}),
    ...(enlaceDeMeta(objeto(v.post).permalink_url) ? { enlace: enlaceDeMeta(objeto(v.post).permalink_url) } : {}),
    ...(typeof creado === "number" || typeof creado === "string" ? { ts: aMilisegundos(creado, ahora) } : {}),
  };
}

/** Instagram, campo `comments` (los de un video en vivo, `live_comments`, no: la respuesta privada solo vale durante la transmisión). */
function deInstagram(campo: unknown, v: Record<string, unknown>): Leido | null {
  if (campo !== "comments") return null;
  const id = texto(v.id) || texto(v.comment_id);
  const de = objeto(v.from);
  const autor = texto(de.id);
  const dicho = limpio(texto(v.text)).slice(0, MAX_TEXTO);
  if (!ID_DE_META.test(id) || !ID_DE_PERSONA.test(autor) || !dicho) return null;
  const usuario = texto(de.username);
  const publicacion = texto(objeto(v.media).id);
  const padre = texto(v.parent_id);
  return {
    id,
    autor,
    texto: dicho,
    ...(USUARIO_DE_INSTAGRAM.test(usuario) ? { usuario, nombre: `@${usuario}` } : {}),
    ...(ID_DE_META.test(publicacion) ? { publicacion } : {}),
    ...(ID_DE_META.test(padre) && padre !== id ? { padre } : {}),
  };
}

/** ¿El aviso trae algún comentario (aunque después se ignore)? Para no contestar «nada que hacer» antes de mirarlo. */
export function traeComentarios(cuerpo: MetaCuerpo): boolean {
  return (cuerpo.entry ?? []).some((e) => (e.changes ?? []).some((c) => c.field === "feed" || c.field === "comments"));
}

/** Cuántos comentarios de un aviso se dejaron de lado y por qué (sin datos de nadie). */
export function anotarIgnorados(ruta: string, i: IgnoradosDeComentarios): void {
  if (i.propios + i.ajenos + i.viejos + i.otros === 0) return;
  console.info(
    `[juan] ${ruta}: comentarios que no se contestan: ${i.propios} propio(s), ${i.ajenos} de otra página o cuenta, ${i.viejos} de hace más de 7 días, ${i.otros} editado(s), oculto(s) o sin texto`,
  );
}
