import { describe, expect, it } from "vitest";
import { enviarSecuencia, type MedioListo } from "../contenedor/lib/envio.mjs";
import { crearRegistroDeEnvios } from "../contenedor/lib/propios.mjs";
import { RITMO_POR_DEFECTO } from "../contenedor/lib/ritmo.mjs";
import { CLIENTE, SockFalso, msgTexto } from "./ayuda/baileys";

/** Un «reloj» virtual: `dormir` no espera, solo suma, y los envíos quedan fechados en ese reloj. */
function montar(opciones: Partial<Parameters<typeof enviarSecuencia>[0]> = {}) {
  const sock = new SockFalso({});
  const registro = crearRegistroDeEnvios();
  let ids = 0;
  const dormido: number[] = [];
  const base = {
    sock,
    jid: CLIENTE,
    burbujas: ["Hola Karen.", "Sí, tenemos camas queen."],
    medios: [] as MedioListo[],
    generarId: () => `ID${++ids}`,
    registro,
    ritmo: RITMO_POR_DEFECTO,
    dormir: async (ms: number) => {
      dormido.push(ms);
      sock.reloj.t += ms;
    },
    azar: () => 0.5,
    ...opciones,
  };
  return { sock, registro, dormido, correr: () => enviarSecuencia(base as any) };
}

const IMAGEN: MedioListo = { tipo: "imagen", bytes: Buffer.from("JPG"), mime: "image/jpeg", nombre: "cama.jpg", pie: "Cama Queen", restoPie: [] };
const DOC: MedioListo = { tipo: "documento", bytes: Buffer.from("PDF"), mime: "application/pdf", nombre: "Cotización.pdf", restoPie: [] };

describe("enviarSecuencia: ritmo humano", () => {
  it("manda las burbujas en orden y devuelve sus ids", async () => {
    const { sock, correr } = montar();
    const r = await correr();
    expect(r).toEqual({ ok: true, ids: ["ID1", "ID2"], enviados: { chunks: 2, medios: 0 } });
    expect(sock.enviados.map((e) => e.args[1])).toEqual([{ text: "Hola Karen." }, { text: "Sí, tenemos camas queen." }]);
    expect(sock.enviados.every((e) => e.args[0] === CLIENTE)).toBe(true);
  });

  it("al menos 1 s entre una burbuja y la siguiente (contrato con Juan)", async () => {
    const { sock, correr } = montar({ burbujas: ["uno", "dos", "tres", "cuatro"] });
    await correr();
    const t = sock.enviados.map((e) => e.t);
    for (let i = 1; i < t.length; i++) expect(t[i] - t[i - 1]).toBeGreaterThanOrEqual(1000);
  });

  it("incluso con el azar al mínimo, la espera entre burbujas no baja de 1 s", async () => {
    const { sock, correr } = montar({ azar: () => 0, burbujas: ["a", "b", "c"] });
    await correr();
    const t = sock.enviados.map((e) => e.t);
    for (let i = 1; i < t.length; i++) expect(t[i] - t[i - 1]).toBeGreaterThanOrEqual(1000);
  });

  it("muestra «escribiendo…» ANTES de cada texto y lo quita al enviar", async () => {
    const { sock, correr } = montar();
    await correr();
    const orden = sock.llamadas.map((l) => l.tipo);
    expect(orden).toEqual([
      "presenceSubscribe",
      "sendPresenceUpdate", // composing
      "sendPresenceUpdate", // paused
      "sendMessage",
      "sendPresenceUpdate", // composing
      "sendPresenceUpdate", // paused
      "sendMessage",
    ]);
    const presencias = sock.llamadas.filter((l) => l.tipo === "sendPresenceUpdate").map((l) => l.args[0]);
    expect(presencias).toEqual(["composing", "paused", "composing", "paused"]);
    const primeraEscritura = sock.llamadas.find((l) => l.args[0] === "composing")!;
    expect(primeraEscritura.args[1]).toBe(CLIENTE);
    expect(primeraEscritura.t).toBeLessThan(sock.enviados[0].t); // empezó a «escribir» antes de enviar
  });

  it("antes de la primera burbuja hay una pausa de «leer», y marca como leído el último mensaje del cliente", async () => {
    const ultimo = msgTexto("hola");
    const { sock, dormido, correr } = montar({ ultimoEntrante: { key: ultimo.key } });
    await correr();
    expect(sock.llamadas[0]).toMatchObject({ tipo: "readMessages", args: [[ultimo.key]] });
    expect(dormido[0]).toBeGreaterThanOrEqual(RITMO_POR_DEFECTO.pensarMinMs);
    expect(dormido[0]).toBeLessThanOrEqual(RITMO_POR_DEFECTO.pensarMaxMs);
  });

  it("el tiempo de «escribiendo…» crece con el largo del texto", async () => {
    const corto = montar({ burbujas: ["ok"] });
    await corto.correr();
    const largo = montar({ burbujas: ["x".repeat(150)] });
    await largo.correr();
    const escribirCorto = corto.dormido[1];
    const escribirLargo = largo.dormido[1];
    expect(escribirLargo).toBeGreaterThan(escribirCorto);
  });

  it("anota el id ANTES de enviar (así el eco no se confunde con la vendedora)", async () => {
    const { sock, registro, correr } = montar();
    let vistoAntes = false;
    const original = sock.sendMessage.bind(sock);
    sock.sendMessage = async (jid: string, c: any, o: any) => {
      vistoAntes = registro.tiene(o.messageId);
      return original(jid, c, o);
    };
    await correr();
    expect(vistoAntes).toBe(true);
    expect(registro.tiene("ID1")).toBe(true);
    expect(registro.tiene("ID2")).toBe(true);
    expect(sock.enviados[0].args[2]).toEqual({ messageId: "ID1" });
  });

  it("la presencia es un adorno: si falla, el mensaje sale igual", async () => {
    const { sock, correr } = montar();
    sock.sendPresenceUpdate = async () => {
      throw new Error("presencia caída");
    };
    sock.presenceSubscribe = async () => {
      throw new Error("presencia caída");
    };
    const r = await correr();
    expect(r.ok).toBe(true);
    expect(sock.enviados).toHaveLength(2);
  });
});

describe("enviarSecuencia: imágenes y documentos", () => {
  it("imagen con pie → { image, caption } y documento → { document, fileName, mimetype }", async () => {
    const { sock, correr } = montar({ burbujas: ["Mira esta."], medios: [IMAGEN, DOC] });
    const r = await correr();
    expect(r).toMatchObject({ ok: true, enviados: { chunks: 1, medios: 2 } });
    const contenidos = sock.enviados.map((e) => e.args[1]);
    expect(contenidos[0]).toEqual({ text: "Mira esta." });
    expect(contenidos[1]).toEqual({ image: IMAGEN.bytes, mimetype: "image/jpeg", caption: "Cama Queen" });
    expect(contenidos[2]).toEqual({ document: DOC.bytes, mimetype: "application/pdf", fileName: "Cotización.pdf" });
    // Se manda el archivo ya descargado y comprobado, NUNCA una URL para que Baileys la baje por su cuenta.
    for (const c of contenidos) {
      expect(JSON.stringify(c, (_k, v) => (v instanceof Uint8Array ? "bytes" : v))).not.toMatch(/"url"/);
    }
  });

  it("sin pie, sin caption", async () => {
    const { sock, correr } = montar({ burbujas: [], medios: [{ ...IMAGEN, pie: undefined }] });
    await correr();
    expect(sock.enviados[0].args[1]).not.toHaveProperty("caption");
  });

  it("los restos de un pie largo salen como texto justo después de su archivo", async () => {
    const { sock, correr } = montar({ burbujas: [], medios: [{ ...IMAGEN, restoPie: ["Segunda parte del pie."] }, { ...DOC }] });
    await correr();
    const contenidos = sock.enviados.map((e) => e.args[1]);
    expect(contenidos.map((c) => (c.text ? "texto" : c.image ? "imagen" : "documento"))).toEqual(["imagen", "texto", "documento"]);
  });

  it("a un archivo también lo precede una pausa, pero no el «escribiendo…»", async () => {
    const { sock, correr } = montar({ burbujas: [], medios: [IMAGEN] });
    await correr();
    expect(sock.llamadas.some((l) => l.args[0] === "composing")).toBe(false);
  });

  it("también respeta el segundo entre un texto y su imagen", async () => {
    const { sock, correr } = montar({ burbujas: ["Mira"], medios: [IMAGEN] });
    await correr();
    expect(sock.enviados[1].t - sock.enviados[0].t).toBeGreaterThanOrEqual(1000);
  });
});

describe("enviarSecuencia: cuando algo falla a mitad", () => {
  it("devuelve lo que SÍ salió, para no repetirlo", async () => {
    const { sock, correr } = montar({ burbujas: ["uno", "dos", "tres"] });
    sock.fallarEnElEnvio = 2;
    const r = await correr();
    expect(r).toEqual({ ok: false, ids: ["ID1"], enviados: { chunks: 1, medios: 0 }, error: "socket cerrado a medias" });
    expect(sock.enviados).toHaveLength(1);
  });

  it("si falla el primero, no salió nada", async () => {
    const { sock, correr } = montar();
    sock.fallarEnElEnvio = 1;
    const r = await correr();
    expect(r).toMatchObject({ ok: false, ids: [] });
  });
});
