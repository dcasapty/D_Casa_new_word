import { describe, expect, it } from "vitest";
import {
  celularDeJid,
  enmascarar,
  esChatDeUnaPersona,
  esMovilPanama,
  jidDeCelular,
  normalizarCelular,
  resolverDestino,
  sinDispositivo,
} from "../contenedor/lib/numeros.mjs";

describe("normalizarCelular (Panamá y el mundo)", () => {
  it.each([
    ["6026-1919", "50760261919"],
    ["60261919", "50760261919"],
    ["6026 1919", "50760261919"],
    ["+507 6026-1919", "50760261919"],
    ["507 6026 1919", "50760261919"],
    ["(507) 6026-1919", "50760261919"],
    ["00507 6026 1919", "50760261919"],
    ["50760261919", "50760261919"],
    ["+50760261919", "50760261919"],
    ["  +507.6026.1919  ", "50760261919"],
  ])("«%s» → %s", (entrada, esperado) => {
    const r = normalizarCelular(entrada);
    expect(r).toEqual({ ok: true, e164: esperado, esPanama: true });
  });

  it("acepta un número como entero", () => {
    expect(normalizarCelular(50760261919)).toEqual({ ok: true, e164: "50760261919", esPanama: true });
  });

  it("deja pasar números internacionales completos", () => {
    expect(normalizarCelular("+1 (305) 555-1234")).toEqual({ ok: true, e164: "13055551234", esPanama: false });
    expect(normalizarCelular("+57 300 123 4567")).toEqual({ ok: true, e164: "573001234567", esPanama: false });
    expect(normalizarCelular("0034 612 345 678")).toEqual({ ok: true, e164: "34612345678", esPanama: false });
  });

  it.each([
    ["", "vacío"],
    ["   ", "vacío"],
    ["hola", "caracteres"],
    ["6026-1919x", "caracteres"],
    ["123", "corto"],
    ["1234567", "corto"],
    ["305 555 1234", "no se sabe de qué país"], // 10 dígitos: ambiguo
    ["123456789", "no se sabe de qué país"], // 9 dígitos
    ["507 6026 19", "lleva 8 dígitos"], // Panamá incompleto
    ["507 6026 19199", "lleva 8 dígitos"], // Panamá con un dígito de más
    ["0 6026 1919", "empieza por 0"],
    ["1234567890123456", "demasiado largo"], // 16 dígitos
  ])("rechaza «%s»", (entrada, parte) => {
    const r = normalizarCelular(entrada);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.motivo).toContain(parte);
  });

  it.each([null, undefined, {}, [], true])("rechaza lo que no es texto: %s", (entrada) => {
    expect(normalizarCelular(entrada).ok).toBe(false);
  });

  it("nunca adivina: no inventa el 507 para un número de 9 o 10 dígitos", () => {
    for (const n of ["612345678", "6123456789"]) {
      const r = normalizarCelular(n);
      expect(r.ok).toBe(false);
    }
  });

  it("reconoce el móvil de Panamá (6xxx-xxxx)", () => {
    expect(esMovilPanama("50760261919")).toBe(true);
    expect(esMovilPanama("5072334455")).toBe(false);
    expect(esMovilPanama("13055551234")).toBe(false);
  });
});

describe("jids y destinos", () => {
  it("arma el jid de un celular", () => {
    expect(jidDeCelular("50760261919")).toBe("50760261919@s.whatsapp.net");
  });

  it("quita el sufijo de dispositivo", () => {
    expect(sinDispositivo("50760261919:12@s.whatsapp.net")).toBe("50760261919@s.whatsapp.net");
    expect(sinDispositivo("50760261919@s.whatsapp.net")).toBe("50760261919@s.whatsapp.net");
    expect(sinDispositivo(null)).toBe(null);
  });

  it("saca el celular de un jid de persona y no inventa uno para un lid", () => {
    expect(celularDeJid("50760261919:3@s.whatsapp.net")).toBe("50760261919");
    expect(celularDeJid("50760261919@c.us")).toBe("50760261919");
    expect(celularDeJid("123456789012345@lid")).toBe(null);
    expect(celularDeJid("120363025246125486@g.us")).toBe(null);
    expect(celularDeJid(undefined)).toBe(null);
  });

  it("resolverDestino acepta celulares y jids de persona", () => {
    expect(resolverDestino("6026-1919")).toEqual({ ok: true, jid: "50760261919@s.whatsapp.net", e164: "50760261919", tipo: "pn" });
    expect(resolverDestino("50760261919@s.whatsapp.net")).toEqual({
      ok: true,
      jid: "50760261919@s.whatsapp.net",
      e164: "50760261919",
      tipo: "pn",
    });
    expect(resolverDestino("50760261919:7@s.whatsapp.net")).toMatchObject({ jid: "50760261919@s.whatsapp.net" });
    expect(resolverDestino("987654321098765@lid")).toEqual({ ok: true, jid: "987654321098765@lid", e164: null, tipo: "lid" });
  });

  it.each([
    "status@broadcast",
    "120363025246125486@g.us",
    "120363025246125486@newsletter",
    "123456789@bot",
    "lista@broadcast",
  ])("NUNCA se le escribe a %s (grupos, estados, canales, bots)", (jid) => {
    const r = resolverDestino(jid);
    expect(r.ok).toBe(false);
    expect(esChatDeUnaPersona(jid)).toBe(false);
  });

  it("rechaza destinos mal formados", () => {
    expect(resolverDestino("").ok).toBe(false);
    expect(resolverDestino(undefined).ok).toBe(false);
    expect(resolverDestino("abc@s.whatsapp.net").ok).toBe(false);
    expect(resolverDestino("123@otro.servidor").ok).toBe(false);
  });

  it("un formato nuevo de chat de persona no se pierde (lista de lo que NO es)", () => {
    expect(esChatDeUnaPersona("123456789012345@lid")).toBe(true);
    expect(esChatDeUnaPersona("50760261919@s.whatsapp.net")).toBe(true);
    expect(esChatDeUnaPersona("123@hosted")).toBe(true);
    expect(esChatDeUnaPersona("")).toBe(false);
    expect(esChatDeUnaPersona(undefined)).toBe(false);
    expect(esChatDeUnaPersona("sin-arroba")).toBe(false);
  });
});

describe("enmascarar (los registros no llevan números completos)", () => {
  it("deja solo los últimos 4 dígitos", () => {
    expect(enmascarar("50760261919@s.whatsapp.net")).toBe("***1919@s.whatsapp.net");
    expect(enmascarar("falló el envío a 50760261919")).toBe("falló el envío a ***1919");
    expect(enmascarar("123456789012345@lid")).toBe("***2345@lid");
  });

  it("no toca números cortos ni texto sin teléfonos", () => {
    expect(enmascarar("reconectando en 3000 ms")).toBe("reconectando en 3000 ms");
    expect(enmascarar(null)).toBe("");
  });
});
