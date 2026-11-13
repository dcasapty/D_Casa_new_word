/**
 * `POST /tienda/v1/mensaje` por el enrutador de verdad (rutas.ts → tienda/rutas.ts): CORS solo para los orígenes permitidos, el pase
 * (firma, vencimiento, red de la conexión) y el cuerpo. El Durable Object de la sesión es un doble que anota lo que recibe.
 */
import { describe, expect, it } from "vitest";
import { CONFIG_POR_DEFECTO, normalizarConfig, type Config } from "../../src/config";
import type { Env } from "../../src/env";
import { manejar, type DepsRutas } from "../../src/rutas";
import type { EntradaTienda, SalidaTienda } from "../../src/tienda/motor";
import { firmarPase } from "../../src/tienda/pase";

const TOKEN = "token-del-worker-de-prueba-0123456789abcdef";
const AHORA = Date.UTC(2026, 10, 13, 16, 0);
const SID = "AAECAwQFBgcICQoLDA0ODw";
const URL_MENSAJE = "https://dcasa-juan.dcasapty.workers.dev/tienda/v1/mensaje";
const ORIGEN = "https://dcasapty.com";

function montar(op: { config?: Config | (() => Promise<Config>); salida?: SalidaTienda; sinToken?: boolean; sinBinding?: boolean } = {}) {
  const recibidos: { nombre: string; entrada: EntradaTienda }[] = [];
  const config = op.config ?? normalizarConfig({ brian_tienda: { activo: true } });
  const env = {
    JUAN_WORKER_TOKEN: op.sinToken ? undefined : TOKEN,
    ...(op.sinBinding
      ? {}
      : {
          TIENDA: {
            idFromName: (n: string) => ({ n }),
            get: (id: { n: string }) => ({
              atender: async (entrada: EntradaTienda) => {
                recibidos.push({ nombre: id.n, entrada });
                return op.salida ?? { status: 200, cuerpo: { ok: true, pose: "saludando", bloques: [{ tipo: "texto", texto: "Con gusto." }], chips: [] } };
              },
            }),
          },
        }),
  } as unknown as Env;
  const d: DepsRutas = {
    adaptadores: [],
    config: typeof config === "function" ? config : async () => config,
    conversacion: () => {
      throw new Error("no se usa");
    },
    gastoMes: async () => 0,
    ahora: () => AHORA,
    esperarDespues: () => {},
  };
  return { env, d, recibidos, pedir: (req: Request) => manejar(req, env, d) };
}

const pase = (extra: Record<string, unknown> = {}) => firmarPase(TOKEN, { v: 1, sid: SID, exp: Math.floor(AHORA / 1000) + 1800, red: "190.140.12.0/24", sitio: 1, ...extra });

async function mensaje(cuerpo: unknown = { texto: "busco un colchón queen", pagina: { tipo: "inicio" } }, op: { origen?: string | null; ip?: string; autorizacion?: string } = {}) {
  const headers: Record<string, string> = { "content-type": "application/json", "cf-connecting-ip": op.ip ?? "190.140.12.34", authorization: op.autorizacion ?? `Pase ${await pase()}` };
  if (op.origen !== null) headers.origin = op.origen ?? ORIGEN;
  return new Request(URL_MENSAJE, { method: "POST", headers, body: typeof cuerpo === "string" ? cuerpo : JSON.stringify(cuerpo) });
}

describe("CORS: solo la tienda puede llamar desde el navegador", () => {
  it("el preflight (OPTIONS) de un origen permitido: 204 con las cabeceras", async () => {
    const m = montar();
    for (const origen of ["https://dcasapty.com", "https://www.dcasapty.com", "https://dcasa-staging.dcasapty.workers.dev"]) {
      const res = await m.pedir(new Request(URL_MENSAJE, { method: "OPTIONS", headers: { origin: origen, "access-control-request-method": "POST", "access-control-request-headers": "authorization, content-type" } }));
      expect(res.status).toBe(204);
      expect(res.headers.get("access-control-allow-origin")).toBe(origen);
      expect(res.headers.get("access-control-allow-methods")).toBe("POST, OPTIONS");
      expect(res.headers.get("access-control-allow-headers")).toBe("authorization, content-type");
      expect(res.headers.get("vary")).toBe("Origin");
    }
  });

  it("otro origen, un origen parecido o sin origen: 403 sin cabeceras CORS (ni en el preflight ni en el POST)", async () => {
    const m = montar();
    for (const origen of ["https://evil.example", "http://dcasapty.com", "https://dcasapty.com.evil.example", "https://evildcasapty.com", "null"]) {
      const pre = await m.pedir(new Request(URL_MENSAJE, { method: "OPTIONS", headers: { origin: origen } }));
      expect(pre.status).toBe(403);
      expect(pre.headers.get("access-control-allow-origin")).toBeNull();
      const post = await m.pedir(await mensaje(undefined, { origen }));
      expect(post.status).toBe(403);
      expect(post.headers.get("access-control-allow-origin")).toBeNull();
    }
    expect((await m.pedir(await mensaje(undefined, { origen: null }))).status).toBe(403);
    expect(m.recibidos).toEqual([]);
  });

  it("los orígenes se pueden cambiar desde Odoo (brian_tienda.origenes)", async () => {
    const m = montar({ config: normalizarConfig({ brian_tienda: { activo: true, origenes: ["https://tienda-nueva.dcasapty.com"] } }) });
    expect((await m.pedir(await mensaje(undefined, { origen: "https://tienda-nueva.dcasapty.com" }))).status).toBe(200);
    expect((await m.pedir(await mensaje(undefined, { origen: "https://dcasapty.com" }))).status).toBe(403);
  });

  it("si Odoo tarda en dar la configuración, el preflight no espera: usa los orígenes de fábrica", async () => {
    const m = montar({ config: () => new Promise<Config>(() => {}) });
    const res = await m.pedir(new Request(URL_MENSAJE, { method: "OPTIONS", headers: { origin: ORIGEN } }));
    expect(res.status).toBe(204);
  }, 5_000);

  it("con la configuración de fábrica (Odoo nunca contestó), los orígenes de fábrica", async () => {
    const m = montar({ config: CONFIG_POR_DEFECTO });
    const res = await m.pedir(new Request(URL_MENSAJE, { method: "OPTIONS", headers: { origin: ORIGEN } }));
    expect(res.status).toBe(204);
  });
});

describe("el pase", () => {
  it("válido: la sesión recibe la petición (un objeto por sid) con la red ofuscada, nunca la IP", async () => {
    const m = montar();
    const res = await m.pedir(await mensaje());
    expect(res.status).toBe(200);
    expect(res.headers.get("access-control-allow-origin")).toBe(ORIGEN);
    expect(res.headers.get("cache-control")).toBe("no-store");
    expect(await res.json()).toEqual({ ok: true, pose: "saludando", bloques: [{ tipo: "texto", texto: "Con gusto." }], chips: [] });
    expect(m.recibidos).toHaveLength(1);
    expect(m.recibidos[0].nombre).toBe(`tienda:${SID}`);
    expect(m.recibidos[0].entrada.red).toMatch(/^[0-9a-f]{32}$/);
    expect(JSON.stringify(m.recibidos[0].entrada)).not.toContain("190.140.12");
  });

  it("la misma red da la misma llave (el tope por red funciona) y otra red, otra", async () => {
    const m = montar();
    await m.pedir(await mensaje(undefined, { ip: "190.140.12.34" }));
    await m.pedir(await mensaje(undefined, { ip: "190.140.12.99" }));
    const otra = await firmarPase(TOKEN, { v: 1, sid: SID, exp: Math.floor(AHORA / 1000) + 1800, red: "190.140.99.0/24", sitio: 1 });
    await m.pedir(await mensaje(undefined, { ip: "190.140.99.1", autorizacion: `Pase ${otra}` }));
    const [a, b, c] = m.recibidos.map((r) => r.entrada.red);
    expect(a).toBe(b);
    expect(c).not.toBe(a);
  });

  it("vencido, de otra red, alterado, sin pase o sin token en el Worker: 401 «pase» (con CORS, para que la página lo lea)", async () => {
    const m = montar();
    const casos = [
      await mensaje(undefined, { autorizacion: `Pase ${await pase({ exp: Math.floor(AHORA / 1000) - 10 })}` }),
      await mensaje(undefined, { ip: "200.1.1.1" }),
      await mensaje(undefined, { autorizacion: `Pase ${(await pase()).replace(/.$/, (c) => (c === "A" ? "B" : "A"))}` }),
      await mensaje(undefined, { autorizacion: "" }),
    ];
    for (const req of casos) {
      const res = await m.pedir(req);
      expect(res.status).toBe(401);
      expect(res.headers.get("access-control-allow-origin")).toBe(ORIGEN);
      expect(await res.json()).toEqual({ ok: false, motivo: "pase" });
    }
    const sinToken = montar({ sinToken: true });
    expect((await sinToken.pedir(await mensaje())).status).toBe(401);
    expect(m.recibidos).toEqual([]);
  });
});

describe("el cuerpo", () => {
  it("un texto de más de 500 letras: 400 «fallo»", async () => {
    const m = montar();
    const res = await m.pedir(await mensaje({ texto: "a".repeat(501) }));
    expect(res.status).toBe(400);
    expect(await res.json()).toMatchObject({ ok: false, motivo: "fallo" });
    expect((await m.pedir(await mensaje({ texto: "á".repeat(500) }))).status).toBe(200);
  });

  it("un cuerpo que no es JSON, vacío o demasiado grande: 400", async () => {
    const m = montar();
    for (const cuerpo of ["no es json", "", JSON.stringify({ texto: "hola", relleno: "x".repeat(20_000) }), JSON.stringify({})]) {
      expect((await m.pedir(await mensaje(cuerpo))).status).toBe(400);
    }
    expect(m.recibidos).toEqual([]);
  });

  it("la acción va en lugar del texto; la ubicación puede ir sola; la página y el carrito se limpian", async () => {
    const m = montar();
    await m.pedir(await mensaje({ texto: "esto se ignora", accion: { tipo: "chip", valor: "Colchones" } }));
    await m.pedir(await mensaje({ ubicacion: { lat: 8.88, lon: -79.78 } }));
    await m.pedir(await mensaje({ texto: "hola", pagina: { tipo: "rara", producto_id: "x", categoria: "Camas\n<script>" }, carrito: { lineas: [{ producto_id: 1, nombre: "  Cama\u0000 Queen ", cantidad: 2 }, { nombre: "", cantidad: 1 }, "x"] } }));
    const [chip, ubicacion, limpio] = m.recibidos.map((r) => r.entrada.peticion);
    expect(chip).toMatchObject({ texto: "", accion: { tipo: "chip", valor: "Colchones" } });
    expect(ubicacion).toMatchObject({ texto: "", accion: null, ubicacion: { lat: 8.88, lon: -79.78 } });
    expect(limpio.pagina).toEqual({ tipo: "otra", producto_id: null, categoria: "Camas <script>" });
    expect(limpio.carrito).toEqual([{ producto_id: 1, nombre: "Cama Queen", cantidad: 2 }]);
  });

  it("acciones y ubicaciones mal formadas: 400", async () => {
    const m = montar();
    for (const cuerpo of [
      { accion: { tipo: "calificar", estrellas: 6 } },
      { accion: { tipo: "confirmar_carrito", producto_id: 1, cantidad: 21, resultado: "ok" } },
      { accion: { tipo: "confirmar_carrito", producto_id: 1, cantidad: 1, resultado: "tal vez" } },
      { accion: { tipo: "borrar_todo" } },
      { ubicacion: { lat: 200, lon: 0 } },
      { ubicacion: { lat: "8.8", lon: "-79" } },
    ]) {
      expect((await m.pedir(await mensaje(cuerpo))).status).toBe(400);
    }
  });

  it("los topes de la sesión llegan con Retry-After; solo POST", async () => {
    const m = montar({ salida: { status: 429, cuerpo: { ok: false, motivo: "tope_sesion" }, reintentarEn: 120 } });
    const res = await m.pedir(await mensaje());
    expect(res.status).toBe(429);
    expect(res.headers.get("retry-after")).toBe("120");
    expect(res.headers.get("access-control-expose-headers")).toBe("retry-after");
    expect(await res.json()).toEqual({ ok: false, motivo: "tope_sesion" });
    const get = await m.pedir(new Request(URL_MENSAJE, { headers: { origin: ORIGEN } }));
    expect(get.status).toBe(405);
  });

  it("otra ruta bajo /tienda/ no existe", async () => {
    const m = montar();
    expect((await m.pedir(new Request("https://juan.example/tienda/v1/otra", { method: "POST", headers: { origin: ORIGEN } }))).status).toBe(404);
  });
});
