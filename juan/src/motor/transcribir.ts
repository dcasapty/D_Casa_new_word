// Notas de voz → texto con Whisper de Workers AI. APAGADO por defecto: el contrato no permite que Workers AI
// sea obligatorio. Se enciende con TRANSCRIBIR_AUDIO=1 Y declarando el binding `ai` en wrangler.jsonc
// (docs/JUAN_WORKER.md). Sin eso, el bot le pide al cliente que escriba, o le dice que una vendedora la escucha.

import type { Env } from "../env";

export function transcriptorDe(env: Env): ((bytes: Uint8Array, mime: string) => Promise<string | null>) | undefined {
  if (env.TRANSCRIBIR_AUDIO !== "1" || !env.AI) return undefined;
  const ai = env.AI;
  return async (bytes) => {
    let bin = "";
    for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
    const r = (await ai.run("@cf/openai/whisper-large-v3-turbo", { audio: btoa(bin) })) as { text?: string };
    return r.text?.trim() || null;
  };
}
