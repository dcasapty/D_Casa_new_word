/**
 * La pantalla «Conversaciones» de Odoo (addons/dcasa_conversaciones/static/src/js/almacen.js) es JavaScript de navegador sin
 * dependencias de Odoo, así que su lógica de tiempo real se prueba aquí, con un bus de mentira:
 *   · «En vivo» solo está encendido si la conexión lo está, y al reconectar la pantalla se pone al día;
 *   · «Ana está viendo / escribiendo» se mueve con los avisos del bus sin pedir nada al servidor;
 *   · las funciones que se le dejan al bus usan el objeto REACTIVO (si usaran el «crudo», la pantalla no se repintaría).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const RUTA = new URL("../../../addons/dcasa_conversaciones/static/src/js/almacen.js", import.meta.url).href;

type Escucha = (e?: unknown) => void;

function mundo() {
  const escuchas = new Map<string, Escucha[]>();
  const suscritos = new Map<string, Escucha>();
  const llamadas: { metodo: string; args: unknown[] }[] = [];
  const respuestas: Record<string, (args: unknown[]) => unknown> = {
    lista: () => ({ conversaciones: [], total: 0, hay_mas: false, sin_leer_total: 0 }),
    hilo: () => ({ mensajes: [], programados: [], hay_mas: false, conversacion: { id: 7 } }),
    refrescar: () => ({ lista: { conversaciones: [], total: 0, hay_mas: false, sin_leer_total: 0 }, hilo: { mensajes: [], programados: [], hay_mas: false, conversacion: { id: 7 } } }),
    presencia: () => ({ presencia: {} }),
    fijar_disponible: (a) => ({ disponible: a[0] }),
  };
  let fallar: Error | null = null;
  const llamar = async (_modelo: string, metodo: string, args: unknown[]) => {
    llamadas.push({ metodo, args });
    if (fallar && metodo === "fijar_disponible") throw fallar;
    return respuestas[metodo]?.(args);
  };
  const bus = {
    workerState: "IDLE" as string,
    subscribe: (tipo: string, f: Escucha) => suscritos.set(tipo, f),
    unsubscribe: (tipo: string) => suscritos.delete(tipo),
    addEventListener: (tipo: string, f: Escucha) => escuchas.set(tipo, [...(escuchas.get(tipo) ?? []), f]),
    removeEventListener: (tipo: string, f: Escucha) => escuchas.set(tipo, (escuchas.get(tipo) ?? []).filter((x) => x !== f)),
    start: async () => {},
  };
  const avisos: string[] = [];
  const notification = { add: (m: string) => avisos.push(m) };
  const orm = { call: llamar, silent: { call: llamar } };
  return {
    orm,
    bus,
    notification,
    llamadas,
    avisos,
    respuestas,
    suscritos,
    dispara: (tipo: string) => (escuchas.get(tipo) ?? []).forEach((f) => f()),
    escuchasDe: (tipo: string) => escuchas.get(tipo) ?? [],
    falla: (e: Error | null) => (fallar = e),
  };
}

async function crear(m = mundo()) {
  const { Almacen } = (await import(/* @vite-ignore */ RUTA)) as { Almacen: new (o: unknown) => any };
  const almacen = new Almacen({ orm: m.orm, bus: m.bus, notification: m.notification });
  // Lo que hace OWL con `useState`: un proxy. Anota cada lectura y escritura para comprobar que los avisos pasan por él
  // (lo que se lee o escribe por el objeto «crudo» no avisa a OWL y la pantalla no se repinta).
  const escrituras: string[] = [];
  const reactivo = new Proxy(almacen, {
    get(objetivo, clave) {
      escrituras.push(`leyó ${String(clave)}`);
      return objetivo[clave];
    },
    set(objetivo, clave, valor) {
      escrituras.push(String(clave));
      objetivo[clave] = valor;
      return true;
    },
  });
  reactivo.iniciado = true;
  escrituras.length = 0;
  return { m, almacen: reactivo, escrituras };
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-10-10T15:00:00Z"));
  (globalThis as any).window = new EventTarget();
});
afterEach(() => {
  vi.useRealTimers();
  delete (globalThis as any).window;
});

describe("«En vivo»", () => {
  it("empieza apagado, se enciende al conectar y se apaga al caerse o al reconectar", async () => {
    const { m, almacen } = await crear();
    almacen.suscribir();
    expect(almacen.enVivo).toBe(false);
    m.dispara("BUS:CONNECT");
    expect(almacen.enVivo).toBe(true);
    m.dispara("BUS:DISCONNECT");
    expect(almacen.enVivo).toBe(false);
    m.dispara("BUS:CONNECT");
    m.dispara("BUS:RECONNECTING");
    expect(almacen.enVivo).toBe(false);
  });

  it("si la conexión ya estaba abierta (otra pestaña la comparte), arranca encendido", async () => {
    const m = mundo();
    m.bus.workerState = "CONNECTED";
    const { almacen } = await crear(m);
    almacen.suscribir();
    await vi.advanceTimersByTimeAsync(0);
    expect(almacen.enVivo).toBe(true);
  });

  it("si el bus no arranca, queda apagado (no se finge)", async () => {
    const m = mundo();
    m.bus.start = async () => {
      throw new Error("sin bus");
    };
    const { almacen } = await crear(m);
    almacen.suscribir();
    await vi.advanceTimersByTimeAsync(0);
    expect(almacen.enVivo).toBe(false);
  });

  it("al reconectar se enciende y se trae la lista y la conversación abierta (lo perdido no llegó por avisos)", async () => {
    const { m, almacen } = await crear();
    almacen.suscribir();
    almacen.seleccionadaId = 7;
    m.llamadas.length = 0;
    m.dispara("BUS:RECONNECT");
    await vi.advanceTimersByTimeAsync(0);
    expect(almacen.enVivo).toBe(true);
    expect(m.llamadas.map((l) => l.metodo).sort()).toEqual(["ficha", "refrescar"]); // la lista y el hilo, en UNA llamada
  });

  it("los avisos del bus repintan la pantalla: las funciones que se le dejan usan el objeto reactivo", async () => {
    const { m, almacen, escrituras } = await crear();
    almacen.suscribir();
    m.dispara("BUS:CONNECT");
    expect(escrituras).toContain("enVivo");
    escrituras.length = 0;
    m.suscritos.get("dcasa_conversaciones/evento")!({ evento: "escribiendo", conversacion_id: 7, activo: true });
    expect(escrituras).toContain("leyó escribiendoBot");
    escrituras.length = 0;
    m.suscritos.get("dcasa_conversaciones/evento")!({ evento: "presencia", usuario_id: 3, conversacion_id: 7, anterior: null, escribiendo: false });
    expect(escrituras).toContain("leyó presencia");
  });

  it("al desuscribir se quitan las escuchas del bus y de la red", async () => {
    const { m, almacen } = await crear();
    almacen.suscribir();
    almacen.desuscribir();
    expect(m.suscritos.size).toBe(0);
    for (const tipo of ["BUS:CONNECT", "BUS:RECONNECT", "BUS:DISCONNECT", "BUS:RECONNECTING"]) expect(m.escuchasDe(tipo)).toEqual([]);
  });

  it("resincronizar no insiste si se sincronizó hace poco, ni si ya hay una en curso, ni antes de iniciar", async () => {
    const { m, almacen } = await crear();
    m.llamadas.length = 0;
    await almacen.resincronizar(20_000);
    expect(m.llamadas).toEqual([]); // se acaba de crear: ya está al día
    vi.advanceTimersByTime(21_000);
    await Promise.all([almacen.resincronizar(20_000), almacen.resincronizar(20_000)]);
    expect(m.llamadas.filter((l) => l.metodo === "lista" || l.metodo === "refrescar")).toHaveLength(1);
    almacen.iniciado = false;
    m.llamadas.length = 0;
    await almacen.resincronizar();
    expect(m.llamadas).toEqual([]);
  });

  it("al volver la red la pantalla se pone al día", async () => {
    const { m, almacen } = await crear();
    almacen.suscribir();
    m.llamadas.length = 0;
    (globalThis as any).window.dispatchEvent(new Event("online"));
    await vi.advanceTimersByTimeAsync(0);
    expect(m.llamadas.some((l) => l.metodo === "lista")).toBe(true);
  });
});

describe("los avisos del servidor", () => {
  const aviso = (m: ReturnType<typeof mundo>, e: object) => m.suscritos.get("dcasa_conversaciones/evento")!({ evento: "mensaje", autor: "cliente", ...e });

  it("un cambio en la conversación abierta se trae con UNA sola llamada (lista + hilo)", async () => {
    const { m, almacen } = await crear();
    almacen.suscribir();
    almacen.seleccionadaId = 7;
    m.llamadas.length = 0;
    aviso(m, { conversacion_id: 7 });
    aviso(m, { conversacion_id: 7 }); // varios avisos juntos se atienden una vez
    await vi.advanceTimersByTimeAsync(500);
    expect(m.llamadas.map((l) => l.metodo).filter((x) => x !== "ficha")).toEqual(["refrescar"]);
    expect(m.llamadas[0].args).toEqual([expect.any(Object), 30, 7, 50]);
  });

  it("un cambio en OTRA conversación solo repone la lista", async () => {
    const { m, almacen } = await crear();
    almacen.suscribir();
    almacen.seleccionadaId = 7;
    m.llamadas.length = 0;
    aviso(m, { conversacion_id: 9 });
    await vi.advanceTimersByTimeAsync(500);
    expect(m.llamadas.map((l) => l.metodo)).toEqual(["lista"]);
  });

  it("sin conversación abierta, refrescarTodo es solo la lista", async () => {
    const { m, almacen } = await crear();
    m.llamadas.length = 0;
    await almacen.refrescarTodo();
    expect(m.llamadas.map((l) => l.metodo)).toEqual(["lista"]);
  });

  it("si el servidor falla, la pantalla sigue (es tiempo real, no una orden)", async () => {
    const { m, almacen } = await crear();
    almacen.seleccionadaId = 7;
    m.respuestas.refrescar = () => {
      throw new Error("sin red");
    };
    await expect(almacen.refrescarTodo()).resolves.toBeUndefined();
  });

  it("si la conversación abierta cambió mientras llegaba la respuesta, no se pisa con la vieja", async () => {
    const { m, almacen } = await crear();
    almacen.seleccionadaId = 7;
    let soltar!: () => void;
    const espera = new Promise<void>((r) => (soltar = r));
    m.respuestas.refrescar = () => espera.then(() => ({ lista: { conversaciones: [], total: 0, hay_mas: false, sin_leer_total: 0 }, hilo: { mensajes: [{ id: 1, tipo: "mensaje", autor: "cliente", ts: "2026-10-10T15:00:00Z" }], programados: [], hay_mas: false, conversacion: { id: 7 } } })) as any;
    const p = almacen.refrescarTodo();
    almacen.seleccionadaId = 9; // la persona abrió otra
    almacen._numeroDeHilo++;
    soltar();
    await p;
    expect(almacen.mensajes).toEqual([]);
  });
});

describe("«Ana está viendo» / «escribiendo»", () => {
  const equipo = [
    { id: 3, nombre: "Ana Vendedora" },
    { id: 4, nombre: "Beto Vendedor" },
  ];

  async function conEquipo() {
    const r = await crear();
    r.almacen.equipo = equipo;
    r.almacen.suscribir();
    return r;
  }
  const evento = (m: ReturnType<typeof mundo>, e: object) => m.suscritos.get("dcasa_conversaciones/evento")!({ evento: "presencia", escribiendo: false, anterior: null, ...e });

  it("un aviso del bus pone a la persona en la conversación sin pedir nada al servidor", async () => {
    const { m, almacen } = await conEquipo();
    m.llamadas.length = 0;
    evento(m, { usuario_id: 3, conversacion_id: 7 });
    expect(almacen.quienVe(7)).toEqual([{ nombre: "Ana", escribiendo: false }]);
    await vi.advanceTimersByTimeAsync(1000);
    expect(m.llamadas).toEqual([]);
  });

  it("al cambiar de conversación sale de la anterior; al escribir, se marca", async () => {
    const { m, almacen } = await conEquipo();
    evento(m, { usuario_id: 3, conversacion_id: 7 });
    evento(m, { usuario_id: 4, conversacion_id: 7 });
    expect(almacen.quienVe(7).map((g: any) => g.nombre)).toEqual(["Ana", "Beto"]);
    evento(m, { usuario_id: 3, conversacion_id: 8, anterior: 7, escribiendo: true });
    expect(almacen.quienVe(7).map((g: any) => g.nombre)).toEqual(["Beto"]);
    expect(almacen.quienVe(8)).toEqual([{ nombre: "Ana", escribiendo: true }]);
    evento(m, { usuario_id: 3, conversacion_id: null, anterior: 8 }); // cerró la pantalla
    expect(almacen.quienVe(8)).toEqual([]);
  });

  it("sin nuevos pulsos, a los ~55 s se borra solo (alguien que cerró la pestaña sin avisar)", async () => {
    const { m, almacen } = await conEquipo();
    evento(m, { usuario_id: 3, conversacion_id: 7 });
    vi.advanceTimersByTime(54_000);
    expect(almacen.quienVe(7)).toHaveLength(1);
    vi.advanceTimersByTime(2_000);
    expect(almacen.quienVe(7)).toEqual([]);
  });

  it("alguien que no está en el equipo se muestra como «Alguien» (nunca rompe)", async () => {
    const { m, almacen } = await conEquipo();
    evento(m, { usuario_id: 99, conversacion_id: 7 });
    expect(almacen.quienVe(7)[0].nombre).toBe("Alguien");
  });

  it("el pulso trae el mapa completo del servidor y reemplaza lo que había (se corrige solo)", async () => {
    const { m, almacen } = await conEquipo();
    evento(m, { usuario_id: 4, conversacion_id: 7 });
    m.respuestas.presencia = () => ({ presencia: { 9: [{ usuario_id: 3, escribiendo: true }] } });
    almacen.seleccionadaId = 9;
    await almacen.latido(true);
    expect(m.llamadas.at(-1)).toEqual({ metodo: "presencia", args: [9, true] });
    expect(almacen.quienVe(7)).toEqual([]);
    expect(almacen.quienVe(9)).toEqual([{ nombre: "Ana", escribiendo: true }]);
  });

  it("si el pulso falla, la pantalla sigue (es un extra)", async () => {
    const { m, almacen } = await conEquipo();
    m.respuestas.presencia = () => {
      throw new Error("sin red");
    };
    await expect(almacen.latido()).resolves.toBeUndefined();
  });

  it("al teclear avisa «escribiendo» a lo más cada 4 s", async () => {
    const { m, almacen } = await conEquipo();
    m.llamadas.length = 0;
    almacen.avisarQueEscribo();
    almacen.avisarQueEscribo();
    vi.advanceTimersByTime(3_000);
    almacen.avisarQueEscribo();
    expect(m.llamadas.filter((l) => l.metodo === "presencia")).toHaveLength(1);
    vi.advanceTimersByTime(1_500);
    almacen.avisarQueEscribo();
    expect(m.llamadas.filter((l) => l.metodo === "presencia")).toHaveLength(2);
    expect(m.llamadas.every((l) => l.args[1] === true)).toBe(true);
  });

  it("abrir una conversación da un pulso enseguida; salir de la pantalla avisa que no hay ninguna abierta", async () => {
    const { m, almacen } = await conEquipo();
    m.llamadas.length = 0;
    await almacen.abrir(7);
    expect(m.llamadas.find((l) => l.metodo === "presencia")?.args).toEqual([7, false]);
    m.llamadas.length = 0;
    almacen.salir();
    expect(m.llamadas).toEqual([{ metodo: "presencia", args: [null, false] }]);
  });
});

describe("mi disponibilidad", () => {
  it("se marca al instante y se guarda; si falla, vuelve a como estaba y avisa", async () => {
    const { m, almacen } = await crear();
    await almacen.fijarDisponible(false);
    expect(almacen.disponible).toBe(false);
    expect(m.llamadas.at(-1)).toEqual({ metodo: "fijar_disponible", args: [false] });
    m.falla(new Error("sin red"));
    await almacen.fijarDisponible(true);
    expect(almacen.disponible).toBe(false);
    expect(m.avisos.length).toBe(1);
  });
});
