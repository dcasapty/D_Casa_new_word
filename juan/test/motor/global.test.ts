/**
 * El contador global de gasto de IA y el estado de salud, y las URL firmadas de los archivos del cliente.
 */
import { describe, expect, it } from "vitest";
import { AlmacenGlobal, Global } from "../../src/motor/global";
import { claveDeConversacion, firmarUrlMedio, nombreDeConversacion, verificarUrlMedio, VIDA_URL_MEDIO_MS } from "../../src/motor/mediosUrl";
import { USO_VACIO } from "../../src/motor/precios";
import type { Env } from "../../src/env";
import { crearSqlNode } from "../helpers/sqlNode";
import { ctxFalso } from "../helpers/doFalso";

const uso = (entrada: number, salida: number) => ({ ...USO_VACIO, entrada, salida });

describe("AlmacenGlobal: el gasto del mes", () => {
  it("suma por mes y por modelo, y cuenta turnos", () => {
    const g = new AlmacenGlobal(crearSqlNode());
    g.registrarGasto("2026-10", "claude-haiku-4-5", uso(1000, 100), 0.0015);
    g.registrarGasto("2026-10", "claude-haiku-4-5", uso(2000, 200), 0.003);
    g.registrarGasto("2026-10", "claude-sonnet-5-5", uso(1000, 100), 0.01);
    const r = g.gastoMes("2026-10");
    expect(r.usd).toBeCloseTo(0.0145, 6);
    expect(r.turnos).toBe(3);
    expect(r.porModelo.map((m) => [m.modelo, m.turnos]).sort()).toEqual([["claude-haiku-4-5", 2], ["claude-sonnet-5-5", 1]]);
  });

  it("un mes nuevo arranca en cero (el tope se reinicia solo)", () => {
    const g = new AlmacenGlobal(crearSqlNode());
    g.registrarGasto("2026-10", "m", uso(1, 1), 5);
    expect(g.gastoMes("2026-11")).toMatchObject({ usd: 0, turnos: 0, modelosSinPrecio: [] });
  });

  it("un modelo sin precio queda marcado como «estimado», y basta un turno estimado para marcarlo", () => {
    const g = new AlmacenGlobal(crearSqlNode());
    g.registrarGasto("2026-10", "muse-spark-1.3", uso(1, 1), 0.01, true);
    g.registrarGasto("2026-10", "muse-spark-1.3", uso(1, 1), 0.01, false);
    g.registrarGasto("2026-10", "claude-haiku-4-5", uso(1, 1), 0.01, false);
    const r = g.gastoMes("2026-10");
    expect(r.modelosSinPrecio).toEqual(["muse-spark-1.3"]);
    expect(r.porModelo.find((m) => m.modelo === "claude-haiku-4-5")!.estimado).toBe(false);
  });

  it("guarda los tokens, también los de caché", () => {
    const sql = crearSqlNode();
    const g = new AlmacenGlobal(sql);
    g.registrarGasto("2026-10", "m", { entrada: 10, cacheLectura: 20, cacheEscritura: 30, salida: 40 }, 1);
    g.registrarGasto("2026-10", "m", { entrada: 1, cacheLectura: 2, cacheEscritura: 3, salida: 4 }, 1);
    expect(sql.uno("SELECT entrada, cache_lectura, cache_escritura, salida FROM gasto")).toEqual({ entrada: 11, cache_lectura: 22, cache_escritura: 33, salida: 44 });
  });
});

describe("AlmacenGlobal: la salud", () => {
  it("guarda y lee cualquier valor JSON, con su hora; pisa el anterior", () => {
    const g = new AlmacenGlobal(crearSqlNode());
    expect(g.leerSalud("x")).toBeNull();
    g.guardarSalud("ia_fallo", { proveedor: "meta", motivo: "500" }, 100);
    g.guardarSalud("ia_fallo", { proveedor: "meta", motivo: "429" }, 200);
    expect(g.leerSalud("ia_fallo")).toEqual({ valor: { proveedor: "meta", motivo: "429" }, ts: 200 });
  });

  it("un valor ilegible se ignora en vez de romper", () => {
    const sql = crearSqlNode();
    const g = new AlmacenGlobal(sql);
    sql.correr("INSERT INTO salud (clave, valor, ts) VALUES ('roto', '{no es json', 1)");
    expect(g.leerSalud("roto")).toBeNull();
  });
});

describe("el Durable Object Global (por RPC los valores viajan como texto JSON)", () => {
  it("guardarSalud/leerSalud de ida y vuelta, y el gasto del mes", () => {
    const g = new Global(ctxFalso() as unknown as DurableObjectState, {} as Env);
    g.registrarGasto("2026-10", "claude-haiku-4-5", uso(100, 10), 0.002, false);
    expect(g.gastoMes("2026-10").usd).toBeCloseTo(0.002, 6);
    g.guardarSalud("avisos", JSON.stringify({ avisados: ["x"] }));
    const leido = g.leerSalud("avisos")!;
    expect(JSON.parse(leido.json)).toEqual({ avisados: ["x"] });
    expect(leido.ts).toBeGreaterThan(0);
    expect(g.leerSalud("no_existe")).toBeNull();
  });
});

describe("URL firmada de un archivo del cliente", () => {
  const SECRETO = "secreto-del-worker-0123456789";
  const AHORA = 1_790_000_000_000;
  const clave = claveDeConversacion("whatsapp_qr", "50760261919");

  it("el nombre de la conversación viaja en base64url (con tildes y @lid incluidos) y vuelve igual", () => {
    for (const [canal, id] of [["whatsapp_qr", "50760261919"], ["whatsapp_qr", "123456789@lid"], ["telegram", "-1001234"], ["messenger", "ñandú"]]) {
      const c = claveDeConversacion(canal, id);
      expect(c).toMatch(/^[A-Za-z0-9_-]+$/);
      expect(nombreDeConversacion(c)).toBe(`${canal}:${id}`);
    }
    expect(nombreDeConversacion("%%%")).toBeNull();
  });

  it("una URL firmada verifica; vence a los 2 días", async () => {
    const url = new URL(await firmarUrlMedio("https://juan.example/", SECRETO, clave, "abc123abc123abc1", AHORA));
    expect(url.pathname).toBe(`/media/${clave}/abc123abc123abc1`);
    const exp = url.searchParams.get("exp");
    const sig = url.searchParams.get("sig");
    expect(Number(exp)).toBe(AHORA + VIDA_URL_MEDIO_MS);
    expect(await verificarUrlMedio(SECRETO, clave, "abc123abc123abc1", exp, sig, AHORA)).toBe("ok");
    expect(await verificarUrlMedio(SECRETO, clave, "abc123abc123abc1", exp, sig, AHORA + VIDA_URL_MEDIO_MS)).toBe("ok");
    expect(await verificarUrlMedio(SECRETO, clave, "abc123abc123abc1", exp, sig, AHORA + VIDA_URL_MEDIO_MS + 1)).toBe("vencida");
  });

  it("cambiar la conversación, el archivo, la hora o el secreto invalida la firma", async () => {
    const url = new URL(await firmarUrlMedio("https://juan.example", SECRETO, clave, "abc123abc123abc1", AHORA));
    const exp = url.searchParams.get("exp");
    const sig = url.searchParams.get("sig");
    expect(await verificarUrlMedio(SECRETO, claveDeConversacion("whatsapp_qr", "50760000000"), "abc123abc123abc1", exp, sig, AHORA)).toBe("firma");
    expect(await verificarUrlMedio(SECRETO, clave, "ffffffffffffffff", exp, sig, AHORA)).toBe("firma");
    expect(await verificarUrlMedio(SECRETO, clave, "abc123abc123abc1", String(Number(exp) + 1), sig, AHORA)).toBe("firma");
    expect(await verificarUrlMedio("otro-secreto", clave, "abc123abc123abc1", exp, sig, AHORA)).toBe("firma");
  });

  it("sin secreto, sin firma o con una hora que no es número: nunca es válida", async () => {
    expect(await verificarUrlMedio("", clave, "x", "123", "abc", AHORA)).toBe("firma");
    expect(await verificarUrlMedio(SECRETO, clave, "x", "123", null, AHORA)).toBe("firma");
    expect(await verificarUrlMedio(SECRETO, clave, "x", null, "abc", AHORA)).toBe("firma");
    expect(await verificarUrlMedio(SECRETO, clave, "x", "mañana", "abc", AHORA)).toBe("firma");
  });
});
