import { ErrorProveedor, type Proveedor, type Respuesta, type Solicitud, type Uso } from "../nucleo/tipos";

/** Paso del guion: texto final, llamadas a herramientas, o un error HTTP simulado. */
export type Paso =
  | string
  | { texto?: string; herramientas?: [string, Record<string, unknown>][]; uso?: Partial<Uso> }
  | { error: number };

/** Proveedor determinista sin red: sigue el guion y anota cada solicitud (como `prueba` en Odoo). */
export class ProveedorSimulado implements Proveedor {
  readonly solicitudes: Solicitud[] = [];
  private n = 0;
  constructor(readonly id: string, private readonly guion: Paso[]) {}

  async chatear(s: Solicitud): Promise<Respuesta> {
    this.solicitudes.push(structuredClone(s));
    const paso = this.guion.shift() ?? "Listo.";
    if (typeof paso === "object" && "error" in paso) {
      throw new ErrorProveedor(`simulado ${paso.error}`, paso.error === 429 || paso.error >= 500, paso.error);
    }
    const p = typeof paso === "string" ? { texto: paso } : paso;
    const llamadas = (p.herramientas ?? []).map(([nombre, argumentos], i) => ({ id: `${this.id}_${++this.n}_${i}`, nombre, argumentos }));
    const uso: Uso = { entrada: 1000, salida: 200, cacheLectura: 0, cacheEscritura: 0, ...(p.uso ?? {}) };
    return { texto: p.texto ?? "", llamadas, fin: llamadas.length ? "herramientas" : "fin", uso, proveedor: this.id, modelo: s.modelo };
  }
}
