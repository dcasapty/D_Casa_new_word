/**
 * Las notas de voz (motor/voz.ts): solo los tipos que graba un navegador, la duración en tres lugares (el navegador, el contenedor y
 * Whisper), solo el texto de vuelta y el audio borrado de la memoria al terminar. Nada de esto guarda el audio en ningún lado.
 */
import { describe, expect, it, vi } from "vitest";
import type { Env } from "../src/env";
import { MODELO_WHISPER } from "../src/motor/transcribir";
import {
  costoDeLaVoz,
  duracionDeclarada,
  duracionDelContenedor,
  esProblema,
  firmaDeAudio,
  leerConTope,
  MAX_BYTES_VOZ,
  peorDuracion,
  PRECIO_WHISPER_USD_POR_MINUTO,
  reservaDeLaNota,
  textoDeLaNota,
  tipoDeAudio,
  transcribirNota,
  validarNota,
  type NotaDeVoz,
} from "../src/motor/voz";
import { mp4, oggOpus, webmOpus } from "./helpers/audio";

const envCon = (ai: unknown, bandera = "1") => ({ AI: ai, TRANSCRIBIR_AUDIO: bandera }) as unknown as Env;
const nota = (bytes: Uint8Array, tipo: NotaDeVoz["tipo"] = "audio/webm", segundos: number | null = null): NotaDeVoz => ({ bytes, tipo, segundos });

describe("tipos y firma: solo lo que graba un navegador", () => {
  it("acepta WebM, Ogg y MP4 (con o sin codecs) y nada más", () => {
    expect(tipoDeAudio("audio/webm;codecs=opus")).toBe("audio/webm");
    expect(tipoDeAudio("Audio/Ogg; codecs=opus")).toBe("audio/ogg");
    expect(tipoDeAudio("audio/mp4")).toBe("audio/mp4");
    for (const malo of ["audio/wav", "audio/mpeg", "video/webm", "application/octet-stream", "text/plain", "", null, undefined]) expect(tipoDeAudio(malo)).toBeNull();
  });

  it("los bytes tienen que decir lo mismo que el tipo", () => {
    expect(firmaDeAudio(webmOpus(3), "audio/webm")).toBe(true);
    expect(firmaDeAudio(oggOpus(3), "audio/ogg")).toBe(true);
    expect(firmaDeAudio(mp4(3), "audio/mp4")).toBe(true);
    expect(firmaDeAudio(oggOpus(3), "audio/webm")).toBe(false);
    expect(firmaDeAudio(webmOpus(3), "audio/mp4")).toBe(false);
    expect(firmaDeAudio(new TextEncoder().encode("<html>hola</html>"), "audio/ogg")).toBe(false);
  });
});

describe("la duración del contenedor", () => {
  it("Ogg Opus: la posición de la última página menos el pre-skip", () => {
    expect(duracionDelContenedor(oggOpus(12.5), "audio/ogg")).toBeCloseTo(12.5, 2);
    expect(duracionDelContenedor(oggOpus(90), "audio/ogg")).toBeCloseTo(90, 2);
  });

  it("WebM de MediaRecorder (clusters sin tamaño, sin Duration): el tiempo del último bloque", () => {
    expect(duracionDelContenedor(webmOpus(12.3), "audio/webm")).toBeCloseTo(12.3, 2);
    expect(duracionDelContenedor(webmOpus(70), "audio/webm")).toBeCloseTo(70, 2);
  });

  it("WebM con Duration en Info: esa", () => {
    expect(duracionDelContenedor(webmOpus(5, { conDuracion: 44 }), "audio/webm")).toBeCloseTo(44, 2);
  });

  it("MP4: la de mvhd; por fragmentos (Safari) no se sabe y la dirá Whisper", () => {
    expect(duracionDelContenedor(mp4(8), "audio/mp4")).toBeCloseTo(8, 3);
    expect(duracionDelContenedor(mp4(0), "audio/mp4")).toBeNull();
  });

  it("basura con la firma correcta: null, sin lanzar", () => {
    const basura = new Uint8Array(4000).fill(0xff);
    basura.set([0x1a, 0x45, 0xdf, 0xa3]);
    expect(duracionDelContenedor(basura, "audio/webm")).toBeNull();
    expect(duracionDelContenedor(new TextEncoder().encode("OggS sin cabeza"), "audio/ogg")).toBeNull();
    expect(duracionDelContenedor(new Uint8Array([0, 0, 0, 1, 0x66, 0x74, 0x79, 0x70]), "audio/mp4")).toBeNull();
  });
});

describe("validarNota", () => {
  it("una nota normal pasa con la duración del contenedor", () => {
    const v = validarNota(webmOpus(10), "audio/webm", 10_200);
    expect(esProblema(v)).toBe(false);
    expect((v as NotaDeVoz).segundos).toBeCloseTo(10, 2);
  });

  it("rechaza: sin tipo (415), vacía (400), pesada (413), firma distinta (400), más de un minuto (413) por el navegador o el contenedor", () => {
    expect(validarNota(webmOpus(3), null, null)).toEqual({ motivo: "tipo", status: 415 });
    expect(validarNota(new Uint8Array(0), "audio/webm", null)).toEqual({ motivo: "audio", status: 400 });
    const pesada = new Uint8Array(MAX_BYTES_VOZ + 1);
    pesada.set([0x1a, 0x45, 0xdf, 0xa3]);
    expect(validarNota(pesada, "audio/webm", null)).toEqual({ motivo: "muy_pesada", status: 413 });
    expect(validarNota(oggOpus(3), "audio/webm", null)).toEqual({ motivo: "audio", status: 400 });
    expect(validarNota(webmOpus(3), "audio/webm", 66_000)).toEqual({ motivo: "muy_larga", status: 413 });
    expect(validarNota(webmOpus(70), "audio/webm", 10_000)).toEqual({ motivo: "muy_larga", status: 413 });
    expect(validarNota(oggOpus(120), "audio/ogg", null)).toEqual({ motivo: "muy_larga", status: 413 });
    expect(validarNota(mp4(70), "audio/mp4", null)).toEqual({ motivo: "muy_larga", status: 413 });
  });

  it("el margen del navegador: 64 s todavía pasa, 66 s no", () => {
    expect(esProblema(validarNota(oggOpus(64), "audio/ogg", 64_000))).toBe(false);
    expect(esProblema(validarNota(oggOpus(66), "audio/ogg", null))).toBe(true);
  });

  it("la duración que dice el navegador: solo un entero razonable", () => {
    expect(duracionDeclarada("12000")).toBe(12000);
    expect(duracionDeclarada(4500)).toBe(4500);
    for (const malo of ["-1", "1e9", "abc", "", null, undefined, 1.5, -3, "99999999"]) expect(duracionDeclarada(malo)).toBeNull();
  });
});

describe("el texto que se devuelve", () => {
  it("sin controles ni saltos, con los espacios juntos", () => {
    expect(textoDeLaNota("  busco\nuna cama\u0000 queen\u202e  ", 500)).toEqual({ texto: "busco una cama queen", recortado: false });
  });

  it("recortado entre palabras al tope (y lo dice)", () => {
    const largo = "palabra ".repeat(100).trim();
    const r = textoDeLaNota(largo, 50);
    expect(r.recortado).toBe(true);
    expect([...r.texto].length).toBeLessThanOrEqual(50);
    expect(r.texto.endsWith("palabra")).toBe(true);
  });
});

describe("el costo (US$0.0005 por minuto, la tabla de Workers AI)", () => {
  it("por minuto de audio y, sin duración, el peor caso (Opus a 6 kbps)", () => {
    expect(PRECIO_WHISPER_USD_POR_MINUTO).toBe(0.0005);
    expect(costoDeLaVoz(60)).toBeCloseTo(0.0005, 10);
    expect(costoDeLaVoz(30)).toBeCloseTo(0.00025, 10);
    expect(peorDuracion(6000 / 8)).toBeCloseTo(1, 10);
    // Lo apartado nunca es menos que la duración del contenedor ni que el peor caso por tamaño, y nunca 0.
    expect(reservaDeLaNota({ bytes: new Uint8Array(45_000), segundos: null })).toBeCloseTo(costoDeLaVoz(60), 10);
    expect(reservaDeLaNota({ bytes: new Uint8Array(10), segundos: 30 })).toBeCloseTo(costoDeLaVoz(30), 10);
    expect(reservaDeLaNota({ bytes: new Uint8Array(0), segundos: 0 })).toBeGreaterThan(0);
  });
});

describe("transcribirNota", () => {
  it("solo llama a Whisper (ningún otro modelo, nada que genere voz), devuelve solo el texto y borra el audio de la memoria", async () => {
    const ai = { run: vi.fn(async (_modelo: string, _entrada: unknown) => ({ text: " Quiero ver camas king ", transcription_info: { duration: 4.2 }, segments: [{ start: 0, end: 4.1, text: "x" }], vtt: "WEBVTT", words: [{ word: "Quiero" }] })) };
    const bytes = webmOpus(4.2);
    const r = await transcribirNota(envCon(ai), nota(bytes, "audio/webm", 4.2), { maxLetras: 500 });
    expect(r).toEqual({ ok: true, texto: "Quiero ver camas king", recortado: false, usd: costoDeLaVoz(4.2), estimado: false, segundos: 4.2 });
    expect(Object.keys(r).sort()).toEqual(["estimado", "ok", "recortado", "segundos", "texto", "usd"]);
    expect(ai.run).toHaveBeenCalledTimes(1);
    expect(ai.run.mock.calls[0][0]).toBe(MODELO_WHISPER);
    expect(bytes.every((b) => b === 0)).toBe(true);
  });

  it("apagado (sin la bandera o sin el binding): no_disponible, sin costo, y el audio se borra igual", async () => {
    const ai = { run: vi.fn() };
    const bytes = webmOpus(2);
    expect(await transcribirNota(envCon(ai, "0"), nota(bytes), { maxLetras: 500 })).toMatchObject({ ok: false, motivo: "no_disponible", usd: 0 });
    expect(await transcribirNota({ TRANSCRIBIR_AUDIO: "1" } as Env, nota(webmOpus(2)), { maxLetras: 500 })).toMatchObject({ ok: false, motivo: "no_disponible" });
    expect(ai.run).not.toHaveBeenCalled();
    expect(bytes.every((b) => b === 0)).toBe(true);
  });

  it("si Whisper dice que duró más de un minuto (el contenedor mintió), el texto NO se devuelve, pero se cobra", async () => {
    const ai = { run: async () => ({ text: "un audio larguísimo para transcribir gratis", transcription_info: { duration: 300 } }) };
    const r = await transcribirNota(envCon(ai), nota(webmOpus(3), "audio/webm", 3), { maxLetras: 500 });
    expect(r).toEqual({ ok: false, motivo: "muy_larga", usd: costoDeLaVoz(300), estimado: false, segundos: 300 });
    expect(JSON.stringify(r)).not.toContain("larguísimo");
  });

  it("también por el final del último segmento", async () => {
    const ai = { run: async () => ({ text: "hola", segments: [{ end: 10 }, { end: 95 }] }) };
    expect(await transcribirNota(envCon(ai), nota(mp4(0), "audio/mp4"), { maxLetras: 500 })).toMatchObject({ ok: false, motivo: "muy_larga" });
  });

  it("nada entendido o lo que Whisper inventa con el silencio: no_se_entendio (cobrado)", async () => {
    for (const text of ["   ", "", "Subtítulos realizados por la comunidad de Amara.org"]) {
      const r = await transcribirNota(envCon({ run: async () => ({ text, transcription_info: { duration: 2 } }) }), nota(webmOpus(2)), { maxLetras: 500 });
      expect(r).toMatchObject({ ok: false, motivo: "no_se_entendio", usd: costoDeLaVoz(2) });
    }
  });

  it("sin duración en ningún lado: se cobra el peor caso y se marca estimado", async () => {
    const bytes = mp4(0);
    const largo = bytes.byteLength;
    const r = await transcribirNota(envCon({ run: async () => ({ text: "hola" }) }), nota(bytes, "audio/mp4"), { maxLetras: 500 });
    expect(r).toMatchObject({ ok: true, texto: "hola", estimado: true, usd: costoDeLaVoz(peorDuracion(largo)) });
  });

  it("si tarda: tardo (cobrado con lo que se sepa); si falla: fallo, sin repetir el error de Workers AI", async () => {
    const lento = { run: () => new Promise(() => {}) };
    expect(await transcribirNota(envCon(lento), nota(webmOpus(5), "audio/webm", 5), { maxLetras: 500, plazoMs: 20 })).toMatchObject({ ok: false, motivo: "tardo", usd: costoDeLaVoz(5) });
    const roto = { run: async () => Promise.reject(new Error("AiError: bad input T2dnUwACAAAAAAAAAAD")) };
    const r = await transcribirNota(envCon(roto), nota(webmOpus(5), "audio/webm", 5), { maxLetras: 500 });
    expect(r).toMatchObject({ ok: false, motivo: "fallo" });
    expect(JSON.stringify(r)).not.toContain("T2dnUw");
  });

  it("recorta al tope de letras de la ruta", async () => {
    const r = await transcribirNota(envCon({ run: async () => ({ text: "cama ".repeat(200), transcription_info: { duration: 50 } }) }), nota(webmOpus(50)), { maxLetras: 500 });
    expect(r.ok && r.recortado).toBe(true);
    expect(r.ok && [...r.texto].length).toBeLessThanOrEqual(500);
  });
});

describe("leerConTope", () => {
  it("lee el cuerpo entero si cabe y null si pasa del tope (aunque no traiga Content-Length)", async () => {
    const chico = new Request("https://x/", { method: "POST", body: new Uint8Array([1, 2, 3]) });
    expect([...(await leerConTope(chico, 10))!]).toEqual([1, 2, 3]);
    const flujo = new ReadableStream<Uint8Array>({
      start(c) {
        for (let i = 0; i < 5; i++) c.enqueue(new Uint8Array(4));
        c.close();
      },
    });
    const grande = new Request("https://x/", { method: "POST", body: flujo, duplex: "half" } as RequestInit);
    expect(await leerConTope(grande, 10)).toBeNull();
    const declarado = new Request("https://x/", { method: "POST", headers: { "content-length": "999999" }, body: new Uint8Array(1) });
    expect(await leerConTope(declarado, 10)).toBeNull();
  });
});
