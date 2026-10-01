import { costoMicro, precioConocido, type TablaPrecios } from "./precios";
import type { Sql } from "./sql";
import type { Persona, Uso } from "./tipos";

/**
 * Libro de uso de tokens y costo. SOLO SE AGREGA: no hay método para editar ni borrar filas.
 * El gasto del mes es la SUMA de filas (no existe columna de saldo).
 * En producción vive en UN Durable Object para toda la empresa (`LibroUso`): el presupuesto es el
 * átomo de coordinación y 1 500 interacciones/día son pocas escrituras para un solo DO.
 */
export interface Topes {
  /** Microdólares por persona y mes, según su rol. */
  porRolMes: Record<Persona["rol"], number>;
  /** Microdólares de toda la empresa en el mes. */
  globalMes: number;
  /** Fracción a partir de la cual se degrada a la ruta económica (p. ej. 0,8). */
  aviso: number;
}

export interface Autorizacion {
  permitido: boolean;
  degradar: boolean;
  motivo?: string;
  gastoPersona: number;
  gastoGlobal: number;
}

export interface FilaUso {
  fecha: string; // ISO
  persona: Persona;
  conversacion: string;
  proveedor: string;
  modelo: string;
  uso: Uso;
}

export interface Libro {
  autorizar(persona: Persona, proveedor: string, modelo: string, mes: string): Promise<Autorizacion>;
  registrar(fila: FilaUso): Promise<number>;
}

export class LibroSql implements Libro {
  constructor(
    private readonly sql: Sql,
    private readonly precios: TablaPrecios,
    private readonly topes: Topes,
  ) {}

  private suma(condicion: string, ...p: (string | number)[]): number {
    const fila = this.sql.ejecutar(`SELECT COALESCE(SUM(costo_micro),0) AS s FROM uso WHERE ${condicion}`, ...p)[0];
    return Number(fila?.s ?? 0);
  }

  async autorizar(persona: Persona, proveedor: string, modelo: string, mes: string): Promise<Autorizacion> {
    const gastoPersona = this.suma("persona = ? AND mes = ?", persona.id, mes);
    const gastoGlobal = this.suma("mes = ?", mes);
    const topePersona = this.topes.porRolMes[persona.rol];
    const base = { gastoPersona, gastoGlobal };
    if (!precioConocido(this.precios, proveedor, modelo)) {
      return { ...base, permitido: false, degradar: false, motivo: `precio PENDIENTE de ${proveedor}/${modelo}` };
    }
    if (gastoPersona >= topePersona) {
      return { ...base, permitido: false, degradar: false, motivo: "tope mensual de la persona alcanzado" };
    }
    if (gastoGlobal >= this.topes.globalMes) {
      return { ...base, permitido: false, degradar: false, motivo: "tope mensual de la empresa alcanzado" };
    }
    const degradar = gastoPersona >= topePersona * this.topes.aviso || gastoGlobal >= this.topes.globalMes * this.topes.aviso;
    return { ...base, permitido: true, degradar };
  }

  async registrar(f: FilaUso): Promise<number> {
    const costo = costoMicro(this.precios, f.proveedor, f.modelo, f.uso);
    this.sql.ejecutar(
      `INSERT INTO uso (fecha, mes, persona, rol, conversacion, proveedor, modelo, entrada, salida,
        cache_lectura, cache_escritura, costo_micro, version_precios) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)`,
      f.fecha, f.fecha.slice(0, 7), f.persona.id, f.persona.rol, f.conversacion, f.proveedor, f.modelo,
      f.uso.entrada, f.uso.salida, f.uso.cacheLectura, f.uso.cacheEscritura, costo, this.precios.version,
    );
    return costo;
  }
}
