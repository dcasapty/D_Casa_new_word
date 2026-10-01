import type { Libro } from "./libro";
import { ErrorProveedor, type Persona, type Proveedor, type Respuesta, type Solicitud } from "./tipos";

export interface Destino {
  proveedor: string;
  modelo: string;
}

/** Rutas por tarea, como DATOS (no código). La primera que esté autorizada y responda, gana. */
export interface Rutas {
  principal: Destino[];
  economica: Destino[];
}

export interface Intento {
  destino: Destino;
  error?: string;
}

export interface ResultadoRuta {
  respuesta: Respuesta;
  destino: Destino;
  intentos: Intento[];
}

export class SinRuta extends Error {}

/**
 * Ruteo multi-modelo con respaldo y disyuntor simple (3 fallos seguidos ⇒ 60 s sin usar ese proveedor).
 * Un 400 se considera error nuestro (cuerpo mal formado): no se reintenta en otro proveedor.
 */
export class Enrutador {
  private fallos = new Map<string, { seguidos: number; abiertoHasta: number }>();

  constructor(
    private readonly proveedores: Record<string, Proveedor>,
    private readonly rutas: Rutas,
    private readonly libro: Libro,
    private readonly reloj: () => number,
  ) {}

  async llamar(base: Omit<Solicitud, "modelo">, persona: Persona, mes: string): Promise<ResultadoRuta> {
    const intentos: Intento[] = [];
    let ruta = this.rutas.principal;
    const primera = ruta[0];
    if (primera) {
      const a = await this.libro.autorizar(persona, primera.proveedor, primera.modelo, mes);
      if (a.permitido && a.degradar) ruta = this.rutas.economica;
    }
    for (const destino of ruta) {
      const prov = this.proveedores[destino.proveedor];
      if (!prov) { intentos.push({ destino, error: "proveedor no configurado" }); continue; }
      const estado = this.fallos.get(destino.proveedor);
      if (estado && estado.abiertoHasta > this.reloj()) { intentos.push({ destino, error: "disyuntor abierto" }); continue; }
      const aut = await this.libro.autorizar(persona, destino.proveedor, destino.modelo, mes);
      if (!aut.permitido) { intentos.push({ destino, error: aut.motivo }); continue; }
      try {
        const respuesta = await prov.chatear({ ...base, modelo: destino.modelo });
        this.fallos.delete(destino.proveedor);
        intentos.push({ destino });
        return { respuesta, destino, intentos };
      } catch (e) {
        if (!(e instanceof ErrorProveedor)) throw e;
        intentos.push({ destino, error: e.message });
        if (e.estado === 400) throw e;
        const f = this.fallos.get(destino.proveedor) ?? { seguidos: 0, abiertoHasta: 0 };
        f.seguidos += 1;
        if (f.seguidos >= 3) f.abiertoHasta = this.reloj() + 60_000;
        this.fallos.set(destino.proveedor, f);
      }
    }
    const err = new SinRuta(intentos.map((i) => `${i.destino.proveedor}/${i.destino.modelo}: ${i.error}`).join(" | "));
    throw err;
  }
}
