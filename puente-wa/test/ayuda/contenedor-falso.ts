// Un doble de `Container` de @cloudflare/containers y un `ctx` de Durable Object en memoria, para probar
// la clase PuenteWa (vigilancia, época, avisos, copias, envío) sin Cloudflare. Imita lo que importa de la
// librería real: `startAndWaitForPorts` llama a `onStart()` SIEMPRE (también si ya estaba corriendo),
// `destroy()` dispara `onStop()`, `schedule()` AGREGA una tarea, y el entorno se lee al arrancar.
import { sqlDePrueba } from "./sql";

export interface CtxFalso {
  storage: {
    sql: ReturnType<typeof sqlDePrueba>["sql"];
    transactionSync<T>(fn: () => T): T;
    get<T>(k: string): Promise<T | undefined>;
    put(k: string, v: unknown): Promise<void>;
    kv: Map<string, unknown>;
  };
  container: { running: boolean };
  blockConcurrencyWhile(fn: () => Promise<void>): Promise<void>;
  listo: Promise<void>[];
}

export function crearCtx(bd = sqlDePrueba()): CtxFalso {
  const kv = new Map<string, unknown>();
  const listo: Promise<void>[] = [];
  return {
    storage: {
      sql: bd.sql,
      transactionSync: bd.transaccion,
      get: async (k) => structuredClone(kv.get(k)) as any,
      put: async (k, v) => void kv.set(k, structuredClone(v)),
      kv,
    },
    container: { running: false },
    blockConcurrencyWhile(fn) {
      const p = fn();
      listo.push(p);
      return p;
    },
    listo,
  };
}

/** Qué hace el «contenedor» ante cada petición. Los tests lo reemplazan. */
export type Manejador = (url: URL, init?: RequestInit) => Response | Promise<Response>;

export class ContenedorBase {
  envVars: Record<string, string> = {};
  defaultPort?: number;
  sleepAfter: string | number = "10m";
  enableInternet?: boolean;

  arranques: { envVars: Record<string, string> }[] = [];
  paradas: { exitCode: number; reason: string }[] = [];
  programadas: { cuando: number; callback: string }[] = [];
  renovaciones = 0;
  llamadas: { url: string; metodo: string; cuerpo?: string }[] = [];
  manejador: Manejador = () => new Response("{}", { status: 200 });
  /** Si es true, el siguiente `startAndWaitForPorts` falla (la librería lanza si el puerto no llega a abrir). */
  fallarArranque = false;

  constructor(
    public ctx: any,
    public env: any,
  ) {}

  async startAndWaitForPorts(_args?: unknown): Promise<void> {
    if (this.fallarArranque) throw new Error("el puerto 8080 no abrió");
    if (!this.ctx.container.running) {
      this.ctx.container.running = true;
      // El entorno se lee AL ARRANCAR.
      this.arranques.push({ envVars: { ...this.envVars } });
    }
    await this.onStart();
  }

  async destroy(): Promise<void> {
    const estabaCorriendo = this.ctx.container.running;
    this.ctx.container.running = false;
    if (estabaCorriendo) {
      const p = { exitCode: 137, reason: "runtime_signal" };
      this.paradas.push(p);
      await this.onStop(p);
    }
  }

  async onStart(): Promise<void> {}
  async onStop(_p: { exitCode: number; reason: string }): Promise<void> {}
  onError(e: unknown): unknown {
    return e;
  }
  renewActivityTimeout(): void {
    this.renovaciones += 1;
  }
  async schedule(cuando: number, callback: string): Promise<unknown> {
    this.programadas.push({ cuando, callback });
    return { taskId: String(this.programadas.length), callback };
  }
  async containerFetch(url: string | URL, init?: RequestInit): Promise<Response> {
    const u = new URL(String(url));
    this.llamadas.push({ url: u.toString(), metodo: init?.method ?? "GET", cuerpo: typeof init?.body === "string" ? init.body : undefined });
    return this.manejador(u, init);
  }
}

export const jsonResp = (cuerpo: unknown, status = 200) =>
  new Response(JSON.stringify(cuerpo), { status, headers: { "content-type": "application/json" } });
