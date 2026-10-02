import { describe, expect, it, vi } from "vitest";

import { handleRequest, manejarRegenerarTienda } from "../src/handler";
import { isBlockedPath, route, rutaEstatica } from "../src/routing";
import { CLASES_AMARILLAS, FONDOS_OSCUROS } from "../src/tienda/estilo";
import { dinero, renderizarSitio, RUTA_AGREGAR } from "../src/tienda/render";
import { CLAVE_MANIFIESTO, clavePagina, regenerarTienda, tiendaActiva } from "../src/tienda/servir";
import { almacenMemoria, feedEjemplo, producto } from "./feed-ejemplo";

const TOKEN = "t".repeat(40);
const paginas = (feed = feedEjemplo()) => new Map(renderizarSitio(feed).map((p) => [p.ruta, p.html]));

function jsonLd(html: string): Record<string, unknown>[] {
  return [...html.matchAll(/<script type="application\/ld\+json">(.*?)<\/script>/gs)].map((m) => JSON.parse(m[1]));
}

/** Recorre las etiquetas y devuelve las clases amarillas que NO están dentro de un fondo azul/navy. */
function amarilloSobreBlanco(html: string): string[] {
  const vacias = new Set(["img", "input", "meta", "link", "br", "hr", "source"]);
  const pila: string[][] = [];
  const malas: string[] = [];
  for (const m of html.matchAll(/<(\/?)([a-z0-9]+)([^>]*)>/gi)) {
    const [, cierre, etiqueta, atributos] = m;
    if (cierre) {
      pila.pop();
      continue;
    }
    const clases = /class="([^"]*)"/.exec(atributos)?.[1].split(/\s+/) ?? [];
    if (clases.some((c) => (CLASES_AMARILLAS as readonly string[]).includes(c))) {
      const oscuro = pila.some((cl) => cl.some((c) => (FONDOS_OSCUROS as readonly string[]).includes(c)));
      if (!oscuro) malas.push(m[0]);
    }
    if (!vacias.has(etiqueta.toLowerCase()) && !atributos.endsWith("/")) pila.push(clases);
  }
  return malas;
}

describe("rutas de la tienda estática (mismas URL que Odoo)", () => {
  const ruta = (u: string, metodo = "GET") => rutaEstatica(new URL(`https://dcasapty.com${u}`), metodo);

  it("sirve desde el almacén solo las páginas públicas", () => {
    for (const u of [
      "/",
      "/shop",
      "/shop/page/2",
      "/shop/category/salas-3",
      "/shop/category/salas-3/page/2",
      "/shop/cama-twin-xht022-12",
      "/visitanos",
      "/privacidad",
      "/terminos",
    ]) {
      expect(ruta(u), u).toBe(u);
    }
    expect(ruta("/?utm_source=ig&fbclid=x")).toBe("/");
    expect(ruta("/", "HEAD")).toBe("/");
  });

  it("todo lo dinámico va a Odoo como hoy", () => {
    for (const u of [
      "/shop/cart",
      "/shop/checkout",
      "/shop/payment",
      "/shop/address",
      "/shop/confirmation",
      "/shop/cart/update_json",
      "/my",
      "/my/orders",
      "/odoo",
      "/web/login",
      "/socios",
      "/brian/mcp",
      "/dcasa/carrito/agregar-borde",
      "/whatsapp",
      "/contactus",
      "/es/shop",
      "/shop?search=cama",
      "/shop?order=list_price+asc",
      "/shop/cama-12?attribute_values=3",
      "/shop/category/salas-3?tags=1",
      "/shop/",
      "/sitemap.xml",
    ]) {
      expect(ruta(u), u).toBeNull();
    }
    expect(ruta("/", "POST")).toBeNull();
    expect(ruta("/shop/cama-12", "POST")).toBeNull();
  });

  it("el feed nunca se expone a internet y la regeneración es del borde", () => {
    expect(isBlockedPath("/dcasa/tienda/feed")).toBe(true);
    expect(isBlockedPath("/es/dcasa/tienda/feed")).toBe(true);
    expect(isBlockedPath("/DCASA/Tienda/Feed")).toBe(true);
    expect(route(new URL("https://dcasapty.com/__edge/tienda/regenerar"), "POST").kind).toBe("tienda_regenerar");
  });

  it("TIENDA_ESTATICA: solo «on» la enciende", () => {
    expect(tiendaActiva("on")).toBe(true);
    expect(tiendaActiva("ON ")).toBe(true);
    for (const v of ["off", "", undefined, "no"]) expect(tiendaActiva(v)).toBe(false);
  });
});

describe("generador de páginas", () => {
  it("genera portada, tienda, categorías con hijas, fichas, Visítanos y legales", () => {
    const sitio = paginas();
    for (const r of ["/", "/shop", "/shop/category/salas-3", "/shop/mueble-1-1", "/visitanos", "/privacidad", "/terminos"]) {
      expect(sitio.has(r), r).toBe(true);
    }
    expect(sitio.has("/shop/category/recamaras-4"), "categoría sin productos").toBe(false);
  });

  it("precio «$X + ITBMS» tal como viene de Odoo", () => {
    const sitio = paginas(feedEjemplo([producto(1, { precio: 1299 }), producto(2, { mas_itbms: false, precio: 15 })]));
    expect(dinero(1299)).toBe("$1,299.00");
    expect(sitio.get("/shop/mueble-1-1")).toContain('$1,299.00 <span class="itbms">+ ITBMS</span>');
    expect(sitio.get("/shop")).toContain("$1,299.00");
    expect(sitio.get("/shop/mueble-2-2")).toContain("$15.00");
    expect(sitio.get("/shop/mueble-2-2")).not.toContain("+ ITBMS</span></p>");
  });

  it("precio oculto si Odoo no deja venderlo a cero: sin precio ni botón de compra", () => {
    const html = paginas(feedEjemplo([producto(1, { precio: 0, precio_visible: false })])).get("/shop/mueble-1-1")!;
    expect(html).not.toContain("$0.00");
    expect(html).not.toContain(RUTA_AGREGAR);
  });

  it("canónica = la URL de Odoo, con el dominio del sitio", () => {
    const sitio = paginas();
    expect(sitio.get("/shop/mueble-1-1")).toContain('<link rel="canonical" href="https://dcasapty.com/shop/mueble-1-1">');
    expect(sitio.get("/shop")).toContain('<link rel="canonical" href="https://dcasapty.com/shop">');
    expect(sitio.get("/")).toContain('<link rel="canonical" href="https://dcasapty.com/">');
    const local = feedEjemplo();
    local.sitio.url_base = "";
    const conHost = renderizarSitio(local, { canonicalHost: "staging.dcasapty.com" }).find((p) => p.ruta === "/shop")!;
    expect(conHost.html).toContain('href="https://staging.dcasapty.com/shop"');
  });

  it("JSON-LD de Odoo (Product + migas) y de la tienda, seguro dentro de <script>", () => {
    const peligroso = producto(1, { nombre: "Mesa </script><script>alert(1)</script>" });
    (peligroso.json_ld[0] as Record<string, unknown>).name = peligroso.nombre;
    const sitio = paginas(feedEjemplo([peligroso]));
    const ficha = sitio.get("/shop/mueble-1-1")!;
    expect(ficha).not.toContain("<script>alert(1)");
    const datos = jsonLd(ficha);
    expect(datos.map((d) => d["@type"])).toEqual(["Organization", "Product"]);
    expect((datos[1] as { name: string }).name).toBe(peligroso.nombre);
    expect(JSON.stringify(datos[1])).not.toContain("availability");
    expect(jsonLd(sitio.get("/")!).map((d) => d["@type"])).toContain("FurnitureStore");
  });

  it("CTA de WhatsApp en todas las páginas y la de la ficha con el nombre del mueble", () => {
    for (const [ruta, html] of paginas()) {
      expect(html, ruta).toContain("Escríbenos por WhatsApp");
      expect(html, ruta).toContain("https://wa.me/50760261919");
    }
    expect(paginas().get("/shop/mueble-1-1")).toContain("Pregunta por este mueble por WhatsApp");
  });

  it("el amarillo nunca toca el blanco y no hay degradados ni sombras", () => {
    for (const [ruta, html] of paginas()) {
      expect(amarilloSobreBlanco(html), ruta).toEqual([]);
      expect(html, ruta).not.toMatch(/gradient\(|box-shadow|text-shadow/);
    }
    // El verificador sí detecta el caso malo.
    expect(amarilloSobreBlanco('<section class="hueso"><a class="btn btn-amarillo">x</a></section>')).toHaveLength(1);
  });

  it("«Agregar al carrito» es un formulario POST a Odoo, sin JavaScript ni token de sesión", () => {
    const html = paginas().get("/shop/mueble-1-1")!;
    expect(html).toContain(`<form action="${RUTA_AGREGAR}" method="post"><input type="hidden" name="product_template_id" value="1">`);
    expect(html).not.toContain("csrf_token");
    expect(html).not.toMatch(/<script(?! type="application\/ld\+json")/);
  });

  it("variantes: una opción por variante con su precio; fichas a configurar las sirve Odoo", () => {
    const cama = producto(7, {
      compra: "variantes",
      variantes: [
        { id: 70, nombre: "Twin", precio: 100, disponible: null, existencias: null },
        { id: 71, nombre: "Queen", precio: 150, disponible: null, existencias: null },
      ],
    });
    const combo = producto(8, { compra: "ficha" });
    const sitio = paginas(feedEjemplo([cama, combo]));
    const html = sitio.get("/shop/mueble-7-7")!;
    expect(html).toContain('name="product_id" value="70"');
    expect(html).toContain("$150.00");
    expect(sitio.get("/shop")).toContain('<span class="desde">desde </span>$100.00');
    expect(sitio.has("/shop/mueble-8-8")).toBe(false);
    expect(sitio.get("/shop")).toContain('href="/shop/mueble-8-8">Elegir');
  });

  it("existencias: nada mientras Odoo no las publique; «Disponible» si las publica", () => {
    expect(paginas().get("/shop/mueble-1-1")).not.toContain("Disponible");
    const sitio = paginas(feedEjemplo([producto(1, { disponible: true, existencias: 3 }), producto(2, { disponible: false, existencias: 0 })]));
    expect(sitio.get("/shop/mueble-1-1")).toContain(">Disponible<");
    expect(sitio.get("/shop/mueble-2-2")).toContain("Agotado");
  });

  it("paginación con las URL de Odoo (/shop/page/N)", () => {
    const muchos = Array.from({ length: 45 }, (_, i) => producto(i + 1));
    const sitio = paginas(feedEjemplo(muchos));
    expect(sitio.has("/shop/page/2")).toBe(true);
    expect(sitio.has("/shop/page/3")).toBe(true);
    expect(sitio.has("/shop/page/4")).toBe(false);
    expect(sitio.has("/shop/page/1")).toBe(false);
    expect(sitio.get("/shop/page/2")).toContain('<link rel="canonical" href="https://dcasapty.com/shop/page/2">');
  });

  it("escapa lo que viene de Odoo en el HTML", () => {
    const html = paginas(feedEjemplo([producto(1, { nombre: 'Mesa "<b>grande</b>"' })])).get("/shop/mueble-1-1")!;
    expect(html).toContain("Mesa &quot;&lt;b&gt;grande&lt;/b&gt;&quot;");
  });

  it("legales con el texto de Odoo", () => {
    expect(paginas().get("/privacidad")).toContain("Ley 81 de 2019");
    expect(paginas().get("/terminos")).toContain("no incluyen el ITBMS");
  });
});

describe("servir desde el almacén (TIENDA_ESTATICA)", () => {
  async function conSitio() {
    const almacen = almacenMemoria();
    await regenerarTienda({ almacen, leerFeed: async () => Response.json(feedEjemplo()) });
    return almacen;
  }
  const odoo = () => vi.fn(async () => new Response("odoo", { headers: { "Content-Type": "text/html" } }));

  it("con la tienda activa, la portada sale del almacén sin tocar Odoo", async () => {
    const almacen = await conSitio();
    const forward = odoo();
    const res = await handleRequest(new Request("https://dcasapty.com/"), { forward, tienda: { activa: true, almacen } });
    expect(res.status).toBe(200);
    expect(res.headers.get("X-Dcasa-Tienda")).toBe("estatica");
    expect(res.headers.get("Content-Type")).toContain("text/html");
    expect(res.headers.get("X-Content-Type-Options")).toBe("nosniff");
    expect(await res.text()).toContain("Tu casa, bien amueblada.");
    expect(forward).not.toHaveBeenCalled();
  });

  it("apagada (producción hasta aprobarla): todo a Odoo", async () => {
    const almacen = await conSitio();
    const forward = odoo();
    const res = await handleRequest(new Request("https://dcasapty.com/"), { forward, tienda: { activa: false, almacen } });
    expect(await res.text()).toBe("odoo");
  });

  it("página que no está en el almacén, carrito, /my y POST: a Odoo", async () => {
    const almacen = await conSitio();
    const forward = odoo();
    const deps = { forward, tienda: { activa: true, almacen } };
    for (const [url, init] of [
      ["https://dcasapty.com/shop/otro-99", {}],
      ["https://dcasapty.com/shop/cart", { headers: { Cookie: "session_id=abc" } }],
      ["https://dcasapty.com/my", { headers: { Cookie: "session_id=abc" } }],
      ["https://dcasapty.com/", { method: "POST", body: "x" }],
    ] as const) {
      expect(await (await handleRequest(new Request(url, init), deps)).text(), url).toBe("odoo");
    }
    expect(forward).toHaveBeenCalledTimes(4);
  });

  it("304 si el navegador ya tiene la versión (ETag)", async () => {
    const almacen = await conSitio();
    const deps = { forward: odoo(), tienda: { activa: true, almacen } };
    const primera = await handleRequest(new Request("https://dcasapty.com/shop"), deps);
    const etag = primera.headers.get("ETag")!;
    expect(etag).toMatch(/^"t-[0-9a-f]+"$/);
    const segunda = await handleRequest(new Request("https://dcasapty.com/shop", { headers: { "If-None-Match": etag } }), deps);
    expect(segunda.status).toBe(304);
  });

  it("si el almacén falla, sirve Odoo", async () => {
    const forward = odoo();
    const almacen = { leer: async () => Promise.reject(new Error("KV caído")), escribir: vi.fn(), borrar: vi.fn() };
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const res = await handleRequest(new Request("https://dcasapty.com/"), { forward, tienda: { activa: true, almacen } });
    expect(await res.text()).toBe("odoo");
  });
});

describe("staging: noindex en todo", () => {
  it("X-Robots-Tag en páginas de Odoo, estáticas, 404 y redirecciones", async () => {
    const forward = vi.fn(async () => new Response("odoo"));
    const almacen = almacenMemoria();
    await regenerarTienda({ almacen, leerFeed: async () => Response.json(feedEjemplo()) });
    const deps = { forward, entorno: "staging", canonicalHost: "staging.dcasapty.com", tienda: { activa: true, almacen } };
    for (const url of [
      "https://staging.dcasapty.com/",
      "https://staging.dcasapty.com/shop/cart",
      "https://staging.dcasapty.com/web/database/manager",
      "https://www.staging.dcasapty.com/shop",
      "https://staging.dcasapty.com/__edge/health",
    ]) {
      const res = await handleRequest(new Request(url), deps);
      expect(res.headers.get("X-Robots-Tag"), url).toBe("noindex, nofollow");
    }
  });

  it("producción no lleva noindex", async () => {
    const res = await handleRequest(new Request("https://dcasapty.com/"), {
      forward: async () => new Response("odoo"),
      entorno: "produccion",
    });
    expect(res.headers.has("X-Robots-Tag")).toBe(false);
  });
});

describe("regeneración (aviso de Odoo)", () => {
  const regenerarCon = (almacen = almacenMemoria()) => ({
    almacen,
    token: TOKEN,
    regenerar: () => regenerarTienda({ almacen, leerFeed: async () => Response.json(feedEjemplo()) }),
  });
  const post = (auth?: string) =>
    new Request("https://dcasapty.com/__edge/tienda/regenerar", {
      method: "POST",
      headers: auth ? { Authorization: auth } : {},
      body: JSON.stringify({ productos: [1] }),
    });

  it("exige el token (≥ 32) y POST", async () => {
    expect((await manejarRegenerarTienda(post(`Bearer ${TOKEN}`), undefined)).status).toBe(404);
    expect((await manejarRegenerarTienda(post("Bearer corto"), { ...regenerarCon(), token: "corto" })).status).toBe(404);
    expect((await manejarRegenerarTienda(post(), regenerarCon())).status).toBe(401);
    expect((await manejarRegenerarTienda(post(`Bearer ${"x".repeat(40)}`), regenerarCon())).status).toBe(401);
    const get = new Request("https://dcasapty.com/__edge/tienda/regenerar");
    expect((await manejarRegenerarTienda(get, regenerarCon())).status).toBe(405);
  });

  it("por el handler: con token regenera y no pasa por Odoo", async () => {
    vi.spyOn(console, "log").mockImplementation(() => undefined);
    const forward = vi.fn();
    const tienda = { activa: false, ...regenerarCon() };
    const res = await handleRequest(post(`Bearer ${TOKEN}`), { forward, tienda });
    expect(res.status).toBe(200);
    const cuerpo = (await res.json()) as { estado: string; escritas: number };
    expect(cuerpo.estado).toBe("ok");
    expect(cuerpo.escritas).toBeGreaterThan(5);
    expect(forward).not.toHaveBeenCalled();
  });

  it("escribe solo lo que cambió y borra lo que ya no existe", async () => {
    const almacen = almacenMemoria();
    let feed = feedEjemplo([producto(1), producto(2)]);
    const regenerar = () => regenerarTienda({ almacen, leerFeed: async () => Response.json(feed) });
    const primera = await regenerar();
    expect(primera.escritas).toBe(primera.paginas);
    const otra = await regenerar();
    expect(otra.escritas).toBe(0);
    feed = feedEjemplo([producto(1, { precio: 99 })]);
    const tercera = await regenerar();
    expect(tercera.borradas).toBe(1);
    expect(almacen.datos.has(clavePagina("/shop/mueble-2-2"))).toBe(false);
    expect(almacen.datos.get(clavePagina("/shop/mueble-1-1"))!.texto).toContain("$99.00");
    expect(JSON.parse(almacen.datos.get(CLAVE_MANIFIESTO)!.texto)).not.toHaveProperty("/shop/mueble-2-2");
  });

  it("un feed roto o vacío no borra el sitio publicado", async () => {
    const almacen = almacenMemoria();
    await regenerarTienda({ almacen, leerFeed: async () => Response.json(feedEjemplo()) });
    const antes = almacen.datos.size;
    expect((await regenerarTienda({ almacen, leerFeed: async () => new Response("x", { status: 500 }) })).estado).toBe("fallo");
    expect((await regenerarTienda({ almacen, leerFeed: async () => new Response("no json") })).estado).toBe("fallo");
    expect((await regenerarTienda({ almacen, leerFeed: async () => Response.json({ version: 99 }) })).estado).toBe("fallo");
    const vacio = await regenerarTienda({ almacen, leerFeed: async () => Response.json(feedEjemplo([])) });
    expect(vacio.estado).toBe("fallo");
    expect(almacen.datos.size).toBe(antes);
  });

  it("si la regeneración falla, Odoo recibe 503 y reintenta", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const almacen = almacenMemoria();
    const res = await manejarRegenerarTienda(post(`Bearer ${TOKEN}`), {
      almacen,
      token: TOKEN,
      regenerar: () => regenerarTienda({ almacen, leerFeed: async () => new Response("", { status: 503 }) }),
    });
    expect(res.status).toBe(503);
  });
});
