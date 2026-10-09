import { describe, expect, it, vi } from "vitest";
import { entregarAJuan } from "../src/juan";

// Valor de PRUEBA: no es ningún secreto real.
const TOKEN = "token-de-prueba-0123456789-abcdefghij";
const sinEspera = async () => {};

function juanQueResponde(...estados: number[]) {
  const peticiones: Request[] = [];
  let i = 0;
  const JUAN = {
    fetch: vi.fn(async (r: Request) => {
      peticiones.push(r.clone());
      const e = estados[Math.min(i++, estados.length - 1)];
      return new Response("{}", { status: e });
    }),
  } as unknown as Fetcher;
  return { JUAN, peticiones };
}

describe("entregarAJuan (service binding JUAN)", () => {
  it("POST /webhooks/whatsapp-qr con el JSON tal cual y el token en las dos formas", async () => {
    const { JUAN, peticiones } = juanQueResponde(200);
    const cuerpo = '{"id_mensaje":"A"}';
    const r = await entregarAJuan({ JUAN, WA_TOKEN: TOKEN }, cuerpo, sinEspera);
    expect(r).toEqual({ ok: true, status: 200 });
    const p = peticiones[0];
    expect(p.method).toBe("POST");
    expect(new URL(p.url).pathname).toBe("/webhooks/whatsapp-qr");
    expect(p.headers.get("content-type")).toBe("application/json");
    expect(p.headers.get("x-wa-token")).toBe(TOKEN);
    expect(p.headers.get("authorization")).toBe(`Bearer ${TOKEN}`);
    expect(await p.text()).toBe(cuerpo);
  });

  it("reintenta una vez si Juan falla con 5xx", async () => {
    const { JUAN } = juanQueResponde(503, 200);
    const r = await entregarAJuan({ JUAN, WA_TOKEN: TOKEN }, "{}", sinEspera);
    expect(r.ok).toBe(true);
    expect(JUAN.fetch).toHaveBeenCalledTimes(2);
  });

  it("si sigue fallando, devuelve el fallo (no definitivo) para que el mensaje se guarde", async () => {
    const { JUAN } = juanQueResponde(500);
    const r = await entregarAJuan({ JUAN, WA_TOKEN: TOKEN }, "{}", sinEspera);
    expect(r).toMatchObject({ ok: false, status: 500, definitivo: false });
  });

  it("un 4xx es definitivo y no se repite (salvo 408 y 429)", async () => {
    const a = juanQueResponde(400);
    expect(await entregarAJuan({ JUAN: a.JUAN, WA_TOKEN: TOKEN }, "{}", sinEspera)).toMatchObject({ ok: false, status: 400, definitivo: true });
    expect(a.JUAN.fetch).toHaveBeenCalledTimes(1);

    const b = juanQueResponde(429, 200);
    expect((await entregarAJuan({ JUAN: b.JUAN, WA_TOKEN: TOKEN }, "{}", sinEspera)).ok).toBe(true);
    const c = juanQueResponde(408, 200);
    expect((await entregarAJuan({ JUAN: c.JUAN, WA_TOKEN: TOKEN }, "{}", sinEspera)).ok).toBe(true);
  });

  it("si la llamada lanza (Juan no existe, se está desplegando), no revienta", async () => {
    const JUAN = {
      fetch: vi.fn(async () => {
        throw new Error("Worker no encontrado");
      }),
    } as unknown as Fetcher;
    const r = await entregarAJuan({ JUAN, WA_TOKEN: TOKEN }, "{}", sinEspera);
    expect(r).toMatchObject({ ok: false, definitivo: false });
    if (!r.ok) expect(r.motivo).toContain("Worker no encontrado");
  });

  it("sin el binding JUAN avisa claramente y no es definitivo (el mensaje se guarda)", async () => {
    const r = await entregarAJuan({ WA_TOKEN: TOKEN }, "{}", sinEspera);
    expect(r).toMatchObject({ ok: false, status: 503, definitivo: false });
    if (!r.ok) expect(r.motivo).toContain("JUAN");
  });
});
