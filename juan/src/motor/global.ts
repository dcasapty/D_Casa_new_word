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
  porModelo: { modelo: string; usd: number; turnos: number; estimado: boolean }[];
  /** Modelos cuyo costo se estimó porque no tenían precio cargado en Odoo. */
  modelosSinPrecio: string[];
}

/** La lógica, sin Cloudflare: se prueba con SQLite de Node. */
export class AlmacenGlobal {
  constructor(private readonly sql: Sql) {
    sql.correr(`CREATE TABLE IF NOT EXISTS gasto (
      mes TEXT NOT NULL, modelo TEXT NOT NULL,
      entrada INTEGER NOT NULL DEFAULT 0, cache_lectura INTEGER NOT NULL DEFAULT 0,
      cache_escritura INTEGER NOT NULL DEFAULT 0, salida INTEGER NOT NULL DEFAULT 0,
      usd REAL NOT NULL DEFAULT 0, turnos INTEGER NOT NULL DEFAULT 0,
      estimado INTEGER NOT NULL DEFAULT 0,
      PRIMARY KEY (mes, modelo))`);
    // El gasto de cada día (en la hora del negocio), sumado de todos los modelos: para la gráfica de Costos de IA.
    sql.correr("CREATE TABLE IF NOT EXISTS gasto_dia (dia TEXT PRIMARY KEY, usd REAL NOT NULL DEFAULT 0, turnos INTEGER NOT NULL DEFAULT 0)");
    sql.correr("CREATE TABLE IF NOT EXISTS salud (clave TEXT PRIMARY KEY, valor TEXT NOT NULL, ts INTEGER NOT NULL)");
    // Las llaves que Juan renueva solo (hoy, la de Instagram por inicio de sesión de Instagram: canales/instagramLlave.ts). Aparte de
    // `salud` a propósito: ninguna ruta ni informe las lee de aquí.
    sql.correr("CREATE TABLE IF NOT EXISTS llaves (clave TEXT PRIMARY KEY, valor TEXT NOT NULL, ts INTEGER NOT NULL)");
    // Las respuestas PÚBLICAS a comentarios de la última hora (solo la hora: ni quién ni qué), para el tope por hora de Ajustes.
    sql.correr("CREATE TABLE IF NOT EXISTS respuestas_publicas (id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER NOT NULL)");
    // Lo mismo con las PRIVADAS (cada una es un turno completo de IA): el tope global por hora, entre todas las cuentas.
    sql.correr("CREATE TABLE IF NOT EXISTS respuestas_privadas (id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER NOT NULL)");
    crearTablasDeLaTienda(sql);
  }

  /**
   * Aparta un lugar para UNA respuesta pública a un comentario si en la última hora van menos de `tope` (entre todas las
   * conversaciones). Sin esperas en medio: dentro del Durable Object es atómico, dos comentarios a la vez no se pasan del tope.
   */
  reservarRespuestaPublica(tope: number, ahora: number): boolean {
    return this.reservar("respuestas_publicas", tope, ahora);
  }

  /** Lo mismo con las respuestas PRIVADAS a comentarios (el tope global por hora). */
  reservarRespuestaPrivada(tope: number, ahora: number): boolean {
    return this.reservar("respuestas_privadas", tope, ahora);
  }

  private reservar(tabla: "respuestas_publicas" | "respuestas_privadas", tope: number, ahora: number): boolean {
    this.sql.correr(`DELETE FROM ${tabla} WHERE ts <= ?`, ahora - 3600_000);
    const n = this.sql.uno<{ n: number }>(`SELECT COUNT(*) AS n FROM ${tabla}`)?.n ?? 0;
    if (n >= tope) return false;
    this.sql.correr(`INSERT INTO ${tabla} (ts) VALUES (?)`, ahora);
    return true;
  }

  registrarGasto(mes: string, modelo: string, uso: Uso, usd: number, estimado = false, dia?: string): void {
    if (dia) {
      this.sql.correr(
        "INSERT INTO gasto_dia (dia, usd, turnos) VALUES (?, ?, 1) ON CONFLICT(dia) DO UPDATE SET usd = usd + excluded.usd, turnos = turnos + 1",
        dia,
        usd,
      );
    }
    this.sql.correr(
      `INSERT INTO gasto (mes, modelo, entrada, cache_lectura, cache_escritura, salida, usd, turnos, estimado)
       VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
       ON CONFLICT(mes, modelo) DO UPDATE SET
         entrada = entrada + excluded.entrada, cache_lectura = cache_lectura + excluded.cache_lectura,
         cache_escritura = cache_escritura + excluded.cache_escritura, salida = salida + excluded.salida,
         usd = usd + excluded.usd, turnos = turnos + 1, estimado = MAX(estimado, excluded.estimado)`,
      mes,
      modelo,
      uso.entrada,
      uso.cacheLectura,
      uso.cacheEscritura,
      uso.salida,
      usd,
      estimado ? 1 : 0,
    );
  }

  gastoMes(mes: string): GastoDelMes {
    const filas = this.sql.todos<{ modelo: string; usd: number; turnos: number; estimado: number }>("SELECT modelo, usd, turnos, estimado FROM gasto WHERE mes = ?", mes);
    return {
      mes,
      usd: filas.reduce((n, f) => n + f.usd, 0),
      turnos: filas.reduce((n, f) => n + f.turnos, 0),
      porModelo: filas.map((f) => ({ ...f, estimado: f.estimado === 1 })),
      modelosSinPrecio: filas.filter((f) => f.estimado === 1).map((f) => f.modelo),
    };
  }

  /** Gasto de cada día del mes («AAAA-MM»), del más viejo al más nuevo. Solo existen los días desde que se guarda por día. */
  gastoPorDia(mes: string): { dia: string; usd: number; turnos: number }[] {
    return this.sql.todos<{ dia: string; usd: number; turnos: number }>("SELECT dia, usd, turnos FROM gasto_dia WHERE dia LIKE ? ORDER BY dia", `${mes}-%`);
  }

  guardarSalud(clave: string, valor: unknown, ahora: number): void {
    this.sql.correr(
      "INSERT INTO salud (clave, valor, ts) VALUES (?, ?, ?) ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor, ts = excluded.ts",
      clave,
      JSON.stringify(valor),
      ahora,
    );
  }

  /** Cambia la llave solo si sigue valiendo `antes` (null = no existía). Sin esperas en medio: dentro del Durable Object es atómico. */
  cambiarLlaveSi(clave: string, antes: string | null, despues: string, ahora: number): boolean {
    if (this.leerLlave(clave) !== antes) return false;
    this.sql.correr(
      "INSERT INTO llaves (clave, valor, ts) VALUES (?, ?, ?) ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor, ts = excluded.ts",
      clave,
      despues,
      ahora,
    );
    return true;
  }

  leerLlave(clave: string): string | null {
    return this.sql.uno<{ valor: string }>("SELECT valor FROM llaves WHERE clave = ?", clave)?.valor ?? null;
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

// ── Brian de la tienda (docs/JUAN.md › «Brian de la tienda») ──────────────────
//
// Sus topes de red y del día y su presupuesto propio viven aquí porque son de TODOS los visitantes: este objeto es uno solo y atiende
// de a una petición, así que «contar y apartar» sin esperas en medio es atómico (dos mensajes a la vez no se pasan del tope).
// Su gasto va en su PROPIA tabla: nunca suma en `gasto` (el de Juan: su tope, «Por pagar a Meta» y los cortes de Odoo).

/** Lo que se aparta para un turno de la tienda: vence solo si el Worker se cae a la mitad (no queda dinero «apartado» para siempre). */
export const VIDA_DE_UNA_RESERVA_MS = 3 * 60_000;
const VIDA_DE_UN_TURNO_DE_LA_TIENDA_MS = 26 * 3600_000;

export interface ReservaTienda {
  /** La red del visitante ya ofuscada (HMAC): aquí nunca llega la IP ni la red en claro. */
  red: string;
  /** «AAAA-MM-DD» y «AAAA-MM», en la hora de Panamá. */
  dia: string;
  mes: string;
  porRed: number;
  porDia: number;
  presupuestoUsd: number;
  /** Lo que puede costar este turno (0 si no llama a la IA). */
  reservaUsd: number;
}

export type ResultadoReservaTienda = { ok: true; id: number } | { ok: false; motivo: "tope_red" | "tope_dia" | "presupuesto" };

export interface GastoTienda {
  mes: string;
  proveedor: string;
  modelo: string;
  uso: Uso;
  usd: number;
  estimado: boolean;
}

export interface GastoTiendaDelMes {
  mes: string;
  usd: number;
  turnos: number;
  porModelo: { proveedor: string; modelo: string; usd: number; turnos: number; estimado: boolean }[];
  /** Lo apartado por turnos que todavía corren. */
  enVueloUsd: number;
  /** Mensajes atendidos hoy (todos, con IA o sin ella). */
  turnosHoy: number;
}

function crearTablasDeLaTienda(sql: Sql): void {
  // Cada mensaje aceptado (con o sin IA): la hora, el día, la red ofuscada y lo apartado. Se borran a las 26 horas.
  sql.correr(`CREATE TABLE IF NOT EXISTS tienda_turnos (id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER NOT NULL, dia TEXT NOT NULL,
    red TEXT NOT NULL, reserva REAL NOT NULL DEFAULT 0, vence INTEGER NOT NULL DEFAULT 0)`);
  sql.correr(`CREATE TABLE IF NOT EXISTS tienda_gasto (
    mes TEXT NOT NULL, proveedor TEXT NOT NULL, modelo TEXT NOT NULL,
    entrada INTEGER NOT NULL DEFAULT 0, cache_lectura INTEGER NOT NULL DEFAULT 0,
    cache_escritura INTEGER NOT NULL DEFAULT 0, salida INTEGER NOT NULL DEFAULT 0,
    usd REAL NOT NULL DEFAULT 0, turnos INTEGER NOT NULL DEFAULT 0, estimado INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (mes, proveedor, modelo))`);
}

/** Los topes y el presupuesto de la tienda, sin Cloudflare (se prueba con SQLite de Node). */
export class TopesDeLaTienda {
  constructor(private readonly sql: Sql) {
    crearTablasDeLaTienda(sql);
  }

  /**
   * Cuenta y aparta UN mensaje si cabe en el tope por red (última hora), en el del día y en el presupuesto del mes (lo gastado más
   * lo apartado por los turnos en curso más lo que puede costar este). Todo sin esperas en medio: es atómico dentro del objeto.
   */
  reservar(p: ReservaTienda, ahora: number): ResultadoReservaTienda {
    this.sql.correr("DELETE FROM tienda_turnos WHERE ts < ?", ahora - VIDA_DE_UN_TURNO_DE_LA_TIENDA_MS);
    const porRed = this.sql.uno<{ n: number }>("SELECT COUNT(*) AS n FROM tienda_turnos WHERE red = ? AND ts > ?", p.red, ahora - 3600_000)?.n ?? 0;
    if (porRed >= p.porRed) return { ok: false, motivo: "tope_red" };
    const delDia = this.sql.uno<{ n: number }>("SELECT COUNT(*) AS n FROM tienda_turnos WHERE dia = ?", p.dia)?.n ?? 0;
    if (delDia >= p.porDia) return { ok: false, motivo: "tope_dia" };
    // El presupuesto solo frena lo que gasta: un turno sin IA (reserva 0: pedir una persona, calificar…) pasa aunque esté agotado.
    const reserva = Math.max(0, p.reservaUsd);
    if (reserva > 0) {
      const gastado = this.gastado(p.mes);
      const enVuelo = this.enVuelo(ahora);
      if (gastado + enVuelo + reserva > Math.max(0, p.presupuestoUsd) + 1e-9) return { ok: false, motivo: "presupuesto" };
    }
    this.sql.correr("INSERT INTO tienda_turnos (ts, dia, red, reserva, vence) VALUES (?, ?, ?, ?, ?)", ahora, p.dia, p.red, reserva, ahora + VIDA_DE_UNA_RESERVA_MS);
    const id = this.sql.uno<{ id: number }>("SELECT last_insert_rowid() AS id")?.id ?? 0;
    return { ok: true, id };
  }

  /** El turno terminó: suelta lo apartado y anota lo que de verdad costó (cada modelo con su proveedor, en su propio renglón). */
  cerrar(id: number, gastos: readonly GastoTienda[]): void {
    this.sql.correr("UPDATE tienda_turnos SET reserva = 0, vence = 0 WHERE id = ?", id);
    for (const g of gastos) {
      if (!(g.usd >= 0) || !Number.isFinite(g.usd)) continue;
      this.sql.correr(
        `INSERT INTO tienda_gasto (mes, proveedor, modelo, entrada, cache_lectura, cache_escritura, salida, usd, turnos, estimado)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
         ON CONFLICT(mes, proveedor, modelo) DO UPDATE SET
           entrada = entrada + excluded.entrada, cache_lectura = cache_lectura + excluded.cache_lectura,
           cache_escritura = cache_escritura + excluded.cache_escritura, salida = salida + excluded.salida,
           usd = usd + excluded.usd, turnos = turnos + 1, estimado = MAX(estimado, excluded.estimado)`,
        g.mes,
        g.proveedor,
        g.modelo,
        g.uso.entrada,
        g.uso.cacheLectura,
        g.uso.cacheEscritura,
        g.uso.salida,
        g.usd,
        g.estimado ? 1 : 0,
      );
    }
  }

  gastoMes(mes: string, dia: string, ahora: number): GastoTiendaDelMes {
    const filas = this.sql.todos<{ proveedor: string; modelo: string; usd: number; turnos: number; estimado: number }>(
      "SELECT proveedor, modelo, usd, turnos, estimado FROM tienda_gasto WHERE mes = ? ORDER BY usd DESC",
      mes,
    );
    return {
      mes,
      usd: filas.reduce((n, f) => n + f.usd, 0),
      turnos: filas.reduce((n, f) => n + f.turnos, 0),
      porModelo: filas.map((f) => ({ ...f, estimado: f.estimado === 1 })),
      enVueloUsd: this.enVuelo(ahora),
      turnosHoy: this.sql.uno<{ n: number }>("SELECT COUNT(*) AS n FROM tienda_turnos WHERE dia = ?", dia)?.n ?? 0,
    };
  }

  private gastado(mes: string): number {
    return this.sql.uno<{ usd: number | null }>("SELECT SUM(usd) AS usd FROM tienda_gasto WHERE mes = ?", mes)?.usd ?? 0;
  }

  private enVuelo(ahora: number): number {
    return this.sql.uno<{ usd: number | null }>("SELECT SUM(reserva) AS usd FROM tienda_turnos WHERE vence > ?", ahora)?.usd ?? 0;
  }
}

export class Global extends DurableObject<Env> {
  private readonly almacen: AlmacenGlobal;
  private readonly tienda: TopesDeLaTienda;

  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env);
    const sql = sqlDeDurableObject(ctx.storage.sql);
    this.almacen = new AlmacenGlobal(sql);
    this.tienda = new TopesDeLaTienda(sql);
  }

  /** Brian de la tienda: cuenta y aparta un mensaje (topes de red y del día, presupuesto propio). */
  reservarTurnoTienda(p: ReservaTienda): ResultadoReservaTienda {
    return this.tienda.reservar(p, Date.now());
  }

  /** Brian de la tienda: suelta lo apartado y anota lo que costó, en su propia tabla. */
  cerrarTurnoTienda(id: number, gastos: GastoTienda[]): void {
    this.tienda.cerrar(id, gastos);
  }

  gastoTienda(mes: string, dia: string): GastoTiendaDelMes {
    return this.tienda.gastoMes(mes, dia, Date.now());
  }

  registrarGasto(mes: string, modelo: string, uso: Uso, usd: number, estimado: boolean, dia?: string): void {
    this.almacen.registrarGasto(mes, modelo, uso, usd, estimado, dia);
  }

  gastoMes(mes: string): GastoDelMes {
    return this.almacen.gastoMes(mes);
  }

  gastoPorDia(mes: string): { dia: string; usd: number; turnos: number }[] {
    return this.almacen.gastoPorDia(mes);
  }

  /** Los valores viajan como texto JSON: los tipos de RPC de Cloudflare no se llevan bien con `unknown` ni `any`. */
  guardarSalud(clave: string, json: string): void {
    this.almacen.guardarSalud(clave, JSON.parse(json), Date.now());
  }

  leerSalud(clave: string): { json: string; ts: number } | null {
    const f = this.almacen.leerSalud(clave);
    return f ? { json: JSON.stringify(f.valor), ts: f.ts } : null;
  }

  /**
   * Una llave que Juan renueva solo (texto JSON), cambiada solo si nadie la cambió desde que se leyó (dos renovaciones a la vez no se
   * pisan). Solo la usan los adaptadores; jamás sale por una ruta.
   */
  cambiarLlaveSi(clave: string, antes: string | null, despues: string): boolean {
    return this.almacen.cambiarLlaveSi(clave, antes, despues, Date.now());
  }

  leerLlave(clave: string): string | null {
    return this.almacen.leerLlave(clave);
  }

  /** El tope por hora de las respuestas públicas a comentarios (Ajustes de Juan › Comentarios). */
  reservarRespuestaPublica(tope: number): boolean {
    return this.almacen.reservarRespuestaPublica(tope, Date.now());
  }

  /** El tope global por hora de las respuestas privadas a comentarios. */
  reservarRespuestaPrivada(tope: number): boolean {
    return this.almacen.reservarRespuestaPrivada(tope, Date.now());
  }
}
