# Referencia de diseño: lo que enseña Feuxui y cómo está D'CASA

**Leído el 2026-11-20** (por pedido de Gerencia: «aprender todos los conocimientos de feuxui.com y comparar con D'CASA»).
[Feuxui](https://feuxui.com/) es el sitio de un director creativo colombiano con una escuela de diseño: **38 conceptos**, cada uno con
explicación, demos, «así no / así sí» y una lista «Antes de publicar»: **30 «tips de diseño»** (color, tipografía, composición,
profundidad, criterio) y **8 «tips de UX»** (interfaces reales corregidas), más una página de método. Se descargó su texto y tres
ayudantes compararon cada concepto con D'CASA **midiendo** el sitio en vivo (`dcasapty.com`, solo lectura, a 1440 y 390 px, contrastes con la
fórmula WCAG exacta) y leyendo el código. Los informes completos, con medidas y `archivo:línea`, están en
[referencias/feuxui/](referencias/feuxui/): [A](referencias/feuxui/A.md) (color, profundidad, criterio),
[B](referencias/feuxui/B.md) (tipografía y composición) y [C](referencias/feuxui/C.md) (UX, más el método). Las capturas y los guiones de
medición no se guardan en el repositorio (viven en la carpeta de trabajo de la sesión); si hace falta repetir, los informes dicen qué
se midió y cómo.

**Regla de uso:** esto es una referencia, no una orden. **Manda la marca** (`CLAUDE.md`, reglas 1 a 6): donde un consejo de Feuxui
choca con ella, queda abajo en «Decisiones para Gerencia», sin aplicar.

## En una frase

D'CASA ya hace bien lo más difícil (texto sobre fondos lisos con contraste de 5,2 a 15,9:1, una grilla real de 12 columnas, el cuerpo
Inter 16/24 exacto, proximidad con la escala 8-16-32, menú, enlaces y formularios modelo en `/socios`). Lo que falla es **concreto y
barato de arreglar**: el texto sobre las fotos del hero, el botón de WhatsApp en escritorio, algunas zonas táctiles de celular, placeholders
y pasos del carrito con poco contraste, y bordes de alineación que no coinciden.

## Lo más importante (de los tres informes, sin repetir, en orden de efecto y bajo costo)

1. **Botón «Escríbenos por WhatsApp» del hero:** hoy es solo contorno y en escritorio da **1,6 a 2,3:1 sobre las 7 fotos** (debe ser ≥ 4,5:1);
   es el único CTA de la marca. Relleno plano azul noche: pasa de 8:1. *(C1; sin choque con la marca)*
2. **Texto del hero sobre las fotos** (subtítulo: peor píxel 2,13:1; antetítulo en celular 2,09:1): una capa de azul de marca solo donde va el
   texto lo sube a 4,54 y 4,94:1 (valores en A, concepto 8). Un velo plano no alcanza (2,3-2,5:1). ⚠ **Decide Gerencia** (ver abajo).
3. **Fondo base del hero en azul noche** (hoy hueso, y sin fotos cargadas el texto blanco casi no se lee). *(A2)*
4. **Placeholders** de búsqueda y de Socios con el gris de la marca (de 2,86 y 3,12:1 a 7,27:1). *(A3)*
5. **Pasos del carrito** legibles: `opacity: 1` (de 2,38 a 7,93:1; el arreglo de `dcasa.scss:2006` lo anula la opacidad 50 % de Odoo). *(A4)*
6. **Zonas táctiles de 44 px o más** en celular: hamburguesa (40×42), «Ordenar por» y «Filtros» (38), la X del cajón (32), «Mi cuenta» (37),
   «Enviar» del contacto (77×38). *(C2)*
7. **La burbuja de Andrés** no debe tapar el cajón del menú, los chips de búsqueda ni la ficha a 390 px. *(C3, B)*
8. **Buscador:** nombre para el lector de pantalla, botón «Buscar», placeholder corto y una pista «Busca con una foto». *(C4)*
9. **Contacto:** «Enviar mensaje» a ancho completo y 48 px, como `/socios`. *(C5)*
10. **Titulares Anton:** tracking −0,02 em desde 60 px (hoy +0,5 %) e interlineado 1,02 → 1,08 (evita choques de tildes cuando se editen
    textos). *(B1)*
11. **Alineación:** titular del hero al borde de 48 px (hoy 96), copyright al mismo borde del pie, «También en combo» a 520 px en la ficha,
    un solo margen en tienda, ficha y carrito. *(B2-B4, B8)*
12. **Botones de ficha, categoría y «Visítanos»** con la misma voz que los de la portada (hoy Oswald 400 minúscula y 0 %; la portada,
    Oswald 500 mayúsculas +6 %). *(B7)*
13. **Escala de letras:** la portada usa 17 tamaños (Feuxui pide 3); colapsar duplicados (15/15,2, 12,8/13, 14/14,4, 20/20,2). *(B6)*
14. **Panel interno:** barra lateral con nombres desde 1200 px; `--dc-tinta-3` a `#5F6A84` (4,20 → 5,00:1). *(C7, A6)*
15. **Una prueba automática de contraste en píxeles para el hero nuevo** (la existente solo cubre el hero antiguo) y **escribir las «Reglas de
    interfaz» en `CLAUDE.md`** (lo que no queda escrito se pierde). *(A7, A8, C8)*

## Decisiones para Gerencia (lo que choca con la marca o con algo que ya se pidió)

| Tema | Qué dice Feuxui | Lo que choca | Recomendación de los informes |
|---|---|---|---|
| Degradado azul en el hero | una capa de color solo donde va el texto | regla 3 «sin degradados»; ya se aprobó el 2026-11-17 pero la regla escrita no lo dice | **reformular la regla 3** para dejar escrita la excepción; un velo plano no alcanza |
| Oscurecer la zona del texto | contraste mínimo 4,5:1 | se pidió «el fondo no lo quiero oscuro» | mostrar capturas antes/después (hay una lista en A) |
| Botón principal del hero | un solo primario por pantalla | regla 5 (CTA único: WhatsApp) frente a «Ver el catálogo» amarillo hoy | decidir si la regla 5 manda también en la portada |
| Fondo en movimiento sin mandos | nada se mueve solo; WCAG 2.2.2 | pedido de «sin control» | que se detenga solo tras una vuelta (~45 s) o una pausa mínima |
| Cabecera de vidrio y zoom del hero | un efecto por diseño | regla 3 (plano) | quitar solo la refracción animada y el reflejo |
| Tres tipografías | máximo dos | regla 2 (Anton, Oswald, Inter) | **dejar las tres**: cada una hace un trabajo distinto |
| Rojo para lo destructivo | reservar un rojo | la paleta no tiene rojo (regla 1) | decidir un rojo único reservado, si el panel va a tener acciones que borran |
| Botones azules iguales en el Inicio | un principal por pantalla | pedido del jefe (2026-10-16) | decisión de la persona, no de marca |
| Grano, bajar saturación, CTA cálido sobre fondo claro | efectos y color | reglas 1 y 3 | **no adoptar** |

## Lo que D'CASA ya hace mejor o igual

Mide y deja escritos los contrastes (`dcasa.scss:17`, `:408`); texto sobre fondos lisos de 5,18 a 15,87:1; modo oscuro del panel que separa el
azul de letra del de relleno (6,9 a 8,07:1 en vez de 1,56:1); sombras con tinte navy y niveles como los de Feuxui; amarillo solo el 0,8 % del
área y siempre sobre azul o navy; tienda en grilla de 12 columnas; cuerpo Inter 16/24 y 0 % de tracking; proximidad 9/17/32 px; un
protagonista claro en la portada; menú sencillo, ni un «ver más» ni «clic aquí» en 9 páginas; `/socios` como formulario modelo; zona del
pulgar bien resuelta en el hero y en la ficha; respeta «reducir movimiento»; excepciones de marca con motivo y vigiladas por pruebas.

## Los 38 conceptos y su veredicto

Leyenda: ✅ cumple · 🟡 a medias · ❌ no cumple · ➖ no aplica · ⚠ choca con la marca. (Texto abreviado; el completo está en los informes.)

### Color, profundidad y criterio (informe A)

| # | Concepto | La regla de Feuxui | Cómo está D'CASA |
|---|---|---|---|
| 1 | Contraste | el texto debe tener 4.5:1 (normal) o 3:1 (titular grande: unos 24 px, o 19 px en negrilla) contra lo que tiene detrás; brillo opuesto; el titular al menos el doble de grande que el texto; «mide, no adivines» y revísalo en el… | 🟡 cumple a medias. Fondos lisos: ✅ (mínimo 5.18:1 salvo 3 excepciones). Hero sobre foto: ❌ en subtítulo y antetítulo. |
| 2 | Paleta de color | tres colores (principal, secundario, acento) más neutros; reparto 60-30-10; el acento aparece en una o dos cosas «porque es escaso»; anota los tres códigos y repítelos; si agregas un color, saca otro. | ✅ en el sitio público (tres colores, códigos fijos, acento escaso); 🟡 en las páginas claras (secundario y acento son el mismo azul) y en el Inicio del celular (el… |
| 3 | Color y fondo | un color no tiene contraste por sí solo, depende de su fondo; decide el fondo primero; si falla, cambia la luz, no el tono; el color de acento debe tener una versión clara y otra oscura. Su ejemplo: el azul #1417FB da 7.0:1 sobre… | ✅ cumple (con el hueco del hero sin fotos). |
| 4 | Temperatura de color | cálidos adelante, fríos atrás; el protagonista (botón, producto, oferta) cálido sobre un fondo frío; una temperatura manda y la otra va de acento; los grises deben ir con esa temperatura. | ✅ en portada y bandas; 🟡 en ficha y categoría (protagonista frío sobre neutro), pero eso viene de la regla 1. |
| 5 | Saturación | un solo color a tope (el acento); la interfaz al 60-80 %; los fondos grandes al 20-40 %; bajar de a 10 % hasta que deje de gritar; bajar un poco la saturación de las fotos. | ✅ en el sitio público; 🟡 en el Inicio del celular del panel. |
| 6 | Caída de luz | la luz se desvanece, no se corta; degradados con cinco puntos (opacidad 100 / 60 / 25 / 8 / 0 a las posiciones 0 / 15 / 40 / 70 / 100 %); sombra en dos capas (contacto Y2 blur4 20 % + ambiente Y24 blur48 12 %); nunca negro puro;… | ⚠ choca con la marca (regla 3, «sin degradados»): el degradado existe porque la dueña lo eligió el 17 nov entre cinco opciones (docs/LEEME_PRIMERO.md, sesión del hero en… |
| 7 | Sombras | una sola fuente de luz y todas las sombras hacia el mismo lado; desenfoque de 2 a 3 veces la altura (Y); opacidad 10-25 %; nunca negro puro (usa un tono oscuro del fondo); tres niveles: baja (Y2 · blur6 · 12 %), media (Y8 ·… | ✅ cumple. Una dirección, tinte de marca, suaves, una por elemento; D'CASA ya usa los niveles de Feuxui sin conocerlos. |
| 8 | Overlays y capas | foto abajo, capa en medio, texto arriba; texto claro con capa oscura; para degradado, de 0 a 70-80 % solo donde va el texto; un color de la marca vale más que un gris plano; mide el contraste sobre la zona más clara de la foto y… | 🟡 cumple a medias (método ✅, magnitud ❌ en subtítulo y antetítulo). |
| 9 | Ruido y grano | una capa de ruido gris en modo Superposición: 0-2 % en texto e interfaz, 2-4 % en fondos lisos, 4-6 % en degradados (esconde las bandas), 6-8 % en fotos; pasado el 8 %, sucio. | ➖ no aplica. Si algún día se propusiera añadir textura, choca con la marca (regla 3, sistema plano). |
| 10 | Efectos | un efecto por diseño y con un motivo; «si apagarlo no te hace falta nada, sobraba»; brillo, borde, sombra y degradado juntos hacen que se vea barato; el efecto sí vale cuando separa (sombra), enfoca (desenfoque), indica «en vivo»… | 🟡 cumple a medias · ⚠ choca con la marca (regla 3, «sistema plano»): la cabecera de vidrio y el zoom son decisiones de la dueña (docs/historico/REDISENO.md:147-157,… |
| 11 | Ojo de diseñador | no preguntes «me gusta», pregunta «por qué funciona»: cinco preguntas (¿qué miro primero?, ¿cuántos colores?, ¿cuántas fuentes y pesos?, ¿dónde está el espacio vacío?, ¿qué se alinea con qué?); guarda tres referentes al día;… | ✅ cumple. |
| 12 | Principio KISS | corto y simple; máximo 2 fuentes y 3 colores con un solo acento; un mensaje por pieza que se entienda en 3 s; quita sombras, marcos, estrellas y degradados que no ayuden; «antes de agregar algo, pregunta qué pasa si lo quitas». | 🟡 cumple a medias. |
| 13 | Rompe las reglas | domina la regla, rompe una sola, exagérala para que se note y ten un motivo que puedas decir en una frase; la diferencia entre error y decisión es la intención. | ✅ cumple (excepciones con motivo y vigiladas), con 🟡 por la acumulación de rupturas en el hero. |

### Tipografía y composición (informe B)

| # | Concepto | La regla de Feuxui | Cómo está D'CASA |
|---|---|---|---|
| 1 | Combinación tipográfica | «Máximo dos fuentes»: una con carácter para el titular y una simple para leer. Contraste, no parecido (dos sans casi iguales parecen un error). Antes de sumar una tercera, juega con los pesos. | 🟡 cumple a medias. Tres familias contra el máximo dos, dicho con honestidad: no es un descuido, es la marca; y sus trabajos están bien repartidos. ⚠ Quitar Oswald choca… |
| 2 | Énfasis | un solo protagonista, con tamaño, color o movimiento; por lo menos el doble de grande que lo demás; el color de acento solo en el protagonista. Prueba del vistazo: entrecierra los ojos. | ✅ cumple en la portada; 🟡 en ficha y categoría. |
| 3 | Jerarquía visual | tres niveles (titular, subtítulo, texto) con una escala fija: cada escalón ×1.5 (32, 48, 72, 108). «Si necesitas un cuarto nivel, te sobra contenido.» Antes de publicar: ¿máximo 3 tamaños de texto? | 🟡 cumple a medias: la jerarquía se entiende, la escala no tiene método. |
| 4 | Tracking y espaciado entre letras | más grande, más cerrado. Titular de 60 px o más: −2 a −5 %. Subtítulo de 24 a 48 px: −1 a −2 %. Párrafo de 14 a 18 px: 0 %. Menos de 12 px: 0 a +2 %. Etiqueta, botón y menú en mayúsculas pequeñas: +5 a +10 %. | 🟡 cumple a medias: párrafos ✅ y etiquetas ✅; titulares ❌. |
| 5 | Interlineado | párrafos a 1.5 (1.4–1.6; si la columna es ancha, 1.6); titulares casi a 1 (0.9–1.1); subtítulos 1.1–1.3; botones y UI de una línea 1.2. Cuida las tildes: al cerrar un titular, que las tildes y la Ñ no choquen con la línea de… | ✅ cumple (con un riesgo conocido en las tildes). |
| 6 | Grilla | cada elemento empieza y termina en una línea de la grilla. 4 columnas para celular, 12 para web. Medianil siempre igual (20–30 px en post; margen 60–90 px en post). «Más columnas no es mejor.» | 🟡 cumple a medias: tienda ✅, portada con bordes comunes pero sin columnas comunes ni medianil único. |
| 7 | Márgenes | mismo margen en los cuatro lados; entre el 5 y el 10 % del lado más corto; margen mayor que el espacio entre elementos. Web: celular 16 a 24 px; en computador, contenido centrado con ancho máximo de unos 1200 px. | 🟡 cumple a medias (la portada es pareja; el resto de páginas, no). |
| 8 | Alineación | elige un eje y respétalo; cada borde toca una línea que otro también toca. Izquierda por defecto para textos largos; centro solo en piezas de máximo tres líneas; nunca justificado. | 🟡 cumple a medias: en la portada hay cinco ejes izquierdos (48, 60, 80, 96 y 75) dentro de una franja de 48 px; en la tienda, cuatro (48, 75, 80, 123). |
| 9 | Proximidad | lo cercano se lee junto. Dentro de un grupo, 8–16 px; entre grupos, por lo menos el doble (escala 8, 16, 32, 64). Cada titular, pegado a su texto. «Foto con nombre, precio con botón.» | ✅ en las zonas grandes (hero, secciones, legal); 🟡 en tarjetas y ficha. |
| 10 | Lectura en Z | poco texto → Z: logo arriba a la izquierda, dato corto arriba a la derecha, mensaje en la diagonal y botón abajo a la derecha. Mucho texto → F. Aplica a portadas y páginas de inicio. | 🟡 cumple a medias: tres de cuatro puntos; el punto 4 de la portada lo ocupa la burbuja de Andrés, no el botón. |
| 11 | Simetría y asimetría | simetría = calma (bodas, lujo, instituciones); asimetría = energía (deporte, moda, lanzamientos, redes), con el peso compensado. Nunca a medias: lo casi centrado parece un error. | ✅ cumple. |
| 12 | Regla de tercios | 3 × 3; lo importante en un cruce y algo que equilibre en el cruce opuesto; el horizonte fuera del centro; aire hacia donde mira el sujeto. Es un punto de partida, no una ley («siempre hay que usarla: no»). | 🟡 cumple a medias: el texto sí; la foto depende de qué foto entre al carrusel y no se pudo medir. |
| 13 | Tensión visual | un desequilibrio pequeño y a propósito: algo al borde, cortado, girado 5–15°, casi tocándose, tamaño extremo o diagonal. Elige una o dos formas por diseño; el texto, ordenado. | ✅ cumple (con medida; la marca pide orden y confianza, no riesgo). |
| 14 | Encuadre | rodear lo importante con una forma, líneas, espacio o luz, con un marco más simple que lo enmarcado; un solo elemento enmarcado. | ✅ cumple. ⚠ El «luz con degradado» de Feuxui y el vidrio de la cabecera chocan con la marca (regla 3, sistema plano); el degradado del hero es una decisión explícita de… |
| 15 | Perspectiva | dar profundidad con escala (cerca, grande), superposición, punto de fuga (formas o texto inclinados) y desenfoque de lo lejano. Con una herramienta ya se nota. | ➖ no aplica a un sistema plano; las herramientas de escala y superposición ya están en uso. ⚠ Desenfoque, degradado de atmósfera y sombras de profundidad chocan con la… |
| 16 | Balance óptico | el ojo lee masa y forma, no medidas: un círculo se ve más chico que un cuadrado del mismo alto (círculo +8–10 %); el «play» va 1/6 hacia la punta; lo centrado en vertical se ve caído (súbelo un poco). «La medida es el punto de… | ✅ cumple. |
| 17 | Eco de forma | una forma madre (un radio de esquina, una curva, una diagonal) repetida con el mismo valor exacto en por lo menos 3 lugares: «si el radio es 24 px, es 24 px en todo». La forma de tu logo puede ser la madre. | 🟡 cumple a medias: familia coherente, valor no único. |

### UX: interfaz y botones (informe C)

| # | Concepto | La regla de Feuxui | Cómo está D'CASA |
|---|---|---|---|
| 1 | Zona del pulgar | lo que se toca seguido va abajo y grande; lo que se toca poco, arriba. Áreas táctiles de al menos 44 pt (Apple) o 48 dp (Material); la acción principal como botón ancho abajo; lo destructivo lejos del pulgar; «probaste la… | 🟡 cumple a medias (sitio y panel). |
| 2 | Menú hamburguesa | la hamburguesa es para pantallas pequeñas; si hay espacio, el menú va a la vista. Máximo cinco opciones, ordenadas por lo que el usuario busca, sección activa con color y una línea, y el botón de acción (cotizar, comprar) aparte… | ✅ cumple en el sitio público; 🟡 en el panel de escritorio (la franja de íconos). |
| 3 | Hero sin carrusel (la portada que acaba de… | «Arriba va un solo mensaje y una sola acción; todo lo demás, abajo». Crítica al carrusel clásico: promete cinco mensajes y casi siempre se ve uno; se mueve solo y justo cuando empiezas a leer el texto cambia; cada slide trae su… | 🟡 cumple a medias. Lo que no aplica de la crítica: los cinco mensajes y los botones por slide. Lo que sí aplica: movimiento sin forma de parar y texto que no siempre se… |
| 4 | Enlaces descriptivos | un enlace debe decir a dónde lleva aunque se lea solo («mira la guía de tallas», no «haz clic aquí» ni «ver más»); subrayado además del color; enlace si lleva a otra página, botón si hace una acción; avisar si descarga un archivo… | ✅ cumple (con dos detalles). |
| 5 | Íconos con texto | «un ícono sin texto solo funciona si es universal. Casi ninguno lo es»; solo la lupa, la X de cerrar, el play y «inicio» van solos; el corazón, la estrella, la flecha de subir, etc. necesitan una palabra. Barras de navegación de… | 🟡 cumple a medias (sitio y panel). |
| 6 | Etiquetas de formulario | «El placeholder no es etiqueta»: la etiqueta siempre visible arriba del campo; el placeholder, si existe, solo da un ejemplo. Cuatro piezas: etiqueta arriba, ayuda antes del error, error junto al campo, botón que dice qué va a… | 🟡 cumple a medias (contacto y /socios ✅; buscador ❌ por el nombre y el corte; checkout sin medir). |
| 7 | Jerarquía de botones | un solo botón principal por pantalla; los demás, un escalón abajo. Cuatro niveles: principal (lleno y en color de acento), secundario (borde, sin relleno), terciario (solo texto) y destructivo (rojo, solo para lo que borra). Cada… | 🟡 sitio público (jerarquía buena en las pantallas pequeñas, con dos dudas); ❌ Inicio del panel (tres llenos iguales + tarjetas llenas). |
| 8 | Texto centrado | centrar solo lo corto (titular, frase, botón); desde la tercera línea, alinear a la izquierda (con dos líneas va bien, tres es el límite). Que todo el texto de una tarjeta comparta un solo borde; el texto justificado abre huecos.… | ✅ cumple. |

## Cómo se usó

- **Rediseño del pago** (2026-11-20): Gerencia vio el pago con Tilopay y pidió que se parezca a Shopify, WooCommerce o Stripe «tomando en cuenta
  el diseño» de Feuxui. Se usaron de aquí: una sola acción primaria por pantalla, etiquetas visibles arriba del campo, botón principal en la
  zona del pulgar, contraste ≥ 4,5:1, jerarquía de tres niveles y márgenes parejos. Ver el avance en la bitácora de
  [LEEME_PRIMERO.md](LEEME_PRIMERO.md).
- **Lista de revisión del proceso** (12 preguntas con el estado de D'CASA) y resumen de las entrevistas: al final del [informe C](referencias/feuxui/C.md).
