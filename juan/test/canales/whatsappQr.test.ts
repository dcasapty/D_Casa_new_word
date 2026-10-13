/**
 * WhatsApp por QR, vía el puente (contrato en docs/JUAN.md → «Worker ↔ puente QR»).
 *   Puente → Worker: POST /webhooks/whatsapp-qr {id_mensaje, de, nombre, tipo, texto?, medio?, ts, propio}
 *   Worker → Puente: POST /api/enviar {para, chunks:[...], medios?:[...]}
 * Reescritura de test/channels/whatsappQr.test.ts y test/puente-wa/*.test.ts del CRM de Baby Caleb (la parte del Worker).
 */
import { describe, expect, it } from "vitest";
import type { Env } from "../../src/env";
import { crearWhatsappQr, esChatDeUnaPersona, idExternoDeJid } from "../../src/canales/whatsappQr";
import { EnvioParcialError } from "../../src/canales/tipos";
import { tokenDelPuente, tokenParaCabecera, tokensIguales } from "../../src/seguridad";

const WA_TOKEN = "token-compartido-con-el-puente-0123456789";

interface PeticionAlPuente {
  url: string;
  metodo: string;
  cabeceras: Record<string, string>;
  cuerpo: any;
}

function puenteFalso(respuesta: (p: PeticionAlPuente) => Response = () => Response.json({ ok: true, enviados: 1 })) {
  const peticiones: PeticionAlPuente[] = [];
  const binding = {
    fetch: async (url: string, init?: RequestInit) => {
      const p = { url, metodo: init?.method ?? "GET", cabeceras: Object.fromEntries(Object.entries((init?.headers ?? {}) as Record<string, string>)), cuerpo: init?.body ? JSON.parse(String(init.body)) : null };
      peticiones.push(p);
      return respuesta(p);
    },
  };
  return { peticiones, env: { WA_TOKEN, PUENTE: binding } as unknown as Env };
}

const adaptador = crearWhatsappQr({ fetch: async () => new Response(new Uint8Array([1, 2, 3]), { headers: { "content-type": "image/jpeg" } }) });

const entrante = (cuerpo: object, cabeceras: Record<string, string> = { "x-wa-token": WA_TOKEN }) =>
  new Request("https://juan.example/webhooks/whatsapp-qr", { method: "POST", headers: { "content-type": "application/json", ...cabeceras }, body: JSON.stringify(cuerpo) });

const mensaje = (extra: object = {}) => ({ id_mensaje: "3EB0A1", de: "50760261919@s.whatsapp.net", nombre: "Karen", tipo: "texto", texto: "Hola, ¿tienen camas queen?", ts: 1_790_000_000, propio: false, ...extra });

describe("el webhook del puente", () => {
  it("un mensaje de texto: el celular E.164 sin + es la llave", async () => {
    const { env } = puenteFalso();
    const r = await adaptador.recibir(entrante(mensaje()), env);
    expect(r.respuesta.status).toBe(200);
    expect(r.entrantes).toEqual([
      {
        canal: "whatsapp_qr",
        id_externo: "50760261919",
        id_mensaje: "3EB0A1",
        nombre: "Karen",
        celular: "50760261919",
        texto: "Hola, ¿tienen camas queen?",
        adjuntos: [],
        ts: 1_790_000_000_000,
        propio: false,
      },
    ]);
  });

  it("se responde DESPUÉS de guardar (esperar): si falla, el puente recibe el error y reintenta", async () => {
    const { env } = puenteFalso();
    expect((await adaptador.recibir(entrante(mensaje()), env)).esperar).toBe(true);
  });

  it("valida el token del puente (cabecera en claro o en base64), en tiempo constante y fallando cerrado", async () => {
    const { env } = puenteFalso();
    expect((await adaptador.recibir(entrante(mensaje(), { "x-wa-token-b64": tokenParaCabecera(WA_TOKEN) }), env)).entrantes).toHaveLength(1);
    for (const mal of [{} as Record<string, string>, { "x-wa-token": "" }, { "x-wa-token": "otro" }, { "x-wa-token": WA_TOKEN + "x" }, { "x-wa-token-b64": "%%%" }]) {
      const r = await adaptador.recibir(entrante(mensaje(), mal), env);
      expect(r.respuesta.status, JSON.stringify(mal)).toBe(401);
      expect(r.entrantes).toEqual([]);
    }
    const sinToken = { PUENTE: {} } as unknown as Env;
    expect((await adaptador.recibir(entrante(mensaje(), { "x-wa-token": "" }), sinToken)).respuesta.status).toBe(401);
  });

  it("un token con tilde o eñe viaja bien en base64 (Node lo corrompería en una cabecera en claro)", () => {
    const raro = "clave-con-ñandú-y-tildé";
    const req = new Request("https://x", { headers: { "x-wa-token-b64": tokenParaCabecera(raro) } });
    expect(tokenDelPuente(req)).toBe(raro);
    expect(tokensIguales(tokenDelPuente(req), raro)).toBe(true);
    expect(tokensIguales("a", "")).toBe(false);
    expect(tokensIguales("", "")).toBe(false);
  });

  it("propio:true = la vendedora escribió desde el teléfono → viaja marcado para registrarla y pausar al bot", async () => {
    const { env } = puenteFalso();
    const r = await adaptador.recibir(entrante(mensaje({ propio: true, texto: "Hola Karen, soy Marisol" })), env);
    expect(r.entrantes[0]).toMatchObject({ propio: true, id_externo: "50760261919", texto: "Hola Karen, soy Marisol" });
  });

  it("imagen con base64: llega en bytes con su tipo y nombre", async () => {
    const { env } = puenteFalso();
    const r = await adaptador.recibir(entrante(mensaje({ tipo: "imagen", texto: "mi pago", medio: { base64: btoa("\xff\xd8\xff\xe0abc"), mime: "image/jpeg", nombre: "yappy.jpg" } })), env);
    const a = r.entrantes[0].adjuntos[0];
    expect(a).toMatchObject({ tipo: "imagen", mime: "image/jpeg", nombre: "yappy.jpg" });
    expect(a.bytes!.length).toBe(7);
    expect(r.entrantes[0].texto).toBe("mi pago");
  });

  it("audio y documento con URL temporal del puente: se pueden bajar", async () => {
    const { env } = puenteFalso();
    const r = await adaptador.recibir(
      entrante(mensaje({ tipo: "documento", texto: null, medio: { url_temporal: "https://puente.example/tmp/abc", mime: "application/pdf", nombre: "cedula.pdf" } })),
      env,
    );
    const a = r.entrantes[0].adjuntos[0];
    expect(a).toMatchObject({ tipo: "documento", url: "https://puente.example/tmp/abc", nombre: "cedula.pdf" });
    expect([...(await a.obtener!())!.bytes]).toEqual([1, 2, 3]);
    const v = await adaptador.recibir(entrante(mensaje({ tipo: "audio", texto: null, medio: { base64: btoa("xyz"), mime: "audio/ogg" } })), env);
    expect(v.entrantes[0].adjuntos[0].tipo).toBe("audio");
  });

  it("el puente manda `de` como el celular (E.164 sin +) y un archivo omitido (muy pesado) NO hace perder el mensaje", async () => {
    // La forma REAL del puente (puente-wa/contenedor/lib/contrato.mjs → construirWebhook): `de` sin «@s.whatsapp.net», `jid` aparte
    // y `medio_omitido` cuando el archivo no cupo. Hallado con el puente real en la integración con Odoo.
    const { env } = puenteFalso();
    const r = await adaptador.recibir(
      entrante(mensaje({ de: "50760261919", jid: "50760261919@s.whatsapp.net", tipo: "video", texto: undefined, medio_omitido: { motivo: "tamano", mime: "video/mp4", bytes: 99_000_000 } })),
      env,
    );
    expect(r.entrantes).toHaveLength(1);
    expect(r.entrantes[0]).toMatchObject({ id_externo: "50760261919", celular: "50760261919", canal: "whatsapp_qr" });
    expect(r.entrantes[0].adjuntos).toEqual([{ tipo: "video", mime: "video/mp4" }]);
    // Un tipo de archivo sin medio y sin motivo sigue siendo nada que contestar (no se inventa un adjunto).
    expect((await adaptador.recibir(entrante(mensaje({ tipo: "video", texto: null })), env)).entrantes).toEqual([]);
  });

  it("sticker, ubicación y contacto llegan como una nota; reacciones y borrados (sin texto ni archivo) se ignoran", async () => {
    const { env } = puenteFalso();
    expect((await adaptador.recibir(entrante(mensaje({ tipo: "ubicacion", texto: null })), env)).entrantes[0].texto).toBe("(el cliente mandó una ubicación)");
    expect((await adaptador.recibir(entrante(mensaje({ tipo: "sticker", texto: null })), env)).entrantes[0].texto).toBe("(el cliente mandó un sticker)");
    expect((await adaptador.recibir(entrante(mensaje({ tipo: "reaccion", texto: null })), env)).entrantes).toEqual([]);
  });

  it("estados, grupos, canales y bots de Meta no son un cliente: se ignoran", async () => {
    const { env } = puenteFalso();
    for (const de of ["status@broadcast", "120363@g.us", "1203@newsletter", "13135550@bot"]) {
      expect((await adaptador.recibir(entrante(mensaje({ de })), env)).entrantes, de).toEqual([]);
    }
    expect(esChatDeUnaPersona("50760261919@s.whatsapp.net")).toBe(true);
    expect(esChatDeUnaPersona("status@broadcast")).toBe(false);
    expect(esChatDeUnaPersona("")).toBe(false);
  });

  it("el JID: se quita el sufijo del servidor, pero un «@lid» se conserva entero (es lo único con lo que se puede contestar)", async () => {
    expect(idExternoDeJid("50760261919@s.whatsapp.net")).toBe("50760261919");
    expect(idExternoDeJid("50760261919:12@s.whatsapp.net")).toBe("50760261919");
    expect(idExternoDeJid("50760261919@c.us")).toBe("50760261919");
    expect(idExternoDeJid("+50760261919")).toBe("50760261919");
    expect(idExternoDeJid("118263@lid")).toBe("118263@lid");
    const { env } = puenteFalso();
    const r = await adaptador.recibir(entrante(mensaje({ de: "118263@lid" })), env);
    expect(r.entrantes[0]).toMatchObject({ id_externo: "118263@lid" });
    expect(r.entrantes[0].celular).toBeUndefined();
  });

  it("la hora puede venir en segundos, milisegundos o ISO", async () => {
    const { env } = puenteFalso();
    const ts = async (v: unknown) => (await adaptador.recibir(entrante(mensaje({ ts: v })), env)).entrantes[0].ts;
    expect(await ts(1_790_000_000)).toBe(1_790_000_000_000);
    expect(await ts(1_790_000_000_000)).toBe(1_790_000_000_000);
    expect(await ts("2026-10-09T15:00:00Z")).toBe(Date.parse("2026-10-09T15:00:00Z"));
  });

  it("un cuerpo que no es JSON → 400 (el puente lo anota; un mensaje que se pierde en silencio es peor)", async () => {
    const { env } = puenteFalso();
    const r = await adaptador.recibir(new Request("https://x", { method: "POST", headers: { "x-wa-token": WA_TOKEN }, body: "basura" }), env);
    expect(r.respuesta.status).toBe(400);
  });

  it("solo POST", async () => {
    const { env } = puenteFalso();
    expect((await adaptador.recibir(new Request("https://x", { method: "GET" }), env)).respuesta.status).toBe(405);
  });
});

describe("enviar por el puente", () => {
  it("POST /api/enviar con {para, chunks}, por el service binding y con el token en base64", async () => {
    const { env, peticiones } = puenteFalso();
    await adaptador.enviar("whatsapp_qr", { para: "50760261919", burbujas: ["Uno", "Dos"], medios: [] }, env);
    expect(peticiones).toHaveLength(1);
    expect(peticiones[0].url).toBe("https://puente/api/enviar");
    expect(peticiones[0].metodo).toBe("POST");
    expect(peticiones[0].cuerpo).toEqual({ para: "50760261919", chunks: ["Uno", "Dos"] });
    expect(peticiones[0].cabeceras["x-wa-token-b64"]).toBe(tokenParaCabecera(WA_TOKEN));
    expect(JSON.stringify(peticiones[0])).not.toContain(WA_TOKEN);
  });

  it("imágenes y documentos viajan en `medios` con tipo, url, nombre, mime y pie", async () => {
    const { env, peticiones } = puenteFalso();
    await adaptador.enviar(
      "whatsapp_qr",
      {
        para: "50760261919",
        burbujas: ["Te la envío"],
        medios: [
          { tipo: "imagen", url: "https://dcasapty.com/foto.jpg", nombre: "Cama Queen", mime: "image/jpeg", pie: "Cama Queen Milán" },
          { tipo: "documento", url: "https://odoo.example/cot.pdf", nombre: "cotizacion.pdf", mime: "application/pdf" },
        ],
      },
      env,
    );
    expect(peticiones[0].cuerpo.medios).toEqual([
      { tipo: "imagen", url: "https://dcasapty.com/foto.jpg", nombre: "Cama Queen", mime: "image/jpeg", pie: "Cama Queen Milán" },
      { tipo: "documento", url: "https://odoo.example/cot.pdf", nombre: "cotizacion.pdf", mime: "application/pdf" },
    ]);
  });

  it("jamás manda a un estado, grupo o canal (sería PUBLICAR con el número del negocio)", async () => {
    const { env, peticiones } = puenteFalso();
    for (const para of ["status@broadcast", "123@g.us", "1@newsletter"]) {
      await expect(adaptador.enviar("whatsapp_qr", { para, burbujas: ["x"], medios: [] }, env)).rejects.toThrow(/no es el chat de una persona/);
    }
    expect(peticiones).toHaveLength(0);
  });

  it("si el puente contesta con error, se lanza para que se vea (no se pierde en silencio)", async () => {
    const { env } = puenteFalso(() => new Response("socket cerrado", { status: 503 }));
    await expect(adaptador.enviar("whatsapp_qr", { para: "50760261919", burbujas: ["x"], medios: [] }, env)).rejects.toThrow(/503.*socket cerrado/);
  });

  it("si el puente alcanzó a mandar parte antes de fallar, lo avisa (lo que salió no se repite)", async () => {
    const { env } = puenteFalso(() => Response.json({ ok: false, error: "socket cerrado", ids: ["A1"], enviados: { chunks: 1, medios: 0 }, parcial: true }, { status: 502 }));
    const e = await adaptador.enviar("whatsapp_qr", { para: "50760261919", burbujas: ["Uno", "Dos"], medios: [] }, env).catch((x) => x);
    expect(e).toBeInstanceOf(EnvioParcialError);
    expect(e.enviado).toEqual({ burbujas: 1, medios: 0, ids: ["A1"] });
    expect(e.message).toMatch(/502.*socket cerrado/);
  });

  it("el conteo del puente incluye el resto de un pie largo: aquí solo cuentan las burbujas propias y los archivos", async () => {
    const { env } = puenteFalso(() => Response.json({ ok: false, ids: ["A", "B", "C"], enviados: { chunks: 5, medios: 1 } }, { status: 502 }));
    const e = await adaptador.enviar("whatsapp_qr", { para: "50760261919", burbujas: ["Uno"], medios: [{ tipo: "imagen", url: "https://x/f.jpg" }] }, env).catch((x) => x);
    expect(e.enviado).toMatchObject({ burbujas: 1, medios: 1 });
  });

  it("un 502 sin nada enviado, o con un cuerpo que no es JSON, es un error normal", async () => {
    for (const respuesta of [() => Response.json({ ok: false, ids: [], enviados: { chunks: 0, medios: 0 } }, { status: 502 }), () => new Response("<html>bad gateway</html>", { status: 502 })]) {
      const { env } = puenteFalso(respuesta);
      const e = await adaptador.enviar("whatsapp_qr", { para: "50760261919", burbujas: ["Uno"], medios: [] }, env).catch((x) => x);
      expect(e).toBeInstanceOf(Error);
      expect(e).not.toBeInstanceOf(EnvioParcialError);
    }
  });

  it("sin el binding PUENTE o sin WA_TOKEN, lo dice por su nombre", async () => {
    await expect(adaptador.enviar("whatsapp_qr", { para: "50760261919", burbujas: ["x"], medios: [] }, { WA_TOKEN } as Env)).rejects.toThrow(/PUENTE/);
    await expect(adaptador.enviar("whatsapp_qr", { para: "50760261919", burbujas: ["x"], medios: [] }, { PUENTE: { fetch: async () => new Response() } } as unknown as Env)).rejects.toThrow(/WA_TOKEN/);
  });

  it("capacidades: imágenes y documentos, sin ventana de 24 h; ruta del contrato", () => {
    expect(adaptador.capacidades("whatsapp_qr")).toMatchObject({ imagenes: true, documentos: true, ventana24h: false });
    expect(adaptador.ruta).toBe("/webhooks/whatsapp-qr");
    expect(adaptador.canales).toEqual(["whatsapp_qr"]);
  });
});

describe("salud del puente", () => {
  it("conectado / necesita QR / caído, según GET /api/estado", async () => {
    const conectado = puenteFalso(() => Response.json({ conexion: "conectada" }));
    expect(await adaptador.salud!("whatsapp_qr", conectado.env)).toMatchObject({ configurado: true, conectado: true });
    expect(conectado.peticiones[0].url).toBe("https://puente/api/estado");
    const qr = puenteFalso(() => Response.json({ conexion: "esperando-qr" }));
    expect(await adaptador.salud!("whatsapp_qr", qr.env)).toMatchObject({ conectado: false, detalle: "esperando-qr" });
    const boolean = puenteFalso(() => Response.json({ conectado: true }));
    expect((await adaptador.salud!("whatsapp_qr", boolean.env)).conectado).toBe(true);
    const caido = puenteFalso(() => new Response("x", { status: 502 }));
    expect(await adaptador.salud!("whatsapp_qr", caido.env)).toMatchObject({ conectado: false, detalle: "el puente contestó 502" });
  });

  it("si el puente no responde, no se cae: lo dice", async () => {
    const env = { WA_TOKEN, PUENTE: { fetch: async () => { throw new Error("Network connection lost"); } } } as unknown as Env;
    expect(await adaptador.salud!("whatsapp_qr", env)).toMatchObject({ configurado: true, conectado: false });
  });

  it("sin binding o sin token: dice los NOMBRES que faltan", async () => {
    expect(await adaptador.salud!("whatsapp_qr", {} as Env)).toEqual({ configurado: false, faltan: ["PUENTE", "WA_TOKEN"], conectado: null });
    expect(adaptador.faltantes({ WA_TOKEN } as Env, "whatsapp_qr")).toEqual(["PUENTE"]);
  });
});

describe("foto de perfil (vía el puente)", () => {
  const BYTES = new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 7, 7]);
  const base64 = btoa(String.fromCharCode(...BYTES));

  it("la pide con POST /api/foto-perfil (con el token) y devuelve los bytes", async () => {
    const { env, peticiones } = puenteFalso(() => Response.json({ ok: true, mime: "image/jpeg", base64 }));
    const foto = await adaptador.fotoDePerfil!("whatsapp_qr", "50760261919", env);
    expect(foto).toEqual({ bytes: BYTES, mime: "image/jpeg" });
    expect(peticiones[0]).toMatchObject({ metodo: "POST", url: "https://puente/api/foto-perfil", cuerpo: { para: "50760261919" } });
    expect(peticiones[0].cabeceras["x-wa-token-b64"]).toBe(tokenParaCabecera(WA_TOKEN));
  });

  it("sin foto (404) es null; cualquier otro fallo del puente lanza para que el motor lo anote", async () => {
    expect(await adaptador.fotoDePerfil!("whatsapp_qr", "50760261919", puenteFalso(() => Response.json({ ok: false }, { status: 404 })).env)).toBeNull();
    await expect(adaptador.fotoDePerfil!("whatsapp_qr", "50760261919", puenteFalso(() => Response.json({}, { status: 502 })).env)).rejects.toThrow(/502/);
  });

  it("respuestas raras (sin base64, base64 inválido, demasiado grande): null", async () => {
    for (const cuerpo of [{ ok: true }, { ok: true, base64: "%%%no-es-base64" }, { ok: false, base64 }, { ok: true, base64: "A".repeat(500_000) }]) {
      expect(await adaptador.fotoDePerfil!("whatsapp_qr", "50760261919", puenteFalso(() => Response.json(cuerpo)).env)).toBeNull();
    }
  });

  it("grupos, estados y canales no se consultan", async () => {
    const { env, peticiones } = puenteFalso();
    for (const jid of ["120363025246125486@g.us", "status@broadcast", "1203@newsletter"]) {
      expect(await adaptador.fotoDePerfil!("whatsapp_qr", jid, env)).toBeNull();
    }
    expect(peticiones).toHaveLength(0);
  });
});
