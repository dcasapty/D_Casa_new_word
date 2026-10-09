/**
 * Regla 5 del contrato: los comprobantes de pago y los documentos de identidad NO llegan al modelo.
 *
 * Reescritura de test/babycaleb/archivos-escalan.test.ts. En Baby Caleb la regla se probaba leyendo el código fuente
 * con expresiones regulares; aquí se prueba el comportamiento: se le entrega al motor un archivo de verdad y se
 * inspecciona TODO lo que el modelo recibió en cada paso.
 *
 * Decisión (docs/JUAN_WORKER.md): en la Fase 1 NINGÚN archivo del cliente llega al modelo. No se puede distinguir un comprobante
 * de una foto del cuarto sin mirarlo, y mirarlo es justo lo que la regla prohíbe.
 */
import { describe, expect, it } from "vitest";
import { enmascararSensibles } from "../../src/dcasa/sensibles";
import { verificarUrlMedio, claveDeConversacion } from "../../src/motor/mediosUrl";
import { crearMundo } from "../helpers/mundo";

const BYTES = new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 1, 2, 3, 4, 5, 6, 7, 8]);
const URL_PUBLICA = "https://dcasa-juan.ejemplo.workers.dev";

function conArchivo(tipo: "imagen" | "documento" | "video" | "audio", mime: string, nombre: string) {
  return { adjuntos: [{ tipo, mime, nombre, bytes: BYTES }] };
}

describe("el archivo del cliente nunca llega al modelo", () => {
  it.each([
    ["imagen", "image/jpeg", "yappy.jpg"],
    ["documento", "application/pdf", "cedula.pdf"],
    ["video", "video/mp4", "video.mp4"],
  ] as const)("un(a) %s no aparece en ningún paso del modelo, ni sus bytes ni su dirección", async (tipo, mime, nombre) => {
    const m = crearMundo({ urlPublica: URL_PUBLICA });
    const g = m.guion([{ texto: "Recibí tu archivo. Una vendedora lo revisa y te confirma por aquí." }]);
    await m.conversar("aquí está mi pago", conArchivo(tipo, mime, nombre));
    for (const llamada of g.doGenerateCalls) {
      const prompt = llamada.prompt as { role: string; content: unknown }[];
      const planos = JSON.stringify(prompt);
      // Ninguna parte de tipo imagen/archivo, ningún byte, ninguna URL ni nombre del archivo.
      const partes = prompt.flatMap((p) => (Array.isArray(p.content) ? (p.content as { type: string }[]) : []));
      expect(partes.every((x) => x.type === "text" || x.type === "tool-call" || x.type === "tool-result")).toBe(true);
      expect(planos).not.toContain(nombre);
      expect(planos).not.toContain("/media/");
      expect(planos).not.toContain("workers.dev");
      expect(planos).not.toContain("data:");
      expect(planos).not.toMatch(/base64|255,216/);
    }
  });

  it("al modelo solo le llega un aviso: no lo ves, ya quedó anotado, nunca confirmes un pago", async () => {
    const m = crearMundo();
    const g = m.guion([{ texto: "Recibí tu archivo. Una vendedora lo revisa." }]);
    await m.conversar("te mando el comprobante", conArchivo("imagen", "image/jpeg", "yappy.jpg"));
    const visto = g.prompts()[0];
    expect(visto).toContain("NO lo ves y no puedes describirlo");
    expect(visto).toContain("ya quedó anotado para una vendedora");
    expect(visto).toContain("NUNCA des por confirmado un pago");
  });

  it("el archivo no se descarta: queda anotado para la vendedora (anotar_conversacion) sin depender del modelo", async () => {
    const m = crearMundo();
    // El modelo no llama NINGUNA herramienta y aun así la nota existe.
    m.guion([{ texto: "Recibí tu archivo." }]);
    await m.conversar("mi cédula", conArchivo("imagen", "image/jpeg", "cedula.jpg"));
    const notas = m.odoo.de("anotar_conversacion");
    expect(notas.length).toBe(1);
    const nota = String(notas[0].args.nota);
    expect(nota).toMatch(/comprobante de pago o un documento de identidad/);
    expect(nota).toMatch(/No se le mostró a la IA/);
    expect(nota).toContain("cedula.jpg");
  });

  it("si el modelo da el pago por recibido, esa frase no sale", async () => {
    const m = crearMundo();
    m.guion([{ texto: "Ya vi tu pago, todo en orden. Coordino la entrega." }, { texto: "Recibí tu archivo. Una vendedora lo revisa y te confirma." }]);
    await m.conversar("te mando el yappy", conArchivo("imagen", "image/jpeg", "yappy.jpg"));
    const texto = m.canal.textos.join("\n");
    expect(texto).not.toMatch(/ya vi tu pago|coordino la entrega/i);
    expect(texto).toContain("Una vendedora lo revisa");
  });

  it("un archivo sin texto también se contesta (no se queda mudo)", async () => {
    const m = crearMundo();
    m.guion([{ texto: "Recibí tu archivo. Una vendedora lo revisa." }]);
    await m.conversar("", conArchivo("imagen", "image/jpeg", "foto.jpg"));
    expect(m.canal.textos.join("\n")).toContain("Una vendedora lo revisa");
  });
});

describe("el archivo SÍ llega a la vendedora, por una URL temporal y firmada", () => {
  it("Odoo recibe el adjunto con una URL de este Worker que vale 2 días", async () => {
    const m = crearMundo({ urlPublica: URL_PUBLICA });
    m.guion([{ texto: "Recibí tu archivo." }]);
    await m.conversar("mi pago", conArchivo("imagen", "image/jpeg", "yappy.jpg"));
    const registro = m.odoo.mensajes.find((x) => x.autor === "cliente")!;
    expect(registro.adjuntos).toHaveLength(1);
    const a = registro.adjuntos![0];
    expect(a).toMatchObject({ tipo: "imagen", mime: "image/jpeg", nombre: "yappy.jpg" });
    expect(a.url).toMatch(new RegExp(`^${URL_PUBLICA}/media/[A-Za-z0-9_-]+/[a-f0-9]{32}\\?exp=\\d+&sig=[a-f0-9]{64}$`));
  });

  it("la URL abre el archivo con la firma correcta y no con otra", async () => {
    const m = crearMundo({ urlPublica: URL_PUBLICA });
    m.guion([{ texto: "Recibí." }]);
    await m.conversar("pago", conArchivo("imagen", "image/jpeg", "yappy.jpg"));
    const url = new URL(m.odoo.mensajes.find((x) => x.autor === "cliente")!.adjuntos![0].url!);
    const [, , clave, id] = url.pathname.split("/");
    expect(clave).toBe(claveDeConversacion("whatsapp_qr", "50760261919"));
    const exp = url.searchParams.get("exp");
    const sig = url.searchParams.get("sig");
    expect(await verificarUrlMedio("secreto-de-prueba", clave, id, exp, sig, m.ahora())).toBe("ok");
    expect(await verificarUrlMedio("otro-secreto", clave, id, exp, sig, m.ahora())).toBe("firma");
    expect(await verificarUrlMedio("secreto-de-prueba", clave, id, exp, "0".repeat(64), m.ahora())).toBe("firma");
    expect(await verificarUrlMedio("secreto-de-prueba", clave + "x", id, exp, sig, m.ahora())).toBe("firma");
    expect(await verificarUrlMedio("secreto-de-prueba", clave, id, exp, sig, Number(exp) + 1)).toBe("vencida");
    const archivo = m.motor.leerMedio(id);
    expect(archivo?.mime).toBe("image/jpeg");
    expect([...archivo!.bytes]).toEqual([...BYTES]);
  });

  it("a los 2 días el archivo ya no está", async () => {
    const m = crearMundo({ urlPublica: URL_PUBLICA });
    m.guion([{ texto: "Recibí." }]);
    await m.conversar("pago", conArchivo("imagen", "image/jpeg", "yappy.jpg"));
    const id = new URL(m.odoo.mensajes[0].adjuntos![0].url!).pathname.split("/")[3];
    expect(m.motor.leerMedio(id)).not.toBeNull();
    await m.pasar(2 * 24 * 3600_000 + 1000);
    expect(m.motor.leerMedio(id)).toBeNull();
  });

  it("un adjunto que ya trae su URL pública (Meta) se pasa tal cual, sin guardar bytes", async () => {
    const m = crearMundo({ urlPublica: URL_PUBLICA });
    m.guion([{ texto: "Recibí." }]);
    await m.conversar("foto", { adjuntos: [{ tipo: "imagen", url: "https://scontent.xx.fbcdn.net/v/foto.jpg" }] });
    expect(m.odoo.mensajes[0].adjuntos![0].url).toBe("https://scontent.xx.fbcdn.net/v/foto.jpg");
  });

  it("sin URL_PUBLICA configurada el adjunto se registra igual, sin dirección (se avisa en /salud)", async () => {
    const m = crearMundo();
    m.guion([{ texto: "Recibí." }]);
    await m.conversar("pago", conArchivo("imagen", "image/jpeg", "yappy.jpg"));
    expect(m.odoo.mensajes[0].adjuntos![0]).toMatchObject({ tipo: "imagen", url: null });
  });
});

describe("notas de voz", () => {
  it("sin transcripción (apagada por defecto): el bot sabe que no puede escucharla y se lo dice al cliente", async () => {
    const m = crearMundo();
    const g = m.guion([{ texto: "No puedo escuchar audios por aquí; ¿me lo escribes?" }]);
    await m.conversar("", conArchivo("audio", "audio/ogg", "nota.ogg"));
    expect(g.prompts()[0]).toContain("nota de voz que no puedes escuchar");
  });

  it("con la transcripción encendida, el modelo recibe el TEXTO (no el audio) y no se anota como archivo sensible", async () => {
    const m = crearMundo({ transcribir: async () => "busco una cama queen" });
    const g = m.guion([{ texto: "Claro, te ayudo con la cama queen." }]);
    await m.conversar("", conArchivo("audio", "audio/ogg", "nota.ogg"));
    expect(g.prompts()[0]).toContain("(nota de voz) busco una cama queen");
    expect(g.prompts()[0]).not.toContain("no puedes escuchar");
    expect(m.odoo.de("anotar_conversacion")).toHaveLength(0);
  });

  it("si la transcripción falla, sigue como si estuviera apagada", async () => {
    const m = crearMundo({ transcribir: async () => { throw new Error("sin Workers AI"); } });
    const g = m.guion([{ texto: "¿Me lo escribes?" }]);
    await m.conversar("", conArchivo("audio", "audio/ogg", "nota.ogg"));
    expect(g.prompts()[0]).toContain("no puedes escuchar");
  });
});

describe("datos sensibles escritos a mano", () => {
  it("tarjeta, CVV y cédula llegan tapados al modelo; Odoo guarda lo que el cliente escribió", async () => {
    const m = crearMundo();
    const g = m.guion([{ texto: "No necesito esos datos. Una vendedora te atiende por aquí." }]);
    await m.conversar("mi tarjeta es 4111 1111 1111 1111 cvv 123 y mi cédula 8-123-4567");
    const visto = g.prompts()[0];
    expect(visto).toContain("[número de tarjeta retirado]");
    expect(visto).toContain("[código de seguridad retirado]");
    expect(visto).toContain("[cédula retirada]");
    expect(visto).not.toMatch(/4111|8-123-4567/);
    expect(m.odoo.mensajes[0].texto).toContain("8-123-4567");
  });

  it("no confunde teléfonos, fechas ni códigos de producto con una cédula o una tarjeta", () => {
    for (const t of ["mi número es 6026-1919", "escríbeme al 507-6026-1919", "lo necesito para el 12-10-2026", "el código es HK-BF-022-N-K-1-W", "llámame al 50760261919", "son 3 cuartos de 14 m2"]) {
      expect(enmascararSensibles(t), t).toBe(t);
    }
  });

  it("reconoce los formatos de cédula panameña", () => {
    for (const c of ["8-123-4567", "PE-12-345", "E-8-12345", "N-12-345", "1-1234-12345"]) {
      expect(enmascararSensibles(`mi cédula ${c}`)).toBe("mi cédula [cédula retirada]");
    }
  });
});
