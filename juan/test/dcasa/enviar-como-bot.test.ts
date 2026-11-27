/**
 * `POST /odoo/enviar` con `autor: "bot"` (2026-11-25, docs/UBICACION.md): Odoo le escribe al cliente A NOMBRE DEL ASISTENTE (la zona
 * y el precio del envío cuando confirma su punto con el enlace de un solo uso). A diferencia de una vendedora: no calla a Juan, no corta
 * lo que traiga, y queda en la historia como mensaje del asistente (el modelo lo ve en el siguiente turno). Idempotente con `id_envio`,
 * igual que siempre. La validación de la ruta (cualquier otro valor = vendedora) está en test/rutas.test.ts.
 */
import { describe, expect, it } from "vitest";
import { crearMundo } from "../helpers/mundo";

describe("POST /odoo/enviar con autor «bot» (Odoo a nombre del asistente)", () => {
  const AVISO = "Listo, tu punto de entrega quedó guardado. El envío a Brisas del Golf cuesta $5.";

  it("sale por el canal, NO calla a Juan y queda en la historia como mensaje del asistente", async () => {
    const m = crearMundo();
    const g = m.guion([{ texto: "Con gusto. ¿Me compartes tu ubicación?" }, { texto: "Con gusto, te lo sumo." }]);
    // El cliente ya venía hablando (pidió el enlace para marcar su punto)…
    await m.conversar("¿cuánto es el envío?");
    const antes = m.canal.textos.length;
    // …y Odoo le escribe a nombre del asistente cuando confirma su punto.
    const r = await m.motor.enviarVendedora({ id_envio: "odoo-aviso-1", texto: AVISO, autor: "bot" });
    expect(r.ok).toBe(true);
    expect(m.canal.textos.slice(antes)).toEqual([AVISO]);
    expect(m.motor.silencio()).toBe(false);
    expect(m.motor.mensajes.ultimos(1)[0]).toMatchObject({ rol: "bot", texto: AVISO });
    // Lo manda Odoo, no el modelo: nada de «escribiendo».
    const escribiendo = [m.canal.escribiendoVeces, m.odoo.escribiendos.length];
    await m.motor.enviarVendedora({ id_envio: "odoo-aviso-1b", texto: "Cualquier duda, aquí estamos.", autor: "bot" });
    expect([m.canal.escribiendoVeces, m.odoo.escribiendos.length]).toEqual(escribiendo);
    // El cliente contesta y Juan la atiende, viendo el aviso como suyo (no como «[Vendedora]»).
    await m.conversar("sí, súmelo");
    expect(g.doGenerateCalls).toHaveLength(2);
    const prompt = g.prompts()[1];
    expect(prompt).toContain(`{"role":"assistant","content":[{"type":"text","text":"${AVISO}"}]}`);
    expect(prompt).not.toContain(`[Vendedora] ${AVISO}`);
  });

  it("su eco (Messenger, Instagram, el teléfono) se reconoce como eco: no parece una vendedora tomando la conversación", async () => {
    const m = crearMundo();
    await m.motor.enviarVendedora({ id_envio: "odoo-aviso-eco", texto: AVISO, autor: "bot" });
    const r = await m.escribir(AVISO, { propio: true });
    expect(r.accion).toBe("eco");
    expect(m.motor.silencio()).toBe(false);
  });

  it("idempotente con id_envio, igual que una vendedora: el reintento de Odoo no lo manda dos veces", async () => {
    const m = crearMundo();
    const a = await m.motor.enviarVendedora({ id_envio: "odoo-aviso-2", texto: AVISO, autor: "bot" });
    const b = await m.motor.enviarVendedora({ id_envio: "odoo-aviso-2", texto: AVISO, autor: "bot" });
    expect(m.canal.salidas).toHaveLength(1);
    expect(b).toMatchObject({ ok: true, repetido: true, id_mensaje: a.id_mensaje });
    expect(m.motor.mensajes.ultimos(5).filter((f) => f.texto === AVISO)).toHaveLength(1);
  });

  it("sin `autor` sigue siendo una vendedora: calla a Juan y queda como «vendedora»", async () => {
    const m = crearMundo();
    await m.motor.enviarVendedora({ id_envio: "odoo-v-1", texto: "Hola, soy Marisol." });
    expect(m.motor.silencio()).toBe(true);
    expect(m.motor.mensajes.ultimos(1)[0]).toMatchObject({ rol: "vendedora" });
  });

  it("un valor raro que llegue por RPC se trata como vendedora", async () => {
    const m = crearMundo();
    await m.motor.enviarVendedora({ texto: "Hola.", autor: "Bot" as unknown as "bot" });
    expect(m.motor.silencio()).toBe(true);
    expect(m.motor.mensajes.ultimos(1)[0]).toMatchObject({ rol: "vendedora" });
  });
});
