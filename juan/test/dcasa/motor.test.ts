// El motor de una conversación de punta a punta: ráfaga de 15 s, bucle de IA con las herramientas de Odoo,
// presentación, burbujas, registro en Odoo, re-chequeo antes de enviar. Con un modelo guionado.
import { describe, expect, it } from "vitest";
import { crearMundo } from "../helpers/mundo";

describe("la ráfaga de 15 s", () => {
  it("junta lo que el cliente escribe y contesta UNA sola vez", async () => {
    const m = crearMundo();
    const guion = m.guion([{ texto: "Claro, te ayudo con eso." }]);
    await m.escribir("hola");
    await m.pasar(5_000);
    await m.escribir("quiero una cama");
    await m.pasar(5_000);
    await m.escribir("queen");
    // Aún no vencen los 15 s del último mensaje.
    await m.pasar(10_000);
    expect(guion.doGenerateCalls.length).toBe(0);
    expect(m.canal.salidas.length).toBe(0);
    await m.pasar(6_000);
    expect(guion.doGenerateCalls.length).toBe(1);
    const prompt = guion.prompts()[0];
    expect(prompt).toContain("hola");
    expect(prompt).toContain("quiero una cama");
    expect(prompt).toContain("queen");
  });

  it("no contesta antes de los 15 s", async () => {
    const m = crearMundo();
    m.guion([{ texto: "Hola, dime." }]);
    await m.escribir("hola");
    await m.pasar(14_000);
    expect(m.canal.salidas.length).toBe(0);
    await m.pasar(2_000);
    expect(m.canal.salidas.length).toBe(1);
  });
});

describe("la presentación y el registro en Odoo", () => {
  it("el primer mensaje trae la presentación como asistente automático y la vía a una persona", async () => {
    const m = crearMundo();
    m.guion([{ texto: "Claro, te cuento." }]);
    await m.conversar("hola");
    const textos = m.canal.textos.join("\n");
    expect(textos).toMatch(/asistente autom[aá]tico/i);
    expect(textos).toContain("asistente automático de D'CASA.");
    expect(textos).toContain("*persona*");
    expect(textos).toContain("Claro, te cuento.");
  });

  it("solo se presenta una vez", async () => {
    const m = crearMundo();
    m.guion([{ texto: "Uno." }, { texto: "Dos." }]);
    await m.conversar("hola");
    await m.conversar("gracias");
    const presentaciones = m.canal.textos.filter((t) => /asistente autom[aá]tico/i.test(t));
    expect(presentaciones.length).toBe(1);
  });

  it("usa la presentación que la dueña aprobó en Odoo si dice que es automática", async () => {
    const m = crearMundo({ config: { mensaje_bienvenida: "Hola, soy el asistente automático de D'CASA. ¿Qué buscas?", texto_privacidad_corto: "Guardamos esta conversación para atenderte." } });
    m.guion([{ texto: "Dime." }]);
    await m.conversar("hola");
    const primera = m.canal.textos[0];
    expect(primera).toContain("¿Qué buscas?");
    expect(primera).toContain("Guardamos esta conversación para atenderte.");
  });

  it("si el texto de bienvenida de Odoo no dice que es automático, usa el de siempre", async () => {
    const m = crearMundo({ config: { mensaje_bienvenida: "Bienvenido a la tienda." } });
    m.guion([{ texto: "Dime." }]);
    await m.conversar("hola");
    expect(m.canal.textos.join("\n")).toMatch(/asistente autom[aá]tico/i);
    expect(m.canal.textos.join("\n")).not.toContain("Bienvenido a la tienda.");
  });

  it("registra en Odoo el mensaje del cliente y la respuesta del bot, con el celular como llave", async () => {
    const m = crearMundo();
    m.guion([{ texto: "Claro." }]);
    await m.conversar("hola");
    const entrante = m.odoo.mensajes.find((x) => x.autor === "cliente")!;
    expect(entrante).toMatchObject({ canal: "whatsapp_qr", id_externo: "50760261919", celular: "50760261919", direccion: "entrante", texto: "hola", nombre: "Karen" });
    const saliente = m.odoo.mensajes.find((x) => x.autor === "bot")!;
    expect(saliente.direccion).toBe("saliente");
    expect(saliente.texto).toContain("Claro.");
  });

  it("registrar dos veces el mismo mensaje del canal no lo duplica", async () => {
    const m = crearMundo();
    m.guion([{ texto: "Hola." }]);
    const e = m.entrante("hola");
    await m.motor.ingest(e);
    const r = await m.motor.ingest(e);
    expect(r.accion).toBe("duplicado");
    await m.pasar(16_000);
    expect(m.odoo.mensajes.filter((x) => x.autor === "cliente").length).toBe(1);
  });
});

describe("las herramientas de Odoo", () => {
  it("consulta el catálogo con la herramienta y responde con el precio «+ ITBMS»", async () => {
    const m = crearMundo();
    const guion = m.guion([
      { llamadas: [{ nombre: "buscar_productos", args: { consulta: "cama queen" } }] },
      { texto: "Tenemos la Cama Queen Milán a $499.00 + ITBMS. ¿Te mando la foto?" },
    ]);
    await m.conversar("¿cuánto cuesta una cama queen?");
    expect(m.odoo.de("buscar_productos").length).toBe(1);
    expect(m.odoo.de("buscar_productos")[0].conversacion_id).toBe(12);
    expect(m.canal.textos.join("\n")).toContain("$499.00 + ITBMS");
    // El modelo recibió la herramienta con el precio ya armado.
    expect(guion.prompts()[1]).toContain("$499.00 + ITBMS");
  });

  it("un precio escrito sin «+ ITBMS» se corrige antes de enviarlo", async () => {
    const m = crearMundo();
    m.guion([
      { llamadas: [{ nombre: "buscar_productos", args: { consulta: "cama" } }] },
      { texto: "La Cama Queen Milán cuesta $499." },
    ]);
    await m.conversar("precio de la cama");
    expect(m.canal.textos.join("\n")).toContain("$499 + ITBMS");
  });

  it("hasta 6 pasos de herramientas y luego responde", async () => {
    const m = crearMundo();
    const guion = m.guion([
      ...Array.from({ length: 6 }, () => ({ llamadas: [{ nombre: "listar_categorias", args: {} }] })),
      { texto: "Tenemos camas, sofás y comedores." },
    ]);
    await m.conversar("¿qué tienen?");
    // 6 pasos permitidos: el límite corta el bucle; como el último paso fue una herramienta, se le pide responder sin más.
    expect(guion.doGenerateCalls.length).toBeLessThanOrEqual(8);
    expect(m.odoo.de("listar_categorias").length).toBeLessThanOrEqual(6);
    expect(m.canal.textos.length).toBeGreaterThan(0);
  });

  it("si Odoo no contesta, el modelo lo sabe y no se inventa el dato", async () => {
    const m = crearMundo();
    const guion = m.guion([
      { llamadas: [{ nombre: "buscar_productos", args: { consulta: "cama" } }] },
      { texto: "Ahorita no pude consultarlo. Una vendedora te lo confirma." },
    ]);
    await m.deps.herramientas(); // la lista de herramientas ya estaba en caché cuando Odoo se cayó
    await m.escribir("cama?");
    m.odoo.caido = true; // se cae después de registrar el mensaje
    await m.pasar(16_000);
    expect(guion.prompts()[1]).toContain("No pude consultar el sistema ahora");
    expect(m.canal.textos.join("\n")).toContain("Una vendedora te lo confirma.");
  });

  it("registra la oportunidad y la nota cuando el modelo lo decide", async () => {
    const m = crearMundo();
    m.guion([
      { llamadas: [{ nombre: "crear_oportunidad", args: { resumen: "Cama Queen Milán CAMA-Q-001", interes: "cama queen" } }, { nombre: "anotar_conversacion", args: { nota: "Es para el cuarto principal" } }] },
      { texto: "Listo, ya lo tengo anotado. ¿Algo más?" },
    ]);
    await m.conversar("quiero la cama queen para mi cuarto");
    expect(m.odoo.de("crear_oportunidad")[0].args.resumen).toContain("CAMA-Q-001");
    expect(m.odoo.de("anotar_conversacion").some((l) => String(l.args.nota).includes("cuarto principal"))).toBe(true);
  });
});

describe("las burbujas", () => {
  it("parte la respuesta en burbujas cortas", async () => {
    const m = crearMundo();
    const parrafo = (t: string) => `${t} ${"Esto es una frase de relleno para que el párrafo sea largo. ".repeat(3)}`.trim();
    m.guion([{ texto: [parrafo("Primera idea."), parrafo("Segunda idea."), parrafo("Tercera idea.")].join("\n\n") }]);
    await m.conversar("hola");
    // presentación + respuesta partida
    expect(m.canal.textos.length).toBeGreaterThanOrEqual(3);
    for (const b of m.canal.textos) expect(b.split("\n").length).toBeLessThanOrEqual(6);
    expect(m.canal.ultimaSalida!.esperaMs).toBe(1000);
  });
});

describe("el re-chequeo con Odoo justo antes de enviar", () => {
  it("si una vendedora tomó la conversación mientras el bot pensaba, no envía", async () => {
    const m = crearMundo();
    m.guion([{ texto: "Respuesta que no debe salir." }]);
    await m.escribir("hola");
    await m.pasar(1_000); // se registra el mensaje: Odoo dice que el bot está activo
    m.odoo.estadoActual = { ...m.odoo.estadoActual, estado: "humano", bot_activo: false };
    await m.pasar(16_000);
    expect(m.canal.salidas.length).toBe(0);
    expect(m.odoo.pedidosDeEstado).toBeGreaterThan(0);
  });

  it("consulta GET /estado antes de CADA respuesta", async () => {
    const m = crearMundo();
    m.guion([{ texto: "Uno." }, { texto: "Dos." }]);
    await m.conversar("hola");
    const antes = m.odoo.pedidosDeEstado;
    await m.conversar("otra cosa");
    expect(m.odoo.pedidosDeEstado).toBe(antes + 1);
  });

  it("si Odoo está caído al re-chequear, contesta con lo último que sabía", async () => {
    const m = crearMundo();
    m.guion([{ texto: "Aquí estoy." }]);
    await m.deps.herramientas();
    await m.escribir("hola");
    await m.pasar(1_000);
    m.odoo.caido = true;
    await m.pasar(16_000);
    expect(m.canal.textos.join("\n")).toContain("Aquí estoy.");
  });

  it("el bot apagado en Odoo (bot_activo_global) guarda el mensaje y no contesta", async () => {
    const m = crearMundo({ config: { bot_activo_global: false } });
    m.guion([{ texto: "No debería salir." }]);
    await m.conversar("hola");
    expect(m.canal.salidas.length).toBe(0);
    expect(m.odoo.mensajes.filter((x) => x.autor === "cliente").length).toBe(1);
  });
});
