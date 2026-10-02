import { describe, expect, it, vi } from "vitest";

import {
  CRON_HORARIO,
  CRON_RESPALDO,
  PAUSA_REARRANQUE_MS,
  autorizado,
  colaDeSalida,
  debeRearrancar,
  debeRegenerarEnCron,
  handleRequest,
  mismoSecreto,
  politicaDeSueno,
  respuestaArrancando,
  secretosFaltantes,
  servirConArranque,
  tareaDelCron,
  variablesDelContenedor,
  type ResultadoRespaldo,
  type SaludContenedor,
} from "../src/handler";
import { route } from "../src/routing";
// Vite entrega el archivo como texto (ver test/raw.d.ts).
import wranglerJsonc from "../wrangler.jsonc?raw";

const TOKEN = "t".repeat(40);
const SECRETOS = {
  ADMIN_PASSWORD: "clave-admin",
  R2_ENDPOINT: "https://cuenta.r2.cloudflarestorage.com",
  R2_BUCKET: "dcasa-respaldos",
  R2_ACCESS_KEY_ID: "id",
  R2_SECRET_ACCESS_KEY: "secreto",
  PGBACKREST_CIPHER_PASS: "cifrado",
};

/** Lee wrangler.jsonc quitando comentarios (respeta las cadenas, p. ej. URLs con //). */
function leerWrangler(): Record<string, any> {
  const texto = wranglerJsonc;
  let salida = "";
  let enCadena = false;
  for (let i = 0; i < texto.length; i++) {
    const c = texto[i];
    if (enCadena) {
      salida += c;
      if (c === "\\") salida += texto[++i];
      else if (c === '"') enCadena = false;
    } else if (c === '"') {
      enCadena = true;
      salida += c;
    } else if (c === "/" && texto[i + 1] === "/") {
      while (i < texto.length && texto[i] !== "\n") i++;
      salida += "\n";
    } else {
      salida += c;
    }
  }
  return JSON.parse(salida.replace(/,(\s*[}\]])/g, "$1"));
}

describe("503 amable mientras Odoo arranca o restaura (I-07)", () => {
  it("al navegador le da una página que se recarga sola, con Retry-After y sin caché", async () => {
    const res = respuestaArrancando(new Request("https://dcasapty.com/shop", { headers: { Accept: "text/html" } }));
    expect(res.status).toBe(503);
    expect(res.headers.get("Retry-After")).toBe("15");
    expect(res.headers.get("Cache-Control")).toBe("no-store");
    expect(res.headers.get("X-Content-Type-Options")).toBe("nosniff");
    const html = await res.text();
    expect(html).toContain('http-equiv="refresh" content="15"');
    expect(html).toContain("Escríbenos por WhatsApp");
    expect(html).not.toMatch(/FED00F/i); // el amarillo nunca sobre blanco
    expect(html).not.toMatch(/gradient/i);
  });

  it("a Brian, Telegram o un POST le da texto plano", async () => {
    const res = respuestaArrancando(new Request("https://dcasapty.com/brian/mcp", { method: "POST", body: "{}" }));
    expect(res.status).toBe(503);
    expect(res.headers.get("Content-Type")).toContain("text/plain");
    expect(res.headers.get("Retry-After")).toBe("15");
  });

  it("si Odoo está listo reenvía sin arrancar nada", async () => {
    const arrancar = vi.fn(async () => {});
    const res = await servirConArranque(new Request("https://dcasapty.com/"), {
      listo: async () => true,
      arrancar,
      reenviar: async () => new Response("odoo"),
    });
    expect(await res.text()).toBe("odoo");
    expect(arrancar).not.toHaveBeenCalled();
  });

  it("si arranca rápido, la visita espera y recibe la página", async () => {
    const res = await servirConArranque(new Request("https://dcasapty.com/"), {
      listo: async () => false,
      arrancar: async () => {},
      reenviar: async () => new Response("odoo"),
    });
    expect(await res.text()).toBe("odoo");
  });

  it("si la restauración tarda, responde 503 sin esperar de más y sin reenviar", async () => {
    const reenviar = vi.fn();
    const arrancar = vi.fn(() => new Promise<void>(() => {})); // restaurando desde R2…
    const res = await servirConArranque(
      new Request("https://dcasapty.com/", { headers: { Accept: "text/html" } }),
      { listo: async () => false, arrancar, reenviar, esperar: async () => {} },
    );
    expect(res.status).toBe(503);
    expect(res.headers.get("Retry-After")).toBe("15");
    expect(arrancar).toHaveBeenCalledOnce();
    expect(reenviar).not.toHaveBeenCalled();
  });

  it("si el arranque falla, también es 503 amable (no 500)", async () => {
    const res = await servirConArranque(new Request("https://dcasapty.com/"), {
      listo: async () => false,
      arrancar: async () => {
        throw new Error("pgbackrest restore falló");
      },
      reenviar: vi.fn(),
      esperar: () => new Promise(() => {}),
    });
    expect(res.status).toBe(503);
  });

  it("sin secretos de R2 no enciende el contenedor (no crearía una base vacía)", async () => {
    const arrancar = vi.fn(async () => {});
    const errores = vi.spyOn(console, "error").mockImplementation(() => {});
    const res = await servirConArranque(new Request("https://dcasapty.com/"), {
      listo: async () => false,
      arrancar,
      reenviar: vi.fn(),
      faltantes: () => secretosFaltantes({ ADMIN_PASSWORD: "x" }),
    });
    errores.mockRestore();
    expect(res.status).toBe(503);
    expect(res.headers.get("Retry-After")).toBe("60");
    expect(arrancar).not.toHaveBeenCalled();
  });

  it("si el Durable Object falla al reenviar, el borde responde 503 amable", async () => {
    const errores = vi.spyOn(console, "error").mockImplementation(() => {});
    const res = await handleRequest(new Request("https://dcasapty.com/shop"), {
      forward: async () => {
        throw new Error("Durable Object reset because its code was updated");
      },
    });
    errores.mockRestore();
    expect(res.status).toBe(503);
    expect(res.headers.get("Retry-After")).toBe("15");
  });
});

describe("/__edge/health combinado con la salud de Odoo", () => {
  const pedir = (salud: () => Promise<SaludContenedor>) => {
    const forward = vi.fn();
    return { forward, res: handleRequest(new Request("https://dcasapty.com/__edge/health"), { forward, salud }) };
  };

  it("200 solo si /dcasa/salud responde bien", async () => {
    const { forward, res } = pedir(async () => ({ contenedor: "healthy", odoo: { status: 200, cuerpo: '{"base":"ok"}' } }));
    const r = await res;
    expect(r.status).toBe(200);
    expect(r.headers.get("Cache-Control")).toBe("no-store");
    expect(await r.json()).toMatchObject({ borde: "ok", odoo: "ok", contenedor: "healthy", salud_http: 200 });
    expect(forward).not.toHaveBeenCalled();
  });

  it("503 si la base falla aunque Odoo responda", async () => {
    const r = await pedir(async () => ({ contenedor: "healthy", odoo: { status: 503 } })).res;
    expect(r.status).toBe(503);
    expect(await r.json()).toMatchObject({ odoo: "error", salud_http: 503 });
  });

  it("apagado o arrancando: lo dice sin despertarlo", async () => {
    const apagado = await pedir(async () => ({ contenedor: "stopped" })).res;
    expect(apagado.status).toBe(503);
    expect(apagado.headers.get("Retry-After")).toBe("15");
    expect(await apagado.json()).toMatchObject({ odoo: "detenido" });
    const arrancando = await pedir(async () => ({ contenedor: "running" })).res;
    expect(await arrancando.json()).toMatchObject({ odoo: "arrancando" });
  });

  it("timeout de /dcasa/salud o Durable Object caído = error", async () => {
    const timeout = await pedir(async () => ({ contenedor: "healthy", odoo: { error: "TimeoutError" } })).res;
    expect(await timeout.json()).toMatchObject({ odoo: "error", detalle: "TimeoutError" });
    const caido = await pedir(async () => {
      throw new Error("DO caído");
    }).res;
    expect(caido.status).toBe(503);
  });

  it("avisa qué secretos faltan", async () => {
    const r = await pedir(async () => ({ contenedor: "stopped", faltan: ["R2_ENDPOINT"] })).res;
    expect(await r.json()).toMatchObject({ odoo: "sin_configurar", faltan: ["R2_ENDPOINT"] });
  });
});

describe("respaldo diario (cron) y a mano (token)", () => {
  const ok: ResultadoRespaldo = { estado: "ok", codigo: 0, duracionMs: 1000 };
  const pedir = (init: RequestInit, token: string | undefined, resultado = ok) => {
    const respaldar = vi.fn(async () => resultado);
    const forward = vi.fn();
    const res = handleRequest(new Request("https://dcasapty.com/__edge/respaldo", init), {
      forward,
      respaldo: { token, respaldar },
    });
    return { res, respaldar, forward };
  };
  const conToken = (t = TOKEN): RequestInit => ({ method: "POST", headers: { Authorization: `Bearer ${t}` } });

  it("el cron diario de madrugada lanza el respaldo; el horario solo despierta", () => {
    expect(tareaDelCron(CRON_RESPALDO)).toBe("respaldo");
    expect(tareaDelCron(CRON_HORARIO)).toBe("despertar");
    expect(tareaDelCron("*/10 * * * *")).toBe("despertar");
    // 08:17 UTC = 03:17 en Panamá (UTC-5, sin horario de verano).
    expect(CRON_RESPALDO).toBe("17 8 * * *");
  });

  it("con el token correcto respalda y devuelve el resultado", async () => {
    const { res, respaldar, forward } = pedir(conToken(), TOKEN);
    const r = await res;
    expect(r.status).toBe(200);
    expect(await r.json()).toEqual(ok);
    expect(respaldar).toHaveBeenCalledOnce();
    expect(forward).not.toHaveBeenCalled();
  });

  it("token equivocado o ausente: 401 sin respaldar", async () => {
    for (const init of [conToken("x".repeat(40)), { method: "POST" }]) {
      const { res, respaldar } = pedir(init, TOKEN);
      expect((await res).status).toBe(401);
      expect(respaldar).not.toHaveBeenCalled();
    }
  });

  it("sin RESPALDO_TOKEN (o uno corto) la ruta no existe y nunca llega a Odoo", async () => {
    for (const token of [undefined, "corto"]) {
      const { res, respaldar, forward } = pedir(conToken("corto"), token);
      expect((await res).status).toBe(404);
      expect(respaldar).not.toHaveBeenCalled();
      expect(forward).not.toHaveBeenCalled();
    }
  });

  it("solo POST", async () => {
    const { res } = pedir({ method: "GET", headers: { Authorization: `Bearer ${TOKEN}` } }, TOKEN);
    expect((await res).status).toBe(405);
  });

  it("fallo → 500, en curso → 409, Odoo apagado → 503", async () => {
    expect((await pedir(conToken(), TOKEN, { estado: "fallo", codigo: 1 }).res).status).toBe(500);
    expect((await pedir(conToken(), TOKEN, { estado: "en_curso" }).res).status).toBe(409);
    expect((await pedir(conToken(), TOKEN, { estado: "omitido" }).res).status).toBe(503);
  });

  it("autorizado compara en tiempo constante y exige Bearer", () => {
    expect(mismoSecreto("abc", "abc")).toBe(true);
    expect(mismoSecreto("abc", "abd")).toBe(false);
    expect(mismoSecreto("abc", "abcd")).toBe(false);
    expect(autorizado(`bearer ${TOKEN}`, TOKEN)).toBe(true);
    expect(autorizado(TOKEN, TOKEN)).toBe(false);
    expect(autorizado(`Bearer ${TOKEN}`, undefined)).toBe(false);
  });

  it("la salida del script se recorta por el final", () => {
    expect(colaDeSalida("corto")).toBe("corto");
    const largo = "a".repeat(3000) + "FIN";
    expect(colaDeSalida(largo).endsWith("FIN")).toBe(true);
    expect(colaDeSalida(largo).length).toBe(2001);
  });

  it("/__edge/* es del borde: rutas desconocidas no van a Odoo", async () => {
    expect(route(new URL("https://dcasapty.com/__edge/respaldo"), "POST")).toEqual({ kind: "respaldo" });
    expect(route(new URL("https://dcasapty.com/__edge/otra"), "GET")).toEqual({ kind: "blocked" });
    expect(route(new URL("https://dcasapty.com/%5F%5Fedge/otra"), "GET")).toEqual({ kind: "blocked" });
  });
});

describe("contenedor único con PostgreSQL local", () => {
  it("pasa R2 y cifrado al contenedor, y ya no pasa nada de Neon", () => {
    const vars = variablesDelContenedor({
      ...SECRETOS,
      DB_HOST: "algo.neon.tech",
      DB_PASSWORD: "x",
      RESPALDO_TOKEN: TOKEN,
      DCASA_PIN_PEPPER: "pimienta",
      BRIAN_API_KEY: "",
    });
    expect(vars).toMatchObject({ ...SECRETOS, DCASA_PIN_PEPPER: "pimienta", APP_VERSION: "dev", DCASA_ENTORNO: "produccion" });
    for (const nombre of ["DB_HOST", "DB_PASSWORD", "DB_SSLMODE", "RESPALDO_TOKEN", "BRIAN_API_KEY"]) {
      expect(vars).not.toHaveProperty(nombre);
    }
    expect(variablesDelContenedor({ DCASA_ENTORNO: "staging" }).DCASA_ENTORNO).toBe("staging");
    expect(variablesDelContenedor({ DCASA_ADJUNTOS: "db" }).DCASA_ADJUNTOS).toBe("db");
    expect(variablesDelContenedor({})).not.toHaveProperty("DCASA_ADJUNTOS");
    expect(variablesDelContenedor({ DCASA_STOCK_PRUEBA: "10" }).DCASA_STOCK_PRUEBA).toBe("10");
    expect(
      variablesDelContenedor({ DCASA_BLACK_WEEKEND: "1", DCASA_BLACK_WEEKEND_INICIO: "2026-10-05", DCASA_BLACK_WEEKEND_FIN: "" }),
    ).toMatchObject({ DCASA_BLACK_WEEKEND: "1", DCASA_BLACK_WEEKEND_INICIO: "2026-10-05" });
    expect(variablesDelContenedor({ DCASA_BLACK_WEEKEND_FIN: "" })).not.toHaveProperty("DCASA_BLACK_WEEKEND_FIN");
  });

  it("detecta los secretos que faltan para arrancar", () => {
    expect(secretosFaltantes(SECRETOS)).toEqual([]);
    expect(secretosFaltantes({ ...SECRETOS, R2_SECRET_ACCESS_KEY: " ", R2_BUCKET: undefined })).toEqual([
      "R2_SECRET_ACCESS_KEY",
      "R2_BUCKET",
    ]);
  });

  it("24/7 por defecto; staging puede dormir; un valor raro no apaga la tienda", () => {
    expect(politicaDeSueno(undefined)).toEqual({ siempreEncendido: true, sleepAfter: "24h" });
    expect(politicaDeSueno("")).toEqual({ siempreEncendido: true, sleepAfter: "24h" });
    expect(politicaDeSueno("nunca").siempreEncendido).toBe(true);
    expect(politicaDeSueno("1h")).toEqual({ siempreEncendido: false, sleepAfter: "1h" });
    const aviso = vi.spyOn(console, "warn").mockImplementation(() => {});
    expect(politicaDeSueno("pronto").siempreEncendido).toBe(true);
    expect(politicaDeSueno("0m").siempreEncendido).toBe(true);
    aviso.mockRestore();
  });

  it("tras una parada rearranca solo en 24/7 y sin bucles", () => {
    const ahora = 1_000_000_000;
    expect(debeRearrancar(true, ahora)).toBe(true);
    expect(debeRearrancar(true, ahora, ahora - 60_000)).toBe(false);
    expect(debeRearrancar(true, ahora, ahora - PAUSA_REARRANQUE_MS)).toBe(true);
    expect(debeRearrancar(false, ahora)).toBe(false);
  });
});

describe("wrangler.jsonc (producción y staging)", () => {
  const config = leerWrangler();
  const contenedor = (c: Record<string, any>) => c.containers[0];

  it("producción: basic, singleton, cerca de Panamá, política default", () => {
    const c = contenedor(config);
    expect(c.instance_type).toBe("basic");
    expect(c.max_instances).toBe(1);
    expect(c.constraints.regions).toEqual(["ENAM"]);
    expect(c.scheduling_policy).toBe("default");
  });

  it("crons = los que entiende el Worker", () => {
    expect(config.triggers.crons).toEqual([CRON_HORARIO, CRON_RESPALDO]);
    expect(config.env.staging.triggers.crons).toEqual([CRON_HORARIO, CRON_RESPALDO]);
  });

  it("sin Neon: la base es local", () => {
    const texto = JSON.stringify(config);
    expect(texto).not.toMatch(/neon/i);
    for (const vars of [config.vars, config.env.staging.vars]) {
      for (const nombre of ["DB_HOST", "DB_PORT", "DB_USER", "DB_SSLMODE"]) expect(vars).not.toHaveProperty(nombre);
    }
  });

  it("producción 24/7", () => {
    expect(politicaDeSueno(config.vars.ODOO_DORMIR_TRAS).siempreEncendido).toBe(true);
    expect(config.vars.DCASA_ENTORNO).toBe("produccion");
    expect(config.vars.DCASA_STOCK_PRUEBA).toBe("0");
    // Black Weekend en producción: solo dentro de la ventana de la dueña (hora de Panamá).
    expect(config.vars.DCASA_BLACK_WEEKEND).toBe("0");
    expect(config.vars.DCASA_BLACK_WEEKEND_INICIO).toBe("2026-10-02");
    expect(config.vars.DCASA_BLACK_WEEKEND_FIN).toBe("2026-10-11");
  });

  it("staging: otro Worker, otra instancia y otro bucket de R2", () => {
    const staging = config.env.staging;
    expect(staging.name).not.toBe(config.name);
    expect(staging.vars.R2_BUCKET).not.toBe(config.vars.R2_BUCKET);
    expect(staging.vars.DCASA_ENTORNO).toBe("staging");
    expect(staging.vars.DCASA_STOCK_PRUEBA).toBe("10");
    expect(staging.vars.DCASA_BLACK_WEEKEND).toBe("1");
    expect(staging.vars.CANONICAL_HOST).not.toBe(config.vars.CANONICAL_HOST);
    const c = contenedor(staging);
    expect(c.instance_type).toBe("basic");
    expect(c.max_instances).toBe(1);
    expect(staging.durable_objects.bindings[0].name).toBe("ODOO");
    expect(staging.migrations).toEqual(config.migrations);
    expect(staging).not.toHaveProperty("routes");
  });

  it("tienda estática: KV por entorno; apagada en producción y encendida en staging", () => {
    expect(config.kv_namespaces).toEqual([{ binding: "TIENDA" }]);
    expect(config.env.staging.kv_namespaces).toEqual([{ binding: "TIENDA" }]);
    expect(config.vars.TIENDA_ESTATICA).toBe("off");
    expect(config.env.staging.vars.TIENDA_ESTATICA).toBe("off");
  });

  it("el secreto de la tienda llega al contenedor (Odoo lo usa para el feed y el aviso)", () => {
    const vars = variablesDelContenedor({ TIENDA_FEED_TOKEN: TOKEN, TIENDA_AVISO_URL: "https://x/__edge/tienda/regenerar" });
    expect(vars.TIENDA_FEED_TOKEN).toBe(TOKEN);
    expect(vars.TIENDA_AVISO_URL).toBe("https://x/__edge/tienda/regenerar");
  });

  it("el cron horario regenera la tienda solo con Odoo ya encendido", () => {
    expect(debeRegenerarEnCron("encendido", true, TOKEN)).toBe(true);
    expect(debeRegenerarEnCron("dormido", true, TOKEN)).toBe(false);
    expect(debeRegenerarEnCron("despertado", true, TOKEN)).toBe(false);
    expect(debeRegenerarEnCron("encendido", false, TOKEN)).toBe(false);
    expect(debeRegenerarEnCron("encendido", true, "corto")).toBe(false);
  });

  it("staging duerme: su cron horario no lo despierta (costos-y-limpieza §2.6)", () => {
    expect(politicaDeSueno(config.env.staging.vars.ODOO_DORMIR_TRAS).siempreEncendido).toBe(false);
  });
});
