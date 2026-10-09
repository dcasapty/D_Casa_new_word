// `GET /odoo/costos`: el gasto de IA del mes por modelo, para la pantalla «Costos de IA» de Odoo (docs/JUAN_PANEL.md).
// `GET /odoo/salud` ya trae el total del mes y el tope; esto agrega el desglose por modelo que el Durable Object «Global» guarda.
// El gasto POR DÍA (`por_dia`) existe desde que el Worker empezó a guardarlo; los días anteriores los arma Odoo con su foto diaria.
//
// Solo números y nombres de modelo: ningún secreto, ningún mensaje de cliente.

import { mesDelNegocio } from "./config";
import type { Env } from "./env";
import { fallo, respuesta } from "./odoo-panel-comun";
import type { DepsRutas } from "./rutas";

const redondear = (n: number, decimales = 4) => Math.round(n * 10 ** decimales) / 10 ** decimales;

export async function manejarCostos(req: Request, env: Env, d: Pick<DepsRutas, "config" | "ahora">): Promise<Response> {
  if (req.method !== "GET") return fallo("método no permitido", 405);
  const cfg = await d.config();
  const mes = mesDelNegocio(cfg.horario.zona, d.ahora());
  try {
    const global = env.GLOBAL.get(env.GLOBAL.idFromName("juan"));
    const g = await global.gastoMes(mes);
    // El detalle por día es un extra: si no se puede leer, el resto de la pantalla sigue igual.
    let porDia: { dia: string; usd: number }[] = [];
    try {
      porDia = await global.gastoPorDia(mes);
    } catch {
      /* se muestra el resto */
    }
    return respuesta({
      ok: true,
      mes,
      gasto_usd: redondear(g.usd, 2),
      turnos: g.turnos,
      tope_usd: cfg.presupuesto_ia_mensual_usd,
      por_modelo: g.porModelo.map((m) => ({ modelo: m.modelo, usd: redondear(m.usd), turnos: m.turnos, estimado: m.estimado })),
      modelos_sin_precio: g.modelosSinPrecio,
      por_dia: (Array.isArray(porDia) ? porDia : []).map((x) => ({ fecha: x.dia, usd: redondear(x.usd, 2) })),
    });
  } catch (e) {
    console.error("[juan] /odoo/costos:", e instanceof Error ? e.message : String(e));
    return fallo("No pude leer el gasto del mes.", 502);
  }
}
