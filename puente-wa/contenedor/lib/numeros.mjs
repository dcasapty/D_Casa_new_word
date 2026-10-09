// @ts-check
// Números de teléfono y chats de WhatsApp: normalización, destinos permitidos y
// enmascarado para los logs. Todo puro, sin red: se prueba en CI.
//
// Vive en `contenedor/lib` porque lo usan los dos lados (el Worker valida el
// destino antes de despertar al contenedor, y el contenedor lo vuelve a validar).
//
// Convención de Juan (docs/JUAN.md): el celular es la llave y viaja en E.164
// SIN el «+» (p. ej. 50760261919). El `jid` de WhatsApp es `<e164>@s.whatsapp.net`.

/** Código de país de Panamá. */
export const PREFIJO_PANAMA = "507";

/** Un celular panameño tiene 8 dígitos (6xxx-xxxx para móviles). */
const DIGITOS_LOCALES_PANAMA = 8;

/**
 * @typedef {{ ok: true, e164: string, esPanama: boolean }} CelularOk
 * @typedef {{ ok: false, motivo: string }} Rechazo
 */

/**
 * Normaliza un celular a E.164 sin «+».
 *
 * Acepta lo que escribe la gente: «6026-1919», «+507 6026-1919», «(507) 6026 1919»,
 * «00507 60261919», «50760261919». Reglas:
 *   · 8 dígitos  → es un número local de Panamá: se le antepone 507.
 *   · 11 dígitos que empiezan por 507 → ya está completo.
 *   · empieza por 507 con otra longitud → inválido (un número de Panamá no tiene
 *     dígitos de más ni de menos).
 *   · 9 o 10 dígitos → inválido: no es un local de Panamá y tampoco un
 *     internacional creíble; adivinar el país mandaría el mensaje a otra persona.
 *   · 11 a 15 dígitos (E.164 llega a 15) → internacional, se deja tal cual.
 *
 * @param {unknown} entrada
 * @returns {CelularOk | Rechazo}
 */
export function normalizarCelular(entrada) {
  if (typeof entrada === "number" && Number.isSafeInteger(entrada) && entrada > 0) {
    entrada = String(entrada);
  }
  if (typeof entrada !== "string") return { ok: false, motivo: "el número no es texto" };
  const texto = entrada.trim();
  if (!texto) return { ok: false, motivo: "el número está vacío" };
  if (texto.length > 40) return { ok: false, motivo: "el número es demasiado largo" };
  // Solo se toleran los separadores que la gente escribe. Letras u otros símbolos
  // delatan que no es un teléfono (y evita que «hola5551234» pase por número).
  if (!/^\+?[\d\s\-.()]+$/.test(texto)) return { ok: false, motivo: "el número tiene caracteres que no son de un teléfono" };

  let digitos = texto.replace(/\D/g, "");
  // Prefijo de llamada internacional: 00507…
  if (digitos.startsWith("00")) digitos = digitos.slice(2);
  if (!digitos) return { ok: false, motivo: "el número no tiene dígitos" };
  if (digitos.startsWith("0")) return { ok: false, motivo: "el número empieza por 0" };

  if (digitos.length === DIGITOS_LOCALES_PANAMA) {
    return { ok: true, e164: PREFIJO_PANAMA + digitos, esPanama: true };
  }
  if (digitos.startsWith(PREFIJO_PANAMA)) {
    if (digitos.length === PREFIJO_PANAMA.length + DIGITOS_LOCALES_PANAMA) {
      return { ok: true, e164: digitos, esPanama: true };
    }
    return { ok: false, motivo: "un número de Panamá lleva 8 dígitos después del 507" };
  }
  if (digitos.length < DIGITOS_LOCALES_PANAMA) return { ok: false, motivo: "el número es demasiado corto" };
  if (digitos.length === 9 || digitos.length === 10) {
    return { ok: false, motivo: "no se sabe de qué país es (escríbelo con el código de país)" };
  }
  if (digitos.length > 15) return { ok: false, motivo: "el número es demasiado largo (máximo 15 dígitos)" };
  return { ok: true, e164: digitos, esPanama: false };
}

/**
 * ¿Es un móvil de Panamá (6xxx-xxxx)? Solo informativo: no se rechaza nada por esto.
 * @param {unknown} e164
 */
export function esMovilPanama(e164) {
  return /^5076\d{7}$/.test(String(e164));
}

/**
 * `50760261919` → `50760261919@s.whatsapp.net`.
 * @param {string} e164
 */
export function jidDeCelular(e164) {
  return `${e164}@s.whatsapp.net`;
}

/**
 * ¿Este chat es una persona escribiéndole al negocio, uno a uno?
 *
 * Fuera: estados y listas de difusión (`@broadcast`), grupos (`@g.us`), canales
 * (`@newsletter`) y bots de Meta (`@bot`). Es una lista de lo que NO es, a
 * propósito: WhatsApp estrena formatos de chat de persona (`@lid`, `@hosted`…)
 * más seguido que formatos que no lo son, y un formato nuevo de persona no debe
 * perder mensajes. Mandarle texto a `status@broadcast` es PUBLICAR un estado con
 * el número del negocio (incidente del 24-sep-2026 en el CRM de origen).
 *
 * @param {unknown} jid
 */
export function esChatDeUnaPersona(jid) {
  const j = String(jid ?? "");
  return (
    !!j &&
    j.includes("@") &&
    !j.endsWith("@broadcast") &&
    !j.endsWith("@g.us") &&
    !j.endsWith("@newsletter") &&
    !j.endsWith("@bot")
  );
}

/**
 * Sin el sufijo de dispositivo: `507…:12@s.whatsapp.net` → `507…@s.whatsapp.net`.
 * @param {string | null | undefined} jid
 */
export function sinDispositivo(jid) {
  if (!jid) return jid;
  const [usuario, servidor] = String(jid).split("@");
  if (!servidor) return jid;
  return `${usuario.split(":")[0]}@${servidor}`;
}

/**
 * El celular E.164 de un jid de persona, o null si no es un número (un `@lid`
 * es un identificador opaco de WhatsApp, no un teléfono).
 * @param {string | null | undefined} jid
 */
export function celularDeJid(jid) {
  const limpio = sinDispositivo(jid);
  if (!limpio) return null;
  const [usuario, servidor] = limpio.split("@");
  if ((servidor === "s.whatsapp.net" || servidor === "c.us") && /^\d{7,15}$/.test(usuario)) return usuario;
  return null;
}

/**
 * @typedef {{ ok: true, jid: string, e164: string | null, tipo: "pn" | "lid" }} DestinoOk
 */

/**
 * Convierte el `para` de `/api/enviar` en un destino de WhatsApp.
 * Acepta un celular en cualquiera de las formas de `normalizarCelular`, o un jid
 * de persona (`…@s.whatsapp.net`, `…@lid`). Los grupos, estados y canales se
 * rechazan SIEMPRE.
 *
 * @param {unknown} para
 * @returns {DestinoOk | Rechazo}
 */
export function resolverDestino(para) {
  if (typeof para !== "string" || !para.trim()) return { ok: false, motivo: "falta el destino (para)" };
  const texto = para.trim();
  if (texto.includes("@")) {
    if (!esChatDeUnaPersona(texto)) {
      return { ok: false, motivo: "no se le escribe a un grupo, estado o canal: solo a personas" };
    }
    const limpio = /** @type {string} */ (sinDispositivo(texto));
    const [usuario, servidor] = limpio.split("@");
    if (servidor === "s.whatsapp.net" || servidor === "c.us") {
      if (!/^\d{7,15}$/.test(usuario)) return { ok: false, motivo: "el jid no tiene un número válido" };
      return { ok: true, jid: jidDeCelular(usuario), e164: usuario, tipo: "pn" };
    }
    if (servidor === "lid") {
      if (!/^\d{5,30}$/.test(usuario)) return { ok: false, motivo: "el identificador lid no es válido" };
      return { ok: true, jid: `${usuario}@lid`, e164: null, tipo: "lid" };
    }
    return { ok: false, motivo: `tipo de chat no admitido (@${servidor})` };
  }
  const n = normalizarCelular(texto);
  if (!n.ok) return { ok: false, motivo: n.motivo };
  return { ok: true, jid: jidDeCelular(n.e164), e164: n.e164, tipo: "pn" };
}

/**
 * Oculta un teléfono para los logs: deja solo los últimos 4 dígitos.
 * `50760261919@s.whatsapp.net` → `***1919@s.whatsapp.net`. Los logs del puente
 * nunca llevan números completos, textos ni credenciales.
 * @param {unknown} valor
 */
export function enmascarar(valor) {
  return String(valor ?? "").replace(/\d{7,}/g, (m) => `***${m.slice(-4)}`);
}
