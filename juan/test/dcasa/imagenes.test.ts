/**
 * La dueña (2026-10-09): muchos clientes mandan una captura de un producto o de una publicación. Si un lector aparte entiende con claridad
 * que es un producto, el bot lo busca en el catálogo y contesta sin pedir el código y sin una vendedora. Comprobantes de pago y
 * documentos de identidad NUNCA se tratan así: ante cualquier señal o duda, la imagen sigue el camino de siempre (regla 5).
 */
import { describe, expect, it } from "vitest";
import type { LecturaImagen } from "../../src/motor/vision";
import { crearMundo } from "../helpers/mundo";

const BYTES = new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 1, 2, 3, 4, 5, 6, 7, 8]);
const imagen = (nombre = "captura.jpg") => ({ adjuntos: [{ tipo: "imagen" as const, mime: "image/jpeg", nombre, bytes: BYTES }] });

const PUBLICACION: LecturaImagen = { tipo: "publicacion", codigos: ["822F"], categoria: "cama", medida: "full", parece_pago: false, parece_identidad: false };
const COMPROBANTE: LecturaImagen = { tipo: "comprobante", codigos: [], categoria: null, medida: null, parece_pago: true, parece_identidad: false };

describe("captura de un producto o de una publicación", () => {
  it("el modelo recibe lo que se leyó (código, tipo, medida), no la imagen, y no se le avisa de «NO lo ves»", async () => {
    const m = crearMundo({ mirarImagen: async () => PUBLICACION });
    const g = m.guion([{ texto: "Sí, la cama 822F está disponible." }]);
    await m.conversar("¿esta la tienen?", imagen());
    const visto = g.prompts()[0];
    expect(visto).toContain("Un lector aparte la miró");
    expect(visto).toContain("código: «822F»");
    expect(visto).toContain("tipo: cama");
    expect(visto).toContain("medida: full");
    expect(visto).toContain("no le pidas al cliente el código otra vez");
    expect(visto).toContain("NO lo repitas ni lo confirmes");
    expect(visto).not.toContain("NO lo ves y no puedes describirlo");
    // Ni los bytes ni nada de la imagen viajan al modelo que conversa.
    const planos = JSON.stringify(g.doGenerateCalls.map((c) => c.prompt));
    expect(planos).not.toMatch(/base64|255,216|data:image/);
  });

  it("no se le deja una nota a la vendedora (el bot la atiende), pero la imagen queda en la conversación de Odoo sin datos de la lectura", async () => {
    const m = crearMundo({ mirarImagen: async () => PUBLICACION });
    m.guion([{ texto: "Sí, la cama 822F está disponible." }]);
    await m.conversar("¿esta la tienen?", imagen());
    expect(m.odoo.de("anotar_conversacion")).toHaveLength(0);
    const delCliente = m.odoo.mensajes.find((x) => x.autor === "cliente")!;
    expect(delCliente.adjuntos).toHaveLength(1);
    expect(delCliente.adjuntos![0].tipo).toBe("imagen");
    expect(JSON.stringify(delCliente)).not.toContain("lectura");
    expect(JSON.stringify(delCliente)).not.toContain("822F");
  });

  it("una foto de un mueble sin código, pero con tipo y medida, también se busca en el catálogo", async () => {
    const m = crearMundo({ mirarImagen: async () => ({ ...PUBLICACION, tipo: "producto", codigos: [] }) });
    const g = m.guion([{ texto: "Tenemos camas full; ¿te muestro?" }]);
    await m.conversar("", imagen("foto.jpg"));
    expect(g.prompts()[0]).toContain("Búscalo con buscar_productos usando el tipo y la medida");
  });
});

describe("comprobantes y documentos: siguen el camino de siempre", () => {
  it("un comprobante: el bot no lo ve, queda anotado para una vendedora y se etiqueta «Comprobante recibido»", async () => {
    const m = crearMundo({ mirarImagen: async () => COMPROBANTE });
    const g = m.guion([{ texto: "Recibí tu archivo. Una vendedora lo revisa." }]);
    await m.conversar("te mando el pago", imagen("yappy.jpg"));
    const visto = g.prompts()[0];
    expect(visto).toContain("NO lo ves y no puedes describirlo");
    expect(visto).toContain("NUNCA des por confirmado un pago");
    expect(visto).not.toContain("Un lector aparte");
    expect(m.odoo.de("anotar_conversacion")).toHaveLength(1);
    expect(m.odoo.de("etiquetar_conversacion").map((c) => c.args.etiqueta)).toEqual(["Comprobante recibido"]);
  });

  it("una imagen que el lector llamó «producto» pero con señal de pago o de identidad se trata como sensible", async () => {
    for (const señal of [{ parece_pago: true }, { parece_identidad: true }]) {
      const m = crearMundo({ mirarImagen: async () => ({ ...PUBLICACION, ...señal }) });
      const g = m.guion([{ texto: "Recibí tu archivo. Una vendedora lo revisa." }]);
      await m.conversar("mira", imagen());
      expect(g.prompts()[0], JSON.stringify(señal)).toContain("NO lo ves y no puedes describirlo");
      expect(g.prompts()[0]).not.toContain("código: «822F»");
      expect(m.odoo.de("anotar_conversacion")).toHaveLength(1);
    }
  });

  it("una cédula no se etiqueta como comprobante ni se lee: solo se anota", async () => {
    const m = crearMundo({ mirarImagen: async () => ({ tipo: "identidad", codigos: [], categoria: null, medida: null, parece_pago: false, parece_identidad: true }) });
    const g = m.guion([{ texto: "Recibí tu archivo." }]);
    await m.conversar("mi cédula", imagen("cedula.jpg"));
    expect(g.prompts()[0]).toContain("NO lo ves y no puedes describirlo");
    expect(m.odoo.de("anotar_conversacion")).toHaveLength(1);
    expect(m.odoo.de("etiquetar_conversacion")).toHaveLength(0);
  });
});

describe("si el lector no puede, todo sigue como antes", () => {
  it.each([
    ["no hay lector (apagado)", undefined],
    ["el lector falla", async () => { throw new Error("sin cupo de Workers AI"); }],
    ["el lector no entendió nada (null)", async () => null],
    ["la imagen es ilegible", async () => ({ ...PUBLICACION, tipo: "ilegible" as const, codigos: [], categoria: null })],
  ])("%s: la imagen la revisa una vendedora y el bot pide el código", async (_caso, lector) => {
    const m = crearMundo({ mirarImagen: lector as never });
    const g = m.guion([{ texto: "Recibí tu imagen. ¿Me dices el código?" }]);
    await m.conversar("¿esta la tienen?", imagen());
    expect(g.prompts()[0]).toContain("NO lo ves y no puedes describirlo");
    expect(m.odoo.de("anotar_conversacion")).toHaveLength(1);
  });

  it("un fallo del lector queda en el registro como aviso", async () => {
    const m = crearMundo({ mirarImagen: async () => { throw new Error("sin cupo"); } });
    m.guion([{ texto: "Recibí tu imagen." }]);
    await m.conversar("hola", imagen());
    expect(m.registros.some((r) => r.nivel === "warn" && /no se pudo leer la imagen/.test(r.mensaje))).toBe(true);
  });
});

describe("tope de lecturas (cada una cuesta un poco de IA)", () => {
  it("lee hasta 3 imágenes por mensaje", async () => {
    let n = 0;
    const m = crearMundo({ mirarImagen: async () => (n++, PUBLICACION) });
    m.guion([{ texto: "Veo varias." }]);
    const cinco = { adjuntos: Array.from({ length: 5 }, (_, i) => ({ tipo: "imagen" as const, mime: "image/jpeg", nombre: `f${i}.jpg`, bytes: BYTES })) };
    await m.conversar("mira estas", cinco);
    expect(n).toBe(3);
  });

  it("lee hasta 10 al día por persona; las demás siguen el camino de siempre", async () => {
    let n = 0;
    const m = crearMundo({ mirarImagen: async () => (n++, PUBLICACION) });
    m.guion([{ texto: "Veo." }]);
    for (let i = 0; i < 12; i++) await m.conversar(`foto ${i} distinta ${"x".repeat(i)}`, imagen(`f${i}.jpg`));
    expect(n).toBe(10);
  });
});
