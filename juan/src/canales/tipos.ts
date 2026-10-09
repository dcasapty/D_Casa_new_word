// La interfaz que cumple CADA canal. El motor no conoce a WhatsApp, Telegram ni Meta:
// solo habla con esto. Agregar un canal = escribir un adaptador con esta forma y
// registrarlo en `canales/index.ts` (docs/JUAN_WORKER.md → «Cómo agregar un canal»).

import type { Env } from "../env";

/** Los mismos valores que `canal` en el contrato con Odoo (docs/JUAN.md). */
export type CanalId = "whatsapp_qr" | "whatsapp_cloud" | "telegram" | "messenger" | "instagram";

export const TODOS_LOS_CANALES: readonly CanalId[] = ["whatsapp_qr", "whatsapp_cloud", "telegram", "messenger", "instagram"];

export type TipoAdjunto = "imagen" | "audio" | "documento" | "video";

export interface AdjuntoEntrante {
  tipo: TipoAdjunto;
  mime?: string;
  nombre?: string;
  /** URL que Odoo puede abrir tal cual (las de Meta, o la temporal del puente). NUNCA una que lleve un token adentro. */
  url?: string;
  /** Si ya viene en bytes (p. ej. base64 del puente), el motor lo guarda y publica una URL firmada y temporal. */
  bytes?: Uint8Array;
  /** Para los canales que obligan a pedir el archivo con credenciales (Telegram, Cloud API): se llama una vez. */
  obtener?: () => Promise<{ bytes: Uint8Array; mime?: string } | null>;
}

export interface Entrante {
  canal: CanalId;
  /** Celular E.164 sin `+` (WhatsApp), `chat_id` (Telegram) o PSID/IGSID (Meta). */
  id_externo: string;
  /** Único por canal: el motor lo usa para no procesar dos veces un reintento del proveedor. */
  id_mensaje: string;
  nombre?: string;
  celular?: string;
  texto?: string;
  adjuntos: AdjuntoEntrante[];
  /** Milisegundos desde 1970. */
  ts: number;
  /**
   * Lo escribió una PERSONA del negocio desde su propio teléfono o bandeja (no el cliente ni el bot):
   * se registra como `vendedora` y el bot se calla.
   */
  propio?: boolean;
}

export interface MedioSaliente {
  tipo: "imagen" | "documento";
  url: string;
  nombre?: string;
  mime?: string;
  /** Pie de foto. */
  pie?: string;
}

export interface Saliente {
  /** `id_externo` del cliente. */
  para: string;
  /** Burbujas de texto, en orden. */
  burbujas: string[];
  /** Imágenes y documentos; salen DESPUÉS del texto. */
  medios: MedioSaliente[];
  /** Pausa entre burbujas, en ms (el puente de WhatsApp la aplica él mismo). */
  esperaMs?: number;
}

export interface ResultadoEnvio {
  /** Ids que el canal dio a lo enviado, si los da (sirven para reconocer el eco del propio bot). */
  ids: string[];
}

export interface ResultadoWebhook {
  /** Lo que se le contesta al proveedor, siempre rápido. */
  respuesta: Response;
  entrantes: Entrante[];
  /** true = el proveedor necesita un error HTTP para reintentar (el puente QR); false = se responde 200 y se procesa aparte. */
  esperar?: boolean;
}

export interface Capacidades {
  imagenes: boolean;
  documentos: boolean;
  /** El canal solo deja escribir primero dentro de las 24 h del último mensaje del cliente. */
  ventana24h: boolean;
  /** Largo máximo de un mensaje de texto. */
  maxTexto: number;
}

/** Lo que falta (secretos, bindings) para que un canal funcione, por nombre. */
export function faltantesDe(requeridos: Record<string, boolean>): string[] {
  return Object.entries(requeridos).filter(([, ok]) => !ok).map(([nombre]) => nombre);
}

export interface SaludCanal {
  configurado: boolean;
  /** Nombres de lo que falta, si algo falta. */
  faltan?: string[];
  /** null = este canal no puede saberlo (no hay una conexión que mirar). */
  conectado: boolean | null;
  detalle?: string;
}

export interface AdaptadorCanal {
  /** Los canales de Odoo que atiende este adaptador (Meta atiende dos). */
  readonly canales: readonly CanalId[];
  /** Ruta pública del webhook, por ejemplo "/webhooks/telegram". */
  readonly ruta: string;
  /** Lo que puede llevar cada canal (Instagram no manda documentos; Telegram sí). */
  capacidades(canal: CanalId): Capacidades;
  /**
   * NOMBRES de lo que le falta a este canal para funcionar: secretos sin cargar o service bindings sin declarar.
   * Vacío = listo. (Que el canal esté ENCENDIDO lo decide Odoo, no esto.) Nunca devuelve valores.
   */
  faltantes(env: Env, canal: CanalId): string[];
  /** ¿Están cargadas sus credenciales? Es `faltantes(...)` vacío. */
  configurado(env: Env, canal: CanalId): boolean;
  /** Verifica el origen del webhook y lo traduce a mensajes del motor. */
  recibir(req: Request, env: Env): Promise<ResultadoWebhook>;
  enviar(canal: CanalId, salida: Saliente, env: Env): Promise<ResultadoEnvio>;
  /** "Escribiendo…", si el canal lo tiene. Mejor esfuerzo. */
  escribiendo?(canal: CanalId, para: string, env: Env): Promise<void>;
  /** Salud de la conexión, si hay una que vigilar. */
  salud?(canal: CanalId, env: Env): Promise<SaludCanal>;
}

/** Respuestas HTTP que se repiten en los webhooks. */
export const ok200 = () => new Response("ok", { status: 200 });
export const json = (cuerpo: unknown, status = 200) =>
  new Response(JSON.stringify(cuerpo), { status, headers: { "content-type": "application/json; charset=utf-8" } });

/** Marcas de tiempo de los proveedores: segundos, milisegundos o ISO. Siempre se devuelve en ms. */
export function aMilisegundos(v: unknown, ahora: number): number {
  if (typeof v === "number" && Number.isFinite(v) && v > 0) return v < 1e12 ? Math.round(v * 1000) : Math.round(v);
  if (typeof v === "string" && v.trim()) {
    if (/^\d+$/.test(v.trim())) return aMilisegundos(Number(v), ahora);
    const t = Date.parse(v);
    if (Number.isFinite(t)) return t;
  }
  return ahora;
}

/**
 * Telegram, Messenger e Instagram no entienden la negrita de WhatsApp (`*persona*`): mostrarían los asteriscos tal cual.
 * Para esos canales se quitan los asteriscos que rodean una palabra o frase (`*persona*` → `persona`).
 */
export function sinNegritas(texto: string): string {
  return texto.replace(/\*([^*\n]+)\*/g, "$1");
}

/** Parte un texto largo respetando el máximo del canal (último recurso: las burbujas ya son cortas). */
export function partirPorLargo(texto: string, max: number): string[] {
  if (texto.length <= max) return [texto];
  const trozos: string[] = [];
  let resto = texto;
  while (resto.length > max) {
    let corte = resto.lastIndexOf("\n", max);
    if (corte < max * 0.5) corte = resto.lastIndexOf(" ", max);
    if (corte < max * 0.5) corte = max;
    trozos.push(resto.slice(0, corte).trim());
    resto = resto.slice(corte).trim();
  }
  if (resto) trozos.push(resto);
  return trozos;
}
