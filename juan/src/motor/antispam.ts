// Anti-spam determinista: corre ANTES del modelo, así el spam no cuesta ni un token (regla 9).
//   · el mismo mensaje por 3.ª vez entre los últimos 5 → la conversación descansa 1 hora;
//   · tope diario de turnos por persona → una despedida amable y descanso de 12 horas.
// Viene de src/spam.ts del CRM de Baby Caleb, sin base de datos: recibe los textos ya leídos.

import { normalizar } from "../dcasa/texto";

export const DESCANSO_POR_REPETIDO_MS = 60 * 60_000;
export const DESCANSO_POR_TOPE_MS = 12 * 3600_000;
export const TOPE_DIARIO_POR_DEFECTO = 50;
export const MIRAR_ATRAS = 5;
/** El mensaje nuevo + 2 iguales anteriores = 3.ª repetición. */
export const REPETICIONES = 2;

/** Un «ok», un «sí» o un «no» sueltos no cuentan como spam: son respuestas, no insistencia. */
export const LARGO_MINIMO_PARA_SPAM = 4;

export function esRepetido(nuevo: string, anteriores: readonly string[]): boolean {
  const n = normalizar(nuevo);
  if (n.length < LARGO_MINIMO_PARA_SPAM) return false;
  return anteriores.slice(0, MIRAR_ATRAS).filter((t) => normalizar(t) === n).length >= REPETICIONES;
}

export function superaTopeDiario(mensajesEnLasUltimas24h: number, tope: number): boolean {
  return tope > 0 && mensajesEnLasUltimas24h >= tope;
}
