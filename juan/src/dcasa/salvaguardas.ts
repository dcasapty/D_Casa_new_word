// Lo que sale hacia el cliente se revisa SIEMPRE, por código, antes de enviarse. El prompt pide
// bien; esto garantiza lo mínimo aunque el modelo se equivoque o el cliente intente manipularlo
// (docs/JUAN.md, reglas 2, 3, 6 y 11):
//
//   · nunca un precio sin «+ ITBMS»                    → se corrige solo
//   · nunca una cifra de dinero que no salió de una herramienta
//   · nunca un número de existencias
//   · nunca prometer entrega, flete, financiamiento, apartado ni descuento
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

/** Todo precio de producto lleva «+ ITBMS» (decisión del dueño). Se agrega donde falte. */
export function asegurarItbms(texto: string, preciosProducto: ReadonlySet<number>): string {
  const montos = extraerMontos(texto).filter((m) => cercano(preciosProducto, m.valor));
  let salida = texto;
  // De atrás hacia adelante para no mover las posiciones que faltan.
  for (const m of montos.reverse()) {
    if (ITBMS_DESPUES.test(salida.slice(m.fin, m.fin + 24))) continue;
    salida = `${salida.slice(0, m.fin)} + ITBMS${salida.slice(m.fin)}`;
  }
  return salida;
}

// ── Cifras de política: plazos, porcentajes, cuotas ───────────────────────────
// «Los cambios son en 30 días», «2 años de garantía», «10 % de recargo»: si la cifra no salió de una herramienta
// (la base de conocimiento, Socios, el catálogo), es un invento. Lo que escribe el cliente tampoco la respalda.

const CIFRA_DE_POLITICA = /\b(\d+(?:[.,]\d+)?)\s*(?:%|por ciento|dias?|horas?|semanas?|meses|mes|a[nñ]os?|cuotas?|pagos)(?![a-z])/g;

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
const PROMESAS: { r: RegExp; que: string }[] = [
  { r: /\b(?:entrega|envio|flete|delivery|despacho|transporte|instalacion|armado)\s+(?:es\s+|va a ser\s+|seria\s+|sera\s+)?(?:gratis|gratuit[oa]|sin costo|sin cargo|incluid[oa])\b/, que: "entrega o flete gratis" },
  { r: new RegExp(`\\b(?:te|se|le)\\s+(?:lo|la|los|las)?\\s*(?:entregamos|enviamos|mandamos|despachamos|llevamos|instalamos)\\s+(?:hoy|ma[nñ]ana|pasado ma[nñ]ana|en\\s+\\d+|el\\s+${DIA}|esta\\s+semana|ya)\\b`), que: "plazo de entrega" },
  { r: new RegExp(`\\b(?:llega|llegaria|llegara|lo recibes|la recibes|los recibes)\\s+(?:hoy|ma[nñ]ana|en\\s+\\d+|el\\s+${DIA}|esta\\s+semana)\\b`), que: "plazo de entrega" },
  { r: /\b(?:entregamos|enviamos|hacemos entregas?|llevamos)\s+(?:a|en)\s+(?:todo|toda|todas|todos|cualquier)\b/, que: "cobertura de entrega" },
  // El costo y el plazo del envío los confirma una vendedora (regla 3), aunque alguna nota de la tienda los traiga.
  { r: /\b(?:envio|flete|entrega|delivery|despacho|transporte)\b[^.!?\n]{0,40}\b(?:cuesta|cuestan|sale|salen|vale|valen|cobramos|es de|son de|tiene un costo|tiene un cargo|tiene un recargo)\b[^.!?\n]{0,15}(?:\$|\d)/, que: "costo de entrega" },
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
];

/** «20% de descuento» solo es una promesa si el 20 NO salió de una herramienta (p. ej. el catálogo). */
const PORCENTAJE = /\b(\d+(?:[.,]\d+)?)\s*%\s*(?:de\s+)?(?:descuento|menos|off|rebaja)\b|\bdescuento\s+(?:de|del)\s+(\d+(?:[.,]\d+)?)\s*%/g;

export function detectarPromesas(texto: string, conocidas: ReadonlySet<number> = new Set()): string[] {
  const t = sinAcentos(texto);
  const que = PROMESAS.filter(({ r }) => r.test(t)).map((p) => p.que);
  for (const m of t.matchAll(PORCENTAJE)) {
    const n = Number((m[1] ?? m[2]).replace(",", "."));
    if (!cercano(conocidas, n)) que.push("descuento");
  }
  return que;
}

// ── Voz de marca ────────────────────────────────────────────────────────────

/** Siempre prohibidas (CLAUDE.md, regla 6). Las de Odoo se suman. */
export const PALABRAS_PROHIBIDAS_DE_MARCA: readonly string[] = ["remate", "remates", "corre", "corran", "liquidacion total", "ultima oportunidad", "no te lo pierdas"];

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
    if (new RegExp(`(?<![a-z0-9_])${escaparRegex(n)}(?![a-z0-9_])`, "i").test(texto)) return n;
  }
  return ctx.textoDelPrompt ? copiaDelPrompt(texto, ctx.textoDelPrompt) : null;
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

  limpio = asegurarItbms(limpio, ctx.preciosProducto);

  const secreto = secretoRepetido(limpio, ctx);
  if (secreto) graves.push({ tipo: "secreto", detalle: "un dato que el cliente dio en confianza" });

  for (const m of extraerMontos(limpio)) {
    if (!cercano(ctx.cifrasConocidas, m.valor)) {
      graves.push({ tipo: "precio_inventado", detalle: m.texto });
    }
  }
  for (const c of cifrasDePolitica(limpio)) if (!respaldada(ctx, c.valor)) graves.push({ tipo: "cifra_inventada", detalle: c.texto });
  for (const h of detectarExistencias(limpio)) graves.push({ tipo: "existencias", detalle: h });
  for (const p of detectarPromesas(limpio, ctx.cifrasConocidas)) graves.push({ tipo: "promesa", detalle: p });
  const prohibida = palabraProhibida(limpio, [...PALABRAS_PROHIBIDAS_DE_MARCA, ...(ctx.palabrasProhibidas ?? [])]);
  if (prohibida) graves.push({ tipo: "palabra_prohibida", detalle: prohibida });

  return { limpio, graves };
}

/** Quita las oraciones que contienen algo grave. Devuelve "" si no queda nada que decir. */
export function quitarGraves(limpio: string, ctx: ContextoRevision): string {
  const buenas = oraciones(limpio).filter((o) => {
    const { graves } = analizarOracion(o, ctx);
    return graves.length === 0;
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
  for (const p of detectarPromesas(o, ctx.cifrasConocidas)) graves.push({ tipo: "promesa", detalle: p });
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
    palabra_prohibida: "una palabra que la marca no usa",
  };
  const lista = [...new Set(graves.map((g) => `${por[g.tipo]} («${g.detalle}»)`))].join("; ");
  return (
    `Tu borrador anterior NO se envió porque tenía ${lista}. Reescribe la respuesta sin eso: ` +
    "usa solo cifras que devolvieron las herramientas (con «+ ITBMS»), nunca digas cuántas unidades hay, " +
    "y todo lo de entregas, flete, financiamiento, apartados y descuentos queda en «te lo confirma una vendedora». " +
    "Mantén el tuteo, sin emojis, en 2 a 4 líneas."
  );
}

