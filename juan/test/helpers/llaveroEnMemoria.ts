// El «llavero» de la llave de Instagram en memoria (en producción es el Durable Object `Global`), con el mismo «cambiar si nadie
// lo cambió» atómico: la comparación y el cambio pasan sin esperas en medio, como dentro del Durable Object.
import type { Llavero } from "../../src/canales/instagramLlave";

export function llaveroEnMemoria(inicial: Record<string, string> = {}): Llavero & { datos: Map<string, string> } {
  const datos = new Map(Object.entries(inicial));
  return {
    datos,
    leer: async (_env, clave) => datos.get(clave) ?? null,
    cambiarSi: async (_env, clave, antes, despues) => {
      if ((datos.get(clave) ?? null) !== antes) return false;
      datos.set(clave, despues);
      return true;
    },
  };
}
