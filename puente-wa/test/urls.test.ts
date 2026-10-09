import { describe, expect, it } from "vitest";
import {
  esIpPublica,
  hostPermitido,
  parseIPv4,
  parseIPv6,
  parsearListaHosts,
  validarUrlMedio,
} from "../contenedor/lib/urls.mjs";

describe("parseIPv4 / parseIPv6", () => {
  it("lee direcciones válidas", () => {
    expect(parseIPv4("192.168.1.10")).toEqual([192, 168, 1, 10]);
    expect(parseIPv6("::1")).toEqual([0, 0, 0, 0, 0, 0, 0, 1]);
    expect(parseIPv6("2001:db8::ff00:42:8329")).toEqual([0x2001, 0xdb8, 0, 0, 0, 0xff00, 0x42, 0x8329]);
    expect(parseIPv6("::ffff:10.0.0.1")).toEqual([0, 0, 0, 0, 0, 0xffff, 0x0a00, 0x0001]);
    expect(parseIPv6("1:2:3:4:5:6:7:8")).toEqual([1, 2, 3, 4, 5, 6, 7, 8]);
    expect(parseIPv6("1:2:3:4:5:6:7::")).toEqual([1, 2, 3, 4, 5, 6, 7, 0]);
  });

  it("rechaza lo ambiguo o mal formado", () => {
    for (const mala of ["1.2.3", "1.2.3.4.5", "256.1.1.1", "01.2.3.4", "1.2.3.-4", "a.b.c.d", "10.0.0.1/8"]) {
      expect(parseIPv4(mala)).toBe(null);
    }
    for (const mala of ["", "1:2:3", ":::", "1::2::3", "12345::1", "fe80::1%eth0", "1:2:3:4:5:6:7:8:9", "g::1", "[::1]"]) {
      expect(parseIPv6(mala)).toBe(null);
    }
  });
});

describe("esIpPublica", () => {
  it.each([
    "8.8.8.8",
    "1.1.1.1",
    "104.16.1.1",
    "172.15.255.255", // justo antes de 172.16/12
    "172.32.0.1", // justo después
    "100.63.255.255", // justo antes del CGNAT
    "100.128.0.1", // justo después
    "198.17.255.255",
    "198.20.0.1",
    "2606:4700:4700::1111", // Cloudflare
    "2a00:1450:4001:81b::200e",
    "::ffff:8.8.8.8", // IPv4 mapeada pública
    "64:ff9b::808:808", // NAT64 hacia 8.8.8.8
  ])("%s es pública", (ip) => {
    expect(esIpPublica(ip)).toBe(true);
  });

  it.each([
    // IPv4 internas, de enlace local, de metadatos, de documentación…
    "0.0.0.0",
    "0.1.2.3",
    "10.0.0.1",
    "10.255.255.255",
    "100.64.0.1",
    "100.127.255.255",
    "127.0.0.1",
    "127.255.255.254",
    "169.254.169.254", // metadatos de la nube
    "169.254.0.1",
    "172.16.0.1",
    "172.31.255.255",
    "192.0.0.1",
    "192.0.2.1",
    "192.88.99.1",
    "192.168.0.1",
    "192.168.255.255",
    "198.18.0.1",
    "198.19.255.255",
    "198.51.100.7",
    "203.0.113.7",
    "224.0.0.1",
    "239.255.255.255",
    "240.0.0.1",
    "255.255.255.255",
    // IPv6 no públicas
    "::",
    "::1",
    "fc00::1",
    "fd12:3456:789a::1",
    "fe80::1",
    "fec0::1",
    "ff02::1",
    "2001:db8::1",
    "2001::1", // Teredo / protocolo IETF
    "100::1",
    "3fff::1",
    "::ffff:127.0.0.1", // IPv4 mapeada interna
    "::ffff:10.1.2.3",
    "::ffff:169.254.169.254",
    "64:ff9b::a00:1", // NAT64 hacia 10.0.0.1
    "64:ff9b:1::1",
    "2002:7f00:1::1", // 6to4 hacia 127.0.0.1
    "2002:a9fe:a9fe::1", // 6to4 hacia 169.254.169.254
  ])("%s NO es pública", (ip) => {
    expect(esIpPublica(ip)).toBe(false);
  });

  it("lo que no se puede leer como IP no es pública", () => {
    for (const x of ["", "dcasapty.com", "999.1.1.1", "01.1.1.1", null, undefined, "1.2.3"]) {
      expect(esIpPublica(x)).toBe(false);
    }
  });

  it("acepta corchetes", () => {
    expect(esIpPublica("[2606:4700:4700::1111]")).toBe(true);
    expect(esIpPublica("[::1]")).toBe(false);
  });
});

describe("hostPermitido y lista de dominios", () => {
  const lista = parsearListaHosts("dcasapty.com, *.workers.dev ,  .Cdn.Ejemplo.com, no es un dominio, localhost");

  it("limpia la lista", () => {
    expect(lista).toEqual(["dcasapty.com", "workers.dev", "cdn.ejemplo.com"]);
    expect(parsearListaHosts(undefined)).toEqual([]);
    expect(parsearListaHosts("")).toEqual([]);
  });

  it("el dominio y sus subdominios, con borde de punto", () => {
    expect(hostPermitido("dcasapty.com", lista)).toBe(true);
    expect(hostPermitido("www.dcasapty.com", lista)).toBe(true);
    expect(hostPermitido("dcasa-staging.dcasapty.workers.dev", lista)).toBe(true);
    expect(hostPermitido("DCASAPTY.COM", lista)).toBe(true);
    expect(hostPermitido("malo-dcasapty.com", lista)).toBe(false);
    expect(hostPermitido("dcasapty.com.malo.net", lista)).toBe(false);
    expect(hostPermitido("evil.com", lista)).toBe(false);
  });

  it("lista vacía = sin restricción de dominio", () => {
    expect(hostPermitido("cualquiera.com", [])).toBe(true);
  });
});

describe("validarUrlMedio (SSRF)", () => {
  const ok = (u: string, hosts: string[] = []) => validarUrlMedio(u, { hostsPermitidos: hosts });

  it("acepta una URL https normal", () => {
    const r = ok("https://dcasapty.com/web/image/product.template/12/image_1024");
    expect(r.ok).toBe(true);
    if (r.ok) expect(r.url.hostname).toBe("dcasapty.com");
    expect(ok("https://dcasapty.com:443/x.jpg").ok).toBe(true);
  });

  it.each([
    ["http://dcasapty.com/x.jpg", "https"],
    ["ftp://dcasapty.com/x.jpg", "https"],
    ["file:///etc/passwd", "https"],
    ["data:image/png;base64,AAAA", "https"],
    ["javascript:alert(1)", "https"],
    ["//dcasapty.com/x.jpg", "válida"],
    ["dcasapty.com/x.jpg", "válida"],
    ["", "falta"],
    ["https://usuario:clave@dcasapty.com/x.jpg", "usuario"],
    ["https://usuario@dcasapty.com/x.jpg", "usuario"],
    ["https://dcasapty.com:8443/x.jpg", "puerto"],
    ["https://dcasapty.com:22/x.jpg", "puerto"],
  ])("rechaza %s", (url, parte) => {
    const r = ok(url);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.motivo).toContain(parte);
  });

  it.each([
    "https://127.0.0.1/x.jpg",
    "https://10.0.0.5/x.jpg",
    "https://169.254.169.254/latest/meta-data/",
    "https://8.8.8.8/x.jpg", // ni siquiera una IP pública: solo nombres
    "https://[::1]/x.jpg",
    "https://[2606:4700:4700::1111]/x.jpg",
    "https://[::ffff:127.0.0.1]/x.jpg",
    "https://2130706433/x.jpg", // 127.0.0.1 en decimal
    "https://0x7f000001/x.jpg", // en hexadecimal
    "https://0177.0.0.1/x.jpg", // en octal
    "https://127.1/x.jpg", // abreviado
    "https://0/x.jpg",
  ])("rechaza la IP escrita de cualquier forma: %s", (url) => {
    const r = ok(url);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.motivo).toMatch(/IP|válida/);
  });

  it.each([
    "https://localhost/x.jpg",
    "https://LOCALHOST/x.jpg",
    "https://localhost./x.jpg",
    "https://app.localhost/x.jpg",
    "https://servidor/x.jpg", // un solo nombre, sin punto
    "https://impresora.local/x.jpg",
    "https://metadata.google.internal/x",
    "https://nas.lan/x.jpg",
    "https://router.home.arpa/x.jpg",
    "https://wiki.intranet/x.jpg",
  ])("rechaza nombres internos: %s", (url) => {
    const r = ok(url);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.motivo).toContain("internos");
  });

  it("con lista de dominios, solo esos (y sus subdominios)", () => {
    const hosts = ["dcasapty.com", "dcasapty.workers.dev"];
    expect(ok("https://dcasapty.com/x.jpg", hosts).ok).toBe(true);
    expect(ok("https://www.dcasapty.com/x.jpg", hosts).ok).toBe(true);
    expect(ok("https://dcasa.dcasapty.workers.dev/x.jpg", hosts).ok).toBe(true);
    const mala = ok("https://evil.com/x.jpg", hosts);
    expect(mala.ok).toBe(false);
    if (!mala.ok) expect(mala.motivo).toContain("lista de permitidos");
    expect(ok("https://dcasapty.com.evil.com/x.jpg", hosts).ok).toBe(false);
    expect(ok("https://evil.com/dcasapty.com/x.jpg", hosts).ok).toBe(false);
    expect(ok("https://evil.com/?u=dcasapty.com", hosts).ok).toBe(false);
  });

  it("una URL absurdamente larga no pasa", () => {
    expect(ok(`https://dcasapty.com/${"a".repeat(3000)}`).ok).toBe(false);
  });

  it("no acepta lo que no es texto", () => {
    expect(validarUrlMedio(undefined).ok).toBe(false);
    expect(validarUrlMedio(123).ok).toBe(false);
    expect(validarUrlMedio({}).ok).toBe(false);
  });
});
