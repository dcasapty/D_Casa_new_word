// Notas de voz de Andrés (el chat de la tienda, tienda/voz.ts) y de Brian del panel (odoo-panel-voz.ts): audio → SOLO texto.
//
// Lo que protege contra la clonación de voces (docs/JUAN.md › «Notas de voz de Andrés y de Brian del panel»):
//   · El audio NUNCA se guarda: ni en R2, ni en un Durable Object, ni en la conversación, ni en un registro (log). Se lee, se pasa a
//     Whisper de Workers AI (dentro de la cuenta de Cloudflare de D'CASA) y sus bytes se borran de la memoria (`fill(0)`) al terminar.
//   · No se devuelve, no se reenvía y no se usa para generar voz: de aquí solo sale el texto (ni los segmentos, ni las palabras con sus
//     tiempos, ni el VTT). En este Worker no existe ningún modelo que genere voz; el único modelo que recibe el audio es MODELO_WHISPER.
//   · Notas cortas, medidas de verdad: la duración es la que el decodificador va a sacar, contada paquete por paquete SIN decodificar
//     (motor/duracion.ts), nunca la que el archivo dice de sí mismo. Más larga que el tope de la ruta, o imposible de medir con
//     certeza: no llega a Whisper. Con esa misma duración se aparta y se cobra (revisión adversarial, 2026-11-16).
//   · Topes por sesión, por red, por día y un presupuesto (los de cada ruta), para que nadie la use como un transcriptor gratis.

import { costoDeLaVoz, duracionDecodificada, PRECIO_WHISPER_USD_POR_MINUTO, tipoDeAudio, TIPOS_DE_AUDIO, type TipoDeAudio } from "./duracion";
import { MODELO_WHISPER, whisperDe } from "./transcribir";
import type { Env } from "../env";

export { costoDeLaVoz, PRECIO_WHISPER_USD_POR_MINUTO, tipoDeAudio, TIPOS_DE_AUDIO, type TipoDeAudio };

/** Lo más que pesa una nota: un minuto grabado por el navegador pesa de 240 KB (Opus a 32 kbps, lo que pide la página) a ~1 MB. */
export const MAX_BYTES_VOZ = 1024 * 1024;
/** Lo más que dura una nota de Brian del panel (el navegador corta solo al llegar). */
export const MAX_SEGUNDOS_VOZ = 60;
/**
 * Lo más que dura una nota de Andrés: lo que cabe en un mensaje del chat (500 letras son unos 30 segundos hablados). Así la
 * privacidad dice la verdad («unos 30 segundos») y el texto casi nunca se recorta.
 */
export const MAX_SEGUNDOS_TIENDA = 30;
/** Margen para el navegador: MediaRecorder tarda un poco en parar. */
export const TOLERANCIA_SEGUNDOS = 5;
/** La transcripción (o un error claro) antes de esto. */
export const PLAZO_VOZ_MS = 20_000;

const ascii = (b: Uint8Array, desde: number, largo: number) => (b.length >= desde + largo ? String.fromCharCode(...b.subarray(desde, desde + largo)) : "");

/** Los bytes dicen lo mismo que el tipo: WebM (EBML 1A 45 DF A3), Ogg («OggS») o MP4 (caja «ftyp»). */
export function firmaDeAudio(b: Uint8Array, tipo: TipoDeAudio): boolean {
  if (tipo === "audio/webm") return b.length > 4 && b[0] === 0x1a && b[1] === 0x45 && b[2] === 0xdf && b[3] === 0xa3;
  if (tipo === "audio/ogg") return ascii(b, 0, 4) === "OggS";
  return ascii(b, 4, 4) === "ftyp";
}

/**
 * Los segundos que de verdad se decodifican (motor/duracion.ts: el TOC de cada paquete Opus, las tramas AAC de un MP4), o null si
 * no se pueden medir con certeza. Lo que el contenedor dice de sí mismo no cuenta.
 */
export function duracionDelContenedor(b: Uint8Array, tipo: TipoDeAudio): number | null {
  return duracionDecodificada(b, tipo);
}

// ── La nota validada ───────────────────────────────────────────────────────────────────────────────

export interface NotaDeVoz {
  bytes: Uint8Array;
  tipo: TipoDeAudio;
  /** Lo que de verdad dura (medido, no lo que dice el archivo). */
  segundos: number;
  /** El tope de la ruta (sin el margen del navegador). */
  maxSegundos: number;
}

export type ProblemaDeLaNota = { motivo: "tipo" | "audio" | "muy_pesada" | "muy_larga"; status: number };

/** La duración que dice el navegador (en milisegundos): un entero razonable, o null si no vino o no se entiende. */
export function duracionDeclarada(v: unknown): number | null {
  const n = typeof v === "string" && /^\d{1,7}$/.test(v.trim()) ? Number(v.trim()) : typeof v === "number" ? v : NaN;
  return Number.isInteger(n) && n >= 0 && n <= 9_999_999 ? n : null;
}

/**
 * La nota lista para transcribir, o el problema (sin repetir nunca el audio en el motivo). Lo que no se puede medir con certeza es
 * «audio» (no se transcribe); lo que dura más que `maxSegundos` (más el margen del navegador), «muy_larga». Todo ANTES de apartar.
 */
export function validarNota(bytes: Uint8Array, tipo: TipoDeAudio | null, declaradaMs: number | null, maxSegundos = MAX_SEGUNDOS_VOZ): NotaDeVoz | ProblemaDeLaNota {
  const aceptados = maxSegundos + TOLERANCIA_SEGUNDOS;
  if (!tipo) return { motivo: "tipo", status: 415 };
  if (bytes.byteLength === 0) return { motivo: "audio", status: 400 };
  if (bytes.byteLength > MAX_BYTES_VOZ) return { motivo: "muy_pesada", status: 413 };
  if (!firmaDeAudio(bytes, tipo)) return { motivo: "audio", status: 400 };
  if (declaradaMs !== null && declaradaMs > aceptados * 1000) return { motivo: "muy_larga", status: 413 };
  const segundos = duracionDecodificada(bytes, tipo);
  if (segundos === null) return { motivo: "audio", status: 400 };
  if (segundos > aceptados) return { motivo: "muy_larga", status: 413 };
  return { bytes, tipo, segundos, maxSegundos };
}

export const esProblema = (v: NotaDeVoz | ProblemaDeLaNota): v is ProblemaDeLaNota => "motivo" in v;

/** Lo que se aparta antes de llamar a Whisper: el costo de lo que de verdad dura la nota. */
export function reservaDeLaNota(nota: Pick<NotaDeVoz, "segundos">): number {
  // Nunca 0: con 0 no se miraría el presupuesto (un turno sin costo pasa siempre).
  return Math.max(0.00001, costoDeLaVoz(nota.segundos));
}

/** Lo que entendió Whisper, limpio: sin controles ni saltos, con los espacios juntos y recortado (entre palabras) a `max` letras. */
export function textoDeLaNota(texto: string, max: number): { texto: string; recortado: boolean } {
  const limpio = texto
    .replace(/[\u0000-\u001f\u007f-\u009f\u2028\u2029\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]+/g, " ")
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
  | { ok: true; texto: string; recortado: boolean; usd: number; estimado: boolean; segundos: number }
  | { ok: false; motivo: "no_disponible" | "muy_larga" | "no_se_entendio" | "tardo" | "fallo"; usd: number; estimado: boolean; segundos: number };

/**
 * Pasa la nota a texto con Whisper. `usd` es lo que costó: 0 si no se llamó a Whisper; si no, lo que de verdad dura la nota (medido)
 * o lo que diga Whisper, lo que sea mayor. Si Whisper tarda o falla, no se sabe cuánto trabajó: se anota la duración medida, marcada
 * «estimado». Los bytes de la nota se borran de la memoria al terminar, pase lo que pase.
 */
export async function transcribirNota(env: Env, nota: NotaDeVoz, op: { maxLetras: number; plazoMs?: number }): Promise<ResultadoNota> {
  const whisper = whisperDe(env);
  if (!whisper) {
    nota.bytes.fill(0);
    return { ok: false, motivo: "no_disponible", usd: 0, estimado: false, segundos: nota.segundos };
  }
  const cobro = (segundos: number, estimado = false) => ({ usd: costoDeLaVoz(segundos), estimado, segundos });
  const aceptados = nota.maxSegundos + TOLERANCIA_SEGUNDOS;
  let reloj: ReturnType<typeof setTimeout> | undefined;
  const plazo = new Promise<"tardo">((r) => (reloj = setTimeout(() => r("tardo"), op.plazoMs ?? PLAZO_VOZ_MS)));
  try {
    const r = await Promise.race([whisper(nota.bytes), plazo]);
    if (r === "tardo") return { ok: false, motivo: "tardo", ...cobro(nota.segundos, true) };
    const cobrado = cobro(Math.max(nota.segundos, r.segundos ?? 0));
    if (cobrado.segundos > aceptados) return { ok: false, motivo: "muy_larga", ...cobrado };
    if (!r.texto || ALUCINACIONES.some((a) => a.test(r.texto!))) return { ok: false, motivo: "no_se_entendio", ...cobrado };
    const limpio = textoDeLaNota(r.texto, op.maxLetras);
    if (!limpio.texto) return { ok: false, motivo: "no_se_entendio", ...cobrado };
    return { ok: true, texto: limpio.texto, recortado: limpio.recortado, ...cobrado };
  } catch {
    // El error de Workers AI no se repite (podría traer un pedazo de la petición); no se sabe si cobró: la duración medida.
    return { ok: false, motivo: "fallo", ...cobro(nota.segundos, true) };
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
