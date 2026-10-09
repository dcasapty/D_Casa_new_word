// Tipos compartidos entre el Worker (router) y el Durable Object.

import type { ArchivoDeCopia } from "./respaldo";
import type { Diario } from "./vigilancia";

export interface Env {
  /** El Durable Object único del puente (y su contenedor). */
  WA: DurableObjectNamespace;
  /** Service binding al Worker `juan`. */
  JUAN?: Fetcher;
  /** Bucket opcional para la copia diaria de la sesión; solo se usa con COPIA_R2 = «on». */
  COPIAS?: R2Bucket;

  // ── Secretos (solo nombres; los valores los carga la dueña) ──
  /** Token compartido con el Worker `juan`. Mínimo 24 caracteres, solo ASCII. */
  WA_TOKEN: string;
  /** Clave que cifra la sesión en reposo. Mínimo 32 caracteres. NO se rota a la ligera. */
  WA_SESION_CLAVE: string;
  /** La clave anterior, solo durante una rotación (docs/JUAN_PUENTE.md). */
  WA_SESION_CLAVE_ANTERIOR?: string;
  TELEGRAM_BOT_TOKEN_JUAN?: string;

  // ── Variables (no secretas) ──
  /** «on» enciende el contenedor y la vigilancia; cualquier otra cosa lo deja apagado. */
  PUENTE_ACTIVO?: string;
  /** URL pública de ESTE Worker: el contenedor vuelve a entrar por aquí a guardar su sesión. */
  PUENTE_BASE_URL: string;
  /** Dominios (separados por coma) de los que se pueden descargar imágenes y documentos. */
  MEDIOS_HOSTS_PERMITIDOS?: string;
  LIMITE_POR_MINUTO?: string;
  LIMITE_POR_DIA?: string;
  LIMITE_POR_DESTINATARIO_HORA?: string;
  LIMITE_FRIOS_DIA?: string;
  ENTRE_BURBUJAS_MS?: string;
  /** Chat de Telegram de la dueña para los avisos de caída. */
  ALERTA_TELEGRAM_CHAT?: string;
  ALERTA_MINUTOS?: string;
  ALERTA_REAVISO_MINUTOS?: string;
  /** «on» sube además la copia diaria a R2 (necesita el bucket COPIAS). */
  COPIA_R2?: string;
}

export type Fallo = { ok: false; status: number; error: string };

/** Lo que el router usa del Durable Object (por RPC). */
export interface PuenteStub {
  // Lo que llama el contenedor (con su época)
  kvGet(clave: string): Promise<string | null>;
  kvSet(clave: string, valor: string, epoca: string | null): Promise<{ ok: true } | Fallo>;
  kvDel(clave: string, epoca: string | null): Promise<{ ok: true } | Fallo>;
  kvLote(
    cuerpo: { leer?: string[]; escribir?: Record<string, string>; borrar?: string[] },
    epoca: string | null,
  ): Promise<
    | { ok: true; leidas: number; escritas: number; borradas: number; valores: Record<string, string | null> }
    | Fallo
  >;
  enviadosRecientes(): Promise<{ id: string; ts: number }[]>;
  marcarEntrante(celular: string): Promise<void>;
  encolarPendiente(cuerpo: string): Promise<number>;

  // Lo que llama el cron (cada minuto)
  despertar(): Promise<void>;

  // Lo que llama Juan (o quien opera) con WA_TOKEN
  estadoPublico(): Promise<Record<string, unknown>>;
  qr(): Promise<{ status: number; cuerpo: unknown }>;
  enviar(cuerpoTexto: string): Promise<{ status: number; cuerpo: unknown }>;
  desvincular(): Promise<{ status: number; cuerpo: unknown }>;
  matar(): Promise<Diario>;
  copiarAhora(): Promise<{ copia: string; filas: number; r2: { subida: boolean; motivo: string } }>;
  listarCopias(): Promise<{ copia: string; creada: string; filas: number }[]>;
  exportarCopia(copia?: string): Promise<ArchivoDeCopia | null>;
  restaurar(opciones: { copia?: string; archivo?: ArchivoDeCopia }): Promise<{ status: number; cuerpo: unknown }>;
  podar(): Promise<{ borradas: number; conservadas: number }>;
  recifrar(): Promise<{ revisadas: number; recifradas: number }>;
}
