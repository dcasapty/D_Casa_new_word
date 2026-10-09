// Qué le falta al puente para poder trabajar. SOLO NOMBRES, nunca valores.
//
// Los secretos NO viajan por GitHub: la dueña los pega directamente en el panel de
// Cloudflare (Workers → este Worker → Settings → Variables and Secrets). Por eso el
// PRIMER despliegue ocurre sin ellos y tiene que salir bien: el puente arranca
// «sin configurar», no enciende el contenedor, no intenta conectar WhatsApp y su
// `/api/estado` dice qué nombres faltan. Los despliegues siguientes nunca borran los
// secretos puestos en el panel.

import { tokenEsApto } from "./comun";

/** Sin estos dos el puente no enciende el contenedor ni guarda la sesión. */
export const SECRETOS_OBLIGATORIOS = ["WA_TOKEN", "WA_SESION_CLAVE"] as const;

/** Sin estos el puente funciona, pero sin avisar a la dueña por Telegram si se cae. */
export const SECRETOS_OPCIONALES = ["TELEGRAM_BOT_TOKEN_JUAN", "ALERTA_TELEGRAM_CHAT"] as const;

export interface Configuracion {
  /** Nombres de los secretos obligatorios que no están (o están vacíos). */
  faltan: string[];
  /** Los que están pero no sirven (demasiado cortos, con caracteres raros). Solo el motivo, nunca el valor. */
  invalidos: { nombre: string; motivo: string }[];
  /** Nombres de los opcionales que no están. */
  opcionalesFaltan: string[];
  /** ¿Se puede encender el contenedor? Solo si no falta ni sobra nada de los obligatorios. */
  listo: boolean;
}

const vacio = (v: unknown) => typeof v !== "string" || v.trim() === "";

export function revisarConfiguracion(env: object): Configuracion {
  const valores = env as Record<string, unknown>;
  const faltan = SECRETOS_OBLIGATORIOS.filter((n) => vacio(valores[n])) as string[];
  const invalidos: { nombre: string; motivo: string }[] = [];

  if (!vacio(valores.WA_TOKEN)) {
    const apto = tokenEsApto(valores.WA_TOKEN as string);
    if (!apto.apto) invalidos.push({ nombre: "WA_TOKEN", motivo: apto.motivo ?? "no es apto" });
  }
  if (!vacio(valores.WA_SESION_CLAVE) && (valores.WA_SESION_CLAVE as string).length < 32) {
    invalidos.push({ nombre: "WA_SESION_CLAVE", motivo: "demasiado corta (mínimo 32 caracteres)" });
  }

  return {
    faltan,
    invalidos,
    opcionalesFaltan: SECRETOS_OPCIONALES.filter((n) => vacio(valores[n])) as string[],
    listo: faltan.length === 0 && invalidos.length === 0,
  };
}

/** El estado de un puente al que le faltan secretos: no conecta, no cae, dice qué falta. */
export function estadoSinConfigurar(cfg: Configuracion, env: { PUENTE_ACTIVO?: string; JUAN?: unknown }) {
  return {
    ok: true,
    estado: "sin_configurar",
    conectado: false,
    activo: env.PUENTE_ACTIVO === "on",
    secretos_faltantes: cfg.faltan,
    secretos_invalidos: cfg.invalidos,
    opcionales_faltantes: cfg.opcionalesFaltan,
    binding_juan: Boolean(env.JUAN),
    mensaje:
      "Faltan secretos en este Worker. Se ponen en el panel de Cloudflare (Workers → este Worker → Settings → Variables and Secrets); " +
      "mientras tanto el puente no enciende el contenedor ni intenta conectar WhatsApp.",
  };
}
