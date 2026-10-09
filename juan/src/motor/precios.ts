// Cuánto cuesta la IA. Se usa para el tope mensual: al llegar, el bot baja al modelo barato.
//
// Tarifas en dólares por millón de tokens, de la ronda 7 (docs/auditoria/ronda7/crm-whatsapp.md §5):
// Haiku 4.5 $1/$5 · Sonnet 5.5 $2/$10 · Opus 5.5 $4/$20. Lectura de caché ≈ 10 % de la entrada y
// escritura de caché (5 min) ≈ 125 % (tarifa publicada de Anthropic; REVISAR cuando cambien las tarifas).
// Un modelo desconocido se cobra como Sonnet: preferimos pasarnos que quedarnos cortos con el tope.

export interface Tarifa {
  entrada: number;
  salida: number;
  cacheLectura: number;
  cacheEscritura: number;
}

const tarifa = (entrada: number, salida: number): Tarifa => ({
  entrada,
  salida,
  cacheLectura: entrada * 0.1,
  cacheEscritura: entrada * 1.25,
});

export const TARIFAS: { patron: RegExp; tarifa: Tarifa }[] = [
  { patron: /haiku/i, tarifa: tarifa(1, 5) },
  { patron: /sonnet/i, tarifa: tarifa(2, 10) },
  { patron: /opus/i, tarifa: tarifa(4, 20) },
];

export const TARIFA_DESCONOCIDA: Tarifa = tarifa(2, 10);

export function tarifaDe(modelo: string): Tarifa {
  return TARIFAS.find((t) => t.patron.test(modelo))?.tarifa ?? TARIFA_DESCONOCIDA;
}

export interface Uso {
  /** Tokens de entrada que NO vinieron de la caché. */
  entrada: number;
  cacheLectura: number;
  cacheEscritura: number;
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

/** Costo en dólares. */
export function costoUsd(modelo: string, uso: Uso): number {
  const t = tarifaDe(modelo);
  return (
    (uso.entrada * t.entrada + uso.cacheLectura * t.cacheLectura + uso.cacheEscritura * t.cacheEscritura + uso.salida * t.salida) /
    1_000_000
  );
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
