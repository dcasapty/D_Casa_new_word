// La interfaz que cumple CADA canal. El motor no conoce a WhatsApp, Telegram ni Meta:
// solo habla con esto. Agregar un canal = escribir un adaptador con esta forma y
// registrarlo en `canales/index.ts` (docs/JUAN.md → «Cómo agregar un canal»).

import type { Env } from "../env";
import type { OrigenUbicacion, UbicacionEntrante } from "./ubicacion";

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
  /**
   * Con qué se vuelve a pedir el archivo al canal (`AdaptadorCanal.descargar`), p. ej. el `media_id` de la Cloud API. Se guarda junto
   * al mensaje crudo (`guardarAntes`): si el Worker se cae antes de atenderlo, el Durable Object lo baja él mismo. Nunca lleva un token.
   */
  ref?: string;
  /** Un sticker (llega como imagen): se guarda para que el equipo lo vea en Odoo, pero el lector de imágenes no lo mira y no se
   *  anota para una vendedora (no es un comprobante ni un producto). */
  sticker?: boolean;
}

/**
 * El mensaje que el cliente citó al escribir (2026-11-07: «este», seleccionando un mensaje). WhatsApp manda solo el id del citado;
 * Telegram manda también lo que decía. El motor busca el texto en su memoria (o se lo dice Odoo) y se lo muestra al modelo como un
 * DATO del cliente, nunca como una orden.
 */
export interface CitaEntrante {
  /** El id que el canal dio al mensaje citado (el `wamid`, o `tg:<chat>:<id>` en Telegram). */
  id: string;
  /** Lo que decía, si el canal lo manda (Telegram). Siempre es dato del cliente. */
  texto?: string;
  /** El citado lo mandó la tienda (el bot o una vendedora), si el canal lo dice. */
  deLaTienda?: boolean;
}

/**
 * Un COMENTARIO público en una publicación de Facebook o de Instagram (2026-11-12, decisión de la dueña: «Solo los que preguntan»,
 * «Corto y lo demás por privado», «Apagado hasta que lo pruebes»). Viaja dentro de un `Entrante` (`comentario`) para aprovechar la
 * bandeja de los webhooks de Meta (guardar antes del 200, rescate, huella de 8 días); el motor NO lo trata como un mensaje: no arma
 * ráfaga, no cuenta para la ventana de 24 h ni se registra en Odoo como mensaje del cliente (ver `MotorConversacion.recibirComentario`).
 */
export interface ComentarioEntrante {
  red: "facebook" | "instagram";
  /** Por dónde llegó y por dónde se contesta: la página de Facebook (Messenger Platform) o Instagram por inicio de sesión de Instagram. */
  puerta: "pagina" | "instagram_login";
  /** El id del comentario en Meta. */
  id: string;
  /** Si es una respuesta a otro comentario, el de arriba: la respuesta pública va ahí (Instagram solo contesta comentarios de primer nivel). */
  padre?: string;
  /** El id de la publicación comentada (Facebook: `post_id`; Instagram: `media.id`). */
  publicacion?: string;
  /** Enlace a la publicación, si el aviso lo trae (Facebook: `post.permalink_url`). Solo https de Facebook o Instagram. */
  enlace?: string;
  /** El usuario de Instagram de quien comentó (sin @), si viene. */
  usuario?: string;
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
  /** El cliente respondió citando un mensaje. */
  cita?: CitaEntrante;
  /** El cliente lo reenvió de otro chat («muchas» = WhatsApp lo marca como reenviado muchas veces). */
  reenviado?: "una" | "muchas";
  /** No es un mensaje: es un comentario público en una publicación (ver `ComentarioEntrante`). `texto` es lo que comentó. */
  comentario?: ComentarioEntrante;
  /**
   * La ubicación de entrega que compartió el cliente (canales/ubicacion.ts): por el chat o con un enlace de mapa en el texto. Las
   * coordenadas van SOLO a Odoo (`POST /ubicacion`): nunca al modelo, al texto de la conversación, a lo que guarda el Durable Object ni al
   * registro. Solo en mensajes del cliente (nunca en uno `propio`).
   */
  ubicacion?: UbicacionEntrante;
  /**
   * El mensaje traía una ubicación que NO viaja con él: la copia que se guarda para el rescate (`crudoDe`) o la cola de pendientes del
   * puente nunca guardan coordenadas. Si se atiende desde ahí, el modelo sabe que la compartió y que hay que pedírsela otra vez.
   */
  ubicacion_omitida?: OrigenUbicacion;
}

/** Las respuestas a un comentario, por la API de la puerta por la que llegó. */
export interface RespuestasAComentarios {
  /**
   * La respuesta PRIVADA (`recipient: {comment_id}`): Meta deja UNA por comentario, dentro de los 7 días, y hasta que la persona
   * conteste no se le puede mandar nada más. Un solo mensaje de texto. Devuelve el id del mensaje y a quién le llegó (el PSID/IGSID).
   */
  privada(canal: CanalId, c: ComentarioEntrante, texto: string, env: Env): Promise<{ id?: string; destinatario?: string }>;
  /** La respuesta PÚBLICA, corta, debajo del comentario (o del de arriba, si es una respuesta). */
  publica(canal: CanalId, c: ComentarioEntrante, texto: string, env: Env): Promise<{ id?: string }>;
  /** El texto y el enlace de la publicación comentada: una consulta barata, sin IA. null = no se pudo. Nunca lanza. */
  publicacion?(canal: CanalId, c: ComentarioEntrante, env: Env): Promise<{ texto?: string; enlace?: string } | null>;
}

/** Lo que el canal dice de un mensaje NUESTRO (las palomitas). «fallido» = no llegó. */
export type EstadoDeEntrega = "enviado" | "entregado" | "leido" | "fallido";

/**
 * Un aviso del canal que NO es un mensaje del cliente: una palomita (enviado, entregado, leído, no llegó) o una reacción. Nunca
 * entra a la conversación del motor: no despierta al bot, no cuenta como mensaje del cliente (ni para la ventana de 24 h, ni para
 * los seguimientos) y no se guarda en el Durable Object. Va directo a Odoo, en una tanda por aviso del canal.
 */
export type EventoCanal =
  | { tipo: "estado"; canal: CanalId; id_externo: string; id_mensaje: string; estado: EstadoDeEntrega; ts: number; error?: string }
  | { tipo: "reaccion"; canal: CanalId; id_externo: string; id_mensaje: string; emoji: string; ts: number };

export interface MedioSaliente {
  tipo: "imagen" | "documento";
  url: string;
  nombre?: string;
  mime?: string;
  /** Pie de foto. */
  pie?: string;
  /**
   * El archivo YA vive en Odoo (p. ej. la cotización en PDF queda en un aviso del hilo): al registrar el mensaje en Odoo
   * va solo la línea «[Documento enviado: …]», sin la URL, para que Odoo no baje una segunda copia de su propio archivo.
   */
  sinCopia?: boolean;
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
  /**
   * «Responder» desde Odoo: el id en el canal del mensaje del cliente que se cita. Lo lleva el PRIMER mensaje que sale (WhatsApp:
   * `context.message_id`; Telegram: `reply_parameters`). Un canal que no sabe citar lo ignora.
   */
  responderA?: string;
  /**
   * El botón nativo «Enviar ubicación» (docs/UBICACION.md): con este texto corto encima, sale DESPUÉS de las burbujas y los archivos,
   * solo si todo lo demás salió. Lo manda el canal que tiene `Capacidades.pedirUbicacion` (WhatsApp Cloud: `location_request_message`);
   * los demás lo ignoran. Si el canal lo rechaza, no es un error del envío: el texto con el enlace ya salió.
   */
  pedirUbicacion?: string;
}

export interface ResultadoEnvio {
  /**
   * Ids que el canal dio a lo enviado, si los da, EN EL ORDEN de `Saliente` (burbujas, después archivos y al final el botón de
   * `pedirUbicacion`, si salió). Sirven para reconocer el eco del propio bot, las palomitas y las citas del cliente.
   */
  ids: string[];
  /** Salió el botón «Enviar ubicación» de `Saliente.pedirUbicacion` (su id, si el canal da ids, es el último de `ids`). */
  ubicacionPedida?: boolean;
}

/**
 * El envío se cortó a la mitad: ya salieron `burbujas` textos y `medios` archivos (en el orden de `Saliente`).
 * Quien reintente manda SOLO lo que falta; si no, el cliente recibiría dos veces lo mismo.
 */
export class EnvioParcialError extends Error {
  constructor(
    mensaje: string,
    readonly enviado: { burbujas: number; medios: number; ids: string[] },
  ) {
    super(mensaje);
    this.name = "EnvioParcialError";
  }
}

export interface ResultadoWebhook {
  /** Lo que se le contesta al proveedor, siempre rápido. */
  respuesta: Response;
  entrantes: Entrante[];
  /** true = el proveedor necesita un error HTTP para reintentar (el puente QR); false = se responde 200 y se procesa aparte. */
  esperar?: boolean;
  /**
   * Palomitas y reacciones del mismo aviso (2026-11-07). No se guardan antes del 200 ni pasan por el Durable Object: se le mandan a
   * Odoo en una tanda DESPUÉS de contestar (rutas.ts → `entregarEventos`). Perder una palomita no es perder un mensaje.
   */
  eventos?: EventoCanal[];
  /**
   * true = el proveedor reintenta SOLO ante un error HTTP y pide una respuesta rápida (Meta: WhatsApp Cloud, Messenger, Instagram).
   * Cada mensaje se guarda tal cual llegó en su Durable Object ANTES de contestar 200; si no se pudo guardar, 500 y Meta reintenta.
   * Lo lento (archivos, IA, la respuesta) va después. Los archivos tienen que venir como `url` o `ref` (nunca solo en bytes).
   */
  guardarAntes?: boolean;
}

export interface Capacidades {
  imagenes: boolean;
  documentos: boolean;
  /** El canal solo deja escribir primero dentro de las 24 h del último mensaje del cliente. */
  ventana24h: boolean;
  /** Largo máximo de un mensaje de texto. */
  maxTexto: number;
  /** Además, máximo en bytes UTF-8 (Instagram por inicio de sesión de Instagram: «UTF-8 y 1000 bytes o menos»). */
  maxBytesTexto?: number;
  /** El canal deja mandar un texto junto a la foto o el documento, en el mismo mensaje (pie de foto). */
  pie?: boolean;
  /** El canal tiene un botón nativo para que el cliente comparta su ubicación con un toque (`Saliente.pedirUbicacion`). */
  pedirUbicacion?: boolean;
}

/** Una foto de perfil de más de esto no se guarda (las de los canales pesan ~10-60 KB). */
export const MAX_FOTO_DE_PERFIL_BYTES = 300 * 1024;

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
  /** Lo que hay que saber de los comentarios de ese canal (se muestra en /salud si «Responder comentarios» está encendido). */
  avisosComentarios?: string[];
}

/** Una llave que vence y el canal renueva solo (Instagram por inicio de sesión de Instagram). Fechas, nunca el valor. */
export interface EstadoDeLlave {
  /** «AAAA-MM-DD» (hora de Panamá). */
  vence: string;
  /** false = todavía no se renovó: es el tope (la llave pegada vence a más tardar ese día). */
  vence_seguro: boolean;
  dias_restantes: number;
  /** «AAAA-MM-DD» de la última renovación que salió bien, o null. */
  renovada: string | null;
  /** «ok» la última salió bien · «fallo» la última falló (se reintenta al día siguiente) · «pendiente» aún no se renovó. */
  renovacion: "ok" | "fallo" | "pendiente";
}

/**
 * Lo que el canal sabe de sí mismo SIN preguntarle a nadie afuera (lo pide también el /salud público): por qué puerta va, cuándo
 * vence su llave y lo que hay que revisar (frases para personas, sin valores).
 */
export interface SaludLocal {
  /** Un canal con dos puertas dice por cuál va (Instagram: «pagina_facebook» o «inicio_sesion_instagram»). */
  puerta?: string;
  llave?: EstadoDeLlave;
  /** La cuenta del negocio en ese canal, si se sabe (p. ej. «@dcasapty»). */
  cuenta?: string;
  /** Avisos del canal que se ignoraron por ser de OTRA cuenta (cuántos, el último y los 4 últimos dígitos de esa cuenta). */
  ignorados?: { cantidad: number; ultimo: string; cuenta: string };
  /** Lo que dice Meta de la suscripción de la app a los mensajes de la cuenta, si se pudo consultar. */
  suscripcion?: "ok" | "no";
  problemas?: string[];
  avisos?: string[];
}

export interface AdaptadorCanal {
  /** Los canales de Odoo que atiende este adaptador (Meta atiende dos). */
  readonly canales: readonly CanalId[];
  /** Ruta pública del webhook, por ejemplo "/webhooks/telegram". */
  readonly ruta: string;
  /** Otros webhooks del mismo adaptador (Meta: «/webhooks/instagram», la puerta del inicio de sesión de Instagram). */
  readonly otrasRutas?: readonly string[];
  /**
   * Lo que puede llevar cada canal (Instagram por la página no manda documentos; Telegram sí). Con `env`, el de la puerta por la que
   * va el canal (Instagram por inicio de sesión de Instagram sí manda PDF); sin `env`, el de siempre.
   */
  capacidades(canal: CanalId, env?: Env): Capacidades;
  /**
   * NOMBRES de lo que le falta a este canal para funcionar: secretos sin cargar o service bindings sin declarar.
   * Vacío = listo. (Que el canal esté ENCENDIDO lo decide Odoo, no esto.) Nunca devuelve valores.
   */
  faltantes(env: Env, canal: CanalId): string[];
  /** ¿Están cargadas sus credenciales? Es `faltantes(...)` vacío. */
  configurado(env: Env, canal: CanalId): boolean;
  /** Verifica el origen del webhook y lo traduce a mensajes del motor. */
  recibir(req: Request, env: Env): Promise<ResultadoWebhook>;
  /** Vuelve a pedir un archivo entrante por su `ref` (el Durable Object, al rescatar un mensaje guardado con `guardarAntes`). */
  descargar?(ref: string, env: Env): Promise<{ bytes: Uint8Array; mime?: string } | null>;
  enviar(canal: CanalId, salida: Saliente, env: Env): Promise<ResultadoEnvio>;
  /**
   * La foto de perfil de quien escribe, pequeña, si el canal la da y la persona la tiene (y deja verla). `null` = no hay.
   * Mejor esfuerzo: puede lanzar; el motor lo registra y sigue. Los bytes solo van a Odoo, nunca a la IA.
   */
  fotoDePerfil?(canal: CanalId, para: string, env: Env): Promise<{ bytes: Uint8Array; mime: string } | null>;
  /**
   * El nombre de quien escribe, para canales cuyo aviso no lo trae (Messenger e Instagram mandan solo un número). `null` = no se
   * pudo. Mejor esfuerzo: puede lanzar; el motor lo pide una vez por conversación y sigue igual si falla.
   */
  nombreDePerfil?(canal: CanalId, para: string, env: Env): Promise<string | null>;
  /** "Escribiendo…", si el canal lo tiene. Mejor esfuerzo. */
  escribiendo?(canal: CanalId, para: string, env: Env): Promise<void>;
  /** Salud de la conexión, si hay una que vigilar. */
  salud?(canal: CanalId, env: Env): Promise<SaludCanal>;
  /** Lo que el canal sabe de sí mismo sin salir a la red (puerta, vencimiento de su llave): /salud lo muestra. */
  saludLocal?(canal: CanalId, env: Env): Promise<SaludLocal>;
  /** Lo que el canal hace solo, cada hora, desde el cron (p. ej. renovar su llave antes de que venza). Nunca lanza por un canal sin configurar. */
  mantener?(env: Env): Promise<void>;
  /** Contestar comentarios de publicaciones (Messenger = Facebook, Instagram), si el canal los recibe. */
  comentarios?: RespuestasAComentarios;
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

/** Lo que sale en el texto cuando un archivo no puede ir como archivo: «nombre: url» (o solo la url). */
export function enlaceDeMedio(m: { nombre?: string; url: string }): string {
  return m.nombre ? `${m.nombre}: ${m.url}` : m.url;
}

const bytesUtf8 = (texto: string) => new TextEncoder().encode(texto).length;

/** Cuántas unidades del principio de `texto` caben en `max` letras y `maxBytes` bytes UTF-8, sin partir un emoji. */
function cuantoCabe(texto: string, max: number, maxBytes?: number): number {
  if (maxBytes === undefined) return max;
  let unidades = 0;
  let bytes = 0;
  for (const c of texto) {
    const b = bytesUtf8(c);
    if (unidades + c.length > max || bytes + b > maxBytes) break;
    unidades += c.length;
    bytes += b;
  }
  return Math.max(1, unidades);
}

/** Parte un texto largo respetando el máximo del canal (último recurso: las burbujas ya son cortas); con `maxBytes`, también en bytes. */
export function partirPorLargo(texto: string, max: number, maxBytes?: number): string[] {
  const cabe = (t: string) => t.length <= max && (maxBytes === undefined || bytesUtf8(t) <= maxBytes);
  if (cabe(texto)) return [texto];
  const trozos: string[] = [];
  let resto = texto;
  while (!cabe(resto)) {
    const tope = cuantoCabe(resto, max, maxBytes);
    let corte = resto.lastIndexOf("\n", tope);
    if (corte < tope * 0.5) corte = resto.lastIndexOf(" ", tope);
    if (corte < tope * 0.5) corte = tope;
    trozos.push(resto.slice(0, corte).trim());
    resto = resto.slice(corte).trim();
  }
  if (resto) trozos.push(resto);
  return trozos;
}
