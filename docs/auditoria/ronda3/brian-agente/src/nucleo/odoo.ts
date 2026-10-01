import type { FetchLike } from "./tipos";

/**
 * Odoo como EJECUTOR de herramientas. Brian en el borde nunca usa sudo: cada llamada va con la
 * clave de API de la PERSONA (Odoo 19 `/json/2/<modelo>/<método>`, `Authorization: bearer <clave>`),
 * así que Odoo aplica sus propios permisos y reglas de registro.
 */
export interface OpcionesLlamada {
  /** Clave de idempotencia (= id de la llamada de herramienta). Odoo debe guardarla con índice único. */
  idem?: string;
}

export interface EjecutorOdoo {
  llamar<T = unknown>(modelo: string, metodo: string, cuerpo: Record<string, unknown>, op?: OpcionesLlamada): Promise<T>;
}

export class ErrorOdoo extends Error {
  constructor(mensaje: string, readonly estado: number) {
    super(mensaje);
    this.name = "ErrorOdoo";
  }
}

/** Cliente JSON-2 real (no se ejecuta en los tests; se prueba con fetch simulado). */
export class OdooJson2 implements EjecutorOdoo {
  constructor(
    private readonly base: string,
    private readonly baseDatos: string,
    private readonly clavePersona: string,
    private readonly fetchFn: FetchLike = fetch,
  ) {}

  async llamar<T>(modelo: string, metodo: string, cuerpo: Record<string, unknown>, op: OpcionesLlamada = {}): Promise<T> {
    const headers: Record<string, string> = {
      "content-type": "application/json",
      authorization: `bearer ${this.clavePersona}`,
      "x-odoo-database": this.baseDatos,
    };
    // Odoo no conoce esta cabecera hoy: el plan de migración (fase 2) añade `brian.accion.idem_key` único.
    if (op.idem) headers["x-brian-idem"] = op.idem;
    const r = await this.fetchFn(`${this.base.replace(/\/$/, "")}/json/2/${modelo}/${metodo}`, {
      method: "POST",
      headers,
      body: JSON.stringify(cuerpo),
    });
    if (!r.ok) {
      const detalle = (await r.text()).slice(0, 300);
      throw new ErrorOdoo(r.status === 403 ? "No tienes permiso en Odoo para esto." : `Odoo respondió ${r.status}: ${detalle}`, r.status);
    }
    return (await r.json()) as T;
  }
}

// ---------------------------------------------------------------------------
// Odoo simulado (datos de ejemplo, NO son datos de D'CASA)
// ---------------------------------------------------------------------------

interface Producto { id: number; codigo: string; nombre: string; disponible: number }
interface Cliente { id: number; nombre: string; celular: string; por_cobrar: number }

export class OdooSimulado implements EjecutorOdoo {
  readonly llamadas: { modelo: string; metodo: string; cuerpo: Record<string, unknown>; idem?: string }[] = [];
  private readonly porIdem = new Map<string, unknown>();
  private siguiente = 100;
  productos: Producto[] = [
    { id: 1, codigo: "DEMO-001", nombre: "Cama Queen de prueba", disponible: 3 },
    { id: 2, codigo: "DEMO-002", nombre: "Colchón Queen de prueba", disponible: 0 },
  ];
  clientes: Cliente[] = [{ id: 7, nombre: "Cliente Demo", celular: "6555-1234", por_cobrar: 120 }];
  pagos: { id: number; factura: string; monto: number; diario: string }[] = [];
  cotizaciones: { id: number; cliente_id: number; lineas: unknown }[] = [];
  /** Permisos simulados por clave de persona (Odoo aplica ACL, no Brian). */
  constructor(private readonly puedeCobrar = true) {}

  async llamar<T>(modelo: string, metodo: string, cuerpo: Record<string, unknown>, op: OpcionesLlamada = {}): Promise<T> {
    this.llamadas.push({ modelo, metodo, cuerpo, idem: op.idem });
    if (op.idem && this.porIdem.has(op.idem)) return this.porIdem.get(op.idem) as T;
    const r = this.despachar(modelo, metodo, cuerpo);
    if (op.idem) this.porIdem.set(op.idem, r);
    return r as T;
  }

  private despachar(modelo: string, metodo: string, c: Record<string, unknown>): unknown {
    const clave = `${modelo}.${metodo}`;
    if (clave === "product.template.search_read") {
      const texto = String(c.texto ?? "").toLowerCase();
      return this.productos.filter((p) => p.nombre.toLowerCase().includes(texto) || p.codigo.toLowerCase() === texto);
    }
    if (clave === "res.partner.search_read") {
      return this.clientes.filter((x) => x.celular === c.celular);
    }
    if (clave === "sale.order.create") {
      const id = this.siguiente++;
      this.cotizaciones.push({ id, cliente_id: Number(c.cliente_id), lineas: c.lineas });
      return { id, nombre: `S${String(id).padStart(5, "0")}` };
    }
    if (clave === "account.payment.registrar") {
      if (!this.puedeCobrar) throw new ErrorOdoo("No tienes permiso en Odoo para esto.", 403);
      const id = this.siguiente++;
      this.pagos.push({ id, factura: String(c.factura), monto: Number(c.monto), diario: String(c.diario) });
      return { id, estado: "registrado" };
    }
    throw new ErrorOdoo(`Método no simulado: ${clave}`, 404);
  }
}
