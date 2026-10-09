// El almacén del puente: todo lo que vive en el SQLite del Durable Object.
//
// En el CRM de origen la sesión de WhatsApp iba a una base D1 aparte. Aquí vive en el
// propio Durable Object (SQLite integrado): no se crea ningún recurso extra en
// Cloudflare, la sesión y el vigilante comparten dueño, y un solo escritor (el DO) la
// toca. Tablas:
//
//   wa_auth        la sesión de Baileys, CIFRADA (cifrado.ts)
//   wa_copias      copias diarias de la sesión (las mismas filas cifradas)
//   wa_envios      cada burbuja enviada: para los topes por minuto / día / destinatario
//   wa_enviados    ids de lo que mandó el puente (para no confundir su eco con la dueña)
//   wa_contactos   cuándo escribió cada cliente por última vez (¿es un envío «frío»?)
//   wa_pendientes  mensajes entrantes que Juan no pudo recibir (se reintentan)
//
// El acceso al SQL va por una interfaz mínima (`SqlLike`) para poder probarlo con el
// SQLite de Node sin Cloudflare.

import type { Cifrador } from "./cifrado";
import type { Envio } from "../contenedor/lib/ritmo.mjs";

/** Lo mínimo que se usa de `SqlStorage` de Cloudflare. */
export interface SqlLike {
  exec(consulta: string, ...enlaces: unknown[]): { toArray(): Record<string, any>[] };
}

export interface DepsAlmacen {
  sql: SqlLike;
  /** `ctx.storage.transactionSync`: o todo, o nada. */
  transaccion<T>(fn: () => T): T;
  cifrador: Cifrador;
  ahora(): number;
}

/** Copias de la sesión que se conservan en el Durable Object. */
export const COPIAS_A_CONSERVAR = 7;
/** Cuántas pre-keys se conservan al podar. Ver `/api/podar`. */
export const PRE_KEYS_A_CONSERVAR = 1000;
/** Filas por consulta al leer/escribir en lote (no pasarse de los límites de SQLite). */
export const FILAS_POR_IDA = 90;

const DIA_MS = 24 * 60 * 60 * 1000;
/** Cuánto se recuerda lo enviado: lo que tarda en volver un eco tras un reinicio. */
const ENVIADOS_MS = 2 * 60 * 60 * 1000;
/** Un cliente que no ha escrito en tanto tiempo se considera «nuevo» para los topes. */
export const CONTACTO_VIGENTE_MS = 30 * DIA_MS;
/** Cuánto se guardan los entrantes que Juan no pudo recibir. */
export const PENDIENTE_MAX_MS = 48 * 60 * 60 * 1000;
export const PENDIENTES_MAX = 500;

export interface FilaCruda {
  clave: string;
  valor: string;
  actualizado_en: number;
}

export interface EstadoSesion {
  total: number;
  preKeys: number;
  appState: number;
  lidMapping: number;
  credsActualizadaEn: string | null;
  vinculado: boolean;
  /** `nextPreKeyId` de las credenciales (solo el número). */
  siguiente: number | null;
  /** `firstUnuploadedPreKeyId` de las credenciales (solo el número). */
  sinSubir: number | null;
  /**
   * La señal que de verdad dice que el dispositivo TERMINÓ de instalarse: si
   * `sinSubir == siguiente`, no queda ninguna llave por subir. Las otras (creds
   * presente, filas lid-mapping) salen en verde con el dispositivo a medio
   * instalar — fue lo que hizo pasar por buena una prueba rota en el CRM de origen.
   */
  instalacionCompleta: boolean | null;
}

export function iniciarEsquema(sql: SqlLike): void {
  const sentencias = [
    `CREATE TABLE IF NOT EXISTS wa_auth (
       clave TEXT PRIMARY KEY, valor TEXT NOT NULL, actualizado_en INTEGER NOT NULL)`,
    `CREATE INDEX IF NOT EXISTS idx_wa_auth_actualizado ON wa_auth (actualizado_en)`,
    `CREATE TABLE IF NOT EXISTS wa_copias (
       copia TEXT NOT NULL, clave TEXT NOT NULL, valor TEXT NOT NULL, actualizado_en INTEGER NOT NULL,
       PRIMARY KEY (copia, clave))`,
    `CREATE TABLE IF NOT EXISTS wa_copias_meta (
       copia TEXT PRIMARY KEY, creada_en INTEGER NOT NULL, filas INTEGER NOT NULL)`,
    `CREATE TABLE IF NOT EXISTS wa_envios (
       id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER NOT NULL, para TEXT NOT NULL, frio INTEGER NOT NULL DEFAULT 0)`,
    `CREATE INDEX IF NOT EXISTS idx_wa_envios_ts ON wa_envios (ts)`,
    `CREATE TABLE IF NOT EXISTS wa_enviados (id TEXT PRIMARY KEY, ts INTEGER NOT NULL)`,
    `CREATE TABLE IF NOT EXISTS wa_contactos (celular TEXT PRIMARY KEY, ultimo_entrante INTEGER NOT NULL)`,
    `CREATE TABLE IF NOT EXISTS wa_pendientes (
       id INTEGER PRIMARY KEY AUTOINCREMENT, creado_en INTEGER NOT NULL,
       intentos INTEGER NOT NULL DEFAULT 0, cuerpo TEXT NOT NULL)`,
  ];
  // Una sentencia por llamada: no se depende de que `exec` admita varias.
  for (const s of sentencias) sql.exec(s);
}

function pedazos<T>(lista: T[], tamano: number): T[][] {
  const salida: T[][] = [];
  for (let i = 0; i < lista.length; i += tamano) salida.push(lista.slice(i, i + tamano));
  return salida;
}

export type Almacen = ReturnType<typeof crearAlmacen>;

export function crearAlmacen({ sql, transaccion, cifrador, ahora }: DepsAlmacen) {
  const filas = <T = Record<string, any>>(consulta: string, ...enlaces: unknown[]) =>
    sql.exec(consulta, ...enlaces).toArray() as T[];

  // ── La sesión (cifrada) ──────────────────────────────────────────────────

  async function get(clave: string): Promise<string | null> {
    const [fila] = filas<{ valor: string }>("SELECT valor FROM wa_auth WHERE clave = ?", clave);
    return fila ? cifrador.descifrar(clave, fila.valor) : null;
  }

  async function set(clave: string, valor: string): Promise<void> {
    const cifrado = await cifrador.cifrar(clave, valor);
    const t = ahora();
    sql.exec(
      `INSERT INTO wa_auth (clave, valor, actualizado_en) VALUES (?, ?, ?)
       ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor, actualizado_en = excluded.actualizado_en`,
      clave,
      cifrado,
      t,
    );
  }

  async function del(clave: string): Promise<void> {
    sql.exec("DELETE FROM wa_auth WHERE clave = ?", clave);
  }

  /**
   * Lee y escribe MUCHAS claves en una sola petición. Es lo que hace que el canal se
   * pueda vincular: al emparejar, WhatsApp exige subir 812 llaves en menos de 30 s y
   * Baileys las entrega todas de una vez (ver contenedor/lib/auth-remoto.mjs).
   *
   * Los valores son texto JSON ya serializado por Baileys; aquí no se interpretan.
   * Todo el cifrado se hace ANTES de abrir la transacción (WebCrypto es asíncrono y
   * `transactionSync` no admite esperas), y la escritura entera es atómica.
   */
  async function lote(cuerpo: {
    leer?: string[];
    escribir?: Record<string, string>;
    borrar?: string[];
  }): Promise<{ ok: true; leidas: number; escritas: number; borradas: number; valores: Record<string, string | null> }> {
    const valores: Record<string, string | null> = {};

    if (cuerpo.leer?.length) {
      for (const grupo of pedazos(cuerpo.leer, FILAS_POR_IDA)) {
        const huecos = grupo.map(() => "?").join(",");
        const encontradas = filas<{ clave: string; valor: string }>(
          `SELECT clave, valor FROM wa_auth WHERE clave IN (${huecos})`,
          ...grupo,
        );
        const claros = await Promise.all(encontradas.map((f) => cifrador.descifrar(f.clave, f.valor)));
        encontradas.forEach((f, i) => {
          valores[f.clave] = claros[i];
        });
      }
      // Las que no existen se devuelven como null EXPLÍCITO. Baileys distingue «no la
      // tengo» de «no pregunté», y omitirlas confundiría las dos.
      for (const clave of cuerpo.leer) if (!(clave in valores)) valores[clave] = null;
    }

    const pares = Object.entries(cuerpo.escribir ?? {});
    const cifradas = await Promise.all(pares.map(([clave, valor]) => cifrador.cifrar(clave, valor)));
    const borrar = cuerpo.borrar ?? [];
    const t = ahora();

    if (pares.length || borrar.length) {
      transaccion(() => {
        pares.forEach(([clave], i) => {
          sql.exec(
            `INSERT INTO wa_auth (clave, valor, actualizado_en) VALUES (?, ?, ?)
             ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor, actualizado_en = excluded.actualizado_en`,
            clave,
            cifradas[i],
            t,
          );
        });
        for (const grupo of pedazos(borrar, FILAS_POR_IDA)) {
          sql.exec(`DELETE FROM wa_auth WHERE clave IN (${grupo.map(() => "?").join(",")})`, ...grupo);
        }
      });
    }

    return {
      ok: true,
      leidas: Object.keys(valores).length,
      escritas: pares.length,
      borradas: borrar.length,
      valores,
    };
  }

  /** ¿Hay sesión guardada? (Sin descifrar nada: es una sola consulta barata.) */
  function hayCreds(): boolean {
    return filas("SELECT 1 AS x FROM wa_auth WHERE clave = 'creds'").length > 0;
  }

  /**
   * Cuántas credenciales hay y de cuándo. Es el mejor testigo de que el canal está
   * vivo y de que terminó de instalarse. Solo se exponen NÚMEROS, nunca material.
   */
  async function estadoSesion(): Promise<EstadoSesion> {
    const [r] = filas<{ total: number; preKeys: number; appState: number; lidMapping: number; credsEn: number | null }>(
      `SELECT COUNT(*) AS total,
              COALESCE(SUM(CASE WHEN clave LIKE 'pre-key-%' THEN 1 ELSE 0 END), 0) AS preKeys,
              COALESCE(SUM(CASE WHEN clave LIKE 'app-state-sync-key-%' THEN 1 ELSE 0 END), 0) AS appState,
              COALESCE(SUM(CASE WHEN clave LIKE 'lid-mapping%' THEN 1 ELSE 0 END), 0) AS lidMapping,
              MAX(CASE WHEN clave = 'creds' THEN actualizado_en END) AS credsEn
         FROM wa_auth`,
    );
    let siguiente: number | null = null;
    let sinSubir: number | null = null;
    if (r.credsEn) {
      try {
        const claro = await get("creds");
        const c = claro ? (JSON.parse(claro) as { nextPreKeyId?: unknown; firstUnuploadedPreKeyId?: unknown }) : null;
        if (typeof c?.nextPreKeyId === "number") siguiente = c.nextPreKeyId;
        if (typeof c?.firstUnuploadedPreKeyId === "number") sinSubir = c.firstUnuploadedPreKeyId;
      } catch {
        // Si no se puede leer (clave equivocada) los números quedan en null y se nota.
      }
    }
    return {
      total: r.total,
      preKeys: r.preKeys,
      appState: r.appState,
      lidMapping: r.lidMapping,
      credsActualizadaEn: r.credsEn ? new Date(r.credsEn).toISOString() : null,
      vinculado: Boolean(r.credsEn),
      siguiente,
      sinSubir,
      instalacionCompleta: siguiente === null || sinSubir === null ? null : siguiente === sinSubir,
    };
  }

  /**
   * Válvula de seguridad, a propósito NO automática: las pre-keys son material
   * criptográfico y borrar una que todavía haga falta rompe el descifrado de un
   * mensaje pendiente. Conserva las más recientes.
   */
  function podarPreKeys(conservar = PRE_KEYS_A_CONSERVAR): number {
    const [antes] = filas<{ n: number }>("SELECT COUNT(*) AS n FROM wa_auth WHERE clave LIKE 'pre-key-%'");
    sql.exec(
      `DELETE FROM wa_auth
        WHERE clave LIKE 'pre-key-%'
          AND clave NOT IN (
            SELECT clave FROM wa_auth WHERE clave LIKE 'pre-key-%' ORDER BY actualizado_en DESC LIMIT ?)`,
      conservar,
    );
    const [despues] = filas<{ n: number }>("SELECT COUNT(*) AS n FROM wa_auth WHERE clave LIKE 'pre-key-%'");
    return antes.n - despues.n;
  }

  /** Vuelve a cifrar con la clave ACTUAL todo lo que esté con la anterior (rotación de clave). */
  async function recifrar(): Promise<{ revisadas: number; recifradas: number }> {
    const todas = filas<FilaCruda>("SELECT clave, valor, actualizado_en FROM wa_auth");
    const pendientes = todas.filter((f) => !cifrador.esActual(f.valor));
    const nuevas: { clave: string; valor: string }[] = [];
    for (const f of pendientes) {
      nuevas.push({ clave: f.clave, valor: await cifrador.cifrar(f.clave, await cifrador.descifrar(f.clave, f.valor)) });
    }
    transaccion(() => {
      for (const n of nuevas) sql.exec("UPDATE wa_auth SET valor = ? WHERE clave = ?", n.valor, n.clave);
    });
    return { revisadas: todas.length, recifradas: nuevas.length };
  }

  // ── Copias de la sesión ──────────────────────────────────────────────────

  /** `2026-10-09T03-17-00Z`: ordenable y sin caracteres que estorben en un nombre de archivo. */
  function idDeCopia(t: number): string {
    return new Date(t).toISOString().replace(/\.\d+Z$/, "Z").replace(/:/g, "-");
  }

  /**
   * Copia de la sesión: las MISMAS filas cifradas (nada en claro). Es atómica y se
   * hace dentro del propio SQLite. Conserva las últimas `COPIAS_A_CONSERVAR`.
   * Si ya existe una copia con ese id (mismo segundo) la reemplaza.
   */
  function copiar(): { copia: string; filas: number } {
    const t = ahora();
    const copia = idDeCopia(t);
    let n = 0;
    transaccion(() => {
      sql.exec("DELETE FROM wa_copias WHERE copia = ?", copia);
      sql.exec(
        "INSERT INTO wa_copias (copia, clave, valor, actualizado_en) SELECT ?, clave, valor, actualizado_en FROM wa_auth",
        copia,
      );
      n = filas<{ n: number }>("SELECT COUNT(*) AS n FROM wa_copias WHERE copia = ?", copia)[0].n;
      sql.exec(
        "INSERT INTO wa_copias_meta (copia, creada_en, filas) VALUES (?, ?, ?) ON CONFLICT(copia) DO UPDATE SET creada_en = excluded.creada_en, filas = excluded.filas",
        copia,
        t,
        n,
      );
      const sobrantes = filas<{ copia: string }>(
        "SELECT copia FROM wa_copias_meta ORDER BY creada_en DESC LIMIT -1 OFFSET ?",
        COPIAS_A_CONSERVAR,
      );
      for (const s of sobrantes) {
        sql.exec("DELETE FROM wa_copias WHERE copia = ?", s.copia);
        sql.exec("DELETE FROM wa_copias_meta WHERE copia = ?", s.copia);
      }
    });
    return { copia, filas: n };
  }

  function listarCopias(): { copia: string; creada: string; filas: number }[] {
    return filas<{ copia: string; creada_en: number; filas: number }>(
      "SELECT copia, creada_en, filas FROM wa_copias_meta ORDER BY creada_en DESC",
    ).map((c) => ({ copia: c.copia, creada: new Date(c.creada_en).toISOString(), filas: c.filas }));
  }

  function ultimaCopiaEn(): number | null {
    const [r] = filas<{ t: number | null }>("SELECT MAX(creada_en) AS t FROM wa_copias_meta");
    return r?.t ?? null;
  }

  /** Las filas (cifradas) de una copia; para exportarla a R2. */
  function filasDeCopia(copia: string): FilaCruda[] {
    return filas<FilaCruda>("SELECT clave, valor, actualizado_en FROM wa_copias WHERE copia = ? ORDER BY clave", copia);
  }

  /**
   * Restaura la sesión desde unas filas (de una copia propia o importadas de R2).
   *
   * Antes de tocar nada comprueba que haya una fila `creds` Y que se pueda
   * descifrar con la clave actual: restaurar una copia hecha con otra clave dejaría
   * la sesión ilegible y peor que como estaba. Reemplaza TODO `wa_auth` de forma
   * atómica. Quien llama debe tener el contenedor APAGADO (si no, volvería a
   * escribir encima).
   */
  async function restaurar(entrada: FilaCruda[]): Promise<{ filas: number }> {
    const creds = entrada.find((f) => f.clave === "creds");
    if (!creds) throw new Error("La copia no trae las credenciales (fila «creds»): no se restaura.");
    await cifrador.descifrar("creds", creds.valor); // lanza si es de otra clave o está alterada
    transaccion(() => {
      sql.exec("DELETE FROM wa_auth");
      for (const f of entrada) {
        sql.exec(
          "INSERT INTO wa_auth (clave, valor, actualizado_en) VALUES (?, ?, ?)",
          f.clave,
          f.valor,
          f.actualizado_en,
        );
      }
    });
    return { filas: entrada.length };
  }

  // ── Envíos y topes ───────────────────────────────────────────────────────

  function enviosRecientes(): Envio[] {
    const desde = ahora() - DIA_MS;
    sql.exec("DELETE FROM wa_envios WHERE ts < ?", desde);
    return filas<{ ts: number; para: string; frio: number }>(
      "SELECT ts, para, frio FROM wa_envios WHERE ts >= ?",
      desde,
    ).map((e) => ({ ts: e.ts, para: e.para, frio: e.frio === 1 }));
  }

  /** Reserva `cantidad` envíos; devuelve los ids de las filas para poder devolver el sobrante. */
  function reservarEnvios(para: string, cantidad: number, frio: boolean): number[] {
    const t = ahora();
    const ids: number[] = [];
    transaccion(() => {
      for (let i = 0; i < cantidad; i++) {
        sql.exec("INSERT INTO wa_envios (ts, para, frio) VALUES (?, ?, ?)", t, para, frio ? 1 : 0);
        ids.push(filas<{ id: number }>("SELECT last_insert_rowid() AS id")[0].id);
      }
    });
    return ids;
  }

  function liberarEnvios(ids: number[]): void {
    transaccion(() => {
      for (const id of ids) sql.exec("DELETE FROM wa_envios WHERE id = ?", id);
    });
  }

  function marcarEntrante(celular: string): void {
    sql.exec(
      `INSERT INTO wa_contactos (celular, ultimo_entrante) VALUES (?, ?)
       ON CONFLICT(celular) DO UPDATE SET ultimo_entrante = excluded.ultimo_entrante`,
      celular,
      ahora(),
    );
  }

  /** ¿Es alguien a quien se le escribe SIN que haya escrito primero (en los últimos 30 días)? */
  function esFrio(celular: string): boolean {
    const [r] = filas<{ ultimo_entrante: number }>(
      "SELECT ultimo_entrante FROM wa_contactos WHERE celular = ?",
      celular,
    );
    return !r || ahora() - r.ultimo_entrante > CONTACTO_VIGENTE_MS;
  }

  function anotarEnviados(ids: string[]): void {
    const t = ahora();
    transaccion(() => {
      sql.exec("DELETE FROM wa_enviados WHERE ts < ?", t - ENVIADOS_MS);
      for (const id of ids) {
        sql.exec("INSERT INTO wa_enviados (id, ts) VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET ts = excluded.ts", id, t);
      }
    });
  }

  function enviadosRecientes(): { id: string; ts: number }[] {
    return filas<{ id: string; ts: number }>(
      "SELECT id, ts FROM wa_enviados WHERE ts >= ? ORDER BY ts",
      ahora() - ENVIADOS_MS,
    );
  }

  // ── Entrantes que Juan no pudo recibir ───────────────────────────────────

  async function encolarPendiente(cuerpo: string): Promise<number> {
    const cifrado = await cifrador.cifrar("pendiente", cuerpo);
    const t = ahora();
    let id = 0;
    transaccion(() => {
      sql.exec("DELETE FROM wa_pendientes WHERE creado_en < ?", t - PENDIENTE_MAX_MS);
      const [{ n }] = filas<{ n: number }>("SELECT COUNT(*) AS n FROM wa_pendientes");
      if (n >= PENDIENTES_MAX) {
        // Tope: se descarta el más viejo antes que crecer sin límite.
        sql.exec("DELETE FROM wa_pendientes WHERE id = (SELECT MIN(id) FROM wa_pendientes)");
      }
      sql.exec("INSERT INTO wa_pendientes (creado_en, cuerpo) VALUES (?, ?)", t, cifrado);
      id = filas<{ id: number }>("SELECT last_insert_rowid() AS id")[0].id;
    });
    return id;
  }

  async function pendientes(limite: number): Promise<{ id: number; intentos: number; cuerpo: string }[]> {
    const lista = filas<{ id: number; intentos: number; cuerpo: string }>(
      "SELECT id, intentos, cuerpo FROM wa_pendientes ORDER BY id LIMIT ?",
      limite,
    );
    return Promise.all(lista.map(async (p) => ({ ...p, cuerpo: await cifrador.descifrar("pendiente", p.cuerpo) })));
  }

  function contarPendientes(): number {
    return filas<{ n: number }>("SELECT COUNT(*) AS n FROM wa_pendientes")[0].n;
  }

  function borrarPendiente(id: number): void {
    sql.exec("DELETE FROM wa_pendientes WHERE id = ?", id);
  }

  function fallarPendiente(id: number): void {
    sql.exec("UPDATE wa_pendientes SET intentos = intentos + 1 WHERE id = ?", id);
  }

  return {
    get,
    set,
    del,
    lote,
    hayCreds,
    estadoSesion,
    podarPreKeys,
    recifrar,
    copiar,
    listarCopias,
    ultimaCopiaEn,
    filasDeCopia,
    restaurar,
    enviosRecientes,
    reservarEnvios,
    liberarEnvios,
    marcarEntrante,
    esFrio,
    anotarEnviados,
    enviadosRecientes,
    encolarPendiente,
    pendientes,
    contarPendientes,
    borrarPendiente,
    fallarPendiente,
  };
}
