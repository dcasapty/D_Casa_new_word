/**
 * Revisión adversarial, tercera vuelta (2026-11-13), sobre a57dec6. Clientes inventados.
 */
import { describe, expect, it } from "vitest";
import type { LecturaImagen } from "../../src/motor/vision";
import { crearMundo } from "../helpers/mundo";

const PUBLICACION: LecturaImagen = { tipo: "publicacion", codigos: ["822F"], categoria: "cama", medida: "full", parece_pago: false, parece_identidad: false };
const deOdoo = (m: ReturnType<typeof crearMundo>) => m.odoo.mensajes.filter((x) => x.autor === "cliente").at(-1)!.adjuntos!;

describe("REVISIÓN 3: una foto de Messenger o Instagram (solo URL) no es un «fallo» del lector", () => {
  it("Meta manda la foto como URL; Juan no la baja ni la lee: no debe llegar a Odoo como «fallo» (avisa cada 10 min y cuenta para la alarma de Gerencia)", async () => {
    let lecturas = 0;
    const m = crearMundo({ mirarImagen: async () => (lecturas++, PUBLICACION) });
    m.guion([{ texto: "¡Qué buena! ¿Me dices el código?" }]);
    await m.conversar("¿tienen esta?", { adjuntos: [{ tipo: "imagen" as const, url: "https://lookaside.fbsbx.com/ig_messaging_cdn/?asset_id=1" }] });
    expect(lecturas).toBe(0);   // el lector nunca la ve: no falló
    expect(deOdoo(m)[0]).toMatchObject({ clase: "sin_leer" });
    expect(deOdoo(m)[0].sin_leer).not.toBe("fallo");
    expect(deOdoo(m)[0].sin_leer).toBe("sin_bajar");
  });
});
