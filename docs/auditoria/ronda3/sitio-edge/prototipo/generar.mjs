// Prototipo estático de D'CASA (ronda 3, r3-sitio-edge). SOLO PARA MEDIR, no es el sitio final.
// Genera dist/ a partir de los datos reales del repo (sin inventar textos ni precios):
//   - addons/dcasa_catalogo/data/catalogo.json + static/img/productos/*.jpg  (productos, precios, fotos)
//   - addons/dcasa_socios/data/puntos.json                                    (cifras de socios)
//   - addons/website_dcasa/static/src/img/*.webp                              (hero y categorías actuales)
//   - textos copiados de addons/website_dcasa/views/*.xml
// Uso: npm i && node generar.mjs   (SOLO=XHT022-T-W,ALJ021439 genera solo esas fichas: build de medición rápido)
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import sharp from 'sharp';

const AQUI = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(AQUI, '../../../../..');
const DIST = path.join(AQUI, 'dist');
const CAT = JSON.parse(fs.readFileSync(path.join(REPO, 'addons/dcasa_catalogo/data/catalogo.json'), 'utf8'));
const FOTOS = path.join(REPO, 'addons/dcasa_catalogo/static/img/productos');
const IMG_WEB = path.join(REPO, 'addons/website_dcasa/static/src/img');
const PUNTOS = JSON.parse(fs.readFileSync(path.join(REPO, 'addons/dcasa_socios/data/puntos.json'), 'utf8'));
const BASE = 'https://dcasapty.com'; // CANONICAL_HOST de edge/wrangler.jsonc
const WA = '50760261919'; // +507 6026-1919 (CLAUDE.md); en producción saldría de la configuración del sitio

// Nombres y orden de las categorías: addons/dcasa_catalogo y website_dcasa (product_public_category_data.xml).
const CATEGORIAS = [
  ['recamaras', 'Recámaras'], ['zapateras', 'Zapateras'], ['organizacion', 'Estantes y organización'],
  ['muebles_tv', 'Muebles de TV'], ['oficina', 'Oficina'], ['colchones', 'Colchones'], ['salas', 'Salas'],
];
const NOMBRE_CAT = Object.fromEntries(CATEGORIAS);
const POR_PAGINA = 24;

const productos = CAT.filter((p) => p.fotos && p.fotos.length) // los 11 sin foto no se publican (igual que Odoo)
  .sort((a, b) => a.orden - b.orden);

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const slug = (s) => s.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
const urlProducto = (p) => `/shop/${slug(p.codigo + ' ' + p.nombre_web)}/`;
const precioMin = (p) => Math.min(...Object.values(p.precios));
const dinero = (n) => '$' + n.toFixed(2); // mismo formato que hoy en la tienda ($ 104.99)
const wa = (texto) => `https://wa.me/${WA}?text=${encodeURIComponent(texto)}`;

// ---------------------------------------------------------------- imágenes
const REG = []; // registro de variantes generadas (para medir pesos)
async function variantes(origen, nombre, anchos, { calidadAvif = 50, calidadWebp = 72 } = {}) {
  const meta = await sharp(origen).metadata();
  const out = { ancho: meta.width, alto: meta.height, avif: [], webp: [] };
  for (const w of [...new Set(anchos.map((a) => Math.min(a, meta.width)))]) {
    for (const fmt of ['avif', 'webp']) {
      const rel = `img/${nombre}-${w}.${fmt}`;
      const dest = path.join(DIST, rel);
      if (!fs.existsSync(dest)) {
        const img = sharp(origen).resize({ width: w, withoutEnlargement: true });
        await (fmt === 'avif' ? img.avif({ quality: calidadAvif, effort: 4 }) : img.webp({ quality: calidadWebp })).toFile(dest);
      }
      out[fmt].push(`/${rel} ${w}w`);
      REG.push({ archivo: rel, origen: path.basename(origen), ancho: w, formato: fmt, bytes: fs.statSync(dest).size });
    }
  }
  out.min = `/img/${nombre}-${Math.min(anchos[0], meta.width)}.webp`;
  return out;
}
function picture(v, { alt = '', sizes, lazy = true, prioridad = false, clase = '' }) {
  return `<picture><source type="image/avif" srcset="${v.avif.join(', ')}" sizes="${sizes}">` +
    `<img src="${v.min}" srcset="${v.webp.join(', ')}" sizes="${sizes}" width="${v.ancho}" height="${v.alto}" alt="${esc(alt)}"` +
    `${clase ? ` class="${clase}"` : ''}${lazy ? ' loading="lazy" decoding="async"' : ''}${prioridad ? ' fetchpriority="high"' : ''}></picture>`;
}

// ---------------------------------------------------------------- CSS (en línea: 0 peticiones que bloqueen)
const CSS = `
@font-face{font-family:Anton;src:url(/fonts/anton-400.woff2) format("woff2");font-display:swap}
@font-face{font-family:Oswald;src:url(/fonts/oswald-500.woff2) format("woff2");font-weight:500;font-display:optional}
@font-face{font-family:Inter;src:url(/fonts/inter-400.woff2) format("woff2");font-weight:400;font-display:optional}
@font-face{font-family:Inter;src:url(/fonts/inter-700.woff2) format("woff2");font-weight:700;font-display:optional}
:root{--azul:#1340B1;--amarillo:#FED00F;--navy:#0E2A6B;--hueso:#F4F1EA;--tinta:#1B2233;--gris:#4A5163}
*{box-sizing:border-box}html,body{overflow-x:clip}h1,h2,p{overflow-wrap:anywhere}html{scroll-padding-top:80px}
body{margin:0;font:400 16px/1.55 Inter,system-ui,sans-serif;color:var(--tinta);background:#fff}
a{color:var(--azul)}img{max-width:100%;height:auto;display:block}
h1,h2,.display{font-family:Anton,Oswald,Impact,sans-serif;font-weight:400;text-transform:uppercase;letter-spacing:.01em;line-height:1.05;margin:0 0 .5rem}
h3,.kicker,.btn,nav a{font-family:Oswald,Inter,sans-serif;font-weight:500}
.c{max-width:1200px;margin:0 auto;padding:0 16px}
.skip{position:absolute;left:-999px}.skip:focus{left:16px;top:8px;background:#fff;padding:8px;z-index:9}
:focus-visible{outline:3px solid var(--navy);outline-offset:2px}
.anuncios{background:var(--azul);color:#fff;font-size:.85rem}.anuncios .c{display:flex;flex-wrap:wrap;gap:.25rem 1rem;justify-content:space-between;padding:.4rem 16px}
.anuncios a{color:var(--amarillo);text-decoration:none;font-weight:700}
header.top{background:#fff;border-bottom:1px solid #e6e3dc;position:sticky;top:0;z-index:5}
header.top .c{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;min-height:64px;gap:.25rem 1rem}
header.top nav{display:flex;gap:.9rem;flex-wrap:wrap}header.top nav a{color:var(--navy);text-decoration:none;text-transform:uppercase;font-size:.95rem;padding:.6rem 0}
.logo img{height:44px;width:auto}
.btn{display:inline-flex;align-items:center;gap:.5rem;padding:.85rem 1.4rem;border-radius:.9rem;text-decoration:none;text-transform:uppercase;letter-spacing:.02em;border:2px solid transparent;min-height:48px}
.btn-azul{background:var(--azul);color:#fff}.btn-amarillo{background:var(--amarillo);color:var(--navy)}.btn-linea{border-color:#fff;color:#fff}
.hero{position:relative;background:var(--navy);color:#fff;overflow:hidden}
.hero picture img{width:100%;height:clamp(420px,72vh,640px);object-fit:cover;opacity:.55}
.hero .t{position:absolute;inset:auto 0 0 0;padding:2rem 16px 2.5rem;max-width:1200px;margin:0 auto}
.hero h1{font-size:clamp(2.6rem,9vw,5.6rem)}.hero p{max-width:36rem;font-size:1.1rem}
.kicker{text-transform:uppercase;letter-spacing:.08em;font-size:.85rem;color:var(--azul);margin:0 0 .25rem}.hero .kicker,.banda .kicker{color:var(--amarillo)}
.ctas{display:flex;flex-wrap:wrap;gap:.75rem;margin-top:1rem}
section{padding:2.5rem 0}.hueso{background:var(--hueso)}
.benef{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:1rem;list-style:none;padding:0;margin:0}
.benef strong{display:block;color:var(--navy)}.benef span{color:var(--gris);font-size:.95rem}
.cab{display:flex;justify-content:space-between;align-items:end;gap:1rem;margin-bottom:1rem;flex-wrap:wrap}
.cats{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:.75rem}
.cat{position:relative;border-radius:1rem;overflow:hidden;color:#fff;text-decoration:none;background:var(--navy)}
.cat img{aspect-ratio:4/5;object-fit:cover;opacity:.75}.cat span{position:absolute;left:.75rem;bottom:.6rem;font:500 1.05rem Oswald,sans-serif;text-transform:uppercase}
.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:.9rem;list-style:none;padding:0;margin:0}
@media(min-width:768px){.grid{grid-template-columns:repeat(4,1fr)}}
.card{display:flex;flex-direction:column;height:100%;border:1px solid #e6e3dc;border-radius:1rem;overflow:hidden;background:#fff}
.card .m{background:var(--hueso)}.card .m img{aspect-ratio:4/5;object-fit:contain;width:100%}
.card .b{padding:.7rem .8rem 1rem;display:flex;flex-direction:column;gap:.35rem;flex:1}
.card h3{font-size:1rem;margin:0;line-height:1.25}.card h3 a{color:var(--tinta);text-decoration:none}
.precio{font:700 1.15rem Inter,sans-serif;color:var(--navy);margin:0}.desde{font-weight:400;font-size:.85rem;color:var(--gris)}
.card .btn{margin-top:auto;justify-content:center;padding:.6rem .8rem;font-size:.9rem}
.filtros{display:flex;gap:.5rem;overflow-x:auto;padding:0 0 .75rem;margin:0 0 1rem;list-style:none}
.filtros a{white-space:nowrap;display:inline-block;padding:.5rem .9rem;border:2px solid var(--azul);border-radius:999px;text-decoration:none;font:500 .9rem Oswald,sans-serif;text-transform:uppercase}
.filtros a[aria-current]{background:var(--azul);color:#fff}
.pag{display:flex;gap:.5rem;justify-content:center;margin-top:1.5rem}.pag a{padding:.5rem .9rem;border:1px solid #ccc;border-radius:.5rem;text-decoration:none}.pag a[aria-current]{background:var(--azul);color:#fff;border-color:var(--azul)}
.ficha{display:grid;gap:1.5rem}@media(min-width:900px){.ficha{grid-template-columns:1.2fr 1fr}}
.galeria{display:flex;overflow-x:auto;scroll-snap-type:x mandatory;gap:.5rem;background:var(--hueso);border-radius:1rem}
.galeria picture{flex:0 0 100%;scroll-snap-align:start}.galeria img{width:100%;aspect-ratio:4/5;object-fit:contain}
.ficha h1{font-size:clamp(1.8rem,5vw,2.6rem);color:var(--navy)}
.tabla{border-collapse:collapse;margin:.5rem 0}.tabla td,.tabla th{padding:.35rem .9rem .35rem 0;text-align:left;border-bottom:1px solid #e6e3dc}
.sellos{list-style:none;padding:0;color:var(--gris)}.sellos strong{color:var(--navy)}
.banda{background:var(--azul);color:#fff}.banda a.btn-amarillo{color:var(--navy)}
details{border-bottom:1px solid #e6e3dc;padding:.75rem 0}summary{cursor:pointer;font-weight:700;color:var(--navy)}
footer{background:var(--navy);color:#fff;padding:2rem 0 5rem;font-size:.95rem}footer a{color:#fff}footer .kicker{color:var(--amarillo)}
.wa{position:fixed;right:16px;bottom:16px;width:56px;height:56px;border-radius:50%;background:var(--azul);display:grid;place-items:center;border:2px solid #fff;z-index:6}
.wa svg{width:28px;height:28px;fill:#fff}
.vh{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.migas{font-size:.9rem;margin:1rem 0}.migas a{color:var(--gris)}
`.replace(/\n/g, '');

const ICONO_WA = '<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M16 3a13 13 0 0 0-11.2 19.6L3 29l6.6-1.7A13 13 0 1 0 16 3zm0 23.6a10.6 10.6 0 0 1-5.4-1.5l-.4-.2-3.9 1 1-3.8-.2-.4A10.6 10.6 0 1 1 16 26.6zm5.8-7.9c-.3-.2-1.9-.9-2.2-1s-.5-.2-.7.2-.8 1-1 1.2-.4.2-.7.1a8.7 8.7 0 0 1-4.3-3.8c-.3-.6.3-.5.9-1.7.1-.2 0-.4 0-.5l-1-2.4c-.3-.6-.5-.5-.7-.5h-.6a1.2 1.2 0 0 0-.9.4 3.6 3.6 0 0 0-1.1 2.7 6.3 6.3 0 0 0 1.3 3.3 14.4 14.4 0 0 0 5.5 4.9c2 .9 2.8.9 3.8.8a3.2 3.2 0 0 0 2.1-1.5 2.6 2.6 0 0 0 .2-1.5c-.1-.2-.3-.3-.6-.4z"/></svg>';
const NUEVA = '<span class="vh"> (se abre en una pestaña nueva)</span>';

function layout({ titulo, descripcion, canonica, cuerpo, jsonld = [], precarga = '' }) {
  return `<!doctype html><html lang="es-419"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(titulo)}</title><meta name="description" content="${esc(descripcion)}">
<link rel="canonical" href="${BASE}${canonica}"><meta name="theme-color" content="#1340B1">
<link rel="icon" href="/img/favicon.png">
<link rel="preload" href="/fonts/anton-400.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/fonts/inter-400.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/fonts/oswald-500.woff2" as="font" type="font/woff2" crossorigin>
${precarga}<style>${CSS}</style>
${jsonld.map((j) => `<script type="application/ld+json">${JSON.stringify(j).replace(/</g, '\\u003c')}</script>`).join('')}
</head><body><a class="skip" href="#contenido">Ir al contenido</a>
<div class="anuncios" role="region" aria-label="Avisos de D'CASA"><div class="c"><span>Entrega a todo Panamá</span>
<a href="${wa("Hola D'CASA, quiero información")}" target="_blank" rel="noopener">Escríbenos por WhatsApp${NUEVA}</a></div></div>
<header class="top"><div class="c"><a class="logo" href="/" aria-label="D'CASA Panamá, inicio"><img src="/img/logo-200.webp" width="200" height="91" alt="D'CASA"></a>
<nav aria-label="Principal"><a href="/shop/">Catálogo</a><a href="/socios">Socios D'CASA</a><a href="/visitanos">Visítanos</a></nav></div></header>
<main id="contenido">${cuerpo}</main>
<footer><div class="c"><p class="kicker">D'CASA Panamá</p>
<address style="font-style:normal">Avenida Las Américas, Urbanización Santa Clara, Local 4550 PB-1, La Chorrera<br>
<a href="tel:+50760261919">+507 6026-1919</a> · <a href="mailto:info@dcasapty.com">info@dcasapty.com</a></address>
<p>D'CASA Panamá · RUC 155779346-2-2026 DV7</p></div></footer>
<a class="wa" href="${wa("Hola D'CASA, quiero información")}" target="_blank" rel="noopener" aria-label="Escríbenos por WhatsApp (se abre en una pestaña nueva)">${ICONO_WA}</a>
</body></html>`;
}

function tarjeta(p, v, i = 99) {
  const varios = Object.keys(p.precios).length > 1;
  return `<li><article class="card"><a class="m" href="${urlProducto(p)}" tabindex="-1" aria-hidden="true">${picture(v, { sizes: '(min-width:1200px) 285px, (min-width:768px) 24vw, 48vw', lazy: i > 1, prioridad: i === 0 })}</a>
<div class="b"><h3><a href="${urlProducto(p)}">${esc(p.nombre_web)}</a></h3>
<p class="precio">${varios ? '<span class="desde">desde </span>' : ''}${dinero(precioMin(p))}</p>
<a class="btn btn-azul" href="${wa(`Hola D'CASA, me interesa: ${p.nombre_web}`)}" target="_blank" rel="noopener">Pídelo por WhatsApp<span class="vh">: ${esc(p.nombre_web)} (se abre en una pestaña nueva)</span></a></div></article></li>`;
}

async function main() {
  const solo = process.env.SOLO ? process.env.SOLO.split(',') : null;
  fs.mkdirSync(path.join(DIST, 'img'), { recursive: true });
  fs.mkdirSync(path.join(DIST, 'fonts'), { recursive: true });
  // Fuentes autoalojadas (OFL, paquetes @fontsource; subconjunto latin = incluye á é í ó ú ñ ¿ ¡)
  const F = path.join(AQUI, 'node_modules/@fontsource');
  for (const [src, dst] of [['anton/files/anton-latin-400-normal.woff2', 'anton-400'], ['oswald/files/oswald-latin-500-normal.woff2', 'oswald-500'],
    ['inter/files/inter-latin-400-normal.woff2', 'inter-400'], ['inter/files/inter-latin-700-normal.woff2', 'inter-700']]) {
    fs.copyFileSync(path.join(F, src), path.join(DIST, 'fonts', dst + '.woff2'));
  }
  await sharp(path.join(REPO, 'addons/dcasa_base/static/img/logo.png')).resize({ width: 200 }).webp({ quality: 85 }).toFile(path.join(DIST, 'img/logo-200.webp'));
  fs.copyFileSync(path.join(IMG_WEB, 'favicon.png'), path.join(DIST, 'img/favicon.png'));

  // Variantes: tarjeta (320/640) de la foto principal de cada producto.
  const vt = {};
  for (const p of productos) vt[p.codigo] = await variantes(path.join(FOTOS, p.fotos[0]), slug(p.fotos[0].replace(/\.jpg$/i, '')), [320, 640]);
  const hero = await variantes(path.join(IMG_WEB, 'hero.webp'), 'hero', [640, 960, 1400], { calidadAvif: 45 });
  const vcat = {};
  for (const [k] of CATEGORIAS) if (fs.existsSync(path.join(IMG_WEB, `cat-${k}.webp`))) vcat[k] = await variantes(path.join(IMG_WEB, `cat-${k}.webp`), `cat-${k}`, [300, 600]);

  const cuenta = Object.fromEntries(CATEGORIAS.map(([k]) => [k, productos.filter((p) => p.categoria === k).length]));
  const tienda = {
    '@context': 'https://schema.org', '@type': 'FurnitureStore', '@id': `${BASE}/#tienda`, name: "D'CASA Panamá", url: BASE,
    telephone: '+507 6026-1919', email: 'info@dcasapty.com', currenciesAccepted: 'USD',
    address: { '@type': 'PostalAddress', streetAddress: 'Avenida Las Américas, Urbanización Santa Clara, Local 4550 PB-1', addressLocality: 'La Chorrera', addressRegion: 'Panamá Oeste', addressCountry: 'PA' },
    geo: { '@type': 'GeoCoordinates', latitude: 8.8765881, longitude: -79.7867962 },
  };

  // ---------------- Portada (textos de homepage_templates.xml; sin «Financiamiento»: SW-03 pendiente)
  const masBuscados = productos.slice(0, 8);
  const dormir = productos.filter((p) => ['recamaras', 'colchones'].includes(p.categoria)).slice(8, 16);
  const pp = PUNTOS.acumulacion?.puntosPorDolar, padrino = PUNTOS.referido?.puntosAlPadrino, ahijado = PUNTOS.referido?.puntosAlAhijado;
  const portada = `
<section class="hero" style="padding:0">${picture(hero, { alt: 'Sala amplia con sofá de cuero, cojines y plantas', sizes: '100vw', lazy: false, prioridad: true })}
<div class="t"><p class="kicker">Mueblería en La Chorrera · Entrega a todo Panamá</p><h1 class="display">Tu casa, bien amueblada.</h1>
<p>Salas, recámaras, colchones y zapateras con precios claros. Muchos vienen en caja: te los llevas hoy mismo.</p>
<div class="ctas"><a class="btn btn-amarillo" href="/shop/">Ver el catálogo</a><a class="btn btn-linea" href="${wa("Hola D'CASA, quiero información")}" target="_blank" rel="noopener">Escríbenos por WhatsApp${NUEVA}</a></div></div></section>
<section><div class="c"><ul class="benef" role="list">
<li><strong>Entrega a todo Panamá</strong><span>Te decimos costo y fecha por WhatsApp.</span></li>
<li><strong>Te lo llevas hoy</strong><span>Muchos muebles vienen en caja y caben en tu carro.</span></li>
<li><strong>Precios claros</strong><span>Sin letra pequeña. Pregunta sin pena.</span></li></ul></div></section>
<section class="hueso"><div class="c"><div class="cab"><div><p class="kicker">Compra por espacio</p><h2>¿Qué le hace falta a tu casa?</h2></div><a href="/shop/">Ver todo el catálogo →</a></div>
<div class="cats">${CATEGORIAS.filter(([k]) => cuenta[k]).map(([k, n]) => `<a class="cat" href="/shop/${slug(k)}/">${vcat[k] ? picture(vcat[k], { sizes: '(min-width:768px) 180px, 45vw' }) : '<div style="aspect-ratio:4/5"></div>'}<span>${esc(n)}</span></a>`).join('')}</div></div></section>
<section><div class="c"><div class="cab"><div><p class="kicker">Precios claros, listos para llevar</p><h2>Lo más buscado</h2></div><a href="/shop/">Ver todo →</a></div>
<ul class="grid" role="list">${masBuscados.map((p) => tarjeta(p, vt[p.codigo])).join('')}</ul></div></section>
<section class="hueso"><div class="c"><div class="cab"><div><p class="kicker">Recámaras y colchones</p><h2>Para dormir mejor</h2></div><a href="/shop/recamaras/">Ver todo →</a></div>
<ul class="grid" role="list">${dormir.map((p) => tarjeta(p, vt[p.codigo])).join('')}</ul></div></section>
<section class="banda"><div class="c"><p class="kicker">Socios D'CASA</p><h2>Suma puntos y gana invitando</h2><ul>
${pp ? `<li><strong>${pp}</strong> ${pp === 1 ? 'punto' : 'puntos'} por cada dólar que pagas.</li>` : ''}
${padrino && ahijado ? `<li><strong>${padrino.toLocaleString('en-US')}</strong> puntos por cada amigo que invitas y compra; tu amigo gana <strong>${ahijado.toLocaleString('en-US')}</strong>.</li>` : ''}
<li>Cámbialos por descuentos y premios en la tienda.</li></ul><div class="ctas"><a class="btn btn-amarillo" href="/socios">Ver mis puntos</a></div></div></section>
<section><div class="c"><p class="kicker">Preguntas frecuentes</p><h2>Lo que más nos preguntan</h2>
<details><summary>¿Hacen entregas a todo Panamá?</summary><p>Sí, llegamos a todo el país. Cuéntanos tu zona por WhatsApp y te decimos costo y fecha de entrega.</p></details>
<details><summary>¿Cómo sé el precio de un mueble?</summary><p>Está en la tienda en línea. Si tienes dudas, escríbenos por WhatsApp y te confirmamos precio y disponibilidad al momento.</p></details>
<details><summary>¿Me ayudan a saber si el mueble me cabe?</summary><p>Claro. Pásanos las medidas de tu espacio por WhatsApp y te decimos si te queda perfecto o cuál te conviene más.</p></details>
<details><summary>¿Puedo ver los muebles antes de comprar?</summary><p>Sí. Visítanos en La Chorrera o escríbenos y te confirmamos existencias y colores disponibles hoy mismo.</p></details>
</div></section>
<section class="banda"><div class="c"><p class="kicker">Visítanos</p><h2>Te esperamos en La Chorrera</h2><p>Avenida Las Américas, Urbanización Santa Clara, Local 4550 PB-1.</p>
<a class="btn btn-amarillo" href="/visitanos">Cómo llegar y más información</a></div></section>`;
  const precargaHero = `<link rel="preload" as="image" type="image/avif" imagesrcset="${hero.avif.join(', ')}" imagesizes="100vw" fetchpriority="high">\n`;
  escribir('index.html', layout({ titulo: "D'CASA Panamá · Muebles en La Chorrera", descripcion: "Tienda en línea de D'CASA Panamá: salas, recámaras, colchones, zapateras, estantes y escritorios con precios claros. Entrega a todo Panamá desde La Chorrera.", canonica: '/', cuerpo: portada, jsonld: [tienda], precarga: precargaHero }));

  // ---------------- Tienda: /shop/ y /shop/<categoria>/ paginadas (filtros = enlaces, sin JS)
  const listas = [['', 'Todos', productos], ...CATEGORIAS.filter(([k]) => cuenta[k]).map(([k, n]) => [k, n, productos.filter((p) => p.categoria === k)])];
  for (const [k, nombre, lista] of listas) {
    const paginas = Math.ceil(lista.length / POR_PAGINA);
    for (let i = 0; i < paginas; i++) {
      const base = `/shop/${k ? slug(k) + '/' : ''}`;
      const ruta = base + (i ? `pagina/${i + 1}/` : '');
      const filtros = listas.map(([k2, n2]) => `<li><a href="/shop/${k2 ? slug(k2) + '/' : ''}"${k2 === k ? ' aria-current="page"' : ''}>${esc(n2)}</a></li>`).join('');
      const pag = paginas > 1 ? `<nav class="pag" aria-label="Páginas">${Array.from({ length: paginas }, (_, j) => `<a href="${base}${j ? `pagina/${j + 1}/` : ''}"${j === i ? ' aria-current="page"' : ''}>${j + 1}</a>`).join('')}</nav>` : '';
      const cuerpo = `<section><div class="c"><h1>${k ? esc(nombre) : 'Catálogo'}</h1><p class="desde">${lista.length} productos</p>
<ul class="filtros" role="list" aria-label="Categorías">${filtros}</ul>
<h2 class="vh">Productos</h2><ul class="grid" role="list">${lista.slice(i * POR_PAGINA, (i + 1) * POR_PAGINA).map((p, j) => tarjeta(p, vt[p.codigo], j)).join('')}</ul>${pag}</div></section>`;
      escribir(ruta.slice(1) + 'index.html', layout({ titulo: `${k ? nombre + ' · ' : ''}Catálogo | D'CASA Panamá`, descripcion: "Tienda en línea de D'CASA Panamá: salas, recámaras, colchones, zapateras, estantes y escritorios con precios claros. Entrega a todo Panamá desde La Chorrera.", canonica: ruta, cuerpo }));
    }
  }

  // ---------------- Fichas (todas; galería completa solo en SOLO o en todas si no se indica)
  // Con SOLO=cod1,cod2 solo se generan esas fichas (medición rápida); sin SOLO, todas con su galería.
  for (const p of productos.filter((x) => !solo || solo.includes(x.codigo))) {
    const fotos = p.fotos;
    const vs = [];
    for (const f of fotos) vs.push(await variantes(path.join(FOTOS, f), slug(f.replace(/\.jpg$/i, '')), [480, 960, 1440]));
    const varios = Object.keys(p.precios).length > 1;
    const precios = varios
      ? `<table class="tabla"><caption class="vh">Precio por tamaño</caption><tbody>${Object.entries(p.precios).map(([t, v]) => `<tr><th scope="row">${esc(t)}</th><td class="precio">${dinero(v)}</td></tr>`).join('')}</tbody></table>`
      : `<p class="precio" style="font-size:1.6rem">${dinero(precioMin(p))}</p>`;
    const cuerpo = `<div class="c"><nav class="migas" aria-label="Ruta"><a href="/shop/">Catálogo</a> › <a href="/shop/${slug(p.categoria)}/">${esc(NOMBRE_CAT[p.categoria])}</a></nav>
<div class="ficha"><div class="galeria" tabindex="0" aria-label="Fotos de ${esc(p.nombre_web)}">${vs.map((v, i) => picture(v, { alt: i ? '' : p.nombre_web, sizes: '(min-width:900px) 640px, 100vw', lazy: i > 0, prioridad: i === 0 })).join('')}</div>
<div><h1>${esc(p.nombre_web)}</h1>${precios}
${p.medidas ? `<h2 class="kicker">Medidas</h2><p>${esc(p.medidas)}</p>` : ''}
${p.combo ? `<p>También en combo ${esc(p.combo)}. Pídelo por WhatsApp.</p>` : ''}
<a class="btn btn-azul" style="width:100%;justify-content:center" href="${wa(`Hola D'CASA, me interesa: ${p.nombre_web}`)}" target="_blank" rel="noopener">Pregunta por este mueble por WhatsApp${NUEVA}</a>
<ul class="sellos" role="list"><li><strong>Entrega a todo Panamá.</strong> Costo y fecha por WhatsApp.</li>
<li><strong>Te lo llevas hoy.</strong> Muchos vienen en caja y caben en tu carro.</li>
<li><strong>Míralo en tienda.</strong> Av. Las Américas, La Chorrera.</li></ul>
<p class="desde">Código ${esc(p.codigo)}</p></div></div></div>`;
    const ld = {
      '@context': 'https://schema.org', '@type': 'Product', name: p.nombre_web, sku: p.codigo, url: BASE + urlProducto(p),
      image: vs.map((v) => BASE + v.webp[v.webp.length - 1].split(' ')[0]),
      brand: { '@type': 'Brand', name: "D'CASA Panamá" },
      // Sin «availability»: el inventario está «sin confirmar» (docs/CATALOGO_REVISAR.md); no se inventa.
      offers: varios
        ? { '@type': 'AggregateOffer', priceCurrency: 'USD', lowPrice: precioMin(p), highPrice: Math.max(...Object.values(p.precios)), offerCount: Object.keys(p.precios).length, seller: { '@id': `${BASE}/#tienda` } }
        : { '@type': 'Offer', priceCurrency: 'USD', price: precioMin(p), url: BASE + urlProducto(p), seller: { '@id': `${BASE}/#tienda` } },
    };
    const migas = { '@context': 'https://schema.org', '@type': 'BreadcrumbList', itemListElement: [
      { '@type': 'ListItem', position: 1, name: 'Catálogo', item: `${BASE}/shop/` },
      { '@type': 'ListItem', position: 2, name: NOMBRE_CAT[p.categoria], item: `${BASE}/shop/${slug(p.categoria)}/` },
      { '@type': 'ListItem', position: 3, name: p.nombre_web }] };
    escribir(urlProducto(p).slice(1) + 'index.html', layout({ titulo: `${p.nombre_web} | D'CASA Panamá`, descripcion: `${p.nombre_web}. ${dinero(precioMin(p))}. Pregunta por WhatsApp o visítanos en La Chorrera.`, canonica: urlProducto(p), cuerpo, jsonld: [ld, migas] }));
  }
  // ---------------- /visitanos (textos de la página actual; mapa como enlace, sin iframe de Google: SW-01)
  const vis = await variantes(path.join(IMG_WEB, 'insp-3.webp'), 'insp-3', [480, 640]);
  escribir('visitanos/index.html', layout({ titulo: "Visítanos | D'CASA Panamá", descripcion: "D'CASA Panamá en La Chorrera: Avenida Las Américas, Urbanización Santa Clara, Local 4550 PB-1. Cómo llegar y cómo escribirnos.", canonica: '/visitanos', jsonld: [tienda], cuerpo: `
<section class="hero" style="padding:0">${picture(vis, { alt: '', sizes: '100vw', lazy: false, prioridad: true })}
<div class="t"><p class="kicker">Visítanos</p><h1 class="display">Te esperamos en La Chorrera</h1></div></section>
<section><div class="c"><h2 class="kicker">La tienda</h2><address style="font-style:normal"><strong>D'CASA Panamá</strong><br>Avenida Las Américas, Urbanización Santa Clara,<br>Local 4550 PB-1, La Chorrera, Panamá Oeste</address>
<ul class="sellos" role="list"><li><a href="https://www.google.com/maps/dir/?api=1&amp;destination=8.8765881%2C-79.7867962" target="_blank" rel="noopener">Abrir la ruta en Google Maps${NUEVA}</a></li>
<li><a href="tel:+50760261919">+507 6026-1919</a></li><li><a href="mailto:info@dcasapty.com">info@dcasapty.com</a></li>
<li><a href="https://www.instagram.com/dcasapty" target="_blank" rel="noopener">@dcasapty${NUEVA}</a></li></ul>
<h2 class="kicker">Antes de venir</h2><p>Escríbenos y te confirmamos el horario, las existencias y los colores disponibles del mueble que te gusta. Muchos vienen en caja: te los llevas hoy mismo.</p>
<a class="btn btn-azul" href="${wa("Hola D'CASA, quiero visitarlos en la tienda")}" target="_blank" rel="noopener">Escríbenos por WhatsApp${NUEVA}</a></div></section>` }));
  escribir('robots.txt', `User-agent: *\nAllow: /\nSitemap: ${BASE}/sitemap.xml\n`);
  const urls = ['/', '/shop/', '/visitanos', ...listas.filter(([k]) => k).map(([k]) => `/shop/${slug(k)}/`), ...productos.filter((x) => !solo || solo.includes(x.codigo)).map(urlProducto)];
  escribir('sitemap.xml', `<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${urls.map((u) => `<url><loc>${BASE}${u}</loc></url>`).join('')}</urlset>`);
  escribir('404.html', layout({ titulo: "Página no encontrada | D'CASA Panamá", descripcion: '', canonica: '/404', cuerpo: '<section><div class="c"><h1>Esta página no existe</h1><p><a class="btn btn-azul" href="/shop/">Ver el catálogo</a></p></div></section>' }));
  escribir('_headers', '/img/*\n  Cache-Control: public, max-age=31536000, immutable\n/fonts/*\n  Cache-Control: public, max-age=31536000, immutable\n');
  fs.writeFileSync(path.join(AQUI, '..', 'variantes-imagenes.json'), JSON.stringify(resumenImagenes(), null, 1));
  console.log('listo:', productos.length, 'productos;', REG.length, 'variantes');
}
function escribir(rel, contenido) { const f = path.join(DIST, rel); fs.mkdirSync(path.dirname(f), { recursive: true }); fs.writeFileSync(f, contenido); }
function resumenImagenes() {
  const vistos = new Map(); for (const r of REG) vistos.set(r.archivo, r);
  const filas = [...vistos.values()];
  const por = {}; for (const r of filas) { const k = `${r.formato}-${r.ancho >= 1400 ? '1400+' : r.ancho}`; (por[k] ||= { n: 0, bytes: 0 }); por[k].n++; por[k].bytes += r.bytes; }
  for (const v of Object.values(por)) v.mediaKB = +(v.bytes / v.n / 1024).toFixed(1);
  return { archivos: filas.length, totalMB: +(filas.reduce((a, r) => a + r.bytes, 0) / 1048576).toFixed(2), porFormatoYAncho: por };
}
main().catch((e) => { console.error(e); process.exit(1); });
