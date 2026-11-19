import { describe, expect, it, vi } from "vitest";

import { cubetaDe, esEscaner, esSondeo } from "../src/bots";
import {
  SECRETOS_PARA_ARRANCAR,
  VARIABLES_DEL_CONTENEDOR,
  handleRequest,
  respuestaArrancando,
  respuestaSalud,
  secretosFaltantes,
  variablesDelContenedor,
} from "../src/handler";
import { esAssetCacheable, isBlockedPath, rutaEstatica, route } from "../src/routing";
// Vite entrega el archivo como texto (ver test/raw.d.ts).
import wranglerJsonc from "../wrangler.jsonc?raw";

// Claves inventadas para la prueba (no son de nadie).
const LLAVE = "LLAVE-DE-PRUEBA-0001-NO-ES-REAL";
const USUARIO = "USUARIO-DE-PRUEBA-0002-NO-ES-REAL";
const CLAVE = "CLAVE-DE-PRUEBA-0003-NO-ES-REAL";
const TILOPAY = { TILOPAY_API_KEY: LLAVE, TILOPAY_API_USER: USUARIO, TILOPAY_API_PASSWORD: CLAVE, TILOPAY_ENTORNO: "prueba" };
const SECRETOS = {
  ADMIN_PASSWORD: "clave-admin",
  R2_ENDPOINT: "https://cuenta.r2.cloudflarestorage.com",
  R2_BUCKET: "dcasa-respaldos",
  R2_ACCESS_KEY_ID: "id",
  R2_SECRET_ACCESS_KEY: "secreto",
  PGBACKREST_CIPHER_PASS: "cifrado",
};
const NOMBRES = ["TILOPAY_API_KEY", "TILOPAY_API_USER", "TILOPAY_API_PASSWORD", "TILOPAY_ENTORNO"];

describe("variables de Tilopay (docs/TILOPAY.md §6)", () => {
  it("viajan al contenedor cuando existen; vacías o ausentes no se pasan", () => {
    for (const nombre of NOMBRES) expect(VARIABLES_DEL_CONTENEDOR).toContain(nombre);
    const llegan = variablesDelContenedor({ ...SECRETOS, ...TILOPAY });
    expect(llegan).toMatchObject(TILOPAY);
    for (const nombre of NOMBRES) {
      expect(variablesDelContenedor({ ...SECRETOS, ...TILOPAY, [nombre]: "" })).not.toHaveProperty(nombre);
      const sin = { ...SECRETOS, ...TILOPAY } as Record<string, string>;
      delete sin[nombre];
      expect(variablesDelContenedor(sin)).not.toHaveProperty(nombre);
    }
    for (const nombre of NOMBRES) expect(variablesDelContenedor(SECRETOS)).not.toHaveProperty(nombre);
  });

  it("son opcionales: sin ellas el contenedor arranca igual", () => {
    for (const nombre of NOMBRES) expect(SECRETOS_PARA_ARRANCAR).not.toContain(nombre);
    expect(secretosFaltantes(SECRETOS)).toEqual([]);
    expect(secretosFaltantes({ ...SECRETOS, ...TILOPAY })).toEqual([]);
  });

  it("las claves nunca aparecen en una respuesta al navegador (salud, arranque, ni lo que contesta Odoo)", async () => {
    const env = { ...SECRETOS, ...TILOPAY };
    const respuestas: Response[] = [
      respuestaSalud({ contenedor: "stopped", faltan: secretosFaltantes({ ...env, R2_BUCKET: "" }) }),
      respuestaSalud({ contenedor: "healthy", faltan: secretosFaltantes(env), odoo: { status: 200, cuerpo: '{"base":"ok"}' } }),
      respuestaArrancando(new Request("https://dcasapty.com/shop")),
    ];
    const forward = vi.fn(async () => new Response("<html>tienda</html>", { status: 200 }));
    respuestas.push(
      await handleRequest(new Request("https://dcasapty.com/__edge/health"), {
        forward,
        salud: async () => ({ contenedor: "healthy", faltan: secretosFaltantes(env), odoo: { status: 200 } }),
      }),
      await handleRequest(new Request("https://dcasapty.com/shop"), { forward }),
    );
    for (const respuesta of respuestas) {
      const texto = await respuesta.text();
      const cabeceras = JSON.stringify([...respuesta.headers.entries()]);
      for (const secreto of [LLAVE, USUARIO, CLAVE]) {
        expect(texto).not.toContain(secreto);
        expect(cabeceras).not.toContain(secreto);
      }
      for (const nombre of NOMBRES) expect(texto).not.toContain(nombre);
    }
  });

  it("producción no fija TILOPAY_ENTORNO en el código (la dueña lo cambia en el panel); staging sí, en «prueba»", () => {
    const sinComentarios = wranglerJsonc
      .split("\n")
      .filter((linea: string) => !linea.trim().startsWith("//"))
      .join("\n");
    const config = JSON.parse(sinComentarios) as { vars: Record<string, string>; env: { staging: { vars: Record<string, string> } } };
    expect(config.vars).not.toHaveProperty("TILOPAY_ENTORNO");
    expect(config.env.staging.vars.TILOPAY_ENTORNO).toBe("prueba");
    for (const nombre of ["TILOPAY_API_KEY", "TILOPAY_API_USER", "TILOPAY_API_PASSWORD"]) {
      expect(config.vars).not.toHaveProperty(nombre);
      expect(config.env.staging.vars).not.toHaveProperty(nombre);
    }
  });
});

describe("/payment/tilopay/* pasa al origen (retorno del cliente y aviso del servidor)", () => {
  const rutas = [
    "/payment/tilopay/return",
    "/payment/tilopay/webhook",
    "/es/payment/tilopay/webhook",
    "/es_419/payment/tilopay/return",
    "//payment//tilopay//webhook",
    "/payment/%74ilopay/webhook",
    "/PAYMENT/Tilopay/Webhook",
  ];

  it("va a Odoo, no está bloqueada y nunca es cacheable (GET ni POST)", () => {
    for (const ruta of rutas) {
      for (const metodo of ["GET", "POST"]) {
        const url = new URL(`https://dcasapty.com${ruta}?code=1&order=S00012-1-3fa9c2e1&OrderHash=b02927cb`);
        expect(isBlockedPath(url.pathname), ruta).toBe(false);
        expect(route(url, metodo, "dcasapty.com"), `${metodo} ${ruta}`).toEqual({ kind: "origin", cacheable: false });
      }
    }
  });

  it("no está entre las páginas guardadas ni entre los assets que se cachean", () => {
    for (const ruta of rutas) {
      expect(rutaEstatica(new URL(`https://dcasapty.com${ruta}`), "GET"), ruta).toBeNull();
      expect(esAssetCacheable(ruta), ruta).toBe(false);
    }
    // Lo demás del módulo de pagos de Odoo (estáticos) sigue cacheándose igual que antes.
    expect(esAssetCacheable("/payment/static/img/card.png")).toBe(true);
    expect(esAssetCacheable("/dcasa_pago_tilopay/static/description/icon.png")).toBe(true);
  });

  it("no la toman por sondeo ni por escáner, y no tiene freno de ritmo (Tilopay manda desde pocas IP, sin cookies)", () => {
    for (const ruta of rutas) {
      expect(esSondeo(ruta), ruta).toBe(false);
      expect(cubetaDe("POST", ruta), ruta).toBeNull();
      expect(cubetaDe("GET", ruta), ruta).toBeNull();
    }
    for (const agente of ["Tilopay/1.0", "Guzzle/7 (PHP)", "python-requests/2.31", "curl/8.4", null]) {
      expect(esEscaner(agente), String(agente)).toBe(false);
    }
  });

  it("con Odoo: un POST sin cookies llega entero (cuerpo y tipo), una sola vez, sin tocar ninguna caché", async () => {
    const cuerpo = JSON.stringify({ orderNumber: "S00012-1-3fa9c2e1", code: "1" });
    const recibidas: { metodo: string; cuerpo: string; tipo: string | null; cookie: string | null; ruta: string }[] = [];
    const forward = vi.fn(async (pedido: Request) => {
      recibidas.push({
        metodo: pedido.method,
        cuerpo: await pedido.text(),
        tipo: pedido.headers.get("Content-Type"),
        cookie: pedido.headers.get("Cookie"),
        ruta: new URL(pedido.url).pathname,
      });
      return new Response('{"estado": "ok"}', { status: 200, headers: { "Content-Type": "application/json" } });
    });
    const cache = { match: vi.fn(async () => undefined), put: vi.fn(async () => undefined) };
    const almacen = {
      leer: vi.fn(async () => null),
      escribir: vi.fn(async () => undefined),
      leerBinario: vi.fn(async () => null),
      escribirBinario: vi.fn(async () => undefined),
      meta: vi.fn(async () => null),
    };
    const respuesta = await handleRequest(
      new Request("https://dcasapty.com/payment/tilopay/webhook", {
        method: "POST",
        body: cuerpo,
        headers: { "Content-Type": "application/json", "User-Agent": "Guzzle/7" },
      }),
      { forward, cache, canonicalHost: "dcasapty.com", tienda: { activa: true, almacen, token: "t".repeat(40) } },
    );
    expect(respuesta.status).toBe(200);
    expect(await respuesta.text()).toBe('{"estado": "ok"}');
    expect(forward).toHaveBeenCalledTimes(1);
    expect(recibidas[0]).toEqual({
      metodo: "POST", cuerpo, tipo: "application/json", cookie: null, ruta: "/payment/tilopay/webhook",
    });
    expect(cache.put).not.toHaveBeenCalled();
    expect(almacen.escribir).not.toHaveBeenCalled();
    expect(almacen.leer).not.toHaveBeenCalled();
  });

  it("el retorno (GET) y el aviso (POST) llegan a Odoo con la puerta del equipo en modo obligatorio", async () => {
    const puerta = {
      config: { ruta: "/entrada-k7q2m9x4", secreto: "s".repeat(40), equipo: "https://dcasa.cloudflareaccess.com", aud: "a".repeat(64), horas: 12 },
      modo: "1" as const,
      exigirCorreo: false,
    };
    const forward = vi.fn(async () => new Response(null, { status: 303, headers: { Location: "/payment/status" } }));
    const retorno = await handleRequest(
      new Request("https://dcasapty.com/payment/tilopay/return?code=1&order=S00012-1-3fa9c2e1&OrderHash=b02927cb"),
      { forward, canonicalHost: "dcasapty.com", puerta },
    );
    expect(retorno.status).toBe(303);
    expect(new URL((forward.mock.calls[0] as unknown as [Request])[0].url).search).toBe(
      "?code=1&order=S00012-1-3fa9c2e1&OrderHash=b02927cb",
    );
    const aviso = await handleRequest(
      new Request("https://dcasapty.com/payment/tilopay/webhook", { method: "POST", body: "{}" }),
      { forward, canonicalHost: "dcasapty.com", puerta },
    );
    expect(aviso.status).toBe(303);
    expect(forward).toHaveBeenCalledTimes(2);
    // Y el panel sí sigue cerrado con esa misma puerta (la prueba de que la puerta de verdad estaba puesta).
    const panel = await handleRequest(new Request("https://dcasapty.com/odoo"), { forward, canonicalHost: "dcasapty.com", puerta });
    expect(panel.status).toBe(404);
    expect(forward).toHaveBeenCalledTimes(2);
  });

  it("200 avisos seguidos no chocan con ningún freno del borde", async () => {
    const forward = vi.fn(async () => new Response('{"estado": "ok"}', { status: 200 }));
    for (let i = 0; i < 200; i++) {
      const respuesta = await handleRequest(
        new Request("https://dcasapty.com/payment/tilopay/webhook", { method: "POST", body: "{}" }),
        { forward },
      );
      expect(respuesta.status).toBe(200);
    }
    expect(forward).toHaveBeenCalledTimes(200);
  });

  it("un POST a Odoo que se corta NO se repite desde el borde (podría confirmar dos veces)", async () => {
    const forward = vi.fn(async () => {
      throw new Error("Network connection lost.");
    });
    const respuesta = await handleRequest(
      new Request("https://dcasapty.com/payment/tilopay/webhook", { method: "POST", body: "{}" }),
      { forward, esperar: async () => undefined },
    );
    expect(forward).toHaveBeenCalledTimes(1);
    expect(respuesta.status).toBeGreaterThanOrEqual(500);
  });
});
