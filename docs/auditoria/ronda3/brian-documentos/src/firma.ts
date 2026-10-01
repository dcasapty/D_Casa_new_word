/**
 * Detección de tipo por FIRMA de bytes (no por mimetype ni extensión: el navegador y Telegram
 * mandan a menudo `application/octet-stream` o vacío; ver brian_panel.js:476,488).
 */
import type { Fuente } from './fuente.ts';
import { Zip } from './zip.ts';

export type Tipo =
  | 'xlsx' | 'xlsm' | 'xlsb' | 'ods' | 'docx' | 'odt' | 'pptx' | 'zip'
  | 'pdf' | 'ole' | 'ole_cifrado'
  | 'png' | 'jpeg' | 'gif' | 'webp' | 'bmp' | 'heic' | 'tiff'
  | 'texto' | 'desconocido';

export interface Deteccion { tipo: Tipo; detalle?: string }

const empieza = (b: Uint8Array, firma: number[], desde = 0) => firma.every((x, i) => b[desde + i] === x);
const ascii = (b: Uint8Array, desde: number, n: number) => String.fromCharCode(...b.subarray(desde, desde + n));

export async function detectar(f: Fuente): Promise<Deteccion> {
  const b = await f.leer(0, Math.min(f.tamano, 4096));
  if (empieza(b, [0x50, 0x4b, 0x03, 0x04]) || empieza(b, [0x50, 0x4b, 0x05, 0x06])) {
    const z = await Zip.abrir(f);
    if (z.tiene('xl/workbook.bin')) return { tipo: 'xlsb', detalle: 'Excel binario: convertir a xlsx (Container)' };
    if (z.tiene('xl/workbook.xml')) return { tipo: z.tiene('xl/vbaProject.bin') ? 'xlsm' : 'xlsx' };
    if (z.tiene('word/document.xml')) return { tipo: 'docx' };
    if (z.tiene('ppt/presentation.xml')) return { tipo: 'pptx' };
    if (z.tiene('mimetype')) {
      const mt = (await z.texto('mimetype', 200)).trim();
      if (mt === 'application/vnd.oasis.opendocument.spreadsheet') return { tipo: 'ods' };
      if (mt === 'application/vnd.oasis.opendocument.text') return { tipo: 'odt' };
    }
    return { tipo: 'zip' };
  }
  if (ascii(b, 0, 5) === '%PDF-') return { tipo: 'pdf' };
  if (empieza(b, [0xd0, 0xcf, 0x11, 0xe0, 0xa1, 0xb1, 0x1a, 0xe1])) {
    // CFB/OLE: .xls/.doc viejos o un xlsx PROTEGIDO CON CONTRASEÑA (EncryptedPackage).
    const nombreUtf16 = (s: string) => Array.from(s).flatMap((c) => [c.charCodeAt(0), 0]);
    const todo = await f.leer(0, Math.min(f.tamano, 1 << 20));
    const buscar = (pat: number[]) => {
      outer: for (let i = 0; i + pat.length <= todo.length; i++) {
        for (let j = 0; j < pat.length; j++) if (todo[i + j] !== pat[j]) continue outer;
        return true;
      }
      return false;
    };
    if (buscar(nombreUtf16('EncryptedPackage'))) return { tipo: 'ole_cifrado', detalle: 'xlsx/docx protegido con contraseña' };
    if (buscar(nombreUtf16('Workbook')) || buscar(nombreUtf16('Book'))) return { tipo: 'ole', detalle: 'xls (Excel 97-2003)' };
    if (buscar(nombreUtf16('WordDocument'))) return { tipo: 'ole', detalle: 'doc (Word 97-2003)' };
    return { tipo: 'ole' };
  }
  if (empieza(b, [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])) return { tipo: 'png' };
  if (empieza(b, [0xff, 0xd8, 0xff])) return { tipo: 'jpeg' };
  if (ascii(b, 0, 6) === 'GIF87a' || ascii(b, 0, 6) === 'GIF89a') return { tipo: 'gif' };
  if (ascii(b, 0, 4) === 'RIFF' && ascii(b, 8, 4) === 'WEBP') return { tipo: 'webp' };
  if (ascii(b, 0, 2) === 'BM' && (b[2] | (b[3] << 8) | (b[4] << 16)) + b[5] * 0x1000000 === f.tamano) return { tipo: 'bmp' };
  if (ascii(b, 4, 4) === 'ftyp' && /^(heic|heix|hevc|mif1|msf1|heim|heis)$/.test(ascii(b, 8, 4))) return { tipo: 'heic' };
  if (ascii(b, 0, 4) === 'II*\0' || ascii(b, 0, 4) === 'MM\0*') return { tipo: 'tiff' };
  // ¿texto? (sin bytes NUL en la muestra)
  if (b.length && !b.includes(0)) return { tipo: 'texto' };
  return { tipo: 'desconocido' };
}
