// Lo que comparten las rutas del panel de Odoo (`odoo-panel-*.ts`): respuestas JSON sin caché y comprobaciones de forma.

export const esObjeto = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);

/** JSON en UTF-8 que nadie guarda: lo que sale por estas rutas (QR, borradores, gasto) no debe quedar en ninguna caché. */
export function respuesta(cuerpo: unknown, status = 200): Response {
  return new Response(JSON.stringify(cuerpo), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
  });
}

export function fallo(mensaje: string, status: number, extra: Record<string, unknown> = {}): Response {
  return respuesta({ ok: false, error: mensaje, ...extra }, status);
}

/** El cuerpo de una petición como objeto JSON, o la respuesta de error que corresponde. */
export async function leerObjeto(req: Request): Promise<Record<string, unknown> | Response> {
  let cuerpo: unknown;
  try {
    cuerpo = await req.json();
  } catch {
    return fallo("el cuerpo debe ser JSON", 400);
  }
  return esObjeto(cuerpo) ? cuerpo : fallo("el cuerpo debe ser un objeto JSON", 400);
}
