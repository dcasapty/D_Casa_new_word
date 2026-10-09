// Cliente de Odoo (docs/JUAN.md → «Worker → Odoo»). Va por el service binding `DCASA`
// hacia el Worker `dcasa`, que reenvía a Odoo; las rutas /dcasa/juan/** no existen en internet.
// Odoo duerme tras 30 min sin tráfico (≈10 s para despertar; hasta 7 min tras un despliegue):
// por eso hay plazos largos y reintentos en lo que se puede repetir sin riesgo.

import type { CanalId } from "../canales/tipos";

export class OdooError extends Error {
  constructor(
    mensaje: string,
    readonly estado: number,
    readonly reintentable: boolean,
    /** Falta el token de Odoo: no es un fallo de Odoo ni de este mensaje, y se arregla pegando el secreto. */
    readonly sinCredenciales = false,
  ) {
    super(mensaje);
    this.name = "OdooError";
  }
}

export interface AdjuntoOdoo {
  tipo: "imagen" | "audio" | "documento" | "video";
  url?: string | null;
  nombre?: string;
  mime?: string;
  /** Qué entendió el lector de imágenes (solo con RECONOCER_IMAGENES=1): para que Odoo avise a la dueña en paralelo. */
  clase?: "producto" | "publicacion" | "comprobante" | "identidad" | "otra";
  /** Comprobante o documento de identidad: Odoo no se lo muestra a la IA. */
  sensible?: boolean;
}

export interface CuerpoMensaje {
  canal: CanalId;
  id_externo: string;
  nombre?: string;
  celular?: string;
  id_mensaje: string;
  direccion: "entrante" | "saliente";
  autor: "cliente" | "bot" | "vendedora";
  texto: string;
  adjuntos?: AdjuntoOdoo[];
  /** ISO 8601 UTC. */
  ts: string;
}

export interface RespuestaMensaje {
  ok?: boolean;
  conversacion_id?: number | null;
  partner_id?: number | null;
  estado?: string;
  bot_activo?: boolean;
  /** ISO, epoch o null: se interpreta con `aMilisegundosOdoo`. */
  pausada_hasta?: string | number | null;
  dentro_de_horario?: boolean;
  /** Lo que una vendedora le dejó dicho al bot al devolverle la conversación (`null` = nada). Si el campo no viene, no se toca. */
  nota_para_el_bot?: string | null;
}

export type EstadoOdoo = Pick<RespuestaMensaje, "estado" | "bot_activo" | "pausada_hasta" | "dentro_de_horario" | "nota_para_el_bot">;

export interface DefHerramienta {
  nombre: string;
  descripcion: string;
  /** JSON Schema (type: object). */
  parametros: Record<string, unknown>;
}

export interface ResultadoHerramienta {
  ok: boolean;
  resultado?: unknown;
  error?: string;
}

export interface CuerpoSeguimientoHecho {
  conversacion_id: number;
  numero: 1 | 2;
  resultado: "enviado" | "descartado";
  motivo?: string;
}

export interface CuerpoEscribiendo {
  canal: CanalId;
  id_externo: string;
  activo: boolean;
}

/** Lo que el motor necesita de Odoo. En las pruebas se sustituye por un doble. */
export interface OdooApi {
  mensaje(cuerpo: CuerpoMensaje): Promise<RespuestaMensaje>;
  estado(canal: CanalId, id_externo: string): Promise<EstadoOdoo>;
  config(): Promise<unknown>;
  herramientas(): Promise<DefHerramienta[]>;
  herramienta(nombre: string, argumentos: Record<string, unknown>, conversacion_id: number | null): Promise<ResultadoHerramienta>;
  seguimientoHecho(cuerpo: CuerpoSeguimientoHecho): Promise<void>;
  /** Opcional: «el asistente está preparando una respuesta» para las pantallas de las vendedoras. Nunca es crítico. */
  escribiendo?(cuerpo: CuerpoEscribiendo): Promise<void>;
}

export interface OpcionesCliente {
  /** Pausa entre reintentos; las pruebas la ponen en 0. */
  dormir?: (ms: number) => Promise<void>;
  plazoMs?: number;
}

const BASE = "https://dcasa/dcasa/juan/v1";
const REINTENTABLES = new Set([408, 425, 429, 500, 502, 503, 504]);

export class OdooCliente implements OdooApi {
  private readonly dormir: (ms: number) => Promise<void>;
  private readonly plazoMs: number;

  constructor(
    private readonly fetcher: Pick<Fetcher, "fetch">,
    private readonly token: string,
    opciones: OpcionesCliente = {},
  ) {
    this.dormir = opciones.dormir ?? ((ms) => new Promise((r) => setTimeout(r, ms)));
    this.plazoMs = opciones.plazoMs ?? 45_000;
  }

  /** Una llamada, con `reintentos` extra SOLO si es seguro repetirla. */
  private async llamar<T>(metodo: "GET" | "POST", ruta: string, cuerpo: unknown, reintentos: number, plazoMs = this.plazoMs): Promise<T> {
    if (!this.token) throw new OdooError("Falta JUAN_ODOO_TOKEN", 0, true, true);
    let ultimo: unknown = null;
    for (let intento = 0; intento <= reintentos; intento++) {
      if (intento > 0) await this.dormir(Math.min(8000, 700 * 2 ** (intento - 1)));
      try {
        const r = await this.fetcher.fetch(`${BASE}${ruta}`, {
          method: metodo,
          headers: {
            authorization: `Bearer ${this.token}`,
            accept: "application/json",
            ...(cuerpo !== undefined ? { "content-type": "application/json; charset=utf-8" } : {}),
          },
          body: cuerpo !== undefined ? JSON.stringify(cuerpo) : undefined,
          signal: AbortSignal.timeout(plazoMs),
        });
        const texto = await r.text();
        let json: unknown = null;
        try {
          json = texto ? JSON.parse(texto) : null;
        } catch {
          /* cuerpo que no es JSON: se informa abajo */
        }
        if (r.ok) return (json ?? {}) as T;
        const detalle = (json as { error?: string } | null)?.error ?? texto.slice(0, 200);
        const e = new OdooError(`Odoo ${metodo} ${ruta} → ${r.status} ${detalle}`, r.status, REINTENTABLES.has(r.status));
        if (!e.reintentable) throw e;
        ultimo = e;
      } catch (e) {
        if (e instanceof OdooError && !e.reintentable) throw e;
        // Red caída, plazo vencido u Odoo despertando.
        ultimo = e instanceof OdooError ? e : new OdooError(`Odoo ${metodo} ${ruta}: ${String(e)}`, 0, true);
      }
    }
    throw ultimo instanceof Error ? ultimo : new OdooError(String(ultimo), 0, true);
  }

  /** Idempotente por `id_mensaje`: se puede repetir. */
  mensaje(cuerpo: CuerpoMensaje): Promise<RespuestaMensaje> {
    return this.llamar<RespuestaMensaje>("POST", "/mensaje", cuerpo, 1, 25_000);
  }

  estado(canal: CanalId, id_externo: string): Promise<EstadoOdoo> {
    const q = new URLSearchParams({ canal, id_externo });
    return this.llamar<EstadoOdoo>("GET", `/estado?${q}`, undefined, 1, 15_000);
  }

  config(): Promise<unknown> {
    return this.llamar<unknown>("GET", "/config", undefined, 1, 10_000);
  }

  async herramientas(): Promise<DefHerramienta[]> {
    return normalizarHerramientas(await this.llamar<unknown>("GET", "/herramientas", undefined, 1, 10_000));
  }

  /**
   * Ejecutar una herramienta NO se repite solo: una nota o una oportunidad podrían duplicarse.
   * Si falla, el modelo recibe el error y lo dice con honestidad.
   */
  async herramienta(nombre: string, argumentos: Record<string, unknown>, conversacion_id: number | null): Promise<ResultadoHerramienta> {
    try {
      const r = await this.llamar<{ ok?: boolean; resultado?: unknown; error?: string }>(
        "POST",
        "/herramienta",
        { nombre, argumentos, conversacion_id },
        0,
        30_000,
      );
      return r.ok === false ? { ok: false, error: r.error ?? "la herramienta falló" } : { ok: true, resultado: r.resultado };
    } catch (e) {
      return { ok: false, error: e instanceof Error ? e.message : String(e) };
    }
  }

  async seguimientoHecho(cuerpo: CuerpoSeguimientoHecho): Promise<void> {
    await this.llamar("POST", "/seguimiento/hecho", cuerpo, 2);
  }

  /** Sin reintentos y con plazo corto: un «escribiendo» tardío no sirve, y jamás debe frenar una respuesta. */
  async escribiendo(cuerpo: CuerpoEscribiendo): Promise<void> {
    await this.llamar("POST", "/escribiendo", cuerpo, 0, 5_000);
  }
}

// ── Herramientas: tolerancia con la forma exacta que mande Odoo ─────────────

const NOMBRE_VALIDO = /^[a-zA-Z0-9_-]{1,64}$/;

/** Acepta `[...]`, `{herramientas: [...]}` o `{resultado: [...]}`; cada una con nombres de campo en español o inglés. */
export function normalizarHerramientas(crudo: unknown): DefHerramienta[] {
  const obj = crudo as Record<string, unknown> | unknown[] | null;
  const lista = Array.isArray(obj)
    ? obj
    : Array.isArray(obj?.herramientas)
      ? obj.herramientas
      : Array.isArray(obj?.resultado)
        ? obj.resultado
        : Array.isArray(obj?.tools)
          ? obj.tools
          : [];
  const salida: DefHerramienta[] = [];
  const vistos = new Set<string>();
  for (const it of lista as Record<string, unknown>[]) {
    if (!it || typeof it !== "object") continue;
    const nombre = String(it.nombre ?? it.name ?? "");
    if (!NOMBRE_VALIDO.test(nombre) || vistos.has(nombre)) continue;
    vistos.add(nombre);
    const esquema = it.parametros ?? it.parameters ?? it.esquema ?? it.input_schema ?? it.inputSchema ?? it.schema;
    salida.push({
      nombre,
      descripcion: String(it.descripcion ?? it.description ?? ""),
      parametros: esquemaDeObjeto(esquema),
    });
  }
  return salida;
}

function esquemaDeObjeto(esquema: unknown): Record<string, unknown> {
  if (!esquema || typeof esquema !== "object" || Array.isArray(esquema)) return { type: "object", properties: {} };
  const e = { ...(esquema as Record<string, unknown>) };
  if (e.type === "object") {
    e.properties ??= {};
    return e;
  }
  if (e.type === undefined && e.properties && typeof e.properties === "object") return { ...e, type: "object" };
  // Un mapa de propiedades sin envoltorio.
  if (e.type === undefined) return { type: "object", properties: e };
  return { type: "object", properties: {} };
}

/** Caché de la lista de herramientas (cambia poco). Si Odoo falla, sirve la última buena. */
export class CargadorHerramientas {
  private ultima: { lista: DefHerramienta[]; en: number } | null = null;
  constructor(
    private readonly traer: () => Promise<DefHerramienta[]>,
    private readonly ahora: () => number = Date.now,
    private readonly ttlMs = 5 * 60_000,
  ) {}

  async obtener(): Promise<DefHerramienta[]> {
    const t = this.ahora();
    if (this.ultima && t - this.ultima.en < this.ttlMs) return this.ultima.lista;
    try {
      const lista = await this.traer();
      // Una lista vacía casi seguro es un error de Odoo: mejor la última buena.
      if (lista.length > 0 || !this.ultima) this.ultima = { lista, en: t };
      return this.ultima.lista;
    } catch (e) {
      console.warn("[herramientas] Odoo no respondió:", String(e));
      return this.ultima?.lista ?? [];
    }
  }
}

/** `pausada_hasta` puede llegar como ISO, epoch en segundos o en milisegundos. null = sin fecha. */
export function aMilisegundosOdoo(v: string | number | null | undefined): number | null {
  if (v === null || v === undefined || v === "") return null;
  if (typeof v === "number") return v < 1e12 ? v * 1000 : v;
  if (/^\d+$/.test(v)) return aMilisegundosOdoo(Number(v));
  // Odoo suele mandar "2026-10-09 14:03:00" (UTC, sin zona).
  const iso = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}/.test(v) ? v.replace(" ", "T") + (/[zZ]|[+-]\d{2}:?\d{2}$/.test(v) ? "" : "Z") : v;
  const t = Date.parse(iso);
  return Number.isFinite(t) ? t : null;
}
