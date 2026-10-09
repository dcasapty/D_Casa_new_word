/**
 * Regla 11 y voz de la marca (CLAUDE.md), vistas desde el CLIENTE: sea lo que sea que diga el modelo, lo que llega por el canal
 * es el pana de las casas: tuteo, sin emojis, sin gritos, sin «remate», burbujas cortas.
 * (Reescritura de las pruebas de «trato» del CRM de Baby Caleb, con la voz de D'CASA.)
 */
import { describe, expect, it } from "vitest";
import { crearMundo } from "../helpers/mundo";

const EMOJI = /\p{Extended_Pictographic}/u;

describe("lo que llega al cliente", () => {
  it("sin emojis, sin signos dobles y sin formato de documento", async () => {
    const m = crearMundo();
    m.guion([{ texto: "¡¡Claro que sí!! 😎🔥 ¿Qué medida buscas??\n## Opciones\n**grandes** o chicas" }]);
    await m.conversar("hola");
    const todo = m.canal.textos.join("\n");
    expect(todo).not.toMatch(EMOJI);
    expect(todo).not.toMatch(/[¡!]{2}|[¿?]{2}|##|\*\*/);
    expect(todo).toContain("¿Qué medida buscas?");
  });

  it("«remate» y «¡corre!» no salen: el modelo reescribe sin presión", async () => {
    const m = crearMundo();
    const g = m.guion([{ texto: "Esta cama está de REMATE, ¡CORRE antes de que se acabe!" }, { texto: "Esa cama te puede gustar. ¿Quieres que te cuente de las medidas?" }]);
    await m.conversar("¿qué camas tienen?");
    const todo = m.canal.textos.join("\n");
    expect(todo).not.toMatch(/remate|corre/i);
    expect(todo).toContain("¿Quieres que te cuente de las medidas?");
    expect(g.prompts()[1]).toMatch(/palabra que la marca no usa/i);
  });

  it("si lo único que dijo fue presión de venta, no sale esa oración", async () => {
    const m = crearMundo();
    m.guion([{ texto: "¡Corre, última oportunidad! ¿Qué mueble buscas?" }]);
    await m.conversar("hola");
    const todo = m.canal.textos.join("\n");
    expect(todo).not.toMatch(/corre|oportunidad/i);
    expect(todo).toContain("¿Qué mueble buscas?");
  });

  it("las palabras que la dueña prohíbe en Odoo tampoco salen, aunque el modelo las use", async () => {
    const m = crearMundo({ config: { palabras_prohibidas: ["ganga", "regalado"] } });
    m.guion([{ texto: "Está regalado, es una ganga." }, { texto: "Es una buena opción para tu sala." }]);
    await m.conversar("¿cómo está el sofá?");
    const todo = m.canal.textos.join("\n");
    expect(todo).not.toMatch(/ganga|regalado/i);
    expect(todo).toContain("buena opción");
  });

  it("las palabras prohibidas viajan al prompt, para que el modelo no las intente", async () => {
    const m = crearMundo({ config: { palabras_prohibidas: ["ganga"] } });
    const g = m.guion([{ texto: "Dime qué buscas." }]);
    await m.conversar("hola");
    expect(g.prompts()[0]).toContain("«ganga»");
  });
});

describe("burbujas cortas (2 a 4 líneas)", () => {
  const parrafo = "Tenemos varias opciones de camas para tu cuarto y te cuento de cada una con calma. ";

  it("una respuesta larga sale en varias burbujas, cada una de máximo 4 líneas", async () => {
    const m = crearMundo();
    m.guion([{ texto: Array.from({ length: 6 }, (_, i) => `${parrafo.trim()} Punto ${i + 1}.`).join("\n\n") }]);
    await m.conversar("cuéntame de las camas");
    const burbujas = m.canal.textos;
    expect(burbujas.length).toBeGreaterThan(1);
    for (const b of burbujas) expect(b.split("\n").length).toBeLessThanOrEqual(4);
  });

  it("nunca más de 4 burbujas por respuesta; lo que sobra se junta en la última, sin perder nada", async () => {
    const m = crearMundo();
    const partes = Array.from({ length: 10 }, (_, i) => `Párrafo ${i + 1}: ${parrafo.repeat(2).trim()}`);
    m.guion([{ texto: partes.join("\n\n") }]);
    await m.conversar("cuéntame todo");
    // La presentación del primer mensaje es aparte; el resto de la respuesta no pasa de 4.
    const todo = m.canal.textos.join("\n");
    for (const p of partes) expect(todo).toContain(`Párrafo ${partes.indexOf(p) + 1}:`);
    expect(m.canal.salidas.every((s) => s.burbujas.length <= 5)).toBe(true);
  });

  it("una respuesta corta es una sola burbuja", async () => {
    const m = crearMundo();
    m.guion([{ texto: "Claro. ¿Qué medida buscas?" }]);
    await m.conversar("hola");
    expect(m.canal.textos.at(-1)).toBe("Claro. ¿Qué medida buscas?");
  });
});

describe("tuteo y presentación", () => {
  it("la presentación va primero, en tuteo, sin emojis, y ofrece una persona", async () => {
    const m = crearMundo();
    m.guion([{ texto: "¿Qué estás buscando?" }]);
    await m.conversar("hola");
    const primera = m.canal.textos[0];
    expect(primera).toMatch(/asistente autom[aá]tico/i);
    expect(primera).toMatch(/persona|vendedora/i);
    expect(primera).not.toMatch(EMOJI);
    expect(primera).not.toMatch(/\busted\b/i);
  });

  it("solo se presenta una vez: el segundo mensaje no repite la presentación", async () => {
    const m = crearMundo();
    m.guion([{ texto: "¿Qué estás buscando?" }, { texto: "Dime la medida." }]);
    await m.conversar("hola");
    const antes = m.canal.textos.length;
    await m.conversar("busco una cama");
    const nuevos = m.canal.textos.slice(antes);
    expect(nuevos.join(" ")).not.toMatch(/asistente autom[aá]tico/i);
  });

  it("la presentación de Odoo manda si dice que es automático; si no, se usa la nuestra", async () => {
    const propia = crearMundo({ config: { mensaje_bienvenida: "Hola, soy el asistente automático de D'CASA. ¿Qué buscas?" } });
    propia.guion([{ texto: "Dime la medida." }]);
    await propia.conversar("hola");
    expect(propia.canal.textos[0]).toBe("Hola, soy el asistente automático de D'CASA. ¿Qué buscas?");

    const enganosa = crearMundo({ config: { mensaje_bienvenida: "Hola, soy Karina de la tienda." } });
    enganosa.guion([{ texto: "Dime la medida." }]);
    await enganosa.conversar("hola");
    expect(enganosa.canal.textos[0]).toMatch(/asistente autom[aá]tico/i);
    expect(enganosa.canal.textos.join("\n")).not.toContain("soy Karina");
  });
});

describe("el nombre del negocio", () => {
  it("usa el nombre público que fija Odoo en el prompt", async () => {
    const m = crearMundo({ config: { nombre_publico: "D'CASA Panamá" } });
    const g = m.guion([{ texto: "Dime qué buscas." }]);
    await m.conversar("hola");
    expect(g.prompts()[0]).toContain("D'CASA Panamá");
  });
});
