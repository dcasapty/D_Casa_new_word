/**
 * Juan pregunta por WhatsApp si el cliente quiere las novedades por correo (Camila etapa 1b, decisión de la dueña,
 * 2026-11-06). Odoo manda `permiso_correo` en /mensaje y /estado: «puedes_preguntar» (se puede, una sola vez y en un buen
 * momento) o «esperando_respuesta» (ya preguntó). La herramienta `permiso_correo` vive en Odoo, con sus candados: solo
 * anota si el último mensaje del cliente, después de ESA pregunta, dice que sí. Si Odoo no manda el dato, Juan no
 * pregunta.
 */
import { describe, expect, it } from "vitest";
import { CONFIG_POR_DEFECTO } from "../../src/config";
import { contextoDelChat } from "../../src/dcasa/prompt";
import { AHORA_INICIAL, crearMundo } from "../helpers/mundo";

const base = { canal: "whatsapp_qr" as const, ahora: AHORA_INICIAL, presentacionEnviada: false };
const prompt = (m: ReturnType<typeof crearMundo>) => JSON.stringify(m.modelo.doGenerateCalls.at(-1)?.prompt ?? "");

describe("permiso_correo", () => {
  it("con «puedes_preguntar», Juan sabe cuándo y cómo preguntar (una vez, y la herramienta antes)", () => {
    const c = contextoDelChat(CONFIG_POR_DEFECTO, { ...base, permisoDeCorreo: "puedes_preguntar" });
    expect(c).toMatch(/novedades por correo/i);
    expect(c).toMatch(/permiso_correo/);
    expect(c).toMatch(/accion="preguntar"/);
    expect(c).toMatch(/una sola vez/i);
    expect(c).toMatch(/cuando te dé su correo|después de mandarle una cotización/);
    expect(c).toMatch(/nunca lo anotes sin que (lo diga|diga que sí)/i);
  });

  it("con «esperando_respuesta», si dice que sí lo anota con la herramienta (y si no, no insiste)", () => {
    const c = contextoDelChat(CONFIG_POR_DEFECTO, { ...base, permisoDeCorreo: "esperando_respuesta" });
    expect(c).toMatch(/accion="anotar"/);
    expect(c).toMatch(/accion="no"/);
    expect(c).toMatch(/no vuelvas a preguntar/i);
  });

  it("sin el dato de Odoo, Juan no pregunta por las novedades", () => {
    const c = contextoDelChat(CONFIG_POR_DEFECTO, base);
    expect(c).not.toMatch(/permiso_correo/);
    expect(contextoDelChat(CONFIG_POR_DEFECTO, { ...base, permisoDeCorreo: "cualquier otra cosa" })).not.toMatch(/permiso_correo/);
  });

  it("llega en la respuesta de Odoo a /mensaje y, cuando Odoo ya no lo manda, el bot no pregunta", async () => {
    const m = crearMundo();
    m.guion([{ texto: "Listo, te mando la cotización." }, { texto: "¡Perfecto!" }]);
    m.odoo.estadoActual = { ...m.odoo.estadoActual, permiso_correo: "puedes_preguntar" };
    await m.conversar("Hola, mi correo es carla.zzcm@example.com, ¿me mandas la cotización?");
    expect(prompt(m)).toContain("permiso_correo");
    m.odoo.estadoActual = { ...m.odoo.estadoActual, permiso_correo: undefined };
    await m.conversar("gracias");
    expect(prompt(m)).not.toContain("accion=\\\"preguntar\\\"");
  });

  it("la herramienta de Odoo llega al modelo como cualquier otra (la publica Odoo con Camila instalada)", async () => {
    const m = crearMundo();
    m.odoo.defs = [
      ...m.odoo.defs,
      {
        nombre: "permiso_correo",
        descripcion: "El permiso del cliente para recibir las novedades por correo.",
        parametros: { type: "object", properties: { accion: { type: "string", enum: ["preguntar", "anotar", "no"] } }, required: ["accion"] },
      },
    ];
    m.guion([{ texto: "Claro." }]);
    await m.conversar("hola");
    expect(JSON.stringify(m.modelo.doGenerateCalls.at(-1)?.tools ?? [])).toContain("permiso_correo");
  });
});
