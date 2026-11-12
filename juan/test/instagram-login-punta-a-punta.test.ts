/**
 * Instagram por «inicio de sesión de Instagram» de punta a punta, con las clases REALES (Worker, Conversacion, Global) sobre Durable
 * Objects de mentira: el mensaje del cliente entra por /webhooks/instagram (firmado con la clave de la app de Instagram), queda en
 * Odoo con su nombre, Juan contesta por graph.instagram.com, el eco de una vendedora queda en Odoo como suyo, el cron renueva la
 * llave y la guarda en el Durable Object `Global`, y /salud dice la puerta y el vencimiento sin mostrar ninguna llave.
 * Solo el exterior es de mentira: `fetch` (Instagram y Claude), el service binding DCASA (Odoo) y el reloj.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import worker from "../src/index";
import { olvidarCaches } from "../src/odoo/fabrica";
import { hmacHex } from "../src/seguridad";
import { armarCluster, dcasaFalso } from "./helpers/doFalso";

const INICIO = Date.parse("2026-11-13T15:00:00Z"); // viernes, 10:00 en Panamá
const SECRETO_IG = "secreto-de-la-app-de-instagram-abcdef0123";
const CUENTA = "17841400000000001";
const CLIENTE = "1234567890123456";
const CONV = `instagram:${CLIENTE}`;
const RESPUESTA_IA = "¡Hola Ana! Sí, tenemos sofás. ¿Para qué espacio lo buscas?";
let vez = 0;

interface Salida {
  api: "instagram" | "claude";
  url: URL;
  metodo: string;
  llave: string;
  cuerpo: any;
}
let salidas: Salida[];
let renovadas: string[];
/** Mientras exista, la renovación espera (Meta tardando). */
let frenoRenovacion: Promise<void> | null;

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
  renovadas = [];
  frenoRenovacion = null;
  vi.stubGlobal("fetch", async (recurso: unknown, init?: RequestInit) => {
    const url = new URL(String(recurso));
    const cuerpo = init?.body && typeof init.body === "string" ? JSON.parse(init.body) : undefined;
    const llave = String((init?.headers as Record<string, string> | undefined)?.authorization ?? url.searchParams.get("access_token") ?? "").replace(/^Bearer /, "");
    if (url.host === "graph.instagram.com") {
      salidas.push({ api: "instagram", url, metodo: init?.method ?? "GET", llave, cuerpo });
      if (url.pathname === "/refresh_access_token") {
        if (frenoRenovacion) await frenoRenovacion;
        const nueva = `IGAArenovada-${renovadas.length + 1}-${"x".repeat(20)}`;
        renovadas.push(nueva);
        return Response.json({ access_token: nueva, token_type: "bearer", expires_in: 5_184_000 });
      }
      if (url.pathname.endsWith("/me") && llave) return Response.json({ user_id: CUENTA, username: "dcasapty", id: "26000000000000001" });
      if (url.pathname.endsWith("/me/messages")) return Response.json({ recipient_id: CLIENTE, message_id: `aWdf_OUT_${salidas.length}` });
      if (url.pathname.endsWith(`/${CLIENTE}`) && url.searchParams.get("fields") === "name,username") return Response.json({ name: "Ana Pérez", username: "ana.pty" });
      return Response.json({ error: { message: "no", code: 100 } }, { status: 400 });
    }
    if (url.host === "api.anthropic.com") {
      salidas.push({ api: "claude", url, metodo: "POST", llave: "", cuerpo });
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
    throw new Error(`salida a la red no esperada: ${url.host}`);
  });
  vi.spyOn(console, "error").mockImplementation(() => {});
  vi.spyOn(console, "warn").mockImplementation(() => {});
  vi.spyOn(console, "log").mockImplementation(() => {});
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function escenario(conInstagram = true) {
  // Una llave distinta en cada escenario: la memoria de 60 s del adaptador es del proceso, como en Cloudflare.
  const tokenIg = `IGAAtoken-pegado-${++vez}-${"0123456789".repeat(2)}`;
  const secretos: Record<string, unknown> = {
    JUAN_ODOO_TOKEN: "token-de-odoo-0123456789abcdef",
    JUAN_WORKER_TOKEN: "token-del-worker-0123456789abcdef",
    ANTHROPIC_API_KEY: "sk-ant-clave-de-prueba-0123456789",
    META_VERIFY_TOKEN: "verificacion-de-prueba-0123456789",
    URL_PUBLICA: "https://juan.example",
    ...(conInstagram ? { INSTAGRAM_TOKEN: tokenIg, INSTAGRAM_APP_SECRET: SECRETO_IG } : {}),
  };
  const odoo = dcasaFalso();
  odoo.estado.config = { ...odoo.estado.config, canales_activos: { instagram: true } };
  const cluster = armarCluster({ ...secretos, DCASA: odoo.fetcher, ENTORNO: "staging", VERSION: "t3st" } as any);
  const ctx = ctxFalso();
  const pedir = (req: Request) => conReloj(worker.fetch(req, cluster.env, ctx));
  const webhook = async (evento: object) => {
    const crudo = JSON.stringify({ object: "instagram", entry: [{ id: CUENTA, time: Math.floor(Date.now() / 1000), messaging: [evento] }] });
    return pedir(new Request("https://juan.example/webhooks/instagram", { method: "POST", headers: { "x-hub-signature-256": `sha256=${await hmacHex(SECRETO_IG, crudo)}` }, body: crudo }));
  };
  const delCliente = (id: string, texto: string) => ({ sender: { id: CLIENTE }, recipient: { id: CUENTA }, timestamp: Date.now(), message: { mid: id, text: texto } });
  const despues = async () => {
    await conReloj(ctx.esperar());
    await conReloj(cluster.correrAlarmas(CONV));
  };
  const pasar = async (ms: number) => {
    await vi.advanceTimersByTimeAsync(ms);
    await conReloj(cluster.correrAlarmas(CONV));
  };
  const cron = async () => {
    const c = ctxFalso();
    await conReloj(worker.scheduled!({ cron: "23 * * * *", scheduledTime: Date.now(), noRetry() {} } as ScheduledController, cluster.env, c));
    await conReloj(c.esperar());
  };
  const salud = async () => (await pedir(new Request("https://juan.example/salud"))).text();
  const respuestasDeLaIA = () => salidas.filter((s) => s.api === "instagram" && s.metodo === "POST" && s.cuerpo?.message?.text === RESPUESTA_IA);
  const llavesGuardadas = () => (cluster.global ? cluster.global.ctx.storage.sql.exec("SELECT clave, valor FROM llaves").toArray() : []);
  return { odoo, cluster, tokenIg, pedir, webhook, delCliente, despues, pasar, cron, salud, respuestasDeLaIA, llavesGuardadas };
}

describe("Instagram por inicio de sesión de Instagram, de punta a punta", () => {
  it("el mensaje del cliente entra, queda en Odoo con su nombre y Juan contesta por graph.instagram.com con la llave de Instagram", async () => {
    const e = escenario();
    expect((await e.webhook(e.delCliente("aWdf_IN_1", "Hola, ¿tienen sofás?"))).status).toBe(200);
    await e.despues();
    const [registro] = e.odoo.mensajes();
    expect(registro).toMatchObject({ canal: "instagram", id_externo: CLIENTE, id_mensaje: "aWdf_IN_1", autor: "cliente", texto: "Hola, ¿tienen sofás?", nombre: "Ana Pérez" });
    await e.pasar(16_000); // la ráfaga
    const [respuesta] = e.respuestasDeLaIA();
    expect(respuesta.url.toString()).toMatch(/^https:\/\/graph\.instagram\.com\/v\d+\.\d+\/me\/messages$/);
    expect(respuesta.llave).toBe(e.tokenIg);
    expect(respuesta.cuerpo).toEqual({ recipient: { id: CLIENTE }, message: { text: RESPUESTA_IA } });
    const delBot = e.odoo.mensajes().filter((m) => m.autor === "bot");
    expect(delBot).toHaveLength(1);
    expect(delBot[0]).toMatchObject({ canal: "instagram", id_externo: CLIENTE });
    expect(delBot[0].texto).toContain(RESPUESTA_IA);
    // La cuenta se le preguntó a Meta una sola vez y quedó guardada en el Durable Object Global.
    expect(salidas.filter((s) => s.url.pathname.endsWith("/me"))).toHaveLength(1);
    expect(e.llavesGuardadas().map((f) => f.clave)).toContain("instagram_cuenta");
  });

  it("lo que una vendedora contesta desde la app de Instagram (eco) queda en Odoo como suyo y el bot se calla", async () => {
    const e = escenario();
    await e.webhook(e.delCliente("aWdf_IN_2", "Hola"));
    await e.despues();
    const eco = { sender: { id: CUENTA }, recipient: { id: CLIENTE }, timestamp: Date.now(), message: { mid: "aWdf_ECO_1", text: "Hola, soy Marisol de D'CASA, te atiendo yo.", is_echo: true } };
    expect((await e.webhook(eco)).status).toBe(200);
    await e.despues();
    await e.pasar(16_000);
    expect(e.odoo.mensajes().filter((m) => m.autor === "vendedora").map((m) => [m.id_mensaje, m.texto])).toEqual([["aWdf_ECO_1", "Hola, soy Marisol de D'CASA, te atiendo yo."]]);
    expect(e.respuestasDeLaIA()).toEqual([]);
  });

  it("el cron renueva la llave al día siguiente, la guarda en el Durable Object Global y Juan contesta con la RENOVADA", async () => {
    const e = escenario();
    await e.cron(); // la primera hora: la anota (y averigua la cuenta)
    expect(renovadas).toEqual([]);
    await vi.advanceTimersByTimeAsync(25 * 3600_000);
    await e.cron();
    expect(renovadas).toHaveLength(1);
    const pedida = salidas.find((s) => s.url.pathname === "/refresh_access_token")!;
    expect(pedida.url.searchParams.get("grant_type")).toBe("ig_refresh_token");
    expect(pedida.llave).toBe(e.tokenIg);
    const guardada = JSON.parse(String(e.llavesGuardadas().find((f) => f.clave === "instagram_llave")!.valor));
    expect(guardada.llave).toBe(renovadas[0]);
    await e.cron(); // otra hora: ya no toca (ni el mismo día ni con 60 días por delante)
    expect(renovadas).toHaveLength(1);

    await e.webhook(e.delCliente("aWdf_IN_3", "¿tienen sofás?"));
    await e.despues();
    await e.pasar(16_000);
    expect(e.respuestasDeLaIA().map((s) => s.llave)).toEqual([renovadas[0]]);
  });

  it("el cron no atrasa el informe de salud (ni los avisos) mientras Meta tarda en renovar la llave", async () => {
    const e = escenario();
    await e.cron();
    await vi.advanceTimersByTimeAsync(25 * 3600_000);
    let soltar!: () => void;
    frenoRenovacion = new Promise<void>((r) => (soltar = r));
    const c = ctxFalso();
    await worker.scheduled!({ cron: "23 * * * *", scheduledTime: Date.now(), noRetry() {} } as ScheduledController, e.cluster.env, c);
    const informeDeAhora = () =>
      e.cluster.global!.ctx.storage.sql.exec("SELECT ts FROM salud WHERE clave = 'ultimo_informe'").toArray().some((f) => Number(f.ts) > INICIO + 24 * 3600_000);
    for (let i = 0; i < 200 && !informeDeAhora(); i++) await vi.advanceTimersByTimeAsync(10);
    expect(informeDeAhora()).toBe(true);
    expect(renovadas).toEqual([]); // la renovación sigue esperando a Meta
    soltar();
    await conReloj(c.esperar());
    expect(renovadas).toHaveLength(1);
  });

  it("/salud (público): Instagram dice su puerta, que no le falta nada y cuándo vence la llave, sin mostrar ninguna llave", async () => {
    const e = escenario();
    await e.cron();
    await vi.advanceTimersByTimeAsync(25 * 3600_000);
    await e.cron();
    const texto = await e.salud();
    for (const secreto of [e.tokenIg, renovadas[0], SECRETO_IG, "token-del-worker", "sk-ant-"]) expect(texto).not.toContain(secreto);
    const j = JSON.parse(texto);
    expect(j.canales.instagram).toEqual({
      activo: true,
      configurado: true,
      faltan: [],
      puerta: "inicio_sesion_instagram",
      llave: { vence: "2027-01-13", vence_seguro: true, dias_restantes: 60, renovada: "2026-11-14", renovacion: "ok" },
      cuenta: "@dcasapty",
    });
    expect(j.canales.messenger.puerta).toBeUndefined();
  });

  it("si falta la clave secreta de la app de Instagram, /salud lo dice por su nombre", async () => {
    const e = escenario();
    delete (e.cluster.env as any).INSTAGRAM_APP_SECRET;
    const j = JSON.parse(await e.salud());
    expect(j.canales.instagram).toMatchObject({ activo: true, configurado: false, faltan: ["INSTAGRAM_APP_SECRET"], puerta: "inicio_sesion_instagram" });
  });

  it("sin los secretos nuevos: /webhooks/instagram no deja pasar nada y /salud dice que Instagram va por la página", async () => {
    const e = escenario(false);
    expect((await e.webhook(e.delCliente("aWdf_IN_4", "hola"))).status).toBe(401);
    await e.despues();
    expect(e.odoo.mensajes()).toEqual([]);
    await e.cron();
    expect(salidas).toEqual([]); // el cron no le habla a Instagram
    const j = JSON.parse(await e.salud());
    expect(j.canales.instagram).toEqual({ activo: true, configurado: false, faltan: ["META_PAGE_TOKEN", "META_APP_SECRET"], puerta: "pagina_facebook" });
  });
});
