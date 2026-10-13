// `POST /odoo/embeber`: la «huella de significado» de unos textos, para que la búsqueda en el conocimiento encuentre «¿instalan los
// muebles?» aunque la entrada diga «armado a domicilio» (docs/JUAN_ODOO.md → Búsqueda por significado).
//
// Odoo manda textos (títulos y contenido de las entradas del equipo, o la pregunta de un cliente) y este Worker devuelve un vector
// por texto. NO ENVÍA NADA, no consulta herramientas, no escribe en Odoo: es una lectura. Corre en Workers AI (`@cf/baai/bge-m3`,
// multilingüe, 1024 dimensiones) dentro de la cuenta de Cloudflare de D'CASA: los textos no salen de ahí.
//
//   · Es opcional: sin el binding `AI` contesta 503 con el NOMBRE que falta y Odoo sigue con la búsqueda por palabras.
//   · El costo es de centavos al mes (se cobra por token de entrada); no pasa por el tope de gasto de IA porque no es un modelo de texto.
//
// Entrada:  { textos: [string] }          (de 1 a 8 textos, cada uno de hasta 2000 letras)
// Salida:   { ok: true, vectores: [[número]], dimensiones, modelo }   o   { ok: false, error }

import type { Env } from "./env";
import { limpiarError } from "./motor/conversacion";
import { fallo, leerObjeto, respuesta } from "./odoo-panel-comun";
import type { DepsRutas } from "./rutas";

export const MODELO_DE_VECTORES = "@cf/baai/bge-m3";
export const DIMENSIONES = 1024;
const MAX_TEXTOS = 8;
const MAX_TEXTO = 2000;
/** Con 4 decimales el coseno cambia en el quinto: sobra, y cada vector viaja y se guarda en ~7 KB en vez de ~20. */
const DECIMALES = 4;

type Ia = NonNullable<Env["AI"]>;

/** Los textos validados, o el motivo (en español) por el que no sirven. */
export function validarTextos(c: Record<string, unknown>): string[] | string {
  if (!Array.isArray(c.textos) || c.textos.length === 0) return "faltan los textos";
  if (c.textos.length > MAX_TEXTOS) return `como máximo ${MAX_TEXTOS} textos por vez`;
  const textos: string[] = [];
  for (const t of c.textos) {
    if (typeof t !== "string") return "cada texto debe ser una cadena";
    const limpio = t.replace(/\s+/g, " ").trim();
    if (!limpio) return "hay un texto vacío";
    if (limpio.length > MAX_TEXTO) return `cada texto tiene como máximo ${MAX_TEXTO} letras`;
    textos.push(limpio);
  }
  return textos;
}

/** Lo que devuelve Workers AI, validado: un vector de `DIMENSIONES` números finitos por texto, o `null` si no es eso. */
export function vectoresDe(salida: unknown, cuantos: number): number[][] | null {
  const datos = (salida as { data?: unknown } | null)?.data;
  if (!Array.isArray(datos) || datos.length !== cuantos) return null;
  const factor = 10 ** DECIMALES;
  const vectores: number[][] = [];
  for (const v of datos) {
    if (!Array.isArray(v) || v.length !== DIMENSIONES || !v.every((n) => typeof n === "number" && Number.isFinite(n))) return null;
    vectores.push(v.map((n: number) => Math.round(n * factor) / factor));
  }
  return vectores;
}

export async function embeber(textos: string[], ai: Ia | undefined): Promise<{ status: number; cuerpo: Record<string, unknown> }> {
  if (!ai) return { status: 503, cuerpo: { ok: false, error: "Falta el binding AI en el Worker: la búsqueda por significado no está disponible.", faltan: ["AI"] } };
  let salida: unknown;
  try {
    salida = await ai.run(MODELO_DE_VECTORES, { text: textos });
  } catch (e) {
    console.warn(`[juan] embeber: Workers AI falló: ${limpiarError(e)}`);
    return { status: 502, cuerpo: { ok: false, error: "No pude calcular el significado ahora." } };
  }
  const vectores = vectoresDe(salida, textos.length);
  if (!vectores) return { status: 502, cuerpo: { ok: false, error: "Workers AI contestó algo que no es un vector." } };
  return { status: 200, cuerpo: { ok: true, vectores, dimensiones: DIMENSIONES, modelo: MODELO_DE_VECTORES } };
}

/** `POST /odoo/embeber`, con las dependencias de producción (o el `ai` que pase la prueba). */
export async function manejarEmbeber(req: Request, env: Env, _d: Pick<DepsRutas, "ahora">, ai: Ia | undefined = env.AI): Promise<Response> {
  if (req.method !== "POST") return fallo("método no permitido", 405);
  const cuerpo = await leerObjeto(req);
  if (cuerpo instanceof Response) return cuerpo;
  const textos = validarTextos(cuerpo);
  if (typeof textos === "string") return fallo(textos, 400);
  const r = await embeber(textos, ai);
  return respuesta(r.cuerpo, r.status);
}
