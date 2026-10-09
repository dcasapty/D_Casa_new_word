/**
 * `enviar_foto_producto(codigo)`: herramienta local. Usa la URL de foto que devolvió `ver_producto`/`buscar_productos` y sale por
 * el canal como imagen. El modelo nunca arma una URL: solo puede mandar fotos que Odoo le dio.
 */
import { describe, expect, it } from "vitest";
import { procesarResultado, RegistroDelTurno, resolverUrl } from "../../src/motor/herramientas";
import { crearMundo } from "../helpers/mundo";

const ver = (codigo: string) => ({ nombre: "ver_producto", args: { codigo } });
const foto = (codigo: string) => ({ nombre: "enviar_foto_producto", args: { codigo } });

describe("la foto de un producto sale por el canal como imagen", () => {
  it("manda la foto de ver_producto, con la URL absoluta del sitio y el nombre como pie", async () => {
    const m = crearMundo();
    m.guion([
      { llamadas: [ver("CAMA-Q-001")] },
      { llamadas: [foto("CAMA-Q-001")] },
      { texto: "Te la envío por aquí. ¿Qué te parece?" },
    ]);
    await m.conversar("mándame la foto de la cama queen");
    expect(m.canal.medios).toEqual([
      { tipo: "imagen", url: "https://dcasapty.com/web/image/product.template/1/image_1024", nombre: "Cama Queen Milán", pie: "Cama Queen Milán" },
    ]);
    // El texto sale primero y la foto después.
    expect(m.canal.ultimaSalida!.burbujas.join("\n")).toContain("Te la envío por aquí");
  });

  it("una URL que ya es absoluta (https) se usa tal cual", async () => {
    const m = crearMundo();
    m.guion([{ llamadas: [ver("SOFA-3P-002")] }, { llamadas: [foto("SOFA-3P-002")] }, { texto: "Aquí va." }]);
    await m.conversar("foto del sofá");
    expect(m.canal.medios[0].url).toBe("https://dcasapty.com/web/image/product.template/2/image_1024");
  });

  it("el código se acepta en minúsculas", async () => {
    const m = crearMundo();
    m.guion([{ llamadas: [ver("CAMA-Q-001")] }, { llamadas: [foto("cama-q-001")] }, { texto: "Aquí va." }]);
    await m.conversar("foto de la cama");
    expect(m.canal.medios).toHaveLength(1);
  });

  it("también sirve la foto que salió de buscar_productos", async () => {
    const m = crearMundo();
    m.guion([{ llamadas: [{ nombre: "buscar_productos", args: { consulta: "cama" } }] }, { llamadas: [foto("CAMA-Q-001")] }, { texto: "Aquí va." }]);
    await m.conversar("foto de la cama");
    expect(m.canal.medios).toHaveLength(1);
  });

  it("queda registrada en Odoo como adjunto de imagen del mensaje del bot", async () => {
    const m = crearMundo();
    m.guion([{ llamadas: [ver("CAMA-Q-001")] }, { llamadas: [foto("CAMA-Q-001")] }, { texto: "Aquí va." }]);
    await m.conversar("foto de la cama");
    await m.pasar(1_000);
    const saliente = m.odoo.mensajes.filter((x) => x.autor === "bot").at(-1)!;
    expect(saliente.adjuntos).toEqual([{ tipo: "imagen", url: "https://dcasapty.com/web/image/product.template/1/image_1024", nombre: "Cama Queen Milán", mime: undefined }]);
  });
});

describe("el modelo no puede mandar cualquier cosa", () => {
  it("un código que no consultó antes no tiene foto", async () => {
    const m = crearMundo();
    const g = m.guion([{ llamadas: [foto("INVENTADO-999")] }, { texto: "No tengo esa foto a la mano." }]);
    await m.conversar("foto del mueble inventado");
    expect(m.canal.medios).toHaveLength(0);
    expect(g.prompts()[1]).toContain("No tengo la foto de ese código");
  });

  it("una URL del modelo no existe: la herramienta solo recibe un código", async () => {
    const m = crearMundo();
    m.guion([{ llamadas: [{ nombre: "enviar_foto_producto", args: { codigo: "https://malo.example/virus.jpg" } }] }, { texto: "No pude." }]);
    await m.conversar("foto");
    expect(m.canal.medios).toHaveLength(0);
  });

  it("como mucho tres fotos por respuesta", async () => {
    const m = crearMundo();
    m.odoo.manejadores.buscar_productos = () => ({
      productos: ["A1", "A2", "A3", "A4"].map((c) => ({ codigo: c, nombre: `Mueble ${c}`, precio: 100, mas_itbms: true, disponibilidad: "disponible", foto: `/web/image/${c}.jpg` })),
    });
    m.guion([
      { llamadas: [{ nombre: "buscar_productos", args: { consulta: "" } }] },
      { llamadas: ["A1", "A2", "A3", "A4"].map(foto) },
      { texto: "Te mando tres; si quieres las demás, dime." },
    ]);
    await m.conversar("fotos de todo");
    expect(m.canal.medios).toHaveLength(3);
  });

  it("la misma foto no se manda dos veces en una respuesta", async () => {
    const m = crearMundo();
    m.guion([{ llamadas: [ver("CAMA-Q-001")] }, { llamadas: [foto("CAMA-Q-001"), foto("CAMA-Q-001")] }, { texto: "Aquí va." }]);
    await m.conversar("foto");
    expect(m.canal.medios).toHaveLength(1);
  });

  it("una foto con http (sin https) o de una ruta rara no se acepta", () => {
    expect(resolverUrl("http://x.example/a.jpg", "https://dcasapty.com")).toBeNull();
    expect(resolverUrl("//otro.example/a.jpg", "https://dcasapty.com")).toBeNull();
    expect(resolverUrl("javascript:alert(1)", "https://dcasapty.com")).toBeNull();
    expect(resolverUrl("/web/image/1", undefined)).toBeNull();
    expect(resolverUrl("/web/image/1", "https://dcasapty.com/")).toBe("https://dcasapty.com/web/image/1");
  });
});

describe("las fotos de turnos anteriores siguen disponibles", () => {
  it("«mándame la foto de la primera» en el turno siguiente", async () => {
    const m = crearMundo();
    m.guion([
      { llamadas: [{ nombre: "buscar_productos", args: { consulta: "cama" } }] },
      { texto: "Tenemos la Cama Queen Milán (CAMA-Q-001). ¿Te mando la foto?" },
      { llamadas: [foto("CAMA-Q-001")] },
      { texto: "Aquí va." },
    ]);
    await m.conversar("¿tienen camas?");
    expect(m.canal.medios).toHaveLength(0);
    await m.conversar("sí, mándala");
    expect(m.canal.medios).toHaveLength(1);
  });
});

describe("canales que no pueden llevar imágenes", () => {
  it("la foto sale como enlace en el texto", async () => {
    const m = crearMundo();
    m.canal.cap = { ...m.canal.cap, imagenes: false };
    m.guion([{ llamadas: [ver("CAMA-Q-001")] }, { llamadas: [foto("CAMA-Q-001")] }, { texto: "Aquí va." }]);
    await m.conversar("foto");
    expect(m.canal.medios).toHaveLength(0);
    expect(m.canal.textos.join("\n")).toContain("https://dcasapty.com/web/image/product.template/1/image_1024");
  });
});

describe("el registro de fotos del turno", () => {
  it("encuentra fotos en 'foto', 'imagen_url' y 'galeria', y arma precio_texto", () => {
    const reg = new RegistroDelTurno();
    const r = procesarResultado(
      { productos: [{ codigo: "a1", precio: 10, foto: "/f/a1.jpg" }, { codigo: "b2", imagen_url: "https://x.example/b2.jpg", precio: 20.5 }, { codigo: "c3", galeria: [{ url: "/f/c3.jpg" }] }] },
      reg,
      "https://dcasapty.com",
    ) as { productos: { precio_texto?: string }[] };
    expect([...reg.fotos.keys()].sort()).toEqual(["A1", "B2", "C3"]);
    expect(reg.fotos.get("A1")!.url).toBe("https://dcasapty.com/f/a1.jpg");
    expect(reg.fotos.get("B2")!.url).toBe("https://x.example/b2.jpg");
    expect(r.productos[0].precio_texto).toBe("$10.00 + ITBMS");
    expect(r.productos[1].precio_texto).toBe("$20.50 + ITBMS");
    expect([...reg.preciosProducto].sort((a, b) => a - b)).toEqual([10, 20.5]);
  });

  it("si mas_itbms es false, no agrega ITBMS", () => {
    const reg = new RegistroDelTurno();
    const r = procesarResultado({ codigo: "x", precio: 5, mas_itbms: false }, reg, undefined) as { precio_texto?: string };
    expect(r.precio_texto).toBeUndefined();
  });
});
