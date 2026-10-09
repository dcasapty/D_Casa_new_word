// Puente de WhatsApp por QR — Worker `dcasa-puente-wa`.
//
// Worker APARTE de `juan` a propósito (como en el CRM de origen): `juan` se publica con
// un solo `wrangler deploy`, y si el contenedor se le colgara encima, una imagen que no
// construye bloquearía publicar un cambio del bot. Aquí, lo peor que pasa es que WhatsApp
// se cae y `juan` sigue vivo (contestando por los demás canales).
//
// Contrato con Juan: docs/JUAN.md, «Worker juan ↔ puente QR». Operación y recuperación:
// docs/JUAN_PUENTE.md.

import { PuenteWa } from "./puente-do";
import { json, manejar } from "./router";
import type { Env, PuenteStub } from "./tipos";
import { enmascarar } from "../contenedor/lib/numeros.mjs";

export { PuenteWa };

/** Un solo contenedor: dos sockets sobre el mismo número se tumban entre sí. */
function instancia(env: Env): PuenteStub {
  return env.WA.get(env.WA.idFromName("unico")) as unknown as PuenteStub;
}

export default {
  /**
   * El cron (cada minuto). Despierta al Durable Object, que solo reanuda la vigilancia si
   * su cadena de alarmas se cortó. No duplica a la vigilancia interna: la respalda. La de
   * adentro es rápida y barata pero depende de que el DO siga en pie; ésta llega desde fuera
   * aunque el DO se haya desalojado — que es exactamente lo que dejó el canal mudo una
   * noche entera. No lanza: un cron que revienta no deja rastro útil.
   *
   * Siempre despierta al DO, también sin secretos: es el DO quien decide (si falta algo, no
   * enciende el contenedor y apaga el que esté corriendo — por ejemplo si la dueña borra WA_TOKEN
   * del panel para detener el canal).
   */
  async scheduled(_evento: ScheduledController, env: Env): Promise<void> {
    try {
      await instancia(env).despertar();
    } catch (e) {
      console.error("cron:", enmascarar(e instanceof Error ? e.message : String(e)));
    }
  },

  async fetch(request: Request, env: Env): Promise<Response> {
    try {
      return await manejar(request, env, () => instancia(env));
    } catch (e) {
      // El detalle va al registro (sin números ni textos); a quien llama, un mensaje corto.
      console.error("puente:", enmascarar(e instanceof Error ? e.message : String(e)));
      return json(500, { error: "Error interno del puente.", detalle: enmascarar(e instanceof Error ? e.message : String(e)).slice(0, 200) });
    }
  },
} satisfies ExportedHandler<Env>;
