# Ronda 6 — Diseño del sitio: regresiones y pulido

Fecha: 2026-10-02. Alcance: `addons/website_dcasa` (Odoo 19). No se tocó `edge/` ni
`addons/dcasa_tienda_borde`.

Pedido de la dueña: el sitio «se dañó mucho». Le gusta el estilo de **/socios** y la **píldora de
Odoo** (logo, CATÁLOGO · SOCIOS D'CASA · VISÍTANOS, carrito, búsqueda, cuenta y el botón azul
«Escríbenos») y lo quiere en todo el sitio. Se quejó de la foto del pie «azulosa», del velo que
lavaba la foto de la portada y de «muchas cosas dañadas».

Método: Odoo local con todos los módulos y el catálogo real (237 productos), capturas con
Playwright a 1440 y 390 px de 11 páginas, Lighthouse 12 móvil (3 corridas por página y modo,
mediana) detrás de un proxy con gzip (como Cloudflare), y `git log -p` de `website_dcasa`.
La base «antes» es una copia de la misma base con el código de `bf28cbd`.

## 1. Regresiones encontradas

| # | Qué se veía | Dónde | Origen |
|---|---|---|---|
| R1 | **Velo azul que lava las fotos** (portada y categorías) | Tienda estática del borde: `.hero{background:navy}` + `img{opacity:.55}` y `.cat img{opacity:.75}` sobre navy | `c7458c7` (Fase 2, `edge/src/tienda/estilo.ts`). Ya apagada; no se tocó |
| R2 | **Foto de la portada apagada**: en Odoo, foto al 45 % sobre negro. Con una foto clara (sala blanca) queda gris y sucia | `dcasa.scss` `.o_dcasa_hero_media img {opacity:.45}` | `40d435d` (v2.1, «hero oscuro») |
| R3 | **Píldora distinta según la página**: oscura sobre las fotos (/, /socios, /visitanos, contacto) y blanca con sombra en tienda, ficha, carrito, legales, cuenta y Black Weekend | `dcasa.scss` (vidrio claro por defecto) | `40d435d`/v2.2 (diseño), agravado por las páginas nuevas sin cabecera propia: `35ec12d` (legales), `fa78864` (Black Weekend) |
| R4 | **/black-weekend: franja blanca** entre la píldora clara y la banda negra | `black_weekend_templates.xml` sin «cabecera encima» | `fa78864` |
| R5 | **Fotos de producto como tiras angostas** con dos bandas grises: el catálogo es casi todo vertical (158 fotos 9:16, 112 3:4) y la tarjeta es 1:1 con `contain` (y en la portada además `multiply` + 8 % de relleno, que las agrisaba) | tarjetas de /shop, carriles de la portada, Black Weekend | `41fbb60` (v2) y `12b0c52` (tarjeta 1:1 con srcset) |
| R6 | **Legales con aspecto de borrador**: subtítulos en Anton en minúscula (Anton es solo para titulares en caja alta), sin cabecera, enlaces del texto sin subrayar (Lighthouse `link-in-text-block`) | `legal_templates.xml` | `35ec12d`, `c7458c7` |
| R7 | **Cuenta (/web/login)**: formulario suelto; Odoo lo pinta oculto y lo muestra con JavaScript → el pie salta ~500 px (**CLS 0,44** en móvil con red lenta) | plantilla de Odoo | Odoo 19 (sin reserva de alto) |
| R8 | **Logo de 56 KB** (PNG) en cada página con prioridad alta, compitiendo con la foto principal. Ya existía el WebP de 3-7 KB pero solo lo usaba el borde | `website.logo` | `c7458c7` creó el WebP sin usarlo en Odoo |
| R9 | **Barra de avisos en dos líneas en el celular** (70 px menos de foto) | `.o_dcasa_anuncios_inner` | v2 |
| R10 | **Filtro de refracción animado** sobre la foto: el `<animate>` del ruido repinta la píldora sin parar | `animaciones.js` | v2.3 |

Lo que **no** era regresión: las fuentes autoalojadas cargan bien (Anton, Oswald e Inter en todas
las páginas), el `<picture>` WebP de `/dcasa/img` no deforma nada (`display: contents`) y el pie de
Odoo **no tiene ninguna foto**: es azul sólido. La «foto azulosa» venía de la tienda del borde
(R1). Ahora un test lo fija (sin `<img>`, `background-image`, `opacity` ni filtros en el pie).

## 2. Qué se corrigió

- **La píldora de /socios en todas las páginas** (R3). Siempre vidrio ahumado en tinta con texto y
  foco blancos, mismo logo, mismos enlaces, carrito, búsqueda, cuenta y «Escríbenos»:
  - sobre fondo claro casi opaca (tinta al 92 %: blanco ≈ 14:1);
  - sobre una foto o fondo oscuro, al 66 % (blanco ≥ 4,6:1 aun sobre blanco puro), sin el brillo
    extra del vidrio claro;
  - las páginas con «cabecera encima» nacen ya con la variante oscura (sin destello al cargar);
  - hamburguesa blanca en el celular.
- **Portada sin velo** (R2): la foto con sus colores reales (`opacity: 1`, sin filtro ni capa
  encima). El contraste lo da una **placa navy plana** (blanco 13,6:1; el CTA amarillo queda sobre
  navy, como manda la regla del amarillo). En el celular, primero la foto y debajo la placa: el
  texto nunca tapa la foto. Ver la decisión pendiente en §5.
- **Cabeceras como la de /socios** para las páginas que no tenían (R4, R6, R7): plantilla
  `website_dcasa.cabecera_pagina` en privacidad, términos y cuenta; /black-weekend sube su banda
  negra bajo la píldora.
- **Fotos de producto 3:4 que llenan la tarjeta** (R5) en /shop, categorías, carriles de la
  portada y Black Weekend. A una 9:16 solo se le recorta aire de arriba y abajo (revisado sobre las
  fotos reales). Las anchas (muebles de TV, estantes con medidas) no se recortan: `animaciones.js`
  las marca `.o_dcasa_foto_ancha` y van enteras. El cuadro no cambia de tamaño: sin CLS.
- **Legales legibles** (R6): subtítulos en Oswald azul en caja alta (como /socios/terminos), cuerpo
  a 17 px / 1,7 y ≈ 70 caracteres por línea, enlaces subrayados.
- **Cuenta** (R7): formulario en la tarjeta de /socios y alto reservado: CLS ≈ 0.
- **Logo en WebP** (R8) mientras sea el de fábrica (se compara el `checksum` del adjunto con
  `dcasa_base/static/img/logo.png`); si la dueña sube otro desde el editor, se muestra el suyo.
- **Avisos en una línea** en el celular (R9).
- **Sin animación del filtro** (R10); la refracción queda solo en el vidrio.

## 3. Mejoras («a la excelencia», sin perder la identidad)

- Jerarquía: titulares Anton solo en caja alta; subtítulos Oswald; cuerpo Inter. Nombres de
  producto de /shop en Inter 600 (antes Oswald condensada, cansaba en dos líneas).
- Accesibilidad (Lighthouse 100 en portada, socios, privacidad, cuenta y Black Weekend; 98 en la ficha y 96 en /shop por marcado del núcleo):
  - «Agregar al carrito» de Black Weekend: el nombre accesible empieza por el texto visible
    (`label-content-name-mismatch`);
  - orden de titulares en /black-weekend (h1 → h2 → h3);
  - ficha: la cantidad tiene nombre («Cantidad») y teclado numérico;
  - cuenta: destino del «Saltar al contenido», botón del ojo con nombre, sin `tabindex="1"`.
- Rendimiento: logo 56 → 3-7 KB; precarga de la foto de la portada; fuera las precargas de
  FontAwesome e Inter (Anton sigue precargada: es el titular); «Compra por espacio» a 400 px en el
  celular; foto de /socios con versión de 480 px; foto principal de la ficha a tiempo y en WebP
  (`website_dcasa.ficha_foto_prioritaria`); sin repintado continuo de la píldora.
- Lo que queda de Odoo y no se tocó (núcleo): los radios de categorías sin `label` y
  `role="article"` en un `<form>` de /shop, el `h6` de atributos en la ficha.

## 4. Métricas antes / después

Lighthouse 12 móvil, mediana de 3, Odoo local con gzip delante, mismas bases de datos.
«Real» = estrangulamiento real de DevTools (4G lenta 1,6 Mb/s, RTT 150 ms, CPU 4×); «simulado» =
el modelo de Lighthouse por defecto.

**Estrangulamiento real (4G lenta + CPU 4×)**

| Página | LCP antes → después | CLS antes → después | Rend. antes → después | Accesib. antes → después | Peso antes → después |
|---|---|---|---|---|---|
| Portada | 3,40 s → **2,74 s** | 0,001 → 0,001 | 54 → 64 | 100 → 100 | 1 764 → 1 453 KB |
| /shop | 3,27 s → **2,68 s** | 0,006 → 0,009 | 59 → 68 | 96 → 96 | 1 215 → 1 114 KB |
| Ficha (con variantes) | 4,89 s → **2,96 s** | 0,004 → 0,005 | 51 → 67 | 95 → 98 | 1 200 → 1 097 KB |
| /black-weekend | 4,07 s → **3,29 s** | 0,021 → 0,027 | 55 → 66 | 98 → **100** | 1 198 → 1 129 KB |
| /socios | 3,44 s → **2,71 s** | 0,005 → 0,006 | 62 → 68 | 100 → 100 | 1 129 → 1 082 KB |
| /privacidad | 3,02 s → **2,59 s** | 0,001 → 0,007 | 69 → 70 | 96 → **100** | 1 076 → 1 065 KB |
| Cuenta (/web/login) | 3,00 s → **2,56 s** | **0,440 → 0,001** | 44 → 68 | 89 → **100** | 1 075 → 1 048 KB |

**Simulado (modelo por defecto de Lighthouse)**: el LCP queda en 7-9 s antes y después en casi
todas las páginas (una de las corridas de la portada dio 2,6 s). Lo explica el CSS y el
JavaScript de Odoo: el modelo cuenta antes de la foto todo lo que el navegador pidió hasta pintar,
y en este servidor eso incluye el paquete diferido de Odoo (583 KB gzip, ≈ 58 % sin usar en cada
página) y su CSS (136 KB gzip, ≈ 90 % sin usar). Bajar eso exige recortar paquetes del núcleo de
Odoo (fuera de esta ronda, propuesta en §5). En producción delante va Cloudflare (Brotli y la
caché del borde).

Playwright sin estrangular (1440 y 390 px, 11 páginas): CLS < 0,03 en todas (la cuenta pasó de
0,04-0,18 a 0,001), sin desborde horizontal y las tres fuentes cargadas en todas las páginas.

Qué movió el LCP: la precarga de la foto de la portada, el logo en WebP, quitar la precarga de
FontAwesome (76 KB, de Odoo) e Inter (36 KB) que competían con el CSS que bloquea el pintado, las
fotos de «Compra por espacio» a 400 px en el celular (−200 KB) y, en la ficha, la foto principal
pedida a tiempo (Odoo le ponía `loading="lazy"`: 2,1 s de espera) en WebP al ancho justo.

**Objetivo LCP < 2,5 s en 4G lenta: no se alcanza todavía** (2,56-3,29 s). Lo que falta es el
CSS de Odoo; ver §5.

## 5. Decisiones para la dueña

- **Placa navy en la portada.** En la v2.1 pidió «sin placa azul»; ahora pidió «sin velo». Las dos
  cosas a la vez no dan contraste AA para el texto blanco sobre una foto clara. Se eligió una placa
  **navy** (no el azul de marca), plana, más chica que la de la v2 y que en el celular va debajo de
  la foto. Si prefiere otra cosa, se cambia en un solo lugar (`.o_dcasa_hero:not(.o_dcasa_hero_compacto)`
  en `dcasa.scss`).
- **Fotos de producto recortadas a 3:4.** Solo se recorta fondo de estudio; las fotos anchas van
  enteras. Si algún producto pierde algo importante, la foto se puede reemplazar por una 3:4.
- **Precarga de la foto de la portada**: si se cambia esa foto desde el editor, hay que apagar la
  vista «D'CASA: precarga de la foto de la portada» o actualizar sus rutas.
- **Siguiente paso de rendimiento (no hecho)**: el CSS de Odoo (136 KB gzip, 90 % sin usar) bloquea
  el primer pintado. Opciones: CSS crítico en línea para la cabecera y el hero, o sacar del paquete
  del sitio los módulos de Odoo que la tienda no usa. Es trabajo sobre el empaquetado del núcleo y
  conviene medirlo en staging con Cloudflare delante.

## 6. Tests

`addons/website_dcasa/tests/test_diseno.py`:
- la píldora (avisos, logo WebP, Catálogo · Socios D'CASA · Visítanos, carrito, búsqueda, cuenta y
  «Escríbenos») está en portada, tienda, categoría, ficha, carrito, Black Weekend, socios,
  visítanos, contacto, privacidad, términos y cuenta;
- las páginas con foto o fondo oscuro llevan la cabecera encima; tienda, ficha y carrito no;
- el pie no tiene fotos, fondos, opacidad ni filtros;
- con otro logo, se respeta el de la dueña;
- la foto de la portada se precarga (solo en la portada), sin precarga de FontAwesome, «Compra por
  espacio» con versión de 400 px y la foto de la ficha «eager», con prioridad alta y srcset;
- en Chrome: la foto de la portada sin opacidad, filtro ni capa encima; el texto en la placa navy;
  la píldora de /shop es la de /socios y el pie no tiene imágenes ni filtros.

`test_seo_y_promesas.test_precarga_de_las_fuentes_del_primer_pantallazo` se actualizó: ahora
exige la precarga de Anton y que Inter y FontAwesome **no** se precarguen.

Corrida: `website_dcasa,dcasa_catalogo,dcasa_tienda_borde,dcasa_base` en base limpia y `ruff check addons`.

## 7. Capturas

En `capturas/` (WebP, ancho 1080 en escritorio). «Antes» es `bf28cbd`; «después», esta ronda.

| Página | Antes | Después |
|---|---|---|
| Portada, escritorio | ![](capturas/portada-1440-antes.webp) | ![](capturas/portada-1440-despues.webp) |
| Portada, celular | ![](capturas/portada-390-antes.webp) | ![](capturas/portada-390-despues.webp) |
| Tienda, escritorio | ![](capturas/tienda-1440-antes.webp) | ![](capturas/tienda-1440-despues.webp) |
| Tienda, celular | ![](capturas/tienda-390-antes.webp) | ![](capturas/tienda-390-despues.webp) |
| Ficha, celular | ![](capturas/ficha-390-antes.webp) | ![](capturas/ficha-390-despues.webp) |
| Black Weekend | ![](capturas/black-weekend-1440-antes.webp) | ![](capturas/black-weekend-1440-despues.webp) |
| Privacidad, celular | ![](capturas/privacidad-390-antes.webp) | ![](capturas/privacidad-390-despues.webp) |
| Cuenta | ![](capturas/cuenta-1440-antes.webp) | ![](capturas/cuenta-1440-despues.webp) |
| Pie (sin cambios: azul sólido, sin foto) | ![](capturas/pie-1440-antes.webp) | ![](capturas/pie-1440-despues.webp) |
