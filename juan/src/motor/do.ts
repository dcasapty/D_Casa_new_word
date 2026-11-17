// El Durable Object de una conversación: SQLite propio, alarma para la ráfaga de 15 s, la cola de Odoo y la bandeja de Meta.
// La lógica vive en MotorConversacion (motor/conversacion.ts); esto solo le presta Cloudflare.
// Un objeto por `canal:id_externo`: dos mensajes de la misma persona se atienden uno a la vez.

import { DurableObject } from "cloudflare:workers";
import { adaptadorDe } from "../canales";
import type { Entrante } from "../canales/tipos";
import type { Env } from "../env";
import { mesDelNegocio } from "../config";
import { obtenerConfig, obtenerHerramientas, odooDe } from "../odoo/fabrica";
import { MotorConversacion, type DepsMotor, type GlobalApi, type NotaDeRespuestaAComentario, type SolicitudEnviar, type SolicitudSeguimiento } from "./conversacion";
import { fabricaDeProduccion, proveedoresConClave } from "./proveedores";
import { USO_VACIO } from "./precios";
import { sqlDeDurableObject } from "./sql";
import { CONCEPTO_VOZ_WHATSAPP, transcriptorDe } from "./transcribir";
import { lectorDeImagenes } from "./vision";
import { TOPE_DIARIO_POR_DEFECTO } from "./antispam";

export function globalDe(env: Env): GlobalApi {
  const stub = () => env.GLOBAL.get(env.GLOBAL.idFromName("juan"));
  return {
    gastoMes: async (mes) => (await stub().gastoMes(mes)).usd,
    registrarGasto: async (mes, modelo, uso, usd, estimado, dia) => {
      await stub().registrarGasto(mes, modelo, uso, usd, estimado, dia);
    },
    guardarSalud: async (clave, json) => {
      await stub().guardarSalud(clave, json);
    },
    reservarRespuestaPublica: async (tope) => stub().reservarRespuestaPublica(tope),
    reservarRespuestaPrivada: async (tope) => stub().reservarRespuestaPrivada(tope),
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
    // Se arma en cada uso: sin ninguna clave de IA el Worker arranca igual (proveedoresDisponibles vacío evita llamarla).
    modelo: (sel) => fabricaDeProduccion(env)(sel),
    proveedoresDisponibles: () => proveedoresConClave(env),
    global: globalDe(env),
    dormir: (ms) => new Promise((r) => setTimeout(r, ms)),
    uuid: () => crypto.randomUUID(),
    bufferMs: (Number(env.BUFFER_SEGUNDOS) || 15) * 1000,
    topeDiario: Number(env.TOPE_DIARIO) || TOPE_DIARIO_POR_DEFECTO,
    urlPublica: env.URL_PUBLICA || undefined,
    urlSitio: env.URL_SITIO || undefined,
    secretoDeMedios: env.JUAN_WORKER_TOKEN,
    // Lo que cobra Cloudflare por cada nota, en su propio renglón de Costos de IA (aparte del gasto de Juan y de «Por pagar a Meta»).
    transcribir: transcriptorDe(env, async (usd, estimado) => {
      const cfg = await obtenerConfig(env);
      await globalDe(env).registrarGasto(mesDelNegocio(cfg.horario.zona, Date.now()), CONCEPTO_VOZ_WHATSAPP, USO_VACIO, usd, estimado);
    }),
    mirarImagen: lectorDeImagenes(env),
    // La conversación de otro id (la respuesta privada a un comentario que Meta entregó a otro id: motor → `avisarAlOtroDestinatario`).
    conversacion: (canal, id) => env.CONVERSACION.get(env.CONVERSACION.idFromName(`${canal}:${id}`)) as unknown as { anotarRespuestaDeComentario(n: NotaDeRespuestaAComentario): Promise<unknown> },
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

  /** Webhooks de Meta: guardar el mensaje crudo antes de contestar 200 (motor/conversacion.ts → `guardarRecibido`). */
  guardarRecibido(e: Entrante) {
    return this.motor.guardarRecibido(e);
  }

  /** Cloudflare la llama al vencer la ráfaga, la cola de Odoo o la limpieza. */
  async alarm(): Promise<void> {
    await this.motor.alarma();
  }

  enviarVendedora(s: SolicitudEnviar) {
    return this.motor.enviarVendedora(s);
  }

  fijarEstado(s: { estado: "humano" | "bot"; pausada_hasta?: string | number | null; nota_para_el_bot?: string | null }) {
    return this.motor.fijarEstado(s);
  }

  seguimiento(s: SolicitudSeguimiento) {
    return this.motor.seguimiento(s);
  }

  leerMedio(id: string) {
    return this.motor.leerMedio(id);
  }

  olvidar() {
    return this.motor.olvidar();
  }

  /** Otra conversación avisa que Meta le entregó a ESTE id la respuesta privada a un comentario (motor → `anotarRespuestaDeComentario`). */
  anotarRespuestaDeComentario(n: NotaDeRespuestaAComentario) {
    return this.motor.anotarRespuestaDeComentario(n);
  }

  resumen() {
    return this.motor.resumen();
  }
}
