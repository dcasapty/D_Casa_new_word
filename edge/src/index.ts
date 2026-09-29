import { Container, getContainer } from "@cloudflare/containers";

import { handleRequest } from "./handler";

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
  ADMIN_PASSWORD: string;
  /** Pimienta del PIN de los socios. Se genera una vez y NUNCA se cambia (ver docs/DESPLIEGUE.md). */
  DCASA_PIN_PEPPER: string;
}

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
   * Cron: despierta Odoo cada pocos minutos para que corran sus acciones
   * planificadas (correos, recordatorios, conciliaciones) aunque no haya visitas.
   */
  async scheduled(_controller: ScheduledController, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(odoo(env).fetch(new Request("http://odoo/web/health")));
  },
} satisfies ExportedHandler<Env>;
