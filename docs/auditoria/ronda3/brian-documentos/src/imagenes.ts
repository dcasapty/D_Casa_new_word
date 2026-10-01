/** Metadatos de imagen SIN decodificar píxeles (formato, ancho, alto) y hash SHA-256. */

export interface InfoImagen { formato: string; ancho?: number; alto?: number }

export function infoImagen(b: Uint8Array): InfoImagen {
  const dv = new DataView(b.buffer, b.byteOffset, b.byteLength);
  if (b.length > 24 && b[0] === 0x89 && b[1] === 0x50 && b[2] === 0x4e && b[3] === 0x47) {
    return { formato: 'png', ancho: dv.getUint32(16), alto: dv.getUint32(20) };
  }
  if (b.length > 4 && b[0] === 0xff && b[1] === 0xd8) {
    let p = 2;
    while (p + 9 < b.length) {
      if (b[p] !== 0xff) { p++; continue; }
      const m = b[p + 1];
      const largo = dv.getUint16(p + 2);
      if ((m >= 0xc0 && m <= 0xc3) || (m >= 0xc5 && m <= 0xc7) || (m >= 0xc9 && m <= 0xcb) || (m >= 0xcd && m <= 0xcf)) {
        return { formato: 'jpeg', alto: dv.getUint16(p + 5), ancho: dv.getUint16(p + 7) };
      }
      p += 2 + largo;
    }
    return { formato: 'jpeg' };
  }
  if (b.length > 10 && b[0] === 0x47 && b[1] === 0x49 && b[2] === 0x46) {
    return { formato: 'gif', ancho: dv.getUint16(6, true), alto: dv.getUint16(8, true) };
  }
  if (b.length > 30 && String.fromCharCode(...b.subarray(8, 12)) === 'WEBP') {
    const tipo = String.fromCharCode(...b.subarray(12, 16));
    if (tipo === 'VP8X') return { formato: 'webp', ancho: 1 + (b[24] | (b[25] << 8) | (b[26] << 16)), alto: 1 + (b[27] | (b[28] << 8) | (b[29] << 16)) };
    if (tipo === 'VP8 ') return { formato: 'webp', ancho: dv.getUint16(26, true) & 0x3fff, alto: dv.getUint16(28, true) & 0x3fff };
    if (tipo === 'VP8L') {
      const v = dv.getUint32(21, true);
      return { formato: 'webp', ancho: (v & 0x3fff) + 1, alto: ((v >> 14) & 0x3fff) + 1 };
    }
    return { formato: 'webp' };
  }
  if (b.length > 26 && b[0] === 0x42 && b[1] === 0x4d) return { formato: 'bmp', ancho: dv.getInt32(18, true), alto: Math.abs(dv.getInt32(22, true)) };
  const s = String.fromCharCode(...b.subarray(0, Math.min(b.length, 8)));
  if (s.startsWith('×ÍÆ\u009a') || s.includes('EMF')) return { formato: 'emf' };
  return { formato: 'desconocido' };
}

export async function sha256(b: Uint8Array): Promise<string> {
  const h = new Uint8Array(await crypto.subtle.digest('SHA-256', b));
  return Array.from(h, (x) => x.toString(16).padStart(2, '0')).join('');
}

/**
 * Tokens visuales estimados para Claude: ⌈ancho/28⌉×⌈alto/28⌉ tras escalar al lado largo
 * máximo del nivel (1568 px estándar; 2576 px alta resolución). Fórmula de la documentación de
 * visión de Claude (ver informe §8); es una ESTIMACIÓN: el conteo real lo da count_tokens.
 */
export function tokensVision(ancho: number, alto: number, ladoMax = 1568, tope = 1568): number {
  const k = Math.min(1, ladoMax / Math.max(ancho, alto));
  const w = Math.round(ancho * k), h = Math.round(alto * k);
  return Math.min(tope, Math.ceil(w / 28) * Math.ceil(h / 28));
}
