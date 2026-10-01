import type { Fila, Sql, Valor } from "./nucleo/sql";

/** Adaptador del SQLite del Durable Object al `Sql` del núcleo. */
export function sqlDeDurableObject(storage: DurableObjectStorage): Sql {
  return {
    ejecutar(consulta: string, ...p: Valor[]): Fila[] {
      return storage.sql.exec(consulta, ...p).toArray() as Fila[];
    },
  };
}
