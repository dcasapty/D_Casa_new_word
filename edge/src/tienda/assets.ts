/**
 * Caché en el borde de los assets que una página de Odoo necesita: bundles de estilos y JS
 * (`/web/assets/<versión>/…`), fuentes, logo y foto del hero (`/<módulo>/static/…`), fotos de
 * producto (`/dcasa/img/…?v=`, `/web/image/…?unique=`) y adjuntos versionados (`/web/content/…?unique=`).
 *
 * Por qué: la caché de páginas (paginas.ts) servía el HTML al instante desde KV, pero los estilos y
 * el JS los daba Odoo; con el contenedor reiniciando (~1 min restaurando desde R2) esas peticiones
 * recibían el 503 «arrancando» y la página salía SIN ESTILOS. Peor que sin caché. Con los assets
 * también en el borde, una página guardada se ve entera aunque Odoo esté caído.
 *
 * Reglas:
 * - Solo se guarda lo que Odoo manda con 200, `Cache-Control: public` (sin private/no-store/no-cache),
 *   sin `Set-Cookie` ni `Vary: Cookie`. Las cabeceras de Odoo se devuelven tal cual (el navegador
 *   cachea lo que Odoo dijo).
 * - Con versión en la URL (`esAssetVersionado`): inmutable, se guarda TTL_ASSET_S sin mirar la marca
 *   de invalidación. Sin versión (estáticos de los módulos): válido si `t ≥ invalidado`; si caducó y
 *   Odoo no responde, se sirve la copia vieja (mejor vieja que rota).
 * - Un asset que una página guardada referencia debe vivir más que la página (TTL 30 d frente a 7 d;
 *   al precalentar se vuelve a pedir si ya tiene más de RETOCAR_TRAS_MS).
 */
import {
  type CacheStatus,
  CONDITIONAL_HEADERS,
  esAssetCacheable,
  esAssetVersionado,
  isCacheableRequest,
  isCacheableResponse,
  notModified,
  notModifiedResponse,
  withCacheStatus,
} from "../routing";
import {
  type AlmacenTienda,
  CABECERA_BORDE,
  type EntradaBinaria,
  enSegundoPlano,
  leerInvalidado,
  TTL_PAGINA_S,
  USER_AGENT_RELLENO,
} from "./almacen";

/** KV borra el asset si nadie lo pidió ni precalentó en este tiempo (los bundles viejos de cada despliegue se van solos). */
export const TTL_ASSET_S = 30 * 24 * 60 * 60;
/**
 * Al precalentar, un asset que ya está pero es más viejo que esto se vuelve a pedir (TTL nuevo): así
 * siempre caduca DESPUÉS que cualquier página guardada que lo referencie (TTL_PAGINA_S + 1 día de margen).
 */
export const RETOCAR_TRAS_MS = (TTL_ASSET_S - TTL_PAGINA_S) * 1000 - 24 * 60 * 60 * 1000;
/** KV admite valores de hasta 25 MiB; los bundles de Odoo pesan 1-3 MB. */
export const MAX_BYTES_ASSET = 24 * 1024 * 1024;
/** Assets no críticos (fuentes, imagen LCP, logo) que se precalientan por página, como mucho. */
export const MAX_ASSETS_POR_PAGINA = 12;

export const claveAsset = (rutaYQuery: string) => `asset:${rutaYQuery}`;

export interface DepsAssets {
  almacen: AlmacenTienda;
  /** TIENDA_FEED_TOKEN si está: con él Odoo no pone cookies a la petición de relleno. */
  token?: string;
  /** Envía una petición al contenedor de Odoo. */
  forward: (request: Request) => Promise<Response>;
  waitUntil?: (promise: Promise<unknown>) => void;
  ahora?: () => number;
}

// ------------------------------------------------------------------ qué assets usa una página

export interface AssetsDePagina {
  /** Sin estos la página se ve rota: hojas de estilo y JS (`src`, o `data-src` del cargador perezoso de Odoo). */
  criticos: string[];
  /** Precargas (fuentes, imagen LCP), logo e imágenes «eager»: mejoran la carga, no deciden si se sirve. */
  otros: string[];
}

const ETIQUETA = /<(link|script|img|source)\b([^>]*)>/gi;
const ATRIBUTO = /([^\s=/>"']+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+))/g;
const PICTURE = /<picture\b[^>]*>([\s\S]*?)<\/picture>/gi;
const IMG_PRIORITARIA = /<img\b[^>]*\b(?:loading\s*=\s*["']?eager|fetchpriority\s*=\s*["']?high)/i;

const decodificar = (valor: string) =>
  valor.replace(/&amp;/g, "&").replace(/&#39;/g, "'").replace(/&quot;/g, '"').replace(/&lt;/g, "<").replace(/&gt;/g, ">");

function atributos(texto: string): Record<string, string> {
  const atts: Record<string, string> = {};
  for (const m of texto.matchAll(ATRIBUTO)) atts[m[1].toLowerCase()] = decodificar(m[2] ?? m[3] ?? m[4] ?? "");
  return atts;
}

/** URLs de un `srcset`/`imagesrcset` («/a.webp 800w, /b.webp 1400w»). */
function candidatosSrcset(srcset: string | undefined): string[] {
  return (srcset ?? "")
    .split(",")
    .map((candidato) => candidato.trim().split(/\s+/)[0])
    .filter(Boolean);
}

/** Ruta (con query) del asset si es del mismo origen y de los que el borde guarda; si no, `null`. */
function rutaDeAsset(href: string | undefined, origen: URL): string | null {
  if (!href) return null;
  let url: URL;
  try {
    url = new URL(href, origen);
  } catch {
    return null;
  }
  if (url.origin !== origen.origin) return null;
  const ruta = url.pathname + url.search;
  return esAssetCacheable(ruta) ? ruta : null;
}

/**
 * Qué assets referencia el HTML de una página de Odoo (sin DOM: expresiones regulares sobre
 * `<link>`, `<script>`, `<img>` y `<picture><source>`). Solo del mismo origen y de las rutas
 * que el borde guarda (`esAssetCacheable`); el resto (CDN ajenos, canonical, RSS) se ignora.
 */
export function assetsDe(html: string, origen: URL): AssetsDePagina {
  const criticos = new Set<string>();
  const otros = new Set<string>();
  const agregar = (destino: Set<string>, ...hrefs: (string | undefined)[]) => {
    for (const href of hrefs) {
      const ruta = rutaDeAsset(href, origen);
      if (ruta) destino.add(ruta);
    }
  };
  for (const m of html.matchAll(ETIQUETA)) {
    const etiqueta = m[1].toLowerCase();
    const a = atributos(m[2]);
    if (etiqueta === "link") {
      const rel = (a.rel ?? "").toLowerCase().split(/\s+/);
      if (rel.includes("stylesheet")) agregar(criticos, a.href, a["data-href"]);
      else if (a.rel) agregar(otros, a.href, ...candidatosSrcset(a.imagesrcset)); // preload (fuentes, LCP), icon…
    } else if (etiqueta === "script") {
      agregar(criticos, a.src, a["data-src"]);
    } else if (etiqueta === "img") {
      const prioritaria = (a.loading ?? "").toLowerCase() === "eager" || (a.fetchpriority ?? "").toLowerCase() === "high";
      if (prioritaria) agregar(otros, a.src, ...candidatosSrcset(a.srcset));
    }
  }
  // <picture>: de una imagen prioritaria el navegador pide la fuente WebP, no el <img> de respaldo.
  for (const m of html.matchAll(PICTURE)) {
    if (!IMG_PRIORITARIA.test(m[1])) continue;
    for (const fuente of m[1].matchAll(/<source\b([^>]*)>/gi)) agregar(otros, ...candidatosSrcset(atributos(fuente[1]).srcset));
  }
  for (const ruta of criticos) otros.delete(ruta);
  return { criticos: [...criticos], otros: [...otros].slice(0, MAX_ASSETS_POR_PAGINA) };
}

// ------------------------------------------------------------------ guardar y servir

/** Petición con la que el borde pide un asset para guardarlo: sin cookies ni IP; con el secreto, Odoo no pone cookies. */
export function peticionDeRellenoAsset(origen: URL, rutaYQuery: string, token?: string): Request {
  const headers: Record<string, string> = {
    Accept: "*/*",
    "User-Agent": USER_AGENT_RELLENO,
    "X-Forwarded-Host": origen.host,
    "X-Forwarded-Proto": origen.protocol.replace(":", ""),
    "X-Disable-Tracking": "1",
  };
  if (token) headers[CABECERA_BORDE] = token;
  return new Request(new URL(rutaYQuery, origen.origin).toString(), { method: "GET", headers });
}

/** ¿Esta respuesta de Odoo se puede guardar y servir a cualquiera? 200, `public`, sin cookies, entera. */
export function esAssetGuardable(respuesta: Response): boolean {
  if (!isCacheableResponse(respuesta)) return false;
  if (respuesta.headers.has("Content-Range")) return false;
  return Number(respuesta.headers.get("Content-Length") ?? 0) <= MAX_BYTES_ASSET;
}

/** Cabeceras de Odoo que se guardan (KV admite 1024 bytes de metadatos) y se devuelven tal cual. */
const CABECERAS_GUARDADAS: Record<string, string> = {
  ct: "Content-Type",
  cc: "Cache-Control",
  et: "ETag",
  lm: "Last-Modified",
  cd: "Content-Disposition",
  csp: "Content-Security-Policy",
};

export function metaDeAsset(headers: Headers, t: number): Record<string, string> {
  const meta: Record<string, string> = { t: String(t) };
  for (const [clave, nombre] of Object.entries(CABECERAS_GUARDADAS)) {
    const valor = headers.get(nombre);
    if (valor !== null) meta[clave] = valor;
  }
  // Lo único que puede crecer es el nombre de archivo de Content-Disposition: sobra.
  if (JSON.stringify(meta).length > 900) delete meta.cd;
  return meta;
}

function cabecerasDeMeta(meta: Record<string, string> | null | undefined): Headers {
  const headers = new Headers();
  for (const [clave, nombre] of Object.entries(CABECERAS_GUARDADAS)) {
    const valor = meta?.[clave];
    if (valor) headers.set(nombre, valor);
  }
  if (!headers.has("Content-Type")) headers.set("Content-Type", "application/octet-stream");
  return headers;
}

function responderAsset(request: Request, entrada: EntradaBinaria, estado: CacheStatus): Response {
  const headers = cabecerasDeMeta(entrada.meta);
  const completa = new Response(entrada.bytes, { status: 200, headers });
  if (notModified(request, completa)) return withCacheStatus(notModifiedResponse(completa), estado);
  if (request.method === "HEAD") {
    headers.set("Content-Length", String(entrada.bytes.byteLength));
    return withCacheStatus(new Response(null, { status: 200, headers }), estado);
  }
  return withCacheStatus(completa, estado);
}

async function guardarAsset(deps: DepsAssets, clave: string, respuesta: Response, t: number, ruta: string): Promise<void> {
  const bytes = await respuesta.arrayBuffer();
  if (bytes.byteLength > MAX_BYTES_ASSET) {
    console.warn(JSON.stringify({ evento: "asset_demasiado_grande", ruta, bytes: bytes.byteLength }));
    return;
  }
  await deps.almacen.escribirBinario(clave, bytes, metaDeAsset(respuesta.headers, t), TTL_ASSET_S);
}

/**
 * Asset pedido por un visitante:
 * - guardado y vigente → HIT (304 si el navegador ya lo tiene; Odoo ni se entera);
 * - no está, o es un estático sin versión anterior a la última invalidación → MISS: se pide a Odoo
 *   la versión completa y, si es guardable, se guarda en segundo plano;
 * - Odoo responde 5xx (arrancando) y había copia vieja → STALE: se sirve la vieja;
 * - lo demás (Range, Authorization, respuesta no guardable) → `null` o BYPASS: lo que diga Odoo.
 * `null` también si el almacén falla: el llamador sigue como si esta caché no existiera.
 */
export async function servirAsset(
  request: Request,
  upstream: Request,
  deps: DepsAssets,
  reenviar: (pedido: Request) => Promise<Response>,
): Promise<Response | null> {
  if (!isCacheableRequest(request) || request.headers.has("Range")) return null;
  const url = new URL(request.url);
  const ruta = url.pathname + url.search;
  const versionado = esAssetVersionado(ruta);
  const clave = claveAsset(ruta);
  let entrada: EntradaBinaria | null;
  let invalidado: number;
  try {
    [entrada, invalidado] = await Promise.all([
      deps.almacen.leerBinario(clave),
      versionado ? Promise.resolve(0) : leerInvalidado(deps.almacen),
    ]);
  } catch (error) {
    console.error(JSON.stringify({ evento: "asset_lectura_fallida", ruta, error: String(error) }));
    return null;
  }
  const t = Number(entrada?.meta?.t ?? NaN);
  if (entrada && (versionado || (Number.isFinite(t) && t >= invalidado))) return responderAsset(request, entrada, "HIT");

  // Se pide la versión completa: con If-None-Match Odoo diría 304 y no habría nada que guardar. El
  // 304 para este navegador lo arma el borde con la copia.
  const llenar = request.method === "GET";
  let pedido = upstream;
  if (llenar) {
    const headers = new Headers(upstream.headers);
    for (const nombre of CONDITIONAL_HEADERS) headers.delete(nombre);
    pedido = new Request(upstream, { headers });
  }
  const inicio = (deps.ahora ?? Date.now)();
  const respuesta = await reenviar(pedido);
  if (llenar && esAssetGuardable(respuesta)) {
    enSegundoPlano(deps.waitUntil, guardarAsset(deps, clave, respuesta.clone(), inicio, ruta), "asset_escritura_fallida", ruta);
    if (notModified(request, respuesta)) {
      await respuesta.body?.cancel();
      return withCacheStatus(notModifiedResponse(respuesta), "MISS");
    }
    return withCacheStatus(respuesta, "MISS");
  }
  if (respuesta.status >= 500 && entrada) {
    // Estático sin versión que caducó con una invalidación y Odoo no responde: mejor viejo que roto.
    await respuesta.body?.cancel();
    return responderAsset(request, entrada, "STALE");
  }
  return withCacheStatus(respuesta, "BYPASS");
}

// ------------------------------------------------------------------ precalentar

/** Assets ya pedidos (o en curso) en una misma corrida: los bundles son los mismos en todas las páginas. */
export type ContextoAssets = Map<string, Promise<boolean>>;

/** Deja el asset en el almacén (si no está, o está por caducar antes que una página nueva). `true` si quedó. */
async function asegurarAsset(origen: URL, ruta: string, deps: DepsAssets): Promise<boolean> {
  const clave = claveAsset(ruta);
  const versionado = esAssetVersionado(ruta);
  const ahora = (deps.ahora ?? Date.now)();
  try {
    const [meta, invalidado] = await Promise.all([
      deps.almacen.meta(clave),
      versionado ? Promise.resolve(0) : leerInvalidado(deps.almacen),
    ]);
    const t = Number(meta?.t ?? NaN);
    const vigente = meta !== null && Number.isFinite(t) && t >= invalidado;
    if (vigente && ahora - t < RETOCAR_TRAS_MS) return true;
    const respuesta = await deps.forward(peticionDeRellenoAsset(origen, ruta, deps.token));
    if (!esAssetGuardable(respuesta)) {
      await respuesta.body?.cancel();
      return vigente;
    }
    await guardarAsset(deps, clave, respuesta, ahora, ruta);
    return true;
  } catch (error) {
    console.error(JSON.stringify({ evento: "asset_precalentar_fallido", ruta, error: String(error) }));
    return false;
  }
}

/**
 * Pide a Odoo y guarda los assets que falten. Devuelve cuántos de `rutas` quedaron en el almacén.
 * `contexto` evita pedir dos veces el mismo asset en una corrida (p. ej. al precalentar 40 páginas
 * que comparten los mismos bundles). De a pocos: el contenedor es chico.
 */
export async function precalentarAssets(
  origen: URL,
  rutas: string[],
  deps: DepsAssets,
  contexto: ContextoAssets = new Map(),
  paralelo = 4,
): Promise<number> {
  const tareas: Promise<boolean>[] = [];
  const nuevas = rutas.filter((ruta) => !contexto.has(ruta));
  for (const ruta of rutas) if (contexto.has(ruta)) tareas.push(contexto.get(ruta)!);
  for (let i = 0; i < nuevas.length; i += paralelo) {
    const lote = nuevas.slice(i, i + paralelo).map((ruta) => {
      const tarea = asegurarAsset(origen, ruta, deps);
      contexto.set(ruta, tarea);
      return tarea;
    });
    await Promise.all(lote);
    tareas.push(...lote);
  }
  return (await Promise.all(tareas)).filter(Boolean).length;
}

/** ¿Están todos en el almacén? (solo metadatos: no baja los bytes) */
export async function assetsPresentes(rutas: string[], almacen: AlmacenTienda): Promise<boolean> {
  const metas = await Promise.all(rutas.map((ruta) => almacen.meta(claveAsset(ruta))));
  return metas.every((meta) => meta !== null);
}
