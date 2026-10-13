// @ts-check
// Validación de URLs de medios y de direcciones IP. Defensa contra SSRF.
//
// El Worker `juan` manda URLs de imágenes y documentos para que el puente las
// descargue y las mande por WhatsApp. Esa descarga sale del contenedor, que vive
// dentro de la red de Cloudflare: si alguien lograra que el bot «mande la foto»
// de una URL interna (metadatos de la nube, servicios locales, la red del
// proveedor), el contenedor sería un trampolín. Reglas:
//
//   · solo https, puerto 443, sin usuario ni contraseña en la URL;
//   · nada de direcciones IP escritas en la URL (todo origen legítimo tiene nombre);
//   · nada de nombres internos (localhost, *.local, *.internal…);
//   · opcionalmente, solo dominios de una lista (MEDIOS_HOSTS_PERMITIDOS);
//   · tras resolver el nombre, TODAS las direcciones tienen que ser públicas;
//   · cada redirección vuelve a pasar por todo esto (lo hace descarga.mjs).
//
// Este archivo es puro (sin red, sin módulos de Node) para poder usarse igual en
// el Worker y en el contenedor, y para probarse a fondo.

/**
 * Dirección IPv4 estricta «a.b.c.d» → [a, b, c, d], o null.
 * Rechaza ceros a la izquierda («010.0.0.1» se lee en octal en algunos
 * sistemas y en decimal en otros: ambigüedad que no se admite).
 * @param {string} texto
 * @returns {number[] | null}
 */
export function parseIPv4(texto) {
  const partes = String(texto).split(".");
  if (partes.length !== 4) return null;
  const salida = [];
  for (const p of partes) {
    if (!/^\d{1,3}$/.test(p)) return null;
    if (p.length > 1 && p.startsWith("0")) return null;
    const n = Number(p);
    if (n > 255) return null;
    salida.push(n);
  }
  return salida;
}

/**
 * Dirección IPv6 → 8 grupos de 16 bits, o null. Admite «::» y un IPv4 al final
 * («::ffff:1.2.3.4»). No admite identificador de zona («%eth0») ni corchetes.
 * @param {string} texto
 * @returns {number[] | null}
 */
export function parseIPv6(texto) {
  let t = String(texto);
  if (!t.includes(":") || t.includes("%") || /[^0-9a-fA-F:.]/.test(t)) return null;

  // IPv4 incrustado al final → dos grupos.
  const ultimoDosPuntos = t.lastIndexOf(":");
  const cola = t.slice(ultimoDosPuntos + 1);
  if (cola.includes(".")) {
    const v4 = parseIPv4(cola);
    if (!v4) return null;
    t = `${t.slice(0, ultimoDosPuntos + 1)}${((v4[0] << 8) | v4[1]).toString(16)}:${((v4[2] << 8) | v4[3]).toString(16)}`;
  }

  const dobles = t.split("::");
  if (dobles.length > 2) return null;
  /** @param {string} s */
  const grupos = (s) => (s === "" ? [] : s.split(":"));
  const izq = grupos(dobles[0]);
  const der = dobles.length === 2 ? grupos(dobles[1]) : [];
  if (dobles.length === 1 && izq.length !== 8) return null;
  if (dobles.length === 2 && izq.length + der.length > 7) return null;

  const relleno = dobles.length === 2 ? new Array(8 - izq.length - der.length).fill("0") : [];
  const todos = [...izq, ...relleno, ...der];
  if (todos.length !== 8) return null;
  const salida = [];
  for (const g of todos) {
    if (!/^[0-9a-fA-F]{1,4}$/.test(g)) return null;
    salida.push(parseInt(g, 16));
  }
  return salida;
}

/** @param {number[]} ip */
function ipv4EsPublica([a, b, c]) {
  if (a === 0) return false; // 0.0.0.0/8 «esta red»
  if (a === 10) return false; // privada
  if (a === 100 && b >= 64 && b <= 127) return false; // 100.64.0.0/10 CGNAT
  if (a === 127) return false; // loopback
  if (a === 169 && b === 254) return false; // enlace local (incluye metadatos 169.254.169.254)
  if (a === 172 && b >= 16 && b <= 31) return false; // privada
  if (a === 192 && b === 0 && c === 0) return false; // 192.0.0.0/24 protocolo IETF
  if (a === 192 && b === 0 && c === 2) return false; // documentación
  if (a === 192 && b === 88 && c === 99) return false; // 6to4 relé
  if (a === 192 && b === 168) return false; // privada
  if (a === 198 && (b === 18 || b === 19)) return false; // pruebas de rendimiento
  if (a === 198 && b === 51 && c === 100) return false; // documentación
  if (a === 203 && b === 0 && c === 113) return false; // documentación
  if (a >= 224) return false; // multicast, reservadas y difusión
  return true;
}

/** @param {number[]} g */
function ipv6EsPublica(g) {
  // IPv4 mapeada (::ffff:a.b.c.d): manda la IPv4 de adentro.
  if (g.slice(0, 5).every((x) => x === 0) && g[5] === 0xffff) {
    return ipv4EsPublica([g[6] >> 8, g[6] & 255, g[7] >> 8, g[7] & 255]);
  }
  // NAT64 (64:ff9b::/96): manda la IPv4 de adentro. El «de uso local» (64:ff9b:1::/48) no.
  if (g[0] === 0x64 && g[1] === 0xff9b) {
    if (g.slice(2, 6).every((x) => x === 0)) {
      return ipv4EsPublica([g[6] >> 8, g[6] & 255, g[7] >> 8, g[7] & 255]);
    }
    return false;
  }
  // 6to4 (2002::/16): manda la IPv4 de adentro.
  if (g[0] === 0x2002) return ipv4EsPublica([g[1] >> 8, g[1] & 255, g[2] >> 8, g[2] & 255]);
  // Solo el unicast global (2000::/3) puede ser público; todo lo demás (::, ::1,
  // fc00::/7, fe80::/10, fec0::/10, ff00::/8…) queda fuera por construcción.
  if ((g[0] & 0xe000) !== 0x2000) return false;
  if (g[0] === 0x2001 && (g[1] & 0xfe00) === 0) return false; // 2001::/23 protocolo IETF (Teredo…)
  if (g[0] === 0x2001 && g[1] === 0x0db8) return false; // documentación
  if (g[0] === 0x3fff && (g[1] & 0xf000) === 0) return false; // 3fff::/20 documentación
  return true;
}

/**
 * ¿Es una dirección IP pública (alcanzable en internet y no interna)?
 * Cualquier cosa que no se pueda leer como IP devuelve false.
 * @param {unknown} ip
 */
export function esIpPublica(ip) {
  const t = String(ip ?? "").trim().replace(/^\[|\]$/g, "");
  const v4 = parseIPv4(t);
  if (v4) return ipv4EsPublica(v4);
  const v6 = parseIPv6(t);
  if (v6) return ipv6EsPublica(v6);
  return false;
}

/**
 * «a.com, b.com» → ["a.com", "b.com"] (minúsculas, sin «*.» ni puntos de borde;
 * se descartan entradas que no parezcan un nombre de dominio).
 * @param {unknown} texto
 * @returns {string[]}
 */
export function parsearListaHosts(texto) {
  return String(texto ?? "")
    .split(/[,\s]+/)
    .map((h) => h.trim().toLowerCase().replace(/^\*?\./, "").replace(/\.$/, ""))
    .filter((h) => /^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$/.test(h));
}

/**
 * ¿El host es uno de los permitidos o un subdominio de ellos? Lista vacía = sin
 * restricción de dominio (las demás defensas siguen aplicando).
 * La comparación respeta el borde del punto: «malo-dcasapty.com» NO es subdominio
 * de «dcasapty.com».
 * @param {string} host
 * @param {string[]} permitidos
 */
export function hostPermitido(host, permitidos) {
  if (!permitidos.length) return true;
  const h = host.toLowerCase().replace(/\.$/, "");
  return permitidos.some((d) => h === d || h.endsWith(`.${d}`));
}

const SUFIJOS_INTERNOS = [".localhost", ".local", ".internal", ".lan", ".home.arpa", ".intranet", ".corp", ".private"];

/**
 * @typedef {{ ok: true, url: URL }} UrlOk
 * @typedef {{ ok: false, motivo: string }} UrlRechazada
 */

/**
 * Valida una URL de medio ANTES de tocar la red.
 *
 * @param {unknown} texto
 * @param {{ hostsPermitidos?: string[] }} [opciones]
 * @returns {UrlOk | UrlRechazada}
 */
export function validarUrlMedio(texto, { hostsPermitidos = [] } = {}) {
  if (typeof texto !== "string" || !texto.trim()) return { ok: false, motivo: "falta la URL" };
  if (texto.length > 2048) return { ok: false, motivo: "la URL es demasiado larga" };
  let url;
  try {
    url = new URL(texto.trim());
  } catch {
    return { ok: false, motivo: "la URL no es válida" };
  }
  if (url.protocol !== "https:") return { ok: false, motivo: "solo se aceptan URLs https" };
  if (url.username || url.password) return { ok: false, motivo: "la URL no puede llevar usuario ni contraseña" };
  if (url.port && url.port !== "443") return { ok: false, motivo: "solo se acepta el puerto 443" };

  const host = url.hostname.toLowerCase().replace(/\.$/, "");
  if (!host) return { ok: false, motivo: "la URL no tiene host" };
  // El parser WHATWG ya normaliza 2130706433, 0x7f.1, etc. a «127.0.0.1»; IPv6 llega con corchetes.
  if (host.startsWith("[") || parseIPv4(host) || parseIPv6(host)) {
    return { ok: false, motivo: "no se aceptan direcciones IP en la URL, solo nombres de dominio" };
  }
  if (!host.includes(".") || host === "localhost" || SUFIJOS_INTERNOS.some((s) => host.endsWith(s))) {
    return { ok: false, motivo: "no se aceptan nombres internos" };
  }
  if (!hostPermitido(host, hostsPermitidos)) {
    return { ok: false, motivo: `el dominio ${host} no está en la lista de permitidos` };
  }
  return { ok: true, url };
}
