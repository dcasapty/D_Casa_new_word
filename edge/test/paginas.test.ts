import { afterEach, describe, expect, it, vi } from "vitest";

import { type EdgeDeps, handleRequest, manejarRegenerarTienda, respuestaArrancando } from "../src/handler";
import { esAssetCacheable, forwardedHeaders, isBlockedPath, route, rutaEstatica } from "../src/routing";
import { claveAsset } from "../src/tienda/assets";
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
const VERSION = "aaaaaaa";
const INMUTABLE = "public, max-age=31536000, immutable";

/** KV en memoria (texto y bytes, con metadatos y TTL anotado). */
function almacenMemoria() {
  const datos = new Map<string, { texto?: string; bytes?: ArrayBuffer; meta?: Record<string, string>; ttl?: number }>();
  const almacen: AlmacenTienda & { datos: typeof datos; assets: () => string[] } = {
    datos,
    assets: () => [...datos.keys()].filter((k) => k.startsWith("asset:")).sort(),
    async leer(clave) {
      const e = datos.get(clave);
      return e?.texto !== undefined ? { texto: e.texto, meta: e.meta ?? null } : null;
    },
    async escribir(clave, texto, meta, ttl) {
      datos.set(clave, { texto, meta, ttl });
    },
    async leerBinario(clave) {
      const e = datos.get(clave);
      return e?.bytes ? { bytes: e.bytes, meta: e.meta ?? null } : null;
    },
    async escribirBinario(clave, bytes, meta, ttl) {
      datos.set(clave, { bytes, meta, ttl });
    },
    async meta(clave) {
      const e = datos.get(clave);
      return e ? (e.meta ?? {}) : null;
    },
  };
  return almacen;
}

/** Almacén que falla como se le pida (KV caído). */
function almacenRoto(fallos: Partial<Record<keyof AlmacenTienda, boolean>>): AlmacenTienda {
  const falla = (nombre: keyof AlmacenTienda) => fallos[nombre] ?? false;
  return {
    leer: async () => (falla("leer") ? Promise.reject(new Error("KV caído")) : null),
    escribir: async () => (falla("escribir") ? Promise.reject(new Error("KV caído")) : undefined),
    leerBinario: async () => (falla("leerBinario") ? Promise.reject(new Error("KV caído")) : null),
    escribirBinario: async () => (falla("escribirBinario") ? Promise.reject(new Error("KV caído")) : undefined),
    meta: async () => (falla("meta") ? Promise.reject(new Error("KV caído")) : null),
  };
}

interface EstadoOdoo {
  precio: number;
  /** Versión de los bundles (el hash de 7 caracteres que Odoo pone en /web/assets/<v>/…). */
  version: string;
  /** Contenedor apagado o arrancando: el Durable Object responde el 503 amable a todo. */
  caido: boolean;
  /** Odoo responde 500 a los assets (p. ej. no pudo compilar el bundle). */
  assetsRotos: boolean;
}

/** Los assets como los sirve Odoo 19 (cabeceras y cookies reales). `null` si no es un asset. */
function assetFalso(url: URL, request: Request, est: EstadoOdoo): Response | null {
  const ruta = url.pathname;
  const conCookie = /session_id=/.test(request.headers.get("Cookie") ?? "");
  const delBorde = request.headers.get(CABECERA_BORDE) === TOKEN;
  // Request._save_session: sin cookie de sesión, Odoo manda session_id… salvo al borde (can_save=False).
  const sesion = (h: Headers) => {
    if (!conCookie && !delBorde) h.set("Set-Cookie", "session_id=nueva; HttpOnly");
  };
  if (est.assetsRotos && esAssetCacheable(ruta + url.search)) return new Response("error", { status: 500 });
  const bundle = /^\/web\/assets\/([^/]+)\/(.+)$/.exec(ruta);
  if (bundle) {
    // content_assets: una versión que no es la vigente redirige a la vigente.
    if (bundle[1] !== est.version) {
      return new Response(null, { status: 302, headers: { Location: `/web/assets/${est.version}/${bundle[2]}` } });
    }
    const h = new Headers({
      "Content-Type": bundle[2].endsWith(".css") ? "text/css; charset=utf-8" : "application/javascript; charset=utf-8",
      "Cache-Control": INMUTABLE,
      ETag: `"${bundle[1]}-${bundle[2]}"`,
    });
    sesion(h);
    return new Response(`/* ${bundle[2]} v${bundle[1]} */`, { headers: h });
  }
  if (/^\/[a-z0-9_]+\/static\//.test(ruta)) {
    // _serve_static: public 7 días, nunca cookies.
    return new Response(`bytes de ${ruta} v${est.version}`, {
      headers: {
        "Content-Type": ruta.endsWith(".woff2") ? "font/woff2" : "image/webp",
        "Cache-Control": "public, max-age=604800",
        ETag: `"st-${ruta}-${est.version}"`,
      },
    });
  }
  if (ruta.startsWith("/dcasa/img/")) {
    // website_dcasa/controllers/imagen.py: sin ?v= redirige; con él, inmutable y sin sesión.
    if (!url.searchParams.has("v")) return new Response(null, { status: 302, headers: { Location: `${ruta}?v=abc123` } });
    return new Response(`foto ${ruta}`, { headers: { "Content-Type": "image/webp", "Cache-Control": INMUTABLE, ETag: '"img"' } });
  }
  if (ruta.startsWith("/web/image/")) {
    const h = new Headers({ "Content-Type": "image/jpeg" });
    if (ruta.includes("res.partner")) h.set("Cache-Control", "private, no-cache"); // avatar de un usuario
    else h.set("Cache-Control", url.searchParams.has("unique") ? INMUTABLE : "no-cache");
    sesion(h);
    return new Response(`imagen ${ruta}`, { headers: h });
  }
  return null;
}

/**
 * Odoo de mentira con las mismas reglas que addons/dcasa_tienda_borde/models/ir_http.py: con el
 * secreto y sin cookies dibuja la página anónima y la certifica; con sesión, la página es de alguien.
 * Sus páginas referencian assets como las de website_dcasa (bundles, fuente precargada, hero, logo,
 * tarjetas con <picture>); los assets se sirven con las cabeceras y cookies de Odoo 19.
 */
function odooFalso(inicial: Partial<EstadoOdoo> = {}) {
  const estado: EstadoOdoo = { precio: 10, version: VERSION, caido: false, assetsRotos: false, ...inicial };
  const forward = vi.fn(async (request: Request) => {
    if (estado.caido) return respuestaArrancando(request);
    const url = new URL(request.url);
    const asset = assetFalso(url, request, estado);
    if (asset) return asset;
    const cookies = request.headers.get("Cookie") ?? "";
    const delBorde = request.headers.get(CABECERA_BORDE) === TOKEN;
    if (["/web/login", "/my", "/shop/cart", "/shop/checkout"].includes(url.pathname) || request.method === "POST") {
      return new Response(`odoo dinámico ${url.pathname}`, {
        headers: { "Content-Type": "text/html; charset=utf-8", "Set-Cookie": "session_id=nueva; HttpOnly" },
      });
    }
    if (url.pathname === "/shop/no-existe-9") return new Response("404 de Odoo", { status: 404 });
    const usuario = /session_id=juana/.test(cookies) ? "Juana Pérez" : null;
    const v = estado.version;
    const head =
      `<head><link rel="canonical" href="https://${url.host}${url.pathname}">` +
      `<link rel="preload" href="/website_dcasa/static/src/fonts/anton-latin.woff2" as="font" type="font/woff2" crossorigin="">` +
      `<link rel="icon" href="/web/image/website/1/favicon?unique=f1">` +
      `<link type="text/css" rel="stylesheet" href="/web/assets/${v}/web.assets_frontend.min.css" data-asset-bundle="web.assets_frontend">` +
      `<script type="text/javascript" src="/web/assets/${v}/web.assets_frontend_minimal.min.js" onerror="__odooAssetError=1"></script>` +
      `<script type="text/javascript" data-src="/web/assets/${v}/web.assets_frontend_lazy.min.js" defer="defer"></script>` +
      `<link rel="stylesheet" href="https://cdn.ajena.example/x.css"></head>`;
    const hero =
      url.pathname === "/"
        ? `<img src="/website_dcasa/static/src/img/hero.webp" srcset="/website_dcasa/static/src/img/hero-800.webp 800w, /website_dcasa/static/src/img/hero.webp 1400w" sizes="100vw" loading="eager" fetchpriority="high" alt="">`
        : "";
    const tarjetas =
      `<picture><source type="image/webp" srcset="/dcasa/img/product.template/5/image_1920/256.webp?v=abc123 256w, /dcasa/img/product.template/5/image_1920/512.webp?v=abc123 512w" sizes="50vw"/>` +
      `<img src="/web/image/product.template/5/image_512?unique=u5" loading="eager" fetchpriority="high"/></picture>` +
      `<picture><source type="image/webp" srcset="/dcasa/img/product.template/6/image_1920/256.webp?v=abc123 256w"/>` +
      `<img src="/web/image/product.template/6/image_512?unique=u6" loading="lazy"/></picture>`;
    const html =
      `<!doctype html><html>${head}<body><nav class="o_dcasa_pildora">` +
      `<img src="/website_dcasa/static/src/img/logo-200.webp" srcset="/website_dcasa/static/src/img/logo-200.webp 1x, /website_dcasa/static/src/img/logo-400.webp 2x" loading="eager">` +
      `CATÁLOGO · SOCIOS D'CASA · VISÍTANOS</nav>${hero}` +
      `<span class="carrito">${usuario ? 3 : 0}</span>${usuario ? `<a>${usuario}</a>` : "<a>Iniciar sesión</a>"}` +
      `<p class="precio">$${estado.precio.toFixed(2)}</p>${tarjetas}<input name="csrf_token" value="${delBorde ? "csrf-borde" : "csrf-visita"}">` +
      `</body></html>`;
    const headers = new Headers({ "Content-Type": "text/html; charset=utf-8" });
    if (delBorde && !usuario) headers.set(CABECERA_BORDE, "anonimo");
    else headers.set("Set-Cookie", "session_id=nueva; HttpOnly");
    return new Response(html, { headers });
  });
  /** Rutas de las páginas (no assets) que se le pidieron a Odoo. */
  const paginasPedidas = () =>
    forward.mock.calls
      .map(([r]) => r)
      .filter((r) => (r.headers.get("Accept") ?? "").includes("text/html") || !assetFalso(new URL(r.url), r, estado))
      .map((r) => new URL(r.url).pathname);
  return { forward, estado, paginasPedidas };
}

function deps(over: Partial<EdgeDeps> = {}, almacen = almacenMemoria(), odoo = odooFalso()) {
  const pendientes: Promise<unknown>[] = [];
  const d: EdgeDeps = {
    forward: odoo.forward,
    waitUntil: (p) => pendientes.push(p),
    canonicalHost: HOST,
    tienda: { activa: true, almacen, token: TOKEN },
    odooListo: async () => !odoo.estado.caido,
    ...over,
  };
  // Las tareas en segundo plano pueden encolar otras (assets tras la página): se agotan todas.
  const terminar = async () => {
    while (pendientes.length) await Promise.all(pendientes.splice(0));
  };
  return { d, almacen, odoo, terminar };
}

const get = (ruta: string, init: RequestInit = {}) => new Request(`https://${HOST}${ruta}`, init);
const CSS = `/web/assets/${VERSION}/web.assets_frontend.min.css`;
const JS_MINIMO = `/web/assets/${VERSION}/web.assets_frontend_minimal.min.js`;
const JS_PEREZOSO = `/web/assets/${VERSION}/web.assets_frontend_lazy.min.js`;
const FUENTE = "/website_dcasa/static/src/fonts/anton-latin.woff2";

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
    expect(odoo.paginasPedidas()).toEqual(["/shop"]);
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
    const html = almacen.datos.get(clavePagina(HOST, "/"))!.texto!;
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
    expect(odoo.paginasPedidas()).toEqual(["/", "/"]);
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

describe("una página guardada nunca se ve rota: sus assets también están en el borde", () => {
  it("al guardar la página se precalientan sus estilos, JS, fuente, logo, hero y foto LCP; las perezosas no", async () => {
    const { d, almacen, odoo, terminar } = deps();
    await handleRequest(get("/"), d);
    await terminar();
    expect(almacen.assets()).toEqual(
      [
        CSS,
        JS_MINIMO,
        JS_PEREZOSO, // data-src del cargador perezoso de Odoo
        FUENTE, // <link rel="preload" as="font">
        "/web/image/website/1/favicon?unique=f1",
        "/website_dcasa/static/src/img/hero.webp",
        "/website_dcasa/static/src/img/hero-800.webp",
        "/website_dcasa/static/src/img/logo-200.webp",
        "/website_dcasa/static/src/img/logo-400.webp",
        "/dcasa/img/product.template/5/image_1920/256.webp?v=abc123", // <source> de la <picture> prioritaria
        "/dcasa/img/product.template/5/image_1920/512.webp?v=abc123",
        "/web/image/product.template/5/image_512?unique=u5",
      ]
        .map(claveAsset)
        .sort(),
    );
    // La página se dio por completa: sus estilos y JS quedaron en el borde.
    expect(almacen.datos.get(clavePagina(HOST, "/"))!.meta!.assets).toBe("ok");
    // Pedidos al borde: con el secreto (Odoo no pone cookies) y sin cookies de nadie.
    const pedidoCss = odoo.forward.mock.calls.map(([r]) => r).find((r) => new URL(r.url).pathname === CSS)!;
    expect(pedidoCss.headers.get(CABECERA_BORDE)).toBe(TOKEN);
    expect(pedidoCss.headers.get("Cookie")).toBeNull();
    const css = almacen.datos.get(claveAsset(CSS))!;
    expect(new TextDecoder().decode(css.bytes)).toContain("web.assets_frontend.min.css");
    expect(css.meta).toMatchObject({ cc: INMUTABLE, ct: "text/css; charset=utf-8" });
    expect(css.ttl).toBeGreaterThan(almacen.datos.get(clavePagina(HOST, "/"))!.ttl!);
  });

  it("HTML y assets guardados + Odoo caído → la página sale ENTERA del borde (nadie nota el reinicio)", async () => {
    const { d, odoo, terminar } = deps();
    await handleRequest(get("/"), d);
    await terminar();
    odoo.estado.caido = true;
    odoo.forward.mockClear();

    const pagina = await handleRequest(get("/", { headers: { Accept: "text/html" } }), d);
    expect(pagina.status).toBe(200);
    expect(pagina.headers.get("X-Dcasa-Cache")).toBe("HIT");
    expect(await pagina.text()).toContain(CSS);
    for (const ruta of [CSS, JS_MINIMO, JS_PEREZOSO, FUENTE, "/website_dcasa/static/src/img/hero.webp"]) {
      const asset = await handleRequest(get(ruta, { headers: { Cookie: "session_id=visitante" } }), d);
      expect(asset.status, ruta).toBe(200);
      expect(asset.headers.get("X-Dcasa-Cache"), ruta).toBe("HIT");
      expect(asset.headers.has("Set-Cookie")).toBe(false);
      expect(asset.headers.get("X-Content-Type-Options")).toBe("nosniff");
    }
    const css = await handleRequest(get(CSS), d);
    expect(css.headers.get("Cache-Control")).toBe(INMUTABLE); // las cabeceras de Odoo, tal cual
    expect(css.headers.get("Content-Type")).toBe("text/css; charset=utf-8");
    expect(await css.text()).toContain("web.assets_frontend.min.css");
    expect(odoo.forward).not.toHaveBeenCalled();
  });

  it("HTML guardado SIN sus estilos + Odoo caído → el 503 amable, nunca una página sin estilos", async () => {
    vi.spyOn(console, "warn").mockImplementation(() => undefined);
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const { d, almacen, odoo, terminar } = deps({}, almacenMemoria(), odooFalso({ assetsRotos: true }));
    await handleRequest(get("/"), d);
    await terminar();
    expect(almacen.assets()).toEqual([]);
    expect(almacen.datos.get(clavePagina(HOST, "/"))!.meta!.assets).toBe("falta");

    // Con Odoo listo, la página guardada se sirve: los assets los dará Odoo.
    odoo.estado.assetsRotos = false;
    const conOdoo = await handleRequest(get("/", { headers: { Accept: "text/html" } }), d);
    expect(conOdoo.status).toBe(200);
    expect(conOdoo.headers.get("X-Dcasa-Cache")).toBe("HIT");

    // Con Odoo caído, no: estilos ausentes = página rota en el celular de la dueña.
    odoo.estado.caido = true;
    const sinOdoo = await handleRequest(get("/", { headers: { Accept: "text/html" } }), d);
    expect(sinOdoo.status).toBe(503);
    expect(sinOdoo.headers.get("Retry-After")).toBe("15");
    expect(sinOdoo.headers.get("X-Dcasa-Estado")).toBe("arrancando");
    expect(sinOdoo.headers.get("Cache-Control")).toBe("no-store");
    expect(await sinOdoo.text()).toContain("Estamos abriendo la tienda");

    // En cuanto los assets llegan al borde (Odoo volvió y el navegador de un visitante, con su cookie
    // de sesión, los pidió), la página vuelve a salir.
    odoo.estado.caido = false;
    for (const ruta of [CSS, JS_MINIMO, JS_PEREZOSO]) {
      const asset = await handleRequest(get(ruta, { headers: { Cookie: "session_id=visitante" } }), d);
      expect(asset.headers.get("X-Dcasa-Cache"), ruta).toBe("MISS");
    }
    await terminar();
    odoo.estado.caido = true;
    const otraVez = await handleRequest(get("/", { headers: { Accept: "text/html" } }), d);
    expect(otraVez.status).toBe(200);
    expect(otraVez.headers.get("X-Dcasa-Cache")).toBe("HIT");
  });

  it("assets con Set-Cookie, privados, sin «public» o no-200 no se guardan (lo que diga Odoo, BYPASS)", async () => {
    const { d, almacen, terminar } = deps({}, almacenMemoria(), odooFalso());
    // Sin cookie de sesión y sin el secreto, Odoo manda session_id: no se comparte con nadie.
    const conCookie = await handleRequest(get(CSS), d);
    expect(conCookie.status).toBe(200);
    expect(conCookie.headers.get("X-Dcasa-Cache")).toBe("BYPASS");
    expect(conCookie.headers.get("Set-Cookie")).toContain("session_id");
    // Avatar de un usuario (private), imagen sin versión (no-cache), bundle de otra versión (302), 404.
    for (const ruta of [
      "/web/image/res.partner/3/avatar_128",
      "/web/image/product.template/5/image_512",
      "/web/assets/zzzzzzz/web.assets_frontend.min.css",
      "/website_dcasa/static/src/img/no-existe.webp",
    ]) {
      const res = await handleRequest(get(ruta, { headers: { Cookie: "session_id=visitante" } }), {
        ...d,
        forward: async (r: Request) =>
          new URL(r.url).pathname.endsWith("no-existe.webp") ? new Response("no", { status: 404 }) : d.forward(r),
      });
      expect(res.headers.get("X-Dcasa-Cache"), ruta).toBe("BYPASS");
    }
    await terminar();
    expect(almacen.assets()).toEqual([]);
    // Con la cookie de sesión del visitante (lo normal al pedir assets), sí se guarda.
    const normal = await handleRequest(get(CSS, { headers: { Cookie: "session_id=visitante" } }), d);
    expect(normal.headers.get("X-Dcasa-Cache")).toBe("MISS");
    await terminar();
    expect(almacen.assets()).toEqual([claveAsset(CSS)]);
  });

  it("304 y HEAD de assets los da el borde; Range y Authorization pasan a Odoo", async () => {
    const { d, odoo, terminar } = deps();
    const visitante = { Cookie: "session_id=visitante" };
    const primera = await handleRequest(get(CSS, { headers: visitante }), d);
    await terminar();
    const etag = primera.headers.get("ETag")!;
    odoo.forward.mockClear();
    const revalida = await handleRequest(get(CSS, { headers: { ...visitante, "If-None-Match": etag } }), d);
    expect(revalida.status).toBe(304);
    expect(revalida.headers.get("ETag")).toBe(etag);
    expect(revalida.headers.get("Cache-Control")).toBe(INMUTABLE);
    const head = await handleRequest(get(CSS, { method: "HEAD", headers: visitante }), d);
    expect(head.status).toBe(200);
    expect(await head.text()).toBe("");
    expect(Number(head.headers.get("Content-Length"))).toBeGreaterThan(0);
    expect(odoo.forward).not.toHaveBeenCalled();
    await handleRequest(get(CSS, { headers: { ...visitante, Range: "bytes=0-10" } }), d);
    await handleRequest(get(CSS, { headers: { ...visitante, Authorization: "Bearer x" } }), d);
    expect(odoo.forward).toHaveBeenCalledTimes(2);
  });

  it("estáticos sin versión (fuentes, logo) caducan con la invalidación; con Odoo caído se sirve el viejo (STALE)", async () => {
    vi.spyOn(console, "log").mockImplementation(() => undefined);
    const { d, odoo, terminar } = deps();
    const visitante = { Cookie: "session_id=visitante" };
    expect((await handleRequest(get(FUENTE, { headers: visitante }), d)).headers.get("X-Dcasa-Cache")).toBe("MISS");
    await terminar();
    expect((await handleRequest(get(FUENTE, { headers: visitante }), d)).headers.get("X-Dcasa-Cache")).toBe("HIT");
    // Una foto del módulo que ninguna página principal referencia (no se precalienta) y un bundle.
    const foto = "/website_dcasa/static/src/img/split-socios.webp";
    await handleRequest(get(foto, { headers: visitante }), d);
    await handleRequest(get(CSS, { headers: visitante }), d);
    await terminar();
    const aviso = () =>
      handleRequest(get("/__edge/tienda/regenerar", { method: "POST", headers: { Authorization: `Bearer ${TOKEN}` }, body: "{}" }), d);

    // Despliegue: los estáticos cambiaron con la misma URL y Odoo avisa. La invalidación los da por
    // viejos: la fuente la trae nueva el precalentado de la portada (que la precarga); la foto que
    // nadie precalienta se vuelve a pedir a Odoo con la primera visita.
    vi.useFakeTimers({ now: Date.now() + 5 });
    odoo.estado.version = "bbbbbbb";
    await aviso();
    await terminar();
    vi.advanceTimersByTime(10);
    const nueva = await handleRequest(get(FUENTE, { headers: visitante }), d);
    expect(nueva.headers.get("X-Dcasa-Cache")).toBe("HIT");
    expect(await nueva.text()).toContain("vbbbbbbb");
    const fotoNueva = await handleRequest(get(foto, { headers: visitante }), d);
    expect(fotoNueva.headers.get("X-Dcasa-Cache")).toBe("MISS");
    expect(await fotoNueva.text()).toContain("vbbbbbbb");
    // Un bundle con versión en la URL no mira la invalidación: su contenido no cambia nunca.
    expect((await handleRequest(get(CSS, { headers: visitante }), d)).headers.get("X-Dcasa-Cache")).toBe("HIT");
    await terminar();

    // Otra invalidación con Odoo caído: no se pudo refrescar nada; la fuente caducó, pero mejor vieja que rota.
    odoo.estado.caido = true;
    await aviso();
    await terminar();
    vi.advanceTimersByTime(10);
    const vieja = await handleRequest(get(FUENTE, { headers: visitante }), d);
    expect(vieja.status).toBe(200);
    expect(vieja.headers.get("X-Dcasa-Cache")).toBe("STALE");
    expect(await vieja.text()).toContain("vbbbbbbb");
    // Vuelve Odoo: la próxima petición la refresca.
    odoo.estado.caido = false;
    expect((await handleRequest(get(FUENTE, { headers: visitante }), d)).headers.get("X-Dcasa-Cache")).toBe("MISS");
  });

  it("/__edge/health dice si la portada y el catálogo sobrevivirían un reinicio", async () => {
    vi.spyOn(console, "log").mockImplementation(() => undefined);
    const { d, terminar } = deps({ salud: async () => ({ contenedor: "healthy", odoo: { status: 200 } }) });
    const antes = (await (await handleRequest(get("/__edge/health"), d)).json()) as { tienda: { rutas: Record<string, string>; sobrevive_reinicio: boolean } };
    expect(antes.tienda).toEqual({ rutas: { "/": "falta", "/shop": "falta", "/black-weekend": "falta" }, sobrevive_reinicio: false });

    await handleRequest(get("/__edge/tienda/regenerar", { method: "POST", headers: { Authorization: `Bearer ${TOKEN}` }, body: "{}" }), d);
    await terminar();
    const despues = (await (await handleRequest(get("/__edge/health"), d)).json()) as typeof antes;
    expect(despues.tienda).toEqual({
      rutas: { "/": "completa", "/shop": "completa", "/black-weekend": "completa" },
      sobrevive_reinicio: true,
    });
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
    expect(odoo.paginasPedidas().sort()).toEqual([...RUTAS_PRINCIPALES, "/shop/mesa-1"].sort());
    vi.advanceTimersByTime(10);
    const despues = await handleRequest(get("/shop/mesa-1"), d);
    expect(despues.headers.get("X-Dcasa-Cache")).toBe("HIT");
    expect(await despues.text()).toContain("$20.00");
  });

  it("despliegue (APP_VERSION nueva): el HTML nuevo referencia los bundles nuevos y estos se precalientan", async () => {
    vi.spyOn(console, "log").mockImplementation(() => undefined);
    const odoo = odooFalso();
    const { d, almacen, terminar } = deps({}, almacenMemoria(), odoo);
    await handleRequest(aviso({ todo: false }), d);
    await terminar();
    expect(almacen.assets()).toContain(claveAsset(CSS));

    // Despliegue: Odoo arranca con bundles nuevos y, al abrir, su cron avisa «todo» (pendiente.py).
    vi.useFakeTimers({ now: Date.now() + 5 });
    odoo.estado.version = "bbbbbbb";
    odoo.forward.mockClear();
    await handleRequest(aviso({ todo: true, productos: [], motivos: ["despliegue"], rutas: [] }), d);
    await terminar();
    vi.advanceTimersByTime(10);
    const cssNuevo = CSS.replace(VERSION, "bbbbbbb");
    const portada = await handleRequest(get("/"), d);
    expect(portada.headers.get("X-Dcasa-Cache")).toBe("HIT");
    expect(await portada.text()).toContain(cssNuevo);
    expect(almacen.assets()).toContain(claveAsset(cssNuevo));
    expect(almacen.datos.get(clavePagina(HOST, "/"))!.meta!.assets).toBe("ok");
    // El bundle nuevo se pidió UNA vez para las tres páginas principales (comparten bundles).
    expect(odoo.forward.mock.calls.filter(([r]) => new URL(r.url).pathname === cssNuevo)).toHaveLength(1);
    // Los bundles viejos siguen en KV hasta que caduquen: no estorban (nadie los referencia).
    expect(almacen.assets()).toContain(claveAsset(CSS));
    odoo.forward.mockClear();
    expect((await handleRequest(get(cssNuevo), d)).headers.get("X-Dcasa-Cache")).toBe("HIT");
    expect(odoo.forward).not.toHaveBeenCalled();
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
    const roto = almacenRoto({ escribir: true });
    expect((await handleRequest(aviso(), { ...d, tienda: { activa: true, almacen: roto, token: TOKEN } })).status).toBe(503);
  });

  it("funciona con la caché apagada (para dejarla lista antes de encenderla); el aviso no se reenvía a Odoo", async () => {
    vi.spyOn(console, "log").mockImplementation(() => undefined);
    const { d, almacen, odoo, terminar } = deps();
    const res = await handleRequest(aviso({ todo: true }), { ...d, tienda: { activa: false, almacen, token: TOKEN } });
    await terminar();
    expect(res.status).toBe(200);
    expect(almacen.datos.has(CLAVE_INVALIDADO)).toBe(true);
    expect(odoo.paginasPedidas().sort()).toEqual([...RUTAS_PRINCIPALES].sort());
  });
});

describe("apagada, sin token o con KV caído: todo a Odoo como siempre", () => {
  it("TIENDA_ESTATICA=off (páginas y assets)", async () => {
    const { d, almacen } = deps();
    const apagada = { ...d, tienda: { activa: false, almacen, token: TOKEN } };
    const res = await handleRequest(get("/"), apagada);
    expect(res.headers.get("X-Dcasa-Cache")).toBeNull();
    expect(res.headers.get("Set-Cookie")).toContain("session_id");
    expect((await handleRequest(get(CSS, { headers: { Cookie: "session_id=v" } }), apagada)).headers.get("X-Dcasa-Cache")).toBeNull();
    expect(almacen.datos.size).toBe(0);
  });

  it("sin token válido no hay caché de páginas (Odoo no podría certificar nada); los assets sí se guardan", async () => {
    const { d, almacen, terminar } = deps();
    const sinToken = { ...d, tienda: { activa: true, almacen, token: "corto" } };
    await handleRequest(get("/"), sinToken);
    expect(almacen.datos.size).toBe(0);
    await handleRequest(get(CSS, { headers: { Cookie: "session_id=v" } }), sinToken);
    await terminar();
    expect(almacen.assets()).toEqual([claveAsset(CSS)]);
  });

  it("si KV no responde, sirve Odoo (páginas y assets)", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const { d } = deps();
    const roto = { ...d, tienda: { activa: true, almacen: almacenRoto({ leer: true, leerBinario: true }), token: TOKEN } };
    const res = await handleRequest(get("/"), roto);
    expect(res.status).toBe(200);
    expect(await res.text()).toContain("Iniciar sesión");
    const css = await handleRequest(get(CSS, { headers: { Cookie: "session_id=v" } }), roto);
    expect(css.status).toBe(200);
    expect(await css.text()).toContain("web.assets_frontend.min.css");
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
