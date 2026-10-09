// Puerta mínima a SQLite. En producción es `ctx.storage.sql` del Durable Object; en las
// pruebas es `node:sqlite`. El motor no sabe cuál de los dos tiene debajo.

export type Param = string | number | null | Uint8Array | ArrayBuffer;

export interface Sql {
  /** Todas las filas. */
  todos<T = Record<string, unknown>>(consulta: string, ...params: Param[]): T[];
  /** La primera fila, o undefined. */
  uno<T = Record<string, unknown>>(consulta: string, ...params: Param[]): T | undefined;
  /** Ejecuta sin devolver filas (INSERT, UPDATE, DELETE, DDL). */
  correr(consulta: string, ...params: Param[]): void;
}

/** Lo poco que usamos de `ctx.storage.sql` (SqlStorage). */
export interface SqlStorageLike {
  exec(consulta: string, ...bindings: unknown[]): { toArray(): Record<string, unknown>[] };
}

/** SqlStorage solo acepta ArrayBuffer para los BLOB: una vista (Uint8Array) se copia a un ArrayBuffer exacto. */
function paraDurableObject(p: Param): unknown {
  if (p instanceof Uint8Array) return p.buffer.slice(p.byteOffset, p.byteOffset + p.byteLength);
  return p;
}

export function sqlDeDurableObject(almacen: SqlStorageLike): Sql {
  const filas = (q: string, p: Param[]) => almacen.exec(q, ...p.map(paraDurableObject)).toArray();
  return {
    todos: <T>(q: string, ...p: Param[]) => filas(q, p) as T[],
    uno: <T>(q: string, ...p: Param[]) => filas(q, p)[0] as T | undefined,
    correr: (q, ...p) => {
      filas(q, p);
    },
  };
}

/** Bytes de una columna BLOB, venga de workerd (ArrayBuffer) o de node:sqlite (Uint8Array). */
export function bytesDeBlob(v: unknown): Uint8Array {
  if (v instanceof Uint8Array) return v;
  if (v instanceof ArrayBuffer) return new Uint8Array(v);
  return new Uint8Array(0);
}
