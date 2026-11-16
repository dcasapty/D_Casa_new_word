// Notas de voz de Andrés (el chat de la tienda, tienda/voz.ts) y de Brian del panel (odoo-panel-voz.ts): audio → SOLO texto.
//
// Lo que protege contra la clonación de voces (docs/JUAN.md › «Notas de voz de Andrés y de Brian del panel»):
//   · El audio NUNCA se guarda: ni en R2, ni en un Durable Object, ni en la conversación, ni en un registro (log). Se lee, se pasa a
//     Whisper de Workers AI (dentro de la cuenta de Cloudflare de D'CASA) y sus bytes se borran de la memoria (`fill(0)`) al terminar.
//   · No se devuelve, no se reenvía y no se usa para generar voz: de aquí solo sale el texto (ni los segmentos, ni las palabras con sus
//     tiempos, ni el VTT). En este Worker no existe ningún modelo que genere voz; el único modelo que recibe el audio es MODELO_WHISPER.
//   · Notas cortas: hasta MAX_SEGUNDOS_VOZ y MAX_BYTES_VOZ, solo los tipos que graba un navegador (WebM, Ogg u MP4) y con los bytes que
//     corresponden al tipo. La duración se mira tres veces: la que dice el navegador, la del contenedor y la que dice Whisper; si la
//     nota resulta más larga que el tope, el texto no se devuelve.
//   · Topes por sesión, por red, por día y un presupuesto (los de cada ruta), para que nadie la use como un transcriptor gratis.

import { MODELO_WHISPER, whisperDe } from "./transcribir";
import type { Env } from "../env";

/** Lo más que pesa una nota: un minuto grabado por el navegador pesa de 240 KB (Opus a 32 kbps, lo que pide la página) a ~1 MB. */
export const MAX_BYTES_VOZ = 1024 * 1024;
/** Lo más que dura una nota de voz (el navegador corta solo al llegar). */
export const MAX_SEGUNDOS_VOZ = 60;
/** Margen para el navegador: MediaRecorder tarda un poco en parar y el contenedor redondea. */
export const TOLERANCIA_SEGUNDOS = 5;
/**
 * Lo que cobra Cloudflare por Whisper large-v3-turbo: US$0.0005 por minuto de audio (46.63 neurons por minuto), según la tabla de
 * precios de Workers AI (developers.cloudflare.com/workers-ai/platform/pricing, leída el 2026-11-16), sin descontar los neurons
 * gratis del día: mejor pasarse. REVISAR si cambia.
 */
export const PRECIO_WHISPER_USD_POR_MINUTO = 0.0005;
/**
 * Para apartar (y estimar) lo que puede costar un audio cuya duración todavía no se sabe: el peor caso es que esté grabado al mínimo
 * de Opus (6 kbps, RFC 6716). Así nunca se aparta de menos.
 */
export const BITS_POR_SEGUNDO_MINIMOS = 6000;
/** La transcripción (o un error claro) antes de esto. */
export const PLAZO_VOZ_MS = 20_000;

/** Lo que graba un navegador con MediaRecorder: Chrome y Edge WebM, Firefox Ogg (u WebM), Safari MP4. Nada más. */
export const TIPOS_DE_AUDIO = ["audio/webm", "audio/ogg", "audio/mp4"] as const;
export type TipoDeAudio = (typeof TIPOS_DE_AUDIO)[number];

/** El tipo de la cabecera (`audio/webm;codecs=opus` → `audio/webm`), o null si no es uno de los permitidos. */
export function tipoDeAudio(contentType: string | null | undefined): TipoDeAudio | null {
  const base = (contentType ?? "").split(";")[0].trim().toLowerCase();
  return (TIPOS_DE_AUDIO as readonly string[]).includes(base) ? (base as TipoDeAudio) : null;
}

const ascii = (b: Uint8Array, desde: number, largo: number) => (b.length >= desde + largo ? String.fromCharCode(...b.subarray(desde, desde + largo)) : "");

/** Los bytes dicen lo mismo que el tipo: WebM (EBML 1A 45 DF A3), Ogg («OggS») o MP4 (caja «ftyp»). */
export function firmaDeAudio(b: Uint8Array, tipo: TipoDeAudio): boolean {
  if (tipo === "audio/webm") return b.length > 4 && b[0] === 0x1a && b[1] === 0x45 && b[2] === 0xdf && b[3] === 0xa3;
  if (tipo === "audio/ogg") return ascii(b, 0, 4) === "OggS";
  return ascii(b, 4, 4) === "ftyp";
}

// ── La duración que dice el contenedor (sin decodificar nada; null si no se puede saber) ──────────────────────────

/** Ogg Opus: la posición (granule, a 48 kHz) de la última página que termina un paquete, menos el pre-skip de «OpusHead». */
function duracionOgg(b: Uint8Array): number | null {
  const cabeza = (() => {
    for (let i = 0; i + 8 <= Math.min(b.length, 512); i++) if (ascii(b, i, 8) === "OpusHead") return i;
    return -1;
  })();
  if (cabeza < 0 || b.length < cabeza + 12) return null;
  const preskip = b[cabeza + 10] | (b[cabeza + 11] << 8);
  const vista = new DataView(b.buffer, b.byteOffset, b.byteLength);
  for (let i = b.length - 27; i >= 0; i--) {
    if (b[i] !== 0x4f || b[i + 1] !== 0x67 || b[i + 2] !== 0x67 || b[i + 3] !== 0x53 || b[i + 4] !== 0) continue;
    const granulo = vista.getBigInt64(i + 6, true);
    if (granulo < 0n) continue; // -1: ningún paquete termina en esta página
    return Math.max(0, Number(granulo) - preskip) / 48_000;
  }
  return null;
}

/** Un número EBML de largo variable: el id (con su marca) o el tamaño (sin ella; `desconocido` si son todos unos). */
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

const ID = { SEGMENTO: 0x18538067, CLUSTER: 0x1f43b675, INFO: 0x1549a966, GRUPO: 0xa0, ESCALA: 0x2ad7b1, DURACION: 0x4489, TIEMPO: 0xe7, BLOQUE_SIMPLE: 0xa3, BLOQUE: 0xa1 };
const CONTENEDORES = new Set([ID.SEGMENTO, ID.CLUSTER, ID.INFO, ID.GRUPO]);

/**
 * WebM (lo que graba Chrome): la «Duration» de Info si viene; si no (MediaRecorder casi nunca la escribe), el tiempo del último
 * bloque (el del cluster más su desplazamiento). Se recorre elemento por elemento, sin buscar patrones sueltos en el audio.
 */
function duracionWebm(b: Uint8Array): number | null {
  let escala = 1_000_000; // ns por unidad (lo de fábrica de Matroska)
  let duracionInfo: number | null = null;
  let tiempoDelCluster = 0;
  let ultimo: number | null = null;
  const vista = new DataView(b.buffer, b.byteOffset, b.byteLength);
  let pos = 0;
  for (let pasos = 0; pos < b.length && pasos < 200_000; pasos++) {
    const id = vint(b, pos, true);
    if (!id) break;
    const tam = vint(b, pos + id.largo, false);
    if (!tam) break;
    const carga = pos + id.largo + tam.largo;
    if (CONTENEDORES.has(id.valor)) {
      pos = carga; // se entra (también con tamaño desconocido, como los clusters de MediaRecorder)
      continue;
    }
    if (tam.desconocido) break;
    const fin = carga + tam.valor;
    if (id.valor === ID.BLOQUE_SIMPLE || id.valor === ID.BLOQUE) {
      const pista = vint(b, carga, false);
      if (pista && carga + pista.largo + 2 <= b.length) ultimo = tiempoDelCluster + vista.getInt16(carga + pista.largo, false);
    } else if (fin <= b.length) {
      if (id.valor === ID.TIEMPO || id.valor === ID.ESCALA) {
        let v = 0;
        for (let i = carga; i < fin && i < carga + 8; i++) v = v * 256 + b[i];
        if (id.valor === ID.TIEMPO) tiempoDelCluster = v;
        else if (v > 0) escala = v;
      } else if (id.valor === ID.DURACION && (tam.valor === 4 || tam.valor === 8)) {
        const d = tam.valor === 4 ? vista.getFloat32(carga, false) : vista.getFloat64(carga, false);
        if (Number.isFinite(d) && d > 0) duracionInfo = d;
      }
    }
    if (fin > b.length) break;
    pos = fin;
  }
  if (duracionInfo !== null) return (duracionInfo * escala) / 1e9;
  return ultimo !== null ? (Math.max(0, ultimo) * escala) / 1e9 : null;
}

/** MP4: la duración de la caja «mvhd» (dentro de «moov»). Un MP4 por fragmentos (Safari) la trae en 0: null, la dirá Whisper. */
function duracionMp4(b: Uint8Array): number | null {
  const vista = new DataView(b.buffer, b.byteOffset, b.byteLength);
  const cajas = (desde: number, hasta: number, tipo: string): number | null => {
    let pos = desde;
    while (pos + 8 <= hasta) {
      let tam = vista.getUint32(pos, false);
      let cabecera = 8;
      if (tam === 1) {
        if (pos + 16 > hasta) return null;
        tam = Number(vista.getBigUint64(pos + 8, false));
        cabecera = 16;
      } else if (tam === 0) tam = hasta - pos;
      if (tam < cabecera || pos + tam > hasta) return null;
      if (ascii(b, pos + 4, 4) === tipo) return pos + cabecera;
      pos += tam;
    }
    return null;
  };
  const moov = cajas(0, b.length, "moov");
  if (moov === null) return null;
  const finMoov = moov - 8 + vista.getUint32(moov - 8, false);
  const mvhd = cajas(moov, Math.min(b.length, finMoov), "mvhd");
  if (mvhd === null || mvhd + 32 > b.length) return null;
  const v1 = b[mvhd] === 1;
  const escala = vista.getUint32(mvhd + (v1 ? 20 : 12), false);
  const dur = v1 ? Number(vista.getBigUint64(mvhd + 24, false)) : vista.getUint32(mvhd + 16, false);
  return escala > 0 && dur > 0 ? dur / escala : null;
}

/** Los segundos que dice el contenedor, o null si no lo dice (o no se entiende). Nunca lanza. */
export function duracionDelContenedor(b: Uint8Array, tipo: TipoDeAudio): number | null {
  try {
    const d = tipo === "audio/ogg" ? duracionOgg(b) : tipo === "audio/webm" ? duracionWebm(b) : duracionMp4(b);
    return d !== null && Number.isFinite(d) && d >= 0 ? d : null;
  } catch {
    return null;
  }
}

/** Los segundos que podría durar un audio de `bytes` en el peor caso (grabado al mínimo de Opus). */
export const peorDuracion = (bytes: number) => (Math.max(0, bytes) * 8) / BITS_POR_SEGUNDO_MINIMOS;

/** Lo que cobra Whisper por `segundos` de audio. */
export const costoDeLaVoz = (segundos: number) => (Math.max(0, segundos) / 60) * PRECIO_WHISPER_USD_POR_MINUTO;

/** Lo más que se acepta: el tope más el margen del navegador. */
const SEGUNDOS_ACEPTADOS = MAX_SEGUNDOS_VOZ + TOLERANCIA_SEGUNDOS;

// ── La nota validada ───────────────────────────────────────────────────────────────────────────────

export interface NotaDeVoz {
  bytes: Uint8Array;
  tipo: TipoDeAudio;
  /** La duración del contenedor, si la dice. */
  segundos: number | null;
}

export type ProblemaDeLaNota = { motivo: "tipo" | "audio" | "muy_pesada" | "muy_larga"; status: number };

/** La duración que dice el navegador (en milisegundos): un entero razonable, o null si no vino o no se entiende. */
export function duracionDeclarada(v: unknown): number | null {
  const n = typeof v === "string" && /^\d{1,7}$/.test(v.trim()) ? Number(v.trim()) : typeof v === "number" ? v : NaN;
  return Number.isInteger(n) && n >= 0 && n <= 9_999_999 ? n : null;
}

/** La nota lista para transcribir, o el problema (sin repetir nunca el audio en el motivo). */
export function validarNota(bytes: Uint8Array, tipo: TipoDeAudio | null, declaradaMs: number | null): NotaDeVoz | ProblemaDeLaNota {
  if (!tipo) return { motivo: "tipo", status: 415 };
  if (bytes.byteLength === 0) return { motivo: "audio", status: 400 };
  if (bytes.byteLength > MAX_BYTES_VOZ) return { motivo: "muy_pesada", status: 413 };
  if (!firmaDeAudio(bytes, tipo)) return { motivo: "audio", status: 400 };
  if (declaradaMs !== null && declaradaMs > SEGUNDOS_ACEPTADOS * 1000) return { motivo: "muy_larga", status: 413 };
  const segundos = duracionDelContenedor(bytes, tipo);
  if (segundos !== null && segundos > SEGUNDOS_ACEPTADOS) return { motivo: "muy_larga", status: 413 };
  return { bytes, tipo, segundos };
}

export const esProblema = (v: NotaDeVoz | ProblemaDeLaNota): v is ProblemaDeLaNota => "motivo" in v;

/** Lo que se aparta antes de llamar a Whisper: el costo con la duración del contenedor o, si no la dice, la del peor caso. */
export function reservaDeLaNota(nota: Pick<NotaDeVoz, "bytes" | "segundos">): number {
  const segundos = nota.segundos !== null ? Math.max(nota.segundos, peorDuracion(nota.bytes.byteLength)) : peorDuracion(nota.bytes.byteLength);
  // Mínimo un centavo de milésima: con 0 no se miraría el presupuesto (un turno sin costo pasa siempre).
  return Math.max(0.00001, costoDeLaVoz(segundos));
}

/** Lo que entendió Whisper, limpio: sin controles ni saltos, con los espacios juntos y recortado (entre palabras) a `max` letras. */
export function textoDeLaNota(texto: string, max: number): { texto: string; recortado: boolean } {
  const limpio = texto
    .replace(/[\u0000-\u001f\u007f-\u009f  ​-‏‪-‮⁦-⁩﻿]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  const letras = [...limpio];
  if (letras.length <= max) return { texto: limpio, recortado: false };
  let corte = letras.slice(0, max).join("");
  const espacio = corte.lastIndexOf(" ");
  if (espacio > max * 0.6) corte = corte.slice(0, espacio);
  return { texto: corte.trim(), recortado: true };
}

/**
 * Lo que Whisper inventa a veces con un audio en silencio (subtítulos de videos con los que aprendió). No es lo que dijo nadie: se
 * trata como «no se entendió».
 */
const ALUCINACIONES = [/amara\.org/i, /^subt[ií]tulos (realizados )?por/i];

export type ResultadoNota =
  | { ok: true; texto: string; recortado: boolean; usd: number; estimado: boolean; segundos: number | null }
  | { ok: false; motivo: "no_disponible" | "muy_larga" | "no_se_entendio" | "tardo" | "fallo"; usd: number; estimado: boolean; segundos: number | null };

/**
 * Pasa la nota a texto con Whisper. `usd` es lo que costó (0 si no se llamó a Whisper; con la duración real si Whisper o el contenedor
 * la dicen y, si no, la del peor caso, `estimado`). Los bytes de la nota se borran de la memoria al terminar, pase lo que pase.
 */
export async function transcribirNota(env: Env, nota: NotaDeVoz, op: { maxLetras: number; plazoMs?: number }): Promise<ResultadoNota> {
  const whisper = whisperDe(env);
  const sinCosto = { usd: 0, estimado: false, segundos: nota.segundos };
  if (!whisper) {
    nota.bytes.fill(0);
    return { ok: false, motivo: "no_disponible", ...sinCosto };
  }
  // Si no se sabe cuánto duró, se cobra el peor caso (mejor pasarse que quedarse corto con el presupuesto).
  const cobro = (segundos: number | null) => ({
    usd: costoDeLaVoz(segundos ?? peorDuracion(nota.bytes.byteLength)),
    estimado: segundos === null,
    segundos,
  });
  let reloj: ReturnType<typeof setTimeout> | undefined;
  const plazo = new Promise<"tardo">((r) => (reloj = setTimeout(() => r("tardo"), op.plazoMs ?? PLAZO_VOZ_MS)));
  try {
    const r = await Promise.race([whisper(nota.bytes), plazo]);
    // Whisper pudo seguir trabajando (y cobrarse): se anota con la duración que se sepa.
    if (r === "tardo") return { ok: false, motivo: "tardo", ...cobro(nota.segundos) };
    const pistas = [r.segundos, nota.segundos].filter((s): s is number => s !== null);
    const segundos = pistas.length ? Math.max(...pistas) : null;
    if (segundos !== null && segundos > SEGUNDOS_ACEPTADOS) return { ok: false, motivo: "muy_larga", ...cobro(segundos) };
    if (!r.texto || ALUCINACIONES.some((a) => a.test(r.texto!))) return { ok: false, motivo: "no_se_entendio", ...cobro(segundos) };
    const limpio = textoDeLaNota(r.texto, op.maxLetras);
    if (!limpio.texto) return { ok: false, motivo: "no_se_entendio", ...cobro(segundos) };
    return { ok: true, texto: limpio.texto, recortado: limpio.recortado, ...cobro(segundos) };
  } catch {
    // El error de Workers AI no se repite (podría traer un pedazo de la petición); se cobra lo que se sepa.
    return { ok: false, motivo: "fallo", ...cobro(nota.segundos) };
  } finally {
    clearTimeout(reloj);
    nota.bytes.fill(0);
  }
}

/** Para las pruebas y el diagnóstico: el único modelo al que llega el audio. */
export const MODELO_DE_LAS_NOTAS = MODELO_WHISPER;

/**
 * Lee el cuerpo crudo con un tope (sin confiar en `Content-Length`): null si pasa del tope. Lo leído de más se borra al momento.
 */
export async function leerConTope(req: Request, max: number): Promise<Uint8Array | null> {
  const largo = Number(req.headers.get("content-length"));
  if (Number.isFinite(largo) && largo > max) return null;
  if (!req.body) return new Uint8Array(0);
  const lector = req.body.getReader();
  const partes: Uint8Array[] = [];
  let total = 0;
  for (;;) {
    const { done, value } = await lector.read();
    if (done) break;
    if (!value) continue;
    total += value.byteLength;
    partes.push(value);
    if (total > max) {
      await lector.cancel().catch(() => undefined);
      for (const p of partes) p.fill(0);
      return null;
    }
  }
  const todo = new Uint8Array(total);
  let pos = 0;
  for (const p of partes) {
    todo.set(p, pos);
    pos += p.byteLength;
    p.fill(0);
  }
  return todo;
}
