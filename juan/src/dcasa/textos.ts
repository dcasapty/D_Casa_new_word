// Los pocos textos que el SISTEMA (no el modelo) le dice al cliente. Voz de la marca: tuteo, breve,
// sin emojis. Si Odoo manda su propio texto (p. ej. el de `pasar_a_vendedora`), ese gana.

import type { Horario } from "../config";

export const TEXTO_TOPE_DIARIO =
  "Gracias por escribirnos tanto. Por hoy ya te acompañé un buen rato; mañana seguimos con gusto. " +
  "Si prefieres, escríbeme *persona* y te atiende una vendedora.";

export const TEXTO_FALLO_TECNICO = "Ahorita no puedo responderte yo, pero ya avisé: una vendedora te atiende por aquí en cuanto pueda.";

export const TEXTO_ARCHIVO_RECIBIDO = "Recibí tu archivo. Una vendedora lo revisa y te confirma por aquí.";

/** «08:00» → «8:00 a. m.»; «17:00» → «5:00 p. m.» */
export function horaLegible(hhmm: string): string {
  const [h, m] = hhmm.split(":").map(Number);
  const sufijo = h >= 12 ? "p. m." : "a. m.";
  const h12 = h % 12 === 0 ? 12 : h % 12;
  return `${h12}:${String(m).padStart(2, "0")} ${sufijo}`;
}

/** Solo si `pasar_a_vendedora` no trajo texto (o Odoo no contestó). */
export function textoPasoAVendedora(dentroDeHorario: boolean, horario: Horario): string {
  return dentroDeHorario
    ? "Listo, ya le pasé tu consulta a una vendedora. Te escribe por aquí en un momento."
    : `Listo, dejé tu consulta para una vendedora. Te escribe por aquí cuando abramos, a partir de las ${horaLegible(horario.inicio)}.`;
}
