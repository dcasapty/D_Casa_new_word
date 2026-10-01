import { ErrorProveedor, type MensajeNeutro, type Proveedor, type Respuesta, type Solicitud } from "../nucleo/tipos";
import { postJson, type OpcionesHttp } from "./comun";

/**
 * Messages API de Anthropic por HTTP directo (el SDK oficial también corre en Workers; aquí se usa
 * fetch para no tener dependencias en el prototipo).
 * - cache_control en el system y en la ÚLTIMA herramienta: el prefijo tools→system se cachea
 *   (lectura 0,1× en Haiku 4.5 y Sonnet 5.5; mínimo cacheable 4 096 tokens en Haiku 4.5 y 512 en Sonnet 5.5).
 * - effort va en output_config (no en Haiku 4.5: da error). Nunca tool_choice any/tool (400 en 5.5).
 * - Los bloques crudos del asistente se reenvían SIN tocar (pensamiento preservado).
 */
const SIN_EFFORT = ["claude-haiku-4-5"];
/** Modelos con respaldo del lado del servidor ante `refusal` (skill claude-api: `fallbacks: "default"`). */
const CON_FALLBACK = ["claude-sonnet-5-5", "claude-opus-5-5"];

export class ProveedorAnthropic implements Proveedor {
  readonly id = "anthropic";
  constructor(private readonly op: OpcionesHttp) {}

  cuerpo(s: Solicitud): Record<string, unknown> {
    const tools = s.herramientas.map((h, i) => ({
      name: h.name,
      description: h.description,
      input_schema: h.input_schema,
      ...(i === s.herramientas.length - 1 ? { cache_control: { type: "ephemeral" } } : {}),
    }));
    const c: Record<string, unknown> = {
      model: s.modelo,
      max_tokens: s.maxTokens,
      system: [{ type: "text", text: s.sistema, cache_control: { type: "ephemeral" } }],
      messages: this.mensajes(s.mensajes),
    };
    if (tools.length) c.tools = tools;
    if (CON_FALLBACK.includes(s.modelo)) c.fallbacks = "default";
    if (s.esfuerzo && !SIN_EFFORT.includes(s.modelo)) {
      c.output_config = { effort: s.esfuerzo === "minimal" ? "low" : s.esfuerzo };
    }
    return c;
  }

  mensajes(ms: MensajeNeutro[]): { role: string; content: any[] }[] {
    const salida: { role: string; content: any[] }[] = [];
    const agregar = (role: string, bloques: any[]) => {
      const ult = salida[salida.length - 1];
      if (ult && ult.role === role) ult.content.push(...bloques);
      else salida.push({ role, content: [...bloques] });
    };
    for (const m of ms) {
      if (m.rol === "user") {
        agregar("user", [
          ...(m.imagenes ?? []).map((i) => ({ type: "image", source: { type: "base64", media_type: i.mimetype, data: i.datos } })),
          { type: "text", text: m.texto || "(sin texto)" },
        ]);
      } else if (m.rol === "assistant") {
        if (m.crudo?.proveedor === "anthropic" && Array.isArray(m.crudo.contenido)) {
          agregar("assistant", m.crudo.contenido as any[]);
          continue;
        }
        const b: any[] = m.texto ? [{ type: "text", text: m.texto }] : [];
        for (const l of m.llamadas ?? []) b.push({ type: "tool_use", id: l.id, name: l.nombre, input: l.argumentos });
        if (b.length) agregar("assistant", b);
      } else {
        agregar("user", [{ type: "tool_result", tool_use_id: m.llamadaId, content: m.texto, is_error: !!m.error }]);
      }
    }
    for (const s of salida) if (s.role === "user") s.content.sort((a, b) => (a.type === "tool_result" ? 0 : 1) - (b.type === "tool_result" ? 0 : 1));
    return salida;
  }

  async chatear(s: Solicitud, senal?: AbortSignal): Promise<Respuesta> {
    const cab: Record<string, string> = { "x-api-key": this.op.clave, "anthropic-version": "2023-06-01" };
    if (CON_FALLBACK.includes(s.modelo)) cab["anthropic-beta"] = "server-side-fallback-2026-07-01";
    if (this.op.gateway) {
      cab["cf-aig-collect-log-payload"] = "false";
      if (s.metadatos) cab["cf-aig-metadata"] = JSON.stringify(s.metadatos);
    }
    const d = (await postJson(this.op, "/v1/messages", cab, this.cuerpo(s), senal)) as Record<string, any>;
    const bloques: any[] = d.content ?? [];
    const texto = bloques.filter((b) => b.type === "text").map((b) => b.text).join("\n").trim();
    const llamadas = bloques.filter((b) => b.type === "tool_use").map((b) => ({ id: b.id, nombre: b.name, argumentos: b.input ?? {} }));
    if (d.stop_reason === "refusal" && !llamadas.length) {
      throw new ErrorProveedor("El modelo declinó la solicitud (refusal).", true, 200);
    }
    const u = d.usage ?? {};
    return {
      texto,
      llamadas,
      fin: llamadas.length ? "herramientas" : d.stop_reason === "max_tokens" ? "limite" : "fin",
      uso: {
        entrada: Number(u.input_tokens ?? 0),
        salida: Number(u.output_tokens ?? 0),
        cacheLectura: Number(u.cache_read_input_tokens ?? 0),
        cacheEscritura: Number(u.cache_creation_input_tokens ?? 0),
      },
      proveedor: this.id,
      modelo: String(d.model ?? s.modelo),
      crudo: bloques,
    };
  }
}
