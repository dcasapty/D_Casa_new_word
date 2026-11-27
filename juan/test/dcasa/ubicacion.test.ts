/**
 * La ubicación de entrega en el motor de los canales (docs/UBICACION.md, «Contrato entre Odoo y el Worker de Juan»):
 *
 *   · cuando el cliente la comparte, el Worker llama `POST /ubicacion` ANTES de llamar al modelo (y aunque el bot no conteste);
 *   · si quedó guardada, el modelo ve el envío ya cotizado como consulta previa de `cotizar_envio` y una nota con la zona; si no es de
 *     Panamá, que pida otra; si Odoo no contestó, que pida el barrio;
 *   · las coordenadas NUNCA llegan al modelo, ni a lo que guarda el Durable Object, ni al registro, ni al texto que va a Odoo.
 */
import { describe, expect, it } from "vitest";
import { crearMundo, type Mundo } from "../helpers/mundo";
import { ENVIO_POR_UBICACION, ZONA_POR_UBICACION } from "../helpers/odooFalso";
import { MotorConversacion } from "../../src/motor/conversacion";
import { prepararEntrante } from "../../src/canales/preparar";
import { TEXTO_ENLACE_DE_MAPA, TEXTO_UBICACION_COMPARTIDA, type UbicacionEntrante } from "../../src/canales/ubicacion";

const PUNTO: UbicacionEntrante = { lat: 9.0012345, lon: -79.5123456, origen: "whatsapp", nombre_lugar: "Super 99 Brisas", direccion: "Vía Domingo Díaz" };
/** Cualquier rastro del punto: las coordenadas (con o sin todos sus decimales) y el lugar que eligió. */
const RASTROS = /9\.00123|79\.51234|Super 99|Domingo D/;
const FRASE = ENVIO_POR_UBICACION.frase_para_el_cliente;

/** Todo lo que el Durable Object tiene guardado (cada fila de cada tabla), como texto. */
function todoLoGuardado(m: Mundo): string {
  const tablas = m.deps.sql.todos<{ name: string }>("SELECT name FROM sqlite_master WHERE type = 'table'");
  return JSON.stringify(tablas.map((t) => m.deps.sql.todos(`SELECT * FROM ${t.name}`)));
}

/** Lo que salió del Worker hacia afuera, menos `POST /ubicacion`: el modelo, el registro, Odoo (mensajes y herramientas) y el canal. */
function todoLoDemas(m: Mundo): string {
  return JSON.stringify([m.modelo.prompts(), m.registros, m.odoo.mensajes, m.odoo.llamadas, m.canal.salidas]);
}

/** El cliente comparte su ubicación por el chat (y no escribe nada más). */
const compartir = (m: Mundo, u: UbicacionEntrante = PUNTO) => m.conversar(TEXTO_UBICACION_COMPARTIDA, { ubicacion: u });

describe("el cliente comparte su ubicación por el chat", () => {
  it("va a Odoo (POST /ubicacion) una sola vez, con la conversación, ANTES de llamar al modelo", async () => {
    const m = crearMundo();
    let guardadasAlPensar = -1;
    m.guion([{ texto: FRASE, alGenerar: () => void (guardadasAlPensar = m.odoo.ubicaciones.length) }]);
    await compartir(m);
    await m.pasar(60_000);
    expect(m.odoo.ubicaciones).toEqual([{ conversacion_id: 12, lat: 9.0012345, lon: -79.5123456, origen: "whatsapp", nombre_lugar: "Super 99 Brisas", direccion: "Vía Domingo Díaz" }]);
    expect(guardadasAlPensar).toBe(1);
    // Primero se registra su mensaje (así existe la conversación), después el punto, y al final la respuesta.
    expect(m.odoo.orden).toEqual(["mensaje:cliente", "ubicacion", "mensaje:bot"]);
  });

  it("el modelo ve el envío ya cotizado (como cotizar_envio) y la zona, y contesta con el precio; ninguna coordenada", async () => {
    const m = crearMundo();
    const g = m.guion([{ texto: FRASE }]);
    await compartir(m);
    const prompt = g.prompts()[0];
    expect(prompt).toContain("<envio_por_ubicacion>");
    expect(prompt).toContain("frase_para_el_cliente");
    expect(prompt).toContain(FRASE);
    expect(prompt).toContain(`quedó guardada como su punto de entrega (zona: ${ZONA_POR_UBICACION})`);
    expect(prompt).toContain(TEXTO_UBICACION_COMPARTIDA);
    // El respaldo del envío es para la guardia, no para el modelo.
    expect(prompt).not.toContain("respaldo_envio");
    expect(prompt).not.toMatch(RASTROS);
    // La guardia deja pasar el precio porque el envío consultado lo respalda.
    expect(m.canal.textos.join("\n")).toContain("cuesta $5.");
    // No se volvió a consultar el envío: ya venía hecho.
    expect(m.odoo.de("cotizar_envio")).toEqual([]);
  });

  it("nada de lo que guarda el Durable Object, ni el registro, ni lo que va a Odoo o al canal lleva el punto", async () => {
    const m = crearMundo();
    m.guion([{ texto: FRASE }]);
    await compartir(m);
    await m.pasar(60_000);
    expect(todoLoGuardado(m)).not.toMatch(RASTROS);
    expect(todoLoDemas(m)).not.toMatch(RASTROS);
    // Lo que sí queda con el mensaje: que la compartió, que quedó guardada y la zona.
    const contexto = JSON.parse(m.motor.mensajes.buscar("wamid-1")!.contexto!);
    expect(contexto.ubicacion).toMatchObject({ origen: "whatsapp", estado: "guardada", zona: ZONA_POR_UBICACION });
    expect(m.odoo.mensajes[0].texto).toBe(TEXTO_UBICACION_COMPARTIDA);
  });

  it("en la vuelta siguiente la nota con la zona sigue en el historial, pero el envío no se vuelve a poner como consulta previa", async () => {
    const m = crearMundo();
    const g = m.guion([{ texto: FRASE }, { texto: "Con gusto." }]);
    await compartir(m);
    await m.conversar("gracias");
    const segundo = g.prompts()[1];
    expect(segundo).toContain(`zona: ${ZONA_POR_UBICACION}`);
    expect(segundo).not.toContain("<envio_por_ubicacion>");
    expect(segundo).not.toMatch(RASTROS);
    expect(m.odoo.ubicaciones).toHaveLength(1);
  });

  it("aunque una vendedora tenga la conversación (el bot no contesta), el punto se guarda igual", async () => {
    const m = crearMundo();
    const g = m.guion([{ texto: "no debía contestar" }]);
    await m.motor.fijarEstado({ estado: "humano" });
    await compartir(m);
    await m.pasar(60_000);
    expect(m.odoo.ubicaciones).toHaveLength(1);
    expect(g.doGenerateCalls).toHaveLength(0);
    expect(m.canal.salidas).toEqual([]);
  });

  it("si el punto no es de Panamá, no hay envío y el modelo sabe que tiene que pedir otro", async () => {
    const m = crearMundo();
    m.odoo.respuestaUbicacion = () => ({ ok: false, error: "Odoo contestó 422", motivo: "fuera_de_panama", estado: 422 });
    const g = m.guion([{ texto: "Esa ubicación no es de Panamá. ¿Me compartes la de entrega?" }]);
    await compartir(m);
    const prompt = g.prompts()[0];
    expect(prompt).toContain("no es de Panamá");
    expect(prompt).not.toContain("<envio_por_ubicacion>");
    expect(prompt).not.toMatch(RASTROS);
    expect(JSON.parse(m.motor.mensajes.buscar("wamid-1")!.contexto!).ubicacion).toEqual({ origen: "whatsapp", estado: "fuera_de_panama" });
  });

  it("si Odoo dice que las coordenadas no sirven, que la comparta otra vez", async () => {
    const m = crearMundo();
    m.odoo.respuestaUbicacion = () => ({ ok: false, error: "Odoo contestó 422", motivo: "coordenadas", estado: 422 });
    const g = m.guion([{ texto: "¿Me la compartes otra vez?" }]);
    await compartir(m);
    expect(g.prompts()[0]).toContain("no se pudo usar");
  });

  it("si Odoo no responde: el modelo sabe que no se guardó y pide el barrio; no se reintenta solo", async () => {
    const m = crearMundo();
    m.odoo.respuestaUbicacion = () => ({ ok: false, error: "Odoo contestó 503", estado: 503 });
    const g = m.guion([{ texto: "¿Me dices el barrio?" }]);
    await compartir(m);
    await m.pasar(30 * 60_000);
    expect(g.prompts()[0]).toContain("no se pudo guardar ahora: pídele el barrio");
    expect(g.prompts()[0]).not.toContain("<envio_por_ubicacion>");
    expect(m.odoo.ubicaciones).toHaveLength(1);
    // Al registro solo va el estado, nunca el punto.
    expect(m.registros.some((r) => /no quedó guardada en Odoo: no_guardada \(HTTP 503\)/.test(r.mensaje))).toBe(true);
    expect(JSON.stringify(m.registros)).not.toMatch(RASTROS);
  });

  it("con Odoo caído hasta la ráfaga, el punto no se guarda a ciegas: queda «no guardada» y se pide el barrio", async () => {
    const m = crearMundo();
    m.guion([{ texto: "¿Me dices el barrio?" }]);
    m.odoo.caido = true;
    await m.escribir(TEXTO_UBICACION_COMPARTIDA, { ubicacion: PUNTO });
    await m.pasar(16_000);
    expect(m.odoo.ubicaciones).toEqual([]);
    expect(JSON.parse(m.motor.mensajes.buscar("wamid-1")!.contexto!).ubicacion).toEqual({ origen: "whatsapp", estado: "no_guardada" });
    m.odoo.caido = false;
    await m.pasar(30 * 60_000);
    // Lo que no se guardó a tiempo no se manda después: el cliente ya recibió la pregunta por el barrio.
    expect(m.odoo.ubicaciones).toEqual([]);
    expect(todoLoGuardado(m)).not.toMatch(RASTROS);
  });

  it("si el objeto se reinicia antes de mandarlo, el punto se perdió (no estaba guardado): se le pide otra vez", async () => {
    const m = crearMundo();
    const g = m.guion([{ texto: "¿Me la compartes otra vez?" }]);
    // Odoo no contesta justo cuando llega el mensaje (el punto espera en la memoria)…
    m.odoo.caido = true;
    await m.escribir(TEXTO_UBICACION_COMPARTIDA, { ubicacion: PUNTO });
    await m.pasar(1000);
    // …y el objeto se reinicia: su memoria se pierde, su almacén no.
    m.motor = new MotorConversacion(m.deps);
    m.odoo.caido = false;
    await m.pasar(60_000);
    expect(m.odoo.ubicaciones).toEqual([]);
    expect(g.prompts()[0]).toContain("no se pudo guardar ahora");
  });

  it("«Borrar mis datos» mientras el punto espera: no se manda", async () => {
    const m = crearMundo();
    m.guion([{ texto: "x" }]);
    m.odoo.caido = true;
    await m.escribir(TEXTO_UBICACION_COMPARTIDA, { ubicacion: PUNTO });
    await m.motor.olvidar();
    m.odoo.caido = false;
    await m.pasar(60_000);
    expect(m.odoo.ubicaciones).toEqual([]);
  });

  it("una ubicación que la tienda comparte desde el teléfono (propio) no es el punto de nadie: no va a Odoo", async () => {
    const m = crearMundo();
    await m.escribir("(se compartió una ubicación desde el teléfono de la tienda)", { propio: true, ubicacion: PUNTO });
    await m.pasar(60_000);
    expect(m.odoo.ubicaciones).toEqual([]);
    expect(todoLoGuardado(m)).not.toMatch(RASTROS);
  });

  it("`ubicacion_omitida` (la copia de rescate o la cola del puente no guardan el punto): el modelo pide la ubicación otra vez", async () => {
    const m = crearMundo();
    const g = m.guion([{ texto: "¿Me la compartes otra vez?" }]);
    await m.conversar(TEXTO_UBICACION_COMPARTIDA, { ubicacion_omitida: "whatsapp" });
    expect(m.odoo.ubicaciones).toEqual([]);
    expect(g.prompts()[0]).toContain("no se pudo guardar ahora");
  });

  it("un Odoo sin la ruta (un cliente sin `guardarUbicacion`): no se guarda y se pide el barrio", async () => {
    const m = crearMundo();
    (m.odoo as { guardarUbicacion?: unknown }).guardarUbicacion = undefined;
    const g = m.guion([{ texto: "¿Me dices el barrio?" }]);
    await compartir(m);
    expect(g.prompts()[0]).toContain("no se pudo guardar ahora");
  });
});

describe("un enlace de mapa en el texto", () => {
  it("se guarda con origen «enlace» y el modelo ve la frase, no el enlace ni las coordenadas", async () => {
    const m = crearMundo();
    const g = m.guion([{ texto: FRASE }]);
    const e = await prepararEntrante(m.entrante("https://maps.google.com/?q=9.0012345,-79.5123456"));
    await m.motor.ingest(e);
    await m.pasar(16_000);
    expect(m.odoo.ubicaciones).toEqual([{ conversacion_id: 12, lat: 9.0012345, lon: -79.5123456, origen: "enlace" }]);
    expect(g.prompts()[0]).toContain(TEXTO_ENLACE_DE_MAPA);
    expect(g.prompts()[0]).toContain("con un enlace de mapa y quedó guardada");
    expect(g.prompts()[0]).not.toMatch(RASTROS);
    expect(m.odoo.mensajes[0].texto).toBe(TEXTO_ENLACE_DE_MAPA);
    expect(todoLoGuardado(m)).not.toMatch(RASTROS);
  });
});
