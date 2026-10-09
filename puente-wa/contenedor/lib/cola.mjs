// @ts-check
// Una cola en serie: «un solo escritor» de la sesión de WhatsApp.
//
// Todo lo que se escribe por el socket pasa por aquí, de una petición a la vez:
// así dos respuestas a la misma persona nunca se entrelazan, el ritmo de envío
// (1 s entre burbujas, «escribiendo…») se respeta de verdad, y una ráfaga de
// clientes no se convierte en una ráfaga de mensajes.

export class ColaLlena extends Error {
  constructor(pendientes) {
    super(`la cola de envío está llena (${pendientes} peticiones esperando)`);
    this.name = "ColaLlena";
    this.code = "COLA_LLENA";
  }
}

export class EsperaAgotada extends Error {
  constructor(ms) {
    super(`la petición esperó más de ${Math.round(ms / 1000)} s su turno y se descartó`);
    this.name = "EsperaAgotada";
    this.code = "ESPERA_AGOTADA";
  }
}

/**
 * @param {{ maxPendientes?: number, esperaMaxMs?: number, ahora?: () => number }} [opciones]
 */
export function crearCola({ maxPendientes = 20, esperaMaxMs = 90_000, ahora = () => Date.now() } = {}) {
  /** @type {Promise<unknown>} */
  let cadena = Promise.resolve();
  let pendientes = 0;

  return {
    /** Peticiones en curso o esperando turno. */
    get pendientes() {
      return pendientes;
    },
    /**
     * Pone `tarea` en la fila. Se rechaza si la fila está llena o si cuando le
     * toca el turno ya esperó demasiado (la tarea NO llega a ejecutarse: mejor
     * un error claro que mandar un mensaje que ya nadie espera).
     *
     * @template T
     * @param {() => Promise<T>} tarea
     * @returns {Promise<T>}
     */
    ejecutar(tarea) {
      if (pendientes >= maxPendientes) return Promise.reject(new ColaLlena(pendientes));
      pendientes += 1;
      const encolada = ahora();
      const resultado = cadena.then(() => {
        if (ahora() - encolada > esperaMaxMs) throw new EsperaAgotada(esperaMaxMs);
        return tarea();
      });
      // La cadena sigue aunque una tarea falle.
      cadena = resultado.then(
        () => undefined,
        () => undefined,
      );
      return resultado.finally(() => {
        pendientes -= 1;
      });
    },
  };
}
