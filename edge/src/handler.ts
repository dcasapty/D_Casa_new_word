import { forwardedHeaders, isCacheableResponse, route, withSecurityHeaders } from "./routing";

export interface EdgeDeps {
  /** Envía la petición al contenedor de Odoo. */
  forward: (request: Request) => Promise<Response>;
  /** Caché del borde (caches.default en producción). */
  cache?: Pick<Cache, "match" | "put">;
  /** Para tareas en segundo plano (ctx.waitUntil). */
  waitUntil?: (promise: Promise<unknown>) => void;
  canonicalHost?: string;
}

export async function handleRequest(request: Request, deps: EdgeDeps): Promise<Response> {
  const url = new URL(request.url);
  const decision = route(url, request.method, deps.canonicalHost);

  switch (decision.kind) {
    case "health":
      return new Response("ok", { headers: { "Content-Type": "text/plain" } });
    case "blocked":
      return new Response("Not Found", { status: 404 });
    case "redirect":
      return Response.redirect(decision.location, decision.status);
  }

  const upstream = new Request(request, { headers: forwardedHeaders(request) });

  if (decision.cacheable && deps.cache) {
    const cacheKey = new Request(url.toString(), { method: "GET" });
    const hit = await deps.cache.match(cacheKey);
    // Lo servido desde la caché también lleva HSTS, nosniff, etc. (Q-03).
    if (hit) return withSecurityHeaders(hit);

    const response = await deps.forward(upstream);
    if (request.method === "GET" && isCacheableResponse(response)) {
      // Se guarda la copia tal como la dio Odoo; las cabeceras se agregan al servir.
      const put = deps.cache.put(cacheKey, response.clone());
      if (deps.waitUntil) {
        deps.waitUntil(put);
      } else {
        await put;
      }
    }
    return withSecurityHeaders(response);
  }

  return withSecurityHeaders(await deps.forward(upstream));
}

export interface ScheduledDeps {
  /** Estado del contenedor sin despertarlo (`Container.getState()`). */
  status: () => Promise<string>;
  /** Petición que despierta a Odoo (enciende el contenedor si está apagado). */
  wake: () => Promise<Response>;
}

/**
 * Cron horario del Worker. No mantiene el contenedor despierto a la fuerza:
 *
 * - Si Odoo ya está encendido, no hace nada: su propio hilo de cron
 *   (`max_cron_threads`) corre las acciones planificadas.
 * - Si está apagado (durmió por `sleepAfter` sin visitas), lo despierta una vez
 *   para que Odoo corra lo pendiente (cola de correo, cron horario de socios…);
 *   luego vuelve a dormir solo si nadie lo usa.
 */
export async function runScheduled(deps: ScheduledDeps): Promise<"encendido" | "despertado"> {
  const status = await deps.status();
  if (status === "running" || status === "healthy") return "encendido";
  const response = await deps.wake();
  // El cuerpo no interesa; se descarta para liberar la conexión.
  await response.body?.cancel();
  return "despertado";
}
