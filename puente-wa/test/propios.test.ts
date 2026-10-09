import { describe, expect, it } from "vitest";
import { ENTRANTE_VIGENTE_MS, RESPUESTA_VIGENTE_MS, contenidoDe, crearRegistroDeEnvios, decidirUpsert, textoDe, tipoDe } from "../contenedor/lib/propios.mjs";
import {
  CLIENTE,
  NEGOCIO,
  msgAudio,
  msgContacto,
  msgDocumento,
  msgImagen,
  msgProtocolo,
  msgReaccion,
  msgSticker,
  msgTemporal,
  msgTexto,
  msgTextoLargo,
  msgUbicacion,
  msgVideo,
} from "./ayuda/baileys";

const AHORA = 1_800_000_000_000;
const s = (ms: number) => Math.floor(ms / 1000);
const ctx = (extra: Record<string, unknown> = {}) => ({ enviados: crearRegistroDeEnvios(), yo: [NEGOCIO, "999999999999999:3@lid"], ahora: AHORA, ...extra });

describe("contenidoDe: qué trae cada mensaje", () => {
  it("texto, en sus dos formas, y con la envoltura de mensajes temporales", () => {
    expect(contenidoDe(msgTexto("hola"))).toMatchObject({ clase: "texto", texto: "hola" });
    expect(contenidoDe(msgTextoLargo("hola con enlace"))).toMatchObject({ clase: "texto", texto: "hola con enlace" });
    expect(contenidoDe(msgTemporal("se borra"))).toMatchObject({ clase: "texto", texto: "se borra" });
  });

  it("imagen, audio, documento, video: tipo, leyenda, mime, nombre y tamaño", () => {
    expect(contenidoDe(msgImagen({ caption: "mira", tam: 1234 }))).toEqual({ clase: "imagen", texto: "mira", mime: "image/jpeg", nombre: null, tamano: 1234 });
    expect(contenidoDe(msgAudio())).toMatchObject({ clase: "audio", mime: "audio/ogg; codecs=opus", texto: null });
    expect(contenidoDe(msgDocumento({ caption: "el comprobante", nombre: "pago.pdf" }))).toMatchObject({
      clase: "documento",
      texto: "el comprobante",
      nombre: "pago.pdf",
      mime: "application/pdf",
    });
    expect(contenidoDe(msgVideo({ caption: "así se ve" }))).toMatchObject({ clase: "video", texto: "así se ve" });
  });

  it("el tamaño llega como Long de protobuf, número o texto", () => {
    const m: any = msgImagen();
    m.message.imageMessage.fileLength = { toNumber: () => 7777, low: 7777, high: 0 };
    expect(contenidoDe(m).tamano).toBe(7777);
    m.message.imageMessage.fileLength = "4321";
    expect(contenidoDe(m).tamano).toBe(4321);
    m.message.imageMessage.fileLength = undefined;
    expect(contenidoDe(m).tamano).toBe(0);
  });

  it("ubicación y contacto viajan como texto descriptivo (datos, no instrucciones)", () => {
    expect(contenidoDe(msgUbicacion())).toMatchObject({ clase: "ubicacion", texto: "Ubicación compartida: 8.8801, -79.7834 (Casa, La Chorrera)" });
    expect(contenidoDe(msgContacto())).toMatchObject({ clase: "contacto", texto: "Contacto compartido: Marisol" });
  });

  it("reacciones, borrados y avisos del protocolo no son mensajes", () => {
    expect(contenidoDe(msgReaccion()).clase).toBe(null);
    expect(contenidoDe(msgProtocolo()).clase).toBe(null);
    expect(contenidoDe({ key: {}, message: {} }).clase).toBe(null);
    expect(contenidoDe({ key: {} }).clase).toBe(null);
  });

  it("tipoDe y textoDe (heredados del CRM de origen)", () => {
    expect(tipoDe(msgImagen())).toBe("imageMessage");
    expect(tipoDe({ message: { messageContextInfo: {}, senderKeyDistributionMessage: {}, conversation: "x" } })).toBe("conversation");
    expect(textoDe(msgImagen({ caption: "leyenda" }))).toBe("leyenda");
    expect(textoDe(msgAudio())).toBe(null);
  });
});

describe("decidirUpsert: ¿cliente, vendedora desde el teléfono, eco o nada?", () => {
  it("un cliente escribe en vivo → entrante", () => {
    expect(decidirUpsert(msgTexto("hola", { ts: s(AHORA) }), "notify", ctx())).toEqual({ accion: "entrante" });
    expect(decidirUpsert(msgImagen({ ts: s(AHORA) }), "notify", ctx())).toEqual({ accion: "entrante" });
    expect(decidirUpsert(msgAudio({ ts: s(AHORA) }), "notify", ctx())).toEqual({ accion: "entrante" });
  });

  it.each([
    ["un estado de un contacto", "status@broadcast"],
    ["una lista de difusión", "12345@broadcast"],
    ["un grupo", "120363025246125486@g.us"],
    ["un canal", "120363025246125486@newsletter"],
    ["un bot de Meta", "13135550002@bot"],
  ])("NUNCA atiende %s", (_n, jid) => {
    expect(decidirUpsert(msgTexto("hola", { de: jid, ts: s(AHORA) }), "notify", ctx())).toEqual({ accion: "ignorar", motivo: "no_es_chat" });
    // ni siquiera si lo escribió la propia dueña en ese chat
    expect(decidirUpsert(msgTexto("hola", { de: jid, fromMe: true, ts: s(AHORA) }), "notify", ctx())).toEqual({ accion: "ignorar", motivo: "no_es_chat" });
  });

  it("ignora el historial viejo (append) de otros", () => {
    expect(decidirUpsert(msgTexto("viejo", { ts: s(AHORA) }), "append", ctx())).toEqual({ accion: "ignorar", motivo: "historial" });
  });

  it("ignora un mensaje de cliente de hace más de un día aunque llegue «en vivo»", () => {
    const viejo = msgTexto("hola", { ts: s(AHORA - ENTRANTE_VIGENTE_MS - 5000) });
    expect(decidirUpsert(viejo, "notify", ctx())).toEqual({ accion: "ignorar", motivo: "viejo" });
    const dehoras = msgTexto("hola", { ts: s(AHORA - 5 * 3_600_000) });
    expect(decidirUpsert(dehoras, "notify", ctx())).toEqual({ accion: "entrante" }); // lo de la noche sí se contesta
  });

  it("ignora stickers, reacciones y avisos del protocolo de un cliente", () => {
    expect(decidirUpsert(msgSticker({ ts: s(AHORA) }), "notify", ctx())).toEqual({ accion: "ignorar", motivo: "sticker" });
    expect(decidirUpsert(msgReaccion({ ts: s(AHORA) }), "notify", ctx())).toEqual({ accion: "ignorar", motivo: "sin_contenido" });
    expect(decidirUpsert(msgProtocolo({ ts: s(AHORA) }), "notify", ctx())).toEqual({ accion: "ignorar", motivo: "sin_contenido" });
  });

  it("un mensaje sin id no se puede deduplicar: se ignora", () => {
    const m: any = msgTexto("x", { ts: s(AHORA) });
    delete m.key.id;
    expect(decidirUpsert(m, "notify", ctx())).toEqual({ accion: "ignorar", motivo: "sin_id" });
  });

  describe("fromMe: lo que sale del número del negocio", () => {
    it("el eco de lo que mandó el propio puente se ignora", () => {
      const c = ctx();
      c.enviados.anotar("3EB0ECO", AHORA);
      const eco = msgTexto("Hola, soy el equipo de D'CASA", { id: "3EB0ECO", fromMe: true, ts: s(AHORA) });
      expect(decidirUpsert(eco, "notify", c)).toEqual({ accion: "ignorar", motivo: "eco_del_bot" });
    });

    it("lo que escribe la vendedora desde el teléfono → propio", () => {
      const m = msgTexto("Buenas, le atiende Marisol", { fromMe: true, ts: s(AHORA) });
      expect(decidirUpsert(m, "notify", ctx())).toEqual({ accion: "propio" });
      // También llega como «append» al reconectar: si es reciente, cuenta.
      expect(decidirUpsert(m, "append", ctx())).toEqual({ accion: "propio" });
    });

    it("cualquier cosa que la vendedora mande cuenta como tomar la conversación (foto, sticker, ubicación…)", () => {
      for (const m of [msgImagen, msgSticker, msgUbicacion, msgDocumento, msgAudio, msgContacto]) {
        expect(decidirUpsert(m({ fromMe: true, ts: s(AHORA) }), "notify", ctx())).toEqual({ accion: "propio" });
      }
    });

    it("una reacción o un borrado suyo NO es tomar la conversación", () => {
      expect(decidirUpsert(msgReaccion({ fromMe: true, ts: s(AHORA) }), "notify", ctx())).toEqual({ accion: "ignorar", motivo: "sin_contenido" });
      expect(decidirUpsert(msgProtocolo({ fromMe: true, ts: s(AHORA) }), "notify", ctx())).toEqual({ accion: "ignorar", motivo: "sin_contenido" });
    });

    it("lo que escribió hace horas (historial de un chat) no pausa nada", () => {
      const viejo = msgTexto("hola", { fromMe: true, ts: s(AHORA - RESPUESTA_VIGENTE_MS - 60_000) });
      expect(decidirUpsert(viejo, "append", ctx())).toEqual({ accion: "ignorar", motivo: "propio_viejo" });
    });

    it("las notas personales (un chat con uno mismo) no son una clienta", () => {
      const nota = msgTexto("comprar tornillos", { fromMe: true, de: "50760269999@s.whatsapp.net", ts: s(AHORA) });
      expect(decidirUpsert(nota, "notify", ctx())).toEqual({ accion: "ignorar", motivo: "nota_personal" });
      const notaLid = msgTexto("x", { fromMe: true, de: "999999999999999@lid", ts: s(AHORA) });
      expect(decidirUpsert(notaLid, "notify", ctx())).toEqual({ accion: "ignorar", motivo: "nota_personal" });
    });

    it("tras un reinicio, los ids que el Worker recuerda siguen reconociendo el eco", () => {
      const reg = crearRegistroDeEnvios();
      reg.cargar([
        { id: "VIEJO1", ts: AHORA - 30 * 60_000 },
        { id: "VIEJO2", ts: AHORA - 10 * 60_000 },
      ]);
      const eco = msgTexto("respuesta del bot", { id: "VIEJO2", fromMe: true, ts: s(AHORA - 10 * 60_000) });
      expect(decidirUpsert(eco, "append", { enviados: reg, yo: [NEGOCIO], ahora: AHORA })).toEqual({ accion: "ignorar", motivo: "eco_del_bot" });
    });
  });
});

describe("registro de envíos del bot", () => {
  it("se poda solo y no crece sin límite", () => {
    const r = crearRegistroDeEnvios();
    for (let i = 0; i < 2500; i++) r.anotar(`id${i}`, AHORA + i);
    expect(r.tamano).toBeLessThanOrEqual(2001);
    expect(r.tiene("id2499")).toBe(true);
    expect(r.tiene("id0")).toBe(false);
    // lo de hace más de 2 horas se olvida
    r.anotar("nuevo", AHORA + 3 * 3_600_000);
    expect(r.tiene("id2499")).toBe(false);
    expect(r.tiene("nuevo")).toBe(true);
  });
});

describe("el cliente de la prueba", () => {
  it("usa números ficticios", () => {
    expect(CLIENTE).toMatch(/^507/);
  });
});
