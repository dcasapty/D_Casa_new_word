import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { handleRequest, variablesDelContenedor } from "../src/handler";
import {
  aBase64Url,
  abrirPuerta,
  cabeceraDeModo,
  cabeceraParaOdoo,
  type ConfigPuerta,
  configPuerta,
  crearCookie,
  depsPuerta,
  esEntrada,
  esLoginPublicoDelPanel,
  esPanel,
  leerCookie,
  NOMBRE_COOKIE,
  reiniciarCacheJwks,
  sinCookieDePuerta,
  verificarJwtAccess,
} from "../src/puerta";

const EQUIPO = "https://dcasa.cloudflareaccess.com";
const AUD = "a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90";
const SECRETO = "s".repeat(40);
const RUTA = "/entrada-k7q2m9x4";
const AHORA = Date.UTC(2026, 9, 10, 15, 0, 0); // 2026-10-10 15:00 UTC
const AHORA_S = Math.floor(AHORA / 1000);

const ENV_VALIDO = {
  DCASA_PUERTA_RUTA: RUTA,
  DCASA_PUERTA_SECRETO: SECRETO,
  DCASA_ACCESS_EQUIPO: EQUIPO,
  DCASA_ACCESS_AUD: AUD,
};

const cfg: ConfigPuerta = { ruta: RUTA, secreto: SECRETO, equipo: EQUIPO, aud: AUD, horas: 12 };

// ------------------------------------------------------------------ llaves RSA de prueba (como las de Access)

interface Par {
  privada: CryptoKey;
  jwk: JsonWebKey & { kid: string };
}

async function generarPar(kid: string): Promise<Par> {
  const par = (await crypto.subtle.generateKey(
    { name: "RSASSA-PKCS1-v1_5", modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: "SHA-256" },
    true,
    ["sign", "verify"],
  )) as CryptoKeyPair;
  const publica = (await crypto.subtle.exportKey("jwk", par.publicKey)) as JsonWebKey;
  return { privada: par.privateKey, jwk: { ...publica, kid, alg: "RS256", use: "sig" } };
}

const enc = new TextEncoder();
const b64json = (valor: unknown) => aBase64Url(enc.encode(JSON.stringify(valor)));

async function firmar(par: Par, carga: Record<string, unknown>, cabecera: Record<string, unknown> = {}): Promise<string> {
  const h = b64json({ alg: "RS256", kid: par.jwk.kid, typ: "JWT", ...cabecera });
  const p = b64json(carga);
  const firma = new Uint8Array(await crypto.subtle.sign("RSASSA-PKCS1-v1_5", par.privada, enc.encode(`${h}.${p}`)));
  return `${h}.${p}.${aBase64Url(firma)}`;
}

const cargaBuena = (extra: Record<string, unknown> = {}) => ({
  iss: EQUIPO,
  aud: [AUD],
  email: "Duena@Example.com",
  iat: AHORA_S - 60,
  nbf: AHORA_S - 60,
  exp: AHORA_S + 3600,
  type: "app",
  ...extra,
});

let par: Par;
let otroPar: Par;

beforeAll(async () => {
  par = await generarPar("llave-1");
  otroPar = await generarPar("llave-1"); // mismo kid, otra llave: una firma ajena
});

let jwksLlamadas = 0;
const deps = (pares: Par[] = [par]) => ({
  ahora: () => AHORA,
  fetchJwks: async () => {
    jwksLlamadas += 1;
    return { keys: pares.map((p) => p.jwk) };
  },
});

beforeEach(() => {
  reiniciarCacheJwks();
  jwksLlamadas = 0;
  vi.spyOn(console, "warn").mockImplementation(() => undefined);
  vi.spyOn(console, "log").mockImplementation(() => undefined);
  vi.spyOn(console, "error").mockImplementation(() => undefined);
});

afterEach(() => vi.restoreAllMocks());

// ------------------------------------------------------------------ configuración

describe("configPuerta", () => {
  it("sin ninguna variable está apagada, sin ruido", () => {
    expect(configPuerta({})).toBeNull();
    expect(console.warn).not.toHaveBeenCalled();
  });

  it("/master es una ruta válida para la entrada", () => {
    expect(configPuerta({ ...ENV_VALIDO, DCASA_PUERTA_RUTA: "/master" })?.ruta).toBe("/master");
    expect(configPuerta({ ...ENV_VALIDO, DCASA_PUERTA_RUTA: "Master" })?.ruta).toBe("/master");
  });

  it("con las cuatro variables válidas queda encendida (ruta en minúsculas, equipo sin barra final)", () => {
    const config = configPuerta({ ...ENV_VALIDO, DCASA_PUERTA_RUTA: "Entrada-K7Q2M9X4", DCASA_ACCESS_EQUIPO: `${EQUIPO}/` });
    expect(config).toEqual({ ruta: RUTA, secreto: SECRETO, equipo: EQUIPO, aud: AUD, horas: 12 });
  });

  it.each([
    ["falta la ruta", { DCASA_PUERTA_RUTA: undefined }],
    ["falta el secreto", { DCASA_PUERTA_SECRETO: undefined }],
    ["falta el equipo", { DCASA_ACCESS_EQUIPO: undefined }],
    ["falta la audiencia", { DCASA_ACCESS_AUD: undefined }],
    ["secreto corto", { DCASA_PUERTA_SECRETO: "corto" }],
    ["ruta demasiado corta", { DCASA_PUERTA_RUTA: "/ab" }],
    ["ruta que ya es del sitio (el panel)", { DCASA_PUERTA_RUTA: "/odoo" }],
    ["ruta que ya es del sitio (la tienda)", { DCASA_PUERTA_RUTA: "/shop" }],
    ["ruta que ya es del sitio (el login)", { DCASA_PUERTA_RUTA: "/web" }],
    ["ruta con barras", { DCASA_PUERTA_RUTA: "/web/login-largo" }],
    ["ruta con caracteres raros", { DCASA_PUERTA_RUTA: "/entrada_k7q2m9x4" }],
    ["equipo que no es de Cloudflare Access", { DCASA_ACCESS_EQUIPO: "https://evil.example.com" }],
    ["equipo sin https", { DCASA_ACCESS_EQUIPO: "http://dcasa.cloudflareaccess.com" }],
    ["equipo con ruta", { DCASA_ACCESS_EQUIPO: `${EQUIPO}/cdn-cgi` }],
    ["audiencia ilegible", { DCASA_ACCESS_AUD: "corta" }],
  ])("%s: la puerta queda APAGADA y se avisa en los logs", (_nombre, cambio) => {
    expect(configPuerta({ ...ENV_VALIDO, ...cambio })).toBeNull();
    expect(console.warn).toHaveBeenCalledWith(expect.stringContaining("puerta_incompleta"));
  });

  it("el aviso de configuración incompleta sale una sola vez, no en cada petición", () => {
    const rota = { ...ENV_VALIDO, DCASA_PUERTA_SECRETO: "distinto-y-corto" };
    for (let i = 0; i < 5; i++) configPuerta(rota);
    expect(console.warn).toHaveBeenCalledTimes(1);
  });

  it("las horas se limitan a 1–24 y por defecto son 12", () => {
    expect(configPuerta({ ...ENV_VALIDO, DCASA_PUERTA_HORAS: "6" })?.horas).toBe(6);
    expect(configPuerta({ ...ENV_VALIDO, DCASA_PUERTA_HORAS: "999" })?.horas).toBe(24);
    expect(configPuerta({ ...ENV_VALIDO, DCASA_PUERTA_HORAS: "0" })?.horas).toBe(12);
    expect(configPuerta({ ...ENV_VALIDO, DCASA_PUERTA_HORAS: "mucho" })?.horas).toBe(12);
  });
});

describe("el interruptor", () => {
  it("depsPuerta: apagada sin variables; el modo sale de la variable y lo raro es «0»", () => {
    expect(depsPuerta({})).toBeUndefined();
    expect(depsPuerta({ ...ENV_VALIDO })).toMatchObject({ modo: "0", exigirCorreo: false });
    expect(depsPuerta({ ...ENV_VALIDO, DCASA_PUERTA_OBLIGATORIA: "0" })?.modo).toBe("0");
    expect(depsPuerta({ ...ENV_VALIDO, DCASA_PUERTA_OBLIGATORIA: "avisar" })?.modo).toBe("avisar");
    expect(depsPuerta({ ...ENV_VALIDO, DCASA_PUERTA_OBLIGATORIA: " 1 " })?.modo).toBe("1");
    expect(depsPuerta({ ...ENV_VALIDO, DCASA_PUERTA_OBLIGATORIA: "si" })?.modo).toBe("0");
    expect(depsPuerta({ ...ENV_VALIDO, DCASA_PUERTA_EXIGIR_CORREO: "1" })?.exigirCorreo).toBe(true);
    // Sin las cuatro variables no hay puerta aunque el interruptor diga «1».
    expect(depsPuerta({ DCASA_PUERTA_OBLIGATORIA: "1" })).toBeUndefined();
  });

  it("al contenedor solo viaja el secreto: ni el modo ni la ruta ni los datos de Access", () => {
    const vars = variablesDelContenedor({
      ...ENV_VALIDO, DCASA_PUERTA_OBLIGATORIA: "1", DCASA_PUERTA_EXIGIR_CORREO: "1", DCASA_PUERTA_HORAS: "6",
    });
    expect(vars.DCASA_PUERTA_SECRETO).toBe(SECRETO);
    for (const solo_del_worker of [
      "DCASA_PUERTA_OBLIGATORIA", "DCASA_PUERTA_EXIGIR_CORREO", "DCASA_PUERTA_RUTA",
      "DCASA_ACCESS_EQUIPO", "DCASA_ACCESS_AUD", "DCASA_PUERTA_HORAS",
    ]) {
      expect(vars).not.toHaveProperty(solo_del_worker);
    }
  });

  it("la cabecera del modo lleva modo, amarre, vencimiento corto y una firma propia", async () => {
    const cabecera = await cabeceraDeModo(cfg, "1", true, AHORA);
    const [modo, exigir, vence, firma] = cabecera.split("|");
    expect([modo, exigir, vence]).toEqual(["1", "1", String(AHORA_S + 300)]);
    expect(firma).toMatch(/^[0-9a-f]{64}$/);
    const otra = await cabeceraDeModo(cfg, "avisar", true, AHORA);
    expect(otra.split("|")[3]).not.toBe(firma);
    const otroSecreto = await cabeceraDeModo({ secreto: "z".repeat(40) }, "1", true, AHORA);
    expect(otroSecreto.split("|")[3]).not.toBe(firma);
  });
});

// ------------------------------------------------------------------ token de Access

describe("verificarJwtAccess", () => {
  it("acepta un token bien firmado, con el correo en minúsculas", async () => {
    const token = await firmar(par, cargaBuena());
    expect(await verificarJwtAccess(token, cfg, deps())).toEqual({ email: "duena@example.com", exp: AHORA_S + 3600 });
  });

  it("acepta la audiencia como texto suelto", async () => {
    const token = await firmar(par, cargaBuena({ aud: AUD }));
    expect(await verificarJwtAccess(token, cfg, deps())).not.toBeNull();
  });

  it.each([
    ["audiencia de otra aplicación", { aud: ["otra-aplicacion-0123456789abcdef"] }],
    ["emisor de otro equipo", { iss: "https://otro.cloudflareaccess.com" }],
    ["vencido", { exp: AHORA_S - 600 }],
    ["todavía no vale", { nbf: AHORA_S + 600 }],
    ["emitido en el futuro", { iat: AHORA_S + 600 }],
    ["sin correo (un service token)", { email: undefined, common_name: "abc.access" }],
    ["correo con barra vertical (rompería la cabecera)", { email: "a|b@example.com" }],
    ["correo sin arroba", { email: "duena" }],
    ["sin vencimiento", { exp: undefined }],
  ])("rechaza: %s", async (_nombre, cambio) => {
    const token = await firmar(par, cargaBuena(cambio));
    expect(await verificarJwtAccess(token, cfg, deps())).toBeNull();
  });

  it("rechaza una firma de otra llave aunque el contenido sea perfecto", async () => {
    const token = await firmar(otroPar, cargaBuena());
    expect(await verificarJwtAccess(token, cfg, deps([par]))).toBeNull();
  });

  it("rechaza un contenido alterado después de firmar", async () => {
    const token = await firmar(par, cargaBuena({ email: "peon@example.com" }));
    const [h, , f] = token.split(".");
    const alterado = `${h}.${b64json(cargaBuena({ email: "jefa@example.com" }))}.${f}`;
    expect(await verificarJwtAccess(alterado, cfg, deps())).toBeNull();
  });

  it("rechaza algoritmos que no sean RS256 (none y HS256)", async () => {
    const sinFirma = `${b64json({ alg: "none", kid: "llave-1" })}.${b64json(cargaBuena())}.`;
    expect(await verificarJwtAccess(sinFirma, cfg, deps())).toBeNull();
    const confundido = `${b64json({ alg: "HS256", kid: "llave-1" })}.${b64json(cargaBuena())}.${aBase64Url(enc.encode("x"))}`;
    expect(await verificarJwtAccess(confundido, cfg, deps())).toBeNull();
    const rsa = await firmar(par, cargaBuena(), { alg: "PS256" });
    expect(await verificarJwtAccess(rsa, cfg, deps())).toBeNull();
  });

  it("rechaza basura, vacío, sin kid y kid desconocido", async () => {
    for (const malo of [null, "", "a.b", "a.b.c", "....", "no es un token"]) {
      expect(await verificarJwtAccess(malo, cfg, deps())).toBeNull();
    }
    const sinKid = await firmar(par, cargaBuena(), { kid: undefined });
    expect(await verificarJwtAccess(sinKid, cfg, deps())).toBeNull();
    const desconocido = await firmar(par, cargaBuena(), { kid: "otra" });
    expect(await verificarJwtAccess(desconocido, cfg, deps())).toBeNull();
  });

  it("si Cloudflare no entrega las llaves, falla cerrado", async () => {
    const token = await firmar(par, cargaBuena());
    const caido = { ahora: () => AHORA, fetchJwks: async () => { throw new Error("HTTP 503"); } };
    expect(await verificarJwtAccess(token, cfg, caido)).toBeNull();
    const roto = { ahora: () => AHORA, fetchJwks: async () => ({ cosa: 1 }) };
    reiniciarCacheJwks();
    expect(await verificarJwtAccess(token, cfg, roto)).toBeNull();
  });

  it("varias visitas a la vez comparten una sola descarga de llaves", async () => {
    const token = await firmar(par, cargaBuena());
    const resultados = await Promise.all(Array.from({ length: 8 }, () => verificarJwtAccess(token, cfg, deps())));
    expect(resultados.every((r) => r !== null)).toBe(true);
    expect(jwksLlamadas).toBe(1);
  });

  it("si Cloudflare falla, no se insiste en cada visita: se espera unos segundos", async () => {
    const token = await firmar(par, cargaBuena());
    let intentos = 0;
    const caido = { ahora: () => AHORA, fetchJwks: async () => { intentos += 1; throw new Error("HTTP 503"); } };
    for (let i = 0; i < 6; i++) expect(await verificarJwtAccess(token, cfg, caido)).toBeNull();
    expect(intentos).toBe(1);
    // Pasados los segundos de pausa se vuelve a intentar.
    const luego = { ...caido, ahora: () => AHORA + 15_000 };
    await verificarJwtAccess(token, cfg, luego);
    expect(intentos).toBe(2);
  });

  it("guarda las llaves una hora y no las pide en cada visita", async () => {
    const token = await firmar(par, cargaBuena());
    await verificarJwtAccess(token, cfg, deps());
    await verificarJwtAccess(token, cfg, deps());
    await verificarJwtAccess(token, cfg, deps());
    expect(jwksLlamadas).toBe(1);
  });

  it("si Access rota sus llaves, vuelve a pedirlas (una vez por minuto como mucho)", async () => {
    const nueva = await generarPar("llave-2");
    const viejo = await firmar(par, cargaBuena());
    await verificarJwtAccess(viejo, cfg, deps([par]));
    const conLlaveNueva = await firmar(nueva, cargaBuena());
    // Dentro del minuto: no se vuelve a pedir; todavía no la conoce.
    expect(await verificarJwtAccess(conLlaveNueva, cfg, deps([par, nueva]))).toBeNull();
    expect(jwksLlamadas).toBe(1);
    // Pasado el minuto: se pide de nuevo y la reconoce.
    const luego = { ...deps([par, nueva]), ahora: () => AHORA + 90_000 };
    const tokenLuego = await firmar(nueva, cargaBuena({ iat: AHORA_S + 60, nbf: AHORA_S + 60, exp: AHORA_S + 7200 }));
    expect(await verificarJwtAccess(tokenLuego, cfg, luego)).not.toBeNull();
    expect(jwksLlamadas).toBe(2);
  });
});

// ------------------------------------------------------------------ cookie propia

describe("cookie de la puerta", () => {
  const identidad = { email: "duena@example.com", exp: AHORA_S + 24 * 3600 };

  async function conCookie(valor: string, extra = ""): Promise<Request> {
    return new Request("https://dcasapty.com/odoo", { headers: { Cookie: `${extra}${NOMBRE_COOKIE}=${valor}` } });
  }

  it("se crea para el tiempo configurado y se lee de vuelta", async () => {
    const cookie = await crearCookie(cfg, identidad, AHORA);
    expect(cookie.maxAge).toBe(12 * 3600);
    expect(await leerCookie(await conCookie(cookie.valor, "session_id=abc; "), cfg, AHORA)).toEqual({
      email: "duena@example.com",
      exp: AHORA_S + 12 * 3600,
    });
  });

  it("nunca dura más que la sesión de Access", async () => {
    const corta = await crearCookie(cfg, { ...identidad, exp: AHORA_S + 600 }, AHORA);
    expect(corta.maxAge).toBe(600);
  });

  it("vence a su hora", async () => {
    const cookie = await crearCookie(cfg, identidad, AHORA);
    expect(await leerCookie(await conCookie(cookie.valor), cfg, AHORA + 12 * 3600 * 1000 + 1000)).toBeNull();
  });

  it("rechaza lo alterado: otro correo, otra hora, otra firma, otro secreto", async () => {
    const cookie = await crearCookie(cfg, identidad, AHORA);
    const [correo, exp, firma] = cookie.valor.split(".");
    const otroCorreo = aBase64Url(enc.encode("jefa@example.com"));
    expect(await leerCookie(await conCookie(`${otroCorreo}.${exp}.${firma}`), cfg, AHORA)).toBeNull();
    expect(await leerCookie(await conCookie(`${correo}.${Number(exp) + 9999}.${firma}`), cfg, AHORA)).toBeNull();
    expect(await leerCookie(await conCookie(`${correo}.${exp}.${"0".repeat(64)}`), cfg, AHORA)).toBeNull();
    expect(await leerCookie(await conCookie(cookie.valor), { ...cfg, secreto: "z".repeat(40) }, AHORA)).toBeNull();
    for (const malo of ["", "a.b", "x.y.z", `${correo}.abc.${firma}`]) {
      expect(await leerCookie(await conCookie(malo), cfg, AHORA)).toBeNull();
    }
  });

  it("sin la cookie no hay puerta", async () => {
    expect(await leerCookie(new Request("https://dcasapty.com/odoo"), cfg, AHORA)).toBeNull();
    expect(await leerCookie(new Request("https://dcasapty.com/", { headers: { Cookie: "session_id=abc" } }), cfg, AHORA)).toBeNull();
  });

  it("la cabecera hacia Odoo lleva correo, vencimiento y una firma distinta a la de la cookie", async () => {
    const cabecera = await cabeceraParaOdoo(cfg, { email: "duena@example.com", exp: 1_800_000_000 });
    const [correo, exp, firma] = cabecera.split("|");
    expect(correo).toBe("duena@example.com");
    expect(exp).toBe("1800000000");
    expect(firma).toMatch(/^[0-9a-f]{64}$/);
    const cookie = await crearCookie(cfg, { email: "duena@example.com", exp: 1_800_000_000 }, AHORA);
    expect(cookie.valor.split(".")[2]).not.toBe(firma);
  });

  it("sinCookieDePuerta quita solo la cookie de la puerta", () => {
    expect(sinCookieDePuerta(`session_id=abc; ${NOMBRE_COOKIE}=xyz; tz=Panama`)).toBe("session_id=abc; tz=Panama");
    expect(sinCookieDePuerta(`${NOMBRE_COOKIE}=xyz`)).toBeNull();
    expect(sinCookieDePuerta("a=1")).toBe("a=1");
    expect(sinCookieDePuerta(null)).toBeNull();
  });
});

// ------------------------------------------------------------------ rutas

describe("rutas de la puerta", () => {
  it("la entrada ignora mayúsculas y la barra final, pero no es una ruta parecida", () => {
    expect(esEntrada(RUTA, cfg)).toBe(true);
    expect(esEntrada(RUTA.toUpperCase(), cfg)).toBe(true);
    expect(esEntrada(`${RUTA}/`, cfg)).toBe(true);
    expect(esEntrada(`${RUTA}/mas`, cfg)).toBe(false);
    expect(esEntrada(`${RUTA}x`, cfg)).toBe(false);
    expect(esEntrada("/", cfg)).toBe(false);
  });

  it("el panel es /odoo y lo de debajo, también con prefijo de idioma; la tienda y el portal no", () => {
    for (const ruta of ["/odoo", "/odoo/action-12", "/es/odoo", "/es_419/odoo/ventas"]) expect(esPanel(ruta)).toBe(true);
    for (const ruta of ["/", "/shop", "/my", "/web/login", "/odoos", "/odoo-gratis", "/socios"]) expect(esPanel(ruta)).toBe(false);
  });
});

// ------------------------------------------------------------------ el borde completo

describe("handleRequest con la puerta", () => {
  const conPuerta = (forward = vi.fn(async (req: Request) => new Response("odoo", { headers: { "X-Visto": req.headers.get("X-Dcasa-Puerta") ?? "" } }))) => ({
    forward,
    puerta: { config: cfg, jwt: deps(), modo: "1", exigirCorreo: false },
  });

  async function entrar(
    forward: (req: Request) => Promise<Response> = vi.fn(async () => new Response("odoo")),
    correo = "duena@example.com",
  ) {
    const token = await firmar(par, cargaBuena({ email: correo, exp: AHORA_S + 24 * 3600 }));
    const respuesta = await handleRequest(
      new Request(`https://dcasapty.com${RUTA}`, { headers: { "Cf-Access-Jwt-Assertion": token } }),
      { forward, puerta: { config: cfg, jwt: deps(), modo: "1", exigirCorreo: false } },
    );
    const cookie = (respuesta.headers.get("Set-Cookie") ?? "").split(";")[0];
    return { respuesta, cookie, forward };
  }

  it("con el interruptor en «0» o «avisar» el panel NO se cierra (rescate y periodo de prueba), pero sí se firma la cabecera", async () => {
    const { cookie } = await entrar();
    const forward = vi.fn(async (req: Request) => new Response(req.headers.get("X-Dcasa-Puerta") ?? "ninguna"));
    const abierto = { config: cfg, jwt: deps(), modo: "avisar" as const, exigirCorreo: false };
    const sin = await handleRequest(new Request("https://dcasapty.com/odoo"), { forward, puerta: abierto });
    expect(await sin.text()).toBe("ninguna");
    const con = await handleRequest(new Request("https://dcasapty.com/odoo", { headers: { Cookie: cookie } }), { forward, puerta: abierto });
    expect((await con.text()).startsWith("duena@example.com|")).toBe(true);
    // La entrada funciona igual en este modo: así se prueba antes de cerrar.
    const token = await firmar(par, cargaBuena({ exp: AHORA_S + 24 * 3600 }));
    const entrada = await handleRequest(
      new Request(`https://dcasapty.com${RUTA}`, { headers: { "Cf-Access-Jwt-Assertion": token } }),
      { forward, puerta: abierto },
    );
    expect(entrada.status).toBe(200);
    expect(entrada.headers.get("Set-Cookie")).toContain(NOMBRE_COOKIE);
  });

  it("apagada: todo pasa como antes y la cabecera falsa del visitante se borra", async () => {
    const forward = vi.fn(async (req: Request) => new Response(req.headers.get("X-Dcasa-Puerta") ?? "ninguna"));
    const res = await handleRequest(
      new Request("https://dcasapty.com/odoo", { headers: { "X-Dcasa-Puerta": "jefa@example.com|9999999999|firma" } }),
      { forward },
    );
    expect(await res.text()).toBe("ninguna");
    expect(forward).toHaveBeenCalledOnce();
  });

  it("encendida y sin cookie: /odoo es un 404 del borde y Odoo ni se entera", async () => {
    const forward = vi.fn();
    for (const ruta of ["/odoo", "/odoo/action-3", "/es/odoo", "/ODOO", "/%6fdoo"]) {
      const res = await handleRequest(new Request(`https://dcasapty.com${ruta}`), { forward, puerta: { config: cfg, jwt: deps(), modo: "1", exigirCorreo: false } });
      expect(res.status, ruta).toBe(404);
      expect(res.headers.get("Strict-Transport-Security")).toContain("max-age=");
    }
    expect(forward).not.toHaveBeenCalled();
  });

  it("encendida: el resto del sitio y /web/login siguen abiertos, sin cabecera, y borra la falsa", async () => {
    const forward = vi.fn(async (req: Request) => new Response(req.headers.get("X-Dcasa-Puerta") ?? "ninguna"));
    for (const ruta of ["/", "/shop", "/web/login", "/my", "/socios"]) {
      const res = await handleRequest(
        new Request(`https://dcasapty.com${ruta}`, { headers: { "X-Dcasa-Puerta": "jefa@example.com|9999999999|firma" } }),
        { forward, puerta: { config: cfg, jwt: deps(), modo: "1", exigirCorreo: false } },
      );
      expect(await res.text(), ruta).toBe("ninguna");
    }
  });

  it("la entrada con un token válido abre la puerta: Odoo da la página del equipo y la respuesta trae la cookie", async () => {
    const forward = vi.fn(async (req: Request) => new Response(`pagina:${new URL(req.url).pathname}:${req.headers.get("X-Dcasa-Puerta")}`));
    const { respuesta } = await entrar(forward);
    expect(respuesta.status).toBe(200);
    const cuerpo = await respuesta.text();
    expect(cuerpo.startsWith(`pagina:${RUTA}:duena@example.com|`)).toBe(true);
    const cookie = respuesta.headers.get("Set-Cookie") ?? "";
    expect(cookie).toContain(`${NOMBRE_COOKIE}=`);
    for (const parte of ["HttpOnly", "Secure", "SameSite=Lax", "Path=/", "Max-Age=43200"]) expect(cookie).toContain(parte);
    expect(cookie).not.toContain("Domain");
    expect(respuesta.headers.get("Cache-Control")).toBe("no-store");
    expect(respuesta.headers.get("X-Content-Type-Options")).toBe("nosniff");
    expect(forward).toHaveBeenCalledOnce();
  });

  it("enviar el formulario (POST) a la entrada también pasa por la puerta, con el token de Access de ese pedido", async () => {
    const token = await firmar(par, cargaBuena({ exp: AHORA_S + 24 * 3600 }));
    const forward = vi.fn(async (req: Request) => new Response(`${req.method}:${await req.text()}:${req.headers.get("X-Dcasa-Puerta-Modo")?.split("|")[0]}`));
    const res = await handleRequest(
      new Request(`https://dcasapty.com${RUTA}`, { method: "POST", body: "login=a", headers: { "Cf-Access-Jwt-Assertion": token } }),
      { forward, puerta: { config: cfg, jwt: deps(), modo: "1", exigirCorreo: false } },
    );
    expect(await res.text()).toBe("POST:login=a:1");
    expect(res.headers.get("Set-Cookie")).toContain(NOMBRE_COOKIE);
  });

  it("si Odoo está arrancando (5xx) la entrada no entrega cookie todavía", async () => {
    const token = await firmar(par, cargaBuena({ exp: AHORA_S + 24 * 3600 }));
    const forward = vi.fn(async () => new Response("arrancando", { status: 503 }));
    const res = await handleRequest(
      new Request(`https://dcasapty.com${RUTA}`, { headers: { "Cf-Access-Jwt-Assertion": token } }),
      { forward, puerta: { config: cfg, jwt: deps(), modo: "1", exigirCorreo: false } },
    );
    expect(res.status).toBe(503);
    expect(res.headers.get("Set-Cookie")).toBeNull();
  });

  it("la entrada sin token, con token malo o con otro método es un 404 sin cookie", async () => {
    const forward = vi.fn();
    const malo = await firmar(otroPar, cargaBuena());
    const casos: Request[] = [
      new Request(`https://dcasapty.com${RUTA}`),
      new Request(`https://dcasapty.com${RUTA}`, { headers: { "Cf-Access-Jwt-Assertion": malo } }),
      new Request(`https://dcasapty.com${RUTA}`, { method: "DELETE", headers: { "Cf-Access-Jwt-Assertion": await firmar(par, cargaBuena()) } }),
    ];
    for (const caso of casos) {
      const res = await handleRequest(caso, { forward, puerta: { config: cfg, jwt: deps(), modo: "1", exigirCorreo: false } });
      expect(res.status).toBe(404);
      expect(res.headers.get("Set-Cookie")).toBeNull();
    }
    expect(forward).not.toHaveBeenCalled();
  });

  it("con la cookie: /odoo llega a Odoo con la cabecera firmada y sin la cookie de la puerta", async () => {
    const { cookie } = await entrar();
    const forward = vi.fn(async (req: Request) => new Response(JSON.stringify({
      puerta: req.headers.get("X-Dcasa-Puerta"), cookie: req.headers.get("Cookie"),
    })));
    const res = await handleRequest(
      new Request("https://dcasapty.com/odoo", { headers: { Cookie: `session_id=abc; ${cookie}` } }),
      { forward, puerta: { config: cfg, jwt: deps(), modo: "1", exigirCorreo: false } },
    );
    const visto = (await res.json()) as { puerta: string; cookie: string };
    const [correo, exp, firma] = visto.puerta.split("|");
    expect(correo).toBe("duena@example.com");
    expect(Number(exp)).toBe(AHORA_S + 12 * 3600);
    expect(firma).toBe((await cabeceraParaOdoo(cfg, { email: correo, exp: Number(exp) })).split("|")[2]);
    expect(visto.cookie).toBe("session_id=abc");
  });

  it("con la cookie, una cabecera falsa del visitante no gana: se reemplaza por la verdadera", async () => {
    const { cookie } = await entrar();
    const forward = vi.fn(async (req: Request) => new Response(req.headers.get("X-Dcasa-Puerta")));
    const res = await handleRequest(
      new Request("https://dcasapty.com/web/login", {
        headers: { Cookie: cookie, "X-Dcasa-Puerta": "jefa@example.com|9999999999|firma" },
      }),
      { forward, puerta: { config: cfg, jwt: deps(), modo: "1", exigirCorreo: false } },
    );
    expect((await res.text()).startsWith("duena@example.com|")).toBe(true);
  });

  it("una cookie fabricada con otro secreto no abre nada", async () => {
    const falsa = await crearCookie({ ...cfg, secreto: "z".repeat(40) }, { email: "jefa@example.com", exp: AHORA_S + 3600 }, AHORA);
    const forward = vi.fn();
    const res = await handleRequest(
      new Request("https://dcasapty.com/odoo", { headers: { Cookie: `${NOMBRE_COOKIE}=${falsa.valor}` } }),
      { forward, puerta: { config: cfg, jwt: deps(), modo: "1", exigirCorreo: false } },
    );
    expect(res.status).toBe(404);
    expect(forward).not.toHaveBeenCalled();
  });

  it("cerrar sesión en Odoo cierra también la puerta", async () => {
    const { cookie } = await entrar();
    const forward = vi.fn(async () => new Response(null, { status: 303, headers: { Location: "/web/login" } }));
    const res = await handleRequest(
      new Request("https://dcasapty.com/web/session/logout", { headers: { Cookie: cookie } }),
      { forward, puerta: { config: cfg, jwt: deps(), modo: "1", exigirCorreo: false } },
    );
    expect(res.status).toBe(303);
    expect(res.headers.get("Set-Cookie")).toContain(`${NOMBRE_COOKIE}=;`);
    expect(res.headers.get("Set-Cookie")).toContain("Max-Age=0");
  });

  it("a Odoo le llega en CADA petición el modo firmado (también sin cookie), y el del visitante se borra", async () => {
    const forward = vi.fn(async (req: Request) => new Response(req.headers.get("X-Dcasa-Puerta-Modo") ?? "ninguna"));
    for (const [modo, exigirCorreo] of [["1", true], ["avisar", false], ["0", false]] as const) {
      const res = await handleRequest(
        new Request("https://dcasapty.com/web/login", { headers: { "X-Dcasa-Puerta-Modo": "0|0|9999999999|firma-falsa" } }),
        { forward, puerta: { config: cfg, jwt: deps(), modo, exigirCorreo } },
      );
      const [m, e, vence, firma] = (await res.text()).split("|");
      expect([m, e]).toEqual([modo, exigirCorreo ? "1" : "0"]);
      expect(Number(vence)).toBe(AHORA_S + 300);
      expect(firma).toBe((await cabeceraDeModo(cfg, modo, exigirCorreo, AHORA)).split("|")[3]);
    }
  });

  it("apagada del todo: ninguna de las dos cabeceras llega a Odoo, ni siquiera las falsas", async () => {
    const forward = vi.fn(async (req: Request) => new Response(
      `${req.headers.get("X-Dcasa-Puerta") ?? "-"}/${req.headers.get("X-Dcasa-Puerta-Modo") ?? "-"}`));
    const res = await handleRequest(
      new Request("https://dcasapty.com/web/login", {
        headers: { "X-Dcasa-Puerta": "a@b.c|1|f", "x-dcasa-puerta-modo": "0|0|1|f" },
      }),
      { forward },
    );
    expect(await res.text()).toBe("-/-");
  });

  it("cerrar sesión con prefijo de idioma también cierra la puerta", async () => {
    const { cookie } = await entrar();
    for (const ruta of ["/web/session/logout", "/es/web/session/logout", "/es_419/web/session/logout"]) {
      const forward = vi.fn(async () => new Response(null, { status: 303, headers: { Location: "/web/login" } }));
      const res = await handleRequest(
        new Request(`https://dcasapty.com${ruta}`, { headers: { Cookie: cookie } }),
        { forward, puerta: { config: cfg, jwt: deps(), modo: "1", exigirCorreo: false } },
      );
      expect(res.headers.get("Set-Cookie"), ruta).toContain("Max-Age=0");
    }
  });

  it("un correo con caracteres fuera de ASCII no abre la puerta (rompería las cabeceras HTTP)", async () => {
    for (const correo of ["jose@例え.jp", "josé@example.com", "a b@example.com", "a@@example.com"]) {
      const token = await firmar(par, cargaBuena({ email: correo }));
      expect(await verificarJwtAccess(token, cfg, deps()), correo).toBeNull();
    }
  });

  it("abrirPuerta se puede probar sola", async () => {
    const token = await firmar(par, cargaBuena());
    const paso = await abrirPuerta(
      new Request(`https://dcasapty.com${RUTA}`, { headers: { "Cf-Access-Jwt-Assertion": token } }),
      cfg,
      deps(),
    );
    expect(paso?.abierta.email).toBe("duena@example.com");
    expect(paso?.setCookie).toContain(NOMBRE_COOKIE);
    expect(await abrirPuerta(new Request(`https://dcasapty.com${RUTA}`), cfg, deps())).toBeNull();
  });

  it("con /master como entrada, el login público del panel manda a /master (solo en modo «1»)", async () => {
    const maestra = { ...cfg, ruta: "/master" };
    const forward = vi.fn(async () => new Response("login-publico"));
    const ir = (modo: "0" | "avisar" | "1", ruta: string, init?: RequestInit) =>
      handleRequest(new Request(`https://dcasapty.com${ruta}`, init), {
        forward, puerta: { config: maestra, jwt: deps(), modo, exigirCorreo: false },
      });
    const sinSesion = await ir("1", "/web/login?redirect=%2Fodoo%3Fdebug%3D1");
    expect(sinSesion.status).toBe(302);
    expect(sinSesion.headers.get("Location")).toBe("/master");
    expect(forward).not.toHaveBeenCalled();
    for (const modo of ["0", "avisar"] as const) {
      expect(await (await ir(modo, "/web/login?redirect=%2Fodoo")).text(), modo).toBe("login-publico");
    }
    // Lo que NO se redirige: clientes, el segundo paso del código, otros destinos y los POST.
    for (const ruta of ["/web/login", "/web/login?redirect=%2Fmy", "/web/login/totp?redirect=%2Fodoo", "/web/login?redirect=%2Fodoo-no", "/my"]) {
      expect(await (await ir("1", ruta)).text(), ruta).toBe("login-publico");
    }
    expect(await (await ir("1", "/web/login?redirect=%2Fodoo", { method: "POST", body: "x=1" })).text()).toBe("login-publico");
  });

  it("esLoginPublicoDelPanel solo reconoce el login con destino al panel", () => {
    const pide = (ruta: string, method = "GET") =>
      esLoginPublicoDelPanel(new Request(`https://dcasapty.com${ruta}`, { method }), ruta.split("?")[0]);
    expect(pide("/web/login?redirect=/odoo")).toBe(true);
    expect(pide("/web/login?redirect=/odoo/action-1")).toBe(true);
    // El QR de un documento (uso interno): el equipo sin sesión va a su página, igual que con /odoo.
    expect(pide("/web/login?redirect=/dcasa/doc/FAC/INV-2026-00001")).toBe(true);
    expect(pide("/web/login?redirect=%2Fdcasa%2Fdoc%2FCOT%2FS00007")).toBe(true);
    expect(pide("/web/login?redirect=/dcasa/docs")).toBe(false);
    expect(pide("/web/login?redirect=/dcasa/juan/x")).toBe(false);
    expect(pide("/web/login?redirect=/dcasa/img/a.webp")).toBe(false);
    expect(pide("/web/login?redirect=/shop")).toBe(false);
    expect(pide("/web/login")).toBe(false);
    expect(pide("/web/login?redirect=/odoo", "POST")).toBe(false);
    expect(pide("/web/login/totp?redirect=/odoo")).toBe(false);
  });
});
