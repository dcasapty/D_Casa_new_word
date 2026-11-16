// El único Durable Object "de todos": cuánto se ha gastado en IA este mes y el último estado de salud.
// (Cada conversación vive en su propio Durable Object; esto es lo que no pertenece a ninguna.)

import { DurableObject } from "cloudflare:workers";
import type { Env } from "../env";
import { sqlDeDurableObject, type Sql } from "./sql";
import type { Uso } from "./precios";
import { TIENDA_POR_DEFECTO } from "../config";

export interface GastoDelMes {
  mes: string;
  /** Lo de los modelos que contestan (Meta, Claude, OpenAI): el tope del mes, el saldo con Meta y los turnos. */
  usd: number;
  turnos: number;
  porModelo: { modelo: string; usd: number; turnos: number; estimado: boolean }[];
  /** Modelos cuyo costo se estimó porque no tenían precio cargado en Odoo. */
  modelosSinPrecio: string[];
  /**
   * Lo que cobra Cloudflare (Workers AI), APARTE: «Busca con una foto» (`cloudflare:lector-de-fotos`) y cualquier `@cf/…`.
   * No suma en `usd`, `turnos` ni en el gasto por día: no es deuda con Meta ni una respuesta de Juan.
   */
  cloudflare: { concepto: string; usd: number; lecturas: number; estimado: boolean }[];
}

/** ¿Es algo que cobra Cloudflare (Workers AI) y no un modelo que contesta? */
export const esDeCloudflare = (modelo: string) => modelo.startsWith("cloudflare:") || modelo.startsWith("@cf/");

/** Una nota de voz de Brian del panel (odoo-panel-voz.ts): quién (ofuscado), cuándo y sus topes. */
export interface ReservaVozPanel {
  /** El usuario de Odoo, ya ofuscado (HMAC con el token del Worker). */
  usuario: string;
  /** «AAAA-MM-DD» y «AAAA-MM», en la hora de Panamá. */
  dia: string;
  mes: string;
  porUsuarioHora: number;
  porDia: number;
  /** Lo más que pueden costar las notas del panel en el mes (USD), en el renglón `concepto` de `gasto`. */
  topeMesUsd: number;
  concepto: string;
}

export type ResultadoReservaVozPanel = { ok: true } | { ok: false; motivo: "tope_usuario" | "tope_dia" | "tope_mes"; reintentarEn?: number };

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
    // Las notas de voz de Brian del panel (odoo-panel-voz.ts): solo la hora, el día y el usuario de Odoo ofuscado, para sus topes.
    // Nunca el audio ni el texto. Se borran a las 26 horas.
    sql.correr("CREATE TABLE IF NOT EXISTS voz_panel (id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER NOT NULL, dia TEXT NOT NULL, usuario TEXT NOT NULL)");
    crearTablasDeLaTienda(sql);
  }

  /**
   * Brian del panel: aparta UNA nota de voz si el usuario no pasó su tope por hora, el panel el suyo del día y lo de las notas en el
   * mes (`concepto` en `gasto`) no llegó a su techo. Sin esperas en medio: atómico dentro del objeto.
   */
  reservarVozPanel(p: ReservaVozPanel, ahora: number): ResultadoReservaVozPanel {
    this.sql.correr("DELETE FROM voz_panel WHERE ts < ?", ahora - 26 * 3600_000);
    const n = (consulta: string, ...params: (string | number)[]) => this.sql.uno<{ n: number }>(consulta, ...params)?.n ?? 0;
    const delUsuario = this.sql.todos<{ ts: number }>("SELECT ts FROM voz_panel WHERE usuario = ? AND ts > ? ORDER BY ts", p.usuario, ahora - 3600_000);
    if (delUsuario.length >= p.porUsuarioHora) {
      return { ok: false, motivo: "tope_usuario", reintentarEn: Math.max(1, Math.ceil((delUsuario[0].ts + 3600_000 - ahora) / 1000)) };
    }
    if (n("SELECT COUNT(*) AS n FROM voz_panel WHERE dia = ?", p.dia) >= p.porDia) return { ok: false, motivo: "tope_dia" };
    const gastado = this.sql.uno<{ usd: number | null }>("SELECT usd FROM gasto WHERE mes = ? AND modelo = ?", p.mes, p.concepto)?.usd ?? 0;
    if (p.topeMesUsd <= 0 || gastado >= p.topeMesUsd) return { ok: false, motivo: "tope_mes" };
    this.sql.correr("INSERT INTO voz_panel (ts, dia, usuario) VALUES (?, ?, ?)", ahora, p.dia, p.usuario);
    return { ok: true };
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
    // Lo de Cloudflare no entra en la gráfica por día (es la de Meta: la pantalla la arma con el acumulado del mes).
    if (dia && !esDeCloudflare(modelo)) {
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
    const todas = this.sql.todos<{ modelo: string; usd: number; turnos: number; estimado: number }>("SELECT modelo, usd, turnos, estimado FROM gasto WHERE mes = ?", mes);
    const filas = todas.filter((f) => !esDeCloudflare(f.modelo));
    return {
      mes,
      usd: filas.reduce((n, f) => n + f.usd, 0),
      turnos: filas.reduce((n, f) => n + f.turnos, 0),
      porModelo: filas.map((f) => ({ ...f, estimado: f.estimado === 1 })),
      modelosSinPrecio: filas.filter((f) => f.estimado === 1).map((f) => f.modelo),
      cloudflare: todas.filter((f) => esDeCloudflare(f.modelo)).map((f) => ({ concepto: f.modelo, usd: f.usd, lecturas: f.turnos, estimado: f.estimado === 1 })),
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

/**
 * Lo que se aparta para un turno de la tienda vence a los 3 minutos. Si para entonces nadie cerró el turno (el Worker se cayó, o el
 * cierre falló), lo apartado pasa a ser GASTO estimado (`liquidarVencidas`): no se suelta como si no hubiera costado nada.
 */
export const VIDA_DE_UNA_RESERVA_MS = 3 * 60_000;
/** El renglón del gasto de la tienda para lo que se cobró sin poder medirse (un turno cortado, o una reserva que nadie cerró). */
export const MODELO_DE_LO_CORTADO = "turnos cortados (estimado)";
/** Marca de una reserva que ya pasó a gasto estimado: si el cierre llega tarde, no se cuenta dos veces. */
const LIQUIDADA = -1;
const VIDA_DE_UN_TURNO_DE_LA_TIENDA_MS = 26 * 3600_000;

export interface ReservaTienda {
  /** La red del visitante ya ofuscada (HMAC): aquí nunca llega la IP ni la red en claro. */
  red: string;
  /** La /48 de una IPv6, también ofuscada (null con IPv4): muchas /64 de la misma /48 no saltan el tope por red. */
  red48?: string | null;
  /** «AAAA-MM-DD» y «AAAA-MM», en la hora de Panamá. */
  dia: string;
  mes: string;
  /** Por hora por red. */
  porRed: number;
  /** Por día entre todos. */
  porDia: number;
  /** Por día por red (sin él, el de fábrica: una sola IP no se lleva el tope del día de todos). */
  porRedDia?: number;
  /** Por hora por /48 (sin él, 3 × el de por red). */
  porRed48?: number;
  /** Por día por /48 (sin él, 3 × el de por red y por día). */
  porRed48Dia?: number;
  /** Turnos con IA a la vez, entre todos (sin él, el de fábrica). */
  enVueloMax?: number;
  /** La parte justa de cada red en los turnos a la vez (sin él, el de fábrica): más que eso nunca deja fuera a otra red. */
  enVueloRed?: number;
  /** El proveedor de la IA del turno: si la reserva vence sin cerrarse, su gasto estimado va con él. */
  proveedor?: string;
  presupuestoUsd: number;
  /** Lo que puede costar este turno (0 si no llama a la IA). */
  reservaUsd: number;
}

/**
 * Las notas de voz de Andrés (tienda/voz.ts): su costo va en el gasto de la tienda con este renglón y este proveedor (lo cobra
 * Cloudflare, no Meta: nunca entra en «Por pagar a Meta»). No suman en las «respuestas» del mes.
 */
export const MODELO_DE_LA_VOZ = "notas de voz (Whisper)";
export const PROVEEDOR_DE_LA_VOZ = "cloudflare";

/** Una nota de voz de la tienda: cuenta como un mensaje en los topes de red y del día y en el presupuesto, más su tope por sesión. */
export interface ReservaVozTienda extends ReservaTienda {
  /** El `sid` del pase, ofuscado (HMAC con el token del Worker). */
  sesion: string;
  /** Notas de voz por hora por sesión. */
  porSesion: number;
}

/** «ocupado»: ya hay demasiados turnos con IA a la vez (no es un tope del visitante: en un momento vuelve a poder). */
export type ResultadoReservaTienda = { ok: true; id: number } | { ok: false; motivo: "tope_red" | "tope_dia" | "presupuesto" | "ocupado" };
export type ResultadoReservaVozTienda = ResultadoReservaTienda | { ok: false; motivo: "tope_sesion"; reintentarEn: number };

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
  // La /48 de IPv6 (2026-11-14). Una tabla que ya existía sin la columna la recibe aquí (si ya la tiene, SQLite se queja y no pasa nada).
  for (const columna of ["red48 TEXT", "proveedor TEXT"]) {
    try {
      sql.correr(`ALTER TABLE tienda_turnos ADD COLUMN ${columna}`);
    } catch {
      /* ya estaba */
    }
  }
  // Las notas de voz de cada sesión (solo la hora y el `sid` ofuscado: nunca el audio ni el texto), para su tope por hora.
  sql.correr("CREATE TABLE IF NOT EXISTS tienda_voz (id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER NOT NULL, sesion TEXT NOT NULL)");
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
    // Primero lo vencido sin cerrar pasa a gasto (antes de borrar lo viejo, para que nada se pierda).
    this.liquidarVencidas(ahora);
    this.sql.correr("DELETE FROM tienda_turnos WHERE ts < ?", ahora - VIDA_DE_UN_TURNO_DE_LA_TIENDA_MS);
    const n = (consulta: string, ...params: (string | number)[]) => this.sql.uno<{ n: number }>(consulta, ...params)?.n ?? 0;
    const haceUnaHora = ahora - 3600_000;
    if (n("SELECT COUNT(*) AS n FROM tienda_turnos WHERE red = ? AND ts > ?", p.red, haceUnaHora) >= p.porRed) return { ok: false, motivo: "tope_red" };
    // Una sola red no se lleva el tope del día de todos (60 por hora serían 1440 al día, más que los 1000 del día).
    const porRedDia = p.porRedDia ?? TIENDA_POR_DEFECTO.tope_red_dia;
    if (n("SELECT COUNT(*) AS n FROM tienda_turnos WHERE red = ? AND dia = ?", p.red, p.dia) >= porRedDia) return { ok: false, motivo: "tope_red" };
    // Con IPv6, una /48 tiene 65 536 redes /64: juntas no pasan de estos topes, por hora y por día (cambiando de /64 cada 45
    // mensajes, una sola /48 juntaba los 1000 del día en unas 5 horas y media).
    if (p.red48) {
      if (n("SELECT COUNT(*) AS n FROM tienda_turnos WHERE red48 = ? AND ts > ?", p.red48, haceUnaHora) >= (p.porRed48 ?? p.porRed * 3)) return { ok: false, motivo: "tope_red" };
      if (n("SELECT COUNT(*) AS n FROM tienda_turnos WHERE red48 = ? AND dia = ?", p.red48, p.dia) >= (p.porRed48Dia ?? porRedDia * 3)) return { ok: false, motivo: "tope_red" };
    }
    if (n("SELECT COUNT(*) AS n FROM tienda_turnos WHERE dia = ?", p.dia) >= p.porDia) return { ok: false, motivo: "tope_dia" };
    // El presupuesto y el tope de turnos a la vez solo frenan lo que usa la IA: un turno sin IA (reserva 0: pedir una persona,
    // calificar…) pasa aunque estén llenos.
    const reserva = Math.max(0, p.reservaUsd);
    if (reserva > 0) {
      if (this.ocupado(p, ahora)) return { ok: false, motivo: "ocupado" };
      const gastado = this.gastado(p.mes);
      const enVuelo = this.enVuelo(ahora);
      if (gastado + enVuelo + reserva > Math.max(0, p.presupuestoUsd) + 1e-9) return { ok: false, motivo: "presupuesto" };
    }
    this.sql.correr(
      "INSERT INTO tienda_turnos (ts, dia, red, red48, reserva, vence, proveedor) VALUES (?, ?, ?, ?, ?, ?, ?)",
      ahora,
      p.dia,
      p.red,
      p.red48 ?? null,
      reserva,
      ahora + VIDA_DE_UNA_RESERVA_MS,
      p.proveedor ?? null,
    );
    const id = this.sql.uno<{ id: number }>("SELECT last_insert_rowid() AS id")?.id ?? 0;
    return { ok: true, id };
  }

  /**
   * Una nota de voz de Andrés: primero su tope por sesión (por hora) y después lo mismo que un mensaje (red, /48, día, turnos a la vez
   * y presupuesto, con `reservaUsd` > 0). Todo en la misma llamada: atómico. Se cierra con `cerrar`, como un turno.
   */
  reservarVoz(p: ReservaVozTienda, ahora: number): ResultadoReservaVozTienda {
    this.sql.correr("DELETE FROM tienda_voz WHERE ts <= ?", ahora - 3600_000);
    const deLaSesion = this.sql.todos<{ ts: number }>("SELECT ts FROM tienda_voz WHERE sesion = ? ORDER BY ts", p.sesion);
    if (deLaSesion.length >= p.porSesion) {
      return { ok: false, motivo: "tope_sesion", reintentarEn: Math.max(1, Math.ceil((deLaSesion[0].ts + 3600_000 - ahora) / 1000)) };
    }
    const r = this.reservar(p, ahora);
    if (r.ok) this.sql.correr("INSERT INTO tienda_voz (ts, sesion) VALUES (?, ?)", ahora, p.sesion);
    return r;
  }

  /**
   * ¿Hay demasiados turnos con IA a la vez? Cada red cuenta como mucho su parte justa (`enVueloRed`, 2 de fábrica): una sola conexión
   * puede usar los lugares libres, pero lo que pase de su parte nunca deja fuera a otra red (revisión adversarial, segunda vuelta). Y
   * una red que ya tiene su parte no agrega más si en total ya se llegó al tope.
   */
  private ocupado(p: ReservaTienda, ahora: number): boolean {
    const tope = p.enVueloMax ?? TIENDA_POR_DEFECTO.tope_en_vuelo;
    const parte = p.enVueloRed ?? TIENDA_POR_DEFECTO.tope_en_vuelo_red;
    const porRed = this.sql.todos<{ red: string; n: number }>("SELECT red, COUNT(*) AS n FROM tienda_turnos WHERE reserva > 0 AND vence > ? GROUP BY red", ahora);
    const total = porRed.reduce((s, f) => s + f.n, 0);
    const justo = porRed.reduce((s, f) => s + Math.min(f.n, parte), 0);
    const deEstaRed = porRed.find((f) => f.red === p.red)?.n ?? 0;
    return justo >= tope || (deEstaRed >= parte && total >= tope);
  }

  /**
   * Lo apartado que venció sin que nadie cerrara el turno (el Worker se cayó, o el cierre falló dos veces) pasa a GASTO estimado, en el
   * renglón «turnos cortados (estimado)» con su proveedor: si la IA trabajó, el proveedor cobró. Se marca para no contarlo dos veces.
   */
  private liquidarVencidas(ahora: number): void {
    const vencidas = this.sql.todos<{ id: number; dia: string; reserva: number; proveedor: string | null }>(
      "SELECT id, dia, reserva, proveedor FROM tienda_turnos WHERE reserva > 0 AND vence > 0 AND vence <= ?",
      ahora,
    );
    for (const v of vencidas) {
      this.sql.correr("UPDATE tienda_turnos SET reserva = 0, vence = ? WHERE id = ?", LIQUIDADA, v.id);
      this.anotarGasto({ mes: v.dia.slice(0, 7), proveedor: v.proveedor ?? "desconocido", modelo: MODELO_DE_LO_CORTADO, uso: { entrada: 0, cacheLectura: 0, cacheEscritura: 0, salida: 0 }, usd: v.reserva, estimado: true });
    }
  }

  /**
   * El turno terminó: suelta lo apartado y anota lo que de verdad costó (cada modelo con su proveedor, en su propio renglón). Si el
   * cierre llega cuando la reserva ya pasó a gasto estimado, no se anota otra vez: lo estimado (lo apartado, el máximo) se queda.
   */
  cerrar(id: number, gastos: readonly GastoTienda[]): void {
    const fila = this.sql.uno<{ vence: number }>("SELECT vence FROM tienda_turnos WHERE id = ?", id);
    if (fila?.vence === LIQUIDADA) return;
    this.sql.correr("UPDATE tienda_turnos SET reserva = 0, vence = 0 WHERE id = ?", id);
    for (const g of gastos) this.anotarGasto(g);
  }

  private anotarGasto(g: GastoTienda): void {
    if (!(g.usd >= 0) || !Number.isFinite(g.usd)) return;
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

  gastoMes(mes: string, dia: string, ahora: number): GastoTiendaDelMes {
    this.liquidarVencidas(ahora);
    const filas = this.sql.todos<{ proveedor: string; modelo: string; usd: number; turnos: number; estimado: number }>(
      "SELECT proveedor, modelo, usd, turnos, estimado FROM tienda_gasto WHERE mes = ? ORDER BY usd DESC",
      mes,
    );
    return {
      mes,
      usd: filas.reduce((n, f) => n + f.usd, 0),
      // Las «respuestas» del mes: las notas de voz no son respuestas (cada una ya trae su mensaje). Su gasto sí suma en `usd`.
      turnos: filas.reduce((n, f) => n + (f.modelo === MODELO_DE_LA_VOZ && f.proveedor === PROVEEDOR_DE_LA_VOZ ? 0 : f.turnos), 0),
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

  /** Andrés: aparta una nota de voz (su tope por sesión más los de un mensaje y el presupuesto). Se cierra con `cerrarTurnoTienda`. */
  reservarVozTienda(p: ReservaVozTienda): ResultadoReservaVozTienda {
    return this.tienda.reservarVoz(p, Date.now());
  }

  /** Brian del panel: aparta una nota de voz (tope por usuario y por día, techo del mes). El gasto se anota con `registrarGasto`. */
  reservarVozPanel(p: ReservaVozPanel): ResultadoReservaVozPanel {
    return this.almacen.reservarVozPanel(p, Date.now());
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
