/**
 * WhatsApp Cloud de punta a punta (clases REALES del Worker y de los Durable Objects): palomitas, reacciones y citas (2026-11-07).
 *   · Un aviso de Meta con solo palomitas o reacciones: 200 enseguida, ningún turno de IA, nada en la conversación del bot; las
 *     palomitas van a Odoo en UNA tanda después del 200.
 *   · Odoo caído para un aviso de solo palomitas: igual 200 (perder una palomita no es perder un mensaje; ver src/eventos.ts).
 *   · Un Odoo viejo (sin /eventos): 200 y no se insiste.
 *   · Un mensaje con cita en el mismo aviso que una palomita: el mensaje se guarda ANTES del 200 (Desplegar 49 sigue en pie).
 * Solo el exterior es de mentira: `fetch` (Graph API de Meta y Claude), el binding DCASA (Odoo) y el reloj.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import worker from "../src/index";
import type { Entrante } from "../src/canales/tipos";
import { olvidarCaches } from "../src/odoo/fabrica";
import { hmacHex } from "../src/seguridad";
import { armarCluster, dcasaFalso } from "./helpers/doFalso";

const INICIO = Date.parse("2026-10-09T15:00:00Z");
const SECRETO_APP = "secreto-de-la-app-de-meta-0123456789";
const NUMERO = "109876543210";
const CLIENTE = "50760001111";
const CONV = `whatsapp_cloud:${CLIENTE}`;
const RESPUESTA_IA = "Claro, la Cama Roble la tenemos.";
const SECRETOS: Record<string, unknown> = {
  JUAN_ODOO_TOKEN: "token-de-odoo-0123456789abcdef",
  JUAN_WORKER_TOKEN: "token-del-worker-0123456789abcdef",
  ANTHROPIC_API_KEY: "sk-ant-clave-de-prueba-0123456789",
  META_APP_SECRET: SECRETO_APP,
  META_VERIFY_TOKEN: "verificacion-de-prueba-0123456789",
  WHATSAPP_CLOUD_TOKEN: "token-cloud-de-prueba-0123456789",
  WHATSAPP_PHONE_NUMBER_ID: NUMERO,
  URL_PUBLICA: "https://juan.example",
};

let llamadasIA: any[];
let enviosMeta: any[];

const ctxFalso = () => {
  const pendientes: Promise<unknown>[] = [];
  return { waitUntil: (p: Promise<unknown>) => void pendientes.push(p), passThroughOnException() {}, esperar: () => Promise.all(pendientes) } as unknown as ExecutionContext & { esperar(): Promise<unknown> };
};

async function conReloj<T>(trabajo: Promise<T>): Promise<T> {
  let listo = false;
  const fin = trabajo.then(
    (v) => ((listo = true), v),
    (e) => {
      listo = true;
      throw e;
    },
  );
  fin.catch(() => {});
  while (!listo) await vi.advanceTimersByTimeAsync(250);
  return fin;
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date", "setTimeout", "clearTimeout"] });
  vi.setSystemTime(INICIO);
  olvidarCaches();
  llamadasIA = [];
  enviosMeta = [];
  vi.stubGlobal("fetch", async (recurso: unknown, init?: RequestInit) => {
    const url = String(recurso);
    const cuerpo = init?.body && typeof init.body === "string" ? JSON.parse(init.body) : undefined;
    if (url.endsWith(`/${NUMERO}/messages`)) {
      enviosMeta.push(cuerpo);
      return Response.json({ messages: [{ id: `wamid.OUT${enviosMeta.length}` }] });
    }
    if (url.startsWith("https://api.anthropic.com/")) {
      llamadasIA.push(cuerpo);
      return Response.json({
        id: "msg_1", type: "message", role: "assistant", model: cuerpo.model,
        content: [{ type: "text", text: RESPUESTA_IA }], stop_reason: "end_turn", stop_sequence: null,
        usage: { input_tokens: 1200, output_tokens: 40, cache_creation_input_tokens: 0, cache_read_input_tokens: 0 },
      });
    }
    throw new Error(`salida a la red no esperada: ${url}`);
  });
  vi.spyOn(console, "error").mockImplementation(() => {});
  vi.spyOn(console, "warn").mockImplementation(() => {});
  vi.spyOn(console, "info").mockImplementation(() => {});
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function escenario() {
  const odoo = dcasaFalso();
  odoo.estado.config = { ...odoo.estado.config, canales_activos: { whatsapp_cloud: true } };
  const cluster = armarCluster({ ...SECRETOS, DCASA: odoo.fetcher, ENTORNO: "staging", VERSION: "t3st" } as any);
  const ctx = ctxFalso();
  const pedir = (req: Request) => conReloj(worker.fetch(req, cluster.env, ctx));
  const aviso = async (value: object) => {
    const crudo = JSON.stringify({ object: "whatsapp_business_account", entry: [{ id: "WABA", changes: [{ field: "messages", value: { messaging_product: "whatsapp", metadata: { phone_number_id: NUMERO }, ...value } }] }] });
    return pedir(new Request("https://juan.example/webhooks/whatsapp-cloud", { method: "POST", headers: { "x-hub-signature-256": `sha256=${await hmacHex(SECRETO_APP, crudo)}` }, body: crudo }));
  };
  const ts = () => String(Math.floor(Date.now() / 1000));
  const recibo = (id: string, status: string) => ({ id, status, timestamp: ts(), recipient_id: CLIENTE });
  const despues = async () => {
    await conReloj(ctx.esperar());
    await conReloj(cluster.correrAlarmas(CONV));
  };
  const pasar = async (ms: number) => {
    await vi.advanceTimersByTimeAsync(ms);
    await conReloj(cluster.correrAlarmas(CONV));
  };
  const eventosEnOdoo = () => odoo.peticiones.filter((p) => p.ruta === "/eventos");
  return { odoo, cluster, ctx, aviso, recibo, ts, despues, pasar, eventosEnOdoo };
}

describe("palomitas y reacciones: nunca un mensaje del cliente", () => {
  it("un aviso de solo palomitas: 200, ninguna conversación ni turno de IA, y UNA llamada a Odoo con las tres", async () => {
    const e = escenario();
    const res = await e.aviso({ statuses: [e.recibo("wamid.OUT1", "sent"), e.recibo("wamid.OUT1", "delivered"), e.recibo("wamid.OUT1", "read")] });
    expect(res.status).toBe(200);
    await e.despues();
    await e.pasar(60_000);
    expect(e.cluster.conversaciones.has(CONV)).toBe(false); // ni siquiera se despertó el Durable Object
    expect(llamadasIA).toEqual([]);
    expect(e.odoo.mensajes()).toEqual([]);
    expect(e.eventosEnOdoo()).toHaveLength(1);
    expect(e.eventosEnOdoo()[0].cuerpo.eventos.map((x: any) => x.estado)).toEqual(["enviado", "entregado", "leido"]);
    expect(e.eventosEnOdoo()[0].cuerpo.eventos[0]).toMatchObject({ tipo: "estado", canal: "whatsapp_cloud", id_externo: CLIENTE, id_mensaje: "wamid.OUT1" });
    expect(e.eventosEnOdoo()[0].auth).toBe(`Bearer ${SECRETOS.JUAN_ODOO_TOKEN}`);
  });

  it("una reacción del cliente: ningún turno de IA, no cuenta como mensaje, va a Odoo como evento", async () => {
    const e = escenario();
    const res = await e.aviso({ contacts: [{ profile: { name: "Cliente de Prueba" }, wa_id: CLIENTE }], messages: [{ from: CLIENTE, id: "wamid.RX", timestamp: e.ts(), type: "reaction", reaction: { message_id: "wamid.OUT1", emoji: "❤️" } }] });
    expect(res.status).toBe(200);
    await e.despues();
    await e.pasar(5 * 60_000);
    expect(llamadasIA).toEqual([]);
    expect(enviosMeta).toEqual([]);
    expect(e.odoo.mensajes()).toEqual([]);
    expect(e.eventosEnOdoo()[0].cuerpo.eventos).toEqual([{ tipo: "reaccion", canal: "whatsapp_cloud", id_externo: CLIENTE, id_mensaje: "wamid.OUT1", emoji: "❤️", ts: new Date(INICIO).toISOString() }]);
  });

  it("una reacción no abre la ventana de 24 h ni frena un seguimiento: el Durable Object no se entera", async () => {
    const e = escenario();
    await e.aviso({ messages: [{ from: CLIENTE, id: "wamid.H", timestamp: e.ts(), type: "text", text: { body: "Hola" } }] });
    await e.despues();
    await e.pasar(16_000);
    const conv = e.cluster.conversaciones.get(CONV)!;
    const antes = conv.ctx.storage.sql.exec("SELECT v FROM kv WHERE k = 'ultimo_cliente_ts'").toArray();
    const mensajesAntes = conv.ctx.storage.sql.exec("SELECT COUNT(*) AS n FROM mensajes").toArray();
    await e.pasar(3600_000);
    await e.aviso({ messages: [{ from: CLIENTE, id: "wamid.RX2", timestamp: e.ts(), type: "reaction", reaction: { message_id: "wamid.OUT1", emoji: "👍" } }] });
    await e.despues();
    expect(conv.ctx.storage.sql.exec("SELECT v FROM kv WHERE k = 'ultimo_cliente_ts'").toArray()).toEqual(antes);
    expect(conv.ctx.storage.sql.exec("SELECT COUNT(*) AS n FROM mensajes").toArray()).toEqual(mensajesAntes);
    expect(llamadasIA).toHaveLength(1); // solo el «Hola»
  });

  it("Odoo caído para un aviso de solo palomitas: Meta recibe 200 igual (y se reintenta un poco por si despertaba)", async () => {
    const e = escenario();
    e.odoo.estado.eventos = () => new Response("Odoo dormido", { status: 503 });
    const res = await e.aviso({ statuses: [e.recibo("wamid.OUT1", "delivered")] });
    expect(res.status).toBe(200);
    await e.despues();
    expect(e.eventosEnOdoo()).toHaveLength(3); // el intento y dos reintentos (2 s y 6 s), dentro de lo que dura waitUntil
  });

  it("Odoo despertando: el reintento entrega la palomita", async () => {
    const e = escenario();
    let dormido = true;
    e.odoo.estado.eventos = (c) => (dormido ? ((dormido = false), new Response("arrancando", { status: 503 })) : Response.json({ ok: true, aplicados: c.eventos.length, desconocidos: [] }));
    expect((await e.aviso({ statuses: [e.recibo("wamid.OUT1", "read")] })).status).toBe(200);
    await e.despues();
    expect(e.eventosEnOdoo()).toHaveLength(2);
  });

  it("un Odoo viejo (sin /eventos): 200 y una sola llamada (no se insiste)", async () => {
    const e = escenario();
    e.odoo.estado.eventos = null;
    expect((await e.aviso({ statuses: [e.recibo("wamid.OUT1", "read")] })).status).toBe(200);
    await e.despues();
    expect(e.eventosEnOdoo()).toHaveLength(1);
  });

  it("la palomita de un mensaje que Odoo todavía no registró: se vuelve a mandar (la respuesta de Juan se registra en paralelo)", async () => {
    const e = escenario();
    let conocido = false;
    e.odoo.estado.eventos = (c) => Response.json({ ok: true, aplicados: conocido ? 1 : 0, desconocidos: conocido ? [] : c.eventos.map((x: any) => x.id_mensaje) });
    expect((await e.aviso({ statuses: [e.recibo("wamid.OUT9", "sent")] })).status).toBe(200);
    setTimeout(() => (conocido = true), 3000);
    await e.despues();
    expect(e.eventosEnOdoo()).toHaveLength(2);
  });
});

describe("citas de punta a punta", () => {
  it("el cliente cita la respuesta de Juan: el mensaje se guarda antes del 200 (con su palomita en el mismo aviso) y el modelo ve lo citado", async () => {
    const e = escenario();
    await e.aviso({ contacts: [{ profile: { name: "Cliente de Prueba" }, wa_id: CLIENTE }], messages: [{ from: CLIENTE, id: "wamid.P1", timestamp: e.ts(), type: "text", text: { body: "¿Tienen camas de roble?" } }] });
    await e.despues();
    await e.pasar(16_000);
    await e.despues();
    // Juan contestó (bienvenida + respuesta) y Odoo recibió los ids de cada burbuja.
    const delBot = e.odoo.mensajes().find((m) => m.autor === "bot");
    expect(delBot.partes.map((p: any) => p.id_canal)).toEqual(enviosMeta.map((_c, i) => `wamid.OUT${i + 1}`));
    const citado = delBot.partes.find((p: any) => p.texto === RESPUESTA_IA).id_canal;

    const conv = e.cluster.conversaciones.get(CONV)!;
    let soltar!: () => void;
    const frenado = new Promise<void>((r) => (soltar = r));
    const ingestReal = conv.instancia.ingest.bind(conv.instancia);
    conv.instancia.ingest = async (x: Entrante) => (await frenado, ingestReal(x));
    const res = await e.aviso({
      contacts: [{ profile: { name: "Cliente de Prueba" }, wa_id: CLIENTE }],
      messages: [{ context: { from: "50760261919", id: citado }, from: CLIENTE, id: "wamid.ESTE", timestamp: e.ts(), type: "text", text: { body: "esta" } }],
      statuses: [e.recibo(citado, "read")],
    });
    expect(res.status).toBe(200);
    expect(conv.ctx.storage.sql.exec("SELECT id_mensaje FROM bandeja WHERE id_mensaje = 'wamid.ESTE'").toArray()).toHaveLength(1); // guardado ANTES del 200
    soltar();
    await e.despues();
    await e.pasar(16_000);
    expect(e.odoo.mensajes().find((m) => m.id_mensaje === "wamid.ESTE").cita).toEqual({ id_canal: citado });
    const ultima = JSON.stringify(llamadasIA.at(-1));
    expect(ultima).toContain(`[El cliente responde a este mensaje de D'CASA: «${RESPUESTA_IA}»]`);
    expect(e.eventosEnOdoo().at(-1)!.cuerpo.eventos[0]).toMatchObject({ estado: "leido", id_mensaje: citado });
  });
});
