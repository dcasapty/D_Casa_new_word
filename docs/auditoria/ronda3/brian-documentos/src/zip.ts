/**
 * Lector de ZIP defensivo por rangos (xlsx, docx, ods son ZIP).
 *
 * - Lee solo el directorio central y las entradas pedidas: memoria ∝ entrada más grande
 *   en uso (y en streaming, ∝ tamaño del trozo), no ∝ archivo.
 * - Defensas contra «zip bombs»: límite de entradas, de tamaño descomprimido declarado (por
 *   entrada y total), de razón de compresión, conteo REAL de bytes al inflar (el encabezado
 *   puede mentir) y detección de entradas solapadas (bomba no recursiva de Fifield).
 * - Rechaza: cifrado, métodos distintos de stored/deflate, ZIP64, rutas absolutas o con «..».
 */
import { Inflate, inflateSync } from 'fflate';
import type { Fuente } from './fuente.ts';

export interface Limites {
  maxEntradas: number;
  maxEntrada: number;          // bytes descomprimidos por entrada
  maxTotal: number;            // bytes descomprimidos declarados en total
  maxRazon: number;            // descomprimido / comprimido (entradas > 1 MB)
}

export const LIMITES_DEFECTO: Limites = {
  maxEntradas: 10_000,
  maxEntrada: 512 * 1024 * 1024,
  maxTotal: 1024 * 1024 * 1024,
  maxRazon: 250,
};

export class ErrorZip extends Error {
  codigo: string;
  constructor(msg: string, codigo: string) { super(msg); this.codigo = codigo; }
}

export interface Entrada {
  nombre: string;
  metodo: number;
  comprimido: number;
  descomprimido: number;
  offsetLocal: number;
  flags: number;
}

const u16 = (b: Uint8Array, o: number) => b[o] | (b[o + 1] << 8);
const u32 = (b: Uint8Array, o: number) => (b[o] | (b[o + 1] << 8) | (b[o + 2] << 16)) + b[o + 3] * 0x1000000;

const dec = new TextDecoder('utf-8');

export class Zip {
  readonly entradas = new Map<string, Entrada>();
  readonly avisos: string[] = [];
  private f: Fuente;
  private lim: Limites;
  constructor(f: Fuente, lim: Limites) { this.f = f; this.lim = lim; }

  static async abrir(f: Fuente, lim: Limites = LIMITES_DEFECTO): Promise<Zip> {
    const z = new Zip(f, lim);
    await z.leerDirectorio();
    return z;
  }

  private async leerDirectorio() {
    const f = this.f;
    if (f.tamano < 22) throw new ErrorZip('archivo demasiado pequeño para ser ZIP', 'no_zip');
    const cola = Math.min(f.tamano, 65_557);
    const b = await f.leer(f.tamano - cola, cola);
    let eocd = -1;
    for (let i = b.length - 22; i >= 0; i--) {
      if (b[i] === 0x50 && b[i + 1] === 0x4b && b[i + 2] === 5 && b[i + 3] === 6) { eocd = i; break; }
    }
    if (eocd < 0) throw new ErrorZip('no se encontró el fin del directorio central', 'no_zip');
    const total = u16(b, eocd + 10);
    const tamCd = u32(b, eocd + 12);
    const offCd = u32(b, eocd + 16);
    if (total === 0xffff || offCd === 0xffffffff) throw new ErrorZip('ZIP64 no soportado en el Worker', 'zip64');
    if (total > this.lim.maxEntradas) throw new ErrorZip(`demasiadas entradas (${total})`, 'bomba');
    if (offCd + tamCd > f.tamano) throw new ErrorZip('directorio central fuera del archivo', 'corrupto');
    const cd = await f.leer(offCd, tamCd);
    let p = 0;
    let sumaDecl = 0;
    for (let k = 0; k < total; k++) {
      if (u32(cd, p) !== 0x02014b50) throw new ErrorZip('directorio central corrupto', 'corrupto');
      const flags = u16(cd, p + 8);
      const metodo = u16(cd, p + 10);
      const comprimido = u32(cd, p + 20);
      const descomprimido = u32(cd, p + 24);
      const ln = u16(cd, p + 28), le = u16(cd, p + 30), lc = u16(cd, p + 32);
      const offsetLocal = u32(cd, p + 42);
      const nombre = dec.decode(cd.subarray(p + 46, p + 46 + ln));
      p += 46 + ln + le + lc;
      if (nombre.endsWith('/')) continue;
      if (nombre.startsWith('/') || nombre.split(/[\\/]/).includes('..')) {
        this.avisos.push(`ruta sospechosa ignorada: ${nombre}`);
        continue;
      }
      if (flags & 1) throw new ErrorZip('el archivo está cifrado (protegido con contraseña)', 'cifrado');
      if (metodo !== 0 && metodo !== 8) throw new ErrorZip(`método de compresión ${metodo} no soportado`, 'metodo');
      if (descomprimido > this.lim.maxEntrada) throw new ErrorZip(`entrada demasiado grande: ${nombre}`, 'bomba');
      if (comprimido > 0 && descomprimido > 1_048_576 && descomprimido / comprimido > this.lim.maxRazon) {
        throw new ErrorZip(`razón de compresión sospechosa en ${nombre} (${Math.round(descomprimido / comprimido)}×)`, 'bomba');
      }
      sumaDecl += descomprimido;
      if (sumaDecl > this.lim.maxTotal) throw new ErrorZip('tamaño descomprimido total excesivo', 'bomba');
      if (this.entradas.has(nombre)) throw new ErrorZip(`entrada duplicada: ${nombre}`, 'corrupto');
      this.entradas.set(nombre, { nombre, metodo, comprimido, descomprimido, offsetLocal, flags });
    }
    // Entradas solapadas (bomba de Fifield): ordenar por offset y comprobar que no se pisan
    const orden = [...this.entradas.values()].sort((a, b2) => a.offsetLocal - b2.offsetLocal);
    for (let i = 1; i < orden.length; i++) {
      const prev = orden[i - 1];
      if (prev.offsetLocal + 30 + prev.comprimido > orden[i].offsetLocal) {
        throw new ErrorZip('entradas solapadas (posible zip bomb)', 'bomba');
      }
    }
  }

  tiene(nombre: string): boolean { return this.entradas.has(nombre); }
  nombres(): string[] { return [...this.entradas.keys()]; }

  private async inicioDatos(e: Entrada): Promise<number> {
    const h = await this.f.leer(e.offsetLocal, 30);
    if (u32(h, 0) !== 0x04034b50) throw new ErrorZip(`encabezado local corrupto: ${e.nombre}`, 'corrupto');
    return e.offsetLocal + 30 + u16(h, 26) + u16(h, 28);
  }

  /** Lee una entrada completa (partes pequeñas e imágenes). */
  async bytes(nombre: string, max = 64 * 1024 * 1024): Promise<Uint8Array> {
    const e = this.entradas.get(nombre);
    if (!e) throw new ErrorZip(`no existe ${nombre}`, 'falta');
    if (e.descomprimido > max) throw new ErrorZip(`${nombre} excede ${max} bytes`, 'grande');
    const ini = await this.inicioDatos(e);
    const datos = await this.f.leer(ini, e.comprimido);
    if (e.metodo === 0) return datos;
    const out = new Uint8Array(e.descomprimido);
    let r: Uint8Array;
    try {
      r = inflateSync(datos, { out });
    } catch (err) {
      throw new ErrorZip(`no se pudo descomprimir ${nombre}: ${(err as Error).message}`, 'corrupto');
    }
    if (r.length !== e.descomprimido) throw new ErrorZip(`tamaño real ≠ declarado en ${nombre}`, 'bomba');
    return r;
  }

  async texto(nombre: string, max?: number): Promise<string> {
    return dec.decode(await this.bytes(nombre, max));
  }

  /**
   * Entrega el texto de una entrada en trozos (streaming): no materializa el XML completo.
   * `alTrozo` puede devolver `false` para detener la lectura (p. ej. ya se leyó la ventana).
   */
  async streamTexto(nombre: string, alTrozo: (s: string) => boolean | void, trozo = 256 * 1024): Promise<void> {
    const e = this.entradas.get(nombre);
    if (!e) throw new ErrorZip(`no existe ${nombre}`, 'falta');
    const ini = await this.inicioDatos(e);
    const td = new TextDecoder('utf-8');
    let real = 0;
    let parar = false;
    const emitir = (u: Uint8Array, fin: boolean) => {
      real += u.length;
      if (real > e.descomprimido) throw new ErrorZip(`${nombre}: más bytes que los declarados (bomba)`, 'bomba');
      if (!parar && alTrozo(td.decode(u, { stream: !fin })) === false) parar = true;
    };
    if (e.metodo === 0) {
      for (let p = 0; p < e.comprimido && !parar; p += trozo) {
        emitir(await this.f.leer(ini + p, Math.min(trozo, e.comprimido - p)), p + trozo >= e.comprimido);
      }
      return;
    }
    const inf = new Inflate((d, fin) => emitir(d, fin));
    for (let p = 0; p < e.comprimido && !parar; p += trozo) {
      const k = Math.min(trozo, e.comprimido - p);
      inf.push(await this.f.leer(ini + p, k), p + k >= e.comprimido);
    }
  }
}
