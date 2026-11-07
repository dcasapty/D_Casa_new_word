/**
 * Palomitas y reacciones → Odoo (`src/eventos.ts` y su camino por las rutas): una tanda por aviso, reintentos que caben en
 * `waitUntil`, lo desconocido se vuelve a mandar, un Odoo viejo no se insiste, y en Telegram solo los chats permitidos.
 */
import { describe, expect, it } from "vitest";
import { CONFIG_POR_DEFECTO, normalizarConfig, type Config } from "../src/config";
import { crearTelegram } from "../src/canales/telegram";
import type { EventoCanal } from "../src/canales/tipos";
import type { Env } from "../src/env";
import { ESPERAS_SI_ES_DESCONOCIDO_MS, ESPERAS_SI_ODOO_FALLA_MS, entregarEventos } from "../src/eventos";
import { OdooError } from "../src/odoo/cliente";
import { manejar, type ConversacionApi, type DepsRutas } from "../src/rutas";

const estado = (id: string, e: "enviado" | "entregado" | "leido" = "entregado"): EventoCanal => ({ tipo: "estado", canal: "whatsapp_cloud", id_externo: "50760001111", id_mensaje: id, estado: e, ts: 1_790_000_000_000 });

describe("entregarEventos", () => {
  it("una tanda, una llamada", async () => {
    const tandas: EventoCanal[][] = [];
    const r = await entregarEventos([estado("a"), estado("b")], { enviar: async (l) => (tandas.push(l), { aplicados: 2, desconocidos: [] }), dormir: async () => {} });
    expect(tandas).toHaveLength(1);
    expect(r).toEqual({ entregados: 2, perdidos: 0, odooViejo: false });
  });

  it("Odoo no contesta: reintenta con las esperas fijadas y, si sigue caído, las pierde sin lanzar", async () => {
    const esperas: number[] = [];
    const r = await entregarEventos([estado("a")], { enviar: async () => Promise.reject(new OdooError("dormido", 503, true)), dormir: async (ms) => void esperas.push(ms) });
    expect(esperas).toEqual(ESPERAS_SI_ODOO_FALLA_MS);
    expect(r).toEqual({ entregados: 0, perdidos: 1, odooViejo: false });
    // Las esperas caben de sobra en los 30 s de waitUntil (con las llamadas de 6 s como máximo).
    expect(ESPERAS_SI_ODOO_FALLA_MS.reduce((a, b) => a + b, 0) + 3 * 6_000).toBeLessThanOrEqual(30_000);
  });

  it("un Odoo viejo (404): una sola llamada, sin reintentos", async () => {
    let n = 0;
    const r = await entregarEventos([estado("a")], { enviar: async () => (n++, Promise.reject(new OdooError("no", 404, false))), dormir: async () => {} });
    expect(n).toBe(1);
    expect(r.odooViejo).toBe(true);
  });

  it("un 400 de Odoo no se reintenta", async () => {
    let n = 0;
    await entregarEventos([estado("a")], { enviar: async () => (n++, Promise.reject(new OdooError("mal", 400, false))), dormir: async () => {} });
    expect(n).toBe(1);
  });

  it("lo que Odoo no conoce se vuelve a mandar SOLO eso, a lo más dos veces", async () => {
    const tandas: string[][] = [];
    const esperas: number[] = [];
    await entregarEventos([estado("conocido"), estado("nuevo")], {
      enviar: async (l) => (tandas.push(l.map((e) => e.id_mensaje)), { desconocidos: ["nuevo"] }),
      dormir: async (ms) => void esperas.push(ms),
    });
    expect(tandas).toEqual([["conocido", "nuevo"], ["nuevo"], ["nuevo"]]);
    expect(esperas).toEqual(ESPERAS_SI_ES_DESCONOCIDO_MS);
  });
});

describe("las rutas: palomitas y reacciones a Odoo después de contestar", () => {
  const SECRETO_TG = "secreto-telegram-de-prueba";
  const env = { TELEGRAM_BOT_TOKEN_JUAN: "123456:token", TELEGRAM_WEBHOOK_SECRET_JUAN: SECRETO_TG } as unknown as Env;
  const sinConversacion = (): ConversacionApi => {
    throw new Error("una reacción no debe tocar ninguna conversación");
  };

  function montar(config: Config | (() => Promise<Config>)) {
    const enviados: EventoCanal[][] = [];
    const pendientes: Promise<unknown>[] = [];
    const deps: DepsRutas = {
      adaptadores: [crearTelegram({ fetch: async () => new Response("{}"), dormir: async () => {} })],
      config: typeof config === "function" ? config : async () => config,
      conversacion: sinConversacion,
      gastoMes: async () => 0,
      ahora: () => 0,
      esperarDespues: (t) => void pendientes.push(t),
      eventos: async (l) => (enviados.push(l), { aplicados: l.length, desconocidos: [] }),
      dormir: async () => {},
    };
    const reaccion = (chat: number) =>
      new Request("https://juan.example/webhooks/telegram", {
        method: "POST",
        headers: { "content-type": "application/json", "x-telegram-bot-api-secret-token": SECRETO_TG },
        body: JSON.stringify({ update_id: 9, message_reaction: { chat: { id: chat, type: "private" }, message_id: 4, user: { id: chat }, date: 1_790_000_000, old_reaction: [], new_reaction: [{ type: "emoji", emoji: "🔥" }] } }),
      });
    return { enviados, pedir: (chat: number) => manejar(reaccion(chat), env, deps), despues: () => Promise.all(pendientes) };
  }

  const config = normalizarConfig({ ...CONFIG_POR_DEFECTO, canales_activos: { telegram: true }, telegram_chats: ["555"] });

  it("la reacción de un chat permitido llega a Odoo; la de otro chat, no; ninguna toca una conversación", async () => {
    const m = montar(config);
    expect((await m.pedir(555)).status).toBe(200);
    expect((await m.pedir(999)).status).toBe(200);
    await m.despues();
    expect(m.enviados.flat().map((e) => e.id_externo)).toEqual(["555"]);
  });

  it("con el canal apagado en Odoo, o sin poder leer la lista de chats, se sueltan (200 igual)", async () => {
    const apagado = montar(normalizarConfig({ ...config, canales_activos: { telegram: false } }));
    expect((await apagado.pedir(555)).status).toBe(200);
    await apagado.despues();
    expect(apagado.enviados).toEqual([]);
    const sinLista = montar(async () => CONFIG_POR_DEFECTO);
    expect((await sinLista.pedir(555)).status).toBe(200);
    await sinLista.despues();
    expect(sinLista.enviados).toEqual([]);
  });
});
