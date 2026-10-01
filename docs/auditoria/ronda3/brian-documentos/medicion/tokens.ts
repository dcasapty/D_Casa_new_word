/** Tamaño de lo que ve el modelo (caracteres → tokens estimados) por documento típico. */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fuenteDeBytes } from '../src/fuente.ts';
import { leerXlsx } from '../src/xlsx.ts';
import { vistaParaModelo } from '../src/modelo.ts';
import { tokensVision } from '../src/imagenes.ts';
const AQUI = resolve(import.meta.dirname, '..');
const real = await leerXlsx(fuenteDeBytes(new Uint8Array(readFileSync(resolve(AQUI, '../../../../up media/DCASA_listado_productos.xlsx')))), 'DCASA_listado_productos.xlsx', { maxFilas: 300 });
const p = real.hojas[0];
const vista = vistaParaModelo(real, p, p.tablas[0]);
const json = JSON.stringify(p.celdas);
const csv = Object.values(p.celdas).map((c) => String(c.valor ?? '')).join(',');
console.log(JSON.stringify({
  vista_chars: vista.length, vista_tok_est: Math.round(vista.length / 3.3),
  intermedio_hoja_json_chars: json.length, intermedio_tok_est: Math.round(json.length / 3.3),
  csv_chars: csv.length,
  vision: {
    ficha_1536x2761_estandar: tokensVision(1536, 2761, 1568, 1568),
    ficha_1536x2761_altares_sin_reducir: tokensVision(1536, 2761, 2576, 4784),
    ficha_reducida_1568_en_altares: tokensVision(1536, 2761, 1568, 4784),
    ficha_reducida_1024_en_altares: tokensVision(1536, 2761, 1024, 4784),
    miniatura_512: tokensVision(1536, 2761, 512, 4784),
    foto_celular_4032x3024_altares: tokensVision(4032, 3024, 2576, 4784),
    foto_celular_reducida_1568: tokensVision(4032, 3024, 1568, 4784),
    pagina_carta_150dpi_1275x1650_altares: tokensVision(1275, 1650, 2576, 4784),
  },
}, null, 1));
console.log(vista.split('\n').slice(0, 14).join('\n'));
