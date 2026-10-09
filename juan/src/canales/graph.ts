// Versión de la Graph API de Meta en UN solo sitio (Messenger, Instagram y WhatsApp Cloud la comparten).
// Meta retira cada versión ~2 años después de publicarla: cuando pasa, las llamadas fallan sin que nadie
// toque el código. Se puede pisar con la variable GRAPH_API_VERSION (wrangler.jsonc) sin esperar un release.

export const GRAPH_API_VERSION = "v26.0";

export function versionGraph(env: { GRAPH_API_VERSION?: string }): string {
  const v = env.GRAPH_API_VERSION?.trim();
  return v && /^v\d+\.\d+$/.test(v) ? v : GRAPH_API_VERSION;
}

export function urlGraph(env: { GRAPH_API_VERSION?: string }, ruta: string): string {
  return `https://graph.facebook.com/${versionGraph(env)}/${ruta.replace(/^\//, "")}`;
}
