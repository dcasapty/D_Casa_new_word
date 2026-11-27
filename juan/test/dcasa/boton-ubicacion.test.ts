/**
 * El botón nativo «Enviar ubicación» de WhatsApp (docs/UBICACION.md; el dueño, 2026-11-25: «que pida la ubicación de la forma más fácil
 * posible» y «que un niño de 5 años pueda comprar»):
 *
 *   · sale solo cuando el modelo llamó `enlace_de_ubicacion` y Odoo dijo `boton_whatsapp: true`, y solo en el canal que lo tiene (WhatsApp
 *     Cloud): WhatsApp por QR, Telegram, Messenger e Instagram se quedan con el texto y su enlace;
 *   · va DESPUÉS del texto con el enlace, y si Meta lo rechaza el turno no se cae: el enlace ya salió;
 *   · el modelo nunca ve `boton_whatsapp` (es una señal para el Worker), y los pasos con íconos de la frase de Odoo (1️⃣ 2️⃣ 3️⃣) llegan
 *     enteros aunque pasen de dos emojis.
 */
import { describe, expect, it } from "vitest";
import { crearMundo } from "../helpers/mundo";
import { DEF_ENLACE_DE_UBICACION, ENLACE_DE_UBICACION, FRASE_DEL_ENLACE, HERRAMIENTAS_DE_PRUEBA } from "../helpers/odooFalso";
import { adaptadorDe, crearAdaptadores } from "../../src/canales/index";
import type { CanalId } from "../../src/canales/tipos";
import { MARCA_BOTON_UBICACION, TEXTO_BOTON_UBICACION } from "../../src/canales/ubicacion";
import { crearWhatsappCloud } from "../../src/canales/whatsappCloud";
import { PARAMETRO_OTRA_CASA } from "../../src/motor/herramientas";
import type { Env } from "../../src/env";

const ADAPTADORES = crearAdaptadores();

/** Una conversación en `canal`, encendido en Ajustes de Juan (fuera del de siempre, los canales empiezan apagados). */
const mundoEn = (canal: CanalId) => crearMundo({ canal, idExterno: canal.startsWith("whatsapp") ? "50760261919" : "998877", config: { canales_activos: { [canal]: true } } });

/** Una conversación en `canal` (con las capacidades REALES de ese canal) donde el modelo manda el enlace para marcar el punto. */
function mundoConEnlace(canal: CanalId, boton: unknown, respuesta = FRASE_DEL_ENLACE, args: Record<string, unknown> = {}) {
  const m = mundoEn(canal);
  m.odoo.defs = [...HERRAMIENTAS_DE_PRUEBA, DEF_ENLACE_DE_UBICACION];
  m.odoo.botonWhatsapp = boton;
  m.canal.cap = adaptadorDe(canal, ADAPTADORES)!.capacidades(canal);
  const g = m.guion([{ llamadas: [{ nombre: "enlace_de_ubicacion", args }] }, { texto: respuesta }]);
  return { m, g };
}

describe("el botón «Enviar ubicación» después del enlace", () => {
  it("WhatsApp Cloud con boton_whatsapp: el texto con el enlace y, al final, el botón; el modelo no ve la señal", async () => {
    const { m, g } = mundoConEnlace("whatsapp_cloud", true);
    await m.conversar("¿cuánto es el envío a mi casa?");
    expect(m.odoo.de("enlace_de_ubicacion")).toHaveLength(1);
    const salida = m.canal.ultimaSalida!;
    expect(salida.pedirUbicacion).toBe(TEXTO_BOTON_UBICACION);
    expect(m.canal.botonesDeUbicacion).toEqual([TEXTO_BOTON_UBICACION]);
    // El texto con el enlace salió entero, con sus pasos y sus íconos (los escribió Odoo, no el modelo).
    const texto = salida.burbujas.join("\n");
    expect(texto).toContain(ENLACE_DE_UBICACION);
    for (const paso of ["1️⃣ Abra el enlace", "2️⃣ Toque «Mi ubicación» y permita", "3️⃣ Escriba su número de casa"]) expect(texto).toContain(paso);
    // La señal es para el Worker: el modelo nunca la ve.
    expect(g.prompts().join("\n")).not.toContain("boton_whatsapp");
  });

  it("lo que salió queda en la historia y en Odoo: el botón es la última parte, con su id y su marca", async () => {
    const { m } = mundoConEnlace("whatsapp_cloud", true);
    await m.conversar("¿cómo le paso mi dirección?");
    await m.pasar(60_000);
    expect(m.motor.mensajes.ultimos(1)[0]).toMatchObject({ rol: "bot", texto: TEXTO_BOTON_UBICACION });
    const registrado = m.odoo.mensajes.find((x) => x.autor === "bot")!;
    expect(registrado.texto.split("\n").at(-1)).toBe(`${TEXTO_BOTON_UBICACION} ${MARCA_BOTON_UBICACION}`);
    const partes = (registrado as { partes?: { id_canal: string; texto?: string }[] }).partes!;
    expect(partes).toHaveLength(m.canal.ultimaSalida!.burbujas.length + 1);
    expect(partes.at(-1)).toMatchObject({ texto: TEXTO_BOTON_UBICACION });
  });

  it("sin boton_whatsapp (o con otro valor que true) no hay botón: el enlace solo", async () => {
    for (const boton of [undefined, false, "true", 1]) {
      const { m } = mundoConEnlace("whatsapp_cloud", boton);
      await m.conversar("¿cuánto es el envío a mi casa?");
      expect(m.canal.ultimaSalida!.burbujas.join("\n"), String(boton)).toContain(ENLACE_DE_UBICACION);
      expect(m.canal.ultimaSalida!.pedirUbicacion, String(boton)).toBeUndefined();
      expect(m.canal.botonesDeUbicacion).toEqual([]);
    }
  });

  it("solo en WhatsApp Cloud: por QR, Telegram, Messenger e Instagram sale el enlace sin botón, aunque Odoo lo pida", async () => {
    for (const canal of ["whatsapp_qr", "telegram", "messenger", "instagram"] as const) {
      const { m } = mundoConEnlace(canal, true);
      await m.conversar("¿cuánto es el envío a mi casa?");
      expect(m.canal.ultimaSalida!.burbujas.join("\n"), canal).toContain(ENLACE_DE_UBICACION);
      expect(m.canal.ultimaSalida!.pedirUbicacion, canal).toBeUndefined();
    }
  });

  it("sin enlace_de_ubicacion en el turno no hay botón", async () => {
    const m = mundoEn("whatsapp_cloud");
    m.odoo.defs = [...HERRAMIENTAS_DE_PRUEBA, DEF_ENLACE_DE_UBICACION];
    m.odoo.botonWhatsapp = true;
    m.canal.cap = adaptadorDe("whatsapp_cloud", ADAPTADORES)!.capacidades("whatsapp_cloud");
    m.guion([{ texto: "Con gusto le ayudo. ¿Qué talla busca?" }]);
    await m.conversar("hola");
    expect(m.canal.ultimaSalida!.pedirUbicacion).toBeUndefined();
  });

  it("si la respuesta se descarta (deja ver algo interno), el botón no la acompaña", async () => {
    const { m } = mundoConEnlace("whatsapp_cloud", true, "Le mando el enlace_de_ubicacion: " + ENLACE_DE_UBICACION);
    await m.conversar("¿cuánto es el envío a mi casa?");
    expect(m.canal.ultimaSalida!.burbujas.join("\n")).not.toContain("enlace_de_ubicacion");
    expect(m.canal.ultimaSalida!.pedirUbicacion).toBeUndefined();
  });

  it("si el canal rechaza el botón, el turno no se cae: el enlace salió, no se reintenta ni pasa a una vendedora", async () => {
    const { m } = mundoConEnlace("whatsapp_cloud", true);
    m.canal.rechazarBotonDeUbicacion = true;
    await m.conversar("¿cuánto es el envío a mi casa?");
    await m.pasar(30 * 60_000);
    expect(m.canal.salidas).toHaveLength(1);
    expect(m.canal.textos.join("\n")).toContain(ENLACE_DE_UBICACION);
    expect(m.motor.mensajes.ultimos(5).map((f) => f.texto)).not.toContain(TEXTO_BOTON_UBICACION);
    expect(m.odoo.mensajes.find((x) => x.autor === "bot")!.texto).not.toContain(MARCA_BOTON_UBICACION);
    expect(m.odoo.de("pasar_a_vendedora")).toEqual([]);
    expect(m.registros.filter((r) => r.nivel === "error")).toEqual([]);
  });
});

describe("para otra casa (un regalo, la abuela, el trabajo): el enlace sin botón", () => {
  const RESPUESTA = `Con gusto. Abra este enlace y busque su barriada, o mueva el mapa hasta su casa: ${ENLACE_DE_UBICACION}`;

  it("el modelo ve `para_otra_casa` en la herramienta; con true no sale el botón y a Odoo no le llega el parámetro", async () => {
    const { m, g } = mundoConEnlace("whatsapp_cloud", true, RESPUESTA, { para_otra_casa: true });
    await m.conversar("es para mi mamá, que vive en Arraiján");
    const esquema = g.doGenerateCalls[0].tools!.find((t) => t.name === "enlace_de_ubicacion") as unknown as { inputSchema: { properties: Record<string, { type: string }> } };
    expect(esquema.inputSchema.properties[PARAMETRO_OTRA_CASA].type).toBe("boolean");
    expect(m.odoo.de("enlace_de_ubicacion").map((l) => l.args)).toEqual([{}]);
    expect(m.canal.ultimaSalida!.pedirUbicacion).toBeUndefined();
    expect(m.canal.botonesDeUbicacion).toEqual([]);
    expect(m.canal.textos.join(" ")).toContain(ENLACE_DE_UBICACION);
  });

  it("el modelo recibe cómo decírselo: que busque la barriada o mueva el mapa (no «Mi ubicación», que sería la del teléfono)", async () => {
    const { m, g } = mundoConEnlace("whatsapp_cloud", true, RESPUESTA, { para_otra_casa: true });
    await m.conversar("es para mi mamá, que vive en Arraiján");
    const resultado = g.prompts()[1];
    expect(resultado).toContain("Es para otra casa");
    expect(resultado).toContain("busque la barriada o mueva el mapa hasta esa casa");
    expect(resultado).not.toContain("boton_whatsapp");
  });

  it("con false (o sin el parámetro) es la de siempre: sale el botón", async () => {
    const { m } = mundoConEnlace("whatsapp_cloud", true, FRASE_DEL_ENLACE, { para_otra_casa: false });
    await m.conversar("¿cuánto es el envío a mi casa?");
    expect(m.canal.botonesDeUbicacion).toEqual([TEXTO_BOTON_UBICACION]);
    expect(m.odoo.de("enlace_de_ubicacion").map((l) => l.args)).toEqual([{}]);
  });

  it("si Odoo ya declara `para_otra_casa`, le llega tal cual (y tampoco sale el botón)", async () => {
    const { m } = mundoConEnlace("whatsapp_cloud", true, RESPUESTA, { para_otra_casa: true });
    m.odoo.defs = [...HERRAMIENTAS_DE_PRUEBA, { ...DEF_ENLACE_DE_UBICACION, parametros: { type: "object", properties: { para_otra_casa: { type: "boolean" } } } }];
    await m.conversar("es para mi mamá, que vive en Arraiján");
    expect(m.odoo.de("enlace_de_ubicacion").map((l) => l.args)).toEqual([{ para_otra_casa: true }]);
    expect(m.canal.botonesDeUbicacion).toEqual([]);
  });
});

describe("con el adaptador REAL de WhatsApp Cloud y Meta de mentira", () => {
  const ENV = { WHATSAPP_CLOUD_TOKEN: "token-cloud-0123456789", WHATSAPP_PHONE_NUMBER_ID: "109876543210", META_APP_SECRET: "s", META_VERIFY_TOKEN: "v" };

  function conMeta(rechazarBoton: boolean) {
    const { m } = mundoConEnlace("whatsapp_cloud", true);
    const cuerpos: Record<string, any>[] = [];
    const f: typeof fetch = async (_url, init) => {
      const cuerpo = JSON.parse(String(init?.body));
      cuerpos.push(cuerpo);
      if (cuerpo.type === "interactive" && rechazarBoton) return Response.json({ error: { message: "(#131009) Parameter value is not valid", code: 131009 } }, { status: 400 });
      return Response.json({ messages: [{ id: `wamid.OUT${cuerpos.length}` }] });
    };
    (m.deps as { canal: unknown }).canal = () => crearWhatsappCloud({ fetch: f, dormir: async () => {} });
    Object.assign(m.deps.env as Env, ENV);
    return { m, cuerpos };
  }

  it("el botón sale como location_request_message, después de los textos", async () => {
    const { m, cuerpos } = conMeta(false);
    await m.conversar("¿cuánto es el envío a mi casa?");
    expect(cuerpos.length).toBeGreaterThan(1);
    expect(cuerpos.slice(0, -1).every((c) => c.type === "text")).toBe(true);
    expect(cuerpos.at(-1)).toEqual({
      messaging_product: "whatsapp",
      recipient_type: "individual",
      to: "50760261919",
      type: "interactive",
      interactive: { type: "location_request_message", body: { text: TEXTO_BOTON_UBICACION }, action: { name: "send_location" } },
    });
    expect(m.motor.mensajes.ultimos(1)[0]).toMatchObject({ rol: "bot", texto: TEXTO_BOTON_UBICACION, id_mensaje: `wamid.OUT${cuerpos.length}` });
  });

  it("si Meta rechaza el botón, los textos no se repiten y el turno termina bien", async () => {
    const { m, cuerpos } = conMeta(true);
    await m.conversar("¿cuánto es el envío a mi casa?");
    await m.pasar(30 * 60_000);
    const textos = cuerpos.filter((c) => c.type === "text");
    const botones = cuerpos.filter((c) => c.type === "interactive");
    expect(botones).toHaveLength(1);
    expect(textos.map((c) => c.text.body).join("\n")).toContain(ENLACE_DE_UBICACION);
    // Una sola vez cada texto: el rechazo del botón no hizo reintentar el envío.
    expect(new Set(textos.map((c) => c.text.body)).size).toBe(textos.length);
    expect(m.odoo.de("pasar_a_vendedora")).toEqual([]);
    expect(m.odoo.mensajes.filter((x) => x.autor === "bot")).toHaveLength(1);
  });
});
