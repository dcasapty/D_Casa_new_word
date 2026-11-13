// El Durable Object de UNA sesión de Brian de la tienda (`tienda:<sid>`): su SQLite guarda el contexto (como mucho 30 turnos) y su
// alarma lo borra todo a las 2 horas sin actividad. La lógica vive en MotorTienda (tienda/motor.ts); esto solo le presta Cloudflare.
// Un objeto por sesión: dos mensajes del mismo visitante se atienden uno a la vez, y su tope por sesión se cuenta sin carreras.

import { DurableObject } from "cloudflare:workers";
import type { Env } from "../env";
import type { GastoTienda, ReservaTienda } from "../motor/global";
import { fabricaDeProduccion, proveedoresConClave } from "../motor/proveedores";
import { sqlDeDurableObject } from "../motor/sql";
import { obtenerConfig, obtenerHerramientas, odooDe } from "../odoo/fabrica";
import { MotorTienda, type DepsTienda, type EntradaTienda } from "./motor";

const HOSTS_CONOCIDOS = ["dcasapty.com", "www.dcasapty.com", "dcasa-staging.dcasapty.workers.dev"];

/** Los hosts del propio sitio (sus direcciones absolutas se vuelven relativas en las tarjetas): los conocidos y el de URL_SITIO. */
export function hostsDelSitio(env: Pick<Env, "URL_SITIO">): string[] {
  const hosts = new Set(HOSTS_CONOCIDOS);
  try {
    if (env.URL_SITIO) hosts.add(new URL(env.URL_SITIO).host.toLowerCase());
  } catch {
    /* una URL_SITIO rara no cambia nada */
  }
  return [...hosts];
}

export function depsDeLaTienda(ctx: DurableObjectState, env: Env): DepsTienda {
  const global = () => env.GLOBAL.get(env.GLOBAL.idFromName("juan"));
  return {
    sql: sqlDeDurableObject(ctx.storage.sql),
    ahora: () => Date.now(),
    config: () => obtenerConfig(env),
    odoo: odooDe(env),
    herramientas: () => obtenerHerramientas(env),
    modelo: (sel) => fabricaDeProduccion(env)(sel),
    proveedoresDisponibles: () => proveedoresConClave(env),
    global: {
      reservarTurnoTienda: async (p: ReservaTienda) => global().reservarTurnoTienda(p),
      cerrarTurnoTienda: async (id: number, gastos: GastoTienda[]) => {
        await global().cerrarTurnoTienda(id, gastos);
      },
      guardarSalud: async (clave, json) => {
        await global().guardarSalud(clave, json);
      },
    },
    fijarAlarma: async (ts) => {
      if (ts === null) await ctx.storage.deleteAlarm();
      else await ctx.storage.setAlarm(ts);
    },
    // Borra de verdad (no solo las filas): el contexto vencido no queda en ningún lado.
    borrarTodo: async () => {
      await ctx.storage.deleteAll();
    },
    hostsDelSitio: hostsDelSitio(env),
    sitio: env.URL_SITIO || undefined,
  };
}

export class TiendaSesion extends DurableObject<Env> {
  private readonly motor: MotorTienda;

  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env);
    this.motor = new MotorTienda(depsDeLaTienda(ctx, env));
  }

  atender(e: EntradaTienda) {
    return this.motor.atender(e);
  }

  /** Cloudflare la llama a las 2 horas de la última actividad: se borra todo. */
  async alarm(): Promise<void> {
    await this.motor.alarma();
  }

  resumen() {
    return this.motor.resumen();
  }
}
