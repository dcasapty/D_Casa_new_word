// Cuánto cuesta la IA. Se usa para el tope mensual: al llegar, el bot baja al modelo barato.
//
// Los precios son DATOS, no código: la tabla de Odoo (`precios_ia`, dólares por millón de tokens) manda sobre la integrada.
// La integrada solo trae Claude, con las tarifas de la ronda 7 (docs/auditoria/ronda7/crm-whatsapp.md §5): Haiku 4.5 $1/$5,
// Sonnet 5.5 $2/$10, Opus 5.5 $4/$20; lectura de caché ≈ 10 % de la entrada y escritura (5 min) ≈ 125 %. REVISAR cuando cambien.
//
// El precio de Meta (Muse Spark) NO está verificado en la página oficial, así que NO viene integrado: la dueña lo carga en Odoo.
// Un modelo sin precio cargado jamás cuenta como gratis: se estima con una tarifa de RESERVA (la de Sonnet, deliberadamente
// alta para que el tope proteja) y se marca como «estimado» para avisar en /salud.

import type { PrecioModelo } from "../config";

export interface Tarifa {
  entrada: number;
  salida: number;
  cacheLectura: number;
  cacheEscritura: number;
}

const tarifa = (entrada: number, salida: number, cacheLectura = entrada * 0.1, cacheEscritura = entrada * 1.25): Tarifa => ({
  entrada,
  salida,
  cacheLectura,
  cacheEscritura,
});

/** Claude, por familia. Nada más: lo demás lo carga la dueña. */
export const TARIFAS_INTEGRADAS: { patron: RegExp; tarifa: Tarifa }[] = [
  { patron: /^claude-.*haiku/i, tarifa: tarifa(1, 5) },
  { patron: /^claude-.*sonnet/i, tarifa: tarifa(2, 10) },
  { patron: /^claude-.*opus/i, tarifa: tarifa(4, 20) },
];

/** Para un modelo sin precio cargado: la de Sonnet. Mejor pasarse que quedarse corto con el tope. */
export const TARIFA_DE_RESERVA: Tarifa = tarifa(2, 10);

export type TablaDePrecios = Record<string, PrecioModelo>;

export interface PrecioResuelto {
  tarifa: Tarifa;
  /** false = no había precio para este modelo: se usó la tarifa de reserva. */
  conPrecio: boolean;
}

export function precioDe(modelo: string, tabla: TablaDePrecios = {}): PrecioResuelto {
  const p = tabla[modelo];
  if (p) {
    return {
      conPrecio: true,
      tarifa: tarifa(p.entrada, p.salida, p.entrada_cache ?? p.entrada * 0.1, p.escritura_cache ?? p.entrada * 1.25),
    };
  }
  const integrada = TARIFAS_INTEGRADAS.find((t) => t.patron.test(modelo));
  if (integrada) return { tarifa: integrada.tarifa, conPrecio: true };
  return { tarifa: TARIFA_DE_RESERVA, conPrecio: false };
}

export function tarifaDe(modelo: string, tabla?: TablaDePrecios): Tarifa {
  return precioDe(modelo, tabla).tarifa;
}

export interface Uso {
  /** Tokens de entrada que NO vinieron de la caché. */
  entrada: number;
  cacheLectura: number;
  cacheEscritura: number;
  /** Incluye los tokens de razonamiento (Muse Spark siempre razona y se cobran como salida). */
  salida: number;
}

export const USO_VACIO: Uso = { entrada: 0, cacheLectura: 0, cacheEscritura: 0, salida: 0 };

export function sumarUso(a: Uso, b: Uso): Uso {
  return {
    entrada: a.entrada + b.entrada,
    cacheLectura: a.cacheLectura + b.cacheLectura,
    cacheEscritura: a.cacheEscritura + b.cacheEscritura,
    salida: a.salida + b.salida,
  };
}

export interface Costo {
  usd: number;
  /** true = sin precio cargado: el costo es una estimación con la tarifa de reserva. */
  estimado: boolean;
}

export function costoDe(modelo: string, uso: Uso, tabla?: TablaDePrecios): Costo {
  const { tarifa: t, conPrecio } = precioDe(modelo, tabla);
  const usd = (uso.entrada * t.entrada + uso.cacheLectura * t.cacheLectura + uso.cacheEscritura * t.cacheEscritura + uso.salida * t.salida) / 1_000_000;
  return { usd, estimado: !conPrecio };
}

/** Solo el número (para las pruebas y los casos en que no importa el aviso). */
export function costoUsd(modelo: string, uso: Uso, tabla?: TablaDePrecios): number {
  return costoDe(modelo, uso, tabla).usd;
}

/** Lo que reporta el SDK de IA (`totalUsage`), llevado a nuestras cuatro cuentas. */
export function usoDelSdk(u: {
  inputTokens?: number | undefined;
  outputTokens?: number | undefined;
  inputTokenDetails?: { noCacheTokens?: number | undefined; cacheReadTokens?: number | undefined; cacheWriteTokens?: number | undefined };
}): Uso {
  const lectura = u.inputTokenDetails?.cacheReadTokens ?? 0;
  const escritura = u.inputTokenDetails?.cacheWriteTokens ?? 0;
  const sinCache = u.inputTokenDetails?.noCacheTokens ?? Math.max(0, (u.inputTokens ?? 0) - lectura - escritura);
  return { entrada: sinCache, cacheLectura: lectura, cacheEscritura: escritura, salida: u.outputTokens ?? 0 };
}

export type Nivel = "rapido" | "inteligente";

/**
 * Tope mensual: al llegar, SIEMPRE el modelo barato. Nunca se calla por dinero (regla 8).
 * Sin tope (≤ 0) no hay límite.
 */
export function aplicarTope(nivel: Nivel, gastoMesUsd: number, topeUsd: number): { nivel: Nivel; bajo: boolean } {
  if (topeUsd > 0 && gastoMesUsd >= topeUsd && nivel !== "rapido") return { nivel: "rapido", bajo: true };
  return { nivel, bajo: false };
}
