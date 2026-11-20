// Tercera vuelta del revisor (sobre f6a04a4): el freno por conexión de Odoo confía en X-Forwarded-For. ¿Lo puede
// falsificar un visitante a través del Worker? Todas pasan.
import { describe, expect, it, vi } from "vitest";

import { handleRequest } from "../src/handler";
import { forwardedHeaders } from "../src/routing";

describe("Tilopay, tercera vuelta: la IP que le llega a Odoo es la que pone Cloudflare, no la del visitante", () => {
  it("X-Forwarded-For y X-Real-IP del visitante se pisan con CF-Connecting-IP", () => {
    const pedido = new Request("https://dcasapty.com/payment/tilopay/return?order=X", {
      headers: {
        "CF-Connecting-IP": "203.0.113.9",
        "X-Forwarded-For": "1.1.1.1, 2.2.2.2",
        "X-Real-IP": "3.3.3.3",
        Forwarded: "for=4.4.4.4",
      },
    });
    const h = forwardedHeaders(pedido);
    expect(h.get("X-Forwarded-For")).toBe("203.0.113.9");
    expect(h.get("X-Real-IP")).toBe("203.0.113.9");
    expect(h.get("X-Forwarded-Host")).toBe("dcasapty.com");
  });

  it("de punta a punta: lo que recibe Odoo en /payment/tilopay/* lleva la IP de Cloudflare", async () => {
    const recibidas: Array<string | null> = [];
    const forward = vi.fn(async (pedido: Request) => {
      recibidas.push(pedido.headers.get("X-Forwarded-For"));
      return new Response("ok");
    });
    for (const ruta of ["/payment/tilopay/return?order=X", "/payment/tilopay/webhook"]) {
      await handleRequest(
        new Request(`https://dcasapty.com${ruta}`, {
          method: ruta.endsWith("webhook") ? "POST" : "GET",
          body: ruta.endsWith("webhook") ? "{}" : undefined,
          headers: { "CF-Connecting-IP": "198.51.100.7", "X-Forwarded-For": "9.9.9.9" },
        }),
        { forward, canonicalHost: "dcasapty.com" },
      );
    }
    expect(recibidas).toEqual(["198.51.100.7", "198.51.100.7"]);
  });

  it("caso límite (no ocurre en Cloudflare, que siempre pone CF-Connecting-IP): sin esa cabecera, la del visitante pasa", () => {
    const h = forwardedHeaders(new Request("https://dcasapty.com/x", { headers: { "X-Forwarded-For": "9.9.9.9" } }));
    expect(h.get("X-Forwarded-For")).toBe("9.9.9.9");
  });
});
