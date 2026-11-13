/**
 * Revisión adversarial (rvf): cuánta memoria ocupa UNA búsqueda por foto del tamaño máximo (MAX_BYTES_FOTO, 1,5 MB) en el Worker (que comparte isolate,
 * y su límite de 128 MB, con los webhooks de WhatsApp). Medición, no prueba de aceptación.
 */
import { expect, it } from "vitest";
import { CONFIG_POR_DEFECTO, normalizarConfig } from "../src/config";
import type { Env } from "../src/env";
import { buscarFoto, MAX_BYTES_FOTO, validarPeticion } from "../src/odoo-panel-buscar-foto";

it("pico de memoria de una foto del tamaño máximo", async () => {
  const gc = (globalThis as { gc?: () => void }).gc;
  const bytes = new Uint8Array(MAX_BYTES_FOTO - 16);
  for (let i = 0; i < bytes.length; i++) bytes[i] = (i * 2654435761) & 0xff;
  bytes.set([0xff, 0xd8, 0xff]);
  const cuerpo = JSON.stringify({ mime: "image/jpeg", base64: Buffer.from(bytes).toString("base64") });
  gc?.();
  const antes = process.memoryUsage();
  let pico = 0;
  const mirar = () => {
    const m = process.memoryUsage();
    pico = Math.max(pico, m.heapUsed + m.arrayBuffers - antes.heapUsed - antes.arrayBuffers);
  };
  const c = JSON.parse(cuerpo);
  mirar();
  const p = validarPeticion(c);
  mirar();
  if (Array.isArray(p)) throw new Error(String(p));
  const env = {
    RECONOCER_IMAGENES: "1",
    AI: { run: async (_m: string, entrada: unknown) => { const s = JSON.stringify(entrada); mirar(); return { response: s.length ? null : null }; } },
  } as unknown as Env;
  const config = normalizarConfig(CONFIG_POR_DEFECTO);
  await buscarFoto(p, env, { config: async () => config, ahora: () => 0, gasto: { gastoMes: async () => 0, registrarGasto: async () => {} } });
  console.log(`pico ≈ ${(pico / 1024 / 1024).toFixed(1)} MB por búsqueda (sin contar el cuerpo crudo de ${(cuerpo.length / 1024 / 1024).toFixed(1)} MB)`);
  expect(pico).toBeGreaterThan(0);
});
