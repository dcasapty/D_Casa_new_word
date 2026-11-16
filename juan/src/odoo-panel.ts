// El panel de Odoo (la pantalla «Conversaciones» y sus hermanas) llama a estas rutas del Worker con
// `Authorization: Bearer <JUAN_WORKER_TOKEN>`; rutas.ts ya comprobó el token antes de llegar aquí.
//
//   POST /odoo/sugerir     → un borrador de respuesta para la vendedora (odoo-panel-sugerir.ts)
//   POST /odoo/resumir     → el resumen de una conversación larga para la vendedora (odoo-panel-resumir.ts)
//   POST /odoo/embeber     → la huella de significado de unos textos, para la búsqueda en el conocimiento (odoo-panel-embeber.ts)
//   POST /odoo/buscar-foto → «Busca con una foto» de la tienda: solo el registro cerrado de la foto (odoo-panel-buscar-foto.ts)
//   POST /odoo/voz         → una nota de voz de Brian del panel: el audio entra, solo sale el texto (odoo-panel-voz.ts)
//   GET  /odoo/costos      → gasto de IA del mes por modelo (odoo-panel-costos.ts)
//   GET  /odoo/qr          → el QR para vincular WhatsApp (odoo-panel-conexiones.ts)
//   POST /odoo/reiniciar   → reiniciar el puente de WhatsApp
//   POST /odoo/desvincular → desvincular el número de WhatsApp

import type { Env } from "./env";
import { manejarBuscarFoto } from "./odoo-panel-buscar-foto";
import { manejarConexiones } from "./odoo-panel-conexiones";
import { manejarCostos } from "./odoo-panel-costos";
import { manejarEmbeber } from "./odoo-panel-embeber";
import { manejarResumir } from "./odoo-panel-resumir";
import { manejarSugerir } from "./odoo-panel-sugerir";
import { manejarVozPanel } from "./odoo-panel-voz";
import type { DepsRutas } from "./rutas";

/** La respuesta de la ruta del panel que corresponda, o `null` si no es una (para que rutas.ts siga con las suyas). */
export async function rutasDelPanel(ruta: string, req: Request, env: Env, d: DepsRutas): Promise<Response | null> {
  switch (ruta) {
    case "/odoo/sugerir":
      return manejarSugerir(req, env, d);
    case "/odoo/resumir":
      return manejarResumir(req, env, d);
    case "/odoo/embeber":
      return manejarEmbeber(req, env, d);
    case "/odoo/buscar-foto":
      return manejarBuscarFoto(req, env, d);
    case "/odoo/voz":
      return manejarVozPanel(req, env, d);
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
