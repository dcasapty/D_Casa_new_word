/**
 * Almacén del borde (en producción, el namespace de Workers KV `TIENDA`; en los tests, un Map) y
 * lo que comparten la caché de páginas (paginas.ts) y la de assets (assets.ts).
 *
 * Claves:
 * - `html:<host><ruta>`  → página de Odoo (texto) con metadatos `{ t, etag, ct, assets }`.
 * - `asset:<ruta?query>` → estilos, JS, fuentes e imágenes (bytes) con metadatos `{ t, ct, cc, et, lm… }`.
 * - `invalidado`         → ms de la última invalidación (aviso de Odoo). Una página, o un estático
 *   sin versión en la URL, vale si `t ≥ invalidado`. Los assets con versión en la URL (hash de
 *   Odoo, `?unique=`, `?v=`) no miran esta marca: su contenido no cambia nunca.
 */

export interface EntradaAlmacen {
  texto: string;
  meta?: Record<string, string> | null;
}

export interface EntradaBinaria {
  bytes: ArrayBuffer;
  meta?: Record<string, string> | null;
}

export interface AlmacenTienda {
  leer(clave: string): Promise<EntradaAlmacen | null>;
  /** `ttlSegundos`: KV borra la clave solo pasado ese tiempo (páginas que nadie vuelve a pedir). */
  escribir(clave: string, texto: string, meta?: Record<string, string>, ttlSegundos?: number): Promise<void>;
  leerBinario(clave: string): Promise<EntradaBinaria | null>;
  escribirBinario(clave: string, bytes: ArrayBuffer, meta?: Record<string, string>, ttlSegundos?: number): Promise<void>;
  /** Solo los metadatos (¿existe?, ¿de cuándo?), sin bajar el valor. `null` si la clave no está. */
  meta(clave: string): Promise<Record<string, string> | null>;
}

export const CLAVE_INVALIDADO = "invalidado";

/**
 * Petición: el secreto `TIENDA_FEED_TOKEN` (solo lo manda el Worker al pedir a Odoo algo para
 * guardarlo: Odoo no guarda sesión ni pone cookies). Respuesta: `anonimo` si Odoo certifica que la
 * página la dibujó para un visitante anónimo. Sin esa marca, la página no se guarda.
 */
export const CABECERA_BORDE = "X-Dcasa-Borde";

export const USER_AGENT_RELLENO = "dcasa-borde/1 (+cache de paginas)";

/** KV borra la página si nadie la pidió en este tiempo (no hace falta borrar nada a mano). */
export const TTL_PAGINA_S = 7 * 24 * 60 * 60;

export async function leerInvalidado(almacen: AlmacenTienda): Promise<number> {
  const entrada = await almacen.leer(CLAVE_INVALIDADO);
  const valor = Number(entrada?.texto ?? 0);
  return Number.isFinite(valor) ? valor : 0;
}

/** Tarea que no debe tumbar la respuesta: se registra si falla y, si hay `waitUntil`, sigue tras responder. */
export function enSegundoPlano(
  waitUntil: ((promise: Promise<unknown>) => void) | undefined,
  tarea: Promise<unknown>,
  evento: string,
  ruta: string,
): Promise<unknown> {
  const segura = tarea.catch((error: unknown) => console.error(JSON.stringify({ evento, ruta, error: String(error) })));
  if (waitUntil) waitUntil(segura);
  return segura;
}
