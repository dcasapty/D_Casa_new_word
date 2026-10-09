import { describe, expect, it } from "vitest";
import { crearCifrador } from "../src/cifrado";

// Claves de PRUEBA: no son ningún secreto real.
const CLAVE = "clave-de-prueba-para-la-sesion-0123456789";
const OTRA = "otra-clave-de-prueba-distinta-9876543210-xyz";

describe("cifrado de la sesión en reposo", () => {
  it("cifra y descifra", async () => {
    const c = await crearCifrador(CLAVE);
    const claro = JSON.stringify({ noiseKey: { private: "SECRETO-DE-PRUEBA" }, registrationId: 1234 });
    const cifrado = await c.cifrar("creds", claro);
    expect(await c.descifrar("creds", cifrado)).toBe(claro);
  });

  it("lo guardado NO contiene el texto en claro", async () => {
    const c = await crearCifrador(CLAVE);
    const cifrado = await c.cifrar("creds", "SECRETO-DE-PRUEBA noiseKey registrationId");
    expect(cifrado).not.toContain("SECRETO");
    expect(cifrado).not.toContain("noiseKey");
    expect(cifrado).toMatch(/^v1\.[\w-]{8}\.[\w-]{16}\.[\w-]+$/);
  });

  it("cada cifrado es distinto (vector de inicialización al azar)", async () => {
    const c = await crearCifrador(CLAVE);
    const a = await c.cifrar("creds", "igual");
    const b = await c.cifrar("creds", "igual");
    expect(a).not.toBe(b);
  });

  it("maneja valores grandes (cientos de KB) y vacíos", async () => {
    const c = await crearCifrador(CLAVE);
    const grande = "x".repeat(600_000);
    expect(await c.descifrar("k", await c.cifrar("k", grande))).toBe(grande);
    expect(await c.descifrar("k", await c.cifrar("k", ""))).toBe("");
    const acentos = "Panamá · niño · 😀";
    expect(await c.descifrar("k", await c.cifrar("k", acentos))).toBe(acentos);
  });

  it("el nombre de la fila va autenticado: un valor copiado a otra fila no descifra", async () => {
    const c = await crearCifrador(CLAVE);
    const cifrado = await c.cifrar("pre-key-1", "valor");
    await expect(c.descifrar("pre-key-2", cifrado)).rejects.toThrow(/alterado|otra fila/);
  });

  it("un valor alterado no descifra", async () => {
    const c = await crearCifrador(CLAVE);
    const cifrado = await c.cifrar("creds", "valor importante");
    const partes = cifrado.split(".");
    const ct = partes[3];
    partes[3] = (ct[0] === "A" ? "B" : "A") + ct.slice(1);
    await expect(c.descifrar("creds", partes.join("."))).rejects.toThrow(/alterado|otra fila/);
  });

  it("con otra clave no descifra, y el error no filtra nada", async () => {
    const a = await crearCifrador(CLAVE);
    const b = await crearCifrador(OTRA);
    const cifrado = await a.cifrar("creds", "SECRETO-DE-PRUEBA");
    const error = await b.descifrar("creds", cifrado).catch((e) => e as Error);
    expect(error).toBeInstanceOf(Error);
    expect((error as Error).message).toContain("clave");
    expect((error as Error).message).not.toContain("SECRETO");
    expect((error as Error).message).not.toContain(CLAVE);
    expect((error as Error).message).not.toContain(OTRA);
  });

  it("un valor sin formato conocido se rechaza", async () => {
    const c = await crearCifrador(CLAVE);
    await expect(c.descifrar("creds", "texto en claro")).rejects.toThrow(/formato/);
    await expect(c.descifrar("creds", "v2.a.b.c")).rejects.toThrow(/formato/);
  });

  it("exige una clave larga", async () => {
    await expect(crearCifrador("corta")).rejects.toThrow(/corta/);
  });

  it("rotación: con la clave anterior todavía se lee, y esActual distingue", async () => {
    const vieja = await crearCifrador(CLAVE);
    const cifradoViejo = await vieja.cifrar("creds", "dato");

    const nueva = await crearCifrador(OTRA, CLAVE);
    expect(nueva.kid).not.toBe(vieja.kid);
    expect(await nueva.descifrar("creds", cifradoViejo)).toBe("dato");
    expect(nueva.esActual(cifradoViejo)).toBe(false);

    const cifradoNuevo = await nueva.cifrar("creds", "dato");
    expect(nueva.esActual(cifradoNuevo)).toBe(true);
    expect(await nueva.descifrar("creds", cifradoNuevo)).toBe("dato");

    // Sin la anterior configurada, lo viejo ya no se lee.
    const soloNueva = await crearCifrador(OTRA);
    await expect(soloNueva.descifrar("creds", cifradoViejo)).rejects.toThrow(/clave/);
  });

  it("el identificador de clave es estable y no revela la clave", async () => {
    const a = await crearCifrador(CLAVE);
    const b = await crearCifrador(CLAVE);
    expect(a.kid).toBe(b.kid);
    expect(CLAVE).not.toContain(a.kid);
    expect(a.kid).toMatch(/^[\w-]{8}$/);
  });
});
