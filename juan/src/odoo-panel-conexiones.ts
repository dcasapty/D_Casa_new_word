// Las rutas de «Conexiones» del panel de Odoo (docs/JUAN_PANEL.md): el QR para vincular WhatsApp y reiniciar o desvincular el
// puente. Todas con `Authorization: Bearer <JUAN_WORKER_TOKEN>` (la comprueba rutas.ts antes de llegar aquí).
//
//   GET  /odoo/qr          → { ok, estado, qr, edad_s }   el QR como imagen PNG (data URL); nada más
//   POST /odoo/reiniciar   → { ok, mensaje }              el puente se apaga y vuelve; la sesión se conserva
//   POST /odoo/desvincular → { ok }                       cierra la sesión: hay que escanear un QR nuevo
//
// El Worker habla con el puente por el service binding PUENTE (nunca por internet). El QR es una credencial en el aire mientras
// dure: JAMÁS se escribe en un registro (ni al éxito ni en un error), no se guarda y no se cachea (`cache-control: no-store`).
// Los errores dicen solo el estado HTTP y un texto corto, nunca el cuerpo que contestó el puente.

import type { Env } from "./env";
import { esObjeto, fallo, respuesta } from "./odoo-panel-comun";
import { tokenParaCabecera } from "./seguridad";

const PREFIJO_QR = "data:image/png;base64,";
const MAX_QR = 200_000;
const PLAZO_MS = 8000;

/** Lo que el puente llama de una forma y el panel de otra. */
const ESTADOS: Record<string, string> = {
  "esperando-qr": "necesita_qr",
  conectada: "conectado",
  cerrada: "desconectado",
  desvinculada: "desvinculada",
  arrancando: "arrancando",
  apagado: "apagado",
};


/** Los NOMBRES de lo que falta para hablar con el puente, o [] si todo está. */
export function faltantesDelPuente(env: Env): string[] {
  const faltan: string[] = [];
  if (!env.PUENTE) faltan.push("PUENTE");
  if (!env.WA_TOKEN) faltan.push("WA_TOKEN");
  return faltan;
}

async function alPuente(env: Env, ruta: string, metodo: "GET" | "POST"): Promise<{ status: number; cuerpo: Record<string, unknown> } | "sin_respuesta"> {
  let reloj: ReturnType<typeof setTimeout> | undefined;
  try {
    const delPuente = await Promise.race([
      env.PUENTE!.fetch(`https://puente${ruta}`, {
        method: metodo,
        headers: { "content-type": "application/json", "x-wa-token-b64": tokenParaCabecera(env.WA_TOKEN!) },
        ...(metodo === "POST" ? { body: "{}" } : {}),
      }),
      new Promise<null>((res) => (reloj = setTimeout(() => res(null), PLAZO_MS))),
    ]);
    if (!delPuente) return "sin_respuesta";
    let cuerpo: unknown = {};
    try {
      cuerpo = await delPuente.json();
    } catch {
      /* el puente contestó sin JSON: se ve por el estado */
    }
    return { status: delPuente.status, cuerpo: esObjeto(cuerpo) ? cuerpo : {} };
  } catch (e) {
    // Solo el tipo: el mensaje de un fallo de red podría traer una dirección.
    console.warn(`[juan] puente ${ruta}: ${e instanceof Error ? e.name : "fallo"}`);
    return "sin_respuesta";
  } finally {
    clearTimeout(reloj);
  }
}

/** Un texto corto y seguro del puente (sin saltos ni nada que parezca un QR o una clave larga). */
function textoCorto(v: unknown): string | undefined {
  if (typeof v !== "string") return undefined;
  const t = v.replace(/[\r\n\t]+/g, " ").trim();
  if (!t || t.length > 200 || t.startsWith("data:")) return undefined;
  return t;
}

export async function manejarConexiones(ruta: string, req: Request, env: Env): Promise<Response> {
  const esperado = ruta === "/odoo/qr" ? "GET" : "POST";
  if (req.method !== esperado) return fallo("método no permitido", 405);
  const faltan = faltantesDelPuente(env);
  if (faltan.length) {
    return fallo(`El puente de WhatsApp no está conectado a este Worker: faltan ${faltan.join(" y ")}.`, 503, { faltan });
  }

  if (ruta === "/odoo/qr") {
    const r = await alPuente(env, "/api/qr", "GET");
    if (r === "sin_respuesta") return fallo("El puente de WhatsApp no contestó.", 504);
    if (r.status >= 400) return fallo(`El puente respondió ${r.status}.`, 502);
    const crudo = r.cuerpo.qr;
    // Solo una imagen PNG: cualquier otra cosa no se pinta en el panel.
    const qr = typeof crudo === "string" && crudo.startsWith(PREFIJO_QR) && crudo.length <= MAX_QR ? crudo : null;
    const estadoCrudo = typeof r.cuerpo.estado === "string" ? r.cuerpo.estado : "";
    const edad = typeof r.cuerpo.edadMs === "number" && Number.isFinite(r.cuerpo.edadMs) ? Math.round(r.cuerpo.edadMs / 1000) : null;
    const mensaje = textoCorto(r.cuerpo.ultimoError);
    return respuesta({ ok: true, estado: ESTADOS[estadoCrudo] ?? (estadoCrudo.slice(0, 30) || "desconocido"), qr, edad_s: edad, ...(mensaje && !qr ? { mensaje } : {}) });
  }

  const ruta_puente = ruta === "/odoo/reiniciar" ? "/api/reiniciar" : "/api/desvincular";
  const r = await alPuente(env, ruta_puente, "POST");
  if (r === "sin_respuesta") return fallo("El puente de WhatsApp no contestó.", 504);
  if (r.status >= 400) {
    const motivo = textoCorto(r.cuerpo.error);
    return fallo(motivo ? `El puente respondió ${r.status}: ${motivo}` : `El puente respondió ${r.status}.`, 502);
  }
  return respuesta({ ok: true, ...(textoCorto(r.cuerpo.mensaje) ? { mensaje: textoCorto(r.cuerpo.mensaje) } : {}) });
}
