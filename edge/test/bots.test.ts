import { describe, expect, it, vi } from "vitest";

import {
  cubetaDe,
  esEscaner,
  esSondeo,
  filtrarAutomatizados,
  LIMITES,
  LimitadorMemoria,
  type Limitador,
} from "../src/bots";
import { handleRequest, variablesDelContenedor } from "../src/handler";

const SITIO = "https://dcasapty.com";

function post(ruta: string, ip = "190.1.2.3", headers: Record<string, string> = {}): Request {
  return new Request(SITIO + ruta, { method: "POST", headers: { "CF-Connecting-IP": ip, ...headers }, body: "x=1" });
}

describe("rutas de sondeo", () => {
  it("corta lo que solo piden los escáneres", () => {
    for (const ruta of [
      "/wp-admin",
      "/wp-admin/setup-config.php",
      "/wp-login.php",
      "/xmlrpc.php",
      "/.env",
      "/.env.production",
      "/api/.env",
      "/.git/config",
      "/phpmyadmin/index.php",
      "/vendor/phpunit/phpunit/src/Util/PHP/eval-stdin.php",
      "/cgi-bin/luci",
      "/index.php",
      "/es/wp-admin",
      "/%2ewp-admin/../.env",
      "/actuator/health",
      "/backup.sql",
    ]) {
      expect(esSondeo(ruta), ruta).toBe(true);
    }
  });

  it("nunca toca las rutas de la tienda, del panel ni de los buscadores", () => {
    for (const ruta of [
      "/",
      "/shop",
      "/shop/sofa-modular-3-puestos-12",
      "/shop/category/salas-4",
      "/web/login",
      "/odoo",
      "/my",
      "/socios",
      "/brian/mcp",
      "/robots.txt",
      "/sitemap.xml",
      "/.well-known/apple-developer-merchantid-domain-association",
      "/web/image/product.template/12/image_1024",
      "/web/assets/1/web.assets_frontend.min.js",
      "/website_dcasa/static/src/fonts/anton.woff2",
      "/privacidad",
    ]) {
      expect(esSondeo(ruta), ruta).toBe(false);
    }
  });
});

describe("escáneres por User-Agent", () => {
  it("reconoce herramientas de ataque que se anuncian", () => {
    for (const ua of ["sqlmap/1.8#stable (https://sqlmap.org)", "Mozilla/5.00 (Nikto/2.5.0)", "Nuclei - Open-source project", "WPScan v3.8"]) {
      expect(esEscaner(ua), ua).toBe(true);
    }
  });

  it("deja pasar buscadores, previsualizadores, agentes de IA y librerías", () => {
    for (const ua of [
      "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
      "Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)",
      "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
      "WhatsApp/2.23.20.0",
      "TelegramBot (like TwitterBot)",
      "meta-externalfetcher/1.1",
      "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; ChatGPT-User/1.0; +https://openai.com/bot)",
      "Claude-User (claude-user@anthropic.com)",
      "python-httpx/0.27.0",
      "curl/8.5.0",
      "node",
      "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148",
    ]) {
      expect(esEscaner(ua), ua).toBe(false);
    }
    expect(esEscaner(null)).toBe(false);
  });
});

describe("límite de intentos", () => {
  it("clasifica solo los POST sensibles", () => {
    expect(cubetaDe("POST", "/web/login")).toBe("acceso");
    expect(cubetaDe("POST", "/web/login/totp")).toBe("acceso");
    expect(cubetaDe("POST", "/web/login/dcasa-2fa")).toBe("acceso");
    expect(cubetaDe("POST", "/es/web/reset_password")).toBe("acceso");
    expect(cubetaDe("POST", "/web/signup")).toBe("acceso");
    expect(cubetaDe("POST", "/socios/entrar")).toBe("acceso");
    expect(cubetaDe("POST", "/website/form/crm.lead")).toBe("formulario");
    expect(cubetaDe("POST", "/shop/cart/add")).toBe("carrito");
    expect(cubetaDe("POST", "/shop/address/submit")).toBe("carrito");
    expect(cubetaDe("GET", "/web/login")).toBeNull();
    expect(cubetaDe("POST", "/brian/mcp")).toBeNull(); // MCP tiene su propio límite por usuario
    expect(cubetaDe("POST", "/brian/telegram/secreto")).toBeNull();
    expect(cubetaDe("POST", "/web/dataset/call_kw/res.partner/read")).toBeNull();
    expect(cubetaDe("POST", "/web/loginx")).toBeNull();
  });

  it("el contador en memoria corta al pasar el límite y se renueva cada minuto", async () => {
    let t = 0;
    const limitador = new LimitadorMemoria(3, 60_000, () => t);
    const veces = async () => (await limitador.limit({ key: "a" })).success;
    expect([await veces(), await veces(), await veces(), await veces()]).toEqual([true, true, true, false]);
    expect((await limitador.limit({ key: "b" })).success).toBe(true); // otra IP, otra cuenta
    t = 60_000;
    expect(await veces()).toBe(true);
  });

  it("no crece sin límite con muchas IP", async () => {
    const limitador = new LimitadorMemoria(1, 60_000, () => 0, 3);
    for (const ip of ["1", "2", "3", "4"]) await limitador.limit({ key: ip });
    expect((await limitador.limit({ key: "1" })).success).toBe(true); // se vació al llenarse
  });

  it("responde 429 con Retry-After usando el binding de Cloudflare si existe", async () => {
    const binding: Limitador = { limit: vi.fn(async () => ({ success: false })) };
    const res = await filtrarAutomatizados(post("/web/login"), new URL(SITIO + "/web/login"), { acceso: binding });
    expect(res?.status).toBe(429);
    expect(res?.headers.get("Retry-After")).toBe("60");
    expect(binding.limit).toHaveBeenCalledWith({ key: "acceso:190.1.2.3" });
  });

  it("si el limitador falla, deja pasar (Odoo tiene su propio bloqueo)", async () => {
    const roto: Limitador = { limit: vi.fn(async () => Promise.reject(new Error("caído"))) };
    const error = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(await filtrarAutomatizados(post("/web/login"), new URL(SITIO + "/web/login"), { acceso: roto })).toBeNull();
    error.mockRestore();
  });

  it("sin IP de Cloudflare no limita (pruebas locales)", async () => {
    const req = new Request(SITIO + "/web/login", { method: "POST", body: "x" });
    expect(await filtrarAutomatizados(req, new URL(req.url))).toBeNull();
  });
});

describe("handleRequest con el filtro", () => {
  it("un sondeo recibe 404 sin despertar a Odoo, con cabeceras de seguridad", async () => {
    const forward = vi.fn();
    const res = await handleRequest(new Request(SITIO + "/wp-login.php"), { forward });
    expect(res.status).toBe(404);
    expect(res.headers.get("Strict-Transport-Security")).toContain("max-age");
    expect(forward).not.toHaveBeenCalled();
  });

  it("un escáner recibe 403; Googlebot llega a Odoo", async () => {
    const forward = vi.fn(async () => new Response("ok"));
    const escaner = await handleRequest(new Request(SITIO + "/", { headers: { "User-Agent": "sqlmap/1.8" } }), { forward });
    expect(escaner.status).toBe(403);
    const google = await handleRequest(
      new Request(SITIO + "/shop", { headers: { "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1)" } }),
      { forward },
    );
    expect(google.status).toBe(200);
    expect(forward).toHaveBeenCalledOnce();
  });

  it("una ráfaga de logins desde una IP se corta en el borde", async () => {
    const forward = vi.fn(async () => new Response("login"));
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const estados: number[] = [];
    for (let i = 0; i < LIMITES.acceso + 2; i++) {
      estados.push((await handleRequest(post("/web/login", "200.9.9.9"), { forward })).status);
    }
    warn.mockRestore();
    expect(estados.slice(0, LIMITES.acceso).every((s) => s === 200)).toBe(true);
    expect(estados.slice(LIMITES.acceso)).toEqual([429, 429]);
    expect(forward).toHaveBeenCalledTimes(LIMITES.acceso);
    // Otra IP (otro cliente) entra normal.
    expect((await handleRequest(post("/web/login", "200.9.9.10"), { forward })).status).toBe(200);
  });

  it("Brian por MCP y el webhook de Telegram no pasan por el límite", async () => {
    const forward = vi.fn(async () => new Response("{}"));
    for (let i = 0; i < 30; i++) {
      const res = await handleRequest(post("/brian/mcp", "200.8.8.8", { Authorization: "Bearer clave" }), { forward });
      expect(res.status).toBe(200);
    }
  });

  it("gestor de bases y API de Odoo siguen bloqueados", async () => {
    const forward = vi.fn();
    for (const ruta of ["/web/database/manager", "/web/database/selector", "/web/database/drop", "/jsonrpc", "/xmlrpc/2/db"]) {
      expect((await handleRequest(new Request(SITIO + ruta, { method: "POST" }), { forward })).status, ruta).toBe(404);
    }
    expect(forward).not.toHaveBeenCalled();
  });
});

describe("cabeceras de seguridad", () => {
  it("HSTS, nosniff, frame-ancestors y X-Frame-Options en /web y /odoo", async () => {
    const forward = vi.fn(async () => new Response("<html></html>", { headers: { "Content-Type": "text/html" } }));
    for (const ruta of ["/web/login", "/odoo", "/my"]) {
      const res = await handleRequest(new Request(SITIO + ruta), { forward });
      expect(res.headers.get("Strict-Transport-Security")).toBe("max-age=31536000; includeSubDomains");
      expect(res.headers.get("X-Content-Type-Options")).toBe("nosniff");
      expect(res.headers.get("X-Frame-Options")).toBe("SAMEORIGIN");
      expect(res.headers.get("Content-Security-Policy")).toBe("frame-ancestors 'self'");
    }
  });

  it("no pisa la CSP que mande Odoo", async () => {
    const forward = vi.fn(async () => new Response("x", { headers: { "Content-Security-Policy": "default-src 'none'" } }));
    const res = await handleRequest(new Request(SITIO + "/web/content/1"), { forward });
    expect(res.headers.get("Content-Security-Policy")).toBe("default-src 'none'");
  });
});

describe("variables de seguridad para el contenedor", () => {
  it("pasa la obligatoriedad del 2FA y Turnstile", () => {
    const vars = variablesDelContenedor({
      DCASA_2FA_OBLIGATORIO: "1",
      DCASA_2FA_ALCANCE: "internos",
      TURNSTILE_SITE_KEY: "0x4AAA",
      TURNSTILE_SECRET: "0x4BBB",
      DCASA_ROBOTS_IA: "cerrada",
    });
    expect(vars).toMatchObject({
      DCASA_2FA_OBLIGATORIO: "1",
      DCASA_2FA_ALCANCE: "internos",
      TURNSTILE_SITE_KEY: "0x4AAA",
      TURNSTILE_SECRET: "0x4BBB",
      DCASA_ROBOTS_IA: "cerrada",
    });
    expect(variablesDelContenedor({})).not.toHaveProperty("DCASA_2FA_OBLIGATORIO");
  });
});
