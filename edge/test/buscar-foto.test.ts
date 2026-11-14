/**
 * «Busca con una foto» en el borde (addons/dcasa_buscar_foto): la foto llega por POST a /shop/foto.
 *
 * El borde frena las ráfagas por IP (los topes por visitante, por hora y por día los pone Odoo), devuelve a la página con el
 * aviso de la tienda en vez de un texto suelto, y NUNCA guarda esa página: ni el POST ni /shop/foto están en la caché.
 */
import { describe, expect, it, vi } from "vitest";

import { cubetaDe, filtrarAutomatizados, FOTO_ESPERA, LIMITES, LimitadorMemoria, RUTA_FOTO } from "../src/bots";
import { handleRequest } from "../src/handler";
import { esRepetible, rutaEstatica } from "../src/routing";

const SITIO = "https://dcasapty.com";

function foto(ip: string): Request {
  return new Request(SITIO + RUTA_FOTO, {
    method: "POST",
    headers: { "CF-Connecting-IP": ip, "Content-Type": "multipart/form-data; boundary=x" },
    body: "--x\r\nContent-Disposition: form-data; name=\"foto\"\r\n\r\n/9j/4AAQ\r\n--x--\r\n",
  });
}

describe("Busca con una foto en el borde", () => {
  it("el POST de la foto tiene su propia cubeta; mirar la página no cuenta", () => {
    expect(cubetaDe("POST", "/shop/foto")).toBe("foto");
    expect(cubetaDe("POST", "/es/shop/foto")).toBe("foto");
    expect(cubetaDe("GET", "/shop/foto")).toBeNull();
    expect(cubetaDe("POST", "/shop/fotos")).toBeNull();
    expect(cubetaDe("POST", "/shop/cart/update")).toBe("carrito");
    expect(LIMITES.foto).toBeGreaterThan(0);
    expect(LIMITES.foto).toBeLessThanOrEqual(10);
  });

  it("al pasarse, vuelve a /shop/foto con el aviso (303), sin guardarse en ninguna caché", async () => {
    const limitador = new LimitadorMemoria(2);
    const estados: Response[] = [];
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    for (let i = 0; i < 3; i++) {
      const req = foto("200.5.5.5");
      estados.push((await filtrarAutomatizados(req, new URL(req.url), { foto: limitador })) ?? new Response("a Odoo"));
    }
    warn.mockRestore();
    expect(estados.slice(0, 2).map((r) => r.status)).toEqual([200, 200]);
    const corte = estados[2];
    expect(corte.status).toBe(303);
    expect(corte.headers.get("Location")).toBe(FOTO_ESPERA);
    expect(corte.headers.get("Cache-Control")).toBe("no-store");
    // Otra IP sigue normal.
    const otra = foto("200.5.5.6");
    expect(await filtrarAutomatizados(otra, new URL(otra.url), { foto: limitador })).toBeNull();
  });

  it("una ráfaga de fotos desde una IP no llega a Odoo después del límite", async () => {
    const forward = vi.fn(async () => new Response("<html>resultados</html>", { headers: { "Content-Type": "text/html" } }));
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const estados: number[] = [];
    for (let i = 0; i < LIMITES.foto + 2; i++) estados.push((await handleRequest(foto("200.7.7.7"), { forward })).status);
    warn.mockRestore();
    expect(estados.slice(0, LIMITES.foto).every((s) => s === 200)).toBe(true);
    expect(estados.slice(LIMITES.foto)).toEqual([303, 303]);
    expect(forward).toHaveBeenCalledTimes(LIMITES.foto);
  });

  it("ni el POST ni la página de la foto se guardan en el borde, y el POST nunca se repite", () => {
    for (const ruta of ["/shop/foto", "/shop/foto?espera=1"]) {
      expect(rutaEstatica(new URL(SITIO + ruta), "GET")).toBeNull();
      expect(rutaEstatica(new URL(SITIO + ruta), "POST")).toBeNull();
    }
    // La tienda sí se guarda (con la cámara en su barra): el cambio de interruptor la rehace (dcasa_tienda_borde).
    expect(rutaEstatica(new URL(SITIO + "/shop"), "GET")).toBe("/shop");
    // Si el enlace con el contenedor se corta a mitad, la foto no se manda dos veces a la IA.
    expect(esRepetible("POST", "/shop/foto")).toBe(false);
  });
});
