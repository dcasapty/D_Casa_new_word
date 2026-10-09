// Baileys dentro de un contenedor de Cloudflare — el cableado real.
//
// El protocolo de WhatsApp Web no tiene webhooks: si nadie sostiene la conexión, los
// mensajes no llegan. Por eso esto es un contenedor y no un Worker.
//
// Aquí solo hay lo que NO se puede probar sin WhatsApp: importar Baileys de verdad,
// abrir el puerto HTTP y atar las señales del proceso. Toda la lógica (reconexión,
// vigilancia, ritmo, entrada y salida de mensajes) vive en `nucleo.mjs` y `lib/`, que
// se prueban con un doble de Baileys.
//
// Las credenciales de la sesión NO tocan el disco —el disco del contenedor es
// descartable—: van al Worker, que las guarda cifradas en el Durable Object.

import http from "node:http";
import makeWASocket, {
  DisconnectReason,
  BufferJSON,
  downloadMediaMessage,
  fetchLatestBaileysVersion,
  generateMessageIDV2,
  initAuthCreds,
  proto,
} from "@whiskeysockets/baileys";
import pino from "pino";
import QRCode from "qrcode";
import { crearNucleo } from "./nucleo.mjs";
import { descargarSeguro } from "./lib/descarga.mjs";
import { leerRitmo } from "./lib/ritmo.mjs";
import { parsearListaHosts } from "./lib/urls.mjs";

const PUERTO = Number(process.env.PORT || 8080);
const PUENTE = (process.env.PUENTE_URL || "").replace(/\/$/, "");
const TOKEN = process.env.PUENTE_TOKEN || "";
const EPOCA = process.env.PUENTE_EPOCA || "0";

if (!PUENTE || !TOKEN) {
  console.error("Faltan PUENTE_URL o PUENTE_TOKEN — sin ellos no hay dónde guardar la sesión.");
  process.exit(1);
}
// El token que recibe el contenedor lo deriva el Durable Object (hexadecimal): solo
// ASCII. Si no lo fuera, una cabecera HTTP lo deformaría en el camino (lección del
// «401 mudo» del CRM de origen: el largo no cambia y el error no delata nada).
if (!/^[\x21-\x7E]+$/.test(TOKEN)) {
  console.error("PUENTE_TOKEN tiene caracteres fuera de ASCII imprimible.");
  process.exit(1);
}

/** Nivel de log de Baileys. Por defecto en silencio: sus logs traen números y datos de clientes. */
const logger = pino({ level: process.env.BAILEYS_LOG || "silent" });

/** Llamada al Worker: siempre con el token del contenedor y la época de este arranque. */
function puente(ruta, init = {}) {
  return fetch(`${PUENTE}${ruta}`, {
    ...init,
    headers: { ...(init.headers || {}), authorization: `Bearer ${TOKEN}`, "x-wa-epoca": EPOCA },
    signal: AbortSignal.timeout(25_000),
  });
}

const nucleo = crearNucleo({
  baileys: {
    makeWASocket,
    DisconnectReason,
    BufferJSON,
    downloadMediaMessage,
    fetchLatestBaileysVersion,
    generateMessageIDV2,
    initAuthCreds,
    proto,
  },
  puente,
  qr: QRCode,
  logger,
  descargar: descargarSeguro,
  config: {
    ritmo: leerRitmo(process.env),
    hostsPermitidos: parsearListaHosts(process.env.MEDIOS_HOSTS_PERMITIDOS),
  },
});

// ── Que un error no mate el proceso ────────────────────────────────────────
//
// No es cosmético: fue el fallo que convirtió un 401 recuperable en un ciclo de
// caídas. Una promesa rechazada sin capturar mata el proceso en Node 22; el contenedor
// moría, la alarma lo relevantaba, volvía a morir, y Cloudflare dejó de entregar
// instancias. Un contenedor que se cae no deja ver por qué se cayó.

process.on("unhandledRejection", (e) => nucleo.anotarError("promesa sin capturar", e));
process.on("uncaughtException", (e) => nucleo.anotarError("excepción sin capturar", e));

// ── HTTP interno, el que el Worker consulta ────────────────────────────────

const CUERPO_MAXIMO = 512 * 1024;

function leer(req) {
  return new Promise((resolver, rechazar) => {
    let datos = "";
    req.on("data", (trozo) => {
      datos += trozo;
      if (datos.length > CUERPO_MAXIMO) {
        rechazar(new Error("cuerpo demasiado grande"));
        req.destroy();
      }
    });
    req.on("end", () => resolver(datos));
    req.on("error", rechazar);
  });
}

const servidor = http.createServer(async (req, res) => {
  const responder = (status, cuerpo) => {
    res.writeHead(status, { "content-type": "application/json", "cache-control": "no-store" });
    res.end(JSON.stringify(cuerpo));
  };
  try {
    const url = new URL(req.url, "http://contenedor");
    const cuerpo = req.method === "POST" || req.method === "PUT" ? await leer(req) : "";
    const r = await nucleo.manejar({ metodo: req.method, ruta: url.pathname, cuerpo });
    responder(r.status, r.cuerpo);
  } catch (e) {
    nucleo.anotarError("http", e);
    if (!res.headersSent) responder(500, { error: e instanceof Error ? e.message : String(e) });
  }
});

servidor.listen(PUERTO, () => console.log(`Servidor interno en :${PUERTO}`));

// Cloudflare para el contenedor con SIGTERM: se cierra el socket con orden.
process.on("SIGTERM", () => {
  console.log("SIGTERM: cerrando el socket.");
  nucleo.detener();
  servidor.close();
  setTimeout(() => process.exit(0), 500).unref();
});

nucleo.arrancar();
