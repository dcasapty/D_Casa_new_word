/**
 * Comentarios de Facebook e Instagram por las TRES vías (2026-11-12): la página de Facebook (`feed`), Instagram por la página
 * (`comments` en /webhooks/meta) e Instagram por inicio de sesión de Instagram (`comments` en /webhooks/instagram). Qué se lee de cada
 * aviso, qué se ignora (lo propio, editado, oculto, vacío, en vivo, viejo) y cómo se contesta (forma exacta de las llamadas a Meta).
 */
import { describe, expect, it } from "vitest";
import type { Env } from "../../src/env";
import { crearMeta } from "../../src/canales/meta";
import { comentariosDeMeta, traeComentarios, VIDA_DE_UN_COMENTARIO_MS } from "../../src/canales/metaComentarios";
import { enlaceDeMeta, type MetaCuerpo } from "../../src/canales/metaComun";
import type { ComentarioEntrante } from "../../src/canales/tipos";
import { hmacHex } from "../../src/seguridad";
import { llaveroEnMemoria } from "../helpers/llaveroEnMemoria";

const SECRETO_FB = "secreto-de-la-app-de-facebook-0123456789";
const SECRETO_IG = "secreto-de-la-app-de-instagram-abcdef0123";
const VERIFICACION = "verificacion-de-prueba-0123456789";
const TOKEN_PAGINA = "token-de-la-pagina-0123456789";
const TOKEN_IG = "IGAAtoken-de-instagram-pegado-0123456789";
const PAGINA = "100200300400500";
const CUENTA_IG = "17841400000000001";
const PSID = "2838000000000001";
const IGSID = "1234567890123456";
const AHORA = Date.UTC(2026, 10, 12, 15, 0);

const envPagina = { META_APP_SECRET: SECRETO_FB, META_VERIFY_TOKEN: VERIFICACION, META_PAGE_TOKEN: TOKEN_PAGINA } as unknown as Env;
const envIg = { ...envPagina, INSTAGRAM_TOKEN: TOKEN_IG, INSTAGRAM_APP_SECRET: SECRETO_IG } as unknown as Env;

/** El aviso de Facebook (`feed`) cuando alguien comenta una publicación de la página (ejemplo de Meta, con nuestros datos de prueba). */
const deFacebook = (valor: Record<string, unknown> = {}, entrada = PAGINA): MetaCuerpo => ({
  object: "page",
  entry: [
    {
      id: entrada,
      time: Math.floor(AHORA / 1000),
      changes: [
        {
          field: "feed",
          value: {
            from: { id: PSID, name: "Ana María López" },
            post: { status_type: "added_photos", is_published: true, permalink_url: "https://www.facebook.com/dcasapty/posts/pfbid0abc", id: `${PAGINA}_777` },
            message: "¿Cuánto cuesta el sofá gris?",
            post_id: `${PAGINA}_777`,
            comment_id: "777_888",
            created_time: Math.floor(AHORA / 1000) - 60,
            item: "comment",
            parent_id: `${PAGINA}_777`,
            verb: "add",
            ...valor,
          },
        },
      ],
    },
  ],
});

/** El aviso de Instagram (`comments`): igual por la página y por inicio de sesión de Instagram. */
const deInstagram = (valor: Record<string, unknown> = {}, entrada = CUENTA_IG, campo = "comments"): MetaCuerpo => ({
  object: "instagram",
  entry: [{ id: entrada, time: Math.floor(AHORA / 1000), changes: [{ field: campo, value: { from: { id: IGSID, username: "ana.muebles" }, media: { id: "18000000000000001", media_product_type: "FEED" }, id: "18100000000000002", text: "¿Lo tienen en azul?", ...valor } }] }],
});

describe("qué se lee de cada aviso", () => {
  it("Facebook (`feed`): un comentario nuevo con quién (PSID, para su conversación de Messenger), qué dijo y la publicación", () => {
    const { entrantes, ignorados } = comentariosDeMeta(deFacebook(), AHORA, { puerta: "pagina" });
    expect(ignorados).toEqual({ propios: 0, viejos: 0, otros: 0 });
    expect(entrantes).toEqual([
      {
        canal: "messenger",
        id_externo: PSID,
        id_mensaje: "comentario:facebook:777_888",
        nombre: "Ana María López",
        texto: "¿Cuánto cuesta el sofá gris?",
        adjuntos: [],
        ts: AHORA - 60_000,
        comentario: { red: "facebook", puerta: "pagina", id: "777_888", publicacion: `${PAGINA}_777`, enlace: "https://www.facebook.com/dcasapty/posts/pfbid0abc" },
      },
    ]);
  });

  it("Instagram (`comments`): el IGSID, el @usuario como nombre y la hora del aviso (Meta no manda la del comentario)", () => {
    for (const puerta of ["pagina", "instagram_login"] as const) {
      const { entrantes } = comentariosDeMeta(deInstagram(), AHORA, { puerta });
      expect(entrantes).toEqual([
        {
          canal: "instagram",
          id_externo: IGSID,
          id_mensaje: "comentario:instagram:18100000000000002",
          nombre: "@ana.muebles",
          texto: "¿Lo tienen en azul?",
          adjuntos: [],
          ts: AHORA,
          comentario: { red: "instagram", puerta, id: "18100000000000002", publicacion: "18000000000000001", usuario: "ana.muebles" },
        },
      ]);
    }
    // Otro ejemplo de Meta trae el id en `comment_id`: también vale.
    const otro = comentariosDeMeta(deInstagram({ id: undefined, comment_id: "18100000000000009" }), AHORA, { puerta: "pagina" });
    expect(otro.entrantes[0].comentario?.id).toBe("18100000000000009");
  });

  it("una respuesta a otro comentario: la pública va al de arriba (`padre`)", () => {
    expect(comentariosDeMeta(deFacebook({ parent_id: "777_555" }), AHORA, { puerta: "pagina" }).entrantes[0].comentario?.padre).toBe("777_555");
    expect(comentariosDeMeta(deInstagram({ parent_id: "18100000000000001" }), AHORA, { puerta: "pagina" }).entrantes[0].comentario?.padre).toBe("18100000000000001");
    expect(comentariosDeMeta(deFacebook(), AHORA, { puerta: "pagina" }).entrantes[0].comentario?.padre).toBeUndefined();
  });

  it("se ignoran los de la propia página o cuenta (sus respuestas también llegan como comentario)", () => {
    expect(comentariosDeMeta(deFacebook({ from: { id: PAGINA, name: "DCASA PTY" } }), AHORA, { puerta: "pagina" }).ignorados.propios).toBe(1);
    expect(comentariosDeMeta(deInstagram({ from: { id: CUENTA_IG, username: "dcasapty" } }), AHORA, { puerta: "pagina" }).ignorados.propios).toBe(1);
    expect(comentariosDeMeta(deInstagram({ from: { id: "26000000000000001", username: "x" } }), AHORA, { puerta: "instagram_login", propios: new Set(["26000000000000001"]) }).ignorados.propios).toBe(1);
    expect(comentariosDeMeta(deInstagram({ from: { id: "26000000000000002", username: "DCasaPty" } }), AHORA, { puerta: "instagram_login", usuarioPropio: "dcasapty" }).ignorados.propios).toBe(1);
  });

  it("se ignoran los editados, borrados, ocultos, sin texto, los de un video en vivo, las reacciones y los ids raros", () => {
    const casos: MetaCuerpo[] = [
      deFacebook({ verb: "edited" }),
      deFacebook({ verb: "remove" }),
      deFacebook({ is_hidden: true }),
      deFacebook({ message: "   " }),
      deFacebook({ item: "reaction", reaction_type: "like" }),
      deFacebook({ from: { id: "no-es-un-id", name: "x" } }),
      deInstagram({ text: "" }),
      deInstagram({}, CUENTA_IG, "live_comments"),
      deInstagram({ from: { id: "<script>" } }),
    ];
    for (const c of casos) expect(comentariosDeMeta(c, AHORA, { puerta: "pagina" }).entrantes, JSON.stringify(c)).toEqual([]);
  });

  it("se ignoran los de hace más de 7 días (Meta ya no deja la respuesta privada)", () => {
    const viejo = Math.floor((AHORA - VIDA_DE_UN_COMENTARIO_MS - 60_000) / 1000);
    const r = comentariosDeMeta(deFacebook({ created_time: viejo }), AHORA, { puerta: "pagina" });
    expect(r.entrantes).toEqual([]);
    expect(r.ignorados.viejos).toBe(1);
  });

  it("los mensajes (`messaging`) no son comentarios y un aviso sin `changes` no trae ninguno", () => {
    const mensaje: MetaCuerpo = { object: "page", entry: [{ id: PAGINA, messaging: [{ sender: { id: PSID }, recipient: { id: PAGINA }, message: { mid: "m1", text: "hola" } }] }] };
    expect(comentariosDeMeta(mensaje, AHORA, { puerta: "pagina" }).entrantes).toEqual([]);
    expect(traeComentarios(mensaje)).toBe(false);
    expect(traeComentarios(deFacebook())).toBe(true);
  });

  it("el enlace a la publicación solo si es https de Facebook o Instagram", () => {
    expect(enlaceDeMeta("https://www.instagram.com/p/C0d1g0/")).toBe("https://www.instagram.com/p/C0d1g0/");
    expect(enlaceDeMeta("https://fb.me/abc")).toBe("https://fb.me/abc");
    for (const malo of ["http://www.facebook.com/x", "https://facebook.com.evil.example/x", "javascript:alert(1)", "https://evil.example/instagram.com", 42]) expect(enlaceDeMeta(malo)).toBeUndefined();
    expect(comentariosDeMeta(deFacebook({ post: { permalink_url: "https://evil.example/p" } }), AHORA, { puerta: "pagina" }).entrantes[0].comentario?.enlace).toBeUndefined();
  });
});

// ── Los webhooks ─────────────────────────────────────────────────────────

interface Llamada {
  url: string;
  metodo: string;
  cabeceras: Record<string, string>;
  cuerpo: string | null;
}

function graphFalso(respuesta: (c: Llamada) => Response | undefined = () => undefined) {
  const llamadas: Llamada[] = [];
  const llavero = llaveroEnMemoria();
  const f: typeof fetch = async (recurso, init) => {
    const c: Llamada = {
      url: String(recurso),
      metodo: init?.method ?? "GET",
      cabeceras: Object.fromEntries(Object.entries((init?.headers ?? {}) as Record<string, string>).map(([k, v]) => [k.toLowerCase(), v])),
      cuerpo: init?.body ? String(init.body) : null,
    };
    llamadas.push(c);
    const propia = respuesta(c);
    if (propia) return propia;
    const u = new URL(c.url);
    if (u.pathname.endsWith("/me") && u.searchParams.get("fields") === "user_id,username") return Response.json({ user_id: CUENTA_IG, username: "dcasapty", id: "26000000000000001" });
    if (u.pathname.endsWith("/me/messages")) return Response.json({ recipient_id: IGSID, message_id: "m.privada.1" });
    if (u.pathname.endsWith("/comments") || u.pathname.endsWith("/replies")) return Response.json({ id: "respuesta.publica.1" });
    if (u.searchParams.get("fields")?.startsWith("caption")) return Response.json({ caption: "Sofá Roma en tela gris", permalink: "https://www.instagram.com/p/C0d1g0/", id: "18000000000000001" });
    if (u.searchParams.get("fields")?.startsWith("message")) return Response.json({ message: "Nuevo comedor de 6 puestos", permalink_url: "https://www.facebook.com/dcasapty/posts/pfbid0abc" });
    return Response.json({ error: { message: "ruta de prueba desconocida", code: 100 } }, { status: 400 });
  };
  return { llamadas, adaptador: crearMeta({ fetch: f, dormir: async () => {}, llavero, ahora: () => AHORA }) };
}

async function firmado(cuerpo: object, secreto: string, ruta: string) {
  const crudo = JSON.stringify(cuerpo);
  return new Request(`https://juan.example${ruta}`, { method: "POST", headers: { "content-type": "application/json", "x-hub-signature-256": `sha256=${await hmacHex(secreto, crudo)}` }, body: crudo });
}

describe("los webhooks de las tres vías", () => {
  it("la página (/webhooks/meta): el comentario de Facebook entra para guardarse antes del 200, como un mensaje", async () => {
    const { adaptador } = graphFalso();
    const r = await adaptador.recibir(await firmado(deFacebook({ created_time: Math.floor(Date.now() / 1000) }), SECRETO_FB, "/webhooks/meta"), envPagina);
    expect(r.respuesta.status).toBe(200);
    expect(r.guardarAntes).toBe(true);
    expect(r.entrantes.map((e) => [e.canal, e.id_externo, e.comentario?.red, e.comentario?.puerta])).toEqual([["messenger", PSID, "facebook", "pagina"]]);
  });

  it("la firma es la de siempre: mal firmado no entra nada", async () => {
    const { adaptador } = graphFalso();
    const r = await adaptador.recibir(await firmado(deFacebook(), "otro-secreto", "/webhooks/meta"), envPagina);
    expect(r.respuesta.status).toBe(401);
    expect(r.entrantes).toEqual([]);
  });

  it("Instagram por la página (/webhooks/meta) entra; si Instagram va por la segunda puerta, lo de la página se ignora", async () => {
    const { adaptador } = graphFalso();
    const ahora = Math.floor(Date.now() / 1000);
    const cuerpo = { ...deInstagram(), entry: deInstagram().entry!.map((e) => ({ ...e, time: ahora })) };
    const porLaPagina = await adaptador.recibir(await firmado(cuerpo, SECRETO_FB, "/webhooks/meta"), envPagina);
    expect(porLaPagina.entrantes.map((e) => e.comentario?.puerta)).toEqual(["pagina"]);
    const conSegundaPuerta = await adaptador.recibir(await firmado(cuerpo, SECRETO_FB, "/webhooks/meta"), envIg);
    expect(conSegundaPuerta.respuesta.status).toBe(200);
    expect(conSegundaPuerta.entrantes).toEqual([]);
  });

  it("Instagram por inicio de sesión (/webhooks/instagram): entra el del cliente; el de la propia cuenta y el de otra cuenta, no", async () => {
    const { adaptador } = graphFalso();
    const ahora = Math.floor(Date.now() / 1000);
    const conHora = (c: MetaCuerpo) => ({ ...c, entry: c.entry!.map((e) => ({ ...e, time: ahora })) });
    const delCliente = await adaptador.recibir(await firmado(conHora(deInstagram()), SECRETO_IG, "/webhooks/instagram"), envIg);
    expect(delCliente.respuesta.status).toBe(200);
    expect(delCliente.entrantes.map((e) => [e.id_externo, e.comentario?.puerta])).toEqual([[IGSID, "instagram_login"]]);
    const propio = await adaptador.recibir(await firmado(conHora(deInstagram({ from: { id: "26000000000000001", username: "dcasapty" } })), SECRETO_IG, "/webhooks/instagram"), envIg);
    expect(propio.entrantes).toEqual([]);
    const ajena = await adaptador.recibir(await firmado(conHora(deInstagram({}, "17841499999999999")), SECRETO_IG, "/webhooks/instagram"), envIg);
    expect(ajena.respuesta.status).toBe(200);
    expect(ajena.entrantes).toEqual([]);
  });
});

// ── Cómo se contesta ─────────────────────────────────────────────────────

const comentarioFb: ComentarioEntrante = { red: "facebook", puerta: "pagina", id: "777_888", publicacion: `${PAGINA}_777` };
const comentarioIg: ComentarioEntrante = { red: "instagram", puerta: "pagina", id: "18100000000000002", publicacion: "18000000000000001", usuario: "ana.muebles" };

describe("la respuesta privada (UNA por comentario)", () => {
  it("por la página: me/messages con `recipient: {comment_id}`, sin `messaging_type`, con la llave de la página", async () => {
    const { adaptador, llamadas } = graphFalso();
    const r = await adaptador.comentarios!.privada("messenger", comentarioFb, "Hola, *te* escribo por tu comentario.", envPagina);
    expect(r).toEqual({ id: "m.privada.1", destinatario: IGSID });
    expect(llamadas).toHaveLength(1);
    expect(llamadas[0].url).toBe("https://graph.facebook.com/v26.0/me/messages");
    expect(llamadas[0].metodo).toBe("POST");
    expect(llamadas[0].cabeceras.authorization).toBe(`Bearer ${TOKEN_PAGINA}`);
    expect(JSON.parse(llamadas[0].cuerpo!)).toEqual({ recipient: { comment_id: "777_888" }, message: { text: "Hola, te escribo por tu comentario." } });
  });

  it("por inicio de sesión de Instagram: graph.instagram.com con la llave de Instagram", async () => {
    const { adaptador, llamadas } = graphFalso();
    await adaptador.comentarios!.privada("instagram", { ...comentarioIg, puerta: "instagram_login" }, "Hola", envIg);
    const envio = llamadas.find((l) => l.url.endsWith("/me/messages"))!;
    expect(envio.url).toBe("https://graph.instagram.com/v26.0/me/messages");
    expect(envio.cabeceras.authorization).toBe(`Bearer ${TOKEN_IG}`);
    expect(JSON.parse(envio.cuerpo!)).toEqual({ recipient: { comment_id: "18100000000000002" }, message: { text: "Hola" } });
  });

  it("si Meta la rechaza, lanza con su mensaje y su código (sin la llave)", async () => {
    const { adaptador } = graphFalso((c) => (c.url.endsWith("/me/messages") ? Response.json({ error: { message: "(#10900) Activity already replied to", code: 10900 } }, { status: 400 }) : undefined));
    const error = await adaptador.comentarios!.privada("messenger", comentarioFb, "Hola", envPagina).catch((e: Error) => e);
    expect(String(error)).toContain("meta 400: (#10900) Activity already replied to (código 10900)");
    expect(String(error)).not.toContain(TOKEN_PAGINA);
  });

  it("sin la llave de la página no llama a nadie", async () => {
    const { adaptador, llamadas } = graphFalso();
    await expect(adaptador.comentarios!.privada("messenger", comentarioFb, "Hola", { ...envPagina, META_PAGE_TOKEN: undefined } as Env)).rejects.toThrow(/Falta META_PAGE_TOKEN/);
    expect(llamadas).toHaveLength(0);
  });
});

describe("la respuesta pública", () => {
  it("Facebook: POST /{comment-id}/comments con `message` (formulario)", async () => {
    const { adaptador, llamadas } = graphFalso();
    expect(await adaptador.comentarios!.publica("messenger", comentarioFb, "¡Hola, Ana! Te escribimos por mensaje directo con los detalles.", envPagina)).toEqual({ id: "respuesta.publica.1" });
    expect(llamadas[0].url).toBe("https://graph.facebook.com/v26.0/777_888/comments");
    expect(llamadas[0].cabeceras["content-type"]).toBe("application/x-www-form-urlencoded");
    expect(new URLSearchParams(llamadas[0].cuerpo!).get("message")).toBe("¡Hola, Ana! Te escribimos por mensaje directo con los detalles.");
  });

  it("Instagram: POST /{ig-comment-id}/replies, al de arriba si es una respuesta; por la segunda puerta en graph.instagram.com", async () => {
    const { adaptador, llamadas } = graphFalso();
    await adaptador.comentarios!.publica("instagram", { ...comentarioIg, padre: "18100000000000001" }, "¡Hola, @ana.muebles!", envPagina);
    expect(llamadas[0].url).toBe("https://graph.facebook.com/v26.0/18100000000000001/replies");
    await adaptador.comentarios!.publica("instagram", { ...comentarioIg, puerta: "instagram_login" }, "¡Hola!", envIg);
    expect(llamadas.at(-1)!.url).toBe("https://graph.instagram.com/v26.0/18100000000000002/replies");
    expect(llamadas.at(-1)!.cabeceras.authorization).toBe(`Bearer ${TOKEN_IG}`);
  });

  it("un id de comentario raro no sale a Meta", async () => {
    const { adaptador, llamadas } = graphFalso();
    await expect(adaptador.comentarios!.publica("messenger", { ...comentarioFb, id: "../me/messages?x" }, "hola", envPagina)).rejects.toThrow();
    expect(llamadas).toHaveLength(0);
  });
});

describe("la publicación comentada (una consulta barata, sin IA)", () => {
  it("Instagram: caption y permalink; Facebook: message y permalink_url", async () => {
    const { adaptador, llamadas } = graphFalso();
    expect(await adaptador.comentarios!.publicacion!("instagram", comentarioIg, envPagina)).toEqual({ texto: "Sofá Roma en tela gris", enlace: "https://www.instagram.com/p/C0d1g0/" });
    expect(llamadas[0].url).toBe("https://graph.facebook.com/v26.0/18000000000000001?fields=caption,permalink");
    expect(await adaptador.comentarios!.publicacion!("messenger", comentarioFb, envPagina)).toEqual({ texto: "Nuevo comedor de 6 puestos", enlace: "https://www.facebook.com/dcasapty/posts/pfbid0abc" });
    expect(llamadas[1].url).toBe(`https://graph.facebook.com/v26.0/${PAGINA}_777?fields=message,permalink_url`);
  });

  it("si Meta no la da, null (y se sigue sin ella)", async () => {
    const { adaptador } = graphFalso(() => Response.json({ error: { message: "sin permiso", code: 10 } }, { status: 403 }));
    expect(await adaptador.comentarios!.publicacion!("instagram", comentarioIg, envPagina)).toBeNull();
    expect(await adaptador.comentarios!.publicacion!("instagram", { ...comentarioIg, publicacion: undefined }, envPagina)).toBeNull();
  });
});
