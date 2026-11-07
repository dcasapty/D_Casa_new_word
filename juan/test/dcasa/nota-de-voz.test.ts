/**
 * Issue #24 · Notas de voz:
 *   · Una nota de voz que pide una persona («quiero hablar con alguien», «no me escriban») vale como si lo escribiera: las reglas
 *     1 y 10 miraban solo el texto escrito (`textoOriginal`), no la transcripción.
 *   · Transcribir y leer imágenes cuesta IA: no se hace con lo que el anti-spam o el tope diario ya frenan, y el audio tiene su
 *     propio tope por persona al día, como las imágenes.
 */
import { describe, expect, it } from "vitest";
import { AUDIOS_POR_DIA } from "../../src/motor/conversacion";
import type { LecturaImagen } from "../../src/motor/vision";
import { crearMundo, type Mundo } from "../helpers/mundo";

const AUDIO = { adjuntos: [{ tipo: "audio" as const, mime: "audio/ogg", nombre: "nota.ogg", bytes: new Uint8Array([1, 2, 3, 4]) }] };
const IMAGEN = { adjuntos: [{ tipo: "imagen" as const, mime: "image/jpeg", nombre: "foto.jpg", bytes: new Uint8Array([9, 9, 9]) }] };

function conTranscripcion(dice: string | (() => string), op: Parameters<typeof crearMundo>[0] = {}) {
  const veces = { n: 0 };
  const m = crearMundo({
    ...op,
    transcribir: async () => {
      veces.n++;
      return typeof dice === "string" ? dice : dice();
    },
  });
  return { m, veces };
}

const pedir = (m: Mundo, ultimo: number) => m.motor.seguimiento({ conversacion_id: 12, numero: 1, contexto: { interes: "cama", ultimo_mensaje_ts: new Date(ultimo).toISOString() } });

describe("una nota de voz que pide una persona (regla 1) o que no le escriban (regla 10)", () => {
  it("«quiero hablar con una persona» dicho en una nota de voz pasa a una vendedora sin esperar a la IA", async () => {
    const { m } = conTranscripcion("Quiero hablar con una persona, por favor.");
    const g = m.guion([{ texto: "(el modelo no debe ni enterarse)" }]);
    await m.conversar("", AUDIO);
    expect(g.doGenerateCalls.length).toBe(0);
    expect(m.odoo.de("pasar_a_vendedora")).toHaveLength(1);
    expect(m.canal.textos.join("\n")).toContain("ya avisé a una vendedora");
  });

  it("«necesito hablar con alguien real» también", async () => {
    const { m } = conTranscripcion("necesito hablar con alguien real");
    m.guion([{ texto: "x" }]);
    await m.conversar("", AUDIO);
    expect(m.odoo.de("pasar_a_vendedora")).toHaveLength(1);
  });

  it("«ya no me escriban» dicho en una nota de voz apaga los seguimientos, como escrito", async () => {
    const { m } = conTranscripcion("Ya no me escriban más, gracias.");
    m.guion([{ texto: "Entendido, no te escribimos más." }]);
    await m.conversar("", AUDIO);
    const ultimo = m.ahora();
    expect(m.odoo.de("anotar_conversacion").some((l) => String(l.args.nota).includes("No enviar seguimientos"))).toBe(true);
    await m.pasar(5 * 3600_000);
    expect(await pedir(m, ultimo)).toMatchObject({ ok: true, resultado: "descartado", motivo: expect.stringMatching(/no lo contacten/) });
  });

  it("una nota de voz que solo menciona «una persona» (una cama para una persona) no es una petición", async () => {
    const { m } = conTranscripcion("busco una cama para una persona");
    const g = m.guion([{ texto: "Tenemos camas sencillas." }]);
    await m.conversar("", AUDIO);
    expect(m.odoo.de("pasar_a_vendedora")).toHaveLength(0);
    expect(g.doGenerateCalls.length).toBe(1);
  });
});

describe("transcribir y leer imágenes, después del anti-spam y del tope diario", () => {
  it("con la conversación en descanso por spam, la nota de voz no se transcribe", async () => {
    const { m, veces } = conTranscripcion("busco una cama");
    m.guion([{ texto: "Hola." }]);
    for (let i = 0; i < 3; i++) await m.escribir("compra compra");
    expect(m.motor.resumen().pendientes).toBe(0);
    expect((await m.escribir("", AUDIO)).accion).toBe("descanso");
    expect(veces.n).toBe(0);
    // Queda para una vendedora, como cualquier archivo que el bot no entendió.
    await m.pasar(60_000);
    expect(m.odoo.mensajes.filter((x) => x.autor === "cliente")).toHaveLength(4);
    expect(m.odoo.de("anotar_conversacion").some((l) => String(l.args.nota).includes("audio"))).toBe(true);
  });

  it("pasado el tope diario de turnos, la nota de voz no se transcribe", async () => {
    const { m, veces } = conTranscripcion("busco una cama", { topeDiario: 2 });
    m.guion([{ texto: "Hola." }]);
    await m.escribir("uno");
    await m.escribir("dos");
    expect((await m.escribir("", AUDIO)).accion).toBe("tope_diario");
    expect((await m.escribir("", AUDIO)).accion).toBe("descanso");
    expect(veces.n).toBe(0);
  });

  it("tampoco se lee una imagen en descanso", async () => {
    let lecturas = 0;
    const m = crearMundo({
      mirarImagen: async (): Promise<LecturaImagen> => {
        lecturas++;
        return { tipo: "producto", codigos: [], categoria: "cama", medida: null, parece_pago: false, parece_identidad: false };
      },
    });
    m.guion([{ texto: "Hola." }]);
    for (let i = 0; i < 3; i++) await m.escribir("compra compra");
    await m.escribir("", IMAGEN);
    expect(lecturas).toBe(0);
  });

  it(`cada persona tiene un tope de ${AUDIOS_POR_DIA} notas de voz transcritas al día; la siguiente queda para una vendedora`, async () => {
    const { m, veces } = conTranscripcion(() => `quiero saber de la cama número ${veces.n}`);
    const g = m.guion([{ texto: "Claro, te cuento." }]);
    for (let i = 0; i < AUDIOS_POR_DIA; i++) await m.conversar("", AUDIO);
    expect(veces.n).toBe(AUDIOS_POR_DIA);
    await m.conversar("", AUDIO);
    expect(veces.n).toBe(AUDIOS_POR_DIA);
    expect(g.prompts().at(-1)).toContain("nota de voz que no puedes escuchar");
    // Al día siguiente vuelve a transcribir.
    await m.pasar(24 * 3600_000);
    await m.conversar("", AUDIO);
    expect(veces.n).toBe(AUDIOS_POR_DIA + 1);
  });
});
