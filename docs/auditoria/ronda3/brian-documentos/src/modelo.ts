/**
 * Lo que ve el MODELO y cómo se valida lo que devuelve.
 *
 * 1. `vistaParaModelo`: nunca el binario ni las 50 000 filas; solo encabezados, muestra,
 *    resumen por columna y las columnas sin rol (lo único que hay que interpretar), todo con
 *    referencias de celda y envuelto como DATO con un delimitador con nonce (no falsificable,
 *    a diferencia del `<<FIN DE LOS DATOS>>` fijo de hoy: conversacion.py:473-477).
 * 2. `ESQUEMA_MAPEO`: salida estructurada (JSON Schema estricto) que el modelo debe llenar.
 * 3. `validarMapeo` / `validarExtraccion`: anti-alucinación. Todo valor que el modelo afirme
 *    debe existir LITERALMENTE en la celda que cita; si no, se descarta y se reporta.
 */
import type { Hoja, Intermedio, Celda } from './xlsx.ts';
import type { Tabla } from './tablas.ts';
import { numero } from './precios.ts';

export function nonce(): string {
  const b = new Uint8Array(9);
  crypto.getRandomValues(b);
  return Array.from(b, (x) => x.toString(36).padStart(2, '0')).join('').slice(0, 12);
}

export function envolverDato(origen: string, contenido: string, n = nonce()): string {
  // el contenido no puede cerrar el bloque: si trae el nonce (imposible salvo fuga), se neutraliza
  const limpio = contenido.split(n).join('[…]');
  return `<dato origen="${origen}" id="${n}">\n${limpio}\n</dato id="${n}">`;
}

const corto = (v: Celda['valor']) => (typeof v === 'string' && v.length > 80 ? `${v.slice(0, 77)}…` : v);

/** Vista compacta de una tabla (tipo SheetCompressor): encabezado + N filas + resumen. */
export function vistaParaModelo(inter: Intermedio, h: Hoja, t: Tabla, filasMuestra = 8): string {
  const lineas: string[] = [];
  lineas.push(`archivo: ${inter.archivo} · hoja: «${h.nombre}» (${h.estado}) · tabla ${t.rango}${t.titulo ? ` · título «${t.titulo}»` : ''}`);
  lineas.push(`filas de datos: ${t.datos.filas}${h.ventana.truncada ? ' (la hoja sigue: pedir más con leer_archivo rango=…)' : ''}`);
  lineas.push('columnas (col | encabezado | rol detectado | confianza):');
  for (const c of t.columnas) lineas.push(`  ${c.col} | ${c.nombre || '(sin encabezado)'} | ${c.rol ?? '¿?'} | ${c.confianza}`);
  lineas.push(`muestra (celda=valor; [img] = imagen en la celda o anclada en la fila):`);
  const imgPorFila = new Map<number, number>();
  for (const im of h.imagenes) { const f = Number(im.celda.replace(/^[A-Z]+/, '')); imgPorFila.set(f, (imgPorFila.get(f) ?? 0) + 1); }
  for (let f = t.datos.desde, k = 0; f <= t.datos.hasta && k < filasMuestra; f++, k++) {
    const partes = t.columnas.map((c) => {
      const cel = h.celdas[`${c.col}${f}`];
      if (!cel) return null;
      if (cel.tipo === 'imagen') return `${c.col}${f}=[img]`;
      if (cel.valor === null) return cel.formula ? `${c.col}${f}=(fórmula sin calcular ${cel.formula})` : null;
      return `${c.col}${f}=${JSON.stringify(corto(cel.valor))}${cel.sospecha_instruccion ? ' ⚠instrucción' : ''}`;
    }).filter(Boolean);
    if (imgPorFila.get(f)) partes.push(`[${imgPorFila.get(f)} img flotante]`);
    lineas.push(`  ${partes.join(' · ')}`);
  }
  return envolverDato(`${inter.archivo}#${h.nombre}!${t.rango}`, lineas.join('\n'));
}

/** Salida estructurada que se pide al modelo cuando hay columnas sin rol. */
export const ESQUEMA_MAPEO = {
  type: 'object',
  additionalProperties: false,
  required: ['columnas', 'preguntas'],
  properties: {
    columnas: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false, required: ['col', 'rol', 'evidencia'],
        properties: {
          col: { type: 'string', pattern: '^[A-Z]{1,3}$' },
          rol: { type: ['string', 'null'], enum: ['codigo', 'descripcion', 'precio', 'precio_contado', 'precio_credito', 'precio_por_tamano', 'combo', 'costo', 'stock', 'medidas', 'categoria', 'foto', 'observaciones', 'color', 'proveedor', 'ignorar', null] },
          evidencia: { type: 'string', description: 'celda(s) que justifican el rol, p. ej. "C5,C6"' },
        },
      },
    },
    preguntas: { type: 'array', items: { type: 'string' }, description: 'dudas para la persona (p. ej. ¿precio con o sin ITBMS?)' },
  },
} as const;

export interface PropuestaMapeo { columnas: Array<{ col: string; rol: string | null; evidencia: string }>; preguntas: string[] }

export function validarMapeo(p: PropuestaMapeo, t: Tabla): { ok: PropuestaMapeo['columnas']; rechazadas: string[] } {
  const cols = new Set(t.columnas.map((c) => c.col));
  const ok: PropuestaMapeo['columnas'] = [], rechazadas: string[] = [];
  for (const c of p.columnas) {
    if (!cols.has(c.col)) rechazadas.push(`${c.col}: columna fuera de la tabla`);
    else if (!/^[A-Z]{1,3}\d+(,[A-Z]{1,3}\d+)*$/.test(c.evidencia.replace(/\s/g, ''))) rechazadas.push(`${c.col}: evidencia sin referencia de celda`);
    else ok.push(c);
  }
  return { ok, rechazadas };
}

/** Un dato extraído por el modelo (de texto libre o de una foto) con su origen. */
export interface DatoExtraido { campo: string; valor: string | number | null; celda?: string; pagina?: number; literal: string }

/**
 * Anti-alucinación: el `literal` debe aparecer en la fuente citada, y si el valor es numérico,
 * debe salir de ese literal. Para fotos (sin celda) se exige confirmación humana siempre.
 */
export function validarExtraccion(d: DatoExtraido, h?: Hoja, textoPagina?: string): { valido: boolean; motivo?: string } {
  let fuente: string | undefined;
  if (d.celda && h) {
    const c = h.celdas[d.celda];
    fuente = c && c.valor !== null ? String(c.valor) : undefined;
    if (fuente === undefined) return { valido: false, motivo: `la celda ${d.celda} está vacía o no se leyó` };
  } else if (textoPagina !== undefined) fuente = textoPagina;
  else return { valido: false, motivo: 'sin fuente verificable (foto): requiere confirmación humana' };
  const norm = (s: string) => s.replace(/\s+/g, ' ').trim().toLowerCase();
  if (!norm(fuente).includes(norm(d.literal))) return { valido: false, motivo: `«${d.literal}» no aparece en la fuente citada` };
  if (typeof d.valor === 'number') {
    const nums = (d.literal.match(/\d[\d.,]*/g) ?? []).map((x) => numero(x));
    if (!nums.some((x) => x !== null && Math.abs(x - (d.valor as number)) < 0.005)) return { valido: false, motivo: `el valor ${d.valor} no sale del literal «${d.literal}»` };
  }
  return { valido: true };
}
