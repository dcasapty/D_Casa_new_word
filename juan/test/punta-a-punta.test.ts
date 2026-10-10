/**
 * De punta a punta, con las clases REALES (Worker, Conversacion, Global) sobre Durable Objects de mentira:
 * Telegram (webhook con secreto) → ráfaga de 15 s → IA (la API de Claude, falsa) → respuesta por Telegram → todo registrado en Odoo.
 * Solo el exterior es de mentira: `fetch` (Telegram y Claude), el service binding DCASA (Odoo) y el reloj.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import worker from "../src/index";
import { TEXTO_FALLO_TECNICO } from "../src/dcasa/textos";
import { olvidarCaches } from "../src/odoo/fabrica";
import { claveDeConversacion } from "../src/motor/mediosUrl";
import { armarCluster, dcasaFalso } from "./helpers/doFalso";

const INICIO = Date.parse("2026-10-09T15:00:00Z"); // viernes, 10:00 en Panamá
const SECRETOS: Record<string, unknown> = {
  JUAN_ODOO_TOKEN: "token-de-odoo-0123456789abcdef",
  JUAN_WORKER_TOKEN: "token-del-worker-0123456789abcdef",
  TELEGRAM_BOT_TOKEN_JUAN: "123456:token-del-bot-0123456789",
  TELEGRAM_WEBHOOK_SECRET_JUAN: "secreto-del-webhook-0123456789",
  ANTHROPIC_API_KEY: "sk-ant-clave-de-prueba-0123456789",
};
const BOT = SECRETOS.TELEGRAM_BOT_TOKEN_JUAN as string;
const TOKEN_WORKER = SECRETOS.JUAN_WORKER_TOKEN as string;
const TOKEN_ODOO = SECRETOS.JUAN_ODOO_TOKEN as string;

interface Salida {
  api: "telegram" | "claude";
  metodo: string;
  cuerpo: any;
  url: string;
}

let salidas: Salida[];
let claude: (cuerpo: any, n: number) => { texto?: string; estado?: number };
let claudeLlamadas: number;

/** `ctx.waitUntil` de mentira: guarda lo que el Worker deja para después de responder. */
const ctxFalso = () => {
  const pendientes: Promise<unknown>[] = [];
  return { waitUntil: (p: Promise<unknown>) => void pendientes.push(p), passThroughOnException() {}, esperar: () => Promise.all(pendientes) } as unknown as ExecutionContext & { esperar(): Promise<unknown> };
};

/**
 * Con el reloj falso, las pausas entre burbujas (1 s) no pasan solas: se empuja el reloj hasta que lo esperado termina.
 * Así una prueba que normalmente tardaría segundos corre al instante.
 */
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
  claudeLlamadas = 0;
  claude = () => ({ texto: "Claro, ¿qué medida de cama buscas?" });
  vi.stubGlobal("fetch", async (recurso: unknown, init?: RequestInit) => {
    const url = String(recurso);
    const cuerpo = init?.body && typeof init.body === "string" ? JSON.parse(init.body) : undefined;
    if (url.startsWith("https://api.telegram.org/")) {
      salidas.push({ api: "telegram", metodo: url.split("/").pop()!.split("?")[0], cuerpo, url });
      return Response.json({ ok: true, result: { message_id: 1000 + salidas.length } });
    }
    if (url.startsWith("https://api.anthropic.com/")) {
      salidas.push({ api: "claude", metodo: "messages", cuerpo, url });
      const r = claude(cuerpo, claudeLlamadas++);
      if (r.estado) return Response.json({ type: "error", error: { type: "api_error", message: "falla simulada" } }, { status: r.estado });
      return Response.json({
        id: "msg_1",
        type: "message",
        role: "assistant",
        model: cuerpo.model,
        content: [{ type: "text", text: r.texto ?? "" }],
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

function escenario(secretos: Record<string, unknown> = SECRETOS, vars: Record<string, unknown> = {}) {
  const odoo = dcasaFalso();
  const cluster = armarCluster({ ...secretos, DCASA: odoo.fetcher, ENTORNO: "staging", VERSION: "t3st", ...vars } as any);
  const ctx = ctxFalso();
  const pedir = (req: Request) => conReloj(worker.fetch(req, cluster.env, ctx));
  /** Un mensaje del cliente por el webhook; luego, como Cloudflare, corre lo que venció al instante (registrar en Odoo). */
  const telegram = async (texto: string, id = 555, extra: object = {}, mensajeId = Math.floor(Math.random() * 1e9)) => {
    const res = await pedir(
      new Request("https://juan.example/webhooks/telegram", {
        method: "POST",
        headers: { "content-type": "application/json", "x-telegram-bot-api-secret-token": String(secretos.TELEGRAM_WEBHOOK_SECRET_JUAN ?? "") },
        body: JSON.stringify({
          update_id: Math.floor(Math.random() * 1e9),
          message: { message_id: mensajeId, from: { id, first_name: "Karen" }, chat: { id, type: "private" }, date: Math.floor(Date.now() / 1000), text: texto, ...extra },
        }),
      }),
    );
    await conReloj(ctx.esperar());
    await conReloj(cluster.correrAlarmas(`telegram:${id}`));
    return res;
  };
  const desdeOdoo = (ruta: string, cuerpo: unknown, token = String(secretos.JUAN_WORKER_TOKEN)) =>
    pedir(new Request(`https://juan.example${ruta}`, { method: "POST", headers: { "content-type": "application/json", authorization: `Bearer ${token}` }, body: JSON.stringify(cuerpo) }));
  /** Pasa el tiempo y dispara las alarmas que venzan (ráfaga, reintentos, cola de Odoo). */
  const pasar = async (ms: number, nombre = "telegram:555") => {
    await vi.advanceTimersByTimeAsync(ms);
    await conReloj(cluster.correrAlarmas(nombre));
  };
  const vencerRafaga = (nombre = "telegram:555") => pasar(16_000, nombre);
  const textosAlCliente = () => salidas.filter((s) => s.api === "telegram" && s.metodo === "sendMessage" && s.cuerpo.chat_id !== "999").map((s) => s.cuerpo.text as string);
  const alIA = () => salidas.filter((s) => s.api === "claude");
  const cron = async () => {
    const c = ctxFalso();
    await conReloj(worker.scheduled!({ cron: "23 * * * *", scheduledTime: Date.now(), noRetry() {} } as ScheduledController, cluster.env, c));
    await conReloj(c.esperar());
  };
  return { odoo, cluster, ctx, pedir, telegram, desdeOdoo, vencerRafaga, pasar, textosAlCliente, alIA, cron };
}

describe("el primer despliegue: sin ningún secreto el Worker NO se cae", () => {
  it("/health y /salud responden; /salud dice qué NOMBRES faltan; el webhook y /odoo fallan cerrados", async () => {
    const e = escenario({});
    expect((await e.pedir(new Request("https://juan.example/health"))).status).toBe(200);

    const salud = await (await e.pedir(new Request("https://juan.example/salud"))).json<any>();
    expect(salud.ok).toBe(false);
    expect(salud.secretos_faltantes).toEqual(["JUAN_ODOO_TOKEN", "JUAN_WORKER_TOKEN", "ANTHROPIC_API_KEY"]);
    expect(salud.canales.telegram.faltan).toEqual(["TELEGRAM_BOT_TOKEN_JUAN", "TELEGRAM_WEBHOOK_SECRET_JUAN"]);

    expect((await e.telegram("hola")).status).toBe(401);
    expect((await e.desdeOdoo("/odoo/estado", { canal: "telegram", id_externo: "1", estado: "bot" })).status).toBe(503);
    expect(e.odoo.peticiones).toEqual([]);
    expect(e.cluster.conversaciones.size).toBe(0);
  });
});

describe("una conversación completa por Telegram", () => {
  it("el mensaje espera la ráfaga de 15 s y NO se contesta antes", async () => {
    const e = escenario();
    expect((await e.telegram("Hola")).status).toBe(200);
    const conv = e.cluster.conversaciones.get("telegram:555")!;
    expect(conv.ctx.alarma).toBeGreaterThanOrEqual(Date.now() + 13_000);
    expect(conv.ctx.alarma).toBeLessThanOrEqual(Date.now() + 15_000);
    expect(e.textosAlCliente()).toEqual([]);
    expect(e.alIA()).toHaveLength(0);
    // Pero el mensaje YA está en Odoo: el historial no espera a la ráfaga.
    expect(e.odoo.mensajes().map((m) => [m.autor, m.texto])).toEqual([["cliente", "Hola"]]);
  });

  it("si el cliente sigue escribiendo, todo se contesta en UN solo turno de IA", async () => {
    const e = escenario();
    await e.telegram("Hola");
    await e.pasar(5_000);
    await e.telegram("busco una cama");
    await e.pasar(5_000);
    await e.telegram("queen, para mi cuarto");
    expect(e.alIA()).toHaveLength(0);
    await e.vencerRafaga();
    expect(e.alIA()).toHaveLength(1);
    const delCliente = JSON.stringify(e.alIA()[0].cuerpo.messages);
    for (const frase of ["Hola", "busco una cama", "queen, para mi cuarto"]) expect(delCliente).toContain(frase);
  });

  it("al vencer la ráfaga contesta con la IA, se presenta como Juan, y todo queda en Odoo", async () => {
    const e = escenario();
    await e.telegram("Hola, busco una cama queen");
    await e.vencerRafaga();

    // Contestó por Telegram, al chat correcto: primero el saludo de Juan, luego lo que dijo la IA.
    const envios = salidas.filter((s) => s.api === "telegram" && s.metodo === "sendMessage");
    expect(envios.every((x) => x.cuerpo.chat_id === "555" && x.url.includes(BOT))).toBe(true);
    expect(envios[0].cuerpo.text).toBe("Hola, soy Juan de D'CASA.");
    expect(envios[envios.length - 1].cuerpo.text).toBe("Claro, ¿qué medida de cama buscas?");
    expect(envios.filter((x) => /soy Juan de D'CASA/i.test(x.cuerpo.text))).toHaveLength(1);
    expect(envios.some((x) => /asistente|autom[aá]tico|\bbot\b/i.test(x.cuerpo.text))).toBe(false);

    // A Claude le llegó la clave, el prompt de D'CASA y el mensaje del cliente.
    const alModelo = e.alIA()[0];
    expect(JSON.stringify(alModelo.cuerpo)).toContain("fuentes_de_verdad");
    expect(JSON.stringify(alModelo.cuerpo.messages)).toContain("busco una cama queen");
    expect(alModelo.cuerpo.model).toBe("claude-haiku-4-5");

    // Odoo recibió AMBOS lados, siempre con el token, y marcó quién escribió cada uno.
    const regs = e.odoo.mensajes();
    expect(regs[0]).toMatchObject({ canal: "telegram", id_externo: "555", autor: "cliente", direccion: "entrante", texto: "Hola, busco una cama queen" });
    const delBot = regs.slice(1);
    expect(delBot.length).toBeGreaterThan(0);
    expect(delBot.every((m) => m.autor === "bot" && m.direccion === "saliente")).toBe(true);
    expect(delBot.map((m) => m.texto).join("\n")).toContain("Claro, ¿qué medida de cama buscas?");
    expect(e.odoo.peticiones.every((p) => p.auth === `Bearer ${TOKEN_ODOO}`)).toBe(true);
  });

  it("el gasto de IA queda anotado en el Durable Object global (para el tope mensual)", async () => {
    const e = escenario();
    await e.telegram("Hola");
    await e.vencerRafaga();
    const gasto = e.cluster.global!.instancia.gastoMes("2026-10");
    expect(gasto.usd).toBeGreaterThan(0);
    expect(gasto.porModelo.map((m) => m.modelo)).toEqual(["claude-haiku-4-5"]);
    expect(gasto.modelosSinPrecio).toEqual([]); // Haiku tiene tarifa propia: no es una estimación
    const salud = await (await e.pedir(new Request("https://juan.example/odoo/salud", { headers: { authorization: `Bearer ${TOKEN_WORKER}` } }))).json<any>();
    expect(salud.tope_alcanzado).toBe(false);
  });

  it("un reintento de Telegram (el mismo mensaje, casi a la vez) no se atiende dos veces", async () => {
    const e = escenario();
    await Promise.all([e.telegram("Hola", 555, {}, 321), e.telegram("Hola", 555, {}, 321)]);
    await e.vencerRafaga();
    expect(e.odoo.mensajes().filter((m) => m.autor === "cliente")).toHaveLength(1);
    expect(e.alIA()).toHaveLength(1);
  });

  it("dos personas distintas = dos conversaciones separadas", async () => {
    const e = escenario();
    await e.telegram("Hola, soy Ana", 111);
    await e.telegram("Hola, soy Beto", 222);
    expect([...e.cluster.conversaciones.keys()].sort()).toEqual(["telegram:111", "telegram:222"]);
    await e.pasar(16_000, "telegram:111");
    await e.pasar(0, "telegram:222");
    const chats = new Set(salidas.filter((s) => s.api === "telegram" && s.metodo === "sendMessage").map((s) => s.cuerpo.chat_id));
    expect([...chats].sort()).toEqual(["111", "222"]);
    // Cada conversación le habló a la IA con SU mensaje, no con el del otro.
    const alModelo = e.alIA().map((s) => JSON.stringify(s.cuerpo.messages));
    expect(alModelo).toHaveLength(2);
    expect(alModelo.filter((m) => m.includes("soy Ana")).every((m) => !m.includes("soy Beto"))).toBe(true);
  });

  it("si Claude falla, reintenta con calma y, si sigue fallando, avisa con honestidad y pasa a una vendedora", async () => {
    const e = escenario();
    claude = () => ({ estado: 500 });
    await e.telegram("Hola");
    await e.vencerRafaga();
    // Primero reintenta a los 60 s y a los 5 min sin molestar al cliente.
    expect(e.textosAlCliente().join(" ")).not.toContain(TEXTO_FALLO_TECNICO);
    await e.pasar(61_000);
    expect(e.textosAlCliente().join(" ")).not.toContain(TEXTO_FALLO_TECNICO);
    await e.pasar(301_000);
    expect(e.textosAlCliente().join(" ")).toContain(TEXTO_FALLO_TECNICO);
    expect(e.odoo.peticiones.some((p) => p.ruta === "/herramienta" && p.cuerpo.nombre === "pasar_a_vendedora")).toBe(true);
  });

  it("sin la clave de la IA el bot lo dice y pasa la conversación a una vendedora, sin llamar a ninguna API de IA", async () => {
    const { ANTHROPIC_API_KEY: _quitada, ...sinClave } = SECRETOS;
    const e = escenario(sinClave);
    await e.telegram("Hola");
    await e.vencerRafaga();
    expect(e.alIA()).toHaveLength(0);
    expect(e.textosAlCliente().join(" ")).toContain(TEXTO_FALLO_TECNICO);
    expect(e.odoo.peticiones.some((p) => p.ruta === "/herramienta" && p.cuerpo.nombre === "pasar_a_vendedora")).toBe(true);
  });

  it("si Odoo está dormido, los mensajes esperan en la cola y se registran cuando despierta (no se pierden)", async () => {
    const e = escenario();
    e.odoo.estado.caido = true;
    await e.telegram("Hola");
    await e.vencerRafaga();
    // Con Odoo caído y sin herramientas el bot NO contesta de memoria (no hay catálogo ni precios): espera, y nada se registró todavía.
    expect(e.textosAlCliente()).toEqual([]);
    expect(e.odoo.peticiones.every((p) => p.ruta !== "/mensaje" || e.odoo.estado.caido)).toBe(true);

    e.odoo.estado.caido = false;
    const antes = e.odoo.peticiones.length;
    await e.pasar(10 * 60_000);
    const registrados = e.odoo.peticiones.slice(antes).filter((p) => p.ruta === "/mensaje").map((p) => p.cuerpo);
    expect(registrados.some((m) => m.autor === "cliente" && m.texto === "Hola")).toBe(true);
    expect(registrados.some((m) => m.autor === "bot")).toBe(true);
    // Y al despertar Odoo (con sus herramientas) el asistente sí contestó, sin que el cliente tuviera que repetir nada.
    expect(e.textosAlCliente().length).toBeGreaterThan(0);
  });

  it("si Odoo sigue dormido, el asistente no inventa: al agotar los reintentos avisa con honestidad y pasa a una vendedora", async () => {
    const e = escenario();
    e.odoo.estado.caido = true;
    await e.telegram("Hola, ¿cuánto cuesta la cama queen?");
    await e.vencerRafaga();
    await e.pasar(61_000);
    await e.pasar(301_000);
    expect(e.alIA()).toHaveLength(0); // jamás se le preguntó a la IA sin catálogo
    expect(e.textosAlCliente().join(" ")).toContain(TEXTO_FALLO_TECNICO);
    // La nota para la vendedora espera en la cola: sale cuando Odoo despierta.
    e.odoo.estado.caido = false;
    await e.pasar(30 * 60_000);
    expect(e.odoo.peticiones.some((p) => p.ruta === "/herramienta" && p.cuerpo.nombre === "pasar_a_vendedora")).toBe(true);
  });
});

describe("una vendedora toma la conversación desde Odoo", () => {
  const dentroDe3h = () => new Date(Date.now() + 3 * 3600_000).toISOString();

  it("/odoo/enviar escribe al cliente por Telegram sin registrarlo dos veces, y el bot se calla", async () => {
    const e = escenario();
    await e.telegram("Hola");
    await e.vencerRafaga();
    salidas.length = 0;
    const llamadasAntes = e.odoo.peticiones.length;

    // Odoo marca la conversación como humana (así contestaría Odoo en /estado).
    e.odoo.estado.mensaje = { ...e.odoo.estado.mensaje, estado: "humano", bot_activo: false, pausada_hasta: dentroDe3h() };
    expect((await e.desdeOdoo("/odoo/estado", { canal: "telegram", id_externo: "555", estado: "humano", pausada_hasta: dentroDe3h() })).status).toBe(200);
    expect((await e.desdeOdoo("/odoo/enviar", { canal: "telegram", id_externo: "555", autor: "vendedora", texto: "Hola Karen, soy Marisol de D'CASA." })).status).toBe(200);
    expect(e.textosAlCliente()).toEqual(["Hola Karen, soy Marisol de D'CASA."]);
    // Odoo ya tiene ese mensaje (la vendedora lo escribió ahí): el Worker no lo vuelve a registrar.
    await e.pasar(1_000);
    expect(e.odoo.peticiones.slice(llamadasAntes).some((p) => p.ruta === "/mensaje" && p.cuerpo.autor === "vendedora")).toBe(false);

    // El cliente contesta: el bot NO interviene.
    await e.telegram("Gracias Marisol");
    await e.vencerRafaga();
    expect(e.textosAlCliente()).toEqual(["Hola Karen, soy Marisol de D'CASA."]);
    expect(e.alIA()).toHaveLength(0);
  });

  it("devolver la conversación al bot (estado=bot) lo vuelve a poner a contestar", async () => {
    const e = escenario();
    await e.telegram("Hola");
    await e.vencerRafaga();
    e.odoo.estado.mensaje = { ...e.odoo.estado.mensaje, estado: "humano", bot_activo: false, pausada_hasta: dentroDe3h() };
    await e.desdeOdoo("/odoo/estado", { canal: "telegram", id_externo: "555", estado: "humano", pausada_hasta: dentroDe3h() });
    e.odoo.estado.mensaje = { ...e.odoo.estado.mensaje, estado: "bot", bot_activo: true, pausada_hasta: null };
    await e.desdeOdoo("/odoo/estado", { canal: "telegram", id_externo: "555", estado: "bot" });
    salidas.length = 0;
    await e.telegram("¿Siguen abiertos hoy?");
    await e.vencerRafaga();
    expect(e.textosAlCliente().length).toBeGreaterThan(0);
    expect(e.alIA()).toHaveLength(1);
  });
});

describe("archivos del cliente: viajan a Odoo por una URL firmada y temporal", () => {
  it("una nota de voz de Telegram se descarga, se guarda y Odoo la baja de /media sin que nada lleve el token del bot", async () => {
    const e = escenario(SECRETOS, { URL_PUBLICA: "https://juan.example" });
    const base = globalThis.fetch;
    vi.stubGlobal("fetch", async (recurso: unknown, init?: RequestInit) => {
      const url = String(recurso);
      if (url.includes("/getFile?")) return Response.json({ ok: true, result: { file_path: "voice/v1.oga" } });
      if (url.includes("/file/bot")) return new Response(new Uint8Array([4, 5, 6]), { headers: { "content-type": "audio/ogg" } });
      return base(recurso as RequestInfo, init);
    });
    await e.telegram("", 555, { text: undefined, voice: { file_id: "V1", duration: 3, mime_type: "audio/ogg" } });

    const registro = e.odoo.mensajes().find((m) => m.autor === "cliente");
    expect(registro).toBeDefined();
    const adjunto = (registro.adjuntos ?? [])[0];
    expect(adjunto.tipo).toBe("audio");
    expect(adjunto.url).toMatch(new RegExp(`^https://juan\\.example/media/${claveDeConversacion("telegram", "555")}/[a-f0-9]{16,64}\\?exp=\\d+&sig=[a-f0-9]{64}$`));
    expect(JSON.stringify(e.odoo.peticiones)).not.toContain(BOT);

    const u = new URL(adjunto.url);
    const archivo = await e.pedir(new Request(adjunto.url));
    expect(archivo.status).toBe(200);
    expect([...new Uint8Array(await archivo.arrayBuffer())]).toEqual([4, 5, 6]);
    // Con la firma cambiada, no.
    const falso = await e.pedir(new Request(`${u.origin}${u.pathname}?exp=${u.searchParams.get("exp")}&sig=${"0".repeat(64)}`));
    expect(falso.status).toBe(403);

    // Y el modelo jamás ve el archivo ni su URL: ni siquiera se le llama por un mensaje que solo trae un archivo.
    await e.vencerRafaga();
    expect(e.alIA().every((s) => !JSON.stringify(s.cuerpo).includes("/media/"))).toBe(true);
  });
});

describe("el cron de salud avisa UNA vez por problema", () => {
  const conPuente = (conectado: boolean) => ({ WA_TOKEN: "token-del-puente-0123456789abcdef", PUENTE: { fetch: async () => Response.json({ conectado }) } });

  it("avisa por Telegram a la dueña, no repite a la hora siguiente, y avisa cuando se arregla", async () => {
    const { JUAN_WORKER_TOKEN: _w, ...sinTokenDelWorker } = SECRETOS;
    const e = escenario({ ...sinTokenDelWorker, ...conPuente(true) }, { ALERTA_TELEGRAM_CHAT_ID: "999" });
    const avisos = () => salidas.filter((s) => s.api === "telegram" && s.cuerpo?.chat_id === "999").map((s) => s.cuerpo.text as string);

    await e.cron();
    expect(avisos()).toHaveLength(1);
    expect(avisos()[0]).toMatch(/JUAN_WORKER_TOKEN/);
    for (const secreto of [TOKEN_ODOO, BOT]) expect(avisos()[0]).not.toContain(secreto);

    await vi.advanceTimersByTimeAsync(3600_000);
    await e.cron();
    expect(avisos()).toHaveLength(1); // el mismo problema no se repite cada hora

    (e.cluster.env as any).JUAN_WORKER_TOKEN = TOKEN_WORKER;
    await vi.advanceTimersByTimeAsync(3600_000);
    await e.cron();
    expect(avisos()).toHaveLength(2);
    expect(avisos()[1]).toMatch(/Resuelto/);
  });

  it("si el puente de WhatsApp se desconecta (hay que volver a escanear el QR) avisa", async () => {
    const e = escenario({ ...SECRETOS, ...conPuente(false) }, { ALERTA_TELEGRAM_CHAT_ID: "999" });
    await e.cron();
    const avisos = salidas.filter((s) => s.cuerpo?.chat_id === "999").map((s) => s.cuerpo.text as string);
    expect(avisos).toHaveLength(1);
    expect(avisos[0]).toMatch(/whatsapp_qr no está conectado/);
  });

  it("todo en orden: no avisa nada", async () => {
    const e = escenario({ ...SECRETOS, ...conPuente(true) }, { ALERTA_TELEGRAM_CHAT_ID: "999" });
    await e.cron();
    expect(salidas.filter((s) => s.cuerpo?.chat_id === "999")).toEqual([]);
  });

  it("sin chat de alertas configurado no intenta avisar a nadie y no se cae", async () => {
    const e = escenario({});
    await e.cron();
    expect(salidas.filter((s) => s.api === "telegram")).toEqual([]);
  });
});
