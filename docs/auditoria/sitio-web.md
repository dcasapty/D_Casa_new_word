# Auditoría del sitio web — `website_dcasa` y `dcasa_catalogo`

Agente `sitio-web` · 30/09/2026 · Auditoría **estática** (vendor/odoo vacío, sin navegador ni fuentes): todo
lo que dependa de cómo renderiza Odoo se marca *(por verificar)*. Contrastes calculados con la fórmula WCAG.
No se consideraron fallos las decisiones documentadas en `docs/REDISENO.md`, `docs/CATALOGO_REVISAR.md`
(decisiones de la dueña del 30/09) ni `CLAUDE.md`.

## Resumen ejecutivo

El sitio está **bien construido para estar sin lanzar**: marca respetada con disciplina (el amarillo solo sobre
azul/navy/foto oscura), foco visible en todas las superficies, `prefers-reduced-motion` cubierto, pausa en la
cinta de reseñas, hero con `fetchpriority`, WebP con `width/height`, JSON-LD seguro, catálogo sin inventar
cifras y checkout adaptado a Panamá. Buena parte de los 100 problemas de `docs/AUDITORIA_UX.md` ya está
resuelta en código (ver §5).

Lo que **impide lanzar con tranquilidad** es legal y de honestidad del contenido, no de diseño:

1. **Privacidad**: el sitio captura datos personales (checkout, contacto, socios) y carga terceros (Google
   Fonts en todas las páginas, Google Maps en `/visitanos`) sin aviso, sin política de privacidad y sin
   banner de cookies.
2. **Sin páginas de política** (entregas, garantía/cambios, términos) ni razón social/RUC visibles.
3. **Promesas sin respaldo**: «financiamiento» (está como pendiente en `docs/PLAN.md:71`) aparece en 7 sitios,
   incluida la descripción que verá Google, y esa misma descripción menciona «comedores», que no se venden.
4. **Precio**: confirmo el hallazgo de `enterprise-gap`: si el Excel es «+ITBMS», la tienda muestra 7 % menos
   de lo que se factura.

| Sev. | Cant. | IDs |
|---|---|---|
| ALTO | 3 | SW-01, SW-02, SW-03 |
| MEDIO | 8 | SW-04 a SW-11 |
| BAJO | 10 | SW-12 a SW-21 |

---

## 1. Hallazgos ALTOS

### SW-01 · ALTO · Privacidad: datos personales y terceros sin aviso ni consentimiento
- **Evidencia.**
  - Recolección: checkout (nombre, teléfono, dirección), `/contactus`, `/socios/registro` (celular + PIN).
  - `addons/website_dcasa/static/src/scss/primary_variables.scss:27-38`: Anton y Oswald se piden a Google
    Fonts (`'url': 'Anton'`, `'Oswald:400,500,600,700'`), más Inter; cada visitante envía su IP a Google en
    la **primera página**.
  - `addons/website_dcasa/views/homepage_templates.xml:180`: iframe de Google Maps en `/visitanos` (aunque es
    `loading="lazy"`, se carga al acercarse y Google pone sus cookies).
  - No hay página de privacidad ni `cookies_bar` (grep en `addons/`: cero coincidencias; el pie
    `layout_templates.xml:142-181` no enlaza nada legal). Odoo además pone su cookie de visitante
    (`visitor_uuid`) en el sitio público *(por verificar)*.
  - Panamá tiene ley de protección de datos personales (Ley 81 de 2019, reglamentada en 2021): exige
    información al titular y consentimiento *(por verificar con asesor legal)*.
- **Arreglo.**
  - Crear `/privacidad` (qué se recoge, para qué, con quién, cómo pedir borrado) y enlazarla en el pie, en el
    formulario de contacto, en el registro de socios y en el checkout.
  - Activar el aviso de cookies de Odoo (Sitio web → Ajustes → «Barra de cookies»).
  - Autoalojar las tres fuentes en `static/src/fonts/` (woff2 + `@font-face` + `font-display: swap`): quita
    el tercero, el bloqueo de render por CSS externo y el riesgo de privacidad.
  - Mapa en dos pasos: imagen fija con botón «Ver mapa» que inyecta el iframe (el enlace «Abrir la ruta en
    Google Maps» ya existe).
- Coordina con `seguridad` (CSP: el borde no envía ninguna, `edge/src/routing.ts:79-84`; si se añade, debe
  permitir `maps.google.com`/`www.google.com` para el iframe y `wa.me`).

### SW-02 · ALTO · Faltan políticas y datos legales (AUDITORIA_UX #66 sigue abierto)
- **Evidencia.** No existe ninguna página de entregas, garantía/cambios ni términos (`views/paginas_templates.xml`
  solo tiene contacto y 404; el pie no las enlaza, `layout_templates.xml:148-175`). El pie no muestra razón
  social ni RUC (datos reales en `CLAUDE.md`, por lo tanto no es inventar). El checkout no pide aceptar
  términos. La ficha apaga deliberadamente la «garantía de 30 días» de Odoo (`data/website_data.xml:236`),
  correcto, pero deja al cliente sin **ninguna** política.
- **Arreglo.** Páginas «Entregas y retiro», «Garantía y cambios», «Términos de compra» con lo que la dueña
  confirme (no redactar plazos por ella); enlazarlas en el pie y en el checkout; mostrar «D'CASA Panamá · RUC
  155779346-2-2026 DV7» en la franja de copyright (`layout_templates.xml:137`).

### SW-03 · ALTO (por confirmar con la dueña) · Promesas sin respaldo en contenido público
Regla 4 de `CLAUDE.md`: no inventar contenido.
- **«Financiamiento / crédito flexible»**: `layout_templates.xml:27` (barra de anuncios), `:69` (ficha),
  `homepage_templates.xml:235` (beneficios), `:344` (FAQ, dice «formas de pago… y también financiamiento
  flexible»), `data/website_data.xml:220` (**descripción de Google de la portada**), `docs/REDISENO.md:43-45`.
  `docs/PLAN.md:71` lo lista como **pendiente** («Financiamiento/crédito: plan de pagos por cliente»). Si hoy
  se ofrece de palabra por WhatsApp, redactarlo así («pregunta por crédito»); si no existe, quitarlo.
- **«Comedores»**: `data/website_data.xml:220` anuncia «Salas, recámaras, colchones y **comedores**». El
  catálogo real (`dcasa_catalogo/data/catalogo.json`: recámaras 103, zapateras 38, estantes 27, TV 17,
  oficina 6, colchones 5, salas 3) no tiene comedores y la categoría está oculta
  (`website_dcasa/data/product_public_category_data.xml:282`). Google mostrará esa frase en los resultados.
  Además, la frase omite lo que más se vende (recámaras, zapateras).
- **«…efectivo, Yappy o tarjeta»** en la entrega/tienda: `models/tienda.py:291`. La pasarela de tarjeta está
  pendiente (`docs/PLAN.md:59`); confirmar que en tienda se acepta tarjeta antes de prometerlo por escrito.
- **«Te lo llevas hoy / Muchos vienen en caja»** (hero, beneficios, ficha, Visítanos): es el diferenciador del
  ADN (`REDISENO.md:50`), pero el inventario arranca en 0 «sin confirmar» en los 199 productos
  (`CATALOGO_REVISAR.md:7`). Aceptable si el tono sigue siendo «muchos», no «todos»; revisar en la ficha de un
  producto que no viene en caja.
- **Arreglo.** Reescribir `website_meta_description` con las categorías reales (recámaras, colchones, zapateras,
  muebles de TV, estantes, oficina) y sin «financiamiento» hasta confirmarlo.

---

## 2. Hallazgos MEDIOS

### SW-04 · MEDIO · CONFIRMA a enterprise-gap: el precio que ve el cliente depende de la pregunta «+ITBMS»
`dcasa_catalogo/catalogo.py:114-115` asigna el `list_price` del Excel con impuesto *incluido* y `:152` fuerza
`show_line_subtotals_tax_selection = 'tax_included'` en **todos** los sitios: la tienda, el carrito y la
cotización por WhatsApp muestran la cifra del Excel como precio final. Si el Excel es «+ITBMS», el cliente ve
$329.99 y la factura sale $353.09 (ruptura de confianza, y riesgo de devolución). Además `docs/PLAN.md:88`
dice que los precios «se muestran sin ITBMS» y `docs/CATALOGO.md:20` que van con ITBMS incluido: los docs se
contradicen. Bloquear el lanzamiento hasta confirmar con la dueña y la factura 00821.

### SW-05 · MEDIO · Fotos de stock de Odoo presentadas como ambientes/productos de D'CASA
- `homepage_templates.xml:198-201` (hero: «sofá de cuero»), `:262` (sofá amarillo), `:308-313` («Inspírate» +
  «Síguenos en Instagram»), `:106`; `models/website.py:19-27` (las 6 tarjetas de «Compra por espacio»: sofá
  turquesa, cabecero tapizado…). `docs/REDISENO.md` («Fotografía») reconoce que son del tema Loftspace
  «mientras llega la sesión de fotos».
- Problema: muestran muebles que D'CASA no vende (salas con 3 productos, sofás de cuero) y el bloque
  «Inspírate» sugiere que son de la tienda. Con la regla 4 es contenido dudoso; además la licencia de
  reutilización fuera de Odoo *(por verificar)*.
- **Arreglo.** Antes de publicar, reemplazar al menos hero, `cat-*.webp` y «Inspírate» con fotos reales del
  catálogo o de la tienda (las fotos de producto ya están en `dcasa_catalogo`); se cambian desde el editor sin
  código.

### SW-06 · MEDIO (por verificar con perfil) · Refracción SVG animada: costo en teléfonos Android
- `views/layout_templates.xml:78-89` (`feTurbulence` + `feDisplacementMap scale=38`),
  `static/src/js/animaciones.js:99-113` (se activa en cualquier Chromium, **incluido Android**) y `:143-159`
  (anima `baseFrequency` 18 s en bucle mientras la píldora está sobre el hero), `dcasa.scss:390-393`.
- `feTurbulence` animado por SMIL no se acelera por GPU: se recalcula por fotograma, justo en la pantalla
  de entrada de un público mayoritariamente móvil. El propio `REDISENO.md` (v2.4) ya tuvo que pausarlo por
  batería. `prefers-reduced-motion` desactiva la animación (bien), pero no hay criterio de gama baja.
- **Arreglo.** Limitar la refracción (y su animación) a `(hover: hover) and (pointer: fine)` o a
  `min-width: 992px`; en móvil dejar el vidrio esmerilado. Medir con Performance de Chrome en un Android de
  gama media antes de decidir. Añadir `@media (prefers-reduced-transparency: reduce)` con fondo sólido.
- Nota de diseño: el vidrio líquido es **pedido de la dueña** (REDISENO v2.1-2.3) aunque roce la regla
  «sistema plano». No se reporta como fallo; solo su costo.

### SW-07 · MEDIO · Contraste del enlace activo sobre el vidrio claro (WCAG 1.4.3)
- `dcasa.scss:354-356` pone el enlace activo en azul `#1340B1`; el fondo del vidrio es `rgba(255,255,255,.62)`
  (`:293`) sobre lo que pase detrás. Con la cabecera ya fija (`:not(.o_header_affixed)` de `:453` ya no
  aplica), sobre la banda azul de socios el fondo efectivo ≈ `#A5B6E1` → **4.33:1**; sobre una foto oscura
  ≈ `#9E9E9E` → **3.27:1**; ambos < 4.5:1 para texto de 15 px. El texto normal (tinta `#1B2233`) sí pasa
  (5.9-15.9:1).
- **Arreglo.** Enlace activo en navy `#0E2A6B` (≥ 5.2:1 en los peores casos) o subir el vidrio claro a
  `.78` de opacidad.

### SW-08 · MEDIO · El checkout no deja pedir factura a nombre de empresa (RUC)
- `controllers/main.py:11-14` fuerza `display_b2b_fields = False` y `models/tienda.py:320-321` desactiva
  `website_sale.address_b2b` para todos. Correcto para el cliente final (AUDITORIA_UX #18), pero un comprador
  con negocio no puede dar RUC/DV ni razón social; la factura saldría a consumidor final.
  `AUDITORIA_UX #18` proponía esconderlo bajo «¿Necesitas factura con RUC?» y no se implementó.
- **Arreglo.** Casilla plegable «Necesito factura con RUC» que muestre RUC/DV y razón social (campos de
  `l10n_pa`/`dcasa_base`). `@contabilidad`: confirmar qué campos exige la factura electrónica de la DGI.

### SW-09 · MEDIO · «Muebles de TV» (17 productos) no tiene tarjeta en la portada; «Salas» casi vacía
`models/website.py:20-27` define 6 tarjetas y omite `muebles_tv` (categoría creada en
`dcasa_catalogo/data/product_public_category_data.xml:5`). «Salas» solo tiene 3 productos pero es la primera
tarjeta y la foto promete sofás. Es la 3.ª categoría del catálogo y hoy solo se llega por el filtro.
**Arreglo:** añadir la tarjeta de Muebles de TV y ordenar las tarjetas por tamaño real (recámaras, zapateras,
estantes, TV…), o quitar/relegar Salas hasta tener inventario.

### SW-10 · MEDIO · Fuentes: bloqueo de render y dependencia externa (rendimiento)
Mismo origen que SW-01 (`primary_variables.scss:27-38`). Rendimiento: CSS de `fonts.googleapis.com` bloquea el
render, más 2 orígenes (DNS+TLS) antes del LCP, que es un titular Anton 48-104 px. Autoalojar, y con
`<link rel="preload" as="font" crossorigin>` solo para Anton (LCP) y Inter 400.

### SW-11 · MEDIO (por verificar) · El HTML no se cachea en el borde: el LCP depende del contenedor
`edge/src/routing.ts:21-26` solo cachea `/web/assets`, `static`, `/web/image` y adjuntos versionados; toda
página HTML (portada, tienda, fichas) va siempre al origen. Con contenedor Cloudflare que duerme, la primera
visita paga el arranque en frío antes de pintar. `@infra`: medir TTFB de `/` en frío y en caliente; si es
alto, cachear `/`, `/shop*` y fichas para anónimos (ya hay separación por tarifa, `REDISENO.md` auditoría)
o mantener el contenedor caliente.

---

## 3. Hallazgos BAJOS

| ID | Dónde | Hallazgo | Arreglo |
|---|---|---|---|
| SW-12 | `views/paginas_templates.xml:163-167` | La 404 solo cambia el color del dibujo: sigue genérica (sin WhatsApp ni enlace al catálogo; AUDITORIA_UX #55 parcial). | Plantilla propia con «Esta página no existe», chips de categorías y botón de WhatsApp. |
| SW-13 | `layout_templates.xml:44-49`, `models/website.py:235-268` | JSON-LD solo en la portada (correcto y seguro). Falta decidir: `openingHoursSpecification` (no se inventa: pedirlo a la dueña; además es el dato que más piden en Google, AUDITORIA_UX #65) y `Product`: Odoo lo emite en cada ficha *(por verificar)*; con inventario 0 «sin confirmar» **comprobar que `availability` no salga `OutOfStock`** en los 199 (Rich Results Test). | Probar una ficha; si sale agotado, forzar `InStock` para productos con `allow_out_of_stock_order`. |
| SW-14 | `data/website_data.xml` | No se define imagen para compartir (`og:image`/`social_default_image`); el negocio vende por WhatsApp, donde la vista previa del enlace es la tarjeta de visita. Cae al logo *(por verificar)*. | Definir imagen social (foto real de la tienda o de un producto). |
| SW-15 | `layout_templates.xml:62,94,170-173`, `homepage_templates.xml:167,304` | Varios enlaces con `target="_blank"` no avisan «se abre en pestaña nueva» (botón de WhatsApp de la ficha, cabecera, pie, Instagram). El resto sí lo hace (v2.4). Es consejo (3.2.5 AAA), pero rompe la consistencia. | Añadir el `visually-hidden` común. |
| SW-16 | `dcasa.scss:594-605`, `homepage_templates.xml:211` | En ≤575 px los botones llevan `white-space: nowrap` y ancho 100 %. «ESCRÍBENOS POR WHATSAPP» + ícono + relleno `btn-lg` ≈ 298 px estimados, > 288 px útiles a 320 px → posible desborde (1.4.10 Reflow). *(por verificar a 320 px)* | Permitir `white-space: normal` bajo 360 px o reducir `padding-x`. |
| SW-17 | `data/resenas.json:268-271`, `resenas_templates.xml:56-60` | «Hace un año» está congelado: envejecerá mal. Sin JavaScript la cinta corre y el botón de pausa no hace nada. La dueña decidió dejar las reseñas (30/09); no se cuestiona el contenido. | Guardar fecha real (mes/año) en el JSON; sin JS, mostrar la fila estática. |
| SW-18 | `homepage_templates.xml:163-165`, `layout_templates.xml:171`, `models/website.py:15` | Teléfono, correo, dirección y coordenadas escritos a mano en varias plantillas, aunque el número de WhatsApp sí es configurable. Si cambia un dato, se desfasan. | Leerlos de `website.company_id`. |
| SW-19 | `dcasa.scss:986-1000,1035-1043` | `ol.o_dcasa_steps` con `list-style: none` pierde la semántica de lista en Safari/VoiceOver (otras listas ya llevan `role="list"`); el «+»/«–» del FAQ es contenido CSS que algunos lectores leen. | `role="list"` en el `<ol>`; `content: '+' / ''`. |
| SW-20 | `dcasa_catalogo/static/img/productos/` | 30 MB de JPG (323 archivos, hasta 265 KB) versionados y copiados a la imagen Docker; solo se usan al instalar (se guardan en BD) y no son públicos por enlace. Además Odoo guarda 4-5 variantes redimensionadas por foto en BD *(por medir)*. `@infra`. | Sacarlos de la imagen tras la carga o guardarlos en R2; medir el tamaño de la BD. Las fotos ya son 1600 px, no más pesadas de lo necesario. |
| SW-21 | `docs/REDISENO.md:58`, `docs/PLAN.md:88`, `dcasa.scss:1285-1316` | REDISENO promete barra fija móvil «con el precio y el botón»: el CSS solo fija cantidad + «Agregar» (el precio no entra). PLAN dice «precios sin ITBMS», contradice el código. | Corregir los docs o mostrar el precio en la barra. |

---

## 4. Lo que está bien hecho (verificado leyendo el código)

- **Marca.**
  - Paleta exacta `#1340B1/#FED00F/#0E2A6B` en `primary_variables.scss`.
  - El amarillo solo vive sobre azul (anuncios, socios, pie, hover del flotante), navy o el hero oscurecido.
  - CTA primario azul sobre claro; Anton/Oswald/Inter con la jerarquía correcta.
  - Sin degradados; el único «efecto» es el vidrio pedido por la dueña.
- **Contraste medido.**

  | Par | Ratio |
  |---|---|
  | azul/blanco | 8.76 |
  | azul/hueso | 7.77 |
  | gris `#4A5163`/blanco | 7.93 |
  | gris/hueso | 7.03 |
  | navy/amarillo | 9.12 |
  | amarillo/azul | 5.94 |
  | blanco/azul | 8.76 |
  | blanco sobre hero (peor caso: foto al 45 % sobre negro) | 4.81 |
  | blanco sobre vidrio ahumado | 7.46 |

  Los comentarios de `dcasa.scss` (7.9:1 y 7.1:1) son exactos.
- **Teclado y foco.** `:focus-visible` de 3 px en cada superficie, con el color correcto por fondo; en el
  botón flotante, doble anillo blanco + navy; en las reseñas, detención de la cinta con el foco
  (`dcasa.scss:1525`); `scroll-padding-top` (2.4.11); objetivos de 44-48 px; `aria-label` con el nombre
  del producto en «Agregar» y en WhatsApp (contiene el texto visible, 2.5.3).
- **Movimiento.** Bloque `prefers-reduced-motion` completo (hero, reseñas, transiciones, gota, reflejo); las
  animaciones de entrada no corren sin JS ni en el editor ni al imprimir; pausa de la cinta (2.2.2); la
  cinta se detiene al pasar el puntero.
- **Semántica.** Un `h1` por página, landmarks (`aside`, `region`, `address`), `alt=""` en decorativas y
  descriptivos en el resto, iconos con `aria-hidden`, `title` en el iframe, `autocomplete` en contacto.
- **Rendimiento.**
  - Hero WebP con `srcset` 800/1400, `fetchpriority=high`, sin `lazy`, dimensiones fijas (CLS 0 documentado).
  - Todas las imágenes de portada en WebP (900 KB en total) con `width/height`, `lazy` y `decoding=async`.
  - Tarjetas con `image_512` y URL con hash.
  - JS propio de 9.6 KB, como Interactions de Odoo 19 con limpieza.
- **SEO.**
  - Título y descripción propios de portada, `/shop` y `/visitanos`.
  - `FurnitureStore` con `@id`, sin campos vacíos y sin `priceRange` inventado; `json_scriptsafe` (con test de
    `</script>`).
  - `/visitanos` en sitemap; `/whatsapp`, `/dcasa/carrito/agregar` y rutas de sesión con `sitemap=False`.
  - Idioma único `es_419` (sin hreflang espurios).
  - Menú corto con nombres iguales en todos los idiomas.
- **Tienda en Panamá.**
  - Sitio en español; ZIP no requerido; país por defecto Panamá.
  - Tres pagos sin pasarela con mensaje de WhatsApp (sin números de cuenta en el código).
  - Retiro en tienda + domicilio «por cotizar» (nunca «Gratis», `dcasa.scss:1846`); se apagó la «garantía
    de 30 días / envío 2-3 días» inventada de Odoo.
  - «Agregar» en un clic sin JavaScript y con las mismas reglas de Odoo; redirección `/whatsapp` segura.
  - Botón flotante oculto en carrito/checkout (evita el problema #25 de AUDITORIA_UX) y en la ficha móvil.
- **Catálogo.** Medidas «solo cuando están impresas en la foto» (115 de 199), combo en campo aparte con
  etiqueta, precios copiados (nunca calculados), idempotente y sin pisar lo que edite la dueña, 11 productos sin
  foto no publicados, búsqueda por varias palabras.
- **Honestidad.** Las reseñas llevan su enlace verificable, no hay `aggregateRating` inventado, no se inventa
  horario (`test_website_dcasa.py:301`).

## 5. Estado de `docs/AUDITORIA_UX.md` (solo las filas del sitio), contrastado con el código

| Estado | Filas |
|---|---|
| **Resuelto en código** | #1 pagos, #2 idioma, #7 entrega, #8 precios en combo aparte, #18 dirección Panamá (salvo RUC, ver SW-08), #19 WhatsApp primero en la ficha, #23 tamaño King, #25 flotante fuera del checkout, #29 hero sin `lazy`, #56 «Quick reorder», #63 categoría TV, #88 `scroll-padding`, #92/#68 flotante y relleno del pie |
| **Abierto o parcial** | #6 ficha sin material/color/garantía (solo medidas en 115/199), #55 (SW-12), #62 h1/chips de categoría *(por verificar)*, #66 (SW-02), #86 comparador (sin override en el módulo), #27/#28 imagen y CLS de la grilla (no hay override de `products_item`; medir en navegador), #44/#64 fotos verticales y anotaciones en chino (catálogo, decisión dueña en duplicados), #65 horario (intencional, pedirlo) |
| **Decisión documentada** | #24 reseñas (30/09), #69 vidrio (pedido de la dueña) |

## 6. Plan de arreglo ordenado

1. **Antes de publicar (bloquean):** SW-04 (ITBMS), SW-03 (descripción de Google, financiamiento, comedores,
   tarjeta), SW-02 (políticas + RUC), SW-01 (privacidad, cookies, fuentes y mapa), SW-05 (fotos reales).
2. **Primera semana:** SW-08 (RUC en checkout), SW-09 (tarjeta de TV), SW-07 (navy en enlace activo), SW-06
   (refracción solo en escritorio, con medición), SW-10 (fuentes propias), SW-11 (TTFB con `infra`).
3. **Pulido:** SW-12 a SW-21 y completar fichas (material, color) desde `fichas.json`.
4. **Verificar con navegador real** (lo que esta auditoría no pudo): Lighthouse móvil sobre `/` y `/shop`,
   320 px, Rich Results Test de una ficha (SW-13), contraste real del vidrio (SW-07) y h1 de categorías.

## 7. Coordinación

- `@seguridad`: SW-01 (CSP, cookies, terceros); confirmar que el formulario de contacto público tiene
  protección antispam (Turnstile de Odoo) *(por verificar)*. No hallé XSS en el código del sitio: todo va con
  `t-out`, y el único JSON en `<script>` usa `json_scriptsafe`.
- `@infra`: SW-11 y SW-20.
- `@contabilidad`: SW-04 y SW-08.
