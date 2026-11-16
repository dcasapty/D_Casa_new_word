/**
 * Las notas de voz (motor/voz.ts y motor/duracion.ts): solo los tipos que graba un navegador, la duración que DE VERDAD se decodifica
 * (contada paquete por paquete, sin creerle al contenedor), solo el texto de vuelta y el audio borrado de la memoria al terminar.
 */
import { describe, expect, it, vi } from "vitest";
import type { Env } from "../src/env";
import { duracionPaqueteOpus, medirMp4, medirOgg, medirWebm } from "../src/motor/duracion";
import { MODELO_WHISPER } from "../src/motor/transcribir";
import {
  costoDeLaVoz,
  duracionDeclarada,
  duracionDelContenedor,
  esProblema,
  firmaDeAudio,
  leerConTope,
  MAX_BYTES_VOZ,
  MAX_SEGUNDOS_TIENDA,
  PRECIO_WHISPER_USD_POR_MINUTO,
  reservaDeLaNota,
  textoDeLaNota,
  tipoDeAudio,
  transcribirNota,
  validarNota,
  type NotaDeVoz,
} from "../src/motor/voz";
import { mp4, oggOpus, paginaOgg, webmOpus } from "./helpers/audio";

const envCon = (ai: unknown, bandera = "1") => ({ AI: ai, TRANSCRIBIR_AUDIO: bandera }) as unknown as Env;
const nota = (bytes: Uint8Array, segundos: number, tipo: NotaDeVoz["tipo"] = "audio/webm", maxSegundos = 60): NotaDeVoz => ({ bytes, tipo, segundos, maxSegundos });

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

describe("el TOC de Opus (RFC 6716 §3.1)", () => {
  it("la duración de cada paquete: tramas por lo que dura cada una", () => {
    expect(duracionPaqueteOpus(new Uint8Array([0xfc]))).toBeCloseTo(0.02, 10); // CELT FB 20 ms, una trama
    expect(duracionPaqueteOpus(new Uint8Array([0x0b]))).toBeCloseTo(0.12, 10); // SILK NB 60 ms, código 3 sin el byte de tramas → lo máximo
    expect(duracionPaqueteOpus(new Uint8Array([0x09]))).toBeCloseTo(0.04, 10); // SILK NB 20 ms, dos tramas (código 1)
    expect(duracionPaqueteOpus(new Uint8Array([(31 << 3) | 3, 6]))).toBeCloseTo(0.12, 10); // CELT FB 20 ms × 6 = 120 ms en 2 bytes
    expect(duracionPaqueteOpus(new Uint8Array([(16 << 3) | 3, 48]))).toBeCloseTo(0.12, 10); // 2,5 ms × 48 = 120 ms
    expect(duracionPaqueteOpus(new Uint8Array([(31 << 3) | 3, 7]))).toBeCloseTo(0.12, 10); // 140 ms no es válido: lo máximo
    expect(duracionPaqueteOpus(new Uint8Array([(31 << 3) | 3, 0]))).toBeCloseTo(0.12, 10); // cero tramas: lo máximo
    expect(duracionPaqueteOpus(new Uint8Array(0))).toBeCloseTo(0.12, 10); // vacío: lo máximo (nunca de menos)
  });
});

describe("la duración que de verdad se decodifica (no la que dice el archivo)", () => {
  it("Ogg Opus: la suma de los paquetes menos el pre-skip, aunque la última página mienta", () => {
    expect(duracionDelContenedor(oggOpus(12.5), "audio/ogg")).toBeCloseTo(12.5, 1);
    expect(duracionDelContenedor(oggOpus(90, { mentir: 3 }), "audio/ogg")).toBeCloseTo(90, 1);
    // Más bytes en cada paquete no es más audio: pesa más, dura lo mismo.
    expect(duracionDelContenedor(oggOpus(10, { relleno: 200 }), "audio/ogg")).toBeCloseTo(10, 1);
  });

  it("Ogg que no se puede recorrer con certeza: CRC malo, página que falta, otro flujo, basura al final", () => {
    const cabeza = [...new TextEncoder().encode("OpusHead"), 1, 1, 0x38, 0x01, 0x80, 0xbb, 0, 0, 0, 0, 0];
    const etiquetas = [...new TextEncoder().encode("OpusTags"), 0, 0, 0, 0, 0, 0, 0, 0];
    const unir = (...p: Uint8Array[]) => new Uint8Array(p.flatMap((x) => [...x]));
    const bien = unir(paginaOgg([cabeza], 0, 0, 2), paginaOgg([etiquetas], 0, 1), paginaOgg([[0xfc, 1]], 960, 2, 4));
    expect(medirOgg(bien)).toBeCloseTo(0.02 - 312 / 48_000, 6);
    expect(medirOgg(unir(paginaOgg([cabeza], 0, 0, 2), paginaOgg([etiquetas], 0, 1), paginaOgg([[0xfc, 1]], 960, 2, 0, { crcMalo: true })))).toBeNull();
    expect(medirOgg(unir(paginaOgg([cabeza], 0, 0, 2), paginaOgg([etiquetas], 0, 1), paginaOgg([[0xfc, 1]], 960, 3)))).toBeNull();
    expect(medirOgg(unir(paginaOgg([cabeza], 0, 0, 2), paginaOgg([etiquetas], 0, 1), paginaOgg([[0xfc, 1]], 960, 2, 0, { serie: 9 })))).toBeNull();
    expect(medirOgg(unir(bien, new Uint8Array([1, 2, 3])))).toBeNull();
    expect(medirOgg(unir(paginaOgg([etiquetas], 0, 0, 2), paginaOgg([[0xfc]], 960, 1)))).toBeNull(); // sin OpusHead
  });

  it("WebM de MediaRecorder (clusters sin tamaño): la suma del TOC de cada bloque, aunque «Duration» mienta", () => {
    expect(duracionDelContenedor(webmOpus(12.3), "audio/webm")).toBeCloseTo(12.3, 2);
    expect(duracionDelContenedor(webmOpus(70), "audio/webm")).toBeCloseTo(70, 2);
    expect(duracionDelContenedor(webmOpus(70, { conDuracion: 5 }), "audio/webm")).toBeCloseTo(70, 2);
    // Paquetes de 2 bytes que valen 120 ms cada uno: lo que importa es el TOC, no el peso.
    expect(duracionDelContenedor(webmOpus(0.4, { paquete: [(31 << 3) | 3, 6] }), "audio/webm")).toBeCloseTo(20 * 0.12, 6);
  });

  it("WebM que no se puede medir con certeza: otro códec, dos pistas, lacing, bytes de más", () => {
    expect(medirWebm(webmOpus(3, { codec: "A_VORBIS" }))).toBeNull();
    expect(medirWebm(webmOpus(3, { pistas: 2 }))).toBeNull();
    expect(medirWebm(webmOpus(3, { lacing: true }))).toBeNull();
    expect(medirWebm(new Uint8Array([...webmOpus(3), 0x00]))).toBeNull();
  });

  it("MP4 (Safari): las tramas AAC de 1024 a la frecuencia de su configuración, aunque «mvhd» mienta; por fragmentos también", () => {
    expect(duracionDelContenedor(mp4(8), "audio/mp4")).toBeCloseTo(8, 1);
    expect(duracionDelContenedor(mp4(8, { mentir: 1 }), "audio/mp4")).toBeCloseTo(8, 1);
    expect(duracionDelContenedor(mp4(25, { fragmentos: true }), "audio/mp4")).toBeCloseTo(25, 1);
  });

  it("MP4 que no se puede medir con certeza: otro códec o una lista de edición que podría repetir el audio", () => {
    expect(medirMp4(mp4(3, { codec: "Opus" }))).toBeNull();
    expect(medirMp4(mp4(3, { edicionesRepetidas: true }))).toBeNull();
    expect(medirMp4(new Uint8Array([0, 0, 0, 1, 0x66, 0x74, 0x79, 0x70]))).toBeNull();
  });

  it("basura con la firma correcta: null, sin lanzar", () => {
    const basura = new Uint8Array(4000).fill(0xff);
    basura.set([0x1a, 0x45, 0xdf, 0xa3]);
    expect(duracionDelContenedor(basura, "audio/webm")).toBeNull();
    expect(duracionDelContenedor(new TextEncoder().encode("OggS sin cabeza"), "audio/ogg")).toBeNull();
  });
});

describe("validarNota (todo antes de apartar)", () => {
  it("una nota normal pasa con su duración medida", () => {
    const v = validarNota(webmOpus(10), "audio/webm", 10_200);
    expect(esProblema(v)).toBe(false);
    expect((v as NotaDeVoz).segundos).toBeCloseTo(10, 2);
  });

  it("rechaza: sin tipo (415), vacía (400), pesada (413), firma distinta (400), imposible de medir (400), más larga que el tope (413)", () => {
    expect(validarNota(webmOpus(3), null, null)).toEqual({ motivo: "tipo", status: 415 });
    expect(validarNota(new Uint8Array(0), "audio/webm", null)).toEqual({ motivo: "audio", status: 400 });
    const pesada = new Uint8Array(MAX_BYTES_VOZ + 1);
    pesada.set([0x1a, 0x45, 0xdf, 0xa3]);
    expect(validarNota(pesada, "audio/webm", null)).toEqual({ motivo: "muy_pesada", status: 413 });
    expect(validarNota(oggOpus(3), "audio/webm", null)).toEqual({ motivo: "audio", status: 400 });
    expect(validarNota(webmOpus(3, { codec: "A_VORBIS" }), "audio/webm", null)).toEqual({ motivo: "audio", status: 400 });
    expect(validarNota(webmOpus(3), "audio/webm", 66_000)).toEqual({ motivo: "muy_larga", status: 413 });
    expect(validarNota(webmOpus(70), "audio/webm", 10_000)).toEqual({ motivo: "muy_larga", status: 413 });
    expect(validarNota(oggOpus(120, { mentir: 5 }), "audio/ogg", null)).toEqual({ motivo: "muy_larga", status: 413 });
    expect(validarNota(mp4(70, { mentir: 3 }), "audio/mp4", null)).toEqual({ motivo: "muy_larga", status: 413 });
  });

  it("el tope de cada ruta: 60 s (+5 del navegador) en el panel, 30 s (+5) en la tienda", () => {
    expect(esProblema(validarNota(oggOpus(64), "audio/ogg", 64_000))).toBe(false);
    expect(esProblema(validarNota(oggOpus(66), "audio/ogg", null))).toBe(true);
    expect(MAX_SEGUNDOS_TIENDA).toBe(30);
    expect(esProblema(validarNota(oggOpus(34), "audio/ogg", null, MAX_SEGUNDOS_TIENDA))).toBe(false);
    expect(validarNota(oggOpus(40), "audio/ogg", null, MAX_SEGUNDOS_TIENDA)).toEqual({ motivo: "muy_larga", status: 413 });
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

describe("el costo (US$0.0005 por minuto, la tabla de Workers AI), con la duración medida", () => {
  it("por minuto de audio decodificado; lo apartado es el costo de lo que de verdad dura, nunca 0", () => {
    expect(PRECIO_WHISPER_USD_POR_MINUTO).toBe(0.0005);
    expect(costoDeLaVoz(60)).toBeCloseTo(0.0005, 10);
    expect(costoDeLaVoz(30)).toBeCloseTo(0.00025, 10);
    expect(reservaDeLaNota({ segundos: 30 })).toBeCloseTo(costoDeLaVoz(30), 10);
    expect(reservaDeLaNota({ segundos: 0 })).toBeGreaterThan(0);
  });
});

describe("transcribirNota", () => {
  it("solo llama a Whisper (ningún otro modelo, nada que genere voz), devuelve solo el texto y borra el audio de la memoria", async () => {
    const ai = { run: vi.fn(async (_modelo: string, _entrada: unknown) => ({ text: " Quiero ver camas king ", transcription_info: { duration: 4.2 }, segments: [{ start: 0, end: 4.1, text: "x" }], vtt: "WEBVTT", words: [{ word: "Quiero" }] })) };
    const bytes = webmOpus(4.2);
    const r = await transcribirNota(envCon(ai), nota(bytes, 4.2), { maxLetras: 500 });
    expect(r).toEqual({ ok: true, texto: "Quiero ver camas king", recortado: false, usd: costoDeLaVoz(4.2), estimado: false, segundos: 4.2 });
    expect(ai.run).toHaveBeenCalledTimes(1);
    expect(ai.run.mock.calls[0][0]).toBe(MODELO_WHISPER);
    expect(bytes.every((b) => b === 0)).toBe(true);
  });

  it("apagado (sin la bandera o sin el binding): no_disponible, sin costo, y el audio se borra igual", async () => {
    const ai = { run: vi.fn() };
    const bytes = webmOpus(2);
    expect(await transcribirNota(envCon(ai, "0"), nota(bytes, 2), { maxLetras: 500 })).toMatchObject({ ok: false, motivo: "no_disponible", usd: 0 });
    expect(await transcribirNota({ TRANSCRIBIR_AUDIO: "1" } as Env, nota(webmOpus(2), 2), { maxLetras: 500 })).toMatchObject({ ok: false, motivo: "no_disponible" });
    expect(ai.run).not.toHaveBeenCalled();
    expect(bytes.every((b) => b === 0)).toBe(true);
  });

  it("se cobra lo mayor entre lo medido y lo que diga Whisper; si Whisper dice más que el tope, el texto NO sale", async () => {
    const corta = { run: async () => ({ text: "hola", transcription_info: { duration: 1 } }) };
    expect(await transcribirNota(envCon(corta), nota(webmOpus(6), 6), { maxLetras: 500 })).toMatchObject({ ok: true, usd: costoDeLaVoz(6), segundos: 6 });
    const larga = { run: async () => ({ text: "un audio larguísimo", transcription_info: { duration: 300 } }) };
    const r = await transcribirNota(envCon(larga), nota(webmOpus(3), 3), { maxLetras: 500 });
    expect(r).toEqual({ ok: false, motivo: "muy_larga", usd: costoDeLaVoz(300), estimado: false, segundos: 300 });
    expect(JSON.stringify(r)).not.toContain("larguísimo");
  });

  it("nada entendido o lo que Whisper inventa con el silencio: no_se_entendio (cobrado)", async () => {
    for (const text of ["   ", "", "Subtítulos realizados por la comunidad de Amara.org"]) {
      const r = await transcribirNota(envCon({ run: async () => ({ text, transcription_info: { duration: 2 } }) }), nota(webmOpus(2), 2), { maxLetras: 500 });
      expect(r).toMatchObject({ ok: false, motivo: "no_se_entendio", usd: costoDeLaVoz(2) });
    }
  });

  it("si Whisper tarda o falla: se cobra la duración medida (no un mínimo), marcada «estimado», sin repetir el error", async () => {
    const lento = { run: () => new Promise(() => {}) };
    expect(await transcribirNota(envCon(lento), nota(webmOpus(25), 25), { maxLetras: 500, plazoMs: 20 })).toMatchObject({ ok: false, motivo: "tardo", usd: costoDeLaVoz(25), estimado: true });
    const roto = { run: async () => Promise.reject(new Error("AiError: bad input T2dnUwACAAAAAAAAAAD")) };
    const r = await transcribirNota(envCon(roto), nota(webmOpus(25), 25), { maxLetras: 500 });
    expect(r).toMatchObject({ ok: false, motivo: "fallo", usd: costoDeLaVoz(25), estimado: true });
    expect(JSON.stringify(r)).not.toContain("T2dnUw");
  });

  it("recorta al tope de letras de la ruta", async () => {
    const r = await transcribirNota(envCon({ run: async () => ({ text: "cama ".repeat(200), transcription_info: { duration: 50 } }) }), nota(webmOpus(50), 50), { maxLetras: 500 });
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
  });
});
