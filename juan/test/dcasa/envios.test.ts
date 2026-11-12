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
 * Revisión adversarial del 2026-11-12: cada escenario del revisor (F1…F8, B1…B4, C1…C5) está aquí con la expectativa al revés.
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
