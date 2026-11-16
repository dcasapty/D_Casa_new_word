// La duración que DE VERDAD se decodifica de una nota de voz, medida sin decodificar (revisión adversarial, 2026-11-16).
//
// Lo que el contenedor dice de sí mismo (la última página de un Ogg, la «Duration» de un WebM, la caja «mvhd» de un MP4) lo escribe
// quien arma el archivo: se puede mentir, y Whisper (ffmpeg) decodifica lo que hay, no lo que dice. Un Ogg Opus de 1 MB con paquetes
// de 2 bytes que valen 120 ms cada uno decodifica 11 horas aunque su última página diga «10 s». Por eso aquí se cuenta lo que el
// decodificador va a sacar, paquete por paquete:
//
//   · Opus (Ogg y WebM): la duración de cada paquete sale de su TOC (RFC 6716 §3.1): las tramas que trae por lo que dura cada una.
//   · AAC en MP4 (lo que graba Safari): cada muestra del contenedor es una trama de 1024 muestras de audio a la frecuencia de su
//     configuración (AudioSpecificConfig); se cuentan las muestras de `stsz` y de cada `trun`.
//
// Y se exige recorrer el archivo ENTERO con certeza: páginas Ogg seguidas, con su CRC, un solo flujo y numeración seguida; un WebM sin
// lacing ni compresión, con una sola pista `A_OPUS`; un MP4 con una sola pista AAC y sin listas de edición que repitan. Lo que no se
// puede medir así devuelve null y la nota NO se transcribe (ni se cobra): nunca se adivina para abajo.

/** Lo que graba un navegador con MediaRecorder (Chrome y Edge WebM, Firefox Ogg, Safari MP4) y lo que manda WhatsApp (Ogg). */
export const TIPOS_DE_AUDIO = ["audio/webm", "audio/ogg", "audio/mp4"] as const;
export type TipoDeAudio = (typeof TIPOS_DE_AUDIO)[number];

/** El tipo de la cabecera (`audio/webm;codecs=opus` → `audio/webm`), o null si no es uno de los que se saben medir. */
export function tipoDeAudio(contentType: string | null | undefined): TipoDeAudio | null {
  const base = (contentType ?? "").split(";")[0].trim().toLowerCase();
  return (TIPOS_DE_AUDIO as readonly string[]).includes(base) ? (base as TipoDeAudio) : null;
}

/**
 * Lo que cobra Cloudflare por Whisper large-v3-turbo: US$0.0005 por minuto de audio (46.63 neurons por minuto), según la tabla de
 * precios de Workers AI (developers.cloudflare.com/workers-ai/platform/pricing, leída el 2026-11-16), sin descontar los neurons
 * gratis del día: mejor pasarse. REVISAR si cambia.
 */
export const PRECIO_WHISPER_USD_POR_MINUTO = 0.0005;

/** Lo que cobra Whisper por `segundos` de audio decodificado. */
export const costoDeLaVoz = (segundos: number) => (Math.max(0, segundos) / 60) * PRECIO_WHISPER_USD_POR_MINUTO;

const ascii = (b: Uint8Array, desde: number, largo: number) => (b.length >= desde + largo ? String.fromCharCode(...b.subarray(desde, desde + largo)) : "");

/** Lo más que puede durar un paquete Opus (RFC 6716: 120 ms). */
export const MAX_PAQUETE_OPUS_S = 0.12;

/**
 * La duración de un paquete Opus por su TOC, en segundos. Un paquete vacío o mal formado se cuenta como el más largo posible (el
 * decodificador puede ocultar la pérdida con audio): así nunca se cuenta de menos.
 */
export function duracionPaqueteOpus(p: Uint8Array): number {
  if (p.length === 0) return MAX_PAQUETE_OPUS_S;
  const toc = p[0];
  const config = toc >> 3;
  const tramaMs = config < 12 ? [10, 20, 40, 60][config & 3] : config < 16 ? [10, 20][config & 1] : [2.5, 5, 10, 20][config & 3];
  const codigo = toc & 3;
  let tramas = codigo === 0 ? 1 : 2;
  if (codigo === 3) {
    if (p.length < 2) return MAX_PAQUETE_OPUS_S;
    tramas = p[1] & 0x3f;
    if (tramas === 0) return MAX_PAQUETE_OPUS_S;
  }
  const ms = tramas * tramaMs;
  return ms > 120 ? MAX_PAQUETE_OPUS_S : ms / 1000;
}

// ── Ogg Opus ───────────────────────────────────────────────────────────────────────────────────────────

const TABLA_CRC = (() => {
  const t = new Uint32Array(256);
  for (let i = 0; i < 256; i++) {
    let r = i << 24;
    for (let k = 0; k < 8; k++) r = r & 0x80000000 ? (r << 1) ^ 0x04c11db7 : r << 1;
    t[i] = r >>> 0;
  }
  return t;
})();

/** El CRC de una página Ogg (con el campo del CRC, bytes 22 a 25, en cero). */
function crcDePagina(b: Uint8Array, desde: number, hasta: number): number {
  let c = 0;
  for (let i = desde; i < hasta; i++) {
    const x = i - desde >= 22 && i - desde < 26 ? 0 : b[i];
    c = ((c << 8) ^ TABLA_CRC[((c >>> 24) ^ x) & 0xff]) >>> 0;
  }
  return c >>> 0;
}

/**
 * Ogg Opus: cada página pegada a la anterior, con su CRC (una página con el CRC malo haría que ffmpeg busque la siguiente «OggS»
 * DENTRO de su cuerpo, donde podría haber audio escondido), un solo flujo, la numeración seguida, nada después del final. El primer
 * paquete es «OpusHead» y el segundo «OpusTags»; los demás se suman por su TOC, menos el pre-skip.
 */
export function medirOgg(b: Uint8Array): number | null {
  const vista = new DataView(b.buffer, b.byteOffset, b.byteLength);
  let pos = 0;
  let serie: number | null = null;
  let secuencia = 0;
  let terminado = false;
  let indice = 0;
  let preskip = 0;
  let segundos = 0;
  // El paquete que se está armando: sus primeros bytes (para el TOC o la cabecera) y su largo.
  let cabeza: number[] | null = null;
  let largo = 0;
  const cerrarPaquete = (): boolean => {
    const p = Uint8Array.from(cabeza ?? []);
    if (indice === 0) {
      if (largo < 19 || ascii(p, 0, 8) !== "OpusHead" || p[8] === 0 || p[8] > 15) return false;
      preskip = p[10] | (p[11] << 8);
    } else if (indice === 1) {
      if (ascii(p, 0, 8) !== "OpusTags") return false;
    } else {
      segundos += duracionPaqueteOpus(largo === 0 ? new Uint8Array(0) : p.subarray(0, Math.min(2, largo)));
    }
    indice++;
    cabeza = null;
    largo = 0;
    return true;
  };
  while (pos < b.length) {
    if (terminado || pos + 27 > b.length || ascii(b, pos, 4) !== "OggS" || b[pos + 4] !== 0) return null;
    const tipo = b[pos + 5];
    const estaSerie = vista.getUint32(pos + 14, true);
    const numero = vista.getUint32(pos + 18, true);
    const segmentos = b[pos + 26];
    if (pos + 27 + segmentos > b.length) return null;
    let cuerpo = 0;
    for (let i = 0; i < segmentos; i++) cuerpo += b[pos + 27 + i];
    const fin = pos + 27 + segmentos + cuerpo;
    if (fin > b.length || crcDePagina(b, pos, fin) !== vista.getUint32(pos + 22, true)) return null;
    if (serie === null) {
      if (!(tipo & 2)) return null; // la primera página abre el flujo
      serie = estaSerie;
    } else if (estaSerie !== serie || tipo & 2 || numero !== secuencia + 1) {
      return null; // otro flujo, un flujo encadenado o una página que falta o sobra
    }
    secuencia = numero;
    // La marca de «continúa el paquete anterior» tiene que coincidir con lo que quedó a medias.
    if (Boolean(tipo & 1) !== (cabeza !== null)) return null;
    let dato = pos + 27 + segmentos;
    for (let i = 0; i < segmentos; i++) {
      const v = b[pos + 27 + i];
      if (cabeza === null) cabeza = [];
      for (let k = 0; k < v && cabeza.length < 19; k++) cabeza.push(b[dato + k]);
      largo += v;
      dato += v;
      if (v < 255 && !cerrarPaquete()) return null;
    }
    if (tipo & 4) terminado = true;
    pos = fin;
  }
  // Un paquete a medias al final también se cuenta (mejor de más).
  if (cabeza !== null && !cerrarPaquete()) return null;
  if (indice < 2) return null;
  return Math.max(0, segundos - preskip / 48_000);
}

// ── WebM (Matroska) con Opus ───────────────────────────────────────────────────────────────────────────

function vint(b: Uint8Array, pos: number, esId: boolean): { valor: number; largo: number; desconocido: boolean } | null {
  const primero = b[pos];
  if (primero === undefined || primero === 0) return null;
  let largo = 1;
  while (largo <= 8 && !(primero & (0x80 >> (largo - 1)))) largo++;
  if (largo > (esId ? 4 : 8) || pos + largo > b.length) return null;
  let valor = esId ? primero : primero & (0xff >> largo);
  let unos = valor === 0xff >> largo;
  for (let i = 1; i < largo; i++) {
    valor = valor * 256 + b[pos + i];
    unos = unos && b[pos + i] === 0xff;
  }
  return { valor, largo, desconocido: !esId && unos };
}

const EBML = {
  SEGMENTO: 0x18538067,
  CLUSTER: 0x1f43b675,
  PISTAS: 0x1654ae6b,
  PISTA: 0xae,
  CODEC: 0x86,
  CODIFICACIONES: 0x6d80,
  GRUPO: 0xa0,
  BLOQUE: 0xa1,
  BLOQUE_SIMPLE: 0xa3,
  BLOQUE_CIFRADO: 0xaf,
};
/** Se entra en ellos (los demás se saltan por su tamaño). Solo el segmento y el cluster pueden tener tamaño desconocido. */
const CONTENEDORES = new Set([EBML.SEGMENTO, EBML.CLUSTER, EBML.PISTAS, EBML.PISTA, EBML.GRUPO]);

/**
 * WebM: el archivo entero, elemento por elemento, sin que sobre ni falte un byte. Una sola pista y que sea `A_OPUS`; sin compresión
 * ni cifrado (cambiarían los bytes del TOC) y sin lacing (varias tramas en un bloque). Cada bloque es un paquete Opus.
 */
export function medirWebm(b: Uint8Array): number | null {
  let pos = 0;
  let pistas = 0;
  let codec = "";
  let bloques = 0;
  let segundos = 0;
  for (let pasos = 0; pos < b.length; pasos++) {
    if (pasos > 2_000_000) return null;
    const id = vint(b, pos, true);
    if (!id) return null;
    const tam = vint(b, pos + id.largo, false);
    if (!tam) return null;
    const carga = pos + id.largo + tam.largo;
    if (CONTENEDORES.has(id.valor)) {
      if (tam.desconocido && id.valor !== EBML.SEGMENTO && id.valor !== EBML.CLUSTER) return null;
      if (id.valor === EBML.PISTA) pistas++;
      pos = carga;
      continue;
    }
    if (tam.desconocido) return null;
    const fin = carga + tam.valor;
    if (fin > b.length) return null;
    if (id.valor === EBML.CODIFICACIONES || id.valor === EBML.BLOQUE_CIFRADO) return null;
    if (id.valor === EBML.CODEC) codec = ascii(b, carga, tam.valor);
    if (id.valor === EBML.BLOQUE_SIMPLE || id.valor === EBML.BLOQUE) {
      const pista = vint(b, carga, false);
      if (!pista) return null;
      // Pista (vint), tiempo (2 bytes) y banderas; los bits 1-2 de las banderas son el lacing.
      const banderas = carga + pista.largo + 2;
      if (banderas >= fin || (b[banderas] >> 1) & 3) return null; // sin banderas o con lacing: no se mide con certeza
      segundos += duracionPaqueteOpus(b.subarray(banderas + 1, fin));
      bloques++;
    }
    pos = fin;
  }
  if (pos !== b.length || pistas !== 1 || codec !== "A_OPUS" || bloques === 0) return null;
  return segundos;
}

// ── MP4 con AAC ───────────────────────────────────────────────────────────────────────────────────────

interface Caja {
  tipo: string;
  carga: number;
  fin: number;
}

/** Las cajas seguidas de [desde, hasta), sin que sobre ni falte un byte; null si alguna está mal. */
function cajas(b: Uint8Array, desde: number, hasta: number): Caja[] | null {
  const vista = new DataView(b.buffer, b.byteOffset, b.byteLength);
  const lista: Caja[] = [];
  let pos = desde;
  while (pos < hasta) {
    if (pos + 8 > hasta) return null;
    let tam = vista.getUint32(pos, false);
    let cabecera = 8;
    if (tam === 1) {
      if (pos + 16 > hasta) return null;
      tam = Number(vista.getBigUint64(pos + 8, false));
      cabecera = 16;
    } else if (tam === 0) {
      tam = hasta - pos;
    }
    if (tam < cabecera || pos + tam > hasta) return null;
    lista.push({ tipo: ascii(b, pos + 4, 4), carga: pos + cabecera, fin: pos + tam });
    pos += tam;
  }
  return lista;
}

const hijo = (b: Uint8Array, padre: Caja | undefined, tipo: string): Caja | undefined => (padre ? cajas(b, padre.carga, padre.fin)?.find((c) => c.tipo === tipo) : undefined);
const hijos = (b: Uint8Array, padre: Caja, tipo: string): Caja[] | null => {
  const l = cajas(b, padre.carga, padre.fin);
  return l ? l.filter((c) => c.tipo === tipo) : null;
};

/** Un descriptor MPEG-4 (etiqueta + largo de 1 a 4 bytes). */
function descriptor(b: Uint8Array, pos: number, fin: number): { etiqueta: number; carga: number; fin: number } | null {
  if (pos >= fin) return null;
  const etiqueta = b[pos];
  let largo = 0;
  let i = pos + 1;
  for (let n = 0; n < 4; n++, i++) {
    if (i >= fin) return null;
    largo = (largo << 7) | (b[i] & 0x7f);
    if (!(b[i] & 0x80)) {
      i++;
      break;
    }
  }
  return i + largo <= fin ? { etiqueta, carga: i, fin: i + largo } : null;
}

const FRECUENCIAS = [96000, 88200, 64000, 48000, 44100, 32000, 24000, 22050, 16000, 12000, 11025, 8000, 7350];

/** La frecuencia de la AudioSpecificConfig de AAC (LC, SBR o PS) dentro de `esds`; null si no es AAC o no se entiende. */
function frecuenciaAac(b: Uint8Array, esds: Caja): number | null {
  // esds: versión y banderas (4) + ES_Descriptor (3) → DecoderConfigDescriptor (4) → DecoderSpecificInfo (5).
  const es = descriptor(b, esds.carga + 4, esds.fin);
  if (!es || es.etiqueta !== 3) return null;
  let p = es.carga + 2;
  const banderas = b[p++];
  if (banderas & 0x80) p += 2;
  if (banderas & 0x40) p += 1 + b[p];
  if (banderas & 0x20) p += 2;
  const dc = descriptor(b, p, es.fin);
  if (!dc || dc.etiqueta !== 4 || b[dc.carga] !== 0x40) return null; // 0x40 = MPEG-4 Audio
  const ds = descriptor(b, dc.carga + 13, dc.fin);
  if (!ds || ds.etiqueta !== 5 || ds.fin - ds.carga < 2) return null;
  // AudioSpecificConfig: el tipo (5 bits) y el índice de frecuencia (4 bits; 15 = 24 bits explícitos).
  let pos = ds.carga * 8;
  const leer = (n: number) => {
    let v = 0;
    for (let k = 0; k < n; k++, pos++) {
      if (pos >= ds.fin * 8) throw new Error("corta");
      v = v * 2 + ((b[pos >> 3] >> (7 - (pos & 7))) & 1);
    }
    return v;
  };
  try {
    let tipo = leer(5);
    if (tipo === 31) tipo = 32 + leer(6);
    if (![2, 5, 29].includes(tipo)) return null; // AAC-LC, o con SBR / PS (tramas de 1024 a la frecuencia de base)
    const indice = leer(4);
    const frecuencia = indice === 15 ? leer(24) : FRECUENCIAS[indice];
    return frecuencia && frecuencia >= 7350 && frecuencia <= 96000 ? frecuencia : null;
  } catch {
    return null;
  }
}

/**
 * MP4 (Safari): el archivo entero en cajas; una sola pista, de sonido, AAC; las muestras de `stsz` más las de cada `trun` (en un
 * MP4 por fragmentos). Cada muestra es una trama de 1024 a la frecuencia de base. Una lista de edición con más de una entrada podría
 * repetir el audio: no se mide.
 */
export function medirMp4(b: Uint8Array): number | null {
  const vista = new DataView(b.buffer, b.byteOffset, b.byteLength);
  const arriba = cajas(b, 0, b.length);
  if (!arriba || arriba[0]?.tipo !== "ftyp") return null;
  const moov = arriba.filter((c) => c.tipo === "moov");
  if (moov.length !== 1) return null;
  const trak = hijos(b, moov[0], "trak");
  if (!trak || trak.length !== 1) return null;
  const elst = hijo(b, hijo(b, trak[0], "edts"), "elst");
  if (elst && (elst.fin - elst.carga < 8 || vista.getUint32(elst.carga + 4, false) > 1)) return null;
  const mdia = hijo(b, trak[0], "mdia");
  const hdlr = hijo(b, mdia, "hdlr");
  if (!hdlr || ascii(b, hdlr.carga + 8, 4) !== "soun") return null;
  const stbl = hijo(b, hijo(b, mdia, "minf"), "stbl");
  const stsd = hijo(b, stbl, "stsd");
  if (!stsd || stsd.fin - stsd.carga < 8 || vista.getUint32(stsd.carga + 4, false) !== 1) return null;
  const entradas = cajas(b, stsd.carga + 8, stsd.fin);
  if (!entradas || entradas.length !== 1 || entradas[0].tipo !== "mp4a") return null;
  const mp4a = entradas[0];
  // AudioSampleEntry: 6 reservados + índice (2) + versión (2) …; la versión 0 ocupa 28 bytes antes de las cajas hijas.
  if (mp4a.fin - mp4a.carga < 28 || vista.getUint16(mp4a.carga + 8, false) !== 0) return null;
  const esds = cajas(b, mp4a.carga + 28, mp4a.fin)?.find((c) => c.tipo === "esds");
  const frecuencia = esds ? frecuenciaAac(b, esds) : null;
  if (!frecuencia) return null;
  const stsz = hijo(b, stbl, "stsz");
  if (!stsz || stsz.fin - stsz.carga < 12) return null;
  let muestras = vista.getUint32(stsz.carga + 8, false);
  for (const moof of arriba.filter((c) => c.tipo === "moof")) {
    const trafs = hijos(b, moof, "traf");
    if (!trafs) return null;
    for (const traf of trafs) {
      const truns = hijos(b, traf, "trun");
      if (!truns) return null;
      for (const trun of truns) {
        if (trun.fin - trun.carga < 8) return null;
        muestras += vista.getUint32(trun.carga + 4, false);
      }
    }
  }
  return (muestras * 1024) / frecuencia;
}

/** Los segundos que de verdad se decodifican, o null si no se pueden medir con certeza. Nunca lanza. */
export function duracionDecodificada(b: Uint8Array, tipo: TipoDeAudio): number | null {
  try {
    const d = tipo === "audio/ogg" ? medirOgg(b) : tipo === "audio/webm" ? medirWebm(b) : medirMp4(b);
    return d !== null && Number.isFinite(d) && d >= 0 ? d : null;
  } catch {
    return null;
  }
}
