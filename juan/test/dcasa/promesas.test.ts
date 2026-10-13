/**
 * Regla 3 del contrato: entregas, flete, financiamiento, apartados y descuentos NUNCA los promete el bot.
 * Siempre «eso te lo confirma una vendedora». Y regla 5/4: ni un pago ni unos puntos se dan por hechos.
 *
 * Aquí el modelo guionado se porta MAL a propósito (promete lo que no debe) y se comprueba que eso nunca llega al cliente.
 */
import { describe, expect, it } from "vitest";
import { detectarPromesas, TEXTO_SIN_DATO } from "../../src/dcasa/salvaguardas";
import { crearMundo } from "../helpers/mundo";

const BUENA = "La entrega te la confirma una vendedora. ¿Quieres que le pase tu consulta?";

const preguntas: [string, string][] = [
  ["¿me lo entregan mañana?", "Sí, te lo entregamos mañana sin falta."],
  ["¿cuánto cuesta el flete a Arraiján?", "El envío es gratis a todo Panamá Oeste."],
  ["¿tienen financiamiento?", "Sí, financiamos en 12 cuotas sin interés."],
  ["¿me la pueden apartar?", "Claro, te la apartamos hasta el sábado."],
  ["¿me hacen descuento si pago en efectivo?", "Te doy un descuento si pagas en efectivo."],
  ["¿llega antes del viernes?", "Sí, te llega el jueves."],
];

describe("el bot no promete entregas, flete, financiamiento, apartados ni descuentos", () => {
  it.each(preguntas)("%s → la promesa se rechaza y el modelo reescribe", async (pregunta, promesa) => {
    const m = crearMundo();
    const g = m.guion([{ texto: promesa }, { texto: BUENA }]);
    await m.conversar(pregunta);
    const texto = m.canal.textos.join("\n");
    expect(detectarPromesas(texto)).toEqual([]);
    expect(texto).toContain("te la confirma una vendedora");
    expect(g.prompts()[1]).toContain("promesa de entrega, flete, financiamiento, apartado o descuento");
  });

  it.each(preguntas)("%s → si el modelo insiste, esa oración no sale", async (pregunta, promesa) => {
    const m = crearMundo();
    m.guion([{ texto: `${promesa} ¿Algo más en lo que te ayude?` }]);
    await m.conversar(pregunta);
    const texto = m.canal.textos.join("\n");
    expect(detectarPromesas(texto)).toEqual([]);
    expect(texto).toContain("¿Algo más en lo que te ayude?");
  });

  it("si lo único que dijo fue una promesa, responde que lo confirma una vendedora", async () => {
    const m = crearMundo();
    m.guion([{ texto: "Te la apartamos hasta el sábado." }]);
    await m.conversar("¿me la apartan?");
    expect(m.canal.textos.at(-1)).toBe(TEXTO_SIN_DATO);
  });

  it("registra el interés y pasa a una vendedora cuando el cliente quiere seguir con eso", async () => {
    const m = crearMundo();
    m.guion([
      {
        llamadas: [
          { nombre: "crear_oportunidad", args: { resumen: "Quiere apartar la cama queen CAMA-Q-001", interes: "apartado" } },
          { nombre: "pasar_a_vendedora", args: { motivo: "Quiere apartar la cama queen" } },
        ],
      },
      { texto: "Listo, ya avisé a una vendedora. Te escribe por aquí en unos minutos." },
    ]);
    await m.conversar("quiero apartar la cama queen");
    expect(m.odoo.de("crear_oportunidad").length).toBe(1);
    expect(m.odoo.de("pasar_a_vendedora").length).toBe(1);
    // El mensaje de la derivación sale aunque Odoo ya haya pausado al bot por esta misma derivación.
    expect(m.canal.textos.join("\n")).toContain("ya avisé a una vendedora");
  });
});

describe("nunca da por recibido un pago ni acredita puntos (reglas 4 y 5)", () => {
  const malas = [
    "Ya vi tu pago, todo en orden.",
    "Tu pago fue confirmado.",
    "Recibimos tu comprobante, queda pagado.",
    "Perfecto, tu transferencia está verificada.",
    "Te acredito 500 puntos ahorita mismo.",
    "Ya acreditamos tus puntos.",
    "Con esta compra ganas 499 puntos.",
    "Te sumamos 300 puntos a tu cuenta.",
  ];
  it.each(malas)("rechaza: %s", async (frase) => {
    const m = crearMundo();
    m.guion([{ texto: frase }]);
    await m.conversar("hola");
    expect(m.canal.textos.join("\n")).not.toContain(frase);
    expect(detectarPromesas(frase).length).toBeGreaterThan(0);
  });

  const buenas = [
    "Recibí tu archivo; una vendedora lo revisa y te confirma.",
    "Los puntos se suman cuando la factura está pagada.",
    "Ganas 1 punto por cada dólar pagado.",
    "Para canjear necesitas 500 puntos.",
  ];
  it.each(buenas)("no rechaza: %s", (frase) => {
    expect(detectarPromesas(frase)).toEqual([]);
  });
});
