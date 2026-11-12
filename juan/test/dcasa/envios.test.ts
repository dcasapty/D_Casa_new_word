/**
 * Envíos (2026-11-12, «sí» de la dueña): Juan dice cuánto cuesta el envío y la promoción del mes con lo que devuelve cotizar_envio, y lo suma
 * a la cotización con agregar_envio si el cliente quiere.
 *
 * La guardia de salida deja decir el costo del envío o «envío gratis» SOLO si en ese mismo turno la herramienta de envíos devolvió esa cifra o
 * ese «gratis» (su `respaldo_envio`, que arma Odoo con el motor y que el modelo no ve). Sin respaldo, se rechaza igual que siempre. El plazo
 * de entrega, el armado y la instalación siguen siempre bloqueados. Lo mismo en inglés.
 */
import { describe, expect, it } from "vitest";
import { analizar, asegurarItbms, detectarPromesas, quitarGraves, type ContextoRevision, type RespaldoDeEnvio } from "../../src/dcasa/salvaguardas";
import { RegistroDelTurno, tomarRespaldoDeEnvio } from "../../src/motor/herramientas";
import { promptEstable } from "../../src/dcasa/prompt";
import { CONFIG_POR_DEFECTO } from "../../src/config";
import { crearMundo } from "../helpers/mundo";
import { ENVIOS } from "../helpers/odooFalso";

const respaldo = (montos: number[], gratis = false): RespaldoDeEnvio => ({ montos: new Set(montos), gratis });
const ctx = (extra: Partial<ContextoRevision> = {}): ContextoRevision => ({ preciosProducto: new Set(), cifrasConocidas: new Set([15, 90, 70, 20, 200, 0]), ...extra });

describe("la guardia: el costo del envío solo con el respaldo de la herramienta de envíos", () => {
  it("sin respaldo, «el envío cuesta $X» sigue rechazado como hoy", () => {
    expect(detectarPromesas("El envío a Villa Lucre cuesta $15.")).toContain("costo de entrega");
    expect(detectarPromesas("El envío a Villa Lucre cuesta $15.", new Set([15]))).toContain("costo de entrega");
    expect(detectarPromesas("El envío a Villa Lucre cuesta $15.", new Set(), respaldo([]))).toContain("costo de entrega");
  });

  it("con la cifra que devolvió la herramienta en este turno, pasa", () => {
    for (const frase of [
      "El envío a Villa Lucre cuesta $15.",
      "El envío cuesta $15 hasta tu casa.",
      "El flete a Colón sale en $90 y con la promoción te queda en $70.",
      "El envío te sale en 15 dólares.",
      "El envío a la 24 de Diciembre cuesta $15.",
    ]) {
      expect(detectarPromesas(frase, new Set(), respaldo([15, 90, 70])), frase).toEqual([]);
    }
  });

  it("otra cifra (aunque la herramienta haya dado alguna) se rechaza", () => {
    expect(detectarPromesas("El envío a Villa Lucre cuesta $20.", new Set(), respaldo([15]))).toContain("costo de entrega");
    expect(detectarPromesas("El envío cuesta $15. El envío a Colón cuesta $90.", new Set(), respaldo([15]))).toContain("costo de entrega");
    expect(detectarPromesas("El envío cuesta $1,250.00.", new Set(), respaldo([1250]))).toEqual([]);
  });

  it("«envío gratis» solo si la herramienta dijo «gratis» en este turno", () => {
    for (const frase of ["Este mes tenemos Envío Gratis Todo Noviembre.", "El envío es gratis.", "Tu envío sería gratis."]) {
      expect(detectarPromesas(frase), frase).toContain("entrega o flete gratis");
      expect(detectarPromesas(frase, new Set(), respaldo([15], false)), frase).toContain("entrega o flete gratis");
      expect(detectarPromesas(frase, new Set(), respaldo([0, 15], true)), frase).toEqual([]);
    }
  });

  it("el armado, la instalación y el plazo de entrega siguen siempre bloqueados", () => {
    const todo = respaldo([0, 3, 15], true);
    expect(detectarPromesas("El armado es gratis.", new Set(), todo)).toContain("entrega o flete gratis");
    expect(detectarPromesas("La instalación va a ser gratis.", new Set(), todo)).toContain("entrega o flete gratis");
    expect(detectarPromesas("Te lo entregamos mañana.", new Set(), todo)).toContain("plazo de entrega");
    expect(detectarPromesas("La entrega tarda 3 días.", new Set(), todo)).toContain("plazo de entrega");
    expect(detectarPromesas("Te lo llevamos el sábado y el envío es gratis.", new Set(), todo)).toEqual(["plazo de entrega"]);
  });

  it("en inglés también", () => {
    expect(detectarPromesas("Delivery costs $15.")).toContain("costo de entrega");
    expect(detectarPromesas("Delivery costs $15.", new Set(), respaldo([15]))).toEqual([]);
    expect(detectarPromesas("Delivery costs $25.", new Set(), respaldo([15]))).toContain("costo de entrega");
    expect(detectarPromesas("Free delivery this month.")).toContain("entrega o flete gratis");
    expect(detectarPromesas("Free delivery this month.", new Set(), respaldo([0, 15], true))).toEqual([]);
    expect(detectarPromesas("Assembly is free.", new Set(), respaldo([0], true))).toContain("entrega o flete gratis");
    expect(detectarPromesas("We'll deliver it tomorrow.", new Set(), respaldo([0], true))).toContain("plazo de entrega");
  });

  it("analizar y quitarGraves: se queda la oración respaldada y se va la que no", () => {
    const con = ctx({ envio: respaldo([15]) });
    expect(analizar("El envío a Villa Lucre cuesta $15.", con).graves).toEqual([]);
    expect(analizar("El envío a Villa Lucre cuesta $15.", ctx()).graves.map((g) => g.tipo)).toContain("promesa");
    expect(quitarGraves("El envío a Villa Lucre cuesta $15. El de Colón cuesta $90 y el envío es gratis.", con)).toBe("El envío a Villa Lucre cuesta $15.");
  });

  it("no le pone «+ ITBMS» a la cifra del envío aunque un producto cueste lo mismo", () => {
    const productos = new Set([15]);
    expect(asegurarItbms("La lámpara cuesta $15. El envío a Villa Lucre cuesta $15.", productos, new Set([15]))).toBe(
      "La lámpara cuesta $15 + ITBMS. El envío a Villa Lucre cuesta $15.",
    );
    expect(asegurarItbms("El envío a Villa Lucre cuesta $15.", productos)).toBe("El envío a Villa Lucre cuesta $15 + ITBMS.", "sin respaldo, como siempre");
  });
});

describe("el respaldo lo arma Odoo y el modelo no lo ve", () => {
  it("tomarRespaldoDeEnvio anota las cifras y el «gratis» y lo quita del resultado", () => {
    const reg = new RegistroDelTurno();
    const visto = tomarRespaldoDeEnvio({ estado: "precio", respaldo_envio: { montos: [0, 15, "x", -3, Number.NaN], gratis: true } }, reg) as Record<string, unknown>;
    expect(visto).toEqual({ estado: "precio" });
    expect([...reg.montosEnvio].sort()).toEqual([0, 15]);
    expect(reg.envioGratis).toBe(true);
    const otro = new RegistroDelTurno();
    expect(tomarRespaldoDeEnvio({ estado: "aparte" }, otro)).toEqual({ estado: "aparte" });
    expect(otro.montosEnvio.size).toBe(0);
    expect(otro.envioGratis).toBe(false);
  });
});

describe("Juan cotiza el envío con la herramienta y lo dice tal cual", () => {
  const frase = ENVIOS.villaLucre.frase_para_el_cliente;

  it("con cotizar_envio en el turno, el precio y el «gratis» de la promoción salen al cliente", async () => {
    const m = crearMundo();
    const g = m.guion([{ llamadas: [{ nombre: "cotizar_envio", args: { lugar: "Villa Lucre" } }] }, { texto: frase }]);
    await m.conversar("¿cuánto cuesta el envío a Villa Lucre?");
    const texto = m.canal.textos.join("\n");
    expect(texto).toContain("Envío a Villa Lucre (José Domingo Espinar, San Miguelito): $15.");
    expect(texto).toContain("Envío Gratis Todo Noviembre");
    expect(texto).toContain("este envío te sale gratis");
    expect(texto).not.toContain("+ ITBMS");
    expect(g.prompts()[1]).not.toContain("respaldo_envio");
    expect(g.prompts()[1]).toContain("frase_para_el_cliente");
  });

  it("el modelo reformula con las cifras de la herramienta y pasa", async () => {
    const m = crearMundo();
    m.guion([{ llamadas: [{ nombre: "cotizar_envio", args: { lugar: "Colón" } }] }, { texto: "El envío a Barrio Norte cuesta $90. Con la promoción, si tu compra pasa de $200 sin ITBMS, te queda en $70." }]);
    await m.conversar("¿y a Colón?");
    expect(m.canal.textos.join("\n")).toContain("El envío a Barrio Norte cuesta $90.");
  });

  it("sin la herramienta en el turno, decir el costo o «gratis» se rechaza como siempre", async () => {
    const m = crearMundo();
    const g = m.guion([{ texto: "El envío a Villa Lucre cuesta $15 y este mes el envío es gratis." }, { texto: "Para decirte el costo del envío necesito el barrio o un punto de referencia." }]);
    await m.conversar("¿cuánto cuesta el envío a Villa Lucre?");
    const texto = m.canal.textos.join("\n");
    expect(texto).not.toContain("$15");
    expect(texto).not.toMatch(/envío es gratis/);
    expect(g.prompts()[1]).toContain("promesa de entrega, flete, financiamiento, apartado o descuento");
  });

  it("una cifra del envío inventada por el modelo no pasa aunque la herramienta haya dado otra", async () => {
    const m = crearMundo();
    m.guion([{ llamadas: [{ nombre: "cotizar_envio", args: { lugar: "Colón" } }] }, { texto: "El envío a Colón cuesta $50. ¿Te sirve?" }]);
    await m.conversar("¿y a Colón?");
    const texto = m.canal.textos.join("\n");
    expect(texto).not.toContain("$50");
  });

  it("en zona con abono, decir «envío gratis» no pasa (la herramienta no lo dijo)", async () => {
    const m = crearMundo();
    m.guion([{ llamadas: [{ nombre: "cotizar_envio", args: { lugar: "Colón" } }] }, { texto: "El envío es gratis a Colón con la promoción. ¿Te lo sumo?" }]);
    await m.conversar("¿y a Colón?");
    expect(m.canal.textos.join("\n")).not.toMatch(/envío es gratis/i);
  });
});

describe("agregar_envio: el PDF nuevo sale con la respuesta", () => {
  it("después de cotizar, sumar el envío deja un solo PDF (el que ya trae el envío)", async () => {
    const m = crearMundo();
    m.guion([
      { llamadas: [{ nombre: "cotizar", args: { lineas: [{ codigo: "CAMA-Q-001" }] } }] },
      { llamadas: [{ nombre: "agregar_envio", args: { lugar_id: 77 } }] },
      { texto: "Listo, te sumé el envío a la cotización. Envío a Villa Lucre: $15, y con la promoción este envío te sale gratis. El PDF va adjunto." },
    ]);
    await m.conversar("cotízame la cama queen y súmale el envío a Villa Lucre");
    expect(m.odoo.enviosSumados).toEqual([{ lugar_id: 77 }]);
    expect(m.canal.medios).toHaveLength(1);
    expect(m.canal.medios[0]).toMatchObject({ tipo: "documento", url: expect.stringContaining("b".repeat(64)) });
    expect(m.canal.textos.join("\n")).toContain("te sale gratis");
  });

  it("sin cotización no se suma nada y el modelo lo sabe", async () => {
    const m = crearMundo();
    const g = m.guion([{ llamadas: [{ nombre: "agregar_envio", args: { lugar_id: 77 } }] }, { texto: "Primero armo la cotización y después le sumo el envío." }]);
    await m.conversar("súmale el envío");
    expect(m.canal.medios).toHaveLength(0);
    expect(g.prompts()[1]).toContain("sin_cotizacion");
  });
});

describe("el prompt: la regla de envíos", () => {
  const prompt = promptEstable(CONFIG_POR_DEFECTO);
  const como = prompt.split("<como_trabajas>")[1]!.split("</como_trabajas>")[0]!;

  it("pide el lugar sin la dirección exacta, usa cotizar_envio, pregunta cuál y ofrece sumarlo", () => {
    expect(como).toMatch(/pregúntale el barrio, el PH o un punto de referencia \(nunca la dirección exacta/);
    expect(como).toContain("cotizar_envio");
    expect(como).toMatch(/Si devuelve varios lugares, pregúntale cuál es/);
    expect(como).toMatch(/frase_para_el_cliente tal cual/);
    expect(como).toContain("«¿Quieres que te lo sume a la cotización?»");
    expect(como).toMatch(/solo si dice que sí, llama a agregar_envio/);
    expect(como).toMatch(/La promoción de envío NUNCA la calculas tú/);
    expect(como).toMatch(/La fecha de entrega la confirma siempre una vendedora/);
  });

  it("la regla 3 sigue mandando la fecha, el financiamiento, los apartados y los descuentos a una vendedora", () => {
    const reglas = prompt.split("<reglas>")[1]!.split("</reglas>")[0]!;
    const tres = reglas.split("\n").find((l) => l.startsWith("3. "))!;
    expect(tres).toContain("cuánto cuesta el envío a un lugar: eso lo dice cotizar_envio");
    expect(tres).toContain("qué día le llega");
    expect(tres).toMatch(/no haces apartados, ni apruebas créditos, ni das descuentos, ni fijas entregas/);
    expect(prompt).toMatch(/el costo del envío y su promoción solo como los dio cotizar_envio, sin calcular nada/);
  });
});
