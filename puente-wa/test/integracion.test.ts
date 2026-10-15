import { afterEach, describe, expect, it, vi } from "vitest";
import { crearCtx, jsonResp } from "./ayuda/contenedor-falso";
import { sqlDePrueba } from "./ayuda/sql";

vi.mock("@cloudflare/containers", async () => {
  const m = await import("./ayuda/contenedor-falso");
  return { Container: m.ContenedorBase };
});

import { crearNucleo } from "../contenedor/nucleo.mjs";
import { RITMO_POR_DEFECTO } from "../contenedor/lib/ritmo.mjs";
import { validarWebhook } from "../contenedor/lib/contrato.mjs";
import { PuenteWa } from "../src/puente-do";
import { manejar } from "../src/router";
import { crearBaileysFalso, msgTexto, msgImagen } from "./ayuda/baileys";

// Recorre la cadena COMPLETA con las piezas reales de punta a punta, sin WhatsApp ni Cloudflare:
//
//   Baileys (doble) → núcleo del contenedor → [HTTP] → router → Durable Object → almacén cifrado
//                                                              → Worker juan (doble)
//   Worker juan (doble) → router (/api/enviar) → Durable Object (topes) → núcleo → Baileys (doble)
//
// Es la prueba que NO se hizo en el CRM de origen: «¿la señal que miramos salió verde, o el sistema funciona?».

// Valores de PRUEBA: no son ningún secreto real.
const TOKEN = "token-de-prueba-0123456789-abcdefghij";
const CLAVE = "clave-de-prueba-para-la-sesion-0123456789";
const BASE = "https://dcasa-puente-wa-staging.test";

function juanFalso(...estados: number[]) {
  let i = 0;
  const recibidos: { cuerpo: any; cabeceras: Headers }[] = [];
  return {
    recibidos,
    fetch: vi.fn(async (r: Request) => {
      recibidos.push({ cuerpo: JSON.parse(await r.clone().text()), cabeceras: r.headers });
      return new Response("{}", { status: estados[Math.min(i++, estados.length - 1)] ?? 200 });
    }),
  };
}

async function montar(juan = juanFalso(200)) {
  const ctx = crearCtx(sqlDePrueba());
  const env: any = { PUENTE_ACTIVO: "on", PUENTE_BASE_URL: BASE, MEDIOS_HOSTS_PERMITIDOS: "dcasapty.com", WA_TOKEN: TOKEN, WA_SESION_CLAVE: CLAVE, JUAN: juan, LIMITE_POR_MINUTO: "60" };
  const d: any = new PuenteWa(ctx as any, env);
  await Promise.all(ctx.listo);
  const baileys = crearBaileysFalso();

  /** Lo que haría `servidor.mjs`: llamar al Worker con el token y la época con los que ARRANCÓ el contenedor. */
  const arrancarContenedor = () => {
    const token = d.envVars.PUENTE_TOKEN as string;
    const epoca = d.envVars.PUENTE_EPOCA as string;
    return (ruta: string, init: any = {}) =>
      manejar(new Request(`${BASE}${ruta}`, { ...init, headers: { ...(init.headers ?? {}), authorization: `Bearer ${token}`, "x-wa-epoca": epoca } }), env, () => d);
  };

  await d.vigilar(); // arranca el «contenedor» (la época sube a 1 y el entorno queda fijado)
  const puente = arrancarContenedor();
  const nucleo = crearNucleo({
    baileys,
    puente: puente as any,
    qr: { toDataURL: async (t: string) => `data:image/png;base64,${btoa(t)}` },
    logger: {},
    descargar: async (_url: string, o: any) => ({ ok: true, bytes: Buffer.from("FOTO"), mime: o.tipo === "imagen" ? "image/jpeg" : "application/pdf" }),
    dormir: async () => {},
    azar: () => 0.5,
    log: { log: () => {}, error: () => {} },
    config: { ritmo: RITMO_POR_DEFECTO, hostsPermitidos: ["dcasapty.com"] },
  });
  // El contenedor del Durable Object ES este núcleo.
  d.manejador = async (u: URL, init?: RequestInit) => {
    const r = await nucleo.manejar({ metodo: init?.method ?? "GET", ruta: u.pathname, cuerpo: typeof init?.body === "string" ? init.body : "" });
    return jsonResp(r.cuerpo, r.status);
  };
  const juanLlama = (ruta: string, init: RequestInit = {}) =>
    manejar(new Request(`${BASE}${ruta}`, { ...init, headers: { authorization: `Bearer ${TOKEN}` } }), env, () => d);

  return { ctx, env, d, baileys, nucleo, puente, juan, juanLlama, arrancarContenedor };
}

const asentar = async () => {
  for (let i = 0; i < 500; i++) await Promise.resolve();
};
// Espera (con tope) a que algo se cumpla. El cifrado de la sesión usa WebCrypto, que se resuelve en un hilo de Node y no
// en la cola de microtareas: contar vueltas con `asentar()` no basta con la máquina cargada (un runner de CI), y esa
// carrera hacía fallar de vez en cuando la prueba de «vinculado» (sesion.vinculado: false).
const esperarA = async (cond: () => boolean | Promise<boolean>, tope = 5000) => {
  const limite = Date.now() + tope;
  while (!(await cond())) {
    if (Date.now() > limite) throw new Error("tiempo agotado esperando que se guardara la sesión");
    await new Promise((r) => setTimeout(r, 5));
  }
};
let activos: { nucleo: { detener(): void } }[] = [];
afterEach(() => {
  for (const a of activos) a.nucleo.detener();
  activos = [];
  vi.restoreAllMocks();
});
async function listo(juan?: ReturnType<typeof juanFalso>) {
  const m = await montar(juan);
  activos.push(m);
  await m.nucleo.arrancar();
  return m;
}

describe("emparejar y reconectar: la sesión vive cifrada en el Durable Object", () => {
  it("las 812 llaves del emparejamiento se suben y se releen en una petición cada vez, cifradas", async () => {
    const m = await listo();
    const keys = (m.baileys.ultimo.config.auth as any).state?.keys ?? (m.baileys.ultimo.config.auth as any).keys;
    const datos: Record<string, any> = {};
    for (let i = 1; i <= 812; i++) datos[String(i)] = { private: `PRIVADA-${i}`, public: `PUBLICA-${i}` };
    const t0 = Date.now();
    await keys.set({ "pre-key": datos });
    const leidas = await keys.get("pre-key", Object.keys(datos));
    expect(Date.now() - t0).toBeLessThan(5000); // Baileys corta a los 30 s
    expect(Object.keys(leidas)).toHaveLength(812);
    expect(leidas["812"]).toEqual({ private: "PRIVADA-812", public: "PUBLICA-812" });

    // En el almacenamiento del DO: 812 filas, ninguna en claro.
    const volcado = JSON.stringify(m.ctx.storage.sql.exec("SELECT * FROM wa_auth").toArray());
    expect(m.ctx.storage.sql.exec("SELECT COUNT(*) AS n FROM wa_auth").toArray()[0].n).toBe(812);
    expect(volcado).not.toContain("PRIVADA");
  });

  it("queda vinculado y 'terminó de instalarse' (la señal que de verdad importa)", async () => {
    const m = await listo();
    const sock = m.baileys.ultimo;
    sock.conexion({ qr: "2@QR" });
    await asentar();
    expect((await m.juanLlama("/api/estado").then((r) => r.json())) as any).toMatchObject({ estado: "necesita_qr", conectado: false });

    // Baileys guarda sus credenciales al emparejar y sube las llaves.
    const creds = (sock.config.auth as any).creds ?? (sock.config.auth as any).state.creds;
    Object.assign(creds, { me: { id: "50760269999:3@s.whatsapp.net" }, nextPreKeyId: 813, firstUnuploadedPreKeyId: 813 });
    sock.ev.emit("creds.update", {});
    await asentar();
    await esperarA(async () => ((await m.d.kvGet("creds")) ?? "").includes("813"));
    sock.conexion({ connection: "open" });
    await m.d.vigilar();

    const e: any = await (await m.juanLlama("/api/estado")).json();
    expect(e).toMatchObject({
      estado: "conectado",
      conectado: true,
      sesion: { vinculado: true, siguiente: 813, sinSubir: 813, instalacionCompleta: true },
    });
    expect(JSON.stringify(e)).not.toContain("50760269999"); // el número sale enmascarado
  });

  it("tras un reinicio del contenedor reconecta con la sesión guardada: sin QR", async () => {
    const m = await listo();
    const creds = (m.baileys.ultimo.config.auth as any).creds ?? (m.baileys.ultimo.config.auth as any).state.creds;
    Object.assign(creds, { registrationId: 4242, nextPreKeyId: 10, firstUnuploadedPreKeyId: 10 });
    m.baileys.ultimo.ev.emit("creds.update", {});
    await asentar();
    await esperarA(async () => ((await m.d.kvGet("creds")) ?? "").includes("4242"));

    await m.d.matar(); // se destruye y vuelve con época nueva
    const puente2 = m.arrancarContenedor();
    const baileys2 = crearBaileysFalso();
    const nucleo2 = crearNucleo({ baileys: baileys2, puente: puente2 as any, qr: { toDataURL: async () => "x" }, logger: {}, descargar: async () => ({}), dormir: async () => {}, log: { log() {}, error() {} } });
    activos.push({ nucleo: nucleo2 });
    await nucleo2.arrancar();
    expect(nucleo2.estado.credencialesVenianDeAlmacen).toBe(true);
    const auth: any = baileys2.ultimo.config.auth;
    expect((auth.creds ?? auth.state.creds).registrationId).toBe(4242);
  });

  it("un contenedor viejo (época anterior) ya no puede pisar la sesión", async () => {
    const m = await listo();
    const credsViejas = (m.baileys.ultimo.config.auth as any).creds ?? (m.baileys.ultimo.config.auth as any).state.creds;
    Object.assign(credsViejas, { registrationId: 1111 });
    m.baileys.ultimo.ev.emit("creds.update", {});
    await asentar();
    await esperarA(async () => ((await m.d.kvGet("creds")) ?? "").includes("1111"));

    await m.d.matar(); // arranca el contenedor nuevo; el viejo quedó «zombi»
    const nuevoPuente = m.arrancarContenedor();
    await nuevoPuente("/puente/kv?clave=creds", { method: "PUT", body: JSON.stringify({ registrationId: 2222 }) });

    // El zombi intenta guardar lo suyo: se rechaza, y la sesión sigue siendo la del contenedor vigente.
    m.baileys.ultimo.ev.emit("creds.update", {});
    await asentar();
    await esperarA(() => (m.nucleo.estado.ultimoError ?? "").includes("saveCreds"));
    expect(m.nucleo.estado.ultimoError).toContain("saveCreds");
    expect(m.nucleo.estado.ultimoError).toContain("409");
    expect(await m.d.kvGet("creds")).toBe(JSON.stringify({ registrationId: 2222 }));
  });
});

describe("entrante: cliente → contenedor → Worker → Juan", () => {
  it("el JSON del contrato llega a Juan con el token compartido", async () => {
    const m = await listo();
    m.baileys.ultimo.conexion({ connection: "open" });
    m.baileys.ultimo.upsert([msgTexto("Hola, ¿tienen camas queen?", { id: "E1" })]);
    await asentar();
    expect(m.juan.recibidos).toHaveLength(1);
    const { cuerpo, cabeceras } = m.juan.recibidos[0];
    expect(cuerpo).toMatchObject({ id_mensaje: "E1", de: "50760261919", tipo: "texto", texto: "Hola, ¿tienen camas queen?", propio: false });
    expect(validarWebhook(cuerpo)).toEqual([]);
    expect(cabeceras.get("x-wa-token")).toBe(TOKEN);
    expect(m.nucleo.estado.entregasFallidas).toBe(0);
  });

  it("una foto llega a Juan en base64", async () => {
    const m = await listo();
    m.baileys.ultimo.conexion({ connection: "open" });
    m.baileys.downloadMediaMessage.mockResolvedValue(Buffer.from("PIXELES"));
    m.baileys.ultimo.upsert([msgImagen({ id: "E2", caption: "mi comprobante" })]);
    await asentar();
    expect(m.juan.recibidos[0].cuerpo).toMatchObject({ tipo: "imagen", texto: "mi comprobante", medio: { base64: btoa("PIXELES"), mime: "image/jpeg" } });
  });

  it("si Juan está caído NO se pierde el mensaje: queda guardado y se entrega cuando vuelve", async () => {
    const juan = juanFalso(500, 500, 200);
    const m = await listo(juan);
    m.baileys.ultimo.conexion({ connection: "open" });
    m.baileys.ultimo.upsert([msgTexto("Quiero una cama", { id: "E3" })]);
    await asentar();
    await new Promise((r) => setTimeout(r, 700)); // la espera real de 500 ms entre los dos intentos rápidos
    await asentar();
    expect(m.nucleo.estado.entregasFallidas).toBe(0); // el contenedor recibió un 202: ya está a salvo
    expect((await m.d.estadoPublico()).pendientes).toBe(1);

    await m.d.vigilar(); // Juan ya contesta 200
    expect((await m.d.estadoPublico()).pendientes).toBe(0);
    expect(juan.recibidos.at(-1)!.cuerpo.id_mensaje).toBe("E3");
  });

  it("la vendedora desde el teléfono: propio:true, y el eco de lo enviado por Juan NO", async () => {
    const m = await listo();
    const sock = m.baileys.ultimo;
    sock.conexion({ connection: "open" });
    sock.upsert([msgTexto("Buenas, le atiende Marisol", { id: "E4", fromMe: true })]);
    await asentar();
    expect(m.juan.recibidos.map((r) => r.cuerpo)).toEqual([expect.objectContaining({ id_mensaje: "E4", propio: true, nombre: null })]);

    // Juan contesta por /api/enviar → el eco del propio envío no vuelve a Juan como si fuera la vendedora.
    const r = await m.juanLlama("/api/enviar", { method: "POST", body: JSON.stringify({ para: "50760261919", chunks: ["Hola, soy el asistente."] }) });
    expect(r.status).toBe(200);
    await asentar();
    expect(m.juan.recibidos).toHaveLength(1);
  });
});

describe("saliente: Juan → /api/enviar → topes → contenedor → WhatsApp", () => {
  it("texto, imagen con pie y documento: salen como mensajes de WhatsApp", async () => {
    const m = await listo();
    const sock = m.baileys.ultimo;
    sock.conexion({ connection: "open" });
    const r = await m.juanLlama("/api/enviar", {
      method: "POST",
      body: JSON.stringify({
        para: "6026-1919",
        chunks: ["Mira esta cama."],
        medios: [
          { tipo: "imagen", url: "https://dcasapty.com/web/image/1", pie: "Cama Queen HK-BF-022" },
          { tipo: "documento", url: "https://dcasapty.com/cot.pdf", nombre: "Cotización.pdf" },
        ],
      }),
    });
    const c: any = await r.json();
    expect(r.status).toBe(200);
    expect(c).toMatchObject({ ok: true, enviados: { chunks: 1, medios: 2 } });
    const contenidos = sock.enviados.map((e) => e.args[1]);
    expect(contenidos[0]).toEqual({ text: "Mira esta cama." });
    expect(contenidos[1]).toMatchObject({ caption: "Cama Queen HK-BF-022" });
    expect(contenidos[2]).toMatchObject({ fileName: "Cotización.pdf" });
    expect(sock.enviados.every((e) => e.args[0] === "50760261919@s.whatsapp.net")).toBe(true);
    // Los ids quedaron recordados en el Durable Object (sobreviven a un reinicio del contenedor).
    expect((await m.d.enviadosRecientes()).map((e: any) => e.id)).toEqual(c.ids);
  });

  it("los topes los aplica el Durable Object y Juan recibe un 429 con Retry-After", async () => {
    const m = await listo();
    m.baileys.ultimo.conexion({ connection: "open" });
    m.env.LIMITE_POR_DIA = "2";
    const enviar = (para: string, n: number) =>
      m.juanLlama("/api/enviar", { method: "POST", body: JSON.stringify({ para, chunks: Array.from({ length: n }, (_, i) => `m${i}`) }) });
    expect((await enviar("60261919", 2)).status).toBe(200);
    const r = await enviar("60262020", 1);
    expect(r.status).toBe(429);
    expect(r.headers.get("retry-after")).not.toBe(null);
    expect(m.baileys.ultimo.enviados).toHaveLength(2); // lo rechazado no llegó a WhatsApp
  });

  it("a un grupo, un estado o una URL interna: rechazado antes de tocar WhatsApp", async () => {
    const m = await listo();
    m.baileys.ultimo.conexion({ connection: "open" });
    for (const cuerpo of [
      { para: "120363025246125486@g.us", chunks: ["x"] },
      { para: "status@broadcast", chunks: ["x"] },
      { para: "60261919", medios: [{ tipo: "imagen", url: "https://169.254.169.254/latest/meta-data/" }] },
      { para: "60261919", medios: [{ tipo: "imagen", url: "http://dcasapty.com/a.jpg" }] },
    ]) {
      const r = await m.juanLlama("/api/enviar", { method: "POST", body: JSON.stringify(cuerpo) });
      expect([400, 422]).toContain(r.status);
    }
    expect(m.baileys.ultimo.enviados).toHaveLength(0);
  });

  it("sin conexión con WhatsApp: 409 (y la cuota no se gasta)", async () => {
    const m = await listo(); // el socket existe pero nunca abrió
    m.env.LIMITE_POR_DIA = "2";
    for (let i = 0; i < 5; i++) {
      const r = await m.juanLlama("/api/enviar", { method: "POST", body: JSON.stringify({ para: "60261919", chunks: ["a", "b"] }) });
      expect(r.status).toBe(409);
    }
    m.baileys.ultimo.conexion({ connection: "open" });
    expect((await m.juanLlama("/api/enviar", { method: "POST", body: JSON.stringify({ para: "60261919", chunks: ["a", "b"] }) })).status).toBe(200);
  });
});
