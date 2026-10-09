// Salud del Worker: lo que contestan `GET /odoo/salud` (con token) y `GET /salud` (público, sin datos sensibles),
// y lo que revisa el cron (crons de wrangler.jsonc).
//
// El Worker arranca SIN secretos (la dueña los pega en el panel de Cloudflare después del primer despliegue,
// docs/JUAN_WORKER.md). Mientras falten, no se cae: responde con un mensaje claro. Aquí solo viajan NOMBRES de
// secretos y estados; jamás un valor.

import { canalActivo, mesDelNegocio, type Config } from "./config";
import type { Env } from "./env";
import type { AdaptadorCanal, CanalId, SaludCanal } from "./canales/tipos";
import { TODOS_LOS_CANALES } from "./canales/tipos";

/** Lo que el Worker necesita SIEMPRE, con qué canal o pieza lo usa y para qué (solo nombres). */
export const SECRETOS_GENERALES: { nombre: keyof Env & string; paraQue: string }[] = [
  { nombre: "JUAN_ODOO_TOKEN", paraQue: "hablar con Odoo (mensajes, configuración, herramientas)" },
  { nombre: "JUAN_WORKER_TOKEN", paraQue: "que Odoo pueda llamar a este Worker (enviar, estado, seguimiento, salud)" },
  { nombre: "ANTHROPIC_API_KEY", paraQue: "la IA que contesta a los clientes" },
];

export interface EstadoDeCanal extends SaludCanal {
  activo: boolean;
}

export interface InformeDeSalud {
  ok: boolean;
  /** Una frase para una persona: qué pasa y qué hacer. */
  mensaje: string;
  version: string;
  entorno: string;
  /** NOMBRES de los secretos generales que faltan. */
  secretos_faltantes: string[];
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
  /** false = no se pregunta a nadie por la red (el endpoint público no debe poder usarse para molestar al puente). */
  consultarConexiones?: boolean;
}

const redondear = (n: number) => Math.round(n * 100) / 100;

function conTiempo<T>(p: Promise<T>, ms: number, defecto: T): Promise<T> {
  return Promise.race([p, new Promise<T>((r) => setTimeout(() => r(defecto), ms))]);
}

export function secretosGeneralesFaltantes(env: Env): string[] {
  return SECRETOS_GENERALES.filter((s) => !env[s.nombre]).map((s) => s.nombre);
}

/** La frase que se lee primero. */
export function resumenParaPersonas(faltantes: string[], canales: Record<CanalId, EstadoDeCanal>, problemas: string[]): string {
  if (faltantes.includes("ANTHROPIC_API_KEY")) {
    return "Falta ANTHROPIC_API_KEY: el asistente todavía no puede contestar a los clientes. Pégala en Cloudflare (Worker → Settings → Variables and Secrets).";
  }
  const activos = TODOS_LOS_CANALES.filter((c) => canales[c].activo);
  const listos = activos.filter((c) => canales[c].configurado);
  if (listos.length === 0) {
    return "Ningún canal está listo todavía: faltan secretos de los canales encendidos en Odoo (mira «canales» para ver cuáles).";
  }
  if (problemas.length > 0) return `Hay ${problemas.length} cosa(s) por revisar: ${problemas[0]}.`;
  return "Todo en orden.";
}

export async function informeDeSalud(d: DepsSalud): Promise<InformeDeSalud> {
  const consultar = d.consultarConexiones !== false;
  const cfg = await d.config();
  const gasto = await d.gastoMes(mesDelNegocio(cfg.horario.zona, d.ahora())).catch(() => 0);
  const secretos = secretosGeneralesFaltantes(d.env);
  const problemas: string[] = secretos.map((s) => {
    const para = SECRETOS_GENERALES.find((x) => x.nombre === s)!.paraQue;
    return `falta ${s} (${para})`;
  });

  const canales = {} as Record<CanalId, EstadoDeCanal>;
  for (const id of TODOS_LOS_CANALES) {
    const a = d.adaptadores.find((x) => x.canales.includes(id));
    const activo = canalActivo(cfg, id);
    const base: SaludCanal = a
      ? { configurado: a.configurado(d.env, id), faltan: a.faltantes(d.env, id), conectado: null }
      : { configurado: false, faltan: [], conectado: null };
    const s: SaludCanal =
      a && consultar && base.configurado && a.salud
        ? await conTiempo(a.salud(id, d.env), 4000, { ...base, conectado: null, detalle: "no contestó a tiempo" })
        : base;
    canales[id] = { activo, ...s };
    if (activo && !s.configurado) problemas.push(`el canal ${id} está encendido pero faltan: ${(s.faltan ?? []).join(", ") || "credenciales"}`);
    if (activo && s.configurado && s.conectado === false) problemas.push(`el canal ${id} no está conectado${s.detalle ? ` (${s.detalle})` : ""}`);
  }

  const tope = cfg.presupuesto_ia_mensual_usd;
  return {
    ok: problemas.length === 0,
    mensaje: resumenParaPersonas(secretos, canales, problemas),
    version: d.env.VERSION ?? "dev",
    entorno: d.env.ENTORNO ?? "desconocido",
    secretos_faltantes: secretos,
    canales,
    gasto_ia_mes_usd: redondear(gasto),
    tope_usd: tope,
    tope_alcanzado: tope > 0 && gasto >= tope,
    problemas,
  };
}

/**
 * Lo único que se muestra sin token: si el Worker está vivo, qué NOMBRES de secretos faltan y el estado de cada canal.
 * Sin gasto, sin tope, sin detalles de conexión.
 */
export interface InformePublico {
  ok: boolean;
  mensaje: string;
  version: string;
  entorno: string;
  secretos_faltantes: string[];
  canales: Record<CanalId, { activo: boolean; configurado: boolean; faltan: string[] }>;
}

export async function informePublico(d: DepsSalud): Promise<InformePublico> {
  const i = await informeDeSalud({ ...d, consultarConexiones: false });
  return {
    ok: i.ok,
    mensaje: i.mensaje,
    version: i.version,
    entorno: i.entorno,
    secretos_faltantes: i.secretos_faltantes,
    canales: Object.fromEntries(
      TODOS_LOS_CANALES.map((c) => [c, { activo: i.canales[c].activo, configurado: i.canales[c].configurado, faltan: i.canales[c].faltan ?? [] }]),
    ) as InformePublico["canales"],
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
