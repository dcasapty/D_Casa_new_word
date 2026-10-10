import { describe, expect, it, vi } from "vitest";

import { handleRequest, secretosFaltantes, SECRETOS_PARA_ARRANCAR, variablesDelContenedor } from "../src/handler";
import { atenderJuan, cabecerasHaciaOdoo, esRutaJuan, MAX_CUERPO_JUAN } from "../src/juan";
import { isBlockedPath, route } from "../src/routing";

const u = (path: string, host = "dcasapty.com") => new URL(`https://${host}${path}`);
const BASE = "https://dcasa/dcasa/juan/v1";

describe("las rutas de Juan no se alcanzan desde internet", () => {
  const rutas = [
    "/dcasa/juan/v1/mensaje",
    "/dcasa/juan/v1/estado?canal=whatsapp_qr&id_externo=1",
    "/dcasa/juan/v1/config",
    "/dcasa/juan/v1/herramientas",
    "/dcasa/juan/v1/herramienta",
    "/dcasa/juan/v1/seguimiento/hecho",
    "/dcasa/juan",
    "/dcasa/juan/",
  ];

  it("el borde las bloquea (404) con cualquier método", () => {
    for (const path of rutas) {
      for (const method of ["GET", "POST", "PUT", "DELETE"]) {
        expect(route(u(path), method), `${method} ${path}`).toEqual({ kind: "blocked" });
      }
    }
  });

  it("también las variantes codificadas, con barras repetidas, mayúsculas o prefijo de idioma", () => {
    for (const path of [
      "//dcasa//juan/v1/mensaje",
      "/DCASA/Juan/v1/Mensaje",
      "/dcasa/%6Auan/v1/mensaje",
      "/dcasa%2Fjuan%2Fv1%2Fmensaje",
      "/dcasa/%256Auan/v1/config", // doble codificación
      "/dcasa/./juan/v1/config",
      "/shop/../dcasa/juan/v1/config",
      "/es/dcasa/juan/v1/mensaje",
      "/es_419/dcasa/juan/v1/mensaje",
    ]) {
      expect(isBlockedPath(path), path).toBe(true);
      expect(route(u(path), "POST"), path).toEqual({ kind: "blocked" });
    }
  });

  it("no bloquea las otras rutas /dcasa/ del sitio", () => {
    for (const path of ["/dcasa/salud", "/dcasa/img/foto.webp?v=abc", "/dcasa/borde/csrf", "/dcasa/tienda"]) {
      expect(isBlockedPath(path), path).toBe(false);
    }
  });

  it("desde internet nunca llega a Odoo y no se distingue de una ruta inexistente", async () => {
    const forward = vi.fn();
    for (const method of ["GET", "POST"]) {
      const res = await handleRequest(new Request("https://dcasapty.com/dcasa/juan/v1/mensaje", { method }), { forward });
      expect(res.status).toBe(404);
    }
    const res = await handleRequest(
      new Request("https://dcasapty.com/dcasa/juan/v1/herramienta", {
        method: "POST",
        headers: { Authorization: "Bearer cualquiera" },
        body: "{}",
      }),
      { forward },
    );
    expect(res.status).toBe(404);
    expect(forward).not.toHaveBeenCalled();
  });
});

describe("cabecerasHaciaOdoo", () => {
  it("nunca deja pasar las cabeceras de la puerta del equipo ni las marcas internas, ni con otra capitalización", () => {
    const pedido = new Request("https://dcasa/dcasa/juan/v1/mensaje", {
      headers: {
        Authorization: "Bearer x",
        Cookie: "session_id=abc",
        "X-Dcasa-Borde": "token",
        "X-Dcasa-Puerta": "a@b.c|9999999999|firma",
        "x-dcasa-puerta-modo": "1|0|9999999999|firma",
      },
    });
    const cabeceras = cabecerasHaciaOdoo(pedido, "dcasapty.com");
    for (const nombre of ["Cookie", "X-Dcasa-Borde", "X-Dcasa-Puerta", "X-Dcasa-Puerta-Modo"]) {
      expect(cabeceras.has(nombre), nombre).toBe(false);
    }
    expect(cabeceras.get("Authorization")).toBe("Bearer x");
    expect(cabeceras.get("X-Forwarded-Host")).toBe("dcasapty.com");
  });
});

describe("esRutaJuan", () => {
  it("solo lo que cuelga de /dcasa/juan/ (ruta normalizada)", () => {
    expect(esRutaJuan("/dcasa/juan/v1/mensaje")).toBe(true);
    expect(esRutaJuan("/dcasa/juan/v1/seguimiento/hecho")).toBe(true);
    expect(esRutaJuan("/DCASA/JUAN/v1/config")).toBe(true);
    for (const no of [
      "/",
      "/dcasa/salud",
      "/dcasa/juan",
      "/dcasa/juanito/v1",
      "/jsonrpc",
      "/web/database/manager",
      "/dcasa/juan/../../web/database/manager",
      "/dcasa/juan/%2e%2e/%2e%2e/jsonrpc",
      "/dcasa/juan/..%2f..%2fjsonrpc",
    ]) {
      expect(esRutaJuan(no), no).toBe(false);
    }
  });
});

describe("atenderJuan (clase JuanEntrada, solo por el service binding)", () => {
  const odooOk = () => vi.fn(async (_req: Request) => new Response(JSON.stringify({ ok: true }), { headers: { "Content-Type": "application/json" } }));

  it("reenvía a Odoo con el token tal cual, sin cookies y con el dominio canónico", async () => {
    const forward = odooOk();
    const res = await atenderJuan(
      new Request(`${BASE}/estado?canal=whatsapp_qr&id_externo=50760261919`, {
        headers: { Authorization: "Bearer TOKEN-DE-PRUEBA", Cookie: "session_id=robada", "X-Dcasa-Borde": "interno" },
      }),
      { forward, canonicalHost: "dcasapty.com" },
    );
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ ok: true });
    const enviado = forward.mock.calls[0][0] as Request;
    expect(enviado.method).toBe("GET");
    expect(new URL(enviado.url).pathname).toBe("/dcasa/juan/v1/estado");
    expect(new URL(enviado.url).search).toBe("?canal=whatsapp_qr&id_externo=50760261919");
    expect(enviado.headers.get("Authorization")).toBe("Bearer TOKEN-DE-PRUEBA");
    expect(enviado.headers.get("Cookie")).toBeNull();
    expect(enviado.headers.get("X-Dcasa-Borde")).toBeNull();
    expect(enviado.headers.get("X-Forwarded-Host")).toBe("dcasapty.com");
    expect(enviado.headers.get("X-Forwarded-Proto")).toBe("https");
  });

  it("reenvía el cuerpo de un POST completo", async () => {
    const forward = odooOk();
    const cuerpo = JSON.stringify({ canal: "telegram", id_externo: "1", id_mensaje: "m1", texto: "Hola ñandú" });
    await atenderJuan(
      new Request(`${BASE}/mensaje`, { method: "POST", headers: { "Content-Type": "application/json" }, body: cuerpo }),
      { forward },
    );
    const enviado = forward.mock.calls[0][0] as Request;
    expect(enviado.method).toBe("POST");
    expect(await enviado.text()).toBe(cuerpo);
    expect(enviado.headers.get("Content-Type")).toBe("application/json");
  });

  it("sin dominio canónico usa el de la petición", async () => {
    const forward = odooOk();
    await atenderJuan(new Request(`${BASE}/config`), { forward });
    expect((forward.mock.calls[0][0] as Request).headers.get("X-Forwarded-Host")).toBe("dcasa");
  });

  it("no es un proxy de Odoo: cualquier otra ruta es 404 y no llega al contenedor", async () => {
    const forward = odooOk();
    for (const path of [
      "/",
      "/web/login",
      "/jsonrpc",
      "/web/database/manager",
      "/brian/mcp",
      "/dcasa/salud",
      "/dcasa/juan/../../jsonrpc",
      "/dcasa/juan/%2e%2e/web/database/manager",
    ]) {
      const res = await atenderJuan(new Request(`https://dcasa${path}`, { method: "POST", body: "{}" }), { forward });
      expect(res.status, path).toBe(404);
      expect(((await res.json()) as { ok: boolean }).ok).toBe(false);
    }
    expect(forward).not.toHaveBeenCalled();
  });

  it("solo GET y POST", async () => {
    const forward = odooOk();
    for (const method of ["PUT", "DELETE", "PATCH"]) {
      const res = await atenderJuan(new Request(`${BASE}/config`, { method }), { forward });
      expect(res.status, method).toBe(405);
      expect(res.headers.get("Allow")).toBe("GET, POST");
    }
    expect(forward).not.toHaveBeenCalled();
  });

  it("corta los cuerpos demasiado grandes (declarados o reales)", async () => {
    const forward = odooOk();
    const declarado = await atenderJuan(
      new Request(`${BASE}/mensaje`, { method: "POST", headers: { "Content-Length": String(MAX_CUERPO_JUAN + 1) }, body: "x" }),
      { forward },
    );
    expect(declarado.status).toBe(413);
    const real = await atenderJuan(
      new Request(`${BASE}/mensaje`, { method: "POST", body: new Uint8Array(MAX_CUERPO_JUAN + 1) }),
      { forward },
    );
    expect(real.status).toBe(413);
    expect(forward).not.toHaveBeenCalled();
  });

  it("si Odoo está arrancando contesta JSON 503 con Retry-After, no la página HTML", async () => {
    const arrancando = vi.fn(
      async () =>
        new Response("<html>arrancando</html>", {
          status: 503,
          headers: { "X-Dcasa-Estado": "arrancando", "Retry-After": "30", "Content-Type": "text/html" },
        }),
    );
    const res = await atenderJuan(new Request(`${BASE}/config`), { forward: arrancando });
    expect(res.status).toBe(503);
    expect(res.headers.get("Retry-After")).toBe("30");
    expect(res.headers.get("Content-Type")).toContain("application/json");
    expect(await res.json()).toEqual({ ok: false, error: "Odoo está arrancando.", reintentar_en: 30 });
  });

  it("si el contenedor no responde (excepción) contesta JSON 503", async () => {
    const roto = vi.fn(async () => {
      throw new Error("Durable Object reiniciando");
    });
    const res = await atenderJuan(new Request(`${BASE}/config`), { forward: roto });
    expect(res.status).toBe(503);
    expect(res.headers.get("Retry-After")).toBe("15");
    const cuerpo = (await res.json()) as { ok: boolean; error: string };
    expect(cuerpo.ok).toBe(false);
    expect(JSON.stringify(cuerpo)).not.toContain("Durable Object"); // no filtra detalles internos
  });

  it("los errores de Odoo (401, 503 sin token, 422) pasan tal cual; nunca cookies ni caché", async () => {
    for (const status of [401, 422, 503]) {
      const forward = vi.fn(
        async () =>
          new Response(JSON.stringify({ ok: false, error: "x" }), {
            status,
            headers: { "Set-Cookie": "session_id=abc", "Cache-Control": "public, max-age=3600", "Content-Type": "application/json" },
          }),
      );
      const res = await atenderJuan(new Request(`${BASE}/herramienta`, { method: "POST", body: "{}" }), { forward });
      expect(res.status).toBe(status);
      expect(res.headers.get("Set-Cookie")).toBeNull();
      expect(res.headers.get("Cache-Control")).toBe("no-store");
      expect(await res.json()).toEqual({ ok: false, error: "x" });
    }
  });
});

describe("variables de Juan hacia el contenedor", () => {
  const NOMBRES = ["JUAN_ODOO_TOKEN", "JUAN_WORKER_TOKEN", "JUAN_URL"] as const;

  it("se pasan a Odoo cuando existen", () => {
    const vars = variablesDelContenedor({
      JUAN_ODOO_TOKEN: "o".repeat(40),
      JUAN_WORKER_TOKEN: "w".repeat(40),
      JUAN_URL: "https://juan.example.workers.dev",
    });
    expect(vars).toMatchObject({
      JUAN_ODOO_TOKEN: "o".repeat(40),
      JUAN_WORKER_TOKEN: "w".repeat(40),
      JUAN_URL: "https://juan.example.workers.dev",
    });
  });

  it("no se pasan cuando faltan o vienen vacías", () => {
    for (const nombre of NOMBRES) {
      expect(variablesDelContenedor({})).not.toHaveProperty(nombre);
      expect(variablesDelContenedor({ [nombre]: "" })).not.toHaveProperty(nombre);
      expect(variablesDelContenedor({ [nombre]: undefined })).not.toHaveProperty(nombre);
    }
  });

  it("son opcionales: sin ellas el contenedor arranca (no son secretos para arrancar)", () => {
    for (const nombre of NOMBRES) {
      expect(SECRETOS_PARA_ARRANCAR as readonly string[]).not.toContain(nombre);
    }
    const base = {
      ADMIN_PASSWORD: "a",
      R2_ENDPOINT: "https://x.r2.cloudflarestorage.com",
      R2_ACCESS_KEY_ID: "k",
      R2_SECRET_ACCESS_KEY: "s",
      PGBACKREST_CIPHER_PASS: "p",
      R2_BUCKET: "b",
    };
    expect(secretosFaltantes(base)).toEqual([]);
  });
});
