/**
 * Cuando un envío al cliente falla (la foto de un producto, el PDF de una cotización...), el motivo tiene que poder verse sin abrir los
 * registros de Cloudflare: queda en /salud (y en la pantalla de Conexiones de Odoo) sin datos de nadie, y se apaga solo cuando un
 * envío posterior sale bien.
 */
import { describe, expect, it } from "vitest";
import { informeDeSalud } from "../../src/salud";
import { CONFIG_POR_DEFECTO, normalizarConfig } from "../../src/config";
import { crearMundo } from "../helpers/mundo";

type Nota = { canal?: string; motivo?: string; con_archivos?: boolean; resuelto?: boolean };
const nota = (m: ReturnType<typeof crearMundo>) => m.gastoGlobal.leerSalud<Nota>("envio_fallo")?.valor;

describe("un envío fallido deja su motivo en /salud", () => {
  it("anota canal y motivo, sin claves ni direcciones (las firmadas llevan la firma en la dirección)", async () => {
    const m = crearMundo();
    await m.escribir("hola"); // así la conversación ya conoce su canal, como en producción
    m.canal.fallar = 2; // el envío y su único reintento
    m.canal.motivoDeFallo = "telegram sendPhoto 400: Bad Request https://odoo.example/dcasa/adjunto/7/1790000000/FIRMA-SECRETA/cot.pdf?sig=abc bot 123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";
    await expect(m.motor.enviarVendedora({ texto: "Hola", adjuntos: [{ tipo: "documento", url: "https://odoo.example/dcasa/adjunto/7/x/y/cot.pdf", nombre: "cot.pdf" }] })).rejects.toThrow();
    const n = nota(m)!;
    expect(n.canal).toBe("whatsapp_qr");
    expect(n.con_archivos).toBe(true);
    expect(n.motivo).toContain("Bad Request");
    expect(n.motivo).not.toMatch(/FIRMA-SECRETA|sig=abc|AAAAAAAA|https?:/);
    expect(n.motivo).toContain("[enlace]");
  });

  it("aparece como un problema legible en el informe de salud", async () => {
    const m = crearMundo();
    await m.escribir("hola");
    m.canal.fallar = 2;
    await expect(m.motor.enviarVendedora({ texto: "Hola" })).rejects.toThrow();
    const guardada = m.gastoGlobal.leerSalud("envio_fallo")!;
    const informe = await informeDeSalud({
      env: { VERSION: "t", ENTORNO: "staging" } as never,
      adaptadores: [],
      config: async () => normalizarConfig({ ...CONFIG_POR_DEFECTO }),
      gastoMes: async () => 0,
      leerSalud: async (clave) => (clave === "envio_fallo" ? { json: JSON.stringify(guardada.valor), ts: guardada.ts } : null),
      ahora: () => m.ahora(),
      consultarConexiones: false,
    });
    expect(informe.problemas.join(" | ")).toMatch(/no se pudo enviar un mensaje por whatsapp_qr: el canal falló/);
  });

  it("cuando un envío posterior sale bien, la nota queda como resuelta", async () => {
    const m = crearMundo();
    await m.escribir("hola");
    m.canal.fallar = 2;
    await expect(m.motor.enviarVendedora({ texto: "Uno" })).rejects.toThrow();
    expect(nota(m)?.resuelto).toBeUndefined();
    await m.motor.enviarVendedora({ texto: "Dos" });
    expect(nota(m)?.resuelto).toBe(true);
  });

  it("si nunca falló nada no se anota nada", async () => {
    const m = crearMundo();
    await m.escribir("hola");
    await m.motor.enviarVendedora({ texto: "Hola" });
    expect(m.gastoGlobal.leerSalud("envio_fallo")).toBeNull();
  });
});
