// El cuerpo de `POST /tienda/v1/mensaje` (contrato §2), validado. Todo lo que manda el navegador es DATO del visitante: se recorta,
// se limpia y nunca llega como orden al modelo. La ubicación se usa solo en el turno en que llega: este objeto no se guarda.

import { TIPOS_DE_PAGINA, type DatosDeLaPagina, type LineaDelCarrito, type TipoDePagina } from "./prompt";

/** El tope del contrato: el visitante escribe hasta 500 letras por mensaje. */
export const MAX_TEXTO = 500;
const MAX_LINEAS_DEL_CARRITO = 20;
const MAX_NOMBRE = 80;
const MAX_CATEGORIA = 60;

export type AccionTienda =
  | { tipo: "chip"; valor: string }
  | { tipo: "confirmar_carrito"; producto_id: number; cantidad: number; resultado: "ok" | "error" }
  | { tipo: "calificar"; estrellas: number };

export interface Ubicacion {
  lat: number;
  lon: number;
}

export interface PeticionTienda {
  /** Lo que escribió el visitante (vacío si vino una acción o solo la ubicación). */
  texto: string;
  accion: AccionTienda | null;
  pagina: DatosDeLaPagina;
  carrito: LineaDelCarrito[];
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

function validarUbicacion(v: unknown): Ubicacion | null | "mal" {
  if (v === undefined || v === null) return null;
  if (!esObjeto(v)) return "mal";
  const { lat, lon } = v;
  if (typeof lat !== "number" || typeof lon !== "number" || !Number.isFinite(lat) || !Number.isFinite(lon)) return "mal";
  if (lat < -90 || lat > 90 || lon < -180 || lon > 180) return "mal";
  return { lat, lon };
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
  return { texto: final, accion, pagina: validarPagina(cuerpo.pagina), carrito: validarCarrito(cuerpo.carrito), ubicacion };
}
