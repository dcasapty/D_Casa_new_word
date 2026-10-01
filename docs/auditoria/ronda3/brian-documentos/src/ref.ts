/** Referencias de celda A1 ↔ (fila, columna) 1-based. */

export function colALetra(c: number): string {
  let s = '';
  while (c > 0) { const m = (c - 1) % 26; s = String.fromCharCode(65 + m) + s; c = Math.floor((c - 1) / 26); }
  return s;
}

export function letraACol(s: string): number {
  let c = 0;
  for (const ch of s.toUpperCase()) c = c * 26 + (ch.charCodeAt(0) - 64);
  return c;
}

export function parsearRef(ref: string): { fila: number; col: number } {
  const m = /^\$?([A-Za-z]{1,3})\$?(\d+)$/.exec(ref.trim());
  if (!m) throw new Error(`referencia inválida: ${ref}`);
  return { col: letraACol(m[1]), fila: Number(m[2]) };
}

export const ref = (fila: number, col: number) => `${colALetra(col)}${fila}`;

export interface Rango { f1: number; c1: number; f2: number; c2: number }

export function parsearRango(r: string): Rango {
  const [a, b] = r.split(':');
  const p = parsearRef(a), q = parsearRef(b ?? a);
  return { f1: Math.min(p.fila, q.fila), c1: Math.min(p.col, q.col), f2: Math.max(p.fila, q.fila), c2: Math.max(p.col, q.col) };
}

export const rangoATexto = (r: Rango) => `${ref(r.f1, r.c1)}:${ref(r.f2, r.c2)}`;

export const dentro = (r: Rango, fila: number, col: number) => fila >= r.f1 && fila <= r.f2 && col >= r.c1 && col <= r.c2;

/** Desplaza las referencias relativas de una fórmula (para fórmulas compartidas). */
export function desplazarFormula(f: string, dFilas: number, dCols: number): string {
  // No toca texto entre comillas ni nombres de hoja entre comillas simples.
  return f.split(/("[^"]*"|'[^']*')/).map((trozo, i) => {
    if (i % 2 === 1) return trozo;
    return trozo.replace(/(\$?)([A-Z]{1,3})(\$?)(\d+)(?![\d(])/g, (m, dc, col, df, fila, off, s) => {
      const antes = s[off - 1];
      if (antes && /[A-Za-z_.]/.test(antes)) return m; // parte de un nombre/función
      const c = dc ? letraACol(col) : letraACol(col) + dCols;
      const r = df ? Number(fila) : Number(fila) + dFilas;
      if (c < 1 || r < 1) return '#REF!';
      return `${dc}${colALetra(c)}${df}${r}`;
    });
  }).join('');
}
