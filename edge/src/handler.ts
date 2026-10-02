import {
  CONDITIONAL_HEADERS,
  conNoindex,
  forwardedHeaders,
  isCacheableRequest,
  isCacheableResponse,
  notModified,
  notModifiedResponse,
  route,
  rutaEstatica,
  withCacheStatus,
  withSecurityHeaders,
} from "./routing";
import { type AlmacenTienda, type ResultadoRegeneracion, servirPaginaEstatica } from "./tienda/servir";

export interface EdgeDeps {
  /** Envía la petición al contenedor de Odoo. */
  forward: (request: Request) => Promise<Response>;
  /** Caché del borde (caches.default en producción). */
  cache?: Pick<Cache, "match" | "put">;
  /** Para tareas en segundo plano (ctx.waitUntil). */
  waitUntil?: (promise: Promise<unknown>) => void;
  canonicalHost?: string;
  /**
   * Estado del contenedor y de Odoo para `/__edge/health` (sin despertarlo). Sin esta
   * dependencia, el health check solo dice que el borde vive.
   */
  salud?: () => Promise<SaludContenedor>;
  /** Respaldo a mano: `POST /__edge/respaldo` con el token compartido. */
  respaldo?: { token?: string; respaldar: () => Promise<ResultadoRespaldo> };
  /**
   * Tienda estática (Fase 2). `activa` = TIENDA_ESTATICA=on: las páginas públicas salen del
   * almacén (KV) y, si no están, de Odoo como siempre. La regeneración (`POST
   * /__edge/tienda/regenerar` con `Bearer TIENDA_FEED_TOKEN`) funciona aunque no esté activa,
   * para dejar las páginas listas antes de encenderla.
   */
  tienda?: {
    activa: boolean;
    almacen?: AlmacenTienda;
    token?: string;
    regenerar?: () => Promise<ResultadoRegeneracion>;
  };
  /** DCASA_ENTORNO: en "staging" toda respuesta lleva `X-Robots-Tag: noindex`. */
  entorno?: string;
}

export async function handleRequest(request: Request, deps: EdgeDeps): Promise<Response> {
  const respuesta = await atender(request, deps);
  return deps.entorno === "staging" ? conNoindex(respuesta) : respuesta;
}

async function atender(request: Request, deps: EdgeDeps): Promise<Response> {
  const url = new URL(request.url);
  const decision = route(url, request.method, deps.canonicalHost);

  switch (decision.kind) {
    case "health":
      if (!deps.salud) return new Response("ok", { headers: { "Content-Type": "text/plain" } });
      return respuestaSalud(
        await deps.salud().catch((error: unknown) => ({
          contenedor: "stopped" as const,
          odoo: { error: `sin respuesta del Durable Object: ${String(error)}` },
        })),
      );
    case "respaldo":
      if (!deps.respaldo) return new Response("Not Found", { status: 404 });
      return manejarRespaldo(request, deps.respaldo);
    case "tienda_regenerar":
      return manejarRegenerarTienda(request, deps.tienda);
    case "blocked":
      return new Response("Not Found", { status: 404 });
    case "redirect":
      return Response.redirect(decision.location, decision.status);
  }

  const estatica = deps.tienda?.activa && deps.tienda.almacen ? rutaEstatica(url, request.method) : null;
  if (estatica && deps.tienda?.almacen) {
    try {
      const pagina = await servirPaginaEstatica(request, estatica, deps.tienda.almacen);
      if (pagina) return withSecurityHeaders(pagina);
    } catch (error) {
      // KV caído o lento: la página la sirve Odoo, como antes de la Fase 2.
      console.error(JSON.stringify({ evento: "tienda_lectura_fallida", ruta: estatica, error: String(error) }));
    }
  }

  const upstream = new Request(request, { headers: forwardedHeaders(request) });

  if (decision.cacheable && deps.cache) {
    if (!isCacheableRequest(request)) {
      return withSecurityHeaders(withCacheStatus(await reenviar(request, upstream, deps), "BYPASS"));
    }
    const cacheKey = new Request(url.toString(), { method: "GET" });
    const hit = await deps.cache.match(cacheKey);
    if (hit) {
      // Lo servido desde la caché también lleva HSTS, nosniff, etc. (Q-03).
      const servida = notModified(request, hit) ? notModifiedResponse(hit) : hit;
      return withSecurityHeaders(withCacheStatus(servida, "HIT"));
    }

    // Al llenar la caché se pide la versión completa: si el navegador mandó If-None-Match,
    // Odoo contestaría 304 y no habría nada que guardar (con poco tráfico, casi todo serían
    // fallos). El 304 para ese navegador lo arma el borde con la copia ya guardada.
    // Las imágenes sin `unique` Odoo las sirve "no-cache" (no se guardan): ahí el 304 de Odoo
    // sigue siendo lo mejor para el navegador (avatares y fotos del panel).
    const llenar = request.method === "GET";
    const sinVersion = url.pathname.startsWith("/web/image") && !url.searchParams.has("unique");
    let pedido = upstream;
    if (llenar && !sinVersion) {
      const headers = new Headers(upstream.headers);
      for (const name of CONDITIONAL_HEADERS) headers.delete(name);
      pedido = new Request(upstream, { headers });
    }
    const response = await reenviar(request, pedido, deps);
    if (llenar && isCacheableResponse(response)) {
      // Se guarda la copia tal como la dio Odoo; las cabeceras se agregan al servir.
      const put = deps.cache.put(cacheKey, response.clone());
      if (deps.waitUntil) {
        deps.waitUntil(put);
      } else {
        await put;
      }
      const servida = notModified(request, response) ? notModifiedResponse(response) : response;
      return withSecurityHeaders(withCacheStatus(servida, "MISS"));
    }
    return withSecurityHeaders(withCacheStatus(response, "BYPASS"));
  }

  return withSecurityHeaders(await reenviar(request, upstream, deps));
}

/**
 * Si el Durable Object del contenedor no responde (se reinicia con cada despliegue,
 * o falla al arrancar), el visitante ve el 503 amable con reintento, no un 500.
 */
async function reenviar(original: Request, upstream: Request, deps: EdgeDeps): Promise<Response> {
  try {
    return await deps.forward(upstream);
  } catch (error) {
    console.error(JSON.stringify({ evento: "reenvio_fallido", error: String(error) }));
    return respuestaArrancando(original);
  }
}

export interface ScheduledDeps {
  /** Estado del contenedor sin despertarlo (`Container.getState()`). */
  status: () => Promise<string>;
  /** Petición que despierta a Odoo (enciende el contenedor si está apagado). */
  wake: () => Promise<Response>;
  /**
   * Política de sueño del entorno (`politicaDeSueno`). `false` = puede dormir (staging):
   * el cron no lo despierta. Ausente = 24/7 (se despierta, como antes).
   */
  siempreEncendido?: boolean;
}

/**
 * Cron horario del Worker. No mantiene el contenedor despierto a la fuerza:
 *
 * - Si Odoo ya está encendido, no hace nada: su propio hilo de cron
 *   (`max_cron_threads`) corre las acciones planificadas.
 * - Si está apagado y el entorno es 24/7 (producción: reinicio de host sin visitas),
 *   lo despierta una vez para que Odoo corra lo pendiente (cola de correo, cron
 *   horario de socios…).
 * - Si está apagado y el entorno puede dormir (`ODOO_DORMIR_TRAS` con duración:
 *   staging), lo deja dormido: despertarlo cada hora lo tenía encendido ~50 % del
 *   tiempo y restaurando desde R2 cada ~2 h (ronda4/costos-y-limpieza §2.6). Lo
 *   enciende la próxima visita.
 */
export async function runScheduled(deps: ScheduledDeps): Promise<"encendido" | "despertado" | "dormido"> {
  const status = await deps.status();
  if (status === "running" || status === "healthy") return "encendido";
  if (deps.siempreEncendido === false) return "dormido";
  const response = await deps.wake();
  // El cuerpo no interesa; se descarta para liberar la conexión.
  await response.body?.cancel();
  return "despertado";
}

// ---------------------------------------------------------------------------
// Fase 1: Odoo + PostgreSQL en un solo contenedor que restaura desde R2.
// Lógica pura (sin Cloudflare) que usan src/index.ts y los tests.
// ---------------------------------------------------------------------------

/**
 * Crons del Worker (deben coincidir con `triggers.crons` de wrangler.jsonc, en UTC).
 * - Horario (minuto 7): despierta Odoo si está apagado (runScheduled).
 * - Diario 08:17 UTC = 03:17 en Panamá (UTC-5 todo el año, sin horario de verano):
 *   respaldo lógico diario (`dcasa-respaldo` dentro del contenedor).
 */
export const CRON_HORARIO = "7 * * * *";
export const CRON_RESPALDO = "17 8 * * *";

export type TareaCron = "despertar" | "respaldo";

/** Qué hace cada disparo del cron. Cualquier expresión desconocida solo despierta. */
export function tareaDelCron(cron: string): TareaCron {
  return cron.trim() === CRON_RESPALDO ? "respaldo" : "despertar";
}

/** Segundos que se le piden al navegador/cliente antes de reintentar. */
export const REINTENTO_SEGUNDOS = 15;

/**
 * Respuesta 503 amable mientras Odoo arranca o restaura la base desde R2 (I-07): en
 * vez de un error pelado, una página corta que se recarga sola. Nunca se guarda en
 * caché. A quien no pide HTML (Brian, Telegram, JSON-RPC, POST) se le da texto.
 */
export function respuestaArrancando(request: Request, reintento = REINTENTO_SEGUNDOS): Response {
  const headers = new Headers({
    "Retry-After": String(reintento),
    "Cache-Control": "no-store",
    "X-Dcasa-Estado": "arrancando",
  });
  const aceptaHtml = (request.headers.get("Accept") || "").includes("text/html");
  if (!aceptaHtml || request.method !== "GET") {
    headers.set("Content-Type", "text/plain; charset=utf-8");
    return withSecurityHeaders(
      new Response(`D'CASA está arrancando. Vuelve a intentar en ${reintento} segundos.\n`, { status: 503, headers }),
    );
  }
  headers.set("Content-Type", "text/html; charset=utf-8");
  return withSecurityHeaders(new Response(paginaArrancando(reintento), { status: 503, headers }));
}

function paginaArrancando(reintento: number): string {
  // Marca: fondo blanco, texto navy/azul, sin amarillo sobre blanco, sin degradados.
  return `<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="${reintento}">
<meta name="robots" content="noindex">
<title>D'CASA · Un momento</title>
<style>
  body{margin:0;background:#fff;color:#0B1F4D;font-family:Inter,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
    min-height:100vh;display:flex;align-items:center;justify-content:center;padding:16px;box-sizing:border-box}
  main{max-width:420px;text-align:center}
  h1{font-family:Anton,Impact,"Arial Narrow",sans-serif;text-transform:uppercase;color:#1340B1;font-weight:400;
    font-size:2rem;letter-spacing:.02em;margin:0 0 12px}
  p{line-height:1.5;margin:0 0 12px}
  a{color:#1340B1;font-weight:600}
</style>
</head>
<body>
<main>
  <h1>Estamos abriendo la tienda</h1>
  <p>Dame un momento: la página se recarga sola en ${reintento} segundos.</p>
  <p>¿Tienes prisa? <a href="https://wa.me/50760261919">Escríbenos por WhatsApp</a></p>
</main>
</body>
</html>
`;
}

export interface ArranqueDeps {
  /** ¿El contenedor corre y Odoo ya responde en su puerto? (no despierta nada) */
  listo: () => Promise<boolean>;
  /** Arranca el contenedor y espera a Odoo. Promesa compartida entre peticiones. */
  arrancar: () => Promise<void>;
  /** Envía la petición a Odoo (contenedor listo). */
  reenviar: (request: Request) => Promise<Response>;
  /** Secretos/variables que faltan para arrancar (si falta alguno, no se arranca). */
  faltantes?: () => string[];
  /** Cuánto se espera al arranque antes de responder 503 (por defecto ESPERA_ARRANQUE_MS). */
  esperaMs?: number;
  esperar?: (ms: number) => Promise<void>;
}

export const ESPERA_ARRANQUE_MS = 8_000;

const dormir = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/**
 * Atiende una petición dentro del Durable Object del contenedor:
 *
 * - Odoo listo → se reenvía.
 * - Faltan secretos (R2, cifrado, admin) → 503 sin arrancar: un contenedor sin
 *   credenciales de R2 no puede restaurar la base y no debe crear una vacía.
 * - Apagado o arrancando → se dispara (o se reutiliza) el arranque y se espera unos
 *   segundos; si Odoo no llega a tiempo (restauración desde R2: ~1-2 min), 503 amable
 *   con Retry-After. El arranque sigue en segundo plano.
 */
export async function servirConArranque(request: Request, deps: ArranqueDeps): Promise<Response> {
  if (await deps.listo()) return deps.reenviar(request);

  const faltan = deps.faltantes?.() ?? [];
  if (faltan.length) {
    console.error(JSON.stringify({ evento: "arranque_bloqueado", faltan }));
    return respuestaArrancando(request, 60);
  }

  const arranque = deps.arrancar().then(
    () => true,
    () => false,
  );
  const esperar = deps.esperar ?? dormir;
  const aTiempo = await Promise.race([arranque, esperar(deps.esperaMs ?? ESPERA_ARRANQUE_MS).then(() => false)]);
  if (aTiempo) return deps.reenviar(request);
  return respuestaArrancando(request);
}

/**
 * Secretos sin los cuales el contenedor no debe arrancar: sin R2 ni la clave de
 * cifrado no hay restauración posible (y arrancar con una base vacía sería peor).
 */
export const SECRETOS_PARA_ARRANCAR = [
  "ADMIN_PASSWORD",
  "R2_ENDPOINT",
  "R2_ACCESS_KEY_ID",
  "R2_SECRET_ACCESS_KEY",
  "PGBACKREST_CIPHER_PASS",
] as const;

/** Variables (`vars`) también obligatorias para arrancar. */
export const VARIABLES_PARA_ARRANCAR = ["R2_BUCKET"] as const;

export function secretosFaltantes(env: object): string[] {
  const valores = env as Record<string, unknown>;
  return [...SECRETOS_PARA_ARRANCAR, ...VARIABLES_PARA_ARRANCAR].filter((nombre) => {
    const valor = valores[nombre];
    return typeof valor !== "string" || valor.trim() === "";
  });
}

/** Variables que se pasan tal cual al contenedor, siempre que estén definidas. */
export const VARIABLES_DEL_CONTENEDOR = [
  // Odoo
  "ADMIN_PASSWORD",
  "ODOO_MASTER_PASSWORD",
  "DCASA_PIN_PEPPER",
  "APP_VERSION",
  "CANONICAL_HOST",
  "DCASA_ENTORNO",
  // Adjuntos: «r2» (por defecto, con las credenciales R2_*) o «db» (emergencia; addons/dcasa_adjuntos_r2)
  "DCASA_ADJUNTOS",
  // Respaldo continuo (pgBackRest) y diario (pg_dump) en R2
  "R2_ENDPOINT",
  "R2_BUCKET",
  "R2_ACCESS_KEY_ID",
  "R2_SECRET_ACCESS_KEY",
  "PGBACKREST_CIPHER_PASS",
  // Brian, el asistente
  "BRIAN_PROVEEDOR",
  "BRIAN_MODELO",
  "BRIAN_BASE_URL",
  "BRIAN_HERRAMIENTAS_MAX",
  "BRIAN_API_KEY",
  "TELEGRAM_BOT_TOKEN",
  "BRIAN_TELEGRAM_SECRETO",
  // Tienda estática del borde (addons/dcasa_tienda_borde): el mismo secreto protege el feed y
  // el aviso de regeneración; TIENDA_AVISO_URL es opcional (por defecto https://CANONICAL_HOST/…).
  "TIENDA_FEED_TOKEN",
  "TIENDA_AVISO_URL",
] as const;

/**
 * Entorno del contenedor. La base es local (PostgreSQL dentro del contenedor): ya no
 * se pasa DB_HOST ni nada de Neon. APP_VERSION y DCASA_ENTORNO llevan valor por defecto.
 * RESPALDO_TOKEN no entra: el respaldo se lanza con exec(), no por HTTP.
 */
export function variablesDelContenedor(env: object): Record<string, string> {
  const valores = env as Record<string, unknown>;
  const resultado: Record<string, string> = { APP_VERSION: "dev", DCASA_ENTORNO: "produccion" };
  for (const nombre of VARIABLES_DEL_CONTENEDOR) {
    const valor = valores[nombre];
    if (typeof valor === "string" && valor !== "") resultado[nombre] = valor;
  }
  return resultado;
}

/**
 * Política de sueño del contenedor según `ODOO_DORMIR_TRAS`:
 * - vacío, ausente o "nunca" → siempre encendido (24/7, producción en la Fase 1);
 * - una duración ("30m", "1h", "90s") → duerme tras ese tiempo sin visitas (staging).
 * Un valor inválido cae en 24/7: ante la duda, no apagar la tienda.
 */
export function politicaDeSueno(valor?: string): { siempreEncendido: boolean; sleepAfter: string } {
  const limpio = (valor ?? "").trim().toLowerCase();
  if (/^\d+[smh]$/.test(limpio) && parseInt(limpio, 10) > 0) {
    return { siempreEncendido: false, sleepAfter: limpio };
  }
  if (limpio !== "" && limpio !== "nunca") {
    console.warn(`ODOO_DORMIR_TRAS inválido («${valor}»): el contenedor queda encendido 24/7.`);
  }
  // En 24/7, sleepAfter solo marca cada cuánto se revisa la inactividad; la revisión no apaga.
  return { siempreEncendido: true, sleepAfter: "24h" };
}

/** Pausa mínima entre rearranques automáticos (evita restaurar desde R2 en bucle). */
export const PAUSA_REARRANQUE_MS = 10 * 60 * 1000;

/**
 * Tras una parada (reinicio de host, rollout, OOM), ¿se rearranca solo? Solo en 24/7
 * y como mucho una vez cada PAUSA_REARRANQUE_MS; si no, el cron horario o la próxima
 * visita lo encienden.
 */
export function debeRearrancar(siempreEncendido: boolean, ahora: number, ultimoRearranque?: number): boolean {
  if (!siempreEncendido) return false;
  return ultimoRearranque === undefined || ahora - ultimoRearranque >= PAUSA_REARRANQUE_MS;
}

// ------------------------------- Salud -------------------------------------

export type EstadoContenedor = "running" | "healthy" | "stopping" | "stopped" | "stopped_with_code";

export interface SaludContenedor {
  /** Estado del contenedor según Cloudflare (`getState()`), sin despertarlo. */
  contenedor: EstadoContenedor;
  /** Respuesta de `/dcasa/salud` (solo si el contenedor estaba listo). */
  odoo?: { status: number; cuerpo?: string } | { error: string };
  /** Secretos/variables que faltan para poder arrancar. */
  faltan?: string[];
}

/**
 * `/__edge/health`: 200 solo si Odoo responde 2xx en `/dcasa/salud` (que comprueba la
 * base). Si el contenedor está apagado o arrancando NO se despierta: se informa y se
 * responde 503 con Retry-After, para que un monitor externo vea la caída real.
 */
export function respuestaSalud(salud: SaludContenedor): Response {
  let odoo: "ok" | "arrancando" | "detenido" | "error" | "sin_configurar";
  if (salud.faltan?.length) odoo = "sin_configurar";
  else if (salud.odoo && "status" in salud.odoo)
    odoo = salud.odoo.status >= 200 && salud.odoo.status < 300 ? "ok" : "error";
  else if (salud.odoo && "error" in salud.odoo) odoo = "error";
  else if (salud.contenedor === "running" || salud.contenedor === "healthy") odoo = "arrancando";
  else odoo = "detenido";

  const cuerpo: Record<string, unknown> = { borde: "ok", odoo, contenedor: salud.contenedor };
  if (salud.faltan?.length) cuerpo.faltan = salud.faltan;
  if (salud.odoo && "status" in salud.odoo) {
    cuerpo.salud_http = salud.odoo.status;
    if (salud.odoo.cuerpo) cuerpo.detalle = salud.odoo.cuerpo.slice(0, 500);
  }
  if (salud.odoo && "error" in salud.odoo) cuerpo.detalle = salud.odoo.error.slice(0, 200);

  const headers = new Headers({ "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" });
  if (odoo !== "ok") headers.set("Retry-After", String(REINTENTO_SEGUNDOS));
  return new Response(JSON.stringify(cuerpo), { status: odoo === "ok" ? 200 : 503, headers });
}

// ------------------------------- Respaldo ----------------------------------

export interface ResultadoRespaldo {
  estado: "ok" | "fallo" | "omitido" | "en_curso";
  codigo?: number;
  duracionMs?: number;
  /** Final de la salida del script (el script no debe imprimir secretos). */
  salida?: string;
  motivo?: string;
}

/** Comparación en tiempo constante (no revela por tiempos cuántos caracteres coinciden). */
export function mismoSecreto(a: string, b: string): boolean {
  const ea = new TextEncoder().encode(a);
  const eb = new TextEncoder().encode(b);
  let diferencia = ea.length ^ eb.length;
  const largo = Math.max(ea.length, eb.length);
  for (let i = 0; i < largo; i++) diferencia |= (ea[i] ?? 0) ^ (eb[i] ?? 0);
  return diferencia === 0;
}

/** Largo mínimo de RESPALDO_TOKEN; uno más corto se trata como no configurado. */
export const LARGO_MINIMO_TOKEN = 32;

/** ¿`Authorization: Bearer …` trae el token? Sin token válido configurado: nunca. */
export function autorizado(authorization: string | null, token?: string): boolean {
  if (!token || token.length < LARGO_MINIMO_TOKEN) return false;
  const match = /^Bearer\s+(.+)$/i.exec(authorization ?? "");
  return match !== null && mismoSecreto(match[1].trim(), token);
}

/** Últimos `max` caracteres de la salida del script (lo útil está al final). */
export function colaDeSalida(texto: string, max = 2000): string {
  return texto.length <= max ? texto : "…" + texto.slice(-max);
}

const ESTADO_HTTP_RESPALDO: Record<ResultadoRespaldo["estado"], number> = {
  ok: 200,
  fallo: 500,
  en_curso: 409,
  omitido: 503,
};

/**
 * `POST /__edge/respaldo` con `Authorization: Bearer <RESPALDO_TOKEN>`: respaldo a mano
 * (simulacros, antes de un cambio grande). Mismo camino que el cron diario. Sin
 * RESPALDO_TOKEN configurado (o con menos de 32 caracteres) la ruta no existe (404).
 */
export async function manejarRespaldo(
  request: Request,
  deps: { token?: string; respaldar: () => Promise<ResultadoRespaldo> },
): Promise<Response> {
  if (!deps.token || deps.token.length < LARGO_MINIMO_TOKEN) return new Response("Not Found", { status: 404 });
  if (request.method !== "POST") {
    return new Response("Method Not Allowed", { status: 405, headers: { Allow: "POST" } });
  }
  if (!autorizado(request.headers.get("Authorization"), deps.token)) {
    return new Response("Unauthorized", { status: 401, headers: { "WWW-Authenticate": "Bearer" } });
  }
  const resultado = await deps.respaldar();
  return new Response(JSON.stringify(resultado), {
    status: ESTADO_HTTP_RESPALDO[resultado.estado],
    headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" },
  });
}

// ------------------------------- Tienda estática ---------------------------

/**
 * `POST /__edge/tienda/regenerar` con `Authorization: Bearer <TIENDA_FEED_TOKEN>`: Odoo avisa que
 * algo cambió (addons/dcasa_tienda_borde) y el Worker relee el feed y reescribe las páginas
 * que cambiaron. Sin token válido configurado (≥ 32 caracteres) o sin almacén, la ruta no existe.
 * Responde cuando terminó: Odoo reintenta si no fue 2xx.
 */
export async function manejarRegenerarTienda(
  request: Request,
  tienda?: { token?: string; almacen?: AlmacenTienda; regenerar?: () => Promise<ResultadoRegeneracion> },
): Promise<Response> {
  if (!tienda?.regenerar || !tienda.almacen || !tienda.token || tienda.token.length < LARGO_MINIMO_TOKEN) {
    return new Response("Not Found", { status: 404 });
  }
  if (request.method !== "POST") {
    return new Response("Method Not Allowed", { status: 405, headers: { Allow: "POST" } });
  }
  if (!autorizado(request.headers.get("Authorization"), tienda.token)) {
    return new Response("Unauthorized", { status: 401, headers: { "WWW-Authenticate": "Bearer" } });
  }
  // El cuerpo (productos y motivos) solo se registra: se regenera todo y se escribe lo que cambió.
  const aviso = await request.text().catch(() => "");
  const resultado = await tienda.regenerar();
  const linea = JSON.stringify({ evento: "tienda_regenerada", aviso: aviso.slice(0, 500), ...resultado });
  if (resultado.estado === "ok") console.log(linea);
  else console.error(linea);
  return new Response(JSON.stringify(resultado), {
    status: resultado.estado === "ok" ? 200 : 503,
    headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" },
  });
}

/** ¿El cron horario regenera la tienda? Solo con almacén y token, y con Odoo ya encendido. */
export function debeRegenerarEnCron(
  odoo: "encendido" | "despertado" | "dormido",
  hayAlmacen: boolean,
  token?: string,
): boolean {
  return odoo === "encendido" && hayAlmacen && !!token && token.length >= LARGO_MINIMO_TOKEN;
}
