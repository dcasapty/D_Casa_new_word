// @ts-check
// El contrato con el Worker `juan` (docs/JUAN.md, «Worker juan ↔ puente QR»):
// qué JSON entra por `POST /api/enviar` y qué JSON sale hacia
// `POST /webhooks/whatsapp-qr`. Aquí se valida lo que entra y se construye (y se
// puede validar) lo que sale; las pruebas de contrato viven en test/contrato.test.ts.

import { resolverDestino } from "./numeros.mjs";
import { MAX_BURBUJA, MAX_BURBUJAS, partirPie, prepararBurbujas } from "./particion.mjs";
import { validarMedioSaliente } from "./medios.mjs";
import { validarUrlMedio } from "./urls.mjs";

/** Tipos de mensaje que el puente entrega a Juan. */
export const TIPOS_ENTRANTES = Object.freeze(["texto", "imagen", "audio", "documento", "video"]);

/** Cuántos medios como máximo en una misma petición de envío. */
export const MAX_MEDIOS = 5;

/** Cuántos mensajes en total (texto + medios + restos de pie) por petición. */
export const MAX_MENSAJES_POR_PETICION = 16;

/**
 * @typedef {{ tipo: "imagen" | "documento", url: string, nombre?: string, mime?: string, pie?: string, restoPie: string[] }} MedioPlan
 * @typedef {{ para: import("./numeros.mjs").DestinoOk, burbujas: string[], medios: MedioPlan[], total: number }} EnvioPlan
 */

/**
 * Valida y normaliza el cuerpo de `POST /api/enviar`:
 *   { para, chunks: [texto…], medios?: [{ tipo: "imagen|documento", url, nombre?, mime?, pie? }] }
 *
 * No toca la red: solo la forma de todo, el destino y las URLs (sintaxis y
 * dominios). La descarga y la comprobación del contenido van después.
 *
 * @param {unknown} cuerpo
 * @param {{ hostsPermitidos?: string[], maxBurbuja?: number }} [opciones]
 * @returns {{ ok: true, plan: EnvioPlan } | { ok: false, status: 400 | 422, error: string }}
 */
export function validarEnviar(cuerpo, { hostsPermitidos = [], maxBurbuja = MAX_BURBUJA } = {}) {
  if (!cuerpo || typeof cuerpo !== "object" || Array.isArray(cuerpo)) {
    return { ok: false, status: 400, error: "Se esperaba un objeto { para, chunks, medios? }." };
  }
  const c = /** @type {Record<string, unknown>} */ (cuerpo);

  const destino = resolverDestino(c.para);
  if (!destino.ok) return { ok: false, status: 400, error: `para: ${destino.motivo}.` };

  const chunks = c.chunks === undefined || c.chunks === null ? [] : c.chunks;
  const burbujas = prepararBurbujas(chunks, { max: maxBurbuja, maxBurbujas: MAX_BURBUJAS });
  if (!burbujas.ok) return { ok: false, status: 400, error: `chunks: ${burbujas.motivo}.` };

  const crudos = c.medios === undefined || c.medios === null ? [] : c.medios;
  if (!Array.isArray(crudos)) return { ok: false, status: 400, error: "medios debe ser una lista." };
  if (crudos.length > MAX_MEDIOS) {
    return { ok: false, status: 400, error: `demasiados medios (${crudos.length}); el máximo es ${MAX_MEDIOS}.` };
  }

  /** @type {MedioPlan[]} */
  const medios = [];
  for (const [i, crudo] of crudos.entries()) {
    const v = validarMedioSaliente(crudo);
    if (!v.ok) return { ok: false, status: 400, error: `medios[${i}]: ${v.motivo}.` };
    const u = validarUrlMedio(v.valor.url, { hostsPermitidos });
    if (!u.ok) return { ok: false, status: 422, error: `medios[${i}]: ${u.motivo}.` };
    const { pie, resto } = partirPie(v.valor.pie);
    medios.push({ ...v.valor, url: u.url.toString(), pie, restoPie: resto });
  }

  const total = burbujas.burbujas.length + medios.length + medios.reduce((n, m) => n + m.restoPie.length, 0);
  if (total === 0) return { ok: false, status: 400, error: "No hay nada que enviar: faltan chunks o medios." };
  if (total > MAX_MENSAJES_POR_PETICION) {
    return { ok: false, status: 400, error: `demasiados mensajes (${total}); el máximo es ${MAX_MENSAJES_POR_PETICION} por petición.` };
  }

  return { ok: true, plan: { para: destino, burbujas: burbujas.burbujas, medios, total } };
}

/**
 * Arma el JSON que el puente entrega al Worker `juan`:
 *
 *   { id_mensaje, de, nombre, tipo, texto?, medio?, ts, propio }
 *
 * Campos extra, aditivos (el Worker puede ignorarlos): `jid` (el chat tal como lo
 * ve WhatsApp, útil cuando `de` es un identificador `@lid` sin teléfono) y
 * `medio_omitido` (había un archivo que no se pudo adjuntar, y por qué).
 *
 * @param {{
 *   idMensaje: string, de: string, nombre: string | null, tipo: string,
 *   texto?: string | null,
 *   medio?: { base64: string, mime: string, nombre: string } | null,
 *   medioOmitido?: { motivo: string, mime?: string, bytes?: number } | null,
 *   ts: number, propio: boolean, jid?: string | null,
 * }} p
 */
export function construirWebhook(p) {
  /** @type {Record<string, unknown>} */
  const salida = {
    id_mensaje: p.idMensaje,
    de: p.de,
    nombre: p.nombre ?? null,
    tipo: p.tipo,
  };
  if (p.texto) salida.texto = p.texto;
  if (p.medio) salida.medio = { base64: p.medio.base64, mime: p.medio.mime, nombre: p.medio.nombre };
  if (p.medioOmitido) salida.medio_omitido = p.medioOmitido;
  salida.ts = new Date(p.ts).toISOString();
  salida.propio = p.propio === true;
  if (p.jid) salida.jid = p.jid;
  return salida;
}

/**
 * Comprueba que un JSON de salida cumple el contrato. Devuelve la lista de
 * incumplimientos (vacía si está bien). Se usa en las pruebas y como cinturón en
 * el Worker: lo que no cumple no se entrega a medias, se rechaza con la causa.
 *
 * @param {unknown} obj
 * @returns {string[]}
 */
export function validarWebhook(obj) {
  /** @type {string[]} */
  const errores = [];
  if (!obj || typeof obj !== "object" || Array.isArray(obj)) return ["el cuerpo no es un objeto"];
  const o = /** @type {Record<string, unknown>} */ (obj);
  if (typeof o.id_mensaje !== "string" || !o.id_mensaje) errores.push("id_mensaje debe ser un texto no vacío");
  if (typeof o.de !== "string" || !o.de) errores.push("de debe ser un texto no vacío");
  if (o.nombre !== null && typeof o.nombre !== "string") errores.push("nombre debe ser texto o null");
  if (typeof o.tipo !== "string" || !TIPOS_ENTRANTES.includes(o.tipo)) {
    errores.push(`tipo debe ser uno de ${TIPOS_ENTRANTES.join("|")}`);
  }
  if (o.texto !== undefined && typeof o.texto !== "string") errores.push("texto, si viene, debe ser texto");
  if (typeof o.ts !== "string" || Number.isNaN(Date.parse(o.ts))) errores.push("ts debe ser una fecha ISO 8601");
  if (typeof o.propio !== "boolean") errores.push("propio debe ser verdadero o falso");
  if (o.medio !== undefined) {
    const m = o.medio;
    if (!m || typeof m !== "object") errores.push("medio debe ser un objeto");
    else {
      const mm = /** @type {Record<string, unknown>} */ (m);
      if (typeof mm.base64 !== "string" && typeof mm.url_temporal !== "string") {
        errores.push("medio necesita base64 o url_temporal");
      }
      if (typeof mm.mime !== "string" || !mm.mime) errores.push("medio.mime debe ser un texto no vacío");
      if (typeof mm.nombre !== "string" || !mm.nombre) errores.push("medio.nombre debe ser un texto no vacío");
    }
  }
  if (o.tipo === "texto" && !o.texto && !o.medio) errores.push("un mensaje de texto necesita texto");
  if (o.tipo !== undefined && o.tipo !== "texto" && !o.medio && !o.medio_omitido && !o.texto) {
    errores.push("un mensaje con archivo necesita el medio, el motivo de su omisión o al menos un texto");
  }
  return errores;
}
