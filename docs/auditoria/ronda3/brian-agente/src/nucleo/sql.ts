/**
 * SQL mínimo común: en el Durable Object es `ctx.storage.sql.exec(q, ...p).toArray()`;
 * en los tests, `node:sqlite`. Así el MISMO SQL se prueba fuera de Cloudflare.
 */
export type Valor = string | number | null;
export type Fila = Record<string, Valor>;

export interface Sql {
  ejecutar(consulta: string, ...parametros: Valor[]): Fila[];
}

export function esquema(sql: Sql): void {
  sql.ejecutar(`CREATE TABLE IF NOT EXISTS mensajes (
    n INTEGER PRIMARY KEY AUTOINCREMENT, json TEXT NOT NULL)`);
  // Libro de uso: solo se INSERTA. No hay UPDATE ni DELETE en el código (regla 2-3 de CLAUDE.md aplicada a tokens).
  sql.ejecutar(`CREATE TABLE IF NOT EXISTS uso (
    id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT NOT NULL, mes TEXT NOT NULL,
    persona TEXT NOT NULL, rol TEXT NOT NULL, conversacion TEXT NOT NULL,
    proveedor TEXT NOT NULL, modelo TEXT NOT NULL,
    entrada INTEGER NOT NULL, salida INTEGER NOT NULL,
    cache_lectura INTEGER NOT NULL, cache_escritura INTEGER NOT NULL,
    costo_micro INTEGER NOT NULL, version_precios TEXT NOT NULL)`);
  // Idempotencia: un id de llamada de herramienta se ejecuta una sola vez.
  sql.ejecutar(`CREATE TABLE IF NOT EXISTS resultados (
    llamada_id TEXT PRIMARY KEY, herramienta TEXT NOT NULL, json TEXT NOT NULL, fecha TEXT NOT NULL)`);
  sql.ejecutar(`CREATE TABLE IF NOT EXISTS pendientes (
    id TEXT PRIMARY KEY, llamada_id TEXT NOT NULL UNIQUE, herramienta TEXT NOT NULL,
    argumentos TEXT NOT NULL, resumen TEXT NOT NULL, persona TEXT NOT NULL,
    creada INTEGER NOT NULL, vence INTEGER NOT NULL, estado TEXT NOT NULL)`);
  sql.ejecutar(`CREATE TABLE IF NOT EXISTS ajustes (clave TEXT PRIMARY KEY, valor TEXT NOT NULL)`);
}
