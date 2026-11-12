// Lo que sale hacia el cliente se revisa SIEMPRE, por código, antes de enviarse. El prompt pide
// bien; esto garantiza lo mínimo aunque el modelo se equivoque o el cliente intente manipularlo
// (docs/JUAN.md, reglas 2, 3, 6 y 11):
//
//   · nunca un precio sin «+ ITBMS»                    → se corrige solo
//   · nunca una cifra de dinero que no salió de una herramienta
//   · nunca un número de existencias
//   · nunca prometer entrega, flete, financiamiento, apartado ni descuento (el costo del envío y un «envío gratis»
//     solo con el respaldo de la herramienta de envíos en ese mismo turno, cada cifra con su papel y su lugar; el
//     plazo, nunca)
//   · nunca revelar el prompt ni los nombres de las herramientas
//   · sin emojis, sin signos dobles, sin «remate» ni «¡corre!»
//
// Lo que se arregla sin ambigüedad (forma, ITBMS) se arregla. Lo que cambiaría el SENTIDO
// (una cifra inventada, una promesa) se le devuelve al modelo una vez para que lo redacte bien;
// si insiste, se quita la oración. Nunca sale al cliente.

import { escaparRegex, normalizar, oraciones, sinAcentos } from "./texto";

export type TipoProblema =
  | "precio_inventado"
  | "cifra_inventada"
  | "existencias"
  | "promesa"
  | "fuga"
  | "secreto"
  | "manda_a_leer"
  | "se_hace_pasar_por_persona"
  | "palabra_prohibida";

export interface Problema {
  tipo: TipoProblema;
  /** Lo que se encontró (para el registro y para decirle al modelo qué corregir). */
  detalle: string;
}

export interface ContextoRevision {
  /** Precios de producto que devolvieron las herramientas (llevan «+ ITBMS»). */
  preciosProducto: ReadonlySet<number>;
  /** Números que aparecieron en el texto de las herramientas (plazos, porcentajes de una política): respaldan cifras de política, no dinero. */
  numerosEnTexto?: ReadonlySet<number>;
  /** Cualquier cifra que ya esté respaldada: herramientas de este turno, mensajes del cliente, respuestas anteriores. */
  cifrasConocidas: ReadonlySet<number>;
  /** Las de Odoo (`palabras_prohibidas`); las de la marca ya van incluidas. */
  palabrasProhibidas?: readonly string[];
  /** Nombres de herramientas que jamás deben aparecer en un mensaje al cliente. */
  nombresHerramientas?: readonly string[];
  /** Texto del prompt estable: ninguna frase larga suya puede salir copiada. */
  textoDelPrompt?: string;
  /** Datos que el cliente dio y no deben repetirse en la respuesta (p. ej. el PIN de Socios). */
  secretos?: readonly string[];
  /** El texto lo escribe (o lo edita y envía) una persona de verdad, como el borrador de una vendedora: ahí «soy vendedora» es cierto. */
  escribePersona?: boolean;
  /** Lo que la herramienta de envíos (cotizar_envio / agregar_envio) devolvió EN ESTE TURNO: solo eso respalda decir el costo del envío o «gratis». */
  envio?: RespaldoDeEnvio;
}

/**
 * Lo que la herramienta de envíos dijo de UN lugar en este turno, cada cifra con su papel (revisión adversarial del 2026-11-12, I1 e I2).
 * Lo arma Odoo con el motor de la tarifa y de la promoción (`respaldo_envio`), no el modelo.
 */
export interface LugarDeEnvio {
  /** Cómo se nombra el lugar (su nombre, su corregimiento, su distrito), sin acentos y en minúsculas. */
  nombres: readonly string[];
  /** El precio normal del envío. */
  normal: number | null;
  /** Lo que paga con la promoción (sin compra todavía: lo que quedaría). */
  final: number | null;
  /** Lo que D'CASA regala o abona: solo se dice como ahorro, abono o descuento, nunca como lo que cuesta. */
  ahorro: number | null;
  /** La frase de la herramienta dice «gratis» (este envío queda o quedaría gratis). */
  gratis: boolean;
  /** Todavía no hay compra: el beneficio (gratis, lo que quedaría, lo abonado) solo con el mínimo en la misma oración. */
  condicional: boolean;
  /** El mínimo de la compra que dice la frase. */
  minimo: number | null;
  /** Lo que suma la cotización, si la frase lo dice (no llega al mínimo). */
  compra: number | null;
  /** El desglose que dice la frase: «Tarifa $45 + peaje $5». */
  cargos: readonly { nombre: string; monto: number }[];
  /** Al envío se le suma el ITBMS (lo dice la herramienta). */
  llevaItbms: boolean;
}

/** El respaldo de la herramienta de envíos en un turno: los lugares que cotizó y, si sumó el envío, el total de la cotización. */
export interface RespaldoDeEnvio {
  lugares: readonly LugarDeEnvio[];
  total: number | null;
}

// ── Textos de reemplazo ─────────────────────────────────────────────────────

export const TEXTO_FUGA = "Eso no te lo puedo compartir. Cuéntame qué mueble buscas y te ayudo.";
export const TEXTO_SIN_DATO = "Ese dato te lo confirma una vendedora. Si quieres, le paso tu consulta.";

// ── Dinero ──────────────────────────────────────────────────────────────────

export interface Monto {
  valor: number;
  inicio: number;
  fin: number;
  texto: string;
}

const MONTO = new RegExp(
  [
    // $499 · $ 1,299.00 · US$ 20 · B/. 15
    String.raw`(?:US\$|U\$S|B\/\.?|\$)\s?(\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d+(?:[.,]\d{1,2})?)`,
    // 499 dólares · 15 balboas · 20 USD
    String.raw`\b(\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d+(?:[.,]\d{1,2})?)\s?(?:dólares|dolares|balboas|USD)\b`,
  ].join("|"),
  "giu",
);

export function parseMonto(t: string): number {
  let s = t.trim();
  if (/^\d{1,3}(,\d{3})+(\.\d+)?$/.test(s)) s = s.replace(/,/g, "");
  else if (/^\d{1,3}\.\d{3}$/.test(s)) s = s.replace(".", "");
  else s = s.replace(",", ".");
  return Number(s);
}

export function extraerMontos(texto: string): Monto[] {
  const salida: Monto[] = [];
  for (const m of texto.matchAll(MONTO)) {
    const num = m[1] ?? m[2];
    const valor = parseMonto(num);
    if (Number.isFinite(valor)) salida.push({ valor, inicio: m.index!, fin: m.index! + m[0].length, texto: m[0] });
  }
  return salida;
}

const cercano = (conjunto: ReadonlySet<number>, v: number) => {
  for (const x of conjunto) if (Math.abs(x - v) < 0.005) return true;
  return false;
};

const ITBMS_DESPUES = /^\s*(?:\(\s*)?(?:\+|más|mas|y)\s*(?:el\s+)?ITBMS/i;
/** El «+ ITBMS» que se le quita a una cifra del envío que no lo lleva (solo la forma de sumarlo, no «y el ITBMS» de una frase). */
const ITBMS_SUMADO = /^\s*(?:\(\s*)?(?:\+|más|mas)\s*(?:el\s+)?ITBMS(?:\s*\))?/i;

/**
 * Todo precio de producto lleva «+ ITBMS» (decisión del dueño). Se agrega donde falte. Una cifra del envío (en una cláusula que habla del
 * envío, y que es el precio de un lugar que cotizó la herramienta en este turno) lleva «+ ITBMS» solo si la herramienta dice que al
 * envío se le suma: si no lo lleva y el modelo se lo puso, se quita; si lo lleva y el modelo no lo puso, se pone (revisión M2). Las
 * otras cifras de una cláusula del envío (lo abonado, el mínimo, el total) no se tocan.
 */
export function asegurarItbms(textoOriginal: string, preciosProducto: ReadonlySet<number>, envio?: RespaldoDeEnvio): string {
  const texto = textoOriginal.normalize("NFC");
  const conLugares = Array.isArray(envio?.lugares) && envio.lugares.length > 0;
  const partes = conLugares ? partirEnClausulas(texto) : null;
  let salida = texto;
  // De atrás hacia adelante para no mover las posiciones que faltan.
  for (const m of extraerMontos(texto).reverse()) {
    const lleva = ITBMS_DESPUES.exec(salida.slice(m.fin, m.fin + 24));
    const clausula = partes?.clausulas.find((c) => c.inicio <= m.inicio && m.fin <= c.fin);
    if (partes && clausula?.deEnvio) {
      const lugares = lugaresDe(partes, clausula, envio!).filter((l) => [l.normal, l.final, ...l.cargos.map((c) => c.monto)].some((x) => x !== null && Math.abs(x - m.valor) < 0.005));
      if (lugares.length === 0) continue;
      if (lugares.every((l) => !l.llevaItbms)) {
        const sumado = ITBMS_SUMADO.exec(salida.slice(m.fin, m.fin + 24));
        if (sumado) salida = `${salida.slice(0, m.fin)}${salida.slice(m.fin + sumado[0].length)}`;
      } else if (lugares.every((l) => l.llevaItbms) && !lleva) {
        salida = `${salida.slice(0, m.fin)} + ITBMS${salida.slice(m.fin)}`;
      }
      continue;
    }
    if (cercano(preciosProducto, m.valor) && !lleva) salida = `${salida.slice(0, m.fin)} + ITBMS${salida.slice(m.fin)}`;
  }
  return salida;
}

// ── Cifras de política: plazos, porcentajes, cuotas ───────────────────────────
// «Los cambios son en 30 días», «2 años de garantía», «10 % de recargo»: si la cifra no salió de una herramienta
// (la base de conocimiento, Socios, el catálogo), es un invento. Lo que escribe el cliente tampoco la respalda.

// En inglés también (la dueña aceptó que Juan conteste en inglés, 2026-10-16): «30 days», «12 months», «10 percent».
const CIFRA_DE_POLITICA = /\b(\d+(?:[.,]\d+)?)\s*(?:%|por ciento|percent|dias?|days?|horas?|hours?|semanas?|weeks?|meses|mes|months?|a[nñ]os?|years?|cuotas?|installments?|pagos|payments)(?![a-z])/g;

const respaldada = (ctx: ContextoRevision, v: number) => cercano(ctx.cifrasConocidas, v) || (!!ctx.numerosEnTexto && cercano(ctx.numerosEnTexto, v));

export function cifrasDePolitica(texto: string): { valor: number; texto: string }[] {
  const t = sinAcentos(texto);
  return [...t.matchAll(CIFRA_DE_POLITICA)].map((m) => ({ valor: Number(m[1].replace(",", ".")), texto: m[0] }));
}

// ── Existencias ─────────────────────────────────────────────────────────────
// Los patrones se escriben SIN acentos y se aplican a `sinAcentos(texto)`: en JavaScript `\b`
// no reconoce «ú» ni «í» como letras, y así no importa cómo los escriba el modelo.

const NUM_PALABRA = "(?:una?|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce|trece|catorce|quince|veinte)";
const SOLO = "(?:solo\\s+|solamente\\s+|apenas\\s+|unicamente\\s+)?";
const EXISTENCIAS: RegExp[] = [
  /\b\d+\s*(?:unidad(?:es)?|und|uds?|pieza(?:s)?|pza(?:s)?|en stock|en existencias?|en inventario|en bodega|disponibles?|de inventario|de existencias?)\b/,
  new RegExp(`\\b${NUM_PALABRA}\\s+(?:unidad(?:es)?|pieza(?:s)?|en stock|en existencias?|en bodega)\\b`),
  new RegExp(`\\b(?:quedan|queda|restan|nos quedan|me quedan|tenemos|hay)\\s+${SOLO}(?:\\d+|${NUM_PALABRA})\\s+(?:unidad|pieza|disponible|en stock|en existencia|en bodega|en inventario|de\\s+(?:este|esta|ese|esa|estos|estas))`),
  new RegExp(`\\b(?:quedan|queda|restan|nos quedan|me quedan)\\s+${SOLO}(?:\\d+|${NUM_PALABRA})\\b`),
  /\b(?:solo|solamente|apenas)\s+(?:\d+|una?|dos|tres)\s+(?:mas|disponibles?|quedan|en)\b/,
  /\bultim[ao]s?\s+(?:unidad(?:es)?|pieza(?:s)?)\b/,
  /\bstock\s*(?:de|:|=)?\s*\d+/,
];

export function detectarExistencias(texto: string): string[] {
  const t = sinAcentos(texto);
  const hallazgos: string[] = [];
  for (const r of EXISTENCIAS) {
    const m = r.exec(t);
    if (m) hallazgos.push(m[0]);
  }
  return hallazgos;
}

// ── Promesas (regla 3): entregas, flete, financiamiento, apartados y descuentos ──

const DIA = "(?:lunes|martes|miercoles|jueves|viernes|sabado|domingo)";
const DIA_EN = "(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)";
// El costo del envío y su «gratis» no están aquí: los revisa `revisarEnvio` (abajo), cláusula por cláusula. El plazo nunca se respalda.
const PROMESAS: { r: RegExp; que: string }[] = [
  { r: /\b(?:instalacion|armado)\s+(?:es\s+|va a ser\s+|seria\s+|sera\s+)?(?:gratis|gratuit[oa]|sin costo|sin cargo|incluid[oa])\b/, que: "entrega o flete gratis" },
  { r: new RegExp(`\\b(?:te|se|le)\\s+(?:lo|la|los|las)?\\s*(?:entregamos|enviamos|mandamos|despachamos|llevamos|instalamos)\\s+(?:hoy|ma[nñ]ana|pasado ma[nñ]ana|en\\s+\\d+|el\\s+${DIA}|esta\\s+semana|ya)\\b`), que: "plazo de entrega" },
  { r: new RegExp(`\\b(?:llega|llegaria|llegara|lo recibes|la recibes|los recibes)\\s+(?:hoy|ma[nñ]ana|en\\s+\\d+|el\\s+${DIA}|esta\\s+semana)\\b`), que: "plazo de entrega" },
  { r: /\b(?:entregamos|enviamos|hacemos entregas?|llevamos)\s+(?:a|en)\s+(?:todo|toda|todas|todos|cualquier)\b/, que: "cobertura de entrega" },
  // El plazo del envío lo confirma una vendedora (regla 3), aunque alguna nota de la tienda lo traiga.
  { r: /\b(?:entrega|envio|despacho|delivery)\b[^.!?\n]{0,30}\b(?:tarda|toma|demora|llega|es)\s+(?:en\s+|de\s+)?(?:entre\s+)?\d+/, que: "plazo de entrega" },
  { r: /\b(?:te|se|le)\s+(?:lo|la|los|las)?\s*(?:apartamos|reservamos|guardamos|separamos)\b/, que: "apartado" },
  { r: /\b(?:queda|quedan|quedo|deje|dejo|dejamos)\s+(?:apartad[oa]s?|reservad[oa]s?|separad[oa]s?)\b/, que: "apartado" },
  { r: /\b(?:te|le)\s+(?:doy|damos|hago|hacemos|aplico|aplicamos|ofrezco|ofrecemos|dejo|dejamos|regalo|regalamos)\s+(?:un\s+|el\s+|una\s+)?(?:\d+\s*%\s*de\s+)?(?:descuento|rebaja|promocion|oferta)\b/, que: "descuento" },
  { r: /\b(?:financiamos|financiamiento\s+(?:disponible|aprobado|a\s+\d+)|a\s+(?:\d+\s+)?(?:cuotas|plazos|meses)\s+sin\s+interes|pagos?\s+(?:a\s+)?(?:cuotas|plazos)\s+(?:disponibles?|sin))\b/, que: "financiamiento" },
  { r: /\b(?:te|le)\s+(?:aprobamos|damos credito|fiamos)\b/, que: "crédito" },
  // Un pago solo lo valida una persona (regla 5): el bot nunca lo da por recibido.
  { r: /\b(?:pago|deposito|transferencia|yappy|comprobante)\s+(?:ya\s+)?(?:fue\s+|esta\s+|queda\s+)?(?:recibid[oa]|confirmad[oa]|aprobad[oa]|acreditad[oa]|verificad[oa]|valid[ao]d[oa])\b/, que: "pago confirmado" },
  { r: /\b(?:recibimos|recibi|confirmamos|confirmo|verifique|verificamos|valide|validamos|vi|veo)\s+(?:ya\s+)?(?:tu|su|el)\s+(?:pago|deposito|transferencia|comprobante|yappy)\b/, que: "pago confirmado" },
  { r: /\bya\s+(?:esta|quedo)\s+pagad[oa]\b/, que: "pago confirmado" },
  // Los puntos nacen con la factura pagada (regla 4): el bot no acredita ni promete puntos de una compra sin facturar.
  { r: /\bacredit(?:o|amos|aremos|are|ado|ada|ados|adas)\b/, que: "puntos acreditados" },
  { r: /\b(?:te|le)\s+(?:sumo|sumamos|sumaremos|damos|daremos|doy|regalo|regalamos|abono|abonamos)\s+(?:\d+\s+)?puntos\b/, que: "puntos prometidos" },
  { r: /\bcon\s+(?:esta|esa|tu|su)\s+compra\s+(?:ganas|ganaras|acumulas|acumularas|sumas|sumaras|recibes|recibiras|te llevas)\b/, que: "puntos prometidos" },
  { r: /\b(?:ganaras|acumularas|sumaras|recibiras|ganaria|acumularia)\s+\d+\s+puntos\b/, que: "puntos prometidos" },
  // Lo mismo en inglés: Juan contesta en inglés a quien le escribe en inglés (decisión de la dueña, 2026-10-16).
  { r: /\b(?:assembly|installation)\s+(?:is\s+|will be\s+|would be\s+)?(?:free|included|at no (?:extra )?cost)\b/, que: "entrega o flete gratis" },
  { r: new RegExp(`\\bwe(?:['’]ll| will| can)?\\s+(?:deliver|ship|send|bring)\\s+(?:it|them|your \\w+)?\\s*(?:today|tomorrow|on\\s+${DIA_EN}|in\\s+\\d+|this\\s+week|right away)\\b`), que: "plazo de entrega" },
  { r: new RegExp(`\\b(?:it(?:['’]ll| will)?\\s+(?:arrive|get there)|you(?:['’]ll| will)\\s+(?:get|receive)\\s+(?:it|them))\\s+(?:today|tomorrow|on\\s+${DIA_EN}|in\\s+\\d+|this\\s+week)\\b`), que: "plazo de entrega" },
  { r: /\bwe(?:['’]ll| will| can)?\s+(?:hold|reserve|put aside|set aside|save)\s+(?:it|them|this|that|the \w+)\s+for\s+you\b|\b(?:it|this|that)(?:['’]s| is)\s+(?:reserved|on hold|set aside)\s+for\s+you\b/, que: "apartado" },
  { r: /\b(?:i|we)(?:['’]ll| will| can)?\s+(?:give|offer|apply|get)\s+you\s+(?:a\s+|an\s+)?(?:\d+\s*%\s*)?(?:discount|special price|deal)\b/, que: "descuento" },
  { r: /\bwe\s+(?:finance|offer financing)\b|\b(?:interest[- ]free|no[- ]interest|zero[- ]interest)\s+(?:installments|payments|months|financing)\b/, que: "financiamiento" },
  { r: /\bwe(?:['’]ll| will| can)?\s+approve\s+(?:you|your)\b|\byou(?:['’]re| are)\s+(?:pre-?)?approved\b/, que: "crédito" },
  { r: /\b(?:payment|transfer|deposit|receipt)\s+(?:has been\s+|was\s+|is\s+)?(?:received|confirmed|approved|verified)\b|\bwe\s+(?:received|got|confirmed|verified)\s+your\s+(?:payment|transfer|deposit|receipt)\b/, que: "pago confirmado" },
];

/** «20% de descuento» solo es una promesa si el 20 NO salió de una herramienta (p. ej. el catálogo). */
const PORCENTAJE = /\b(\d+(?:[.,]\d+)?)\s*%\s*(?:de\s+)?(?:descuento|menos|off|rebaja)\b|\bdescuento\s+(?:de|del)\s+(\d+(?:[.,]\d+)?)\s*%/g;

/** Las promesas de siempre (entregas, apartados, financiamiento, descuentos…), sin el costo del envío. */
function promesasSinEnvio(texto: string, conocidas: ReadonlySet<number>): string[] {
  const t = sinAcentos(texto);
  const que = PROMESAS.filter((p) => p.r.test(t)).map((p) => p.que);
  for (const m of t.matchAll(PORCENTAJE)) {
    const n = Number((m[1] ?? m[2]).replace(",", "."));
    if (!cercano(conocidas, n)) que.push("descuento");
  }
  return que;
}

export function detectarPromesas(texto: string, conocidas: ReadonlySet<number> = new Set(), envio?: RespaldoDeEnvio): string[] {
  return [...promesasSinEnvio(texto, conocidas), ...revisarEnvio(texto, envio)];
}

// ── El envío: cada cifra con su papel y su lugar (revisión adversarial del 2026-11-12: I1, I2, I3, I5, M1) ──────────
// Cada oración se parte en cláusulas («;», « y », « pero », « o », y una coma seguida de otro sujeto: «, la cama…»; nunca dentro de un
// paréntesis ni en los dos puntos). Toda cláusula que habla del envío (envío, flete, entrega, domicilio, delivery, shipping…; o de la
// promoción, el abono o «gratis» en una oración que habla del envío; o que sigue a una del envío sin sujeto propio) y lleva una cifra de
// dinero o un «gratis» (dicho de cualquier forma: «no pagas», «sin costo», «on us», «$0»…) solo pasa si la herramienta de envíos de ESTE
// turno la respalda, con el papel correcto (el precio normal, lo que queda, lo abonado o ahorrado SOLO como ahorro, el mínimo, lo que
// suma la cotización, el total, el desglose) y para el lugar que nombra (o, si no nombra ninguno, para alguno de los cotizados). Con la
// promoción condicional (todavía sin compra), lo que queda, lo abonado y el «gratis» solo con el mínimo en la misma oración. Las
// cláusulas que no hablan del envío siguen las reglas de los productos.

const PALABRA_ENVIO = /\b(?:envio|envios|flete|fletes|entrega|entregas|domicilio|delivery|deliveries|shipping|despacho|transporte|llevamos|llevarlo|llevarla|llevartelo|llevartela|entregamos|despachamos)\b/;
const PALABRA_PROMOCION = /\b(?:promocion|promo|abono|abona|abonamos|regala|regalamos|ahorras|ahorro|descuento|rebaja|gratis|gratuit[oa]|te queda|te quedaria|te sale|te saldria|free|on us|save)\b/;
// Con sus acentos: «tu cama» tiene sujeto propio; «tú pagas» no (sigue hablando del envío).
const SUJETO_PROPIO = /^(?:la|el|los|las|tu|tus|su|sus|mi|mis|este|esta|estos|estas|ese|esa|esos|esas|the|your|my|this|that|these|those)\s+(\S+)/;
const SUJETO_DEL_ENVIO = /^(?:promocion|promo|abono|descuento|rebaja|ahorro|envio|flete|entrega|delivery|shipping)/;
const CORTES = /\s*;\s*|\s+(?:y|e|pero|o|u|aunque|mientras que|mientras|and|but|or|while)\s+|,\s+(?=(?:la|el|los|las|tu|tus|su|sus|mi|mis|este|esta|estos|estas|ese|esa|the|your|my|this|that)\s)/g;
const GRATIS_DICHO =
  /\b(?:gratis|gratuit[oa]s?|sin costo|sin cargo|no pagas|no te cuesta|no cuesta nada|no tiene costo|por nuestra cuenta|corre por nuestra cuenta|te lo regalamos|te regala(?:mos)? el envio|free|on us|no charge|at no (?:extra )?cost|won'?t pay|will not pay|don'?t pay|complimentary)\b/;
/** «Flete incluido», «el envío va incluido»: es decir que es gratis (salvo que hable del total: «el total, con el envío incluido»). */
const ENVIO_INCLUIDO = /\b(?:envio|flete|entrega|delivery|shipping|despacho|transporte)\b[^.;]{0,30}?\b(?:incluid[oa]|included)\b/;
const HABLA_DEL_TOTAL = /\b(?:total|cotizacion|precio)\b/;
/** Antes de la cifra: es lo abonado o lo ahorrado («te abona $20», «te ahorras $45», «el abono es de $20», «save $20»). */
const AHORRO_ANTES = /\b(?:abona|abonamos|abonan|abono|ahorras|ahorrarias|ahorro|ahorrar|descuento|descontamos|rebaja|rebajamos|resta|restamos|pone|ponemos|cubre|cubrimos|asume|asumimos|save|saving|savings|discount|credit|off|covers?)\b/;
/** Después de la cifra: «$20 menos», «$20 más barato», «$20 de descuento», «$20 off». */
const AHORRO_DESPUES = /^\s*(?:\+\s*itbms\s*)?(?:menos|mas barato|de descuento|de ahorro|de rebaja|de abono|off|less|cheaper)\b/;
/** Antes de la cifra: el mínimo de la compra («en compras de más de $200», «el mínimo es de $200», «over $200»). */
const MINIMO_ANTES = /\b(?:mas de|pasa de|pasan de|pase de|supera|superior(?:es)? a|minim[oa]|al menos|por lo menos|a partir de|over|more than|minimum|at least|above)\b/;
const TOTAL_ANTES = /\btotal\b/;
const COMPRA_ANTES = /\b(?:suma|sumas|compra|compras|cotizacion|purchase|order)\b/;

interface Tramo {
  inicio: number;
  fin: number;
}
interface Clausula extends Tramo {
  oracion: number;
  deEnvio: boolean;
}
interface Particion {
  texto: string;
  /** El texto sin acentos y en minúsculas, con el MISMO largo (cada letra en su lugar). */
  bajo: string;
  oraciones: Tramo[];
  clausulas: Clausula[];
}

/** Sin acentos y en minúsculas, letra por letra: las posiciones son las mismas que las del texto. */
function bajar(t: string): string {
  let salida = "";
  for (let i = 0; i < t.length; i++) {
    const s = sinAcentos(t[i]);
    salida += s.length === 1 ? s : t[i].toLowerCase().slice(0, 1) || t[i];
  }
  return salida;
}

/** Las oraciones con su posición: las mismas (y en el mismo orden) que `oraciones()`. */
function oracionesConPosicion(t: string): Tramo[] {
  const salida: Tramo[] = [];
  const agregar = (desde: number, hasta: number) => {
    const trozo = t.slice(desde, hasta);
    const inicio = desde + (trozo.length - trozo.trimStart().length);
    const fin = hasta - (trozo.length - trozo.trimEnd().length);
    if (fin > inicio) salida.push({ inicio, fin });
  };
  let desde = 0;
  for (const m of t.matchAll(/(?<=[.!?…])\s+|\n+/g)) {
    agregar(desde, m.index!);
    desde = m.index! + m[0].length;
  }
  agregar(desde, t.length);
  return salida;
}

function partirEnClausulas(texto: string): Particion {
  const bajo = bajar(texto);
  const oraciones = oracionesConPosicion(texto);
  const clausulas: Clausula[] = [];
  let anteriorDelEnvio = false;
  const minusculas = texto.toLowerCase();
  // El sujeto propio se mira con los acentos («tu cama» / «tú pagas»); su palabra, sin acentos.
  const sujetoDe = (desde: number, hasta: number) => {
    const s = SUJETO_PROPIO.exec(minusculas.slice(desde, hasta).trimStart());
    return s ? sinAcentos(s[1]) : null;
  };
  oraciones.forEach((o, i) => {
    const ob = bajo.slice(o.inicio, o.fin);
    const sujeto = sujetoDe(o.inicio, o.fin);
    // Una oración habla del envío si lo nombra, o si sigue a una que habla del envío y trae la promoción, el abono o «gratis» sin otro sujeto.
    const delEnvio = PALABRA_ENVIO.test(ob) || (anteriorDelEnvio && (PALABRA_PROMOCION.test(ob) || GRATIS_DICHO.test(ob)) && (!sujeto || SUJETO_DEL_ENVIO.test(sujeto)));
    anteriorDelEnvio = delEnvio;
    if (!delEnvio) {
      clausulas.push({ inicio: o.inicio, fin: o.fin, oracion: i, deEnvio: false });
      return;
    }
    const mascara = ob.replace(/\([^)]*\)/g, (m) => `(${"x".repeat(m.length - 2)})`);
    let previa = false;
    const agregar = (desde: number, hasta: number) => {
      const cb = ob.slice(desde, hasta).trim();
      if (!cb) return;
      const s = sujetoDe(o.inicio + desde, o.inicio + hasta);
      const deEnvio = PALABRA_ENVIO.test(cb) || (s ? SUJETO_DEL_ENVIO.test(s) : PALABRA_PROMOCION.test(cb) || GRATIS_DICHO.test(cb) || previa);
      previa = deEnvio;
      clausulas.push({ inicio: o.inicio + desde, fin: o.inicio + hasta, oracion: i, deEnvio });
    };
    let desde = 0;
    for (const m of mascara.matchAll(CORTES)) {
      agregar(desde, m.index!);
      desde = m.index! + m[0].length;
    }
    agregar(desde, ob.length);
  });
  return { texto, bajo, oraciones, clausulas };
}

const casi = (a: number | null | undefined, b: number) => a !== null && a !== undefined && Math.abs(a - b) < 0.005;

/** Los lugares del respaldo que nombra un texto (su nombre, corregimiento o distrito como palabras enteras). */
function nombrados(textoBajo: string, envio: RespaldoDeEnvio): LugarDeEnvio[] {
  return envio.lugares.filter((l) => l.nombres.some((n) => n.length >= 3 && new RegExp(`(?<![\\p{L}\\p{N}])${escaparRegex(n)}(?![\\p{L}\\p{N}])`, "u").test(textoBajo)));
}

/** Los lugares de los que habla la cláusula: los que nombra; si no nombra ninguno, los que nombra su oración; si tampoco, todos. */
function lugaresDe(p: Particion, c: Clausula, envio: RespaldoDeEnvio): readonly LugarDeEnvio[] {
  const enLaClausula = nombrados(p.bajo.slice(c.inicio, c.fin), envio);
  if (enLaClausula.length) return enLaClausula;
  const o = p.oraciones[c.oracion];
  const enLaOracion = nombrados(p.bajo.slice(o.inicio, o.fin), envio);
  return enLaOracion.length ? enLaOracion : envio.lugares;
}

/** ¿La oración dice el mínimo de la compra de ese lugar? (Con la promoción condicional, el beneficio solo va con su condición.) */
function condicionDicha(l: LugarDeEnvio, oracion: string): boolean {
  return !l.condicional || (l.minimo !== null && extraerMontos(oracion).some((m) => casi(l.minimo, m.valor)));
}

/** ¿Esa cifra, dicha así (lo que va antes y después), es una cifra de ese lugar con el papel correcto? */
function cifraDelLugar(l: LugarDeEnvio, valor: number, antes: string, despues: string, oracion: string, envio: RespaldoDeEnvio): boolean {
  if (MINIMO_ANTES.test(antes)) return casi(l.minimo, valor);
  if (AHORRO_ANTES.test(antes) || AHORRO_DESPUES.test(despues)) return casi(l.ahorro, valor) && condicionDicha(l, oracion);
  if (TOTAL_ANTES.test(antes)) return casi(envio.total, valor);
  if (COMPRA_ANTES.test(antes)) return casi(l.compra, valor);
  const cargo = l.cargos.find((c) => c.nombre && antes.includes(sinAcentos(c.nombre)));
  if (cargo) return casi(cargo.monto, valor);
  return casi(l.normal, valor) || (casi(l.final, valor) && condicionDicha(l, oracion));
}

/** Lo que tiene de malo, sobre el envío, cada oración del texto (en el orden de `oraciones()`). */
export function revisarEnvioPorOracion(textoOriginal: string, envio?: RespaldoDeEnvio): string[][] {
  const p = partirEnClausulas(textoOriginal.normalize("NFC"));
  const salida: string[][] = p.oraciones.map(() => []);
  const conLugares = Array.isArray(envio?.lugares) && envio.lugares.length > 0;
  for (const c of p.clausulas) {
    if (!c.deEnvio) continue;
    const cb = p.bajo.slice(c.inicio, c.fin);
    const montos = extraerMontos(p.texto.slice(c.inicio, c.fin));
    const gratis = GRATIS_DICHO.test(cb) || (ENVIO_INCLUIDO.test(cb) && !HABLA_DEL_TOTAL.test(cb)) || montos.some((m) => m.valor === 0);
    if (montos.length === 0 && !gratis) continue;
    const problemas = salida[c.oracion];
    if (!conLugares) {
      problemas.push(montos.some((m) => m.valor !== 0) ? "costo de entrega" : "entrega o flete gratis");
      continue;
    }
    const o = p.oraciones[c.oracion];
    const oracion = p.texto.slice(o.inicio, o.fin);
    const lugares = lugaresDe(p, c, envio!);
    let finAnterior = 0;
    for (const m of montos) {
      const antes = cb.slice(Math.max(finAnterior, m.inicio - 40), m.inicio);
      const despues = cb.slice(m.fin, m.fin + 24);
      finAnterior = m.fin;
      if (m.valor === 0) continue; // «$0» es un «gratis»
      if (!lugares.some((l) => cifraDelLugar(l, m.valor, antes, despues, oracion, envio!))) problemas.push("costo de entrega");
    }
    if (gratis && !lugares.some((l) => l.gratis && condicionDicha(l, oracion))) problemas.push("entrega o flete gratis");
  }
  return salida.map((ps) => [...new Set(ps)]);
}

/** Lo que tiene de malo el texto sobre el envío (cifras o «gratis» que la herramienta de envíos de este turno no respalda). */
export function revisarEnvio(texto: string, envio?: RespaldoDeEnvio): string[] {
  return [...new Set(revisarEnvioPorOracion(texto, envio).flat())];
}

// ── Mandar a leer políticas ─────────────────────────────────────────────────

/**
 * La dueña no quiere que el bot mande a nadie a leer políticas, términos ni avisos de privacidad: se le responde con
 * lo que dice la base de conocimiento, y si la persona quiere el documento, ella misma lo encuentra en la página.
 * Se revisa sobre texto sin acentos y en minúsculas.
 */
const MANDA_A_LEER = [
  /\b(?:lee|leer|leas|leerlas|leerlos|revisa|revisar|revises|consulta|consultar|consultes|visita|visitar|mira|checa|checar)\b[^.!?\n]{0,70}\b(?:politicas?|terminos|aviso de privacidad|aviso legal|privacidad)\b/,
  /\b(?:mas|todo)\s+(?:en|sobre)\s+(?:nuestras?\s+)?(?:politicas?|terminos|aviso de privacidad|privacidad)\b/,
  /\b(?:en|segun|ver|vea|ve)\s+(?:nuestras?|las|los|la|el)\s+(?:politicas?|terminos(?: y condiciones)?|aviso de privacidad|politica de privacidad)\b/,
  /dcasapty\.com\/(?:privacidad|terminos|politica)/,
  /\b(?:read|check|see|review|visit|look at)\b[^.!?\n]{0,70}\b(?:policy|policies|terms and conditions|terms of (?:use|service|sale)|our terms|privacy notice)\b/,
];

/**
 * Juan se presenta con nombre de persona, pero NUNCA dice que lo es: ni «soy una persona», ni «soy humano», ni «no soy un bot», ni que es
 * vendedor o vendedora (esas son las personas de la tienda). «No soy una persona, soy el asistente virtual» está bien.
 */
const SER_HUMANO = [
  /(?<!\bno )\bsoy (?:una |un )?(?:persona|humano|humana|ser humano)\b/,
  /(?<!\bno )\bsoy (?:una |un )?(?:persona )?(?:real|de verdad|de carne y hueso)\b/,
  /\bno soy (?:ningun |ninguna |un |una )?(?:bot|chatbot|robot|ia|inteligencia artificial|programa|maquina|asistente(?: virtual| automatico)?)\b/,
  /(?<!\bno soy (?:una |un )?(?:persona )?)\bde carne y hueso\b/,
  /(?<!\bno )\b(?:hablas?|esta hablando|estas hablando) con (?:una |un )?(?:persona|humano|humana)(?: real| de verdad)?\b/,
  /\bsoy (?:un |una )?(?:vendedor|vendedora|asesor|asesora) (?:de|en) /,
  /\bsoy (?:el |la |un |una )?(?:vendedor|vendedora)\b/,
  /\bi(?:['’]m| am) (?:an? )?(?:real )?(?:human(?: being)?|person)\b/,
  /\bi(?:['’]m| am) not (?:an? )?(?:bot|chatbot|robot|ai|machine|program|(?:virtual )?assistant)\b/,
  /\byou(?:['’]re| are) (?:talking|chatting|speaking) (?:to|with) (?:an? )?(?:real )?(?:human|person)\b/,
  /\bi(?:['’]m| am) (?:an? |the )?(?:salesperson|sales rep|sales representative|saleswoman|salesman|seller)\b/,
];

export function detectarSerHumano(texto: string): string[] {
  const t = sinAcentos(texto.toLowerCase());
  return SER_HUMANO.map((re) => re.exec(t)?.[0]).filter((x): x is string => !!x);
}

export function detectarMandaALeer(texto: string): string[] {
  const t = sinAcentos(texto).toLowerCase();
  return MANDA_A_LEER.filter((r) => r.test(t)).map(() => "mandar a leer políticas o términos");
}

// ── Voz de marca ────────────────────────────────────────────────────────────

/** Siempre prohibidas (CLAUDE.md, regla 6). Las de Odoo se suman. */
export const PALABRAS_PROHIBIDAS_DE_MARCA: readonly string[] = ["remate", "remates", "corre", "corran", "liquidacion total", "ultima oportunidad", "no te lo pierdas", "last chance"];

function palabraProhibida(texto: string, palabras: readonly string[]): string | null {
  const t = ` ${normalizar(texto)} `;
  for (const p of palabras) {
    const n = normalizar(p);
    if (n && t.includes(` ${n} `)) return p;
  }
  return null;
}

const EMOJI = /[\p{Extended_Pictographic}\u{1F1E6}-\u{1F1FF}\u{1F3FB}-\u{1F3FF}\u{FE0F}\u{200D}\u{20E3}✓✔✅☑]/gu;

/** Forma: sin emojis, sin signos dobles, sin markdown de documento. WhatsApp usa *un* asterisco. */
export function limpiarForma(texto: string): string {
  return texto
    .replace(EMOJI, "")
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/\*\*([^*\n]+)\*\*/g, "*$1*")
    .replace(/__([^_\n]+)__/g, "_$1_")
    .replace(/^\s*[-–—]{3,}\s*$/gm, "")
    .replace(/¡{2,}/g, "¡")
    .replace(/¿{2,}/g, "¿")
    .replace(/!{2,}/g, "!")
    .replace(/\?{2,}/g, "?")
    .replace(/\.{4,}/g, "...")
    .replace(/[ \t]{2,}/g, " ")
    .replace(/ +([,.;:!?])/g, "$1")
    .replace(/\n{3,}/g, "\n\n")
    .replace(/[ \t]+\n/g, "\n")
    .trim();
}

// ── Fugas del prompt ────────────────────────────────────────────────────────

const ETIQUETAS_DEL_PROMPT = [
  "<fuentes_de_verdad>",
  "</fuentes_de_verdad>",
  "<identidad>",
  "<voz>",
  "<reglas>",
  "<contexto_de_este_chat>",
  "<mensaje_del_cliente>",
  "regla inquebrantable",
  "system prompt",
  "prompt del sistema",
];

/** Ventanas de 10 palabras: copiar una regla entera del prompt es una fuga; decir «te lo confirma una vendedora» no. */
function copiaDelPrompt(texto: string, prompt: string): string | null {
  const ventana = 10;
  const palabras = normalizar(texto).split(" ").filter(Boolean);
  if (palabras.length < ventana) return null;
  const base = ` ${normalizar(prompt)} `;
  for (let i = 0; i + ventana <= palabras.length; i++) {
    const trozo = palabras.slice(i, i + ventana).join(" ");
    if (base.includes(` ${trozo} `)) return trozo;
  }
  return null;
}

/** El modelo «aceptó» una manipulación: lo dice en voz alta aunque no haya filtrado nada. */
const ACUSES_DE_MANIPULACION = new RegExp(
  [
    String.raw`\bmodo\s+(?:administrador|admin|desarrollador|developer|dios|debug|mantenimiento|sin\s+restricciones)\b`,
    String.raw`\bsin\s+(?:reglas|restricciones|filtros)\b`,
    String.raw`\b(?:ignor(?:o|are|ando)|olvido|olvidare|dejo\s+de\s+seguir)\s+(?:mis|las|todas\s+mis|todas\s+las|mi)\s+(?:reglas|instrucciones|normas)\b`,
    String.raw`\ba\s+partir\s+de\s+ahora\s+(?:soy|ya\s+no\s+soy|actuo|actuare|respondo\s+como)\b`,
    String.raw`\bahora\s+(?:soy|actuo\s+como)\s+(?:dan|otro|otra)\b`,
    String.raw`\bmis\s+(?:instrucciones|reglas)\s+(?:dicen|son|indican|me\s+piden)\b`,
  ].join("|"),
);

function fuga(texto: string, ctx: ContextoRevision): string | null {
  const bajo = texto.toLowerCase();
  for (const e of ETIQUETAS_DEL_PROMPT) if (bajo.includes(e)) return e;
  const acuse = ACUSES_DE_MANIPULACION.exec(sinAcentos(texto));
  if (acuse) return acuse[0];
  for (const n of ctx.nombresHerramientas ?? []) {
    // Un nombre con guion bajo («buscar_productos») nunca es una frase natural: basta que aparezca. Uno de una sola palabra
    // («cotizar») sí lo es («para cotizar necesito el tamaño»): solo cuenta si se escribe como llamada o entre comillas.
    const patron = n.includes("_") ? `(?<![a-z0-9_])${escaparRegex(n)}(?![a-z0-9_])` : `(?<![a-z0-9_])${escaparRegex(n)}\\s*\\(|[\`'"“«]${escaparRegex(n)}[\`'"”»]`;
    if (new RegExp(patron, "i").test(texto)) return n;
  }
  return ctx.textoDelPrompt ? copiaDelPrompt(texto, ctx.textoDelPrompt) : null;
}

/** Lo que delata información interna en un texto (una etiqueta o una frase copiada del prompt, el nombre de una herramienta), o null. */
export function detectarFuga(texto: string, ctx: ContextoRevision): string | null {
  return fuga(limpiarForma(texto), ctx);
}

// ── Análisis y reparación ───────────────────────────────────────────────────

export interface Analisis {
  /** El texto con la forma arreglada y el «+ ITBMS» puesto donde faltaba. */
  limpio: string;
  /** Lo que cambiaría el sentido: hay que reescribir o quitar. */
  graves: Problema[];
}

export function analizar(borrador: string, ctx: ContextoRevision): Analisis {
  const graves: Problema[] = [];
  let limpio = limpiarForma(borrador);

  const f = fuga(limpio, ctx);
  if (f) {
    graves.push({ tipo: "fuga", detalle: f });
    return { limpio, graves };
  }

  limpio = asegurarItbms(limpio, ctx.preciosProducto, ctx.envio);

  const secreto = secretoRepetido(limpio, ctx);
  if (secreto) graves.push({ tipo: "secreto", detalle: "un dato que el cliente dio en confianza" });

  for (const m of extraerMontos(limpio)) {
    if (!cercano(ctx.cifrasConocidas, m.valor)) {
      graves.push({ tipo: "precio_inventado", detalle: m.texto });
    }
  }
  for (const c of cifrasDePolitica(limpio)) if (!respaldada(ctx, c.valor)) graves.push({ tipo: "cifra_inventada", detalle: c.texto });
  for (const h of detectarExistencias(limpio)) graves.push({ tipo: "existencias", detalle: h });
  for (const p of detectarPromesas(limpio, ctx.cifrasConocidas, ctx.envio)) graves.push({ tipo: "promesa", detalle: p });
  for (const p of detectarMandaALeer(limpio).slice(0, 1)) graves.push({ tipo: "manda_a_leer", detalle: p });
  for (const p of ctx.escribePersona ? [] : detectarSerHumano(limpio).slice(0, 1)) graves.push({ tipo: "se_hace_pasar_por_persona", detalle: p });
  const prohibida = palabraProhibida(limpio, [...PALABRAS_PROHIBIDAS_DE_MARCA, ...(ctx.palabrasProhibidas ?? [])]);
  if (prohibida) graves.push({ tipo: "palabra_prohibida", detalle: prohibida });

  return { limpio, graves };
}

/** Quita las oraciones que contienen algo grave. Devuelve "" si no queda nada que decir. */
export function quitarGraves(limpio: string, ctx: ContextoRevision): string {
  // El envío se revisa con el texto entero (una oración sigue el tema de la anterior) y se reparte por oración.
  const delEnvio = revisarEnvioPorOracion(limpio, ctx.envio);
  const buenas = oraciones(limpio).filter((o, i) => {
    const { graves } = analizarOracion(o, ctx);
    return graves.length === 0 && (delEnvio[i] ?? []).length === 0;
  });
  return buenas.join(" ").trim();
}

/** Un dato que el cliente dio en confianza (su PIN) y la respuesta repite. */
function secretoRepetido(texto: string, ctx: ContextoRevision): boolean {
  return (ctx.secretos ?? []).some((x) => x.length >= 4 && texto.includes(x));
}

function analizarOracion(o: string, ctx: ContextoRevision): { graves: Problema[] } {
  const graves: Problema[] = [];
  if (secretoRepetido(o, ctx)) graves.push({ tipo: "secreto", detalle: "un dato que el cliente dio en confianza" });
  for (const m of extraerMontos(o)) if (!cercano(ctx.cifrasConocidas, m.valor)) graves.push({ tipo: "precio_inventado", detalle: m.texto });
  for (const c of cifrasDePolitica(o)) if (!respaldada(ctx, c.valor)) graves.push({ tipo: "cifra_inventada", detalle: c.texto });
  for (const h of detectarExistencias(o)) graves.push({ tipo: "existencias", detalle: h });
  for (const p of promesasSinEnvio(o, ctx.cifrasConocidas)) graves.push({ tipo: "promesa", detalle: p });
  for (const p of detectarMandaALeer(o).slice(0, 1)) graves.push({ tipo: "manda_a_leer", detalle: p });
  for (const p of ctx.escribePersona ? [] : detectarSerHumano(o).slice(0, 1)) graves.push({ tipo: "se_hace_pasar_por_persona", detalle: p });
  const prohibida = palabraProhibida(o, [...PALABRAS_PROHIBIDAS_DE_MARCA, ...(ctx.palabrasProhibidas ?? [])]);
  if (prohibida) graves.push({ tipo: "palabra_prohibida", detalle: prohibida });
  return { graves };
}

/** La nota que se le da al modelo para que reescriba su borrador. */
export function notaDeCorreccion(graves: readonly Problema[]): string {
  const por: Record<TipoProblema, string> = {
    precio_inventado: "una cifra de dinero que no salió de una herramienta",
    cifra_inventada: "una cifra (plazo, porcentaje, cuotas) que no salió de una herramienta",
    existencias: "un número de existencias o inventario",
    promesa: "una promesa de entrega, flete, financiamiento, apartado o descuento",
    fuga: "información interna",
    secreto: "un dato que el cliente dio en confianza (como su PIN): jamás se repite",
    manda_a_leer: "mandar al cliente a leer políticas, términos o avisos (respóndele tú con lo que dice la herramienta)",
    se_hace_pasar_por_persona: "decir que eres una persona o que no eres un bot (eres Juan, el asistente virtual de D'CASA: si preguntan de verdad, dilo con naturalidad)",
    palabra_prohibida: "una palabra que la marca no usa",
  };
  const lista = [...new Set(graves.map((g) => `${por[g.tipo]} («${g.detalle}»)`))].join("; ");
  return (
    `Tu borrador anterior NO se envió porque tenía ${lista}. Reescribe la respuesta sin eso: ` +
    "usa solo cifras que devolvieron las herramientas (con «+ ITBMS»), nunca digas cuántas unidades hay, " +
    "el costo del envío solo tal cual lo dio cotizar_envio (o agregar_envio) en esta respuesta (lo que D'CASA abona o regala, solo como ahorro; " +
    "si la promoción depende de la compra, con su condición en la misma oración), " +
    "y lo demás de entregas (la fecha), flete, financiamiento, apartados y descuentos queda en «te lo confirma una vendedora». " +
    "Mantén el tuteo, sin emojis, en 2 a 4 líneas."
  );
}

