// El motor de UNA conversación (`canal:id_externo`). Es lógica pura: no importa Cloudflare.
// El Durable Object (motor/do.ts) le presta SQLite, el reloj y la alarma; las pruebas le prestan
// SQLite de Node, un reloj de mentira, un Odoo falso y un modelo guionado.
//
// Camino de un mensaje:
//   ingest → (duplicado · silencio · persona · anti-spam) → se guarda y arma la ráfaga de 15 s
//   alarma → registra en Odoo → ¿alguien tiene la conversación? → bucle de IA con herramientas (≤ 6 pasos)
//          → guardia de salida (ITBMS, cifras, existencias, promesas, fugas) → re-chequeo con Odoo
//          → burbujas cortas por el canal → registro en Odoo
//
// Lo que NO hace: guardar el historial permanente, decidir el seguimiento ni tocar puntos, precios o stock.
// Eso es de Odoo (docs/JUAN.md → «Quién sabe qué»).

import type { ModelMessage } from "ai";
import { canalActivo, dentroDeHorario, diaDelNegocio, mesDelNegocio, type Config } from "../config";
import type { AdaptadorCanal, CanalId, Entrante, MedioSaliente, Saliente } from "../canales/tipos";
import { EnvioParcialError, partirPorLargo } from "../canales/tipos";
import { noQuiereSeguimiento, pideUnaPersona } from "../dcasa/intencion";
import { contextoDelChat, promptEstable, promptParaFugas, promptSeguimiento, presentacionPorDefecto } from "../dcasa/prompt";
import { analizar, detectarSerHumano, notaDeCorreccion, quitarGraves, TEXTO_FUGA, TEXTO_SIN_DATO, limpiarForma, type ContextoRevision } from "../dcasa/salvaguardas";
import { pinesEscritos, taparPines, textoParaElModelo } from "../dcasa/sensibles";
import { TEXTO_FALLO_TECNICO, TEXTO_TOPE_DIARIO, textoPasoAVendedora } from "../dcasa/textos";
import { aMilisegundosOdoo, OdooError, type AdjuntoOdoo, type CuerpoMensaje, type DefHerramienta, type EstadoOdoo, type OdooApi, type RespuestaMensaje } from "../odoo/cliente";
import type { Env } from "../env";
import { Cola, crearEsquema, Fotos, Kv, Medios, Mensajes, type FilaMensaje } from "./almacen";
import { DESCANSO_POR_REPETIDO_MS, DESCANSO_POR_TOPE_MS, esRepetido, superaTopeDiario, TOPE_DIARIO_POR_DEFECTO } from "./antispam";
import { partirEnBurbujas } from "./burbujas";
import { cifrasDeTexto, construirHerramientas, RegistroDelTurno, textoDeLaHerramienta } from "./herramientas";
import { correrTurno, elegirNivel, type EntradaDelTurno, type SalidaDelTurno } from "./modelo";
import { planDeIntentos, type FabricaDeModelos, type ProveedorIa, type SeleccionDeModelo } from "./proveedores";
import { aplicarTope, costoDe, sumarUso, USO_VACIO, type Nivel, type Uso } from "./precios";
import { firmarUrlMedio } from "./mediosUrl";
import { esProductoSeguro, type LectorDeImagenes, type LecturaImagen } from "./vision";
import type { Sql } from "./sql";

// ── Constantes ──────────────────────────────────────────────────────────────

const MENSAJE_VENCIDO_MS = 2 * 3600_000;
const REINTENTOS_DE_IA = [60_000, 300_000];
/** La línea con que un archivo saliente queda en el historial («[Foto enviada: …]», «[Documento enviado: …]»). */
const etiquetaDeMedio = (m: MedioSaliente) => `[${m.tipo === "documento" ? "Documento enviado" : "Foto enviada"}${m.nombre ? `: ${m.nombre}` : ""}]`;

const ESPERA_ENTRE_BURBUJAS_MS = 1000;
const HISTORIAL_PARA_EL_MODELO = 20;
/** Lo máximo que se le muestra al modelo de UN mensaje del cliente: WhatsApp deja mandar decenas de miles de letras y cada una se paga. */
const MAX_LETRAS_DE_UN_MENSAJE_PARA_EL_MODELO = 2000;

function recortarParaElModelo(texto: string): string {
  return texto.length > MAX_LETRAS_DE_UN_MENSAJE_PARA_EL_MODELO ? `${texto.slice(0, MAX_LETRAS_DE_UN_MENSAJE_PARA_EL_MODELO)} […mensaje muy largo, el resto no se muestra]` : texto;
}
/** Imágenes que se leen por mensaje y por persona al día: cada lectura cuesta un poco de IA. */
const IMAGENES_POR_MENSAJE = 3;
/** Un pie de foto largo no cabe en todos los canales (Telegram corta en 1024): hasta aquí viaja junto a la foto. */
const MAX_PIE_DE_FOTO = 1000;
/** La foto de perfil se vuelve a pedir cada semana (la gente la cambia); si algo falla, a la hora. Plazo máximo por intento. */
const CADA_CUANTO_FOTO_DE_PERFIL_MS = 7 * 24 * 3600_000;
const REINTENTO_FOTO_DE_PERFIL_MS = 3600_000;
const PLAZO_FOTO_DE_PERFIL_MS = 8000;

function bytesABase64(bytes: Uint8Array): string {
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(bin);
}
const IMAGENES_POR_DIA = 10;

/** Lo que ya salió por el canal en un mismo envío. */
interface ProgresoDeEnvio {
  burbujas: number;
  medios: number;
  ids: string[];
}

/** El estado de un envío de Odoo, recordado por su `id_envio`: saliendo, cortado a medias o terminado. */
interface EnvioRecordado {
  e: "curso" | "parcial" | "listo";
  ts: number;
  b: number;
  m: number;
  ids: string[];
  /** Solo en «listo»: el id que se le devolvió a Odoo. */
  id?: string;
}
const PREFIJO_ID_ENVIO = "ide:";

/** Un adjunto como se guarda en la copia de trabajo: el de Odoo más lo que se leyó de la imagen (esto NO viaja a Odoo). */
type AdjuntoLocal = AdjuntoOdoo & { lectura?: LecturaImagen };
const RETENCION_MENSAJES_MS = 30 * 24 * 3600_000;
/** Un mensaje por registrar en Odoo es el historial permanente: se conserva un mes entero (como los de la copia de trabajo). */
const RETENCION_COLA_MENSAJES_MS = 30 * 24 * 3600_000;
/** Las escrituras sueltas (etiquetas, notas) pierden valor pronto: a los 3 días ya no importan. */
const RETENCION_COLA_HERRAMIENTAS_MS = 3 * 24 * 3600_000;
/** Con tantos intentos seguidos la cola deja el ritmo rápido (30 s → 15 min) y pasa a uno lento; NUNCA descarta. */
const INTENTOS_COLA_RAPIDOS = 12;
/** Una escritura suelta que Odoo rechaza con un 4xx se deja tras tantos intentos (reintentar no la arregla). */
const INTENTOS_COLA_HERRAMIENTA = 6;
const ESPERA_COLA_LENTA_MS = 6 * 3600_000;
/** Un envío desde Odoo recordado por su `id_envio`: el tiempo que Odoo puede seguir reintentándolo. */
const VIDA_ID_ENVIO_MS = 3 * 24 * 3600_000;
/** Mientras un envío con ese `id_envio` está saliendo, otro igual espera (si no, el cliente recibiría el mensaje dos veces). */
const ENVIO_EN_CURSO_MS = 3 * 60_000;
/** La ráfaga espera a que el cliente termine de escribir, pero no más de esto desde su primer mensaje (tantas veces `bufferMs`). */
const TOPE_DE_RAFAGA_VECES = 3;
const VENTANA_24H_MS = 23 * 3600_000;
const MARCA_PIN = "••••";
const CACHE_DE_HERRAMIENTAS_MS = 60_000;

const MAX_NOTA_DE_LA_VENDEDORA = 500;

/** La nota de una vendedora para el bot (Odoo la limita a 500 letras): un dato sin saltos ni etiquetas, o null. */
export function limpiarNota(v: unknown): string | null {
  if (typeof v !== "string") return null;
  const t = v.replace(/\s+/g, " ").trim().slice(0, MAX_NOTA_DE_LA_VENDEDORA);
  return t || null;
}

/** El mensaje de un error de la IA, sin nada que parezca una clave (algunos proveedores repiten la clave mal escrita). */
export function limpiarError(e: unknown): string {
  const t = e instanceof Error ? e.message : String(e);
  return t.replace(/(?:sk|LLM|xai|key)[-|_][A-Za-z0-9_\-|]{6,}/gi, "[clave]").replace(/Bearer\s+\S+/gi, "Bearer [clave]").slice(0, 300);
}

/** El motivo de un envío fallido para /salud: sin claves, sin tokens de bots y sin direcciones (las firmadas llevan la firma en la dirección). */
export function motivoDeEnvio(e: unknown): string {
  return limpiarError(e).replace(/https?:\/\/\S+/gi, "[enlace]").replace(/\b\d{6,}:[A-Za-z0-9_-]{20,}/g, "[clave]");
}

// ── Dependencias ────────────────────────────────────────────────────────────

export interface GlobalApi {
  gastoMes(mes: string): Promise<number>;
  /** `estimado`: el modelo no tenía precio cargado y se usó la tarifa de reserva (se avisa en /salud). */
  registrarGasto(mes: string, modelo: string, uso: Uso, usd: number, estimado: boolean, dia?: string): Promise<void>;
  /** Deja un dato para /salud (último fallo de la IA, uso del respaldo...). Valores como texto JSON, nunca secretos. */
  guardarSalud?(clave: string, json: string): Promise<void>;
}

export interface DepsMotor {
  sql: Sql;
  /** Se les pasa a los adaptadores de canal (secretos, bindings). */
  env: Env;
  ahora(): number;
  fijarAlarma(ts: number | null): Promise<void>;
  odoo: OdooApi;
  config(): Promise<Config>;
  herramientas(): Promise<DefHerramienta[]>;
  canal(id: CanalId): AdaptadorCanal | undefined;
  /** Arma el modelo de IA del proveedor elegido (Anthropic, Meta u OpenAI). */
  modelo: FabricaDeModelos;
  /** Qué proveedores de IA tienen su clave cargada ahora. */
  proveedoresDisponibles(): ProveedorIa[];
  global: GlobalApi;
  dormir(ms: number): Promise<void>;
  uuid(): string;
  bufferMs: number;
  topeDiario?: number;
  urlPublica?: string;
  urlSitio?: string;
  /** Llave con la que se firman las URL temporales de archivos. */
  secretoDeMedios?: string;
  /** Solo con TRANSCRIBIR_AUDIO=1: texto de una nota de voz, o null. */
  transcribir?: (bytes: Uint8Array, mime: string) => Promise<string | null>;
  /** Solo con RECONOCER_IMAGENES=1: qué es una imagen del cliente (producto, código, ¿comprobante?). Ver vision.ts. */
  mirarImagen?: LectorDeImagenes;
  log?: (nivel: "info" | "warn" | "error", mensaje: string, extra?: unknown) => void;
}

export interface ResultadoIngest {
  ok: true;
  accion: "en_espera" | "duplicado" | "silencio" | "descanso" | "propio" | "eco" | "vencido" | "persona" | "tope_diario";
}

export interface SolicitudEnviar {
  /**
   * Llave de idempotencia: el mismo `id_envio` nunca sale dos veces por el canal (Odoo reintenta si no oyó la respuesta).
   * Odoo manda el `id_mensaje` de su propio mensaje.
   */
  id_envio?: string;
  texto?: string;
  adjuntos?: { tipo: string; url: string; nombre?: string; mime?: string }[];
}

export interface SolicitudSeguimiento {
  conversacion_id: number;
  numero: number;
  contexto?: { interes?: string; ultimo_mensaje_ts?: string | number };
}

export type ResultadoSeguimiento =
  | { ok: true; resultado: "enviado" }
  | { ok: true; resultado: "descartado"; motivo: string }
  | { ok: true; resultado: "pospuesto"; motivo: string }
  | { ok: false; error: string };

const esEcoDelNegocio = (texto: string, recientes: readonly string[]) => {
  const t = texto.trim();
  if (!t) return false;
  return recientes.some((c) => {
    const x = c.trim();
    return x === t || (t.length >= 25 && x.includes(t));
  });
};

export class MotorConversacion {
  readonly kv: Kv;
  readonly mensajes: Mensajes;
  readonly cola: Cola;
  readonly medios: Medios;
  readonly fotos: Fotos;
  private procesando = false;
  private ultimoEscribiendo: number | null = null;
  /** Lo último que se le dijo a Odoo sobre si el asistente está preparando una respuesta (no se repite). */
  private escribiendoEnOdoo = false;
  /** Odoo no contestó en esta pasada: no se le insiste dentro de la misma alarma (el cliente no espera minutos). */
  private odooCaido = false;

  constructor(private readonly deps: DepsMotor) {
    crearEsquema(deps.sql);
    this.kv = new Kv(deps.sql);
    this.mensajes = new Mensajes(deps.sql);
    this.cola = new Cola(deps.sql);
    this.medios = new Medios(deps.sql);
    this.fotos = new Fotos(deps.sql);
  }

  private log(nivel: "info" | "warn" | "error", mensaje: string, extra?: unknown) {
    (this.deps.log ?? ((n, m, e) => console[n](`[juan] ${m}`, e ?? "")))(nivel, mensaje, extra);
  }

  // ── Identidad y estado ────────────────────────────────────────────────────

  private canalId(): CanalId {
    return this.kv.texto("canal") as CanalId;
  }
  private idExterno(): string {
    return this.kv.texto("id_externo") ?? "";
  }
  private conversacionId(): number | null {
    return this.kv.numero("conversacion_id");
  }
  private epoca(): number {
    return this.kv.numero("epoca") ?? 0;
  }

  private fijarIdentidad(e: Pick<Entrante, "canal" | "id_externo" | "nombre" | "celular">): void {
    this.kv.poner("canal", e.canal);
    this.kv.poner("id_externo", e.id_externo);
    if (e.nombre) this.kv.poner("nombre", e.nombre);
    const celular = e.celular ?? (/^\d{8,15}$/.test(e.id_externo) && (e.canal === "whatsapp_qr" || e.canal === "whatsapp_cloud") ? e.id_externo : undefined);
    if (celular) this.kv.poner("celular", celular);
  }

  private aplicarEstadoDeOdoo(r: RespuestaMensaje | EstadoOdoo): void {
    if ("conversacion_id" in r && typeof r.conversacion_id === "number") this.kv.poner("conversacion_id", r.conversacion_id);
    if (typeof r.estado === "string") this.kv.poner("odoo_estado", r.estado);
    if (typeof r.bot_activo === "boolean") this.kv.poner("odoo_bot_activo", r.bot_activo);
    if (r.pausada_hasta !== undefined) this.kv.poner("odoo_pausa_hasta", aMilisegundosOdoo(r.pausada_hasta));
    if (typeof r.dentro_de_horario === "boolean") this.kv.poner("odoo_dentro_horario", r.dentro_de_horario);
    // Odoo manda la nota de la vendedora en /mensaje y /estado (null = no hay); si el campo no viene, se conserva la que había.
    if ("nota_para_el_bot" in r) this.kv.poner("nota_vendedora", limpiarNota(r.nota_para_el_bot));
  }

  /** La pausa que pusimos nosotros (una persona acaba de escribir o Odoo acaba de avisar): es exacta, vale por su hora. */
  private silencioLocal(ahora: number): boolean {
    const local = this.kv.numero("pausa_hasta");
    return local !== null && local > ahora;
  }

  /** Lo último que Odoo dijo. Puede estar viejo: por eso se vuelve a mirar después de registrar el mensaje nuevo. */
  private silencioDeOdoo(ahora: number): boolean {
    const hasta = this.kv.numero("odoo_pausa_hasta");
    if (hasta !== null && hasta > ahora) return true;
    // Apagado sin fecha (el bot global, o «humano» indefinido) vale hasta que Odoo diga otra cosa; con fecha vencida, ya no.
    if (this.kv.texto("odoo_bot_activo") === "0") return hasta === null;
    // Una persona la tiene y Odoo no puso fecha: sigue suya hasta que se la devuelvan.
    return this.kv.texto("odoo_estado") === "humano" && hasta === null;
  }

  /** ¿El bot debe callarse? Cualquiera de los dos lados que diga «silencio» gana. */
  silencio(ahora = this.deps.ahora()): boolean {
    return this.silencioLocal(ahora) || this.silencioDeOdoo(ahora);
  }

  /** Una persona intervino: el bot suelta lo que traía, cancela la respuesta en curso y se calla. */
  private humanoIntervino(cfg: Config | null, ahora: number, hasta?: number | null): void {
    this.kv.sumar("epoca");
    const minutos = cfg?.pausa_por_defecto_minutos ?? 120;
    this.kv.poner("pausa_hasta", hasta ?? ahora + minutos * 60_000);
    this.mensajes.limpiarPendientes();
    this.kv.poner("t_rafaga", null);
    this.kv.poner("pide_persona", null);
  }

  // ── Entrada ───────────────────────────────────────────────────────────────

  async ingest(e: Entrante): Promise<ResultadoIngest> {
    const ahora = this.deps.ahora();
    this.fijarIdentidad(e);

    if (e.id_mensaje && this.mensajes.existe(e.id_mensaje)) return { ok: true, accion: "duplicado" };

    const { lista, transcripciones, lecturas } = await this.prepararAdjuntos(e, ahora);
    // Mientras se preparaban los adjuntos pudo entrar el mismo mensaje por otra puerta (un reintento del proveedor en paralelo).
    if (e.id_mensaje && this.mensajes.existe(e.id_mensaje)) return { ok: true, accion: "duplicado" };
    const textoOriginal = (e.texto ?? "").trim();
    const texto = [textoOriginal, ...transcripciones.map((t) => `(nota de voz) ${t}`)].filter(Boolean).join("\n");

    // Lo escribió una persona del negocio desde su teléfono o bandeja.
    if (e.propio) return this.ingestarPropio(e, texto, lista, ahora);

    // ── Anti-spam (corre antes de todo lo demás, sin gastar IA) ──
    const previos = this.mensajes.textosDelCliente(5);
    const repetido = !!textoOriginal && esRepetido(textoOriginal, previos);
    const sobreElTope = superaTopeDiario(this.mensajes.delClienteDesde(ahora - 24 * 3600_000), this.deps.topeDiario ?? TOPE_DIARIO_POR_DEFECTO);
    const pide = !!textoOriginal && pideUnaPersona(textoOriginal);
    const vencido = ahora - e.ts > MENSAJE_VENCIDO_MS;

    const adjuntosLocales: AdjuntoLocal[] = lista.map((a, i) => (lecturas[i] ? { ...a, lectura: lecturas[i]! } : a));
    const idFila = this.mensajes.insertar({ id_mensaje: e.id_mensaje, rol: "cliente", texto: texto || "(archivo)", adjuntos: adjuntosLocales, ts: e.ts, pendiente: false });
    this.kv.poner("ultimo_cliente_ts", Math.max(this.kv.numero("ultimo_cliente_ts") ?? 0, e.ts));

    // Odoo es el historial permanente: todo mensaje del cliente se registra, conteste el bot o no.
    this.cola.agregar("mensaje", this.cuerpoDeMensaje(e, taparPines(texto), "cliente", "entrante", lista), ahora);
    await this.programar();

    if (textoOriginal && noQuiereSeguimiento(textoOriginal) && !this.kv.bandera("sin_seguimiento")) {
      this.kv.poner("sin_seguimiento", true);
      this.cola.agregar("herramienta", { nombre: "anotar_conversacion", argumentos: { nota: "El cliente pidió que no lo contacten más o dijo que ya no le interesa. No enviar seguimientos." } }, ahora);
    }

    // Solo la pausa PROPIA corta aquí. Lo que Odoo dijo la última vez puede estar viejo (una pausa que ya venció, una
    // devolución que aún no nos llega): el mensaje se guarda para contestar y la ráfaga decide cuando Odoo ya respondió.
    const silenciada = this.silencioLocal(ahora);
    // Todo archivo queda anotado para una vendedora (puede ser un comprobante o un documento de identidad).
    // Una captura de producto que el lector entendió con claridad no necesita a una vendedora: el bot la atiende con el catálogo.
    const aNotar = lista.filter((a, i) => !(a.tipo === "audio" && transcripciones.length > 0) && !esProductoSeguro(lecturas[i]));
    if (aNotar.length > 0 && !silenciada && !this.silencioDeOdoo(ahora)) {
      this.cola.agregar("herramienta", { nombre: "anotar_conversacion", argumentos: { nota: this.notaDeArchivos(aNotar) } }, ahora);
    }
    // Un comprobante de pago: etiqueta para que las vendedoras lo encuentren (el bot nunca lo da por confirmado).
    if (lecturas.some((l) => l && (l.tipo === "comprobante" || l.parece_pago)) && !silenciada && !this.silencioDeOdoo(ahora)) {
      this.cola.agregar("herramienta", { nombre: "etiquetar_conversacion", argumentos: { etiqueta: "Comprobante recibido" } }, ahora);
    }
    if (silenciada) return { ok: true, accion: "silencio" };
    if (vencido) return { ok: true, accion: "vencido" };

    // «persona», «vendedora», «humano»: pasa siempre, incluso en descanso (regla 1).
    if (pide) {
      this.mensajes.marcarPendientes([idFila], true);
      this.kv.poner("pide_persona", true);
      this.kv.poner("t_rafaga", ahora + 1000);
      await this.programar();
      return { ok: true, accion: "persona" };
    }

    const descanso = this.kv.numero("descanso_hasta");
    if (descanso !== null && descanso > ahora) return { ok: true, accion: "descanso" };

    if (repetido) {
      this.kv.poner("descanso_hasta", ahora + DESCANSO_POR_REPETIDO_MS);
      this.mensajes.limpiarPendientes();
      this.kv.poner("t_rafaga", null);
      await this.programar();
      this.log("warn", "mensaje repetido: la conversación descansa 1 hora");
      return { ok: true, accion: "descanso" };
    }

    if (sobreElTope) {
      this.kv.poner("descanso_hasta", ahora + DESCANSO_POR_TOPE_MS);
      this.mensajes.limpiarPendientes();
      this.kv.poner("t_rafaga", null);
      await this.emitir({ burbujas: [TEXTO_TOPE_DIARIO], medios: [], autor: "bot", registrar: true }).catch((err) => this.log("error", "despedida del tope diario", String(err)));
      await this.programar();
      return { ok: true, accion: "tope_diario" };
    }

    this.mensajes.marcarPendientes([idFila], true);
    this.kv.poner("t_rafaga", this.siguienteSalidaDeRafaga(ahora));
    await this.programar();
    return { ok: true, accion: "en_espera" };
  }

  /**
   * Cada mensaje nuevo reinicia la espera de la ráfaga (el cliente sigue escribiendo), pero no para siempre: pasadas
   * `TOPE_DE_RAFAGA_VECES` esperas desde el primer mensaje de la ráfaga, se contesta con lo que haya. Sin este tope, quien escribe
   * una frase por vez cada 10 s nunca recibiría respuesta.
   */
  private siguienteSalidaDeRafaga(ahora: number): number {
    const armada = this.kv.numero("t_rafaga") !== null;
    const inicioGuardado = this.kv.numero("t_rafaga_inicio");
    const inicio = armada && inicioGuardado !== null && inicioGuardado <= ahora ? inicioGuardado : ahora;
    this.kv.poner("t_rafaga_inicio", inicio);
    return Math.max(ahora, Math.min(ahora + this.deps.bufferMs, inicio + TOPE_DE_RAFAGA_VECES * this.deps.bufferMs));
  }

  private notaDeArchivos(lista: AdjuntoOdoo[]): string {
    const partes = lista.map((a) => `${a.tipo}${a.nombre ? ` «${a.nombre}»` : ""}`);
    const puedeSerSensible = lista.some((a) => a.tipo !== "audio");
    return (
      `El cliente envió ${lista.length === 1 ? "un archivo" : `${lista.length} archivos`}: ${partes.join(", ")}. ` +
      (puedeSerSensible ? "Puede ser un comprobante de pago o un documento de identidad. " : "") +
      "No se le mostró a la IA: revisar y confirmar con el cliente."
    );
  }

  /** Mensaje escrito por una persona de D'CASA desde el teléfono o la bandeja del canal. */
  private async ingestarPropio(e: Entrante, texto: string, lista: AdjuntoOdoo[], ahora: number): Promise<ResultadoIngest> {
    const recientes = this.mensajes.salientesDesde(ahora - 15 * 60_000);
    // El eco del propio bot (o de algo que se mandó desde Odoo) no es una persona escribiendo.
    if ((texto && esEcoDelNegocio(texto, recientes)) || (e.id_mensaje && this.kv.texto(`env:${e.id_mensaje}`) !== null)) {
      return { ok: true, accion: "eco" };
    }
    this.mensajes.insertar({ id_mensaje: e.id_mensaje, rol: "vendedora", texto: texto || "(archivo)", adjuntos: lista, ts: e.ts });
    this.cola.agregar("mensaje", this.cuerpoDeMensaje(e, texto, "vendedora", "saliente", lista), ahora);
    this.humanoIntervino(await this.deps.config(), ahora);
    await this.programar();
    return { ok: true, accion: "propio" };
  }

  private cuerpoDeMensaje(e: Pick<Entrante, "canal" | "id_externo" | "nombre" | "celular" | "id_mensaje">, texto: string, autor: CuerpoMensaje["autor"], direccion: CuerpoMensaje["direccion"], adjuntos: AdjuntoOdoo[], ts = this.deps.ahora(), idMensaje = e.id_mensaje): CuerpoMensaje {
    return {
      canal: e.canal,
      id_externo: e.id_externo,
      nombre: this.kv.texto("nombre") ?? e.nombre,
      celular: this.kv.texto("celular") ?? undefined,
      id_mensaje: idMensaje,
      direccion,
      autor,
      texto,
      ...(adjuntos.length ? { adjuntos } : {}),
      ts: new Date(ts).toISOString(),
    };
  }

  private async prepararAdjuntos(e: Entrante, ahora: number): Promise<{ lista: AdjuntoOdoo[]; transcripciones: string[]; lecturas: (LecturaImagen | null)[] }> {
    const lista: AdjuntoOdoo[] = [];
    const transcripciones: string[] = [];
    const lecturas: (LecturaImagen | null)[] = [];
    let imagenesLeidas = 0;
    for (const a of e.adjuntos ?? []) {
      let lectura: LecturaImagen | null = null;
      let url = a.url ?? null;
      if (a.bytes && a.bytes.byteLength > 0) {
        const mime = a.mime ?? "application/octet-stream";
        if (a.tipo === "imagen" && this.deps.mirarImagen && imagenesLeidas < IMAGENES_POR_MENSAJE && this.cabeOtraLecturaHoy(ahora)) {
          imagenesLeidas++;
          try {
            lectura = await this.deps.mirarImagen(a.bytes, mime);
          } catch (err) {
            this.log("warn", "no se pudo leer la imagen: sigue el camino de siempre (la revisa una vendedora)", String(err));
          }
        }
        if (a.tipo === "audio" && this.deps.transcribir) {
          try {
            const t = await this.deps.transcribir(a.bytes, mime);
            if (t) transcripciones.push(t.trim());
          } catch (err) {
            this.log("warn", "no se pudo transcribir la nota de voz", String(err));
          }
        }
        try {
          const id = this.deps.uuid().replace(/-/g, "");
          this.medios.guardar(id, a.bytes, mime, a.nombre, ahora);
          if (this.deps.urlPublica && this.deps.secretoDeMedios) {
            const clave = (await import("./mediosUrl")).claveDeConversacion(e.canal, e.id_externo);
            url = await firmarUrlMedio(this.deps.urlPublica, this.deps.secretoDeMedios, clave, id, ahora);
          }
        } catch (err) {
          this.log("warn", "no se pudo guardar el archivo", String(err));
        }
      }
      const marca = lectura ? marcaDeLectura(lectura) : {};
      lista.push({ tipo: a.tipo, url, nombre: a.nombre, mime: a.mime, ...marca });
      lecturas.push(lectura);
    }
    return { lista, transcripciones, lecturas };
  }

  /** Cuenta una lectura de imagen en el día de esta persona; false si ya llegó al tope (entonces la imagen sigue el camino de siempre). */
  private cabeOtraLecturaHoy(ahora: number): boolean {
    const dia = new Date(ahora).toISOString().slice(0, 10);
    const n = this.kv.texto("imagenes_dia") === dia ? (this.kv.numero("imagenes_n") ?? 0) : 0;
    if (n >= IMAGENES_POR_DIA) return false;
    this.kv.poner("imagenes_dia", dia);
    this.kv.poner("imagenes_n", n + 1);
    return true;
  }

  // ── Alarma ────────────────────────────────────────────────────────────────

  /** Programa la próxima alarma: la más cercana entre la ráfaga, la cola de Odoo y la limpieza. */
  async programar(): Promise<void> {
    const candidatas = [this.kv.numero("t_rafaga"), this.cola.proxima(), this.kv.numero("t_purga")].filter((x): x is number => x !== null);
    await this.deps.fijarAlarma(candidatas.length ? Math.min(...candidatas) : null);
  }

  async alarma(): Promise<void> {
    if (this.procesando) return;
    this.procesando = true;
    this.odooCaido = false;
    try {
      const ahora = this.deps.ahora();
      if (this.kv.numero("t_purga") === null) this.kv.poner("t_purga", ahora + 24 * 3600_000);

      await this.vaciarCola().catch((e) => this.log("error", "cola de Odoo", String(e)));

      const t = this.kv.numero("t_rafaga");
      if (t !== null && t <= this.deps.ahora()) {
        this.kv.poner("t_rafaga", null);
        this.kv.poner("t_rafaga_inicio", null);
        await this.procesarRafaga().catch((e) => this.log("error", "ráfaga", e instanceof Error ? (e.stack ?? e.message) : String(e)));
      }

      const p = this.kv.numero("t_purga");
      if (p !== null && p <= this.deps.ahora()) {
        this.purgar();
        this.kv.poner("t_purga", this.deps.ahora() + 24 * 3600_000);
      }
    } finally {
      this.procesando = false;
      await this.programar();
    }
  }

  private purgar(): void {
    const ahora = this.deps.ahora();
    this.mensajes.purgar(ahora - RETENCION_MENSAJES_MS, 200);
    this.cola.purgar(ahora - RETENCION_COLA_MENSAJES_MS, "mensaje");
    this.cola.purgar(ahora - RETENCION_COLA_HERRAMIENTAS_MS, "herramienta");
    this.medios.purgar(ahora - 2 * 24 * 3600_000);
    this.fotos.purgar(ahora - 30 * 24 * 3600_000);
    this.deps.sql.correr("DELETE FROM enviados WHERE ts < ?", ahora - 24 * 3600_000);
    this.deps.sql.correr("DELETE FROM seguimientos WHERE ts < ?", ahora - 90 * 24 * 3600_000);
    this.deps.sql.correr("DELETE FROM kv WHERE k LIKE 'env:%' AND CAST(v AS INTEGER) < ?", ahora - 24 * 3600_000);
    this.deps.sql.correr(`DELETE FROM kv WHERE k LIKE '${PREFIJO_ID_ENVIO}%' AND CAST(json_extract(v, '$.ts') AS INTEGER) < ?`, ahora - VIDA_ID_ENVIO_MS);
  }

  // ── Cola de escrituras a Odoo (con reintentos: Odoo puede estar dormido) ──

  /**
   * Lo que no se pudo entregar a Odoo se reintenta SIEMPRE: primero rápido (30 s, 1 min, 2 min... hasta 15 min) y, pasados
   * `INTENTOS_COLA_RAPIDOS`, cada 6 horas. Nada se descarta por fallar (el historial de los clientes está en juego): solo se
   * borra al entregarse, por vejez (`purgar`) o si Odoo rechaza una escritura suelta por una razón que no se arregla reintentando.
   */
  private async vaciarCola(): Promise<void> {
    const habiaEstancadas = this.kv.bandera("cola_estancada");
    let entregadas = 0;
    for (const fila of this.cola.vencidas(this.deps.ahora())) {
      const ahora = this.deps.ahora();
      try {
        if (fila.tipo === "mensaje") {
          const r = await this.deps.odoo.mensaje(JSON.parse(fila.cuerpo) as CuerpoMensaje);
          this.aplicarEstadoDeOdoo(r);
          this.cola.borrar(fila.id);
        } else {
          const id = this.conversacionId();
          if (id === null) {
            this.cola.reintentar(fila.id, ahora + 60_000);
            continue;
          }
          const c = JSON.parse(fila.cuerpo) as { nombre: string; argumentos: Record<string, unknown> };
          const r = await this.deps.odoo.herramienta(c.nombre, c.argumentos, id);
          // Odoo contestó y la rechazó (`transitorio: false`): reintentar no la arregla. Si ni siquiera se pudo hablar con Odoo, sí.
          if (!r.ok) throw r.transitorio === false ? new OdooError(r.error ?? "Odoo rechazó la herramienta", 422, false) : new Error(r.error ?? "herramienta falló");
          this.cola.borrar(fila.id);
        }
        entregadas++;
      } catch (err) {
        // Sin el token de Odoo (primer despliegue, antes de pegar los secretos) lo pendiente espera: no se pierde ni gasta intentos.
        if (err instanceof OdooError && err.sinCredenciales) {
          this.cola.posponer(fila.id, ahora + 5 * 60_000);
          this.odooCaido = true;
          break;
        }
        const intentos = fila.intentos + 1;
        // Una etiqueta o nota que Odoo rechaza (4xx) no mejora reintentando: tras unos intentos se deja. Un MENSAJE jamás se descarta.
        if (fila.tipo === "herramienta" && err instanceof OdooError && !err.reintentable && intentos >= INTENTOS_COLA_HERRAMIENTA) {
          this.log("error", `Odoo rechazó la escritura «${fila.tipo}» ${intentos} veces: se deja`, String(err));
          this.cola.borrar(fila.id);
        } else if (intentos >= INTENTOS_COLA_RAPIDOS) {
          this.cola.reintentar(fila.id, ahora + ESPERA_COLA_LENTA_MS);
          if (intentos === INTENTOS_COLA_RAPIDOS) this.log("error", `Odoo no recibe un ${fila.tipo} tras ${intentos} intentos: se reintenta cada 6 horas, no se pierde`, String(err));
          this.kv.poner("cola_estancada", true);
          await this.anotarEnSalud("cola_estancada", { ts: ahora, desde: fila.creado, tipo: fila.tipo });
        } else {
          this.cola.reintentar(fila.id, ahora + Math.min(15 * 60_000, 30_000 * 2 ** fila.intentos));
        }
        // Odoo caído o dormido: no se le insiste con el resto de la cola en esta pasada.
        if (!(err instanceof OdooError) || err.reintentable) {
          this.odooCaido = true;
          break;
        }
      }
    }
    // Se entregó algo y ya no queda nada vencido por tantos intentos: el aviso de /salud se retira.
    if (habiaEstancadas && entregadas > 0 && !this.cola.hayEstancadas(INTENTOS_COLA_RAPIDOS)) {
      this.kv.poner("cola_estancada", null);
      await this.anotarEnSalud("cola_estancada", { ts: this.deps.ahora(), resuelto: true });
    }
  }

  // ── Ráfaga: contestar ─────────────────────────────────────────────────────

  /** Para las pantallas de las vendedoras («el asistente está escribiendo»): una señal al empezar y otra al terminar. */
  private async avisarEscribiendoAOdoo(activo: boolean): Promise<void> {
    if (this.escribiendoEnOdoo === activo) return;
    this.escribiendoEnOdoo = activo;
    const odoo = this.deps.odoo;
    if (this.odooCaido || !odoo.escribiendo) return;
    try {
      await odoo.escribiendo({ canal: this.canalId(), id_externo: this.idExterno(), activo });
    } catch {
      /* es un extra de las pantallas: si no llega, Odoo lo olvida solo al minuto */
    }
  }

  /**
   * La foto de perfil de quien escribe, para el avatar de la pantalla de Odoo. A lo más una vez por semana por conversación (una
   * hora después si algo falló) y con un plazo corto: jamás frena ni rompe la respuesta. Los bytes van solo a Odoo, nunca a la IA.
   */
  private async actualizarFotoDePerfil(cfg: Config): Promise<void> {
    if (!cfg.guardar_foto_perfil || this.odooCaido) return;
    const ahora = this.deps.ahora();
    if (ahora < (this.kv.numero("foto_perfil_proximo") ?? 0)) return;
    const canal = this.canalId();
    const adaptador = this.deps.canal(canal);
    const odoo = this.deps.odoo;
    if (!adaptador?.fotoDePerfil || !odoo.fotoPerfil) return;
    // Se agenda ANTES de intentar: pase lo que pase, no se repite en cada mensaje.
    this.kv.poner("foto_perfil_proximo", ahora + REINTENTO_FOTO_DE_PERFIL_MS);
    let reloj: ReturnType<typeof setTimeout> | undefined;
    try {
      const plazo = new Promise<never>((_, rechazar) => {
        reloj = setTimeout(() => rechazar(new Error("plazo vencido")), PLAZO_FOTO_DE_PERFIL_MS);
      });
      const hecho = (async () => {
        const foto = await adaptador.fotoDePerfil!(canal, this.idExterno(), this.deps.env);
        if (foto) await odoo.fotoPerfil!({ canal, id_externo: this.idExterno(), mime: foto.mime, base64: bytesABase64(foto.bytes) });
      })();
      await Promise.race([hecho, plazo]);
      this.kv.poner("foto_perfil_proximo", ahora + CADA_CUANTO_FOTO_DE_PERFIL_MS);
    } catch (e) {
      this.log("warn", "no se pudo traer la foto de perfil", String(e));
    } finally {
      clearTimeout(reloj);
    }
  }

  private async procesarRafaga(): Promise<void> {
    const pend = this.mensajes.pendientes();
    if (pend.length === 0) return;
    const ids = pend.map((p) => p.id);
    // Se consumen YA: si algo falla a medias, se vuelven a marcar (nunca se contesta dos veces lo mismo).
    this.mensajes.marcarPendientes(ids, false);
    const epoca0 = this.epoca();
    const cfg = await this.deps.config();
    const ahora = this.deps.ahora();
    await this.actualizarFotoDePerfil(cfg);

    if (!cfg.bot_activo_global || !canalActivo(cfg, this.canalId())) {
      this.log("info", "bot apagado en Odoo para este canal: se guarda el mensaje y no se contesta");
      return;
    }
    if (this.silencio(ahora)) return;

    if (this.kv.bandera("pide_persona")) {
      this.kv.poner("pide_persona", null);
      await this.atenderPeticionDePersona(cfg, "El cliente pidió hablar con una persona.");
      return;
    }

    if (planDeIntentos(cfg, "rapido", this.deps.proveedoresDisponibles()).length === 0) {
      // Ningún proveedor de IA tiene clave (p. ej. el primer despliegue, antes de pegar los secretos): el cliente no se
      // queda sin respuesta ni se insiste a ciegas, y /salud dice qué falta.
      await this.alFallarLaIA(cfg, ids, new Error("ningún proveedor de IA tiene clave"), true);
      return;
    }
    try {
      await this.turnoDeIA(cfg, pend, ids, epoca0);
    } finally {
      await this.avisarEscribiendoAOdoo(false);
    }
  }

  private async atenderPeticionDePersona(cfg: Config, motivo: string): Promise<void> {
    const ahora = this.deps.ahora();
    const r = this.odooCaido ? { ok: false as const, resultado: undefined } : await this.deps.odoo.herramienta("pasar_a_vendedora", { motivo }, this.conversacionId());
    let texto: string | null = null;
    if (r.ok) {
      texto = textoDeLaHerramienta(r.resultado);
    } else {
      // Odoo no contestó: el aviso queda en la cola y se entrega apenas Odoo vuelva.
      this.cola.agregar("herramienta", { nombre: "pasar_a_vendedora", argumentos: { motivo } }, ahora);
    }
    const dentro = this.kv.texto("odoo_dentro_horario") !== null ? this.kv.bandera("odoo_dentro_horario") : dentroDeHorario(cfg.horario, ahora);
    texto ??= textoPasoAVendedora(dentro, cfg.horario);
    await this.responder(cfg, texto, [], undefined);
    this.kv.poner("pausa_hasta", ahora + cfg.pausa_por_defecto_minutos * 60_000);
    await this.programar();
  }

  /**
   * El historial que ve el modelo. `ahora` son los mensajes que se están contestando en ESTE turno.
   *
   * Un turno puede terminar de contestar DESPUÉS de que el cliente escribió otra cosa: la respuesta del bot a la primera pregunta se
   * guarda con un id mayor que la segunda pregunta. Si el historial acabara con la voz del propio bot, el modelo lo tomaría como el
   * comienzo de su respuesta (o contestaría vacío). Por eso esa respuesta se coloca justo antes de lo que se contesta ahora.
   */
  private mensajesParaElModelo(ahora: number[] = []): ModelMessage[] {
    let filas = this.mensajes.ultimos(HISTORIAL_PARA_EL_MODELO);
    let fin = filas.length;
    while (fin > 0 && filas[fin - 1].rol === "bot") fin--;
    const cola = filas.slice(fin);
    const primeraDeAhora = filas.findIndex((f) => ahora.includes(f.id));
    if (cola.length > 0 && primeraDeAhora >= 0 && primeraDeAhora < fin) {
      filas = [...filas.slice(0, primeraDeAhora), ...cola, ...filas.slice(primeraDeAhora, fin)];
    }
    const salida: ModelMessage[] = [];
    for (const f of filas) {
      const adj = this.notaDeAdjuntosParaElModelo(f);
      if (f.rol === "cliente") {
        salida.push({ role: "user", content: `${recortarParaElModelo(textoParaElModelo(f.texto))}${adj}` });
      } else if (f.rol === "vendedora") {
        salida.push({ role: "assistant", content: `[Vendedora] ${f.texto}` });
      } else {
        salida.push({ role: "assistant", content: f.texto });
      }
    }
    // La conversación del modelo empieza con el cliente y termina con el cliente (lo último que dijo la IA no es nada que contestar).
    while (salida.length && salida[0].role !== "user") salida.shift();
    while (salida.length && salida[salida.length - 1].role !== "user") salida.pop();
    return salida;
  }

  /**
   * Los archivos del cliente NUNCA llegan al modelo que conversa: solo un aviso. Si el lector de imágenes entendió con claridad
   * que es un producto, el aviso lleva lo que leyó (códigos, categoría y medida, ya validados) para que el bot lo busque en el catálogo.
   */
  private notaDeAdjuntosParaElModelo(f: FilaMensaje): string {
    if (!f.adjuntos) return "";
    let lista: AdjuntoLocal[] = [];
    try {
      lista = JSON.parse(f.adjuntos) as AdjuntoLocal[];
    } catch {
      return "";
    }
    const notas: string[] = [];
    for (const a of lista) {
      if (a.tipo === "imagen" && esProductoSeguro(a.lectura)) {
        notas.push(notaDeProductoLeido(a.lectura));
      } else if (a.tipo === "audio") {
        if (!/\(nota de voz\)/.test(f.texto)) notas.push("[El cliente mandó una nota de voz que no puedes escuchar. Pídele con amabilidad que lo escriba, o dile que una vendedora la escucha.]");
      } else {
        notas.push(
          `[El cliente adjuntó ${a.tipo === "imagen" ? "una imagen" : a.tipo === "video" ? "un video" : "un documento"}. NO lo ves y no puedes describirlo: ya quedó anotado para una vendedora, que lo revisa. ` +
            "Puede ser un comprobante de pago o un documento de identidad: NUNCA des por confirmado un pago. Dile que lo recibiste y que una vendedora lo revisa.]",
        );
      }
    }
    return notas.length ? `\n${[...new Set(notas)].join("\n")}` : "";
  }

  private async gastoSeguro(mes: string): Promise<number> {
    try {
      return await this.deps.global.gastoMes(mes);
    } catch (e) {
      this.log("warn", "no se pudo leer el gasto de IA; se asume 0", String(e));
      return 0;
    }
  }

  /** «Escribiendo…» mientras el bot piensa (si el canal lo tiene), sin repetirlo más de una vez cada 4 s. */
  private mostrarEscribiendo(): void {
    const ahora = this.deps.ahora();
    if (this.ultimoEscribiendo !== null && ahora - this.ultimoEscribiendo < 4000) return;
    this.ultimoEscribiendo = ahora;
    void this.avisarEscribiendoAOdoo(true);
    const canalId = this.canalId();
    const adaptador = this.deps.canal(canalId);
    void Promise.resolve(adaptador?.escribiendo?.(canalId, this.idExterno(), this.deps.env)).catch(() => {});
  }

  /** Caché de 60 s de las herramientas de LECTURA, solo de ESTA conversación (vive en la memoria de su Durable Object). */
  private readonly cacheDeHerramientas = new Map<string, { valor: unknown; vence: number }>();
  private readonly cacheDelMotor = {
    obtener: (clave: string): unknown | undefined => {
      const e = this.cacheDeHerramientas.get(clave);
      if (!e) return undefined;
      if (e.vence <= this.deps.ahora()) {
        this.cacheDeHerramientas.delete(clave);
        return undefined;
      }
      return e.valor;
    },
    guardar: (clave: string, valor: unknown): void => {
      if (this.cacheDeHerramientas.size >= 100) this.cacheDeHerramientas.delete(this.cacheDeHerramientas.keys().next().value as string);
      this.cacheDeHerramientas.set(clave, { valor, vence: this.deps.ahora() + CACHE_DE_HERRAMIENTAS_MS });
    },
  };

  /**
   * Prueba los proveedores en el orden del plan (el principal y luego el respaldo). Cada fallo se anota para /salud; si contesta
   * un proveedor que no es el primero, también. Al final, un último intento tras una pausa por si fue un tropiezo pasajero.
   */
  private async correrConRespaldo(
    plan: SeleccionDeModelo[],
    entrada: Omit<EntradaDelTurno, "modelo" | "proveedor" | "nivel">,
  ): Promise<{ salida: SalidaDelTurno; usado: SeleccionDeModelo }> {
    const intentos = [...plan];
    const reintento = plan.find((p) => p.nivel === "rapido");
    if (reintento) intentos.push(reintento);
    let ultimoError: unknown = new Error("ningún proveedor de IA tiene clave");
    for (let i = 0; i < intentos.length; i++) {
      const sel = intentos[i];
      if (i === intentos.length - 1 && i > 0 && reintento) await this.deps.dormir(2000);
      try {
        const salida = await correrTurno({ ...entrada, modelo: this.deps.modelo(sel), proveedor: sel.proveedor, nivel: sel.nivel });
        if (sel.proveedor !== plan[0].proveedor) {
          this.log("warn", `contestó el respaldo: ${sel.proveedor}/${sel.modelo}`);
          await this.anotarEnSalud("ia_respaldo", { proveedor: sel.proveedor, modelo: sel.modelo, ts: this.deps.ahora() });
        }
        return { salida, usado: sel };
      } catch (e) {
        ultimoError = e;
        const motivo = limpiarError(e);
        this.log("error", `la IA ${sel.proveedor}/${sel.modelo} falló`, motivo);
        await this.anotarEnSalud("ia_fallo", { proveedor: sel.proveedor, modelo: sel.modelo, motivo, ts: this.deps.ahora() });
      }
    }
    throw ultimoError;
  }

  private async anotarEnSalud(clave: string, valor: unknown): Promise<void> {
    try {
      await this.deps.global.guardarSalud?.(clave, JSON.stringify(valor));
    } catch {
      /* /salud es un extra: nunca estorba */
    }
  }

  private async turnoDeIA(cfg: Config, pend: FilaMensaje[], ids: number[], epoca0: number): Promise<void> {
    const ahora = this.deps.ahora();
    const textoReciente = pend.map((p) => p.texto.slice(0, MAX_LETRAS_DE_UN_MENSAJE_PARA_EL_MODELO)).join("\n");
    const nivelPedido = elegirNivel({
      textoDelCliente: textoReciente,
      llamadasRecientes: (this.kv.numero("llamadas_t1") ?? 0) + (this.kv.numero("llamadas_t2") ?? 0),
      busquedaFloja: this.kv.bandera("busqueda_floja"),
    });
    const mes = mesDelNegocio(cfg.horario.zona, ahora);
    // El gasto del mes y la lista de herramientas se piden a la vez: ninguna depende de la otra.
    const [gasto, defs] = await Promise.all([this.gastoSeguro(mes), this.deps.herramientas()]);
    // Sin la lista de herramientas (Odoo no contestó y no hay una anterior) el modelo contestaría de memoria, sin catálogo, precios ni
    // existencias: se prefiere no contestar. Se reintenta con calma y, si Odoo no vuelve, pasa a una vendedora (igual que si fallara la IA).
    if (defs.length === 0) {
      await this.alFallarLaIA(cfg, ids, new Error("Odoo no entregó las herramientas del asistente"));
      return;
    }
    const { nivel, bajo } = aplicarTope(nivelPedido, gasto, cfg.presupuesto_ia_mensual_usd);
    if (bajo) this.log("warn", "tope mensual de IA alcanzado: se usa el modelo económico");
    const plan = planDeIntentos(cfg, nivel, this.deps.proveedoresDisponibles());

    const registro = new RegistroDelTurno();
    const herramientas = construirHerramientas({
      odoo: this.deps.odoo,
      defs,
      conversacionId: () => this.conversacionId(),
      registro,
      sitio: this.deps.urlSitio,
      celularDeLaConversacion: this.kv.texto("celular") ?? undefined,
      omitir: () => this.odooCaido,
      cache: this.cacheDelMotor,
      identidad: `${this.canalId()}:${this.idExterno()}`,
      alEmpezar: () => this.mostrarEscribiendo(),
      fotoPrevia: (c) => {
        const f = this.fotos.buscar(c);
        return f ? { url: f.url, nombre: f.nombre ?? undefined } : undefined;
      },
      fotosYaEnviadas: () => this.fotosEnviadas(),
      textoDelCliente: () => this.mensajes.textosDelCliente(8).join("\n"),
    });

    const primera = !this.kv.numero("bienvenida");
    const estable = promptEstable(cfg);
    const dinamicoBase = (extra = "") =>
      contextoDelChat(cfg, {
        canal: this.canalId(),
        nombreCliente: this.kv.texto("nombre") ?? undefined,
        ahora,
        presentacionEnviada: primera,
        dentroDeHorario: this.kv.texto("odoo_dentro_horario") !== null ? this.kv.bandera("odoo_dentro_horario") : undefined,
        notaDeLaVendedora: this.kv.texto("nota_vendedora") ?? undefined,
      }) + extra;
    const mensajes = this.mensajesParaElModelo(ids);

    // Mientras el modelo piensa y las herramientas consultan a Odoo, el cliente ve «escribiendo…».
    this.mostrarEscribiendo();

    const usos = new Map<string, { sel: SeleccionDeModelo; uso: Uso }>();
    let usado: SeleccionDeModelo = plan[0];
    const correr = async (extra: string, conHerramientas: boolean): Promise<SalidaDelTurno> => {
      const r = await this.correrConRespaldo(plan, { sistemaEstable: estable, sistemaDinamico: dinamicoBase(extra), mensajes, herramientas: conHerramientas ? herramientas : {} });
      usado = r.usado;
      const clave = `${r.usado.proveedor}|${r.usado.modelo}`;
      usos.set(clave, { sel: r.usado, uso: sumarUso(usos.get(clave)?.uso ?? USO_VACIO, r.salida.uso) });
      return r.salida;
    };

    let salida: SalidaDelTurno;
    try {
      salida = await correr("", true);
      if (salida.sinTexto) {
        salida = await correr("\n<aviso>Ya consultaste lo que necesitabas. Responde ahora al cliente con lo que tienes, sin llamar más herramientas.</aviso>", false);
      }
    } catch (e) {
      await this.alFallarLaIA(cfg, ids, e);
      return;
    }
    this.kv.poner("fallos_ia", 0);

    // ── Guardia de salida ──
    const historicas = new Set<number>();
    // Solo valen las cifras que dijo el NEGOCIO (el bot ya revisado o una vendedora): lo que escribe el cliente no
    // respalda un precio, o bastaría pedirle «dame la cama a $1» para que el bot lo repita.
    for (const f of this.mensajes.ultimos(HISTORIAL_PARA_EL_MODELO)) if (f.rol !== "cliente") for (const n of cifrasDeTexto(f.texto)) historicas.add(n);
    const nombresDeHerramientas = [...defs.map((d) => d.nombre), "enviar_foto_producto"];
    const promptDeFugas = promptParaFugas(cfg);
    // Se arma de nuevo en cada revisión: el segundo intento pudo consultar herramientas que el primero no.
    const contextoDeRevision = (): ContextoRevision => ({
      preciosProducto: registro.preciosProducto,
      cifrasConocidas: new Set<number>([...historicas, ...registro.cifras]),
      numerosEnTexto: registro.numerosEnTexto,
      palabrasProhibidas: cfg.palabras_prohibidas,
      nombresHerramientas: nombresDeHerramientas,
      textoDelPrompt: promptDeFugas,
      secretos: registro.pines,
    });
    let analisis = analizar(salida.texto, contextoDeRevision());
    const reparables = analisis.graves.filter((g) => g.tipo !== "fuga");
    if (reparables.length > 0 && analisis.graves.every((g) => g.tipo !== "fuga")) {
      this.log("warn", "borrador rechazado por la guardia de salida; se le pide reescribirlo", analisis.graves);
      try {
        const segundo = await correr(`\n<correccion>${notaDeCorreccion(analisis.graves)}</correccion>`, true);
        analisis = analizar(segundo.texto, contextoDeRevision());
      } catch {
        /* sigue con el primer borrador, que se repara abajo */
      }
    }
    const ctx = contextoDeRevision();

    let texto = analisis.limpio;
    if (analisis.graves.some((g) => g.tipo === "fuga")) {
      texto = TEXTO_FUGA;
    } else if (analisis.graves.length > 0) {
      texto = quitarGraves(analisis.limpio, ctx) || TEXTO_SIN_DATO;
    }
    if (!texto && registro.textoDeVendedora) texto = limpiarForma(registro.textoDeVendedora);
    if (!texto) texto = TEXTO_SIN_DATO;

    // El gasto se anota aunque la respuesta no llegue a salir (cada modelo con SU precio).
    for (const { sel, uso } of usos.values()) await this.anotarGasto(mes, sel.modelo, uso, cfg);

    // Una pregunta que la base de conocimiento no supo contestar queda registrada para que las vendedoras la completen:
    // no depende de que el modelo se acuerde de llamar la herramienta.
    if (registro.busquedasFlojas > 0 && registro.consultasUtiles === 0 && !registro.preguntaRegistrada && defs.some((d) => d.nombre === "registrar_pregunta_sin_respuesta")) {
      this.cola.agregar(
        "herramienta",
        {
          nombre: "registrar_pregunta_sin_respuesta",
          argumentos: { pregunta: textoParaElModelo(textoReciente).slice(0, 500), resumen: "Registrada automáticamente: la base de conocimiento no tenía respuesta." },
        },
        ahora,
      );
    }
    this.kv.poner("busqueda_floja", registro.busquedasFlojas > 0 || registro.preguntaRegistrada);

    // ── Última puerta: ¿alguien tomó la conversación mientras el bot pensaba? ──
    if (!(await this.puedeEnviar(epoca0, registro.pasoAVendedora))) {
      this.log("info", "una persona tomó la conversación mientras el bot pensaba: no se envía");
      return;
    }

    for (const [codigo, f] of registro.fotos) this.fotos.guardar(codigo, f.url, f.nombre, ahora);
    const ultimoIdAntes = this.mensajes.ultimos(1)[0]?.id ?? 0;
    try {
      await this.responder(cfg, texto, registro.medios, usado.modelo);
    } catch (e) {
      // La respuesta ya estaba lista (y pagada) pero no salió: no se pierde en silencio.
      await this.alFallarElEnvio(cfg, ids, e, ultimoIdAntes);
      return;
    }
    this.kv.poner("fallos_envio", 0);

    this.kv.poner("llamadas_t2", this.kv.numero("llamadas_t1") ?? 0);
    this.kv.poner("llamadas_t1", registro.llamadas.length);
    for (const pin of new Set(registro.pines)) this.mensajes.redactar(pin, MARCA_PIN);
    // Un PIN escrito en el chat no se queda en la historia que se le muestra al modelo, lo haya usado o no.
    for (const pin of new Set(pend.flatMap((p) => pinesEscritos(p.texto)))) this.mensajes.redactar(pin, MARCA_PIN);
    if (registro.pasoAVendedora) this.kv.poner("pausa_hasta", this.deps.ahora() + cfg.pausa_por_defecto_minutos * 60_000);
  }

  private async anotarGasto(mes: string, modelo: string, uso: Uso, cfg: Config): Promise<void> {
    const costo = costoDe(modelo, uso, cfg.precios_ia);
    if (costo.estimado) this.log("warn", `el modelo ${modelo} no tiene precio cargado en Odoo (precios_ia): el gasto se estima con la tarifa de reserva`);
    try {
      await this.deps.global.registrarGasto(mes, modelo, uso, costo.usd, costo.estimado, diaDelNegocio(cfg.horario.zona, this.deps.ahora()));
    } catch (e) {
      this.log("warn", "no se pudo anotar el gasto de IA", String(e));
    }
  }

  /** La IA falló del todo: se reintenta con calma; si sigue fallando, no se deja al cliente sin respuesta. */
  private async alFallarLaIA(cfg: Config, ids: number[], e: unknown, definitivo = false): Promise<void> {
    const fallos = this.kv.sumar("fallos_ia");
    this.log("error", `la IA falló (${fallos})`, e instanceof Error ? e.message : String(e));
    if (!definitivo && fallos <= REINTENTOS_DE_IA.length) {
      this.mensajes.marcarPendientes(ids, true);
      this.kv.poner("t_rafaga", this.deps.ahora() + REINTENTOS_DE_IA[fallos - 1]);
      return;
    }
    this.kv.poner("fallos_ia", 0);
    const motivo = "Falla técnica del asistente: no pudo responder al cliente. Atender a mano.";
    this.cola.agregar("herramienta", { nombre: "pasar_a_vendedora", argumentos: { motivo } }, this.deps.ahora());
    await this.responder(cfg, TEXTO_FALLO_TECNICO, [], undefined);
    this.kv.poner("pausa_hasta", this.deps.ahora() + cfg.pausa_por_defecto_minutos * 60_000);
  }

  /**
   * La respuesta estaba lista pero el canal no la dejó salir. Si no salió NADA, se reintenta el turno con calma (como si fallara la IA);
   * si ya salió una parte, no se repite (el cliente vería dos veces lo mismo) y se avisa a una vendedora. Tras los reintentos, igual.
   */
  private async alFallarElEnvio(cfg: Config, ids: number[], e: unknown, ultimoIdAntes: number): Promise<void> {
    const ahora = this.deps.ahora();
    const algoSalio = this.mensajes.ultimos(10).some((f) => f.id > ultimoIdAntes && f.rol === "bot");
    const fallos = this.kv.sumar("fallos_envio");
    this.log("error", `la respuesta estaba lista pero no salió por el canal (${fallos})`, e instanceof Error ? e.message : String(e));
    if (!algoSalio && fallos <= REINTENTOS_DE_IA.length) {
      this.mensajes.marcarPendientes(ids, true);
      this.kv.poner("t_rafaga", ahora + REINTENTOS_DE_IA[fallos - 1]);
      return;
    }
    this.kv.poner("fallos_envio", 0);
    if (algoSalio && !this.kv.numero("bienvenida")) this.kv.poner("bienvenida", ahora);
    const motivo = algoSalio
      ? "La respuesta del asistente se envió a medias: el canal falló. Revisar la conversación y escribirle al cliente."
      : "El canal no dejó entregar la respuesta del asistente. Atender a mano.";
    this.cola.agregar("herramienta", { nombre: "pasar_a_vendedora", argumentos: { motivo } }, ahora);
    this.kv.poner("pausa_hasta", ahora + cfg.pausa_por_defecto_minutos * 60_000);
  }

  /** El re-chequeo con Odoo justo antes de enviar (docs/JUAN.md, `GET /estado`). */
  private async puedeEnviar(epoca0: number, loCausoEsteTurno: boolean): Promise<boolean> {
    if (this.epoca() !== epoca0) return false;
    // Si ESTE turno pasó la conversación a una vendedora, la pausa es nuestra: el último mensaje sí sale.
    if (loCausoEsteTurno) return true;
    try {
      if (this.odooCaido) throw new Error("Odoo no contestó en esta pasada");
      const e = await this.deps.odoo.estado(this.canalId(), this.idExterno());
      this.aplicarEstadoDeOdoo(e);
    } catch (err) {
      // Odoo no contestó: se sigue con lo último que se sabía (el mensaje de hace unos segundos).
      this.log("warn", "no se pudo re-chequear el estado en Odoo; se usa el último conocido", String(err));
    }
    return this.epoca() === epoca0 && !this.silencio();
  }

  // ── Salida ────────────────────────────────────────────────────────────────

  private presentacion(cfg: Config): string[] {
    const propia = cfg.mensaje_bienvenida;
    // La bienvenida de Odoo manda, salvo que afirme ser una persona real (Juan nunca lo dice): entonces se usa la de siempre.
    const base = propia?.trim() && detectarSerHumano(propia).length === 0 ? propia : presentacionPorDefecto(cfg.nombre_publico);
    const priv = cfg.texto_privacidad_corto;
    return partirEnBurbujas(priv ? `${base}\n${priv}` : base, { objetivo: 520, maxLineas: 6 });
  }

  /** Texto del modelo → burbujas cortas (con la presentación delante si es el primer mensaje) → canal. */
  private async responder(cfg: Config, texto: string, medios: MedioSaliente[], modelo: string | undefined): Promise<void> {
    const burbujas = partirEnBurbujas(texto);
    const primera = !this.kv.numero("bienvenida");
    const todas = primera ? [...this.presentacion(cfg), ...burbujas] : burbujas;
    await this.emitir({ burbujas: todas, medios, autor: "bot", registrar: true, modelo });
    if (primera) this.kv.poner("bienvenida", this.deps.ahora());
  }

  /** Direcciones de las fotos que este bot ya le mandó al cliente (para que «más fotos» no repita). Las últimas 80. */
  private fotosEnviadas(): Set<string> {
    try {
      const v: unknown = JSON.parse(this.kv.texto("fotos_enviadas") ?? "[]");
      return new Set(Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []);
    } catch {
      return new Set();
    }
  }

  private recordarFotos(urls: string[]): void {
    if (urls.length === 0) return;
    this.kv.poner("fotos_enviadas", JSON.stringify([...new Set([...this.fotosEnviadas(), ...urls])].slice(-80)));
  }

  /**
   * Envía por el canal, lo anota en el historial local y (si toca) lo encola para Odoo.
   *
   * Si el canal se corta a la mitad (`EnvioParcialError`), lo ya enviado no se repite: se reintenta solo lo que falta, y lo que sí
   * salió igual queda anotado. `progreso` permite seguir donde se quedó un envío anterior (el reintento de Odoo con el mismo `id_envio`).
   */
  private async emitir(o: { burbujas: string[]; medios: MedioSaliente[]; autor: "bot" | "vendedora"; registrar: boolean; modelo?: string; progreso?: ProgresoDeEnvio; alAvanzar?: (p: ProgresoDeEnvio) => void }): Promise<string[]> {
    const canalId = this.canalId();
    const adaptador = this.deps.canal(canalId);
    if (!adaptador) throw new Error(`no hay adaptador para el canal ${canalId}`);
    const cap = adaptador.capacidades(canalId);

    // Lo que el canal no puede llevar como archivo, sale como enlace en el texto.
    const enlaces: string[] = [];
    const medios = o.medios.filter((m) => {
      const soporta = m.tipo === "imagen" ? cap.imagenes : cap.documentos;
      if (!soporta) enlaces.push(m.nombre ? `${m.nombre}: ${m.url}` : m.url);
      return soporta;
    });
    const burbujas = [...o.burbujas, ...enlaces].flatMap((b) => partirPorLargo(b, cap.maxTexto)).filter((b) => b.trim());
    if (burbujas.length === 0 && medios.length === 0) return [];

    const progreso = o.progreso ?? { burbujas: 0, medios: 0, ids: [] };
    const inicio = { burbujas: progreso.burbujas, medios: progreso.medios, ids: progreso.ids.length };
    const falta = () => progreso.burbujas < burbujas.length || progreso.medios < medios.length;
    // Antes de enviar (despedidas, seguimientos...) también; si ya se mostró hace poco, no se repite.
    if (o.autor === "bot") this.mostrarEscribiendo();

    let fallo: unknown = null;
    for (let intento = 0; falta(); intento++) {
      const salida: Saliente = {
        para: this.idExterno(),
        burbujas: burbujas.slice(progreso.burbujas),
        medios: medios.slice(progreso.medios),
        esperaMs: ESPERA_ENTRE_BURBUJAS_MS,
      };
      try {
        const r = await adaptador.enviar(canalId, salida, this.deps.env);
        progreso.burbujas = burbujas.length;
        progreso.medios = medios.length;
        progreso.ids.push(...r.ids);
        fallo = null;
      } catch (e) {
        fallo = e;
        if (e instanceof EnvioParcialError) {
          progreso.burbujas = Math.min(burbujas.length, progreso.burbujas + e.enviado.burbujas);
          progreso.medios = Math.min(medios.length, progreso.medios + e.enviado.medios);
          progreso.ids.push(...e.enviado.ids);
        }
      }
      o.alAvanzar?.(progreso);
      if (fallo === null || intento >= 1) break;
      await this.deps.dormir(1500);
    }

    // Lo que SÍ salió se anota aunque el envío haya terminado mal.
    const ahora = this.deps.ahora();
    const salieronBurbujas = burbujas.slice(inicio.burbujas, progreso.burbujas);
    const salieronMedios = medios.slice(inicio.medios, progreso.medios);
    for (const id of progreso.ids.slice(inicio.ids)) this.kv.poner(`env:${id}`, ahora);
    for (const b of salieronBurbujas) this.mensajes.insertar({ id_mensaje: null, rol: o.autor, texto: b, ts: ahora, modelo: o.modelo });
    // El pie de lo que escribió una vendedora se guarda con la foto: así el asistente sabe qué se le dijo al cliente.
    for (const m of salieronMedios) this.mensajes.insertar({ id_mensaje: null, rol: o.autor, texto: `${etiquetaDeMedio(m)}${o.autor === "vendedora" && m.pie ? ` ${m.pie}` : ""}`, ts: ahora, modelo: o.modelo });
    if (o.autor === "bot") this.recordarFotos(salieronMedios.filter((m) => m.tipo === "imagen").map((m) => m.url));

    if (o.registrar && (salieronBurbujas.length > 0 || salieronMedios.length > 0)) {
      this.cola.agregar(
        "mensaje",
        this.cuerpoDeMensaje(
          { canal: canalId, id_externo: this.idExterno(), id_mensaje: "" },
          [...salieronBurbujas, ...salieronMedios.map(etiquetaDeMedio)].join("\n"),
          o.autor,
          "saliente",
          // Lo que ya vive en Odoo (la cotización en PDF) no se baja otra vez: solo queda la línea de texto.
          salieronMedios.filter((m) => !m.sinCopia).map((m) => ({ tipo: m.tipo, url: m.url, nombre: m.nombre, mime: m.mime })),
          ahora,
          `${o.autor}-${this.deps.uuid()}`,
        ),
        ahora,
      );
      await this.programar();
    }
    if (fallo !== null) {
      this.log("error", "no se pudo enviar por el canal", fallo instanceof Error ? fallo.message : String(fallo));
      // Para /salud (y la pantalla de Conexiones de Odoo): el motivo, sin datos de nadie. Así un fallo repetido se ve sin abrir los registros.
      this.kv.poner("envio_fallo_abierto", true);
      await this.anotarEnSalud("envio_fallo", { canal: canalId, motivo: motivoDeEnvio(fallo), con_archivos: medios.length > 0, ts: ahora });
      throw fallo;
    }
    if (this.kv.bandera("envio_fallo_abierto")) {
      this.kv.poner("envio_fallo_abierto", null);
      await this.anotarEnSalud("envio_fallo", { canal: canalId, resuelto: true, ts: ahora });
    }
    return progreso.ids;
  }

  // ── Odoo → Worker ─────────────────────────────────────────────────────────

  /**
   * `POST /odoo/enviar`: una vendedora escribe desde Odoo. Sin IA, sin ráfaga.
   *
   * Con `id_envio` es idempotente: Odoo reintenta cuando no oyó la respuesta (se cayó la red, el Worker tardó más de 25 s), y ese
   * reintento NO vuelve a mandar al cliente lo que ya salió. Si ese mismo envío todavía está saliendo, el reintento espera.
   */
  async enviarVendedora(s: SolicitudEnviar): Promise<{ ok: true; id_mensaje: string; repetido?: true }> {
    const idEnvio = s.id_envio || null;
    const previo = idEnvio ? this.envioRecordado(idEnvio) : null;
    if (previo?.e === "listo") return { ok: true, id_mensaje: previo.id ?? `vendedora-${idEnvio}`, repetido: true };
    if (previo?.e === "curso" && this.deps.ahora() - previo.ts < ENVIO_EN_CURSO_MS) {
      throw new Error("Ese mensaje ya se está enviando: se reintenta en un momento.");
    }

    // Se marca «saliendo» ANTES de cualquier espera: dos peticiones iguales que llegan casi juntas no pueden pasar las dos.
    // Un envío cortado a la mitad sigue donde se quedó: lo que ya salió no se repite.
    const progreso: ProgresoDeEnvio = previo ? { burbujas: previo.b, medios: previo.m, ids: [...previo.ids] } : { burbujas: 0, medios: 0, ids: [] };
    const recordar = (e: EnvioRecordado["e"], id?: string) => {
      if (idEnvio) this.kv.poner(`${PREFIJO_ID_ENVIO}${idEnvio}`, JSON.stringify({ e, ts: this.deps.ahora(), b: progreso.burbujas, m: progreso.medios, ids: progreso.ids, ...(id ? { id } : {}) } satisfies EnvioRecordado));
    };
    recordar("curso");

    let ids: string[];
    try {
      const cfg = await this.deps.config();
      const ahora = this.deps.ahora();
      const medios: MedioSaliente[] = [];
      const extra: string[] = [];
      for (const a of s.adjuntos ?? []) {
        if (a.tipo === "imagen" || a.tipo === "documento") medios.push({ tipo: a.tipo, url: a.url, nombre: a.nombre, mime: a.mime });
        else extra.push(a.nombre ? `${a.nombre}: ${a.url}` : a.url); // audio y video salen como enlace
      }
      const texto = (s.texto ?? "").trim();
      let burbujas = [...(texto ? [texto] : []), ...extra];
      if (burbujas.length === 0 && medios.length === 0) throw new Error("No hay nada que enviar.");
      // Una foto o un documento con su texto: el texto viaja como pie de la primera (una sola burbuja para el cliente), si el canal
      // lo permite y cabe. Si no, sale como siempre: el texto y luego los archivos.
      const canalId = this.canalId();
      if (texto && medios.length > 0 && extra.length === 0 && texto.length <= MAX_PIE_DE_FOTO && this.deps.canal(canalId)?.capacidades(canalId).pie) {
        medios[0] = { ...medios[0], pie: texto };
        burbujas = [];
      }
      // Primero se corta lo que el bot traiga a medias: una persona está escribiendo.
      this.humanoIntervino(cfg, ahora);
      ids = await this.emitir({ burbujas, medios, autor: "vendedora", registrar: false, progreso, alAvanzar: () => recordar("curso") });
    } catch (err) {
      if (progreso.burbujas + progreso.medios > 0) recordar("parcial");
      else if (idEnvio) this.kv.poner(`${PREFIJO_ID_ENVIO}${idEnvio}`, null);
      throw err;
    }
    const idMensaje = ids[0] ?? `vendedora-${this.deps.uuid()}`;
    recordar("listo", idMensaje);
    await this.programar();
    return { ok: true, id_mensaje: idMensaje };
  }

  /** Lo que se recuerda de un envío de Odoo con ese `id_envio`, o null. */
  private envioRecordado(idEnvio: string): EnvioRecordado | null {
    const crudo = this.kv.texto(`${PREFIJO_ID_ENVIO}${idEnvio}`);
    if (!crudo) return null;
    try {
      const v = JSON.parse(crudo) as Partial<EnvioRecordado>;
      if ((v.e !== "curso" && v.e !== "parcial" && v.e !== "listo") || typeof v.ts !== "number") return null;
      return { e: v.e, ts: v.ts, b: Number(v.b) || 0, m: Number(v.m) || 0, ids: Array.isArray(v.ids) ? v.ids.filter((x): x is string => typeof x === "string") : [], ...(typeof v.id === "string" ? { id: v.id } : {}) };
    } catch {
      return null;
    }
  }

  /** `POST /odoo/estado`: tomar o devolver la conversación. */
  async fijarEstado(s: { estado: "humano" | "bot"; pausada_hasta?: string | number | null; nota_para_el_bot?: string | null }): Promise<{ ok: true }> {
    const cfg = await this.deps.config();
    const ahora = this.deps.ahora();
    if (s.estado === "humano") {
      this.humanoIntervino(cfg, ahora, aMilisegundosOdoo(s.pausada_hasta));
      // Quien toma la conversación borra la nota anterior (Odoo hace lo mismo).
      this.kv.poner("nota_vendedora", null);
    } else {
      // Al devolverla puede venir una nota («ya quedó la visita del sábado»): el bot la lee hasta que otra persona tome la conversación.
      this.kv.poner("nota_vendedora", limpiarNota(s.nota_para_el_bot));
      this.kv.poner("pausa_hasta", null);
      this.kv.poner("odoo_estado", "bot");
      this.kv.poner("odoo_pausa_hasta", null);
      this.kv.poner("odoo_bot_activo", true);
      this.kv.poner("descanso_hasta", null);
    }
    await this.programar();
    return { ok: true };
  }

  /** `POST /odoo/seguimiento`: redactar y enviar el seguimiento n.º 1 o 2. */
  async seguimiento(s: SolicitudSeguimiento): Promise<ResultadoSeguimiento> {
    const numero = s.numero === 1 || s.numero === 2 ? s.numero : null;
    if (numero === null) return { ok: false, error: "numero debe ser 1 o 2" };
    const cfg = await this.deps.config();
    const ahora = this.deps.ahora();
    const canalId = this.canalId();
    if (!canalId) return { ok: false, error: "conversación desconocida para este Worker" };
    if (!cfg.bot_activo_global || !canalActivo(cfg, canalId)) return { ok: true, resultado: "pospuesto", motivo: "el bot está apagado" };

    const cierra = async (resultado: "descartado", motivo: string): Promise<ResultadoSeguimiento> => {
      await this.deps.odoo.seguimientoHecho({ conversacion_id: s.conversacion_id, numero, resultado, motivo }).catch((e) => this.log("warn", "seguimiento/hecho", String(e)));
      return { ok: true, resultado, motivo };
    };

    const clave = `${numero}:${s.contexto?.ultimo_mensaje_ts ?? ""}`;
    if (this.deps.sql.uno("SELECT 1 AS x FROM seguimientos WHERE clave = ?", clave)) {
      return { ok: true, resultado: "descartado", motivo: "ya se envió este seguimiento" };
    }
    if (this.kv.bandera("sin_seguimiento")) return cierra("descartado", "el cliente pidió que no lo contacten");

    const visto = s.contexto?.ultimo_mensaje_ts !== undefined ? aMsDeContexto(s.contexto.ultimo_mensaje_ts) : null;
    const ultimoCliente = this.kv.numero("ultimo_cliente_ts");
    if (visto !== null && ultimoCliente !== null && ultimoCliente > visto + 1000) return cierra("descartado", "el cliente ya volvió a escribir");

    const adaptador = this.deps.canal(canalId);
    if (adaptador?.capacidades(canalId).ventana24h && ultimoCliente !== null && ahora - ultimoCliente > VENTANA_24H_MS) {
      return cierra("descartado", "fuera de la ventana de 24 h del canal");
    }

    if (this.silencio(ahora)) return cierra("descartado", "una vendedora tiene la conversación");
    let dentro: boolean | undefined;
    try {
      const e = await this.deps.odoo.estado(canalId, this.idExterno());
      this.aplicarEstadoDeOdoo(e);
      if (this.silencio(ahora)) return cierra("descartado", "una vendedora tiene la conversación");
      dentro = e.dentro_de_horario;
    } catch (err) {
      this.log("warn", "seguimiento: no se pudo consultar el estado", String(err));
      return { ok: false, error: "no se pudo consultar el estado en Odoo" };
    }
    // Manda el horario que calcula Odoo; el de la configuración solo si Odoo no lo dijo.
    if (cfg.seguimiento.solo_horario_laboral && !(dentro ?? dentroDeHorario(cfg.horario, ahora))) {
      return { ok: true, resultado: "pospuesto", motivo: "fuera del horario laboral" };
    }

    // ── Redactar (sin herramientas: no puede traer precios ni existencias) ──
    const epoca0 = this.epoca();
    const mes = mesDelNegocio(cfg.horario.zona, ahora);
    // El seguimiento siempre es del nivel económico: redactar dos líneas no necesita más (y respeta el tope).
    const plan = planDeIntentos(cfg, "rapido", this.deps.proveedoresDisponibles());
    if (plan.length === 0) return { ok: false, error: "ningún proveedor de IA tiene clave" };
    const reciente = this.mensajesParaElModelo().slice(-6);
    let r: { salida: SalidaDelTurno; usado: SeleccionDeModelo };
    try {
      r = await this.correrConRespaldo(plan, {
        sistemaEstable: promptSeguimiento(cfg, { numero, interes: s.contexto?.interes ?? "", ahora, nombreCliente: this.kv.texto("nombre") ?? undefined }),
        sistemaDinamico: "Redacta el mensaje de seguimiento ahora.",
        mensajes: reciente.length ? reciente : [{ role: "user", content: "(sin mensajes)" }],
        herramientas: {},
        cachear: false,
      });
    } catch (err) {
      this.log("error", "seguimiento: la IA falló", limpiarError(err));
      return { ok: false, error: "la IA no pudo redactar el seguimiento" };
    }
    const modelo = r.usado.modelo;
    await this.anotarGasto(mes, modelo, r.salida.uso, cfg);

    // Un seguimiento no lleva cifras de dinero: cualquiera es una invención.
    const ctx: ContextoRevision = { preciosProducto: new Set(), cifrasConocidas: new Set(), palabrasProhibidas: cfg.palabras_prohibidas, textoDelPrompt: promptParaFugas(cfg) };
    const a = analizar(r.salida.texto, ctx);
    const texto = a.graves.length ? quitarGraves(a.limpio, ctx) : a.limpio;
    if (!texto) return { ok: false, error: "el borrador del seguimiento no pasó la guardia de salida" };

    if (!(await this.puedeEnviar(epoca0, false))) return cierra("descartado", "una vendedora tomó la conversación");

    try {
      await this.emitir({ burbujas: partirEnBurbujas(texto, { maxBurbujas: 2 }), medios: [], autor: "bot", registrar: true, modelo });
    } catch (err) {
      return { ok: false, error: `no se pudo enviar: ${err instanceof Error ? err.message : String(err)}` };
    }
    this.deps.sql.correr("INSERT OR REPLACE INTO seguimientos (clave, ts) VALUES (?, ?)", clave, ahora);
    await this.deps.odoo.seguimientoHecho({ conversacion_id: s.conversacion_id, numero, resultado: "enviado" }).catch((e) => this.log("warn", "seguimiento/hecho", String(e)));
    return { ok: true, resultado: "enviado" };
  }

  /** Un archivo guardado para Odoo (la ruta pública `/media/...` ya verificó la firma). */
  leerMedio(id: string): { bytes: Uint8Array; mime: string; nombre: string | null } | null {
    return this.medios.leer(id, this.deps.ahora());
  }

  /**
   * «Borrar mis datos» (Ley 81): Odoo ya borró la conversación y aquí se borra la copia de trabajo (mensajes, cola,
   * archivos, memoria de la persona). Sin esto, el bot seguiría «recordando» lo que se borró. Devuelve cuántos mensajes había.
   */
  async olvidar(): Promise<{ ok: true; mensajes: number }> {
    const mensajes = this.deps.sql.uno<{ n: number }>("SELECT COUNT(*) AS n FROM mensajes")?.n ?? 0;
    for (const tabla of ["mensajes", "cola", "medios", "fotos", "enviados", "seguimientos", "kv"]) this.deps.sql.correr(`DELETE FROM ${tabla}`);
    await this.deps.fijarAlarma(null);
    return { ok: true, mensajes };
  }

  /** Para las pruebas y el diagnóstico. */
  resumen() {
    return {
      canal: this.kv.texto("canal"),
      id_externo: this.kv.texto("id_externo"),
      conversacion_id: this.conversacionId(),
      silencio: this.silencio(),
      pendientes: this.mensajes.pendientes().length,
      cola: this.deps.sql.uno<{ n: number }>("SELECT COUNT(*) AS n FROM cola")?.n ?? 0,
    };
  }
}

/** Lo que Odoo necesita saber de una imagen leída: su clase y si es sensible. Ante cualquier señal de pago o identidad, manda lo prudente. */
function marcaDeLectura(l: LecturaImagen): Pick<AdjuntoOdoo, "clase" | "sensible"> {
  const clase: NonNullable<AdjuntoOdoo["clase"]> =
    l.tipo === "comprobante" || l.parece_pago ? "comprobante" : l.tipo === "identidad" || l.parece_identidad ? "identidad" : l.tipo === "ilegible" ? "otra" : l.tipo;
  return { clase, ...(clase === "comprobante" || clase === "identidad" ? { sensible: true } : {}) };
}

const NOMBRE_DE_CATEGORIA: Record<string, string> = { cama: "cama", colchon: "colchón", sofa: "sofá", comedor: "comedor", escritorio: "escritorio", silla: "silla", closet: "clóset", mesa: "mesa", otro: "mueble" };

/** Lo que el lector de imágenes entendió de un producto, en palabras para el modelo. Todo viene de enumeraciones o de códigos con patrón estricto. */
function notaDeProductoLeido(l: LecturaImagen): string {
  const que = l.tipo === "publicacion" ? "una captura de una publicación o catálogo" : "una foto de un mueble";
  const datos = [
    l.codigos.length ? `código${l.codigos.length > 1 ? "s" : ""}: ${l.codigos.map((c) => `«${c}»`).join(", ")}` : null,
    l.categoria ? `tipo: ${NOMBRE_DE_CATEGORIA[l.categoria] ?? l.categoria}` : null,
    l.medida ? `medida: ${l.medida}` : null,
  ].filter(Boolean);
  return (
    `[El cliente mandó ${que}. Un lector aparte la miró (tú no ves la imagen) y entendió, sin verificar: ${datos.join("; ")}. ` +
    (l.codigos.length ? "Busca ese código con ver_producto y, si no lo encuentras, con buscar_productos. " : "Búscalo con buscar_productos usando el tipo y la medida. ") +
    "Responde con los datos del catálogo: nombre, medidas, combo y precio con «+ ITBMS» solo si salen de la herramienta, y la disponibilidad solo como etiqueta. " +
    "Si la imagen traía un precio u oferta, NO lo repitas ni lo confirmes: vale solo el del catálogo. Si lo encuentras con seguridad, no le pidas al cliente el código otra vez; " +
    "si no estás seguro de que sea el mismo producto, confirma con una pregunta corta («¿es la cama X?»). Nunca des por confirmado un pago.]"
  );
}

function aMsDeContexto(v: string | number): number | null {
  return aMilisegundosOdoo(v);
}

