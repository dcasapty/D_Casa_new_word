// Los bloques de la respuesta de Brian de la tienda (contrato §2) y lo que los arma sin el modelo.
//
//   · Las TARJETAS salen solo de lo que devolvieron buscar_productos / ver_producto en ESE turno: el modelo elige cuáles, por id;
//     el nombre, el precio, la disponibilidad, la imagen y la dirección los pone el Worker con los datos de la herramienta.
//   · `proponer_carrito` solo con un producto ya visto en la sesión, agregable y con una cantidad válida, y solo si el visitante lo
//     pidió o lo confirmó en ese mensaje.
//   · El mensaje de WhatsApp lleva lo del carrito (o lo último que se le mostró), sin datos personales.
//   · `sumar_envio` (A2) solo con un lugar que dio `cotizar_envio` con precio en la sesión, y solo si el visitante lo pidió o dijo
//     que sí; la página le pide a Odoo que ponga la línea del envío (la de `dcasa_envios`, con su promoción). Andrés no suma nada.
//   · `proponer_cambio_carrito` (A4) solo con un producto que YA está en el carrito (lo dice la página), cantidad de 0 a 20 (0 =
//     quitar), y solo si el visitante pidió el cambio en ese mensaje o dijo que sí a la pregunta. La página lo aplica en Odoo.

import { normalizar, sinAcentos } from "../dcasa/texto";
import type { LineaDelCarrito, Pose } from "./prompt";

// ── Tipos de la respuesta ────────────────────────────────────────────────────

export type Disponibilidad = "disponible" | "pocas" | "agotado";

export interface TarjetaDeProducto {
  producto_id: number | null;
  plantilla_id: number | null;
  nombre: string;
  precio_texto: string;
  disponibilidad: Disponibilidad | null;
  imagen: string | null;
  url: string | null;
  agregable: boolean;
}

export type Bloque =
  | { tipo: "texto"; texto: string }
  /** `titulo`: el grupo de la vitrina (A5), la categoría que más se repite entre esas tarjetas (de Odoo), o null. */
  | { tipo: "productos"; productos: TarjetaDeProducto[]; titulo?: string | null }
  | { tipo: "proponer_carrito"; producto_id: number; cantidad: number; nombre: string }
  | { tipo: "proponer_cambio_carrito"; producto_id: number; cantidad: number; nombre: string }
  | { tipo: "sugerencias"; texto: string; opciones: string[] }
  | { tipo: "ubicacion"; texto: string }
  /** `lugar_id`: el lugar de la tabla de envíos que dio `cotizar_envio` (para sumarlo, A2); null si no vino. */
  | { tipo: "envio"; texto: string; lugar: string; lugar_id?: number | null }
  | { tipo: "sumar_envio"; lugar_id: number; lugar: string }
  /** La tarjeta del carrito con su cotización: la pinta la página con los números de Odoo. */
  | { tipo: "carrito" }
  | { tipo: "whatsapp"; texto: string; mensaje: string }
  | { tipo: "calificar" };

export interface RespuestaTienda {
  ok: true;
  pose: Pose;
  bloques: Bloque[];
  chips: string[];
}

export const TEXTO_DEL_BOTON_DE_WHATSAPP = "Escríbenos por WhatsApp";
export const TEXTO_DE_UBICACION = "¿A dónde te lo llevamos?";
export const MAX_TARJETAS = 6;
export const MAX_CHIPS = 4;
export const MAX_OPCIONES = 3;
const MAX_LARGO_DE_OPCION = 40;

// ── Productos que devolvieron las herramientas ───────────────────────────────

/** Un producto tal como lo recuerda la sesión (lo devolvió una herramienta). Datos del catálogo, nada del visitante. */
export interface ProductoVisto {
  producto_id: number | null;
  plantilla_id: number | null;
  codigo: string;
  nombre: string;
  precio_texto: string;
  disponibilidad: Disponibilidad | null;
  imagen: string | null;
  url: string | null;
  agregable: boolean;
  /** Palabras de sus categorías y su nombre, para elegir la pose (cama, cocina…). */
  categorias: string[];
}

const esObjeto = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
const entero = (v: unknown): number | null => (typeof v === "number" && Number.isInteger(v) && v > 0 ? v : null);
const texto = (v: unknown, max: number): string => (typeof v === "string" ? v.replace(/[\u0000-\u001f\u007f]+/g, " ").replace(/\s+/g, " ").trim().slice(0, max) : "");

/**
 * Una dirección para la página: relativa al mismo sitio («/shop/…», «/web/image/…»). Una absoluta de uno de los sitios conocidos se
 * vuelve relativa; cualquier otra cosa (otro dominio, «//», «javascript:») no se usa.
 */
export function rutaDelSitio(v: unknown, hosts: readonly string[]): string | null {
  if (typeof v !== "string") return null;
  const t = v.trim();
  if (!t) return null;
  if (t.startsWith("/") && !t.startsWith("//") && !/[\s<>"'\\]/.test(t)) return t.slice(0, 500);
  try {
    const u = new URL(t);
    if (u.protocol !== "https:" || !hosts.includes(u.host.toLowerCase())) return null;
    const ruta = `${u.pathname}${u.search}`;
    return ruta.startsWith("/") && !ruta.startsWith("//") ? ruta.slice(0, 500) : null;
  } catch {
    return null;
  }
}

function disponibilidadDe(v: unknown): Disponibilidad | null {
  return v === "disponible" || v === "pocas" || v === "agotado" ? v : null;
}

/** Los productos de UN resultado de buscar_productos (su lista) o de ver_producto (la ficha; tolera `{producto: {...}}`). */
export function productosDelResultado(herramienta: string, resultado: unknown, hosts: readonly string[]): ProductoVisto[] {
  if (!esObjeto(resultado)) return [];
  let crudos: unknown[] = [];
  if (herramienta === "buscar_productos" && Array.isArray(resultado.productos)) crudos = resultado.productos;
  else if (herramienta === "ver_producto") crudos = [esObjeto(resultado.producto) ? resultado.producto : resultado];
  const salida: ProductoVisto[] = [];
  for (const c of crudos) {
    if (!esObjeto(c)) continue;
    const nombre = texto(c.nombre, 120);
    const codigo = texto(c.codigo, 40);
    const producto_id = entero(c.producto_id);
    if (!nombre || (!codigo && producto_id === null)) continue;
    const precio_texto = texto(c.precio_texto, 60);
    salida.push({
      producto_id,
      plantilla_id: entero(c.plantilla_id),
      codigo,
      nombre,
      precio_texto,
      disponibilidad: disponibilidadDe(c.disponibilidad),
      imagen: rutaDelSitio(c.imagen, hosts) ?? rutaDelSitio(c.foto, hosts),
      url: rutaDelSitio(c.ruta, hosts) ?? rutaDelSitio(c.url, hosts),
      // Solo con el «sí» de Odoo y un id que agregar: sin eso la tarjeta lleva a la ficha.
      agregable: c.agregable === true && producto_id !== null && !!precio_texto,
      categorias: Array.isArray(c.categorias) ? c.categorias.map((x) => texto(x, 60)).filter(Boolean).slice(0, 6) : [],
    });
  }
  return salida;
}

/** La clave con la que la sesión recuerda un producto: su id si lo tiene; si no, su código. */
export function claveDeProducto(p: Pick<ProductoVisto, "producto_id" | "codigo">): string {
  return p.producto_id !== null ? `id:${p.producto_id}` : `codigo:${p.codigo.toUpperCase()}`;
}

/** Busca lo que el modelo eligió (un número = producto_id; un texto = código, o un número escrito) entre los productos dados. */
export function buscarProducto(ref: unknown, productos: Iterable<ProductoVisto>): ProductoVisto | null {
  const lista = [...productos];
  if (typeof ref === "number" && Number.isInteger(ref)) return lista.find((p) => p.producto_id === ref) ?? null;
  if (typeof ref === "string" && ref.trim()) {
    const t = ref.trim();
    if (/^\d{1,10}$/.test(t)) {
      const n = Number(t);
      const porId = lista.find((p) => p.producto_id === n);
      if (porId) return porId;
    }
    return lista.find((p) => p.codigo && p.codigo.toUpperCase() === t.toUpperCase()) ?? null;
  }
  return null;
}

export function tarjetaDe(p: ProductoVisto): TarjetaDeProducto {
  return {
    producto_id: p.producto_id,
    plantilla_id: p.plantilla_id,
    nombre: p.nombre,
    precio_texto: p.precio_texto,
    disponibilidad: p.disponibilidad,
    imagen: p.imagen,
    url: p.url,
    agregable: p.agregable,
  };
}

// ── Lo que quiere el visitante (sin el modelo) ──────────────────────────────

/**
 * ¿Pidió o confirmó poner algo en el carrito en ESTE mensaje? Sin eso, `proponer_carrito` no sale (el modelo no puede decidir por el
 * visitante): se le pregunta primero. Conservador a propósito: preguntar de más no molesta; agregar sin permiso, sí.
 */
export function pideOConfirmaCarrito(textoDelVisitante: string): boolean {
  const t = ` ${normalizar(textoDelVisitante)} `;
  if (!t.trim()) return false;
  if (/ (no|nada|todavia no|aun no|mejor no|ahorita no) (gracias |quiero |lo |la |me )?/.test(t) && !/ (si|dale|claro) /.test(t)) return false;
  return /( si | sip | dale | claro | ok | okay | perfecto | de una | yes | sure | add | agrega| agregue| agregar| a[nñ]ade| a[nñ]adi| pon(lo|la|los|las|me|melo|mela|melos|melas)? | poner | me (lo|la|los|las) llevo | (lo|la|los|las) quiero | (lo|la|los|las) compro | comprar)/.test(t);
}

/** Un «sí» corto a una pregunta de Brian («¿Te lo pongo en el carrito?»): se resuelve sin el modelo. */
export function esUnSi(textoDelVisitante: string): boolean {
  const t = normalizar(textoDelVisitante);
  return /^(si|sip|si por favor|si porfa|dale|ok|okay|claro|claro que si|perfecto|de una|yes|sure|si gracias|si ponlo|si ponla|si agregalo|si agregala|ponlo|ponla|agregalo|agregala|si ponlo en el carrito|si ponla en el carrito|ponlo en el carrito|ponla en el carrito|si agregalo al carrito|agregalo al carrito)$/.test(t);
}

/**
 * A2. ¿Pide en ESTE mensaje sumar el envío a su cotización o a su carrito? («súmale el envío», «súmalo a la cotización», «agrégale el
 * envío», «inclúyelo»). Un «sí» corto a la pregunta «¿Te lo sumo a la cotización?» lo resuelve `esUnSi`.
 */
export function pideSumarEnvio(textoDelVisitante: string): boolean {
  const t = ` ${normalizar(textoDelVisitante)} `;
  if (!t.trim() || / no (me )?(lo |la )?(sumes|agregues|incluyas|pongas|metas) /.test(t)) return false;
  if (/ (sumale|sumalo|sumala|sumamelo|sumamela|sumelo|sumele|sumarlo|sumarle|sumarmelo|sumamelo) /.test(t)) return true;
  if (/ (suma|sumar|sumas|sumes|sumarias) (el |ese |eso |lo |la )?(envio|flete|eso|delivery) /.test(t)) return true;
  if (/ (lo|la|me lo|me la) (sumas|sumarias|puedes sumar|podrias sumar) /.test(t)) return true;
  if (/ cotizacion con (el )?(envio|flete) | con (el )?(envio|flete) (incluido|sumado) /.test(t)) return true;
  return / (agrega|agregale|agregalo|anade|anadele|anadelo|incluye|incluyelo|incluyele|ponle|pon|mete|metele) (?:\S+ ){0,3}(envio|flete|delivery) /.test(t);
}

/**
 * A4. ¿Pide en ESTE mensaje cambiar la cantidad de algo del carrito o quitarlo? («quita la cama», «déjame solo uno», «mejor dos»,
 * «ya no quiero el colchón», «uno menos»). Conservador: sin uno de estos verbos, el modelo solo puede preguntar.
 */
export function pideCambiarCarrito(textoDelVisitante: string): boolean {
  const t = ` ${normalizar(textoDelVisitante)} `;
  if (!t.trim()) return false;
  return /( quita| quitale| quitalo| quitala| quitalos| quitar| saca| sacalo| sacala| sacar| elimina| eliminalo| eliminala| borra| borralo| borrala| remueve| cambia| cambialo| cambiala| cambiame| deja | dejame| dejalo| dejala| baja | bajale| sube | subele| reduce| aumenta| ya no (lo |la |los |las )?quiero| no (lo |la )?quiero| mejor (solo |nada mas )?(un|una|uno|dos|tres|cuatro|cinco|\d+) | solo (un|una|uno|dos|tres|cuatro|cinco|\d+) | (uno|una|otro|otra) (mas|menos) | ponme (solo |nada mas )?(un|una|uno|dos|tres|cuatro|cinco|\d+) | en vez de )/.test(t);
}

/** ¿Pide ver su carrito o la cotización? («dame la cotización», «¿qué tengo en el carrito?»). La página pinta la tarjeta. */
export function pideVerCarrito(textoDelVisitante: string): boolean {
  const t = ` ${normalizar(textoDelVisitante)} `;
  return /( cotizacion | cotizame | cotizarme | presupuesto | el pdf | ver (mi|el) carrito | mi carrito | que tengo en el carrito )/.test(t);
}

/**
 * El título del grupo de la vitrina (A5): la categoría (de Odoo) que más se repite entre las tarjetas de ESE turno; con empate, la
 * de la primera tarjeta. Sin categorías, null (la página usa lo que pidió el visitante).
 */
export function tituloDelGrupo(productos: readonly Pick<ProductoVisto, "categorias">[]): string | null {
  const cuenta = new Map<string, number>();
  for (const p of productos) for (const c of new Set(p.categorias.map((x) => x.trim()).filter(Boolean))) cuenta.set(c, (cuenta.get(c) ?? 0) + 1);
  let mejor: string | null = null;
  for (const [c, n] of cuenta) if (mejor === null || n > (cuenta.get(mejor) ?? 0)) mejor = c;
  return mejor ? mejor.replace(/[<>{}\[\]]/g, "").slice(0, 40) || null : null;
}

/** Un «no» corto a esa misma pregunta. */
export function esUnNo(textoDelVisitante: string): boolean {
  const t = normalizar(textoDelVisitante);
  return /^(no|no gracias|nop|ahorita no|todavia no|mejor no|no por ahora|por ahora no|no thanks|no thank you)$/.test(t);
}

// ── Lo que el modelo no puede decir en la tienda ────────────────────────────

/**
 * «Te lo puse en el carrito», «ya está en tu carrito», «lo agregué»: el modelo NUNCA pone nada en el carrito (lo hace el navegador con
 * Odoo y avisa). Solo el turno en que Odoo confirmó, y con el texto del Worker, se dice. Se revisa por oración, sin acentos.
 */
const AFIRMA_CARRITO = [
  /\b(?:te |ya )?(?:lo|la|los|las) (?:puse|agregue|a[nñ]adi|meti)\b/,
  /\bte (?:puse|agregue|a[nñ]adi|meti|deje) (?:\S+ ){0,6}en (?:el|tu) carrito\b/,
  /\bya (?:esta|estan|quedo|quedaron|lo tienes|la tienes|los tienes|las tienes) en (?:el|tu) carrito\b/,
  /\b(?:agregad[oa]s?|a[nñ]adid[oa]s?|puest[oa]s?) (?:a|al|en) (?:el |tu )?carrito\b/,
  /\bi (?:added|put) (?:it|them)\b/,
  /\b(?:added|is now) (?:to|in) your cart\b/,
  // Quitar del carrito, cambiar la cantidad o sumar el envío (A2, A4): tampoco lo hace el modelo; lo confirma Odoo y lo dice
  // el Worker (revisión adversarial, 2026-11-16: «agregué / incluí / cambié / retiré», «el envío ya está en tu cotización»).
  /\b(?:te |ya )?(?:lo|la|los|las) (?:quite|saque|sume|borre|elimine|retire)\b/,
  /\b(?:quite|saque|borre|elimine|retire) (?:\S+ ){0,6}del carrito\b/,
  /\b(?:deje|cambie) (?:\S+ ){0,6}(?:en|del) (?:el |tu )?carrito\b/,
  /\b(?:sume|agregue|a[nñ]adi|inclui|puse|meti) (?:\S+ ){0,3}(?:envio|flete)\b/,
  /\b(?:cambie|actualice|ajuste|deje|baje|subi) (?:\S+ ){0,3}(?:cantidad|cantidades)\b/,
  /\b(?:envio|flete)\b(?: \S+){0,3} (?:esta|estan|quedo|queda) (?:sumad[oa]|incluid[oa]|agregad[oa]|puest[oa]|en (?:tu|la) (?:cotizacion|carrito))\b/,
  /\bya (?:lo|la|los|las) tienes (?:sumad[oa]s?|incluid[oa]s?|agregad[oa]s?|en (?:tu|la) cotizacion)\b/,
];

/**
 * ¿Esta oración dice que algo YA se hizo en el carrito o en la cotización? Lo que se pregunta no se afirma: se mira solo lo que va
 * antes del «¿» (así «Ya te lo puse en el carrito, ¿algo más?» sí cuenta), una oración sin «¿» que termina en «?» es una pregunta,
 * y una cláusula en subjuntivo («¿Quieres que te lo quite…?», «que la saque») no es una confirmación.
 */
export function afirmaCarrito(oracion: string): boolean {
  let t = sinAcentos(oracion.toLowerCase()).trim();
  const pregunta = t.indexOf("¿");
  if (pregunta >= 0) t = t.slice(0, pregunta);
  else if (/\?\s*$/.test(t)) return false;
  t = t.replace(/\bque (?:te |me |se )?(?:lo|la|los|las) \S+/g, "que");
  return AFIRMA_CARRITO.some((r) => r.test(t));
}

/** «Hola, soy Andrés…» al empezar: la página ya lo presentó (contrato, «Voz»). Se quita esa primera frase. También
 * «soy Brian», el nombre que tuvo hasta el 2026-11-15 (Brian es ahora solo el asistente del panel). */
export function sinPresentacion(textoDelModelo: string): string {
  return textoDelModelo.replace(/^\s*(?:¡\s*)?(?:hola|buenas|buenos dias|buenas tardes|buenas noches)[\s,!.¡]*(?:,\s*)?soy (?:andr[eé]s|brian)\b[^.!?\n]*[.!?]?\s*/i, "").trim();
}

/** Una opción o un chip: corto, de una línea, sin enlaces. */
export function opcionCorta(v: unknown): string {
  const t = texto(v, MAX_LARGO_DE_OPCION + 1);
  if (!t || t.length > MAX_LARGO_DE_OPCION || /https?:|www\./i.test(t)) return "";
  return t;
}

// ── WhatsApp ─────────────────────────────────────────────────────────────────

/**
 * El mensaje que va prellenado en wa.me (el número lo pone la página desde el ajuste de Odoo). Lleva lo del carrito si hay; si no, lo
 * último que Brian le mostró. Nunca datos personales: los nombres del carrito vienen de la página y se recortan y se limpian.
 */
export function mensajeDeWhatsapp(carrito: readonly LineaDelCarrito[], vistos: readonly Pick<ProductoVisto, "nombre">[]): string {
  const limpio = (t: string) => t.replace(/https?:\/\/\S+|www\.\S+/gi, "").replace(/[<>{}\[\]]/g, "").replace(/\s+/g, " ").trim().slice(0, 60);
  const base = "Hola, vengo del chat de la web";
  const delCarrito = carrito.map((l) => ({ n: limpio(l.nombre), c: l.cantidad })).filter((l) => l.n).slice(0, 5);
  if (delCarrito.length) return `${base}. Tengo en el carrito: ${delCarrito.map((l) => `${l.c} × ${l.n}`).join("; ")}.`.slice(0, 400);
  const nombres = [...new Set(vistos.map((v) => limpio(v.nombre)).filter(Boolean))].slice(-2);
  if (nombres.length) return `${base}: me interesa ${nombres.join(" y ")}.`.slice(0, 400);
  return `${base}.`;
}

// ── La pose del robot ────────────────────────────────────────────────────────

export interface SenalesDePose {
  bloques: readonly Bloque[];
  herramientas: readonly string[];
  noche: boolean;
  /** La pose que pidió el modelo, si es una de las 16. */
  delModelo: Pose | null;
  textoDelVisitante: string;
  productos: readonly ProductoVisto[];
  agradecimiento?: boolean;
}

/** Una pose según lo que lleva la respuesta (las acciones mandan; si no, la del modelo; si no, una que acompañe). */
export function elegirPose(s: SenalesDePose): Pose {
  const hay = (tipo: Bloque["tipo"]) => s.bloques.some((b) => b.tipo === tipo);
  if (hay("calificar")) return "cinco_estrellas";
  if (hay("proponer_carrito") || hay("proponer_cambio_carrito") || hay("sumar_envio") || hay("carrito")) return "bolsita";
  if (hay("envio") || hay("ubicacion")) return "mapa";
  if (hay("whatsapp")) return s.noche ? "durmiendo" : "burbuja_chat";
  if (s.agradecimiento) return "corazon";
  if (s.delModelo) return s.delModelo;
  if (s.herramientas.includes("reglas_socios")) return "fidelidad";
  if (s.herramientas.includes("horario_y_tienda")) return "escritorio";
  if (/\b(mide|miden|medida|medidas|cabe|caben|espacio)\b/.test(sinAcentos(s.textoDelVisitante.toLowerCase()))) return "cinta_metrica";
  if (hay("productos")) {
    const palabras = sinAcentos(s.productos.flatMap((p) => [p.nombre, ...p.categorias]).join(" ").toLowerCase());
    if (/\b(colchon|colchones|cama|camas|base|bases|almohada)/.test(palabras)) return "cama";
    if (/\b(cocina|comedor|comedores|mesa|mesas|silla|sillas|desayunador)/.test(palabras)) return "cocina";
    if (/\b(cuadro|cuadros|marco|espejo|decoracion)/.test(palabras)) return "marco_foto";
    return "con_laptop";
  }
  if (hay("sugerencias")) return "busto_estrella";
  return "asomado_burbuja";
}
