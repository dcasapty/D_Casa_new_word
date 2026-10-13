/**
 * Respuesta 503 «amable» mientras Odoo arranca o restaura la base desde R2 (I-07). Vive aparte de
 * handler.ts porque también la usa la caché de páginas (src/tienda/paginas.ts): una página guardada
 * cuyos estilos y JS no están en el borde se cambia por esta cuando Odoo no puede servirlos.
 */
import { withSecurityHeaders } from "./routing";

/** Segundos que se le piden al navegador/cliente antes de reintentar. */
export const REINTENTO_SEGUNDOS = 15;

/**
 * En vez de un error pelado, una página corta que se recarga sola. Nunca se guarda en caché. A
 * quien no pide HTML (Brian, Telegram, JSON-RPC, POST) se le da texto.
 */
export function respuestaArrancando(request: Request, reintento = REINTENTO_SEGUNDOS): Response {
  const headers = new Headers({
    "Retry-After": String(reintento),
    "Cache-Control": "no-store",
    "X-Dcasa-Estado": "arrancando",
  });
  const aceptaHtml = (request.headers.get("Accept") || "").includes("text/html");
  if (!aceptaHtml || request.method !== "GET") {
    headers.set("Content-Type", "text/plain; charset=utf-8");
    return withSecurityHeaders(
      new Response(`D'CASA está arrancando. Vuelve a intentar en ${reintento} segundos.\n`, { status: 503, headers }),
    );
  }
  headers.set("Content-Type", "text/html; charset=utf-8");
  return withSecurityHeaders(new Response(paginaArrancando(reintento), { status: 503, headers }));
}

function paginaArrancando(reintento: number): string {
  // Marca: fondo blanco, texto navy/azul, sin amarillo sobre blanco, sin degradados.
  return `<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="${reintento}">
<meta name="robots" content="noindex">
<title>D'CASA · Un momento</title>
<style>
  body{margin:0;background:#fff;color:#0B1F4D;font-family:Inter,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
    min-height:100vh;display:flex;align-items:center;justify-content:center;padding:16px;box-sizing:border-box}
  main{max-width:420px;text-align:center}
  h1{font-family:Anton,Impact,"Arial Narrow",sans-serif;text-transform:uppercase;color:#1340B1;font-weight:400;
    font-size:2rem;letter-spacing:.02em;margin:0 0 12px}
  p{line-height:1.5;margin:0 0 12px}
  a{color:#1340B1;font-weight:600}
</style>
</head>
<body>
<main>
  <h1>Estamos abriendo la tienda</h1>
  <p>Dame un momento: la página se recarga sola en ${reintento} segundos.</p>
  <p>¿Tienes prisa? <a href="https://wa.me/50760261919">Escríbenos por WhatsApp</a></p>
</main>
</body>
</html>
`;
}
