import { describe, expect, it, vi } from "vitest";
import { derivarTokenContenedor } from "../src/comun";
import { PENDIENTE_MAX_CARACTERES, manejar, prepararPendiente } from "../src/router";
import type { Env, PuenteStub } from "../src/tipos";
import { construirWebhook } from "../contenedor/lib/contrato.mjs";

// Valores de PRUEBA: no son ningún secreto real.
const TOKEN = "token-de-prueba-0123456789-abcdefghij";
const CLAVE = "clave-de-prueba-para-la-sesion-0123456789";
const BASE = "https://dcasa-puente-wa.test";

function stubFalso(sobre: Partial<Record<keyof PuenteStub, any>> = {}) {
  const f = (v: unknown) => vi.fn(async () => v);
  const stub = {
    despertar: f(undefined),
    kvGet: f(null),
    kvSet: f({ ok: true }),
    kvDel: f({ ok: true }),
    kvLote: f({ ok: true, leidas: 0, escritas: 0, borradas: 0, valores: {} }),
    enviadosRecientes: f([]),
    marcarEntrante: f(undefined),
    encolarPendiente: f(7),
    estadoPublico: f({ ok: true, estado: "conectado", conectado: true }),
    qr: f({ status: 200, cuerpo: { qr: "data:image/png;base64,QQQ" } }),
    enviar: f({ status: 200, cuerpo: { ok: true, ids: ["A"] } }),
    desvincular: f({ status: 200, cuerpo: { ok: true } }),
    matar: f({ reiniciosForzados: 2 }),
    copiarAhora: f({ copia: "2026-10-09T03-17-00Z", filas: 3, r2: { subida: false, motivo: "apagado" } }),
    listarCopias: f([{ copia: "c1", creada: "x", filas: 3 }]),
    exportarCopia: f({ version: 1, copia: "c1", creada: "x", filas: [] }),
    restaurar: f({ status: 200, cuerpo: { ok: true } }),
    podar: f({ borradas: 1, conservadas: 1000 }),
    recifrar: f({ revisadas: 2, recifradas: 2 }),
    ...sobre,
  };
  return stub as unknown as PuenteStub & Record<string, ReturnType<typeof vi.fn>>;
}

const juanQue = (...estados: number[]) => {
  let i = 0;
  return { fetch: vi.fn(async () => new Response("{}", { status: estados[Math.min(i++, estados.length - 1)] })) } as unknown as Fetcher;
};
const envBase = (extra: Record<string, unknown> = {}): Env =>
  ({ WA_TOKEN: TOKEN, WA_SESION_CLAVE: CLAVE, PUENTE_ACTIVO: "on", PUENTE_BASE_URL: BASE, WA: {} as any, JUAN: juanQue(200), ...extra }) as Env;

async function pedir(env: Env, stub: PuenteStub, ruta: string, init: RequestInit & { token?: string | null } = {}) {
  const { token = TOKEN, ...resto } = init;
  const headers = new Headers(resto.headers);
  if (token) headers.set("authorization", `Bearer ${token}`);
  return manejar(new Request(`${BASE}${ruta}`, { ...resto, headers }), env, () => stub);
}
const api = (env: Env, stub: PuenteStub, ruta: string, init: RequestInit & { token?: string | null } = {}) => pedir(env, stub, ruta, init);
const cuerpo = async (r: Response) => JSON.parse(await r.text());

describe("sin secretos (el primer despliegue sale sin ellos)", () => {
  it("/health responde siempre", async () => {
    const r = await pedir({ PUENTE_BASE_URL: BASE } as Env, stubFalso(), "/health", { token: null });
    expect(await r.text()).toBe("ok");
  });

  it("/api/estado sin WA_TOKEN: dice que no está configurado y SOLO los nombres que faltan", async () => {
    const stub = stubFalso();
    const r = await pedir({ PUENTE_BASE_URL: BASE, PUENTE_ACTIVO: "on" } as Env, stub, "/api/estado", { token: null });
    expect(r.status).toBe(200);
    expect(await cuerpo(r)).toMatchObject({
      estado: "sin_configurar",
      conectado: false,
      secretos_faltantes: ["WA_TOKEN", "WA_SESION_CLAVE"],
      opcionales_faltantes: ["TELEGRAM_BOT_TOKEN_JUAN", "ALERTA_TELEGRAM_CHAT"],
      binding_juan: false,
    });
    expect(stub.estadoPublico).not.toHaveBeenCalled(); // no toca el Durable Object ni el contenedor
  });

  it("todo lo demás responde 503 con los nombres que faltan (no 500, no se cae)", async () => {
    const env = { PUENTE_BASE_URL: BASE } as Env;
    for (const [metodo, ruta] of [["POST", "/api/enviar"], ["GET", "/api/qr"], ["POST", "/api/reiniciar"], ["PUT", "/puente/kv?clave=creds"], ["POST", "/puente/entrante"]] as const) {
      const r = await pedir(env, stubFalso(), ruta, { method: metodo, token: null });
      expect(r.status).toBe(503);
      expect(await cuerpo(r)).toMatchObject({ secretos_faltantes: ["WA_TOKEN", "WA_SESION_CLAVE"] });
    }
  });

  it("con WA_TOKEN pero sin WA_SESION_CLAVE: /api/estado exige token y dice qué falta", async () => {
    const env = envBase({ WA_SESION_CLAVE: undefined });
    const sin = await pedir(env, stubFalso(), "/api/estado", { token: null });
    expect(sin.status).toBe(401);
    const con = await pedir(env, stubFalso(), "/api/estado");
    expect(await cuerpo(con)).toMatchObject({ estado: "sin_configurar", secretos_faltantes: ["WA_SESION_CLAVE"] });
    const enviar = await pedir(env, stubFalso(), "/api/enviar", { method: "POST", body: "{}" });
    expect(enviar.status).toBe(503);
  });

  it("secretos inservibles se reportan por nombre y motivo, sin el valor", async () => {
    const env = envBase({ WA_TOKEN: "valor-uno-xyz", WA_SESION_CLAVE: "valor-dos-abc" });
    const r = await pedir(env, stubFalso(), "/api/estado", { token: "valor-uno-xyz" });
    const c = await cuerpo(r);
    expect(c.estado).toBe("sin_configurar");
    expect(c.secretos_invalidos.map((i: any) => i.nombre)).toEqual(["WA_TOKEN", "WA_SESION_CLAVE"]);
    expect(JSON.stringify(c)).not.toContain("valor-uno");
    expect(JSON.stringify(c)).not.toContain("valor-dos");
  });
});

describe("autenticación de /api/* (WA_TOKEN, en tiempo constante)", () => {
  const rutas: [string, string][] = [
    ["GET", "/api/estado"],
    ["GET", "/api/qr"],
    ["POST", "/api/enviar"],
    ["POST", "/api/desvincular"],
    ["POST", "/api/reiniciar"],
    ["GET", "/api/copias"],
    ["POST", "/api/copias"],
    ["GET", "/api/copias/exportar"],
    ["POST", "/api/restaurar"],
    ["POST", "/api/podar"],
    ["POST", "/api/recifrar"],
  ];

  it.each(rutas)("%s %s sin token → 401, y nada llega al Durable Object", async (metodo, ruta) => {
    const stub = stubFalso();
    const r = await api(envBase(), stub, ruta, { method: metodo, token: null });
    expect(r.status).toBe(401);
    for (const fn of Object.values(stub)) expect(fn).not.toHaveBeenCalled();
  });

  it("token equivocado → 401, y la respuesta no revela nada del esperado", async () => {
    const r = await api(envBase(), stubFalso(), "/api/estado", { token: TOKEN + "x" });
    expect(r.status).toBe(401);
    const c = await cuerpo(r);
    expect(c).toEqual({ error: "Token inválido.", via: "bearer", presentadoLargo: TOKEN.length + 1 });
    expect(JSON.stringify(c)).not.toContain(String(TOKEN.length) + ",");
  });

  it("acepta Authorization: Bearer, x-wa-token y x-wa-token-b64", async () => {
    const env = envBase();
    const formas: Record<string, string>[] = [{ authorization: `Bearer ${TOKEN}` }, { "x-wa-token": TOKEN }, { "x-wa-token-b64": btoa(TOKEN) }];
    for (const headers of formas) {
      const r = await manejar(new Request(`${BASE}/api/estado`, { headers }), env, () => stubFalso());
      expect(r.status).toBe(200);
    }
  });

  it("el token en la URL NO vale", async () => {
    const r = await manejar(new Request(`${BASE}/api/qr?t=${TOKEN}&token=${TOKEN}`), envBase(), () => stubFalso());
    expect(r.status).toBe(401);
  });

  it("el token del CONTENEDOR no abre /api/*, y el WA_TOKEN no abre /puente/* (mínimo privilegio)", async () => {
    const sub = await derivarTokenContenedor(TOKEN);
    const env = envBase();
    expect((await api(env, stubFalso(), "/api/qr", { token: sub })).status).toBe(401);
    expect((await pedir(env, stubFalso(), "/puente/enviados", { token: TOKEN })).status).toBe(401);
    expect((await pedir(env, stubFalso(), "/puente/enviados", { token: sub })).status).toBe(200);
  });

  it("rutas desconocidas: 404", async () => {
    expect((await api(envBase(), stubFalso(), "/api/nada")).status).toBe(404);
    expect((await manejar(new Request(`${BASE}/otra-cosa`), envBase(), () => stubFalso())).status).toBe(404);
    expect((await api(envBase(), stubFalso(), "/api/enviar", { method: "GET" })).status).toBe(404);
  });
});

describe("/api/*: lo que ve Juan", () => {
  it("GET /api/estado: lo del Durable Object más secretos faltantes, binding y si el token es apto", async () => {
    const env = envBase();
    const r = await api(env, stubFalso(), "/api/estado");
    expect(await cuerpo(r)).toMatchObject({
      estado: "conectado",
      conectado: true,
      secretos_faltantes: [],
      opcionales_faltantes: ["TELEGRAM_BOT_TOKEN_JUAN", "ALERTA_TELEGRAM_CHAT"],
      binding_juan: true,
      token: { apto: { apto: true } },
    });
    expect(r.headers.get("cache-control")).toBe("no-store");
  });

  it("GET /api/qr: pasa lo del contenedor, sin caché", async () => {
    const r = await api(envBase(), stubFalso(), "/api/qr");
    expect(r.status).toBe(200);
    expect(r.headers.get("cache-control")).toBe("no-store");
    expect((await cuerpo(r)).qr).toContain("data:image/png");
  });

  it("POST /api/enviar: pasa el cuerpo TAL CUAL al Durable Object y devuelve su respuesta", async () => {
    const stub = stubFalso();
    const c = JSON.stringify({ para: "60261919", chunks: ["Hola"] });
    const r = await api(envBase(), stub, "/api/enviar", { method: "POST", body: c });
    expect(stub.enviar).toHaveBeenCalledWith(c);
    expect(r.status).toBe(200);
    expect(await cuerpo(r)).toEqual({ ok: true, ids: ["A"] });
  });

  it.each([
    [429, { error: "tope", reintentar_en_s: 41.2 }, "42"],
    [503, { error: "cola llena", reintentar_en_s: 30 }, "30"],
    [429, { error: "tope" }, "30"],
  ])("un %i trae Retry-After para que Juan sepa cuándo volver", async (status, c, esperado) => {
    const stub = stubFalso({ enviar: vi.fn(async () => ({ status, cuerpo: c })) });
    const r = await api(envBase(), stub, "/api/enviar", { method: "POST", body: "{}" });
    expect(r.status).toBe(status);
    expect(r.headers.get("retry-after")).toBe(esperado);
  });

  it("desvincular y reiniciar", async () => {
    const stub = stubFalso();
    expect((await api(envBase(), stub, "/api/desvincular", { method: "POST" })).status).toBe(200);
    const r = await api(envBase(), stub, "/api/reiniciar", { method: "POST" });
    expect(await cuerpo(r)).toMatchObject({ ok: true, reinicios_forzados: 2 });
  });

  it("copias: listar, sacar una, exportar como descarga", async () => {
    const stub = stubFalso();
    expect(await cuerpo(await api(envBase(), stub, "/api/copias"))).toMatchObject({ copias: [{ copia: "c1" }] });
    expect(await cuerpo(await api(envBase(), stub, "/api/copias", { method: "POST" }))).toMatchObject({ copia: "2026-10-09T03-17-00Z", filas: 3 });
    const exp = await api(envBase(), stub, "/api/copias/exportar?id=c1");
    expect(stub.exportarCopia).toHaveBeenCalledWith("c1");
    expect(exp.headers.get("content-disposition")).toContain('filename="sesion-c1.json"');
    const nada = stubFalso({ exportarCopia: vi.fn(async () => null) });
    expect((await api(envBase(), nada, "/api/copias/exportar")).status).toBe(404);
  });

  describe("restaurar", () => {
    const restaurar = (env: Env, stub: PuenteStub, c: unknown) => api(env, stub, "/api/restaurar", { method: "POST", body: JSON.stringify(c) });
    const archivo = { version: 1, copia: "c9", creada: "x", filas: [{ clave: "creds", valor: "v1.a.b.c", actualizado_en: 1 }] };

    it("desde una copia del Durable Object", async () => {
      const stub = stubFalso();
      expect((await restaurar(envBase(), stub, { copia: "c1" })).status).toBe(200);
      expect(stub.restaurar).toHaveBeenCalledWith({ copia: "c1" });
      await restaurar(envBase(), stub, {});
      expect(stub.restaurar).toHaveBeenLastCalledWith({ copia: undefined });
    });

    it("desde un archivo pegado (con comprobación de forma)", async () => {
      const stub = stubFalso();
      expect((await restaurar(envBase(), stub, { archivo })).status).toBe(200);
      expect(stub.restaurar).toHaveBeenCalledWith({ archivo });
      expect((await restaurar(envBase(), stub, { archivo: { version: 1, copia: "x", filas: [{ clave: "creds", valor: "EN CLARO", actualizado_en: 1 }] } })).status).toBe(400);
    });

    it("desde R2", async () => {
      const stub = stubFalso();
      const get = vi.fn(async (k: string) => (k === "sesion/c9.json" ? { text: async () => JSON.stringify(archivo) } : null));
      const env = envBase({ COPIAS: { get } });
      expect((await restaurar(env, stub, { origen: "r2", copia: "c9" })).status).toBe(200);
      expect(stub.restaurar).toHaveBeenCalledWith({ archivo });
      expect((await restaurar(env, stub, { origen: "r2", copia: "no-esta" })).status).toBe(404);
      expect((await restaurar(env, stub, { origen: "r2" })).status).toBe(400);
      expect((await restaurar(env, stub, { origen: "r2", copia: "../../etc" })).status).toBe(400);
      expect((await restaurar(envBase(), stub, { origen: "r2", copia: "c9" })).status).toBe(409); // sin bucket enlazado
    });

    it("cuerpo que no es JSON", async () => {
      const r = await api(envBase(), stubFalso(), "/api/restaurar", { method: "POST", body: "no es json" });
      expect(r.status).toBe(400);
    });
  });

  it("podar y recifrar", async () => {
    const stub = stubFalso();
    expect(await cuerpo(await api(envBase(), stub, "/api/podar", { method: "POST" }))).toMatchObject({ borradas: 1 });
    expect(await cuerpo(await api(envBase(), stub, "/api/recifrar", { method: "POST" }))).toMatchObject({ recifradas: 2 });
  });
});

describe("/puente/*: lo que llama el contenedor", () => {
  let sub: string;
  const puente = async (env: Env, stub: PuenteStub, ruta: string, init: RequestInit & { epoca?: string } = {}) => {
    sub ??= await derivarTokenContenedor(TOKEN);
    const { epoca, ...resto } = init;
    const headers = new Headers(resto.headers);
    if (epoca) headers.set("x-wa-epoca", epoca);
    return pedir(env, stub, ruta, { ...resto, headers, token: sub });
  };

  it("kv: leer, escribir y borrar, con la época del contenedor", async () => {
    const stub = stubFalso({ kvGet: vi.fn(async (k: string) => (k === "creds" ? '{"a":1}' : null)) });
    const env = envBase();
    const g = await puente(env, stub, "/puente/kv?clave=creds");
    expect(await g.text()).toBe('{"a":1}');
    expect((await puente(env, stub, "/puente/kv?clave=nada")).status).toBe(404);
    expect((await puente(env, stub, "/puente/kv?clave=creds", { method: "PUT", body: '{"b":2}', epoca: "3" })).status).toBe(200);
    expect(stub.kvSet).toHaveBeenCalledWith("creds", '{"b":2}', "3");
    expect((await puente(env, stub, "/puente/kv?clave=creds", { method: "DELETE", epoca: "3" })).status).toBe(200);
    expect(stub.kvDel).toHaveBeenCalledWith("creds", "3");
    expect((await puente(env, stub, "/puente/kv?clave=creds", { method: "PATCH" })).status).toBe(405);
  });

  it("un escritor obsoleto recibe 409", async () => {
    const stub = stubFalso({ kvSet: vi.fn(async () => ({ ok: false, status: 409, error: "Escritor obsoleto" })) });
    const r = await puente(envBase(), stub, "/puente/kv?clave=creds", { method: "PUT", body: "{}", epoca: "1" });
    expect(r.status).toBe(409);
    expect((await cuerpo(r)).error).toContain("obsoleto");
  });

  it.each(["", "a b", "x".repeat(301), "a\nb", "ñandú", "a\tb"])("clave inválida «%s»", async (clave) => {
    const r = await puente(envBase(), stubFalso(), `/puente/kv?clave=${encodeURIComponent(clave)}`);
    expect(r.status).toBe(400);
  });

  it("claves reales de Baileys son válidas", async () => {
    const claves = [
      "creds",
      "pre-key-12",
      "session-50760261919@s.whatsapp.net.0",
      "sender-key-120363025246125486@g.us::50760261919::0",
      "app-state-sync-key-AAAAAD7e",
      "app-state-sync-key-a+B/c9==", // los ids de las llaves de estado son base64
      "lid-mapping-50760261919",
      "device-list-50760261919",
    ];
    for (const clave of claves) {
      expect((await puente(envBase(), stubFalso(), `/puente/kv?clave=${encodeURIComponent(clave)}`)).status).toBe(404);
    }
  });

  it("kv-lote: valida la forma y pasa la época", async () => {
    const stub = stubFalso();
    const env = envBase();
    const ok = await puente(env, stub, "/puente/kv-lote", { method: "POST", body: JSON.stringify({ leer: ["a"], escribir: { b: "1" }, borrar: ["c"] }), epoca: "2" });
    expect(ok.status).toBe(200);
    expect(stub.kvLote).toHaveBeenCalledWith({ leer: ["a"], escribir: { b: "1" }, borrar: ["c"] }, "2");
    for (const mal of [{ leer: "a" }, { escribir: { b: 5 } }, { escribir: [] }, { borrar: [1] }, { leer: ["con espacio"] }, null, "texto"]) {
      expect((await puente(env, stub, "/puente/kv-lote", { method: "POST", body: JSON.stringify(mal) })).status).toBe(400);
    }
    expect((await puente(env, stub, "/puente/kv-lote", { method: "POST", body: "no json" })).status).toBe(400);
  });

  it("enviados recientes", async () => {
    const stub = stubFalso({ enviadosRecientes: vi.fn(async () => [{ id: "A", ts: 1 }]) });
    expect(await cuerpo(await puente(envBase(), stub, "/puente/enviados"))).toEqual({ ids: [{ id: "A", ts: 1 }] });
  });

  describe("entrante: del contenedor hacia el Worker juan", () => {
    const mensaje = (extra: Record<string, unknown> = {}) =>
      JSON.stringify(construirWebhook({ idMensaje: "A1", de: "50760261919", nombre: "Karen", tipo: "texto", texto: "Hola", ts: Date.UTC(2026, 9, 9), propio: false, ...extra } as any));

    it("lo entrega a Juan por el binding con el token, tal cual, y marca al cliente como «ya nos escribió»", async () => {
      const juan = juanQue(200);
      const stub = stubFalso();
      const c = mensaje();
      const r = await puente(envBase({ JUAN: juan }), stub, "/puente/entrante", { method: "POST", body: c });
      expect(r.status).toBe(200);
      expect(await cuerpo(r)).toEqual({ ok: true, entregado: true });
      const enviada = (juan.fetch as any).mock.calls[0][0] as Request;
      expect(new URL(enviada.url).pathname).toBe("/webhooks/whatsapp-qr");
      expect(enviada.headers.get("x-wa-token")).toBe(TOKEN);
      expect(await enviada.text()).toBe(c);
      expect(stub.marcarEntrante).toHaveBeenCalledWith("50760261919");
    });

    it("lo que escribe la vendedora (propio:true) NO marca al cliente", async () => {
      const stub = stubFalso();
      await puente(envBase(), stub, "/puente/entrante", { method: "POST", body: mensaje({ propio: true, nombre: null }) });
      expect(stub.marcarEntrante).not.toHaveBeenCalled();
    });

    it("si Juan no está disponible, el mensaje NO se pierde: se guarda y se responde 202", async () => {
      const stub = stubFalso();
      const c = mensaje();
      const r = await puente(envBase({ JUAN: juanQue(500) }), stub, "/puente/entrante", { method: "POST", body: c });
      expect(r.status).toBe(202);
      expect(await cuerpo(r)).toMatchObject({ ok: true, entregado: false, encolado: true });
      expect(stub.encolarPendiente).toHaveBeenCalledWith(c);
    });

    it("sin el binding JUAN (aún no desplegado) también se guarda", async () => {
      const stub = stubFalso();
      const r = await puente(envBase({ JUAN: undefined }), stub, "/puente/entrante", { method: "POST", body: mensaje() });
      expect(r.status).toBe(202);
      expect(stub.encolarPendiente).toHaveBeenCalled();
    });

    it("si ni siquiera se puede guardar, 503: el contenedor reintenta", async () => {
      const stub = stubFalso({ encolarPendiente: vi.fn(async () => { throw new Error("disco lleno"); }) });
      const r = await puente(envBase({ JUAN: juanQue(500) }), stub, "/puente/entrante", { method: "POST", body: mensaje() });
      expect(r.status).toBe(503);
    });

    it("si Juan lo rechaza por malformado (400/422) no se guarda ni se repite", async () => {
      const stub = stubFalso();
      const r = await puente(envBase({ JUAN: juanQue(422) }), stub, "/puente/entrante", { method: "POST", body: mensaje() });
      expect(r.status).toBe(422);
      expect(stub.encolarPendiente).not.toHaveBeenCalled();
    });

    it("un cuerpo que no cumple el contrato no llega a Juan", async () => {
      const juan = juanQue(200);
      const mal = JSON.stringify({ id_mensaje: "x", de: "50760261919", tipo: "sticker", propio: false, ts: "ayer" });
      const r = await puente(envBase({ JUAN: juan }), stubFalso(), "/puente/entrante", { method: "POST", body: mal });
      expect(r.status).toBe(400);
      expect((await cuerpo(r)).errores.length).toBeGreaterThan(0);
      expect(juan.fetch).not.toHaveBeenCalled();
      expect((await puente(envBase({ JUAN: juan }), stubFalso(), "/puente/entrante", { method: "POST", body: "no json" })).status).toBe(400);
    });
  });
});

describe("prepararPendiente: una fila de SQLite admite 2 MB", () => {
  it("lo que cabe se guarda tal cual", () => {
    const t = JSON.stringify({ id_mensaje: "A", texto: "hola" });
    expect(prepararPendiente(t, JSON.parse(t))).toBe(t);
  });

  it("un archivo enorme se guarda sin el archivo, diciendo que lo hubo", () => {
    const payload = { id_mensaje: "A", de: "507", tipo: "video", ts: "x", propio: false, medio: { base64: "A".repeat(PENDIENTE_MAX_CARACTERES + 1), mime: "video/mp4", nombre: "v.mp4" } };
    const guardado = JSON.parse(prepararPendiente(JSON.stringify(payload), payload));
    expect(guardado).not.toHaveProperty("medio");
    expect(guardado.medio_omitido).toMatchObject({ motivo: "juan_no_disponible", mime: "video/mp4" });
    expect(guardado.medio_omitido.bytes).toBeGreaterThan(PENDIENTE_MAX_CARACTERES / 2);
    expect(JSON.stringify(guardado).length).toBeLessThan(1000);
  });
});
