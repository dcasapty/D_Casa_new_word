// Un doble de Baileys para las pruebas: lo mínimo del socket (eventos, envío, presencia) y
// constructores de mensajes con la forma real. NO se prueba contra WhatsApp de verdad.
import { EventEmitter } from "node:events";
import { vi } from "vitest";

// ── Mensajes con la forma de Baileys ──────────────────────────────────────────

export const CLIENTE = "50760261919@s.whatsapp.net";
export const NEGOCIO = "50760269999:3@s.whatsapp.net";

interface Base {
  id?: string;
  de?: string;
  fromMe?: boolean;
  ts?: number; // segundos
  pushName?: string;
  alt?: string;
}
let contador = 0;
const sig = () => `MSG${++contador}`;
const ahoraS = () => Math.floor(Date.now() / 1000);

function envolver(b: Base, message: Record<string, unknown>) {
  return {
    key: { remoteJid: b.de ?? CLIENTE, fromMe: b.fromMe ?? false, id: b.id ?? sig(), ...(b.alt ? { remoteJidAlt: b.alt } : {}) },
    message,
    messageTimestamp: b.ts ?? ahoraS(),
    ...(b.pushName !== undefined ? { pushName: b.pushName } : { pushName: "Karen" }),
  };
}

export const msgTexto = (texto: string, b: Base = {}) => envolver(b, { conversation: texto });
export const msgTextoLargo = (texto: string, b: Base = {}) => envolver(b, { extendedTextMessage: { text: texto } });
export const msgImagen = (b: Base & { caption?: string; tam?: number } = {}) =>
  envolver(b, { imageMessage: { caption: b.caption, mimetype: "image/jpeg", fileLength: b.tam ?? 50_000 } });
export const msgAudio = (b: Base & { tam?: number } = {}) =>
  envolver(b, { audioMessage: { mimetype: "audio/ogg; codecs=opus", fileLength: b.tam ?? 20_000, ptt: true, seconds: 7 } });
export const msgDocumento = (b: Base & { caption?: string; nombre?: string; tam?: number } = {}) =>
  envolver(b, {
    documentMessage: { caption: b.caption, mimetype: "application/pdf", fileName: b.nombre ?? "comprobante.pdf", fileLength: b.tam ?? 80_000 },
  });
export const msgVideo = (b: Base & { caption?: string; tam?: number } = {}) =>
  envolver(b, { videoMessage: { caption: b.caption, mimetype: "video/mp4", fileLength: b.tam ?? 900_000 } });
export const msgSticker = (b: Base = {}) => envolver(b, { stickerMessage: { mimetype: "image/webp" } });
export const msgUbicacion = (b: Base = {}) =>
  envolver(b, { locationMessage: { degreesLatitude: 8.8801, degreesLongitude: -79.7834, name: "Casa", address: "La Chorrera" } });
export const msgContacto = (b: Base = {}) => envolver(b, { contactMessage: { displayName: "Marisol" } });
export const msgReaccion = (b: Base = {}) => envolver(b, { reactionMessage: { text: "👍", key: { id: "X" } } });
export const msgProtocolo = (b: Base = {}) => envolver(b, { protocolMessage: { type: 0 } });
/** Un mensaje «temporal» (con la envoltura de mensajes que desaparecen). */
export const msgTemporal = (texto: string, b: Base = {}) => envolver(b, { ephemeralMessage: { message: { conversation: texto } } });

// ── El socket falso ──────────────────────────────────────────────────────────

export interface Llamada {
  tipo: "sendMessage" | "sendPresenceUpdate" | "presenceSubscribe" | "readMessages";
  args: any[];
  /** Instante virtual en ms (acumulado por `dormir`). */
  t: number;
}

export class SockFalso {
  ev = new EventEmitter();
  user = { id: NEGOCIO, lid: "999999999999999:3@lid" };
  ws: { isOpen: boolean } = { isOpen: true };
  llamadas: Llamada[] = [];
  ended = false;
  loggedOut = false;
  /** Falla el envío número N (1 = el primero). */
  fallarEnElEnvio: number | null = null;
  enviosHechos = 0;
  lids: Record<string, string> = {};
  /** Reloj virtual: lo mueve quien inyecta `dormir`. */
  reloj = { t: 0 };

  signalRepository = {
    lidMapping: {
      getPNForLID: async (lid: string) => this.lids[lid] ?? null,
      getLIDForPN: async (pn: string) => Object.entries(this.lids).find(([, v]) => v === pn)?.[0] ?? null,
    },
  };

  constructor(public config: any) {}

  private anotar(tipo: Llamada["tipo"], args: any[]) {
    this.llamadas.push({ tipo, args, t: this.reloj.t });
  }
  async sendMessage(jid: string, contenido: any, opciones: any) {
    this.enviosHechos += 1;
    if (this.fallarEnElEnvio === this.enviosHechos) throw new Error("socket cerrado a medias");
    this.anotar("sendMessage", [jid, contenido, opciones]);
    // Baileys emite el eco de lo enviado EN EL MISMO TICK en que termina sendMessage.
    queueMicrotask(() =>
      this.ev.emit("messages.upsert", {
        type: "notify",
        messages: [{ key: { remoteJid: jid, fromMe: true, id: opciones?.messageId }, message: contenido.text ? { conversation: contenido.text } : { imageMessage: {} }, messageTimestamp: ahoraS() }],
      }),
    );
    return { key: { id: opciones?.messageId } };
  }
  async sendPresenceUpdate(...args: any[]) {
    this.anotar("sendPresenceUpdate", args);
  }
  async presenceSubscribe(...args: any[]) {
    this.anotar("presenceSubscribe", args);
  }
  async readMessages(...args: any[]) {
    this.anotar("readMessages", args);
  }
  updateMediaMessage = vi.fn();
  /** Fotos de perfil por jid: una URL, o `null` = sin foto (Baileys lanza «item-not-found»). */
  fotos: Record<string, string | null> = {};
  pedidasFotos: [string, string][] = [];
  async profilePictureUrl(jid: string, tipo: string) {
    this.pedidasFotos.push([jid, tipo]);
    const url = this.fotos[jid];
    if (!url) throw new Error("item-not-found");
    return url;
  }
  end() {
    this.ended = true;
  }
  async logout() {
    this.loggedOut = true;
  }

  /** Lo que enviaron: [jid, contenido]. */
  get enviados() {
    return this.llamadas.filter((l) => l.tipo === "sendMessage");
  }
  conexion(u: Record<string, unknown>) {
    this.ev.emit("connection.update", u);
  }
  upsert(messages: any[], type = "notify") {
    this.ev.emit("messages.upsert", { messages, type });
  }
  cierre(codigo: number) {
    this.conexion({ connection: "close", lastDisconnect: { error: { output: { statusCode: codigo } } } });
  }
}

// ── La librería falsa ────────────────────────────────────────────────────────

export function crearBaileysFalso() {
  const sockets: SockFalso[] = [];
  let ids = 0;
  const baileys = {
    sockets,
    makeWASocket: vi.fn((config: any) => {
      const s = new SockFalso(config);
      sockets.push(s);
      return s;
    }),
    DisconnectReason: { loggedOut: 401, connectionReplaced: 440, restartRequired: 515 },
    BufferJSON: { replacer: undefined as any, reviver: undefined as any },
    initAuthCreds: () => ({ registrationId: 1234, nextPreKeyId: 1, firstUnuploadedPreKeyId: 1 }),
    proto: { Message: { AppStateSyncKeyData: { fromObject: (x: unknown) => x } } },
    fetchLatestBaileysVersion: vi.fn(async () => ({ version: [2, 3000, 1] as [number, number, number] })),
    downloadMediaMessage: vi.fn(async () => Buffer.from("BYTES-DEL-ARCHIVO")),
    generateMessageIDV2: (user?: string) => `3EB0${++ids}${user ? "U" : ""}`,
    get ultimo() {
      return sockets[sockets.length - 1];
    },
  };
  return baileys;
}

// ── El Worker falso (lo que el contenedor ve del otro lado) ──────────────────

export interface PuenteFalso {
  (ruta: string, init?: any): Promise<{ ok: boolean; status: number; text(): Promise<string>; json(): Promise<any> }>;
  llamadas: { ruta: string; metodo: string; cuerpo: any }[];
  entrantes: any[];
  kv: Map<string, string>;
  /** Hace que la siguiente(s) N llamadas fallen con este estado (0 = error de red). */
  fallar(n: number, estado?: number): void;
  enviados: { id: string; ts: number }[];
}

/** Un «Worker» en memoria con las rutas /puente/*: la sesión, los ids enviados y la entrega a Juan. */
export function crearPuenteFalso(): PuenteFalso {
  let fallos = 0;
  let estadoFallo = 0;
  const puente = (async (ruta: string, init: any = {}) => {
    const metodo = init.method ?? "GET";
    let cuerpo: any = undefined;
    if (typeof init.body === "string") {
      try {
        cuerpo = JSON.parse(init.body);
      } catch {
        cuerpo = init.body;
      }
    }
    puente.llamadas.push({ ruta, metodo, cuerpo });
    const resp = (status: number, datos: unknown) => {
      const texto = typeof datos === "string" ? datos : JSON.stringify(datos);
      return { ok: status >= 200 && status < 300, status, text: async () => texto, json: async () => JSON.parse(texto) };
    };
    if (fallos > 0) {
      fallos -= 1;
      if (estadoFallo === 0) throw new Error("fetch failed");
      return resp(estadoFallo, { error: "falla de prueba" });
    }
    const u = new URL(ruta, "https://puente.test");
    if (u.pathname === "/puente/kv") {
      const clave = u.searchParams.get("clave")!;
      if (metodo === "GET") return puente.kv.has(clave) ? resp(200, puente.kv.get(clave)!) : resp(404, "no existe");
      if (metodo === "PUT") {
        puente.kv.set(clave, init.body);
        return resp(200, { ok: true });
      }
      if (metodo === "DELETE") {
        puente.kv.delete(clave);
        return resp(200, { ok: true });
      }
    }
    if (u.pathname === "/puente/kv-lote") {
      const valores: Record<string, string | null> = {};
      for (const k of cuerpo.leer ?? []) valores[k] = puente.kv.get(k) ?? null;
      for (const [k, v] of Object.entries<string>(cuerpo.escribir ?? {})) puente.kv.set(k, v);
      for (const k of cuerpo.borrar ?? []) puente.kv.delete(k);
      return resp(200, { ok: true, valores });
    }
    if (u.pathname === "/puente/enviados") return resp(200, { ids: puente.enviados });
    if (u.pathname === "/puente/entrante") {
      puente.entrantes.push(cuerpo);
      return resp(200, { ok: true, entregado: true });
    }
    return resp(404, "no existe");
  }) as PuenteFalso;
  puente.llamadas = [];
  puente.entrantes = [];
  puente.kv = new Map();
  puente.enviados = [];
  puente.fallar = (n, estado = 0) => {
    fallos = n;
    estadoFallo = estado;
  };
  return puente;
}
