// URL temporal y firmada de un archivo que el cliente mandó (comprobante, foto, nota de voz).
// El archivo vive 2 días en el SQLite del Durable Object de esa conversación; Odoo lo descarga
// (la ruta es `GET /media/<conversación>/<id>?exp=...&sig=...`) y lo guarda en sus adjuntos.
// La firma sale del token del Worker, así que sin esa llave nadie puede fabricar un enlace.

import { hmacHex, tokensIguales } from "../seguridad";

export const VIDA_URL_MEDIO_MS = 2 * 24 * 3600_000;

function base64url(t: string): string {
  const bytes = new TextEncoder().encode(t);
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function deBase64url(t: string): string | null {
  try {
    const bin = atob(t.replace(/-/g, "+").replace(/_/g, "/"));
    return new TextDecoder().decode(Uint8Array.from(bin, (c) => c.charCodeAt(0)));
  } catch {
    return null;
  }
}

/** El nombre del Durable Object (`canal:id_externo`) viaja en la ruta, en base64url. */
export const claveDeConversacion = (canal: string, idExterno: string) => base64url(`${canal}:${idExterno}`);
export const nombreDeConversacion = (clave: string) => deBase64url(clave);

export async function firmarUrlMedio(urlPublica: string, secreto: string, clave: string, id: string, ahora: number): Promise<string> {
  const exp = ahora + VIDA_URL_MEDIO_MS;
  const sig = await hmacHex(secreto, `medio.${clave}.${id}.${exp}`);
  return `${urlPublica.replace(/\/$/, "")}/media/${clave}/${id}?exp=${exp}&sig=${sig}`;
}

export async function verificarUrlMedio(secreto: string, clave: string, id: string, exp: string | null, sig: string | null, ahora: number): Promise<"ok" | "vencida" | "firma"> {
  const vence = Number(exp);
  if (!secreto || !sig || !Number.isFinite(vence)) return "firma";
  const esperada = await hmacHex(secreto, `medio.${clave}.${id}.${vence}`);
  if (!tokensIguales(sig, esperada)) return "firma";
  return ahora > vence ? "vencida" : "ok";
}
