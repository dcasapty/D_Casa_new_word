/**
 * Fuente de bytes con acceso aleatorio. El lector de zip solo pide rangos, así que el archivo
 * completo NUNCA tiene que estar en memoria: en Cloudflare la fuente es un objeto de R2 leído
 * con `get(clave, { range })`; en pruebas, un archivo o un Uint8Array.
 */
export interface Fuente {
  readonly tamano: number;
  leer(desde: number, largo: number): Promise<Uint8Array>;
}

export function fuenteDeBytes(b: Uint8Array): Fuente {
  return {
    tamano: b.length,
    async leer(desde, largo) {
      return b.subarray(desde, Math.min(b.length, desde + largo));
    },
  };
}

/** Interfaz mínima de un bucket R2 (para no depender de @cloudflare/workers-types). */
export interface BucketR2 {
  head(clave: string): Promise<{ size: number } | null>;
  get(clave: string, op?: { range?: { offset: number; length: number } }):
    Promise<{ arrayBuffer(): Promise<ArrayBuffer> } | null>;
}

/** Fuente sobre R2: cada `leer` es una petición con rango (operación clase B). */
export async function fuenteR2(bucket: BucketR2, clave: string): Promise<Fuente> {
  const h = await bucket.head(clave);
  if (!h) throw new Error(`no existe en R2: ${clave}`);
  return {
    tamano: h.size,
    async leer(desde, largo) {
      const o = await bucket.get(clave, { range: { offset: desde, length: largo } });
      if (!o) throw new Error(`R2 no devolvió el rango ${desde}+${largo}`);
      return new Uint8Array(await o.arrayBuffer());
    },
  };
}

/** Envuelve una fuente con una caché de bloques (reduce peticiones a R2 al leer cabeceras). */
export function conCache(f: Fuente, bloque = 256 * 1024, maxBloques = 8): Fuente {
  const cache = new Map<number, Uint8Array>();
  async function bloqueN(n: number) {
    let b = cache.get(n);
    if (!b) {
      b = await f.leer(n * bloque, bloque);
      cache.set(n, b);
      if (cache.size > maxBloques) cache.delete(cache.keys().next().value as number);
    }
    return b;
  }
  return {
    tamano: f.tamano,
    async leer(desde, largo) {
      if (largo > bloque * 2) return f.leer(desde, largo);
      const fin = Math.min(f.tamano, desde + largo);
      const out = new Uint8Array(fin - desde);
      let p = desde;
      while (p < fin) {
        const n = Math.floor(p / bloque);
        const b = await bloqueN(n);
        const ini = p - n * bloque;
        const k = Math.min(b.length - ini, fin - p);
        out.set(b.subarray(ini, ini + k), p - desde);
        p += k;
      }
      return out;
    },
  };
}
