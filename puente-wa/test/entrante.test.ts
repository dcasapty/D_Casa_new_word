import { describe, expect, it, vi } from "vitest";
import { armarEntrante, elegirDe } from "../contenedor/lib/entrante.mjs";
import { validarWebhook } from "../contenedor/lib/contrato.mjs";
import { LIMITE_ENTRANTE } from "../contenedor/lib/medios.mjs";
import {
  CLIENTE,
  msgAudio,
  msgDocumento,
  msgImagen,
  msgReaccion,
  msgSticker,
  msgTexto,
  msgUbicacion,
  msgVideo,
} from "./ayuda/baileys";

const AHORA = 1_800_000_000_000;
const descarga = (texto = "BYTES") => vi.fn(async () => Buffer.from(texto));
const armar = (msg: any, extra: Record<string, unknown> = {}) =>
  armarEntrante(msg, { propio: false, candidatos: [CLIENTE], descargarMedio: descarga(), ahora: AHORA, ...extra } as any);

describe("elegirDe (el número del cliente en la forma del contrato)", () => {
  it("E.164 sin «+»", () => {
    expect(elegirDe(["50760261919@s.whatsapp.net"])).toEqual({ de: "50760261919", jid: "50760261919@s.whatsapp.net" });
    expect(elegirDe(["50760261919:12@s.whatsapp.net"])).toEqual({ de: "50760261919", jid: "50760261919@s.whatsapp.net" });
  });

  it("si el chat es un LID pero se conoce su número, manda el número", () => {
    expect(elegirDe(["987654321098765@lid", "50760261919@s.whatsapp.net"])?.de).toBe("50760261919");
  });

  it("si solo hay LID, manda el jid completo: sigue siendo una llave estable y a ese chat se le puede contestar", () => {
    expect(elegirDe(["987654321098765@lid"])).toEqual({ de: "987654321098765@lid", jid: "987654321098765@lid" });
  });

  it("sin nada utilizable, null", () => {
    expect(elegirDe([])).toBe(null);
    expect(elegirDe(["", "status@broadcast"])).toBe(null);
  });
});

describe("armarEntrante: del mensaje de Baileys al JSON del contrato", () => {
  it("texto", async () => {
    const r = await armar(msgTexto("Hola, ¿tienen camas queen?", { id: "A1", ts: Math.floor(AHORA / 1000), pushName: "Karen" }));
    expect(r!.payload).toEqual({
      id_mensaje: "A1",
      de: "50760261919",
      nombre: "Karen",
      tipo: "texto",
      texto: "Hola, ¿tienen camas queen?",
      ts: new Date(Math.floor(AHORA / 1000) * 1000).toISOString(),
      propio: false,
      jid: CLIENTE,
    });
    expect(validarWebhook(r!.payload)).toEqual([]);
  });

  it("imagen con leyenda: se descarga y viaja en base64", async () => {
    const bajar = descarga("FOTO-DE-PRUEBA");
    const r = await armar(msgImagen({ caption: "este es mi comprobante" }), { descargarMedio: bajar });
    expect(bajar).toHaveBeenCalledOnce();
    expect(r!.payload).toMatchObject({
      tipo: "imagen",
      texto: "este es mi comprobante",
      medio: { base64: Buffer.from("FOTO-DE-PRUEBA").toString("base64"), mime: "image/jpeg", nombre: "imagen.jpg" },
    });
    expect(validarWebhook(r!.payload)).toEqual([]);
  });

  it("nota de voz: mime sin parámetros y sin texto", async () => {
    const r = await armar(msgAudio());
    expect(r!.payload).toMatchObject({ tipo: "audio", medio: { mime: "audio/ogg", nombre: "nota-de-voz.ogg" } });
    expect(r!.payload).not.toHaveProperty("texto");
  });

  it("documento: conserva su nombre (saneado) y su leyenda", async () => {
    const r = await armar(msgDocumento({ nombre: "../../Comprobante de pago.pdf", caption: "pagué hoy" }));
    expect(r!.payload).toMatchObject({ tipo: "documento", texto: "pagué hoy", medio: { mime: "application/pdf", nombre: "Comprobante de pago.pdf" } });
  });

  it("video", async () => {
    const r = await armar(msgVideo());
    expect(r!.payload).toMatchObject({ tipo: "video", medio: { mime: "video/mp4", nombre: "video.mp4" } });
  });

  it("la vendedora desde el teléfono: propio:true y sin el nombre de la dueña", async () => {
    const r = await armar(msgTexto("Buenas tardes, le atiende Marisol", { fromMe: true, pushName: "Marisol D'CASA" }), { propio: true });
    expect(r!.payload).toMatchObject({ propio: true, nombre: null, de: "50760261919", texto: "Buenas tardes, le atiende Marisol" });
    expect(validarWebhook(r!.payload)).toEqual([]);
  });

  it("un sticker de la vendedora avisa igual (tomó la conversación)", async () => {
    const r = await armar(msgSticker({ fromMe: true }), { propio: true });
    expect(r!.payload).toMatchObject({ tipo: "texto", propio: true, texto: "Sticker enviado desde el teléfono" });
    expect(validarWebhook(r!.payload)).toEqual([]);
  });

  it("ubicación de un cliente: texto con las coordenadas", async () => {
    const r = await armar(msgUbicacion());
    expect(r!.payload).toMatchObject({ tipo: "texto", texto: "Ubicación compartida: 8.8801, -79.7834 (Casa, La Chorrera)" });
  });

  it("un archivo que pasa del tope NO se descarga y se dice por qué", async () => {
    const bajar = descarga();
    const r = await armar(msgVideo({ tam: LIMITE_ENTRANTE.video + 1 }), { descargarMedio: bajar });
    expect(bajar).not.toHaveBeenCalled();
    expect(r!.payload).toMatchObject({ tipo: "video", medio_omitido: { motivo: "tamano", mime: "video/mp4", bytes: LIMITE_ENTRANTE.video + 1 } });
    expect(r!.payload).not.toHaveProperty("medio");
    expect(r!.sinMedio).toBe(true);
    expect(validarWebhook(r!.payload)).toEqual([]);
  });

  it("si la descarga falla, el mensaje igual sale (mejor eso que perderlo) y dice qué pasó", async () => {
    const r = await armar(msgImagen({ caption: "mira" }), {
      descargarMedio: vi.fn(async () => {
        throw new Error("media key vencida");
      }),
    });
    expect(r!.payload).toMatchObject({ tipo: "imagen", texto: "mira", medio_omitido: { motivo: "descarga_fallida", mime: "image/jpeg" } });
    expect(JSON.stringify(r!.payload)).not.toContain("media key");
    expect(validarWebhook(r!.payload)).toEqual([]);
  });

  it("una descarga más grande de lo que decía el mensaje también se omite", async () => {
    const grande = Buffer.alloc(LIMITE_ENTRANTE.imagen + 10);
    const r = await armar(msgImagen({ tam: 1000 }), { descargarMedio: vi.fn(async () => grande) });
    expect(r!.payload).toMatchObject({ medio_omitido: { motivo: "tamano" } });
  });

  it("lo que no es un mensaje (reacción) y lo que no se puede ubicar, no se entrega", async () => {
    expect(await armar(msgReaccion())).toBe(null);
    expect(await armar(msgTexto("hola"), { candidatos: ["status@broadcast"] })).toBe(null);
    expect(await armar(msgTexto("   "))).toBe(null);
    const sinId: any = msgTexto("x");
    delete sinId.key.id;
    expect(await armar(sinId)).toBe(null);
  });

  it("el JSON jamás lleva el mensaje crudo de Baileys (claves de medios, etc.)", async () => {
    const m: any = msgImagen();
    m.message.imageMessage.mediaKey = "MEDIA-KEY-SECRETA";
    m.message.imageMessage.url = "https://mmg.whatsapp.net/secreto";
    const r = await armar(m);
    const texto = JSON.stringify(r!.payload);
    expect(texto).not.toContain("MEDIA-KEY-SECRETA");
    expect(texto).not.toContain("mmg.whatsapp.net");
    expect(Object.keys(r!.payload).sort()).toEqual(["de", "id_mensaje", "jid", "medio", "nombre", "propio", "tipo", "ts"]);
  });

  it("con un LID sin número, el cliente se identifica por el jid completo", async () => {
    const r = await armar(msgTexto("hola", { de: "987654321098765@lid" }), { candidatos: ["987654321098765@lid"] });
    expect(r!.payload).toMatchObject({ de: "987654321098765@lid", jid: "987654321098765@lid" });
  });
});
