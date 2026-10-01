/**
 * Normalización DETERMINISTA de precios escritos como texto.
 *
 * Regla de CLAUDE.md: no inventar cifras. Cada precio devuelto conserva el `literal` del que
 * sale; lo que no se entiende queda en `sin_interpretar` (y va al modelo o a una persona),
 * nunca se rellena. «Queen $—» → tamaño presente con precio null + alerta.
 */

export interface Precio {
  valor: number | null;      // null = el texto nombra el precio pero no lo da («$—»)
  moneda: 'USD' | 'PAB' | null;
  literal: string;
  etiqueta?: string;         // tamaño o variante: Twin, Full, Queen, King, «El par (-10%)», «Combo…»
  calificador?: 'desde' | 'hasta' | 'aprox';
}

export interface PreciosTexto {
  precios: Precio[];
  sin_interpretar: string;   // resto del texto que no es precio ni etiqueta
  alertas: string[];
}

const TAMANOS = ['twin', 'full', 'queen', 'king', 'individual', 'semidoble', 'doble', 'matrimonial', 'sencilla', 'imperial', 'california king', 'super king'];

/** Interpreta «1,329.99», «1.329,99», «149,99», «149.99», «1329». */
export function numero(s: string): number | null {
  let t = s.replace(/\s/g, '');
  if (!/^\d[\d.,]*$/.test(t)) return null;
  const ultPunto = t.lastIndexOf('.'), ultComa = t.lastIndexOf(',');
  if (ultPunto >= 0 && ultComa >= 0) {
    // el último separador es el decimal
    t = ultComa > ultPunto ? t.replace(/\./g, '').replace(',', '.') : t.replace(/,/g, '');
  } else if (ultComa >= 0) {
    // solo comas: decimal si hay 1-2 dígitos detrás de la última y es la única
    const tras = t.length - ultComa - 1;
    t = (t.split(',').length === 2 && tras > 0 && tras <= 2) ? t.replace(',', '.') : t.replace(/,/g, '');
  } else if (ultPunto >= 0) {
    const tras = t.length - ultPunto - 1;
    if (t.split('.').length > 2 || tras === 3) t = t.replace(/\./g, ''); // 1.329 = mil trescientos
  }
  const v = Number(t);
  return Number.isFinite(v) ? v : null;
}

// moneda + número (o guion de «sin precio»)
const RE_PRECIO = /(US\$|USD|B\/\.|PAB|\$)\s*(\d[\d.,]*\d|\d|[—–-]+)|(\d[\d.,]*\d|\d)\s*(USD|B\/\.|balboas?|dólares?)/giu;

export function preciosEnTexto(texto: string): PreciosTexto {
  const precios: Precio[] = [];
  const alertas: string[] = [];
  let resto = texto;
  const marcas: Array<[number, number]> = [];
  let m: RegExpExecArray | null;
  RE_PRECIO.lastIndex = 0;
  while ((m = RE_PRECIO.exec(texto))) {
    const simbolo = (m[1] ?? m[4] ?? '').toUpperCase();
    const cifra = m[2] ?? m[3] ?? '';
    const moneda: Precio['moneda'] = /B\/\.|PAB|BALBOA/.test(simbolo) ? 'PAB' : 'USD';
    const valor = /^[—–-]+$/.test(cifra) ? null : numero(cifra);
    // etiqueta: lo que hay entre el precio anterior (o separador) y este precio
    const ini = marcas.length ? marcas[marcas.length - 1][1] : 0;
    let etiqueta = texto.slice(ini, m.index).replace(/^[\s·•|/;,:]+|[\s·•|/;,:]+$/g, '').trim();
    let calificador: Precio['calificador'];
    const cal = /\b(desde|a partir de|hasta|aprox\.?|aproximadamente)\b\s*$/i.exec(etiqueta);
    if (cal) {
      const c = cal[1].toLowerCase();
      calificador = c.startsWith('hasta') ? 'hasta' : c.startsWith('aprox') ? 'aprox' : 'desde';
      etiqueta = etiqueta.slice(0, cal.index).trim();
    }
    const p: Precio = { valor, moneda, literal: m[0] };
    if (etiqueta) p.etiqueta = etiqueta;
    if (calificador) p.calificador = calificador;
    precios.push(p);
    marcas.push([m.index, m.index + m[0].length]);
    if (valor === null) alertas.push(`precio vacío para «${etiqueta || '?'}» (${m[0]})`);
    else if (valor === 0) alertas.push(`precio cero (¿vacío?) para «${etiqueta || '?'}» (${m[0]})`);
  }
  for (const [a, b] of marcas.slice().reverse()) resto = resto.slice(0, a) + ' ' + resto.slice(b);
  // quitar etiquetas usadas
  for (const p of precios) if (p.etiqueta) resto = resto.replace(p.etiqueta, ' ');
  resto = resto.replace(/(desde|a partir de|hasta|aprox\.?)/gi, ' ').replace(/[\s·•|/;,:]+/g, ' ').trim();
  // alerta: tamaños con precios no crecientes
  const tam = precios.filter((p) => p.etiqueta && TAMANOS.includes(p.etiqueta.toLowerCase()) && p.valor !== null);
  for (let i = 1; i < tam.length; i++) {
    const a = TAMANOS.indexOf(tam[i - 1].etiqueta!.toLowerCase()), b = TAMANOS.indexOf(tam[i].etiqueta!.toLowerCase());
    if (a < 4 && b < 4 && b > a && tam[i].valor! < tam[i - 1].valor!) {
      alertas.push(`precio no creciente: ${tam[i - 1].etiqueta} ${tam[i - 1].valor} > ${tam[i].etiqueta} ${tam[i].valor}`);
    }
  }
  return { precios, sin_interpretar: resto, alertas };
}
