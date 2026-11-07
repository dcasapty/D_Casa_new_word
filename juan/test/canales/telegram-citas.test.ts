/**
 * Telegram: citas (`reply_to_message`, con el texto del citado), reenviados (`forward_origin`) y reacciones (`message_reaction`, solo
 * si el webhook las pidió en `allowed_updates`). Telegram no les da a los bots «entregado» ni «leído»: no hay palomitas.
 */
import { describe, expect, it } from "vitest";
import type { Env } from "../../src/env";
import { crearTelegram, type TgUpdate } from "../../src/canales/telegram";

const SECRETO = "secreto-del-webhook-de-prueba";
const env = { TELEGRAM_BOT_TOKEN_JUAN: "123456:token-de-prueba", TELEGRAM_WEBHOOK_SECRET_JUAN: SECRETO } as Env;

function tg() {
  const llamadas: { metodo: string; cuerpo: Record<string, any> | null }[] = [];
  let id = 300;
  const f: typeof fetch = async (recurso, init) => {
    const metodo = String(recurso).split("/").pop()!.split("?")[0];
    llamadas.push({ metodo, cuerpo: init?.body ? JSON.parse(String(init.body)) : null });
    return Response.json({ ok: true, result: { message_id: ++id } });
  };
  return { adaptador: crearTelegram({ fetch: f, dormir: async () => {} }), llamadas };
}

const peticion = (cuerpo: unknown) =>
  new Request("https://juan.example/webhooks/telegram", { method: "POST", headers: { "content-type": "application/json", "x-telegram-bot-api-secret-token": SECRETO }, body: JSON.stringify(cuerpo) });

const mensaje = (extra: Record<string, unknown>): TgUpdate => ({
  update_id: 1,
  message: { message_id: 20, from: { id: 555, first_name: "Cliente" }, chat: { id: 555, type: "private" }, date: 1_790_000_000, text: "este", ...extra },
});

describe("citas y reenviados", () => {
  it("el cliente responde a un mensaje del bot: el id y el texto del citado viajan con el mensaje", async () => {
    const { adaptador } = tg();
    const r = await adaptador.recibir(
      peticion(mensaje({ reply_to_message: { message_id: 18, from: { id: 999, first_name: "Juan", is_bot: true }, chat: { id: 555, type: "private" }, date: 1_789_999_000, text: "Tenemos la Cama Queen Milán y la Cama Roble" } })),
      env,
    );
    expect(r.entrantes[0]).toMatchObject({ id_mensaje: "tg:555:20", texto: "este", cita: { id: "tg:555:18", texto: "Tenemos la Cama Queen Milán y la Cama Roble", deLaTienda: true } });
  });

  it("si eligió un pedazo del citado (quote), vale ese pedazo; una foto sin pie se cita como «Foto»", async () => {
    const { adaptador } = tg();
    const conPedazo = await adaptador.recibir(
      peticion(mensaje({ quote: { text: "la Cama Roble" }, reply_to_message: { message_id: 18, from: { id: 999, is_bot: true }, chat: { id: 555, type: "private" }, date: 1, text: "Tenemos la Cama Queen Milán y la Cama Roble" } })),
      env,
    );
    expect(conPedazo.entrantes[0].cita?.texto).toBe("la Cama Roble");
    const foto = await adaptador.recibir(peticion(mensaje({ reply_to_message: { message_id: 10, from: { id: 555 }, chat: { id: 555, type: "private" }, date: 1, photo: [{ file_id: "F", width: 90, height: 90 }] } })), env);
    expect(foto.entrantes[0].cita).toEqual({ id: "tg:555:10", texto: "Foto", deLaTienda: false });
  });

  it("forward_origin (o el viejo forward_date) = reenviado", async () => {
    const { adaptador } = tg();
    const a = await adaptador.recibir(peticion(mensaje({ text: "mira", forward_origin: { type: "user" } })), env);
    const b = await adaptador.recibir(peticion(mensaje({ text: "mira", forward_date: 1_789_000_000 })), env);
    expect([a.entrantes[0].reenviado, b.entrantes[0].reenviado]).toEqual(["una", "una"]);
  });
});

describe("reacciones (message_reaction)", () => {
  const reaccion = (nueva: unknown[], extra: Record<string, unknown> = {}) => ({
    update_id: 2,
    message_reaction: { chat: { id: 555, type: "private" }, message_id: 18, user: { id: 555, first_name: "Cliente" }, date: 1_790_000_100, old_reaction: [], new_reaction: nueva, ...extra },
  });

  it("poner y quitar: un evento (nunca un mensaje) con el último emoji; vacía = la quitó", async () => {
    const { adaptador } = tg();
    const puso = await adaptador.recibir(peticion(reaccion([{ type: "emoji", emoji: "👍" }])), env);
    expect(puso.entrantes).toEqual([]);
    expect(puso.eventos).toEqual([{ tipo: "reaccion", canal: "telegram", id_externo: "555", id_mensaje: "tg:555:18", emoji: "👍", ts: 1_790_000_100_000 }]);
    const quito = await adaptador.recibir(peticion(reaccion([])), env);
    expect(quito.eventos?.[0]).toMatchObject({ emoji: "" });
  });

  it("de un grupo, de un bot o solo con emojis propios: se ignora", async () => {
    const { adaptador } = tg();
    for (const u of [reaccion([{ type: "emoji", emoji: "👍" }], { chat: { id: -1, type: "group" } }), reaccion([{ type: "emoji", emoji: "👍" }], { user: { id: 1, is_bot: true } }), reaccion([{ type: "custom_emoji", custom_emoji_id: "123" }])]) {
      const r = await adaptador.recibir(peticion(u), env);
      expect(r.respuesta.status).toBe(200);
      expect(r.eventos).toBeUndefined();
      expect(r.entrantes).toEqual([]);
    }
  });
});

describe("«Responder» desde Odoo", () => {
  it("el primer mensaje lleva reply_parameters (sale aunque el citado ya no exista); los demás no", async () => {
    const { adaptador, llamadas } = tg();
    await adaptador.enviar("telegram", { para: "555", burbujas: ["Sí, esa misma", "¿Algo más?"], medios: [{ tipo: "imagen", url: "https://dcasapty.com/a.jpg" }], responderA: "tg:555:20" }, env);
    expect(llamadas.map((l) => l.cuerpo?.reply_parameters)).toEqual([{ message_id: 20, allow_sending_without_reply: true }, undefined, undefined]);
  });

  it("un id de otro chat o de otro canal no se usa", async () => {
    const { adaptador, llamadas } = tg();
    await adaptador.enviar("telegram", { para: "555", burbujas: ["Hola"], medios: [], responderA: "tg:777:20" }, env);
    await adaptador.enviar("telegram", { para: "555", burbujas: ["Hola"], medios: [], responderA: "wamid.X" }, env);
    expect(llamadas.every((l) => l.cuerpo?.reply_parameters === undefined)).toBe(true);
  });
});
