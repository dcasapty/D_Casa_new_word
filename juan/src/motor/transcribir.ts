// Notas de voz → texto con Whisper de Workers AI. Se enciende con TRANSCRIBIR_AUDIO=1 Y el binding `ai` de wrangler.jsonc
// (docs/JUAN_WORKER.md §12). Si falta cualquiera de los dos, no hay transcriptor y el bot le pide al cliente que escriba,
// o le dice que una vendedora la escucha. El audio no sale de la cuenta de Cloudflare de D'CASA.

import type { Env } from "../env";

/** Una nota de voz normal pesa unas decenas de KB; más de esto no es una nota de voz y no vale la pena procesarlo. */
const MAX_BYTES_AUDIO = 8 * 1024 * 1024;

export function transcriptorDe(env: Env): ((bytes: Uint8Array, mime: string) => Promise<string | null>) | undefined {
  if (env.TRANSCRIBIR_AUDIO !== "1" || !env.AI) return undefined;
  const ai = env.AI;
  return async (bytes) => {
    if (bytes.byteLength === 0 || bytes.byteLength > MAX_BYTES_AUDIO) return null;
    let bin = "";
    for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
    const r = (await ai.run("@cf/openai/whisper-large-v3-turbo", { audio: btoa(bin) })) as { text?: string };
    return r.text?.trim() || null;
  };
}
