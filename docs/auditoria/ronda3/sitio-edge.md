# Ronda 3 · `r3-sitio-edge` — Sitio público y tienda: rendimiento al menor costo

Agente `r3-sitio-edge` · 2026-10-01 · Informe INCREMENTAL (se completa a medida que hay mediciones).

## Resumen ejecutivo

- **Medido, no supuesto.** Odoo 19 real con los 8 módulos, Lighthouse 12.8 móvil, mediana de 3 corridas: el sitio
  actual da **39-55 puntos**, LCP **8,2-10,8 s**, TBT 0,3-1,4 s y pesa **1,05-1,93 MB** (536 KB son JS de Odoo).
- **Prototipo estático** con los mismos datos (catálogo, precios, fotos y textos reales): **99-100 puntos**, LCP
  **1,6-2,2 s**, TBT ≤ 45 ms, CLS 0, **138-251 KB**, 0 JS, 1 solo origen.
- **El HTML de Odoo no se puede cachear tal cual**: manda `Set-Cookie` de sesión a cada anónimo y el CSRF va atado a
  la sesión (probado: el «Agregar» de la portada da 400 con un token de otra sesión). Cachearlo exige cambios y aun
  así no arregla el peso ni el TBT, ni deja dormir a Odoo.
- **Recomendación: C (mixto)**: catálogo público en Workers Static Assets (**$0**, peticiones gratis e ilimitadas
  según la doc oficial), pedido por WhatsApp; Odoo como ERP + `/socios` detrás del Worker, ya **a demanda**. Es lo
  que más rinde y lo que más ahorra (permite bajar el contenedor de 24/7 a demanda).
- Arreglos inmediatos aunque no se cambie nada: hero con `loading="eager"` (Odoo lo vuelve `lazy`), quitar el cron que
  impide dormir, autoalojar fuentes. Bloqueante de contenido: el ITBMS.
- Sin usuarios reales no hay Core Web Vitals de campo: todo es laboratorio.

## 1. Línea base medida (Odoo 19 real, 2026-10-01)

**Método.** Base `r3_web` (copia de `dcasa_test`: 8 módulos, 202 plantillas, 188 publicadas), Odoo con
`--workers=0 --proxy-mode` (igual que `docker/entrypoint.sh:39-43`) en `:8180`. Delante, un proxy mínimo
(`sitio-edge/herramientas/servir.js proxy`) que **comprime con Brotli** las respuestas de texto, como haría el
borde de Cloudflare: Odoo/werkzeug no comprime (medido: `/` 124 KB → 10,6 KB; `web.assets_frontend_lazy.min.js`
2,49 MB → 539 KB). Sin ese proxy la primera medición daba 4,5 MB y puntuación 26: hubiera sido injusto con Odoo.
Lighthouse 12.8.2, perfil **móvil por defecto** (Moto G Power emulado, 4G lenta simulada, CPU ×4), Chromium 1194
headless, **3 corridas por página, se reporta la mediana**. La máquina tiene 4 vCPU compartidas con otros 7 agentes
(carga 4-8 durante las corridas): las cifras absolutas son pesimistas y ruidosas; lo comparable es la diferencia
con el prototipo medido igual. Las fuentes de Google salen por el proxy de la sesión (Chrome confía solo en la
clave de su CA, `--ignore-certificate-errors-spki-list=<hash de esa CA>`; no se desactivó TLS).
**No hay Core Web Vitals de campo**: el sitio no tiene usuarios reales (CrUX vacío); todo es de laboratorio.

| Página | Perf. (3 corridas) | LCP | FCP | TBT | CLS | Speed Index | TTFB (lab) | Peso | Peticiones | Orígenes |
|---|---|---|---|---|---|---|---|---|---|---|
| `/` | **41** (41/37/45) | 8,96 s | 3,93 s | 939 ms | 0 | 6,20 s | 83 ms | 1 354 KB | 25 | 4 |
| `/shop` | **39** (41/39/38) | 10,77 s | 4,09 s | 812 ms | **0,126** | 6,40 s | 255 ms | 1 929 KB | 29 | 4 |
| Ficha (cama twin XHT022-T-W) | **39** (37/39/49) | 8,33 s | 3,86 s | 1 398 ms | 0 | 6,41 s | 248 ms | 1 420 KB | 24 | 4 |
| `/visitanos` | **55** (59/55/38) | 8,17 s | 4,23 s | 329 ms | 0 | 6,05 s | 62 ms | 1 053 KB | 23 | 5 |

Accesibilidad / buenas prácticas / SEO de Lighthouse: `/` 100/100/100 · `/shop` 96/100/92 · ficha 95/100/85 ·
`/visitanos` 100/100/92. TTFB del servidor en caliente (curl, mediana de 9, sin cookie): `/` 50 ms, `/shop` 282 ms,
ficha 178 ms, `/visitanos` 53 ms (local, sin red; en Cloudflare se suma la ida y vuelta al contenedor y el arranque
en frío si duerme: eso lo mide `r3-odoo-medicion`).

**Qué pesa (transferido, comprimido, mediana de la portada):**

| Tipo | KB | De dónde |
|---|---|---|
| JavaScript | **536** | `web.assets_frontend_lazy.min.js` (2,49 MB sin comprimir, ~1,5 MB sin usar según Lighthouse) + `frontend_minimal` |
| Imágenes | 396 (portada) · 970 (`/shop`) · 462 (ficha) | WebP propios bien dimensionados en la portada; en `/shop` y la ficha, `image_1024`/`image_512` JPEG de Odoo |
| Fuentes | 168 | Font Awesome 4.7 (76 KB) + odoo_ui_icons + Anton/Oswald/Inter desde `fonts.gstatic.com` |
| CSS | 120 | `web.assets_frontend.min.css` (1 MB sin comprimir; Lighthouse estima ~103 KB sin usar) + 3 hojas de Google Fonts |
| `website/translations` (fetch) | 88 | 405 KB sin comprimir: traducciones del front pedidas por JS en **cada** página |

**Diagnóstico** (auditorías de Lighthouse en la corrida mediana):
- El LCP no es culpa del servidor: en `/shop` el desglose es TTFB 8 % · **retraso de carga 70 % (5,0 s)** ·
  carga 12 % · render 10 %. La imagen del primer producto se descubre tarde, detrás del CSS que bloquea
  (ahorro estimado 1,3 s) y del JS.
- TBT 0,8-1,4 s: evaluar ~2,5 MB de JS de Odoo (interacciones, OWL, wishlist, comparador, chat de visitante…)
  en un teléfono medio.
- CLS 0,126 en `/shop`: el culpable es `#o_wsale_pager` (el paginador se desplaza cuando cargan las imágenes de
  la grilla). Es el #27/#28 de AUDITORIA_UX que `sitio-web` dejó «por medir»: **confirmado**.
- `/visitanos`: el LCP es la foto del hero (`insp-3.webp`) y sale con `loading="lazy"` en el HTML servido
  aunque la plantilla (`homepage_templates.xml`, página Visítanos) no lo pone: lo agrega el post-proceso de
  imágenes del sitio de Odoo. Una imagen LCP perezosa retrasa el LCP.
- Cada página manda `Set-Cookie: session_id` y `frontend_lang` a un anónimo y no manda `Cache-Control`:
  ver §2.A (no se puede cachear tal cual).
- Hallazgos menores verificados en el HTML servido: JSON-LD `Organization` de Odoo con
  `"name": "D&#39;CASA Panamá"` (entidad HTML dentro de JSON: Google leerá el texto literal `&#39;`) y
  `"url": "http://localhost:8169"` (en producción hay que fijar `web.base.url`/dominio del sitio); migas
  `"All Products"` sin traducir; el `Product` de la ficha sí sale con `availability: InStock` (SW-13 queda
  verificado: no sale `OutOfStock`).

Datos: `sitio-edge/lighthouse/linea-base-odoo.json` (medianas por página) y `linea-base-odoo.md`.

## 2. Estrategias para el sitio público (con documentación oficial)

### Fuentes oficiales usadas (MCP `search_cloudflare_documentation`, consultado 2026-10-01)

| Hecho | Fuente (Last updated) |
|---|---|
| Peticiones a Static Assets **gratis e ilimitadas** en Free y Paid; Workers Paid $5/mes con 10 M peticiones + 30 M ms CPU incluidos, +$0,30/M y +$0,02/M ms; Free 100 000 peticiones/día y 10 ms CPU | https://developers.cloudflare.com/workers/platform/pricing/ (2026-08-28) · https://developers.cloudflare.com/workers/platform/limits/ |
| Static Assets: 20 000 archivos por versión (Free) / 100 000 (Paid), 25 MiB por archivo, `_headers` 100 reglas | https://developers.cloudflare.com/workers/platform/limits/#static-assets |
| Por defecto el asset se sirve **sin invocar** el Worker; `run_worker_first` (bool o lista de rutas, máx. 100) para que el Worker vaya antes en rutas concretas | https://developers.cloudflare.com/workers/static-assets/ · …/static-assets/routing/worker-script/ · …/wrangler/configuration/ |
| **Workers Cache** (`"cache": {"enabled": true}`, Wrangler ≥ 4.69): respeta `Cache-Control` con `stale-while-revalidate` asíncrono, `Cache-Tag` y `ctx.cache.purge({tags})`; **al activarlo, cada petición se cobra como petición de Worker, incluidos los Static Assets** (que normalmente son gratis); los HIT no gastan CPU; la purga desde el Worker usa siempre los límites del plan Free | https://developers.cloudflare.com/workers/cache/ · …/workers/cache/configuration/ · …/workers/cache/purge/ · …/workers/cache/limitations/ |
| Cache API (`caches.default`, lo que usa hoy `edge/src/handler.ts`): `stale-while-revalidate` **no** se soporta con `cache.match/put`; `cache.delete` purga solo en el centro de datos local | https://developers.cloudflare.com/cache/concepts/cache-control/ · https://developers.cloudflare.com/workers/reference/how-the-cache-works/ |
| Purga por URL, prefijo, host, **etiqueta** y todo: **en todos los planes** desde 2025-04-01. Free: 800 URL/s; etiquetas/prefijo/host: 5 peticiones/min, cubeta 25, 100 operaciones por petición | https://developers.cloudflare.com/changelog/post/2025-04-01-purge-for-all/ · https://developers.cloudflare.com/cache/how-to/purge-cache/ · …/purge-by-tags/ (2026-08-21) |
| Por defecto Cloudflare **no cachea HTML** (DYNAMIC) ni respuestas con `Set-Cookie`; una Cache Rule «Eligible for cache» lo habilita | https://developers.cloudflare.com/cache/concepts/default-cache-behavior/ (2026-09-14) · …/cache/troubleshooting/investigating-uncached-responses/ |
| KV: Free 100 000 lecturas y 1 000 escrituras/día; Paid 10 M lecturas + 1 M escrituras/mes, 1 GB. D1: Free 5 M filas leídas y 100 000 escritas/día, 5 GB (se aplica desde 2026-09-01); Paid 25 000 M leídas, 50 M escritas, 5 GB | https://developers.cloudflare.com/workers/platform/pricing/ · …/changelog/post/2026-09-01-d1-free-tier-limit-enforcement/ |
| Queues en el plan Free: 10 000 operaciones/día, retención 24 h | https://developers.cloudflare.com/changelog/post/2026-02-04-queues-free-plan/ |
| R2: 10 GB-mes, 1 M Clase A y 10 M Clase B gratis/mes; luego $0,015/GB-mes, $4,50/M y $0,36/M; egreso gratis | https://developers.cloudflare.com/r2/pricing/ (2026-08-07) |
| Images (transformaciones): Free 5 000 transformaciones únicas/mes (al pasarse, error 9422, sin cobro); Paid $0,50 por 1 000 adicionales; `format=auto` cuenta una sola vez; el binding también se cobra por transformación única desde 2026-07-01 | https://developers.cloudflare.com/images/pricing/ (dateModified 2026-07-08) · …/changelog/post/2026-07-01-binding-unique-transformations/ |
| Containers (costo de mantener Odoo despierto): ver `ronda3/cf-plataforma.md` (standard-1 24/7 ≈ $32-38/mes; standard-2 ≈ $47-58; el cron `*/10` impide dormir) | https://developers.cloudflare.com/containers/platform/pricing/ (2026-08-28), citado por `r3-cf-plataforma` |

### A. Odoo sigue renderizando; el Worker cachea el HTML de anónimos

**Qué hay que cambiar para que funcione** (medido en §1 y en la bitácora):
1. Odoo manda `Set-Cookie: session_id` y `frontend_lang` a **todo** visitante, y ningún `Cache-Control`. El Worker
   tendría que, para `GET` de `/`, `/shop*`, fichas y `/visitanos` **sin** cookie `session_id`: pedir a Odoo,
   **quitar `Set-Cookie`**, poner `Cache-Control: public, s-maxage=…, stale-while-revalidate=…` y `Cache-Tag`
   (`producto-<id>`, `categoria-<id>`, `sitio`). Con cookie de sesión (carrito, cliente con cuenta, socio): siempre al origen.
2. **CSRF**: el token va en el HTML y está atado a la sesión (`vendor/odoo/odoo/http.py:1971-1981`). Probado: el
   formulario sin JS `/dcasa/carrito/agregar` con un token de otra sesión → **400 «Session expired (invalid CSRF
   token)»**. En cambio el «Agregar al carrito» de Odoo por JSON-RPC (`/shop/cart/add`, `type='jsonrpc'`) funcionó
   desde un cliente nuevo sin token (devolvió `cart_quantity: 1`), y `/website/form/*` es `csrf=False`
   (`vendor/odoo/addons/website/controllers/form.py:31`). O sea: hay que cambiar el «Agregar» de un clic de la portada
   (`homepage_templates.xml`, `tarjeta_producto`) a JSON-RPC o a un enlace a la ficha, o reescribir el token en el
   borde (imposible sin sesión).
3. El HTML cacheado lleva el contador de carrito en 0 y «Inicia sesión»: aceptable para anónimos.
4. Con `caches.default` (lo que ya usa `edge/src/handler.ts`) no hay `stale-while-revalidate` y la purga es
   local por centro de datos. Hay que pasar a **Workers Cache** (`cache.enabled`), que sí trae SWR asíncrono y purga
   por etiqueta global, pero entonces **todas** las peticiones del Worker se cobran como peticiones (hoy ya pasan
   todas por el Worker porque no hay Static Assets: no cambia nada en la práctica). Alternativa sin Worker en medio:
   Cache Rules de zona (HTML «Eligible for cache», bypass si hay cookie `session_id`) + purga por URL/tag desde Odoo.
5. Purga al cambiar un producto: una acción automática de Odoo en `product.template` (write de precio, nombre,
   publicado, foto) que llame a la API de purga con la etiqueta `producto-<id>` y `categoria-<id>`. Con el plan
   Free alcanza: 5 purgas/min con cubeta de 25 y 100 etiquetas por purga.

**Rendimiento esperado.** Un HIT elimina el TTFB del contenedor (y su arranque en frío) pero **no** cambia lo que
pesa la página: siguen los 536 KB de JS, el CSS de 1 MB sin comprimir, Font Awesome y Google Fonts. El LCP de
laboratorio de §1 está dominado por el retraso de carga y el render en el teléfono, no por el TTFB (TTFB = 8 % del
LCP de `/shop`). Estimación: LCP 9-11 s → 8-10 s, TBT igual, puntuación 40-55. **No llega a «bueno».**

**Costo.** $0 extra de Workers con hasta 100 000 peticiones/día en Free; ~25 peticiones por vista ⇒ unas 4 000
vistas/día antes de necesitar Paid ($5). El costo dominante sigue siendo el contenedor de Odoo, y **no permite que
Odoo duerma de verdad**: cada miss (caché fría por centro de datos, página nueva, bot que rastrea 188 fichas, carrito,
checkout, `/socios`, `/web/login`) lo despierta (1-3 s de arranque del contenedor + arranque de Odoo; lo mide
`r3-odoo-medicion`). `r3-cf-plataforma` ya confirmó: sin sacar el sitio de Odoo, «a demanda» converge a 24/7.

**Qué se pierde.** Nada de Odoo (constructor, checkout, cuentas, `/socios` siguen igual). **Esfuerzo**: 1-2 días
(reglas del Worker + quitar cookie + cambiar el «Agregar» + acción de purga + tests de `edge/`). **Riesgo**: servir
a un cliente una página con datos de otro si la regla de bypass por cookie falla (hay que testearlo como se hizo con
`isCacheableResponse`).

### B. Catálogo generado al borde (Static Assets) con datos exportados de Odoo; pedido por WhatsApp

**Cómo.** Un script de build (como el prototipo de §3) lee el catálogo desde Odoo (JSON exportado por
`/json/2` o `xmlrpc` con una clave de API de solo lectura, o el mismo `catalogo.json` mientras Odoo no sea la
fuente) y genera HTML + variantes de imagen. `wrangler deploy` lo publica como **Workers Static Assets** (gratis,
sin invocar al Worker). El CTA es **«Escríbenos por WhatsApp»** con el nombre del mueble ya escrito (CTA único del
ADN), igual que hoy. Si se quiere «carrito», uno ligero en el navegador (localStorage) que arma **un solo mensaje
de WhatsApp** con la lista; crear el pedido en Odoo por cola es opcional (Worker `POST /api/pedido` → Queue →
consumidor que llama a Odoo cuando esté despierto; Queues Free 10 000 operaciones/día).

**Rendimiento medido**: ver §3 (prototipo). **Costo**: $0 en Workers Free para el sitio público, a cualquier volumen
razonable (los Static Assets no cuentan); 188 productos × ~8 variantes ≈ 1 500-2 600 archivos, lejos de los 20 000
del plan Free. Si hay Worker para rutas dinámicas (`/api/pedido`, proxy a `/socios`), sus peticiones sí cuentan.

**Odoo puede dormir**: el visitante del catálogo **nunca** despierta el contenedor. Solo lo despiertan el personal
(panel), los socios (`/socios`) y la sincronización. Con eso el contenedor pasa de 24/7 a horario o a demanda:
según `ronda3/cf-plataforma.md`, standard-1 24/7 ≈ $32-38/mes contra ≈ $10,6-18,9 a demanda/horario (o menos
en `basic` si la memoria medida alcanza).

**Qué se pierde.** El constructor de páginas de Odoo para el sitio público (la dueña hoy edita textos y fotos desde
Sitio web › Editar): los textos pasarían a un archivo de contenido versionado (o a campos de Odoo que el build lee),
editables con Brian o con un formulario. El checkout web de Odoo (hoy los tres pagos ya terminan en WhatsApp/tienda:
`sitio-web.md` §4, «Tres pagos sin pasarela con mensaje de WhatsApp»), las cuentas de cliente (`/my`) y el
comparador/wishlist. `/socios` no se pierde: el Worker lo sigue mandando a Odoo (o se reimplementa aparte; fuera
de mi alcance). SEO: se gana (HTML liviano, JSON-LD propio), siempre que se mantengan las URL (§5).
**Esfuerzo**: 3-5 días (generador + exportación desde Odoo + despliegue en CI + redirecciones + pruebas).

### C. Mixto (recomendado, ver §5)

Catálogo público (`/`, `/shop/*`, fichas, `/visitanos`) en Static Assets; el Worker con `run_worker_first` solo para
`/socios*`, `/web*`, `/my*`, `/shop/cart*`, `/shop/checkout*`, `/brian/*`, `/json/*`, `/odoo*` (todo eso va al
contenedor como hoy). El build se dispara al cambiar un producto en Odoo (webhook → GitHub Actions o Workers Builds)
y además una vez al día. Odoo sigue siendo la única fuente de precios y fotos.

| | A. Cachear HTML de Odoo | B. Estático + WhatsApp | C. Mixto |
|---|---|---|---|
| Rendimiento móvil (lab) | 40-55 pts, LCP ~8-10 s (estimado) | ver §3 (medido) | igual que B en el catálogo |
| Costo del sitio público | $0-5 + contenedor 24/7 | **$0** | $0 (+ $5 si se usa Paid para otras cosas) |
| ¿Odoo duerme? | No en la práctica | **Sí** | Sí (solo panel, socios, carrito si se deja) |
| Constructor de Odoo | Se conserva | Se pierde en lo público | Se pierde en lo público |
| Checkout/cuentas Odoo | Se conservan | Se pierden | Se conservan detrás de rutas |
| Riesgo principal | Fuga de HTML con sesión; CSRF | Precio desfasado si falla el build | Igual que B + dos sistemas de URL |
| Esfuerzo | 1-2 días | 3-5 días | 4-6 días |

## 3. Prototipo estático medido

**Qué es.** `sitio-edge/prototipo/generar.mjs` (Node + sharp + fuentes @fontsource OFL) genera `dist/` desde los
datos reales del repo: 188 productos publicables de `catalogo.json` (los 11 sin foto se omiten, igual que Odoo),
precios copiados tal cual, fotos de `static/img/productos`, cifras de socios leídas de `puntos.json`, textos copiados
de `homepage_templates.xml`/`layout_templates.xml`. Páginas: portada, `/shop/` y `/shop/<categoría>/` paginadas
de 24 (los filtros por categoría son enlaces, **0 JavaScript**), fichas (con `SOLO=` se generan solo las 2 medidas)
con JSON-LD `Product` + `BreadcrumbList`, `/visitanos`, `robots.txt`, `sitemap.xml`, `404.html` y `_headers`.
CSS en línea (~8 KB), 4 fuentes woff2 autoalojadas (Anton 18,6 KB precargada con `swap`; Inter 400/700 y Oswald 500
con `optional`), `<picture>` AVIF + WebP con `srcset`, `sizes`, `width/height`, hero y primeras tarjetas sin `lazy`
y con `fetchpriority`. Se sirve con `herramientas/servir.js static` (Brotli + `Cache-Control` como Static Assets).

**Decisiones de contenido (reglas de marca y «no inventar»):**
- Azul `#1340B1` / amarillo `#FED00F` / navy; el amarillo solo sobre azul, navy o el hero oscurecido (igual que hoy);
  Anton/Oswald/Inter; sin degradados ni sombras. CTA único «Escríbenos por WhatsApp» (+507 6026-1919) y, por
  producto, «Pídelo por WhatsApp» con el nombre del mueble (mismo texto que el botón de la ficha actual).
- **Precio**: se muestra la cifra del catálogo sin leyenda de impuesto, **igual que hoy el sitio** (`$104.99`). La duda
  ITBMS (E-01/SW-04: el Excel dice «+ITBMS») sigue abierta y aplica igual al prototipo. En productos con varios
  tamaños la tarjeta dice «desde» el menor y la ficha lista cada tamaño.
- Se quitó «Financiamiento» (SW-03, sin respaldo) y el iframe de Google Maps (SW-01: queda el enlace «Abrir la ruta»).
  Hero y fotos de categorías son las del sitio actual (fotos de stock, SW-05 sigue pendiente) para comparar a igualdad.
- JSON-LD `Product` **sin `availability`**: el inventario está «sin confirmar»; no se inventa. Faltan las reseñas, la
  galería «Inspírate» y la guía (no medidas; las reseñas suman texto, no peso relevante).

**Resultado (mismo método que §1: Lighthouse 12.8 móvil, mediana de 3, misma máquina):**

| Página | Perf. Odoo → prototipo | LCP | FCP | TBT | CLS | Peso | Peticiones | Orígenes |
|---|---|---|---|---|---|---|---|---|
| Portada | 41 → **100** | 8,96 → **1,59 s** | 3,93 → 0,91 s | 939 → 29 ms | 0 → 0 | 1 354 → **251 KB** | 25 → 14 | 4 → 1 |
| `/shop` | 39 → **99** | 10,77 → **1,88 s** | 4,09 → 0,91 s | 812 → 45 ms | 0,126 → **0** | 1 929 → **199 KB** | 29 → 17 | 4 → 1 |
| Ficha cama twin | 39 → **100** | 8,33 → **1,73 s** | 3,86 → 0,93 s | 1 398 → 0 ms | 0 → 0 | 1 420 → **138 KB** | 24 → 9 | 4 → 1 |
| Ficha zapatera ALJ021439 | 39 → **99** | 8,84 → **2,15 s** | 3,99 → 0,95 s | 1 050 → 3 ms | 0 → 0 | 1 503 → **188 KB** | 24 → 9 | 4 → 1 |
| `/visitanos` | 55 → **100** | 8,17 → **1,66 s** | 4,23 → 0,91 s | 329 → 0 ms | 0 → 0 | 1 053 → **146 KB** | 23 → 8 | 5 → 1 |

Accesibilidad / buenas prácticas / SEO de Lighthouse en el prototipo: 100/100/100 en las 5 páginas.
Peso de la portada: HTML 6 KB, fuentes 78 KB, imágenes 136 KB, 0 KB de JS (Odoo: 536 KB de JS).
Primera versión del prototipo (guardada en `lighthouse/prototipo-v1-cls.json`): CLS 0,16 por el cambio de fuente
(Inter/Oswald con `swap` movían la cabecera) y 92-93 pts; se corrigió con `font-display: optional` + `preload`.
Avisos que quedan: Lighthouse sugiere ~30 KB de ahorro con `sizes` más finos en la grilla.

**Límites de la comparación.** Ambos servidores son locales (TTFB de laboratorio 2-250 ms; en producción el
estático sale del borde de Cloudflare más cercano a Panamá y Odoo del contenedor en la región que toque). El
prototipo no tiene carrito, cuentas, buscador ni editor: es lo que se gana **si** el sitio público se limita a
catálogo + WhatsApp. Sin usuarios reales no hay datos de campo (CrUX/INP): son mediciones de laboratorio.

## 4. Imágenes: pipeline recomendado y pesos medidos

**Hoy (medido en Odoo):** la grilla de `/shop` pide `image_1024` JPEG para una tarjeta que en el móvil mide ~180 px
de ancho. Ejemplo XHT022-T-W: `image_1024` = **59 092 B**, `image_512` = 17 398 B, `image_1920` = 48 040 B (¡el
1024 pesa más que el original de 48 KB!). Con `?unique=` Odoo responde `Cache-Control: public, max-age=31536000,
immutable` (cacheable en el borde); sin `unique`, `no-cache`. Odoo guarda además 5 tamaños por foto en la base
(`r3-reconstruccion`: 75 MB de imágenes de producto en `dcasa_test` para 30,5 MB de originales).

**Variantes del prototipo** (sharp 0.34, AVIF q50 esfuerzo 4 y WebP q72; `herramientas`/`prototipo/generar.mjs`;
resumen en `sitio-edge/variantes-imagenes.json`). Medias por archivo:

| Uso | Ancho | AVIF | WebP | Lo que Odoo manda hoy para lo mismo |
|---|---|---|---|---|
| Tarjeta (móvil 1x-2x) | 320 / 640 | **3,2 KB / 7,7 KB** | 4,5 KB / 12,8 KB | `image_512` 17 KB o `image_1024` 59 KB (JPEG) |
| Ficha | 480 / ~890 (original) | 13,7 KB / 35,2 KB | 21,1 KB / 56,4 KB | `image_1024` ~59 KB |
| Hero portada | 640 / 960 / 1400 | 25-42 KB | 41-73 KB | `hero-800.webp` 35 KB / `hero.webp` (1400) |

Para la foto XHT022-T-W_6: 640 px AVIF **3 344 B** contra 59 092 B de `image_1024` (−94 %). Todo el lote
generado (188 fotos principales × 2 anchos × 2 formatos + 2 fichas completas + hero + categorías) = 890 archivos,
**8,97 MB**. El catálogo completo con galería (323 fotos × 3 anchos × 2 formatos + tarjetas) se estima en
~2 600 archivos y ~50 MB: cabe en Static Assets (20 000 archivos, 25 MiB por archivo en Free).

| Opción | Costo oficial | Pros | Contras |
|---|---|---|---|
| **1. Pregenerar en el build y servir como Static Assets** (recomendada) | **$0** (peticiones a assets gratis e ilimitadas) | Sin dependencias en tiempo de visita; AVIF/WebP con calidad controlada; `width/height` exactos en el HTML; caché `immutable` con nombre versionado | El build tarda (6 min 45 s para 890 archivos en esta máquina cargada; en CI solo se regeneran fotos nuevas si se cachea la carpeta por hash) |
| 2. Originales en R2 + transformaciones de Images por URL | R2: 30 MB ≪ 10 GB gratis; Images Free: 5 000 transformaciones únicas/mes, `format=auto` cuenta una; 323 fotos × 4 anchos ≈ 1 300/mes ⇒ **$0** | Sin build de imágenes; cambia tamaños sin redeploy | Si se pasa de 5 000 (más anchos, más fotos, parámetros sueltos) las nuevas fallan con error 9422 en Free; primera petición de cada variante más lenta; otra pieza que configurar |
| 3. Seguir con `/web/image` de Odoo detrás del borde | $0 en Workers, pero despierta el contenedor en cada miss | Nada que construir | JPEG sobredimensionado; Odoo tiene que estar despierto; base de datos más pesada |

Recomendación: **opción 1** ahora (el volumen es chico), con `_headers` `Cache-Control: public, max-age=31536000,
immutable` para `/img/*` y `/fonts/*` (ya lo genera el prototipo). Pasar a la 2 solo si el catálogo crece a miles de
fotos. Los JPEG de `addons/dcasa_catalogo/static/img/productos` (30 MB) pueden salir del repo/imagen Docker a R2
(SW-20) y el build leerlos de ahí. Las variantes generadas **no** van a git (`prototipo/.gitignore`).

## 5. Recomendación

**Arquitectura: C (mixto).** El sitio público —portada, catálogo, fichas, Visítanos— se genera desde los datos de
Odoo y se sirve como **Workers Static Assets** con CTA único por WhatsApp. Odoo queda como ERP y sigue atendiendo,
detrás del mismo Worker (`run_worker_first`), `/socios*`, `/web*`, `/my*`, `/brian/*`, `/json/*` y, si la dueña
quiere conservarlos, `/shop/cart*` y `/shop/checkout*`. Es lo único medido que da a la vez:
- **el mejor rendimiento**: 99-100 pts y LCP 1,6-2,2 s en móvil, contra 39-55 pts y LCP 8-11 s (§3);
- **el menor costo**: el sitio público cuesta **$0** a cualquier volumen razonable, y además **deja dormir a Odoo**,
  que es lo que realmente cuesta (`ronda3/cf-plataforma.md`: standard-1 24/7 ≈ $32-38/mes contra ≈ $10,6-18,9 a
  demanda/horario; menos en `basic` si la memoria medida alcanza).

Costo mensual del **sitio público** según tráfico (vistas/mes = **supuestos**, no hay datos reales de D'CASA):

| Vistas/mes (supuesto) | A. HTML de Odoo cacheado (~25 pet./vista por el Worker) | C. Estático (10-17 pet./vista, todas assets) |
|---|---|---|
| 10 000 | Workers Free ($0) + contenedor 24/7 | $0 |
| 100 000 | ~2,5 M pet. ≈ 83 000/día: al borde del Free ⇒ Paid $5 + contenedor 24/7 | $0 |
| 1 000 000 | 25 M pet. ⇒ $5 + 15 M × $0,30 = **$9,50** + contenedor 24/7 | $0 |

(Precios: https://developers.cloudflare.com/workers/platform/pricing/, 2026-08-28. El contenedor de Odoo necesita
Workers Paid de todas formas; los $5 ya están dentro de las cifras de `cf-plataforma`.)

**Orden de trabajo:**
1. **Ya, sin decidir arquitectura** (sirve también si el sitio sigue en Odoo un tiempo):
   `loading="eager"` en el hero de la portada y de Visítanos (Odoo les pone `lazy`, §1); quitar o espaciar el cron
   `*/10` que impide dormir (`edge/wrangler.jsonc:25`, hallazgo de `r3-cf-plataforma`); autoalojar fuentes (SW-10);
   fijar `web.base.url` y corregir el `D&#39;CASA` del JSON-LD `Organization`.
2. **Bloqueante de contenido**: decidir el ITBMS (E-01/SW-04) antes de publicar precios en cualquier arquitectura.
3. **Generador en el repo** (fuera de `docs/`; p. ej. `sitio/` o dentro de `edge/`): partir de `prototipo/generar.mjs`;
   fuente = exportación de Odoo (nombre, precio por variante, combo, medidas, fotos, **`website_url` de Odoo**,
   publicado) con una clave de API de solo lectura; variantes de imagen cacheadas por hash en CI.
4. **Worker**: `assets` + `run_worker_first` para las rutas de Odoo (lista de §2.C), `not_found_handling: "404-page"`,
   cabeceras de seguridad también en los assets (`_headers`), tests en `edge/test` como los actuales.
5. **Sincronización**: acción automática de Odoo al cambiar precio/nombre/foto/publicado de un producto →
   `repository_dispatch` (o Workers Builds) → build + `wrangler deploy` (~minutos); más un build diario de respaldo y
   alerta si falla. Con Static Assets cada despliegue publica una versión nueva de los archivos; no hay purga manual que mantener (comportamiento de caché de assets por verificar al desplegar).
6. **Odoo a demanda** (`sleepAfter` corto, sin cron que lo despierte); medir arranque en frío con `r3-odoo-medicion`.
7. Opcional, después: «lista de pedido» en el navegador que arma un solo mensaje de WhatsApp; crear el pedido en
   Odoo por Queue solo si la dueña lo pide.

**Riesgos y cómo cerrarlos:**

| Riesgo | Mitigación |
|---|---|
| **SEO: cambio de URL** (Odoo usa `/shop/<slug>-<id>` y `/shop/category/<slug>-<id>`; el prototipo usa otras) | El generador usa **exactamente** `website_url` de Odoo; si alguna cambia, `_redirects` (hasta 2 000 estáticas) con 301. Hoy el sitio no está publicado: es el momento barato de fijar URLs. |
| **Contenido duplicado** (catálogo estático y `/shop` de Odoo vivos a la vez) | El Worker no deja pasar `/shop` ni fichas a Odoo (solo carrito/checkout si se conservan); `canonical` y `sitemap.xml` solo del estático; `noindex` en lo que quede de Odoo público. |
| **Precio desfasado** (Odoo cambió y el build falló) | Build disparado por la acción de Odoo + diario + alerta; la venta se confirma por WhatsApp, y el precio de la factura sale de Odoo. Nunca calcular precios en el build: solo copiarlos (regla del catálogo). |
| **Stock** | El inventario está «sin confirmar»: no mostrar existencias ni `availability` hasta que haya conteo; cuando lo haya, exportarlo en el mismo build. |
| **La dueña pierde el constructor de Odoo** para el sitio | Textos en un archivo de contenido versionado (editable con Brian o un formulario simple); fotos y precios siguen saliendo de Odoo. Es el costo real de esta opción: decirlo al dueño. |
| **Checkout/cuentas de Odoo** | Hoy los tres pagos terminan en WhatsApp/tienda; si se quieren conservar, siguen en Odoo detrás de `run_worker_first` (despiertan el contenedor solo cuando alguien compra). |
| **Privacidad** (SW-01) | El prototipo ya no carga terceros (0 orígenes externos: sin Google Fonts ni iframe de Maps). |

**Si el dueño prefiere quedarse con el sitio en Odoo (A):** se puede, pero hay que (1) quitar `Set-Cookie` a anónimos
en rutas cacheables, (2) cambiar el «Agregar» sin JS por el de JSON-RPC (el de formulario rompe con CSRF), (3)
migrar de `caches.default` a Workers Cache con `stale-while-revalidate` y `Cache-Tag`, (4) purgar por etiqueta desde
Odoo. Gana TTFB, no gana el peso de 1-2 MB ni el TBT de 0,8-1,4 s, y Odoo sigue despierto. No lo recomiendo.

## 6. Archivos entregados

- `docs/auditoria/ronda3/sitio-edge/prototipo/` — `generar.mjs`, `package.json`, `.gitignore` (excluye
  `node_modules/` y `dist/`). Regenerar: `cd prototipo && npm i && SOLO=XHT022-T-W,ALJ021439 node generar.mjs`
  (sin `SOLO`, todas las fichas con galería) y `npm run serve` (puerto 8191).
- `docs/auditoria/ronda3/sitio-edge/herramientas/` — `servir.js` (proxy con Brotli para Odoo / servidor estático),
  `run.sh` (Lighthouse ×N), `resumen.js` (medianas), `base.sh` y `proto.sh` (las corridas de este informe).
- `docs/auditoria/ronda3/sitio-edge/lighthouse/` — `linea-base-odoo.{json,md}`, `prototipo.{json,md}`,
  `prototipo-v1-cls.json` (resúmenes; los JSON completos de Lighthouse, ~700 KB c/u, no se versionan).
- `docs/auditoria/ronda3/sitio-edge/variantes-imagenes.json` — pesos de las variantes generadas.

## 7. Coordinación

- `r3-reconstruccion` adoptó este trabajo como **Fase 1** de su híbrido con criterios de salida LCP < 2,5 s y
  Lighthouse ≥ 90: el prototipo los cumple en las 5 páginas medidas (LCP 1,6-2,2 s, 99-100 pts); falta «0 pedidos
  perdidos» y «Odoo sin tráfico anónimo», que dependen del Worker real.
- `r3-cf-plataforma` confirmó que, sin sacar el sitio de Odoo, el contenedor converge a 24/7; sus costos de
  contenedor son los que uso en §2 y §5.
- La compresión al cliente la hace Cloudflare sola en las respuestas de un Worker (gzip/brotli según el cliente;
  https://developers.cloudflare.com/workers/runtime-apis/fetch/): por eso la línea base se midió con Brotli delante.
