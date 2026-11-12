// Instagram por «inicio de sesión de Instagram» (la segunda puerta, `graph.instagram.com`): la llave que vence y la cuenta.
//
// La llave (INSTAGRAM_TOKEN) es una «long-lived Instagram User access token»: vale 60 días y se renueva con
// `GET graph.instagram.com/refresh_access_token?grant_type=ig_refresh_token` si tiene al menos 24 h y no ha vencido; la renovada
// vale otros 60 días desde ese momento (developers.facebook.com/documentation/instagram-platform/reference/refresh_access_token).
// La dueña la pega UNA vez como secreto. El Worker no puede escribir secretos, así que la renovada se guarda en el Durable Object
// `Global` (tabla `llaves`), junto a la huella de la pegada de la que viene: si la dueña pega otra, la huella cambia y manda la
// nueva. Siempre se usa la más nueva. La renueva el cron horario (cuando le quedan menos de 20 días o todavía no se sabe cuándo
// vence; nunca más de un intento al día). La llave NUNCA sale por /salud, por un registro ni en una URL que se registre.

import { createHash } from "node:crypto";
import type { Env } from "../env";
import { urlInstagram } from "./graph";

/** Hay algún secreto de la segunda puerta: Instagram va por ella (si falta algo, /salud dice qué). Sin ninguno, como siempre. */
export function puertaInstagramElegida(env: Env): boolean {
  return !!(env.INSTAGRAM_TOKEN?.trim() || env.INSTAGRAM_APP_SECRET?.trim());
}

/** Por dónde va Instagram (lo dice /salud). */
export const PUERTA_PAGINA = "pagina_facebook";
export const PUERTA_INSTAGRAM = "inicio_sesion_instagram";

const DIA_MS = 86_400_000;
/** Lo que vale una llave larga de Instagram (y la renovada, desde que se renueva). */
export const VIDA_LLAVE_MS = 60 * DIA_MS;
/** Se renueva cuando le quedan menos de esto. */
export const RENOVAR_CON_MENOS_DE_MS = 20 * DIA_MS;
/** Meta solo renueva una llave que tenga al menos 24 h. */
export const EDAD_MINIMA_PARA_RENOVAR_MS = DIA_MS;
/** Nunca más de un intento de renovación al día (salga bien o mal). */
export const ENTRE_INTENTOS_MS = DIA_MS;
/** Con menos de esto, un fallo al renovar ya es un problema (no un aviso). */
export const URGENTE_MS = 7 * DIA_MS;

export const CLAVE_LLAVE = "instagram_llave";
export const CLAVE_CUENTA = "instagram_cuenta";
export const URL_RENOVAR = "https://graph.instagram.com/refresh_access_token";

export interface EstadoLlave {
  /** Huella (16 hex) del INSTAGRAM_TOKEN pegado del que viene esta cadena de llaves. Nunca la llave. */
  semilla: string;
  /** Cuándo vio Juan por primera vez la llave pegada (ms). Esa vence a más tardar a los 60 días de eso. */
  vistaEn: number;
  /** La llave renovada por Juan (la más nueva). Sin renovar todavía: no hay, se usa la pegada. */
  llave?: string;
  /** Cuándo vence la llave vigente (ms): se sabe desde la primera renovación (Meta dice `expires_in`). */
  vence?: number;
  renovadaEn?: number;
  /** El último intento de renovar, saliera bien o mal (para no intentar más de una vez al día). */
  intentoEn?: number;
  /** Por qué falló el último intento (lo que dijo Meta, sin la llave). Sin esto: el último salió bien, o no hubo. */
  error?: string;
}

/** La cuenta de Instagram de D'CASA según `GET /me` (o la variable INSTAGRAM_ACCOUNT_ID). */
export interface CuentaInstagram {
  /** `user_id` (el id que traen los webhooks, según Meta) y el `id` de la app: se aceptan los dos. */
  ids: string[];
  usuario?: string;
  /** Huella de la llave con la que se preguntó (si la dueña pega otra, se vuelve a preguntar). */
  semilla?: string;
  ts?: number;
}

/** Dónde se guardan la llave renovada y la cuenta: el Durable Object `Global` (en las pruebas, un mapa). */
export interface Llavero {
  leer(env: Env, clave: string): Promise<string | null>;
  guardar(env: Env, clave: string, valor: string): Promise<void>;
}

export const llaveroDelGlobal: Llavero = {
  async leer(env, clave) {
    if (!env.GLOBAL) return null;
    return (await env.GLOBAL.get(env.GLOBAL.idFromName("juan")).leerLlave(clave)) ?? null;
  },
  async guardar(env, clave, valor) {
    if (!env.GLOBAL) return;
    await env.GLOBAL.get(env.GLOBAL.idFromName("juan")).guardarLlave(clave, valor);
  },
};

/**
 * Para saber si la llave pegada cambió: SHA-256 en 16 hex. Síncrona a propósito (`node:crypto`, como motor/almacen.ts): va en el
 * camino del webhook y no debe esperar a nadie. La huella solo vive en el Durable Object `Global`.
 */
export function huella(llave: string): string {
  return createHash("sha256").update(llave).digest("hex").slice(0, 16);
}

function leerJson<T>(texto: string | null): T | null {
  if (!texto) return null;
  try {
    return JSON.parse(texto) as T;
  } catch {
    return null;
  }
}

/** El estado guardado, o uno nuevo si la dueña pegó otra llave (otra huella): esa manda y se olvida la cadena anterior. */
export function alDia(guardado: EstadoLlave | null, semilla: string, ahora: number): { estado: EstadoLlave; nuevo: boolean } {
  if (guardado && guardado.semilla === semilla && Number.isFinite(guardado.vistaEn)) return { estado: { ...guardado }, nuevo: false };
  return { estado: { semilla, vistaEn: ahora }, nuevo: true };
}

/** Cuándo vence la llave vigente: la fecha de Meta si ya se renovó (`seguro`), o el tope de la pegada (vista + 60 días). */
export function venceDe(estado: EstadoLlave): { ts: number; seguro: boolean } {
  return estado.vence !== undefined ? { ts: estado.vence, seguro: true } : { ts: estado.vistaEn + VIDA_LLAVE_MS, seguro: false };
}

/** ¿Toca renovar ahora? Con menos de 20 días, o sin saber cuándo vence; nunca dos intentos el mismo día ni una llave de < 24 h. */
export function tocaRenovar(estado: EstadoLlave, ahora: number): boolean {
  if (estado.intentoEn !== undefined && ahora - estado.intentoEn < ENTRE_INTENTOS_MS) return false;
  if (ahora - (estado.renovadaEn ?? estado.vistaEn) < EDAD_MINIMA_PARA_RENOVAR_MS) return false;
  if (estado.vence === undefined) return true; // la primera renovación dice cuándo vence
  if (estado.vence <= ahora) return false; // ya venció: Meta no la renueva; hay que pegar otra
  return estado.vence - ahora < RENOVAR_CON_MENOS_DE_MS;
}

/** El estado de la llave tal como está (sin guardar nada). null = no hay INSTAGRAM_TOKEN. */
export async function leerEstado(env: Env, llavero: Llavero, ahora: number): Promise<EstadoLlave | null> {
  const pegada = env.INSTAGRAM_TOKEN?.trim();
  if (!pegada) return null;
  return alDia(leerJson<EstadoLlave>(await llavero.leer(env, CLAVE_LLAVE)), huella(pegada), ahora).estado;
}

/** Lo que dijo Meta, en corto y sin la llave (Instagram contesta `{error:{message,code}}` o `{error_message,code}`). */
export function motivoDeMeta(status: number, j: unknown, llave: string): string {
  const o = (j && typeof j === "object" ? j : {}) as { error?: { message?: unknown; code?: unknown } | string; error_message?: unknown; code?: unknown };
  const err = typeof o.error === "object" && o.error ? o.error : undefined;
  const texto = String(err?.message ?? o.error_message ?? (typeof o.error === "string" ? o.error : "") ?? "").trim() || "sin detalle";
  const codigo = err?.code ?? o.code;
  const limpio = (llave.length >= 8 ? texto.split(llave).join("…") : texto).replace(/[\u0000-\u001f]/g, " ").slice(0, 120);
  return `HTTP ${status}: ${limpio}${codigo !== undefined ? ` [${String(codigo).slice(0, 10)}]` : ""}`;
}

export interface DepsLlave {
  fetch: typeof fetch;
  llavero: Llavero;
  ahora(): number;
}

export type ResultadoRenovacion = "sin_llave" | "no_toca" | "renovada" | "fallo";

/**
 * El cron (cada hora): renueva la llave si toca. Anota el intento ANTES de llamar a Meta (si algo se cae a la mitad, no se
 * reintenta hasta el día siguiente). Si falla, la llave vigente se sigue usando mientras no venza.
 */
export async function renovarLlave(env: Env, d: DepsLlave): Promise<ResultadoRenovacion> {
  const pegada = env.INSTAGRAM_TOKEN?.trim();
  if (!pegada) return "sin_llave";
  const ahora = d.ahora();
  const { estado, nuevo } = alDia(leerJson<EstadoLlave>(await d.llavero.leer(env, CLAVE_LLAVE)), huella(pegada), ahora);
  const guardar = () => d.llavero.guardar(env, CLAVE_LLAVE, JSON.stringify(estado));
  if (!tocaRenovar(estado, ahora)) {
    if (nuevo) await guardar(); // desde cuándo se conoce la llave pegada: de ahí sale «vence a más tardar»
    return "no_toca";
  }
  const vigente = estado.llave ?? pegada;
  estado.intentoEn = ahora;
  await guardar();
  try {
    // Como lo documenta Meta para esta ruta, la llave va en la consulta: esta URL no se registra nunca (ni en los errores).
    const r = await d.fetch(`${URL_RENOVAR}?grant_type=ig_refresh_token&access_token=${encodeURIComponent(vigente)}`);
    const j = (await r.json().catch(() => null)) as { access_token?: unknown; expires_in?: unknown } | null;
    const nueva = typeof j?.access_token === "string" ? j.access_token.trim() : "";
    if (r.ok && nueva) {
      const segundos = Number(j?.expires_in);
      estado.llave = nueva;
      estado.vence = ahora + (Number.isFinite(segundos) && segundos > 0 ? segundos * 1000 : VIDA_LLAVE_MS);
      estado.renovadaEn = ahora;
      delete estado.error;
      await guardar();
      console.log(`[juan] instagram: llave renovada; vence el ${fechaPanama(estado.vence)}`);
      return "renovada";
    }
    estado.error = motivoDeMeta(r.status, j, vigente);
  } catch {
    estado.error = "no se pudo conectar con Meta";
  }
  await guardar();
  console.warn(`[juan] instagram: no se pudo renovar la llave (${estado.error}); se sigue usando la vigente`);
  return "fallo";
}

/**
 * La cuenta de D'CASA: la variable INSTAGRAM_ACCOUNT_ID si está; si no, la guardada (si es de esta misma llave); si no, se le
 * pregunta a Meta (`GET /me?fields=user_id,username`) y se guarda. null = no se sabe (no hay llave o Meta no contestó).
 */
export async function cuentaDeInstagram(env: Env, d: DepsLlave & { llave(env: Env): Promise<string | undefined> }): Promise<CuentaInstagram | null> {
  const fija = env.INSTAGRAM_ACCOUNT_ID?.trim();
  if (fija) return { ids: [fija] };
  const pegada = env.INSTAGRAM_TOKEN?.trim();
  if (!pegada) return null;
  const semilla = huella(pegada);
  const guardada = leerJson<CuentaInstagram>(await d.llavero.leer(env, CLAVE_CUENTA));
  const valida = guardada && Array.isArray(guardada.ids) && guardada.ids.length > 0 ? guardada : null;
  if (valida && valida.semilla === semilla) return valida;
  const llave = await d.llave(env);
  if (!llave) return valida;
  try {
    // La llave en la cabecera, como en el envío (graph.instagram.com la acepta así): nunca en una URL.
    const r = await d.fetch(`${urlInstagram(env, "me")}?fields=user_id,username`, { headers: { authorization: `Bearer ${llave}` } });
    const j = (await r.json().catch(() => null)) as Record<string, unknown> | null;
    // La documentación muestra `{data:[{user_id, username}]}`; la API suele contestar el objeto suelto: se aceptan los dos.
    const datos = (Array.isArray(j?.data) ? (j!.data as Record<string, unknown>[])[0] : j) ?? {};
    const ids = [datos.user_id, datos.id].map((x) => (typeof x === "string" || typeof x === "number" ? String(x) : "")).filter((x) => /^\d{5,30}$/.test(x));
    if (!r.ok || ids.length === 0) {
      console.warn(`[juan] instagram: /me no dijo cuál es la cuenta (${motivoDeMeta(r.status, j, llave)})`);
      return valida;
    }
    const usuario = typeof datos.username === "string" ? datos.username.replace(/[^\w.]/g, "").slice(0, 40) : undefined;
    const cuenta: CuentaInstagram = { ids: [...new Set(ids)], ...(usuario ? { usuario } : {}), semilla, ts: d.ahora() };
    await d.llavero.guardar(env, CLAVE_CUENTA, JSON.stringify(cuenta));
    return cuenta;
  } catch {
    console.warn("[juan] instagram: /me no contestó (no se pudo conectar con Meta)");
    return valida;
  }
}

/** La cuenta guardada (sin preguntarle a nadie): para /salud. */
export async function cuentaGuardada(env: Env, llavero: Llavero): Promise<CuentaInstagram | null> {
  const fija = env.INSTAGRAM_ACCOUNT_ID?.trim();
  if (fija) return { ids: [fija] };
  const c = leerJson<CuentaInstagram>(await llavero.leer(env, CLAVE_CUENTA));
  return c && Array.isArray(c.ids) && c.ids.length > 0 ? c : null;
}

const FORMATO_PANAMA = new Intl.DateTimeFormat("en-CA", { timeZone: "America/Panama", year: "numeric", month: "2-digit", day: "2-digit" });

/** «AAAA-MM-DD» en la hora de Panamá. */
export function fechaPanama(ts: number): string {
  return FORMATO_PANAMA.format(new Date(ts));
}

/** Días que le quedan, hacia arriba (recién renovada: 60; vencida: 0). */
export function diasQueQuedan(vence: number, ahora: number): number {
  return Math.max(0, Math.ceil((vence - ahora) / DIA_MS));
}
