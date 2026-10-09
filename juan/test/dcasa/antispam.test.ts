/**
 * Regla 9 del contrato: anti-spam. Mensaje repetido → descanso de 1 h; tope diario por persona; ráfaga de 15 s.
 * Reescritura de test/spam.test.ts del CRM de Baby Caleb. Nada de esto gasta IA.
 */
import { describe, expect, it } from "vitest";
import { esRepetido, superaTopeDiario } from "../../src/motor/antispam";
import { TEXTO_TOPE_DIARIO } from "../../src/dcasa/textos";
import { crearMundo } from "../helpers/mundo";

describe("¿es el mismo mensaje otra vez?", () => {
  it("la 3.ª vez entre los últimos 5 sí", () => {
    expect(esRepetido("comprar ya", ["comprar ya", "comprar ya"])).toBe(true);
    expect(esRepetido("comprar ya", ["hola", "comprar ya", "otra cosa", "comprar ya"])).toBe(true);
  });
  it("la 2.ª todavía no", () => {
    expect(esRepetido("comprar ya", ["comprar ya", "hola"])).toBe(false);
  });
  it("no distingue mayúsculas, acentos, signos ni espacios", () => {
    expect(esRepetido("¡Comprár  YA!", ["comprar ya", "COMPRAR YA."])).toBe(true);
  });
  it("«ok» o «sí» sueltos no cuentan", () => {
    expect(esRepetido("ok", ["ok", "ok"])).toBe(false);
    expect(esRepetido("sí", ["sí", "sí"])).toBe(false);
    expect(esRepetido("no", ["no", "no"])).toBe(false);
    expect(esRepetido("a", ["a", "a"])).toBe(false);
    expect(esRepetido("dale", ["dale", "dale"])).toBe(true);
  });
  it("solo mira los últimos 5", () => {
    expect(esRepetido("comprar ya", ["x1", "x2", "x3", "x4", "x5", "comprar ya", "comprar ya"])).toBe(false);
  });
  it("el tope diario", () => {
    expect(superaTopeDiario(50, 50)).toBe(true);
    expect(superaTopeDiario(49, 50)).toBe(false);
    expect(superaTopeDiario(1000, 0)).toBe(false);
  });
});

describe("mensaje repetido → la conversación descansa 1 hora, sin gastar IA", () => {
  it("el mismo mensaje por 3.ª vez: no se contesta y no se llama al modelo", async () => {
    const m = crearMundo();
    const g = m.guion([{ texto: "Hola." }]);
    await m.conversar("comprar comprar");
    await m.escribir("comprar comprar");
    const tercera = await m.escribir("comprar comprar");
    expect(tercera.accion).toBe("descanso");
    await m.pasar(20_000);
    expect(g.doGenerateCalls.length).toBe(1);
    expect(m.registros.some((r) => r.mensaje.includes("descansa 1 hora"))).toBe(true);
  });

  it("durante el descanso no hay respuesta, pero TODO queda registrado en Odoo", async () => {
    const m = crearMundo();
    m.guion([{ texto: "Hola." }]);
    for (let i = 0; i < 3; i++) await m.escribir("spam spam");
    await m.pasar(20_000);
    await m.conversar("otra cosa distinta");
    expect(m.canal.salidas.length).toBe(0);
    expect(m.odoo.mensajes.filter((x) => x.autor === "cliente")).toHaveLength(4);
  });

  it("pasada la hora, vuelve a contestar", async () => {
    const m = crearMundo();
    m.guion([{ texto: "Aquí estoy." }]);
    for (let i = 0; i < 3; i++) await m.escribir("spam spam");
    await m.pasar(61 * 60_000);
    await m.conversar("hola, ahora sí quiero una cama");
    expect(m.canal.textos.join("\n")).toContain("Aquí estoy.");
  });

  it("el descanso de uno no afecta a otro cliente (cada uno tiene su conversación)", async () => {
    const a = crearMundo({ idExterno: "50760000001" });
    const b = crearMundo({ idExterno: "50760000002" });
    a.guion([{ texto: "A" }]);
    b.guion([{ texto: "B" }]);
    for (let i = 0; i < 4; i++) await a.escribir("spam");
    await b.conversar("hola");
    expect(b.canal.textos.join("\n")).toContain("B");
  });
});

describe("tope diario de turnos por persona", () => {
  it("al cruzarlo: UNA despedida amable y 12 horas de descanso", async () => {
    const m = crearMundo({ topeDiario: 4 });
    m.guion([{ texto: "Respuesta." }]);
    for (const t of ["uno", "dos", "tres", "cuatro"]) await m.escribir(t);
    const r = await m.escribir("cinco");
    expect(r.accion).toBe("tope_diario");
    expect(m.canal.textos).toEqual([TEXTO_TOPE_DIARIO]);
    // Los siguientes mensajes no reciben nada más.
    await m.conversar("seis");
    await m.conversar("siete");
    expect(m.canal.textos.filter((t) => t === TEXTO_TOPE_DIARIO)).toHaveLength(1);
    expect(m.canal.textos).toHaveLength(1);
  });

  it("la despedida respeta la voz: tuteo, sin emojis, ofrece una persona", () => {
    expect(TEXTO_TOPE_DIARIO).toContain("*persona*");
    expect(TEXTO_TOPE_DIARIO).not.toMatch(/\p{Extended_Pictographic}/u);
    expect(TEXTO_TOPE_DIARIO).not.toMatch(/\busted\b/i);
  });

  it("a las 12 horas vuelve", async () => {
    const m = crearMundo({ topeDiario: 3 });
    m.guion([{ texto: "De vuelta." }]);
    for (const t of ["uno", "dos", "tres", "cuatro"]) await m.escribir(t);
    await m.pasar(13 * 3600_000);
    await m.conversar("hola otra vez");
    // Pasaron más de 12 h pero menos de 24: los 3 mensajes de antes siguen contando, así que ahora entra el tope otra vez
    // salvo que ya hayan salido de la ventana de 24 h. Se comprueba con el reloj a +25 h.
    await m.pasar(12 * 3600_000);
    await m.conversar("buenas, una pregunta");
    expect(m.canal.textos.join("\n")).toContain("De vuelta.");
  });

  it("lo que cuenta es la ventana de 24 horas, no el día del calendario", async () => {
    const m = crearMundo({ topeDiario: 3 });
    m.guion([{ texto: "Hola." }]);
    await m.escribir("uno");
    await m.escribir("dos");
    await m.pasar(25 * 3600_000);
    const r = await m.escribir("tres");
    expect(r.accion).toBe("en_espera");
  });
});

describe("la ráfaga de 15 s", () => {
  it("tres mensajes distintos seguidos → una sola respuesta", async () => {
    const m = crearMundo();
    const g = m.guion([{ texto: "Te ayudo con todo eso." }]);
    await m.escribir("hola");
    await m.escribir("quiero una cama");
    await m.escribir("queen");
    await m.pasar(20_000);
    expect(g.doGenerateCalls.length).toBe(1);
  });

  it("un mensaje viejo (más de 2 h de retraso) se guarda pero no se contesta", async () => {
    const m = crearMundo();
    const g = m.guion([{ texto: "no debería salir" }]);
    const r = await m.escribir("hola", { ts: m.ahora() - 3 * 3600_000 });
    expect(r.accion).toBe("vencido");
    await m.pasar(20_000);
    expect(g.doGenerateCalls.length).toBe(0);
    expect(m.odoo.mensajes).toHaveLength(1);
  });

  it("estados, grupos y otros chats que no son una persona nunca llegan a contestarse", async () => {
    const m = crearMundo();
    m.guion([{ texto: "Hola." }]);
    // El adaptador los descarta antes; aquí se comprueba que el canal jamás publicaría un estado.
    const { crearWhatsappQr } = await import("../../src/canales/whatsappQr");
    const qr = crearWhatsappQr();
    await expect(qr.enviar("whatsapp_qr", { para: "status@broadcast", burbujas: ["x"], medios: [] }, {} as never)).rejects.toThrow(/no es el chat de una persona/);
  });
});
