// Un servidor FALSO compatible con OpenAI (Chat Completions) que se porta como la API de Meta (Muse Spark),
// según docs/auditoria/ronda3/brian-agente.md §2:
//   · exige `Authorization: Bearer <clave>`;
//   · SIEMPRE razona: `reasoning_effort: "none"` (o cualquier valor fuera de minimal|low|medium|high|xhigh) → HTTP 400;
//   · el razonamiento CUENTA dentro de `max_completion_tokens`: si se lo come todo, la respuesta llega vacía (finish_reason "length");
//   · `max_tokens` (alias deprecado) → 400; usa `max_completion_tokens`;
//   · `tool_choice` solo acepta "auto" (cualquier otro → 400);
//   · admite llamadas a herramientas en paralelo; informa `prompt_tokens_details.cached_tokens` y los tokens de razonamiento.
// Se le pasa al proveedor como `fetch`, así no hay red.

export interface PeticionAMeta {
  url: string;
  cabeceras: Record<string, string>;
  cuerpo: Record<string, any>;
}

export interface RespuestaDeMeta {
  texto?: string;
  llamadas?: { nombre: string; args: Record<string, unknown> }[];
  /** Tokens de entrada (prompt). */
  entrada?: number;
  /** Cuántos de los de entrada salieron de la caché automática. */
  cacheados?: number;
  /** Salida visible; el razonamiento se suma según `reasoning_effort`. */
  salida?: number;
  /** Fuerza un error HTTP (402, 429, 500...). */
  estado?: number;
}

export interface OpcionesServidorMeta {
  clave: string;
  /** Qué contesta a cada petición (la n.ª, desde 0). */
  guion: (peticion: PeticionAMeta, n: number) => RespuestaDeMeta;
}

export const TOKENS_DE_RAZONAMIENTO: Record<string, number> = { minimal: 50, low: 300, medium: 1200, high: 4000, xhigh: 12000 };
/** Lo mínimo que la respuesta visible necesita además del razonamiento. */
const MINIMO_VISIBLE = 30;

const json = (cuerpo: unknown, estado = 200) => new Response(JSON.stringify(cuerpo), { status: estado, headers: { "content-type": "application/json" } });
const error = (estado: number, mensaje: string) => json({ error: { message: mensaje, type: "invalid_request_error" } }, estado);

export function crearServidorMeta(op: OpcionesServidorMeta) {
  const peticiones: PeticionAMeta[] = [];
  const rechazos: { estado: number; mensaje: string }[] = [];

  const rechazar = (estado: number, mensaje: string) => {
    rechazos.push({ estado, mensaje });
    return error(estado, mensaje);
  };

  const servidorFetch: typeof fetch = async (recurso, init) => {
    const url = typeof recurso === "string" ? recurso : recurso instanceof URL ? recurso.toString() : recurso.url;
    const cabeceras = Object.fromEntries(Object.entries((init?.headers ?? {}) as Record<string, string>).map(([k, v]) => [k.toLowerCase(), String(v)]));
    const cuerpo = JSON.parse(String(init?.body ?? "{}")) as Record<string, any>;
    const peticion = { url, cabeceras, cuerpo };
    peticiones.push(peticion);
    const n = peticiones.length - 1;

    if (!url.endsWith("/chat/completions")) return rechazar(404, "ruta desconocida");
    if (cabeceras.authorization !== `Bearer ${op.clave}`) return rechazar(401, "Invalid API key");

    // ── Las particularidades de Muse Spark ──
    if (cuerpo.reasoning_effort !== undefined && !(cuerpo.reasoning_effort in TOKENS_DE_RAZONAMIENTO)) {
      return rechazar(400, `reasoning_effort "${cuerpo.reasoning_effort}" is not supported: Muse Spark always reasons (minimal, low, medium, high, xhigh)`);
    }
    if ("max_tokens" in cuerpo) return rechazar(400, "max_tokens is deprecated for this model; use max_completion_tokens");
    if (cuerpo.tool_choice !== undefined && cuerpo.tool_choice !== "auto") return rechazar(400, 'only "auto" is supported for tool_choice');
    if (typeof cuerpo.max_completion_tokens !== "number") return rechazar(400, "max_completion_tokens is required");

    const r = op.guion(peticion, n);
    if (r.estado) return rechazar(r.estado, `error simulado ${r.estado}`);

    const esfuerzo: string = cuerpo.reasoning_effort ?? "medium";
    const razonamiento = TOKENS_DE_RAZONAMIENTO[esfuerzo];
    const salidaVisible = r.salida ?? 40;
    const tope = cuerpo.max_completion_tokens as number;
    const entrada = r.entrada ?? 800;
    const uso = (completion: number) => ({
      prompt_tokens: entrada,
      completion_tokens: completion,
      total_tokens: entrada + completion,
      prompt_tokens_details: { cached_tokens: r.cacheados ?? 0 },
      completion_tokens_details: { reasoning_tokens: Math.min(razonamiento, completion) },
    });

    // El razonamiento se come el tope: no queda nada para responder.
    if (razonamiento + MINIMO_VISIBLE > tope) {
      return json({
        id: `chatcmpl-${n}`,
        object: "chat.completion",
        created: 0,
        model: cuerpo.model,
        choices: [{ index: 0, message: { role: "assistant", content: "" }, finish_reason: "length" }],
        usage: uso(tope),
      });
    }

    const mensaje: Record<string, unknown> = { role: "assistant", content: r.texto ?? null };
    if (r.llamadas?.length) {
      mensaje.tool_calls = r.llamadas.map((l, i) => ({ id: `call_${n}_${i}`, type: "function", function: { name: l.nombre, arguments: JSON.stringify(l.args) } }));
    }
    return json({
      id: `chatcmpl-${n}`,
      object: "chat.completion",
      created: 0,
      model: cuerpo.model,
      choices: [{ index: 0, message: mensaje, finish_reason: r.llamadas?.length ? "tool_calls" : "stop" }],
      usage: uso(razonamiento + salidaVisible),
    });
  };

  return { fetch: servidorFetch, peticiones, rechazos };
}
