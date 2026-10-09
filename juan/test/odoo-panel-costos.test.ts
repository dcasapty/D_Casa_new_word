/** `GET /odoo/costos`: el gasto del mes por modelo que lee la pantalla «Costos de IA» de Odoo. */
import { describe, expect, it, vi } from "vitest";
import { CONFIG_POR_DEFECTO, normalizarConfig } from "../src/config";
import type { Env } from "../src/env";
import { manejarCostos } from "../src/odoo-panel-costos";

const AHORA = Date.UTC(2026, 9, 9, 15, 0);

function montar(opciones: { gasto?: unknown; falla?: boolean; config?: Record<string, unknown> } = {}) {
  const pedidos: string[] = [];
  const env = {
    GLOBAL: {
      idFromName: (n: string) => n,
      get: () => ({
        gastoMes: async (mes: string) => {
          pedidos.push(mes);
          if (opciones.falla) throw new Error("el almacén no responde: secreto-interno-123");
          return (
            opciones.gasto ?? {
              mes,
              usd: 12.3456,
              turnos: 321,
              porModelo: [
                { modelo: "claude-haiku-4-5", usd: 2.34567891, turnos: 300, estimado: false },
                { modelo: "claude-sonnet-5-5", usd: 10.0, turnos: 21, estimado: false },
              ],
              modelosSinPrecio: [],
            }
          );
        },
      }),
    },
  } as unknown as Env;
  const config = normalizarConfig({ ...CONFIG_POR_DEFECTO, ...opciones.config });
  return { env, pedidos, pedir: (metodo = "GET") => manejarCostos(new Request("https://juan.example/odoo/costos", { method: metodo }), env, { config: async () => config, ahora: () => AHORA }) };
}

describe("GET /odoo/costos", () => {
  it("devuelve el mes (en la hora de Panamá), el total, el tope y el gasto de cada modelo", async () => {
    const m = montar();
    const res = await m.pedir();
    expect(res.status).toBe(200);
    expect(res.headers.get("cache-control")).toBe("no-store");
    expect(await res.json()).toEqual({
      ok: true,
      mes: "2026-10",
      gasto_usd: 12.35,
      turnos: 321,
      tope_usd: CONFIG_POR_DEFECTO.presupuesto_ia_mensual_usd,
      por_modelo: [
        { modelo: "claude-haiku-4-5", usd: 2.3457, turnos: 300, estimado: false },
        { modelo: "claude-sonnet-5-5", usd: 10, turnos: 21, estimado: false },
      ],
      modelos_sin_precio: [],
    });
    expect(m.pedidos).toEqual(["2026-10"]);
  });

  it("a las 11 p. m. del 31 en Panamá sigue siendo el mes que termina (no el UTC)", async () => {
    const m = montar();
    const res = await manejarCostos(new Request("https://juan.example/odoo/costos"), m.env, {
      config: async () => normalizarConfig(CONFIG_POR_DEFECTO),
      ahora: () => Date.UTC(2026, 10, 1, 4, 30), // 1.º de noviembre 04:30 UTC = 31 de octubre 11:30 p. m. en Panamá
    });
    expect((await res.json<any>()).mes).toBe("2026-10");
  });

  it("avisa de los modelos que gastaron sin precio cargado", async () => {
    const m = montar({
      gasto: { mes: "2026-10", usd: 1, turnos: 1, porModelo: [{ modelo: "muse-spark-1.3", usd: 1, turnos: 1, estimado: true }], modelosSinPrecio: ["muse-spark-1.3"] },
    });
    const j = await (await m.pedir()).json<any>();
    expect(j.modelos_sin_precio).toEqual(["muse-spark-1.3"]);
    expect(j.por_modelo[0].estimado).toBe(true);
  });

  it("un mes sin gasto: ceros, no un error", async () => {
    const m = montar({ gasto: { mes: "2026-10", usd: 0, turnos: 0, porModelo: [], modelosSinPrecio: [] } });
    const j = await (await m.pedir()).json<any>();
    expect([j.gasto_usd, j.turnos, j.por_modelo]).toEqual([0, 0, []]);
  });

  it("si el almacén falla: 502 con un texto genérico (sin el mensaje interno)", async () => {
    const error = vi.spyOn(console, "error").mockImplementation(() => {});
    const res = await montar({ falla: true }).pedir();
    expect(res.status).toBe(502);
    expect(await res.json()).toEqual({ ok: false, error: "No pude leer el gasto del mes." });
    error.mockRestore();
  });

  it("solo GET", async () => {
    const m = montar();
    for (const metodo of ["POST", "PUT", "DELETE"]) expect((await m.pedir(metodo)).status).toBe(405);
    expect(m.pedidos).toEqual([]);
  });
});
