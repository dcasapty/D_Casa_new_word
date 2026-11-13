/**
 * Revisión adversarial (2026-11-13) del cambio «solo comprobantes de verdad». Clientes inventados.
 *
 * Fuera de aquí, a propósito: «producto» o «publicación» con parece_pago NO es comprobante (lo eligió la dueña; riesgo aceptado, ver el
 * comentario de `esComprobante` en src/motor/vision.ts).
 */
import { describe, expect, it } from "vitest";
import type { LecturaImagen } from "../../src/motor/vision";
import { crearMundo } from "../helpers/mundo";

const BYTES = new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 1, 2, 3, 4, 5, 6, 7, 8]);
const imagen = (nombre = "captura.jpg") => ({ adjuntos: [{ tipo: "imagen" as const, mime: "image/jpeg", nombre, bytes: BYTES }] });
const PUBLICACION: LecturaImagen = { tipo: "publicacion", codigos: ["822F"], categoria: "cama", medida: "full", parece_pago: false, parece_identidad: false };
const adjuntoEnOdoo = (m: ReturnType<typeof crearMundo>) => m.odoo.mensajes.filter((x) => x.autor === "cliente").at(-1)!.adjuntos![0];

describe("REVISIÓN: imágenes que Juan NO lee llegan a Odoo como «sin_leer» con su porqué (Odoo decide si avisa)", () => {
  it("la 11.ª imagen del día (tope de lecturas) llega «sin_leer» por «tope»", async () => {
    const m = crearMundo({ mirarImagen: async () => PUBLICACION });
    m.guion([{ texto: "Veo." }]);
    for (let i = 0; i < 10; i++) await m.conversar(`foto ${i} distinta ${"x".repeat(i)}`, imagen(`f${i}.jpg`));
    await m.conversar("listo, ya te hice el Yappy", imagen("yappy.jpg"));
    expect(adjuntoEnOdoo(m)).toMatchObject({ clase: "sin_leer", sin_leer: "tope" });
    expect(m.odoo.de("etiquetar_conversacion")).toHaveLength(0);
  });

  it("si el lector falla (sin cupo, tardó demasiado) o no entiende nada, la imagen llega «sin_leer» por «fallo»", async () => {
    for (const lector of [async () => { throw new Error("sin cupo de Workers AI"); }, async () => null]) {
      const m = crearMundo({ mirarImagen: lector });
      m.guion([{ texto: "Recibí tu imagen." }]);
      await m.conversar("te mando el pago", imagen("yappy.jpg"));
      expect(adjuntoEnOdoo(m)).toMatchObject({ clase: "sin_leer", sin_leer: "fallo" });
    }
  });

  it("una imagen ilegible (sin señal de pago ni de identidad) llega «sin_leer» por «ilegible»: puede ser un recibo borroso", async () => {
    const m = crearMundo({ mirarImagen: async () => ({ tipo: "ilegible", codigos: [], categoria: null, medida: null, parece_pago: false, parece_identidad: false }) });
    m.guion([{ texto: "Recibí tu imagen." }]);
    await m.conversar("ahí va", imagen("borrosa.jpg"));
    expect(adjuntoEnOdoo(m)).toMatchObject({ clase: "sin_leer", sin_leer: "ilegible" });
    expect(adjuntoEnOdoo(m).sensible).toBeUndefined();
  });

  it("una ilegible con señal de pago sigue llegando como comprobante (lo prudente)", async () => {
    const m = crearMundo({ mirarImagen: async () => ({ tipo: "ilegible", codigos: [], categoria: null, medida: null, parece_pago: true, parece_identidad: false }) });
    m.guion([{ texto: "Recibí tu imagen." }]);
    await m.conversar("ahí va", imagen("borrosa.jpg"));
    expect(adjuntoEnOdoo(m)).toMatchObject({ clase: "comprobante", sensible: true });
  });

  it("un sticker no se lee, pero llega como «otra»: no es una imagen que Juan no pudo leer (no avisa en Odoo)", async () => {
    let lecturas = 0;
    const m = crearMundo({ mirarImagen: async () => (lecturas++, PUBLICACION) });
    m.guion([{ texto: "Jaja." }]);
    await m.conversar("(el cliente mandó un sticker)", { adjuntos: [{ tipo: "imagen" as const, mime: "image/webp", nombre: "sticker.webp", bytes: BYTES, sticker: true }] });
    expect(lecturas).toBe(0);
    expect(adjuntoEnOdoo(m)).toMatchObject({ tipo: "imagen", clase: "otra" });
  });
});
