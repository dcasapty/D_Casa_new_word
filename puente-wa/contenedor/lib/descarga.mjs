// @ts-check
// Descarga segura de una URL de imagen o documento (protección contra SSRF).
//
// Por qué se descarga aquí y no se le pasa la URL a Baileys
// (`sendMessage(jid, { image: { url } })`): Baileys haría su propia petición,
// siguiendo redirecciones a donde sea, sin mirar a qué dirección resuelve el
// nombre. Con la descarga hecha aquí:
//
//   · solo https y solo dominios válidos (validarUrlMedio);
//   · el nombre se resuelve UNA vez, se comprueba que TODAS sus direcciones sean
//     públicas y la conexión se hace a esa dirección ya comprobada (el `lookup`
//     personalizado) — así no hay ventana para el «DNS rebinding», donde el
//     nombre cambia de dirección entre la comprobación y la conexión;
//   · las redirecciones se siguen a mano, con tope, y cada salto vuelve a pasar
//     por todo lo anterior (un 302 hacia http://169.254.169.254 muere en el acto);
//   · el tamaño se corta mientras se descarga, no al final;
//   · el contenido se contrasta con el tipo declarado (firma de los bytes).

import dns from "node:dns";
import https from "node:https";
import { contenidoCoincide, mimeLimpio } from "./medios.mjs";
import { esIpPublica, validarUrlMedio } from "./urls.mjs";

export const REDIRECCIONES_MAX = 3;
export const TIMEOUT_DESCARGA_MS = 20_000;

/**
 * El `lookup` que usa la conexión: resuelve el nombre, exige que TODAS las
 * direcciones sean públicas y devuelve esas mismas.
 *
 * @param {(host: string, opts: any) => Promise<{ address: string, family: number }[]>} resolver
 * @returns {(host: string, opciones: any, cb: (...args: any[]) => void) => void}
 */
export function crearLookupSeguro(resolver) {
  return (host, opciones, cb) => {
    const callback = typeof opciones === "function" ? opciones : cb;
    const quiereTodas = typeof opciones === "object" && opciones !== null && opciones.all === true;
    resolver(host, { all: true, verbatim: true })
      .then((direcciones) => {
        if (!direcciones.length) throw Object.assign(new Error(`el nombre ${host} no resuelve`), { code: "ENOTFOUND" });
        const mala = direcciones.find((d) => !esIpPublica(d.address));
        if (mala) {
          throw Object.assign(new Error(`el nombre ${host} resuelve a una dirección no pública`), { code: "ENOTPUBLIC" });
        }
        if (quiereTodas) callback(null, direcciones);
        else callback(null, direcciones[0].address, direcciones[0].family);
      })
      .catch((e) => callback(e));
  };
}

/**
 * @typedef {{
 *   request?: (url: URL, opciones: any, cb: (res: any) => void) => any,
 *   resolver?: (host: string, opts: any) => Promise<{ address: string, family: number }[]>,
 * }} Deps
 * @typedef {{ ok: true, bytes: Buffer, mime: string, url: string }
 *   | { ok: false, estado: 422 | 502 | 504, motivo: string }} Resultado
 */

/**
 * Descarga una URL con todas las defensas.
 *
 * @param {string} urlTexto
 * @param {{
 *   tipo: "imagen" | "documento",
 *   mimesPermitidos: readonly string[],
 *   maxBytes: number,
 *   hostsPermitidos?: string[],
 *   mimeDeclarado?: string,
 *   timeoutMs?: number,
 *   deps?: Deps,
 * }} opciones
 * @returns {Promise<Resultado>}
 */
export async function descargarSeguro(urlTexto, opciones) {
  const { tipo, mimesPermitidos, maxBytes, hostsPermitidos = [], mimeDeclarado, timeoutMs = TIMEOUT_DESCARGA_MS } = opciones;
  const request = opciones.deps?.request ?? https.request;
  const resolver = opciones.deps?.resolver ?? ((host, o) => dns.promises.lookup(host, o));
  const lookup = crearLookupSeguro(resolver);
  const limite = Date.now() + timeoutMs;

  let actual = urlTexto;
  for (let salto = 0; salto <= REDIRECCIONES_MAX; salto++) {
    const v = validarUrlMedio(actual, { hostsPermitidos });
    if (!v.ok) return { ok: false, estado: 422, motivo: salto === 0 ? v.motivo : `redirección rechazada: ${v.motivo}` };

    const faltan = limite - Date.now();
    if (faltan <= 0) return { ok: false, estado: 504, motivo: "la descarga tardó demasiado" };

    let respuesta;
    try {
      respuesta = await pedir(request, v.url, lookup, faltan, maxBytes);
    } catch (e) {
      const err = /** @type {any} */ (e);
      if (err?.code === "ENOTPUBLIC") return { ok: false, estado: 422, motivo: "el servidor está en una dirección no pública" };
      if (err?.code === "ETIMEDOUT" || err?.name === "TimeoutError") return { ok: false, estado: 504, motivo: "la descarga tardó demasiado" };
      if (err?.code === "ETOOBIG") return { ok: false, estado: 422, motivo: `el archivo pesa más de ${Math.round(maxBytes / 1048576)} MB` };
      return { ok: false, estado: 502, motivo: `no se pudo descargar (${err?.code ?? err?.message ?? "error de red"})` };
    }

    if (respuesta.estado >= 300 && respuesta.estado < 400 && respuesta.ubicacion) {
      try {
        actual = new URL(respuesta.ubicacion, v.url).toString();
      } catch {
        return { ok: false, estado: 502, motivo: "la redirección no es una URL válida" };
      }
      continue;
    }
    if (respuesta.estado !== 200) {
      return { ok: false, estado: 502, motivo: `el origen contestó ${respuesta.estado}` };
    }

    const delOrigen = mimeLimpio(respuesta.contentType);
    const declarado = mimeDeclarado ? mimeLimpio(mimeDeclarado) : "";
    const sinTipo = delOrigen === "" || delOrigen === "application/octet-stream" || delOrigen === "binary/octet-stream";
    /** @type {string} */
    let efectivo;
    if (mimesPermitidos.includes(delOrigen)) efectivo = delOrigen;
    // Un origen que no dice qué es (octet-stream): manda lo declarado en la petición.
    else if (sinTipo && declarado && mimesPermitidos.includes(declarado)) efectivo = declarado;
    else return { ok: false, estado: 422, motivo: `el tipo ${delOrigen || "(sin tipo)"} no se puede enviar como ${tipo}` };
    if (declarado && declarado !== efectivo) {
      return { ok: false, estado: 422, motivo: "el tipo del archivo no coincide con el declarado" };
    }
    if (!respuesta.bytes.length) return { ok: false, estado: 422, motivo: "el archivo está vacío" };
    if (!contenidoCoincide(efectivo, respuesta.bytes)) {
      return { ok: false, estado: 422, motivo: "el contenido del archivo no corresponde a su tipo" };
    }
    return { ok: true, bytes: respuesta.bytes, mime: efectivo, url: v.url.toString() };
  }
  return { ok: false, estado: 422, motivo: `demasiadas redirecciones (máximo ${REDIRECCIONES_MAX})` };
}

/**
 * Un GET, con tope de tamaño mientras llega y de tiempo en total.
 *
 * @param {NonNullable<Deps["request"]>} request
 * @param {URL} url
 * @param {ReturnType<typeof crearLookupSeguro>} lookup
 * @param {number} timeoutMs
 * @param {number} maxBytes
 * @returns {Promise<{ estado: number, ubicacion: string | null, contentType: string, bytes: Buffer }>}
 */
function pedir(request, url, lookup, timeoutMs, maxBytes) {
  return new Promise((resolver, rechazar) => {
    let terminado = false;
    /** @param {(v: any) => void} f @param {any} v */
    const fin = (f, v) => {
      if (terminado) return;
      terminado = true;
      clearTimeout(reloj);
      f(v);
    };
    const req = request(
      url,
      {
        method: "GET",
        lookup,
        // Sin reutilizar conexiones: cada descarga hace su propia comprobación.
        agent: false,
        headers: { accept: "*/*", "accept-encoding": "identity", "user-agent": "dcasa-puente-wa/1" },
      },
      (res) => {
        const estado = res.statusCode ?? 0;
        const declarado = Number(res.headers["content-length"] ?? 0);
        if (estado === 200 && declarado > maxBytes) {
          res.destroy();
          fin(rechazar, Object.assign(new Error("demasiado grande"), { code: "ETOOBIG" }));
          return;
        }
        // Una redirección o un error no necesita su cuerpo.
        if (estado !== 200) {
          res.resume();
          fin(resolver, {
            estado,
            ubicacion: typeof res.headers.location === "string" ? res.headers.location : null,
            contentType: "",
            bytes: Buffer.alloc(0),
          });
          return;
        }
        /** @type {Buffer[]} */
        const trozos = [];
        let total = 0;
        res.on("data", (/** @type {Buffer} */ t) => {
          total += t.length;
          if (total > maxBytes) {
            res.destroy();
            fin(rechazar, Object.assign(new Error("demasiado grande"), { code: "ETOOBIG" }));
            return;
          }
          trozos.push(t);
        });
        res.on("end", () =>
          fin(resolver, {
            estado,
            ubicacion: null,
            contentType: String(res.headers["content-type"] ?? ""),
            bytes: Buffer.concat(trozos),
          }),
        );
        res.on("error", (/** @type {Error} */ e) => fin(rechazar, e));
        res.on("close", () => {
          if (!res.complete) fin(rechazar, Object.assign(new Error("conexión cortada"), { code: "ECONNRESET" }));
        });
      },
    );
    const reloj = setTimeout(() => {
      req.destroy();
      fin(rechazar, Object.assign(new Error("tiempo agotado"), { code: "ETIMEDOUT" }));
    }, timeoutMs);
    req.on("error", (/** @type {Error} */ e) => fin(rechazar, e));
    req.end();
  });
}
