// Instagram por «inicio de sesión de Instagram» («Instagram API with Instagram Login», `graph.instagram.com`): la segunda puerta.
//
// Por qué existe (2026-11-12): por la página (Messenger Platform, meta.ts) Meta solo manda los avisos de cuentas con papel en la app
// mientras la app no tenga el acceso avanzado; a los clientes de verdad no les llegaba nada. Con esta puerta la app atiende SOLO la
// cuenta propia de D'CASA (@dcasapty), y Meta dice que para eso basta el acceso estándar (docs/JUAN_CANALES.md §3).
//
//   · GET  /webhooks/instagram → verificación con el MISMO META_VERIFY_TOKEN (solo con la puerta lista: INSTAGRAM_APP_SECRET puesto).
//   · POST /webhooks/instagram → firma `X-Hub-Signature-256` con INSTAGRAM_APP_SECRET (la clave secreta de la app de Instagram,
//     distinta de la de Facebook). El aviso tiene el mismo formato que por la página (`entry[].messaging[]`, `is_echo`).
//   · Solo se atienden los mensajes a la cuenta de D'CASA (los ids que da `GET /me` y, si está, INSTAGRAM_ACCOUNT_ID). Si todavía no
//     se sabe cuál es, se atiende lo que Meta firma para la cuenta que manda el aviso (`entry.id` igual al lado de la tienda) y /salud
//     lo dice: nunca se contesta con error por eso (Meta desuscribe una app que falla mucho).
//   · El envío es la misma maquinaria que por la página (metaComun.ts) hablando con `graph.instagram.com/<v>/me/messages` y la llave
//     de Instagram (la renovada, si Juan ya la renovó: instagramLlave.ts). Esta puerta además acepta PDF.
//   · Antes del 200 esta puerta espera como mucho ~1 s (la cuenta y anotar avisos ajenos); con lo de rutas.ts (configuración ≤ 1 s
//     y guardar ≤ 3 s) queda por debajo de los 5 s.
//
// El cliente: Meta dice que el «Instagram-scoped ID» es propio de la persona y de la cuenta de Instagram con la que habla, el mismo en
// todas las apps (developers.facebook.com/documentation/instagram-platform/overview, «Scoped User IDs»): por las dos puertas el
// `id_externo` debería ser el mismo y la conversación sigue en el mismo hilo de Odoo. Si un día no lo fuera, ese cliente aparecería
// UNA vez como conversación nueva (y la vieja queda como historial); como a los clientes reales nunca les llegó nada por la página,
// solo pasaría con las cuentas de prueba (las que tienen papel en la app).

import type { Env } from "../env";
import { firmaMetaValida } from "../seguridad";
import { urlInstagram } from "./graph";
import {
  anotarAjenos,
  CLAVE_AJENOS,
  CLAVE_SUSCRIPCION,
  cuentaFija,
  cuentaGuardada,
  descubrirCuenta,
  diasQueQuedan,
  fechaPanama,
  leerEstado,
  leerGuardado,
  limpiarRechazo,
  llaveroDelGlobal,
  marcarRechazo,
  PLAZO_CRON_MS,
  PUERTA_INSTAGRAM,
  renovarLlave,
  revisarSuscripcion,
  URGENTE_MS,
  VENTANA_AJENOS_MS,
  VIGENCIA_SUSCRIPCION_MS,
  venceDe,
  type Ajenos,
  type DepsLlave,
  type Suscripcion,
} from "./instagramLlave";
import { anotarIgnorados, comentariosDeMeta, traeComentarios } from "./metaComentarios";
import { eventosDeMeta, maquinaMeta, respuestaDeVerificacion, type MaquinaMeta, type MetaCuerpo, type OpcionesMeta } from "./metaComun";
import { faltantesDe, json, ok200, type Capacidades, type ResultadoEnvio, type ResultadoWebhook, type Saliente, type SaludLocal } from "./tipos";

export const RUTA_INSTAGRAM_LOGIN = "/webhooks/instagram";

/** Instagram por esta puerta: admite PDF; el texto, según Meta, «UTF-8 y 1000 bytes o menos» (se corta por bytes, no por letras). */
export const CAPACIDADES_INSTAGRAM_LOGIN: Capacidades = { imagenes: true, documentos: true, ventana24h: true, maxTexto: 1000, maxBytesTexto: 1000 };

/** Lo más que el webhook espera a saber la cuenta (leerla del Durable Object o, la primera vez, preguntarla a Meta). */
const PLAZO_CUENTA_MS = 700;
/** El `GET /me` desde el webhook (dentro del plazo de arriba). */
const PLAZO_ME_WEBHOOK_MS = 600;
/** Lo más que el webhook espera para anotar avisos de otra cuenta (para /salud). */
const PLAZO_AJENOS_MS = 250;
/** Cuánto se recuerdan, en memoria, la llave vigente y la cuenta (las dos viven en el Durable Object `Global`). */
const MEMORIA_MS = 60_000;
/** Si `/me` falló, no se vuelve a preguntar desde el webhook hasta dentro de esto (el cron sigue probando cada hora). */
const ESPERA_TRAS_FALLO_MS = 10 * 60_000;

export interface PuertaInstagram {
  recibir(req: Request, env: Env): Promise<ResultadoWebhook>;
  faltantes(env: Env): string[];
  enviar(salida: Saliente, env: Env): Promise<ResultadoEnvio>;
  nombreDePerfil(para: string, env: Env): Promise<string | null>;
  fotoDePerfil(para: string, env: Env): Promise<{ bytes: Uint8Array; mime: string } | null>;
  escribiendo(para: string, env: Env): Promise<void>;
  saludLocal(env: Env): Promise<SaludLocal>;
  /** El cron: renovar la llave si toca, averiguar la cuenta si no se sabe y mirar la suscripción. */
  mantener(env: Env): Promise<void>;
  /** Contestar comentarios por `graph.instagram.com` (respuesta privada, pública y la publicación comentada). */
  comentarios: Pick<MaquinaMeta, "responderEnPrivado" | "responderEnPublico" | "publicacion">;
}

/**
 * Solo los avisos de la tienda: con `ids`, los de esas cuentas; sin ellos (todavía no se sabe la cuenta), los que son coherentes
 * (`entry.id` igual al lado de la tienda: quien recibe un mensaje del cliente, o quien escribe un eco). Los mensajes de prueba de
 * Meta (`is_self`) nunca.
 */
export function soloDeLaCuenta(cuerpo: MetaCuerpo, ids: ReadonlySet<string> | null): { cuerpo: MetaCuerpo; ignorados: number; ajena: string | null } {
  let ignorados = 0;
  let ajena: string | null = null;
  const entry = (cuerpo.entry ?? []).flatMap((en) => {
    const id = String(en.id ?? "");
    const permitidos = ids ?? new Set(id ? [id] : []);
    const n = (en.messaging?.filter((ev) => ev.message).length ?? 0) + (en.changes?.filter((c) => c.field === "comments").length ?? 0);
    if (!permitidos.has(id)) {
      ignorados += n;
      if (n > 0) ajena = id;
      return [];
    }
    const messaging = (en.messaging ?? []).filter((ev) => {
      if (ev.message?.is_self === true) return false;
      const tienda = ev.message?.is_echo === true ? ev.sender?.id : ev.recipient?.id;
      const ok = tienda === undefined || permitidos.has(String(tienda));
      if (!ok && ev.message) {
        ignorados++;
        ajena = String(tienda);
      }
      return ok;
    });
    return [{ ...en, messaging }];
  });
  return { cuerpo: { ...cuerpo, entry }, ignorados, ajena };
}

/** Una promesa con plazo: si no termina a tiempo, `defecto` (sin lanzar). */
export async function conPlazo<T>(p: Promise<T>, ms: number, defecto: T): Promise<T> {
  let reloj: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([p.catch(() => defecto), new Promise<T>((r) => (reloj = setTimeout(() => r(defecto), ms)))]);
  } finally {
    clearTimeout(reloj);
  }
}

export function crearPuertaInstagram(op: OpcionesMeta = {}): PuertaInstagram {
  const f: typeof fetch = op.fetch ?? ((...a) => fetch(...a));
  const llavero = op.llavero ?? llaveroDelGlobal;
  const ahora = op.ahora ?? (() => Date.now());
  let recordada: { pegada: string; llave: string; rechazada: boolean; hasta: number } | null = null;
  let cuentaRecordada: { pegada: string; ids: string[]; hasta: number } | null = null;
  let falloDeCuenta: { pegada: string; hasta: number } | null = null;
  /** Ya llegó un aviso firmado con INSTAGRAM_APP_SECRET: no hace falta probar también la clave de Facebook. */
  let firmaIgVista = false;

  /** La llave más nueva: la renovada por Juan (si viene de la pegada de ahora), si no la pegada. */
  async function llave(env: Env): Promise<string | undefined> {
    const pegada = env.INSTAGRAM_TOKEN?.trim();
    if (!pegada) return undefined;
    const t = ahora();
    if (recordada && recordada.pegada === pegada && t < recordada.hasta) return recordada.llave;
    try {
      const estado = await leerEstado(env, llavero, t);
      const vigente = estado?.llave ?? pegada;
      recordada = { pegada, llave: vigente, rechazada: !!estado?.rechazada, hasta: t + MEMORIA_MS };
      return vigente;
    } catch (e) {
      // Sin poder leer el Durable Object se usa la pegada SOLO para esta vez (no se recuerda: la vigente puede ser la renovada).
      console.warn("[juan] instagram: no pude leer la llave renovada; esta vez uso la pegada:", e instanceof Error ? e.message.slice(0, 120) : "error");
      return pegada;
    }
  }

  const deps: DepsLlave & { llave(env: Env): Promise<string | undefined> } = { fetch: f, llavero, ahora, llave };

  /** Los ids de la cuenta de D'CASA (los de `/me` y, si está bien escrita, INSTAGRAM_ACCOUNT_ID). Vacío = todavía no se sabe. */
  async function idsDeLaTienda(env: Env, plazoMe: number): Promise<string[]> {
    const pegada = env.INSTAGRAM_TOKEN?.trim() ?? "";
    const fija = cuentaFija(env).id;
    const t = ahora();
    let ids: string[] = [];
    if (cuentaRecordada && cuentaRecordada.pegada === pegada && t < cuentaRecordada.hasta) {
      ids = cuentaRecordada.ids;
    } else if (falloDeCuenta && falloDeCuenta.pegada === pegada && t < falloDeCuenta.hasta) {
      ids = (await cuentaGuardada(env, llavero).catch(() => null))?.ids ?? [];
    } else {
      const { cuenta, fallo } = await descubrirCuenta(env, deps, plazoMe);
      ids = cuenta?.ids ?? [];
      if (fallo) falloDeCuenta = { pegada, hasta: t + ESPERA_TRAS_FALLO_MS };
      else {
        falloDeCuenta = null;
        if (ids.length) cuentaRecordada = { pegada, ids, hasta: t + MEMORIA_MS };
      }
    }
    return [...new Set([...ids, ...(fija ? [fija] : [])])];
  }

  const maquina = maquinaMeta(op, {
    url: urlInstagram,
    llave,
    secreto: "INSTAGRAM_TOKEN",
    messagingType: false,
    pdfEnInstagram: true,
    async rechazoDeLlave(env, motivo) {
      recordada = null; // la próxima vez se vuelve a leer (quizá ya hay otra)
      await marcarRechazo(env, deps, "al enviar", motivo);
    },
    async llaveFunciono(env) {
      if (!recordada?.rechazada) return;
      recordada = { ...recordada, rechazada: false };
      await limpiarRechazo(env, deps);
    },
  });

  return {
    faltantes(env) {
      return faltantesDe({ INSTAGRAM_TOKEN: !!env.INSTAGRAM_TOKEN?.trim(), INSTAGRAM_APP_SECRET: !!env.INSTAGRAM_APP_SECRET?.trim(), META_VERIFY_TOKEN: !!env.META_VERIFY_TOKEN });
    },

    async recibir(req, env) {
      const nada = (respuesta: Response): ResultadoWebhook => ({ respuesta, entrantes: [] });
      const secretoIg = env.INSTAGRAM_APP_SECRET?.trim();
      // Sin la clave de la app de Instagram la puerta no está lista: tampoco se verifica la URL (Meta la daría por buena y después
      // cada aviso fallaría).
      if (req.method === "GET") return nada(secretoIg ? respuestaDeVerificacion(req, env.META_VERIFY_TOKEN) : new Response("falta INSTAGRAM_APP_SECRET", { status: 403 }));
      if (req.method !== "POST") return nada(new Response("método no permitido", { status: 405 }));

      // La firma se calcula sobre el cuerpo CRUDO, con la clave secreta de la app de INSTAGRAM. Meta escribe solo «la clave secreta
      // de tu app» (developers.facebook.com/documentation/instagram-platform/webhooks/setup): mientras no haya llegado ninguno firmado
      // con la de Instagram, si no cuadra y la de Facebook de D'CASA (META_APP_SECRET) sí, se acepta y queda anotado.
      const crudo = await req.text();
      const firma = req.headers.get("x-hub-signature-256");
      if (await firmaMetaValida(crudo, firma, secretoIg)) {
        firmaIgVista = true;
      } else {
        if (!secretoIg || firmaIgVista || !(await firmaMetaValida(crudo, firma, env.META_APP_SECRET))) return nada(new Response("firma inválida", { status: 401 }));
        console.warn("[juan] /webhooks/instagram: el aviso venía firmado con META_APP_SECRET (la clave de Facebook), no con INSTAGRAM_APP_SECRET");
      }
      let cuerpo: MetaCuerpo;
      try {
        cuerpo = JSON.parse(crudo) as MetaCuerpo;
      } catch {
        return nada(ok200());
      }
      if (cuerpo.object !== "instagram") return nada(ok200());
      // Lecturas, reacciones, postbacks…: lo que hoy se ignora, se ignora igual (y no hace falta saber la cuenta). Los comentarios sí
      // se miran (campo `comments`).
      if (eventosDeMeta(cuerpo, Date.now()).length === 0 && !traeComentarios(cuerpo)) return nada(json({ ok: true }));

      const ids = await conPlazo(idsDeLaTienda(env, PLAZO_ME_WEBHOOK_MS), PLAZO_CUENTA_MS, [] as string[]);
      if (ids.length === 0) console.warn("[juan] instagram: todavía no sé cuál es la cuenta de D'CASA; atiendo lo que Meta firma para la cuenta que manda el aviso");
      const { cuerpo: deLaCuenta, ignorados, ajena } = soloDeLaCuenta(cuerpo, ids.length ? new Set(ids) : null);
      if (ignorados > 0) {
        console.warn(`[juan] instagram: ${ignorados} aviso(s) que no son de la cuenta de D'CASA se ignoran${ajena ? ` (cuenta …${ajena.slice(-4)})` : ""}`);
        await conPlazo(anotarAjenos(env, deps, ignorados, ajena ?? ""), PLAZO_AJENOS_MS, undefined);
      }
      // Los comentarios de las publicaciones de la cuenta: los de la propia cuenta (sus respuestas) se ignoran.
      const { entrantes: comentarios, ignorados: deComentarios } = comentariosDeMeta(deLaCuenta, Date.now(), { puerta: "instagram_login", ...(ids.length ? { propios: new Set(ids) } : {}) });
      anotarIgnorados(RUTA_INSTAGRAM_LOGIN, deComentarios);
      // Como por la página: 200 cuando cada mensaje ya quedó guardado (`guardarAntes`, rutas.ts). Los archivos llegan como `url`.
      return { respuesta: json({ ok: true }), entrantes: [...eventosDeMeta(deLaCuenta, Date.now()), ...comentarios], guardarAntes: true };
    },

    enviar: (salida, env) => maquina.enviar("instagram", salida, env),
    comentarios: maquina,
    nombreDePerfil: (para, env) => maquina.nombreDePerfil("instagram", para, env),
    fotoDePerfil: (para, env) => maquina.fotoDePerfil(para, env),
    escribiendo: (para, env) => maquina.escribiendo(para, env),

    async saludLocal(env) {
      const local: SaludLocal = { puerta: PUERTA_INSTAGRAM };
      const t = ahora();
      const problemas: string[] = [];
      const avisos: string[] = [];
      if (cuentaFija(env).mala) problemas.push("INSTAGRAM_ACCOUNT_ID no es el número de una cuenta de Instagram: se ignora (bórralo o déjalo solo con números)");
      const estado = await leerEstado(env, llavero, t);
      if (estado) {
        const v = venceDe(estado);
        local.llave = {
          vence: fechaPanama(v.ts),
          vence_seguro: v.seguro,
          dias_restantes: diasQueQuedan(v.ts, t),
          renovada: estado.renovadaEn !== undefined ? fechaPanama(estado.renovadaEn) : null,
          renovacion: estado.error ? "fallo" : estado.renovadaEn !== undefined ? "ok" : "pendiente",
        };
        // Frases estables (con la fecha, no con los días): el cron avisa una vez por frase.
        const cuando = `${v.seguro ? "vence" : "vence a más tardar"} el ${fechaPanama(v.ts)}`;
        if (estado.rechazada) {
          const r = estado.rechazada;
          problemas.push(
            `Meta rechaza la llave de Instagram (INSTAGRAM_TOKEN) desde el ${fechaPanama(r.desde)} (${r.donde}: ${r.motivo}): Juan no puede contestar por Instagram; genera otra en Meta y pégala en Cloudflare`,
          );
        } else if (v.ts <= t) {
          problemas.push(`la llave de Instagram (INSTAGRAM_TOKEN) venció${v.seguro ? "" : " a más tardar"} el ${fechaPanama(v.ts)}: Juan ya no puede contestar por Instagram; genera otra en Meta y pégala en Cloudflare`);
        } else if (estado.error) {
          const frase = `no se pudo renovar la llave de Instagram (${estado.error}); ${cuando}`;
          if (v.ts - t <= URGENTE_MS) problemas.push(`${frase}: si no se arregla antes, genera otra en Meta y pégala en INSTAGRAM_TOKEN`);
          else avisos.push(`${frase}; Juan lo vuelve a intentar cada día`);
        }
        const c = await cuentaGuardada(env, llavero);
        if (c?.usuario) local.cuenta = `@${c.usuario}`;
        if (!c && !cuentaFija(env).id && env.INSTAGRAM_APP_SECRET?.trim()) {
          problemas.push(
            "todavía no sé cuál es la cuenta de Instagram de D'CASA (Meta no contestó a /me con INSTAGRAM_TOKEN): mientras tanto atiendo lo que Meta firma para la cuenta que manda cada aviso; revisa la llave o pon la variable INSTAGRAM_ACCOUNT_ID",
          );
        }
        const s = await leerGuardado<Suscripcion>(env, llavero, CLAVE_SUSCRIPCION);
        if (s && t - s.ts < VIGENCIA_SUSCRIPCION_MS) {
          local.suscripcion = s.estado;
          if (s.estado === "no") problemas.push("Meta no tiene la app suscrita a los mensajes de la cuenta de Instagram (sin «messages»): en Meta, al lado de @dcasapty, enciende «Webhook subscription»");
        }
      }
      const a = await leerGuardado<Ajenos>(env, llavero, CLAVE_AJENOS);
      if (a && t - a.ultimo < VENTANA_AJENOS_MS) {
        local.ignorados = { cantidad: a.cantidad, ultimo: fechaPanama(a.ultimo), cuenta: a.cuenta };
        problemas.push(`desde el ${fechaPanama(a.desde)} se ignoran avisos de Instagram de otra cuenta (${a.cuenta}), no de la de D'CASA: si esa es la de D'CASA, revisa o borra INSTAGRAM_ACCOUNT_ID`);
      }
      if (problemas.length) local.problemas = problemas;
      if (avisos.length) local.avisos = avisos;
      return local;
    },

    async mantener(env) {
      if (!env.INSTAGRAM_TOKEN?.trim()) return;
      const r = await renovarLlave(env, deps);
      if (r === "renovada") recordada = null; // la de memoria ya no es la más nueva
      // La cuenta, si todavía no se sabe (o la llave es otra); desde el cron sí se espera a Meta (con su plazo).
      const { cuenta, fallo } = await descubrirCuenta(env, deps, PLAZO_CRON_MS);
      if (!fallo && cuenta) {
        falloDeCuenta = null;
        cuentaRecordada = { pegada: env.INSTAGRAM_TOKEN.trim(), ids: cuenta.ids, hasta: ahora() + MEMORIA_MS };
      }
      await revisarSuscripcion(env, deps);
    },
  };
}
