/**
 * CSS de la tienda estática (en línea en cada página: 0 peticiones que bloqueen el render).
 * Parte del prototipo medido en docs/auditoria/ronda3/sitio-edge (99-100 en Lighthouse móvil).
 *
 * Marca (CLAUDE.md): azul #1340B1, amarillo #FED00F SOLO sobre azul, navy o negro (.hero, .banda,
 * .anuncios, footer, .bw de Black Weekend), texto sobre blanco en azul o navy; Anton/Oswald/Inter;
 * plano: sin degradados ni sombras.
 */
export const FUENTES = {
  anton: "/website_dcasa/static/src/fonts/anton-latin.woff2",
  inter: "/website_dcasa/static/src/fonts/inter-latin-var.woff2",
  oswald: "/website_dcasa/static/src/fonts/oswald-latin-var.woff2",
} as const;

/** Clases que pintan amarillo: solo pueden vivir dentro de un contenedor azul o navy. */
export const CLASES_AMARILLAS = ["btn-amarillo", "kicker-claro", "bw-titulo"] as const;
/** Contenedores con fondo azul, navy o negro (donde el amarillo sí puede ir). */
export const FONDOS_OSCUROS = ["hero", "banda", "anuncios", "pie", "bw"] as const;

export const CSS = `
@font-face{font-family:Anton;src:url(${FUENTES.anton}) format("woff2");font-display:swap}
@font-face{font-family:Oswald;src:url(${FUENTES.oswald}) format("woff2");font-weight:400 700;font-display:optional}
@font-face{font-family:Inter;src:url(${FUENTES.inter}) format("woff2");font-weight:400 700;font-display:optional}
:root{--azul:#1340B1;--amarillo:#FED00F;--navy:#0B1F4D;--hueso:#F4F1EA;--tinta:#1B2233;--gris:#4A5163;--linea:#E6E3DC}
*{box-sizing:border-box}html,body{overflow-x:clip}h1,h2,p{overflow-wrap:anywhere}html{scroll-padding-top:80px}
body{margin:0;font:400 16px/1.55 Inter,system-ui,sans-serif;color:var(--tinta);background:#fff}
a{color:var(--azul)}img{max-width:100%;height:auto;display:block}
h1,h2,.display{font-family:Anton,Oswald,Impact,sans-serif;font-weight:400;text-transform:uppercase;letter-spacing:.01em;line-height:1.05;margin:0 0 .5rem;color:var(--navy)}
h3,.kicker,.btn,nav a{font-family:Oswald,Inter,sans-serif;font-weight:500}
.c{max-width:1200px;margin:0 auto;padding:0 16px}
.skip{position:absolute;left:-999px}.skip:focus{left:16px;top:8px;background:#fff;padding:8px;z-index:9}
:focus-visible{outline:3px solid var(--navy);outline-offset:2px}
.anuncios{background:var(--azul);color:#fff;font-size:.85rem}.anuncios .c{display:flex;flex-wrap:wrap;gap:.25rem 1rem;justify-content:space-between;padding:.4rem 16px}
.anuncios a{color:var(--amarillo);text-decoration:none;font-weight:700}
header.top{background:#fff;border-bottom:1px solid var(--linea);position:sticky;top:0;z-index:5}
header.top .c{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;min-height:64px;gap:.25rem 1rem}
header.top nav{display:flex;gap:.9rem;flex-wrap:wrap}header.top nav a{color:var(--navy);text-decoration:none;text-transform:uppercase;font-size:.95rem;padding:.6rem 0}
.logo img{height:44px;width:auto}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:.5rem;padding:.85rem 1.4rem;border-radius:.9rem;text-decoration:none;text-transform:uppercase;letter-spacing:.02em;border:2px solid transparent;min-height:48px;font-size:1rem;cursor:pointer}
.btn-azul{background:var(--azul);color:#fff}.btn-borde{border-color:var(--azul);color:var(--azul);background:#fff}
.btn-amarillo{background:var(--amarillo);color:var(--navy)}.btn-linea{border-color:#fff;color:#fff}
.hero{position:relative;background:var(--navy);color:#fff;overflow:hidden;padding:0}
.hero img{width:100%;height:clamp(420px,72vh,640px);object-fit:cover;opacity:.55}
.hero.compacto img{height:clamp(260px,40vh,380px)}
.hero .t{position:absolute;inset:auto 0 0 0;padding:2rem 16px 2.5rem;max-width:1200px;margin:0 auto}
.hero h1{font-size:clamp(2.6rem,9vw,5.6rem);color:#fff}.hero.compacto h1{font-size:clamp(2rem,7vw,3.6rem)}.hero p{max-width:36rem;font-size:1.1rem}
.kicker{text-transform:uppercase;letter-spacing:.08em;font-size:.85rem;color:var(--azul);margin:0 0 .25rem}.kicker-claro{color:var(--amarillo)}
.ctas{display:flex;flex-wrap:wrap;gap:.75rem;margin-top:1rem}
section{padding:2.5rem 0}.hueso{background:var(--hueso)}
.benef{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:1rem;list-style:none;padding:0;margin:0}
.benef strong{display:block;color:var(--navy)}.benef span{color:var(--gris);font-size:.95rem}
.cab{display:flex;justify-content:space-between;align-items:end;gap:1rem;margin-bottom:1rem;flex-wrap:wrap}
.cats{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:.75rem}
.cat{position:relative;border-radius:1rem;overflow:hidden;color:#fff;text-decoration:none;background:var(--navy)}
.cat img{aspect-ratio:4/5;object-fit:cover;opacity:.75;width:100%}.cat span{position:absolute;left:.75rem;bottom:.6rem;font:500 1.05rem Oswald,sans-serif;text-transform:uppercase}
.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:.9rem;list-style:none;padding:0;margin:0}
@media(min-width:768px){.grid{grid-template-columns:repeat(4,1fr)}}
.card{display:flex;flex-direction:column;height:100%;border:1px solid var(--linea);border-radius:1rem;overflow:hidden;background:#fff}
.card .m picture,.galeria picture{display:contents}.card .m{background:var(--hueso);display:block}.card .m img{aspect-ratio:1/1;object-fit:contain;width:100%}
.card .b{padding:.7rem .8rem 1rem;display:flex;flex-direction:column;gap:.35rem;flex:1}
.card h3{font-size:1rem;margin:0;line-height:1.25}.card h3 a{color:var(--tinta);text-decoration:none}
.precio{font:700 1.15rem Inter,sans-serif;color:var(--navy);margin:0}.itbms,.desde{font-weight:400;font-size:.85rem;color:var(--gris)}
.acciones{margin-top:auto;display:flex;gap:.4rem}.acciones form{flex:1;margin:0}.acciones .btn{width:100%;padding:.6rem .8rem;font-size:.9rem}
.acciones .wa{flex:0 0 48px;padding:0;border-color:var(--azul)}
.filtros{display:flex;gap:.5rem;overflow-x:auto;padding:0 0 .75rem;margin:0 0 1rem;list-style:none}
.filtros a{white-space:nowrap;display:inline-block;padding:.5rem .9rem;border:2px solid var(--azul);border-radius:999px;text-decoration:none;font:500 .9rem Oswald,sans-serif;text-transform:uppercase}
.filtros a[aria-current]{background:var(--azul);color:#fff}
.pag{display:flex;gap:.5rem;justify-content:center;margin-top:1.5rem;flex-wrap:wrap}.pag a{padding:.5rem .9rem;border:1px solid #ccc;border-radius:.5rem;text-decoration:none}.pag a[aria-current]{background:var(--azul);color:#fff;border-color:var(--azul)}
.ficha{display:grid;gap:1.5rem}@media(min-width:900px){.ficha{grid-template-columns:1.2fr 1fr}}
.galeria{display:flex;overflow-x:auto;scroll-snap-type:x mandatory;gap:.5rem;background:var(--hueso);border-radius:1rem}
.galeria img{flex:0 0 100%;scroll-snap-align:start;width:100%;aspect-ratio:1/1;object-fit:contain}
.ficha h1{font-size:clamp(1.8rem,5vw,2.6rem)}
.ficha .precio{font-size:1.6rem}
.variantes{border:0;padding:0;margin:1rem 0}.variantes legend{font:500 1rem Oswald,sans-serif;text-transform:uppercase;color:var(--navy);margin-bottom:.5rem}
.variantes label{display:flex;justify-content:space-between;gap:1rem;padding:.7rem .9rem;border:2px solid var(--linea);border-radius:.75rem;margin-bottom:.5rem;cursor:pointer}
.variantes input{accent-color:var(--azul)}.variantes label:has(input:checked){border-color:var(--azul)}
.compra{display:grid;gap:.75rem;margin:1rem 0}.compra .btn{width:100%}
.estado{display:inline-block;font-weight:700;color:var(--navy)}
.sellos{list-style:none;padding:0;color:var(--gris)}.sellos strong{color:var(--navy)}
.desc{margin:1rem 0}.desc img{height:auto}
.banda{background:var(--azul);color:#fff}.banda h2{color:#fff}.banda a{color:#fff}.banda a.btn-amarillo{color:var(--navy)}
.legal{max-width:48rem}.legal h2{font-size:1.6rem;margin-top:1.5rem}
details{border-bottom:1px solid var(--linea);padding:.75rem 0}summary{cursor:pointer;font-weight:700;color:var(--navy)}
footer.pie{background:var(--navy);color:#fff;padding:2rem 0 5rem;font-size:.95rem}footer.pie a{color:#fff}footer.pie .kicker{color:var(--amarillo)}
footer.pie .cols{display:grid;gap:1rem;grid-template-columns:repeat(auto-fit,minmax(200px,1fr))}footer.pie ul{list-style:none;padding:0;margin:0}footer.pie li{padding:.2rem 0}
.wa-flotante{position:fixed;right:16px;bottom:16px;width:56px;height:56px;border-radius:50%;background:var(--azul);display:grid;place-items:center;border:2px solid #fff;z-index:6}
.wa-flotante svg,.wa svg{width:26px;height:26px;fill:currentColor}.wa-flotante{color:#fff}.wa{color:var(--azul)}
.vh{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.migas{font-size:.9rem;margin:1rem 0}.migas a{color:var(--gris)}
.bw{background:#000;color:#fff}.bw p{max-width:44rem}.bw .bw-titulo{color:var(--amarillo);font-size:clamp(2.5rem,8vw,5rem)}.bw h1.bw-titulo{font-size:clamp(3rem,11vw,7rem)}
.bw a.btn-amarillo{color:var(--navy)}.bw :focus-visible{outline-color:var(--amarillo)}.bw .card :focus-visible{outline-color:var(--azul)}
.bw-card{color:var(--tinta);padding:.6rem}.bw-card .b p{max-width:none}.combo{margin:0;color:var(--navy);font-size:.95rem}.combo strong{font-family:Oswald,Inter,sans-serif}
.bw-acciones{margin-top:auto;display:grid;gap:.4rem}.bw-acciones form{margin:0}.bw-acciones .btn{width:100%;padding:.6rem .8rem;font-size:.9rem}
.card .m{position:relative}.bw-etiqueta{position:absolute;top:.5rem;left:.5rem;background:#000;color:var(--amarillo);font:600 .75rem/1 Oswald,Inter,sans-serif;letter-spacing:.08em;text-transform:uppercase;padding:.4rem .6rem;border-radius:.4rem}
`.replace(/\n/g, "");
