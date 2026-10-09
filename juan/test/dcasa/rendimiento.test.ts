/**
 * Rendimiento: cada herramienta pasa por Odoo (service binding → contenedor), así que
 *   · las de LECTURA se guardan 60 s en el Durable Object de la conversación (mismos argumentos);
 *   · las herramientas independientes de un mismo paso corren juntas;
 *   · el cliente ve «escribiendo…» mientras el bot piensa, si el canal lo permite.
 * Y lo importante: la caché jamás mezcla datos de una conversación (o de un celular) con otra.
 */
import { describe, expect, it } from "vitest";
import { argumentosEstables, construirHerramientas, HERRAMIENTAS_DE_LECTURA, RegistroDelTurno } from "../../src/motor/herramientas";
import { crearMundo } from "../helpers/mundo";
import { OdooFalso } from "../helpers/odooFalso";

const buscar = (consulta: string) => ({ nombre: "buscar_productos", args: { consulta } });

describe("caché de 60 s de las herramientas de lectura", () => {
  it("la misma consulta dos veces seguidas: un solo viaje a Odoo, y el modelo recibe lo mismo las dos veces", async () => {
    const m = crearMundo();
    const g = m.guion([
      { llamadas: [buscar("cama")] },
      { texto: "La Cama Queen Milán está en $499.00 + ITBMS." },
      { llamadas: [buscar("cama")] },
      { texto: "Sigue en $499.00 + ITBMS." },
    ]);
    await m.conversar("precio de la cama");
    await m.conversar("¿y cuánto era la cama?");
    expect(m.odoo.de("buscar_productos")).toHaveLength(1);
    expect(g.prompts()[3]).toContain('"precio_texto":"$499.00 + ITBMS"');
    expect(m.canal.textos.at(-1)).toBe("Sigue en $499.00 + ITBMS.");
  });

  it("con lo guardado también se arma el registro del turno: precios (ITBMS) y fotos", async () => {
    const m = crearMundo();
    m.guion([
      { llamadas: [buscar("cama")] },
      { texto: "Está en $499." },
      { llamadas: [buscar("cama"), { nombre: "enviar_foto_producto", args: { codigo: "CAMA-Q-001" } }] },
      { texto: "Cuesta $499. Te envío la foto." },
    ]);
    await m.conversar("precio de la cama");
    await m.conversar("el precio otra vez y la foto");
    expect(m.odoo.de("buscar_productos")).toHaveLength(1);
    expect(m.canal.textos.at(-1)).toContain("$499 + ITBMS");
    expect(m.canal.medios).toHaveLength(1);
  });

  it("a los 60 s ya no sirve: se vuelve a preguntar a Odoo (un precio puede haber cambiado)", async () => {
    const m = crearMundo();
    m.guion([{ llamadas: [buscar("cama")] }, { texto: "Uno." }, { llamadas: [buscar("cama")] }, { texto: "Dos." }]);
    await m.conversar("precio de la cama");
    await m.pasar(61_000);
    await m.conversar("¿y ahora?");
    expect(m.odoo.de("buscar_productos")).toHaveLength(2);
  });

  it("antes de los 60 s sí sirve, aunque haya pasado casi un minuto", async () => {
    const m = crearMundo();
    m.guion([{ llamadas: [buscar("cama")] }, { texto: "Uno." }, { llamadas: [buscar("cama")] }, { texto: "Dos." }]);
    await m.conversar("precio de la cama");
    await m.pasar(20_000);
    await m.conversar("¿y ahora?");
    expect(m.odoo.de("buscar_productos")).toHaveLength(1);
  });

  it("otros argumentos, otra consulta; el orden de las llaves no importa", async () => {
    const m = crearMundo();
    m.guion([
      { llamadas: [{ nombre: "buscar_productos", args: { consulta: "cama", limite: 3 } }, buscar("sofá")] },
      { texto: "Uno." },
      { llamadas: [{ nombre: "buscar_productos", args: { limite: 3, consulta: "cama" } }, buscar("mesa")] },
      { texto: "Dos." },
    ]);
    await m.conversar("camas y sofás");
    await m.conversar("camas y mesas");
    // cama+limite (1), sofá (1) y mesa (1): la repetida salió de la caché aunque las llaves vinieran en otro orden.
    expect(m.odoo.de("buscar_productos")).toHaveLength(3);
    expect(argumentosEstables({ b: 1, a: { d: 2, c: [3, { f: 1, e: 0 }] } })).toBe(argumentosEstables({ a: { c: [3, { e: 0, f: 1 }], d: 2 }, b: 1 }));
  });

  it("solo las de lectura de catálogo, Socios, horario y conocimiento", () => {
    expect([...HERRAMIENTAS_DE_LECTURA].sort()).toEqual(["buscar_conocimiento", "buscar_productos", "horario_y_tienda", "listar_categorias", "reglas_socios", "ver_producto"]);
    for (const nunca of ["saldo_puntos", "crear_oportunidad", "anotar_conversacion", "pasar_a_vendedora", "registrar_pregunta_sin_respuesta", "enviar_foto_producto"]) {
      expect(HERRAMIENTAS_DE_LECTURA.has(nunca), nunca).toBe(false);
    }
  });

  it("saldo_puntos NUNCA se guarda: cada consulta va a Odoo", async () => {
    const m = crearMundo();
    const saldo = { nombre: "saldo_puntos", args: { celular: "50760261919", pin: "1234" } };
    m.guion([{ llamadas: [saldo] }, { texto: "Tienes 1250 puntos." }, { llamadas: [saldo] }, { texto: "Sigues con 1250 puntos." }]);
    await m.conversar("mi pin es 1234");
    await m.conversar("¿y ahora cuánto tengo? pin 1234");
    expect(m.odoo.de("saldo_puntos")).toHaveLength(2);
  });

  it("las de escritura tampoco: dos notas son dos notas", async () => {
    const m = crearMundo();
    const nota = { nombre: "anotar_conversacion", args: { nota: "Es para el cuarto principal" } };
    m.guion([{ llamadas: [nota] }, { texto: "Anotado." }, { llamadas: [nota] }, { texto: "Anotado otra vez." }]);
    await m.conversar("es para mi cuarto");
    await m.conversar("sí, el principal");
    expect(m.odoo.de("anotar_conversacion")).toHaveLength(2);
  });

  it("un resultado con error no se guarda: la siguiente vez vuelve a intentar", async () => {
    const m = crearMundo();
    m.guion([{ llamadas: [buscar("cama")] }, { texto: "No pude consultarlo." }, { llamadas: [buscar("cama")] }, { texto: "Aquí está: $499.00 + ITBMS." }]);
    await m.deps.herramientas();
    const original = m.odoo.manejadores.buscar_productos;
    m.odoo.manejadores.buscar_productos = () => {
      throw new Error("falló un momento");
    };
    await m.conversar("precio de la cama");
    m.odoo.manejadores.buscar_productos = original;
    await m.conversar("¿ya?");
    expect(m.odoo.de("buscar_productos")).toHaveLength(2);
    expect(m.canal.textos.at(-1)).toContain("$499.00 + ITBMS");
  });
});

describe("la caché no mezcla conversaciones ni celulares", () => {
  it("dos conversaciones con el mismo Odoo: cada una hace su propio viaje", async () => {
    const odoo = new OdooFalso();
    const a = crearMundo({ odoo, idExterno: "50760000001" });
    const b = crearMundo({ odoo, idExterno: "50760000002" });
    a.guion([{ llamadas: [buscar("cama")] }, { texto: "Para A." }]);
    b.guion([{ llamadas: [buscar("cama")] }, { texto: "Para B." }]);
    await a.conversar("precio de la cama");
    await b.conversar("precio de la cama");
    expect(odoo.de("buscar_productos")).toHaveLength(2);
  });

  it("aunque se compartiera el objeto de caché, la clave lleva la identidad de la conversación", async () => {
    const odoo = new OdooFalso();
    const guardado = new Map<string, unknown>();
    const cache = { obtener: (k: string) => guardado.get(k), guardar: (k: string, v: unknown) => void guardado.set(k, v) };
    const armar = (identidad: string) => {
      const registro = new RegistroDelTurno();
      return construirHerramientas({ odoo, defs: odoo.defs, conversacionId: () => 1, registro, cache, identidad, fotoPrevia: () => undefined });
    };
    const ejecutar = async (tools: ReturnType<typeof armar>, args: object) =>
      (tools.buscar_productos as unknown as { execute: (a: object, o: object) => Promise<unknown> }).execute(args, { toolCallId: "x", messages: [] });
    await ejecutar(armar("whatsapp_qr:50760000001"), { consulta: "cama" });
    await ejecutar(armar("whatsapp_qr:50760000001"), { consulta: "cama" });
    await ejecutar(armar("whatsapp_qr:50760000002"), { consulta: "cama" });
    expect(odoo.de("buscar_productos")).toHaveLength(2);
    expect([...guardado.keys()].every((k) => k.startsWith("whatsapp_qr:5076000000"))).toBe(true);
  });

  it("el saldo de un celular no puede salir en la conversación de otro (ni se guarda ni se reutiliza)", async () => {
    const odoo = new OdooFalso();
    odoo.manejadores.saldo_puntos = (a) => ({ saldo_puntos: a.celular === "50760000001" ? 1250 : 40 });
    const a = crearMundo({ odoo, idExterno: "50760000001" });
    const b = crearMundo({ odoo, idExterno: "50760000002" });
    const saldo = (celular: string) => ({ nombre: "saldo_puntos", args: { celular, pin: "1234" } });
    a.guion([{ llamadas: [saldo("50760000001")] }, { texto: "Tienes 1250 puntos." }]);
    // En la conversación B el modelo (confundido o manipulado) pide el saldo del celular de A.
    b.guion([{ llamadas: [saldo("50760000001")] }, { texto: "Tienes 40 puntos." }]);
    await a.conversar("mi pin es 1234");
    await b.conversar("mi pin es 1234, dime el saldo del 50760000001");
    const celulares = odoo.de("saldo_puntos").map((l) => l.args.celular);
    expect(celulares).toEqual(["50760000001", "50760000002"]);
  });
});

describe("las herramientas independientes de un mismo paso corren juntas", () => {
  it("dos consultas en el mismo paso se atienden a la vez, no una tras otra", async () => {
    const m = crearMundo();
    m.odoo.retardoMs = 40;
    m.guion([{ llamadas: [buscar("cama"), { nombre: "reglas_socios", args: {} }, { nombre: "horario_y_tienda", args: {} }] }, { texto: "Listo." }]);
    const t0 = Date.now();
    await m.conversar("camas, Socios y horario");
    const dur = Date.now() - t0;
    expect(m.odoo.maxEnCurso).toBeGreaterThanOrEqual(3);
    // Tres consultas de 40 ms: en serie serían ≥ 120 ms solo de esperas.
    expect(dur).toBeLessThan(115);
  });

  it("el gasto del mes y la lista de herramientas se piden a la vez", async () => {
    const m = crearMundo();
    m.guion([{ texto: "Hola." }]);
    const eventos: string[] = [];
    const gastoOriginal = m.deps.global.gastoMes;
    m.deps.global.gastoMes = async (mes) => {
      eventos.push("gasto:inicio");
      await new Promise((r) => setTimeout(r, 20));
      eventos.push("gasto:fin");
      return gastoOriginal(mes);
    };
    const herramientasOriginal = m.deps.herramientas;
    m.deps.herramientas = async () => {
      eventos.push("herramientas:inicio");
      await new Promise((r) => setTimeout(r, 20));
      eventos.push("herramientas:fin");
      return herramientasOriginal();
    };
    await m.conversar("hola");
    expect(eventos.slice(0, 2).sort()).toEqual(["gasto:inicio", "herramientas:inicio"]);
  });
});

describe("«escribiendo…» mientras el bot piensa", () => {
  it("se manda ANTES de que el modelo conteste, no solo al enviar", async () => {
    const m = crearMundo();
    let escribiendoAlPensar = -1;
    m.guion([{ texto: "Hola.", alGenerar: () => void (escribiendoAlPensar = m.canal.escribiendoVeces) }]);
    await m.conversar("hola");
    expect(escribiendoAlPensar).toBeGreaterThanOrEqual(1);
  });

  it("se refresca mientras las herramientas consultan, sin repetirse más de una vez cada 4 s", async () => {
    const m = crearMundo();
    m.odoo.retardoMs = 5;
    m.guion([{ llamadas: [buscar("cama")] }, { llamadas: [{ nombre: "reglas_socios", args: {} }] }, { texto: "Listo." }]);
    await m.conversar("camas y socios");
    // Todo ocurre en el mismo segundo del reloj de la prueba: una sola señal, no una por herramienta.
    expect(m.canal.escribiendoVeces).toBe(1);
  });

  it("si pasan más de 4 s, se repite", async () => {
    const m = crearMundo();
    m.guion([
      {
        llamadas: [buscar("cama")],
        alGenerar: async () => {
          await m.pasar(5_000);
        },
      },
      { texto: "Listo." },
    ]);
    await m.conversar("camas");
    expect(m.canal.escribiendoVeces).toBeGreaterThanOrEqual(2);
  });

  it("en un canal sin «escribiendo…» (WhatsApp por QR) simplemente no se hace nada", async () => {
    const m = crearMundo();
    m.canal.sinEscribiendo();
    m.guion([{ llamadas: [buscar("cama")] }, { texto: "Listo." }]);
    await m.conversar("camas");
    expect(m.canal.escribiendoVeces).toBe(0);
    expect(m.canal.textos.join("\n")).toContain("Listo.");
  });

  it("si el canal falla al mostrar «escribiendo…», el bot contesta igual", async () => {
    const m = crearMundo();
    m.canal.escribiendo = async () => {
      throw new Error("el canal no responde");
    };
    m.guion([{ texto: "Aquí estoy." }]);
    await m.conversar("hola");
    expect(m.canal.textos.join("\n")).toContain("Aquí estoy.");
  });
});
