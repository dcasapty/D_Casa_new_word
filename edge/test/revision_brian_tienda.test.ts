// Revisión adversarial de «Brian de la tienda» (2026-11-14): FALLA con 66d01ac y pasa cuando se arregla.
import { describe, expect, it } from "vitest";
import { cubetaDe, filtrarAutomatizados, type Limitador } from "../src/bots";

describe("revisión: la cotización en PDF del chat", () => {
  it("GET /dcasa/brian/v1/carrito/cotizacion.pdf tiene límite por IP (cada uno arranca wkhtmltopdf en Odoo, workers = 0)", () => {
    // Hoy: null. Las lecturas nunca cuentan, y el tope de Odoo es por SESIÓN (10 por hora): con otra cookie, o con varias
    // peticiones a la vez antes de que la sesión se guarde, no frena nada.
    expect(cubetaDe("GET", "/dcasa/brian/v1/carrito/cotizacion.pdf")).not.toBeNull();
  });

  it("una ráfaga de PDF desde una IP recibe 429 en el borde", async () => {
    let n = 0;
    const limitador: Limitador = { limit: async () => ({ success: ++n <= 10 }) };
    const limitadores = { carrito: limitador, formulario: limitador, acceso: limitador, foto: limitador };
    let rechazadas = 0;
    for (let i = 0; i < 30; i++) {
      const url = new URL("https://dcasapty.com/dcasa/brian/v1/carrito/cotizacion.pdf");
      const req = new Request(url, { headers: { "CF-Connecting-IP": "190.140.12.34", "User-Agent": "Mozilla/5.0" } });
      if (await filtrarAutomatizados(req, url, limitadores)) rechazadas++;
    }
    expect(rechazadas).toBeGreaterThan(0);
  });
});
