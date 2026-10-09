/**
 * Lo que una vendedora manda desde Odoo con una foto o un documento y un texto sale como UN solo mensaje para el cliente
 * (el texto va de pie de la primera foto), en los canales que lo permiten. En los demás, como siempre: texto y luego el archivo.
 */
import { describe, expect, it } from "vitest";
import { crearMundo } from "../helpers/mundo";

const FOTO = { tipo: "imagen", url: "https://dcasapty.com/web/image/1/foto.jpg", nombre: "cuarto.jpg", mime: "image/jpeg" };
const PDF = { tipo: "documento", url: "https://dcasapty.com/web/content/2/cotizacion.pdf", nombre: "cotizacion.pdf", mime: "application/pdf" };

function mundoConPie(pie: boolean) {
  const m = crearMundo();
  m.canal.cap = { ...m.canal.cap, pie };
  return m;
}

describe("foto con su texto: una sola burbuja", () => {
  it("el texto viaja como pie de la foto y no sale aparte", async () => {
    const m = mundoConPie(true);
    await m.motor.enviarVendedora({ texto: "Mira cómo queda la cama gris", adjuntos: [FOTO] });
    expect(m.canal.textos).toEqual([]);
    expect(m.canal.medios).toHaveLength(1);
    expect(m.canal.medios[0]).toMatchObject({ tipo: "imagen", url: FOTO.url, pie: "Mira cómo queda la cama gris" });
  });

  it("con varios archivos, el texto va de pie del PRIMERO y los demás salen sin pie", async () => {
    const m = mundoConPie(true);
    await m.motor.enviarVendedora({ texto: "Te mando todo", adjuntos: [PDF, FOTO] });
    expect(m.canal.textos).toEqual([]);
    expect(m.canal.medios.map((x) => [x.tipo, x.pie])).toEqual([["documento", "Te mando todo"], ["imagen", undefined]]);
  });

  it("si el canal no permite pie de foto, sale como siempre: el texto y luego el archivo", async () => {
    const m = mundoConPie(false);
    await m.motor.enviarVendedora({ texto: "Mira cómo queda", adjuntos: [FOTO] });
    expect(m.canal.textos).toEqual(["Mira cómo queda"]);
    expect(m.canal.medios[0].pie).toBeUndefined();
  });

  it("un texto muy largo no cabe de pie de foto: sale aparte", async () => {
    const m = mundoConPie(true);
    const largo = "Una explicación larga. ".repeat(60);
    await m.motor.enviarVendedora({ texto: largo, adjuntos: [FOTO] });
    expect(m.canal.textos.join(" ")).toContain("Una explicación larga.");
    expect(m.canal.medios[0].pie).toBeUndefined();
  });

  it("sin texto, solo el archivo; sin archivo, solo el texto", async () => {
    const m = mundoConPie(true);
    await m.motor.enviarVendedora({ adjuntos: [FOTO] });
    await m.motor.enviarVendedora({ texto: "Hola" });
    expect(m.canal.medios).toHaveLength(1);
    expect(m.canal.medios[0].pie).toBeUndefined();
    expect(m.canal.textos).toEqual(["Hola"]);
  });

  it("un audio o un video (que salen como enlace) mantienen el texto como burbuja aparte", async () => {
    const m = mundoConPie(true);
    await m.motor.enviarVendedora({ texto: "Escucha esto", adjuntos: [FOTO, { tipo: "audio", url: "https://dcasapty.com/a.ogg", nombre: "a.ogg" }] });
    expect(m.canal.textos).toContain("Escucha esto");
    expect(m.canal.medios[0].pie).toBeUndefined();
  });

  it("el asistente sabe después qué se le dijo al cliente junto a la foto (queda en su historial)", async () => {
    const m = mundoConPie(true);
    await m.motor.enviarVendedora({ texto: "La entrega la coordina Karen", adjuntos: [FOTO] });
    const historial = m.deps.sql.todos<{ texto: string; rol: string }>("SELECT texto, rol FROM mensajes ORDER BY id");
    expect(historial.some((f) => f.rol === "vendedora" && f.texto.includes("La entrega la coordina Karen"))).toBe(true);
  });
});
