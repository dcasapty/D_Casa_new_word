/**
 * Tokenizador XML en streaming, mínimo y defensivo (sin dependencias; corre en Workers).
 *
 * - Acepta trozos de texto (`alimentar`) y emite eventos de apertura, cierre y texto.
 * - NO procesa DTD: cualquier `<!DOCTYPE` o `<!ENTITY` aborta (defensa contra XXE y
 *   «billion laughs»). OOXML válido nunca lleva DTD.
 * - Entidades: solo las 5 predefinidas y referencias numéricas.
 * - Límites: longitud máxima de una etiqueta y de un nodo de texto (evita que un archivo
 *   malicioso haga crecer el búfer sin fin).
 * - Los nombres se entregan sin prefijo de espacio de nombres («x:c» → «c»): en OOXML los
 *   prefijos varían entre productores (Excel, LibreOffice, openpyxl).
 */

export type Atributos = Record<string, string>;

export interface Manejador {
  abrir?(nombre: string, atr: Atributos, vacia: boolean): void;
  cerrar?(nombre: string): void;
  texto?(t: string): void;
}

export class ErrorXml extends Error {}

const MAX_ETIQUETA = 64 * 1024;
const MAX_TEXTO = 4 * 1024 * 1024;

const ENTIDADES: Record<string, string> = { lt: '<', gt: '>', amp: '&', quot: '"', apos: "'" };

export function decodificarEntidades(s: string): string {
  if (s.indexOf('&') < 0) return s;
  return s.replace(/&(#x[0-9a-fA-F]+|#[0-9]+|[a-zA-Z]+);/g, (m, e: string) => {
    if (e[0] === '#') {
      const n = e[1] === 'x' || e[1] === 'X' ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10);
      return Number.isFinite(n) && n >= 0 && n <= 0x10ffff ? String.fromCodePoint(n) : '';
    }
    const v = ENTIDADES[e];
    if (v === undefined) throw new ErrorXml(`entidad no permitida: ${m}`);
    return v;
  });
}

/** Quita el prefijo de espacio de nombres. */
export function local(nombre: string): string {
  const i = nombre.indexOf(':');
  return i < 0 ? nombre : nombre.slice(i + 1);
}

const RE_ATR = /([^\s=/>]+)\s*=\s*("([^"]*)"|'([^']*)')/g;

function atributos(s: string): Atributos {
  const out: Atributos = {};
  RE_ATR.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = RE_ATR.exec(s))) {
    out[m[1]] = decodificarEntidades(m[3] ?? m[4] ?? '');
  }
  return out;
}

export class TokenizadorXml {
  private buf = '';
  private textoPend = '';
  constructor(private m: Manejador) {}

  alimentar(trozo: string): void {
    this.buf += trozo;
    this.procesar(false);
  }

  terminar(): void {
    this.procesar(true);
    if (this.buf.trim()) throw new ErrorXml('XML truncado');
  }

  private emitirTexto(t: string) {
    this.textoPend += t;
    if (this.textoPend.length > MAX_TEXTO) throw new ErrorXml('nodo de texto demasiado grande');
  }

  private vaciarTexto() {
    if (this.textoPend && this.m.texto) this.m.texto(decodificarEntidades(this.textoPend));
    this.textoPend = '';
  }

  private procesar(fin: boolean) {
    let i = 0;
    const b = this.buf;
    const n = b.length;
    while (i < n) {
      const lt = b.indexOf('<', i);
      if (lt < 0) {
        this.emitirTexto(b.slice(i));
        i = n;
        break;
      }
      if (lt > i) this.emitirTexto(b.slice(i, lt));
      // ¿Qué tipo de marca?
      if (b.startsWith('<![CDATA[', lt)) {
        const f = b.indexOf(']]>', lt + 9);
        if (f < 0) { i = lt; break; }
        // CDATA: texto literal (sin entidades): se escapa & para que vaciarTexto no lo decodifique
        this.emitirTexto(b.slice(lt + 9, f).replace(/&/g, '&amp;'));
        i = f + 3;
        continue;
      }
      if (b.startsWith('<!--', lt)) {
        const f = b.indexOf('-->', lt + 4);
        if (f < 0) { i = lt; break; }
        i = f + 3;
        continue;
      }
      if (b.startsWith('<!', lt)) {
        // DOCTYPE / ENTITY / cualquier declaración: prohibido
        if (n - lt >= 9 || fin) throw new ErrorXml('DTD/declaración no permitida en OOXML');
        i = lt;
        break;
      }
      if (b.startsWith('<?', lt)) {
        const f = b.indexOf('?>', lt + 2);
        if (f < 0) { i = lt; break; }
        i = f + 2;
        continue;
      }
      // etiqueta normal: buscar '>' fuera de comillas
      let j = lt + 1;
      let comilla = '';
      for (; j < n; j++) {
        const c = b[j];
        if (comilla) { if (c === comilla) comilla = ''; }
        else if (c === '"' || c === "'") comilla = c;
        else if (c === '>') break;
      }
      if (j >= n) {
        if (n - lt > MAX_ETIQUETA) throw new ErrorXml('etiqueta demasiado larga');
        i = lt;
        break;
      }
      this.vaciarTexto();
      const cuerpo = b.slice(lt + 1, j);
      if (cuerpo[0] === '/') {
        this.m.cerrar?.(local(cuerpo.slice(1).trim()));
      } else {
        const vacia = cuerpo.endsWith('/');
        const sin = vacia ? cuerpo.slice(0, -1) : cuerpo;
        const k = sin.search(/[\s]/);
        const nombre = local(k < 0 ? sin : sin.slice(0, k));
        this.m.abrir?.(nombre, k < 0 ? {} : atributos(sin.slice(k)), vacia);
        if (vacia) this.m.cerrar?.(nombre);
      }
      i = j + 1;
    }
    this.buf = b.slice(i);
    if (fin) this.vaciarTexto();
  }
}

/** Utilidad para XML pequeños (workbook, rels, styles…): parsea todo de una vez. */
export function parsearXml(texto: string, m: Manejador): void {
  const t = new TokenizadorXml(m);
  t.alimentar(texto);
  t.terminar();
}

/** Árbol simple para partes pequeñas (≤ unos MB). */
export interface Nodo { n: string; a: Atributos; h: Nodo[]; t: string }

export function arbolXml(texto: string): Nodo {
  const raiz: Nodo = { n: '#raiz', a: {}, h: [], t: '' };
  const pila: Nodo[] = [raiz];
  parsearXml(texto, {
    abrir(n, a) { const nodo = { n, a, h: [], t: '' }; pila[pila.length - 1].h.push(nodo); pila.push(nodo); },
    cerrar() { pila.pop(); },
    texto(t) { pila[pila.length - 1].t += t; },
  });
  return raiz.h[0] ?? raiz;
}

export function hijos(n: Nodo | undefined, nombre: string): Nodo[] {
  return n ? n.h.filter((x) => x.n === nombre) : [];
}

export function hijo(n: Nodo | undefined, nombre: string): Nodo | undefined {
  return n?.h.find((x) => x.n === nombre);
}

export function* recorrer(n: Nodo): Generator<Nodo> {
  yield n;
  for (const h of n.h) yield* recorrer(h);
}

export function textoTotal(n: Nodo): string {
  let s = n.t;
  for (const h of n.h) s += textoTotal(h);
  return s;
}
