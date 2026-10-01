import { spawn, type ChildProcess } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

/**
 * Integración en el runtime REAL de Workers (workerd local con `wrangler dev`; sin cuenta y sin red externa):
 * el mismo SQL del núcleo corre sobre el SQLite de un Durable Object.
 * (@cloudflare/vitest-pool-workers 0.22 pide vitest ^4 y este proyecto usa vitest 5.)
 * Se omite con BRIAN_SIN_WORKERD=1.
 */
const PUERTO = 8799;
let proc: ChildProcess | undefined;
const omitir = process.env.BRIAN_SIN_WORKERD === "1";

beforeAll(async () => {
  if (omitir) return;
  proc = spawn("npx", ["wrangler", "dev", "--config", "test/workerd/wrangler.jsonc", "--port", String(PUERTO), "--ip", "127.0.0.1", "--show-interactive-dev-session=false",
    "--persist-to", mkdtempSync(join(tmpdir(), "brian-workerd-"))], {
    stdio: "pipe", detached: true,
  });
  for (let i = 0; i < 90; i++) {
    try {
      const r = await fetch(`http://127.0.0.1:${PUERTO}/cdn-cgi/local/explorer/api/local/workers`);
      if (r.ok) return;
    } catch { /* aún arrancando */ }
    await new Promise((ok) => setTimeout(ok, 1000));
  }
  throw new Error("wrangler dev no arrancó");
}, 120_000);

afterAll(() => {
  if (proc?.pid) process.kill(-proc.pid, "SIGTERM");
});

describe.skipIf(omitir)("núcleo de Brian dentro de un Durable Object (workerd)", () => {
  it("turno con herramienta + confirmación idempotente + libro en el SQLite del DO", async () => {
    const r = (await (await fetch(`http://127.0.0.1:${PUERTO}/?conv=${crypto.randomUUID()}`)).json()) as Record<string, any>;
    expect(r.pendientes).toBe(1);
    expect(r.c1).toBe("ejecutada");
    expect(r.c2).toMatchObject({ estado: "ejecutada", repetida: true });
    expect(r.pagos).toBe(1);
    expect(r.uso).toEqual({ n: 2, costo: 4200 });
    expect(r.mensajes.n).toBe(6);
  });

  it("el estado del DO persiste: repetir el mismo guion en la MISMA conversación no vuelve a cobrar", async () => {
    const conv = crypto.randomUUID();
    await (await fetch(`http://127.0.0.1:${PUERTO}/?conv=${conv}`)).text();
    const r = (await (await fetch(`http://127.0.0.1:${PUERTO}/?conv=${conv}`)).json()) as Record<string, any>;
    // El segundo turno reutiliza el resultado guardado por id de llamada: ni pendiente nueva ni segundo pago.
    expect(r.pendientes).toBe(0);
    expect(r.pagos).toBe(1);
  });
});
