/**
 * Mide UN lector sobre UN archivo en un proceso aparte: tiempo de pared, CPU, y memoria
 * (maxRSS delta sobre la línea base tras importar; y pico de heap+ArrayBuffers muestreado en
 * cada lectura de la fuente para el prototipo). Uso:
 *   node --expose-gc --experimental-strip-types medicion/uno.ts <lector> <archivo>
 */
import { openSync, readSync, fstatSync, readFileSync } from 'node:fs';
import { performance } from 'node:perf_hooks';
const [lector, archivo] = process.argv.slice(2);
const mb = (x: number) => Math.round((x / 1048576) * 10) / 10;
let pico = 0;
const muestrear = () => { const m = process.memoryUsage(); pico = Math.max(pico, m.heapUsed + m.arrayBuffers); };

async function correr(): Promise<string> {
  if (lector === 'proto' || lector === 'proto-buffer') {
    const { leerXlsx } = await import('../src/xlsx.ts');
    const { fuenteDeBytes } = await import('../src/fuente.ts');
    const fd = openSync(archivo, 'r');
    const tam = fstatSync(fd).size;
    // fuente por rangos (como R2): nunca tiene el archivo entero en memoria
    const porRangos = { tamano: tam, async leer(d: number, l: number) { const b = new Uint8Array(Math.min(l, tam - d)); readSync(fd, b, 0, b.length, d); muestrear(); return b; } };
    gc!(); base();
    const f = lector === 'proto' ? porRangos : fuenteDeBytes(new Uint8Array(readFileSync(archivo)));
    const r = await leerXlsx(f, 'x', { maxFilas: 60, sha256: 'medicion' });
    return `${r.hojas.map((h) => `${h.nombre}:${h.resumen.filas_con_datos}f/${h.resumen.celdas}c/${h.imagenes.length}img`).join(',')}`;
  }
  if (lector === 'exceljs') {
    const ExcelJS = (await import('exceljs')).default;
    const buf = readFileSync(archivo);
    gc!(); base();
    const wb = new ExcelJS.Workbook();
    await wb.xlsx.load(buf as unknown as ArrayBuffer);
    muestrear();
    return wb.worksheets.map((w) => `${w.name}:${w.actualRowCount}f/${w.getImages().length}img`).join(',');
  }
  if (lector === 'sheetjs') {
    const XLSX = (await import('xlsx')).default;
    const buf = readFileSync(archivo);
    gc!(); base();
    const wb = XLSX.read(buf, { cellFormula: true, cellNF: true });
    muestrear();
    return wb.SheetNames.map((n) => `${n}:${wb.Sheets[n]['!ref']}`).join(',');
  }
  throw new Error(`lector desconocido ${lector}`);
}
let rssBase = 0, t0 = 0, cpu0 = process.cpuUsage();
function base() { rssBase = process.resourceUsage().maxRSS * 1024; pico = 0; muestrear(); const b = pico; pico = 0; heapBase = b; t0 = performance.now(); cpu0 = process.cpuUsage(); }
let heapBase = 0;
try {
  const det = await correr();
  const ms = performance.now() - t0;
  const cpu = process.cpuUsage(cpu0);
  const rssFin = process.resourceUsage().maxRSS * 1024;
  console.log(JSON.stringify({ lector, archivo: archivo.split('/').pop(), ok: true, ms: Math.round(ms), cpu_ms: Math.round((cpu.user + cpu.system) / 1000),
    rss_delta_mb: mb(rssFin - rssBase), heap_pico_mb: mb(Math.max(0, pico - heapBase)), detalle: det }));
} catch (e) {
  console.log(JSON.stringify({ lector, archivo: archivo.split('/').pop(), ok: false, error: String((e as Error).message).slice(0, 200) }));
}
