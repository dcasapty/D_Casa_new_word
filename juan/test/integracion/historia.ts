// Sección 2: la historia de Karen, de la bienvenida al seguimiento. Cada paso depende del anterior (misma conversación).

import { spawnSync } from "node:child_process";
import { beforeAll, describe, expect, it } from "vitest";
import { OdooRpc, celularNuevo, type ContextoIA } from "./ayuda";
import type { Escena } from "./escena";

/** El PDF de la cotización lo arma wkhtmltopdf (el trabajo de CI de esta integración no lo instala: ahí solo se prueba lo que no lo necesita). */
const HAY_WKHTMLTOPDF = spawnSync("wkhtmltopdf", ["--version"]).status === 0;

export function seccionHistoria(e: Escena) {
  describe("2. La historia de Karen: bienvenida → camas queen → herramientas → vendedora → devolver", () => {
    const celular = celularNuevo();
    let convId: number;
    let admin: OdooRpc;
    let ventas: OdooRpc;
    beforeAll(() => {
      admin = e.admin;
      ventas = e.ventas;
    });

    // El `codigo` que Juan ve y le dice al cliente es el CÓDIGO PÚBLICO (DC-…), no la referencia del proveedor; el producto
    // de la prueba se reconoce por su nombre. Las herramientas siguen entendiendo la referencia vieja (INT-CAMA-Q).
    const producto = (c: ContextoIA, nombre: string) => (c.resultado("buscar_productos")?.resultado?.productos ?? []).find((p: any) => p.nombre === nombre);

    it("bienvenida y pregunta por camas queen: el bot busca en el catálogo REAL de Odoo y contesta con el precio «+ ITBMS»", async () => {
      const w = e.w;
      w.ia.guionar([
        { llamadas: [{ nombre: "buscar_productos", args: { consulta: "cama queen" } }] },
        (c) => {
          const p = producto(c, "Cama Roble Queen Integración");
          return { texto: `Sí, tenemos la ${p.nombre}, a ${p.precio_texto}. ¿Quieres que te cuente más de esa cama?` };
        },
      ]);
      const r = await w.cliente(celular, "Hola, ¿tienen camas queen?");
      expect(r.status).toBe(200);
      await w.quieta(celular);

      // Lo que le llegó al cliente por el puente: el saludo de Juan (sin anunciarse como asistente) y la respuesta, con «+ ITBMS».
      const texto = w.puente.textos().join("\n");
      expect(texto).toContain("Hola, soy Juan de D'CASA.");
      expect(texto).not.toMatch(/asistente automático/i);
      expect(texto).toContain("Cama Roble Queen Integración");
      expect(texto).toContain("$349.99 + ITBMS");
      expect(w.puente.envios[0].para).toBe(celular);
      expect(w.ia.sinGuion).toEqual([]);

      // Al modelo se le ofrecieron las herramientas de Odoo con sus nombres públicos (más la local de la foto).
      const ofrecidas = w.ia.peticiones[0].cuerpo.tools.map((t: any) => t.name).sort();
      expect(ofrecidas).toEqual(expect.arrayContaining(["buscar_productos", "ver_producto", "reglas_socios", "horario_y_tienda", "pasar_a_vendedora", "enviar_foto_producto"]));
      expect(ofrecidas.some((n: string) => n.startsWith("juan_"))).toBe(false);
      // Y vio las lecciones de la dueña (se editan en Odoo).
      expect(JSON.stringify(w.ia.peticiones[0].cuerpo.system)).toContain("Si preguntan por Yappy");
      // La disponibilidad le llegó como etiqueta, nunca como número.
      const resultado = JSON.stringify(w.ia.peticiones[1].cuerpo.messages);
      expect(resultado).toContain("disponible");
      expect(resultado).not.toMatch(/\b25\b/);

      // En Odoo quedó TODO: la ficha de la clienta, la conversación y los mensajes (cliente + asistente).
      const conv = (await e.conversacionDe(celular))!;
      expect(conv).toBeTruthy();
      convId = conv.id;
      expect(conv.estado).toBe("bot");
      expect(conv.bot_atiende).toBe(true);
      const [ficha] = await ventas.leer("res.partner", [conv.partner_id[0]], ["name", "phone"]);
      expect(ficha.name).toBe("Karen");
      expect(ficha.phone).toContain("6");
      expect(await e.textosDe(celular, "cliente")).toEqual(["Hola, ¿tienen camas queen?"]);
      const delBot = (await e.textosDe(celular, "bot")).join("\n");
      expect(delBot).toContain("Hola, soy Juan de D'CASA.");
      expect(delBot).toContain("$349.99 + ITBMS");
      // La herramienta quedó auditada en Brian como el usuario técnico «juan».
      const acciones = await admin.buscar("brian.accion", [["herramienta", "=", "juan_buscar_productos"], ["canal", "=", "juan"]], ["estado", "usuario_id"]);
      expect(acciones.length).toBeGreaterThan(0);
      expect(acciones.every((a: any) => a.estado === "hecha")).toBe(true);
      expect(String(acciones[0].usuario_id[1])).toMatch(/juan/i);
    });

    it("las herramientas del contrato corren de verdad en Odoo: ver_producto, reglas_socios, horario_y_tienda, buscar_conocimiento, crear_oportunidad, etiquetar, anotar y la foto", async () => {
      const w = e.w;
      w.ia.guionar([
        {
          llamadas: [
            { nombre: "ver_producto", args: { codigo: "INT-CAMA-Q" } },
            { nombre: "reglas_socios", args: {} },
            { nombre: "horario_y_tienda", args: {} },
            { nombre: "buscar_conocimiento", args: { consulta: "horario y dirección" } },
          ],
        },
        // La foto se pide con el código que Juan acaba de ver (el público, DC-…), tal cual lo devolvió ver_producto.
        (c) => ({
          llamadas: [
            { nombre: "enviar_foto_producto", args: { codigo: c.resultado("ver_producto")?.resultado?.codigo } },
            { nombre: "etiquetar_conversacion", args: { etiqueta: "Pidió precio" } },
            { nombre: "crear_oportunidad", args: { resumen: "Karen quiere una cama queen para su cuarto.", interes: "Cama queen", presupuesto: 400 } },
            { nombre: "anotar_conversacion", args: { nota: "Prefiere la cama de roble. Pregunta por Socios." } },
          ],
        }),
        (c) => {
          const ficha = c.resultado("ver_producto")?.resultado;
          return { texto: `La ${ficha.nombre} mide ${ficha.medidas}. Te mando la foto y ya te dejé anotada con una vendedora.` };
        },
      ]);
      await w.cliente(celular, "Me gusta la INT-CAMA-Q. ¿Qué medidas tiene? Mándame la foto. ¿Y cómo funciona Socios y a qué hora abren?");
      await w.quieta(celular);
      expect(w.ia.sinGuion).toEqual([]);
      expect(w.ia.pendientes).toBe(0);

      // Cada herramienta devolvió datos reales (y el modelo los vio sin números de existencias).
      const vistos = JSON.stringify(w.ia.peticiones.at(-1)!.cuerpo.messages);
      expect(vistos).toContain("Ancho × Largo: 160 × 200 cm");
      expect(vistos).toMatch(/puntos/i); // reglas_socios (las cifras salen de puntos.json)
      expect(vistos).toContain("La Chorrera"); // horario_y_tienda
      expect(vistos).not.toMatch(/INT-SECRETO/); // un producto sin publicar no existe para el cliente

      // La foto salió por el puente: la URL pasó la validación REAL del puente (https, dominio de D'CASA) y se pudo bajar.
      expect(w.puente.rechazos).toEqual([]);
      const conFoto = w.puente.envios.find((x) => x.medios.length > 0)!;
      expect(conFoto).toBeTruthy();
      expect(conFoto.medios[0].tipo).toBe("imagen");
      expect(new URL(conFoto.medios[0].url).hostname).toBe("dcasapty.com");
      expect(conFoto.descargas[0].estado).toBe(200);
      expect(conFoto.descargas[0].mime).toMatch(/^image\//);

      // Etiqueta, oportunidad y nota: en Odoo, ligadas a la clienta y a la conversación.
      const conv = (await e.conversacionDe(celular))!;
      const etiquetas = await ventas.leer("dcasa.conversacion.etiqueta", conv.etiqueta_ids, ["name"]);
      expect(etiquetas.map((x: any) => x.name)).toContain("Pidió precio");
      expect(conv.oportunidad_id).toBeTruthy();
      const [lead] = await admin.leer("crm.lead", [conv.oportunidad_id[0]], ["partner_id", "type", "expected_revenue", "name"]);
      expect(lead.partner_id[0]).toBe(conv.partner_id[0]);
      expect(lead.type).toBe("opportunity");
      expect(lead.expected_revenue).toBe(400);
      const notas = await admin.buscar("mail.message", [["model", "=", "res.partner"], ["res_id", "=", conv.partner_id[0]], ["body", "ilike", "cama de roble"]], ["body"]);
      expect(notas.length).toBeGreaterThan(0);

      // Todas quedaron auditadas como «hecha».
      for (const nombre of ["crear_oportunidad", "etiquetar_conversacion", "anotar_conversacion", "reglas_socios", "horario_y_tienda", "buscar_conocimiento", "ver_producto"]) {
        const filas = await admin.buscar("brian.accion", [["herramienta", "=", `juan_${nombre}`]], ["estado"]);
        expect(filas.some((f: any) => f.estado === "hecha"), nombre).toBe(true);
      }
      // El cliente nunca ve los nombres de las herramientas.
      expect(w.puente.textos().join(" ")).not.toMatch(/crear_oportunidad|buscar_productos|etiquetar_conversacion/);
    });

    it("pide una persona → pasar_a_vendedora en Odoo: el bot pausa, hay actividad y aviso, y el cliente recibe el texto de Odoo", async () => {
      const w = e.w;
      w.ia.guionar([{ texto: "(no debería llamarse: «persona» pasa siempre sin IA)" }]);
      const antes = w.puente.envios.length;
      await w.cliente(celular, "Quiero hablar con una persona");
      await w.quieta(celular);
      expect(w.ia.pendientes).toBe(1); // la IA no se usó

      const texto = w.puente.envios.slice(antes).flatMap((x) => x.chunks).join("\n");
      // Dentro del horario laboral (la prueba lo abre 24 h): el texto es el que Odoo manda en pasar_a_vendedora.
      expect(texto).toContain("ya avisé a una vendedora");

      const conv = (await e.conversacionDe(celular))!;
      expect(conv.estado).toBe("humano");
      expect(conv.bot_atiende).toBe(false);
      expect(Date.parse(`${conv.pausada_hasta}Z`) - Date.now()).toBeGreaterThan(110 * 60_000);
      const actividades = await admin.buscar("mail.activity", [["res_model", "=", "dcasa.conversacion"], ["res_id", "=", convId]], ["summary", "note"]);
      expect(actividades.length).toBeGreaterThan(0);
      expect(actividades[0].summary).toContain("Atender a Karen");
      const avisos = (await e.mensajesDe(celular)).filter((m) => m.tipo === "aviso").map((m) => m.texto as string);
      expect(avisos.join("\n")).toMatch(/pasó la conversación a una vendedora/);
    });

    it("mientras la tiene una persona, el bot calla (aunque el cliente escriba) y todo queda registrado", async () => {
      const w = e.w;
      w.ia.guionar([{ texto: "(no debería llamarse)" }]);
      const envios = w.puente.envios.length;
      await w.cliente(celular, "¿Sigues ahí?");
      await w.quieta(celular);
      expect(w.puente.envios.length).toBe(envios);
      expect(w.ia.pendientes).toBe(1);
      expect(await e.textosDe(celular, "cliente")).toContain("¿Sigues ahí?");
      expect((await e.conversacionDe(celular))!.estado).toBe("humano");
    });

    it("la vendedora toma la conversación con el método real de Odoo y escribe desde Odoo: sale por el canal, una sola vez", async () => {
      const w = e.w;
      const resumen = await ventas.llamar("dcasa.conversacion", "tomar", [convId], { minutos: 60 });
      expect(resumen.estado).toBe("humano");
      expect(resumen.asignada_a?.nombre).toBe("Vendedora Integración");
      // El Worker se enteró (POST /odoo/estado) y el aviso no quedó pendiente en Odoo.
      expect((await e.conversacionDe(celular))!.estado_pendiente_de_avisar).toBe(false);

      const envios = w.puente.envios.length;
      const r = await ventas.llamar("dcasa.conversacion", "enviar_respuesta", [convId, "Hola Karen, soy Ana. Te confirmo la cama para el sábado."]);
      expect(r.enviado).toBe(true);
      expect(w.puente.envios.length).toBe(envios + 1);
      expect(w.puente.envios.at(-1)!.chunks).toEqual(["Hola Karen, soy Ana. Te confirmo la cama para el sábado."]);
      expect(w.puente.envios.at(-1)!.para).toBe(celular);

      const delOdoo = (await e.mensajesDe(celular)).filter((m) => m.autor === "vendedora" && m.tipo === "mensaje");
      expect(delOdoo).toHaveLength(1);
      expect(delOdoo[0].estado_envio).toBe("enviado");
      expect(delOdoo[0].origen).toBe("odoo");
      expect(delOdoo[0].id_mensaje).not.toMatch(/^odoo-/); // el Worker le dio su id real

      // El eco del puente (WhatsApp repite lo que enviamos) NO duplica el mensaje; lo que escribe desde el teléfono, sí se registra.
      await w.desdeElTelefono(celular, "Hola Karen, soy Ana. Te confirmo la cama para el sábado.");
      await w.desdeElTelefono(celular, "Ana desde el teléfono: ¿te sirve el sábado por la tarde?");
      await w.quieta(celular);
      const textos = await e.textosDe(celular, "vendedora");
      expect(textos.filter((t) => t.startsWith("Hola Karen, soy Ana"))).toHaveLength(1);
      expect(textos).toContain("Ana desde el teléfono: ¿te sirve el sábado por la tarde?");
      expect(w.puente.envios.length).toBe(envios + 1); // nada de eso reenvía
    });

    it("devolver al asistente con una nota: Odoo avisa al Worker y el bot la lee en el prompt hasta que otra persona tome la conversación", async () => {
      const w = e.w;
      await ventas.llamar("dcasa.conversacion", "devolver", [convId, "ya quedó la visita del sábado a las 3 de la tarde"]);
      const [c] = await admin.leer("dcasa.conversacion", [convId], ["estado", "nota_para_el_bot", "estado_pendiente_de_avisar"]);
      expect(c).toMatchObject({ estado: "bot", nota_para_el_bot: "ya quedó la visita del sábado a las 3 de la tarde", estado_pendiente_de_avisar: false });

      w.ia.guionar([{ texto: "Con gusto, Karen. Cualquier otra duda me escribes." }]);
      const antes = w.puente.envios.length;
      await w.cliente(celular, "Gracias, ¿entonces quedamos para el sábado?");
      await w.quieta(celular);
      expect(w.puente.envios.length).toBe(antes + 1); // el bot volvió a contestar
      expect(w.puente.envios.at(-1)!.chunks.join(" ")).toContain("Con gusto, Karen");
      expect(JSON.stringify(w.ia.peticiones.at(-1)!.cuerpo.system)).toContain("ya quedó la visita del sábado");
    });

    it("tomar de nuevo borra la nota: el bot ya no la lee", async () => {
      const w = e.w;
      await ventas.llamar("dcasa.conversacion", "tomar", [convId, 30]);
      await ventas.llamar("dcasa.conversacion", "devolver", [convId]);
      w.ia.guionar([{ texto: "Claro, aquí sigo para ayudarte." }]);
      await w.cliente(celular, "¿Me ayudas con otra cosa?");
      await w.quieta(celular);
      expect(JSON.stringify(w.ia.peticiones.at(-1)!.cuerpo.system)).not.toContain("ya quedó la visita del sábado");
    });
  });

  describe("2b. Cotización automática: Juan arma el borrador y el PDF en Odoo y el puente lo baja con la URL firmada", () => {
    const celular = celularNuevo();
    let admin: OdooRpc;
    let ventas: OdooRpc;
    beforeAll(() => {
      admin = e.admin;
      ventas = e.ventas;
    });

    const pedido = (codigo: string, cantidad: number) => ({ nombre: "cotizar", args: { lineas: [{ codigo, cantidad }] } });

    it.skipIf(!HAY_WKHTMLTOPDF)("encendida (de fábrica): hay cotización en Ventas, aviso con el PDF en el hilo y el documento sale por el puente", async () => {
      const w = e.w;
      w.ia.guionar([
        { llamadas: [pedido("INT-CAMA-Q", 2)] },
        (c) => {
          const r = c.resultado("cotizar")?.resultado;
          return { texto: `Listo, te armé la cotización ${r.cotizacion.numero}: el total es ${r.cotizacion.total_texto}, con ITBMS. El PDF va adjunto.` };
        },
      ]);
      await w.cliente(celular, "Mándame la cotización de dos INT-CAMA-Q", { nombre: "Marta" });
      await w.quieta(celular);
      expect(w.ia.sinGuion).toEqual([]);
      expect(w.puente.rechazos).toEqual([]);

      // Odoo: un borrador enviado (nunca confirmado), a precio de lista, con los totales de Odoo.
      const conv = (await e.conversacionDe(celular))!;
      const ordenes = await admin.buscar("sale.order", [["partner_id", "=", conv.partner_id[0]]], ["name", "state", "amount_untaxed", "amount_tax", "amount_total", "user_id"]);
      expect(ordenes).toHaveLength(1);
      const orden = ordenes[0];
      expect(orden.state).toBe("sent");
      expect(orden.amount_untaxed).toBeCloseTo(2 * 349.99, 2);
      expect(orden.amount_total).toBeCloseTo(2 * 349.99 * 1.07, 2);
      expect(orden.user_id).toBe(false);
      const lineas = await admin.buscar("sale.order.line", [["order_id", "=", orden.id]], ["price_unit", "product_uom_qty", "discount"]);
      expect(lineas).toEqual([expect.objectContaining({ price_unit: 349.99, product_uom_qty: 2, discount: 0 })]);

      // El PDF salió por el puente como documento, con un enlace firmado de dcasapty.com que el puente bajó entero.
      const envio = w.puente.envios.find((x) => x.medios.some((m) => m.tipo === "documento"))!;
      expect(envio).toBeTruthy();
      expect(envio.medios[0]).toMatchObject({ tipo: "documento", nombre: `Cotizacion-${orden.name}.pdf` });
      const url = new URL(envio.medios[0].url);
      expect(url.protocol).toBe("https:");
      expect(url.pathname).toMatch(new RegExp(`^/dcasa/adjunto/\\d+/\\d+/[0-9a-f]{64}/Cotizacion-${orden.name}\\.pdf$`));
      expect(envio.descargas[0].estado).toBe(200);
      expect(envio.descargas[0].mime).toBe("application/pdf");
      expect(Buffer.from(envio.descargas[0].bytes).subarray(0, 4).toString()).toBe("%PDF");
      // El texto que vio el cliente trae el total de Odoo.
      expect(w.puente.textos().join("\n")).toContain(`$${orden.amount_total.toFixed(2)}`);

      // El modelo nunca vio el enlace firmado.
      expect(JSON.stringify(w.ia.peticiones.at(-1)!.cuerpo.messages)).not.toContain("/dcasa/adjunto/");

      // En el hilo: el aviso (interno) que guarda el PDF y la línea del mensaje del bot SIN una segunda copia del archivo.
      const mensajes = await e.mensajesDe(celular);
      const aviso = mensajes.find((m) => m.tipo === "aviso" && m.adjunto_ids.length > 0)!;
      expect(aviso).toBeTruthy();
      expect(aviso.texto).toContain(orden.name);
      const [adjunto] = await admin.leer("ir.attachment", aviso.adjunto_ids, ["name", "mimetype", "res_model", "res_id"]);
      expect(adjunto).toMatchObject({ name: `Cotizacion-${orden.name}.pdf`, mimetype: "application/pdf", res_model: "dcasa.mensaje", res_id: aviso.id });
      const delBot = mensajes.filter((m) => m.autor === "bot" && m.tipo === "mensaje");
      expect(delBot.map((m) => m.texto).join("\n")).toContain(`[Documento enviado: Cotizacion-${orden.name}.pdf]`);
      expect(delBot.every((m) => m.adjunto_ids.length === 0 && m.adjuntos_fallidos === 0)).toBe(true);

      // Auditada en Brian como el usuario técnico «juan».
      const acciones = await admin.buscar("brian.accion", [["herramienta", "=", "juan_cotizar"]], ["estado"]);
      expect(acciones.some((a: any) => a.estado === "hecha")).toBe(true);
    });

    it("apagada en Ajustes: nada se arma ni se manda, y Juan le pasa la conversación a una vendedora; la vendedora sí puede mandarla a mano", async () => {
      const w = e.w;
      const otro = celularNuevo();
      await e.ajustes({ cotizacion_automatica: false });
      try {
        w.ia.guionar([
          { llamadas: [pedido("INT-CAMA-Q", 1)] },
          (c) => {
            expect(c.resultado("cotizar")?.resultado).toMatchObject({ creada: false, motivo: "apagada" });
            return { texto: "Una vendedora te prepara la cotización." };
          },
        ]);
        const antes = w.puente.envios.filter((x) => x.medios.length > 0).length;
        await w.cliente(otro, "Mándame la cotización de la INT-CAMA-Q", { nombre: "Pedro" });
        await w.quieta(otro);
        expect(w.ia.sinGuion).toEqual([]);
        expect(w.puente.envios.filter((x) => x.medios.length > 0).length).toBe(antes);
        const conv = (await e.conversacionDe(otro))!;
        expect(await admin.buscar("sale.order", [["partner_id", "=", conv.partner_id[0]]], ["name"])).toEqual([]);

        // La vendedora arma y manda la suya con los botones de la pantalla (funciona con la automática apagada).
        if (!HAY_WKHTMLTOPDF) return;
        const [variante] = await admin.buscar("product.product", [["default_code", "=", "INT-CAMA-Q"]], ["id"]);
        const creada = await ventas.llamar("dcasa.conversacion", "crear_cotizacion", [conv.id, [{ variante_id: variante.id, cantidad: 1 }]]);
        const enviada = await ventas.llamar("dcasa.conversacion", "enviar_cotizacion", [conv.id, creada.cotizacion.id]);
        expect(enviada.cotizacion.estado).toBe("sent");
        expect(w.puente.rechazos).toEqual([]);
        expect(w.puente.envios.filter((x) => x.medios.length > 0).length).toBe(antes + 1);
      } finally {
        await e.ajustes({ cotizacion_automatica: true });
      }
    });
  });
}
