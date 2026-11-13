// `POST /odoo/buscar-foto`: «Busca con una foto» de la tienda web (addons/dcasa_buscar_foto, docs/CATALOGO.md).
//
// Un visitante de la tienda sube la foto de un mueble; Odoo la valida y la manda aquí UNA vez. Este Worker la lee con EL MISMO
// lector de imágenes que usa Juan en las conversaciones (motor/vision.ts: solo se importa, no se cambia) y devuelve SOLO el
// registro cerrado: tipo, códigos, categoría, medida, ¿parece pago?, ¿parece identidad? Ningún texto libre de la imagen sale de
// aquí, y Odoo decide con eso qué productos publicados se parecen.
//
//   · La foto NO se guarda: ni en un Durable Object, ni en R2, ni en un registro (log). Se lee y se olvida. Lo único que se anota
//     es el gasto (modelo y tokens, números) en el Durable Object `Global`, como cualquier otro uso de IA.
//   · Cuenta para el tope de IA del mes (`presupuesto_ia_mensual_usd`): con el tope alcanzado no se lee (causa «tope») y la
//     tienda dice «Ahora no podemos buscar por foto». Juan sigue contestando con el modelo económico, como siempre.
//   · Contesta siempre antes de PLAZO_BUSCAR_FOTO_MS; Odoo espera más que eso (TIMEOUT_BUSCAR_FOTO en
//     addons/dcasa_buscar_foto/models/buscar_foto.py; una prueba lo exige).
//
// Entrada:  { mime: "image/jpeg" | "image/png" | "image/webp", base64 }    (la foto ya achicada por el navegador)
// Salida:   { ok: true, lectura: { tipo, codigos, categoria, medida, parece_pago, parece_identidad } | null }
//           { ok: false, causa: "tope" | "no_disponible" | "tardo", error }       (null = el lector no pudo leerla)

import { diaDelNegocio, mesDelNegocio, type Config } from "./config";
import type { Env } from "./env";
import { costoDe, type Uso } from "./motor/precios";
import { lectorDeImagenes, MODELO_VISION_POR_DEFECTO, type LecturaImagen } from "./motor/vision";
import { fallo, leerObjeto, respuesta } from "./odoo-panel-comun";
import type { GastoApi } from "./odoo-panel-sugerir";
import type { DepsRutas } from "./rutas";

/** El mismo tope que el lector de imágenes (motor/vision.ts): una foto achicada por el navegador pesa cientos de KB. */
export const MAX_BYTES_FOTO = 4 * 1024 * 1024;
/** El cuerpo entero (la foto en base64 pesa 4/3 más), para no leer de más ni un byte. */
export const MAX_CUERPO = Math.ceil((MAX_BYTES_FOTO * 4) / 3) + 4096;
/** Odoo espera TIMEOUT_BUSCAR_FOTO (30 s): el Worker contesta antes, con la lectura o con «tardo». */
export const PLAZO_BUSCAR_FOTO_MS = 25_000;
/**
 * Si Workers AI no dice cuántos tokens usó, se anota una estimación ALTA (una foto de 1024 px son unos cientos o pocos miles de
 * tokens): mejor pasarse que quedarse corto con el tope del mes. Es una salvaguarda, no un precio.
 */
export const USO_ESTIMADO: Uso = { entrada: 3000, cacheLectura: 0, cacheEscritura: 0, salida: 200 };

export const TIPOS_DE_FOTO = { "image/jpeg": "jpeg", "image/png": "png", "image/webp": "webp" } as const;
export type MimeDeFoto = keyof typeof TIPOS_DE_FOTO;
export type CausaBuscarFoto = "tope" | "no_disponible" | "tardo";

export interface PeticionBuscarFoto {
  mime: MimeDeFoto;
  bytes: Uint8Array;
}

/** Los bytes dicen lo mismo que el tipo: JPEG (FF D8 FF), PNG (firma de 8 bytes) o WebP (RIFF….WEBP). */
export function firmaCoincide(bytes: Uint8Array, mime: MimeDeFoto): boolean {
  const empieza = (...b: number[]) => b.every((v, i) => bytes[i] === v);
  if (mime === "image/jpeg") return bytes.length > 3 && empieza(0xff, 0xd8, 0xff);
  if (mime === "image/png") return bytes.length > 8 && empieza(0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a);
  return bytes.length > 12 && empieza(0x52, 0x49, 0x46, 0x46) && String.fromCharCode(...bytes.subarray(8, 12)) === "WEBP";
}

/** La petición validada, o `[status, motivo]` (en español) si no sirve. Nunca repite la foto en el motivo. */
export function validarPeticion(c: Record<string, unknown>): PeticionBuscarFoto | [number, string] {
  const mime = typeof c.mime === "string" ? c.mime.trim().toLowerCase() : "";
  if (!(mime in TIPOS_DE_FOTO)) return [400, "la foto tiene que ser JPEG, PNG o WebP"];
  if (typeof c.base64 !== "string" || !c.base64) return [400, "falta la foto"];
  if (c.base64.length > MAX_CUERPO) return [413, "la foto pesa demasiado"];
  if (!/^[A-Za-z0-9+/]+={0,2}$/.test(c.base64) || c.base64.length % 4 !== 0) return [400, "la foto no viene en base64"];
  let binario: string;
  try {
    binario = atob(c.base64);
  } catch {
    return [400, "la foto no viene en base64"];
  }
  if (binario.length === 0) return [400, "falta la foto"];
  if (binario.length > MAX_BYTES_FOTO) return [413, "la foto pesa demasiado"];
  const bytes = new Uint8Array(binario.length);
  for (let i = 0; i < binario.length; i++) bytes[i] = binario.charCodeAt(i);
  if (!firmaCoincide(bytes, mime as MimeDeFoto)) return [400, "el archivo no es la imagen que dice ser"];
  return { mime: mime as MimeDeFoto, bytes };
}

/** SOLO los seis campos del registro cerrado, copiados uno por uno (aunque el lector algún día devolviera más). */
export function registroCerrado(l: LecturaImagen | null): LecturaImagen | null {
  if (!l) return null;
  return {
    tipo: l.tipo,
    codigos: [...l.codigos],
    categoria: l.categoria,
    medida: l.medida,
    parece_pago: l.parece_pago === true,
    parece_identidad: l.parece_identidad === true,
  };
}

/** Lo que Workers AI cuenta del uso de un modelo de chat (`usage`), si lo dice. */
function usoDeLaRespuesta(r: unknown): Uso | null {
  const u = (r as { usage?: Record<string, unknown> } | null)?.usage;
  if (!u || typeof u !== "object") return null;
  const entrada = Number(u.prompt_tokens ?? u.input_tokens);
  const salida = Number(u.completion_tokens ?? u.output_tokens);
  if (!Number.isFinite(entrada) || !Number.isFinite(salida) || entrada < 0 || salida < 0) return null;
  return { entrada, cacheLectura: 0, cacheEscritura: 0, salida };
}

/** Un error para el registro, sin nada que se parezca a la foto (un pedazo largo de base64 se tapa). */
function errorSinFoto(e: unknown): string {
  const texto = e instanceof Error ? e.message : String(e);
  return texto.replace(/[A-Za-z0-9+/=]{60,}/g, "[…]").slice(0, 200);
}

export interface DepsBuscarFoto {
  config(): Promise<Config>;
  ahora(): number;
  gasto: GastoApi;
  /** Para las pruebas: un plazo corto. */
  plazoMs?: number;
}

type Resultado = { status: number; cuerpo: Record<string, unknown> };
const noPuede = (status: number, causa: CausaBuscarFoto, error: string): Resultado => ({ status, cuerpo: { ok: false, causa, error } });

export async function buscarFoto(p: PeticionBuscarFoto, env: Env, d: DepsBuscarFoto): Promise<Resultado> {
  const cfg = await d.config();
  const ahora = d.ahora();
  const mes = mesDelNegocio(cfg.horario.zona, ahora);
  const tope = cfg.presupuesto_ia_mensual_usd;
  if (tope > 0 && (await d.gasto.gastoMes(mes)) >= tope) {
    return noPuede(429, "tope", "Se llegó al tope de IA del mes: la búsqueda por foto vuelve el mes que viene o al subir el tope.");
  }

  // El lector de Juan, con el binding envuelto solo para contar los tokens (la foto no se toca ni se guarda aquí).
  const usos: Uso[] = [];
  let llamadas = 0;
  const ai = env.AI;
  const envContado: Env = ai
    ? {
        ...env,
        AI: {
          run: async (modelo: string, entrada: unknown) => {
            llamadas++;
            const r = await ai.run(modelo, entrada);
            const uso = usoDeLaRespuesta(r);
            if (uso) usos.push(uso);
            return r;
          },
        },
      }
    : env;
  const lector = lectorDeImagenes(envContado);
  if (!lector) return noPuede(503, "no_disponible", "La lectura de imágenes está apagada en el Worker (RECONOCER_IMAGENES y el binding AI).");

  const modelo = env.MODELO_VISION || MODELO_VISION_POR_DEFECTO;
  const anotarGasto = async () => {
    if (llamadas === 0) return;
    // Por cada llamada sin `usage`, la estimación alta.
    const uso = usos.reduce<Uso>(
      (a, u) => ({ entrada: a.entrada + u.entrada, cacheLectura: 0, cacheEscritura: 0, salida: a.salida + u.salida }),
      { entrada: 0, cacheLectura: 0, cacheEscritura: 0, salida: 0 },
    );
    for (let i = usos.length; i < llamadas; i++) {
      uso.entrada += USO_ESTIMADO.entrada;
      uso.salida += USO_ESTIMADO.salida;
    }
    const costo = costoDe(modelo, uso, cfg.precios_ia);
    await d.gasto
      .registrarGasto(mes, modelo, uso, costo.usd, costo.estimado, diaDelNegocio(cfg.horario.zona, ahora))
      .catch((e) => console.warn("[juan] buscar-foto: no se pudo anotar el gasto:", errorSinFoto(e)));
  };

  let reloj: ReturnType<typeof setTimeout> | undefined;
  const plazo = new Promise<"tardo">((res) => (reloj = setTimeout(() => res("tardo"), d.plazoMs ?? PLAZO_BUSCAR_FOTO_MS)));
  let lectura: LecturaImagen | null;
  try {
    const r = await Promise.race([lector(p.bytes, p.mime), plazo]);
    if (r === "tardo") {
      // La llamada pudo seguir corriendo (y cobrarse): se anota con la estimación.
      llamadas = Math.max(llamadas, 1);
      await anotarGasto();
      return noPuede(504, "tardo", "La lectura de la foto tardó demasiado.");
    }
    lectura = r;
  } catch (e) {
    console.warn(`[juan] buscar-foto: el lector de imágenes falló: ${errorSinFoto(e)}`);
    await anotarGasto();
    const tardo = e instanceof Error && /tard[oó] demasiado/.test(e.message);
    return tardo ? noPuede(504, "tardo", "La lectura de la foto tardó demasiado.") : noPuede(502, "no_disponible", "No pude leer la foto ahora.");
  } finally {
    clearTimeout(reloj);
  }
  await anotarGasto();
  return { status: 200, cuerpo: { ok: true, lectura: registroCerrado(lectura) } };
}

/** `POST /odoo/buscar-foto`, con las dependencias de producción (o las que pase la prueba). */
export async function manejarBuscarFoto(req: Request, env: Env, d: Pick<DepsRutas, "ahora" | "config" | "gastoMes">, deps?: DepsBuscarFoto): Promise<Response> {
  if (req.method !== "POST") return fallo("método no permitido", 405);
  const largo = Number(req.headers.get("content-length") ?? "0");
  if (Number.isFinite(largo) && largo > MAX_CUERPO) return fallo("la foto pesa demasiado", 413);
  const cuerpo = await leerObjeto(req);
  if (cuerpo instanceof Response) return cuerpo;
  const peticion = validarPeticion(cuerpo);
  if (Array.isArray(peticion)) return fallo(peticion[1], peticion[0]);
  try {
    const global = () => env.GLOBAL.get(env.GLOBAL.idFromName("juan"));
    const r = await buscarFoto(
      peticion,
      env,
      deps ?? {
        config: d.config,
        ahora: d.ahora,
        gasto: {
          gastoMes: d.gastoMes,
          registrarGasto: async (mes, modelo, uso, usd, estimado, dia) => global().registrarGasto(mes, modelo, uso, usd, estimado, dia),
        },
      },
    );
    return respuesta(r.cuerpo, r.status);
  } catch (e) {
    console.error("[juan] /odoo/buscar-foto:", errorSinFoto(e));
    return fallo("No pude buscar con la foto ahora.", 502, { causa: "no_disponible" });
  }
}
