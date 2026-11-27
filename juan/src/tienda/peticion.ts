// El cuerpo de `POST /tienda/v1/mensaje` (contrato §2), validado. Todo lo que manda el navegador es DATO del visitante: se recorta,
// se limpia y nunca llega como orden al modelo. La ubicación (y su precisión) se usa solo en el turno en que llega: este objeto no se
// guarda.

import { TIPOS_DE_PAGINA, type DatosDeLaPagina, type LineaDelCarrito, type TipoDePagina } from "./prompt";

/** El tope del contrato: el visitante escribe hasta 500 letras por mensaje. */
export const MAX_TEXTO = 500;
const MAX_LINEAS_DEL_CARRITO = 20;
const MAX_NOMBRE = 80;
const MAX_CATEGORIA = 60;
const MAX_ID = 2 ** 31;

/**
 * Por qué Odoo no sumó el envío (`POST /dcasa/brian/v1/carrito/envio`): la página lo cuenta tal cual. Otro motivo cualquiera se
 * lee como `fallo` (nunca llega texto libre de la página a lo que dice Andrés).
 */
export const MOTIVOS_DEL_ENVIO = ["sin_carrito", "sin_tarifa", "aparte", "lugar", "ajeno", "tope", "apagado", "fallo"] as const;
export type MotivoDelEnvio = (typeof MOTIVOS_DEL_ENVIO)[number];

export type AccionTienda =
  | { tipo: "chip"; valor: string }
  | { tipo: "confirmar_carrito"; producto_id: number; cantidad: number; resultado: "ok" | "error" }
  /** A2: lo que pasó cuando la página le pidió a Odoo sumar el envío que Andrés propuso (`sumar_envio`). */
  | { tipo: "confirmar_envio"; lugar_id: number; resultado: "ok" | "error"; motivo: MotivoDelEnvio | null }
  /** A4: lo que pasó cuando la página aplicó en Odoo el cambio que Andrés propuso (`proponer_cambio_carrito`). */
  | { tipo: "confirmar_cambio"; producto_id: number; cantidad: number; resultado: "ok" | "error" }
  /** A3: el visitante bajó una cantidad o quitó algo del carrito (con el chat abierto). `ahora` 0 = lo quitó. */
  | { tipo: "carrito_bajo"; producto_id: number | null; nombre: string; antes: number; ahora: number }
  | { tipo: "calificar"; estrellas: number };

/** A2: el envío que ya está en el carrito (lo dice Odoo a la página; la página se lo pasa al Worker como dato). */
export interface EnvioDelCarrito {
  lugar_id: number | null;
  lugar: string;
}

export interface Ubicacion {
  lat: number;
  lon: number;
  /**
   * Cuántos metros de error dice el teléfono (`coords.accuracy`), si la página lo manda. Como las coordenadas: solo vale en este turno y no
   * se guarda; a Odoo no le llega (cotizar_envio solo recibe el punto).
   */
  precision?: number;
}

/** Más que esto no es una precisión: Panamá entero cabe en mucho menos (la de un computador sin GPS anda en unos kilómetros). */
export const MAX_PRECISION_M = 1_000_000;
/** Siete decimales (≈1 cm), como en los canales (canales/ubicacion.ts): más no dice nada. */
const conSieteDecimales = (n: number) => Math.round(n * 1e7) / 1e7 || 0; // `|| 0`: nunca «-0»

export interface PeticionTienda {
  /** Lo que escribió el visitante (vacío si vino una acción o solo la ubicación). */
  texto: string;
  accion: AccionTienda | null;
  pagina: DatosDeLaPagina;
  carrito: LineaDelCarrito[];
  /** El envío que la página dice que ya está sumado en el carrito (o null). Dato de la página, como las líneas. */
  envioDelCarrito: EnvioDelCarrito | null;
  /** Solo el turno en que tocó «Usar mi ubicación». Nunca se guarda. */
  ubicacion: Ubicacion | null;
}

const esObjeto = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
const entero = (v: unknown, min: number, max: number): number | null => (typeof v === "number" && Number.isInteger(v) && v >= min && v <= max ? v : null);

/** Un texto corto de la página (nombre de una línea del carrito, categoría): sin controles ni saltos, recortado. */
export function textoCorto(v: unknown, max: number): string {
  if (typeof v !== "string") return "";
  return v.replace(/[\u0000-\u001f\u007f\u2028\u2029]+/g, " ").replace(/\s+/g, " ").trim().slice(0, max);
}

/** El texto del visitante: sin controles (los saltos de línea sí), recortado. `null` = más largo que el tope. */
function textoDelVisitante(v: unknown): string | null {
  if (v === undefined || v === null) return "";
  if (typeof v !== "string") return null;
  if ([...v].length > MAX_TEXTO) return null;
  return v.replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]+/g, " ").trim();
}

function validarAccion(v: unknown): AccionTienda | null | "mal" {
  if (v === undefined || v === null) return null;
  if (!esObjeto(v)) return "mal";
  if (v.tipo === "chip") {
    const valor = textoDelVisitante(v.valor);
    return valor ? { tipo: "chip", valor } : "mal";
  }
  if (v.tipo === "confirmar_carrito") {
    const producto_id = entero(v.producto_id, 1, 2 ** 31);
    const cantidad = entero(v.cantidad, 1, 20);
    if (producto_id === null || cantidad === null || (v.resultado !== "ok" && v.resultado !== "error")) return "mal";
    return { tipo: "confirmar_carrito", producto_id, cantidad, resultado: v.resultado };
  }
  if (v.tipo === "confirmar_envio") {
    const lugar_id = entero(v.lugar_id, 1, MAX_ID);
    if (lugar_id === null || (v.resultado !== "ok" && v.resultado !== "error")) return "mal";
    const motivo = v.resultado === "ok" ? null : (MOTIVOS_DEL_ENVIO as readonly unknown[]).includes(v.motivo) ? (v.motivo as MotivoDelEnvio) : "fallo";
    return { tipo: "confirmar_envio", lugar_id, resultado: v.resultado, motivo };
  }
  if (v.tipo === "confirmar_cambio") {
    const producto_id = entero(v.producto_id, 1, MAX_ID);
    const cantidad = entero(v.cantidad, 0, 20);
    if (producto_id === null || cantidad === null || (v.resultado !== "ok" && v.resultado !== "error")) return "mal";
    return { tipo: "confirmar_cambio", producto_id, cantidad, resultado: v.resultado };
  }
  if (v.tipo === "carrito_bajo") {
    const antes = entero(v.antes, 1, 999);
    const ahora = entero(v.ahora, 0, 998);
    if (antes === null || ahora === null || ahora >= antes) return "mal";
    return { tipo: "carrito_bajo", producto_id: entero(v.producto_id, 1, MAX_ID), nombre: textoCorto(v.nombre, MAX_NOMBRE), antes, ahora };
  }
  if (v.tipo === "calificar") {
    const estrellas = entero(v.estrellas, 1, 5);
    return estrellas === null ? "mal" : { tipo: "calificar", estrellas };
  }
  return "mal";
}

function validarPagina(v: unknown): DatosDeLaPagina {
  const p = esObjeto(v) ? v : {};
  const tipo = typeof p.tipo === "string" && (TIPOS_DE_PAGINA as readonly string[]).includes(p.tipo) ? (p.tipo as TipoDePagina) : "otra";
  return { tipo, producto_id: entero(p.producto_id, 1, 2 ** 31), categoria: textoCorto(p.categoria, MAX_CATEGORIA) };
}

function validarCarrito(v: unknown): LineaDelCarrito[] {
  const c = esObjeto(v) ? v : {};
  const lineas = Array.isArray(c.lineas) ? c.lineas : [];
  const salida: LineaDelCarrito[] = [];
  for (const l of lineas.slice(0, MAX_LINEAS_DEL_CARRITO)) {
    if (!esObjeto(l)) continue;
    const nombre = textoCorto(l.nombre, MAX_NOMBRE);
    const cantidad = entero(l.cantidad, 1, 999);
    if (!nombre || cantidad === null) continue;
    salida.push({ producto_id: entero(l.producto_id, 1, 2 ** 31), nombre, cantidad });
  }
  return salida;
}

function validarEnvioDelCarrito(v: unknown): EnvioDelCarrito | null {
  const c = esObjeto(v) ? v : {};
  if (!esObjeto(c.envio)) return null;
  const lugar = textoCorto(c.envio.lugar, MAX_NOMBRE);
  const lugar_id = entero(c.envio.lugar_id, 1, MAX_ID);
  return lugar || lugar_id !== null ? { lugar_id, lugar } : null;
}

function validarUbicacion(v: unknown): Ubicacion | null | "mal" {
  if (v === undefined || v === null) return null;
  if (!esObjeto(v)) return "mal";
  const { lat, lon, precision } = v;
  if (typeof lat !== "number" || typeof lon !== "number" || !Number.isFinite(lat) || !Number.isFinite(lon)) return "mal";
  if (lat < -90 || lat > 90 || lon < -180 || lon > 180) return "mal";
  // La precisión es opcional (una página de antes no la manda); si viene, es un número de metros, como lat y lon: nada de texto.
  if (precision !== undefined && precision !== null) {
    if (typeof precision !== "number" || !Number.isFinite(precision) || precision < 0 || precision > MAX_PRECISION_M) return "mal";
    return { lat: conSieteDecimales(lat), lon: conSieteDecimales(lon), precision };
  }
  return { lat: conSieteDecimales(lat), lon: conSieteDecimales(lon) };
}

/** La petición validada, o el motivo (en palabras) por el que no sirve. */
export function validarPeticionTienda(cuerpo: unknown): PeticionTienda | string {
  if (!esObjeto(cuerpo)) return "el cuerpo debe ser un objeto JSON";
  const texto = textoDelVisitante(cuerpo.texto);
  if (texto === null) return `el texto tiene como máximo ${MAX_TEXTO} letras`;
  const accion = validarAccion(cuerpo.accion);
  if (accion === "mal") return "acción inválida";
  const ubicacion = validarUbicacion(cuerpo.ubicacion);
  if (ubicacion === "mal") return "ubicación inválida";
  // La acción va EN LUGAR del texto (contrato §2).
  const final = accion ? "" : texto;
  if (!final && !accion && !ubicacion) return "falta el texto";
  return { texto: final, accion, pagina: validarPagina(cuerpo.pagina), carrito: validarCarrito(cuerpo.carrito), envioDelCarrito: validarEnvioDelCarrito(cuerpo.carrito), ubicacion };
}
