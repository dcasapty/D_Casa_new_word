/**
 * La llave de Instagram por inicio de sesión de Instagram: la dueña la pega una vez (INSTAGRAM_TOKEN, 60 días) y Juan la renueva
 * sola (`refresh_access_token`) antes de que venza, guardando la vigente en el Durable Object `Global`. Cuándo sí, cuándo no, qué
 * pasa si falla, y lo que dice /salud (fechas, nunca la llave).
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Env } from "../../src/env";
import { crearMeta } from "../../src/canales/meta";
import {
  CLAVE_CUENTA,
  CLAVE_LLAVE,
  huella,
  motivoDeMeta,
  renovarLlave,
  tocaRenovar,
  type EstadoLlave,
  type Llavero,
} from "../../src/canales/instagramLlave";

const DIA = 86_400_000;
const T0 = Date.UTC(2026, 10, 13, 15, 23); // 13 nov 2026, 10:23 en Panamá
const TOKEN_IG = "IGAAtoken-de-instagram-pegado-0123456789";
const SECRETO_IG = "secreto-de-la-app-de-instagram-abcdef0123";
const env = { INSTAGRAM_TOKEN: TOKEN_IG, INSTAGRAM_APP_SECRET: SECRETO_IG, META_VERIFY_TOKEN: "verificacion-0123456789" } as unknown as Env;

function llaveroEnMemoria(inicial: Record<string, string> = {}): Llavero & { datos: Map<string, string> } {
  const datos = new Map(Object.entries(inicial));
  return { datos, leer: async (_e, c) => datos.get(c) ?? null, guardar: async (_e, c, v) => void datos.set(c, v) };
}

/** Meta de mentira: la renovación devuelve una llave nueva numerada (o lo que diga `respuesta`). */
function metaFalso(respuesta?: (url: URL, n: number) => Response | undefined) {
  const pedidas: URL[] = [];
  /** La llave con que salió cada envío (cabecera Authorization). */
  const conLlave: string[] = [];
  let reloj = T0;
  const llavero = llaveroEnMemoria();
  const f: typeof fetch = async (recurso, init) => {
    const url = new URL(String(recurso));
    pedidas.push(url);
    if (url.pathname.endsWith("/me/messages")) conLlave.push(String((init?.headers as Record<string, string>)?.authorization ?? "").replace(/^Bearer /, ""));
    const propia = respuesta?.(url, pedidas.length - 1);
    if (propia) return propia;
    if (url.pathname === "/refresh_access_token") return Response.json({ access_token: `IGAArenovada-${pedidas.length}-abcdefghij`, token_type: "bearer", expires_in: 5_184_000 });
    if (url.pathname.endsWith("/me")) return Response.json({ user_id: "17841400000000001", username: "dcasapty", id: "26000000000000001" });
    if (url.pathname.endsWith("/me/messages")) return Response.json({ message_id: "m" });
    return Response.json({ error: { message: "?" } }, { status: 400 });
  };
  const deps = { fetch: f, llavero, ahora: () => reloj };
  const adaptador = crearMeta({ fetch: f, dormir: async () => {}, llavero, ahora: () => reloj });
  return {
    pedidas,
    conLlave,
    llavero,
    deps,
    adaptador,
    pasar: (ms: number) => void (reloj += ms),
    ahora: () => reloj,
    estado: () => JSON.parse(llavero.datos.get(CLAVE_LLAVE) ?? "null") as EstadoLlave | null,
    renovaciones: () => pedidas.filter((u) => u.pathname === "/refresh_access_token"),
  };
}

afterEach(() => vi.restoreAllMocks());

describe("cuándo toca renovar", () => {
  const base: EstadoLlave = { semilla: "x", vistaEn: T0 };
  it("una llave pegada de la que no se sabe cuándo vence: sí, en cuanto tiene 24 h (la renovación dice cuándo vence)", () => {
    expect(tocaRenovar(base, T0 + 23 * 3600_000)).toBe(false);
    expect(tocaRenovar(base, T0 + DIA)).toBe(true);
  });
  it("con fecha de Meta: solo cuando le quedan menos de 20 días, y nunca ya vencida", () => {
    const renovada: EstadoLlave = { ...base, renovadaEn: T0, vence: T0 + 60 * DIA };
    expect(tocaRenovar(renovada, T0 + 39 * DIA)).toBe(false); // le quedan 21
    expect(tocaRenovar(renovada, T0 + 41 * DIA)).toBe(true); // le quedan 19
    expect(tocaRenovar(renovada, T0 + 60 * DIA)).toBe(false); // venció: Meta ya no la renueva
  });
  it("nunca más de un intento al día (salga bien o mal)", () => {
    const intentada: EstadoLlave = { ...base, vence: T0 + 10 * DIA, renovadaEn: T0 - 50 * DIA, intentoEn: T0, error: "x" };
    expect(tocaRenovar(intentada, T0 + 23 * 3600_000)).toBe(false);
    expect(tocaRenovar(intentada, T0 + DIA)).toBe(true);
  });
});

describe("la renovación (el cron)", () => {
  it("sin INSTAGRAM_TOKEN no hace nada", async () => {
    const m = metaFalso();
    expect(await renovarLlave({} as Env, m.deps)).toBe("sin_llave");
    expect(m.pedidas).toEqual([]);
    expect(m.llavero.datos.size).toBe(0);
  });

  it("la primera vez solo anota desde cuándo la conoce; al día siguiente la renueva y guarda la nueva con su vencimiento", async () => {
    const m = metaFalso();
    expect(await renovarLlave(env, m.deps)).toBe("no_toca");
    expect(m.renovaciones()).toEqual([]);
    expect(m.estado()).toEqual({ semilla: huella(TOKEN_IG), vistaEn: T0 });
    m.pasar(2 * 3600_000);
    expect(await renovarLlave(env, m.deps)).toBe("no_toca"); // cada hora el cron vuelve: todavía no tiene 24 h
    m.pasar(DIA);
    expect(await renovarLlave(env, m.deps)).toBe("renovada");
    const [pedida] = m.renovaciones();
    expect(pedida.origin).toBe("https://graph.instagram.com");
    expect(pedida.searchParams.get("grant_type")).toBe("ig_refresh_token");
    expect(pedida.searchParams.get("access_token")).toBe(TOKEN_IG);
    const e = m.estado()!;
    expect(e.llave).toMatch(/^IGAArenovada-/);
    expect(e.vence).toBe(m.ahora() + 5_184_000_000);
    expect(e.renovadaEn).toBe(m.ahora());
    expect(e.error).toBeUndefined();
  });

  it("después usa siempre la más nueva: la siguiente renovación (con < 20 días) se pide con la RENOVADA", async () => {
    const m = metaFalso();
    await renovarLlave(env, m.deps);
    m.pasar(DIA);
    await renovarLlave(env, m.deps);
    const primera = m.estado()!.llave!;
    m.pasar(30 * DIA);
    expect(await renovarLlave(env, m.deps)).toBe("no_toca"); // le quedan 30
    m.pasar(11 * DIA);
    expect(await renovarLlave(env, m.deps)).toBe("renovada"); // le quedan 19
    expect(m.renovaciones().at(-1)!.searchParams.get("access_token")).toBe(primera);
    expect(m.estado()!.llave).not.toBe(primera);
    // Y el envío usa la última (la de memoria se olvida al renovar desde el cron).
    await m.adaptador.mantener!(env);
    await m.adaptador.enviar("instagram", { para: "1234567890123456", burbujas: ["hola"], medios: [] }, env);
    expect(m.conLlave).toEqual([m.estado()!.llave]);
  });

  it("si Meta falla: anota el motivo (sin la llave), no reintenta el mismo día, y al día siguiente sí", async () => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    let fallar = true;
    const m = metaFalso((url) =>
      url.pathname === "/refresh_access_token" && fallar ? Response.json({ error: { message: `Error validating access token for ${TOKEN_IG}`, code: 190 } }, { status: 400 }) : undefined,
    );
    await renovarLlave(env, m.deps);
    m.pasar(DIA);
    expect(await renovarLlave(env, m.deps)).toBe("fallo");
    const e = m.estado()!;
    expect(e.error).toBe("HTTP 400: Error validating access token for … [190]");
    expect(e.intentoEn).toBe(m.ahora());
    expect(e.llave).toBeUndefined(); // se sigue usando la pegada
    expect(JSON.stringify(e)).not.toContain(TOKEN_IG);
    for (let h = 1; h < 24; h++) {
      m.pasar(3600_000);
      expect(await renovarLlave(env, m.deps)).toBe("no_toca");
    }
    expect(m.renovaciones()).toHaveLength(1);
    fallar = false;
    m.pasar(3600_000);
    expect(await renovarLlave(env, m.deps)).toBe("renovada");
    expect(m.estado()!.error).toBeUndefined();
  });

  it("si Meta no contesta (red): «no se pudo conectar», sin la URL (que lleva la llave)", async () => {
    const aviso = vi.spyOn(console, "warn").mockImplementation(() => {});
    const m = metaFalso((url) => {
      if (url.pathname === "/refresh_access_token") throw new TypeError(`fetch failed: ${url.toString()}`);
      return undefined;
    });
    await renovarLlave(env, m.deps);
    m.pasar(DIA);
    expect(await renovarLlave(env, m.deps)).toBe("fallo");
    expect(m.estado()!.error).toBe("no se pudo conectar con Meta");
    expect(aviso.mock.calls.flat().join(" ")).not.toContain(TOKEN_IG);
  });

  it("si la dueña pega OTRA llave, esa manda: se olvida la cadena anterior (y la cuenta se vuelve a preguntar)", async () => {
    const m = metaFalso();
    await renovarLlave(env, m.deps);
    m.pasar(DIA);
    await renovarLlave(env, m.deps);
    expect(m.estado()!.llave).toBeDefined();
    const otra = { ...env, INSTAGRAM_TOKEN: "IGAAuna-llave-nueva-pegada-0000000000" } as Env;
    expect(await renovarLlave(otra, m.deps)).toBe("no_toca");
    expect(m.estado()).toEqual({ semilla: huella("IGAAuna-llave-nueva-pegada-0000000000"), vistaEn: m.ahora() });
  });

  it("el motivo de Meta en corto, con o sin el formato viejo de Instagram, y nunca con la llave", () => {
    expect(motivoDeMeta(400, { error_type: "OAuthException", code: 400, error_message: "Invalid token" }, TOKEN_IG)).toBe("HTTP 400: Invalid token [400]");
    expect(motivoDeMeta(500, null, TOKEN_IG)).toBe("HTTP 500: sin detalle");
    expect(motivoDeMeta(400, { error: { message: "token SECRETO123 vencido", code: 190 } }, "SECRETO123")).toBe("HTTP 400: token … vencido [190]");
  });
});

describe("/salud (lo local de Instagram): puerta, vencimiento y avisos, sin la llave", () => {
  it("recién pegada: pendiente, vence a más tardar a los 60 días; la cuenta, cuando el cron la averigua", async () => {
    const m = metaFalso();
    await m.adaptador.mantener!(env); // el cron: anota la llave y averigua la cuenta
    const s = await m.adaptador.saludLocal!("instagram", env);
    expect(s).toEqual({
      puerta: "inicio_sesion_instagram",
      llave: { vence: "2027-01-12", vence_seguro: false, dias_restantes: 60, renovada: null, renovacion: "pendiente" },
      cuenta: "@dcasapty",
    });
    expect(JSON.parse(m.llavero.datos.get(CLAVE_CUENTA)!).ids).toContain("17841400000000001");
  });

  it("renovada: la fecha de Meta y «ok»", async () => {
    const m = metaFalso();
    await m.adaptador.mantener!(env);
    m.pasar(DIA);
    await m.adaptador.mantener!(env);
    const s = await m.adaptador.saludLocal!("instagram", env);
    expect(s.llave).toEqual({ vence: "2027-01-13", vence_seguro: true, dias_restantes: 60, renovada: "2026-11-14", renovacion: "ok" });
    expect(s.problemas).toBeUndefined();
    expect(s.avisos).toBeUndefined();
  });

  it("si la renovación falla con tiempo de sobra: un AVISO (con la fecha) y sigue contestando; a 7 días o menos, un PROBLEMA", async () => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    let fallar = false;
    const m = metaFalso((url) => (url.pathname === "/refresh_access_token" && fallar ? Response.json({ error: { message: "Session has expired", code: 190 } }, { status: 400 }) : undefined));
    await m.adaptador.mantener!(env);
    m.pasar(DIA);
    await m.adaptador.mantener!(env); // renovada: vence el 2027-01-13
    fallar = true;
    m.pasar(41 * DIA); // le quedan 19: toca y falla
    await m.adaptador.mantener!(env);
    let s = await m.adaptador.saludLocal!("instagram", env);
    expect(s.llave).toMatchObject({ vence: "2027-01-13", dias_restantes: 19, renovacion: "fallo" });
    expect(s.problemas).toBeUndefined();
    expect(s.avisos).toEqual(["no se pudo renovar la llave de Instagram (HTTP 400: Session has expired [190]); vence el 2027-01-13; Juan lo vuelve a intentar cada día y mientras tanto sigue contestando"]);
    // Sigue usándola mientras no venza.
    await m.adaptador.enviar("instagram", { para: "1234567890123456", burbujas: ["hola"], medios: [] }, env);
    m.pasar(13 * DIA);
    await m.adaptador.mantener!(env);
    s = await m.adaptador.saludLocal!("instagram", env);
    expect(s.llave?.dias_restantes).toBe(6);
    expect(s.problemas?.[0]).toMatch(/^no se pudo renovar la llave de Instagram .*vence el 2027-01-13: si no se arregla antes, genera otra en Meta y pégala en INSTAGRAM_TOKEN$/);
    m.pasar(7 * DIA);
    s = await m.adaptador.saludLocal!("instagram", env);
    expect(s.problemas?.[0]).toBe("la llave de Instagram (INSTAGRAM_TOKEN) venció el 2027-01-13: Juan ya no puede contestar por Instagram; genera otra en Meta y pégala en Cloudflare");
    expect(JSON.stringify(s)).not.toContain(TOKEN_IG);
    expect(JSON.stringify(s)).not.toContain("IGAArenovada");
  });

  it("si nunca supo cuál es la cuenta: lo dice (los mensajes esperan)", async () => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    const m = metaFalso((url) => (url.pathname.endsWith("/me") ? Response.json({ error: { message: "x", code: 190 } }, { status: 400 }) : undefined));
    await m.adaptador.mantener!(env);
    const s = await m.adaptador.saludLocal!("instagram", env);
    expect(s.problemas?.join(" ")).toMatch(/todavía no sé cuál es la cuenta de Instagram de D'CASA.*INSTAGRAM_ACCOUNT_ID/);
    expect(s.cuenta).toBeUndefined();
    // Con la variable, no hace falta preguntar.
    expect((await m.adaptador.saludLocal!("instagram", { ...env, INSTAGRAM_ACCOUNT_ID: "17841400000000001" } as Env)).problemas).toBeUndefined();
  });
});
