/**
 * `cotizar`: Juan arma la cotización (Odoo calcula todo) y el PDF sale como archivo junto con la respuesta. El enlace firmado del PDF
 * nunca le llega al modelo; solo va una cotización por respuesta; un «no» de Odoo (apagada, código que no existe) le llega al modelo con
 * su explicación. Y «más fotos»: otras de la galería, sin repetir.
 */
import { describe, expect, it } from "vitest";
import { RechazoDeOdoo } from "../helpers/odooFalso";
import { crearMundo } from "../helpers/mundo";

const cotizar = (...lineas: { codigo: string; cantidad?: number; opcion?: string }[]) => ({ nombre: "cotizar", args: { lineas } });
const ver = (codigo: string) => ({ nombre: "ver_producto", args: { codigo } });
const foto = (codigo: string, adicionales?: boolean) => ({ nombre: "enviar_foto_producto", args: adicionales === undefined ? { codigo } : { codigo, adicionales } });

// 2 × $799.50 + $499.00 = $2,098.00; ITBMS $146.86; total $2,244.86
const PIDE = "mándame la cotización del sofá (2) y la cama";
const LINEAS = [{ codigo: "SOFA-3P-002", cantidad: 2 }, { codigo: "CAMA-Q-001" }];

describe("cotizar: el PDF sale como documento junto con la respuesta", () => {
  it("manda el PDF por el canal y el texto dice el total que calculó Odoo", async () => {
    const m = crearMundo();
    m.guion([{ llamadas: [cotizar(...LINEAS)] }, { texto: "Listo, te armé la cotización con el sofá y la cama. El total es $2,244.86 con ITBMS. El PDF va adjunto." }]);
    await m.conversar(PIDE);
    expect(m.canal.medios).toEqual([
      { tipo: "documento", url: expect.stringMatching(/^https:\/\/dcasa\.example\/dcasa\/adjunto\/41\/\d+\/a{64}\/Cotizacion-S00008\.pdf$/), nombre: "Cotizacion-S00008.pdf", mime: "application/pdf", sinCopia: true },
    ]);
    expect(m.canal.textos.join("\n")).toContain("$2,244.86");
    expect(m.odoo.cotizacionesArmadas).toBe(1);
    expect(m.odoo.llamadas.find((l) => l.nombre === "cotizar")!.args).toEqual({ lineas: LINEAS });
  });

  it("el modelo NO ve el enlace del PDF: solo que va adjunto", async () => {
    const m = crearMundo();
    const g = m.guion([{ llamadas: [cotizar(...LINEAS)] }, { texto: "Listo, el PDF va adjunto." }]);
    await m.conversar(PIDE);
    const visto = g.prompts()[1];
    expect(visto).not.toContain("dcasa/adjunto");
    expect(visto).not.toContain("a".repeat(64));
    expect(visto).toContain('"pdf_adjunto":true');
    expect(visto).toContain("2,244.86");
  });

  it("en Odoo queda solo la línea de texto: no se baja una segunda copia de su propio archivo", async () => {
    const m = crearMundo();
    m.guion([{ llamadas: [cotizar(...LINEAS)] }, { texto: "Listo, el PDF va adjunto." }]);
    await m.conversar(PIDE);
    await m.pasar(1_000);
    const saliente = m.odoo.mensajes.filter((x) => x.autor === "bot").at(-1)!;
    expect(saliente.texto).toContain("[Documento enviado: Cotizacion-S00008.pdf]");
    expect(saliente.texto).not.toContain("Foto enviada");
    expect(saliente.adjuntos ?? []).toEqual([]);
  });

  it("en el historial del modelo el archivo queda como «Documento enviado», no como foto", async () => {
    const m = crearMundo();
    const g = m.guion([{ llamadas: [cotizar(...LINEAS)] }, { texto: "Listo, el PDF va adjunto." }, { texto: "De nada." }]);
    await m.conversar(PIDE);
    await m.conversar("gracias");
    expect(g.prompts().at(-1)).toContain("[Documento enviado: Cotizacion-S00008.pdf]");
  });

  it("solo va una cotización por respuesta: la segunda ni siquiera llega a Odoo", async () => {
    const m = crearMundo();
    const g = m.guion([{ llamadas: [cotizar(...LINEAS)] }, { llamadas: [cotizar({ codigo: "MESA-C-003" })] }, { texto: "Te mando esa; si cambias algo, me dices." }]);
    await m.conversar(PIDE);
    expect(m.odoo.llamadas.filter((l) => l.nombre === "cotizar")).toHaveLength(1);
    expect(m.canal.medios).toHaveLength(1);
    expect(g.prompts()[2]).toContain("ya_va_una");
  });

  it("un enlace que no es https no se manda como archivo y el modelo lo sabe", async () => {
    const m = crearMundo();
    const original = m.odoo.manejadores.cotizar;
    m.odoo.manejadores.cotizar = (a, o) => {
      const r = original(a, o) as { documento: { url: string } };
      return { ...r, documento: { ...r.documento, url: "http://malo.example/x.pdf" } };
    };
    const g = m.guion([{ llamadas: [cotizar(...LINEAS)] }, { texto: "Una vendedora te manda el documento." }]);
    await m.conversar(PIDE);
    expect(m.canal.medios).toHaveLength(0);
    expect(g.prompts()[1]).toContain('"pdf_adjunto":false');
  });

  it("si el canal no lleva documentos, el PDF sale como enlace en el texto", async () => {
    const m = crearMundo();
    m.canal.cap = { ...m.canal.cap, documentos: false };
    m.guion([{ llamadas: [cotizar(...LINEAS)] }, { texto: "Aquí va tu cotización." }]);
    await m.conversar(PIDE);
    expect(m.canal.medios).toHaveLength(0);
    expect(m.canal.textos.join("\n")).toContain("Cotizacion-S00008.pdf: https://dcasa.example/dcasa/adjunto/41/");
  });
});

describe("cotizar: el interruptor de Ajustes y los «no» de Odoo", () => {
  it("apagada: no sale ningún PDF y el modelo recibe la orden de pasar a una vendedora", async () => {
    const m = crearMundo();
    m.odoo.cotizacionAutomatica = false;
    const g = m.guion([{ llamadas: [cotizar(...LINEAS)] }, { texto: "Una vendedora te prepara la cotización." }]);
    await m.conversar(PIDE);
    expect(m.canal.medios).toHaveLength(0);
    expect(m.odoo.cotizacionesArmadas).toBe(0);
    expect(g.prompts()[1]).toContain("apagada");
    expect(g.prompts()[1]).toContain("pasar_a_vendedora");
  });

  it("un código que no existe: el modelo lee la explicación de Odoo en vez de un «no pude consultar»", async () => {
    const m = crearMundo();
    const g = m.guion([{ llamadas: [cotizar({ codigo: "INVENTADO-9" })] }, { texto: "Ese código no lo manejamos." }]);
    await m.conversar("cotízame el INVENTADO-9");
    expect(m.canal.medios).toHaveLength(0);
    expect(g.prompts()[1]).toContain("No encuentro el código «INVENTADO-9»");
    expect(g.prompts()[1]).not.toContain("No pude consultar el sistema ahora");
  });

  it("un fallo que no es una explicación de Odoo (se cayó, 401…) sigue siendo «no pude consultar»", async () => {
    const m = crearMundo();
    m.odoo.manejadores.cotizar = () => {
      throw new Error("Odoo POST /herramienta → 401 token inválido JUAN_ODOO_TOKEN");
    };
    const g = m.guion([{ llamadas: [cotizar(...LINEAS)] }, { texto: "Una vendedora te la manda." }]);
    await m.conversar(PIDE);
    expect(g.prompts()[1]).toContain("No pude consultar el sistema ahora");
    expect(g.prompts()[1]).not.toContain("JUAN_ODOO_TOKEN");
  });

  it("una explicación de Odoo muy larga se recorta", async () => {
    const m = crearMundo();
    m.odoo.manejadores.cotizar = () => {
      throw new RechazoDeOdoo("x".repeat(2000));
    };
    const g = m.guion([{ llamadas: [cotizar(...LINEAS)] }, { texto: "Una vendedora te la manda." }]);
    await m.conversar(PIDE);
    // El falso de Odoo no recorta (lo hace el cliente real); aquí basta con que llegue como explicación y no como fallo genérico.
    expect(g.prompts()[1]).toContain("xxxx");
  });

  it("el modelo puede decir el total que devolvió la herramienta, pero uno inventado se rechaza", async () => {
    const m = crearMundo();
    m.guion([{ llamadas: [cotizar(...LINEAS)] }, { texto: "El total es $1,200.00 con ITBMS, el PDF va adjunto." }]);
    await m.conversar(PIDE);
    expect(m.canal.textos.join("\n")).not.toContain("$1,200.00");
  });
});

describe("«más fotos»: otras de la galería, sin repetir ninguna", () => {
  const galeria = (n: number) => Array.from({ length: n }, (_, i) => `/web/image/product.image/${i + 10}/image_1024`);
  const conGaleria = (m: ReturnType<typeof crearMundo>, n: number) => {
    m.odoo.manejadores.ver_producto = (a) => ({
      producto: { codigo: String(a.codigo), nombre: "Cama Queen Milán", precio: 499, mas_itbms: true, foto: "/web/image/product.template/1/image_1024", galeria: galeria(n) },
    });
  };
  const urls = (m: ReturnType<typeof crearMundo>) => m.canal.medios.map((x) => x.url.replace("https://dcasapty.com", ""));

  it("la primera pide la principal; «más fotos» manda 3 de la galería; luego las que quedan; luego avisa que no hay más", async () => {
    const m = crearMundo();
    conGaleria(m, 5);
    const g = m.guion([
      { llamadas: [ver("CAMA-Q-001")] }, { llamadas: [foto("CAMA-Q-001")] }, { texto: "Aquí la tienes." },
      { llamadas: [ver("CAMA-Q-001")] }, { llamadas: [foto("CAMA-Q-001", true)] }, { texto: "Aquí van más." },
      { llamadas: [ver("CAMA-Q-001")] }, { llamadas: [foto("CAMA-Q-001", true)] }, { texto: "Y estas." },
      { llamadas: [ver("CAMA-Q-001")] }, { llamadas: [foto("CAMA-Q-001", true)] }, { texto: "Esas son todas las que tengo." },
    ]);
    await m.conversar("foto de la cama queen");
    expect(urls(m)).toEqual(["/web/image/product.template/1/image_1024"]);
    await m.conversar("¿tienes más fotos?");
    expect(urls(m).slice(1)).toEqual(galeria(5).slice(0, 3));
    await m.conversar("y más?");
    expect(urls(m).slice(4)).toEqual(galeria(5).slice(3));
    await m.conversar("otra más");
    expect(m.canal.medios).toHaveLength(6);
    expect(g.prompts().at(-1)).toContain("Ya le mandaste todas las fotos");
    expect(new Set(urls(m)).size).toBe(6);
  });

  it("si la principal también está en la galería no se repite", async () => {
    const m = crearMundo();
    m.odoo.manejadores.ver_producto = () => ({
      producto: { codigo: "CAMA-Q-001", nombre: "Cama", precio: 499, mas_itbms: true, foto: "/web/image/product.template/1/image_1024", galeria: ["/web/image/product.template/1/image_1024", "/web/image/product.image/11/image_1024"] },
    });
    m.guion([{ llamadas: [ver("CAMA-Q-001")] }, { llamadas: [foto("CAMA-Q-001", true)] }, { texto: "Aquí va una más." }]);
    await m.conversar("más fotos de la cama");
    expect(urls(m)).toEqual(["/web/image/product.image/11/image_1024"]);
  });

  it("sin consultar el producto en el turno, no hay galería: la herramienta dice qué hacer", async () => {
    const m = crearMundo();
    const g = m.guion([{ llamadas: [foto("CAMA-Q-001", true)] }, { texto: "Un momento." }]);
    await m.conversar("más fotos");
    expect(m.canal.medios).toHaveLength(0);
    expect(g.prompts()[1]).toContain("consulta primero el producto con ver_producto");
  });

  it("nunca más de tres fotos por respuesta, aunque la pida varias veces", async () => {
    const m = crearMundo();
    conGaleria(m, 8);
    m.guion([{ llamadas: [ver("CAMA-Q-001")] }, { llamadas: [foto("CAMA-Q-001", true), foto("CAMA-Q-001", true)] }, { texto: "Aquí van." }]);
    await m.conversar("muéstrame todas las fotos");
    expect(m.canal.medios).toHaveLength(3);
  });

  it("una galería de un solo producto no se mezcla con la de otro", async () => {
    const m = crearMundo();
    m.odoo.manejadores.ver_producto = (a) => ({
      producto: { codigo: String(a.codigo), nombre: String(a.codigo), precio: 10, mas_itbms: true, foto: `/f/${String(a.codigo)}.jpg`, galeria: [`/g/${String(a.codigo)}-1.jpg`] },
    });
    m.guion([{ llamadas: [ver("A1"), ver("B2")] }, { llamadas: [foto("A1", true)] }, { texto: "Aquí va." }]);
    await m.conversar("más fotos de A1");
    expect(urls(m)).toEqual(["/g/A1-1.jpg"]);
  });
});
