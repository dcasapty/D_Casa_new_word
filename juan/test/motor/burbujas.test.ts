/**
 * Regla 11: burbujas cortas (2 a 4 líneas). Reescritura de la prueba del chunker del CRM de Baby Caleb.
 */
import { describe, expect, it } from "vitest";
import { partirEnBurbujas } from "../../src/motor/burbujas";
import { partirPorLargo } from "../../src/canales/tipos";

describe("partirEnBurbujas", () => {
  it("un texto corto es una sola burbuja; vacío, ninguna", () => {
    expect(partirEnBurbujas("Hola, ¿en qué te ayudo?")).toEqual(["Hola, ¿en qué te ayudo?"]);
    expect(partirEnBurbujas("   \n  ")).toEqual([]);
    expect(partirEnBurbujas("")).toEqual([]);
  });

  it("cada párrafo (línea en blanco) es una idea; los vecinos cortos se juntan mientras quepan", () => {
    expect(partirEnBurbujas("Uno corto.\n\nDos corto.")).toEqual(["Uno corto.\nDos corto."]);
  });

  it("un párrafo largo se parte por oraciones, sin cortar ninguna a la mitad", () => {
    const oracion = "Esta cama viene en varias medidas y la puedes ver en el showroom.";
    const texto = Array.from({ length: 6 }, () => oracion).join(" ");
    const b = partirEnBurbujas(texto);
    expect(b.length).toBeGreaterThan(1);
    for (const burbuja of b) {
      expect(burbuja.endsWith(".")).toBe(true);
    }
    // No se pierde ni una palabra.
    expect(b.join(" ").replace(/\s+/g, " ")).toBe(texto);
  });

  it("nunca más de 4 líneas por burbuja (salvo una lista, que se queda junta)", () => {
    const b = partirEnBurbujas("a\n\nb\n\nc\n\nd\n\ne\n\nf");
    for (const x of b) expect(x.split("\n").length).toBeLessThanOrEqual(4);
  });

  it("una lista de varias líneas NO se corta por la mitad", () => {
    const lista = "Tenemos:\n- Cama queen\n- Cama king\n- Cama full";
    const b = partirEnBurbujas(`Mira lo que hay.\n\n${lista}`);
    expect(b.some((x) => x.includes(lista))).toBe(true);
  });

  it("tope de burbujas: lo que sobra se junta en la última, sin perder texto", () => {
    const parrafos = Array.from({ length: 12 }, (_, i) => `Párrafo número ${i} con bastante texto para ocupar su propia burbuja y obligar a partir. `.repeat(3).trim());
    const b = partirEnBurbujas(parrafos.join("\n\n"), { maxBurbujas: 3 });
    expect(b).toHaveLength(3);
    for (const p of parrafos) expect(b.join("\n")).toContain(p.slice(0, 40));
  });

  it("maxBurbujas = 1 devuelve todo junto", () => {
    expect(partirEnBurbujas("Uno.\n\nDos.\n\nTres.", { maxBurbujas: 1 })).toEqual(["Uno.\n\nDos.\n\nTres."]);
  });
});

describe("partirPorLargo (último recurso por el límite del canal)", () => {
  it("lo que cabe no se toca", () => {
    expect(partirPorLargo("corto", 100)).toEqual(["corto"]);
  });

  it("corta en salto de línea o espacio antes que a media palabra, y no pierde nada", () => {
    const texto = "palabra ".repeat(40).trim();
    const trozos = partirPorLargo(texto, 50);
    expect(trozos.length).toBeGreaterThan(1);
    for (const t of trozos) {
      expect(t.length).toBeLessThanOrEqual(50);
      expect(t).not.toMatch(/^\s|\s$/);
      expect(t.split(" ").every((w) => w === "palabra")).toBe(true);
    }
    expect(trozos.join(" ")).toBe(texto);
  });

  it("una palabra más larga que el máximo se corta igual (no se cuelga)", () => {
    const trozos = partirPorLargo("x".repeat(250), 100);
    expect(trozos.map((t) => t.length)).toEqual([100, 100, 50]);
  });
});
