// Instagram por «inicio de sesión de Instagram» («Instagram API with Instagram Login», `graph.instagram.com`): la segunda puerta.
//
// Por qué existe (2026-11-12): por la página (Messenger Platform, meta.ts) Meta solo manda los avisos de cuentas con papel en la app
// mientras la app no tenga el acceso avanzado; a los clientes de verdad no les llegaba nada. Con esta puerta la app atiende SOLO la
// cuenta propia de D'CASA (@dcasapty), y Meta dice que para eso basta el acceso estándar (docs/JUAN_CANALES.md §3).
//
//   · GET  /webhooks/instagram → verificación con el MISMO META_VERIFY_TOKEN.
//   · POST /webhooks/instagram → firma `X-Hub-Signature-256` con INSTAGRAM_APP_SECRET (la clave secreta de la app de Instagram,
//     distinta de la de Facebook). El aviso tiene el mismo formato que por la página (`entry[].messaging[]`, `is_echo`).
//   · Solo se atienden los mensajes a la cuenta de D'CASA (INSTAGRAM_ACCOUNT_ID o la que dice `GET /me`).
//   · El envío es la misma maquinaria que por la página (metaComun.ts) hablando con `graph.instagram.com/<v>/me/messages` y la llave
//     de Instagram (la renovada, si Juan ya la renovó: instagramLlave.ts). Esta puerta además acepta PDF.
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
  cuentaDeInstagram,
  cuentaGuardada,
  diasQueQuedan,
  fechaPanama,
  leerEstado,
  llaveroDelGlobal,
  PUERTA_INSTAGRAM,
  renovarLlave,
  URGENTE_MS,
  venceDe,
  type CuentaInstagram,
  type DepsLlave,
} from "./instagramLlave";
import { eventosDeMeta, maquinaMeta, respuestaDeVerificacion, type MetaCuerpo, type OpcionesMeta } from "./metaComun";
import { faltantesDe, json, ok200, type Capacidades, type ResultadoEnvio, type ResultadoWebhook, type Saliente, type SaludLocal } from "./tipos";

export const RUTA_INSTAGRAM_LOGIN = "/webhooks/instagram";

/**
 * Instagram por esta puerta: admite PDF; el texto, según Meta, «UTF-8 y 1000 bytes o menos» (no letras): 800 letras deja aire para
 * tildes y emojis.
 */
export const CAPACIDADES_INSTAGRAM_LOGIN: Capacidades = { imagenes: true, documentos: true, ventana24h: true, maxTexto: 800 };

/** Cuánto se espera, dentro del webhook, a saber cuál es la cuenta (solo la primera vez: después está guardada). */
const PLAZO_CUENTA_MS = 1_500;
/** Cuánto se recuerdan, en memoria, la llave vigente y la cuenta (las dos viven en el Durable Object `Global`). */
const MEMORIA_MS = 60_000;

export interface PuertaInstagram {
  recibir(req: Request, env: Env): Promise<ResultadoWebhook>;
  faltantes(env: Env): string[];
  enviar(salida: Saliente, env: Env): Promise<ResultadoEnvio>;
  nombreDePerfil(para: string, env: Env): Promise<string | null>;
  fotoDePerfil(para: string, env: Env): Promise<{ bytes: Uint8Array; mime: string } | null>;
  escribiendo(para: string, env: Env): Promise<void>;
  saludLocal(env: Env): Promise<SaludLocal>;
  /** El cron: renovar la llave si toca y averiguar la cuenta si no se sabe. */
  mantener(env: Env): Promise<void>;
}

/** Solo los avisos dirigidos a (o escritos por) la cuenta de D'CASA; los mensajes de prueba de Meta (`is_self`) tampoco. */
export function soloDeLaCuenta(cuerpo: MetaCuerpo, ids: ReadonlySet<string>): { cuerpo: MetaCuerpo; ignorados: number } {
  let ignorados = 0;
  const entry = (cuerpo.entry ?? []).flatMap((en) => {
    const n = en.messaging?.length ?? 0;
    if (!ids.has(String(en.id ?? ""))) {
      ignorados += n;
      return [];
    }
    const messaging = (en.messaging ?? []).filter((ev) => {
      if (ev.message?.is_self === true) return false;
      // El lado de la tienda: quien recibe un mensaje del cliente, o quien escribe un eco.
      const tienda = ev.message?.is_echo === true ? ev.sender?.id : ev.recipient?.id;
      const ok = tienda === undefined || ids.has(String(tienda));
      if (!ok) ignorados++;
      return ok;
    });
    return [{ ...en, messaging }];
  });
  return { cuerpo: { ...cuerpo, entry }, ignorados };
}

export function crearPuertaInstagram(op: OpcionesMeta = {}): PuertaInstagram {
  const f: typeof fetch = op.fetch ?? ((...a) => fetch(...a));
  const llavero = op.llavero ?? llaveroDelGlobal;
  const ahora = op.ahora ?? (() => Date.now());
  let recordada: { pegada: string; llave: string; hasta: number } | null = null;
  let cuentaRecordada: { pegada: string; fija: string; cuenta: CuentaInstagram; hasta: number } | null = null;

  /** La llave más nueva: la renovada por Juan (si viene de la pegada de ahora), si no la pegada. */
  async function llave(env: Env): Promise<string | undefined> {
    const pegada = env.INSTAGRAM_TOKEN?.trim();
    if (!pegada) return undefined;
    const t = ahora();
    if (recordada && recordada.pegada === pegada && t < recordada.hasta) return recordada.llave;
    let vigente = pegada;
    try {
      const estado = await leerEstado(env, llavero, t);
      if (estado?.llave) vigente = estado.llave;
    } catch (e) {
      console.warn("[juan] instagram: no pude leer la llave renovada; uso la pegada:", e instanceof Error ? e.message.slice(0, 120) : "error");
    }
    recordada = { pegada, llave: vigente, hasta: t + MEMORIA_MS };
    return vigente;
  }

  const deps: DepsLlave & { llave(env: Env): Promise<string | undefined> } = { fetch: f, llavero, ahora, llave };

  async function cuenta(env: Env): Promise<CuentaInstagram | null> {
    const pegada = env.INSTAGRAM_TOKEN?.trim() ?? "";
    const fija = env.INSTAGRAM_ACCOUNT_ID?.trim() ?? "";
    const t = ahora();
    if (cuentaRecordada && cuentaRecordada.pegada === pegada && cuentaRecordada.fija === fija && t < cuentaRecordada.hasta) return cuentaRecordada.cuenta;
    const c = await cuentaDeInstagram(env, deps);
    if (c) cuentaRecordada = { pegada, fija, cuenta: c, hasta: t + MEMORIA_MS };
    return c;
  }

  const maquina = maquinaMeta(op, { url: urlInstagram, llave, secreto: "INSTAGRAM_TOKEN", messagingType: false, pdfEnInstagram: true });

  return {
    faltantes(env) {
      return faltantesDe({ INSTAGRAM_TOKEN: !!env.INSTAGRAM_TOKEN?.trim(), INSTAGRAM_APP_SECRET: !!env.INSTAGRAM_APP_SECRET?.trim(), META_VERIFY_TOKEN: !!env.META_VERIFY_TOKEN });
    },

    async recibir(req, env) {
      const nada = (respuesta: Response): ResultadoWebhook => ({ respuesta, entrantes: [] });
      if (req.method === "GET") return nada(respuestaDeVerificacion(req, env.META_VERIFY_TOKEN));
      if (req.method !== "POST") return nada(new Response("método no permitido", { status: 405 }));

      // La firma se calcula sobre el cuerpo CRUDO, con la clave secreta de la app de INSTAGRAM (no META_APP_SECRET).
      const crudo = await req.text();
      if (!(await firmaMetaValida(crudo, req.headers.get("x-hub-signature-256"), env.INSTAGRAM_APP_SECRET?.trim()))) {
        return nada(new Response("firma inválida", { status: 401 }));
      }
      let cuerpo: MetaCuerpo;
      try {
        cuerpo = JSON.parse(crudo) as MetaCuerpo;
      } catch {
        return nada(ok200());
      }
      if (cuerpo.object !== "instagram") return nada(ok200());
      // Lecturas, reacciones, postbacks…: lo que hoy se ignora, se ignora igual (y no hace falta saber la cuenta).
      if (eventosDeMeta(cuerpo, Date.now()).length === 0) return nada(json({ ok: true }));

      let reloj: ReturnType<typeof setTimeout> | undefined;
      const c = await Promise.race([
        cuenta(env).catch(() => null),
        new Promise<null>((r) => (reloj = setTimeout(() => r(null), PLAZO_CUENTA_MS))),
      ]).finally(() => clearTimeout(reloj));
      if (!c) {
        // Sin saber cuál es la cuenta de D'CASA no se atiende nada: Meta reintenta (hasta 36 h) y /salud dice qué falta.
        console.error("[juan] instagram: no sé cuál es la cuenta de D'CASA (INSTAGRAM_ACCOUNT_ID vacío y /me no contestó); Meta reintentará");
        return nada(new Response("cuenta de Instagram desconocida: reintenta", { status: 503 }));
      }
      const { cuerpo: deLaCuenta, ignorados } = soloDeLaCuenta(cuerpo, new Set(c.ids));
      if (ignorados > 0) {
        const ajenas = [...new Set((cuerpo.entry ?? []).map((e) => String(e.id ?? "")).filter((id) => !c.ids.includes(id)))].map((id) => `…${id.slice(-4)}`);
        console.warn(`[juan] instagram: ${ignorados} aviso(s) que no son de la cuenta de D'CASA se ignoran${ajenas.length ? ` (cuenta ${ajenas.join(", ")})` : ""}`);
      }
      // Como por la página: 200 cuando cada mensaje ya quedó guardado (`guardarAntes`, rutas.ts). Los archivos llegan como `url`.
      return { respuesta: json({ ok: true }), entrantes: eventosDeMeta(deLaCuenta, Date.now()), guardarAntes: true };
    },

    enviar: (salida, env) => maquina.enviar("instagram", salida, env),
    nombreDePerfil: (para, env) => maquina.nombreDePerfil("instagram", para, env),
    fotoDePerfil: (para, env) => maquina.fotoDePerfil(para, env),
    escribiendo: (para, env) => maquina.escribiendo(para, env),

    async saludLocal(env) {
      const local: SaludLocal = { puerta: PUERTA_INSTAGRAM };
      const t = ahora();
      const estado = await leerEstado(env, llavero, t);
      if (!estado) return local;
      const v = venceDe(estado);
      local.llave = {
        vence: fechaPanama(v.ts),
        vence_seguro: v.seguro,
        dias_restantes: diasQueQuedan(v.ts, t),
        renovada: estado.renovadaEn !== undefined ? fechaPanama(estado.renovadaEn) : null,
        renovacion: estado.error ? "fallo" : estado.renovadaEn !== undefined ? "ok" : "pendiente",
      };
      const problemas: string[] = [];
      const avisos: string[] = [];
      // Frases estables (con la fecha, no con los días): el cron avisa una vez por frase.
      const cuando = `${v.seguro ? "vence" : "vence a más tardar"} el ${fechaPanama(v.ts)}`;
      if (v.ts <= t) {
        problemas.push(`la llave de Instagram (INSTAGRAM_TOKEN) venció${v.seguro ? "" : " a más tardar"} el ${fechaPanama(v.ts)}: Juan ya no puede contestar por Instagram; genera otra en Meta y pégala en Cloudflare`);
      } else if (estado.error) {
        const frase = `no se pudo renovar la llave de Instagram (${estado.error}); ${cuando}`;
        if (v.ts - t <= URGENTE_MS) problemas.push(`${frase}: si no se arregla antes, genera otra en Meta y pégala en INSTAGRAM_TOKEN`);
        else avisos.push(`${frase}; Juan lo vuelve a intentar cada día y mientras tanto sigue contestando`);
      }
      const c = await cuentaGuardada(env, llavero);
      if (c?.usuario) local.cuenta = `@${c.usuario}`;
      if (!c && env.INSTAGRAM_APP_SECRET?.trim()) {
        problemas.push(
          "todavía no sé cuál es la cuenta de Instagram de D'CASA (Meta no contestó a /me con INSTAGRAM_TOKEN): los mensajes de Instagram esperan y Meta los reintenta; revisa la llave o pon la variable INSTAGRAM_ACCOUNT_ID",
        );
      }
      if (problemas.length) local.problemas = problemas;
      if (avisos.length) local.avisos = avisos;
      return local;
    },

    async mantener(env) {
      if (!env.INSTAGRAM_TOKEN?.trim()) return;
      const r = await renovarLlave(env, deps);
      if (r === "renovada") recordada = null; // la de memoria ya no es la más nueva
      // La cuenta, si todavía no se sabe (o la llave es otra).
      await cuenta(env).catch(() => null);
    },
  };
}
