/**
 * Reglas del borde (sin dependencias de Cloudflare: se testean en Node).
 */

export type Route =
  | { kind: "health" }
  | { kind: "respaldo" }
  | { kind: "tienda_regenerar" }
  | { kind: "blocked" }
  | { kind: "redirect"; location: string; status: 301 | 308 }
  | { kind: "origin"; cacheable: boolean };

/**
 * Rutas que nunca se exponen a internet (se comparan contra la ruta normalizada,
 * ver `normalizePath`):
 *
 * - `/web/database/*`: gestor de bases de datos (borrar, respaldar, restaurar).
 * - `/jsonrpc`: además de los modelos, despacha el servicio `db` (`drop`, `dump`,
 *   `restore`, `change_admin_password`…), protegido solo por la contraseña maestra.
 *   El cuerpo no se inspecciona en el borde, así que se bloquea completo.
 * - `/xmlrpc/*` (incluye `/xmlrpc/db` y `/xmlrpc/2/db`): la misma API en XML-RPC.
 * - `/json/2/*` y `/doc-bearer/*`: API externa de Odoo 19 con clave de API. Nada de
 *   D'CASA la usa hoy; cuando Brian en el borde la necesite (fase posterior) se
 *   abrirá con su propia protección, no desde internet abierto.
 *
 * - `/dcasa/tienda/feed`: catálogo para el generador de la tienda estática. Lleva su propio
 *   secreto, pero solo lo pide el Worker, directo al contenedor (sin pasar por estas reglas).
 *
 * Ningún módulo de `addons/` ni el Worker usan estas rutas (Brian habla por
 * `/brian/mcp` y el sitio por `/web/dataset/*` y rutas `http`).
 */
const BLOCKED_PREFIXES = ["/web/database", "/jsonrpc", "/xmlrpc", "/json/2", "/doc-bearer", "/dcasa/tienda/feed"];

/**
 * Odoo (http_routing) quita un prefijo de idioma (`/es/…`, `/es_419/…`) y vuelve a
 * enrutar, incluso en un POST: `/es/jsonrpc` llega a `/jsonrpc`. Por eso las
 * rutas bloqueadas se comprueban también sin un primer segmento con forma de idioma.
 */
const LANG_SEGMENT = /^\/[a-z]{2,3}(?:[_-][a-z0-9]{2,4})?(?:@[a-z]+)?(?=\/|$)/;

/** Decodifica %XX byte a byte (sin lanzar con secuencias inválidas). */
function percentDecode(path: string): string {
  return path.replace(/%([0-9a-f]{2})/gi, (_m, hex: string) => String.fromCharCode(parseInt(hex, 16)));
}

/**
 * Ruta canónica para decidir bloqueos: decodifica %XX hasta que no cambie (doble
 * codificación incluida), pasa `\` a `/`, colapsa barras repetidas, resuelve `.` y
 * `..` y pasa a minúsculas. Es más agresiva que Odoo a propósito (Odoo distingue
 * mayúsculas y decodifica una sola vez): ante la duda, se bloquea de más.
 */
export function normalizePath(pathname: string): string {
  let path = pathname;
  for (let i = 0; i < 5; i++) {
    const decoded = percentDecode(path);
    if (decoded === path) break;
    path = decoded;
  }
  path = path.toLowerCase().replace(/\\/g, "/");
  const segments: string[] = [];
  for (const segment of path.split("/")) {
    if (segment === "" || segment === ".") continue;
    if (segment === "..") {
      segments.pop();
      continue;
    }
    segments.push(segment);
  }
  return "/" + segments.join("/");
}

/** ¿La ruta (o la ruta sin prefijo de idioma) cae en una ruta bloqueada? */
export function isBlockedPath(pathname: string): boolean {
  const path = normalizePath(pathname);
  const candidates = [path, path.replace(LANG_SEGMENT, "") || "/"];
  return candidates.some((candidate) => BLOCKED_PREFIXES.some((prefix) => candidate.startsWith(prefix)));
}

/**
 * Endpoints de Brian (servidor MCP y webhook de Telegram): llevan credenciales
 * (Authorization / secreto) y respuestas por usuario. Nunca se guardan en caché.
 */
const NEVER_CACHE_PREFIXES = ["/brian/"];

/**
 * Recursos estáticos o versionados que se pueden guardar en la caché del borde. Que la
 * ruta esté aquí no basta: además Odoo tiene que responder "public" (isCacheableResponse),
 * y Odoo solo marca "public" lo servido a un visitante anónimo (`Stream.public`, http.py).
 *
 * No entran (a propósito):
 * - El HTML (`/`, `/shop`, fichas): Odoo manda `Set-Cookie` de sesión a todo anónimo y el
 *   CSRF va atado a esa sesión. Cachearlo exige quitar la cookie a anónimos, bypass por
 *   `session_id`, purga por etiqueta y pasar el «Agregar» a JSON-RPC (ronda3/sitio-edge.md §2.A).
 * - `/web/webclient/translations`: Odoo responde `public, max-age=1 año` pero el JS lo pide
 *   con `cache: "no-store"` y compara el hash para enterarse de traducciones nuevas.
 */
const CACHEABLE_PATTERNS = [
  /^\/web\/assets\//, // bundles JS/CSS con hash en la URL
  /^\/[a-z0-9_]+\/static\//, // archivos estáticos de los módulos (fuentes, fotos del tema)
  /^\/web\/image\//, // imágenes de productos (solo si Odoo responde "public")
  /^\/web\/content\/[^?]*\?(?:.*&)?unique=/, // adjuntos versionados (/web/content/12-abc/x.css?unique=…)
  /^\/dcasa\/img\/[^?]*\?(?:.*&)?v=/, // fotos WebP/JPEG al ancho justo, versionadas (website_dcasa/models/imagen.py)
];

export function route(url: URL, method: string, canonicalHost?: string): Route {
  if (url.pathname === "/__edge/health") {
    return { kind: "health" };
  }
  if (url.pathname === "/__edge/respaldo") {
    return { kind: "respaldo" };
  }
  if (url.pathname === "/__edge/tienda/regenerar") {
    return { kind: "tienda_regenerar" };
  }
  // `/__edge/*` es del borde: lo que no existe aquí no se reenvía a Odoo.
  if (isBlockedPath(url.pathname) || normalizePath(url.pathname).startsWith("/__edge/")) {
    return { kind: "blocked" };
  }
  if (canonicalHost && url.hostname !== canonicalHost && url.hostname === `www.${canonicalHost}`) {
    const target = new URL(url.toString());
    target.hostname = canonicalHost;
    target.protocol = "https:";
    // 308 conserva el método y el cuerpo (un POST a /brian/mcp sigue siendo POST).
    const status = method === "GET" || method === "HEAD" ? 301 : 308;
    return { kind: "redirect", location: target.toString(), status };
  }
  if (NEVER_CACHE_PREFIXES.some((prefix) => url.pathname.startsWith(prefix))) {
    return { kind: "origin", cacheable: false };
  }
  const isRead = method === "GET" || method === "HEAD";
  const pathAndQuery = url.pathname + url.search;
  return { kind: "origin", cacheable: isRead && CACHEABLE_PATTERNS.some((re) => re.test(pathAndQuery)) };
}

/**
 * Solo se guarda en caché lo que Odoo marca como público y no trae cookie:
 * así nunca se comparte entre visitantes una respuesta ligada a una sesión.
 */
export function isCacheableResponse(response: Response): boolean {
  if (response.status !== 200) return false;
  if (response.headers.has("Set-Cookie")) return false;
  // Una respuesta que varía según la cookie o según todo depende de quién la pide.
  const vary = (response.headers.get("Vary") || "").toLowerCase();
  if (/(^|,)\s*(\*|cookie|authorization)\s*(,|$)/.test(vary)) return false;
  const cacheControl = (response.headers.get("Cache-Control") || "").toLowerCase();
  if (!cacheControl.includes("public")) return false;
  return !/(private|no-store|no-cache)/.test(cacheControl);
}

/**
 * ¿Esta petición puede leer o llenar la caché del borde? Solo lecturas y nunca con
 * credenciales explícitas (`Authorization`): esas respuestas son de quien las pide.
 * La cookie de sesión no cuenta: Odoo se la pone a todo anónimo, y lo que sirve a un
 * usuario con sesión lo marca "private", que isCacheableResponse ya rechaza.
 */
export function isCacheableRequest(request: Request): boolean {
  if (request.method !== "GET" && request.method !== "HEAD") return false;
  return !request.headers.has("Authorization");
}

/** Cabeceras de validación condicional que el borde quita al llenar su caché. */
export const CONDITIONAL_HEADERS = ["If-None-Match", "If-Modified-Since", "If-Match", "If-Unmodified-Since", "If-Range"];

function etagsIguales(a: string, b: string): boolean {
  const limpia = (etag: string) => etag.trim().replace(/^W\//, "");
  return limpia(a) === limpia(b);
}

/**
 * ¿El navegador ya tiene esta versión? (If-None-Match manda sobre If-Modified-Since,
 * RFC 9110 §13.1.3). Permite responder 304 desde el borde aunque la copia en caché sea
 * un 200 completo.
 */
export function notModified(request: Request, response: Response): boolean {
  if (response.status !== 200) return false;
  const ifNoneMatch = request.headers.get("If-None-Match");
  const etag = response.headers.get("ETag");
  if (ifNoneMatch !== null) {
    if (!etag) return false;
    return ifNoneMatch.trim() === "*" || ifNoneMatch.split(",").some((candidato) => etagsIguales(candidato, etag));
  }
  const ifModifiedSince = Date.parse(request.headers.get("If-Modified-Since") ?? "");
  const lastModified = Date.parse(response.headers.get("Last-Modified") ?? "");
  return !Number.isNaN(ifModifiedSince) && !Number.isNaN(lastModified) && lastModified <= ifModifiedSince;
}

/** 304 con las cabeceras que el navegador necesita para refrescar su copia (RFC 9110 §15.4.5). */
export function notModifiedResponse(response: Response): Response {
  const headers = new Headers();
  for (const name of ["Cache-Control", "ETag", "Expires", "Last-Modified", "Vary", "Content-Location", "Date"]) {
    const value = response.headers.get(name);
    if (value !== null) headers.set(name, value);
  }
  return new Response(null, { status: 304, headers });
}

/** Cabecera de diagnóstico: permite medir si la caché del borde de verdad acierta. */
export const CACHE_STATUS_HEADER = "X-Dcasa-Cache";
export type CacheStatus = "HIT" | "MISS" | "BYPASS";

export function withCacheStatus(response: Response, status: CacheStatus): Response {
  if (response.status === 101 || (response as Response & { webSocket?: unknown }).webSocket) return response;
  const marked = new Response(response.body, response);
  marked.headers.set(CACHE_STATUS_HEADER, status);
  return marked;
}

/** Cabeceras para que Odoo (proxy_mode) conozca el host, el esquema y la IP reales. */
export function forwardedHeaders(request: Request): Headers {
  const url = new URL(request.url);
  const headers = new Headers(request.headers);
  const clientIp = request.headers.get("CF-Connecting-IP");
  headers.set("X-Forwarded-Host", url.host);
  headers.set("X-Forwarded-Proto", url.protocol.replace(":", ""));
  if (clientIp) {
    headers.set("X-Forwarded-For", clientIp);
    headers.set("X-Real-IP", clientIp);
  }
  return headers;
}

const SECURITY_HEADERS: Record<string, string> = {
  "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "strict-origin-when-cross-origin",
  // El constructor de sitios de Odoo carga la página en un iframe del mismo origen.
  "X-Frame-Options": "SAMEORIGIN",
  // Lo mismo en CSP (los navegadores nuevos priorizan frame-ancestors). Solo si Odoo no mandó
  // su propia CSP: /web/login ya la trae igual.
  "Content-Security-Policy": "frame-ancestors 'self'",
  "X-Permitted-Cross-Domain-Policies": "none",
};

export function withSecurityHeaders(response: Response): Response {
  // Las respuestas de WebSocket (101) no se pueden reconstruir.
  if (response.status === 101 || (response as Response & { webSocket?: unknown }).webSocket) {
    return response;
  }
  const secured = new Response(response.body, response);
  for (const [name, value] of Object.entries(SECURITY_HEADERS)) {
    if (!secured.headers.has(name)) secured.headers.set(name, value);
  }
  return secured;
}

// ------------------------------------------------------------------ tienda estática

/**
 * Rutas que la tienda estática puede servir (las mismas URL de Odoo). Todo lo demás (carrito,
 * checkout, pago, /my, /odoo, /web, /socios, /brian, /dcasa/*, buscador, filtros) va a Odoo.
 * Las fichas y categorías llevan el `-<id>` final del slug de Odoo: así `/shop/cart`,
 * `/shop/checkout`, `/shop/payment`… nunca se confunden con un producto.
 */
const RUTAS_ESTATICAS = [
  /^\/$/,
  /^\/shop(?:\/page\/[1-9]\d{0,4})?$/,
  /^\/shop\/category\/[a-z0-9-]+-\d{1,10}(?:\/page\/[1-9]\d{0,4})?$/,
  /^\/shop\/[a-z0-9-]+-\d{1,10}$/,
  /^\/(?:visitanos|privacidad|terminos|black-weekend)$/,
];

/** Parámetros que no cambian la página (campañas): con ellos se sigue sirviendo la estática. */
const PARAMETROS_IGNORABLES = /^(?:utm_[a-z_]+|gclid|fbclid|msclkid|gbraid|wbraid)$/;

/**
 * Ruta de la página estática que corresponde a esta petición, o `null` si va a Odoo: solo
 * GET/HEAD, sin parámetros de búsqueda/filtro/orden y con una ruta de la lista.
 */
export function rutaEstatica(url: URL, method: string): string | null {
  if (method !== "GET" && method !== "HEAD") return null;
  for (const nombre of url.searchParams.keys()) {
    if (!PARAMETROS_IGNORABLES.test(nombre)) return null;
  }
  return RUTAS_ESTATICAS.some((re) => re.test(url.pathname)) ? url.pathname : null;
}

/** Staging no se indexa: `X-Robots-Tag` en TODA respuesta (también redirecciones y 503). */
export function conNoindex(response: Response): Response {
  if (response.status === 101 || (response as Response & { webSocket?: unknown }).webSocket) return response;
  const marcada = new Response(response.body, response);
  marcada.headers.set("X-Robots-Tag", "noindex, nofollow");
  return marcada;
}
