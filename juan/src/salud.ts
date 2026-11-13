// Salud del Worker: lo que contestan `GET /odoo/salud` (con token) y `GET /salud` (público, sin datos sensibles),
// y lo que revisa el cron (crons de wrangler.jsonc).
//
// El Worker arranca SIN secretos (la dueña los pega en el panel de Cloudflare después del primer despliegue,
// docs/JUAN.md). Mientras falten, no se cae: responde con un mensaje claro. Aquí solo viajan NOMBRES de
// secretos y estados; jamás un valor.

import { canalActivo, mesDelNegocio, type Config, type ProveedorIa } from "./config";
import type { Env } from "./env";
import type { AdaptadorCanal, CanalId, EstadoDeLlave, SaludCanal, SaludLocal } from "./canales/tipos";
import { TODOS_LOS_CANALES } from "./canales/tipos";
import { entrenaConLosMensajes, modelosDelPapel, NOMBRE_DE_LA_CLAVE, clavePresente } from "./motor/proveedores";
import { precioDe } from "./motor/precios";

/** Lo que el Worker necesita SIEMPRE (la clave de la IA depende de qué proveedor se elija en Odoo: ver `clavesDeIa`). */
export const SECRETOS_GENERALES: { nombre: "JUAN_ODOO_TOKEN" | "JUAN_WORKER_TOKEN"; paraQue: string }[] = [
  { nombre: "JUAN_ODOO_TOKEN", paraQue: "hablar con Odoo (mensajes, configuración, herramientas)" },
  { nombre: "JUAN_WORKER_TOKEN", paraQue: "que Odoo pueda llamar a este Worker (enviar, estado, seguimiento, salud)" },
];

export interface EstadoDeCanal extends SaludCanal {
  activo: boolean;
  /** Por qué puerta va (solo los canales con dos: Instagram, «pagina_facebook» o «inicio_sesion_instagram»). */
  puerta?: string;
  /** Cuándo vence su llave y si la renovación va bien (Instagram por inicio de sesión de Instagram). Nunca el valor. */
  llave?: EstadoDeLlave;
  /** La cuenta del negocio en ese canal, si se sabe («@dcasapty»). */
  cuenta?: string;
  /** Avisos ignorados por ser de otra cuenta (cuántos, el último, «…1234»). */
  ignorados?: SaludLocal["ignorados"];
  /** Lo que dice Meta de la suscripción de la app a los mensajes, si se pudo consultar. */
  suscripcion?: SaludLocal["suscripcion"];
}

export interface EstadoDeIa {
  proveedor: ProveedorIa;
  respaldo: ProveedorIa | null;
  modelo_rapido: string;
  modelo_inteligente: string;
  /** Proveedores cuya clave está cargada. */
  con_clave: ProveedorIa[];
  /** NOMBRES de las claves que faltan (la del principal y la del respaldo, si hay). */
  claves_faltantes: string[];
  /** El último fallo registrado (sin claves ni datos de clientes). */
  ultimo_fallo?: { proveedor: string; modelo: string; motivo: string; ts: number };
  ultimo_respaldo?: { proveedor: string; modelo: string; ts: number };
  /** Modelos que gastaron sin tener precio cargado en Odoo (`precios_ia`). */
  modelos_sin_precio: string[];
}

export interface InformeDeSalud {
  ok: boolean;
  /** Una frase para una persona: qué pasa y qué hacer. */
  mensaje: string;
  version: string;
  entorno: string;
  /** NOMBRES de los secretos que faltan (generales y de la IA elegida). */
  secretos_faltantes: string[];
  ia: EstadoDeIa;
  canales: Record<CanalId, EstadoDeCanal>;
  /**
   * Lo gastado en IA en el mes (`mes`). `null` si el contador no se pudo leer: SIN DATO, no un cero (con un 0, Odoo
   * mostraba «$0 por pagar» y guardaba una foto en 0; revisión de «Costos de IA», 2026-11-12).
   */
  gasto_ia_mes_usd: number | null;
  /** El mes de ese gasto, «AAAA-MM» en la zona del negocio: Odoo usa ESTE mes para su corte (a las 00:00 del día 1 los relojes pueden diferir). */
  mes: string;
  tope_usd: number;
  tope_alcanzado: boolean;
  /** Lo que falta o está mal, en palabras; vacío si todo bien. */
  problemas: string[];
  /** Cosas que conviene saber aunque todo funcione (p. ej. un modelo que entrena con los mensajes). */
  avisos: string[];
}

export interface DepsSalud {
  env: Env;
  adaptadores: readonly AdaptadorCanal[];
  config(): Promise<Config>;
  gastoMes(mes: string): Promise<number>;
  ahora(): number;
  /** Modelos que gastaron este mes sin precio cargado. */
  modelosSinPrecio?(mes: string): Promise<string[]>;
  /** Lo que el motor dejó anotado (último fallo de la IA, uso del respaldo). */
  leerSalud?(clave: string): Promise<{ json: string; ts: number } | null>;
  /** false = no se pregunta a nadie por la red (el endpoint público no debe poder usarse para molestar al puente). */
  consultarConexiones?: boolean;
}

const redondear = (n: number) => Math.round(n * 100) / 100;

function conTiempo<T>(p: Promise<T>, ms: number, defecto: T): Promise<T> {
  return Promise.race([p, new Promise<T>((r) => setTimeout(() => r(defecto), ms))]);
}

/** Solo los dos tokens con Odoo (no depende de la configuración, que viene de Odoo). */
export function secretosGeneralesFaltantes(env: Env): string[] {
  return SECRETOS_GENERALES.filter((s) => !env[s.nombre]).map((s) => s.nombre as string);
}

/** Las claves de IA que hacen falta según lo elegido en Odoo: la del principal y, si hay respaldo, la del respaldo. */
export function clavesDeIa(cfg: Config): { proveedor: ProveedorIa; clave: string; papel: "principal" | "respaldo" }[] {
  const lista: { proveedor: ProveedorIa; clave: string; papel: "principal" | "respaldo" }[] = [{ proveedor: cfg.proveedor_ia, clave: NOMBRE_DE_LA_CLAVE[cfg.proveedor_ia], papel: "principal" }];
  if (cfg.proveedor_respaldo_ia) lista.push({ proveedor: cfg.proveedor_respaldo_ia, clave: NOMBRE_DE_LA_CLAVE[cfg.proveedor_respaldo_ia], papel: "respaldo" });
  return lista;
}

/** NOMBRES de los secretos que faltan: los dos tokens con Odoo y la(s) clave(s) de la IA elegida(s). */
export function secretosFaltantes(env: Env, cfg: Config): string[] {
  const generales = SECRETOS_GENERALES.filter((s) => !env[s.nombre]).map((s) => s.nombre as string);
  const ia = clavesDeIa(cfg).filter((c) => !clavePresente(env, c.proveedor)).map((c) => c.clave as string);
  return [...generales, ...ia];
}

/** La frase que se lee primero. */
export function resumenParaPersonas(ia: EstadoDeIa, canales: Record<CanalId, EstadoDeCanal>, problemas: string[]): string {
  if (ia.con_clave.length === 0 || (!ia.con_clave.includes(ia.proveedor) && !(ia.respaldo && ia.con_clave.includes(ia.respaldo)))) {
    return `Falta ${ia.claves_faltantes[0] ?? NOMBRE_DE_LA_CLAVE[ia.proveedor]}: el asistente todavía no puede contestar con IA y le dice a cada cliente que una vendedora lo atiende. Pega la clave en Cloudflare (Worker → Settings → Variables and Secrets).`;
  }
  const activos = TODOS_LOS_CANALES.filter((c) => canales[c].activo);
  const listos = activos.filter((c) => canales[c].configurado);
  if (listos.length === 0) {
    return "Ningún canal está listo todavía: faltan secretos de los canales encendidos en Odoo (mira «canales» para ver cuáles).";
  }
  if (problemas.length > 0) return `Hay ${problemas.length} cosa(s) por revisar: ${problemas[0]}.`;
  return "Todo en orden.";
}

async function leerJson<T>(d: DepsSalud, clave: string): Promise<T | undefined> {
  try {
    const f = await d.leerSalud?.(clave);
    return f ? (JSON.parse(f.json) as T) : undefined;
  } catch {
    return undefined;
  }
}

export async function informeDeSalud(d: DepsSalud): Promise<InformeDeSalud> {
  const consultar = d.consultarConexiones !== false;
  const cfg = await d.config();
  const mes = mesDelNegocio(cfg.horario.zona, d.ahora());
  const gasto: number | null = await d.gastoMes(mes).catch(() => null);
  const sinPrecio = (await d.modelosSinPrecio?.(mes).catch(() => [] as string[])) ?? [];
  const faltantes = secretosFaltantes(d.env, cfg);
  const problemas: string[] = [];
  const avisos: string[] = [];

  for (const s of SECRETOS_GENERALES) if (!d.env[s.nombre]) problemas.push(`falta ${s.nombre} (${s.paraQue})`);
  if (gasto === null) avisos.push("no pude leer el gasto de IA del mes (el contador no respondió): Odoo no muestra cifras de costos hasta que se pueda");
  // Sin su propia dirección, el Worker guarda las fotos y notas de voz del cliente pero Odoo no las puede traer: en el chat
  // sale «No se pudo traer 1 archivo» (lo vio la dueña el 2026-11-03).
  if (!/^https:\/\/[^/\s]+/.test(d.env.URL_PUBLICA ?? "")) {
    problemas.push("falta la variable URL_PUBLICA (la dirección https de este Worker): las fotos, notas de voz y archivos de los clientes no llegan al chat de Odoo");
  }

  // ── La IA ──
  const conClave = (["anthropic", "meta", "openai"] as const).filter((p) => clavePresente(d.env, p));
  const claves = clavesDeIa(cfg);
  const falta = claves.filter((c) => !clavePresente(d.env, c.proveedor));
  for (const c of falta) {
    problemas.push(
      c.papel === "principal"
        ? `falta ${c.clave}: el proveedor de IA «${c.proveedor}» no puede contestar${cfg.proveedor_respaldo_ia && clavePresente(d.env, cfg.proveedor_respaldo_ia) ? " (contesta el respaldo)" : ""}`
        : `falta ${c.clave}: el respaldo «${c.proveedor}» no puede contestar`,
    );
  }
  const alguno = claves.some((c) => clavePresente(d.env, c.proveedor));
  if (!alguno) problemas.push("ningún proveedor de IA tiene clave: a cada cliente se le dice que una vendedora lo atiende");
  for (const papel of ["principal", "respaldo"] as const) {
    const m = modelosDelPapel(cfg, papel);
    if (!m) continue;
    for (const modelo of new Set([m.rapido, m.inteligente])) {
      if (entrenaConLosMensajes(modelo)) {
        avisos.push(`el modelo ${modelo} puede usar los mensajes de los clientes para entrenar; confirma que el texto de privacidad lo diga (Ley 81 de 2019)`);
      }
      if (!precioDe(modelo, cfg.precios_ia).conPrecio) {
        problemas.push(`el modelo ${modelo} no tiene precio cargado en Odoo (precios_ia): el tope mensual lo estima con una tarifa de reserva`);
      }
    }
  }
  for (const m of sinPrecio) {
    if (!problemas.some((p) => p.includes(m))) problemas.push(`el modelo ${m} gastó este mes sin precio cargado en Odoo (precios_ia)`);
  }
  const ultimoFallo = await leerJson<EstadoDeIa["ultimo_fallo"]>(d, "ia_fallo");
  const ultimoRespaldo = await leerJson<EstadoDeIa["ultimo_respaldo"]>(d, "ia_respaldo");
  const hace24h = d.ahora() - 24 * 3600_000;
  if (ultimoFallo && ultimoFallo.ts > hace24h) {
    problemas.push(`la IA «${ultimoFallo.proveedor}/${ultimoFallo.modelo}» falló hace poco: ${ultimoFallo.motivo}`);
  }
  // Odoo no recibe lo que le llega al Worker: nada se pierde (se guarda y se reintenta), pero el historial y los avisos no avanzan.
  const cola = await leerJson<{ ts: number; resuelto?: boolean }>(d, "cola_estancada");
  if (cola && !cola.resuelto && cola.ts > d.ahora() - 12 * 3600_000) {
    problemas.push("Odoo no está recibiendo los mensajes de los clientes: el Worker los guarda y los reintenta cada 6 horas; no se pierde nada, pero hay que revisar Odoo");
  }
  // Un envío por el canal que falló (el motivo ya viene sin datos de nadie). Se apaga solo cuando un envío posterior sale bien.
  const envio = await leerJson<{ ts: number; canal?: string; motivo?: string; con_archivos?: boolean; resuelto?: boolean }>(d, "envio_fallo");
  if (envio && !envio.resuelto && envio.ts > hace24h) {
    problemas.push(`no se pudo enviar ${envio.con_archivos ? "un mensaje con foto o archivo" : "un mensaje"} por ${envio.canal ?? "un canal"}: ${envio.motivo ?? "sin detalle"}`);
  }
  // Comentarios de Instagram y Facebook (revisión del 2026-11-13): lo que hay que mirar en la prueba real (sin datos de nadie).
  const sinClasificar = await leerJson<{ ts: number; red?: string; motivo?: string }>(d, "comentario_sin_clasificar");
  if (sinClasificar && sinClasificar.ts > hace24h) {
    avisos.push(`la IA no pudo clasificar un comentario de ${sinClasificar.red ?? "una red"} (se reintenta 3 veces en 24 horas): ${sinClasificar.motivo ?? "sin detalle"}`);
  }
  const otroId = await leerJson<{ ts: number; red?: string }>(d, "comentario_otro_destinatario");
  if (otroId && otroId.ts > d.ahora() - 7 * 24 * 3600_000) {
    avisos.push(
      `Meta entregó una respuesta privada a un comentario de ${otroId.red ?? "una red"} a un id distinto del que comentó: Juan le avisó a esa conversación para que su eco no se tome como una vendedora; si la persona contesta, su mensaje sale en otra conversación de Odoo. Revísalo en la prueba real`,
    );
  }
  const topePrivadas = await leerJson<{ ts: number; tope?: number }>(d, "comentario_tope_privadas");
  if (topePrivadas && topePrivadas.ts > hace24h) {
    avisos.push(`se llegó al tope de ${topePrivadas.tope ?? "?"} respuestas privadas a comentarios en una hora (entre todas las personas): las de más quedaron anotadas sin respuesta`);
  }
  const ecoAdelantado = await leerJson<{ ts: number; red?: string }>(d, "comentario_eco_adelantado");
  if (ecoAdelantado && ecoAdelantado.ts > d.ahora() - 7 * 24 * 3600_000) {
    avisos.push(`el eco de una respuesta privada a un comentario de ${ecoAdelantado.red ?? "una red"} llegó antes que su aviso y se tomó un momento como una vendedora (Juan deshizo la pausa; en Odoo puede verse como mensaje de una vendedora)`);
  }
  const principal = modelosDelPapel(cfg, "principal");
  const ia: EstadoDeIa = {
    proveedor: cfg.proveedor_ia,
    respaldo: cfg.proveedor_respaldo_ia,
    modelo_rapido: principal?.rapido ?? "",
    modelo_inteligente: principal?.inteligente ?? "",
    con_clave: [...conClave],
    claves_faltantes: falta.map((c) => c.clave as string),
    ...(ultimoFallo && ultimoFallo.ts > hace24h ? { ultimo_fallo: ultimoFallo } : {}),
    ...(ultimoRespaldo && ultimoRespaldo.ts > hace24h ? { ultimo_respaldo: ultimoRespaldo } : {}),
    modelos_sin_precio: sinPrecio,
  };

  // ── Los canales ──
  const canales = {} as Record<CanalId, EstadoDeCanal>;
  for (const id of TODOS_LOS_CANALES) {
    const a = d.adaptadores.find((x) => x.canales.includes(id));
    const activo = canalActivo(cfg, id);
    const base: SaludCanal = a
      ? { configurado: a.configurado(d.env, id), faltan: a.faltantes(d.env, id), conectado: null }
      : { configurado: false, faltan: [], conectado: null };
    const s: SaludCanal =
      a && consultar && base.configurado && a.salud
        ? await conTiempo(a.salud(id, d.env), 4000, { ...base, conectado: null, detalle: "no contestó a tiempo" })
        : base;
    // Lo que el canal sabe sin salir a la red (también para el /salud público): la puerta y su llave.
    const local: SaludLocal = a?.saludLocal ? await conTiempo(a.saludLocal(id, d.env).catch(() => ({})), 3000, {}) : {};
    canales[id] = {
      activo,
      ...s,
      ...(local.puerta ? { puerta: local.puerta } : {}),
      ...(local.llave ? { llave: local.llave } : {}),
      ...(local.cuenta ? { cuenta: local.cuenta } : {}),
      ...(local.ignorados ? { ignorados: local.ignorados } : {}),
      ...(local.suscripcion ? { suscripcion: local.suscripcion } : {}),
    };
    if (activo && !s.configurado) problemas.push(`el canal ${id} está encendido pero faltan: ${(s.faltan ?? []).join(", ") || "credenciales"}`);
    if (activo && s.configurado && s.conectado === false) problemas.push(`el canal ${id} no está conectado${s.detalle ? ` (${s.detalle})` : ""}`);
    if (activo) {
      problemas.push(...(local.problemas ?? []));
      avisos.push(...(local.avisos ?? []));
      if (cfg.comentarios.activo) avisos.push(...(s.avisosComentarios ?? []));
    }
  }

  const tope = cfg.presupuesto_ia_mensual_usd;
  return {
    ok: problemas.length === 0,
    mensaje: resumenParaPersonas(ia, canales, problemas),
    version: d.env.VERSION ?? "dev",
    entorno: d.env.ENTORNO ?? "desconocido",
    secretos_faltantes: faltantes,
    ia,
    canales,
    gasto_ia_mes_usd: gasto === null ? null : redondear(gasto),
    mes,
    tope_usd: tope,
    tope_alcanzado: gasto !== null && tope > 0 && gasto >= tope,
    problemas,
    avisos,
  };
}

/**
 * Lo único que se muestra sin token: si el Worker está vivo, qué NOMBRES de secretos faltan y el estado de cada canal (en
 * Instagram, además, por qué puerta va y cuándo vence su llave: fechas, nunca la llave). Sin gasto, sin tope, sin motivos de
 * fallo, sin detalles de conexión.
 */
export interface InformePublico {
  ok: boolean;
  mensaje: string;
  version: string;
  entorno: string;
  secretos_faltantes: string[];
  ia: { proveedor: ProveedorIa; respaldo: ProveedorIa | null; lista: boolean };
  /** `puerta`, `llave`, `cuenta`, `ignorados` y `suscripcion` solo en los canales que las tienen (Instagram). */
  canales: Record<
    CanalId,
    { activo: boolean; configurado: boolean; faltan: string[]; puerta?: string; llave?: EstadoDeLlave; cuenta?: string; ignorados?: SaludLocal["ignorados"]; suscripcion?: SaludLocal["suscripcion"] }
  >;
}

export async function informePublico(d: DepsSalud): Promise<InformePublico> {
  const i = await informeDeSalud({ ...d, consultarConexiones: false });
  return {
    ok: i.ok,
    mensaje: i.mensaje,
    version: i.version,
    entorno: i.entorno,
    secretos_faltantes: i.secretos_faltantes,
    ia: { proveedor: i.ia.proveedor, respaldo: i.ia.respaldo, lista: i.ia.con_clave.includes(i.ia.proveedor) || (!!i.ia.respaldo && i.ia.con_clave.includes(i.ia.respaldo)) },
    canales: Object.fromEntries(
      TODOS_LOS_CANALES.map((c) => {
        const k = i.canales[c];
        const extra = { puerta: k.puerta, llave: k.llave, cuenta: k.cuenta, ignorados: k.ignorados, suscripcion: k.suscripcion };
        return [c, { activo: k.activo, configurado: k.configurado, faltan: k.faltan ?? [], ...Object.fromEntries(Object.entries(extra).filter(([, v]) => v !== undefined)) }];
      }),
    ) as InformePublico["canales"],
  };
}

// ── Cron: avisar una vez por problema ───────────────────────────────────────

export interface EstadoDeAvisos {
  /** Problemas ya avisados (para no repetir el mismo aviso cada hora). */
  avisados: string[];
}

/** Compara los problemas de ahora con los ya avisados: qué avisar nuevo y qué se arregló. */
export function decidirAvisos(problemas: string[], previo: EstadoDeAvisos): { mensajes: string[]; nuevo: EstadoDeAvisos } {
  const nuevos = problemas.filter((p) => !previo.avisados.includes(p));
  const arreglados = previo.avisados.filter((p) => !problemas.includes(p));
  const mensajes = [
    ...nuevos.map((p) => `Aviso del asistente de D'CASA: ${p}.`),
    ...arreglados.map((p) => `Resuelto en el asistente de D'CASA: ${p}.`),
  ];
  return { mensajes, nuevo: { avisados: problemas } };
}
