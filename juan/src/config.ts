// Configuración editable por la dueña en Odoo (`GET /dcasa/juan/v1/config`), con caché de 60 s.
// Si Odoo no contesta se usa la última buena; si nunca hubo una, los valores por defecto
// de abajo (los mismos del contrato, docs/JUAN.md). El bot nunca se queda mudo por esto.

import type { CanalId } from "./canales/tipos";

/** Quién pone la IA. Se elige en Odoo (`proveedor_ia`); cambiar de uno a otro no toca código. */
export type ProveedorIa = "anthropic" | "meta" | "openai";
export const PROVEEDORES_IA: readonly ProveedorIa[] = ["anthropic", "meta", "openai"];

/**
 * Modelos de cada proveedor cuando Odoo no dice cuál. Meta: SIEMPRE el estándar (`muse-spark-1.3`); el nivel «contributor»
 * entrena con los mensajes y solo se usa si la dueña lo escribe a propósito en Odoo. OpenAI: sin modelo por defecto (hay que elegirlo).
 */
export const MODELOS_POR_DEFECTO: Record<ProveedorIa, { rapido: string; inteligente: string }> = {
  anthropic: { rapido: "claude-haiku-4-5", inteligente: "claude-sonnet-5-5" },
  meta: { rapido: "muse-spark-1.3", inteligente: "muse-spark-1.3" },
  openai: { rapido: "", inteligente: "" },
};

/** Qué forma debe tener el identificador de modelo de cada proveedor: Odoo no puede mandar al Worker a cualquier parte. */
const FORMA_DE_MODELO: Record<ProveedorIa, RegExp> = {
  anthropic: /^claude-[a-z0-9.-]{3,60}$/,
  meta: /^muse-[a-z0-9.-]{3,60}$/,
  openai: /^(?:gpt|chatgpt|o\d)[a-z0-9.-]{0,60}$/,
};

/** Dólares por millón de tokens. `entrada_cache` y `escritura_cache` son opcionales (si faltan: 10 % y 125 % de la entrada). */
export interface PrecioModelo {
  entrada: number;
  salida: number;
  entrada_cache?: number;
  escritura_cache?: number;
}

export interface Horario {
  /** "HH:MM" */
  inicio: string;
  fin: string;
  /**
   * 0 = domingo ... 6 = sábado: la convención de `Date.getDay()` y la que publica Odoo en `GET /config`
   * (addons/dcasa_conversaciones/models/horario.py → `dia_js`). NO es el `weekday()` de Python (lunes = 0).
   */
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
  proveedor_ia: ProveedorIa;
  /** Si el principal falla o no tiene clave, contesta este. null = sin respaldo. */
  proveedor_respaldo_ia: ProveedorIa | null;
  modelo_rapido: string;
  modelo_inteligente: string;
  /** Modelos del proveedor de respaldo; vacío = los de siempre de ese proveedor. */
  modelo_rapido_respaldo: string;
  modelo_inteligente_respaldo: string;
  /** Precio por modelo (USD por millón de tokens). Un modelo sin precio no cuenta como gratis: ver motor/precios.ts. */
  precios_ia: Record<string, PrecioModelo>;
  /** Lo que las vendedoras han aprendido de casos reales (máx. 20 líneas). Va al prompt; NO es fuente de datos. */
  lecciones: string[];
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
  proveedor_ia: "anthropic",
  proveedor_respaldo_ia: null,
  modelo_rapido: "claude-haiku-4-5",
  modelo_inteligente: "claude-sonnet-5-5",
  modelo_rapido_respaldo: "",
  modelo_inteligente_respaldo: "",
  precios_ia: {},
  lecciones: [],
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
const proveedor = (v: unknown): ProveedorIa | null => (typeof v === "string" && (PROVEEDORES_IA as readonly string[]).includes(v.trim().toLowerCase()) ? (v.trim().toLowerCase() as ProveedorIa) : null);

/** El identificador de modelo, solo si tiene la forma del proveedor elegido; lo demás se descarta. */
export function modeloValido(p: ProveedorIa, v: unknown): string {
  return typeof v === "string" && FORMA_DE_MODELO[p].test(v.trim()) ? v.trim() : "";
}

const MAX_LECCIONES = 20;
const MAX_LARGO_LECCION = 300;

/** Las lecciones llegan como texto (una por línea) o como lista. Sin ángulos: no pueden abrir ni cerrar etiquetas del prompt. */
export function normalizarLecciones(v: unknown): string[] {
  const crudas = typeof v === "string" ? [v] : Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : [];
  return crudas
    .flatMap((x) => x.split(/\r?\n/))
    .map((l) => l.replace(/[<>]/g, "").replace(/^\s*[-*•]\s*/, "").trim().slice(0, MAX_LARGO_LECCION))
    .filter(Boolean)
    .slice(0, MAX_LECCIONES);
}

const precioNumero = (v: unknown): number | null => {
  const n = typeof v === "number" ? v : typeof v === "string" ? Number(v) : NaN;
  return Number.isFinite(n) && n >= 0 && n <= 1000 ? n : null;
};

/** `{ "muse-spark-1.3": { entrada: 1.25, salida: 4.25, entrada_cache: 0.15 } }`; también acepta input/output/cache_read. */
export function normalizarPrecios(v: unknown): Record<string, PrecioModelo> {
  if (!esObjeto(v)) return {};
  const salida: Record<string, PrecioModelo> = {};
  for (const [modelo, crudo] of Object.entries(v)) {
    if (!/^[a-z0-9][a-z0-9._-]{2,80}$/i.test(modelo) || !esObjeto(crudo)) continue;
    const entrada = precioNumero(crudo.entrada ?? crudo.input);
    const salidaUsd = precioNumero(crudo.salida ?? crudo.output);
    if (entrada === null || salidaUsd === null) continue;
    const cache = precioNumero(crudo.entrada_cache ?? crudo.cache_read);
    const escritura = precioNumero(crudo.escritura_cache ?? crudo.cache_write);
    salida[modelo] = { entrada, salida: salidaUsd, ...(cache !== null ? { entrada_cache: cache } : {}), ...(escritura !== null ? { escritura_cache: escritura } : {}) };
  }
  return salida;
}

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
  const principal = proveedor(c.proveedor_ia) ?? d.proveedor_ia;
  const respaldo = proveedor(c.proveedor_respaldo_ia);
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
    proveedor_ia: principal,
    proveedor_respaldo_ia: respaldo && respaldo !== principal ? respaldo : null,
    modelo_rapido: modeloValido(principal, c.modelo_rapido) || MODELOS_POR_DEFECTO[principal].rapido,
    modelo_inteligente: modeloValido(principal, c.modelo_inteligente) || MODELOS_POR_DEFECTO[principal].inteligente,
    modelo_rapido_respaldo: respaldo ? modeloValido(respaldo, c.modelo_rapido_respaldo) : "",
    modelo_inteligente_respaldo: respaldo ? modeloValido(respaldo, c.modelo_inteligente_respaldo) : "",
    precios_ia: normalizarPrecios(c.precios_ia),
    lecciones: normalizarLecciones(c.lecciones),
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

/** En el orden de `Horario.dias`: 0 = domingo. */
const DIAS_CORTOS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function minutos(hhmm: string): number {
  const [h, m] = hhmm.split(":").map(Number);
  return h * 60 + m;
}

/** Hora, minuto y día de la semana (0 = domingo) en la zona del negocio. */
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
