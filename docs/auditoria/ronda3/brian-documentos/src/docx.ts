/**
 * Word (.docx) → bloques ordenados (párrafos, tablas como matrices, imágenes con alt).
 * Sin mammoth: el mismo zip + tokenizador del xlsx (mammoth convierte a HTML y pierde la
 * estructura de tabla en celdas combinadas; aquí solo hace falta texto + tablas + imágenes).
 */
import { Zip } from './zip.ts';
import type { Fuente } from './fuente.ts';
import { TokenizadorXml } from './xml.ts';
import { infoImagen, sha256 } from './imagenes.ts';
import { sospechaInstruccion } from './inyeccion.ts';

export type Bloque =
  | { tipo: 'parrafo'; n: number; texto: string; estilo?: string; sospecha_instruccion?: true }
  | { tipo: 'tabla'; n: number; filas: string[][] }
  | { tipo: 'imagen'; n: number; ruta: string; alt?: string; formato?: string; ancho?: number; alto?: number; bytes: number; sha256?: string };

export async function leerDocx(f: Fuente): Promise<{ bloques: Bloque[]; avisos: string[] }> {
  const z = await Zip.abrir(f);
  const avisos = [...z.avisos];
  if (z.tiene('word/vbaData.xml') || z.tiene('word/vbaProject.bin')) avisos.push('macros presentes: NO se ejecutan');
  const relsTxt = z.tiene('word/_rels/document.xml.rels') ? await z.texto('word/_rels/document.xml.rels') : '';
  const relMap = new Map<string, string>();
  for (const m of relsTxt.matchAll(/<Relationship\b[^>]*>/g)) {
    const id = /Id="([^"]+)"/.exec(m[0])?.[1], t = /Target="([^"]+)"/.exec(m[0])?.[1];
    if (id && t && !/TargetMode="External"/.test(m[0])) relMap.set(id, t.startsWith('/') ? t.slice(1) : `word/${t}`);
  }
  const bloques: Bloque[] = [];
  let n = 0;
  let parrafo = '', estilo: string | undefined, enT = false;
  let profTabla = 0;
  let tabla: string[][] | null = null, fila: string[] | null = null, celda = '';
  let altPend: string | undefined;
  const imgsPend: Array<{ ruta: string; alt?: string }> = [];
  const tok = new TokenizadorXml({
    abrir(nom, a) {
      if (nom === 'tbl') { profTabla++; if (profTabla === 1) tabla = []; }
      else if (nom === 'tr' && profTabla === 1) fila = [];
      else if (nom === 'tc' && profTabla === 1) celda = '';
      else if (nom === 'p') { parrafo = ''; estilo = undefined; }
      else if (nom === 'pStyle') estilo = a['w:val'] ?? a.val;
      else if (nom === 't') enT = true;
      else if (nom === 'tab') parrafo += '\t';
      else if (nom === 'br') parrafo += '\n';
      else if (nom === 'docPr') altPend = a.descr || a.title || undefined;
      else if (nom === 'blip') {
        const id = Object.entries(a).find(([k]) => k.endsWith(':embed'))?.[1];
        const ruta = id ? relMap.get(id) : undefined;
        if (ruta) imgsPend.push({ ruta, alt: altPend });
      }
    },
    texto(t) { if (enT) parrafo += t; },
    cerrar(nom) {
      if (nom === 't') enT = false;
      else if (nom === 'p') {
        if (profTabla > 0) celda += (celda ? '\n' : '') + parrafo;
        else if (parrafo.trim()) bloques.push({ tipo: 'parrafo', n: n++, texto: parrafo, ...(estilo ? { estilo } : {}), ...(sospechaInstruccion(parrafo) ? { sospecha_instruccion: true as const } : {}) });
        for (const im of imgsPend.splice(0)) bloques.push({ tipo: 'imagen', n: n++, ruta: im.ruta, alt: im.alt, bytes: 0 });
      } else if (nom === 'tc' && profTabla === 1) fila?.push(celda.trim());
      else if (nom === 'tr' && profTabla === 1 && fila) { tabla?.push(fila); fila = null; }
      else if (nom === 'tbl') { profTabla--; if (profTabla === 0 && tabla) { bloques.push({ tipo: 'tabla', n: n++, filas: tabla }); tabla = null; } }
    },
  });
  await z.streamTexto('word/document.xml', (s) => { tok.alimentar(s); });
  tok.terminar();
  for (const b of bloques) {
    if (b.tipo !== 'imagen' || !z.tiene(b.ruta)) continue;
    const bytes = await z.bytes(b.ruta, 20 << 20);
    Object.assign(b, infoImagen(bytes), { bytes: bytes.length, sha256: await sha256(bytes) });
  }
  return { bloques, avisos };
}
