/**
 * Telegram: el canal de PRUEBAS (clientas de prueba y avisos). Webhook con secreto; envío de texto, fotos y documentos.
 * Reescritura de test/channels/telegram.test.ts del CRM de Baby Caleb.
 */
import { describe, expect, it } from "vitest";
import type { Env } from "../../src/env";
import { avisarPorTelegram, crearTelegram, type TgUpdate } from "../../src/canales/telegram";

const SECRETO = "secreto-del-webhook-de-prueba";
const TOKEN = "123456:token-de-prueba";
const env = { TELEGRAM_BOT_TOKEN_JUAN: TOKEN, TELEGRAM_WEBHOOK_SECRET_JUAN: SECRETO } as Env;

interface Llamada {
  url: string;
  cuerpo: Record<string, any> | null;
}

function telegramFalso(respuestas: Record<string, unknown> = {}) {
  const llamadas: Llamada[] = [];
  let id = 100;
  const fetchFalso: typeof fetch = async (recurso, init) => {
    const url = String(recurso);
    llamadas.push({ url, cuerpo: init?.body ? JSON.parse(String(init.body)) : null });
    const metodo = url.split("/").pop()!.split("?")[0];
    if (url.includes("/file/bot")) return new Response(new Uint8Array([9, 8, 7]), { headers: { "content-type": "image/jpeg" } });
    const manual = respuestas[metodo];
    if (manual instanceof Response) return manual;
    return Response.json(manual ?? { ok: true, result: metodo === "getFile" ? { file_path: "photos/file_1.jpg" } : { message_id: ++id } });
  };
  return { fetch: fetchFalso, llamadas };
}

const tg = (f = telegramFalso()) => ({ adaptador: crearTelegram({ fetch: f.fetch, dormir: async () => {} }), ...f });

const update = (msg: Partial<NonNullable<TgUpdate["message"]>> = {}): TgUpdate => ({
  update_id: 1,
  message: { message_id: 7, from: { id: 555, first_name: "Karen" }, chat: { id: 555, type: "private" }, date: 1_790_000_000, text: "hola", ...msg },
});

const peticion = (cuerpo: unknown, secreto: string | null = SECRETO, metodo = "POST") =>
  new Request("https://juan.example/webhooks/telegram", {
    method: metodo,
    headers: { "content-type": "application/json", ...(secreto !== null ? { "x-telegram-bot-api-secret-token": secreto } : {}) },
    body: metodo === "GET" ? undefined : JSON.stringify(cuerpo),
  });

describe("el webhook de Telegram", () => {
  it("con el secreto correcto traduce el mensaje: celular/llave = chat_id, nombre, texto, hora", async () => {
    const { adaptador } = tg();
    const r = await adaptador.recibir(peticion(update()), env);
    expect(r.respuesta.status).toBe(200);
    expect(r.entrantes).toEqual([
      { canal: "telegram", id_externo: "555", id_mensaje: "tg:555:7", nombre: "Karen", texto: "hola", adjuntos: [], ts: 1_790_000_000_000 },
    ]);
  });

  it("sin el secreto, con otro secreto o con el secreto vacío → 401 y nada entra", async () => {
    const { adaptador } = tg();
    for (const mal of [null, "", "otro", SECRETO + "x", SECRETO.slice(0, -1)]) {
      const r = await adaptador.recibir(peticion(update(), mal), env);
      expect(r.respuesta.status, String(mal)).toBe(401);
      expect(r.entrantes).toEqual([]);
    }
  });

  it("falla cerrado: sin TELEGRAM_WEBHOOK_SECRET_JUAN configurado no pasa ni un secreto vacío", async () => {
    const { adaptador } = tg();
    const sinSecreto = { TELEGRAM_BOT_TOKEN_JUAN: TOKEN } as Env;
    expect((await adaptador.recibir(peticion(update(), ""), sinSecreto)).respuesta.status).toBe(401);
    expect((await adaptador.recibir(peticion(update(), "cualquiera"), sinSecreto)).respuesta.status).toBe(401);
  });

  it("solo POST", async () => {
    const { adaptador } = tg();
    expect((await adaptador.recibir(peticion(null, SECRETO, "GET"), env)).respuesta.status).toBe(405);
  });

  it("un cuerpo que no es JSON responde 200 (un error haría reintentar a Telegram sin parar)", async () => {
    const { adaptador } = tg();
    const r = await adaptador.recibir(new Request("https://x/webhooks/telegram", { method: "POST", headers: { "x-telegram-bot-api-secret-token": SECRETO }, body: "no es json" }), env);
    expect(r.respuesta.status).toBe(200);
    expect(r.entrantes).toEqual([]);
  });

  it("grupos, bots, ediciones y botones se ignoran", async () => {
    const { adaptador } = tg();
    for (const u of [update({ chat: { id: -100, type: "group" } }), update({ from: { id: 9, is_bot: true } }), { update_id: 2 } as TgUpdate, update({ text: undefined })]) {
      const r = await adaptador.recibir(peticion(u), env);
      expect(r.respuesta.status).toBe(200);
      expect(r.entrantes).toEqual([]);
    }
  });

  it("«/start» es un «hola» para el bot", async () => {
    const { adaptador } = tg();
    expect((await adaptador.recibir(peticion(update({ text: "/start" })), env)).entrantes[0].texto).toBe("Hola");
    expect((await adaptador.recibir(peticion(update({ text: "/start@mi_bot" })), env)).entrantes[0].texto).toBe("Hola");
  });

  it("«/miid» contesta el chat_id de quien escribe y no llega al bot", async () => {
    const f = telegramFalso();
    const { adaptador } = tg(f);
    const r = await adaptador.recibir(peticion(update({ text: "/miid" })), env);
    expect(r.entrantes).toEqual([]);
    const envio = f.llamadas.find((l) => l.url.endsWith("/sendMessage"))!;
    expect(envio.cuerpo).toMatchObject({ chat_id: 555 });
    expect(envio.cuerpo!.text).toContain("555");
  });

  it("una foto con pie: el pie es el texto y la foto una imagen descargable por getFile (sin exponer el token)", async () => {
    const f = telegramFalso();
    const { adaptador } = tg(f);
    const r = await adaptador.recibir(
      peticion(update({ text: undefined, caption: "mi comprobante", photo: [{ file_id: "chica", width: 90, height: 90 }, { file_id: "grande", width: 800, height: 800 }] })),
      env,
    );
    const e = r.entrantes[0];
    expect(e.texto).toBe("mi comprobante");
    expect(e.adjuntos).toHaveLength(1);
    expect(e.adjuntos[0]).toMatchObject({ tipo: "imagen" });
    // Nada de la URL con el token viaja en el mensaje:
    expect(JSON.stringify(e)).not.toContain(TOKEN);
    const bajado = await e.adjuntos[0].obtener!();
    expect([...bajado!.bytes]).toEqual([9, 8, 7]);
    const getFile = f.llamadas.find((l) => l.url.includes("getFile"))!;
    expect(getFile.url).toContain("file_id=grande");
  });

  it("nota de voz, documento y video", async () => {
    const { adaptador } = tg();
    const r = await adaptador.recibir(
      peticion(update({ text: undefined, voice: { file_id: "v" }, document: { file_id: "d", file_name: "cedula.pdf", mime_type: "application/pdf" }, video: { file_id: "vi" } })),
      env,
    );
    expect(r.entrantes[0].adjuntos.map((a) => a.tipo)).toEqual(["audio", "documento", "video"]);
    expect(r.entrantes[0].adjuntos[1]).toMatchObject({ nombre: "cedula.pdf", mime: "application/pdf" });
  });

  it("si getFile falla, el adjunto queda sin bytes (no se cae el webhook)", async () => {
    const f = telegramFalso({ getFile: { ok: false, description: "file is too big" } });
    const { adaptador } = tg(f);
    const r = await adaptador.recibir(peticion(update({ text: undefined, photo: [{ file_id: "x", width: 1, height: 1 }] })), env);
    expect(await r.entrantes[0].adjuntos[0].obtener!()).toBeNull();
  });
});

describe("enviar por Telegram", () => {
  it("texto: una llamada por burbuja, en orden, y devuelve los ids", async () => {
    const f = telegramFalso();
    const { adaptador } = tg(f);
    const r = await adaptador.enviar("telegram", { para: "555", burbujas: ["Uno", "Dos"], medios: [] }, env);
    const envios = f.llamadas.filter((l) => l.url.endsWith("/sendMessage"));
    expect(envios.map((e) => e.cuerpo)).toEqual([{ chat_id: "555", text: "Uno" }, { chat_id: "555", text: "Dos" }]);
    expect(r.ids).toEqual(["tg:555:101", "tg:555:102"]);
  });

  it("quita los asteriscos de negrita (Telegram no los entiende): *persona* sale como persona", async () => {
    const f = telegramFalso();
    const { adaptador } = tg(f);
    await adaptador.enviar("telegram", { para: "555", burbujas: ["Escríbeme *persona* y te atiende una vendedora. 2 * 3"], medios: [] }, env);
    const envios = f.llamadas.filter((l) => l.url.endsWith("/sendMessage"));
    expect(envios[0].cuerpo).toEqual({ chat_id: "555", text: "Escríbeme persona y te atiende una vendedora. 2 * 3" });
  });

  it("imagen: sendPhoto con la URL y el pie; documento: sendDocument", async () => {
    const f = telegramFalso();
    const { adaptador } = tg(f);
    await adaptador.enviar(
      "telegram",
      {
        para: "555",
        burbujas: [],
        medios: [
          { tipo: "imagen", url: "https://dcasapty.com/foto.jpg", pie: "Cama Queen Milán" },
          { tipo: "documento", url: "https://odoo.example/cot.pdf", nombre: "cot.pdf", pie: "Tu cotización" },
        ],
      },
      env,
    );
    expect(f.llamadas.map((l) => l.url.split("/").pop())).toEqual(["sendPhoto", "sendDocument"]);
    expect(f.llamadas[0].cuerpo).toEqual({ chat_id: "555", photo: "https://dcasapty.com/foto.jpg", caption: "Cama Queen Milán" });
    expect(f.llamadas[1].cuerpo).toMatchObject({ document: "https://odoo.example/cot.pdf", caption: "Tu cotización" });
  });

  it("si Telegram rechaza, lanza el motivo (chat not found, bot bloqueado...) sin mostrar el token", async () => {
    const f = telegramFalso({ sendMessage: Response.json({ ok: false, description: "Forbidden: bot was blocked by the user" }, { status: 403 }) });
    const { adaptador } = tg(f);
    const p = adaptador.enviar("telegram", { para: "555", burbujas: ["x"], medios: [] }, env);
    await expect(p).rejects.toThrow(/403.*bot was blocked by the user/);
    await p.catch((e) => expect(String(e)).not.toContain(TOKEN));
  });

  it("sin TELEGRAM_BOT_TOKEN_JUAN no envía", async () => {
    const { adaptador } = tg();
    await expect(adaptador.enviar("telegram", { para: "1", burbujas: ["x"], medios: [] }, {} as Env)).rejects.toThrow(/TELEGRAM_BOT_TOKEN_JUAN/);
  });

  it("«escribiendo…» es un sendChatAction y nunca lanza", async () => {
    const f = telegramFalso({ sendChatAction: Response.json({ ok: false }, { status: 500 }) });
    const { adaptador } = tg(f);
    await expect(adaptador.escribiendo!("telegram", "555", env)).resolves.toBeUndefined();
    expect(f.llamadas[0].cuerpo).toEqual({ chat_id: "555", action: "typing" });
  });

  it("capacidades: imágenes y documentos, sin ventana de 24 h", () => {
    const { adaptador } = tg();
    expect(adaptador.capacidades("telegram")).toMatchObject({ imagenes: true, documentos: true, ventana24h: false });
    expect(adaptador.ruta).toBe("/webhooks/telegram");
  });
});

describe("configuración y avisos", () => {
  it("dice los NOMBRES de lo que falta", () => {
    const { adaptador } = tg();
    expect(adaptador.faltantes({} as Env, "telegram")).toEqual(["TELEGRAM_BOT_TOKEN_JUAN", "TELEGRAM_WEBHOOK_SECRET_JUAN"]);
    expect(adaptador.faltantes({ TELEGRAM_BOT_TOKEN_JUAN: "x" } as Env, "telegram")).toEqual(["TELEGRAM_WEBHOOK_SECRET_JUAN"]);
    expect(adaptador.configurado(env, "telegram")).toBe(true);
  });

  it("avisarPorTelegram: manda el texto a un chat; sin token o sin chat no hace nada; nunca lanza", async () => {
    const f = telegramFalso();
    expect(await avisarPorTelegram(env, "999", "Aviso", f.fetch)).toBe(true);
    expect(f.llamadas[0].cuerpo).toEqual({ chat_id: "999", text: "Aviso" });
    expect(await avisarPorTelegram({} as Env, "999", "Aviso", f.fetch)).toBe(false);
    expect(await avisarPorTelegram(env, "", "Aviso", f.fetch)).toBe(false);
    expect(await avisarPorTelegram(env, "999", "Aviso", (async () => { throw new Error("sin red"); }) as typeof fetch)).toBe(false);
  });
});
