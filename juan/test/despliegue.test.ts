// Guardas de la configuración de Cloudflare de `juan` que no se pueden probar ejecutándola (no se despliega nada).
// Nacieron de la integración real con Odoo (test/integracion): el binding DCASA no declaraba `entrypoint`, así que en
// Cloudflare el Worker `juan` habría llamado al `fetch` PÚBLICO del Worker `dcasa` —donde /dcasa/juan/** da 404— y no a
// la clase `JuanEntrada` (edge/src/juan.ts) que sí reenvía a Odoo. Ninguna prueba de cada lado lo veía.
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const leer = (ruta: string) => readFileSync(new URL(ruta, import.meta.url), "utf8");

/** Quita comentarios `//` y `/* *​/` de un JSONC respetando las cadenas (las URL llevan «//»). */
function jsonc(texto: string): any {
  let salida = "";
  let enCadena = false;
  for (let i = 0; i < texto.length; i++) {
    const c = texto[i];
    const n = texto[i + 1];
    if (enCadena) {
      salida += c;
      if (c === "\\") salida += texto[++i];
      else if (c === '"') enCadena = false;
    } else if (c === '"') {
      enCadena = true;
      salida += c;
    } else if (c === "/" && n === "/") {
      while (i < texto.length && texto[i] !== "\n") i++;
      salida += "\n";
    } else if (c === "/" && n === "*") {
      i += 2;
      while (i < texto.length && !(texto[i] === "*" && texto[i + 1] === "/")) i++;
      i++;
    } else salida += c;
  }
  return JSON.parse(salida.replace(/,(\s*[}\]])/g, "$1"));
}

const juan = jsonc(leer("../wrangler.jsonc"));
const borde = jsonc(leer("../../edge/wrangler.jsonc"));

describe("el binding DCASA entra por JuanEntrada, no por el fetch público del Worker dcasa", () => {
  const dcasa = (servicios: { binding: string; service: string; entrypoint?: string }[]) => servicios.find((s) => s.binding === "DCASA");

  it("producción: service «dcasa» + entrypoint «JuanEntrada»", () => {
    expect(dcasa(juan.services)).toEqual({ binding: "DCASA", service: borde.name, entrypoint: "JuanEntrada" });
  });

  it("staging: service «dcasa-staging» + entrypoint «JuanEntrada»", () => {
    expect(dcasa(juan.env.staging.services)).toEqual({ binding: "DCASA", service: borde.env.staging.name, entrypoint: "JuanEntrada" });
  });

  it("el Worker dcasa exporta de verdad la clase JuanEntrada y es un WorkerEntrypoint con fetch", () => {
    const indice = leer("../../edge/src/index.ts");
    expect(indice).toMatch(/export class JuanEntrada extends WorkerEntrypoint<Env>/);
    expect(indice).toMatch(/class JuanEntrada[\s\S]*?override async fetch\(request: Request\)/);
  });

  it("el cliente de Odoo llama con fetch() al binding (lo que JuanEntrada implementa), no por RPC", () => {
    const cliente = leer("../src/odoo/cliente.ts");
    expect(cliente).toMatch(/this\.fetcher\.fetch\(/);
    expect(cliente).toContain("https://dcasa/dcasa/juan/v1");
  });
});

describe("los dos entornos (producción y staging) tienen las mismas piezas", () => {
  it("Durable Objects, migración, cron y bindings iguales", () => {
    const { env, ...produccion } = juan;
    const staging = env.staging;
    expect(staging.durable_objects).toEqual(produccion.durable_objects);
    expect(staging.migrations).toEqual(produccion.migrations);
    expect(staging.triggers).toEqual(produccion.triggers);
    expect(Object.keys(staging.vars).sort()).toEqual(Object.keys(produccion.vars).sort());
  });
});
