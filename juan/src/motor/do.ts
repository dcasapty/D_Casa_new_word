// El Durable Object de una conversación: SQLite propio, alarma para la ráfaga de 15 s y la cola de Odoo.
// La lógica vive en MotorConversacion (motor/conversacion.ts); esto solo le presta Cloudflare.
// Un objeto por `canal:id_externo`: dos mensajes de la misma persona se atienden uno a la vez.

import { DurableObject } from "cloudflare:workers";
import { adaptadorDe } from "../canales";
import type { Entrante } from "../canales/tipos";
import type { Env } from "../env";
import { obtenerConfig, obtenerHerramientas, odooDe } from "../odoo/fabrica";
import { MotorConversacion, type DepsMotor, type GlobalApi, type SolicitudEnviar, type SolicitudSeguimiento } from "./conversacion";
import { fabricaAnthropic } from "./modelo";
import { sqlDeDurableObject } from "./sql";
import { transcriptorDe } from "./transcribir";
import { TOPE_DIARIO_POR_DEFECTO } from "./antispam";

export function globalDe(env: Env): GlobalApi {
  const stub = () => env.GLOBAL.get(env.GLOBAL.idFromName("juan"));
  return {
    gastoMes: async (mes) => (await stub().gastoMes(mes)).usd,
    registrarGasto: async (mes, modelo, uso, usd) => {
      await stub().registrarGasto(mes, modelo, uso, usd);
    },
  };
}

export function depsDeProduccion(ctx: DurableObjectState, env: Env): DepsMotor {
  return {
    sql: sqlDeDurableObject(ctx.storage.sql),
    env,
    ahora: () => Date.now(),
    fijarAlarma: async (ts) => {
      if (ts === null) await ctx.storage.deleteAlarm();
      else await ctx.storage.setAlarm(ts);
    },
    odoo: odooDe(env),
    config: () => obtenerConfig(env),
    herramientas: () => obtenerHerramientas(env),
    canal: (id) => adaptadorDe(id),
    // Se arma en cada uso: sin ANTHROPIC_API_KEY el Worker arranca igual (iaConfigurada=false evita llamarlo).
    modelo: (id) => fabricaAnthropic(env.ANTHROPIC_API_KEY ?? "")(id),
    global: globalDe(env),
    dormir: (ms) => new Promise((r) => setTimeout(r, ms)),
    uuid: () => crypto.randomUUID(),
    bufferMs: (Number(env.BUFFER_SEGUNDOS) || 15) * 1000,
    iaConfigurada: !!env.ANTHROPIC_API_KEY,
    topeDiario: Number(env.TOPE_DIARIO) || TOPE_DIARIO_POR_DEFECTO,
    urlPublica: env.URL_PUBLICA || undefined,
    urlSitio: env.URL_SITIO || undefined,
    secretoDeMedios: env.JUAN_WORKER_TOKEN,
    transcribir: transcriptorDe(env),
  };
}

export class Conversacion extends DurableObject<Env> {
  private readonly motor: MotorConversacion;

  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env);
    this.motor = new MotorConversacion(depsDeProduccion(ctx, env));
  }

  ingest(e: Entrante) {
    return this.motor.ingest(e);
  }

  /** Cloudflare la llama al vencer la ráfaga, la cola de Odoo o la limpieza. */
  async alarm(): Promise<void> {
    await this.motor.alarma();
  }

  enviarVendedora(s: SolicitudEnviar) {
    return this.motor.enviarVendedora(s);
  }

  fijarEstado(s: { estado: "humano" | "bot"; pausada_hasta?: string | number | null }) {
    return this.motor.fijarEstado(s);
  }

  seguimiento(s: SolicitudSeguimiento) {
    return this.motor.seguimiento(s);
  }

  leerMedio(id: string) {
    return this.motor.leerMedio(id);
  }

  resumen() {
    return this.motor.resumen();
  }
}
