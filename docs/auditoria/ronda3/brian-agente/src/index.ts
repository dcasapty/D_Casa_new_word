import { getAgentByName } from "agents";
import type { Env } from "./env";

export { BrianConversacion } from "./agente";
export { LibroUso } from "./libro_do";

/** Compara en tiempo constante (best practice de Workers: no comparar secretos con ===). */
async function firmaValida(secreto: string, datos: string, firmaHex: string): Promise<boolean> {
  const k = await crypto.subtle.importKey("raw", new TextEncoder().encode(secreto), { name: "HMAC", hash: "SHA-256" }, false, ["verify"]);
  const bytes = new Uint8Array((firmaHex.match(/../g) ?? []).map((h) => parseInt(h, 16)));
  return crypto.subtle.verify("HMAC", k, bytes, new TextEncoder().encode(datos));
}

/**
 * Entrada: POST /brian/<conversación>/(mensaje|confirmar)
 * Identidad: `x-brian-persona` (JSON) + `x-brian-firma` (HMAC del JSON + `x-brian-ts`, emitido por Odoo al abrir
 * el panel; caduca en 5 min). En producción: JWT corto para el WebSocket (ver informe §3.5).
 */
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const m = url.pathname.match(/^\/brian\/([\w-]{8,64})\/(mensaje|confirmar)$/);
    if (!m || request.method !== "POST") return new Response("no encontrado", { status: 404 });
    const persona = request.headers.get("x-brian-persona") ?? "";
    const ts = Number(request.headers.get("x-brian-ts") ?? 0);
    if (!persona || Math.abs(Date.now() - ts) > 5 * 60_000) return new Response("sin identidad", { status: 401 });
    if (!(await firmaValida(env.BRIAN_FIRMA, `${ts}.${persona}`, request.headers.get("x-brian-firma") ?? ""))) {
      return new Response("firma inválida", { status: 401 });
    }
    const id = (JSON.parse(persona) as { id: string }).id;
    const agente = await getAgentByName(env.BrianConversacion, `${id}:${m[1]}`);
    return agente.fetch(request);
  },
} satisfies ExportedHandler<Env>;
