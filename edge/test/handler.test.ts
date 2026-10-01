import { describe, expect, it, vi } from "vitest";

import { handleRequest, runScheduled } from "../src/handler";

function memoryCache() {
  const store = new Map<string, Response>();
  return {
    store,
    match: vi.fn(async (req: Request) => store.get(req.url)?.clone()),
    put: vi.fn(async (req: Request, res: Response) => void store.set(req.url, res)),
  };
}

describe("handleRequest", () => {
  it("reenvía las páginas a Odoo con cabeceras de proxy y seguridad", async () => {
    const forward = vi.fn(async (req: Request) => new Response(req.headers.get("X-Forwarded-Host")));
    const res = await handleRequest(new Request("https://dcasapty.com/"), { forward });
    expect(await res.text()).toBe("dcasapty.com");
    expect(res.headers.get("X-Content-Type-Options")).toBe("nosniff");
    expect(forward).toHaveBeenCalledOnce();
  });

  it("nunca llega a Odoo con el gestor de bases de datos", async () => {
    const forward = vi.fn();
    const res = await handleRequest(new Request("https://dcasapty.com/web/database/manager"), { forward });
    expect(res.status).toBe(404);
    expect(forward).not.toHaveBeenCalled();
  });

  it("sirve los assets desde la caché del borde después del primer pedido", async () => {
    const cache = memoryCache();
    const forward = vi.fn(async () => new Response("css", { headers: { "Cache-Control": "public, max-age=31536000" } }));
    const url = "https://dcasapty.com/web/assets/abc/web.assets_frontend.min.css";

    expect(await (await handleRequest(new Request(url), { forward, cache })).text()).toBe("css");
    expect(await (await handleRequest(new Request(url), { forward, cache })).text()).toBe("css");
    expect(forward).toHaveBeenCalledOnce();
  });

  it("pone cabeceras de seguridad también en lo cacheable y en lo servido desde la caché", async () => {
    const cache = memoryCache();
    const forward = vi.fn(async () => new Response("css", { headers: { "Cache-Control": "public, max-age=31536000" } }));
    const url = "https://dcasapty.com/web/assets/abc/web.assets_frontend.min.css";

    const primera = await handleRequest(new Request(url), { forward, cache });
    const segunda = await handleRequest(new Request(url), { forward, cache });
    expect(forward).toHaveBeenCalledOnce();
    for (const res of [primera, segunda]) {
      expect(res.headers.get("X-Content-Type-Options")).toBe("nosniff");
      expect(res.headers.get("Strict-Transport-Security")).toContain("max-age=");
      expect(res.headers.get("Cache-Control")).toBe("public, max-age=31536000");
    }
  });

  it("marca HIT/MISS/BYPASS para poder medir la caché del borde", async () => {
    const cache = memoryCache();
    const forward = vi.fn(async () => new Response("css", { headers: { "Cache-Control": "public, max-age=31536000" } }));
    const url = "https://dcasapty.com/web/assets/abc/web.assets_frontend.min.css";

    expect((await handleRequest(new Request(url), { forward, cache })).headers.get("X-Dcasa-Cache")).toBe("MISS");
    expect((await handleRequest(new Request(url), { forward, cache })).headers.get("X-Dcasa-Cache")).toBe("HIT");
    // Las páginas no llevan la marca: no pasan por la caché.
    const pagina = await handleRequest(new Request("https://dcasapty.com/shop"), { forward, cache });
    expect(pagina.headers.get("X-Dcasa-Cache")).toBeNull();
  });

  it("nunca guarda lo que Odoo sirve a un usuario con sesión (private) ni con cookie", async () => {
    const cache = memoryCache();
    const url = "https://dcasapty.com/web/image/res.users/2/avatar_128?unique=abc";
    const casos: Record<string, string>[] = [
      { "Cache-Control": "private, max-age=31536000, immutable" },
      { "Cache-Control": "public, max-age=31536000", "Set-Cookie": "session_id=x; HttpOnly" },
    ];
    for (const headers of casos) {
      const forward = vi.fn(async () => new Response("img", { headers }));
      const res = await handleRequest(new Request(url, { headers: { Cookie: "session_id=abc" } }), { forward, cache });
      expect(res.headers.get("X-Dcasa-Cache")).toBe("BYPASS");
    }
    expect(cache.put).not.toHaveBeenCalled();
  });

  it("con Authorization ni lee ni llena la caché", async () => {
    const cache = memoryCache();
    const forward = vi.fn(async () => new Response("css", { headers: { "Cache-Control": "public, max-age=31536000" } }));
    const url = "https://dcasapty.com/web/assets/abc/web.assets_frontend.min.css";
    await handleRequest(new Request(url), { forward, cache });
    const res = await handleRequest(new Request(url, { headers: { Authorization: "Bearer x" } }), { forward, cache });
    expect(res.headers.get("X-Dcasa-Cache")).toBe("BYPASS");
    expect(forward).toHaveBeenCalledTimes(2);
    expect(cache.match).toHaveBeenCalledOnce();
  });

  it("llena la caché aunque el navegador revalide y le responde 304 desde el borde", async () => {
    const cache = memoryCache();
    const forward = vi.fn(async (req: Request) =>
      req.headers.has("If-None-Match")
        ? new Response(null, { status: 304, headers: { ETag: '"v1"' } })
        : new Response("woff2", { headers: { "Cache-Control": "public, max-age=604800", ETag: '"v1"' } }),
    );
    const url = "https://dcasapty.com/website_dcasa/static/src/fonts/anton-latin.woff2";
    const revalida = () => new Request(url, { headers: { "If-None-Match": '"v1"' } });

    const primera = await handleRequest(revalida(), { forward, cache });
    expect(primera.status).toBe(304);
    expect(primera.headers.get("X-Dcasa-Cache")).toBe("MISS");
    expect(forward.mock.calls[0][0].headers.has("If-None-Match")).toBe(false);
    expect(cache.put).toHaveBeenCalledOnce();

    const segunda = await handleRequest(revalida(), { forward, cache });
    expect(segunda.status).toBe(304);
    expect(segunda.headers.get("X-Dcasa-Cache")).toBe("HIT");
    const completa = await handleRequest(new Request(url), { forward, cache });
    expect(completa.status).toBe(200);
    expect(await completa.text()).toBe("woff2");
    expect(forward).toHaveBeenCalledOnce();
  });

  it("deja que Odoo conteste el 304 de las imágenes sin versión (no se guardan)", async () => {
    const cache = memoryCache();
    const forward = vi.fn(async (_req: Request) => new Response(null, { status: 304, headers: { ETag: '"a"' } }));
    const url = "https://dcasapty.com/web/image/res.partner/3/avatar_128";
    const res = await handleRequest(new Request(url, { headers: { "If-None-Match": '"a"' } }), { forward, cache });
    expect(res.status).toBe(304);
    expect(forward.mock.calls[0][0].headers.get("If-None-Match")).toBe('"a"');
    expect(cache.put).not.toHaveBeenCalled();
  });

  it("bloquea /jsonrpc y sus variantes codificadas sin llegar a Odoo", async () => {
    const forward = vi.fn();
    for (const path of ["/jsonrpc", "//jsonrpc", "/%6Asonrpc", "/es/jsonrpc", "/web/%64atabase/manager", "/json/2/res.users/write"]) {
      const res = await handleRequest(new Request(`https://dcasapty.com${path}`, { method: "POST", body: "{}" }), { forward });
      expect(res.status, path).toBe(404);
    }
    expect(forward).not.toHaveBeenCalled();
  });

  it("no guarda en caché respuestas privadas", async () => {
    const cache = memoryCache();
    const forward = vi.fn(async () => new Response("img", { headers: { "Cache-Control": "private" } }));
    await handleRequest(new Request("https://dcasapty.com/web/image/res.partner/3/avatar_128"), { forward, cache });
    expect(cache.put).not.toHaveBeenCalled();
  });

  it("reenvía el POST de MCP a Odoo con su cuerpo y su Authorization, sin caché", async () => {
    const cache = memoryCache();
    const forward = vi.fn(async (req: Request) =>
      Response.json({ auth: req.headers.get("Authorization"), body: await req.text(), method: req.method }),
    );
    const body = JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tools/list" });
    const res = await handleRequest(
      new Request("https://dcasapty.com/brian/mcp", {
        method: "POST",
        body,
        headers: { Authorization: "Bearer clave", "Content-Type": "application/json" },
      }),
      { forward, cache },
    );
    expect(await res.json()).toEqual({ auth: "Bearer clave", body, method: "POST" });
    expect(cache.match).not.toHaveBeenCalled();
    expect(cache.put).not.toHaveBeenCalled();
  });

  it("deja pasar el webhook de Telegram con su encabezado secreto", async () => {
    const forward = vi.fn(async (req: Request) => new Response(req.headers.get("X-Telegram-Bot-Api-Secret-Token")));
    const res = await handleRequest(
      new Request("https://dcasapty.com/brian/telegram/s3cr3t", {
        method: "POST",
        body: "{}",
        headers: { "X-Telegram-Bot-Api-Secret-Token": "s3cr3t" },
      }),
      { forward },
    );
    expect(res.status).toBe(200);
    expect(await res.text()).toBe("s3cr3t");
  });

  it("redirige www a dominio canónico", async () => {
    const res = await handleRequest(new Request("https://www.dcasapty.com/shop"), {
      forward: vi.fn(),
      canonicalHost: "dcasapty.com",
    });
    expect(res.status).toBe(301);
    expect(res.headers.get("Location")).toBe("https://dcasapty.com/shop");
  });

  it("expone un health check propio del borde", async () => {
    const res = await handleRequest(new Request("https://dcasapty.com/__edge/health"), { forward: vi.fn() });
    expect(await res.text()).toBe("ok");
  });
});

describe("runScheduled (cron horario)", () => {
  it("no toca a Odoo si ya está encendido (su propio cron corre las tareas)", async () => {
    for (const status of ["running", "healthy"]) {
      const wake = vi.fn();
      expect(await runScheduled({ status: async () => status, wake })).toBe("encendido");
      expect(wake).not.toHaveBeenCalled();
    }
  });

  it("despierta a Odoo una vez si está apagado", async () => {
    for (const status of ["stopped", "stopped_with_code"]) {
      const wake = vi.fn(async () => new Response("ok"));
      expect(await runScheduled({ status: async () => status, wake })).toBe("despertado");
      expect(wake).toHaveBeenCalledOnce();
    }
  });
});
