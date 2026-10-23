import { describe, expect, it, vi } from "vitest";

import { handleRequest, REINTENTOS_REENVIO } from "../src/handler";
import { esCorteDeConexion, esRepetible, rutaParaRegistro } from "../src/routing";

/**
 * Producción, 23 oct: el enlace Worker → Durable Object se cortaba con «Network connection lost.» en fotos y lecturas
 * mientras las demás peticiones salían bien, y el panel de Odoo mostraba «Se perdió la conexión». Las lecturas se repiten;
 * lo que guarda nunca.
 */
const CORTE = "Error: Network connection lost.";

function forwardQueFalla(veces: number, error: unknown = new Error(CORTE)) {
  let fallos = 0;
  const cuerpos: string[] = [];
  const forward = vi.fn(async (pedido: Request) => {
    cuerpos.push(pedido.method === "POST" ? await pedido.text() : "");
    if (fallos < veces) {
      fallos += 1;
      throw error;
    }
    return Response.json({ jsonrpc: "2.0", result: [] });
  });
  return { forward, cuerpos };
}

const sinPausa = async () => {};

function llamada(modelo: string, metodo: string, cuerpo = '{"params":{"model":"x"}}') {
  return new Request(`https://dcasapty.com/web/dataset/call_kw/${modelo}/${metodo}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: cuerpo,
  });
}

describe("reenviar repite las lecturas si el enlace con el contenedor se corta", () => {
  it("una foto que falla una vez sale en el segundo intento", async () => {
    const errores = vi.spyOn(console, "error").mockImplementation(() => {});
    const { forward } = forwardQueFalla(1);
    const res = await handleRequest(new Request("https://dcasapty.com/web/image/product.template/39/image_128"), {
      forward,
      esperar: sinPausa,
    });
    expect(res.status).toBe(200);
    expect(forward).toHaveBeenCalledTimes(2);
    const registro = JSON.parse(String(errores.mock.calls[0][0]));
    expect(registro).toMatchObject({ evento: "reenvio_fallido", intento: 1, reintenta: true, metodo: "GET" });
    expect(registro.ruta).toBe("/web/image/product.template");
    errores.mockRestore();
  });

  it("una lectura de Odoo (POST) se repite con el mismo cuerpo", async () => {
    const errores = vi.spyOn(console, "error").mockImplementation(() => {});
    const { forward, cuerpos } = forwardQueFalla(2);
    const cuerpo = '{"jsonrpc":"2.0","params":{"model":"account.move","method":"web_search_read"}}';
    const res = await handleRequest(llamada("account.move", "web_search_read", cuerpo), { forward, esperar: sinPausa });
    expect(res.status).toBe(200);
    expect(forward).toHaveBeenCalledTimes(3);
    expect(cuerpos).toEqual([cuerpo, cuerpo, cuerpo]);
    errores.mockRestore();
  });

  it("las lecturas propias revisadas también (el panel de Conversaciones, el Inicio)", async () => {
    const errores = vi.spyOn(console, "error").mockImplementation(() => {});
    for (const [modelo, metodo] of [
      ["dcasa.conversacion", "iniciar_panel"],
      ["dcasa.tablero", "obtener_datos"],
    ]) {
      const { forward } = forwardQueFalla(1);
      const res = await handleRequest(llamada(modelo, metodo), { forward, esperar: sinPausa });
      expect(res.status).toBe(200);
      expect(forward).toHaveBeenCalledTimes(2);
    }
    errores.mockRestore();
  });

  it("lo que guarda, confirma o cobra NUNCA se repite: 503 amable al primer corte", async () => {
    const errores = vi.spyOn(console, "error").mockImplementation(() => {});
    for (const metodo of ["action_confirm", "write", "create", "action_post", "web_save", "unlink"]) {
      const { forward } = forwardQueFalla(1);
      const res = await handleRequest(llamada("sale.order", metodo), { forward, esperar: sinPausa });
      expect(res.status).toBe(503);
      expect(forward).toHaveBeenCalledOnce();
    }
    const registro = JSON.parse(String(errores.mock.calls[0][0]));
    expect(registro).toMatchObject({ intento: 1, reintenta: false, metodo: "POST" });
    errores.mockRestore();
  });

  it("si el corte sigue, se rinde tras los reintentos y responde el 503 amable", async () => {
    const errores = vi.spyOn(console, "error").mockImplementation(() => {});
    const { forward } = forwardQueFalla(99);
    const pausas: number[] = [];
    const res = await handleRequest(new Request("https://dcasapty.com/odoo/action-123"), {
      forward,
      esperar: async (ms) => void pausas.push(ms),
    });
    expect(res.status).toBe(503);
    expect(res.headers.get("Retry-After")).toBe("15");
    expect(forward).toHaveBeenCalledTimes(1 + REINTENTOS_REENVIO);
    expect(pausas).toEqual([400, 800]);
    errores.mockRestore();
  });

  it("si Cloudflare dice que está sobrecargado, no insiste", async () => {
    const errores = vi.spyOn(console, "error").mockImplementation(() => {});
    const sobrecargado = Object.assign(new Error("Durable Object is overloaded."), { overloaded: true, retryable: true });
    const { forward } = forwardQueFalla(1, sobrecargado);
    const res = await handleRequest(new Request("https://dcasapty.com/shop"), { forward, esperar: sinPausa });
    expect(res.status).toBe(503);
    expect(forward).toHaveBeenCalledOnce();
    errores.mockRestore();
  });
});

describe("qué se puede repetir", () => {
  it("GET y HEAD siempre; POST solo lecturas conocidas", () => {
    expect(esRepetible("GET", "/web/image/product.template/1/image_128")).toBe(true);
    expect(esRepetible("HEAD", "/shop")).toBe(true);
    expect(esRepetible("POST", "/web/dataset/call_kw/res.partner/web_read")).toBe(true);
    expect(esRepetible("POST", "/web/action/load")).toBe(true);
    expect(esRepetible("POST", "/web/dataset/call_kw/res.partner/web_save")).toBe(false);
    expect(esRepetible("POST", "/web/dataset/call_kw/dcasa.conversacion/enviar")).toBe(false);
    expect(esRepetible("POST", "/web/dataset/call_kw/otro.modelo/obtener_datos")).toBe(false);
    expect(esRepetible("POST", "/shop/cart/update_json")).toBe(false);
    expect(esRepetible("POST", "/dcasa/juan/v1/mensaje")).toBe(false);
    expect(esRepetible("PUT", "/web/image/x")).toBe(false);
  });

  it("solo los cortes de conexión se reintentan", () => {
    expect(esCorteDeConexion(new Error("Network connection lost."))).toBe(true);
    expect(esCorteDeConexion(new Error("Durable Object reset because its code was updated."))).toBe(true);
    expect(esCorteDeConexion(Object.assign(new Error("x"), { retryable: true }))).toBe(true);
    expect(esCorteDeConexion(Object.assign(new Error("x"), { retryable: true, overloaded: true }))).toBe(false);
    expect(esCorteDeConexion(new Error("arranque en pausa tras un fallo reciente"))).toBe(false);
  });

  it("el registro no guarda rutas largas (podrían llevar un token)", () => {
    expect(rutaParaRegistro("/web/dataset/call_kw/sale.order/web_read")).toBe("/web/dataset/call_kw/sale.order/web_read");
    expect(rutaParaRegistro("/my/orders/12/abc123token")).toBe("/my/orders/12");
  });
});
