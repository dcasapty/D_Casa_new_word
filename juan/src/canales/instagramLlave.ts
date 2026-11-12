// Instagram por «inicio de sesión de Instagram» (la segunda puerta, `graph.instagram.com`): la llave que vence y la cuenta.
//
// La llave (INSTAGRAM_TOKEN) es una «long-lived Instagram User access token»: vale 60 días y se renueva con
// `GET graph.instagram.com/refresh_access_token?grant_type=ig_refresh_token` si tiene al menos 24 h y no ha vencido; la renovada
// vale otros 60 días desde ese momento (developers.facebook.com/documentation/instagram-platform/reference/refresh_access_token).
// La dueña la pega UNA vez como secreto. El Worker no puede escribir secretos, así que la renovada se guarda en el Durable Object
// `Global` (tabla `llaves`), junto a la huella de la pegada de la que viene: si la dueña pega otra, la huella cambia y manda la
// nueva. Siempre se usa la más nueva. La renueva el cron horario (cuando le quedan menos de 20 días o todavía no se sabe cuándo
// vence; nunca más de un intento al día). La llave NUNCA sale por /salud ni por un registro.
//
// Todo cambio a lo guardado es un «cambiar si nadie lo cambió» dentro del Durable Object (`Llavero.cambiarSi`): dos renovaciones a
// la vez no se pisan (una reserva el intento y la otra se retira), y un aviso de «llave rechazada» no borra una llave recién renovada.

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

export const DIA_MS = 86_400_000;
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
/** Cuánto vale un aviso de «se ignoraron avisos de otra cuenta» sin que se repita. */
export const VENTANA_AJENOS_MS = 7 * DIA_MS;
/** Una consulta de la suscripción más vieja que esto ya no se muestra. */
export const VIGENCIA_SUSCRIPCION_MS = 3 * 3600_000;
/** Plazos de Meta desde el cron (desde el webhook el de /me es mucho más corto). */
export const PLAZO_CRON_MS = 10_000;

export const CLAVE_LLAVE = "instagram_llave";
export const CLAVE_CUENTA = "instagram_cuenta";
export const CLAVE_AJENOS = "instagram_ajenos";
export const CLAVE_SUSCRIPCION = "instagram_suscripcion";
export const URL_RENOVAR = "https://graph.instagram.com/refresh_access_token";

/** Meta rechazó la llave (código 190: vencida, revocada o inválida). Se borra en cuanto algo sale bien con la vigente. */
export interface Rechazo {
  desde: number;
  /** «al renovarla», «al preguntar la cuenta (/me)» o «al enviar». */
  donde: string;
  motivo: string;
}

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
  rechazada?: Rechazo;
}

/** La cuenta de Instagram de D'CASA según `GET /me`. */
export interface CuentaInstagram {
  /** `user_id` (el id que traen los webhooks, según Meta) y el `id` de la app: se aceptan los dos. */
  ids: string[];
  usuario?: string;
  /** Huella de la llave con la que se preguntó (si la dueña pega otra, se vuelve a preguntar). */
  semilla?: string;
  ts?: number;
}

/** Avisos ignorados por ser de otra cuenta: cuántos desde cuándo (en una ventana de 7 días), el último y de qué cuenta («…1234»). */
export interface Ajenos {
  desde: number;
  ultimo: number;
  cantidad: number;
  cuenta: string;
}

export interface Suscripcion {
  estado: "ok" | "no";
  ts: number;
}

/** Dónde se guardan la llave renovada y la cuenta: el Durable Object `Global` (en las pruebas, un mapa). */
export interface Llavero {
  leer(env: Env, clave: string): Promise<string | null>;
  /** Cambia el valor solo si sigue siendo `antes` (null = no había nada). true = se cambió. Atómico (dentro del Durable Object). */
  cambiarSi(env: Env, clave: string, antes: string | null, despues: string): Promise<boolean>;
}

export const llaveroDelGlobal: Llavero = {
  async leer(env, clave) {
    if (!env.GLOBAL) return null;
    return (await env.GLOBAL.get(env.GLOBAL.idFromName("juan")).leerLlave(clave)) ?? null;
  },
  async cambiarSi(env, clave, antes, despues) {
    if (!env.GLOBAL) return false;
    return env.GLOBAL.get(env.GLOBAL.idFromName("juan")).cambiarLlaveSi(clave, antes, despues);
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

/**
 * Lee, cambia y guarda SOLO si nadie cambió el valor entretanto; si alguien lo cambió, vuelve a leer y a decidir (hasta 5 veces).
 * `cambio` devuelve el valor nuevo, o undefined para dejarlo como está. Devuelve lo que quedó guardado (o null si no se pudo).
 */
export async function actualizar<T>(env: Env, llavero: Llavero, clave: string, cambio: (actual: T | null) => T | undefined): Promise<T | null> {
  for (let i = 0; i < 5; i++) {
    const antes = await llavero.leer(env, clave);
    const actual = leerJson<T>(antes);
    const nuevo = cambio(actual);
    if (nuevo === undefined) return actual;
    if (await llavero.cambiarSi(env, clave, antes, JSON.stringify(nuevo))) return nuevo;
  }
  console.warn(`[juan] instagram: no se pudo guardar ${clave} (otro proceso lo cambiaba a la vez)`);
  return null;
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

type RespuestaMeta = { error?: { message?: unknown; code?: unknown; type?: unknown } | string; error_message?: unknown; error_type?: unknown; code?: unknown } | null;

/** ¿Meta rechazó la LLAVE (vencida, revocada, inválida)? Código 190 (o 102), o el formato viejo de Instagram con OAuthException. */
export function esRechazoDeLlave(j: unknown): boolean {
  const o = (j && typeof j === "object" ? j : {}) as NonNullable<RespuestaMeta>;
  const err = typeof o.error === "object" && o.error ? o.error : undefined;
  const codigo = Number(err?.code ?? o.code);
  if (codigo === 190 || codigo === 102) return true;
  return o.error_type === "OAuthException" && /access token|session/i.test(String(o.error_message ?? ""));
}

/** Lo que dijo Meta, en corto y sin la llave (Instagram contesta `{error:{message,code}}` o `{error_message,code}`). */
export function motivoDeMeta(status: number, j: unknown, llave: string): string {
  const o = (j && typeof j === "object" ? j : {}) as NonNullable<RespuestaMeta>;
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

/** Anota que Meta rechazó la llave (la primera vez: así la frase de /salud no cambia en cada fallo). */
export async function marcarRechazo(env: Env, d: DepsLlave, donde: string, motivo: string): Promise<void> {
  const pegada = env.INSTAGRAM_TOKEN?.trim();
  if (!pegada) return;
  const semilla = huella(pegada);
  const ahora = d.ahora();
  await actualizar<EstadoLlave>(env, d.llavero, CLAVE_LLAVE, (g) => {
    const { estado } = alDia(g, semilla, ahora);
    if (estado.rechazada) return undefined;
    return { ...estado, rechazada: { desde: ahora, donde, motivo } };
  });
}

/** Algo salió bien con la llave vigente: ya no está rechazada. */
export async function limpiarRechazo(env: Env, d: DepsLlave): Promise<void> {
  const pegada = env.INSTAGRAM_TOKEN?.trim();
  if (!pegada) return;
  const semilla = huella(pegada);
  await actualizar<EstadoLlave>(env, d.llavero, CLAVE_LLAVE, (g) => {
    if (!g || g.semilla !== semilla || !g.rechazada) return undefined;
    const { rechazada: _r, ...resto } = g;
    return resto;
  });
}

export type ResultadoRenovacion = "sin_llave" | "no_toca" | "renovada" | "fallo";

/**
 * El cron (cada hora): renueva la llave si toca. El intento se RESERVA antes de llamar a Meta (dentro del Durable Object: si dos lo
 * intentan a la vez, solo uno llama). Si falla, la llave vigente se sigue usando mientras sirva; si Meta la rechaza, /salud lo dice.
 */
export async function renovarLlave(env: Env, d: DepsLlave): Promise<ResultadoRenovacion> {
  const pegada = env.INSTAGRAM_TOKEN?.trim();
  if (!pegada) return "sin_llave";
  const ahora = d.ahora();
  const semilla = huella(pegada);
  let toca = false;
  const reservado = await actualizar<EstadoLlave>(env, d.llavero, CLAVE_LLAVE, (g) => {
    const { estado, nuevo } = alDia(g, semilla, ahora);
    toca = tocaRenovar(estado, ahora);
    if (toca) return { ...estado, intentoEn: ahora };
    return nuevo ? estado : undefined; // desde cuándo se conoce la llave pegada: de ahí sale «vence a más tardar»
  });
  if (!toca || !reservado) return "no_toca";

  const vigente = reservado.llave ?? pegada;
  let resultado: { llave: string; vence: number } | { error: string; rechazo: boolean };
  try {
    // Como lo documenta Meta para esta ruta, la llave va en la consulta: esta URL no se registra nunca (ni en los errores).
    const r = await d.fetch(`${URL_RENOVAR}?grant_type=ig_refresh_token&access_token=${encodeURIComponent(vigente)}`, { signal: AbortSignal.timeout(PLAZO_CRON_MS) });
    const j = (await r.json().catch(() => null)) as { access_token?: unknown; expires_in?: unknown } | null;
    const nueva = typeof j?.access_token === "string" ? j.access_token.trim() : "";
    if (r.ok && nueva) {
      const segundos = Number(j?.expires_in);
      resultado = { llave: nueva, vence: ahora + (Number.isFinite(segundos) && segundos > 0 ? segundos * 1000 : VIDA_LLAVE_MS) };
    } else {
      resultado = { error: motivoDeMeta(r.status, j, vigente), rechazo: esRechazoDeLlave(j) };
    }
  } catch {
    resultado = { error: "no se pudo conectar con Meta", rechazo: false };
  }
  // Se guarda sobre lo que haya AHORA (si la dueña pegó otra llave entretanto, este resultado ya no sirve y se descarta).
  await actualizar<EstadoLlave>(env, d.llavero, CLAVE_LLAVE, (g) => {
    if (!g || g.semilla !== semilla) return undefined;
    if ("llave" in resultado) {
      const { error: _e, rechazada: _r, ...resto } = g;
      return { ...resto, llave: resultado.llave, vence: resultado.vence, renovadaEn: ahora };
    }
    return { ...g, error: resultado.error, ...(resultado.rechazo && !g.rechazada ? { rechazada: { desde: ahora, donde: "al renovarla", motivo: resultado.error } } : {}) };
  });
  if ("llave" in resultado) {
    console.log(`[juan] instagram: llave renovada; vence el ${fechaPanama(resultado.vence)}`);
    return "renovada";
  }
  console.warn(`[juan] instagram: no se pudo renovar la llave (${resultado.error})`);
  return "fallo";
}

/** INSTAGRAM_ACCOUNT_ID, si es un número de cuenta; si tiene otra cosa, se ignora y /salud lo dice. */
export function cuentaFija(env: Env): { id: string | null; mala: boolean } {
  const v = env.INSTAGRAM_ACCOUNT_ID?.trim();
  if (!v) return { id: null, mala: false };
  return /^\d{5,30}$/.test(v) ? { id: v, mala: false } : { id: null, mala: true };
}

/** La cuenta guardada (sin preguntarle a nadie), sea de la llave que sea. */
export async function cuentaGuardada(env: Env, llavero: Llavero): Promise<CuentaInstagram | null> {
  const c = leerJson<CuentaInstagram>(await llavero.leer(env, CLAVE_CUENTA));
  return c && Array.isArray(c.ids) && c.ids.length > 0 ? c : null;
}

/**
 * La cuenta de D'CASA según Meta: la guardada si es de esta misma llave; si no, se pregunta (`GET /me?fields=user_id,username`, con
 * la llave en la cabecera y un plazo) y se guarda. `fallo` = se preguntó y Meta no dijo cuál (se devuelve la guardada vieja, si hay).
 */
export async function descubrirCuenta(env: Env, d: DepsLlave & { llave(env: Env): Promise<string | undefined> }, plazoMs: number): Promise<{ cuenta: CuentaInstagram | null; fallo: boolean }> {
  const pegada = env.INSTAGRAM_TOKEN?.trim();
  if (!pegada) return { cuenta: null, fallo: false };
  const semilla = huella(pegada);
  const guardada = await cuentaGuardada(env, d.llavero);
  if (guardada && guardada.semilla === semilla) return { cuenta: guardada, fallo: false };
  const llave = await d.llave(env);
  if (!llave) return { cuenta: guardada, fallo: true };
  try {
    const r = await d.fetch(`${urlInstagram(env, "me")}?fields=user_id,username`, { headers: { authorization: `Bearer ${llave}` }, signal: AbortSignal.timeout(plazoMs) });
    const j = (await r.json().catch(() => null)) as Record<string, unknown> | null;
    // La documentación muestra `{data:[{user_id, username}]}`; la API suele contestar el objeto suelto: se aceptan los dos.
    const datos = (Array.isArray(j?.data) ? (j!.data as Record<string, unknown>[])[0] : j) ?? {};
    const ids = [datos.user_id, datos.id].map((x) => (typeof x === "string" || typeof x === "number" ? String(x) : "")).filter((x) => /^\d{5,30}$/.test(x));
    if (!r.ok || ids.length === 0) {
      const motivo = motivoDeMeta(r.status, j, llave);
      console.warn(`[juan] instagram: /me no dijo cuál es la cuenta (${motivo})`);
      if (esRechazoDeLlave(j)) await marcarRechazo(env, d, "al preguntar la cuenta (/me)", motivo).catch(() => {});
      return { cuenta: guardada, fallo: true };
    }
    const usuario = typeof datos.username === "string" ? datos.username.replace(/[^\w.]/g, "").slice(0, 40) : undefined;
    const cuenta: CuentaInstagram = { ids: [...new Set(ids)], ...(usuario ? { usuario } : {}), semilla, ts: d.ahora() };
    await actualizar<CuentaInstagram>(env, d.llavero, CLAVE_CUENTA, () => cuenta);
    await limpiarRechazo(env, d).catch(() => {});
    return { cuenta, fallo: false };
  } catch {
    console.warn("[juan] instagram: /me no contestó a tiempo (o no se pudo conectar con Meta)");
    return { cuenta: guardada, fallo: true };
  }
}

/** Cuenta los avisos ignorados por ser de otra cuenta (en una ventana de 7 días), para /salud. Sin datos de clientes. */
export async function anotarAjenos(env: Env, d: DepsLlave, cantidad: number, cuenta: string): Promise<void> {
  const ahora = d.ahora();
  await actualizar<Ajenos>(env, d.llavero, CLAVE_AJENOS, (g) => {
    const sigue = g && ahora - g.ultimo < VENTANA_AJENOS_MS;
    return { desde: sigue ? g.desde : ahora, ultimo: ahora, cantidad: (sigue ? g.cantidad : 0) + cantidad, cuenta: `…${cuenta.slice(-4)}` };
  });
}

/**
 * El cron: ¿Meta tiene a la app suscrita a los mensajes de la cuenta? (`GET /me/subscribed_apps`). Si la consulta no se entiende,
 * no se guarda nada (no se inventa un problema). Meta puede apagar la suscripción tras muchas entregas fallidas.
 */
export async function revisarSuscripcion(env: Env, d: DepsLlave & { llave(env: Env): Promise<string | undefined> }): Promise<void> {
  const llave = await d.llave(env);
  if (!llave) return;
  try {
    const r = await d.fetch(urlInstagram(env, "me/subscribed_apps"), { headers: { authorization: `Bearer ${llave}` }, signal: AbortSignal.timeout(PLAZO_CRON_MS) });
    const j = (await r.json().catch(() => null)) as { data?: { subscribed_fields?: unknown }[] } | null;
    if (!r.ok || !Array.isArray(j?.data)) return;
    const conMensajes = j.data.some((a) => Array.isArray(a?.subscribed_fields) && a.subscribed_fields.includes("messages"));
    const s: Suscripcion = { estado: conMensajes ? "ok" : "no", ts: d.ahora() };
    await actualizar<Suscripcion>(env, d.llavero, CLAVE_SUSCRIPCION, () => s);
  } catch {
    // Sin respuesta: la próxima hora.
  }
}

export async function leerGuardado<T>(env: Env, llavero: Llavero, clave: string): Promise<T | null> {
  return leerJson<T>(await llavero.leer(env, clave));
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
