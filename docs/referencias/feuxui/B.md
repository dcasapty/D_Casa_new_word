# Informe B — Tipografía y composición: Feuxui frente a D'CASA

Auditora: letra **B** · 17 conceptos (5 de tipografía y 12 de composición) · fecha de las mediciones: 2026-11-20.

## Cómo se hizo (y qué no se pudo medir)

- Leí completos los 17 textos de Feuxui antes de mirar D'CASA. Sus cifras están en cada concepto. Una advertencia justa: Feuxui enseña con
  afiches de 1080 px y piezas de redes. Sus reglas («máximo dos fuentes», «tres tamaños bastan», «5–10 % del lado corto») son
  guía para esas piezas; en una tienda en línea hacen falta más niveles. Lo aplico igual, pero lo digo cuando pesa.
- Sitio en vivo con Chromium: portada, categoría (`/shop/category/salas-1`), ficha (`/shop/cama-king-black-2806-8`), carrito vacío,
  `/visitanos` y `/terminos`, a **1440 px** y a **390 px**. En total **27 cargas de página (solo GET)**, con pausa de 1 s entre cargas.
  No envié formularios ni escribí en el chat de Andrés ni toqué el panel.
- Medí con `getComputedStyle` y con las cajas reales de los elementos. Dos pruebas (el tracking del titular y las tildes en 2 líneas) las
  hice **en mi navegador, sobre la página ya cargada**: cambié el estilo allí y fotografié. No se escribió nada en producción.
- Capturas y datos: `$S/feux/capturas_B/` (`$S` = `/tmp/claude-0/-home-user-D-Casa-new-word/df109763-bd03-5083-be8c-fbf5e389a556/scratchpad`).
  Los JSON `portada_1440.json`, `producto_390.json`, etc., traen cada texto con su fuente, tamaño, interlineado y posición.
  Los scripts están en `$S/feux/scripts_B/`.
- **No pude medir**: la composición de cada foto del carrusel de la portada (solo vi la que cargó: la cama de cabecero azul);
  el panel interno de Odoo en vivo (solo código y capturas anteriores: `$S/capturas/4_inicio_celular.png`); otros anchos de pantalla.
  El contraste de color no es mío (lo cubre otra letra).
- Aviso de método: cuando digo «1440 px» uso una ventana de 1440 × 900; «lado corto» en escritorio es entonces 900 px, y lo calculo
  también contra el ancho para no esconder nada.

### La escala tipográfica real del sitio (medida)

| Papel | 1440 px | 390 px | Interlineado | Tracking | Fuente |
|---|---|---|---|---|---|
| Titular de portada (h1) | 104 px | 48 px | 1.02 | +0.5 % | Anton |
| Titular de página interior (h1) | 64 px | 36 px | 1.02 | +0.5 % | Anton |
| Titular de la banda «de cine» | 60 px | 36 px | 1.02 | +0.5 % | Anton |
| Título de sección (h2) | 40 px | 28 px | 1.02 | +0.5 % | Anton |
| Título de ficha (h1) | 32 px | 24.7 px | 1.05 | +0.5 % | Anton |
| Subtítulo de portada | 20.2 px | 16.8 px | 1.55 | 0 | Inter |
| Cuerpo | 16 px | 16 px | 1.5 | 0 | Inter |
| Texto legal (largo) | 17 px | 17 px | 1.7 | 0 | Inter |
| Botones grandes | 20 px | 16 px | — | +6 % / +3 % | Oswald 500, mayúsculas |
| Antetítulo (kicker) | 13–14 px | 13–14 px | — | +14 % | Oswald 500, mayúsculas |
| Precio de tarjeta | 20 px | 20 px | 1.1 | 0 | Oswald 600 |
| Nombre de producto en tarjeta | 15 px | 14 px | 1.35 | 0 | Inter 500 |

- **Tamaños distintos en una sola página:** la portada usa **17 a 1440 px** (12, 12.8, 13, 14, 14.4, 15, 15.2, 16, 17.6, 18.7, 20, 20.2, 24,
  29.6, 40, 60, 104) y **18 a 390 px**. Ficha: 8. Carrito: 7. Categoría: 7. Visítanos: 7.
- Siete de esos tamaños caen entre 12 y 15.2 px: una «cola» de diferencias de décimas (15 y 15.2; 12.8 y 13; 14 y 14.4; 20 y 20.2).
- En el código hay **37 expresiones de `font-size` distintas en 70 declaraciones** (`addons/website_dcasa/static/src/scss/dcasa.scss`),
  10 valores de `letter-spacing` y 10 de `line-height`.
- **Reparto del texto visible por fuente (por caracteres, portada a 1440):** Inter 72 %, Oswald 24 %, Anton 4 %. En ficha, carrito y
  visítanos: Inter 64–73 %, Oswald 25–33 %, Anton 2–3 %.
- **Familias de texto cargadas realmente en el navegador:** Anton, Oswald, Inter (más dos fuentes de íconos, FontAwesome y odoo_ui_icons,
  que no son texto). Pie de la pila del `body`: «Odoo Unicode Support Noto», solo para glifos que falten. No se cuela ninguna cuarta
  familia de texto en el sitio público.

---

## TIPOGRAFÍA

### 1 · Combinación tipográfica
- **La regla de Feuxui:** «Máximo dos fuentes»: una con carácter para el titular y una simple para leer. Contraste, no parecido (dos
  sans casi iguales parecen un error). Antes de sumar una tercera, juega con los pesos.
- **D'CASA hoy:** usa **tres** familias, por regla de marca (CLAUDE.md, regla 2; `primary_variables.scss:70-92`: Anton para titulares,
  Oswald para h3-h6, menú y botones, Inter para el cuerpo). Cada una tiene un trabajo claro y casi no se pisan: Anton solo titulares
  grandes (2–4 % del texto visible), Oswald etiquetas, botones y precios (24–33 %), Inter la lectura (64–73 %). El par Anton + Inter
  cumple la fórmula de Feuxui al pie de la letra (carácter arriba, simple para leer). **Anton y Oswald, en cambio, son dos tipografías
  condensadas de palo seco, hermanas de aspecto**: por eso funcionan solo porque se separan por tamaño (Anton 32–104 px, Oswald 12–20 px),
  por tracking (+0.5 % contra +6 a +14 %) y por color. En las capturas se leen distintas, pero es justo lo que Feuxui llama «dos
  parecidas». Se descargan 74 KB entre las tres (`fuentes.scss:9-11`).
  En el panel interno de Odoo la pila es solo Inter (`dcasa_base/static/src/scss/primary_variables.scss:8`), con Anton en unas pocas cifras;
  ahí sí se cumple el «máximo dos».
- **Veredicto:** 🟡 cumple a medias. Tres familias contra el máximo dos, dicho con honestidad: no es un descuido, es la marca; y sus trabajos
  están bien repartidos. ⚠ **Quitar Oswald choca con la marca (regla 2).**
- **Qué haría:** nada que cambiar mientras la regla 2 mande. Si Gerencia quisiera probarlo: Anton + Inter, y las etiquetas, botones y menú
  en Inter 600–700, mayúsculas, +6 %. Ahorra una fuente (21 KB) y un riesgo de «parecidas», pero cambia la personalidad. Esfuerzo
  medio (toca unas 23 reglas de Oswald en `dcasa.scss`), riesgo de marca alto. Mi recomendación: dejarlo como está.

### 2 · Énfasis
- **La regla de Feuxui:** un solo protagonista, con tamaño, color o movimiento; por lo menos el doble de grande que lo demás; el color de
  acento solo en el protagonista. Prueba del vistazo: entrecierra los ojos.
- **D'CASA hoy:**
  - **Portada, primera pantalla: ✅.** El titular mide 104 px; lo siguiente más grande en pantalla es el subtítulo de 20.2 px (5 veces) y
    el menú de 15.2 px. El único color de acento fuerte es el amarillo del botón «Ver el catálogo» (más el enlace amarillo de la barra
    azul de arriba). El botón de WhatsApp va en contorno blanco y baja a segundo plano. Captura: `portada_1440_arriba.png`.
  - **Ficha, 1440 px: 🟡.** Dos cosas azules y fuertes compiten: el título (Anton 32 px, azul) y el botón a todo el ancho «Pregunta por
    este mueble por WhatsApp» (520 × 52 px, relleno azul). El precio (Oswald 20 px) queda tercero. En celular, título 24.7 px contra
    precio 20 px: solo 1.24 veces. Captura: `producto_1440_completa.png`.
  - **Categoría: 🟡.** No hay protagonista: la primera cosa de la página es la miga de pan y el buscador. El título «Salas» existe en el
    HTML pero está oculto (es la opción de Odoo «mostrar título de categoría», apagada; `website_sale.scss:83-86` del vendor).
  - **Banda «de cine»:** su titular mide 60 px y el de «Lo más buscado» (la sección donde se vende) mide 40 px (`dcasa.scss:2273-2275`
    contra `:72-76`). Es decorativo, pero le quita rango a los productos.
- **Veredicto:** ✅ cumple en la portada; 🟡 en ficha y categoría.
- **Qué haría:** (a) mostrar el título de cada categoría desde el editor del sitio (opción por categoría, sin código; verificar que la
  dueña lo vea). Esfuerzo poco, riesgo nulo. (b) Nada en la portada. (c) Hay una tensión con la marca que decide Gerencia: ⚠ **regla 5
  (CTA único: Escríbenos por WhatsApp)**. El amarillo protagonista del hero es «Ver el catálogo», no WhatsApp; si se aplicara el énfasis
  literal, el botón amarillo sería el de WhatsApp. No lo cambio por mi cuenta.

### 3 · Jerarquía visual
- **La regla de Feuxui:** tres niveles (titular, subtítulo, texto) con una escala fija: cada escalón ×1.5 (32, 48, 72, 108). «Si necesitas
  un cuarto nivel, te sobra contenido.» Antes de publicar: ¿máximo 3 tamaños de texto?
- **D'CASA hoy:** los tres niveles **se leen**: titular Anton (40–104 px), subtítulo/etiqueta Oswald (13–20 px) y texto Inter (16–20 px).
  Pero no hay una razón fija entre escalones: 16 → 24 → 40 → 60 → 104 da saltos de ×1.5, ×1.67, ×1.5 y ×1.73. Y la cola de
  tamaños chicos (siete valores entre 12 y 15.2 px; ver tabla) no tiene función distinta: son décimas. Total **17 tamaños** en la portada
  frente a los «3» de Feuxui. Hay además tres tamaños de «h2» en la misma portada: 60 px (cine), 40 px (secciones) y 29.6 px
  (¿Te quedó alguna duda?, `dcasa.scss:1583`). Es justo reconocer que una tienda necesita más que un afiche: precio, ITBMS, estado,
  etiquetas. Pero 17 es mucho.
  Lo que sí está bien: cuerpo a 16 px/24 px; el título de portada a 6.5 veces el cuerpo es una jerarquía clara.
  Panel interno: el acceso del Inicio tiene solo dos niveles (título 16 px/700, subtítulo 12.8 px al 82 %; `dcasa_interfaz/.../interfaz.scss:178-193`).
  Aun así `interfaz.scss` declara 22 tamaños distintos.
- **Veredicto:** 🟡 cumple a medias: la jerarquía se entiende, la escala no tiene método.
- **Qué haría:** definir una escala con nombre, por ejemplo `xs 12 / sm 14 / md 16 / lg 20` para texto y `h2 40 / h1 64–104` para
  titulares, y colapsar primero los duplicados que difieren menos de 0.5 px (15/15.2, 12.8/13, 14/14.4, 20/20.2). Es la mitad del beneficio
  con un cuarto del trabajo. Esfuerzo **poco** para los duplicados (cambio de valores en `dcasa.scss`); **medio** para los 37 valores
  completos. Riesgo bajo: cambios de décimas. No choca con la marca.

### 4 · Tracking y espaciado entre letras
- **La regla de Feuxui:** más grande, más cerrado. Titular de 60 px o más: **−2 a −5 %**. Subtítulo de 24 a 48 px: −1 a −2 %. Párrafo de 14 a 18
  px: 0 %. Menos de 12 px: 0 a +2 %. Etiqueta, botón y menú en mayúsculas pequeñas: **+5 a +10 %**.
- **D'CASA hoy (medido):**
  - **Titulares Anton a +0.5 % en todos los tamaños** (`dcasa.scss:62`; `:1904` para la ficha): hero 104 px, cine 60 px, interior 64 px,
    h2 de 40 px, ficha 32 px. Feuxui pide −2 a −5 % (≥60 px) y −1 a −2 % (24–48 px): D'CASA va al revés, unos 2.5 a 5.5 puntos de
    diferencia.
  - **Párrafos en Inter a 0 %** en todo el sitio (cuerpo, subtítulos, legales): ✅.
  - **Etiquetas, botones y menú:** menú +6 %, botones grandes +6 % (celular +3 %), barra de anuncios +8 % (celular +3 %), etiquetas
    de categoría +5 %: ✅ o muy cerca. Los antetítulos van a **+14 %** (`dcasa.scss:83`), cuatro puntos sobre el techo de Feuxui. Las
    píldoras de la banda de cine, +12 % a 11 px en celular (`dcasa.scss:2393-2410`).
  - **Prueba en mi navegador con el titular real del hero** (`tracking_h1_*.png`): la primera línea «TU CASA, BIEN» mide 537 px a +0.5 %,
    530 px a 0 %, 503 px a −2 % y 476 px a −4 %. A **−2 % se ve más sólido y limpio**; a **−4 % las letras L-A-D de «AMUEBLADA» ya casi se
    tocan**. O sea: Feuxui dice «el punto justo ronda −4 %» para fuentes comunes, pero Anton ya es una fuente condensada y cerrada de
    fábrica; su límite práctico está más cerca de −2 a −3 %.
- **Veredicto:** 🟡 cumple a medias: párrafos ✅ y etiquetas ✅; **titulares ❌**.
- **Qué haría:** Anton ≥ 60 px a **−0.02em** (hero, cine, interior); h2 de 40 px y ficha a **−0.01em**. Esfuerzo **poco** (dos o tres líneas:
  `dcasa.scss:62` separando `.o_dcasa_display` de `.o_dcasa_h2`, y `:1904`). Riesgo bajo; ningún test fija el tracking (revisé
  `tests/`). Antetítulos de +.14em a +.10em (`:83`), opcional. No choca con la marca.

### 5 · Interlineado
- **La regla de Feuxui:** párrafos a 1.5 (1.4–1.6; si la columna es ancha, 1.6); titulares casi a 1 (0.9–1.1); subtítulos 1.1–1.3; botones y UI de una
  línea 1.2. **Cuida las tildes:** al cerrar un titular, que las tildes y la Ñ no choquen con la línea de arriba. Más aire entre párrafos que
  entre líneas.
- **D'CASA hoy (medido):** titulares Anton a **1.02** (ficha y CTA 1.05); cuerpo 1.5; subtítulo del hero 1.55; texto legal **1.7** en una
  columna de 706 px (unos 80 caracteres por renglón, estimado, no contado: Feuxui dice que con columna ancha se sube, y D'CASA sube); reseñas 1.6; nombre de
  producto 1.35 (dos o tres renglones; `dcasa.scss:1185`). Entre bloques de texto largo: 12 px bajo cada título legal y unos 40 px antes del siguiente (3.3
  veces), mientras el aire entre líneas del párrafo es 11.9 px: ✅.
  **Prueba de las tildes** (`tildes_anton.png`, hecha en mi navegador con la fuente real): con `line-height: 1.02`, las tildes de una segunda
  línea (Ó, Í, É) **tocan la base de las letras de la línea de arriba**; con 1.1 hay un respiro mínimo. En los titulares que hoy tiene el
  sitio no hay choque (por ejemplo el de la portada no lleva tilde en el segundo renglón), pero la dueña edita esos textos y el día que
  ponga «… en LA CÁMARA» abajo, chocará. Excepciones sueltas: el título del carrito vacío va a 1.2 y sin el tracking del sistema
  (distinto de todos los demás Anton).
- **Veredicto:** ✅ cumple (con un riesgo conocido en las tildes).
- **Qué haría:** subir los titulares Anton de 1.02 a **1.08** (dentro del rango 0.9–1.1; `dcasa.scss:63`, `:1905`). Cuesta unos 8 px por renglón
  en el hero de 104 px. Esfuerzo **poco**, riesgo bajo. Nombre de producto a 1.4 (`dcasa.scss:1185`). Igualar el título del carrito vacío al
  sistema Anton (1.08 y mismo tracking). No choca con la marca.

---

## COMPOSICIÓN

### 6 · Grilla
- **La regla de Feuxui:** cada elemento empieza y termina en una línea de la grilla. 4 columnas para celular, 12 para web. Medianil siempre igual
  (20–30 px en post; margen 60–90 px en post). «Más columnas no es mejor.»
- **D'CASA hoy:**
  - **Tienda y categoría: una grilla real de 12 columnas** (`o_wsale_products_grid_table grid`: 12 columnas, medianil 16 px, filas 32 px,
    tanto a 1440 como a 390). Las tarjetas ocupan 3 columnas de 12 (226.5 px). ✅ en el espíritu de Feuxui.
  - **Portada: no hay una sola grilla; cada bloque trae la suya.** Categorías y galería: 6 columnas de 210.7 px con medianil 16 px. Beneficios:
    4 columnas de 321 px con medianil 20/24 px. Carril de productos: 5 tarjetas a la vista (el ancho se calcula, `dcasa.scss:1041-1062`; a 1440 sale 256 px), medianil 16 px (5 × 256 + 4 × 16 =
    1344 px, justo el ancho del contenido). Bloques foto/texto: 2 × 636 px con medianil **72 px**. Banda de cine: 400 px y 934 px con medianil 57.6
    px. Los bordes de afuera (x = 48 y x = 1392) coinciden en todos; las líneas interiores no se comparten (la mitad del bloque foto/texto cae
    en x = 684/756 y ninguna otra sección tiene una columna ahí).
  - **Medianiles en celular, en la misma portada:** 8 (galería), 10 (categorías), 12 (carriles), 16 (filas), 17.6 (beneficios) y 32 (bloques).
  - Contenedor: `max-width: 1440px` con relleno `clamp(1rem, 4vw, 3rem)` (`dcasa.scss:40-45`): 48 px de margen a 1440, 16 px a 390.
  - Espaciado (Feuxui: múltiplos de 8): en `dcasa.scss` muchos valores no caen en la escala de 8 (.35, .6, .85, .9, 1.1 rem = 5.6, 9.6, 13.6,
    14.4, 17.6 px).
- **Veredicto:** 🟡 cumple a medias: tienda ✅, portada con bordes comunes pero sin columnas comunes ni medianil único.
- **Qué haría:** no inventar una grilla nueva. Fijar **dos medianiles** (16 px entre tarjetas, 32 px entre bloques) y usarlos como variables;
  en celular, uno solo para las grillas de tarjetas (12 px). Los medianiles de la portada están en cinco lugares (`dcasa.scss:869`, `:873`, `:926`, `:930`, `:1041-1045`). Esfuerzo **poco a medio**, riesgo bajo (hay capturas de contrato visual por revisar). No choca con la marca.

### 7 · Márgenes
- **La regla de Feuxui:** mismo margen en los cuatro lados; **entre el 5 y el 10 % del lado más corto**; margen mayor que el espacio entre elementos. Web:
  celular **16 a 24 px**; en computador, contenido centrado con ancho máximo de unos 1200 px.
- **D'CASA hoy (medido):**

| Dónde | Margen lateral | % del ancho | % del lado corto |
|---|---|---|---|
| Portada, secciones, 1440 × 900 | 48 px | 3.3 % | 5.3 % (contra 900 px de alto) |
| Portada, 390 px | 16 px | 4.1 % | 4.1 % |
| Tienda, ficha y pie, 390 px | 15 px | 3.8 % | 3.8 % |
| Cabecera (píldora), 390 px | 8 px (su contenido arranca a 28 px) | 2.1 % | 2.1 % |
| Texto de la barra de copyright, 1440 px | 75 px | 5.2 % | 8.3 % |
| Ficha, galería, 1440 px | 75 px | 5.2 % | 8.3 % |
| Ficha, miga de pan, 1440 px | 123 px | 8.5 % | 13.7 % |

  - En celular D'CASA queda dentro de lo que Feuxui da en píxeles (16 a 24 px) pero **debajo de su regla rápida del 5 %** (19.5 px). Se
    ve cómodo en las capturas; no lo marco como falla.
  - **Contenedor de escritorio:** 1440 px de ancho máximo (contenido de 1344 px), contra los «unos 1200 px» de Feuxui. Los textos largos
    sí van angostos (subtítulo 36 rem, texto de cine 26 rem, legal 706 px), así que la lectura no sufre.
  - **El margen no siempre es mayor que el espacio entre elementos:** en celular el margen es 16 px y los beneficios van a 17.6 px entre sí y
    los bloques foto/texto a 32 px. En escritorio, el margen de 48 px es menor que el medianil de 72 px de los bloques foto/texto.
  - **Zona segura:** el botón flotante de Andrés (unos 75–80 px, abajo a la derecha, a unos 23–24 px del borde a 1440 px) **tapa texto** en la ficha a 390 px: el aviso
    «También en combo… Combo con colchón $339.99. Pídelo por WhatsApp» queda debajo de la burbuja en la primera pantalla
    (`producto_390_arriba.png`).
  - Hay 15 px (Odoo) en tienda/pie y 16 px (D'CASA) en portada: un píxel de diferencia sin motivo.
- **Veredicto:** 🟡 cumple a medias (la portada es pareja; el resto de páginas, no).
- **Qué haría:** (a) 15 → 16 px en celular para tienda, ficha y pie (`$dcasa-gutter` también en `.container` de Odoo): poco. (b) Dejar libre la
  zona de la burbuja en la ficha móvil (un relleno a la derecha del aviso o subir la burbuja sobre la barra fija): poco, riesgo bajo. (c) Los márgenes
  desiguales de escritorio se resuelven en el concepto 8. No choca con la marca.

### 8 · Alineación
- **La regla de Feuxui:** elige un eje y respétalo; cada borde toca una línea que otro también toca. Izquierda por defecto para textos largos; centro
  solo en piezas de máximo tres líneas; **nunca justificado**.
- **D'CASA hoy (medido, borde izquierdo a 1440 px):**
  - **Portada, secciones y pie: x = 48** en todas (cabeza de sección, tarjetas, columnas del pie). ✅
  - **Titular de la portada: x = 96** (`dcasa.scss:843`: `padding-left: clamp(2rem, 7vw, 6rem)`). Es el único texto a 96 en las páginas que medí:
    las cabeceras interiores (`/visitanos`, `/terminos`) arrancan a 48.
  - **Píldora de la cabecera: borde en x = 60 y logo en x = 80**; ninguno es 48 ni 96 (a 390 px: borde en x = 8, contenido de la píldora desde x = 28, contra 16 del contenido de la página).
  - **Barra del copyright: texto a x = 75** contra 48 de las columnas del pie justo encima. El código intentó unirlas
    (`dcasa.scss:1884-1891`: «Mismo borde izquierdo que la portada en las páginas de Odoo y en el pie»), pero esa regla no incluye la franja del
    copyright y su selector `.oe_website_sale > .container` no encuentra nada en Odoo 19 (el contenedor lleva la clase en el mismo elemento).
  - **Categoría y ficha:** filtro y miga de pan a x = 123; galería a x = 75; título de ficha a x = 780. En la ficha la **miga de pan (123) no cae sobre
    la galería (75)**. Carrito: a x = 75.
  - **Borde derecho de la ficha:** el bloque «También en combo» mide 585 px de ancho y se pasa 65 px de los demás (520 px: botón de WhatsApp,
    sellos, cantidad). Se ve en `producto_1440_completa.png`. Origen: `dcasa_catalogo/views/product_templates.xml:31-40`.
  - **Alineación del texto:** casi todo a la izquierda. El centro aparece solo en etiquetas de botón y en el carrito vacío (título y una línea).
    No hay texto justificado (revisado en el código: ninguna regla `justify`). ✅
  - Dentro de la tarjeta de producto, nombre, precio y botones comparten un solo borde (x = 63): ✅.
- **Veredicto:** 🟡 cumple a medias: en la portada hay **cinco ejes izquierdos** (48, 60, 80, 96 y 75) dentro de una franja de 48 px; en la tienda, cuatro
  (48, 75, 80, 123).
- **Qué haría, por costo:**
  1. Titular de la portada al mismo borde que el resto: `padding-left` de `clamp(2rem, 7vw, 6rem)` a `$dcasa-gutter` (`dcasa.scss:843`). **Poco**, riesgo bajo
     (los tests del hero miden fotos, capas y colores, no la x del texto).
  2. Agregar `.o_footer_copyright .container` a la regla de `dcasa.scss:1884-1887`. **Poco**.
  3. Bloque «También en combo» al ancho de los demás (`max-width` en `.o_dcasa_ficha_datos`, `catalogo.scss:2`). **Poco**.
  4. Arreglar la regla de `dcasa.scss:1884-1891` para el contenedor de tienda (cuenta de Odoo 19): breadcrumb, filtros y galería a 48 px. **Medio**,
     riesgo medio (la barra lateral del filtro y la ficha tienen anchos propios; probar a 390, 768 y 1440).
  5. Opcional: alinear el logo de la píldora con el contenido (hoy 80 contra 48; hay un test que mide la píldora, revisarlo antes). **Medio**.
  No choca con la marca.

### 9 · Proximidad
- **La regla de Feuxui:** lo cercano se lee junto. Dentro de un grupo, 8–16 px; **entre grupos, por lo menos el doble** (escala 8, 16, 32, 64). Cada
  titular, pegado a su texto. «Foto con nombre, precio con botón.»
- **D'CASA hoy (medido):**
  - **Hero: ✅ clavado.** Antetítulo → titular: 9 px; titular → subtítulo: 17 px; subtítulo → botones: 32 px. Es exactamente 8–16 dentro y 32 entre grupos.
  - **Cabeza de sección: ✅.** Antetítulo a 6.4 px del título; título a 28 px del contenido; 72 px de aire hacia arriba y abajo de cada sección
    (`dcasa.scss:19,134`).
  - **Texto legal: ✅.** Título a 12 px de su texto; 40 px de aire antes de cada título nuevo (3.3 veces).
  - **Tarjeta de producto, portada a 1440 px: 🟡.** Foto → nombre 12 px; nombre → fila de precio y botones 10 px; relleno lateral 14 px. El **precio
    comparte fila con los dos botones** (grupo «precio con botón», bien), pero el aire entre nombre y precio (10 px) no es el doble de nada: todo está a 8–14 px.
  - **Tarjeta a 390 px: 🟡.** Nombre (hasta tres renglones) → precio 8 px; precio → botones 10 px: los tres bloques quedan a la misma distancia.
  - **Tarjeta de la tienda (categoría): 🟡.** Foto → nombre 8 px, nombre → precio 8 px, precio → botón 8 px (`categoria`, medido en `cadenas.cjs`).
  - **Ficha, columna derecha a 1440 px:** título → código 16 px; código → precio 18 px; precio (y su etiqueta «Disponible») → bloque de combo 24–26 px; combo → botón de WhatsApp 49 px;
    botón → sellos 16 px; sellos → «Agregar al carrito» 16 px. El grupo título-código-precio queda bien junto. Pero **el precio (y 292) y el botón de compra
    (y 683) quedan a 391 px de distancia** con el combo, el WhatsApp y los sellos en medio. En celular se arregla con la barra fija de abajo (cantidad y
    «Agregar» a la vista junto al precio: precio en y = 659, barra en y = 771, captura `producto_390_arriba.png`).
  - **Dos diseños de tarjeta para el mismo producto:** en la portada (nombre 15 px/500, precio 20 px, botones redondos) y en la tienda (nombre 16
    px/600, precio 17.6 px, un botón ancho «Agregar al carrito»): el mismo mueble se presenta con jerarquías distintas.
- **Veredicto:** ✅ en las zonas grandes (hero, secciones, legal); 🟡 en tarjetas y ficha.
- **Qué haría:** en la tarjeta, separar el nombre del precio con 16 px (hoy 10) y dejar 8 px entre precio y botones: `dcasa.scss:1187` (`margin-bottom: .625rem` →
  `1rem`). Poco, riesgo bajo (la tarjeta de la portada crece unos 6 px; la tarjeta de la tienda tiene su propio espaciado, `dcasa.scss:1938-1950`). Mover el
  bloque de combo bajo los sellos y acercar «Agregar al carrito» al precio en escritorio: medio. No choca con la marca.

### 10 · Lectura en Z
- **La regla de Feuxui:** poco texto → Z: logo arriba a la izquierda, dato corto arriba a la derecha, mensaje en la diagonal y **botón abajo a la derecha**. Mucho
  texto → F. Aplica a portadas y páginas de inicio.
- **D'CASA hoy:**
  - **Portada, primera pantalla a 1440 px** (`portada_1440_arriba.png`): 1 arriba a la izquierda, logo (x = 80, y = 66): ✅. 2 arriba a la derecha: carrito, buscador y «Mi cuenta»
    (utilidad, no el dato más útil) y, en la barra azul, el enlace **amarillo** «Escríbenos por WhatsApp» (x = 894–1077), lo más fuerte de esa zona: 🟡 parcial.
    3 diagonal: el titular de 104 px y, detrás, el degradado azul a 118° que va de arriba-izquierda hacia abajo-derecha: ✅. 4 abajo a la derecha: **no hay botón**; está la burbuja de Andrés
    (80 px, x = 1337–1417, y = 796–876). Los botones del hero cierran **abajo a la izquierda del bloque de texto** (x = 96–679, y = 596–657).
    Esto sigue otra regla de Feuxui, la de alineación («si el titular va a la izquierda, el botón también»): las dos reglas chocan entre sí y D'CASA eligió alinear.
  - **Portada, resto: F.** Cabeza a la izquierda con «Ver todo →» al extremo derecho de la misma fila (`.o_dcasa_section_head`, `justify-content: space-between`):
    pequeña Z dentro de cada sección. Es lo que ya planteaba `docs/historico/REDISENO.md` («El ojo recorre la pantalla en F»).
  - **Tarjeta de producto:** foto arriba, nombre, precio a la izquierda, **botones de carrito y WhatsApp abajo a la derecha**: la Z de Feuxui, tal cual. ✅
  - **Ficha:** miga de pan arriba a la izquierda; foto a la izquierda; título y precio arriba a la derecha; «Agregar al carrito» abajo a la derecha de la columna (y = 683–731, a la
    vista en 900 px de alto). En celular: precio y estado arriba, barra de compra fija abajo. ✅ para una página con más texto.
- **Veredicto:** 🟡 cumple a medias: tres de cuatro puntos; el punto 4 de la portada lo ocupa la burbuja de Andrés, no el botón.
- **Qué haría:** nada en el diseño. Dejar el botón con el texto (alineación primero). Si se quiere reforzar, que la burbuja se esconda mientras se ve el hero, como ya
  se hace con el botón flotante de WhatsApp (`dcasa.scss:848-853`), así la esquina de cierre queda limpia. Esfuerzo poco, riesgo bajo; es una decisión de Andrés/Gerencia.
  No choca con la marca (⚠ la regla 5 es lo único que pesa: un solo botón, el de WhatsApp).

### 11 · Simetría y asimetría
- **La regla de Feuxui:** simetría = calma (bodas, lujo, instituciones); asimetría = energía (deporte, moda, lanzamientos, redes), con el peso compensado. **Nunca a
  medias**: lo casi centrado parece un error.
- **D'CASA hoy:** el hero es **asimétrico con intención**: texto en el tercio izquierdo (x = 96–680) y la foto ocupando todo; la cama queda a la derecha. Los bloques foto/texto **se espejan** de
  una sección a otra («Te lo llevas hoy»: foto a la izquierda; «Socios»: foto a la derecha): peso compensado. La banda de cine reparte 400 px / 934 px (30 % / 70 %). Beneficios: 4 columnas
  iguales (simétrico, calma). Lo centrado es exacto y solo en lo utilitario: el menú de la cabecera está a x = 566/566 (centro 719.5 contra 720), el grupo de la barra de anuncios también; el
  carrito vacío es una columna centrada de 3 líneas (justo el caso que Feuxui permite). No encontré nada «casi centrado».
- **Veredicto:** ✅ cumple.
- **Qué haría:** nada que cambiar.

### 12 · Regla de tercios
- **La regla de Feuxui:** 3 × 3; lo importante en un cruce y algo que equilibre en el cruce opuesto; el horizonte fuera del centro; aire hacia donde mira el sujeto. Es un punto de partida, no
  una ley («siempre hay que usarla: no»).
- **D'CASA hoy (1440 × 900):** las líneas de tercios están en x = 480 y 960, y = 300 y 600. El bloque de texto del hero ocupa el tercio izquierdo (x = 96–680); su primera línea del titular
  cruza la línea de y = 300 (titular de y = 273 a 485) y los botones empiezan en y = 596, a 4 px de la línea de y = 600. El bloque queda centrado verticalmente (centro en y = 450 de 900).
  Es decir, **el texto sigue los tercios de forma aproximada** (probablemente sin intención: ningún documento lo dice). **La foto no está bajo nuestro control:** son fotos de catálogo (a
  menudo verticales 3:4 o 9:16) recortadas con `object-fit: cover` y `object-position: 50% 42%` (`dcasa.scss:817`) y un zoom lento de 1.06 a 1.16: la cama cae
  cerca del centro de la pantalla. En celular el texto ocupa la mitad de abajo (y = 390–788 de 844) y la foto la de arriba.
  El resto de la portada no centra «todo»: títulos a la izquierda, bloques a un lado.
- **Veredicto:** 🟡 cumple a medias: el texto sí; la foto depende de qué foto entre al carrusel y no se pudo medir.
- **Qué haría:** nada en el código. Para el carrusel, regla de proceso: al subir fotos al hero, preferir las que dejan el producto en el tercio derecho y aire a la izquierda donde va el texto
  (el degradado azul ya lo supone). Esfuerzo poco (criterio de quien sube las fotos); riesgo nulo. No choca con la marca.

### 13 · Tensión visual
- **La regla de Feuxui:** un desequilibrio pequeño y a propósito: algo al borde, cortado, girado 5–15°, casi tocándose, tamaño extremo o diagonal. **Elige una o dos formas por diseño; el texto, ordenado.**
- **D'CASA hoy:** usa pocas, y bien: **corte** (el carril de productos deja asomar la siguiente tarjeta en celular: la tercera empieza en x = 352 de 390, unos 38 px visibles; las dos cintas de la banda de
  cine corren cortadas por el borde derecho, en sentidos opuestos), **tamaño extremo** (titular de 104 px frente a antetítulos de 14 px), **diagonal** (el degradado de 118° del hero, `dcasa.scss:767-775`) y
  **movimiento** (zoom lento de la foto). **No usa giros:** no hay una sola regla `rotate` ni `skew` en `dcasa.scss`. El texto va siempre alineado a la izquierda. Los distintivos «Agotado» y las
  píldoras de categoría están pegados a la esquina de la foto.
- **Veredicto:** ✅ cumple (con medida; la marca pide orden y confianza, no riesgo).
- **Qué haría:** nada. Si Gerencia quisiera más energía, una forma como máximo por pantalla: un titular a −5° o una foto que sangre por el borde; y avisar que el giro choca con el tono «ordenado y confiable»
  (voz de marca, regla 6; no es una regla escrita contra el giro, es una decisión de estilo).

### 14 · Encuadre
- **La regla de Feuxui:** rodear lo importante con una forma, líneas, espacio o luz, con un marco más simple que lo enmarcado; un solo elemento enmarcado.
- **D'CASA hoy:** las tarjetas de producto son un marco simple (filo de 1 px `rgb(227,225,219)`, esquinas de 16 px, **sin sombra**; medido) sobre fondo hueso, con la foto sobre un fondo de estudio `#EEEDEA`
  que enmarca las fotos anchas (`dcasa.scss:1311`). Las secciones alternan bandas blanco, hueso y azul noche con una banda amarilla de 14 px (`dcasa.scss:145-148`, eco del logo): cada banda enmarca su idea.
  En el hero, el degradado azul actúa de reflector sobre el texto y deja libre la cama. El espacio también encuadra: 72 px de aire en cada sección.
  Dos cosas flojas: (1) la **categoría** no tiene a quién enmarcar (no hay título visible); (2) en `/visitanos`, el marco del mapa es una caja gris de unos 750 × 560 px (medida sobre la captura `visitanos_1440_completa.png`) con un botón «Ver el mapa» (por el consentimiento
  de cookies de Google): mucho marco, poco dentro.
  Un ojo crítico: la píldora de la cabecera es un marco **más complejo que lo que enmarca** (cuatro textos y tres íconos dentro de una caja con `backdrop-filter: blur(16px) saturate(210%)` y un brillo en diagonal,
  `dcasa.scss:348-376`). Es la excepción al sistema plano.
- **Veredicto:** ✅ cumple. ⚠ El «luz con degradado» de Feuxui y el vidrio de la cabecera **chocan con la marca (regla 3, sistema plano)**; el degradado del hero es una decisión explícita de la dueña (2026-11-17).
- **Qué haría:** mostrar el título en la categoría (concepto 2). Nada más. Qué hacer con el vidrio de la cabecera lo decide Gerencia (otra letra lo cubre en «efectos»).

### 15 · Perspectiva
- **La regla de Feuxui:** dar profundidad con **escala** (cerca, grande), **superposición**, **punto de fuga** (formas o texto inclinados) y **desenfoque** de lo lejano. Con una herramienta ya se nota.
- **D'CASA hoy:** el sistema es plano a propósito. La profundidad viene de la **fotografía** (las camas y salas están fotografiadas en tres cuartos, con su propia perspectiva), de la **escala** (titular de 104 px
  frente a 14 px) y de la **superposición** (texto sobre foto en el hero, distintivos sobre fotos, burbuja de Andrés flotando, píldora de cabecera sobre el hero). El zoom lento de la foto (1.06 → 1.16)
  da sensación de avance. **No hay** texto inclinado hacia un punto de fuga, ni desenfoque del fondo, ni sombras de profundidad en el contenido: las tarjetas no llevan sombra (medido). Hay 7 `box-shadow` en `dcasa.scss`: tres en `none`, un aro de foco (`:2221`) y tres en
  la píldora de vidrio de la cabecera (`:351`, `:475`, `:523`), una de ellas con una sombra suave de 40 px de difusión (`0 16px 40px -24px`, solo cuando la cabecera va sobre foto oscura).
- **Veredicto:** ➖ no aplica a un sistema plano; las herramientas de escala y superposición ya están en uso. ⚠ **Desenfoque, degradado de atmósfera y sombras de profundidad chocan con la marca (regla 3)**; el texto
  inclinado a un punto de fuga no está prohibido por escrito pero rompe «plano y ordenado».
- **Qué haría:** nada. No lo recomiendo: la tienda vende fotografía de producto, y la perspectiva ya está en la foto.

### 16 · Balance óptico
- **La regla de Feuxui:** el ojo lee masa y forma, no medidas: un círculo se ve más chico que un cuadrado del mismo alto (círculo +8–10 %); el «play» va 1/6 hacia la punta; lo centrado en vertical se ve caído (súbelo un poco).
  «La medida es el punto de partida; el ojo tiene la última palabra.»
- **D'CASA hoy (medido a 4× de zoom):** los íconos dentro de los botones redondos de 48 px quedan centrados con diferencias menores a 1 píxel real: el carrito, a 0.1 px a la derecha y 0.4 px abajo; el ícono de WhatsApp,
  a 0.7 px a la izquierda y 1 px arriba (`optico_par.png`). Se ven bien. El menú de la cabecera está al centro exacto (566 px a cada lado). Las fotos anchas de producto (`object-fit: contain`) van al centro geométrico del cuadro de 3:4,
  con bandas grises iguales arriba y abajo; en la categoría el sofá se ve ligeramente asentado hacia abajo (su masa visual está en la parte baja de la foto), que es justo el «centro vertical se ve caído» de Feuxui.
- **Veredicto:** ✅ cumple.
- **Qué haría:** opcional y chico: para las fotos anchas, `object-position: 50% 44%` en lugar de 50 % para subirlas unos 2–3 px sobre el centro real (`dcasa.scss:1327-1329` en la portada y `:1933` en la tienda, regla `.o_dcasa_foto_ancha`). Poco, riesgo nulo, ganancia leve. No choca con la marca.

### 17 · Eco de forma
- **La regla de Feuxui:** una forma madre (un radio de esquina, una curva, una diagonal) repetida **con el mismo valor exacto en por lo menos 3 lugares**: «si el radio es 24 px, es 24 px en todo». La forma de tu logo puede ser la madre.
- **D'CASA hoy (radios medidos):** tarjetas, fotos de categoría y de galería: **16 px** (`$dcasa-radius: 1rem`, `dcasa.scss:18`, usado 14 veces); foto grande de los bloques foto/texto: **24 px** (`$dcasa-radius * 1.5`, `:1482`, `:1720`);
  botones: **12 px** (normales) y **14.4 px** (grandes) (`primary_variables.scss:97-98`); íconos redondos del carrito y de WhatsApp, flechas de carril: **50 %** (7 reglas); distintivos, «Pausar» y píldoras: **999 px** (11 reglas);
  píldora de cabecera: 16 px. Hay otros valores sueltos (3 px, .4 rem, .6 rem, 1.25 rem). La **forma** es una sola: esquinas suaves, círculos y píldoras, nunca esquinas duras. El **valor** exacto repite en tarjetas y fotos (16 px), pero los
  botones (12/14.4) no lo siguen. Eco del logo: la banda amarilla de 14 px bajo la sección azul repite el rectángulo azul con barra amarilla del logo.
- **Veredicto:** 🟡 cumple a medias: familia coherente, valor no único.
- **Qué haría:** botones al mismo 16 px de las tarjetas: `btn-border-radius` y `btn-border-radius-lg` de `.75rem`/`.9rem` a `1rem` (`primary_variables.scss:97-98`). Los tests no fijan el radio de los botones (solo el de la píldora); revisar la píldora y el CTA
  del menú. Esfuerzo **poco**, riesgo bajo, efecto pequeño pero se nota junto a las tarjetas. No choca con la marca.

---

## Lo más importante

Las ocho mejoras de mayor efecto y menor costo, en orden:

1. **Cerrar un poco el tracking de los titulares Anton y subir su interlineado** (`dcasa.scss:62-63`, `:1904-1905`): −0.02em en ≥60 px, −0.01em en h2 de 40 px y ficha; interlineado 1.02 → 1.08. Hace más sólido el titular de la portada
   y evita choques de tildes cuando la dueña edite textos. Poco, riesgo bajo.
2. **Titular de la portada al mismo borde que todo el sitio** (x = 96 → 48; `dcasa.scss:843`). Una línea. Poco.
3. **Franja del copyright al mismo borde del pie** (agregar `.o_footer_copyright .container` a `dcasa.scss:1884-1887`). Poco.
4. **Ficha: «También en combo» al mismo ancho (520 px) que el botón de WhatsApp y los sellos** (`catalogo.scss:2`). Poco.
5. **Mostrar el título de cada categoría** (opción del editor por categoría, sin código): da un protagonista a una página que hoy no lo tiene. Poco, sin riesgo.
6. **Colapsar los tamaños de letra duplicados** (15/15.2, 12.8/13, 14/14.4, 20/20.2) y ponerles nombre (12, 14, 16, 20). Poco para empezar, medio para los 37 valores.
7. **Botones de ficha, categoría y «Visítanos» con la misma voz que los de la portada**: hoy son Oswald 400 en minúscula y 0 % (ficha 15.2 px, visítanos 20 px) o 12.8 px en la categoría, contra Oswald 500, mayúsculas y +6 % en la portada
   (`dcasa.scss:161-171` aplica solo bajo `.o_dcasa_home`). Ampliar el selector a todo el sitio. Poco, riesgo bajo (cambian de aspecto botones de Odoo; revisar a 390 px).
8. **Un solo borde izquierdo y un solo margen en tienda, ficha y carrito** (corregir `dcasa.scss:1884-1891` para Odoo 19; 15 → 16 px en celular). Medio, riesgo medio.

Después, si hay tiempo: separar nombre y precio en la tarjeta (10 → 16 px), botones a 16 px de radio, dejar libre la zona de la burbuja de Andrés en la ficha móvil, fotos anchas 2–3 px más arriba.

## Lo que choca con la marca (para que decida Gerencia)

- **Reducir a dos familias** (la regla de Feuxui «máximo dos») → ⚠ **choca con la marca (regla 2: Anton, Oswald e Inter)**. Mi recomendación: dejar las tres; Anton e Inter ya cumplen la fórmula y Oswald hace un trabajo distinto.
- **Que el botón amarillo protagonista sea WhatsApp** (énfasis y un solo protagonista) → ⚠ **regla 5 (CTA único: Escríbenos por WhatsApp)**. Hoy el amarillo del hero es «Ver el catálogo» y WhatsApp va en contorno. Es una decisión de la dueña, no mía.
- **Profundidad por desenfoque, degradado de atmósfera o sombras; texto inclinado a un punto de fuga** (perspectiva) → ⚠ **regla 3 (plano, sin degradados ni sombras dramáticas)**.
- **«Luz» como encuadre (oscurecer bordes con degradado)** → ⚠ **regla 3**. Ya existe un degradado en el hero (`dcasa.scss:767-775`, decisión de la dueña del 2026-11-17, permitido por `test_contrato_visual.py` como «la única capa»); y el vidrio de la cabecera (`backdrop-filter`, `dcasa.scss:348-349`)
  es otra excepción al sistema plano. No lo toqué ni lo recomiendo ampliar.
- **Tensión por giro de 5–15°** → no hay regla escrita en contra, pero va contra el tono «ordenado y confiable» (regla 6, voz). Decisión de estilo.
- **Z con botón abajo a la derecha** → no choca con ninguna regla de marca, pero choca con la otra regla de Feuxui (alineación a la izquierda). Se queda la alineación.

## Lo que D'CASA ya hace mejor o igual que Feuxui

- **Cuerpo de lectura exacto:** Inter 16 px con 24 px de interlineado (1.5 al punto) y 0 % de tracking; texto legal a 17 px/1.7 en columna de 706 px, subiendo el interlineado por la columna ancha, que es lo que Feuxui aconseja. Y 12 px bajo cada título legal contra
  40 px antes del siguiente: títulos pegados a su texto.
- **Proximidad del hero clavada:** 9/17 px dentro y 32 px entre grupos, la escala 8–16–32 de Feuxui; cabezas de sección con 6.4/28/72 px.
- **Un protagonista claro en la portada:** titular 5 veces mayor que lo siguiente y un único amarillo (el botón del catálogo).
- **Alineación del texto sana:** casi todo a la izquierda, centro solo en el carrito vacío (3 líneas), **nada justificado** en todo el código.
- **Tienda sobre una grilla real de 12 columnas** con medianil 16 px y filas 32 px, también en celular; el carril de la portada suma justo 1344 px (5 × 256 + 4 × 16).
- **Tarjeta con la Z de Feuxui:** foto arriba, precio a la izquierda y acciones abajo a la derecha, con zonas de 48 px.
- **Balance óptico en los íconos de 48 px:** centrados a menos de 1 px; menú de cabecera al centro exacto.
- **Forma coherente:** esquinas suaves, círculos y píldoras; un solo radio madre definido como variable (`$dcasa-radius`, `dcasa.scss:18`, 14 usos); la banda amarilla repite la forma del logo.
- **Pocas formas de tensión y bien usadas** (corte del carril, tamaño extremo del titular, diagonal del hero) con el texto ordenado, tal como pide Feuxui.
- **Tres familias con trabajo propio**, una cantidad medida (Anton 2–4 %, Oswald 24–33 %, Inter 64–73 % del texto) y autoalojadas en subconjunto latino (74 KB en total, `fuentes.scss:9-11`): lejos de las «cinco que se pelean».
- **Panel interno:** una sola familia (Inter) con dos niveles claros en el Inicio (título 16 px/700, subtítulo 12.8 px) y margen de 16 px en celular (`$S/capturas/4_inicio_celular.png`).
