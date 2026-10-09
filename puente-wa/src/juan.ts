// Entrega de los mensajes entrantes al Worker `juan` (service binding `JUAN`).
//
// Contrato (docs/JUAN.md): `POST /webhooks/whatsapp-qr` con el JSON del puente y el
// token compartido `WA_TOKEN`. La petición lleva el token en las dos formas que usan
// los Workers hermanos —`x-wa-token` (la del CRM de origen) y `Authorization: Bearer`
// (la de Odoo ↔ Juan)—: es el mismo valor y Juan lee la que prefiera.
//
// Worker a Worker de la MISMA cuenta SIEMPRE por service binding: por URL pública da
// el error 1042 de Cloudflare, que se disfraza de 404 y manda a buscar la causa al
// lugar equivocado (lección del CRM de origen).

export interface EntornoJuan {
  JUAN?: Fetcher;
  WA_TOKEN: string;
}

export type ResultadoEntrega =
  | { ok: true; status: number }
  | { ok: false; status: number; definitivo: boolean; motivo: string };

/** Espera entre reintentos rápidos antes de dejar el mensaje en la cola de pendientes. */
export const ESPERAS_ENTREGA_MS = [0, 500];

/** Cuánto se espera la respuesta de Juan en cada intento. */
export const TOPE_JUAN_MS = 40_000;

export async function entregarAJuan(
  env: EntornoJuan,
  cuerpo: string,
  dormir: (ms: number) => Promise<void> = (ms) => new Promise((r) => setTimeout(r, ms)),
): Promise<ResultadoEntrega> {
  if (!env.JUAN) {
    return { ok: false, status: 503, definitivo: false, motivo: "falta el service binding JUAN (¿se desplegó juan?)" };
  }
  let ultimo: ResultadoEntrega = { ok: false, status: 0, definitivo: false, motivo: "sin intentos" };
  for (const espera of ESPERAS_ENTREGA_MS) {
    if (espera) await dormir(espera);
    try {
      const r = await env.JUAN.fetch(
        new Request("https://juan/webhooks/whatsapp-qr", {
          method: "POST",
          headers: {
            "content-type": "application/json",
            "x-wa-token": env.WA_TOKEN,
            authorization: `Bearer ${env.WA_TOKEN}`,
          },
          body: cuerpo,
          // Un Juan que no contesta no cuelga al puente: se trata como fallo reintentable.
          signal: AbortSignal.timeout(TOPE_JUAN_MS),
        }),
      );
      if (r.ok) return { ok: true, status: r.status };
      // Un 4xx es definitivo (cuerpo mal formado, token): repetir no lo arregla.
      // 408 y 429 son «vuelve más tarde», no definitivos.
      const definitivo = r.status >= 400 && r.status < 500 && r.status !== 408 && r.status !== 429;
      ultimo = { ok: false, status: r.status, definitivo, motivo: `Juan contestó ${r.status}` };
      if (definitivo) return ultimo;
    } catch (e) {
      ultimo = { ok: false, status: 0, definitivo: false, motivo: `no se pudo llamar a Juan: ${e instanceof Error ? e.message : String(e)}` };
    }
  }
  return ultimo;
}
