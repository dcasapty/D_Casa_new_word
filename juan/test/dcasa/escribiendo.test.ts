/**
 * Las vendedoras ven en su pantalla cuándo el asistente está preparando una respuesta: el motor le avisa a Odoo UNA vez al
 * empezar y UNA al terminar (cuente lo que cuente la IA). Es un extra: si Odoo no lo recibe, la conversación sigue igual.
 */
import { describe, expect, it } from "vitest";
import { crearMundo } from "../helpers/mundo";

describe("«escribiendo» para las pantallas de Odoo", () => {
  it("avisa que empezó y que terminó, una sola vez cada cosa", async () => {
    const m = crearMundo();
    m.guion([{ texto: "Claro que sí, ¿para cuántas personas?" }]);
    await m.conversar("Hola, busco una cama");
    expect(m.odoo.escribiendos).toEqual([true, false]);
  });

  it("con herramientas de por medio (varias señales de «escribiendo» al cliente) a Odoo sigue yendo una sola", async () => {
    const m = crearMundo();
    m.guion([{ llamadas: [{ nombre: "buscar_productos", args: { consulta: "cama queen" } }] }, { texto: "Tenemos varias camas queen." }]);
    await m.conversar("¿Tienen camas queen?");
    expect(m.odoo.escribiendos).toEqual([true, false]);
  });

  it("si la IA falla, igual avisa que terminó (la pantalla no se queda «escribiendo»)", async () => {
    const m = crearMundo();
    m.guion([{ error: new Error("sin cupo") }]);
    await m.conversar("Hola");
    expect(m.odoo.escribiendos.at(-1)).toBe(false);
    expect(m.odoo.escribiendos.filter((x) => x)).toHaveLength(1);
  });

  it("si Odoo no recibe la señal, el cliente igual recibe su respuesta", async () => {
    const m = crearMundo();
    m.odoo.escribiendo = async () => {
      throw new Error("Odoo no contesta");
    };
    m.guion([{ texto: "Hola, ¿en qué te ayudo?" }]);
    await m.conversar("Hola");
    expect(m.canal.textos.join(" ")).toContain("¿en qué te ayudo?");
  });

  it("si el bot está apagado o hay una persona atendiendo, no se dice que está escribiendo", async () => {
    const m = crearMundo();
    m.odoo.estadoActual = { ...m.odoo.estadoActual, bot_activo: false };
    m.guion([{ texto: "no debe salir" }]);
    await m.conversar("Hola");
    expect(m.odoo.escribiendos).toEqual([]);
  });
});

describe("el gasto de IA también se anota por día", () => {
  it("cada turno suma al día de hoy del negocio (la gráfica de Costos de IA no depende de que alguien abra la pantalla)", async () => {
    const m = crearMundo();
    m.guion([{ texto: "Hola, ¿en qué te ayudo?" }]);
    await m.conversar("Hola");
    const dias = m.gastoGlobal.gastoPorDia("2026-10");
    expect(dias).toHaveLength(1);
    expect(dias[0].turnos).toBe(1);
    expect(dias[0].usd).toBeGreaterThan(0);
    expect(dias[0].usd).toBeCloseTo(m.gastoGlobal.gastoMes("2026-10").usd, 8);
  });
});
