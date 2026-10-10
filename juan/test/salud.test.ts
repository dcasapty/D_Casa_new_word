/**
 * La salud del Worker: qué secretos faltan (solo NOMBRES), el estado de cada canal, el tope de IA y los avisos del cron
 * (una vez por problema, y un «resuelto» cuando se arregla).
 */
import { describe, expect, it } from "vitest";
import { normalizarConfig } from "../src/config";
import { crearAdaptadores } from "../src/canales";
import type { Env } from "../src/env";
import { clavesDeIa, decidirAvisos, informeDeSalud, informePublico, secretosFaltantes, secretosGeneralesFaltantes } from "../src/salud";

const AHORA = Date.UTC(2026, 9, 9, 15, 0);
const todo = {
  JUAN_ODOO_TOKEN: "valor-secreto-1",
  JUAN_WORKER_TOKEN: "valor-secreto-2",
  ANTHROPIC_API_KEY: "valor-secreto-3",
  TELEGRAM_BOT_TOKEN_JUAN: "valor-secreto-4",
  TELEGRAM_WEBHOOK_SECRET_JUAN: "valor-secreto-5",
  WA_TOKEN: "valor-secreto-6",
  PUENTE: { fetch: async () => Response.json({ conectado: true }) },
} as unknown as Env;

const deps = (env: Env, config: Record<string, unknown> = {}, extra: Record<string, unknown> = {}) => ({
  env,
  adaptadores: crearAdaptadores(),
  config: async () => normalizarConfig(config),
  gastoMes: async () => 0,
  ahora: () => AHORA,
  ...extra,
});

describe("secretos que faltan: solo nombres, según lo que Odoo eligió", () => {
  it("los dos tokens con Odoo y la clave de la IA principal", () => {
    expect(secretosFaltantes({} as Env, normalizarConfig({}))).toEqual(["JUAN_ODOO_TOKEN", "JUAN_WORKER_TOKEN", "ANTHROPIC_API_KEY"]);
    expect(secretosFaltantes(todo, normalizarConfig({}))).toEqual([]);
    expect(secretosGeneralesFaltantes({ JUAN_ODOO_TOKEN: "x" } as Env)).toEqual(["JUAN_WORKER_TOKEN"]);
  });

  it("con Meta de principal y Claude de respaldo se piden las dos claves; con OpenAI, la suya", () => {
    const sinIa = { JUAN_ODOO_TOKEN: "a", JUAN_WORKER_TOKEN: "b" } as Env;
    expect(secretosFaltantes(sinIa, normalizarConfig({ proveedor_ia: "meta", proveedor_respaldo_ia: "anthropic" }))).toEqual(["META_AI_API_KEY", "ANTHROPIC_API_KEY"]);
    expect(secretosFaltantes(sinIa, normalizarConfig({ proveedor_ia: "openai" }))).toEqual(["OPENAI_API_KEY"]);
    expect(clavesDeIa(normalizarConfig({ proveedor_ia: "meta" }))).toEqual([{ proveedor: "meta", clave: "META_AI_API_KEY", papel: "principal" }]);
  });

  it("la clave de un proveedor que Odoo no eligió NO se exige", () => {
    expect(secretosFaltantes({ JUAN_ODOO_TOKEN: "a", JUAN_WORKER_TOKEN: "b", ANTHROPIC_API_KEY: "c" } as Env, normalizarConfig({ proveedor_ia: "anthropic" }))).toEqual([]);
  });
});

describe("informeDeSalud", () => {
  it("todo cargado y el puente conectado: en orden", async () => {
    const i = await informeDeSalud(deps(todo));
    expect(i.ok).toBe(true);
    expect(i.mensaje).toBe("Todo en orden.");
    expect(i.problemas).toEqual([]);
    expect(i.canales.whatsapp_qr).toMatchObject({ activo: true, configurado: true, conectado: true });
    expect(i.canales.telegram).toMatchObject({ activo: true, configurado: true });
    expect(i.canales.messenger).toMatchObject({ activo: false, configurado: false });
  });

  it("un canal APAGADO en Odoo al que le faltan secretos no es un problema; uno ENCENDIDO sí", async () => {
    const sinMeta = await informeDeSalud(deps(todo));
    expect(sinMeta.problemas.join(" ")).not.toMatch(/messenger|instagram|whatsapp_cloud/);
    const conMeta = await informeDeSalud(deps(todo, { canales_activos: { messenger: true } }));
    expect(conMeta.problemas.join(" ")).toMatch(/messenger.*META_PAGE_TOKEN, META_APP_SECRET, META_VERIFY_TOKEN/);
    expect(conMeta.ok).toBe(false);
  });

  it("el puente desconectado es un problema (hay que volver a escanear el QR)", async () => {
    const env = { ...todo, PUENTE: { fetch: async () => Response.json({ conectado: false, estado: "esperando QR" }) } } as unknown as Env;
    const i = await informeDeSalud(deps(env));
    expect(i.canales.whatsapp_qr.conectado).toBe(false);
    expect(i.problemas.join(" ")).toMatch(/whatsapp_qr no está conectado/);
  });

  it("Odoo no recibe lo que se le manda: es un problema (con una frase estable, para avisar una sola vez), hasta que se resuelve", async () => {
    const nota = (valor: unknown, ts = AHORA - 3600_000) => ({ leerSalud: async (clave: string) => (clave === "cola_estancada" ? { json: JSON.stringify(valor), ts } : null) });
    const atascada = await informeDeSalud(deps(todo, {}, nota({ ts: AHORA - 3600_000, tipo: "mensaje" })));
    expect(atascada.ok).toBe(false);
    expect(atascada.problemas.filter((p) => /Odoo no está recibiendo/.test(p))).toHaveLength(1);
    expect(atascada.problemas.join("")).not.toMatch(/\d+ mensaje/); // sin cifras que cambien: así el cron no avisa de nuevo cada vez
    const resuelta = await informeDeSalud(deps(todo, {}, nota({ ts: AHORA - 60_000, resuelto: true })));
    expect(resuelta.problemas).toEqual([]);
    const vieja = await informeDeSalud(deps(todo, {}, nota({ ts: AHORA - 13 * 3600_000 }))); // nadie lo reanotó en 12 h: ya pasó
    expect(vieja.problemas).toEqual([]);
  });

  it("un puente que no contesta a tiempo no cuelga el informe", async () => {
    const env = { ...todo, PUENTE: { fetch: () => new Promise<Response>(() => {}) } } as unknown as Env;
    const t0 = Date.now();
    const i = await informeDeSalud(deps(env));
    expect(Date.now() - t0).toBeLessThan(6000);
    expect(i.canales.whatsapp_qr.conectado).toBeNull();
    expect(i.canales.whatsapp_qr.detalle).toMatch(/no contestó a tiempo/);
  }, 10_000);

  it("el tope de IA: se alcanza cuando el gasto llega al presupuesto; con tope 0 nunca", async () => {
    const bajo = await informeDeSalud(deps(todo, { presupuesto_ia_mensual_usd: 30 }, { gastoMes: async () => 29.99 }));
    const justo = await informeDeSalud(deps(todo, { presupuesto_ia_mensual_usd: 30 }, { gastoMes: async () => 30 }));
    const sinTope = await informeDeSalud(deps(todo, { presupuesto_ia_mensual_usd: 0 }, { gastoMes: async () => 500 }));
    expect([bajo.tope_alcanzado, justo.tope_alcanzado, sinTope.tope_alcanzado]).toEqual([false, true, false]);
    expect(justo.gasto_ia_mes_usd).toBe(30);
  });

  it("si el contador global falla, el informe sale igual (gasto 0)", async () => {
    const i = await informeDeSalud(deps(todo, {}, { gastoMes: async () => Promise.reject(new Error("global caído")) }));
    expect(i.gasto_ia_mes_usd).toBe(0);
  });

  it("jamás incluye el valor de un secreto, ni en el informe completo ni en el público", async () => {
    const completo = JSON.stringify(await informeDeSalud(deps({ ...todo, JUAN_WORKER_TOKEN: undefined } as unknown as Env)));
    const publico = JSON.stringify(await informePublico(deps(todo)));
    for (const valor of ["valor-secreto-1", "valor-secreto-2", "valor-secreto-3", "valor-secreto-4", "valor-secreto-5", "valor-secreto-6"]) {
      expect(completo).not.toContain(valor);
      expect(publico).not.toContain(valor);
    }
  });

  it("el informe público no consulta al puente por la red (no se puede usar para molestarlo)", async () => {
    let llamadas = 0;
    const env = { ...todo, PUENTE: { fetch: async () => (llamadas++, Response.json({ conectado: true })) } } as unknown as Env;
    await informePublico(deps(env));
    expect(llamadas).toBe(0);
    await informeDeSalud(deps(env));
    expect(llamadas).toBe(1);
  });
});

describe("decidirAvisos (el cron)", () => {
  it("la primera vez avisa todo; la segunda no repite", () => {
    const a = decidirAvisos(["falta X", "canal Y caído"], { avisados: [] });
    expect(a.mensajes).toHaveLength(2);
    expect(a.mensajes[0]).toBe("Aviso del asistente de D'CASA: falta X.");
    const b = decidirAvisos(["falta X", "canal Y caído"], a.nuevo);
    expect(b.mensajes).toEqual([]);
  });

  it("avisa lo nuevo y avisa «resuelto» lo que se arregló", () => {
    const previo = { avisados: ["falta X", "canal Y caído"] };
    const r = decidirAvisos(["canal Y caído", "falta Z"], previo);
    expect(r.mensajes).toEqual(["Aviso del asistente de D'CASA: falta Z.", "Resuelto en el asistente de D'CASA: falta X."]);
    expect(r.nuevo.avisados).toEqual(["canal Y caído", "falta Z"]);
  });

  it("sin problemas y sin avisos previos: nada", () => {
    expect(decidirAvisos([], { avisados: [] })).toEqual({ mensajes: [], nuevo: { avisados: [] } });
  });

  it("un problema que vuelve después de resolverse se avisa de nuevo", () => {
    const uno = decidirAvisos(["caído"], { avisados: [] });
    const resuelto = decidirAvisos([], uno.nuevo);
    const otraVez = decidirAvisos(["caído"], resuelto.nuevo);
    expect(otraVez.mensajes).toEqual(["Aviso del asistente de D'CASA: caído."]);
  });
});
