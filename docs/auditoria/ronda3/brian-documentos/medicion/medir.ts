/**
 * Orquestador: cada combinación (lector, archivo) corre REPS veces en procesos aparte y se
 * reporta la MEDIANA (hay otros agentes usando la máquina: 4 vCPU, 16 GB).
 *   node --experimental-strip-types medicion/medir.ts [reps]
 */
import { execFileSync } from 'node:child_process';
import { existsSync, writeFileSync, mkdirSync, statSync } from 'node:fs';
import { resolve } from 'node:path';
const REPS = Number(process.argv[2] ?? 3);
const AQUI = resolve(import.meta.dirname, '..');
const archivos = [
  resolve(AQUI, '../../../../up media/DCASA_listado_productos.xlsx'),
  ...['sintetico.xlsx', 'datos_1mb.xlsx', 'datos_10mb.xlsx', 'datos_10mb_sst.xlsx', 'datos_50mb.xlsx', 'datos_50mb_sst.xlsx', 'fotos_50mb.xlsx'].map((n) => resolve(AQUI, 'fixtures', n)),
].filter(existsSync);
// proto-128: el mismo lector con el heap de V8 topado a ~120 MB (old 96 + 3×8 semi): ¿cabe en el isolate?
const lectores = (process.env.LECTORES ?? 'proto,proto-128,proto-buffer,exceljs,sheetjs,openpyxl-ro,openpyxl-full').split(',');
const FLAGS_128 = ['--max-old-space-size=96', '--max-semi-space-size=8'];
const mediana = (xs: number[]) => { const s = [...xs].sort((a, b) => a - b); return s[Math.floor(s.length / 2)]; };
const filas: Record<string, unknown>[] = [];
for (const a of archivos) for (const l of lectores) {
  const runs: Record<string, any>[] = [];
  const pesado = ['exceljs', 'sheetjs', 'openpyxl-full'].includes(l) && statSync(a).size > 40e6;
  for (let i = 0; i < (pesado ? 1 : REPS); i++) {
    let out: string;
    try {
      out = l.startsWith('openpyxl')
        ? execFileSync('python3', [resolve(AQUI, 'medicion/uno_openpyxl.py'), l === 'openpyxl-ro' ? 'ro' : 'full', a], { encoding: 'utf8', timeout: 600_000 })
        : execFileSync(process.execPath, [...(l === 'proto-128' ? FLAGS_128 : []), '--expose-gc', '--experimental-strip-types', '--no-warnings', resolve(AQUI, 'medicion/uno.ts'), l === 'proto-128' ? 'proto' : l, a], { encoding: 'utf8', timeout: 600_000, maxBuffer: 1 << 24 });
    } catch (e) { out = JSON.stringify({ lector: l, archivo: a.split('/').pop(), ok: false, error: String((e as Error).message).slice(0, 160) }); }
    runs.push(JSON.parse(out.trim().split('\n').pop()!));
    if (!runs[runs.length - 1].ok) break;
  }
  const ok = runs.every((r) => r.ok);
  const fila = ok ? {
    archivo: runs[0].archivo, lector: l, reps: runs.length,
    ms: mediana(runs.map((r) => r.ms)), cpu_ms: mediana(runs.map((r) => r.cpu_ms)),
    rss_delta_mb: mediana(runs.map((r) => r.rss_delta_mb)),
    heap_pico_mb: runs[0].heap_pico_mb === null ? null : mediana(runs.map((r) => r.heap_pico_mb)),
    ms_todas: runs.map((r) => r.ms).join('/'), detalle: runs[0].detalle,
  } : { archivo: runs[0].archivo, lector: l, ok: false, error: runs[runs.length - 1].error };
  filas.push(fila);
  console.log(JSON.stringify(fila));
}
mkdirSync(resolve(AQUI, 'medicion/salida'), { recursive: true });
writeFileSync(resolve(AQUI, 'medicion/salida/mediciones.json'), JSON.stringify({ fecha: new Date().toISOString(), reps: REPS, node: process.version, filas }, null, 1));
