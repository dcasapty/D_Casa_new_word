/**
 * `POST /odoo/voz` (Brian del panel) por el enrutador de verdad: solo con el token de Odoo, solo el texto de vuelta, topes por usuario
 * y por día, el techo del mes y el gasto en su propio renglón de Cloudflare (aparte del de Juan). El contador es el de verdad.
 */
import { readFileSync } from "node:fs";
import { afterEach, describe, expect, it, vi } from "vitest";
import { normalizarConfig } from "../src/config";
import type { Env } from "../src/env";
import { AlmacenGlobal } from "../src/motor/global";
import { USO_VACIO } from "../src/motor/precios";
import { MODELO_WHISPER } from "../src/motor/transcribir";
import { costoDeLaVoz, MAX_BYTES_VOZ, MAX_SEGUNDOS_VOZ, PLAZO_VOZ_MS, TIPOS_DE_AUDIO } from "../src/motor/voz";
import { CONCEPTO_DEL_GASTO, TOPE_POR_USUARIO_HORA } from "../src/odoo-panel-voz";
import { manejar, type DepsRutas } from "../src/rutas";
import { aBase64, oggOpus, webmOpus } from "./helpers/audio";
import { crearSqlNode } from "./helpers/sqlNode";

const TOKEN = "token-del-worker-de-prueba-0123456789abcdef";
const AHORA = Date.UTC(2026, 10, 16, 16, 0);
const URL_VOZ = "https://dcasa-juan.dcasapty.workers.dev/odoo/voz";
const DICHO = "Brian, dime cuántas cotizaciones quedaron abiertas esta semana";

afterEach(() => vi.restoreAllMocks());

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const leer = async (res: Response) => (await res.json()) as Record<string, any>;

function montar(op: { ai?: { run: (...a: unknown[]) => Promise<unknown> } | null; bandera?: string; texto?: string; duracion?: number } = {}) {
  const almacen = new AlmacenGlobal(crearSqlNode());
  const ai = op.ai === null ? undefined : (op.ai ?? { run: vi.fn(async () => ({ text: op.texto ?? DICHO, transcription_info: { duration: op.duracion ?? 5 }, segments: [{ end: 5 }], vtt: "WEBVTT" })) });
  const env = {
    JUAN_WORKER_TOKEN: TOKEN,
    TRANSCRIBIR_AUDIO: op.bandera ?? "1",
    ...(ai ? { AI: ai } : {}),
    GLOBAL: {
      idFromName: () => ({}),
      get: () => ({
        reservarVozPanel: async (p: Parameters<AlmacenGlobal["reservarVozPanel"]>[0]) => almacen.reservarVozPanel(p, AHORA),
        registrarGasto: async (...a: Parameters<AlmacenGlobal["registrarGasto"]>) => almacen.registrarGasto(...a),
      }),
    },
  } as unknown as Env;
  const config = normalizarConfig({});
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
  return { env, d, ai, almacen, pedir: (req: Request) => manejar(req, env, d) };
}

const pedido = (cuerpo: Record<string, unknown>, token: string | null = TOKEN) =>
  new Request(URL_VOZ, { method: "POST", headers: { "content-type": "application/json", ...(token ? { authorization: `Bearer ${token}` } : {}) }, body: JSON.stringify(cuerpo) });
const nota = (extra: Record<string, unknown> = {}) => ({ mime: "audio/webm;codecs=opus", base64: aBase64(webmOpus(5)), usuario: 7, duracion_ms: 5100, ...extra });

describe("POST /odoo/voz", () => {
  it("sin el token de Odoo (o con otro): 401 y no se transcribe nada", async () => {
    const m = montar();
    for (const token of [null, "otro-token-0123456789abcdef0123456789"]) expect((await m.pedir(pedido(nota(), token))).status).toBe(401);
    expect((m.ai as { run: ReturnType<typeof vi.fn> }).run).not.toHaveBeenCalled();
  });

  it("200 con SOLO el texto (ni audio, ni segmentos, ni VTT) y solo se llama a Whisper", async () => {
    const m = montar();
    const res = await m.pedir(pedido(nota()));
    expect(res.status).toBe(200);
    expect(res.headers.get("cache-control")).toBe("no-store");
    const cuerpo = await leer(res);
    expect(cuerpo).toEqual({ ok: true, texto: DICHO, recortado: false });
    const run = (m.ai as { run: ReturnType<typeof vi.fn> }).run;
    expect(run).toHaveBeenCalledTimes(1);
    expect(run.mock.calls[0][0]).toBe(MODELO_WHISPER);
  });

  it("el gasto va en su renglón de Cloudflare: no suma en el de Juan ni en sus turnos", async () => {
    const m = montar({ duracion: 30 });
    await m.pedir(pedido(nota({ base64: aBase64(oggOpus(30)), mime: "audio/ogg" })));
    const g = m.almacen.gastoMes("2026-11");
    expect(g.usd).toBe(0);
    expect(g.turnos).toBe(0);
    expect(g.cloudflare).toEqual([{ concepto: CONCEPTO_DEL_GASTO, usd: costoDeLaVoz(30), lecturas: 1, estimado: false }]);
  });

  it("nada del audio ni del texto ni del usuario en los registros", async () => {
    const lineas: string[] = [];
    for (const nivel of ["log", "info", "warn", "error", "debug"] as const) vi.spyOn(console, nivel).mockImplementation((...a: unknown[]) => void lineas.push(a.map(String).join(" ")));
    const m = montar();
    const audio = aBase64(webmOpus(5));
    await m.pedir(pedido(nota({ base64: audio, usuario: "usuario-raro-42" })));
    await m.pedir(pedido(nota({ base64: aBase64(webmOpus(80)) })));
    const todo = lineas.join("\n");
    expect(lineas.length).toBeGreaterThan(0);
    for (const prohibido of [DICHO, "cotizaciones", audio.slice(0, 40), "usuario-raro-42"]) expect(todo).not.toContain(prohibido);
  });

  it("rechaza sin gastar: tipo (415), base64 roto (400), firma (400), pesada (413), más de un minuto (413)", async () => {
    const casos: [Record<string, unknown>, number, string][] = [
      [nota({ mime: "audio/wav" }), 415, "tipo"],
      [nota({ base64: "no es base64!" }), 400, "audio"],
      [nota({ base64: aBase64(oggOpus(3)) }), 400, "audio"],
      [nota({ base64: aBase64(new Uint8Array(MAX_BYTES_VOZ + 3)) }), 413, "muy_pesada"],
      [nota({ base64: aBase64(webmOpus(75)) }), 413, "muy_larga"],
      [nota({ duracion_ms: 120_000 }), 413, "muy_larga"],
    ];
    for (const [cuerpo, status, causa] of casos) {
      const m = montar();
      const res = await m.pedir(pedido(cuerpo));
      const r = await leer(res);
      expect([res.status, r.causa]).toEqual([status, causa]);
      expect(JSON.stringify(r)).not.toContain(String(cuerpo.base64).slice(0, 30));
      expect((m.ai as { run: ReturnType<typeof vi.fn> }).run).not.toHaveBeenCalled();
    }
  });

  it("apagado (sin TRANSCRIBIR_AUDIO o sin binding): 503 no_disponible", async () => {
    for (const m of [montar({ bandera: "0" }), montar({ ai: null })]) {
      const res = await m.pedir(pedido(nota()));
      expect([res.status, (await leer(res)).causa]).toEqual([503, "no_disponible"]);
    }
  });

  it("tope por usuario por hora (429 con reintentar_en); otro usuario sigue pudiendo", async () => {
    const m = montar();
    for (let i = 0; i < TOPE_POR_USUARIO_HORA; i++) expect((await m.pedir(pedido(nota()))).status).toBe(200);
    const res = await m.pedir(pedido(nota()));
    const r = await leer(res);
    expect([res.status, r.causa]).toEqual([429, "tope_usuario"]);
    expect(r.reintentar_en).toBeGreaterThan(0);
    expect((await m.pedir(pedido(nota({ usuario: 8 })))).status).toBe(200);
  });

  it("el techo del mes: 429 tope_mes (de fábrica 5 USD; Odoo puede mandar otro, 0 = apagado)", async () => {
    const m = montar();
    m.almacen.registrarGasto("2026-11", CONCEPTO_DEL_GASTO, USO_VACIO, 5, false);
    expect((await leer(await m.pedir(pedido(nota())))).causa).toBe("tope_mes");
    expect((await m.pedir(pedido(nota({ tope_mes_usd: 10 })))).status).toBe(200);
    expect((await leer(await montar().pedir(pedido(nota({ tope_mes_usd: 0 }))))).causa).toBe("tope_mes");
    expect((await montar().pedir(pedido(nota({ tope_mes_usd: -1 })))).status).toBe(400);
  });

  it("si Whisper dice más de un minuto, el texto no sale (pero se cobra); no entendido: 422", async () => {
    const largo = montar({ duracion: 200 });
    const r = await largo.pedir(pedido(nota()));
    expect([r.status, (await leer(r)).causa]).toEqual([413, "muy_larga"]);
    expect(largo.almacen.gastoMes("2026-11").cloudflare[0].usd).toBeCloseTo(costoDeLaVoz(200), 10);
    expect((await montar({ texto: "" }).pedir(pedido(nota()))).status).toBe(422);
  });

  it("solo POST", async () => {
    const m = montar();
    expect((await m.pedir(new Request(URL_VOZ, { headers: { authorization: `Bearer ${TOKEN}` } }))).status).toBe(405);
  });

  it("Odoo espera, con margen, lo que tarda el Worker (TIMEOUT_VOZ) y valida los mismos tipos y topes (dcasa_brian/models/voz.py)", () => {
    const puente = readFileSync(new URL("../../addons/dcasa_conversaciones/models/brian_voz.py", import.meta.url), "utf8");
    const m = /^TIMEOUT_VOZ\s*=\s*\(\s*[\d.]+\s*,\s*([\d.]+)\s*\)/m.exec(puente);
    expect(m, "brian_voz.py define TIMEOUT_VOZ = (conectar, leer)").not.toBeNull();
    expect(Number(m![1]) * 1000).toBeGreaterThanOrEqual(PLAZO_VOZ_MS + 5000);
    const reglas = readFileSync(new URL("../../addons/dcasa_brian/models/voz.py", import.meta.url), "utf8");
    expect(/^TIPOS = \(([^)]*)\)/m.exec(reglas)?.[1].match(/audio\/\w+/g)).toEqual([...TIPOS_DE_AUDIO]);
    expect(Number(/^MAX_BYTES = 1024 \* 1024$/m.test(reglas) ? 1024 * 1024 : NaN)).toBe(MAX_BYTES_VOZ);
    expect(Number(/^MAX_SEGUNDOS = (\d+)$/m.exec(reglas)?.[1])).toBe(MAX_SEGUNDOS_VOZ);
  });
});
