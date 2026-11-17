// `POST /tienda/v1/voz` (y `GET`, `OPTIONS`): las notas de voz del chat de la tienda (Andrés). docs/JUAN.md › «Notas de voz».
//
// El navegador manda el audio crudo con el mismo pase y desde los mismos orígenes que `/tienda/v1/mensaje` (tienda/rutas.ts ya
// comprobó CORS y el pase antes de llegar aquí). Este Worker lo pasa a texto con Whisper (motor/voz.ts) y devuelve SOLO el texto.
// Después la página manda ese texto como un mensaje normal por `/tienda/v1/mensaje`: la lógica del chat no se duplica, y el visitante
// ve lo que se entendió antes de la respuesta.
//
//   · El audio no toca el Durable Object de la sesión, ni la conversación, ni R2, ni los registros. Se borra de la memoria al terminar.
//   · La duración es la que de verdad se decodifica (motor/duracion.ts), hasta MAX_SEGUNDOS_TIENDA (unos 30 s: lo que cabe en un
//     mensaje del chat). Más larga, o imposible de medir: se rechaza ANTES de apartar nada. Se aparta y se cobra con esa duración.
//   · Cuenta como un mensaje en los topes de red, /48 y del día, y en los turnos a la vez; tiene además su tope por sesión (el mismo
//     número que los mensajes por hora por sesión, contado aparte en `Global`). El mensaje que la página manda enseguida con el texto
//     NO vuelve a contar: la nota deja un crédito para su red (global.ts). Su costo va en el gasto de la tienda (renglón «notas de
//     voz (Whisper)», proveedor `cloudflare`): suma en su presupuesto, nunca en el de Juan ni en «Por pagar a Meta».
//   · La transcripción y el cierre de la reserva corren dentro de `waitUntil`: si el visitante corta la conexión, igual terminan y
//     sueltan su lugar «en vuelo» (y, por si acaso, la reserva de una nota vence a los 30 s, no a los 3 minutos).
//
// Entrada:  POST /tienda/v1/voz?duracion_ms=<entero>   Authorization: Pase <pase>   Content-Type: audio/webm | audio/ogg | audio/mp4
//           (con `;codecs=…` si se quiere)   Cuerpo: los bytes del audio, hasta MAX_BYTES_VOZ y MAX_SEGUNDOS_TIENDA.
// Salida:   200 {ok: true, texto, recortado}   (texto de hasta MAX_TEXTO letras, lo mismo que acepta `/tienda/v1/mensaje`)
//           {ok: false, motivo}: pase 401 · apagado 503 · no_disponible 503 · tipo 415 · audio 400 · muy_pesada 413 · muy_larga 413
//           · tope_sesion / tope_red / tope_dia / presupuesto / ocupado 429 (con Retry-After salvo presupuesto) · no_se_entendio 422
//           · tardo 504 · fallo 502.
// GET:      {ok: true, disponible, max_segundos, max_bytes, tipos}: si la página muestra el micrófono (sin pase: no dice nada más).

import type { Config } from "../config";
import { diaDelNegocio, mesDelNegocio } from "../config";
import type { Env } from "../env";
import type { GastoTienda, ResultadoReservaVozTienda, ReservaVozTienda } from "../motor/global";
import { MODELO_DE_LA_VOZ, PROVEEDOR_DE_LA_VOZ } from "../motor/global";
import { USO_VACIO } from "../motor/precios";
import { whisperDe } from "../motor/transcribir";
import {
  duracionDeclarada,
  esProblema,
  leerConTope,
  MAX_BYTES_VOZ,
  MAX_SEGUNDOS_TIENDA,
  TOLERANCIA_SEGUNDOS,
  reservaDeLaNota,
  tipoDeAudio,
  TIPOS_DE_AUDIO,
  transcribirNota,
  validarNota,
  type ResultadoNota,
} from "../motor/voz";
import { hmacHex } from "../seguridad";
import { llaveDeRed, llaveDeRed48 } from "./pase";
import { MAX_TEXTO } from "./peticion";

export const RUTA_DE_LA_VOZ = "/tienda/v1/voz";

export type MotivoVoz =
  | "pase"
  | "apagado"
  | "no_disponible"
  | "tipo"
  | "audio"
  | "muy_pesada"
  | "muy_larga"
  | "tope_sesion"
  | "tope_red"
  | "tope_dia"
  | "presupuesto"
  | "ocupado"
  | "no_se_entendio"
  | "tardo"
  | "fallo";

const STATUS: Record<Exclude<ResultadoNota, { ok: true }>["motivo"], number> = { no_disponible: 503, muy_larga: 413, no_se_entendio: 422, tardo: 504, fallo: 502 };

/** Lo que la ruta necesita del Durable Object `Global` (o un doble en las pruebas). */
export interface GlobalVozTiendaApi {
  reservarVozTienda(p: ReservaVozTienda): Promise<ResultadoReservaVozTienda>;
  cerrarTurnoTienda(id: number, gastos: GastoTienda[]): Promise<void>;
}

export interface DepsVozTienda {
  global?: GlobalVozTiendaApi;
  /** Para las pruebas: un plazo corto para Whisper. */
  plazoMs?: number;
  log?(nivel: "info" | "warn" | "error", mensaje: string): void;
}

export interface ContextoVozTienda {
  req: Request;
  env: Env;
  config(): Promise<Config>;
  ahora(): number;
  /** El `sid` del pase ya verificado. */
  sid: string;
  /** Responde con CORS (lo arma tienda/rutas.ts con el origen ya comprobado). */
  responder(cuerpo: unknown, status: number, extra?: Record<string, string>): Response;
  /** `ctx.waitUntil`: lo que sigue aunque el visitante corte la conexión (la transcripción y el cierre de la reserva). */
  esperarDespues?(trabajo: Promise<unknown>): void;
  deps?: DepsVozTienda;
}

/** `GET /tienda/v1/voz`: si la página debe mostrar el micrófono (la tienda encendida y la transcripción también). */
export async function disponibilidadDeLaVoz(env: Env, config: () => Promise<Config>): Promise<Record<string, unknown>> {
  let activo = false;
  try {
    activo = (await config()).tienda.activo;
  } catch {
    activo = false;
  }
  return { ok: true, disponible: activo && !!whisperDe(env), max_segundos: MAX_SEGUNDOS_TIENDA, max_bytes: MAX_BYTES_VOZ, tipos: [...TIPOS_DE_AUDIO] };
}

export async function atenderVozTienda(c: ContextoVozTienda): Promise<Response> {
  const t0 = Date.now();
  const deps = c.deps ?? {};
  const log = (nivel: "info" | "warn" | "error", diag: Record<string, unknown>) => {
    // Solo el resultado, el tamaño (en KB) y los tiempos: nunca el audio, el texto, la IP, la red ni el `sid`.
    const linea = JSON.stringify({ voz: true, ...diag, ms: Date.now() - t0 });
    if (deps.log) deps.log(nivel, linea);
    else console[nivel === "info" ? "log" : nivel](`[juan] tienda: ${linea}`);
  };
  const error = (motivo: MotivoVoz, status: number, extra: Record<string, string> = {}, kb?: number) => {
    log(status >= 500 ? "error" : "warn", { resultado: motivo, ...(kb !== undefined ? { kb } : {}) });
    return c.responder({ ok: false, motivo }, status, extra);
  };

  // Lo barato primero: el tipo y lo que dice el navegador, antes de leer un solo byte.
  const tipo = tipoDeAudio(c.req.headers.get("content-type"));
  if (!tipo) return error("tipo", 415);
  const declarada = duracionDeclarada(new URL(c.req.url).searchParams.get("duracion_ms"));
  if (declarada !== null && declarada > (MAX_SEGUNDOS_TIENDA + TOLERANCIA_SEGUNDOS) * 1000) return error("muy_larga", 413);

  let cfg: Config;
  try {
    cfg = await c.config();
  } catch {
    return error("fallo", 502);
  }
  const t = cfg.tienda;
  if (!t.activo) return error("apagado", 503);
  if (!whisperDe(c.env)) return error("no_disponible", 503);

  const bytes = await leerConTope(c.req, MAX_BYTES_VOZ).catch(() => null);
  if (bytes === null) return error("muy_pesada", 413);
  const kb = Math.ceil(bytes.byteLength / 1024);
  // La duración de verdad (contada paquete por paquete), antes de apartar nada.
  const nota = validarNota(bytes, tipo, declarada, MAX_SEGUNDOS_TIENDA);
  if (esProblema(nota)) {
    bytes.fill(0);
    return error(nota.motivo, nota.status, {}, kb);
  }

  const global: GlobalVozTiendaApi | null = deps.global ?? (c.env.GLOBAL ? (c.env.GLOBAL.get(c.env.GLOBAL.idFromName("juan")) as unknown as GlobalVozTiendaApi) : null);
  if (!global) {
    nota.bytes.fill(0);
    return error("fallo", 503, {}, kb);
  }
  // La red de la conexión y la sesión, ofuscadas como en `/tienda/v1/mensaje` (aquí no llega ni se guarda nada en claro).
  const ofuscar = async (llave: string) => (await hmacHex(c.env.JUAN_WORKER_TOKEN ?? "", llave)).slice(0, 32);
  const ip = c.req.headers.get("cf-connecting-ip");
  const red = await ofuscar(`brian-tienda-red:${llaveDeRed(ip)}`);
  const llave48 = llaveDeRed48(ip);
  const red48 = llave48 ? await ofuscar(`brian-tienda-red48:${llave48}`) : null;
  const sesion = await ofuscar(`brian-tienda-voz-sid:${c.sid}`);
  const ahora = c.ahora();
  const mes = mesDelNegocio(cfg.horario.zona, ahora);
  const dia = diaDelNegocio(cfg.horario.zona, ahora);

  let reserva: ResultadoReservaVozTienda;
  try {
    reserva = await global.reservarVozTienda({
      red,
      red48,
      dia,
      mes,
      sesion,
      porSesion: t.tope_sesion_hora,
      porRed: t.tope_red_hora,
      porDia: t.tope_dia,
      porRedDia: t.tope_red_dia,
      porRed48: t.tope_red48_hora,
      porRed48Dia: t.tope_red48_dia,
      enVueloMax: t.tope_en_vuelo,
      enVueloRed: t.tope_en_vuelo_red,
      proveedor: PROVEEDOR_DE_LA_VOZ,
      presupuestoUsd: t.presupuesto_mes_usd,
      reservaUsd: reservaDeLaNota(nota),
    });
  } catch {
    // Sin el contador no se sabe si cabe en los topes ni en el presupuesto: se falla cerrado.
    nota.bytes.fill(0);
    return error("fallo", 502, {}, kb);
  }
  if (!reserva.ok) {
    nota.bytes.fill(0);
    const m = reserva.motivo;
    const espera = m === "tope_sesion" ? reserva.reintentarEn : m === "tope_red" ? 900 : m === "tope_dia" ? 3600 : m === "ocupado" ? 15 : undefined;
    return error(m, 429, espera ? { "retry-after": String(espera) } : {}, kb);
  }

  const id = reserva.id;
  // La transcripción y el cierre, juntos y dentro de `waitUntil`: si el visitante corta la conexión, Cloudflare no los cancela y el
  // lugar «en vuelo» se suelta igual (con lo que costó anotado).
  const trabajo = (async (): Promise<ResultadoNota> => {
    let r: ResultadoNota | null = null;
    try {
      r = await transcribirNota(c.env, nota, { maxLetras: MAX_TEXTO, plazoMs: deps.plazoMs });
      return r;
    } finally {
      // Suelta lo apartado y anota lo que costó (si no se llamó a Whisper, nada). Si cerrar falla, se reintenta una vez; si
      // tampoco, lo apartado pasa a gasto estimado a los 30 s (global.ts): lo cobrado nunca se suelta como si no hubiera costado.
      const gastos: GastoTienda[] = r && r.usd > 0 ? [{ mes, proveedor: PROVEEDOR_DE_LA_VOZ, modelo: MODELO_DE_LA_VOZ, uso: USO_VACIO, usd: r.usd, estimado: r.estimado }] : [];
      const cerrar = () => global.cerrarTurnoTienda(id, gastos);
      await cerrar()
        .catch(async () => {
          await new Promise((res) => setTimeout(res, 250));
          await cerrar();
        })
        .catch(() => log("warn", { resultado: "sin_cerrar" }));
    }
  })();
  c.esperarDespues?.(trabajo.catch(() => undefined));
  const r = await trabajo;
  if (!r.ok) return error(r.motivo, STATUS[r.motivo], {}, kb);
  log("info", { resultado: "ok", kb, recortado: r.recortado });
  return c.responder({ ok: true, texto: r.texto, recortado: r.recortado }, 200);
}
