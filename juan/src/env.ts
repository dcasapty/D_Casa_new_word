// Lo que el Worker `dcasa-juan` recibe de Cloudflare: bindings, variables y secretos.
// Solo NOMBRES: los valores de los secretos los carga la dueña (docs/JUAN_WORKER.md).

import type { Conversacion } from "./motor/do";
import type { Global } from "./motor/global";

export interface Env {
  // ── Bindings ──────────────────────────────────────────────────────────────
  /** Un Durable Object por conversación (`canal:id_externo`). Su SQLite guarda la memoria de trabajo. */
  CONVERSACION: DurableObjectNamespace<Conversacion>;
  /** Un solo Durable Object: gasto de IA del mes y estado de salud. */
  GLOBAL: DurableObjectNamespace<Global>;
  /** Service binding al Worker `dcasa` (que reenvía a Odoo). Worker a Worker NUNCA por URL pública. */
  DCASA: Fetcher;
  /** Service binding al puente de WhatsApp por QR (`puente-wa/`). */
  PUENTE?: Fetcher;
  /** Workers AI, SOLO para transcribir notas de voz y SOLO con TRANSCRIBIR_AUDIO=1. No se declara por defecto. */
  AI?: { run(modelo: string, entrada: unknown): Promise<unknown> };

  // ── Variables (wrangler.jsonc > vars) ─────────────────────────────────────
  /** "produccion" o "staging". */
  ENTORNO?: string;
  /** Versión (SHA del commit) que dice /odoo/salud. */
  VERSION?: string;
  /** URL pública de ESTE Worker (sin barra final). Para las URL temporales de archivos que Odoo descarga. */
  URL_PUBLICA?: string;
  /** Sitio público (para volver absolutas las URL relativas de las fotos). */
  URL_SITIO?: string;
  /** Segundos de espera para juntar ráfagas (15 por defecto). */
  BUFFER_SEGUNDOS?: string;
  /** Turnos máximos por persona en 24 h (50 por defecto). */
  TOPE_DIARIO?: string;
  /** "1" activa la transcripción de notas de voz con Workers AI (apagado por defecto). */
  TRANSCRIBIR_AUDIO?: string;
  /** Chat de Telegram al que el cron de salud avisa si algo se cae. Vacío = sin avisos. */
  ALERTA_TELEGRAM_CHAT_ID?: string;
  /** Solo si se activa la Cloud API de WhatsApp: el Phone Number ID del número. */
  WHATSAPP_PHONE_NUMBER_ID?: string;
  /** Versión de la Graph API de Meta (vNN.N). Vacío = la del código. */
  GRAPH_API_VERSION?: string;
  /** Dirección de la API de IA de Meta (Chat Completions compatible con OpenAI). Vacío = https://api.meta.ai/v1. */
  META_AI_BASE_URL?: string;
  /** Dirección de la API de OpenAI (o una compatible). Vacío = https://api.openai.com/v1. */
  OPENAI_BASE_URL?: string;

  // ── Secretos (solo nombres) ───────────────────────────────────────────────
  JUAN_ODOO_TOKEN?: string;
  JUAN_WORKER_TOKEN?: string;
  WA_TOKEN?: string;
  /** La IA: solo hace falta la del proveedor que se elija en Odoo (proveedor_ia) y, si hay, la del respaldo. */
  ANTHROPIC_API_KEY?: string;
  META_AI_API_KEY?: string;
  OPENAI_API_KEY?: string;
  TELEGRAM_BOT_TOKEN_JUAN?: string;
  TELEGRAM_WEBHOOK_SECRET_JUAN?: string;
  META_APP_SECRET?: string;
  META_VERIFY_TOKEN?: string;
  META_PAGE_TOKEN?: string;
  /** Solo si se activa la Cloud API de WhatsApp (no está en el contrato original de secretos). */
  WHATSAPP_CLOUD_TOKEN?: string;
}
