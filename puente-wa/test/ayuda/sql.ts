// Un SQLite de verdad (el de Node) con la forma de `SqlStorage` de Cloudflare, para probar el
// almacén sin Workers. `exec` devuelve algo con `toArray()`; `transaccion` hace BEGIN/COMMIT.
import { DatabaseSync } from "node:sqlite";
import type { SqlLike } from "../../src/almacen";

export function sqlDePrueba() {
  const db = new DatabaseSync(":memory:");
  const sql: SqlLike = {
    exec(consulta, ...enlaces) {
      const stmt = db.prepare(consulta);
      const filas = /^\s*(select|pragma|with)/i.test(consulta)
        ? (stmt.all(...(enlaces as any[])) as Record<string, any>[])
        : (stmt.run(...(enlaces as any[])), []);
      return { toArray: () => filas };
    },
  };
  let enTransaccion = false;
  return {
    sql,
    db,
    transaccion<T>(fn: () => T): T {
      // `transactionSync` de Cloudflare no se anida: si ya hay una, se sigue dentro de ella.
      if (enTransaccion) return fn();
      db.exec("BEGIN");
      enTransaccion = true;
      try {
        const r = fn();
        db.exec("COMMIT");
        return r;
      } catch (e) {
        db.exec("ROLLBACK");
        throw e;
      } finally {
        enTransaccion = false;
      }
    },
    /** Todo el contenido de una tabla como texto: para comprobar que NADA está en claro. */
    volcado(tabla: string): string {
      return JSON.stringify(db.prepare(`SELECT * FROM ${tabla}`).all());
    },
  };
}
