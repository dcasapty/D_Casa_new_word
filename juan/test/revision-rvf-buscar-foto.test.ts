/**
 * Revisión adversarial (rvf) de `POST /odoo/buscar-foto`: la tienda sola no puede comerse el presupuesto de IA de Juan.
 *
 * Con el código revisado, 200 fotos al día durante un mes gastaban del mismo tope que las conversaciones. Ahora (I4): la foto
 * tiene su techo propio (`tope_mes_usd`, 5 USD de fábrica) y no se lee con el gasto de Juan por encima del 80 % de su tope.
 */
import { expect, it } from "vitest";
import { CONFIG_POR_DEFECTO, normalizarConfig } from "../src/config";
import type { Env } from "../src/env";
import { buscarFoto, TOPE_MES_FOTO_USD, validarPeticion } from "../src/odoo-panel-buscar-foto";

const JPEG = new Uint8Array([0xff, 0xd8, 0xff, 0xe0, ...new TextEncoder().encode("foto inventada".repeat(10)), 0xff, 0xd9]);

function montar(gastoDeJuan: number) {
  // Una foto que hace que el modelo no conteste JSON (texto escrito en la imagen, por ejemplo): el lector de Juan llama
  // DOS veces (con esquema y sin él), y Workers AI no siempre dice los tokens → la estimación alta, dos veces.
  const env = { RECONOCER_IMAGENES: "1", AI: { run: async () => ({ response: "no es json" }) } } as unknown as Env;
  const config = normalizarConfig({ ...CONFIG_POR_DEFECTO, presupuesto_ia_mensual_usd: 30 });
  const p = validarPeticion({ mime: "image/jpeg", base64: Buffer.from(JPEG).toString("base64") });
  if (Array.isArray(p)) throw new Error(p[1]);
  const cuenta = { foto: 0, juan: gastoDeJuan, lecturas: 0 };
  const deps = {
    config: async () => config,
    ahora: () => Date.UTC(2026, 10, 13, 15),
    gasto: {
      // Como en Global: lo de Cloudflare (la foto) no suma en el gasto de Juan.
      gastoMes: async () => cuenta.juan,
      gastoFotoMes: async () => cuenta.foto,
      registrarGasto: async (_mes: string, concepto: string, _uso: unknown, usd: number) => {
        if (concepto.startsWith("cloudflare:")) cuenta.foto += usd;
        else cuenta.juan += usd;
        cuenta.lecturas++;
      },
    },
  };
  return { p, env, deps, cuenta };
}

it("la búsqueda por foto no puede comerse el presupuesto de IA de las conversaciones de Juan", async () => {
  const { p, env, deps, cuenta } = montar(0);
  // El tope de fábrica de la tienda: 200 por día (TOPES_DE_FABRICA['dia']), un mes de 30 días, sin conversaciones.
  for (let i = 0; i < 200 * 30; i++) await buscarFoto(p, env, deps);
  expect(cuenta.juan, "nada de la foto cae en el gasto de Juan").toBe(0);
  // Lo más que se pasa es lo de UNA búsqueda (la que empezó con el techo todavía sin tocar).
  expect(cuenta.foto, `la tienda sola gastó $${cuenta.foto.toFixed(4)}`).toBeLessThanOrEqual(TOPE_MES_FOTO_USD + 0.01);
});

it("con el gasto de Juan por encima del 80 % de su tope no se lee ni una foto", async () => {
  const { p, env, deps, cuenta } = montar(30 * 0.8);
  for (let i = 0; i < 50; i++) expect((await buscarFoto(p, env, deps)).cuerpo).toMatchObject({ ok: false, causa: "reserva" });
  expect(cuenta.lecturas).toBe(0);
});
