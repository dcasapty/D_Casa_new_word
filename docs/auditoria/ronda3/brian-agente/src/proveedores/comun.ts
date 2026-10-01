import { ErrorProveedor, type FetchLike } from "../nucleo/tipos";

export interface OpcionesHttp {
  /** URL base del proveedor o de AI Gateway (p. ej. …/v1/{cuenta}/{gateway}/custom-meta/v1). */
  base: string;
  clave: string;
  fetch?: FetchLike;
  /** Cabeceras extra (cf-aig-authorization, etc.). */
  cabeceras?: Record<string, string>;
  /** Si va por AI Gateway: no guardar prompts en los logs (solo métricas). */
  gateway?: boolean;
  timeoutMs?: number;
}

export async function postJson(op: OpcionesHttp, ruta: string, cabeceras: Record<string, string>, cuerpo: unknown, senal?: AbortSignal): Promise<unknown> {
  const f = op.fetch ?? fetch;
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), op.timeoutMs ?? 90_000);
  senal?.addEventListener("abort", () => ctrl.abort());
  let r: Response;
  try {
    r = await f(`${op.base.replace(/\/$/, "")}${ruta}`, {
      method: "POST",
      headers: { "content-type": "application/json", ...cabeceras, ...(op.cabeceras ?? {}) },
      body: JSON.stringify(cuerpo),
      signal: ctrl.signal,
    });
  } catch (e) {
    throw new ErrorProveedor(`No pude conectarme con el proveedor de IA (${(e as Error).name}).`, true);
  } finally {
    clearTimeout(t);
  }
  if (r.ok) return r.json();
  const detalle = (await r.text()).slice(0, 300);
  if (r.status === 429 || r.status >= 500) throw new ErrorProveedor(`Proveedor saturado o caído (${r.status}).`, true, r.status);
  if (r.status === 402) throw new ErrorProveedor("Sin saldo en el proveedor de IA (402).", false, 402);
  if (r.status === 401 || r.status === 403) throw new ErrorProveedor("Clave de IA inválida o sin permiso.", false, r.status);
  throw new ErrorProveedor(`El proveedor rechazó la solicitud (${r.status}): ${detalle}`, false, r.status);
}
