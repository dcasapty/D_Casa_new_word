/** Cuántas lecturas por rango (operaciones clase B de R2) hace el lector por archivo. */
import { openSync, readSync, fstatSync } from 'node:fs';
import { resolve } from 'node:path';
import { conCache, type Fuente } from '../src/fuente.ts';
import { leerXlsx } from '../src/xlsx.ts';
const AQUI = resolve(import.meta.dirname, '..');
for (const a of [resolve(AQUI, '../../../../up media/DCASA_listado_productos.xlsx'), resolve(AQUI, 'fixtures/sintetico.xlsx'), resolve(AQUI, 'fixtures/datos_10mb.xlsx')]) {
  const fd = openSync(a, 'r'); const tam = fstatSync(fd).size;
  let n = 0, bytes = 0;
  const f: Fuente = { tamano: tam, async leer(d, l) { n++; const b = new Uint8Array(Math.min(l, tam - d)); readSync(fd, b, 0, b.length, d); bytes += b.length; return b; } };
  await leerXlsx(conCache(f), 'x', { sha256: 'x' });
  console.log(JSON.stringify({ archivo: a.split('/').pop(), tamano: tam, peticiones: n, bytes_leidos: bytes }));
}
