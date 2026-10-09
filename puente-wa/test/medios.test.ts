import { describe, expect, it } from "vitest";
import {
  LIMITE_ENTRANTE,
  LIMITE_SALIENTE,
  MIMES_SALIENTES,
  contenidoCoincide,
  extensionDe,
  mimeLimpio,
  nombreSeguro,
  sniffMime,
  validarMedioSaliente,
} from "../contenedor/lib/medios.mjs";

const bytes = (...b: number[]) => Uint8Array.from(b);
const JPG = bytes(0xff, 0xd8, 0xff, 0xe0, 0, 0x10, 0x4a, 0x46);
const PNG = bytes(0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 0);
const WEBP = bytes(0x52, 0x49, 0x46, 0x46, 1, 2, 3, 4, 0x57, 0x45, 0x42, 0x50, 0x56);
const PDF = new TextEncoder().encode("%PDF-1.7\n1 0 obj");
const ZIP = bytes(0x50, 0x4b, 0x03, 0x04, 0x14, 0, 0, 0);
const OLE = bytes(0xd0, 0xcf, 0x11, 0xe0, 0xa1, 0xb1, 0x1a, 0xe1);
const HTML = new TextEncoder().encode("<!doctype html><html><body>hola</body></html>");
const EXE = bytes(0x4d, 0x5a, 0x90, 0, 3, 0, 0, 0);
const TXT = new TextEncoder().encode("a,b,c\n1,2,3\n");

describe("sniffMime: lo que el archivo ES, no lo que dice ser", () => {
  it("reconoce las firmas", () => {
    expect(sniffMime(JPG)).toBe("image/jpeg");
    expect(sniffMime(PNG)).toBe("image/png");
    expect(sniffMime(WEBP)).toBe("image/webp");
    expect(sniffMime(PDF)).toBe("application/pdf");
    expect(sniffMime(ZIP)).toBe("ooxml");
    expect(sniffMime(OLE)).toBe("ole");
    expect(sniffMime(HTML)).toBe(null);
    expect(sniffMime(EXE)).toBe(null);
    expect(sniffMime(bytes())).toBe(null);
  });
});

describe("contenidoCoincide", () => {
  it("el tipo declarado tiene que ser el real", () => {
    expect(contenidoCoincide("image/jpeg", JPG)).toBe(true);
    expect(contenidoCoincide("image/png", JPG)).toBe(false);
    expect(contenidoCoincide("image/jpeg", HTML)).toBe(false);
    expect(contenidoCoincide("image/jpeg", EXE)).toBe(false);
    expect(contenidoCoincide("application/pdf", PDF)).toBe(true);
    expect(contenidoCoincide("application/pdf", JPG)).toBe(false);
    expect(contenidoCoincide("application/vnd.openxmlformats-officedocument.wordprocessingml.document", ZIP)).toBe(true);
    expect(contenidoCoincide("application/vnd.openxmlformats-officedocument.wordprocessingml.document", PDF)).toBe(false);
    expect(contenidoCoincide("application/msword", OLE)).toBe(true);
    expect(contenidoCoincide("application/msword", ZIP)).toBe(false);
  });

  it("texto plano: sin bytes nulos y sin firma de otro formato", () => {
    expect(contenidoCoincide("text/csv", TXT)).toBe(true);
    expect(contenidoCoincide("text/plain", TXT)).toBe(true);
    expect(contenidoCoincide("text/plain", EXE)).toBe(false); // trae bytes nulos
    expect(contenidoCoincide("text/plain", JPG)).toBe(false); // es una imagen
  });

  it("un tipo desconocido nunca coincide", () => {
    expect(contenidoCoincide("application/x-msdownload", EXE)).toBe(false);
    expect(contenidoCoincide("", JPG)).toBe(false);
  });

  it("ignora mayúsculas y parámetros del tipo", () => {
    expect(contenidoCoincide("IMAGE/JPEG; charset=binary", JPG)).toBe(true);
  });
});

describe("nombreSeguro", () => {
  it("quita rutas y caracteres peligrosos", () => {
    expect(nombreSeguro("../../etc/passwd", "text/plain")).toBe("passwd.txt");
    expect(nombreSeguro("C:\\Users\\x\\cotización.pdf", "application/pdf")).toBe("cotización.pdf");
    expect(nombreSeguro('a<b>c:"d|e?f*.pdf', "application/pdf")).toBe("abcdef.pdf");
    expect(nombreSeguro("hola\u0000\u001f.pdf", "application/pdf")).toBe("hola.pdf");
    expect(nombreSeguro(".htaccess", "text/plain")).toBe("htaccess.txt");
  });

  it("pone la extensión que corresponde al tipo", () => {
    expect(nombreSeguro("catalogo", "application/pdf")).toBe("catalogo.pdf");
    expect(nombreSeguro("catalogo.final", "application/pdf")).toBe("catalogo.final.pdf");
    expect(nombreSeguro("foto.PNG", "image/png")).toBe("foto.PNG");
    expect(nombreSeguro("foto.exe", "image/jpeg")).toBe("foto.exe.jpg"); // la extensión real manda al final
  });

  it("usa el nombre por defecto si no viene uno", () => {
    expect(nombreSeguro(undefined, "image/webp", "imagen")).toBe("imagen.webp");
    expect(nombreSeguro("   ", "application/pdf", "documento")).toBe("documento.pdf");
    expect(nombreSeguro("", "video/quicktime", "video")).toBe("video");
  });

  it("recorta lo larguísimo conservando la extensión", () => {
    const n = nombreSeguro("a".repeat(300) + ".pdf", "application/pdf");
    expect(n.length).toBeLessThanOrEqual(100);
    expect(n.endsWith(".pdf")).toBe(true);
  });
});

describe("tipos y límites", () => {
  it("mimeLimpio / extensionDe", () => {
    expect(mimeLimpio("Audio/OGG; codecs=opus")).toBe("audio/ogg");
    expect(mimeLimpio(null)).toBe("");
    expect(extensionDe("image/jpeg")).toBe("jpg");
    expect(extensionDe("audio/ogg; codecs=opus")).toBe("ogg");
    expect(extensionDe("application/x-raro")).toBe("");
  });

  it("los límites caben en un contenedor de 256 MiB", () => {
    const MB = 1024 * 1024;
    for (const v of Object.values(LIMITE_ENTRANTE)) expect(v).toBeLessThanOrEqual(12 * MB);
    for (const v of Object.values(LIMITE_SALIENTE)) expect(v).toBeLessThanOrEqual(12 * MB);
  });

  it("no se envían ejecutables, HTML ni scripts", () => {
    const todos = [...MIMES_SALIENTES.imagen, ...MIMES_SALIENTES.documento];
    for (const prohibido of ["text/html", "application/x-msdownload", "application/javascript", "image/svg+xml", "application/zip"]) {
      expect(todos).not.toContain(prohibido);
    }
  });
});

describe("validarMedioSaliente", () => {
  it("acepta una imagen y un documento", () => {
    expect(validarMedioSaliente({ tipo: "imagen", url: "https://x.com/a.jpg", pie: "Cama" })).toMatchObject({ ok: true });
    expect(
      validarMedioSaliente({ tipo: "documento", url: "https://x.com/c.pdf", nombre: "Cotización.pdf", mime: "application/pdf" }),
    ).toMatchObject({ ok: true });
  });

  it.each([
    [null, "objeto"],
    ["texto", "objeto"],
    [{ tipo: "audio", url: "https://x.com/a.ogg" }, "imagen"],
    [{ tipo: "video", url: "https://x.com/a.mp4" }, "imagen"],
    [{ tipo: "imagen" }, "url"],
    [{ tipo: "imagen", url: "https://x.com/a.jpg", mime: "image/gif" }, "no se puede enviar"],
    [{ tipo: "imagen", url: "https://x.com/a.jpg", mime: "application/pdf" }, "no se puede enviar"],
    [{ tipo: "documento", url: "https://x.com/a.exe", mime: "application/x-msdownload" }, "no se puede enviar"],
    [{ tipo: "imagen", url: "https://x.com/a.jpg", nombre: 5 }, "nombre"],
    [{ tipo: "imagen", url: "https://x.com/a.jpg", pie: 5 }, "pie"],
  ])("rechaza %j", (medio, parte) => {
    const r = validarMedioSaliente(medio);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.motivo).toContain(parte);
  });
});
