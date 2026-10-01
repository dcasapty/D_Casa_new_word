/**
 * Lector de .xlsx/.xlsm para Brian → esquema intermedio `dcasa.xlsx/2`.
 *
 * Corre en Workers (solo fflate + Web Crypto + TextDecoder). Lee por rangos y en streaming:
 * una pasada por hoja calcula el RESUMEN completo (filas, fórmulas, tipos por columna,
 * combinadas, ocultas) y guarda celdas solo de la VENTANA pedida (`rango` o las primeras
 * `maxFilas` filas). Así un libro de 50 MB no se materializa: el modelo pide páginas.
 */
import { Zip, type Limites, LIMITES_DEFECTO } from './zip.ts';
import type { Fuente } from './fuente.ts';
import { TokenizadorXml, arbolXml, hijos, hijo, recorrer, textoTotal, type Nodo } from './xml.ts';
import { ref, parsearRef, parsearRango, rangoATexto, dentro, desplazarFormula, colALetra, type Rango } from './ref.ts';
import { infoImagen, sha256 } from './imagenes.ts';
import { sospechaInstruccion } from './inyeccion.ts';
import { preciosEnTexto, type PreciosTexto } from './precios.ts';
import { detectarTablas, type Tabla } from './tablas.ts';

export const ESQUEMA = 'dcasa.xlsx/2';

export interface Celda {
  valor: string | number | boolean | null;
  tipo: 'n' | 's' | 'b' | 'e' | 'd' | 'f_sin_cache' | 'imagen';
  formula?: string;
  formula_compartida_de?: string;     // celda maestra de una fórmula compartida
  formato?: string;                   // código de formato numérico (no General)
  clase_formato?: 'moneda' | 'porcentaje' | 'fecha' | 'numero';
  combina?: string;                   // si es ancla de una combinada: su rango
  combinada_en?: string;              // si está cubierta por una combinada: su ancla
  imagen?: string;                    // id de imagen (en celda)
  comentario?: string;
  enlace?: string;
  precios?: PreciosTexto;
  sospecha_instruccion?: true;
  oculta?: true;                      // fila o columna oculta
}

export interface ImagenXlsx {
  id: string;                         // sha256[:16]
  tipo: 'flotante' | 'en_celda';
  celda: string;                      // ancla (esquina superior izquierda)
  hasta?: string;                     // twoCellAnchor
  anclaje?: string;                   // oneCell | twoCell | absolute
  ruta: string;                       // parte dentro del zip (para ver_imagen)
  bytes: number;
  sha256?: string;
  formato?: string;
  ancho?: number;
  alto?: number;
  alt?: string;                       // texto alternativo (dato, puede traer inyección)
  calc_origin?: number;
  sospecha_instruccion?: true;
}

export interface ResumenColumna { col: string; numeros: number; textos: number; vacias: number; formulas: number }

export interface Hoja {
  nombre: string;
  estado: 'visible' | 'hidden' | 'veryHidden';
  dimension?: string;
  resumen: {
    filas_con_datos: number; celdas: number; formulas: number; formulas_sin_cache: number;
    ultima_fila: number; ultima_columna: string; columnas: ResumenColumna[];
  };
  combinadas: string[];
  filas_ocultas: number[];
  columnas_ocultas: string[];
  imagenes: ImagenXlsx[];
  cuadros_texto: Array<{ celda: string; texto: string; sospecha_instruccion?: true }>;
  ventana: { rango: string | null; filas: number; truncada: boolean };
  celdas: Record<string, Celda>;
  tablas: Tabla[];
}

export interface Intermedio {
  esquema: string;
  archivo: string;
  tipo: 'xlsx' | 'xlsm';
  bytes: number;
  sha256: string | null;
  avisos: string[];
  nombres_definidos: Record<string, string>;
  hojas: Hoja[];
  estadisticas: { ms: number };
}

export interface OpcionesXlsx {
  hoja?: string;             // solo esta hoja (por defecto: todas)
  rango?: string;            // ventana A1:H40 (por defecto: primeras maxFilas filas)
  maxFilas?: number;         // def. 60
  maxColumnasResumen?: number;
  sha256?: string;           // si ya se calculó al subir (DigestStream en el Worker)
  limites?: Limites;
  incluirHashImagenes?: boolean;
}

// ---------------------------------------------------------------------------------------
const FORMATOS_INTEGRADOS: Record<number, string> = {
  1: '0', 2: '0.00', 3: '#,##0', 4: '#,##0.00', 5: '"$"#,##0_);("$"#,##0)', 6: '"$"#,##0_);[Red]("$"#,##0)',
  7: '"$"#,##0.00_);("$"#,##0.00)', 8: '"$"#,##0.00_);[Red]("$"#,##0.00)', 9: '0%', 10: '0.00%', 11: '0.00E+00',
  14: 'mm-dd-yy', 15: 'd-mmm-yy', 16: 'd-mmm', 17: 'mmm-yy', 18: 'h:mm AM/PM', 19: 'h:mm:ss AM/PM', 20: 'h:mm',
  21: 'h:mm:ss', 22: 'm/d/yy h:mm', 37: '#,##0 ;(#,##0)', 38: '#,##0 ;[Red](#,##0)', 39: '#,##0.00;(#,##0.00)',
  40: '#,##0.00;[Red](#,##0.00)', 44: '_("$"* #,##0.00_)', 45: 'mm:ss', 46: '[h]:mm:ss', 47: 'mmss.0', 49: '@',
};

function claseFormato(f: string): Celda['clase_formato'] | undefined {
  const sin = f.replace(/"[^"]*"/g, (m) => (/[$€£]|B\/\./.test(m) ? '$' : '')).replace(/\[[^\]]*\]/g, (m) => (/\$/.test(m) ? '$' : ''));
  if (/[$€£]|B\/\./.test(sin)) return 'moneda';
  if (/%/.test(sin)) return 'porcentaje';
  if (/[dmyhs]/i.test(sin.replace(/General/i, ''))) return 'fecha';
  if (/[0#]/.test(sin)) return 'numero';
  return undefined;
}

function resolverRuta(base: string, destino: string): string {
  if (destino.startsWith('/')) return destino.slice(1);
  const partes = base.split('/').slice(0, -1);
  for (const p of destino.split('/')) {
    if (p === '..') partes.pop();
    else if (p !== '.') partes.push(p);
  }
  return partes.join('/');
}

function rutaRels(parte: string): string {
  const i = parte.lastIndexOf('/');
  return `${parte.slice(0, i)}/_rels/${parte.slice(i + 1)}.rels`;
}

async function rels(z: Zip, parte: string): Promise<Map<string, { tipo: string; destino: string; externo: boolean }>> {
  const m = new Map<string, { tipo: string; destino: string; externo: boolean }>();
  const r = rutaRels(parte);
  if (!z.tiene(r)) return m;
  const arbol = arbolXml(await z.texto(r, 8 << 20));
  for (const n of hijos(arbol, 'Relationship')) {
    const externo = n.a.TargetMode === 'External';
    m.set(n.a.Id, { tipo: n.a.Type.split('/').pop() ?? '', destino: externo ? n.a.Target : resolverRuta(parte, n.a.Target), externo });
  }
  return m;
}

/** Fecha serial de Excel (sistema 1900) → ISO. */
function serialAFecha(v: number): string {
  const ms = Math.round((v - 25569) * 86400 * 1000);
  const d = new Date(ms);
  return Number.isFinite(d.getTime()) ? d.toISOString().replace('T00:00:00.000Z', '') : String(v);
}

// ---------------------------------------------------------------------------------------
// Imágenes «en celda» (Excel 365 «Colocar en celda» / función IMAGE): cadena richData
//   celda@vm (1-based) → metadata.xml valueMetadata/bk[vm-1] → <rc t v> cuyo metadataType[t-1]
//   se llama XLRICHVALUE → futureMetadata[XLRICHVALUE]/bk[v] → xlrd:rvb@i → rdrichvalue.xml rv[i]
//   → estructura rv@s en rdrichvaluestructure.xml → posición de la clave
//   «_rvRel:LocalImageIdentifier» → valor en esa posición → richValueRel.xml rel[valor]@r:id
//   → richValueRel.xml.rels → xl/media/…  (también CalcOrigin y Text = texto alternativo)
// ---------------------------------------------------------------------------------------
interface ValorRico { ruta?: string; calcOrigin?: number; alt?: string; tipo: string; web?: string }

async function cadenaRichData(z: Zip, avisos: string[]): Promise<Map<number, ValorRico>> {
  const porVm = new Map<number, ValorRico>();
  if (!z.tiene('xl/metadata.xml')) return porVm;
  const meta = arbolXml(await z.texto('xl/metadata.xml', 32 << 20));
  const tipos = hijos(hijo(meta, 'metadataTypes'), 'metadataType').map((n) => n.a.name);
  const futuro = hijos(meta, 'futureMetadata').find((n) => n.a.name === 'XLRICHVALUE');
  const rvbPorBk: Array<number | undefined> = hijos(futuro, 'bk').map((bk) => {
    for (const n of recorrer(bk)) if (n.n === 'rvb') return Number(n.a.i);
    return undefined;
  });
  const leerSiHay = async (p: string) => (z.tiene(p) ? arbolXml(await z.texto(p, 64 << 20)) : undefined);
  const rv = await leerSiHay('xl/richData/rdrichvalue.xml');
  const est = await leerSiHay('xl/richData/rdrichvaluestructure.xml');
  const relXml = await leerSiHay('xl/richData/richValueRel.xml');
  const estructuras = hijos(est, 's').map((s) => ({ t: s.a.t, claves: hijos(s, 'k').map((k) => k.a.n) }));
  const valores = hijos(rv, 'rv').map((n) => ({ s: Number(n.a.s), v: hijos(n, 'v').map((x) => x.t) }));
  const relIds = hijos(relXml, 'rel').map((n) => n.a['r:id'] ?? Object.entries(n.a).find(([k]) => k.endsWith(':id'))?.[1]);
  const relMap = await rels(z, 'xl/richData/richValueRel.xml');
  // imágenes web (función IMAGE con URL): rdRichValueWebImage.xml
  const web = await leerSiHay('xl/richData/rdRichValueWebImage.xml');
  const webRels = web ? await rels(z, 'xl/richData/rdRichValueWebImage.xml') : new Map();
  const webImgs = hijos(web, 'webImageSrd').map((n) => {
    const a = hijo(n, 'address');
    const id = a ? Object.entries(a.a).find(([k]) => k.endsWith(':id'))?.[1] : undefined;
    return id ? webRels.get(id)?.destino : undefined;
  });
  hijos(hijo(meta, 'valueMetadata'), 'bk').forEach((bk, i) => {
    const vm = i + 1;
    const rc = hijos(bk, 'rc').find((r) => tipos[Number(r.a.t) - 1] === 'XLRICHVALUE');
    if (!rc) return;
    const iRv = rvbPorBk[Number(rc.a.v)];
    const valor = iRv === undefined ? undefined : valores[iRv];
    const estr = valor ? estructuras[valor.s] : undefined;
    if (!valor || !estr) { avisos.push(`richData: vm=${vm} sin valor rico resoluble`); return; }
    const campo = (clave: string) => { const k = estr.claves.indexOf(clave); return k < 0 ? undefined : valor.v[k]; };
    const vr: ValorRico = { tipo: estr.t };
    const co = campo('CalcOrigin'); if (co !== undefined) vr.calcOrigin = Number(co);
    const alt = campo('Text'); if (alt) vr.alt = alt;
    if (estr.t === '_localImage') {
      const id = campo('_rvRel:LocalImageIdentifier');
      const rid = id === undefined ? undefined : relIds[Number(id)];
      const destino = rid ? relMap.get(rid)?.destino : undefined;
      if (destino) vr.ruta = destino; else avisos.push(`richData: vm=${vm} imagen local sin destino`);
    } else if (estr.t === '_webimage') {
      const id = campo('WebImageIdentifier');
      vr.web = id === undefined ? undefined : webImgs[Number(id)];
    }
    porVm.set(vm, vr);
  });
  return porVm;
}

// ---------------------------------------------------------------------------------------
async function imagenesFlotantes(z: Zip, parteDibujo: string): Promise<{ imgs: Omit<ImagenXlsx, 'id' | 'bytes'>[]; textos: Hoja['cuadros_texto'] }> {
  const imgs: Omit<ImagenXlsx, 'id' | 'bytes'>[] = [];
  const textos: Hoja['cuadros_texto'] = [];
  if (!z.tiene(parteDibujo)) return { imgs, textos };
  const arbol = arbolXml(await z.texto(parteDibujo, 32 << 20));
  const r = await rels(z, parteDibujo);
  const marca = (n: Nodo | undefined) => {
    if (!n) return undefined;
    const col = Number(hijo(n, 'col')?.t ?? 0), fila = Number(hijo(n, 'row')?.t ?? 0);
    return ref(fila + 1, col + 1);
  };
  for (const anc of arbol.h) {
    if (!/^(oneCellAnchor|twoCellAnchor|absoluteAnchor)$/.test(anc.n)) continue;
    const desde = marca(hijo(anc, 'from')) ?? 'A1';
    const hasta = anc.n === 'twoCellAnchor' ? marca(hijo(anc, 'to')) : undefined;
    for (const n of recorrer(anc)) {
      if (n.n === 'pic') {
        const cNvPr = [...recorrer(n)].find((x) => x.n === 'cNvPr');
        const blip = [...recorrer(n)].find((x) => x.n === 'blip');
        const rid = blip ? Object.entries(blip.a).find(([k]) => k.endsWith(':embed'))?.[1] : undefined;
        const destino = rid ? r.get(rid) : undefined;
        if (!destino || destino.externo) continue;
        const alt = cNvPr?.a.descr || undefined;
        imgs.push({ tipo: 'flotante', celda: desde, hasta, anclaje: anc.n.replace('Anchor', ''), ruta: destino.destino, alt });
      } else if (n.n === 'sp') {
        const tx = [...recorrer(n)].find((x) => x.n === 'txBody');
        const t = tx ? textoTotal(tx).trim() : '';
        if (t) textos.push({ celda: desde, texto: t, ...(sospechaInstruccion(t) ? { sospecha_instruccion: true as const } : {}) });
      }
    }
  }
  return { imgs, textos };
}

async function comentarios(z: Zip, r: Map<string, { tipo: string; destino: string }>): Promise<Map<string, string>> {
  const out = new Map<string, string>();
  for (const { tipo, destino } of r.values()) {
    if (!z.tiene(destino)) continue;
    if (tipo === 'comments') {
      const a = arbolXml(await z.texto(destino, 16 << 20));
      for (const c of hijos(hijo(a, 'commentList'), 'comment')) out.set(c.a.ref, textoTotal(hijo(c, 'text') ?? c).trim());
    } else if (tipo === 'threadedComment') {
      const a = arbolXml(await z.texto(destino, 16 << 20));
      for (const c of hijos(a, 'threadedComment')) {
        const t = textoTotal(hijo(c, 'text') ?? c).trim();
        out.set(c.a.ref, out.has(c.a.ref) ? `${out.get(c.a.ref)}\n${t}` : t);
      }
    }
  }
  return out;
}

// ---------------------------------------------------------------------------------------
export async function leerXlsx(f: Fuente, archivo: string, op: OpcionesXlsx = {}): Promise<Intermedio> {
  const t0 = Date.now();
  const z = await Zip.abrir(f, op.limites ?? LIMITES_DEFECTO);
  const avisos = [...z.avisos];
  const maxFilas = op.maxFilas ?? 60;
  const maxColRes = op.maxColumnasResumen ?? 60;
  const nombres = z.nombres();
  if (z.tiene('xl/vbaProject.bin')) avisos.push('macros VBA presentes: NO se ejecutan');
  if (nombres.some((n) => n.startsWith('xl/externalLinks/'))) avisos.push('vínculos a otros libros: NO se siguen (valores en caché)');
  if (z.tiene('xl/connections.xml')) avisos.push('conexiones de datos externas: NO se siguen');
  if (nombres.some((n) => n.startsWith('xl/embeddings/'))) avisos.push('objetos incrustados (OLE) presentes: no se abren');

  const sha = op.sha256 ?? (f.tamano <= 16 * 1024 * 1024 ? await sha256(await f.leer(0, f.tamano)) : null);
  if (!sha) avisos.push('sha256 no calculado (archivo > 16 MB): calcularlo al subir con DigestStream');

  // workbook + rels
  const wb = arbolXml(await z.texto('xl/workbook.xml', 16 << 20));
  const wbRels = await rels(z, 'xl/workbook.xml');
  const fecha1904 = hijo(wb, 'workbookPr')?.a.date1904 === '1' || hijo(wb, 'workbookPr')?.a.date1904 === 'true';
  if (fecha1904) avisos.push('libro con sistema de fechas 1904');
  const nombresDef: Record<string, string> = {};
  for (const d of hijos(hijo(wb, 'definedNames'), 'definedName')) {
    if (d.a.name?.startsWith('_xlnm._FilterDatabase')) continue;
    nombresDef[d.a.localSheetId !== undefined ? `${d.a.name}@${d.a.localSheetId}` : d.a.name] = d.t;
  }

  // sharedStrings (streaming: no se carga el XML entero)
  const sst: string[] = [];
  const parteSst = [...wbRels.values()].find((x) => x.tipo === 'sharedStrings')?.destino ?? 'xl/sharedStrings.xml';
  if (z.tiene(parteSst)) {
    let enSi = false, enT = false, enRph = false, actual = '';
    const tok = new TokenizadorXml({
      abrir(n) { if (n === 'si') { enSi = true; actual = ''; } else if (n === 't' && enSi && !enRph) enT = true; else if (n === 'rPh') enRph = true; },
      cerrar(n) { if (n === 'si') { sst.push(actual); enSi = false; } else if (n === 't') enT = false; else if (n === 'rPh') enRph = false; },
      texto(t) { if (enT) actual += t; },
    });
    await z.streamTexto(parteSst, (s) => { tok.alimentar(s); });
    tok.terminar();
  }

  // estilos → formato numérico por índice de estilo
  const fmtPorEstilo: Array<string | undefined> = [];
  const parteEst = [...wbRels.values()].find((x) => x.tipo === 'styles')?.destino ?? 'xl/styles.xml';
  if (z.tiene(parteEst)) {
    const st = arbolXml(await z.texto(parteEst, 32 << 20));
    const propios = new Map<number, string>();
    for (const nf of hijos(hijo(st, 'numFmts'), 'numFmt')) propios.set(Number(nf.a.numFmtId), nf.a.formatCode);
    for (const xf of hijos(hijo(st, 'cellXfs'), 'xf')) {
      const id = Number(xf.a.numFmtId ?? 0);
      fmtPorEstilo.push(id === 0 ? undefined : propios.get(id) ?? FORMATOS_INTEGRADOS[id]);
    }
  }

  const ricos = await cadenaRichData(z, avisos);
  const cacheImg = new Map<string, { bytes: number; sha?: string; info: ReturnType<typeof infoImagen> }>();
  const metaImagen = async (ruta: string) => {
    let m = cacheImg.get(ruta);
    if (!m) {
      const e = z.entradas.get(ruta);
      if (!e) { m = { bytes: 0, info: { formato: 'falta' } }; }
      else {
        // solo la cabecera para dimensiones; el hash exige leerla entera (≤ 20 MB)
        const leerTodo = op.incluirHashImagenes !== false && e.descomprimido <= 20 * 1024 * 1024;
        const b = leerTodo ? await z.bytes(ruta) : undefined;
        m = { bytes: e.descomprimido, sha: b ? await sha256(b) : undefined, info: b ? infoImagen(b) : { formato: ruta.split('.').pop() ?? '?' } };
      }
      cacheImg.set(ruta, m);
    }
    return m;
  };

  const hojas: Hoja[] = [];
  for (const s of hijos(hijo(wb, 'sheets'), 'sheet')) {
    if (op.hoja && s.a.name !== op.hoja) continue;
    const rid = Object.entries(s.a).find(([k]) => k.endsWith(':id'))?.[1];
    const parte = rid ? wbRels.get(rid)?.destino : undefined;
    if (!parte || !z.tiene(parte)) { avisos.push(`hoja «${s.a.name}» sin parte XML (¿gráfico?)`); continue; }
    hojas.push(await leerHoja(z, parte, s.a.name, (s.a.state as Hoja['estado']) ?? 'visible'));
  }

  async function leerHoja(z: Zip, parte: string, nombre: string, estado: Hoja['estado']): Promise<Hoja> {
    const r = await rels(z, parte);
    const ventana: Rango | null = op.rango ? parsearRango(op.rango) : null;
    const celdas: Record<string, Celda> = {};
    const combinadas: string[] = [];
    const filasOcultas: number[] = [];
    const colsOcultas = new Set<number>();
    const enlaces: Array<{ ref: string; rid?: string; loc?: string }> = [];
    const resumenCols = new Map<number, ResumenColumna>();
    const maestras = new Map<string, { formula: string; fila: number; col: number; celda: string }>();
    let dimension: string | undefined;
    let filasConDatos = 0, nCeldas = 0, nFormulas = 0, nSinCache = 0, ultimaFila = 0, ultimaCol = 0;
    let filasEnVentana = 0, truncada = false;
    let dibujoRid: string | undefined;

    // estado de la celda en curso
    let filaAct = 0, filaTieneDatos = false, filaOculta = false, filaGuardar = false;
    let cRef = '', cT = '', cS = -1, cVm = 0, cF: string | null = null, cFAttr: Record<string, string> = {}, cV: string | null = null, cIs = '';
    let dentroDe = '';
    let colImplicita = 0;

    const guardarFila = (fila: number) => {
      if (ventana) return fila >= ventana.f1 && fila <= ventana.f2;
      return filasEnVentana < maxFilas;
    };

    const tok = new TokenizadorXml({
      abrir(n, a) {
        switch (n) {
          case 'dimension': dimension = a.ref; break;
          case 'col':
            if (a.hidden === '1' || a.hidden === 'true') for (let c = Number(a.min); c <= Math.min(Number(a.max), 16384); c++) colsOcultas.add(c);
            break;
          case 'row':
            filaAct = a.r ? Number(a.r) : filaAct + 1;
            colImplicita = 0;
            filaTieneDatos = false;
            filaOculta = a.hidden === '1' || a.hidden === 'true';
            if (filaOculta) filasOcultas.push(filaAct);
            filaGuardar = guardarFila(filaAct);
            break;
          case 'c':
            colImplicita++;
            cRef = a.r ?? ref(filaAct, colImplicita);
            if (a.r) colImplicita = parsearRef(a.r).col;
            cT = a.t ?? 'n'; cS = a.s ? Number(a.s) : -1; cVm = a.vm ? Number(a.vm) : 0;
            cF = null; cFAttr = {}; cV = null; cIs = '';
            break;
          case 'f': dentroDe = 'f'; cF = ''; cFAttr = a; break;
          case 'v': dentroDe = 'v'; cV = ''; break;
          case 't': if (dentroDe === 'is' || dentroDe === 'ist') dentroDe = 'ist'; break;
          case 'is': dentroDe = 'is'; break;
          case 'mergeCell': if (a.ref) combinadas.push(a.ref); break;
          case 'hyperlink': enlaces.push({ ref: a.ref, rid: Object.entries(a).find(([k]) => k.endsWith(':id'))?.[1], loc: a.location }); break;
          case 'drawing': dibujoRid = Object.entries(a).find(([k]) => k.endsWith(':id'))?.[1]; break;
        }
      },
      texto(t) {
        if (dentroDe === 'f' && cF !== null) cF += t;
        else if (dentroDe === 'v' && cV !== null) cV += t;
        else if (dentroDe === 'ist') cIs += t;
      },
      cerrar(n) {
        if (n === 'f' || n === 'v') { dentroDe = ''; return; }
        if (n === 'is') { dentroDe = ''; return; }
        if (n === 't' && dentroDe === 'ist') { dentroDe = 'is'; return; }
        if (n !== 'c') return;
        // --- celda completa ---
        const { fila, col } = parsearRef(cRef);
        // fórmula compartida
        let formula = cF || undefined;
        let maestra: string | undefined;
        if (cFAttr.t === 'shared' && cFAttr.si !== undefined) {
          if (cF) maestras.set(cFAttr.si, { formula: cF, fila, col, celda: cRef });
          else {
            const m = maestras.get(cFAttr.si);
            if (m) { formula = desplazarFormula(m.formula, fila - m.fila, col - m.col); maestra = m.celda; }
          }
        }
        let valor: Celda['valor'] = null;
        let tipo: Celda['tipo'] = 'n';
        if (cT === 's') { valor = cV !== null ? sst[Number(cV)] ?? null : null; tipo = 's'; }
        else if (cT === 'inlineStr') { valor = cIs; tipo = 's'; }
        else if (cT === 'str') { valor = cV ?? ''; tipo = 's'; }
        else if (cT === 'b') { valor = cV === '1'; tipo = 'b'; }
        else if (cT === 'e') { valor = cV; tipo = 'e'; }
        else if (cT === 'd') { valor = cV; tipo = 'd'; }
        else if (cV !== null && cV !== '') { valor = Number(cV); tipo = 'n'; }
        const tieneFormula = formula !== undefined || cFAttr.t === 'shared' || cFAttr.t === 'array';
        if (tieneFormula && (cV === null || (cV === '' && cT !== 'str'))) { tipo = 'f_sin_cache'; valor = null; nSinCache++; }
        const rico = cVm ? ricos.get(cVm) : undefined;
        if (rico) tipo = 'imagen';
        const vacia = valor === null && !tieneFormula && !rico;
        if (vacia) return;
        nCeldas++;
        if (tieneFormula) nFormulas++;
        if (!filaTieneDatos) { filaTieneDatos = true; filasConDatos++; if (filaGuardar) filasEnVentana++; }
        if (fila > ultimaFila) ultimaFila = fila;
        if (col > ultimaCol) ultimaCol = col;
        if (col <= maxColRes) {
          let rc = resumenCols.get(col);
          if (!rc) { rc = { col: colALetra(col), numeros: 0, textos: 0, vacias: 0, formulas: 0 }; resumenCols.set(col, rc); }
          if (typeof valor === 'number') rc.numeros++; else if (valor !== null) rc.textos++;
          if (tieneFormula) rc.formulas++;
        }
        const guardar = ventana ? dentro(ventana, fila, col) : filaGuardar;
        if (!guardar) { if (!ventana && !filaGuardar) truncada = true; return; }
        const c: Celda = { valor, tipo };
        if (formula) c.formula = formula.startsWith('=') ? formula : `=${formula}`;
        if (maestra) c.formula_compartida_de = maestra;
        const fmt = cS >= 0 ? fmtPorEstilo[cS] : undefined;
        if (fmt && fmt !== 'General' && fmt !== '@') {
          c.formato = fmt;
          const cl = claseFormato(fmt);
          if (cl) c.clase_formato = cl;
          if (cl === 'fecha' && typeof valor === 'number') { c.valor = serialAFecha(fecha1904 ? valor + 1462 : valor); c.tipo = 'd'; }
        }
        if (typeof c.valor === 'string' && c.tipo === 's') {
          if (/[$]|B\/\.|USD|PAB|balboa/i.test(c.valor)) {
            const p = preciosEnTexto(c.valor);
            if (p.precios.length) c.precios = p;
          }
          if (sospechaInstruccion(c.valor)) c.sospecha_instruccion = true;
        }
        if (filaOculta || colsOcultas.has(col)) c.oculta = true;
        celdas[cRef] = c;
        if (rico) { c.valor = null; (c as Celda & { _rico?: ValorRico })._rico = rico; }
      },
    });
    await z.streamTexto(parte, (s) => { tok.alimentar(s); });
    tok.terminar();
    if (!ventana && filasConDatos > filasEnVentana) truncada = true;

    // combinadas: marcar ancla y cubiertas (solo dentro de la ventana guardada)
    for (const cr of combinadas) {
      const g = parsearRango(cr);
      const ancla = ref(g.f1, g.c1);
      if (celdas[ancla]) celdas[ancla].combina = cr;
      for (let fi = g.f1; fi <= g.f2; fi++) for (let co = g.c1; co <= g.c2; co++) {
        const k = ref(fi, co);
        if (k === ancla) continue;
        const enVentana = ventana ? dentro(ventana, fi, co) : Object.prototype.hasOwnProperty.call(celdas, ancla);
        if (!enVentana) continue;
        celdas[k] = { ...(celdas[k] ?? { valor: null, tipo: 's' as const }), combinada_en: ancla };
      }
    }
    // comentarios y enlaces
    const coms = await comentarios(z, r);
    for (const [k, t] of coms) {
      if (!celdas[k]) continue;
      celdas[k].comentario = t;
      if (sospechaInstruccion(t)) celdas[k].sospecha_instruccion = true;
    }
    for (const e of enlaces) {
      const destino = e.rid ? r.get(e.rid)?.destino : e.loc;
      if (destino && celdas[e.ref]) celdas[e.ref].enlace = destino;
    }
    // imágenes
    const imagenes: ImagenXlsx[] = [];
    let cuadros: Hoja['cuadros_texto'] = [];
    const dib = dibujoRid ? r.get(dibujoRid) : undefined;
    if (dib) {
      const { imgs, textos } = await imagenesFlotantes(z, dib.destino);
      cuadros = textos;
      for (const im of imgs) {
        const m = await metaImagen(im.ruta);
        imagenes.push({ id: (m.sha ?? im.ruta).slice(0, 16), ...im, bytes: m.bytes, sha256: m.sha, formato: m.info.formato, ancho: m.info.ancho, alto: m.info.alto,
          ...(sospechaInstruccion(im.alt) ? { sospecha_instruccion: true as const } : {}) });
      }
    }
    for (const [k, c] of Object.entries(celdas)) {
      const rico = (c as Celda & { _rico?: ValorRico })._rico;
      if (!rico) continue;
      delete (c as Celda & { _rico?: ValorRico })._rico;
      if (rico.ruta) {
        const m = await metaImagen(rico.ruta);
        const id = (m.sha ?? rico.ruta).slice(0, 16);
        c.imagen = id;
        imagenes.push({ id, tipo: 'en_celda', celda: k, ruta: rico.ruta, bytes: m.bytes, sha256: m.sha, formato: m.info.formato, ancho: m.info.ancho, alto: m.info.alto,
          ...(rico.alt ? { alt: rico.alt } : {}), ...(rico.calcOrigin !== undefined ? { calc_origin: rico.calcOrigin } : {}),
          ...(sospechaInstruccion(rico.alt) ? { sospecha_instruccion: true as const } : {}) });
      } else if (rico.web) {
        c.enlace = rico.web;
        c.valor = '[imagen web]';
      }
    }
    const hoja: Hoja = {
      nombre, estado, dimension,
      resumen: {
        filas_con_datos: filasConDatos, celdas: nCeldas, formulas: nFormulas, formulas_sin_cache: nSinCache,
        ultima_fila: ultimaFila, ultima_columna: colALetra(ultimaCol),
        columnas: [...resumenCols.values()].sort((a, b) => a.col.length - b.col.length || a.col.localeCompare(b.col))
          .map((c) => ({ ...c, vacias: Math.max(0, filasConDatos - c.numeros - c.textos) })),
      },
      combinadas, filas_ocultas: filasOcultas, columnas_ocultas: [...colsOcultas].slice(0, 200).map(colALetra),
      imagenes, cuadros_texto: cuadros,
      ventana: { rango: ventana ? rangoATexto(ventana) : null, filas: filasEnVentana, truncada },
      celdas, tablas: [],
    };
    hoja.tablas = detectarTablas(hoja);
    return hoja;
  }

  return {
    esquema: ESQUEMA, archivo, tipo: z.tiene('xl/vbaProject.bin') ? 'xlsm' : 'xlsx', bytes: f.tamano, sha256: sha,
    avisos, nombres_definidos: nombresDef, hojas, estadisticas: { ms: Date.now() - t0 },
  };
}
