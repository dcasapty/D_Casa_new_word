/**
 * Caché en el borde del HTML que dibuja Odoo (sin Cloudflare: el almacén es una interfaz; en
 * producción es un namespace de Workers KV, ver src/index.ts y ./almacen.ts).
 *
 * Una sola fuente de diseño: el borde NO dibuja nada. Guarda, byte a byte, la página que Odoo
 * renderiza para un visitante anónimo y se la sirve a los visitantes anónimos. Quien tiene sesión
 * de usuario, carrito, lista de deseos o sesión de socio (cookie `dcasa_personal`, que pone Odoo:
 * addons/dcasa_tienda_borde/models/ir_http.py) pasa directo a Odoo.
 *
 * Una página guardada nunca debe verse rota: al guardarla se precalientan también sus assets
 * (./assets.ts: estilos y JS primero; luego fuentes, logo y foto LCP) y se anota en sus metadatos si
 * los críticos quedaron en el borde (`assets: ok`). Si no quedaron y Odoo no está listo para darlos,
 * se responde la página de «estamos abriendo» (503) en vez de un HTML sin estilos.
 *
 * Claves del almacén:
 * - `html:<host><ruta>` → HTML tal como lo dio Odoo, con metadatos `{ t, etag, ct, assets }` (`t` =
 *   cuándo se empezó a pedir a Odoo, ms).
 * - `invalidado` → ms de la última invalidación (aviso de Odoo). Una página vale si `t ≥ invalidado`
 *   (el cambio en Odoo se confirmó ≥ 20 s antes del aviso: PAUSA_AVISO de pendiente.py).
 *   Así una invalidación es UNA escritura, sin listar ni borrar claves.
 */
import { respuestaArrancando } from "../arranque";
import { type CacheStatus, withCacheStatus } from "../routing";
import {
  type AlmacenTienda,
  CABECERA_BORDE,
  CLAVE_INVALIDADO,
  type EntradaAlmacen,
  enSegundoPlano,
  leerInvalidado,
  TTL_PAGINA_S,
  USER_AGENT_RELLENO,
} from "./almacen";
import { assetsDe, assetsPresentes, type ContextoAssets, precalentarAssets } from "./assets";

export type { AlmacenTienda, EntradaAlmacen, EntradaBinaria } from "./almacen";
export { CABECERA_BORDE, CLAVE_INVALIDADO, TTL_PAGINA_S } from "./almacen";

export const clavePagina = (host: string, ruta: string) => `html:${host}${ruta}`;

/** Cookie que Odoo pone a quien tiene algo propio en la sesión (usuario, carrito, deseos, socio). */
export const COOKIE_PERSONAL = "dcasa_personal";
/** El JS de addons/dcasa_tienda_borde lo lee (Navigation Timing) para refrescar el CSRF. */
export const SERVER_TIMING = "dcasa-borde";

/** Una página guardada se sirve sin preguntar a Odoo durante este tiempo; luego, vieja + refresco. */
export const FRESCA_MS = 60 * 60 * 1000;
/** Páginas que se piden a Odoo apenas llega una invalidación (las más visitadas). */
export const RUTAS_PRINCIPALES = ["/", "/shop", "/black-weekend"];
/** Las que /__edge/health mira para decir si el sitio sobrevive un reinicio (/black-weekend puede no existir). */
export const RUTAS_VITALES = ["/", "/shop"];
/** Tope de páginas precalentadas por aviso (el resto se llena con la primera visita). */
export const MAX_PRECALENTAR = 40;

export interface DepsPaginas {
  almacen: AlmacenTienda;
  /** TIENDA_FEED_TOKEN (≥ 32). */
  token: string;
  /** Envía una petición al contenedor de Odoo. */
  forward: (request: Request) => Promise<Response>;
  waitUntil?: (promise: Promise<unknown>) => void;
  ahora?: () => number;
  /**
   * ¿Odoo está listo para responder? (estado del contenedor, sin despertarlo ni hablarle). Solo se
   * consulta cuando una página guardada tiene assets críticos que no están en el borde: si Odoo no
   * está, mejor el 503 amable que una página sin estilos. Sin esta dependencia se sirve siempre.
   */
  odooListo?: () => Promise<boolean>;
}

/** ¿La petición es de alguien con algo propio (o con credenciales)? Entonces va directo a Odoo. */
export function esPersonal(request: Request): boolean {
  if (request.headers.has("Authorization")) return true;
  const cookies = request.headers.get("Cookie") ?? "";
  return cookies.split(";").some((par) => {
    const [nombre, valor] = par.split("=");
    return nombre?.trim() === COOKIE_PERSONAL && (valor ?? "").trim() !== "";
  });
}

export async function etagDe(html: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(html));
  const hex = [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
  return `"p-${hex.slice(0, 24)}"`;
}

/**
 * La petición con la que el borde le pide a Odoo la página para guardarla: SIN cookies (Odoo la
 * dibuja para el usuario público, sin carrito ni nada de nadie), sin IP del visitante (sin geoIP),
 * con un User-Agent fijo, sin rastreo de visitas y con el secreto: Odoo no guarda sesión ni pone
 * cookies y certifica la respuesta como anónima. Los parámetros de campaña (`utm_*`…) se quitan:
 * `ruta` ya viene sin ellos.
 */
export function peticionDeRelleno(url: URL, ruta: string, token: string): Request {
  const destino = new URL(ruta, url.origin);
  return new Request(destino.toString(), {
    method: "GET",
    headers: {
      Accept: "text/html,application/xhtml+xml",
      "User-Agent": USER_AGENT_RELLENO,
      "X-Forwarded-Host": url.host,
      "X-Forwarded-Proto": url.protocol.replace(":", ""),
      // Odoo no cuenta esta petición como visita (website.visitor): no es de nadie.
      "X-Disable-Tracking": "1",
      [CABECERA_BORDE]: token,
    },
  });
}

/** ¿Odoo certificó esta respuesta como página anónima guardable? */
export function esGuardable(respuesta: Response): boolean {
  if (respuesta.status !== 200) return false;
  if (respuesta.headers.has("Set-Cookie")) return false;
  if (respuesta.headers.get(CABECERA_BORDE) !== "anonimo") return false;
  return (respuesta.headers.get("Content-Type") ?? "").toLowerCase().startsWith("text/html");
}

interface Pagina {
  html: string;
  etag: string;
  ct: string;
}

/** Metadato `assets` de una página guardada: ¿sus estilos y JS quedaron en el borde al guardarla? */
export type EstadoAssets = "ok" | "falta";

/** Respuesta al visitante: el HTML de Odoo intacto + validación (ETag) + diagnóstico. */
function responder(request: Request, pagina: Pagina, estado: CacheStatus): Response {
  const headers = new Headers({
    "Content-Type": pagina.ct,
    // El navegador revalida siempre: el 304 lo da el borde y, con sesión, la petición va a Odoo.
    "Cache-Control": "no-cache",
    ETag: pagina.etag,
    "Server-Timing": `${SERVER_TIMING};desc="${estado}"`,
  });
  const ifNoneMatch = request.headers.get("If-None-Match");
  const limpia = (e: string) => e.trim().replace(/^W\//, "");
  const respuesta =
    ifNoneMatch && ifNoneMatch.split(",").some((e) => limpia(e) === pagina.etag)
      ? new Response(null, { status: 304, headers })
      : new Response(request.method === "HEAD" ? null : pagina.html, { status: 200, headers });
  return withCacheStatus(respuesta, estado);
}

/**
 * Pide la página a Odoo como anónimo y, si Odoo la certifica, la guarda. Devuelve la página o la
 * respuesta de Odoo tal cual (404, redirección, 503 mientras arranca…), que no se guarda.
 *
 * `escritura` termina cuando la página Y sus assets están en el almacén: primero los críticos
 * (estilos y JS, que deciden `assets: ok|falta`), luego la página, luego fuentes, logo y foto LCP.
 * Al visitante no se le hace esperar nada de eso (el llamador la deja en segundo plano).
 */
export async function rellenar(
  url: URL,
  ruta: string,
  deps: DepsPaginas,
  contexto?: ContextoAssets,
): Promise<{ pagina: Pagina; escritura: Promise<void> } | { respuesta: Response }> {
  const inicio = (deps.ahora ?? Date.now)();
  const respuesta = await deps.forward(peticionDeRelleno(url, ruta, deps.token));
  if (!esGuardable(respuesta)) return { respuesta };
  const html = await respuesta.text();
  const pagina: Pagina = {
    html,
    etag: await etagDe(html),
    ct: respuesta.headers.get("Content-Type") ?? "text/html; charset=utf-8",
  };
  return { pagina, escritura: guardarPagina(url, ruta, pagina, inicio, deps, contexto ?? new Map()) };
}

async function guardarPagina(
  url: URL,
  ruta: string,
  pagina: Pagina,
  t: number,
  deps: DepsPaginas,
  contexto: ContextoAssets,
): Promise<void> {
  const assets = assetsDe(pagina.html, url);
  const criticos = await precalentarAssets(url, assets.criticos, deps, contexto);
  const estado: EstadoAssets = criticos === assets.criticos.length ? "ok" : "falta";
  await deps.almacen.escribir(
    clavePagina(url.host, ruta),
    pagina.html,
    { t: String(t), etag: pagina.etag, ct: pagina.ct, assets: estado },
    TTL_PAGINA_S,
  );
  await precalentarAssets(url, assets.otros, deps, contexto);
}

/**
 * Una página guardada se sirve solo si el navegador va a poder pintarla: sus estilos y JS deben
 * estar en el borde o, si no, Odoo debe estar listo para darlos. Con Odoo arrancando (reinicio,
 * despliegue, caída) y assets que faltan, mejor la página de «estamos abriendo» que una sin estilos.
 * Barato: si la página se guardó con `assets: ok` no se lee nada más.
 */
async function retenerSinAssets(
  request: Request,
  url: URL,
  ruta: string,
  entrada: EntradaAlmacen,
  deps: DepsPaginas,
): Promise<Response | null> {
  if (entrada.meta?.assets === "ok" || !deps.odooListo) return null;
  const criticos = assetsDe(entrada.texto, url).criticos;
  if (criticos.length === 0) return null;
  try {
    if (await assetsPresentes(criticos, deps.almacen)) return null;
  } catch (error) {
    console.error(JSON.stringify({ evento: "pagina_lectura_fallida", ruta, error: String(error) }));
    return null;
  }
  if (await deps.odooListo().catch(() => false)) return null;
  console.warn(JSON.stringify({ evento: "pagina_retenida", ruta, motivo: "assets críticos sin guardar y Odoo no listo" }));
  return withCacheStatus(respuestaArrancando(request), "BYPASS");
}

/**
 * Página pública para un visitante anónimo:
 * - guardada y válida (posterior a la última invalidación) y fresca → HIT, sin tocar Odoo;
 * - válida pero de hace más de FRESCA_MS → STALE: se sirve y se pide otra a Odoo en segundo plano;
 * - no está, o es anterior a la última invalidación → MISS: se pide a Odoo ahora y se guarda.
 * Si Odoo no la certifica como anónima (404, redirección, error), se responde lo que diga Odoo
 * a la petición ORIGINAL del visitante (`reenviarOriginal`), sin guardar nada.
 * `null` si el almacén falla: el llamador la manda a Odoo como siempre.
 */
export async function servirPagina(
  request: Request,
  ruta: string,
  deps: DepsPaginas,
  reenviarOriginal: () => Promise<Response>,
): Promise<Response | null> {
  const url = new URL(request.url);
  let entrada: EntradaAlmacen | null;
  let invalidado: number;
  try {
    [entrada, invalidado] = await Promise.all([
      deps.almacen.leer(clavePagina(url.host, ruta)),
      leerInvalidado(deps.almacen),
    ]);
  } catch (error) {
    console.error(JSON.stringify({ evento: "pagina_lectura_fallida", ruta, error: String(error) }));
    return null;
  }

  const t = Number(entrada?.meta?.t ?? NaN);
  if (entrada && Number.isFinite(t) && t >= invalidado) {
    const retenida = await retenerSinAssets(request, url, ruta, entrada, deps);
    if (retenida) return retenida;
    const pagina: Pagina = {
      html: entrada.texto,
      etag: entrada.meta?.etag ?? (await etagDe(entrada.texto)),
      ct: entrada.meta?.ct ?? "text/html; charset=utf-8",
    };
    if ((deps.ahora ?? Date.now)() - t < FRESCA_MS) return responder(request, pagina, "HIT");
    enSegundoPlano(
      deps.waitUntil,
      rellenar(url, ruta, deps).then(async (r) => {
        if ("pagina" in r) await r.escritura;
        else await r.respuesta.body?.cancel();
      }),
      "pagina_refresco_fallido",
      ruta,
    );
    return responder(request, pagina, "STALE");
  }

  const resultado = await rellenar(url, ruta, deps);
  if ("pagina" in resultado) {
    enSegundoPlano(deps.waitUntil, resultado.escritura, "pagina_escritura_fallida", ruta);
    return responder(request, resultado.pagina, "MISS");
  }
  // Odoo arrancando o con error: esa respuesta (503 amable) vale para el visitante tal cual.
  if (resultado.respuesta.status >= 500) return withCacheStatus(resultado.respuesta, "BYPASS");
  await resultado.respuesta.body?.cancel();
  return withCacheStatus(await reenviarOriginal(), "BYPASS");
}

/** Marca todas las páginas guardadas como viejas (una escritura). Devuelve la marca. */
export async function invalidar(almacen: AlmacenTienda, ahora = Date.now()): Promise<number> {
  await almacen.escribir(CLAVE_INVALIDADO, String(ahora));
  return ahora;
}

/** Rutas a precalentar tras un aviso: las principales + las que mande Odoo, sin repetir ni basura. */
export function rutasAPrecalentar(rutasDeOdoo: unknown, esRutaGuardable: (ruta: string) => boolean): string[] {
  const extra = Array.isArray(rutasDeOdoo) ? rutasDeOdoo.filter((r): r is string => typeof r === "string") : [];
  return [...new Set([...RUTAS_PRINCIPALES, ...extra])].filter(esRutaGuardable).slice(0, MAX_PRECALENTAR);
}

/**
 * Pide a Odoo y guarda las rutas dadas con sus assets (de a pocas: el contenedor es chico). La
 * primera va sola: sus bundles (los mismos en todo el sitio) quedan en el borde una vez y las demás
 * los encuentran. Devuelve cuántas páginas se guardaron y cuántos assets distintos se revisaron.
 */
export async function precalentar(
  origen: URL,
  rutas: string[],
  deps: DepsPaginas,
  paralelo = 3,
): Promise<{ paginas: number; assets: number }> {
  const contexto: ContextoAssets = new Map();
  let paginas = 0;
  const una = async (ruta: string) => {
    try {
      const r = await rellenar(origen, ruta, deps, contexto);
      if ("pagina" in r) {
        await r.escritura;
        paginas++;
      } else {
        await r.respuesta.body?.cancel();
      }
    } catch (error) {
      console.error(JSON.stringify({ evento: "pagina_precalentar_fallido", ruta, error: String(error) }));
    }
  };
  if (rutas.length) await una(rutas[0]);
  for (let i = 1; i < rutas.length; i += paralelo) {
    await Promise.all(rutas.slice(i, i + paralelo).map(una));
  }
  return { paginas, assets: contexto.size };
}

/** `TIENDA_ESTATICA`: "on" (también "1", "true", "si") enciende la caché de páginas. */
export function tiendaActiva(valor?: string): boolean {
  return ["on", "1", "true", "si", "sí"].includes((valor ?? "").trim().toLowerCase());
}

// ------------------------------------------------------------------ estado (para /__edge/health)

/**
 * - `completa`: la página está, vale y sus estilos y JS también están → saldría entera del borde
 *   aunque Odoo estuviera reiniciando;
 * - `sin_assets`: la página está pero le faltan assets críticos (con Odoo caído daría el 503 amable);
 * - `vieja`: anterior a la última invalidación (la próxima visita la pide a Odoo);
 * - `falta`: nadie la ha pedido ni precalentado (o no existe, p. ej. /black-weekend fuera de campaña).
 */
export type EstadoPagina = "completa" | "sin_assets" | "vieja" | "falta";

export interface EstadoTienda {
  rutas: Record<string, EstadoPagina>;
  /** Las páginas vitales (portada y catálogo) saldrían enteras del borde si Odoo se reiniciara ahora. */
  sobrevive_reinicio: boolean;
}

export async function estadoTienda(
  origen: URL,
  almacen: AlmacenTienda,
  rutas = RUTAS_PRINCIPALES,
  vitales = RUTAS_VITALES,
): Promise<EstadoTienda> {
  const invalidado = await leerInvalidado(almacen);
  const estados = await Promise.all(
    rutas.map(async (ruta): Promise<[string, EstadoPagina]> => {
      const entrada = await almacen.leer(clavePagina(origen.host, ruta));
      if (!entrada) return [ruta, "falta"];
      const t = Number(entrada.meta?.t ?? NaN);
      if (!Number.isFinite(t) || t < invalidado) return [ruta, "vieja"];
      if (entrada.meta?.assets === "ok") return [ruta, "completa"];
      const criticos = assetsDe(entrada.texto, origen).criticos;
      const completa = criticos.length === 0 || (await assetsPresentes(criticos, almacen));
      return [ruta, completa ? "completa" : "sin_assets"];
    }),
  );
  const porRuta = Object.fromEntries(estados);
  return { rutas: porRuta, sobrevive_reinicio: vitales.every((ruta) => porRuta[ruta] === "completa") };
}
