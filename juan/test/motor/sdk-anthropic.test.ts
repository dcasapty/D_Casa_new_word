/**
 * El camino REAL de Claude: `fabricaDeProduccion` → `@ai-sdk/anthropic` → `correrTurno` (`generateText` de `ai`), contra un
 * `fetch` falso que contesta como la API de Mensajes de Anthropic. Las demás pruebas usan un modelo de mentira (modeloGuionado) y no
 * pasan por el proveedor: esta es la que avisa si una versión nueva del SDK (Dependabot, grupo «ia») cambia lo que de verdad se manda.
 *
 * Lo que se comprueba:
 *   · el prompt estable va marcado para la caché (`cache_control: ephemeral`) y el dinámico no; sin `cachear`, ninguno;
 *   · el tope de salida de Claude (700) y la clave en `x-api-key`;
 *   · el bucle de herramientas: el modelo pide una, se ejecuta y su resultado vuelve como `tool_result`;
 *   · el uso suma los dos pasos y separa lectura y escritura de caché.
 */
import { describe, expect, it } from "vitest";
import { jsonSchema, tool } from "ai";
import type { Env } from "../../src/env";
import { correrTurno } from "../../src/motor/modelo";
import { fabricaDeProduccion } from "../../src/motor/proveedores";

const CLAVE = "sk-ant-clave-de-prueba";

interface Peticion {
  url: string;
  cabeceras: Headers;
  cuerpo: Record<string, any>;
}

/** Un servidor falso de Anthropic: devuelve las respuestas en orden y guarda lo que recibió. */
function servidorAnthropic(respuestas: Record<string, unknown>[]) {
  const peticiones: Peticion[] = [];
  const fetchFalso = (async (entrada: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof entrada === "string" ? entrada : entrada instanceof URL ? entrada.href : entrada.url;
    peticiones.push({ url, cabeceras: new Headers(init?.headers), cuerpo: JSON.parse(String(init?.body ?? "{}")) });
    const r = respuestas[Math.min(peticiones.length - 1, respuestas.length - 1)];
    return new Response(JSON.stringify(r), { status: 200, headers: { "content-type": "application/json" } });
  }) as typeof fetch;
  return { fetch: fetchFalso, peticiones };
}

const mensaje = (content: unknown[], stop_reason: string, usage: Record<string, number>) => ({
  id: "msg_prueba",
  type: "message",
  role: "assistant",
  model: "claude-haiku-4-5",
  content,
  stop_reason,
  stop_sequence: null,
  usage,
});

function modeloClaude(fetchFalso: typeof fetch) {
  return fabricaDeProduccion({ ANTHROPIC_API_KEY: CLAVE } as Env, { fetch: fetchFalso })({ proveedor: "anthropic", modelo: "claude-haiku-4-5", nivel: "rapido" });
}

describe("Claude por el SDK real (fetch falso)", () => {
  it("marca el prompt estable para la caché, ejecuta la herramienta pedida y suma el uso de los dos pasos", async () => {
    const servidor = servidorAnthropic([
      mensaje([{ type: "tool_use", id: "toolu_1", name: "horario_y_tienda", input: { dia: "sabado" } }], "tool_use", {
        input_tokens: 40,
        output_tokens: 12,
        cache_creation_input_tokens: 900,
        cache_read_input_tokens: 0,
      }),
      mensaje([{ type: "text", text: "Abrimos el sábado de 9 a 6." }], "end_turn", {
        input_tokens: 60,
        output_tokens: 15,
        cache_creation_input_tokens: 0,
        cache_read_input_tokens: 900,
      }),
    ]);
    const recibidos: unknown[] = [];
    const salida = await correrTurno({
      modelo: modeloClaude(servidor.fetch),
      proveedor: "anthropic",
      nivel: "rapido",
      sistemaEstable: "Eres Juan, de D'CASA. (estable)",
      sistemaDinamico: "Hoy es viernes. (dinámico)",
      mensajes: [{ role: "user", content: "¿Abren el sábado?" }],
      herramientas: {
        horario_y_tienda: tool({
          description: "Horario de la tienda",
          inputSchema: jsonSchema({ type: "object", properties: { dia: { type: "string" } } } as never),
          execute: async (args: unknown) => {
            recibidos.push(args);
            return { ok: true, resultado: { sabado: "9:00 a 18:00" } };
          },
        }),
      },
    });

    expect(servidor.peticiones).toHaveLength(2);
    const [primera, segunda] = servidor.peticiones;
    expect(primera.url).toBe("https://api.anthropic.com/v1/messages");
    expect(primera.cabeceras.get("x-api-key")).toBe(CLAVE);
    expect(primera.cuerpo.model).toBe("claude-haiku-4-5");
    expect(primera.cuerpo.max_tokens).toBe(700);
    expect(primera.cuerpo.system).toEqual([
      { type: "text", text: "Eres Juan, de D'CASA. (estable)", cache_control: { type: "ephemeral" } },
      { type: "text", text: "Hoy es viernes. (dinámico)" },
    ]);
    // Los mensajes de sistema van en `system`, nunca dentro de `messages` (el SDK 7 los rechaza ahí).
    expect(primera.cuerpo.messages.map((m: { role: string }) => m.role)).toEqual(["user"]);
    expect(primera.cuerpo.tools.map((t: { name: string }) => t.name)).toEqual(["horario_y_tienda"]);

    expect(recibidos).toEqual([{ dia: "sabado" }]);
    const resultado = segunda.cuerpo.messages.at(-1).content.find((c: { type: string }) => c.type === "tool_result");
    expect(resultado.tool_use_id).toBe("toolu_1");
    expect(JSON.stringify(resultado.content)).toContain("9:00 a 18:00");

    expect(salida.texto).toBe("Abrimos el sábado de 9 a 6.");
    expect(salida.pasos).toBe(2);
    expect(salida.sinTexto).toBe(false);
    expect(salida.consultas).toEqual([{ herramienta: "horario_y_tienda", resultado: { ok: true, resultado: { sabado: "9:00 a 18:00" } } }]);
    expect(salida.uso).toEqual({ entrada: 100, cacheLectura: 900, cacheEscritura: 900, salida: 27 });
  });

  it("con cachear: false no marca nada para la caché", async () => {
    const servidor = servidorAnthropic([mensaje([{ type: "text", text: "Listo." }], "end_turn", { input_tokens: 10, output_tokens: 2 })]);
    const salida = await correrTurno({
      modelo: modeloClaude(servidor.fetch),
      proveedor: "anthropic",
      nivel: "rapido",
      sistemaEstable: "estable",
      sistemaDinamico: "dinámico",
      mensajes: [{ role: "user", content: "hola" }],
      herramientas: {},
      cachear: false,
    });
    expect(salida.texto).toBe("Listo.");
    expect(JSON.stringify(servidor.peticiones[0].cuerpo)).not.toContain("cache_control");
    expect(servidor.peticiones[0].cuerpo.system).toEqual([
      { type: "text", text: "estable" },
      { type: "text", text: "dinámico" },
    ]);
  });
});
