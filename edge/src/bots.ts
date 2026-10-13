/**
 * Freno barato a bots y agentes automatizados en el borde (sin dependencias de Cloudflare:
 * se testea en Node). Ver docs/SEGURIDAD_ACCESO.md → «Bots y agentes automatizados».
 *
 * 1. Rutas de sondeo (/wp-admin, /.env, /phpmyadmin, *.php…): 404 sin despertar a Odoo.
 * 2. Escáneres que se anuncian como tales (sqlmap, nikto, nuclei…): 403. NUNCA se tocan
 *    Googlebot, Bingbot ni los previsualizadores de WhatsApp/Facebook/Telegram: el sitio vive
 *    de SEO y de compartir enlaces. Tampoco las librerías HTTP genéricas (python, curl, node):
 *    las usan Brian por MCP, Telegram y las integraciones.
 * 3. Límite de intentos por IP en los POST sensibles (login, clave, registro, formularios,
 *    carrito): 429 con Retry-After. Usa el binding de Rate Limiting de Workers si existe
 *    (wrangler.jsonc, hoy comentado) y si no, un contador en memoria del isolate (aproximado:
 *    cada ubicación de Cloudflare y cada isolate cuentan por su lado; frena ráfagas, no es exacto).
 */
import { normalizePath } from "./routing";

/** Igual que en routing.ts: Odoo quita un primer segmento de idioma (`/es/…`). */
const SEGMENTO_IDIOMA = /^\/[a-z]{2,3}(?:[_-][a-z0-9]{2,4})?(?:@[a-z]+)?(?=\/|$)/;

/** La ruta normalizada y, aparte, sin el primer segmento si tiene forma de idioma (`/web` también la tiene). */
function candidatas(pathname: string): string[] {
  const ruta = normalizePath(pathname);
  return [ruta, ruta.replace(SEGMENTO_IDIOMA, "") || "/"];
}

// ------------------------------------------------------------------ sondeos

/** Prefijos que solo piden los escáneres (Odoo no tiene nada así). */
const PREFIJOS_SONDEO = [
  "/wp-admin",
  "/wp-login",
  "/wp-content",
  "/wp-includes",
  "/wp-json",
  "/wordpress",
  "/xmlrpc.php",
  "/phpmyadmin",
  "/pma",
  "/myadmin",
  "/adminer",
  "/vendor/phpunit",
  "/cgi-bin",
  "/server-status",
  "/server-info",
  "/actuator",
  "/boaform",
  "/hnap1",
  "/owa",
  "/autodiscover",
  "/ecp",
  "/_ignition",
  "/telescope",
  "/solr",
  "/manager/html",
];

/** Carpetas ocultas de servidor o de código (`/.env`, `/x/.git/config`…). `/.well-known` sí pasa. */
const SEGMENTO_OCULTO = /(?:^|\/)\.(?:env|git|svn|hg|aws|ssh|docker|vscode|idea|htaccess|htpasswd|ds_store|npmrc|bash_history)(?:[./]|$)/;

/** Extensiones de otros servidores: Odoo no sirve ninguna. */
const EXTENSION_AJENA = /\.(?:php\d?|phtml|asp|aspx|ashx|jsp|jspx|cgi|pl|env|ini|sql|bak|old|swp|config)$/;

export function esSondeo(pathname: string): boolean {
  return candidatas(pathname).some(
    (ruta) =>
      PREFIJOS_SONDEO.some((prefijo) => ruta === prefijo || ruta.startsWith(`${prefijo}/`)) ||
      SEGMENTO_OCULTO.test(ruta) ||
      EXTENSION_AJENA.test(ruta),
  );
}

// ------------------------------------------------------------------ escáneres

/**
 * Herramientas de ataque o escaneo masivo que se identifican en el User-Agent. Lista corta y
 * conservadora a propósito: un falso positivo aquí deja fuera a un cliente o a un buscador.
 */
const AGENTES_ESCANER =
  /\b(?:sqlmap|nikto|nmap|masscan|zgrab|nuclei|wpscan|acunetix|netsparker|dirbuster|gobuster|ffuf|feroxbuster|wfuzz|hydra|openvas|w3af|joomscan|commix|xsstrike|arachni|jaeles|zmeu|morfeus|fimap|havij|l9explore|l9tcpid)\b/i;

export function esEscaner(userAgent: string | null): boolean {
  return !!userAgent && AGENTES_ESCANER.test(userAgent);
}

// ------------------------------------------------------------------ límite de intentos

export type Cubeta = "acceso" | "formulario" | "carrito";

/**
 * Intentos por minuto y por IP. Generosos: en Panamá mucha gente sale a internet por la
 * misma IP del operador móvil (CGNAT), y una tienda llena no debe ver un 429.
 */
export const LIMITES: Record<Cubeta, number> = {
  acceso: 10, // login, 2FA, cambio de clave, registro, entrar a /socios
  formulario: 10, // contacto y formularios del sitio
  carrito: 120, // agregar, cambiar cantidades, dirección y pago
};

const RUTAS_ACCESO = [
  "/web/login", // incluye /web/login/totp y /web/login/dcasa-2fa
  "/web/session/authenticate",
  "/web/reset_password",
  "/web/signup",
  "/auth-timeout/check-identity",
  "/socios/entrar",
  "/socios/registro",
  "/socios/pin",
];
const RUTAS_FORMULARIO = ["/website/form/", "/website/mass_mailing/"];
const RUTAS_CARRITO = ["/shop/cart/", "/shop/address", "/shop/checkout", "/shop/payment", "/shop/confirm_order"];

/** ¿Qué límite aplica? Solo a métodos que escriben (POST, PUT…); las lecturas nunca. */
export function cubetaDe(method: string, pathname: string): Cubeta | null {
  if (method === "GET" || method === "HEAD" || method === "OPTIONS") return null;
  const rutas = candidatas(pathname);
  const empieza = (prefijos: string[]) =>
    rutas.some((ruta) => prefijos.some((p) => ruta === p.replace(/\/$/, "") || ruta.startsWith(p.endsWith("/") ? p : `${p}/`)));
  if (empieza(RUTAS_ACCESO)) return "acceso";
  if (empieza(RUTAS_FORMULARIO)) return "formulario";
  if (empieza(RUTAS_CARRITO)) return "carrito";
  return null;
}

/** Lo mismo que el binding de Rate Limiting de Workers (`env.X.limit({ key })`). */
export interface Limitador {
  limit(opciones: { key: string }): Promise<{ success: boolean }>;
}

/**
 * Contador en memoria (ventana fija de 60 s) para cuando no hay binding. Vive lo que vive el
 * isolate; con más de `maxClaves` IP distintas se vacía (no crece sin límite).
 */
export class LimitadorMemoria implements Limitador {
  private readonly ventanas = new Map<string, { inicio: number; cuenta: number }>();

  constructor(
    private readonly limite: number,
    private readonly periodoMs = 60_000,
    private readonly ahora: () => number = Date.now,
    private readonly maxClaves = 10_000,
  ) {}

  async limit({ key }: { key: string }): Promise<{ success: boolean }> {
    const t = this.ahora();
    let ventana = this.ventanas.get(key);
    if (!ventana || t - ventana.inicio >= this.periodoMs) {
      if (this.ventanas.size >= this.maxClaves) this.ventanas.clear();
      ventana = { inicio: t, cuenta: 0 };
      this.ventanas.set(key, ventana);
    }
    ventana.cuenta += 1;
    return { success: ventana.cuenta <= this.limite };
  }
}

const enMemoria: Record<Cubeta, LimitadorMemoria> = {
  acceso: new LimitadorMemoria(LIMITES.acceso),
  formulario: new LimitadorMemoria(LIMITES.formulario),
  carrito: new LimitadorMemoria(LIMITES.carrito),
};

export const REINTENTO_429_S = 60;

function demasiados(): Response {
  return new Response("Demasiados intentos seguidos. Espera un minuto y vuelve a intentar.\n", {
    status: 429,
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "no-store",
      "Retry-After": String(REINTENTO_429_S),
    },
  });
}

/**
 * Filtro previo a Odoo. Devuelve la respuesta de rechazo o `null` si la petición sigue.
 * `limitadores`: bindings de Rate Limiting por cubeta (los que falten usan la memoria).
 */
export async function filtrarAutomatizados(
  request: Request,
  url: URL,
  limitadores: Partial<Record<Cubeta, Limitador>> = {},
): Promise<Response | null> {
  if (esSondeo(url.pathname)) {
    return new Response("Not Found", { status: 404, headers: { "Cache-Control": "no-store" } });
  }
  if (esEscaner(request.headers.get("User-Agent"))) {
    return new Response("Forbidden", { status: 403, headers: { "Cache-Control": "no-store" } });
  }
  const cubeta = cubetaDe(request.method, url.pathname);
  const ip = request.headers.get("CF-Connecting-IP");
  if (!cubeta || !ip) return null;
  const limitador = limitadores[cubeta] ?? enMemoria[cubeta];
  try {
    const { success } = await limitador.limit({ key: `${cubeta}:${ip}` });
    if (success) return null;
  } catch (error) {
    // Si el limitador falla, se deja pasar: Odoo tiene su propio bloqueo por intentos.
    console.error(JSON.stringify({ evento: "limitador_fallido", cubeta, error: String(error) }));
    return null;
  }
  console.warn(JSON.stringify({ evento: "limite_intentos", cubeta, ruta: url.pathname }));
  return demasiados();
}
