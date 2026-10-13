// Durable Objects de mentira para las pruebas "de punta a punta": las CLASES de verdad (`Conversacion`, `Global`) corriendo
// sobre un `ctx.storage.sql` hecho con node:sqlite que se porta como el de workerd (BLOB como ArrayBuffer), con alarmas anotadas.
import { DatabaseSync } from "node:sqlite";
import type { Env } from "../../src/env";
import { Conversacion } from "../../src/motor/do";
import { Global } from "../../src/motor/global";
import { HERRAMIENTAS_DE_PRUEBA } from "./odooFalso";

export interface CtxFalso {
  storage: {
    sql: { exec(consulta: string, ...bindings: unknown[]): { toArray(): Record<string, unknown>[] } };
    setAlarm(ts: number): Promise<void>;
    deleteAlarm(): Promise<void>;
    getAlarm(): Promise<number | null>;
  };
  alarma: number | null;
}

export function ctxFalso(): CtxFalso {
  const db = new DatabaseSync(":memory:");
  const ctx: CtxFalso = {
    alarma: null,
    storage: {
      sql: {
        exec(consulta, ...bindings) {
          for (const b of bindings) {
            if (b instanceof Uint8Array) throw new Error("SqlStorage solo acepta ArrayBuffer para los BLOB");
          }
          const params = bindings.map((b) => (b instanceof ArrayBuffer ? new Uint8Array(b) : b)) as (string | number | null | Uint8Array)[];
          const filas = db.prepare(consulta).all(...params) as Record<string, unknown>[];
          const comoWorkerd = filas.map((f) =>
            Object.fromEntries(Object.entries(f).map(([k, v]) => [k, v instanceof Uint8Array ? v.buffer.slice(v.byteOffset, v.byteOffset + v.byteLength) : v])),
          );
          return { toArray: () => comoWorkerd };
        },
      },
      async setAlarm(ts) {
        ctx.alarma = ts;
      },
      async deleteAlarm() {
        ctx.alarma = null;
      },
      async getAlarm() {
        return ctx.alarma;
      },
    },
  };
  return ctx;
}

/** Un `DurableObjectNamespace` que crea (y recuerda) una instancia de verdad por nombre. */
function espacio<T extends object>(crear: (nombre: string) => T) {
  const instancias = new Map<string, T>();
  const porId = (nombre: string) => {
    let i = instancias.get(nombre);
    if (!i) instancias.set(nombre, (i = crear(nombre)));
    return i;
  };
  return {
    instancias,
    idFromName: (nombre: string) => ({ nombre }),
    // Una llamada por RPC siempre es asíncrona.
    get: (id: { nombre: string }) =>
      new Proxy({} as Record<string, unknown>, {
        get: (_o, metodo: string) => async (...args: unknown[]) => {
          const objeto = porId(id.nombre) as Record<string, (...a: unknown[]) => unknown>;
          return objeto[metodo](...args);
        },
      }),
  };
}

export interface Cluster {
  env: Env;
  conversaciones: Map<string, { instancia: Conversacion; ctx: CtxFalso }>;
  global: { instancia: Global; ctx: CtxFalso } | null;
  /** Dispara la alarma de la conversación (como haría Cloudflare al vencer). */
  alarma(nombre: string): Promise<void>;
  /** Como Cloudflare: mientras la alarma programada ya venció, se dispara (la cola de Odoo vence al instante). */
  correrAlarmas(nombre: string): Promise<number>;
}

/** Arma `env.CONVERSACION` y `env.GLOBAL` con las clases reales. `base` trae secretos, DCASA, vars... */
export function armarCluster(base: Partial<Env>): Cluster {
  const cluster = {
    env: undefined as unknown as Env,
    conversaciones: new Map<string, { instancia: Conversacion; ctx: CtxFalso }>(),
    global: null as Cluster["global"],
    async alarma(nombre: string) {
      const c = cluster.conversaciones.get(nombre);
      if (!c) throw new Error(`no hay conversación ${nombre}`);
      c.ctx.alarma = null;
      await c.instancia.alarm();
    },
    async correrAlarmas(nombre: string) {
      const c = cluster.conversaciones.get(nombre);
      let n = 0;
      while (c && c.ctx.alarma !== null && c.ctx.alarma <= Date.now() && n < 20) {
        await cluster.alarma(nombre);
        n++;
      }
      return n;
    },
  } satisfies Cluster;

  const conversaciones = espacio((nombre) => {
    const ctx = ctxFalso();
    const instancia = new Conversacion(ctx as unknown as DurableObjectState, cluster.env);
    cluster.conversaciones.set(nombre, { instancia, ctx });
    return instancia;
  });
  const global = espacio((_nombre) => {
    const ctx = ctxFalso();
    const instancia = new Global(ctx as unknown as DurableObjectState, cluster.env);
    cluster.global = { instancia, ctx };
    return instancia;
  });
  cluster.env = { ...base, CONVERSACION: conversaciones, GLOBAL: global } as unknown as Env;
  return cluster;
}

/**
 * El Worker `dcasa` (Odoo) de mentira, por el service binding: habla el contrato de docs/JUAN.md.
 * Anota lo que Juan le manda; las respuestas se pueden cambiar desde la prueba.
 */
export function dcasaFalso() {
  const peticiones: { metodo: string; ruta: string; cuerpo: any; auth: string | null }[] = [];
  const estado = {
    /** Los chats de Telegram de las pruebas están en la lista permitida de Odoo (el canal no es abierto: ver `soloLosPermitidos` en rutas.ts). */
    config: { telegram_chats: ["555", "111", "222", "333", "444", "666", "777", "888", "999"] } as Record<string, unknown>,
    herramientas: HERRAMIENTAS_DE_PRUEBA as unknown[],
    mensaje: { ok: true, conversacion_id: 77, estado: "bot", bot_activo: true, pausada_hasta: null, dentro_de_horario: true } as Record<string, unknown>,
    herramienta: (_nombre: string, _args: Record<string, unknown>): unknown => ({ ok: true, resultado: {} }),
    caido: false,
  };
  const fetcher = {
    fetch: async (url: string, init?: RequestInit) => {
      const u = new URL(url);
      const ruta = u.pathname.replace("/dcasa/juan/v1", "");
      const cuerpo = init?.body ? JSON.parse(String(init.body)) : undefined;
      const auth = new Headers(init?.headers).get("authorization");
      peticiones.push({ metodo: init?.method ?? "GET", ruta, cuerpo, auth });
      if (estado.caido) return new Response("Odoo dormido", { status: 503 });
      if (ruta === "/config") return Response.json(estado.config);
      if (ruta === "/herramientas") return Response.json({ herramientas: estado.herramientas });
      if (ruta === "/mensaje") return Response.json(estado.mensaje);
      if (ruta === "/estado") return Response.json(estado.mensaje);
      if (ruta === "/herramienta") return Response.json(estado.herramienta(cuerpo.nombre, cuerpo.argumentos));
      if (ruta === "/seguimiento/hecho") return Response.json({ ok: true });
      if (ruta === "/escribiendo") return Response.json({ ok: true });
      return new Response("no", { status: 404 });
    },
  };
  return { fetcher: fetcher as unknown as Fetcher, peticiones, estado, mensajes: () => peticiones.filter((p) => p.ruta === "/mensaje").map((p) => p.cuerpo) };
}
