// Yappy directo (addons/dcasa_pago_yappy, docs/YAPPY.md): lo que el borde tiene que garantizar. El aviso de Yappy es un GET
// abierto (sin cookies, sin cuerpo): tiene que cruzar entero hasta Odoo, una sola vez, sin tocar ninguna caché, y las claves
// jamás pueden salir hacia el navegador. Las claves de abajo son inventadas (no son de nadie).
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
import { esAssetCacheable, forwardedHeaders, isBlockedPath, rutaEstatica, route } from "../src/routing";
// Vite entrega el archivo como texto (ver test/raw.d.ts).
import wranglerJsonc from "../wrangler.jsonc?raw";
import routingTs from "../src/routing.ts?raw";

const ID = "ID-COMERCIO-DE-PRUEBA-0001-NO-ES-REAL";
const CLAVE = "Y2xhdmUtaW52ZW50YWRhLnNlZ3VuZG8udGVyY2Vy";
const YAPPY = {
  YAPPY_ID_COMERCIO: ID,
  YAPPY_CLAVE_SECRETA: CLAVE,
  YAPPY_DOMINIO: "dcasapty.com",
  YAPPY_ENTORNO: "prueba",
  YAPPY_URL_BASE: "https://dcasa-staging.dcasapty.workers.dev",
};
const SECRETOS = {
  ADMIN_PASSWORD: "clave-admin",
  R2_ENDPOINT: "https://cuenta.r2.cloudflarestorage.com",
  R2_BUCKET: "dcasa-respaldos",
  R2_ACCESS_KEY_ID: "id",
  R2_SECRET_ACCESS_KEY: "secreto",
  PGBACKREST_CIPHER_PASS: "cifrado",
};
const NOMBRES = ["YAPPY_ID_COMERCIO", "YAPPY_CLAVE_SECRETA", "YAPPY_DOMINIO", "YAPPY_ENTORNO", "YAPPY_URL_BASE"];
const AVISO = "orderId=S0012X7KQ2&status=E&domain=dcasapty.com&hash=b02927cb4f0a9c1d&confirmationNumber=CONF-123";

describe("variables de Yappy directo (docs/YAPPY.md)", () => {
  it("viajan al contenedor cuando existen; vacías o ausentes no se pasan", () => {
    for (const nombre of NOMBRES) expect(VARIABLES_DEL_CONTENEDOR).toContain(nombre);
    expect(variablesDelContenedor({ ...SECRETOS, ...YAPPY })).toMatchObject(YAPPY);
    for (const nombre of NOMBRES) {
      expect(variablesDelContenedor({ ...SECRETOS, ...YAPPY, [nombre]: "" })).not.toHaveProperty(nombre);
      const sin = { ...SECRETOS, ...YAPPY } as Record<string, string>;
      delete sin[nombre];
      expect(variablesDelContenedor(sin)).not.toHaveProperty(nombre);
    }
    for (const nombre of NOMBRES) expect(variablesDelContenedor(SECRETOS)).not.toHaveProperty(nombre);
  });

  it("son opcionales: sin ellas el contenedor arranca igual", () => {
    for (const nombre of NOMBRES) expect(SECRETOS_PARA_ARRANCAR).not.toContain(nombre);
    expect(secretosFaltantes(SECRETOS)).toEqual([]);
    expect(secretosFaltantes({ ...SECRETOS, ...YAPPY })).toEqual([]);
  });

  it("las claves nunca aparecen en una respuesta al navegador (salud, arranque, ni lo que contesta Odoo)", async () => {
    const env = { ...SECRETOS, ...YAPPY };
    const respuestas: Response[] = [
      respuestaSalud({ contenedor: "stopped", faltan: secretosFaltantes({ ...env, R2_BUCKET: "" }) }),
      respuestaSalud({ contenedor: "healthy", faltan: secretosFaltantes(env), odoo: { status: 200, cuerpo: '{"base":"ok"}' } }),
      respuestaArrancando(new Request("https://dcasapty.com/payment/yappy/ipn?" + AVISO)),
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
      for (const secreto of [ID, CLAVE]) {
        expect(texto).not.toContain(secreto);
        expect(cabeceras).not.toContain(secreto);
      }
      for (const nombre of NOMBRES) expect(texto).not.toContain(nombre);
    }
  });

  it("YAPPY_URL_BASE (la dirección a la que Yappy avisa) cruza al contenedor, tal cual, y no es secreta ni obligatoria", () => {
    expect(VARIABLES_DEL_CONTENEDOR).toContain("YAPPY_URL_BASE");
    expect(SECRETOS_PARA_ARRANCAR).not.toContain("YAPPY_URL_BASE");
    expect(variablesDelContenedor({ ...SECRETOS, YAPPY_URL_BASE: "https://dcasa-staging.dcasapty.workers.dev" })).toMatchObject({
      YAPPY_URL_BASE: "https://dcasa-staging.dcasapty.workers.dev",
    });
    expect(variablesDelContenedor({ ...SECRETOS, YAPPY_URL_BASE: "" })).not.toHaveProperty("YAPPY_URL_BASE");
    expect(variablesDelContenedor(SECRETOS)).not.toHaveProperty("YAPPY_URL_BASE");
    expect(secretosFaltantes(SECRETOS)).toEqual([]);
  });

  it("staging fija YAPPY_URL_BASE con SU dirección workers.dev (la de TIENDA_AVISO_URL, https y sin ruta); producción no la fija", () => {
    const sinComentarios = wranglerJsonc
      .split("\n")
      .filter((linea: string) => !linea.trim().startsWith("//"))
      .join("\n");
    const config = JSON.parse(sinComentarios) as {
      vars: Record<string, string>;
      workers_dev?: boolean;
      env: { staging: { name: string; vars: Record<string, string>; routes: unknown[] } };
    };
    const url = config.env.staging.vars.YAPPY_URL_BASE;
    expect(url).toMatch(/^https:\/\/[a-z0-9.-]+$/);
    // el Worker de staging: su nombre + el subdominio de la cuenta; la misma dirección que ya usa el aviso de la caché de páginas
    expect(new URL(config.env.staging.vars.TIENDA_AVISO_URL).origin).toBe(url);
    expect(new URL(url).hostname.startsWith(`${config.env.staging.name}.`)).toBe(true);
    expect(new URL(url).hostname.endsWith(".workers.dev")).toBe(true);
    // y esa dirección existe de verdad: staging no tiene dominio propio (routes vacío) y workers.dev sigue respondiendo
    expect(config.env.staging.routes).toEqual([]);
    expect(config.workers_dev).toBe(true);
    expect(config.vars).not.toHaveProperty("YAPPY_URL_BASE");
  });

  it("producción no fija YAPPY_ENTORNO en el código (la dueña lo cambia en el panel); staging sí, en «prueba»", () => {
    const sinComentarios = wranglerJsonc
      .split("\n")
      .filter((linea: string) => !linea.trim().startsWith("//"))
      .join("\n");
    const config = JSON.parse(sinComentarios) as { vars: Record<string, string>; env: { staging: { vars: Record<string, string> } } };
    expect(config.vars).not.toHaveProperty("YAPPY_ENTORNO");
    expect(config.env.staging.vars.YAPPY_ENTORNO).toBe("prueba");
    // Ni el id ni la clave ni el dominio viven en el repositorio (es público): solo el panel de Cloudflare.
    for (const nombre of ["YAPPY_ID_COMERCIO", "YAPPY_CLAVE_SECRETA", "YAPPY_DOMINIO"]) {
      expect(config.vars).not.toHaveProperty(nombre);
      expect(config.env.staging.vars).not.toHaveProperty(nombre);
    }
    expect(sinComentarios).not.toMatch(/YAPPY_(ID_COMERCIO|CLAVE_SECRETA|DOMINIO)/);
  });
});

describe("/payment/yappy/* pasa al origen (el arranque del pago y el aviso del servidor de Yappy)", () => {
  const rutas = [
    "/payment/yappy/ipn",
    "/payment/yappy/iniciar",
    "/es/payment/yappy/ipn",
    "/es_419/payment/yappy/iniciar",
    "//payment//yappy//ipn",
    "/payment/%79appy/ipn",
    "/PAYMENT/Yappy/IPN",
  ];

  it("va a Odoo, no está bloqueada y nunca es cacheable (GET, HEAD ni POST)", () => {
    for (const ruta of rutas) {
      for (const metodo of ["GET", "HEAD", "POST"]) {
        const url = new URL(`https://dcasapty.com${ruta}?${AVISO}`);
        expect(isBlockedPath(url.pathname), ruta).toBe(false);
        expect(route(url, metodo, "dcasapty.com"), `${metodo} ${ruta}`).toEqual({ kind: "origin", cacheable: false });
      }
    }
  });

  it("segunda cerradura: la ruta está en NEVER_CACHE_PREFIXES (hoy ningún patrón de assets la tomaría; esto avisa si alguien la quita)", () => {
    const lista = /const NEVER_CACHE_PREFIXES = \[([^\]]*)\]/.exec(routingTs);
    expect(lista, "no se encontró NEVER_CACHE_PREFIXES").not.toBeNull();
    expect(lista![1]).toContain('"/payment/yappy/"');
    expect(lista![1]).toContain('"/payment/tilopay/"');
  });

  it("ninguna variante rara se vuelve cacheable ni cae en una ruta bloqueada", () => {
    const raras = [
      "/payment/yappy/ipn.css",
      "/payment/yappy/ipn.png?unique=abc",
      "/payment/yappy/../yappy/ipn",
      "/%70ayment/yappy/ipn",
      "/payment/%2e%2e/payment/yappy/ipn",
      "/es/payment/yappy/ipn.js",
      "/payment/yappy/static/x.png",
    ];
    for (const ruta of raras) {
      for (const metodo of ["GET", "HEAD", "POST"]) {
        const url = new URL(`https://dcasapty.com${ruta}`);
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
    // Lo estático del módulo (el script y los estilos del botón) sí se sigue cacheando como cualquier asset de Odoo.
    expect(esAssetCacheable("/payment/static/img/card.png")).toBe(true);
    expect(esAssetCacheable("/dcasa_pago_yappy/static/description/icon.png")).toBe(true);
  });

  it("no la toman por sondeo ni por escáner, y no tiene freno de ritmo del borde (Yappy manda desde pocas IP, sin cookies)", () => {
    for (const ruta of rutas) {
      expect(esSondeo(ruta), ruta).toBe(false);
      expect(cubetaDe("POST", ruta), ruta).toBeNull();
      expect(cubetaDe("GET", ruta), ruta).toBeNull();
    }
    for (const agente of ["Java/17.0.2", "okhttp/4.12.0", "Apache-HttpClient/4.5", "Guzzle/7 (PHP)", "python-requests/2.31", "curl/8.4", null]) {
      expect(esEscaner(agente), String(agente)).toBe(false);
    }
  });

  it("el aviso (GET abierto) llega entero a Odoo: ruta, cada parámetro y la firma, sin cookies, una sola vez, sin tocar la caché", async () => {
    const recibidas: { metodo: string; url: string; cookie: string | null }[] = [];
    const forward = vi.fn(async (pedido: Request) => {
      recibidas.push({ metodo: pedido.method, url: pedido.url, cookie: pedido.headers.get("Cookie") });
      return new Response("ok", { status: 200, headers: { "Content-Type": "text/plain", "Cache-Control": "public, max-age=3600" } });
    });
    const cache = { match: vi.fn(async () => undefined), put: vi.fn(async () => undefined) };
    const almacen = {
      leer: vi.fn(async () => null),
      escribir: vi.fn(async () => undefined),
      leerBinario: vi.fn(async () => null),
      escribirBinario: vi.fn(async () => undefined),
      meta: vi.fn(async () => null),
    };
    const respuesta = await handleRequest(new Request(`https://dcasapty.com/payment/yappy/ipn?${AVISO}`), {
      forward,
      cache,
      canonicalHost: "dcasapty.com",
      tienda: { activa: true, almacen, token: "t".repeat(40) },
    });
    expect(respuesta.status).toBe(200);
    expect(await respuesta.text()).toBe("ok");
    expect(forward).toHaveBeenCalledTimes(1);
    expect(recibidas[0].metodo).toBe("GET");
    expect(recibidas[0].cookie).toBeNull();
    const url = new URL(recibidas[0].url);
    expect(url.pathname).toBe("/payment/yappy/ipn");
    expect(url.search).toBe(`?${AVISO}`);
    // Aunque Odoo dijera «public», el borde no lo guarda ni lo consulta.
    expect(cache.put).not.toHaveBeenCalled();
    expect(cache.match).not.toHaveBeenCalled();
    expect(almacen.escribir).not.toHaveBeenCalled();
    expect(almacen.leer).not.toHaveBeenCalled();
  });

  it("dos avisos seguidos con la misma orden y firma no se mezclan ni se sirven de una copia", async () => {
    let vez = 0;
    const forward = vi.fn(async () => new Response(`respuesta-${++vez}`, { status: 200, headers: { "Cache-Control": "public, max-age=600" } }));
    const cache = { match: vi.fn(async () => undefined), put: vi.fn(async () => undefined) };
    const a = await handleRequest(new Request(`https://dcasapty.com/payment/yappy/ipn?${AVISO}`), { forward, cache });
    const b = await handleRequest(new Request(`https://dcasapty.com/payment/yappy/ipn?${AVISO}`), { forward, cache });
    expect(await a.text()).toBe("respuesta-1");
    expect(await b.text()).toBe("respuesta-2");
    expect(forward).toHaveBeenCalledTimes(2);
    expect(cache.put).not.toHaveBeenCalled();
  });

  it("el arranque del pago (POST JSON del navegador) llega entero y su respuesta, que trae un token, no se guarda", async () => {
    const cuerpo = JSON.stringify({ jsonrpc: "2.0", method: "call", params: { reference: "S00012-1", celular: "60000101" } });
    const recibidas: { metodo: string; cuerpo: string; tipo: string | null; ruta: string }[] = [];
    const forward = vi.fn(async (pedido: Request) => {
      recibidas.push({
        metodo: pedido.method,
        cuerpo: await pedido.text(),
        tipo: pedido.headers.get("Content-Type"),
        ruta: new URL(pedido.url).pathname,
      });
      return new Response('{"result": {"ok": true, "token": "token-de-un-solo-pago"}}', {
        status: 200,
        headers: { "Content-Type": "application/json", "Cache-Control": "public, max-age=3600" },
      });
    });
    const cache = { match: vi.fn(async () => undefined), put: vi.fn(async () => undefined) };
    const respuesta = await handleRequest(
      new Request("https://dcasapty.com/payment/yappy/iniciar", {
        method: "POST",
        body: cuerpo,
        headers: { "Content-Type": "application/json", Cookie: "session_id=abc" },
      }),
      { forward, cache, canonicalHost: "dcasapty.com" },
    );
    expect(respuesta.status).toBe(200);
    expect(forward).toHaveBeenCalledTimes(1);
    expect(recibidas[0]).toEqual({ metodo: "POST", cuerpo, tipo: "application/json", ruta: "/payment/yappy/iniciar" });
    expect(cache.put).not.toHaveBeenCalled();
  });

  it("el aviso llega a Odoo con la puerta del equipo en modo obligatorio, y el panel sigue cerrado con esa misma puerta", async () => {
    const puerta = {
      config: { ruta: "/entrada-k7q2m9x4", secreto: "s".repeat(40), equipo: "https://dcasa.cloudflareaccess.com", aud: "a".repeat(64), horas: 12 },
      modo: "1" as const,
      exigirCorreo: false,
    };
    const forward = vi.fn(async () => new Response("ok", { status: 200 }));
    const aviso = await handleRequest(new Request(`https://dcasapty.com/payment/yappy/ipn?${AVISO}`), {
      forward,
      canonicalHost: "dcasapty.com",
      puerta,
    });
    expect(aviso.status).toBe(200);
    expect(forward).toHaveBeenCalledTimes(1);
    expect(new URL((forward.mock.calls[0] as unknown as [Request])[0].url).search).toBe(`?${AVISO}`);
    const panel = await handleRequest(new Request("https://dcasapty.com/odoo"), { forward, canonicalHost: "dcasapty.com", puerta });
    expect(panel.status).toBe(404);
    expect(forward).toHaveBeenCalledTimes(1);
  });

  it("200 avisos seguidos no chocan con ningún freno del borde", async () => {
    const forward = vi.fn(async () => new Response("ok", { status: 200 }));
    for (let i = 0; i < 200; i++) {
      const respuesta = await handleRequest(new Request(`https://dcasapty.com/payment/yappy/ipn?${AVISO}`), { forward });
      expect(respuesta.status).toBe(200);
    }
    expect(forward).toHaveBeenCalledTimes(200);
  });
});

describe("Yappy: cuando Odoo no está listo el aviso NO se da por recibido", () => {
  it("Odoo caído o arrancando: el borde contesta 503 con Retry-After (nunca 200) para que Yappy pueda reintentar", async () => {
    const forward = vi.fn(async () => {
      throw new Error("Network connection lost.");
    });
    const respuesta = await handleRequest(new Request(`https://dcasapty.com/payment/yappy/ipn?${AVISO}`), {
      forward,
      esperar: async () => undefined,
    });
    expect(respuesta.status).toBe(503);
    expect(respuesta.headers.get("Retry-After")).not.toBeNull();
    expect(respuesta.headers.get("Cache-Control")).toBe("no-store");
    expect(await respuesta.text()).not.toContain("orderId");
  });

  it("el 503 de «arrancando» no lleva ni la firma ni los parámetros del aviso", async () => {
    const respuesta = respuestaArrancando(new Request(`https://dcasapty.com/payment/yappy/ipn?${AVISO}`));
    const texto = await respuesta.text();
    expect(respuesta.status).toBe(503);
    for (const pedazo of ["b02927cb4f0a9c1d", "S0012X7KQ2", "CONF-123"]) expect(texto).not.toContain(pedazo);
  });
});

describe("Yappy: la IP que le llega a Odoo es la que pone Cloudflare, no la del visitante", () => {
  it("X-Forwarded-For y X-Real-IP del visitante se pisan con CF-Connecting-IP (el freno por conexión de Odoo depende de esto)", () => {
    const pedido = new Request("https://dcasapty.com/payment/yappy/iniciar", {
      method: "POST",
      headers: {
        "CF-Connecting-IP": "203.0.113.9",
        "X-Forwarded-For": "1.1.1.1, 2.2.2.2",
        "X-Real-IP": "3.3.3.3",
        Forwarded: "for=4.4.4.4",
      },
    });
    const h = forwardedHeaders(pedido);
    expect(h.get("X-Forwarded-For")).toBe("203.0.113.9");
    expect(h.get("X-Real-IP")).toBe("203.0.113.9");
    expect(h.get("X-Forwarded-Host")).toBe("dcasapty.com");
  });

  it("de punta a punta, en el arranque y en el aviso", async () => {
    const recibidas: Array<string | null> = [];
    const forward = vi.fn(async (pedido: Request) => {
      recibidas.push(pedido.headers.get("X-Forwarded-For"));
      return new Response("ok");
    });
    for (const [ruta, metodo] of [
      [`/payment/yappy/ipn?${AVISO}`, "GET"],
      ["/payment/yappy/iniciar", "POST"],
    ] as const) {
      await handleRequest(
        new Request(`https://dcasapty.com${ruta}`, {
          method: metodo,
          body: metodo === "POST" ? "{}" : undefined,
          headers: { "CF-Connecting-IP": "198.51.100.7", "X-Forwarded-For": "9.9.9.9" },
        }),
        { forward, canonicalHost: "dcasapty.com" },
      );
    }
    expect(recibidas).toEqual(["198.51.100.7", "198.51.100.7"]);
  });
});
