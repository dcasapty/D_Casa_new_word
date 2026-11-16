// Notas de voz de mentira con la forma de lo que graba un navegador: contenedores válidos (el Ogg con su CRC) y paquetes Opus de
// verdad en su TOC (20 ms cada uno), o tramas AAC contadas en el MP4. El «audio» es relleno: no se decodifica, se mide.

const texto = (s: string) => [...s].map((c) => c.charCodeAt(0));
const u32be = (n: number) => [(n >>> 24) & 0xff, (n >>> 16) & 0xff, (n >>> 8) & 0xff, n & 0xff];
const u16be = (n: number) => [(n >> 8) & 0xff, n & 0xff];

/** Un paquete Opus de 20 ms (TOC 0xFC: CELT banda completa, 20 ms, una trama) con dos bytes de relleno. */
export const PAQUETE_20MS = [0xfc, 0x11, 0x22];
const PRESKIP = 312;

// ── Ogg ─────────────────────────────────────────────────────────────────────────────────────────────
const TABLA = (() => {
  const t = new Uint32Array(256);
  for (let i = 0; i < 256; i++) {
    let r = i << 24;
    for (let k = 0; k < 8; k++) r = r & 0x80000000 ? (r << 1) ^ 0x04c11db7 : r << 1;
    t[i] = r >>> 0;
  }
  return t;
})();
function crc(b: Uint8Array): number {
  let c = 0;
  for (const x of b) c = ((c << 8) ^ TABLA[((c >>> 24) ^ x) & 0xff]) >>> 0;
  return c >>> 0;
}

/** Una página Ogg con su CRC. `tipo`: 2 = abre el flujo, 4 = lo cierra, 1 = continúa un paquete. */
export function paginaOgg(paquetes: number[][], granulo: number, seq: number, tipo = 0, op: { serie?: number; crcMalo?: boolean } = {}): Uint8Array {
  const lacing: number[] = [];
  for (const p of paquetes) {
    for (let n = p.length; n >= 255; n -= 255) lacing.push(255);
    lacing.push(p.length % 255);
  }
  const cuerpo = paquetes.flat();
  const out = new Uint8Array(27 + lacing.length + cuerpo.length);
  const v = new DataView(out.buffer);
  out.set([0x4f, 0x67, 0x67, 0x53, 0, tipo]);
  v.setBigInt64(6, BigInt(granulo), true);
  v.setUint32(14, op.serie ?? 0x1234, true);
  v.setUint32(18, seq, true);
  out[26] = lacing.length;
  out.set(lacing, 27);
  out.set(cuerpo, 27 + lacing.length);
  v.setUint32(22, (crc(out) ^ (op.crcMalo ? 1 : 0)) >>> 0, true);
  return out;
}

const unir = (partes: Uint8Array[]) => {
  const total = partes.reduce((n, p) => n + p.length, 0);
  const b = new Uint8Array(total);
  let pos = 0;
  for (const p of partes) {
    b.set(p, pos);
    pos += p.length;
  }
  return b;
};

/** Cuántos paquetes de 20 ms hacen `segundos` decodificados (con el pre-skip descontado). */
const paquetesOgg = (segundos: number) => Math.max(0, Math.round((segundos + PRESKIP / 48_000) / 0.02));

/**
 * Ogg Opus de `segundos` de verdad, en paquetes de 20 ms (hasta 255 por página). `mentir`: la última página dice otra duración
 * (lo que mide de verdad no cambia). `relleno`: bytes de más dentro de cada paquete (para hacerlo pesar más sin durar más).
 */
export function oggOpus(segundos: number, op: { mentir?: number; relleno?: number } = {}): Uint8Array {
  const cabeza = [...texto("OpusHead"), 1, 1, PRESKIP & 0xff, PRESKIP >> 8, 0x80, 0xbb, 0, 0, 0, 0, 0];
  const etiquetas = [...texto("OpusTags"), 4, 0, 0, 0, ...texto("dcas"), 0, 0, 0, 0];
  const partes = [paginaOgg([cabeza], 0, 0, 2), paginaOgg([etiquetas], 0, 1)];
  const paquete = [...PAQUETE_20MS, ...new Array(op.relleno ?? 0).fill(0x33)];
  let quedan = paquetesOgg(segundos);
  let granulo = 0;
  let seq = 2;
  while (quedan > 0) {
    const n = Math.min(255, quedan);
    quedan -= n;
    granulo += n * 960;
    const ultima = quedan === 0;
    const g = ultima && op.mentir !== undefined ? Math.round(op.mentir * 48_000) + PRESKIP : granulo;
    partes.push(paginaOgg(new Array(n).fill(paquete), g, seq++, ultima ? 4 : 0));
  }
  return unir(partes);
}

// ── WebM ────────────────────────────────────────────────────────────────────────────────────────────
const tam = (n: number) => (n < 127 ? [0x80 | n] : [0x40 | (n >> 8), n & 0xff]);
const elemento = (id: number[], datos: number[]) => [...id, ...tam(datos.length), ...datos];
const DESCONOCIDO = [0x01, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff];

/**
 * WebM como el de MediaRecorder de Chrome: segmento y clusters de tamaño desconocido, una pista `A_OPUS` y un paquete de 20 ms por
 * bloque. `conDuracion`: una «Duration» en Info (mentirosa o no: no se le cree). `codec`, `pistas`, `lacing`: para probar lo que no
 * se puede medir.
 */
export function webmOpus(segundos: number, op: { conDuracion?: number; codec?: string; pistas?: number; lacing?: boolean; paquete?: number[] } = {}): Uint8Array {
  const ebml = elemento([0x1a, 0x45, 0xdf, 0xa3], elemento([0x42, 0x82], texto("webm")));
  const escala = elemento([0x2a, 0xd7, 0xb1], [0x0f, 0x42, 0x40]);
  const duracion: number[] = [];
  if (op.conDuracion !== undefined) {
    const f = new Uint8Array(8);
    new DataView(f.buffer).setFloat64(0, op.conDuracion * 1000, false);
    duracion.push(...elemento([0x44, 0x89], [...f]));
  }
  const info = elemento([0x15, 0x49, 0xa9, 0x66], [...escala, ...duracion]);
  const pista = (n: number) => elemento([0xae], [...elemento([0xd7], [n]), ...elemento([0x86], texto(op.codec ?? "A_OPUS"))]);
  const pistas = elemento([0x16, 0x54, 0xae, 0x6b], Array.from({ length: op.pistas ?? 1 }, (_, i) => pista(i + 1)).flat());
  const paquete = op.paquete ?? PAQUETE_20MS;
  const bloque = (rel: number) => elemento([0xa3], [0x81, ...u16be(rel), op.lacing ? 0x82 : 0x80, ...paquete]);
  const total = Math.round(segundos / 0.02);
  const clusters: number[] = [];
  for (let i = 0; i < total; i++) {
    if (i % 1000 === 0) clusters.push(0x1f, 0x43, 0xb6, 0x75, ...DESCONOCIDO, ...elemento([0xe7], u32be(i * 20)));
    clusters.push(...bloque((i % 1000) * 20));
  }
  return new Uint8Array([...ebml, 0x18, 0x53, 0x80, 0x67, ...DESCONOCIDO, ...info, ...pistas, ...clusters]);
}

// ── MP4 (AAC) ───────────────────────────────────────────────────────────────────────────────────────
const caja = (tipo: string, ...datos: number[][]) => {
  const cuerpo = datos.flat();
  return [...u32be(8 + cuerpo.length), ...texto(tipo), ...cuerpo];
};
const llena = (tipo: string, ...datos: number[][]) => caja(tipo, [0, 0, 0, 0], ...datos);

/**
 * MP4 con una pista AAC-LC a 48 kHz de `segundos` (una muestra = una trama de 1024). `fragmentos`: como Safari, las muestras van en
 * `moof/trun` (y `stsz` vacío). `edicionesRepetidas`: una lista de edición de dos entradas (podría repetir el audio). `codec`: otro
 * tipo de muestra (p. ej. «Opus»). `mentir`: la duración que dice `mvhd` (no se le cree).
 */
export function mp4(segundos: number, op: { fragmentos?: boolean; edicionesRepetidas?: boolean; codec?: string; mentir?: number } = {}): Uint8Array {
  const muestras = Math.round((segundos * 48_000) / 1024);
  const ftyp = caja("ftyp", texto("M4A "), [0, 0, 0, 0], texto("isom"));
  const mvhd = llena("mvhd", u32be(0), u32be(0), u32be(1000), u32be(Math.round((op.mentir ?? segundos) * 1000)), new Array(80).fill(0));
  const esds = llena(
    "esds",
    [0x03, 25, 0, 1, 0],
    [0x04, 17, 0x40, 0x15, 0, 0, 0, ...u32be(64000), ...u32be(64000)],
    [0x05, 2, 0x11, 0x88],
    [0x06, 1, 0x02],
  );
  const entrada = caja(op.codec ?? "mp4a", [0, 0, 0, 0, 0, 0, 0, 1], [0, 0, 0, 0, 0, 0, 0, 0], [0, 1, 0, 16, 0, 0, 0, 0], u32be(48000 << 16 >>> 0), esds);
  const stsd = llena("stsd", u32be(1), entrada);
  const stsz = llena("stsz", u32be(10), u32be(op.fragmentos ? 0 : muestras));
  const stbl = caja("stbl", stsd, stsz);
  const hdlr = llena("hdlr", u32be(0), texto("soun"), new Array(12).fill(0), [0]);
  const mdia = caja("mdia", llena("mdhd", new Array(20).fill(0)), hdlr, caja("minf", stbl));
  const edts = op.edicionesRepetidas ? [caja("edts", llena("elst", u32be(2), new Array(24).fill(0)))] : [];
  const trak = caja("trak", ...edts, mdia);
  const moov = caja("moov", mvhd, trak, ...(op.fragmentos ? [caja("mvex", llena("trex", new Array(20).fill(0)))] : []));
  const partes = [ftyp, moov];
  if (op.fragmentos) {
    for (let hechas = 0; hechas < muestras; hechas += 200) {
      const n = Math.min(200, muestras - hechas);
      partes.push(caja("moof", llena("mfhd", u32be(1)), caja("traf", llena("tfhd", u32be(1)), llena("trun", u32be(n)))));
      partes.push(caja("mdat", new Array(n * 10).fill(0x11)));
    }
  } else {
    partes.push(caja("mdat", new Array(muestras * 10).fill(0x11)));
  }
  return new Uint8Array(partes.flat());
}

/** Base64 de unos bytes (para el cuerpo de `/odoo/voz`). */
export function aBase64(b: Uint8Array): string {
  let bin = "";
  for (let i = 0; i < b.length; i += 0x8000) bin += String.fromCharCode(...b.subarray(i, i + 0x8000));
  return btoa(bin);
}
