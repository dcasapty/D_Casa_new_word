// Las herramientas del modelo = las de Odoo (docs/JUAN.md): el Worker pide la lista
// (`GET /herramientas`), se la pasa al modelo tal cual y ejecuta con `POST /herramienta`.
// Además, una local: `enviar_foto_producto(codigo)`.
//
// Todo lo que vuelve de Odoo pasa por `procesarResultado` antes de llegar al modelo:
//   · se quita cualquier número de existencias (el modelo solo conoce la etiqueta);
//   · se agrega `precio_texto` («$499.00 + ITBMS») para que copie el precio ya correcto;
//   · se anotan los precios y cifras conocidas (la guardia de salida las usa para rechazar inventos);
//   · se recuerdan las fotos que devolvió `ver_producto`, que son las únicas que `enviar_foto_producto` puede enviar.

import { jsonSchema, tool, type ToolSet } from "ai";
import type { DefHerramienta, OdooApi } from "../odoo/cliente";
import type { MedioSaliente } from "../canales/tipos";
import { extraerMontos, parseMonto } from "../dcasa/salvaguardas";

/** Lo que se aprende durante UN turno del modelo. */
export class RegistroDelTurno {
  /** Precios de producto vistos (llevan «+ ITBMS»). */
  readonly preciosProducto = new Set<number>();
  /** Toda cifra respaldada por una herramienta. */
  readonly cifras = new Set<number>();
  /** Números que aparecen escritos dentro del texto de un resultado («cambios dentro de 8 días»): respaldan plazos y porcentajes. */
  readonly numerosEnTexto = new Set<number>();
  readonly fotos = new Map<string, { url: string; nombre?: string }>();
  readonly medios: MedioSaliente[] = [];
  readonly llamadas: { nombre: string; ok: boolean }[] = [];
  pasoAVendedora = false;
  textoDeVendedora: string | null = null;
  readonly pines: string[] = [];
  /** buscar_conocimiento sin respuesta (vacía o floja). */
  busquedasFlojas = 0;
  /** Consultas que SÍ trajeron algo útil (conocimiento, Socios, horario, catálogo con resultados). */
  consultasUtiles = 0;
  /** El modelo ya llamó registrar_pregunta_sin_respuesta en este turno. */
  preguntaRegistrada = false;
}

/** Herramientas de LECTURA: dan lo mismo para los mismos argumentos durante un rato, así que se guardan 60 s. Nunca saldo_puntos ni las de escritura. */
export const HERRAMIENTAS_DE_LECTURA: ReadonlySet<string> = new Set([
  "buscar_productos",
  "ver_producto",
  "listar_categorias",
  "reglas_socios",
  "horario_y_tienda",
  "buscar_conocimiento",
]);

export interface CacheDeHerramientas {
  obtener(clave: string): unknown | undefined;
  guardar(clave: string, valor: unknown): void;
}

/** Argumentos con las llaves ordenadas: {a,b} y {b,a} son la misma consulta. */
export function argumentosEstables(v: unknown): string {
  if (Array.isArray(v)) return `[${v.map(argumentosEstables).join(",")}]`;
  if (v && typeof v === "object") {
    return `{${Object.keys(v as object)
      .sort()
      .map((k) => `${JSON.stringify(k)}:${argumentosEstables((v as Record<string, unknown>)[k])}`)
      .join(",")}}`;
  }
  return JSON.stringify(v) ?? "null";
}

/**
 * ¿La búsqueda en la base de conocimiento salió floja? Sin resultados, `encontrado: false` o una puntuación baja.
 * (El CRM de Baby Caleb subía al modelo inteligente cuando `lastSearchKbScore < 0.5`.) Tolera la forma exacta que mande Odoo.
 */
export function busquedaFlojaDe(resultado: unknown): boolean {
  if (resultado === null || resultado === undefined) return true;
  if (Array.isArray(resultado)) return resultado.length === 0;
  if (typeof resultado === "string") return resultado.trim().length === 0;
  if (!esObjeto(resultado)) return false;
  if (resultado.encontrado === false || resultado.sin_resultados === true) return true;
  for (const k of ["resultados", "fragmentos", "documentos", "items", "resultado", "articulos"]) {
    const lista = resultado[k];
    if (Array.isArray(lista)) {
      if (lista.length === 0) return true;
      const puntos = lista.map((x) => (esObjeto(x) ? [x.score, x.puntaje, x.similitud, x.relevancia].find((n) => typeof n === "number") : undefined)).filter((n): n is number => typeof n === "number");
      return puntos.length > 0 && Math.max(...puntos) < 0.5;
    }
  }
  return false;
}

const CLAVES_DE_EXISTENCIAS = /^(existencias?|stock|qty_available|free_qty|virtual_available|incoming_qty|outgoing_qty|cantidad(_disponible)?|unidades(_disponibles)?|inventario|disponible_cantidad|en_bodega|saldo_stock)$/i;
const CLAVES_DE_PRECIO = /precio|price|importe/i;
const CLAVES_DE_FOTO = ["foto", "foto_url", "imagen", "imagen_url", "image", "image_url", "url_foto", "url_imagen"];
const CLAVES_DE_URL = /^(url|foto|imagen|image|galeria|enlace|link)|(_url|_foto|_imagen)$/i;
const CLAVES_SIN_CIFRAS = /(^|_)(id|ids|conversacion_id|partner_id|product_id|template_id)$/i;

const esObjeto = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
const aTexto = (v: unknown) => (typeof v === "string" ? v : "");

export function formatearPrecio(n: number): string {
  return `$${n.toFixed(2)}`;
}

export function resolverUrl(url: string, sitio: string | undefined): string | null {
  const u = url.trim();
  if (/^https:\/\//i.test(u)) return u;
  if (u.startsWith("/") && !u.startsWith("//") && sitio) return `${sitio.replace(/\/$/, "")}${u}`;
  return null;
}

/** Recorre el resultado: quita existencias, agrega `precio_texto`, recoge cifras y fotos. Devuelve una copia. */
export function procesarResultado(valor: unknown, reg: RegistroDelTurno, sitio: string | undefined, clave = "", enPrecio = false): unknown {
  if (Array.isArray(valor)) return valor.map((v) => procesarResultado(v, reg, sitio, clave, enPrecio));

  if (typeof valor === "number") {
    if (Number.isFinite(valor) && !CLAVES_SIN_CIFRAS.test(clave)) {
      reg.cifras.add(valor);
      if (enPrecio) reg.preciosProducto.add(valor);
    }
    return valor;
  }

  if (typeof valor === "string") {
    for (const m of extraerMontos(valor)) {
      reg.cifras.add(m.valor);
      if (enPrecio) reg.preciosProducto.add(m.valor);
    }
    // Direcciones de fotos y rutas llevan números que no son datos (ids): no cuentan.
    if (!CLAVES_DE_URL.test(clave) && !/^(?:https?:)?\/|^data:/i.test(valor.trim())) for (const n of cifrasDeTexto(valor)) reg.numerosEnTexto.add(n);
    return valor;
  }

  if (!esObjeto(valor)) return valor;

  const salida: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(valor)) {
    // El modelo nunca ve un número de existencias, aunque Odoo lo mande por error.
    if (CLAVES_DE_EXISTENCIAS.test(k) && (typeof v === "number" || (typeof v === "string" && /^\s*\d+([.,]\d+)?\s*$/.test(v)))) continue;
    salida[k] = procesarResultado(v, reg, sitio, k, enPrecio || CLAVES_DE_PRECIO.test(k));
  }

  // Un producto: código + foto. Es lo único que `enviar_foto_producto` puede mandar.
  const codigo = aTexto(valor.codigo).trim();
  if (codigo) {
    let url: string | null = null;
    for (const c of CLAVES_DE_FOTO) {
      if (typeof valor[c] === "string") {
        url = resolverUrl(valor[c] as string, sitio);
        if (url) break;
      }
    }
    if (!url && Array.isArray(valor.galeria)) {
      for (const g of valor.galeria) {
        const cand = typeof g === "string" ? g : esObjeto(g) ? aTexto(g.url) : "";
        url = cand ? resolverUrl(cand, sitio) : null;
        if (url) break;
      }
    }
    if (url) reg.fotos.set(codigo.toUpperCase(), { url, nombre: aTexto(valor.nombre) || undefined });
  }

  // «$499.00 + ITBMS» ya armado, para que el modelo lo copie en vez de escribirlo.
  const precio = valor.precio;
  if (typeof precio === "number" && Number.isFinite(precio) && valor.mas_itbms !== false && salida.precio_texto === undefined) {
    salida.precio_texto = `${formatearPrecio(precio)} + ITBMS`;
    reg.preciosProducto.add(precio);
  }
  return salida;
}

const LIMITE_JSON = 20_000;

/** Un resultado enorme no cabe en el contexto: se recortan las listas más largas. */
export function acotar(valor: unknown): unknown {
  let actual = valor;
  for (let i = 0; i < 8 && JSON.stringify(actual).length > LIMITE_JSON; i++) {
    actual = recortarLaMasLarga(actual);
  }
  return actual;
}

function recortarLaMasLarga(v: unknown): unknown {
  if (Array.isArray(v)) return v.length > 1 ? v.slice(0, Math.ceil(v.length / 2)) : v;
  if (!esObjeto(v)) return v;
  let mayor: string | null = null;
  let largo = -1;
  for (const [k, x] of Object.entries(v)) {
    const l = Array.isArray(x) || esObjeto(x) ? JSON.stringify(x).length : 0;
    if (l > largo) {
      largo = l;
      mayor = k;
    }
  }
  if (mayor === null) return v;
  return { ...v, [mayor]: recortarLaMasLarga(v[mayor]) };
}

export interface OpcionesHerramientas {
  odoo: OdooApi;
  defs: DefHerramienta[];
  conversacionId: () => number | null;
  registro: RegistroDelTurno;
  sitio?: string;
  /** Celular de la conversación (WhatsApp): `saldo_puntos` solo se consulta con ese. */
  celularDeLaConversacion?: string;
  /** Fotos de turnos anteriores (código → url). */
  fotoPrevia: (codigo: string) => { url: string; nombre?: string } | undefined;
  /** true = Odoo no contesta en esta pasada: las herramientas fallan al instante en vez de esperar. */
  omitir?: () => boolean;
  /** Caché de 60 s de las herramientas de LECTURA (solo de esta conversación). */
  cache?: CacheDeHerramientas;
  /** Quién es esta conversación (`canal:id`): va en la clave de la caché, para que jamás se mezclen datos de dos personas. */
  identidad?: string;
  /** Se llama justo antes de preguntarle a Odoo (para mostrar «escribiendo…» mientras tanto). */
  alEmpezar?: () => void;
}

const MAX_FOTOS_POR_RESPUESTA = 3;

/** Extrae el texto que `pasar_a_vendedora` pide decirle al cliente. */
export function textoDeLaHerramienta(resultado: unknown): string | null {
  if (typeof resultado === "string") return resultado.trim() || null;
  if (!esObjeto(resultado)) return null;
  // `texto_para_el_cliente` es la clave que publica Odoo (addons/dcasa_conversaciones, `_pasar_a_vendedora`); las demás, por tolerancia.
  for (const k of ["texto_para_el_cliente", "texto", "mensaje", "texto_para_cliente", "texto_cliente", "decir", "respuesta", "texto_sugerido"]) {
    const v = resultado[k];
    if (typeof v === "string" && v.trim()) return v.trim();
  }
  return null;
}

/** Procesa el resultado para el modelo y anota si la consulta sirvió o salió floja. */
function anotarConsulta(nombre: string, resultado: unknown, reg: RegistroDelTurno, sitio: string | undefined): unknown {
  if (nombre === "buscar_conocimiento" && busquedaFlojaDe(resultado)) {
    reg.busquedasFlojas++;
    // Sin respuesta en la base de conocimiento: el modelo recibe la orden de NO improvisar, junto con lo poco que haya salido.
    return {
      sin_respuesta: true,
      instruccion:
        "La base de conocimiento no tiene respuesta para esto. NO la inventes ni la deduzcas por parecido. Dile al cliente que una vendedora lo confirma, " +
        "llama a registrar_pregunta_sin_respuesta con su pregunta y, si hay interés de compra, también a crear_oportunidad.",
      detalle: procesarResultado(resultado, reg, sitio),
    };
  }
  if (HERRAMIENTAS_DE_LECTURA.has(nombre) && !(nombre === "buscar_productos" && busquedaFlojaDe(resultado))) reg.consultasUtiles++;
  return procesarResultado(resultado, reg, sitio);
}

export function construirHerramientas(op: OpcionesHerramientas): ToolSet {
  const { odoo, registro } = op;
  const tools: ToolSet = {};

  // El modelo puede pedir varias herramientas en un mismo paso y el SDK las corre a la vez. Las que ESCRIBEN en Odoo se turnan: todas tocan
  // la MISMA conversación (oportunidad, etiqueta, nota...) y dos transacciones sobre la misma fila chocan en Postgres («could not serialize
  // access due to concurrent update»): Odoo contestaba error y la herramienta fallaba al azar. Hallado con Odoo real (test/integracion).
  let turno: Promise<unknown> = Promise.resolve();
  const enTurno = <T>(trabajo: () => Promise<T>): Promise<T> => {
    const mia = turno.then(trabajo, trabajo);
    turno = mia.catch(() => undefined);
    return mia;
  };

  for (const def of op.defs) {
    if (def.nombre === "enviar_foto_producto") continue; // la local manda
    tools[def.nombre] = tool({
      description: def.descripcion,
      inputSchema: jsonSchema(def.parametros as never),
      execute: async (args: unknown) => {
        const argumentos = esObjeto(args) ? { ...args } : {};
        // Un cliente (o un mensaje manipulado) no puede pedir el saldo de otro número.
        if (def.nombre === "saldo_puntos" && op.celularDeLaConversacion) argumentos.celular = op.celularDeLaConversacion;
        if (def.nombre === "saldo_puntos" && typeof argumentos.pin === "string") registro.pines.push(argumentos.pin);

        // Lectura repetida (mismos argumentos, misma conversación, menos de 60 s): sin viaje a Odoo.
        const clave =
          op.cache && HERRAMIENTAS_DE_LECTURA.has(def.nombre) ? `${op.identidad ?? ""}|${def.nombre}|${argumentosEstables(argumentos)}` : null;
        const guardado = clave ? op.cache!.obtener(clave) : undefined;
        if (guardado !== undefined) {
          registro.llamadas.push({ nombre: def.nombre, ok: true });
          return { ok: true, resultado: acotar(anotarConsulta(def.nombre, guardado, registro, op.sitio)) };
        }

        op.alEmpezar?.();
        const llamar = async () => (op.omitir?.() ? { ok: false as const, resultado: undefined } : odoo.herramienta(def.nombre, argumentos, op.conversacionId()));
        // Las consultas corren juntas (no escriben nada); las que escriben sobre la conversación, una tras otra.
        const r = await (HERRAMIENTAS_DE_LECTURA.has(def.nombre) ? llamar() : enTurno(llamar));
        registro.llamadas.push({ nombre: def.nombre, ok: r.ok });
        if (!r.ok) {
          return {
            ok: false,
            error: "No pude consultar el sistema ahora.",
            instruccion: "Dile al cliente, con honestidad, que ahorita no pudiste consultarlo y ofrécele una vendedora. No inventes el dato.",
          };
        }
        if (def.nombre === "pasar_a_vendedora") {
          registro.pasoAVendedora = true;
          registro.textoDeVendedora = textoDeLaHerramienta(r.resultado);
        }
        if (def.nombre === "registrar_pregunta_sin_respuesta") registro.preguntaRegistrada = true;
        if (clave) op.cache!.guardar(clave, r.resultado);
        return { ok: true, resultado: acotar(anotarConsulta(def.nombre, r.resultado, registro, op.sitio)) };
      },
    });
  }

  tools.enviar_foto_producto = tool({
    description:
      "Envía al cliente la foto de un producto por este mismo chat. Úsala solo con un código que ya consultaste con ver_producto o buscar_productos. " +
      "La foto sale junto con tu respuesta; no digas que ya la mandaste, di que se la envías.",
    inputSchema: jsonSchema({
      type: "object",
      properties: { codigo: { type: "string", description: "Código del producto, tal cual lo devolvió la herramienta." } },
      required: ["codigo"],
      additionalProperties: false,
    } as never),
    execute: async (args: unknown) => {
      const codigo = esObjeto(args) ? aTexto(args.codigo).trim().toUpperCase() : "";
      const foto = registro.fotos.get(codigo) ?? op.fotoPrevia(codigo);
      registro.llamadas.push({ nombre: "enviar_foto_producto", ok: !!foto });
      if (!codigo || !foto) {
        return { ok: false, error: "No tengo la foto de ese código. Consulta primero el producto con ver_producto." };
      }
      if (registro.medios.some((m) => m.url === foto.url)) return { ok: true, resultado: "Esa foto ya va en tu respuesta." };
      if (registro.medios.length >= MAX_FOTOS_POR_RESPUESTA) {
        return { ok: false, error: `Ya van ${MAX_FOTOS_POR_RESPUESTA} fotos en esta respuesta; ofrece mandar las demás después.` };
      }
      registro.medios.push({ tipo: "imagen", url: foto.url, nombre: foto.nombre, pie: foto.nombre });
      return { ok: true, resultado: "La foto sale junto con tu respuesta." };
    },
  });

  return tools;
}

/** Para las pruebas y el registro de cifras: números de un texto cualquiera (mensajes del cliente, respuestas previas). */
export function cifrasDeTexto(texto: string): number[] {
  const n: number[] = [];
  for (const m of texto.matchAll(/\d+(?:[.,]\d+)*/g)) {
    const v = parseMonto(m[0]);
    if (Number.isFinite(v)) n.push(v);
  }
  return n;
}
