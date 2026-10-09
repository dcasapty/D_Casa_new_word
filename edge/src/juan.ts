/**
 * Entrada del Worker `juan` (el asistente de clientes) a Odoo, por service binding.
 *
 * Contrato (docs/JUAN.md): las rutas `/dcasa/juan/**` de Odoo NO se alcanzan desde internet
 * (`routing.ts` las bloquea con 404, igual que `/jsonrpc`): solo entran por esta clase
 * (`JuanEntrada`, en `index.ts`), que únicamente el Worker `juan` puede llamar con su binding
 * `{ "binding": "DCASA", "service": "dcasa", "entrypoint": "JuanEntrada" }`.
 *
 * Aquí no hay dependencias de Cloudflare: se prueba entera en Node (`test/juan.test.ts`).
 *
 * Qué hace y qué NO hace:
 * - Reenvía solo `GET`/`POST` a `/dcasa/juan/**` (ruta normalizada: `..`, `%2e`, `//` y mayúsculas no
 *   sirven para salir de ahí). Cualquier otra ruta es 404: este punto de entrada NO es un proxy de Odoo.
 * - No toca el token: `Authorization: Bearer <JUAN_ODOO_TOKEN>` pasa tal cual y es Odoo quien lo
 *   comprueba (en tiempo constante). Sin token configurado en Odoo, todas responden 503.
 * - Quita cookies y la cabecera interna del borde; pone el host canónico para que Odoo vea el dominio real.
 * - Si Odoo está arrancando (el contenedor dormía o se está reiniciando), responde JSON 503 con
 *   `Retry-After` (el Worker `juan` reintenta y encola lo que escribe), no la página HTML de «arrancando».
 */
import { normalizePath } from "./routing";

export const PREFIJO_JUAN = "/dcasa/juan/";
/** Un mensaje con adjuntos en base64 es lo más grande que Odoo acepta (ver controllers/juan.py). */
export const MAX_CUERPO_JUAN = 14 * 1024 * 1024;
export const REINTENTO_JUAN_SEGUNDOS = 15;
const METODOS = new Set(["GET", "POST"]);

export interface DepsJuan {
  /** Envía la petición al contenedor de Odoo. */
  forward: (request: Request) => Promise<Response>;
  /** Dominio real (CANONICAL_HOST) que verá Odoo; si falta, el de la petición. */
  canonicalHost?: string;
}

function json(cuerpo: Record<string, unknown>, status: number, extra: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(cuerpo), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
      ...extra,
    },
  });
}

/** ¿Es una ruta de la API de Juan? Se decide sobre la ruta normalizada (sin `..`, `%XX`, `//`). */
export function esRutaJuan(pathname: string): boolean {
  return normalizePath(pathname).startsWith(PREFIJO_JUAN);
}

/** Cabeceras hacia Odoo: lo del Worker `juan` (incluido su `Authorization`) sin cookies ni marcas internas. */
export function cabecerasHaciaOdoo(request: Request, canonicalHost?: string): Headers {
  const url = new URL(request.url);
  const headers = new Headers(request.headers);
  headers.delete("Cookie");
  headers.delete("X-Dcasa-Borde");
  headers.set("X-Forwarded-Host", canonicalHost || url.host);
  headers.set("X-Forwarded-Proto", "https");
  return headers;
}

export async function atenderJuan(request: Request, deps: DepsJuan): Promise<Response> {
  const url = new URL(request.url);
  if (!esRutaJuan(url.pathname)) {
    return json({ ok: false, error: "No existe." }, 404);
  }
  if (!METODOS.has(request.method)) {
    return json({ ok: false, error: "Método no permitido." }, 405, { Allow: "GET, POST" });
  }
  const declarado = Number(request.headers.get("Content-Length") ?? "0");
  if (Number.isFinite(declarado) && declarado > MAX_CUERPO_JUAN) {
    return json({ ok: false, error: "El cuerpo es demasiado grande." }, 413);
  }
  // El cuerpo se lee entero (tope de 14 MB): así el tamaño real se comprueba aunque no venga Content-Length.
  const cuerpo = request.method === "GET" ? undefined : await request.arrayBuffer();
  if (cuerpo && cuerpo.byteLength > MAX_CUERPO_JUAN) {
    return json({ ok: false, error: "El cuerpo es demasiado grande." }, 413);
  }
  // La ruta que ve Odoo es la normalizada: lo que se revisó es lo que se envía.
  const destino = new URL(url.toString());
  destino.pathname = normalizePath(url.pathname);
  const upstream = new Request(destino, {
    method: request.method,
    headers: cabecerasHaciaOdoo(request, deps.canonicalHost),
    body: cuerpo,
  });
  let respuesta: Response;
  try {
    respuesta = await deps.forward(upstream);
  } catch (error) {
    console.error(JSON.stringify({ evento: "juan_sin_odoo", error: String(error).slice(0, 200) }));
    return json({ ok: false, error: "Odoo no responde.", reintentar_en: REINTENTO_JUAN_SEGUNDOS }, 503, {
      "Retry-After": String(REINTENTO_JUAN_SEGUNDOS),
    });
  }
  // `servirConArranque` contesta con la página «arrancando» mientras el contenedor despierta.
  if (respuesta.headers.get("X-Dcasa-Estado") === "arrancando") {
    const espera = respuesta.headers.get("Retry-After") ?? String(REINTENTO_JUAN_SEGUNDOS);
    return json({ ok: false, error: "Odoo está arrancando.", reintentar_en: Number(espera) || REINTENTO_JUAN_SEGUNDOS }, 503, {
      "Retry-After": espera,
    });
  }
  const final = new Response(respuesta.body, respuesta);
  final.headers.set("Cache-Control", "no-store");
  final.headers.delete("Set-Cookie");
  return final;
}
