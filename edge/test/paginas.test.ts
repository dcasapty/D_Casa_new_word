import { afterEach, describe, expect, it, vi } from "vitest";

import { type EdgeDeps, handleRequest, manejarRegenerarTienda } from "../src/handler";
import { forwardedHeaders, isBlockedPath, route, rutaEstatica } from "../src/routing";
import {
  type AlmacenTienda,
  CABECERA_BORDE,
  CLAVE_INVALIDADO,
  clavePagina,
  COOKIE_PERSONAL,
  esPersonal,
  FRESCA_MS,
  RUTAS_PRINCIPALES,
  tiendaActiva,
} from "../src/tienda/paginas";

const TOKEN = "t".repeat(40);
const HOST = "dcasapty.com";

/** KV en memoria (con metadatos y TTL anotado). */
function almacenMemoria() {
  const datos = new Map<string, { texto: string; meta?: Record<string, string>; ttl?: number }>();
  const almacen: AlmacenTienda & { datos: typeof datos } = {
    datos,
    async leer(clave) {
      const e = datos.get(clave);
      return e ? { texto: e.texto, meta: e.meta ?? null } : null;
    },
    async escribir(clave, texto, meta, ttl) {
      datos.set(clave, { texto, meta, ttl });
    },
  };
  return almacen;
}

/**
 * Odoo de mentira con las mismas reglas que addons/dcasa_tienda_borde/models/ir_http.py: con el
 * secreto y sin cookies dibuja la página anónima y la certifica; con sesión, la página es de alguien.
 */
function odooFalso(estado = { precio: 10 }) {
  const forward = vi.fn(async (request: Request) => {
    const url = new URL(request.url);
    const cookies = request.headers.get("Cookie") ?? "";
    const delBorde = request.headers.get(CABECERA_BORDE) === TOKEN;
    if (["/web/login", "/my", "/shop/cart", "/shop/checkout"].includes(url.pathname) || request.method === "POST") {
      return new Response(`odoo dinámico ${url.pathname}`, {
        headers: { "Content-Type": "text/html; charset=utf-8", "Set-Cookie": "session_id=nueva; HttpOnly" },
      });
    }
    if (url.pathname === "/shop/no-existe-9") return new Response("404 de Odoo", { status: 404 });
    const usuario = /session_id=juana/.test(cookies) ? "Juana Pérez" : null;
    const html =
      `<!doctype html><html><head><link rel="canonical" href="https://${url.host}${url.pathname}"></head>` +
      `<body><nav class="o_dcasa_pildora">CATÁLOGO · SOCIOS D'CASA · VISÍTANOS</nav>` +
      `<span class="carrito">${usuario ? 3 : 0}</span>${usuario ? `<a>${usuario}</a>` : "<a>Iniciar sesión</a>"}` +
      `<p class="precio">$${estado.precio.toFixed(2)}</p><input name="csrf_token" value="${delBorde ? "csrf-borde" : "csrf-visita"}">` +
      `</body></html>`;
    const headers = new Headers({ "Content-Type": "text/html; charset=utf-8" });
    if (delBorde && !usuario) headers.set(CABECERA_BORDE, "anonimo");
    else headers.set("Set-Cookie", "session_id=nueva; HttpOnly");
    return new Response(html, { headers });
  });
  return { forward, estado };
}

function deps(over: Partial<EdgeDeps> = {}, almacen = almacenMemoria(), odoo = odooFalso()) {
  const pendientes: Promise<unknown>[] = [];
  const d: EdgeDeps = {
    forward: odoo.forward,
    waitUntil: (p) => pendientes.push(p),
    canonicalHost: HOST,
    tienda: { activa: true, almacen, token: TOKEN },
    ...over,
  };
  return { d, almacen, odoo, terminar: () => Promise.all(pendientes.splice(0)) };
}

const get = (ruta: string, init: RequestInit = {}) => new Request(`https://${HOST}${ruta}`, init);

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("rutas que pueden salir de la caché (mismas URL que Odoo)", () => {
  const ruta = (u: string, metodo = "GET") => rutaEstatica(new URL(`https://${HOST}${u}`), metodo);

  it("solo las páginas públicas", () => {
    for (const u of [
      "/",
      "/shop",
      "/shop/page/2",
      "/shop/category/salas-3",
      "/shop/category/salas-3/page/2",
      "/shop/cama-twin-xht022-12",
      "/visitanos",
      "/privacidad",
      "/terminos",
      "/black-weekend",
    ]) {
      expect(ruta(u), u).toBe(u);
    }
    expect(ruta("/?utm_source=ig&fbclid=x")).toBe("/");
    expect(ruta("/", "HEAD")).toBe("/");
  });

  it("nunca /web, /my, carrito, checkout, POST, búsqueda ni filtros", () => {
    for (const u of [
      "/shop/cart",
      "/shop/checkout",
      "/shop/payment",
      "/shop/address",
      "/shop/confirmation",
      "/shop/cart/update_json",
      "/my",
      "/my/orders",
      "/odoo",
      "/web",
      "/web/login",
      "/socios",
      "/brian/mcp",
      "/dcasa/borde/csrf",
      "/whatsapp",
      "/es/shop",
      "/shop?search=cama",
      "/shop?order=list_price+asc",
      "/shop/cama-12?attribute_values=3",
      "/shop/category/salas-3?tags=1",
      "/shop/",
      "/sitemap.xml",
    ]) {
      expect(ruta(u), u).toBeNull();
    }
    expect(ruta("/", "POST")).toBeNull();
    expect(ruta("/shop/cama-12", "POST")).toBeNull();
  });

  it("la invalidación es del borde; TIENDA_ESTATICA solo «on» la enciende", () => {
    expect(route(new URL(`https://${HOST}/__edge/tienda/regenerar`), "POST").kind).toBe("tienda_regenerar");
    expect(isBlockedPath("/dcasa/borde/csrf")).toBe(false);
    expect(tiendaActiva("on")).toBe(true);
    expect(tiendaActiva("ON ")).toBe(true);
    for (const v of ["off", "", undefined, "no"]) expect(tiendaActiva(v)).toBe(false);
  });

  it("quién es personal: cookie de Odoo o credenciales; session_id solo no cuenta", () => {
    expect(esPersonal(get("/", { headers: { Cookie: "session_id=abc; frontend_lang=es_419" } }))).toBe(false);
    expect(esPersonal(get("/", { headers: { Cookie: `session_id=abc; ${COOKIE_PERSONAL}=1` } }))).toBe(true);
    expect(esPersonal(get("/", { headers: { Cookie: `${COOKIE_PERSONAL}=` } }))).toBe(false);
    expect(esPersonal(get("/", { headers: { Cookie: `x${COOKIE_PERSONAL}=1` } }))).toBe(false);
    expect(esPersonal(get("/", { headers: { Authorization: "Bearer x" } }))).toBe(true);
  });
});

describe("anónimo: HTML de Odoo guardado en el borde", () => {
  it("la primera visita lo pide a Odoo (sin cookies, con el secreto) y la segunda no toca Odoo", async () => {
    const { d, almacen, odoo, terminar } = deps();
    const visita = { headers: { Cookie: "session_id=de-otro-anonimo; frontend_lang=es_419", "CF-Connecting-IP": "1.2.3.4" } };

    const primera = await handleRequest(get("/shop?utm_source=ig", visita), d);
    await terminar();
    expect(primera.headers.get("X-Dcasa-Cache")).toBe("MISS");
    const pedido = odoo.forward.mock.calls[0][0];
    expect(new URL(pedido.url).pathname + new URL(pedido.url).search).toBe("/shop");
    expect(pedido.headers.get("Cookie")).toBeNull();
    expect(pedido.headers.get("X-Forwarded-For")).toBeNull();
    expect(pedido.headers.get(CABECERA_BORDE)).toBe(TOKEN);
    expect(pedido.headers.get("X-Forwarded-Host")).toBe(HOST);
    expect(pedido.headers.get("X-Disable-Tracking")).toBe("1");
    const html = await primera.text();

    const segunda = await handleRequest(get("/shop", visita), d);
    expect(segunda.headers.get("X-Dcasa-Cache")).toBe("HIT");
    expect(odoo.forward).toHaveBeenCalledTimes(1);
    // Idéntico, byte a byte, a lo que dibujó Odoo: navbar píldora, canonical y todo.
    const odooDirecto = await (await odoo.forward(new Request(`https://${HOST}/shop`, { headers: { [CABECERA_BORDE]: TOKEN } }))).text();
    expect(await segunda.text()).toBe(odooDirecto);
    expect(html).toBe(odooDirecto);
    expect(html).toContain('<link rel="canonical" href="https://dcasapty.com/shop">');
    expect(html).toContain("o_dcasa_pildora");

    expect(segunda.headers.get("Content-Type")).toBe("text/html; charset=utf-8");
    expect(segunda.headers.get("Cache-Control")).toBe("no-cache");
    expect(segunda.headers.get("Server-Timing")).toBe('dcasa-borde;desc="HIT"');
    expect(segunda.headers.get("X-Content-Type-Options")).toBe("nosniff");
    expect(segunda.headers.has("Set-Cookie")).toBe(false);
    expect(segunda.headers.has(CABECERA_BORDE)).toBe(false);
    const guardada = almacen.datos.get(clavePagina(HOST, "/shop"))!;
    expect(guardada.ttl).toBeGreaterThan(0);
    expect(guardada.meta!.etag).toMatch(/^"p-[0-9a-f]{24}"$/);
  });

  it("nada personal en la caché: ni carrito, ni nombre, ni el CSRF del visitante", async () => {
    const { d, almacen, terminar } = deps();
    await handleRequest(get("/", { headers: { Cookie: "session_id=juana" } }), d);
    await terminar();
    const html = almacen.datos.get(clavePagina(HOST, "/"))!.texto;
    expect(html).not.toContain("Juana");
    expect(html).toContain('<span class="carrito">0</span>');
    expect(html).not.toContain("csrf-visita");
  });

  it("304 con el ETag y HEAD sin cuerpo", async () => {
    const { d, terminar } = deps();
    const primera = await handleRequest(get("/visitanos"), d);
    await terminar();
    const etag = primera.headers.get("ETag")!;
    const otra = await handleRequest(get("/visitanos", { headers: { "If-None-Match": etag } }), d);
    expect(otra.status).toBe(304);
    const head = await handleRequest(get("/visitanos", { method: "HEAD" }), d);
    expect(head.status).toBe(200);
    expect(await head.text()).toBe("");
  });

  it("cada host tiene su copia (workers.dev y el dominio no se mezclan)", async () => {
    const { d, almacen, terminar } = deps({ canonicalHost: undefined });
    await handleRequest(new Request("https://dcasa-staging.x.workers.dev/"), d);
    await handleRequest(get("/"), d);
    await terminar();
    expect(almacen.datos.has(clavePagina("dcasa-staging.x.workers.dev", "/"))).toBe(true);
    expect(almacen.datos.has(clavePagina(HOST, "/"))).toBe(true);
  });
});

describe("logueado o con carrito: directo a Odoo", () => {
  it("con la cookie dcasa_personal recibe la página de Odoo con sus datos y no se guarda nada", async () => {
    const { d, almacen, odoo } = deps();
    const res = await handleRequest(get("/", { headers: { Cookie: `session_id=juana; ${COOKIE_PERSONAL}=1` } }), d);
    expect(res.headers.get("X-Dcasa-Cache")).toBe("BYPASS");
    expect(await res.text()).toContain("Juana Pérez");
    const pedido = odoo.forward.mock.calls[0][0];
    expect(pedido.headers.get("Cookie")).toContain("session_id=juana");
    expect(pedido.headers.get(CABECERA_BORDE)).toBeNull();
    expect(almacen.datos.size).toBe(0);
  });

  it("aunque haya copia guardada, el logueado no la recibe", async () => {
    const { d, odoo, terminar } = deps();
    await handleRequest(get("/"), d);
    await terminar();
    const res = await handleRequest(get("/", { headers: { Cookie: `session_id=juana; ${COOKIE_PERSONAL}=1` } }), d);
    expect(await res.text()).toContain("Juana Pérez");
    expect(odoo.forward).toHaveBeenCalledTimes(2);
  });

  it("/web, /my, /shop/cart, /shop/checkout y POST nunca se guardan ni se sirven guardados", async () => {
    const { d, almacen, terminar } = deps();
    for (const req of [
      get("/web/login"),
      get("/my"),
      get("/shop/cart"),
      get("/shop/checkout"),
      get("/", { method: "POST", body: "x" }),
      get("/shop?search=cama"),
    ]) {
      const res = await handleRequest(req, d);
      expect(res.headers.get("X-Dcasa-Cache"), req.url).toBeNull();
    }
    await terminar();
    expect(almacen.datos.size).toBe(0);
  });

  it("una respuesta sin el certificado de Odoo (o con Set-Cookie) no se guarda: va la de Odoo", async () => {
    const odoo = odooFalso();
    const sinMarca = vi.fn(async (r: Request) => {
      const res = await odoo.forward(r);
      const h = new Headers(res.headers);
      h.delete(CABECERA_BORDE);
      return new Response(await res.text(), { headers: h });
    });
    const { d, almacen, terminar } = deps({ forward: sinMarca });
    const res = await handleRequest(get("/"), d);
    await terminar();
    expect(res.headers.get("X-Dcasa-Cache")).toBe("BYPASS");
    expect(almacen.datos.size).toBe(0);
    // La segunda petición a Odoo es la ORIGINAL del visitante (con su cookie), no la del borde.
    expect(sinMarca).toHaveBeenCalledTimes(2);
  });

  it("404 y 503 de Odoo no se guardan", async () => {
    const { d, almacen, terminar } = deps();
    expect((await handleRequest(get("/shop/no-existe-9"), d)).status).toBe(404);
    const caido = deps({ forward: async () => Promise.reject(new Error("contenedor reiniciando")) });
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const res = await handleRequest(get("/", { headers: { Accept: "text/html" } }), caido.d);
    expect(res.status).toBe(503);
    expect(res.headers.get("X-Dcasa-Cache")).toBe("BYPASS");
    await terminar();
    await caido.terminar();
    expect(almacen.datos.size).toBe(0);
    expect(caido.almacen.datos.size).toBe(0);
  });

  it("el visitante no puede hablarle a Odoo con la cabecera del borde", () => {
    const h = forwardedHeaders(get("/", { headers: { [CABECERA_BORDE]: TOKEN } }));
    expect(h.has(CABECERA_BORDE)).toBe(false);
  });
});

describe("invalidación (aviso de Odoo)", () => {
  const aviso = (cuerpo: unknown = { productos: [1], rutas: ["/shop/mesa-1", "/my", "/shop?x=1"] }, auth = `Bearer ${TOKEN}`) =>
    get("/__edge/tienda/regenerar", { method: "POST", headers: { Authorization: auth }, body: JSON.stringify(cuerpo) });

  it("cambia el precio en Odoo → aviso → la próxima visita ve el precio nuevo", async () => {
    vi.spyOn(console, "log").mockImplementation(() => undefined);
    const odoo = odooFalso({ precio: 10 });
    const { d, almacen, terminar } = deps({}, almacenMemoria(), odoo);
    await handleRequest(get("/shop/mesa-1"), d);
    await terminar();
    expect(await (await handleRequest(get("/shop/mesa-1"), d)).text()).toContain("$10.00");

    vi.useFakeTimers({ now: Date.now() + 5 });
    odoo.estado.precio = 20;
    odoo.forward.mockClear();
    const res = await handleRequest(aviso(), d);
    expect(res.status).toBe(200);
    expect(((await res.json()) as { estado: string }).estado).toBe("ok");
    expect(Number(almacen.datos.get(CLAVE_INVALIDADO)!.texto)).toBeGreaterThan(0);
    // Ya respondido, se piden a Odoo las principales y la ficha que cambió (no /my ni con parámetros).
    await terminar();
    const precalentadas = odoo.forward.mock.calls.map(([r]) => new URL(r.url).pathname).sort();
    expect(precalentadas).toEqual([...RUTAS_PRINCIPALES, "/shop/mesa-1"].sort());
    vi.advanceTimersByTime(10);
    const despues = await handleRequest(get("/shop/mesa-1"), d);
    expect(despues.headers.get("X-Dcasa-Cache")).toBe("HIT");
    expect(await despues.text()).toContain("$20.00");
  });

  it("sin precalentar, la página vieja no se sirve: MISS", async () => {
    vi.spyOn(console, "log").mockImplementation(() => undefined);
    const odoo = odooFalso({ precio: 10 });
    const { d, almacen, terminar } = deps({}, almacenMemoria(), odoo);
    await handleRequest(get("/shop/category/salas-3"), d);
    await terminar();
    vi.useFakeTimers({ now: Date.now() + 5 });
    await handleRequest(aviso({}), d);
    await terminar();
    vi.advanceTimersByTime(10);
    odoo.estado.precio = 30;
    const res = await handleRequest(get("/shop/category/salas-3"), d);
    expect(res.headers.get("X-Dcasa-Cache")).toBe("MISS");
    expect(await res.text()).toContain("$30.00");
    await terminar();
    expect(almacen.datos.get(clavePagina(HOST, "/shop/category/salas-3"))!.texto).toContain("$30.00");
  });

  it("pasada una hora se sirve la guardada (STALE) y se refresca en segundo plano", async () => {
    const odoo = odooFalso({ precio: 10 });
    const { d, terminar } = deps({}, almacenMemoria(), odoo);
    vi.useFakeTimers({ now: 1_000_000 });
    await handleRequest(get("/"), d);
    await terminar();
    vi.setSystemTime(1_000_000 + FRESCA_MS + 1);
    odoo.estado.precio = 11;
    const vieja = await handleRequest(get("/"), d);
    expect(vieja.headers.get("X-Dcasa-Cache")).toBe("STALE");
    expect(await vieja.text()).toContain("$10.00");
    await terminar();
    const nueva = await handleRequest(get("/"), d);
    expect(nueva.headers.get("X-Dcasa-Cache")).toBe("HIT");
    expect(await nueva.text()).toContain("$11.00");
  });

  it("exige el token (≥ 32), POST y almacén; si KV falla, 503 para que Odoo reintente", async () => {
    const { d } = deps();
    expect((await handleRequest(aviso({}, "Bearer corto"), d)).status).toBe(401);
    expect((await handleRequest(aviso({}, ""), d)).status).toBe(401);
    expect((await handleRequest(get("/__edge/tienda/regenerar"), d)).status).toBe(405);
    expect((await handleRequest(aviso(), { ...d, tienda: { activa: true, token: TOKEN } })).status).toBe(404);
    expect((await handleRequest(aviso(), { ...d, tienda: { activa: true, almacen: almacenMemoria(), token: "corto" } })).status).toBe(404);
    expect((await manejarRegenerarTienda(aviso(), null)).status).toBe(404);
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const roto: AlmacenTienda = { leer: async () => null, escribir: async () => Promise.reject(new Error("KV")) };
    expect((await handleRequest(aviso(), { ...d, tienda: { activa: true, almacen: roto, token: TOKEN } })).status).toBe(503);
  });

  it("funciona con la caché apagada (para dejarla lista antes de encenderla); el aviso no se reenvía a Odoo", async () => {
    vi.spyOn(console, "log").mockImplementation(() => undefined);
    const { d, almacen, odoo, terminar } = deps();
    const res = await handleRequest(aviso({ todo: true }), { ...d, tienda: { activa: false, almacen, token: TOKEN } });
    await terminar();
    expect(res.status).toBe(200);
    expect(almacen.datos.has(CLAVE_INVALIDADO)).toBe(true);
    const rutas = odoo.forward.mock.calls.map(([r]) => new URL(r.url).pathname);
    expect(rutas.sort()).toEqual([...RUTAS_PRINCIPALES].sort());
  });
});

describe("apagada, sin token o con KV caído: todo a Odoo como siempre", () => {
  it("TIENDA_ESTATICA=off", async () => {
    const { d, almacen } = deps();
    const res = await handleRequest(get("/"), { ...d, tienda: { activa: false, almacen, token: TOKEN } });
    expect(res.headers.get("X-Dcasa-Cache")).toBeNull();
    expect(res.headers.get("Set-Cookie")).toContain("session_id");
    expect(almacen.datos.size).toBe(0);
  });

  it("sin token válido no hay caché (Odoo no podría certificar nada)", async () => {
    const { d, almacen } = deps();
    await handleRequest(get("/"), { ...d, tienda: { activa: true, almacen, token: "corto" } });
    expect(almacen.datos.size).toBe(0);
  });

  it("si KV no responde, sirve Odoo", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const { d } = deps();
    const roto: AlmacenTienda = { leer: async () => Promise.reject(new Error("KV caído")), escribir: vi.fn() };
    const res = await handleRequest(get("/"), { ...d, tienda: { activa: true, almacen: roto, token: TOKEN } });
    expect(res.status).toBe(200);
    expect(await res.text()).toContain("Iniciar sesión");
  });
});

describe("staging: noindex en todo", () => {
  it("X-Robots-Tag en páginas guardadas, de Odoo, 404 y redirecciones", async () => {
    const { d, terminar } = deps({ entorno: "staging", canonicalHost: "staging.dcasapty.com" });
    for (const url of [
      "https://staging.dcasapty.com/",
      "https://staging.dcasapty.com/",
      "https://staging.dcasapty.com/shop/cart",
      "https://staging.dcasapty.com/web/database/manager",
      "https://www.staging.dcasapty.com/shop",
      "https://staging.dcasapty.com/__edge/health",
    ]) {
      const res = await handleRequest(new Request(url), d);
      expect(res.headers.get("X-Robots-Tag"), url).toBe("noindex, nofollow");
      await terminar();
    }
  });

  it("producción no lleva noindex", async () => {
    const { d } = deps({ entorno: "produccion" });
    const res = await handleRequest(get("/"), d);
    expect(res.headers.has("X-Robots-Tag")).toBe(false);
  });
});
