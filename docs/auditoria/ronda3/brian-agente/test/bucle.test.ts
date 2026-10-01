import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { OdooSimulado } from "../src/nucleo/odoo";
import { ProveedorSimulado } from "../src/proveedores/simulado";
import type { Proveedor, Respuesta, Solicitud } from "../src/nucleo/tipos";
import { armar, DUENA, TOPES, VENDEDORA } from "./apoyo";

describe("bucle de herramientas", () => {
  it("lectura: ejecuta en Odoo con idem = id de la llamada y registra el costo en el libro", async () => {
    const meta = new ProveedorSimulado("meta", [{ herramientas: [["buscar_productos", { texto: "queen" }]] }, "Hay 1 cama Queen disponible."]);
    const { brian, odoo, sql } = armar({ meta });
    const r = await brian.turno(DUENA, "¿Qué camas queen hay?");
    expect(r.texto).toBe("Hay 1 cama Queen disponible.");
    expect(odoo.llamadas).toHaveLength(1);
    expect(odoo.llamadas[0]!.idem).toBe("meta_1_0");
    const filas = sql.ejecutar("SELECT proveedor, modelo, costo_micro FROM uso");
    // 2 llamadas × (1000 × 1,25 + 200 × 4,25) = 2 × 2100 µ$
    expect(filas).toHaveLength(2);
    expect(r.costoMicro).toBe(4200);
    expect(r.modelos).toEqual(["meta/muse-spark-1.3", "meta/muse-spark-1.3"]);
  });

  it("prefijo estable: sistema y herramientas idénticos entre turnos y horas; lo variable va en <contexto>", async () => {
    const meta = new ProveedorSimulado("meta", ["uno", "dos"]);
    const { brian, reloj } = armar({ meta });
    await brian.turno(DUENA, "hola", "Ventas › Pedidos");
    reloj.t += 3 * 3600_000;
    await brian.turno(DUENA, "otra cosa", "Contabilidad");
    const [a, b] = meta.solicitudes;
    expect(JSON.stringify([a!.sistema, a!.herramientas])).toBe(JSON.stringify([b!.sistema, b!.herramientas]));
    expect(a!.sistema).not.toMatch(/\d{2}:\d{2}|Dueña|Ventas/);
    const ultimo = b!.mensajes[b!.mensajes.length - 1]!;
    expect(ultimo.rol === "user" && ultimo.texto).toMatch(/<contexto>[\s\S]*13:00[\s\S]*Contabilidad/);
  });

  it("idempotencia: si el modelo repite el mismo id de llamada, Odoo no ejecuta dos veces", async () => {
    let n = 0;
    const repetidor: Proveedor = {
      id: "meta",
      async chatear(s: Solicitud): Promise<Respuesta> {
        n++;
        const base = { proveedor: "meta", modelo: s.modelo, uso: { entrada: 10, salida: 1, cacheLectura: 0, cacheEscritura: 0 }, fin: "herramientas" as const };
        if (n <= 2) return { ...base, texto: "", llamadas: [{ id: "MISMO", nombre: "crear_cotizacion", argumentos: { cliente_id: 7, lineas: [{ producto_id: 1, cantidad: 1 }] } }] };
        return { ...base, fin: "fin", texto: "Cotización creada.", llamadas: [] };
      },
    };
    const { brian, odoo } = armar({ meta: repetidor });
    await brian.turno(DUENA, "cotiza una cama para el 6555-1234");
    expect(odoo.cotizaciones).toHaveLength(1);
    expect(odoo.llamadas.filter((l) => l.metodo === "create")).toHaveLength(1);
  });

  it("perfil: a la vendedora no se le ofrece ni se le ejecuta registrar_pago", async () => {
    const meta = new ProveedorSimulado("meta", [{ herramientas: [["registrar_pago", { factura: "F1", monto: 10, diario: "banco" }]] }, "No puedo."]);
    const { brian, odoo } = armar({ meta });
    const r = await brian.turno(VENDEDORA, "cobra 10 a F1");
    expect(meta.solicitudes[0]!.herramientas.map((h) => h.name)).not.toContain("registrar_pago");
    expect(r.pendientes).toHaveLength(0);
    expect(odoo.pagos).toHaveLength(0);
  });

  it("valida argumentos: campo no permitido vuelve como error al modelo, no a Odoo", async () => {
    const meta = new ProveedorSimulado("meta", [{ herramientas: [["buscar_productos", { texto: "x", sudo: true }]] }, "ok"]);
    const { brian, odoo } = armar({ meta });
    await brian.turno(DUENA, "x");
    expect(odoo.llamadas).toHaveLength(0);
    const tool = meta.solicitudes[1]!.mensajes.find((m) => m.rol === "tool");
    expect(tool && tool.rol === "tool" && tool.error).toBe(true);
  });
});

describe("confirmación humana de acciones sensibles", () => {
  const pedirCobro = () => new ProveedorSimulado("meta", [{ texto: "Preparo el cobro.", herramientas: [["registrar_pago", { factura: "F-00821", monto: 50, diario: "banco" }]] }]);

  it("crea la tarjeta con el resumen resuelto, NO ejecuta, y no gasta otra llamada al modelo", async () => {
    const meta = pedirCobro();
    const { brian, odoo } = armar({ meta });
    const r = await brian.turno(DUENA, "registra 50 a la F-00821 por banco");
    expect(r.pendientes).toHaveLength(1);
    expect(r.pendientes[0]!.resumen).toBe("Registrar un cobro de $50.00 a la factura F-00821 (diario: banco).");
    expect(r.texto).toMatch(/Necesito tu confirmación/);
    expect(odoo.pagos).toHaveLength(0);
    expect(meta.solicitudes).toHaveLength(1);
  });

  it("confirmar ejecuta una sola vez; repetir devuelve el mismo resultado sin volver a Odoo", async () => {
    const { brian, odoo } = armar({ meta: pedirCobro() });
    const { pendientes } = await brian.turno(DUENA, "cobra");
    const id = pendientes[0]!.id;
    const a = await brian.confirmar(DUENA, id, true);
    const b = await brian.confirmar(DUENA, id, true);
    expect(a).toMatchObject({ estado: "ejecutada", repetida: false });
    expect(b).toMatchObject({ estado: "ejecutada", repetida: true });
    expect(odoo.pagos).toHaveLength(1);
    expect(odoo.llamadas.filter((l) => l.metodo === "registrar")[0]!.idem).toBe(pendientes[0]!.llamadaId);
  });

  it("dos confirmaciones simultáneas: una ejecuta y la otra ve «en_curso»", async () => {
    const { brian, odoo } = armar({ meta: pedirCobro() });
    const { pendientes } = await brian.turno(DUENA, "cobra");
    const [a, b] = await Promise.all([brian.confirmar(DUENA, pendientes[0]!.id, true), brian.confirmar(DUENA, pendientes[0]!.id, true)]);
    expect([a.estado, b.estado].sort()).toEqual(["ejecutada", "en_curso"]);
    expect(odoo.pagos).toHaveLength(1);
  });

  it("caduca a los 10 minutos y ya no se puede ejecutar", async () => {
    const { brian, odoo, reloj } = armar({ meta: pedirCobro() });
    const { pendientes } = await brian.turno(DUENA, "cobra");
    reloj.t += 10 * 60_000 + 1;
    expect(await brian.confirmar(DUENA, pendientes[0]!.id, true)).toEqual({ estado: "caducada" });
    expect(await brian.confirmar(DUENA, pendientes[0]!.id, true)).toEqual({ estado: "caducada" });
    expect(odoo.pagos).toHaveLength(0);
  });

  it("otra persona no puede confirmar; cancelar deja constancia en la conversación", async () => {
    const { brian, odoo, sql } = armar({ meta: pedirCobro() });
    const { pendientes } = await brian.turno(DUENA, "cobra");
    expect(await brian.confirmar(VENDEDORA, pendientes[0]!.id, true)).toEqual({ estado: "no_autorizado" });
    expect(await brian.confirmar(DUENA, pendientes[0]!.id, false)).toEqual({ estado: "cancelada" });
    expect(odoo.pagos).toHaveLength(0);
    const ultimo = sql.ejecutar("SELECT json FROM mensajes ORDER BY n DESC LIMIT 1")[0]!;
    expect(String(ultimo.json)).toMatch(/canceló/);
  });

  it("si Odoo niega el permiso (ACL de la persona), la acción queda «fallida» y no se reintenta sola", async () => {
    const { brian } = armar({ meta: pedirCobro() }, { odoo: new OdooSimulado(false) });
    const { pendientes } = await brian.turno(DUENA, "cobra");
    expect(await brian.confirmar(DUENA, pendientes[0]!.id, true)).toEqual({ estado: "fallida", error: "No tienes permiso en Odoo para esto." });
    expect(await brian.confirmar(DUENA, pendientes[0]!.id, true)).toEqual({ estado: "fallida" });
  });
});

describe("ruteo, respaldo y topes de gasto", () => {
  it("si Meta falla (503), responde Claude Sonnet y el libro lo anota a nombre de Anthropic", async () => {
    const meta = new ProveedorSimulado("meta", [{ error: 503 }]);
    const anthropic = new ProveedorSimulado("anthropic", ["Respondo yo."]);
    const { brian, sql } = armar({ meta, anthropic });
    const r = await brian.turno(DUENA, "hola");
    expect(r.texto).toBe("Respondo yo.");
    expect(sql.ejecutar("SELECT proveedor, modelo, costo_micro FROM uso")).toEqual([
      { proveedor: "anthropic", modelo: "claude-sonnet-5-5", costo_micro: 1000 * 2 + 200 * 10 },
    ]);
  });

  it("un 400 es error nuestro: no se reintenta en otro proveedor", async () => {
    const anthropic = new ProveedorSimulado("anthropic", ["no debería"]);
    const { brian } = armar({ meta: new ProveedorSimulado("meta", [{ error: 400 }]), anthropic });
    const r = await brian.turno(DUENA, "hola");
    expect(r.texto).toMatch(/no puedo hablar/);
    expect(anthropic.solicitudes).toHaveLength(0);
  });

  it("un modelo con precio PENDIENTE no se usa (no se puede medir) y se pasa al siguiente", async () => {
    const openai = new ProveedorSimulado("openai", ["no"]);
    const anthropic = new ProveedorSimulado("anthropic", ["sí"]);
    const config = { rutas: { principal: [{ proveedor: "openai", modelo: "gpt-5.4-mini" }, { proveedor: "anthropic", modelo: "claude-haiku-4-5" }], economica: [] } };
    const { brian } = armar({ openai, anthropic }, { config });
    expect((await brian.turno(DUENA, "hola")).texto).toBe("sí");
    expect(openai.solicitudes).toHaveLength(0);
  });

  it("al 80 % del tope pasa a la ruta económica (Haiku); al 100 % bloquea con mensaje en español", async () => {
    // Tope de la vendedora: 100 000 µ$. Cada llamada a Meta simulada cuesta 2 100 µ$ (1000 entrada + 200 salida).
    const caro = { uso: { entrada: 60_000, salida: 2_000 } }; // 60 000×1,25 + 2 000×4,25 = 83 500 µ$
    const meta = new ProveedorSimulado("meta", [{ texto: "a", ...caro }]);
    const anthropic = new ProveedorSimulado("anthropic", [{ texto: "b", uso: { entrada: 15_000, salida: 400 } }, "c"]);
    const { brian } = armar({ meta, anthropic }, { topes: TOPES });
    expect((await brian.turno(VENDEDORA, "uno")).modelos).toEqual(["meta/muse-spark-1.3"]);
    // 83 500 ≥ 80 % de 100 000 ⇒ económica
    expect((await brian.turno(VENDEDORA, "dos")).modelos).toEqual(["anthropic/claude-haiku-4-5"]);
    // 83 500 + 15 000×1 + 400×5 = 100 500 ≥ 100 000 ⇒ bloqueo
    const r3 = await brian.turno(VENDEDORA, "tres");
    expect(r3.texto).toMatch(/tope de gasto/);
    expect(r3.modelos).toEqual([]);
    // la dueña (otro tope, y el global va en 100 500 de 5 000 000) sigue por la ruta principal
    expect((await brian.turno(DUENA, "cuatro")).modelos).toEqual(["meta/muse-spark-1.3"]);
  });

  it("disyuntor: tras 3 fallos seguidos de Meta, durante 60 s ni se intenta", async () => {
    const meta = new ProveedorSimulado("meta", [{ error: 503 }, { error: 503 }, { error: 503 }, "meta volvió"]);
    const anthropic = new ProveedorSimulado("anthropic", ["1", "2", "3", "4"]);
    const { brian, reloj } = armar({ meta, anthropic });
    for (let i = 0; i < 4; i++) await brian.turno(DUENA, `m${i}`);
    expect(meta.solicitudes).toHaveLength(3);
    reloj.t += 61_000;
    expect((await brian.turno(DUENA, "m5")).texto).toBe("meta volvió");
  });
});

describe("reglas del libro", () => {
  it("el código del libro no tiene UPDATE ni DELETE sobre `uso` (solo se agrega)", () => {
    const fuente = readFileSync(new URL("../src/nucleo/libro.ts", import.meta.url), "utf8");
    expect(fuente).not.toMatch(/UPDATE\s+uso|DELETE\s+FROM\s+uso/i);
  });
});
