# Ronda 3 · `r3-sitio-edge` — Sitio público y tienda: rendimiento al menor costo

Agente `r3-sitio-edge` · 2026-10-01 · Informe INCREMENTAL (se completa a medida que hay mediciones).

## Estado
- [ ] 1. Línea base medida (Odoo local + Lighthouse móvil, mediana de 3)
- [ ] 2. Estrategias A/B/C con documentación oficial de Cloudflare
- [ ] 3. Prototipo estático medido
- [ ] 4. Pipeline de imágenes
- [ ] 5. Recomendación

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

