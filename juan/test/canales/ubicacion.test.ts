/**
 * La ubicación de entrega en cada canal (docs/UBICACION.md, «Contrato entre Odoo y el Worker de Juan»): el punto sale en
 * `Entrante.ubicacion`, validado, y el texto (lo que se guarda y lo único que ve el modelo) nunca lleva las coordenadas. Una ubicación
 * sin coordenadas que sirvan (números basura, fuera de rango) no se adivina. La que comparte la tienda desde el teléfono no es la de
 * nadie: ni se lee.
 */
import { describe, expect, it } from "vitest";
import type { Env } from "../../src/env";
import { crearWhatsappCloud } from "../../src/canales/whatsappCloud";
import { crearWhatsappQr, ubicacionDelPuente } from "../../src/canales/whatsappQr";
import { crearTelegram, ubicacionDeTelegram, type TgUpdate } from "../../src/canales/telegram";
import { eventosDeMeta } from "../../src/canales/metaComun";
import {
  coordenada,
  coordenadasValidas,
  crearUbicacion,
  TEXTO_UBICACION_COMPARTIDA,
  TEXTO_UBICACION_ILEGIBLE,
  TEXTO_UBICACION_PROPIA,
} from "../../src/canales/ubicacion";
import { hmacHex } from "../../src/seguridad";

/** Ningún número de las coordenadas de prueba aparece en el texto del mensaje. */
const sinCoordenadas = (texto: string | undefined) => expect(texto ?? "").not.toMatch(/9\.00|79\.5|8\.88|79\.78/);

/** Valores que NO son coordenadas: texto con basura, no finitos, fuera de rango, de otro tipo. */
const BASURA: [unknown, unknown][] = [
  ["9.0abc", -79.5],
  [Number.NaN, -79.5],
  [9, Number.POSITIVE_INFINITY],
  [90.0001, -79.5],
  [-91, -79.5],
  [9, 180.5],
  [9, -181],
  [null, -79.5],
  [9, undefined],
  [{ v: 9 }, -79.5],
  [true, -79.5],
  ["", ""],
];

describe("canales/ubicacion: la validación compartida", () => {
  it("acepta números finitos (y texto que sea solo un número) dentro de rango, con 7 decimales", () => {
    expect(coordenadasValidas(9.00123456789, -79.51234567)).toEqual({ lat: 9.0012346, lon: -79.5123457 });
    expect(coordenadasValidas("9.0012", " -79.5123 ")).toEqual({ lat: 9.0012, lon: -79.5123 });
    expect(coordenadasValidas(90, -180)).toEqual({ lat: 90, lon: -180 });
    expect(coordenadasValidas(-0, 0)).toEqual({ lat: 0, lon: 0 });
    expect(Object.is(coordenadasValidas(-0, 0)!.lat, -0)).toBe(false);
  });

  it("todo lo demás es null: nunca se adivina un punto", () => {
    for (const [lat, lon] of BASURA) expect(coordenadasValidas(lat, lon), JSON.stringify([lat, lon])).toBe(null);
    expect(coordenada("1e5")).toBe(null);
    expect(coordenada("0x10")).toBe(null);
  });

  it("el nombre y la dirección del lugar: de una línea, sin caracteres de control y recortados a 120 y 200", () => {
    const u = crearUbicacion(9, -79.5, "whatsapp", { nombre: "  Super\n99\u0000 Brisas ", direccion: "x".repeat(250) });
    expect(u).toEqual({ lat: 9, lon: -79.5, origen: "whatsapp", nombre_lugar: "Super 99 Brisas", direccion: "x".repeat(200) });
    expect(crearUbicacion(9, -79.5, "enlace", { nombre: "   ", direccion: 7 })).toEqual({ lat: 9, lon: -79.5, origen: "enlace" });
    expect(crearUbicacion(9, -79.5, "whatsapp", { nombre: "n".repeat(130) })!.nombre_lugar).toHaveLength(120);
  });
});

// ── WhatsApp Cloud ────────────────────────────────────────────────────────────

const SECRETO = "secreto-de-la-app-0123456789abcdef";
const envCloud = { META_APP_SECRET: SECRETO, META_VERIFY_TOKEN: "v", WHATSAPP_CLOUD_TOKEN: "t", WHATSAPP_PHONE_NUMBER_ID: "109876543210" } as unknown as Env;

async function firmadoCloud(value: object) {
  const crudo = JSON.stringify({ object: "whatsapp_business_account", entry: [{ id: "WABA", changes: [{ field: "messages", value }] }] });
  return new Request("https://juan.example/webhooks/whatsapp-cloud", { method: "POST", headers: { "x-hub-signature-256": `sha256=${await hmacHex(SECRETO, crudo)}` }, body: crudo });
}

const cloud = crearWhatsappCloud({ fetch: async () => Response.json({}), dormir: async () => {} });
const mensajeDeUbicacion = (location: object) => ({ from: "50760261919", id: "wamid.LOC1", timestamp: "1790000000", type: "location", location });

describe("WhatsApp Cloud: `type: location`", () => {
  it("la ubicación actual (solo coordenadas): `ubicacion` con origen «whatsapp» y el texto sin coordenadas", async () => {
    const r = await cloud.recibir(await firmadoCloud({ messages: [mensajeDeUbicacion({ latitude: 9.0012345, longitude: -79.5123456 })] }), envCloud);
    expect(r.entrantes).toHaveLength(1);
    expect(r.entrantes[0]).toMatchObject({ texto: TEXTO_UBICACION_COMPARTIDA, ubicacion: { lat: 9.0012345, lon: -79.5123456, origen: "whatsapp" } });
    expect(r.entrantes[0].ubicacion).not.toHaveProperty("nombre_lugar");
    sinCoordenadas(r.entrantes[0].texto);
  });

  it("un lugar elegido trae su nombre y dirección", async () => {
    const r = await cloud.recibir(await firmadoCloud({ messages: [mensajeDeUbicacion({ latitude: 9.0012345, longitude: -79.5123456, name: "Super 99 Brisas", address: "Vía Domingo Díaz" })] }), envCloud);
    expect(r.entrantes[0].ubicacion).toEqual({ lat: 9.0012345, lon: -79.5123456, origen: "whatsapp", nombre_lugar: "Super 99 Brisas", direccion: "Vía Domingo Díaz" });
  });

  it("sin coordenadas, con números basura o fuera de rango: sin `ubicacion` y un texto que lo dice", async () => {
    for (const [latitude, longitude] of BASURA) {
      const r = await cloud.recibir(await firmadoCloud({ messages: [mensajeDeUbicacion({ latitude, longitude })] }), envCloud);
      expect(r.entrantes[0], JSON.stringify([latitude, longitude])).not.toHaveProperty("ubicacion");
      expect(r.entrantes[0].texto).toBe(TEXTO_UBICACION_ILEGIBLE);
    }
    const sinNada = await cloud.recibir(await firmadoCloud({ messages: [{ from: "50760261919", id: "wamid.L2", type: "location" }] }), envCloud);
    expect(sinNada.entrantes[0]).toMatchObject({ texto: TEXTO_UBICACION_ILEGIBLE });
    expect(sinNada.entrantes[0]).not.toHaveProperty("ubicacion");
  });

  it("la que comparte la tienda desde el teléfono (un eco) no se lee: ni punto ni coordenadas", async () => {
    const r = await cloud.recibir(await firmadoCloud({ message_echoes: [{ ...mensajeDeUbicacion({ latitude: 9.0012345, longitude: -79.5123456 }), from: "109876543210", to: "50760261919" }] }), envCloud);
    expect(r.entrantes[0]).toMatchObject({ propio: true, texto: TEXTO_UBICACION_PROPIA });
    expect(r.entrantes[0]).not.toHaveProperty("ubicacion");
  });
});

// ── WhatsApp por QR (el puente) ───────────────────────────────────────────────

const WA_TOKEN = "token-compartido-con-el-puente-0123456789";
const envQr = { WA_TOKEN, PUENTE: { fetch: async () => Response.json({ ok: true }) } } as unknown as Env;
const qr = crearWhatsappQr({ fetch: async () => new Response("") });
const delPuente = (extra: object) =>
  new Request("https://juan.example/webhooks/whatsapp-qr", {
    method: "POST",
    headers: { "content-type": "application/json", "x-wa-token": WA_TOKEN },
    body: JSON.stringify({ id_mensaje: "3EB0LOC", de: "50760261919@s.whatsapp.net", nombre: "Karen", tipo: "texto", ts: 1_790_000_000, propio: false, ...extra }),
  });

describe("WhatsApp por QR: `ubicacion` del puente", () => {
  it("el punto que manda el puente sale validado; el texto es el de siempre, sin coordenadas", async () => {
    const r = await qr.recibir(delPuente({ texto: TEXTO_UBICACION_COMPARTIDA, ubicacion: { lat: 9.0012345, lon: -79.5123456, nombre: "Casa", direccion: "La Chorrera" } }), envQr);
    expect(r.entrantes[0]).toMatchObject({
      texto: TEXTO_UBICACION_COMPARTIDA,
      ubicacion: { lat: 9.0012345, lon: -79.5123456, origen: "whatsapp", nombre_lugar: "Casa", direccion: "La Chorrera" },
    });
  });

  it("aunque el puente mande otro texto, el que queda es el de la ubicación", async () => {
    const r = await qr.recibir(delPuente({ texto: "Ubicación: 9.0012345,-79.5123456", ubicacion: { lat: 9.0012345, lon: -79.5123456 } }), envQr);
    expect(r.entrantes[0].texto).toBe(TEXTO_UBICACION_COMPARTIDA);
  });

  it("números basura o fuera de rango: sin punto y «no llegó bien»", async () => {
    for (const [lat, lon] of BASURA) {
      const r = await qr.recibir(delPuente({ texto: TEXTO_UBICACION_COMPARTIDA, ubicacion: { lat, lon } }), envQr);
      expect(r.entrantes[0], JSON.stringify([lat, lon])).not.toHaveProperty("ubicacion");
      expect(r.entrantes[0].texto).toBe(TEXTO_UBICACION_ILEGIBLE);
    }
  });

  it("`ubicacion_omitida` (la cola de pendientes del puente no guarda el punto): el motor sabrá que hay que pedirla otra vez", async () => {
    const r = await qr.recibir(delPuente({ texto: TEXTO_UBICACION_COMPARTIDA, ubicacion_omitida: true }), envQr);
    expect(r.entrantes[0]).toMatchObject({ texto: TEXTO_UBICACION_COMPARTIDA, ubicacion_omitida: "whatsapp" });
    expect(r.entrantes[0]).not.toHaveProperty("ubicacion");
  });

  it("un puente de antes (la ubicación como texto CON coordenadas): se reconoce, el punto sale aparte y el texto queda limpio", async () => {
    const r = await qr.recibir(delPuente({ texto: "Ubicación compartida: 8.8801, -79.7834 (Casa, La Chorrera)" }), envQr);
    expect(r.entrantes[0]).toMatchObject({ texto: TEXTO_UBICACION_COMPARTIDA, ubicacion: { lat: 8.8801, lon: -79.7834, origen: "whatsapp", nombre_lugar: "Casa", direccion: "La Chorrera" } });
    sinCoordenadas(r.entrantes[0].texto);
    const sinCoords = await qr.recibir(delPuente({ texto: "Ubicación compartida: sin coordenadas (Casa)" }), envQr);
    expect(sinCoords.entrantes[0]).toMatchObject({ texto: TEXTO_UBICACION_ILEGIBLE });
    expect(sinCoords.entrantes[0]).not.toHaveProperty("ubicacion");
    const fuera = await qr.recibir(delPuente({ texto: "Ubicación compartida: 98.8801, -79.7834" }), envQr);
    expect(fuera.entrantes[0]).toMatchObject({ texto: TEXTO_UBICACION_ILEGIBLE });
  });

  it("la que comparte la tienda desde el teléfono (propio) no viaja como punto, ni la nueva ni la de un puente de antes", async () => {
    for (const extra of [{ ubicacion: { lat: 9.0012345, lon: -79.5123456 } }, { texto: "Ubicación compartida: 9.0012345, -79.5123456" }]) {
      const r = await qr.recibir(delPuente({ texto: "Ubicación compartida desde el teléfono", propio: true, ...extra }), envQr);
      expect(r.entrantes[0]).toMatchObject({ propio: true, texto: TEXTO_UBICACION_PROPIA });
      expect(r.entrantes[0]).not.toHaveProperty("ubicacion");
      sinCoordenadas(r.entrantes[0].texto);
    }
  });

  it("un texto cualquiera que no es una ubicación no se toca", () => {
    expect(ubicacionDelPuente({ texto: "Mi ubicación compartida: casa verde" })).toBe(null);
    expect(ubicacionDelPuente({ texto: "hola" })).toBe(null);
  });
});

// ── Telegram ──────────────────────────────────────────────────────────────────

const SECRETO_TG = "secreto-telegram-0123456789";
const envTg = { TELEGRAM_BOT_TOKEN_JUAN: "123:ABC", TELEGRAM_WEBHOOK_SECRET_JUAN: SECRETO_TG } as unknown as Env;
const telegram = crearTelegram({ fetch: async () => Response.json({ ok: true, result: {} }), dormir: async () => {} });
const deTelegram = (msg: Partial<NonNullable<TgUpdate["message"]>>) =>
  new Request("https://juan.example/webhooks/telegram", {
    method: "POST",
    headers: { "content-type": "application/json", "x-telegram-bot-api-secret-token": SECRETO_TG },
    body: JSON.stringify({ update_id: 1, message: { message_id: 7, from: { id: 555, first_name: "Karen" }, chat: { id: 555, type: "private" }, date: 1_790_000_000, ...msg } }),
  });

describe("Telegram: `message.location` y `message.venue`", () => {
  it("la ubicación compartida: `ubicacion` con origen «whatsapp» (el valor del contrato para «compartida en el chat»)", async () => {
    const r = await telegram.recibir(deTelegram({ location: { latitude: 9.0012345, longitude: -79.5123456 } }), envTg);
    expect(r.entrantes[0]).toMatchObject({ texto: TEXTO_UBICACION_COMPARTIDA, ubicacion: { lat: 9.0012345, lon: -79.5123456, origen: "whatsapp" } });
    sinCoordenadas(r.entrantes[0].texto);
  });

  it("un lugar (venue) trae nombre y dirección", async () => {
    const r = await telegram.recibir(
      deTelegram({ location: { latitude: 9.0012345, longitude: -79.5123456 }, venue: { location: { latitude: 9.0012345, longitude: -79.5123456 }, title: "Super 99", address: "Vía Domingo Díaz" } }),
      envTg,
    );
    expect(r.entrantes[0].ubicacion).toEqual({ lat: 9.0012345, lon: -79.5123456, origen: "whatsapp", nombre_lugar: "Super 99", direccion: "Vía Domingo Díaz" });
  });

  it("números basura o fuera de rango: sin punto y «no llegó bien»", async () => {
    for (const [latitude, longitude] of BASURA) {
      const r = await telegram.recibir(deTelegram({ location: { latitude, longitude } }), envTg);
      expect(r.entrantes[0], JSON.stringify([latitude, longitude])).not.toHaveProperty("ubicacion");
      expect(r.entrantes[0].texto).toBe(TEXTO_UBICACION_ILEGIBLE);
    }
    expect(ubicacionDeTelegram({ venue: { title: "x" } })).toBe("ilegible");
    expect(ubicacionDeTelegram({})).toBe(null);
  });

  it("si cita un mensaje con ubicación, lo citado dice «Ubicación», nunca las coordenadas", async () => {
    const r = await telegram.recibir(
      deTelegram({ text: "aquí", reply_to_message: { message_id: 5, from: { id: 555 }, chat: { id: 555, type: "private" }, date: 1, location: { latitude: 9.0012345, longitude: -79.5123456 } } }),
      envTg,
    );
    expect(r.entrantes[0].cita).toMatchObject({ texto: "Ubicación" });
    expect(r.entrantes[0]).not.toHaveProperty("ubicacion");
  });
});

// ── Messenger e Instagram ─────────────────────────────────────────────────────

const deMeta = (message: object, extra: object = {}) => ({
  object: "page",
  entry: [{ id: "PAGINA", messaging: [{ sender: { id: "PSID1" }, recipient: { id: "PAGINA" }, timestamp: 1_790_000_000_000, message: { mid: "m_loc", ...message }, ...extra }] }],
});

describe("Messenger e Instagram: adjunto `location`", () => {
  it("con `payload.coordinates`: `ubicacion` con origen «whatsapp» y el texto sin coordenadas", () => {
    const [e] = eventosDeMeta(deMeta({ attachments: [{ type: "location", title: "Ubicación de Karen", payload: { coordinates: { lat: 9.0012345, long: -79.5123456 } } }] }) as never, 0);
    expect(e).toMatchObject({ canal: "messenger", texto: TEXTO_UBICACION_COMPARTIDA, ubicacion: { lat: 9.0012345, lon: -79.5123456, origen: "whatsapp" } });
    // El título de Meta no es un lugar (suele traer el nombre de la persona): no viaja.
    expect(e.ubicacion).not.toHaveProperty("nombre_lugar");
  });

  it("sin coordenadas o con basura: nada se inventa", () => {
    for (const payload of [{}, { coordinates: {} }, { coordinates: { lat: "x", long: -79.5 } }, { coordinates: { lat: 9, long: 500 } }, { url: "https://www.bing.com/maps?x" }]) {
      const [e] = eventosDeMeta(deMeta({ attachments: [{ type: "location", payload }] }) as never, 0);
      expect(e, JSON.stringify(payload)).not.toHaveProperty("ubicacion");
      expect(e.texto).toBe(TEXTO_UBICACION_ILEGIBLE);
    }
  });

  it("la que manda la página (un eco) no se lee", () => {
    const [e] = eventosDeMeta(deMeta({ is_echo: true, attachments: [{ type: "location", payload: { coordinates: { lat: 9.0012345, long: -79.5123456 } } }] }, { sender: { id: "PAGINA" }, recipient: { id: "PSID1" } }) as never, 0);
    expect(e).toMatchObject({ propio: true, texto: TEXTO_UBICACION_PROPIA });
    expect(e).not.toHaveProperty("ubicacion");
  });

  it("un enlace de mapa compartido desde la app (adjunto `fallback`) pasa al texto, para sacar el punto de ahí", () => {
    const [e] = eventosDeMeta(deMeta({ attachments: [{ type: "fallback", payload: { url: "https://maps.app.goo.gl/AbCdEf123" } }] }) as never, 0);
    expect(e.texto).toBe("https://maps.app.goo.gl/AbCdEf123");
    // Si el texto ya trae el enlace, no se repite; un enlace que no es de mapa sigue como siempre.
    const [conTexto] = eventosDeMeta(deMeta({ text: "aquí https://maps.app.goo.gl/AbCdEf123", attachments: [{ type: "fallback", payload: { url: "https://maps.app.goo.gl/AbCdEf123" } }] }) as never, 0);
    expect(conTexto.texto).toBe("aquí https://maps.app.goo.gl/AbCdEf123");
    const [otro] = eventosDeMeta(deMeta({ attachments: [{ type: "fallback", payload: { url: "https://ejemplo.com/x" } }] }) as never, 0);
    expect(otro.texto).toBe("(el cliente compartió un enlace)");
  });
});
