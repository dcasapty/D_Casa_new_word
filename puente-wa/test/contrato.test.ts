import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import {
  MAX_MEDIOS,
  MAX_MENSAJES_POR_PETICION,
  TIPOS_ENTRANTES,
  construirWebhook,
  validarEnviar,
  validarWebhook,
} from "../contenedor/lib/contrato.mjs";

// El contrato es docs/JUAN.md, «Worker juan ↔ puente QR». Estas pruebas fijan la FORMA del JSON que
// sale (puente → Juan) y del que entra (Juan → puente); si alguien cambia el contrato o el código,
// una de las dos partes rompe aquí en vez de romper en producción.

const TS = Date.UTC(2026, 9, 9, 14, 3, 0);

describe("contrato puente → Juan: POST /webhooks/whatsapp-qr", () => {
  it("texto", () => {
    const j = construirWebhook({ idMensaje: "3EB0AAA", de: "50760261919", nombre: "Karen", tipo: "texto", texto: "Hola, ¿tienen camas queen?", ts: TS, propio: false, jid: "50760261919@s.whatsapp.net" });
    expect(j).toEqual({
      id_mensaje: "3EB0AAA",
      de: "50760261919",
      nombre: "Karen",
      tipo: "texto",
      texto: "Hola, ¿tienen camas queen?",
      ts: "2026-10-09T14:03:00.000Z",
      propio: false,
      jid: "50760261919@s.whatsapp.net",
    });
    expect(validarWebhook(j)).toEqual([]);
  });

  it.each(["imagen", "audio", "documento", "video"])("%s con medio en base64", (tipo) => {
    const j = construirWebhook({
      idMensaje: "ID1",
      de: "50760261919",
      nombre: null,
      tipo,
      medio: { base64: "AAAA", mime: "application/octet-stream", nombre: "archivo.bin" },
      ts: TS,
      propio: false,
    });
    expect(j.medio).toEqual({ base64: "AAAA", mime: "application/octet-stream", nombre: "archivo.bin" });
    expect(j).not.toHaveProperty("texto");
    expect(validarWebhook(j)).toEqual([]);
  });

  it("un archivo con leyenda lleva el texto Y el medio", () => {
    const j = construirWebhook({ idMensaje: "ID1", de: "50760261919", nombre: "K", tipo: "imagen", texto: "Esta es la cama", medio: { base64: "AAAA", mime: "image/jpeg", nombre: "imagen.jpg" }, ts: TS, propio: false });
    expect(j.texto).toBe("Esta es la cama");
    expect(validarWebhook(j)).toEqual([]);
  });

  it("propio:true cuando la vendedora escribe desde el teléfono", () => {
    const j = construirWebhook({ idMensaje: "ID2", de: "50760261919", nombre: null, tipo: "texto", texto: "Buenas tardes, le atiende Marisol", ts: TS, propio: true });
    expect(j.propio).toBe(true);
    expect(j.nombre).toBe(null);
    expect(validarWebhook(j)).toEqual([]);
  });

  it("si el archivo no se pudo adjuntar, lo dice (medio_omitido) en vez de callarlo", () => {
    const j = construirWebhook({ idMensaje: "ID3", de: "50760261919", nombre: "K", tipo: "video", medioOmitido: { motivo: "tamano", mime: "video/mp4", bytes: 20_000_000 }, ts: TS, propio: false });
    expect(j.medio_omitido).toEqual({ motivo: "tamano", mime: "video/mp4", bytes: 20_000_000 });
    expect(j).not.toHaveProperty("medio");
    expect(validarWebhook(j)).toEqual([]);
  });

  it("el único valor de tipo posible está en el contrato", () => {
    expect([...TIPOS_ENTRANTES]).toEqual(["texto", "imagen", "audio", "documento", "video"]);
  });

  it("propio es SIEMPRE un booleano (por defecto false)", () => {
    const j = construirWebhook({ idMensaje: "ID", de: "507", nombre: null, tipo: "texto", texto: "x", ts: TS, propio: undefined as any });
    expect(j.propio).toBe(false);
  });

  describe("validarWebhook detecta lo que rompe el contrato", () => {
    const bueno = () => construirWebhook({ idMensaje: "A", de: "50760261919", nombre: "K", tipo: "texto", texto: "hola", ts: TS, propio: false });

    it.each([
      ["sin id", (j: any) => delete j.id_mensaje, "id_mensaje"],
      ["sin de", (j: any) => delete j.de, "de debe"],
      ["tipo fuera del contrato", (j: any) => (j.tipo = "sticker"), "tipo debe ser"],
      ["propio no booleano", (j: any) => (j.propio = "no"), "propio"],
      ["ts que no es fecha", (j: any) => (j.ts = "ayer"), "ts"],
      ["nombre que no es texto", (j: any) => (j.nombre = 5), "nombre"],
      ["texto vacío en un mensaje de texto", (j: any) => delete j.texto, "necesita texto"],
      ["medio sin mime", (j: any) => (j.medio = { base64: "A", nombre: "x" }), "medio.mime"],
      ["medio sin nombre", (j: any) => (j.medio = { base64: "A", mime: "image/jpeg" }), "medio.nombre"],
      ["medio sin base64 ni url", (j: any) => (j.medio = { mime: "image/jpeg", nombre: "x.jpg" }), "base64 o url_temporal"],
    ])("%s", (_n, rompe, parte) => {
      const j: any = bueno();
      rompe(j);
      expect(validarWebhook(j).join(" | ")).toContain(parte);
    });

    it("acepta url_temporal en lugar de base64 (el contrato admite las dos)", () => {
      const j: any = construirWebhook({ idMensaje: "A", de: "507", nombre: null, tipo: "imagen", ts: TS, propio: false, medio: { base64: "x", mime: "image/jpeg", nombre: "a.jpg" } });
      j.medio = { url_temporal: "https://x/y", mime: "image/jpeg", nombre: "a.jpg" };
      expect(validarWebhook(j)).toEqual([]);
    });

    it("lo que no es un objeto", () => {
      expect(validarWebhook(null)).toEqual(["el cuerpo no es un objeto"]);
      expect(validarWebhook([])).toEqual(["el cuerpo no es un objeto"]);
    });
  });
});

describe("contrato Juan → puente: POST /api/enviar", () => {
  const ok = (cuerpo: unknown, hosts: string[] = []) => validarEnviar(cuerpo, { hostsPermitidos: hosts });

  it("solo texto: { para, chunks }", () => {
    const r = ok({ para: "50760261919", chunks: ["Hola Karen.", "Sí, tenemos camas queen."] });
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(r.plan.para).toMatchObject({ jid: "50760261919@s.whatsapp.net", e164: "50760261919" });
      expect(r.plan.burbujas).toEqual(["Hola Karen.", "Sí, tenemos camas queen."]);
      expect(r.plan.medios).toEqual([]);
      expect(r.plan.total).toBe(2);
    }
  });

  it("con medios: imagen con pie y documento con nombre y mime", () => {
    const r = ok({
      para: "6026-1919",
      chunks: ["Mira esta."],
      medios: [
        { tipo: "imagen", url: "https://dcasapty.com/web/image/1", pie: "Cama Queen HK-BF-022" },
        { tipo: "documento", url: "https://dcasapty.com/cot/12.pdf", nombre: "Cotización.pdf", mime: "application/pdf" },
      ],
    });
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(r.plan.medios).toHaveLength(2);
      expect(r.plan.medios[0]).toMatchObject({ tipo: "imagen", pie: "Cama Queen HK-BF-022", restoPie: [] });
      expect(r.plan.medios[1]).toMatchObject({ tipo: "documento", nombre: "Cotización.pdf", mime: "application/pdf" });
      expect(r.plan.total).toBe(3);
    }
  });

  it("solo medios (sin chunks) también vale", () => {
    expect(ok({ para: "60261919", medios: [{ tipo: "imagen", url: "https://dcasapty.com/a.jpg" }] }).ok).toBe(true);
    expect(ok({ para: "60261919", chunks: [], medios: [{ tipo: "imagen", url: "https://dcasapty.com/a.jpg" }] }).ok).toBe(true);
  });

  it("un pie muy largo no se pierde: lo que sobra sale como texto después", () => {
    const largo = "Esta cama es muy cómoda y firme. ".repeat(60).trim();
    const r = ok({ para: "60261919", medios: [{ tipo: "imagen", url: "https://dcasapty.com/a.jpg", pie: largo }] });
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(r.plan.medios[0].restoPie.length).toBeGreaterThan(0);
      expect(r.plan.total).toBe(1 + r.plan.medios[0].restoPie.length);
    }
  });

  it("divide una burbuja enorme", () => {
    const r = ok({ para: "60261919", chunks: ["palabra ".repeat(600)] });
    expect(r.ok && r.plan.burbujas.length).toBeGreaterThan(1);
  });

  it.each([
    ["no es un objeto", "hola", 400, "objeto"],
    ["falta el destino", { chunks: ["hola"] }, 400, "para"],
    ["destino inválido", { para: "123", chunks: ["hola"] }, 400, "para"],
    ["a un grupo", { para: "120363025246125486@g.us", chunks: ["hola"] }, 400, "grupo"],
    ["a un estado", { para: "status@broadcast", chunks: ["hola"] }, 400, "estado"],
    ["chunks no es lista", { para: "60261919", chunks: "hola" }, 400, "chunks"],
    ["chunk que no es texto", { para: "60261919", chunks: [1] }, 400, "chunks"],
    ["no hay nada que enviar", { para: "60261919", chunks: [] }, 400, "nada que enviar"],
    ["medios no es lista", { para: "60261919", chunks: ["x"], medios: {} }, 400, "medios"],
    ["medio de tipo audio", { para: "60261919", medios: [{ tipo: "audio", url: "https://dcasapty.com/a.ogg" }] }, 400, "medios[0]"],
    ["URL http", { para: "60261919", medios: [{ tipo: "imagen", url: "http://dcasapty.com/a.jpg" }] }, 422, "https"],
    ["URL de metadatos", { para: "60261919", medios: [{ tipo: "imagen", url: "https://169.254.169.254/x" }] }, 422, "IP"],
    ["URL con usuario", { para: "60261919", medios: [{ tipo: "imagen", url: "https://a:b@dcasapty.com/x.jpg" }] }, 422, "usuario"],
  ])("rechaza: %s", (_n, cuerpo, status, parte) => {
    const r = ok(cuerpo);
    expect(r.ok).toBe(false);
    if (!r.ok) {
      expect(r.status).toBe(status);
      expect(r.error).toContain(parte);
    }
  });

  it("con lista de dominios, una URL de otro dominio es 422", () => {
    const r = ok({ para: "60261919", medios: [{ tipo: "imagen", url: "https://evil.example.org/a.jpg" }] }, ["dcasapty.com"]);
    expect(r).toMatchObject({ ok: false, status: 422 });
  });

  it("topes por petición: burbujas, medios y total", () => {
    const once = Array.from({ length: 11 }, (_, i) => `m${i}`);
    expect(ok({ para: "60261919", chunks: once }).ok).toBe(false);
    const medios = Array.from({ length: MAX_MEDIOS + 1 }, () => ({ tipo: "imagen", url: "https://dcasapty.com/a.jpg" }));
    expect(ok({ para: "60261919", medios }).ok).toBe(false);
    // 10 burbujas + 5 medios con pie largo (cada uno deja un resto) supera el total.
    const pie = "frase larga. ".repeat(150);
    const muchos = ok({
      para: "60261919",
      chunks: Array.from({ length: 10 }, (_, i) => `m${i}`),
      medios: Array.from({ length: MAX_MEDIOS }, () => ({ tipo: "imagen", url: "https://dcasapty.com/a.jpg", pie })),
    });
    expect(muchos.ok).toBe(false);
    if (!muchos.ok) expect(muchos.error).toContain(String(MAX_MENSAJES_POR_PETICION));
  });

  it("acepta el jid de persona y el LID como destino", () => {
    expect(ok({ para: "50760261919@s.whatsapp.net", chunks: ["hola"] }).ok).toBe(true);
    const lid = ok({ para: "987654321098765@lid", chunks: ["hola"] });
    expect(lid.ok && lid.plan.para.tipo).toBe("lid");
  });
});

describe("el contrato escrito en docs/JUAN.md sigue diciendo lo que el código cumple", () => {
  const doc = readFileSync(new URL("../../docs/JUAN.md", import.meta.url), "utf8");
  const seccion = doc.slice(doc.indexOf("## Contrato Worker `juan` ↔ puente QR"), doc.indexOf("## Reglas de comportamiento del bot"));

  it("la sección existe", () => {
    expect(seccion.length).toBeGreaterThan(200);
  });

  it("rutas, campos y tipos del contrato", () => {
    for (const parte of [
      "POST /webhooks/whatsapp-qr",
      "id_mensaje",
      "tipo:\"texto|imagen|audio|documento|video\"",
      "url_temporal|base64",
      "propio:false",
      "propio:true",
      "POST /api/enviar",
      "chunks",
      "medios?:[{tipo:\"imagen|documento\"",
      "1 s entre burbujas",
      "GET /api/estado",
      "GET /api/qr",
      "WA_TOKEN",
      "PUENTE",
      "JUAN",
    ]) {
      expect(seccion).toContain(parte);
    }
  });
});
