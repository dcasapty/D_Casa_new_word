/**
 * CSV/TSV → mismo esquema de hoja que el xlsx (celdas A1, tablas, precios), para que Brian
 * tenga UNA sola forma de razonar sobre tablas.
 *
 * Excel en español guarda CSV en Windows-1252 con «;» y coma decimal: hoy Brian lo decodifica
 * como UTF-8 con `errors='replace'` (conversacion.py:487-489) y corrompe tildes y «ñ».
 * El decodificador cp1252 va escrito a mano: no consta en la documentación de Workers que
 * su TextDecoder soporte «windows-1252» (NO VERIFICADO), y son 32 códigos.
 */
import type { Hoja, Celda } from './xlsx.ts';
import { ref } from './ref.ts';
import { numero, preciosEnTexto } from './precios.ts';
import { sospechaInstruccion } from './inyeccion.ts';
import { detectarTablas } from './tablas.ts';

const CP1252_80_9F = [0x20ac, 0, 0x201a, 0x192, 0x201e, 0x2026, 0x2020, 0x2021, 0x2c6, 0x2030, 0x160, 0x2039, 0x152, 0, 0x17d, 0,
  0, 0x2018, 0x2019, 0x201c, 0x201d, 0x2022, 0x2013, 0x2014, 0x2dc, 0x2122, 0x161, 0x203a, 0x153, 0, 0x17e, 0x178];

export function decodificarTexto(b: Uint8Array): { texto: string; codificacion: 'utf-8' | 'utf-16le' | 'windows-1252' } {
  if (b[0] === 0xef && b[1] === 0xbb && b[2] === 0xbf) return { texto: new TextDecoder('utf-8').decode(b.subarray(3)), codificacion: 'utf-8' };
  if (b[0] === 0xff && b[1] === 0xfe) return { texto: new TextDecoder('utf-16le').decode(b.subarray(2)), codificacion: 'utf-16le' };
  try {
    return { texto: new TextDecoder('utf-8', { fatal: true }).decode(b), codificacion: 'utf-8' };
  } catch {
    let s = '';
    for (const x of b) s += String.fromCharCode(x >= 0x80 && x <= 0x9f ? CP1252_80_9F[x - 0x80] || x : x);
    return { texto: s, codificacion: 'windows-1252' };
  }
}

export function separador(texto: string): string {
  const muestra = texto.split(/\r?\n/).slice(0, 20).join('\n');
  const cand = [';', ',', '\t', '|'];
  let mejor = ',', puntos = -1;
  for (const c of cand) {
    const cuentas = muestra.split('\n').filter(Boolean).map((l) => l.split(c).length - 1);
    const consistentes = cuentas.filter((n) => n > 0 && n === cuentas[0]).length;
    if (consistentes > puntos) { puntos = consistentes; mejor = c; }
  }
  return mejor;
}

export function parsearCsv(texto: string, sep: string): string[][] {
  const filas: string[][] = [];
  let fila: string[] = [], campo = '', comillas = false;
  for (let i = 0; i < texto.length; i++) {
    const c = texto[i];
    if (comillas) {
      if (c === '"') { if (texto[i + 1] === '"') { campo += '"'; i++; } else comillas = false; }
      else campo += c;
    } else if (c === '"') comillas = true;
    else if (c === sep) { fila.push(campo); campo = ''; }
    else if (c === '\n' || c === '\r') {
      if (c === '\r' && texto[i + 1] === '\n') i++;
      fila.push(campo); filas.push(fila); fila = []; campo = '';
    } else campo += c;
  }
  if (campo || fila.length) { fila.push(campo); filas.push(fila); }
  return filas;
}

export function leerCsv(b: Uint8Array, nombre: string, maxFilas = 60): { hoja: Hoja; codificacion: string; separador: string } {
  const { texto, codificacion } = decodificarTexto(b);
  const sep = separador(texto);
  const filas = parsearCsv(texto, sep);
  const celdas: Record<string, Celda> = {};
  let n = 0, ultCol = 0;
  filas.forEach((f, i) => {
    if (i >= maxFilas) return;
    f.forEach((v, j) => {
      const t = v.trim();
      if (!t) return;
      n++; ultCol = Math.max(ultCol, j + 1);
      // número: «1.329,99» (regional español, separador «;») o «1,329.99»; numero() decide por el último separador
      const num = /^\d[\d.,]*$/.test(t) ? numero(t) : null;
      const c: Celda = num !== null && !(i === 0) ? { valor: num, tipo: 'n' } : { valor: t, tipo: 's' };
      // OWASP CSV injection: un texto que empieza por = + - @ se guarda como DATO (nunca fórmula)
      if (typeof c.valor === 'string' && /[$]|B\/\./.test(c.valor)) { const p = preciosEnTexto(c.valor); if (p.precios.length) c.precios = p; }
      if (typeof c.valor === 'string' && sospechaInstruccion(c.valor)) c.sospecha_instruccion = true;
      celdas[ref(i + 1, j + 1)] = c;
    });
  });
  const hoja: Hoja = {
    nombre, estado: 'visible', dimension: undefined,
    resumen: { filas_con_datos: filas.length, celdas: n, formulas: 0, formulas_sin_cache: 0, ultima_fila: filas.length, ultima_columna: String(ultCol), columnas: [] },
    combinadas: [], filas_ocultas: [], columnas_ocultas: [], imagenes: [], cuadros_texto: [],
    ventana: { rango: null, filas: Math.min(filas.length, maxFilas), truncada: filas.length > maxFilas },
    celdas, tablas: [],
  };
  hoja.tablas = detectarTablas(hoja);
  return { hoja, codificacion, separador: sep };
}
