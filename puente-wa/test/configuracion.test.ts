import { describe, expect, it } from "vitest";
import { SECRETOS_OBLIGATORIOS, SECRETOS_OPCIONALES, estadoSinConfigurar, revisarConfiguracion } from "../src/configuracion";

// Valores de PRUEBA: no son ningún secreto real.
const TOKEN = "token-de-prueba-0123456789-abcdefghij";
const CLAVE = "clave-de-prueba-para-la-sesion-0123456789";

describe("revisarConfiguracion (solo nombres, nunca valores)", () => {
  it("sin nada: faltan los dos obligatorios", () => {
    const c = revisarConfiguracion({});
    expect(c.faltan).toEqual(["WA_TOKEN", "WA_SESION_CLAVE"]);
    expect(c.listo).toBe(false);
    expect(c.opcionalesFaltan).toEqual(["TELEGRAM_BOT_TOKEN_JUAN", "ALERTA_TELEGRAM_CHAT"]);
  });

  it("con los obligatorios, listo (los opcionales solo apagan el aviso por Telegram)", () => {
    const c = revisarConfiguracion({ WA_TOKEN: TOKEN, WA_SESION_CLAVE: CLAVE });
    expect(c).toMatchObject({ faltan: [], invalidos: [], listo: true });
    expect(c.opcionalesFaltan.length).toBe(2);
    expect(revisarConfiguracion({ WA_TOKEN: TOKEN, WA_SESION_CLAVE: CLAVE, TELEGRAM_BOT_TOKEN_JUAN: "x", ALERTA_TELEGRAM_CHAT: "1" }).opcionalesFaltan).toEqual([]);
  });

  it("vacíos o con solo espacios cuentan como faltantes", () => {
    expect(revisarConfiguracion({ WA_TOKEN: "", WA_SESION_CLAVE: "   " }).faltan).toEqual(["WA_TOKEN", "WA_SESION_CLAVE"]);
    expect(revisarConfiguracion({ WA_TOKEN: 123 as any, WA_SESION_CLAVE: CLAVE }).faltan).toEqual(["WA_TOKEN"]);
  });

  it("presentes pero inservibles: se dice el MOTIVO, jamás el valor", () => {
    const c = revisarConfiguracion({ WA_TOKEN: "corto-ñ", WA_SESION_CLAVE: "tambien-corta" });
    expect(c.listo).toBe(false);
    expect(c.faltan).toEqual([]);
    expect(c.invalidos.map((i) => i.nombre)).toEqual(["WA_TOKEN", "WA_SESION_CLAVE"]);
    expect(JSON.stringify(c)).not.toContain("corto-ñ");
    expect(JSON.stringify(c)).not.toContain("tambien-corta");
  });

  it("un WA_TOKEN con caracteres fuera de ASCII no es apto", () => {
    const c = revisarConfiguracion({ WA_TOKEN: "contraseña-larga-0123456789-abcdef", WA_SESION_CLAVE: CLAVE });
    expect(c.invalidos).toEqual([{ nombre: "WA_TOKEN", motivo: expect.stringContaining("ASCII") }]);
  });

  it("los nombres coinciden con el contrato (docs/JUAN.md)", () => {
    expect(SECRETOS_OBLIGATORIOS).toContain("WA_TOKEN");
    expect(SECRETOS_OPCIONALES).toContain("TELEGRAM_BOT_TOKEN_JUAN");
  });
});

describe("estadoSinConfigurar", () => {
  it("dice que no está conectado y qué nombres faltan; nada más", () => {
    const e = estadoSinConfigurar(revisarConfiguracion({}), { PUENTE_ACTIVO: "on" });
    expect(e).toMatchObject({
      ok: true,
      estado: "sin_configurar",
      conectado: false,
      activo: true,
      secretos_faltantes: ["WA_TOKEN", "WA_SESION_CLAVE"],
      binding_juan: false,
    });
    expect(e.mensaje).toContain("Variables and Secrets");
  });
});
