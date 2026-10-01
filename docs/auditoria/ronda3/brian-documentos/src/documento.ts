/**
 * Punto de entrada: detectar por firma → decidir DÓNDE se procesa → extraer.
 *
 * Umbrales medidos en Node 22 (informe §4.4, mediana de 3): lo que llena la memoria es
 * sharedStrings (se guarda entero como arreglo de textos); el XML de las hojas va en streaming
 * y las imágenes no cuentan (solo se hashean de a una). 10 MB con sharedStrings de 14 MB: pico
 * de heap 38 MB con tope de 120 MB; 50 MB con sharedStrings de 67 MB: OOM con el tope. 50 MB de
 * celdas sin sharedStrings (340 MB de XML): 43 MB de heap pero ~19 s de CPU. Por eso el ruteo
 * mira los tamaños DESCOMPRIMIDOS, no el tamaño del archivo (40 fotos = 50 MB y 0,3 s).
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
  xlsxWorkerBytes: 100 * 1024 * 1024,        // = cuerpo máximo de petición (plan Free/Pro de la zona)
  partesXmlWorkerBytes: 160 * 1024 * 1024,   // XML de hojas + sharedStrings descomprimidos (CPU ≲ 10 s)
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
