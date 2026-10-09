import { describe, expect, it, vi } from "vitest";
import type { Env } from "../src/env";
import { transcriptorDe } from "../src/motor/transcribir";

const AUDIO = new Uint8Array([79, 103, 103, 83, 0, 2, 0, 0]);

function envCon(parcial: Partial<Env>): Env {
  return parcial as Env;
}

describe("transcriptorDe (notas de voz)", () => {
  it("apagado por defecto: sin la bandera no hay transcriptor aunque exista el binding", () => {
    const ai = { run: vi.fn() };
    expect(transcriptorDe(envCon({ AI: ai }))).toBeUndefined();
    expect(transcriptorDe(envCon({ AI: ai, TRANSCRIBIR_AUDIO: "0" }))).toBeUndefined();
    expect(ai.run).not.toHaveBeenCalled();
  });

  it("sin el binding de Workers AI tampoco hay transcriptor, aunque la bandera esté en 1", () => {
    expect(transcriptorDe(envCon({ TRANSCRIBIR_AUDIO: "1" }))).toBeUndefined();
  });

  it("con bandera y binding manda el audio en base64 a Whisper y devuelve el texto sin espacios sobrantes", async () => {
    const ai = { run: vi.fn(async () => ({ text: "  busco una cama queen  " })) };
    const t = transcriptorDe(envCon({ AI: ai, TRANSCRIBIR_AUDIO: "1" }));
    expect(t).toBeDefined();
    expect(await t!(AUDIO, "audio/ogg")).toBe("busco una cama queen");
    expect(ai.run).toHaveBeenCalledWith("@cf/openai/whisper-large-v3-turbo", { audio: btoa(String.fromCharCode(...AUDIO)) });
  });

  it("si Whisper no entiende nada devuelve null (el bot pide que lo escriban)", async () => {
    const t = transcriptorDe(envCon({ AI: { run: async () => ({ text: "   " }) }, TRANSCRIBIR_AUDIO: "1" }));
    expect(await t!(AUDIO, "audio/ogg")).toBeNull();
  });

  it("no procesa un audio vacío ni uno enorme", async () => {
    const ai = { run: vi.fn(async () => ({ text: "hola" })) };
    const t = transcriptorDe(envCon({ AI: ai, TRANSCRIBIR_AUDIO: "1" }))!;
    expect(await t(new Uint8Array(0), "audio/ogg")).toBeNull();
    expect(await t(new Uint8Array(9 * 1024 * 1024), "audio/ogg")).toBeNull();
    expect(ai.run).not.toHaveBeenCalled();
  });
});
