/**
 * `POST /tienda/v1/voz` por el enrutador de verdad (rutas.ts → tienda/rutas.ts → tienda/voz.ts): el mismo CORS y el mismo pase que
 * `/tienda/v1/mensaje`, los topes y el presupuesto de la tienda (con su contador real, en SQLite de Node), y lo que no se negocia:
 * de vuelta SOLO el texto, el audio no llega al Durable Object de la sesión ni a los registros, y solo se llama a Whisper.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { normalizarConfig, type Config } from "../../src/config";
import type { Env } from "../../src/env";
import { MODELO_DE_LA_VOZ, TopesDeLaTienda } from "../../src/motor/global";
import { MODELO_WHISPER } from "../../src/motor/transcribir";
import { costoDeLaVoz, MAX_BYTES_VOZ } from "../../src/motor/voz";
import { manejar, type DepsRutas } from "../../src/rutas";
import { firmarPase } from "../../src/tienda/pase";
import { manejarTienda } from "../../src/tienda/rutas";
import { aBase64, mp4, oggOpus, webmOpus } from "../helpers/audio";
import { crearSqlNode } from "../helpers/sqlNode";

const TOKEN = "token-del-worker-de-prueba-0123456789abcdef";
const AHORA = Date.UTC(2026, 10, 16, 16, 0);
const SID = "AAECAwQFBgcICQoLDA0ODw";
const URL_VOZ = "https://dcasa-juan.dcasapty.workers.dev/tienda/v1/voz";
const ORIGEN = "https://dcasapty.com";
const DICHO = "Busco un juego de sala gris para un apartamento pequeño";

afterEach(() => vi.restoreAllMocks());

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const leer = async (res: Response) => (await res.json()) as Record<string, any>;

function montar(op: { config?: Config; ai?: { run: (...a: unknown[]) => Promise<unknown> } | null; bandera?: string; texto?: string; duracion?: number } = {}) {
  const sql = crearSqlNode();
  const topes = new TopesDeLaTienda(sql);
  const ai = op.ai === null ? undefined : (op.ai ?? { run: vi.fn(async () => ({ text: ` ${op.texto ?? DICHO} `, transcription_info: { duration: op.duracion ?? 4 }, vtt: "WEBVTT", words: [{ word: "Busco" }] })) });
  const sesiones: string[] = [];
  const env = {
    JUAN_WORKER_TOKEN: TOKEN,
    TRANSCRIBIR_AUDIO: op.bandera ?? "1",
    ...(ai ? { AI: ai } : {}),
    // El Durable Object de la sesión: la voz NUNCA debe tocarlo (ahí vive la conversación).
    TIENDA: {
      idFromName: (n: string) => {
        sesiones.push(n);
        return { n };
      },
      get: () => ({
        atender: async () => {
          throw new Error("la voz no debe llegar a la sesión");
        },
      }),
    },
  } as unknown as Env;
  const config = op.config ?? normalizarConfig({ brian_tienda: { activo: true } });
  const d: DepsRutas = {
    adaptadores: [],
    config: async () => config,
    conversacion: () => {
      throw new Error("no se usa");
    },
    gastoMes: async () => 0,
    ahora: () => AHORA,
    esperarDespues: () => {},
  };
  const global = {
    reservarVozTienda: vi.fn(async (p: Parameters<TopesDeLaTienda["reservarVoz"]>[0]) => topes.reservarVoz(p, AHORA)),
    cerrarTurnoTienda: vi.fn(async (id: number, gastos: Parameters<TopesDeLaTienda["cerrar"]>[1]) => topes.cerrar(id, gastos)),
  };
  // Por el enrutador de verdad, con el contador de la tienda inyectado (en producción, el Durable Object `Global`).
  const pedir = (req: Request) => {
    const ruta = new URL(req.url).pathname;
    return ruta.startsWith("/tienda/") ? manejarTienda(ruta, req, env, d, { voz: { global } }) : manejar(req, env, d);
  };
  return { env, d, ai, topes, sql, global, sesiones, pedir };
}

const pase = () => firmarPase(TOKEN, { v: 1, sid: SID, exp: Math.floor(AHORA / 1000) + 1800, red: "190.140.12.0/24", sitio: 1 });

async function nota(audio: Uint8Array = webmOpus(4), op: { tipo?: string; origen?: string | null; ip?: string; autorizacion?: string; duracion?: string } = {}) {
  const headers: Record<string, string> = { "content-type": op.tipo ?? "audio/webm;codecs=opus", "cf-connecting-ip": op.ip ?? "190.140.12.34", authorization: op.autorizacion ?? `Pase ${await pase()}` };
  if (op.origen !== null) headers.origin = op.origen ?? ORIGEN;
  const url = `${URL_VOZ}${op.duracion !== undefined ? `?duracion_ms=${op.duracion}` : "?duracion_ms=4100"}`;
  return new Request(url, { method: "POST", headers, body: audio });
}

describe("la puerta: el mismo CORS y el mismo pase que el chat", () => {
  it("el preflight de un origen permitido: 204 con GET, POST y OPTIONS", async () => {
    const m = montar();
    const res = await m.pedir(new Request(URL_VOZ, { method: "OPTIONS", headers: { origin: ORIGEN, "access-control-request-method": "POST", "access-control-request-headers": "authorization, content-type" } }));
    expect(res.status).toBe(204);
    expect(res.headers.get("access-control-allow-origin")).toBe(ORIGEN);
    expect(res.headers.get("access-control-allow-methods")).toBe("GET, POST, OPTIONS");
    expect(res.headers.get("access-control-allow-headers")).toBe("authorization, content-type");
  });

  it("otro origen o sin origen: 403 sin cabeceras CORS, y no se llama a Whisper", async () => {
    const m = montar();
    for (const origen of ["https://evil.example", "http://dcasapty.com", null]) {
      const res = await m.pedir(await nota(undefined, { origen: origen as string | null }));
      expect(res.status).toBe(403);
      expect(res.headers.get("access-control-allow-origin")).toBeNull();
    }
    expect((m.ai as { run: ReturnType<typeof vi.fn> }).run).not.toHaveBeenCalled();
  });

  it("sin pase, vencido o falsificado: 401 «pase», y no se lee ni se transcribe nada", async () => {
    const m = montar();
    for (const autorizacion of ["", "Pase nada", "Bearer x", `Pase ${await firmarPase("otro-token-0123456789abcdef0123456789", { v: 1, sid: SID, exp: Math.floor(AHORA / 1000) + 600, sitio: 1 })}`]) {
      const res = await m.pedir(await nota(undefined, { autorizacion }));
      expect(res.status).toBe(401);
      expect(await leer(res)).toEqual({ ok: false, motivo: "pase" });
    }
    expect((m.ai as { run: ReturnType<typeof vi.fn> }).run).not.toHaveBeenCalled();
    expect(m.global.reservarVozTienda).not.toHaveBeenCalled();
  });

  it("GET dice si se muestra el micrófono (sin pase, sin nada más)", async () => {
    const get = (m: ReturnType<typeof montar>) => m.pedir(new Request(URL_VOZ, { headers: { origin: ORIGEN } }));
    const res = await get(montar());
    expect(res.status).toBe(200);
    expect(res.headers.get("access-control-allow-origin")).toBe(ORIGEN);
    expect(await leer(res)).toEqual({ ok: true, disponible: true, max_segundos: 60, max_bytes: MAX_BYTES_VOZ, tipos: ["audio/webm", "audio/ogg", "audio/mp4"] });
    expect((await leer(await get(montar({ bandera: "0" })))).disponible).toBe(false);
    expect((await leer(await get(montar({ ai: null })))).disponible).toBe(false);
    expect((await leer(await get(montar({ config: normalizarConfig({ brian_tienda: { activo: false } }) })))).disponible).toBe(false);
  });
});

describe("una nota de voz: solo el texto de vuelta", () => {
  it("200 {ok, texto, recortado} y nada más: ni audio, ni segmentos, ni palabras, ni VTT", async () => {
    const m = montar();
    const res = await m.pedir(await nota());
    expect(res.status).toBe(200);
    expect(res.headers.get("cache-control")).toBe("no-store");
    expect(res.headers.get("access-control-allow-origin")).toBe(ORIGEN);
    const cuerpo = await leer(res);
    expect(cuerpo).toEqual({ ok: true, texto: DICHO, recortado: false });
    expect(Object.keys(cuerpo).sort()).toEqual(["ok", "recortado", "texto"]);
  });

  it("solo se llama a Whisper, una vez; el audio nunca llega al Durable Object de la sesión", async () => {
    const m = montar();
    await m.pedir(await nota());
    const run = (m.ai as { run: ReturnType<typeof vi.fn> }).run;
    expect(run).toHaveBeenCalledTimes(1);
    expect(run.mock.calls[0][0]).toBe(MODELO_WHISPER);
    expect(m.sesiones).toEqual([]);
  });

  it("nada del audio ni del texto en los registros (ni la IP ni el sid)", async () => {
    const lineas: string[] = [];
    for (const nivel of ["log", "info", "warn", "error", "debug"] as const) vi.spyOn(console, nivel).mockImplementation((...a: unknown[]) => void lineas.push(a.map(String).join(" ")));
    const m = montar();
    const audio = webmOpus(4);
    const huella = aBase64(audio).slice(0, 40);
    await m.pedir(await nota(audio));
    await m.pedir(await nota(webmOpus(70), { duracion: "4000" }));
    const todo = lineas.join("\n");
    expect(lineas.length).toBeGreaterThan(0);
    for (const prohibido of [DICHO, "Busco", huella, "190.140.12", SID]) expect(todo).not.toContain(prohibido);
  });

  it("el costo va al gasto de la tienda (renglón de la voz, proveedor cloudflare) con la duración que dice Whisper", async () => {
    const m = montar({ duracion: 6 });
    await m.pedir(await nota(webmOpus(6)));
    const g = m.topes.gastoMes("2026-11", "2026-11-16", AHORA);
    expect(g.porModelo).toEqual([{ proveedor: "cloudflare", modelo: MODELO_DE_LA_VOZ, usd: costoDeLaVoz(6), turnos: 1, estimado: false }]);
    expect(g.enVueloUsd).toBe(0);
    // Y cuenta como un mensaje en el día de la tienda.
    expect(g.turnosHoy).toBe(1);
  });

  it("un texto más largo que lo que acepta el chat (500 letras) vuelve recortado y lo dice", async () => {
    const m = montar({ texto: "quiero una cama ".repeat(60), duracion: 55 });
    const cuerpo = await leer(await m.pedir(await nota(webmOpus(55), { duracion: "55000" })));
    expect(cuerpo.recortado).toBe(true);
    expect([...cuerpo.texto].length).toBeLessThanOrEqual(500);
  });

  it("Ogg (Firefox) y MP4 (Safari) también", async () => {
    for (const [audio, tipo] of [[oggOpus(3), "audio/ogg;codecs=opus"], [mp4(3), "audio/mp4"], [mp4(0), "audio/mp4"]] as const) {
      const res = await montar().pedir(await nota(audio, { tipo }));
      expect(res.status).toBe(200);
    }
  });
});

describe("lo que se rechaza antes de gastar", () => {
  it("tipo no permitido (415), firma distinta (400), vacío (400), pesado (413), más de un minuto (413): sin Whisper y sin apartar", async () => {
    const casos: [Uint8Array, string, number, string, string?][] = [
      [webmOpus(3), "audio/wav", 415, "tipo"],
      [webmOpus(3), "text/plain", 415, "tipo"],
      [oggOpus(3), "audio/webm", 400, "audio"],
      [new Uint8Array(0), "audio/webm", 400, "audio"],
      [new Uint8Array(MAX_BYTES_VOZ + 10), "audio/webm", 413, "muy_pesada"],
      [webmOpus(70), "audio/webm", 413, "muy_larga"],
      [oggOpus(3), "audio/ogg", 413, "muy_larga", "90000"],
    ];
    for (const [audio, tipo, status, motivo, duracion] of casos) {
      const m = montar();
      const res = await m.pedir(await nota(audio, { tipo, duracion }));
      expect([res.status, await leer(res)]).toEqual([status, { ok: false, motivo }]);
      expect((m.ai as { run: ReturnType<typeof vi.fn> }).run).not.toHaveBeenCalled();
      expect(m.global.reservarVozTienda).not.toHaveBeenCalled();
    }
  });

  it("la tienda apagada: 503 «apagado»; la transcripción apagada o sin binding: 503 «no_disponible»", async () => {
    const apagada = montar({ config: normalizarConfig({ brian_tienda: { activo: false } }) });
    expect([(await apagada.pedir(await nota())).status, apagada.global.reservarVozTienda.mock.calls.length]).toEqual([503, 0]);
    for (const m of [montar({ bandera: "0" }), montar({ ai: null })]) {
      const res = await m.pedir(await nota());
      expect([res.status, await leer(res)]).toEqual([503, { ok: false, motivo: "no_disponible" }]);
      expect(m.global.reservarVozTienda).not.toHaveBeenCalled();
    }
  });

  it("si Whisper dice que duró más de un minuto: 413 y el texto NO sale (pero se cobra)", async () => {
    const m = montar({ duracion: 240 });
    const res = await m.pedir(await nota(mp4(0), { tipo: "audio/mp4" }));
    expect([res.status, await leer(res)]).toEqual([413, { ok: false, motivo: "muy_larga" }]);
    expect(m.topes.gastoMes("2026-11", "2026-11-16", AHORA).usd).toBeCloseTo(costoDeLaVoz(240), 10);
  });

  it("no se entendió: 422; Whisper falla: 502; tarda: 504", async () => {
    expect((await montar({ texto: "  " }).pedir(await nota())).status).toBe(422);
    expect((await montar({ ai: { run: async () => Promise.reject(new Error("x")) } }).pedir(await nota())).status).toBe(502);
    const lento = montar({ ai: { run: () => new Promise(() => {}) } });
    const res = await manejarTienda("/tienda/v1/voz", await nota(), lento.env, lento.d, { voz: { global: lento.global, plazoMs: 20 } });
    expect([res.status, await leer(res)]).toEqual([504, { ok: false, motivo: "tardo" }]);
  });
});

describe("los topes y el presupuesto de la tienda", () => {
  it("tope por sesión (el de mensajes por hora): 429 con Retry-After", async () => {
    const m = montar({ config: normalizarConfig({ brian_tienda: { activo: true, tope_sesion_hora: 2 } }) });
    expect((await m.pedir(await nota())).status).toBe(200);
    expect((await m.pedir(await nota())).status).toBe(200);
    const res = await m.pedir(await nota());
    expect([res.status, await leer(res)]).toEqual([429, { ok: false, motivo: "tope_sesion" }]);
    expect(Number(res.headers.get("retry-after"))).toBeGreaterThan(0);
    expect(res.headers.get("access-control-expose-headers")).toBe("retry-after");
  });

  it("tope por red y del día: 429; el presupuesto agotado: 429 «presupuesto» (Whisper no se llama)", async () => {
    const red = montar({ config: normalizarConfig({ brian_tienda: { activo: true, tope_red_hora: 1 } }) });
    await red.pedir(await nota());
    const r1 = await red.pedir(await nota());
    expect([r1.status, await leer(r1), r1.headers.get("retry-after")]).toEqual([429, { ok: false, motivo: "tope_red" }, "900"]);
    const dia = montar({ config: normalizarConfig({ brian_tienda: { activo: true, tope_dia: 1 } }) });
    await dia.pedir(await nota());
    const r2 = await dia.pedir(await nota(undefined, { ip: "200.1.2.3" }));
    expect([r2.status, await leer(r2)]).toEqual([429, { ok: false, motivo: "tope_dia" }]);
    const sinPlata = montar({ config: normalizarConfig({ brian_tienda: { activo: true, presupuesto_mes_usd: 0 } }) });
    const r3 = await sinPlata.pedir(await nota());
    expect([r3.status, await leer(r3)]).toEqual([429, { ok: false, motivo: "presupuesto" }]);
    expect((sinPlata.ai as { run: ReturnType<typeof vi.fn> }).run).not.toHaveBeenCalled();
  });

  it("sin el contador Global no se sabe si cabe: falla cerrado (502) sin llamar a Whisper", async () => {
    const m = montar();
    m.global.reservarVozTienda.mockRejectedValueOnce(new Error("Global caído"));
    const res = await m.pedir(await nota());
    expect([res.status, await leer(res)]).toEqual([502, { ok: false, motivo: "fallo" }]);
    expect((m.ai as { run: ReturnType<typeof vi.fn> }).run).not.toHaveBeenCalled();
  });

  it("la red y la sesión llegan al contador ofuscadas (ni la IP ni el sid en claro)", async () => {
    const m = montar();
    await m.pedir(await nota(undefined, { ip: "2001:db8:1:2:3:4:5:6" }));
    const p = m.global.reservarVozTienda.mock.calls[0][0];
    expect(JSON.stringify(p)).not.toContain("2001");
    expect(JSON.stringify(p)).not.toContain(SID);
    expect(p.red).toMatch(/^[0-9a-f]{32}$/);
    expect(p.red48).toMatch(/^[0-9a-f]{32}$/);
    expect(p.sesion).toMatch(/^[0-9a-f]{32}$/);
  });
});
