// Utilidades de texto compartidas por las reglas de D'CASA.

/** Minúsculas y sin acentos (la ñ se conserva: «año» no es «ano»). */
export function sinAcentos(t: string): string {
  return t
    .replace(/ñ/gi, (m) => (m === "ñ" ? "\u0001" : "\u0002"))
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/\u0001/g, "ñ")
    .replace(/\u0002/g, "Ñ")
    .toLowerCase();
}

/** Para comparar frases: sin acentos, sin signos, espacios simples. */
export function normalizar(t: string): string {
  return sinAcentos(t)
    .replace(/[^\p{L}\p{N}\s]/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/** Parte en oraciones conservando cada una tal cual (incluida su puntuación). */
export function oraciones(t: string): string[] {
  return t
    .split(/(?<=[.!?…])\s+|\n+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

/** Escapa un texto para usarlo dentro de una expresión regular. */
export function escaparRegex(t: string): string {
  return t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
