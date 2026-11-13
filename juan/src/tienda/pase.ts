// El pase de Brian de la tienda (contrato §1 y §2; precisiones en docs/JUAN.md › «Brian de la tienda»).
//
// Odoo lo entrega en `POST /dcasa/brian/v1/pase` y el navegador lo trae en `Authorization: Pase <pase>`:
//   pase  = base64url(payload) "." base64url(firma)
//   llave = HMAC-SHA256(JUAN_WORKER_TOKEN, "brian-tienda-pase-v1")          (los 32 bytes crudos)
//   firma = HMAC-SHA256(llave, <el texto base64url del payload>)
//   payload = {v: 1, sid, exp, red?, sitio}
//
// Sin secretos nuevos: la llave sale del token que Odoo y el Worker ya comparten. Se comprueban la firma (en tiempo constante), el
// vencimiento y el `sid`. La `red` del pase NO se compara con la conexión (decisión del coordinador, 2026-11-13): el navegador puede
// llegar a dcasapty.com por IPv6 y al Worker por IPv4, y todo pase daría 401. El abuso lo frenan los 30 minutos del pase, el tope de
// pases por red de Odoo y los topes del Worker (por sesión, por red de la conexión —`llaveDeRed`— y por día).

const codificador = new TextEncoder();

export const CONTEXTO_DE_LA_LLAVE = "brian-tienda-pase-v1";
/** Un pase vive 30 minutos (Odoo); más de una hora es un pase mal hecho. */
export const VIDA_MAXIMA_S = 3600;
const LARGO_MAXIMO = 1024;

export interface Pase {
  sid: string;
  /** Epoch en segundos. */
  exp: number;
  /** La red que vio Odoo, si la trae: informativa, no se compara con la conexión. */
  red: string | null;
  sitio: number;
}

export type MotivoDePase = "sin_token" | "falta" | "forma" | "firma" | "vencido";

export type ResultadoPase = { ok: true; pase: Pase } | { ok: false; motivo: MotivoDePase };

// ── base64url ────────────────────────────────────────────────────────────────

export function aBase64Url(bytes: Uint8Array): string {
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function deBase64Url(texto: string): Uint8Array | null {
  if (!/^[A-Za-z0-9_-]+={0,2}$/.test(texto)) return null;
  const limpio = texto.replace(/=+$/, "").replace(/-/g, "+").replace(/_/g, "/");
  if (limpio.length % 4 === 1) return null;
  try {
    const bin = atob(limpio + "=".repeat((4 - (limpio.length % 4)) % 4));
    return Uint8Array.from(bin, (c) => c.charCodeAt(0));
  } catch {
    return null;
  }
}

// ── La llave y la firma ──────────────────────────────────────────────────────

async function hmac(llave: Uint8Array, mensaje: string): Promise<Uint8Array> {
  const k = await crypto.subtle.importKey("raw", llave, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return new Uint8Array(await crypto.subtle.sign("HMAC", k, codificador.encode(mensaje)));
}

const llaves = new Map<string, Promise<Uint8Array>>();

/** La llave del pase (32 bytes), derivada del token compartido con Odoo. Se calcula una vez por token. */
export function llaveDelPase(token: string): Promise<Uint8Array> {
  let l = llaves.get(token);
  if (!l) {
    l = hmac(codificador.encode(token), CONTEXTO_DE_LA_LLAVE);
    if (llaves.size > 4) llaves.clear();
    llaves.set(token, l);
  }
  return l;
}

/** Igualdad de bytes en tiempo constante (el largo se mezcla en el resultado en vez de salir antes). */
export function bytesIguales(a: Uint8Array, b: Uint8Array): boolean {
  let dif = a.length ^ b.length;
  const n = Math.max(a.length, b.length);
  for (let i = 0; i < n; i++) dif |= (a[i] ?? 0) ^ (b[i] ?? 0);
  return dif === 0;
}

/** Lo que hace Odoo: para las pruebas (y para documentar el formato con código que corre). */
export async function firmarPase(token: string, payload: Record<string, unknown>): Promise<string> {
  const cuerpo = aBase64Url(codificador.encode(JSON.stringify(payload)));
  const firma = await hmac(await llaveDelPase(token), cuerpo);
  return `${cuerpo}.${aBase64Url(firma)}`;
}

// ── Direcciones IP y redes ───────────────────────────────────────────────────

/** Los 4 o 16 bytes de una IP (sin corchetes ni zona). Una IPv6 «mapeada» (::ffff:a.b.c.d) devuelve la IPv4. null = no es una IP. */
export function bytesDeIp(texto: string): Uint8Array | null {
  const ip = texto.trim().replace(/^\[|\]$/g, "").replace(/%.*$/, "");
  const v4 = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(ip);
  if (v4) {
    const partes = v4.slice(1).map(Number);
    if (partes.some((p) => p > 255) || v4.slice(1).some((p) => p.length > 1 && p.startsWith("0"))) return null;
    return Uint8Array.from(partes);
  }
  if (!ip.includes(":") || !/^[0-9a-fA-F:.]+$/.test(ip)) return null;
  const mitades = ip.split("::");
  if (mitades.length > 2) return null;
  const grupos = (s: string): number[] | null => {
    if (!s) return [];
    const salida: number[] = [];
    const piezas = s.split(":");
    for (let i = 0; i < piezas.length; i++) {
      const p = piezas[i];
      if (i === piezas.length - 1 && p.includes(".")) {
        const b = bytesDeIp(p);
        if (!b || b.length !== 4) return null;
        salida.push((b[0] << 8) | b[1], (b[2] << 8) | b[3]);
      } else if (/^[0-9a-fA-F]{1,4}$/.test(p)) salida.push(parseInt(p, 16));
      else return null;
    }
    return salida;
  };
  const izq = grupos(mitades[0]);
  const der = mitades.length === 2 ? grupos(mitades[1]) : [];
  if (!izq || !der) return null;
  let todos: number[];
  if (mitades.length === 2) {
    const faltan = 8 - izq.length - der.length;
    if (faltan < 1) return null;
    todos = [...izq, ...new Array<number>(faltan).fill(0), ...der];
  } else {
    if (izq.length !== 8) return null;
    todos = izq;
  }
  const bytes = new Uint8Array(16);
  todos.forEach((g, i) => {
    bytes[i * 2] = g >> 8;
    bytes[i * 2 + 1] = g & 0xff;
  });
  // ::ffff:a.b.c.d es una IPv4: se compara como IPv4 (así lo hace Odoo).
  if (bytes.slice(0, 10).every((b) => b === 0) && bytes[10] === 0xff && bytes[11] === 0xff) return bytes.slice(12);
  return bytes;
}

/**
 * La llave del tope por red del Worker, de `CF-Connecting-IP`: la IPv4 entera o la red /64 de una IPv6 (lo que recibe un solo cliente),
 * igual que el borde y la búsqueda por foto. Nunca la /24 de una IPv4: muchos clientes del mismo operador comparten una (y está el
 * CGNAT). Una IPv4 escrita como IPv6 (::ffff:a.b.c.d) cuenta como IPv4. Sin IP o con algo que no es una IP: «sin-ip» (una sola llave
 * para todos esos, que así no se escapan del tope).
 */
export function llaveDeRed(ip: string | null): string {
  const b = ip ? bytesDeIp(ip) : null;
  if (!b) return "sin-ip";
  if (b.length === 4) return b.join(".");
  const grupos: string[] = [];
  for (let i = 0; i < 8; i += 2) grupos.push(((b[i] << 8) | b[i + 1]).toString(16));
  return `${grupos.join(":")}::/64`;
}

// ── Verificar ────────────────────────────────────────────────────────────────

const SID = /^[A-Za-z0-9_-]{16,64}$/;

/**
 * Verifica `Authorization: Pase <pase>` contra el token de Odoo y el reloj: firma, vencimiento y `sid` (la red del pase no se compara).
 * Falla cerrado: sin token configurado, sin cabecera o con cualquier cosa rara, no pasa. El orden importa: primero la firma (en
 * tiempo constante) y solo después se lee lo que dice el payload.
 */
export async function verificarPase(token: string | undefined, cabecera: string | null, ahoraMs: number): Promise<ResultadoPase> {
  if (!token) return { ok: false, motivo: "sin_token" };
  const m = /^Pase\s+(\S+)$/i.exec((cabecera ?? "").trim());
  if (!m) return { ok: false, motivo: "falta" };
  const pase = m[1];
  if (pase.length > LARGO_MAXIMO) return { ok: false, motivo: "forma" };
  const partes = pase.split(".");
  if (partes.length !== 2 || !partes[0] || !partes[1]) return { ok: false, motivo: "forma" };
  const [cuerpo, firmaTexto] = partes;
  const firma = deBase64Url(firmaTexto);
  const bytesCuerpo = deBase64Url(cuerpo);
  if (!firma || !bytesCuerpo) return { ok: false, motivo: "forma" };
  const esperada = await hmac(await llaveDelPase(token), cuerpo);
  if (!bytesIguales(firma, esperada)) return { ok: false, motivo: "firma" };

  let datos: unknown;
  try {
    datos = JSON.parse(new TextDecoder("utf-8", { fatal: true, ignoreBOM: false }).decode(bytesCuerpo));
  } catch {
    return { ok: false, motivo: "forma" };
  }
  if (!datos || typeof datos !== "object" || Array.isArray(datos)) return { ok: false, motivo: "forma" };
  const d = datos as Record<string, unknown>;
  if (d.v !== 1 || typeof d.sid !== "string" || !SID.test(d.sid)) return { ok: false, motivo: "forma" };
  if (typeof d.exp !== "number" || !Number.isFinite(d.exp)) return { ok: false, motivo: "forma" };
  const sitio = typeof d.sitio === "number" && Number.isInteger(d.sitio) ? d.sitio : 0;
  const ahoraS = ahoraMs / 1000;
  if (d.exp <= ahoraS) return { ok: false, motivo: "vencido" };
  if (d.exp > ahoraS + VIDA_MAXIMA_S) return { ok: false, motivo: "forma" };
  const red = typeof d.red === "string" && d.red.length <= 64 ? d.red : null;
  return { ok: true, pase: { sid: d.sid, exp: d.exp, red, sitio } };
}
