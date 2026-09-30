import { describe, expect, it } from "vitest";

import { forwardedHeaders, isCacheableResponse, route, withSecurityHeaders } from "../src/routing";

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
    ]) {
      expect(route(u(path), "GET")).toEqual({ kind: "origin", cacheable: true });
    }
  });

  it("no cachea páginas, carrito ni escrituras", () => {
    expect(route(u("/"), "GET")).toEqual({ kind: "origin", cacheable: false });
    expect(route(u("/shop/cart"), "GET")).toEqual({ kind: "origin", cacheable: false });
    expect(route(u("/web/assets/x.css"), "POST")).toEqual({ kind: "origin", cacheable: false });
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
