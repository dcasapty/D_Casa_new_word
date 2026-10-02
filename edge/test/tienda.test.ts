import { describe, expect, it, vi } from "vitest";

import { handleRequest, manejarRegenerarTienda } from "../src/handler";
import { isBlockedPath, route, rutaEstatica } from "../src/routing";
import { CLASES_AMARILLAS, FONDOS_OSCUROS } from "../src/tienda/estilo";
import { dinero, renderizarSitio, RUTA_AGREGAR } from "../src/tienda/render";
import { CLAVE_MANIFIESTO, clavePagina, regenerarTienda, tiendaActiva } from "../src/tienda/servir";
import { almacenMemoria, feedBlackWeekend, feedEjemplo, producto } from "./feed-ejemplo";

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

  it("fotos: <picture> con WebP al ancho justo y JPEG de respaldo; solo la LCP sin espera", () => {
    const feed = feedEjemplo([producto(1), producto(2), producto(3), producto(4)]);
    const tienda = paginas(feed).get("/shop")!;
    const fotos = [...tienda.matchAll(/<picture>(.*?)<\/picture>/gs)].map((m) => m[1]);
    expect(fotos.length).toBeGreaterThanOrEqual(4);
    for (const foto of fotos) {
      expect(foto).toMatch(
        /^<source type="image\/webp" srcset="\/dcasa\/img\/product\.template\/\d+\/image_1920\/256\.webp\?v=0123456789ab 256w, [^"]*\/512\.webp\?v=\w+ 512w, [^"]*\/1024\.webp\?v=\w+ 1024w" sizes="[^"]+">/,
      );
      expect(foto).toMatch(/<img src="[^"]*\/512\.jpg\?v=\w+" srcset="[^"]*256\.jpg[^"]* 256w, [^"]*512\.jpg[^"]* 512w, [^"]*1024\.jpg[^"]* 1024w"/);
      expect(foto).toContain('width="512" height="512"');
    }
    expect(fotos.slice(0, 2).every((f) => f.includes('loading="eager" fetchpriority="high"'))).toBe(true);
    expect(fotos.slice(2).every((f) => f.includes('loading="lazy"') && !f.includes("fetchpriority"))).toBe(true);

    const ficha = paginas(feed).get("/shop/mueble-1-1")!;
    const lcp = /<div class="galeria"[^>]*><picture>(.*?)<\/picture>/s.exec(ficha)![1];
    expect(lcp).toContain("/1600.webp?v=0123456789ab 1600w");
    expect(lcp).toContain('src="/dcasa/img/product.template/1/image_1920/1024.jpg?v=0123456789ab"');
    expect(lcp).toContain('loading="eager" fetchpriority="high"');
    expect(ficha).toMatch(/<link rel="preload" as="image" type="image\/webp" imagesrcset="[^"]*512\.webp[^"]*1600\.webp\?v=\w+ 1600w"/);
  });

  it("galería en WebP y, con un feed de un Odoo anterior, las URL de /web/image", () => {
    const galeria = { base: "/dcasa/img/product.image/9/image_1920", v: "abcdefabcdef" };
    const conGaleria = producto(1, { galeria: ["/web/image/product.image/9/image_1024"], galeria_fotos: [galeria] });
    const ficha = paginas(feedEjemplo([conGaleria])).get("/shop/mueble-1-1")!;
    expect(ficha).toContain("/dcasa/img/product.image/9/image_1920/1024.webp?v=abcdefabcdef 1024w");
    expect(ficha.match(/fetchpriority="high"/g)?.length).toBe(2); // la foto LCP y su precarga

    const viejo = producto(2);
    delete viejo.imagen!.foto;
    const html = paginas(feedEjemplo([viejo])).get("/shop/mueble-2-2")!;
    expect(html).not.toContain("<picture>");
    expect(html).toContain("/web/image/product.template/2/image_1024?unique=abc1234");
  });

  it("legales con el texto de Odoo", () => {
    expect(paginas().get("/privacidad")).toContain("Ley 81 de 2019");
    expect(paginas().get("/terminos")).toContain("no incluyen el ITBMS");
  });
});

describe("Black Weekend", () => {
  const PROHIBIDAS = /tafi|tiempo limitado|remate|cuotas|financiamiento|¡¡corre|cuenta regresiva/i;
  const visible = (html: string) => html.replace(/<script.*?<\/script>|<style.*?<\/style>/gs, "");

  it("activa: banda en la portada antes de los carriles, página /black-weekend y etiqueta", () => {
    const sitio = paginas(feedBlackWeekend(true));
    const portada = sitio.get("/")!;
    expect(portada).toContain('<section class="bw"');
    expect(portada.indexOf('class="bw"')).toBeLessThan(portada.indexOf("Compra por espacio"));
    expect(portada.indexOf('class="bw"')).toBeLessThan(portada.indexOf("Lo más buscado"));
    expect(portada).toContain('href="/black-weekend"');
    expect(sitio.has("/black-weekend")).toBe(true);
    // La etiqueta sale en la tarjeta del producto marcado, no en la del otro.
    const tienda = sitio.get("/shop")!;
    const tarjeta = (id: number) => tienda.slice(tienda.indexOf(`/shop/mueble-${id}-${id}`), tienda.indexOf("</article>", tienda.indexOf(`/shop/mueble-${id}-${id}`)));
    expect(tarjeta(1)).toContain("bw-etiqueta");
    expect(tarjeta(2)).not.toContain(`class="bw-etiqueta"`);
  });

  it("inactiva o sin productos: ni banda, ni página, ni etiqueta", () => {
    for (const feed of [feedBlackWeekend(false), { ...feedBlackWeekend(true), black_weekend: { ...feedBlackWeekend(true).black_weekend!, productos: [] } }, feedEjemplo()]) {
      const sitio = paginas(feed);
      expect(sitio.has("/black-weekend")).toBe(false);
      for (const html of sitio.values()) {
        expect(html).not.toContain('class="bw"');
        expect(html).not.toContain(`class="bw-etiqueta"`);
      }
    }
  });

  it("/black-weekend: precio y combo del feed, canónica, ItemList, imagen para compartir y CTA", () => {
    const html = paginas(feedBlackWeekend(true)).get("/black-weekend")!;
    expect(html).toContain('<link rel="canonical" href="https://dcasapty.com/black-weekend">');
    expect(html).toContain("$259.99 <span class=\"itbms\">+ ITBMS</span>");
    expect(html).toContain("Combo con colchón First Class <strong>$469.99</strong>");
    expect(html).toContain("del 5 al 11 de octubre de 2026");
    expect(html).toContain('<meta property="og:image" content="https://dcasapty.com/website_dcasa/static/src/img/black_weekend/og.jpg">');
    expect(html).toContain('<meta name="twitter:card" content="summary_large_image">');
    expect(html).toMatch(/<meta name="description" content="Black Weekend en D&#39;CASA Panamá/);
    const lista = jsonLd(html).find((j) => j["@type"] === "ItemList");
    expect(lista?.numberOfItems).toBe(2);
    // Directa: el producto; con color destacado: la variante.
    expect(html).toContain('name="product_template_id" value="1"');
    expect(html).toContain('name="product_id" value="30"');
    expect(html).toContain(`action="${RUTA_AGREGAR}"`);
    expect(html).toContain("c%C3%B3digo%20BW-1");
    expect(html).toContain("Código BW-3-NEGRO");
    expect(html).toContain('type="image/webp"');
    expect(html).not.toContain("/web/image/product.product/10/image_1920");
  });

  it("el precio sale del feed: si cambia en Odoo, cambia la página", () => {
    const feed = feedBlackWeekend(true);
    feed.black_weekend!.productos[0].precio = 249.5;
    const html = paginas(feed).get("/black-weekend")!;
    expect(html).toContain("$249.50");
    expect(html).not.toContain("$259.99");
  });

  it("sin amarillo sobre blanco ni palabras prohibidas", () => {
    for (const [ruta, html] of paginas(feedBlackWeekend(true))) {
      expect(amarilloSobreBlanco(html), ruta).toEqual([]);
      expect(visible(html), ruta).not.toMatch(PROHIBIDAS);
      expect(html, ruta).not.toMatch(/gradient\(|box-shadow|text-shadow/);
    }
    expect(amarilloSobreBlanco('<section class="hueso"><h2 class="bw-titulo">x</h2></section>')).toHaveLength(1);
  });

  it("ruta estática /black-weekend", () => {
    expect(rutaEstatica(new URL("https://dcasapty.com/black-weekend"), "GET")).toBe("/black-weekend");
    expect(rutaEstatica(new URL("https://dcasapty.com/black-weekend?utm_source=ig"), "GET")).toBe("/black-weekend");
    expect(rutaEstatica(new URL("https://dcasapty.com/black-weekend/x"), "GET")).toBeNull();
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

  it("Black Weekend: aparece y desaparece con la campaña al regenerar", async () => {
    const almacen = almacenMemoria();
    await regenerarTienda({ almacen, leerFeed: async () => Response.json(feedBlackWeekend(true)) });
    expect(almacen.datos.has(clavePagina("/black-weekend"))).toBe(true);
    const terminada = await regenerarTienda({ almacen, leerFeed: async () => Response.json(feedBlackWeekend(false)) });
    expect(terminada.borradas).toBe(1);
    expect(almacen.datos.has(clavePagina("/black-weekend"))).toBe(false);
    expect(almacen.datos.get(clavePagina("/"))!.texto).not.toContain('class="bw"');
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
