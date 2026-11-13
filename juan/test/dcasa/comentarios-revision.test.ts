/**
 * Revisión adversarial de los comentarios de Instagram y Facebook (134eaef..35c9d0d, 2026-11-13). Las pruebas del revisor describían
 * cada fallo (pasaban mientras el fallo existía); aquí van al revés: lo que debe pasar. Decisiones del coordinador:
 *   A (bloqueante) el interruptor apagado frena también lo que ya iba por la privada o la pública · B todo comentario con letras va a la
 *   IA · C tope por persona (1 pública y 3 privadas en 24 h) · D en Instagram nunca el @usuario; en Facebook el de pila solo si es limpio
 *   · E una palabra de queja nunca recibe respuesta pública · F solo los comentarios de D'CASA · G sin «escribiendo…» y la presentación
 *   nunca sola · H el eco de la privada a otro id no se toma como una vendedora · I «Borrar mis datos» a mitad · y los menores.
 */
import { describe, expect, it } from "vitest";
import type { ComentarioEntrante, Entrante } from "../../src/canales/tipos";
import { OdooError } from "../../src/odoo/cliente";
import { clasePorReglas, nombreParaElPublico, textoPublico } from "../../src/motor/comentarios";
import { comentariosDeMeta } from "../../src/canales/metaComentarios";
import type { MotorConversacion } from "../../src/motor/conversacion";
import { crearMundo, type Mundo } from "../helpers/mundo";

const QUIEN = "17841400000000777";
const PREGUNTA = { texto: '{"result":"pregunta"}' };

function mundoComentarios(op: { canal?: "instagram" | "messenger"; comentarios?: Record<string, unknown>; config?: Record<string, unknown>; topeDiario?: number; vecinos?: Map<string, MotorConversacion> } = {}): Mundo {
  const canal = op.canal ?? "instagram";
  const m = crearMundo({ canal, idExterno: QUIEN, topeDiario: op.topeDiario, vecinos: op.vecinos, config: { canales_activos: { [canal]: true }, comentarios: { activo: true, ...op.comentarios }, ...op.config } });
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

async function comentar(m: Mundo, e: Entrante) {
  const r = await m.motor.ingest(e);
  await m.pasar(2_000);
  return r;
}

describe("A (bloqueante). el interruptor apagado frena un comentario que ya iba por la privada", () => {
  it("Odoo falla el aviso inicial, la dueña apaga «Responder comentarios»: no sale ni la privada ni la pública, y Odoo dice por qué", async () => {
    const m = mundoComentarios();
    m.guion([PREGUNTA, { texto: "¿Cuál sofá te interesa?" }]);
    m.odoo.falloDeComentario = new OdooError("Odoo dormido", 503, true);
    await comentar(m, comentario(m, "¿Cuánto cuesta el sofá?"));
    expect(m.canal.privadas).toHaveLength(0);
    m.odoo.rawConfig = { ...(m.odoo.rawConfig as object), comentarios: { activo: false } };
    m.odoo.falloDeComentario = null;
    await m.pasar(3 * 60_000);
    expect((await m.config()).comentarios.activo).toBe(false);
    expect(m.canal.privadas).toHaveLength(0);
    expect(m.canal.publicas).toHaveLength(0);
    expect(m.odoo.comentarios.at(-1)).toMatchObject({ clase: "pregunta", privada: "no", publica: "no", motivo: "se apagó «Responder comentarios»" });
    expect(m.odoo.mensajes.filter((x) => x.autor === "bot")).toHaveLength(0);
  });

  it("lo mismo si se apaga la red (Instagram) o el canal", async () => {
    for (const [apagado, motivo] of [
      [{ comentarios: { activo: true, instagram: false } }, "se apagaron los comentarios de Instagram"],
      [{ canales_activos: { instagram: false } }, "se apagó el canal Instagram"],
    ] as const) {
      const m = mundoComentarios();
      m.guion([PREGUNTA, { texto: "¿Cuál sofá te interesa?" }]);
      m.odoo.falloDeComentario = new OdooError("Odoo dormido", 503, true);
      await comentar(m, comentario(m, "¿Cuánto cuesta el sofá?"));
      m.odoo.rawConfig = { ...(m.odoo.rawConfig as object), ...apagado };
      m.odoo.falloDeComentario = null;
      await m.pasar(3 * 60_000);
      expect(m.canal.privadas, JSON.stringify(apagado)).toHaveLength(0);
      expect(m.canal.publicas, JSON.stringify(apagado)).toHaveLength(0);
      expect(m.odoo.comentarios.at(-1), JSON.stringify(apagado)).toMatchObject({ privada: "no", publica: "no", motivo });
    }
  });

  it("si se apaga mientras la IA prepara la privada (justo antes de enviar), tampoco sale", async () => {
    const m = mundoComentarios();
    // Mientras la IA escribe la privada, la dueña lo apaga (la configuración se vuelve a leer justo antes de enviar).
    let apagar = false;
    m.guion([PREGUNTA, { texto: "¿Cuál sofá te interesa?", alGenerar: () => void (apagar = true) }]);
    const original = m.deps.config;
    m.deps.config = async () => {
      const cfg = await original();
      return apagar ? { ...cfg, comentarios: { ...cfg.comentarios, activo: false } } : cfg;
    };
    await comentar(m, comentario(m, "¿Cuánto cuesta el sofá?"));
    expect(m.canal.privadas).toHaveLength(0);
    expect(m.canal.publicas).toHaveLength(0);
    expect(m.odoo.comentarios.at(-1)).toMatchObject({ privada: "no", publica: "no", motivo: "se apagó «Responder comentarios»" });
  });

  it("si se apaga después de la privada, la pública ya no sale (y el aviso lo dice)", async () => {
    const m = mundoComentarios();
    m.guion([PREGUNTA, { texto: "¿Cuál sofá te interesa?" }]);
    const original = m.deps.config;
    m.deps.config = async () => {
      const cfg = await original();
      return m.canal.privadas.length > 0 ? { ...cfg, comentarios: { ...cfg.comentarios, activo: false } } : cfg;
    };
    await comentar(m, comentario(m, "¿Cuánto cuesta el sofá?"));
    expect(m.canal.privadas).toHaveLength(1);
    expect(m.canal.publicas).toHaveLength(0);
    expect(m.odoo.comentarios.at(-1)).toMatchObject({ privada: "respondida", publica: "no", motivo: "se apagó «Responder comentarios»" });
  });
});

describe("B. las quejas cortas ya no se tiran como «otro»", () => {
  const quejas = ["Mentirosos", "Fraudes", "Tumbe", "Mala calidad", "No sirven", "Se me rompió el sofá", "Basura de muebles", "No contestan", "Llevo 3 semanas esperando", "Yo pagué y nada", "Nadie responde el wasap", "Me cancelaron"];

  it("ninguna es «otro» por las reglas baratas (son «queja» por el respaldo fijo)", () => {
    expect(quejas.filter((q) => clasePorReglas(q) === "otro")).toEqual([]);
    expect(quejas.filter((q) => clasePorReglas(q) !== "queja")).toEqual([]);
  });

  it("en el motor, cada una deja su aviso de queja en Odoo (Gerencia se entera), sin respuestas y sin gastar IA", async () => {
    const m = mundoComentarios();
    m.guion([PREGUNTA]);
    for (const q of quejas) await comentar(m, comentario(m, q));
    expect(m.modelo.doGenerateCalls).toHaveLength(0);
    expect(m.odoo.comentarios).toHaveLength(quejas.length);
    expect(m.odoo.comentarios.every((c) => c.clase === "queja" && c.privada === "no" && c.publica === "no")).toBe(true);
    expect(m.canal.privadas.length + m.canal.publicas.length).toBe(0);
  });

  it("una queja corta sin palabra conocida la ve la IA (todo lo que tiene letras va al clasificador)", async () => {
    const m = mundoComentarios();
    m.guion([{ texto: '{"result":"queja"}' }]);
    await comentar(m, comentario(m, "Qué vergüenza"));
    expect(m.modelo.doGenerateCalls).toHaveLength(1);
    expect(m.odoo.comentarios[0]).toMatchObject({ clase: "queja" });
  });
});

describe("C. tope por persona: 1 respuesta pública y 3 privadas en 24 horas (en comentarios distintos)", () => {
  it("12 comentarios «¿precio?» del mismo autor = 3 privadas, 1 pública y 3 turnos completos; lo demás se anota sin contestar", async () => {
    const m = mundoComentarios({ topeDiario: 3 });
    const pasos = [];
    for (let i = 0; i < 3; i++) pasos.push(PREGUNTA, { texto: `¿Cuál te interesa? ${i}` });
    pasos.push(PREGUNTA);
    m.guion(pasos);
    for (let i = 0; i < 12; i++) await comentar(m, comentario(m, `¿precio? ${i}`));
    expect(m.canal.privadas).toHaveLength(3);
    expect(m.canal.publicas).toHaveLength(1);
    // 12 clasificaciones (baratas) y solo 3 turnos completos.
    expect(m.modelo.doGenerateCalls).toHaveLength(12 + 3);
    const finales = m.odoo.comentarios.filter((c) => c.privada !== "pendiente");
    expect(finales).toHaveLength(12);
    expect(finales.filter((c) => c.privada === "respondida")).toHaveLength(3);
    expect(finales.filter((c) => c.privada === "no" && /tope por persona/.test(c.motivo ?? ""))).toHaveLength(9);
    expect(finales.filter((c) => c.privada === "respondida" && c.publica === "no" && /tope por persona: ya se le respondió en público/.test(c.motivo ?? ""))).toHaveLength(2);
  });

  it("pasadas 24 horas vuelve a tener lugar; los topes se cambian en Ajustes", async () => {
    const m = mundoComentarios({ comentarios: { publicas_por_persona: 2, privadas_por_persona: 1 } });
    m.guion([PREGUNTA, { texto: "¿Cuál te interesa?" }, PREGUNTA, PREGUNTA, { texto: "¿En qué medida?" }]);
    await comentar(m, comentario(m, "¿Precio?"));
    await comentar(m, comentario(m, "¿Y el envío?"));
    expect(m.canal.privadas).toHaveLength(1);
    expect(m.odoo.comentarios.at(-1)).toMatchObject({ privada: "no", motivo: "tope por persona: ya se le respondió 1 comentario por privado en 24 horas" });
    await m.pasar(24 * 3600_000);
    await comentar(m, comentario(m, "¿Y en gris?"));
    expect(m.canal.privadas).toHaveLength(2);
    expect(m.canal.publicas).toHaveLength(2);
  });

  it("si Meta rechazó la privada, no gasta el cupo de esa persona", async () => {
    const m = mundoComentarios({ comentarios: { privadas_por_persona: 1 } });
    m.guion([PREGUNTA, { texto: "¿Cuál te interesa?" }, PREGUNTA, { texto: "¿Cuál comedor?" }]);
    m.canal.falloPrivada = new Error("meta 400: (#10900) Activity already replied to (código 10900)");
    await comentar(m, comentario(m, "¿Precio?"));
    m.canal.falloPrivada = null;
    await comentar(m, comentario(m, "¿Precio del comedor?"));
    expect(m.canal.privadas).toHaveLength(1);
  });

  it("varias preguntas que esperaban a Odoo a la vez tampoco se pasan del tope (se mira otra vez justo antes de enviar)", async () => {
    const m = mundoComentarios({ comentarios: { privadas_por_persona: 1 } });
    m.guion([PREGUNTA, PREGUNTA, { texto: "¿Cuál te interesa?" }]);
    m.odoo.falloDeComentario = new OdooError("Odoo dormido", 503, true);
    await comentar(m, comentario(m, "¿Precio del sofá?"));
    await comentar(m, comentario(m, "¿Precio de la mesa?"));
    m.odoo.falloDeComentario = null;
    await m.pasar(10 * 60_000);
    expect(m.canal.privadas).toHaveLength(1);
    expect(m.odoo.comentarios.filter((c) => c.privada === "no" && /tope por persona/.test(c.motivo ?? ""))).toHaveLength(1);
  });
});

describe("D. lo público: el nombre lo escribe quien comenta, así que se cuida", () => {
  it("en Instagram nunca sale el @usuario: «¡Hola! Te escribimos por mensaje directo con los detalles.»", () => {
    for (const u of ["dcasa.estafa", "no.compren.en.dcasa", "gana.dinero.ya", "dcasa.oficial", "ana.muebles"]) {
      expect(nombreParaElPublico("instagram", `@${u}`)).toBe("");
      expect(textoPublico("¡Hola, {nombre}! Te escribimos por mensaje directo con los detalles.", nombreParaElPublico("instagram", `@${u}`))).toBe("¡Hola! Te escribimos por mensaje directo con los detalles.");
    }
  });

  it("en Facebook, un «nombre de pila» que es un insulto, una queja o la marca no sale", () => {
    for (const nombre of ["Estafadores", "Ladrones", "Dcasa", "Mentirosos", "Basura"]) {
      expect(textoPublico("¡Hola, {nombre}! Te escribimos por mensaje directo con los detalles.", nombreParaElPublico("facebook", `${nombre} Total`))).toBe("¡Hola! Te escribimos por mensaje directo con los detalles.");
    }
    expect(nombreParaElPublico("facebook", "Ana María López")).toBe("Ana");
  });

  it("enlaces, cifras, signos y patrones de reemplazo ($&) en el nombre siguen sin pasar", () => {
    for (const malo of ["https://x.co", "Ana$&", "$'", "Ana<b>", "Ana‮abc", "Ana123", "*Ana*", "{nombre}"]) {
      expect(nombreParaElPublico("facebook", malo)).toBe("");
    }
    expect(textoPublico("¡Hola, {nombre}! *Oferta*", "")).toBe("¡Hola! Oferta");
  });

  it("el Worker tampoco usa un texto de Ajustes con direcciones web sin esquema: va el de fábrica", () => {
    expect(textoPublico("Mira dcasapty.com/ofertas o bit.ly/xyz, {nombre}", "Ana")).toBe("¡Hola, Ana! Te escribimos por mensaje directo con los detalles.");
  });

  it("en el motor: la respuesta pública de Instagram va sin nombre", async () => {
    const m = mundoComentarios();
    m.guion([PREGUNTA, { texto: "¿Cuál te interesa?" }]);
    await comentar(m, comentario(m, "¿Precio?", { usuario: "dcasa.estafa" }, { nombre: "@dcasa.estafa" }));
    expect(m.canal.publicas.map((p) => p.texto)).toEqual(["¡Hola! Te escribimos por mensaje directo con los detalles."]);
  });
});

describe("E. una queja con pregunta no depende solo del modelo económico", () => {
  it("con una palabra de queja nunca sale la frase pública (aunque la IA diría «pregunta»): es queja, aviso a Gerencia y sin privada", async () => {
    const m = mundoComentarios();
    m.guion([PREGUNTA, { texto: "Te escribo por tu comentario: ¿me das tu número de pedido?" }]);
    await comentar(m, comentario(m, "¿Cuándo me devuelven mi plata? Estafadores, nunca llegó"));
    expect(m.canal.publicas).toHaveLength(0);
    expect(m.canal.privadas).toHaveLength(0);
    expect(m.modelo.doGenerateCalls).toHaveLength(0);
    expect(m.odoo.comentarios.at(-1)).toMatchObject({ clase: "queja", privada: "no", publica: "no" });
  });
});

describe("F. filtros de entrada (metaComentarios)", () => {
  const ahora = Date.parse("2026-11-12T15:00:00Z");
  const propias = new Set(["111", "17841400000000001"]);

  it("la respuesta de la propia página (from.id = entry.id) se ignora", () => {
    const r = comentariosDeMeta({ object: "page", entry: [{ id: "111", time: ahora / 1000, changes: [{ field: "feed", value: { item: "comment", verb: "add", comment_id: "1_2", post_id: "111_9", parent_id: "1_1", from: { id: "111", name: "D'CASA" }, message: "¡Hola, Ana! Te escribimos…", created_time: ahora / 1000 } }] }] }, ahora, { puerta: "pagina" });
    expect(r.entrantes).toHaveLength(0);
    expect(r.ignorados.propios).toBe(1);
  });

  it("con las cuentas de D'CASA (lo que /webhooks/meta ahora averigua): un comentario de la cuenta de Instagram con from.id ≠ entry.id no se atiende", () => {
    const r = comentariosDeMeta(
      { object: "instagram", entry: [{ id: "17841400000000001", time: ahora / 1000, changes: [{ field: "comments", value: { id: "c1", from: { id: "9990001112223", username: "dcasapanama" }, text: "¡Hola, @ana! Te escribimos por mensaje directo con los detalles.", media: { id: "m1" } } }] }] },
      ahora,
      { puerta: "pagina", cuentas: propias, propios: propias, usuarioPropio: "dcasapanama" },
    );
    expect(r.entrantes).toHaveLength(0);
    expect(r.ignorados.propios).toBe(1);
  });

  it("un comentario en OTRA página suscrita a la app no entra", () => {
    const r = comentariosDeMeta(
      { object: "page", entry: [{ id: "OTRA_PAGINA", time: ahora / 1000, changes: [{ field: "feed", value: { item: "comment", verb: "add", comment_id: "5_6", post_id: "OTRA_PAGINA_1", from: { id: "123456789", name: "Pedro" }, message: "Son unos estafadores, ¿cuándo me devuelven?", created_time: ahora / 1000 } }] }] },
      ahora,
      { puerta: "pagina", cuentas: propias, propios: propias },
    );
    expect(r.entrantes).toHaveLength(0);
    expect(r.ignorados.ajenos).toBe(1);
  });
});

describe("G. la respuesta privada de quien solo comentó", () => {
  it("no se manda «escribiendo…» (Meta lo rechaza a quien nunca escribió: ruido)", async () => {
    const m = mundoComentarios();
    m.guion([PREGUNTA, { llamadas: [{ nombre: "buscar_productos", args: { consulta: "Roma" } }] }, { texto: "¿Cuál te interesa?" }]);
    await comentar(m, comentario(m, "¿Precio?"));
    expect(m.canal.privadas).toHaveLength(1);
    expect(m.canal.escribiendoVeces).toBe(0);
  });

  it("si la presentación + la respuesta no caben, sale la respuesta sin la presentación (nunca la presentación sola)", async () => {
    const m = mundoComentarios({ config: { mensaje_bienvenida: "Hola, soy Juan de D'CASA. " + "Te cuento rápido cómo trabajamos. ".repeat(12) } });
    m.canal.cap = { ...m.canal.cap, maxTexto: 600, maxBytesTexto: 600 };
    m.guion([PREGUNTA, { texto: `El Sofá Roma lo tenemos en gris y en beige. ${"Detalle. ".repeat(20)}` }]);
    await comentar(m, comentario(m, "¿Precio?"));
    const t = m.canal.privadas[0]?.texto ?? "";
    expect(t).toContain("Sofá Roma");
    expect(t).not.toContain("cómo trabajamos");
    expect(m.canal.publicas).toHaveLength(1);
    // La presentación no salió: va con el próximo mensaje.
    m.guion([{ texto: "El Roma lo tenemos en gris." }]);
    await m.conversar("¿Hay en gris?");
    expect(m.canal.textos[0]).toContain("cómo trabajamos");
  });
});

describe("H. si el id del comentario (from.id) no es el PSID de Messenger", () => {
  it("el eco de la privada en la conversación del otro id es de Juan (no de una vendedora) y Juan contesta cuando la persona escribe", async () => {
    const vecinos = new Map<string, MotorConversacion>();
    const m = mundoComentarios({ canal: "messenger", vecinos });
    const otra = crearMundo({ canal: "messenger", idExterno: "999000111", odoo: m.odoo, vecinos, config: { canales_activos: { messenger: true } } });
    m.canal.destinatarioPrivada = "999000111";
    m.guion([PREGUNTA, { texto: "Te escribo por tu comentario: ¿cuál comedor te interesa?" }]);
    await comentar(m, comentario(m, "Info del comedor"));
    expect(m.registros.some((r) => /id distinto/.test(r.mensaje))).toBe(true);
    expect(m.gastoGlobal.leerSalud("comentario_otro_destinatario")).not.toBeNull();
    // El eco de Meta llega a la conversación del PSID.
    const eco = await otra.motor.ingest(otra.entrante(m.canal.privadas[0].texto, { id_mensaje: "priv1", propio: true, nombre: undefined }));
    expect(eco.accion).toBe("eco");
    expect(otra.motor.silencio()).toBe(false);
    expect(m.odoo.mensajes.filter((x) => x.autor === "vendedora")).toHaveLength(0);
    // La persona contesta el mensaje privado: Juan responde, sabiendo de qué venía la charla (y sin volver a presentarse).
    otra.guion([{ texto: "El comedor Milán de 6 puestos lo tenemos." }]);
    await otra.conversar("El de 6 puestos");
    expect(otra.canal.textos).toEqual(["El comedor Milán de 6 puestos lo tenemos."]);
    expect(otra.modelo.prompts()[0]).toContain("Info del comedor");
    expect(otra.modelo.prompts()[0]).toContain("¿cuál comedor te interesa?");
  });

  it("si el eco ganó la carrera y se tomó como una vendedora, el aviso deshace la pausa y queda en /salud", async () => {
    const vecinos = new Map<string, MotorConversacion>();
    const otra = crearMundo({ canal: "messenger", idExterno: "999000111", vecinos, config: { canales_activos: { messenger: true } } });
    const eco = await otra.motor.ingest(otra.entrante("Te escribo por tu comentario: ¿cuál comedor te interesa?", { id_mensaje: "priv9", propio: true, nombre: undefined }));
    expect(eco.accion).toBe("propio");
    expect(otra.motor.silencio()).toBe(true);
    await otra.motor.anotarRespuestaDeComentario({ canal: "messenger", id_externo: "999000111", red: "facebook", id_comentario: "5_6", comentario: "Info del comedor", ts_comentario: otra.ahora(), id_envio: "priv9", texto: "Te escribo por tu comentario: ¿cuál comedor te interesa?", con_presentacion: false, ts: otra.ahora() });
    expect(otra.motor.silencio()).toBe(false);
    expect(otra.gastoGlobal.leerSalud("comentario_eco_adelantado")).not.toBeNull();
  });
});

describe("I. «Borrar mis datos» (Ley 81) a mitad de un comentario", () => {
  it("si llega mientras sale la privada, el comentario se suelta: nada nuevo en Odoo ni en la memoria, y su eco no revive la conversación", async () => {
    const m = mundoComentarios();
    m.guion([PREGUNTA, { texto: "¿Cuál sofá te interesa?" }]);
    let soltar!: () => void;
    m.canal.puertaPrivada = new Promise<void>((r) => (soltar = r));
    const e = comentario(m, "¿Cuánto cuesta el sofá?");
    await m.motor.ingest(e);
    const corrida = m.pasar(2_000);
    for (let i = 0; i < 200 && !(m.motor.comentarios.leer(e.comentario!.id)?.estado ?? "").includes('"curso"'); i++) await new Promise((r) => setTimeout(r, 0));
    expect(m.motor.comentarios.leer(e.comentario!.id)?.estado).toContain('"curso"');
    const antes = { comentarios: m.odoo.comentarios.length, mensajes: m.odoo.mensajes.length };
    await m.motor.olvidar();
    soltar();
    await corrida;
    await m.pasar(5 * 60_000);
    expect(m.odoo.mensajes.length).toBe(antes.mensajes);
    expect(m.odoo.comentarios.length).toBe(antes.comentarios);
    expect(m.motor.mensajes.ultimos(10)).toHaveLength(0);
    expect(m.canal.publicas).toHaveLength(0);
    // El eco de esa privada llega después: es de Juan, no de una vendedora (no vuelve a escribir en Odoo).
    const eco = await m.motor.ingest(m.entrante("¿Cuál sofá te interesa?", { id_mensaje: "priv1", propio: true }));
    expect(eco.accion).toBe("eco");
    expect(m.odoo.mensajes.length).toBe(antes.mensajes);
  });
});

describe("menores", () => {
  it("(4) si la IA no puede preparar la privada, se reintenta 3 veces en 24 horas; mientras, Odoo dice «reintento» y la causa real", async () => {
    const m = mundoComentarios();
    m.guion([PREGUNTA, { error: new Error("overloaded") }]);
    await comentar(m, comentario(m, "¿Precio?"));
    expect(m.canal.privadas).toHaveLength(0);
    expect(m.odoo.comentarios.at(-1)).toMatchObject({ privada: "reintento", publica: "pendiente", motivo: expect.stringMatching(/^la IA no respondió/) });
    // La IA vuelve.
    m.guion([{ texto: "¿Cuál te interesa?" }]);
    await m.pasar(31 * 60_000);
    expect(m.canal.privadas).toHaveLength(1);
    expect(m.odoo.comentarios.at(-1)).toMatchObject({ privada: "respondida", publica: "respondida" });
  });

  it("(4) si ni en los reintentos, queda «no_preparada» con la causa (nunca «Meta no dejó»)", async () => {
    const m = mundoComentarios();
    m.guion([PREGUNTA, { error: new Error("overloaded") }]);
    await comentar(m, comentario(m, "¿Precio?"));
    await m.pasar(24 * 3600_000);
    expect(m.canal.privadas).toHaveLength(0);
    expect(m.odoo.comentarios.at(-1)).toMatchObject({ privada: "no_preparada", publica: "no", motivo: expect.stringMatching(/^la IA no respondió/) });
  });

  it("(4) Odoo sin herramientas (sin catálogo): la misma espera, y la causa es Odoo", async () => {
    const m = mundoComentarios();
    m.guion([PREGUNTA]);
    m.odoo.defs = [];
    await comentar(m, comentario(m, "¿Precio?"));
    await m.pasar(24 * 3600_000);
    expect(m.canal.privadas).toHaveLength(0);
    expect(m.odoo.comentarios.at(-1)).toMatchObject({ privada: "no_preparada", motivo: "Odoo no le dio a Juan el catálogo ni los precios" });
  });

  it("(5) si el objeto Global falla al apartar el lugar, la pública queda como «fallo» con el error real (no «tope»)", async () => {
    const m = mundoComentarios();
    m.guion([PREGUNTA, { texto: "¿Cuál te interesa?" }]);
    m.deps.global.reservarRespuestaPublica = async () => {
      throw new Error("Global no contesta");
    };
    await comentar(m, comentario(m, "¿Precio?"));
    expect(m.canal.privadas).toHaveLength(1);
    expect(m.canal.publicas).toHaveLength(0);
    expect(m.odoo.comentarios.at(-1)).toMatchObject({ privada: "respondida", publica: "fallo", motivo: expect.stringContaining("Global no contesta") });
  });

  it("(7) «Borrar mis datos» mientras la IA clasifica: no se escribe nada después", async () => {
    const m = mundoComentarios();
    // Odoo borra la conversación mientras el modelo económico clasifica.
    m.guion([{ ...PREGUNTA, alGenerar: async () => void (await m.motor.olvidar()) }, { texto: "¿Cuál te interesa?" }]);
    await comentar(m, comentario(m, "¿Precio?"));
    await m.pasar(5 * 60_000);
    expect(m.odoo.comentarios).toHaveLength(0);
    expect(m.canal.privadas.length + m.canal.publicas.length).toBe(0);
    expect(m.motor.resumen()).toMatchObject({ canal: null, id_externo: null, cola: 0 });
  });
});
