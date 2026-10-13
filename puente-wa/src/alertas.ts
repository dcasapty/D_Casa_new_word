// Aviso a la dueña por Telegram cuando WhatsApp lleva demasiado desconectado.
//
// Solo nombres de secretos: `TELEGRAM_BOT_TOKEN_JUAN` (el bot) y el chat de la dueña
// (`ALERTA_TELEGRAM_CHAT`). El texto NUNCA lleva el QR, tokens ni credenciales: dice qué
// pasa y a quién acudir. Un fallo al avisar no rompe la vigilancia.

import type { Veredicto } from "./comun";
import type { Diario } from "./vigilancia";

export interface ConfigAlerta {
  /** Minutos sin conexión antes del primer aviso. */
  minutos: number;
  /** Cada cuántos minutos se repite el aviso mientras siga caído. */
  reavisoMinutos: number;
}

export const ALERTA_POR_DEFECTO: ConfigAlerta = { minutos: 10, reavisoMinutos: 120 };

export function leerConfigAlerta(env: { ALERTA_MINUTOS?: string; ALERTA_REAVISO_MINUTOS?: string }): ConfigAlerta {
  const n = (v: string | undefined, d: number, min: number, max: number) => {
    const x = Number(v);
    return v !== undefined && v !== "" && Number.isFinite(x) ? Math.min(max, Math.max(min, Math.round(x))) : d;
  };
  return {
    minutos: n(env.ALERTA_MINUTOS, ALERTA_POR_DEFECTO.minutos, 1, 1440),
    reavisoMinutos: n(env.ALERTA_REAVISO_MINUTOS, ALERTA_POR_DEFECTO.reavisoMinutos, 10, 10080),
  };
}

export type Alerta = { tipo: "caida" | "necesita_qr" | "recuperado"; texto: string };

/**
 * ¿Hay que avisar ahora? Función pura: no envía nada ni toca el diario (quien llama
 * aplica `despuesDeAvisar`).
 *
 *  · Nunca avisa si el canal jamás estuvo conectado (instalación nueva, la dueña
 *    todavía no escaneó el QR) ni si el puente está apagado a propósito.
 *  · Avisa una vez cuando se cumplen `minutos` sin conexión, y vuelve a avisar cada
 *    `reavisoMinutos` mientras siga igual.
 *  · Avisa UNA vez la recuperación, solo si antes se había avisado la caída.
 */
export function evaluarAlerta(
  d: Pick<Diario, "sinConexionDesde" | "ultimaConexionVista" | "avisoActivo" | "ultimoAvisoEn">,
  veredicto: Veredicto,
  ahora: number,
  cfg: ConfigAlerta,
): Alerta | null {
  if (veredicto === "sano") {
    if (!d.avisoActivo) return null;
    const antes = d.ultimoAvisoEn ?? ahora;
    const min = Math.max(1, Math.round((ahora - (d.sinConexionDesde ?? antes)) / 60_000));
    return {
      tipo: "recuperado",
      texto: `WhatsApp (el puente de D'CASA) volvió a conectarse. Estuvo sin conexión unos ${min} min. Ya no hay que hacer nada.`,
    };
  }

  if (d.sinConexionDesde === null || !d.ultimaConexionVista) return null;
  const min = Math.floor((ahora - d.sinConexionDesde) / 60_000);
  if (min < cfg.minutos) return null;
  if (d.avisoActivo && d.ultimoAvisoEn !== null && ahora - d.ultimoAvisoEn < cfg.reavisoMinutos * 60_000) return null;

  const sigue = d.avisoActivo ? "Sigue igual. " : "";
  if (veredicto === "esperando-a-una-persona") {
    return {
      tipo: "necesita_qr",
      texto:
        `${sigue}WhatsApp (el puente de D'CASA) quedó desvinculado hace ${min} min: hay que escanear un código QR nuevo ` +
        "desde el teléfono del negocio. Mientras tanto el asistente no contesta por WhatsApp. Pasos en docs/JUAN_PUENTE.md.",
    };
  }
  return {
    tipo: "caida",
    texto:
      `${sigue}WhatsApp (el puente de D'CASA) lleva ${min} min sin conexión y el asistente no está contestando por ahí. ` +
      "El sistema intenta reconectar solo; si no se arregla, revisa docs/JUAN_PUENTE.md («Si WhatsApp lo desconecta»).",
  };
}

/** Lo que cambia en el diario una vez enviado (o intentado) un aviso. */
export function despuesDeAvisar(
  d: Pick<Diario, "avisoActivo" | "ultimoAvisoEn">,
  alerta: Alerta,
  ahora: number,
): Pick<Diario, "avisoActivo" | "ultimoAvisoEn"> {
  if (alerta.tipo === "recuperado") return { avisoActivo: false, ultimoAvisoEn: null };
  return { avisoActivo: true, ultimoAvisoEn: ahora };
}

/**
 * Manda un mensaje por la API de Telegram. Nunca lanza ni registra el token (la URL
 * lo lleva): devuelve `{ ok, motivo }` con algo que SÍ se puede mostrar.
 */
export async function enviarTelegram(
  llamar: typeof fetch,
  token: string,
  chat: string,
  texto: string,
): Promise<{ ok: boolean; motivo?: string }> {
  try {
    const r = await llamar(`https://api.telegram.org/bot${token}/sendMessage`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ chat_id: chat, text: texto, disable_web_page_preview: true }),
    });
    if (r.ok) return { ok: true };
    return { ok: false, motivo: `Telegram contestó ${r.status}` };
  } catch {
    return { ok: false, motivo: "no se pudo llegar a Telegram" };
  }
}
