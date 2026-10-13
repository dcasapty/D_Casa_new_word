// Copia diaria de la sesión de WhatsApp.
//
// Dónde se guarda, en dos capas:
//
//   1. SIEMPRE dentro del Durable Object (tabla `wa_copias`): la última semana, ya
//      cifrada. Protege de una sesión corrupta o de un `creds` borrado por error. NO
//      protege de perder el Durable Object entero (por ejemplo, borrar el Worker).
//   2. OPCIONAL en R2, detrás de un interruptor APAGADO (`COPIA_R2` = «on» y el bucket
//      `COPIAS` enlazado en wrangler.jsonc): una copia fuera del Durable Object. Está
//      apagado porque crear el bucket es un recurso nuevo en Cloudflare y lo decide la
//      dueña. Los objetos de R2 NO se borran desde el código (regla del repositorio: R2
//      no se vacía a mano); la retención se pone con una regla de ciclo de vida del bucket.
//
// En las dos capas las copias son las MISMAS filas cifradas con `WA_SESION_CLAVE`: quien
// vea una copia no ve credenciales. Y sin esa clave (que NO está en el bucket ni en
// el Worker más que como secreto) la copia es inútil: guardar la clave aparte es parte
// del procedimiento (docs/JUAN_PUENTE.md).

import type { FilaCruda } from "./almacen";

/** Cada cuánto se saca una copia. */
export const COPIA_CADA_MS = 24 * 60 * 60 * 1000;
/** Margen para que la hora no se corra un poco cada día. */
const MARGEN_MS = 10 * 60 * 1000;

export interface ArchivoDeCopia {
  version: 1;
  copia: string;
  creada: string;
  /** Filas CIFRADAS (nunca en claro). */
  filas: FilaCruda[];
}

/**
 * ¿Toca sacar la copia diaria? Solo si hay sesión (credenciales), el canal está
 * conectado ahora mismo (no se copia una sesión rota encima de una buena) y pasó un
 * día desde la última — o todavía no hay ninguna (la primera, nada más vincular).
 */
export function debeCopiar(i: {
  ultimaCopiaEn: number | null;
  hayCreds: boolean;
  conectado: boolean;
  ahora: number;
}): boolean {
  if (!i.hayCreds || !i.conectado) return false;
  if (i.ultimaCopiaEn === null) return true;
  return i.ahora - i.ultimaCopiaEn >= COPIA_CADA_MS - MARGEN_MS;
}

/** La clave del objeto en R2: `sesion/2026-10-09T03-17-00Z.json`. */
export function claveR2(copia: string): string {
  return `sesion/${copia}.json`;
}

export function armarArchivo(copia: string, creada: string, filas: FilaCruda[]): ArchivoDeCopia {
  return { version: 1, copia, creada, filas };
}

/** Lee un archivo de copia (de R2 o pegado a mano) con comprobaciones de forma. */
export function leerArchivo(texto: string): ArchivoDeCopia {
  let datos: unknown;
  try {
    datos = JSON.parse(texto);
  } catch {
    throw new Error("El archivo de copia no es JSON.");
  }
  const a = datos as Partial<ArchivoDeCopia> | null;
  if (!a || a.version !== 1 || !Array.isArray(a.filas) || typeof a.copia !== "string") {
    throw new Error("El archivo de copia no tiene el formato esperado (versión 1).");
  }
  for (const f of a.filas) {
    if (!f || typeof f.clave !== "string" || typeof f.valor !== "string" || typeof f.actualizado_en !== "number") {
      throw new Error("El archivo de copia trae filas mal formadas.");
    }
    if (!f.valor.startsWith("v1.")) throw new Error(`La fila «${f.clave}» no está cifrada: no se acepta una copia en claro.`);
  }
  return a as ArchivoDeCopia;
}

/**
 * Sube la copia a R2 si el interruptor está en «on» y el bucket está enlazado.
 * Nunca lanza: devuelve el motivo para dejarlo en el diario.
 */
export async function subirCopiaR2(
  env: { COPIA_R2?: string; COPIAS?: R2Bucket },
  archivo: ArchivoDeCopia,
): Promise<{ subida: boolean; motivo: string }> {
  if (env.COPIA_R2 !== "on") return { subida: false, motivo: "interruptor COPIA_R2 apagado" };
  if (!env.COPIAS) return { subida: false, motivo: "COPIA_R2 está en «on» pero falta enlazar el bucket COPIAS" };
  try {
    await env.COPIAS.put(claveR2(archivo.copia), JSON.stringify(archivo), {
      httpMetadata: { contentType: "application/json" },
      customMetadata: { filas: String(archivo.filas.length), version: "1" },
    });
    return { subida: true, motivo: `subida a R2 como ${claveR2(archivo.copia)}` };
  } catch (e) {
    return { subida: false, motivo: `R2 falló: ${e instanceof Error ? e.message : String(e)}` };
  }
}
