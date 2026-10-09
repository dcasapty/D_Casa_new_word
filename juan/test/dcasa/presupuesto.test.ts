/**
 * Regla 8 del contrato: al llegar al tope de IA del mes, el bot baja al modelo barato; NUNCA se queda sin contestar por dinero.
 * Más la selección rápido/inteligente, la caché de prompt y el respaldo cuando el proveedor falla.
 *
 * Reescritura de test/budget.test.ts, test/pricing.test.ts y test/upgrade/modelSelector.test.ts del CRM de Baby Caleb.
 */
import { describe, expect, it } from "vitest";
import { elegirNivel } from "../../src/motor/modelo";
import { aplicarTope, costoUsd, tarifaDe, usoDelSdk } from "../../src/motor/precios";
import { TEXTO_FALLO_TECNICO } from "../../src/dcasa/textos";
import { crearMundo } from "../helpers/mundo";

const RAPIDO = "claude-haiku-4-5";
const INTELIGENTE = "claude-sonnet-5-5";

describe("cuánto cuesta la IA", () => {
  it("Haiku 4.5 a $1 / $5, Sonnet 5.5 a $2 / $10 por millón de tokens", () => {
    expect(costoUsd(RAPIDO, { entrada: 1_000_000, cacheLectura: 0, cacheEscritura: 0, salida: 1_000_000 })).toBeCloseTo(6, 6);
    expect(costoUsd(INTELIGENTE, { entrada: 1_000_000, cacheLectura: 0, cacheEscritura: 0, salida: 1_000_000 })).toBeCloseTo(12, 6);
  });

  it("la lectura de caché cuesta el 10 % y la escritura el 125 % de la entrada", () => {
    const t = tarifaDe(INTELIGENTE);
    expect(t.cacheLectura).toBeCloseTo(0.2, 6);
    expect(t.cacheEscritura).toBeCloseTo(2.5, 6);
  });

  it("un modelo desconocido se cobra como Sonnet: mejor pasarse que quedarse corto con el tope", () => {
    expect(tarifaDe("claude-algo-nuevo-9")).toEqual(tarifaDe(INTELIGENTE));
  });

  it("separa lo que vino de la caché de lo que no", () => {
    const u = usoDelSdk({ inputTokens: 1000, outputTokens: 50, inputTokenDetails: { noCacheTokens: 200, cacheReadTokens: 700, cacheWriteTokens: 100 } });
    expect(u).toEqual({ entrada: 200, cacheLectura: 700, cacheEscritura: 100, salida: 50 });
    expect(usoDelSdk({ inputTokens: 500, outputTokens: 10, inputTokenDetails: {} })).toEqual({ entrada: 500, cacheLectura: 0, cacheEscritura: 0, salida: 10 });
  });
});

describe("el tope mensual", () => {
  it("al alcanzarlo baja de inteligente a rápido", () => {
    expect(aplicarTope("inteligente", 30, 30)).toEqual({ nivel: "rapido", bajo: true });
    expect(aplicarTope("inteligente", 12, 30)).toEqual({ nivel: "inteligente", bajo: false });
  });
  it("el rápido sigue siendo rápido (nunca se apaga)", () => {
    expect(aplicarTope("rapido", 999, 30)).toEqual({ nivel: "rapido", bajo: false });
  });
  it("sin tope (0) no hay límite", () => {
    expect(aplicarTope("inteligente", 999, 0)).toEqual({ nivel: "inteligente", bajo: false });
  });
});

describe("rápido por defecto, inteligente cuando hace falta", () => {
  const base = { textoDelCliente: "hola, ¿tienen camas?", llamadasRecientes: 0 };
  it("una consulta normal va al rápido", () => expect(elegirNivel(base)).toBe("rapido"));
  it("un cliente molesto va al inteligente", () => {
    for (const t of ["esto es una estafa", "el sofá llegó dañado", "quiero hacer un reclamo", "ya les escribí tres veces y nadie me contesta", "pésimo servicio"]) {
      expect(elegirNivel({ ...base, textoDelCliente: t }), t).toBe("inteligente");
    }
  });
  it("muchas herramientas en los dos turnos anteriores suben al inteligente", () => {
    expect(elegirNivel({ ...base, llamadasRecientes: 6 })).toBe("inteligente");
    expect(elegirNivel({ ...base, llamadasRecientes: 5 })).toBe("rapido");
  });
  it("una búsqueda floja en la base de conocimiento también", () => {
    expect(elegirNivel({ ...base, busquedaFloja: true })).toBe("inteligente");
    expect(elegirNivel({ ...base, busquedaFloja: false })).toBe("rapido");
  });
  it("un mensaje larguísimo o con muchas preguntas también", () => {
    expect(elegirNivel({ ...base, textoDelCliente: "x".repeat(800) })).toBe("inteligente");
    expect(elegirNivel({ ...base, textoDelCliente: "¿precio? ¿medidas? ¿colores? ¿entrega?" })).toBe("inteligente");
  });
});

describe("el motor usa los modelos de la configuración de Odoo", () => {
  it("rápido por defecto: el de modelo_rapido", async () => {
    const m = crearMundo();
    m.guion([{ texto: "Hola." }]);
    await m.conversar("hola");
    expect(m.idsDeModelo).toEqual([RAPIDO]);
  });

  it("un cliente molesto usa modelo_inteligente", async () => {
    const m = crearMundo();
    m.guion([{ texto: "Lamento lo del sofá." }]);
    await m.conversar("el sofá llegó dañado y es una vergüenza");
    expect(m.idsDeModelo[0]).toBe(INTELIGENTE);
  });

  it("los modelos los elige la dueña en Odoo", async () => {
    const m = crearMundo({ config: { modelo_rapido: "claude-haiku-9-9", modelo_inteligente: "claude-sonnet-9-9" } });
    m.guion([{ texto: "Hola." }, { texto: "Lamento." }]);
    await m.conversar("hola");
    await m.conversar("esto es una estafa");
    expect(m.idsDeModelo).toEqual(["claude-haiku-9-9", "claude-sonnet-9-9"]);
  });

  it("Odoo no puede mandar al Worker a otro proveedor: un id que no es de Claude se descarta", async () => {
    const m = crearMundo({ config: { modelo_rapido: "gpt-4o-mini; DROP", modelo_inteligente: "https://malo.example/modelo" } });
    m.guion([{ texto: "Hola." }]);
    await m.conversar("hola");
    expect(m.idsDeModelo).toEqual([RAPIDO]);
  });
});

describe("al llegar al tope mensual, el bot sigue contestando con el modelo barato", () => {
  async function gastar(m: ReturnType<typeof crearMundo>, usd: number) {
    const mes = "2026-10";
    m.gastoGlobal.registrarGasto(mes, INTELIGENTE, { entrada: 0, cacheLectura: 0, cacheEscritura: 0, salida: 0 }, usd);
  }

  it("con $29.99 de $30 todavía puede usar el inteligente", async () => {
    const m = crearMundo();
    await gastar(m, 29.99);
    m.guion([{ texto: "Lamento." }]);
    await m.conversar("esto es una estafa");
    expect(m.idsDeModelo[0]).toBe(INTELIGENTE);
  });

  it("con $30 de $30 baja al rápido y CONTESTA igual", async () => {
    const m = crearMundo();
    await gastar(m, 30);
    m.guion([{ texto: "Lamento lo del sofá; una vendedora te ayuda." }]);
    await m.conversar("el sofá llegó dañado, es una estafa");
    expect(m.idsDeModelo).toEqual([RAPIDO]);
    expect(m.canal.textos.join("\n")).toContain("una vendedora te ayuda");
    expect(m.registros.some((r) => r.mensaje.includes("tope mensual"))).toBe(true);
  });

  it("muy por encima del tope sigue contestando (nunca se calla por dinero)", async () => {
    const m = crearMundo();
    await gastar(m, 500);
    m.guion([{ texto: "Aquí sigo." }]);
    await m.conversar("hola");
    expect(m.canal.textos.join("\n")).toContain("Aquí sigo.");
  });

  it("el tope lo fija la dueña en Odoo", async () => {
    const m = crearMundo({ config: { presupuesto_ia_mensual_usd: 5 } });
    await gastar(m, 5);
    m.guion([{ texto: "Lamento." }]);
    await m.conversar("esto es una estafa");
    expect(m.idsDeModelo).toEqual([RAPIDO]);
  });

  it("lo gastado el mes pasado no cuenta", async () => {
    const m = crearMundo();
    m.gastoGlobal.registrarGasto("2026-09", INTELIGENTE, { entrada: 0, cacheLectura: 0, cacheEscritura: 0, salida: 0 }, 400);
    m.guion([{ texto: "Lamento." }]);
    await m.conversar("esto es una estafa");
    expect(m.idsDeModelo[0]).toBe(INTELIGENTE);
  });

  it("si no se puede leer el gasto, se asume 0 y se contesta", async () => {
    const m = crearMundo();
    m.fallosDeGlobal = true;
    m.guion([{ texto: "Hola." }]);
    await m.conversar("hola");
    expect(m.canal.textos.join("\n")).toContain("Hola.");
  });
});

describe("el gasto se anota con el costo real de cada turno", () => {
  it("tokens × tarifa del modelo que contestó", async () => {
    const m = crearMundo();
    m.guion([{ texto: "Hola.", entrada: 1000, salida: 100 }]);
    await m.conversar("hola");
    // 1000 × $1/M + 100 × $5/M = $0.0015
    expect(m.gastoDelMes()).toBeCloseTo(0.0015, 6);
  });

  it("suma los pasos de herramientas y el reintento de la guardia", async () => {
    const m = crearMundo();
    m.guion([
      { llamadas: [{ nombre: "buscar_productos", args: { consulta: "cama" } }], entrada: 1000, salida: 50 },
      { texto: "Solo quedan 3 unidades.", entrada: 1200, salida: 50 },
      { texto: "Está disponible.", entrada: 1200, salida: 20 },
    ]);
    await m.conversar("¿hay cama?");
    // 3.400 de entrada y 120 de salida con Haiku
    expect(m.gastoDelMes()).toBeCloseTo((3400 * 1 + 120 * 5) / 1e6, 6);
  });

  it("separa lo que vino de la caché de prompt (más barato)", async () => {
    const m = crearMundo();
    m.guion([{ texto: "Hola.", entrada: 100, salida: 10, cacheLectura: 2000 }]);
    await m.conversar("hola");
    expect(m.gastoDelMes()).toBeCloseTo((100 * 1 + 2000 * 0.1 + 10 * 5) / 1e6, 8);
  });

  it("el seguimiento también cuenta", async () => {
    const m = crearMundo();
    m.guion([{ texto: "Hola.", entrada: 10, salida: 5 }, { texto: "¿Sigues buscando la cama? Aquí estoy.", entrada: 500, salida: 30 }]);
    await m.conversar("quiero una cama");
    const antes = m.gastoDelMes();
    await m.pasar(5 * 3600_000);
    await m.motor.seguimiento({ conversacion_id: 12, numero: 1, contexto: { interes: "cama queen", ultimo_mensaje_ts: new Date(m.ahora() - 5 * 3600_000).toISOString() } });
    expect(m.gastoDelMes()).toBeGreaterThan(antes);
  });
});

describe("la caché de prompt", () => {
  it("el bloque estable lleva la marca de caché y el dinámico no", async () => {
    const m = crearMundo();
    const g = m.guion([{ texto: "Hola." }]);
    await m.conversar("hola");
    const sistema = (g.doGenerateCalls[0].prompt as { role: string; providerOptions?: Record<string, unknown> }[]).filter((p) => p.role === "system");
    expect(sistema).toHaveLength(2);
    expect(sistema[0].providerOptions).toEqual({ anthropic: { cacheControl: { type: "ephemeral" } } });
    expect(sistema[1].providerOptions).toBeUndefined();
  });

  it("la fecha y hora (que cambian cada turno) van en el bloque que NO se cachea", async () => {
    const m = crearMundo();
    const g = m.guion([{ texto: "Hola." }]);
    await m.conversar("hola");
    const sistema = (g.doGenerateCalls[0].prompt as { role: string; content: string }[]).filter((p) => p.role === "system");
    expect(sistema[0].content).not.toMatch(/2026/);
    expect(sistema[1].content).toMatch(/2026/);
  });
});

describe("si el proveedor de IA falla, nunca se deja al cliente sin respuesta", () => {
  it("el inteligente cae al rápido", async () => {
    const m = crearMundo();
    m.guion([{ error: new Error("529 overloaded") }]);
    // Primer modelo falla; el guion sigue con su último paso (el error) → luego el texto de respaldo.
    m.guion([{ error: new Error("529 overloaded") }, { texto: "Lamento el problema; una vendedora te ayuda." }]);
    await m.conversar("esto es una estafa");
    expect(m.idsDeModelo.slice(0, 2)).toEqual([INTELIGENTE, RAPIDO]);
    expect(m.canal.textos.join("\n")).toContain("una vendedora te ayuda");
  });

  it("si el rápido falla una vez, reintenta tras una pausa", async () => {
    const m = crearMundo();
    m.guion([{ error: new Error("rate limit") }, { texto: "Ya estoy aquí." }]);
    await m.conversar("hola");
    expect(m.idsDeModelo).toEqual([RAPIDO, RAPIDO]);
    expect(m.canal.textos.join("\n")).toContain("Ya estoy aquí.");
  });

  it("si todo falla, reintenta en un minuto y en cinco; el cliente no recibe respuestas repetidas", async () => {
    const m = crearMundo();
    m.guion([{ error: new Error("caído") }]);
    await m.escribir("hola");
    await m.pasar(16_000);
    expect(m.canal.salidas.length).toBe(0);
    await m.pasar(60_000);
    expect(m.canal.salidas.length).toBe(0);
    // Vuelve el servicio al tercer intento.
    m.guion([{ texto: "Perdona la demora." }]);
    await m.pasar(5 * 60_000);
    expect(m.canal.textos.filter((t) => t.includes("Perdona la demora."))).toHaveLength(1);
  });

  it("si sigue caído, el cliente recibe una disculpa honesta y se avisa a una vendedora", async () => {
    const m = crearMundo();
    m.guion([{ error: new Error("caído") }]);
    await m.escribir("hola");
    await m.pasar(16_000 + 60_000 + 5 * 60_000 + 60_000);
    expect(m.canal.textos).toContain(TEXTO_FALLO_TECNICO);
    // El aviso queda en la cola de Odoo y se entrega.
    await m.pasar(60_000);
    expect(m.odoo.de("pasar_a_vendedora").length).toBe(1);
    expect(String(m.odoo.de("pasar_a_vendedora")[0].args.motivo)).toMatch(/Falla técnica/);
  });
});

describe("sin ninguna clave de IA (primer despliegue, antes de pegar los secretos)", () => {
  it("no se intenta la IA: el cliente recibe la disculpa y se avisa a una vendedora", async () => {
    const m = crearMundo();
    m.proveedores = [];
    const g = m.guion([{ texto: "no debería llamarse" }]);
    await m.conversar("hola");
    expect(g.doGenerateCalls.length).toBe(0);
    expect(m.canal.textos).toContain(TEXTO_FALLO_TECNICO);
    await m.pasar(60_000);
    expect(m.odoo.de("pasar_a_vendedora").length).toBe(1);
  });
});
