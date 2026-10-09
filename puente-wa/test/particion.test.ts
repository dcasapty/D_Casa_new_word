import { describe, expect, it } from "vitest";
import {
  MAX_BURBUJA,
  MAX_BURBUJAS,
  MAX_PIE,
  limpiarTexto,
  partirPie,
  partirTexto,
  prepararBurbujas,
} from "../contenedor/lib/particion.mjs";

const normalizar = (t: string) => t.replace(/\s+/g, " ").trim();

describe("limpiarTexto", () => {
  it("normaliza saltos de línea y quita caracteres de control", () => {
    expect(limpiarTexto("Hola\r\nQué tal\r\n\r\n\r\n\r\nBien\u0000\u0007")).toBe("Hola\nQué tal\n\nBien");
    expect(limpiarTexto("   espacios   ")).toBe("espacios");
    expect(limpiarTexto(null)).toBe("");
  });
});

describe("partirTexto", () => {
  it("no toca un texto corto", () => {
    expect(partirTexto("Hola, ¿en qué te ayudo?")).toEqual(["Hola, ¿en qué te ayudo?"]);
  });

  it("un texto vacío no da burbujas", () => {
    expect(partirTexto("")).toEqual([]);
    expect(partirTexto("   \n  ")).toEqual([]);
  });

  it("parte por párrafos y junta los que caben", () => {
    const p1 = "a".repeat(500);
    const p2 = "b".repeat(500);
    const p3 = "c".repeat(500);
    const r = partirTexto(`${p1}\n\n${p2}\n\n${p3}`, 1100);
    expect(r).toEqual([`${p1}\n\n${p2}`, p3]);
  });

  it("parte por frases cuando un párrafo no cabe", () => {
    const frase = "Esta cama queen es de madera firme y viene con base. ";
    const texto = frase.repeat(40).trim();
    const r = partirTexto(texto, 300);
    expect(r.length).toBeGreaterThan(1);
    for (const b of r) {
      expect(b.length).toBeLessThanOrEqual(300);
      expect(b.endsWith(".")).toBe(true); // cortó en un punto, no a la mitad de una palabra
    }
    expect(normalizar(r.join(" "))).toBe(normalizar(texto));
  });

  it("una palabra enorme (una URL) se corta a la fuerza pero sin perder nada", () => {
    const url = "https://dcasapty.com/" + "x".repeat(2500);
    const r = partirTexto(`Mira esto ${url}`, 1000);
    for (const b of r) expect(b.length).toBeLessThanOrEqual(1000);
    expect(r.join("").replace(/\s/g, "")).toContain(url);
  });

  it("no parte un emoji por la mitad", () => {
    const texto = "😀".repeat(30); // cada uno ocupa dos unidades UTF-16
    const r = partirTexto(texto, 21);
    for (const b of r) {
      expect(b.length).toBeLessThanOrEqual(21);
      expect([...b].every((c) => c === "😀")).toBe(true); // ninguna mitad suelta
    }
    expect(r.join("")).toBe(texto);
  });

  it("propiedad: nunca pasa del máximo y conserva todas las palabras en orden", () => {
    // Texto determinista con párrafos, líneas y frases de tamaños variados.
    let semilla = 12345;
    const azar = () => {
      semilla = (semilla * 1103515245 + 12345) & 0x7fffffff;
      return semilla / 0x7fffffff;
    };
    const palabras = ["mueble", "cama", "sala", "queen", "madera", "entrega", "La Chorrera", "ITBMS", "colchón", "comedor"];
    for (let caso = 0; caso < 200; caso++) {
      const partes: string[] = [];
      const parrafos = 1 + Math.floor(azar() * 6);
      for (let p = 0; p < parrafos; p++) {
        const frases = 1 + Math.floor(azar() * 12);
        const lineas: string[] = [];
        for (let f = 0; f < frases; f++) {
          const n = 1 + Math.floor(azar() * 25);
          const w = Array.from({ length: n }, () => palabras[Math.floor(azar() * palabras.length)]);
          lineas.push(w.join(" ") + (azar() < 0.8 ? "." : "!"));
        }
        partes.push(lineas.join(azar() < 0.3 ? "\n" : " "));
      }
      const texto = partes.join(azar() < 0.5 ? "\n\n" : "\n");
      const max = 40 + Math.floor(azar() * 400);
      const r = partirTexto(texto, max);
      for (const b of r) {
        expect(b.length).toBeLessThanOrEqual(max);
        expect(b.length).toBeGreaterThan(0);
      }
      expect(normalizar(r.join(" "))).toBe(normalizar(texto));
    }
  });

  it("rechaza un máximo absurdo", () => {
    expect(() => partirTexto("hola", 5)).toThrow();
  });
});

describe("prepararBurbujas", () => {
  it("parte las demasiado largas y descarta las vacías", () => {
    const r = prepararBurbujas(["Hola", "", "  ", "x ".repeat(1000)]);
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(r.burbujas[0]).toBe("Hola");
      expect(r.burbujas.length).toBeGreaterThan(2);
      for (const b of r.burbujas) expect(b.length).toBeLessThanOrEqual(MAX_BURBUJA);
    }
  });

  it("frena un bucle desbocado: máximo de burbujas por petición", () => {
    const muchas = Array.from({ length: MAX_BURBUJAS + 1 }, (_, i) => `mensaje ${i}`);
    const r = prepararBurbujas(muchas);
    expect(r.ok).toBe(false);
    expect(prepararBurbujas(muchas.slice(0, MAX_BURBUJAS)).ok).toBe(true);
  });

  it("exige una lista de textos", () => {
    expect(prepararBurbujas("hola").ok).toBe(false);
    expect(prepararBurbujas(["ok", 5]).ok).toBe(false);
    expect(prepararBurbujas([]).ok).toBe(true);
  });
});

describe("partirPie (el pie de una foto)", () => {
  it("un pie corto queda como pie", () => {
    expect(partirPie("Cama Queen HK-BF-022")).toEqual({ pie: "Cama Queen HK-BF-022", resto: [] });
  });

  it("sin pie no hay pie", () => {
    expect(partirPie(undefined)).toEqual({ pie: undefined, resto: [] });
    expect(partirPie("  ")).toEqual({ pie: undefined, resto: [] });
  });

  it("un pie largo no se recorta en silencio: lo que sobra sale como texto", () => {
    const largo = "Esta cama es muy cómoda. ".repeat(100).trim();
    const { pie, resto } = partirPie(largo);
    expect(pie!.length).toBeLessThanOrEqual(MAX_PIE);
    expect(resto.length).toBeGreaterThan(0);
    expect(normalizar([pie, ...resto].join(" "))).toBe(normalizar(largo));
  });
});
