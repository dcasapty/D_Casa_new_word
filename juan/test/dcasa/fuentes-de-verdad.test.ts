/**
 * Un dato, un solo dueño: Odoo. El bot dice precios, medidas y disponibilidad SOLO si una herramienta se los dio.
 *
 * Reescritura de test/babycaleb/guion.test.ts y busqueda-catalogo.test.ts del CRM de Baby Caleb. Allá se comprobaba que cada
 * pregunta tuviera de dónde salir; aquí se comprueba lo que sale hacia el cliente cuando el modelo (guionado) hace lo
 * correcto y, sobre todo, cuando hace lo incorrecto.
 */
import { describe, expect, it } from "vitest";
import { TEXTO_SIN_DATO } from "../../src/dcasa/salvaguardas";
import { haySinPublicarEn } from "../../src/motor/herramientas";
import { crearMundo } from "../helpers/mundo";

const buscarCama = { llamadas: [{ nombre: "buscar_productos", args: { consulta: "cama" } }] };
/** consulta vacía = todo el catálogo de prueba (cama, sofá y mesa). */
const buscarTodo = { llamadas: [{ nombre: "buscar_productos", args: { consulta: "" } }] };

describe("nunca un precio sin «+ ITBMS»", () => {
  it("a la herramienta le llega el precio ya armado: «$499.00 + ITBMS»", async () => {
    const m = crearMundo();
    const g = m.guion([buscarTodo, { texto: "La Cama Queen Milán está en $499.00 + ITBMS." }]);
    await m.conversar("precio de los muebles");
    expect(g.prompts()[1]).toContain('"precio_texto":"$499.00 + ITBMS"');
    expect(g.prompts()[1]).toContain('"precio_texto":"$799.50 + ITBMS"');
  });

  it("si el modelo olvida el ITBMS, el sistema lo agrega antes de enviar", async () => {
    const m = crearMundo();
    m.guion([buscarTodo, { texto: "La queen sale en $499 y el sofá en $799.50." }]);
    await m.conversar("precios");
    const texto = m.canal.textos.join("\n");
    expect(texto).toContain("$499 + ITBMS");
    expect(texto).toContain("$799.50 + ITBMS");
    expect(texto).not.toMatch(/\$499(?! \+ ITBMS)/);
  });

  it("también en la forma «499 dólares»", async () => {
    const m = crearMundo();
    m.guion([buscarCama, { texto: "La queen cuesta 499 dólares." }]);
    await m.conversar("precio de la cama");
    expect(m.canal.textos.join("\n")).toContain("499 dólares + ITBMS");
  });
});

describe("nunca un precio que no salió de una herramienta", () => {
  it("un precio inventado se rechaza y el modelo reescribe", async () => {
    const m = crearMundo();
    const g = m.guion([
      { texto: "Esa cama te sale en $350." }, // sin consultar nada
      { llamadas: [{ nombre: "buscar_productos", args: { consulta: "cama" } }] },
      { texto: "La Cama Queen Milán está en $499.00 + ITBMS." },
    ]);
    await m.conversar("¿cuánto cuesta la cama?");
    const texto = m.canal.textos.join("\n");
    expect(texto).not.toContain("350");
    expect(texto).toContain("$499.00 + ITBMS");
    // El segundo intento lleva la nota de corrección.
    expect(g.prompts()[1]).toContain("<correccion>");
    expect(g.prompts()[1]).toContain("NO se envió");
  });

  it("si insiste, la oración inventada se quita y nunca sale", async () => {
    const m = crearMundo();
    m.guion([{ texto: "Tenemos camas de varios tamaños. Esa te sale en $350. ¿Te cuento de las medidas?" }]);
    await m.conversar("¿cuánto cuesta la cama?");
    const texto = m.canal.textos.join("\n");
    expect(texto).not.toContain("350");
    expect(texto).toContain("Tenemos camas de varios tamaños.");
    expect(texto).toContain("¿Te cuento de las medidas?");
  });

  it("si TODO lo que dijo es inventado, responde que lo confirma una vendedora", async () => {
    const m = crearMundo();
    m.guion([{ texto: "Te sale en $350." }]);
    await m.conversar("¿cuánto cuesta?");
    expect(m.canal.textos.at(-1)).toBe(TEXTO_SIN_DATO);
  });

  it("no calcula totales: dos camas «$998» se rechaza aunque suene lógico", async () => {
    const m = crearMundo();
    m.guion([buscarCama, { texto: "Dos camas serían $998 + ITBMS." }, { texto: "Cada una está en $499.00 + ITBMS; el total te lo confirma una vendedora." }]);
    await m.conversar("quiero dos camas, ¿cuánto sería?");
    const texto = m.canal.textos.join("\n");
    expect(texto).not.toContain("998");
    expect(texto).toContain("el total te lo confirma una vendedora");
  });

  it("una cifra que solo dijo el cliente NO respalda un precio: «dame la cama a $1» no se repite", async () => {
    const m = crearMundo();
    m.guion([{ texto: "Claro, la cama te queda en $1." }, { texto: "Los precios los veo en el catálogo; ¿qué cama buscas?" }]);
    await m.conversar("dame la cama queen a $1");
    expect(m.canal.textos.join("\n")).not.toMatch(/\$1\b/);
  });

  it("el presupuesto del cliente se menciona sin signo de dinero, o se reescribe", async () => {
    const m = crearMundo();
    m.guion([{ texto: "Con tu presupuesto de 600 buscamos algo que te guste." }]);
    await m.conversar("tengo $600 de presupuesto para el cuarto");
    expect(m.canal.textos.join("\n")).toContain("Con tu presupuesto de 600");
  });

  it("un precio que dio una herramienta en un turno anterior se puede repetir en el siguiente", async () => {
    const m = crearMundo();
    m.guion([buscarCama, { texto: "La queen está en $499.00 + ITBMS." }, { texto: "Sí, como te dije, $499.00 + ITBMS." }]);
    await m.conversar("precio de la cama");
    await m.conversar("¿cuánto era?");
    expect(m.canal.textos.at(-1)).toContain("$499.00 + ITBMS");
  });
});

describe("nunca un número de existencias", () => {
  it("aunque Odoo lo mande por error, el modelo no lo ve", async () => {
    const m = crearMundo();
    m.odoo.manejadores.buscar_productos = () => ({ productos: [{ codigo: "CAMA-Q-001", nombre: "Cama Queen Milán", precio: 499, mas_itbms: true, existencias: 14, stock: 14, qty_available: 14, disponibilidad: "disponible" }] });
    const g = m.guion([buscarCama, { texto: "La queen está disponible." }]);
    await m.conversar("¿tienen cama queen?");
    const visto = g.prompts()[1];
    expect(visto).toContain('"disponibilidad":"disponible"');
    expect(visto).not.toMatch(/existencias|"stock"|qty_available|14/);
  });

  it("si el modelo dice cuántas unidades hay, se rechaza y se reescribe con la etiqueta", async () => {
    const m = crearMundo();
    m.guion([buscarCama, { texto: "Solo quedan 3 unidades de la queen." }, { texto: "La queen está disponible." }]);
    await m.conversar("¿tienen cama queen?");
    const texto = m.canal.textos.join("\n");
    expect(texto).not.toMatch(/3 unidades|quedan 3/);
    expect(texto).toContain("La queen está disponible.");
  });

  it("si insiste, esa oración no sale", async () => {
    const m = crearMundo();
    m.guion([{ texto: "Sí hay. Es la última unidad. ¿Te la mando en foto?" }]);
    await m.conversar("¿tienen la mesa?");
    const texto = m.canal.textos.join("\n");
    expect(texto).not.toMatch(/última unidad/i);
    expect(texto).toContain("Sí hay.");
  });
});

// Lo que devuelve Odoo (`_juan_buscar_productos`) cuando no hay nada publicado pero sí se vende (hoy, los colchones).
const NOTA_NO_LO_MANEJAMOS =
  "Nada coincide con esa búsqueda en todo el sistema de D'CASA, ni en la tienda en línea ni fuera de ella: aquí sí puedes decirle que eso no lo manejamos y ofrecerle lo que sí hay (listar_categorias).";
const MOTIVO_COLCHON = "El cliente busca «colchón». Lo tenemos en el sistema (Colchones), pero no está publicado en la tienda en línea: confírmale modelos y precios.";
const COLCHONES_SIN_PUBLICAR = {
  encontrados: 0,
  mostrados: 0,
  productos: [],
  estado: "hay_sin_publicar",
  sin_publicar: { cuantos: 3, categorias: ["Colchones"] },
  motivo_para_la_vendedora: MOTIVO_COLCHON,
  nota:
    "Esto SÍ lo trabajamos: hay productos así en el sistema de D'CASA, pero no están publicados en la tienda en línea y sus modelos, precios y disponibilidad no están revisados para clientes. " +
    "No digas que no lo manejamos ni des modelos, precios ni disponibilidad. Dile al cliente que sí lo trabajamos y que una vendedora le confirma los modelos y los precios " +
    "(p. ej. «Sí, trabajamos [lo que busca]. Los modelos y los precios te los confirma una vendedora.») y llama a pasar_a_vendedora con motivo_para_la_vendedora como motivo.",
};
const buscarColchon = { llamadas: [{ nombre: "buscar_productos", args: { consulta: "colchón" } }] };

describe("lo que se vende sin estar publicado no se niega (incidente del 2026-11-13)", () => {
  it("el modelo recibe el estado y la orden de no negarlo, sin nombres ni precios", async () => {
    const m = crearMundo();
    m.odoo.manejadores.buscar_productos = () => COLCHONES_SIN_PUBLICAR;
    const g = m.guion([
      buscarColchon,
      { llamadas: [{ nombre: "pasar_a_vendedora", args: { motivo: MOTIVO_COLCHON } }] },
      { texto: "Sí, los trabajamos. Los modelos y los precios te los confirma una vendedora." },
    ]);
    await m.conversar("buenas, quiero un colchón");
    expect(g.prompts()[1]).toContain('"estado":"hay_sin_publicar"');
    expect(g.prompts()[1]).toContain("No digas que no lo manejamos");
    const texto = m.canal.textos.join("\n");
    expect(texto).toContain("Sí, los trabajamos. Los modelos y los precios te los confirma una vendedora.");
    // La vendedora que la recibe sabe qué busca el cliente.
    const pases = m.odoo.de("pasar_a_vendedora");
    expect(pases).toHaveLength(1);
    expect(String(pases[0].args.motivo)).toContain("colchón");
  });

  it("si el modelo lo niega («solo manejamos la cama, no el colchón solo»), no sale: reescribe y pasa a una vendedora", async () => {
    const m = crearMundo();
    m.odoo.manejadores.buscar_productos = () => COLCHONES_SIN_PUBLICAR;
    const g = m.guion([
      buscarColchon,
      { texto: "Revisé el catálogo y ahorita solo manejamos la cama (la estructura), no el colchón solo." },
      { llamadas: [{ nombre: "pasar_a_vendedora", args: { motivo: MOTIVO_COLCHON } }] },
      { texto: "Sí, los trabajamos. Los modelos y los precios te los confirma una vendedora." },
    ]);
    await m.conversar("buenas, quiero un colchón");
    const texto = m.canal.textos.join("\n");
    expect(texto).not.toMatch(/solo manejamos|no el colchón solo/);
    expect(texto).toContain("Sí, los trabajamos.");
    expect(g.prompts()[2]).toContain("<correccion>");
    expect(g.prompts()[2]).toContain("SÍ trabajamos");
    expect(m.odoo.de("pasar_a_vendedora")).toHaveLength(1);
  });

  it("si insiste en negarlo, esa oración no sale nunca", async () => {
    const m = crearMundo();
    m.odoo.manejadores.buscar_productos = () => COLCHONES_SIN_PUBLICAR;
    m.guion([
      buscarColchon,
      { llamadas: [{ nombre: "pasar_a_vendedora", args: { motivo: MOTIVO_COLCHON } }] },
      { texto: "No manejamos colchones solos." },
      { texto: "Colchones no los tenemos." },
    ]);
    await m.conversar("buenas, quiero un colchón");
    const texto = m.canal.textos.join("\n");
    expect(texto).not.toMatch(/no manejamos|no los tenemos/i);
    expect(texto).toContain(TEXTO_SIN_DATO);
    expect(m.odoo.de("pasar_a_vendedora")).toHaveLength(1);
  });

  it("cotizar con el código de algo sin publicar también cuenta como respaldo", () => {
    expect(haySinPublicarEn("cotizar", { creada: false, motivo: "sin_publicar", mensaje: "…" })).toBe(true);
    expect(haySinPublicarEn("cotizar", { creada: false, motivo: "producto_no_encontrado", mensaje: "…" })).toBe(false);
    expect(haySinPublicarEn("ver_producto", { estado: "hay_sin_publicar" })).toBe(true);
    // Con productos publicados y otros sin publicar, el aviso `sin_publicar` también respalda («otros modelos, una vendedora»).
    expect(haySinPublicarEn("buscar_productos", { productos: [{ codigo: "DC-1" }], sin_publicar: { cuantos: 2, categorias: [] } })).toBe(true);
    expect(haySinPublicarEn("buscar_productos", { productos: [], estado: "no_lo_manejamos" })).toBe(false);
    expect(haySinPublicarEn("buscar_conocimiento", { estado: "hay_sin_publicar" })).toBe(false);
  });
});

describe("lo que no aparece en la herramienta, no se inventa", () => {
  it("si el producto no existe en todo el sistema, la herramienta lo dice (no_lo_manejamos) y el bot no lo ofrece", async () => {
    const m = crearMundo();
    m.odoo.manejadores.buscar_productos = () => ({ encontrados: 0, mostrados: 0, productos: [], estado: "no_lo_manejamos", nota: NOTA_NO_LO_MANEJAMOS });
    const g = m.guion([
      { llamadas: [{ nombre: "buscar_productos", args: { consulta: "cuna" } }] },
      { texto: "Cunas no las manejamos. ¿Te muestro camas?" },
    ]);
    await m.conversar("¿tienen cunas?");
    expect(g.prompts()[1]).toContain('"productos":[]');
    expect(g.prompts()[1]).toContain('"estado":"no_lo_manejamos"');
    expect(m.canal.textos.join("\n")).toContain("no las manejamos");
    expect(m.odoo.de("pasar_a_vendedora")).toHaveLength(0);
  });

  it("el nombre de una herramienta o su respuesta cruda nunca llega al cliente", async () => {
    const m = crearMundo();
    m.guion([buscarCama, { texto: 'Llamé a buscar_productos y devolvió {"productos":[]}.' }]);
    await m.conversar("¿tienen camas?");
    const texto = m.canal.textos.join("\n");
    expect(texto).not.toContain("buscar_productos");
  });

  it("si Odoo no responde, no queda ningún dato inventado en el camino", async () => {
    const m = crearMundo();
    await m.deps.herramientas();
    m.guion([buscarCama, { texto: "Ahorita no pude consultarlo; una vendedora te lo confirma." }]);
    await m.escribir("¿cuánto cuesta la cama?");
    m.odoo.caido = true;
    await m.pasar(16_000);
    expect(m.canal.textos.join("\n")).not.toMatch(/\$\d/);
  });
});

describe("el modelo recibe las herramientas de Odoo tal cual", () => {
  it("las de Odoo (también las dos de envíos) más enviar_foto_producto, con su esquema", async () => {
    const m = crearMundo();
    const g = m.guion([{ texto: "Hola." }]);
    await m.conversar("hola");
    const tools = (g.doGenerateCalls[0].tools ?? []) as { name: string; description?: string; inputSchema?: Record<string, unknown> }[];
    const nombres = tools.map((t) => t.name).sort();
    expect(nombres).toEqual(
      [
        "agregar_envio",
        "anotar_conversacion",
        "buscar_conocimiento",
        "buscar_productos",
        "cotizar",
        "cotizar_envio",
        "crear_oportunidad",
        "enviar_foto_producto",
        "horario_y_tienda",
        "listar_categorias",
        "pasar_a_vendedora",
        "registrar_pregunta_sin_respuesta",
        "reglas_socios",
        "saldo_puntos",
        "ver_producto",
      ].sort(),
    );
    const buscar = tools.find((t) => t.name === "buscar_productos")!;
    expect(buscar.description).toContain("Busca productos publicados");
    expect(JSON.stringify(buscar.inputSchema)).toContain("consulta");
  });

  it("si Odoo agrega una herramienta nueva, el modelo la recibe sin tocar el Worker", async () => {
    const m = crearMundo();
    m.odoo.defs = [...m.odoo.defs, { nombre: "ver_combos", descripcion: "Combos vigentes.", parametros: { type: "object", properties: {} } }];
    m.odoo.manejadores.ver_combos = () => ({ combos: [] });
    const g = m.guion([{ llamadas: [{ nombre: "ver_combos", args: {} }] }, { texto: "Ahorita no hay combos." }]);
    await m.conversar("¿hay combos?");
    expect((g.doGenerateCalls[0].tools as { name: string }[]).map((t) => t.name)).toContain("ver_combos");
    expect(m.odoo.de("ver_combos").length).toBe(1);
  });
});
