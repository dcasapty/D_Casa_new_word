/**
 * Regla 10 del contrato: seguimiento (decisión de la dueña). Máximo 2 mensajes a quien preguntó y no volvió:
 * el 1.º a las 5 h, solo en horario laboral; el 2.º a los 5 días; ninguno si ya compró o pidió que no lo contacten.
 *
 * ODOO decide a quién y cuándo (`POST /odoo/seguimiento`). El Worker redacta (corto, sin presión, voz de marca) y envía,
 * y confirma con `seguimiento/hecho`. Reescritura de test/followup/run.test.ts del CRM de Baby Caleb (que decidía todo ahí).
 */
import { describe, expect, it } from "vitest";
import { crearMundo, type Mundo } from "../helpers/mundo";

const SEGUIMIENTO_1 = "Hola Karen, ¿pudiste ver la cama queen? Si quieres, te ayudo con medidas o fotos. Y si prefieres, escríbeme *persona*.";

async function conversacionInteresada(m: Mundo) {
  m.guion([{ texto: "Tenemos camas queen. ¿Te cuento de las medidas?" }]);
  await m.conversar("hola, quiero una cama queen");
  return m.ahora();
}

const pedir = (m: Mundo, ultimo: number, numero: 1 | 2 = 1, interes = "cama queen") =>
  m.motor.seguimiento({ conversacion_id: 12, numero, contexto: { interes, ultimo_mensaje_ts: new Date(ultimo).toISOString() } });

describe("el seguimiento se redacta con el motor y se envía", () => {
  it("corto, por el mismo canal, registrado en Odoo y confirmado con seguimiento/hecho", async () => {
    const m = crearMundo();
    const ultimo = await conversacionInteresada(m);
    await m.pasar(5 * 3600_000);
    const g = m.guion([{ texto: SEGUIMIENTO_1 }]);
    const r = await pedir(m, ultimo);
    expect(r).toEqual({ ok: true, resultado: "enviado" });
    expect(m.canal.textos.at(-1)).toBe(SEGUIMIENTO_1);
    expect(m.odoo.mensajes.at(-1)).toMatchObject({ autor: "bot", direccion: "saliente" });
    await m.pasar(1_000);
    expect(m.odoo.mensajes.at(-1)!.texto).toContain("¿pudiste ver la cama queen?");
    expect(m.odoo.hechos).toEqual([{ conversacion_id: 12, numero: 1, resultado: "enviado" }]);
    expect(g.doGenerateCalls.length).toBe(1);
  });

  it("se redacta SIN herramientas (no puede traer precios ni existencias) y con el modelo barato", async () => {
    const m = crearMundo();
    const ultimo = await conversacionInteresada(m);
    await m.pasar(5 * 3600_000);
    const g = m.guion([{ texto: SEGUIMIENTO_1 }]);
    m.idsDeModelo.length = 0;
    await pedir(m, ultimo);
    expect(g.doGenerateCalls[0].tools ?? []).toHaveLength(0);
    expect(m.idsDeModelo).toEqual(["claude-haiku-4-5"]);
  });

  it("el modelo recibe el interés como dato, la regla de no presionar y el tuteo", async () => {
    const m = crearMundo();
    const ultimo = await conversacionInteresada(m);
    await m.pasar(5 * 3600_000);
    const g = m.guion([{ texto: SEGUIMIENTO_1 }]);
    await pedir(m, ultimo, 1, "cama queen CAMA-Q-001");
    const visto = g.prompts()[0];
    expect(visto).toContain("cama queen CAMA-Q-001");
    expect(visto).toMatch(/Sin presión/);
    expect(visto).toMatch(/Tuteo/);
    expect(visto).toMatch(/NO menciones precios/);
  });

  it("el segundo es el último y lo dice", async () => {
    const m = crearMundo();
    const ultimo = await conversacionInteresada(m);
    await m.pasar(5 * 24 * 3600_000);
    const g = m.guion([{ texto: "Hola Karen, no te escribo más por este tema. Si te sirve, aquí estoy." }]);
    const r = await pedir(m, ultimo, 2);
    expect(r.ok && r.resultado).toBe("enviado");
    expect(g.prompts()[0]).toMatch(/ÚLTIMO mensaje/);
    expect(m.odoo.hechos[0].numero).toBe(2);
  });

  it("un seguimiento con un precio, un descuento o presión NO sale", async () => {
    const m = crearMundo();
    const ultimo = await conversacionInteresada(m);
    await m.pasar(5 * 3600_000);
    m.guion([{ texto: "¡Última oportunidad! La queen está en $499 con 20% de descuento." }]);
    const r = await pedir(m, ultimo);
    expect(r.ok).toBe(false);
    expect(m.canal.textos.join("\n")).not.toMatch(/499|descuento|oportunidad/);
    expect(m.odoo.hechos).toHaveLength(0);
  });

  it("si el borrador mezcla algo bueno y algo malo, sale solo lo bueno", async () => {
    const m = crearMundo();
    const ultimo = await conversacionInteresada(m);
    await m.pasar(5 * 3600_000);
    m.guion([{ texto: "Hola Karen, ¿pudiste ver la cama? Hoy tiene 15% de descuento. Escríbeme *persona* si prefieres." }]);
    const r = await pedir(m, ultimo);
    expect(r).toEqual({ ok: true, resultado: "enviado" });
    expect(m.canal.textos.at(-1)).not.toMatch(/descuento/);
    expect(m.canal.textos.at(-1)).toContain("¿pudiste ver la cama?");
  });

  it("sin emojis ni signos dobles", async () => {
    const m = crearMundo();
    const ultimo = await conversacionInteresada(m);
    await m.pasar(5 * 3600_000);
    m.guion([{ texto: "¡¡Hola Karen!! 😊 ¿Sigues buscando tu cama?" }]);
    await pedir(m, ultimo);
    expect(m.canal.textos.at(-1)).toBe("¡Hola Karen! ¿Sigues buscando tu cama?");
  });
});

describe("cuándo NO se envía (y qué se le dice a Odoo)", () => {
  it("el cliente ya volvió a escribir → descartado", async () => {
    const m = crearMundo();
    const ultimo = await conversacionInteresada(m);
    await m.pasar(2 * 3600_000);
    m.guion([{ texto: "Claro." }]);
    await m.conversar("una pregunta más");
    await m.pasar(4 * 3600_000);
    const r = await pedir(m, ultimo);
    expect(r).toMatchObject({ ok: true, resultado: "descartado", motivo: expect.stringMatching(/volvió a escribir/) });
    expect(m.odoo.hechos).toEqual([expect.objectContaining({ numero: 1, resultado: "descartado" })]);
  });

  it("pidió que no lo contacten → descartado, aunque Odoo no lo sepa", async () => {
    const m = crearMundo();
    m.guion([{ texto: "Entendido, no te escribimos más." }]);
    const ultimo = await (async () => {
      await m.conversar("no me escriban más, gracias");
      return m.ahora();
    })();
    await m.pasar(5 * 3600_000);
    const r = await pedir(m, ultimo);
    expect(r).toMatchObject({ ok: true, resultado: "descartado", motivo: expect.stringMatching(/no lo contacten/) });
    expect(m.odoo.de("anotar_conversacion").some((l) => String(l.args.nota).includes("No enviar seguimientos"))).toBe(true);
  });

  it("una vendedora tiene la conversación → descartado", async () => {
    const m = crearMundo();
    const ultimo = await conversacionInteresada(m);
    await m.motor.fijarEstado({ estado: "humano", pausada_hasta: new Date(m.ahora() + 10 * 3600_000).toISOString() });
    await m.pasar(5 * 3600_000);
    const r = await pedir(m, ultimo);
    expect(r).toMatchObject({ ok: true, resultado: "descartado", motivo: expect.stringMatching(/vendedora/) });
  });

  it("Odoo dice que la conversación es de una persona → descartado", async () => {
    const m = crearMundo();
    const ultimo = await conversacionInteresada(m);
    await m.pasar(5 * 3600_000);
    m.odoo.estadoActual = { ...m.odoo.estadoActual, estado: "humano", bot_activo: false };
    const r = await pedir(m, ultimo);
    expect(r).toMatchObject({ resultado: "descartado" });
  });

  it("fuera del horario laboral → se pospone SIN dar por hecho (Odoo vuelve a pedirlo)", async () => {
    const m = crearMundo();
    const ultimo = await conversacionInteresada(m);
    await m.pasar(5 * 3600_000);
    m.odoo.estadoActual = { ...m.odoo.estadoActual, dentro_de_horario: false };
    const g = m.guion([{ texto: SEGUIMIENTO_1 }]);
    const r = await pedir(m, ultimo);
    expect(r).toMatchObject({ ok: true, resultado: "pospuesto", motivo: expect.stringMatching(/horario/) });
    expect(g.doGenerateCalls.length).toBe(0);
    expect(m.odoo.hechos).toHaveLength(0);
  });

  it("si la configuración dice que el seguimiento no es solo en horario laboral, sale igual", async () => {
    const m = crearMundo({ config: { seguimiento: { solo_horario_laboral: false } } });
    const ultimo = await conversacionInteresada(m);
    await m.pasar(5 * 3600_000);
    m.odoo.estadoActual = { ...m.odoo.estadoActual, dentro_de_horario: false };
    m.guion([{ texto: SEGUIMIENTO_1 }]);
    expect((await pedir(m, ultimo)).ok && true).toBe(true);
    expect(m.odoo.hechos.at(-1)?.resultado).toBe("enviado");
  });

  it("el bot apagado en Odoo → se pospone", async () => {
    const m = crearMundo();
    const ultimo = await conversacionInteresada(m);
    m.odoo.rawConfig = { bot_activo_global: false };
    await m.pasar(5 * 3600_000);
    expect(await pedir(m, ultimo)).toMatchObject({ resultado: "pospuesto" });
  });

  it("Odoo pide el mismo seguimiento dos veces → se envía una sola", async () => {
    const m = crearMundo();
    const ultimo = await conversacionInteresada(m);
    await m.pasar(5 * 3600_000);
    m.guion([{ texto: SEGUIMIENTO_1 }]);
    await pedir(m, ultimo);
    const segunda = await pedir(m, ultimo);
    expect(segunda).toMatchObject({ resultado: "descartado", motivo: expect.stringMatching(/ya se envió/) });
    expect(m.canal.textos.filter((t) => t === SEGUIMIENTO_1)).toHaveLength(1);
  });

  it("número inválido → error claro", async () => {
    const m = crearMundo();
    await conversacionInteresada(m);
    expect(await m.motor.seguimiento({ conversacion_id: 12, numero: 3 })).toEqual({ ok: false, error: "numero debe ser 1 o 2" });
  });

  it("si el canal falla al enviar, Odoo recibe un error (y vuelve a pedirlo) y NADA se da por hecho", async () => {
    const m = crearMundo();
    const ultimo = await conversacionInteresada(m);
    await m.pasar(5 * 3600_000);
    m.guion([{ texto: SEGUIMIENTO_1 }]);
    m.canal.fallar = 5;
    const r = await pedir(m, ultimo);
    expect(r.ok).toBe(false);
    expect(m.odoo.hechos).toHaveLength(0);
    m.canal.fallar = 0;
    expect(await pedir(m, ultimo)).toEqual({ ok: true, resultado: "enviado" });
  });

  it("si la IA falla al redactar, error (no se inventa un texto)", async () => {
    const m = crearMundo();
    const ultimo = await conversacionInteresada(m);
    await m.pasar(5 * 3600_000);
    m.guion([{ error: new Error("caído") }]);
    expect((await pedir(m, ultimo)).ok).toBe(false);
    expect(m.canal.textos.filter((t) => /Hola Karen/.test(t))).toHaveLength(0);
  });
});

describe("la ventana de 24 h de Messenger, Instagram y WhatsApp Cloud", () => {
  it("fuera de la ventana el texto libre no se puede enviar → descartado con el motivo", async () => {
    const m = crearMundo({ canal: "messenger", idExterno: "psid-1", config: { canales_activos: { messenger: true } } });
    m.canal.cap = { ...m.canal.cap, ventana24h: true };
    m.guion([{ texto: "Tenemos camas queen." }]);
    await m.conversar("quiero una cama");
    const ultimo = m.ahora();
    await m.pasar(5 * 24 * 3600_000);
    const r = await pedir(m, ultimo, 2);
    expect(r).toMatchObject({ resultado: "descartado", motivo: expect.stringMatching(/24 h/) });
    expect(m.odoo.hechos.at(-1)).toMatchObject({ numero: 2, resultado: "descartado" });
  });

  it("dentro de la ventana sí sale", async () => {
    const m = crearMundo({ canal: "messenger", idExterno: "psid-1", config: { canales_activos: { messenger: true } } });
    m.canal.cap = { ...m.canal.cap, ventana24h: true };
    m.guion([{ texto: "Tenemos camas queen." }]);
    await m.conversar("quiero una cama");
    const ultimo = m.ahora();
    await m.pasar(5 * 3600_000);
    m.guion([{ texto: SEGUIMIENTO_1 }]);
    expect((await pedir(m, ultimo)).ok).toBe(true);
    expect(m.canal.textos.at(-1)).toBe(SEGUIMIENTO_1);
  });

  it("WhatsApp por QR y Telegram no tienen ventana: el de los 5 días sale", async () => {
    const m = crearMundo();
    const ultimo = await conversacionInteresada(m);
    await m.pasar(5 * 24 * 3600_000);
    m.guion([{ texto: "Hola Karen, ¿sigues interesada? Aquí estoy." }]);
    expect(await pedir(m, ultimo, 2)).toEqual({ ok: true, resultado: "enviado" });
  });
});
