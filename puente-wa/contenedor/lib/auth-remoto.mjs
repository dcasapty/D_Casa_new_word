// @ts-check
// El equivalente de `useMultiFileAuthState` de Baileys, pero contra el Worker.
//
// Baileys guarda dos cosas: `creds`, que es la identidad del dispositivo vinculado,
// y las llaves de sesión de Signal. Mientras `creds` sobreviva, no hay QR nuevo —
// y eso es lo que hace viable este canal.
//
// Aquí NO tocan el disco: el disco del contenedor es descartable. Van al Worker,
// que las guarda CIFRADAS en el almacenamiento SQLite del Durable Object (en el
// CRM de origen iban a una base D1; aquí no se crea ningún recurso extra).
//
// El almacén por LOTES no es una optimización: es lo que hace que el canal se
// pueda vincular. Al emparejar, WhatsApp exige subir 812 llaves de un solo uso;
// Baileys las entrega al almacén en UNA llamada y enseguida las relee todas.
// Sirviéndolas de a una son ~1.600 viajes y Baileys corta la operación a los 30 s
// (UPLOAD_TIMEOUT). Se midió en el CRM de origen: de a una, el emparejamiento moría
// a mitad de camino y el teléfono quedaba vinculado a un dispositivo que nunca
// terminó de instalarse. Los valores viajan ya serializados con el replacer de
// Baileys (que sabe convertir sus Buffer); el Worker los guarda como texto.

/**
 * @typedef {(ruta: string, init?: any) => Promise<{ ok: boolean, status: number, text(): Promise<string>, json(): Promise<any> }>} Puente
 */

/** El cuerpo del error, recortado. El Worker explica ahí por qué rechazó. */
/** @param {{ text(): Promise<string> }} r */
async function porQue(r) {
  try {
    return (await r.text()).replace(/\s+/g, " ").slice(0, 300);
  } catch {
    return "";
  }
}

/**
 * Cliente del almacén remoto de claves.
 * @param {Puente} puente
 * @param {{ reviver: any, replacer: any }} BufferJSON
 */
export function crearClienteKv(puente, BufferJSON) {
  return {
    async get(/** @type {string} */ clave) {
      const r = await puente(`/puente/kv?clave=${encodeURIComponent(clave)}`);
      if (r.status === 404) return null;
      if (!r.ok) throw new Error(`kvGet(${clave}) → ${r.status} · ${await porQue(r)}`);
      return JSON.parse(await r.text(), BufferJSON.reviver);
    },
    async set(/** @type {string} */ clave, /** @type {unknown} */ valor) {
      const r = await puente(`/puente/kv?clave=${encodeURIComponent(clave)}`, {
        method: "PUT",
        body: JSON.stringify(valor, BufferJSON.replacer),
      });
      if (!r.ok) throw new Error(`kvSet(${clave}) → ${r.status} · ${await porQue(r)}`);
    },
    async del(/** @type {string} */ clave) {
      await puente(`/puente/kv?clave=${encodeURIComponent(clave)}`, { method: "DELETE" });
    },
    async lote(/** @type {{ leer?: string[], escribir?: Record<string, string>, borrar?: string[] }} */ cuerpo) {
      const r = await puente("/puente/kv-lote", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(cuerpo),
      });
      if (!r.ok) throw new Error(`kvLote → ${r.status} · ${await porQue(r)}`);
      return r.json();
    },
  };
}

/**
 * @param {ReturnType<typeof crearClienteKv>} kv
 * @param {{ BufferJSON: any, initAuthCreds: () => any, proto: any }} baileys
 * @returns {Promise<{ state: any, saveCreds: () => Promise<void>, veniaGuardada: boolean }>}
 */
export async function crearEstadoRemoto(kv, { BufferJSON, initAuthCreds, proto }) {
  const guardadas = await kv.get("creds");
  const creds = guardadas || initAuthCreds();

  return {
    veniaGuardada: Boolean(guardadas),
    state: {
      creds,
      keys: {
        // Una sola petición para TODAS las ids. Baileys pide de a cientos.
        get: async (/** @type {string} */ tipo, /** @type {string[]} */ ids) => {
          /** @type {Record<string, any>} */
          const salida = {};
          if (!ids.length) return salida;
          const { valores } = await kv.lote({ leer: ids.map((id) => `${tipo}-${id}`) });
          for (const id of ids) {
            const crudo = valores[`${tipo}-${id}`];
            if (crudo == null) {
              salida[id] = null;
              continue;
            }
            // El reviver de Baileys reconstruye sus Buffer. El Worker devuelve el
            // texto tal como se guardó, sin interpretarlo.
            let valor = JSON.parse(crudo, BufferJSON.reviver);
            // Caso especial documentado por Baileys: esta llave tiene que volver
            // como mensaje de protobuf, no como objeto pelado.
            if (tipo === "app-state-sync-key" && valor) {
              valor = proto.Message.AppStateSyncKeyData.fromObject(valor);
            }
            salida[id] = valor;
          }
          return salida;
        },
        // El lote entero en una petición: es el camino de las 812 llaves del emparejamiento.
        set: async (/** @type {Record<string, Record<string, any>>} */ datos) => {
          /** @type {Record<string, string>} */
          const escribir = {};
          /** @type {string[]} */
          const borrar = [];
          for (const tipo in datos) {
            for (const id in datos[tipo]) {
              const valor = datos[tipo][id];
              const clave = `${tipo}-${id}`;
              if (valor) escribir[clave] = JSON.stringify(valor, BufferJSON.replacer);
              else borrar.push(clave);
            }
          }
          if (!Object.keys(escribir).length && !borrar.length) return;
          await kv.lote({ escribir, borrar });
        },
      },
    },
    saveCreds: () => kv.set("creds", creds),
  };
}
