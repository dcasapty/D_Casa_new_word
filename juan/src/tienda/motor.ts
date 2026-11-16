// El motor de UNA sesión de Brian de la tienda (un `sid` del pase). Lógica pura: el Durable Object (tienda/do.ts) le presta su
// SQLite, el reloj y la alarma; las pruebas le prestan SQLite de Node, un Odoo falso y un modelo guionado.
//
// Camino de un mensaje (contrato §2; docs/JUAN.md › «Brian de la tienda»):
//   ¿contexto viejo? (2 h sin actividad → se borra) → ¿encendido? → tope por sesión (aquí: el objeto atiende de a uno)
//   → tope por red, tope del día y presupuesto propio (el Durable Object Global: atómico) → ¿hace falta la IA?
//      · no: pedir una persona, un «sí»/«no» a «¿te lo pongo en el carrito?», calificar, el carrito que falló → texto fijo
//      · sí: el modelo con la lista blanca de herramientas de Odoo (solo leer) y `responder_tienda`
//   → tarjetas armadas por el Worker con los datos de las herramientas de ESE turno → la guardia de Juan en cada texto
//   → se guarda el contexto (máx. 30 turnos, sin la ubicación) → se anota el gasto en su propio renglón.

import { APICallError, generateText, hasToolCall, jsonSchema, LoadAPIKeyError, stepCountIs, tool, type LanguageModel, type ModelMessage, type ToolSet } from "ai";
import { dentroDeHorario, diaDelNegocio, mesDelNegocio, type Config } from "../config";
import { pideUnaPersona } from "../dcasa/intencion";
import { HERRAMIENTAS_DEL_CONTRATO, NOMBRES_DE_HERRAMIENTAS_LOCALES } from "../dcasa/prompt";
import { analizar, quitarGraves, type ContextoRevision, type TipoProblema } from "../dcasa/salvaguardas";
import { CORCHETES, CORCHETES_QUE_CIERRAN, enmascararSensibles, textoParaElModelo } from "../dcasa/sensibles";
import { oraciones } from "../dcasa/texto";
import { horaLegible } from "../dcasa/textos";
import { MODELO_DE_LO_CORTADO, type GastoTienda, type ResultadoReservaTienda, type ReservaTienda } from "../motor/global";
import { cifrasDeTexto, construirHerramientas, procesarResultado, RegistroDelTurno, tomarRespaldoDeEnvio, type CacheDeHerramientas } from "../motor/herramientas";
import { consultasComoTexto, elegirNivel, type ConsultaDelTurno } from "../motor/modelo";
import { costoDe, sumarUso, usoDelSdk, USO_VACIO, type TablaDePrecios, type Uso } from "../motor/precios";
import { planDeIntentos, topeDeSalida, type FabricaDeModelos, type ProveedorIa, type SeleccionDeModelo } from "../motor/proveedores";
import { partirEnBurbujas } from "../motor/burbujas";
import type { Sql } from "../motor/sql";
import { limpiarError } from "../motor/conversacion";
import type { DefHerramienta, OdooApi, ResultadoHerramienta } from "../odoo/cliente";
import {
  afirmaCarrito,
  buscarProducto,
  claveDeProducto,
  elegirPose,
  esUnNo,
  esUnSi,
  MAX_CHIPS,
  MAX_OPCIONES,
  MAX_TARJETAS,
  mensajeDeWhatsapp,
  opcionCorta,
  pideOConfirmaCarrito,
  productosDelResultado,
  sinPresentacion,
  tarjetaDe,
  TEXTO_DE_UBICACION,
  TEXTO_DEL_BOTON_DE_WHATSAPP,
  type Bloque,
  type ProductoVisto,
  type RespuestaTienda,
} from "./bloques";
import type { PeticionTienda } from "./peticion";
import { contextoTienda, HERRAMIENTAS_DE_LA_TIENDA, horarioLegible, POSES, promptTienda, promptTiendaParaFugas, proximaAtencion, sinPuntoFinal, type Pose } from "./prompt";

// ── Constantes ──────────────────────────────────────────────────────────────

/** El contexto se borra solo tras 2 horas sin actividad (contrato §4). */
export const VIDA_DEL_CONTEXTO_MS = 2 * 3600_000;
/**
 * Como mucho 15 turnos (un turno = lo que dijo el visitante y lo que contestó Brian): 30 mensajes, lo que dice /privacidad
 * («hasta 30 mensajes»; revisión adversarial, 2026-11-14). El modelo ve los últimos 10 turnos: no se pierde nada.
 */
export const MAX_TURNOS = 15;
/** Lo que el modelo ve de la conversación: los últimos 10 turnos. */
const MENSAJES_PARA_EL_MODELO = 20;
const MAX_VISTOS = 60;
const CACHE_MS = 60_000;
export const NOMBRE_RESPONDER = "responder_tienda";
/** La respuesta (o un error claro) antes de esto: el navegador espera. Cada paso es una vuelta completa al modelo. */
export const PLAZO_TOTAL_MS = 28_000;
const PASOS = 5;
/** Lo que puede gastar UN turno, en tokens, para apartarlo del presupuesto antes de llamar a la IA (dos pasadas: la de corrección). */
const TOKENS_RESERVA: Uso = { entrada: 60_000, cacheLectura: 0, cacheEscritura: 0, salida: 8_000 };

export type MotivoTienda = "pase" | "tope_sesion" | "tope_red" | "tope_dia" | "presupuesto" | "apagado" | "fallo";

export interface ErrorTienda {
  ok: false;
  motivo: MotivoTienda;
}

export interface SalidaTienda {
  status: number;
  cuerpo: RespuestaTienda | ErrorTienda;
  /** Segundos para `Retry-After` (topes). */
  reintentarEn?: number;
}

export interface EntradaTienda {
  peticion: PeticionTienda;
  /** La red del visitante ya ofuscada (HMAC con la llave del Worker): ni la IP ni la red en claro llegan aquí. */
  red: string;
  /** La /48 de su IPv6, también ofuscada (null con IPv4). */
  red48?: string | null;
}

export interface GlobalTiendaApi {
  reservarTurnoTienda(p: ReservaTienda): Promise<ResultadoReservaTienda>;
  cerrarTurnoTienda(id: number, gastos: GastoTienda[]): Promise<void>;
  guardarSalud?(clave: string, json: string): Promise<void>;
}

export interface DepsTienda {
  sql: Sql;
  /** El reloj del negocio (topes, horario, mes). */
  ahora(): number;
  config(): Promise<Config>;
  odoo: Pick<OdooApi, "herramientaTienda">;
  herramientas(): Promise<DefHerramienta[]>;
  modelo: FabricaDeModelos;
  proveedoresDisponibles(): ProveedorIa[];
  global: GlobalTiendaApi;
  fijarAlarma(ts: number | null): Promise<void>;
  /** Borra TODO lo de la sesión (en producción, `ctx.storage.deleteAll()`); sin esto, se vacían las tablas. */
  borrarTodo?(): Promise<void>;
  /** Los hosts del propio sitio: sus direcciones absolutas se vuelven relativas en las tarjetas. */
  hostsDelSitio: string[];
  /** Para volver absolutas las direcciones relativas que necesita el registro del turno (no salen al navegador). */
  sitio?: string;
  /** Para las pruebas: un plazo más corto y el reloj de los plazos (por defecto, el de verdad). */
  plazoMs?: number;
  reloj?: () => number;
  log?(nivel: "info" | "warn" | "error", mensaje: string): void;
}

interface FilaMensaje {
  id: number;
  rol: "cliente" | "brian";
  origen: "visitante" | "sistema";
  texto: string;
}

interface Oferta {
  producto_id: number;
  cantidad: number;
  nombre: string;
}

/** Lo que el modelo puede mandar en `responder_tienda` (se valida todo: nada se usa a ciegas). */
interface RespuestaDelModelo {
  texto: string;
  productos: unknown[];
  ofrecer_carrito: unknown;
  proponer_carrito: unknown;
  sugerencias: { texto: string; opciones: unknown[] } | null;
  pedir_ubicacion: boolean;
  whatsapp: boolean;
  calificar: boolean;
  chips: unknown[];
  pose: Pose | null;
}

const esObjeto = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);

// ── La herramienta con la que el modelo contesta ─────────────────────────────

const REF_PRODUCTO = { description: "producto_id (número) o, si no hay id, el código del producto, tal como lo devolvió la herramienta.", anyOf: [{ type: "integer" }, { type: "string" }] };

export const ESQUEMA_RESPONDER = {
  type: "object",
  properties: {
    texto: { type: "string", description: "Lo que le dices al cliente: de 1 a 3 líneas, sin enlaces ni listas de precios." },
    productos: { type: "array", items: REF_PRODUCTO, description: "Los productos que la página muestra en tarjetas (de los que devolvieron las herramientas en este mensaje), hasta 6." },
    ofrecer_carrito: { type: "object", properties: { producto: REF_PRODUCTO, cantidad: { type: "integer" } }, description: "El producto que le PREGUNTAS si quiere poner en el carrito." },
    proponer_carrito: { type: "object", properties: { producto: REF_PRODUCTO, cantidad: { type: "integer" } }, description: "Solo si el cliente pidió o confirmó en este mensaje poner ese producto en el carrito." },
    sugerencias: { type: "object", properties: { texto: { type: "string" }, opciones: { type: "array", items: { type: "string" } } }, description: "Una pregunta corta con 2 o 3 opciones." },
    pedir_ubicacion: { type: "boolean", description: "true si necesitas saber a dónde se lleva para calcular el envío." },
    whatsapp: { type: "boolean", description: "true si conviene que lo atienda una persona por WhatsApp." },
    calificar: { type: "boolean", description: "true si el cliente se despide o agradece al final." },
    chips: { type: "array", items: { type: "string" }, description: "Hasta 4 respuestas rápidas cortas." },
    pose: { type: "string", enum: [...POSES], description: "Opcional: la pose del robot que mejor acompaña la respuesta." },
  },
  required: ["texto"],
} as const;

function leerRespuestaDelModelo(v: unknown): RespuestaDelModelo | null {
  let o: unknown = v;
  if (typeof v === "string") {
    try {
      o = JSON.parse(v);
    } catch {
      return null;
    }
  }
  if (!esObjeto(o)) return null;
  const sug = esObjeto(o.sugerencias) && typeof o.sugerencias.texto === "string" ? { texto: o.sugerencias.texto, opciones: Array.isArray(o.sugerencias.opciones) ? o.sugerencias.opciones : [] } : null;
  return {
    texto: typeof o.texto === "string" ? o.texto : "",
    productos: Array.isArray(o.productos) ? o.productos.slice(0, 20) : [],
    ofrecer_carrito: o.ofrecer_carrito,
    proponer_carrito: o.proponer_carrito,
    sugerencias: sug,
    pedir_ubicacion: o.pedir_ubicacion === true,
    whatsapp: o.whatsapp === true,
    calificar: o.calificar === true,
    chips: Array.isArray(o.chips) ? o.chips.slice(0, 10) : [],
    pose: typeof o.pose === "string" && (POSES as readonly string[]).includes(o.pose) ? (o.pose as Pose) : null,
  };
}

// ── Una vuelta al modelo ─────────────────────────────────────────────────────

interface EntradaModelo {
  modelo: LanguageModel;
  sel: SeleccionDeModelo;
  sistemaEstable: string;
  sistemaDinamico: string;
  mensajes: ModelMessage[];
  herramientas: ToolSet;
  abortSignal: AbortSignal;
  /** Cada paso que termina, con su uso: se anota en ese momento (aunque después la vuelta se corte o falle). */
  alPaso(uso: Uso): void;
}

interface SalidaModelo {
  texto: string;
  respuesta: RespuestaDelModelo | null;
  uso: Uso;
  consultas: ConsultaDelTurno[];
  herramientasUsadas: string[];
}

async function correrModelo(e: EntradaModelo): Promise<SalidaModelo> {
  const r = await generateText({
    model: e.modelo,
    // Igual que el motor de Juan (motor/modelo.ts): con Claude, el prompt estable se cachea; Meta y OpenAI cachean solos por prefijo.
    system:
      e.sel.proveedor === "anthropic"
        ? [
            { role: "system", content: e.sistemaEstable, providerOptions: { anthropic: { cacheControl: { type: "ephemeral" as const } } } },
            { role: "system", content: e.sistemaDinamico },
          ]
        : `${e.sistemaEstable}\n\n${e.sistemaDinamico}`,
    messages: e.mensajes,
    tools: e.herramientas,
    stopWhen: [stepCountIs(PASOS), hasToolCall(NOMBRE_RESPONDER)],
    maxOutputTokens: topeDeSalida(e.sel.proveedor, e.sel.nivel),
    maxRetries: 0,
    abortSignal: e.abortSignal,
    onStepEnd: (paso) => e.alPaso(usoDelSdk(paso.usage)),
  });
  const llamadas = r.steps.flatMap((s) => s.toolCalls);
  const final = [...llamadas].reverse().find((c) => c.toolName === NOMBRE_RESPONDER);
  return {
    texto: r.text.trim(),
    respuesta: final ? leerRespuestaDelModelo(final.input) : null,
    uso: usoDelSdk(r.totalUsage),
    consultas: r.steps.flatMap((s) => s.toolResults.filter((t) => t.toolName !== NOMBRE_RESPONDER).map((t) => ({ herramienta: t.toolName, resultado: t.output }))),
    herramientasUsadas: llamadas.map((c) => c.toolName).filter((n) => n !== NOMBRE_RESPONDER),
  };
}

class PlazoVencido extends Error {}

/** El renglón con que se anota lo que costó un turno que se cortó o falló sin que se pudiera medir (estimado: lo apartado). */
export { MODELO_DE_LO_CORTADO };

/**
 * Lo que cuesta UN turno de la tienda, PASO POR PASO (revisión adversarial, 2026-11-14, B1): cada vuelta al modelo que termina se
 * anota aunque el turno después se corte por el plazo o falle (el proveedor ya la cobró). Si una vuelta se cortó o falló con la
 * petición ya enviada, lo que costó no se sabe: el turno anota al menos lo que se había apartado, como estimado. Todo va a la tabla
 * de la tienda (nunca a la de Juan) cuando el turno se cierra; lo que llegue después ya no cuenta (lo cubre lo estimado).
 */
export class CuentaDelTurno {
  private readonly usos = new Map<string, { sel: SeleccionDeModelo; uso: Uso }>();
  private cerrada = false;
  /** La última vuelta que se cortó o falló con la petición enviada (lo que costó no se sabe). */
  sinMedir: SeleccionDeModelo | null = null;

  constructor(
    readonly mes: string,
    readonly reservaUsd: number,
    private readonly precios: TablaDePrecios,
  ) {}

  anotar(sel: SeleccionDeModelo, uso: Uso): void {
    if (this.cerrada) return;
    const clave = `${sel.proveedor}|${sel.modelo}`;
    this.usos.set(clave, { sel, uso: sumarUso(this.usos.get(clave)?.uso ?? USO_VACIO, uso) });
  }

  /** Cierra la cuenta: un renglón por modelo y, si algo quedó sin medir, lo apartado que falte, como estimado. */
  gastos(): GastoTienda[] {
    this.cerrada = true;
    const filas: GastoTienda[] = [...this.usos.values()].map(({ sel, uso }) => {
      const c = costoDe(sel.modelo, uso, this.precios);
      return { mes: this.mes, proveedor: sel.proveedor, modelo: sel.modelo, uso, usd: c.usd, estimado: c.estimado };
    });
    const medido = filas.reduce((n, f) => n + f.usd, 0);
    if (this.sinMedir && medido < this.reservaUsd) {
      filas.push({ mes: this.mes, proveedor: this.sinMedir.proveedor, modelo: MODELO_DE_LO_CORTADO, uso: USO_VACIO, usd: this.reservaUsd - medido, estimado: true });
    }
    return filas;
  }
}

/** ¿El proveedor rechazó la petición sin procesarla (un 4xx, o sin clave)? Entonces no cobró: no hace falta estimar nada. */
function rechazadaSinCobro(err: unknown): boolean {
  if (LoadAPIKeyError.isInstance(err)) return true;
  return APICallError.isInstance(err) && typeof err.statusCode === "number" && err.statusCode >= 400 && err.statusCode < 500;
}

/**
 * Lo que escribió el visitante, para el modelo: la neutralización de Juan (etiquetas, marcas de confianza, tarjetas y cédulas) y,
 * además, sin corchetes: las notas que arma el Worker van entre «[…]» y el visitante no puede imitarlas (revisión, 2026-11-14, I1).
 * Todos los que el modelo puede leer como corchete (los de ancho completo «［］», «【】»…: la clase de dcasa/sensibles.ts) se cambian.
 */
export function sinCorchetes(texto: string): string {
  return texto.replace(CORCHETES, "⟦").replace(CORCHETES_QUE_CIERRAN, "⟧");
}

export function delVisitanteParaElModelo(texto: string): string {
  return sinCorchetes(textoParaElModelo(texto));
}

/** Lo que se guarda de lo que dijo el visitante (o una nota del Worker), con su origen explícito: nunca se adivina por la forma. */
interface Entrada {
  texto: string;
  origen: "visitante" | "sistema";
}
const nota = (texto: string): Entrada => ({ texto, origen: "sistema" });

// ── Textos fijos (sin IA) ────────────────────────────────────────────────────

/** De noche, quien quiera una persona sabe cuándo le contestan (el horario sale de Ajustes de Juan). Sin «a. m..»: una sola vez el punto. */
export function lineaDeNoche(cfg: Config): string {
  return `Como ahora la tienda está cerrada, te responden en cuanto abramos, a partir de las ${sinPuntoFinal(horaLegible(cfg.horario.inicio))}.`;
}

/**
 * ¿Brian anuncia que es de noche? Solo fuera del horario y con `avisar_cerrado` (de fábrica). Apagado (la dueña, 2026-11-15: «que
 * siempre esté activo»), fuera del horario atiende igual que de día: sin la línea de noche y sin la pose dormida.
 */
export function anunciaLaNoche(cfg: Config, ms: number): boolean {
  return cfg.tienda.avisar_cerrado && !dentroDeHorario(cfg.horario, ms);
}

/**
 * Sin `avisar_cerrado`, cuando piden una persona fuera del horario: honesto, pero sin «cerrado» ni «no hay vendedoras». Dentro del
 * horario (o con el aviso de siempre), nada.
 */
export function lineaDelHorarioAmable(cfg: Config, ms: number): string | null {
  if (cfg.tienda.avisar_cerrado) return null;
  const proxima = proximaAtencion(cfg, ms);
  return proxima ? `Las vendedoras atienden ${horarioLegible(cfg)}; te escriben ${sinPuntoFinal(proxima)}.` : null;
}

export const TEXTO_PERSONA = "Claro que sí. Una persona del equipo te atiende por WhatsApp.";
export const TEXTO_SEGURO = "Para no darte un dato equivocado, prefiero que te lo confirme una persona del equipo por WhatsApp.";
export const TEXTO_GRACIAS_POR_CALIFICAR = "Gracias por calificarme, de verdad me ayuda. Que tengas un lindo día.";
export const TEXTO_CARRITO_FALLO = "No pude ponerlo en el carrito ahorita, disculpa. Puedes intentarlo desde su ficha o, si prefieres, te atiende una persona por WhatsApp.";
export const TEXTO_SIN_CONFIRMAR = "Gracias. ¿Te ayudo con algo más?";
export const TEXTO_SI = "Con gusto, te lo pongo en el carrito.";
export const TEXTO_NO = "Perfecto, sin problema. ¿Te muestro algo más?";
export const TEXTO_OCUPADO = "Hay mucha gente escribiendo en este momento. Inténtalo otra vez en un momentito, o escríbenos por WhatsApp.";
export const OPCIONES_DESPUES_DEL_CARRITO = ["¿Cuánto cuesta el envío?", "Seguir viendo"];
export const CHIPS_DE_OFERTA = ["Sí, ponlo en el carrito", "No, gracias"];

export function textoListo(nombre: string, cantidad: number): string {
  return `Listo, te puse ${cantidad > 1 ? `${cantidad} × ` : ""}${nombre} en el carrito. ¡Gracias!`;
}

const QUE_ESTUVO_MAL: Record<TipoProblema, string> = {
  precio_inventado: "una cifra de dinero que no salió de una herramienta",
  cifra_inventada: "una cifra (plazo, porcentaje o cuotas) que no salió de una herramienta",
  existencias: "un número de existencias",
  promesa: "una promesa de entrega, flete, financiamiento, apartado o descuento",
  fuga: "información interna",
  secreto: "un dato que el cliente dio en confianza",
  manda_a_leer: "mandar al cliente a leer políticas o términos",
  se_hace_pasar_por_persona: "decir que eres una persona o que no eres un bot (eres Andrés, el asistente virtual de D'CASA)",
  palabra_prohibida: "una palabra que la marca no usa",
  niega_producto: "decir que no manejamos algo que sí se trabaja aunque no esté en la tienda en línea (di que sí y ofrece WhatsApp)",
};

function notaDeCorreccion(graves: readonly TipoProblema[]): string {
  const que = [...new Set(graves)].map((t) => QUE_ESTUVO_MAL[t]).join("; ");
  return (
    `Tu respuesta anterior NO se mostró porque tenía ${que}. Vuelve a contestar con responder_tienda sin eso: precios solo copiados de ` +
    "buscar_productos o ver_producto (con «+ ITBMS»), nunca cuántas unidades hay, ninguna cifra que no te dio una herramienta, y lo de " +
    "entregas, apartados, financiamiento y descuentos solo como lo dice buscar_conocimiento (o por WhatsApp). De 1 a 3 líneas, en tuteo."
  );
}

// ── El motor ─────────────────────────────────────────────────────────────────

export class MotorTienda {
  private cola: Promise<unknown> = Promise.resolve();
  private enEspera = 0;
  private readonly cacheDeHerramientas = new Map<string, { valor: unknown; vence: number }>();
  private readonly cache: CacheDeHerramientas = {
    obtener: (clave) => {
      const e = this.cacheDeHerramientas.get(clave);
      if (!e) return undefined;
      if (e.vence <= this.deps.ahora()) {
        this.cacheDeHerramientas.delete(clave);
        return undefined;
      }
      return e.valor;
    },
    guardar: (clave, valor) => {
      if (this.cacheDeHerramientas.size >= 50) this.cacheDeHerramientas.delete(this.cacheDeHerramientas.keys().next().value as string);
      this.cacheDeHerramientas.set(clave, { valor, vence: this.deps.ahora() + CACHE_MS });
    },
  };

  constructor(private readonly deps: DepsTienda) {
    this.crearEsquema();
  }

  private crearEsquema(): void {
    const { sql } = this.deps;
    sql.correr("CREATE TABLE IF NOT EXISTS mensajes (id INTEGER PRIMARY KEY AUTOINCREMENT, rol TEXT NOT NULL, origen TEXT NOT NULL, texto TEXT NOT NULL, ts INTEGER NOT NULL)");
    sql.correr("CREATE TABLE IF NOT EXISTS vistos (clave TEXT PRIMARY KEY, json TEXT NOT NULL, ts INTEGER NOT NULL)");
    sql.correr("CREATE TABLE IF NOT EXISTS kv (clave TEXT PRIMARY KEY, valor TEXT NOT NULL)");
    sql.correr("CREATE TABLE IF NOT EXISTS envios (id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER NOT NULL)");
  }

  private log(nivel: "info" | "warn" | "error", mensaje: string): void {
    if (this.deps.log) this.deps.log(nivel, mensaje);
    else console[nivel === "info" ? "log" : nivel](`[juan] tienda: ${mensaje}`);
  }

  // ── kv ──
  private leer(clave: string): string | null {
    return this.deps.sql.uno<{ valor: string }>("SELECT valor FROM kv WHERE clave = ?", clave)?.valor ?? null;
  }
  private poner(clave: string, valor: string | number | boolean | null): void {
    if (valor === null) this.deps.sql.correr("DELETE FROM kv WHERE clave = ?", clave);
    else this.deps.sql.correr("INSERT INTO kv (clave, valor) VALUES (?, ?) ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor", clave, String(valor));
  }
  private leerJson<T>(clave: string): T | null {
    const v = this.leer(clave);
    if (!v) return null;
    try {
      return JSON.parse(v) as T;
    } catch {
      return null;
    }
  }

  /**
   * Un mensaje a la vez por sesión (el objeto puede recibir otro mientras espera a la IA): se atienden en orden. Si ya hay dos
   * esperando, el tercero recibe el tope de la sesión: la página no manda mensajes encimados.
   */
  atender(e: EntradaTienda): Promise<SalidaTienda> {
    if (this.enEspera >= 2) return Promise.resolve({ status: 429, cuerpo: { ok: false, motivo: "tope_sesion" }, reintentarEn: 10 });
    this.enEspera++;
    const turno = this.cola.then(
      () => this.atenderUno(e),
      () => this.atenderUno(e),
    );
    this.cola = turno.catch(() => undefined).finally(() => {
      this.enEspera--;
    });
    return turno;
  }

  /** La alarma de Cloudflare: pasadas 2 horas sin actividad, se borra todo; si hubo actividad, se vuelve a programar. */
  async alarma(): Promise<void> {
    const ultimo = Number(this.leer("ultimo") ?? 0);
    const ahora = this.deps.ahora();
    if (!ultimo || ahora - ultimo >= VIDA_DEL_CONTEXTO_MS - 1000) await this.olvidar();
    else await this.deps.fijarAlarma(ultimo + VIDA_DEL_CONTEXTO_MS);
  }

  /** Borra todo lo de esta sesión (contexto, productos vistos, contadores). */
  async olvidar(): Promise<void> {
    if (this.deps.borrarTodo) await this.deps.borrarTodo();
    else for (const t of ["mensajes", "vistos", "kv", "envios"]) this.deps.sql.correr(`DELETE FROM ${t}`);
    this.crearEsquema();
    this.cacheDeHerramientas.clear();
    await this.deps.fijarAlarma(null).catch(() => undefined);
  }

  /** Para las pruebas y el diagnóstico: cuántas filas hay de cada cosa (nunca textos). */
  resumen(): { mensajes: number; vistos: number; envios: number } {
    const n = (t: string) => this.deps.sql.uno<{ n: number }>(`SELECT COUNT(*) AS n FROM ${t}`)?.n ?? 0;
    return { mensajes: n("mensajes"), vistos: n("vistos"), envios: n("envios") };
  }

  private async atenderUno(e: EntradaTienda): Promise<SalidaTienda> {
    const t0 = (this.deps.reloj ?? Date.now)();
    const diag: Record<string, unknown> = {};
    const terminar = (s: SalidaTienda) => {
      const cuerpo = s.cuerpo;
      diag.resultado = cuerpo.ok ? "ok" : cuerpo.motivo;
      if (cuerpo.ok) diag.bloques = cuerpo.bloques.map((b) => b.tipo);
      diag.ms = (this.deps.reloj ?? Date.now)() - t0;
      this.log(cuerpo.ok ? "info" : "warn", JSON.stringify(diag));
      return s;
    };
    const ahora = this.deps.ahora();
    const ultimo = Number(this.leer("ultimo") ?? 0);
    if (ultimo && ahora - ultimo >= VIDA_DEL_CONTEXTO_MS) await this.olvidar();

    const cfg = await this.deps.config();
    const t = cfg.tienda;
    if (!t.activo) return terminar({ status: 503, cuerpo: { ok: false, motivo: "apagado" } });

    const p = e.peticion;
    const accion = p.accion;
    const esConfirmacion = accion?.tipo === "confirmar_carrito";

    // ── Tope por sesión (este objeto atiende de a uno: contar y anotar no se pisan) ──
    if (!esConfirmacion) {
      this.deps.sql.correr("DELETE FROM envios WHERE ts <= ?", ahora - 3600_000);
      const filas = this.deps.sql.todos<{ ts: number }>("SELECT ts FROM envios ORDER BY ts");
      if (filas.length >= t.tope_sesion_hora) {
        const espera = Math.max(1, Math.ceil((filas[0].ts + 3600_000 - ahora) / 1000));
        return terminar({ status: 429, cuerpo: { ok: false, motivo: "tope_sesion" }, reintentarEn: espera });
      }
    }

    // ── Qué se va a hacer (y si llama a la IA) ──
    const plan = this.planear(p);
    diag.plan = plan.tipo;
    const usaIa = plan.tipo === "modelo" || plan.tipo === "agregado";
    const mes = mesDelNegocio(cfg.horario.zona, ahora);
    const dia = diaDelNegocio(cfg.horario.zona, ahora);
    const reservar = (reservaUsd: number) =>
      this.deps.global.reservarTurnoTienda({
        red: e.red,
        red48: e.red48 ?? null,
        dia,
        mes,
        porRed: t.tope_red_hora,
        porDia: t.tope_dia,
        porRedDia: t.tope_red_dia,
        porRed48: t.tope_red48_hora,
        porRed48Dia: t.tope_red48_dia,
        enVueloMax: t.tope_en_vuelo,
        enVueloRed: t.tope_en_vuelo_red,
        proveedor: planDeIntentos(cfg, "inteligente", this.deps.proveedoresDisponibles())[0]?.proveedor ?? cfg.proveedor_ia,
        presupuestoUsd: t.presupuesto_mes_usd,
        reservaUsd,
      });
    let reserva: ResultadoReservaTienda;
    let reservaUsd = usaIa ? this.reservaDelTurno(cfg) : 0;
    try {
      reserva = await reservar(reservaUsd);
      // Lo que Odoo ya puso en el carrito se confirma igual con el presupuesto agotado o con mucha gente: texto fijo, sin la IA.
      if (!reserva.ok && (reserva.motivo === "presupuesto" || reserva.motivo === "ocupado") && plan.tipo === "agregado") {
        reservaUsd = 0;
        reserva = await reservar(0);
        plan.sinIa = true;
      }
    } catch (err) {
      // Sin el contador no se puede saber si cabe en el presupuesto: se falla cerrado.
      this.log("error", `no se pudo apartar el turno: ${limpiarError(err)}`);
      return terminar({ status: 502, cuerpo: { ok: false, motivo: "fallo" } });
    }
    if (!reserva.ok && reserva.motivo === "ocupado") {
      // Demasiados turnos con IA a la vez entre todos: una respuesta amable (no es un tope del visitante; no se guarda ni se cuenta).
      const noche = anunciaLaNoche(cfg, ahora);
      return terminar({
        status: 200,
        cuerpo: { ok: true, pose: noche ? "durmiendo" : "burbuja_chat", bloques: [{ tipo: "texto", texto: TEXTO_OCUPADO }, { tipo: "whatsapp", texto: TEXTO_DEL_BOTON_DE_WHATSAPP, mensaje: mensajeDeWhatsapp(p.carrito, []) }], chips: [] },
      });
    }
    if (!reserva.ok) {
      const espera = reserva.motivo === "tope_red" ? 900 : reserva.motivo === "tope_dia" ? 3600 : undefined;
      return terminar({ status: 429, cuerpo: { ok: false, motivo: reserva.motivo as Exclude<typeof reserva.motivo, "ocupado"> }, ...(espera ? { reintentarEn: espera } : {}) });
    }
    if (!esConfirmacion) this.deps.sql.correr("INSERT INTO envios (ts) VALUES (?)", ahora);

    const cuenta = new CuentaDelTurno(mes, reservaUsd, cfg.precios_ia);
    try {
      const salida = await this.ejecutar(cfg, p, plan, cuenta, diag);
      if (salida.cuerpo.ok) {
        this.poner("ultimo", ahora);
        this.recortar();
        await this.deps.fijarAlarma(ahora + VIDA_DEL_CONTEXTO_MS).catch((err) => this.log("warn", `no se pudo programar la limpieza: ${limpiarError(err)}`));
      }
      return terminar(salida);
    } catch (err) {
      this.log("error", `el turno falló: ${limpiarError(err)}`);
      return terminar({ status: 502, cuerpo: { ok: false, motivo: "fallo" } });
    } finally {
      // Si cerrar falla (el Global no responde, un despliegue), se reintenta una vez; si tampoco, lo apartado vence a los 3 minutos
      // y pasa a gasto estimado (global.ts → `liquidarVencidas`): lo cobrado no se suelta como si no hubiera costado nada.
      const gastos = cuenta.gastos();
      const cerrar = () => this.deps.global.cerrarTurnoTienda(reserva.id, gastos);
      await cerrar()
        .catch(async () => {
          await new Promise((r) => setTimeout(r, 250));
          await cerrar();
        })
        .catch((err) => this.log("warn", `no se pudo cerrar el turno (lo apartado pasará a gasto estimado): ${limpiarError(err)}`));
    }
  }

  /** Lo que puede costar un turno con IA, con el precio del modelo más caro del plan: se aparta antes y se suelta al terminar. */
  private reservaDelTurno(cfg: Config): number {
    const plan = planDeIntentos(cfg, "inteligente", this.deps.proveedoresDisponibles());
    const maximo = Math.max(0, ...plan.map((s) => costoDe(s.modelo, TOKENS_RESERVA, cfg.precios_ia).usd));
    return Math.min(1, Math.max(0.01, maximo * 2));
  }

  // ── Qué toca hacer ──

  private planear(p: PeticionTienda): Plan {
    const accion = p.accion;
    if (accion?.tipo === "calificar") return { tipo: "calificar", estrellas: accion.estrellas };
    if (accion?.tipo === "confirmar_carrito") {
      const pendiente = this.leerJson<Oferta>("pendiente");
      const coincide = !!pendiente && pendiente.producto_id === accion.producto_id && pendiente.cantidad === accion.cantidad;
      if (!coincide) return { tipo: "sin_confirmar" };
      return accion.resultado === "ok" ? { tipo: "agregado", oferta: pendiente } : { tipo: "carrito_fallo", oferta: pendiente };
    }
    const texto = accion?.tipo === "chip" ? accion.valor : p.texto;
    if (texto && pideUnaPersona(texto)) return { tipo: "persona" };
    const oferta = this.leerJson<Oferta>("oferta");
    if (oferta && texto && !p.ubicacion) {
      // El «sí» se resuelve sin la IA solo si el producto sigue entre lo visto y se puede agregar; si no, contesta el modelo.
      const visto = this.vistos().find((v) => v.producto_id === oferta.producto_id && v.agregable);
      if (esUnSi(texto) && visto) return { tipo: "si", oferta: { ...oferta, nombre: visto.nombre } };
      if (esUnNo(texto)) return { tipo: "no" };
    }
    return { tipo: "modelo" };
  }

  private async ejecutar(cfg: Config, p: PeticionTienda, plan: Plan, cuenta: CuentaDelTurno, diag: Record<string, unknown>): Promise<SalidaTienda> {
    const ahora = this.deps.ahora();
    const noche = anunciaLaNoche(cfg, ahora);
    const textoDelVisitante = p.accion?.tipo === "chip" ? p.accion.valor : p.texto;
    const vistos = this.vistos();
    const whatsapp = (): Bloque => ({ tipo: "whatsapp", texto: TEXTO_DEL_BOTON_DE_WHATSAPP, mensaje: mensajeDeWhatsapp(p.carrito, vistos.slice(-2)) });
    const fijo = (bloques: Bloque[], chips: string[] = [], entrada?: Entrada, pose?: Pose): SalidaTienda => {
      const respuesta: RespuestaTienda = {
        ok: true,
        pose: pose ?? elegirPose({ bloques, herramientas: [], noche, delModelo: null, textoDelVisitante, productos: [], agradecimiento: /gracias|thank/i.test(textoDelVisitante) }),
        bloques,
        chips,
      };
      this.guardarTurno(entrada ?? this.entradaParaElHistorial(p), bloques);
      return { status: 200, cuerpo: respuesta };
    };

    switch (plan.tipo) {
      case "calificar": {
        // Las estrellas las guarda el navegador en Odoo (con su sesión): aquí solo se agradece, una vez por sesión.
        this.poner("calificado", 1);
        return fijo([{ tipo: "texto", texto: TEXTO_GRACIAS_POR_CALIFICAR }], [], nota("[El cliente calificó la atención]"), "cinco_estrellas");
      }
      case "persona": {
        const amable = lineaDelHorarioAmable(cfg, ahora);
        const texto = noche ? `${TEXTO_PERSONA} ${lineaDeNoche(cfg)}` : amable ? `${TEXTO_PERSONA} ${amable}` : TEXTO_PERSONA;
        return fijo([{ tipo: "texto", texto }, whatsapp()]);
      }
      case "si": {
        // «¿Te lo pongo en el carrito?» → «sí»: sin la IA (`planear` ya comprobó que el producto sigue visto y es agregable).
        this.poner("oferta", null);
        this.poner("pendiente", JSON.stringify(plan.oferta));
        return fijo([
          { tipo: "texto", texto: TEXTO_SI },
          { tipo: "proponer_carrito", producto_id: plan.oferta.producto_id, cantidad: plan.oferta.cantidad, nombre: plan.oferta.nombre },
        ]);
      }
      case "no": {
        this.poner("oferta", null);
        return fijo([{ tipo: "texto", texto: TEXTO_NO }]);
      }
      case "sin_confirmar":
        // La página avisó de un carrito que Brian no propuso (o ya confirmado): no se afirma nada.
        return fijo([{ tipo: "texto", texto: TEXTO_SIN_CONFIRMAR }], [], nota("[La página avisó de un cambio en el carrito]"));
      case "carrito_fallo": {
        // Odoo dijo que NO: Brian nunca dice «listo». El texto es fijo y ofrece la ficha o WhatsApp.
        this.poner("pendiente", null);
        const visto = vistos.find((v) => v.producto_id === plan.oferta.producto_id);
        const bloques: Bloque[] = [{ tipo: "texto", texto: TEXTO_CARRITO_FALLO }];
        if (visto?.url) bloques.push({ tipo: "productos", productos: [{ ...tarjetaDe(visto), agregable: false }] });
        bloques.push(whatsapp());
        return fijo(bloques, [], nota(`[No se pudo poner en el carrito: ${plan.oferta.nombre}]`));
      }
      case "agregado": {
        this.poner("pendiente", null);
        const listo = textoListo(plan.oferta.nombre, plan.oferta.cantidad);
        return this.turnoConModelo(cfg, p, cuenta, diag, {
          antes: listo,
          sinIa: plan.sinIa,
          entrada: nota(`[Se puso en el carrito: ${plan.oferta.cantidad} × ${plan.oferta.nombre}]`),
          nota: `El sistema ya puso en el carrito ${plan.oferta.cantidad} × «${plan.oferta.nombre}» (Odoo lo confirmó) y ya se lo dijo al cliente con «${listo}». No lo repitas ni vuelvas a dar las gracias. Ofrécele el siguiente paso en una o dos líneas: si buscar_productos devuelve algo que combine con eso, sugiérelo con cortesía; si no, calcular el envío o seguir viendo.`,
          sinFallar: true,
        });
      }
      case "modelo":
        return this.turnoConModelo(cfg, p, cuenta, diag, {});
    }
  }

  // ── El turno con la IA ──

  private async turnoConModelo(
    cfg: Config,
    p: PeticionTienda,
    cuenta: CuentaDelTurno,
    diag: Record<string, unknown>,
    op: { antes?: string; nota?: string; entrada?: Entrada; sinFallar?: boolean; sinIa?: boolean },
  ): Promise<SalidaTienda> {
    const reloj = this.deps.reloj ?? Date.now;
    const inicio = reloj();
    const plazo = this.deps.plazoMs ?? PLAZO_TOTAL_MS;
    const queda = () => inicio + plazo - reloj();
    const ahora = this.deps.ahora();
    const noche = anunciaLaNoche(cfg, ahora);
    const textoDelVisitante = p.accion?.tipo === "chip" ? p.accion.valor : p.texto;
    const vistosAntes = this.vistos();
    const whatsapp = (): Bloque => ({ tipo: "whatsapp", texto: TEXTO_DEL_BOTON_DE_WHATSAPP, mensaje: mensajeDeWhatsapp(p.carrito, vistosAntes.slice(-2)) });
    this.poner("oferta", null);

    /** Cuando la IA no puede: el carrito ya confirmado no se pierde; lo demás es un fallo que la página traduce con WhatsApp. */
    const sinIa = (motivo: string): SalidaTienda => {
      diag.sin_ia = motivo;
      if (!op.sinFallar) return { status: 502, cuerpo: { ok: false, motivo: "fallo" } };
      const bloques: Bloque[] = [{ tipo: "texto", texto: op.antes ?? TEXTO_SIN_CONFIRMAR }, { tipo: "sugerencias", texto: "¿Seguimos?", opciones: OPCIONES_DESPUES_DEL_CARRITO }];
      this.guardarTurno(op.entrada ?? this.entradaParaElHistorial(p), bloques);
      return { status: 200, cuerpo: { ok: true, pose: "bolsita", bloques, chips: [] } };
    };

    if (op.sinIa) return sinIa("presupuesto");
    const defs = (await this.deps.herramientas().catch(() => [] as DefHerramienta[])).filter((d) => HERRAMIENTAS_DE_LA_TIENDA.has(d.nombre));
    // Sin las herramientas de Odoo el modelo contestaría de memoria (sin catálogo ni precios): no se contesta (como Juan).
    if (defs.length === 0) return sinIa("sin_herramientas");
    const nivel = elegirNivel({
      textoDelCliente: textoDelVisitante,
      llamadasRecientes: Number(this.leer("llamadas_t1") ?? 0) + Number(this.leer("llamadas_t2") ?? 0),
      busquedaFloja: this.leer("busqueda_floja") === "1",
    });
    const plan = planDeIntentos(cfg, nivel, this.deps.proveedoresDisponibles());
    if (plan.length === 0) return sinIa("sin_clave");

    const registro = new RegistroDelTurno();
    const odoo = this.deps.odoo;
    // Solo la lista blanca llega a Odoo, sin `conversacion_id`, con los textos tapados y sin coordenadas (el modelo no las pone).
    const odooDeLaTienda = {
      herramienta: async (nombre: string, argumentos: Record<string, unknown>): Promise<ResultadoHerramienta> => {
        if (!HERRAMIENTAS_DE_LA_TIENDA.has(nombre)) return { ok: false, error: "herramienta no permitida", transitorio: false, rechazo: "Esa herramienta no está disponible en el chat de la página." };
        if (!odoo.herramientaTienda) return { ok: false, error: "sin herramientas de la tienda", transitorio: true };
        return odoo.herramientaTienda(nombre, argumentosLimpios(nombre, argumentos));
      },
    };
    const herramientas: ToolSet = construirHerramientas({
      odoo: odooDeLaTienda as unknown as OdooApi,
      defs,
      conversacionId: () => null,
      registro,
      sitio: this.deps.sitio,
      fotoPrevia: () => undefined,
      cache: this.cache,
      identidad: "tienda",
      sinArchivos: true,
    });
    herramientas[NOMBRE_RESPONDER] = tool({
      description: "Tu respuesta al cliente (llámala una vez, al final). La página arma las tarjetas con los productos que elijas.",
      inputSchema: jsonSchema(ESQUEMA_RESPONDER as never),
      execute: async () => "ok",
    });

    // ── La ubicación: el Worker consulta el envío con ella; el modelo solo ve el resultado, sin coordenadas ──
    let envioPorUbicacion: unknown = null;
    const consultasPrevias: ConsultaDelTurno[] = [];
    if (p.ubicacion && odoo.herramientaTienda) {
      const r = await odoo.herramientaTienda("cotizar_envio", { lat: p.ubicacion.lat, lon: p.ubicacion.lon }).catch(() => null);
      if (r?.ok) {
        const sinRespaldo = tomarRespaldoDeEnvio(sinCoordenadas(r.resultado), registro);
        envioPorUbicacion = procesarResultado(sinRespaldo, registro, this.deps.sitio);
        consultasPrevias.push({ herramienta: "cotizar_envio", resultado: { ok: true, resultado: envioPorUbicacion } });
      } else {
        envioPorUbicacion = { ok: false, error: r?.rechazo ?? "No pude consultar el envío con la ubicación ahora." };
      }
      diag.ubicacion = true;
    }

    const sistemaEstable = promptTienda(cfg);
    const dinamico = (extra = "") =>
      contextoTienda(cfg, { ahora, pagina: p.pagina, carrito: p.carrito, envioPorUbicacion, nota: op.nota }) + extra;
    const actual = textoDelVisitante
      ? delVisitanteParaElModelo(textoDelVisitante)
      : p.ubicacion
        ? "(El cliente tocó «Usar mi ubicación».)"
        : "(El cliente sigue en la página.)";
    const mensajes: ModelMessage[] = [...this.historialParaElModelo(), { role: "user", content: actual }];
    /**
     * Una vuelta con un plazo; los fallos se anotan para /salud (sin claves). Cada paso que termina se anota en la cuenta del turno en
     * ese momento; si la vuelta se corta o falla con la petición ya enviada, la cuenta lo sabe y anota al menos lo apartado.
     */
    const vuelta = async (sel: SeleccionDeModelo, ms: number, o: { extra?: string; previos?: ModelMessage[]; soloResponder?: boolean } = {}): Promise<SalidaModelo | null> => {
      if (ms <= 500) return null;
      const control = new AbortController();
      let temporizador: ReturnType<typeof setTimeout> | undefined;
      const vencido = new Promise<never>((_, rechazar) => {
        temporizador = setTimeout(() => {
          control.abort();
          rechazar(new PlazoVencido("plazo vencido"));
        }, ms);
      });
      const llamada = correrModelo({
        modelo: this.deps.modelo(sel),
        sel,
        sistemaEstable,
        sistemaDinamico: dinamico(o.extra),
        mensajes: [...mensajes, ...(o.previos ?? [])],
        herramientas: o.soloResponder ? { [NOMBRE_RESPONDER]: herramientas[NOMBRE_RESPONDER] } : herramientas,
        abortSignal: control.signal,
        alPaso: (uso) => cuenta.anotar(sel, uso),
      });
      llamada.catch(() => {});
      try {
        return await Promise.race([llamada, vencido]);
      } catch (err) {
        if (!rechazadaSinCobro(err)) cuenta.sinMedir = sel;
        const motivo = err instanceof PlazoVencido ? "tardó demasiado" : limpiarError(err);
        this.log("warn", `la IA ${sel.proveedor}/${sel.modelo} falló: ${motivo}`);
        await this.deps.global.guardarSalud?.("ia_fallo", JSON.stringify({ proveedor: sel.proveedor, modelo: sel.modelo, motivo: `(tienda) ${motivo}`, ts: ahora })).catch(() => {});
        return null;
      } finally {
        clearTimeout(temporizador);
      }
    };

    // ── 1) Contestar: el plan (principal y respaldo con clave), dentro del plazo ──
    let salida: SalidaModelo | null = null;
    let usado: SeleccionDeModelo | null = null;
    for (let i = 0; i < plan.length && !salida; i++) {
      const ultimo = i === plan.length - 1;
      const ms = ultimo ? queda() : Math.max(queda() * 0.6, Math.min(queda(), 8000));
      const s = await vuelta(plan[i], ms);
      if (s) [salida, usado] = [s, plan[i]];
    }
    if (!salida || !usado) return sinIa("ia");
    diag.modelo = usado.modelo;
    let consultas = [...consultasPrevias, ...salida.consultas];
    let herramientasUsadas = [...salida.herramientasUsadas];

    // Gastó sus pasos consultando y no contestó: que conteste con lo que ya consultó, solo con responder_tienda.
    if (!salida.respuesta && !salida.texto) {
      const consultado = consultasComoTexto(salida.consultas).trim();
      const s2 = await vuelta(usado, queda(), {
        extra: "\n<aviso>Ya consultaste lo que necesitabas. Contesta AHORA con responder_tienda, sin llamar otras herramientas.</aviso>",
        previos: consultado ? [{ role: "user", content: consultado }] : [],
        soloResponder: true,
      });
      if (s2 && (s2.respuesta || s2.texto)) salida = { ...s2, consultas: salida.consultas, herramientasUsadas: salida.herramientasUsadas };
    }

    // ── 2) La guardia de Juan en el texto principal (una corrección si cambia el sentido; si no, se quita la oración) ──
    const historicas = new Set<number>();
    // Las cifras que ya dijo Brian (los precios de sus tarjetas, por ejemplo); los ids de producto no cuentan como cifras.
    for (const f of this.mensajesGuardados()) if (f.rol === "brian") for (const n of cifrasDeTexto(f.texto.replace(/\(id [^)]*\)/g, ""))) historicas.add(n);
    const nombres = [...new Set([...HERRAMIENTAS_DEL_CONTRATO, ...NOMBRES_DE_HERRAMIENTAS_LOCALES, ...HERRAMIENTAS_DE_LA_TIENDA, ...defs.map((d) => d.nombre), NOMBRE_RESPONDER, "etiquetar_conversacion", "guardar_correo", "no_quiere_novedades"])];
    const fugas = promptTiendaParaFugas(cfg);
    const contexto = (): ContextoRevision => ({
      preciosProducto: registro.preciosProducto,
      cifrasConocidas: new Set<number>([...historicas, ...registro.cifras]),
      numerosEnTexto: registro.numerosEnTexto,
      palabrasProhibidas: cfg.palabras_prohibidas,
      nombresHerramientas: nombres,
      textoDelPrompt: fugas,
      envio: registro.envio,
      haySinPublicar: registro.haySinPublicar,
    });

    let respuesta = salida.respuesta ?? leerRespuestaDelModelo({ texto: salida.texto });
    let revision = revisarTexto(respuesta?.texto ?? "", contexto(), !!op.antes);
    if (revision.graves.length > 0 && !revision.fuga && queda() > 3000) {
      // La ronda de herramientas de la primera pasada no se repite: lo consultado viaja como datos.
      const consultado = consultasComoTexto(salida.consultas).trim();
      const s3 = await vuelta(usado, queda(), {
        extra: `\n<correccion>${notaDeCorreccion(revision.graves)}</correccion>`,
        previos: consultado ? [{ role: "user", content: consultado }] : [],
      });
      if (s3 && (s3.respuesta || s3.texto)) {
        const r3 = s3.respuesta ?? leerRespuestaDelModelo({ texto: s3.texto });
        const rev3 = revisarTexto(r3?.texto ?? "", contexto(), !!op.antes);
        diag.correccion = rev3.graves;
        if (!rev3.fuga && (rev3.graves.length === 0 || rev3.limpio)) {
          respuesta = r3;
          revision = rev3;
          consultas = [...consultas, ...s3.consultas];
          herramientasUsadas = [...herramientasUsadas, ...s3.herramientasUsadas];
        }
      }
    }
    diag.herramientas = herramientasUsadas;
    diag.revision = revision.graves;

    // ── 3) Los productos de ESTE turno (solo de las herramientas) y lo que ya se había visto en la sesión ──
    const hosts = this.deps.hostsDelSitio;
    const delTurno = new Map<string, ProductoVisto>();
    for (const c of consultas) {
      if (c.herramienta !== "buscar_productos" && c.herramienta !== "ver_producto") continue;
      const r = esObjeto(c.resultado) ? c.resultado.resultado : undefined;
      for (const prod of productosDelResultado(c.herramienta, r, hosts)) delTurno.set(claveDeProducto(prod), prod);
    }
    const sesion = new Map<string, ProductoVisto>([...vistosAntes.map((v) => [claveDeProducto(v), v] as const), ...delTurno]);
    this.guardarVistos([...delTurno.values()]);
    this.poner("llamadas_t2", this.leer("llamadas_t1") ?? "0");
    this.poner("llamadas_t1", herramientasUsadas.length);
    this.poner("busqueda_floja", registro.busquedasFlojas > 0 ? 1 : 0);

    // ── 4) Los bloques ──
    const bloques: Bloque[] = [];
    let chips: string[] = [];
    if (revision.fuga) {
      // El modelo dejó ver algo interno: nada de lo que escribió sale. Respuesta segura con WhatsApp.
      bloques.push({ tipo: "texto", texto: noche ? `${TEXTO_SEGURO} ${lineaDeNoche(cfg)}` : TEXTO_SEGURO }, whatsapp());
      return this.salidaDelModelo(bloques, [], op, p, noche, respuesta, herramientasUsadas, []);
    }
    if (op.antes) bloques.push({ tipo: "texto", texto: op.antes });
    const principal = revision.limpio;
    const seguro = !principal && !op.antes;
    if (principal) for (const b of partirEnBurbujas(principal, { maxBurbujas: 3, objetivo: 300 })) bloques.push({ tipo: "texto", texto: b });

    // Tarjetas: las que eligió el modelo, solo de este turno (si contestó sin la herramienta, hasta 4 de lo encontrado).
    const elegidas: ProductoVisto[] = [];
    const refs = respuesta?.productos.length ? respuesta.productos : salida.respuesta ? [] : [...delTurno.values()].slice(0, 4).map((v) => v.producto_id ?? v.codigo);
    for (const ref of refs) {
      const prod = buscarProducto(ref, delTurno.values());
      if (prod && !elegidas.includes(prod) && elegidas.length < MAX_TARJETAS) elegidas.push(prod);
    }
    if (elegidas.length) bloques.push({ tipo: "productos", productos: elegidas.map(tarjetaDe) });

    if (!seguro && respuesta) {
      // El carrito: proponer solo con permiso del visitante; si no, se le pregunta (y se recuerda la oferta).
      const prop = productoDelCarrito(respuesta.proponer_carrito, sesion.values());
      const ofr = productoDelCarrito(respuesta.ofrecer_carrito, sesion.values());
      if (prop && pideOConfirmaCarrito(textoDelVisitante)) {
        bloques.push({ tipo: "proponer_carrito", producto_id: prop.producto_id, cantidad: prop.cantidad, nombre: prop.nombre });
        this.poner("pendiente", JSON.stringify(prop));
      } else if (prop ?? ofr) {
        const oferta = (prop ?? ofr)!;
        this.poner("oferta", JSON.stringify(oferta));
        chips = [...CHIPS_DE_OFERTA];
        if (prop && !/carrito/i.test(principal)) bloques.push({ tipo: "texto", texto: `¿Te pongo ${oferta.nombre} en el carrito?` });
      }
      if (respuesta.sugerencias) {
        const t = revisarTexto(respuesta.sugerencias.texto, contexto(), false);
        const opciones = respuesta.sugerencias.opciones.map(opcionCorta).filter((o) => o && textoLimpio(o, contexto())).slice(0, MAX_OPCIONES);
        if (t.limpio && !t.fuga && t.graves.length === 0 && opciones.length) bloques.push({ tipo: "sugerencias", texto: t.limpio, opciones });
      }
      if (respuesta.pedir_ubicacion) bloques.push({ tipo: "ubicacion", texto: TEXTO_DE_UBICACION });
      if (!chips.length) chips = respuesta.chips.map(opcionCorta).filter((c) => c && textoLimpio(c, contexto())).slice(0, MAX_CHIPS);
    }

    // El envío: la frase de cotizar_envio tal cual (si pasa la guardia), con su lugar.
    const envio = ultimoEnvio(consultas);
    if (envio) {
      const t = revisarTexto(envio.frase, contexto(), false);
      if (!t.fuga && t.graves.length === 0 && t.limpio) bloques.push({ tipo: "envio", texto: t.limpio, lugar: envio.lugar });
    }

    const pideWhatsapp = seguro || !!respuesta?.whatsapp || registro.haySinPublicar;
    if (seguro) bloques.unshift({ tipo: "texto", texto: TEXTO_SEGURO });
    if (pideWhatsapp) {
      // De noche, quien va a WhatsApp sabe que le contestan al abrir (aunque el modelo no lo haya dicho).
      const dijoNoche = bloques.some((b) => b.tipo === "texto" && /\babr(?:ir|amos|an|imos|e)\b/i.test(b.texto));
      if (noche && !dijoNoche) bloques.push({ tipo: "texto", texto: lineaDeNoche(cfg) });
      bloques.push(whatsapp());
    }
    if (respuesta?.calificar && !seguro && this.leer("calificado") !== "1" && this.leer("calificar_ofrecido") !== "1") {
      bloques.push({ tipo: "calificar" });
      this.poner("calificar_ofrecido", 1);
    }
    return this.salidaDelModelo(bloques, chips, op, p, noche, respuesta, herramientasUsadas, elegidas);
  }

  private salidaDelModelo(
    bloques: Bloque[],
    chips: string[],
    op: { entrada?: Entrada },
    p: PeticionTienda,
    noche: boolean,
    respuesta: RespuestaDelModelo | null,
    herramientas: string[],
    productos: ProductoVisto[],
  ): SalidaTienda {
    const textoDelVisitante = p.accion?.tipo === "chip" ? p.accion.valor : p.texto;
    const pose = elegirPose({ bloques, herramientas, noche, delModelo: respuesta?.pose ?? null, textoDelVisitante, productos });
    this.guardarTurno(op.entrada ?? this.entradaParaElHistorial(p), bloques);
    return { status: 200, cuerpo: { ok: true, pose, bloques, chips } };
  }

  // ── El contexto guardado (como mucho 30 turnos, sin la ubicación) ──

  /**
   * Lo que se guarda de lo que dijo el visitante: su texto con tarjetas y cédulas tapadas, con origen «visitante» aunque empiece con
   * «[» (I1 de la revisión: nunca se adivina por la forma). Sin texto, una nota del Worker. Nunca coordenadas.
   */
  private entradaParaElHistorial(p: PeticionTienda): Entrada {
    if (p.accion?.tipo === "chip") return { texto: enmascararSensibles(p.accion.valor), origen: "visitante" };
    if (p.texto) return { texto: enmascararSensibles(p.texto), origen: "visitante" };
    if (p.ubicacion) return nota("[El cliente compartió su ubicación para calcular el envío]");
    return nota("[El cliente sigue en la página]");
  }

  private guardarTurno(entrada: Entrada, bloques: readonly Bloque[]): void {
    const ahora = this.deps.ahora();
    this.deps.sql.correr("INSERT INTO mensajes (rol, origen, texto, ts) VALUES ('cliente', ?, ?, ?)", entrada.origen, entrada.texto.slice(0, 600), ahora);
    this.deps.sql.correr("INSERT INTO mensajes (rol, origen, texto, ts) VALUES ('brian', 'sistema', ?, ?)", resumenDeLaRespuesta(bloques).slice(0, 2500), ahora);
  }

  private recortar(): void {
    this.deps.sql.correr(`DELETE FROM mensajes WHERE id NOT IN (SELECT id FROM mensajes ORDER BY id DESC LIMIT ${MAX_TURNOS * 2})`);
    this.deps.sql.correr(`DELETE FROM vistos WHERE clave NOT IN (SELECT clave FROM vistos ORDER BY ts DESC LIMIT ${MAX_VISTOS})`);
  }

  private mensajesGuardados(): FilaMensaje[] {
    return this.deps.sql.todos<FilaMensaje>(`SELECT id, rol, origen, texto FROM mensajes ORDER BY id DESC LIMIT ${MENSAJES_PARA_EL_MODELO}`).reverse();
  }

  /** Lo que ve el modelo: lo del visitante como DATO (sin etiquetas que imiten las nuestras), lo de Brian tal cual. Empieza con el cliente. */
  private historialParaElModelo(): ModelMessage[] {
    const salida: ModelMessage[] = this.mensajesGuardados().map((f) =>
      f.rol === "brian" ? { role: "assistant" as const, content: f.texto } : { role: "user" as const, content: f.origen === "sistema" ? f.texto : delVisitanteParaElModelo(f.texto) },
    );
    while (salida.length && salida[0].role !== "user") salida.shift();
    return salida;
  }

  private vistos(): ProductoVisto[] {
    return this.deps.sql
      .todos<{ json: string }>("SELECT json FROM vistos ORDER BY ts")
      .map((f) => {
        try {
          return JSON.parse(f.json) as ProductoVisto;
        } catch {
          return null;
        }
      })
      .filter((v): v is ProductoVisto => !!v);
  }

  private guardarVistos(lista: readonly ProductoVisto[]): void {
    const ahora = this.deps.ahora();
    lista.forEach((v, i) =>
      this.deps.sql.correr("INSERT INTO vistos (clave, json, ts) VALUES (?, ?, ?) ON CONFLICT(clave) DO UPDATE SET json = excluded.json, ts = excluded.ts", claveDeProducto(v), JSON.stringify(v), ahora + i),
    );
  }
}

type Plan =
  | { tipo: "modelo" }
  | { tipo: "persona" }
  | { tipo: "calificar"; estrellas: number }
  | { tipo: "si"; oferta: Oferta }
  | { tipo: "no" }
  | { tipo: "sin_confirmar" }
  | { tipo: "agregado"; oferta: Oferta; sinIa?: boolean }
  | { tipo: "carrito_fallo"; oferta: Oferta };

// ── Ayudas ───────────────────────────────────────────────────────────────────

/** Los argumentos que el modelo pone en una herramienta: textos tapados y recortados; sin coordenadas en `cotizar_envio`. */
export function argumentosLimpios(nombre: string, argumentos: Record<string, unknown>): Record<string, unknown> {
  const salida: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(argumentos)) {
    if (nombre === "cotizar_envio" && /^(lat|lon|lng|latitud|longitud|coordenadas)$/i.test(k)) continue;
    salida[k] = typeof v === "string" ? enmascararSensibles(v).slice(0, 300) : v;
  }
  return salida;
}

/** Quita cualquier coordenada que Odoo devolviera (no tiene por qué, pero no se guarda ni se le muestra al modelo). */
export function sinCoordenadas(v: unknown): unknown {
  if (Array.isArray(v)) return v.map(sinCoordenadas);
  if (!esObjeto(v)) return v;
  const salida: Record<string, unknown> = {};
  for (const [k, x] of Object.entries(v)) if (!/^(lat|lon|lng|latitud|longitud|coordenadas)$/i.test(k)) salida[k] = sinCoordenadas(x);
  return salida;
}

/** El producto y la cantidad de una propuesta del modelo, solo si es de lo visto, agregable y con una cantidad válida (1 a 20). */
function productoDelCarrito(v: unknown, vistos: Iterable<ProductoVisto>): Oferta | null {
  if (!esObjeto(v)) return null;
  const prod = buscarProducto(v.producto ?? v.producto_id ?? v.codigo, vistos);
  if (!prod || !prod.agregable || prod.producto_id === null) return null;
  const cantidad = v.cantidad === undefined ? 1 : v.cantidad;
  if (typeof cantidad !== "number" || !Number.isInteger(cantidad) || cantidad < 1 || cantidad > 20) return null;
  return { producto_id: prod.producto_id, cantidad, nombre: prod.nombre };
}

/** La última cotización de envío del turno con precio (la frase y el lugar), si hay. */
function ultimoEnvio(consultas: readonly ConsultaDelTurno[]): { frase: string; lugar: string } | null {
  for (let i = consultas.length - 1; i >= 0; i--) {
    const c = consultas[i];
    if (c.herramienta !== "cotizar_envio" || !esObjeto(c.resultado)) continue;
    const r = c.resultado.resultado;
    if (!esObjeto(r) || r.estado !== "precio" || typeof r.frase_para_el_cliente !== "string") continue;
    const lugar = esObjeto(r.lugar) && typeof r.lugar.nombre === "string" ? r.lugar.nombre.trim().slice(0, 80) : "";
    return { frase: r.frase_para_el_cliente, lugar };
  }
  return null;
}

interface Revision {
  limpio: string;
  graves: TipoProblema[];
  fuga: boolean;
}

/**
 * La guardia de Juan (dcasa/salvaguardas.ts) en un texto de la tienda, más lo propio de la web: la presentación que ya hizo la página
 * se quita, y ninguna oración puede decir que algo ya está en el carrito salvo el turno en que Odoo lo confirmó.
 */
function revisarTexto(crudo: string, ctx: ContextoRevision, carritoConfirmado: boolean): Revision {
  const sinSaludo = sinPresentacion(crudo);
  if (!sinSaludo) return { limpio: "", graves: [], fuga: false };
  const a = analizar(sinSaludo, ctx);
  if (a.graves.some((g) => g.tipo === "fuga")) return { limpio: "", graves: ["fuga"], fuga: true };
  const graves = [...new Set(a.graves.map((g) => g.tipo))];
  let limpio = graves.length ? quitarGraves(a.limpio, ctx) : a.limpio;
  if (!carritoConfirmado) limpio = oraciones(limpio).filter((o) => !afirmaCarrito(o)).join(" ").trim();
  // Que quede algo con sentido (al menos tres palabras): «Claro.» solo no ayuda a nadie.
  if ((limpio.match(/\p{L}{2,}/gu) ?? []).length < 3 && graves.length) limpio = "";
  return { limpio, graves, fuga: false };
}

function textoLimpio(t: string, ctx: ContextoRevision): boolean {
  const a = analizar(t, ctx);
  return a.graves.length === 0 && !afirmaCarrito(t);
}

/** Lo que Brian dijo, para el contexto del siguiente turno: los textos y un resumen de las tarjetas (datos de las herramientas). */
function resumenDeLaRespuesta(bloques: readonly Bloque[]): string {
  const partes: string[] = [];
  for (const b of bloques) {
    if (b.tipo === "texto") partes.push(b.texto);
    else if (b.tipo === "productos") partes.push(`[Tarjetas que mostré: ${b.productos.map((p) => `«${p.nombre}» (id ${p.producto_id ?? "—"}) a ${p.precio_texto || "precio en la ficha"}, ${p.disponibilidad ?? "sin etiqueta"}${p.agregable ? "" : ", se elige en su ficha"}`).join("; ")}]`);
    else if (b.tipo === "proponer_carrito") partes.push(`[Propuse poner en el carrito: ${b.cantidad} × «${b.nombre}»]`);
    else if (b.tipo === "sugerencias") partes.push(`${b.texto} (${b.opciones.join(" / ")})`);
    else if (b.tipo === "envio") partes.push(`[Envío a ${b.lugar || "un lugar"}: ${b.texto}]`);
    else if (b.tipo === "ubicacion") partes.push(`[Pedí a dónde se lleva]`);
    else if (b.tipo === "whatsapp") partes.push("[Ofrecí WhatsApp]");
    else if (b.tipo === "calificar") partes.push("[Ofrecí calificar la atención]");
  }
  return partes.join("\n");
}
