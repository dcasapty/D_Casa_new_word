/**
 * Las rutas del Worker, sin Cloudflare: /health, /salud (pública), webhooks de los canales, /media firmado y /odoo/* con token.
 * Las conversaciones son un doble que anota lo que le piden; los adaptadores de Telegram y WhatsApp QR son los de verdad.
 */
import { describe, expect, it, vi } from "vitest";
import type { Env } from "../src/env";
import { CONFIG_POR_DEFECTO, normalizarConfig, type Config } from "../src/config";
import { crearTelegram } from "../src/canales/telegram";
import { crearWhatsappQr } from "../src/canales/whatsappQr";
import type { AdaptadorCanal, CanalId, Entrante } from "../src/canales/tipos";
import { claveDeConversacion, firmarUrlMedio, VIDA_URL_MEDIO_MS } from "../src/motor/mediosUrl";
import { manejar, type ConversacionApi, type DepsRutas } from "../src/rutas";
import { CanalFalso } from "./helpers/canalFalso";

const TOKEN_WORKER = "token-del-worker-de-prueba-0123456789";
const TOKEN_ODOO = "token-de-odoo-de-prueba-0123456789";
const SECRETO_TG = "secreto-telegram-de-prueba";
const BOT_TG = "123456:token-del-bot-de-prueba";
const WA_TOKEN = "token-del-puente-de-prueba-0123456789";
const AHORA = Date.UTC(2026, 9, 9, 15, 0);

const envCompleto = {
  JUAN_WORKER_TOKEN: TOKEN_WORKER,
  JUAN_ODOO_TOKEN: TOKEN_ODOO,
  ANTHROPIC_API_KEY: "sk-ant-de-prueba-0123456789",
  TELEGRAM_BOT_TOKEN_JUAN: BOT_TG,
  TELEGRAM_WEBHOOK_SECRET_JUAN: SECRETO_TG,
  WA_TOKEN,
  PUENTE: {},
  ENTORNO: "staging",
  VERSION: "abc1234",
} as unknown as Env;

class ConversacionDoble implements ConversacionApi {
  ingestados: Entrante[] = [];
  enviados: unknown[] = [];
  estados: unknown[] = [];
  seguimientos: unknown[] = [];
  olvidos = 0;
  medio: { bytes: Uint8Array; mime: string; nombre: string | null } | null = null;
  falla: string | null = null;
  seguimientoResultado: any = { ok: true, resultado: "enviado" };

  async ingest(e: Entrante) {
    if (this.falla) throw new Error(this.falla);
    this.ingestados.push(e);
    return { ok: true as const, accion: "en_espera" as const };
  }
  async enviarVendedora(s: unknown) {
    if (this.falla) throw new Error(this.falla);
    this.enviados.push(s);
    return { ok: true as const, id_mensaje: "m1" };
  }
  async fijarEstado(s: unknown) {
    if (this.falla) throw new Error(this.falla);
    this.estados.push(s);
    return { ok: true as const };
  }
  async seguimiento(s: unknown) {
    this.seguimientos.push(s);
    return this.seguimientoResultado;
  }
  async leerMedio() {
    return this.medio;
  }
  async olvidar() {
    if (this.falla) throw new Error(this.falla);
    this.olvidos++;
    return { ok: true as const, mensajes: 3 };
  }
}

function montar(opciones: { config?: Partial<Config> | Record<string, unknown>; adaptadores?: AdaptadorCanal[]; gasto?: number } = {}) {
  const conv = new ConversacionDoble();
  const pedidas: [CanalId, string][] = [];
  const pendientes: Promise<unknown>[] = [];
  const config = normalizarConfig({ ...CONFIG_POR_DEFECTO, ...opciones.config });
  const deps: DepsRutas = {
    adaptadores: opciones.adaptadores ?? [crearTelegram({ fetch: async () => new Response("{}"), dormir: async () => {} }), crearWhatsappQr({ fetch: async () => new Response("{}") })],
    config: async () => config,
    conversacion: (canal, id) => {
      pedidas.push([canal, id]);
      return conv;
    },
    gastoMes: async () => opciones.gasto ?? 0,
    ahora: () => AHORA,
    esperarDespues: (t) => void pendientes.push(t),
  };
  return {
    conv,
    pedidas,
    deps,
    /** Espera lo que el Worker dejó para después de responder (como `ctx.waitUntil`). */
    async despues() {
      await Promise.all(pendientes);
    },
    pedir: (req: Request, env: Env = envCompleto) => manejar(req, env, deps),
  };
}

const get = (ruta: string, cab: Record<string, string> = {}) => new Request(`https://juan.example${ruta}`, { headers: cab });
const post = (ruta: string, cuerpo: unknown, cab: Record<string, string> = {}) =>
  new Request(`https://juan.example${ruta}`, { method: "POST", headers: { "content-type": "application/json", ...cab }, body: typeof cuerpo === "string" ? cuerpo : JSON.stringify(cuerpo) });
const deOdoo = { authorization: `Bearer ${TOKEN_WORKER}` };

describe("rutas básicas", () => {
  it("/health responde ok, también con barra final", async () => {
    const m = montar();
    for (const r of ["/health", "/health/"]) {
      const res = await m.pedir(get(r), {} as Env);
      expect([res.status, await res.text()]).toEqual([200, "ok"]);
    }
  });

  it("una ruta desconocida: 404", async () => {
    expect((await montar().pedir(get("/admin"))).status).toBe(404);
    expect((await montar().pedir(get("/"))).status).toBe(404);
  });
});

describe("GET /salud (pública)", () => {
  it("con todo cargado: ok, y NINGÚN valor de secreto en la respuesta", async () => {
    const res = await montar().pedir(get("/salud"));
    const texto = await res.text();
    expect(res.status).toBe(200);
    for (const secreto of [TOKEN_WORKER, TOKEN_ODOO, SECRETO_TG, BOT_TG, WA_TOKEN, "sk-ant-de-prueba"]) expect(texto).not.toContain(secreto);
    const j = JSON.parse(texto);
    expect(j.secretos_faltantes).toEqual([]);
    expect(j.entorno).toBe("staging");
    expect(j.version).toBe("abc1234");
    expect(j.ia).toEqual({ proveedor: "anthropic", respaldo: null, lista: true });
  });

  it("un Worker recién desplegado, sin secretos, NO se cae: dice qué NOMBRES faltan", async () => {
    const res = await montar().pedir(get("/salud"), {} as Env);
    expect(res.status).toBe(200);
    const j = await res.json<any>();
    expect(j.ok).toBe(false);
    expect(j.secretos_faltantes).toEqual(["JUAN_ODOO_TOKEN", "JUAN_WORKER_TOKEN", "ANTHROPIC_API_KEY"]);
    expect(j.ia.lista).toBe(false);
    expect(j.mensaje).toMatch(/ANTHROPIC_API_KEY/);
    expect(j.canales.telegram).toEqual({ activo: true, configurado: false, faltan: ["TELEGRAM_BOT_TOKEN_JUAN", "TELEGRAM_WEBHOOK_SECRET_JUAN"] });
    expect(j.canales.whatsapp_cloud.activo).toBe(false);
  });

  it("no muestra gasto, tope ni motivos de fallo (eso es de /odoo/salud)", async () => {
    const j = await (await montar({ gasto: 12.34 }).pedir(get("/salud"))).json<any>();
    expect(j).not.toHaveProperty("gasto_ia_mes_usd");
    expect(j).not.toHaveProperty("tope_usd");
    expect(j).not.toHaveProperty("problemas");
    expect(JSON.stringify(j)).not.toContain("12.34");
  });

  it("solo GET", async () => {
    expect((await montar().pedir(post("/salud", {}))).status).toBe(405);
  });

  it("con otra IA elegida en Odoo, pide la clave de ESA IA", async () => {
    const j = await (await montar({ config: { proveedor_ia: "meta", proveedor_respaldo_ia: "anthropic" } }).pedir(get("/salud"), { JUAN_ODOO_TOKEN: "x", JUAN_WORKER_TOKEN: "y" } as Env)).json<any>();
    expect(j.secretos_faltantes).toEqual(["META_AI_API_KEY", "ANTHROPIC_API_KEY"]);
    expect(j.ia).toEqual({ proveedor: "meta", respaldo: "anthropic", lista: false });
  });
});

describe("/odoo/*: el token", () => {
  const rutas: [string, () => Request][] = [
    ["GET /odoo/salud", () => get("/odoo/salud")],
    ["POST /odoo/enviar", () => post("/odoo/enviar", { canal: "telegram", id_externo: "1", texto: "hola" })],
    ["POST /odoo/estado", () => post("/odoo/estado", { canal: "telegram", id_externo: "1", estado: "humano" })],
    ["POST /odoo/seguimiento", () => post("/odoo/seguimiento", { canal: "telegram", id_externo: "1", conversacion_id: 1, numero: 1 })],
  ];

  it("sin JUAN_WORKER_TOKEN en el Worker: 503 con el NOMBRE que falta, aunque la petición traiga un Bearer cualquiera", async () => {
    const m = montar();
    for (const [nombre, hacer] of rutas) {
      const req = hacer();
      req.headers.set("authorization", "Bearer lo-que-sea");
      const res = await m.pedir(req, { JUAN_ODOO_TOKEN: "x" } as Env);
      expect(res.status, nombre).toBe(503);
      const j = await res.json<any>();
      expect(j.secretos_faltantes).toEqual(["JUAN_WORKER_TOKEN"]);
      expect(j.error).toMatch(/JUAN_WORKER_TOKEN/);
    }
    expect(m.pedidas).toEqual([]);
  });

  it("token ausente o equivocado: 401 y no se toca ninguna conversación", async () => {
    const m = montar();
    for (const [nombre, hacer] of rutas) {
      for (const cab of [{}, { authorization: "Bearer otro" }, { authorization: TOKEN_WORKER }, { authorization: `Basic ${TOKEN_WORKER}` }, { authorization: `Bearer ${TOKEN_WORKER}x` }, { authorization: "Bearer " }]) {
        const req = hacer();
        for (const [k, v] of Object.entries(cab)) req.headers.set(k, v);
        expect((await m.pedir(req)).status, `${nombre} ${JSON.stringify(cab)}`).toBe(401);
      }
    }
    expect(m.pedidas).toEqual([]);
  });

  it("el token del puente (WA_TOKEN) y el de Odoo→Worker son distintos: uno no abre la puerta del otro", async () => {
    const m = montar();
    expect((await m.pedir(get("/odoo/salud", { authorization: `Bearer ${WA_TOKEN}` }))).status).toBe(401);
    expect((await m.pedir(get("/odoo/salud", { authorization: `Bearer ${TOKEN_ODOO}` }))).status).toBe(401);
  });
});

describe("GET /odoo/salud", () => {
  it("con token: el informe completo (gasto, tope, canales, IA) y aun así ningún valor de secreto", async () => {
    const res = await montar({ gasto: 31.5, config: { presupuesto_ia_mensual_usd: 30 } }).pedir(get("/odoo/salud", deOdoo));
    const texto = await res.text();
    for (const secreto of [TOKEN_WORKER, TOKEN_ODOO, SECRETO_TG, BOT_TG, WA_TOKEN, "sk-ant-de-prueba"]) expect(texto).not.toContain(secreto);
    const j = JSON.parse(texto);
    expect(res.status).toBe(200);
    expect(j.gasto_ia_mes_usd).toBe(31.5);
    expect(j.tope_usd).toBe(30);
    expect(j.tope_alcanzado).toBe(true);
    expect(Object.keys(j.canales).sort()).toEqual(["instagram", "messenger", "telegram", "whatsapp_cloud", "whatsapp_qr"]);
  });

  it("solo GET", async () => {
    expect((await montar().pedir(post("/odoo/salud", {}, deOdoo))).status).toBe(405);
  });
});

describe("POST /odoo/enviar", () => {
  const base = { canal: "whatsapp_qr", id_externo: "50760261919", autor: "vendedora", texto: "Hola, soy Marisol." };

  it("pasa el texto y los adjuntos a la conversación (la que corresponde a canal:id_externo)", async () => {
    const m = montar();
    const res = await m.pedir(post("/odoo/enviar", { ...base, id_externo: " 50760261919 ", adjuntos: [{ tipo: "imagen", url: "https://sitio/foto.jpg", nombre: "foto.jpg", mime: "image/jpeg", extra: 1 }, "basura"] }, deOdoo));
    expect([res.status, await res.json()]).toEqual([200, { ok: true, id_mensaje: "m1" }]);
    expect(m.pedidas).toEqual([["whatsapp_qr", "50760261919"]]);
    expect(m.conv.enviados).toEqual([{ texto: "Hola, soy Marisol.", adjuntos: [{ tipo: "imagen", url: "https://sitio/foto.jpg", nombre: "foto.jpg", mime: "image/jpeg" }] }]);
  });

  it("solo adjuntos (sin texto) también vale", async () => {
    const m = montar();
    expect((await m.pedir(post("/odoo/enviar", { ...base, texto: undefined, adjuntos: [{ tipo: "documento", url: "https://sitio/ficha.pdf" }] }, deOdoo))).status).toBe(200);
  });

  it("valida el cuerpo con 400 y mensajes claros", async () => {
    const m = montar();
    const casos: [unknown, RegExp][] = [
      ["no es json", /JSON/],
      [[1, 2], /objeto/],
      [{ ...base, canal: "tiktok" }, /canal/],
      [{ ...base, canal: undefined }, /canal/],
      [{ ...base, id_externo: "  " }, /id_externo/],
      [{ ...base, id_externo: 5 }, /id_externo/],
      [{ ...base, autor: "bot" }, /vendedora/],
      [{ ...base, texto: "   " }, /texto o adjuntos/],
      [{ ...base, texto: undefined, adjuntos: [] }, /texto o adjuntos/],
      [{ ...base, adjuntos: [{ tipo: "imagen", url: "http://inseguro/foto.jpg" }] }, /https/],
      [{ ...base, adjuntos: [{ tipo: "imagen" }] }, /https/],
    ];
    for (const [cuerpo, patron] of casos) {
      const res = await m.pedir(post("/odoo/enviar", cuerpo, deOdoo));
      expect(res.status, JSON.stringify(cuerpo)).toBe(400);
      expect((await res.json<any>()).error).toMatch(patron);
    }
    expect(m.conv.enviados).toEqual([]);
  });

  it("un canal sin credenciales en el Worker: 502 diciendo cuál (no se intenta enviar)", async () => {
    const m = montar();
    const res = await m.pedir(post("/odoo/enviar", base, deOdoo), { JUAN_WORKER_TOKEN: TOKEN_WORKER } as Env);
    expect(res.status).toBe(502);
    expect((await res.json<any>()).error).toMatch(/whatsapp_qr/);
    expect(m.conv.enviados).toEqual([]);
  });

  it("si la conversación falla: 502 con el motivo acortado, sin romper el Worker", async () => {
    const m = montar();
    m.conv.falla = "x".repeat(900);
    const res = await m.pedir(post("/odoo/enviar", base, deOdoo));
    expect(res.status).toBe(502);
    expect((await res.json<any>()).error).toHaveLength(300);
  });

  it("solo POST", async () => {
    expect((await montar().pedir(get("/odoo/enviar", deOdoo))).status).toBe(405);
  });
});

describe("POST /odoo/estado", () => {
  it("humano con fecha de fin, bot sin fecha", async () => {
    const m = montar();
    expect((await m.pedir(post("/odoo/estado", { canal: "telegram", id_externo: "9", estado: "humano", pausada_hasta: "2026-10-09T20:00:00Z" }, deOdoo))).status).toBe(200);
    expect((await m.pedir(post("/odoo/estado", { canal: "telegram", id_externo: "9", estado: "humano", pausada_hasta: 1_790_000_000 }, deOdoo))).status).toBe(200);
    expect((await m.pedir(post("/odoo/estado", { canal: "telegram", id_externo: "9", estado: "bot" }, deOdoo))).status).toBe(200);
    expect(m.conv.estados).toEqual([
      { estado: "humano", pausada_hasta: "2026-10-09T20:00:00Z", nota_para_el_bot: null },
      { estado: "humano", pausada_hasta: 1_790_000_000, nota_para_el_bot: null },
      { estado: "bot", pausada_hasta: null, nota_para_el_bot: null },
    ]);
  });

  it("al devolver la conversación Odoo puede mandar la nota de la vendedora para el bot", async () => {
    const m = montar();
    const res = await m.pedir(post("/odoo/estado", { canal: "whatsapp_qr", id_externo: "50760261919", estado: "bot", nota_para_el_bot: "ya quedó la visita del sábado" }, deOdoo));
    expect(res.status).toBe(200);
    // Una nota que no es texto no pasa.
    await m.pedir(post("/odoo/estado", { canal: "whatsapp_qr", id_externo: "50760261919", estado: "bot", nota_para_el_bot: { x: 1 } }, deOdoo));
    expect(m.conv.estados).toEqual([
      { estado: "bot", pausada_hasta: null, nota_para_el_bot: "ya quedó la visita del sábado" },
      { estado: "bot", pausada_hasta: null, nota_para_el_bot: null },
    ]);
  });

  it("un estado inventado: 400", async () => {
    const m = montar();
    for (const estado of ["pausado", "", undefined, 1]) {
      expect((await m.pedir(post("/odoo/estado", { canal: "telegram", id_externo: "9", estado }, deOdoo))).status).toBe(400);
    }
    expect(m.conv.estados).toEqual([]);
  });
});

describe("POST /odoo/olvidar", () => {
  it("borra la copia de trabajo de ESA conversación y dice cuántos mensajes tenía", async () => {
    const m = montar();
    const res = await m.pedir(post("/odoo/olvidar", { canal: "telegram", id_externo: "555" }, deOdoo));
    expect([res.status, await res.json()]).toEqual([200, { ok: true, mensajes: 3 }]);
    expect(m.pedidas).toEqual([["telegram", "555"]]);
    expect(m.conv.olvidos).toBe(1);
  });

  it("sin la clave de Odoo, 401 y no borra nada", async () => {
    const m = montar();
    expect((await m.pedir(post("/odoo/olvidar", { canal: "telegram", id_externo: "555" }))).status).toBe(401);
    expect((await m.pedir(post("/odoo/olvidar", { canal: "telegram", id_externo: "555" }, { authorization: "Bearer mal" }))).status).toBe(401);
    expect(m.conv.olvidos).toBe(0);
  });

  it("valida canal e id_externo", async () => {
    const m = montar();
    expect((await m.pedir(post("/odoo/olvidar", { canal: "fax", id_externo: "1" }, deOdoo))).status).toBe(400);
    expect((await m.pedir(post("/odoo/olvidar", { canal: "telegram" }, deOdoo))).status).toBe(400);
    expect(m.conv.olvidos).toBe(0);
  });

  it("si falla, 502 con el motivo corto (Odoo no borra su copia hasta que esta se borre)", async () => {
    const m = montar();
    m.conv.falla = "almacenamiento no disponible";
    const res = await m.pedir(post("/odoo/olvidar", { canal: "telegram", id_externo: "555" }, deOdoo));
    expect(res.status).toBe(502);
  });
});

describe("POST /odoo/seguimiento", () => {
  const base = { canal: "whatsapp_qr", id_externo: "50760261919", conversacion_id: 42, numero: 1, contexto: { interes: "cama queen", ultimo_mensaje_ts: "2026-10-08T15:00:00Z", otro: "ignorado" } };

  it("pasa lo que la conversación necesita y devuelve lo que ella decida", async () => {
    const m = montar();
    const res = await m.pedir(post("/odoo/seguimiento", base, deOdoo));
    expect([res.status, await res.json()]).toEqual([200, { ok: true, resultado: "enviado" }]);
    expect(m.conv.seguimientos).toEqual([{ conversacion_id: 42, numero: 1, contexto: { interes: "cama queen", ultimo_mensaje_ts: "2026-10-08T15:00:00Z" } }]);
  });

  it("descartado y pospuesto son respuestas normales (200)", async () => {
    const m = montar();
    m.conv.seguimientoResultado = { ok: true, resultado: "descartado", motivo: "el cliente pidió no recibir más mensajes" };
    const res = await m.pedir(post("/odoo/seguimiento", { ...base, numero: 2 }, deOdoo));
    expect(res.status).toBe(200);
    expect((await res.json<any>()).motivo).toMatch(/no recibir/);
  });

  it("si no se pudo redactar o enviar: 502 con `ok:false` (Odoo reintenta más tarde)", async () => {
    const m = montar();
    m.conv.seguimientoResultado = { ok: false, error: "la IA no respondió" };
    const res = await m.pedir(post("/odoo/seguimiento", base, deOdoo));
    expect([res.status, await res.json()]).toEqual([502, { ok: false, error: "la IA no respondió" }]);
  });

  it("valida conversacion_id y numero (solo 1 o 2)", async () => {
    const m = montar();
    for (const malo of [{ conversacion_id: "42" }, { conversacion_id: undefined }, { numero: 3 }, { numero: 0 }, { numero: "1" }, { numero: undefined }]) {
      expect((await m.pedir(post("/odoo/seguimiento", { ...base, ...malo }, deOdoo))).status, JSON.stringify(malo)).toBe(400);
    }
    expect(m.conv.seguimientos).toEqual([]);
  });

  it("sin `contexto` también funciona", async () => {
    const m = montar();
    expect((await m.pedir(post("/odoo/seguimiento", { ...base, contexto: undefined }, deOdoo))).status).toBe(200);
    expect(m.conv.seguimientos[0]).toMatchObject({ contexto: {} });
  });
});

describe("rutas desconocidas bajo /odoo/", () => {
  it("con token: 404 (y no se toca nada)", async () => {
    const m = montar();
    expect((await m.pedir(post("/odoo/borrar", { canal: "telegram", id_externo: "1" }, deOdoo))).status).toBe(404);
    expect((await m.pedir(post("/odoo/admin", {}, deOdoo))).status).toBe(400);
  });
});

describe("GET /media/<conversación>/<id>", () => {
  const clave = claveDeConversacion("whatsapp_qr", "50760261919");
  const id = "a1b2c3d4e5f60718";
  const firmada = async (ahora = AHORA) => new URL(await firmarUrlMedio("https://juan.example", TOKEN_WORKER, clave, id, ahora));
  const archivo = () => ({ bytes: new Uint8Array([1, 2, 3, 4]), mime: "image/jpeg", nombre: "comprobante pago.jpg" });

  it("con la firma buena entrega el archivo, privado y sin que el navegador adivine el tipo", async () => {
    const m = montar();
    m.conv.medio = archivo();
    const u = await firmada();
    const res = await m.pedir(get(u.pathname + u.search));
    expect(res.status).toBe(200);
    expect([...new Uint8Array(await res.arrayBuffer())]).toEqual([1, 2, 3, 4]);
    expect(res.headers.get("content-type")).toBe("image/jpeg");
    expect(res.headers.get("cache-control")).toMatch(/private/);
    expect(res.headers.get("x-content-type-options")).toBe("nosniff");
    expect(res.headers.get("content-disposition")).toBe("inline; filename*=UTF-8''comprobante%20pago.jpg");
    expect(m.pedidas).toEqual([["whatsapp_qr", "50760261919"]]);
  });

  it("firma falsa, cambiada o sin firma: 403 y NO se abre la conversación", async () => {
    const m = montar();
    m.conv.medio = archivo();
    const u = await firmada();
    const sig = u.searchParams.get("sig")!;
    const casos = [`${u.pathname}?exp=${u.searchParams.get("exp")}&sig=${"0".repeat(64)}`, `${u.pathname}?exp=${u.searchParams.get("exp")}`, `${u.pathname}?sig=${sig}`, `${u.pathname}?exp=${Number(u.searchParams.get("exp")) + 1}&sig=${sig}`, `${u.pathname.replace(id, "ffffffffffffffff")}${u.search}`];
    for (const c of casos) expect((await m.pedir(get(c))).status, c).toBe(403);
    expect(m.pedidas).toEqual([]);
  });

  it("firmada con OTRO secreto: 403 (sin la llave nadie fabrica un enlace)", async () => {
    const m = montar();
    const falsa = new URL(await firmarUrlMedio("https://juan.example", "otro-secreto", clave, id, AHORA));
    expect((await m.pedir(get(falsa.pathname + falsa.search))).status).toBe(403);
  });

  it("sin JUAN_WORKER_TOKEN en el Worker no hay con qué firmar: 403 siempre", async () => {
    const m = montar();
    const u = await firmada();
    expect((await m.pedir(get(u.pathname + u.search), {} as Env)).status).toBe(403);
  });

  it("vencida a los 2 días: 410", async () => {
    const m = montar();
    m.conv.medio = archivo();
    const u = await firmada(AHORA - VIDA_URL_MEDIO_MS - 1000);
    expect((await m.pedir(get(u.pathname + u.search))).status).toBe(410);
  });

  it("el archivo ya no está (se borró a los 2 días): 404", async () => {
    const m = montar();
    const u = await firmada();
    expect((await m.pedir(get(u.pathname + u.search))).status).toBe(404);
  });

  it("un id mal formado o una clave que no es una conversación: 404", async () => {
    const m = montar();
    expect((await m.pedir(get(`/media/${clave}/../../etc`))).status).toBe(404);
    expect((await m.pedir(get(`/media/${clave}/xyz`))).status).toBe(404);
    expect((await m.pedir(get(`/media/${clave}`))).status).toBe(404);
    const rara = claveDeConversacion("tiktok", "1");
    const u = new URL(await firmarUrlMedio("https://juan.example", TOKEN_WORKER, rara, id, AHORA));
    expect((await m.pedir(get(u.pathname + u.search))).status).toBe(404);
  });

  it("solo GET", async () => {
    const u = await firmada();
    expect((await montar().pedir(post(u.pathname + u.search, {}))).status).toBe(405);
  });
});

describe("webhook de Telegram", () => {
  const update = (texto = "hola") => ({ update_id: 1, message: { message_id: 7, from: { id: 555, first_name: "Karen" }, chat: { id: 555, type: "private" }, date: 1_790_000_000, text: texto } });
  const hook = (cuerpo: unknown, secreto: string | null = SECRETO_TG) =>
    post("/webhooks/telegram", cuerpo, secreto === null ? {} : { "x-telegram-bot-api-secret-token": secreto });

  it("responde 200 DE INMEDIATO y atiende el mensaje después (waitUntil)", async () => {
    const m = montar();
    const res = await m.pedir(hook(update()));
    expect(res.status).toBe(200);
    expect(m.conv.ingestados).toHaveLength(0); // todavía no: se hace después de responder
    await m.despues();
    expect(m.conv.ingestados.map((e) => [e.canal, e.id_externo, e.texto])).toEqual([["telegram", "555", "hola"]]);
    expect(m.pedidas).toEqual([["telegram", "555"]]);
  });

  it("un fallo al atender no vuelve error a Telegram (no reintenta en bucle)", async () => {
    const m = montar();
    m.conv.falla = "se cayó";
    const err = vi.spyOn(console, "error").mockImplementation(() => {});
    const res = await m.pedir(hook(update()));
    await m.despues();
    expect(res.status).toBe(200);
    expect(err).toHaveBeenCalled();
    err.mockRestore();
  });

  it("secreto malo: 401 y nada se atiende", async () => {
    const m = montar();
    for (const s of [null, "otro", ""]) expect((await m.pedir(hook(update(), s))).status).toBe(401);
    await m.despues();
    expect(m.pedidas).toEqual([]);
  });

  it("sin secretos cargados el webhook falla cerrado", async () => {
    const m = montar();
    expect((await m.pedir(hook(update()), {} as Env)).status).toBe(401);
    await m.despues();
    expect(m.pedidas).toEqual([]);
  });

  it("canal APAGADO en Odoo: responde 200 y no atiende ni registra", async () => {
    const m = montar({ config: { canales_activos: { telegram: false } } });
    const res = await m.pedir(hook(update()));
    await m.despues();
    expect(res.status).toBe(200);
    expect(m.pedidas).toEqual([]);
  });

  it("un archivo se descarga ANTES de pasar a la conversación, y lo que viaja no lleva funciones ni tokens", async () => {
    const fetchTg: typeof fetch = async (r) => {
      const url = String(r);
      if (url.includes("/getFile?")) return Response.json({ ok: true, result: { file_path: "photos/f.jpg" } });
      return new Response(new Uint8Array([7, 7, 7]), { headers: { "content-type": "image/jpeg" } });
    };
    const m = montar({ adaptadores: [crearTelegram({ fetch: fetchTg, dormir: async () => {} })] });
    const foto = { update_id: 2, message: { message_id: 8, from: { id: 555, first_name: "Karen" }, chat: { id: 555, type: "private" }, date: 1_790_000_000, caption: "así", photo: [{ file_id: "F1", width: 90, height: 90 }, { file_id: "F2", width: 800, height: 800 }] } };
    await m.pedir(hook(foto));
    await m.despues();
    const [e] = m.conv.ingestados;
    expect(e.adjuntos).toHaveLength(1);
    expect([...e.adjuntos[0].bytes!]).toEqual([7, 7, 7]);
    expect("obtener" in e.adjuntos[0] && (e.adjuntos[0] as any).obtener).toBeFalsy();
    expect(JSON.stringify(e.adjuntos[0])).not.toContain(BOT_TG);
  });

  it("si la descarga falla, el mensaje igual llega (sin bytes)", async () => {
    const fetchTg: typeof fetch = async () => new Response("no", { status: 500 });
    const m = montar({ adaptadores: [crearTelegram({ fetch: fetchTg, dormir: async () => {} })] });
    const aviso = vi.spyOn(console, "warn").mockImplementation(() => {});
    await m.pedir(hook({ update_id: 3, message: { message_id: 9, from: { id: 555, first_name: "K" }, chat: { id: 555, type: "private" }, date: 1_790_000_000, voice: { file_id: "V1", duration: 3 } } }));
    await m.despues();
    expect(m.conv.ingestados).toHaveLength(1);
    expect(m.conv.ingestados[0].adjuntos[0].bytes).toBeUndefined();
    aviso.mockRestore();
  });

  it("un archivo de más de 12 MB se descarta (no se guarda en el Durable Object)", async () => {
    const a = new CanalFalso("telegram");
    a.ruta = "/webhooks/telegram";
    a.recibir = async () => ({
      respuesta: new Response("ok"),
      entrantes: [{ canal: "telegram", id_externo: "1", id_mensaje: "g", adjuntos: [{ tipo: "documento", obtener: async () => ({ bytes: new Uint8Array(12 * 1024 * 1024 + 1) }) }], ts: 1 }],
    });
    const m = montar({ adaptadores: [a] });
    await m.pedir(post("/webhooks/telegram", {}));
    await m.despues();
    expect(m.conv.ingestados[0].adjuntos[0].bytes).toBeUndefined();
  });

  it("varios mensajes en un mismo POST se atienden en orden", async () => {
    const a = new CanalFalso("telegram");
    a.ruta = "/webhooks/telegram";
    a.recibir = async () => ({
      respuesta: new Response("ok"),
      entrantes: ["uno", "dos", "tres"].map((t, i) => ({ canal: "telegram" as const, id_externo: "1", id_mensaje: `m${i}`, texto: t, adjuntos: [], ts: i + 1 })),
    });
    const m = montar({ adaptadores: [a] });
    await m.pedir(post("/webhooks/telegram", {}));
    await m.despues();
    expect(m.conv.ingestados.map((e) => e.texto)).toEqual(["uno", "dos", "tres"]);
  });

  it("si el adaptador revienta: 500 (y el error no se filtra al que llama)", async () => {
    const a = new CanalFalso("telegram");
    a.ruta = "/webhooks/telegram";
    a.recibir = async () => {
      throw new Error("detalle interno con " + BOT_TG);
    };
    const err = vi.spyOn(console, "error").mockImplementation(() => {});
    const res = await montar({ adaptadores: [a] }).pedir(post("/webhooks/telegram", {}));
    expect([res.status, await res.text()]).toEqual([500, "error"]);
    err.mockRestore();
  });
});

describe("webhook del puente de WhatsApp (se responde DESPUÉS de guardar)", () => {
  const msg = { id_mensaje: "3EB0A1", de: "50760261919@s.whatsapp.net", nombre: "Karen", tipo: "texto", texto: "Hola", ts: 1_790_000_000, propio: false };
  const hook = (cuerpo: unknown, token = WA_TOKEN) => post("/webhooks/whatsapp-qr", cuerpo, { "x-wa-token": token });

  it("200 solo cuando la conversación ya lo guardó", async () => {
    const m = montar();
    const res = await m.pedir(hook(msg));
    expect(res.status).toBe(200);
    expect(m.conv.ingestados).toHaveLength(1); // ya está, sin esperar a waitUntil
  });

  it("si no se puede guardar: 500, para que el puente reintente", async () => {
    const m = montar();
    m.conv.falla = "disco lleno";
    const err = vi.spyOn(console, "error").mockImplementation(() => {});
    const res = await m.pedir(hook(msg));
    expect(res.status).toBe(500);
    err.mockRestore();
  });

  it("token malo: 401", async () => {
    const m = montar();
    expect((await m.pedir(hook(msg, "otro"))).status).toBe(401);
    expect(m.pedidas).toEqual([]);
  });

  it("un mensaje propio (la vendedora escribió desde su teléfono) llega marcado como propio", async () => {
    const m = montar();
    await m.pedir(hook({ ...msg, propio: true, texto: "Te atiendo yo" }));
    expect(m.conv.ingestados[0].propio).toBe(true);
  });
});

describe("ninguna ruta de los Baby Caleb sobrevive", () => {
  it("/admin, /api, /member, /twilio, /manychat, /cal, /campaigns: todas 404", async () => {
    const m = montar();
    for (const r of ["/admin", "/admin/login", "/api/chat", "/member", "/twilio/sms", "/manychat/webhook", "/webhooks/twilio", "/webhooks/manychat", "/webhooks/cal", "/campaigns", "/flywheel"]) {
      expect((await m.pedir(get(r))).status, r).toBe(404);
    }
  });
});
