import { describe, expect, it } from "vitest";
import { ColaLlena, EsperaAgotada, crearCola } from "../contenedor/lib/cola.mjs";

const pausa = (ms: number) => new Promise((r) => setTimeout(r, ms));

describe("cola en serie (un solo escritor)", () => {
  it("ejecuta de una en una y en orden, aunque lleguen todas a la vez", async () => {
    const cola = crearCola();
    const eventos: string[] = [];
    const tarea = (n: string, ms: number) => async () => {
      eventos.push(`inicio ${n}`);
      await pausa(ms);
      eventos.push(`fin ${n}`);
      return n;
    };
    const r = await Promise.all([cola.ejecutar(tarea("A", 30)), cola.ejecutar(tarea("B", 5)), cola.ejecutar(tarea("C", 1))]);
    expect(r).toEqual(["A", "B", "C"]);
    expect(eventos).toEqual(["inicio A", "fin A", "inicio B", "fin B", "inicio C", "fin C"]);
  });

  it("una tarea que falla no detiene a las siguientes", async () => {
    const cola = crearCola();
    const falla = cola.ejecutar(async () => {
      throw new Error("boom");
    });
    const sigue = cola.ejecutar(async () => "sigo");
    await expect(falla).rejects.toThrow("boom");
    await expect(sigue).resolves.toBe("sigo");
    expect(cola.pendientes).toBe(0);
  });

  it("cuenta las pendientes y rechaza cuando la fila está llena", async () => {
    const cola = crearCola({ maxPendientes: 2 });
    let suelta!: () => void;
    const bloqueada = new Promise<void>((r) => (suelta = r));
    const a = cola.ejecutar(() => bloqueada);
    const b = cola.ejecutar(async () => "b");
    expect(cola.pendientes).toBe(2);
    await expect(cola.ejecutar(async () => "c")).rejects.toBeInstanceOf(ColaLlena);
    suelta();
    await Promise.all([a, b]);
    expect(cola.pendientes).toBe(0);
    await expect(cola.ejecutar(async () => "d")).resolves.toBe("d");
  });

  it("si a una petición le toca el turno demasiado tarde, se descarta SIN ejecutarse", async () => {
    let t = 0;
    const cola = crearCola({ esperaMaxMs: 1000, ahora: () => t });
    let suelta!: () => void;
    const primera = cola.ejecutar(() => new Promise<void>((r) => (suelta = r)));
    await pausa(5); // la primera ya arrancó (a tiempo) y sigue ocupando el turno
    let ejecutada = false;
    const segunda = cola.ejecutar(async () => {
      ejecutada = true;
    });
    t += 1500; // la segunda lleva esperando más que el tope
    suelta();
    await primera;
    await expect(segunda).rejects.toBeInstanceOf(EsperaAgotada);
    expect(ejecutada).toBe(false);
  });
});
