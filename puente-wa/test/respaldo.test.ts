import { describe, expect, it, vi } from "vitest";
import { COPIA_CADA_MS, armarArchivo, claveR2, debeCopiar, leerArchivo, subirCopiaR2 } from "../src/respaldo";

const T0 = 1_800_000_000_000;
const FILA = { clave: "creds", valor: "v1.kid.iv.ct", actualizado_en: 1 };

describe("debeCopiar (copia diaria)", () => {
  const base = { hayCreds: true, conectado: true, ahora: T0 };

  it("la primera, en cuanto hay sesión conectada", () => {
    expect(debeCopiar({ ...base, ultimaCopiaEn: null })).toBe(true);
  });

  it("después, una por día (con un margen para que la hora no se corra)", () => {
    expect(debeCopiar({ ...base, ultimaCopiaEn: T0 - 60_000 })).toBe(false);
    expect(debeCopiar({ ...base, ultimaCopiaEn: T0 - COPIA_CADA_MS + 20 * 60_000 })).toBe(false);
    expect(debeCopiar({ ...base, ultimaCopiaEn: T0 - COPIA_CADA_MS + 5 * 60_000 })).toBe(true);
    expect(debeCopiar({ ...base, ultimaCopiaEn: T0 - COPIA_CADA_MS })).toBe(true);
    expect(debeCopiar({ ...base, ultimaCopiaEn: T0 - 3 * COPIA_CADA_MS })).toBe(true);
  });

  it("nunca copia sin sesión, ni una sesión que no está conectada (no se pisa una buena con una rota)", () => {
    expect(debeCopiar({ ...base, ultimaCopiaEn: null, hayCreds: false })).toBe(false);
    expect(debeCopiar({ ...base, ultimaCopiaEn: null, conectado: false })).toBe(false);
  });
});

describe("archivo de copia", () => {
  it("clave del objeto en R2", () => {
    expect(claveR2("2026-10-09T03-17-00Z")).toBe("sesion/2026-10-09T03-17-00Z.json");
  });

  it("armar y leer son inversos", () => {
    const a = armarArchivo("2026-10-09T03-17-00Z", "2026-10-09T03:17:00.000Z", [FILA]);
    expect(leerArchivo(JSON.stringify(a))).toEqual(a);
  });

  it.each([
    ["no es json", "{{{", /JSON/],
    ["versión desconocida", JSON.stringify({ version: 2, copia: "x", filas: [] }), /formato/],
    ["sin filas", JSON.stringify({ version: 1, copia: "x" }), /formato/],
    ["fila mal formada", JSON.stringify({ version: 1, copia: "x", filas: [{ clave: "a" }] }), /mal formadas/],
    ["fila EN CLARO", JSON.stringify({ version: 1, copia: "x", filas: [{ clave: "creds", valor: '{"noiseKey":"x"}', actualizado_en: 1 }] }), /no está cifrada/],
  ])("rechaza: %s", (_n, texto, patron) => {
    expect(() => leerArchivo(texto as string)).toThrow(patron as RegExp);
  });
});

describe("subirCopiaR2 (opcional, apagado por defecto)", () => {
  const archivo = armarArchivo("2026-10-09T03-17-00Z", "2026-10-09T03:17:00.000Z", [FILA]);

  it("apagado por defecto: no toca R2", async () => {
    const put = vi.fn();
    const r = await subirCopiaR2({ COPIAS: { put } as unknown as R2Bucket }, archivo);
    expect(r.subida).toBe(false);
    expect(put).not.toHaveBeenCalled();
    expect((await subirCopiaR2({ COPIA_R2: "off", COPIAS: { put } as unknown as R2Bucket }, archivo)).subida).toBe(false);
  });

  it("encendido pero sin bucket enlazado: lo dice, no revienta", async () => {
    const r = await subirCopiaR2({ COPIA_R2: "on" }, archivo);
    expect(r).toMatchObject({ subida: false });
    expect(r.motivo).toContain("COPIAS");
  });

  it("encendido y con bucket: sube las filas cifradas con su clave", async () => {
    const put = vi.fn(async () => ({}));
    const r = await subirCopiaR2({ COPIA_R2: "on", COPIAS: { put } as unknown as R2Bucket }, archivo);
    expect(r.subida).toBe(true);
    const [clave, cuerpo] = put.mock.calls[0] as unknown as [string, string];
    expect(clave).toBe("sesion/2026-10-09T03-17-00Z.json");
    expect(JSON.parse(cuerpo).filas[0].valor).toBe("v1.kid.iv.ct");
  });

  it("si R2 falla, no lanza: devuelve el motivo", async () => {
    const put = vi.fn(async () => {
      throw new Error("R2 caído");
    });
    const r = await subirCopiaR2({ COPIA_R2: "on", COPIAS: { put } as unknown as R2Bucket }, archivo);
    expect(r).toMatchObject({ subida: false });
    expect(r.motivo).toContain("R2 caído");
  });

  it("el código jamás borra objetos de R2 (regla del repositorio: la retención es del bucket)", async () => {
    const { readFileSync } = await import("node:fs");
    const fuente = readFileSync(new URL("../src/respaldo.ts", import.meta.url), "utf8");
    expect(fuente).not.toMatch(/\.delete\(|deleteObject|\.list\(/);
  });
});
