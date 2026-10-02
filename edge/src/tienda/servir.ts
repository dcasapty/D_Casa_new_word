/**
 * Tienda estática: guardar las páginas generadas y servirlas (sin Cloudflare: el almacén es una
 * interfaz; en producción es un namespace de Workers KV, ver src/index.ts).
 *
 * Claves:
 * - `pagina:<ruta>` → HTML de la página, con metadatos `{ etag }`.
 * - `manifiesto` → `{ <ruta>: <etag> }` de lo publicado: permite escribir SOLO lo que cambió
 *   (las escrituras de KV son lo que cuesta) y borrar las páginas que ya no existen.
 * - `estado` → resumen de la última regeneración (diagnóstico).
 */
import { renderizarSitio } from "./render";
import { esFeedValido } from "./tipos";

export interface EntradaAlmacen {
  texto: string;
  meta?: Record<string, string> | null;
}

export interface AlmacenTienda {
  /** `fresco`: sin la caché del borde de KV (para el manifiesto al regenerar). */
  leer(clave: string, opciones?: { fresco?: boolean }): Promise<EntradaAlmacen | null>;
  escribir(clave: string, texto: string, meta?: Record<string, string>): Promise<void>;
  borrar(clave: string): Promise<void>;
}

export const CLAVE_MANIFIESTO = "manifiesto";
export const CLAVE_ESTADO = "estado";
export const clavePagina = (ruta: string) => `pagina:${ruta}`;

/** Cabecera de diagnóstico: qué sirvió la página. */
export const CABECERA_TIENDA = "X-Dcasa-Tienda";
/** Cabecera con el secreto al pedir el feed a Odoo. */
export const CABECERA_TOKEN_FEED = "X-Dcasa-Tienda-Token";
export const RUTA_FEED = "/dcasa/tienda/feed";

/** El navegador revalida siempre (max-age=0) y el ETag le ahorra la descarga si nada cambió. */
export const CACHE_PAGINA = "public, max-age=0, must-revalidate";

export async function etagDe(html: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(html));
  const hex = [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
  return `"t-${hex.slice(0, 24)}"`;
}

/** Página guardada → respuesta (304 si el navegador ya la tiene). `null` si no está: va a Odoo. */
export async function servirPaginaEstatica(
  request: Request,
  ruta: string,
  almacen: AlmacenTienda,
): Promise<Response | null> {
  const entrada = await almacen.leer(clavePagina(ruta));
  if (!entrada) return null;
  const etag = entrada.meta?.etag ?? (await etagDe(entrada.texto));
  const headers = new Headers({
    "Content-Type": "text/html; charset=utf-8",
    "Cache-Control": CACHE_PAGINA,
    ETag: etag,
    [CABECERA_TIENDA]: "estatica",
  });
  const ifNoneMatch = request.headers.get("If-None-Match");
  if (ifNoneMatch && ifNoneMatch.split(",").some((e) => e.trim().replace(/^W\//, "") === etag)) {
    return new Response(null, { status: 304, headers });
  }
  return new Response(request.method === "HEAD" ? null : entrada.texto, { status: 200, headers });
}

export interface ResultadoRegeneracion {
  estado: "ok" | "fallo";
  motivo?: string;
  paginas?: number;
  escritas?: number;
  borradas?: number;
  productos?: number;
  duracionMs?: number;
}

export interface DepsRegenerar {
  almacen: AlmacenTienda;
  /** Pide el feed a Odoo (con el secreto). */
  leerFeed: () => Promise<Response>;
  canonicalHost?: string;
  /** Escrituras simultáneas a KV. */
  paralelo?: number;
}

/** Si el sitio tenía al menos esto de páginas y el feed nuevo no trae productos, no se publica. */
const MINIMO_PARA_PROTEGER = 5;

async function enLotes<T>(items: T[], tamano: number, fn: (item: T) => Promise<void>): Promise<void> {
  for (let i = 0; i < items.length; i += tamano) await Promise.all(items.slice(i, i + tamano).map(fn));
}

/**
 * Lee el feed, genera todas las páginas y escribe solo las que cambiaron. Un feed roto o vacío
 * (con un sitio ya publicado) no borra nada: se informa el fallo y el sitio sigue como estaba.
 */
export async function regenerarTienda(deps: DepsRegenerar): Promise<ResultadoRegeneracion> {
  const inicio = Date.now();
  let respuesta: Response;
  try {
    respuesta = await deps.leerFeed();
  } catch (error) {
    return { estado: "fallo", motivo: `sin respuesta de Odoo: ${String(error)}` };
  }
  if (!respuesta.ok) {
    await respuesta.body?.cancel();
    return { estado: "fallo", motivo: `feed HTTP ${respuesta.status}` };
  }
  let feed: unknown;
  try {
    feed = await respuesta.json();
  } catch {
    return { estado: "fallo", motivo: "feed no es JSON" };
  }
  if (!esFeedValido(feed)) return { estado: "fallo", motivo: "feed inválido o de otra versión" };

  const anterior = await leerManifiesto(deps.almacen);
  if (!feed.productos.length && Object.keys(anterior).length >= MINIMO_PARA_PROTEGER) {
    return { estado: "fallo", motivo: "feed sin productos: no se borra el sitio publicado" };
  }

  const paginas = renderizarSitio(feed, { canonicalHost: deps.canonicalHost });
  const manifiesto: Record<string, string> = {};
  const cambiadas: { ruta: string; html: string; etag: string }[] = [];
  for (const pagina of paginas) {
    const etag = await etagDe(pagina.html);
    manifiesto[pagina.ruta] = etag;
    if (anterior[pagina.ruta] !== etag) cambiadas.push({ ...pagina, etag });
  }
  const sobran = Object.keys(anterior).filter((ruta) => !(ruta in manifiesto));
  const paralelo = deps.paralelo ?? 20;
  await enLotes(cambiadas, paralelo, (p) => deps.almacen.escribir(clavePagina(p.ruta), p.html, { etag: p.etag }));
  await enLotes(sobran, paralelo, (ruta) => deps.almacen.borrar(clavePagina(ruta)));
  if (cambiadas.length || sobran.length || !Object.keys(anterior).length) {
    await deps.almacen.escribir(CLAVE_MANIFIESTO, JSON.stringify(manifiesto));
  }
  const resultado: ResultadoRegeneracion = {
    estado: "ok",
    paginas: paginas.length,
    escritas: cambiadas.length,
    borradas: sobran.length,
    productos: feed.productos.length,
    duracionMs: Date.now() - inicio,
  };
  await deps.almacen.escribir(CLAVE_ESTADO, JSON.stringify({ ...resultado, generado: feed.generado }));
  return resultado;
}

async function leerManifiesto(almacen: AlmacenTienda): Promise<Record<string, string>> {
  const entrada = await almacen.leer(CLAVE_MANIFIESTO, { fresco: true });
  if (!entrada) return {};
  try {
    const datos = JSON.parse(entrada.texto) as unknown;
    return datos && typeof datos === "object" ? (datos as Record<string, string>) : {};
  } catch {
    return {};
  }
}

/** `TIENDA_ESTATICA`: "on" (también "1", "true", "si") enciende la tienda estática. */
export function tiendaActiva(valor?: string): boolean {
  return ["on", "1", "true", "si", "sí"].includes((valor ?? "").trim().toLowerCase());
}
