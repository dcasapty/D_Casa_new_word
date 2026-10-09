/**
 * Las rutas de «Conexiones» del panel de Odoo: el QR para vincular WhatsApp, reiniciar y desvincular el puente.
 * Lo que más importa: el QR NUNCA se escribe en un registro (ni al éxito ni en un error), nunca se cachea, y los errores
 * no repiten lo que contestó el puente.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Env } from "../src/env";
import { faltantesDelPuente, manejarConexiones } from "../src/odoo-panel-conexiones";
import { tokenParaCabecera } from "../src/seguridad";

const WA_TOKEN = "token-del-puente-de-prueba-0123456789ñ";
const QR = `data:image/png;base64,${"iVBORw0KGgo".repeat(40)}`;

interface Llamada {
  url: string;
  metodo: string;
  cabeceras: Record<string, string>;
  cuerpo?: string;
}

function puenteFalso(contesta: (ruta: string, metodo: string) => Response | Promise<Response> | "colgado") {
  const llamadas: Llamada[] = [];
  const fetcher = {
    fetch: async (url: string, init?: RequestInit) => {
      const u = new URL(url);
      llamadas.push({ url, metodo: init?.method ?? "GET", cabeceras: Object.fromEntries(new Headers(init?.headers).entries()), cuerpo: init?.body as string | undefined });
      const r = contesta(u.pathname, init?.method ?? "GET");
      if (r === "colgado") return new Promise<Response>(() => {});
      return r;
    },
  } as unknown as Fetcher;
  return { fetcher, llamadas };
}

const jsonRes = (cuerpo: unknown, status = 200) => new Response(JSON.stringify(cuerpo), { status, headers: { "content-type": "application/json" } });
const envCon = (fetcher?: Fetcher, extra: Partial<Env> = {}) => ({ PUENTE: fetcher, WA_TOKEN, ...extra }) as unknown as Env;
const pedir = (ruta: string, metodo: string, env: Env) => manejarConexiones(ruta, new Request(`https://juan.example${ruta}`, { method: metodo, ...(metodo === "POST" ? { body: "{}" } : {}) }), env);

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

/** Todo lo que el Worker pudo imprimir mientras corría la prueba. */
function espiarRegistros() {
  const canales = ["log", "info", "warn", "error", "debug"] as const;
  const espias = canales.map((c) => vi.spyOn(console, c).mockImplementation(() => {}));
  return () => espias.flatMap((e) => e.mock.calls.flat().map((x) => (typeof x === "string" ? x : JSON.stringify(x)))).join("\n");
}

describe("GET /odoo/qr", () => {
  it("devuelve el QR como imagen PNG, sin caché, y le habla al puente con el token codificado", async () => {
    const p = puenteFalso(() => jsonRes({ qr: QR, edadMs: 12_400, generados: 3, estado: "esperando-qr", ultimoError: null }));
    const res = await pedir("/odoo/qr", "GET", envCon(p.fetcher));
    expect(res.status).toBe(200);
    expect(res.headers.get("cache-control")).toBe("no-store");
    expect(await res.json()).toEqual({ ok: true, estado: "necesita_qr", qr: QR, edad_s: 12 });
    expect(p.llamadas).toHaveLength(1);
    expect(p.llamadas[0].url).toBe("https://puente/api/qr");
    expect(p.llamadas[0].metodo).toBe("GET");
    expect(p.llamadas[0].cabeceras["x-wa-token-b64"]).toBe(tokenParaCabecera(WA_TOKEN));
  });

  it("traduce el estado del puente a palabras del panel", async () => {
    const casos: [string, string][] = [
      ["esperando-qr", "necesita_qr"],
      ["conectada", "conectado"],
      ["desvinculada", "desvinculada"],
      ["cerrada", "desconectado"],
      ["arrancando", "arrancando"],
      ["apagado", "apagado"],
      ["algo-nuevo", "algo-nuevo"],
    ];
    for (const [crudo, esperado] of casos) {
      const p = puenteFalso(() => jsonRes({ qr: null, estado: crudo }));
      const j = await (await pedir("/odoo/qr", "GET", envCon(p.fetcher))).json<any>();
      expect([crudo, j.estado]).toEqual([crudo, esperado]);
      expect(j.qr).toBeNull();
    }
  });

  it("con la sesión conectada no hay QR", async () => {
    const p = puenteFalso(() => jsonRes({ qr: null, edadMs: null, estado: "conectada" }));
    expect(await (await pedir("/odoo/qr", "GET", envCon(p.fetcher))).json()).toEqual({ ok: true, estado: "conectado", qr: null, edad_s: null });
  });

  it("solo acepta una imagen PNG: todo lo demás se descarta", async () => {
    const malos: unknown[] = ["<script>alert(1)</script>", "javascript:alert(1)", "data:text/html;base64,AAAA", "data:image/svg+xml;base64,AAAA", `data:image/png;base64,${"A".repeat(250_000)}`, 5, ["x"], { a: 1 }, true];
    for (const malo of malos) {
      const p = puenteFalso(() => jsonRes({ qr: malo, estado: "esperando-qr" }));
      const j = await (await pedir("/odoo/qr", "GET", envCon(p.fetcher))).json<any>();
      expect(j.qr).toBeNull();
    }
  });

  it("el QR no se escribe en ningún registro, ni con éxito ni cuando algo sale mal", async () => {
    const leer = espiarRegistros();
    const trozo = QR.slice(30, 90);
    const casos = [
      puenteFalso(() => jsonRes({ qr: QR, estado: "esperando-qr" })),
      puenteFalso(() => jsonRes({ error: QR, qr: QR }, 500)),
      puenteFalso(() => jsonRes({ qr: QR, ultimoError: QR, estado: "esperando-qr" })),
      puenteFalso(() => {
        throw new Error(`falló con ${QR}`);
      }),
      puenteFalso(() => new Response(QR, { status: 200 })),
    ];
    for (const p of casos) await pedir("/odoo/qr", "GET", envCon(p.fetcher));
    expect(leer()).not.toContain(trozo);
    expect(leer()).not.toContain("iVBORw0KGgo");
  });

  it("un error del puente no repite lo que contestó (puede traer el QR)", async () => {
    const p = puenteFalso(() => jsonRes({ error: `no pude: ${QR}` }, 500));
    const res = await pedir("/odoo/qr", "GET", envCon(p.fetcher));
    expect(res.status).toBe(502);
    const texto = await res.text();
    expect(JSON.parse(texto)).toEqual({ ok: false, error: "El puente respondió 500." });
    expect(texto).not.toContain("iVBOR");
  });

  it("el último error del puente se muestra solo si es un texto corto (y nunca un data:)", async () => {
    let p = puenteFalso(() => jsonRes({ qr: null, estado: "cerrada", ultimoError: "Connection Closed" }));
    expect((await (await pedir("/odoo/qr", "GET", envCon(p.fetcher))).json<any>()).mensaje).toBe("Connection Closed");
    p = puenteFalso(() => jsonRes({ qr: null, estado: "cerrada", ultimoError: QR }));
    expect((await (await pedir("/odoo/qr", "GET", envCon(p.fetcher))).json<any>()).mensaje).toBeUndefined();
    p = puenteFalso(() => jsonRes({ qr: null, estado: "cerrada", ultimoError: "x".repeat(500) }));
    expect((await (await pedir("/odoo/qr", "GET", envCon(p.fetcher))).json<any>()).mensaje).toBeUndefined();
  });

  it("si el puente no contesta a tiempo: 504, sin colgarse", async () => {
    vi.useFakeTimers();
    const p = puenteFalso(() => "colgado");
    const pendiente = pedir("/odoo/qr", "GET", envCon(p.fetcher));
    await vi.advanceTimersByTimeAsync(9000);
    const res = await pendiente;
    expect(res.status).toBe(504);
    expect(await res.json()).toEqual({ ok: false, error: "El puente de WhatsApp no contestó." });
  });

  it("si la llamada al puente revienta: 504 y solo el tipo de error en el registro", async () => {
    const leer = espiarRegistros();
    const p = puenteFalso(() => {
      throw new TypeError("fetch failed https://interno.example/secreto?token=abc");
    });
    const res = await pedir("/odoo/qr", "GET", envCon(p.fetcher));
    expect(res.status).toBe(504);
    expect(leer()).toContain("TypeError");
    expect(leer()).not.toContain("interno.example");
    expect(leer()).not.toContain("abc");
  });

  it("sin el puente o sin WA_TOKEN: 503 con los NOMBRES que faltan, y no se llama a nadie", async () => {
    const p = puenteFalso(() => jsonRes({}));
    let res = await pedir("/odoo/qr", "GET", envCon(undefined));
    expect(res.status).toBe(503);
    expect((await res.json<any>()).faltan).toEqual(["PUENTE"]);
    res = await pedir("/odoo/qr", "GET", { PUENTE: p.fetcher } as unknown as Env);
    expect((await res.json<any>()).faltan).toEqual(["WA_TOKEN"]);
    res = await pedir("/odoo/qr", "GET", {} as Env);
    const j = await res.json<any>();
    expect(j.faltan).toEqual(["PUENTE", "WA_TOKEN"]);
    expect(j.error).toMatch(/PUENTE y WA_TOKEN/);
    expect(p.llamadas).toHaveLength(0);
    expect(faltantesDelPuente(envCon(p.fetcher))).toEqual([]);
  });

  it("solo GET", async () => {
    const p = puenteFalso(() => jsonRes({}));
    for (const metodo of ["POST", "PUT", "DELETE"]) expect((await pedir("/odoo/qr", metodo, envCon(p.fetcher))).status).toBe(405);
    expect(p.llamadas).toHaveLength(0);
  });
});

describe("POST /odoo/reiniciar y /odoo/desvincular", () => {
  it("reiniciar le pide al puente /api/reiniciar", async () => {
    const p = puenteFalso(() => jsonRes({ ok: true, mensaje: "Contenedor reiniciado. Vuelve en menos de un minuto y no debe pedir QR.", reinicios_forzados: 1 }));
    const res = await pedir("/odoo/reiniciar", "POST", envCon(p.fetcher));
    expect(res.status).toBe(200);
    expect(res.headers.get("cache-control")).toBe("no-store");
    expect(await res.json()).toEqual({ ok: true, mensaje: "Contenedor reiniciado. Vuelve en menos de un minuto y no debe pedir QR." });
    expect(p.llamadas.map((l) => [l.metodo, new URL(l.url).pathname])).toEqual([["POST", "/api/reiniciar"]]);
    expect(p.llamadas[0].cabeceras["x-wa-token-b64"]).toBe(tokenParaCabecera(WA_TOKEN));
  });

  it("desvincular le pide al puente /api/desvincular", async () => {
    const p = puenteFalso(() => jsonRes({ ok: true }));
    const res = await pedir("/odoo/desvincular", "POST", envCon(p.fetcher));
    expect(await res.json()).toEqual({ ok: true });
    expect(p.llamadas.map((l) => [l.metodo, new URL(l.url).pathname])).toEqual([["POST", "/api/desvincular"]]);
  });

  it("cada una solo con POST: un GET no desvincula nada", async () => {
    const p = puenteFalso(() => jsonRes({ ok: true }));
    for (const ruta of ["/odoo/reiniciar", "/odoo/desvincular"]) {
      for (const metodo of ["GET", "PUT", "DELETE"]) expect((await pedir(ruta, metodo, envCon(p.fetcher))).status).toBe(405);
    }
    expect(p.llamadas).toHaveLength(0);
  });

  it("si el puente dice que no, se dice por qué (texto corto) con 502", async () => {
    const p = puenteFalso(() => jsonRes({ error: "El puente está apagado." }, 409));
    const res = await pedir("/odoo/desvincular", "POST", envCon(p.fetcher));
    expect(res.status).toBe(502);
    expect(await res.json()).toEqual({ ok: false, error: "El puente respondió 409: El puente está apagado." });
  });

  it("un error con un texto enorme o con un QR no se repite", async () => {
    for (const cuerpo of [{ error: "e".repeat(500) }, { error: QR }, "no es json"]) {
      const p = puenteFalso(() => (typeof cuerpo === "string" ? new Response(cuerpo, { status: 500 }) : jsonRes(cuerpo, 500)));
      const j = await (await pedir("/odoo/reiniciar", "POST", envCon(p.fetcher))).json<any>();
      expect(j).toEqual({ ok: false, error: "El puente respondió 500." });
    }
  });

  it("sin puente: 503 y no se llama a nadie", async () => {
    for (const ruta of ["/odoo/reiniciar", "/odoo/desvincular"]) {
      const res = await pedir(ruta, "POST", {} as Env);
      expect(res.status).toBe(503);
      expect((await res.json<any>()).faltan).toEqual(["PUENTE", "WA_TOKEN"]);
    }
  });
});
