/**
 * La IA se elige en Odoo, sin tocar código: `proveedor_ia` (anthropic | meta | openai), `proveedor_respaldo_ia` opcional,
 * `modelo_rapido`, `modelo_inteligente` y `precios_ia`. Meta (Muse Spark) es un proveedor de primera clase, con sus particularidades:
 * siempre razona (`reasoning_effort` low/medium, nunca «none»), el razonamiento cuenta dentro del tope de salida,
 * `max_completion_tokens` en vez de `max_tokens`, y `tool_choice` solo «auto».
 *
 * Las pruebas de Meta corren contra un servidor FALSO compatible con OpenAI que se porta como Meta (test/helpers/servidorMeta.ts):
 * si el Worker mandara `reasoning_effort: "none"`, un `tool_choice` distinto de «auto» o `max_tokens`, el servidor respondería 400.
 */
import { describe, expect, it } from "vitest";
import { CONFIG_POR_DEFECTO, normalizarConfig, normalizarPrecios } from "../../src/config";
import type { Env } from "../../src/env";
import { informeDeSalud } from "../../src/salud";
import { ajustarCuerpo, entrenaConLosMensajes, fabricaDeProduccion, modelosDelPapel, planDeIntentos, topeDeSalida } from "../../src/motor/proveedores";
import { costoDe } from "../../src/motor/precios";
import { TEXTO_FALLO_TECNICO } from "../../src/dcasa/textos";
import { crearMundo } from "../helpers/mundo";
import { modeloGuionado } from "../helpers/modeloGuionado";
import { crearServidorMeta, TOKENS_DE_RAZONAMIENTO, type RespuestaDeMeta } from "../helpers/servidorMeta";
import { crearAdaptadores } from "../../src/canales";

const CLAVE_META = "LLM|clave-de-prueba-0123456789";
const PRECIO_META = { "muse-spark-1.3": { entrada: 1.25, salida: 4.25, entrada_cache: 0.15 } };
const ENV_META = { META_AI_API_KEY: CLAVE_META } as Env;

/** Un mundo cuyo proveedor principal es Meta, hablando con el servidor falso. */
function mundoMeta(guion: (n: number) => RespuestaDeMeta, config: Record<string, unknown> = {}, extra: { respaldo?: ReturnType<typeof modeloGuionado> } = {}) {
  const servidor = crearServidorMeta({ clave: CLAVE_META, guion: (_p, n) => guion(n) });
  const real = fabricaDeProduccion(ENV_META, { fetch: servidor.fetch });
  const m = crearMundo({
    proveedores: extra.respaldo ? ["meta", "anthropic"] : ["meta"],
    config: { proveedor_ia: "meta", precios_ia: PRECIO_META, ...config },
    fabrica: (sel) => (sel.proveedor === "meta" ? real(sel) : extra.respaldo!),
  });
  return { m, servidor };
}

describe("la configuración de Odoo elige el proveedor", () => {
  it("sin nada: Anthropic, con Claude Haiku 4.5 y Sonnet 5.5, sin respaldo", () => {
    const c = normalizarConfig({});
    expect(c).toMatchObject({ proveedor_ia: "anthropic", proveedor_respaldo_ia: null, modelo_rapido: "claude-haiku-4-5", modelo_inteligente: "claude-sonnet-5-5" });
  });

  it("proveedor_ia: meta → muse-spark-1.3 (el estándar) en los dos niveles", () => {
    const c = normalizarConfig({ proveedor_ia: "meta" });
    expect(c).toMatchObject({ proveedor_ia: "meta", modelo_rapido: "muse-spark-1.3", modelo_inteligente: "muse-spark-1.3" });
  });

  it("jamás elige por su cuenta el nivel «contributor» (entrena con los mensajes): solo si la dueña lo escribe", () => {
    expect(JSON.stringify(normalizarConfig({ proveedor_ia: "meta" }))).not.toMatch(/contributor/);
    const a_proposito = normalizarConfig({ proveedor_ia: "meta", modelo_rapido: "muse-spark-1.3-contributor", modelo_inteligente: "muse-spark-1.3-contributor" });
    expect(a_proposito.modelo_rapido).toBe("muse-spark-1.3-contributor");
    expect(entrenaConLosMensajes(a_proposito.modelo_rapido)).toBe(true);
    expect(entrenaConLosMensajes("muse-spark-1.3")).toBe(false);
  });

  it("un modelo de otro proveedor, o con forma rara, se descarta y se usa el de siempre", () => {
    expect(normalizarConfig({ proveedor_ia: "meta", modelo_rapido: "claude-haiku-4-5" }).modelo_rapido).toBe("muse-spark-1.3");
    expect(normalizarConfig({ proveedor_ia: "anthropic", modelo_rapido: "muse-spark-1.3" }).modelo_rapido).toBe("claude-haiku-4-5");
    expect(normalizarConfig({ proveedor_ia: "meta", modelo_rapido: "muse-spark; DROP TABLE" }).modelo_rapido).toBe("muse-spark-1.3");
    expect(normalizarConfig({ proveedor_ia: "meta", modelo_rapido: "https://malo.example/m" }).modelo_rapido).toBe("muse-spark-1.3");
  });

  it("un proveedor desconocido cae en Anthropic", () => {
    expect(normalizarConfig({ proveedor_ia: "skynet" }).proveedor_ia).toBe("anthropic");
    expect(normalizarConfig({ proveedor_ia: "META" }).proveedor_ia).toBe("meta");
  });

  it("OpenAI no trae modelo por defecto: hay que elegirlo, y sin él ese proveedor no se usa", () => {
    const sin = normalizarConfig({ proveedor_ia: "openai" });
    expect(sin.modelo_rapido).toBe("");
    expect(modelosDelPapel(sin, "principal")).toBeNull();
    expect(planDeIntentos(sin, "rapido", ["openai"])).toEqual([]);
    const con = normalizarConfig({ proveedor_ia: "openai", modelo_rapido: "gpt-4o-mini", modelo_inteligente: "gpt-4o" });
    expect(planDeIntentos(con, "inteligente", ["openai"]).map((x) => x.modelo)).toEqual(["gpt-4o", "gpt-4o-mini"]);
  });

  it("el respaldo es opcional, distinto del principal y con sus propios modelos", () => {
    expect(normalizarConfig({ proveedor_ia: "meta", proveedor_respaldo_ia: "meta" }).proveedor_respaldo_ia).toBeNull();
    const c = normalizarConfig({ proveedor_ia: "meta", proveedor_respaldo_ia: "anthropic", modelo_rapido_respaldo: "claude-haiku-4-5", modelo_inteligente_respaldo: "gpt-4o" });
    expect(c.proveedor_respaldo_ia).toBe("anthropic");
    expect(c.modelo_rapido_respaldo).toBe("claude-haiku-4-5");
    expect(c.modelo_inteligente_respaldo).toBe(""); // «gpt-4o» no es de Anthropic
    expect(modelosDelPapel(c, "respaldo")).toEqual({ proveedor: "anthropic", rapido: "claude-haiku-4-5", inteligente: "claude-sonnet-5-5" });
  });

  it("el plan de intentos: principal (inteligente y luego rápido) y después el respaldo; solo proveedores con clave", () => {
    const c = normalizarConfig({ proveedor_ia: "anthropic", proveedor_respaldo_ia: "meta" });
    expect(planDeIntentos(c, "inteligente", ["anthropic", "meta"]).map((x) => `${x.proveedor}:${x.nivel}`)).toEqual([
      "anthropic:inteligente",
      "anthropic:rapido",
      "meta:inteligente",
      "meta:rapido",
    ]);
    expect(planDeIntentos(c, "rapido", ["anthropic", "meta"]).map((x) => `${x.proveedor}:${x.nivel}`)).toEqual(["anthropic:rapido", "meta:rapido"]);
    expect(planDeIntentos(c, "rapido", ["meta"]).map((x) => x.proveedor)).toEqual(["meta"]);
    expect(planDeIntentos(c, "rapido", [])).toEqual([]);
  });

  it("la tabla de precios acepta los nombres en español y en inglés, y descarta lo raro", () => {
    expect(normalizarPrecios({ "muse-spark-1.3": { entrada: 1.25, salida: 4.25, entrada_cache: 0.15 }, "otro-modelo": { input: "2", output: 8, cache_read: 0.2 } })).toEqual({
      "muse-spark-1.3": { entrada: 1.25, salida: 4.25, entrada_cache: 0.15 },
      "otro-modelo": { entrada: 2, salida: 8, entrada_cache: 0.2 },
    });
    expect(normalizarPrecios({ malo: { entrada: -1, salida: 5 }, "sin-salida": { entrada: 1 }, "x y": { entrada: 1, salida: 1 }, "ok-modelo": "texto" })).toEqual({});
    expect(normalizarPrecios("no es un objeto")).toEqual({});
  });
});

describe("la petición a la API de Meta cumple sus particularidades", () => {
  it("max_tokens → max_completion_tokens; reasoning_effort fijo por nivel (nunca «none»); tool_choice solo «auto»", () => {
    const base = { model: "muse-spark-1.3", messages: [], max_tokens: 700, tools: [{ type: "function" }] };
    expect(ajustarCuerpo("meta", "rapido", base)).toMatchObject({ max_completion_tokens: 700, reasoning_effort: "low", tool_choice: "auto" });
    expect(ajustarCuerpo("meta", "rapido", base)).not.toHaveProperty("max_tokens");
    expect(ajustarCuerpo("meta", "inteligente", base).reasoning_effort).toBe("medium");
    // Aunque algo más arriba pidiera otra cosa, sale lo permitido.
    expect(ajustarCuerpo("meta", "rapido", { ...base, reasoning_effort: "none", tool_choice: "required" })).toMatchObject({ reasoning_effort: "low", tool_choice: "auto" });
    expect(ajustarCuerpo("meta", "rapido", { ...base, tool_choice: { type: "function", function: { name: "x" } } }).tool_choice).toBe("auto");
    // Sin herramientas no hay tool_choice.
    expect(ajustarCuerpo("meta", "rapido", { model: "m", messages: [], max_tokens: 5, tool_choice: "auto" })).not.toHaveProperty("tool_choice");
  });

  it("con OpenAI solo cambia el nombre del límite: no se inventa reasoning_effort", () => {
    const b = ajustarCuerpo("openai", "rapido", { model: "gpt-x", messages: [], max_tokens: 900, tools: [{}] });
    expect(b).toMatchObject({ max_completion_tokens: 900 });
    expect(b).not.toHaveProperty("max_tokens");
    expect(b).not.toHaveProperty("reasoning_effort");
  });

  it("el tope de salida de Meta es mucho más alto que el de Claude: el razonamiento sale de ahí", () => {
    expect(topeDeSalida("anthropic", "rapido")).toBe(700);
    expect(topeDeSalida("meta", "rapido")).toBeGreaterThanOrEqual(TOKENS_DE_RAZONAMIENTO.low * 10);
    expect(topeDeSalida("meta", "inteligente")).toBeGreaterThanOrEqual(TOKENS_DE_RAZONAMIENTO.medium * 5);
    expect(topeDeSalida("meta", "inteligente")).toBeGreaterThan(topeDeSalida("meta", "rapido"));
  });

  it("el servidor falso SÍ se queda sin respuesta si el tope fuera el de Claude (por eso se sube)", async () => {
    const s = crearServidorMeta({ clave: CLAVE_META, guion: () => ({ texto: "Hola." }) });
    const pedir = (cuerpo: object) =>
      s.fetch("https://api.meta.ai/v1/chat/completions", { method: "POST", headers: { authorization: `Bearer ${CLAVE_META}` }, body: JSON.stringify({ model: "muse-spark-1.3", messages: [], ...cuerpo }) });
    const corto = (await (await pedir({ reasoning_effort: "medium", max_completion_tokens: 700 })).json()) as any;
    expect(corto.choices[0].finish_reason).toBe("length");
    expect(corto.choices[0].message.content).toBe("");
    const largo = (await (await pedir({ reasoning_effort: "low", max_completion_tokens: topeDeSalida("meta", "rapido") })).json()) as any;
    expect(largo.choices[0].message.content).toBe("Hola.");
    // …y rechaza lo que Meta rechaza.
    expect((await pedir({ reasoning_effort: "none", max_completion_tokens: 4000 })).status).toBe(400);
    expect((await pedir({ reasoning_effort: "low", max_completion_tokens: 4000, tool_choice: "required" })).status).toBe(400);
    expect((await pedir({ reasoning_effort: "low", max_tokens: 4000 })).status).toBe(400);
  });
});

describe("el motor contesta con Meta (servidor falso)", () => {
  const respuestaNormal = (n: number): RespuestaDeMeta => (n === 0 ? { texto: "Claro, dime qué buscas." } : { texto: "Claro." });

  it("manda la petición como Meta la espera: dirección, clave, modelo, límite, razonamiento y un solo mensaje de sistema", async () => {
    const { m, servidor } = mundoMeta(respuestaNormal);
    await m.conversar("hola");
    expect(servidor.rechazos).toEqual([]);
    const p = servidor.peticiones[0];
    expect(p.url).toBe("https://api.meta.ai/v1/chat/completions");
    expect(p.cabeceras.authorization).toBe(`Bearer ${CLAVE_META}`);
    expect(p.cuerpo.model).toBe("muse-spark-1.3");
    expect(p.cuerpo.max_completion_tokens).toBe(4000);
    expect(p.cuerpo).not.toHaveProperty("max_tokens");
    expect(p.cuerpo.reasoning_effort).toBe("low");
    expect(p.cuerpo.tool_choice).toBe("auto");
    const sistema = (p.cuerpo.messages as { role: string; content: string }[]).filter((x) => x.role === "system");
    expect(sistema).toHaveLength(1);
    expect(sistema[0].content).toContain("<fuentes_de_verdad>");
    expect(sistema[0].content).toContain("<contexto_de_este_chat>");
    expect(m.canal.textos.join("\n")).toContain("Claro, dime qué buscas.");
  });

  it("el prompt estable va ANTES de lo que cambia en cada turno: así la caché automática por prefijo funciona", async () => {
    const { m, servidor } = mundoMeta(respuestaNormal);
    await m.conversar("hola");
    const texto = (servidor.peticiones[0].cuerpo.messages as { content: string }[])[0].content;
    expect(texto.indexOf("<ultimo_recordatorio>")).toBeLessThan(texto.indexOf("<contexto_de_este_chat>"));
  });

  it("un cliente molesto usa el nivel inteligente: razonamiento medium y más tope de salida", async () => {
    const { m, servidor } = mundoMeta(respuestaNormal);
    await m.conversar("esto es una estafa, el sofá llegó dañado");
    const cuerpo = servidor.peticiones[0].cuerpo;
    expect(cuerpo.reasoning_effort).toBe("medium");
    expect(cuerpo.max_completion_tokens).toBe(8000);
    expect(servidor.rechazos).toEqual([]);
  });

  it("las herramientas de Odoo viajan en formato OpenAI y Meta puede pedir varias a la vez: se ejecutan juntas", async () => {
    const { m, servidor } = mundoMeta((n) =>
      n === 0
        ? { llamadas: [{ nombre: "buscar_productos", args: { consulta: "" } }, { nombre: "reglas_socios", args: {} }, { nombre: "horario_y_tienda", args: {} }] }
        : { texto: "La Cama Queen Milán está en $499.00 + ITBMS." },
    );
    m.odoo.retardoMs = 40;
    await m.conversar("camas, Socios y horario");
    expect(servidor.rechazos).toEqual([]);
    const tools = servidor.peticiones[0].cuerpo.tools as { type: string; function: { name: string; parameters: { type: string } } }[];
    expect(tools.every((t) => t.type === "function" && t.function.parameters.type === "object")).toBe(true);
    expect(tools.map((t) => t.function.name)).toContain("buscar_productos");
    expect(tools.map((t) => t.function.name)).toContain("enviar_foto_producto");
    expect(m.odoo.maxEnCurso).toBeGreaterThanOrEqual(3);
    // El resultado de las herramientas vuelve como mensajes «tool» y la segunda petición sigue cumpliendo las reglas de Meta.
    const segunda = servidor.peticiones[1].cuerpo.messages as { role: string }[];
    expect(segunda.filter((x) => x.role === "tool")).toHaveLength(3);
    expect(servidor.peticiones[1].cuerpo.tool_choice).toBe("auto");
    expect(m.canal.textos.join("\n")).toContain("$499.00 + ITBMS");
  });

  it("la guardia de salida es la misma con Meta: un precio inventado no sale", async () => {
    const { m } = mundoMeta((n) => (n === 0 ? { texto: "Esa cama te sale en $350." } : { texto: "Eso te lo confirma una vendedora." }));
    await m.conversar("¿cuánto cuesta la cama?");
    expect(m.canal.textos.join("\n")).not.toContain("350");
  });

  it("si el razonamiento se come el tope y la respuesta llega vacía, se le pide responder y nunca se queda mudo", async () => {
    // Con un tope diminuto el servidor devuelve «length» con el contenido vacío; el motor lo trata como «sin texto».
    const { m, servidor } = mundoMeta(() => ({ texto: "no llega" }));
    const original = servidor.fetch;
    let n = 0;
    (m.deps as any).modelo = (sel: any) => {
      const real = fabricaDeProduccion(ENV_META, {
        fetch: async (u, i) => {
          const cuerpo = JSON.parse(String(i?.body));
          // Simula el servidor con un tope demasiado bajo solo en la primera llamada.
          if (n++ === 0) cuerpo.max_completion_tokens = 100;
          return original(u, { ...i, body: JSON.stringify(cuerpo) });
        },
      });
      return real(sel);
    };
    await m.conversar("hola");
    expect(m.canal.textos.length).toBeGreaterThan(0);
  });

  it("el uso incluye el razonamiento (se cobra como salida) y la caché automática", async () => {
    const { m } = mundoMeta(() => ({ texto: "Hola.", entrada: 1000, cacheados: 600, salida: 40 }));
    await m.conversar("hola");
    // 400 de entrada sin caché + 600 de caché + (300 de razonamiento «low» + 40 visibles) de salida
    const esperado = costoDe("muse-spark-1.3", { entrada: 400, cacheLectura: 600, cacheEscritura: 0, salida: 340 }, PRECIO_META).usd;
    expect(m.gastoDelMes()).toBeCloseTo(esperado, 9);
    expect(m.gastoDelMes()).toBeCloseTo((400 * 1.25 + 600 * 0.15 + 340 * 4.25) / 1e6, 9);
  });
});

describe("el precio de Meta no está verificado: se carga en Odoo y NUNCA se asume gratis", () => {
  it("con el precio cargado, el tope mensual lo usa", async () => {
    const { m } = mundoMeta(() => ({ texto: "Hola." }), { precios_ia: { "muse-spark-1.3": { entrada: 1000, salida: 1000 } }, presupuesto_ia_mensual_usd: 0.5 });
    await m.conversar("hola");
    expect(m.gastoDelMes()).toBeGreaterThan(0.5);
    // Ya pasó el tope: un cliente molesto igual se atiende, pero con el nivel barato (razonamiento «low»).
    m.selecciones.length = 0;
    await m.conversar("esto es una estafa");
    expect(m.selecciones[0].nivel).toBe("rapido");
    expect(m.canal.textos.at(-1)).toBe("Hola.");
  });

  it("sin precio cargado: se estima con una tarifa de reserva (no cero), se marca como estimado y se registra el aviso", async () => {
    const { m } = mundoMeta(() => ({ texto: "Hola.", entrada: 1000, salida: 40 }), { precios_ia: {} });
    await m.conversar("hola");
    // 1000 de entrada y 340 de salida con la tarifa de reserva ($2 / $10 por millón)
    expect(m.gastoDelMes()).toBeCloseTo((1000 * 2 + 340 * 10) / 1e6, 9);
    expect(m.gastoDelMes()).toBeGreaterThan(0);
    const mes = m.gastoGlobal.gastoMes("2026-10");
    expect(mes.modelosSinPrecio).toEqual(["muse-spark-1.3"]);
    expect(m.registros.some((r) => r.mensaje.includes("no tiene precio cargado"))).toBe(true);
  });

  it("y el tope sigue funcionando con la tarifa de reserva", async () => {
    const { m } = mundoMeta(() => ({ texto: "Hola.", entrada: 1_000_000, salida: 40 }), { precios_ia: {}, presupuesto_ia_mensual_usd: 1 });
    await m.conversar("hola");
    m.selecciones.length = 0;
    await m.conversar("esto es una estafa");
    expect(m.selecciones[0].nivel).toBe("rapido");
  });

  it("/salud avisa qué modelo no tiene precio, antes y después de gastar", async () => {
    const { m } = mundoMeta(() => ({ texto: "Hola." }), { precios_ia: {} });
    await m.conversar("hola");
    const informe = await informeDeSalud({
      env: { META_AI_API_KEY: CLAVE_META, JUAN_ODOO_TOKEN: "x", JUAN_WORKER_TOKEN: "y" } as Env,
      adaptadores: crearAdaptadores(),
      config: () => m.config(),
      gastoMes: async (mes) => m.gastoGlobal.gastoMes(mes).usd,
      modelosSinPrecio: async (mes) => m.gastoGlobal.gastoMes(mes).modelosSinPrecio,
      ahora: m.ahora,
      consultarConexiones: false,
    });
    expect(informe.ia.modelos_sin_precio).toEqual(["muse-spark-1.3"]);
    expect(informe.problemas.join("\n")).toMatch(/muse-spark-1\.3 no tiene precio cargado/);
  });
});

describe("si el proveedor elegido falla o no tiene clave, contesta el respaldo", () => {
  const claude = (texto = "Te respondo con el respaldo.") => modeloGuionado([{ texto }]);

  it("Meta responde 500 → contesta Claude y queda anotado para /salud", async () => {
    const respaldo = claude();
    const { m, servidor } = mundoMeta(() => ({ estado: 500 }), { proveedor_respaldo_ia: "anthropic" }, { respaldo });
    await m.conversar("hola");
    expect(servidor.peticiones.length).toBeGreaterThan(0);
    expect(m.canal.textos.join("\n")).toContain("Te respondo con el respaldo.");
    expect(m.selecciones.map((s) => s.proveedor)).toContain("anthropic");
    const fallo = m.gastoGlobal.leerSalud<{ proveedor: string; modelo: string; motivo: string }>("ia_fallo")!.valor;
    expect(fallo).toMatchObject({ proveedor: "meta", modelo: "muse-spark-1.3" });
    expect(m.gastoGlobal.leerSalud<{ proveedor: string }>("ia_respaldo")!.valor.proveedor).toBe("anthropic");
    expect(m.registros.some((r) => r.mensaje.includes("contestó el respaldo"))).toBe(true);
  });

  it("Meta responde 402 (sin saldo) o 429 → también el respaldo", async () => {
    for (const estado of [402, 429, 401]) {
      const { m } = mundoMeta(() => ({ estado }), { proveedor_respaldo_ia: "anthropic" }, { respaldo: claude() });
      await m.conversar("hola");
      expect(m.canal.textos.join("\n"), String(estado)).toContain("Te respondo con el respaldo.");
    }
  });

  it("el gasto se anota con el precio del modelo que de verdad contestó", async () => {
    const respaldo = modeloGuionado([{ texto: "Respaldo.", entrada: 1000, salida: 100 }], "claude-haiku-4-5");
    const { m } = mundoMeta(() => ({ estado: 500 }), { proveedor_respaldo_ia: "anthropic" }, { respaldo });
    await m.conversar("hola");
    expect(m.gastoDelMes()).toBeCloseTo((1000 * 1 + 100 * 5) / 1e6, 9);
  });

  it("Meta sin clave cargada → ni se intenta: contesta el respaldo", async () => {
    const respaldo = claude();
    const { m, servidor } = mundoMeta(() => ({ texto: "no debería llamarse" }), { proveedor_respaldo_ia: "anthropic" }, { respaldo });
    m.proveedores = ["anthropic"];
    await m.conversar("hola");
    expect(servidor.peticiones).toHaveLength(0);
    expect(m.canal.textos.join("\n")).toContain("Te respondo con el respaldo.");
  });

  it("sin respaldo, un fallo de Meta reintenta con calma y luego pasa a una vendedora (nunca queda mudo)", async () => {
    const { m } = mundoMeta(() => ({ estado: 500 }));
    await m.escribir("hola");
    await m.pasar(16_000 + 60_000 + 5 * 60_000 + 60_000);
    expect(m.canal.textos).toContain(TEXTO_FALLO_TECNICO);
    await m.pasar(60_000);
    expect(m.odoo.de("pasar_a_vendedora")).toHaveLength(1);
  });

  it("ningún proveedor con clave: «una vendedora te atiende», aviso a la vendedora y /salud lo dice", async () => {
    const { m } = mundoMeta(() => ({ texto: "no debería llamarse" }));
    m.proveedores = [];
    await m.conversar("hola");
    expect(m.canal.textos).toContain(TEXTO_FALLO_TECNICO);
    expect(TEXTO_FALLO_TECNICO).toMatch(/vendedora te atiende/);
    await m.pasar(60_000);
    expect(m.odoo.de("pasar_a_vendedora")).toHaveLength(1);
    const informe = await informeDeSalud({ env: { JUAN_ODOO_TOKEN: "x", JUAN_WORKER_TOKEN: "y" } as Env, adaptadores: crearAdaptadores(), config: () => m.config(), gastoMes: async () => 0, ahora: m.ahora, consultarConexiones: false });
    expect(informe.ok).toBe(false);
    expect(informe.secretos_faltantes).toEqual(["META_AI_API_KEY"]);
    expect(informe.problemas.join("\n")).toMatch(/ningún proveedor de IA tiene clave/);
    expect(informe.mensaje).toMatch(/Falta META_AI_API_KEY/);
    expect(informe.mensaje).toMatch(/una vendedora/);
  });

  it("el seguimiento también usa el respaldo", async () => {
    const respaldo = claude("Hola Karen, ¿pudiste ver la cama? Escríbeme *persona* si prefieres.");
    const { m } = mundoMeta((n) => (n === 0 ? { texto: "Tenemos camas queen." } : { estado: 500 }), { proveedor_respaldo_ia: "anthropic" }, { respaldo });
    await m.conversar("quiero una cama");
    const ultimo = m.ahora();
    await m.pasar(5 * 3600_000);
    const r = await m.motor.seguimiento({ conversacion_id: 12, numero: 1, contexto: { interes: "cama", ultimo_mensaje_ts: new Date(ultimo).toISOString() } });
    expect(r).toEqual({ ok: true, resultado: "enviado" });
    expect(m.canal.textos.at(-1)).toContain("¿pudiste ver la cama?");
  });

  it("la clave nunca aparece en lo que queda anotado para /salud ni en los registros", async () => {
    // El servidor repite la clave en su mensaje de error (algunos proveedores lo hacen).
    const servidor = crearServidorMeta({ clave: "otra-clave", guion: () => ({ texto: "x" }) });
    const real = fabricaDeProduccion({ META_AI_API_KEY: CLAVE_META } as Env, { fetch: servidor.fetch });
    const m = crearMundo({ proveedores: ["meta"], config: { proveedor_ia: "meta" }, fabrica: real });
    await m.conversar("hola");
    const guardado = JSON.stringify(m.gastoGlobal.leerSalud("ia_fallo")) + JSON.stringify(m.registros);
    expect(guardado).not.toContain("0123456789");
    expect(guardado).toContain("Invalid API key");
  });
});

describe("salud de la IA", () => {
  const baseEnv = { JUAN_ODOO_TOKEN: "x", JUAN_WORKER_TOKEN: "y" } as Env;
  const dep = (cfg: Record<string, unknown>, env: Env) => ({
    env,
    adaptadores: crearAdaptadores(),
    config: async () => normalizarConfig(cfg),
    gastoMes: async () => 0,
    ahora: () => Date.parse("2026-10-09T15:00:00Z"),
    consultarConexiones: false,
  });

  it("pide la clave del proveedor elegido (no la de Anthropic si se eligió Meta)", async () => {
    const i = await informeDeSalud(dep({ proveedor_ia: "meta" }, baseEnv));
    expect(i.secretos_faltantes).toEqual(["META_AI_API_KEY"]);
    expect(i.ia).toMatchObject({ proveedor: "meta", con_clave: [], claves_faltantes: ["META_AI_API_KEY"] });
    const j = await informeDeSalud(dep({ proveedor_ia: "anthropic" }, baseEnv));
    expect(j.secretos_faltantes).toEqual(["ANTHROPIC_API_KEY"]);
  });

  it("con el respaldo cargado, avisa que falta la del principal pero que sigue contestando", async () => {
    const i = await informeDeSalud(dep({ proveedor_ia: "meta", proveedor_respaldo_ia: "anthropic", precios_ia: PRECIO_META }, { ...baseEnv, ANTHROPIC_API_KEY: "k" } as Env));
    expect(i.problemas.join("\n")).toMatch(/falta META_AI_API_KEY.*contesta el respaldo/);
    expect(i.mensaje).not.toMatch(/todavía no puede contestar/);
  });

  it("todo cargado: ok", async () => {
    const i = await informeDeSalud(dep({ proveedor_ia: "meta", precios_ia: PRECIO_META }, { ...baseEnv, META_AI_API_KEY: "k" } as Env));
    expect(i.problemas.filter((p) => !p.includes("canal"))).toEqual([]);
    expect(i.ia.con_clave).toEqual(["meta"]);
  });

  it("el modelo «contributor» aparece como aviso (entrena con los mensajes de los clientes)", async () => {
    const i = await informeDeSalud(
      dep({ proveedor_ia: "meta", modelo_rapido: "muse-spark-1.3-contributor", modelo_inteligente: "muse-spark-1.3-contributor", precios_ia: { "muse-spark-1.3-contributor": { entrada: 0.1, salida: 0.2 } } }, { ...baseEnv, META_AI_API_KEY: "k" } as Env),
    );
    expect(i.avisos.join("\n")).toMatch(/muse-spark-1\.3-contributor puede usar los mensajes de los clientes para entrenar/);
    expect(i.avisos.join("\n")).toMatch(/Ley 81/);
  });

  it("un modelo sin precio cargado es un problema visible, no un cero silencioso", async () => {
    const i = await informeDeSalud(dep({ proveedor_ia: "meta" }, { ...baseEnv, META_AI_API_KEY: "k" } as Env));
    expect(i.problemas.join("\n")).toMatch(/muse-spark-1\.3 no tiene precio cargado/);
    const claude = await informeDeSalud(dep({}, { ...baseEnv, ANTHROPIC_API_KEY: "k" } as Env));
    expect(claude.problemas.join("\n")).not.toMatch(/precio cargado/);
  });

  it("la configuración por defecto sigue siendo la de siempre", () => {
    expect(CONFIG_POR_DEFECTO.proveedor_ia).toBe("anthropic");
    expect(CONFIG_POR_DEFECTO.precios_ia).toEqual({});
  });
});
