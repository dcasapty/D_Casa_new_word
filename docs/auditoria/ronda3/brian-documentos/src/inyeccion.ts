/**
 * Señales de inyección de instrucciones en DATOS (celdas, comentarios, texto alternativo de
 * imágenes, texto de PDF/Word, texto que el modelo transcribe de una foto).
 *
 * No es un filtro de seguridad (un atacante puede evadir cualquier lista): es una SEÑAL para
 * (1) marcar la celda con `sospecha_instruccion`, (2) mostrarla en la vista previa y
 * (3) que `aplicar_importacion` exija confirmación reforzada. La defensa real es estructural:
 * el modelo nunca obtiene herramientas de escritura por leer un archivo (ver informe §7).
 */
const PATRONES: RegExp[] = [
  /\b(ignora|olvida|omite|desobedece)\b.{0,40}\b(instrucci|regla|indicaci|anterior)/i,
  /\b(ignore|disregard|forget)\b.{0,40}\b(instruction|previous|above|rules)/i,
  /\b(system prompt|prompt del sistema|mensaje del sistema|developer message)\b/i,
  /\b(eres ahora|act[uú]a como|you are now|new instructions|nuevas instrucciones)\b/i,
  /\b(sin (pedir )?confirma|without confirm|no (le )?preguntes|no avises)\b/i,
  /\b(aplicar_importacion|deshacer_importacion|crear_producto|actualizar_producto|borrar|elimina(r)? todo)\b/i,
  /<<\s*(FIN|DATOS)|<\/?(system|assistant|tool_use|function_call)>/i,
  /\b(env[ií]a|manda|send)\b.{0,40}\b(contrase|password|token|api key|clave)/i,
];

export function sospechaInstruccion(texto: string | null | undefined): boolean {
  if (!texto || texto.length < 12) return false;
  return PATRONES.some((p) => p.test(texto));
}
