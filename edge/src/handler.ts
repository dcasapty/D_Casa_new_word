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
    if (hit) return hit;

    const response = await deps.forward(upstream);
    if (request.method === "GET" && isCacheableResponse(response)) {
      const put = deps.cache.put(cacheKey, response.clone());
      deps.waitUntil ? deps.waitUntil(put) : await put;
    }
    return response;
  }

  return withSecurityHeaders(await deps.forward(upstream));
}
