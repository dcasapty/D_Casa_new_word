import type { Sql } from "./sql";

/** Idempotencia por id de llamada + confirmaciones humanas con caducidad. */
export type EstadoPendiente = "pendiente" | "ejecutando" | "ejecutada" | "cancelada" | "caducada" | "fallida";

export interface Pendiente {
  id: string;
  llamadaId: string;
  herramienta: string;
  argumentos: Record<string, unknown>;
  resumen: string;
  persona: string;
  creada: number;
  vence: number;
  estado: EstadoPendiente;
}

export class Acciones {
  constructor(
    private readonly sql: Sql,
    private readonly reloj: () => number,
    private readonly nuevoId: () => string,
    private readonly ttlMs = 10 * 60 * 1000,
  ) {}

  resultadoPrevio(llamadaId: string): unknown | undefined {
    const f = this.sql.ejecutar("SELECT json FROM resultados WHERE llamada_id = ?", llamadaId)[0];
    return f ? JSON.parse(String(f.json)) : undefined;
  }

  guardarResultado(llamadaId: string, herramienta: string, valor: unknown): void {
    this.sql.ejecutar(
      "INSERT OR IGNORE INTO resultados (llamada_id, herramienta, json, fecha) VALUES (?,?,?,?)",
      llamadaId, herramienta, JSON.stringify(valor ?? null), new Date(this.reloj()).toISOString(),
    );
  }

  crearPendiente(llamadaId: string, herramienta: string, argumentos: Record<string, unknown>, resumen: string, persona: string): Pendiente {
    const previa = this.sql.ejecutar("SELECT id FROM pendientes WHERE llamada_id = ?", llamadaId)[0];
    if (previa) return this.obtener(String(previa.id)) as Pendiente;
    const ahora = this.reloj();
    const p: Pendiente = {
      id: this.nuevoId(), llamadaId, herramienta, argumentos, resumen, persona,
      creada: ahora, vence: ahora + this.ttlMs, estado: "pendiente",
    };
    this.sql.ejecutar(
      `INSERT INTO pendientes (id, llamada_id, herramienta, argumentos, resumen, persona, creada, vence, estado)
       VALUES (?,?,?,?,?,?,?,?,?)`,
      p.id, p.llamadaId, p.herramienta, JSON.stringify(p.argumentos), p.resumen, p.persona, p.creada, p.vence, p.estado,
    );
    return p;
  }

  obtener(id: string): Pendiente | undefined {
    const f = this.sql.ejecutar("SELECT * FROM pendientes WHERE id = ?", id)[0];
    if (!f) return undefined;
    return {
      id: String(f.id), llamadaId: String(f.llamada_id), herramienta: String(f.herramienta),
      argumentos: JSON.parse(String(f.argumentos)), resumen: String(f.resumen), persona: String(f.persona),
      creada: Number(f.creada), vence: Number(f.vence), estado: String(f.estado) as EstadoPendiente,
    };
  }

  /** Transición atómica (una sentencia): solo cambia si el estado actual es `desde`. */
  transicion(id: string, desde: EstadoPendiente, hacia: EstadoPendiente): boolean {
    const r = this.sql.ejecutar("UPDATE pendientes SET estado = ? WHERE id = ? AND estado = ? RETURNING id", hacia, id, desde);
    return r.length === 1;
  }

  vencida(p: Pendiente): boolean {
    return this.reloj() > p.vence;
  }
}
