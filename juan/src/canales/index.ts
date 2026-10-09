// El registro de canales. Agregar un canal = escribir un adaptador (canales/tipos.ts → AdaptadorCanal)
// y ponerlo en esta lista. Nada más del Worker cambia: las rutas, el envío y la salud salen de aquí.

import { crearMeta } from "./meta";
import type { AdaptadorCanal, CanalId } from "./tipos";
import { crearTelegram } from "./telegram";
import { crearWhatsappCloud } from "./whatsappCloud";
import { crearWhatsappQr } from "./whatsappQr";

export function crearAdaptadores(opciones: { fetch?: typeof fetch; dormir?: (ms: number) => Promise<void> } = {}): AdaptadorCanal[] {
  return [crearWhatsappQr(opciones), crearTelegram(opciones), crearMeta(opciones), crearWhatsappCloud(opciones)];
}

export const ADAPTADORES: readonly AdaptadorCanal[] = crearAdaptadores();

export function adaptadorDe(canal: CanalId, lista: readonly AdaptadorCanal[] = ADAPTADORES): AdaptadorCanal | undefined {
  return lista.find((a) => a.canales.includes(canal));
}

export function adaptadorPorRuta(ruta: string, lista: readonly AdaptadorCanal[] = ADAPTADORES): AdaptadorCanal | undefined {
  return lista.find((a) => a.ruta === ruta);
}
