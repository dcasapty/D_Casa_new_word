// `POST /tienda/v1/mensaje` (y su `OPTIONS`): el chat de «Brian de la tienda» en dcasapty.com (contrato §2; docs/JUAN.md).
//
// El navegador habla directo con este Worker (no a través de Odoo: una respuesta de IA tarda de 3 a 20 s y no debe ocupar un hilo de
// Odoo). Aquí: CORS (solo los orígenes permitidos), el pase de Odoo (firma, vencimiento y `sid`; su red no se compara) y el cuerpo.
// Lo demás (topes, contexto, IA, guardia) lo hace el Durable Object de la sesión.
//
// Nada de lo que llega se escribe en los registros: ni el texto, ni la IP, ni el `sid`, ni la ubicación.

import { CONFIG_POR_DEFECTO, ORIGENES_DE_LA_TIENDA_POR_DEFECTO, type Config } from "../config";
import type { Env } from "../env";
import { hmacHex } from "../seguridad";
import type { DepsRutas } from "../rutas";
import type { EntradaTienda, MotivoTienda, SalidaTienda } from "./motor";
import { llaveDeRed, llaveDeRed48, verificarPase } from "./pase";
import { validarPeticionTienda } from "./peticion";

export const RUTA_DEL_MENSAJE = "/tienda/v1/mensaje";
/** El cuerpo más grande que se lee: 500 letras de texto más el carrito y la página caben de sobra. */
const MAX_CUERPO = 16_384;
const PLAZO_CONFIG_CORS_MS = 1_500;

/** Lo que la ruta necesita de una sesión (el stub del Durable Object o un doble en las pruebas). */
export interface SesionTiendaApi {
  atender(e: EntradaTienda): Promise<SalidaTienda>;
}

export interface DepsRutaTienda {
  sesion?(sid: string): SesionTiendaApi;
}

/** Los orígenes permitidos: los de Odoo si llegan a tiempo; si no, los de fábrica (un preflight no espera a que Odoo despierte). */
async function origenesPermitidos(d: Pick<DepsRutas, "config">): Promise<readonly string[]> {
  let reloj: ReturnType<typeof setTimeout> | undefined;
  try {
    const cfg = await Promise.race([d.config(), new Promise<null>((r) => (reloj = setTimeout(() => r(null), PLAZO_CONFIG_CORS_MS)))]);
    return cfg && cfg !== CONFIG_POR_DEFECTO ? (cfg as Config).tienda.origenes : ORIGENES_DE_LA_TIENDA_POR_DEFECTO;
  } catch {
    return ORIGENES_DE_LA_TIENDA_POR_DEFECTO;
  } finally {
    clearTimeout(reloj);
  }
}

function cabecerasCors(origen: string): Record<string, string> {
  return {
    "access-control-allow-origin": origen,
    "access-control-allow-methods": "POST, OPTIONS",
    "access-control-allow-headers": "authorization, content-type",
    "access-control-expose-headers": "retry-after",
    "access-control-max-age": "600",
    vary: "Origin",
  };
}

function responder(cuerpo: unknown, status: number, origen: string | null, extra: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(cuerpo), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store", "x-content-type-options": "nosniff", ...(origen ? cabecerasCors(origen) : { vary: "Origin" }), ...extra },
  });
}

const error = (motivo: MotivoTienda, status: number, origen: string | null, extra: Record<string, string> = {}) => responder({ ok: false, motivo }, status, origen, extra);

export async function manejarTienda(ruta: string, req: Request, env: Env, d: Pick<DepsRutas, "config" | "ahora">, deps: DepsRutaTienda = {}): Promise<Response> {
  if (ruta !== RUTA_DEL_MENSAJE) return new Response("no encontrado", { status: 404 });
  const origen = req.headers.get("origin");
  const permitidos = await origenesPermitidos(d);
  // Solo desde la tienda: otro origen (o sin `Origin`) no recibe ni las cabeceras CORS.
  if (!origen || !permitidos.includes(origen.toLowerCase())) return new Response("origen no permitido", { status: 403, headers: { vary: "Origin", "cache-control": "no-store" } });
  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: { ...cabecerasCors(origen), "cache-control": "no-store" } });
  if (req.method !== "POST") return responder({ ok: false, motivo: "fallo" }, 405, origen, { allow: "POST, OPTIONS" });

  const verificado = await verificarPase(env.JUAN_WORKER_TOKEN, req.headers.get("authorization"), d.ahora());
  if (!verificado.ok) return error("pase", 401, origen);

  const largo = Number(req.headers.get("content-length") ?? 0);
  if (largo > MAX_CUERPO) return error("fallo", 400, origen);
  let cuerpo: unknown;
  try {
    const texto = await req.text();
    if (texto.length > MAX_CUERPO) return error("fallo", 400, origen);
    cuerpo = JSON.parse(texto);
  } catch {
    return error("fallo", 400, origen);
  }
  const peticion = validarPeticionTienda(cuerpo);
  if (typeof peticion === "string") return responder({ ok: false, motivo: "fallo", error: peticion }, 400, origen);

  const sesion = deps.sesion?.(verificado.pase.sid) ?? (env.TIENDA ? (env.TIENDA.get(env.TIENDA.idFromName(`tienda:${verificado.pase.sid}`)) as unknown as SesionTiendaApi) : null);
  if (!sesion) return error("fallo", 503, origen);
  try {
    // El tope por red: la IPv4 entera o la /64 de la IPv6 de la conexión (como el borde), guardada ofuscada (HMAC con el token del
    // Worker) y solo 26 horas.
    const ip = req.headers.get("cf-connecting-ip");
    const ofuscar = async (llave: string) => (await hmacHex(env.JUAN_WORKER_TOKEN ?? "", llave)).slice(0, 32);
    const red = await ofuscar(`brian-tienda-red:${llaveDeRed(ip)}`);
    // Con IPv6, también su /48 (el tope por /48); con IPv4, no hay.
    const llave48 = llaveDeRed48(ip);
    const red48 = llave48 ? await ofuscar(`brian-tienda-red48:${llave48}`) : null;
    const r = await sesion.atender({ peticion, red, red48 });
    return responder(r.cuerpo, r.status, origen, r.reintentarEn ? { "retry-after": String(r.reintentarEn) } : {});
  } catch (e) {
    console.error("[juan] tienda:", e instanceof Error ? e.message.slice(0, 200) : "error");
    return error("fallo", 502, origen);
  }
}
