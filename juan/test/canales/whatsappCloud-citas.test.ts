/**
 * WhatsApp Cloud: citas, reenviados, reacciones y palomitas (pedido de la dueña, 2026-11-07: «si un cliente dice "este",
 * seleccionando un mensaje… solamente vemos la palabra "este"»; «no vemos si se entregó, no vemos el estado del mensaje»).
 * Los cuerpos son los que manda Meta (forma de la documentación de la Cloud API), con números y nombres de mentira.
 */
import { describe, expect, it } from "vitest";
import type { Env } from "../../src/env";
import { EnvioParcialError } from "../../src/canales/tipos";
import { crearWhatsappCloud, motivoDeMeta } from "../../src/canales/whatsappCloud";
import { hmacHex } from "../../src/seguridad";

const SECRETO = "secreto-de-la-app-0123456789abcdef";
const NUMERO = "109876543210";
const CLIENTE = "50760001111";
const TIENDA = "50760261919";
const env = { META_APP_SECRET: SECRETO, META_VERIFY_TOKEN: "verificacion-0123456789", WHATSAPP_CLOUD_TOKEN: "token-cloud-0123456789", WHATSAPP_PHONE_NUMBER_ID: NUMERO } as unknown as Env;

interface Llamada {
  url: string;
  cuerpo: any;
}

function nubeFalsa(responder: (c: Llamada, n: number) => Response = (_c, n) => Response.json({ messages: [{ id: `wamid.OUT${n}` }] })) {
  const llamadas: Llamada[] = [];
  const f: typeof fetch = async (recurso, init) => {
    const c = { url: String(recurso), cuerpo: init?.body ? JSON.parse(String(init.body)) : null };
    llamadas.push(c);
    return responder(c, llamadas.length - 1);
  };
  return { llamadas, adaptador: crearWhatsappCloud({ fetch: f, dormir: async () => {} }) };
}

async function firmado(cuerpo: object) {
  const crudo = JSON.stringify(cuerpo);
  return new Request("https://juan.example/webhooks/whatsapp-cloud", { method: "POST", headers: { "x-hub-signature-256": `sha256=${await hmacHex(SECRETO, crudo)}` }, body: crudo });
}

const aviso = (value: object) => ({
  object: "whatsapp_business_account",
  entry: [{ id: "WABA", changes: [{ field: "messages", value: { messaging_product: "whatsapp", metadata: { display_phone_number: TIENDA, phone_number_id: NUMERO }, ...value } }] }],
});
const contactos = [{ profile: { name: "Cliente de Prueba" }, wa_id: CLIENTE }];

describe("citas y reenviados (messages[].context)", () => {
  const { adaptador } = nubeFalsa();

  it("el cliente responde a un mensaje NUESTRO: viaja el id del citado y que lo mandó la tienda", async () => {
    const r = await adaptador.recibir(
      await firmado(
        aviso({
          contacts: contactos,
          messages: [{ context: { from: TIENDA, id: "wamid.NUESTRO1" }, from: CLIENTE, id: "wamid.ESTE", timestamp: "1790000000", type: "text", text: { body: "este" } }],
        }),
      ),
      env,
    );
    expect(r.entrantes).toHaveLength(1);
    expect(r.entrantes[0]).toMatchObject({ id_mensaje: "wamid.ESTE", texto: "este", cita: { id: "wamid.NUESTRO1", deLaTienda: true } });
    expect(r.entrantes[0].reenviado).toBeUndefined();
    expect(r.eventos).toBeUndefined();
  });

  it("el cliente cita un mensaje SUYO (una foto que mandó antes)", async () => {
    const r = await adaptador.recibir(
      await firmado(aviso({ contacts: contactos, messages: [{ context: { from: CLIENTE, id: "wamid.SUFOTO" }, from: CLIENTE, id: "wamid.2", timestamp: "1790000001", type: "text", text: { body: "¿tienen esta en gris?" } }] })),
      env,
    );
    expect(r.entrantes[0].cita).toEqual({ id: "wamid.SUFOTO", deLaTienda: false });
  });

  it("reenviado y reenviado muchas veces (forwarded / frequently_forwarded)", async () => {
    const r = await adaptador.recibir(
      await firmado(
        aviso({
          contacts: contactos,
          messages: [
            { context: { forwarded: true }, from: CLIENTE, id: "wamid.R1", timestamp: "1790000002", type: "text", text: { body: "Mira esta cama" } },
            { context: { frequently_forwarded: true, forwarded: true }, from: CLIENTE, id: "wamid.R2", timestamp: "1790000003", type: "image", image: { id: "MEDIA9", mime_type: "image/jpeg" } },
          ],
        }),
      ),
      env,
    );
    expect(r.entrantes.map((e) => e.reenviado)).toEqual(["una", "muchas"]);
    expect(r.entrantes.every((e) => e.cita === undefined)).toBe(true);
  });

  it("un eco de la app del teléfono nunca lleva cita ni reenviado del cliente", async () => {
    const r = await adaptador.recibir(
      await firmado(aviso({ message_echoes: [{ context: { from: CLIENTE, id: "wamid.X" }, from: TIENDA, to: CLIENTE, id: "wamid.ECO", timestamp: "1790000004", type: "text", text: { body: "Sí la tenemos" } }] })),
      env,
    );
    expect(r.entrantes[0]).toMatchObject({ propio: true, id_externo: CLIENTE });
    expect(r.entrantes[0].cita).toBeUndefined();
  });
});

describe("reacciones: eventos, nunca mensajes", () => {
  const { adaptador } = nubeFalsa();

  it("poner y quitar una reacción (sin emoji = la quitó); ninguna es un mensaje del cliente", async () => {
    const r = await adaptador.recibir(
      await firmado(
        aviso({
          contacts: contactos,
          messages: [
            { from: CLIENTE, id: "wamid.RX1", timestamp: "1790000010", type: "reaction", reaction: { message_id: "wamid.NUESTRO1", emoji: "👍" } },
            { from: CLIENTE, id: "wamid.RX2", timestamp: "1790000020", type: "reaction", reaction: { message_id: "wamid.NUESTRO1" } },
          ],
        }),
      ),
      env,
    );
    expect(r.entrantes).toEqual([]);
    expect(r.eventos).toEqual([
      { tipo: "reaccion", canal: "whatsapp_cloud", id_externo: CLIENTE, id_mensaje: "wamid.NUESTRO1", emoji: "👍", ts: 1_790_000_010_000 },
      { tipo: "reaccion", canal: "whatsapp_cloud", id_externo: CLIENTE, id_mensaje: "wamid.NUESTRO1", emoji: "", ts: 1_790_000_020_000 },
    ]);
  });

  it("la reacción que la tienda deja desde el teléfono (eco) se ignora", async () => {
    const r = await adaptador.recibir(
      await firmado(aviso({ message_echoes: [{ from: TIENDA, to: CLIENTE, id: "wamid.RE", timestamp: "1790000030", type: "reaction", reaction: { message_id: "wamid.C1", emoji: "❤️" } }] })),
      env,
    );
    expect(r.entrantes).toEqual([]);
    expect(r.eventos).toBeUndefined();
  });
});

describe("recibos (statuses): las palomitas", () => {
  const { adaptador } = nubeFalsa();

  it("sent, delivered y read de un mensaje nuestro: eventos con el cliente como destinatario", async () => {
    const r = await adaptador.recibir(
      await firmado(
        aviso({
          statuses: [
            { id: "wamid.OUT0", status: "sent", timestamp: "1790000100", recipient_id: CLIENTE, conversation: { id: "CONV", origin: { type: "service" } }, pricing: { billable: false, category: "service" } },
            { id: "wamid.OUT0", status: "delivered", timestamp: "1790000101", recipient_id: CLIENTE },
            { id: "wamid.OUT0", status: "read", timestamp: "1790000160", recipient_id: CLIENTE },
          ],
        }),
      ),
      env,
    );
    expect(r.respuesta.status).toBe(200);
    expect(r.entrantes).toEqual([]);
    expect(r.eventos?.map((e) => (e.tipo === "estado" ? [e.estado, e.id_externo, e.ts] : null))).toEqual([
      ["enviado", CLIENTE, 1_790_000_100_000],
      ["entregado", CLIENTE, 1_790_000_101_000],
      ["leido", CLIENTE, 1_790_000_160_000],
    ]);
  });

  it("failed lleva el motivo: los conocidos en palabras de la tienda, los demás con el texto y el código de Meta", async () => {
    const r = await adaptador.recibir(
      await firmado(
        aviso({
          statuses: [
            { id: "wamid.OUT1", status: "failed", timestamp: "1790000200", recipient_id: CLIENTE, errors: [{ code: 131047, title: "Re-engagement message", message: "Re-engagement message", error_data: { details: "Message failed to send because more than 24 hours have passed since the customer last replied to this number." } }] },
            { id: "wamid.OUT2", status: "failed", timestamp: "1790000201", recipient_id: CLIENTE, errors: [{ code: 131000, title: "Something went wrong" }] },
          ],
        }),
      ),
      env,
    );
    const [a, b] = r.eventos ?? [];
    expect(a).toMatchObject({ tipo: "estado", estado: "fallido", id_mensaje: "wamid.OUT1" });
    expect(a.tipo === "estado" && a.error).toMatch(/24 horas.*plantilla/);
    expect(b.tipo === "estado" && b.error).toBe("Something went wrong (código 131000)");
  });

  it("estados desconocidos (deleted, warning) o sin destinatario se ignoran sin romper", async () => {
    const r = await adaptador.recibir(
      await firmado(aviso({ statuses: [{ id: "wamid.Z", status: "deleted", recipient_id: CLIENTE }, { id: "wamid.Z", status: "warning", recipient_id: CLIENTE }, { id: "wamid.Z", status: "read" }] })),
      env,
    );
    expect(r.respuesta.status).toBe(200);
    expect(r.eventos).toBeUndefined();
  });

  it("un mismo aviso con un mensaje del cliente y palomitas: el mensaje se guarda antes del 200 y las palomitas van aparte", async () => {
    const r = await adaptador.recibir(
      await firmado(
        aviso({
          contacts: contactos,
          messages: [{ from: CLIENTE, id: "wamid.M", timestamp: "1790000300", type: "text", text: { body: "ok gracias" } }],
          statuses: [{ id: "wamid.OUT3", status: "read", timestamp: "1790000299", recipient_id: CLIENTE }],
        }),
      ),
      env,
    );
    expect(r.guardarAntes).toBe(true);
    expect(r.entrantes.map((e) => e.id_mensaje)).toEqual(["wamid.M"]);
    expect(r.eventos).toHaveLength(1);
  });

  it("un id que no es texto (reacción o recibo mal formado) se ignora sin romper el aviso", async () => {
    const r = await adaptador.recibir(
      await firmado(
        aviso({
          contacts: contactos,
          messages: [{ from: CLIENTE, id: "wamid.RX", timestamp: "1790000400", type: "reaction", reaction: { message_id: 12345, emoji: "👍" } }],
          statuses: [
            { id: { raro: true }, status: "read", timestamp: "1790000401", recipient_id: CLIENTE },
            { id: "wamid.BIEN", status: "read", timestamp: "1790000402", recipient_id: CLIENTE },
          ],
        }),
      ),
      env,
    );
    expect(r.respuesta.status).toBe(200);
    expect(r.eventos?.map((e) => e.id_mensaje)).toEqual(["wamid.BIEN"]);
  });

  it("motivoDeMeta: sin errores no hay motivo", () => {
    expect(motivoDeMeta({ id: "x", status: "failed" })).toBeUndefined();
  });
});

describe("«Responder» desde Odoo: la cita sale con el primer mensaje", () => {
  it("context.message_id solo en el primer mensaje (texto y luego foto)", async () => {
    const { adaptador, llamadas } = nubeFalsa();
    const r = await adaptador.enviar(
      "whatsapp_cloud",
      { para: CLIENTE, burbujas: ["Sí, esa es la Cama Queen Milán", "¿Te la aparto con una vendedora?"], medios: [{ tipo: "imagen", url: "https://dcasapty.com/a.jpg" }], responderA: "wamid.ESTE" },
      env,
    );
    expect(llamadas.map((l) => l.cuerpo.context)).toEqual([{ message_id: "wamid.ESTE" }, undefined, undefined]);
    expect(r.ids).toEqual(["wamid.OUT0", "wamid.OUT1", "wamid.OUT2"]);
  });

  it("si Meta rechaza la cita (4xx), sale igual sin ella; un 5xx no se maquilla", async () => {
    const rechazo = nubeFalsa((c, n) => (c.cuerpo.context ? Response.json({ error: { message: "Invalid parameter", code: 100 } }, { status: 400 }) : Response.json({ messages: [{ id: `wamid.OK${n}` }] })));
    const r = await rechazo.adaptador.enviar("whatsapp_cloud", { para: CLIENTE, burbujas: ["Claro"], medios: [], responderA: "wamid.VIEJO" }, env);
    expect(r.ids).toEqual(["wamid.OK1"]);
    expect(rechazo.llamadas.map((l) => !!l.cuerpo.context)).toEqual([true, false]);

    const caida = nubeFalsa(() => new Response("no", { status: 503 }));
    await expect(caida.adaptador.enviar("whatsapp_cloud", { para: CLIENTE, burbujas: ["Claro"], medios: [], responderA: "wamid.VIEJO" }, env)).rejects.toThrow(/503/);
    expect(caida.llamadas).toHaveLength(1);
  });

  it("solo un 400 con código 100 o 131009 (parámetro inválido) reenvía sin cita: un 408, un 401 u otro 400 no (podría duplicar)", async () => {
    for (const [estado, codigo] of [
      [408, 100],
      [401, 190],
      [400, 131047],
    ] as const) {
      const nube = nubeFalsa(() => Response.json({ error: { message: "rechazo", code: codigo } }, { status: estado }));
      await expect(nube.adaptador.enviar("whatsapp_cloud", { para: CLIENTE, burbujas: ["Claro"], medios: [], responderA: "wamid.VIEJO" }, env)).rejects.toThrow(new RegExp(String(estado)));
      expect(nube.llamadas).toHaveLength(1);
    }
    const r131009 = nubeFalsa((c, n) => (c.cuerpo.context ? Response.json({ error: { message: "Parameter value is not valid", code: 131009 } }, { status: 400 }) : Response.json({ messages: [{ id: `wamid.OK${n}` }] })));
    const r = await r131009.adaptador.enviar("whatsapp_cloud", { para: CLIENTE, burbujas: ["Claro"], medios: [], responderA: "wamid.VIEJO" }, env);
    expect(r.ids).toEqual(["wamid.OK1"]);
  });

  it("si se cae a la mitad, dice cuánto salió (y con qué ids): quien reintenta no repite la primera burbuja", async () => {
    const { adaptador } = nubeFalsa((_c, n) => (n === 1 ? Response.json({ error: { message: "Service unavailable", code: 2 } }, { status: 503 }) : Response.json({ messages: [{ id: `wamid.P${n}` }] })));
    const e = await adaptador.enviar("whatsapp_cloud", { para: CLIENTE, burbujas: ["uno", "dos", "tres"], medios: [] }, env).catch((x) => x);
    expect(e).toBeInstanceOf(EnvioParcialError);
    expect((e as EnvioParcialError).enviado).toEqual({ burbujas: 1, medios: 0, ids: ["wamid.P0"] });
  });
});
