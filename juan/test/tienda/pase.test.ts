/**
 * El pase de Brian de la tienda: firma con la llave derivada de JUAN_WORKER_TOKEN (comparada en tiempo constante), vencimiento y
 * `sid`; la red del pase NO se compara con la conexión. Y la llave del tope por red del Worker (la IPv4 entera o la /64 de una IPv6).
 * Las cuentas se comprueban también con `node:crypto`,
 * que es como lo calcula Odoo en Python (`hmac.new(...).digest()`): si una de las dos mitades usara el hex en vez de los bytes, no
 * coincidirían.
 */
import { createHmac } from "node:crypto";
import { describe, expect, it } from "vitest";
import { aBase64Url, bytesDeIp, deBase64Url, firmarPase, llaveDeRed, llaveDeRed48, llaveDelPase, verificarPase } from "../../src/tienda/pase";

const TOKEN = "token-del-worker-de-prueba-0123456789abcdef";
const AHORA = Date.UTC(2026, 10, 13, 16, 0);
const SID = "AAECAwQFBgcICQoLDA0ODw"; // 16 bytes en base64url
const payload = (extra: Record<string, unknown> = {}) => ({ v: 1, sid: SID, exp: Math.floor(AHORA / 1000) + 1800, red: "190.140.12.0/24", sitio: 1, ...extra });
const cabecera = (pase: string) => `Pase ${pase}`;

/** Lo que hace Odoo, escrito aparte con node:crypto (no con el código del Worker). */
function paseComoOdoo(token: string, datos: Record<string, unknown>): string {
  const llave = createHmac("sha256", Buffer.from(token, "utf8")).update("brian-tienda-pase-v1").digest();
  const cuerpo = Buffer.from(JSON.stringify(datos), "utf8").toString("base64url");
  const firma = createHmac("sha256", llave).update(cuerpo).digest("base64url");
  return `${cuerpo}.${firma}`;
}

describe("la llave y la firma (las mismas cuentas que Odoo)", () => {
  it("la llave son los 32 bytes crudos de HMAC-SHA256(token, «brian-tienda-pase-v1»)", async () => {
    const esperada = createHmac("sha256", TOKEN).update("brian-tienda-pase-v1").digest();
    expect(Buffer.from(await llaveDelPase(TOKEN)).equals(esperada)).toBe(true);
  });

  it("un pase hecho como Odoo (con node:crypto) pasa, y el del Worker es idéntico", async () => {
    const datos = payload();
    const deOdoo = paseComoOdoo(TOKEN, datos);
    expect(await firmarPase(TOKEN, datos)).toBe(deOdoo);
    const r = await verificarPase(TOKEN, cabecera(deOdoo), AHORA);
    expect(r).toEqual({ ok: true, pase: { sid: SID, exp: datos.exp, red: "190.140.12.0/24", sitio: 1 } });
  });

  it("base64url sin relleno, y con relleno también se acepta", async () => {
    const bytes = new Uint8Array([251, 255, 0, 1]);
    expect(aBase64Url(bytes)).toBe("-_8AAQ");
    expect([...deBase64Url("-_8AAQ")!]).toEqual([251, 255, 0, 1]);
    expect([...deBase64Url("-_8AAQ==")!]).toEqual([251, 255, 0, 1]);
    expect(deBase64Url("no+es/base64url")).toBeNull();
  });
});

describe("verificar el pase", () => {
  it("válido: firma buena, sin vencer y desde su red", async () => {
    const r = await verificarPase(TOKEN, cabecera(await firmarPase(TOKEN, payload())), AHORA);
    expect(r.ok).toBe(true);
  });

  it("vencido: exp en el pasado (o justo ahora)", async () => {
    for (const exp of [Math.floor(AHORA / 1000) - 1, Math.floor(AHORA / 1000)]) {
      const r = await verificarPase(TOKEN, cabecera(await firmarPase(TOKEN, payload({ exp }))), AHORA);
      expect(r).toEqual({ ok: false, motivo: "vencido" });
    }
  });

  it("un pase que dura más de una hora no es de Odoo", async () => {
    const r = await verificarPase(TOKEN, cabecera(await firmarPase(TOKEN, payload({ exp: Math.floor(AHORA / 1000) + 7200 }))), AHORA);
    expect(r).toEqual({ ok: false, motivo: "forma" });
  });

  it("la red del pase no se compara: vale desde otra IP, otra familia (IPv4/IPv6) o sin red", async () => {
    for (const red of ["190.140.12.0/24", "2001:db8:0:1::/64", undefined, 5]) {
      const r = await verificarPase(TOKEN, cabecera(await firmarPase(TOKEN, payload({ red }))), AHORA);
      expect(r.ok).toBe(true);
    }
    const r = await verificarPase(TOKEN, cabecera(await firmarPase(TOKEN, payload({ red: 5 }))), AHORA);
    expect(r.ok && r.pase.red).toBeNull();
  });

  it("alterado: cambiar el payload (otra red, otro sid, más tiempo) rompe la firma", async () => {
    const pase = await firmarPase(TOKEN, payload());
    const [, firma] = pase.split(".");
    for (const cambio of [{ red: "0.0.0.0/0" }, { red: "8.8.8.0/24" }, { sid: "BBBBBBBBBBBBBBBBBBBBBB" }, { exp: Math.floor(AHORA / 1000) + 3000 }]) {
      const otro = aBase64Url(new TextEncoder().encode(JSON.stringify(payload(cambio))));
      expect(await verificarPase(TOKEN, cabecera(`${otro}.${firma}`), AHORA)).toEqual({ ok: false, motivo: "firma" });
    }
  });

  it("alterado: una firma cambiada, cortada o de otro token no pasa", async () => {
    const pase = await firmarPase(TOKEN, payload());
    const [cuerpo, firma] = pase.split(".");
    const cambiada = `${firma.slice(0, -2)}${firma.endsWith("AA") ? "BB" : "AA"}`;
    expect(await verificarPase(TOKEN, cabecera(`${cuerpo}.${cambiada}`), AHORA)).toEqual({ ok: false, motivo: "firma" });
    expect(await verificarPase(TOKEN, cabecera(`${cuerpo}.${firma.slice(0, 20)}`), AHORA)).toEqual({ ok: false, motivo: "firma" });
    const deOtro = await firmarPase("otro-token-que-no-es-el-del-worker-000", payload());
    expect(await verificarPase(TOKEN, cabecera(deOtro), AHORA)).toEqual({ ok: false, motivo: "firma" });
  });

  it("falla cerrado: sin token en el Worker, sin cabecera, con otro esquema o mal formado", async () => {
    const pase = await firmarPase(TOKEN, payload());
    expect(await verificarPase(undefined, cabecera(pase), AHORA)).toEqual({ ok: false, motivo: "sin_token" });
    expect(await verificarPase("", cabecera(pase), AHORA)).toEqual({ ok: false, motivo: "sin_token" });
    expect(await verificarPase(TOKEN, null, AHORA)).toEqual({ ok: false, motivo: "falta" });
    expect(await verificarPase(TOKEN, `Bearer ${pase}`, AHORA)).toEqual({ ok: false, motivo: "falta" });
    for (const raro of ["Pase solo-una-parte", "Pase a.b.c", `Pase ${"x".repeat(2000)}.y`, "Pase .", "Pase ¡¿.!!"]) {
      const r = await verificarPase(TOKEN, raro, AHORA);
      expect(r.ok).toBe(false);
    }
  });

  it("un payload firmado pero sin la forma del contrato no pasa (v, sid, exp)", async () => {
    for (const cambio of [{ v: 2 }, { sid: "corto" }, { sid: "con espacios y raro!!" }, { sid: undefined }, { exp: "mañana" }]) {
      const r = await verificarPase(TOKEN, cabecera(await firmarPase(TOKEN, payload(cambio))), AHORA);
      expect(r).toEqual({ ok: false, motivo: "forma" });
    }
  });
});

describe("la llave del tope por red (de CF-Connecting-IP, como el borde)", () => {
  it("IPv4: la dirección entera (nunca la /24: el mismo operador comparte una, y está el CGNAT)", () => {
    expect(llaveDeRed("190.140.12.34")).toBe("190.140.12.34");
    expect(llaveDeRed("190.140.12.35")).not.toBe(llaveDeRed("190.140.12.34"));
  });

  it("IPv6: la red /64 (lo que recibe un solo cliente), escriba como se escriba", () => {
    expect(llaveDeRed("2001:db8:0:1:aaaa:bbbb:cccc:dddd")).toBe("2001:db8:0:1::/64");
    expect(llaveDeRed("2001:0db8:0000:0001::1")).toBe("2001:db8:0:1::/64");
    expect(llaveDeRed("[2001:db8:0:1::99]")).toBe("2001:db8:0:1::/64");
    expect(llaveDeRed("2001:db8:0:2::1")).toBe("2001:db8:0:2::/64");
  });

  it("una IPv4 dentro de IPv6 (::ffff:a.b.c.d) cuenta como IPv4; sin IP o con algo raro, una sola llave para todos", () => {
    expect(llaveDeRed("::ffff:190.140.12.34")).toBe("190.140.12.34");
    for (const raro of [null, "", "no-es-ip", "1.2.3", "256.1.1.1"]) expect(llaveDeRed(raro)).toBe("sin-ip");
  });

  it("la /48 de una IPv6 (para el tope por /48); con IPv4 o sin IP, ninguna", () => {
    expect(llaveDeRed48("2001:db8:aa:1:2:3:4:5")).toBe("2001:db8:aa::/48");
    expect(llaveDeRed48("2001:0db8:00aa:ffff::1")).toBe("2001:db8:aa::/48");
    for (const sin of ["190.140.12.34", "::ffff:190.140.12.34", null, "no-es-ip"]) expect(llaveDeRed48(sin)).toBeNull();
  });

  it("lee bien las IP, y lo que no es una IP no pasa", () => {
    expect([...bytesDeIp("2001:db8::1")!]).toEqual([0x20, 0x01, 0x0d, 0xb8, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1]);
    expect(bytesDeIp("[2001:db8::1]")?.length).toBe(16);
    for (const raro of ["", "1.2.3", "256.1.1.1", "01.2.3.4", "1::2::3", "gggg::1", "hola"]) expect(bytesDeIp(raro)).toBeNull();
  });
});
