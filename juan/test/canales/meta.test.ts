/**
 * Messenger e Instagram (Meta oficial): verificación GET, firma X-Hub-Signature-256, ecos de la Página, envío por la Send API.
 * Reescritura de test/channels/meta.test.ts del CRM de Baby Caleb (sin ManyChat).
 */
import { describe, expect, it } from "vitest";
import type { Env } from "../../src/env";
import { crearMeta, eventosDeMeta, MAX_ADJUNTO_MESSENGER_BYTES, MAX_FOTO_INSTAGRAM_BYTES } from "../../src/canales/meta";
import { adaptadorDe, adaptadorPorRuta, crearAdaptadores } from "../../src/canales/index";
import { hmacHex } from "../../src/seguridad";
import { EnvioParcialError } from "../../src/canales/tipos";

const SECRETO = "secreto-de-la-app-0123456789abcdef";
const VERIFICACION = "verificacion-de-prueba-0123456789";
const TOKEN_PAGINA = "token-de-la-pagina-0123456789";

const env = { META_APP_SECRET: SECRETO, META_VERIFY_TOKEN: VERIFICACION, META_PAGE_TOKEN: TOKEN_PAGINA } as unknown as Env;

interface Llamada {
  url: string;
  cabeceras: Record<string, string>;
  cuerpo: any;
}

/** Lo que sirve «nuestro sitio» (https://sitio/…): el archivo que Juan baja para subírselo a Messenger. */
const archivoDelSitio = (url: string) =>
  new Response(new Uint8Array([1, 2, 3, 4]), { headers: { "content-type": url.endsWith(".pdf") ? "application/pdf" : "image/jpeg" } });

/** Un cuerpo `FormData` como objeto: los campos JSON interpretados y el archivo como {nombre, tipo, bytes}. */
function deFormData(form: FormData): Record<string, any> {
  const o: Record<string, any> = {};
  for (const [k, v] of form.entries()) {
    if (typeof v !== "string") o[k] = { nombre: v.name, tipo: v.type, bytes: v.size };
    else {
      try {
        o[k] = JSON.parse(v);
      } catch {
        o[k] = v;
      }
    }
  }
  return o;
}

function graphFalso(
  respuesta: (c: Llamada, n: number) => Response = (_c, n) => Response.json({ recipient_id: "1", message_id: `m.${n}` }),
  sitio: (url: string) => Response = archivoDelSitio,
) {
  const llamadas: Llamada[] = [];
  const descargas: string[] = [];
  const f: typeof fetch = async (recurso, init) => {
    if (String(recurso).startsWith("https://sitio/")) {
      descargas.push(String(recurso));
      return sitio(String(recurso));
    }
    const c = {
      url: String(recurso),
      cabeceras: Object.fromEntries(Object.entries((init?.headers ?? {}) as Record<string, string>).map(([k, v]) => [k.toLowerCase(), v])),
      cuerpo: init?.body instanceof FormData ? deFormData(init.body) : init?.body ? JSON.parse(String(init.body)) : null,
    };
    llamadas.push(c);
    return respuesta(c, llamadas.length - 1);
  };
  return { llamadas, descargas, adaptador: crearMeta({ fetch: f, dormir: async () => {} }) };
}

async function firmado(cuerpo: object, secreto = SECRETO) {
  const crudo = JSON.stringify(cuerpo);
  return new Request("https://juan.example/webhooks/meta", {
    method: "POST",
    headers: { "content-type": "application/json", "x-hub-signature-256": `sha256=${await hmacHex(secreto, crudo)}` },
    body: crudo,
  });
}

const evento = (extra: object = {}) => ({
  object: "page",
  entry: [{ id: "PAGINA", messaging: [{ sender: { id: "PSID1" }, recipient: { id: "PAGINA" }, timestamp: 1_790_000_000_000, message: { mid: "m_abc", text: "Hola, ¿tienen sofás?" }, ...extra }] }],
});

describe("la verificación del webhook (GET)", () => {
  const { adaptador } = graphFalso();
  const verificar = (q: string, e: Env = env) => adaptador.recibir(new Request(`https://juan.example/webhooks/meta?${q}`), e);

  it("con el token correcto devuelve el reto tal cual", async () => {
    const r = await verificar(`hub.mode=subscribe&hub.verify_token=${VERIFICACION}&hub.challenge=12345`);
    expect(r.respuesta.status).toBe(200);
    expect(await r.respuesta.text()).toBe("12345");
  });

  it("con otro token, otro modo o sin token configurado: 403", async () => {
    expect((await verificar("hub.mode=subscribe&hub.verify_token=otro&hub.challenge=1")).respuesta.status).toBe(403);
    expect((await verificar(`hub.mode=unsubscribe&hub.verify_token=${VERIFICACION}&hub.challenge=1`)).respuesta.status).toBe(403);
    expect((await verificar("hub.mode=subscribe&hub.verify_token=&hub.challenge=1", {} as Env)).respuesta.status).toBe(403);
  });
});

describe("la firma del POST", () => {
  const { adaptador } = graphFalso();

  it("firma correcta: entrega el mensaje", async () => {
    const r = await adaptador.recibir(await firmado(evento()), env);
    expect(r.respuesta.status).toBe(200);
    expect(r.entrantes).toHaveLength(1);
  });

  it("firma incorrecta, ausente o de otro formato: 401 y no entra nada", async () => {
    const cuerpo = JSON.stringify(evento());
    const casos: (string | null)[] = [null, "", "sha256=", `sha256=${"0".repeat(64)}`, "sha1=abc", `sha256=${await hmacHex("otro-secreto", cuerpo)}`];
    for (const firma of casos) {
      const req = new Request("https://juan.example/webhooks/meta", { method: "POST", headers: firma === null ? {} : { "x-hub-signature-256": firma }, body: cuerpo });
      const r = await adaptador.recibir(req, env);
      expect(r.respuesta.status, String(firma)).toBe(401);
      expect(r.entrantes).toEqual([]);
    }
  });

  it("la firma vale para el cuerpo EXACTO: si cambia un byte, falla", async () => {
    const crudo = JSON.stringify(evento());
    const firma = `sha256=${await hmacHex(SECRETO, crudo)}`;
    const r = await adaptador.recibir(new Request("https://x/webhooks/meta", { method: "POST", headers: { "x-hub-signature-256": firma }, body: crudo.replace("sofás", "sofas") }), env);
    expect(r.respuesta.status).toBe(401);
  });

  it("sin META_APP_SECRET falla cerrado aunque la firma venga bien formada", async () => {
    const req = await firmado(evento());
    expect((await adaptador.recibir(req, {} as Env)).respuesta.status).toBe(401);
  });

  it("un cuerpo que no es JSON (pero bien firmado) se acepta sin romper", async () => {
    const crudo = "esto no es json";
    const req = new Request("https://x/webhooks/meta", { method: "POST", headers: { "x-hub-signature-256": `sha256=${await hmacHex(SECRETO, crudo)}` }, body: crudo });
    const r = await adaptador.recibir(req, env);
    expect(r.respuesta.status).toBe(200);
    expect(r.entrantes).toEqual([]);
  });

  it("otros métodos: 405", async () => {
    expect((await adaptador.recibir(new Request("https://x/webhooks/meta", { method: "PUT" }), env)).respuesta.status).toBe(405);
  });
});

describe("cómo se leen los eventos", () => {
  it("Messenger: el PSID es la llave", () => {
    const [e] = eventosDeMeta(evento(), 5);
    expect(e).toEqual({ canal: "messenger", id_externo: "PSID1", id_mensaje: "m_abc", texto: "Hola, ¿tienen sofás?", adjuntos: [], ts: 1_790_000_000_000, propio: false });
  });

  it("Instagram: object=instagram cambia el canal", () => {
    expect(eventosDeMeta({ ...evento(), object: "instagram" }, 5)[0].canal).toBe("instagram");
  });

  it("un eco (lo escribió la Página) es `propio` y el cliente es el DESTINATARIO", () => {
    const [e] = eventosDeMeta(evento({ sender: { id: "PAGINA" }, recipient: { id: "PSID1" }, message: { mid: "m_eco", text: "Te atiendo yo", is_echo: true } }), 5);
    expect(e.propio).toBe(true);
    expect(e.id_externo).toBe("PSID1");
    expect(e.texto).toBe("Te atiendo yo");
  });

  it("recibos de entrega, lecturas y postbacks (sin `message`) se ignoran", () => {
    expect(eventosDeMeta({ object: "page", entry: [{ messaging: [{ sender: { id: "1" }, delivery: {} } as any, { sender: { id: "1" }, read: {} } as any] }] }, 5)).toEqual([]);
  });

  it("imagen, audio, video y archivo llegan como adjuntos con la URL de Meta (sin token)", () => {
    const [e] = eventosDeMeta(
      evento({
        message: {
          mid: "m_adj",
          attachments: [
            { type: "image", payload: { url: "https://cdn.fbsbx.com/a.jpg" } },
            { type: "audio", payload: { url: "https://cdn.fbsbx.com/a.mp4" } },
            { type: "video", payload: { url: "https://cdn.fbsbx.com/v.mp4" } },
            { type: "file", payload: { url: "https://cdn.fbsbx.com/f.pdf" } },
          ],
        },
      }),
      5,
    );
    expect(e.texto).toBeUndefined();
    expect(e.adjuntos.map((a) => [a.tipo, a.url])).toEqual([
      ["imagen", "https://cdn.fbsbx.com/a.jpg"],
      ["audio", "https://cdn.fbsbx.com/a.mp4"],
      ["video", "https://cdn.fbsbx.com/v.mp4"],
      ["documento", "https://cdn.fbsbx.com/f.pdf"],
    ]);
  });

  it("ubicación y enlace compartido se vuelven una nota de texto; un mensaje vacío se descarta", () => {
    const loc = eventosDeMeta(evento({ message: { mid: "m1", attachments: [{ type: "location", payload: {} }] } }), 5);
    expect(loc[0].texto).toMatch(/ubicaci/);
    const enlace = eventosDeMeta(evento({ message: { mid: "m2", attachments: [{ type: "fallback", payload: {} }] } }), 5);
    expect(enlace[0].texto).toMatch(/enlace/);
    expect(eventosDeMeta(evento({ message: { mid: "m3", text: "   " } }), 5)).toEqual([]);
  });

  it("un POST con varios eventos entrega todos, en orden", () => {
    const cuerpo = {
      object: "page",
      entry: [
        { messaging: [{ sender: { id: "A" }, message: { mid: "1", text: "uno" } }, { sender: { id: "B" }, message: { mid: "2", text: "dos" } }] },
        { messaging: [{ sender: { id: "C" }, message: { mid: "3", text: "tres" } }] },
      ],
    };
    expect(eventosDeMeta(cuerpo, 5).map((e) => [e.id_externo, e.texto])).toEqual([["A", "uno"], ["B", "dos"], ["C", "tres"]]);
  });

  it("sin mid se inventa un id estable por cliente y hora (para no duplicar un reintento)", () => {
    const [e] = eventosDeMeta(evento({ message: { text: "hola" } }), 5);
    expect(e.id_mensaje).toBe("meta:PSID1:1790000000000");
  });
});

describe("el envío por la Send API", () => {
  it("texto: una llamada por burbuja, con messaging_type RESPONSE, el token de la Página en la cabecera y la versión de Graph", async () => {
    const { llamadas, adaptador } = graphFalso();
    const r = await adaptador.enviar("messenger", { para: "PSID1", burbujas: ["Hola.", "¿Qué buscas?"], medios: [] }, env);
    expect(llamadas).toHaveLength(2);
    expect(llamadas[0].url).toMatch(/^https:\/\/graph\.facebook\.com\/v\d+\.\d+\/me\/messages$/);
    expect(llamadas[0].cabeceras.authorization).toBe(`Bearer ${TOKEN_PAGINA}`);
    expect(llamadas[0].cuerpo).toEqual({ recipient: { id: "PSID1" }, messaging_type: "RESPONSE", message: { text: "Hola." } });
    expect(llamadas[1].cuerpo.message.text).toBe("¿Qué buscas?");
    expect(r.ids).toEqual(["m.0", "m.1"]);
  });

  it("quita los asteriscos de negrita (Messenger e Instagram no los entienden)", async () => {
    const { llamadas, adaptador } = graphFalso();
    await adaptador.enviar("messenger", { para: "PSID1", burbujas: ["Escríbeme *persona* y te atiende una vendedora."], medios: [] }, env);
    expect(llamadas[0].cuerpo.message.text).toBe("Escríbeme persona y te atiende una vendedora.");
  });

  it("el token NO viaja en la URL", async () => {
    const { llamadas, adaptador } = graphFalso();
    await adaptador.enviar("messenger", { para: "PSID1", burbujas: ["Hola"], medios: [] }, env);
    expect(llamadas[0].url).not.toContain(TOKEN_PAGINA);
  });

  it("GRAPH_API_VERSION pisa la versión por defecto (y una versión mal escrita se ignora)", async () => {
    const { llamadas, adaptador } = graphFalso();
    await adaptador.enviar("messenger", { para: "PSID1", burbujas: ["Hola"], medios: [] }, { ...env, GRAPH_API_VERSION: "v30.0" } as Env);
    expect(llamadas[0].url).toContain("/v30.0/");
    await adaptador.enviar("messenger", { para: "PSID1", burbujas: ["Hola"], medios: [] }, { ...env, GRAPH_API_VERSION: "malo" } as Env);
    expect(llamadas[1].url).not.toContain("/malo/");
  });

  it("Messenger SUBE las imágenes y documentos (filedata), después del texto: Meta ya no los baja de nuestro sitio", async () => {
    // 2026-11-09: con `payload.url` Meta respondía «(#100) Error al subir el producto»: el texto salía y la foto no.
    const { llamadas, descargas, adaptador } = graphFalso();
    const r = await adaptador.enviar(
      "messenger",
      { para: "PSID1", burbujas: ["Mira"], medios: [{ tipo: "imagen", url: "https://sitio/foto.jpg" }, { tipo: "documento", url: "https://sitio/ficha.pdf", nombre: "ficha.pdf" }] },
      env,
    );
    expect(llamadas.map((l) => l.cuerpo.message.text ?? l.cuerpo.message.attachment.type)).toEqual(["Mira", "image", "file"]);
    expect(descargas).toEqual(["https://sitio/foto.jpg", "https://sitio/ficha.pdf"]);
    const foto = llamadas[1];
    expect(foto.url).toMatch(/\/me\/messages$/);
    expect(foto.cabeceras.authorization).toBe(`Bearer ${TOKEN_PAGINA}`);
    expect(foto.cabeceras["content-type"]).toBeUndefined();   // lo pone FormData, con su «boundary»
    expect(foto.cuerpo.recipient).toEqual({ id: "PSID1" });
    expect(foto.cuerpo.messaging_type).toBe("RESPONSE");
    expect(foto.cuerpo.message.attachment.payload).toEqual({ is_reusable: false });   // sin url
    expect(foto.cuerpo.filedata).toEqual({ nombre: "foto.jpg", tipo: "image/jpeg", bytes: 4 });
    expect(llamadas[2].cuerpo.filedata).toEqual({ nombre: "ficha.pdf", tipo: "application/pdf", bytes: 4 });
    expect(JSON.stringify(llamadas)).not.toContain("https://sitio/");   // nuestra URL firmada no le llega a Meta
    expect(r.ids).toEqual(["m.0", "m.1", "m.2"]);
  });

  it("Messenger: si Juan no logra bajar el archivo (error, 404 o vacío), lo manda por URL como antes: nunca peor", async () => {
    const respuestas: Array<() => Response> = [
      () => new Response("No existe.", { status: 404 }),
      () => new Response(new Uint8Array(0), { headers: { "content-type": "image/jpeg" } }),
      () => {
        throw new TypeError("network");
      },
    ];
    for (const sitio of respuestas) {
      const { llamadas, adaptador } = graphFalso(undefined, sitio);
      const r = await adaptador.enviar("messenger", { para: "PSID1", burbujas: ["Mira"], medios: [{ tipo: "imagen", url: "https://sitio/foto.jpg" }] }, env);
      expect(llamadas).toHaveLength(2);
      expect(llamadas[1].cuerpo.message.attachment.payload).toEqual({ url: "https://sitio/foto.jpg", is_reusable: true });
      expect(r.ids).toEqual(["m.0", "m.1"]);
    }
  });

  it("Messenger: un archivo de más de 25 MB no se sube ni se manda (y avisa qué SÍ salió)", async () => {
    const grande = graphFalso(undefined, () => new Response(new Uint8Array(MAX_ADJUNTO_MESSENGER_BYTES + 1), { headers: { "content-type": "image/jpeg" } }));
    const e = await grande.adaptador.enviar("messenger", { para: "PSID1", burbujas: ["Mira"], medios: [{ tipo: "imagen", url: "https://sitio/foto.jpg" }] }, env).catch((x) => x);
    expect(e).toBeInstanceOf(EnvioParcialError);
    expect(e.message).toMatch(/25 MB/);
    expect(e.enviado).toEqual({ burbujas: 1, medios: 0, ids: ["m.0"] });
    expect(grande.llamadas).toHaveLength(1);
  });

  /** Graph que acepta la subida de Instagram (`me/message_attachments`) y devuelve un attachment_id. */
  const conSubida = (c: Llamada, n: number) =>
    c.url.endsWith("/me/message_attachments") ? Response.json({ attachment_id: "att.IG1" }) : Response.json({ recipient_id: "1", message_id: `m.${n}` });
  const rechazo = (mensaje: string) => Response.json({ error: { message: mensaje, code: 100 } }, { status: 400 });
  /** Meta rechaza el envío CON archivo subido (multipart) y acepta lo demás. */
  const sinSubidaEnElEnvio = (c: Llamada, n: number) => (c.url.endsWith("/me/messages") && c.cuerpo?.filedata ? rechazo("Error al subir el producto") : conSubida(c, n));
  const foto = [{ tipo: "imagen" as const, url: "https://sitio/foto.jpg" }];

  it("Instagram SUBE la foto en el mismo envío, como Messenger (me/messages con filedata); el documento se omite", async () => {
    // 2026-11-10: con `payload.url` el texto salía y la foto no (igual que Messenger el 9 nov).
    const { llamadas, descargas, adaptador } = graphFalso(conSubida);
    const r = await adaptador.enviar("instagram", { para: "IGSID", burbujas: ["Mira"], medios: [...foto, { tipo: "documento", url: "https://sitio/ficha.pdf" }] }, env);
    expect(descargas).toEqual(["https://sitio/foto.jpg"]); // el documento ni se baja
    expect(llamadas).toHaveLength(2);
    const envio = llamadas[1];
    expect(envio.url).toMatch(/^https:\/\/graph\.facebook\.com\/v\d+\.\d+\/me\/messages$/);
    expect(envio.cabeceras.authorization).toBe(`Bearer ${TOKEN_PAGINA}`);
    expect(envio.cabeceras["content-type"]).toBeUndefined(); // lo pone FormData
    expect(envio.cuerpo.recipient).toEqual({ id: "IGSID" });
    expect(envio.cuerpo.message).toEqual({ attachment: { type: "image", payload: { is_reusable: false } } });
    expect(envio.cuerpo.filedata).toEqual({ nombre: "foto.jpg", tipo: "image/jpeg", bytes: 4 });
    expect(JSON.stringify(llamadas)).not.toContain("https://sitio/"); // nuestra URL firmada no le llega a Meta
    expect(r.ids).toEqual(["m.0", "m.1"]);
    expect(adaptador.capacidades("instagram").documentos).toBe(false);
    expect(adaptador.capacidades("messenger").documentos).toBe(true);
  });

  it("Instagram: si Meta no acepta el archivo en el envío, lo sube aparte (message_attachments, platform=instagram) y manda el attachment_id", async () => {
    const { llamadas, adaptador } = graphFalso(sinSubidaEnElEnvio);
    const r = await adaptador.enviar("instagram", { para: "IGSID", burbujas: [], medios: foto }, env);
    expect(llamadas).toHaveLength(3);
    const [, subida, envio] = llamadas;
    expect(subida.url).toMatch(/\/me\/message_attachments$/);
    expect(subida.cuerpo.platform).toBe("instagram");
    expect(subida.cuerpo.message).toEqual({ attachment: { type: "image", payload: { is_reusable: true } } });
    expect(subida.cuerpo.filedata).toEqual({ nombre: "foto.jpg", tipo: "image/jpeg", bytes: 4 });
    expect(envio.cuerpo).toEqual({ recipient: { id: "IGSID" }, messaging_type: "RESPONSE", message: { attachment: { type: "image", payload: { attachment_id: "att.IG1" } } } });
    expect(r.ids).toEqual(["m.2"]);
  });

  it("Instagram: si Juan no logra bajar la foto, va por URL como antes (sin is_reusable)", async () => {
    for (const sitio of [() => new Response("No existe.", { status: 404 }), () => {
      throw new TypeError("network");
    }]) {
      const { llamadas, adaptador } = graphFalso(conSubida, sitio);
      await adaptador.enviar("instagram", { para: "IGSID", burbujas: [], medios: foto }, env);
      expect(llamadas).toHaveLength(1);
      expect(llamadas[0].cuerpo.message.attachment).toEqual({ type: "image", payload: { url: "https://sitio/foto.jpg" } });
    }
  });

  it("Instagram: si los tres caminos fallan, el error dice qué contestó Meta a cada uno (se ve en Odoo) y avisa qué SÍ salió", async () => {
    const todoMal = (c: Llamada, n: number) =>
      c.cuerpo?.message?.text ? Response.json({ message_id: `m.${n}` }) : c.url.endsWith("/me/message_attachments") ? rechazo("Unsupported upload") : rechazo("Error al subir el producto");
    const { llamadas, adaptador } = graphFalso(todoMal);
    const e = await adaptador.enviar("instagram", { para: "IGSID", burbujas: ["Mira"], medios: foto }, env).catch((x) => x);
    expect(e).toBeInstanceOf(EnvioParcialError);
    expect(e.enviado).toEqual({ burbujas: 1, medios: 0, ids: ["m.0"] });
    // Odoo guarda 200 letras: los tres intentos caben, con lo que dijo Meta y su código.
    expect(e.message).toBe("Instagram no aceptó la foto · envío: Error al subir el producto [100] · aparte: Unsupported upload [100] · URL: Error al subir el producto [100]");
    expect(e.message.length).toBeLessThanOrEqual(200);
    expect(e.message).not.toContain("https://sitio/");
    expect(llamadas.map((l) => (l.url.endsWith("/me/message_attachments") ? "subida" : l.cuerpo?.filedata ? "envío con archivo" : l.cuerpo.message.text ? "texto" : "url"))).toEqual(["texto", "envío con archivo", "subida", "url"]);
  });

  it("Instagram: una foto de más de 8 MB no se sube ni se manda (y avisa qué SÍ salió)", async () => {
    const grande = graphFalso(conSubida, () => new Response(new Uint8Array(MAX_FOTO_INSTAGRAM_BYTES + 1), { headers: { "content-type": "image/jpeg" } }));
    const e = await grande.adaptador.enviar("instagram", { para: "IGSID", burbujas: ["Mira"], medios: foto }, env).catch((x) => x);
    expect(e).toBeInstanceOf(EnvioParcialError);
    expect(e.message).toMatch(/8 MB/);
    expect(e.enviado).toEqual({ burbujas: 1, medios: 0, ids: ["m.0"] });
    expect(grande.llamadas).toHaveLength(1);
  });

  it("Messenger sigue igual: sube en la misma llamada (filedata) y nunca usa message_attachments", async () => {
    const { llamadas, adaptador } = graphFalso(conSubida);
    await adaptador.enviar("messenger", { para: "PSID1", burbujas: [], medios: [{ tipo: "imagen", url: "https://sitio/foto.jpg" }] }, env);
    expect(llamadas).toHaveLength(1);
    expect(llamadas[0].url).toMatch(/\/me\/messages$/);
    expect(llamadas[0].cuerpo.filedata).toEqual({ nombre: "foto.jpg", tipo: "image/jpeg", bytes: 4 });
  });

  it("ambos canales avisan que solo se escribe dentro de las 24 h; Instagram corta el texto más corto", () => {
    const { adaptador } = graphFalso();
    expect(adaptador.capacidades("messenger").ventana24h).toBe(true);
    expect(adaptador.capacidades("instagram").ventana24h).toBe(true);
    expect(adaptador.capacidades("instagram").maxTexto).toBeLessThan(adaptador.capacidades("messenger").maxTexto);
  });

  it("fuera de la ventana de 24 h Meta rechaza: el error trae el motivo y NO el token", async () => {
    const { adaptador } = graphFalso(() => Response.json({ error: { message: "This message is sent outside of allowed window.", code: 10 } }, { status: 400 }));
    const err = await adaptador.enviar("messenger", { para: "PSID1", burbujas: ["Hola"], medios: [] }, env).catch((e: Error) => e);
    expect(err).toBeInstanceOf(Error);
    expect((err as Error).message).toMatch(/outside of allowed window/);
    expect((err as Error).message).toMatch(/código 10/);
    expect((err as Error).message).not.toContain(TOKEN_PAGINA);
  });

  it("si se corta a la mitad, avisa qué SÍ salió (para que el reintento no lo repita)", async () => {
    const { llamadas, adaptador } = graphFalso((_c, n) => (n === 2 ? Response.json({ error: { message: "Temporarily unavailable", code: 2 } }, { status: 500 }) : Response.json({ recipient_id: "1", message_id: `m.${n}` })));
    const e = await adaptador.enviar("messenger", { para: "PSID1", burbujas: ["Uno", "Dos", "Tres"], medios: [] }, env).catch((x) => x);
    expect(llamadas).toHaveLength(3);
    expect(e).toBeInstanceOf(EnvioParcialError);
    expect(e.enviado).toEqual({ burbujas: 2, medios: 0, ids: ["m.0", "m.1"] });
  });

  it("si falla desde la primera llamada, es un error normal (no salió nada)", async () => {
    const { adaptador } = graphFalso(() => Response.json({ error: { message: "x", code: 1 } }, { status: 500 }));
    const e = await adaptador.enviar("messenger", { para: "PSID1", burbujas: ["Uno"], medios: [] }, env).catch((x) => x);
    expect(e).toBeInstanceOf(Error);
    expect(e).not.toBeInstanceOf(EnvioParcialError);
  });

  it("sin META_PAGE_TOKEN no intenta nada", async () => {
    const { llamadas, adaptador } = graphFalso();
    await expect(adaptador.enviar("messenger", { para: "PSID1", burbujas: ["Hola"], medios: [] }, {} as Env)).rejects.toThrow(/META_PAGE_TOKEN/);
    expect(llamadas).toHaveLength(0);
  });

  it("escribiendo: manda typing_on y nunca rompe si Meta falla", async () => {
    const { llamadas, adaptador } = graphFalso(() => Response.json({ error: { message: "no" } }, { status: 500 }));
    await expect(adaptador.escribiendo!("messenger", "PSID1", env)).resolves.toBeUndefined();
    expect(llamadas[0].cuerpo).toEqual({ recipient: { id: "PSID1" }, sender_action: "typing_on" });
  });
});

describe("foto de perfil", () => {
  const FOTO_URL = "https://scontent.xx.fbcdn.net/v/t1.30497-1/abc.jpg";
  const responder = (c: { url: string }) =>
    c.url.includes("graph.facebook.com") ? Response.json({ profile_pic: FOTO_URL, id: "123456" }) : new Response(new Uint8Array([5, 6, 7]), { headers: { "content-type": "image/jpeg" } });

  it("el nombre: Messenger da nombre y apellido; Instagram el nombre o, si no hay, @usuario", async () => {
    const msg = graphFalso(() => Response.json({ first_name: " Ana ", last_name: "Pérez", id: "1" }));
    expect(await msg.adaptador.nombreDePerfil!("messenger", "1234567890", env)).toBe("Ana Pérez");
    expect(msg.llamadas[0].url).toContain("/1234567890?fields=first_name,last_name");
    expect(msg.llamadas[0].url).not.toContain(TOKEN_PAGINA);
    expect(msg.llamadas[0].cabeceras.authorization).toBe(`Bearer ${TOKEN_PAGINA}`);
    const ig = graphFalso(() => Response.json({ name: "Tienda Ana", username: "ana.pty" }));
    expect(await ig.adaptador.nombreDePerfil!("instagram", "1234567890", env)).toBe("Tienda Ana");
    expect(ig.llamadas[0].url).toContain("fields=name,username");
    const soloUsuario = graphFalso(() => Response.json({ username: "ana.pty" }));
    expect(await soloUsuario.adaptador.nombreDePerfil!("instagram", "1234567890", env)).toBe("@ana.pty");
  });

  it("el nombre: sin el permiso del perfil (lo normal antes de la revisión de Meta), sale de la conversación de la página", async () => {
    // El perfil responde «(#100) … Business Asset User Profile Access»; la conversación sí trae a los participantes.
    const sinPermiso = (c: Llamada) =>
      c.url.includes("/me/conversations")
        ? Response.json({ data: [{ id: "t_1", participants: { data: [{ name: "DCASA PTY", id: "999" }, { name: "Ana Pérez", email: "x@facebook.com", id: "1234567890" }] } }] })
        : Response.json({ error: { message: "Requires Business Asset User Profile Access", code: 100 } }, { status: 400 });
    const msg = graphFalso(sinPermiso);
    expect(await msg.adaptador.nombreDePerfil!("messenger", "1234567890", env)).toBe("Ana Pérez");
    expect(msg.llamadas[1].url).toContain("/me/conversations?platform=messenger&user_id=1234567890&fields=participants");
    expect(msg.llamadas[1].url).not.toContain(TOKEN_PAGINA);
    const ig = graphFalso((c) =>
      c.url.includes("/me/conversations")
        ? Response.json({ data: [{ participants: { data: [{ username: "dcasapty", id: "999" }, { username: "ana.pty", id: "1234567890" }] } }] })
        : Response.json({ error: { code: 100 } }, { status: 400 }),
    );
    expect(await ig.adaptador.nombreDePerfil!("instagram", "1234567890", env)).toBe("@ana.pty");
    expect(ig.llamadas[1].url).toContain("platform=instagram");
  });

  it("el nombre: sin token, con un id raro, errores de Graph o nada que leer, null (y sin caracteres de control)", async () => {
    expect(await graphFalso().adaptador.nombreDePerfil!("messenger", "1234567890", {} as Env)).toBeNull();
    const raro = graphFalso();
    expect(await raro.adaptador.nombreDePerfil!("messenger", "../me", env)).toBeNull();
    expect(raro.llamadas).toHaveLength(0);
    const errores = graphFalso(() => Response.json({ error: { message: "x" } }, { status: 400 }));
    expect(await errores.adaptador.nombreDePerfil!("messenger", "1234567890", env)).toBeNull();
    expect(errores.llamadas).toHaveLength(2);   // el perfil y la conversación
    expect(await graphFalso(() => Response.json({ id: "1", data: [] })).adaptador.nombreDePerfil!("messenger", "1234567890", env)).toBeNull();
    const deOtro = graphFalso((c) => (c.url.includes("conversations") ? Response.json({ data: [{ participants: { data: [{ name: "Otra persona", id: "555" }] } }] }) : Response.json({})));
    expect(await deOtro.adaptador.nombreDePerfil!("messenger", "1234567890", env)).toBeNull();
    expect(await graphFalso(() => Response.json({ first_name: "Ana\u0000\n", last_name: "" })).adaptador.nombreDePerfil!("messenger", "1234567890", env)).toBe("Ana");
  });

  it("pide profile_pic a Graph (con el token de la Página) y baja la imagen de los servidores de Meta", async () => {
    const { llamadas, adaptador } = graphFalso(responder);
    const foto = await adaptador.fotoDePerfil!("messenger", "1234567890", env);
    expect(foto).toEqual({ bytes: new Uint8Array([5, 6, 7]), mime: "image/jpeg" });
    expect(llamadas[0].url).toMatch(/graph\.facebook\.com\/v[\d.]+\/1234567890\?fields=profile_pic$/);
    expect(llamadas[0].cabeceras.authorization).toBe(`Bearer ${env.META_PAGE_TOKEN}`);
    expect(llamadas[1].url).toBe(FOTO_URL);
  });

  it("solo baja de servidores de Meta, por https: cualquier otra dirección se ignora", async () => {
    for (const mala of ["https://evil.example.com/a.jpg", "http://scontent.xx.fbcdn.net/a.jpg", "https://fbcdn.net.evil.com/a.jpg", "no es una url", ""]) {
      const { llamadas, adaptador } = graphFalso(() => Response.json({ profile_pic: mala }));
      expect(await adaptador.fotoDePerfil!("instagram", "1234567890", env)).toBeNull();
      expect(llamadas).toHaveLength(1);
    }
  });

  it("sin foto, con error de Meta, sin token o con un id raro: null, sin lanzar", async () => {
    expect(await graphFalso(() => Response.json({ id: "1" })).adaptador.fotoDePerfil!("messenger", "1234567890", env)).toBeNull();
    expect(await graphFalso(() => Response.json({ error: { message: "x" } }, { status: 400 })).adaptador.fotoDePerfil!("messenger", "1234567890", env)).toBeNull();
    const sinToken = graphFalso();
    expect(await sinToken.adaptador.fotoDePerfil!("messenger", "1234567890", {} as Env)).toBeNull();
    expect(await sinToken.adaptador.fotoDePerfil!("messenger", "../me?fields=x", env)).toBeNull();
    expect(sinToken.llamadas).toHaveLength(0);
  });

  it("una imagen enorme no se acepta", async () => {
    const { adaptador } = graphFalso((c) => (c.url.includes("graph.facebook.com") ? Response.json({ profile_pic: FOTO_URL }) : new Response(new Uint8Array(400 * 1024))));
    expect(await adaptador.fotoDePerfil!("messenger", "1234567890", env)).toBeNull();
  });
});

describe("lo que falta y el registro", () => {
  const { adaptador } = graphFalso();

  it("faltantes devuelve solo NOMBRES", () => {
    expect(adaptador.faltantes({} as Env, "messenger")).toEqual(["META_PAGE_TOKEN", "META_APP_SECRET", "META_VERIFY_TOKEN"]);
    expect(adaptador.faltantes(env, "messenger")).toEqual([]);
    expect(adaptador.configurado(env, "instagram")).toBe(true);
    expect(adaptador.configurado({ ...env, META_PAGE_TOKEN: "" } as Env, "instagram")).toBe(false);
  });

  it("salud: configurado o no, sin pretender saber si hay conexión", async () => {
    // (Puede traer `avisosComentarios`: si se sabe cuál es la página, para los comentarios; ver comentarios-revision2.)
    expect(await adaptador.salud!("messenger", env)).toMatchObject({ configurado: true, faltan: [], conectado: null });
    expect((await adaptador.salud!("messenger", {} as Env)).faltan).toContain("META_PAGE_TOKEN");
  });

  it("un solo adaptador atiende los dos canales, en una sola ruta", () => {
    const lista = crearAdaptadores();
    expect(adaptadorDe("messenger", lista)).toBe(adaptadorDe("instagram", lista));
    expect(adaptadorPorRuta("/webhooks/meta", lista)?.canales).toEqual(["messenger", "instagram"]);
  });
});
