import { describe, expect, it } from "vitest";

import {
  forwardedHeaders,
  isBlockedPath,
  isCacheableRequest,
  isCacheableResponse,
  notModified,
  notModifiedResponse,
  normalizePath,
  route,
  withSecurityHeaders,
} from "../src/routing";

const u = (path: string, host = "dcasapty.com") => new URL(`https://${host}${path}`);

describe("route", () => {
  it("responde el health check del borde", () => {
    expect(route(u("/__edge/health"), "GET")).toEqual({ kind: "health" });
  });

  it("bloquea el gestor de bases de datos", () => {
    for (const path of ["/web/database/manager", "/web/database/backup", "/xmlrpc/2/db"]) {
      expect(route(u(path), "POST")).toEqual({ kind: "blocked" });
    }
  });

  it("bloquea las API RPC de Odoo (/jsonrpc con servicio db, XML-RPC, /json/2)", () => {
    for (const path of [
      "/jsonrpc",
      "/jsonrpc/",
      "/xmlrpc/db",
      "/xmlrpc/common",
      "/xmlrpc/2/object",
      "/json/2",
      "/json/2/res.partner/search_read",
      "/doc-bearer/index.json",
    ]) {
      for (const method of ["GET", "POST"]) {
        expect(route(u(path), method), `${method} ${path}`).toEqual({ kind: "blocked" });
      }
    }
  });

  it("bloquea también las variantes codificadas, con // , mayúsculas o prefijo de idioma", () => {
    for (const path of [
      "//web/database/manager",
      "/web//database/manager",
      "///jsonrpc",
      "/web/%64atabase/manager",
      "/web/%2564atabase/manager", // doble codificación
      "/web%2Fdatabase%2Fmanager",
      "/%6Asonrpc",
      "/%4A%53%4F%4ERPC",
      "/JsonRpc",
      "/WEB/Database/Manager",
      "/json%2F2/res.partner/read",
      "/web/./database/manager",
      "/shop/../jsonrpc",
      "/shop/%2e%2e/jsonrpc",
      "/web\\database\\manager",
      "/es/jsonrpc",
      "/es_419/web/database/manager",
      "/en/xmlrpc/2/db",
      "/es-419/json/2/res.users/write",
    ]) {
      expect(isBlockedPath(path), path).toBe(true);
      expect(route(new URL(`https://dcasapty.com${path}`), "POST"), path).toEqual({ kind: "blocked" });
    }
  });

  it("no bloquea las rutas normales del sitio, del backend ni de Brian", () => {
    for (const path of [
      "/",
      "/shop",
      "/es/shop",
      "/socios",
      "/web/login",
      "/web/dataset/call_kw/res.partner/read",
      "/web/session/get_session_info",
      "/json/version",
      "/brian/mcp",
      "/doc",
      "/r/ABC123",
    ]) {
      expect(isBlockedPath(path), path).toBe(false);
    }
  });

  it("redirige www al dominio canónico", () => {
    expect(route(u("/shop?x=1", "www.dcasapty.com"), "GET", "dcasapty.com")).toEqual({
      kind: "redirect",
      location: "https://dcasapty.com/shop?x=1",
      status: 301,
    });
  });

  it("redirige los POST de www con 308 (conserva método y cuerpo)", () => {
    expect(route(u("/brian/mcp", "www.dcasapty.com"), "POST", "dcasapty.com")).toEqual({
      kind: "redirect",
      location: "https://dcasapty.com/brian/mcp",
      status: 308,
    });
  });

  it("deja pasar a Brian (MCP y Telegram) sin caché ni bloqueo", () => {
    for (const path of ["/brian/mcp", "/brian/telegram/secreto-largo"]) {
      for (const method of ["GET", "POST"]) {
        expect(route(u(path), method)).toEqual({ kind: "origin", cacheable: false });
      }
    }
  });

  it("no redirige otros hosts (p. ej. *.workers.dev)", () => {
    expect(route(u("/", "dcasa.cuenta.workers.dev"), "GET", "dcasapty.com").kind).toBe("origin");
  });

  it("marca como cacheables los estáticos y assets", () => {
    for (const path of [
      "/web/assets/1a2b3c/web.assets_frontend.min.css",
      "/website_dcasa/static/src/scss/dcasa.scss",
      "/web/image/product.template/5/image_512",
      "/web/content/12?unique=abc",
      "/web/content/12-abc/google-font-anton.css?unique=abc",
      "/web/content/12?download=true&unique=abc",
      "/website_dcasa/static/src/fonts/anton-latin.woff2",
    ]) {
      expect(route(u(path), "GET")).toEqual({ kind: "origin", cacheable: true });
    }
  });

  it("no cachea páginas, carrito ni escrituras", () => {
    expect(route(u("/"), "GET")).toEqual({ kind: "origin", cacheable: false });
    expect(route(u("/shop/cart"), "GET")).toEqual({ kind: "origin", cacheable: false });
    expect(route(u("/web/assets/x.css"), "POST")).toEqual({ kind: "origin", cacheable: false });
  });

  it("no cachea adjuntos sin versión ni las traducciones del JS", () => {
    for (const path of ["/web/content/12", "/web/content/12/factura.pdf", "/web/webclient/translations?lang=es_419"]) {
      expect(route(u(path), "GET"), path).toEqual({ kind: "origin", cacheable: false });
    }
  });
});

describe("normalizePath", () => {
  it("decodifica, colapsa barras, resuelve puntos y pasa a minúsculas", () => {
    expect(normalizePath("//Web//%64atabase/./x/../Manager/")).toBe("/web/database/manager");
    expect(normalizePath("/%252e%252e/jsonrpc")).toBe("/jsonrpc");
    expect(normalizePath("/a/%ZZ/b")).toBe("/a/%zz/b"); // secuencia inválida: no lanza
    expect(normalizePath("/")).toBe("/");
  });
});

describe("isCacheableResponse", () => {
  const res = (headers: Record<string, string>, status = 200) => new Response("x", { status, headers });

  it("acepta respuestas públicas sin cookie", () => {
    expect(isCacheableResponse(res({ "Cache-Control": "public, max-age=31536000, immutable" }))).toBe(true);
  });

  it("rechaza privadas, sin cabecera, con cookie o con error", () => {
    expect(isCacheableResponse(res({ "Cache-Control": "private, max-age=60" }))).toBe(false);
    expect(isCacheableResponse(res({}))).toBe(false);
    expect(isCacheableResponse(res({ "Cache-Control": "public", "Set-Cookie": "session_id=1" }))).toBe(false);
    expect(isCacheableResponse(res({ "Cache-Control": "public" }, 404))).toBe(false);
    expect(isCacheableResponse(res({ "Cache-Control": "public, no-store" }))).toBe(false);
  });

  it("rechaza lo que varía según la cookie o la credencial", () => {
    const publica = "public, max-age=604800";
    expect(isCacheableResponse(res({ "Cache-Control": publica, Vary: "Cookie" }))).toBe(false);
    expect(isCacheableResponse(res({ "Cache-Control": publica, Vary: "Accept-Encoding, Authorization" }))).toBe(false);
    expect(isCacheableResponse(res({ "Cache-Control": publica, Vary: "*" }))).toBe(false);
    expect(isCacheableResponse(res({ "Cache-Control": publica, Vary: "Accept-Encoding" }))).toBe(true);
  });
});

describe("isCacheableRequest", () => {
  it("solo lecturas sin credenciales explícitas", () => {
    const url = "https://dcasapty.com/web/image/product.template/5/image_512?unique=abc";
    expect(isCacheableRequest(new Request(url))).toBe(true);
    expect(isCacheableRequest(new Request(url, { method: "HEAD" }))).toBe(true);
    // La cookie de sesión no basta para saltarse la caché: Odoo se la pone a todo anónimo.
    expect(isCacheableRequest(new Request(url, { headers: { Cookie: "session_id=abc" } }))).toBe(true);
    expect(isCacheableRequest(new Request(url, { headers: { Authorization: "Bearer x" } }))).toBe(false);
    expect(isCacheableRequest(new Request(url, { method: "POST", body: "x" }))).toBe(false);
  });
});

describe("notModified", () => {
  const ok = new Response("x", { headers: { ETag: '"v1"', "Last-Modified": "Wed, 01 Oct 2026 10:00:00 GMT" } });
  const req = (headers: Record<string, string>) => new Request("https://dcasapty.com/web/assets/a/b.css", { headers });

  it("compara ETag (débil o fuerte) y, si no hay ETag pedido, la fecha", () => {
    expect(notModified(req({ "If-None-Match": '"v1"' }), ok)).toBe(true);
    expect(notModified(req({ "If-None-Match": 'W/"v1", "v0"' }), ok)).toBe(true);
    expect(notModified(req({ "If-None-Match": '"v2"' }), ok)).toBe(false);
    expect(notModified(req({ "If-Modified-Since": "Wed, 01 Oct 2026 11:00:00 GMT" }), ok)).toBe(true);
    expect(notModified(req({ "If-Modified-Since": "Wed, 01 Oct 2026 09:00:00 GMT" }), ok)).toBe(false);
    expect(notModified(req({}), ok)).toBe(false);
  });

  it("el 304 conserva las cabeceras de caché y no lleva cuerpo", async () => {
    const res = notModifiedResponse(
      new Response("x", { headers: { ETag: '"v1"', "Cache-Control": "public, max-age=60", "Content-Type": "text/css" } }),
    );
    expect(res.status).toBe(304);
    expect(res.headers.get("ETag")).toBe('"v1"');
    expect(res.headers.get("Cache-Control")).toBe("public, max-age=60");
    expect(res.headers.get("Content-Type")).toBeNull();
    expect(await res.text()).toBe("");
  });
});

describe("forwardedHeaders", () => {
  it("pasa host, esquema e IP real a Odoo", () => {
    const req = new Request("https://dcasapty.com/shop", { headers: { "CF-Connecting-IP": "190.1.2.3" } });
    const headers = forwardedHeaders(req);
    expect(headers.get("X-Forwarded-Host")).toBe("dcasapty.com");
    expect(headers.get("X-Forwarded-Proto")).toBe("https");
    expect(headers.get("X-Forwarded-For")).toBe("190.1.2.3");
  });
});

describe("withSecurityHeaders", () => {
  it("agrega cabeceras de seguridad sin pisar las de Odoo", () => {
    const res = withSecurityHeaders(new Response("ok", { headers: { "X-Frame-Options": "DENY" } }));
    expect(res.headers.get("X-Content-Type-Options")).toBe("nosniff");
    expect(res.headers.get("Strict-Transport-Security")).toContain("max-age=");
    expect(res.headers.get("X-Frame-Options")).toBe("DENY");
  });
});
