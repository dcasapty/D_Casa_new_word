/**
 * Instagram por «inicio de sesión de Instagram» (la segunda puerta, graph.instagram.com): webhook propio (/webhooks/instagram) con
 * la clave secreta de la app de Instagram, solo la cuenta de D'CASA, envío con la llave de Instagram (la renovada si la hay), nombre
 * y foto del cliente, y que SIN sus secretos todo queda como antes (Instagram por la página).
 * Mismo patrón que test/canales/meta.test.ts.
 */
import { describe, expect, it, vi } from "vitest";
import type { Env } from "../../src/env";
import { crearMeta } from "../../src/canales/meta";
import { adaptadorPorRuta, crearAdaptadores } from "../../src/canales/index";
import { CLAVE_CUENTA, CLAVE_LLAVE, huella, type EstadoLlave, type Llavero } from "../../src/canales/instagramLlave";
import { soloDeLaCuenta } from "../../src/canales/instagramLogin";
import { hmacHex } from "../../src/seguridad";
import { EnvioParcialError } from "../../src/canales/tipos";

const SECRETO_FB = "secreto-de-la-app-de-facebook-0123456789";
const SECRETO_IG = "secreto-de-la-app-de-instagram-abcdef0123";
const VERIFICACION = "verificacion-de-prueba-0123456789";
const TOKEN_PAGINA = "token-de-la-pagina-0123456789";
const TOKEN_IG = "IGAAtoken-de-instagram-pegado-0123456789";
const TOKEN_IG_RENOVADO = "IGAAtoken-de-instagram-renovado-9876543210";
const CUENTA = "17841400000000001"; // el id de la cuenta de D'CASA en los webhooks
const AJENA = "17841499999999999";
const CLIENTE = "1234567890123456"; // el IGSID de quien escribe
const AHORA = Date.UTC(2026, 10, 12, 15, 0);

const envPagina = { META_APP_SECRET: SECRETO_FB, META_VERIFY_TOKEN: VERIFICACION, META_PAGE_TOKEN: TOKEN_PAGINA } as unknown as Env;
const envIg = { ...envPagina, INSTAGRAM_TOKEN: TOKEN_IG, INSTAGRAM_APP_SECRET: SECRETO_IG } as unknown as Env;

interface Llamada {
  url: string;
  metodo: string;
  cabeceras: Record<string, string>;
  cuerpo: any;
}

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

export function llaveroEnMemoria(inicial: Record<string, string> = {}): Llavero & { datos: Map<string, string> } {
  const datos = new Map(Object.entries(inicial));
  return {
    datos,
    leer: async (_env, clave) => datos.get(clave) ?? null,
    guardar: async (_env, clave, valor) => void datos.set(clave, valor),
  };
}

/** Graph de Instagram de mentira: /me dice la cuenta, me/messages acepta, el perfil da un nombre. Anota todo. */
function igFalso(
  opciones: {
    respuesta?: (c: Llamada, n: number) => Response | undefined;
    sitio?: (url: string) => Response;
    llavero?: Llavero & { datos: Map<string, string> };
  } = {},
) {
  const llamadas: Llamada[] = [];
  const descargas: string[] = [];
  const llavero = opciones.llavero ?? llaveroEnMemoria();
  const f: typeof fetch = async (recurso, init) => {
    const url = String(recurso);
    if (url.startsWith("https://sitio/")) {
      descargas.push(url);
      return (opciones.sitio ?? ((u: string) => new Response(new Uint8Array([1, 2, 3, 4]), { headers: { "content-type": u.endsWith(".pdf") ? "application/pdf" : "image/jpeg" } })))(url);
    }
    const c: Llamada = {
      url,
      metodo: init?.method ?? "GET",
      cabeceras: Object.fromEntries(Object.entries((init?.headers ?? {}) as Record<string, string>).map(([k, v]) => [k.toLowerCase(), v])),
      cuerpo: init?.body instanceof FormData ? deFormData(init.body) : init?.body ? JSON.parse(String(init.body)) : null,
    };
    llamadas.push(c);
    const propia = opciones.respuesta?.(c, llamadas.length - 1);
    if (propia) return propia;
    const u = new URL(url);
    if (u.pathname.endsWith("/me") && u.searchParams.get("fields") === "user_id,username") return Response.json({ user_id: CUENTA, username: "dcasapty", id: "26000000000000001" });
    if (u.pathname.endsWith("/me/messages")) return Response.json({ recipient_id: CLIENTE, message_id: `ig.m.${llamadas.length - 1}` });
    return Response.json({ error: { message: "ruta de prueba desconocida", code: 100 } }, { status: 400 });
  };
  return { llamadas, descargas, llavero, adaptador: crearMeta({ fetch: f, dormir: async () => {}, llavero, ahora: () => AHORA }) };
}

const mensaje = (extra: object = {}, entrada = CUENTA) => ({
  object: "instagram",
  entry: [{ id: entrada, time: 1_790_000_000, messaging: [{ sender: { id: CLIENTE }, recipient: { id: entrada }, timestamp: 1_790_000_000_000, message: { mid: "aWdfZAG1_1", text: "Hola, ¿tienen sofás?" }, ...extra }] }],
});

async function firmado(cuerpo: object, secreto = SECRETO_IG, ruta = "/webhooks/instagram") {
  const crudo = JSON.stringify(cuerpo);
  return new Request(`https://juan.example${ruta}`, { method: "POST", headers: { "content-type": "application/json", "x-hub-signature-256": `sha256=${await hmacHex(secreto, crudo)}` }, body: crudo });
}

const noLoDice = (texto: string) => {
  for (const s of [TOKEN_IG, TOKEN_IG_RENOVADO, SECRETO_IG, TOKEN_PAGINA, SECRETO_FB]) expect(texto).not.toContain(s);
};

describe("el webhook de Instagram por inicio de sesión de Instagram (/webhooks/instagram)", () => {
  it("es del adaptador de Meta (una ruta más), sin cambiar las rutas que ya había", () => {
    const lista = crearAdaptadores();
    expect(adaptadorPorRuta("/webhooks/instagram", lista)).toBe(adaptadorPorRuta("/webhooks/meta", lista));
    expect(lista.map((a) => a.ruta)).not.toContain("/webhooks/instagram");
  });

  it("verificación (GET) con el MISMO META_VERIFY_TOKEN: reto tal cual; con otro token, 403", async () => {
    const { adaptador } = igFalso();
    const verificar = (q: string, e: Env = envIg) => adaptador.recibir(new Request(`https://juan.example/webhooks/instagram?${q}`), e);
    const ok = await verificar(`hub.mode=subscribe&hub.verify_token=${VERIFICACION}&hub.challenge=98765`);
    expect([ok.respuesta.status, await ok.respuesta.text()]).toEqual([200, "98765"]);
    expect((await verificar("hub.mode=subscribe&hub.verify_token=otro&hub.challenge=1")).respuesta.status).toBe(403);
    expect((await verificar(`hub.mode=subscribe&hub.verify_token=${VERIFICACION}&hub.challenge=1`, {} as Env)).respuesta.status).toBe(403);
  });

  it("firma buena (clave de la app de INSTAGRAM): entra el mensaje del cliente, para Odoo como Instagram", async () => {
    const { adaptador } = igFalso();
    const r = await adaptador.recibir(await firmado(mensaje()), envIg);
    expect(r.respuesta.status).toBe(200);
    expect(r.guardarAntes).toBe(true);
    expect(r.entrantes).toEqual([{ canal: "instagram", id_externo: CLIENTE, id_mensaje: "aWdfZAG1_1", texto: "Hola, ¿tienen sofás?", adjuntos: [], ts: 1_790_000_000_000, propio: false }]);
  });

  it("firma mala, ausente, con la clave de FACEBOOK o sin INSTAGRAM_APP_SECRET: 401 y no entra nada", async () => {
    const { adaptador } = igFalso();
    const cuerpo = JSON.stringify(mensaje());
    for (const firma of [null, "", "sha256=", `sha256=${"0".repeat(64)}`, `sha256=${await hmacHex("otro", cuerpo)}`]) {
      const req = new Request("https://juan.example/webhooks/instagram", { method: "POST", headers: firma === null ? {} : { "x-hub-signature-256": firma }, body: cuerpo });
      const r = await adaptador.recibir(req, envIg);
      expect(r.respuesta.status, String(firma)).toBe(401);
      expect(r.entrantes).toEqual([]);
    }
    expect((await adaptador.recibir(await firmado(mensaje(), SECRETO_FB), envIg)).respuesta.status).toBe(401);
    expect((await adaptador.recibir(await firmado(mensaje()), { ...envIg, INSTAGRAM_APP_SECRET: undefined } as Env)).respuesta.status).toBe(401);
    expect((await adaptador.recibir(await firmado(mensaje()), envPagina)).respuesta.status).toBe(401); // sin los secretos nuevos
  });

  it("la firma vale para el cuerpo EXACTO; un cuerpo que no es JSON se acepta sin romper; otros métodos 405", async () => {
    const { adaptador } = igFalso();
    const crudo = JSON.stringify(mensaje());
    const firma = `sha256=${await hmacHex(SECRETO_IG, crudo)}`;
    const cambiado = new Request("https://x/webhooks/instagram", { method: "POST", headers: { "x-hub-signature-256": firma }, body: crudo.replace("sofás", "sofas") });
    expect((await adaptador.recibir(cambiado, envIg)).respuesta.status).toBe(401);
    const noJson = "esto no es json";
    const r = await adaptador.recibir(new Request("https://x/webhooks/instagram", { method: "POST", headers: { "x-hub-signature-256": `sha256=${await hmacHex(SECRETO_IG, noJson)}` }, body: noJson }), envIg);
    expect([r.respuesta.status, r.entrantes]).toEqual([200, []]);
    expect((await adaptador.recibir(new Request("https://x/webhooks/instagram", { method: "PUT" }), envIg)).respuesta.status).toBe(405);
  });

  it("el eco (lo contestó una vendedora desde la app de Instagram) es `propio` y el cliente es el DESTINATARIO", async () => {
    const { adaptador } = igFalso();
    const eco = mensaje({ sender: { id: CUENTA }, recipient: { id: CLIENTE }, message: { mid: "aWdfZAG1_eco", text: "Te atiendo yo, soy Ana", is_echo: true } });
    const [e] = (await adaptador.recibir(await firmado(eco), envIg)).entrantes;
    expect(e).toMatchObject({ canal: "instagram", id_externo: CLIENTE, id_mensaje: "aWdfZAG1_eco", texto: "Te atiendo yo, soy Ana", propio: true });
  });

  it("una foto (y audio, video, archivo) llega como adjunto con la URL de Meta; lo que hoy se ignora, se ignora igual", async () => {
    const { adaptador } = igFalso();
    const foto = mensaje({
      message: {
        mid: "m_foto",
        attachments: [
          { type: "image", payload: { url: "https://lookaside.fbsbx.com/ig_messaging_cdn/?asset_id=1" } },
          { type: "audio", payload: { url: "https://cdn.fbsbx.com/a.mp4" } },
          { type: "ig_reel", payload: { url: "https://cdn.fbsbx.com/reel" } },
        ],
      },
    });
    const [e] = (await adaptador.recibir(await firmado(foto), envIg)).entrantes;
    expect(e.adjuntos.map((a) => [a.tipo, a.url])).toEqual([
      ["imagen", "https://lookaside.fbsbx.com/ig_messaging_cdn/?asset_id=1"],
      ["audio", "https://cdn.fbsbx.com/a.mp4"],
    ]);
    // Lecturas, reacciones, mensajes borrados o no soportados: nada que atender (y ni se pregunta la cuenta).
    const sinNada = {
      object: "instagram",
      entry: [
        {
          id: CUENTA,
          messaging: [
            { sender: { id: CLIENTE }, recipient: { id: CUENTA }, read: { mid: "x" } },
            { sender: { id: CLIENTE }, recipient: { id: CUENTA }, reaction: { mid: "x", action: "react", emoji: "❤️" } },
            { sender: { id: CLIENTE }, recipient: { id: CUENTA }, message: { mid: "y", is_deleted: true } },
            { sender: { id: CLIENTE }, recipient: { id: CUENTA }, message: { mid: "z", is_unsupported: true } },
          ],
        },
      ],
    };
    const g = igFalso();
    const r = await g.adaptador.recibir(await firmado(sinNada), envIg);
    expect([r.respuesta.status, r.entrantes]).toEqual([200, []]);
    expect(g.llamadas).toEqual([]);
  });

  it("solo la cuenta de D'CASA: lo de otra cuenta, o dirigido a otra, se ignora (200, nada entra)", async () => {
    const aviso = vi.spyOn(console, "warn").mockImplementation(() => {});
    const { adaptador } = igFalso();
    const deOtra = await adaptador.recibir(await firmado(mensaje({}, AJENA)), envIg);
    expect([deOtra.respuesta.status, deOtra.entrantes]).toEqual([200, []]);
    const aOtra = mensaje({ recipient: { id: AJENA } });
    expect((await adaptador.recibir(await firmado(aOtra), envIg)).entrantes).toEqual([]);
    const ecoDeOtra = mensaje({ sender: { id: AJENA }, recipient: { id: CLIENTE }, message: { mid: "e", text: "x", is_echo: true } });
    expect((await adaptador.recibir(await firmado(ecoDeOtra), envIg)).entrantes).toEqual([]);
    // Un lote mixto: entra solo lo de D'CASA.
    const mixto = { object: "instagram", entry: [...mensaje({}, AJENA).entry, ...mensaje().entry] };
    expect((await adaptador.recibir(await firmado(mixto), envIg)).entrantes.map((e) => e.id_externo)).toEqual([CLIENTE]);
    expect(aviso.mock.calls.flat().join(" ")).toMatch(/no son de la cuenta de D'CASA/);
    aviso.mockRestore();
  });

  it("los mensajes de prueba de Meta a la propia cuenta (`is_self`) no son de un cliente", () => {
    const { cuerpo } = soloDeLaCuenta(mensaje({ message: { mid: "s", text: "prueba", is_self: true } }), new Set([CUENTA]));
    expect(cuerpo.entry?.[0].messaging).toEqual([]);
  });

  it("la cuenta: sin INSTAGRAM_ACCOUNT_ID se la pregunta a Meta UNA vez (GET /me en graph.instagram.com) y la recuerda", async () => {
    const { adaptador, llamadas, llavero } = igFalso();
    await adaptador.recibir(await firmado(mensaje()), envIg);
    await adaptador.recibir(await firmado(mensaje()), envIg);
    const alMe = llamadas.filter((l) => new URL(l.url).pathname.endsWith("/me"));
    expect(alMe).toHaveLength(1);
    expect(alMe[0].url).toMatch(/^https:\/\/graph\.instagram\.com\/v\d+\.\d+\/me\?fields=user_id,username$/);
    expect(alMe[0].cabeceras.authorization).toBe(`Bearer ${TOKEN_IG}`);
    expect(JSON.parse(llavero.datos.get(CLAVE_CUENTA)!)).toMatchObject({ ids: [CUENTA, "26000000000000001"], usuario: "dcasapty", semilla: huella(TOKEN_IG) });
    // Otro proceso (otro Worker) la lee de lo guardado, sin preguntar.
    const otro = igFalso({ llavero });
    expect((await otro.adaptador.recibir(await firmado(mensaje()), envIg)).entrantes).toHaveLength(1);
    expect(otro.llamadas).toEqual([]);
  });

  it("con INSTAGRAM_ACCOUNT_ID no se pregunta nada y manda esa", async () => {
    const { adaptador, llamadas } = igFalso();
    const env = { ...envIg, INSTAGRAM_ACCOUNT_ID: AJENA } as Env;
    expect((await adaptador.recibir(await firmado(mensaje({}, AJENA)), env)).entrantes).toHaveLength(1);
    vi.spyOn(console, "warn").mockImplementation(() => {});
    expect((await adaptador.recibir(await firmado(mensaje()), env)).entrantes).toEqual([]);
    vi.restoreAllMocks();
    expect(llamadas).toEqual([]);
  });

  it("si no se sabe cuál es la cuenta (Meta no contesta /me): 503 para que Meta reintente, y nada entra", async () => {
    const error = vi.spyOn(console, "error").mockImplementation(() => {});
    const aviso = vi.spyOn(console, "warn").mockImplementation(() => {});
    const { adaptador } = igFalso({ respuesta: (c) => (new URL(c.url).pathname.endsWith("/me") ? Response.json({ error: { message: "Invalid OAuth access token", code: 190 } }, { status: 400 }) : undefined) });
    const r = await adaptador.recibir(await firmado(mensaje()), envIg);
    expect([r.respuesta.status, r.entrantes]).toEqual([503, []]);
    noLoDice([...error.mock.calls, ...aviso.mock.calls].flat().join(" "));
    vi.restoreAllMocks();
  });
});

describe("envío por graph.instagram.com con la llave de Instagram", () => {
  it("texto: graph.instagram.com/<v>/me/messages, la llave de Instagram en la cabecera (no en la URL), sin messaging_type", async () => {
    const { adaptador, llamadas } = igFalso();
    const r = await adaptador.enviar("instagram", { para: CLIENTE, burbujas: ["Hola.", "Escríbeme *persona* y te atiende una vendedora."], medios: [] }, envIg);
    expect(llamadas).toHaveLength(2);
    expect(llamadas[0].url).toMatch(/^https:\/\/graph\.instagram\.com\/v\d+\.\d+\/me\/messages$/);
    expect(llamadas[0].cabeceras.authorization).toBe(`Bearer ${TOKEN_IG}`);
    expect(llamadas[0].cuerpo).toEqual({ recipient: { id: CLIENTE }, message: { text: "Hola." } });
    expect(llamadas[1].cuerpo.message.text).toBe("Escríbeme persona y te atiende una vendedora.");
    expect(r.ids).toEqual(["ig.m.0", "ig.m.1"]);
    noLoDice(llamadas.map((l) => l.url).join(" "));
  });

  it("Messenger no cambia: sigue por graph.facebook.com con la llave de la página", async () => {
    const { adaptador, llamadas } = igFalso();
    await adaptador.enviar("messenger", { para: "PSID1", burbujas: ["Hola"], medios: [] }, envIg);
    expect(llamadas[0].url).toMatch(/^https:\/\/graph\.facebook\.com\//);
    expect(llamadas[0].cabeceras.authorization).toBe(`Bearer ${TOKEN_PAGINA}`);
    expect(llamadas[0].cuerpo.messaging_type).toBe("RESPONSE");
  });

  it("usa la llave RENOVADA por Juan si viene de la pegada; si la dueña pegó otra, manda la pegada", async () => {
    const estado: EstadoLlave = { semilla: huella(TOKEN_IG), vistaEn: AHORA - 30 * 86_400_000, llave: TOKEN_IG_RENOVADO, vence: AHORA + 59 * 86_400_000, renovadaEn: AHORA - 86_400_000 };
    const llavero = llaveroEnMemoria({ [CLAVE_LLAVE]: JSON.stringify(estado) });
    const g = igFalso({ llavero });
    await g.adaptador.enviar("instagram", { para: CLIENTE, burbujas: ["Hola"], medios: [] }, envIg);
    expect(g.llamadas[0].cabeceras.authorization).toBe(`Bearer ${TOKEN_IG_RENOVADO}`);
    const otra = igFalso({ llavero });
    await otra.adaptador.enviar("instagram", { para: CLIENTE, burbujas: ["Hola"], medios: [] }, { ...envIg, INSTAGRAM_TOKEN: "IGAAotra-llave-pegada-por-la-duena-000" } as Env);
    expect(otra.llamadas[0].cabeceras.authorization).toBe("Bearer IGAAotra-llave-pegada-por-la-duena-000");
  });

  it("foto: la SUBE en el mismo envío (filedata), como hoy, sin messaging_type; nuestra URL firmada no le llega a Meta", async () => {
    const { adaptador, llamadas, descargas } = igFalso();
    const r = await adaptador.enviar("instagram", { para: CLIENTE, burbujas: ["Mira"], medios: [{ tipo: "imagen", url: "https://sitio/foto.jpg" }] }, envIg);
    expect(descargas).toEqual(["https://sitio/foto.jpg"]);
    const foto = llamadas[1];
    expect(foto.url).toMatch(/^https:\/\/graph\.instagram\.com\/v\d+\.\d+\/me\/messages$/);
    expect(foto.cabeceras.authorization).toBe(`Bearer ${TOKEN_IG}`);
    expect(foto.cuerpo.messaging_type).toBeUndefined();
    expect(foto.cuerpo.message).toEqual({ attachment: { type: "image", payload: { is_reusable: false } } });
    expect(foto.cuerpo.filedata).toEqual({ nombre: "foto.jpg", tipo: "image/jpeg", bytes: 4 });
    expect(JSON.stringify(llamadas)).not.toContain("https://sitio/");
    expect(r.ids).toEqual(["ig.m.0", "ig.m.1"]);
  });

  it("foto: los mismos tres caminos que hoy (en el envío, aparte con attachment_id, por URL), todos en graph.instagram.com", async () => {
    const rechazo = (m: string) => Response.json({ error: { message: m, code: 100 } }, { status: 400 });
    const { adaptador, llamadas } = igFalso({
      respuesta: (c) => (c.cuerpo?.filedata && c.url.endsWith("/me/messages") ? rechazo("Error al subir") : c.url.endsWith("/me/message_attachments") ? rechazo("Unsupported") : undefined),
    });
    await adaptador.enviar("instagram", { para: CLIENTE, burbujas: [], medios: [{ tipo: "imagen", url: "https://sitio/foto.jpg" }] }, envIg);
    expect(llamadas.map((l) => [new URL(l.url).host, l.url.endsWith("/me/message_attachments") ? "aparte" : l.cuerpo?.filedata ? "envío" : "url"])).toEqual([
      ["graph.instagram.com", "envío"],
      ["graph.instagram.com", "aparte"],
      ["graph.instagram.com", "url"],
    ]);
    expect(llamadas[2].cuerpo).toEqual({ recipient: { id: CLIENTE }, message: { attachment: { type: "image", payload: { url: "https://sitio/foto.jpg" } } } });
  });

  it("PDF: esta puerta lo admite (Meta: `file`, solo pdf, hasta 25 MB): se sube en el mismo envío", async () => {
    const { adaptador, llamadas } = igFalso();
    expect(adaptador.capacidades("instagram", envIg).documentos).toBe(true);
    const r = await adaptador.enviar("instagram", { para: CLIENTE, burbujas: [], medios: [{ tipo: "documento", url: "https://sitio/cotizacion.pdf", nombre: "Cotización S00042.pdf" }] }, envIg);
    expect(llamadas).toHaveLength(1);
    expect(llamadas[0].cuerpo.message).toEqual({ attachment: { type: "file", payload: { is_reusable: false } } });
    expect(llamadas[0].cuerpo.filedata).toEqual({ nombre: "Cotización S00042.pdf", tipo: "application/pdf", bytes: 4 });
    expect(r.ids).toEqual(["ig.m.0"]);
  });

  it("PDF que Instagram no acepta (ni subido ni por URL): sale lo mismo que hoy, el enlace en el texto", async () => {
    const aviso = vi.spyOn(console, "warn").mockImplementation(() => {});
    const { adaptador, llamadas } = igFalso({ respuesta: (c) => (c.cuerpo?.message?.text ? undefined : Response.json({ error: { message: "Unsupported file", code: 100 } }, { status: 400 })) });
    const r = await adaptador.enviar("instagram", { para: CLIENTE, burbujas: [], medios: [{ tipo: "documento", url: "https://sitio/cotizacion.pdf?sig=abc", nombre: "Cotización.pdf" }] }, envIg);
    expect(llamadas.map((l) => (l.cuerpo?.filedata ? "subido" : l.cuerpo.message.attachment ? "url" : "enlace"))).toEqual(["subido", "url", "enlace"]);
    expect(llamadas[2].cuerpo).toEqual({ recipient: { id: CLIENTE }, message: { text: "Cotización.pdf: https://sitio/cotizacion.pdf?sig=abc" } });
    expect(r.ids).toEqual(["ig.m.2"]);
    // Un documento que no es PDF (o pasa de 25 MB) va directo como enlace.
    const otro = igFalso({ sitio: () => new Response(new Uint8Array([1]), { headers: { "content-type": "application/vnd.ms-excel" } }) });
    await otro.adaptador.enviar("instagram", { para: CLIENTE, burbujas: [], medios: [{ tipo: "documento", url: "https://sitio/lista.xls", nombre: "lista.xls" }] }, envIg);
    expect(otro.llamadas.map((l) => l.cuerpo.message.text)).toEqual(["lista.xls: https://sitio/lista.xls"]);
    aviso.mockRestore();
  });

  it("si se corta a la mitad avisa qué SÍ salió; fuera de la ventana el error trae el motivo y NO la llave", async () => {
    const { adaptador } = igFalso({ respuesta: (_c, n) => (n === 1 ? Response.json({ error: { message: "This message is sent outside of allowed window.", code: 10 } }, { status: 400 }) : undefined) });
    const e = await adaptador.enviar("instagram", { para: CLIENTE, burbujas: ["Uno", "Dos"], medios: [] }, envIg).catch((x) => x);
    expect(e).toBeInstanceOf(EnvioParcialError);
    expect(e.enviado).toEqual({ burbujas: 1, medios: 0, ids: ["ig.m.0"] });
    expect(e.message).toMatch(/outside of allowed window.*código 10/);
    noLoDice(e.message);
  });

  it("sin INSTAGRAM_TOKEN (solo la clave secreta): no intenta nada y dice qué falta", async () => {
    const { adaptador, llamadas } = igFalso();
    const env = { ...envPagina, INSTAGRAM_APP_SECRET: SECRETO_IG } as Env;
    await expect(adaptador.enviar("instagram", { para: CLIENTE, burbujas: ["Hola"], medios: [] }, env)).rejects.toThrow(/INSTAGRAM_TOKEN/);
    expect(llamadas).toEqual([]);
  });

  it("escribiendo: typing_on por graph.instagram.com, y nunca rompe si Meta no lo acepta", async () => {
    const { adaptador, llamadas } = igFalso({ respuesta: () => Response.json({ error: { message: "no" } }, { status: 400 }) });
    await expect(adaptador.escribiendo!("instagram", CLIENTE, envIg)).resolves.toBeUndefined();
    expect(llamadas[0].url).toMatch(/^https:\/\/graph\.instagram\.com\/.*\/me\/messages$/);
    expect(llamadas[0].cuerpo).toEqual({ recipient: { id: CLIENTE }, sender_action: "typing_on" });
  });
});

describe("el nombre y la foto del cliente (User Profile API de esta puerta)", () => {
  it("el nombre: name, o @username si no hay; con la llave de Instagram en la cabecera", async () => {
    const { adaptador, llamadas } = igFalso({ respuesta: (c) => (c.url.includes(`/${CLIENTE}?fields=name,username`) ? Response.json({ name: " Ana Pérez ", username: "ana.pty" }) : undefined) });
    expect(await adaptador.nombreDePerfil!("instagram", CLIENTE, envIg)).toBe("Ana Pérez");
    expect(llamadas[0].url).toMatch(new RegExp(`^https://graph\\.instagram\\.com/v\\d+\\.\\d+/${CLIENTE}\\?fields=name,username$`));
    expect(llamadas[0].cabeceras.authorization).toBe(`Bearer ${TOKEN_IG}`);
    const soloUsuario = igFalso({ respuesta: (c) => (c.url.includes("fields=name,username") ? Response.json({ username: "ana.pty" }) : undefined) });
    expect(await soloUsuario.adaptador.nombreDePerfil!("instagram", CLIENTE, envIg)).toBe("@ana.pty");
  });

  it("el nombre: si el perfil no responde, sale de la conversación (como hoy); si nada, null", async () => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    const conv = igFalso({
      respuesta: (c) =>
        c.url.includes("/me/conversations")
          ? Response.json({ data: [{ participants: { data: [{ username: "dcasapty", id: CUENTA }, { username: "ana.pty", id: CLIENTE }] } }] })
          : c.url.includes("fields=name,username")
            ? Response.json({ error: { code: 230 } }, { status: 400 })
            : undefined,
    });
    expect(await conv.adaptador.nombreDePerfil!("instagram", CLIENTE, envIg)).toBe("@ana.pty");
    expect(conv.llamadas[1].url).toContain(`graph.instagram.com/`);
    expect(conv.llamadas[1].url).toContain(`/me/conversations?platform=instagram&user_id=${CLIENTE}&fields=participants`);
    const nada = igFalso({ respuesta: () => Response.json({ error: { code: 100 } }, { status: 400 }) });
    expect(await nada.adaptador.nombreDePerfil!("instagram", CLIENTE, envIg)).toBeNull();
    vi.restoreAllMocks();
  });

  it("la foto de perfil: profile_pic de graph.instagram.com y la imagen solo de servidores de Meta", async () => {
    const FOTO = "https://scontent.cdninstagram.com/v/t51/abc.jpg";
    const { adaptador, llamadas } = igFalso({
      respuesta: (c) => (c.url.includes("fields=profile_pic") ? Response.json({ profile_pic: FOTO }) : c.url === FOTO ? new Response(new Uint8Array([5, 6, 7]), { headers: { "content-type": "image/jpeg" } }) : undefined),
    });
    expect(await adaptador.fotoDePerfil!("instagram", CLIENTE, envIg)).toEqual({ bytes: new Uint8Array([5, 6, 7]), mime: "image/jpeg" });
    expect(llamadas[0].url).toMatch(/^https:\/\/graph\.instagram\.com\/v[\d.]+\/\d+\?fields=profile_pic$/);
    expect(llamadas[0].cabeceras.authorization).toBe(`Bearer ${TOKEN_IG}`);
    const mala = igFalso({ respuesta: (c) => (c.url.includes("fields=profile_pic") ? Response.json({ profile_pic: "https://evil.example.com/a.jpg" }) : undefined) });
    expect(await mala.adaptador.fotoDePerfil!("instagram", CLIENTE, envIg)).toBeNull();
    expect(mala.llamadas).toHaveLength(1);
  });
});

describe("qué puerta, qué falta y que sin los secretos nuevos todo queda como antes", () => {
  it("con los secretos nuevos: Instagram pide INSTAGRAM_TOKEN, INSTAGRAM_APP_SECRET y META_VERIFY_TOKEN (no la llave de la página)", () => {
    const { adaptador } = igFalso();
    expect(adaptador.faltantes(envIg, "instagram")).toEqual([]);
    expect(adaptador.faltantes({ INSTAGRAM_TOKEN: TOKEN_IG } as Env, "instagram")).toEqual(["INSTAGRAM_APP_SECRET", "META_VERIFY_TOKEN"]);
    expect(adaptador.faltantes({ INSTAGRAM_APP_SECRET: SECRETO_IG, META_VERIFY_TOKEN: "v" } as Env, "instagram")).toEqual(["INSTAGRAM_TOKEN"]);
    expect(adaptador.configurado({ INSTAGRAM_TOKEN: TOKEN_IG, INSTAGRAM_APP_SECRET: SECRETO_IG, META_VERIFY_TOKEN: "v" } as Env, "instagram")).toBe(true);
    // Messenger sigue pidiendo lo suyo.
    expect(adaptador.faltantes({ INSTAGRAM_TOKEN: TOKEN_IG, INSTAGRAM_APP_SECRET: SECRETO_IG } as Env, "messenger")).toEqual(["META_PAGE_TOKEN", "META_APP_SECRET", "META_VERIFY_TOKEN"]);
  });

  it("capacidades: por esta puerta, PDF sí y texto de 800; sin env o sin los secretos, las de siempre", () => {
    const { adaptador } = igFalso();
    expect(adaptador.capacidades("instagram", envIg)).toEqual({ imagenes: true, documentos: true, ventana24h: true, maxTexto: 800 });
    expect(adaptador.capacidades("instagram", envPagina)).toEqual({ imagenes: true, documentos: false, ventana24h: true, maxTexto: 950 });
    expect(adaptador.capacidades("instagram")).toEqual(adaptador.capacidades("instagram", envPagina));
    expect(adaptador.capacidades("messenger", envIg)).toEqual(adaptador.capacidades("messenger"));
  });

  it("sin los secretos nuevos Instagram sigue por la página: graph.facebook.com, META_PAGE_TOKEN y messaging_type", async () => {
    const { adaptador, llamadas } = igFalso();
    await adaptador.enviar("instagram", { para: CLIENTE, burbujas: ["Hola"], medios: [] }, envPagina);
    expect(llamadas[0].url).toMatch(/^https:\/\/graph\.facebook\.com\/v\d+\.\d+\/me\/messages$/);
    expect(llamadas[0].cabeceras.authorization).toBe(`Bearer ${TOKEN_PAGINA}`);
    expect(llamadas[0].cuerpo).toEqual({ recipient: { id: CLIENTE }, messaging_type: "RESPONSE", message: { text: "Hola" } });
    expect(await adaptador.saludLocal!("instagram", envPagina)).toEqual({ puerta: "pagina_facebook" });
    expect(adaptador.faltantes(envPagina, "instagram")).toEqual([]);
  });

  it("sin los secretos nuevos, lo de Instagram que llega por la página entra como siempre", async () => {
    const { adaptador } = igFalso();
    const r = await adaptador.recibir(await firmado(mensaje({}, "PAGINA"), SECRETO_FB, "/webhooks/meta"), envPagina);
    expect(r.entrantes.map((e) => [e.canal, e.id_externo])).toEqual([["instagram", CLIENTE]]);
  });

  it("con la segunda puerta, lo de Instagram que llega por la PÁGINA se ignora (no se atiende dos veces); Messenger entra igual", async () => {
    const aviso = vi.spyOn(console, "warn").mockImplementation(() => {});
    const { adaptador } = igFalso();
    const ig = await adaptador.recibir(await firmado(mensaje({}, "PAGINA"), SECRETO_FB, "/webhooks/meta"), envIg);
    expect([ig.respuesta.status, ig.entrantes]).toEqual([200, []]);
    const msn = { object: "page", entry: [{ id: "PAGINA", messaging: [{ sender: { id: "PSID1" }, recipient: { id: "PAGINA" }, timestamp: 1, message: { mid: "m_1", text: "hola" } }] }] };
    expect((await adaptador.recibir(await firmado(msn, SECRETO_FB, "/webhooks/meta"), envIg)).entrantes.map((e) => e.canal)).toEqual(["messenger"]);
    aviso.mockRestore();
  });

  it("el cron sin INSTAGRAM_TOKEN no llama a nadie ni guarda nada", async () => {
    const { adaptador, llamadas, llavero } = igFalso();
    await adaptador.mantener!(envPagina);
    expect(llamadas).toEqual([]);
    expect(llavero.datos.size).toBe(0);
  });
});
