import type { BrianConversacion } from "./agente";
import type { LibroUso } from "./libro_do";

export interface Env {
  BrianConversacion: DurableObjectNamespace<BrianConversacion>;
  LIBRO: DurableObjectNamespace<LibroUso>;
  /** URL de AI Gateway, p. ej. https://gateway.ai.cloudflare.com/v1/<cuenta>/brian */
  AIG_BASE: string;
  ODOO_URL: string;
  ODOO_DB: string;
  /** JSON con Topes en microdólares (ver nucleo/libro.ts). */
  BRIAN_TOPES: string;
  META_API_KEY: string;
  ANTHROPIC_API_KEY: string;
  /** Secreto HMAC compartido con Odoo para firmar la identidad de la persona. */
  BRIAN_FIRMA: string;
}
