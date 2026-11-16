/**
 * Revisión adversarial de las notas de voz (rama local/voz). Cada prueba demuestra un hallazgo; con el arreglo (medir la duración
 * que de verdad se decodifica, motor/duracion.ts, y la reserva de voz con vida corta) todas pasan. Dos se adaptaron sin aflojarlas:
 * la 1a medía un «peor caso» que ya no existe (ahora se exige que lo apartado cubra lo que de verdad dura) y la 1c esperaba que la
 * nota de 11 horas llegara a Whisper (ahora se exige que NO llegue, y el caso de Whisper lento se prueba con una nota permitida).
 *
 *  1. El «peor caso» de 6 kbps no es el peor caso: un Ogg Opus válido de 1 MB (paquetes de 2 bytes = 120 ms cada uno) dura
 *     11 h 14 min. ffmpeg (lo que usa Whisper para decodificar) lo decodifica entero aunque la última página mienta «10 s».
 *     El tope de 65 s no se mira antes de Whisper y, si Whisper tarda o falla, se anota 1/29 de lo que cuesta de verdad.
 *  2. Una nota de voz cuyo Worker se cancela (el visitante corta la conexión: Cloudflare cancela todo lo que no esté en
 *     waitUntil) nunca cierra su reserva: el lugar «en vuelo» queda ocupado 3 minutos (VIDA_DE_UNA_RESERVA_MS), no 20 s.
 *     Cuatro redes bastan para dejar el chat de la tienda en «ocupado» para todos.
 */
import { describe, expect, it, vi } from "vitest";
import { normalizarConfig } from "../src/config";
import type { Env } from "../src/env";
import { TopesDeLaTienda, type ReservaVozTienda } from "../src/motor/global";
import { costoDeLaVoz, duracionDelContenedor, MAX_BYTES_VOZ, PLAZO_VOZ_MS, reservaDeLaNota, validarNota, esProblema } from "../src/motor/voz";
import type { DepsRutas } from "../src/rutas";
import { firmarPase } from "../src/tienda/pase";
import { manejarTienda } from "../src/tienda/rutas";
import { crearSqlNode } from "./helpers/sqlNode";

// ── Un Ogg Opus mínimo y válido (con CRC), como el que arma scripts/ogg_dtx.py y decodifica ffmpeg ──────────────
const TABLA = (() => {
  const t = new Uint32Array(256);
  for (let i = 0; i < 256; i++) {
    let r = i << 24;
    for (let k = 0; k < 8; k++) r = r & 0x80000000 ? (r << 1) ^ 0x04c11db7 : r << 1;
    t[i] = r >>> 0;
  }
  return t;
})();
function crc(b: Uint8Array): number {
  let c = 0;
  for (const x of b) c = ((c << 8) ^ TABLA[((c >>> 24) ^ x) & 0xff]) >>> 0;
  return c >>> 0;
}
function pagina(paquetes: Uint8Array[], granulo: bigint, seq: number, tipo = 0): Uint8Array {
  const lacing: number[] = [];
  for (const p of paquetes) {
    for (let n = p.length; n >= 255; n -= 255) lacing.push(255);
    lacing.push(p.length % 255);
  }
  const cuerpo = paquetes.reduce((n, p) => n + p.length, 0);
  const out = new Uint8Array(27 + lacing.length + cuerpo);
  const v = new DataView(out.buffer);
  out.set([0x4f, 0x67, 0x67, 0x53, 0, tipo]);
  v.setBigInt64(6, granulo, true);
  v.setUint32(14, 0x1234, true);
  v.setUint32(18, seq, true);
  out[26] = lacing.length;
  out.set(lacing, 27);
  let pos = 27 + lacing.length;
  for (const p of paquetes) {
    out.set(p, pos);
    pos += p.length;
  }
  v.setUint32(22, crc(out), true);
  return out;
}
const ascii = (s: string) => [...s].map((c) => c.charCodeAt(0));

/** `{bytes, segundosReales}`: paquetes code 3 (TOC 0xFB: CELT FB 20 ms × 6 tramas vacías = 120 ms), 255 por página. */
function oggDeHoras(maxBytes: number, mentirSegundos: number | null): { bytes: Uint8Array; segundosReales: number } {
  const head = new Uint8Array([...ascii("OpusHead"), 1, 1, 0x38, 0x01, 0x80, 0xbb, 0, 0, 0, 0, 0]);
  const tags = new Uint8Array([...ascii("OpusTags"), 4, 0, 0, 0, ...ascii("rvvz"), 0, 0, 0, 0]);
  const partes = [pagina([head], 0n, 0, 2), pagina([tags], 0n, 1)];
  let total = partes.reduce((n, p) => n + p.length, 0);
  const paquete = new Uint8Array([(31 << 3) | 3, 6]);
  const tamPagina = 27 + 255 + 255 * 2;
  let granulo = 0n;
  let paquetes = 0;
  for (let seq = 2; total + tamPagina <= maxBytes; seq++) {
    granulo += 255n * 5760n;
    paquetes += 255;
    const p = pagina(new Array(255).fill(paquete), mentirSegundos === null ? granulo : BigInt(Math.round(mentirSegundos * 48_000)), seq);
    partes.push(p);
    total += p.length;
  }
  const bytes = new Uint8Array(total);
  let pos = 0;
  for (const p of partes) {
    bytes.set(p, pos);
    pos += p.length;
  }
  return { bytes, segundosReales: paquetes * 0.12 };
}

// ── La ruta de la tienda, como en test/tienda/voz.test.ts ─────────────────────────────────────────────────
const TOKEN = "token-del-worker-de-prueba-0123456789abcdef";
const AHORA = Date.UTC(2026, 10, 16, 16, 0);
const SID = "AAECAwQFBgcICQoLDA0ODw";
const URL_VOZ = "https://dcasa-juan.dcasapty.workers.dev/tienda/v1/voz";

describe("hallazgo 1: el «peor caso» de 6 kbps no es el peor caso", () => {
  it("un Ogg Opus válido de 1 MB dura 11 horas: el contenedor honesto lo dice y el peor caso apartado es 29 veces menos", () => {
    const { bytes, segundosReales } = oggDeHoras(MAX_BYTES_VOZ, null);
    expect(bytes.byteLength).toBeLessThanOrEqual(MAX_BYTES_VOZ);
    // Nuestro propio lector del contenedor está de acuerdo en que es Ogg Opus de 11 horas (ffmpeg también: 40 483,79 s).
    expect(duracionDelContenedor(bytes, "audio/ogg")).toBeCloseTo(segundosReales - 312 / 48_000, 1);
    // Lo que se aparta / se cobra si Whisper tarda o falla sale de esa duración medida: cubre lo que dura (antes: 1397 s contra 40 484 s).
    const medida = duracionDelContenedor(bytes, "audio/ogg");
    expect(medida).not.toBeNull();
    expect(reservaDeLaNota({ segundos: medida! })).toBeGreaterThanOrEqual(costoDeLaVoz(segundosReales) * 0.99);
  });

  it("con la última página mintiendo «10 s», la nota de 11 horas pasa la validación y llega a Whisper", () => {
    const { bytes } = oggDeHoras(MAX_BYTES_VOZ, 10);
    const nota = validarNota(bytes, "audio/ogg", null);
    // Se esperaba «muy_larga» antes de llamar a Whisper (la duración de verdad está en los paquetes, sin decodificar).
    expect(esProblema(nota) ? nota.motivo : "aceptada").toBe("muy_larga");
  });

  it("la ruta: la nota de 11 horas (que dice «10 s») ni llega a Whisper ni aparta nada; una permitida que miente y tarda se cobra entera", async () => {
    const { bytes } = oggDeHoras(MAX_BYTES_VOZ, 10);
    const sql = crearSqlNode();
    const topes = new TopesDeLaTienda(sql);
    const ai = { run: vi.fn(() => new Promise(() => {})) }; // 11 horas de audio: no termina dentro del plazo
    const env = { JUAN_WORKER_TOKEN: TOKEN, TRANSCRIBIR_AUDIO: "1", AI: ai } as unknown as Env;
    const config = normalizarConfig({ brian_tienda: { activo: true } });
    const d = { config: async () => config, ahora: () => AHORA } as unknown as DepsRutas;
    const global = {
      reservarVozTienda: async (p: ReservaVozTienda) => topes.reservarVoz(p, AHORA),
      cerrarTurnoTienda: async (id: number, g: Parameters<TopesDeLaTienda["cerrar"]>[1]) => topes.cerrar(id, g),
    };
    const pase = await firmarPase(TOKEN, { v: 1, sid: SID, exp: Math.floor(AHORA / 1000) + 1800, sitio: 1 });
    const req = new Request(URL_VOZ, {
      method: "POST",
      headers: { origin: "https://dcasapty.com", authorization: `Pase ${pase}`, "content-type": "audio/ogg;codecs=opus", "cf-connecting-ip": "190.140.12.34" },
      body: bytes,
    });
    const res = await manejarTienda("/tienda/v1/voz", req, env, d, { voz: { global, plazoMs: 30 } });
    expect(res.status).toBe(413);
    expect(ai.run).not.toHaveBeenCalled();
    expect(topes.gastoMes("2026-11", "2026-11-16", AHORA)).toMatchObject({ usd: 0, enVueloUsd: 0, turnosHoy: 0 });

    // Una nota permitida (25 s de verdad, en paquetes de 120 ms) cuya última página dice «2 s», y Whisper tarda: se anota lo que de
    // verdad decodifica Whisper (25 s), no lo que dice el archivo ni un mínimo.
    const head = new Uint8Array([...ascii("OpusHead"), 1, 1, 0x38, 0x01, 0x80, 0xbb, 0, 0, 0, 0, 0]);
    const tags = new Uint8Array([...ascii("OpusTags"), 4, 0, 0, 0, ...ascii("rvvz"), 0, 0, 0, 0]);
    const paquetes = Math.round(25 / 0.12);
    const partes = [pagina([head], 0n, 0, 2), pagina([tags], 0n, 1), pagina(new Array(paquetes).fill(new Uint8Array([(31 << 3) | 3, 6])), 2n * 48_000n, 2, 4)];
    const corta = new Uint8Array(partes.reduce((n, p) => n + p.length, 0));
    let pos = 0;
    for (const p of partes) {
      corta.set(p, pos);
      pos += p.length;
    }
    const pase2 = await firmarPase(TOKEN, { v: 1, sid: "AAECAwQFBgcICQoLDA0OEA", exp: Math.floor(AHORA / 1000) + 1800, sitio: 1 });
    const req2 = new Request(URL_VOZ, {
      method: "POST",
      headers: { origin: "https://dcasapty.com", authorization: `Pase ${pase2}`, "content-type": "audio/ogg;codecs=opus", "cf-connecting-ip": "190.140.12.35" },
      body: corta,
    });
    const res2 = await manejarTienda("/tienda/v1/voz", req2, env, d, { voz: { global, plazoMs: 30 } });
    expect(res2.status).toBe(504);
    const anotado = topes.gastoMes("2026-11", "2026-11-16", AHORA).usd;
    expect(anotado).toBeGreaterThanOrEqual(costoDeLaVoz(paquetes * 0.12 - 312 / 48_000) * 0.99);
  });
});

describe("hallazgo 1b: con esas notas, 90 peticiones de 2 conexiones apagan a Andrés el resto del mes", () => {
  it("Whisper termina y dice la duración (11 h): cada nota se cobra US$0.34 y el presupuesto de US$30 se acaba", async () => {
    const { bytes, segundosReales } = oggDeHoras(MAX_BYTES_VOZ, 10);
    const topes = new TopesDeLaTienda(crearSqlNode());
    // Lo que contestaría Whisper si alcanza: «no entendí nada» (silencio) y la duración real que decodificó.
    const ai = { run: vi.fn(async () => ({ text: "", transcription_info: { duration: segundosReales } })) };
    const env = { JUAN_WORKER_TOKEN: TOKEN, TRANSCRIBIR_AUDIO: "1", AI: ai } as unknown as Env;
    const config = normalizarConfig({ brian_tienda: { activo: true } });
    const d = { config: async () => config, ahora: () => AHORA } as unknown as DepsRutas;
    const global = {
      reservarVozTienda: async (p: ReservaVozTienda) => topes.reservarVoz(p, AHORA),
      cerrarTurnoTienda: async (id: number, g: Parameters<TopesDeLaTienda["cerrar"]>[1]) => topes.cerrar(id, g),
    };
    let enviadas = 0;
    for (let i = 0; i < 90; i++) {
      const sid = `AAECAwQFBgcICQoLDA0O${String(i % 10).padStart(2, "0")}`;
      const pase = await firmarPase(TOKEN, { v: 1, sid, exp: Math.floor(AHORA / 1000) + 1800, sitio: 1 });
      const req = new Request(URL_VOZ, {
        method: "POST",
        headers: { origin: "https://dcasapty.com", authorization: `Pase ${pase}`, "content-type": "audio/ogg", "cf-connecting-ip": i < 45 ? "190.140.12.34" : "201.218.1.9" },
        body: bytes.slice(),
      });
      const res = await manejarTienda("/tienda/v1/voz", req, env, d, { voz: { global } });
      if (res.status !== 429) enviadas++;
    }
    expect(enviadas).toBeGreaterThan(80);
    // Una clienta de verdad, desde otra conexión: su mensaje ya no cabe en el presupuesto del mes.
    const clienta = topes.reservar(
      { red: "otra-red", dia: "2026-11-16", mes: "2026-11", porRed: 60, porDia: 1000, presupuestoUsd: config.tienda.presupuesto_mes_usd, proveedor: "anthropic", reservaUsd: 0.02 },
      AHORA,
    );
    expect(clienta).toMatchObject({ ok: true });
  }, 120_000);
});

describe("hallazgo 2: una nota cortada a medias ocupa un lugar «en vuelo» 3 minutos", () => {
  it("8 notas de 4 redes que nunca se cierran (el visitante cortó) dejan el chat en «ocupado» un minuto después", () => {
    const topes = new TopesDeLaTienda(crearSqlNode());
    const base = { dia: "2026-11-16", mes: "2026-11", porRed: 60, porDia: 1000, porRedDia: 50, enVueloMax: 8, enVueloRed: 2, presupuestoUsd: 30 };
    for (let red = 0; red < 4; red++) {
      for (let i = 0; i < 2; i++) {
        const r = topes.reservarVoz({ ...base, red: `red-atacante-${red}`, sesion: `s-${red}-${i}`, porSesion: 20, proveedor: "cloudflare", reservaUsd: 0.0116 }, AHORA);
        expect(r.ok).toBe(true);
        // …y el Worker se cancela: el `finally` de tienda/voz.ts (cerrarTurnoTienda) nunca corre.
      }
    }
    // Ninguna nota legítima dura más que PLAZO_VOZ_MS (20 s): un minuto después esos lugares deberían estar libres.
    const despues = AHORA + 3 * PLAZO_VOZ_MS;
    const cliente = topes.reservar({ ...base, red: "red-de-una-clienta", proveedor: "anthropic", reservaUsd: 0.02 }, despues);
    expect(cliente).toMatchObject({ ok: true });
  });
});
