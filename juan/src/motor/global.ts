// El único Durable Object "de todos": cuánto se ha gastado en IA este mes y el último estado de salud.
// (Cada conversación vive en su propio Durable Object; esto es lo que no pertenece a ninguna.)

import { DurableObject } from "cloudflare:workers";
import type { Env } from "../env";
import { sqlDeDurableObject, type Sql } from "./sql";
import type { Uso } from "./precios";

export interface GastoDelMes {
  mes: string;
  usd: number;
  turnos: number;
  porModelo: { modelo: string; usd: number; turnos: number }[];
}

/** La lógica, sin Cloudflare: se prueba con SQLite de Node. */
export class AlmacenGlobal {
  constructor(private readonly sql: Sql) {
    sql.correr(`CREATE TABLE IF NOT EXISTS gasto (
      mes TEXT NOT NULL, modelo TEXT NOT NULL,
      entrada INTEGER NOT NULL DEFAULT 0, cache_lectura INTEGER NOT NULL DEFAULT 0,
      cache_escritura INTEGER NOT NULL DEFAULT 0, salida INTEGER NOT NULL DEFAULT 0,
      usd REAL NOT NULL DEFAULT 0, turnos INTEGER NOT NULL DEFAULT 0,
      PRIMARY KEY (mes, modelo))`);
    sql.correr("CREATE TABLE IF NOT EXISTS salud (clave TEXT PRIMARY KEY, valor TEXT NOT NULL, ts INTEGER NOT NULL)");
  }

  registrarGasto(mes: string, modelo: string, uso: Uso, usd: number): void {
    this.sql.correr(
      `INSERT INTO gasto (mes, modelo, entrada, cache_lectura, cache_escritura, salida, usd, turnos)
       VALUES (?, ?, ?, ?, ?, ?, ?, 1)
       ON CONFLICT(mes, modelo) DO UPDATE SET
         entrada = entrada + excluded.entrada, cache_lectura = cache_lectura + excluded.cache_lectura,
         cache_escritura = cache_escritura + excluded.cache_escritura, salida = salida + excluded.salida,
         usd = usd + excluded.usd, turnos = turnos + 1`,
      mes,
      modelo,
      uso.entrada,
      uso.cacheLectura,
      uso.cacheEscritura,
      uso.salida,
      usd,
    );
  }

  gastoMes(mes: string): GastoDelMes {
    const filas = this.sql.todos<{ modelo: string; usd: number; turnos: number }>("SELECT modelo, usd, turnos FROM gasto WHERE mes = ?", mes);
    return {
      mes,
      usd: filas.reduce((n, f) => n + f.usd, 0),
      turnos: filas.reduce((n, f) => n + f.turnos, 0),
      porModelo: filas,
    };
  }

  guardarSalud(clave: string, valor: unknown, ahora: number): void {
    this.sql.correr(
      "INSERT INTO salud (clave, valor, ts) VALUES (?, ?, ?) ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor, ts = excluded.ts",
      clave,
      JSON.stringify(valor),
      ahora,
    );
  }

  leerSalud<T = unknown>(clave: string): { valor: T; ts: number } | null {
    const f = this.sql.uno<{ valor: string; ts: number }>("SELECT valor, ts FROM salud WHERE clave = ?", clave);
    if (!f) return null;
    try {
      return { valor: JSON.parse(f.valor) as T, ts: f.ts };
    } catch {
      return null;
    }
  }
}

export class Global extends DurableObject<Env> {
  private readonly almacen: AlmacenGlobal;

  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env);
    this.almacen = new AlmacenGlobal(sqlDeDurableObject(ctx.storage.sql));
  }

  registrarGasto(mes: string, modelo: string, uso: Uso, usd: number): void {
    this.almacen.registrarGasto(mes, modelo, uso, usd);
  }

  gastoMes(mes: string): GastoDelMes {
    return this.almacen.gastoMes(mes);
  }

  /** Los valores viajan como texto JSON: los tipos de RPC de Cloudflare no se llevan bien con `unknown` ni `any`. */
  guardarSalud(clave: string, json: string): void {
    this.almacen.guardarSalud(clave, JSON.parse(json), Date.now());
  }

  leerSalud(clave: string): { json: string; ts: number } | null {
    const f = this.almacen.leerSalud(clave);
    return f ? { json: JSON.stringify(f.valor), ts: f.ts } : null;
  }
}
