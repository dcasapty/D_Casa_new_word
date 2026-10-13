/**
 * `POST /odoo/embeber`: la huella de significado de unos textos. Con un Workers AI falso: se prueba qué recibe el modelo, que lo
 * que contesta se valida (forma y largo del vector), que sin el binding `AI` no se rompe nada y que la ruta pide el token de Odoo.
 */
import { describe, expect, it } from "vitest";
import type { Env } from "../src/env";
import { DIMENSIONES, MODELO_DE_VECTORES, embeber, manejarEmbeber, validarTextos, vectoresDe } from "../src/odoo-panel-embeber";

const vector = (valor = 0.123456789) => Array.from({ length: DIMENSIONES }, () => valor);

function iaFalsa(responder: (entrada: { text: string[] }) => unknown) {
  const llamadas: { modelo: string; entrada: { text: string[] } }[] = [];
  const ai = {
    async run(modelo: string, entrada: unknown) {
      llamadas.push({ modelo, entrada: entrada as { text: string[] } });
      return responder(entrada as { text: string[] });
    },
  };
  return { ai, llamadas };
}

const buenaIa = () => iaFalsa(({ text }) => ({ shape: [text.length, DIMENSIONES], data: text.map(() => vector()) }));
const req = (cuerpo: unknown, metodo = "POST") =>
  new Request("https://juan.example/odoo/embeber", { method: metodo, headers: { "content-type": "application/json" }, ...(metodo === "POST" ? { body: typeof cuerpo === "string" ? cuerpo : JSON.stringify(cuerpo) } : {}) });
const deps = { ahora: () => 0 };

describe("validar los textos", () => {
  it("acepta de 1 a 8 textos y les junta los espacios", () => {
    expect(validarTextos({ textos: ["  ¿instalan   los muebles?\n"] })).toEqual(["¿instalan los muebles?"]);
    expect(validarTextos({ textos: Array.from({ length: 8 }, (_, i) => `texto ${i}`) })).toHaveLength(8);
  });

  it("rechaza lo que no sirve, diciendo por qué", () => {
    expect(validarTextos({})).toMatch(/faltan los textos/);
    expect(validarTextos({ textos: [] })).toMatch(/faltan los textos/);
    expect(validarTextos({ textos: "hola" })).toMatch(/faltan los textos/);
    expect(validarTextos({ textos: Array.from({ length: 9 }, () => "x") })).toMatch(/como máximo 8/);
    expect(validarTextos({ textos: [3] })).toMatch(/cadena/);
    expect(validarTextos({ textos: ["   "] })).toMatch(/vacío/);
    expect(validarTextos({ textos: ["a".repeat(2001)] })).toMatch(/2000/);
  });
});

describe("validar lo que contesta Workers AI", () => {
  it("redondea a 4 decimales y conserva el orden", () => {
    const v = vectoresDe({ data: [vector(0.123456789), vector(-0.5)] }, 2)!;
    expect(v[0]![0]).toBe(0.1235);
    expect(v[1]![0]).toBe(-0.5);
  });

  it("devuelve null si no es lo esperado: cuántos, de cuántas dimensiones, números finitos", () => {
    expect(vectoresDe(null, 1)).toBeNull();
    expect(vectoresDe({}, 1)).toBeNull();
    expect(vectoresDe({ data: [vector()] }, 2)).toBeNull();
    expect(vectoresDe({ data: [[1, 2, 3]] }, 1)).toBeNull();
    expect(vectoresDe({ data: [[...vector().slice(1), Number.NaN]] }, 1)).toBeNull();
    expect(vectoresDe({ data: [[...vector().slice(1), "x"]] }, 1)).toBeNull();
  });
});

describe("embeber", () => {
  it("le pasa los textos tal cual al modelo multilingüe y devuelve un vector por texto", async () => {
    const { ai, llamadas } = buenaIa();
    const r = await embeber(["garantía de colchones", "armado a domicilio"], ai);
    expect(r.status).toBe(200);
    expect(r.cuerpo).toMatchObject({ ok: true, dimensiones: DIMENSIONES, modelo: MODELO_DE_VECTORES });
    expect((r.cuerpo.vectores as number[][]).length).toBe(2);
    expect(llamadas).toEqual([{ modelo: "@cf/baai/bge-m3", entrada: { text: ["garantía de colchones", "armado a domicilio"] } }]);
  });

  it("sin el binding AI: 503 con el NOMBRE que falta, sin lanzar", async () => {
    const r = await embeber(["hola"], undefined);
    expect(r.status).toBe(503);
    expect(r.cuerpo).toMatchObject({ ok: false, faltan: ["AI"] });
  });

  it("si Workers AI falla: 502 sin el mensaje interno", async () => {
    const { ai } = iaFalsa(() => {
      throw new Error("Bearer sk-secreto reventó");
    });
    const r = await embeber(["hola"], ai);
    expect(r.status).toBe(502);
    expect(JSON.stringify(r.cuerpo)).not.toContain("sk-secreto");
  });

  it("si contesta algo que no es un vector: 502", async () => {
    const { ai } = iaFalsa(() => ({ data: [[1, 2, 3]] }));
    expect((await embeber(["hola"], ai)).status).toBe(502);
  });
});

describe("POST /odoo/embeber por HTTP", () => {
  it("solo POST", async () => {
    expect((await manejarEmbeber(req({}, "GET"), {} as Env, deps)).status).toBe(405);
  });

  it("un cuerpo que no es JSON o no es un objeto: 400", async () => {
    expect((await manejarEmbeber(req("no es json"), {} as Env, deps)).status).toBe(400);
    expect((await manejarEmbeber(req([1]), {} as Env, deps)).status).toBe(400);
  });

  it("textos inválidos: 400 y la IA ni se toca", async () => {
    const { ai, llamadas } = buenaIa();
    const res = await manejarEmbeber(req({ textos: [] }), {} as Env, deps, ai);
    expect(res.status).toBe(400);
    expect(llamadas).toEqual([]);
  });

  it("va sin caché y devuelve los vectores", async () => {
    const { ai } = buenaIa();
    const res = await manejarEmbeber(req({ textos: ["horario"] }), {} as Env, deps, ai);
    expect(res.status).toBe(200);
    expect(res.headers.get("cache-control")).toBe("no-store");
    expect((await res.json<any>()).vectores).toHaveLength(1);
  });

  it("toma el binding AI del entorno cuando no se le pasa otro", async () => {
    const { ai, llamadas } = buenaIa();
    const res = await manejarEmbeber(req({ textos: ["horario"] }), { AI: ai } as unknown as Env, deps);
    expect(res.status).toBe(200);
    expect(llamadas).toHaveLength(1);
  });
});
