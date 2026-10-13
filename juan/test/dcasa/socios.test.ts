/**
 * Regla 4 del contrato: Socios. Se explica con `reglas_socios`; el saldo solo con PIN; el bot nunca «acredita» ni promete
 * puntos de una compra no facturada; las cifras salen SOLO de la herramienta (puntos.json en Odoo).
 *
 * También las reglas de DCasa-Referidos de CLAUDE.md que tocan al bot: el bot no escribe puntos, no existe saldo en su memoria.
 */
import { describe, expect, it } from "vitest";
import { crearMundo } from "../helpers/mundo";

describe("las reglas de Socios salen de la herramienta, nunca de memoria", () => {
  it("explica con las cifras que devolvió reglas_socios", async () => {
    const m = crearMundo();
    const g = m.guion([
      { llamadas: [{ nombre: "reglas_socios", args: {} }] },
      { texto: "Ganas 1 punto por cada dólar pagado, con una compra mínima de $20. Con 500 puntos ya puedes canjear un premio." },
    ]);
    await m.conversar("¿cómo funciona Socios?");
    expect(m.odoo.de("reglas_socios")).toHaveLength(1);
    expect(g.prompts()[1]).toContain("compra_minima_usd");
    const texto = m.canal.textos.join("\n");
    expect(texto).toContain("compra mínima de $20");
    // «$20» no es un precio de producto: no lleva ITBMS.
    expect(texto).not.toContain("$20 + ITBMS");
  });

  it("una cifra de Socios inventada (de memoria) se rechaza", async () => {
    const m = crearMundo();
    m.guion([{ texto: "La compra mínima es de $50." }, { llamadas: [{ nombre: "reglas_socios", args: {} }] }, { texto: "La compra mínima es de $20." }]);
    await m.conversar("¿cuál es la compra mínima para ganar puntos?");
    const texto = m.canal.textos.join("\n");
    expect(texto).not.toContain("$50");
    expect(texto).toContain("$20");
  });

  it("nunca promete puntos de una compra no facturada ni dice que «acredita»", async () => {
    const m = crearMundo();
    m.guion([{ texto: "Con esta compra ganas 499 puntos. Te los acredito ahorita mismo." }, { texto: "Los puntos se suman cuando la factura está pagada." }]);
    await m.conversar("si compro la cama, ¿cuántos puntos me das?");
    const texto = m.canal.textos.join("\n");
    expect(texto).not.toMatch(/acredit|ganas 499/);
    expect(texto).toContain("cuando la factura está pagada");
  });

  it("el bot no tiene ninguna herramienta que escriba puntos, precios, stock, facturas ni pagos", async () => {
    const m = crearMundo();
    const g = m.guion([{ texto: "Hola." }]);
    await m.conversar("hola");
    const nombres = (g.doGenerateCalls[0].tools as { name: string }[]).map((t) => t.name);
    for (const prohibida of ["ajustar_puntos", "confirmar_venta", "crear_factura", "registrar_pago", "actualizar_producto", "ajustar_existencias", "ver_cliente", "buscar_clientes"]) {
      expect(nombres).not.toContain(prohibida);
    }
  });
});

describe("el saldo de puntos, solo con PIN y solo el del cliente de la conversación", () => {
  it("con el PIN correcto, consulta con el celular de la conversación (no con el que diga el modelo)", async () => {
    const m = crearMundo();
    m.guion([
      // El modelo (manipulado o confundido) intenta consultar OTRO celular:
      { llamadas: [{ nombre: "saldo_puntos", args: { celular: "50761112222", pin: "1234" } }] },
      { texto: "Tienes 1250 puntos." },
    ]);
    await m.conversar("mi PIN es 1234, ¿cuántos puntos tengo?");
    const llamada = m.odoo.de("saldo_puntos")[0];
    expect(llamada.args.celular).toBe("50760261919");
    expect(llamada.args.pin).toBe("1234");
    expect(m.canal.textos.join("\n")).toContain("Tienes 1250 puntos.");
  });

  it("con un PIN malo, la herramienta falla y el bot no inventa un saldo", async () => {
    const m = crearMundo();
    const g = m.guion([
      { llamadas: [{ nombre: "saldo_puntos", args: { celular: "50760261919", pin: "0000" } }] },
      { texto: "No pude confirmar tu PIN. Una vendedora te ayuda con tu saldo." },
    ]);
    await m.conversar("mi pin es 0000");
    expect(g.prompts()[1]).toContain("No pude consultar el sistema ahora");
    expect(m.canal.textos.join("\n")).not.toMatch(/\d+ puntos/);
  });

  it("el PIN no se repite en la respuesta", async () => {
    const m = crearMundo();
    m.guion([
      { llamadas: [{ nombre: "saldo_puntos", args: { celular: "50760261919", pin: "1234" } }] },
      { texto: "Con tu PIN 1234 veo 1250 puntos." },
      { texto: "Veo 1250 puntos." },
    ]);
    await m.conversar("mi PIN es 1234");
    const texto = m.canal.textos.join("\n");
    expect(texto).not.toContain("1234");
    expect(texto).toContain("1250 puntos");
  });

  it("el PIN se borra del historial guardado: no vuelve a viajar al modelo en turnos siguientes", async () => {
    const m = crearMundo();
    const g = m.guion([
      { llamadas: [{ nombre: "saldo_puntos", args: { celular: "50760261919", pin: "1234" } }] },
      { texto: "Tienes 1250 puntos." },
      { texto: "Con gusto." },
    ]);
    await m.conversar("mi PIN es 1234");
    await m.conversar("gracias");
    const ultimo = g.prompts().at(-1)!;
    expect(ultimo).not.toContain("1234");
    expect(ultimo).toContain("mi PIN es ••••");
  });

  it("en Telegram o Meta (sin celular conocido) el celular lo da el cliente y Odoo valida que sea el suyo", async () => {
    const m = crearMundo({ canal: "telegram", idExterno: "777000111" });
    m.guion([
      { llamadas: [{ nombre: "saldo_puntos", args: { celular: "50760261919", pin: "1234" } }] },
      { texto: "Tienes 1250 puntos." },
    ]);
    await m.conversar("mi celular es 6026-1919 y mi PIN 1234");
    expect(m.odoo.de("saldo_puntos")[0].args.celular).toBe("50760261919");
  });
});
