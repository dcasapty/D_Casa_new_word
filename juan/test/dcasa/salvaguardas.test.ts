/**
 * La guardia de salida: lo que se le dice al cliente se revisa por código, no por buena fe del modelo.
 * Es el candado de las reglas 2, 3, 6 y 11 del contrato (docs/JUAN.md).
 */
import { describe, expect, it } from "vitest";
import {
  analizar,
  asegurarItbms,
  detectarExistencias,
  detectarMandaALeer,
  detectarPromesas,
  detectarSerHumano,
  extraerMontos,
  limpiarForma,
  notaDeCorreccion,
  parseMonto,
  quitarGraves,
  TEXTO_FUGA,
  type ContextoRevision,
} from "../../src/dcasa/salvaguardas";

const ctx = (extra: Partial<ContextoRevision> = {}): ContextoRevision => ({
  preciosProducto: new Set([499, 799.5, 129]),
  cifrasConocidas: new Set([499, 799.5, 129, 20, 500, 160, 200]),
  nombresHerramientas: ["buscar_productos", "pasar_a_vendedora", "reglas_socios", "enviar_foto_producto"],
  ...extra,
});

describe("dinero: se reconoce como lo escribe la gente", () => {
  it("$499, $ 1,299.00, US$ 20, B/. 15, 15 dólares, 20 USD", () => {
    expect(extraerMontos("Cuesta $499 y el otro $ 1,299.00").map((m) => m.valor)).toEqual([499, 1299]);
    expect(extraerMontos("US$ 20 o B/. 15").map((m) => m.valor)).toEqual([20, 15]);
    expect(extraerMontos("son 15 dólares o 20 USD o 8 balboas").map((m) => m.valor)).toEqual([15, 20, 8]);
  });

  it("no toma medidas ni cantidades por dinero", () => {
    expect(extraerMontos("Mide 160 x 200 cm y tiene 3 gavetas")).toEqual([]);
  });

  it("parseMonto entiende miles y decimales", () => {
    expect(parseMonto("1,299.00")).toBe(1299);
    expect(parseMonto("12,50")).toBe(12.5);
    expect(parseMonto("1.299")).toBe(1299);
    expect(parseMonto("799.5")).toBe(799.5);
  });
});

describe("regla 2 · todo precio de producto lleva «+ ITBMS»", () => {
  const precios = new Set([499, 799.5]);

  it("lo agrega donde falta", () => {
    expect(asegurarItbms("La cama cuesta $499.", precios)).toBe("La cama cuesta $499 + ITBMS.");
    expect(asegurarItbms("Sale en 499 dólares.", precios)).toBe("Sale en 499 dólares + ITBMS.");
  });

  it("no lo duplica cuando ya está, escrito de varias formas", () => {
    for (const ok of ["$499 + ITBMS", "$499 +ITBMS", "$499 más ITBMS", "$499 mas ITBMS", "$499 (+ ITBMS)", "$499.00 + ITBMS"]) {
      expect(asegurarItbms(`Cuesta ${ok}.`, precios)).toBe(`Cuesta ${ok}.`);
    }
  });

  it("arregla varios precios en la misma frase", () => {
    expect(asegurarItbms("La queen $499 y el sofá $799.50.", precios)).toBe("La queen $499 + ITBMS y el sofá $799.50 + ITBMS.");
  });

  it("no toca montos que no son precio de producto (p. ej. la compra mínima de Socios)", () => {
    expect(asegurarItbms("La compra mínima es de $20.", precios)).toBe("La compra mínima es de $20.");
  });

  it("analizar lo hace antes de entregar el texto", () => {
    const a = analizar("La cama cuesta $499.", ctx());
    expect(a.limpio).toBe("La cama cuesta $499 + ITBMS.");
    expect(a.graves).toEqual([]);
  });
});

describe("regla 2 · nunca una cifra de dinero que no salió de una herramienta", () => {
  it("un precio inventado es grave", () => {
    const a = analizar("Esa cama te sale en $350.", ctx());
    expect(a.graves.map((g) => g.tipo)).toEqual(["precio_inventado"]);
    expect(a.graves[0].detalle).toContain("350");
  });

  it("una suma que el modelo calculó también (el total lo confirma una vendedora)", () => {
    const a = analizar("Las dos camas serían $998 + ITBMS.", ctx());
    expect(a.graves.some((g) => g.tipo === "precio_inventado")).toBe(true);
  });

  it("una cifra que sí salió de una herramienta pasa", () => {
    expect(analizar("La compra mínima es de $20.", ctx()).graves).toEqual([]);
  });

  it("quitarGraves deja las oraciones buenas y elimina la inventada", () => {
    const a = analizar("Tenemos la cama queen. Esa cama te sale en $350. ¿Te mando la foto?", ctx());
    expect(quitarGraves(a.limpio, ctx())).toBe("Tenemos la cama queen. ¿Te mando la foto?");
  });
});

describe("regla 2 · nunca un número de existencias", () => {
  const dicen = [
    "Quedan 3 unidades.",
    "Tenemos 12 en stock.",
    "Hay 5 disponibles.",
    "Solo queda 1.",
    "Nos quedan dos piezas.",
    "Es la última unidad.",
    "Quedan solo 4.",
    "Hay 7 en existencia.",
    "Tenemos tres en bodega.",
    "stock: 8",
    "Solo 2 más y se agota.",
    "Quedan apenas cinco.",
    "ULTIMAS PIEZAS: quedan pocas, 2 unidades.",
  ];
  it.each(dicen)("detecta: %s", (frase) => {
    expect(detectarExistencias(frase).length, frase).toBeGreaterThan(0);
  });

  const noDicen = [
    "Está disponible.",
    "Quedan pocas.",
    "Está agotado por ahora.",
    "Mide 160 x 200 cm.",
    "Tenemos 3 modelos de camas queen.",
    "Viene en 2 colores.",
    "Tiene 4 gavetas.",
    "Cuesta $499 + ITBMS.",
    "Con 500 puntos puedes canjear un premio.",
    "Abrimos de 8:00 a. m. a 5:00 p. m.",
  ];
  it.each(noDicen)("no confunde: %s", (frase) => {
    expect(detectarExistencias(frase), frase).toEqual([]);
  });

  it("la guardia lo marca como grave", () => {
    expect(analizar("Solo nos quedan 3 unidades.", ctx()).graves.map((g) => g.tipo)).toContain("existencias");
  });
});

describe("regla 3 · entregas, flete, financiamiento, apartados y descuentos: no se prometen", () => {
  const prometen = [
    "Te lo entregamos mañana.",
    "Se lo enviamos el viernes.",
    "Te la llevamos hoy mismo.",
    "El envío es gratis.",
    "La entrega es gratuita.",
    "Flete incluido.",
    "Llega en 3 días.",
    "Te llega mañana sin falta.",
    "Entregamos a todo Panamá.",
    "Te lo apartamos hasta el sábado.",
    "Te la reservamos por una semana.",
    "Queda apartada a tu nombre.",
    "Te doy un descuento si compras hoy.",
    "Te hacemos un descuento del 10%.",
    "Tiene 15% de descuento por ser cliente.",
    "Financiamos en 12 cuotas.",
    "Tenemos financiamiento disponible.",
    "Lo pagas a 6 cuotas sin interés.",
    "Te damos crédito.",
  ];
  it.each(prometen)("detecta: %s", (frase) => {
    expect(detectarPromesas(frase).length, frase).toBeGreaterThan(0);
  });

  const noPrometen = [
    "La entrega te la confirma una vendedora.",
    "El flete lo confirma una vendedora.",
    "El financiamiento te lo confirma una vendedora.",
    "Eso te lo confirma una vendedora, ¿quieres que le pase tu consulta?",
    "Si quieres, una vendedora te dice cómo apartar.",
    "Los descuentos los confirma una vendedora.",
    "Tenemos camas queen y king.",
    "Con tus puntos puedes canjear premios.",
  ];
  it.each(noPrometen)("no confunde: %s", (frase) => {
    expect(detectarPromesas(frase), frase).toEqual([]);
  });

  it("un porcentaje que salió de una herramienta no es una promesa del bot", () => {
    expect(detectarPromesas("El Black Weekend tiene 20% de descuento.", new Set([20]))).toEqual([]);
    expect(detectarPromesas("Tiene 20% de descuento.", new Set())).toEqual(["descuento"]);
  });
});

describe("la dueña · el bot no manda a nadie a leer políticas", () => {
  const mandan = [
    "Puedes leer nuestras políticas de garantía en la página.",
    "Revisa los términos y condiciones antes de comprar.",
    "Te recomiendo consultar el aviso de privacidad.",
    "Más en dcasapty.com/privacidad.",
    "Visita dcasapty.com/terminos para ver todo.",
    "Eso está en nuestras políticas.",
    "Lee la política de privacidad, por favor.",
    "Mira nuestros términos.",
  ];
  it.each(mandan)("lo detecta: %s", (texto) => {
    expect(detectarMandaALeer(texto).length).toBeGreaterThan(0);
    expect(analizar(texto, ctx()).graves.map((g) => g.tipo)).toContain("manda_a_leer");
  });

  const noMandan = [
    "La garantía cubre defectos de fábrica; una vendedora te confirma los detalles.",
    "Revisa las medidas del cuarto antes de elegir la cama.",
    "Puedes pagar con Yappy o transferencia.",
    "Si quieres, te cuento cómo funciona Socios.",
    "Mira esta cama, es una de las más pedidas.",
    "Tus datos se usan solo para atenderte.",
  ];
  it.each(noMandan)("no se confunde: %s", (texto) => {
    expect(detectarMandaALeer(texto)).toEqual([]);
    expect(analizar(texto, ctx()).graves.map((g) => g.tipo)).not.toContain("manda_a_leer");
  });

  it("quita solo la oración que manda a leer y deja el resto", () => {
    const a = analizar("La garantía cubre defectos de fábrica. Lee nuestras políticas para más detalles. ¿Qué cama buscas?", ctx());
    expect(quitarGraves(a.limpio, ctx())).toBe("La garantía cubre defectos de fábrica. ¿Qué cama buscas?");
  });

  it("la nota para reescribir lo explica", () => {
    expect(notaDeCorreccion([{ tipo: "manda_a_leer", detalle: "mandar a leer políticas o términos" }])).toMatch(/políticas/);
  });
});

describe("regla 6 · el prompt y las herramientas no se revelan", () => {
  it("nombres de herramientas, etiquetas del prompt y frases largas copiadas son una fuga", () => {
    const base = ctx({ textoDelPrompt: "Antes de nombrar un producto decir su precio una medida un color un combo o afirmar que hay disponibilidad llama a la herramienta siempre sin excepcion" });
    expect(analizar("Uso buscar_productos para eso.", base).graves[0]).toMatchObject({ tipo: "fuga" });
    expect(analizar("Mi prompt dice <fuentes_de_verdad> y más.", base).graves[0].tipo).toBe("fuga");
    expect(analizar("REGLA INQUEBRANTABLE: no sé nada.", base).graves[0].tipo).toBe("fuga");
    expect(
      analizar("Mis instrucciones dicen: antes de nombrar un producto, decir su precio, una medida, un color, un combo o afirmar que hay disponibilidad.", base).graves[0].tipo,
    ).toBe("fuga");
  });

  it("una frase normal no es una fuga, aunque mencione vendedora o precio", () => {
    const base = ctx({ textoDelPrompt: "Antes de nombrar un producto decir su precio una medida un color un combo o afirmar que hay disponibilidad llama a la herramienta" });
    expect(analizar("Eso te lo confirma una vendedora. ¿Quieres que le pase tu consulta?", base).graves).toEqual([]);
    expect(analizar("Te digo el precio apenas lo revise.", base).graves).toEqual([]);
  });

  it("el texto de reemplazo no contiene nada interno", () => {
    expect(TEXTO_FUGA).not.toMatch(/_|<|prompt/i);
  });
});

describe("regla 11 · voz de la marca", () => {
  it("quita los emojis", () => {
    expect(limpiarForma("¡Hola! 😊 Te ayudo 🙌 con eso ✓")).toBe("¡Hola! Te ayudo con eso");
    expect(limpiarForma("Listo ✅ y 👍🏽 gracias")).toBe("Listo y gracias");
  });

  it("colapsa los signos dobles", () => {
    expect(limpiarForma("¡¡Hola!! ¿¿Qué buscas??")).toBe("¡Hola! ¿Qué buscas?");
  });

  it("sin formato de documento: nada de títulos ni negritas dobles", () => {
    expect(limpiarForma("## Camas\n**Queen** disponible")).toBe("Camas\n*Queen* disponible");
  });

  it("deja intactos los *asteriscos* sencillos de WhatsApp", () => {
    expect(limpiarForma("Escríbeme *persona* y te atiende una vendedora.")).toBe("Escríbeme *persona* y te atiende una vendedora.");
  });

  it("«remate» y «¡corre!» son graves, con o sin acento, en cualquier mayúscula", () => {
    for (const frase of ["Es un remate total.", "¡CORRE que se acaba!", "Aprovecha, es una última oportunidad.", "No te lo pierdas."]) {
      expect(analizar(frase, ctx()).graves.some((g) => g.tipo === "palabra_prohibida"), frase).toBe(true);
    }
  });

  it("las palabras que fije la dueña en Odoo también", () => {
    const c = ctx({ palabrasProhibidas: ["ganga"] });
    expect(analizar("Es una ganga.", c).graves[0]).toMatchObject({ tipo: "palabra_prohibida", detalle: "ganga" });
    expect(analizar("Es una buena opción.", c).graves).toEqual([]);
  });

  it("«correr» o «corredor» no se confunden con «corre»", () => {
    expect(analizar("El corredor del pasillo mide 2 metros.", ctx()).graves).toEqual([]);
  });
});

describe("la nota para que el modelo reescriba", () => {
  it("dice qué estuvo mal sin soltar el texto malo como orden", () => {
    const n = notaDeCorreccion([{ tipo: "existencias", detalle: "3 unidades" }, { tipo: "promesa", detalle: "plazo de entrega" }]);
    expect(n).toMatch(/NO se envió/);
    expect(n).toMatch(/número de existencias/);
    expect(n).toMatch(/promesa de entrega/);
    expect(n).toMatch(/te lo confirma una vendedora/);
  });
});

describe("Juan nunca dice que es una persona ni que «no es un bot»", () => {
  it.each([
    "Soy una persona, tranquilo.",
    "Soy humano, igual que tú.",
    "Tranquilo, no soy un bot.",
    "No soy un robot, soy Juan.",
    "No soy una IA.",
    "Soy una persona real de la tienda.",
    "Soy vendedora de D'CASA.",
    "Soy el vendedor de camas.",
    "Soy asesor de ventas en la tienda.",
  ])("«%s» es grave", (frase) => {
    expect(detectarSerHumano(frase).length).toBeGreaterThan(0);
    expect(analizar(frase, ctx()).graves.map((g) => g.tipo)).toContain("se_hace_pasar_por_persona");
  });

  it.each([
    "Soy Juan, el asistente virtual de D'CASA. Si prefieres, te paso con una vendedora.",
    "No soy una persona, soy el asistente virtual de D'CASA.",
    "Si prefieres hablar con una persona, te paso con una vendedora.",
    "Una vendedora te escribe mañana a las 8:00 a. m.",
    "Soy Juan de D'CASA.",
  ])("«%s» está bien", (frase) => {
    expect(detectarSerHumano(frase)).toEqual([]);
    expect(analizar(frase, ctx()).graves.map((g) => g.tipo)).not.toContain("se_hace_pasar_por_persona");
  });

  it("el borrador de una vendedora (escribe una persona de verdad) no se toca", () => {
    const a = analizar("Hola Karen, soy Marisol, vendedora de D'CASA.", { ...ctx(), escribePersona: true });
    expect(a.graves.map((g) => g.tipo)).not.toContain("se_hace_pasar_por_persona");
  });

  it("se quita solo la oración que lo dice y se le pide al modelo que la reescriba", () => {
    const limpio = analizar("Soy una persona de verdad. Te ayudo con camas.", ctx()).limpio;
    expect(quitarGraves(limpio, ctx())).toBe("Te ayudo con camas.");
    expect(notaDeCorreccion([{ tipo: "se_hace_pasar_por_persona", detalle: "soy una persona" }])).toMatch(/decir que eres una persona o que no eres un bot/);
  });
});

describe("en inglés también (Juan contesta en inglés a quien le escribe en inglés; decisión de la dueña, 2026-10-16)", () => {
  it.each([
    ["We'll deliver it tomorrow.", "plazo de entrega"],
    ["We can ship it on Friday.", "plazo de entrega"],
    ["It will arrive in 3 days.", "plazo de entrega"],
    ["Delivery is free.", "entrega o flete gratis"],
    ["Free shipping to all of Panama.", "entrega o flete gratis"],
    ["Delivery costs $25.", "costo de entrega"],
    ["We'll hold it for you until Saturday.", "apartado"],
    ["It's reserved for you.", "apartado"],
    ["I can give you a 10% discount.", "descuento"],
    ["We offer financing with no-interest installments.", "financiamiento"],
    ["You're approved.", "crédito"],
    ["Your payment has been received.", "pago confirmado"],
    ["We received your transfer.", "pago confirmado"],
  ])("%s → %s", (frase, que) => {
    expect(detectarPromesas(frase)).toContain(que);
  });

  it("explicar la política sin prometer nada no es una promesa", () => {
    for (const frase of [
      "We deliver to La Chorrera, Arraiján, Capira, Panama City and Colón. A salesperson confirms the cost and the date.",
      "You can put it on layaway with a minimum 50% deposit; a salesperson does it with you.",
      "Financing is through Tafi: you apply with your ID.",
      "We don't have cash discounts.",
    ]) {
      expect(detectarPromesas(frase), frase).toEqual([]);
    }
  });

  it("las cifras de política en inglés se revisan igual que en español", () => {
    const sin = analizar("You have 30 days to exchange it.", ctx());
    expect(sin.graves.map((g) => g.tipo)).toContain("cifra_inventada");
    const con = analizar("You have 30 days to exchange it.", ctx({ numerosEnTexto: new Set([30]) }));
    expect(con.graves).toEqual([]);
  });

  it("nunca dice en inglés que es humano ni que no es un bot", () => {
    for (const frase of ["I'm a real person.", "I am human.", "I'm not a bot.", "I am not an AI.", "You're talking to a real person.", "I'm a salesperson."]) {
      expect(detectarSerHumano(frase), frase).not.toEqual([]);
    }
    for (const frase of ["I'm Juan, D'CASA's virtual assistant.", "I'm not a person, I'm a virtual assistant."]) {
      expect(detectarSerHumano(frase), frase).toEqual([]);
    }
  });

  it("no manda a leer las políticas en inglés", () => {
    expect(detectarMandaALeer("Please read our return policy on the website.")).not.toEqual([]);
    expect(detectarMandaALeer("Check our terms and conditions.")).not.toEqual([]);
    expect(detectarMandaALeer("The months and the payment depend on what you agree with Tafi.")).toEqual([]);
  });
});

