/**
 * Caché en el borde del HTML que dibuja Odoo (sin Cloudflare: el almacén es una interfaz; en
 * producción es un namespace de Workers KV, ver src/index.ts).
 *
 * Una sola fuente de diseño: el borde NO dibuja nada. Guarda, byte a byte, la página que Odoo
 * renderiza para un visitante anónimo y se la sirve a los visitantes anónimos. Quien tiene sesión
 * de usuario, carrito, lista de deseos o sesión de socio (cookie `dcasa_personal`, que pone Odoo:
 * addons/dcasa_tienda_borde/models/ir_http.py) pasa directo a Odoo.
 *
 * Claves del almacén:
 * - `html:<host><ruta>` → HTML tal como lo dio Odoo, con metadatos `{ t, etag, ct }` (`t` = cuándo
 *   se empezó a pedir a Odoo, ms).
 * - `invalidado` → ms de la última invalidación (aviso de Odoo). Una página vale si `t ≥ invalidado`
 *   (el cambio en Odoo se confirmó ≥ 20 s antes del aviso: PAUSA_AVISO de pendiente.py).
 *   Así una invalidación es UNA escritura, sin listar ni borrar claves.
 */
import { withCacheStatus, type CacheStatus } from "../routing";

export interface EntradaAlmacen {
  texto: string;
  meta?: Record<string, string> | null;
}

export interface AlmacenTienda {
  leer(clave: string): Promise<EntradaAlmacen | null>;
  /** `ttlSegundos`: KV borra la clave solo pasado ese tiempo (páginas que nadie vuelve a pedir). */
  escribir(clave: string, texto: string, meta?: Record<string, string>, ttlSegundos?: number): Promise<void>;
}

export const CLAVE_INVALIDADO = "invalidado";
export const clavePagina = (host: string, ruta: string) => `html:${host}${ruta}`;

/**
 * Petición: el secreto `TIENDA_FEED_TOKEN` (solo lo manda el Worker al pedir la página para
 * guardarla). Respuesta: `anonimo` si Odoo certifica que la dibujó para un visitante anónimo, sin
 * guardar sesión ni poner cookies. Sin esa marca, no se guarda.
 */
export const CABECERA_BORDE = "X-Dcasa-Borde";
/** Cookie que Odoo pone a quien tiene algo propio en la sesión (usuario, carrito, deseos, socio). */
export const COOKIE_PERSONAL = "dcasa_personal";
/** El JS de addons/dcasa_tienda_borde lo lee (Navigation Timing) para refrescar el CSRF. */
export const SERVER_TIMING = "dcasa-borde";

/** Una página guardada se sirve sin preguntar a Odoo durante este tiempo; luego, vieja + refresco. */
export const FRESCA_MS = 60 * 60 * 1000;
/** KV borra la página si nadie la pidió en este tiempo (no hace falta borrar nada a mano). */
export const TTL_PAGINA_S = 7 * 24 * 60 * 60;
/** Páginas que se piden a Odoo apenas llega una invalidación (las más visitadas). */
export const RUTAS_PRINCIPALES = ["/", "/shop", "/black-weekend"];
/** Tope de páginas precalentadas por aviso (el resto se llena con la primera visita). */
export const MAX_PRECALENTAR = 40;

const USER_AGENT_RELLENO = "dcasa-borde/1 (+cache de paginas)";

export interface DepsPaginas {
  almacen: AlmacenTienda;
  /** TIENDA_FEED_TOKEN (≥ 32). */
  token: string;
  /** Envía una petición al contenedor de Odoo. */
  forward: (request: Request) => Promise<Response>;
  waitUntil?: (promise: Promise<unknown>) => void;
  ahora?: () => number;
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
 */
export async function rellenar(
  url: URL,
  ruta: string,
  deps: DepsPaginas,
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
  const escritura = deps.almacen.escribir(
    clavePagina(url.host, ruta),
    html,
    { t: String(inicio), etag: pagina.etag, ct: pagina.ct },
    TTL_PAGINA_S,
  );
  return { pagina, escritura };
}

function enSegundoPlano(deps: DepsPaginas, tarea: Promise<unknown>, evento: string, ruta: string): Promise<unknown> {
  const segura = tarea.catch((error: unknown) =>
    console.error(JSON.stringify({ evento, ruta, error: String(error) })),
  );
  if (deps.waitUntil) deps.waitUntil(segura);
  return segura;
}

async function leerInvalidado(almacen: AlmacenTienda): Promise<number> {
  const entrada = await almacen.leer(CLAVE_INVALIDADO);
  const valor = Number(entrada?.texto ?? 0);
  return Number.isFinite(valor) ? valor : 0;
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
    const pagina: Pagina = {
      html: entrada.texto,
      etag: entrada.meta?.etag ?? (await etagDe(entrada.texto)),
      ct: entrada.meta?.ct ?? "text/html; charset=utf-8",
    };
    if ((deps.ahora ?? Date.now)() - t < FRESCA_MS) return responder(request, pagina, "HIT");
    enSegundoPlano(
      deps,
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
    enSegundoPlano(deps, resultado.escritura, "pagina_escritura_fallida", ruta);
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

/** Pide a Odoo y guarda las rutas dadas (de a pocas: el contenedor es chico). */
export async function precalentar(origen: URL, rutas: string[], deps: DepsPaginas, paralelo = 3): Promise<number> {
  let guardadas = 0;
  for (let i = 0; i < rutas.length; i += paralelo) {
    await Promise.all(
      rutas.slice(i, i + paralelo).map(async (ruta) => {
        try {
          const r = await rellenar(origen, ruta, deps);
          if ("pagina" in r) {
            await r.escritura;
            guardadas++;
          } else {
            await r.respuesta.body?.cancel();
          }
        } catch (error) {
          console.error(JSON.stringify({ evento: "pagina_precalentar_fallido", ruta, error: String(error) }));
        }
      }),
    );
  }
  return guardadas;
}

/** `TIENDA_ESTATICA`: "on" (también "1", "true", "si") enciende la caché de páginas. */
export function tiendaActiva(valor?: string): boolean {
  return ["on", "1", "true", "si", "sí"].includes((valor ?? "").trim().toLowerCase());
}
