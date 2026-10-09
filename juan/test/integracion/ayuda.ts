// Ayudas de la prueba de integración REAL (scripts/integracion_juan.sh).
//
// Aquí no hay dobles entre Odoo y el Worker:
//   · Odoo es el de verdad (otro proceso, con su base y sus tokens generados por el script).
//   · El Worker `juan` es el de verdad: su `fetch` real (src/index.ts), las clases reales de Durable Object, el cliente
//     real de Odoo y las rutas reales `/odoo/*` y `/media/*`, servidos por un servidor HTTP de Node. Es el mismo
//     camino que en producción salvo lo que Cloudflare pone: el almacenamiento SQLite de los Durable Objects (aquí,
//     node:sqlite) y las alarmas (aquí, un reloj que las dispara).
//   · El service binding `DCASA` es el código real de `edge/src/juan.ts` (la entrada `JuanEntrada`), que reenvía por HTTP
//     al Odoo real.
//   · Lo único de mentira es lo de afuera: la IA (un modelo guionado que habla como la API de Anthropic) y el puente de
//     WhatsApp (que valida lo que recibe con el MISMO código del puente real, `puente-wa/contenedor/lib`).
//
// Los tokens llegan por el entorno del proceso (los generó el script); aquí jamás se imprimen ni se comparan en un
// `expect` que pueda mostrarlos.

import { createHash, randomBytes } from "node:crypto";
import http from "node:http";
import { pathToFileURL } from "node:url";
import { vi } from "vitest";
import { atenderJuan } from "../../../edge/src/juan";
import worker from "../../src/index";
import { olvidarCaches } from "../../src/odoo/fabrica";
import { tokenParaCabecera } from "../../src/seguridad";
import { armarCluster, type Cluster } from "../helpers/doFalso";

export const ODOO_URL = process.env.ODOO_INTEGRACION_URL ?? "";
export const hayOdoo = ODOO_URL !== "";
export const JUAN_PUERTO = Number(process.env.JUAN_INTEGRACION_PUERTO ?? 0);
export const TOKEN_ODOO = process.env.JUAN_ODOO_TOKEN ?? "";
export const TOKEN_WORKER = process.env.JUAN_WORKER_TOKEN ?? "";
export const BD = process.env.ODOO_INTEGRACION_DB ?? "";
export const ODOO_URL_SIN_TOKEN = process.env.ODOO_INTEGRACION_URL_SIN_TOKEN ?? "";

/** El `fetch` de verdad, antes de que la prueba lo reemplace para la IA. */
export const fetchReal: typeof fetch = globalThis.fetch.bind(globalThis);

// ── Utilidades ──────────────────────────────────────────────────────────────

export const dormir = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

export async function esperarHasta<T>(que: string, condicion: () => Promise<T | false | null | undefined> | T | false | null | undefined, ms = 20_000, cada = 100): Promise<T> {
  const limite = Date.now() + ms;
  let ultimo: unknown;
  while (Date.now() < limite) {
    try {
      const v = await condicion();
      if (v) return v;
    } catch (e) {
      ultimo = e;
    }
    await dormir(cada);
  }
  throw new Error(`Se agotó la espera (${ms} ms): ${que}${ultimo ? ` · último error: ${String(ultimo)}` : ""}`);
}

/** Un celular de Panamá de mentira y único por escenario: 507 6xxx-xxxx. */
export function celularNuevo(): string {
  const n = randomBytes(4).readUInt32BE(0) % 10_000_000;
  return `5076${String(n).padStart(7, "0")}`;
}

export const sha1 = (bytes: Uint8Array) => createHash("sha1").update(bytes).digest("hex");

/** Un PNG de 1×1 píxel (el mismo de los productos de prueba), con un byte de relleno para distinguir archivos. */
export const PNG_BASE64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";
export const pngBytes = () => Uint8Array.from(Buffer.from(PNG_BASE64, "base64"));

// ── Odoo por RPC (como lo haría una persona de ventas desde la pantalla) ────

export class OdooRpc {
  private cookie = "";
  constructor(
    private readonly login: string,
    private readonly clave: string,
    private readonly base = ODOO_URL,
  ) {}

  private async json(ruta: string, params: Record<string, unknown>): Promise<{ result?: any; error?: any; cabeceras: Headers }> {
    const r = await fetchReal(`${this.base}${ruta}`, {
      method: "POST",
      headers: { "content-type": "application/json", ...(this.cookie ? { cookie: this.cookie } : {}) },
      body: JSON.stringify({ jsonrpc: "2.0", method: "call", params }),
    });
    const cuerpo = (await r.json()) as { result?: unknown; error?: unknown };
    return { ...cuerpo, cabeceras: r.headers };
  }

  async autenticar(): Promise<this> {
    const r = await this.json("/web/session/authenticate", { db: BD, login: this.login, password: this.clave });
    if (r.error || !r.result?.uid) throw new Error(`No se pudo entrar a Odoo como ${this.login}: ${JSON.stringify(r.error?.data?.message ?? "sin uid")}`);
    const set = r.cabeceras.getSetCookie().find((c) => c.startsWith("session_id="));
    this.cookie = set?.split(";")[0] ?? "";
    return this;
  }

  /** `call_kw`. Lanza con el mensaje de Odoo si falla. */
  async llamar<T = any>(modelo: string, metodo: string, args: unknown[] = [], kwargs: Record<string, unknown> = {}): Promise<T> {
    const r = await this.json(`/web/dataset/call_kw/${modelo}/${metodo}`, { model: modelo, method: metodo, args, kwargs });
    if (r.error) throw new Error(`Odoo ${modelo}.${metodo}: ${r.error.data?.message ?? r.error.message}`);
    return r.result as T;
  }

  leer<T = any>(modelo: string, ids: number[], campos: string[]): Promise<T[]> {
    return this.llamar<T[]>(modelo, "read", [ids, campos]);
  }

  buscar<T = any>(modelo: string, dominio: unknown[], campos: string[], extra: Record<string, unknown> = {}): Promise<T[]> {
    return this.llamar<T[]>(modelo, "search_read", [dominio, campos], extra);
  }

  escribir(modelo: string, ids: number[], valores: Record<string, unknown>) {
    return this.llamar<boolean>(modelo, "write", [ids, valores]);
  }

  /** Ejecuta un cron del módulo como lo haría el planificador de Odoo (el botón «ejecutar manualmente»). */
  async dispararCron(nombreParcial: string): Promise<void> {
    const [cron] = await this.buscar("ir.cron", [["name", "ilike", nombreParcial]], ["id"]);
    if (!cron) throw new Error(`No hay un cron «${nombreParcial}»`);
    await this.llamar("ir.cron", "method_direct_trigger", [[cron.id]]);
  }
}

/** Una petición HTTP directa a la API de Juan de Odoo (como la haría el Worker), con el token indicado. */
export async function apiOdoo(
  metodo: "GET" | "POST",
  ruta: string,
  opciones: { cuerpo?: unknown; token?: string | null; base?: string; cabeceras?: Record<string, string> } = {},
): Promise<{ estado: number; json: any; cabeceras: Headers }> {
  const token = opciones.token === undefined ? TOKEN_ODOO : opciones.token;
  const r = await fetchReal(`${opciones.base ?? ODOO_URL}/dcasa/juan/v1${ruta}`, {
    method: metodo,
    headers: {
      accept: "application/json",
      ...(token ? { authorization: `Bearer ${token}` } : {}),
      ...(opciones.cuerpo !== undefined ? { "content-type": "application/json; charset=utf-8" } : {}),
      ...opciones.cabeceras,
    },
    body: opciones.cuerpo !== undefined ? JSON.stringify(opciones.cuerpo) : undefined,
  });
  const texto = await r.text();
  let json: any = null;
  try {
    json = texto ? JSON.parse(texto) : null;
  } catch {
    /* no era JSON */
  }
  return { estado: r.status, json, cabeceras: r.headers };
}

// ── El service binding DCASA = edge/src/juan.ts (código real) → Odoo real ───

export interface EstadoDelEnlace {
  /** Peticiones que quedaron registradas (método, ruta con consulta, cuerpo ya parseado). */
  peticiones: { metodo: string; ruta: string; cuerpo?: any; estado: number }[];
  /** Cuántas de las próximas peticiones se contestan como «Odoo arrancando» (503) sin llegar a Odoo. */
  dormido: number;
}

export function enlaceDcasa(estado: EstadoDelEnlace, base = ODOO_URL): Fetcher {
  return {
    fetch: async (input: unknown, init?: RequestInit) => {
      const req = new Request(input as string, init);
      const url = new URL(req.url);
      const texto = req.method === "GET" ? "" : await req.clone().text();
      let cuerpo: any;
      try {
        cuerpo = texto ? JSON.parse(texto) : undefined;
      } catch {
        cuerpo = texto;
      }
      const anotar = (estadoHttp: number) => estado.peticiones.push({ metodo: req.method, ruta: url.pathname + url.search, cuerpo, estado: estadoHttp });
      if (estado.dormido > 0) {
        estado.dormido--;
        // Lo mismo que contesta el borde mientras el contenedor despierta (edge/src/juan.ts).
        const r = await atenderJuan(req, {
          forward: async () => new Response("<html>arrancando</html>", { status: 200, headers: { "X-Dcasa-Estado": "arrancando", "Retry-After": "15" } }),
          canonicalHost: "dcasapty.com",
        });
        anotar(r.status);
        return r;
      }
      const r = await atenderJuan(req, {
        forward: async (upstream) => {
          const destino = new URL(upstream.url);
          return fetchReal(`${base}${destino.pathname}${destino.search}`, {
            method: upstream.method,
            headers: upstream.headers,
            body: upstream.method === "GET" ? undefined : Buffer.from(await upstream.arrayBuffer()),
          });
        },
        canonicalHost: "dcasapty.com",
      });
      anotar(r.status);
      return r;
    },
  } as unknown as Fetcher;
}

// ── El puente de WhatsApp de mentira, con la validación del puente de verdad ─

export interface EnvioAlPuente {
  para: string;
  chunks: string[];
  medios: { tipo: string; url: string; nombre?: string; mime?: string; pie?: string }[];
  /** Lo que el «puente» bajó de cada URL de medio (después de validarla con el código real del puente). */
  descargas: { url: string; estado: number; mime: string; bytes: Uint8Array }[];
}

export const DOMINIOS_DEL_PUENTE = "dcasapty.com,dcasapty.workers.dev";

export function crearPuente(waToken: string) {
  const envios: EnvioAlPuente[] = [];
  const rechazos: { estado: number; error: string }[] = [];
  let contrato: Promise<any> | undefined;
  const cargarContrato = () =>
    (contrato ??= import(/* @vite-ignore */ pathToFileURL(new URL("../../../puente-wa/contenedor/lib/contrato.mjs", import.meta.url).pathname).href));
  let urls: Promise<any> | undefined;
  const cargarUrls = () => (urls ??= import(/* @vite-ignore */ pathToFileURL(new URL("../../../puente-wa/contenedor/lib/urls.mjs", import.meta.url).pathname).href));

  const fetcher = {
    fetch: async (input: unknown, init?: RequestInit) => {
      const req = new Request(input as string, init);
      const url = new URL(req.url);
      const token = Buffer.from(req.headers.get("x-wa-token-b64") ?? "", "base64").toString("utf8");
      if (token !== waToken) return Response.json({ error: "no autorizado" }, { status: 401 });
      if (req.method === "GET" && url.pathname === "/api/estado") return Response.json({ conectado: true, estado: "conectado" });
      if (req.method !== "POST" || url.pathname !== "/api/enviar") return Response.json({ error: "no existe" }, { status: 404 });

      const cuerpo = await req.json();
      const { validarEnviar } = await cargarContrato();
      const { parsearListaHosts } = await cargarUrls();
      const v = validarEnviar(cuerpo, { hostsPermitidos: parsearListaHosts(DOMINIOS_DEL_PUENTE) });
      if (!v.ok) {
        rechazos.push({ estado: v.status, error: v.error });
        return Response.json({ error: v.error }, { status: v.status });
      }
      const envio: EnvioAlPuente = { para: v.plan.para.e164 ?? v.plan.para.jid, chunks: v.plan.burbujas, medios: [], descargas: [] };
      // El puente baja el medio desde internet. Aquí «internet» es el Odoo local: se cambia solo el origen, la ruta firmada es la real.
      for (const m of v.plan.medios) {
        envio.medios.push({ tipo: m.tipo, url: m.url, nombre: m.nombre, mime: m.mime, pie: m.pie });
        const destino = new URL(m.url);
        const r = await fetchReal(`${ODOO_URL}${destino.pathname}${destino.search}`);
        const bytes = new Uint8Array(await r.arrayBuffer());
        envio.descargas.push({ url: m.url, estado: r.status, mime: r.headers.get("content-type") ?? "", bytes });
        if (r.status !== 200) {
          rechazos.push({ estado: 502, error: `no se pudo bajar ${destino.pathname.slice(0, 40)}… (${r.status})` });
          return Response.json({ error: `medios: la descarga respondió ${r.status}` }, { status: 502 });
        }
      }
      envios.push(envio);
      return Response.json({ ok: true, ids: envio.chunks.map((_, i) => `puente-${envios.length}-${i}`) });
    },
  } as unknown as Fetcher;
  return { fetcher, envios, rechazos, textos: () => envios.flatMap((e) => e.chunks) };
}

// ── La IA de mentira: la API de mensajes de Anthropic, guionada ─────────────

export interface ContextoIA {
  cuerpo: any;
  /** El prompt de sistema completo, como texto. */
  sistema: string;
  /** Lo que devolvieron las herramientas hasta ahora en este turno (nombre → resultado ya parseado). */
  resultado(nombre: string): any;
  /** Las herramientas que se le ofrecieron al modelo. */
  herramientas: string[];
}
export type PasoIA = { texto: string } | { llamadas: { nombre: string; args: Record<string, unknown> }[] };
export type PasoDinamico = PasoIA | ((c: ContextoIA) => PasoIA);

export function crearIa() {
  const peticiones: { cuerpo: any; modelo: string }[] = [];
  let guion: PasoDinamico[] = [];
  let paso = 0;
  const sinGuion: string[] = [];
  let n = 0;

  const aTexto = (x: unknown): string => (typeof x === "string" ? x : JSON.stringify(x));

  function contexto(cuerpo: any): ContextoIA {
    const nombres = new Map<string, string>();
    const resultados = new Map<string, any>();
    for (const m of cuerpo.messages ?? []) {
      if (!Array.isArray(m.content)) continue;
      for (const b of m.content) {
        if (b.type === "tool_use") nombres.set(b.id, b.name);
        if (b.type === "tool_result") {
          const crudo = Array.isArray(b.content) ? b.content.map((c: any) => c.text ?? "").join("") : aTexto(b.content);
          let parsed: unknown = crudo;
          try {
            parsed = JSON.parse(crudo);
          } catch {
            /* texto plano */
          }
          resultados.set(nombres.get(b.tool_use_id) ?? b.tool_use_id, parsed);
        }
      }
    }
    return {
      cuerpo,
      sistema: Array.isArray(cuerpo.system) ? cuerpo.system.map((s: any) => s.text ?? "").join("\n") : aTexto(cuerpo.system ?? ""),
      resultado: (nombre) => resultados.get(nombre),
      herramientas: (cuerpo.tools ?? []).map((t: any) => t.name),
    };
  }

  function responder(cuerpo: any): Response {
    peticiones.push({ cuerpo, modelo: cuerpo.model });
    const actual = guion[paso++];
    let salida: PasoIA;
    if (!actual) {
      sinGuion.push(`petición ${peticiones.length} sin paso en el guion`);
      salida = { texto: "(sin guion)" };
    } else {
      salida = typeof actual === "function" ? actual(contexto(cuerpo)) : actual;
    }
    const content =
      "llamadas" in salida
        ? salida.llamadas.map((l) => ({ type: "tool_use", id: `toolu_${++n}`, name: l.nombre, input: l.args }))
        : [{ type: "text", text: salida.texto }];
    return Response.json({
      id: `msg_${++n}`,
      type: "message",
      role: "assistant",
      model: cuerpo.model,
      content,
      stop_reason: "llamadas" in salida ? "tool_use" : "end_turn",
      stop_sequence: null,
      usage: { input_tokens: 1200, output_tokens: 40, cache_creation_input_tokens: 0, cache_read_input_tokens: 0 },
    });
  }

  return {
    peticiones,
    sinGuion,
    /** Lo que el modelo contestará en las próximas llamadas (una por paso del bucle de herramientas). */
    guionar(pasos: PasoDinamico[]) {
      guion = pasos;
      paso = 0;
    },
    /** ¿Se consumió todo el guion? */
    get pendientes() {
      return guion.length - paso;
    },
    responder,
  };
}

// ── El Worker `juan` completo, escuchando en un puerto ──────────────────────

export interface Mundo {
  url: string;
  cluster: Cluster;
  enlace: EstadoDelEnlace;
  puente: ReturnType<typeof crearPuente>;
  ia: ReturnType<typeof crearIa>;
  waToken: string;
  /** Lo que llegó al Worker por HTTP desde Odoo (/odoo/*) y desde fuera (/media/*, webhooks), con su estado. */
  entradas: { metodo: string; ruta: string; estado: number }[];
  /** Un mensaje del cliente por WhatsApp (QR), por el webhook real. Devuelve la respuesta HTTP del Worker. */
  cliente(celular: string, texto: string, extra?: Record<string, unknown>): Promise<Response>;
  /** Lo mismo, pero como si la vendedora lo hubiera escrito desde el teléfono (`propio: true`). */
  desdeElTelefono(celular: string, texto: string): Promise<Response>;
  /** Una petición de Odoo al Worker (`/odoo/*`), con el token que se indique (por defecto el bueno). */
  odooAlWorker(metodo: "GET" | "POST", ruta: string, cuerpo?: unknown, token?: string | null): Promise<{ estado: number; json: any }>;
  /** Espera a que el Durable Object de esa conversación termine lo pendiente (ráfaga, cola de Odoo). */
  quieta(celular: string, ms?: number): Promise<void>;
  /** Olvida la caché de 60 s de la configuración y las herramientas del Worker (después de cambiar ajustes en Odoo). */
  refrescarConfig(): void;
  cerrar(): Promise<void>;
}

export async function levantarWorker(): Promise<Mundo> {
  const waToken = randomBytes(16).toString("hex");
  const enlace: EstadoDelEnlace = { peticiones: [], dormido: 0 };
  const puente = crearPuente(waToken);
  const ia = crearIa();
  const url = `http://127.0.0.1:${JUAN_PUERTO}`;

  vi.stubGlobal("fetch", async (recurso: unknown, init?: RequestInit) => {
    const direccion = typeof recurso === "string" ? recurso : recurso instanceof URL ? recurso.toString() : (recurso as Request).url;
    if (direccion.startsWith("https://api.anthropic.com/")) return ia.responder(JSON.parse(String(init?.body ?? "{}")));
    if (direccion.startsWith("https://api.telegram.org/")) throw new Error("la integración no habla con Telegram");
    return fetchReal(recurso as string, init);
  });

  const cluster = armarCluster({
    JUAN_ODOO_TOKEN: TOKEN_ODOO,
    JUAN_WORKER_TOKEN: TOKEN_WORKER,
    WA_TOKEN: waToken,
    // Una clave de mentira: la API de Anthropic es la guionada de arriba. No es un secreto.
    ANTHROPIC_API_KEY: "sk-ant-integracion-sin-valor",
    DCASA: enlaceDcasa(enlace),
    PUENTE: puente.fetcher,
    ENTORNO: "integracion",
    URL_PUBLICA: url,
    URL_SITIO: "https://dcasapty.com",
    BUFFER_SEGUNDOS: "1",
    TOPE_DIARIO: "50",
  } as never);
  olvidarCaches();

  const pendientes: Promise<unknown>[] = [];
  const ctx = {
    waitUntil: (p: Promise<unknown>) => void pendientes.push(p.catch(() => {})),
    passThroughOnException() {},
  } as unknown as ExecutionContext;

  const servidor = http.createServer(async (req, res) => {
    try {
      const trozos: Buffer[] = [];
      for await (const t of req) trozos.push(t as Buffer);
      const cuerpo = Buffer.concat(trozos);
      const cabeceras = new Headers();
      for (const [k, v] of Object.entries(req.headers)) if (v !== undefined) cabeceras.set(k, Array.isArray(v) ? v.join(", ") : v);
      const r = await worker.fetch(
        new Request(`${url}${req.url}`, { method: req.method, headers: cabeceras, body: req.method === "GET" || req.method === "HEAD" ? undefined : cuerpo }),
        cluster.env,
        ctx,
      );
      entradas.push({ metodo: req.method ?? 'GET', ruta: (req.url ?? '').split('?')[0], estado: r.status });
      res.writeHead(r.status, Object.fromEntries(r.headers.entries()));
      res.end(Buffer.from(await r.arrayBuffer()));
    } catch (e) {
      res.writeHead(500).end(String(e));
    }
  });
  await new Promise<void>((ok, mal) => {
    servidor.once("error", mal);
    servidor.listen(JUAN_PUERTO, "127.0.0.1", () => ok());
  });

  // Las alarmas de Cloudflare: cuando vence la de un Durable Object, se dispara (una a la vez por objeto).
  const enMarcha = new Set<string>();
  const reloj = setInterval(() => {
    for (const [nombre, c] of cluster.conversaciones) {
      if (c.ctx.alarma !== null && c.ctx.alarma <= Date.now() && !enMarcha.has(nombre)) {
        enMarcha.add(nombre);
        c.ctx.alarma = null;
        c.instancia
          .alarm()
          .catch((e) => console.error("[integracion] alarma:", String(e)))
          .finally(() => enMarcha.delete(nombre));
      }
    }
  }, 50);

  const nombreDe = (celular: string) => `whatsapp_qr:${celular}`;
  let contador = 0;
  const entradas: Mundo['entradas'] = [];

  const mundo: Mundo = {
    url,
    cluster,
    enlace,
    puente,
    ia,
    waToken,
    entradas,

    async cliente(celular, texto, extra = {}) {
      return fetchReal(`${url}/webhooks/whatsapp-qr`, {
        method: "POST",
        headers: { "content-type": "application/json", "x-wa-token-b64": tokenParaCabecera(waToken) },
        body: JSON.stringify({
          id_mensaje: `WAMID.${celular}.${++contador}.${randomBytes(3).toString("hex")}`,
          de: `${celular}@s.whatsapp.net`,
          nombre: "Karen",
          tipo: "texto",
          texto,
          ts: new Date().toISOString(),
          propio: false,
          ...extra,
        }),
      });
    },

    desdeElTelefono(celular, texto) {
      return mundo.cliente(celular, texto, { propio: true, nombre: undefined });
    },

    async odooAlWorker(metodo, ruta, cuerpo, token) {
      const t = token === undefined ? TOKEN_WORKER : token;
      const r = await fetchReal(`${url}${ruta}`, {
        method: metodo,
        headers: { ...(t ? { authorization: `Bearer ${t}` } : {}), ...(cuerpo !== undefined ? { "content-type": "application/json" } : {}) },
        body: cuerpo !== undefined ? JSON.stringify(cuerpo) : undefined,
      });
      const texto = await r.text();
      let json: any = null;
      try {
        json = JSON.parse(texto);
      } catch {
        json = texto;
      }
      return { estado: r.status, json };
    },

    async quieta(celular, ms = 20_000) {
      await esperarHasta(
        `la conversación ${celular} quede quieta`,
        async () => {
          const c = cluster.conversaciones.get(nombreDe(celular));
          if (!c) return false;
          const r = (await c.instancia.resumen()) as { pendientes: number; cola: number };
          // La alarma de limpieza (a las 24 h) siempre queda programada: «quieta» es que no haya nada próximo ni pendiente.
          const proxima = c.ctx.alarma !== null && c.ctx.alarma < Date.now() + 5_000;
          return !enMarcha.has(nombreDe(celular)) && r.pendientes === 0 && r.cola === 0 && !proxima;
        },
        ms,
        150,
      );
    },

    refrescarConfig() {
      olvidarCaches();
    },

    async cerrar() {
      clearInterval(reloj);
      await new Promise<void>((ok) => servidor.close(() => ok()));
      await Promise.allSettled(pendientes);
      vi.unstubAllGlobals();
    },
  };
  return mundo;
}
