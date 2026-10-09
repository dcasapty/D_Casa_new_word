// El panel de Odoo (la pantalla «Conversaciones» y sus hermanas) llama a estas rutas del Worker con
// `Authorization: Bearer <JUAN_WORKER_TOKEN>`; rutas.ts ya comprobó el token antes de llegar aquí.
//
//   POST /odoo/sugerir     → un borrador de respuesta para la vendedora (odoo-panel-sugerir.ts)
//   GET  /odoo/costos      → gasto de IA del mes por modelo (odoo-panel-costos.ts)
//   GET  /odoo/qr          → el QR para vincular WhatsApp (odoo-panel-conexiones.ts)
//   POST /odoo/reiniciar   → reiniciar el puente de WhatsApp
//   POST /odoo/desvincular → desvincular el número de WhatsApp

import type { Env } from "./env";
import { manejarConexiones } from "./odoo-panel-conexiones";
import { manejarCostos } from "./odoo-panel-costos";
import { manejarSugerir } from "./odoo-panel-sugerir";
import type { DepsRutas } from "./rutas";

/** La respuesta de la ruta del panel que corresponda, o `null` si no es una (para que rutas.ts siga con las suyas). */
export async function rutasDelPanel(ruta: string, req: Request, env: Env, d: DepsRutas): Promise<Response | null> {
  switch (ruta) {
    case "/odoo/sugerir":
      return manejarSugerir(req, env, d);
    case "/odoo/costos":
      return manejarCostos(req, env, d);
    case "/odoo/qr":
    case "/odoo/reiniciar":
    case "/odoo/desvincular":
      return manejarConexiones(ruta, req, env);
    default:
      return null;
  }
}
