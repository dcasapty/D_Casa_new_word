/**
 * Regla 7 del contrato: una persona de D'CASA tomó la conversación → el bot calla y no la retoma solo.
 *
 * Reescritura de test/takeover.test.ts del CRM de Baby Caleb. Las tres puertas por las que una persona entra:
 *   · escribe desde el teléfono (WhatsApp por QR, `propio:true`)         → registrar como vendedora y pausar al bot
 *   · escribe desde Odoo (`POST /odoo/enviar`)                            → sale por el canal, sin IA, y pausa al bot
 *   · toma o devuelve la conversación en Odoo (`POST /odoo/estado`)
 * y la cuarta, que no es una puerta sino un candado: Odoo dice «humano» al re-chequear justo antes de enviar.
 */
import { describe, expect, it } from "vitest";
import { crearMundo } from "../helpers/mundo";

const DOS_HORAS = 120 * 60_000;

describe("la vendedora escribe desde su teléfono (propio:true)", () => {
  it("se registra en Odoo como «vendedora» y el bot se calla", async () => {
    const m = crearMundo();
    const g = m.guion([{ texto: "Hola, ¿qué buscas?" }, { texto: "no debería salir" }]);
    await m.conversar("hola");
    const antes = m.canal.textos.length;

    const r = await m.escribir("Hola Karen, soy Marisol de D'CASA. Ya te ayudo con la cama.", { propio: true });
    expect(r.accion).toBe("propio");
    await m.pasar(1_000);
    const registro = m.odoo.mensajes.find((x) => x.autor === "vendedora")!;
    expect(registro).toMatchObject({ direccion: "saliente", autor: "vendedora", id_externo: "50760261919" });
    expect(registro.texto).toContain("soy Marisol");
    await m.pasar(1_000);

    // El cliente sigue la conversación con ella: el bot no se mete.
    await m.conversar("gracias Marisol, ¿cuánto cuesta?");
    expect(m.canal.textos.length).toBe(antes);
    expect(g.doGenerateCalls.length).toBe(1);
    // …pero el mensaje del cliente SÍ quedó en Odoo (la bandeja no pierde la mitad del chat).
    expect(m.odoo.mensajes.some((x) => x.autor === "cliente" && x.texto.includes("¿cuánto cuesta?"))).toBe(true);
  });

  it("cancela la respuesta que el bot tenía en la ráfaga", async () => {
    const m = crearMundo();
    const g = m.guion([{ texto: "no debería salir" }]);
    await m.escribir("hola, quiero una cama");
    await m.pasar(5_000);
    await m.escribir("Hola, te atiendo yo.", { propio: true });
    await m.pasar(20_000);
    expect(g.doGenerateCalls.length).toBe(0);
    expect(m.canal.salidas.length).toBe(0);
  });

  it("si la vendedora escribe MIENTRAS el bot pensaba, la respuesta del bot no sale", async () => {
    const m = crearMundo();
    m.guion([
      {
        texto: "Respuesta del bot que no debe salir.",
        alGenerar: async () => {
          await m.escribir("Yo me encargo, Karen.", { propio: true });
        },
      },
    ]);
    await m.conversar("hola");
    expect(m.canal.textos.join("\n")).not.toContain("Respuesta del bot");
  });

  it("el eco del propio bot NO cuenta como una persona escribiendo", async () => {
    const m = crearMundo();
    m.guion([{ texto: "Tenemos camas queen y king, ¿cuál buscas?" }, { texto: "Claro." }]);
    await m.conversar("hola");
    // El teléfono reenvía como «propio» lo que acaba de mandar el bot.
    const eco = await m.escribir("Tenemos camas queen y king, ¿cuál buscas?", { propio: true });
    expect(eco.accion).toBe("eco");
    expect(m.motor.silencio()).toBe(false);
    await m.conversar("la queen");
    expect(m.canal.textos.at(-1)).toBe("Claro.");
  });

  it("también reconoce el eco por el id que el canal dio al enviar", async () => {
    const m = crearMundo();
    m.guion([{ texto: "Hola." }]);
    await m.conversar("hola");
    const r = await m.escribir(undefined, { propio: true, id_mensaje: "m1", adjuntos: [{ tipo: "imagen", url: "https://x/y.jpg" }] });
    expect(r.accion).toBe("eco");
  });

  it("cada mensaje suyo renueva la pausa; al vencer, el bot vuelve cuando el cliente escribe", async () => {
    const m = crearMundo();
    m.guion([{ texto: "Hola." }, { texto: "Aquí sigo para lo que necesites." }]);
    await m.conversar("hola");
    await m.escribir("Hola, te atiendo yo.", { propio: true });
    await m.pasar(DOS_HORAS - 60_000);
    await m.escribir("Te mando las fotos ahora.", { propio: true });
    await m.pasar(DOS_HORAS - 60_000);
    // Pasaron casi 4 horas desde el primero, pero 2 desde el último: sigue pausado.
    await m.conversar("¿y las fotos?");
    expect(m.canal.textos.at(-1)).not.toContain("Aquí sigo");
    await m.pasar(2 * 60_000);
    await m.conversar("¿hola?");
    expect(m.canal.textos.at(-1)).toContain("Aquí sigo");
  });

  it("la pausa por defecto sale de la configuración de Odoo", async () => {
    const m = crearMundo({ config: { pausa_por_defecto_minutos: 10 } });
    m.guion([{ texto: "Hola." }, { texto: "Ya estoy de vuelta." }]);
    await m.conversar("hola");
    await m.escribir("Te atiendo yo.", { propio: true });
    await m.pasar(11 * 60_000);
    await m.conversar("sigo aquí");
    expect(m.canal.textos.at(-1)).toBe("Ya estoy de vuelta.");
  });
});

describe("Odoo toma o devuelve la conversación (POST /odoo/estado)", () => {
  it("«humano» cancela la respuesta en curso", async () => {
    const m = crearMundo();
    const g = m.guion([{ texto: "no debería salir" }]);
    await m.escribir("hola");
    await m.pasar(5_000);
    await m.motor.fijarEstado({ estado: "humano" });
    await m.pasar(20_000);
    expect(g.doGenerateCalls.length).toBe(0);
    expect(m.canal.salidas.length).toBe(0);
  });

  it("«humano» con fecha: calla hasta esa fecha", async () => {
    const m = crearMundo();
    m.guion([{ texto: "De vuelta." }]);
    await m.motor.fijarEstado({ estado: "humano", pausada_hasta: new Date(m.ahora() + 30 * 60_000).toISOString() });
    await m.conversar("hola");
    expect(m.canal.salidas.length).toBe(0);
    await m.pasar(31 * 60_000);
    await m.conversar("¿hay alguien?");
    expect(m.canal.textos.join("\n")).toContain("De vuelta.");
  });

  it("«bot» la devuelve: el bot vuelve a contestar", async () => {
    const m = crearMundo();
    m.guion([{ texto: "Aquí estoy." }]);
    await m.motor.fijarEstado({ estado: "humano" });
    await m.conversar("hola");
    expect(m.canal.salidas.length).toBe(0);
    await m.motor.fijarEstado({ estado: "bot" });
    await m.conversar("¿me ayudas?");
    expect(m.canal.textos.join("\n")).toContain("Aquí estoy.");
  });

  it("devolver la conversación también levanta un descanso por spam", async () => {
    const m = crearMundo();
    m.guion([{ texto: "Aquí estoy." }]);
    for (let i = 0; i < 3; i++) await m.escribir("comprar");
    expect((await m.escribir("comprar")).accion).toBe("descanso");
    await m.motor.fijarEstado({ estado: "bot" });
    await m.conversar("hola otra vez");
    expect(m.canal.textos.join("\n")).toContain("Aquí estoy.");
  });
});

describe("Odoo dice «humano» al re-chequear (candado final)", () => {
  it("«humano» sin fecha: el bot calla hasta que se la devuelvan", async () => {
    const m = crearMundo();
    m.odoo.estadoActual = { ...m.odoo.estadoActual, estado: "humano", bot_activo: false, pausada_hasta: null };
    m.guion([{ texto: "no debería salir" }]);
    await m.conversar("hola");
    await m.pasar(24 * 3600_000);
    await m.conversar("¿hola?");
    expect(m.canal.salidas.length).toBe(0);
    m.odoo.estadoActual = { ...m.odoo.estadoActual, estado: "bot", bot_activo: true };
    await m.motor.fijarEstado({ estado: "bot" });
    m.guion([{ texto: "Aquí estoy." }]);
    await m.conversar("¿ya?");
    expect(m.canal.textos.join("\n")).toContain("Aquí estoy.");
  });

  it("una pausa con fecha futura que manda Odoo se respeta; vencida, no", async () => {
    const m = crearMundo();
    m.guion([{ texto: "Ya volví." }]);
    m.odoo.estadoActual = { ...m.odoo.estadoActual, bot_activo: false, pausada_hasta: "2026-10-09 16:00:00" }; // UTC: dentro de 1 h
    await m.conversar("hola");
    expect(m.canal.salidas.length).toBe(0);
    m.odoo.estadoActual = { ...m.odoo.estadoActual, bot_activo: true, estado: "bot" };
    await m.pasar(2 * 3600_000);
    await m.conversar("¿ya estás?");
    expect(m.canal.textos.join("\n")).toContain("Ya volví.");
  });
});

describe("la vendedora escribe desde Odoo (POST /odoo/enviar)", () => {
  it("sale por el canal tal cual, sin IA y sin ráfaga", async () => {
    const m = crearMundo();
    const g = m.guion([{ texto: "no debería pensar" }]);
    const r = await m.motor.enviarVendedora({ texto: "Hola Karen, te escribe Marisol de D'CASA." });
    expect(r.ok).toBe(true);
    expect(r.id_mensaje).toBeTruthy();
    expect(m.canal.ultimaSalida!.burbujas).toEqual(["Hola Karen, te escribe Marisol de D'CASA."]);
    expect(g.doGenerateCalls.length).toBe(0);
  });

  it("manda imágenes y documentos; el audio y el video salen como enlace", async () => {
    const m = crearMundo();
    await m.motor.enviarVendedora({
      texto: "Te paso la cotización y las fotos.",
      adjuntos: [
        { tipo: "documento", url: "https://odoo.example/cot.pdf", nombre: "cotizacion.pdf", mime: "application/pdf" },
        { tipo: "imagen", url: "https://odoo.example/cama.jpg", nombre: "cama.jpg" },
        { tipo: "audio", url: "https://odoo.example/nota.ogg", nombre: "nota.ogg" },
      ],
    });
    const s = m.canal.ultimaSalida!;
    expect(s.medios.map((x) => x.tipo)).toEqual(["documento", "imagen"]);
    expect(s.medios[0]).toMatchObject({ url: "https://odoo.example/cot.pdf", nombre: "cotizacion.pdf", mime: "application/pdf" });
    expect(s.burbujas.join("\n")).toContain("nota.ogg: https://odoo.example/nota.ogg");
  });

  it("deja al bot callado (la persona acaba de tomar la conversación) y corta lo que traía a medias", async () => {
    const m = crearMundo();
    const g = m.guion([{ texto: "no debería salir" }]);
    await m.escribir("hola");
    await m.pasar(5_000);
    await m.motor.enviarVendedora({ texto: "Hola, soy Marisol." });
    await m.pasar(20_000);
    expect(g.doGenerateCalls.length).toBe(0);
    expect(m.canal.textos).toEqual(["Hola, soy Marisol."]);
  });

  it("queda en el historial del bot como «[Vendedora]», para que no la contradiga cuando vuelva", async () => {
    const m = crearMundo();
    const g = m.guion([{ texto: "Perfecto." }]);
    await m.conversar("hola");
    await m.motor.enviarVendedora({ texto: "La cama queen la tenemos en el showroom." });
    await m.motor.fijarEstado({ estado: "bot" });
    await m.conversar("gracias");
    expect(g.prompts().at(-1)).toContain("[Vendedora] La cama queen la tenemos en el showroom.");
  });

  it("no manda un texto largo cortado a medias: respeta el máximo del canal", async () => {
    const m = crearMundo();
    m.canal.cap = { ...m.canal.cap, maxTexto: 100 };
    await m.motor.enviarVendedora({ texto: "Palabra ".repeat(40).trim() });
    expect(m.canal.ultimaSalida!.burbujas.length).toBeGreaterThan(1);
    for (const b of m.canal.ultimaSalida!.burbujas) expect(b.length).toBeLessThanOrEqual(100);
  });

  it("si no hay nada que enviar, falla con un mensaje claro", async () => {
    const m = crearMundo();
    await expect(m.motor.enviarVendedora({})).rejects.toThrow(/nada que enviar/);
  });

  it("si el canal falla, el error le llega a Odoo (no se traga)", async () => {
    const m = crearMundo();
    m.canal.fallar = 5;
    await expect(m.motor.enviarVendedora({ texto: "Hola" })).rejects.toThrow(/el canal falló/);
  });
});

describe("cuando es el propio bot quien pasa la conversación", () => {
  it("el mensaje de despedida de ESE turno sí sale, aunque Odoo ya esté en «humano»", async () => {
    const m = crearMundo();
    m.guion([
      { llamadas: [{ nombre: "pasar_a_vendedora", args: { motivo: "Reclamo por un sofá dañado", urgencia: "alta" } }] },
      { texto: "Listo, ya avisé a una vendedora. Te escribe por aquí en unos minutos." },
    ]);
    await m.conversar("el sofá llegó dañado y estoy muy molesta");
    expect(m.odoo.estadoActual.estado).toBe("humano");
    expect(m.canal.textos.join("\n")).toContain("ya avisé a una vendedora");
    // …y a partir de ahí, calla.
    const n = m.canal.textos.length;
    await m.conversar("¿hola? ¿hay alguien?");
    expect(m.canal.textos.length).toBe(n);
  });
});
