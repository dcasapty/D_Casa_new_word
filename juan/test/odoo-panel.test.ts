/**
 * Las rutas del panel de Odoo vistas desde `manejar` (rutas.ts): todas piden el token de Odoo, en tiempo constante, y no
 * pisan a las rutas que ya existían (`/odoo/enviar`, `/odoo/estado`, `/odoo/seguimiento`, `/odoo/salud`).
 */
import { describe, expect, it } from "vitest";
import { CONFIG_POR_DEFECTO, normalizarConfig } from "../src/config";
import type { Env } from "../src/env";
import { manejar, type DepsRutas } from "../src/rutas";

const TOKEN_WORKER = "token-del-worker-de-prueba-0123456789";
const WA_TOKEN = "token-del-puente-de-prueba-0123456789";
const AHORA = Date.UTC(2026, 9, 9, 15, 0);
const QR = `data:image/png;base64,${"iVBORw0KGgo".repeat(20)}`;

const puente = (llamadas: string[]) =>
  ({
    fetch: async (url: string, init?: RequestInit) => {
      llamadas.push(`${init?.method ?? "GET"} ${new URL(url).pathname}`);
      return new Response(JSON.stringify({ ok: true, qr: QR, estado: "esperando-qr", edadMs: 3000 }), { headers: { "content-type": "application/json" } });
    },
  }) as unknown as Fetcher;

function montar() {
  const llamadasPuente: string[] = [];
  const estados: unknown[] = [];
  const enviados: unknown[] = [];
  const env = {
    JUAN_WORKER_TOKEN: TOKEN_WORKER,
    WA_TOKEN,
    PUENTE: puente(llamadasPuente),
    GLOBAL: { idFromName: (n: string) => n, get: () => ({ gastoMes: async () => ({ usd: 3, turnos: 4, porModelo: [], modelosSinPrecio: [] }) }) },
  } as unknown as Env;
  const config = normalizarConfig(CONFIG_POR_DEFECTO);
  const conv = {
    ingest: async () => ({ ok: true as const, accion: "en_espera" as const }),
    enviarVendedora: async (s: unknown) => (enviados.push(s), { ok: true as const, id_mensaje: "m1" }),
    fijarEstado: async (s: unknown) => (estados.push(s), { ok: true as const }),
    seguimiento: async () => ({ ok: true as const, resultado: "enviado" as const }),
    leerMedio: async () => null,
    olvidar: async () => ({ ok: true as const, mensajes: 0 }),
  };
  const deps: DepsRutas = {
    adaptadores: [],
    config: async () => config,
    conversacion: () => conv,
    gastoMes: async () => 3,
    ahora: () => AHORA,
    esperarDespues: () => {},
  };
  return { env, deps, llamadasPuente, estados, enviados, pedir: (req: Request, e: Env = env) => manejar(req, e, deps) };
}

const req = (ruta: string, metodo = "GET", cab: Record<string, string> = {}, cuerpo?: unknown) =>
  new Request(`https://juan.example${ruta}`, { method: metodo, headers: { "content-type": "application/json", ...cab }, ...(cuerpo !== undefined ? { body: JSON.stringify(cuerpo) } : {}) });
const conToken = { authorization: `Bearer ${TOKEN_WORKER}` };

const RUTAS: [string, string][] = [
  ["POST", "/odoo/sugerir"],
  ["GET", "/odoo/costos"],
  ["GET", "/odoo/qr"],
  ["POST", "/odoo/reiniciar"],
  ["POST", "/odoo/desvincular"],
];

describe("las rutas del panel piden el token de Odoo", () => {
  it("sin token o con uno equivocado: 401 y no se toca ni el puente ni nada", async () => {
    const m = montar();
    for (const [metodo, ruta] of RUTAS) {
      for (const cab of [{} as Record<string, string>, { authorization: "Bearer otro-token" }, { authorization: TOKEN_WORKER }, { authorization: `Bearer ${TOKEN_WORKER}x` }, { authorization: "Basic abc" }]) {
        const res = await m.pedir(req(ruta, metodo, cab, metodo === "POST" ? {} : undefined));
        expect([ruta, res.status]).toEqual([ruta, 401]);
      }
    }
    expect(m.llamadasPuente).toEqual([]);
  });

  it("sin JUAN_WORKER_TOKEN en el Worker: 503 que nombra el secreto, aunque llegue un Bearer cualquiera", async () => {
    const m = montar();
    for (const [metodo, ruta] of RUTAS) {
      const res = await m.pedir(req(ruta, metodo, { authorization: "Bearer lo-que-sea" }, metodo === "POST" ? {} : undefined), {} as Env);
      expect(res.status).toBe(503);
      expect((await res.json<any>()).secretos_faltantes).toContain("JUAN_WORKER_TOKEN");
    }
  });

  it("con el token correcto cada ruta contesta lo suyo", async () => {
    const m = montar();
    expect((await m.pedir(req("/odoo/costos", "GET", conToken))).status).toBe(200);
    const qr = await m.pedir(req("/odoo/qr", "GET", conToken));
    expect(await qr.json<any>()).toMatchObject({ ok: true, estado: "necesita_qr", qr: QR });
    expect((await m.pedir(req("/odoo/reiniciar", "POST", conToken, {}))).status).toBe(200);
    expect((await m.pedir(req("/odoo/desvincular", "POST", conToken, {}))).status).toBe(200);
    expect(m.llamadasPuente).toEqual(["GET /api/qr", "POST /api/reiniciar", "POST /api/desvincular"]);
    // /sugerir sin clave de IA en este entorno: dice cuál falta (y no se cae).
    const sugerir = await m.pedir(req("/odoo/sugerir", "POST", conToken, { conversacion_id: 1, canal: "whatsapp_qr", mensajes: [{ autor: "cliente", texto: "Hola" }] }));
    expect(sugerir.status).toBe(503);
  });

  it("el método equivocado da 405, no una acción", async () => {
    const m = montar();
    expect((await m.pedir(req("/odoo/qr", "POST", conToken, {}))).status).toBe(405);
    expect((await m.pedir(req("/odoo/reiniciar", "GET", conToken))).status).toBe(405);
    expect((await m.pedir(req("/odoo/costos", "POST", conToken, {}))).status).toBe(405);
    expect((await m.pedir(req("/odoo/sugerir", "GET", conToken))).status).toBe(405);
    expect(m.llamadasPuente).toEqual([]);
  });

  it("también con una barra final", async () => {
    const m = montar();
    expect((await m.pedir(req("/odoo/costos/", "GET", conToken))).status).toBe(200);
  });
});

describe("las rutas de siempre siguen igual", () => {
  it("/odoo/estado, /odoo/enviar y /odoo/salud no pasan por el panel", async () => {
    const m = montar();
    const estado = await m.pedir(req("/odoo/estado", "POST", conToken, { canal: "telegram", id_externo: "1", estado: "humano" }));
    expect(estado.status).toBe(200);
    expect(m.estados).toHaveLength(1);
    const salud = await m.pedir(req("/odoo/salud", "GET", conToken));
    expect(salud.status).toBe(200);
    expect((await salud.json<any>()).canales).toBeDefined();
    // Una ruta que no existe sigue dando 404.
    expect((await m.pedir(req("/odoo/no-existe", "POST", conToken, { canal: "telegram", id_externo: "1" }))).status).toBe(404);
  });
});
