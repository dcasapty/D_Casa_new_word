/**
 * Reglas del borde (sin dependencias de Cloudflare: se testean en Node).
 */

export type Route =
  | { kind: "health" }
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
 * Ningún módulo de `addons/` ni el Worker usan estas rutas (Brian habla por
 * `/brian/mcp` y el sitio por `/web/dataset/*` y rutas `http`).
 */
const BLOCKED_PREFIXES = ["/web/database", "/jsonrpc", "/xmlrpc", "/json/2", "/doc-bearer"];

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

/** Recursos estáticos o versionados que se pueden guardar en la caché del borde. */
const CACHEABLE_PATTERNS = [
  /^\/web\/assets\//, // bundles JS/CSS con hash en la URL
  /^\/[a-z0-9_]+\/static\//, // archivos estáticos de los módulos
  /^\/web\/image\//, // imágenes de productos (solo si Odoo responde "public")
  /^\/web\/content\/[^/]*\?.*unique=/, // adjuntos versionados
];

export function route(url: URL, method: string, canonicalHost?: string): Route {
  if (url.pathname === "/__edge/health") {
    return { kind: "health" };
  }
  if (isBlockedPath(url.pathname)) {
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
  const cacheControl = (response.headers.get("Cache-Control") || "").toLowerCase();
  if (!cacheControl.includes("public")) return false;
  return !/(private|no-store|no-cache)/.test(cacheControl);
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
