/**
 * Juan y las novedades por correo (Camila etapa 1b, decisiones de la dueña del 2026-11-06: se activan solas al agregar
 * el correo y se quitan cuando el cliente dice que no). Odoo manda `permiso_correo` en /mensaje y /estado: «activo» (le
 * llegan) o «sin_correo» (su ficha no tiene correo). Las herramientas viven en Odoo: `guardar_correo` (el correo que
 * escribió el cliente; Odoo activa las novedades) y `no_quiere_novedades` (siempre se honra un no). Juan nunca las
 * activa ni pregunta si las quiere.
 */
import { describe, expect, it } from "vitest";
import { CONFIG_POR_DEFECTO } from "../../src/config";
import { contextoDelChat } from "../../src/dcasa/prompt";
import { AHORA_INICIAL, crearMundo } from "../helpers/mundo";

const base = { canal: "whatsapp_qr" as const, ahora: AHORA_INICIAL, presentacionEnviada: false };
const prompt = (m: ReturnType<typeof crearMundo>) => JSON.stringify(m.modelo.doGenerateCalls.at(-1)?.prompt ?? "");

describe("permiso_correo", () => {
  it("con «activo», si el cliente dice que no (aunque sea con dudas) Juan lo honra con la herramienta", () => {
    const c = contextoDelChat(CONFIG_POR_DEFECTO, { ...base, permisoDeCorreo: "activo" });
    expect(c).toMatch(/recibe las novedades de D'CASA en su correo/);
    expect(c).toMatch(/no_quiere_novedades/);
    expect(c).toMatch(/claro o con dudas/);
    expect(c).toMatch(/siempre se respeta un no/i);
    expect(c).toMatch(/nunca las activas ni le preguntas si las quiere/i);
    expect(c).not.toMatch(/guardar_correo/);
  });

  it("con «sin_correo», si da su correo lo guarda y le avisa que le llegarán (y que puede decir que no)", () => {
    const c = contextoDelChat(CONFIG_POR_DEFECTO, { ...base, permisoDeCorreo: "sin_correo" });
    expect(c).toMatch(/guardar_correo/);
    expect(c).toMatch(/tal como lo escribió/);
    expect(c).toMatch(/puede decir que no cuando quiera/);
    expect(c).toMatch(/no se lo pidas solo para eso/i);
    expect(c).toMatch(/no_quiere_novedades/);
  });

  it("con «sin_permiso» (tiene correo pero no le llegan), igual honra un no y no se las ofrece", () => {
    const c = contextoDelChat(CONFIG_POR_DEFECTO, { ...base, permisoDeCorreo: "sin_permiso" });
    expect(c).toMatch(/no_quiere_novedades/);
    expect(c).toMatch(/no se las ofrezcas/i);
    expect(c).toMatch(/siempre se respeta un no/i);
    expect(c).not.toMatch(/guardar_correo/);
  });

  it("«sin_permiso» llega de Odoo y queda en el prompt del turno", async () => {
    const m = crearMundo();
    m.guion([{ texto: "¡Claro!" }]);
    m.odoo.estadoActual = { ...m.odoo.estadoActual, permiso_correo: "sin_permiso" };
    await m.conversar("Hola, ¿tienen camas queen?");
    expect(prompt(m)).toContain("no_quiere_novedades");
  });

  it("sin el dato de Odoo (o con uno que no conoce), nada de novedades", () => {
    const c = contextoDelChat(CONFIG_POR_DEFECTO, base);
    expect(c).not.toMatch(/no_quiere_novedades|guardar_correo/);
    for (const viejo of ["puedes_preguntar", "esperando_respuesta", "cualquier otra cosa"]) {
      expect(contextoDelChat(CONFIG_POR_DEFECTO, { ...base, permisoDeCorreo: viejo })).not.toMatch(/no_quiere_novedades/);
    }
  });

  it("llega en la respuesta de Odoo a /mensaje y, cuando Odoo ya no lo manda, se va del prompt", async () => {
    const m = crearMundo();
    m.guion([{ texto: "Listo, te mando la cotización." }, { texto: "¡Perfecto!" }]);
    m.odoo.estadoActual = { ...m.odoo.estadoActual, permiso_correo: "activo" };
    await m.conversar("Hola, ¿me mandas la cotización?");
    expect(prompt(m)).toContain("no_quiere_novedades");
    m.odoo.estadoActual = { ...m.odoo.estadoActual, permiso_correo: undefined };
    await m.conversar("gracias");
    expect(prompt(m)).not.toContain("no_quiere_novedades");
  });

  it("las herramientas de Odoo llegan al modelo como cualquier otra (las publica Odoo con Camila instalada)", async () => {
    const m = crearMundo();
    m.odoo.defs = [
      ...m.odoo.defs,
      {
        nombre: "guardar_correo",
        descripcion: "Guarda en su ficha el correo que el cliente te escribió en el chat.",
        parametros: { type: "object", properties: { correo: { type: "string" } }, required: ["correo"] },
      },
      {
        nombre: "no_quiere_novedades",
        descripcion: "El cliente no quiere recibir novedades por correo.",
        parametros: { type: "object", properties: {} },
      },
    ];
    m.guion([{ texto: "Claro." }]);
    await m.conversar("hola");
    const herramientas = JSON.stringify(m.modelo.doGenerateCalls.at(-1)?.tools ?? []);
    expect(herramientas).toContain("guardar_correo");
    expect(herramientas).toContain("no_quiere_novedades");
  });
});
