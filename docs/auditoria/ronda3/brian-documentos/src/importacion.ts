/**
 * Vista previa e importación IDEMPOTENTE por lotes (lado puro, sin Odoo).
 *
 * El plan lo aplica después el servidor (Odoo o D1) en lotes con savepoint; aquí se calcula
 * qué se haría, con trazabilidad celda→campo y la llave de idempotencia
 * `sha256(archivo):hoja:fila`. Reglas de CLAUDE.md: no inventar precios (sin precio → se omite
 * el campo y se alerta), `modo_itbms` OBLIGATORIO y explícito. Para D'CASA el dueño ya decidió
 * (bitácora, 2026-10-01): los precios del Excel son SIN ITBMS → `mas_itbms`; el parámetro se
 * mantiene porque un proveedor puede mandar listas con impuesto incluido.
 */
import type { Hoja, Intermedio } from './xlsx.ts';
import type { Tabla } from './tablas.ts';
import { registros } from './tablas.ts';

export type ModoItbms = 'incluido' | 'mas_itbms';

export interface Existente { codigo: string; precio: number | null; nombre: string; id: number }

export interface Linea {
  llave: string;                       // sha256:hoja:fila  (idempotencia)
  fila: number;
  accion: 'crear' | 'actualizar' | 'sin_cambios' | 'omitir';
  codigo: string | null;
  valores: Record<string, unknown>;
  antes?: Record<string, unknown>;     // para revertir
  origen: Record<string, string>;      // campo → celda
  imagenes: string[];
  alertas: string[];
  requiere_revision: boolean;
}

export interface Plan {
  archivo: string; sha256: string | null; hoja: string; tabla: string; modo_itbms: ModoItbms;
  lineas: Linea[];
  lotes: string[][];                   // llaves por lote
  resumen: Record<Linea['accion'] | 'con_alertas', number>;
}

export function planificar(inter: Intermedio, h: Hoja, t: Tabla, existentes: Map<string, Existente>, modo: ModoItbms, tamLote = 50): Plan {
  if (modo !== 'incluido' && modo !== 'mas_itbms') throw new Error('modo_itbms es obligatorio (incluido | mas_itbms)');
  const regs = registros(h, t);
  const vistos = new Map<string, number>();
  const lineas: Linea[] = [];
  for (const r of regs) {
    const llave = `${inter.sha256 ?? inter.archivo}:${h.nombre}:${r.fila}`;
    const codigoRaw = r.campos.codigo?.valor;
    const codigo = typeof codigoRaw === 'string' ? codigoRaw.trim().toUpperCase() : codigoRaw != null ? String(codigoRaw) : null;
    const alertas = [...r.alertas];
    const valores: Record<string, unknown> = {};
    const origen: Record<string, string> = {};
    for (const [campo, v] of Object.entries(r.campos)) { origen[campo] = v.celda; }
    if (r.campos.descripcion) valores.nombre = String(r.campos.descripcion.valor).trim();
    const p = r.campos.precio ?? r.campos.precio_contado;
    if (p && typeof p.valor === 'number') valores.precio = p.valor;
    else if (p?.precios?.precios.length === 1 && p.precios.precios[0].valor !== null) valores.precio = p.precios.precios[0].valor;
    else if (p?.precios && p.precios.precios.length > 1) {
      valores.variantes = Object.fromEntries(p.precios.precios.map((x) => [x.etiqueta ?? x.literal, x.valor]));
      alertas.push(`${p.celda}: varios precios en una celda → variantes (revisar)`);
    } else alertas.push('sin precio: no se inventa (queda sin precio)');
    if (r.campos.precio_por_tamano?.precios) valores.variantes = Object.fromEntries(r.campos.precio_por_tamano.precios.precios.map((x) => [x.etiqueta ?? x.literal, x.valor]));
    if (valores.precio !== undefined) valores.precio_modo_itbms = modo;
    if (r.campos.costo) alertas.push('trae COSTO: dato sensible, solo gerente');
    let accion: Linea['accion'] = 'crear';
    let antes: Record<string, unknown> | undefined;
    if (!codigo) { accion = 'omitir'; alertas.push('sin código: no se puede casar con el catálogo'); }
    else {
      if (vistos.has(codigo)) { alertas.push(`código repetido (también en fila ${vistos.get(codigo)})`); accion = 'omitir'; }
      vistos.set(codigo, r.fila);
      const e = existentes.get(codigo);
      if (accion !== 'omitir' && e) {
        const cambia = (valores.precio !== undefined && valores.precio !== e.precio) || (valores.nombre !== undefined && valores.nombre !== e.nombre);
        accion = cambia ? 'actualizar' : 'sin_cambios';
        antes = { precio: e.precio, nombre: e.nombre, id: e.id };
        if (typeof valores.precio === 'number' && e.precio && Math.abs(valores.precio - e.precio) / e.precio > 0.3) alertas.push(`cambio de precio > 30 % (${e.precio} → ${valores.precio}): segunda confirmación`);
      }
    }
    if (r.oculta) alertas.push('fila OCULTA en Excel (¿descontinuado?)');
    lineas.push({ llave, fila: r.fila, accion, codigo, valores, ...(antes ? { antes } : {}), origen, imagenes: r.imagenes, alertas, requiere_revision: alertas.length > 0 });
  }
  const aplicables = lineas.filter((l) => l.accion === 'crear' || l.accion === 'actualizar');
  const lotes: string[][] = [];
  for (let i = 0; i < aplicables.length; i += tamLote) lotes.push(aplicables.slice(i, i + tamLote).map((l) => l.llave));
  const resumen = { crear: 0, actualizar: 0, sin_cambios: 0, omitir: 0, con_alertas: 0 };
  for (const l of lineas) { resumen[l.accion]++; if (l.requiere_revision) resumen.con_alertas++; }
  return { archivo: inter.archivo, sha256: inter.sha256, hoja: h.nombre, tabla: t.rango, modo_itbms: modo, lineas, lotes, resumen };
}

/**
 * Simulación de aplicar en lotes con registro de idempotencia y reversión (el registro real
 * es `brian.importacion.linea` en Odoo o una tabla D1; aquí, un Map).
 */
export interface Registro { aplicado: Map<string, { id: number; antes?: Record<string, unknown> }> }

export function aplicar(plan: Plan, reg: Registro, escribir: (l: Linea) => number, soloLotes?: number[]): { aplicadas: number; saltadas: number } {
  let aplicadas = 0, saltadas = 0;
  const porLlave = new Map(plan.lineas.map((l) => [l.llave, l]));
  plan.lotes.forEach((lote, i) => {
    if (soloLotes && !soloLotes.includes(i)) return;
    for (const k of lote) {
      if (reg.aplicado.has(k)) { saltadas++; continue; }   // idempotente: reenviar no duplica
      const l = porLlave.get(k)!;
      const id = escribir(l);
      reg.aplicado.set(k, { id, antes: l.antes });
      aplicadas++;
    }
  });
  return { aplicadas, saltadas };
}

export function revertir(plan: Plan, reg: Registro, deshacer: (id: number, antes?: Record<string, unknown>) => void): number {
  let n = 0;
  for (const l of plan.lineas) {
    const a = reg.aplicado.get(l.llave);
    if (!a) continue;
    deshacer(a.id, a.antes);   // creado → archivar (no borrar); actualizado → restaurar `antes`
    reg.aplicado.delete(l.llave);
    n++;
  }
  return n;
}
