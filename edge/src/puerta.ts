/**
 * La puerta del equipo (docs/SEGURIDAD_ACCESO.md §8). Sin dependencias de Cloudflare: se prueba en Node.
 *
 * El personal entra al panel por TRES pasos, en este orden:
 *   1. Cloudflare Access (Zero Trust): un PIN que llega al correo. Protege UNA ruta del sitio, la «entrada»
 *      (`DCASA_PUERTA_RUTA`, p. ej. `/master`), que es también la PÁGINA de login del equipo (la sirve Odoo:
 *      correo y clave, o llave de acceso). Access le entrega al Worker un token firmado (`Cf-Access-Jwt-Assertion`);
 *      aquí se VERIFICA (firma, emisor, audiencia, vencimiento): si Access estuviera mal configurado, la entrada
 *      simplemente no abre.
 *   2. La clave de Odoo (o la llave de acceso).   3. El código de la app (Google Authenticator).
 *
 * Con el token verificado, el Worker pone su PROPIA cookie firmada (`__Host-dcasa_puerta`, 12 h por defecto,
 * nunca más que la sesión de Access). En cada petición con esa cookie válida, el Worker le manda a Odoo la
 * cabecera `X-Dcasa-Puerta: <correo>|<vence>|<firma>` (firmada con `DCASA_PUERTA_SECRETO`, que Odoo también
 * tiene): Odoo solo deja entrar o seguir dentro al personal (usuarios internos) cuando la cabecera es válida
 * (addons/dcasa_seguridad). Los clientes y los socios no pasan por aquí.
 *
 * Todo está APAGADO mientras falte cualquiera de las cuatro variables: `configPuerta` devuelve `null` y el borde
 * se comporta exactamente como antes.
 */

/** Cookie de la puerta. `__Host-`: solo HTTPS, sin dominio, ruta `/`. */
export const NOMBRE_COOKIE = "__Host-dcasa_puerta";
/** Cabecera hacia Odoo. El borde SIEMPRE la borra de lo que manda el visitante. */
export const CABECERA_PUERTA = "X-Dcasa-Puerta";
/**
 * Qué exige Odoo en ESTA petición: `<modo>|<exigir correo 0/1>|<vence>|<firma>`. La decide el Worker en cada petición
 * (su variable cambia en cuanto se despliega, sin reiniciar el contenedor: así el rescate funciona al instante) y la
 * firma con el mismo secreto. Una petición sin esta cabecera (las que nacen dentro del contenedor, p. ej. la que arma
 * un PDF) no exige nada. También se borra siempre de lo que manda el visitante.
 */
export const CABECERA_MODO = "X-Dcasa-Puerta-Modo";
const VIDA_CABECERA_MODO_S = 300;
/** A dónde va la persona al pasar la puerta. */
export const DESTINO_PANEL = "/odoo";

const HORAS_POR_DEFECTO = 12;
const HORAS_MAXIMAS = 24;
const LARGO_MINIMO_SECRETO = 32;
const TTL_JWKS_MS = 60 * 60 * 1000;
/** Si llega un token con una llave desconocida, se vuelve a pedir el listado, pero no más de una vez por minuto. */
const PAUSA_REFRESCO_JWKS_MS = 60 * 1000;
const MARGEN_RELOJ_S = 60;

export interface ConfigPuerta {
  /** Ruta de la entrada, en minúsculas: «/entrada-…». */
  ruta: string;
  secreto: string;
  /** `https://<equipo>.cloudflareaccess.com` (sin barra final). */
  equipo: string;
  /** Audiencia («AUD tag») de la aplicación de Access. */
  aud: string;
  horas: number;
}

export interface EntornoPuerta {
  /** «0» (por defecto), «avisar» o «1»: ver `DepsPuerta.modo`. Con «1» el borde también cierra `/odoo…` sin la puerta. */
  DCASA_PUERTA_OBLIGATORIA?: string;
  /** «1» = Odoo exige que el correo con que se pasó la puerta sea el de la cuenta. */
  DCASA_PUERTA_EXIGIR_CORREO?: string;
  DCASA_PUERTA_RUTA?: string;
  DCASA_PUERTA_SECRETO?: string;
  DCASA_ACCESS_EQUIPO?: string;
  DCASA_ACCESS_AUD?: string;
  DCASA_PUERTA_HORAS?: string;
}

/** Mínimo 3 letras después de la barra (`/master` sirve). Una ruta larga y rara es más discreta, pero lo que protege es el PIN. */
const RUTA_VALIDA = /^\/[a-z0-9][a-z0-9-]{2,63}$/;
/** Rutas que ya son del sitio o de Odoo: la entrada no puede taparlas. */
const RESERVADAS = new Set([
  "odoo", "web", "shop", "my", "mi-cuenta", "socios", "brian", "dcasa", "website", "mail", "auth", "report", "contactus",
  "privacidad", "terminos", "visitanos", "whatsapp", "sitemap", "robots", "favicon", "longpolling", "websocket",
  "calendar", "survey", "blog", "forum", "event", "slides", "helpdesk", "api", "json", "jsonrpc", "xmlrpc",
]);
const EQUIPO_VALIDO = /^https:\/\/[a-z0-9][a-z0-9-]{0,62}\.cloudflareaccess\.com$/;
const AUD_VALIDA = /^[A-Za-z0-9]{16,128}$/;

/** Un aviso por problema y por isolate: configPuerta se llama en cada petición y no debe llenar los logs. */
const avisados = new Set<string>();

function limpio(valor: unknown): string {
  return typeof valor === "string" ? valor.trim() : "";
}

/**
 * La configuración de la puerta, o `null` si está apagada. Apagada = faltan variables (todas son necesarias).
 * Incompleta o inválida = también `null`, pero con un aviso en los logs: así un error de copiar y pegar no
 * deja a medias una puerta que parece encendida.
 */
export function configPuerta(env: EntornoPuerta): ConfigPuerta | null {
  const rutaCruda = limpio(env.DCASA_PUERTA_RUTA);
  const secreto = limpio(env.DCASA_PUERTA_SECRETO);
  const equipoCrudo = limpio(env.DCASA_ACCESS_EQUIPO);
  const aud = limpio(env.DCASA_ACCESS_AUD);
  if (!rutaCruda && !secreto && !equipoCrudo && !aud) return null;

  const ruta = ("/" + rutaCruda.replace(/^\/+/, "")).toLowerCase();
  const equipo = equipoCrudo.replace(/\/+$/, "").toLowerCase();
  const problemas: string[] = [];
  if (RESERVADAS.has(ruta.slice(1))) problemas.push(`DCASA_PUERTA_RUTA (${ruta} ya es una ruta del sitio: elige otra, p. ej. /master)`);
  else if (!RUTA_VALIDA.test(ruta)) problemas.push("DCASA_PUERTA_RUTA (3 a 64 letras minúsculas, números o guiones, p. ej. /master)");
  if (secreto.length < LARGO_MINIMO_SECRETO) problemas.push(`DCASA_PUERTA_SECRETO (mínimo ${LARGO_MINIMO_SECRETO} caracteres)`);
  if (!EQUIPO_VALIDO.test(equipo)) problemas.push("DCASA_ACCESS_EQUIPO (https://<equipo>.cloudflareaccess.com)");
  if (!AUD_VALIDA.test(aud)) problemas.push("DCASA_ACCESS_AUD (el «AUD tag» de la aplicación de Access)");
  if (problemas.length) {
    const aviso = JSON.stringify({ evento: "puerta_incompleta", detalle: "La puerta queda APAGADA", faltan: problemas });
    if (!avisados.has(aviso)) {
      avisados.add(aviso);
      console.warn(aviso);
    }
    return null;
  }
  const horasPedidas = Number.parseInt(limpio(env.DCASA_PUERTA_HORAS), 10);
  const horas = Number.isFinite(horasPedidas) && horasPedidas >= 1 ? Math.min(horasPedidas, HORAS_MAXIMAS) : HORAS_POR_DEFECTO;
  return { ruta, secreto, equipo, aud, horas };
}

export type ModoPuerta = "0" | "avisar" | "1";

/** Lo que el borde necesita para trabajar con la puerta (o `undefined` si está apagada: sigue como siempre). */
export interface DepsPuerta {
  config: ConfigPuerta;
  /** `0` solo verifica y firma; `avisar` además hace que Odoo anote lo que entra sin puerta; `1` exige la puerta. */
  modo: ModoPuerta;
  /** `DCASA_PUERTA_EXIGIR_CORREO=1`: Odoo exige que el correo de la puerta sea el de la cuenta. */
  exigirCorreo: boolean;
  jwt?: DepsJwt;
}

export function depsPuerta(env: EntornoPuerta): Pick<DepsPuerta, "config" | "modo" | "exigirCorreo"> | undefined {
  const config = configPuerta(env);
  if (!config) return undefined;
  const pedido = limpio(env.DCASA_PUERTA_OBLIGATORIA).toLowerCase();
  const modo: ModoPuerta = pedido === "1" || pedido === "avisar" ? pedido : "0";
  return { config, modo, exigirCorreo: limpio(env.DCASA_PUERTA_EXIGIR_CORREO) === "1" };
}

/** Valor de `X-Dcasa-Puerta-Modo`: el modo y el amarre del correo, firmados y con vencimiento corto. */
export async function cabeceraDeModo(
  cfg: Pick<ConfigPuerta, "secreto">,
  modo: ModoPuerta,
  exigirCorreo: boolean,
  ahoraMs: number,
): Promise<string> {
  const vence = Math.floor(ahoraMs / 1000) + VIDA_CABECERA_MODO_S;
  const exigir = exigirCorreo ? "1" : "0";
  const firma = await hmacHex(cfg.secreto, `modo|${modo}|${exigir}|${vence}`);
  return `${modo}|${exigir}|${vence}|${firma}`;
}

// ------------------------------------------------------------------ utilidades criptográficas

const codificador = new TextEncoder();

export function aBase64Url(bytes: Uint8Array): string {
  let binario = "";
  for (const byte of bytes) binario += String.fromCharCode(byte);
  return btoa(binario).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function deBase64Url(texto: string): Uint8Array | null {
  if (!/^[A-Za-z0-9_-]*$/.test(texto)) return null;
  const relleno = texto.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (texto.length % 4)) % 4);
  try {
    const binario = atob(relleno);
    return Uint8Array.from(binario, (letra) => letra.charCodeAt(0));
  } catch {
    return null;
  }
}

async function hmacHex(secreto: string, mensaje: string): Promise<string> {
  const clave = await crypto.subtle.importKey("raw", codificador.encode(secreto), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const firma = new Uint8Array(await crypto.subtle.sign("HMAC", clave, codificador.encode(mensaje)));
  return Array.from(firma, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

/** Comparación sin atajos: el tiempo no depende de en qué letra difieren. */
export function igualesSinAtajo(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diferencia = 0;
  for (let i = 0; i < a.length; i++) diferencia |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diferencia === 0;
}

// ------------------------------------------------------------------ token de Access (JWT RS256)

export interface DepsJwt {
  /** Descarga el listado de llaves públicas del equipo (`<equipo>/cdn-cgi/access/certs`). */
  fetchJwks?: (url: string) => Promise<unknown>;
  /** Reloj en milisegundos (para pruebas). */
  ahora?: () => number;
}

export interface IdentidadAccess {
  /** Correo con el que se identificó en Access, en minúsculas. */
  email: string;
  /** Vencimiento del token de Access (segundos Unix). */
  exp: number;
}

interface CacheJwks {
  claves: Map<string, CryptoKey>;
  cargadoEn: number;
  ultimoRefresco: number;
}

const cacheJwks = new Map<string, CacheJwks>();
/** Descargas en curso (una por equipo: veinte pedidos a la vez no hacen veinte descargas). */
const descargasEnCurso = new Map<string, Promise<CacheJwks>>();
/** Cuándo falló la última descarga de cada equipo: tras un fallo no se insiste durante unos segundos. */
const ultimoFalloJwks = new Map<string, number>();
const PAUSA_TRAS_FALLO_JWKS_MS = 10 * 1000;
const TOPE_DESCARGA_JWKS_MS = 5 * 1000;

/** Para pruebas: olvida las llaves guardadas y los avisos ya dados. */
export function reiniciarCacheJwks(): void {
  avisados.clear();
  cacheJwks.clear();
  descargasEnCurso.clear();
  ultimoFalloJwks.clear();
}

async function descargarJwks(url: string): Promise<unknown> {
  const respuesta = await fetch(url, { headers: { Accept: "application/json" }, signal: AbortSignal.timeout(TOPE_DESCARGA_JWKS_MS) });
  if (!respuesta.ok) throw new Error(`HTTP ${respuesta.status}`);
  return respuesta.json();
}

async function cargarLlaves(equipo: string, deps: DepsJwt, ahora: number): Promise<CacheJwks> {
  const crudo = (await (deps.fetchJwks ?? descargarJwks)(`${equipo}/cdn-cgi/access/certs`)) as { keys?: unknown };
  const claves = new Map<string, CryptoKey>();
  const lista = Array.isArray(crudo?.keys) ? (crudo.keys as Array<Record<string, unknown>>) : [];
  for (const jwk of lista) {
    if (jwk?.kty !== "RSA" || typeof jwk.kid !== "string" || typeof jwk.n !== "string" || typeof jwk.e !== "string") continue;
    try {
      const clave = await crypto.subtle.importKey(
        "jwk",
        { kty: "RSA", n: jwk.n, e: jwk.e, alg: "RS256", ext: true },
        { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
        false,
        ["verify"],
      );
      claves.set(jwk.kid, clave);
    } catch {
      // una llave rara no invalida las demás
    }
  }
  return { claves, cargadoEn: ahora, ultimoRefresco: ahora };
}

async function claveParaKid(equipo: string, kid: string, deps: DepsJwt, ahora: number): Promise<CryptoKey | null> {
  const guardado = cacheJwks.get(equipo);
  const vigente = guardado && ahora - guardado.cargadoEn < TTL_JWKS_MS;
  if (guardado && vigente && guardado.claves.has(kid)) return guardado.claves.get(kid) ?? null;
  // Llave desconocida (Access rota sus llaves) o listado viejo: se vuelve a pedir, con pausa entre intentos.
  if (guardado && ahora - guardado.ultimoRefresco < PAUSA_REFRESCO_JWKS_MS) return guardado.claves.get(kid) ?? null;
  // Sin nada guardado y con un fallo reciente: no se insiste (una ráfaga de pedidos no se convierte en una ráfaga
  // de descargas contra Cloudflare).
  const fallo = ultimoFalloJwks.get(equipo);
  if (fallo !== undefined && ahora - fallo < PAUSA_TRAS_FALLO_JWKS_MS) return guardado?.claves.get(kid) ?? null;
  try {
    let descarga = descargasEnCurso.get(equipo);
    if (!descarga) {
      descarga = cargarLlaves(equipo, deps, ahora).finally(() => descargasEnCurso.delete(equipo));
      descargasEnCurso.set(equipo, descarga);
    }
    const nuevo = await descarga;
    cacheJwks.set(equipo, nuevo);
    ultimoFalloJwks.delete(equipo);
    return nuevo.claves.get(kid) ?? null;
  } catch (error) {
    console.error(JSON.stringify({ evento: "puerta_jwks_fallido", error: String(error).slice(0, 200) }));
    ultimoFalloJwks.set(equipo, ahora);
    if (guardado) guardado.ultimoRefresco = ahora;
    return guardado?.claves.get(kid) ?? null;
  }
}

function rechazo(motivo: string): null {
  console.warn(JSON.stringify({ evento: "puerta_token_rechazado", motivo }));
  return null;
}

function objetoJson(parte: string): Record<string, unknown> | null {
  const bytes = deBase64Url(parte);
  if (!bytes) return null;
  try {
    const valor: unknown = JSON.parse(new TextDecoder().decode(bytes));
    return valor && typeof valor === "object" && !Array.isArray(valor) ? (valor as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

/** ASCII imprimible, sin espacios ni «|» ni un segundo «@»: un carácter raro haría fallar las cabeceras HTTP. */
const CORREO_VALIDO = /^[\x21-\x3f\x41-\x7b\x7d-\x7e]{1,64}@[\x21-\x3f\x41-\x7b\x7d-\x7e]{1,190}$/;

/**
 * Verifica el token que Access pone en `Cf-Access-Jwt-Assertion`. Falla CERRADO: cualquier duda = `null`.
 * Solo RS256 (nunca `none` ni HS256), emisor y audiencia exactos, vigente, con un correo bien formado.
 */
export async function verificarJwtAccess(
  token: string | null,
  cfg: Pick<ConfigPuerta, "equipo" | "aud">,
  deps: DepsJwt = {},
): Promise<IdentidadAccess | null> {
  if (!token) return rechazo("sin token");
  const ahoraMs = (deps.ahora ?? Date.now)();
  const partes = token.split(".");
  if (partes.length !== 3 || partes.some((parte) => parte === "")) return rechazo("forma");
  const cabecera = objetoJson(partes[0]);
  const carga = objetoJson(partes[1]);
  const firma = deBase64Url(partes[2]);
  if (!cabecera || !carga || !firma) return rechazo("ilegible");
  if (cabecera.alg !== "RS256") return rechazo("algoritmo");
  if (typeof cabecera.kid !== "string" || cabecera.kid === "") return rechazo("sin kid");

  const clave = await claveParaKid(cfg.equipo, cabecera.kid, deps, ahoraMs);
  if (!clave) return rechazo("llave desconocida");
  const valida = await crypto.subtle.verify(
    "RSASSA-PKCS1-v1_5",
    clave,
    firma as unknown as BufferSource,
    codificador.encode(`${partes[0]}.${partes[1]}`),
  );
  if (!valida) return rechazo("firma");

  const ahoraS = Math.floor(ahoraMs / 1000);
  if (typeof carga.iss !== "string" || carga.iss.replace(/\/+$/, "").toLowerCase() !== cfg.equipo) return rechazo("emisor");
  const audiencia = carga.aud;
  const coincide = Array.isArray(audiencia) ? audiencia.includes(cfg.aud) : audiencia === cfg.aud;
  if (!coincide) return rechazo("audiencia");
  if (typeof carga.exp !== "number" || !Number.isFinite(carga.exp) || carga.exp <= ahoraS - MARGEN_RELOJ_S) return rechazo("vencido");
  if (typeof carga.nbf === "number" && carga.nbf > ahoraS + MARGEN_RELOJ_S) return rechazo("todavía no vale");
  if (typeof carga.iat === "number" && carga.iat > ahoraS + MARGEN_RELOJ_S) return rechazo("emitido en el futuro");
  const email = typeof carga.email === "string" ? carga.email.trim().toLowerCase() : "";
  if (!CORREO_VALIDO.test(email)) return rechazo("sin correo");
  return { email, exp: carga.exp };
}

// ------------------------------------------------------------------ cookie propia y cabecera hacia Odoo

export interface PuertaAbierta {
  email: string;
  /** Vencimiento (segundos Unix). */
  exp: number;
}

/** Cookie de la puerta para quien acaba de pasar Access: dura lo configurado, nunca más que su sesión de Access. */
export async function crearCookie(
  cfg: ConfigPuerta,
  identidad: IdentidadAccess,
  ahoraMs: number,
): Promise<{ valor: string; exp: number; maxAge: number }> {
  const ahoraS = Math.floor(ahoraMs / 1000);
  const exp = Math.min(ahoraS + cfg.horas * 3600, identidad.exp);
  const correo = aBase64Url(codificador.encode(identidad.email));
  const firma = await hmacHex(cfg.secreto, `cookie|${correo}|${exp}`);
  return { valor: `${correo}.${exp}.${firma}`, exp, maxAge: Math.max(exp - ahoraS, 0) };
}

function leerCookieCruda(cabecera: string | null, nombre: string): string | null {
  if (!cabecera) return null;
  for (const trozo of cabecera.split(";")) {
    const igual = trozo.indexOf("=");
    if (igual < 0) continue;
    if (trozo.slice(0, igual).trim() === nombre) return trozo.slice(igual + 1).trim();
  }
  return null;
}

/** ¿La petición trae la cookie de la puerta, firmada por nosotros y vigente? */
export async function leerCookie(request: Request, cfg: ConfigPuerta, ahoraMs: number): Promise<PuertaAbierta | null> {
  const crudo = leerCookieCruda(request.headers.get("Cookie"), NOMBRE_COOKIE);
  if (!crudo) return null;
  const partes = crudo.split(".");
  if (partes.length !== 3 || !/^\d{1,12}$/.test(partes[1]) || !/^[0-9a-f]{64}$/.test(partes[2])) return null;
  const exp = Number(partes[1]);
  if (exp <= Math.floor(ahoraMs / 1000)) return null;
  const esperada = await hmacHex(cfg.secreto, `cookie|${partes[0]}|${exp}`);
  if (!igualesSinAtajo(esperada, partes[2])) return null;
  const bytes = deBase64Url(partes[0]);
  if (!bytes) return null;
  const email = new TextDecoder().decode(bytes);
  return CORREO_VALIDO.test(email) ? { email, exp } : null;
}

/** Valor de `X-Dcasa-Puerta` para Odoo: `<correo>|<vence>|<firma>`. Odoo lo verifica con el mismo secreto. */
export async function cabeceraParaOdoo(cfg: ConfigPuerta, puerta: PuertaAbierta): Promise<string> {
  const firma = await hmacHex(cfg.secreto, `cabecera|${puerta.email}|${puerta.exp}`);
  return `${puerta.email}|${puerta.exp}|${firma}`;
}

/** Quita la cookie de la puerta del `Cookie` que viaja a Odoo (Odoo no la necesita). */
export function sinCookieDePuerta(cookie: string | null): string | null {
  if (!cookie) return cookie;
  const resto = cookie
    .split(";")
    .filter((trozo) => trozo.slice(0, Math.max(trozo.indexOf("="), 0)).trim() !== NOMBRE_COOKIE)
    .map((trozo) => trozo.trim())
    .filter((trozo) => trozo !== "");
  return resto.length ? resto.join("; ") : null;
}

function cookieDePuerta(valor: string, maxAge: number): string {
  return `${NOMBRE_COOKIE}=${valor}; Max-Age=${maxAge}; Path=/; Secure; HttpOnly; SameSite=Lax`;
}

/** `Set-Cookie` que borra la cookie (al cerrar sesión). */
export const COOKIE_BORRADA = cookieDePuerta("", 0);

// ------------------------------------------------------------------ rutas

/** ¿Esta petición es la entrada de la puerta (la ruta secreta)? */
export function esEntrada(pathname: string, cfg: ConfigPuerta): boolean {
  const ruta = pathname.toLowerCase().replace(/\/+$/, "");
  return ruta === cfg.ruta;
}

const SEGMENTO_IDIOMA = /^\/[a-z]{2,3}(?:[_-][a-z0-9]{2,4})?(?:@[a-z]+)?(?=\/|$)/;

/** La ruta normalizada y, aparte, sin un primer segmento con forma de idioma (Odoo lo quita y vuelve a enrutar). */
export function rutasConYSinIdioma(rutaNormalizada: string): string[] {
  return [rutaNormalizada, rutaNormalizada.replace(SEGMENTO_IDIOMA, "") || "/"];
}

/**
 * ¿Es el panel de Odoo (`/odoo…`, con o sin prefijo de idioma)? Sin la puerta abierta, el borde responde 404
 * a estas rutas: el panel ni siquiera aparece para quien no es del equipo.
 */
export function esPanel(rutaNormalizada: string): boolean {
  return rutasConYSinIdioma(rutaNormalizada).some((ruta) => ruta === "/odoo" || ruta.startsWith("/odoo/"));
}

/** 404 igual al de una página que no existe: la ruta de la entrada no se delata. */
export function respuestaNoExiste(): Response {
  return new Response("Not Found", { status: 404, headers: { "Cache-Control": "no-store" } });
}

export interface PasoPorLaPuerta {
  /** Quién pasó, para firmar la cabecera de ESTA petición (la cookie recién creada aún no viaja en ella). */
  abierta: PuertaAbierta;
  /** Valor del `Set-Cookie` que abre la puerta en el navegador. */
  setCookie: string;
}

/**
 * La entrada (`DCASA_PUERTA_RUTA`): Access ya pidió el PIN; aquí se VERIFICA el token que dejó. Si es bueno, la
 * persona pasó: se devuelve su identidad y la cookie, y el borde le entrega la página de login de Odoo. Cualquier
 * otra cosa (sin token, token malo, método raro) es `null` y el que llama responde 404.
 */
export async function abrirPuerta(request: Request, cfg: ConfigPuerta, deps: DepsJwt = {}): Promise<PasoPorLaPuerta | null> {
  if (request.method !== "GET" && request.method !== "POST" && request.method !== "HEAD") return null;
  const identidad = await verificarJwtAccess(request.headers.get("Cf-Access-Jwt-Assertion"), cfg, deps);
  if (!identidad) return null;
  const ahoraMs = (deps.ahora ?? Date.now)();
  const cookie = await crearCookie(cfg, identidad, ahoraMs);
  if (cookie.maxAge <= 0) return null;
  console.log(JSON.stringify({ evento: "puerta_abierta", correo: identidad.email, vence: cookie.exp }));
  return { abierta: { email: identidad.email, exp: cookie.exp }, setCookie: cookieDePuerta(cookie.valor, cookie.maxAge) };
}

/** La respuesta de Odoo para la entrada, con la cookie de la puerta y sin guardarse en ninguna caché. */
export function conCookieDePuerta(respuesta: Response, setCookie: string): Response {
  if (respuesta.status >= 500) return respuesta; // Odoo arrancando: todavía no se abre nada
  const abierta = new Response(respuesta.body, respuesta);
  abierta.headers.append("Set-Cookie", setCookie);
  abierta.headers.set("Cache-Control", "no-store");
  return abierta;
}

/**
 * ¿Es el login PÚBLICO al que Odoo manda a quien perdió la sesión del panel (`/web/login?redirect=/odoo…` o
 * `redirect=/dcasa/doc/…`, el QR de un documento)? El
 * personal ya no inicia sesión ahí: se le lleva a la página del equipo. El segundo paso del código (`/web/login/totp`)
 * y el login de clientes (sin `redirect` hacia el panel) no se tocan.
 */
export function esLoginPublicoDelPanel(request: Request, rutaNormalizada: string): boolean {
  if (request.method !== "GET" || rutaNormalizada !== "/web/login") return false;
  const destino = new URL(request.url).searchParams.get("redirect") ?? "";
  // `/dcasa/doc/…` es el QR de un documento (uso interno): quien lo escanea sin sesión llega a este login y, si es del
  // equipo, debe ir a la página del equipo igual que con `/odoo…`.
  return /^\/(?:odoo|dcasa\/doc)(?:[/?#]|$)/i.test(destino);
}
