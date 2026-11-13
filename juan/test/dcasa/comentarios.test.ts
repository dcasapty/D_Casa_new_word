/**
 * Comentarios de Instagram y Facebook (2026-11-12). Decisiones de la dueña: «Solo los que preguntan» (las quejas no se contestan:
 * avisan a Gerencia), «Corto y lo demás por privado» y «Apagado hasta que lo pruebes». El motor de UNA conversación con un canal y un
 * Odoo de mentira: clase (reglas baratas y la IA económica con salida cerrada), respuesta privada con el motor de siempre (mismas
 * herramientas y guardia de salida), pública con el texto de Ajustes, tope por hora, nunca dos veces y el aviso en Odoo.
 */
import { describe, expect, it } from "vitest";
import type { ComentarioEntrante, Entrante } from "../../src/canales/tipos";
import { OdooError } from "../../src/odoo/cliente";
import { crearMundo, type Mundo } from "../helpers/mundo";

const QUIEN = "17841400000000777";
const PREGUNTA = { texto: '{"result":"pregunta"}' };
const RESPUESTA_SOFA = "Te escribo por tu comentario. El Sofá de 3 puestos Roma está en $799.50 + ITBMS y quedan pocas unidades. ¿Quieres que te cuente las medidas? Contéstame por aquí.";

function mundoComentarios(op: { canal?: "instagram" | "messenger"; comentarios?: Record<string, unknown>; config?: Record<string, unknown> } = {}): Mundo {
  const canal = op.canal ?? "instagram";
  const m = crearMundo({ canal, idExterno: QUIEN, config: { canales_activos: { [canal]: true }, comentarios: { activo: true, ...op.comentarios }, ...op.config } });
  m.canal.cap = { ...m.canal.cap, ventana24h: true, maxTexto: 1000, maxBytesTexto: 1000 };
  return m;
}

let n = 0;
function comentario(m: Mundo, texto: string, extra: Partial<ComentarioEntrante> = {}, entrante: Partial<Entrante> = {}): Entrante {
  const id = extra.id ?? `1790000${++n}`;
  const red = m.canal.canales[0] === "messenger" ? "facebook" : "instagram";
  return m.entrante(texto, {
    id_mensaje: `comentario:${red}:${id}`,
    nombre: red === "instagram" ? "@ana.muebles" : "Ana María López",
    celular: undefined,
    comentario: { red, puerta: "pagina", id, publicacion: "MEDIA1", ...(red === "instagram" ? { usuario: "ana.muebles" } : {}), ...extra },
    ...entrante,
  });
}

/** Llega el comentario (webhook) y la alarma lo atiende, con la cola de Odoo. */
async function comentar(m: Mundo, e: Entrante) {
  const r = await m.motor.ingest(e);
  await m.pasar(2_000);
  return r;
}

const herramientasDe = (m: Mundo, llamada: number) => (m.modelo.doGenerateCalls[llamada]?.tools ?? []).map((t) => t.name);

describe("una pregunta en un comentario: corto en público y lo demás por privado", () => {
  it("Instagram: clasifica con la IA económica, responde por privado con el catálogo y en público con el texto de Ajustes", async () => {
    const m = mundoComentarios();
    m.guion([PREGUNTA, { llamadas: [{ nombre: "buscar_productos", args: { consulta: "Roma" } }] }, { texto: RESPUESTA_SOFA }]);
    const r = await comentar(m, comentario(m, "¿Cuánto cuesta el sofá?"));
    expect(r.accion).toBe("en_espera");

    // La clase la decidió el modelo económico con salida cerrada (una de tres palabras).
    expect(m.selecciones[0]).toMatchObject({ nivel: "rapido" });
    const formato = m.modelo.doGenerateCalls[0].responseFormat as { type: string; schema?: { properties?: { result?: { enum?: string[] } } } };
    expect(formato.type).toBe("json");
    expect(formato.schema?.properties?.result?.enum).toEqual(["pregunta", "queja", "otro"]);

    // UNA respuesta privada (con la presentación, por ser la primera vez) y nada por el envío normal.
    expect(m.canal.privadas).toHaveLength(1);
    expect(m.canal.privadas[0].texto).toBe(`Hola, soy Juan de D'CASA.\n\n${RESPUESTA_SOFA}`);
    expect(m.canal.salidas).toHaveLength(0);
    // La pública, con el @usuario.
    expect(m.canal.publicas.map((p) => p.texto)).toEqual(["¡Hola, @ana.muebles! Te escribimos por mensaje directo con los detalles."]);

    // En Odoo: el aviso antes de la respuesta (así queda en el hilo) y el resultado en el mismo aviso; el comentario NO es un mensaje del cliente.
    expect(m.odoo.orden).toEqual(["comentario:pendiente", "mensaje:bot", "comentario:respondida"]);
    expect(m.odoo.comentarios[0]).toMatchObject({ privada: "pendiente", publica: "pendiente", enlace: "https://www.instagram.com/p/C0d1g0/" });
    expect(m.odoo.comentarios.at(-1)).toMatchObject({ canal: "instagram", id_externo: QUIEN, red: "instagram", clase: "pregunta", privada: "respondida", publica: "respondida", texto: "¿Cuánto cuesta el sofá?", enlace: "https://www.instagram.com/p/C0d1g0/" });
    expect(m.odoo.mensajes.filter((x) => x.autor === "cliente")).toHaveLength(0);
    expect(m.odoo.mensajes.find((x) => x.autor === "bot")?.texto).toContain("$799.50 + ITBMS");
  });

  it("el modelo ve el comentario con su marca y la publicación, y no tiene herramientas que manden archivos", async () => {
    const m = mundoComentarios();
    m.guion([PREGUNTA, { texto: "Te escribo por tu comentario: ¿cuál de los sofás de la publicación te interesa?" }]);
    await comentar(m, comentario(m, "precio porfa"));
    const prompt = m.modelo.prompts()[1];
    expect(prompt).toContain("dejó este comentario en una publicación de Instagram de D'CASA que dice «Sofá Roma de 3 puestos, tela gris. Pregunta por el tuyo.»");
    expect(prompt).toContain("MENSAJE PRIVADO");
    expect(herramientasDe(m, 1)).toContain("buscar_productos");
    for (const nombre of ["enviar_foto_producto", "cotizar", "agregar_envio"]) expect(herramientasDe(m, 1)).not.toContain(nombre);
  });

  it("Facebook: el de pila del perfil en la respuesta pública; sin nombre, «{nombre}» se quita", async () => {
    const m = mundoComentarios({ canal: "messenger" });
    m.guion([PREGUNTA, { texto: "Te escribo por tu comentario. ¿Cuál mueble te interesa?" }, PREGUNTA, { texto: "¿Cuál mueble te interesa?" }]);
    await comentar(m, comentario(m, "Info del comedor por favor"));
    await comentar(m, comentario(m, "Info del comedor por favor", {}, { nombre: "https://spam.example" }));
    expect(m.canal.publicas.map((p) => p.texto)).toEqual(["¡Hola, Ana! Te escribimos por mensaje directo con los detalles.", "¡Hola! Te escribimos por mensaje directo con los detalles."]);
    expect(m.odoo.comentarios.at(-1)).toMatchObject({ canal: "messenger", red: "facebook" });
  });

  it("la respuesta privada pasa por la guardia de salida: un precio inventado no sale", async () => {
    const m = mundoComentarios();
    m.guion([PREGUNTA, { texto: "Ese sofá te sale en $350, una ganga." }, { texto: "Ese sofá te sale en $350, una ganga." }]);
    await comentar(m, comentario(m, "¿Cuánto vale?"));
    expect(m.canal.privadas).toHaveLength(1);
    expect(m.canal.privadas[0].texto).not.toContain("350");
  });

  it("una sola vez la presentación: el segundo comentario de la misma persona ya no la lleva", async () => {
    const m = mundoComentarios();
    m.guion([PREGUNTA, { texto: "¿Cuál te interesa?" }, PREGUNTA, { texto: "¿En qué medida la buscas?" }]);
    await comentar(m, comentario(m, "¿Tienen camas?"));
    await comentar(m, comentario(m, "¿Y colchones?"));
    expect(m.canal.privadas.map((p) => p.texto)).toEqual(["Hola, soy Juan de D'CASA.\n\n¿Cuál te interesa?", "¿En qué medida la buscas?"]);
  });

  it("si la persona contesta el mensaje privado, sigue como un chat normal (con el comentario en la memoria)", async () => {
    const m = mundoComentarios();
    m.guion([PREGUNTA, { texto: "¿Cuál sofá te interesa?" }]);
    await comentar(m, comentario(m, "¿Cuánto cuesta?"));
    m.guion([{ texto: "El Roma lo tenemos en gris." }]);
    await m.conversar("El Roma, ¿hay en gris?");
    expect(m.canal.textos).toEqual(["El Roma lo tenemos en gris."]);
    expect(m.modelo.prompts()[0]).toContain("dejó este comentario en una publicación de Instagram");
  });
});

describe("a cuáles NO responde", () => {
  it("emojis solos, solo menciones, saludos y elogios cortos: «otro» sin gastar IA y sin tocar Odoo", async () => {
    const m = mundoComentarios();
    for (const texto of ["😍😍😍", "@maria.p @juanito", "@maria mira 👀", "Qué lindo", "Hola", "Bello!!", "Me encanta este estilo"]) await comentar(m, comentario(m, texto));
    expect(m.modelo.doGenerateCalls).toHaveLength(0);
    expect(m.odoo.comentarios).toHaveLength(0);
    expect(m.canal.privadas.length + m.canal.publicas.length).toBe(0);
  });

  it("lo que la IA dice «otro» tampoco se contesta ni se anota", async () => {
    const m = mundoComentarios();
    m.guion([{ texto: '{"result":"otro"}' }]);
    await comentar(m, comentario(m, "Yo tengo uno igualito en mi casa desde hace años, buenísimo"));
    expect(m.modelo.doGenerateCalls).toHaveLength(1);
    expect(m.odoo.comentarios).toHaveLength(0);
    expect(m.canal.privadas.length + m.canal.publicas.length).toBe(0);
  });

  it("una queja no se contesta: queda el aviso en Odoo (para Gerencia) con el enlace a la publicación", async () => {
    const m = mundoComentarios();
    m.guion([{ texto: '{"result":"queja"}' }]);
    await comentar(m, comentario(m, "Estafadores, pagué hace un mes y nada"));
    expect(m.canal.privadas.length + m.canal.publicas.length).toBe(0);
    expect(m.odoo.comentarios).toEqual([expect.objectContaining({ clase: "queja", privada: "no", publica: "no", texto: "Estafadores, pagué hace un mes y nada", enlace: "https://www.instagram.com/p/C0d1g0/" })]);
    expect(m.odoo.mensajes).toHaveLength(0);
  });

  it("una queja corta («estafa») no se pierde por las reglas baratas: la ve la IA", async () => {
    const m = mundoComentarios();
    m.guion([{ texto: '{"result":"queja"}' }]);
    await comentar(m, comentario(m, "Estafa"));
    expect(m.modelo.doGenerateCalls).toHaveLength(1);
    expect(m.odoo.comentarios[0]).toMatchObject({ clase: "queja" });
  });

  it("si la IA falla al clasificar, no responde y lo deja anotado (Odoo y /salud)", async () => {
    const m = mundoComentarios();
    m.guion([{ error: new Error("el proveedor no contesta") }]);
    await comentar(m, comentario(m, "¿Hacen envíos a Chitré?"));
    expect(m.canal.privadas.length + m.canal.publicas.length).toBe(0);
    expect(m.odoo.comentarios).toEqual([expect.objectContaining({ clase: "sin_clasificar", privada: "no", publica: "no" })]);
    expect(m.gastoGlobal.leerSalud("comentario_sin_clasificar")).not.toBeNull();
  });

  it("si la IA contesta algo que no es una de las tres palabras, cuenta como falla (no adivina)", async () => {
    const m = mundoComentarios();
    m.guion([{ texto: "Creo que es una pregunta sobre envíos." }]);
    await comentar(m, comentario(m, "¿Hacen envíos a Chitré?"));
    expect(m.canal.privadas).toHaveLength(0);
    expect(m.odoo.comentarios[0]).toMatchObject({ clase: "sin_clasificar" });
  });

  it("un comentario de hace más de 7 días se ignora (Meta ya no deja la respuesta privada)", async () => {
    const m = mundoComentarios();
    const r = await comentar(m, comentario(m, "¿Precio?", {}, { ts: m.ahora() - 8 * 24 * 3600_000 }));
    expect(r.accion).toBe("vencido");
    expect(m.modelo.doGenerateCalls).toHaveLength(0);
    expect(m.odoo.comentarios).toHaveLength(0);
  });
});

describe("«Apagado hasta que lo pruebes»", () => {
  it("con «Responder comentarios» apagado no hace nada: ni IA, ni respuestas, ni Odoo", async () => {
    for (const config of [{ comentarios: { activo: false } }, { comentarios: { activo: true, instagram: false } }, { comentarios: { activo: true }, canales_activos: { instagram: false } }, { comentarios: { activo: true }, bot_activo_global: false }]) {
      const m = crearMundo({ canal: "instagram", idExterno: QUIEN, config: { canales_activos: { instagram: true }, ...config } });
      m.guion([PREGUNTA, { texto: "Hola" }]);
      await comentar(m, comentario(m, "¿Cuánto cuesta?"));
      expect(m.modelo.doGenerateCalls, JSON.stringify(config)).toHaveLength(0);
      expect(m.odoo.comentarios).toHaveLength(0);
      expect(m.canal.privadas.length + m.canal.publicas.length).toBe(0);
    }
  });

  it("de fábrica (Odoo no manda nada de comentarios) está apagado", async () => {
    const m = crearMundo({ canal: "instagram", idExterno: QUIEN, config: { canales_activos: { instagram: true } } });
    m.guion([PREGUNTA]);
    await comentar(m, comentario(m, "¿Cuánto cuesta?"));
    expect(m.modelo.doGenerateCalls).toHaveLength(0);
  });
});

describe("tope por hora de respuestas públicas", () => {
  it("pasado el tope ya no responde en público (para no parecer spam), pero sí por privado; a la hora siguiente vuelve", async () => {
    const m = mundoComentarios({ comentarios: { tope_por_hora: 1 } });
    m.guion([PREGUNTA, { texto: "¿Cuál te interesa?" }, PREGUNTA, { texto: "¿En qué color?" }, PREGUNTA, { texto: "¿Para cuántas personas?" }]);
    await comentar(m, comentario(m, "¿Precio del sofá?"));
    await comentar(m, comentario(m, "¿Precio de la mesa?"));
    expect(m.canal.privadas).toHaveLength(2);
    expect(m.canal.publicas).toHaveLength(1);
    expect(m.odoo.comentarios.at(-1)).toMatchObject({ privada: "respondida", publica: "tope" });
    await m.pasar(3600_000);
    await comentar(m, comentario(m, "¿Precio del comedor?"));
    expect(m.canal.publicas).toHaveLength(2);
  });

  it("con el tope en 0 nunca responde en público", async () => {
    const m = mundoComentarios({ comentarios: { tope_por_hora: 0 } });
    m.guion([PREGUNTA, { texto: "¿Cuál te interesa?" }]);
    await comentar(m, comentario(m, "¿Precio?"));
    expect(m.canal.privadas).toHaveLength(1);
    expect(m.canal.publicas).toHaveLength(0);
  });
});

describe("nunca dos veces el mismo comentario", () => {
  it("Meta lo manda otra vez (antes o después de atenderlo): una sola respuesta privada y una pública", async () => {
    const m = mundoComentarios();
    m.guion([PREGUNTA, { texto: "¿Cuál te interesa?" }, PREGUNTA, { texto: "otra vez" }]);
    const e = comentario(m, "¿Precio?");
    expect((await m.motor.ingest(e)).accion).toBe("en_espera");
    expect((await m.motor.ingest({ ...e })).accion).toBe("duplicado");
    await m.pasar(2_000);
    expect((await comentar(m, { ...e })).accion).toBe("duplicado");
    expect(m.canal.privadas).toHaveLength(1);
    expect(m.canal.publicas).toHaveLength(1);
    expect(m.modelo.doGenerateCalls).toHaveLength(2);
  });

  it("si el objeto se cayó mientras salía la privada, no la manda otra vez ni responde en público: lo dice en Odoo", async () => {
    const m = mundoComentarios();
    const e = comentario(m, "¿Precio?");
    await m.motor.ingest(e);
    // Así queda guardado si el Durable Object se reinicia justo después de marcar «saliendo».
    m.motor.comentarios.ponerEstado(e.comentario!.id, JSON.stringify({ fase: "privada", clase: "pregunta", privada: "curso", avisoInicial: true, texto: "¿Cuál te interesa?" }), m.ahora());
    await m.pasar(2_000);
    expect(m.canal.privadas.length + m.canal.publicas.length).toBe(0);
    expect(m.modelo.doGenerateCalls).toHaveLength(0);
    expect(m.odoo.comentarios.at(-1)).toMatchObject({ privada: "incierta", publica: "no" });
  });

  it("si Odoo no contesta al empezar, espera y lo intenta de nuevo, sin responder dos veces", async () => {
    const m = mundoComentarios();
    m.guion([PREGUNTA, { texto: "¿Cuál te interesa?" }]);
    m.odoo.falloDeComentario = new OdooError("Odoo no contesta", 503, true);
    await comentar(m, comentario(m, "¿Precio?"));
    expect(m.canal.privadas).toHaveLength(0);
    m.odoo.falloDeComentario = null;
    await m.pasar(2 * 60_000);
    expect(m.canal.privadas).toHaveLength(1);
    expect(m.canal.publicas).toHaveLength(1);
    expect(m.modelo.doGenerateCalls.filter((c) => c.responseFormat?.type === "json")).toHaveLength(1);
    // La publicación se leyó una vez y el modelo la ve igual en el segundo intento.
    expect(m.canal.publicacionesLeidas).toBe(1);
    expect(m.modelo.prompts().at(-1)).toContain("Sofá Roma de 3 puestos");
  });
});

describe("cuando no se puede responder", () => {
  it("si Meta rechaza la privada, lo dice en Odoo con su motivo y no responde en público (no diría la verdad)", async () => {
    const m = mundoComentarios();
    m.guion([PREGUNTA, { texto: "¿Cuál te interesa?" }]);
    m.canal.falloPrivada = new Error("meta 400: (#10900) Activity already replied to (código 10900)");
    await comentar(m, comentario(m, "¿Precio?"));
    expect(m.canal.publicas).toHaveLength(0);
    expect(m.odoo.comentarios.at(-1)).toMatchObject({ privada: "fallo", publica: "no", motivo: "(#10900) Activity already replied to (código 10900)" });
    expect(m.odoo.mensajes.filter((x) => x.autor === "bot")).toHaveLength(0);
  });

  it("si Meta rechaza la pública, la privada igual quedó y Odoo lo sabe", async () => {
    const m = mundoComentarios();
    m.guion([PREGUNTA, { texto: "¿Cuál te interesa?" }]);
    m.canal.falloPublica = new Error("meta 400: (#200) Permissions error (código 200)");
    await comentar(m, comentario(m, "¿Precio?"));
    expect(m.canal.privadas).toHaveLength(1);
    expect(m.odoo.comentarios.at(-1)).toMatchObject({ privada: "respondida", publica: "fallo", motivo: "(#200) Permissions error (código 200)" });
  });

  it("si una vendedora atiende a esa persona, Juan no se mete: ni privada ni pública, y el aviso lo dice", async () => {
    const m = mundoComentarios();
    m.guion([PREGUNTA, { texto: "¿Cuál te interesa?" }]);
    m.odoo.estadoActual = { ...m.odoo.estadoActual, estado: "humano", bot_activo: false };
    await comentar(m, comentario(m, "¿Precio?"));
    expect(m.canal.privadas.length + m.canal.publicas.length).toBe(0);
    expect(m.odoo.comentarios.at(-1)).toMatchObject({ privada: "vendedora", publica: "no" });
  });

  it("un seguimiento a quien solo comentó se descarta: la ventana de 24 h nunca se abrió", async () => {
    const m = mundoComentarios();
    m.guion([PREGUNTA, { texto: "¿Cuál te interesa?" }]);
    await comentar(m, comentario(m, "¿Precio?"));
    await m.pasar(5 * 3600_000);
    const r = await m.motor.seguimiento({ conversacion_id: 12, numero: 1, contexto: {} });
    expect(r).toMatchObject({ resultado: "descartado", motivo: expect.stringMatching(/24 h/) });
  });
});

describe("el mensaje privado es UNO solo", () => {
  it("si la respuesta no cabe en un mensaje de Instagram, se recorta entera por burbujas (nunca dos mensajes)", async () => {
    const m = mundoComentarios();
    const larga = Array.from({ length: 6 }, (_, i) => `Párrafo ${i + 1}: ${"detalle de la tienda ".repeat(12).trim()}.`).join("\n\n");
    m.guion([PREGUNTA, { texto: larga }]);
    await comentar(m, comentario(m, "¿Qué tienen?"));
    expect(m.canal.privadas).toHaveLength(1);
    expect(new TextEncoder().encode(m.canal.privadas[0].texto).length).toBeLessThanOrEqual(1000);
    expect(m.canal.privadas[0].texto.startsWith("Hola, soy Juan de D'CASA.")).toBe(true);
  });
});
