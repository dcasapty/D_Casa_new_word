import { describe, expect, it } from "vitest";
import {
  LATIDO_VENCIDO_MS,
  autorizado,
  derivarTokenContenedor,
  latidoVencido,
  reinicioPedido,
  tokenEsApto,
  tokenPresentado,
  tokensIguales,
  veredictoDeSalud,
} from "../src/comun";

// Valores de PRUEBA: no son ningún secreto real.
const TOKEN = "token-de-prueba-0123456789-abcdefghij";

const pet = (cabeceras: Record<string, string>, url = "https://puente.test/api/estado") =>
  new Request(url, { headers: cabeceras });

describe("tokensIguales (tiempo constante)", () => {
  it("iguales y distintos", () => {
    expect(tokensIguales(TOKEN, TOKEN)).toBe(true);
    expect(tokensIguales(TOKEN + "x", TOKEN)).toBe(false);
    expect(tokensIguales(TOKEN.slice(0, -1), TOKEN)).toBe(false);
    expect(tokensIguales("A" + TOKEN.slice(1), TOKEN)).toBe(false);
    expect(tokensIguales(TOKEN.slice(0, -1) + "Z", TOKEN)).toBe(false);
  });

  it("un token esperado vacío nunca coincide (ni con otro vacío)", () => {
    expect(tokensIguales("", "")).toBe(false);
    expect(tokensIguales("algo", "")).toBe(false);
  });

  it("no se deja engañar por largos distintos con prefijo común", () => {
    expect(tokensIguales("abc", "abcdef")).toBe(false);
    expect(tokensIguales("abcdef", "abc")).toBe(false);
  });

  it("no usa === para comparar (recorre siempre todo el largo)", () => {
    // La función no devuelve antes de tiempo: se comprueba por construcción leyendo el código fuente.
    expect(tokensIguales.toString()).not.toMatch(/presentado\s*===\s*esperado/);
    expect(tokensIguales.toString()).toContain("for (");
  });
});

describe("tokenPresentado: de dónde viene el token (nunca de la URL)", () => {
  it("Authorization: Bearer", () => {
    expect(tokenPresentado(pet({ authorization: `Bearer ${TOKEN}` }))).toEqual({ via: "bearer", valor: TOKEN });
    expect(tokenPresentado(pet({ authorization: `bearer   ${TOKEN}  ` })).valor).toBe(TOKEN);
  });

  it("x-wa-token (el del CRM de origen)", () => {
    expect(tokenPresentado(pet({ "x-wa-token": TOKEN }))).toEqual({ via: "cabecera", valor: TOKEN });
  });

  it("x-wa-token-b64, incluso con caracteres fuera de ASCII (el «401 mudo»)", () => {
    const raro = "tóken-ñandú-0123456789-abcdef";
    const b64 = btoa(String.fromCharCode(...new TextEncoder().encode(raro)));
    expect(tokenPresentado(pet({ "x-wa-token-b64": b64 }))).toEqual({ via: "cabecera-b64", valor: raro });
    expect(tokenPresentado(pet({ "x-wa-token-b64": "%%%no-es-base64" })).valor).toBe("");
  });

  it("el token en la URL NO se acepta (quedaría en los registros de Cloudflare)", () => {
    const r = pet({}, `https://puente.test/api/qr?t=${TOKEN}&token=${TOKEN}`);
    expect(tokenPresentado(r)).toEqual({ via: "nada", valor: "" });
    expect(autorizado(r, TOKEN)).toBe(false);
  });

  it("autorizado()", () => {
    expect(autorizado(pet({ authorization: `Bearer ${TOKEN}` }), TOKEN)).toBe(true);
    expect(autorizado(pet({ authorization: "Bearer otro" }), TOKEN)).toBe(false);
    expect(autorizado(pet({}), TOKEN)).toBe(false);
    expect(autorizado(pet({ authorization: "Basic abc" }), TOKEN)).toBe(false);
  });
});

describe("tokenEsApto", () => {
  it("mínimo 24 caracteres y solo ASCII imprimible", () => {
    expect(tokenEsApto(TOKEN)).toEqual({ apto: true });
    expect(tokenEsApto("corto").apto).toBe(false);
    expect(tokenEsApto("a".repeat(23)).apto).toBe(false);
    expect(tokenEsApto("a".repeat(24)).apto).toBe(true);
    const ene = tokenEsApto("contraseña-larga-0123456789-abcdef");
    expect(ene.apto).toBe(false);
    expect(ene.motivo).toContain("ASCII");
    expect(tokenEsApto("con espacio 0123456789 abcdefghijkl").apto).toBe(false);
    expect(tokenEsApto("con“comillas”curvas-0123456789-abc").apto).toBe(false);
  });
});

describe("derivarTokenContenedor (el contenedor nunca tiene el WA_TOKEN)", () => {
  it("es hexadecimal de 64 caracteres, determinista y distinto del WA_TOKEN", async () => {
    const a = await derivarTokenContenedor(TOKEN);
    const b = await derivarTokenContenedor(TOKEN);
    expect(a).toMatch(/^[0-9a-f]{64}$/);
    expect(a).toBe(b);
    expect(a).not.toContain(TOKEN);
    expect(tokenEsApto(a).apto).toBe(true); // solo ASCII: no hay «401 mudo» en este tramo
  });

  it("cambia si cambia el WA_TOKEN, y un token no sirve por el otro", async () => {
    const a = await derivarTokenContenedor(TOKEN);
    const b = await derivarTokenContenedor(TOKEN + "1");
    expect(a).not.toBe(b);
    expect(tokensIguales(a, TOKEN)).toBe(false);
    expect(tokensIguales(TOKEN, a)).toBe(false);
  });

  it("coincide con HMAC-SHA256 calculado aparte (vector de referencia)", async () => {
    const { createHmac } = await import("node:crypto");
    const esperado = createHmac("sha256", TOKEN).update("dcasa-puente-wa/contenedor/v1").digest("hex");
    expect(await derivarTokenContenedor(TOKEN)).toBe(esperado);
  });
});

describe("salud", () => {
  it("veredictoDeSalud", () => {
    expect(veredictoDeSalud("conectada")).toBe("sano");
    expect(veredictoDeSalud("esperando-qr")).toBe("esperando-a-una-persona");
    expect(veredictoDeSalud("desvinculada")).toBe("esperando-a-una-persona");
    for (const c of ["cerrada", "arrancando", null, undefined, "", "otra-cosa"]) {
      expect(veredictoDeSalud(c)).toBe("caido");
    }
  });

  it("latidoVencido", () => {
    const ahora = 1_800_000_000_000;
    expect(latidoVencido(null, ahora)).toBe(false);
    expect(latidoVencido(undefined, ahora)).toBe(false);
    expect(latidoVencido(ahora - 1000, ahora)).toBe(false);
    expect(latidoVencido(ahora - LATIDO_VENCIDO_MS, ahora)).toBe(false);
    expect(latidoVencido(ahora - LATIDO_VENCIDO_MS - 1, ahora)).toBe(true);
  });

  it("reinicioPedido empieza de cero", () => {
    expect(reinicioPedido(new Date("2026-10-09T12:00:00Z"))).toEqual({
      ultimaMuerteVista: "2026-10-09T12:00:00.000Z",
      desconectadoSeguidos: 0,
    });
  });
});
