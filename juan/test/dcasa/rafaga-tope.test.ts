/**
 * Ola 1 · la ráfaga espera a que el cliente termine de escribir, pero no para siempre.
 * Antes cada mensaje reiniciaba los 15 s: quien escribe una frase cada 10 s no recibía respuesta nunca.
 */
import { describe, expect, it } from "vitest";
import { crearMundo } from "../helpers/mundo";

describe("el tope de la ráfaga", () => {
  it("un cliente que escribe una frase cada 10 s recibe respuesta a los 45 s del primer mensaje (3 veces la espera), no nunca", async () => {
    const m = crearMundo();
    const g = m.guion([{ texto: "Claro, te ayudo." }, { texto: "Otra respuesta." }]);
    const t0 = m.ahora();
    let respondioA: number | null = null;
    for (let i = 0; i < 12 && respondioA === null; i++) {
      await m.escribir(`frase ${i}`);
      await m.pasar(10_000);
      if (m.canal.textos.some((t) => t.includes("Claro, te ayudo."))) respondioA = m.ahora() - t0;
    }
    expect(respondioA).not.toBeNull();
    expect(respondioA!).toBeLessThanOrEqual(55_000);
    expect(g.doGenerateCalls).toHaveLength(1); // todo se contestó en UN solo turno
  });

  it("si el cliente deja de escribir, se espera lo de siempre (15 s) y no se acorta", async () => {
    const m = crearMundo();
    m.guion([{ texto: "Hola, ¿en qué te ayudo?" }]);
    await m.escribir("hola");
    await m.pasar(14_000);
    expect(m.canal.textos).toEqual([]);
    await m.pasar(2_000);
    expect(m.canal.textos.join(" ")).toContain("¿en qué te ayudo?");
  });

  it("después de contestar, la siguiente ráfaga empieza de cero (no hereda el tope de la anterior)", async () => {
    const m = crearMundo();
    const g = m.guion([{ texto: "Primera." }, { texto: "Segunda." }]);
    await m.conversar("uno");
    expect(g.doGenerateCalls).toHaveLength(1);
    await m.pasar(5 * 60_000);
    await m.escribir("dos");
    await m.pasar(14_000);
    expect(g.doGenerateCalls).toHaveLength(1); // todavía espera sus 15 s completos
    await m.pasar(2_000);
    expect(g.doGenerateCalls).toHaveLength(2);
  });
});

describe("sin las herramientas de Odoo el asistente no contesta de memoria", () => {
  it("con Odoo caído desde el arranque: no llama a la IA, reintenta y al agotarse avisa con honestidad", async () => {
    const m = crearMundo();
    m.odoo.caido = true;
    const g = m.guion([{ texto: "Cuesta $199 la queen." }]);
    await m.conversar("¿cuánto cuesta la cama queen?");
    await m.pasar(61_000);
    await m.pasar(301_000);
    expect(g.doGenerateCalls).toHaveLength(0);
    expect(m.canal.textos.join(" ")).not.toContain("$199");
    expect(m.canal.textos.join(" ")).toMatch(/vendedora/i);
  });

  it("si Odoo vuelve antes de agotar los reintentos, contesta normal", async () => {
    const m = crearMundo();
    m.odoo.caido = true;
    m.guion([{ texto: "Aquí estoy." }]);
    await m.conversar("hola");
    expect(m.canal.textos).toEqual([]);
    m.odoo.caido = false;
    await m.pasar(61_000);
    expect(m.canal.textos.join(" ")).toContain("Aquí estoy.");
  });
});
