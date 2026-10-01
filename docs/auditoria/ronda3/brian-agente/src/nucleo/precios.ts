import tabla from "../../data/precios.json";
import type { Uso } from "./tipos";

export interface Precio {
  entrada: number | null;
  cache_escritura: number | null;
  cache_lectura: number | null;
  salida: number | null;
  estado: string;
  fuente: string;
  consultado: string;
}

export interface TablaPrecios {
  version: string;
  modelos: Record<string, Precio>;
}

export const PRECIOS: TablaPrecios = tabla as TablaPrecios;

export class PrecioPendiente extends Error {}

/** Clave canónica «proveedor/modelo». */
export const clave = (proveedor: string, modelo: string) => `${proveedor}/${modelo}`;

export function precioConocido(t: TablaPrecios, proveedor: string, modelo: string): boolean {
  const p = t.modelos[clave(proveedor, modelo)];
  return !!p && [p.entrada, p.cache_escritura, p.cache_lectura, p.salida].every((v) => typeof v === "number");
}

/**
 * Costo en MICRODÓLARES (enteros, para sumar sin errores de coma flotante).
 * tokens × (USD/MTok) = microdólares exactos; se redondea hacia arriba una vez al final.
 */
export function costoMicro(t: TablaPrecios, proveedor: string, modelo: string, uso: Uso): number {
  const p = t.modelos[clave(proveedor, modelo)];
  if (!p || !precioConocido(t, proveedor, modelo)) {
    throw new PrecioPendiente(`Sin precio verificado para ${clave(proveedor, modelo)} (PENDIENTE en data/precios.json)`);
  }
  const bruto =
    uso.entrada * (p.entrada as number) +
    uso.cacheEscritura * (p.cache_escritura as number) +
    uso.cacheLectura * (p.cache_lectura as number) +
    uso.salida * (p.salida as number);
  return Math.ceil(bruto - 1e-9);
}

/** Cabecera `cf-aig-custom-cost` (USD por token) para que AI Gateway registre el costo de Meta. */
export function cabeceraCostoGateway(t: TablaPrecios, proveedor: string, modelo: string): string | undefined {
  const p = t.modelos[clave(proveedor, modelo)];
  if (!p || !precioConocido(t, proveedor, modelo)) return undefined;
  const porToken = (v: number | null) => (v as number) / 1_000_000;
  return JSON.stringify({
    per_token_in: porToken(p.entrada),
    per_token_out: porToken(p.salida),
    per_cache_read_token: porToken(p.cache_lectura),
    per_cache_write_token: porToken(p.cache_escritura),
  });
}
