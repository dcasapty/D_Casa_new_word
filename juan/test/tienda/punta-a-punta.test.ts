/**
 * Brian de la tienda de punta a punta, con las clases REALES (el Worker, `TiendaSesion` y `Global`) sobre Durable Objects de mentira:
 * navegador (CORS + pase de Odoo) → sesión → topes en Global → la IA (la API de Claude, falsa, con herramientas) → Odoo (el binding
 * DCASA, falso) → respuesta con tarjetas. Y después: /salud, /odoo/costos y la limpieza a las 2 horas.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import worker from "../../src/index";
import type { Env } from "../../src/env";
import { olvidarCaches } from "../../src/odoo/fabrica";
import { TiendaSesion } from "../../src/tienda/do";
import { firmarPase } from "../../src/tienda/pase";
import { armarCluster, ctxFalso, dcasaFalso } from "../helpers/doFalso";

const INICIO = Date.parse("2026-11-13T16:00:00Z"); // viernes, 11:00 en Panamá
const TOKEN_WORKER = "token-del-worker-0123456789abcdef";
const TOKEN_ODOO = "token-de-odoo-0123456789abcdef";
const SID = "AAECAwQFBgcICQoLDA0ODw";
const ORIGEN = "https://dcasapty.com";

const COLCHON = { producto_id: 456, plantilla_id: 123, codigo: "DC-K7M4PX", nombre: "Colchón Queen Ortopédico", precio: 278, precio_texto: "$278.00 + ITBMS", mas_itbms: true, disponibilidad: "disponible", url: "https://dcasapty.com/shop/colchon-123", ruta: "/shop/colchon-123", foto: null, imagen: "/web/image/product.template/123/image_512", agregable: true, categorias: ["Colchones"] };

type BloqueClaude = { type: "text"; text: string } | { type: "tool_use"; id: string; name: string; input: unknown };
let claude: (cuerpo: any, n: number) => BloqueClaude[];
let alClaude: any[];

/** Un namespace de Durable Object con la clase REAL `TiendaSesion` (y `deleteAll` como el de workerd). */
function espacioDeLaTienda(env: () => Env) {
  const instancias = new Map<string, { instancia: TiendaSesion; ctx: ReturnType<typeof ctxFalso> }>();
  return {
    instancias,
    idFromName: (nombre: string) => ({ nombre }),
    get: (id: { nombre: string }) =>
      new Proxy({} as Record<string, unknown>, {
        get: (_o, metodo: string) => async (...args: unknown[]) => {
          let i = instancias.get(id.nombre);
          if (!i) {
            const ctx = ctxFalso();
            const storage = ctx.storage as unknown as Record<string, unknown>;
            storage.deleteAll = async () => {
              const tablas = ctx.storage.sql.exec("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'").toArray();
              for (const t of tablas) ctx.storage.sql.exec(`DROP TABLE "${String(t.name)}"`);
            };
            i = { instancia: new TiendaSesion(ctx as unknown as DurableObjectState, env()), ctx };
            instancias.set(id.nombre, i);
          }
          return (i.instancia as unknown as Record<string, (...a: unknown[]) => unknown>)[metodo](...args);
        },
      }),
  };
}

function escenario() {
  const odoo = dcasaFalso();
  odoo.estado.config = { ...odoo.estado.config, brian_tienda: { activo: true, presupuesto_mes_usd: 30, tope_sesion_hora: 20, tope_red_hora: 60, tope_dia: 1000 } };
  odoo.estado.herramienta = (nombre) => (nombre === "buscar_productos" ? { ok: true, resultado: { encontrados: 1, mostrados: 1, productos: [COLCHON] } } : { ok: true, resultado: {} });
  const cluster = armarCluster({ JUAN_ODOO_TOKEN: TOKEN_ODOO, JUAN_WORKER_TOKEN: TOKEN_WORKER, ANTHROPIC_API_KEY: "sk-ant-clave-de-prueba-0123456789", DCASA: odoo.fetcher, URL_SITIO: "https://dcasapty.com", URL_PUBLICA: "https://dcasa-juan.dcasapty.workers.dev" } as never);
  const tienda = espacioDeLaTienda(() => cluster.env);
  (cluster.env as unknown as Record<string, unknown>).TIENDA = tienda;
  const ctx = { waitUntil: () => {}, passThroughOnException() {} } as unknown as ExecutionContext;
  const pedir = (req: Request) => worker.fetch(req, cluster.env, ctx);
  const mensaje = async (cuerpo: unknown) =>
    pedir(
      new Request("https://dcasa-juan.dcasapty.workers.dev/tienda/v1/mensaje", {
        method: "POST",
        headers: {
          origin: ORIGEN,
          "content-type": "application/json",
          "cf-connecting-ip": "190.140.12.34",
          authorization: `Pase ${await firmarPase(TOKEN_WORKER, { v: 1, sid: SID, exp: Math.floor(Date.now() / 1000) + 1800, red: "190.140.12.0/24", sitio: 1 })}`,
        },
        body: JSON.stringify(cuerpo),
      }),
    );
  return { odoo, cluster, tienda, pedir, mensaje };
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(INICIO);
  olvidarCaches();
  alClaude = [];
  claude = (_c, n) =>
    n === 0
      ? [{ type: "tool_use", id: "toolu_1", name: "buscar_productos", input: { consulta: "colchón queen" } }]
      : [{ type: "tool_use", id: "toolu_2", name: "responder_tienda", input: { texto: "Mira este colchón queen; el precio es + ITBMS. ¿Para qué cuarto lo buscas?", productos: [456] } }];
  vi.stubGlobal("fetch", async (recurso: unknown, init?: RequestInit) => {
    const url = String(recurso);
    if (!url.startsWith("https://api.anthropic.com/")) throw new Error(`salida a la red no esperada: ${url}`);
    const cuerpo = JSON.parse(String(init?.body));
    alClaude.push(cuerpo);
    const content = claude(cuerpo, alClaude.length - 1);
    return Response.json({
      id: `msg_${alClaude.length}`,
      type: "message",
      role: "assistant",
      model: cuerpo.model,
      content,
      stop_reason: content.some((b) => b.type === "tool_use") ? "tool_use" : "end_turn",
      stop_sequence: null,
      usage: { input_tokens: 2000, output_tokens: 80, cache_creation_input_tokens: 0, cache_read_input_tokens: 0 },
    });
  });
  vi.spyOn(console, "log").mockImplementation(() => {});
  vi.spyOn(console, "warn").mockImplementation(() => {});
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("Brian de la tienda, de punta a punta", () => {
  it("un mensaje: CORS, pase, la IA con la lista blanca, Odoo sin conversación y la tarjeta con los datos de la herramienta", async () => {
    const e = escenario();
    const res = await e.mensaje({ texto: "busco un colchón queen", pagina: { tipo: "inicio" } });
    expect(res.status).toBe(200);
    expect(res.headers.get("access-control-allow-origin")).toBe(ORIGEN);
    const cuerpo = (await res.json()) as any;
    expect(cuerpo.ok).toBe(true);
    expect(cuerpo.bloques).toEqual([
      { tipo: "texto", texto: "Mira este colchón queen; el precio es + ITBMS. ¿Para qué cuarto lo buscas?" },
      { tipo: "productos", productos: [{ producto_id: 456, plantilla_id: 123, nombre: "Colchón Queen Ortopédico", precio_texto: "$278.00 + ITBMS", disponibilidad: "disponible", imagen: "/web/image/product.template/123/image_512", url: "/shop/colchon-123", agregable: true }], titulo: "Colchón queen" },
    ]);
    expect(cuerpo.pose).toBe("cama");
    // A Claude: solo las herramientas de la lista blanca (de las 13 de prueba que publica Odoo) y responder_tienda.
    const herramientas = alClaude[0].tools.map((t: { name: string }) => t.name).sort();
    expect(herramientas).toEqual(["buscar_conocimiento", "buscar_productos", "cotizar_envio", "horario_y_tienda", "listar_categorias", "reglas_socios", "responder_tienda", "ver_producto"]);
    // A Odoo: la herramienta sin conversacion_id, con origen «tienda», con el token de Odoo; y nada de /mensaje ni /escribiendo.
    const llamada = e.odoo.peticiones.find((p) => p.ruta === "/herramienta")!;
    expect(llamada.cuerpo).toEqual({ nombre: "buscar_productos", argumentos: { consulta: "colchón queen" }, origen: "tienda" });
    expect(llamada.auth).toBe(`Bearer ${TOKEN_ODOO}`);
    expect(e.odoo.peticiones.map((p) => p.ruta).filter((r) => r !== "/config" && r !== "/herramientas" && r !== "/herramienta")).toEqual([]);
  });

  it("/salud dice si está listo (sin cifras) y /odoo/costos trae su gasto aparte del de Juan", async () => {
    const e = escenario();
    await e.mensaje({ texto: "busco un colchón queen" });
    const salud = (await (await e.pedir(new Request("https://juan.example/salud"))).json()) as any;
    expect(salud.tienda).toEqual({ listo: true, activo: true, ajustes: "odoo", pase: true, ia: true, presupuesto: "disponible" });
    const costos = (await (await e.pedir(new Request("https://juan.example/odoo/costos", { headers: { authorization: `Bearer ${TOKEN_WORKER}` } }))).json()) as any;
    expect(costos.gasto_usd).toBe(0);
    expect(costos.turnos).toBe(0);
    expect(costos.por_modelo).toEqual([]);
    expect(costos.tienda).toMatchObject({ mes: "2026-11", turnos: 1, presupuesto_usd: 30, por_modelo: [{ modelo: "claude-haiku-4-5", proveedor: "anthropic", turnos: 1, estimado: false }] });
    expect(costos.tienda.usd).toBeGreaterThan(0);
    const conToken = (await (await e.pedir(new Request("https://juan.example/odoo/salud", { headers: { authorization: `Bearer ${TOKEN_WORKER}` } }))).json()) as any;
    expect(conToken.gasto_ia_mes_usd).toBe(0);
    expect(conToken.tienda).toMatchObject({ listo: true, presupuesto_usd: 30, agotado: false, turnos_hoy: 1, tope_dia: 1000 });
    expect(conToken.tienda.gasto_mes_usd).toBeGreaterThan(0);
  });

  it("a las 2 horas sin actividad la alarma de la sesión borra todo (de verdad: deleteAll)", async () => {
    const e = escenario();
    await e.mensaje({ texto: "busco un colchón queen" });
    const sesion = e.tienda.instancias.get(`tienda:${SID}`)!;
    expect(sesion.ctx.alarma).toBe(INICIO + 2 * 3600_000);
    expect(sesion.instancia.resumen().mensajes).toBe(2);
    vi.setSystemTime(INICIO + 2 * 3600_000);
    await sesion.instancia.alarm();
    expect(sesion.instancia.resumen()).toEqual({ mensajes: 0, vistos: 0, envios: 0 });
    expect(sesion.ctx.alarma).toBeNull();
  });

  it("apagado en Odoo (o un Odoo sin el módulo): «apagado» sin llamar a la IA, y /salud lo dice", async () => {
    const e = escenario();
    e.odoo.estado.config = { telegram_chats: [] };
    const res = await e.mensaje({ texto: "hola" });
    expect(res.status).toBe(503);
    expect(await res.json()).toEqual({ ok: false, motivo: "apagado" });
    expect(alClaude).toEqual([]);
    const salud = (await (await e.pedir(new Request("https://juan.example/salud"))).json()) as any;
    expect(salud.tienda).toMatchObject({ listo: false, activo: false, ajustes: "fabrica" });
  });
});
