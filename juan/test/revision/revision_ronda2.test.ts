/**
 * Revisión adversarial, segunda vuelta (2026-11-13): cuándo una imagen llega a Odoo SIN clase (= en Odoo, «una imagen que Juan no pudo
 * leer: puede ser un comprobante», con aviso). Clientes inventados.
 */
import { describe, expect, it } from "vitest";
import type { LecturaImagen } from "../../src/motor/vision";
import { crearMundo } from "../helpers/mundo";

const BYTES = new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 1, 2, 3, 4, 5, 6, 7, 8]);
const PUBLICACION: LecturaImagen = { tipo: "publicacion", codigos: ["822F"], categoria: "cama", medida: "full", parece_pago: false, parece_identidad: false };
const deOdoo = (m: ReturnType<typeof crearMundo>) => m.odoo.mensajes.filter((x) => x.autor === "cliente").at(-1)!.adjuntos!;

describe("REVISIÓN 2: imágenes sin leer con el lector FUNCIONANDO (Odoo decide con el porqué si avisa «puede ser un comprobante»)", () => {
  it("cinco capturas de Instagram en un mensaje: las 3 primeras se leen («publicacion», sin aviso); la 4.ª y la 5.ª llegan «sin_leer» por «tope»", async () => {
    const m = crearMundo({ mirarImagen: async () => PUBLICACION });
    m.guion([{ texto: "Veo varias." }]);
    const cinco = { adjuntos: Array.from({ length: 5 }, (_, i) => ({ tipo: "imagen" as const, mime: "image/jpeg", nombre: `ig${i}.jpg`, bytes: BYTES })) };
    await m.conversar("¿cuál de estas tienen?", cinco);
    expect(deOdoo(m).map((a) => a.clase ?? null)).toEqual(["publicacion", "publicacion", "publicacion", "sin_leer", "sin_leer"]);
    expect(deOdoo(m).map((a) => a.sin_leer ?? null)).toEqual([null, null, null, "tope", "tope"]);
  });

  it("Odoo distingue «no la leí porque el lector está apagado» de «la intenté leer y no pude»", async () => {
    const apagado = crearMundo();
    apagado.guion([{ texto: "Recibí tu imagen." }]);
    await apagado.conversar("mira esta", { adjuntos: [{ tipo: "imagen" as const, mime: "image/jpeg", nombre: "ig.jpg", bytes: BYTES }] });
    const fallo = crearMundo({ mirarImagen: async () => { throw new Error("sin cupo"); } });
    fallo.guion([{ texto: "Recibí tu imagen." }]);
    await fallo.conversar("mira esta", { adjuntos: [{ tipo: "imagen" as const, mime: "image/jpeg", nombre: "ig.jpg", bytes: BYTES }] });
    // Lo que propuso la revisión: Juan dice por qué no la leyó (`sin_leer: "apagado" | "tope" | "fallo" | "ilegible"`).
    expect(deOdoo(apagado)[0]).not.toEqual(deOdoo(fallo)[0]);
    expect(deOdoo(apagado)[0]).toMatchObject({ clase: "sin_leer", sin_leer: "apagado" });
    expect(deOdoo(fallo)[0]).toMatchObject({ clase: "sin_leer", sin_leer: "fallo" });
  });

  it("el descanso del anti-spam (o el tope diario) cuenta como «tope»", async () => {
    const m = crearMundo({ mirarImagen: async () => PUBLICACION });
    m.guion([{ texto: "Hola." }]);
    // El mismo texto repetido: el anti-spam lo frena y no se gasta IA en leer.
    for (let i = 0; i < 6; i++) await m.conversar("hola", { adjuntos: [{ tipo: "imagen" as const, mime: "image/jpeg", nombre: `r${i}.jpg`, bytes: BYTES }] });
    expect(deOdoo(m)[0]).toMatchObject({ clase: "sin_leer", sin_leer: "tope" });
  });
});
