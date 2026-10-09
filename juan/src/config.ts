// Configuración editable por la dueña en Odoo (`GET /dcasa/juan/v1/config`), con caché de 60 s.
// Si Odoo no contesta se usa la última buena; si nunca hubo una, los valores por defecto
// de abajo (los mismos del contrato, docs/JUAN.md). El bot nunca se queda mudo por esto.

import type { CanalId } from "./canales/tipos";

export interface Horario {
  /** "HH:MM" */
  inicio: string;
  fin: string;
  /** 0 = lunes ... 6 = domingo (como el `weekday()` de Python/Odoo). */
  dias: number[];
  zona: string;
}

export interface Config {
  nombre_publico: string;
  bot_activo_global: boolean;
  canales_activos: Partial<Record<CanalId, boolean>>;
  horario: Horario;
  seguimiento: {
    primero_horas: number;
    segundo_dias: number;
    solo_horario_laboral: boolean;
    maximo: number;
  };
  presupuesto_ia_mensual_usd: number;
  modelo_rapido: string;
  modelo_inteligente: string;
  mensaje_bienvenida: string;
  texto_privacidad_corto: string;
  palabras_prohibidas: string[];
  pausa_por_defecto_minutos: number;
}

export const CONFIG_POR_DEFECTO: Config = {
  nombre_publico: "el equipo de D'CASA",
  bot_activo_global: true,
  canales_activos: {},
  horario: { inicio: "08:00", fin: "17:00", dias: [0, 1, 2, 3, 4, 5, 6], zona: "America/Panama" },
  seguimiento: { primero_horas: 5, segundo_dias: 5, solo_horario_laboral: true, maximo: 2 },
  presupuesto_ia_mensual_usd: 30,
  modelo_rapido: "claude-haiku-4-5",
  modelo_inteligente: "claude-sonnet-5-5",
  mensaje_bienvenida: "",
  texto_privacidad_corto: "",
  palabras_prohibidas: [],
  pausa_por_defecto_minutos: 120,
};

/** Canales que arrancan encendidos si Odoo no dice nada. La Cloud API y Meta empiezan APAGADOS. */
const ENCENDIDOS_POR_DEFECTO: Record<CanalId, boolean> = {
  telegram: true,
  whatsapp_qr: true,
  whatsapp_cloud: false,
  messenger: false,
  instagram: false,
};

export function canalActivo(cfg: Config, canal: CanalId): boolean {
  const v = cfg.canales_activos[canal];
  return typeof v === "boolean" ? v : ENCENDIDOS_POR_DEFECTO[canal];
}

const esObjeto = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
const texto = (v: unknown, defecto: string) => (typeof v === "string" && v.trim() ? v.trim() : defecto);
const numero = (v: unknown, defecto: number, min: number, max: number) => {
  const n = typeof v === "number" ? v : typeof v === "string" ? Number(v) : NaN;
  return Number.isFinite(n) ? Math.min(max, Math.max(min, n)) : defecto;
};
const hora = (v: unknown, defecto: string) => (typeof v === "string" && /^\d{1,2}:\d{2}$/.test(v.trim()) ? v.trim() : defecto);
/** Un identificador de modelo de Anthropic; lo demás se descarta (Odoo no puede mandar al Worker a otro proveedor). */
const modelo = (v: unknown, defecto: string) => (typeof v === "string" && /^claude-[a-z0-9.-]{3,60}$/.test(v.trim()) ? v.trim() : defecto);

/** Convierte lo que conteste Odoo en una Config completa y segura. Nunca lanza. */
export function normalizarConfig(crudo: unknown): Config {
  const d = CONFIG_POR_DEFECTO;
  const c = esObjeto(crudo) ? crudo : {};
  const h = esObjeto(c.horario) ? c.horario : {};
  const s = esObjeto(c.seguimiento) ? c.seguimiento : {};
  const ca = esObjeto(c.canales_activos) ? c.canales_activos : {};
  const canales: Partial<Record<CanalId, boolean>> = {};
  for (const id of Object.keys(ENCENDIDOS_POR_DEFECTO) as CanalId[]) {
    if (typeof ca[id] === "boolean") canales[id] = ca[id] as boolean;
  }
  const dias = Array.isArray(h.dias)
    ? [...new Set(h.dias.map(Number).filter((n) => Number.isInteger(n) && n >= 0 && n <= 6))]
    : d.horario.dias;
  return {
    nombre_publico: texto(c.nombre_publico, d.nombre_publico),
    bot_activo_global: typeof c.bot_activo_global === "boolean" ? c.bot_activo_global : d.bot_activo_global,
    canales_activos: canales,
    horario: {
      inicio: hora(h.inicio, d.horario.inicio),
      fin: hora(h.fin, d.horario.fin),
      dias: dias.length ? dias : d.horario.dias,
      zona: texto(h.zona, d.horario.zona),
    },
    seguimiento: {
      primero_horas: numero(s.primero_horas, d.seguimiento.primero_horas, 0, 24 * 30),
      segundo_dias: numero(s.segundo_dias, d.seguimiento.segundo_dias, 0, 365),
      solo_horario_laboral:
        typeof s.solo_horario_laboral === "boolean" ? s.solo_horario_laboral : d.seguimiento.solo_horario_laboral,
      maximo: numero(s.maximo, d.seguimiento.maximo, 0, 2),
    },
    presupuesto_ia_mensual_usd: numero(c.presupuesto_ia_mensual_usd, d.presupuesto_ia_mensual_usd, 0, 100000),
    modelo_rapido: modelo(c.modelo_rapido, d.modelo_rapido),
    modelo_inteligente: modelo(c.modelo_inteligente, d.modelo_inteligente),
    mensaje_bienvenida: typeof c.mensaje_bienvenida === "string" ? c.mensaje_bienvenida.trim() : "",
    texto_privacidad_corto: typeof c.texto_privacidad_corto === "string" ? c.texto_privacidad_corto.trim() : "",
    palabras_prohibidas: Array.isArray(c.palabras_prohibidas)
      ? c.palabras_prohibidas.filter((p): p is string => typeof p === "string" && p.trim().length > 0).map((p) => p.trim())
      : [],
    pausa_por_defecto_minutos: numero(c.pausa_por_defecto_minutos, d.pausa_por_defecto_minutos, 1, 60 * 24 * 14),
  };
}

export const CONFIG_TTL_MS = 60_000;

/**
 * Caché de 60 s de la configuración. Una instancia por isolate; si Odoo falla se sirve la última buena
 * (aunque esté vencida) para que el bot siga contestando.
 */
export class CargadorConfig {
  private ultima: { config: Config; en: number } | null = null;
  private pendiente: Promise<Config> | null = null;

  constructor(
    private readonly traer: () => Promise<unknown>,
    private readonly ahora: () => number = Date.now,
  ) {}

  async obtener(): Promise<Config> {
    const t = this.ahora();
    if (this.ultima && t - this.ultima.en < CONFIG_TTL_MS) return this.ultima.config;
    // Varias conversaciones a la vez comparten una sola ida a Odoo.
    this.pendiente ??= this.refrescar().finally(() => {
      this.pendiente = null;
    });
    return this.pendiente;
  }

  private async refrescar(): Promise<Config> {
    try {
      const config = normalizarConfig(await this.traer());
      this.ultima = { config, en: this.ahora() };
      return config;
    } catch (e) {
      console.warn("[config] Odoo no respondió; se usa la última configuración buena:", String(e));
      if (this.ultima) return this.ultima.config;
      return CONFIG_POR_DEFECTO;
    }
  }
}

// ── Horario ────────────────────────────────────────────────────────────────

const DIAS_CORTOS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function minutos(hhmm: string): number {
  const [h, m] = hhmm.split(":").map(Number);
  return h * 60 + m;
}

/** Hora, minuto y día de la semana (0 = lunes) en la zona del negocio. */
export function relojDelNegocio(zona: string, ms: number): { minutosDelDia: number; dia: number } {
  let partes: Intl.DateTimeFormatPart[];
  try {
    partes = new Intl.DateTimeFormat("en-US", {
      timeZone: zona,
      hour: "numeric",
      minute: "numeric",
      hourCycle: "h23",
      weekday: "short",
    }).formatToParts(new Date(ms));
  } catch {
    return relojDelNegocio("America/Panama", ms);
  }
  const get = (t: string) => partes.find((p) => p.type === t)?.value ?? "0";
  return { minutosDelDia: Number(get("hour")) * 60 + Number(get("minute")), dia: Math.max(0, DIAS_CORTOS.indexOf(get("weekday"))) };
}

/** ¿Estamos dentro del horario de atención de las vendedoras? */
export function dentroDeHorario(horario: Horario, ms: number): boolean {
  const { minutosDelDia, dia } = relojDelNegocio(horario.zona, ms);
  return horario.dias.includes(dia) && minutosDelDia >= minutos(horario.inicio) && minutosDelDia < minutos(horario.fin);
}

/** "2026-10" según la zona del negocio: el mes del tope de IA. */
export function mesDelNegocio(zona: string, ms: number): string {
  try {
    const p = new Intl.DateTimeFormat("en-CA", { timeZone: zona, year: "numeric", month: "2-digit" }).format(new Date(ms));
    return p.slice(0, 7);
  } catch {
    return new Date(ms).toISOString().slice(0, 7);
  }
}
