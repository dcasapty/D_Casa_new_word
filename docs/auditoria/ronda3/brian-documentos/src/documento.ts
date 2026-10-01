/**
 * Punto de entrada: detectar por firma → decidir DÓNDE se procesa → extraer.
 *
 * Umbrales medidos en Node 22 (informe §4.4): el lector de este prototipo procesa el peor
 * caso (solo celdas) de 10 MB con pico de memoria muy por debajo de los 128 MB del isolate,
 * pero 50 MB de solo celdas no cabe con margen (sharedStrings + tiempo de CPU). Se fija el
 * umbral conservador abajo; por encima → Container (Python/openpyxl o calamine).
 */
import type { Fuente } from './fuente.ts';
import { detectar, type Deteccion } from './firma.ts';
import { Zip } from './zip.ts';

export type Destino =
  | { donde: 'worker'; lector: 'xlsx' | 'csv' | 'docx' | 'pdf' }
  | { donde: 'modelo'; motivo: string }                 // fotos y páginas escaneadas: visión
  | { donde: 'container'; motivo: string }
  | { donde: 'rechazar'; motivo: string };

export const UMBRALES = {
  xlsxWorkerBytes: 15 * 1024 * 1024,         // archivo xlsx
  partesXmlWorkerBytes: 160 * 1024 * 1024,   // suma de sheet*.xml + sharedStrings descomprimidos
  sharedStringsWorkerBytes: 24 * 1024 * 1024,
  pdfWorkerBytes: 20 * 1024 * 1024,
  imagenModeloBytes: 4 * 1024 * 1024,        // por encima: redimensionar (Images binding) antes
};

export async function decidir(f: Fuente): Promise<{ deteccion: Deteccion; destino: Destino }> {
  const d = await detectar(f);
  const t = f.tamano;
  const r = (destino: Destino) => ({ deteccion: d, destino });
  switch (d.tipo) {
    case 'xlsx': case 'xlsm': {
      if (t > UMBRALES.xlsxWorkerBytes) return r({ donde: 'container', motivo: `xlsx de ${(t / 1048576).toFixed(1)} MB > umbral del Worker` });
      const z = await Zip.abrir(f);
      let xml = 0, sst = 0;
      for (const e of z.entradas.values()) {
        if (/^xl\/worksheets\/sheet\d+\.xml$/.test(e.nombre)) xml += e.descomprimido;
        if (e.nombre === 'xl/sharedStrings.xml') { sst = e.descomprimido; xml += sst; }
      }
      if (xml > UMBRALES.partesXmlWorkerBytes || sst > UMBRALES.sharedStringsWorkerBytes) {
        return r({ donde: 'container', motivo: `XML descomprimido ${(xml / 1048576).toFixed(0)} MB / sharedStrings ${(sst / 1048576).toFixed(0)} MB` });
      }
      return r({ donde: 'worker', lector: 'xlsx' });
    }
    case 'xlsb': case 'ods': return r({ donde: 'container', motivo: `${d.tipo}: convertir a xlsx con LibreOffice/calamine` });
    case 'ole': return r({ donde: 'container', motivo: `${d.detalle ?? 'formato OLE'}: convertir con LibreOffice` });
    case 'ole_cifrado': return r({ donde: 'rechazar', motivo: 'archivo protegido con contraseña: pide a la persona que lo guarde sin contraseña' });
    case 'docx': return r({ donde: 'worker', lector: 'docx' });
    case 'pdf': return t > UMBRALES.pdfWorkerBytes ? r({ donde: 'container', motivo: 'PDF grande: trocear' }) : r({ donde: 'worker', lector: 'pdf' });
    case 'png': case 'jpeg': case 'webp': case 'gif':
      return r({ donde: 'modelo', motivo: t > UMBRALES.imagenModeloBytes ? 'foto: redimensionar a ≤1568 px (Images binding) y visión' : 'foto: visión del modelo' });
    case 'heic': case 'tiff': case 'bmp': return r({ donde: 'modelo', motivo: `${d.tipo}: convertir a JPEG/WebP antes (no todos los proveedores lo aceptan)` });
    case 'texto': return r({ donde: 'worker', lector: 'csv' });
    case 'pptx': case 'odt': case 'zip': return r({ donde: 'container', motivo: `${d.tipo}: fuera del alcance del Worker` });
    default: return r({ donde: 'rechazar', motivo: 'tipo de archivo desconocido' });
  }
}
