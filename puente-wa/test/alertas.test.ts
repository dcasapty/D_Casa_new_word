import { describe, expect, it, vi } from "vitest";
import { ALERTA_POR_DEFECTO, despuesDeAvisar, enviarTelegram, evaluarAlerta, leerConfigAlerta } from "../src/alertas";
import { aplicarVigilancia, diarioNuevo, type Diario } from "../src/vigilancia";

const T0 = 1_800_000_000_000;
const MIN = 60_000;
const CFG = { minutos: 10, reavisoMinutos: 120 };

/** Un diario de un canal que estuvo conectado y se cayó hace `hace` minutos. */
function caido(hace: number, extra: Partial<Diario> = {}): Diario {
  return { ...diarioNuevo(), ultimaConexionVista: new Date(T0 - 60 * MIN).toISOString(), sinConexionDesde: T0 - hace * MIN, ...extra };
}

describe("evaluarAlerta", () => {
  it("antes de N minutos no avisa; al cumplirse, avisa", () => {
    expect(evaluarAlerta(caido(3), "caido", T0, CFG)).toBe(null);
    expect(evaluarAlerta(caido(9), "caido", T0, CFG)).toBe(null);
    const a = evaluarAlerta(caido(10), "caido", T0, CFG);
    expect(a?.tipo).toBe("caida");
    expect(a?.texto).toContain("10 min");
  });

  it("si está esperando el QR (desvinculado) el aviso lo dice con claridad", () => {
    const a = evaluarAlerta(caido(15), "esperando-a-una-persona", T0, CFG);
    expect(a?.tipo).toBe("necesita_qr");
    expect(a?.texto).toContain("QR");
    expect(a?.texto).toContain("teléfono del negocio");
  });

  it("no insiste: un solo aviso, y recién a las 2 h vuelve a avisar", () => {
    let d = caido(10);
    const a = evaluarAlerta(d, "caido", T0, CFG)!;
    d = { ...d, ...despuesDeAvisar(d, a, T0) };
    expect(d.avisoActivo).toBe(true);
    expect(evaluarAlerta({ ...d, sinConexionDesde: T0 - 60 * MIN }, "caido", T0 + 30_000, CFG)).toBe(null);
    expect(evaluarAlerta({ ...d, sinConexionDesde: T0 - 60 * MIN }, "caido", T0 + 119 * MIN, CFG)).toBe(null);
    const otra = evaluarAlerta({ ...d, sinConexionDesde: T0 - 60 * MIN }, "caido", T0 + 120 * MIN, CFG);
    expect(otra?.texto).toContain("Sigue igual");
  });

  it("avisa UNA vez la recuperación, y solo si antes avisó la caída", () => {
    let d = caido(25);
    const a = evaluarAlerta(d, "caido", T0, CFG)!;
    d = { ...d, ...despuesDeAvisar(d, a, T0) };
    const r = evaluarAlerta(d, "sano", T0 + 3 * MIN, CFG);
    expect(r?.tipo).toBe("recuperado");
    expect(r?.texto).toContain("volvió a conectarse");
    // Ya recuperado, el diario deja de tener un aviso activo: nada más que decir.
    d = { ...d, ...despuesDeAvisar(d, r!, T0 + 3 * MIN), sinConexionDesde: null };
    expect(d.avisoActivo).toBe(false);
    expect(evaluarAlerta(d, "sano", T0 + 4 * MIN, CFG)).toBe(null);
    // Una caída corta que nunca llegó a avisar, tampoco avisa al volver.
    expect(evaluarAlerta(caido(2), "sano", T0, CFG)).toBe(null);
  });

  it("jamás avisa si el canal nunca estuvo conectado (instalación nueva, aún sin escanear el QR)", () => {
    const nunca = { ...diarioNuevo(), sinConexionDesde: T0 - 600 * MIN };
    expect(evaluarAlerta(nunca, "esperando-a-una-persona", T0, CFG)).toBe(null);
    expect(evaluarAlerta(nunca, "caido", T0, CFG)).toBe(null);
  });

  it("sin «desde cuándo» no hay nada que medir", () => {
    expect(evaluarAlerta({ ...caido(30), sinConexionDesde: null }, "caido", T0, CFG)).toBe(null);
  });

  it("el texto nunca lleva tokens, QR ni números de teléfono", () => {
    for (const v of ["caido", "esperando-a-una-persona"] as const) {
      const a = evaluarAlerta(caido(45), v, T0, CFG)!;
      expect(a.texto).not.toMatch(/\d{7,}/);
      expect(a.texto.toLowerCase()).not.toContain("token");
      expect(a.texto).not.toContain("data:image");
    }
  });

  it("línea de tiempo completa con el diario real: caída → aviso → recuperación", () => {
    let d = diarioNuevo();
    d = aplicarVigilancia(d, "sano", T0).diario; // conectado
    const eventos: string[] = [];
    for (let t = 1; t <= 40; t++) {
      const ahora = T0 + t * MIN;
      // Se cae en el minuto 1; el aviso sale 10 minutos después (minuto 11).
      const veredicto = t < 30 ? "caido" : "sano";
      const previo = d;
      d = aplicarVigilancia(d, veredicto, ahora).diario;
      const a = evaluarAlerta(veredicto === "sano" ? previo : d, veredicto, ahora, CFG);
      if (a) {
        eventos.push(`${t}:${a.tipo}`);
        d = { ...d, ...despuesDeAvisar(d, a, ahora) };
      }
    }
    expect(eventos).toEqual(["11:caida", "30:recuperado"]);
  });
});

describe("leerConfigAlerta", () => {
  it("valores por defecto y recortados a un rango sano", () => {
    expect(leerConfigAlerta({})).toEqual(ALERTA_POR_DEFECTO);
    expect(leerConfigAlerta({ ALERTA_MINUTOS: "5", ALERTA_REAVISO_MINUTOS: "60" })).toEqual({ minutos: 5, reavisoMinutos: 60 });
    expect(leerConfigAlerta({ ALERTA_MINUTOS: "0" }).minutos).toBe(1);
    expect(leerConfigAlerta({ ALERTA_MINUTOS: "mucho" }).minutos).toBe(10);
  });
});

describe("enviarTelegram", () => {
  const TOKEN_FALSO = "123456:ABC-token-de-prueba";

  it("llama a la API de Telegram con el chat y el texto", async () => {
    const llamar = vi.fn(async () => new Response("{}", { status: 200 }));
    const r = await enviarTelegram(llamar as any, TOKEN_FALSO, "-100999", "hola dueña");
    expect(r).toEqual({ ok: true });
    const [url, init] = llamar.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe(`https://api.telegram.org/bot${TOKEN_FALSO}/sendMessage`);
    expect(JSON.parse(init.body as string)).toMatchObject({ chat_id: "-100999", text: "hola dueña" });
  });

  it("si Telegram falla o no se llega, devuelve un motivo sin el token y no lanza", async () => {
    const r401 = await enviarTelegram((async () => new Response("no", { status: 401 })) as any, TOKEN_FALSO, "1", "x");
    expect(r401).toEqual({ ok: false, motivo: "Telegram contestó 401" });
    const red = await enviarTelegram((async () => {
      throw new Error(`fallo conectando a https://api.telegram.org/bot${TOKEN_FALSO}/sendMessage`);
    }) as any, TOKEN_FALSO, "1", "x");
    expect(red.ok).toBe(false);
    expect(JSON.stringify(red)).not.toContain(TOKEN_FALSO);
  });
});
