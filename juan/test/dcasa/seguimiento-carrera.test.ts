/**
 * Issue #24 · Carreras del seguimiento:
 *   · «el cliente ya volvió a escribir» se miraba ANTES de redactar, no justo antes de enviar: si escribía mientras la IA redactaba, le
 *     llegaba igual el «¿sigues interesado?»;
 *   · `seguimientos.clave` se anotaba DESPUÉS de enviar: dos pedidos del mismo seguimiento a la vez (Odoo que reintenta tras su plazo
 *     de 25 s, el cron y un reintento a mano) mandaban dos. Ahora el seguimiento se reclama antes de redactar y se suelta si no sale.
 */
import { describe, expect, it } from "vitest";
import { crearMundo, type Mundo } from "../helpers/mundo";

const SEGUIMIENTO = "Hola Karen, ¿pudiste ver la cama queen? Si quieres, te ayudo con medidas o fotos.";

async function interesada(m: Mundo) {
  m.guion([{ texto: "Tenemos camas queen. ¿Te cuento de las medidas?" }]);
  await m.conversar("hola, quiero una cama queen");
  return m.ahora();
}

const pedir = (m: Mundo, ultimo: number) => m.motor.seguimiento({ conversacion_id: 12, numero: 1, contexto: { interes: "cama queen", ultimo_mensaje_ts: new Date(ultimo).toISOString() } });
const seguimientosEnviados = (m: Mundo) => m.canal.textos.filter((t) => t === SEGUIMIENTO).length;

describe("el seguimiento no le gana a la respuesta del cliente (issue #24)", () => {
  it("si el cliente escribe MIENTRAS se redacta el seguimiento, no sale", async () => {
    const m = crearMundo();
    const ultimo = await interesada(m);
    await m.pasar(5 * 3600_000);
    m.guion([
      {
        texto: SEGUIMIENTO,
        alGenerar: async () => {
          await m.motor.ingest(m.entrante("sí, todavía la quiero, ¿qué medidas tiene?"));
        },
      },
    ]);
    const r = await pedir(m, ultimo);
    expect(r).toMatchObject({ ok: true, resultado: "descartado", motivo: expect.stringMatching(/volvió a escribir/) });
    expect(seguimientosEnviados(m)).toBe(0);
    expect(m.odoo.hechos).toEqual([expect.objectContaining({ numero: 1, resultado: "descartado" })]);
  });

  it("si pide que no le escriban MIENTRAS se redacta, tampoco sale", async () => {
    const m = crearMundo();
    const ultimo = await interesada(m);
    await m.pasar(5 * 3600_000);
    m.guion([{ texto: SEGUIMIENTO, alGenerar: () => void m.motor.ingest(m.entrante("ya no me escriban, gracias")) }]);
    const r = await pedir(m, ultimo);
    expect(r).toMatchObject({ resultado: "descartado" });
    expect(seguimientosEnviados(m)).toBe(0);
  });
});

describe("dos pedidos del mismo seguimiento a la vez mandan uno solo (issue #24)", () => {
  it("el segundo pedido, mientras el primero redacta, se pospone sin redactar ni enviar", async () => {
    const m = crearMundo();
    const ultimo = await interesada(m);
    await m.pasar(5 * 3600_000);
    const g = m.guion([{ texto: SEGUIMIENTO }]);
    const [a, b] = await Promise.all([pedir(m, ultimo), pedir(m, ultimo)]);
    expect([a, b]).toContainEqual({ ok: true, resultado: "enviado" });
    expect([a, b]).toContainEqual({ ok: true, resultado: "pospuesto", motivo: expect.stringMatching(/ya se está enviando/) });
    expect(seguimientosEnviados(m)).toBe(1);
    expect(g.doGenerateCalls.length).toBe(1);
    expect(m.odoo.hechos.filter((h) => h.resultado === "enviado")).toHaveLength(1);
  });

  it("después de enviado, el mismo pedido otra vez se reconoce (como siempre)", async () => {
    const m = crearMundo();
    const ultimo = await interesada(m);
    await m.pasar(5 * 3600_000);
    m.guion([{ texto: SEGUIMIENTO }]);
    await pedir(m, ultimo);
    expect(await pedir(m, ultimo)).toMatchObject({ resultado: "descartado", motivo: expect.stringMatching(/ya se envió/) });
    expect(seguimientosEnviados(m)).toBe(1);
  });

  it("si la IA falla al redactar, el reclamo se suelta: el siguiente pedido sí lo envía", async () => {
    const m = crearMundo();
    const ultimo = await interesada(m);
    await m.pasar(5 * 3600_000);
    m.guion([{ error: new Error("caído") }]);
    expect((await pedir(m, ultimo)).ok).toBe(false);
    m.guion([{ texto: SEGUIMIENTO }]);
    expect(await pedir(m, ultimo)).toEqual({ ok: true, resultado: "enviado" });
  });

  it("un reclamo que quedó colgado (el objeto se reinició a mitad) vence solo a los pocos minutos", async () => {
    const m = crearMundo();
    const ultimo = await interesada(m);
    await m.pasar(5 * 3600_000);
    m.guion([{ texto: SEGUIMIENTO, alGenerar: () => new Promise<void>(() => {}) }]); // se queda redactando para siempre
    void pedir(m, ultimo);
    for (let i = 0; i < 20; i++) await new Promise((r) => setTimeout(r, 0));
    expect(await pedir(m, ultimo)).toMatchObject({ resultado: "pospuesto" });
    await m.pasar(5 * 60_000);
    m.guion([{ texto: SEGUIMIENTO }]);
    expect(await pedir(m, ultimo)).toEqual({ ok: true, resultado: "enviado" });
  });

  it("si la redacción tarda más que el reclamo y otro pedido ya lo envió, el primero que vuelve no envía otro", async () => {
    const m = crearMundo();
    const ultimo = await interesada(m);
    await m.pasar(5 * 3600_000);
    let abrirA!: () => void;
    const puertaA = new Promise<void>((r) => (abrirA = r));
    m.guion([{ texto: SEGUIMIENTO, alGenerar: () => puertaA }]);
    const a = pedir(m, ultimo); // se queda redactando más de 3 minutos
    for (let i = 0; i < 20; i++) await new Promise((r) => setTimeout(r, 0));
    await m.pasar(4 * 60_000);
    m.guion([{ texto: SEGUIMIENTO }]);
    expect(await pedir(m, ultimo)).toEqual({ ok: true, resultado: "enviado" });
    abrirA();
    expect(await a).toMatchObject({ ok: true, resultado: "descartado", motivo: expect.stringMatching(/ya se envió/) });
    expect(seguimientosEnviados(m)).toBe(1);
  });

  it("un pedido viejo que termina mal no suelta el reclamo del pedido que lo reemplazó", async () => {
    const m = crearMundo();
    const ultimo = await interesada(m);
    await m.pasar(5 * 3600_000);
    let fallarA!: () => void;
    const puertaA = new Promise<void>((_, rechazar) => (fallarA = () => rechazar(new Error("se cayó la IA"))));
    m.guion([{ texto: SEGUIMIENTO, alGenerar: () => puertaA }]);
    const a = pedir(m, ultimo);
    for (let i = 0; i < 20; i++) await new Promise((r) => setTimeout(r, 0));
    await m.pasar(4 * 60_000); // el reclamo de A venció
    let abrirB!: () => void;
    const puertaB = new Promise<void>((r) => (abrirB = r));
    m.guion([{ texto: SEGUIMIENTO, alGenerar: () => puertaB }, { error: new Error("caído") }]);
    const b = pedir(m, ultimo); // B reclama y se queda redactando
    for (let i = 0; i < 20; i++) await new Promise((r) => setTimeout(r, 0));
    fallarA();
    expect((await a).ok).toBe(false);
    // A terminó mal, pero el reclamo ya era de B: un tercer pedido se pospone (no redacta otro a la vez).
    expect(await pedir(m, ultimo)).toMatchObject({ ok: true, resultado: "pospuesto" });
    abrirB();
    expect(await b).toEqual({ ok: true, resultado: "enviado" });
    expect(seguimientosEnviados(m)).toBe(1);
  });
});
