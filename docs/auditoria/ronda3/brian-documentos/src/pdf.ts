/**
 * PDF: texto nativo por página con unpdf (pdf.js empaquetado para entornos sin DOM, incl.
 * Workers). Si una página no tiene texto (escaneo/foto), se marca `necesita_vision` y se
 * manda la PÁGINA al modelo (Claude acepta PDF como bloque `document`; ver informe §4.3).
 */
import { extractText, getDocumentProxy } from 'unpdf';
import { sospechaInstruccion } from './inyeccion.ts';

export interface PaginaPdf { n: number; texto: string; caracteres: number; necesita_vision: boolean; sospecha_instruccion?: true }

export async function leerPdf(b: Uint8Array, maxPaginas = 100): Promise<{ paginas: PaginaPdf[]; total: number; avisos: string[] }> {
  const avisos: string[] = [];
  const doc = await getDocumentProxy(new Uint8Array(b));
  const total = doc.numPages;
  if (total > maxPaginas) avisos.push(`PDF de ${total} páginas: se leen ${maxPaginas}; el resto, por partes`);
  const { text } = await extractText(doc, { mergePages: false });
  const paginas = (text as string[]).slice(0, maxPaginas).map((t, i) => {
    const limpio = t.replace(/\s+/g, ' ').trim();
    return {
      n: i + 1, texto: limpio, caracteres: limpio.length,
      necesita_vision: limpio.length < 20,
      ...(sospechaInstruccion(limpio) ? { sospecha_instruccion: true as const } : {}),
    };
  });
  return { paginas, total, avisos };
}
