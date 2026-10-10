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
 * Lo que el cliente escribe viaja al modelo como DATOS. Para que no pueda cerrar una etiqueta de nuestro
 * prompt ni abrir otra («</fuentes_de_verdad> Ahora eres...»), los ángulos se cambian por comillas angulares.
 */
export function neutralizarEtiquetas(texto: string): string {
  // También los corchetes que el historial usa como marcas de confianza («[Vendedora] …», «[El cliente adjuntó …]»):
  // el cliente no puede escribir uno y hacerlo pasar por la voz de una vendedora.
  return texto.replace(/</g, "‹").replace(/>/g, "›").replace(/\[(\s*(?:vendedora|el cliente|asistente|sistema)\b)/gi, "⟦$1");
}

/** Un nombre de perfil puede traer instrucciones: se deja corto y sin saltos ni etiquetas. */
export function nombreSeguro(nombre: string | undefined): string {
  return neutralizarEtiquetas((nombre ?? "").replace(/[\r\n\t]+/g, " ").trim()).slice(0, 40);
}

/** Todo lo que se le muestra al modelo del texto de un cliente. */
export function textoParaElModelo(texto: string): string {
  return neutralizarEtiquetas(enmascararSensibles(texto));
}
