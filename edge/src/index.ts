import { Container, getContainer, type StopParams } from "@cloudflare/containers";

import {
  colaDeSalida,
  debeRearrancar,
  handleRequest,
  politicaDeSueno,
  runScheduled,
  secretosFaltantes,
  servirConArranque,
  tareaDelCron,
  variablesDelContenedor,
  type ResultadoRespaldo,
  type SaludContenedor,
} from "./handler";

export interface Env {
  ODOO: DurableObjectNamespace<OdooContainer>;
  // Variables (wrangler.jsonc > vars; distintas en env.staging)
  CANONICAL_HOST?: string;
  APP_VERSION?: string;
  /** "produccion" o "staging": el contenedor lo usa para no mezclar respaldos. */
  DCASA_ENTORNO?: string;
  /** Bucket de R2 de los respaldos (uno por entorno). */
  R2_BUCKET?: string;
  /** Vacío/"nunca" = 24/7; una duración ("1h") = duerme sin visitas (ver politicaDeSueno). */
  ODOO_DORMIR_TRAS?: string;
  // Secretos (wrangler secret put …; ver edge/CONTRATO_CONTENEDOR.md)
  /** Clave del usuario `admin` de Odoo (se fija al crear la base; ver docs/DESPLIEGUE.md). */
  ADMIN_PASSWORD?: string;
  /**
   * Contraseña maestra de Odoo (`admin_passwd`), distinta de la de `admin`. Opcional:
   * si falta, el contenedor genera una aleatoria en cada arranque y no la muestra.
   */
  ODOO_MASTER_PASSWORD?: string;
  /** Pimienta del PIN de los socios. Se genera una vez y NUNCA se cambia (ver docs/DESPLIEGUE.md). */
  DCASA_PIN_PEPPER?: string;
  /** `https://<ACCOUNT_ID>.r2.cloudflarestorage.com` (endpoint S3 de R2). */
  R2_ENDPOINT?: string;
  /** Token de API de R2 (S3) con lectura y escritura SOLO sobre R2_BUCKET. */
  R2_ACCESS_KEY_ID?: string;
  R2_SECRET_ACCESS_KEY?: string;
  /** Clave de cifrado del repositorio de pgBackRest. Perderla = perder los respaldos. */
  PGBACKREST_CIPHER_PASS?: string;
  /** Opcional: habilita `POST /__edge/respaldo` (≥ 32 caracteres). */
  RESPALDO_TOKEN?: string;
  // Brian, el asistente (opcionales; ver docs/BRIAN.md y docs/DESPLIEGUE.md).
  BRIAN_PROVEEDOR?: string;
  BRIAN_MODELO?: string;
  BRIAN_BASE_URL?: string;
  BRIAN_HERRAMIENTAS_MAX?: string;
  /** Secreto: clave del proveedor de IA. */
  BRIAN_API_KEY?: string;
  /** Secreto: token del bot de Telegram (@BotFather). */
  TELEGRAM_BOT_TOKEN?: string;
  /** Secreto: ruta y encabezado del webhook de Telegram. */
  BRIAN_TELEGRAM_SECRETO?: string;
}

/**
 * Una sola instancia de Odoo + PostgreSQL (singleton): toda la tienda usa el mismo
 * Durable Object y por tanto el mismo contenedor. `max_instances: 1` en wrangler.jsonc
 * impide que Cloudflare encienda un segundo contenedor (dos PostgreSQL escribiendo al
 * mismo repositorio de R2 serían dos contabilidades distintas).
 */
const INSTANCE = "odoo-main";

/** Puerto de Odoo. El contrato con la imagen: no escucha hasta que la base está lista. */
const PUERTO = 8069;
/** Tope para que Odoo abra el puerto: restauración desde R2 (~1 min medido) + arranque. */
const TOPE_ARRANQUE_MS = 180_000;
/** Si un arranque falla, no se reintenta antes de esto (evita restaurar desde R2 en bucle). */
const PAUSA_TRAS_FALLO_MS = 30_000;
/** Tiempo máximo de `/dcasa/salud`. */
const TIMEOUT_SALUD_MS = 5_000;
/**
 * Respaldo diario: el script de la imagen, con tope de 14 min (el evento del cron
 * tiene 15 min de CPU/espera; `timeout` mata también a sus hijos).
 */
const COMANDO_RESPALDO = ["timeout", "--kill-after=30", "840", "/usr/local/bin/dcasa-respaldo"];

export class OdooContainer extends Container<Env> {
  defaultPort = PUERTO;
  enableInternet = true; // R2, correo saliente, pasarelas de pago, WhatsApp, IA de Brian.
  // waitForPort hace fetch a `http://<pingEndpoint>`: cualquier respuesta HTTP = puerto listo.
  pingEndpoint = "localhost/web/health";

  private readonly siempreEncendido: boolean;
  private arranque?: Promise<void>;
  private ultimoFalloArranque = 0;
  private respaldoEnCurso = false;

  constructor(ctx: ConstructorParameters<typeof Container<Env>>[0], env: Env) {
    const politica = politicaDeSueno(env.ODOO_DORMIR_TRAS);
    // sleepAfter va por opciones: un inicializador de campo lo pisaría después.
    super(ctx, env, { sleepAfter: politica.sleepAfter });
    this.siempreEncendido = politica.siempreEncendido;
    this.envVars = variablesDelContenedor(env);
  }

  /** Visitas: si Odoo no está listo, arranca y responde 503 amable mientras restaura. */
  override async fetch(request: Request): Promise<Response> {
    return servirConArranque(request, {
      listo: () => this.estaListo(),
      arrancar: () => this.iniciarArranque(),
      reenviar: (upstream) => this.containerFetch(upstream),
      faltantes: () => secretosFaltantes(this.env),
    });
  }

  private async estaListo(): Promise<boolean> {
    if (!this.ctx.container?.running) return false;
    return (await this.getState()).status === "healthy";
  }

  /** Un solo arranque a la vez; las peticiones que llegan mientras tanto lo comparten. */
  private iniciarArranque(): Promise<void> {
    if (this.arranque) return this.arranque;
    if (Date.now() - this.ultimoFalloArranque < PAUSA_TRAS_FALLO_MS) {
      return Promise.reject(new Error("arranque en pausa tras un fallo reciente"));
    }
    console.log(JSON.stringify({ evento: "arranque_iniciado" }));
    const inicio = Date.now();
    this.arranque = this.startAndWaitForPorts({
      ports: PUERTO,
      cancellationOptions: { portReadyTimeoutMS: TOPE_ARRANQUE_MS, instanceGetTimeoutMS: 30_000 },
    })
      .then(() => console.log(JSON.stringify({ evento: "arranque_listo", duracionMs: Date.now() - inicio })))
      .catch((error: unknown) => {
        this.ultimoFalloArranque = Date.now();
        console.error(JSON.stringify({ evento: "arranque_fallido", duracionMs: Date.now() - inicio, error: String(error) }));
        throw error;
      })
      .finally(() => {
        this.arranque = undefined;
      });
    return this.arranque;
  }

  /** 24/7: el temporizador de inactividad se revisa, pero nunca apaga el contenedor. */
  override async onActivityExpired(): Promise<void> {
    if (this.siempreEncendido) return;
    console.log(JSON.stringify({ evento: "contenedor_inactivo", accion: "apagar" }));
    await this.stop(); // SIGTERM: la imagen archiva el WAL antes de salir.
  }

  override async onStop(params: StopParams): Promise<void> {
    // reason "runtime_signal" = lo paró Cloudflare (rollout, reinicio de host, sueño);
    // "exit" = el proceso terminó solo (fallo de restauración, OOM, error de Odoo).
    const ahora = Date.now();
    const ultimo = await this.ctx.storage.get<number>("ultimoRearranque");
    const rearrancar = debeRearrancar(this.siempreEncendido, ahora, ultimo);
    const registro = { evento: "contenedor_detenido", exitCode: params.exitCode, motivo: params.reason, rearrancar };
    if (params.exitCode === 0) console.log(JSON.stringify(registro));
    else console.error(JSON.stringify(registro));
    if (rearrancar) {
      await this.ctx.storage.put("ultimoRearranque", ahora);
      await this.schedule(30, "rearrancar");
    }
  }

  override onError(error: unknown): unknown {
    console.error(JSON.stringify({ evento: "contenedor_error", error: String(error) }));
    throw error;
  }

  /** Callback de `schedule()` tras una parada en 24/7. */
  async rearrancar(): Promise<void> {
    if ((await this.estaListo()) || secretosFaltantes(this.env).length) return;
    await this.iniciarArranque().catch(() => undefined); // ya quedó registrado
  }

  /** Para `/__edge/health`: estado real sin encender nada. */
  async salud(): Promise<SaludContenedor> {
    const faltan = secretosFaltantes(this.env);
    const estado = await this.getState();
    const contenedor = this.ctx.container?.running ? estado.status : "stopped";
    if (contenedor !== "healthy") return { contenedor, faltan };
    try {
      const respuesta = await this.containerFetch(
        new Request("http://localhost/dcasa/salud", { signal: AbortSignal.timeout(TIMEOUT_SALUD_MS) }),
      );
      const cuerpo = (await respuesta.text()).slice(0, 500);
      return { contenedor, faltan, odoo: { status: respuesta.status, cuerpo } };
    } catch (error) {
      return { contenedor, faltan, odoo: { error: String(error) } };
    }
  }

  /**
   * Respaldo lógico diario dentro del contenedor (contrato en edge/CONTRATO_CONTENEDOR.md).
   * No enciende el contenedor: si está apagado no hay nada nuevo que respaldar (todo
   * lo confirmado ya está en el WAL archivado en R2).
   */
  async respaldar(origen: "cron" | "manual"): Promise<ResultadoRespaldo> {
    if (this.respaldoEnCurso) return { estado: "en_curso" };
    if (!(await this.estaListo())) return { estado: "omitido", motivo: "Odoo no está encendido" };
    this.respaldoEnCurso = true;
    const inicio = Date.now();
    try {
      this.renewActivityTimeout();
      const proceso = await this.ctx.container!.exec(COMANDO_RESPALDO, {
        env: { ...this.envVars, DCASA_RESPALDO_ORIGEN: origen },
        stdout: "pipe",
        stderr: "combined",
      });
      const salida = await proceso.output();
      const resultado: ResultadoRespaldo = {
        estado: salida.exitCode === 0 ? "ok" : "fallo",
        codigo: salida.exitCode,
        duracionMs: Date.now() - inicio,
        salida: colaDeSalida(new TextDecoder().decode(salida.stdout)),
      };
      return resultado;
    } catch (error) {
      return { estado: "fallo", duracionMs: Date.now() - inicio, motivo: String(error) };
    } finally {
      this.respaldoEnCurso = false;
    }
  }
}

function odoo(env: Env) {
  return getContainer(env.ODOO, INSTANCE);
}

function registrarRespaldo(resultado: ResultadoRespaldo, origen: string): ResultadoRespaldo {
  const linea = JSON.stringify({ evento: "respaldo", origen, ...resultado });
  if (resultado.estado === "ok") console.log(linea);
  else console.error(linea);
  return resultado;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    return handleRequest(request, {
      forward: (upstream) => odoo(env).fetch(upstream),
      cache: caches.default,
      waitUntil: (promise) => ctx.waitUntil(promise),
      canonicalHost: env.CANONICAL_HOST,
      salud: () => odoo(env).salud(),
      respaldo: {
        token: env.RESPALDO_TOKEN,
        respaldar: async () => registrarRespaldo(await odoo(env).respaldar("manual"), "manual"),
      },
    });
  },

  /**
   * Crons (wrangler.jsonc, ver CRON_HORARIO y CRON_RESPALDO en src/handler.ts):
   * - horario: si Odoo está apagado lo despierta; si está encendido no hace nada;
   * - diario de madrugada (Panamá): respaldo lógico dentro del contenedor.
   */
  async scheduled(controller: ScheduledController, env: Env, ctx: ExecutionContext): Promise<void> {
    const container = odoo(env);
    if (tareaDelCron(controller.cron) === "respaldo") {
      ctx.waitUntil(container.respaldar("cron").then((resultado) => registrarRespaldo(resultado, "cron")));
      return;
    }
    ctx.waitUntil(
      runScheduled({
        status: async () => (await container.getState()).status,
        wake: () => container.fetch(new Request("http://odoo/web/health")),
      }).then((resultado) => console.log(`cron: Odoo ${resultado}`)),
    );
  },
} satisfies ExportedHandler<Env>;
