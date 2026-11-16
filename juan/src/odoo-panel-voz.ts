// `POST /odoo/voz`: las notas de voz de Brian del panel (addons/dcasa_brian, docs/BRIAN.md › «Notas de voz»).
//
// Una persona del equipo graba una indicación en el panel de Odoo; Odoo comprueba que es un usuario interno y manda el audio aquí UNA
// vez, con `Authorization: Bearer <JUAN_WORKER_TOKEN>` (rutas.ts ya lo comprobó en tiempo constante). Este Worker lo pasa a texto con
// Whisper (motor/voz.ts) y devuelve SOLO el texto: Odoo lo pone en la caja de Brian para que la persona lo revise y lo mande.
//
//   · El audio no se guarda en ningún lado (ni aquí ni en Odoo), no se devuelve y no se usa para generar voz. Se borra de la memoria.
//   · Topes: TOPE_POR_USUARIO_HORA notas por hora por usuario y TOPE_POR_DIA en el día entre todos (contados en `Global`, con el
//     usuario ofuscado), y lo de las notas en el mes no pasa de `tope_mes_usd` (lo puede mandar Odoo; si no, TOPE_MES_USD).
//   · El gasto va en «Costos de IA» en su propio renglón de Cloudflare, CONCEPTO_DEL_GASTO («Cloudflare: notas de voz del panel»):
//     no suma en el gasto de Juan, ni en su tope, ni en «Por pagar a Meta» (motor/global.ts, `esDeCloudflare`).
//
// Entrada:  { mime: "audio/webm" | "audio/ogg" | "audio/mp4" (con `;codecs=…` si se quiere), base64, usuario, duracion_ms?, tope_mes_usd? }
// Salida:   { ok: true, texto, recortado }
//           { ok: false, causa, error }: no_disponible 503 · tipo 415 · audio 400 · muy_pesada 413 · muy_larga 413 · tope_usuario 429
//           · tope_dia 429 · tope_mes 429 · no_se_entendio 422 · tardo 504 · fallo 502. `error` nunca repite el audio.

import { diaDelNegocio, mesDelNegocio, type Config } from "./config";
import type { Env } from "./env";
import type { ReservaVozPanel, ResultadoReservaVozPanel } from "./motor/global";
import { USO_VACIO, type Uso } from "./motor/precios";
import { whisperDe } from "./motor/transcribir";
import { duracionDeclarada, esProblema, MAX_BYTES_VOZ, tipoDeAudio, transcribirNota, validarNota, type ResultadoNota } from "./motor/voz";
import { fallo, leerObjeto, respuesta } from "./odoo-panel-comun";
import type { DepsRutas } from "./rutas";
import { hmacHex } from "./seguridad";

/** Cómo se anota el gasto en `Global` (aparte de Juan: lo cobra Cloudflare). Odoo lo nombra «Cloudflare: notas de voz del panel». */
export const CONCEPTO_DEL_GASTO = "cloudflare:notas-de-voz-del-panel";
/** Notas por hora por usuario: una cada dos minutos, de sobra para dictarle a Brian. */
export const TOPE_POR_USUARIO_HORA = 30;
/** Notas por día entre todo el equipo. */
export const TOPE_POR_DIA = 500;
/** Techo del mes si Odoo no manda el suyo (USD): como «Busca con una foto». A US$0.0005 el minuto son 10 000 minutos. */
export const TOPE_MES_USD = 5;
export const MAX_TOPE_MES_USD = 1000;
/** Las letras que se devuelven: un minuto hablado son unas 1000; la caja de Brian acepta más. */
export const MAX_LETRAS_PANEL = 2000;
/** El cuerpo entero (el audio en base64 pesa 4/3 más), para no leer de más. */
export const MAX_CUERPO = Math.ceil((MAX_BYTES_VOZ * 4) / 3) + 4096;

export interface DepsVozPanel {
  config(): Promise<Config>;
  ahora(): number;
  reservar(p: ReservaVozPanel): Promise<ResultadoReservaVozPanel>;
  registrarGasto(mes: string, modelo: string, uso: Uso, usd: number, estimado: boolean): Promise<void>;
  /** Para las pruebas: un plazo corto para Whisper. */
  plazoMs?: number;
}

type Resultado = { status: number; cuerpo: Record<string, unknown> };
const noPuede = (status: number, causa: string, error: string): Resultado => ({ status, cuerpo: { ok: false, causa, error } });

const TEXTOS: Record<string, [number, string]> = {
  no_disponible: [503, "Las notas de voz están apagadas en el Worker (TRANSCRIBIR_AUDIO y el binding AI)."],
  tipo: [415, "La nota tiene que ser WebM, Ogg o MP4 (lo que graba el navegador)."],
  audio: [400, "El archivo no es una nota de voz que se pueda leer."],
  muy_pesada: [413, "La nota pesa demasiado."],
  muy_larga: [413, "La nota pasa de un minuto."],
  no_se_entendio: [422, "No se entendió lo que se dijo en la nota."],
  tardo: [504, "La nota tardó demasiado en pasarse a texto."],
  fallo: [502, "No pude pasar la nota a texto ahora."],
  tope_usuario: [429, "Llegaste al tope de notas de voz por hora."],
  tope_dia: [429, "El equipo llegó al tope de notas de voz del día."],
  tope_mes: [429, "Las notas de voz del panel llegaron a su tope del mes."],
};
const conCausa = (causa: string): Resultado => {
  const [status, texto] = TEXTOS[causa] ?? TEXTOS.fallo;
  return noPuede(status, causa, texto);
};

/** La nota del panel ya validada como objeto (el audio todavía en base64). */
export async function transcribirDelPanel(c: Record<string, unknown>, env: Env, d: DepsVozPanel): Promise<Resultado> {
  // Lo barato primero.
  const tipo = tipoDeAudio(typeof c.mime === "string" ? c.mime : null);
  if (!tipo) return conCausa("tipo");
  const usuario = typeof c.usuario === "number" || typeof c.usuario === "string" ? String(c.usuario).trim() : "";
  if (!/^[\w.:-]{1,64}$/.test(usuario)) return noPuede(400, "audio", "falta el usuario de Odoo");
  let topeMesUsd = TOPE_MES_USD;
  if (c.tope_mes_usd !== undefined && c.tope_mes_usd !== null) {
    if (typeof c.tope_mes_usd !== "number" || !Number.isFinite(c.tope_mes_usd) || c.tope_mes_usd < 0 || c.tope_mes_usd > MAX_TOPE_MES_USD) {
      return noPuede(400, "audio", `tope_mes_usd va de 0 a ${MAX_TOPE_MES_USD}`);
    }
    topeMesUsd = c.tope_mes_usd;
  }
  if (!whisperDe(env)) return conCausa("no_disponible");
  if (typeof c.base64 !== "string" || !c.base64) return conCausa("audio");
  if (c.base64.length > MAX_CUERPO) return conCausa("muy_pesada");
  if (!/^[A-Za-z0-9+/]+={0,2}$/.test(c.base64) || c.base64.length % 4 !== 0) return conCausa("audio");
  let binario: string;
  try {
    binario = atob(c.base64);
  } catch {
    return conCausa("audio");
  }
  if (binario.length > MAX_BYTES_VOZ) return conCausa("muy_pesada");
  const bytes = new Uint8Array(binario.length);
  for (let i = 0; i < binario.length; i++) bytes[i] = binario.charCodeAt(i);
  binario = "";
  const nota = validarNota(bytes, tipo, duracionDeclarada(c.duracion_ms));
  if (esProblema(nota)) {
    bytes.fill(0);
    return conCausa(nota.motivo);
  }

  const cfg = await d.config();
  const ahora = d.ahora();
  const mes = mesDelNegocio(cfg.horario.zona, ahora);
  let reserva: ResultadoReservaVozPanel;
  try {
    reserva = await d.reservar({
      usuario: (await hmacHex(env.JUAN_WORKER_TOKEN ?? "", `brian-panel-voz:${usuario}`)).slice(0, 32),
      dia: diaDelNegocio(cfg.horario.zona, ahora),
      mes,
      porUsuarioHora: TOPE_POR_USUARIO_HORA,
      porDia: TOPE_POR_DIA,
      topeMesUsd,
      concepto: CONCEPTO_DEL_GASTO,
    });
  } catch {
    nota.bytes.fill(0);
    return conCausa("fallo");
  }
  if (!reserva.ok) {
    nota.bytes.fill(0);
    const r = conCausa(reserva.motivo);
    if (reserva.reintentarEn) r.cuerpo.reintentar_en = reserva.reintentarEn;
    return r;
  }
  const r: ResultadoNota = await transcribirNota(env, nota, { maxLetras: MAX_LETRAS_PANEL, plazoMs: d.plazoMs });
  if (r.usd > 0) {
    // Sin día: lo de Cloudflare no entra en la gráfica por día (es la de Meta) y va en su propio renglón.
    await d.registrarGasto(mes, CONCEPTO_DEL_GASTO, USO_VACIO, r.usd, r.estimado).catch(() => console.warn("[juan] voz del panel: no se pudo anotar el gasto"));
  }
  if (!r.ok) return conCausa(r.motivo);
  return { status: 200, cuerpo: { ok: true, texto: r.texto, recortado: r.recortado } };
}

/** `POST /odoo/voz`, con las dependencias de producción (o las que pase la prueba). */
export async function manejarVozPanel(req: Request, env: Env, d: Pick<DepsRutas, "ahora" | "config">, deps?: DepsVozPanel): Promise<Response> {
  if (req.method !== "POST") return fallo("método no permitido", 405);
  const largo = Number(req.headers.get("content-length") ?? "0");
  if (Number.isFinite(largo) && largo > MAX_CUERPO) return fallo(TEXTOS.muy_pesada[1], 413, { causa: "muy_pesada" });
  const t0 = Date.now();
  const cuerpo = await leerObjeto(req);
  if (cuerpo instanceof Response) return cuerpo;
  try {
    const global = () => env.GLOBAL.get(env.GLOBAL.idFromName("juan"));
    const r = await transcribirDelPanel(
      cuerpo,
      env,
      deps ?? {
        config: d.config,
        ahora: d.ahora,
        reservar: async (p) => global().reservarVozPanel(p),
        registrarGasto: async (mes, modelo, uso, usd, estimado) => global().registrarGasto(mes, modelo, uso, usd, estimado),
      },
    );
    // Una línea por nota: el resultado y el tiempo. Nunca el audio, el texto ni el usuario.
    console.log(`[juan] voz del panel: ${JSON.stringify({ resultado: r.cuerpo.ok ? "ok" : r.cuerpo.causa, ms: Date.now() - t0 })}`);
    return respuesta(r.cuerpo, r.status);
  } catch (e) {
    console.error("[juan] /odoo/voz:", e instanceof Error ? e.name : "error");
    return fallo(TEXTOS.fallo[1], 502, { causa: "fallo" });
  } finally {
    cuerpo.base64 = undefined;
  }
}
