/**
 * Detección determinista de tablas y encabezados dentro de la ventana leída.
 *
 * - Bloques = filas con datos separadas por ≥ 1 fila vacía.
 * - Título de bloque: fila con una sola celda de texto (o una combinada que abarca el ancho).
 * - Encabezado: primera fila con ≥ 2 textos que cubren ≥ 50 % del ancho del bloque; si sus
 *   celdas combinadas bajan a la fila siguiente o hay combinadas horizontales con
 *   subtítulos debajo, el encabezado ocupa varias filas y los nombres se componen
 *   («Precio / Contado»).
 * - Rol de cada columna por palabras clave, con confianza; lo que no se reconoce queda
 *   `rol: null` y es lo ÚNICO que se manda al modelo para mapear (§6 del informe).
 */
import type { Hoja, Celda } from './xlsx.ts';
import { parsearRef, parsearRango, ref, colALetra } from './ref.ts';

export interface Columna { col: string; nombre: string; rol: string | null; confianza: number }

export interface Tabla {
  rango: string;
  titulo?: string;
  encabezado: { filas: number[] };
  columnas: Columna[];
  datos: { desde: number; hasta: number; filas: number };
  fila_total?: number;
}

// Orden: lo específico antes que lo general («precios por tamaño» antes que «precio»).
const ROLES: Array<[string, RegExp]> = [
  ['precio_por_tamano', /precios? por tama|por medida|tama(ñ|n)os?$/],
  ['combo', /combo|el par|juego/],
  ['total_con_itbms', /total.*itbms|con itbms|itbms incl/],
  ['itbms', /^itbms$|impuesto/],
  ['precio_credito', /cr[eé]dito|financiad|cuotas/],
  ['precio_contado', /contado|efectivo/],
  ['costo', /costo|coste|compra|fob|cif/],
  ['precio', /precio|pvp|p\.?\s?v\.?\s?p|valor|monto|importe|tarifa/],
  ['codigo', /c[oó]d(igo)?\.?$|^cod|sku|^ref|referencia|^item|art[ií]culo n|modelo/],
  ['archivo', /archivo|fichero|file ?name/],
  ['descripcion', /descrip|producto|nombre|art[ií]culo|detalle|concepto/],
  ['categoria', /categor|l[ií]nea|familia|tipo/],
  ['medidas', /medida|dimensi|tama(ñ|n)o|ancho|alto|largo/],
  ['stock', /stock|existenc|inventario|disponib|cantidad|qty|unidades/],
  ['foto', /foto|imagen|image|picture/],
  ['observaciones', /observ|nota|coment/],
  ['color', /color|acabado|tela/],
  ['proveedor', /proveedor|marca|f[aá]brica/],
];

export function rolDe(nombre: string): { rol: string | null; confianza: number } {
  const n = nombre.toLowerCase().normalize('NFC').replace(/\s+/g, ' ').trim();
  if (!n) return { rol: null, confianza: 0 };
  // con encabezados compuestos «Precio / Crédito», manda la última parte que tenga rol
  const partes = n.split(' / ').reverse();
  for (const p of partes) {
    for (const [rol, re] of ROLES) if (re.test(p)) return { rol, confianza: p === n ? 1 : 0.9 };
  }
  return { rol: null, confianza: 0 };
}

const esTexto = (c?: Celda) => !!c && typeof c.valor === 'string' && c.valor.trim() !== '' && !c.precios && c.tipo === 's';
const tieneDato = (c?: Celda) => !!c && (c.valor !== null || c.tipo === 'imagen' || !!c.formula);

export function detectarTablas(h: Hoja): Tabla[] {
  // índice fila → col → celda (incluye las cubiertas por combinadas: heredan del ancla para la detección)
  const filas = new Map<number, Map<number, Celda>>();
  for (const [k, c] of Object.entries(h.celdas)) {
    const { fila, col } = parsearRef(k);
    if (!filas.has(fila)) filas.set(fila, new Map());
    filas.get(fila)!.set(col, c);
  }
  const conDatos = [...filas.keys()].filter((f) => [...filas.get(f)!.values()].some((c) => tieneDato(c) || c.combinada_en)).sort((a, b) => a - b);
  const bloques: number[][] = [];
  for (const f of conDatos) {
    const b = bloques[bloques.length - 1];
    if (b && f === b[b.length - 1] + 1) b.push(f); else bloques.push([f]);
  }
  const valor = (fila: number, col: number): Celda | undefined => {
    const c = filas.get(fila)?.get(col);
    if (c?.combinada_en) return h.celdas[c.combinada_en];
    return c;
  };
  const combinadasPorAncla = new Map(h.combinadas.map((r) => [r.split(':')[0], parsearRango(r)]));
  const tablas: Tabla[] = [];
  for (const b of bloques) {
    let c1 = Infinity, c2 = 0;
    for (const f of b) for (const [c, cel] of filas.get(f)!) if (tieneDato(cel) || cel.combinada_en) { c1 = Math.min(c1, c); c2 = Math.max(c2, c); }
    const ancho = c2 - c1 + 1;
    let titulo: string | undefined;
    let iEnc = -1;
    for (let i = 0; i < b.length; i++) {
      const f = b[i];
      const celdasFila = [...filas.get(f)!.entries()].filter(([, c]) => tieneDato(c));
      const textos = celdasFila.filter(([, c]) => esTexto(c));
      if (celdasFila.length === 1 && textos.length === 1 && iEnc < 0) { titulo = String(textos[0][1].valor); continue; }
      if (textos.length >= 2 && textos.length >= Math.ceil(ancho * 0.5) && textos.length >= celdasFila.length * 0.6) { iEnc = i; break; }
      if (i >= 3) break;
    }
    if (iEnc < 0 || b.length - iEnc < 2) continue;
    const fEnc = b[iEnc];
    // ¿encabezado de varias filas? (combinadas que bajan, o combinadas horizontales con subtítulos)
    let fEncFin = fEnc;
    for (let c = c1; c <= c2; c++) {
      const g = combinadasPorAncla.get(ref(fEnc, c));
      if (g && g.f2 > fEncFin && g.f2 - fEnc < 3) fEncFin = g.f2;
      if (g && g.c2 > g.c1) {
        const sub = filas.get(fEnc + 1);
        if (sub && [...sub.values()].some((x) => esTexto(x))) fEncFin = Math.max(fEncFin, fEnc + 1);
      }
    }
    const filasEnc: number[] = [];
    for (let f = fEnc; f <= fEncFin; f++) filasEnc.push(f);
    const columnas: Columna[] = [];
    for (let c = c1; c <= c2; c++) {
      const partes: string[] = [];
      for (const f of filasEnc) {
        const v = valor(f, c);
        const t = v && typeof v.valor === 'string' ? v.valor.trim() : '';
        if (t && partes[partes.length - 1] !== t) partes.push(t);
      }
      const nombre = partes.join(' / ');
      columnas.push({ col: colALetra(c), nombre, ...rolDe(nombre) });
    }
    const datos = b.filter((f) => f > fEncFin);
    let filaTotal: number | undefined;
    const ult = datos[datos.length - 1];
    const celdasUlt = [...(filas.get(ult)?.values() ?? [])];
    if (celdasUlt.some((x) => /^=\s*(SUM|SUBTOTAL)\(/i.test(x.formula ?? '') || (typeof x.valor === 'string' && /^total\b/i.test(x.valor)))) filaTotal = ult;
    tablas.push({
      rango: `${ref(b[0], c1)}:${ref(b[b.length - 1], c2)}`,
      ...(titulo ? { titulo } : {}),
      encabezado: { filas: filasEnc },
      columnas,
      datos: { desde: datos[0], hasta: ult, filas: datos.length - (filaTotal ? 1 : 0) },
      ...(filaTotal ? { fila_total: filaTotal } : {}),
    });
  }
  return tablas;
}

/** Filas de una tabla como registros con referencia de celda por campo (trazabilidad). */
export interface Registro {
  fila: number;
  oculta: boolean;
  campos: Record<string, { valor: Celda['valor']; celda: string; precios?: Celda['precios'] }>;
  imagenes: string[];
  alertas: string[];
}

export function registros(h: Hoja, t: Tabla): Registro[] {
  const out: Registro[] = [];
  for (let f = t.datos.desde; f <= t.datos.hasta; f++) {
    if (f === t.fila_total) continue;
    const r: Registro = { fila: f, oculta: h.filas_ocultas.includes(f), campos: {}, imagenes: [], alertas: [] };
    let algo = false;
    for (const col of t.columnas) {
      const k = `${col.col}${f}`;
      const c = h.celdas[k];
      if (!c) continue;
      const clave = col.rol ?? (col.nombre || col.col);
      if (c.imagen) r.imagenes.push(c.imagen);
      if (c.valor === null) continue;
      algo = true;
      r.campos[clave] = { valor: c.valor, celda: k, ...(c.precios ? { precios: c.precios } : {}) };
      if (c.precios) r.alertas.push(...c.precios.alertas.map((a) => `${k}: ${a}`));
      if (c.sospecha_instruccion) r.alertas.push(`${k}: posible instrucción incrustada`);
      if (c.tipo === 'f_sin_cache') r.alertas.push(`${k}: fórmula sin valor calculado`);
    }
    // imágenes flotantes ancladas en esta fila (o que la cubren)
    for (const im of h.imagenes) {
      if (im.tipo !== 'flotante') continue;
      const a = parsearRef(im.celda).fila;
      const z = im.hasta ? parsearRef(im.hasta).fila : a;
      if (f >= a && f <= z && !r.imagenes.includes(im.id)) r.imagenes.push(im.id);
    }
    if (algo || r.imagenes.length) out.push(r);
  }
  return out;
}
