// El Worker del puente: enruta y autentica. La lógica de verdad vive en el Durable
// Object y en los módulos puros; aquí solo hay rutas, tokens y formas de respuesta.
//
// Dos puertas, dos tokens (mínimo privilegio):
//
//   /api/*      WA_TOKEN, el que comparte con el Worker `juan` (y Odoo, para el QR).
//   /puente/*   el token DERIVADO del contenedor (`derivarTokenContenedor`) + su época.
//               Son las rutas por las que el contenedor guarda la sesión y entrega los
//               mensajes entrantes. Con WA_TOKEN no se puede leer la sesión.
//
// Ninguna ruta imprime el QR ni credenciales en los registros, y NINGUNA acepta el
// token en la URL (quedaría en los registros de Cloudflare).

import { entregarAJuan } from "./juan";
import { derivarTokenContenedor, tokenPresentado, tokensIguales, tokenEsApto } from "./comun";
import { leerArchivo } from "./respaldo";
import type { Env, PuenteStub } from "./tipos";
import { validarWebhook } from "../contenedor/lib/contrato.mjs";

export function json(codigo: number, cuerpo: unknown, extra: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(cuerpo), {
    status: codigo,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store", ...extra },
  });
}

/** Una clave de Baileys: `creds`, `pre-key-12`, `session-507…@s.whatsapp.net.0`… */
const CLAVE_VALIDA = /^[\w.:@\-/]{1,300}$/;

/** Más grande que esto, un entrante pendiente se guarda sin el archivo (límite de fila de SQLite: 2 MB). */
export const PENDIENTE_MAX_CARACTERES = 1_000_000;

/** El token del contenedor sale de WA_TOKEN con un HMAC; se recuerda para no recalcularlo por petición. */
const cacheTokenContenedor = new Map<string, string>();
async function tokenDelContenedor(waToken: string): Promise<string> {
  let t = cacheTokenContenedor.get(waToken);
  if (!t) {
    t = await derivarTokenContenedor(waToken);
    cacheTokenContenedor.clear();
    cacheTokenContenedor.set(waToken, t);
  }
  return t;
}

function noAutorizado(request: Request): Response {
  // El 401 no revela nada del token esperado: solo por dónde llegó lo presentado.
  const { via, valor } = tokenPresentado(request);
  return json(401, { error: "Token inválido.", via, presentadoLargo: valor.length });
}

/** Un entrante que no se pudo entregar se guarda para reintentar; si trae un archivo enorme, sin el archivo. */
export function prepararPendiente(texto: string, payload: Record<string, any>): string {
  if (texto.length <= PENDIENTE_MAX_CARACTERES) return texto;
  const { medio, ...resto } = payload;
  return JSON.stringify({
    ...resto,
    medio_omitido: { motivo: "juan_no_disponible", mime: medio?.mime, bytes: Math.floor(((medio?.base64?.length ?? 0) * 3) / 4) },
  });
}

export async function manejar(request: Request, env: Env, stub: () => PuenteStub): Promise<Response> {
  const url = new URL(request.url);
  const ruta = url.pathname;

  if (ruta === "/health") return new Response("ok");

  if (!env.WA_TOKEN) return json(500, { error: "Falta el secret WA_TOKEN." });
  if (!env.WA_SESION_CLAVE) return json(500, { error: "Falta el secret WA_SESION_CLAVE." });

  // ── Del contenedor ───────────────────────────────────────────────────────
  if (ruta.startsWith("/puente/")) {
    const presentado = tokenPresentado(request).valor;
    if (!tokensIguales(presentado, await tokenDelContenedor(env.WA_TOKEN))) return noAutorizado(request);
    return rutasDelContenedor(request, env, stub(), ruta, url);
  }

  // ── De Juan (y de quien opera) ───────────────────────────────────────────
  if (ruta.startsWith("/api/")) {
    if (!tokensIguales(tokenPresentado(request).valor, env.WA_TOKEN)) return noAutorizado(request);
    return rutasDeApi(request, env, stub(), ruta, url);
  }

  return json(404, { error: "no existe" });
}

// ── /puente/* ────────────────────────────────────────────────────────────────

async function rutasDelContenedor(request: Request, env: Env, s: PuenteStub, ruta: string, url: URL): Promise<Response> {
  const epoca = request.headers.get("x-wa-epoca");

  if (ruta === "/puente/kv") {
    const clave = url.searchParams.get("clave");
    if (!clave || !CLAVE_VALIDA.test(clave)) return json(400, { error: "Falta ?clave= o no es válida." });
    if (request.method === "GET") {
      const valor = await s.kvGet(clave);
      return valor === null
        ? new Response("no existe", { status: 404 })
        : new Response(valor, { headers: { "content-type": "application/json", "cache-control": "no-store" } });
    }
    if (request.method === "PUT") {
      const r = await s.kvSet(clave, await request.text(), epoca);
      return r.ok ? json(200, { ok: true }) : json(r.status, { error: r.error });
    }
    if (request.method === "DELETE") {
      const r = await s.kvDel(clave, epoca);
      return r.ok ? json(200, { ok: true }) : json(r.status, { error: r.error });
    }
    return json(405, { error: "método no permitido" });
  }

  // El MISMO almacén, por lotes: es lo que hace que el canal se pueda vincular (812 llaves
  // en menos de 30 s). Ver contenedor/lib/auth-remoto.mjs.
  if (ruta === "/puente/kv-lote" && request.method === "POST") {
    let cuerpo: any;
    try {
      cuerpo = await request.json();
    } catch {
      return json(400, { error: "El cuerpo no es JSON." });
    }
    const esLista = (x: unknown) => x === undefined || (Array.isArray(x) && x.every((c) => typeof c === "string" && CLAVE_VALIDA.test(c)));
    const escribirValido =
      cuerpo?.escribir === undefined ||
      (typeof cuerpo.escribir === "object" &&
        cuerpo.escribir !== null &&
        !Array.isArray(cuerpo.escribir) &&
        Object.entries(cuerpo.escribir).every(([k, v]) => CLAVE_VALIDA.test(k) && typeof v === "string"));
    if (!cuerpo || typeof cuerpo !== "object" || !esLista(cuerpo.leer) || !esLista(cuerpo.borrar) || !escribirValido) {
      return json(400, { error: "Se esperaba { leer?: [clave], escribir?: {clave: texto}, borrar?: [clave] }." });
    }
    const r = await s.kvLote({ leer: cuerpo.leer, escribir: cuerpo.escribir, borrar: cuerpo.borrar }, epoca);
    return r.ok ? json(200, r) : json(r.status, { error: r.error });
  }

  // Los ids que el puente ya envió: el contenedor los carga al arrancar para no tomar el
  // eco de un mensaje suyo por una respuesta escrita por una persona.
  if (ruta === "/puente/enviados" && request.method === "GET") {
    return json(200, { ids: await s.enviadosRecientes() });
  }

  // ── Mensajes entrantes: del contenedor hacia el Worker `juan` ──
  if (ruta === "/puente/entrante" && request.method === "POST") {
    const texto = await request.text();
    let payload: Record<string, any>;
    try {
      payload = JSON.parse(texto);
    } catch {
      return json(400, { error: "El cuerpo no es JSON." });
    }
    const errores = validarWebhook(payload);
    if (errores.length) return json(400, { error: "El mensaje no cumple el contrato con Juan.", errores });

    // Quien nos escribe ya no es un destinatario «frío» para los topes de envío.
    if (payload.propio !== true) await s.marcarEntrante(String(payload.de)).catch(() => {});

    const r = await entregarAJuan(env, texto);
    if (r.ok) return json(200, { ok: true, entregado: true });
    // Un cuerpo que Juan rechaza por malformado no se arregla repitiendo: no se guarda.
    if (r.definitivo && [400, 413, 422].includes(r.status)) {
      return json(422, { ok: false, error: r.motivo, juan_status: r.status });
    }
    // Juan no está disponible (se está desplegando, un error suyo…): el mensaje del cliente
    // NO se pierde. Se guarda y la vigilancia lo reintenta hasta que Juan lo reciba.
    try {
      await s.encolarPendiente(prepararPendiente(texto, payload));
    } catch {
      return json(503, { ok: false, error: `${r.motivo}; y no se pudo guardar para reintentar` });
    }
    return json(202, { ok: true, entregado: false, encolado: true, motivo: r.motivo });
  }

  return json(404, { error: "no existe" });
}

// ── /api/* ───────────────────────────────────────────────────────────────────

async function rutasDeApi(request: Request, env: Env, s: PuenteStub, ruta: string, url: URL): Promise<Response> {
  if (ruta === "/api/estado" && request.method === "GET") {
    const estado = await s.estadoPublico();
    return json(200, { ...estado, token: { apto: tokenEsApto(env.WA_TOKEN) } });
  }

  // El QR solo con token, sin caché y NUNCA a los registros. El contenedor tampoco lo sirve
  // con la sesión conectada: un QR servido con la sesión activa dejaría que cualquiera con
  // el panel abierto vincule OTRO teléfono.
  if (ruta === "/api/qr" && request.method === "GET") {
    const r = await s.qr();
    return json(r.status, r.cuerpo);
  }

  if (ruta === "/api/enviar" && request.method === "POST") {
    const r = await s.enviar(await request.text());
    return json(r.status, r.cuerpo, r.status === 429 || r.status === 503 ? { "retry-after": String(retryAfter(r.cuerpo)) } : {});
  }

  if (ruta === "/api/desvincular" && request.method === "POST") {
    const r = await s.desvincular();
    return json(r.status, r.cuerpo);
  }

  if (ruta === "/api/reiniciar" && request.method === "POST") {
    const diario = await s.matar();
    return json(200, {
      ok: true,
      mensaje: "Contenedor reiniciado. Vuelve en menos de un minuto y no debe pedir QR.",
      reinicios_forzados: diario.reiniciosForzados,
    });
  }

  // ── Copias de la sesión ──
  if (ruta === "/api/copias" && request.method === "GET") {
    return json(200, { ok: true, copias: await s.listarCopias() });
  }
  if (ruta === "/api/copias" && request.method === "POST") {
    return json(200, { ok: true, ...(await s.copiarAhora()) });
  }
  if (ruta === "/api/copias/exportar" && request.method === "GET") {
    const archivo = await s.exportarCopia(url.searchParams.get("id") ?? undefined);
    if (!archivo) return json(404, { error: "No hay ninguna copia que exportar." });
    return json(200, archivo, { "content-disposition": `attachment; filename="sesion-${archivo.copia}.json"` });
  }
  if (ruta === "/api/restaurar" && request.method === "POST") {
    let cuerpo: { copia?: string; origen?: string; archivo?: unknown } = {};
    try {
      cuerpo = (await request.json()) ?? {};
    } catch {
      return json(400, { error: "El cuerpo no es JSON." });
    }
    try {
      if (cuerpo.origen === "r2") {
        if (!env.COPIAS) return json(409, { error: "No hay bucket COPIAS enlazado." });
        if (!cuerpo.copia || !/^[\w\-:]+$/.test(cuerpo.copia)) return json(400, { error: "Falta «copia» (el id de la copia en R2)." });
        const objeto = await env.COPIAS.get(`sesion/${cuerpo.copia}.json`);
        if (!objeto) return json(404, { error: "Esa copia no está en R2." });
        const r = await s.restaurar({ archivo: leerArchivo(await objeto.text()) });
        return json(r.status, r.cuerpo);
      }
      if (cuerpo.archivo !== undefined) {
        const r = await s.restaurar({ archivo: leerArchivo(JSON.stringify(cuerpo.archivo)) });
        return json(r.status, r.cuerpo);
      }
      const r = await s.restaurar({ copia: cuerpo.copia });
      return json(r.status, r.cuerpo);
    } catch (e) {
      return json(400, { error: e instanceof Error ? e.message : String(e) });
    }
  }

  if (ruta === "/api/podar" && request.method === "POST") {
    return json(200, { ok: true, ...(await s.podar()) });
  }
  if (ruta === "/api/recifrar" && request.method === "POST") {
    return json(200, { ok: true, ...(await s.recifrar()) });
  }

  return json(404, { error: "no existe" });
}

function retryAfter(cuerpo: unknown): number {
  const c = cuerpo as { reintentar_en_s?: unknown } | null;
  const n = Number(c?.reintentar_en_s);
  return Number.isFinite(n) && n > 0 ? Math.ceil(n) : 30;
}
