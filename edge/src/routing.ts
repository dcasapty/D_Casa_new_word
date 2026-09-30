/**
 * Reglas del borde (sin dependencias de Cloudflare: se testean en Node).
 */

export type Route =
  | { kind: "health" }
  | { kind: "blocked" }
  | { kind: "redirect"; location: string; status: 301 | 308 }
  | { kind: "origin"; cacheable: boolean };

/** Rutas de administración de bases de datos: nunca se exponen a internet. */
const BLOCKED_PREFIXES = ["/web/database", "/xmlrpc/db", "/xmlrpc/2/db"];

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
  if (BLOCKED_PREFIXES.some((prefix) => url.pathname.startsWith(prefix))) {
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
