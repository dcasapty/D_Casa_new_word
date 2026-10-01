import { describe, expect, it } from "vitest";
import { cabeceraCostoGateway, costoMicro, PRECIOS, PrecioPendiente } from "../src/nucleo/precios";
import { OdooJson2 } from "../src/nucleo/odoo";
import { ProveedorAnthropic } from "../src/proveedores/anthropic";
import { ProveedorCompat } from "../src/proveedores/openai_compat";
import type { Solicitud } from "../src/nucleo/tipos";

const SOL: Solicitud = {
  modelo: "muse-spark-1.3",
  sistema: "SIS",
  herramientas: [
    { name: "a", description: "A", input_schema: { type: "object" } },
    { name: "b", description: "B", input_schema: { type: "object" } },
  ],
  mensajes: [
    { rol: "user", texto: "hola", imagenes: [{ mimetype: "image/png", datos: "AAA" }] },
    { rol: "assistant", texto: "", llamadas: [{ id: "x1", nombre: "a", argumentos: { q: 1 } }] },
    { rol: "tool", llamadaId: "x1", nombre: "a", texto: "{}" },
  ],
  maxTokens: 1000,
  esfuerzo: "low",
  metadatos: { persona: "u1" },
};

function fetchFalso(respuesta: unknown, estado = 200) {
  const vistas: { url: string; init: RequestInit }[] = [];
  const f = async (url: string, init: RequestInit) => {
    vistas.push({ url, init });
    return new Response(JSON.stringify(respuesta), { status: estado });
  };
  return { f, vistas };
}

describe("precios (data/precios.json)", () => {
  it("calcula microdólares exactos con caché (Sonnet 5.5 oficial)", () => {
    // 1000×2 + 500×2,5 + 4000×0,2 + 300×10 = 2000 + 1250 + 800 + 3000
    expect(costoMicro(PRECIOS, "anthropic", "claude-sonnet-5-5", { entrada: 1000, cacheEscritura: 500, cacheLectura: 4000, salida: 300 })).toBe(7050);
  });
  it("un precio PENDIENTE no se rellena: lanza", () => {
    expect(() => costoMicro(PRECIOS, "openai", "gpt-5.4-mini", { entrada: 1, salida: 1, cacheLectura: 0, cacheEscritura: 0 })).toThrow(PrecioPendiente);
  });
  it("cada precio lleva fuente y fecha", () => {
    for (const p of Object.values(PRECIOS.modelos)) {
      expect(p.fuente).toMatch(/^https:\/\//);
      expect(p.consultado).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    }
  });
  it("arma cf-aig-custom-cost por token para AI Gateway", () => {
    const c = JSON.parse(cabeceraCostoGateway(PRECIOS, "meta", "muse-spark-1.3")!);
    expect(c.per_token_in).toBeCloseTo(1.25e-6);
    expect(c.per_cache_read_token).toBeCloseTo(0.15e-6);
  });
});

describe("Meta (Chat Completions compatible)", () => {
  it("manda max_completion_tokens y reasoning_effort, nunca tool_choice; imágenes como image_url", async () => {
    const { f, vistas } = fetchFalso({
      model: "muse-spark-1.3",
      choices: [{ finish_reason: "stop", message: { content: " listo " } }],
      usage: { prompt_tokens: 5000, completion_tokens: 40, prompt_tokens_details: { cached_tokens: 4096 } },
    });
    const p = new ProveedorCompat({ id: "meta", base: "https://api.meta.ai/v1/", clave: "LLM|x", fetch: f, gateway: true });
    const r = await p.chatear(SOL);
    const v = vistas[0]!;
    expect(v.url).toBe("https://api.meta.ai/v1/chat/completions");
    const cuerpo = JSON.parse(String(v.init.body));
    expect(cuerpo.max_completion_tokens).toBe(1000);
    expect(cuerpo.reasoning_effort).toBe("low");
    expect(cuerpo).not.toHaveProperty("tool_choice");
    expect(cuerpo).not.toHaveProperty("max_tokens");
    expect(cuerpo.messages[0]).toEqual({ role: "system", content: "SIS" });
    expect(cuerpo.messages[1].content[1].type).toBe("image_url");
    expect(cuerpo.messages[2].tool_calls[0].function.arguments).toBe('{"q":1}');
    expect(cuerpo.messages[3]).toEqual({ role: "tool", tool_call_id: "x1", content: "{}" });
    const h = v.init.headers as Record<string, string>;
    expect(h.authorization).toBe("Bearer LLM|x");
    expect(h["cf-aig-collect-log-payload"]).toBe("false");
    expect(JSON.parse(h["cf-aig-metadata"]!)).toEqual({ persona: "u1" });
    expect(h["cf-aig-custom-cost"]).toBeDefined();
    expect(r.texto).toBe("listo");
    expect(r.uso).toEqual({ entrada: 904, salida: 40, cacheLectura: 4096, cacheEscritura: 0 });
  });
  it("prohíbe cualquier modelo «contributor» (entrena con los prompts) sin llamar a la red", async () => {
    const { f, vistas } = fetchFalso({});
    const p = new ProveedorCompat({ id: "meta", base: "https://api.meta.ai/v1", clave: "k", fetch: f });
    await expect(p.chatear({ ...SOL, modelo: "muse-spark-1.3-contributor" })).rejects.toThrow(/prohibido/);
    expect(vistas).toHaveLength(0);
  });
  it("402 (sin saldo) no es reintentable; 429 sí", async () => {
    const p402 = new ProveedorCompat({ id: "meta", base: "b", clave: "k", fetch: fetchFalso({}, 402).f });
    await expect(p402.chatear(SOL)).rejects.toMatchObject({ estado: 402, reintentable: false });
    const p429 = new ProveedorCompat({ id: "meta", base: "b", clave: "k", fetch: fetchFalso({}, 429).f });
    await expect(p429.chatear(SOL)).rejects.toMatchObject({ estado: 429, reintentable: true });
  });
  it("argumentos JSON inválidos no rompen el bucle", () => {
    const r = ProveedorCompat.respuesta({ choices: [{ message: { tool_calls: [{ id: "c", function: { name: "a", arguments: "{mal" } }] } }] }, "meta", "m");
    expect(r.llamadas[0]!.argumentos).toEqual({ __invalidos__: "{mal" });
  });
});

describe("Anthropic (Messages API)", () => {
  it("cachea system y la ÚLTIMA herramienta; effort en output_config; fallback de servidor en Sonnet 5.5", async () => {
    const { f, vistas } = fetchFalso({
      content: [{ type: "text", text: "ok" }], stop_reason: "end_turn",
      usage: { input_tokens: 10, output_tokens: 5, cache_read_input_tokens: 6000, cache_creation_input_tokens: 0 },
    });
    const p = new ProveedorAnthropic({ base: "https://api.anthropic.com", clave: "sk", fetch: f });
    const r = await p.chatear({ ...SOL, modelo: "claude-sonnet-5-5" });
    const c = JSON.parse(String(vistas[0]!.init.body));
    expect(vistas[0]!.url).toBe("https://api.anthropic.com/v1/messages");
    expect(c.system[0].cache_control).toEqual({ type: "ephemeral" });
    expect(c.tools[0]).not.toHaveProperty("cache_control");
    expect(c.tools[1].cache_control).toEqual({ type: "ephemeral" });
    expect(c.output_config).toEqual({ effort: "low" });
    expect(c).not.toHaveProperty("tool_choice");
    expect(c.fallbacks).toBe("default");
    expect((vistas[0]!.init.headers as Record<string, string>)["anthropic-beta"]).toBe("server-side-fallback-2026-07-01");
    // tool_result va en un mensaje de usuario propio, primero
    expect(c.messages[2].content[0].type).toBe("tool_result");
    expect(r.uso.cacheLectura).toBe(6000);
  });
  it("Haiku 4.5 no recibe effort (no lo admite)", () => {
    const c = new ProveedorAnthropic({ base: "b", clave: "k" }).cuerpo({ ...SOL, modelo: "claude-haiku-4-5" });
    expect(c).not.toHaveProperty("output_config");
    expect(c).not.toHaveProperty("fallbacks");
  });
  it("reenvía sin tocar los bloques crudos de un turno anterior de Claude (pensamiento preservado)", () => {
    const crudo = [{ type: "thinking", thinking: "", signature: "s" }, { type: "tool_use", id: "t", name: "a", input: {} }];
    const ms = new ProveedorAnthropic({ base: "b", clave: "k" }).mensajes([
      { rol: "user", texto: "hola" },
      { rol: "assistant", texto: "", llamadas: [], crudo: { proveedor: "anthropic", contenido: crudo } },
    ]);
    expect(ms[1]!.content).toEqual(crudo);
  });
});

describe("Odoo JSON-2", () => {
  it("usa la clave de la PERSONA y manda la clave de idempotencia", async () => {
    const { f, vistas } = fetchFalso([{ id: 1 }]);
    await new OdooJson2("https://odoo.x/", "dcasa", "clave-de-ana", f).llamar("res.partner", "search_read", { celular: "6555-1234" }, { idem: "L1" });
    expect(vistas[0]!.url).toBe("https://odoo.x/json/2/res.partner/search_read");
    const h = vistas[0]!.init.headers as Record<string, string>;
    expect(h.authorization).toBe("bearer clave-de-ana");
    expect(h["x-brian-idem"]).toBe("L1");
  });
});
