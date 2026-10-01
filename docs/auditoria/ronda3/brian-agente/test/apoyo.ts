import { DatabaseSync } from "node:sqlite";
import { Brian, type Configuracion } from "../src/nucleo/bucle";
import { LibroSql, type Topes } from "../src/nucleo/libro";
import { OdooSimulado } from "../src/nucleo/odoo";
import { PRECIOS } from "../src/nucleo/precios";
import { esquema, type Fila, type Sql, type Valor } from "../src/nucleo/sql";
import type { Persona, Proveedor } from "../src/nucleo/tipos";

/** Mismo SQL que el Durable Object, sobre node:sqlite en memoria. */
export function sqlMemoria(): Sql {
  const db = new DatabaseSync(":memory:");
  return {
    ejecutar(q: string, ...p: Valor[]): Fila[] {
      const st = db.prepare(q);
      if (/^\s*(SELECT|.*RETURNING)/is.test(q)) return st.all(...p) as Fila[];
      st.run(...p);
      return [];
    },
  };
}

export const DUENA: Persona = { id: "u1", nombre: "Dueña", rol: "duena", areas: ["catalogo", "clientes", "ventas", "contabilidad"] };
export const VENDEDORA: Persona = { id: "u2", nombre: "Vendedora", rol: "vendedora", areas: ["catalogo", "clientes", "ventas"] };

// Topes de EJEMPLO para pruebas (microdólares); los reales los decide el dueño.
export const TOPES: Topes = { porRolMes: { duena: 1_000_000, gerencia: 500_000, vendedora: 100_000 }, globalMes: 5_000_000, aviso: 0.8 };

export function armar(proveedores: Record<string, Proveedor>, op: {
  topes?: Topes; reloj?: { t: number }; config?: Partial<Configuracion>; odoo?: OdooSimulado; sql?: Sql;
} = {}) {
  const sql = op.sql ?? sqlMemoria();
  esquema(sql);
  const reloj = op.reloj ?? { t: Date.parse("2026-10-01T15:00:00Z") };
  const libro = new LibroSql(sql, PRECIOS, op.topes ?? TOPES);
  const odoo = op.odoo ?? new OdooSimulado();
  let n = 0;
  const brian = new Brian({
    sql, libro, proveedores, odoo, reloj: () => reloj.t, nuevoId: () => `p${++n}`, conversacion: "conv-1", config: op.config,
  });
  return { brian, sql, libro, odoo, reloj };
}
