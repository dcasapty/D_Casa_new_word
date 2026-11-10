/**
 * Messenger e Instagram no mandan el nombre de quien escribe (solo un número): en Odoo salía «Messenger 2838…». Juan se lo pide al
 * canal una vez por conversación, antes de guardar el mensaje, y lo manda a Odoo con el mensaje (Odoo cambia el nombre provisional
 * por el real). Si el canal ya trae el nombre (WhatsApp, Telegram) no se pide nada; si falla, la conversación sigue igual.
 */
import { describe, expect, it } from "vitest";
import { crearMundo } from "../helpers/mundo";

const HORA = 3600_000;
const sinNombre = { nombre: undefined };

describe("el nombre del cliente de Messenger e Instagram", () => {
  it("con el primer mensaje se pide al canal y llega a Odoo con el mensaje del cliente", async () => {
    const m = crearMundo({ canal: "messenger", config: { canales_activos: { messenger: true } } });
    m.canal.nombre = "Ana Pérez";
    m.guion([{ texto: "Hola Ana, ¿qué buscas?" }]);
    await m.conversar("Hola", sinNombre);
    expect(m.canal.nombresPedidos).toBe(1);
    const delCliente = m.odoo.mensajes.filter((x) => x.direccion === "entrante");
    expect(delCliente[0]?.nombre).toBe("Ana Pérez");
    expect(m.canal.textos.join(" ")).toContain("Hola Ana");
  });

  it("no se vuelve a pedir en la misma conversación", async () => {
    const m = crearMundo({ canal: "messenger", config: { canales_activos: { messenger: true } } });
    m.canal.nombre = "Ana Pérez";
    m.guion([{ texto: "Claro." }]);
    await m.conversar("Hola", sinNombre);
    await m.conversar("¿Y la cama gris?", sinNombre);
    expect(m.canal.nombresPedidos).toBe(1);
    expect(m.odoo.mensajes.filter((x) => x.direccion === "entrante").every((x) => x.nombre === "Ana Pérez")).toBe(true);
  });

  it("si el canal ya trae el nombre (WhatsApp) no se pide nada", async () => {
    const m = crearMundo();
    m.canal.nombre = "Otro";
    m.guion([{ texto: "Hola" }]);
    await m.conversar("Hola");
    expect(m.canal.nombresPedidos).toBe(0);
    expect(m.odoo.mensajes[0]?.nombre).toBe("Karen");
  });

  it("si el canal falla o no lo sabe, la respuesta sale igual y se reintenta a la hora (no antes)", async () => {
    const m = crearMundo({ canal: "messenger", config: { canales_activos: { messenger: true } } });
    m.canal.nombre = new Error("Graph no contestó");
    m.guion([{ texto: "Claro que sí." }]);
    await m.conversar("Hola", sinNombre);
    expect(m.canal.textos.join(" ")).toContain("Claro que sí.");
    expect(m.canal.nombresPedidos).toBe(1);
    await m.conversar("Otra", sinNombre);
    expect(m.canal.nombresPedidos).toBe(1);
    m.canal.nombre = "Ana Pérez";
    await m.pasar(HORA + 60_000);
    await m.conversar("Ya pasó una hora", sinNombre);
    expect(m.canal.nombresPedidos).toBe(2);
    expect(m.odoo.mensajes.at(-1)?.nombre ?? m.odoo.mensajes.filter((x) => x.direccion === "entrante").at(-1)?.nombre).toBe("Ana Pérez");
  });
});
