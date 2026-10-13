// @ts-check
// Partición de mensajes en «burbujas».
//
// Juan ya manda el texto en burbujas cortas (2–4 líneas, docs/JUAN.md). Esto es
// la red de seguridad del puente: si una burbuja llega enorme, se parte donde
// una persona partiría (párrafo, línea, frase, palabra) y nunca a la mitad de
// una palabra salvo que no quede otra (una URL larguísima).

/** Máximo de caracteres por burbuja. WhatsApp admite mucho más; una pared de texto no. */
export const MAX_BURBUJA = 1200;

/** Máximo del pie de una foto o documento (WhatsApp recorta alrededor de 1024). */
export const MAX_PIE = 1000;

/** Máximo de burbujas de texto por petición: frena a un bucle desbocado. */
export const MAX_BURBUJAS = 10;

/**
 * Quita lo que no debe viajar a WhatsApp: saltos de línea de Windows, caracteres
 * de control y espacios al borde. Conserva saltos de línea y tabuladores.
 * @param {unknown} texto
 */
export function limpiarTexto(texto) {
  return String(texto ?? "")
    .replace(/\r\n?/g, "\n")
    // eslint-disable-next-line no-control-regex
    .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/g, "")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

/**
 * Niveles de corte, del más natural al más brusco. `union` es lo que se pone
 * al volver a juntar trozos dentro de una misma burbuja.
 */
const NIVELES = [
  { corte: /\n{2,}/, union: "\n\n" }, // párrafos
  { corte: /\n/, union: "\n" }, // líneas
  { corte: /(?<=[.!?…])\s+/, union: " " }, // frases
  { corte: /\s+/, union: " " }, // palabras
];

/**
 * Corte duro por longitud, sin partir un par sustituto (emoji, letras raras).
 * @param {string} texto
 * @param {number} max
 */
function cortarDuro(texto, max) {
  const piezas = [];
  let resto = texto;
  while (resto.length > max) {
    let corte = max;
    const anterior = resto.charCodeAt(corte - 1);
    // 0xD800–0xDBFF: mitad alta de un par sustituto; no se corta entre las dos mitades.
    if (anterior >= 0xd800 && anterior <= 0xdbff) corte -= 1;
    piezas.push(resto.slice(0, corte));
    resto = resto.slice(corte);
  }
  if (resto) piezas.push(resto);
  return piezas;
}

/**
 * @param {string} texto
 * @param {number} nivel
 * @param {number} max
 * @returns {string[]}
 */
function dividir(texto, nivel, max) {
  if (texto.length <= max) return [texto];
  if (nivel >= NIVELES.length) return cortarDuro(texto, max);
  const { corte, union } = NIVELES[nivel];
  const trozos = texto.split(corte).map((t) => t.trim()).filter(Boolean);
  if (trozos.length <= 1) return dividir(texto, nivel + 1, max);

  /** @type {string[]} */
  const burbujas = [];
  let actual = "";
  for (const trozo of trozos) {
    const subtrozos = trozo.length > max ? dividir(trozo, nivel + 1, max) : [trozo];
    for (const sub of subtrozos) {
      if (!actual) actual = sub;
      else if (actual.length + union.length + sub.length <= max) actual += union + sub;
      else {
        burbujas.push(actual);
        actual = sub;
      }
    }
  }
  if (actual) burbujas.push(actual);
  return burbujas;
}

/**
 * Parte un texto en burbujas de hasta `max` caracteres, en orden y sin perder
 * nada (salvo los espacios donde se corta). Un texto vacío da `[]`.
 *
 * @param {unknown} texto
 * @param {number} [max]
 * @returns {string[]}
 */
export function partirTexto(texto, max = MAX_BURBUJA) {
  if (!Number.isInteger(max) || max < 20) throw new Error("max de la burbuja inválido (mínimo 20)");
  const limpio = limpiarTexto(texto);
  if (!limpio) return [];
  return dividir(limpio, 0, max);
}

/**
 * Prepara la lista de burbujas de una petición: parte las demasiado largas,
 * descarta las vacías y respeta el tope de burbujas.
 *
 * @param {unknown} chunks
 * @param {{ max?: number, maxBurbujas?: number }} [opciones]
 * @returns {{ ok: true, burbujas: string[] } | { ok: false, motivo: string }}
 */
export function prepararBurbujas(chunks, { max = MAX_BURBUJA, maxBurbujas = MAX_BURBUJAS } = {}) {
  if (!Array.isArray(chunks)) return { ok: false, motivo: "chunks debe ser una lista de textos" };
  /** @type {string[]} */
  const burbujas = [];
  for (const chunk of chunks) {
    if (typeof chunk !== "string") return { ok: false, motivo: "cada chunk debe ser un texto" };
    burbujas.push(...partirTexto(chunk, max));
  }
  if (burbujas.length > maxBurbujas) {
    return { ok: false, motivo: `demasiadas burbujas (${burbujas.length}); el máximo es ${maxBurbujas} por petición` };
  }
  return { ok: true, burbujas };
}

/**
 * El pie de una imagen o documento. Si pasa del tope, el pie se queda con la
 * primera parte y lo que sobra sale como burbujas de texto a continuación (no
 * se recorta en silencio ni se rechaza la respuesta entera).
 *
 * @param {unknown} pie
 * @returns {{ pie: string | undefined, resto: string[] }}
 */
export function partirPie(pie) {
  const limpio = limpiarTexto(pie);
  if (!limpio) return { pie: undefined, resto: [] };
  const partes = partirTexto(limpio, MAX_PIE);
  return { pie: partes[0], resto: partes.slice(1) };
}
