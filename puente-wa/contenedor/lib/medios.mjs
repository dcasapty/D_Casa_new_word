// @ts-check
// Medios (imágenes, documentos, audio, video): tipos permitidos, tamaños,
// nombres seguros y comprobación del contenido real.
//
// No se confía en lo que el origen dice que manda: el tipo declarado (cabecera
// Content-Type, campo `mime`) se contrasta con los primeros bytes del archivo
// (su «firma»). Así una página HTML o un ejecutable con extensión `.jpg` no
// sale por el número del negocio.

const MB = 1024 * 1024;

/** Tope por archivo que se ENVÍA (Juan → cliente). WhatsApp comprime las fotos. */
export const LIMITE_SALIENTE = Object.freeze({ imagen: 6 * MB, documento: 12 * MB });

/**
 * Tope por archivo que se RECIBE (cliente → Juan). El contenedor `lite` tiene
 * 256 MiB: un archivo de 12 MB pasa por memoria varias veces (descarga, base64,
 * JSON), así que no se sube de aquí sin subir el tamaño del contenedor.
 */
export const LIMITE_ENTRANTE = Object.freeze({
  imagen: 10 * MB,
  audio: 10 * MB,
  documento: 12 * MB,
  video: 12 * MB,
});

/** Tipos que se pueden ENVIAR, por clase. */
export const MIMES_SALIENTES = Object.freeze({
  imagen: ["image/jpeg", "image/png", "image/webp"],
  documento: [
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "text/plain",
    "text/csv",
  ],
});

/** @type {Record<string, string>} */
const EXTENSION = {
  "image/jpeg": "jpg",
  "image/png": "png",
  "image/webp": "webp",
  "application/pdf": "pdf",
  "application/msword": "doc",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
  "application/vnd.ms-excel": "xls",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
  "application/vnd.ms-powerpoint": "ppt",
  "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
  "text/plain": "txt",
  "text/csv": "csv",
  "audio/ogg": "ogg",
  "audio/mpeg": "mp3",
  "audio/mp4": "m4a",
  "audio/aac": "aac",
  "video/mp4": "mp4",
  "video/3gpp": "3gp",
};

/**
 * `image/jpeg; charset=…` → `image/jpeg` (minúsculas, sin parámetros).
 * @param {unknown} mime
 */
export function mimeLimpio(mime) {
  return String(mime ?? "").split(";")[0].trim().toLowerCase();
}

/**
 * Extensión de archivo para un tipo, o "" si no se conoce.
 * @param {unknown} mime
 */
export function extensionDe(mime) {
  return EXTENSION[mimeLimpio(mime)] ?? "";
}

/**
 * Nombre de archivo seguro para mostrar al cliente: sin rutas, sin caracteres de
 * control, con extensión coherente con el tipo, de hasta 100 caracteres.
 *
 * @param {unknown} nombre
 * @param {string} mime
 * @param {string} [porDefecto]  Nombre base si no viene uno usable.
 */
export function nombreSeguro(nombre, mime, porDefecto = "archivo") {
  const ext = extensionDe(mime);
  let base = String(nombre ?? "")
    .replace(/[\u0000-\u001F\u007F]/g, "")
    .split(/[\\/]/)
    .pop() ?? "";
  base = base.replace(/[<>:"|?*]/g, "").replace(/^\.+/, "").trim();
  if (!base) base = porDefecto;
  if (ext && !base.toLowerCase().endsWith(`.${ext}`)) {
    // «catalogo.final» + pdf → «catalogo.final.pdf»; un nombre sin extensión también.
    base = `${base}.${ext}`;
  }
  if (base.length > 100) {
    const punto = base.lastIndexOf(".");
    const extension = punto > 0 && base.length - punto <= 8 ? base.slice(punto) : "";
    base = base.slice(0, 100 - extension.length) + extension;
  }
  return base;
}

/**
 * La «firma» real del archivo según sus primeros bytes.
 * @param {Uint8Array} bytes
 * @returns {"image/jpeg" | "image/png" | "image/webp" | "application/pdf" | "ooxml" | "ole" | null}
 */
export function sniffMime(bytes) {
  const b = bytes;
  if (b.length >= 3 && b[0] === 0xff && b[1] === 0xd8 && b[2] === 0xff) return "image/jpeg";
  if (b.length >= 8 && b[0] === 0x89 && b[1] === 0x50 && b[2] === 0x4e && b[3] === 0x47) return "image/png";
  if (
    b.length >= 12 &&
    b[0] === 0x52 && b[1] === 0x49 && b[2] === 0x46 && b[3] === 0x46 && // RIFF
    b[8] === 0x57 && b[9] === 0x45 && b[10] === 0x42 && b[11] === 0x50 // WEBP
  ) {
    return "image/webp";
  }
  if (b.length >= 5 && b[0] === 0x25 && b[1] === 0x50 && b[2] === 0x44 && b[3] === 0x46 && b[4] === 0x2d) {
    return "application/pdf";
  }
  if (b.length >= 4 && b[0] === 0x50 && b[1] === 0x4b && (b[2] === 0x03 || b[2] === 0x05) && (b[3] === 0x04 || b[3] === 0x06)) {
    return "ooxml"; // zip: docx, xlsx, pptx
  }
  if (b.length >= 8 && b[0] === 0xd0 && b[1] === 0xcf && b[2] === 0x11 && b[3] === 0xe0 && b[4] === 0xa1 && b[5] === 0xb1) {
    return "ole"; // doc, xls, ppt antiguos
  }
  return null;
}

/**
 * Texto plano: sin bytes nulos en los primeros 4 KB.
 * @param {Uint8Array} bytes
 */
function pareceTexto(bytes) {
  const n = Math.min(bytes.length, 4096);
  for (let i = 0; i < n; i++) if (bytes[i] === 0) return false;
  return true;
}

const OOXML = new Set([
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "application/vnd.openxmlformats-officedocument.presentationml.presentation",
]);
const OLE = new Set(["application/msword", "application/vnd.ms-excel", "application/vnd.ms-powerpoint"]);

/**
 * ¿Los bytes corresponden al tipo declarado?
 * @param {string} mimeDeclarado
 * @param {Uint8Array} bytes
 */
export function contenidoCoincide(mimeDeclarado, bytes) {
  const mime = mimeLimpio(mimeDeclarado);
  const firma = sniffMime(bytes);
  if (mime === "image/jpeg" || mime === "image/png" || mime === "image/webp" || mime === "application/pdf") {
    return firma === mime;
  }
  if (OOXML.has(mime)) return firma === "ooxml";
  if (OLE.has(mime)) return firma === "ole";
  if (mime === "text/plain" || mime === "text/csv") return firma === null && pareceTexto(bytes);
  return false;
}

/**
 * Valida el medio de una petición `/api/enviar` (sin descargar nada todavía).
 *
 * @param {unknown} medio
 * @returns {{ ok: true, valor: { tipo: "imagen" | "documento", url: string, nombre?: string, mime?: string, pie?: string } } | { ok: false, motivo: string }}
 */
export function validarMedioSaliente(medio) {
  if (!medio || typeof medio !== "object" || Array.isArray(medio)) return { ok: false, motivo: "cada medio debe ser un objeto" };
  const m = /** @type {Record<string, unknown>} */ (medio);
  if (m.tipo !== "imagen" && m.tipo !== "documento") {
    return { ok: false, motivo: "el tipo de medio debe ser «imagen» o «documento»" };
  }
  if (typeof m.url !== "string" || !m.url) return { ok: false, motivo: "falta la url del medio" };
  if (m.nombre !== undefined && m.nombre !== null && typeof m.nombre !== "string") {
    return { ok: false, motivo: "nombre debe ser texto" };
  }
  if (m.pie !== undefined && m.pie !== null && typeof m.pie !== "string") return { ok: false, motivo: "pie debe ser texto" };
  let mime;
  if (m.mime !== undefined && m.mime !== null) {
    if (typeof m.mime !== "string") return { ok: false, motivo: "mime debe ser texto" };
    mime = mimeLimpio(m.mime);
    if (!MIMES_SALIENTES[m.tipo].includes(mime)) {
      return { ok: false, motivo: `el tipo ${mime || "(vacío)"} no se puede enviar como ${m.tipo}` };
    }
  }
  return {
    ok: true,
    valor: {
      tipo: m.tipo,
      url: m.url,
      nombre: typeof m.nombre === "string" ? m.nombre : undefined,
      mime,
      pie: typeof m.pie === "string" ? m.pie : undefined,
    },
  };
}
