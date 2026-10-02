/**
 * Generador de la tienda estática: convierte el feed de Odoo en páginas HTML (sin framework,
 * sin Cloudflare: se prueba en Node). Parte del prototipo medido en
 * docs/auditoria/ronda3/sitio-edge/prototipo/generar.mjs.
 *
 * Reglas:
 * - URL idénticas a las de Odoo (`website_url`, `/shop/category/<slug>`, `/shop/page/N`): el
 *   canónico de cada página es la misma URL que tendría en Odoo.
 * - Precios tal cual vienen de Odoo, con «+ ITBMS» si Odoo lo pone. Nada de cifras inventadas.
 * - Existencias solo si Odoo las publica (`disponible` ≠ null).
 * - CTA único de la marca: «Escríbenos por WhatsApp»; además «Agregar al carrito» (POST normal a
 *   `/dcasa/carrito/agregar-borde`, sin JavaScript).
 * - Fichas con `compra: "ficha"` (atributos a configurar, combos…) no se generan: las sirve Odoo.
 */
import { CSS, FUENTES } from "./estilo";
import type { CategoriaFeed, Feed, ProductoFeed } from "./tipos";

export interface PaginaGenerada {
  ruta: string;
  html: string;
}

export interface OpcionesRender {
  /** Host canónico del Worker (CANONICAL_HOST): solo si el feed no trae URL pública. */
  canonicalHost?: string;
}

/** Ruta del POST de «Agregar al carrito» en Odoo (addons/dcasa_tienda_borde). */
export const RUTA_AGREGAR = "/dcasa/carrito/agregar-borde";

const IMG = "/website_dcasa/static/src/img";

export function esc(valor: unknown): string {
  return String(valor ?? "").replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c] as string,
  );
}

/** JSON seguro dentro de <script> (como json_scriptsafe de Odoo). */
export function jsonSeguro(datos: unknown): string {
  return JSON.stringify(datos)
    .replace(/</g, "\\u003c")
    .replace(/>/g, "\\u003e")
    .replace(/&/g, "\\u0026")
    .replace(new RegExp(String.fromCharCode(0x2028), "g"), "\\u2028")
    .replace(new RegExp(String.fromCharCode(0x2029), "g"), "\\u2029");
}

/** `$1,299.00` (USD, como la tienda de Odoo en Panamá). Otra moneda: con su código delante. */
export function dinero(valor: number, moneda = "USD"): string {
  const cifra = valor.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return moneda === "USD" ? `$${cifra}` : `${moneda} ${cifra}`;
}

function precioHtml(p: ProductoFeed, valor: number, desde = false): string {
  if (!p.precio_visible) return "";
  return (
    `<p class="precio">${desde ? '<span class="desde">desde </span>' : ""}${esc(dinero(valor, p.moneda))}` +
    `${p.mas_itbms ? ' <span class="itbms">+ ITBMS</span>' : ""}</p>`
  );
}

function precioMinimo(p: ProductoFeed): { valor: number; desde: boolean } {
  if (p.compra === "variantes" && p.variantes.length) {
    const precios = p.variantes.map((v) => v.precio);
    const minimo = Math.min(...precios);
    return { valor: minimo, desde: Math.max(...precios) !== minimo };
  }
  return { valor: p.precio, desde: false };
}

const ICONO_WA =
  '<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M16 3a13 13 0 0 0-11.2 19.6L3 29l6.6-1.7A13 13 0 1 0 16 3zm0 23.6a10.6 10.6 0 0 1-5.4-1.5l-.4-.2-3.9 1 1-3.8-.2-.4A10.6 10.6 0 1 1 16 26.6zm5.8-7.9c-.3-.2-1.9-.9-2.2-1s-.5-.2-.7.2-.8 1-1 1.2-.4.2-.7.1a8.7 8.7 0 0 1-4.3-3.8c-.3-.6.3-.5.9-1.7.1-.2 0-.4 0-.5l-1-2.4c-.3-.6-.5-.5-.7-.5h-.6a1.2 1.2 0 0 0-.9.4 3.6 3.6 0 0 0-1.1 2.7 6.3 6.3 0 0 0 1.3 3.3 14.4 14.4 0 0 0 5.5 4.9c2 .9 2.8.9 3.8.8a3.2 3.2 0 0 0 2.1-1.5 2.6 2.6 0 0 0 .2-1.5c-.1-.2-.3-.3-.6-.4z"/></svg>';
const NUEVA = '<span class="vh"> (se abre en una pestaña nueva)</span>';

/** Contexto común de todas las páginas. */
class Sitio {
  readonly base: string;
  readonly nombre: string;
  private readonly numeroWa: string | null;
  readonly productos: Map<number, ProductoFeed>;
  readonly categorias: CategoriaFeed[];

  constructor(
    readonly feed: Feed,
    opciones: OpcionesRender,
  ) {
    this.base = (feed.sitio.url_base || (opciones.canonicalHost ? `https://${opciones.canonicalHost}` : "")).replace(
      /\/$/,
      "",
    );
    this.nombre = feed.sitio.nombre || "D'CASA Panamá";
    this.numeroWa = /wa\.me\/(\d+)/.exec(feed.sitio.whatsapp)?.[1] ?? null;
    this.productos = new Map(feed.productos.map((p) => [p.id, p]));
    this.categorias = [...feed.categorias].sort((a, b) => a.secuencia - b.secuencia || a.id - b.id);
  }

  /** Enlace de WhatsApp con el número configurado en Odoo; sin número, /contactus (como Odoo). */
  wa(texto: string): string {
    return this.numeroWa ? `https://wa.me/${this.numeroWa}?text=${encodeURIComponent(texto)}` : "/contactus";
  }

  get waGeneral(): string {
    return this.feed.sitio.whatsapp || this.wa("Hola D'CASA, quiero información");
  }

  /** La categoría y todas sus hijas (como `child_of` en Odoo). */
  descendientes(id: number): Set<number> {
    const ids = new Set([id]);
    let creciendo = true;
    while (creciendo) {
      creciendo = false;
      for (const c of this.categorias) {
        if (c.padre_id !== null && ids.has(c.padre_id) && !ids.has(c.id)) {
          ids.add(c.id);
          creciendo = true;
        }
      }
    }
    return ids;
  }

  productosDe(categoria: CategoriaFeed): ProductoFeed[] {
    const ids = this.descendientes(categoria.id);
    return this.feed.productos.filter((p) => p.categorias.some((c) => ids.has(c)));
  }

  /** ¿Se genera la ficha estática? (las de configurar las sigue sirviendo Odoo) */
  fichaEstatica(p: ProductoFeed): boolean {
    return p.compra !== "ficha";
  }
}

function layout(
  s: Sitio,
  pagina: {
    titulo: string;
    descripcion: string;
    ruta: string;
    cuerpo: string;
    jsonld?: unknown[];
    precarga?: string;
  },
): string {
  const jsonld = [s.feed.sitio.json_ld_organizacion, ...(pagina.jsonld ?? [])].filter(
    (j) => j && typeof j === "object" && Object.keys(j as object).length,
  );
  const canonica = s.base ? `<link rel="canonical" href="${esc(s.base + pagina.ruta)}">` : "";
  const e = s.feed.empresa;
  return `<!doctype html><html lang="es-419"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(pagina.titulo)}</title>${pagina.descripcion ? `<meta name="description" content="${esc(pagina.descripcion)}">` : ""}
${canonica}<meta name="theme-color" content="#1340B1">
<meta property="og:title" content="${esc(pagina.titulo)}"><meta property="og:type" content="website">${s.base ? `<meta property="og:url" content="${esc(s.base + pagina.ruta)}">` : ""}
<link rel="icon" href="${IMG}/favicon.png">
<link rel="preload" href="${FUENTES.anton}" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="${FUENTES.inter}" as="font" type="font/woff2" crossorigin>
${pagina.precarga ?? ""}<style>${CSS}</style>
${jsonld.map((j) => `<script type="application/ld+json">${jsonSeguro(j)}</script>`).join("")}
</head><body><a class="skip" href="#contenido">Ir al contenido</a>
<div class="anuncios" role="region" aria-label="Avisos de D'CASA"><div class="c"><span>Entrega a todo Panamá</span>
<a href="${esc(s.waGeneral)}" target="_blank" rel="noopener">Escríbenos por WhatsApp${NUEVA}</a></div></div>
<header class="top"><div class="c"><a class="logo" href="/" aria-label="${esc(s.nombre)}, inicio"><img src="${IMG}/logo-200.webp" srcset="${IMG}/logo-200.webp 1x, ${IMG}/logo-400.webp 2x" width="200" height="91" alt="D'CASA"></a>
<nav aria-label="Menú principal"><a href="/shop">Catálogo</a><a href="/socios">Socios D'CASA</a><a href="/visitanos">Visítanos</a><a href="/shop/cart">Carrito</a><a href="/my">Mi cuenta</a></nav></div></header>
<main id="contenido">${pagina.cuerpo}</main>
<footer class="pie"><div class="c cols">
<div><p class="kicker">${esc(e.nombre || s.nombre)}</p><p>Tu casa, bien amueblada. Camas, colchones, salas, muebles de TV, zapateras, estantes y escritorios, con la mejor atención y precios pensados para ti.</p>${e.ruc ? `<p>RUC ${esc(e.ruc)}</p>` : ""}</div>
<div><p class="kicker">Tienda</p><ul><li><a href="/shop">Catálogo</a></li><li><a href="/socios">Socios: mis puntos</a></li><li><a href="/my">Mi cuenta</a></li><li><a href="/contactus">Contacto</a></li><li><a href="/privacidad">Privacidad</a></li><li><a href="/terminos">Términos y condiciones</a></li></ul></div>
<div><p class="kicker">Visítanos</p><address style="font-style:normal">${esc(e.calle)}<br>${esc(e.ciudad)}</address><p><a href="/visitanos">Cómo llegar</a></p></div>
<div><p class="kicker">Escríbenos</p><ul><li><a href="${esc(s.waGeneral)}" target="_blank" rel="noopener">Escríbenos por WhatsApp${NUEVA}</a></li>${e.email ? `<li><a href="mailto:${esc(e.email)}">${esc(e.email)}</a></li>` : ""}<li><a href="https://www.instagram.com/dcasapty" target="_blank" rel="noopener">@dcasapty${NUEVA}</a></li></ul></div>
</div></footer>
<a class="wa-flotante" href="${esc(s.waGeneral)}" target="_blank" rel="noopener" aria-label="Escríbenos por WhatsApp (se abre en una pestaña nueva)">${ICONO_WA}</a>
</body></html>`;
}

function imagenProducto(
  p: ProductoFeed,
  opciones: { sizes: string; prioridad?: boolean; grande?: boolean; alt?: string },
): string {
  if (!p.imagen) return `<div style="aspect-ratio:1/1" aria-hidden="true"></div>`;
  const i = p.imagen;
  const srcset = opciones.grande
    ? `${i.image_512} 512w, ${i.image_1024} 1024w, ${i.image_1920} 1920w`
    : `${i.image_256} 256w, ${i.image_512} 512w, ${i.image_1024} 1024w`;
  const src = opciones.grande ? i.image_1024 : i.image_512;
  const carga = opciones.prioridad ? ' loading="eager" fetchpriority="high"' : ' loading="lazy" decoding="async"';
  return `<img src="${esc(src)}" srcset="${esc(srcset)}" sizes="${opciones.sizes}" width="512" height="512" alt="${esc(opciones.alt ?? "")}"${carga}>`;
}

function formularioAgregar(p: ProductoFeed, texto = "Agregar"): string {
  return `<form action="${RUTA_AGREGAR}" method="post"><input type="hidden" name="product_template_id" value="${p.id}"><button type="submit" class="btn btn-azul" aria-label="Agregar ${esc(p.nombre)} al carrito">${texto}</button></form>`;
}

function tarjeta(s: Sitio, p: ProductoFeed, indice = 99): string {
  const { valor, desde } = precioMinimo(p);
  const accion =
    p.compra === "directa" && p.precio_visible
      ? formularioAgregar(p)
      : `<a class="btn btn-azul" href="${esc(p.url)}">Elegir<span class="vh">: ${esc(p.nombre)}</span></a>`;
  return `<li><article class="card"><a class="m" href="${esc(p.url)}" tabindex="-1" aria-hidden="true">${imagenProducto(p, { sizes: "(min-width:1200px) 285px, (min-width:768px) 24vw, 48vw", prioridad: indice < 2 })}</a>
<div class="b"><h3><a href="${esc(p.url)}">${esc(p.nombre)}</a></h3>${precioHtml(p, valor, desde)}
<div class="acciones">${accion}<a class="btn btn-borde wa" href="${esc(p.whatsapp || s.wa(`Hola D'CASA, me interesa: ${p.nombre}`))}" target="_blank" rel="noopener" aria-label="Preguntar por ${esc(p.nombre)} por WhatsApp (se abre en una pestaña nueva)">${ICONO_WA}</a></div></div></article></li>`;
}

function rejilla(s: Sitio, productos: ProductoFeed[]): string {
  return `<ul class="grid" role="list">${productos.map((p, i) => tarjeta(s, p, i)).join("")}</ul>`;
}

// ------------------------------------------------------------------ portada

function portada(s: Sitio): PaginaGenerada {
  const f = s.feed;
  const elegir = (ids: number[]) => ids.map((id) => s.productos.get(id)).filter((p): p is ProductoFeed => !!p);
  const masBuscados = elegir(f.portada.mas_buscados);
  const dormir = elegir(f.portada.para_dormir);
  const { puntos_por_dolar: pp, puntos_al_padrino: padrino, puntos_al_ahijado: ahijado } = f.socios;
  const miles = (n: number) => n.toLocaleString("en-US");
  const carril = (titulo: string, kicker: string, enlace: string, lista: ProductoFeed[], clase = "") =>
    lista.length
      ? `<section${clase ? ` class="${clase}"` : ""}><div class="c"><div class="cab"><div><p class="kicker">${kicker}</p><h2>${titulo}</h2></div><a href="${esc(enlace)}">Ver todo<span class="vh">: ${titulo}</span> →</a></div>${lista.length ? `<ul class="grid" role="list">${lista.map((p) => tarjeta(s, p)).join("")}</ul>` : ""}</div></section>`
      : "";
  const cuerpo = `
<section class="hero"><img src="${IMG}/hero.webp" srcset="${IMG}/hero-800.webp 800w, ${IMG}/hero.webp 1400w" sizes="100vw" width="1400" height="787" loading="eager" fetchpriority="high" alt="Sala amplia con sofá de cuero, cojines y plantas">
<div class="t"><p class="kicker kicker-claro">Mueblería en La Chorrera · Entrega a todo Panamá</p><h1 class="display">Tu casa, bien amueblada.</h1>
<p>Salas, recámaras, colchones y zapateras con precios claros. Muchos vienen en caja: te los llevas hoy mismo.</p>
<div class="ctas"><a class="btn btn-amarillo" href="/shop">Ver el catálogo</a><a class="btn btn-linea" href="${esc(s.waGeneral)}" target="_blank" rel="noopener">Escríbenos por WhatsApp${NUEVA}</a></div></div></section>
<section><div class="c"><ul class="benef" role="list">
<li><strong>Entrega a todo Panamá</strong><span>Te decimos costo y fecha por WhatsApp.</span></li>
<li><strong>Te lo llevas hoy</strong><span>Muchos muebles vienen en caja y caben en tu carro.</span></li>
<li><strong>Míralo en tienda</strong><span>Visítanos en La Chorrera y pruébalo antes de llevártelo.</span></li>
<li><strong>Precios claros</strong><span>Sin letra pequeña. Pregunta sin pena.</span></li></ul></div></section>
<section class="hueso"><div class="c"><div class="cab"><div><p class="kicker">Compra por espacio</p><h2>¿Qué le hace falta a tu casa?</h2></div><a href="/shop">Ver todo el catálogo →</a></div>
<div class="cats">${f.portada.categorias.map((c) => `<a class="cat" href="${esc(c.url)}"><img src="${esc(c.imagen)}" width="800" height="1000" alt="${esc(c.alt)}" loading="lazy" decoding="async"><span>${esc(c.nombre)}</span></a>`).join("")}</div></div></section>
${carril("Lo más buscado", "Precios claros, listos para llevar", "/shop", masBuscados)}
${carril("Para dormir mejor", "Recámaras y colchones", f.portada.para_dormir_url || "/shop", dormir, "hueso")}
<section class="banda"><div class="c"><p class="kicker kicker-claro">Socios D'CASA</p><h2>Suma puntos y gana invitando</h2><ul>
${pp ? `<li><strong>${pp}</strong> ${pp === 1 ? "punto" : "puntos"} por cada dólar que pagas.</li>` : ""}
${padrino && ahijado ? `<li><strong>${miles(padrino)}</strong> puntos por cada amigo que invitas y compra; tu amigo gana <strong>${miles(ahijado)}</strong>.</li>` : ""}
<li>Cámbialos por descuentos y premios en la tienda.</li></ul><div class="ctas"><a class="btn btn-amarillo" href="/socios">Ver mis puntos</a><a class="btn btn-linea" href="/socios/terminos">Cómo funciona</a></div></div></section>
<section><div class="c"><p class="kicker">Preguntas frecuentes</p><h2>Lo que más nos preguntan</h2>
<details><summary>¿Hacen entregas a todo Panamá?</summary><p>Sí, llegamos a todo el país. Cuéntanos tu zona por WhatsApp y te decimos costo y fecha de entrega.</p></details>
<details><summary>¿Cómo sé el precio de un mueble?</summary><p>Está en la tienda en línea. Si tienes dudas, escríbenos por WhatsApp y te confirmamos precio y disponibilidad al momento.</p></details>
<details><summary>¿Qué formas de pago manejan?</summary><p>Transferencia bancaria, Yappy, o pagas al recibir o en la tienda. Escríbenos y te explicamos la que mejor te sirve.</p></details>
<details><summary>¿Me ayudan a saber si el mueble me cabe?</summary><p>Claro. Pásanos las medidas de tu espacio por WhatsApp y te decimos si te queda perfecto o cuál te conviene más.</p></details>
<details><summary>¿Puedo ver los muebles antes de comprar?</summary><p>Sí. Visítanos en La Chorrera o escríbenos y te confirmamos existencias y colores disponibles hoy mismo.</p></details>
</div></section>
<section class="banda"><div class="c"><p class="kicker kicker-claro">Visítanos</p><h2>Te esperamos en La Chorrera</h2><p>${esc(f.empresa.calle)}.</p>
<a class="btn btn-amarillo" href="/visitanos">Cómo llegar y más información</a></div></section>`;
  const precarga = `<link rel="preload" as="image" imagesrcset="${IMG}/hero-800.webp 800w, ${IMG}/hero.webp 1400w" imagesizes="100vw" fetchpriority="high">\n`;
  return {
    ruta: "/",
    html: layout(s, {
      titulo: f.portada.seo.titulo || s.nombre,
      descripcion: f.portada.seo.descripcion || f.tienda.descripcion,
      ruta: "/",
      cuerpo,
      jsonld: [f.sitio.json_ld_tienda],
      precarga,
    }),
  };
}

// ------------------------------------------------------------------ tienda (listados)

function rutaListado(base: string, pagina: number): string {
  return pagina > 1 ? `${base}/page/${pagina}` : base;
}

function listados(s: Sitio): PaginaGenerada[] {
  const f = s.feed;
  const porPagina = Math.max(1, f.sitio.por_pagina || 21);
  const conProductos = s.categorias.filter((c) => s.productosDe(c).length);
  const raices = conProductos.filter((c) => c.padre_id === null || !conProductos.some((x) => x.id === c.padre_id));
  const listas: { base: string; categoria: CategoriaFeed | null; productos: ProductoFeed[] }[] = [
    { base: "/shop", categoria: null, productos: f.productos },
    ...conProductos.map((c) => ({ base: c.url, categoria: c, productos: s.productosDe(c) })),
  ];
  const paginas: PaginaGenerada[] = [];
  for (const lista of listas) {
    const total = Math.max(1, Math.ceil(lista.productos.length / porPagina));
    for (let n = 1; n <= total; n++) {
      const ruta = rutaListado(lista.base, n);
      const actual = lista.categoria?.id ?? null;
      const filtros = [
        `<li><a href="/shop"${actual === null ? ' aria-current="page"' : ""}>Todos</a></li>`,
        ...raices.map(
          (c) => `<li><a href="${esc(c.url)}"${c.id === actual ? ' aria-current="page"' : ""}>${esc(c.nombre)}</a></li>`,
        ),
      ].join("");
      const pag =
        total > 1
          ? `<nav class="pag" aria-label="Páginas">${Array.from({ length: total }, (_, i) => `<a href="${esc(rutaListado(lista.base, i + 1))}"${i + 1 === n ? ' aria-current="page"' : ""}>${i + 1}</a>`).join("")}</nav>`
          : "";
      const nombre = lista.categoria?.nombre ?? "Catálogo";
      const cuerpo = `<section><div class="c">${lista.categoria ? `<nav class="migas" aria-label="Ruta"><a href="/shop">Todos los productos</a> › ${esc(nombre)}</nav>` : ""}<h1>${esc(nombre)}</h1><p class="desde">${lista.productos.length} productos</p>
<ul class="filtros" role="list" aria-label="Categorías">${filtros}</ul>
<h2 class="vh">Productos</h2>${rejilla(s, lista.productos.slice((n - 1) * porPagina, n * porPagina))}${pag}</div></section>`;
      const seo = lista.categoria?.seo;
      paginas.push({
        ruta,
        html: layout(s, {
          titulo: seo?.titulo || `${nombre}${n > 1 ? ` (página ${n})` : ""} | ${s.nombre}`,
          descripcion: seo?.descripcion || f.tienda.descripcion,
          ruta,
          cuerpo,
        }),
      });
    }
  }
  return paginas;
}

// ------------------------------------------------------------------ fichas

function ficha(s: Sitio, p: ProductoFeed): PaginaGenerada {
  const categoria = s.categorias.find((c) => c.id === p.categorias[0]);
  const fotos = [
    imagenProducto(p, { sizes: "(min-width:900px) 640px, 100vw", prioridad: true, grande: true, alt: p.nombre }),
    ...p.galeria.map((url) => `<img src="${esc(url)}" width="512" height="512" alt="" loading="lazy" decoding="async">`),
  ].join("");
  const estado =
    p.disponible === null ? "" : `<p class="estado">${p.disponible ? "Disponible" : "Agotado por ahora: pregúntanos por WhatsApp"}</p>`;
  let compra = "";
  if (p.precio_visible && p.compra === "directa") {
    compra = formularioAgregar(p, "Agregar al carrito");
  } else if (p.precio_visible && p.compra === "variantes") {
    const opciones = p.variantes
      .map(
        (v, i) =>
          `<label><span><input type="radio" name="product_id" value="${v.id}"${i === 0 ? " checked" : ""}${v.disponible === false ? " disabled" : ""}> ${esc(v.nombre)}${v.disponible === false ? " (agotado)" : ""}</span><span class="precio">${esc(dinero(v.precio, p.moneda))}${p.mas_itbms ? ' <span class="itbms">+ ITBMS</span>' : ""}</span></label>`,
      )
      .join("");
    compra = `<form action="${RUTA_AGREGAR}" method="post"><fieldset class="variantes"><legend>Elige una opción</legend>${opciones}</fieldset><button type="submit" class="btn btn-azul" style="width:100%">Agregar al carrito</button></form>`;
  }
  const { valor, desde } = precioMinimo(p);
  const cuerpo = `<div class="c"><nav class="migas" aria-label="Ruta"><a href="/shop">Todos los productos</a>${categoria ? ` › <a href="${esc(categoria.url)}">${esc(categoria.nombre)}</a>` : ""}</nav>
<div class="ficha"><div class="galeria" tabindex="0" role="region" aria-label="Fotos de ${esc(p.nombre)}">${fotos}</div>
<div><h1>${esc(p.nombre)}</h1>${precioHtml(p, valor, desde)}${estado}
<div class="compra"><a class="btn btn-azul" href="${esc(p.whatsapp || s.wa(`Hola D'CASA, me interesa: ${p.nombre}`))}" target="_blank" rel="noopener">Pregunta por este mueble por WhatsApp${NUEVA}</a>${compra}</div>
${p.descripcion_html ? `<div class="desc">${p.descripcion_html}</div>` : p.descripcion_corta ? `<p class="desc">${esc(p.descripcion_corta)}</p>` : ""}
<ul class="sellos" role="list"><li><strong>Entrega a todo Panamá.</strong> Costo y fecha por WhatsApp.</li>
<li><strong>Te lo llevas hoy.</strong> Muchos vienen en caja y caben en tu carro.</li>
<li><strong>Míralo en tienda.</strong> Av. Las Américas, La Chorrera.</li></ul>
${p.codigo ? `<p class="desde">Código ${esc(p.codigo)}</p>` : ""}</div></div></div>`;
  const precioTexto = p.precio_visible ? ` ${dinero(valor, p.moneda)}${p.mas_itbms ? " + ITBMS" : ""}.` : "";
  return {
    ruta: p.url,
    html: layout(s, {
      titulo: p.seo.titulo || `${p.nombre} | ${s.nombre}`,
      descripcion:
        p.seo.descripcion ||
        p.descripcion_corta ||
        `${p.nombre}.${precioTexto} Escríbenos por WhatsApp o visítanos en La Chorrera.`,
      ruta: p.url,
      cuerpo,
      jsonld: p.json_ld,
      precarga: p.imagen
        ? `<link rel="preload" as="image" imagesrcset="${esc(`${p.imagen.image_512} 512w, ${p.imagen.image_1024} 1024w, ${p.imagen.image_1920} 1920w`)}" imagesizes="(min-width:900px) 640px, 100vw" fetchpriority="high">\n`
        : "",
    }),
  };
}

// ------------------------------------------------------------------ páginas fijas

function visitanos(s: Sitio): PaginaGenerada {
  const e = s.feed.empresa;
  const cuerpo = `
<section class="hero compacto"><img src="${IMG}/insp-3.webp" width="640" height="640" alt="" loading="eager" fetchpriority="high">
<div class="t"><p class="kicker kicker-claro">Visítanos</p><h1 class="display">Te esperamos en La Chorrera</h1></div></section>
<section><div class="c"><h2 class="kicker">La tienda</h2><address style="font-style:normal"><strong>${esc(e.nombre || s.nombre)}</strong><br>${esc(e.calle)}<br>${esc(e.ciudad)}, Panamá Oeste</address>
<ul class="sellos" role="list"><li><a href="https://www.google.com/maps/dir/?api=1&amp;destination=${e.latitud}%2C${e.longitud}" target="_blank" rel="noopener">Abrir la ruta en Google Maps${NUEVA}</a></li>
${e.telefono ? `<li><a href="tel:${esc(e.telefono.replace(/[^+\d]/g, ""))}">${esc(e.telefono)}</a></li>` : ""}${e.email ? `<li><a href="mailto:${esc(e.email)}">${esc(e.email)}</a></li>` : ""}
<li><a href="https://www.instagram.com/dcasapty" target="_blank" rel="noopener">@dcasapty${NUEVA}</a></li></ul>
<h2 class="kicker">Antes de venir</h2><p>Escríbenos y te confirmamos el horario, las existencias y los colores disponibles del mueble que te gusta. Muchos vienen en caja: te los llevas hoy mismo.</p>
<a class="btn btn-azul" href="${esc(s.wa("Hola D'CASA, quiero visitarlos en la tienda"))}" target="_blank" rel="noopener">Escríbenos por WhatsApp${NUEVA}</a></div></section>`;
  return {
    ruta: "/visitanos",
    html: layout(s, {
      titulo: `Visítanos | ${s.nombre}`,
      descripcion: `${s.nombre} en La Chorrera: ${e.calle}. Cómo llegar y cómo escribirnos.`,
      ruta: "/visitanos",
      cuerpo,
      jsonld: [s.feed.sitio.json_ld_tienda],
    }),
  };
}

function legal(s: Sitio, ruta: string): PaginaGenerada | null {
  const p = s.feed.paginas[ruta];
  if (!p) return null;
  const cuerpo = `<section><div class="c legal"><p class="kicker">${esc(s.nombre)}</p><h1>${esc(p.titulo)}</h1><p class="desde">Última actualización: ${esc(p.actualizado)}</p>${p.html}</div></section>`;
  return { ruta, html: layout(s, { titulo: `${p.titulo} | ${s.nombre}`, descripcion: p.descripcion, ruta, cuerpo }) };
}

/** Todas las páginas del sitio estático. */
export function renderizarSitio(feed: Feed, opciones: OpcionesRender = {}): PaginaGenerada[] {
  const s = new Sitio(feed, opciones);
  const paginas = [
    portada(s),
    ...listados(s),
    ...feed.productos.filter((p) => s.fichaEstatica(p)).map((p) => ficha(s, p)),
    visitanos(s),
    ...["/privacidad", "/terminos"].map((ruta) => legal(s, ruta)).filter((p): p is PaginaGenerada => !!p),
  ];
  // Una sola página por ruta (la primera gana): un slug repetido no pisa otra página.
  const vistas = new Set<string>();
  return paginas.filter((p) => (vistas.has(p.ruta) ? false : (vistas.add(p.ruta), true)));
}
