// Notas de voz de mentira con la forma de lo que graba un navegador (solo las cabeceras que importan; el «audio» es relleno).

const texto = (s: string) => [...s].map((c) => c.charCodeAt(0));
const u32be = (n: number) => [(n >>> 24) & 0xff, (n >>> 16) & 0xff, (n >>> 8) & 0xff, n & 0xff];
const u16be = (n: number) => [(n >> 8) & 0xff, n & 0xff];
const i64le = (n: number) => {
  const b = new Uint8Array(8);
  new DataView(b.buffer).setBigInt64(0, BigInt(n), true);
  return [...b];
};

/** Ogg Opus de `segundos`: la página de «OpusHead» (pre-skip 312) y la última con su posición a 48 kHz, con `relleno` bytes en medio. */
export function oggOpus(segundos: number, relleno = 2000): Uint8Array {
  const pagina = (tipo: number, granulo: number, datos: number[]) => [...texto("OggS"), 0, tipo, ...i64le(granulo), 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, datos.length, ...datos];
  const cabeza = [...texto("OpusHead"), 1, 1, 0x38, 0x01, 0x80, 0xbb, 0, 0, 0, 0, 0];
  const medio = new Array(relleno).fill(0x5a);
  const ultima = pagina(4, 312 + Math.round(segundos * 48_000), [1, 2, 3]);
  return new Uint8Array([...pagina(2, 0, cabeza), ...medio, ...ultima]);
}

/** WebM como el de MediaRecorder de Chrome: segmento y clusters de tamaño desconocido, sin «Duration»; el último bloque en `segundos`. */
export function webmOpus(segundos: number, op: { conDuracion?: number } = {}): Uint8Array {
  const desconocido = [0x01, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff];
  const ebml = [0x1a, 0x45, 0xdf, 0xa3, 0x84, 0x42, 0x86, 0x81, 0x01];
  const escala = [0x2a, 0xd7, 0xb1, 0x83, 0x0f, 0x42, 0x40];
  const duracion: number[] = [];
  if (op.conDuracion !== undefined) {
    const f = new Uint8Array(8);
    new DataView(f.buffer).setFloat64(0, op.conDuracion * 1000, false);
    duracion.push(0x44, 0x89, 0x88, ...f);
  }
  const info = [0x15, 0x49, 0xa9, 0x66, 0x80 | (escala.length + duracion.length), ...escala, ...duracion];
  const bloque = (rel: number) => [0xa3, 0x80 | 24, 0x81, ...u16be(rel), 0x80, ...new Array(20).fill(0x33)];
  const total = Math.round(segundos * 1000);
  const clusters: number[] = [];
  for (let base = 0; base <= total; base += 30_000) {
    clusters.push(0x1f, 0x43, 0xb6, 0x75, ...desconocido, 0xe7, 0x84, ...u32be(base));
    for (let rel = 0; base + rel <= total && rel < 30_000; rel += 5_000) clusters.push(...bloque(Math.min(rel, total - base)));
    if (total - base < 30_000 && (total - base) % 5000 !== 0) clusters.push(...bloque(total - base));
  }
  return new Uint8Array([...ebml, 0x18, 0x53, 0x80, 0x67, ...desconocido, ...info, ...clusters]);
}

/** MP4 con la duración en «mvhd» (versión 0, escala 1000); `segundos` 0 = por fragmentos (sin duración, como Safari). */
export function mp4(segundos: number): Uint8Array {
  const ftyp = [...u32be(16), ...texto("ftyp"), ...texto("M4A "), 0, 0, 0, 0];
  const cuerpoMvhd = [0, 0, 0, 0, ...u32be(0), ...u32be(0), ...u32be(1000), ...u32be(Math.round(segundos * 1000)), ...new Array(80).fill(0)];
  const mvhd = [...u32be(8 + cuerpoMvhd.length), ...texto("mvhd"), ...cuerpoMvhd];
  const moov = [...u32be(8 + mvhd.length), ...texto("moov"), ...mvhd];
  const mdat = [...u32be(8 + 500), ...texto("mdat"), ...new Array(500).fill(0x11)];
  return new Uint8Array([...ftyp, ...moov, ...mdat]);
}

/** Base64 de unos bytes (para el cuerpo de `/odoo/voz`). */
export function aBase64(b: Uint8Array): string {
  let bin = "";
  for (const x of b) bin += String.fromCharCode(x);
  return btoa(bin);
}
