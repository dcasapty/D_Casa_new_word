// Notas de voz → texto con Whisper de Workers AI. Se enciende con TRANSCRIBIR_AUDIO=1 Y el binding `ai` de wrangler.jsonc
// (docs/JUAN.md §12). Si falta cualquiera de los dos, no hay transcriptor y el bot le pide al cliente que escriba,
// o le dice que una vendedora la escucha. El audio no sale de la cuenta de Cloudflare de D'CASA.
//
// Lo usan las notas de voz de WhatsApp (`transcriptorDe`) y las de Andrés y Brian del panel (motor/voz.ts, con `whisperDe`, que
// además dice cuánto duró el audio para cobrarlo y para no devolver el texto de un audio más largo que el tope).

import type { Env } from "../env";

/** Una nota de voz normal pesa unas decenas de KB; más de esto no es una nota de voz y no vale la pena procesarlo. */
const MAX_BYTES_AUDIO = 8 * 1024 * 1024;
/** El único modelo que se llama con el audio: transcribe (audio → texto). No hay ningún modelo que genere voz en este Worker. */
export const MODELO_WHISPER = "@cf/openai/whisper-large-v3-turbo";

export interface Transcripcion {
  /** El texto, sin espacios sobrantes; null si Whisper no entendió nada. */
  texto: string | null;
  /** Lo que duró el audio según Whisper (`transcription_info.duration` o el final del último segmento); null si no lo dice. */
  segundos: number | null;
}

const numeroPositivo = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) && v >= 0 ? v : null);

/** La duración que dice la respuesta de Whisper, si la dice (la mayor de las dos pistas). */
function duracionDeLaRespuesta(r: unknown): number | null {
  if (!r || typeof r !== "object") return null;
  const o = r as { transcription_info?: { duration?: unknown }; segments?: unknown };
  const pistas: number[] = [];
  const info = numeroPositivo(o.transcription_info?.duration);
  if (info !== null) pistas.push(info);
  if (Array.isArray(o.segments)) {
    for (const s of o.segments) {
      const fin = numeroPositivo((s as { end?: unknown } | null)?.end);
      if (fin !== null) pistas.push(fin);
    }
  }
  return pistas.length ? Math.max(...pistas) : null;
}

/**
 * Whisper con el binding de esta cuenta, o undefined si está apagado (sin TRANSCRIBIR_AUDIO=1 o sin el binding). Solo devuelve el
 * texto y la duración: ni los segmentos, ni las palabras con sus tiempos, ni el VTT salen de aquí.
 */
export function whisperDe(env: Env): ((bytes: Uint8Array) => Promise<Transcripcion>) | undefined {
  if (env.TRANSCRIBIR_AUDIO !== "1" || !env.AI) return undefined;
  const ai = env.AI;
  return async (bytes) => {
    if (bytes.byteLength === 0 || bytes.byteLength > MAX_BYTES_AUDIO) return { texto: null, segundos: null };
    let bin = "";
    for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
    const r = (await ai.run(MODELO_WHISPER, { audio: btoa(bin) })) as { text?: unknown } | null;
    bin = "";
    const texto = typeof r?.text === "string" ? r.text.trim() : "";
    return { texto: texto || null, segundos: duracionDeLaRespuesta(r) };
  };
}

export function transcriptorDe(env: Env): ((bytes: Uint8Array, mime: string) => Promise<string | null>) | undefined {
  const whisper = whisperDe(env);
  if (!whisper) return undefined;
  return async (bytes) => (await whisper(bytes)).texto;
}
