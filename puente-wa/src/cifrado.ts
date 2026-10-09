// Cifrado en reposo de la sesión de WhatsApp.
//
// Las credenciales de Baileys (`creds` y las llaves de Signal) son lo que permite
// hablar COMO el número del negocio. Quien las lea puede vincularse como la tienda.
// Por eso nunca se guardan en claro: cada valor se cifra con AES-GCM antes de
// llegar al almacenamiento del Durable Object (y por tanto también en las copias).
//
// La clave sale del secreto `WA_SESION_CLAVE` (HKDF-SHA-256). Es un secreto APARTE
// de `WA_TOKEN` a propósito: el token se puede rotar sin avisar (si se filtra, se
// cambia) y la clave de cifrado NO — rotarla deja ilegible la sesión y obliga a
// escanear el QR de nuevo. Mismo trato que `DCASA_PIN_PEPPER`: se genera una vez, se
// respalda y no se toca. Para cambiarla de verdad hay un procedimiento con
// `WA_SESION_CLAVE_ANTERIOR` + `/api/recifrar` (docs/JUAN_PUENTE.md).
//
// Formato de cada valor cifrado:  v1.<kid>.<iv>.<cifrado>   (base64url)
//   · kid: identifica con qué clave se cifró (para poder rotar sin perder nada);
//   · iv:  12 bytes al azar, distinto en cada cifrado;
//   · el nombre de la clave (`creds`, `pre-key-12`…) va como dato autenticado: un
//     valor cifrado copiado a OTRA fila no descifra (nadie puede intercambiar filas).

const SAL = "dcasa-puente-wa/sesion";
const INFO = "dcasa-puente-wa/sesion/v1";
const codificar = new TextEncoder();
const decodificar = new TextDecoder();

export interface Cifrador {
  /** Identificador de la clave actual: sale de una derivación aparte y no revela nada de la clave. */
  readonly kid: string;
  cifrar(nombre: string, texto: string): Promise<string>;
  descifrar(nombre: string, cifrado: string): Promise<string>;
  /** ¿Este valor está cifrado con la clave ACTUAL (y no con la anterior)? */
  esActual(cifrado: string): boolean;
}

function aBase64Url(bytes: Uint8Array): string {
  let binario = "";
  const trozo = 0x8000;
  for (let i = 0; i < bytes.length; i += trozo) {
    binario += String.fromCharCode(...bytes.subarray(i, i + trozo));
  }
  return btoa(binario).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function deBase64Url(texto: string): Uint8Array<ArrayBuffer> {
  const base64 = texto.replace(/-/g, "+").replace(/_/g, "/");
  const relleno = base64.length % 4 === 0 ? "" : "=".repeat(4 - (base64.length % 4));
  return Uint8Array.from(atob(base64 + relleno), (c) => c.charCodeAt(0));
}

interface Llave {
  kid: string;
  llave: CryptoKey;
}

async function derivar(secreto: string): Promise<Llave> {
  if (secreto.length < 32) {
    throw new Error("WA_SESION_CLAVE es demasiado corta (mínimo 32 caracteres).");
  }
  const base = await crypto.subtle.importKey("raw", codificar.encode(secreto), "HKDF", false, ["deriveKey", "deriveBits"]);
  const params = { name: "HKDF", hash: "SHA-256", salt: codificar.encode(SAL) } as const;
  const llave = await crypto.subtle.deriveKey(
    { ...params, info: codificar.encode(INFO) },
    base,
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt", "decrypt"],
  );
  // El identificador sale de OTRA derivación: no revela nada de la clave.
  const bits = await crypto.subtle.deriveBits({ ...params, info: codificar.encode(`${INFO}/kid`) }, base, 48);
  return { kid: aBase64Url(new Uint8Array(bits)), llave };
}

/**
 * @param secreto  `WA_SESION_CLAVE`.
 * @param anterior `WA_SESION_CLAVE_ANTERIOR`, solo durante una rotación.
 */
export async function crearCifrador(secreto: string, anterior?: string): Promise<Cifrador> {
  const actual = await derivar(secreto);
  const llaves = new Map<string, CryptoKey>([[actual.kid, actual.llave]]);
  if (anterior) {
    const vieja = await derivar(anterior);
    llaves.set(vieja.kid, vieja.llave);
  }

  return {
    kid: actual.kid,

    async cifrar(nombre, texto) {
      const iv = crypto.getRandomValues(new Uint8Array(12));
      const cifrado = await crypto.subtle.encrypt(
        { name: "AES-GCM", iv, additionalData: codificar.encode(nombre) },
        actual.llave,
        codificar.encode(texto),
      );
      return `v1.${actual.kid}.${aBase64Url(iv)}.${aBase64Url(new Uint8Array(cifrado))}`;
    },

    async descifrar(nombre, cifrado) {
      const partes = cifrado.split(".");
      if (partes.length !== 4 || partes[0] !== "v1") throw new Error(`El valor de «${nombre}» no está cifrado en un formato conocido.`);
      const llave = llaves.get(partes[1]);
      if (!llave) {
        throw new Error(
          `«${nombre}» está cifrado con una clave que este Worker no tiene (kid ${partes[1]}). ¿Cambió WA_SESION_CLAVE?`,
        );
      }
      try {
        const claro = await crypto.subtle.decrypt(
          { name: "AES-GCM", iv: deBase64Url(partes[2]), additionalData: codificar.encode(nombre) },
          llave,
          deBase64Url(partes[3]),
        );
        return decodificar.decode(claro);
      } catch {
        // Sin detalles: el error de WebCrypto no dice nada útil y no debe filtrar nada.
        throw new Error(`No se pudo descifrar «${nombre}»: el valor está alterado o es de otra fila.`);
      }
    },

    esActual(cifrado) {
      return cifrado.startsWith(`v1.${actual.kid}.`);
    },
  };
}
