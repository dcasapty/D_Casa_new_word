/**
 * La revisión adversarial de la segunda puerta de Instagram (2026-11-12): cada hallazgo con su prueba, ya arreglado.
 *   I1 el eco del ENLACE del PDF no calla al bot · I2 sin saber la cuenta: 200 y sin preguntar /me en cada aviso · I3 una
 *   INSTAGRAM_ACCOUNT_ID equivocada no tira mensajes en silencio · I4 una llave que Meta rechaza es PROBLEMA en /salud de inmediato
 *   R5 sin memoria de la pegada si el Global falla · R6 dos renovaciones a la vez no se pisan · R7 sin la clave, no se verifica la
 *   URL · R8 la segunda firma solo mientras no se haya visto la buena · cortar por 1000 bytes · la suscripción en /salud.
 */
import { describe, expect, it, vi } from "vitest";
import type { Env } from "../../src/env";
import { crearMeta } from "../../src/canales/meta";
import { CLAVE_LLAVE, huella, renovarLlave, type EstadoLlave, type Llavero } from "../../src/canales/instagramLlave";
import { partirPorLargo } from "../../src/canales/tipos";
import { hmacHex } from "../../src/seguridad";
import { crearMundo } from "../helpers/mundo";
import { llaveroEnMemoria } from "../helpers/llaveroEnMemoria";

const SECRETO_FB = "secreto-de-la-app-de-facebook-0123456789";
const SECRETO_IG = "secreto-de-la-app-de-instagram-abcdef0123";
const VERIF = "verificacion-de-prueba-0123456789";
const TOKEN_IG = "IGAAtoken-de-instagram-pegado-0123456789";
const CUENTA = "17841400000000001"; // user_id (el de los webhooks)
const ID_APP = "26000000000000001"; // el `id` que /me también devuelve (app-scoped)
const CLIENTE = "1234567890123456";
const AHORA = Date.UTC(2026, 10, 12, 15, 0);
const DIA = 86_400_000;

const envBase = { META_APP_SECRET: SECRETO_FB, META_VERIFY_TOKEN: VERIF, META_PAGE_TOKEN: "token-pagina-0123456789" };
const envIg = { ...envBase, INSTAGRAM_TOKEN: TOKEN_IG, INSTAGRAM_APP_SECRET: SECRETO_IG } as unknown as Env;

const aviso = (entrada = CUENTA, recipient = entrada) => ({
  object: "instagram",
  entry: [{ id: entrada, time: 1, messaging: [{ sender: { id: CLIENTE }, recipient: { id: recipient }, timestamp: AHORA, message: { mid: "aWdf_1", text: "hola" } }] }],
});
async function firmado(cuerpo: object | string, secreto = SECRETO_IG) {
  const crudo = typeof cuerpo === "string" ? cuerpo : JSON.stringify(cuerpo);
  return new Request("https://juan.example/webhooks/instagram", { method: "POST", headers: { "x-hub-signature-256": `sha256=${await hmacHex(secreto, crudo)}` }, body: crudo });
}
const callar = () => {
  vi.spyOn(console, "warn").mockImplementation(() => {});
  vi.spyOn(console, "error").mockImplementation(() => {});
  vi.spyOn(console, "log").mockImplementation(() => {});
};
/** /me de Meta: la cuenta de D'CASA (user_id) y el id de la app. */
const meBien = () => Response.json({ user_id: CUENTA, username: "dcasapty", id: ID_APP });
const rechazo190 = () => Response.json({ error: { message: "Error validating access token: The session has been invalidated", code: 190 } }, { status: 400 });

describe("I1 · el eco del ENLACE del PDF (cuando Meta no acepta el archivo) no calla al bot", () => {
  const cotizar = { nombre: "cotizar", args: { lineas: [{ codigo: "SOFA-3P-002", cantidad: 2 }, { codigo: "CAMA-Q-001" }] } };
  for (const conPuertaNueva of [false, true]) {
    it(conPuertaNueva ? "puerta nueva (graph.instagram.com): el eco del enlace es del bot" : "por la página (como antes)", async () => {
      const m = crearMundo({ canal: "instagram", idExterno: CLIENTE, config: { canales_activos: { instagram: true } } });
      const env = { ...envBase, ...(conPuertaNueva ? { INSTAGRAM_TOKEN: TOKEN_IG, INSTAGRAM_APP_SECRET: SECRETO_IG, INSTAGRAM_ACCOUNT_ID: CUENTA } : {}) } as unknown as Env;
      const acciones: string[] = [];
      let n = 0;
      const f: typeof fetch = async (recurso, init) => {
        const url = String(recurso);
        if (url.startsWith("https://dcasa.example/")) return new Response(new Uint8Array([37, 80, 68, 70]), { headers: { "content-type": "application/pdf" } });
        if (url.includes("/me/messages")) {
          if (init?.body instanceof FormData) return Response.json({ error: { message: "(#100) Error al subir el producto", code: 100 } }, { status: 400 });
          const cuerpo = JSON.parse(String(init?.body));
          if (cuerpo.sender_action) return Response.json({ recipient_id: "x" });
          if (cuerpo.message?.attachment) return Response.json({ error: { message: "(#100) Error al subir el producto", code: 100 } }, { status: 400 });
          // Un texto: Meta entrega su ECO por el webhook antes de contestar (issue #24) y el motor lo atiende en paralelo.
          const texto: string = cuerpo.message.text;
          acciones.push(`${texto.includes("dcasa.example") ? "ENLACE" : "burbuja"}→${(await m.motor.ingest(m.entrante(undefined, { propio: true, id_mensaje: `eco_${++n}`, nombre: undefined, texto }))).accion}`);
          return Response.json({ recipient_id: "x", message_id: `m_${n}` });
        }
        return Response.json({ error: { message: "?", code: 1 } }, { status: 400 });
      };
      callar();
      const real = crearMeta({ fetch: f, dormir: async () => {}, llavero: llaveroEnMemoria(), ahora: () => m.ahora() });
      (m.deps as { env: Env }).env = env;
      (m.deps as { canal: unknown }).canal = () => real;
      m.guion([{ llamadas: [cotizar] }, { texto: "Listo, te armé la cotización. El PDF va adjunto." }]);
      await m.conversar("mándame la cotización del sofá y la cama");
      vi.restoreAllMocks();
      if (conPuertaNueva) expect(acciones).toContain("ENLACE→eco");
      expect(acciones.every((a) => a.endsWith("→eco"))).toBe(true);
      expect(m.motor.silencio()).toBe(false);
      expect(m.odoo.mensajes.filter((x) => x.autor === "vendedora")).toHaveLength(0);
    });
  }
});

describe("I2 · sin saber la cuenta: 200 (Meta no desuscribe la app) y /me no se pregunta en cada aviso", () => {
  it("si /me falla, los avisos coherentes entran con 200 y /me se pregunta UNA vez cada 10 minutos", async () => {
    callar();
    let preguntas = 0;
    let t = AHORA;
    const f: typeof fetch = async (r) => {
      if (String(r).includes("/me?")) {
        preguntas++;
        return Response.json({ error: { message: "Service unavailable", code: 2 } }, { status: 503 });
      }
      return Response.json({}, { status: 400 });
    };
    const a = crearMeta({ fetch: f, llavero: llaveroEnMemoria(), ahora: () => t });
    const resultados: [number, number][] = [];
    for (let i = 0; i < 5; i++) {
      const r = await a.recibir(await firmado(aviso()), envIg);
      resultados.push([r.respuesta.status, r.entrantes.length]);
    }
    expect(resultados).toEqual(Array(5).fill([200, 1]));
    expect(preguntas).toBe(1);
    t += 11 * 60_000;
    await a.recibir(await firmado(aviso()), envIg);
    expect(preguntas).toBe(2);
    vi.restoreAllMocks();
  });

  it("si /me no contesta nunca, el webhook no espera más de ~0,7 s (con rutas.ts queda por debajo de 5 s)", async () => {
    callar();
    const f: typeof fetch = async (r) => (String(r).includes("/me?") ? new Promise<Response>(() => {}) : Response.json({}));
    const a = crearMeta({ fetch: f, llavero: llaveroEnMemoria() });
    const inicio = Date.now();
    const r = await a.recibir(await firmado(aviso()), envIg);
    expect(Date.now() - inicio).toBeLessThan(1_500);
    expect([r.respuesta.status, r.entrantes.length]).toEqual([200, 1]);
    vi.restoreAllMocks();
  });
});

describe("I3 · INSTAGRAM_ACCOUNT_ID equivocada: no tira mensajes en silencio", () => {
  it("con el id de la app en vez del user_id: entran igual (vale también lo que dice /me)", async () => {
    const env = { ...envIg, INSTAGRAM_ACCOUNT_ID: ID_APP } as unknown as Env;
    const a = crearMeta({ fetch: async (r) => (String(r).includes("/me?") ? meBien() : Response.json({})), llavero: llaveroEnMemoria(), ahora: () => AHORA });
    const r = await a.recibir(await firmado(aviso()), env);
    expect([r.respuesta.status, r.entrantes.length]).toEqual([200, 1]);
  });

  it("si de verdad se ignoran (otra cuenta y /me no lo aclara), /salud lo dice: cuántos, cuándo y de qué cuenta, sin datos del cliente", async () => {
    callar();
    const env = { ...envIg, INSTAGRAM_ACCOUNT_ID: ID_APP } as unknown as Env;
    const a = crearMeta({ fetch: async () => Response.json({}, { status: 500 }), llavero: llaveroEnMemoria(), ahora: () => AHORA });
    for (let i = 0; i < 3; i++) expect((await a.recibir(await firmado(aviso()), env)).entrantes).toEqual([]);
    const local = await a.saludLocal!("instagram", env);
    expect(local.ignorados).toEqual({ cantidad: 3, ultimo: "2026-11-12", cuenta: "…0001" });
    expect(local.problemas).toContain("desde el 2026-11-12 se ignoran avisos de Instagram de otra cuenta (…0001), no de la de D'CASA: si esa es la de D'CASA, revisa o borra INSTAGRAM_ACCOUNT_ID");
    expect(JSON.stringify(local)).not.toContain(CLIENTE);
    vi.restoreAllMocks();
  });

  it("un valor que no es un número («@dcasapty») se ignora y /salud lo dice; los mensajes siguen entrando", async () => {
    callar();
    const env = { ...envIg, INSTAGRAM_ACCOUNT_ID: "@dcasapty" } as unknown as Env;
    const a = crearMeta({ fetch: async (r) => (String(r).includes("/me?") ? meBien() : Response.json({})), llavero: llaveroEnMemoria(), ahora: () => AHORA });
    expect((await a.recibir(await firmado(aviso()), env)).entrantes).toHaveLength(1);
    expect((await a.saludLocal!("instagram", env)).problemas).toContain("INSTAGRAM_ACCOUNT_ID no es el número de una cuenta de Instagram: se ignora (bórralo o déjalo solo con números)");
    vi.restoreAllMocks();
  });
});

describe("I4 · una llave que Meta rechaza (190) es PROBLEMA en /salud de inmediato, con un texto verdadero", () => {
  it("llave nueva inválida (con la cuenta de la llave anterior guardada): el primer cron ya lo dice; el envío falla y la renovación no lo suaviza", async () => {
    callar();
    let t = AHORA;
    const llavero = llaveroEnMemoria({ instagram_cuenta: JSON.stringify({ ids: [CUENTA], usuario: "dcasapty", semilla: "llave-anterior00", ts: AHORA - 10 * DIA }) });
    const a = crearMeta({ fetch: async () => rechazo190(), dormir: async () => {}, llavero, ahora: () => t });
    await a.mantener!(envIg); // el cron de la primera hora: /me con la llave nueva → 190
    const antes = await a.saludLocal!("instagram", envIg);
    expect(antes.problemas?.[0]).toBe(
      "Meta rechaza la llave de Instagram (INSTAGRAM_TOKEN) desde el 2026-11-12 (al preguntar la cuenta (/me): HTTP 400: Error validating access token: The session has been invalidated [190]): Juan no puede contestar por Instagram; genera otra en Meta y pégala en Cloudflare",
    );
    // Los mensajes del cliente siguen entrando a Odoo (la cuenta guardada sirve), aunque Juan no pueda contestar.
    expect((await a.recibir(await firmado(aviso()), envIg)).entrantes).toHaveLength(1);
    await expect(a.enviar("instagram", { para: CLIENTE, burbujas: ["hola"], medios: [] }, envIg)).rejects.toThrow(/190/);
    t += DIA + 3600_000;
    await a.mantener!(envIg); // la renovación también falla con 190
    const despues = await a.saludLocal!("instagram", envIg);
    expect(despues.problemas?.[0]).toMatch(/^Meta rechaza la llave de Instagram \(INSTAGRAM_TOKEN\) desde el 2026-11-12/);
    expect(despues.avisos).toBeUndefined();
    expect(JSON.stringify(despues)).not.toMatch(/sigue contestando/);
    expect(JSON.stringify(despues)).not.toContain(TOKEN_IG);
    vi.restoreAllMocks();
  });

  it("un 190 al ENVIAR también; y en cuanto un envío sale bien con la llave, el problema se borra", async () => {
    callar();
    let rechazar = true;
    const llavero = llaveroEnMemoria();
    const f: typeof fetch = async (r) => (String(r).includes("/me/messages") ? (rechazar ? rechazo190() : Response.json({ message_id: "m" })) : meBien());
    let t = AHORA;
    const a = crearMeta({ fetch: f, dormir: async () => {}, llavero, ahora: () => t });
    await expect(a.enviar("instagram", { para: CLIENTE, burbujas: ["hola"], medios: [] }, envIg)).rejects.toThrow(/190/);
    expect((await a.saludLocal!("instagram", envIg)).problemas?.[0]).toMatch(/^Meta rechaza la llave de Instagram \(INSTAGRAM_TOKEN\) desde el 2026-11-12 \(al enviar: HTTP 400: Error validating/);
    rechazar = false;
    t += 2 * 60_000;
    await a.enviar("instagram", { para: CLIENTE, burbujas: ["hola"], medios: [] }, envIg);
    expect((await a.saludLocal!("instagram", envIg)).problemas?.filter((p) => p.startsWith("Meta rechaza"))).toEqual([]);
    vi.restoreAllMocks();
  });
});

describe("R5 · si leer el Global falla una vez, la pegada se usa solo esa vez (no se recuerda)", () => {
  it("el siguiente envío ya usa la renovada", async () => {
    callar();
    const estado: EstadoLlave = { semilla: huella(TOKEN_IG), vistaEn: AHORA - 70 * DIA, llave: "IGAArenovada-9876543210", vence: AHORA + 50 * DIA, renovadaEn: AHORA - 10 * DIA };
    const base = llaveroEnMemoria({ [CLAVE_LLAVE]: JSON.stringify(estado) });
    let fallar = 1;
    const llavero: Llavero = { leer: async (e, k) => (fallar-- > 0 ? Promise.reject(new Error("DO reiniciándose")) : base.leer(e, k)), cambiarSi: base.cambiarSi };
    const usadas: string[] = [];
    const f: typeof fetch = async (_r, init) => {
      usadas.push(String((init?.headers as Record<string, string>).authorization));
      return Response.json({ message_id: "m" });
    };
    let t = AHORA;
    const a = crearMeta({ fetch: f, dormir: async () => {}, llavero, ahora: () => t });
    await a.enviar("instagram", { para: CLIENTE, burbujas: ["uno"], medios: [] }, envIg);
    t += 30_000;
    await a.enviar("instagram", { para: CLIENTE, burbujas: ["dos"], medios: [] }, envIg);
    expect(usadas).toEqual([`Bearer ${TOKEN_IG}`, "Bearer IGAArenovada-9876543210"]);
    vi.restoreAllMocks();
  });
});

describe("R6 · dos renovaciones a la vez: una reserva el intento, la otra se retira, nada se pisa", () => {
  it("una sola llamada a Meta y la renovada queda guardada", async () => {
    callar();
    const llavero = llaveroEnMemoria({ [CLAVE_LLAVE]: JSON.stringify({ semilla: huella(TOKEN_IG), vistaEn: AHORA - 2 * DIA }) });
    let n = 0;
    const f: typeof fetch = async () => {
      n++;
      await new Promise((r) => setTimeout(r, 5));
      return Response.json({ access_token: "IGAAnueva-0123456789", expires_in: 5_184_000 });
    };
    const deps = { fetch: f, llavero, ahora: () => AHORA };
    const r = await Promise.all([renovarLlave(envIg, deps), renovarLlave(envIg, deps)]);
    expect(r.sort()).toEqual(["no_toca", "renovada"]);
    expect(n).toBe(1);
    const final = JSON.parse(llavero.datos.get(CLAVE_LLAVE)!) as EstadoLlave;
    expect(final.llave).toBe("IGAAnueva-0123456789");
    expect(final.error).toBeUndefined();
    vi.restoreAllMocks();
  });

  it("si la dueña pega otra llave mientras se renueva, el resultado viejo se descarta (manda la nueva)", async () => {
    callar();
    const llavero = llaveroEnMemoria({ [CLAVE_LLAVE]: JSON.stringify({ semilla: huella(TOKEN_IG), vistaEn: AHORA - 2 * DIA }) });
    const otra = "IGAAotra-llave-pegada-0000000000";
    const f: typeof fetch = async () => {
      // Mientras Meta contesta, el cron de otra hora ya vio la llave nueva.
      await renovarLlave({ ...envIg, INSTAGRAM_TOKEN: otra } as Env, { fetch: f, llavero, ahora: () => AHORA });
      return Response.json({ access_token: "IGAAde-la-vieja-0123456789", expires_in: 5_184_000 });
    };
    await renovarLlave(envIg, { fetch: f, llavero, ahora: () => AHORA });
    expect(JSON.parse(llavero.datos.get(CLAVE_LLAVE)!)).toEqual({ semilla: huella(otra), vistaEn: AHORA });
    vi.restoreAllMocks();
  });
});

describe("R7 · la verificación GET de /webhooks/instagram exige la puerta lista", () => {
  it("sin INSTAGRAM_APP_SECRET: 403 (Meta no da la URL por buena); con ella, el reto", async () => {
    const a = crearMeta({ fetch: async () => Response.json({}) });
    const url = `https://juan.example/webhooks/instagram?hub.mode=subscribe&hub.verify_token=${VERIF}&hub.challenge=42`;
    expect((await a.recibir(new Request(url), envBase as unknown as Env)).respuesta.status).toBe(403);
    expect((await a.recibir(new Request(url), { ...envBase, INSTAGRAM_TOKEN: TOKEN_IG } as unknown as Env)).respuesta.status).toBe(403);
    const ok = await a.recibir(new Request(url), envIg);
    expect([ok.respuesta.status, await ok.respuesta.text()]).toEqual([200, "42"]);
  });
});

describe("R8 · la segunda firma (META_APP_SECRET) solo mientras no llegó ninguno firmado con la de Instagram", () => {
  it("después del primer aviso bueno, una firma basura cuesta UN solo HMAC (y la de Facebook ya no se acepta)", async () => {
    const a = crearMeta({ fetch: async (r) => (String(r).includes("/me?") ? meBien() : Response.json({})), llavero: llaveroEnMemoria(), ahora: () => AHORA });
    // Un proceso nuevo: hasta saber cuál usa Meta, una firma inválida cuesta dos HMAC (documentado; ~ms por MB).
    const espia = vi.spyOn(crypto.subtle, "sign");
    const basura = () => new Request("https://juan.example/webhooks/instagram", { method: "POST", headers: { "x-hub-signature-256": `sha256=${"0".repeat(64)}` }, body: "x".repeat(10_000) });
    expect((await a.recibir(basura(), envIg)).respuesta.status).toBe(401);
    expect(espia).toHaveBeenCalledTimes(2);
    expect((await a.recibir(await firmado(aviso()), envIg)).respuesta.status).toBe(200);
    espia.mockClear();
    expect((await a.recibir(basura(), envIg)).respuesta.status).toBe(401);
    expect(espia).toHaveBeenCalledTimes(1);
    expect((await a.recibir(await firmado(aviso(), SECRETO_FB), envIg)).respuesta.status).toBe(401);
    espia.mockRestore();
  });
});

describe("el texto se corta por 1000 bytes UTF-8 (lo que dice Meta), no por letras", () => {
  it("con tildes y emojis cada trozo cabe en 1000 bytes y ningún emoji queda partido; sin bytes, igual que antes", () => {
    const largo = "Señora, ñandú y café ☕ 🛋️ ".repeat(80);
    const trozos = partirPorLargo(largo, 1000, 1000);
    expect(trozos.length).toBeGreaterThan(1);
    for (const t of trozos) {
      expect(new TextEncoder().encode(t).length).toBeLessThanOrEqual(1000);
      expect(t).not.toMatch(/[\ud800-\udbff](?![\udc00-\udfff])|(?<![\ud800-\udbff])[\udc00-\udfff]/);
    }
    expect(trozos.join(" ").replace(/\s+/g, " ").trim()).toBe(largo.replace(/\s+/g, " ").trim());
    expect(partirPorLargo(largo, 950)).toEqual(partirPorLargo(largo, 950, undefined));
  });

  it("por esta puerta el motor lo pide así (capacidades)", () => {
    expect(crearMeta().capacidades("instagram", envIg).maxBytesTexto).toBe(1000);
    expect(crearMeta().capacidades("instagram", envBase as unknown as Env).maxBytesTexto).toBeUndefined();
  });
});

describe("la suscripción de la app a los mensajes, en /salud (si Meta deja consultarla)", () => {
  it("sin «messages» en /me/subscribed_apps: problema con qué encender; con «messages»: ok; si la consulta no se entiende, nada", async () => {
    callar();
    let respuesta: () => Response = () => Response.json({ data: [] });
    const f: typeof fetch = async (r) => {
      const u = String(r);
      if (u.includes("/me/subscribed_apps")) return respuesta();
      if (u.includes("/me?")) return meBien();
      return Response.json({ error: { message: "x", code: 1 } }, { status: 400 });
    };
    const a = crearMeta({ fetch: f, llavero: llaveroEnMemoria(), ahora: () => AHORA });
    await a.mantener!(envIg);
    let s = await a.saludLocal!("instagram", envIg);
    expect(s.suscripcion).toBe("no");
    expect(s.problemas).toContain("Meta no tiene la app suscrita a los mensajes de la cuenta de Instagram (sin «messages»): en Meta, al lado de @dcasapty, enciende «Webhook subscription»");
    respuesta = () => Response.json({ data: [{ subscribed_fields: ["messages", "message_echoes"] }] });
    await a.mantener!(envIg);
    s = await a.saludLocal!("instagram", envIg);
    expect(s.suscripcion).toBe("ok");
    expect(s.problemas).toBeUndefined();
    const otra = crearMeta({ fetch: async (r) => (String(r).includes("/me?") ? meBien() : Response.json({ error: { message: "Unsupported get request", code: 100 } }, { status: 400 })), llavero: llaveroEnMemoria(), ahora: () => AHORA });
    await otra.mantener!(envIg);
    expect((await otra.saludLocal!("instagram", envIg)).suscripcion).toBeUndefined();
    vi.restoreAllMocks();
  });
});
