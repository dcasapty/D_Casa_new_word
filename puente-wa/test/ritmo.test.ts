import { describe, expect, it } from "vitest";
import {
  RITMO_POR_DEFECTO as D,
  esperaEntreBurbujas,
  evaluarCuotas,
  leerRitmo,
  pausaMedio,
  pausaPensar,
  segundosParaQueQuepa,
  tiempoEscribiendo,
  type Envio,
} from "../contenedor/lib/ritmo.mjs";

const SEG = 1000;
const MIN = 60 * SEG;
const HORA = 60 * MIN;
const DIA = 24 * HORA;
const AHORA = 1_800_000_000_000;

const sinAzar = () => 0;
const todoAzar = () => 0.999999;

describe("tiempos de escritura", () => {
  it("entre burbujas: SIEMPRE al menos 1 s (contrato con Juan), con algo de azar encima", () => {
    expect(esperaEntreBurbujas(sinAzar)).toBe(1000);
    expect(esperaEntreBurbujas(todoAzar)).toBeGreaterThanOrEqual(1000);
    expect(esperaEntreBurbujas(todoAzar)).toBeLessThanOrEqual(1000 + D.entreBurbujasAzarMs);
    for (let i = 0; i < 100; i++) expect(esperaEntreBurbujas(Math.random)).toBeGreaterThanOrEqual(1000);
  });

  it("aunque alguien configure menos de 1 s, no baja del mínimo", () => {
    const r = leerRitmo({ ENTRE_BURBUJAS_MS: "100" });
    expect(r.entreBurbujasMs).toBe(1000);
    expect(esperaEntreBurbujas(sinAzar, { ...D, entreBurbujasMs: 10 })).toBe(1000);
  });

  it("«escribiendo…» crece con el largo, con piso y con tope", () => {
    const cero = () => 0.5; // variación nula
    expect(tiempoEscribiendo("", cero)).toBe(D.escribirMinMs);
    expect(tiempoEscribiendo("Hola", cero)).toBe(D.escribirMinMs);
    const mediano = tiempoEscribiendo("x".repeat(60), cero);
    expect(mediano).toBe(60 * D.escribirMsPorCaracter);
    expect(tiempoEscribiendo("x".repeat(5000), cero)).toBe(D.escribirMaxMs);
    expect(tiempoEscribiendo("x".repeat(100), cero)).toBeGreaterThan(tiempoEscribiendo("x".repeat(60), cero));
  });

  it("la variación del «escribiendo…» nunca se sale del rango", () => {
    for (let i = 0; i < 200; i++) {
      const t = tiempoEscribiendo("x".repeat(80), Math.random);
      expect(t).toBeGreaterThanOrEqual(D.escribirMinMs);
      expect(t).toBeLessThanOrEqual(D.escribirMaxMs);
    }
  });

  it("pausa de «leer» antes de contestar y pausa antes de un archivo, dentro de su rango", () => {
    expect(pausaPensar(sinAzar)).toBe(D.pensarMinMs);
    expect(pausaPensar(todoAzar)).toBe(D.pensarMaxMs);
    expect(pausaMedio(sinAzar)).toBe(D.prepararMedioMinMs);
    expect(pausaMedio(todoAzar)).toBe(D.prepararMedioMaxMs);
  });
});

describe("leerRitmo (variables del Worker)", () => {
  it("sin variables, los valores por defecto", () => {
    expect(leerRitmo({})).toEqual(D);
  });

  it("lee los topes y los recorta a un rango sano", () => {
    const r = leerRitmo({ LIMITE_POR_MINUTO: "5", LIMITE_POR_DIA: "200", LIMITE_POR_DESTINATARIO_HORA: "12", LIMITE_FRIOS_DIA: "3" });
    expect(r).toMatchObject({ porMinuto: 5, porDia: 200, porDestinatarioHora: 12, friosPorDia: 3 });
    expect(leerRitmo({ LIMITE_POR_MINUTO: "99999" }).porMinuto).toBe(60);
    expect(leerRitmo({ LIMITE_POR_DIA: "0" }).porDia).toBe(1);
    expect(leerRitmo({ LIMITE_POR_DIA: "-5" }).porDia).toBe(1);
  });

  it("valores que no son números caen al defecto", () => {
    expect(leerRitmo({ LIMITE_POR_MINUTO: "muchos" }).porMinuto).toBe(D.porMinuto);
    expect(leerRitmo({ LIMITE_POR_MINUTO: "" }).porMinuto).toBe(D.porMinuto);
  });

  it("los defaults son conservadores", () => {
    expect(D.porMinuto).toBeLessThanOrEqual(12);
    expect(D.porDia).toBeLessThanOrEqual(500);
    expect(D.friosPorDia).toBeLessThanOrEqual(20);
  });
});

describe("segundosParaQueQuepa", () => {
  it("0 si ya cabe", () => {
    expect(segundosParaQueQuepa([], AHORA, MIN, 10, 3)).toBe(0);
    expect(segundosParaQueQuepa([AHORA - 5 * SEG], AHORA, MIN, 10, 3)).toBe(0);
  });

  it("espera a que caduquen los más viejos", () => {
    // Tope 3, ya hay 3: hace 50 s, 30 s y 10 s. Para 1 más, tiene que caducar el de hace 50 s (en 10 s).
    const marcas = [AHORA - 50 * SEG, AHORA - 30 * SEG, AHORA - 10 * SEG];
    expect(segundosParaQueQuepa(marcas, AHORA, MIN, 3, 1)).toBe(10);
    // Para 2 más, el de hace 30 s (en 30 s).
    expect(segundosParaQueQuepa(marcas, AHORA, MIN, 3, 2)).toBe(30);
  });

  it("null si nunca cabrá (pide más que el tope)", () => {
    expect(segundosParaQueQuepa([], AHORA, MIN, 3, 4)).toBe(null);
  });

  it("ignora lo que ya salió de la ventana", () => {
    expect(segundosParaQueQuepa([AHORA - 2 * MIN, AHORA - 3 * MIN], AHORA, MIN, 2, 1)).toBe(0);
  });
});

function envios(n: number, hace: number, para = "50760000001", frio = false): Envio[] {
  return Array.from({ length: n }, () => ({ ts: AHORA - hace, para, frio }));
}

describe("evaluarCuotas", () => {
  const cfg = { ...D, porMinuto: 10, porDia: 100, porDestinatarioHora: 8, friosPorDia: 3 };
  const base = { ahora: AHORA, para: "50761111111", esFrio: false, cantidad: 3, cfg };

  it("pasa cuando hay holgura", () => {
    expect(evaluarCuotas({ ...base, envios: [] })).toEqual({ ok: true });
  });

  it("tope por minuto, con el tiempo de espera", () => {
    const r = evaluarCuotas({ ...base, envios: envios(9, 20 * SEG, "50762222222") });
    expect(r).toMatchObject({ ok: false, limite: "minuto" });
    if (!r.ok) expect(r.reintentarEnS).toBe(40);
  });

  it("tope por día", () => {
    const e = [...envios(60, 2 * HORA, "50762222222"), ...envios(39, 5 * HORA, "50763333333")];
    const r = evaluarCuotas({ ...base, envios: e });
    expect(r).toMatchObject({ ok: false, limite: "dia" });
    if (!r.ok) expect(r.reintentarEnS).toBeGreaterThan(0);
  });

  it("tope por destinatario y hora: no se le escribe sin parar a la misma persona", () => {
    const r = evaluarCuotas({ ...base, envios: envios(6, 10 * MIN, "50761111111") });
    expect(r).toMatchObject({ ok: false, limite: "destinatario" });
    // A otra persona sí se puede.
    expect(evaluarCuotas({ ...base, para: "50764444444", envios: envios(6, 10 * MIN, "50761111111") })).toEqual({ ok: true });
  });

  it("una petición más grande que el tope por minuto nunca cabrá", () => {
    const r = evaluarCuotas({ ...base, cantidad: 11, envios: [] });
    expect(r).toMatchObject({ ok: false, limite: "minuto", reintentarEnS: null });
  });

  it("personas nuevas (a quienes no nos han escrito): tope por día, contado por persona", () => {
    const frios = [
      ...envios(2, 3 * HORA, "50760000011", true),
      ...envios(1, 4 * HORA, "50760000012", true),
      ...envios(5, 6 * HORA, "50760000013", true),
    ];
    // Ya hay 3 personas frías hoy (el tope): una cuarta persona fría no pasa…
    const nueva = evaluarCuotas({ ...base, cantidad: 1, esFrio: true, envios: frios });
    expect(nueva).toMatchObject({ ok: false, limite: "frios" });
    // …pero seguir escribiéndole a una de esas tres sí (es la misma persona).
    expect(evaluarCuotas({ ...base, cantidad: 1, esFrio: true, para: "50760000011", envios: frios })).toEqual({ ok: true });
    // Y alguien que sí nos escribió antes no cuenta como frío.
    expect(evaluarCuotas({ ...base, cantidad: 1, esFrio: false, envios: frios })).toEqual({ ok: true });
  });

  it("lo de hace más de un día ya no cuenta", () => {
    const viejos = envios(500, DIA + HORA, "50762222222", true);
    expect(evaluarCuotas({ ...base, esFrio: true, envios: viejos })).toEqual({ ok: true });
  });
});
