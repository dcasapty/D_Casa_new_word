import type { EjecutorOdoo } from "./odoo";
import type { EsquemaHerramienta, Persona } from "./tipos";

/**
 * CONTRATO COMÚN DE HERRAMIENTAS (propuesta para r3-brian-habilidades y r3-brian-documentos).
 * - nombre: snake_case estable (cambiarlo rompe la caché de prompt y las evals).
 * - esquema: JSON Schema con additionalProperties:false y `required` (sirve para `strict` en Claude y Meta).
 * - nivel: lectura | construccion | sensible (sensible = tarjeta de confirmación humana con caducidad).
 * - area: la usa el perfil de la persona para ofrecerla o no (Odoo ∩ Perfil).
 * - resumir: texto de la tarjeta con los valores YA resueltos (B-09 de la ronda 1).
 * - ejecutar: siempre por EjecutorOdoo con la clave de la persona y `idem` = id de llamada.
 */
export type Nivel = "lectura" | "construccion" | "sensible";

export interface ContextoHerramienta {
  odoo: EjecutorOdoo;
  persona: Persona;
  idem: string;
}

export interface Herramienta {
  nombre: string;
  descripcion: string;
  esquema: Record<string, unknown>;
  nivel: Nivel;
  area: string;
  resumir?: (args: Record<string, unknown>) => string;
  ejecutar: (args: Record<string, unknown>, ctx: ContextoHerramienta) => Promise<unknown>;
}

const obj = (props: Record<string, unknown>, requeridos: string[]) => ({
  type: "object",
  properties: props,
  required: requeridos,
  additionalProperties: false,
});

export const HERRAMIENTAS: Herramienta[] = [
  {
    nombre: "buscar_productos",
    descripcion: "Busca productos del catálogo por nombre o código y dice cuántos hay disponibles.",
    esquema: obj({ texto: { type: "string", description: "Nombre o código" } }, ["texto"]),
    nivel: "lectura",
    area: "catalogo",
    ejecutar: (a, c) => c.odoo.llamar("product.template", "search_read", { texto: a.texto }, { idem: c.idem }),
  },
  {
    nombre: "consultar_cliente",
    descripcion: "Busca un cliente por celular (llave del cliente) y devuelve lo que tiene por cobrar.",
    esquema: obj({ celular: { type: "string", pattern: "^[0-9]{4}-?[0-9]{4}$" } }, ["celular"]),
    nivel: "lectura",
    area: "clientes",
    ejecutar: (a, c) => c.odoo.llamar("res.partner", "search_read", { celular: a.celular }, { idem: c.idem }),
  },
  {
    nombre: "crear_cotizacion",
    descripcion: "Crea una cotización en borrador para un cliente. No confirma ni factura.",
    esquema: obj(
      {
        cliente_id: { type: "integer" },
        lineas: {
          type: "array",
          minItems: 1,
          items: obj({ producto_id: { type: "integer" }, cantidad: { type: "integer", minimum: 1 } }, ["producto_id", "cantidad"]),
        },
      },
      ["cliente_id", "lineas"],
    ),
    nivel: "construccion",
    area: "ventas",
    ejecutar: (a, c) => c.odoo.llamar("sale.order", "create", { cliente_id: a.cliente_id, lineas: a.lineas }, { idem: c.idem }),
  },
  {
    nombre: "registrar_pago",
    descripcion: "Registra un cobro sobre una factura publicada. Requiere confirmación de la persona.",
    esquema: obj(
      {
        factura: { type: "string" },
        monto: { type: "number", exclusiveMinimum: 0 },
        diario: { type: "string", enum: ["efectivo", "banco", "tarjeta"] },
      },
      ["factura", "monto", "diario"],
    ),
    nivel: "sensible",
    area: "contabilidad",
    resumir: (a) => `Registrar un cobro de $${Number(a.monto).toFixed(2)} a la factura ${String(a.factura)} (diario: ${String(a.diario)}).`,
    ejecutar: (a, c) =>
      c.odoo.llamar("account.payment", "registrar", { factura: a.factura, monto: a.monto, diario: a.diario }, { idem: c.idem }),
  },
];

/** Herramientas que el PERFIL de la persona permite. Odoo vuelve a comprobar con la clave de la persona. */
export function catalogoPara(persona: Persona, todas: Herramienta[] = HERRAMIENTAS): Herramienta[] {
  return todas.filter((h) => persona.areas.includes(h.area)).sort((a, b) => a.nombre.localeCompare(b.nombre));
}

export function esquemas(hs: Herramienta[]): EsquemaHerramienta[] {
  return hs.map((h) => ({ name: h.nombre, description: h.descripcion, input_schema: h.esquema }));
}

/** Validación mínima del lado del borde (tipos y requeridos); la validación fuerte la hace Odoo. */
export function validar(h: Herramienta, args: Record<string, unknown>): string | null {
  const req = (h.esquema.required as string[]) ?? [];
  for (const r of req) if (!(r in args)) return `Falta el campo «${r}».`;
  const props = Object.keys((h.esquema.properties as Record<string, unknown>) ?? {});
  for (const k of Object.keys(args)) if (!props.includes(k)) return `Campo no permitido «${k}».`;
  return null;
}
