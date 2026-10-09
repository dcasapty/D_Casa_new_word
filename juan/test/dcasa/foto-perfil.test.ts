/**
 * La foto de perfil de quien escribe se guarda en Odoo (para el avatar de la pantalla de las vendedoras): la pide el canal, a lo
 * más una vez por semana por conversación, solo si está encendido en Ajustes de Juan, y NUNCA llega a la IA. Si algo falla, la
 * conversación sigue igual.
 */
import { describe, expect, it, vi } from "vitest";
import { crearMundo } from "../helpers/mundo";

const FOTO = { bytes: new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 1, 2, 3, 4]), mime: "image/jpeg" };
const BASE64_FOTO = btoa(String.fromCharCode(...FOTO.bytes));
const SEMANA = 7 * 24 * 3600_000;
const HORA = 3600_000;

function mundoConFoto(op: Parameters<typeof crearMundo>[0] = {}) {
  const m = crearMundo(op);
  m.canal.foto = FOTO;
  return m;
}

describe("foto de perfil", () => {
  it("con el primer mensaje se pide al canal y se le manda a Odoo (base64, con el canal y la llave del cliente)", async () => {
    const m = mundoConFoto();
    m.guion([{ texto: "Hola Karen, ¿en qué te ayudo?" }]);
    await m.conversar("Hola");
    expect(m.canal.fotosPedidas).toBe(1);
    expect(m.odoo.fotosPerfil).toEqual([{ canal: "whatsapp_qr", id_externo: "50760261919", mime: "image/jpeg", base64: BASE64_FOTO }]);
  });

  it("no llega nunca al modelo: ni los bytes ni su base64 aparecen en lo que ve la IA", async () => {
    const m = mundoConFoto();
    const g = m.guion([{ texto: "Hola" }]);
    await m.conversar("Hola");
    const visto = JSON.stringify(g.doGenerateCalls.map((c) => c.prompt));
    expect(visto).not.toContain(BASE64_FOTO);
    expect(visto).not.toMatch(/foto de perfil|255,216/i);
  });

  it("en la misma semana no se vuelve a pedir; pasada la semana, sí (la gente cambia su foto)", async () => {
    const m = mundoConFoto();
    m.guion([{ texto: "Claro." }]);
    await m.conversar("Hola");
    await m.conversar("¿Y la cama gris?");
    expect(m.canal.fotosPedidas).toBe(1);
    await m.pasar(SEMANA - 60_000);
    await m.conversar("Otra pregunta");
    expect(m.canal.fotosPedidas).toBe(1);
    await m.pasar(2 * 60_000);
    await m.conversar("Una más");
    expect(m.canal.fotosPedidas).toBe(2);
  });

  it("apagado en Ajustes de Juan: no se pide nada al canal", async () => {
    const m = mundoConFoto({ config: { guardar_foto_perfil: false } });
    m.guion([{ texto: "Hola" }]);
    await m.conversar("Hola");
    expect(m.canal.fotosPedidas).toBe(0);
    expect(m.odoo.fotosPerfil).toEqual([]);
  });

  it("si la persona no tiene foto (o no la deja ver) no se manda nada a Odoo y se vuelve a intentar en una semana", async () => {
    const m = crearMundo();
    m.guion([{ texto: "Hola" }]);
    await m.conversar("Hola");
    expect(m.canal.fotosPedidas).toBe(1);
    expect(m.odoo.fotosPerfil).toEqual([]);
    await m.pasar(HORA * 2);
    await m.conversar("Otra vez");
    expect(m.canal.fotosPedidas).toBe(1);
    await m.pasar(SEMANA);
    await m.conversar("Pasó una semana");
    expect(m.canal.fotosPedidas).toBe(2);
  });

  it("si el canal falla, la respuesta sale igual y se reintenta a la hora (no antes)", async () => {
    const m = crearMundo();
    m.canal.foto = new Error("el puente no contestó");
    m.guion([{ texto: "Claro que sí." }]);
    await m.conversar("Hola");
    expect(m.canal.textos.join(" ")).toContain("Claro que sí.");
    expect(m.canal.fotosPedidas).toBe(1);
    await m.pasar(HORA - 120_000);
    await m.conversar("Sigo aquí");
    expect(m.canal.fotosPedidas).toBe(1);
    m.canal.foto = FOTO;
    await m.pasar(180_000);
    await m.conversar("¿Hay novedades?");
    expect(m.canal.fotosPedidas).toBe(2);
    expect(m.odoo.fotosPerfil).toHaveLength(1);
  });

  it("si Odoo rechaza o no recibe la foto, la respuesta sale igual", async () => {
    const m = mundoConFoto();
    m.odoo.falloFotoPerfil = new Error("Odoo dijo que no");
    m.guion([{ texto: "Hola, ¿qué buscas?" }]);
    await m.conversar("Hola");
    expect(m.canal.textos.join(" ")).toContain("¿qué buscas?");
  });

  it("un canal lentísimo no frena la respuesta más de 8 segundos", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    try {
      const m = crearMundo();
      m.canal.fotoDePerfil = () => new Promise(() => {});
      m.guion([{ texto: "Aquí estoy." }]);
      const en = m.conversar("Hola");
      await vi.advanceTimersByTimeAsync(9000);
      await en;
      expect(m.canal.textos.join(" ")).toContain("Aquí estoy.");
    } finally {
      vi.useRealTimers();
    }
  });

  it("un canal que no tiene foto de perfil (WhatsApp Cloud) o un Odoo viejo sin la ruta: no pasa nada", async () => {
    const sinCanal = mundoConFoto();
    sinCanal.canal.sinFotoDePerfil();
    sinCanal.guion([{ texto: "Hola" }]);
    await sinCanal.conversar("Hola");
    expect(sinCanal.odoo.fotosPerfil).toEqual([]);
    const sinOdoo = mundoConFoto();
    (sinOdoo.odoo as { fotoPerfil?: unknown }).fotoPerfil = undefined;
    sinOdoo.guion([{ texto: "Hola" }]);
    await sinOdoo.conversar("Hola");
    expect(sinOdoo.canal.fotosPedidas).toBe(0);
  });

  it("con Odoo caído no se guarda nada y la conversación no se rompe", async () => {
    const m = mundoConFoto();
    m.odoo.caido = true;
    m.guion([{ texto: "Hola" }]);
    await m.conversar("Hola");
    expect(m.odoo.fotosPerfil).toEqual([]);
    expect(m.canal.textos.length).toBeGreaterThan(0);
  });
});
