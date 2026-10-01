import { DurableObject } from "cloudflare:workers";
import { LibroSql, type Autorizacion, type FilaUso, type Topes } from "./nucleo/libro";
import { PRECIOS } from "./nucleo/precios";
import { esquema } from "./nucleo/sql";
import type { Persona } from "./nucleo/tipos";
import { sqlDeDurableObject } from "./sql_do";
import type { Env } from "./env";

/**
 * Un solo DO para toda la empresa: el presupuesto mensual es el átomo de coordinación.
 * 1 500 interacciones/día × ~3 llamadas = ~4 500 escrituras/día: muy por debajo de lo que aguanta un DO.
 */
export class LibroUso extends DurableObject<Env> {
  private libro: LibroSql;
  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env);
    const sql = sqlDeDurableObject(ctx.storage);
    esquema(sql);
    this.libro = new LibroSql(sql, PRECIOS, JSON.parse(env.BRIAN_TOPES) as Topes);
  }
  async autorizar(persona: Persona, proveedor: string, modelo: string, mes: string): Promise<Autorizacion> {
    return this.libro.autorizar(persona, proveedor, modelo, mes);
  }
  async registrar(fila: FilaUso): Promise<number> {
    return this.libro.registrar(fila);
  }
}
