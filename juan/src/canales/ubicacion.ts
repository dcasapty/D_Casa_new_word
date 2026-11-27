// La ubicación de entrega que la clienta comparte por el chat (docs/UBICACION.md, «Contrato entre Odoo y el Worker de Juan»).
//
// Las coordenadas viajan del canal a Odoo (`POST /ubicacion`) y a ningún otro lado: nunca al modelo de IA, nunca al texto que se guarda
// de la conversación (aquí ni en Odoo), nunca a la memoria guardada del Durable Object ni al registro del Worker. En su lugar, el texto
// del mensaje dice solo «(la clienta compartió su ubicación de entrega)».
//
// `origen` usa los valores del contrato: «whatsapp» es una ubicación compartida EN EL CHAT (WhatsApp, y también Telegram y Messenger,
// que la comparten igual), «enlace» es un enlace de mapa pegado en el texto (motor/enlacesMapa.ts).

export type OrigenUbicacion = "whatsapp" | "enlace";

export interface UbicacionEntrante {
  lat: number;
  lon: number;
  origen: OrigenUbicacion;
  /** El nombre del lugar, si la clienta eligió un lugar en vez de su ubicación actual (WhatsApp lo manda). Hasta 120 letras. */
  nombre_lugar?: string;
  /** La dirección de ese lugar, si el canal la manda. Hasta 200 letras. */
  direccion?: string;
}

export const MAX_NOMBRE_LUGAR = 120;
export const MAX_DIRECCION = 200;

/** Lo que queda como texto del mensaje (y lo único que ve el modelo) cuando la clienta compartió su ubicación en el chat. */
export const TEXTO_UBICACION_COMPARTIDA = "(la clienta compartió su ubicación de entrega)";
/** El mensaje era solo un enlace de mapa con coordenadas. */
export const TEXTO_ENLACE_DE_MAPA = "(la clienta mandó un enlace de mapa con su ubicación de entrega)";
/** Un enlace de mapa con coordenadas dentro de un texto más largo: se cambia por esto. */
export const TEXTO_ENLACE_EN_EL_TEXTO = "(enlace de mapa con su ubicación de entrega)";
/** El canal dijo que era una ubicación, pero sin coordenadas que sirvan (o fuera de rango): no se adivina nada. */
export const TEXTO_UBICACION_ILEGIBLE = "(la clienta intentó compartir una ubicación, pero no llegó bien)";
/** Una persona de la tienda compartió una ubicación desde el teléfono: no es el punto de entrega de nadie y no se guarda. */
export const TEXTO_UBICACION_PROPIA = "(se compartió una ubicación desde el teléfono de la tienda)";

/**
 * Lo que dice encima del botón nativo «Enviar ubicación» (WhatsApp Cloud, `Saliente.pedirUbicacion`), después del mensaje con el enlace
 * de `enlace_de_ubicacion`: corto, de usted y con su ícono (el dueño, 2026-11-25: «que un niño de 5 años pueda comprar»).
 */
export const TEXTO_BOTON_UBICACION = "📍 O toque «Enviar ubicación» y listo.";
/** En el mensaje que se registra en Odoo, junto al texto del botón: así la vendedora sabe que salió un botón y no solo un texto. */
export const MARCA_BOTON_UBICACION = "[Botón «Enviar ubicación»]";

/** Un número de coordenada: número finito, o texto que sea solo un número decimal. Cualquier otra cosa, null. */
export function coordenada(v: unknown): number | null {
  if (typeof v === "number") return Number.isFinite(v) ? v : null;
  if (typeof v === "string" && /^\s*[-+]?\d{1,3}(?:\.\d+)?\s*$/.test(v)) return Number(v);
  return null;
}

/** Latitud y longitud válidas (finitas y dentro de rango), con 7 decimales (≈1 cm: más no dice nada). null si no sirven. */
export function coordenadasValidas(lat: unknown, lon: unknown): { lat: number; lon: number } | null {
  const a = coordenada(lat);
  const o = coordenada(lon);
  if (a === null || o === null || Math.abs(a) > 90 || Math.abs(o) > 180) return null;
  const r = (n: number) => Math.round(n * 1e7) / 1e7 || 0; // `|| 0`: nunca «-0»
  return { lat: r(a), lon: r(o) };
}

/** Un texto del canal (nombre o dirección del lugar), de una línea, sin caracteres de control y recortado. Vacío o raro: undefined. */
export function textoDeLugar(v: unknown, max: number): string | undefined {
  if (typeof v !== "string") return undefined;
  const limpio = v
    .replace(/[\p{Cc}\p{Cf}]/gu, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, max)
    .trim();
  return limpio || undefined;
}

/** La ubicación de un mensaje, validada; null si las coordenadas no sirven (nunca se adivina una). */
export function crearUbicacion(lat: unknown, lon: unknown, origen: OrigenUbicacion, lugar: { nombre?: unknown; direccion?: unknown } = {}): UbicacionEntrante | null {
  const c = coordenadasValidas(lat, lon);
  if (!c) return null;
  const nombre = textoDeLugar(lugar.nombre, MAX_NOMBRE_LUGAR);
  const direccion = textoDeLugar(lugar.direccion, MAX_DIRECCION);
  return { ...c, origen, ...(nombre ? { nombre_lugar: nombre } : {}), ...(direccion ? { direccion } : {}) };
}
