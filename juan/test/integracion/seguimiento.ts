// Sección 3: el seguimiento. Odoo decide quién (solo con intención de compra) y cuándo (5 h, luego 5 días, máximo 2); el Worker redacta y envía;
// el Worker le confirma a Odoo con POST /seguimiento/hecho. Odoo → Worker: POST /odoo/seguimiento.

import { beforeAll, describe, expect, it } from "vitest";
import { OdooRpc, celularNuevo, esperarHasta } from "./ayuda";
import type { Escena } from "./escena";

/** `YYYY-MM-DD HH:MM:SS` en UTC: el formato de fecha y hora de Odoo. */
const aOdoo = (ms: number) => new Date(ms).toISOString().replace("T", " ").slice(0, 19);
const deOdoo = (v: string | false | null | undefined) => (v ? Date.parse(`${v.replace(" ", "T")}Z`) : null);
const HORA = 3600_000;

export function seccionSeguimiento(e: Escena) {
  describe("3. Seguimiento: Odoo pide, el Worker redacta y envía, Odoo cuenta", () => {
    let admin: OdooRpc;
    beforeAll(() => {
      admin = e.admin;
    });
    const celular = celularNuevo();
    let convId: number;

    const esperarSeguimientos = (n: number) =>
      esperarHasta(`Odoo cuente ${n} seguimiento(s) enviado(s)`, async () => {
        const c = (await e.conversacionDe(celular))!;
        return c.seguimientos_enviados === n && !c.seguimiento_pedido_en ? c : false;
      });

    it("después de que el bot contesta, Odoo programa el 1.º a las 5 h (solo en horario laboral)", async () => {
      // Luis muestra interés concreto: el asistente registra la oportunidad (eso habilita el seguimiento).
      e.w.ia.guionar([
        { llamadas: [{ nombre: "crear_oportunidad", args: { resumen: "Luis busca un colchón.", interes: "ando buscando un colchón" } }] },
        { texto: "Claro, Luis. ¿Qué medida de colchón buscas?" },
      ]);
      await e.w.cliente(celular, "Hola, ando buscando un colchón", { nombre: "Luis" });
      await e.w.quieta(celular);
      const c = (await e.conversacionDe(celular))!;
      convId = c.id;
      expect(c.estado).toBe("bot");
      expect(c.seguimientos_enviados).toBe(0);
      const espera = deOdoo(c.seguimiento_proximo)! - Date.now();
      // 5 h desde la última actividad; si cayera fuera del horario (la prueba abre casi todo el día), esperaría al siguiente.
      expect(espera).toBeGreaterThan(4.9 * HORA);
      expect(espera).toBeLessThan(24 * HORA);
    });

    it("1.º vencido → el cron de Odoo lo pide a /odoo/seguimiento → el Worker redacta, envía y confirma con seguimiento/hecho", async () => {
      await admin.escribir("dcasa.conversacion", [convId], { seguimiento_proximo: aOdoo(Date.now() - 60_000) });
      e.w.ia.guionar([{ texto: "Hola Luis, ¿pudiste ver el colchón? Si quieres, seguimos cuando tú puedas." }]);
      const envios = e.w.puente.envios.length;
      const pedidos = e.w.entradas.filter((x) => x.ruta === "/odoo/seguimiento").length;

      await admin.dispararCron("pedir los seguimientos");

      expect(e.w.entradas.filter((x) => x.ruta === "/odoo/seguimiento")).toHaveLength(pedidos + 1);
      expect(e.w.entradas.filter((x) => x.ruta === "/odoo/seguimiento").at(-1)!.estado).toBe(200);
      expect(e.w.puente.envios.length).toBe(envios + 1);
      expect(e.w.puente.envios.at(-1)!.para).toBe(celular);
      expect(e.w.puente.envios.at(-1)!.chunks.join(" ")).toContain("Hola Luis, ¿pudiste ver el colchón?");
      // El seguimiento se redacta SIN herramientas (no puede traer precios ni existencias) y con el interés que Odoo mandó.
      const peticion = e.w.ia.peticiones.at(-1)!.cuerpo;
      expect(peticion.tools ?? []).toEqual([]);
      expect(JSON.stringify(peticion.system)).toContain("ando buscando un colchón");

      await e.w.quieta(celular); // el texto que salió se registra en Odoo en segundo plano (cola del Worker)
      const c = await esperarSeguimientos(1);
      expect(c.ultimo_seguimiento_en).toBeTruthy();
      expect(c.estado).toBe("bot");
      const avisos = (await e.mensajesDe(celular)).filter((m) => m.tipo === "aviso").map((m) => m.texto as string);
      expect(avisos.join("\n")).toContain("Seguimiento n.º 1 enviado");
      // El texto que salió quedó en Odoo como mensaje del asistente.
      expect((await e.textosDe(celular, "bot")).join("\n")).toContain("¿pudiste ver el colchón?");
      // Y Odoo cuenta el 2.º a 5 DÍAS desde el 1.º (no desde el último mensaje del cliente), en horario laboral.
      const proximo = deOdoo(c.seguimiento_proximo)! - deOdoo(c.ultimo_seguimiento_en)!;
      expect(proximo).toBeGreaterThanOrEqual(5 * 24 * HORA - 1000);
      expect(proximo).toBeLessThan(6 * 24 * HORA);
    });

    it("2.º vencido → mismo camino; después de 2 ya no hay más (máximo 2)", async () => {
      await admin.escribir("dcasa.conversacion", [convId], { seguimiento_proximo: aOdoo(Date.now() - 60_000) });
      e.w.ia.guionar([{ texto: "Luis, no te escribiré más por este tema. Si quieres retomarlo, aquí estamos." }]);
      const envios = e.w.puente.envios.length;
      await admin.dispararCron("pedir los seguimientos");
      expect(e.w.puente.envios.length).toBe(envios + 1);
      await e.w.quieta(celular);
      const c = await esperarSeguimientos(2);
      expect(c.seguimiento_proximo).toBeFalsy();
      // Aunque el cron vuelva a correr, no hay un 3.º.
      await admin.dispararCron("pedir los seguimientos");
      expect(e.w.puente.envios.length).toBe(envios + 1);
    });

    it("si el cliente vuelve a escribir, el conteo empieza de nuevo", async () => {
      e.w.ia.guionar([{ texto: "¡Qué bueno que volviste, Luis! Cuéntame." }]);
      await e.w.cliente(celular, "Hola de nuevo, sí me interesa el colchón");
      await e.w.quieta(celular);
      const c = (await e.conversacionDe(celular))!;
      expect(c.seguimientos_enviados).toBe(0);
      expect(deOdoo(c.seguimiento_proximo)! - Date.now()).toBeGreaterThan(4.9 * HORA);
    });

    it("quien solo preguntó (sin intención de compra: no hay oportunidad) no recibe seguimiento", async () => {
      const curioso = celularNuevo();
      e.w.ia.guionar([{ texto: "Abrimos todos los días; una vendedora te atiende en ese horario." }]);
      await e.w.cliente(curioso, "¿A qué hora abren?");
      await e.w.quieta(curioso);
      const c = (await e.conversacionDe(curioso))!;
      expect(c.oportunidad_id).toBeFalsy();
      expect(c.seguimiento_proximo).toBeFalsy();
      await admin.escribir("dcasa.conversacion", [c.id], { seguimiento_proximo: aOdoo(Date.now() - 60_000) });
      const pedidos = e.w.entradas.filter((x) => x.ruta === "/odoo/seguimiento").length;
      await admin.dispararCron("pedir los seguimientos");
      expect(e.w.entradas.filter((x) => x.ruta === "/odoo/seguimiento")).toHaveLength(pedidos); // Odoo no lo pidió
    });

    it("quien pide que no lo contacten no recibe seguimiento (Odoo no lo pide)", async () => {
      const otro = celularNuevo();
      e.w.ia.guionar([{ texto: "Entendido, no te escribiremos más." }]);
      await e.w.cliente(otro, "No me vuelvan a escribir por favor");
      await e.w.quieta(otro);
      const c = (await e.conversacionDe(otro))!;
      expect(c.seguimiento_proximo).toBeFalsy();
      const [ficha] = await admin.leer("res.partner", [c.partner_id[0]], ["dcasa_no_contactar"]);
      expect(ficha.dcasa_no_contactar).toBe(true);
      await admin.escribir("dcasa.conversacion", [c.id], { seguimiento_proximo: aOdoo(Date.now() - 60_000) });
      const pedidos = e.w.entradas.filter((x) => x.ruta === "/odoo/seguimiento").length;
      await admin.dispararCron("pedir los seguimientos");
      expect(e.w.entradas.filter((x) => x.ruta === "/odoo/seguimiento")).toHaveLength(pedidos); // Odoo no lo pidió
    });

    it("si la conversación la tiene una vendedora, Odoo no pide seguimiento", async () => {
      const c = (await e.conversacionDe(celular))!;
      await e.ventas.llamar("dcasa.conversacion", "tomar", [c.id, 30]);
      await admin.escribir("dcasa.conversacion", [c.id], { seguimiento_proximo: aOdoo(Date.now() - 60_000) });
      const pedidos = e.w.entradas.filter((x) => x.ruta === "/odoo/seguimiento").length;
      await admin.dispararCron("pedir los seguimientos");
      expect(e.w.entradas.filter((x) => x.ruta === "/odoo/seguimiento")).toHaveLength(pedidos);
      await e.ventas.llamar("dcasa.conversacion", "devolver", [c.id]);
    });

    it("el Worker se defiende solo: no envía un seguimiento si el cliente ya volvió a escribir y se lo dice a Odoo (descartado)", async () => {
      const otro = celularNuevo();
      e.w.ia.guionar([{ texto: "Hola, ¿qué buscas?" }]);
      await e.w.cliente(otro, "Hola, quiero una cama");
      await e.w.quieta(otro);
      const c = (await e.conversacionDe(otro))!;
      const envios = e.w.puente.envios.length;
      // Odoo pidió el seguimiento con un «último mensaje» viejo (el cliente escribió después): el Worker lo descarta.
      const r = await e.w.odooAlWorker("POST", "/odoo/seguimiento", {
        conversacion_id: c.id, canal: "whatsapp_qr", id_externo: otro, numero: 1,
        contexto: { interes: "cama", ultimo_mensaje_ts: new Date(Date.now() - 10 * HORA).toISOString() },
      });
      expect(r.estado).toBe(200);
      expect(r.json).toMatchObject({ ok: true, resultado: "descartado" });
      expect(e.w.puente.envios.length).toBe(envios);
      const despues = await esperarHasta("Odoo recibe el descartado", async () => {
        const x = (await e.conversacionDe(otro))!;
        return x.seguimientos_enviados >= 1 ? x : false;
      });
      expect(despues.seguimiento_proximo).toBeFalsy();
    });
  });
}
