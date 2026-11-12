// Messenger e Instagram (Meta oficial). Una sola app de Meta cubre ambos: el webhook trae el mismo formato
// (`entry[].messaging[]`) y el envío es la Send API (`graph.facebook.com/<versión>/me/messages`) con el token de la Página.
//
//   · GET  /webhooks/meta  → verificación (hub.verify_token = META_VERIFY_TOKEN; se devuelve hub.challenge)
//   · POST /webhooks/meta  → firma `X-Hub-Signature-256` (HMAC-SHA256 del cuerpo con META_APP_SECRET), siempre
//   · Solo se puede escribir dentro de las 24 h del último mensaje del cliente (messaging_type RESPONSE).
//   · `is_echo` = lo escribió la Página (una persona desde la bandeja de Meta, o este mismo bot): `propio:true`.
//
// Instagram tiene una SEGUNDA PUERTA (2026-11-12): «inicio de sesión de Instagram» (`graph.instagram.com`, instagramLogin.ts), con
// su propio webhook (`/webhooks/instagram`), su llave (INSTAGRAM_TOKEN, que Juan renueva) y su clave secreta (INSTAGRAM_APP_SECRET).
// Si está alguno de esos dos secretos, Instagram va por ahí (envío, nombre, foto, salud) y lo de Instagram que llegue por la página
// se ignora (no se atiende dos veces lo mismo). Sin ellos, todo queda como antes. Messenger no cambia.

import type { Env } from "../env";
import { firmaMetaValida } from "../seguridad";
import { urlGraph } from "./graph";
import { crearPuertaInstagram, CAPACIDADES_INSTAGRAM_LOGIN, RUTA_INSTAGRAM_LOGIN } from "./instagramLogin";
import { PUERTA_PAGINA, puertaInstagramElegida } from "./instagramLlave";
import { eventosDeMeta, maquinaMeta, respuestaDeVerificacion, type MetaCuerpo, type OpcionesMeta, type PuertaMeta } from "./metaComun";
import {
  faltantesDe,
  json,
  ok200,
  type AdaptadorCanal,
  type Capacidades,
  type CanalId,
  type ResultadoEnvio,
  type ResultadoWebhook,
  type Saliente,
  type SaludCanal,
  type SaludLocal,
} from "./tipos";

export { eventosDeMeta, MAX_ADJUNTO_MESSENGER_BYTES, MAX_FOTO_INSTAGRAM_BYTES, type OpcionesMeta } from "./metaComun";

const CAPACIDADES: Record<"messenger" | "instagram", Capacidades> = {
  messenger: { imagenes: true, documentos: true, ventana24h: true, maxTexto: 1900 },
  // Instagram (por la página) no admite documentos y su texto es más corto.
  instagram: { imagenes: true, documentos: false, ventana24h: true, maxTexto: 950 },
};

/** La página de Facebook: `graph.facebook.com` con META_PAGE_TOKEN. */
const PUERTA_DE_LA_PAGINA: PuertaMeta = {
  url: urlGraph,
  llave: async (env) => env.META_PAGE_TOKEN || undefined,
  secreto: "META_PAGE_TOKEN",
  messagingType: true,
  pdfEnInstagram: false,
};

export function crearMeta(op: OpcionesMeta = {}): AdaptadorCanal {
  const pagina = maquinaMeta(op, PUERTA_DE_LA_PAGINA);
  const ig = crearPuertaInstagram(op);
  /** Este canal va por la segunda puerta (Instagram con alguno de sus secretos). */
  const porInstagram = (canal: CanalId, env: Env | undefined) => canal === "instagram" && !!env && puertaInstagramElegida(env);
  const deCanal = (canal: CanalId): "messenger" | "instagram" => (canal === "instagram" ? "instagram" : "messenger");

  return {
    canales: ["messenger", "instagram"],
    ruta: "/webhooks/meta",
    otrasRutas: [RUTA_INSTAGRAM_LOGIN],

    capacidades(canal: CanalId, env?: Env): Capacidades {
      if (porInstagram(canal, env)) return CAPACIDADES_INSTAGRAM_LOGIN;
      return canal === "instagram" ? CAPACIDADES.instagram : CAPACIDADES.messenger;
    },

    faltantes(env: Env, canal: CanalId): string[] {
      if (porInstagram(canal, env)) return ig.faltantes(env);
      return faltantesDe({ META_PAGE_TOKEN: !!env.META_PAGE_TOKEN, META_APP_SECRET: !!env.META_APP_SECRET, META_VERIFY_TOKEN: !!env.META_VERIFY_TOKEN });
    },

    configurado(env: Env, canal: CanalId): boolean {
      return this.faltantes(env, canal).length === 0;
    },

    async recibir(req: Request, env: Env): Promise<ResultadoWebhook> {
      // La segunda puerta de Instagram tiene su propio webhook (y su propia clave secreta).
      if (new URL(req.url).pathname.replace(/\/+$/, "") === RUTA_INSTAGRAM_LOGIN) return ig.recibir(req, env);

      const nada = (respuesta: Response): ResultadoWebhook => ({ respuesta, entrantes: [] });

      if (req.method === "GET") return nada(respuestaDeVerificacion(req, env.META_VERIFY_TOKEN));
      if (req.method !== "POST") return nada(new Response("método no permitido", { status: 405 }));

      // La firma se calcula sobre el cuerpo CRUDO: se lee como texto antes de interpretarlo.
      const crudo = await req.text();
      if (!(await firmaMetaValida(crudo, req.headers.get("x-hub-signature-256"), env.META_APP_SECRET))) {
        return nada(new Response("firma inválida", { status: 401 }));
      }
      let cuerpo: MetaCuerpo;
      try {
        cuerpo = JSON.parse(crudo) as MetaCuerpo;
      } catch {
        return nada(ok200());
      }
      if (cuerpo.object === "instagram" && puertaInstagramElegida(env)) {
        // Instagram va por la segunda puerta: lo que llegue por la página (cuentas con papel en la app) llegaría dos veces.
        if ((cuerpo.entry ?? []).some((e) => e.messaging?.length)) console.warn("[juan] /webhooks/meta: Instagram va por /webhooks/instagram; el aviso que llegó por la página se ignora");
        return nada(json({ ok: true }));
      }
      // Como WhatsApp Cloud: se contesta 200 cuando cada mensaje ya quedó guardado (`guardarAntes`, rutas.ts). Los archivos de
      // Messenger e Instagram llegan como `url` (no hay nada que bajar con credenciales antes de guardarlos).
      return { respuesta: json({ ok: true }), entrantes: eventosDeMeta(cuerpo, Date.now()), guardarAntes: true };
    },

    async enviar(canal: CanalId, salida: Saliente, env: Env): Promise<ResultadoEnvio> {
      if (porInstagram(canal, env)) return ig.enviar(salida, env);
      return pagina.enviar(deCanal(canal), salida, env);
    },

    async nombreDePerfil(canal: CanalId, para: string, env: Env): Promise<string | null> {
      if (porInstagram(canal, env)) return ig.nombreDePerfil(para, env);
      return pagina.nombreDePerfil(deCanal(canal), para, env);
    },

    async fotoDePerfil(canal: CanalId, para: string, env: Env): Promise<{ bytes: Uint8Array; mime: string } | null> {
      if (porInstagram(canal, env)) return ig.fotoDePerfil(para, env);
      return pagina.fotoDePerfil(para, env);
    },

    async escribiendo(canal: CanalId, para: string, env: Env): Promise<void> {
      if (porInstagram(canal, env)) return ig.escribiendo(para, env);
      return pagina.escribiendo(para, env);
    },

    async salud(canal: CanalId, env: Env): Promise<SaludCanal> {
      return { configurado: this.configurado(env, canal), faltan: this.faltantes(env, canal), conectado: null };
    },

    async saludLocal(canal: CanalId, env: Env): Promise<SaludLocal> {
      if (canal !== "instagram") return {};
      return porInstagram(canal, env) ? ig.saludLocal(env) : { puerta: PUERTA_PAGINA };
    },

    async mantener(env: Env): Promise<void> {
      await ig.mantener(env);
    },
  };
}
