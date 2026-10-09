/**
 * WhatsApp Cloud API: adaptador COMPLETO pero APAGADO por configuración (plan B si bloquean el número del QR).
 * Lo de los ecos (`message_echoes`) NO está verificado contra la documentación de Meta: estas pruebas fijan la forma que se asumió.
 */
import { describe, expect, it } from "vitest";
import type { Env } from "../../src/env";
import { crearWhatsappCloud } from "../../src/canales/whatsappCloud";
import { adaptadorDe, adaptadorPorRuta, crearAdaptadores } from "../../src/canales/index";
import { hmacHex } from "../../src/seguridad";

const SECRETO = "secreto-de-la-app-0123456789abcdef";
const VERIFICACION = "verificacion-de-prueba-0123456789";
const TOKEN = "token-cloud-0123456789";
const NUMERO = "109876543210";

const env = { META_APP_SECRET: SECRETO, META_VERIFY_TOKEN: VERIFICACION, WHATSAPP_CLOUD_TOKEN: TOKEN, WHATSAPP_PHONE_NUMBER_ID: NUMERO } as unknown as Env;

interface Llamada {
  url: string;
  metodo: string;
  cabeceras: Record<string, string>;
  cuerpo: any;
}

function nubeFalsa(responder: (c: Llamada, n: number) => Response = (_c, n) => Response.json({ messages: [{ id: `wamid.OUT${n}` }] })) {
  const llamadas: Llamada[] = [];
  const f: typeof fetch = async (recurso, init) => {
    const c = {
      url: String(recurso),
      metodo: init?.method ?? "GET",
      cabeceras: Object.fromEntries(Object.entries((init?.headers ?? {}) as Record<string, string>).map(([k, v]) => [k.toLowerCase(), v])),
      cuerpo: init?.body ? JSON.parse(String(init.body)) : null,
    };
    llamadas.push(c);
    return responder(c, llamadas.length - 1);
  };
  return { llamadas, adaptador: crearWhatsappCloud({ fetch: f, dormir: async () => {} }) };
}

async function firmado(cuerpo: object) {
  const crudo = JSON.stringify(cuerpo);
  return new Request("https://juan.example/webhooks/whatsapp-cloud", {
    method: "POST",
    headers: { "x-hub-signature-256": `sha256=${await hmacHex(SECRETO, crudo)}` },
    body: crudo,
  });
}

const cambio = (value: object) => ({ object: "whatsapp_business_account", entry: [{ id: "WABA", changes: [{ field: "messages", value }] }] });
const contactos = [{ profile: { name: "Karen" }, wa_id: "50760261919" }];

describe("la verificación y la firma", () => {
  const { adaptador } = nubeFalsa();

  it("GET con el token correcto devuelve el reto; con otro, 403", async () => {
    const ok = await adaptador.recibir(new Request(`https://x/webhooks/whatsapp-cloud?hub.mode=subscribe&hub.verify_token=${VERIFICACION}&hub.challenge=777`), env);
    expect(await ok.respuesta.text()).toBe("777");
    const mal = await adaptador.recibir(new Request("https://x/webhooks/whatsapp-cloud?hub.mode=subscribe&hub.verify_token=otro&hub.challenge=777"), env);
    expect(mal.respuesta.status).toBe(403);
  });

  it("POST sin firma, con firma mala o sin secreto: 401", async () => {
    const cuerpo = JSON.stringify(cambio({ messages: [] }));
    for (const cab of [{} as Record<string, string>, { "x-hub-signature-256": `sha256=${"a".repeat(64)}` }]) {
      expect((await adaptador.recibir(new Request("https://x/w", { method: "POST", headers: cab, body: cuerpo }), env)).respuesta.status).toBe(401);
    }
    expect((await adaptador.recibir(await firmado(cambio({ messages: [] })), {} as Env)).respuesta.status).toBe(401);
  });
});

describe("los mensajes del cliente", () => {
  const { adaptador } = nubeFalsa();

  it("texto: el celular es la llave y el nombre sale del contacto", async () => {
    const r = await adaptador.recibir(
      await firmado(cambio({ contacts: contactos, messages: [{ from: "50760261919", id: "wamid.A", timestamp: "1790000000", type: "text", text: { body: "Hola, ¿tienen camas?" } }] })),
      env,
    );
    expect(r.entrantes).toEqual([
      { canal: "whatsapp_cloud", id_externo: "50760261919", id_mensaje: "wamid.A", nombre: "Karen", celular: "50760261919", texto: "Hola, ¿tienen camas?", adjuntos: [], ts: 1_790_000_000_000, propio: false },
    ]);
  });

  it("botones y listas interactivas llegan como el texto que el cliente tocó", async () => {
    const r = await adaptador.recibir(
      await firmado(
        cambio({
          messages: [
            { from: "507", id: "wamid.B", type: "button", button: { text: "Ver catálogo" } },
            { from: "507", id: "wamid.C", type: "interactive", interactive: { button_reply: { title: "Sí" } } },
            { from: "507", id: "wamid.D", type: "interactive", interactive: { list_reply: { title: "Dormitorios" } } },
          ],
        }),
      ),
      env,
    );
    expect(r.entrantes.map((e) => e.texto)).toEqual(["Ver catálogo", "Sí", "Dormitorios"]);
  });

  it("imagen con pie de foto: el pie es el texto y el archivo un adjunto que se descarga con Bearer", async () => {
    const { llamadas, adaptador: a } = nubeFalsa((c) =>
      c.url.includes("/MEDIA1") ? Response.json({ url: "https://lookaside.fbsbx.com/x", mime_type: "image/jpeg" }) : new Response(new Uint8Array([9, 8, 7])),
    );
    const r = await a.recibir(await firmado(cambio({ messages: [{ from: "50760261919", id: "wamid.E", type: "image", image: { id: "MEDIA1", caption: "así la quiero", mime_type: "image/jpeg" } }] })), env);
    const [e] = r.entrantes;
    expect(e.texto).toBe("así la quiero");
    expect(e.adjuntos[0]).toMatchObject({ tipo: "imagen", mime: "image/jpeg" });
    // Nada se descarga hasta que el motor lo pide, y lo que viaja hacia el motor no lleva el token.
    expect(llamadas).toHaveLength(0);
    expect(JSON.stringify({ ...e, adjuntos: e.adjuntos.map((x) => ({ ...x, obtener: undefined })) })).not.toContain(TOKEN);
    const bajado = await e.adjuntos[0].obtener!();
    expect([...bajado!.bytes]).toEqual([9, 8, 7]);
    expect(llamadas.map((l) => l.cabeceras.authorization)).toEqual([`Bearer ${TOKEN}`, `Bearer ${TOKEN}`]);
  });

  it("si Meta no entrega el archivo, `obtener` devuelve null sin romper", async () => {
    const { adaptador: a } = nubeFalsa(() => new Response("no", { status: 404 }));
    const r = await a.recibir(await firmado(cambio({ messages: [{ from: "507", id: "wamid.F", type: "audio", audio: { id: "M" } }] })), env);
    expect(await r.entrantes[0].adjuntos[0].obtener!()).toBeNull();
  });

  it("documento, video, ubicación y sticker; las reacciones se ignoran", async () => {
    const r = await adaptador.recibir(
      await firmado(
        cambio({
          messages: [
            { from: "507", id: "1", type: "document", document: { id: "D", filename: "comprobante.pdf", caption: "mi pago" } },
            { from: "507", id: "2", type: "video", video: { id: "V" } },
            { from: "507", id: "3", type: "location" },
            { from: "507", id: "4", type: "sticker" },
            { from: "507", id: "5", type: "reaction" },
          ],
        }),
      ),
      env,
    );
    expect(r.entrantes.map((e) => e.id_mensaje)).toEqual(["1", "2", "3", "4"]);
    expect(r.entrantes[0].adjuntos[0]).toMatchObject({ tipo: "documento", nombre: "comprobante.pdf" });
    expect(r.entrantes[1].adjuntos[0].tipo).toBe("video");
    expect(r.entrantes[2].texto).toMatch(/ubicaci/);
  });

  it("los recibos de entrega y lectura (`statuses`) se ignoran", async () => {
    const r = await adaptador.recibir(await firmado(cambio({ statuses: [{ id: "wamid.X", status: "delivered", recipient_id: "507" }] })), env);
    expect(r.respuesta.status).toBe(200);
    expect(r.entrantes).toEqual([]);
  });
});

describe("lo que escribe la vendedora desde la app (coexistencia)", () => {
  it("un eco es `propio` y el cliente es el DESTINATARIO", async () => {
    const { adaptador } = nubeFalsa();
    const r = await adaptador.recibir(
      await firmado(cambio({ message_echoes: [{ from: "50761112222", to: "50760261919", id: "wamid.ECO", timestamp: "1790000100", type: "text", text: { body: "Hola, soy Marisol" } }] })),
      env,
    );
    expect(r.entrantes[0]).toMatchObject({ propio: true, id_externo: "50760261919", texto: "Hola, soy Marisol", id_mensaje: "wamid.ECO" });
  });
});

describe("el envío", () => {
  it("texto: POST a <phone_number_id>/messages con Bearer y messaging_product", async () => {
    const { llamadas, adaptador } = nubeFalsa();
    const r = await adaptador.enviar("whatsapp_cloud", { para: "50760261919", burbujas: ["Hola.", "¿Qué buscas?"], medios: [] }, env);
    expect(llamadas[0].url).toMatch(new RegExp(`^https://graph\\.facebook\\.com/v\\d+\\.\\d+/${NUMERO}/messages$`));
    expect(llamadas[0].cabeceras.authorization).toBe(`Bearer ${TOKEN}`);
    expect(llamadas[0].cuerpo).toEqual({ messaging_product: "whatsapp", recipient_type: "individual", to: "50760261919", type: "text", text: { preview_url: false, body: "Hola." } });
    expect(llamadas).toHaveLength(2);
    expect(r.ids).toEqual(["wamid.OUT0", "wamid.OUT1"]);
    expect(llamadas[0].url).not.toContain(TOKEN);
  });

  it("imágenes y documentos salen por enlace, con pie y nombre de archivo", async () => {
    const { llamadas, adaptador } = nubeFalsa();
    await adaptador.enviar(
      "whatsapp_cloud",
      {
        para: "507",
        burbujas: [],
        medios: [
          { tipo: "imagen", url: "https://sitio/foto.jpg", pie: "Cama Roma" },
          { tipo: "documento", url: "https://sitio/ficha.pdf", nombre: "ficha.pdf" },
        ],
      },
      env,
    );
    expect(llamadas[0].cuerpo).toMatchObject({ type: "image", image: { link: "https://sitio/foto.jpg", caption: "Cama Roma" } });
    expect(llamadas[1].cuerpo).toMatchObject({ type: "document", document: { link: "https://sitio/ficha.pdf", filename: "ficha.pdf" } });
  });

  it("fuera de las 24 h Meta pide una plantilla: el motivo sale en el error, sin el token", async () => {
    const { adaptador } = nubeFalsa(() => Response.json({ error: { message: "Re-engagement message", code: 131047 } }, { status: 400 }));
    const err = (await adaptador.enviar("whatsapp_cloud", { para: "507", burbujas: ["Hola"], medios: [] }, env).catch((e: Error) => e)) as Error;
    expect(err.message).toMatch(/Re-engagement/);
    expect(err.message).toMatch(/131047/);
    expect(err.message).not.toContain(TOKEN);
  });

  it("sin token o sin número no hace ninguna llamada", async () => {
    const { llamadas, adaptador } = nubeFalsa();
    const salida = { para: "507", burbujas: ["Hola"], medios: [] };
    await expect(adaptador.enviar("whatsapp_cloud", salida, { ...env, WHATSAPP_CLOUD_TOKEN: "" } as Env)).rejects.toThrow(/WHATSAPP_CLOUD_TOKEN/);
    await expect(adaptador.enviar("whatsapp_cloud", salida, { ...env, WHATSAPP_PHONE_NUMBER_ID: "" } as Env)).rejects.toThrow(/WHATSAPP_PHONE_NUMBER_ID/);
    expect(llamadas).toHaveLength(0);
  });
});

describe("capacidades, faltantes y registro", () => {
  const { adaptador } = nubeFalsa();

  it("exige la ventana de 24 h y admite imágenes y documentos", () => {
    expect(adaptador.capacidades("whatsapp_cloud")).toMatchObject({ imagenes: true, documentos: true, ventana24h: true });
  });

  it("faltantes: solo nombres, y el número es una VARIABLE (no secreto) que también cuenta", () => {
    expect(adaptador.faltantes({} as Env, "whatsapp_cloud")).toEqual(["WHATSAPP_CLOUD_TOKEN", "WHATSAPP_PHONE_NUMBER_ID", "META_APP_SECRET", "META_VERIFY_TOKEN"]);
    expect(adaptador.faltantes(env, "whatsapp_cloud")).toEqual([]);
  });

  it("está en el registro, con su propia ruta, aparte de Messenger e Instagram", () => {
    const lista = crearAdaptadores();
    expect(adaptadorPorRuta("/webhooks/whatsapp-cloud", lista)?.canales).toEqual(["whatsapp_cloud"]);
    expect(adaptadorDe("whatsapp_cloud", lista)).not.toBe(adaptadorDe("messenger", lista));
    expect(lista.map((a) => a.ruta).sort()).toEqual(["/webhooks/meta", "/webhooks/telegram", "/webhooks/whatsapp-cloud", "/webhooks/whatsapp-qr"]);
    // Dos adaptadores nunca comparten ruta: el router no sabría a cuál mandar.
    expect(new Set(lista.map((a) => a.ruta)).size).toBe(lista.length);
  });
});
