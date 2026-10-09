/**
 * Messenger e Instagram (Meta oficial): verificación GET, firma X-Hub-Signature-256, ecos de la Página, envío por la Send API.
 * Reescritura de test/channels/meta.test.ts del CRM de Baby Caleb (sin ManyChat).
 */
import { describe, expect, it } from "vitest";
import type { Env } from "../../src/env";
import { crearMeta, eventosDeMeta } from "../../src/canales/meta";
import { adaptadorDe, adaptadorPorRuta, crearAdaptadores } from "../../src/canales/index";
import { hmacHex } from "../../src/seguridad";

const SECRETO = "secreto-de-la-app-0123456789abcdef";
const VERIFICACION = "verificacion-de-prueba-0123456789";
const TOKEN_PAGINA = "token-de-la-pagina-0123456789";

const env = { META_APP_SECRET: SECRETO, META_VERIFY_TOKEN: VERIFICACION, META_PAGE_TOKEN: TOKEN_PAGINA } as unknown as Env;

interface Llamada {
  url: string;
  cabeceras: Record<string, string>;
  cuerpo: any;
}

function graphFalso(respuesta: (c: Llamada, n: number) => Response = (_c, n) => Response.json({ recipient_id: "1", message_id: `m.${n}` })) {
  const llamadas: Llamada[] = [];
  const f: typeof fetch = async (recurso, init) => {
    const c = {
      url: String(recurso),
      cabeceras: Object.fromEntries(Object.entries((init?.headers ?? {}) as Record<string, string>).map(([k, v]) => [k.toLowerCase(), v])),
      cuerpo: init?.body ? JSON.parse(String(init.body)) : null,
    };
    llamadas.push(c);
    return respuesta(c, llamadas.length - 1);
  };
  return { llamadas, adaptador: crearMeta({ fetch: f, dormir: async () => {} }) };
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

  it("Messenger manda imágenes y documentos como adjuntos por URL, después del texto", async () => {
    const { llamadas, adaptador } = graphFalso();
    await adaptador.enviar(
      "messenger",
      { para: "PSID1", burbujas: ["Mira"], medios: [{ tipo: "imagen", url: "https://sitio/foto.jpg" }, { tipo: "documento", url: "https://sitio/ficha.pdf", nombre: "ficha.pdf" }] },
      env,
    );
    expect(llamadas.map((l) => l.cuerpo.message.text ?? l.cuerpo.message.attachment.type)).toEqual(["Mira", "image", "file"]);
    expect(llamadas[1].cuerpo.message.attachment.payload.url).toBe("https://sitio/foto.jpg");
  });

  it("Instagram NO admite documentos: la imagen sale, el documento se omite", async () => {
    const { llamadas, adaptador } = graphFalso();
    await adaptador.enviar("instagram", { para: "IGSID", burbujas: [], medios: [{ tipo: "imagen", url: "https://sitio/foto.jpg" }, { tipo: "documento", url: "https://sitio/ficha.pdf" }] }, env);
    expect(llamadas).toHaveLength(1);
    expect(llamadas[0].cuerpo.message.attachment.type).toBe("image");
    expect(adaptador.capacidades("instagram").documentos).toBe(false);
    expect(adaptador.capacidades("messenger").documentos).toBe(true);
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

describe("lo que falta y el registro", () => {
  const { adaptador } = graphFalso();

  it("faltantes devuelve solo NOMBRES", () => {
    expect(adaptador.faltantes({} as Env, "messenger")).toEqual(["META_PAGE_TOKEN", "META_APP_SECRET", "META_VERIFY_TOKEN"]);
    expect(adaptador.faltantes(env, "messenger")).toEqual([]);
    expect(adaptador.configurado(env, "instagram")).toBe(true);
    expect(adaptador.configurado({ ...env, META_PAGE_TOKEN: "" } as Env, "instagram")).toBe(false);
  });

  it("salud: configurado o no, sin pretender saber si hay conexión", async () => {
    expect(await adaptador.salud!("messenger", env)).toEqual({ configurado: true, faltan: [], conectado: null });
    expect((await adaptador.salud!("messenger", {} as Env)).faltan).toContain("META_PAGE_TOKEN");
  });

  it("un solo adaptador atiende los dos canales, en una sola ruta", () => {
    const lista = crearAdaptadores();
    expect(adaptadorDe("messenger", lista)).toBe(adaptadorDe("instagram", lista));
    expect(adaptadorPorRuta("/webhooks/meta", lista)?.canales).toEqual(["messenger", "instagram"]);
  });
});
