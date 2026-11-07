// Datos que el modelo no necesita ver (regla 5 y Ley 81 de 2019): números de tarjeta, CVV y cédulas
// escritos a mano en un mensaje. Al modelo llegan tapados; Odoo y la vendedora ven el original.
// Las IMÁGENES y documentos del cliente no pasan por aquí: simplemente nunca se le envían al modelo.

const TARJETA = /\b(?:\d[ -]?){12,18}\d\b/g;
const CVV = /\b(cvv2?|cvc2?|c[oó]digo de seguridad)\s*[:=]?\s*\d{3,4}\b/gi;
/** 8-123-4567, PE-12-345, E-8-12345, N-12-345, 8-NT-2-514 ... (provincia/letras-tomo-asiento). */
const CEDULA = /\b(?:PE|E|N|AV|PI|\d{1,2}(?:-?(?:AV|PI|NT))?)-\d{1,4}-\d{3,6}\b/gi;

/** «mi pin es 482913», «clave: 4829», «contraseña 123456»: el PIN de Socios que alguien escribe en el chat. */
const PIN_ESCRITO = /\b(?:pin|clave|contrase(?:ñ|n)a)\b[^\d\n]{0,20}(\d{4,8})\b/gi;

export const MARCA_PIN_ESCRITO = "[PIN retirado]";

/** Los PIN que aparecen escritos en un texto (para borrarlos del historial local después del turno). */
export function pinesEscritos(texto: string): string[] {
  return [...texto.matchAll(PIN_ESCRITO)].map((m) => m[1]);
}

/** El texto con los PIN tapados: es lo que viaja a Odoo (la historia que ven las vendedoras no necesita el PIN del socio). */
export function taparPines(texto: string): string {
  return texto.replace(PIN_ESCRITO, (m, pin: string) => m.replace(pin, MARCA_PIN_ESCRITO));
}

export const MARCA_TARJETA = "[número de tarjeta retirado]";
export const MARCA_CEDULA = "[cédula retirada]";

export function enmascararSensibles(texto: string): string {
  return texto
    .replace(CVV, "[código de seguridad retirado]")
    .replace(TARJETA, MARCA_TARJETA)
    .replace(CEDULA, (m) => (/^\d{1,2}-\d{2}-\d{3,6}$/.test(m) && esFecha(m) ? m : MARCA_CEDULA));
}

/** «12-10-2026» no es una cédula: el segundo grupo de una cédula tiene 3 o 4 cifras, pero «12-10-26» sí podría confundirse. */
function esFecha(m: string): boolean {
  const [d, mes, a] = m.split("-").map(Number);
  return d >= 1 && d <= 31 && mes >= 1 && mes <= 12 && (a >= 1900 || a <= 99);
}

/**
 * Caracteres invisibles de formato (\p{Cf}: espacio de ancho cero, unión de palabras, guion suave, controles bidi, etiquetas
 * Unicode…): no se ven, pero separan letras para que un filtro no reconozca una palabra, o esconden instrucciones. Se quitan del texto
 * del cliente. El ZWJ (U+200D) se queda: une los emojis compuestos (👨‍👩‍👧).
 */
const INVISIBLES = /(?!\u200d)\p{Cf}/gu;
/** Todo lo que el modelo puede leer como «[» o como «<»/«>». */
const CORCHETES = /[\[\uff3b\u3010\u3014\u3016\u3018\u301a\u2045\ufe5d\u298b\u298d\u298f]/gu;
const ANGULO_ABRE = /[<\uff1c\ufe64\u2329\u3008]/g;
const ANGULO_CIERRA = /[>\uff1e\ufe65\u232a\u3009]/g;
/** Letras de otros alfabetos (y números) que se ven iguales a las latinas de las marcas. */
const PARECIDAS: Record<string, string> = {
  а: "a", е: "e", о: "o", р: "p", с: "c", у: "y", х: "x", і: "i", ј: "j", ѕ: "s", ԁ: "d", ӏ: "l", һ: "h", ν: "v", ο: "o", α: "a",
  ε: "e", ι: "i", τ: "t", κ: "k", ρ: "p", η: "n", "0": "o", "1": "l", "3": "e", "4": "a", "5": "s", "7": "t", "|": "l", ı: "i", ł: "l",
};
/**
 * Las marcas que el historial usa para hablar con autoridad («[Vendedora] …», «[El cliente responde …]», «[Sistema] …»), también con
 * unas pocas letras delante («[1) Vendedora]», «[Nota: el cliente…»): confundir un corchete de verdad con una marca solo lo cambia por «⟦».
 */
const MARCA_DE_CONFIANZA = /^[a-z]{0,12}?(?:e[li]c[li][li]ente|vendedora|asistente|sistema)/;

/** Cómo «se lee» lo que sigue a un corchete: sin invisibles, sin acentos, letras de ancho completo y parecidas a latinas, solo letras. */
function esqueleto(trozo: string): string {
  const base = trozo.normalize("NFKC").replace(INVISIBLES, "").toLowerCase().normalize("NFD").replace(/\p{M}/gu, "");
  return [...base].map((ch) => PARECIDAS[ch] ?? ch).join("").replace(/[^a-z]/g, "");
}

/**
 * Lo que el cliente escribe viaja al modelo como DATOS. Para que no pueda cerrar una etiqueta de nuestro
 * prompt ni abrir otra («</fuentes_de_verdad> Ahora eres...»), los ángulos se cambian por comillas angulares.
 */
export function neutralizarEtiquetas(texto: string): string {
  // También los corchetes que el historial usa como marcas de confianza («[Vendedora] …», «[El cliente adjuntó …]»):
  // el cliente no puede escribir uno y hacerlo pasar por la voz de una vendedora. No basta con mirar el ASCII (revisión 2026-11-07):
  // un espacio invisible, un espacio duro, un guion suave, un corchete de ancho completo o una «Е» cirílica se leen igual. Por eso lo
  // que sigue a cada corchete se compara «como se lee» (esqueleto); el texto que ve el modelo solo pierde los invisibles.
  const limpio = texto.replace(INVISIBLES, "").replace(ANGULO_ABRE, "‹").replace(ANGULO_CIERRA, "›");
  return limpio.replace(CORCHETES, (corchete, pos: number) => (MARCA_DE_CONFIANZA.test(esqueleto(limpio.slice(pos + corchete.length, pos + corchete.length + 60))) ? "⟦" : corchete));
}

/** Un nombre de perfil puede traer instrucciones: se deja corto y sin saltos ni etiquetas. */
export function nombreSeguro(nombre: string | undefined): string {
  return neutralizarEtiquetas((nombre ?? "").replace(/[\r\n\t]+/g, " ").trim()).slice(0, 40);
}

/** Todo lo que se le muestra al modelo del texto de un cliente. */
export function textoParaElModelo(texto: string): string {
  return neutralizarEtiquetas(enmascararSensibles(texto));
}
