/**
 * Después de la ubicación, el número de casa o las indicaciones para el motorizado (el dueño, 2026-11-25: el dolor número uno son los
 * pedidos devueltos por direcciones malas; después de tener la ubicación SIEMPRE se pregunta, corto y con ícono):
 *
 *   · el turno que contesta a la ubicación compartida pide, al final del precio, la pregunta de las indicaciones (una sola vez);
 *   · lo que la clienta contesta va a Odoo con `guardar_indicaciones` (con la conversación), y el modelo se lo confirma;
 *   · ni el modelo, ni el almacén, ni el registro ven coordenadas en ningún paso.
 */
import { describe, expect, it } from "vitest";
import { crearMundo, type Mundo } from "../helpers/mundo";
import { DEF_GUARDAR_INDICACIONES, ENVIO_POR_UBICACION, HERRAMIENTAS_DE_PRUEBA } from "../helpers/odooFalso";
import { PREGUNTA_DE_INDICACIONES } from "../../src/dcasa/prompt";
import { TEXTO_UBICACION_COMPARTIDA, type UbicacionEntrante } from "../../src/canales/ubicacion";

const PUNTO: UbicacionEntrante = { lat: 9.0012345, lon: -79.5123456, origen: "whatsapp" };
const RASTROS = /9\.00123|79\.51234/;
const RESPUESTA_CON_PREGUNTA = `${ENVIO_POR_UBICACION.frase_para_el_cliente} ${PREGUNTA_DE_INDICACIONES}`;

function todoLoGuardado(m: Mundo): string {
  const tablas = m.deps.sql.todos<{ name: string }>("SELECT name FROM sqlite_master WHERE type = 'table'");
  return JSON.stringify(tablas.map((t) => m.deps.sql.todos(`SELECT * FROM ${t.name}`)));
}

function mundo() {
  const m = crearMundo();
  m.odoo.defs = [...HERRAMIENTAS_DE_PRUEBA, DEF_GUARDAR_INDICACIONES];
  return m;
}

describe("después de la ubicación: el número de casa o las indicaciones para el motorizado", () => {
  it("el turno que contesta a la ubicación pide la pregunta de las indicaciones al final del precio, y sale con su ícono", async () => {
    const m = mundo();
    const g = m.guion([{ texto: RESPUESTA_CON_PREGUNTA }]);
    await m.conversar(TEXTO_UBICACION_COMPARTIDA, { ubicacion: PUNTO });
    const prompt = g.prompts()[0];
    expect(prompt).toContain("<envio_por_ubicacion>");
    expect(prompt).toContain("Al final de ese mismo mensaje, si todavía no tiene su número de casa o las indicaciones para el motorizado, pregúnteselas una sola vez");
    expect(prompt).toContain(PREGUNTA_DE_INDICACIONES);
    expect(prompt).not.toMatch(RASTROS);
    // La guardia deja pasar el precio (respaldado por el envío ya cotizado) y la pregunta con su casita.
    const texto = m.canal.textos.join("\n");
    expect(texto).toContain("cuesta $5.");
    expect(texto).toContain(PREGUNTA_DE_INDICACIONES);
  });

  it("lo que contesta va a Odoo con guardar_indicaciones (con la conversación) y el modelo se lo confirma", async () => {
    const m = mundo();
    const g = m.guion([
      { texto: RESPUESTA_CON_PREGUNTA },
      { llamadas: [{ nombre: "guardar_indicaciones", args: { texto: "Casa 24, portón verde, frente al chino" } }] },
      { texto: "Listo, ya quedó para el motorizado." },
    ]);
    await m.conversar(TEXTO_UBICACION_COMPARTIDA, { ubicacion: PUNTO });
    await m.conversar("Casa 24, portón verde, frente al chino");
    expect(m.odoo.de("guardar_indicaciones")).toEqual([{ nombre: "guardar_indicaciones", args: { texto: "Casa 24, portón verde, frente al chino" }, conversacion_id: 12 }]);
    expect(m.odoo.indicaciones).toEqual(["Casa 24, portón verde, frente al chino"]);
    // El modelo vio lo que devolvió Odoo y contestó corto.
    expect(g.prompts()[2]).toContain('"guardado":true');
    expect(m.canal.textos.at(-1)).toBe("Listo, ya quedó para el motorizado.");
    await m.pasar(60_000);
    // Ninguna coordenada en ningún lado: ni el modelo, ni el almacén, ni el registro, ni lo que va a Odoo.
    expect(g.prompts().join("\n")).not.toMatch(RASTROS);
    expect(todoLoGuardado(m)).not.toMatch(RASTROS);
    expect(JSON.stringify([m.registros, m.odoo.mensajes, m.odoo.llamadas, m.canal.salidas])).not.toMatch(RASTROS);
  });

  it("guardar_indicaciones es una escritura: dos veces lo mismo en un turno va a Odoo una sola vez", async () => {
    const m = mundo();
    m.guion([
      { llamadas: [{ nombre: "guardar_indicaciones", args: { texto: "Casa 24" } }, { nombre: "guardar_indicaciones", args: { texto: "Casa 24" } }] },
      { texto: "Listo, ya quedó para el motorizado." },
    ]);
    await m.conversar("Casa 24");
    expect(m.odoo.de("guardar_indicaciones")).toHaveLength(1);
  });
});
