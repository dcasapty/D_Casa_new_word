/**
 * El cliente de Odoo (docs/JUAN.md → «Worker → Odoo»): rutas del contrato, Bearer, reintentos solo donde es seguro,
 * tolerancia con la forma de la lista de herramientas y con las fechas de `pausada_hasta`.
 */
import { describe, expect, it } from "vitest";
import { aMilisegundosOdoo, CargadorHerramientas, normalizarHerramientas, OdooCliente, OdooError, type DefHerramienta } from "../../src/odoo/cliente";

const TOKEN = "token-de-odoo-de-prueba-0123456789";

interface Llamada {
  url: string;
  metodo: string;
  cabeceras: Record<string, string>;
  cuerpo: any;
  tieneSenal: boolean;
}

/** Un `DCASA` falso: contesta lo que diga el guion (una función, o una lista que se va gastando). */
function dcasaFalso(guion: ((l: Llamada, n: number) => Response | Promise<Response>) | (Response | Error)[]) {
  const llamadas: Llamada[] = [];
  const fetcher = {
    fetch: async (url: string, init?: RequestInit) => {
      const l: Llamada = {
        url,
        metodo: init?.method ?? "GET",
        cabeceras: Object.fromEntries(Object.entries((init?.headers ?? {}) as Record<string, string>)),
        cuerpo: init?.body ? JSON.parse(String(init.body)) : undefined,
        tieneSenal: !!init?.signal,
      };
      llamadas.push(l);
      const n = llamadas.length - 1;
      if (typeof guion === "function") return guion(l, n);
      const r = guion[Math.min(n, guion.length - 1)];
      if (r instanceof Error) throw r;
      return r.clone();
    },
  };
  const esperas: number[] = [];
  const cliente = new OdooCliente(fetcher as any, TOKEN, { dormir: async (ms) => void esperas.push(ms) });
  return { llamadas, esperas, cliente };
}

const ok = (cuerpo: unknown = { ok: true }) => Response.json(cuerpo);
const falla = (estado: number, cuerpo: unknown = { error: "algo pasó" }) => Response.json(cuerpo, { status: estado });

describe("las rutas y la autenticación", () => {
  it("mensaje: POST /dcasa/juan/v1/mensaje con Bearer y el cuerpo del contrato", async () => {
    const { cliente, llamadas } = dcasaFalso([ok({ ok: true, conversacion_id: 7, bot_activo: true, estado: "bot" })]);
    const cuerpo = { canal: "telegram", id_externo: "99", id_mensaje: "tg:1", direccion: "entrante", autor: "cliente", texto: "hola", ts: "2026-10-09T14:00:00Z" } as const;
    const r = await cliente.mensaje(cuerpo);
    expect(r.conversacion_id).toBe(7);
    expect(llamadas[0]).toMatchObject({ metodo: "POST", url: "https://dcasa/dcasa/juan/v1/mensaje", cuerpo });
    expect(llamadas[0].cabeceras.authorization).toBe(`Bearer ${TOKEN}`);
    expect(llamadas[0].cabeceras["content-type"]).toMatch(/application\/json/);
    expect(llamadas[0].tieneSenal).toBe(true);
  });

  it("estado: GET con canal e id_externo en la query (y codificados)", async () => {
    const { cliente, llamadas } = dcasaFalso([ok({ estado: "bot", bot_activo: true })]);
    await cliente.estado("whatsapp_qr", "507 60&26");
    expect(llamadas[0].metodo).toBe("GET");
    expect(llamadas[0].url).toBe("https://dcasa/dcasa/juan/v1/estado?canal=whatsapp_qr&id_externo=507+60%2626");
    expect(llamadas[0].cuerpo).toBeUndefined();
    expect(llamadas[0].cabeceras["content-type"]).toBeUndefined();
  });

  it("config, herramientas, herramienta y seguimiento/hecho usan las rutas del contrato", async () => {
    const { cliente, llamadas } = dcasaFalso(() => ok({ herramientas: [], ok: true, resultado: {} }));
    await cliente.config();
    await cliente.herramientas();
    await cliente.herramienta("buscar_productos", { consulta: "cama" }, 5);
    await cliente.seguimientoHecho({ conversacion_id: 5, numero: 1, resultado: "enviado" });
    expect(llamadas.map((l) => `${l.metodo} ${l.url.replace("https://dcasa/dcasa/juan/v1", "")}`)).toEqual([
      "GET /config",
      "GET /herramientas",
      "POST /herramienta",
      "POST /seguimiento/hecho",
    ]);
    expect(llamadas[2].cuerpo).toEqual({ nombre: "buscar_productos", argumentos: { consulta: "cama" }, conversacion_id: 5 });
    expect(llamadas[3].cuerpo).toEqual({ conversacion_id: 5, numero: 1, resultado: "enviado" });
  });

  it("sin token no sale NINGUNA llamada y el error pide el secreto (por nombre)", async () => {
    const llamadas: unknown[] = [];
    const cliente = new OdooCliente({ fetch: async (...a: unknown[]) => void llamadas.push(a) } as any, "", { dormir: async () => {} });
    const e = (await cliente.estado("telegram", "1").catch((x: OdooError) => x)) as OdooError;
    expect(e).toBeInstanceOf(OdooError);
    expect(e.sinCredenciales).toBe(true);
    expect(e.message).toBe("Falta JUAN_ODOO_TOKEN");
    expect(llamadas).toHaveLength(0);
  });
});

describe("reintentos", () => {
  it("mensaje: un 503 (Odoo despertando) se reintenta una vez, con espera, y la segunda vale", async () => {
    const { cliente, llamadas, esperas } = dcasaFalso([falla(503), ok({ ok: true, conversacion_id: 3 })]);
    const r = await cliente.mensaje({ canal: "telegram", id_externo: "1", id_mensaje: "a", direccion: "entrante", autor: "cliente", texto: "hola", ts: "x" });
    expect(r.conversacion_id).toBe(3);
    expect(llamadas).toHaveLength(2);
    expect(esperas).toHaveLength(1);
  });

  it("mensaje: dos fallos seguidos terminan en error REINTENTABLE (el motor lo encola)", async () => {
    const { cliente, llamadas } = dcasaFalso([falla(502), falla(502)]);
    const e = (await cliente.mensaje({ canal: "telegram", id_externo: "1", id_mensaje: "a", direccion: "entrante", autor: "cliente", texto: "hola", ts: "x" }).catch((x: OdooError) => x)) as OdooError;
    expect(llamadas).toHaveLength(2);
    expect(e).toBeInstanceOf(OdooError);
    expect(e.reintentable).toBe(true);
    expect(e.estado).toBe(502);
  });

  it("un error de red o de plazo (fetch que lanza) cuenta como reintentable, estado 0", async () => {
    const { cliente, llamadas } = dcasaFalso([new DOMException("The operation timed out", "TimeoutError"), new Error("red caída")]);
    const e = (await cliente.estado("telegram", "1").catch((x: OdooError) => x)) as OdooError;
    expect(llamadas).toHaveLength(2);
    expect(e.reintentable).toBe(true);
    expect(e.estado).toBe(0);
  });

  it("un 400/401/404 NO se reintenta (no cambiaría nada) y trae el motivo de Odoo", async () => {
    for (const estado of [400, 401, 403, 404, 422]) {
      const { cliente, llamadas } = dcasaFalso([falla(estado, { error: "canal desconocido" })]);
      const e = (await cliente.estado("telegram", "1").catch((x: OdooError) => x)) as OdooError;
      expect(llamadas, String(estado)).toHaveLength(1);
      expect(e.reintentable).toBe(false);
      expect(e.estado).toBe(estado);
      expect(e.message).toContain("canal desconocido");
    }
  });

  it("el cuerpo de un error que no es JSON se acorta y no rompe", async () => {
    const { cliente } = dcasaFalso([new Response("<html>" + "x".repeat(5000) + "</html>", { status: 500 }), new Response("<html>oops</html>", { status: 500 })]);
    const e = (await cliente.config().catch((x: OdooError) => x)) as OdooError;
    expect(e.message.length).toBeLessThan(400);
  });

  it("herramienta: NUNCA se reintenta sola (una nota o una oportunidad se duplicaría) y el fallo vuelve como dato", async () => {
    const { cliente, llamadas } = dcasaFalso([falla(503), ok({ ok: true, resultado: "ok" })]);
    const r = await cliente.herramienta("anotar_conversacion", { nota: "x" }, 4);
    expect(llamadas).toHaveLength(1);
    expect(r.ok).toBe(false);
    expect(r.error).toMatch(/503/);
  });

  it("herramienta: `ok:false` de Odoo llega con su error; `ok:true` con su resultado", async () => {
    expect(await dcasaFalso([ok({ ok: false, error: "no hay stock de eso" })]).cliente.herramienta("x", {}, null)).toEqual({ ok: false, error: "no hay stock de eso" });
    expect(await dcasaFalso([ok({ ok: true, resultado: { n: 2 } })]).cliente.herramienta("x", {}, null)).toEqual({ ok: true, resultado: { n: 2 } });
    expect(await dcasaFalso([ok({ ok: false })]).cliente.herramienta("x", {}, null)).toEqual({ ok: false, error: "la herramienta falló" });
  });

  it("seguimiento/hecho se reintenta hasta 2 veces (es idempotente)", async () => {
    const { cliente, llamadas } = dcasaFalso([falla(500), falla(500), ok()]);
    await cliente.seguimientoHecho({ conversacion_id: 1, numero: 2, resultado: "descartado", motivo: "el cliente ya compró" });
    expect(llamadas).toHaveLength(3);
  });

  it("escribiendo usa su ruta, manda el aviso tal cual y NO se reintenta (uno tardío no sirve)", async () => {
    const { cliente, llamadas } = dcasaFalso([falla(500), ok()]);
    await expect(cliente.escribiendo({ canal: "telegram", id_externo: "77", activo: true })).rejects.toBeInstanceOf(OdooError);
    expect(llamadas).toHaveLength(1);
    expect(`${llamadas[0].metodo} ${llamadas[0].url.replace("https://dcasa/dcasa/juan/v1", "")}`).toBe("POST /escribiendo");
    expect(llamadas[0].cuerpo).toEqual({ canal: "telegram", id_externo: "77", activo: true });
    expect(llamadas[0].cabeceras.authorization).toBe(`Bearer ${TOKEN}`);
  });

  it("foto-perfil manda la foto a su ruta, se puede repetir una vez y dice si Odoo la guardó", async () => {
    const { cliente, llamadas } = dcasaFalso([falla(502), ok({ ok: true, guardada: true })]);
    const r = await cliente.fotoPerfil({ canal: "telegram", id_externo: "77", mime: "image/jpeg", base64: "QUJD" });
    expect(r).toEqual({ guardada: true });
    expect(llamadas).toHaveLength(2);
    expect(`${llamadas[0].metodo} ${llamadas[0].url.replace("https://dcasa/dcasa/juan/v1", "")}`).toBe("POST /foto-perfil");
    expect(llamadas[0].cuerpo).toEqual({ canal: "telegram", id_externo: "77", mime: "image/jpeg", base64: "QUJD" });
    expect(await dcasaFalso([ok({ ok: true, guardada: false })]).cliente.fotoPerfil({ canal: "telegram", id_externo: "77", mime: "image/jpeg", base64: "QUJD" })).toEqual({ guardada: false });
  });

  it("la espera entre reintentos crece pero tiene techo", async () => {
    const { cliente, esperas } = dcasaFalso([falla(500), falla(500), falla(500)]);
    await cliente.seguimientoHecho({ conversacion_id: 1, numero: 1, resultado: "enviado" }).catch(() => {});
    expect(esperas).toEqual([700, 1400]);
    expect(Math.max(...esperas)).toBeLessThanOrEqual(8000);
  });
});

describe("la lista de herramientas, venga como venga", () => {
  const esquema = { type: "object", properties: { consulta: { type: "string" } }, required: ["consulta"] };

  it("acepta una lista, {herramientas}, {resultado} y {tools}", () => {
    const una = [{ nombre: "buscar_productos", descripcion: "Busca", parametros: esquema }];
    for (const forma of [una, { herramientas: una }, { resultado: una }, { tools: una }]) {
      expect(normalizarHerramientas(forma)).toEqual([{ nombre: "buscar_productos", descripcion: "Busca", parametros: esquema }]);
    }
  });

  it("acepta nombres de campo en inglés (name, description, input_schema, parameters)", () => {
    expect(normalizarHerramientas([{ name: "a", description: "d", input_schema: esquema }, { name: "b", parameters: esquema }]).map((h) => [h.nombre, h.descripcion, h.parametros])).toEqual([
      ["a", "d", esquema],
      ["b", "", esquema],
    ]);
  });

  it("descarta las que no tienen nombre válido y las repetidas; nunca lanza", () => {
    const lista = normalizarHerramientas([{ nombre: "ok_1" }, { nombre: "con espacio" }, { nombre: "" }, { nombre: "ok_1", descripcion: "repetida" }, null, "texto", { nombre: "x".repeat(65) }]);
    expect(lista.map((h) => h.nombre)).toEqual(["ok_1"]);
    expect(normalizarHerramientas(null)).toEqual([]);
    expect(normalizarHerramientas({ otra: 1 })).toEqual([]);
  });

  it("el esquema siempre sale como objeto con `properties` (los modelos lo exigen)", () => {
    expect(normalizarHerramientas([{ nombre: "a" }])[0].parametros).toEqual({ type: "object", properties: {} });
    expect(normalizarHerramientas([{ nombre: "a", parametros: { type: "object" } }])[0].parametros).toEqual({ type: "object", properties: {} });
    expect(normalizarHerramientas([{ nombre: "a", parametros: { properties: { q: { type: "string" } } } }])[0].parametros).toEqual({ type: "object", properties: { q: { type: "string" } } });
    expect(normalizarHerramientas([{ nombre: "a", parametros: { q: { type: "string" } } }])[0].parametros).toEqual({ type: "object", properties: { q: { type: "string" } } });
    expect(normalizarHerramientas([{ nombre: "a", parametros: [1, 2] }])[0].parametros).toEqual({ type: "object", properties: {} });
    expect(normalizarHerramientas([{ nombre: "a", parametros: { type: "string" } }])[0].parametros).toEqual({ type: "object", properties: {} });
  });

  it("`herramientas()` del cliente ya viene normalizada", async () => {
    const { cliente } = dcasaFalso([ok({ herramientas: [{ nombre: "buscar_productos", descripcion: "Busca" }] })]);
    expect(await cliente.herramientas()).toEqual([{ nombre: "buscar_productos", descripcion: "Busca", parametros: { type: "object", properties: {} } }]);
  });
});

describe("CargadorHerramientas", () => {
  const una: DefHerramienta[] = [{ nombre: "a", descripcion: "", parametros: { type: "object", properties: {} } }];
  const otra: DefHerramienta[] = [{ nombre: "b", descripcion: "", parametros: { type: "object", properties: {} } }];

  it("guarda 5 minutos y luego vuelve a pedir", async () => {
    let ahora = 1_000_000;
    let n = 0;
    const c = new CargadorHerramientas(async () => (++n === 1 ? una : otra), () => ahora);
    expect((await c.obtener())[0].nombre).toBe("a");
    ahora += 4 * 60_000;
    expect((await c.obtener())[0].nombre).toBe("a");
    expect(n).toBe(1);
    ahora += 2 * 60_000;
    expect((await c.obtener())[0].nombre).toBe("b");
    expect(n).toBe(2);
  });

  it("si Odoo falla sirve la última lista buena; si nunca hubo, lista vacía (el bot sigue sin herramientas, no se cae)", async () => {
    let ahora = 0;
    let fallar = false;
    const c = new CargadorHerramientas(async () => {
      if (fallar) throw new Error("Odoo dormido");
      return una;
    }, () => ahora);
    expect(await c.obtener()).toEqual(una);
    fallar = true;
    ahora += 10 * 60_000;
    expect(await c.obtener()).toEqual(una);

    const nuevo = new CargadorHerramientas(async () => {
      throw new Error("Odoo dormido");
    }, () => ahora);
    expect(await nuevo.obtener()).toEqual([]);
  });

  it("una lista vacía NO pisa la última buena (casi seguro es un error de Odoo)", async () => {
    let ahora = 0;
    let respuesta: DefHerramienta[] = una;
    const c = new CargadorHerramientas(async () => respuesta, () => ahora);
    await c.obtener();
    respuesta = [];
    ahora += 10 * 60_000;
    expect(await c.obtener()).toEqual(una);
  });
});

describe("aMilisegundosOdoo", () => {
  it("null, vacío o indefinido: sin fecha", () => {
    expect(aMilisegundosOdoo(null)).toBeNull();
    expect(aMilisegundosOdoo(undefined)).toBeNull();
    expect(aMilisegundosOdoo("")).toBeNull();
  });

  it("epoch en segundos o en milisegundos, como número o como texto", () => {
    expect(aMilisegundosOdoo(1_790_000_000)).toBe(1_790_000_000_000);
    expect(aMilisegundosOdoo(1_790_000_000_000)).toBe(1_790_000_000_000);
    expect(aMilisegundosOdoo("1790000000")).toBe(1_790_000_000_000);
  });

  it("ISO con zona se respeta; el «2026-10-09 14:03:00» de Odoo es UTC", () => {
    expect(aMilisegundosOdoo("2026-10-09T14:03:00Z")).toBe(Date.UTC(2026, 9, 9, 14, 3));
    expect(aMilisegundosOdoo("2026-10-09T09:03:00-05:00")).toBe(Date.UTC(2026, 9, 9, 14, 3));
    expect(aMilisegundosOdoo("2026-10-09 14:03:00")).toBe(Date.UTC(2026, 9, 9, 14, 3));
  });

  it("basura: sin fecha, no lanza", () => {
    expect(aMilisegundosOdoo("pronto")).toBeNull();
  });
});
