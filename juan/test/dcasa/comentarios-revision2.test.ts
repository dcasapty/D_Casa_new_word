/**
 * Segunda vuelta de la revisión adversarial de los comentarios (35c9d0d..168a291, 2026-11-13). Las pruebas del revisor describían cada
 * hallazgo (pasaban mientras existía); aquí van al revés. Decisiones del coordinador:
 *   1a `GET /me` con plazo · 1b sin saber la página: los mensajes se guardan y 500 (Meta reintenta), y META_PAGE_ID de respaldo ·
 *   2a un Telegram de queja por persona cada 24 h (Odoo) · 3a una palabra de queja ya no decide la clase: la IA decide, pero nunca hay
 *   pública y si la IA falla es queja · menores: pasado el tope por persona ni IA ni un aviso por comentario · tope global de privadas
 *   por hora · en lo público nunca el nombre (tampoco en Facebook) · /salud dice «no sé cuál es tu Instagram» · el eco que gana la
 *   carrera no llega a Odoo como una vendedora.
 */
import { describe, expect, it } from "vitest";
import type { Env } from "../../src/env";
import { normalizarConfig } from "../../src/config";
import { crearMeta } from "../../src/canales/meta";
import type { MetaCuerpo } from "../../src/canales/metaComun";
import type { ComentarioEntrante, Entrante } from "../../src/canales/tipos";
import { clasePorReglas, pareceQueja, textoPublico } from "../../src/motor/comentarios";
import { AlmacenGlobal } from "../../src/motor/global";
import type { MotorConversacion } from "../../src/motor/conversacion";
import { informeDeSalud } from "../../src/salud";
import { hmacHex } from "../../src/seguridad";
import { llaveroEnMemoria } from "../helpers/llaveroEnMemoria";
import { crearMundo, type Mundo } from "../helpers/mundo";
import { crearSqlNode } from "../helpers/sqlNode";

const QUIEN = "17841400000000777";
const PREGUNTA = { texto: '{"result":"pregunta"}' };
const FABRICA = "¡Hola! Te escribimos por mensaje directo con los detalles.";

function mundoComentarios(op: { canal?: "instagram" | "messenger"; comentarios?: Record<string, unknown>; config?: Record<string, unknown>; vecinos?: Map<string, MotorConversacion>; id?: string; global?: AlmacenGlobal } = {}): Mundo {
  const canal = op.canal ?? "instagram";
  const m = crearMundo({ canal, idExterno: op.id ?? QUIEN, vecinos: op.vecinos, global: op.global, config: { canales_activos: { [canal]: true }, comentarios: { activo: true, ...op.comentarios }, ...op.config } });
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
    comentario: { red, puerta: "pagina", id, publicacion: `MEDIA${n}`, ...(red === "instagram" ? { usuario: "ana.muebles" } : {}), ...extra },
    ...entrante,
  });
}
async function comentar(m: Mundo, e: Entrante) {
  const r = await m.motor.ingest(e);
  await m.pasar(2_000);
  return r;
}

// ── /webhooks/meta ──
const SECRETO_FB = "secreto-de-la-app-de-facebook-0123456789";
const PAGINA = "100200300400500";
const CUENTA_IG = "17841400000000001";
const envPagina = { META_APP_SECRET: SECRETO_FB, META_VERIFY_TOKEN: "verificacion-de-prueba-0123456789", META_PAGE_TOKEN: "token-de-la-pagina-0123456789" } as unknown as Env;
const ahoraS = () => Math.floor(Date.now() / 1000);
const fbComentario = (extra: Record<string, unknown> = {}): MetaCuerpo => ({
  object: "page",
  entry: [{ id: PAGINA, time: ahoraS(), changes: [{ field: "feed", value: { from: { id: "2838000000000001", name: "Ana López" }, message: "¿Precio del sofá?", post_id: `${PAGINA}_7`, comment_id: "7_8", created_time: ahoraS(), item: "comment", parent_id: `${PAGINA}_7`, verb: "add", ...extra } }] }],
});
const conMensaje = (cuerpo: MetaCuerpo): MetaCuerpo => ({ ...cuerpo, entry: [{ ...cuerpo.entry![0], messaging: [{ sender: { id: "2838000000000001" }, recipient: { id: PAGINA }, timestamp: Date.now(), message: { mid: "m.1", text: "hola" } }] }] });
async function firmado(cuerpo: object) {
  const crudo = JSON.stringify(cuerpo);
  return new Request("https://juan.example/webhooks/meta", { method: "POST", headers: { "content-type": "application/json", "x-hub-signature-256": `sha256=${await hmacHex(SECRETO_FB, crudo)}` }, body: crudo });
}
function meta(f: typeof fetch, reloj = { t: Date.now() }) {
  return { adaptador: crearMeta({ fetch: f, dormir: async () => {}, llavero: llaveroEnMemoria(), ahora: () => reloj.t }), reloj };
}

describe("1. el filtro por página de /webhooks/meta", () => {
  it("1a. si Graph se cuelga en GET /me, el webhook igual termina (con plazo): el mensaje del aviso se guarda y se pide el reintento", async () => {
    const { adaptador } = meta(() => new Promise<Response>(() => {}));
    const inicio = Date.now();
    const r = await Promise.race([adaptador.recibir(await firmado(conMensaje(fbComentario())), envPagina), new Promise<null>((res) => setTimeout(() => res(null), 4500))]);
    expect(r).not.toBeNull();
    expect(Date.now() - inicio).toBeLessThan(4000);
    expect(r!.respuesta.status).toBe(500);
    expect(r!.guardarAntes).toBe(true);
    expect(r!.entrantes.map((e) => e.id_mensaje)).toEqual(["m.1"]);
  }, 8000);

  it("1b. si GET /me falla, se contesta 500 (Meta reintenta: nada se pierde) y en cuanto Graph vuelve, el comentario entra", async () => {
    let fallar = true;
    let preguntas = 0;
    const { adaptador, reloj } = meta(async (u) => {
      if (String(u).includes("/me?")) {
        preguntas++;
        return fallar ? Response.json({ error: { message: "caído", code: 2 } }, { status: 500 }) : Response.json({ id: PAGINA });
      }
      return Response.json({}, { status: 400 });
    });
    const a = await adaptador.recibir(await firmado(fbComentario()), envPagina);
    expect(a.respuesta.status).toBe(500);
    expect(a.entrantes).toEqual([]);
    fallar = false;
    reloj.t += 5_000;
    const b = await adaptador.recibir(await firmado(fbComentario()), envPagina); // el reintento de Meta
    expect(b.respuesta.status).toBe(200);
    expect(b.entrantes.map((e) => e.comentario?.id)).toEqual(["7_8"]);
    expect(preguntas).toBeGreaterThanOrEqual(3);
  });

  it("1b. con META_PAGE_ID de respaldo, si Meta no contesta, el comentario de la página entra igual (y uno de otra página no)", async () => {
    const { adaptador } = meta(async () => Response.json({ error: { message: "caído", code: 2 } }, { status: 500 }));
    const env = { ...envPagina, META_PAGE_ID: PAGINA } as unknown as Env;
    const r = await adaptador.recibir(await firmado(fbComentario()), env);
    expect(r.respuesta.status).toBe(200);
    expect(r.entrantes).toHaveLength(1);
    const otra: MetaCuerpo = { object: "page", entry: [{ ...fbComentario().entry![0], id: "999888777666555" }] };
    expect((await adaptador.recibir(await firmado(otra), env)).entrantes).toEqual([]);
  });

  it("(menor 1) sin permiso para ver su Instagram, /salud lo dice claro: «no sé cuál es tu Instagram»", async () => {
    const f: typeof fetch = async (u) => {
      const url = new URL(String(u));
      if (url.searchParams.get("fields") === "id") return Response.json({ id: PAGINA });
      return Response.json({ error: { message: "sin permiso", code: 10 } }, { status: 403 });
    };
    const { adaptador } = meta(f);
    const ig: MetaCuerpo = { object: "instagram", entry: [{ id: CUENTA_IG, time: ahoraS(), changes: [{ field: "comments", value: { from: { id: "1234567890123456", username: "ana" }, media: { id: "18000000000000001" }, id: "18100000000000002", text: "¿precio?" } }] }] };
    expect((await adaptador.recibir(await firmado(ig), envPagina)).entrantes).toEqual([]);
    const salud = await adaptador.salud!("instagram", envPagina);
    expect(salud.avisosComentarios?.join(" ")).toMatch(/no sé cuál es tu Instagram.*instagram_basic/);
    // Y en el informe de /salud, con «Responder comentarios» encendido.
    const informe = await informeDeSalud({
      env: { ...envPagina, JUAN_ODOO_TOKEN: "a", JUAN_WORKER_TOKEN: "b", ANTHROPIC_API_KEY: "c", URL_PUBLICA: "https://juan.example" } as unknown as Env,
      adaptadores: [crearMeta({ fetch: f, dormir: async () => {}, llavero: llaveroEnMemoria() })],
      config: async () => normalizarConfig({ canales_activos: { instagram: true, messenger: true }, comentarios: { activo: true } }),
      gastoMes: async () => 0,
      ahora: () => Date.now(),
    });
    expect(informe.avisos.some((a) => a.startsWith("no sé cuál es tu Instagram"))).toBe(true);
  });
});

describe("2. topes por persona y por hora", () => {
  it("un cliente real que pregunta en 2 publicaciones recibe 2 privadas y 1 pública (la 2.ª, aviso «tope por persona»)", async () => {
    const m = mundoComentarios();
    m.guion([PREGUNTA, { texto: "¿Cuál sofá te interesa?" }, PREGUNTA, { texto: "¿Para cuántas personas el comedor?" }]);
    await comentar(m, comentario(m, "¿Precio del sofá?"));
    await comentar(m, comentario(m, "¿Y el comedor cuánto?"));
    expect(m.canal.privadas).toHaveLength(2);
    expect(m.canal.publicas).toHaveLength(1);
    expect(m.odoo.comentarios.at(-1)).toMatchObject({ privada: "respondida", publica: "no", motivo: expect.stringMatching(/tope por persona/) });
  });

  it("(menor 2) pasado el tope, una pregunta no gasta clasificación y solo la primera deja un aviso en Odoo en 24 horas", async () => {
    const m = mundoComentarios();
    const pasos = [];
    for (let i = 0; i < 3; i++) pasos.push(PREGUNTA, { texto: `¿Cuál te interesa? ${i}` });
    m.guion(pasos);
    for (let i = 0; i < 10; i++) await comentar(m, comentario(m, `¿precio? ${i}`));
    expect(m.canal.privadas).toHaveLength(3);
    expect(m.modelo.doGenerateCalls.length).toBe(3 + 3);
    expect(m.odoo.comentarios.filter((c) => c.motivo?.includes("tope por persona") && c.privada === "no")).toHaveLength(1);
    // A las 24 horas vuelve a tener lugar.
    m.guion([PREGUNTA, { texto: "¿Cuál te interesa hoy?" }]);
    await m.pasar(24 * 3600_000);
    await comentar(m, comentario(m, "¿precio? mañana"));
    expect(m.canal.privadas).toHaveLength(4);
  });

  it("(menor 3) tope global de privadas por hora entre todas las cuentas (60 de fábrica): 5 cuentas con el tope en 10 = 10 privadas", async () => {
    const global = new AlmacenGlobal(crearSqlNode());
    let privadas = 0;
    let topeHora = 0;
    for (let k = 0; k < 5; k++) {
      const m = mundoComentarios({ id: `1784140000000${k}`, global, comentarios: { privadas_por_hora: 10 } });
      // Lo que va a pasar (el guion es uno solo, en orden): las 9 primeras privadas y la 10.ª salen; las demás no gastan turno.
      const turno = (i: number) => ({ texto: `¿Cuál te interesa? ${i}` });
      m.guion(k < 3 ? [PREGUNTA, turno(0), PREGUNTA, turno(1), PREGUNTA, turno(2)] : k === 3 ? [PREGUNTA, turno(0), PREGUNTA] : [PREGUNTA]);
      for (let i = 0; i < 3; i++) await comentar(m, comentario(m, `¿precio? ${k}-${i}`));
      privadas += m.canal.privadas.length;
      topeHora += m.odoo.comentarios.filter((c) => c.privada === "no" && /tope de la hora/.test(c.motivo ?? "")).length;
      if (k === 4) expect(m.gastoGlobal.leerSalud("comentario_tope_privadas")).not.toBeNull();
    }
    expect([privadas, topeHora]).toEqual([10, 5]);
    expect(normalizarConfig({}).comentarios.privadas_por_hora).toBe(60);
  });
});

describe("3. una palabra de queja ya no decide sola: las preguntas de compra se contestan", () => {
  const preguntasDeCompra = [
    "¿Si no me gusta lo devuelvo?",
    "¿Hacen reembolso si no me queda?",
    "¿No llegan a Chiriquí?",
    "¿Esa mesa no sirve para exterior?",
    "¿Es resistente o se rompe fácil?",
    "¿La tela se rompe con las uñas del perro?",
    "¿Es de mala calidad o buena?",
    "Estoy esperando la quincena para comprarlo 😍",
    "Esperando el catálogo 🙏",
    "¿Puedo apartarlo y que cancele el resto en la entrega?",
    "¿El sillón se tumba? ¿es reclinable?",
    "¡Mentira! ¿a ese precio? Lo quiero",
    "¿Tienen papelera para la basura del baño?",
  ];
  it("ninguna tiene palabras de queja y ninguna es «queja» por las reglas", () => {
    expect(preguntasDeCompra.filter((p) => pareceQueja(p))).toEqual([]);
    expect(preguntasDeCompra.filter((p) => clasePorReglas(p) !== null)).toEqual([]);
  });

  it("en el motor, «¿Es resistente o se rompe fácil?» recibe su privada y su pública", async () => {
    const m = mundoComentarios();
    m.guion([PREGUNTA, { texto: "Es muy resistente: estructura de madera maciza." }]);
    await comentar(m, comentario(m, "¿Es resistente o se rompe fácil?"));
    expect(m.canal.privadas).toHaveLength(1);
    expect(m.canal.publicas).toHaveLength(1);
    expect(m.odoo.comentarios.at(-1)).toMatchObject({ clase: "pregunta", privada: "respondida", publica: "respondida" });
  });

  it("con una palabra de queja que sí cuenta, la IA decide: «pregunta» = privada sin pública; «queja» = Gerencia; falla = queja", async () => {
    const pregunta = mundoComentarios();
    pregunta.guion([PREGUNTA, { texto: "Te escribo por tu comentario: ¿me das tu número de pedido?" }]);
    await comentar(pregunta, comentario(pregunta, "Sigo esperando mi pedido, ¿me dicen cuándo llega?"));
    expect([pregunta.canal.privadas.length, pregunta.canal.publicas.length]).toEqual([1, 0]);
    const queja = mundoComentarios();
    queja.guion([{ texto: '{"result":"queja"}' }]);
    await comentar(queja, comentario(queja, "Sigo esperando mi pedido, ¿me dicen cuándo llega?"));
    expect(queja.odoo.comentarios.at(-1)).toMatchObject({ clase: "queja", privada: "no", publica: "no" });
    const falla = mundoComentarios();
    falla.guion([{ error: new Error("caído") }]);
    await comentar(falla, comentario(falla, "Sigo esperando mi pedido, ¿me dicen cuándo llega?"));
    await falla.pasar(24 * 3600_000);
    expect(falla.odoo.comentarios.at(-1)).toMatchObject({ clase: "queja", privada: "no", publica: "no" });
  });

  it("las acotaciones de antes siguen (tumbona, cesto de basura, plata sola, cancelar en presente, todavía, garantía)", () => {
    for (const p of ["¿Tienen tumbonas?", "¿Venden cesto de basura?", "¿Lo tienen en plata?", "¿Puedo cancelar con Yappy?", "¿Todavía hay?", "¿Tiene garantía?", "¿Precio?"]) expect(pareceQueja(p), p).toBe(false);
  });
});

describe("4. reintentos (siguen bien)", () => {
  it("la IA cae al clasificar hasta que pasan los 7 días: no responde tarde", async () => {
    const m = mundoComentarios();
    m.guion(Array.from({ length: 10 }, () => ({ error: new Error("caído") })));
    const e = comentario(m, "¿Precio?", {}, { ts: m.ahora() - (167 * 3600_000 - 10 * 60_000) });
    await comentar(m, e);
    m.guion([PREGUNTA, { texto: "¿Cuál te interesa?" }]);
    await m.pasar(24 * 3600_000);
    expect(m.canal.privadas.length + m.canal.publicas.length).toBe(0);
  });

  it("la redacción falla dos veces y luego sale UNA privada y UNA pública; Odoo pasa de «reintento» a «respondida»", async () => {
    const m = mundoComentarios();
    m.guion([PREGUNTA, { error: new Error("caído") }]);
    await comentar(m, comentario(m, "¿Precio?"));
    m.guion([{ error: new Error("caído") }]);
    await m.pasar(31 * 60_000);
    m.guion([{ texto: "¿Cuál sofá te interesa?" }]);
    await m.pasar(3 * 3600_000 + 60_000);
    expect(m.canal.privadas).toHaveLength(1);
    expect(m.canal.publicas).toHaveLength(1);
    expect(m.odoo.comentarios.map((c) => c.privada)).toEqual(["pendiente", "reintento", "reintento", "respondida"]);
  });
});

describe("5. lo público nunca lleva el nombre (tampoco en Facebook)", () => {
  it("la frase de fábrica no tiene nombre; las de antes con «{nombre}» no quedan rotas", () => {
    expect(textoPublico(FABRICA)).toBe(FABRICA);
    expect(textoPublico("¡Hola, {nombre}! Te escribimos por mensaje directo con los detalles.")).toBe(FABRICA);
    expect(textoPublico("{nombre}: te escribimos por mensaje directo.")).toBe("Te escribimos por mensaje directo.");
    expect(textoPublico("¡{nombre}! Te escribimos por mensaje directo.")).toBe("Te escribimos por mensaje directo.");
    expect(textoPublico("¡{nombre}, gracias! Te escribimos por privado.")).toBe("¡Gracias! Te escribimos por privado.");
  });

  it("en Facebook un «nombre» que es un insulto que no está en ninguna lista tampoco sale: no sale ningún nombre", async () => {
    const m = mundoComentarios({ canal: "messenger", comentarios: { publicas_por_persona: 10, privadas_por_persona: 10 } });
    const nombres = ["Timadores Total", "Tramposos X", "Vendehumo Y", "Ana María López"];
    const pasos = [];
    for (let i = 0; i < nombres.length; i++) pasos.push(PREGUNTA, { texto: "¿Cuál te interesa?" });
    m.guion(pasos);
    for (const nombre of nombres) await comentar(m, comentario(m, "Info del comedor", {}, { nombre }));
    expect(m.canal.publicas.map((p) => p.texto)).toEqual(Array(nombres.length).fill(FABRICA));
  });

  it("el Worker ignora un texto de Ajustes con dirección web o llaves sueltas (usa el de fábrica)", () => {
    for (const t of ["Mira dcasapty.com/ofertas {nombre}", "bit.ly/x", "wa.me/50760261919", "{nombre", "Hola {cliente}"]) expect(normalizarConfig({ comentarios: { texto_publico: t } }).comentarios.texto_publico, t).toBe(FABRICA);
  });
});

describe("6. H: el eco que gana la carrera no llega a Odoo como una vendedora", () => {
  const ECO = "Te escribo por tu comentario: ¿cuál comedor te interesa?";
  const nota = (otra: Mundo, id_envio: string) => ({ canal: "messenger" as const, id_externo: "999000111", red: "facebook" as const, id_comentario: "5_6", comentario: "Info del comedor", ts_comentario: otra.ahora(), id_envio, texto: ECO, con_presentacion: false, ts: otra.ahora() });

  it("aunque la cola de Odoo corra antes del aviso, el mensaje de «vendedora» espera, el aviso lo quita y Juan contesta después", async () => {
    const vecinos = new Map<string, MotorConversacion>();
    const otra = crearMundo({ canal: "messenger", idExterno: "999000111", vecinos, config: { canales_activos: { messenger: true } } });
    otra.canal.cap = { ...otra.canal.cap, ventana24h: true };
    const eco = await otra.motor.ingest(otra.entrante(ECO, { id_mensaje: "priv9", propio: true, nombre: undefined }));
    expect(eco.accion).toBe("propio");
    await otra.pasar(5_000); // la cola de Odoo corre: el mensaje de «vendedora» todavía espera
    expect(otra.odoo.mensajes.filter((x) => x.autor === "vendedora")).toHaveLength(0);
    await otra.motor.anotarRespuestaDeComentario(nota(otra, "priv9"));
    await otra.pasar(2 * 60_000);
    expect(otra.odoo.mensajes.filter((x) => x.autor === "vendedora")).toHaveLength(0);
    expect(otra.motor.silencio()).toBe(false);
    otra.guion([{ texto: "El comedor Milán lo tenemos." }]);
    await otra.conversar("El de 6 puestos");
    expect(otra.canal.textos.join("\n")).toContain("El comedor Milán lo tenemos.");
  });

  it("si de verdad fue una vendedora (nadie avisa), su mensaje llega a Odoo al minuto", async () => {
    const otra = crearMundo({ canal: "messenger", idExterno: "999000222", config: { canales_activos: { messenger: true } } });
    otra.canal.cap = { ...otra.canal.cap, ventana24h: true };
    await otra.motor.ingest(otra.entrante("Hola, te escribo por tu comentario, soy Karla de D'CASA.", { id_mensaje: "mano1", propio: true, nombre: undefined }));
    await otra.pasar(5_000);
    expect(otra.odoo.mensajes.filter((x) => x.autor === "vendedora")).toHaveLength(0);
    await otra.pasar(61_000);
    expect(otra.odoo.mensajes.filter((x) => x.autor === "vendedora")).toHaveLength(1);
    expect(otra.motor.silencio()).toBe(true);
  });

  it("en una conversación con historia, el mensaje de una vendedora va a Odoo enseguida (como siempre)", async () => {
    const m = crearMundo({ canal: "messenger", idExterno: "999000333", config: { canales_activos: { messenger: true } } });
    m.canal.cap = { ...m.canal.cap, ventana24h: true };
    m.guion([{ texto: "¡Hola! ¿En qué te ayudo?" }]);
    await m.conversar("Hola");
    await m.motor.ingest(m.entrante("Te atiendo yo", { id_mensaje: "mano2", propio: true, nombre: undefined }));
    await m.pasar(2_000);
    expect(m.odoo.mensajes.filter((x) => x.autor === "vendedora")).toHaveLength(1);
  });
});
