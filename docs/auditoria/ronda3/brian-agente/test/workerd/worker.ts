/**
 * Worker SOLO para la prueba de integración en workerd (Miniflare): ejecuta el núcleo de Brian dentro de
 * un Durable Object real con su SQLite, con proveedor y Odoo simulados (sin red).
 */
import { DurableObject } from "cloudflare:workers";
import { Brian } from "../../src/nucleo/bucle";
import { LibroSql } from "../../src/nucleo/libro";
import { OdooSimulado } from "../../src/nucleo/odoo";
import { PRECIOS } from "../../src/nucleo/precios";
import { esquema } from "../../src/nucleo/sql";
import type { Persona } from "../../src/nucleo/tipos";
import { ProveedorSimulado } from "../../src/proveedores/simulado";
import { sqlDeDurableObject } from "../../src/sql_do";

const DUENA: Persona = { id: "u1", nombre: "Dueña", rol: "duena", areas: ["catalogo", "clientes", "ventas", "contabilidad"] };
const TOPES = { porRolMes: { duena: 1_000_000, gerencia: 1, vendedora: 1 }, globalMes: 5_000_000, aviso: 0.8 };

export class ConvPrueba extends DurableObject {
  private odoo = new OdooSimulado();
  async escenario(): Promise<Record<string, unknown>> {
    const sql = sqlDeDurableObject(this.ctx.storage);
    esquema(sql);
    const meta = new ProveedorSimulado("meta", [
      { herramientas: [["buscar_productos", { texto: "queen" }]] },
      { texto: "Preparo el cobro.", herramientas: [["registrar_pago", { factura: "F-1", monto: 50, diario: "banco" }]] },
    ]);
    const brian = new Brian({
      sql, libro: new LibroSql(sql, PRECIOS, TOPES), proveedores: { meta }, odoo: this.odoo,
      reloj: () => Date.now(), nuevoId: () => crypto.randomUUID(), conversacion: "c1",
    });
    const t = await brian.turno(DUENA, "busca camas y cobra 50 a F-1");
    const id = t.pendientes[0]!.id;
    const c1 = await brian.confirmar(DUENA, id, true);
    const c2 = await brian.confirmar(DUENA, id, true);
    const uso = sql.ejecutar("SELECT COUNT(*) AS n, SUM(costo_micro) AS costo FROM uso")[0];
    const mensajes = sql.ejecutar("SELECT COUNT(*) AS n FROM mensajes")[0];
    return { pendientes: t.pendientes.length, c1: c1.estado, c2, pagos: this.odoo.pagos.length, uso, mensajes };
  }
}

export default {
  async fetch(_req: Request, env: { CONV: DurableObjectNamespace<ConvPrueba> }): Promise<Response> {
    return Response.json(await env.CONV.getByName("prueba").escenario());
  },
};
