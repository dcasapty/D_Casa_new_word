// Enlaces de mapa en el texto del cliente (docs/UBICACION.md, «Contrato…» §4): de un enlace de Google Maps, Waze o Apple Maps sale
// el punto de entrega sin que el cliente copie nada. Es lógica pura: la red (solo para los enlaces cortos de Google) entra como `fetch`.
//
//   · Google:  `google.com/maps/…` y `maps.google.com/…` con `!3dLAT!4dLON` (el pin del lugar), `?q=` / `?query=` / `?ll=` con
//              «lat,lon», `/maps/search/LAT,LON` o `/maps/place/LAT,LON`, y `/@LAT,LON` (el centro del mapa), en ese orden.
//   · Cortos:  `maps.app.goo.gl/…` y `goo.gl/maps/…` no traen el punto: se sigue su redirección A MANO (`redirect: "manual"`, leyendo
//              solo la cabecera `Location`), únicamente hacia hosts de Google de la lista, como mucho 3 saltos y 5 s, sin leer el cuerpo.
//   · Waze:    `waze.com/ul?ll=LAT,LON`, y `waze.com/ul/h<geohash>` (lo que comparte la app; un geohash ES el punto, codificado: de 8
//              letras o más, ±19 m o mejor).
//   · Apple:   `maps.apple.com/?ll=`, `?q=` (si es «lat,lon») o `?coordinate=`.
//
// Un enlace sin coordenadas (una búsqueda por nombre) no se adivina: queda en el texto tal cual. Los números necesitan al menos 3
// decimales (≈100 m): «q=1,2» no es un punto de entrega.

import { coordenadasValidas, TEXTO_ENLACE_DE_MAPA, TEXTO_ENLACE_EN_EL_TEXTO } from "../canales/ubicacion";

export interface Coordenadas {
  lat: number;
  lon: number;
}

/** Solo a estos se sigue una redirección (contrato §4). */
export const HOSTS_QUE_SE_SIGUEN: ReadonlySet<string> = new Set(["maps.app.goo.gl", "goo.gl", "maps.google.com", "www.google.com", "google.com"]);
export const MAX_SALTOS = 3;
export const PLAZO_RESOLVER_MS = 5000;
/** Cuántos enlaces de mapa CORTOS se siguen por la red por mensaje. Los que traen el punto escrito se tapan todos (auditoría 1: el
 * cuarto quedaba en el texto y sus coordenadas llegaban al modelo). */
export const MAX_ENLACES_POR_MENSAJE = 3;
/** Tope de enlaces que se miran en un mensaje (un mensaje de 4.000 letras no trae más). */
const MAX_ENLACES_MIRADOS = 60;

const HOST_GOOGLE = /^(?:www\.|maps\.)?google\.(?:com?|[a-z]{2})(?:\.[a-z]{2})?$/;
const HOST_WAZE = /^(?:www\.|ul\.)?waze\.com$/;
const HOST_APPLE = /^maps\.apple\.com$/;

/** Un número de coordenada con al menos 3 decimales. */
const NUM = String.raw`[-+]?\d{1,3}\.\d{3,}`;
const PAR = new RegExp(String.raw`^\s*(?:loc:)?\s*\+?(${NUM})\s*,\s*\+?(${NUM})\s*$`);

function par(v: string | null | undefined): Coordenadas | null {
  const m = v ? PAR.exec(v) : null;
  return m ? coordenadasValidas(m[1], m[2]) : null;
}

function decodificar(t: string): string {
  try {
    return decodeURIComponent(t.replace(/\+/g, " "));
  } catch {
    return t;
  }
}

function aUrl(href: string): URL | null {
  try {
    const u = new URL(href);
    return u.protocol === "https:" || u.protocol === "http:" ? u : null;
  } catch {
    return null;
  }
}

const esCortoDeGoogle = (u: URL) => u.hostname.toLowerCase() === "maps.app.goo.gl" || (u.hostname.toLowerCase() === "goo.gl" && /^\/maps(?:\/|$)/.test(u.pathname));
const esDeGoogleMaps = (u: URL) => {
  const host = u.hostname.toLowerCase();
  return HOST_GOOGLE.test(host) && (host.startsWith("maps.") || /^\/maps(?:\/|$|\?)/.test(u.pathname));
};

/** ¿Es un enlace de mapa que se reconoce (traiga o no coordenadas)? */
export function esEnlaceDeMapa(href: string): boolean {
  const u = aUrl(href);
  if (!u) return false;
  const host = u.hostname.toLowerCase();
  return esCortoDeGoogle(u) || esDeGoogleMaps(u) || (HOST_WAZE.test(host) && /^\/ul(?:\/|$)/.test(u.pathname)) || HOST_APPLE.test(host);
}

function deGoogle(u: URL): Coordenadas | null {
  const ruta = decodificar(u.pathname);
  // El pin del lugar (`…/data=…!3d9.0123!4d-79.5111…`): el último, por si la dirección trae más de uno.
  const pines = [...ruta.matchAll(new RegExp(String.raw`!3d(${NUM})!4d(${NUM})`, "g"))];
  const pin = pines.length ? coordenadasValidas(pines[pines.length - 1][1], pines[pines.length - 1][2]) : null;
  if (pin) return pin;
  for (const clave of ["q", "query", "ll"]) {
    const c = par(u.searchParams.get(clave));
    if (c) return c;
  }
  const buscado = new RegExp(String.raw`/maps/(?:search|place)/\s*\+?(${NUM})\s*,\s*\+?(${NUM})`).exec(ruta);
  if (buscado) return coordenadasValidas(buscado[1], buscado[2]);
  // El centro del mapa (`/@9.0123,-79.5111,17z`): lo último, porque es donde estaba el mapa, no necesariamente el lugar.
  const centro = new RegExp(String.raw`/@(${NUM}),(${NUM})`).exec(ruta);
  return centro ? coordenadasValidas(centro[1], centro[2]) : null;
}

const BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz";

/** Un geohash, decodificado (el centro de su celda). null si trae letras que no son del alfabeto. */
export function decodificarGeohash(h: string): Coordenadas | null {
  const lat = [-90, 90];
  const lon = [-180, 180];
  let esLon = true;
  for (const letra of h.toLowerCase()) {
    const v = BASE32.indexOf(letra);
    if (v < 0) return null;
    // Cada letra son 5 bits, alternando longitud y latitud: cada bit parte el intervalo por la mitad.
    for (let b = 4; b >= 0; b--) {
      const r = esLon ? lon : lat;
      r[(v >> b) & 1 ? 0 : 1] = (r[0] + r[1]) / 2;
      esLon = !esLon;
    }
  }
  return coordenadasValidas((lat[0] + lat[1]) / 2, (lon[0] + lon[1]) / 2);
}

function deWaze(u: URL): Coordenadas | null {
  if (!/^\/ul(?:\/|$)/.test(u.pathname)) return null;
  const c = par(u.searchParams.get("ll"));
  if (c) return c;
  const g = /^\/ul\/h([0-9b-hjkmnp-z]{8,12})\/?$/i.exec(u.pathname);
  return g ? decodificarGeohash(g[1]) : null;
}

function deApple(u: URL): Coordenadas | null {
  for (const clave of ["ll", "coordinate", "q"]) {
    const c = par(u.searchParams.get(clave));
    if (c) return c;
  }
  return null;
}

/** Las coordenadas que trae ESCRITAS un enlace de mapa (sin ir a la red). null si no trae o no es un enlace de mapa. */
export function coordenadasDeEnlace(href: string): Coordenadas | null {
  const u = aUrl(href);
  if (!u) return null;
  const host = u.hostname.toLowerCase();
  if (esDeGoogleMaps(u)) return deGoogle(u);
  if (HOST_WAZE.test(host)) return deWaze(u);
  if (HOST_APPLE.test(host)) return deApple(u);
  return null;
}

/** ¿Se puede pedir esta dirección al seguir un enlace corto? Solo https, sin usuario ni puerto, y a un host de la lista. */
function sePuedeSeguir(u: URL): boolean {
  return u.protocol === "https:" && !u.username && !u.password && !u.port && HOSTS_QUE_SE_SIGUEN.has(u.hostname.toLowerCase());
}

/**
 * Un enlace corto de Google (`maps.app.goo.gl/…`, `goo.gl/maps/…`): se sigue su redirección a mano, leyendo solo la cabecera
 * `Location` (el cuerpo no se lee), mientras apunte a un host de Google de la lista. Como mucho `MAX_SALTOS` peticiones y una señal
 * que corta todo. Nunca lanza: null si no llega a un enlace con coordenadas.
 */
export async function resolverEnlaceCorto(href: string, f: typeof fetch, senal: AbortSignal): Promise<Coordenadas | null> {
  let actual = aUrl(href);
  if (!actual || !esCortoDeGoogle(actual)) return null;
  try {
    for (let salto = 0; salto < MAX_SALTOS && actual; salto++) {
      if (!sePuedeSeguir(actual) || senal.aborted) return null;
      const r = await f(actual.toString(), { method: "GET", redirect: "manual", signal: senal, headers: { accept: "text/html" } });
      void r.body?.cancel().catch(() => {});
      const destino = r.status >= 300 && r.status < 400 ? r.headers.get("location") : null;
      if (!destino) return null;
      let siguiente: URL;
      try {
        siguiente = new URL(destino, actual);
      } catch {
        return null;
      }
      // Que el destino traiga el punto escrito basta: no hace falta pedirlo.
      const c = coordenadasDeEnlace(siguiente.toString());
      if (c) return c;
      actual = siguiente;
    }
  } catch {
    // Se cortó por el plazo, o la red falló: no hay punto.
  }
  return null;
}

interface EnlaceHallado {
  inicio: number;
  fin: number;
  href: string;
}

/** Los enlaces de mapa del texto, con su posición (sin los signos de la frase que los rodean). Como mucho `MAX_ENLACES_MIRADOS`. */
export function enlacesDeMapaEn(texto: string): EnlaceHallado[] {
  const hallados: EnlaceHallado[] = [];
  for (const m of texto.matchAll(/\S+/g)) {
    let pedazo = m[0];
    let inicio = m.index ?? 0;
    const antes = /^[(<[«"'“¿¡]+/.exec(pedazo)?.[0].length ?? 0;
    pedazo = pedazo.slice(antes).replace(/[)>\]»"'”.,;:!?]+$/, "");
    inicio += antes;
    if (!pedazo) continue;
    const href = /^https?:\/\//i.test(pedazo) ? pedazo : /^[a-z0-9-]+(?:\.[a-z0-9-]+)+\//i.test(pedazo) ? `https://${pedazo}` : null;
    if (!href || !esEnlaceDeMapa(href)) continue;
    hallados.push({ inicio, fin: inicio + pedazo.length, href });
    if (hallados.length >= MAX_ENLACES_MIRADOS) break;
  }
  return hallados;
}

export interface UbicacionDelTexto {
  /** El texto con cada enlace que dio un punto cambiado por una frase sin coordenadas (igual al original si ninguno lo dio). */
  texto: string;
  /** El punto del primer enlace que lo dio; null si ninguno. */
  coordenadas: Coordenadas | null;
}

/** Arma el texto sin los enlaces que dieron un punto. Si no queda nada más que el enlace, la frase entera. */
function reemplazar(texto: string, hallados: EnlaceHallado[], puntos: (Coordenadas | null)[]): UbicacionDelTexto {
  let salida = "";
  let desde = 0;
  let primero: Coordenadas | null = null;
  hallados.forEach((h, i) => {
    const c = puntos[i];
    if (!c) return;
    primero ??= c;
    salida += `${texto.slice(desde, h.inicio)}${TEXTO_ENLACE_EN_EL_TEXTO}`;
    desde = h.fin;
  });
  if (!primero) return { texto, coordenadas: null };
  salida += texto.slice(desde);
  const sinFrase = salida.split(TEXTO_ENLACE_EN_EL_TEXTO).join("");
  return { texto: /[\p{L}\p{N}]/u.test(sinFrase) ? salida.trim() : TEXTO_ENLACE_DE_MAPA, coordenadas: primero };
}

/** Coordenadas escritas a mano («8.9012, -79.8013»), con al menos 3 decimales cada una, sueltas (no dentro de un enlace). */
const PAR_SUELTO = /(?<=^|[\s(:«"])([-+]?\d{1,2}\.\d{3,})\s*,\s*([-+]?\d{1,3}\.\d{3,})(?![\w.])/g;
/** Panamá con holgura: un par fuera de aquí (un precio, una medida) no se toca. */
const enPanama = (c: Coordenadas) => c.lat >= 7 && c.lat <= 10 && c.lon >= -83.5 && c.lon <= -77;

/** «lat 8.9012 lon -79.8013» / «latitud: 8.9012, longitud: -79.8013». */
const PAR_CON_NOMBRE = /\blat(?:itud)?\s*[:=]?\s*([-+]?\d{1,2}\.\d{3,})\s*[,;]?\s*(?:lon|lng|long|longitud)\s*[:=]?\s*([-+]?\d{1,3}\.\d{3,})/gi;
/** Apple Maps y otros: «8.90119° N, 79.80131° W». */
const PAR_CON_HEMISFERIO = /(\d{1,2}\.\d{3,})\s*°?\s*([NS])\s*[,;]?\s*(\d{1,3}\.\d{3,})\s*°?\s*([EOW])\b/gi;
/** Grados, minutos y segundos: «8°54'04.3"N 79°48'04.7"W». */
const PAR_GMS = /(\d{1,2})\s*°\s*(\d{1,2})\s*['′]\s*(\d{1,2}(?:\.\d+)?)\s*(?:"|″|'')\s*([NS])\s*[,;]?\s*(\d{1,3})\s*°\s*(\d{1,2})\s*['′]\s*(\d{1,2}(?:\.\d+)?)\s*(?:"|″|'')\s*([EOW])/gi;
/** Un código Plus de Google («7Q2F+3X», «7Q2F+3X La Chorrera»): no se decodifica, pero señala la casa: se tapa. */
const CODIGO_PLUS = /\b[23456789CFGHJMPQRVWX]{4,8}\+[23456789CFGHJMPQRVWX]{2,3}\b/gi;

const conSigno = (valor: number, hemisferio: string) => (/[SWO]/i.test(hemisferio) ? -valor : valor);

/**
 * Las coordenadas escritas a mano dentro de Panamá (decimales sueltos, con nombre, con hemisferio o en grados-minutos-segundos) se
 * tapan como un enlace (auditorías 1 y 2: llegaban tal cual al modelo) y, si ningún enlace dio un punto, son el punto. Un código Plus
 * se tapa también (no se decodifica).
 */
function taparParesSueltos(r: UbicacionDelTexto): UbicacionDelTexto {
  let primero = r.coordenadas;
  let hubo = false;
  const tapar = (todo: string, c: Coordenadas | null): string => {
    if (!c || !enPanama(c)) return todo;
    hubo = true;
    primero ??= c;
    return TEXTO_ENLACE_EN_EL_TEXTO;
  };
  let texto = r.texto
    .replace(PAR_CON_NOMBRE, (todo: string, a: string, b: string) => tapar(todo, coordenadasValidas(a, b)))
    .replace(PAR_CON_HEMISFERIO, (todo: string, a: string, ns: string, b: string, eo: string) =>
      tapar(todo, coordenadasValidas(conSigno(Number(a), ns), conSigno(Number(b), eo))),
    )
    .replace(PAR_GMS, (todo: string, g1: string, m1: string, s1: string, ns: string, g2: string, m2: string, s2: string, eo: string) => {
      const lat = conSigno(Number(g1) + Number(m1) / 60 + Number(s1) / 3600, ns);
      const lon = conSigno(Number(g2) + Number(m2) / 60 + Number(s2) / 3600, eo);
      return tapar(todo, coordenadasValidas(lat, lon));
    })
    .replace(PAR_SUELTO, (todo: string, a: string, b: string) => tapar(todo, coordenadasValidas(a, b)));
  texto = texto.replace(CODIGO_PLUS, () => {
    hubo = true;
    return TEXTO_ENLACE_EN_EL_TEXTO;
  });
  if (!hubo) return r;
  const sinFrase = texto.split(TEXTO_ENLACE_EN_EL_TEXTO).join("");
  return { texto: /[\p{L}\p{N}]/u.test(sinFrase) ? texto.trim() : TEXTO_ENLACE_DE_MAPA, coordenadas: primero };
}

/**
 * Sin ir a la red: quita del texto los enlaces que traen las coordenadas escritas (los cortos quedan: no las traen) y las coordenadas
 * escritas a mano. Es lo que se guarda en la copia de rescate (canales/preparar.ts → `crudoDe`), que nunca guarda un punto.
 */
export function quitarCoordenadasDelTexto(texto: string): UbicacionDelTexto {
  const hallados = enlacesDeMapaEn(texto);
  if (hallados.length === 0) return taparParesSueltos({ texto, coordenadas: null });
  return taparParesSueltos(reemplazar(texto, hallados, hallados.map((h) => coordenadasDeEnlace(h.href))));
}

/**
 * El punto de entrega que trae el texto del cliente, si trae un enlace de mapa con coordenadas (escritas o detrás de un enlace corto de
 * Google), y el texto sin esas coordenadas. Un solo plazo para todo el mensaje. Nunca lanza.
 */
export async function ubicacionDelTexto(texto: string, op: { fetch?: typeof fetch; plazoMs?: number } = {}): Promise<UbicacionDelTexto> {
  const hallados = enlacesDeMapaEn(texto);
  if (hallados.length === 0) return taparParesSueltos({ texto, coordenadas: null });
  const f: typeof fetch = op.fetch ?? ((...a) => fetch(...a));
  const control = new AbortController();
  const reloj = setTimeout(() => control.abort(), op.plazoMs ?? PLAZO_RESOLVER_MS);
  try {
    const puntos: (Coordenadas | null)[] = [];
    let seguidos = 0;
    for (const h of hallados) {
      const escrito = coordenadasDeEnlace(h.href);
      if (escrito || seguidos >= MAX_ENLACES_POR_MENSAJE) {
        puntos.push(escrito);
        continue;
      }
      seguidos += 1;
      puntos.push(await resolverEnlaceCorto(h.href, f, control.signal));
    }
    return taparParesSueltos(reemplazar(texto, hallados, puntos));
  } finally {
    clearTimeout(reloj);
  }
}
