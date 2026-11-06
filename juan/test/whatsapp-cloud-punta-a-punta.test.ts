/**
 * WhatsApp Cloud (el WhatsApp de la tienda desde el 2026-11-02) de punta a punta, con las clases REALES (Worker, Conversacion,
 * Global) sobre Durable Objects de mentira. Lo que se prueba: Meta solo reintenta lo que no recibió 200, así que el 200 sale cuando
 * el mensaje ya está guardado en el Durable Object; lo que se guardó se atiende aunque el Worker muera después de contestar, y
 * un reintento de Meta (el mismo `wamid`) nunca se contesta dos veces.
 * Solo el exterior es de mentira: `fetch` (Graph API de Meta y Claude), el service binding DCASA (Odoo) y el reloj.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import worker from "../src/index";
import type { Entrante } from "../src/canales/tipos";
import { olvidarCaches } from "../src/odoo/fabrica";
import { hmacHex } from "../src/seguridad";
import { armarCluster, dcasaFalso } from "./helpers/doFalso";

const INICIO = Date.parse("2026-10-09T15:00:00Z"); // viernes, 10:00 en Panamá
const SECRETO_APP = "secreto-de-la-app-de-meta-0123456789";
const NUMERO = "109876543210";
const CLIENTE = "50760261919";
const CONV = `whatsapp_cloud:${CLIENTE}`;
const RESPUESTA_IA = "Claro, ¿qué medida de cama buscas?";
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

interface Salida {
  api: "graph" | "claude";
  url: string;
  metodo: string;
  cuerpo: any;
}
let salidas: Salida[];

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
  salidas = [];
  vi.stubGlobal("fetch", async (recurso: unknown, init?: RequestInit) => {
    const url = String(recurso);
    const cuerpo = init?.body && typeof init.body === "string" ? JSON.parse(init.body) : undefined;
    if (url.startsWith("https://graph.facebook.com/")) {
      salidas.push({ api: "graph", url, metodo: init?.method ?? "GET", cuerpo });
      if (url.endsWith(`/${NUMERO}/messages`)) return Response.json({ messages: [{ id: `wamid.OUT${salidas.length}` }] });
      if (url.endsWith("/MEDIA1")) return Response.json({ url: "https://graph.facebook.com/descarga/MEDIA1", mime_type: "image/jpeg" });
      if (url.endsWith("/descarga/MEDIA1")) return new Response(new Uint8Array([9, 8, 7]), { headers: { "content-type": "image/jpeg" } });
      return new Response("no", { status: 404 });
    }
    if (url.startsWith("https://api.anthropic.com/")) {
      salidas.push({ api: "claude", url, metodo: "POST", cuerpo });
      return Response.json({
        id: "msg_1",
        type: "message",
        role: "assistant",
        model: cuerpo.model,
        content: [{ type: "text", text: RESPUESTA_IA }],
        stop_reason: "end_turn",
        stop_sequence: null,
        usage: { input_tokens: 1200, output_tokens: 40, cache_creation_input_tokens: 0, cache_read_input_tokens: 0 },
      });
    }
    throw new Error(`salida a la red no esperada: ${url}`);
  });
  vi.spyOn(console, "error").mockImplementation(() => {});
  vi.spyOn(console, "warn").mockImplementation(() => {});
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
  /** Crea (si hace falta) el Durable Object de la conversación y lo devuelve, para mirarlo o ponerle una falla. */
  const objeto = async () => {
    const ns = cluster.env.CONVERSACION as unknown as { get(id: unknown): { resumen(): Promise<unknown> }; idFromName(n: string): unknown };
    await ns.get(ns.idFromName(CONV)).resumen();
    return cluster.conversaciones.get(CONV)!;
  };
  const filas = async (tabla: "bandeja" | "mensajes", id: string) =>
    (await objeto()).ctx.storage.sql.exec(`SELECT id_mensaje FROM ${tabla} WHERE id_mensaje = ?`, id).toArray().length;
  /** El POST de Meta, firmado con la clave de la app. Devuelve la respuesta del Worker SIN correr lo de después (waitUntil). */
  const webhook = async (mensaje: object) => {
    const crudo = JSON.stringify({
      object: "whatsapp_business_account",
      entry: [{ id: "WABA", changes: [{ field: "messages", value: { contacts: [{ profile: { name: "Karen" }, wa_id: CLIENTE }], messages: [mensaje] } }] }],
    });
    return pedir(new Request("https://juan.example/webhooks/whatsapp-cloud", { method: "POST", headers: { "x-hub-signature-256": `sha256=${await hmacHex(SECRETO_APP, crudo)}` }, body: crudo }));
  };
  const texto = (id: string, cuerpo = "Hola, busco una cama queen") => ({ from: CLIENTE, id, timestamp: String(Math.floor(Date.now() / 1000)), type: "text", text: { body: cuerpo } });
  /** Lo de después del 200 (ctx.waitUntil) y las alarmas que ya vencieron (la cola de Odoo). */
  const despues = async () => {
    await conReloj(ctx.esperar());
    await conReloj(cluster.correrAlarmas(CONV));
  };
  const pasar = async (ms: number) => {
    await vi.advanceTimersByTimeAsync(ms);
    await conReloj(cluster.correrAlarmas(CONV));
  };
  const respuestasDeLaIA = () => salidas.filter((s) => s.api === "graph" && s.metodo === "POST" && s.cuerpo?.text?.body === RESPUESTA_IA);
  const delCliente = () => odoo.mensajes().filter((m) => m.autor === "cliente");
  return { odoo, cluster, ctx, objeto, filas, webhook, texto, despues, pasar, respuestasDeLaIA, delCliente };
}

describe("WhatsApp Cloud: el 200 sale con el mensaje ya guardado", () => {
  it("en el momento del 200 el mensaje ya está en el Durable Object; después se registra en Odoo y se contesta UNA vez", async () => {
    const e = escenario();
    const conv = await e.objeto();
    // Lo de después del 200 queda frenado, para mirar el Durable Object justo cuando Meta recibe la respuesta.
    let soltar!: () => void;
    const frenado = new Promise<void>((r) => (soltar = r));
    const ingestReal = conv.instancia.ingest.bind(conv.instancia);
    conv.instancia.ingest = async (x: Entrante) => (await frenado, ingestReal(x));

    const res = await e.webhook(e.texto("wamid.A"));
    expect(res.status).toBe(200);
    expect(await e.filas("bandeja", "wamid.A")).toBe(1); // guardado (SQLite del objeto) ANTES del 200
    expect(e.delCliente()).toEqual([]); // y todavía no atendido: eso es lo lento, va después

    soltar();
    await e.despues();
    expect(await e.filas("bandeja", "wamid.A")).toBe(0);
    expect(await e.filas("mensajes", "wamid.A")).toBe(1);
    expect(e.delCliente().map((m) => [m.canal, m.id_externo, m.id_mensaje])).toEqual([["whatsapp_cloud", CLIENTE, "wamid.A"]]);
    await e.pasar(16_000); // la ráfaga
    expect(e.respuestasDeLaIA()).toHaveLength(1);
  });

  it("Meta reintenta el mismo mensaje (antes y después de contestarlo): un solo registro en Odoo y UNA sola respuesta", async () => {
    const e = escenario();
    expect((await e.webhook(e.texto("wamid.B"))).status).toBe(200);
    expect((await e.webhook(e.texto("wamid.B"))).status).toBe(200); // Meta no oyó el primer 200
    await e.despues();
    await e.pasar(16_000);
    expect((await e.webhook(e.texto("wamid.B"))).status).toBe(200); // y otra vez, ya contestado
    await e.despues();
    await e.pasar(5 * 60_000);
    expect(e.delCliente().map((m) => m.id_mensaje)).toEqual(["wamid.B"]);
    expect(salidas.filter((s) => s.api === "claude")).toHaveLength(1);
    expect(e.respuestasDeLaIA()).toHaveLength(1);
  });

  it("si el Worker muere después del 200 (lo de después no llega a atenderlo), a los 2 minutos lo atiende la alarma, una vez", async () => {
    const e = escenario();
    const conv = await e.objeto();
    const ingestReal = conv.instancia.ingest.bind(conv.instancia);
    let caidas = 1;
    conv.instancia.ingest = async (x: Entrante) => {
      if (caidas-- > 0) throw new Error("el Worker se reinició a mitad");
      return ingestReal(x);
    };
    expect((await e.webhook(e.texto("wamid.C"))).status).toBe(200);
    await e.despues();
    expect(e.delCliente()).toEqual([]); // se perdía: Meta ya tenía su 200 y no reintenta
    expect(await e.filas("bandeja", "wamid.C")).toBe(1);

    await e.pasar(2 * 60_000);
    await e.pasar(16_000);
    expect(e.delCliente().map((m) => m.id_mensaje)).toEqual(["wamid.C"]);
    expect(e.respuestasDeLaIA()).toHaveLength(1);
    expect(await e.filas("bandeja", "wamid.C")).toBe(0);
  });

  it("si el Durable Object no pudo guardarlo: 500, Meta reintenta, entra y se contesta una vez", async () => {
    const e = escenario();
    const conv = await e.objeto();
    const guardarReal = conv.instancia.guardarRecibido.bind(conv.instancia);
    let fallas = 1;
    conv.instancia.guardarRecibido = async (x: Entrante) => {
      if (fallas-- > 0) throw new Error("el Durable Object no respondió");
      return guardarReal(x);
    };
    expect((await e.webhook(e.texto("wamid.D"))).status).toBe(500);
    await e.despues();
    expect(e.delCliente()).toEqual([]);
    expect((await e.webhook(e.texto("wamid.D"))).status).toBe(200); // el reintento de Meta
    await e.despues();
    await e.pasar(16_000);
    expect(e.delCliente().map((m) => m.id_mensaje)).toEqual(["wamid.D"]);
    expect(e.respuestasDeLaIA()).toHaveLength(1);
  });

  it("una foto que el Worker no alcanzó a bajar: el Durable Object la pide a Meta con el media_id y queda para Odoo", async () => {
    const e = escenario();
    const conv = await e.objeto();
    const ingestReal = conv.instancia.ingest.bind(conv.instancia);
    let caidas = 1;
    conv.instancia.ingest = async (x: Entrante) => {
      if (caidas-- > 0) throw new Error("el Worker se reinició a mitad");
      return ingestReal(x);
    };
    const foto = { from: CLIENTE, id: "wamid.E", timestamp: String(Math.floor(Date.now() / 1000)), type: "image", image: { id: "MEDIA1", caption: "así la quiero", mime_type: "image/jpeg" } };
    expect((await e.webhook(foto)).status).toBe(200);
    await e.despues();
    const bajadasAntes = salidas.filter((s) => s.url.endsWith("/descarga/MEDIA1")).length;

    await e.pasar(2 * 60_000);
    expect(salidas.filter((s) => s.url.endsWith("/descarga/MEDIA1")).length).toBe(bajadasAntes + 1);
    const [registro] = e.delCliente();
    expect(registro).toMatchObject({ id_mensaje: "wamid.E", texto: "así la quiero" });
    expect(registro.adjuntos[0].url).toMatch(/^https:\/\/juan\.example\/media\//);
  });
});
