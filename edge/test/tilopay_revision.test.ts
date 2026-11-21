// Pruebas de la revisión independiente de Tilopay (2026-11-19, etiqueta rv_tilopay): intentos de colar /payment/tilopay/*
// por una caché o un bloqueo del borde. Todas pasan; quedan como cobertura.
import { describe, expect, it, vi } from "vitest";

import { handleRequest, variablesDelContenedor } from "../src/handler";
import { isBlockedPath, route } from "../src/routing";

describe("rv_tilopay: rutas de Tilopay frente al borde", () => {
  const raras = [
    "/payment/tilopay/return.css",
    "/payment/tilopay/return.png?unique=abc",
    "/payment/tilopay/../tilopay/return",
    "/%70ayment/tilopay/webhook",
    "/payment/tilopay//webhook",
    "/payment/%2e%2e/payment/tilopay/return",
    "/es/payment/tilopay/webhook.js",
    "/payment/tilopay/static/x.png",
  ];

  it("ninguna variante se vuelve cacheable ni cae en una ruta bloqueada", () => {
    for (const ruta of raras) {
      for (const metodo of ["GET", "HEAD", "POST"]) {
        const url = new URL(`https://dcasapty.com${ruta}`);
        expect(isBlockedPath(url.pathname), ruta).toBe(false);
        const decision = route(url, metodo, "dcasapty.com");
        expect(decision, `${metodo} ${ruta}`).toEqual({ kind: "origin", cacheable: false });
      }
    }
  });

  it("una respuesta 'public' de Odoo en esa ruta no se guarda aunque venga marcada así", async () => {
    const cache = { match: vi.fn(async () => undefined), put: vi.fn(async () => undefined) };
    const forward = vi.fn(
      async () => new Response("ok", { status: 200, headers: { "Cache-Control": "public, max-age=3600" } }),
    );
    for (const ruta of ["/payment/tilopay/return?code=1&order=X", "/payment/tilopay/return.png"]) {
      const r = await handleRequest(new Request(`https://dcasapty.com${ruta}`), { forward, cache, canonicalHost: "dcasapty.com" });
      expect(r.status).toBe(200);
    }
    expect(cache.put).not.toHaveBeenCalled();
    expect(cache.match).not.toHaveBeenCalled();
  });

  it("las claves de Tilopay no viajan al contenedor si llegan con espacios o vacías, y nunca se inventan", () => {
    const env = { TILOPAY_API_KEY: "   ", TILOPAY_API_USER: "", TILOPAY_ENTORNO: "produccion" };
    const llegan = variablesDelContenedor(env);
    expect(llegan).not.toHaveProperty("TILOPAY_API_USER");
    expect(llegan).not.toHaveProperty("TILOPAY_API_PASSWORD");
    // (informativo) una cadena de solo espacios SÍ se pasa tal cual: Odoo la recorta y la toma como ausente.
    expect(llegan.TILOPAY_API_KEY).toBe("   ");
  });
});
