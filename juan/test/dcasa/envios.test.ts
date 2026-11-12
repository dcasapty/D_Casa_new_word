/**
 * Envíos (2026-11-12, «sí» de la dueña): Juan dice cuánto cuesta el envío y la promoción del mes con lo que devuelve cotizar_envio, y lo suma
 * a la cotización con agregar_envio si el cliente quiere.
 *
 * La guardia de salida deja decir el costo del envío o «envío gratis» SOLO si en ese mismo turno la herramienta de envíos lo respaldó (su
 * `respaldo_envio`, que arma Odoo con el motor y que el modelo no ve): cada cifra con su papel (el precio normal, lo que queda, lo abonado
 * solo como ahorro, el mínimo, lo que suma la cotización, el total) y para el lugar que nombra; con la promoción condicional, el beneficio
 * solo con el mínimo en la misma oración. Se revisa cláusula por cláusula, diga como diga el envío o el «gratis». El plazo de entrega, el
 * armado y la instalación siguen siempre bloqueados. Lo mismo en inglés.
 *
 * Revisión adversarial del 2026-11-12: cada escenario del revisor (F1…F8, B1…B4, C1…C5) está aquí con la expectativa al revés. Segunda
 * vuelta (I-4, I-5, I-6, M-4, M-5): N1…N8, P1…P4, C2', C6 y W1, también al revés, y el sondeo de frases legítimas. Tercera vuelta (B-1,
 * I-A, I-C, M-e): las frases de sondeo3 y regresion3 y las conversaciones C3-1 y C3-2.
 */
import { describe, expect, it } from "vitest";
import { analizar, asegurarItbms, detectarPromesas, quitarGraves, type ContextoRevision, type LugarDeEnvio, type RespaldoDeEnvio } from "../../src/dcasa/salvaguardas";
import { RegistroDelTurno, tomarRespaldoDeEnvio } from "../../src/motor/herramientas";
import { promptEstable } from "../../src/dcasa/prompt";
import { CONFIG_POR_DEFECTO } from "../../src/config";
import { crearMundo } from "../helpers/mundo";
import { ENVIOS } from "../helpers/odooFalso";

const lugar = (l: Partial<LugarDeEnvio> & { nombres: string[] }): LugarDeEnvio => ({
  normal: null,
  final: null,
  ahorro: null,
  gratis: false,
  condicional: false,
  minimo: null,
  compra: null,
  cargos: [],
  llevaItbms: false,
  ...l,
});
const respaldo = (lugares: LugarDeEnvio[], total: number | null = null): RespaldoDeEnvio => ({ lugares, total });

// Como los devuelve Odoo (sin compra todavía, la promoción es condicional; con la compra de la cotización, aplica).
const VILLA_LUCRE = lugar({ nombres: ["villa lucre", "jose domingo espinar", "san miguelito"], normal: 15, final: 0, ahorro: 15, gratis: true, condicional: true, minimo: 200 });
const VILLA_LUCRE_APLICA = { ...VILLA_LUCRE, condicional: false };
const COLON = lugar({ nombres: ["barrio norte", "colon"], normal: 90, final: 70, ahorro: 20, condicional: true, minimo: 200 });
const COLON_APLICA = { ...COLON, condicional: false };
const SIN_PROMOCION = lugar({ nombres: ["costa inventada", "santa prueba", "panama"], normal: 45 });

const ctx = (envio?: RespaldoDeEnvio, precios: number[] = []): ContextoRevision => ({
  preciosProducto: new Set(precios),
  cifrasConocidas: new Set([0, 15, 20, 45, 70, 90, 200, 499, 855.47, ...precios]),
  envio,
});
const graves = (texto: string, envio?: RespaldoDeEnvio, precios: number[] = []) => analizar(texto, ctx(envio, precios)).graves.map((g) => g.detalle);

describe("la guardia: el costo del envío solo con el respaldo de la herramienta de envíos", () => {
  it("sin respaldo, decir el costo del envío o «gratis» sigue rechazado", () => {
    expect(detectarPromesas("El envío a Villa Lucre cuesta $15.")).toContain("costo de entrega");
    expect(detectarPromesas("El envío a Villa Lucre cuesta $15.", new Set([15]))).toContain("costo de entrega");
    expect(detectarPromesas("El envío a Villa Lucre cuesta $15.", new Set(), respaldo([]))).toContain("costo de entrega");
    for (const frase of ["Este mes tenemos Envío Gratis Todo Noviembre.", "El envío es gratis.", "Tu envío sería gratis."]) {
      expect(detectarPromesas(frase), frase).toContain("entrega o flete gratis");
    }
  });

  it("con la cifra que devolvió la herramienta en este turno, y con su papel, pasa", () => {
    const r = respaldo([lugar({ nombres: ["villa lucre"], normal: 15 }), lugar({ nombres: ["colon"], normal: 90, final: 70, ahorro: 20, minimo: 200 })]);
    for (const frase of [
      "El envío a Villa Lucre cuesta $15.",
      "El envío cuesta $15 hasta tu casa.",
      "El flete a Colón sale en $90 y con la promoción te queda en $70.",
      "El envío te sale en 15 dólares.",
      "El envío a la 24 de Diciembre cuesta $15.",
      "Envío a Villa Lucre: $15.",
    ]) {
      expect(detectarPromesas(frase, new Set(), r), frase).toEqual([]);
    }
    expect(detectarPromesas("El envío cuesta $1,250.00.", new Set(), respaldo([lugar({ nombres: ["lejos"], normal: 1250 })]))).toEqual([]);
  });

  it("otra cifra (aunque la herramienta haya dado alguna) se rechaza", () => {
    const r = respaldo([lugar({ nombres: ["villa lucre"], normal: 15 })]);
    expect(detectarPromesas("El envío a Villa Lucre cuesta $20.", new Set(), r)).toContain("costo de entrega");
    expect(detectarPromesas("El envío cuesta $15. El envío a Colón cuesta $90.", new Set(), r)).toContain("costo de entrega");
  });

  it("«envío gratis» solo si la herramienta lo dijo de ese envío, y con la condición si todavía no hay compra", () => {
    for (const frase of ["Este mes tenemos Envío Gratis Todo Noviembre.", "El envío es gratis.", "Tu envío sería gratis."]) {
      expect(detectarPromesas(frase, new Set(), respaldo([SIN_PROMOCION])), frase).toContain("entrega o flete gratis");
      expect(detectarPromesas(frase, new Set(), respaldo([VILLA_LUCRE_APLICA])), frase).toEqual([]);
      expect(detectarPromesas(frase, new Set(), respaldo([VILLA_LUCRE])), frase).toContain("entrega o flete gratis");
    }
    expect(detectarPromesas("En compras de más de $200 sin ITBMS, el envío a Villa Lucre es gratis.", new Set(), respaldo([VILLA_LUCRE]))).toEqual([]);
  });

  it("el armado, la instalación y el plazo de entrega siguen siempre bloqueados", () => {
    const todo = respaldo([lugar({ nombres: ["villa lucre"], normal: 15, final: 0, ahorro: 15, gratis: true, minimo: 200 })]);
    expect(detectarPromesas("El armado es gratis.", new Set(), todo)).toContain("entrega o flete gratis");
    expect(detectarPromesas("La instalación va a ser gratis.", new Set(), todo)).toContain("entrega o flete gratis");
    expect(detectarPromesas("Te lo entregamos mañana.", new Set(), todo)).toContain("plazo de entrega");
    expect(detectarPromesas("La entrega tarda 3 días.", new Set(), todo)).toContain("plazo de entrega");
    expect(detectarPromesas("Te lo llevamos el sábado y el envío es gratis.", new Set(), todo)).toEqual(["plazo de entrega"]);
  });

  it("en inglés también", () => {
    const r = respaldo([lugar({ nombres: ["villa lucre"], normal: 15 })]);
    expect(detectarPromesas("Delivery costs $15.")).toContain("costo de entrega");
    expect(detectarPromesas("Delivery costs $15.", new Set(), r)).toEqual([]);
    expect(detectarPromesas("Delivery costs $25.", new Set(), r)).toContain("costo de entrega");
    expect(detectarPromesas("Free delivery this month.")).toContain("entrega o flete gratis");
    expect(detectarPromesas("Free delivery this month.", new Set(), respaldo([VILLA_LUCRE_APLICA]))).toEqual([]);
    expect(detectarPromesas("Assembly is free.", new Set(), respaldo([VILLA_LUCRE_APLICA]))).toContain("entrega o flete gratis");
    expect(detectarPromesas("We'll deliver it tomorrow.", new Set(), respaldo([VILLA_LUCRE_APLICA]))).toContain("plazo de entrega");
  });

  it("analizar y quitarGraves: se queda la oración respaldada y se va la que no", () => {
    const con = respaldo([lugar({ nombres: ["villa lucre"], normal: 15 })]);
    expect(graves("El envío a Villa Lucre cuesta $15.", con)).toEqual([]);
    expect(analizar("El envío a Villa Lucre cuesta $15.", ctx()).graves.map((g) => g.tipo)).toContain("promesa");
    expect(quitarGraves("El envío a Villa Lucre cuesta $15. El de Colón cuesta $90 y el envío es gratis.", ctx(con))).toBe("El envío a Villa Lucre cuesta $15.");
  });
});

describe("revisión adversarial: lo que antes se colaba ahora no pasa (F1…F7)", () => {
  it("F1 lo abonado nunca es lo que cuesta: Colón $90 con $20 de abono → «el envío cuesta $20» no pasa", () => {
    expect(detectarPromesas("El envío a Colón cuesta $20.", new Set(), respaldo([COLON_APLICA]))).toContain("costo de entrega");
    expect(graves("El envío a Colón cuesta $20.", respaldo([COLON_APLICA]))).toContain("costo de entrega");
    // Dicho como ahorro, sí.
    for (const frase of ["Con la promoción, D'CASA te abona $20 del envío a Colón.", "El envío a Colón te sale $20 más barato.", "El abono del envío es de $20."]) {
      expect(graves(frase, respaldo([COLON_APLICA])), frase).toEqual([]);
    }
  });

  it("F2 / C1 cada lugar con sus cifras: Villa Lucre $15 gratis y Colón $90 en el mismo turno", () => {
    const dos = respaldo([VILLA_LUCRE_APLICA, COLON_APLICA]);
    expect(graves("El envío a Colón cuesta $15.", dos)).toContain("costo de entrega");
    expect(graves("El envío a Colón es gratis.", dos)).toContain("entrega o flete gratis");
    expect(graves("El envío a Colón cuesta $90 y el de Villa Lucre te sale gratis.", dos)).toEqual([]);
    expect(graves("El envío a Villa Lucre cuesta $15 y a Colón $90.", dos)).toEqual([]);
    expect(graves("El envío a Villa Lucre cuesta $15 y a Colón $15.", dos)).toContain("costo de entrega");
    // Sin nombrar el lugar, pasa una cifra que tenga el papel correcto en alguno de los dos.
    expect(graves("El envío cuesta $90.", dos)).toEqual([]);
    expect(graves("El envío cuesta $20.", dos)).toContain("costo de entrega");
  });

  it("F3 se revisa diga como diga el costo: «Envío a Colón: $20», «te queda en $20», «pagas $20»…", () => {
    const r = respaldo([COLON]);
    for (const t of [
      "Envío a Colón: $20.",
      "El envío a Colón te queda en $20.",
      "Por el envío a Colón pagas $20.",
      "Te cobramos $20 por el envío a Colón.",
      "Son $20 de envío a Colón.",
      "El envío a Colón: $200.",
      "Envío a Colón, $20.",
      "Para el envío a Colón: te queda en $20.",
      "El envío a Colón cuesta $90. Con la promoción te queda en $20.",
    ]) {
      expect(graves(t, r), t).toContain("costo de entrega");
    }
  });

  it("F3b sin ninguna herramienta de envíos en el turno, una cifra conocida (el precio de un producto) dicha como envío no pasa", () => {
    for (const t of ["Envío a Colón: $499.", "El envío a Colón te queda en $499.", "Por el envío pagas $499."]) {
      expect(graves(t, undefined, [499]), t).toContain("costo de entrega");
    }
  });

  it("F4 «gratis» dicho de cualquier forma (sin respaldo de ese «gratis») no pasa", () => {
    for (const t of [
      "El envío te sale gratis.",
      "Con la promoción el envío te sale gratis.",
      "El envío a Colón te queda gratis.",
      "No pagas envío.",
      "El envío va por nuestra cuenta.",
      "Te lo llevamos sin costo.",
      "El envío a Colón te queda en $0.",
      "Shipping to Colón is on us.",
      "You won't pay for shipping.",
    ]) {
      expect(graves(t), t).toContain("entrega o flete gratis");
      expect(graves(t, respaldo([COLON_APLICA])), t).toContain("entrega o flete gratis");
    }
    expect(graves("No pagas envío.", respaldo([VILLA_LUCRE_APLICA]))).toEqual([]);
    expect(graves("El envío a Villa Lucre te queda en $0.", respaldo([VILLA_LUCRE_APLICA]))).toEqual([]);
  });

  it("F5 con la promoción condicional, el «gratis» o lo que queda solo con el mínimo en la misma oración", () => {
    expect(graves("El envío a Villa Lucre es gratis.", respaldo([VILLA_LUCRE]))).toContain("entrega o flete gratis");
    expect(graves("El envío a Colón cuesta $70.", respaldo([COLON]))).toContain("costo de entrega");
    expect(graves("Con la promoción, D'CASA te abona $20 del envío a Colón.", respaldo([COLON]))).toContain("costo de entrega");
    // Con el mínimo, sí; y el precio normal pasa solo.
    expect(graves("Si tu compra pasa de $200, el envío a Villa Lucre es gratis.", respaldo([VILLA_LUCRE]))).toEqual([]);
    expect(graves("En compras de más de $200, el envío a Colón te queda en $70.", respaldo([COLON]))).toEqual([]);
    expect(graves("El envío a Colón cuesta $90.", respaldo([COLON]))).toEqual([]);
  });

  it("F6 en inglés, igual", () => {
    for (const t of ["Shipping to Colón: $20.", "Delivery runs $20.", "You'd pay $20 for delivery.", "It's $20 for the delivery."]) {
      expect(graves(t, respaldo([COLON])), t).toContain("costo de entrega");
    }
    expect(graves("Shipping to Colón costs $90.", respaldo([COLON]))).toEqual([]);
  });

  it("F7 / M2 el ITBMS del envío es el que dice la herramienta: se quita si no lo lleva y se pone si lo lleva", () => {
    expect(asegurarItbms("El envío a Villa Lucre cuesta $15 + ITBMS.", new Set(), respaldo([VILLA_LUCRE]))).toBe("El envío a Villa Lucre cuesta $15.");
    expect(asegurarItbms("El envío a Villa Lucre cuesta $15 (+ ITBMS).", new Set(), respaldo([VILLA_LUCRE]))).toBe("El envío a Villa Lucre cuesta $15.");
    const conItbms = respaldo([{ ...SIN_PROMOCION, llevaItbms: true }]);
    expect(asegurarItbms("El envío a Costa Inventada cuesta $45.", new Set(), conItbms)).toBe("El envío a Costa Inventada cuesta $45 + ITBMS.");
    expect(asegurarItbms("El envío a Costa Inventada cuesta $45 + ITBMS.", new Set(), conItbms)).toBe("El envío a Costa Inventada cuesta $45 + ITBMS.");
    // El mínimo (que es sin ITBMS) y lo abonado no se tocan.
    expect(asegurarItbms("En compras de más de $200 sin ITBMS, D'CASA te abona $20 del envío.", new Set([200, 20]), conItbms)).toBe(
      "En compras de más de $200 sin ITBMS, D'CASA te abona $20 del envío.",
    );
    // Sin el respaldo de envíos, como siempre: la cifra de un producto lleva «+ ITBMS».
    expect(asegurarItbms("El envío a Villa Lucre cuesta $15.", new Set([15]))).toBe("El envío a Villa Lucre cuesta $15 + ITBMS.");
    expect(asegurarItbms("La lámpara cuesta $15. El envío a Villa Lucre cuesta $15.", new Set([15]), respaldo([VILLA_LUCRE]))).toBe(
      "La lámpara cuesta $15 + ITBMS. El envío a Villa Lucre cuesta $15.",
    );
  });

  it("F8 el precio de un producto igual al del envío, en otra cláusula de la misma oración, lleva su «+ ITBMS»", () => {
    expect(asegurarItbms("El envío cuesta $45 y la mesa $45.", new Set([45]), respaldo([SIN_PROMOCION]))).toBe("El envío cuesta $45 y la mesa $45 + ITBMS.");
  });
});

describe("revisión adversarial: lo que antes se bloqueaba de más ahora pasa (B1…B4, M1)", () => {
  it("B1 envío respaldado y el precio de un producto en la misma oración", () => {
    const r = respaldo([VILLA_LUCRE_APLICA]);
    for (const t of ["El envío es de $15 y la cama cuesta $499 + ITBMS.", "El envío a Villa Lucre sale gratis y la cama vale $499 + ITBMS."]) {
      expect(graves(t, r, [499]), t).toEqual([]);
      expect(quitarGraves(analizar(t, ctx(r, [499])).limpio, ctx(r, [499])), t).toBe(t);
    }
  });

  it("B2 lo abonado dicho como abono pasa aunque todavía no haya compra, si va con la condición", () => {
    expect(graves("En compras de más de $200, el envío cuesta $90 y el abono es de $20.", respaldo([COLON]))).toEqual([]);
    expect(graves("El envío cuesta $90 y el abono es de $20.", respaldo([COLON_APLICA]))).toEqual([]);
  });

  it("B3 el mínimo de la promoción, dicho como mínimo", () => {
    const t = "Para el envío gratis la compra tiene que ser de más de $200, o sea el mínimo del envío gratis es de $200.";
    expect(graves(t, respaldo([VILLA_LUCRE]))).toEqual([]);
    expect(graves("El mínimo para el envío gratis es de $15.", respaldo([VILLA_LUCRE]))).toContain("costo de entrega");
  });

  it("B4 / M1 después de sumar el envío, el total de la cotización dicho como total", () => {
    const r = respaldo([VILLA_LUCRE_APLICA], 855.47);
    for (const t of ["Con el envío, el total de tu cotización es de $855.47.", "Ya te sumé el envío; la cotización sale en $855.47.", "El total con el envío queda en $855.47."]) {
      expect(graves(t, r), t).toEqual([]);
    }
    expect(graves("Con el envío te queda en $855.47.", r)).toContain("costo de entrega");
  });

  it("lo que suma la cotización (la compra no llega al mínimo) y el desglose del envío, como los dice la herramienta", () => {
    const chica = respaldo([lugar({ nombres: ["costa inventada"], normal: 50, minimo: 200, compra: 90, cargos: [{ nombre: "tarifa", monto: 45 }, { nombre: "peaje", monto: 5 }] })]);
    const frase =
      "Envío a Costa Inventada (Santa Prueba, Panamá): $50. Tarifa $45 + peaje $5. La promoción de noviembre es para compras de más de $200 sin ITBMS; " +
      "tu cotización suma $90 sin ITBMS, así que el envío va a su precio normal.";
    expect(analizar(frase, { ...ctx(chica), cifrasConocidas: new Set([5, 45, 50, 90, 200]) }).graves).toEqual([]);
    expect(analizar("El envío a Costa Inventada: tarifa $45 + peaje $5.", { ...ctx(chica), cifrasConocidas: new Set([5, 45]) }).graves).toEqual([]);
    expect(analizar("El envío a Costa Inventada cuesta $45.", { ...ctx(chica), cifrasConocidas: new Set([45]) }).graves.map((g) => g.detalle)).toContain("costo de entrega");
  });

  it("las frases de la herramienta pasan tal cual (con y sin promoción, con abono, con la compra)", () => {
    expect(graves(ENVIOS.villaLucre.frase_para_el_cliente, respaldo([VILLA_LUCRE]))).toEqual([]);
    expect(graves(ENVIOS.colon.frase_para_el_cliente, respaldo([COLON]))).toEqual([]);
    expect(
      graves(
        "El envío a Barrio Norte (Colón) cuesta normalmente $90. Con la promoción de noviembre, como tu compra pasa de $200 sin ITBMS, D'CASA te abona $20 del envío: te queda en $70. La promoción es hasta el 30 de noviembre; después, el envío vuelve a su precio normal.",
        respaldo([COLON_APLICA]),
      ),
    ).toEqual([]);
    expect(graves("Envío a Costa Inventada (Santa Prueba, Panamá): $45.", respaldo([SIN_PROMOCION]))).toEqual([]);
    expect(graves("La promoción de noviembre no aplica cuando la compra lleva colchón, así que el envío va a su precio normal.", respaldo([SIN_PROMOCION]))).toEqual([]);
    // Cambiando las cifras de lugar, no: lo abonado no es lo que queda.
    expect(graves("En compras de más de $200, D'CASA te abona $70 del envío: te queda en $20.", respaldo([COLON]))).toContain("costo de entrega");
  });
});

describe("más formas de decirlo (sondas de la revisión)", () => {
  it("«tú pagas» sigue hablando del envío (no es «tu cama»); lo que pone D'CASA es un ahorro", () => {
    const r = respaldo([COLON_APLICA]);
    expect(graves("El envío normalmente cuesta $90; con la promoción, D'CASA pone $20 y tú pagas $70.", r)).toEqual([]);
    expect(graves("El envío normalmente cuesta $90; con la promoción, D'CASA pone $70 y tú pagas $20.", r)).toContain("costo de entrega");
    expect(graves("El envío a Colón cuesta $90 y tu cama cuesta $499 + ITBMS.", r, [499])).toEqual([]);
  });

  it("«incluido»: el envío incluido en el total no es un «gratis»; «flete incluido» sí", () => {
    expect(graves("El total es de $855.47, con el envío incluido.", respaldo([COLON_APLICA], 855.47))).toEqual([]);
    expect(graves("El envío a Colón va incluido.", respaldo([COLON_APLICA]))).toContain("entrega o flete gratis");
    expect(graves("Flete incluido.", respaldo([COLON_APLICA]))).toContain("entrega o flete gratis");
  });

  it("una oración que sigue a la del envío y habla de la promoción también se revisa", () => {
    expect(graves("El envío a Colón cuesta $90. Con la promoción te queda en $20.", respaldo([COLON_APLICA]))).toContain("costo de entrega");
    expect(graves("El envío a Colón cuesta $90. Con la promoción te queda en $70.", respaldo([COLON_APLICA]))).toEqual([]);
    expect(graves("El envío a Colón cuesta $90. La cama Queen cuesta $499 + ITBMS.", respaldo([COLON_APLICA]), [499])).toEqual([]);
    expect(quitarGraves("El envío a Colón cuesta $90. Con la promoción te queda en $20. ¿Te lo sumo?", ctx(respaldo([COLON_APLICA])))).toBe(
      "El envío a Colón cuesta $90. ¿Te lo sumo?",
    );
  });
});

describe("el respaldo lo arma Odoo y el modelo no lo ve", () => {
  it("tomarRespaldoDeEnvio anota cada lugar con sus cifras y el total, y lo quita del resultado", () => {
    const reg = new RegistroDelTurno();
    const visto = tomarRespaldoDeEnvio(
      {
        estado: "precio",
        respaldo_envio: {
          lugares: [
            { nombres: ["Villa Lucre", "José Domingo Espinar", 3], normal: 15, final: 0, ahorro: 15, gratis: true, condicional: true, minimo: 200, compra: null, cargos: [{ nombre: "Peaje", monto: 5 }, { nombre: "x", monto: -1 }], lleva_itbms: false },
            "no es un lugar",
          ],
          total: 855.47,
        },
      },
      reg,
    ) as Record<string, unknown>;
    expect(visto).toEqual({ estado: "precio" });
    expect(reg.envio.lugares).toEqual([
      { nombres: ["villa lucre", "jose domingo espinar"], normal: 15, final: 0, ahorro: 15, gratis: true, condicional: true, minimo: 200, compra: null, cargos: [{ nombre: "peaje", monto: 5 }], llevaItbms: false },
    ]);
    expect(reg.envio.total).toBe(855.47);
    const otro = new RegistroDelTurno();
    expect(tomarRespaldoDeEnvio({ estado: "aparte" }, otro)).toEqual({ estado: "aparte" });
    expect(otro.envio).toEqual({ lugares: [], total: null });
    tomarRespaldoDeEnvio({ respaldo_envio: { lugares: [{ nombres: ["x"], normal: -3, final: Number.NaN, ahorro: "20" }] } }, otro);
    expect(otro.envio.lugares[0]).toMatchObject({ normal: null, final: null, ahorro: null });
  });
});

describe("Juan cotiza el envío con la herramienta y lo dice tal cual", () => {
  const frase = ENVIOS.villaLucre.frase_para_el_cliente;

  it("con cotizar_envio en el turno, el precio y el «gratis» de la promoción salen al cliente", async () => {
    const m = crearMundo();
    const g = m.guion([{ llamadas: [{ nombre: "cotizar_envio", args: { lugar: "Villa Lucre" } }] }, { texto: frase }]);
    await m.conversar("¿cuánto cuesta el envío a Villa Lucre?");
    const texto = m.canal.textos.join("\n");
    expect(texto).toContain("El envío a Villa Lucre (José Domingo Espinar, San Miguelito) cuesta normalmente $15.");
    expect(texto).toContain("D'CASA te regala el envío: te sale gratis (te ahorras $15)");
    expect(texto).toContain("La promoción es hasta el 30 de noviembre; después, el envío vuelve a su precio normal.");
    expect(texto).not.toContain("+ ITBMS");
    expect(g.prompts()[1]).not.toContain("respaldo_envio");
    expect(g.prompts()[1]).toContain("frase_para_el_cliente");
  });

  it("en zona con abono, la frase entera de la herramienta sale tal cual: precio normal, abono de D'CASA y hasta cuándo", async () => {
    const m = crearMundo();
    m.guion([{ llamadas: [{ nombre: "cotizar_envio", args: { lugar: "Colón" } }] }, { texto: ENVIOS.colon.frase_para_el_cliente }]);
    await m.conversar("¿y a Colón?");
    expect(m.canal.textos.join("\n")).toContain(ENVIOS.colon.frase_para_el_cliente);
  });

  it("el abono dicho con otras palabras pasa si va como ahorro y con la condición", async () => {
    const m = crearMundo();
    m.guion([
      { llamadas: [{ nombre: "cotizar_envio", args: { lugar: "Colón" } }] },
      { texto: "El envío a Colón cuesta $90 y, si tu compra pasa de $200, el envío te sale $20 más barato." },
    ]);
    await m.conversar("¿y a Colón?");
    expect(m.canal.textos.join("\n")).toContain("el envío te sale $20 más barato");
  });

  it("el modelo reformula con las cifras de la herramienta y pasa", async () => {
    const m = crearMundo();
    m.guion([{ llamadas: [{ nombre: "cotizar_envio", args: { lugar: "Colón" } }] }, { texto: "El envío a Barrio Norte cuesta $90. Con la promoción, si tu compra pasa de $200 sin ITBMS, te queda en $70." }]);
    await m.conversar("¿y a Colón?");
    expect(m.canal.textos.join("\n")).toContain("El envío a Barrio Norte cuesta $90. Con la promoción, si tu compra pasa de $200 sin ITBMS, te queda en $70.");
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
    expect(m.canal.textos.join("\n")).not.toContain("$50");
  });

  it("en zona con abono, decir «envío gratis» no pasa (la herramienta no lo dijo)", async () => {
    const m = crearMundo();
    m.guion([{ llamadas: [{ nombre: "cotizar_envio", args: { lugar: "Colón" } }] }, { texto: "El envío es gratis a Colón con la promoción. ¿Te lo sumo?" }]);
    await m.conversar("¿y a Colón?");
    expect(m.canal.textos.join("\n")).not.toMatch(/envío es gratis/i);
  });

  it("C1 dos lugares en un turno: el precio de Villa Lucre no sale como el de Colón", async () => {
    const m = crearMundo();
    m.guion([
      { llamadas: [{ nombre: "cotizar_envio", args: { lugar: "Villa Lucre" } }, { nombre: "cotizar_envio", args: { lugar: "Colón" } }] },
      { texto: "El envío a Colón cuesta $15 y el envío es gratis con la promoción." },
    ]);
    await m.conversar("¿cuánto cuesta el envío a Villa Lucre y a Colón?");
    const texto = m.canal.textos.join("\n");
    expect(texto).not.toContain("El envío a Colón cuesta $15");
    expect(texto).not.toContain("es gratis");
  });

  it("C2 Colón: lo abonado dicho como el precio no sale", async () => {
    const m = crearMundo();
    m.guion([{ llamadas: [{ nombre: "cotizar_envio", args: { lugar: "Colón" } }] }, { texto: "El envío a Colón te queda en $20 con la promoción." }]);
    await m.conversar("¿y a Colón?");
    expect(m.canal.textos.join("\n")).not.toContain("$20");
  });

  it("C3 Villa Lucre sin compra: el «gratis» sin la condición del mínimo no sale", async () => {
    const m = crearMundo();
    m.guion([{ llamadas: [{ nombre: "cotizar_envio", args: { lugar: "Villa Lucre" } }] }, { texto: "El envío a Villa Lucre es gratis este mes." }]);
    await m.conversar("¿cuánto el envío a Villa Lucre?");
    expect(m.canal.textos.join("\n")).not.toContain("es gratis este mes");
  });

  it("C4 el turno siguiente, sin herramienta, no puede decir «te sale gratis» ni repetir una cifra del envío", async () => {
    const m = crearMundo();
    m.guion([{ llamadas: [{ nombre: "cotizar_envio", args: { lugar: "Colón" } }] }, { texto: ENVIOS.colon.frase_para_el_cliente }]);
    await m.conversar("¿y a Colón?");
    m.guion([{ texto: "Sí, a Colón el envío te sale gratis. Envío a Colón: $20." }]);
    await m.conversar("¿entonces a Colón me sale gratis?");
    const ultimo = m.canal.textos.at(-1) ?? "";
    expect(ultimo).not.toContain("te sale gratis");
    expect(ultimo).not.toContain("$20");
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

  it("C5 / M1 el total de la cotización con el envío sale (dicho como total)", async () => {
    const m = crearMundo();
    m.guion([
      { llamadas: [{ nombre: "cotizar", args: { lineas: [{ codigo: "CAMA-Q-001" }] } }] },
      { llamadas: [{ nombre: "agregar_envio", args: { lugar_id: 77 } }] },
      { texto: "Listo, ya te sumé el envío a Villa Lucre. Con el envío, el total de tu cotización es de $855.47. El PDF va adjunto." },
    ]);
    await m.conversar("cotízame la cama queen y súmale el envío a Villa Lucre");
    expect(m.canal.textos.join("\n")).toContain("Con el envío, el total de tu cotización es de $855.47.");
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
    // Revisión adversarial: la condición junto al beneficio, lo abonado como ahorro y, con varias cotizaciones, preguntar a cuál.
    expect(como).toContain("el mínimo va en la misma oración que el beneficio");
    expect(como).toContain("lo que D'CASA abona o regala dilo siempre como ahorro");
    expect(como).toMatch(/más de una cotización abierta, pregúntale a cuál \(número y total\) y pásala en cotizacion/);
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

describe("segunda vuelta: solo cuenta como del envío la cifra que la cláusula le atribuye al envío (I-4, P1…P4)", () => {
  const VILLA_APLICA = respaldo([VILLA_LUCRE_APLICA]);

  it("sin herramienta de envíos, un precio de producto conocido en una cláusula que dice entrega o domicilio pasa", () => {
    for (const frase of [
      "La cama está en $499 + ITBMS más el envío, que depende del barrio.",
      "Precio: $499 + ITBMS, entrega a domicilio disponible.",
      "El sofá de $499 + ITBMS también te lo llevamos a domicilio.",
      "Sí, la llevamos a domicilio: la cama cuesta $499 + ITBMS.",
      "La cama queen sale en $499 + ITBMS con entrega a domicilio disponible.",
    ]) {
      expect(graves(frase, undefined, [499]), frase).toEqual([]);
      expect(quitarGraves(frase, ctx(undefined, [499])), frase).toBe(frase);
    }
  });

  it("P1 el subtotal de la cotización dicho como tal, junto al envío", () => {
    expect(graves("Tu cotización suma $499 sin el envío; el envío a Villa Lucre cuesta $15.", VILLA_APLICA, [499])).toEqual([]);
  });

  it("el total con el envío incluido, tras agregar_envio", () => {
    expect(graves("Tu cotización con el envío incluido queda en $855.47.", respaldo([VILLA_LUCRE_APLICA], 855.47), [499])).toEqual([]);
  });

  it("P3 retirarlo en la tienda «sin costo» no es un envío gratis", () => {
    expect(graves("Puedes retirarlo en la tienda sin costo o pedir entrega a domicilio.")).toEqual([]);
  });

  it("P4 el precio del producto en la oración que sigue a la del envío", () => {
    expect(graves("El envío a Villa Lucre te sale gratis (te ahorras $15). Te sale en $499 + ITBMS la cama.", VILLA_APLICA, [499])).toEqual([]);
  });

  it("pero una cifra que no es precio de producto, dicha como costo del envío, sigue sin pasar sin herramienta", () => {
    for (const frase of ["Envío a Colón: $499.", "El envío a Colón te queda en $499.", "Por el envío pagas $499."]) {
      expect(graves(frase), frase).toContain("costo de entrega");
    }
  });
});

describe("segunda vuelta: falsos negativos que ahora no pasan (I-5, I-6, M-5)", () => {
  const COLON_COND = respaldo([COLON]);
  const COLON_SI = respaldo([COLON_APLICA]);
  const VILLA_SI = respaldo([VILLA_LUCRE_APLICA]);

  it("N1 la cifra en la oración que sigue a la del envío, sin palabra de envío", () => {
    expect(graves("El envío a Colón cuesta $90. Pero al final pagas $20.", COLON_COND)).toContain("costo de entrega");
    expect(graves("El envío a Colón cuesta $90. A ti al final son $20.", COLON_COND)).toContain("costo de entrega");
  });

  it("N2 la cifra con otro sujeto en la misma oración", () => {
    expect(graves("El envío a Colón cuesta $90, tu precio final $20.", COLON_COND)).toContain("costo de entrega");
    expect(graves("El envío a Colón cuesta normalmente $90, el monto que pagas $20.", COLON_COND)).toContain("costo de entrega");
  });

  it("N3 un lugar que la herramienta no cotizó no toma el precio del que sí", () => {
    expect(graves("El envío a David cuesta $15.", VILLA_SI)).not.toEqual([]);
    expect(graves("El envío a Bocas del Toro te sale gratis.", VILLA_SI)).not.toEqual([]);
    // El que sí cotizó, con cualquiera de sus nombres, y una fecha con mayúscula no es un lugar.
    expect(graves("El envío a San Miguelito te sale gratis.", VILLA_SI)).toEqual([]);
    expect(graves("El envío a la 24 de Diciembre cuesta $15.", respaldo([lugar({ nombres: ["villa lucre"], normal: 15 })]))).toEqual([]);
    // «hasta» + una fecha no es un lugar.
    expect(graves("El envío a Villa Lucre es gratis hasta Diciembre si tu compra pasa de $200.", respaldo([VILLA_LUCRE]))).toEqual([]);
    expect(graves("Hasta Navidad, el envío a Villa Lucre es gratis si tu compra pasa de $200.", respaldo([VILLA_LUCRE]))).toEqual([]);
  });

  it("N4 otras palabras de envío (mandar, traslado, llevar, hasta <lugar>, sending, getting it to)", () => {
    for (const frase of [
      "Mandarlo a Colón te cuesta $20.",
      "El traslado a Colón cuesta $20.",
      "Que te lo lleven a Colón son $20.",
      "Hasta Colón te sale en $20.",
      "Sending it to Colón costs $20.",
      "Getting it to Colón is $20.",
    ]) {
      expect(graves(frase, COLON_COND), frase).not.toEqual([]);
    }
    // Con la cifra que sí es de ese lugar, pasan.
    expect(graves("Hasta Colón te sale en $90.", COLON_COND)).toEqual([]);
    expect(graves("Mandarlo a Colón te cuesta $90.", COLON_COND)).toEqual([]);
  });

  it("N5 el lugar dicho en la oración anterior", () => {
    expect(graves("Te cuento lo de Colón. El envío cuesta $15.", respaldo([VILLA_LUCRE_APLICA, COLON_APLICA]))).toContain("costo de entrega");
    expect(graves("Te cuento lo de Colón. El envío cuesta $90.", respaldo([VILLA_LUCRE_APLICA, COLON_APLICA]))).toEqual([]);
  });

  it("N6 una palabra de ahorro cerca no vuelve ahorro un costo: manda el verbo de costo", () => {
    for (const frase of [
      "Con el abono, el envío a Colón te cuesta $20.",
      "El envío a Colón, ya con el descuento, sale en $20.",
      "El envío a Colón con el abono te cuesta $20.",
      "Con la rebaja el envío a Colón te queda en $20.",
    ]) {
      expect(graves(frase, COLON_SI), frase).toContain("costo de entrega");
    }
    // Dicho como ahorro (objeto del verbo de ahorro o «abono de»), pasa.
    for (const frase of ["Con la promoción, D'CASA te abona $20 del envío a Colón.", "En el envío a Colón te ahorras $20.", "El abono del envío a Colón es de $20."]) {
      expect(graves(frase, COLON_SI), frase).toEqual([]);
    }
  });

  it("N7 «gratis» dicho de otras formas, sin respaldo", () => {
    for (const frase of ["El envío a Colón te sale en cero.", "El envío a Colón lo paga D'CASA.", "El envío lo pagamos nosotros.", "El envío va por cuenta de D'CASA."]) {
      expect(graves(frase), frase).toContain("entrega o flete gratis");
    }
  });

  it("N8 / M-5 la condición negada no es la condición", () => {
    expect(graves("El envío a Villa Lucre es gratis aunque tu compra no pase de $200.", respaldo([VILLA_LUCRE]))).not.toEqual([]);
    expect(graves("El envío a Villa Lucre es gratis sin importar si tu compra pasa de $200.", respaldo([VILLA_LUCRE]))).not.toEqual([]);
    expect(graves("El envío a Villa Lucre es gratis si tu compra pasa de $200 sin ITBMS.", respaldo([VILLA_LUCRE]))).toEqual([]);
  });
});

describe("segunda vuelta: el sondeo de frases legítimas", () => {
  const VILLA_COND = lugar({ nombres: ["villa lucre", "jose domingo espinar", "san miguelito"], normal: 15, final: 0, ahorro: 15, gratis: true, condicional: true, minimo: 200 });
  const VILLA_SI = { ...VILLA_COND, condicional: false };
  const COLON_COND = lugar({ nombres: ["barrio norte", "colon"], normal: 90, final: 70, ahorro: 20, condicional: true, minimo: 200 });
  const COLON_MONTO = lugar({ nombres: ["barrio norte", "colon"], normal: 90, minimo: 200, compra: 129 });
  const PEAJE = lugar({
    nombres: ["cerro ficticio", "la chorrera"],
    normal: 40,
    final: 0,
    ahorro: 40,
    gratis: true,
    condicional: true,
    minimo: 200,
    cargos: [
      { nombre: "tarifa", monto: 35 },
      { nombre: "peaje", monto: 5 },
    ],
  });
  const c = (envio?: RespaldoDeEnvio): ContextoRevision => ({
    preciosProducto: new Set([499, 799.5]),
    cifrasConocidas: new Set([0, 15, 20, 35, 5, 40, 70, 90, 129, 200, 499, 799.5, 855.47]),
    envio,
  });
  const casos: [RespaldoDeEnvio | undefined, string][] = [
    [respaldo([VILLA_COND]), "El envío a Villa Lucre cuesta normalmente $15, pero si tu compra pasa de $200 sin ITBMS te sale gratis."],
    [respaldo([VILLA_COND]), "A Villa Lucre el envío es $15. Si compras más de $200 sin ITBMS, te lo regalamos (te ahorras $15)."],
    [respaldo([VILLA_COND]), "El envío a Villa Lucre sale en $15. Con la promoción de noviembre, en compras de más de $200 sin ITBMS, es gratis."],
    [respaldo([VILLA_COND]), "El envío a Villa Lucre cuesta $15. Este mes, si tu compra pasa de $200 sin ITBMS, D'CASA te lo regala."],
    [respaldo([VILLA_COND]), "El envío a Villa Lucre cuesta $15 normalmente; con compras de más de $200 sin ITBMS es gratis hasta el 30 de noviembre."],
    [respaldo([VILLA_COND]), "Shipping to Villa Lucre normally costs $15. With the November promotion, on purchases over $200 before ITBMS, D'CASA covers it: it's free (you save $15)."],
    [respaldo([COLON_COND]), "El envío a Barrio Norte cuesta $90. Si tu compra pasa de $200 sin ITBMS, D'CASA te abona $20 y te queda en $70."],
    [respaldo([COLON_COND]), "A Colón el envío normal es de $90; con la promoción (compras de más de $200 sin ITBMS) te abonamos $20 y te queda en $70."],
    [respaldo([COLON_COND]), "El envío a Colón cuesta $90. Con la promoción, si compras más de $200 sin ITBMS, pagas $70."],
    [respaldo([COLON_MONTO]), "El envío a Colón cuesta $90. La promoción es para compras de más de $200 sin ITBMS y tu cotización suma $129, así que el envío va a su precio normal."],
    [respaldo([COLON_MONTO]), "Como tu compra es de $129 (menos de $200), el envío a Colón queda en su precio normal de $90."],
    [respaldo([PEAJE]), "El envío a Cerro Ficticio cuesta normalmente $40 (tarifa $35 + peaje $5). Si tu compra pasa de $200 sin ITBMS, te sale gratis."],
    [respaldo([VILLA_SI], 855.47), "Listo, ya te sumé el envío a Villa Lucre: normalmente cuesta $15, pero con tu compra te sale gratis. El total queda en $855.47 y el PDF va adjunto."],
    [respaldo([VILLA_SI], 855.47), "Listo, te sumé el envío gratis a Villa Lucre; tu cotización queda en $855.47 con todo."],
    [respaldo([VILLA_SI], 855.47), "Tu cotización con el envío incluido queda en $855.47."],
    [respaldo([VILLA_SI], 855.47), "La cama ($799.50 + ITBMS) y el envío gratis a Villa Lucre: total $855.47."],
    [undefined, "Hacemos entregas a domicilio; el costo te lo confirma una vendedora. La cama cuesta $499 + ITBMS."],
    [undefined, "La cama cuesta $499 + ITBMS y el envío te lo cotizo si me dices el barrio."],
    [undefined, "Sí, la llevamos a domicilio: la cama cuesta $499 + ITBMS."],
    [undefined, "Con la promo de noviembre ahorras en el envío; la cama cuesta $499 + ITBMS."],
    [undefined, "Tenemos el sofá en $799.50 + ITBMS; el delivery depende de tu zona."],
  ];

  it("todas pasan enteras", () => {
    for (const [envio, frase] of casos) {
      expect(analizar(frase, c(envio)).graves.map((g) => g.detalle), frase).toEqual([]);
    }
  });

  it("«incluye la entrega» sin herramienta de envíos es prometer el envío gratis: se queda fuera (lo dice una vendedora)", () => {
    expect(analizar("El combo de $799.50 + ITBMS incluye la entrega en La Chorrera.", c()).graves.map((g) => g.detalle)).toContain("entrega o flete gratis");
  });
});

describe("segunda vuelta: en la conversación (C2', C6, W1)", () => {
  it("C2' Colón: «pagas $20» en la oración siguiente a la del envío no sale", async () => {
    const m = crearMundo();
    m.guion([{ llamadas: [{ nombre: "cotizar_envio", args: { lugar: "Colón" } }] }, { texto: "El envío a Barrio Norte cuesta $90. Pero al final pagas $20 si tu compra pasa de $200." }]);
    await m.conversar("¿y a Colón?");
    expect(m.canal.textos.join("\n")).not.toContain("pagas $20");
  });

  it("C6 sin herramienta de envíos: el precio del producto con «entrega a domicilio» sale entero", async () => {
    const m = crearMundo();
    m.guion([{ llamadas: [{ nombre: "buscar_productos", args: { consulta: "cama" } }] }, { texto: "La cama queen sale en $499 + ITBMS con entrega a domicilio disponible." }]);
    await m.conversar("¿cuánto la cama queen? ¿la llevan?");
    expect(m.canal.textos.join(" | ")).toContain("La cama queen sale en $499 + ITBMS con entrega a domicilio disponible.");
  });

  it("W1 / M-4 agregar_envio rechazado (sin_cotizar_envio) → cotizar_envio → agregar_envio otra vez: la segunda llega a Odoo y lo suma", async () => {
    const m = crearMundo();
    let cotizado = false;
    const agregar = m.odoo.manejadores.agregar_envio;
    const cotizar = m.odoo.manejadores.cotizar_envio;
    m.odoo.manejadores.cotizar_envio = (a, o) => {
      cotizado = true;
      return cotizar(a, o);
    };
    m.odoo.manejadores.agregar_envio = (a, o) =>
      cotizado ? agregar(a, o) : { sumado: false, motivo: "sin_cotizar_envio", instruccion: "Llama primero a cotizar_envio con el lugar que dijo el cliente." };
    m.guion([
      { llamadas: [{ nombre: "cotizar", args: { lineas: [{ codigo: "CAMA-Q-001" }] } }] },
      { llamadas: [{ nombre: "agregar_envio", args: { lugar_id: 77 } }] },
      { llamadas: [{ nombre: "cotizar_envio", args: { lugar_id: 77 } }] },
      { llamadas: [{ nombre: "agregar_envio", args: { lugar_id: 77 } }] },
      { texto: "Listo." },
    ]);
    await m.conversar("cotízame la cama y súmale el envío a Villa Lucre");
    expect(m.odoo.llamadas.filter((l) => l.nombre === "agregar_envio")).toHaveLength(2);
    expect(m.odoo.enviosSumados).toEqual([{ lugar_id: 77 }]);
  });

  it("W1 / M-4 lo que sí salió bien se sigue recordando en el turno: el mismo agregar_envio repetido llega una sola vez", async () => {
    const m = crearMundo();
    m.guion([
      { llamadas: [{ nombre: "cotizar", args: { lineas: [{ codigo: "CAMA-Q-001" }] } }] },
      { llamadas: [{ nombre: "agregar_envio", args: { lugar_id: 77 } }] },
      { llamadas: [{ nombre: "agregar_envio", args: { lugar_id: 77 } }] },
      { texto: "Listo." },
    ]);
    await m.conversar("cotízame la cama y súmale el envío a Villa Lucre");
    expect(m.odoo.llamadas.filter((l) => l.nombre === "agregar_envio")).toHaveLength(1);
    expect(m.odoo.enviosSumados).toEqual([{ lugar_id: 77 }]);
  });
});

describe("tercera vuelta: las palabras del costo no sacan la cifra del envío (B-1, I-C)", () => {
  const COLON_SI = respaldo([COLON_APLICA]);
  const DAVID = lugar({ nombres: ["san pablo", "david"], normal: 150, final: 130, ahorro: 20, minimo: 200 });
  const COLON_Y_DAVID = respaldo([COLON_APLICA, DAVID]);

  it("B-1 sin herramienta de envíos, «tiene un costo de», «la tarifa es», «el monto es», «the fee is»… no pasan", () => {
    for (const frase of [
      "El envío a Colón tiene un costo de $499.",
      "El envío a Colón tiene un costo de $90.",
      "El envío tiene un costo de $90.",
      "Para el envío a Colón, la tarifa es $499.",
      "El envío a Colón: la tarifa es de $499.",
      "El envío a Colón con tu compra queda en $499.",
      "El envío a Colón: el monto es $90.",
      "El envío a Colón tiene un valor de $90.",
      "Delivery to Colón has a cost of $90.",
      "Delivery to Colón: the fee is $90.",
    ]) {
      expect(graves(frase, undefined, [499]), frase).toContain("costo de entrega");
    }
  });

  it("B-1 con la herramienta, la cifra de otro lugar (o un precio de producto) dicha con esas palabras no pasa; la de ese lugar, sí", () => {
    for (const frase of [
      "El envío a Colón tiene un costo de $150.",
      "El envío a Colón tiene un valor de $130.",
      "Para el envío a Colón, la tarifa es $150.",
      "El envío a Colón: el monto es $130.",
      "El envío a Colón te sale en $130.",
    ]) {
      expect(graves(frase, COLON_Y_DAVID), frase).toContain("costo de entrega");
    }
    expect(graves("El envío a Colón tiene un costo de $499.", COLON_SI, [499])).toContain("costo de entrega");
    expect(graves("El envío a Colón tiene un costo de $15.", respaldo([VILLA_LUCRE_APLICA]))).toContain("costo de entrega");
    for (const frase of ["El envío a Colón tiene un costo de $90.", "El envío a Colón tiene un costo de $70.", "Para el envío a Colón, la tarifa es $90."]) {
      expect(graves(frase, COLON_Y_DAVID), frase).toEqual([]);
    }
  });

  it("B-1 una oración cuyo sujeto es el costo sigue hablando del envío; la del producto, no", () => {
    expect(graves("El envío a Colón cuesta $90. El costo final es $20.", COLON_SI)).toContain("costo de entrega");
    expect(graves("El envío a Colón cuesta $90. El precio de la cama es $499 + ITBMS.", COLON_SI, [499])).toEqual([]);
  });

  it("I-C «por tu compra», «con tu compra», «queda en el precio de» siguen siendo del envío", () => {
    expect(graves("El envío a Colón, por tu compra, te queda en $130.", COLON_Y_DAVID)).toContain("costo de entrega");
    expect(graves("El envío a Colón queda en el precio de $130.", COLON_Y_DAVID)).toContain("costo de entrega");
    expect(graves("El envío a Colón, por tu compra, te queda en $70.", COLON_Y_DAVID)).toEqual([]);
    // La cotización dicha como tal, sí es de la cotización.
    expect(graves("Tu cotización con el envío incluido queda en $855.47.", respaldo([VILLA_LUCRE_APLICA], 855.47))).toEqual([]);
  });
});

describe("tercera vuelta: un lugar no cotizado, dígase como se diga (I-A)", () => {
  const VILLA_SI = respaldo([VILLA_LUCRE_APLICA]);

  it("no toma el «gratis» ni el precio de Villa Lucre", () => {
    for (const frase of [
      "El envío a David te sale gratis.",
      "El envío a david te sale gratis.",
      "A David el envío te sale gratis.",
      "A David el envío te sale gratis si tu compra pasa de $200 sin ITBMS.",
      "Para David también: el envío te sale gratis.",
      "Te lo mandamos a David gratis.",
      "Llevarlo a Bugaba cuesta $15.",
      "El envío a san pablo cuesta $15.",
    ]) {
      expect(graves(frase, VILLA_SI), frase).not.toEqual([]);
    }
  });

  it("lo que no es un lugar no cuenta: a tu casa, a domicilio, en compras, hasta el 30, a su precio normal…", () => {
    for (const frase of [
      "El envío a Villa Lucre te sale gratis y te lo llevamos a tu casa.",
      "El envío a domicilio a Villa Lucre te sale gratis.",
      "El envío a Villa Lucre te sale gratis hasta el 30 de noviembre.",
      "El envío a San Miguelito te sale gratis, en compras de más de $200 sin ITBMS.",
      "Listo, te sumé el envío gratis a Villa Lucre en tu cotización.",
      "El envío te sale gratis a ti.",
      "El envío a Villa Lucre cuesta $15 hasta tu casa.",
    ]) {
      expect(graves(frase, VILLA_SI), frase).toEqual([]);
    }
    expect(graves("El envío a Colón cuesta $90; con la promoción va a su precio normal.", respaldo([COLON]))).toEqual([]);
  });
});

describe("tercera vuelta: la condición es MÁS de $200 (M-e)", () => {
  it("«$200 o más», «desde $200», «a partir de $200», «al menos $200» no son la condición", () => {
    for (const frase of [
      "El envío a Villa Lucre es gratis si compras $200 o más.",
      "El envío a Villa Lucre es gratis en compras desde $200 sin ITBMS.",
      "El envío a Villa Lucre es gratis a partir de $200 sin ITBMS.",
      "El envío a Villa Lucre es gratis si tu compra es de al menos $200.",
      "El envío a Villa Lucre es gratis en compras de $200 sin ITBMS en adelante.",
    ]) {
      expect(graves(frase, respaldo([VILLA_LUCRE])), frase).toContain("entrega o flete gratis");
    }
    expect(graves("El envío a Villa Lucre es gratis si tu compra pasa de $200 sin ITBMS.", respaldo([VILLA_LUCRE]))).toEqual([]);
    expect(graves("El envío a Villa Lucre es gratis en compras de más de $200 sin ITBMS.", respaldo([VILLA_LUCRE]))).toEqual([]);
  });
});

describe("tercera vuelta: el sondeo (sondeo3)", () => {
  const c = (envio?: RespaldoDeEnvio): ContextoRevision => ({
    preciosProducto: new Set([499, 799.5, 129]),
    cifrasConocidas: new Set([0, 15, 20, 70, 90, 130, 150, 200, 499, 799.5, 129, 855.47, 1298.5]),
    envio,
  });
  const CA = COLON_APLICA;
  const VA = VILLA_LUCRE_APLICA;

  it("las frases legítimas pasan enteras", () => {
    const casos: [RespaldoDeEnvio | undefined, string][] = [
      [undefined, "Sí, la llevamos a domicilio: la cama cuesta $499 + ITBMS."],
      [undefined, "La cama está en $499 + ITBMS más el envío, que depende del barrio."],
      [undefined, "Precio: $499 + ITBMS, entrega a domicilio disponible."],
      [undefined, "Con envío a domicilio, la cama Queen Milán queda en $499 + ITBMS."],
      [undefined, "Hacemos envíos; el sofá Roma está en $799.50 + ITBMS."],
      [undefined, "El sofá Roma ($799.50 + ITBMS) te lo podemos enviar a domicilio."],
      [undefined, "Tu cotización suma $1,298.50 + ITBMS sin el envío."],
      [undefined, "Puedes retirarlo en la tienda sin costo o pedir entrega a domicilio."],
      [undefined, "Delivery is available; the bed is $499 + ITBMS."],
      [undefined, "We deliver to your home: the bed costs $499 + ITBMS."],
      [undefined, "El combo cama + colchón está en $799.50 + ITBMS y la entrega te la confirma una vendedora."],
      [undefined, "Hasta Navidad, el sofá Roma está en $799.50 + ITBMS."],
      [undefined, "Hasta La Chorrera llegan nuestras entregas; la mesa cuesta $129 + ITBMS."],
      [undefined, "Tenemos la cama en $499 + ITBMS hasta agotar existencias, con entrega a domicilio."],
      [respaldo([VA], 855.47), "Tu cotización con el envío incluido queda en $855.47."],
      [respaldo([VA], 855.47), "Listo: envío gratis a Villa Lucre y tu cotización queda en $855.47."],
      [respaldo([VA]), "El envío a Villa Lucre te sale gratis (te ahorras $15). Te sale en $499 + ITBMS la cama."],
      [
        respaldo([COLON]),
        "El envío a Barrio Norte cuesta normalmente $90. Con la promoción de noviembre, en compras de más de $200 sin ITBMS, D'CASA te abona $20 del envío: te queda en $70. La promoción es hasta el 30 de noviembre; después, el envío vuelve a su precio normal. No aplica si la compra lleva colchón.",
      ],
      [
        respaldo([{ ...CA, minimo: null }]),
        "El envío a Barrio Norte (Colón) cuesta normalmente $90. Tu cotización ya tiene la promoción de noviembre, así que D'CASA te abona $20 del envío: te queda en $70.",
      ],
      [
        respaldo([{ ...VA, minimo: null }], 855.47),
        "Ese envío ya estaba en tu cotización S00012. El envío a Villa Lucre (José Domingo Espinar, San Miguelito) cuesta normalmente $15. Tu cotización ya tiene la promoción de noviembre, así que D'CASA te regala el envío: te sale gratis (te ahorras $15). El total de la cotización queda en $855.47.",
      ],
      [respaldo([CA]), "El envío a Colón tiene un costo de $70."],
      [respaldo([CA]), "El envío a Colón tiene un costo de $90."],
    ];
    for (const [envio, frase] of casos) {
      expect(analizar(frase, c(envio)).graves.map((g) => g.detalle), frase).toEqual([]);
    }
  });

  it("las que dicen mal el envío no pasan", () => {
    const casos: [RespaldoDeEnvio, string][] = [
      [respaldo([VILLA_LUCRE]), "El envío a Villa Lucre te sale gratis con la compra."],
      [respaldo([VILLA_LUCRE]), "Con la promoción, el envío a Villa Lucre no tiene costo."],
      [respaldo([COLON]), "El envío a Colón te queda en $70 con tu compra."],
      [respaldo([COLON]), "El envío a Colón cuesta $90 y con la promo, $70."],
      [respaldo([COLON]), "El envío a Colón: $90, o $70 con la promo."],
      [respaldo([CA]), "Ya con el abono de $20, el envío a Colón queda en $20."],
      [respaldo([CA]), "El envío a Colón sale en $90 menos el abono, o sea $20."],
      [respaldo([CA]), "El abono del envío a Colón es de $90."],
    ];
    for (const [envio, frase] of casos) {
      expect(analizar(frase, c(envio)).graves, frase).not.toEqual([]);
    }
  });
});

describe("tercera vuelta: en la conversación (C3-1, C3-2)", () => {
  it("C3-1 el turno siguiente, sin cotizar_envio: «El envío a Colón tiene un costo de $30» (el 30 del «30 de noviembre») no sale", async () => {
    const m = crearMundo();
    m.guion([{ llamadas: [{ nombre: "cotizar_envio", args: { lugar: "Villa Lucre" } }] }, { texto: ENVIOS.villaLucre.frase_para_el_cliente }]);
    await m.conversar("¿cuánto el envío a Villa Lucre?");
    m.guion([{ texto: "El envío a Colón tiene un costo de $30." }, { texto: "El envío a Colón tiene un costo de $30." }]);
    await m.conversar("¿y a Colón?");
    expect(m.canal.textos.join(" | ")).not.toContain("tiene un costo de $30");
  });

  it("C3-2 con cotizar_envio de Villa Lucre, «A David el envío te sale gratis…» no sale; lo de Villa Lucre, sí", async () => {
    const m = crearMundo();
    m.guion([
      { llamadas: [{ nombre: "cotizar_envio", args: { lugar: "Villa Lucre" } }] },
      { texto: "A Villa Lucre el envío cuesta normalmente $15. A David el envío te sale gratis si tu compra pasa de $200 sin ITBMS." },
    ]);
    await m.conversar("¿cuánto el envío a Villa Lucre y a David?");
    const texto = m.canal.textos.join(" | ");
    expect(texto).not.toContain("A David el envío te sale gratis");
    expect(texto).toContain("A Villa Lucre el envío cuesta normalmente $15.");
  });
});
