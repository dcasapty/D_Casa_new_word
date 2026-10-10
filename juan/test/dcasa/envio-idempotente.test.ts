/**
 * Ola 1 · «que no duplique». Odoo reintenta un envío cuando no oyó la respuesta (se cayó la red, el Worker tardó más de 25 s).
 * Ese reintento NO puede volver a mandarle al cliente lo que ya salió: la llave es `id_envio` (el `id_mensaje` del mensaje en Odoo).
 */
import { describe, expect, it } from "vitest";
import { crearMundo } from "../helpers/mundo";

describe("POST /odoo/enviar con id_envio", () => {
  it("el mismo envío dos veces sale UNA sola vez, y Odoo recibe el mismo id", async () => {
    const m = crearMundo();
    const a = await m.motor.enviarVendedora({ id_envio: "odoo-abc", texto: "Hola Karen, soy Marisol." });
    const b = await m.motor.enviarVendedora({ id_envio: "odoo-abc", texto: "Hola Karen, soy Marisol." });
    expect(m.canal.textos).toEqual(["Hola Karen, soy Marisol."]);
    expect(b).toEqual({ ok: true, id_mensaje: a.id_mensaje, repetido: true });
  });

  it("dos envíos distintos (otro id_envio) salen los dos", async () => {
    const m = crearMundo();
    await m.motor.enviarVendedora({ id_envio: "odoo-1", texto: "Uno" });
    await m.motor.enviarVendedora({ id_envio: "odoo-2", texto: "Uno" });
    expect(m.canal.textos).toEqual(["Uno", "Uno"]);
  });

  it("sin id_envio (un Odoo viejo) funciona como siempre", async () => {
    const m = crearMundo();
    await m.motor.enviarVendedora({ texto: "Hola" });
    await m.motor.enviarVendedora({ texto: "Hola" });
    expect(m.canal.textos).toEqual(["Hola", "Hola"]);
  });

  it("si el mismo envío todavía está saliendo, el reintento espera (no sale por segunda vez)", async () => {
    const m = crearMundo();
    let abrir!: () => void;
    m.canal.puerta = new Promise<void>((r) => (abrir = r));
    const primero = m.motor.enviarVendedora({ id_envio: "odoo-lento", texto: "Te paso el precio" });
    await Promise.resolve();
    await expect(m.motor.enviarVendedora({ id_envio: "odoo-lento", texto: "Te paso el precio" })).rejects.toThrow(/ya se está enviando/);
    abrir();
    const r = await primero;
    expect(m.canal.textos).toEqual(["Te paso el precio"]);
    // Y cuando Odoo vuelve a preguntar, ya está hecho.
    expect(await m.motor.enviarVendedora({ id_envio: "odoo-lento", texto: "Te paso el precio" })).toEqual({ ok: true, id_mensaje: r.id_mensaje, repetido: true });
  });

  it("si el Worker se reinició a mitad de un envío (quedó «saliendo» hace minutos), el reintento sí lo manda", async () => {
    const m = crearMundo();
    // Lo que queda en la memoria del Durable Object si se cae a mitad de un envío: «saliendo», sin terminar, de hace 4 minutos.
    m.motor.kv.poner("ide:odoo-colgado", JSON.stringify({ e: "curso", ts: m.ahora() - 4 * 60_000, b: 0, m: 0, ids: [] }));
    await m.motor.enviarVendedora({ id_envio: "odoo-colgado", texto: "Hola" });
    expect(m.canal.textos).toEqual(["Hola"]);
  });

  it("las marcas de envíos viejos se limpian solas con la purga diaria", async () => {
    const m = crearMundo();
    await m.motor.enviarVendedora({ id_envio: "odoo-viejo", texto: "Hola" });
    expect(m.motor.kv.texto("ide:odoo-viejo")).not.toBeNull();
    await m.escribir("hola");
    await m.pasar(25 * 3600_000); // dispara la purga (t_purga a las 24 h)
    expect(m.motor.kv.texto("ide:odoo-viejo")).not.toBeNull(); // 3 días de memoria: Odoo puede seguir reintentando
    await m.pasar(4 * 24 * 3600_000);
    await m.pasar(25 * 3600_000);
    expect(m.motor.kv.texto("ide:odoo-viejo")).toBeNull();
  });

  it("un envío que falló del todo no deja rastro: el reintento de Odoo lo manda completo", async () => {
    const m = crearMundo();
    m.canal.fallar = 2; // el intento y su reintento interno
    await expect(m.motor.enviarVendedora({ id_envio: "odoo-fallo", texto: "Hola" })).rejects.toThrow(/el canal falló/);
    expect(m.canal.textos).toEqual([]);
    await m.motor.enviarVendedora({ id_envio: "odoo-fallo", texto: "Hola" });
    expect(m.canal.textos).toEqual(["Hola"]);
  });
});

describe("un envío que se corta a la mitad", () => {
  const TEXTO_LARGO = ["Primera idea.", "Segunda idea."];

  it("el reintento interno manda SOLO lo que faltaba (el cliente no recibe lo mismo dos veces)", async () => {
    const m = crearMundo();
    m.canal.cap = { ...m.canal.cap, maxTexto: 20 };
    m.canal.cortarEn = { burbujas: 1 };
    await m.motor.enviarVendedora({ id_envio: "odoo-parcial", texto: TEXTO_LARGO.join(" ") });
    expect(m.canal.textos).toEqual(TEXTO_LARGO);
  });

  it("si el reintento interno también falla, lo que sí salió queda anotado y el reintento de Odoo sigue donde quedó", async () => {
    const m = crearMundo();
    m.canal.cap = { ...m.canal.cap, maxTexto: 20 };
    m.canal.cortarEn = { burbujas: 1 };
    m.canal.fallar = 1; // tras el corte, el reintento interno falla
    // el primer envío entrega la burbuja 1 y se corta; el reintento interno falla antes de enviar nada más
    // (cortarEn se gasta en el primer envío; `fallar` en el segundo)
    const falla = m.motor.enviarVendedora({ id_envio: "odoo-parcial-2", texto: TEXTO_LARGO.join(" ") });
    await expect(falla).rejects.toThrow(/el canal falló/);
    expect(m.canal.textos).toEqual(["Primera idea."]);
    // El historial local lo sabe: el asistente no contradice lo que ya se le dijo al cliente.
    expect(m.motor.mensajes.ultimos(5).map((f) => f.texto)).toEqual(["Primera idea."]);
    // Odoo reintenta con la misma llave: sale SOLO la segunda.
    await m.motor.enviarVendedora({ id_envio: "odoo-parcial-2", texto: TEXTO_LARGO.join(" ") });
    expect(m.canal.textos).toEqual(TEXTO_LARGO);
  });

  it("un archivo que ya salió no se manda otra vez cuando el texto es lo que falló", async () => {
    const m = crearMundo();
    m.canal.cortarEn = { burbujas: 1, medios: 0 };
    await m.motor.enviarVendedora({
      id_envio: "odoo-medio",
      texto: "Mira esto",
      adjuntos: [
        { tipo: "imagen", url: "https://odoo.example/a.jpg", nombre: "a.jpg" },
        { tipo: "imagen", url: "https://odoo.example/b.jpg", nombre: "b.jpg" },
      ],
    });
    expect(m.canal.textos).toEqual(["Mira esto"]);
    expect(m.canal.medios.map((x) => x.nombre)).toEqual(["a.jpg", "b.jpg"]);
  });

  it("también cuando responde el bot: lo que salió queda registrado en Odoo, y el resto se completa", async () => {
    const m = crearMundo();
    m.canal.cap = { ...m.canal.cap, maxTexto: 20 };
    m.canal.cortarEn = { burbujas: 1 };
    m.guion([{ texto: "Primera idea. Segunda idea." }]);
    await m.conversar("hola");
    const dicho = m.canal.textos.filter((t) => /idea/.test(t));
    expect(dicho).toEqual(["Primera idea.", "Segunda idea."]);
    const registrado = m.odoo.mensajes.filter((x) => x.autor === "bot").map((x) => x.texto).join("\n");
    expect(registrado).toContain("Primera idea.");
    expect(registrado).toContain("Segunda idea.");
  });
});
