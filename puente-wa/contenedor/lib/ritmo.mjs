// @ts-check
// Ritmo de envío conservador.
//
// El riesgo real del canal por QR es que WhatsApp bloquee el número (docs/JUAN.md,
// docs/auditoria/ronda7/crm-whatsapp.md §2.1). Lo que más delata a un bot no es
// lo que dice, sino CÓMO escribe: ráfagas, velocidad sobrehumana, muchos números
// nuevos, cero «escribiendo…». Este módulo decide los tiempos y los topes.
// Todo es puro: el reloj y el azar se inyectan, así que se prueba sin esperar.

/**
 * @typedef {{
 *   entreBurbujasMs: number, entreBurbujasAzarMs: number,
 *   pensarMinMs: number, pensarMaxMs: number,
 *   escribirMsPorCaracter: number, escribirMinMs: number, escribirMaxMs: number, escribirVariacion: number,
 *   prepararMedioMinMs: number, prepararMedioMaxMs: number,
 *   porMinuto: number, porDia: number, porDestinatarioHora: number, friosPorDia: number,
 *   esperaMaxPorMinutoS: number, colaMax: number, colaEsperaMaxMs: number,
 * }} Ritmo
 */

/**
 * Valores por defecto. Se pueden bajar o subir por variables del Worker, pero
 * `entreBurbujasMs` nunca baja de 1000 (contrato: «1 s entre burbujas»).
 */
export const RITMO_POR_DEFECTO = /** @type {Ritmo} */ (Object.freeze({
  /** Mínimo entre dos burbujas seguidas (contrato con Juan). */
  entreBurbujasMs: 1000,
  /** Se le suma una espera al azar de 0 a esto. */
  entreBurbujasAzarMs: 600,
  /** Pausa «de leer» antes de la primera burbuja de una respuesta: entre estos dos valores. */
  pensarMinMs: 800,
  pensarMaxMs: 2200,
  /** «Escribiendo…» proporcional al largo, con tope. */
  escribirMsPorCaracter: 35,
  escribirMinMs: 700,
  escribirMaxMs: 5000,
  /** Variación al azar del tiempo de escribir (±). */
  escribirVariacion: 0.25,
  /** Pausa corta antes de mandar una imagen o un documento. */
  prepararMedioMinMs: 900,
  prepararMedioMaxMs: 1800,
  /** Tope de burbujas (texto o medio) por minuto, por día y por destinatario/hora. */
  porMinuto: 10,
  porDia: 400,
  porDestinatarioHora: 30,
  /** Destinatarios a los que se les escribe sin que ellos hayan escrito antes, por día. */
  friosPorDia: 15,
  /** Si falta menos de esto para que quepa en el minuto, se espera en vez de rechazar. */
  esperaMaxPorMinutoS: 20,
  /** Cuántas peticiones de envío pueden esperar turno, y cuánto. */
  colaMax: 20,
  colaEsperaMaxMs: 90_000,
}));

const MIN_MS = 60_000;
const HORA_MS = 3_600_000;
const DIA_MS = 86_400_000;

/**
 * @param {unknown} valor
 * @param {number} porDefecto
 * @param {number} min
 * @param {number} max
 */
function numeroEnRango(valor, porDefecto, min, max) {
  if (valor === undefined || valor === null || valor === "") return porDefecto;
  const n = Number(valor);
  if (!Number.isFinite(n)) return porDefecto;
  return Math.min(max, Math.max(min, Math.round(n)));
}

/**
 * Lee el ritmo desde variables de entorno (todas texto). Valores raros caen al
 * defecto o se recortan al rango permitido; el mínimo entre burbujas es 1000 ms.
 *
 * @param {Record<string, unknown>} [env]
 * @returns {Ritmo}
 */
export function leerRitmo(env = {}) {
  const d = RITMO_POR_DEFECTO;
  return {
    ...d,
    porMinuto: numeroEnRango(env.LIMITE_POR_MINUTO, d.porMinuto, 1, 60),
    porDia: numeroEnRango(env.LIMITE_POR_DIA, d.porDia, 1, 5000),
    porDestinatarioHora: numeroEnRango(env.LIMITE_POR_DESTINATARIO_HORA, d.porDestinatarioHora, 1, 500),
    friosPorDia: numeroEnRango(env.LIMITE_FRIOS_DIA, d.friosPorDia, 0, 500),
    entreBurbujasMs: numeroEnRango(env.ENTRE_BURBUJAS_MS, d.entreBurbujasMs, 1000, 30_000),
  };
}

/**
 * Número al azar en [min, max], con `azar()` ∈ [0, 1).
 * @param {() => number} azar @param {number} min @param {number} max
 */
function entre(azar, min, max) {
  return Math.round(min + azar() * (max - min));
}

/**
 * Pausa antes de la primera burbuja: la persona «lee» antes de contestar.
 * @param {() => number} azar
 * @param {Ritmo} [cfg]
 */
export function pausaPensar(azar, cfg = RITMO_POR_DEFECTO) {
  return entre(azar, cfg.pensarMinMs, cfg.pensarMaxMs);
}

/**
 * Cuánto dura el «escribiendo…» de una burbuja: proporcional a lo que se
 * escribiría a mano, con tope, y con algo de variación para no ser metronómico.
 * @param {string} texto
 * @param {() => number} azar
 * @param {Ritmo} [cfg]
 */
export function tiempoEscribiendo(texto, azar, cfg = RITMO_POR_DEFECTO) {
  const base = String(texto ?? "").length * cfg.escribirMsPorCaracter;
  const variacion = 1 + (azar() * 2 - 1) * cfg.escribirVariacion;
  const ms = Math.round(base * variacion);
  return Math.min(cfg.escribirMaxMs, Math.max(cfg.escribirMinMs, ms));
}

/**
 * Pausa antes de mandar una imagen o un documento (subirlo «toma un momento»).
 * @param {() => number} azar
 * @param {Ritmo} [cfg]
 */
export function pausaMedio(azar, cfg = RITMO_POR_DEFECTO) {
  return entre(azar, cfg.prepararMedioMinMs, cfg.prepararMedioMaxMs);
}

/**
 * Espera entre dos burbujas seguidas: SIEMPRE al menos `entreBurbujasMs`
 * (1 s por contrato) más un poco al azar.
 * @param {() => number} azar
 * @param {Ritmo} [cfg]
 */
export function esperaEntreBurbujas(azar, cfg = RITMO_POR_DEFECTO) {
  const minimo = Math.max(1000, cfg.entreBurbujasMs);
  return minimo + Math.round(azar() * cfg.entreBurbujasAzarMs);
}

/**
 * @typedef {{ ts: number, para: string, frio: boolean }} Envio
 * @typedef {{ ok: true }
 *   | { ok: false, limite: "minuto" | "dia" | "destinatario" | "frios", reintentarEnS: number | null, detalle: string }} Cuota
 */

/**
 * Cuántos segundos faltan para que quepan `n` envíos más en una ventana.
 * Cada envío «caduca» al cumplir la ventana; hay que esperar a que caduquen los
 * más viejos hasta que `usados + n <= limite`.
 *
 * @param {number[]} marcas  Instantes (ms) de los envíos dentro de la ventana.
 * @param {number} ahora
 * @param {number} ventanaMs
 * @param {number} limite
 * @param {number} n
 * @returns {number | null}  null si nunca cabrá (n > limite).
 */
export function segundosParaQueQuepa(marcas, ahora, ventanaMs, limite, n) {
  if (n > limite) return null;
  const dentro = marcas.filter((t) => ahora - t < ventanaMs).sort((a, b) => a - b);
  const exceso = dentro.length + n - limite;
  if (exceso <= 0) return 0;
  const hasta = dentro[exceso - 1] + ventanaMs;
  return Math.max(1, Math.ceil((hasta - ahora) / 1000));
}

/**
 * ¿Se puede enviar `cantidad` burbujas a `para` ahora?
 *
 * Mira, en este orden: minuto (global), día (global), destinatario por hora y
 * destinatarios «fríos» por día (alguien que nunca nos escribió). Devuelve el
 * primer tope que se pasaría y en cuántos segundos volver a intentar.
 *
 * @param {{ ahora: number, para: string, esFrio: boolean, cantidad: number, envios: Envio[], cfg?: Ritmo }} p
 * @returns {Cuota}
 */
export function evaluarCuotas({ ahora, para, esFrio, cantidad, envios, cfg = RITMO_POR_DEFECTO }) {
  const n = Math.max(1, cantidad);

  const tsMin = envios.map((e) => e.ts);
  const espMin = segundosParaQueQuepa(tsMin, ahora, MIN_MS, cfg.porMinuto, n);
  if (espMin === null || espMin > 0) {
    return {
      ok: false,
      limite: "minuto",
      reintentarEnS: espMin,
      detalle: `tope de ${cfg.porMinuto} mensajes por minuto`,
    };
  }

  const espDia = segundosParaQueQuepa(tsMin, ahora, DIA_MS, cfg.porDia, n);
  if (espDia === null || espDia > 0) {
    return { ok: false, limite: "dia", reintentarEnS: espDia, detalle: `tope de ${cfg.porDia} mensajes por día` };
  }

  const tsPara = envios.filter((e) => e.para === para).map((e) => e.ts);
  const espPara = segundosParaQueQuepa(tsPara, ahora, HORA_MS, cfg.porDestinatarioHora, n);
  if (espPara === null || espPara > 0) {
    return {
      ok: false,
      limite: "destinatario",
      reintentarEnS: espPara,
      detalle: `tope de ${cfg.porDestinatarioHora} mensajes por hora a una misma persona`,
    };
  }

  if (esFrio) {
    // Un «frío» se cuenta una vez por destinatario y día, no por burbuja.
    const friosHoy = new Set(
      envios.filter((e) => e.frio && ahora - e.ts < DIA_MS && e.para !== para).map((e) => e.para),
    );
    const yaEraDeHoy = envios.some((e) => e.frio && e.para === para && ahora - e.ts < DIA_MS);
    if (!yaEraDeHoy && friosHoy.size + 1 > cfg.friosPorDia) {
      const masViejo = Math.min(
        ...envios.filter((e) => e.frio && ahora - e.ts < DIA_MS).map((e) => e.ts),
      );
      return {
        ok: false,
        limite: "frios",
        reintentarEnS: Number.isFinite(masViejo) ? Math.max(1, Math.ceil((masViejo + DIA_MS - ahora) / 1000)) : null,
        detalle: `tope de ${cfg.friosPorDia} personas nuevas por día (a quienes no nos han escrito antes)`,
      };
    }
  }

  return { ok: true };
}
