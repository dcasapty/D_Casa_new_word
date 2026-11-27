/**
 * Enlaces de mapa en el texto de la clienta (docs/UBICACION.md, «Contrato…» §4): qué formatos dan un punto, cómo se siguen los cortos de
 * Google (a mano, solo a hosts de Google de la lista, como mucho 3 saltos y 5 s, sin leer el cuerpo) y qué queda en el texto (nunca las
 * coordenadas). Un enlace sin coordenadas no se adivina. También `prepararEntrante` y la copia de rescate (`crudoDe`).
 */
import { describe, expect, it } from "vitest";
import {
  coordenadasDeEnlace,
  decodificarGeohash,
  enlacesDeMapaEn,
  esEnlaceDeMapa,
  HOSTS_QUE_SE_SIGUEN,
  MAX_SALTOS,
  quitarCoordenadasDelTexto,
  resolverEnlaceCorto,
  ubicacionDelTexto,
} from "../../src/motor/enlacesMapa";
import { crudoDe, entranteDeCrudo, prepararEntrante } from "../../src/canales/preparar";
import { TEXTO_ENLACE_DE_MAPA, TEXTO_ENLACE_EN_EL_TEXTO, type UbicacionEntrante } from "../../src/canales/ubicacion";
import type { Entrante } from "../../src/canales/tipos";

const PUNTO = { lat: 9.0012345, lon: -79.5123456 };

/** Un geohash (para probar el de Waze con un punto conocido). */
function geohash(lat: number, lon: number, largo: number): string {
  const B = "0123456789bcdefghjkmnpqrstuvwxyz";
  const la = [-90, 90];
  const lo = [-180, 180];
  let salida = "";
  let bits = 0;
  let letra = 0;
  let esLon = true;
  while (salida.length < largo) {
    const r = esLon ? lo : la;
    const v = esLon ? lon : lat;
    const medio = (r[0] + r[1]) / 2;
    letra = (letra << 1) | (v >= medio ? 1 : 0);
    r[v >= medio ? 0 : 1] = medio;
    esLon = !esLon;
    if (++bits === 5) {
      salida += B[letra];
      bits = 0;
      letra = 0;
    }
  }
  return salida;
}

describe("los formatos que dan un punto (sin ir a la red)", () => {
  it.each([
    // Google: el pin del lugar gana al centro del mapa.
    ["https://www.google.com/maps/place/Super+99/@9.0100000,-79.5200000,17z/data=!3m1!4b1!4m6!3m5!1s0x8f:0x1!8m2!3d9.0012345!4d-79.5123456!16s%2Fg", PUNTO],
    ["https://maps.google.com/?q=9.0012345,-79.5123456", PUNTO],
    ["https://www.google.com/maps?q=9.0012345%2C-79.5123456", PUNTO],
    ["https://www.google.com/maps?q=loc:9.0012345,+-79.5123456", PUNTO],
    ["https://www.google.com/maps/search/?api=1&query=9.0012345,-79.5123456", PUNTO],
    ["https://maps.google.com/maps?ll=9.0012345,-79.5123456&z=16", PUNTO],
    ["https://www.google.com/maps/search/9.0012345,+-79.5123456?entry=tts", PUNTO],
    ["https://www.google.com/maps/place/9.0012345,-79.5123456", PUNTO],
    ["https://www.google.com/maps/@9.0012345,-79.5123456,15z", PUNTO],
    ["https://google.com/maps/@9.0012345,-79.5123456,15z", PUNTO],
    ["https://www.google.com.pa/maps/@9.0012345,-79.5123456,15z", PUNTO],
    // Waze y Apple.
    ["https://www.waze.com/ul?ll=9.0012345%2C-79.5123456&navigate=yes", PUNTO],
    ["https://ul.waze.com/ul?place=ChIJxyz&ll=9.00123450%2C-79.51234560&navigate=yes", PUNTO],
    ["https://maps.apple.com/?ll=9.0012345,-79.5123456&q=Casa", PUNTO],
    ["https://maps.apple.com/?q=9.0012345,-79.5123456", PUNTO],
    ["https://maps.apple.com/place?coordinate=9.0012345,-79.5123456&name=Casa", PUNTO],
  ])("%s", (url, esperado) => {
    expect(esEnlaceDeMapa(url)).toBe(true);
    expect(coordenadasDeEnlace(url)).toEqual(esperado);
  });

  it("el geohash de Waze (`waze.com/ul/h<geohash>`): de 8 letras o más, el centro de su celda", () => {
    const g = geohash(PUNTO.lat, PUNTO.lon, 10);
    const c = coordenadasDeEnlace(`https://waze.com/ul/h${g}`)!;
    expect(Math.abs(c.lat - PUNTO.lat)).toBeLessThan(0.00002);
    expect(Math.abs(c.lon - PUNTO.lon)).toBeLessThan(0.00002);
    expect(decodificarGeohash("d1v8")).not.toBe(null);
    expect(decodificarGeohash("dai")).toBe(null); // «a» e «i» no son del alfabeto
    // Muy corto (± kilómetros): no es un punto de entrega.
    expect(coordenadasDeEnlace(`https://waze.com/ul/h${g.slice(0, 7)}`)).toBe(null);
  });

  it.each([
    "https://www.google.com/maps/search/Super+99+Brisas",
    "https://maps.google.com/?q=Super+99",
    "https://www.google.com/maps/place/Super+99/data=!4m2!3m1!1s0x8f:0x1",
    "https://www.google.com/maps?q=1,2",
    "https://www.google.com/maps?q=9.1,-79.5",
    "https://www.google.com/maps?q=99.0012345,-79.5123456",
    "https://www.google.com/maps?q=9.0012345,-190.5123456",
    "https://www.waze.com/ul?q=Super%2099",
    "https://maps.apple.com/?q=Super%2099",
    "https://maps.app.goo.gl/AbCdEf123",
  ])("sin coordenadas escritas (o basura): null — %s", (url) => {
    expect(coordenadasDeEnlace(url)).toBe(null);
  });

  it.each([
    "https://www.google.com/search?q=9.0012345,-79.5123456",
    "https://evilgoogle.com/maps?q=9.0012345,-79.5123456",
    "https://google.com.evil.io/maps?q=9.0012345,-79.5123456",
    "https://ejemplo.com/maps?q=9.0012345,-79.5123456",
    "https://goo.gl/AbCdEf",
    "ftp://maps.google.com/?q=9.0012345,-79.5123456",
    "no es una url",
  ])("no es un enlace de mapa: %s", (url) => {
    expect(esEnlaceDeMapa(url)).toBe(false);
    expect(coordenadasDeEnlace(url)).toBe(null);
  });
});

// ── Los cortos de Google ──────────────────────────────────────────────────────

interface Pedido {
  url: string;
  init: RequestInit | undefined;
}

/** Un fetch de mentira: cada URL contesta lo que diga `rutas`; cuenta lo pedido y si alguien leyó el cuerpo. */
function redFalsa(rutas: Record<string, { estado: number; ubicacion?: string }>) {
  const pedidos: Pedido[] = [];
  let cuerposLeidos = 0;
  let cuerposCancelados = 0;
  const f: typeof fetch = async (recurso, init) => {
    const url = String(recurso);
    pedidos.push({ url, init });
    const r = rutas[url] ?? { estado: 404 };
    const cuerpo = new ReadableStream({
      pull(c) {
        cuerposLeidos++;
        c.enqueue(new TextEncoder().encode("<html>9.0012345,-79.5123456</html>"));
        c.close();
      },
      cancel() {
        cuerposCancelados++;
      },
    }, { highWaterMark: 0 });
    return new Response(r.estado === 204 || r.estado === 304 ? null : cuerpo, { status: r.estado, headers: r.ubicacion ? { location: r.ubicacion } : {} });
  };
  return { f, pedidos, leidos: () => cuerposLeidos, cancelados: () => cuerposCancelados };
}

const senal = () => new AbortController().signal;
const LUGAR = "https://www.google.com/maps/place/Super+99/data=!4m6!3m5!8m2!3d9.0012345!4d-79.5123456";

describe("los enlaces cortos de Google se siguen a mano", () => {
  it("un salto: GET con `redirect: manual`, se lee solo `Location` (el cuerpo no se lee) y el punto sale del destino", async () => {
    const red = redFalsa({ "https://maps.app.goo.gl/AbCdEf123": { estado: 302, ubicacion: LUGAR } });
    expect(await resolverEnlaceCorto("https://maps.app.goo.gl/AbCdEf123", red.f, senal())).toEqual(PUNTO);
    expect(red.pedidos).toHaveLength(1);
    expect(red.pedidos[0].init).toMatchObject({ method: "GET", redirect: "manual" });
    expect(red.pedidos[0].init?.signal).toBeInstanceOf(AbortSignal);
    expect(red.leidos()).toBe(0);
    // El cuerpo se suelta sin leerlo (no queda una conexión abierta esperando).
    expect(red.cancelados()).toBe(1);
  });

  it("varios saltos entre hosts de Google, mientras el destino no traiga el punto escrito", async () => {
    const red = redFalsa({
      "https://goo.gl/maps/Xyz123": { estado: 301, ubicacion: "https://maps.google.com/?q=Super+99&ftid=0x8f:0x1" },
      "https://maps.google.com/?q=Super+99&ftid=0x8f:0x1": { estado: 302, ubicacion: LUGAR },
    });
    expect(await resolverEnlaceCorto("https://goo.gl/maps/Xyz123", red.f, senal())).toEqual(PUNTO);
    expect(red.pedidos.map((p) => p.url)).toEqual(["https://goo.gl/maps/Xyz123", "https://maps.google.com/?q=Super+99&ftid=0x8f:0x1"]);
    expect(red.leidos()).toBe(0);
  });

  it("un destino relativo se resuelve contra el host actual", async () => {
    const red = redFalsa({ "https://maps.app.goo.gl/R": { estado: 302, ubicacion: "/maps/place/X/data=!3d9.0012345!4d-79.5123456" } });
    // `/maps/…` en maps.app.goo.gl no es Google Maps: se sigue (está en la lista) y, como no hay más ruta, null.
    expect(await resolverEnlaceCorto("https://maps.app.goo.gl/R", red.f, senal())).toBe(null);
    const red2 = redFalsa({
      "https://maps.app.goo.gl/R": { estado: 302, ubicacion: "https://www.google.com/x" },
      "https://www.google.com/x": { estado: 302, ubicacion: "/maps/place/X/data=!3d9.0012345!4d-79.5123456" },
    });
    expect(await resolverEnlaceCorto("https://maps.app.goo.gl/R", red2.f, senal())).toEqual(PUNTO);
  });

  it("como mucho 3 saltos: una cadena sin fin se corta y no hay punto", async () => {
    const rutas: Record<string, { estado: number; ubicacion: string }> = {};
    for (let i = 0; i < 10; i++) rutas[i === 0 ? "https://maps.app.goo.gl/Loop" : `https://www.google.com/r${i}`] = { estado: 302, ubicacion: `https://www.google.com/r${i + 1}` };
    const red = redFalsa(rutas);
    expect(await resolverEnlaceCorto("https://maps.app.goo.gl/Loop", red.f, senal())).toBe(null);
    expect(red.pedidos).toHaveLength(MAX_SALTOS);
  });

  it.each([
    ["un host que no es de la lista", "https://evil.example/maps?x=1"],
    ["el consentimiento de Google (no está en la lista)", "https://consent.google.com/m?continue=https://www.google.com/maps"],
    ["otro país de Google sin el punto escrito", "https://www.google.com.pa/maps?q=Super"],
    ["http en vez de https", "http://www.google.com/maps?q=Super"],
    ["con usuario", "https://alguien@www.google.com/maps?q=Super"],
    ["con puerto", "https://www.google.com:8443/maps?q=Super"],
    ["una dirección interna", "https://169.254.169.254/latest/meta-data/"],
  ])("NO se sigue %s", async (_nombre, destino) => {
    const red = redFalsa({ "https://maps.app.goo.gl/AbC": { estado: 302, ubicacion: destino } });
    expect(await resolverEnlaceCorto("https://maps.app.goo.gl/AbC", red.f, senal())).toBe(null);
    expect(red.pedidos.map((p) => p.url)).toEqual(["https://maps.app.goo.gl/AbC"]);
  });

  it("un destino fuera de la lista que YA trae el punto escrito sirve sin pedirlo", async () => {
    const red = redFalsa({ "https://maps.app.goo.gl/AbC": { estado: 302, ubicacion: "https://www.google.com.pa/maps/@9.0012345,-79.5123456,17z" } });
    expect(await resolverEnlaceCorto("https://maps.app.goo.gl/AbC", red.f, senal())).toEqual(PUNTO);
    expect(red.pedidos).toHaveLength(1);
  });

  it("solo se empieza por un corto de Google: nada más se pide a la red", async () => {
    const red = redFalsa({});
    for (const url of ["https://goo.gl/AbCdEf", "https://ejemplo.com/x", "https://www.google.com/maps/search/Super", "https://user@maps.app.goo.gl/x", "https://maps.app.goo.gl:444/x"]) {
      expect(await resolverEnlaceCorto(url, red.f, senal()), url).toBe(null);
    }
    expect(red.pedidos).toEqual([]);
    expect([...HOSTS_QUE_SE_SIGUEN].sort()).toEqual(["goo.gl", "google.com", "maps.app.goo.gl", "maps.google.com", "www.google.com"]);
  });

  it("una respuesta sin redirección (200, 404) o sin `Location`: null", async () => {
    for (const r of [{ estado: 200 }, { estado: 404 }, { estado: 302 }, { estado: 500 }]) {
      const red = redFalsa({ "https://maps.app.goo.gl/AbC": r });
      expect(await resolverEnlaceCorto("https://maps.app.goo.gl/AbC", red.f, senal()), JSON.stringify(r)).toBe(null);
      expect(red.leidos()).toBe(0);
    }
  });

  it("si la red falla o se pasa del plazo (5 s para todo el mensaje), no hay punto y nunca lanza", async () => {
    const cuelga: typeof fetch = (_u, init) =>
      new Promise((_r, rechazar) => init?.signal?.addEventListener("abort", () => rechazar(new DOMException("plazo", "AbortError"))));
    const inicio = Date.now();
    const r = await ubicacionDelTexto("https://maps.app.goo.gl/AbC", { fetch: cuelga, plazoMs: 30 });
    expect(r).toEqual({ texto: "https://maps.app.goo.gl/AbC", coordenadas: null });
    expect(Date.now() - inicio).toBeLessThan(2000);
    const rota: typeof fetch = async () => {
      throw new TypeError("red caída");
    };
    expect(await ubicacionDelTexto("https://maps.app.goo.gl/AbC", { fetch: rota })).toEqual({ texto: "https://maps.app.goo.gl/AbC", coordenadas: null });
  });
});

// ── El texto ──────────────────────────────────────────────────────────────────

describe("el texto que queda (lo que se guarda y lo que ve el modelo)", () => {
  const sinRed: typeof fetch = async () => {
    throw new Error("no debía ir a la red");
  };

  it("si el mensaje es solo el enlace, queda la frase entera", async () => {
    for (const t of ["https://maps.google.com/?q=9.0012345,-79.5123456", "  maps.google.com/?q=9.0012345,-79.5123456 ", "(https://maps.google.com/?q=9.0012345,-79.5123456)", "<https://maps.google.com/?q=9.0012345,-79.5123456>."]) {
      expect(await ubicacionDelTexto(t, { fetch: sinRed }), t).toEqual({ texto: TEXTO_ENLACE_DE_MAPA, coordenadas: PUNTO });
    }
  });

  it("auditoría 1: un cuarto enlace con el punto escrito también se tapa (antes llegaba al modelo)", async () => {
    const e = (n: number) => `https://maps.google.com/?q=9.00${n}2345,-79.5123456`;
    const r = await ubicacionDelTexto(`a ${e(1)} b ${e(2)} c ${e(3)} d ${e(4)} e ${e(5)}`, { fetch: sinRed });
    expect(r.texto).not.toMatch(/\d\.\d{3,}/);
    expect(r.coordenadas).toEqual({ lat: 9.0012345, lon: -79.5123456 });
    expect(quitarCoordenadasDelTexto(`x ${e(1)} ${e(2)} ${e(3)} ${e(4)}`).texto).not.toMatch(/\d\.\d{3,}/);
  });

  it("auditoría 2: con nombre, con hemisferio, en grados-minutos-segundos y los códigos Plus también se tapan", async () => {
    for (const t of [
      "lat 9.0012345 lon -79.5123456",
      "latitud: 9.0012345, longitud: -79.5123456",
      "9.0012345° N, 79.5123456° W",
      "9°00'04.4\"N 79°30'44.4\"W",
    ]) {
      const r = await ubicacionDelTexto(`mi casa: ${t} gracias`, { fetch: sinRed });
      expect(r.texto, t).not.toMatch(/9[.°]0|79[.°]/);
      expect(r.coordenadas, t).not.toBeNull();
      expect(Math.abs((r.coordenadas?.lat ?? 0) - 9.0012), t).toBeLessThan(0.001);
      expect(Math.abs((r.coordenadas?.lon ?? 0) + 79.5123), t).toBeLessThan(0.001);
    }
    const plus = await ubicacionDelTexto("es aquí 7Q2F+3X La Chorrera", { fetch: sinRed });
    expect(plus.texto).not.toContain("7Q2F+3X");
    expect(plus.coordenadas).toBeNull();
  });

  it("auditoría 1: las coordenadas escritas a mano en Panamá se tapan y son el punto; un precio no", async () => {
    for (const t of ["mi casa es 9.0012345, -79.5123456 la verde", "9.0012345,-79.5123456"]) {
      const r = await ubicacionDelTexto(t, { fetch: sinRed });
      expect(r.coordenadas, t).toEqual(PUNTO);
      expect(r.texto, t).not.toMatch(/9\.0012|79\.5123/);
      expect(quitarCoordenadasDelTexto(t).texto, t).not.toMatch(/9\.0012|79\.5123/);
    }
    const precio = "son 15.000, 20.500 y 1.250";
    expect(await ubicacionDelTexto(precio, { fetch: sinRed })).toEqual({ texto: precio, coordenadas: null });
  });

  it("dentro de una frase, solo el enlace se cambia; ninguna coordenada queda", async () => {
    const r = await ubicacionDelTexto("Es aquí https://maps.google.com/?q=9.0012345,-79.5123456, la casa verde", { fetch: sinRed });
    expect(r).toEqual({ texto: `Es aquí ${TEXTO_ENLACE_EN_EL_TEXTO}, la casa verde`, coordenadas: PUNTO });
  });

  it("lo que comparte Google Maps (nombre, dirección y el enlace corto): queda el nombre y la dirección, sin el enlace", async () => {
    const red = redFalsa({ "https://maps.app.goo.gl/AbCdEf123": { estado: 302, ubicacion: LUGAR } });
    const r = await ubicacionDelTexto("Super 99 Brisas\nVía Domingo Díaz, Panamá\nhttps://maps.app.goo.gl/AbCdEf123", { fetch: red.f });
    expect(r).toEqual({ texto: `Super 99 Brisas\nVía Domingo Díaz, Panamá\n${TEXTO_ENLACE_EN_EL_TEXTO}`, coordenadas: PUNTO });
  });

  it("un corto que no da el punto queda en el texto tal cual (no trae coordenadas)", async () => {
    const red = redFalsa({ "https://maps.app.goo.gl/Nada": { estado: 200 } });
    expect(await ubicacionDelTexto("aquí: https://maps.app.goo.gl/Nada", { fetch: red.f })).toEqual({ texto: "aquí: https://maps.app.goo.gl/Nada", coordenadas: null });
  });

  it("varios enlaces con punto: vale el primero y todos se cambian", async () => {
    const r = await ubicacionDelTexto("o https://maps.google.com/?q=9.0012345,-79.5123456 o https://www.waze.com/ul?ll=8.8801000,-79.7834000", { fetch: sinRed });
    expect(r.coordenadas).toEqual(PUNTO);
    expect(r.texto).toBe(`o ${TEXTO_ENLACE_EN_EL_TEXTO} o ${TEXTO_ENLACE_EN_EL_TEXTO}`);
  });

  it("un texto sin enlaces de mapa ni coordenadas sueltas no se toca (ni se va a la red)", async () => {
    for (const t of ["hola", "https://ejemplo.com/maps?q=9.0012345,-79.5123456"]) {
      expect(await ubicacionDelTexto(t, { fetch: sinRed }), t).toEqual({ texto: t, coordenadas: null });
    }
  });

  it("se miran todos los enlaces del mensaje, pero solo 3 cortos se siguen por la red", async () => {
    const t = Array.from({ length: 5 }, (_, i) => `https://maps.google.com/?q=9.00${i}2345,-79.5123456`).join(" ");
    expect(enlacesDeMapaEn(t)).toHaveLength(5);
    const pedidos: string[] = [];
    const red: typeof fetch = async (u) => {
      pedidos.push(String(u));
      return new Response(null, { status: 404 });
    };
    await ubicacionDelTexto(Array.from({ length: 5 }, (_, i) => `https://maps.app.goo.gl/Abc${i}`).join(" "), { fetch: red });
    expect(pedidos).toHaveLength(3);
  });

  it("sin red (la copia de rescate): quita los que traen el punto escrito; los cortos quedan", () => {
    expect(quitarCoordenadasDelTexto("aquí https://maps.google.com/?q=9.0012345,-79.5123456 y https://maps.app.goo.gl/AbC")).toEqual({
      texto: `aquí ${TEXTO_ENLACE_EN_EL_TEXTO} y https://maps.app.goo.gl/AbC`,
      coordenadas: PUNTO,
    });
    expect(quitarCoordenadasDelTexto("https://maps.app.goo.gl/AbC")).toEqual({ texto: "https://maps.app.goo.gl/AbC", coordenadas: null });
  });
});

// ── preparar.ts ───────────────────────────────────────────────────────────────

const base = (extra: Partial<Entrante> = {}): Entrante => ({ canal: "instagram", id_externo: "IG1", id_mensaje: "m1", texto: "hola", adjuntos: [], ts: 1, ...extra });
const ENLACE = "https://maps.google.com/?q=9.0012345,-79.5123456";

describe("prepararEntrante: el enlace de la clienta se vuelve su ubicación", () => {
  it("con un enlace con coordenadas: `ubicacion` con origen «enlace» y el texto sin coordenadas", async () => {
    const e = await prepararEntrante(base({ texto: ENLACE }));
    expect(e.ubicacion).toEqual({ ...PUNTO, origen: "enlace" });
    expect(e.texto).toBe(TEXTO_ENLACE_DE_MAPA);
  });

  it("los cortos se siguen con el `fetch` que se le pasa", async () => {
    const red = redFalsa({ "https://maps.app.goo.gl/AbC": { estado: 302, ubicacion: LUGAR } });
    const e = await prepararEntrante(base({ texto: "https://maps.app.goo.gl/AbC" }), { fetch: red.f });
    expect(e.ubicacion).toEqual({ ...PUNTO, origen: "enlace" });
  });

  it("si el canal ya trajo la ubicación, manda esa; el enlace igual sale del texto", async () => {
    const delCanal: UbicacionEntrante = { lat: 8.8801, lon: -79.7834, origen: "whatsapp" };
    const e = await prepararEntrante(base({ texto: `y también ${ENLACE}`, ubicacion: delCanal }));
    expect(e.ubicacion).toEqual(delCanal);
    expect(e.texto).toBe(`y también ${TEXTO_ENLACE_EN_EL_TEXTO}`);
  });

  it("lo que escribe la tienda y los comentarios públicos no se tocan", async () => {
    const propio = await prepararEntrante(base({ texto: ENLACE, propio: true }));
    expect(propio.texto).toBe(ENLACE);
    expect(propio).not.toHaveProperty("ubicacion");
    const comentario = await prepararEntrante(base({ texto: ENLACE, comentario: { red: "instagram", puerta: "pagina", id: "c1" } }));
    expect(comentario.texto).toBe(ENLACE);
    expect(comentario).not.toHaveProperty("ubicacion");
  });

  it("un mensaje rescatado con `ubicacion_omitida` no gana un punto nuevo, pero el texto igual se limpia", async () => {
    const e = await prepararEntrante(base({ texto: ENLACE, ubicacion_omitida: "whatsapp" }));
    expect(e).not.toHaveProperty("ubicacion");
    expect(e.texto).toBe(TEXTO_ENLACE_DE_MAPA);
  });
});

describe("crudoDe: la copia de rescate nunca guarda un punto", () => {
  it("la ubicación del canal queda como `ubicacion_omitida`", () => {
    const c = crudoDe(base({ texto: "(la clienta compartió su ubicación de entrega)", ubicacion: { ...PUNTO, origen: "whatsapp", nombre_lugar: "Casa" } }));
    expect(c).not.toHaveProperty("ubicacion");
    expect(c.ubicacion_omitida).toBe("whatsapp");
    expect(JSON.stringify(c)).not.toMatch(/9\.0012|79\.5123|Casa/);
  });

  it("un enlace con el punto escrito se cambia por la frase (y queda `ubicacion_omitida`); uno corto queda, el rescate lo sigue", () => {
    const c = crudoDe(base({ texto: `aquí ${ENLACE}` }));
    expect(c.texto).toBe(`aquí ${TEXTO_ENLACE_EN_EL_TEXTO}`);
    expect(c.ubicacion_omitida).toBe("enlace");
    expect(JSON.stringify(c)).not.toMatch(/9\.0012|79\.5123/);
    const corto = crudoDe(base({ texto: "https://maps.app.goo.gl/AbC" }));
    expect(corto.texto).toBe("https://maps.app.goo.gl/AbC");
    expect(corto).not.toHaveProperty("ubicacion_omitida");
    expect(entranteDeCrudo(c)).toMatchObject({ ubicacion_omitida: "enlace" });
  });

  it("lo que escribe la tienda se guarda tal cual", () => {
    const c = crudoDe(base({ texto: ENLACE, propio: true }));
    expect(c.texto).toBe(ENLACE);
    expect(c).not.toHaveProperty("ubicacion_omitida");
  });
});
