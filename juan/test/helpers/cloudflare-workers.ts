// Doble mínimo del módulo virtual `cloudflare:workers` (solo existe dentro de workerd).
// Lo justo para que las clases de Durable Object se puedan importar y probar en Node.
export class DurableObject<E = unknown> {
  ctx: any;
  env: E;
  constructor(ctx: any, env: E) {
    this.ctx = ctx;
    this.env = env;
  }
}
