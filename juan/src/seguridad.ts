// Comparaciones y firmas que no filtran información por el tiempo que tardan.

const codificador = new TextEncoder();

/**
 * Igualdad en tiempo constante. Compara BYTES (no code units), así un token con
 * tilde o eñe no se cuela, y no corta en el primer carácter distinto.
 * Un secreto vacío NUNCA coincide: sin token configurado no entra nadie.
 */
export function tokensIguales(presentado: string, esperado: string): boolean {
  if (!esperado) return false;
  const a = codificador.encode(presentado);
  const b = codificador.encode(esperado);
  // El largo se mezcla en el resultado en vez de salir antes de tiempo.
  let dif = a.length ^ b.length;
  const n = Math.max(a.length, b.length);
  for (let i = 0; i < n; i++) dif |= (a[i] ?? 0) ^ (b[i] ?? 0);
  return dif === 0;
}

/** `Authorization: Bearer <token>` contra el esperado, en tiempo constante. */
export function bearerValido(req: Request, esperado: string | undefined): boolean {
  if (!esperado) return false;
  const m = /^Bearer\s+(.+)$/i.exec(req.headers.get("authorization") ?? "");
  return !!m && tokensIguales(m[1].trim(), esperado);
}

export async function hmacHex(secreto: string, mensaje: string): Promise<string> {
  const llave = await crypto.subtle.importKey(
    "raw",
    codificador.encode(secreto),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const firma = await crypto.subtle.sign("HMAC", llave, codificador.encode(mensaje));
  return [...new Uint8Array(firma)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/**
 * Firma `X-Hub-Signature-256: sha256=<hex>` de Meta (Messenger, Instagram, WhatsApp Cloud).
 * Falla cerrado: sin secreto, sin cabecera o con otro formato, no pasa.
 */
export async function firmaMetaValida(
  cuerpoCrudo: string,
  cabecera: string | null | undefined,
  secretoApp: string | undefined,
): Promise<boolean> {
  if (!secretoApp || !cabecera || !cabecera.startsWith("sha256=")) return false;
  const esperado = await hmacHex(secretoApp, cuerpoCrudo);
  return tokensIguales(cabecera.slice("sha256=".length).toLowerCase(), esperado);
}

/** Token del puente: `x-wa-token-b64` (UTF-8 en base64) o `x-wa-token` en claro. */
export function tokenDelPuente(req: Request): string {
  const b64 = req.headers.get("x-wa-token-b64");
  if (b64 !== null) {
    try {
      return new TextDecoder().decode(Uint8Array.from(atob(b64), (c) => c.charCodeAt(0)));
    } catch {
      return "";
    }
  }
  return req.headers.get("x-wa-token") ?? "";
}

/** Para mandar el token al puente sin que una tilde se corrompa en la cabecera. */
export function tokenParaCabecera(token: string): string {
  let bin = "";
  for (const b of codificador.encode(token)) bin += String.fromCharCode(b);
  return btoa(bin);
}
