import { cabeceraCostoGateway, PRECIOS } from "../nucleo/precios";
import { ErrorProveedor, type LlamadaHerramienta, type MensajeNeutro, type Proveedor, type Respuesta, type Solicitud } from "../nucleo/tipos";
import { postJson, type OpcionesHttp } from "./comun";

/**
 * Chat Completions compatible con OpenAI. Sirve para:
 * - Meta Model API: base https://api.meta.ai/v1 (o el custom provider de AI Gateway), modelo muse-spark-1.3.
 *   Diferencias verificadas (extractos de dev.meta.ai + paquetes que ya la usan): `max_completion_tokens`,
 *   `reasoning_effort` sin "none" (siempre razona), `tool_choice` SOLO "auto" ⇒ aquí nunca se envía.
 * - OpenAI y otros compatibles.
 */
export interface OpcionesCompat extends OpcionesHttp {
  id: "meta" | "openai" | string;
  /** Lista blanca exacta de modelos permitidos (vacía = cualquiera). */
  permitidos?: string[];
}

export class ProveedorCompat implements Proveedor {
  readonly id: string;
  constructor(private readonly op: OpcionesCompat) {
    this.id = op.id;
  }

  /** Ningún ID que entrene con los datos (nivel Contributor de Meta) puede salir con datos de D'CASA. */
  static modeloProhibido(modelo: string): boolean {
    return /contributor/i.test(modelo);
  }

  cuerpo(s: Solicitud): Record<string, unknown> {
    if (ProveedorCompat.modeloProhibido(s.modelo)) {
      throw new ErrorProveedor(`Modelo prohibido: ${s.modelo} entrena con los prompts.`, false, 400);
    }
    if (this.op.permitidos?.length && !this.op.permitidos.includes(s.modelo)) {
      throw new ErrorProveedor(`Modelo fuera de la lista blanca: ${s.modelo}`, false, 400);
    }
    const c: Record<string, unknown> = {
      model: s.modelo,
      messages: [{ role: "system", content: s.sistema }, ...this.mensajes(s.mensajes)],
      max_completion_tokens: s.maxTokens,
    };
    if (s.herramientas.length) {
      c.tools = s.herramientas.map((h) => ({
        type: "function",
        function: { name: h.name, description: h.description, parameters: h.input_schema },
      }));
    }
    if (s.esfuerzo) c.reasoning_effort = s.esfuerzo;
    return c;
  }

  mensajes(ms: MensajeNeutro[]): unknown[] {
    return ms.map((m) => {
      if (m.rol === "user") {
        if (!m.imagenes?.length) return { role: "user", content: m.texto };
        return {
          role: "user",
          content: [
            { type: "text", text: m.texto },
            ...m.imagenes.map((i) => ({ type: "image_url", image_url: { url: `data:${i.mimetype};base64,${i.datos}` } })),
          ],
        };
      }
      if (m.rol === "assistant") {
        const a: Record<string, unknown> = { role: "assistant", content: m.texto || null };
        if (m.llamadas?.length) {
          a.tool_calls = m.llamadas.map((l) => ({
            id: l.id, type: "function", function: { name: l.nombre, arguments: JSON.stringify(l.argumentos) },
          }));
        }
        return a;
      }
      return { role: "tool", tool_call_id: m.llamadaId, content: m.texto };
    });
  }

  async chatear(s: Solicitud, senal?: AbortSignal): Promise<Respuesta> {
    const cab: Record<string, string> = { authorization: `Bearer ${this.op.clave}` };
    if (this.op.gateway) {
      cab["cf-aig-collect-log-payload"] = "false";
      if (s.metadatos) cab["cf-aig-metadata"] = JSON.stringify(s.metadatos);
      const costo = cabeceraCostoGateway(PRECIOS, this.id, s.modelo);
      if (costo) cab["cf-aig-custom-cost"] = costo;
    }
    const d = (await postJson(this.op, "/chat/completions", cab, this.cuerpo(s), senal)) as Record<string, any>;
    return ProveedorCompat.respuesta(d, this.id, s.modelo);
  }

  static respuesta(d: Record<string, any>, proveedor: string, modelo: string): Respuesta {
    const op = (d.choices ?? [])[0] ?? {};
    const msg = op.message ?? {};
    const llamadas: LlamadaHerramienta[] = (msg.tool_calls ?? []).map((c: any, i: number) => {
      let args: Record<string, unknown>;
      try {
        const v = JSON.parse(c.function?.arguments || "{}");
        args = v && typeof v === "object" && !Array.isArray(v) ? v : { __invalidos__: c.function?.arguments };
      } catch {
        args = { __invalidos__: c.function?.arguments };
      }
      return { id: c.id || `llamada_${i}`, nombre: c.function?.name, argumentos: args };
    });
    const u = d.usage ?? {};
    const cache = Number(u.prompt_tokens_details?.cached_tokens ?? 0);
    const fin = llamadas.length ? "herramientas" : op.finish_reason === "length" ? "limite" : op.finish_reason === "content_filter" ? "rechazo" : "fin";
    return {
      texto: String(msg.content ?? "").trim(),
      llamadas,
      fin,
      uso: { entrada: Math.max(0, Number(u.prompt_tokens ?? 0) - cache), salida: Number(u.completion_tokens ?? 0), cacheLectura: cache, cacheEscritura: 0 },
      proveedor,
      modelo: String(d.model ?? modelo),
    };
  }
}
