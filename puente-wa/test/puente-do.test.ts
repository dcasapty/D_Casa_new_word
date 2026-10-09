import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { sqlDePrueba } from "./ayuda/sql";
import { crearCtx, jsonResp, type CtxFalso } from "./ayuda/contenedor-falso";

// La clase `Container` de @cloudflare/containers necesita el runtime de Cloudflare; aquí se cambia por un
// doble que imita lo que importa (ver ayuda/contenedor-falso.ts). El resto de PuenteWa es el código REAL.
vi.mock("@cloudflare/containers", async () => {
  const m = await import("./ayuda/contenedor-falso");
  return { Container: m.ContenedorBase };
});

import { PuenteWa } from "../src/puente-do";
import { derivarTokenContenedor } from "../src/comun";
import { diarioNuevo } from "../src/vigilancia";

// Valores de PRUEBA: no son ningún secreto real.
const TOKEN = "token-de-prueba-0123456789-abcdefghij";
const CLAVE = "clave-de-prueba-para-la-sesion-0123456789";
const OTRA_CLAVE = "otra-clave-de-prueba-distinta-9876543210-xyz";
const T0 = Date.UTC(2026, 9, 9, 15, 0, 0);
const MIN = 60_000;
const HORA = 60 * MIN;

type Do = PuenteWa & Record<string, any>;

function juanFalso(...estados: number[]) {
  let i = 0;
  const recibidos: string[] = [];
  return {
    recibidos,
    fetch: vi.fn(async (r: Request) => {
      recibidos.push(await r.text());
      return new Response("{}", { status: estados[Math.min(i++, estados.length - 1)] ?? 200 });
    }),
  };
}

async function montar(envExtra: Record<string, unknown> = {}, ctx: CtxFalso = crearCtx()) {
  const env: any = {
    PUENTE_ACTIVO: "on",
    PUENTE_BASE_URL: "https://dcasa-puente-wa-staging.dcasapty.workers.dev",
    MEDIOS_HOSTS_PERMITIDOS: "dcasapty.com",
    WA_TOKEN: TOKEN,
    WA_SESION_CLAVE: CLAVE,
    JUAN: juanFalso(200),
    ...envExtra,
  };
  const d = new PuenteWa(ctx as any, env) as Do;
  await Promise.all(ctx.listo);
  return { d, ctx, env };
}

/** El contenedor responde como si WhatsApp estuviera en el estado dado. */
function contenedor(d: Do, conexion: string | null = "conectada", extra: Record<string, unknown> = {}) {
  d.manejador = (u: URL, init?: RequestInit) => {
    if (u.pathname === "/estado") {
      if (conexion === null) throw new Error("no contesta");
      return jsonResp({ conexion, vinculadoComo: "***1919:3@s.whatsapp.net", reconexiones: 2, mensajesRecibidos: 5, ignorados: { no_es_chat: 1 }, enviosEnCola: 0, ultimoError: null, ...extra });
    }
    if (u.pathname === "/reconectar") return jsonResp({ ok: true });
    if (u.pathname === "/logout") return jsonResp({ ok: true });
    if (u.pathname === "/qr") return jsonResp({ qr: "data:image/png;base64,QQQ", estado: conexion, generados: 1 });
    if (u.pathname === "/enviar") {
      const c = JSON.parse(String(init?.body));
      const n = (c.chunks?.length ?? 0) + (c.medios?.length ?? 0);
      return jsonResp({ ok: true, ids: Array.from({ length: n }, (_, i) => `ID${i + 1}`), id_mensaje: `ID${n}`, enviados: { chunks: c.chunks?.length ?? 0, medios: c.medios?.length ?? 0 } });
    }
    return jsonResp({ error: "no existe" }, 404);
  };
}

let telegram: ReturnType<typeof vi.fn>;
beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date", "setTimeout", "clearTimeout"] });
  vi.setSystemTime(T0);
  telegram = vi.fn(async () => new Response("{}", { status: 200 }));
  vi.stubGlobal("fetch", telegram);
  vi.spyOn(console, "log").mockImplementation(() => {});
  vi.spyOn(console, "error").mockImplementation(() => {});
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});
const avanzar = (ms: number) => vi.setSystemTime(Date.now() + ms);
/** Deja correr las promesas pendientes (no usa temporizadores: sirve con los relojes falsos). */
const asentar = async () => {
  for (let i = 0; i < 300; i++) await Promise.resolve();
};
/**
 * Corre una vigilancia dejando avanzar los relojes falsos (las esperas de reintento usan setTimeout). Avanza
 * hasta que termine, cediendo turno a las operaciones reales de cifrado (WebCrypto trabaja fuera del hilo):
 * contar vueltas fijas sería frágil con la máquina cargada.
 */
async function vigilarAvanzando(d: Do) {
  let terminada = false;
  const p = d.vigilar().finally(() => {
    terminada = true;
  });
  for (let vuelta = 0; !terminada && vuelta < 400; vuelta++) {
    await asentar();
    await new Promise((r) => setImmediate(r)); // setImmediate no está entre los relojes falsos
    await vi.advanceTimersByTimeAsync(600);
  }
  await p;
}

describe("arranque y entorno del contenedor", () => {
  it("el contenedor recibe un token DERIVADO, nunca el WA_TOKEN ni la clave de cifrado", async () => {
    const { d } = await montar();
    expect(d.envVars!.PUENTE_TOKEN).toBe(await derivarTokenContenedor(TOKEN));
    const todo = JSON.stringify(d.envVars!);
    expect(todo).not.toContain(TOKEN);
    expect(todo).not.toContain(CLAVE);
    expect(d.envVars!).toMatchObject({
      PORT: "8080",
      PUENTE_URL: "https://dcasa-puente-wa-staging.dcasapty.workers.dev",
      MEDIOS_HOSTS_PERMITIDOS: "dcasapty.com",
    });
  });

  it("cada arranque real sube la época y el contenedor la recibe; las comprobaciones no cuentan como arranque", async () => {
    const { d, ctx } = await montar();
    contenedor(d);
    await d.vigilar();
    expect(d.arranques).toHaveLength(1);
    expect(d.arranques[0].envVars.PUENTE_EPOCA).toBe("1");
    expect(ctx.storage.kv.get("epoca")).toBe(1);

    // 10 vigilancias más con el contenedor ya corriendo: ni arranques nuevos ni épocas nuevas.
    for (let i = 0; i < 10; i++) await d.vigilar();
    expect(d.arranques).toHaveLength(1);
    expect(ctx.storage.kv.get("epoca")).toBe(1);
    expect((await d.diario()).arranquesContenedor).toBe(1);
  });

  it("la época sobrevive a un reinicio del Durable Object", async () => {
    const ctx = crearCtx();
    const a = await montar({}, ctx);
    contenedor(a.d);
    await a.d.vigilar();
    const b = await montar({}, ctx); // el DO se reconstruye con el mismo almacenamiento
    expect(b.d.envVars!.PUENTE_EPOCA).toBe("1");
  });
});

describe("un solo escritor: la época", () => {
  it("solo el contenedor vigente puede escribir la sesión", async () => {
    const { d } = await montar();
    contenedor(d);
    await d.vigilar(); // época 1
    expect(await d.kvSet("creds", '{"a":1}', "1")).toEqual({ ok: true });
    expect(await d.kvGet("creds")).toBe('{"a":1}');
    for (const mala of [null, "0", "2", "uno"]) {
      expect(await d.kvSet("creds", "{}", mala)).toMatchObject({ ok: false, status: 409 });
      expect(await d.kvDel("creds", mala)).toMatchObject({ ok: false, status: 409 });
      expect(await d.kvLote({ escribir: { x: "1" } }, mala)).toMatchObject({ ok: false, status: 409 });
    }
    expect(await d.kvGet("creds")).toBe('{"a":1}'); // intacta
  });

  it("un contenedor «zombi» de la época anterior deja de poder escribir tras un reinicio", async () => {
    const { d } = await montar();
    contenedor(d);
    await d.vigilar(); // época 1
    await d.matar(); // destruye y arranca de nuevo → época 2
    expect(d.arranques.map((a: any) => a.envVars.PUENTE_EPOCA)).toEqual(["1", "2"]);
    expect(await d.kvSet("creds", "{}", "1")).toMatchObject({ ok: false, status: 409 });
    expect(await d.kvSet("creds", "{}", "2")).toEqual({ ok: true });
  });

  it("leer es inofensivo; solo escribir o borrar exige la época", async () => {
    const { d } = await montar();
    contenedor(d);
    await d.vigilar();
    await d.kvLote({ escribir: { "pre-key-1": "uno" } }, "1");
    expect(await d.kvLote({ leer: ["pre-key-1", "nada"] }, null)).toMatchObject({ ok: true, valores: { "pre-key-1": "uno", nada: null } });
  });

  it("la sesión queda CIFRADA en el almacenamiento del Durable Object", async () => {
    const bd = sqlDePrueba();
    const { d } = await montar({}, crearCtx(bd));
    contenedor(d);
    await d.vigilar();
    await d.kvSet("creds", '{"noiseKey":"SECRETO-DE-PRUEBA"}', "1");
    expect(bd.volcado("wa_auth")).not.toContain("SECRETO");
    expect(await d.kvGet("creds")).toContain("SECRETO"); // pero se lee bien
  });
});

describe("sin secretos o apagado: no enciende el contenedor", () => {
  it.each([
    ["sin WA_TOKEN", { WA_TOKEN: undefined }],
    ["sin WA_SESION_CLAVE", { WA_SESION_CLAVE: undefined }],
    ["con WA_TOKEN inservible", { WA_TOKEN: "corto" }],
    ["con PUENTE_ACTIVO apagado", { PUENTE_ACTIVO: "off" }],
    ["con PUENTE_ACTIVO sin definir", { PUENTE_ACTIVO: undefined }],
  ])("%s", async (_n, env) => {
    const { d } = await montar(env);
    contenedor(d);
    await d.vigilar();
    await d.despertar();
    expect(d.arranques).toHaveLength(0);
    expect(d.programadas).toHaveLength(0); // ni siquiera cadena de alarmas
    expect(d.llamadas).toHaveLength(0);
    expect((await d.enviar(JSON.stringify({ para: "60261919", chunks: ["hola"] }))).status).toBe(503);
    expect((await d.qr()).cuerpo).toMatchObject({ qr: null });
  });

  it("si se quitan los secretos (la dueña borra WA_TOKEN), el contenedor que corría se apaga", async () => {
    const ctx = crearCtx();
    const a = await montar({}, ctx);
    contenedor(a.d);
    await a.d.vigilar();
    expect(ctx.container.running).toBe(true);
    const b = await montar({ WA_TOKEN: undefined }, ctx); // el DO se reconstruye con el nuevo entorno
    await b.d.despertar(); // lo llama el cron cada minuto
    expect(ctx.container.running).toBe(false);
    expect(b.d.arranques).toHaveLength(0);
  });

  it("el token del contenedor falta en el entorno si falta WA_TOKEN (no se inventa uno)", async () => {
    const { d } = await montar({ WA_TOKEN: undefined });
    expect(d.envVars!.PUENTE_TOKEN).toBeUndefined();
  });

  it("si la dueña cambia WA_TOKEN, el contenedor vivo se reinicia para tomar el token nuevo (la sesión no se pierde)", async () => {
    const ctx = crearCtx();
    const a = await montar({}, ctx);
    contenedor(a.d);
    await a.d.vigilar();
    await a.d.kvSet("creds", "SESION", "1");

    const b = await montar({ WA_TOKEN: "token-nuevo-de-prueba-9876543210-zyxwvu" }, ctx);
    contenedor(b.d);
    await b.d.vigilar();
    expect(b.d.paradas).toHaveLength(1); // se destruyó el que tenía el token viejo
    expect(b.d.arranques).toHaveLength(1);
    expect(b.d.arranques[0].envVars.PUENTE_TOKEN).toBe(await derivarTokenContenedor("token-nuevo-de-prueba-9876543210-zyxwvu"));
    expect(b.d.arranques[0].envVars.PUENTE_EPOCA).toBe("2");
    expect(await b.d.kvGet("creds")).toBe("SESION");
    // Y sin cambios de token no se reinicia más.
    await b.d.vigilar();
    expect(b.d.paradas).toHaveLength(1);
  });
});

describe("la vigilancia", () => {
  it("encadena SIEMPRE la siguiente (30 s, por schedule(), UNA sola vez por latido)", async () => {
    const { d } = await montar();
    contenedor(d);
    await d.vigilar();
    expect(d.programadas).toEqual([{ cuando: 30, callback: "vigilar" }]);
    await d.vigilar();
    expect(d.programadas).toHaveLength(2); // una por latido, sin otros dueños que programen
    expect(d.renovaciones).toBeGreaterThanOrEqual(2); // renueva la actividad a mano
  });

  it("aun si el arranque del contenedor falla, la próxima vigilancia ya quedó pedida", async () => {
    const { d } = await montar();
    d.fallarArranque = true;
    await d.vigilar();
    expect(d.programadas).toHaveLength(1);
    const dia = await d.diario();
    expect(dia.ultimoFalloDelLatido).toContain("puerto");
    expect(dia.latidos).toBe(1);
  });

  it("el cron solo revive la cadena si se cortó (no multiplica las cadenas)", async () => {
    const { d } = await montar();
    contenedor(d);
    await d.despertar(); // nunca latió → arranca
    expect(d.programadas).toHaveLength(1);
    avanzar(30_000);
    await d.despertar(); // latió hace 30 s → no hace nada
    expect(d.programadas).toHaveLength(1);
    avanzar(4 * MIN);
    await d.despertar(); // el último latido está vencido → la reanuda
    expect(d.programadas).toHaveLength(2);
  });

  it("conectado: sin reconexiones ni reinicios", async () => {
    const { d } = await montar();
    contenedor(d, "conectada");
    for (let i = 0; i < 20; i++) {
      await d.vigilar();
      avanzar(30_000);
    }
    expect(d.llamadas.filter((l: any) => l.url.endsWith("/reconectar"))).toHaveLength(0);
    expect(d.paradas).toHaveLength(0);
    const dia = await d.diario();
    expect(dia).toMatchObject({ latidos: 20, desconectadoSeguidos: 0, sinConexionDesde: null });
  });

  it("caído: primero pide reconectar (barato); a la quinta vigilancia seguida destruye y levanta de cero", async () => {
    const { d } = await montar();
    contenedor(d, "cerrada");
    for (let i = 0; i < 4; i++) {
      await d.vigilar();
      avanzar(30_000);
    }
    expect(d.llamadas.filter((l: any) => l.url.endsWith("/reconectar"))).toHaveLength(4);
    expect(d.paradas).toHaveLength(0);
    await d.vigilar(); // la quinta
    expect(d.paradas).toHaveLength(1);
    expect(d.arranques).toHaveLength(2);
    expect((await d.diario()).reiniciosForzados).toBe(1);
  });

  it("el contenedor que ni contesta cuenta como caído", async () => {
    const { d } = await montar();
    contenedor(d, null);
    await d.vigilar();
    expect((await d.diario()).desconectadoSeguidos).toBe(1);
  });

  it("esperando el QR o desvinculado: NUNCA reinicia (tumbaría el QR que se está escaneando)", async () => {
    const { d } = await montar();
    contenedor(d, "esperando-qr");
    for (let i = 0; i < 40; i++) {
      await d.vigilar();
      avanzar(30_000);
    }
    expect(d.paradas).toHaveLength(0);
    expect(d.arranques).toHaveLength(1);
    expect(d.llamadas.filter((l: any) => l.url.endsWith("/reconectar"))).toHaveLength(0);
  });

  it("matar() es un punto y aparte: limpia la racha y vuelve a levantar", async () => {
    const { d } = await montar();
    contenedor(d, "cerrada");
    for (let i = 0; i < 3; i++) await d.vigilar();
    const dia = await d.matar();
    expect(dia.desconectadoSeguidos).toBe(0);
    expect(d.paradas).toHaveLength(1);
    expect(d.arranques).toHaveLength(2);
  });
});

describe("aviso a la dueña por Telegram", () => {
  const conAvisos = { TELEGRAM_BOT_TOKEN_JUAN: "123456:token-falso-de-prueba", ALERTA_TELEGRAM_CHAT: "-100777" };

  async function caidaDespuesDeConectar(env: Record<string, unknown> = conAvisos) {
    const m = await montar(env);
    contenedor(m.d, "conectada");
    await m.d.vigilar(); // estuvo conectado
    contenedor(m.d, "cerrada");
    return m;
  }

  it("avisa una vez a los 10 min sin conexión, repite a las 2 h y avisa la recuperación", async () => {
    const { d } = await caidaDespuesDeConectar();
    const enviosTelegram = () => telegram.mock.calls.filter((c: any[]) => String(c[0]).startsWith("https://api.telegram.org/"));

    avanzar(30_000);
    await d.vigilar(); // sin conexión desde hace 0 min
    avanzar(9 * MIN);
    await d.vigilar();
    expect(enviosTelegram()).toHaveLength(0);

    avanzar(2 * MIN); // ya van 11 min
    await d.vigilar();
    expect(enviosTelegram()).toHaveLength(1);
    const [url, init] = enviosTelegram()[0] as [string, RequestInit];
    expect(url).toBe("https://api.telegram.org/bot123456:token-falso-de-prueba/sendMessage");
    expect(JSON.parse(String(init.body))).toMatchObject({ chat_id: "-100777" });
    expect(JSON.parse(String(init.body)).text).toContain("sin conexión");

    avanzar(30 * MIN);
    await d.vigilar();
    expect(enviosTelegram()).toHaveLength(1); // no insiste

    avanzar(2 * HORA);
    await d.vigilar();
    expect(enviosTelegram()).toHaveLength(2); // a las 2 h, otra vez

    contenedor(d, "conectada");
    avanzar(30_000);
    await d.vigilar();
    expect(enviosTelegram()).toHaveLength(3);
    expect(JSON.parse(String((enviosTelegram()[2] as any)[1].body)).text).toContain("volvió a conectarse");
    avanzar(30_000);
    await d.vigilar();
    expect(enviosTelegram()).toHaveLength(3); // ya recuperado, silencio
  });

  it("desvinculado desde el teléfono: el aviso pide escanear el QR", async () => {
    const m = await montar(conAvisos);
    contenedor(m.d, "conectada");
    await m.d.vigilar();
    contenedor(m.d, "desvinculada");
    avanzar(30_000);
    await m.d.vigilar();
    avanzar(11 * MIN);
    await m.d.vigilar();
    expect(JSON.parse(String((telegram.mock.calls[0] as any)[1].body)).text).toContain("QR");
  });

  it("instalación nueva (nunca conectó): jamás avisa", async () => {
    const m = await montar(conAvisos);
    contenedor(m.d, "esperando-qr");
    for (let i = 0; i < 40; i++) {
      await m.d.vigilar();
      avanzar(MIN);
    }
    expect(telegram).not.toHaveBeenCalled();
  });

  it("sin configurar Telegram no falla: solo lo deja en el registro", async () => {
    const { d } = await caidaDespuesDeConectar({});
    avanzar(30_000);
    await d.vigilar();
    avanzar(12 * MIN);
    await expect(d.vigilar()).resolves.toBeUndefined();
    expect(telegram).not.toHaveBeenCalled();
    expect(((await d.diario()) as any).ultimoFalloDelLatido).toBe(null);
  });

  it("si Telegram falla, la vigilancia sigue y el token no sale en los registros", async () => {
    telegram.mockImplementation(async () => {
      throw new Error("sin red hacia api.telegram.org/bot123456:token-falso-de-prueba");
    });
    const { d } = await caidaDespuesDeConectar();
    avanzar(30_000);
    await d.vigilar();
    avanzar(12 * MIN);
    await expect(d.vigilar()).resolves.toBeUndefined();
    const registros = JSON.stringify([...(console.log as any).mock.calls, ...(console.error as any).mock.calls]);
    expect(registros).not.toContain("token-falso-de-prueba");
  });
});

describe("copia diaria de la sesión", () => {
  async function conSesion(env: Record<string, unknown> = {}) {
    const m = await montar(env);
    contenedor(m.d, "conectada");
    await m.d.vigilar();
    await m.d.kvSet("creds", JSON.stringify({ nextPreKeyId: 5, firstUnuploadedPreKeyId: 5 }), "1");
    await m.d.kvLote({ escribir: { "pre-key-1": "a", "session-x": "b" } }, "1");
    return m;
  }

  it("la saca al primer latido sano con sesión, y después una por día", async () => {
    const { d } = await conSesion();
    avanzar(30_000);
    await d.vigilar();
    expect(await d.listarCopias()).toHaveLength(1);
    avanzar(30_000);
    await d.vigilar();
    expect(await d.listarCopias()).toHaveLength(1);
    avanzar(24 * HORA);
    await d.vigilar();
    expect(await d.listarCopias()).toHaveLength(2);
  });

  it("recién vinculado, espera a que el dispositivo termine de instalarse antes de la primera copia", async () => {
    const m = await montar();
    contenedor(m.d, "conectada");
    await m.d.vigilar();
    // Quedan llaves por subir (sinSubir ≠ siguiente): todavía instalándose.
    await m.d.kvSet("creds", JSON.stringify({ nextPreKeyId: 813, firstUnuploadedPreKeyId: 645 }), "1");
    avanzar(30_000);
    await m.d.vigilar();
    expect(await m.d.listarCopias()).toHaveLength(0);
    // Termina de instalarse: ahora sí.
    await m.d.kvSet("creds", JSON.stringify({ nextPreKeyId: 813, firstUnuploadedPreKeyId: 813 }), "1");
    avanzar(30_000);
    await m.d.vigilar();
    expect(await m.d.listarCopias()).toHaveLength(1);
  });

  it("no copia una sesión que no está conectada", async () => {
    const { d } = await conSesion();
    contenedor(d, "cerrada");
    avanzar(30_000);
    await d.vigilar();
    expect(await d.listarCopias()).toHaveLength(0);
  });

  it("con R2 apagado (por defecto) no toca R2; con el interruptor encendido sube las filas CIFRADAS", async () => {
    const put = vi.fn(async () => ({}));
    const apagada = await conSesion({ COPIAS: { put } });
    const r1 = await apagada.d.copiarAhora();
    expect(r1.r2.subida).toBe(false);
    expect(put).not.toHaveBeenCalled();

    const encendida = await conSesion({ COPIA_R2: "on", COPIAS: { put } });
    const r2 = await encendida.d.copiarAhora();
    expect(r2.r2.subida).toBe(true);
    const [clave, cuerpo] = put.mock.calls[0] as unknown as [string, string];
    expect(clave).toMatch(/^sesion\/.+\.json$/);
    expect(cuerpo).not.toContain("nextPreKeyId");
    expect(JSON.parse(cuerpo).filas.every((f: any) => f.valor.startsWith("v1."))).toBe(true);
  });

  it("exportarCopia entrega el archivo cifrado de la última copia", async () => {
    const { d } = await conSesion();
    await d.copiarAhora();
    const a = await d.exportarCopia();
    expect(a?.filas.length).toBe(3);
    expect(JSON.stringify(a)).not.toContain("nextPreKeyId");
    expect(await d.exportarCopia("no-existe")).toBe(null);
  });
});

describe("restaurar la sesión", () => {
  async function conCopia() {
    const m = await montar();
    contenedor(m.d, "conectada");
    await m.d.vigilar();
    await m.d.kvSet("creds", '{"version":"BUENA"}', "1");
    const { copia } = await m.d.copiarAhora();
    await m.d.kvSet("creds", '{"version":"DAÑADA"}', "1");
    return { ...m, copia };
  }

  it("apaga el contenedor, guarda lo que había como una copia más, restaura y vuelve a levantar", async () => {
    const { d, copia } = await conCopia();
    avanzar(HORA);
    const r = await d.restaurar({ copia });
    expect(r.status).toBe(200);
    expect(await d.kvGet("creds")).toBe('{"version":"BUENA"}');
    expect(d.paradas).toHaveLength(1);
    expect(d.arranques).toHaveLength(2); // y volvió, con época nueva
    expect(d.arranques[1].envVars.PUENTE_EPOCA).toBe("2");
    expect(await d.listarCopias()).toHaveLength(2); // la dañada quedó guardada por si acaso
  });

  it("sin indicar copia, usa la más reciente", async () => {
    const { d } = await conCopia();
    expect((await d.restaurar({})).status).toBe(200);
    expect(await d.kvGet("creds")).toBe('{"version":"BUENA"}');
  });

  it("una copia que no existe: 404 y no se toca nada", async () => {
    const { d } = await conCopia();
    const r = await d.restaurar({ copia: "no-existe" });
    expect(r.status).toBe(404);
    expect(await d.kvGet("creds")).toBe('{"version":"DAÑADA"}');
    expect(d.paradas).toHaveLength(0);
  });

  it("una copia hecha con OTRA clave se rechaza (422), la sesión queda intacta y el contenedor vuelve", async () => {
    const origen = await montar({ WA_SESION_CLAVE: OTRA_CLAVE });
    contenedor(origen.d, "conectada");
    await origen.d.vigilar();
    await origen.d.kvSet("creds", "DE-OTRA-CLAVE", "1");
    await origen.d.copiarAhora();
    const archivo = await origen.d.exportarCopia();

    const { d } = await conCopia();
    const r = await d.restaurar({ archivo: archivo! });
    expect(r.status).toBe(422);
    expect(await d.kvGet("creds")).toBe('{"version":"DAÑADA"}');
    expect(d.arranques.length).toBe(2); // se apagó para restaurar y volvió a levantar
  });

  it("acepta un archivo exportado (p. ej. bajado de R2) de la misma clave", async () => {
    const { d, copia } = await conCopia();
    const archivo = await d.exportarCopia(copia);
    expect((await d.restaurar({ archivo: archivo! })).status).toBe(200);
    expect(await d.kvGet("creds")).toBe('{"version":"BUENA"}');
  });
});

describe("entrantes que Juan no pudo recibir", () => {
  it("se reintentan en orden hasta que Juan los recibe, y se borran", async () => {
    const juan = juanFalso(500, 500, 200);
    const { d } = await montar({ JUAN: juan });
    contenedor(d);
    await d.encolarPendiente('{"id_mensaje":"A"}');
    await d.encolarPendiente('{"id_mensaje":"B"}');

    await vigilarAvanzando(d); // Juan sigue caído (dos intentos rápidos fallan)
    expect(juan.recibidos).toEqual(['{"id_mensaje":"A"}', '{"id_mensaje":"A"}']);
    avanzar(5 * MIN);
    await vigilarAvanzando(d); // y ahora sí
    expect(juan.recibidos.slice(2)).toEqual(['{"id_mensaje":"A"}', '{"id_mensaje":"B"}']);
    expect((await d.estadoPublico()).pendientes).toBe(0);
  });

  it("espera cada vez más entre intentos si Juan sigue caído (no se le martilla cada 30 s)", async () => {
    const juan = juanFalso(503);
    const { d } = await montar({ JUAN: juan });
    contenedor(d);
    await d.encolarPendiente('{"id_mensaje":"A"}');
    await vigilarAvanzando(d);
    const tras1 = juan.fetch.mock.calls.length;
    avanzar(30_000);
    await vigilarAvanzando(d); // aún dentro de la espera
    expect(juan.fetch.mock.calls.length).toBe(tras1);
    avanzar(5 * MIN);
    await vigilarAvanzando(d);
    expect(juan.fetch.mock.calls.length).toBeGreaterThan(tras1);
  });

  it("un pendiente que Juan rechaza por malformado (422) se descarta; no se reintenta eternamente", async () => {
    const juan = juanFalso(422);
    const { d } = await montar({ JUAN: juan });
    contenedor(d);
    await d.encolarPendiente("{}");
    await vigilarAvanzando(d);
    expect((await d.estadoPublico()).pendientes).toBe(0);
  });
});

describe("enviar: ritmo y topes", () => {
  const cuerpo = (para = "60261919", chunks = ["Hola", "Sí hay"]) => JSON.stringify({ para, chunks });

  async function listo(env: Record<string, unknown> = {}) {
    const m = await montar(env);
    contenedor(m.d, "conectada");
    await m.d.vigilar();
    return m;
  }

  it("envía y devuelve lo del contenedor; recuerda los ids enviados", async () => {
    const { d } = await listo();
    const r = await d.enviar(cuerpo());
    expect(r.status).toBe(200);
    expect(r.cuerpo).toMatchObject({ ok: true, ids: ["ID1", "ID2"] });
    expect(d.llamadas.at(-1)).toMatchObject({ url: "http://contenedor/enviar", metodo: "POST" });
    expect((await d.enviadosRecientes()).map((e: any) => e.id)).toEqual(["ID1", "ID2"]);
  });

  it("valida ANTES de despertar al contenedor", async () => {
    const { d } = await listo();
    const antes = d.llamadas.length;
    expect((await d.enviar("no es json")).status).toBe(400);
    expect((await d.enviar(JSON.stringify({ para: "120363025246125486@g.us", chunks: ["x"] }))).status).toBe(400);
    expect((await d.enviar(JSON.stringify({ para: "60261919", medios: [{ tipo: "imagen", url: "http://dcasapty.com/a.jpg" }] }))).status).toBe(422);
    expect((await d.enviar(JSON.stringify({ para: "60261919", medios: [{ tipo: "imagen", url: "https://evil.example.org/a.jpg" }] }))).status).toBe(422); // fuera de la lista de dominios
    expect(d.llamadas.length).toBe(antes);
  });

  it("tope por minuto: espera si falta poco, rechaza (429) si falta mucho", async () => {
    const { d } = await listo({ LIMITE_POR_MINUTO: "4" });
    expect((await d.enviar(cuerpo("60261919", ["a", "b", "c"]))).status).toBe(200);
    // Quedan 1 de 4: pedir 2 más no cabe; la espera (hasta que caduque el primero) es de 60 s > 20 s.
    const r = await d.enviar(cuerpo("60262020", ["d", "e"]));
    expect(r.status).toBe(429);
    expect(r.cuerpo).toMatchObject({ limite: "minuto" });
    expect((r.cuerpo as any).reintentar_en_s).toBeGreaterThan(0);

    // Si solo faltan unos segundos, ESPERA y envía.
    avanzar(45_000);
    const espera = d.enviar(cuerpo("60262020", ["d", "e"]));
    await vi.advanceTimersByTimeAsync(16_000);
    expect((await espera).status).toBe(200);
  });

  it("tope por día", async () => {
    const { d } = await listo({ LIMITE_POR_DIA: "5", LIMITE_POR_MINUTO: "60" });
    expect((await d.enviar(cuerpo("60261919", ["1", "2", "3"]))).status).toBe(200);
    avanzar(2 * MIN);
    expect((await d.enviar(cuerpo("60262020", ["4", "5"]))).status).toBe(200);
    avanzar(2 * MIN);
    const r = await d.enviar(cuerpo("60263030", ["6"]));
    expect(r.status).toBe(429);
    expect(r.cuerpo).toMatchObject({ limite: "dia" });
  });

  it("tope de personas nuevas por día (a quienes no nos han escrito antes); los que escribieron no cuentan", async () => {
    const { d } = await listo({ LIMITE_FRIOS_DIA: "2", LIMITE_POR_MINUTO: "60" });
    await d.marcarEntrante("50760269001"); // este sí nos escribió
    expect((await d.enviar(cuerpo("60269001", ["hola"]))).status).toBe(200);
    expect((await d.enviar(cuerpo("60269002", ["hola"]))).status).toBe(200);
    expect((await d.enviar(cuerpo("60269003", ["hola"]))).status).toBe(200);
    const r = await d.enviar(cuerpo("60269004", ["hola"]));
    expect(r.status).toBe(429);
    expect(r.cuerpo).toMatchObject({ limite: "frios" });
    // Seguirle escribiendo a uno de los dos primeros, sí.
    expect((await d.enviar(cuerpo("60269002", ["otra cosa"]))).status).toBe(200);
  });

  it("lo que no salió se devuelve al tope (un fallo del contenedor no gasta cuota)", async () => {
    const { d } = await listo({ LIMITE_POR_DIA: "3", LIMITE_POR_MINUTO: "60" });
    d.manejador = () => jsonResp({ ok: false, error: "No hay conexión con WhatsApp.", estado: "cerrada" }, 409);
    for (let i = 0; i < 5; i++) expect((await d.enviar(cuerpo("60261919", ["a", "b"]))).status).toBe(409);
    contenedor(d, "conectada");
    expect((await d.enviar(cuerpo("60261919", ["a", "b"]))).status).toBe(200); // la cuota sigue intacta
  });

  it("si salió una parte (502 parcial), solo cuenta lo que salió", async () => {
    const { d } = await listo({ LIMITE_POR_DIA: "4", LIMITE_POR_MINUTO: "60" });
    d.manejador = () => jsonResp({ ok: false, error: "socket cerrado", parcial: true, ids: ["X1"], enviados: { chunks: 1, medios: 0 } }, 502);
    expect((await d.enviar(cuerpo("60261919", ["a", "b", "c"]))).status).toBe(502);
    contenedor(d, "conectada");
    avanzar(2 * MIN);
    expect((await d.enviar(cuerpo("60261919", ["a", "b", "c"]))).status).toBe(200); // 1 + 3 = 4 ≤ 4
  });

  it("dos envíos a la vez no pasan los dos el mismo tope (se reserva antes de enviar)", async () => {
    const { d } = await listo({ LIMITE_POR_MINUTO: "3" });
    // El «contenedor» tarda un poco: sin la reserva previa, los dos verían el tope libre.
    d.manejador = async () => {
      await asentar();
      return jsonResp({ ok: true, ids: ["A", "B"], enviados: { chunks: 2, medios: 0 } });
    };
    const [a, b] = await Promise.all([d.enviar(cuerpo("60261919", ["1", "2"])), d.enviar(cuerpo("60262020", ["3", "4"]))]);
    expect([a.status, b.status]).toEqual([200, 429]); // 2 + 2 > 3: el segundo ve la reserva del primero
    expect(b.cuerpo).toMatchObject({ limite: "minuto" });
  });

  it("si el contenedor no contesta, 502 y la reserva se devuelve", async () => {
    const { d } = await listo({ LIMITE_POR_DIA: "2", LIMITE_POR_MINUTO: "60" });
    d.manejador = () => {
      throw new Error("conexión rota");
    };
    expect((await d.enviar(cuerpo("60261919", ["a", "b"]))).status).toBe(502);
    contenedor(d, "conectada");
    expect((await d.enviar(cuerpo("60261919", ["a", "b"]))).status).toBe(200);
  });
});

describe("estado público", () => {
  it("conectado, con sesión completa y sin ningún secreto", async () => {
    const { d } = await montar();
    contenedor(d, "conectada");
    await d.vigilar();
    await d.kvSet("creds", JSON.stringify({ nextPreKeyId: 813, firstUnuploadedPreKeyId: 813, noiseKey: "SECRETO" }), "1");
    const e = await d.estadoPublico();
    expect(e).toMatchObject({
      ok: true,
      estado: "conectado",
      conectado: true,
      desconectado_min: null,
      activo: true,
      sesion: { vinculado: true, instalacionCompleta: true, siguiente: 813, sinSubir: 813 },
      copias: { r2: "apagada", guardadas: 0 },
      pendientes: 0,
    });
    const texto = JSON.stringify(e);
    for (const secreto of [TOKEN, CLAVE, "SECRETO", await derivarTokenContenedor(TOKEN)]) expect(texto).not.toContain(secreto);
  });

  it("muestra cuánto del ritmo permitido se está usando", async () => {
    const { d } = await montar({ LIMITE_POR_MINUTO: "10", LIMITE_FRIOS_DIA: "5" });
    contenedor(d, "conectada");
    await d.vigilar();
    await d.enviar(JSON.stringify({ para: "60261919", chunks: ["a", "b"] }));
    await d.enviar(JSON.stringify({ para: "60262020", chunks: ["c"] }));
    const e = await d.estadoPublico();
    expect(e.cuotas).toEqual({
      ultimo_minuto: 3,
      ultimas_24h: 3,
      personas_nuevas_24h: 2,
      limites: { por_minuto: 10, por_dia: 400, por_destinatario_hora: 30, personas_nuevas_por_dia: 5 },
    });
  });

  it("necesita QR", async () => {
    const { d } = await montar();
    contenedor(d, "esperando-qr");
    await d.vigilar();
    expect(await d.estadoPublico()).toMatchObject({ estado: "necesita_qr", conectado: false });
  });

  it("desconectado desde hace N minutos", async () => {
    const { d } = await montar();
    contenedor(d, "conectada");
    await d.vigilar();
    contenedor(d, "cerrada");
    avanzar(MIN);
    await d.vigilar();
    avanzar(7 * MIN);
    const e = await d.estadoPublico();
    expect(e).toMatchObject({ estado: "desconectado", conectado: false, desconectado_min: 7 });
    expect(e.desconectado_desde).toBe(new Date(T0 + MIN).toISOString());
  });

  it("apagado: no despierta al contenedor", async () => {
    const { d } = await montar({ PUENTE_ACTIVO: "off" });
    const e = await d.estadoPublico();
    expect(e).toMatchObject({ estado: "apagado", conectado: false, activo: false });
    expect(d.llamadas).toHaveLength(0);
  });

  it("si el contenedor no contesta en 4 s, el estado igual responde con lo que tiene", async () => {
    const { d } = await montar();
    await d.kvGet("x"); // calienta el cifrador: así el tope de 4 s se arma sin esperas reales de por medio
    d.manejador = () => new Promise<Response>(() => {});
    const p = d.estadoPublico();
    await asentar();
    await vi.advanceTimersByTimeAsync(4100);
    const e = await p;
    expect(e.contenedor).toMatchObject({ error: expect.stringContaining("4 s") });
  });

  it("QR: lo pasa tal cual; si tarda, devuelve 202 «arrancando»", async () => {
    const { d } = await montar();
    contenedor(d, "esperando-qr");
    expect(await d.qr()).toMatchObject({ status: 200, cuerpo: { qr: "data:image/png;base64,QQQ" } });
    d.manejador = () => new Promise<Response>(() => {});
    const p = d.qr();
    await vi.advanceTimersByTimeAsync(4100);
    expect(await p).toEqual({ status: 202, cuerpo: { qr: null, estado: "arrancando" } });
  });

  it("desvincular pide al contenedor cerrar la sesión", async () => {
    const { d } = await montar();
    contenedor(d, "conectada");
    await d.vigilar();
    expect(await d.desvincular()).toEqual({ status: 200, cuerpo: { ok: true } });
    expect(d.llamadas.at(-1).url).toBe("http://contenedor/logout");
  });
});

describe("mantenimiento", () => {
  it("podar y recifrar", async () => {
    const { d } = await montar();
    contenedor(d);
    await d.vigilar();
    await d.kvLote({ escribir: Object.fromEntries(Array.from({ length: 1100 }, (_, i) => [`pre-key-${i}`, "x"])) }, "1");
    expect(await d.podar()).toEqual({ borradas: 100, conservadas: 1000 });
    expect(await d.recifrar()).toMatchObject({ recifradas: 0 });
  });

  it("el diario nuevo trae los campos esperados", () => {
    expect(Object.keys(diarioNuevo()).sort()).toEqual(
      expect.arrayContaining(["avisoActivo", "desconectadoSeguidos", "sinConexionDesde", "ultimaConexionVista", "ultimoLatidoEn"]),
    );
  });
});
