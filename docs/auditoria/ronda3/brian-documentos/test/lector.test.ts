import { describe, it, expect } from 'vitest';
import { readFileSync, existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { zipSync, deflateSync, strToU8 } from 'fflate';
import { fuenteDeBytes, fuenteR2, conCache, type BucketR2 } from '../src/fuente.ts';
import { leerXlsx } from '../src/xlsx.ts';
import { Zip, ErrorZip } from '../src/zip.ts';
import { ErrorXml, TokenizadorXml } from '../src/xml.ts';
import { detectar } from '../src/firma.ts';
import { decidir } from '../src/documento.ts';
import { preciosEnTexto, numero } from '../src/precios.ts';
import { leerCsv } from '../src/csv.ts';
import { leerDocx } from '../src/docx.ts';
import { leerPdf } from '../src/pdf.ts';
import { registros } from '../src/tablas.ts';
import { validarExtraccion, envolverDato, vistaParaModelo, validarMapeo } from '../src/modelo.ts';
import { planificar, aplicar, revertir, type Existente } from '../src/importacion.ts';
import { tokensVision } from '../src/imagenes.ts';

const FIX = resolve(__dirname, '../fixtures');
const REPO = resolve(__dirname, '../../../../..');
const REAL = resolve(REPO, 'up media/DCASA_listado_productos.xlsx');
const bytes = (p: string) => new Uint8Array(readFileSync(p));
const fuente = (p: string) => fuenteDeBytes(bytes(p));

describe('xlsx sintético (dcasa.xlsx/2)', async () => {
  const inter = await leerXlsx(fuente(`${FIX}/sintetico.xlsx`), 'sintetico.xlsx');
  const h = inter.hojas[0];

  it('hojas, estado y hoja oculta', () => {
    expect(inter.esquema).toBe('dcasa.xlsx/2');
    expect(inter.hojas.map((x) => [x.nombre, x.estado])).toEqual([['Lista Proveedor', 'visible'], ['Costos (oculta)', 'hidden']]);
  });

  it('celdas combinadas: ancla y cubiertas', () => {
    expect(h.combinadas).toContain('C4:D4');
    expect(h.celdas.C4.combina).toBe('C4:D4');
    expect(h.celdas.D4.combinada_en).toBe('C4');
    expect(h.celdas.A5.combinada_en).toBe('A4');
  });

  it('fórmulas: valor en caché, fórmula, y fórmula SIN caché', () => {
    expect(h.celdas.G6).toMatchObject({ valor: 160.49, formula: '=ROUND(C6*1.07,2)', clase_formato: 'moneda' });
    expect(h.celdas.C18).toMatchObject({ valor: null, tipo: 'f_sin_cache', formula: '=SUM(C16:C16)' });
    expect(h.resumen.formulas_sin_cache).toBe(1);
  });

  it('formatos: moneda y fecha (serial → ISO)', () => {
    expect(h.celdas.C6).toMatchObject({ valor: 149.99, formato: '"$"#,##0.00', clase_formato: 'moneda' });
    expect(h.celdas.B2).toMatchObject({ valor: '2026-09-15', tipo: 'd' });
  });

  it('fila oculta, comentario e hipervínculo', () => {
    expect(h.filas_ocultas).toEqual([11]);
    expect(h.celdas.A11.oculta).toBe(true);
    expect(h.celdas.C6.comentario).toContain('WhatsApp');
    expect(h.celdas.B8.enlace).toBe('https://example.com/sofa');
  });

  it('imágenes flotantes con su celda ancla (oneCell y twoCell)', () => {
    const flot = h.imagenes.filter((i) => i.tipo === 'flotante');
    expect(flot.map((i) => [i.celda, i.hasta ?? null, i.anclaje, i.ancho, i.alto]).sort()).toEqual([
      ['F6', null, 'oneCell', 120, 90], ['F7', 'G9', 'twoCell', 200, 150]]);
  });

  it('imágenes EN CELDA (richData): vm → rc XLRICHVALUE → rv → clave por nombre → media', () => {
    const enc = Object.fromEntries(h.imagenes.filter((i) => i.tipo === 'en_celda').map((i) => [i.celda, i]));
    expect(enc.F9.ruta).toBe('xl/media/encelda1.png');
    // F10: bk con dos <rc> (XLDAPR primero) y estructura con CalcOrigin antes del identificador
    expect(enc.F10.ruta).toBe('xl/media/encelda2.png');
    expect(enc.F10.alt).toBe('Colchón Queen visto de frente');
    expect(enc.F10.calc_origin).toBe(5);
    expect(h.celdas.F10).toMatchObject({ tipo: 'imagen', imagen: enc.F10.id });
  });

  it('precios en texto normalizados con literal y alertas', () => {
    expect(h.celdas.C7.precios!.precios.map((p) => [p.etiqueta, p.valor])).toEqual([['Full', 149.99], ['Queen', 169.99]]);
    expect(h.celdas.C9.precios!.alertas[0]).toMatch(/precio vacío para «Queen»/);
    expect(h.celdas.C10.precios!.precios[0]).toMatchObject({ valor: 59.99, calificador: 'desde' });
    expect(h.celdas.C17.precios!.precios[0]).toMatchObject({ valor: 18, moneda: 'PAB' });
  });

  it('inyección en una celda: marcada, no obedecida', () => {
    expect(h.celdas.H7.sospecha_instruccion).toBe(true);
    expect(h.celdas.B7.sospecha_instruccion).toBeUndefined();
  });

  it('dos tablas en la hoja, encabezado de dos filas y título', () => {
    expect(h.tablas.map((t) => t.rango)).toEqual(['A4:H11', 'A14:C18']);
    const t = h.tablas[0];
    expect(t.encabezado.filas).toEqual([4, 5]);
    expect(t.columnas.slice(0, 4).map((c) => [c.nombre, c.rol])).toEqual([
      ['Código', 'codigo'], ['Descripción', 'descripcion'], ['Precio / Contado', 'precio_contado'], ['Precio / Crédito', 'precio_credito']]);
    expect(h.tablas[1]).toMatchObject({ titulo: 'ACCESORIOS', fila_total: 18, datos: { filas: 2 } });
  });

  it('registros: cada campo con su celda y las imágenes de la fila', () => {
    const regs = registros(h, h.tablas[0]);
    const cam1 = regs.find((r) => r.fila === 6)!;
    expect(cam1.campos.codigo).toEqual({ valor: 'CAM-001', celda: 'A6' });
    expect(cam1.imagenes).toHaveLength(1);
    expect(regs.find((r) => r.fila === 10)!.imagenes).toEqual([h.celdas.F10.imagen]);
    expect(regs.find((r) => r.fila === 11)!.oculta).toBe(true);
  });

  it('ventana: rango pedido devuelve solo esas celdas y el resumen sigue completo', async () => {
    const v = await leerXlsx(fuente(`${FIX}/sintetico.xlsx`), 's', { hoja: 'Lista Proveedor', rango: 'A6:C8' });
    expect(Object.keys(v.hojas[0].celdas).sort()).toEqual(['A6', 'A7', 'A8', 'B6', 'B7', 'B8', 'C6', 'C7', 'C8']);
    expect(v.hojas[0].resumen.celdas).toBe(h.resumen.celdas);
  });

  it('lee igual desde R2 por rangos (fuente simulada) y con caché de bloques', async () => {
    const b = bytes(`${FIX}/sintetico.xlsx`);
    let peticiones = 0;
    const bucket: BucketR2 = {
      async head() { return { size: b.length }; },
      async get(_k, op) { peticiones++; const r = op!.range!; return { async arrayBuffer() { return b.slice(r.offset, r.offset + r.length).buffer; } }; },
    };
    const r2 = await leerXlsx(conCache(await fuenteR2(bucket, 'k'), 4096), 'sintetico.xlsx');
    expect(r2.hojas[0].celdas.G6.valor).toBe(160.49);
    expect(peticiones).toBeGreaterThan(0);
  });
});

describe('Excel real del negocio (up media/DCASA_listado_productos.xlsx)', async () => {
  const inter = await leerXlsx(fuente(REAL), 'DCASA_listado_productos.xlsx', { maxFilas: 300 });
  const p = inter.hojas.find((x) => x.nombre === 'Productos')!;
  it('coincide con lo medido en la ronda 2', () => {
    expect(inter.sha256!.slice(0, 8)).toBe('731580f9');
    expect(inter.hojas.map((x) => x.nombre)).toEqual(['Productos', 'Imágenes (proyecto)', 'Todas las fichas', 'Notas']);
    expect(p.dimension).toBe('A1:G220');
    expect(p.tablas[0].datos.filas).toBe(219);
    expect(inter.hojas.reduce((s, x) => s + x.imagenes.length + x.combinadas.length + x.resumen.formulas, 0)).toBe(0);
  });
  it('mapea encabezados por rol, incluido «Precio (+ITBMS)» vs «Precios por tamaño»', () => {
    expect(p.tablas[0].columnas.map((c) => c.rol)).toEqual(['codigo', 'descripcion', 'precio', 'precio_por_tamano', 'combo', 'stock', 'observaciones']);
  });
  it('alertas deterministas: precios no crecientes y tamaño sin precio', () => {
    const alertas = Object.entries(p.celdas).filter(([k, c]) => k.startsWith('D') && c.precios?.alertas.length).map(([k]) => k);
    expect(alertas.sort()).toEqual(['D142', 'D171', 'D182']);
  });
  it('códigos únicos 199 de 219 filas', () => {
    const cods = registros(p, p.tablas[0]).map((r) => String(r.campos.codigo?.valor ?? ''));
    expect(cods.length).toBe(219);
    expect(new Set(cods.filter(Boolean)).size).toBe(199);
  });
});

const EXT = process.env.XLCELLIMAGE_DIR ?? resolve(__dirname, '../fixtures/externos/xlcellimage/tests/data');
describe.skipIf(!existsSync(`${EXT}/test_workbook_multi_rc.xlsx`))('libros REALES de Excel 365 con imágenes en celda (dalmartin/xlcellimage, GPL-3, no versionados)', () => {
  it('multi_rc: I1→image3, C4→image2 (no image3), I23→image3', async () => {
    const r = await leerXlsx(fuente(`${EXT}/test_workbook_multi_rc.xlsx`), 'multi_rc');
    const m = Object.fromEntries(r.hojas[0].imagenes.map((i) => [i.celda, i.ruta]));
    expect(m).toEqual({ I1: 'xl/media/image3.png', C4: 'xl/media/image2.png', I23: 'xl/media/image3.png' });
  });
  it('test_workbook: tres imágenes en celda resueltas', async () => {
    const r = await leerXlsx(fuente(`${EXT}/test_workbook.xlsx`), 'wb');
    expect(r.hojas[0].imagenes.filter((i) => i.tipo === 'en_celda')).toHaveLength(3);
    expect(r.avisos).toEqual([]);
  });
});

// ---------------------------------------------------------------- seguridad
function zipCon(entradas: Record<string, Uint8Array>) { return zipSync(entradas, { level: 9 }); }
const xlsxMin = (sst: string) => zipCon({
  '[Content_Types].xml': strToU8('<Types/>'),
  'xl/workbook.xml': strToU8('<workbook xmlns:r="r"><sheets><sheet name="H" sheetId="1" r:id="rId1"/></sheets></workbook>'),
  'xl/_rels/workbook.xml.rels': strToU8('<Relationships><Relationship Id="rId1" Type="x/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="x/sharedStrings" Target="sharedStrings.xml"/></Relationships>'),
  'xl/worksheets/sheet1.xml': strToU8('<worksheet><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c></row></sheetData></worksheet>'),
  'xl/sharedStrings.xml': strToU8(sst),
});

describe('defensas', () => {
  it('zip bomb por razón de compresión (200 MB de ceros) → rechazo sin descomprimir', async () => {
    const z = zipCon({ 'xl/workbook.xml': new Uint8Array(200 * 1024 * 1024) });
    await expect(Zip.abrir(fuenteDeBytes(z))).rejects.toMatchObject({ codigo: 'bomba' });
  });

  it('encabezado que MIENTE sobre el tamaño: se corta al contar bytes reales', async () => {
    const real = new Uint8Array(3 * 1024 * 1024).fill(65);
    const z = zipSync({ 'a.xml': real }, { level: 1 });
    // parchear el tamaño descomprimido declarado (directorio central, offset 24) a 1000
    const dv = new DataView(z.buffer);
    for (let i = z.length - 22; i >= 0; i--) if (dv.getUint32(i, true) === 0x02014b50) { dv.setUint32(i + 24, 1000, true); break; }
    const zip = await Zip.abrir(fuenteDeBytes(z));
    await expect(zip.streamTexto('a.xml', () => {})).rejects.toBeInstanceOf(ErrorZip);
  });

  it('entradas solapadas (bomba de Fifield) → rechazo', async () => {
    const z = zipSync({ 'a.xml': strToU8('hola'), 'b.xml': strToU8('chao') }, { level: 0 });
    const dv = new DataView(z.buffer);
    let k = 0;
    for (let i = 0; i < z.length - 4; i++) if (dv.getUint32(i, true) === 0x02014b50) { if (k++ === 1) dv.setUint32(i + 42, 0, true); }
    await expect(Zip.abrir(fuenteDeBytes(z))).rejects.toMatchObject({ codigo: 'bomba' });
  });

  it('XML con DOCTYPE/ENTITY («billion laughs», XXE) → rechazo', async () => {
    const sst = '<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;">]><sst><si><t>&lol2;</t></si></sst>';
    await expect(leerXlsx(fuenteDeBytes(xlsxMin(sst)), 'b.xlsx')).rejects.toBeInstanceOf(ErrorXml);
  });

  it('entidad desconocida → rechazo; predefinidas y numéricas → bien', () => {
    const textos: string[] = [];
    const t = new TokenizadorXml({ texto: (s) => textos.push(s) });
    t.alimentar('<a>&lt;x&gt; &#241; &#xF1;</a>'); t.terminar();
    expect(textos.join('')).toBe('<x> ñ ñ');
    expect(() => { const u = new TokenizadorXml({}); u.alimentar('<a>&xxe;</a>'); u.terminar(); }).toThrow(ErrorXml);
  });

  it('XML partido en trozos arbitrarios da el mismo resultado (streaming)', () => {
    const xml = '<r><c r="A1" t="s"><v>12</v></c><![CDATA[a<b&c]]><x a="1>2"/></r>';
    const salida = (trozos: string[]) => { const ev: string[] = []; const t = new TokenizadorXml({ abrir: (n, a) => ev.push(`<${n}${JSON.stringify(a)}`), texto: (s) => ev.push(s), cerrar: (n) => ev.push(`</${n}`) }); trozos.forEach((s) => t.alimentar(s)); t.terminar(); return ev.join('|'); };
    const entero = salida([xml]);
    for (let i = 1; i < xml.length; i++) expect(salida([xml.slice(0, i), xml.slice(i)])).toBe(entero);
  });

  it('ruta con «..» se ignora con aviso; cifrado se rechaza', async () => {
    const z = zipCon({ '../../evil.xml': strToU8('x'), 'ok.xml': strToU8('y') });
    const zip = await Zip.abrir(fuenteDeBytes(z));
    expect(zip.avisos[0]).toMatch(/ruta sospechosa/);
    const c = zipCon({ 'a.xml': strToU8('x') });
    const dv = new DataView(c.buffer);
    for (let i = 0; i < c.length - 4; i++) if (dv.getUint32(i, true) === 0x02014b50) dv.setUint16(i + 8, 1, true);
    await expect(Zip.abrir(fuenteDeBytes(c))).rejects.toMatchObject({ codigo: 'cifrado' });
  });

  it('macros y vínculos externos: aviso, nunca se ejecutan', async () => {
    const base = Object.fromEntries(Object.entries({
      'xl/workbook.xml': '<workbook xmlns:r="r"><sheets><sheet name="H" sheetId="1" r:id="rId1"/></sheets></workbook>',
      'xl/_rels/workbook.xml.rels': '<Relationships><Relationship Id="rId1" Type="x/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
      'xl/worksheets/sheet1.xml': '<worksheet><sheetData/></worksheet>',
      'xl/vbaProject.bin': 'MACRO', 'xl/externalLinks/externalLink1.xml': '<externalLink/>',
    }).map(([k, v]) => [k, strToU8(v)]));
    const r = await leerXlsx(fuenteDeBytes(zipCon(base)), 'm.xlsm');
    expect(r.tipo).toBe('xlsm');
    expect(r.avisos.join(' ')).toMatch(/macros VBA presentes: NO se ejecutan.*vínculos a otros libros/);
  });
});

// ---------------------------------------------------------------- otros formatos
describe('detección por firma y ruteo', () => {
  it('cada fixture se detecta por bytes, no por extensión', async () => {
    const tipos = await Promise.all(['sintetico.xlsx', 'ficha.docx', 'lista.pdf', 'proveedor.csv'].map(async (n) => (await detectar(fuente(`${FIX}/${n}`))).tipo));
    expect(tipos).toEqual(['xlsx', 'docx', 'pdf', 'texto']);
    expect((await detectar(fuenteDeBytes(new Uint8Array([0xd0, 0xcf, 0x11, 0xe0, 0xa1, 0xb1, 0x1a, 0xe1, 0, 0])))).tipo).toBe('ole');
    expect((await detectar(fuenteDeBytes(strToU8('BMW;X5;45000')))).tipo).toBe('texto');
  });
  it('ruteo: xlsx pequeño al Worker; protegido se rechaza; foto al modelo', async () => {
    expect((await decidir(fuente(`${FIX}/sintetico.xlsx`))).destino).toEqual({ donde: 'worker', lector: 'xlsx' });
    const png = bytes(`${FIX}/sintetico.xlsx`);
    const z = await Zip.abrir(fuenteDeBytes(png));
    const foto = await z.bytes('xl/media/encelda1.png');
    expect((await decidir(fuenteDeBytes(foto))).destino.donde).toBe('modelo');
  });
});

describe('precios en texto', () => {
  it.each([
    ['Twin $139.99 · Full $170.99 · Queen $216.99 · King $341.99', [139.99, 170.99, 216.99, 341.99]],
    ['B/. 1.329,99', [1329.99]],
    ['$1,329.99', [1329.99]],
    ['Combo con colchón $329.99', [329.99]],
    ['El par (-10%) $269.98', [269.98]],
    ['149,99 USD', [149.99]],
  ])('%s', (t, esperado) => expect(preciosEnTexto(t).precios.map((p) => p.valor)).toEqual(esperado));
  it('no inventa: «Queen $—» y «$00» quedan como alertas', () => {
    expect(preciosEnTexto('Queen $—').precios[0].valor).toBeNull();
    expect(preciosEnTexto('Precio queen en blanco ($00)').alertas[0]).toMatch(/precio cero/);
  });
  it('números con separadores regionales', () => {
    expect([numero('1.329,99'), numero('1,329.99'), numero('149,99'), numero('1.329')]).toEqual([1329.99, 1329.99, 149.99, 1329]);
  });
});

describe('CSV, Word y PDF', () => {
  it('CSV de Excel en español (Windows-1252, «;», coma decimal)', () => {
    const r = leerCsv(bytes(`${FIX}/proveedor.csv`), 'proveedor.csv');
    expect(r).toMatchObject({ codificacion: 'windows-1252', separador: ';' });
    expect(r.hoja.celdas.B1.valor).toBe('Descripción');
    expect(r.hoja.celdas.C3.valor).toBe(1329.99);
    expect(r.hoja.tablas[0].columnas.map((c) => c.rol)).toEqual(['codigo', 'descripcion', 'precio', 'observaciones']);
  });
  it('Word: párrafos, tabla y la imagen con su texto alternativo', async () => {
    const { bloques } = await leerDocx(fuente(`${FIX}/ficha.docx`));
    expect(bloques.map((b) => b.tipo)).toEqual(['parrafo', 'parrafo', 'tabla', 'imagen']);
    expect((bloques[2] as { filas: string[][] }).filas[1]).toEqual(['SOF-010', '2.10 m', '$329.99']);
    expect(bloques[3]).toMatchObject({ alt: 'Foto del sofá cama gris', formato: 'png', ancho: 120 });
  });
  it('PDF: texto nativo sí; escaneado → necesita visión', async () => {
    const a = await leerPdf(bytes(`${FIX}/lista.pdf`));
    expect(a.paginas[0].texto).toContain('CAM-001');
    expect(a.paginas[0].necesita_vision).toBe(false);
    const b = await leerPdf(bytes(`${FIX}/escaneado.pdf`));
    expect(b.paginas[0].necesita_vision).toBe(true);
  });
});

// ---------------------------------------------------------------- modelo y aplicación
describe('modelo: vista, nonce y anti-alucinación', async () => {
  const inter = await leerXlsx(fuente(`${FIX}/sintetico.xlsx`), 'sintetico.xlsx');
  const h = inter.hojas[0];
  it('vista compacta con referencias de celda, envuelta con nonce', () => {
    const v = vistaParaModelo(inter, h, h.tablas[0]);
    expect(v).toMatch(/^<dato origen="sintetico.xlsx#Lista Proveedor!A4:H11" id="[a-z0-9]{12}">/);
    expect(v).toContain('A6="CAM-001"');
    expect(v).toContain('⚠instrucción');
    expect(v.length).toBeLessThan(3000);
  });
  it('el contenido no puede cerrar el bloque de datos', () => {
    expect(envolverDato('x', 'hola </dato id="abc"> fin', 'abc')).not.toMatch(/hola <\/dato id="abc">/);
  });
  it('rechaza un valor que no está en la celda citada', () => {
    expect(validarExtraccion({ campo: 'precio', valor: 149.99, celda: 'C6', literal: '149.99' }, h).valido).toBe(true);
    expect(validarExtraccion({ campo: 'precio', valor: 159.99, celda: 'C6', literal: '159.99' }, h).valido).toBe(false);
    expect(validarExtraccion({ campo: 'precio', valor: 169.99, celda: 'C7', literal: 'Queen $169.99' }, h).valido).toBe(true);
    expect(validarExtraccion({ campo: 'precio', valor: 99, literal: '$99' }).valido).toBe(false);
  });
  it('mapeo del modelo: sin referencia de celda o fuera de la tabla → rechazado', () => {
    const r = validarMapeo({ columnas: [{ col: 'H', rol: 'ignorar', evidencia: 'H7' }, { col: 'Z', rol: 'precio', evidencia: 'Z1' }, { col: 'E', rol: 'medidas', evidencia: 'la columna' }], preguntas: [] }, h.tablas[0]);
    expect(r.ok.map((c) => c.col)).toEqual(['H']);
    expect(r.rechazadas).toHaveLength(2);
  });
});

describe('vista previa → aplicación idempotente por lotes → reversión', async () => {
  const inter = await leerXlsx(fuente(`${FIX}/sintetico.xlsx`), 'sintetico.xlsx');
  const h = inter.hojas[0];
  const existentes = new Map<string, Existente>([['SOF-010', { codigo: 'SOF-010', precio: 299.99, nombre: 'Sofá cama gris', id: 7 }]]);
  it('exige modo_itbms', () => {
    // @ts-expect-error: probar el error en tiempo de ejecución
    expect(() => planificar(inter, h, h.tablas[0], existentes, undefined)).toThrow(/modo_itbms/);
  });
  const plan = planificar(inter, h, h.tablas[0], existentes, 'mas_itbms', 2);
  it('plan con trazabilidad y alertas', () => {
    expect(plan.resumen).toMatchObject({ crear: 5, actualizar: 1 });
    const sof = plan.lineas.find((l) => l.codigo === 'SOF-010')!;
    expect(sof).toMatchObject({ accion: 'actualizar', valores: { precio: 329.99, precio_modo_itbms: 'mas_itbms' }, antes: { precio: 299.99 }, origen: { precio_contado: 'C8' } });
    const cam2 = plan.lineas.find((l) => l.codigo === 'CAM-002')!;
    expect(cam2.valores.variantes).toEqual({ Full: 149.99, Queen: 169.99 });
    expect(plan.lineas.find((l) => l.codigo === 'OCU-001')!.alertas).toContain('fila OCULTA en Excel (¿descontinuado?)');
    expect(plan.lineas.find((l) => l.codigo === 'CAM-001')!.imagenes).toHaveLength(1);
  });
  it('aplicar dos veces no duplica; revertir restaura', () => {
    const reg = { aplicado: new Map() };
    let id = 100;
    const escritos: string[] = [];
    const a1 = aplicar(plan, reg, (l) => { escritos.push(l.llave); return l.antes?.id as number ?? id++; });
    const a2 = aplicar(plan, reg, () => { throw new Error('no debería escribir'); });
    expect(a1.aplicadas).toBe(6);
    expect(a2).toEqual({ aplicadas: 0, saltadas: 6 });
    expect(plan.lotes.length).toBe(3);
    const deshechos: Array<[number, unknown]> = [];
    expect(revertir(plan, reg, (i, antes) => deshechos.push([i, antes]))).toBe(6);
    expect(deshechos.find(([i]) => i === 7)![1]).toMatchObject({ precio: 299.99 });
  });
});

describe('costo de visión (estimación)', () => {
  it('ficha Canva 1536×2761: tope 1568 en nivel estándar', () => {
    expect(tokensVision(1536, 2761)).toBe(1568);
    expect(tokensVision(1536, 2761, 2576, 4784)).toBeLessThanOrEqual(4784);
    expect(tokensVision(120, 90)).toBe(20);
  });
});
