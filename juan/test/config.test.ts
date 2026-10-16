/**
 * La configuración que edita la dueña en Odoo: normalización (nunca lanza, nunca deja un valor inseguro),
 * caché de 60 s con la última buena como respaldo, horario y mes del negocio (America/Panama, UTC-5 sin cambio de hora).
 */
import { describe, expect, it } from "vitest";
import {
  canalActivo,
  CargadorConfig,
  CONFIG_POR_DEFECTO,
  CONFIG_TTL_MS,
  dentroDeHorario,
  mesDelNegocio,
  normalizarChats,
  modeloValido,
  normalizarConfig,
  normalizarLecciones,
  normalizarPrecios,
  relojDelNegocio,
  type Horario,
} from "../src/config";

describe("chats de Telegram permitidos", () => {
  it("vienen vacíos de fábrica: Telegram no es un canal abierto", () => {
    expect(CONFIG_POR_DEFECTO.telegram_chats).toEqual([]);
    expect(normalizarConfig({}).telegram_chats).toEqual([]);
  });

  it("el interruptor «abierto a cualquiera» viene apagado y solo un true lo enciende", () => {
    expect(CONFIG_POR_DEFECTO.telegram_abierto).toBe(false);
    expect(normalizarConfig({}).telegram_abierto).toBe(false);
    expect(normalizarConfig({ telegram_abierto: true }).telegram_abierto).toBe(true);
    for (const raro of ["true", 1, "si", null]) expect(normalizarConfig({ telegram_abierto: raro }).telegram_abierto).toBe(false);
  });

  it("solo cifras (como texto o número), sin repetir, y lo raro se descarta", () => {
    expect(normalizarChats(["555", 555, " 7013 ", "-100123456", "abc", "12", "", null, {}, "5550"])).toEqual(["555", "7013", "5550"]);
    expect(normalizarChats("555")).toEqual([]);
    expect(normalizarChats(undefined)).toEqual([]);
    expect(normalizarConfig({ telegram_chats: ["555", "x"] }).telegram_chats).toEqual(["555"]);
  });

  it("tiene tope de tamaño", () => {
    const muchos = Array.from({ length: 2000 }, (_, i) => String(100000 + i));
    expect(normalizarChats(muchos)).toHaveLength(500);
  });
});

describe("normalizarConfig: nunca lanza y siempre devuelve algo usable", () => {
  it("basura de cualquier tipo → los valores por defecto del contrato", () => {
    for (const crudo of [null, undefined, 5, "hola", [], [1, 2], true]) {
      expect(normalizarConfig(crudo)).toEqual(CONFIG_POR_DEFECTO);
    }
  });

  it("los valores por defecto son los del contrato (docs/JUAN.md)", () => {
    const d = CONFIG_POR_DEFECTO;
    expect(d.bot_activo_global).toBe(true);
    expect(d.horario).toEqual({ inicio: "08:00", fin: "17:00", dias: [0, 1, 2, 3, 4, 5, 6], zona: "America/Panama" });
    expect(d.seguimiento).toEqual({ primero_horas: 5, segundo_dias: 5, solo_horario_laboral: true, maximo: 2 });
    expect(d.proveedor_ia).toBe("anthropic");
    expect(d.proveedor_respaldo_ia).toBeNull();
    expect(d.pausa_por_defecto_minutos).toBe(120);
  });

  it("la foto de perfil: encendida por defecto, se apaga solo con un «false» de verdad", () => {
    expect(CONFIG_POR_DEFECTO.guardar_foto_perfil).toBe(true);
    expect(normalizarConfig({}).guardar_foto_perfil).toBe(true);
    expect(normalizarConfig({ guardar_foto_perfil: false }).guardar_foto_perfil).toBe(false);
    for (const raro of ["no", 0, null]) expect(normalizarConfig({ guardar_foto_perfil: raro }).guardar_foto_perfil).toBe(true);
  });

  it("lee lo que Odoo manda y deja lo demás por defecto", () => {
    const c = normalizarConfig({
      nombre_publico: "D'CASA Panamá",
      bot_activo_global: false,
      horario: { inicio: "9:00", fin: "18:30", dias: [0, 1, 2, 3, 4, 5], zona: "America/Panama" },
      seguimiento: { primero_horas: "3", segundo_dias: 4, solo_horario_laboral: false, maximo: 1 },
      presupuesto_ia_mensual_usd: 12.5,
      palabras_prohibidas: ["remate", "  ", 7, "gratis "],
      pausa_por_defecto_minutos: 45,
      mensaje_bienvenida: "  Hola, soy Juan, el asistente automático.  ",
    });
    expect(c.nombre_publico).toBe("D'CASA Panamá");
    expect(c.bot_activo_global).toBe(false);
    expect(c.horario).toEqual({ inicio: "9:00", fin: "18:30", dias: [0, 1, 2, 3, 4, 5], zona: "America/Panama" });
    expect(c.seguimiento).toEqual({ primero_horas: 3, segundo_dias: 4, solo_horario_laboral: false, maximo: 1 });
    expect(c.presupuesto_ia_mensual_usd).toBe(12.5);
    expect(c.palabras_prohibidas).toEqual(["remate", "gratis"]);
    expect(c.pausa_por_defecto_minutos).toBe(45);
    expect(c.mensaje_bienvenida).toBe("Hola, soy Juan, el asistente automático.");
  });

  it("números fuera de rango se recortan; el máximo de seguimientos nunca pasa de 2", () => {
    const c = normalizarConfig({ seguimiento: { maximo: 9, primero_horas: -4, segundo_dias: 99999 }, presupuesto_ia_mensual_usd: -5, pausa_por_defecto_minutos: 0 });
    expect(c.seguimiento.maximo).toBe(2);
    expect(c.seguimiento.primero_horas).toBe(0);
    expect(c.seguimiento.segundo_dias).toBe(365);
    expect(c.presupuesto_ia_mensual_usd).toBe(0);
    expect(c.pausa_por_defecto_minutos).toBe(1);
  });

  it("horario mal formado → el de siempre; días inválidos se descartan", () => {
    const c = normalizarConfig({ horario: { inicio: "mañana", fin: 17, dias: [0, 9, "x", 2, 2, -1], zona: "" } });
    expect(c.horario.inicio).toBe("08:00");
    expect(c.horario.fin).toBe("17:00");
    expect(c.horario.dias).toEqual([0, 2]);
    expect(c.horario.zona).toBe("America/Panama");
    expect(normalizarConfig({ horario: { dias: [] } }).horario.dias).toEqual([0, 1, 2, 3, 4, 5, 6]);
  });

  it("canales_activos: solo canales conocidos y solo booleanos", () => {
    const c = normalizarConfig({ canales_activos: { telegram: false, messenger: true, whatsapp_qr: "sí", tiktok: true } });
    expect(c.canales_activos).toEqual({ telegram: false, messenger: true });
  });
});

describe("canalActivo: qué arranca encendido si Odoo no dice nada", () => {
  it("Telegram y WhatsApp QR sí; WhatsApp Cloud, Messenger e Instagram NO", () => {
    const c = normalizarConfig({});
    expect(canalActivo(c, "telegram")).toBe(true);
    expect(canalActivo(c, "whatsapp_qr")).toBe(true);
    expect(canalActivo(c, "whatsapp_cloud")).toBe(false);
    expect(canalActivo(c, "messenger")).toBe(false);
    expect(canalActivo(c, "instagram")).toBe(false);
  });

  it("lo que diga Odoo manda, en los dos sentidos", () => {
    const c = normalizarConfig({ canales_activos: { telegram: false, whatsapp_cloud: true } });
    expect(canalActivo(c, "telegram")).toBe(false);
    expect(canalActivo(c, "whatsapp_cloud")).toBe(true);
  });
});

describe("proveedor de IA y modelos", () => {
  it("por defecto Claude: Haiku rápido, Sonnet inteligente", () => {
    const c = normalizarConfig({});
    expect([c.proveedor_ia, c.modelo_rapido, c.modelo_inteligente]).toEqual(["anthropic", "claude-haiku-4-5", "claude-sonnet-5-5"]);
  });

  it("Meta: si Odoo no dice modelo, el estándar (nunca el contributor)", () => {
    const c = normalizarConfig({ proveedor_ia: "meta" });
    expect([c.modelo_rapido, c.modelo_inteligente]).toEqual(["muse-spark-1.3", "muse-spark-1.3"]);
  });

  it("un modelo con la forma de OTRO proveedor se descarta (Odoo no apunta al Worker a cualquier parte)", () => {
    expect(modeloValido("anthropic", "claude-haiku-4-5")).toBe("claude-haiku-4-5");
    expect(modeloValido("anthropic", "muse-spark-1.3")).toBe("");
    expect(modeloValido("meta", "claude-haiku-4-5")).toBe("");
    expect(modeloValido("meta", "muse-spark-1.3-contributor")).toBe("muse-spark-1.3-contributor");
    expect(modeloValido("openai", "gpt-5-mini")).toBe("gpt-5-mini");
    expect(modeloValido("openai", "https://malo.example/x")).toBe("");
    expect(modeloValido("anthropic", 42)).toBe("");
    expect(normalizarConfig({ proveedor_ia: "meta", modelo_rapido: "claude-haiku-4-5" }).modelo_rapido).toBe("muse-spark-1.3");
  });

  it("proveedor desconocido → Claude; mayúsculas y espacios no estorban", () => {
    expect(normalizarConfig({ proveedor_ia: "gemini" }).proveedor_ia).toBe("anthropic");
    expect(normalizarConfig({ proveedor_ia: " Meta " }).proveedor_ia).toBe("meta");
  });

  it("el respaldo no puede ser el mismo que el principal; sin respaldo no hay modelos de respaldo", () => {
    expect(normalizarConfig({ proveedor_ia: "anthropic", proveedor_respaldo_ia: "anthropic" }).proveedor_respaldo_ia).toBeNull();
    const c = normalizarConfig({ proveedor_ia: "meta", proveedor_respaldo_ia: "anthropic", modelo_rapido_respaldo: "claude-haiku-4-5", modelo_inteligente_respaldo: "claude-sonnet-5-5" });
    expect([c.proveedor_respaldo_ia, c.modelo_rapido_respaldo, c.modelo_inteligente_respaldo]).toEqual(["anthropic", "claude-haiku-4-5", "claude-sonnet-5-5"]);
    const sin = normalizarConfig({ proveedor_ia: "meta", modelo_rapido_respaldo: "claude-haiku-4-5" });
    expect([sin.proveedor_respaldo_ia, sin.modelo_rapido_respaldo]).toEqual([null, ""]);
  });
});

describe("precios_ia", () => {
  it("acepta español e inglés, números o texto, con o sin precios de caché", () => {
    expect(
      normalizarPrecios({
        "muse-spark-1.3": { entrada: 1.25, salida: "4.25", entrada_cache: 0.15 },
        "claude-haiku-4-5": { input: 1, output: 5, cache_read: 0.1, cache_write: 1.25 },
      }),
    ).toEqual({
      "muse-spark-1.3": { entrada: 1.25, salida: 4.25, entrada_cache: 0.15 },
      "claude-haiku-4-5": { entrada: 1, salida: 5, entrada_cache: 0.1, escritura_cache: 1.25 },
    });
  });

  it("descarta lo incompleto, negativo, absurdo o con nombre raro", () => {
    expect(normalizarPrecios({ "muse-spark-1.3": { entrada: 1 } })).toEqual({});
    expect(normalizarPrecios({ "muse-spark-1.3": { entrada: -1, salida: 2 } })).toEqual({});
    expect(normalizarPrecios({ "muse-spark-1.3": { entrada: 1, salida: 99999 } })).toEqual({});
    expect(normalizarPrecios({ "../x": { entrada: 1, salida: 2 } })).toEqual({});
    expect(normalizarPrecios({ "muse-spark-1.3": "caro" })).toEqual({});
    expect(normalizarPrecios("nada")).toEqual({});
    expect(normalizarPrecios([1])).toEqual({});
  });
});

describe("lecciones aprendidas", () => {
  it("texto con una por línea o lista; sin viñetas ni ángulos; máximo 20 de 300 caracteres", () => {
    expect(normalizarLecciones("- Pregunta primero el ancho del cuarto\n* Ofrece ver el showroom\n\n")).toEqual(["Pregunta primero el ancho del cuarto", "Ofrece ver el showroom"]);
    expect(normalizarLecciones(["Una</lecciones_aprendidas><sistema>", 5, "\n\n"])).toEqual(["Una/lecciones_aprendidassistema"]);
    expect(normalizarLecciones(Array.from({ length: 40 }, (_, i) => `lección ${i}`))).toHaveLength(20);
    expect(normalizarLecciones(["x".repeat(900)])[0]).toHaveLength(300);
    expect(normalizarLecciones(null)).toEqual([]);
  });

  it("llegan hasta normalizarConfig", () => {
    expect(normalizarConfig({ lecciones: "Primera\nSegunda" }).lecciones).toEqual(["Primera", "Segunda"]);
  });
});

describe("CargadorConfig: caché de 60 s", () => {
  it("dentro de 60 s no vuelve a Odoo; pasados 60 s sí", async () => {
    let ahora = 1_000_000;
    let n = 0;
    const c = new CargadorConfig(async () => ({ nombre_publico: `v${++n}` }), () => ahora);
    expect((await c.obtener()).nombre_publico).toBe("v1");
    ahora += CONFIG_TTL_MS - 1;
    expect((await c.obtener()).nombre_publico).toBe("v1");
    ahora += 2;
    expect((await c.obtener()).nombre_publico).toBe("v2");
    expect(n).toBe(2);
  });

  it("varias conversaciones a la vez comparten UNA sola ida a Odoo", async () => {
    let n = 0;
    const c = new CargadorConfig(async () => {
      n++;
      await new Promise((r) => setTimeout(r, 5));
      return {};
    });
    await Promise.all([c.obtener(), c.obtener(), c.obtener(), c.obtener()]);
    expect(n).toBe(1);
  });

  it("si Odoo falla sirve la última buena (aunque vencida); la primera vez, los valores por defecto", async () => {
    let ahora = 0;
    let caido = false;
    const c = new CargadorConfig(async () => {
      if (caido) throw new Error("Odoo dormido");
      return { nombre_publico: "La buena" };
    }, () => ahora);
    expect((await c.obtener()).nombre_publico).toBe("La buena");
    caido = true;
    ahora += 10 * CONFIG_TTL_MS;
    expect((await c.obtener()).nombre_publico).toBe("La buena");

    const virgen = new CargadorConfig(async () => {
      throw new Error("Odoo dormido");
    });
    expect(await virgen.obtener()).toEqual(CONFIG_POR_DEFECTO);
  });

  it("tras un fallo vuelve a intentar en la siguiente pregunta (no se queda atascado)", async () => {
    let ahora = 0;
    let caido = true;
    const c = new CargadorConfig(async () => {
      if (caido) throw new Error("x");
      return { nombre_publico: "Ya" };
    }, () => ahora);
    expect((await c.obtener()).nombre_publico).toBe(CONFIG_POR_DEFECTO.nombre_publico);
    caido = false;
    expect((await c.obtener()).nombre_publico).toBe("Ya");
  });
});

describe("horario y mes del negocio (America/Panama = UTC-5)", () => {
  // Lunes a viernes (0 = domingo, como lo publica Odoo).
  const h: Horario = { inicio: "08:00", fin: "17:00", dias: [1, 2, 3, 4, 5], zona: "America/Panama" };
  // 2026-10-09 es viernes.
  const panama = (dia: number, hh: number, mm = 0) => Date.UTC(2026, 9, dia, hh + 5, mm);

  it("hora y día de la semana en la zona del negocio (0 = domingo, igual que los días que publica Odoo)", () => {
    expect(relojDelNegocio("America/Panama", panama(9, 10, 30))).toEqual({ minutosDelDia: 630, dia: 5 }); // viernes
    expect(relojDelNegocio("America/Panama", panama(11, 8))).toEqual({ minutosDelDia: 480, dia: 0 }); // domingo
    expect(relojDelNegocio("America/Panama", panama(12, 0)).dia).toBe(1); // lunes
    expect(relojDelNegocio("America/Panama", panama(10, 12, 0)).dia).toBe(6); // sábado
  });

  it("a las 23:30 UTC del viernes en Panamá todavía son las 18:30 del viernes", () => {
    expect(relojDelNegocio("America/Panama", Date.UTC(2026, 9, 9, 23, 30))).toEqual({ minutosDelDia: 18 * 60 + 30, dia: 5 });
  });

  it("dentro: de 8:00 (incluida) a 17:00 (excluida), solo en los días marcados", () => {
    expect(dentroDeHorario(h, panama(9, 8, 0))).toBe(true);
    expect(dentroDeHorario(h, panama(9, 16, 59))).toBe(true);
    expect(dentroDeHorario(h, panama(9, 17, 0))).toBe(false);
    expect(dentroDeHorario(h, panama(9, 7, 59))).toBe(false);
    expect(dentroDeHorario(h, panama(10, 10, 0))).toBe(false); // sábado
    expect(dentroDeHorario(h, panama(11, 10, 0))).toBe(false); // domingo
    expect(dentroDeHorario(h, panama(12, 10, 0))).toBe(true); // lunes
    expect(dentroDeHorario({ ...h, dias: [0, 1, 2, 3, 4, 5, 6] }, panama(10, 10, 0))).toBe(true);
    // Solo domingos: el 0 de Odoo es el domingo, no el lunes.
    expect(dentroDeHorario({ ...h, dias: [0] }, panama(11, 10, 0))).toBe(true);
    expect(dentroDeHorario({ ...h, dias: [0] }, panama(12, 10, 0))).toBe(false);
  });

  it("el domingo puede cerrar más temprano (decisión de la dueña, 2026-10-16)", () => {
    const todos: Horario = { inicio: "09:00", fin: "18:00", dias: [0, 1, 2, 3, 4, 5, 6], zona: "America/Panama", fin_domingo: "17:00" };
    expect(dentroDeHorario(todos, panama(11, 16, 59))).toBe(true); // domingo
    expect(dentroDeHorario(todos, panama(11, 17, 30))).toBe(false); // domingo, ya cerró
    expect(dentroDeHorario(todos, panama(12, 17, 30))).toBe(true); // lunes
    expect(dentroDeHorario(todos, panama(12, 18, 0))).toBe(false);
  });

  it("la hora del domingo llega de Odoo; mal formada, antes de abrir o sin domingo, no se usa", () => {
    const base = { inicio: "09:00", fin: "18:00", dias: [0, 1, 2, 3, 4, 5, 6], zona: "America/Panama" };
    expect(normalizarConfig({ horario: { ...base, fin_domingo: "17:00" } }).horario.fin_domingo).toBe("17:00");
    expect(normalizarConfig({ horario: base }).horario).not.toHaveProperty("fin_domingo");
    expect(normalizarConfig({ horario: { ...base, fin_domingo: "temprano" } }).horario).not.toHaveProperty("fin_domingo");
    expect(normalizarConfig({ horario: { ...base, fin_domingo: "08:00" } }).horario).not.toHaveProperty("fin_domingo");
    expect(normalizarConfig({ horario: { ...base, dias: [1, 2, 3], fin_domingo: "17:00" } }).horario).not.toHaveProperty("fin_domingo");
  });

  it("una zona inválida no rompe: cae en Panamá", () => {
    expect(relojDelNegocio("Marte/Olympus", panama(9, 10)).minutosDelDia).toBe(600);
  });

  it("mesDelNegocio: el mes cambia a medianoche de Panamá, no de UTC", () => {
    expect(mesDelNegocio("America/Panama", Date.UTC(2026, 9, 31, 23, 0))).toBe("2026-10"); // 18:00 del 31 en Panamá
    expect(mesDelNegocio("America/Panama", Date.UTC(2026, 10, 1, 4, 59))).toBe("2026-10"); // 23:59 del 31 en Panamá
    expect(mesDelNegocio("America/Panama", Date.UTC(2026, 10, 1, 5, 0))).toBe("2026-11");
    expect(mesDelNegocio("zona-mala", Date.UTC(2026, 9, 9))).toMatch(/^2026-(09|10)$/);
  });
});
