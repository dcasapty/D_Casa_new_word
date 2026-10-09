/**
 * Regla 1 del contrato: «persona», «vendedora» o «humano» pasan SIEMPRE a una vendedora, y el bot se presenta como automático.
 * No depende del modelo: el motor lo resuelve antes de pensar en IA (aunque el modelo se negara, la persona entra).
 */
import { describe, expect, it } from "vitest";
import { pideUnaPersona } from "../../src/dcasa/intencion";
import { crearMundo } from "../helpers/mundo";

describe("cuándo el cliente está pidiendo una persona", () => {
  const SI = [
    "persona",
    "Persona",
    "PERSONA!!",
    "  persona  ",
    "vendedora",
    "vendedor",
    "humano",
    "una persona",
    "una persona por favor",
    "quiero una persona",
    "quiero hablar con una persona",
    "quiero hablar con un humano",
    "necesito una vendedora",
    "necesito hablar con alguien",
    "pásame con una vendedora",
    "pasame con un asesor",
    "me pasas con una persona?",
    "puedo hablar con una vendedora?",
    "hola, quiero una vendedora",
    "hablar con alguien real",
    "quiero hablar con una persona de verdad",
    "no quiero hablar con un bot",
    "prefiero una persona",
    "que me atienda una persona",
    "con alguien de verdad por favor",
    "Atención humana",
  ];
  it.each(SI)("sí: «%s»", (t) => {
    expect(pideUnaPersona(t), t).toBe(true);
  });

  const NO = [
    "hola",
    "cama para una persona",
    "somos tres personas en la casa",
    "una persona me dijo que tienen descuento",
    "quiero una cama individual para una persona",
    "la vendedora que me atendió ayer fue muy amable, quiero la misma cama",
    "¿cuánto cuesta la mesa para 6 personas?",
    "el humano promedio duerme 8 horas, ¿qué colchón me recomiendas?",
    "mi sobrino es muy buena persona y quiere un escritorio",
    "",
  ];
  it.each(NO)("no: «%s»", (t) => {
    expect(pideUnaPersona(t), t).toBe(false);
  });
});

describe("«persona» siempre pasa a una vendedora", () => {
  it("llama a pasar_a_vendedora SIN esperar a la IA, y dice lo que Odoo manda decir", async () => {
    const m = crearMundo();
    const g = m.guion([{ texto: "(el modelo no debe ni enterarse)" }]);
    await m.conversar("persona");
    expect(g.doGenerateCalls.length).toBe(0);
    expect(m.odoo.de("pasar_a_vendedora")).toHaveLength(1);
    expect(m.odoo.de("pasar_a_vendedora")[0].args.motivo).toMatch(/persona/);
    expect(m.canal.textos.join("\n")).toContain("Listo, ya avisé a una vendedora");
  });

  it("no espera los 15 s de la ráfaga: contesta en un par de segundos", async () => {
    const m = crearMundo();
    m.guion([{ texto: "x" }]);
    await m.escribir("quiero hablar con una vendedora");
    await m.pasar(2_000);
    expect(m.canal.textos.join("\n")).toContain("ya avisé a una vendedora");
  });

  it("fuera de horario dice lo que Odoo dice para ese horario", async () => {
    const m = crearMundo();
    m.odoo.estadoActual = { ...m.odoo.estadoActual, dentro_de_horario: false };
    m.guion([{ texto: "x" }]);
    await m.conversar("vendedora");
    expect(m.canal.textos.join("\n")).toContain("cuando abramos");
  });

  it("después de pasar, el bot se calla: los mensajes siguientes se guardan y no se contestan", async () => {
    const m = crearMundo();
    const g = m.guion([{ texto: "no debe salir" }]);
    await m.conversar("humano");
    const enviados = m.canal.textos.length;
    await m.conversar("¿y cuánto cuesta la cama?");
    expect(m.canal.textos.length).toBe(enviados);
    expect(g.doGenerateCalls.length).toBe(0);
    expect(m.odoo.mensajes.filter((x) => x.autor === "cliente").map((x) => x.texto)).toContain("¿y cuánto cuesta la cama?");
  });

  it("funciona aunque la conversación esté en descanso por spam", async () => {
    const m = crearMundo();
    m.guion([{ texto: "Hola." }]);
    for (let i = 0; i < 3; i++) await m.escribir("compra ya");
    expect((await m.escribir("compra ya")).accion).toBe("descanso");
    const r = await m.escribir("persona");
    expect(r.accion).toBe("persona");
    await m.pasar(3_000);
    expect(m.odoo.de("pasar_a_vendedora")).toHaveLength(1);
  });

  it("funciona aunque el tope diario de turnos ya se haya cruzado", async () => {
    const m = crearMundo({ topeDiario: 2 });
    m.guion([{ texto: "Hola." }]);
    await m.escribir("uno");
    await m.escribir("dos");
    expect((await m.escribir("tres")).accion).toBe("tope_diario");
    await m.escribir("persona");
    await m.pasar(3_000);
    expect(m.odoo.de("pasar_a_vendedora")).toHaveLength(1);
  });

  it("si Odoo no contesta, el aviso queda en la cola, el cliente lo sabe y se entrega apenas Odoo vuelve", async () => {
    const m = crearMundo();
    m.guion([{ texto: "x" }]);
    await m.escribir("persona");
    m.odoo.caido = true;
    await m.pasar(3_000);
    expect(m.canal.textos.join("\n")).toMatch(/pasé tu consulta a una vendedora|dejé tu consulta/);
    expect(m.odoo.de("pasar_a_vendedora")).toHaveLength(0);
    m.odoo.caido = false;
    await m.pasar(10 * 60_000);
    expect(m.odoo.de("pasar_a_vendedora")).toHaveLength(1);
  });

  it("también cuando es el primer mensaje: la presentación como asistente automático va primero", async () => {
    const m = crearMundo();
    m.guion([{ texto: "x" }]);
    await m.conversar("persona");
    expect(m.canal.textos[0]).toMatch(/asistente autom[aá]tico/i);
    expect(m.canal.textos.join("\n")).toContain("ya avisé a una vendedora");
  });

  it("si el modelo tiene que decidir (frase ambigua), puede llamar a la herramienta y su texto sale", async () => {
    const m = crearMundo();
    m.guion([
      { llamadas: [{ nombre: "pasar_a_vendedora", args: { motivo: "El cliente quiere negociar el precio", urgencia: "normal" } }] },
      { texto: "Listo, ya avisé a una vendedora. Te escribe por aquí en unos minutos." },
    ]);
    await m.conversar("esto lo quiero ver con alguien de la tienda, ¿se puede?");
    expect(m.odoo.de("pasar_a_vendedora")).toHaveLength(1);
    expect(m.canal.textos.join("\n")).toContain("ya avisé a una vendedora");
  });
});

describe("se presenta como asistente automático", () => {
  it("lo dice en la primera burbuja, con el nombre público y la vía a una persona", async () => {
    const m = crearMundo();
    m.guion([{ texto: "Dime qué buscas." }]);
    await m.conversar("hola");
    const primera = m.canal.textos[0];
    expect(primera).toMatch(/asistente automático/);
    expect(primera).toContain("«el equipo de D'CASA»");
    expect(primera).toContain("escríbeme *persona* y te atiende una vendedora");
  });

  it("no firma como «Juan»", async () => {
    const m = crearMundo();
    m.guion([{ texto: "Dime qué buscas." }]);
    await m.conversar("hola");
    expect(m.canal.textos.join("\n")).not.toMatch(/\bJuan\b/);
  });
});
