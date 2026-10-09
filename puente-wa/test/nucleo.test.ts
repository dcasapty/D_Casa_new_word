import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { crearNucleo, QR_VENCE_MS, VIGILANTE_MS } from "../contenedor/nucleo.mjs";
import { validarWebhook } from "../contenedor/lib/contrato.mjs";
import { RITMO_POR_DEFECTO } from "../contenedor/lib/ritmo.mjs";
import {
  CLIENTE,
  crearBaileysFalso,
  crearPuenteFalso,
  msgAudio,
  msgImagen,
  msgTexto,
  type SockFalso,
} from "./ayuda/baileys";

// Pruebas del núcleo del contenedor con un doble de Baileys. NO se toca WhatsApp.

const QR_CRUDO = "2@QR-CRUDO-DE-PRUEBA,abc,def";

function montar(config: Record<string, unknown> = {}, descargarPersonalizado?: (...a: any[]) => Promise<any>) {
  const baileys = crearBaileysFalso();
  const puente = crearPuenteFalso();
  const log = { log: vi.fn(), error: vi.fn() };
  const qr = { toDataURL: vi.fn(async (t: string) => `data:image/png;base64,${Buffer.from(t).toString("base64")}`) };
  const descargar = vi.fn(
    descargarPersonalizado ?? (async (url: string, o: any) => ({ ok: true, bytes: Buffer.from("BYTES-DEL-ARCHIVO"), mime: o.tipo === "imagen" ? "image/jpeg" : "application/pdf", url })),
  );
  /** `dormir` no espera: solo mueve el reloj virtual del socket vigente. */
  const dormido: number[] = [];
  const dormir = async (ms: number) => {
    dormido.push(ms);
    if (baileys.ultimo) baileys.ultimo.reloj.t += ms;
    await Promise.resolve();
  };
  const nucleo = crearNucleo({
    baileys,
    puente: puente as any,
    qr,
    logger: {},
    descargar,
    dormir,
    azar: () => 0.5,
    log,
    config: { ritmo: RITMO_POR_DEFECTO, hostsPermitidos: [], ...config },
  });
  return { baileys, puente, log, qr, descargar, dormido, nucleo, get sock(): SockFalso { return baileys.ultimo; } };
}
type M = ReturnType<typeof montar>;

async function conectado(m: M) {
  await m.nucleo.arrancar();
  m.sock.conexion({ connection: "open" });
  return m.sock;
}

const post = (m: M, ruta: string, cuerpo: unknown) =>
  m.nucleo.manejar({ metodo: "POST", ruta, cuerpo: typeof cuerpo === "string" ? cuerpo : JSON.stringify(cuerpo) });
const get = (m: M, ruta: string) => m.nucleo.manejar({ metodo: "GET", ruta });
/** Deja correr las promesas pendientes (la cola de entrantes trabaja en segundo plano). */
const asentar = async () => {
  // Solo microtareas: sirve con relojes reales y con los falsos (vi.useFakeTimers también finge setImmediate).
  for (let i = 0; i < 500; i++) await Promise.resolve();
};

let activos: M[] = [];
function nuevo(...args: Parameters<typeof montar>) {
  const m = montar(...args);
  activos.push(m);
  return m;
}
afterEach(() => {
  for (const m of activos) m.nucleo.detener();
  activos = [];
  vi.useRealTimers();
});

describe("arranque", () => {
  it("abre el socket con las opciones que reducen el riesgo", async () => {
    const m = nuevo();
    await m.nucleo.arrancar();
    expect(m.baileys.makeWASocket).toHaveBeenCalledOnce();
    const cfg = m.sock.config;
    expect(cfg.syncFullHistory).toBe(false);
    expect(cfg.markOnlineOnConnect).toBe(false); // el teléfono de la dueña sigue sonando
    expect(cfg.browser[0]).toContain("DCASA");
    expect(cfg.version).toEqual([2, 3000, 1]);
    expect(typeof cfg.getMessage).toBe("function");
    expect(m.nucleo.estado.conexion).toBe("arrancando");
  });

  it("si no se puede consultar la versión del protocolo, arranca igual con la de la librería", async () => {
    const m = nuevo();
    m.baileys.fetchLatestBaileysVersion.mockRejectedValueOnce(new Error("fetch failed"));
    await m.nucleo.arrancar();
    expect(m.baileys.makeWASocket).toHaveBeenCalledOnce();
    expect(m.sock.config.version).toBeUndefined();
    expect(m.nucleo.estado.avisoVersion).toContain("sin consultar");
  });

  it("con credenciales guardadas las usa (no pide QR); sin ellas crea unas nuevas", async () => {
    const con = nuevo();
    con.puente.kv.set("creds", JSON.stringify({ registrationId: 777, nextPreKeyId: 5, firstUnuploadedPreKeyId: 5 }));
    await con.nucleo.arrancar();
    expect(con.sock.config.auth.state?.creds ?? con.sock.config.auth.creds).toMatchObject({ registrationId: 777 });
    expect(con.nucleo.estado.credencialesVenianDeAlmacen).toBe(true);

    const sin = nuevo();
    await sin.nucleo.arrancar();
    expect(sin.sock.config.auth.creds).toMatchObject({ registrationId: 1234 });
    expect(sin.nucleo.estado.credencialesVenianDeAlmacen).toBe(false);
  });

  it("si el Worker no contesta al arrancar, reintenta con espera creciente y el proceso sigue en pie", async () => {
    const m = nuevo();
    m.puente.fallar(3); // tres caídas de red seguidas
    await m.nucleo.arrancar();
    expect(m.baileys.makeWASocket).toHaveBeenCalledOnce();
    expect(m.dormido.slice(0, 3)).toEqual([2000, 4000, 8000]);
  });

  it("guarda las credenciales cuando Baileys las actualiza", async () => {
    const m = nuevo();
    await m.nucleo.arrancar();
    m.puente.llamadas.length = 0;
    m.sock.ev.emit("creds.update", {});
    await asentar();
    const put = m.puente.llamadas.find((l) => l.metodo === "PUT");
    expect(put?.ruta).toBe("/puente/kv?clave=creds");
  });
});

describe("el QR", () => {
  it("se sirve mientras sirve y NUNCA aparece en los registros", async () => {
    const m = nuevo();
    await m.nucleo.arrancar();
    m.sock.conexion({ qr: QR_CRUDO });
    await asentar();
    expect(m.nucleo.estado.conexion).toBe("esperando-qr");
    const r = await get(m, "/qr");
    expect(r.status).toBe(200);
    expect(r.cuerpo.qr).toContain("data:image/png;base64,");
    expect(r.cuerpo).toMatchObject({ generados: 1, estado: "esperando-qr" });
    expect(r.cuerpo.edadMs).toBeGreaterThanOrEqual(0);

    const registros = JSON.stringify([...m.log.log.mock.calls, ...m.log.error.mock.calls]);
    expect(registros).not.toContain(QR_CRUDO);
    expect(registros).not.toContain(Buffer.from(QR_CRUDO).toString("base64"));
    expect(registros).not.toContain("data:image");
    expect(registros).toContain("QR nuevo disponible (#1)");
  });

  it("un QR de más de 45 s ya no se sirve (el teléfono diría «revisa tu conexión»)", async () => {
    vi.useFakeTimers();
    const m = nuevo();
    await m.nucleo.arrancar();
    m.sock.conexion({ qr: QR_CRUDO });
    await vi.advanceTimersByTimeAsync(10);
    expect((await get(m, "/qr")).cuerpo.qr).not.toBe(null);
    await vi.advanceTimersByTimeAsync(QR_VENCE_MS - 100);
    expect((await get(m, "/qr")).cuerpo.qr).not.toBe(null);
    await vi.advanceTimersByTimeAsync(200);
    expect((await get(m, "/qr")).cuerpo.qr).toBe(null);
  });

  it("con la sesión conectada no se sirve ningún QR (cualquiera vincularía OTRO teléfono)", async () => {
    const m = nuevo();
    await m.nucleo.arrancar();
    m.sock.conexion({ qr: QR_CRUDO });
    await asentar();
    m.sock.conexion({ connection: "open" });
    expect(m.nucleo.estado.conexion).toBe("conectada");
    expect((await get(m, "/qr")).cuerpo.qr).toBe(null);
    // aunque llegara otro QR rezagado
    m.sock.conexion({ qr: QR_CRUDO });
    await asentar();
    m.nucleo.estado.conexion = "conectada";
    expect((await get(m, "/qr")).cuerpo.qr).toBe(null);
  });

  it("el estado y los registros enmascaran el número vinculado", async () => {
    const m = nuevo();
    await conectado(m);
    expect(m.nucleo.estado.vinculadoComo).toContain("***");
    expect(m.nucleo.estado.vinculadoComo).not.toContain("50760269999");
    expect(JSON.stringify((await get(m, "/estado")).cuerpo)).not.toContain("50760269999");
  });
});

describe("desvinculación y reconexión", () => {
  it("si el teléfono desvincula (401): borra las credenciales y NO reconecta", async () => {
    vi.useFakeTimers();
    const m = nuevo();
    m.puente.kv.set("creds", JSON.stringify({ registrationId: 1 }));
    await m.nucleo.arrancar();
    m.sock.conexion({ connection: "open" });
    m.sock.cierre(401);
    await vi.advanceTimersByTimeAsync(5);
    expect(m.nucleo.estado.conexion).toBe("desvinculada");
    expect(m.puente.kv.has("creds")).toBe(false);
    await vi.advanceTimersByTimeAsync(5 * 60_000);
    expect(m.baileys.makeWASocket).toHaveBeenCalledOnce(); // no insiste: generaría un QR tras otro
    expect(m.nucleo.estado.vinculadoComo).toBe(null);
  });

  it("cualquier otro cierre reconecta con espera creciente: 3 s, 6 s, 12 s…", async () => {
    vi.useFakeTimers();
    const m = nuevo();
    await m.nucleo.arrancar();
    for (const [i, espera] of [3000, 6000, 12_000].entries()) {
      m.baileys.ultimo.cierre(428);
      await vi.advanceTimersByTimeAsync(espera - 1);
      expect(m.baileys.makeWASocket).toHaveBeenCalledTimes(i + 1);
      await vi.advanceTimersByTimeAsync(2);
      expect(m.baileys.makeWASocket).toHaveBeenCalledTimes(i + 2);
    }
  });

  it("la espera tiene tope de 60 s, y al conectar se reinicia la cuenta", async () => {
    vi.useFakeTimers();
    const m = nuevo();
    await m.nucleo.arrancar();
    /** Espera exactamente lo que anunció el núcleo y devuelve cuánto era. */
    const esperarElRetroceso = async () => {
      const espera = Date.parse(m.nucleo.estado.proximoIntentoEn!) - Date.now();
      await vi.advanceTimersByTimeAsync(espera + 1);
      return espera;
    };
    const esperas: number[] = [];
    for (let i = 0; i < 8; i++) {
      m.baileys.ultimo.cierre(428);
      esperas.push(await esperarElRetroceso());
    }
    expect(esperas).toEqual([3000, 6000, 12_000, 24_000, 48_000, 60_000, 60_000, 60_000]);

    // Conecta: la próxima caída vuelve a esperar 3 s.
    m.baileys.ultimo.conexion({ connection: "open" });
    m.baileys.ultimo.cierre(428);
    expect(await esperarElRetroceso()).toBe(3000);
  });

  it("el reinicio que WhatsApp pide tras vincular (515) se atiende enseguida", async () => {
    vi.useFakeTimers();
    const m = nuevo();
    await m.nucleo.arrancar();
    m.baileys.ultimo.cierre(515);
    await vi.advanceTimersByTimeAsync(1001);
    expect(m.baileys.makeWASocket).toHaveBeenCalledTimes(2);
  });

  it("si OTRA sesión tomó el número (440) espera al menos 60 s en vez de pelearse", async () => {
    vi.useFakeTimers();
    const m = nuevo();
    await m.nucleo.arrancar();
    m.baileys.ultimo.cierre(440);
    await vi.advanceTimersByTimeAsync(59_000);
    expect(m.baileys.makeWASocket).toHaveBeenCalledOnce();
    await vi.advanceTimersByTimeAsync(2000);
    expect(m.baileys.makeWASocket).toHaveBeenCalledTimes(2);
  });

  it("al reconectar cierra el socket anterior y le quita la voz (un solo escritor)", async () => {
    vi.useFakeTimers();
    const m = nuevo();
    await m.nucleo.arrancar();
    const viejo = m.baileys.ultimo;
    viejo.cierre(428);
    await vi.advanceTimersByTimeAsync(3100);
    const nuevoSock = m.baileys.ultimo;
    expect(nuevoSock).not.toBe(viejo);
    expect(viejo.ended).toBe(true);
    expect(viejo.ev.listenerCount("messages.upsert")).toBe(0);
    // Un evento rezagado del socket viejo no pisa el estado ni entrega nada.
    viejo.ev.emit("messages.upsert", { type: "notify", messages: [msgTexto("fantasma")] });
    viejo.ev.emit("connection.update", { connection: "open" });
    await asentar();
    expect(m.puente.entrantes).toHaveLength(0);
    expect(m.nucleo.estado.conexion).not.toBe("conectada");
  });

  it("la cadena de reconexión NO se corta si conectar() falla (la noche muda del 16-sep)", async () => {
    vi.useFakeTimers();
    const m = nuevo();
    await m.nucleo.arrancar();
    m.baileys.ultimo.cierre(428);
    m.puente.fallar(2); // las dos próximas lecturas de credenciales fallan
    await vi.advanceTimersByTimeAsync(3100); // intento 1: falla
    expect(m.nucleo.estado.ultimoError).toContain("reconectar");
    await vi.advanceTimersByTimeAsync(6100); // intento 2: falla
    await vi.advanceTimersByTimeAsync(12_100); // intento 3: ya funciona
    expect(m.baileys.makeWASocket.mock.calls.length).toBeGreaterThanOrEqual(2);
    m.baileys.ultimo.conexion({ connection: "open" });
    expect(m.nucleo.estado.conexion).toBe("conectada");
  });
});

describe("el vigilante", () => {
  it("un socket «conectado» que en realidad está muerto (zombi) se rescata", async () => {
    vi.useFakeTimers();
    const m = nuevo();
    const sock = await conectado(m);
    sock.ws.isOpen = false;
    m.nucleo.vigilar();
    expect(m.nucleo.estado).toMatchObject({ conexion: "cerrada", rescatesDelVigilante: 1 });
    expect(m.nucleo.estado.ultimoError).toContain("zombi");
    await vi.advanceTimersByTimeAsync(3100);
    expect(m.baileys.makeWASocket).toHaveBeenCalledTimes(2);
  });

  it("un socket sano no se toca", async () => {
    const m = nuevo();
    await conectado(m);
    m.nucleo.vigilar();
    expect(m.nucleo.estado.rescatesDelVigilante).toBe(0);
    expect(m.nucleo.estado.conexion).toBe("conectada");
  });

  it("esperando el QR o desvinculado se deja en paz (reconectar tumbaría el QR que se está mirando)", async () => {
    vi.useFakeTimers();
    const m = nuevo();
    await m.nucleo.arrancar();
    m.sock.conexion({ qr: QR_CRUDO });
    await vi.advanceTimersByTimeAsync(10);
    await vi.advanceTimersByTimeAsync(10 * 60_000);
    expect(m.baileys.makeWASocket).toHaveBeenCalledOnce();
    expect(m.nucleo.estado.rescatesDelVigilante).toBe(0);
  });

  it("si lleva caído y nadie reconecta, lo rescata (pero antes le da tiempo al camino normal)", async () => {
    vi.useFakeTimers();
    const m = nuevo();
    await conectado(m);
    // Se pierde el cierre: queda «cerrada» sin ninguna reconexión programada.
    m.nucleo.estado.conexion = "cerrada";
    (m.nucleo.estado as any).conexionDesde = Date.now();
    m.nucleo.vigilar();
    expect(m.nucleo.estado.rescatesDelVigilante).toBe(0); // acaba de caerse: tiempo al camino normal
    await vi.advanceTimersByTimeAsync(VIGILANTE_MS + 100); // el intervalo del vigilante corre solo
    expect(m.nucleo.estado.rescatesDelVigilante).toBe(1);
    await vi.advanceTimersByTimeAsync(3100);
    expect(m.baileys.makeWASocket.mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it("cada intento nuevo tiene 30 s para conectar antes de que el vigilante lo recicle", async () => {
    vi.useFakeTimers();
    const m = nuevo();
    await m.nucleo.arrancar(); // t = 0
    m.sock.cierre(428);
    await vi.advanceTimersByTimeAsync(3001); // t = 3 s: nace el 2.º socket, que no llega a abrir
    expect(m.baileys.makeWASocket).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(27_200); // t = 30,2 s: primera revisión del vigilante (el intento lleva 27 s)
    expect(m.nucleo.estado.rescatesDelVigilante).toBe(0);
    await vi.advanceTimersByTimeAsync(30_000); // t = 60,2 s: ya pasó de 30 s sin abrir → lo recicla
    expect(m.nucleo.estado.rescatesDelVigilante).toBe(1);
  });

  it("si un intento lento por fin conecta, la reconexión ya programada no tumba la conexión sana", async () => {
    vi.useFakeTimers();
    const m = nuevo();
    await m.nucleo.arrancar();
    m.sock.cierre(428); // se programa reconectar en 3 s…
    m.sock.conexion({ connection: "open" }); // …pero el mismo socket llega a abrir antes
    expect(m.nucleo.estado.conexion).toBe("conectada");
    await vi.advanceTimersByTimeAsync(5000);
    expect(m.baileys.makeWASocket).toHaveBeenCalledOnce();
    expect(m.sock.ended).toBe(false);
  });

  it("anota cuándo vigiló por última vez", async () => {
    const m = nuevo();
    await conectado(m);
    expect(m.nucleo.estado.ultimaVigilancia).toBe(null);
    m.nucleo.vigilar();
    expect(m.nucleo.estado.ultimaVigilancia).not.toBe(null);
  });
});

describe("mensajes que llegan → JSON del contrato hacia el Worker", () => {
  it("texto de un cliente", async () => {
    const m = nuevo();
    const sock = await conectado(m);
    sock.upsert([msgTexto("Hola, ¿tienen camas queen?", { id: "T1" })]);
    await asentar();
    expect(m.puente.entrantes).toHaveLength(1);
    const j = m.puente.entrantes[0];
    expect(j).toMatchObject({ id_mensaje: "T1", de: "50760261919", nombre: "Karen", tipo: "texto", texto: "Hola, ¿tienen camas queen?", propio: false });
    expect(validarWebhook(j)).toEqual([]);
    expect(m.puente.llamadas.at(-1)).toMatchObject({ ruta: "/puente/entrante", metodo: "POST" });
    expect(m.nucleo.estado.mensajesRecibidos).toBe(1);
  });

  it("imagen, nota de voz: se descargan en el momento y viajan en base64", async () => {
    const m = nuevo();
    const sock = await conectado(m);
    m.baileys.downloadMediaMessage.mockResolvedValue(Buffer.from("CONTENIDO"));
    sock.upsert([msgImagen({ id: "I1", caption: "mi comprobante" }), msgAudio({ id: "A1" })]);
    await asentar();
    expect(m.baileys.downloadMediaMessage).toHaveBeenCalledTimes(2);
    expect(m.puente.entrantes.map((e) => e.tipo)).toEqual(["imagen", "audio"]);
    expect(m.puente.entrantes[0]).toMatchObject({ texto: "mi comprobante", medio: { base64: Buffer.from("CONTENIDO").toString("base64"), mime: "image/jpeg" } });
    expect(m.puente.entrantes.every((e) => validarWebhook(e).length === 0)).toBe(true);
    expect(m.nucleo.estado.archivosRecibidos).toBe(2);
  });

  it("la vendedora escribe desde el teléfono → propio:true", async () => {
    const m = nuevo();
    const sock = await conectado(m);
    sock.upsert([msgTexto("Buenas, le atiende Marisol", { id: "P1", fromMe: true })]);
    await asentar();
    expect(m.puente.entrantes).toHaveLength(1);
    expect(m.puente.entrantes[0]).toMatchObject({ propio: true, de: "50760261919", nombre: null, texto: "Buenas, le atiende Marisol" });
    expect(m.nucleo.estado.respuestasDelTelefono).toBe(1);
    expect(m.nucleo.estado.mensajesRecibidos).toBe(0);
  });

  it("estados, grupos, canales, historial y reacciones NO se entregan", async () => {
    const m = nuevo();
    const sock = await conectado(m);
    sock.upsert([
      msgTexto("estado de un contacto", { de: "status@broadcast" }),
      msgTexto("en un grupo", { de: "120363025246125486@g.us" }),
      msgTexto("de un canal", { de: "120363025246125486@newsletter" }),
      msgTexto("difusión", { de: "lista@broadcast" }),
    ]);
    sock.upsert([msgTexto("mensaje viejo del historial")], "append");
    sock.upsert([{ ...msgTexto("x"), message: { reactionMessage: { text: "👍" } } }]);
    await asentar();
    expect(m.puente.entrantes).toHaveLength(0);
    expect(m.nucleo.estado.ignorados).toMatchObject({ no_es_chat: 4, historial: 1, sin_contenido: 1 });
    expect(m.nucleo.estado.mensajesRecibidos).toBe(0);
  });

  it("un mensaje que WhatsApp entrega dos veces solo se entrega una", async () => {
    const m = nuevo();
    const sock = await conectado(m);
    sock.upsert([msgTexto("hola", { id: "DUP" })]);
    sock.upsert([msgTexto("hola", { id: "DUP" })]);
    await asentar();
    expect(m.puente.entrantes).toHaveLength(1);
    expect(m.nucleo.estado.ignorados.duplicado).toBe(1);
  });

  it("al contestar a un chat que llegó como @lid, marca como leído su último mensaje", async () => {
    const m = nuevo();
    const sock = await conectado(m);
    sock.lids["987654321098765@lid"] = "50760261919@s.whatsapp.net";
    sock.upsert([msgTexto("hola desde un lid", { id: "LID1", de: "987654321098765@lid" })]);
    await asentar();
    await post(m, "/enviar", { para: "60261919", chunks: ["Hola"] });
    expect(sock.llamadas.find((l) => l.tipo === "readMessages")?.args[0][0]).toMatchObject({ id: "LID1" });
  });

  it("si un mensaje no llegó a Juan, una re-entrega de WhatsApp puede volver a intentarlo", async () => {
    const m = nuevo();
    const sock = await conectado(m);
    m.puente.fallar(3, 503); // los tres intentos fallan
    sock.upsert([msgTexto("hola", { id: "RE1" })]);
    await asentar();
    expect(m.puente.entrantes).toHaveLength(0);
    sock.upsert([msgTexto("hola", { id: "RE1" })]); // WhatsApp lo vuelve a entregar
    await asentar();
    expect(m.puente.entrantes).toHaveLength(1);
  });

  it("un chat @lid se resuelve a su número con el mapa de Baileys", async () => {
    const m = nuevo();
    const sock = await conectado(m);
    sock.lids["987654321098765@lid"] = "50760261919@s.whatsapp.net";
    sock.upsert([msgTexto("hola desde un lid", { de: "987654321098765@lid" })]);
    await asentar();
    expect(m.puente.entrantes[0]).toMatchObject({ de: "50760261919", jid: "50760261919@s.whatsapp.net" });
  });

  it("el JSON entrante jamás lleva el mensaje crudo ni nada de las credenciales", async () => {
    const m = nuevo();
    const sock = await conectado(m);
    const msg: any = msgImagen({ id: "I2" });
    msg.message.imageMessage.mediaKey = "MEDIA-KEY-SECRETA";
    sock.upsert([msg]);
    await asentar();
    expect(JSON.stringify(m.puente.entrantes)).not.toContain("MEDIA-KEY-SECRETA");
  });
});

describe("entrega al Worker con reintentos", () => {
  it("reintenta si el Worker falla (5xx o red) y entrega UNA sola vez", async () => {
    const m = nuevo();
    const sock = await conectado(m);
    m.puente.fallar(2, 503);
    sock.upsert([msgTexto("hola", { id: "R1" })]);
    await asentar();
    expect(m.puente.entrantes).toHaveLength(1);
    expect(m.puente.llamadas.filter((l) => l.ruta === "/puente/entrante")).toHaveLength(3);
    expect(m.dormido).toEqual(expect.arrayContaining([2000, 6000]));
  });

  it("un 4xx no se repite (el cuerpo mal formado no se arregla insistiendo) y queda anotado", async () => {
    const m = nuevo();
    const sock = await conectado(m);
    m.puente.fallar(5, 422);
    sock.upsert([msgTexto("hola", { id: "R2" })]);
    await asentar();
    expect(m.puente.llamadas.filter((l) => l.ruta === "/puente/entrante")).toHaveLength(1);
    expect(m.nucleo.estado.entregasFallidas).toBe(1);
    expect(m.nucleo.estado.ultimoError).toContain("entrante");
  });

  it("si el Worker no vuelve tras los reintentos, lo anota sin perder el proceso", async () => {
    const m = nuevo();
    const sock = await conectado(m);
    m.puente.fallar(10);
    sock.upsert([msgTexto("hola", { id: "R3" })]);
    await asentar();
    expect(m.nucleo.estado.entregasFallidas).toBe(1);
    expect(m.nucleo.estado.conexion).toBe("conectada");
  });
});

describe("POST /enviar", () => {
  const cuerpo = { para: "6026-1919", chunks: ["Hola Karen.", "Sí, tenemos camas queen."] };

  it("manda las burbujas y devuelve los ids", async () => {
    const m = nuevo();
    const sock = await conectado(m);
    const r = await post(m, "/enviar", cuerpo);
    expect(r.status).toBe(200);
    expect(r.cuerpo).toMatchObject({ ok: true, enviados: { chunks: 2, medios: 0 } });
    expect(r.cuerpo.ids).toHaveLength(2);
    expect(r.cuerpo.id_mensaje).toBe(r.cuerpo.ids[1]);
    expect(sock.enviados.map((e) => [e.args[0], e.args[1].text])).toEqual([
      [CLIENTE, "Hola Karen."],
      [CLIENTE, "Sí, tenemos camas queen."],
    ]);
    expect(m.nucleo.estado.mensajesEnviados).toBe(2);
  });

  it("el eco de lo que envió NO se toma por la vendedora (no hay entrante, no se pausa al bot)", async () => {
    const m = nuevo();
    const sock = await conectado(m);
    await post(m, "/enviar", cuerpo);
    await asentar(); // el doble emite el eco en el mismo tick que termina sendMessage
    expect(sock.enviados).toHaveLength(2);
    expect(m.puente.entrantes).toHaveLength(0);
    expect(m.nucleo.estado.ignorados.eco_del_bot).toBe(2);
    expect(m.nucleo.estado.respuestasDelTelefono).toBe(0);
  });

  it("tras un reinicio, los ids que recuerda el Worker siguen reconociendo el eco", async () => {
    const m = nuevo();
    m.puente.enviados = [{ id: "ENVIADO-ANTES", ts: Date.now() - 60_000 }];
    const sock = await conectado(m);
    sock.upsert([msgTexto("respuesta que mandó el bot antes del reinicio", { id: "ENVIADO-ANTES", fromMe: true })], "append");
    await asentar();
    expect(m.puente.entrantes).toHaveLength(0);
    expect(m.nucleo.estado.ignorados.eco_del_bot).toBe(1);
  });

  it("imágenes y documentos: se descargan con las defensas y salen como archivo", async () => {
    const m = nuevo({ hostsPermitidos: ["dcasapty.com"] });
    const sock = await conectado(m);
    const r = await post(m, "/enviar", {
      para: "60261919",
      chunks: ["Mira esta."],
      medios: [
        { tipo: "imagen", url: "https://dcasapty.com/web/image/1", pie: "Cama Queen HK-BF-022" },
        { tipo: "documento", url: "https://dcasapty.com/cot.pdf", nombre: "Cotización.pdf" },
      ],
    });
    expect(r.status).toBe(200);
    expect(r.cuerpo.enviados).toEqual({ chunks: 1, medios: 2 });
    expect(m.descargar).toHaveBeenCalledTimes(2);
    expect(m.descargar.mock.calls[0][1]).toMatchObject({ tipo: "imagen", hostsPermitidos: ["dcasapty.com"], maxBytes: 6 * 1024 * 1024 });
    expect(m.descargar.mock.calls[1][1]).toMatchObject({ tipo: "documento", maxBytes: 12 * 1024 * 1024 });
    const [, imagen, documento] = sock.enviados.map((e) => e.args[1]);
    expect(imagen).toMatchObject({ caption: "Cama Queen HK-BF-022", mimetype: "image/jpeg" });
    expect(Buffer.from(imagen.image).toString()).toBe("BYTES-DEL-ARCHIVO");
    expect(documento).toMatchObject({ fileName: "Cotización.pdf", mimetype: "application/pdf" });
  });

  it("si un archivo no se puede descargar, NO sale nada (ni el texto): sin respuestas a medias", async () => {
    const m = nuevo({}, async () => ({ ok: false, estado: 422, motivo: "el servidor está en una dirección no pública" }));
    const sock = await conectado(m);
    const r = await post(m, "/enviar", { para: "60261919", chunks: ["Mira"], medios: [{ tipo: "imagen", url: "https://dcasapty.com/a.jpg" }] });
    expect(r.status).toBe(422);
    expect(r.cuerpo.error).toContain("medios[0]");
    expect(sock.enviados).toHaveLength(0);
  });

  it("un fallo de red al descargar es 502", async () => {
    const m = nuevo({}, async () => ({ ok: false, estado: 502, motivo: "no se pudo descargar (ECONNRESET)" }));
    await conectado(m);
    const r = await post(m, "/enviar", { para: "60261919", medios: [{ tipo: "imagen", url: "https://dcasapty.com/a.jpg" }] });
    expect(r.status).toBe(502);
  });

  it("sin conexión con WhatsApp: 409 y no se intenta nada", async () => {
    const m = nuevo();
    await m.nucleo.arrancar(); // sigue «arrancando»
    const r = await post(m, "/enviar", cuerpo);
    expect(r.status).toBe(409);
    expect(r.cuerpo).toMatchObject({ estado: "arrancando" });
    expect(m.sock.enviados).toHaveLength(0);
  });

  it.each([
    ["no es JSON", "esto no es json", 400],
    ["destino inválido", { para: "123", chunks: ["x"] }, 400],
    ["a un grupo", { para: "120363025246125486@g.us", chunks: ["x"] }, 400],
    ["a los estados", { para: "status@broadcast", chunks: ["x"] }, 400],
    ["URL http", { para: "60261919", medios: [{ tipo: "imagen", url: "http://dcasapty.com/a.jpg" }] }, 422],
    ["URL interna", { para: "60261919", medios: [{ tipo: "imagen", url: "https://169.254.169.254/x" }] }, 422],
  ])("rechaza sin enviar: %s", async (_n, c, status) => {
    const m = nuevo();
    const sock = await conectado(m);
    const r = await post(m, "/enviar", c);
    expect(r.status).toBe(status);
    expect(sock.enviados).toHaveLength(0);
    expect(m.descargar).not.toHaveBeenCalled();
  });

  it("si el socket falla a mitad, devuelve 502 con lo que SÍ salió", async () => {
    const m = nuevo();
    const sock = await conectado(m);
    sock.fallarEnElEnvio = 2;
    const r = await post(m, "/enviar", { para: "60261919", chunks: ["uno", "dos", "tres"] });
    expect(r.status).toBe(502);
    expect(r.cuerpo).toMatchObject({ ok: false, parcial: true, enviados: { chunks: 1, medios: 0 } });
    expect(r.cuerpo.ids).toHaveLength(1);
    expect(m.nucleo.estado.mensajesEnviados).toBe(1);
  });

  it("ritmo: al menos 1 s entre burbujas y «escribiendo…» antes de cada texto", async () => {
    const m = nuevo();
    const sock = await conectado(m);
    await post(m, "/enviar", { para: "60261919", chunks: ["uno", "dos", "tres"] });
    const t = sock.enviados.map((e) => e.t);
    expect(t[1] - t[0]).toBeGreaterThanOrEqual(1000);
    expect(t[2] - t[1]).toBeGreaterThanOrEqual(1000);
    expect(sock.llamadas.filter((l) => l.args[0] === "composing")).toHaveLength(3);
  });

  it("marca como leído el último mensaje del cliente antes de contestarle", async () => {
    const m = nuevo();
    const sock = await conectado(m);
    const entrante = msgTexto("hola", { id: "L1" });
    sock.upsert([entrante]);
    await asentar();
    await post(m, "/enviar", { para: "60261919", chunks: ["Hola"] });
    const leido = sock.llamadas.find((l) => l.tipo === "readMessages");
    expect(leido?.args[0][0]).toMatchObject({ id: "L1" });
  });

  it("un solo escritor: dos peticiones a la vez NO entrelazan sus burbujas", async () => {
    const m = nuevo();
    const sock = await conectado(m);
    // Cada pausa cede el turno (await), así que sin la cola las burbujas de A y B se alternarían.
    const [a, b] = await Promise.all([
      post(m, "/enviar", { para: "60261919", chunks: ["A1", "A2", "A3"] }),
      post(m, "/enviar", { para: "60262020", chunks: ["B1", "B2", "B3"] }),
    ]);
    expect(a.status).toBe(200);
    expect(b.status).toBe(200);
    expect(sock.enviados.map((e) => e.args[1].text)).toEqual(["A1", "A2", "A3", "B1", "B2", "B3"]);
  });

  it("si la fila de envíos está llena: 503 con cuándo reintentar", async () => {
    const m = nuevo({ ritmo: { ...RITMO_POR_DEFECTO, colaMax: 1 } });
    await conectado(m);
    const [a, b] = await Promise.all([post(m, "/enviar", { para: "60261919", chunks: ["uno"] }), post(m, "/enviar", { para: "60262020", chunks: ["dos"] })]);
    expect([a.status, b.status].sort()).toEqual([200, 503]);
    const lleno = [a, b].find((r) => r.status === 503)!;
    expect(lleno.cuerpo.reintentar_en_s).toBeGreaterThan(0);
  });
});

describe("rutas de operación", () => {
  it("/reconectar: 409 si está desvinculado, y si no programa la reconexión", async () => {
    vi.useFakeTimers();
    const m = nuevo();
    await conectado(m);
    m.sock.cierre(428);
    const ok = await post(m, "/reconectar", "");
    expect(ok.status).toBe(200);
    expect(ok.cuerpo.programada).toBe(true);
    await vi.advanceTimersByTimeAsync(60_000);

    m.baileys.ultimo.cierre(401);
    await vi.advanceTimersByTimeAsync(10);
    const no = await post(m, "/reconectar", "");
    expect(no.status).toBe(409);
  });

  it("/logout: cierra la sesión, borra las credenciales y queda desvinculado", async () => {
    const m = nuevo();
    m.puente.kv.set("creds", "{}");
    const sock = await conectado(m);
    const r = await post(m, "/logout", "");
    expect(r.status).toBe(200);
    expect(sock.loggedOut).toBe(true);
    expect(m.puente.kv.has("creds")).toBe(false);
    expect(m.nucleo.estado.conexion).toBe("desvinculada");
  });

  it("rutas que no existen: 404", async () => {
    const m = nuevo();
    expect((await get(m, "/nada")).status).toBe(404);
  });

  it("/estado: sin tokens y con contadores", async () => {
    const m = nuevo();
    const sock = await conectado(m);
    sock.upsert([msgTexto("hola")]);
    await asentar();
    const e = (await get(m, "/estado")).cuerpo;
    expect(e).toMatchObject({ conexion: "conectada", mensajesRecibidos: 1, enviosEnCola: 0 });
    expect(JSON.stringify(e)).not.toMatch(/token|TOKEN|authorization/i);
  });

  it("los errores se anotan SIN números completos", async () => {
    const m = nuevo();
    m.nucleo.anotarError("prueba", new Error("falló el envío a 50760261919@s.whatsapp.net"));
    expect(m.nucleo.estado.ultimoError).toBe("prueba: falló el envío a ***1919@s.whatsapp.net");
    expect(JSON.stringify(m.log.error.mock.calls)).not.toContain("50760261919");
  });
});
