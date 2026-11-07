/**
 * Issue #24 · Un turno puede correr el modelo una segunda vez: cuando gastó sus pasos consultando sin escribir (`sinTexto`) o cuando
 * la guardia de salida rechazó el borrador (pasada de corrección). Esa segunda pasada partía SIN la ronda de herramientas de la
 * primera: el modelo se quedaba sin los datos que consultó y volvía a llamar las de escritura (`anotar_conversacion`,
 * `pasar_a_vendedora`, `crear_oportunidad` llegaban dos veces a Odoo). Ahora la ronda viaja a la segunda pasada y, dentro de un
 * mismo turno, la misma escritura con los mismos argumentos corre una sola vez (`pasar_a_vendedora`, una sola vez con lo que sea).
 */
import { describe, expect, it } from "vitest";
import { MAX_ESCRITURAS_POR_TURNO } from "../../src/motor/herramientas";
import { crearMundo } from "../helpers/mundo";
import { RechazoDeOdoo } from "../helpers/odooFalso";

const VER = { nombre: "ver_producto", args: { codigo: "CAMA-Q-001" } };
const NOTA = { nombre: "anotar_conversacion", args: { nota: "Quiere la queen para el sábado." } };
const OPORTUNIDAD = { nombre: "crear_oportunidad", args: { resumen: "Cama Queen Milán", interes: "cama queen" } };

describe("la segunda pasada del turno conserva lo que hizo la primera (issue #24)", () => {
  it("sin texto tras gastar los pasos: el modelo escribe CON los datos que ya consultó", async () => {
    const m = crearMundo();
    const g = m.guion([...Array.from({ length: 6 }, () => ({ llamadas: [VER] })), { texto: "La Cama Queen Milán cuesta $499.00 + ITBMS y mide 160 x 200 cm." }]);
    await m.conversar("¿cuánto cuesta la cama queen?");
    expect(g.doGenerateCalls.length).toBe(7);
    const reintento = g.prompts()[6];
    expect(reintento).toContain("160 x 200 cm");
    expect(reintento).toContain("lo_que_ya_consultaste");
    expect(m.canal.textos.at(-1)).toContain("$499.00 + ITBMS");
  });

  it("la pasada de corrección ve su ronda de herramientas y no repite las escrituras en Odoo", async () => {
    const m = crearMundo();
    const g = m.guion([
      { llamadas: [VER, NOTA, OPORTUNIDAD] },
      { texto: "La Cama Queen Milán cuesta $1,234.00 + ITBMS." }, // precio inventado: la guardia pide corregir
      { llamadas: [NOTA, OPORTUNIDAD] }, // el modelo, por las dudas, lo vuelve a anotar
      { texto: "La Cama Queen Milán cuesta $499.00 + ITBMS." },
    ]);
    await m.conversar("quiero la cama queen para el sábado");
    await m.pasar(60_000);
    const correccion = g.prompts()[2];
    expect(correccion).toContain("<correccion>");
    expect(correccion).toContain("160 x 200 cm");
    expect(m.odoo.de("anotar_conversacion")).toHaveLength(1);
    expect(m.odoo.de("crear_oportunidad")).toHaveLength(1);
    expect(m.canal.textos.at(-1)).toContain("$499.00 + ITBMS");
  });

  it("pasar a una vendedora corre una sola vez por turno, aunque la segunda pasada lo pida con otro motivo", async () => {
    const m = crearMundo();
    m.guion([
      { llamadas: [{ nombre: "pasar_a_vendedora", args: { motivo: "Quiere financiamiento" } }] },
      { texto: "Te paso con una vendedora; el financiamiento sale en $1,234 al mes." }, // cifra inventada: corrección
      { llamadas: [{ nombre: "pasar_a_vendedora", args: { motivo: "Pidió financiamiento con un banco" } }] },
      { texto: "Listo, ya avisé a una vendedora para que te cuente del financiamiento." },
    ]);
    await m.conversar("¿tienen financiamiento?");
    expect(m.odoo.de("pasar_a_vendedora")).toHaveLength(1);
  });

  it("un rechazo de pasar_a_vendedora no se recuerda: la llamada corregida llega a Odoo y el cliente pasa a una persona", async () => {
    const m = crearMundo();
    const manejadores = (m.odoo as unknown as { manejadores: Record<string, (a: Record<string, unknown>, o: unknown) => unknown> }).manejadores;
    const original = manejadores.pasar_a_vendedora;
    manejadores.pasar_a_vendedora = (a, o) => {
      if (!String(a.motivo ?? "").trim()) throw new RechazoDeOdoo("Cuéntale a la vendedora por qué se la pasas.");
      return original(a, o);
    };
    m.guion([
      { llamadas: [{ nombre: "pasar_a_vendedora", args: { motivo: "" } }] },
      { llamadas: [{ nombre: "pasar_a_vendedora", args: { motivo: "Quiere pagar con tarjeta ya" } }] },
      { texto: "Listo, ya avisé a una vendedora." },
    ]);
    await m.conversar("quiero pagar ya, con tarjeta");
    expect(m.odoo.de("pasar_a_vendedora").map((l) => l.args.motivo)).toEqual(["", "Quiere pagar con tarjeta ya"]);
    expect(m.motor.silencio()).toBe(true);
  });

  it("dos pasar_a_vendedora en el mismo paso: si Odoo rechaza la primera, la segunda (con sus argumentos) llega igual", async () => {
    const m = crearMundo();
    const manejadores = (m.odoo as unknown as { manejadores: Record<string, (a: Record<string, unknown>, o: unknown) => unknown> }).manejadores;
    const original = manejadores.pasar_a_vendedora;
    manejadores.pasar_a_vendedora = (a, o) => {
      if (!String(a.motivo ?? "").trim()) throw new RechazoDeOdoo("Cuéntale a la vendedora por qué se la pasas.");
      return original(a, o);
    };
    m.guion([
      { llamadas: [{ nombre: "pasar_a_vendedora", args: { motivo: "" } }, { nombre: "pasar_a_vendedora", args: { motivo: "Quiere pagar con tarjeta ya" } }] },
      { texto: "Listo, ya avisé a una vendedora." },
    ]);
    await m.conversar("quiero pagar ya, con tarjeta");
    expect(m.odoo.de("pasar_a_vendedora").map((l) => l.args.motivo)).toEqual(["", "Quiere pagar con tarjeta ya"]);
    expect(m.motor.silencio()).toBe(true);
  });

  it("dos pasar_a_vendedora en el mismo paso que salen bien llegan a Odoo una sola vez", async () => {
    const m = crearMundo();
    m.guion([
      { llamadas: [{ nombre: "pasar_a_vendedora", args: { motivo: "Quiere pagar" } }, { nombre: "pasar_a_vendedora", args: { motivo: "Quiere pagar con tarjeta" } }] },
      { texto: "Listo, ya avisé a una vendedora." },
    ]);
    await m.conversar("quiero pagar ya, con tarjeta");
    expect(m.odoo.de("pasar_a_vendedora")).toHaveLength(1);
  });

  it("un rechazo con unos argumentos no frena la misma herramienta con otros", async () => {
    const m = crearMundo();
    const manejadores = (m.odoo as unknown as { manejadores: Record<string, (a: Record<string, unknown>, o: unknown) => unknown> }).manejadores;
    const original = manejadores.crear_oportunidad;
    manejadores.crear_oportunidad = (a, o) => {
      if (!a.interes) throw new RechazoDeOdoo("Faltan datos: interes.");
      return original(a, o);
    };
    m.guion([
      { llamadas: [{ nombre: "crear_oportunidad", args: { resumen: "Cama queen" } }] },
      { llamadas: [{ nombre: "crear_oportunidad", args: { resumen: "Cama queen", interes: "cama queen" } }] },
      { texto: "Anotado." },
    ]);
    await m.conversar("quiero una cama queen");
    expect(m.odoo.de("crear_oportunidad")).toHaveLength(2);
  });

  it("la misma escritura con OTROS argumentos sí corre (dos notas distintas son dos notas)", async () => {
    const m = crearMundo();
    m.guion([{ llamadas: [NOTA, { nombre: "anotar_conversacion", args: { nota: "Prefiere color gris." } }] }, { texto: "Anotado." }]);
    await m.conversar("la quiero gris, para el sábado");
    expect(m.odoo.de("anotar_conversacion")).toHaveLength(2);
  });

  it(`un modelo desbocado no escribe más de ${MAX_ESCRITURAS_POR_TURNO} veces en Odoo en un turno`, async () => {
    const m = crearMundo();
    const notas = Array.from({ length: MAX_ESCRITURAS_POR_TURNO + 4 }, (_, i) => ({ nombre: "anotar_conversacion", args: { nota: `Nota ${i}` } }));
    m.guion([{ llamadas: notas }, { texto: "Listo." }]);
    await m.conversar("hola");
    expect(m.odoo.de("anotar_conversacion")).toHaveLength(MAX_ESCRITURAS_POR_TURNO);
  });

  it("una escritura que falló por Odoo caído se puede intentar otra vez en el mismo turno (no se recuerda el fallo)", async () => {
    const m = crearMundo();
    let fallar = true;
    const herramienta = m.odoo.herramienta.bind(m.odoo);
    m.odoo.herramienta = async (nombre, args, id) => {
      if (nombre === "anotar_conversacion" && fallar) {
        fallar = false;
        return { ok: false, resultado: undefined };
      }
      return herramienta(nombre, args, id);
    };
    m.guion([{ llamadas: [NOTA] }, { llamadas: [NOTA] }, { texto: "Anotado." }]);
    await m.conversar("la quiero para el sábado");
    expect(m.odoo.de("anotar_conversacion")).toHaveLength(1);
  });
});
