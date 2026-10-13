// Sección 5: idempotencia, Odoo dormido, códigos de error y reintentos (en los dos sentidos). La 429 va AL FINAL de todo
// porque frena a esta máquina durante un minuto (los intentos fallidos con un token malo se cuentan por IP).

import { beforeAll, describe, expect, it } from "vitest";
import { OdooCliente, OdooError } from "../../src/odoo/cliente";
import { OdooRpc, ODOO_URL_SIN_TOKEN, TOKEN_ODOO, apiOdoo, celularNuevo, enlaceDcasa, type EstadoDelEnlace } from "./ayuda";
import type { Escena } from "./escena";

const nuevoEstado = (): EstadoDelEnlace => ({ peticiones: [], dormido: 0 });

export function seccionErrores(e: Escena) {
  describe("5. Idempotencia, Odoo dormido y códigos de error", () => {
    let admin: OdooRpc;
    beforeAll(() => {
      admin = e.admin;
    });

    it("idempotencia: el mismo id_mensaje dos veces por el webhook queda UNA vez en Odoo (y el bot contesta una sola vez)", async () => {
      const celular = celularNuevo();
      e.w.ia.guionar([{ texto: "Hola, ¿qué buscas?" }, { texto: "(no debe pedirse)" }]);
      const cuerpo = { id_mensaje: `WAMID.repetido.${celular}` };
      await e.w.cliente(celular, "Hola", cuerpo);
      await e.w.cliente(celular, "Hola", cuerpo);
      await e.w.quieta(celular);
      expect(await e.textosDe(celular, "cliente")).toEqual(["Hola"]);
      expect(e.w.ia.peticiones.length).toBeGreaterThan(0);
      expect(e.w.ia.pendientes).toBe(1); // una sola respuesta de la IA
    });

    it("una vendedora toma la conversación MIENTRAS el bot piensa (y Odoo avisa al Worker): el bot no envía lo que traía", async () => {
      const celular = celularNuevo();
      e.w.ia.guionar([
        {
          texto: "(esta respuesta no debe salir)",
          mientrasPiensa: async () => {
            const c = await e.conversacionDe(celular);
            await e.ventas.llamar("dcasa.conversacion", "tomar", [c!.id, 30]);
          },
        },
      ]);
      await e.w.cliente(celular, "Hola, quiero una cama");
      await e.w.quieta(celular);
      expect(e.w.puente.envios.filter((x) => x.para === celular)).toHaveLength(0);
      expect(await e.textosDe(celular, "bot")).toEqual([]);
      expect(await e.textosDe(celular, "cliente")).toEqual(["Hola, quiero una cama"]);
      expect((await e.conversacionDe(celular))!.estado).toBe("humano");
    });

    it("el Worker no se entera de que tomaron la conversación (no llegó el aviso): igual lo ve JUSTO antes de enviar, con GET /estado", async () => {
      const celular = celularNuevo();
      e.w.ia.guionar([
        {
          texto: "(esta respuesta tampoco debe salir)",
          mientrasPiensa: async () => {
            const c = await e.conversacionDe(celular);
            // Se cambia el estado directo en la base de Odoo: ningún POST /odoo/estado sale hacia el Worker.
            await admin.escribir("dcasa.conversacion", [c!.id], { estado: "humano", pausada_hasta: false });
          },
        },
      ]);
      const avisos = e.w.entradas.filter((x) => x.ruta === "/odoo/estado").length;
      await e.w.cliente(celular, "Buenas, ¿tienen colchones?");
      await e.w.quieta(celular);
      expect(e.w.entradas.filter((x) => x.ruta === "/odoo/estado")).toHaveLength(avisos);
      expect(e.w.puente.envios.filter((x) => x.para === celular)).toHaveLength(0);
      const consultas = e.w.enlace.peticiones.filter((p) => p.metodo === "GET" && p.ruta.includes("/estado") && p.ruta.includes(celular));
      expect(consultas.length).toBeGreaterThan(0);
      expect(await e.textosDe(celular, "bot")).toEqual([]);
    });

    it("Odoo dormido (503 «arrancando» con Retry-After): el Worker reintenta y el mensaje queda una sola vez", async () => {
      const celular = celularNuevo();
      // Lo que contesta el borde mientras el contenedor despierta.
      e.w.enlace.dormido = 1;
      const crudo = await enlaceDcasa(e.w.enlace).fetch("https://dcasa/dcasa/juan/v1/config", { headers: { authorization: `Bearer ${TOKEN_ODOO}` } });
      expect(crudo.status).toBe(503);
      expect(crudo.headers.get("retry-after")).toBe("15");
      expect(await crudo.json()).toMatchObject({ ok: false, error: "Odoo está arrancando.", reintentar_en: 15 });

      e.w.enlace.dormido = 1;
      e.w.ia.guionar([{ texto: "Hola, ¿qué buscas?" }]);
      await e.w.cliente(celular, "Hola, buenas");
      await e.w.quieta(celular);
      const registros = e.w.enlace.peticiones.filter((p) => p.ruta.endsWith("/mensaje") && p.cuerpo?.id_externo === celular && p.cuerpo?.autor === "cliente");
      expect(registros.map((r) => r.estado)).toEqual([503, 200]); // un intento fallido, el reintento entró
      expect(await e.textosDe(celular, "cliente")).toEqual(["Hola, buenas"]);
    });

    it("401: token malo o ausente → JSON {ok:false,error}; el cliente del Worker no reintenta un 401", async () => {
      for (const token of ["x".repeat(40), "", null]) {
        const r = await apiOdoo("GET", "/config", { token });
        expect(r.estado, String(token ? "token malo" : "sin token")).toBe(401);
        expect(r.json).toMatchObject({ ok: false });
        expect(typeof r.json.error).toBe("string");
        expect(r.cabeceras.get("www-authenticate")).toMatch(/Bearer/);
      }
      const intentos = nuevoEstado();
      const malo = new OdooCliente(enlaceDcasa(intentos), "x".repeat(40), { dormir: async () => {} });
      const error = await malo.config().catch((x) => x);
      expect(error).toBeInstanceOf(OdooError);
      expect(error).toMatchObject({ estado: 401, reintentable: false });
      expect(intentos.peticiones).toHaveLength(1); // ni un reintento
    });

    it("503: Odoo sin JUAN_ODOO_TOKEN contesta 503 a todo (aunque el token sea el bueno) y el Worker lo trata como reintentable", async () => {
      expect(ODOO_URL_SIN_TOKEN, "el script levanta un Odoo sin tokens").toBeTruthy();
      for (const [metodo, ruta] of [["GET", "/config"], ["GET", "/herramientas"], ["GET", "/estado?canal=whatsapp_qr&id_externo=50760000000"]] as const) {
        const r = await apiOdoo(metodo, ruta, { base: ODOO_URL_SIN_TOKEN, token: TOKEN_ODOO });
        expect(r.estado, ruta).toBe(503);
        expect(r.json).toMatchObject({ ok: false });
        expect(r.json.error).toMatch(/JUAN_ODOO_TOKEN/);
      }
      expect((await apiOdoo("POST", "/mensaje", { base: ODOO_URL_SIN_TOKEN, cuerpo: {} })).estado).toBe(503);
      const estado = nuevoEstado();
      const cliente = new OdooCliente(enlaceDcasa(estado, ODOO_URL_SIN_TOKEN), TOKEN_ODOO, { dormir: async () => {} });
      const error = await cliente.config().catch((x) => x);
      expect(error).toMatchObject({ estado: 503, reintentable: true });
      expect(estado.peticiones.length).toBe(2); // lo intentó dos veces (1 reintento)
    });

    it("Odoo → Worker: sin token o con uno malo, 401 con JSON; con el bueno, /odoo/salud responde lo del contrato", async () => {
      for (const token of ["x".repeat(40), null]) {
        const r = await e.w.odooAlWorker("POST", "/odoo/estado", { canal: "whatsapp_qr", id_externo: celularNuevo(), estado: "bot" }, token);
        expect(r.estado).toBe(401);
        expect(r.json).toMatchObject({ ok: false });
      }
      const salud = await e.w.odooAlWorker("GET", "/odoo/salud");
      expect(salud.estado).toBe(200);
      expect(salud.json).toMatchObject({ canales: expect.any(Object), gasto_ia_mes_usd: expect.any(Number), tope_usd: 30 });
      expect(typeof salud.json.version).toBe("string");
      expect(typeof salud.json.ok).toBe("boolean");
      // Cuerpos inválidos: 400 con el texto del problema (Odoo lo guarda como motivo del fallo).
      const sinCanal = await e.w.odooAlWorker("POST", "/odoo/enviar", { canal: "sms", id_externo: "1", texto: "x" });
      expect(sinCanal.estado).toBe(400);
      const adjuntoHttp = await e.w.odooAlWorker("POST", "/odoo/enviar", {
        canal: "whatsapp_qr", id_externo: celularNuevo(), adjuntos: [{ tipo: "imagen", url: "http://dcasapty.com/x.png" }], autor: "vendedora",
      });
      expect(adjuntoHttp.estado).toBe(400);
      expect(adjuntoHttp.json.error).toMatch(/https/);
    });

    it("Probar conexión (botón de Ajustes): Odoo le pregunta su salud al Worker y lo muestra", async () => {
      const accion = await admin.llamar("dcasa.juan.ajustes", "action_probar_conexion", [[e.ajustesId]]);
      // El Worker contesta 200 aunque diga que le falta algo (aquí: los secretos de Telegram, que la prueba no carga).
      expect(accion.params.message).toMatch(/^El Worker respondió\./);
      expect(accion.params.message).toContain("whatsapp_qr: conectado");
      expect(accion.params.message).toMatch(/telegram: sin configurar \(TELEGRAM_BOT_TOKEN_JUAN/);
      expect(accion.params.message).not.toMatch(/[{}]/); // los canales se leen como texto, no como un diccionario
      expect(accion.params.type).toBe("warning");
    });

    it("429: demasiados intentos fallidos con un token malo frenan a todos, incluso al token bueno, un minuto", async () => {
      let ultimo = 0;
      for (let i = 0; i < 32 && ultimo !== 429; i++) ultimo = (await apiOdoo("GET", "/config", { token: "y".repeat(40) })).estado;
      expect(ultimo).toBe(429);
      const bueno = await apiOdoo("GET", "/config");
      expect(bueno.estado).toBe(429);
      expect(bueno.cabeceras.get("retry-after")).toBe("60");
      expect(bueno.json).toMatchObject({ ok: false });
      // El cliente del Worker lo trata como reintentable (con espera), no como un error de datos.
      const estado = nuevoEstado();
      const cliente = new OdooCliente(enlaceDcasa(estado), TOKEN_ODOO, { dormir: async () => {} });
      expect(await cliente.config().catch((x) => x)).toMatchObject({ estado: 429, reintentable: true });
    });
  });
}
