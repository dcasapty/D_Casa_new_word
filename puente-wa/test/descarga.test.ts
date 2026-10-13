import http from "node:http";
import type { AddressInfo } from "node:net";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { REDIRECCIONES_MAX, crearLookupSeguro, descargarSeguro } from "../contenedor/lib/descarga.mjs";
import { MIMES_SALIENTES } from "../contenedor/lib/medios.mjs";

// Un servidor HTTP local hace de «internet». La descarga de verdad usa https.request; aquí se
// inyecta un `request` que habla con este servidor, para probar de verdad el streaming, las
// redirecciones, los topes de tamaño y los tiempos — sin red.

const JPG = Buffer.concat([Buffer.from([0xff, 0xd8, 0xff, 0xe0]), Buffer.alloc(2000, 7)]);
const PDF = Buffer.concat([Buffer.from("%PDF-1.7\n"), Buffer.alloc(1000, 65)]);
const HTML = Buffer.from("<!doctype html><html>hola</html>");

let servidor: http.Server;
let puerto = 0;
const visitas: string[] = [];

type Ruta = (req: http.IncomingMessage, res: http.ServerResponse) => void;
const rutas: Record<string, Ruta> = {
  "/foto.jpg": (_q, r) => {
    r.writeHead(200, { "content-type": "image/jpeg", "content-length": JPG.length });
    r.end(JPG);
  },
  "/foto-sin-tipo.jpg": (_q, r) => {
    r.writeHead(200, { "content-type": "application/octet-stream" });
    r.end(JPG);
  },
  "/mentira.jpg": (_q, r) => {
    // Dice ser una imagen y es una página HTML.
    r.writeHead(200, { "content-type": "image/jpeg" });
    r.end(HTML);
  },
  "/html": (_q, r) => {
    r.writeHead(200, { "content-type": "text/html" });
    r.end(HTML);
  },
  "/cotizacion.pdf": (_q, r) => {
    r.writeHead(200, { "content-type": "application/pdf" });
    r.end(PDF);
  },
  "/grande-declarado": (_q, r) => {
    r.writeHead(200, { "content-type": "image/jpeg", "content-length": 50_000_000 });
    r.end(JPG);
  },
  "/grande-chorro": (_q, r) => {
    // No declara el tamaño y manda sin parar: el corte tiene que ser en pleno chorro.
    r.writeHead(200, { "content-type": "image/jpeg" });
    r.write(JPG);
    const t = setInterval(() => r.write(Buffer.alloc(64 * 1024, 1)), 1);
    r.on("close", () => clearInterval(t));
  },
  "/vacio": (_q, r) => {
    r.writeHead(200, { "content-type": "image/jpeg", "content-length": 0 });
    r.end();
  },
  "/404": (_q, r) => {
    r.writeHead(404);
    r.end("no");
  },
  "/500": (_q, r) => {
    r.writeHead(500);
    r.end("error");
  },
  "/cuelga": () => {
    /* nunca contesta */
  },
  "/redir-bien": (_q, r) => {
    r.writeHead(302, { location: "/foto.jpg" });
    r.end();
  },
  "/redir-doble": (_q, r) => {
    r.writeHead(301, { location: "/redir-bien" });
    r.end();
  },
  "/redir-a-http": (_q, r) => {
    r.writeHead(302, { location: "http://dcasapty.com/foto.jpg" });
    r.end();
  },
  "/redir-a-metadatos": (_q, r) => {
    r.writeHead(302, { location: "https://169.254.169.254/latest/meta-data/" });
    r.end();
  },
  "/redir-a-localhost": (_q, r) => {
    r.writeHead(302, { location: "https://localhost/admin" });
    r.end();
  },
  "/redir-a-otro-dominio": (_q, r) => {
    r.writeHead(302, { location: "https://evil.example.org/foto.jpg" });
    r.end();
  },
  "/redir-sin-fin": (_q, r) => {
    r.writeHead(302, { location: "/redir-sin-fin" });
    r.end();
  },
};

beforeAll(async () => {
  servidor = http.createServer((req, res) => {
    visitas.push(req.url ?? "");
    (rutas[req.url ?? ""] ?? ((_q, r) => (r.writeHead(404), r.end())))(req, res);
  });
  await new Promise<void>((ok) => servidor.listen(0, "127.0.0.1", ok));
  puerto = (servidor.address() as AddressInfo).port;
});
afterAll(() => {
  servidor.closeAllConnections();
  servidor.close();
});

/** Un `https.request` falso: apunta SIEMPRE al servidor local, y deja registrar las opciones que recibió. */
const opcionesVistas: any[] = [];
function pedirAlLocal(url: URL, opciones: any, cb: (res: http.IncomingMessage) => void) {
  opcionesVistas.push({ host: url.hostname, ...opciones });
  return http.request({ host: "127.0.0.1", port: puerto, path: url.pathname + url.search, method: opciones.method, headers: opciones.headers }, cb);
}

const base = {
  tipo: "imagen" as const,
  mimesPermitidos: MIMES_SALIENTES.imagen,
  maxBytes: 1_000_000,
  deps: { request: pedirAlLocal as any },
};

describe("descargarSeguro: lo que sí se descarga", () => {
  it("baja una imagen y comprueba su tipo y su contenido", async () => {
    const r = await descargarSeguro("https://dcasapty.com/foto.jpg", base);
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(r.mime).toBe("image/jpeg");
      expect(Buffer.from(r.bytes).toString("hex")).toBe(JPG.toString("hex"));
    }
  });

  it("baja un documento PDF", async () => {
    const r = await descargarSeguro("https://dcasapty.com/cotizacion.pdf", {
      ...base,
      tipo: "documento",
      mimesPermitidos: MIMES_SALIENTES.documento,
    });
    expect(r.ok && r.mime).toBe("application/pdf");
  });

  it("si el origen no dice qué es (octet-stream), manda lo declarado… y el contenido tiene que coincidir", async () => {
    const r = await descargarSeguro("https://dcasapty.com/foto-sin-tipo.jpg", { ...base, mimeDeclarado: "image/jpeg" });
    expect(r.ok && r.mime).toBe("image/jpeg");
    const sin = await descargarSeguro("https://dcasapty.com/foto-sin-tipo.jpg", base);
    expect(sin.ok).toBe(false);
  });

  it("pide sin comprimir, sin reutilizar conexiones y con el lookup seguro", async () => {
    opcionesVistas.length = 0;
    await descargarSeguro("https://dcasapty.com/foto.jpg", base);
    const o = opcionesVistas[0];
    expect(o.method).toBe("GET");
    expect(o.agent).toBe(false);
    expect(o.headers["accept-encoding"]).toBe("identity");
    expect(typeof o.lookup).toBe("function");
    expect(o.host).toBe("dcasapty.com");
  });

  it("sigue redirecciones legítimas (hasta 3 saltos)", async () => {
    const una = await descargarSeguro("https://dcasapty.com/redir-bien", base);
    expect(una.ok).toBe(true);
    const dos = await descargarSeguro("https://dcasapty.com/redir-doble", base);
    expect(dos.ok).toBe(true);
    if (dos.ok) expect(dos.url).toBe("https://dcasapty.com/foto.jpg");
  });
});

describe("descargarSeguro: lo que NO (SSRF y abusos)", () => {
  it("no sigue una redirección a http", async () => {
    const r = await descargarSeguro("https://dcasapty.com/redir-a-http", base);
    expect(r).toMatchObject({ ok: false, estado: 422 });
    if (!r.ok) expect(r.motivo).toContain("redirección rechazada");
  });

  it("no sigue una redirección a los metadatos de la nube (IP interna)", async () => {
    visitas.length = 0;
    const r = await descargarSeguro("https://dcasapty.com/redir-a-metadatos", base);
    expect(r).toMatchObject({ ok: false, estado: 422 });
    // Tampoco llegó a pedirla: solo se visitó la primera URL.
    expect(visitas).toEqual(["/redir-a-metadatos"]);
  });

  it("no sigue una redirección a localhost", async () => {
    const r = await descargarSeguro("https://dcasapty.com/redir-a-localhost", base);
    expect(r).toMatchObject({ ok: false, estado: 422 });
  });

  it("con lista de dominios, tampoco sigue una redirección a otro dominio", async () => {
    const r = await descargarSeguro("https://dcasapty.com/redir-a-otro-dominio", { ...base, hostsPermitidos: ["dcasapty.com"] });
    expect(r).toMatchObject({ ok: false, estado: 422 });
    if (!r.ok) expect(r.motivo).toContain("lista de permitidos");
  });

  it("corta un bucle de redirecciones", async () => {
    visitas.length = 0;
    const r = await descargarSeguro("https://dcasapty.com/redir-sin-fin", base);
    expect(r).toMatchObject({ ok: false, estado: 422 });
    if (!r.ok) expect(r.motivo).toContain("demasiadas redirecciones");
    expect(visitas.length).toBe(REDIRECCIONES_MAX + 1);
  });

  it("rechaza la URL mala antes de tocar la red", async () => {
    visitas.length = 0;
    for (const u of ["http://dcasapty.com/foto.jpg", "https://127.0.0.1/foto.jpg", "https://u:p@dcasapty.com/foto.jpg", "https://localhost/foto.jpg"]) {
      const r = await descargarSeguro(u, base);
      expect(r).toMatchObject({ ok: false, estado: 422 });
    }
    expect(visitas).toEqual([]);
  });

  it("rechaza un archivo que declara ser enorme sin bajarlo", async () => {
    const r = await descargarSeguro("https://dcasapty.com/grande-declarado", base);
    expect(r).toMatchObject({ ok: false, estado: 422 });
    if (!r.ok) expect(r.motivo).toContain("pesa más");
  });

  it("corta en pleno chorro un archivo que no declara su tamaño", async () => {
    const r = await descargarSeguro("https://dcasapty.com/grande-chorro", base);
    expect(r).toMatchObject({ ok: false, estado: 422 });
    if (!r.ok) expect(r.motivo).toContain("pesa más");
  });

  it("rechaza un tipo que no es el pedido", async () => {
    const r = await descargarSeguro("https://dcasapty.com/html", base);
    expect(r).toMatchObject({ ok: false, estado: 422 });
    if (!r.ok) expect(r.motivo).toContain("text/html");
  });

  it("rechaza lo que dice ser imagen y es otra cosa (HTML con extensión .jpg)", async () => {
    const r = await descargarSeguro("https://dcasapty.com/mentira.jpg", base);
    expect(r).toMatchObject({ ok: false, estado: 422 });
    if (!r.ok) expect(r.motivo).toContain("no corresponde");
  });

  it("rechaza si el tipo declarado en la petición no coincide con el del origen", async () => {
    const r = await descargarSeguro("https://dcasapty.com/foto.jpg", { ...base, mimeDeclarado: "image/png" });
    expect(r).toMatchObject({ ok: false, estado: 422 });
  });

  it("rechaza un archivo vacío", async () => {
    const r = await descargarSeguro("https://dcasapty.com/vacio", base);
    expect(r).toMatchObject({ ok: false, estado: 422 });
  });

  it("errores del origen: 404 y 500", async () => {
    expect(await descargarSeguro("https://dcasapty.com/404", base)).toMatchObject({ ok: false, estado: 502 });
    expect(await descargarSeguro("https://dcasapty.com/500", base)).toMatchObject({ ok: false, estado: 502 });
  });

  it("un origen que no contesta no cuelga la respuesta: tiempo máximo", async () => {
    const t0 = Date.now();
    const r = await descargarSeguro("https://dcasapty.com/cuelga", { ...base, timeoutMs: 300 });
    expect(r).toMatchObject({ ok: false, estado: 504 });
    expect(Date.now() - t0).toBeLessThan(3000);
  });

  it("una conexión que falla se reporta sin filtrar detalles", async () => {
    const r = await descargarSeguro("https://dcasapty.com/foto.jpg", {
      ...base,
      deps: {
        request: ((_u: URL, _o: any, _cb: any) => {
          const req = http.request({ host: "127.0.0.1", port: 1, path: "/" });
          return req;
        }) as any,
      },
    });
    expect(r).toMatchObject({ ok: false, estado: 502 });
    if (!r.ok) expect(r.motivo).toContain("ECONNREFUSED");
  });
});

describe("crearLookupSeguro: el nombre se resuelve una vez y TODAS sus direcciones deben ser públicas", () => {
  const consulta = (lookup: ReturnType<typeof crearLookupSeguro>, host: string, opciones: any = {}) =>
    new Promise<{ error: any; direccion?: any; familia?: any }>((ok) => lookup(host, opciones, (error: any, direccion: any, familia: any) => ok({ error, direccion, familia })));

  it("deja pasar un nombre que resuelve a una dirección pública", async () => {
    const lookup = crearLookupSeguro(async () => [{ address: "104.16.1.1", family: 4 }]);
    expect(await consulta(lookup, "dcasapty.com")).toMatchObject({ error: null, direccion: "104.16.1.1", familia: 4 });
  });

  it("con {all:true} devuelve la lista (así lo pide Node con autoSelectFamily)", async () => {
    const lista = [
      { address: "104.16.1.1", family: 4 },
      { address: "2606:4700::1", family: 6 },
    ];
    const lookup = crearLookupSeguro(async () => lista);
    const r = await consulta(lookup, "dcasapty.com", { all: true });
    expect(r.error).toBe(null);
    expect(r.direccion).toEqual(lista);
  });

  it.each([
    ["127.0.0.1", "loopback"],
    ["10.1.2.3", "privada"],
    ["169.254.169.254", "metadatos de la nube"],
    ["192.168.0.5", "privada"],
    ["::1", "loopback IPv6"],
    ["fd00::1", "ULA"],
    ["::ffff:127.0.0.1", "IPv4 mapeada"],
  ])("rechaza un nombre que resuelve a %s (%s): DNS rebinding", async (address) => {
    const lookup = crearLookupSeguro(async () => [{ address, family: address.includes(":") ? 6 : 4 }]);
    const r = await consulta(lookup, "malo.example.org");
    expect(r.error?.code).toBe("ENOTPUBLIC");
  });

  it("si UNA de las direcciones es interna, rechaza todo el nombre", async () => {
    const lookup = crearLookupSeguro(async () => [
      { address: "104.16.1.1", family: 4 },
      { address: "10.0.0.7", family: 4 },
    ]);
    expect((await consulta(lookup, "mixto.example.org")).error?.code).toBe("ENOTPUBLIC");
  });

  it("un nombre que no resuelve es un error, no un permiso", async () => {
    const lookup = crearLookupSeguro(async () => []);
    expect((await consulta(lookup, "nada.example.org")).error?.code).toBe("ENOTFOUND");
    const falla = crearLookupSeguro(async () => {
      throw Object.assign(new Error("boom"), { code: "ESERVFAIL" });
    });
    expect((await consulta(falla, "x.example.org")).error?.code).toBe("ESERVFAIL");
  });

  it("Node de verdad usa nuestro lookup: una conexión a un nombre que resuelve a una IP interna ni se intenta", async () => {
    const lookup = crearLookupSeguro(async () => [{ address: "10.0.0.7", family: 4 }]);
    const intento = new Promise((ok, mal) => {
      const req = http.request({ host: "malo.example.org", port: 80, lookup: lookup as any }, ok);
      req.on("error", mal);
      req.end();
    });
    await expect(intento).rejects.toMatchObject({ code: "ENOTPUBLIC" });
  });

  it("descargarSeguro traduce el rechazo del lookup a un 422 claro", async () => {
    const r = await descargarSeguro("https://malo.example.org/foto.jpg", {
      ...base,
      deps: {
        resolver: async () => [{ address: "10.0.0.7", family: 4 }],
        // Hace lo mismo que https.request: conectar por el `lookup` que recibe.
        request: ((_url: URL, opciones: any, cb: any) =>
          http.request({ host: "malo.example.org", port: puerto, path: "/foto.jpg", lookup: opciones.lookup, method: "GET" }, cb)) as any,
      },
    });
    expect(r).toMatchObject({ ok: false, estado: 422 });
    if (!r.ok) expect(r.motivo).toContain("no pública");
  });
});
