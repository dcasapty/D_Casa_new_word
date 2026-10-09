// SQLite de Node (node:sqlite) con la misma forma que `ctx.storage.sql` de un Durable Object.
import { DatabaseSync } from "node:sqlite";
import type { Param, Sql } from "../../src/motor/sql";

function convertir(p: Param): string | number | null | Uint8Array {
  return p instanceof ArrayBuffer ? new Uint8Array(p) : p;
}

export function crearSqlNode(): Sql {
  const db = new DatabaseSync(":memory:");
  return {
    todos: <T>(q: string, ...p: Param[]) => db.prepare(q).all(...p.map(convertir)).map((f) => ({ ...f })) as T[],
    uno: <T>(q: string, ...p: Param[]) => {
      const f = db.prepare(q).get(...p.map(convertir));
      return f ? ({ ...f } as T) : undefined;
    },
    correr: (q: string, ...p: Param[]) => {
      db.prepare(q).run(...p.map(convertir));
    },
  };
}
