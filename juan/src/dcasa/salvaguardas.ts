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
//   · nunca negar un producto («no lo manejamos») que la herramienta dijo que sí se vende aunque no esté publicado
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
  | "palabra_prohibida"
  | "niega_producto";

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
  /** Una herramienta dijo EN ESTE TURNO que hay productos así que se venden sin estar publicados en la tienda en línea: no se niegan. */
  haySinPublicar?: boolean;
  /**
   * Las frases que Odoo escribió para el cliente EN ESTE TURNO (`frase_para_el_cliente` de una herramienta). Una línea que el modelo
   * copia tal cual conserva sus íconos: los escribió la tienda, no el modelo. Todo lo demás del mensaje sigue sin emojis.
   */
  frasesDeLaTienda?: readonly string[];
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
const SIN_ITBMS_DESPUES = /^\s*(?:\(\s*)?sin\s+(?:el\s+)?ITBMS/i;
/** El «+ ITBMS» que se le quita a una cifra del envío que no lo lleva (solo la forma de sumarlo, no «y el ITBMS» de una frase). */
const ITBMS_SUMADO = /^\s*(?:\(\s*)?(?:\+|más|mas)\s*(?:el\s+)?ITBMS(?:\s*\))?/i;

/**
 * Todo precio de producto lleva «+ ITBMS» (decisión del dueño). Se agrega donde falte. Una cifra que la oración le atribuye al envío (y que
 * es el precio de un lugar que cotizó la herramienta en este turno) lleva «+ ITBMS» solo si la herramienta dice que al envío se le suma: si
 * no lo lleva y el modelo se lo puso, se quita; si lo lleva y el modelo no lo puso, se pone (revisión M2). Las otras cifras del envío (lo
 * abonado, el mínimo, el total) no se tocan.
 */
export function asegurarItbms(textoOriginal: string, preciosProducto: ReadonlySet<number>, envio?: RespaldoDeEnvio): string {
  const texto = textoOriginal.normalize("NFC");
  const conLugares = Array.isArray(envio?.lugares) && envio.lugares.length > 0;
  const partes = conLugares ? partirEnClausulas(texto) : null;
  let salida = texto;
  // De atrás hacia adelante para no mover las posiciones que faltan.
  for (const m of extraerMontos(texto).reverse()) {
    const lleva = ITBMS_DESPUES.exec(salida.slice(m.fin, m.fin + 24));
    if (SIN_ITBMS_DESPUES.test(salida.slice(m.fin, m.fin + 24))) continue; // «$200 sin ITBMS»: dicho a propósito
    const clausula = partes?.clausulas.find((c) => c.inicio <= m.inicio && m.fin <= c.fin);
    if (partes && clausula?.deEnvio) {
      // Lo abonado, el mínimo, el total o lo que suma la cotización, dicho en una cláusula del envío: no se tocan.
      const cb = partes.bajo.slice(clausula.inicio, clausula.fin);
      const r = m.inicio - clausula.inicio;
      if (papelDe(cb.slice(Math.max(0, r - 40), r), cb.slice(r + m.fin - m.inicio, r + m.fin - m.inicio + 24)) !== "costo") continue;
    }
    if (partes && clausula && cifraDelEnvio(partes, clausula, m.inicio - clausula.inicio, m.fin - clausula.inicio, cercano(preciosProducto, m.valor))) {
      const lugares = lugaresDe(partes, clausula, envio!).filter((l) => [l.normal, l.final, ...l.cargos.map((c) => c.monto)].some((x) => casi(x, m.valor)));
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

export function detectarPromesas(texto: string, conocidas: ReadonlySet<number> = new Set(), envio?: RespaldoDeEnvio, preciosProducto: ReadonlySet<number> = new Set()): string[] {
  return [...promesasSinEnvio(texto, conocidas), ...revisarEnvio(texto, envio, preciosProducto)];
}

// ── El envío: cada cifra con su papel y su lugar (revisión adversarial del 2026-11-12, primera y segunda vuelta) ─────────
// Cada oración se parte en cláusulas («;», « y », « pero », « o », y una coma seguida de otro sujeto: «, la cama…»; nunca dentro de un
// paréntesis ni en los dos puntos). En una cláusula que habla del envío, solo cuentan como del envío las cifras y los «gratis» que la
// cláusula le ATRIBUYE al envío: lo que se dice de «la cama», de «el sofá», del «precio» de algo o de «tu cotización» y su total sigue las
// reglas de los productos (segunda vuelta, I-4). Una cifra o un «gratis» del envío solo pasa si la herramienta de envíos de ESTE turno lo
// respalda: con su papel (el precio normal; lo que queda; lo abonado o ahorrado SOLO dicho como ahorro: «te abona $20», «te ahorras $20»,
// «$20 menos»; el mínimo dicho como mínimo; lo que suma la cotización; el total; el desglose), para el lugar que nombra (o el último que
// nombró la oración anterior; un lugar que la herramienta no cotizó no toma el precio de otro) y, con la promoción condicional, con el
// mínimo dicho (no negado) en la misma oración. Y cuando se viene hablando del envío, decir como costo una cifra que es lo abonado o el
// mínimo («pero al final pagas $20») tampoco pasa, salvo que sea el precio de un producto.

const PALABRA_ENVIO =
  /\b(?:envio|envios|flete|fletes|entrega|entregas|domicilio|delivery|deliveries|shipping|despacho|transporte|traslado|traslados|llevamos|llevarlo|llevarla|llevartelo|llevartela|lleven|llevemos|entregamos|despachamos|mandarlo|mandarla|mandartelo|mandartela|mandartelos|mandartelas|mandarselo|mandarsela|mandamos|mandar|mandarte|enviarlo|enviarla|enviartelo|enviartela|enviartelos|enviartelas|enviarselo|enviarsela|enviamos|enviar|enviarte|llevartelos|llevartelas|llevarselo|llevarsela|despachar|sending|deliver|delivering|getting it to)\b/;
/** «Hasta Colón te sale en $20», «hasta La Chorrera»: «hasta» + un nombre propio (no una fecha) también es hablar del envío (N4). */
const HASTA_UN_NOMBRE = /(?<![\p{L}\p{N}])[Hh]asta\s+(?:(?:la|el|los|las|La|El|Los|Las)\s+)?(\p{Lu}[\p{L}'’]*)/gu;
const FECHA_CON_NOMBRE = /^(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre|lunes|martes|miercoles|jueves|viernes|sabado|domingo|navidad|año)$/;
/** Dónde dice «hasta <lugar>» el texto (tal cual, con sus mayúsculas): las posiciones de cada «hasta». */
function hastaUnLugar(original: string): { pos: number; fin: number }[] {
  return [...original.matchAll(HASTA_UN_NOMBRE)].filter((m) => !FECHA_CON_NOMBRE.test(sinAcentos(m[1]))).map((m) => ({ pos: m.index!, fin: m.index! + 5 }));
}
const PALABRA_PROMOCION = /\b(?:promocion|promo|abono|abona|abonamos|regala|regalamos|ahorras|ahorro|descuento|rebaja|gratis|gratuit[oa]|te queda|te quedaria|te sale|te saldria|free|on us|save)\b/;
// Con sus acentos: «tu cama» tiene sujeto propio; «tú pagas» no (sigue hablando del envío).
const SUJETO_PROPIO = /^(?:la|el|los|las|tu|tus|su|sus|mi|mis|este|esta|estos|estas|ese|esa|esos|esas|the|your|my|this|that|these|those)\s+(\S+)/;
const SUJETO_DEL_ENVIO = /^(?:promocion|promo|abono|descuento|rebaja|ahorro|envio|flete|entrega|delivery|shipping|traslado)/;
const CORTES = /\s*;\s*|\s+(?:y|e|pero|o|u|aunque|mientras que|mientras|and|but|or|while)\s+|,\s+(?=(?:la|el|los|las|tu|tus|su|sus|mi|mis|este|esta|estos|estas|ese|esa|the|your|my|this|that)\s)/g;
const GRATIS_DICHO =
  /\b(?:gratis|gratuit[oa]s?|sin costo|sin cargo|no pagas|no te cuesta|no cuesta nada|no tiene costo|por nuestra cuenta|corre por nuestra cuenta|va por cuenta de|por cuenta de d'?casa|lo paga d'?casa|lo pagamos(?: nosotros)?|lo asumimos|lo cubrimos|te lo regala(?:mos)?|te regala(?:mos)? el envio|en cero|cero dolares|free|on us|no charge|at no (?:extra )?cost|won'?t pay|will not pay|don'?t pay|complimentary)\b/;
/** «Flete incluido», «el envío va incluido», «incluye la entrega»: es decir que es gratis (salvo que hable del total: «el total, con el envío incluido»). */
const ENVIO_INCLUIDO = /\b(?:envio|flete|entrega|delivery|shipping|despacho|transporte)\b[^.;]{0,30}?\b(?:incluid[oa]|included)\b|\bincluyen?\s+(?:el|la)\s+(?:envio|entrega|flete|delivery|traslado)\b/;
const HABLA_DEL_TOTAL = /\b(?:total|cotizacion|precio)\b/;
// Qué es cada cifra, por lo que va JUSTO antes (o después): la construcción, no una palabra suelta cerca (segunda vuelta, I-6).
const AHORRO_JUSTO_ANTES =
  /(?:\b(?:abona|abonamos|abonan|ahorras|ahorra|ahorrarias|ahorrar|descontamos|rebajamos|resta|restamos|pone|ponemos|cubre|cubrimos|asume|asumimos|save|saves|saving|cover|covers)|\b(?:abono|ahorro|descuento|rebaja)(?:\s+del?\s+(?:envio|flete)(?:\s+(?:a|hasta|para)(?:\s+[a-z'ñ]+){1,4}?)?)?(?:\s+(?:es|seria|sera|queda|sale|de))?(?:\s+de)?|\b(?:discount|credit)\s+of)\s*(?:\(\s*)?$/;
const AHORRO_DESPUES = /^\s*(?:\+\s*itbms\s*)?(?:menos|mas barato|de descuento|de ahorro|de rebaja|de abono|off|less|cheaper)\b/;
const MINIMO_JUSTO_ANTES =
  /(?:\b(?:mas de|pasa de|pasan de|pase de|supera|superior(?:es)? a|al menos|por lo menos|a partir de|menos de|over|more than|at least|above|minimum(?: of)?)|\bminim[oa](?:\s+\S+){0,4}?\s+(?:es|sera|seria)\s+de|\bminim[oa]\s+de)\s*(?:\(\s*)?$/;
const COMPRA_JUSTO_ANTES = /\b(?:suma|sumas|compra(?:\s+es)?\s+de|cotizacion(?:\s+\S+){0,2}?\s+(?:suma|es de|queda en|sale en))\s*$/;
const TOTAL_ANTES = /\btotal\b/;
/** Una cifra dicha como «$20 de envío», «$20 por el envío», «$20 del envío»: del envío, diga lo que diga antes. */
const DEL_ENVIO_DESPUES = /^\s*(?:\+\s*itbms\s*)?(?:de|del|por el|por la|para el|en)\s+(?:envio|flete|entrega|domicilio|delivery|shipping|traslado)\b/;
/** El mínimo dicho negado («aunque tu compra no pase de $200», «menos de $200»): no es decir la condición (segunda vuelta, M-5). */
const CONDICION_NEGADA = /\b(?:no\s+(?:pase|pasa|llegue|llega|supere|alcance|sea de mas)|aunque|sin importar|menos de|por debajo de|less than|under|below|even if|regardless)\b[^$]*$/;
/** El mínimo dicho como «$200 o más», «desde $200», «a partir de $200»: la regla es MÁS de $200, así que no es decir la condición (tercera
 * vuelta, M-e). */
const CONDICION_INEXACTA_ANTES =
  /\b(?:desde|a partir de|al menos|por lo menos|como minimo|igual o (?:mayor|superior) (?:a|que)|mayor o igual (?:a|que)|at least|from|starting at)\s*(?:\(\s*)?$/;
const CONDICION_INEXACTA_DESPUES = /^\s*(?:\+\s*itbms\s*)?(?:(?:sin|con|before|plus) itbms\s*)?(?:o mas|o superior|o arriba|en adelante|para arriba|or more|or above|and up|and above)\b/;
// Las «anclas»: de qué habla cada parte de la cláusula.
const ANCLA_PROMOCION = /\b(?:promocion|promo|abono|abona|abonamos|ahorro|ahorras|descuento|rebaja|regala|regalamos)\b/g;
const ANCLA_COTIZACION = /\b(?:cotizacion|total|subtotal|compra|compras|pedido|orden|order|purchase)\b/g;
const ANCLA_OTRA = /\b(?:la|el|los|las|un|una|unos|unas|tu|tus|su|sus|este|esta|estos|estas|ese|esa|esos|esas|del|al|the|your|this|that|these|those)\s+([a-zñ]+)|\b(?:retirarlo|retirarla|retiro|retirar|recoger|recogerlo|recogerla|pickup|pick up)\b/g;
/** «La compra», «tu cotización», «el total» dichos como complemento («con tu compra», «por tu compra», «en total»): no son de quién es la
 * cifra (tercera vuelta, B-1 e I-C). */
const COMO_COMPLEMENTO = /\b(?:con|por|sin|para|en|de|del|a|al|segun|desde|hasta|with|for|by|on|in|of)\s+(?:(?:el|la|los|las|tu|tus|su|sus|mi|mis|este|esta|un|una|the|your|this|my)\s+)?$/;
/** Las palabras del costo («tiene un costo de», «la tarifa es», «el monto», «the fee»): no dicen DE QUÉ es la cifra, así que la cifra sigue
 * siendo de lo que se venía nombrando (el envío). Tercera vuelta, B-1. */
const NEUTRALES = new Set([
  ...["costo", "costos", "coste", "valor", "valores", "tarifa", "tarifas", "monto", "montos", "precio", "precios", "cargo", "cargos", "cobro"],
  ...["cobros", "pago", "pagos", "importe", "cuota", "cuotas", "cifra", "cantidad", "cuenta", "suma", "numero", "servicio", "servicios", "viaje"],
  ...["recorrido", "ruta", "camion", "fee", "fees", "cost", "costs", "price", "prices", "rate", "rates", "charge", "charges", "amount", "sum"],
  ...["figure", "service", "trip", "mismo", "misma", "resto", "momento", "dia", "mes", "ano", "año", "final", "vez", "caso", "lugar", "zona"],
  ...["barrio", "tema", "punto", "normal", "neto", "doble", "otro", "otra"],
]);
/** Un producto con nombre («la cama», «el sofá», «the bed»): la cifra que va con él es del producto. Otro sustantivo cualquiera solo se
 * lleva la cifra si es el precio de un producto conocido del turno. */
const PRODUCTO = new RegExp(
  "^(?:" +
    [
      "camas?|sofas?|sofacamas?|muebles?|mesas?|mesitas?|sillas?|sillon(?:es)?|butacas?|combos?|colchon(?:es)?|comedor(?:es)?|juegos?|salas?",
      "seccional(?:es)?|futon(?:es)?|literas?|closets?|roperos?|armarios?|escritorios?|comodas?|peinadoras?|gaveteros?|bancos?|banquetas?",
      "taburetes?|reclinables?|cabeceras?|cunas?|espejos?|lamparas?|alfombras?|repisas?|libreros?|modular(?:es)?|zapateras?|vitrinas?",
      "aparador(?:es)?|recamaras?|almohadas?|productos?|articulos?|modelos?|piezas?|sets?|beds?|couch(?:es)?|tables?|chairs?|mattress(?:es)?",
      "dressers?|desks?|nightstands?|wardrobes?|headboards?|items?|products?|furniture|pieces?",
    ].join("|") +
    ")$",
);
const ENVIO_COMO_COMPLEMENTO = /\b(?:con|sin|mas|ademas de|aparte de|incluid[oa]s?|incluye|plus|with|without)\s+(?:el\s+|la\s+|los\s+|las\s+|tu\s+|su\s+|del\s+)?$/;

type Tema = "envio" | "promocion" | "cotizacion" | "otro";

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
  oraciones: (Tramo & { delEnvio: boolean; siguePorElEnvio: boolean })[];
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

const gratisDicho = (cb: string) => GRATIS_DICHO.test(cb) || (ENVIO_INCLUIDO.test(cb) && !HABLA_DEL_TOTAL.test(cb));

function partirEnClausulas(texto: string): Particion {
  const bajo = bajar(texto);
  const minusculas = texto.toLowerCase();
  // El sujeto propio se mira con los acentos («tu cama» / «tú pagas»); su palabra, sin acentos.
  const sujetoDe = (desde: number, hasta: number) => {
    const s = SUJETO_PROPIO.exec(minusculas.slice(desde, hasta).trimStart());
    return s ? sinAcentos(s[1]) : null;
  };
  const oraciones: Particion["oraciones"] = [];
  const clausulas: Clausula[] = [];
  let anteriorDelEnvio = false;
  oracionesConPosicion(texto).forEach((o, i) => {
    const ob = bajo.slice(o.inicio, o.fin);
    const sujeto = sujetoDe(o.inicio, o.fin);
    // Una oración habla del envío si lo nombra, o si sigue a una que habla del envío y trae la promoción, el abono o «gratis» sin otro sujeto,
    // o si su sujeto es una palabra del costo («El costo final es $20», «La tarifa es de $20»: tercera vuelta, B-1).
    const delEnvio =
      PALABRA_ENVIO.test(ob) ||
      hastaUnLugar(texto.slice(o.inicio, o.fin)).length > 0 ||
      (anteriorDelEnvio && (PALABRA_PROMOCION.test(ob) || gratisDicho(ob)) && (!sujeto || SUJETO_DEL_ENVIO.test(sujeto))) ||
      (anteriorDelEnvio && !!sujeto && NEUTRALES.has(sujeto));
    oraciones.push({ ...o, delEnvio, siguePorElEnvio: anteriorDelEnvio });
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
      // Con sujeto propio, habla del envío si ese sujeto es del envío; una palabra del costo («, la tarifa es $150») no es sujeto propio.
      const propio = s && !NEUTRALES.has(s) ? s : null;
      const deEnvio =
        PALABRA_ENVIO.test(cb) ||
        hastaUnLugar(texto.slice(o.inicio + desde, o.inicio + hasta)).length > 0 ||
        (propio ? SUJETO_DEL_ENVIO.test(propio) : PALABRA_PROMOCION.test(cb) || gratisDicho(cb) || previa);
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

interface Ancla {
  pos: number;
  fin: number;
  tema: Tema;
  /** «Otra cosa» que no es un producto con nombre: solo se lleva la cifra si es el precio de un producto conocido. */
  debil?: boolean;
}

/** De qué habla cada parte de la cláusula: dónde nombra el envío, la promoción, la cotización u otra cosa (un producto). Las palabras del
 * costo («un costo», «la tarifa», «el precio») no son ancla: la cifra sigue siendo de lo que se venía nombrando. */
function anclas(p: Particion, c: Clausula): Ancla[] {
  const cb = p.bajo.slice(c.inicio, c.fin);
  const original = p.texto.slice(c.inicio, c.fin);
  const salida: Ancla[] = [];
  for (const m of cb.matchAll(new RegExp(PALABRA_ENVIO.source, "g"))) {
    // «con el envío», «sin el envío», «más el envío»: el envío como complemento, no como lo que cuesta.
    if (!ENVIO_COMO_COMPLEMENTO.test(cb.slice(0, m.index!))) salida.push({ pos: m.index!, fin: m.index! + m[0].length, tema: "envio" });
  }
  for (const h of hastaUnLugar(original)) salida.push({ ...h, tema: "envio" });
  for (const m of cb.matchAll(ANCLA_PROMOCION)) salida.push({ pos: m.index!, fin: m.index! + m[0].length, tema: "promocion" });
  for (const m of cb.matchAll(ANCLA_COTIZACION)) {
    // «tu cotización suma», «el total es»: sí; «con tu compra», «por tu compra», «en total»: complemento, no es de quién es la cifra.
    if (!COMO_COMPLEMENTO.test(cb.slice(0, m.index!))) salida.push({ pos: m.index!, fin: m.index! + m[0].length, tema: "cotizacion" });
  }
  for (const m of cb.matchAll(ANCLA_OTRA)) {
    const palabra = m[1];
    let debil = false;
    if (palabra !== undefined) {
      const enElTexto = m.index! + m[0].length - palabra.length;
      // Un nombre propio («la Chorrera»), una palabra del costo o algo que ya es ancla (el envío, la promoción, la cotización) no es «otra cosa».
      if (/^\p{Lu}/u.test(original[enElTexto] ?? "") || NEUTRALES.has(palabra)) continue;
      if (PALABRA_ENVIO.test(palabra) || new RegExp(`^(?:${ANCLA_PROMOCION.source})$`).test(palabra) || new RegExp(`^(?:${ANCLA_COTIZACION.source})$`).test(palabra)) continue;
      debil = !PRODUCTO.test(palabra);
    }
    salida.push({ pos: m.index!, fin: m.index! + m[0].length, tema: "otro", debil });
  }
  return salida.sort((a, b) => a.pos - b.pos);
}

/** ¿De qué habla la cifra (o el «gratis») en esa posición? Lo que la nombra justo después («$20 de envío»), o la última ancla antes; si no hay,
 * la que la recibe justo después, sin pausa (un producto o el envío: «$499 + ITBMS la cama», «$20 for the delivery»); si no, el precio de un
 * producto conocido con el envío nombrado aparte («Precio: $499 + ITBMS, entrega a domicilio disponible») es del producto; si no, la
 * cláusula (que habla del envío por su oración). `precioDeProducto`: la cifra es el precio de un producto conocido del turno. */
function temaEn(p: Particion, c: Clausula, inicio: number, fin: number, precioDeProducto = false): Tema {
  const cb = p.bajo.slice(c.inicio, c.fin);
  if (DEL_ENVIO_DESPUES.test(cb.slice(fin, fin + 40))) return "envio";
  const todas = anclas(p, c).filter((a) => !a.debil || precioDeProducto);
  const antes = todas.filter((a) => a.fin <= inicio).at(-1);
  if (antes) return antes.tema;
  const despues = todas.filter((a) => a.pos >= fin);
  const recibe = despues.find((a) => (a.tema === "otro" || a.tema === "envio") && !/[,:;]/.test(cb.slice(fin, a.pos)));
  if (recibe) return recibe.tema;
  if (precioDeProducto && despues.some((a) => a.tema === "envio")) return "otro";
  return c.deEnvio ? "envio" : "otro";
}

/** ¿La cifra en esa posición (dentro de la cláusula) se la atribuye la cláusula al envío? */
function cifraDelEnvio(p: Particion, c: Clausula, inicio: number, fin: number, precioDeProducto = false): boolean {
  if (!c.deEnvio) return false;
  const tema = temaEn(p, c, inicio, fin, precioDeProducto);
  return tema === "envio" || tema === "promocion";
}

/** Los lugares del respaldo que nombra un texto (su nombre, corregimiento o distrito como palabras enteras), con dónde los nombra. */
function nombrados(textoBajo: string, envio: RespaldoDeEnvio): { lugar: LugarDeEnvio; pos: number }[] {
  const salida: { lugar: LugarDeEnvio; pos: number }[] = [];
  for (const lugar of envio.lugares) {
    let pos = -1;
    for (const n of lugar.nombres) {
      if (n.length < 3) continue;
      const m = new RegExp(`(?<![\\p{L}\\p{N}])${escaparRegex(n)}(?![\\p{L}\\p{N}])`, "gu");
      for (const x of textoBajo.matchAll(m)) pos = Math.max(pos, x.index!);
    }
    if (pos >= 0) salida.push({ lugar, pos });
  }
  return salida;
}

/** Los lugares de los que habla la cláusula: los que nombra; si no, los que nombra su oración; si tampoco, el ÚLTIMO que nombró la oración
 * anterior (segunda vuelta, N5); si tampoco, todos. */
function lugaresDe(p: Particion, c: Clausula, envio: RespaldoDeEnvio): readonly LugarDeEnvio[] {
  const enLaClausula = nombrados(p.bajo.slice(c.inicio, c.fin), envio);
  if (enLaClausula.length) return enLaClausula.map((x) => x.lugar);
  const o = p.oraciones[c.oracion];
  const enLaOracion = nombrados(p.bajo.slice(o.inicio, o.fin), envio);
  if (enLaOracion.length) return enLaOracion.map((x) => x.lugar);
  const anterior = p.oraciones[c.oracion - 1];
  if (anterior) {
    const antes = nombrados(p.bajo.slice(anterior.inicio, anterior.fin), envio).sort((a, b) => a.pos - b.pos);
    if (antes.length) return [antes.at(-1)!.lugar];
  }
  return envio.lugares;
}

/** Lo que va después de «a», «para», «hasta», «en» y no es un lugar: «a tu casa», «a domicilio», «en compras», «en cero», «a partir de», «hasta
 * noviembre», «para ti»… (los nombres de los productos, las palabras del envío, del costo y de la promoción tampoco). */
const NO_ES_LUGAR = new Set([
  ...["casa", "hogar", "domicilio", "puerta", "edificio", "apartamento", "apto", "ph", "oficina", "trabajo", "negocio", "local", "tienda"],
  ...["tiendas", "sucursal", "direccion", "area", "sector", "sitio", "cliente", "clientes", "cotizacion", "cotizaciones", "factura", "pdf"],
  ...["compra", "compras", "pedido", "orden", "total", "subtotal", "efectivo", "tarjeta", "credito", "contado", "linea", "partir", "mitad"],
  ...["cero", "cambio", "menos", "mas", "cuanto", "cuando", "que", "quien", "donde", "como", "ti", "usted", "ustedes", "nosotros", "ellos"],
  ...["ella", "ellas", "el", "mi", "si", "eso", "esto", "ello", "todo", "nada", "algo", "hoy", "mañana", "ayer", "luego", "ahora", "siempre"],
  ...["adelante", "fin", "nuevo", "nueva", "tiempo", "hora", "horas", "dias", "semana", "semanas", "meses", "años", "fecha", "aviso"],
  ...["oferta", "stock", "existencia", "existencias", "camino", "serio", "promocion", "promo", "abono", "descuento", "rebaja", "d'casa"],
  ...["dcasa", "itbms", "dolar", "dolares", "balboas", "uno", "una", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve"],
  ...["diez", "once", "doce", "trece", "catorce", "quince", "veinte", "treinta", "cuarenta", "cincuenta", "sesenta", "setenta", "ochenta"],
  ...["noventa", "cien", "ciento", "doscientos", "trescientos", "cuatrocientos", "quinientos", "mil", "todos", "todas", "cualquier"],
  ...["gusto", "mano", "medida", "plazos", "you", "your", "home", "us", "me", "store", "queen", "king", "full", "twin", "llevar", "pagar"],
]);
const HACIA = /(?<![\p{L}\p{N}'’])(a|hasta|para|en|to)\s+/gu;
const DETERMINANTE = /^(?:la|el|los|las|un|una|unos|unas|este|esta|ese|esa|otro|otra|cada|todo|toda|nuestro|nuestra|the|an?)\s+/;
const POSESIVO = /^(?:tu|tus|su|sus|mi|mis|your|my|our)\s/;

/** Un lugar que la cláusula nombra para el envío y que la herramienta no cotizó en este turno (ni con sus otros nombres): su precio o su
 * «gratis» no lo da ningún otro lugar. En cualquier parte de la cláusula («El envío a David», «A David el envío…», «Para David también»,
 * «Te lo mandamos a David»), con o sin mayúscula («a david»); lo que no es un lugar («a tu casa», «a domicilio», «en compras») no cuenta.
 * Segunda vuelta N3; tercera vuelta I-A. */
function lugarNoCotizado(p: Particion, c: Clausula, envio: RespaldoDeEnvio): string | null {
  const original = p.texto.slice(c.inicio, c.fin);
  const cb = p.bajo.slice(c.inicio, c.fin);
  const nombres = envio.lugares.flatMap((l) => l.nombres).filter((n) => n.length >= 3);
  const conocido = (resto: string) => nombres.some((n) => resto.startsWith(n) && !/^[\p{L}\p{N}]/u.test(resto.slice(n.length)));
  for (const m of cb.matchAll(HACIA)) {
    let desde = m.index! + m[0].length;
    if (conocido(cb.slice(desde)) || POSESIVO.test(cb.slice(desde))) continue;
    const det = DETERMINANTE.exec(cb.slice(desde));
    if (det) {
      desde += det[0].length;
      if (conocido(cb.slice(desde))) continue;
    }
    const palabra = /^[\p{L}'’]+/u.exec(cb.slice(desde))?.[0];
    if (!palabra) continue; // «en $70», «hasta el 30 de noviembre», «a la 24 de Diciembre»
    const mayuscula = /^\p{Lu}/u.test(original[desde] ?? "");
    if (m[1] === "to" && !mayuscula) continue; // en inglés, solo un nombre propio («to Chitré»), no «to you», «to pay»
    if (NO_ES_LUGAR.has(palabra) || NEUTRALES.has(palabra) || FECHA_CON_NOMBRE.test(palabra) || PRODUCTO.test(palabra)) continue;
    if (PALABRA_ENVIO.test(palabra) || new RegExp(`^(?:${ANCLA_PROMOCION.source})$`).test(palabra) || PALABRA_PROMOCION.test(palabra)) continue;
    if (!mayuscula && (palabra.length < 3 || /(?:ar|er|ir)$/.test(palabra))) continue; // «a ti», «a pagar», «para recibir»
    return original.slice(desde, desde + palabra.length);
  }
  return null;
}

/** ¿La oración dice el mínimo de la compra de ese lugar (sin negarlo)? Con la promoción condicional, el beneficio solo va con su condición. */
function condicionDicha(l: LugarDeEnvio, oracion: string): boolean {
  if (!l.condicional) return true;
  if (l.minimo === null) return false;
  const bajo = bajar(oracion);
  return extraerMontos(oracion).some((m) => {
    const antes = bajo.slice(Math.max(0, m.inicio - 40), m.inicio);
    return casi(l.minimo, m.valor) && !CONDICION_NEGADA.test(antes) && !CONDICION_INEXACTA_ANTES.test(antes) && !CONDICION_INEXACTA_DESPUES.test(bajo.slice(m.fin, m.fin + 30));
  });
}

type Papel = "ahorro" | "minimo" | "compra" | "total" | "cargo" | "costo";

/** Qué papel tiene la cifra por cómo se dice (lo que va justo antes y justo después). */
function papelDe(antes: string, despues: string, l?: LugarDeEnvio): Papel {
  if (MINIMO_JUSTO_ANTES.test(antes)) return "minimo";
  if (AHORRO_JUSTO_ANTES.test(antes) || AHORRO_DESPUES.test(despues)) return "ahorro";
  if (TOTAL_ANTES.test(antes)) return "total";
  if (COMPRA_JUSTO_ANTES.test(antes)) return "compra";
  if (l && l.cargos.some((c) => c.nombre && antes.includes(sinAcentos(c.nombre)))) return "cargo";
  return "costo";
}

/** ¿Esa cifra, dicha así, es una cifra de ese lugar con el papel correcto? */
function cifraDelLugar(l: LugarDeEnvio, valor: number, antes: string, despues: string, oracion: string, envio: RespaldoDeEnvio): boolean {
  switch (papelDe(antes, despues, l)) {
    case "minimo":
      return casi(l.minimo, valor);
    case "ahorro":
      return casi(l.ahorro, valor) && condicionDicha(l, oracion);
    case "total":
      return casi(envio.total, valor);
    case "compra":
      return casi(l.compra, valor);
    case "cargo":
      return l.cargos.some((c) => antes.includes(sinAcentos(c.nombre)) && casi(c.monto, valor));
    default:
      return casi(l.normal, valor) || (casi(l.final, valor) && condicionDicha(l, oracion));
  }
}

/** Lo que tiene de malo, sobre el envío, cada oración del texto (en el orden de `oraciones()`). */
export function revisarEnvioPorOracion(textoOriginal: string, envio?: RespaldoDeEnvio, preciosProducto: ReadonlySet<number> = new Set()): string[][] {
  const p = partirEnClausulas(textoOriginal.normalize("NFC"));
  const salida: string[][] = p.oraciones.map(() => []);
  const conLugares = Array.isArray(envio?.lugares) && envio.lugares.length > 0;
  for (const c of p.clausulas) {
    const problemas = salida[c.oracion];
    const o = p.oraciones[c.oracion];
    const oracion = p.texto.slice(o.inicio, o.fin);
    const cb = p.bajo.slice(c.inicio, c.fin);
    const montos = extraerMontos(p.texto.slice(c.inicio, c.fin));
    const delEnvio = montos.filter((m) => cifraDelEnvio(p, c, m.inicio, m.fin, cercano(preciosProducto, m.valor)));
    // El «gratis» del envío: dicho en una cláusula del envío y atribuido al envío (no a «retirarlo en la tienda sin costo»).
    const gratisRe = GRATIS_DICHO.exec(cb);
    const gratis =
      c.deEnvio &&
      ((!!gratisRe && ["envio", "promocion"].includes(temaEn(p, c, gratisRe.index, gratisRe.index + gratisRe[0].length))) ||
        (ENVIO_INCLUIDO.test(cb) && !HABLA_DEL_TOTAL.test(cb)) ||
        delEnvio.some((m) => m.valor === 0));
    if (delEnvio.length === 0 && !gratis) {
      // Viniendo de hablar del envío, una cifra que es lo abonado o el mínimo, dicha como costo, es el costo del envío (N1, N2).
      if (conLugares && (o.delEnvio || o.siguePorElEnvio)) {
        for (const m of montos) {
          if (cercano(preciosProducto, m.valor) || temaEn(p, c, m.inicio, m.fin) === "cotizacion") continue;
          const papel = papelDe(cb.slice(Math.max(0, m.inicio - 40), m.inicio), cb.slice(m.fin, m.fin + 24));
          if (papel !== "costo") continue;
          if (envio!.lugares.some((l) => (casi(l.ahorro, m.valor) || casi(l.minimo, m.valor)) && !casi(l.normal, m.valor) && !casi(l.final, m.valor))) problemas.push("costo de entrega");
        }
      }
      continue;
    }
    if (!conLugares) {
      problemas.push(delEnvio.some((m) => m.valor !== 0) ? "costo de entrega" : "entrega o flete gratis");
      continue;
    }
    if (lugarNoCotizado(p, c, envio!)) {
      problemas.push(delEnvio.some((m) => m.valor !== 0) ? "costo de entrega" : "entrega o flete gratis");
      continue;
    }
    const lugares = lugaresDe(p, c, envio!);
    let finAnterior = 0;
    for (const m of montos) {
      const antes = cb.slice(Math.max(finAnterior, m.inicio - 40), m.inicio);
      const despues = cb.slice(m.fin, m.fin + 24);
      finAnterior = m.fin;
      if (m.valor === 0 || !delEnvio.includes(m)) continue; // «$0» es un «gratis»; lo que no es del envío, reglas de producto
      if (!lugares.some((l) => cifraDelLugar(l, m.valor, antes, despues, oracion, envio!))) problemas.push("costo de entrega");
    }
    if (gratis && !lugares.some((l) => l.gratis && condicionDicha(l, oracion))) problemas.push("entrega o flete gratis");
  }
  return salida.map((ps) => [...new Set(ps)]);
}

/** Lo que tiene de malo el texto sobre el envío (cifras o «gratis» que la herramienta de envíos de este turno no respalda). */
export function revisarEnvio(texto: string, envio?: RespaldoDeEnvio, preciosProducto: ReadonlySet<number> = new Set()): string[] {
  return [...new Set(revisarEnvioPorOracion(texto, envio, preciosProducto).flat())];
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

/**
 * Incidente del 2026-11-13: un cliente pidió un colchón y Juan contestó «ahorita solo manejamos la cama, no el colchón solo». Los
 * colchones sí se venden (están en Odoo con su precio) pero no están publicados en la tienda en línea, y el cliente se fue. Cuando una
 * herramienta dijo en el turno que hay productos así sin publicar, decir que no se manejan es falso. Solo se mira con ese respaldo
 * (`haySinPublicar`): sin él, «no lo manejamos» puede ser cierto (la herramienta dijo `no_lo_manejamos`).
 * Una oración que habla de la tienda en línea («no está publicado en la página») o de la etiqueta de existencias («agotado») es cierta
 * y pasa. Se revisa por oración, sobre texto sin acentos y en minúsculas.
 */
const NIEGA_PRODUCTO = [
  /\b(?:no|ya no|tampoco)\s+(?:lo |la |los |las |le |les )?(?:manejamos|trabajamos|vendemos|tenemos|ofrecemos|traemos)\b/,
  /\b(?:solo|solamente|unicamente|nada mas)\s+(?:manejamos|trabajamos|vendemos|tenemos|ofrecemos|traemos)\b/,
  /\bno\s+(?:contamos|disponemos)\s+(?:con|de)\b/,
  /\bwe\s+(?:don['’]?t|do not|no longer)\s+(?:carry|sell|have|offer)\b/,
  /\bwe\s+only\s+(?:carry|sell|have|offer)\b/,
];
const HABLA_DE_LA_TIENDA_EN_LINEA = /\b(?:publicad|en linea|online|en la pagina|en la web|en el sitio|disponib|agotad|existencia|stock|published|website|available|sold out)/;

export function detectarNiegaProducto(texto: string): string[] {
  const hallados: string[] = [];
  for (const o of oraciones(texto)) {
    const t = sinAcentos(o.toLowerCase());
    if (HABLA_DE_LA_TIENDA_EN_LINEA.test(t)) continue;
    const m = NIEGA_PRODUCTO.map((re) => re.exec(t)?.[0]).find((x): x is string => !!x);
    if (m) hallados.push(m);
  }
  return hallados;
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

const VISTO = /[✓✔✅☑]\u{FE0F}?/gu;

/** Una línea como se compara con las de una frase de la tienda: sin espacios de más. */
const lineaComparable = (l: string) => l.replace(/\s+/g, " ").trim();

/**
 * Quita los emojis del texto del modelo, salvo en las líneas que copió tal cual de una frase que Odoo escribió para el cliente en
 * este turno (`frasesDeLaTienda`: los pasos «1️⃣ 2️⃣ 3️⃣» del enlace de ubicación, el 📍 de la pregunta). Esas las escribió la tienda,
 * no el modelo; todo lo demás sigue sin íconos (voz de D'CASA).
 */
function sinEmojis(texto: string, frasesDeLaTienda: readonly string[] = []): string {
  // El «visto» (✓ ✔ ✅ ☑) se quita siempre, también de una frase de Odoo.
  const sinVisto = texto.replace(VISTO, "");
  const deLaTienda = new Set(
    frasesDeLaTienda
      .flatMap((f) => f.replace(VISTO, "").split("\n"))
      .map(lineaComparable)
      .filter((l) => l && new RegExp(EMOJI.source, "u").test(l)),
  );
  if (deLaTienda.size === 0) return sinVisto.replace(EMOJI, "");
  return sinVisto
    .split("\n")
    .map((linea) => (deLaTienda.has(lineaComparable(linea)) ? linea : linea.replace(EMOJI, "")))
    .join("\n");
}

/**
 * Forma: sin emojis, sin signos dobles, sin markdown de documento. WhatsApp usa *un* asterisco.
 * `frasesDeLaTienda`: las líneas que el modelo copia tal cual de una frase de Odoo conservan sus íconos (ver `ContextoRevision`).
 */
export function limpiarForma(texto: string, frasesDeLaTienda?: readonly string[]): string {
  return sinEmojis(texto, frasesDeLaTienda)
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
  let limpio = limpiarForma(borrador, ctx.frasesDeLaTienda);

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
  for (const p of detectarPromesas(limpio, ctx.cifrasConocidas, ctx.envio, ctx.preciosProducto)) graves.push({ tipo: "promesa", detalle: p });
  for (const p of detectarMandaALeer(limpio).slice(0, 1)) graves.push({ tipo: "manda_a_leer", detalle: p });
  for (const p of ctx.escribePersona ? [] : detectarSerHumano(limpio).slice(0, 1)) graves.push({ tipo: "se_hace_pasar_por_persona", detalle: p });
  const prohibida = palabraProhibida(limpio, [...PALABRAS_PROHIBIDAS_DE_MARCA, ...(ctx.palabrasProhibidas ?? [])]);
  if (prohibida) graves.push({ tipo: "palabra_prohibida", detalle: prohibida });
  for (const p of ctx.haySinPublicar ? detectarNiegaProducto(limpio).slice(0, 1) : []) graves.push({ tipo: "niega_producto", detalle: p });

  return { limpio, graves };
}

/** Quita las oraciones que contienen algo grave. Devuelve "" si no queda nada que decir. */
export function quitarGraves(limpio: string, ctx: ContextoRevision): string {
  // El envío se revisa con el texto entero (una oración sigue el tema de la anterior) y se reparte por oración.
  const delEnvio = revisarEnvioPorOracion(limpio, ctx.envio, ctx.preciosProducto);
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
  for (const p of ctx.haySinPublicar ? detectarNiegaProducto(o).slice(0, 1) : []) graves.push({ tipo: "niega_producto", detalle: p });
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
    niega_producto:
      "decir que no manejamos algo que SÍ trabajamos (la herramienta dijo que hay productos así, solo que no están publicados en la tienda en línea: " +
      "di que sí lo trabajamos y que una vendedora le confirma modelos y precios, sin dar ninguno, y pásale la conversación)",
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

