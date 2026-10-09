// @ts-check
// El núcleo del puente: sostiene el socket de WhatsApp (Baileys) y habla con el
// Worker. Todo llega INYECTADO (Baileys, la conexión con el Worker, el generador
// de QR, el reloj, el azar), así que se prueba entero con un doble de Baileys sin
// tocar WhatsApp. `servidor.mjs` es solo el cableado real (HTTP + Baileys de verdad).
//
// Cada `try` de este archivo tiene un incidente detrás. Ver la bitácora del CRM de
// origen (docs/bitacora-whatsapp-qr.md de crm-baby-caleb) y docs/JUAN_PUENTE.md
// antes de «simplificar» alguno. Los más caros:
//
//   · programarReconexion() encadena SIEMPRE el siguiente intento. Sin eso, un
//     fallo al leer las credenciales dejaba el canal mudo para siempre (16-sep).
//   · cerrarAnterior() + generaciones: dos sockets sobre el mismo número se
//     expulsan en ciclo.
//   · un error no capturado mata Node 22; el contenedor entraba en ciclo de caídas.
//   · el QR vence a los 45 s: uno viejo hace que el teléfono diga «revisa tu conexión».
//   · el QR no se sirve con la sesión activa: cualquiera con acceso vincularía OTRO teléfono.

import { crearClienteKv, crearEstadoRemoto } from "./lib/auth-remoto.mjs";
import { ColaLlena, EsperaAgotada, crearCola } from "./lib/cola.mjs";
import { validarEnviar } from "./lib/contrato.mjs";
import { armarEntrante } from "./lib/entrante.mjs";
import { enviarSecuencia } from "./lib/envio.mjs";
import { LIMITE_SALIENTE, MIMES_SALIENTES, nombreSeguro } from "./lib/medios.mjs";
import { enmascarar, sinDispositivo } from "./lib/numeros.mjs";
import { crearRegistroDeEnvios, decidirUpsert } from "./lib/propios.mjs";
import { RITMO_POR_DEFECTO } from "./lib/ritmo.mjs";

/** Cada cuánto se revisa a sí mismo. Mismo valor que VIGILANTE_MS en src/comun.ts. */
export const VIGILANTE_MS = 30_000;

/**
 * Cuánto vale un QR antes de estar muerto.
 *
 * WhatsApp rota el `ref` del emparejamiento cada ~20 s y lo invalida al minuto.
 * Servir uno vencido no da error: el teléfono lo lee, intenta emparejar contra un
 * `ref` que ya no existe y muestra «Revisa tu conexión y vuelve a intentarlo» —un
 * mensaje que culpa a la red del dueño cuando el problema está de este lado—.
 */
export const QR_VENCE_MS = 45_000;

/** Códigos de cierre de WhatsApp que importan (DisconnectReason de Baileys). */
const CIERRE = { loggedOut: 401, connectionReplaced: 440, restartRequired: 515 };

/** Cuántos ids de mensajes entrantes se recuerdan para no entregar dos veces el mismo. */
const VISTOS_MAX = 1000;

/**
 * @typedef {{
 *   baileys: any,
 *   puente: import("./lib/auth-remoto.mjs").Puente,
 *   qr: { toDataURL(texto: string, opciones?: any): Promise<string> },
 *   logger: any,
 *   descargar: (url: string, opciones: any) => Promise<any>,
 *   config?: {
 *     ritmo?: import("./lib/ritmo.mjs").Ritmo,
 *     hostsPermitidos?: string[],
 *     navegador?: [string, string, string],
 *     vigilanteMs?: number,
 *   },
 *   dormir?: (ms: number) => Promise<void>,
 *   azar?: () => number,
 *   log?: { log: (...a: any[]) => void, error: (...a: any[]) => void },
 * }} Dependencias
 */

/** @param {Dependencias} deps */
export function crearNucleo(deps) {
  const { baileys, puente, qr: generadorQr, logger, descargar } = deps;
  const ritmo = deps.config?.ritmo ?? RITMO_POR_DEFECTO;
  const hostsPermitidos = deps.config?.hostsPermitidos ?? [];
  const navegador = deps.config?.navegador ?? ["DCASA Panama", "Chrome", "1.0.0"];
  const vigilanteMs = deps.config?.vigilanteMs ?? VIGILANTE_MS;
  const dormir = deps.dormir ?? ((/** @type {number} */ ms) => new Promise((r) => setTimeout(r, ms)));
  const azar = deps.azar ?? Math.random;
  const log = deps.log ?? console;

  const kv = crearClienteKv(puente, baileys.BufferJSON);

  // ── Estado observable ────────────────────────────────────────────────────

  const estado = {
    /** arrancando | esperando-qr | conectada | cerrada | desvinculada */
    conexion: "arrancando",
    // Desde cuándo lleva en ese estado. El vigilante lo necesita para no pisarle el
    // trabajo a una reconexión que ya está en marcha.
    conexionDesde: Date.now(),
    arrancadoEn: new Date().toISOString(),
    /** El número vinculado, ENMASCARADO: el estado sale por /api/estado. */
    vinculadoComo: /** @type {string | null} */ (null),
    reconexiones: 0,
    // Lo que el vigilante tuvo que rescatar. Si crece, algo de fondo está mal.
    rescatesDelVigilante: 0,
    ultimaVigilancia: /** @type {string | null} */ (null),
    proximoIntentoEn: /** @type {string | null} */ (null),
    mensajesRecibidos: 0,
    mensajesEnviados: 0,
    /** Mensajes que salieron del número SIN que los mandara el bot: una persona desde el teléfono. */
    respuestasDelTelefono: 0,
    /** Notas de voz, imágenes, documentos y videos descargados y reenviados. */
    archivosRecibidos: 0,
    /** Mensajes que no se entregaron a Juan tras reintentar. */
    entregasFallidas: 0,
    /** Qué se ignoró y por qué (estados, grupos, historial, ecos…). */
    ignorados: /** @type {Record<string, number>} */ ({}),
    ultimoError: /** @type {string | null} */ (null),
    credencialesVenianDeAlmacen: false,
    qrGenerados: 0,
    avisoVersion: /** @type {string | null} */ (null),
  };

  /** @param {string} valor */
  function ponerConexion(valor) {
    if (estado.conexion === valor) return;
    estado.conexion = valor;
    estado.conexionDesde = Date.now();
  }

  /** @param {string} prefijo @param {unknown} e */
  function anotarError(prefijo, e) {
    const msg = e instanceof Error ? e.message : String(e);
    estado.ultimoError = enmascarar(`${prefijo}: ${msg}`).slice(0, 300);
    log.error(`${prefijo}:`, enmascarar(msg));
  }

  /** @param {string} motivo */
  function ignorar(motivo) {
    estado.ignorados[motivo] = (estado.ignorados[motivo] ?? 0) + 1;
  }

  // ── QR ───────────────────────────────────────────────────────────────────

  /** @type {string | null} */
  let qrActual = null;
  let qrEn = 0;
  let qrGenerados = 0;

  /** El QR solo si todavía sirve, y nunca con la sesión conectada. Uno vencido es peor que ninguno. */
  function qrVigente() {
    if (!qrActual) return null;
    if (estado.conexion === "conectada" || Date.now() - qrEn > QR_VENCE_MS) {
      qrActual = null;
      return null;
    }
    return qrActual;
  }

  // ── El socket ────────────────────────────────────────────────────────────

  /** @type {any} */
  let socket = null;
  let generacion = 0;
  let reconexionProgramada = false;
  let intentosReconexion = 0;
  /** Verdadero mientras el arranque inicial siga reintentando por su cuenta. */
  let arrancando = true;
  /** Cuándo se abrió el último socket: cada intento nuevo tiene `vigilanteMs` para conectar antes de que el vigilante lo recicle. */
  let intentoDesde = 0;

  // Lo que mandó el bot contra lo que mandó una persona.
  const enviadosPorElBot = crearRegistroDeEnvios();
  /** Textos enviados, para `getMessage` (Baileys los pide si el cliente reclama un reenvío). */
  const textosEnviados = new Map();
  /** Último mensaje de cada cliente: para marcarlo leído justo antes de contestar. */
  const ultimosEntrantes = new Map();
  /** Ids de entrantes ya vistos (WhatsApp a veces entrega dos veces tras reconectar). */
  const vistos = new Set();

  /**
   * Cierra el socket anterior ANTES de abrir otro.
   *
   * Sin esto se arma una tormenta que se alimenta sola: WhatsApp admite una sola
   * conexión por dispositivo vinculado, así que el socket nuevo expulsa al viejo,
   * el viejo dispara su `close`, ese `close` programa otra reconexión, y la
   * siguiente expulsa a la nueva. Quitarle los listeners es igual de importante:
   * un socket muerto sigue emitiendo eventos que pisan el estado compartido.
   */
  function cerrarAnterior() {
    if (!socket) return;
    try {
      socket.ev.removeAllListeners();
    } catch {
      /* ya estaba cerrado */
    }
    try {
      socket.end(undefined);
    } catch {
      /* ya estaba cerrado */
    }
    socket = null;
  }

  /** Los ids que el Worker recuerda haber enviado: sobreviven a un reinicio del contenedor. */
  async function precargarEnviados() {
    try {
      const r = await puente("/puente/enviados");
      if (!r.ok) return;
      const cuerpo = await r.json();
      if (Array.isArray(cuerpo?.ids)) enviadosPorElBot.cargar(cuerpo.ids);
    } catch {
      // Una ayuda, no un requisito: sin esto solo se pierde la memoria de ecos viejos.
    }
  }

  async function conectar() {
    cerrarAnterior();
    const mia = ++generacion;

    const { state, saveCreds, veniaGuardada } = await crearEstadoRemoto(kv, baileys);
    estado.credencialesVenianDeAlmacen = veniaGuardada;
    await precargarEnviados();

    // Consultar la versión del protocolo es una comodidad, NO un requisito: Baileys
    // trae una por defecto. Sin este `try` se vuelve un punto único de fallo.
    let version;
    try {
      ({ version } = await baileys.fetchLatestBaileysVersion());
      estado.avisoVersion = null;
    } catch (e) {
      estado.avisoVersion = `sin consultar (${e instanceof Error ? e.message : String(e)})`;
    }

    // Otro conectar() más nuevo nos adelantó mientras esperábamos: gana el último.
    if (mia !== generacion) return;
    cerrarAnterior();

    const s = baileys.makeWASocket({
      version,
      auth: state,
      logger,
      browser: navegador,
      syncFullHistory: false,
      // No marcarse «en línea» al conectar: si el puente se anuncia en línea, el
      // teléfono de la dueña deja de sonar con los mensajes nuevos.
      markOnlineOnConnect: false,
      getMessage: async (/** @type {any} */ key) => textosEnviados.get(key?.id),
    });
    socket = s;
    intentoDesde = Date.now();

    /** Un socket viejo que todavía emite eventos no tiene voz. */
    const vigente = () => mia === generacion;

    s.ev.on("creds.update", () => {
      if (!vigente()) return;
      saveCreds().catch((/** @type {unknown} */ e) => anotarError("saveCreds", e));
    });

    s.ev.on("connection.update", async (/** @type {any} */ u) => {
      if (!vigente()) return;
      const { connection, lastDisconnect, qr } = u;

      if (qr) {
        ponerConexion("esperando-qr");
        try {
          qrActual = await generadorQr.toDataURL(qr, { width: 512, margin: 2 });
          qrEn = Date.now();
          qrGenerados += 1;
          // Solo el número de orden: el contenido del QR NUNCA va a los logs.
          log.log(`QR nuevo disponible (#${qrGenerados}).`);
        } catch (e) {
          anotarError("qr", e);
        }
      }

      if (connection === "open") {
        ponerConexion("conectada");
        estado.vinculadoComo = enmascarar(s.user?.id ?? "") || null;
        estado.ultimoError = null;
        intentosReconexion = 0;
        qrActual = null; // ya no sirve, y servirlo sería un riesgo
        log.log("Conectada.");
      }

      if (connection === "close") {
        // Sin `instanceof Boom`: Baileys y esta app pueden traer versiones distintas
        // de la librería y el instanceof fallaría en silencio. Se lee el código a pelo.
        const causa = Number(lastDisconnect?.error?.output?.statusCode ?? 0);
        ponerConexion("cerrada");
        estado.ultimoError = `cierre ${causa}`;

        if (causa === CIERRE.loggedOut) {
          // El teléfono desvinculó el dispositivo. Las credenciales ya no valen, y NO
          // se reconecta: sin sesión, insistir solo genera un QR tras otro.
          log.log("Sesión cerrada desde el teléfono. Limpiando credenciales.");
          await kv.del("creds").catch(() => {});
          estado.vinculadoComo = null;
          ponerConexion("desvinculada");
          return;
        }
        programarReconexion(causa);
      }
    });

    // Los mensajes entrantes se reenvían al Worker, que los pasa a Juan. El
    // contenedor no conoce a Juan: así el token de Juan no viaja hasta aquí.
    s.ev.on("messages.upsert", (/** @type {any} */ u) => {
      if (!vigente()) return;
      alLlegarMensajes(s, u.messages ?? [], u.type);
    });
  }

  /**
   * Programa UNA reconexión, y garantiza que la cadena NO se corte.
   *
   * El 16-sep-2026 el canal del CRM de origen se quedó mudo una noche entera porque
   * si `conectar()` rechazaba —y puede: lo primero que hace es leer las credenciales
   * por HTTPS— el error se anotaba y nadie volvía a intentarlo. El `catch` que
   * vuelve a llamar a `programarReconexion` es lo que cierra ese agujero.
   *
   * @param {number} causa
   */
  function programarReconexion(causa) {
    if (reconexionProgramada) return;
    if (estado.conexion === "desvinculada") return; // esto necesita una persona
    reconexionProgramada = true;
    estado.reconexiones += 1;

    // 515 (restartRequired) es el reinicio que WhatsApp pide tras vincular: es
    // esperado y se atiende de inmediato. Lo demás espera cada vez más.
    intentosReconexion = causa === CIERRE.restartRequired ? 0 : intentosReconexion + 1;
    let espera = intentosReconexion === 0 ? 1000 : Math.min(3000 * 2 ** (intentosReconexion - 1), 60_000);
    // 440: OTRA sesión tomó el número (otro contenedor, o la dueña vinculó de nuevo).
    // Reconectar enseguida arma el pleito de «dos escritores»; se espera y se avisa.
    if (causa === CIERRE.connectionReplaced) espera = Math.max(espera, 60_000);
    estado.proximoIntentoEn = new Date(Date.now() + espera).toISOString();
    log.log(`Reconectando en ${espera} ms (cierre ${causa}).`);

    setTimeout(() => {
      reconexionProgramada = false;
      // Si mientras esperaba el socket ya se conectó (un intento lento que por fin abrió),
      // reconectar ahora tumbaría una conexión sana.
      if (estado.conexion === "conectada" && socketAbierto()) return;
      conectar().catch((e) => {
        anotarError("reconectar", e);
        // LA línea del arreglo. Sin ella la cadena termina aquí y el canal se queda
        // mudo para siempre sin que nada lo note.
        programarReconexion(causa);
      });
    }, espera);
  }

  /**
   * ¿El WebSocket sigue de verdad abierto?
   *
   * Conservador a propósito: si no se puede medir, se devuelve `true`. Declarar
   * muerto un socket sano cuesta una reconexión innecesaria; equivocarse al revés
   * solo retrasa el rescate hasta que el latido del Worker lo note.
   */
  function socketAbierto() {
    try {
      const ws = socket?.ws;
      if (!ws) return false;
      if (typeof ws.isOpen === "boolean") return ws.isOpen;
      const cual = ws.readyState ?? ws.socket?.readyState;
      if (typeof cual === "number") return cual === 1; // 1 = OPEN
      return true;
    } catch {
      return true;
    }
  }

  /**
   * El vigilante: la red de seguridad de última instancia. Cubre los casos en los
   * que el camino normal (`connection.update`) no llega a ejecutarse: una promesa
   * que rechazó, un socket que murió sin emitir `close`, un `setTimeout` perdido.
   *
   * `esperando-qr` y `desvinculada` se dejan en paz a propósito: no son fallos, son
   * estados que esperan a una persona. Reconectar ahí solo genera un código nuevo y
   * le tumba al dueño el que está mirando en la pantalla.
   */
  function vigilar() {
    estado.ultimaVigilancia = new Date().toISOString();

    if (estado.conexion === "desvinculada" || estado.conexion === "esperando-qr") return;

    if (estado.conexion === "conectada") {
      if (socketAbierto()) return;
      // Dice estar conectada y el socket no está abierto: es un zombi.
      log.error("El socket dice conectada pero no está abierto. Rescatando.");
      estado.ultimoError = "socket zombi: conectada sin socket abierto";
      estado.rescatesDelVigilante += 1;
      ponerConexion("cerrada");
      programarReconexion(0);
      return;
    }

    // `cerrada` o `arrancando`. Si ya hay algo en camino, no se pisa.
    if (reconexionProgramada || arrancando) return;
    // Y se le da al camino normal el tiempo de hacer su trabajo antes de meterse: desde que se
    // cayó, y desde que se abrió el último intento de conexión.
    if (Date.now() - Math.max(estado.conexionDesde, intentoDesde) < vigilanteMs) return;

    log.error(`Nadie está reconectando y lleva caída. Rescatando (${estado.conexion}).`);
    estado.rescatesDelVigilante += 1;
    programarReconexion(0);
  }

  // ── Lo que llega ─────────────────────────────────────────────────────────

  /** Una a la vez: el contenedor `lite` tiene 256 MiB y un archivo de 12 MB pasa varias veces por memoria. */
  const colaEntrantes = crearCola({ maxPendientes: 500, esperaMaxMs: 10 * 60_000 });

  /**
   * Los nombres del chat que conocemos. WhatsApp está pasando a identificadores LID,
   * y el mismo chat puede venir como `507…@s.whatsapp.net` o como `…@lid`.
   * @param {any} s @param {any} msg
   */
  async function nombresDelChat(s, msg) {
    /** @type {string[]} */
    const nombres = [msg.key?.remoteJid, msg.key?.remoteJidAlt].filter(Boolean);
    const mapa = s.signalRepository?.lidMapping;
    for (const jid of [...nombres]) {
      try {
        if (jid.endsWith("@lid") && mapa?.getPNForLID) nombres.push(await mapa.getPNForLID(jid));
        else if (jid.endsWith("@s.whatsapp.net") && mapa?.getLIDForPN) nombres.push(await mapa.getLIDForPN(jid));
      } catch {
        // El mapa es una ayuda, no un requisito: con el jid original alcanza casi siempre.
      }
    }
    return [...new Set(nombres.filter(Boolean).map((j) => /** @type {string} */ (sinDispositivo(j))))];
  }

  /**
   * @param {any} s
   * @param {any[]} mensajes
   * @param {string} type
   */
  function alLlegarMensajes(s, mensajes, type) {
    for (const msg of mensajes) {
      const decision = decidirUpsert(msg, type, {
        enviados: enviadosPorElBot,
        yo: [s.user?.id, s.user?.lid],
      });
      if (decision.accion === "ignorar") {
        ignorar(decision.motivo);
        continue;
      }
      const id = msg.key.id;
      if (vistos.has(id)) {
        ignorar("duplicado");
        continue;
      }
      vistos.add(id);
      if (vistos.size > VISTOS_MAX) vistos.delete(vistos.values().next().value);

      const propio = decision.accion === "propio";
      if (propio) estado.respuestasDelTelefono += 1;
      else {
        estado.mensajesRecibidos += 1;
        ultimosEntrantes.set(sinDispositivo(msg.key.remoteJid), { key: msg.key, ts: Date.now() });
        if (ultimosEntrantes.size > 200) ultimosEntrantes.delete(ultimosEntrantes.keys().next().value);
      }

      colaEntrantes.ejecutar(() => entregar(s, msg, propio)).catch((e) => anotarError("entregar", e));
    }
  }

  /**
   * Arma el JSON del contrato y lo entrega al Worker, con reintentos. Juan es
   * idempotente por `id_mensaje`, así que repetir es seguro.
   * @param {any} s @param {any} msg @param {boolean} propio
   */
  async function entregar(s, msg, propio) {
    const armado = await armarEntrante(msg, {
      propio,
      candidatos: await nombresDelChat(s, msg),
      descargarMedio: (m) =>
        baileys.downloadMediaMessage(m, "buffer", {}, { logger, reuploadRequest: s.updateMediaMessage }),
    });
    if (!armado) {
      ignorar("sin_contenido");
      return;
    }
    if (armado.payload.medio) estado.archivosRecibidos += 1;
    else if (armado.sinMedio) estado.ultimoError = `archivo no adjuntado (${JSON.stringify(armado.payload.medio_omitido)})`;

    const cuerpo = JSON.stringify(armado.payload);
    const esperas = [0, 2000, 6000];
    /** @type {unknown} */
    let ultimo = null;
    for (const espera of esperas) {
      if (espera) await dormir(espera);
      try {
        const r = await puente("/puente/entrante", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: cuerpo,
        });
        if (r.ok) return;
        const detalle = (await r.text().catch(() => "")).replace(/\s+/g, " ").slice(0, 200);
        ultimo = new Error(`entrante → ${r.status} · ${detalle}`);
        // Un 4xx es definitivo (cuerpo mal formado, token): repetir no lo arregla.
        if (r.status >= 400 && r.status < 500) break;
      } catch (e) {
        ultimo = e;
      }
    }
    estado.entregasFallidas += 1;
    throw ultimo instanceof Error ? ultimo : new Error("no se pudo entregar el mensaje");
  }

  // ── Lo que sale ──────────────────────────────────────────────────────────

  const colaEnvios = crearCola({ maxPendientes: ritmo.colaMax, esperaMaxMs: ritmo.colaEsperaMaxMs });

  /**
   * `POST /enviar`: { para, chunks, medios? } → texto, imágenes con pie y documentos.
   * @param {string} cuerpoTexto
   * @returns {Promise<{ status: number, cuerpo: any }>}
   */
  async function enviar(cuerpoTexto) {
    /** @type {unknown} */
    let crudo;
    try {
      crudo = JSON.parse(cuerpoTexto);
    } catch {
      return { status: 400, cuerpo: { error: "El cuerpo no es JSON." } };
    }
    const v = validarEnviar(crudo, { hostsPermitidos });
    if (!v.ok) return { status: v.status, cuerpo: { error: v.error } };
    const plan = v.plan;

    if (estado.conexion !== "conectada" || !socket) {
      return { status: 409, cuerpo: { error: "No hay conexión con WhatsApp.", estado: estado.conexion } };
    }

    try {
      const res = await colaEnvios.ejecutar(async () => {
        if (estado.conexion !== "conectada" || !socket) {
          return { fallo: { status: 409, cuerpo: { error: "No hay conexión con WhatsApp.", estado: estado.conexion } } };
        }
        // Los archivos se bajan DENTRO del turno (uno a la vez, la memoria es poca) y
        // ANTES del primer mensaje: si uno no sirve, no sale una respuesta a medias.
        /** @type {import("./lib/envio.mjs").MedioListo[]} */
        const medios = [];
        for (const [i, m] of plan.medios.entries()) {
          const r = await descargar(m.url, {
            tipo: m.tipo,
            mimesPermitidos: MIMES_SALIENTES[m.tipo],
            maxBytes: LIMITE_SALIENTE[m.tipo],
            hostsPermitidos,
            mimeDeclarado: m.mime,
          });
          if (!r.ok) {
            return { fallo: { status: r.estado === 422 ? 422 : 502, cuerpo: { error: `medios[${i}]: ${r.motivo}.` } } };
          }
          medios.push({
            tipo: m.tipo,
            bytes: r.bytes,
            mime: r.mime,
            nombre: nombreSeguro(m.nombre, r.mime, m.tipo === "imagen" ? "imagen" : "documento"),
            pie: m.pie,
            restoPie: m.restoPie,
          });
        }
        const envio = await enviarSecuencia({
          sock: socket,
          jid: plan.para.jid,
          burbujas: plan.burbujas,
          medios,
          generarId: baileys.generateMessageIDV2,
          registro: enviadosPorElBot,
          ritmo,
          dormir,
          azar,
          ultimoEntrante: ultimosEntrantes.get(plan.para.jid) ?? null,
          alEnviar: (id, contenido) => {
            if (contenido?.text) {
              textosEnviados.set(id, { conversation: contenido.text });
              if (textosEnviados.size > 300) textosEnviados.delete(textosEnviados.keys().next().value);
            }
          },
        });
        estado.mensajesEnviados += envio.ids.length;
        return { envio };
      });

      if ("fallo" in res && res.fallo) return res.fallo;
      const envio = /** @type {NonNullable<typeof res.envio>} */ (res.envio);
      if (envio.ok) {
        return {
          status: 200,
          cuerpo: { ok: true, id_mensaje: envio.ids[envio.ids.length - 1], ids: envio.ids, enviados: envio.enviados },
        };
      }
      anotarError("enviar", envio.error);
      return {
        status: 502,
        cuerpo: { ok: false, error: envio.error, ids: envio.ids, enviados: envio.enviados, parcial: envio.ids.length > 0 },
      };
    } catch (e) {
      if (e instanceof ColaLlena || e instanceof EsperaAgotada) {
        return { status: 503, cuerpo: { error: e.message, reintentar_en_s: 30 } };
      }
      anotarError("enviar", e);
      return { status: 500, cuerpo: { error: e instanceof Error ? e.message : String(e) } };
    }
  }

  // ── HTTP interno: lo que el Worker consulta ──────────────────────────────

  /**
   * @param {{ metodo: string, ruta: string, cuerpo?: string }} peticion
   * @returns {Promise<{ status: number, cuerpo: any }>}
   */
  async function manejar({ metodo, ruta, cuerpo = "" }) {
    if (ruta === "/estado") {
      return { status: 200, cuerpo: { ...estado, enviosEnCola: colaEnvios.pendientes } };
    }

    // El error va incluido a propósito: cuando no hay QR ni conexión, el error ES la
    // información, y obligar a abrir otra ruta para verlo es esconderlo justo cuando importa.
    if (ruta === "/qr") {
      const vigente = qrVigente();
      return {
        status: 200,
        cuerpo: {
          qr: vigente,
          // La edad es el diagnóstico: un QR de 90 s explica por qué el teléfono dice
          // «Revisa tu conexión» sin que nada más falle.
          edadMs: vigente ? Date.now() - qrEn : null,
          generados: qrGenerados,
          estado: estado.conexion,
          ultimoError: estado.ultimoError,
        },
      };
    }

    if (ruta === "/enviar" && metodo === "POST") return enviar(cuerpo);

    // La empuja el latido del Durable Object cuando ve el contenedor prendido pero
    // WhatsApp desconectado. Es idempotente: si ya hay una reconexión en camino, no
    // hace nada. Lo barato antes que el martillo de destruir el contenedor entero.
    if (ruta === "/reconectar" && metodo === "POST") {
      if (estado.conexion === "desvinculada") {
        return {
          status: 409,
          cuerpo: { error: "El número está desvinculado. Hay que escanear un código nuevo.", estado: estado.conexion },
        };
      }
      programarReconexion(0);
      return {
        status: 200,
        cuerpo: {
          ok: true,
          estado: estado.conexion,
          programada: reconexionProgramada,
          proximoIntentoEn: estado.proximoIntentoEn,
        },
      };
    }

    if (ruta === "/logout" && metodo === "POST") {
      try {
        await socket?.logout();
      } catch {
        /* ya estaba cerrado */
      }
      await kv.del("creds").catch(() => {});
      ponerConexion("desvinculada");
      estado.vinculadoComo = null;
      return { status: 200, cuerpo: { ok: true } };
    }

    return { status: 404, cuerpo: { error: "no existe" } };
  }

  // ── Arranque ─────────────────────────────────────────────────────────────

  /** @type {ReturnType<typeof setInterval> | null} */
  let reloj = null;

  /**
   * Arranque con reintentos y espera creciente. Si el Worker está caído no sirve
   * reintentar cada segundo: se castiga al Worker y no se arregla nada. El proceso
   * SIGUE EN PIE, que es lo que permite leer el error desde fuera.
   */
  async function arrancar() {
    if (!reloj) {
      reloj = setInterval(() => {
        // Dentro de un try: una excepción aquí mataría el intervalo, y un vigilante
        // que se muere en silencio es peor que no tener vigilante.
        try {
          vigilar();
        } catch (e) {
          anotarError("vigilante", e);
        }
      }, vigilanteMs);
    }
    let intentos = 0;
    for (;;) {
      try {
        await conectar();
        // A partir de aquí el vigilante manda: el bucle de arranque ya no reintenta.
        arrancando = false;
        return;
      } catch (e) {
        intentos += 1;
        anotarError(`arranque (intento ${intentos})`, e);
        await dormir(Math.min(2000 * 2 ** (intentos - 1), 60_000));
      }
    }
  }

  function detener() {
    if (reloj) clearInterval(reloj);
    reloj = null;
    cerrarAnterior();
  }

  return {
    estado,
    manejar,
    arrancar,
    detener,
    vigilar,
    anotarError,
    /** Solo para pruebas. */
    _interno: { programarReconexion, conectar, get socket() { return socket; }, enviadosPorElBot, colaEnvios },
  };
}
