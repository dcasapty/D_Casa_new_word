// La decisión de cada vigilancia, sin entrada/salida.
//
// El Durable Object vigila a su contenedor cada 30 s (y el cron de plataforma cada
// minuto lo respalda). Aquí está el JUICIO: dado lo que dijo el contenedor, qué anota
// el diario y qué hay que hacer (nada, pedir que reconecte, o el martillo de
// destruir el contenedor). Aparte y puro para poder probarlo a fondo.

import { LATIDOS_ANTES_DE_REINICIAR, type Veredicto } from "./comun";

export interface Diario {
  arrancadoEn: string;
  latidos: number;
  arranquesContenedor: number;
  ultimoArranque: string | null;
  ultimaMuerteVista: string | null;
  /**
   * Cuándo se vigiló por última vez. Es la señal que faltó el 16-sep-2026: el canal
   * llevaba horas mudo y el panel lo mostraba como si nada.
   */
  ultimoLatidoEn: number | null;
  /** Vigilancias seguidas con el contenedor prendido pero WhatsApp caído. */
  desconectadoSeguidos: number;
  /** La última vez que se vio el socket de WhatsApp realmente abierto (ISO). */
  ultimaConexionVista: string | null;
  /**
   * Desde cuándo NO hay una conexión sana (ms desde epoch), o null si la hay. Es lo que
   * lee `/api/estado` («desconectado desde hace N min») y lo que dispara el aviso.
   */
  sinConexionDesde: number | null;
  /** Cuántas veces hubo que destruir el contenedor para recuperarlo. */
  reiniciosForzados: number;
  /** Lo último que impidió vigilar, si algo lo impidió. */
  ultimoFalloDelLatido: string | null;
  /** Por qué murió el contenedor la última vez, según el propio runtime. */
  ultimaSalida: string | null;
  /** Aviso por Telegram: hay uno enviado y todavía no se avisó la recuperación. */
  avisoActivo: boolean;
  ultimoAvisoEn: number | null;
  /** Última copia diaria de la sesión (ms desde epoch) y su resultado. */
  ultimaCopiaEn: number | null;
  ultimaCopiaR2: string | null;
  ultimoFalloDeCopia: string | null;
}

export function diarioNuevo(ahora = new Date()): Diario {
  return {
    arrancadoEn: ahora.toISOString(),
    latidos: 0,
    arranquesContenedor: 0,
    ultimoArranque: null,
    ultimaMuerteVista: null,
    ultimoLatidoEn: null,
    desconectadoSeguidos: 0,
    ultimaConexionVista: null,
    sinConexionDesde: null,
    reiniciosForzados: 0,
    ultimoFalloDelLatido: null,
    ultimaSalida: null,
    avisoActivo: false,
    ultimoAvisoEn: null,
    ultimaCopiaEn: null,
    ultimaCopiaR2: null,
    ultimoFalloDeCopia: null,
  };
}

/**
 * Un diario escrito por una versión anterior no trae los campos nuevos. Sin estos
 * respaldos, el primer `+= 1` daría NaN y ese NaN viajaría al estado.
 */
export function normalizarDiario(guardado: Partial<Diario> | undefined | null, ahora = new Date()): Diario {
  const base = diarioNuevo(ahora);
  if (!guardado) return base;
  return { ...base, ...guardado };
}

export type Accion = "nada" | "pedir_reconexion" | "reiniciar";

/**
 * Aplica lo que dijo el contenedor al diario y decide qué hacer.
 *
 *   sano                    → todo al día; nada que hacer.
 *   esperando-a-una-persona → sin vincular o esperando el QR. NO es un fallo y NO se
 *                             reinicia: reiniciar genera un código nuevo y le tumba al
 *                             dueño el que está mirando. Sí cuenta como «sin conexión»
 *                             para el estado y el aviso.
 *   caido                   → prendido pero mudo: primero se le pide que reconecte
 *                             (barato); tras `LATIDOS_ANTES_DE_REINICIAR` seguidas, el
 *                             martillo.
 */
export function aplicarVigilancia(
  diario: Diario,
  veredicto: Veredicto,
  ahora: number,
): { diario: Diario; accion: Accion } {
  const d = { ...diario };

  if (veredicto === "sano") {
    d.desconectadoSeguidos = 0;
    d.sinConexionDesde = null;
    d.ultimaConexionVista = new Date(ahora).toISOString();
    return { diario: d, accion: "nada" };
  }

  if (d.sinConexionDesde === null) d.sinConexionDesde = ahora;

  if (veredicto === "esperando-a-una-persona") {
    d.desconectadoSeguidos = 0;
    return { diario: d, accion: "nada" };
  }

  d.desconectadoSeguidos += 1;
  if (d.desconectadoSeguidos >= LATIDOS_ANTES_DE_REINICIAR) {
    d.reiniciosForzados += 1;
    d.desconectadoSeguidos = 0;
    return { diario: d, accion: "reiniciar" };
  }
  return { diario: d, accion: "pedir_reconexion" };
}

export type EstadoCanal = "apagado" | "iniciando" | "necesita_qr" | "conectado" | "desconectado";

/**
 * El estado que se le muestra al mundo en `/api/estado`:
 *
 *   apagado       PUENTE_ACTIVO no está en «on»: no se enciende el contenedor.
 *   conectado     WhatsApp conectado.
 *   necesita_qr   hay que escanear un código (nunca vinculado, o desvinculado desde el teléfono).
 *   desconectado  estuvo vinculado y ahora no hay conexión (se está reintentando).
 *   iniciando     recién encendido, todavía sin respuesta del contenedor.
 */
export function resumirEstado(i: {
  activo: boolean;
  conexion: string | null | undefined;
  vinculadoAlgunaVez: boolean;
  sinConexionDesde: number | null;
  ahora: number;
}): { estado: EstadoCanal; conectado: boolean; desconectadoMin: number | null } {
  if (!i.activo) return { estado: "apagado", conectado: false, desconectadoMin: null };
  const min = i.sinConexionDesde === null ? null : Math.max(0, Math.floor((i.ahora - i.sinConexionDesde) / 60_000));
  if (i.conexion === "conectada") return { estado: "conectado", conectado: true, desconectadoMin: null };
  if (i.conexion === "esperando-qr" || i.conexion === "desvinculada") {
    return { estado: "necesita_qr", conectado: false, desconectadoMin: min };
  }
  if (i.vinculadoAlgunaVez && min !== null) return { estado: "desconectado", conectado: false, desconectadoMin: min };
  return { estado: "iniciando", conectado: false, desconectadoMin: min };
}
