import { Container, getContainer } from "@cloudflare/containers";

import { handleRequest, runScheduled } from "./handler";

export interface Env {
  ODOO: DurableObjectNamespace<OdooContainer>;
  // Variables (wrangler.jsonc > vars)
  CANONICAL_HOST?: string;
  APP_VERSION?: string;
  DB_HOST: string;
  DB_PORT?: string;
  DB_NAME?: string;
  DB_USER: string;
  DB_SSLMODE?: string;
  // Secretos (wrangler secret put …)
  DB_PASSWORD: string;
  /** Clave del usuario `admin` de Odoo (se fija al crear la base; ver docs/DESPLIEGUE.md). */
  ADMIN_PASSWORD: string;
  /**
   * Contraseña maestra de Odoo (`admin_passwd`), distinta de la de `admin`. Opcional:
   * si falta, el contenedor genera una aleatoria en cada arranque y no la muestra.
   */
  ODOO_MASTER_PASSWORD?: string;
  /** Pimienta del PIN de los socios. Se genera una vez y NUNCA se cambia (ver docs/DESPLIEGUE.md). */
  DCASA_PIN_PEPPER: string;
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

/** Variables opcionales que se pasan tal cual al contenedor solo si están definidas. */
export const OPTIONAL_CONTAINER_VARS = [
  "ODOO_MASTER_PASSWORD",
  "BRIAN_PROVEEDOR",
  "BRIAN_MODELO",
  "BRIAN_BASE_URL",
  "BRIAN_HERRAMIENTAS_MAX",
  "BRIAN_API_KEY",
  "TELEGRAM_BOT_TOKEN",
  "BRIAN_TELEGRAM_SECRETO",
] as const;

/** Una sola instancia de Odoo: toda la tienda comparte el mismo contenedor. */
const INSTANCE = "odoo-main";

export class OdooContainer extends Container<Env> {
  defaultPort = 8069;
  // Odoo tarda en arrancar: mejor mantenerlo despierto un buen rato.
  sleepAfter = "30m";
  enableInternet = true; // correo saliente, pasarelas de pago, WhatsApp, etc.
  pingEndpoint = "web/health";

  constructor(ctx: ConstructorParameters<typeof Container<Env>>[0], env: Env) {
    super(ctx, env);
    this.envVars = {
      DB_HOST: env.DB_HOST,
      DB_PORT: env.DB_PORT ?? "5432",
      DB_NAME: env.DB_NAME ?? "dcasa",
      DB_USER: env.DB_USER,
      DB_PASSWORD: env.DB_PASSWORD,
      DB_SSLMODE: env.DB_SSLMODE ?? "require",
      ADMIN_PASSWORD: env.ADMIN_PASSWORD,
      APP_VERSION: env.APP_VERSION ?? "dev",
      DCASA_PIN_PEPPER: env.DCASA_PIN_PEPPER,
    };
    for (const name of OPTIONAL_CONTAINER_VARS) {
      const value = env[name];
      if (value) this.envVars[name] = value;
    }
  }

  override onError(error: unknown): unknown {
    console.error("Odoo container error", error);
    throw error;
  }
}

function odoo(env: Env) {
  return getContainer(env.ODOO, INSTANCE);
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    return handleRequest(request, {
      forward: (upstream) => odoo(env).fetch(upstream),
      cache: caches.default,
      waitUntil: (promise) => ctx.waitUntil(promise),
      canonicalHost: env.CANONICAL_HOST,
    });
  },

  /**
   * Cron horario (wrangler.jsonc): si Odoo duerme, lo despierta una vez para que
   * corran sus acciones planificadas; si ya está encendido no hace nada. Ver
   * runScheduled() en src/handler.ts y docs/DESPLIEGUE.md → «Cron del Worker».
   */
  async scheduled(_controller: ScheduledController, env: Env, ctx: ExecutionContext): Promise<void> {
    const container = odoo(env);
    ctx.waitUntil(
      runScheduled({
        status: async () => (await container.getState()).status,
        wake: () => container.fetch(new Request("http://odoo/web/health")),
      }).then((resultado) => console.log(`cron: Odoo ${resultado}`)),
    );
  },
} satisfies ExportedHandler<Env>;
