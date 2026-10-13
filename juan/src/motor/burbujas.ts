// Partir la respuesta en burbujas cortas (regla 11: 2 a 4 líneas por burbuja).
// Sale del chunker del CRM de Baby Caleb, con tope por burbuja y sin cortar listas por la mitad.

export interface OpcionesBurbujas {
  /** Máximo de burbujas (el resto se junta en la última). */
  maxBurbujas?: number;
  /** Largo objetivo por burbuja, en caracteres. */
  objetivo?: number;
  /** Líneas máximas por burbuja. */
  maxLineas?: number;
}

const POR_DEFECTO = { maxBurbujas: 4, objetivo: 320, maxLineas: 4 };

/** Parte un párrafo largo en oraciones que quepan en `objetivo`. */
function partirParrafo(p: string, objetivo: number): string[] {
  if (p.length <= objetivo) return [p];
  const oraciones = p.split(/(?<=[.!?…])\s+/).filter(Boolean);
  const salida: string[] = [];
  let actual = "";
  for (const o of oraciones) {
    if (actual && (actual + " " + o).length > objetivo) {
      salida.push(actual);
      actual = o;
    } else {
      actual = actual ? `${actual} ${o}` : o;
    }
  }
  if (actual) salida.push(actual);
  return salida;
}

const lineas = (t: string) => t.split("\n").length;

export function partirEnBurbujas(texto: string, opciones: OpcionesBurbujas = {}): string[] {
  const { maxBurbujas, objetivo, maxLineas } = { ...POR_DEFECTO, ...opciones };
  const limpio = texto.trim();
  if (!limpio) return [];
  const tope = Math.max(1, Math.floor(maxBurbujas));
  if (tope === 1) return [limpio];

  // Un párrafo (separado por línea en blanco) es una idea; una lista se queda junta.
  const piezas = limpio
    .split(/\n\s*\n/)
    .map((p) => p.trim())
    .filter(Boolean)
    .flatMap((p) => (lineas(p) > 1 ? [p] : partirParrafo(p, objetivo)));

  // Se juntan piezas vecinas mientras la burbuja siga corta.
  const burbujas: string[] = [];
  let actual = "";
  for (const pieza of piezas) {
    const junta = actual ? `${actual}\n${pieza}` : pieza;
    if (actual && (junta.length > objetivo || lineas(junta) > maxLineas)) {
      burbujas.push(actual);
      actual = pieza;
    } else {
      actual = junta;
    }
  }
  if (actual) burbujas.push(actual);

  if (burbujas.length <= tope) return burbujas;
  // Demasiadas: lo que sobra se junta en la última, sin perder nada.
  return [...burbujas.slice(0, tope - 1), burbujas.slice(tope - 1).join("\n")];
}
