// Salud del Worker: lo que contesta `GET /odoo/salud` y lo que revisa el cron (crons de wrangler.jsonc).
// El cron mira la conexión del puente de WhatsApp y el gasto de IA, y avisa por Telegram a la dueña
// (ALERTA_TELEGRAM_CHAT_ID) UNA vez por problema y otra cuando se arregla. Sin ese chat, solo queda en los logs.

import { canalActivo, mesDelNegocio, type Config } from "./config";
import type { Env } from "./env";
import type { AdaptadorCanal, CanalId, SaludCanal } from "./canales/tipos";
import { TODOS_LOS_CANALES } from "./canales/tipos";

export interface EstadoDeCanal extends SaludCanal {
  activo: boolean;
}

export interface InformeDeSalud {
  ok: boolean;
  version: string;
  entorno: string;
  canales: Record<CanalId, EstadoDeCanal>;
  gasto_ia_mes_usd: number;
  tope_usd: number;
  tope_alcanzado: boolean;
  /** Lo que falta o está mal, en palabras; vacío si todo bien. */
  problemas: string[];
}

export interface DepsSalud {
  env: Env;
  adaptadores: readonly AdaptadorCanal[];
  config(): Promise<Config>;
  gastoMes(mes: string): Promise<number>;
  ahora(): number;
}

const redondear = (n: number) => Math.round(n * 100) / 100;

function conTiempo<T>(p: Promise<T>, ms: number, defecto: T): Promise<T> {
  return Promise.race([p, new Promise<T>((r) => setTimeout(() => r(defecto), ms))]);
}

export async function informeDeSalud(d: DepsSalud): Promise<InformeDeSalud> {
  const cfg = await d.config();
  const gasto = await d.gastoMes(mesDelNegocio(cfg.horario.zona, d.ahora())).catch(() => 0);
  const problemas: string[] = [];
  if (!d.env.JUAN_ODOO_TOKEN) problemas.push("falta JUAN_ODOO_TOKEN: no se puede hablar con Odoo");
  if (!d.env.ANTHROPIC_API_KEY) problemas.push("falta ANTHROPIC_API_KEY: el bot no puede contestar");
  if (!d.env.JUAN_WORKER_TOKEN) problemas.push("falta JUAN_WORKER_TOKEN: Odoo no puede llamar al Worker");

  const canales = {} as Record<CanalId, EstadoDeCanal>;
  for (const id of TODOS_LOS_CANALES) {
    const a = d.adaptadores.find((x) => x.canales.includes(id));
    const activo = canalActivo(cfg, id);
    const s: SaludCanal = a
      ? await conTiempo(a.salud?.(id, d.env) ?? Promise.resolve({ configurado: a.configurado(d.env, id), conectado: null }), 4000, {
          configurado: a.configurado(d.env, id),
          conectado: null,
          detalle: "no contestó a tiempo",
        })
      : { configurado: false, conectado: null };
    canales[id] = { activo, ...s };
    if (activo && !s.configurado) problemas.push(`el canal ${id} está encendido pero le faltan credenciales`);
    if (activo && s.configurado && s.conectado === false) problemas.push(`el canal ${id} no está conectado${s.detalle ? ` (${s.detalle})` : ""}`);
  }

  const tope = cfg.presupuesto_ia_mensual_usd;
  return {
    ok: problemas.length === 0,
    version: d.env.VERSION ?? "dev",
    entorno: d.env.ENTORNO ?? "desconocido",
    canales,
    gasto_ia_mes_usd: redondear(gasto),
    tope_usd: tope,
    tope_alcanzado: tope > 0 && gasto >= tope,
    problemas,
  };
}

// ── Cron: avisar una vez por problema ───────────────────────────────────────

export interface EstadoDeAvisos {
  /** Problemas ya avisados (para no repetir el mismo aviso cada hora). */
  avisados: string[];
}

/** Compara los problemas de ahora con los ya avisados: qué avisar nuevo y qué se arregló. */
export function decidirAvisos(problemas: string[], previo: EstadoDeAvisos): { mensajes: string[]; nuevo: EstadoDeAvisos } {
  const nuevos = problemas.filter((p) => !previo.avisados.includes(p));
  const arreglados = previo.avisados.filter((p) => !problemas.includes(p));
  const mensajes = [
    ...nuevos.map((p) => `Aviso del asistente de D'CASA: ${p}.`),
    ...arreglados.map((p) => `Resuelto en el asistente de D'CASA: ${p}.`),
  ];
  return { mensajes, nuevo: { avisados: problemas } };
}
