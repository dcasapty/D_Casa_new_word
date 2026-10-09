/**
 * Integración REAL Odoo ⇄ Worker `juan` (se omite si no hay ODOO_INTEGRACION_URL; la corre scripts/integracion_juan.sh).
 *
 * Recorre, con el Odoo de verdad y el Worker de verdad (ver ayuda.ts), la historia de una clienta:
 *   bienvenida → pregunta por camas queen → herramientas reales de Odoo → mensajes registrados en Odoo →
 *   una vendedora toma la conversación con el método real de Odoo → el bot calla → devolver (con nota) →
 *   seguimiento 1 vencido → Odoo lo pide a /odoo/seguimiento → el Worker redacta → seguimiento/hecho → seguimiento 2.
 * Y los adjuntos en los dos sentidos, la idempotencia, la pausa y los errores.
 */
import { afterAll, beforeAll, describe } from "vitest";
import { hayOdoo } from "./ayuda";
import { seccionContrato } from "./contrato";
import { Escena } from "./escena";
import { seccionHistoria } from "./historia";
import { seccionSeguimiento } from "./seguimiento";

describe.skipIf(!hayOdoo)("Juan: Odoo real + Worker real", { timeout: 90_000 }, () => {
  const escena = new Escena();
  beforeAll(() => escena.iniciar(), 60_000);
  afterAll(() => escena.cerrar());

  seccionContrato(escena);
  seccionHistoria(escena);
  seccionSeguimiento(escena);
});
