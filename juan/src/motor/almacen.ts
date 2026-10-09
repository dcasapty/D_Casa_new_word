// Memoria de trabajo de UNA conversación, en el SQLite del propio Durable Object.
// Odoo guarda el historial permanente; aquí solo vive lo necesario para contestar bien:
// los últimos mensajes, la ráfaga pendiente, una cola de escrituras a Odoo y archivos temporales.

import { bytesDeBlob, type Sql } from "./sql";

const ESQUEMA = [
  "CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT)",
  `CREATE TABLE IF NOT EXISTS mensajes (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     id_mensaje TEXT UNIQUE,
     rol TEXT NOT NULL,
     texto TEXT NOT NULL,
     adjuntos TEXT,
     ts INTEGER NOT NULL,
     pendiente INTEGER NOT NULL DEFAULT 0,
     modelo TEXT
   )`,
  "CREATE INDEX IF NOT EXISTS mensajes_ts ON mensajes(ts)",
  `CREATE TABLE IF NOT EXISTS cola (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     tipo TEXT NOT NULL,
     cuerpo TEXT NOT NULL,
     intentos INTEGER NOT NULL DEFAULT 0,
     proximo INTEGER NOT NULL,
     creado INTEGER NOT NULL
   )`,
  `CREATE TABLE IF NOT EXISTS medios (
     id TEXT NOT NULL,
     parte INTEGER NOT NULL,
     mime TEXT,
     nombre TEXT,
     datos BLOB,
     creado INTEGER NOT NULL,
     PRIMARY KEY (id, parte)
   )`,
  "CREATE TABLE IF NOT EXISTS fotos (codigo TEXT PRIMARY KEY, url TEXT NOT NULL, nombre TEXT, ts INTEGER NOT NULL)",
  "CREATE TABLE IF NOT EXISTS enviados (id TEXT PRIMARY KEY, ts INTEGER NOT NULL)",
  "CREATE TABLE IF NOT EXISTS seguimientos (clave TEXT PRIMARY KEY, ts INTEGER NOT NULL)",
];

export function crearEsquema(sql: Sql): void {
  for (const s of ESQUEMA) sql.correr(s);
}

export type Rol = "cliente" | "bot" | "vendedora";

export interface FilaMensaje {
  id: number;
  id_mensaje: string | null;
  rol: Rol;
  texto: string;
  adjuntos: string | null;
  ts: number;
  pendiente: number;
  modelo: string | null;
}

/** Valores sueltos de la conversación (identidad, estado, pausas, contadores). */
export class Kv {
  constructor(private readonly sql: Sql) {}

  texto(k: string): string | null {
    return this.sql.uno<{ v: string | null }>("SELECT v FROM kv WHERE k = ?", k)?.v ?? null;
  }
  numero(k: string): number | null {
    const v = this.texto(k);
    if (v === null || v === "") return null;
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }
  poner(k: string, v: string | number | boolean | null): void {
    if (v === null) {
      this.sql.correr("DELETE FROM kv WHERE k = ?", k);
      return;
    }
    this.sql.correr("INSERT INTO kv (k, v) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v", k, typeof v === "boolean" ? (v ? "1" : "0") : String(v));
  }
  bandera(k: string): boolean {
    return this.texto(k) === "1";
  }
  sumar(k: string, delta = 1): number {
    const n = (this.numero(k) ?? 0) + delta;
    this.poner(k, n);
    return n;
  }
}

export class Mensajes {
  constructor(private readonly sql: Sql) {}

  existe(idMensaje: string): boolean {
    return !!this.sql.uno("SELECT 1 AS x FROM mensajes WHERE id_mensaje = ?", idMensaje);
  }

  insertar(m: { id_mensaje: string | null; rol: Rol; texto: string; adjuntos?: unknown[]; ts: number; pendiente?: boolean; modelo?: string }): number {
    this.sql.correr(
      "INSERT INTO mensajes (id_mensaje, rol, texto, adjuntos, ts, pendiente, modelo) VALUES (?, ?, ?, ?, ?, ?, ?)",
      m.id_mensaje,
      m.rol,
      m.texto,
      m.adjuntos?.length ? JSON.stringify(m.adjuntos) : null,
      m.ts,
      m.pendiente ? 1 : 0,
      m.modelo ?? null,
    );
    return this.sql.uno<{ id: number }>("SELECT last_insert_rowid() AS id")!.id;
  }

  pendientes(): FilaMensaje[] {
    return this.sql.todos<FilaMensaje>("SELECT * FROM mensajes WHERE pendiente = 1 ORDER BY id");
  }

  marcarPendientes(ids: number[], valor: boolean): void {
    for (const id of ids) this.sql.correr("UPDATE mensajes SET pendiente = ? WHERE id = ?", valor ? 1 : 0, id);
  }

  limpiarPendientes(): void {
    this.sql.correr("UPDATE mensajes SET pendiente = 0 WHERE pendiente = 1");
  }

  /** Los últimos `n`, en orden cronológico. */
  ultimos(n: number): FilaMensaje[] {
    return this.sql.todos<FilaMensaje>("SELECT * FROM mensajes ORDER BY id DESC LIMIT ?", n).reverse();
  }

  /** Mensajes del cliente en las últimas 24 h (para el tope diario). */
  delClienteDesde(desde: number): number {
    return this.sql.uno<{ n: number }>("SELECT COUNT(*) AS n FROM mensajes WHERE rol = 'cliente' AND ts > ?", desde)?.n ?? 0;
  }

  /** Los textos de los últimos `n` mensajes del cliente (para detectar repetidos). */
  textosDelCliente(n: number): string[] {
    return this.sql.todos<{ texto: string }>("SELECT texto FROM mensajes WHERE rol = 'cliente' ORDER BY id DESC LIMIT ?", n).map((f) => f.texto);
  }

  /** Lo que dijeron el bot o una vendedora hace poco (para reconocer el eco de un mensaje propio). */
  salientesDesde(desde: number): string[] {
    return this.sql
      .todos<{ texto: string }>("SELECT texto FROM mensajes WHERE rol IN ('bot', 'vendedora') AND ts > ?", desde)
      .map((f) => f.texto);
  }

  hayDelNegocio(): boolean {
    return !!this.sql.uno("SELECT 1 AS x FROM mensajes WHERE rol IN ('bot', 'vendedora') LIMIT 1");
  }

  redactar(secreto: string, marca: string): void {
    if (secreto.length < 4) return;
    this.sql.correr("UPDATE mensajes SET texto = REPLACE(texto, ?, ?) WHERE rol = 'cliente' AND instr(texto, ?) > 0", secreto, marca, secreto);
  }

  purgar(antesDe: number, conservar: number): void {
    this.sql.correr(
      "DELETE FROM mensajes WHERE ts < ? AND id NOT IN (SELECT id FROM mensajes ORDER BY id DESC LIMIT ?)",
      antesDe,
      conservar,
    );
  }
}

export interface FilaCola {
  id: number;
  tipo: "mensaje" | "herramienta";
  cuerpo: string;
  intentos: number;
  proximo: number;
  creado: number;
}

export class Cola {
  constructor(private readonly sql: Sql) {}

  agregar(tipo: FilaCola["tipo"], cuerpo: unknown, ahora: number): void {
    this.sql.correr("INSERT INTO cola (tipo, cuerpo, intentos, proximo, creado) VALUES (?, ?, 0, ?, ?)", tipo, JSON.stringify(cuerpo), ahora, ahora);
  }
  vencidas(ahora: number): FilaCola[] {
    return this.sql.todos<FilaCola>("SELECT * FROM cola WHERE proximo <= ? ORDER BY id", ahora);
  }
  proxima(): number | null {
    return this.sql.uno<{ p: number | null }>("SELECT MIN(proximo) AS p FROM cola")?.p ?? null;
  }
  borrar(id: number): void {
    this.sql.correr("DELETE FROM cola WHERE id = ?", id);
  }
  reintentar(id: number, proximo: number): void {
    this.sql.correr("UPDATE cola SET intentos = intentos + 1, proximo = ? WHERE id = ?", proximo, id);
  }
  purgar(antesDe: number): void {
    this.sql.correr("DELETE FROM cola WHERE creado < ?", antesDe);
  }
}

/** Archivos que llegaron en bytes (base64 del puente, fotos de Telegram): viven unos días y se sirven con URL firmada. */
const PARTE = 900_000;
export const MEDIO_MAXIMO = 12 * 1024 * 1024;
export const MEDIO_VIDA_MS = 2 * 24 * 3600_000;

export class Medios {
  constructor(private readonly sql: Sql) {}

  guardar(id: string, bytes: Uint8Array, mime: string, nombre: string | undefined, ahora: number): void {
    if (bytes.byteLength > MEDIO_MAXIMO) throw new Error(`archivo demasiado grande (${bytes.byteLength} bytes)`);
    const partes = Math.max(1, Math.ceil(bytes.byteLength / PARTE));
    for (let i = 0; i < partes; i++) {
      this.sql.correr(
        "INSERT INTO medios (id, parte, mime, nombre, datos, creado) VALUES (?, ?, ?, ?, ?, ?)",
        id,
        i,
        mime,
        nombre ?? null,
        bytes.slice(i * PARTE, (i + 1) * PARTE),
        ahora,
      );
    }
  }

  leer(id: string, ahora: number): { bytes: Uint8Array; mime: string; nombre: string | null } | null {
    const filas = this.sql.todos<{ mime: string; nombre: string | null; datos: unknown; creado: number }>(
      "SELECT mime, nombre, datos, creado FROM medios WHERE id = ? ORDER BY parte",
      id,
    );
    if (filas.length === 0 || ahora - filas[0].creado > MEDIO_VIDA_MS) return null;
    const trozos = filas.map((f) => bytesDeBlob(f.datos));
    const bytes = new Uint8Array(trozos.reduce((n, t) => n + t.byteLength, 0));
    let i = 0;
    for (const t of trozos) {
      bytes.set(t, i);
      i += t.byteLength;
    }
    return { bytes, mime: filas[0].mime, nombre: filas[0].nombre };
  }

  purgar(antesDe: number): void {
    this.sql.correr("DELETE FROM medios WHERE creado < ?", antesDe);
  }
}

export class Fotos {
  constructor(private readonly sql: Sql) {}
  guardar(codigo: string, url: string, nombre: string | undefined, ts: number): void {
    this.sql.correr(
      "INSERT INTO fotos (codigo, url, nombre, ts) VALUES (?, ?, ?, ?) ON CONFLICT(codigo) DO UPDATE SET url = excluded.url, nombre = excluded.nombre, ts = excluded.ts",
      codigo,
      url,
      nombre ?? null,
      ts,
    );
  }
  buscar(codigo: string): { url: string; nombre: string | null } | undefined {
    return this.sql.uno<{ url: string; nombre: string | null }>("SELECT url, nombre FROM fotos WHERE codigo = ?", codigo);
  }
  purgar(antesDe: number): void {
    this.sql.correr("DELETE FROM fotos WHERE ts < ?", antesDe);
  }
}
