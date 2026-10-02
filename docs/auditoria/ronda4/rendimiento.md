# Ronda 4 · Rendimiento del sitio: ¿se puede mejorar o es el techo?

Agente `r4-rendimiento` · 2026-10-01 · Solo investigación (no se tocó código).

**Respuesta corta para el dueño: no, no es el techo.** El sitio público de hoy (Odoo renderizando cada página)
está lejos de su máximo: hay mejoras rápidas dentro de Odoo/Worker y, sobre todo, la Fase 2 (catálogo estático
en el borde) ya se prototipó y midió en **99-100 puntos** de Lighthouse móvil contra **39-55** de hoy. Donde sí hay
un techo duro es en el **panel de administración (`/odoo`)**: su velocidad la marca la CPU del contenedor
(1/4 de vCPU) y solo sube pagando una instancia más grande.

Convención: «medido» = hay cifra con método en un informe citado; «estimado» = cálculo propio sin medir;
«sin medir» = no hay dato. No se pudo medir staging (`dcasa-staging.dcasapty.workers.dev`): el proxy de esta
sesión bloquea `workers.dev`. **No hay datos de campo** (usuarios reales / CrUX): todo es laboratorio.

## 1. Lo que ya está medido (rondas anteriores)

Fuente: `docs/auditoria/ronda3/sitio-edge.md` §1 y §3 (Lighthouse 12.8 móvil, Moto G emulado, 4G lenta, CPU ×4,
mediana de 3, Odoo 19 real con Brotli delante, servidor local: el TTFB de laboratorio **no** incluye la red
Panamá → contenedor).

| Página | Odoo hoy: puntos / LCP / TBT / peso | Prototipo estático: puntos / LCP / TBT / peso |
|---|---|---|
| Portada | 41 / 8,96 s / 939 ms / 1 354 KB | **100 / 1,59 s / 29 ms / 251 KB** |
| `/shop` | 39 / 10,77 s / 812 ms / 1 929 KB (CLS 0,126) | **99 / 1,88 s / 45 ms / 199 KB** (CLS 0) |
| Ficha (cama twin) | 39 / 8,33 s / 1 398 ms / 1 420 KB | **100 / 1,73 s / 0 ms / 138 KB** |
| `/visitanos` | 55 / 8,17 s / 329 ms / 1 053 KB | **100 / 1,66 s / 0 ms / 146 KB** |

- **TTFB del servidor** (curl local, en caliente, sin red): `/` 50 ms, `/shop` 282 ms, ficha 178 ms, `/visitanos`
  53 ms (`sitio-edge.md` §1). CPU por visita en un núcleo completo: `/` 25 ms, `/shop` **174 ms**, ficha 110 ms;
  `/` con sesión de admin ~114 ms (`ronda3/odoo-medicion.md` §2.1).
- **Qué pesa en Odoo** (portada): JS **536 KB** comprimidos (`web.assets_frontend_lazy.min.js` 2,49 MB sin
  comprimir, ~1,5 MB sin usar según Lighthouse); imágenes 396 KB (970 KB en `/shop`, JPEG `image_1024` para
  tarjetas de ~180 px); fuentes 168 KB (Font Awesome 76 KB + Google Fonts); CSS 120 KB (1 MB sin comprimir);
  `/website/translations` 88 KB en **cada** página (`sitio-edge.md` §1).
- **Diagnóstico medido**: el LCP **no** es culpa del servidor. En `/shop`: TTFB 8 % · retraso de carga 70 %
  (5,0 s) · carga 12 % · render 10 %. El cuello es el peso de JS/CSS que el teléfono tiene que bajar y ejecutar.
- **Odoo no comprime** (werkzeug): sin Brotli serían 4,5 MB y 26 puntos. Cloudflare comprime las respuestas
  del Worker solo (`sitio-edge.md` §7).
- **Arranque**: Odoo arranca en ~3 s en 4 núcleos (`odoo-medicion.md` §2.1); restauración desde R2 ~10 s + `-u`
  ~25 s (`edge/src/index.ts:70`); tras cada despliegue, la primera visita regenera bundles: **11,4 s con 4 núcleos,
  «varias decenas de segundos» con 1/4 vCPU** (estimado en `odoo-medicion.md` §2.6, líneas 107-112).
- **Bajo carga** (un proceso con hilos, `workers = 0`, `docker/entrypoint.sh:175`): ~13 pet./s **en un núcleo
  completo** (GIL); 20 simultáneas → p50 1,2-2,6 s (`odoo-medicion.md` §2.1).
- Plan: `DECISION_Y_PLAN.md:79-82` (Fase 2, criterio Lighthouse ≥ 90 y LCP < 2,5 s). El prototipo ya cumple.

## 2. Qué hace hoy el Worker (`edge/`)

| Pregunta | Respuesta | Dónde |
|---|---|---|
| ¿Qué cachea? | Solo `GET/HEAD` de `/web/assets/*`, `/<módulo>/static/*`, `/web/image/*` y `/web/content/*?…unique=` | `edge/src/routing.ts:82-87`, `:111-113` |
| ¿Con qué condición? | Solo si Odoo responde 200, **sin `Set-Cookie`** y con `Cache-Control: public` sin `private/no-store/no-cache` | `routing.ts:120-126` |
| ¿Qué TTL? | El que pone Odoo (el Worker no lo reescribe): estáticos de módulo `public, max-age` **1 semana**; bundles y adjuntos con hash/`unique` **1 año `immutable`**; imágenes sin `unique` → `no-cache` (no se cachean) | `vendor/odoo/odoo/http.py:334,338,2231-2232`; `vendor/odoo/addons/web/controllers/binary.py:84-87,158-161` |
| ¿Mecanismo? | Cache API `caches.default` (`match`/`put`), clave = URL completa | `edge/src/index.ts:238`; `edge/src/handler.ts:44-61` |
| ¿HTML público (`/`, `/shop`, fichas)? | **No se cachea nunca**: cada visita va al contenedor. Odoo además manda `Set-Cookie: session_id` a todo anónimo y CSRF atado a la sesión | `routing.ts:113`; `sitio-edge.md` §2.A |
| ¿Cookies/bypass? | No hay regla por cookie: lo que no está en la lista blanca va siempre al origen; `/brian/*` nunca se cachea | `routing.ts:79,108-110` |
| ¿Contenedor frío? | El DO espera hasta **8 s** al arranque; si no llega, página 503 «Estamos abriendo la tienda» con `Retry-After: 15` y recarga sola; tope de arranque 420 s | `handler.ts:195,209-226,133-179`; `index.ts:71` |
| ¿Duerme? | Producción 24/7 (`ODOO_DORMIR_TRAS: ""`); staging duerme tras 1 h ⇒ en staging la primera visita tras una hora ve el 503 (restauración desde R2) | `edge/wrangler.jsonc` (vars y `env.staging.vars`) |

**Observaciones nuevas (no estaban en informes previos):**
1. **Cache API y dominio.** La documentación dice que la Cache API funciona en Workers con **dominio personalizado**
   (https://developers.cloudflare.com/workers/runtime-apis/cache/). Hoy `routes` está comentado en
   `edge/wrangler.jsonc` (solo `workers.dev`): que `caches.default` esté guardando algo en staging **no está
   verificado** (sin medir; históricamente era un no-op en `workers.dev`). Con el dominio activo debería funcionar.
2. **La Cache API es local por centro de datos**, no tiene *tiered cache* ni colapsa peticiones simultáneas
   (https://developers.cloudflare.com/workers/cache/limitations/). Con poco tráfico, en Panamá habrá muchos
   *miss* que van al contenedor. **Workers Cache** (`"cache": {"enabled": true}`) sí trae tiered cache,
   colapso de peticiones, `stale-while-revalidate` y purga global por etiqueta (https://developers.cloudflare.com/workers/cache/).
3. **Recorrido de cada visita de HTML**: navegador en Panamá → Worker en el PoP más cercano → Durable Object →
   contenedor en ENAM (`wrangler.jsonc`, `constraints.regions`). La doc advierte que «Durable Objects and their
   associated Container instances are not guaranteed to run in the same location»
   (https://developers.cloudflare.com/containers/concepts/architecture/). La latencia real Panamá ↔ contenedor
   está **sin medir**; un viaje Panamá ↔ este de EE. UU. suele rondar 40-70 ms de ida y vuelta (**estimado, sin
   verificar**). Con el TTFB de servidor medido, el TTFB real de `/shop` quedaría del orden de 0,4-1 s en un
   contenedor de 1/4 vCPU (estimado). Aun así, el TTFB es la parte menor del LCP (8 % en `/shop`).

## 3. Cuellos de botella para un usuario real en Panamá

| # | Cuello | Peso en la experiencia | Evidencia |
|---|---|---|---|
| 1 | **JS de Odoo website** (536 KB comprimidos, 2,49 MB de JS a ejecutar) ⇒ TBT 0,3-1,4 s, LCP tardío | **El mayor** | `sitio-edge.md` §1 |
| 2 | **CSS render-blocking** de 1 MB + `@import` de Google Fonts **dentro** del CSS (cadena CSS → CSS → fuente, 2 orígenes extra) | Alto (ahorro estimado 1,3 s por CSS bloqueante en `/shop`) | `vendor/odoo/addons/website/static/src/scss/website.scss:5-17`; `addons/website_dcasa/static/src/scss/primary_variables.scss:24-34` |
| 3 | **Imágenes de producto JPEG sobredimensionadas** (`image_1024` ≈ 59 KB para una tarjeta de ~180 px; AVIF 640 px = 3,3 KB) | Alto en `/shop` y fichas | `sitio-edge.md` §4 |
| 4 | **Render por petición en un contenedor de 1/4 vCPU** (`/shop` 174 ms de CPU en un núcleo ⇒ hasta ~4× más si la CPU está acotada, **estimado**) + ida y vuelta a ENAM | Medio en TTFB; alto con varios visitantes a la vez | `odoo-medicion.md` §2.1; `wrangler.jsonc` `instance_type: basic` |
| 5 | Arranque en frío / tras despliegue (503 de hasta decenas de segundos; bundles se regeneran con 1/4 vCPU) | Raro en producción 24/7; frecuente en staging | `handler.ts:195`; `odoo-medicion.md:107-112` |
| 6 | CLS 0,126 en `/shop` (`#o_wsale_pager`) | Medio (puntuación) | `sitio-edge.md` §1 |
| 7 | Terceros: Google Fonts (2 orígenes), iframe de Google Maps en la portada/Visítanos (con `loading="lazy"`), Font Awesome 4.7 | Bajo-medio | `addons/website_dcasa/views/homepage_templates.xml:185-186` |
| 8 | `/website/translations` 88 KB pedido por JS en cada página | Bajo-medio (caché del navegador sin medir) | `sitio-edge.md` §1 |

Lo que **ya** está bien: imágenes propias del tema en WebP (`addons/website_dcasa/static/src/img/*.webp`, 14-85 KB;
hero 82 KB + `hero-800.webp` 36 KB); hero y LCP con `loading="eager" fetchpriority="high"`
(`homepage_templates.xml:143,206`, `layout_templates.xml:142`, test en `tests/test_seo_y_promesas.py:52-53`);
lista de deseos y comparador en la lista de desinstalación (`docker/entrypoint.sh:136-138`; efecto en el peso
del JS **sin medir**: la línea base de ronda 3 pudo incluirlos).

## 4. Mejoras clasificadas

### (a) Rápidas, sin cambiar la arquitectura (dentro de Odoo y del Worker)

| Mejora | Esfuerzo | Impacto esperado | Confianza |
|---|---|---|---|
| **Fuentes locales**: activar «fuentes locales» de Odoo (`google-local-fonts`, `vendor/odoo/addons/website/models/assets.py:235-275`, las guarda como adjuntos `/web/content/…`) o `@font-face` propio con woff2 en `website_dcasa/static` + `preload` de Anton; sacar Oswald a 1-2 pesos (hoy pide 400-700, `primary_variables.scss:31`) | 0,5 día | Quita 2 orígenes y la cadena `@import`; FCP −0,3 a −1 s (estimado). El prototipo midió que `font-display: optional` + preload eliminó un CLS de 0,16 | Media |
| **Tarjetas con `image_512`/`image_256`** en la grilla de `/shop` y carriles (heredar la plantilla de `website_sale`) + `width/height` o `aspect-ratio` en la imagen | 0,5-1 día | `/shop` de ~970 KB de imágenes a ~250-350 KB (estimado); arregla el CLS 0,126 del paginador | Media-alta |
| **Fotos de producto en WebP** al importar (`dcasa_catalogo`) en vez de JPEG | 1 día | −30-50 % por foto frente a JPEG (estimado por la tabla de `sitio-edge.md` §4); Odoo sigue sirviendo un solo formato (sin AVIF ni `srcset` por navegador) | Media |
| **Workers Cache** en lugar de `caches.default` para estáticos e imágenes (tiered cache, colapso de peticiones) y activar el dominio propio | 0,5 día | Menos *miss* al contenedor desde Panamá; no cambia el LCP de laboratorio | Alta (doc oficial) |
| **Cachear HTML anónimo** en el borde (`sitio-edge.md` §2.A): quitar `Set-Cookie` a anónimos en rutas públicas, bypass si hay `session_id`, `Cache-Tag` + purga al cambiar un producto, «Agregar» por JSON-RPC (el de formulario falla por CSRF) | 1-2 días | TTFB ≈ el del borde y la página sigue viva aunque el contenedor arranque; **LCP 9-11 → 8-10 s, puntuación 40-55** (estimado en `sitio-edge.md` §2.A). No toca el JS | Media; riesgo de servir HTML con sesión si falla el bypass |
| Mapa de Google como enlace/imagen estática en vez de `<iframe>` | 1 h | Menos terceros en `/visitanos` (sin medir) | Media |
| Revisar módulos que inyectan JS al frente (chat de visitante, etc.) además de los ya listados | 0,5 día | TBT algo menor (sin medir); el núcleo de Odoo website/OWL no se puede quitar | Baja |
| `workers = 2` (prefork) en vez de hilos | config | Duplica pet./s **con un núcleo completo** (`odoo-medicion.md`: 12,9 → 27 pet./s), pero +~90 MiB y con 1/4 vCPU no hay CPU que repartir: **no recomendado en basic** | Media |

**Techo realista del sitio dentro de Odoo con todo lo anterior: ~50-70 puntos en Lighthouse móvil y LCP de
~4-7 s en laboratorio (estimado, sin medir).** No llega a «bueno» (≥ 90, LCP < 2,5 s) porque el JS y el CSS de
Odoo website (TBT 0,3-1,4 s) siguen ahí; eso solo se quita sacando el catálogo de Odoo.

### (b) Fase 2: catálogo estático en el borde (ya prototipado y medido)

- **Medido**: 99-100 puntos, LCP 1,6-2,2 s, TBT ≤ 45 ms, CLS 0, 138-251 KB, 0 JS, 1 solo origen
  (`sitio-edge.md` §3; prototipo en `docs/auditoria/ronda3/sitio-edge/prototipo/generar.mjs`).
- Cómo: HTML generado desde los datos de Odoo, AVIF/WebP con `srcset`, fuentes woff2 propias, servido como
  Workers Static Assets (gratis e ilimitado según https://developers.cloudflare.com/workers/platform/pricing/);
  el Worker con `run_worker_first` manda a Odoo solo `/socios`, `/web`, `/my`, `/brian`, carrito/checkout.
- Bonus: el visitante del catálogo **no despierta** el contenedor ni compite por su 1/4 de vCPU con el personal.
- Lo que se pierde: el constructor de Odoo para las páginas públicas (§2.B de `sitio-edge.md`).
- Esfuerzo: 3-4 semanas según `DECISION_Y_PLAN.md:79-82`.

### (c) Lo que no se mejora en este plan (techo duro)

| Parte | Techo | Por qué |
|---|---|---|
| **Panel `/odoo` (back-office)** y páginas con sesión (carrito, checkout, `/socios`, `/my`) | Lo marca la CPU: 1/4 vCPU, un proceso Python | Son por usuario, no se cachean. El logueado cuesta 4-5× más CPU que el anónimo (`odoo-medicion.md` §2.1). El JS del backend (~6,9 MB de bundles sin comprimir, `odoo-medicion.md:108`) se cachea en el navegador tras la primera carga |
| **Arranque en frío y primer acceso tras desplegar** | Restauración R2 (~10 s) + `-u` (~25 s) + regenerar bundles (decenas de s con 1/4 vCPU, estimado) | Disco efímero; no hay snapshots con política `default` (`wrangler.jsonc`, comentario de `scheduling_policy`) |
| Distancia Panamá ↔ ENAM | ~40-70 ms por ida y vuelta (sin verificar) | No hay región de Containers en Centroamérica; ENAM es lo más cercano |

**Subir de instancia** (tipos y precios: `ronda3/cf-plataforma.md:202,316-318`, fuente https://developers.cloudflare.com/containers/platform/limits/
y …/containers/platform/pricing/, 2026-08/09; cifras 24/7 con CPU 3-25 %, incluyen los $5 del plan Paid):

| Tipo | vCPU / RAM | 24/7 $/mes | Qué gana el panel |
|---|---|---|---|
| basic (hoy) | 1/4 / 1 GiB | ≈ 11,9-14,7 | — |
| standard-1 | 1/2 / 4 GiB | ≈ 32,4-38,1 | ~2× CPU (estimado) |
| standard-2 | 1 / 6 GiB | ≈ 46,9-58,3 | ~4× CPU (estimado); permitiría `workers = 2` |
| Personalizado | mín. 1 vCPU y 3 GiB/vCPU | ≥ standard-2 | No abarata (`cf-plataforma.md:203`) |

Cambiar `instance_type` es una línea en `edge/wrangler.jsonc` (la política `default` sí lo admite). Ganancia real
en el panel **sin medir**: conviene medir en staging con standard-1 antes de pagar el doble o triple.

## 5. Conclusión por parte

- **Sitio público**: no está en su techo. Con arreglos rápidos (fuentes locales, imágenes más chicas, CLS,
  Workers Cache, opcionalmente HTML cacheado) mejora algo (estimado 50-70 pts); el salto real a 99-100 pts y
  LCP < 2,5 s está **medido** con el catálogo estático de la Fase 2. Ese es el techo práctico y ya se conoce.
- **Panel de administración**: en basic está cerca de su techo; solo mejora con más vCPU (standard-1 ≈ +$20/mes,
  standard-2 ≈ +$35-44/mes respecto a basic, 24/7) o quitándole trabajo al contenedor (Fase 2 saca a los visitantes).
- **Pendiente de medir** (cuando haya dominio y acceso): TTFB real desde Panamá, si `caches.default` cachea en
  staging, Lighthouse contra staging real, y el panel en standard-1.
