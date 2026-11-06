/**
 * Las rutas del Worker, sin Cloudflare: /health, /salud (pública), webhooks de los canales, /media firmado y /odoo/* con token.
 * Las conversaciones son un doble que anota lo que le piden; los adaptadores de Telegram y WhatsApp QR son los de verdad.
 */
import { describe, expect, it, vi } from "vitest";
import type { Env } from "../src/env";
import { CONFIG_POR_DEFECTO, normalizarConfig, type Config } from "../src/config";
import { crearTelegram } from "../src/canales/telegram";
import { crearWhatsappQr } from "../src/canales/whatsappQr";
import { crearWhatsappCloud } from "../src/canales/whatsappCloud";
import { crearMeta } from "../src/canales/meta";
import { hmacHex } from "../src/seguridad";
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
  /** Lo que se guardó crudo antes de contestar (webhooks de Meta), en orden. */
  guardados: Entrante[] = [];
  /** Si no es null, `guardarRecibido` lanza esto (el Durable Object no pudo guardar). */
  fallaGuardar: string | null = null;
  /** Mientras exista, `guardarRecibido` espera a que se resuelva (para ver que el 200 no sale antes). */
  puertaGuardar: Promise<void> | null = null;
  /** Solo este id_mensaje falla al guardarse (un lote donde uno sí y otro no). */
  fallarSoloA: string | null = null;
  enviados: unknown[] = [];
  estados: unknown[] = [];
  seguimientos: unknown[] = [];
  olvidos = 0;
  medio: { bytes: Uint8Array; mime: string; nombre: string | null } | null = null;
  falla: string | null = null;
  seguimientoResultado: any = { ok: true, resultado: "enviado" };

  /** Guarda, pero la respuesta del Durable Object se pierde en la red («Network connection lost»). */
  perderRespuesta = false;

  private guardado = (id: string) => this.guardados.some((g) => g.id_mensaje === id);
  private atendido = (id: string) => this.ingestados.some((g) => g.id_mensaje === id);

  async ingest(e: Entrante) {
    if (this.falla) throw new Error(this.falla);
    // Como el Durable Object: lo que entró por la bandeja y ya se atendió es un repetido.
    if (this.guardado(e.id_mensaje) && this.atendido(e.id_mensaje)) return { ok: true as const, accion: "duplicado" as const };
    this.ingestados.push(e);
    return { ok: true as const, accion: "en_espera" as const };
  }
  async guardarRecibido(e: Entrante) {
    if (this.puertaGuardar) await this.puertaGuardar;
    if (this.fallaGuardar) throw new Error(this.fallaGuardar);
    if (this.fallarSoloA === e.id_mensaje) throw new Error("no se pudo guardar este");
    // Como el Durable Object: el mismo id_mensaje (un reintento de Meta) no es nuevo; sigue pendiente mientras nadie lo atendió.
    const nuevo = !this.guardado(e.id_mensaje);
    if (nuevo) this.guardados.push(e);
    if (this.perderRespuesta) throw new Error("Network connection lost.");
    return { nuevo, pendiente: !this.atendido(e.id_mensaje) };
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
  const config = normalizarConfig({ ...CONFIG_POR_DEFECTO, telegram_chats: ["555", "556"], ...opciones.config });
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
    ["POST /odoo/sugerir", () => post("/odoo/sugerir", { conversacion_id: 1, canal: "telegram", mensajes: [{ autor: "cliente", texto: "hola" }] })],
    ["POST /odoo/resumir", () => post("/odoo/resumir", { conversacion_id: 1, canal: "telegram", mensajes: [{ autor: "cliente", texto: "hola" }] })],
    ["POST /odoo/embeber", () => post("/odoo/embeber", { textos: ["hola"] })],
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

  it("id_envio (la llave contra duplicados) pasa tal cual a la conversación; sin él, un Odoo viejo sigue funcionando", async () => {
    const m = montar();
    expect((await m.pedir(post("/odoo/enviar", { ...base, id_envio: "odoo-0f1e2d3c4b5a69788796a5b4c3d2e1f0" }, deOdoo))).status).toBe(200);
    expect(m.conv.enviados).toEqual([{ id_envio: "odoo-0f1e2d3c4b5a69788796a5b4c3d2e1f0", texto: "Hola, soy Marisol.", adjuntos: [] }]);
    expect((await m.pedir(post("/odoo/enviar", base, deOdoo))).status).toBe(200);
    expect((m.conv.enviados[1] as { id_envio?: string }).id_envio).toBeUndefined();
  });

  it("un id_envio con forma rara → 400 (no se usa de llave de memoria)", async () => {
    const m = montar();
    for (const malo of ["", 5, "con espacios", "x".repeat(121), "a/b", { a: 1 }]) {
      const res = await m.pedir(post("/odoo/enviar", { ...base, id_envio: malo }, deOdoo));
      expect(res.status, JSON.stringify(malo)).toBe(400);
      expect((await res.json<any>()).error).toMatch(/id_envio/);
    }
    expect(m.conv.enviados).toEqual([]);
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

  it("un chat que NO está en la lista de Odoo se ignora: 200, nada se atiende ni se descarga ni llega a la IA", async () => {
    const fetchTg = vi.fn(async () => new Response("{}"));
    const m = montar({ adaptadores: [crearTelegram({ fetch: fetchTg as unknown as typeof fetch, dormir: async () => {} })] });
    const foto = { update_id: 5, message: { message_id: 8, from: { id: 999, first_name: "Intruso" }, chat: { id: 999, type: "private" }, date: 1_790_000_000, caption: "hola", photo: [{ file_id: "F1", width: 90, height: 90 }] } };
    const res = await m.pedir(hook(foto));
    await m.despues();
    expect(res.status).toBe(200);
    expect(m.pedidas).toEqual([]);
    expect(m.conv.ingestados).toEqual([]);
    expect(fetchTg).not.toHaveBeenCalled(); // ni siquiera se bajó la foto
  });

  it("si la dueña ABRE Telegram a cualquiera, entran todos los chats (ella decide)", async () => {
    const m = montar({ config: { telegram_chats: [], telegram_abierto: true } });
    const res = await m.pedir(hook({ update_id: 6, message: { message_id: 9, from: { id: 999, first_name: "Cualquiera" }, chat: { id: 999, type: "private" }, date: 1_790_000_000, text: "hola" } }));
    await m.despues();
    expect(res.status).toBe(200);
    expect(m.conv.ingestados.map((e) => e.id_externo)).toEqual(["999"]);
  });

  it("el interruptor solo vale si Odoo manda true de verdad (un texto o un 1 no lo abre)", async () => {
    for (const raro of ["true", 1, "si", null]) {
      const m = montar({ config: { telegram_chats: [], telegram_abierto: raro as never } });
      await m.pedir(hook(update()));
      await m.despues();
      expect(m.pedidas, String(raro)).toEqual([]);
    }
  });

  it("con la lista vacía nadie entra por Telegram (pero WhatsApp no se toca)", async () => {
    const m = montar({ config: { telegram_chats: [] } });
    await m.pedir(hook(update()));
    await m.despues();
    expect(m.pedidas).toEqual([]);
  });

  it("si la lista no se pudo leer (Odoo dormido) contesta 503 para que Telegram reintente, no pierde el mensaje", async () => {
    const m = montar();
    m.deps.config = async () => CONFIG_POR_DEFECTO;
    const res = await m.pedir(hook(update()));
    await m.despues();
    expect(res.status).toBe(503);
    expect(m.pedidas).toEqual([]);
    m.deps.config = async () => normalizarConfig({ telegram_chats: ["555"] });
    expect((await m.pedir(hook(update()))).status).toBe(200);
    await m.despues();
    expect(m.conv.ingestados).toHaveLength(1);
  });

  it("el chat permitido se compara como texto exacto (no por prefijo)", async () => {
    const m = montar({ config: { telegram_chats: ["5550"] } });
    await m.pedir(hook(update()));
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
      entrantes: [{ canal: "telegram", id_externo: "555", id_mensaje: "g", adjuntos: [{ tipo: "documento", obtener: async () => ({ bytes: new Uint8Array(12 * 1024 * 1024 + 1) }) }], ts: 1 }],
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
      entrantes: ["uno", "dos", "tres"].map((t, i) => ({ canal: "telegram" as const, id_externo: "555", id_mensaje: `m${i}`, texto: t, adjuntos: [], ts: i + 1 })),
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

describe("webhooks de Meta (WhatsApp Cloud, Messenger, Instagram): el 200 sale DESPUÉS de guardar", () => {
  const SECRETO_META = "secreto-de-la-app-meta-0123456789";
  const TOKEN_CLOUD = "token-cloud-de-prueba-0123456789";
  const envMeta = { ...envCompleto, META_APP_SECRET: SECRETO_META, META_VERIFY_TOKEN: "verificacion-0123456789", WHATSAPP_CLOUD_TOKEN: TOKEN_CLOUD, WHATSAPP_PHONE_NUMBER_ID: "109876543210", META_PAGE_TOKEN: "pagina-0123456789" } as unknown as Env;
  const encendidos = { canales_activos: { whatsapp_cloud: true, messenger: true, instagram: true } };
  const red = vi.fn(async () => new Response("{}"));
  const adaptadoresMeta = () => [
    crearWhatsappCloud({ fetch: red as unknown as typeof fetch, dormir: async () => {} }),
    crearMeta({ fetch: red as unknown as typeof fetch, dormir: async () => {} }),
    crearTelegram({ fetch: red as unknown as typeof fetch, dormir: async () => {} }),
    crearWhatsappQr({ fetch: red as unknown as typeof fetch }),
  ];
  const wa = (id: string, texto = "Hola, ¿tienen camas?") => ({ from: "50760261919", id, timestamp: "1790000000", type: "text", text: { body: texto } });
  const lote = (mensajes: object[]) => ({ object: "whatsapp_business_account", entry: [{ id: "WABA", changes: [{ field: "messages", value: { contacts: [{ profile: { name: "Karen" }, wa_id: "50760261919" }], messages: mensajes } }] }] });
  const firmado = async (ruta: string, cuerpo: object, secreto = SECRETO_META) => {
    const crudo = JSON.stringify(cuerpo);
    return new Request(`https://juan.example${ruta}`, { method: "POST", headers: { "content-type": "application/json", "x-hub-signature-256": `sha256=${await hmacHex(secreto, crudo)}` }, body: crudo });
  };
  const cloud = (cuerpo: object, secreto?: string) => firmado("/webhooks/whatsapp-cloud", cuerpo, secreto);
  const montarMeta = (config: Record<string, unknown> = encendidos) => montar({ config, adaptadores: adaptadoresMeta() });
  /** Espera, con el bucle de eventos real (setImmediate no se falsea), a que algo pase. */
  const hasta = async (listo: () => boolean) => {
    for (let i = 0; i < 5000 && !listo(); i++) await new Promise((r) => setImmediate(r));
  };

  it("el 200 no sale hasta que el Durable Object guardó el mensaje; lo lento (atenderlo) va después", async () => {
    const m = montarMeta();
    let abrir!: () => void;
    m.conv.puertaGuardar = new Promise<void>((r) => (abrir = r));
    let contestado = false;
    const respuesta = m.pedir(await cloud(lote([wa("wamid.A")])), envMeta).then((r) => ((contestado = true), r));
    for (let i = 0; i < 20; i++) await new Promise((r) => setTimeout(r, 0));
    expect(contestado).toBe(false); // el Durable Object todavía no confirmó: Meta sigue esperando
    expect(m.conv.guardados).toEqual([]);
    abrir();
    const res = await respuesta;
    expect(res.status).toBe(200);
    expect(m.conv.guardados.map((e) => [e.canal, e.id_externo, e.id_mensaje, e.texto])).toEqual([["whatsapp_cloud", "50760261919", "wamid.A", "Hola, ¿tienen camas?"]]);
    expect(m.pedidas[0]).toEqual(["whatsapp_cloud", "50760261919"]);
    await m.despues(); // como ctx.waitUntil: descargas, IA y respuesta, después del 200
    expect(m.conv.ingestados.map((e) => e.id_mensaje)).toEqual(["wamid.A"]);
  });

  it("si no se pudo guardar: 500 para que Meta reintente, y nada se atiende", async () => {
    const m = montarMeta();
    m.conv.fallaGuardar = "el Durable Object no respondió";
    const err = vi.spyOn(console, "error").mockImplementation(() => {});
    const res = await m.pedir(await cloud(lote([wa("wamid.B")])), envMeta);
    await m.despues();
    expect(res.status).toBe(500);
    expect(m.conv.ingestados).toEqual([]);
    expect(err).toHaveBeenCalled();
    err.mockRestore();
    // Meta reintenta el mismo POST: ahora sí se guarda, 200 y se atiende una vez.
    m.conv.fallaGuardar = null;
    expect((await m.pedir(await cloud(lote([wa("wamid.B")])), envMeta)).status).toBe(200);
    await m.despues();
    expect(m.conv.ingestados.map((e) => e.id_mensaje)).toEqual(["wamid.B"]);
  });

  it("un reintento de Meta con el mismo id (no oyó el 200): 200 otra vez y NO se atiende dos veces", async () => {
    const m = montarMeta();
    const primero = await m.pedir(await cloud(lote([wa("wamid.C")])), envMeta);
    const reintento = await m.pedir(await cloud(lote([wa("wamid.C")])), envMeta); // antes de que termine lo de después
    await m.despues();
    const tarde = await m.pedir(await cloud(lote([wa("wamid.C")])), envMeta); // y después de atenderlo
    await m.despues();
    expect([primero.status, reintento.status, tarde.status]).toEqual([200, 200, 200]);
    expect(m.conv.ingestados.map((e) => e.id_mensaje)).toEqual(["wamid.C"]);
  });

  it("un lote donde uno no se pudo guardar: 500 (Meta reintenta), el que sí se guardó se atiende y el reintento no lo repite", async () => {
    const m = montarMeta();
    m.conv.fallarSoloA = "wamid.E";
    const err = vi.spyOn(console, "error").mockImplementation(() => {});
    const res = await m.pedir(await cloud(lote([wa("wamid.D", "uno"), wa("wamid.E", "dos")])), envMeta);
    await m.despues();
    expect(res.status).toBe(500);
    expect(m.conv.ingestados.map((e) => e.id_mensaje)).toEqual(["wamid.D"]);
    m.conv.fallarSoloA = null;
    expect((await m.pedir(await cloud(lote([wa("wamid.D", "uno"), wa("wamid.E", "dos")])), envMeta)).status).toBe(200);
    await m.despues();
    expect(m.conv.ingestados.map((e) => e.id_mensaje)).toEqual(["wamid.D", "wamid.E"]);
    err.mockRestore();
  });

  it("5 · se guardó pero la respuesta del Durable Object se perdió en la red: 500, y el reintento de Meta lo atiende ya (no espera al rescate)", async () => {
    const m = montarMeta();
    m.conv.perderRespuesta = true;
    const err = vi.spyOn(console, "error").mockImplementation(() => {});
    expect((await m.pedir(await cloud(lote([wa("wamid.L")])), envMeta)).status).toBe(500);
    await m.despues();
    expect(m.conv.ingestados).toEqual([]);
    m.conv.perderRespuesta = false;
    expect((await m.pedir(await cloud(lote([wa("wamid.L")])), envMeta)).status).toBe(200);
    await m.despues();
    expect(m.conv.ingestados.map((e) => e.id_mensaje)).toEqual(["wamid.L"]);
    // Y otro reintento, ya atendido, no lo repite.
    expect((await m.pedir(await cloud(lote([wa("wamid.L")])), envMeta)).status).toBe(200);
    await m.despues();
    expect(m.conv.ingestados).toHaveLength(1);
    err.mockRestore();
  });

  it("5 · si el Durable Object no contesta, el webhook no se queda colgado: 500 a los 3 s (dentro de los 5 s de Meta)", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date"] });
    const err = vi.spyOn(console, "error").mockImplementation(() => {});
    try {
      const m = montarMeta();
      let pedido: number | null = null;
      m.conv.guardarRecibido = () => {
        pedido ??= Date.now();
        return new Promise(() => {}); // el Durable Object nunca contesta
      };
      const req = await cloud(lote([wa("wamid.M")]));
      let res: Response | undefined;
      void m.pedir(req, envMeta).then((r) => (res = r));
      await hasta(() => pedido !== null); // la firma (WebCrypto) corre en tiempo real: el reloj falso arranca recién aquí
      for (let i = 0; i < 100 && !res; i++) await vi.advanceTimersByTimeAsync(100);
      expect(res?.status).toBe(500);
      expect(pedido).not.toBeNull();
      expect(Date.now() - pedido!).toBeLessThanOrEqual(3_100);
    } finally {
      err.mockRestore();
      vi.useRealTimers();
    }
  });

  it("si falla el PRIMERO de una misma persona, los que siguen de ella tampoco se guardan: el reintento los trae en orden", async () => {
    const m = montarMeta();
    m.conv.fallarSoloA = "wamid.K1";
    const err = vi.spyOn(console, "error").mockImplementation(() => {});
    expect((await m.pedir(await cloud(lote([wa("wamid.K1", "uno"), wa("wamid.K2", "dos")])), envMeta)).status).toBe(500);
    await m.despues();
    expect(m.conv.guardados).toEqual([]);
    expect(m.conv.ingestados).toEqual([]);
    m.conv.fallarSoloA = null;
    expect((await m.pedir(await cloud(lote([wa("wamid.K1", "uno"), wa("wamid.K2", "dos")])), envMeta)).status).toBe(200);
    await m.despues();
    expect(m.conv.ingestados.map((e) => e.texto)).toEqual(["uno", "dos"]);
    err.mockRestore();
  });

  it("lo que se guarda son datos planos: el archivo va con su media_id (`ref`), sin funciones ni el token; se baja DESPUÉS del 200", async () => {
    red.mockClear();
    const m = montarMeta();
    let abrir!: () => void;
    m.conv.puertaGuardar = new Promise<void>((r) => (abrir = r));
    const foto = { from: "50760261919", id: "wamid.F", type: "image", image: { id: "MEDIA1", caption: "así", mime_type: "image/jpeg" } };
    const respuesta = m.pedir(await cloud(lote([foto])), envMeta);
    for (let i = 0; i < 20; i++) await new Promise((r) => setTimeout(r, 0));
    expect(red).not.toHaveBeenCalled(); // mientras se guarda (antes del 200) no se baja nada: contestar no depende de Meta
    abrir();
    expect((await respuesta).status).toBe(200);
    const [g] = m.conv.guardados;
    expect(g.adjuntos).toEqual([{ tipo: "imagen", mime: "image/jpeg", ref: "MEDIA1" }]);
    expect(JSON.stringify(g)).not.toContain(TOKEN_CLOUD);
    await m.despues();
    expect(red).toHaveBeenCalled(); // la descarga va en lo de después
  });

  it("canal APAGADO en Odoo (configuración conocida): 200 y no se guarda ni se atiende", async () => {
    const m = montarMeta({ canales_activos: { whatsapp_cloud: false } });
    const res = await m.pedir(await cloud(lote([wa("wamid.G")])), envMeta);
    await m.despues();
    expect(res.status).toBe(200);
    expect(m.pedidas).toEqual([]);
  });

  it("configuración desconocida (Odoo dormido y sin copia): el mensaje se GUARDA igual (antes se perdía: el canal arranca apagado)", async () => {
    const m = montarMeta();
    m.deps.config = async () => CONFIG_POR_DEFECTO;
    const res = await m.pedir(await cloud(lote([wa("wamid.H")])), envMeta);
    await m.despues();
    expect(res.status).toBe(200);
    expect(m.conv.guardados.map((e) => e.id_mensaje)).toEqual(["wamid.H"]);
    // El Worker no lo atiende sin saber si el canal está encendido: queda en la bandeja y lo decide el rescate del Durable Object.
    expect(m.conv.ingestados).toEqual([]);
  });

  it("si Odoo tarda con la configuración, no se le espera más de 1 s: el mensaje se guarda y Meta recibe su 200", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date"] });
    try {
      const m = montarMeta();
      let pedido: number | null = null;
      m.deps.config = () => {
        pedido ??= Date.now();
        return new Promise<Config>(() => {}); // Odoo colgado
      };
      const req = await cloud(lote([wa("wamid.I")]));
      let res: Response | undefined;
      const p = m.pedir(req, envMeta).then((r) => (res = r));
      await hasta(() => pedido !== null); // la firma (WebCrypto) corre en tiempo real: el reloj falso arranca recién aquí
      for (let i = 0; i < 100 && !res; i++) await vi.advanceTimersByTimeAsync(100);
      await p;
      expect(res!.status).toBe(200);
      expect(Date.now() - pedido!).toBeLessThanOrEqual(1_100);
      expect(m.conv.guardados.map((e) => e.id_mensaje)).toEqual(["wamid.I"]);
    } finally {
      vi.useRealTimers();
    }
  });

  it("firma mala: 401 y nada se guarda (la verificación no cambió)", async () => {
    const m = montarMeta();
    expect((await m.pedir(await cloud(lote([wa("wamid.J")]), "otra-clave"), envMeta)).status).toBe(401);
    await m.despues();
    expect(m.pedidas).toEqual([]);
  });

  it("Messenger e Instagram comparten el camino: también se guardan antes del 200 y un fallo da 500", async () => {
    const evento = (mid: string, object = "page") => ({ object, entry: [{ id: "PAGINA", messaging: [{ sender: { id: "PSID1" }, recipient: { id: "PAGINA" }, timestamp: 1_790_000_000_000, message: { mid, text: "Hola" } }] }] });
    const m = montarMeta();
    expect((await m.pedir(await firmado("/webhooks/meta", evento("m_1")), envMeta)).status).toBe(200);
    expect((await m.pedir(await firmado("/webhooks/meta", evento("ig_1", "instagram")), envMeta)).status).toBe(200);
    expect(m.conv.guardados.map((e) => [e.canal, e.id_mensaje])).toEqual([["messenger", "m_1"], ["instagram", "ig_1"]]);
    await m.despues();
    expect(m.conv.ingestados.map((e) => e.id_mensaje)).toEqual(["m_1", "ig_1"]);
    m.conv.fallaGuardar = "caído";
    const err = vi.spyOn(console, "error").mockImplementation(() => {});
    expect((await m.pedir(await firmado("/webhooks/meta", evento("m_2")), envMeta)).status).toBe(500);
    err.mockRestore();
  });

  it("Telegram y el puente QR siguen igual: no pasan por la bandeja", async () => {
    const m = montarMeta();
    const qr = await m.pedir(post("/webhooks/whatsapp-qr", { id_mensaje: "3EB0X", de: "50760261919@s.whatsapp.net", tipo: "texto", texto: "Hola", ts: 1_790_000_000 }, { "x-wa-token": WA_TOKEN }), envMeta);
    expect(qr.status).toBe(200);
    expect(m.conv.ingestados.map((e) => e.id_mensaje)).toEqual(["3EB0X"]); // QR: guardado ANTES del 200, como siempre
    const tg = await m.pedir(post("/webhooks/telegram", { update_id: 1, message: { message_id: 7, from: { id: 555, first_name: "K" }, chat: { id: 555, type: "private" }, date: 1_790_000_000, text: "hola" } }, { "x-telegram-bot-api-secret-token": SECRETO_TG }), envMeta);
    expect(tg.status).toBe(200);
    expect(m.conv.ingestados).toHaveLength(1); // Telegram: después del 200, como siempre
    await m.despues();
    expect(m.conv.ingestados.map((e) => e.canal)).toEqual(["whatsapp_qr", "telegram"]);
    expect(m.conv.guardados).toEqual([]);
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
