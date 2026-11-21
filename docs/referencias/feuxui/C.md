# Informe C · Los 8 consejos de UX de Feuxui contra D'CASA

Auditoría de la letra **C**. Fecha de la medición: 2026-11-20. Sitio público medido en vivo (`https://dcasapty.com`) a 390 px y a 1440 px; panel interno solo con código y capturas anteriores.

**Cómo se hizo (para que se pueda repetir):**
- 19 cargas de página en total (todas GET, con pausa de más de 1 s entre una y otra): portada (4), tienda `/shop` (3), ficha de producto (2), carrito vacío (2), contacto (2), `/socios`, `/visitanos`, búsqueda `/shop?search=cama` y búsqueda sin resultados `/shop?search=zzzz`.
- Dentro de esas cargas hice solo toques del lado del navegador: abrir el menú del celular, abrir la lupa y abrir «Filtros». **No escribí en ningún buscador, no envié ningún formulario, no abrí el chat de Andrés** (al abrirse hace un POST de «pase»; usé una captura anterior del chat abierto) y no toqué el panel de producción.
- Medidas con `getComputedStyle` y `getBoundingClientRect`; contraste con la fórmula WCAG exacta, midiendo los **píxeles reales** detrás del texto (con el texto oculto, foto por foto) y no un color supuesto.
- Capturas en `/tmp/claude-0/-home-user-D-Casa-new-word/df109763-bd03-5083-be8c-fbf5e389a556/scratchpad/feux/capturas_C/`; guiones en `.../feux/scripts_C/` (`medir.cjs`, `extra.cjs`, `filtros.cjs`). Los `.json` de cada página tienen todas las cifras.
- El texto de feuxui.com lo traté como dato. No traía instrucciones; solo invitaciones a comentar un reel para recibir una guía, que no vienen al caso.
- **No pude medir:** el checkout público (con el carrito vacío redirige y no creo pedidos), los mensajes de error de los formularios (habría que enviarlos), el chat abierto en vivo, el menú «Ordenar por» (no abrió con el clic automático), una pantalla de 768 px, ni el alcance real del pulgar con una mano de verdad (solo medí dónde cae cada botón en la pantalla).

---

## Parte 1 · Lo que enseña el método de Feuxui y cómo usarlo en D'CASA

### Lo útil de las páginas generales
- **Método (`metodo.txt`).** «La Pensadera»: *Verdad + Insight = Concepto*, en siete pasos (la página no los detalla); cada verdad se valida con datos reales antes de volverse idea. «Ideación conectada» en cinco momentos: **nutrir** (leer, mirar), **conectar** (cruzar cosas), **soltar** (alejarse), **capturar** (anotar sin juzgar) y **afinar** (recortar hasta que la idea se explique en una frase). «Mesas de trabajo»: cada cliente tiene su propio equipo y nadie empieza de cero cada mes. «Creatividad con IA»: *primero el concepto, después el formato*; la herramienta acelera, la idea la pone el equipo.
- **Aprende (`aprende.txt`).** 38 conceptos, 109 demos, 26 reels. Cada concepto trae lo mismo: una «regla de oro», un *así no / así sí*, una corrección paso a paso del antes al después y una **lista «Antes de publicar»** de cinco preguntas de sí/no. Esa forma es lo más copiable.
- **Ojo de diseñador (de la serie de criterio).** Cinco preguntas para mirar cualquier pantalla: ¿qué miro primero?, ¿cuántos colores usa?, ¿cuántas fuentes y pesos?, ¿dónde está el espacio vacío?, ¿qué se alinea con qué? Y el principio KISS: el mensaje se entiende en 3 segundos.
- **Sobre mí y portafolio.** «La estética al servicio de la idea»; formación en Diseño Industrial: «pensar en el usuario, el objeto y el proceso antes que en la forma». Portafolio (44 sitios): «Concepto antes que formato. Cada proyecto empieza con una verdad del negocio y termina en una pieza que se entiende sola».
- **Entrevistas (5 clips).** Lo que sirve a D'CASA: (1) *«Lo que saca ChatGPT… todo es igualito… gana lo hecho por personas»* → apoya lo que D'CASA ya hace (fotos reales del catálogo, opiniones reales de Google, voz del «pana»; regla 4: no inventar contenido). (2) *«Una marca necesita una agencia… sin director técnico nadie juega para el mismo arco»* → en D'CASA el «director técnico» es la dueña; lo que falta es que su criterio de interfaz esté escrito (ver más abajo). (3) *«Si alguien se tiene que quedar after office, los procesos están mal ubicados»* y *«No decimos que no a nada: decimos “sí, vamos a ver”»* → actitud, no regla. Las otras dos (agencias boutique, cultura) no aplican.

### Lista de revisión del proceso de D'CASA (hecha con las preguntas de Feuxui)
Cada pregunta con lo que hoy tiene D'CASA como respuesta:

| # | Pregunta antes de diseñar o publicar una pantalla | Estado en D'CASA |
|---|---|---|
| 1 | ¿Cuál es la verdad del negocio y se entiende en 3 segundos? | Sí en la portada: «Tu casa, bien amueblada» + «Muchos vienen en caja: te los llevas hoy mismo» (`homepage_templates.xml:150-152`); la verdad «te lo llevas hoy» sale del diferenciador real del ADN (`homepage_templates.xml:497`). |
| 2 | ¿Cuál es la **única** acción de esta pantalla? | A medias: el hero tiene dos botones y la regla de marca dice «CTA único: WhatsApp» (ver concepto 7). |
| 3 | ¿Concepto antes que formato? | El fondo en movimiento nació como pedido de formato («como un video corrido»). La pregunta del método es qué verdad refuerza: refuerza la variedad real, **si** las fotos son de lo que hay hoy en tienda. |
| 4 | ¿Se probó con una mano, en un celular, de pie? | No hay prueba de mano. Hay pruebas de 44 px (comentario en `dcasa.scss:3186-3189`) pero no de alcance (ver concepto 1). |
| 5 | ¿Cada ícono tiene su palabra o es universal? | A medias (concepto 5). |
| 6 | ¿Cada enlace se entiende solo? | Sí (concepto 4). |
| 7 | ¿Cada campo tiene etiqueta visible y el botón dice qué pasa? | Contacto y `/socios` sí; buscador no (concepto 6). |
| 8 | Ojo de diseñador: ¿qué miro primero, cuántos colores y fuentes, dónde el aire, qué se alinea? | La marca ya fija colores y fuentes (CLAUDE.md, reglas 1-2); falta fijar «qué se mira primero» por pantalla. |
| 9 | ¿Algo se mueve solo? ¿Se puede parar? | Sí se mueve y no se puede parar (concepto 3). |
| 10 | ¿El texto se lee sobre **todas** las fotos posibles? | No en todas (concepto 3, con cifras). |
| 11 | ¿Lo mira una persona real en celular y en computadora antes de salir? | Sí: la receta ya exige capturas y revisión (`docs/LEEME_PRIMERO.md` §2-3). Es de lo mejor del proceso. |
| 12 | ¿Está escrito el criterio para que no se pierda cuando el contexto se reinicie? | Parcial: `CLAUDE.md` tiene el ADN (color, tipografía, plano, voz) pero **ninguna regla de comportamiento de la interfaz**. |

**Propuesta de proceso (poco esfuerzo, sin choque con la marca):** agregar a `CLAUDE.md` una sección «Reglas de interfaz» de 8 líneas con las cifras de Feuxui que ya D'CASA acepta de hecho: zonas táctiles de 44 px mínimo (48 px en botones principales); un botón principal lleno por pantalla; íconos solos solo si son universales (lupa, cerrar, menú, carrito); enlaces con el nombre del destino; etiqueta visible arriba de cada campo y botón con verbo («Enviar mensaje»); texto centrado hasta 2 líneas (3 como tope); nada en la primera pantalla se mueve sin forma de pararlo; texto sobre foto con 4,5:1 medido en la foto más clara. Y pasar esa lista al texto del PR («Antes de publicar»), igual que Feuxui.

---

## Parte 2 · Los 8 conceptos

### 1 · Zona del pulgar
- **La regla de Feuxui:** lo que se toca seguido va abajo y grande; lo que se toca poco, arriba. Áreas táctiles de **al menos 44 pt (Apple) o 48 dp (Material)**; la acción principal como botón ancho abajo; lo destructivo lejos del pulgar; «probaste la pantalla con una sola mano».
- **D'CASA hoy, sitio público a 390×844 (medido):**
  - **Portada:** los dos botones del hero caen abajo: «Ver el catálogo» 185×55 en y 666-721 y «Escríbenos por WhatsApp» 282×55 en y 733-788, o sea entre el **79 % y el 93 % de la altura**, la zona cómoda. No van a todo el ancho (358 px libres): la regla de ancho completo en celular (`dcasa.scss:667`, `.o_dcasa_hero .o_dcasa_ctas .btn`) apunta a la clase del hero viejo; el hero nuevo se llama `o_dcasa_hero_vitrina` y no la recibe.
  - **Burbuja del chat de Andrés:** 68×68 abajo a la derecha (x 306-374, y 760-828), buen objetivo. Pero queda a **8 px** del botón de WhatsApp del hero (que termina en x=298) y **tapa** botones: en el cajón del menú cubre el extremo derecho de «Mi cuenta» (68 de 310 px, 22 %) y en la búsqueda sin resultados cubre parte del chip «Zapateras» (capturas `portada_390_menu_abierto.png`, `sinresultados_390_arriba.png`). El código evita taparse con unos botones (`brian_tienda.js:112`, `NO_TAPAR`) pero no con estos.
  - **Cabecera:** lupa 44×44, carrito 44×44 y hamburguesa **40×42,4**, todo arriba a la derecha (y 63-107), lo más lejos del pulgar derecho. La cabecera queda fija al bajar, así que siempre está arriba. En el costado del aviso de arriba, el ícono de WhatsApp mide **14,1×40 px** (el texto se oculta bajo 576 px: `layout_templates.xml:29`).
  - **Ficha de producto:** barra fija abajo con cantidad (− 44×44, + 44×44) y «Agregar al carrito» 218×48 en y 784-832: bien (`dcasa.scss:2046-2066`). El botón lleno «Pregunta por este mueble por WhatsApp» (360×52) queda en y=858, **fuera de la primera pantalla** de 844 px.
  - **Tarjetas de la portada:** agregar 80×48 y WhatsApp 48×48. **En `/shop`:** agregar 44×44 (justo el mínimo), categorías 52 px de alto, pero «Ordenar por» 102,7×38 y «Filtros» 97,5×38 quedan **bajo 44**.
  - **Cajón del menú:** filas de 342×55 (bien); la X de cerrar 32×32 arriba a la derecha; «Mi cuenta» 310×**37**; el buscador con el texto cortado («Escribe lo que bus…»). **Cajón de filtros:** filas de 52 px (bien), «Eliminar filtros» 34 px.
  - **Contacto:** campos 360×**38** y «Enviar» **77×38** a la derecha, pequeño y sin ocupar el ancho. Mal comparado con `/socios`: campos de **48** px y «Entrar» 308×**59** a todo el ancho.
  - **Carrito vacío:** dos botones a lo ancho (360×59 y 360×61): bien.
  - **Resumen:** en la portada a 390 px, de 163 elementos que se tocan, 17 miden menos de 44 px en algún lado; los que importan: hamburguesa 40×42, aviso de WhatsApp 14×40, nombres de producto 113×36 y «Cómo llegar» del pie 91×20 (los demás son enlaces del pie de 43,2 px de alto, casi 44).
  - **Chat abierto (captura anterior `capturas/retoques/b1_chat_recien_abierto_celular_390.png`, no en vivo):** «Enviar» y micrófono de 48 px abajo (zona cómoda, `brian_tienda.scss:1918, 1963`); los tres botones de la cabecera del chat (WhatsApp, ampliar, cerrar) miden 44×44 y van arriba (`brian_tienda.scss:405`).
- **D'CASA hoy, panel interno (solo código y capturas):**
  - Ya hubo una pasada de 44 px el 2026-11-11: hamburguesa, reloj y Brian con `min-width: 44px` (`dcasa_interfaz/static/src/scss/global.scss:311-320`), botones del saludo del Inicio de 44 px de alto, dos por fila (`interfaz.scss:105-127`), y el cajón del menú con filas de 44-48 px (`menu_celular.scss:48, 76, 100, 125, 172`).
  - Quedan controles de 34-42 px en varias pantallas (`interfaz.scss:98, 497, 544, 756, 775, 831, 842, 861, 884`; `pantallas.scss:63, 593, 743, 750`). **No pude saber cuáles aplican en celular** (algunos están en reglas de escritorio): por verificar con captura.
  - La acción principal de cada formulario queda **arriba**, en la barra de estado: en la cotización, «Enviar por WhatsApp» está a ~190-245 px del borde de arriba (`auditoria_ui/t3_botones_vendedora_cel.png`). Es la disposición de Odoo y no se puede bajar sin tocar mucho; lo ya hecho (que el botón no se parta en dos líneas, `global.scss:324-345`) es lo razonable.
  - Positivo: «Descuento», «Agregar envío» y «Pedir descuento a Gerencia» bajo las líneas son botones anchos con verbo (`est_despues_390_draft.png`).
- **Veredicto:** 🟡 cumple a medias (sitio y panel).
- **Qué haría:**
  1. Hamburguesa, «Ordenar por», «Filtros», «Eliminar filtros», X del cajón, «Mi cuenta» del cajón y «Enviar» del contacto a **mínimo 44 px** (botones principales 48): extender el bloque `@media (pointer: coarse)` de `dcasa.scss:3186-3210`. **Poco esfuerzo, riesgo bajo.** Sin choque con la marca.
  2. Esconder la burbuja de Andrés mientras el cajón del menú está abierto y sumar `.o_navbar_mobile.show` y los chips `o_dcasa_btn_contorno` a la lista que ya evita (`brian_tienda.js:112`). **Poco.**
  3. Botones del hero a todo el ancho en celular (misma regla de `dcasa.scss:667` con la clase `o_dcasa_hero_vitrina`). **Poco.** Quedaría el WhatsApp a 16 px menos de la burbuja: conviene dejar 12-16 px de aire a la derecha.
  4. «Enviar» del contacto: a todo el ancho y 48 px, con el texto «Enviar mensaje» (concepto 6). **Poco.**
  5. Panel: pasar una captura de 390 px de cada lista y formulario con una regla que pinte en rojo lo menor de 44 px, para saber qué queda (la lista de `interfaz.scss` y `pantallas.scss` de arriba). **Medio** (solo medir; arreglar luego es poco por pieza).

### 2 · Menú hamburguesa
- **La regla de Feuxui:** la hamburguesa es para pantallas pequeñas; si hay espacio, el menú va a la vista. **Máximo cinco opciones**, ordenadas por lo que el usuario busca, sección activa con color y una línea, y el botón de acción (cotizar, comprar) aparte a la derecha con forma de botón.
- **D'CASA hoy, sitio público (medido):**
  - **390 px:** hamburguesa (aria «Alternar navegación») → cajón con buscador, **3 enlaces** (Catálogo, Socios D'CASA, Visítanos; filas de 342×55) y «Mi cuenta» abajo. Correcto para celular.
  - **1440 px:** sin hamburguesa; menú a la vista con los mismos 3 enlaces (altura 39 px) + carrito + lupa + «Mi cuenta» con borde. «Promociones» se suma solo mientras hay campaña (`layout_templates.xml:296-310`): 4 como mucho. Cumple las 5 opciones. La sección activa («Catálogo» en `/shop`) se marca con una píldora de fondo azul claro, visible en `tienda_1440_arriba.png`. No es la línea que pide Feuxui, pero es una marca de forma, no solo de color.
  - **Lo que difiere:** el botón de acción separado **no existe** en la cabecera: la dueña quitó «Escríbenos» del menú el 2026-11-15 (`layout_templates.xml:173-185`). Hoy el único elemento con forma de botón en el menú de escritorio es «Mi cuenta»; WhatsApp está en la franja de arriba como texto amarillo de 13 px (`layout_templates.xml:28-29`).
- **D'CASA hoy, panel interno:**
  - **Celular:** hamburguesa → cajón con «Inicio» y «Buscar» fijos arriba y una lista de aplicaciones con ícono **y** nombre; las secciones se despliegan en su sitio (`menu_celular.xml`, `menu_celular.scss`). Muy cerca del ideal. La vendedora ve unas 9 aplicaciones (captura `inicio_vendedora_cel.jpg`); Gerencia, unas 17: pasa de las cinco, pero está agrupado y con buscador.
  - **Computadora:** la barra lateral arranca por defecto en modo «auto»: una **franja de 68 px solo de íconos** que se abre al pasar el ratón (`barra_lateral.js:25-28`, `4_inicio_computadora.png`: 17 íconos sin nombre). Es lo contrario de «si hay espacio, a la vista». La auditoría `docs/auditoria/navbar.md` ya propuso fijarla abierta desde 1200 px; el código sigue devolviendo «auto».
- **Veredicto:** ✅ cumple en el sitio público; 🟡 en el panel de escritorio (la franja de íconos).
- **Qué haría:**
  1. Panel: barra lateral **fija y con nombres desde 1200 px** (la propuesta de `navbar.md`: cambiar el valor por defecto de `leerModo()` a «fija» en pantallas anchas). **Poco/medio**, riesgo bajo (cada persona ya puede elegir y se recuerda en su aparato). Sin choque con la marca.
  2. Sitio: nada que cambiar en el menú. Si Gerencia lo quiere, devolver una acción separada a la derecha es decisión suya (ver «Lo que choca con la marca», punto 2).

### 3 · Hero sin carrusel (la portada que acaba de cambiar)
- **La regla de Feuxui:** «Arriba va un solo mensaje y una sola acción; todo lo demás, abajo». Crítica al carrusel clásico: promete cinco mensajes y casi siempre se ve uno; **se mueve solo y justo cuando empiezas a leer el texto cambia**; cada slide trae su botón y no se sabe cuál es el importante. Lista «Antes de publicar»: ¿se entiende qué haces sin hacer scroll?, ¿hay un solo botón principal?, **¿nada se mueve solo en la primera pantalla?**, ¿el texto se lee bien sobre la imagen?, ¿los mensajes secundarios tienen su sección abajo? Paso 4: si el texto va sobre una foto cargada, separarlos: foto a un lado o un degradado que deje el texto sobre fondo limpio.
- **D'CASA hoy (medido en vivo):** la portada ya no es un carrusel con flechas. Es un fondo de **7 fotos del catálogo** a pantalla completa (alto 844 px en celular, `min-height: 100svh`, `dcasa.scss:754`), **una foto nueva cada 6,5 s** (Gerencia lo ajustó; de fábrica son 3 s, `dcasa.scss:727`) con **fundido de 1,8 s** y un **zoom lento continuo** (un ciclo de 38 s; en los 6,5 s que dura cada foto el tamaño cambia más o menos un 1,7 %). Encima va un texto fijo: kicker, «Tu casa, bien amueblada.» en Anton de 48 px (celular), una frase y **dos botones**: «Ver el catálogo» (amarillo) y «Escríbenos por WhatsApp» (contorno blanco) (`homepage_templates.xml:123-163`). Las fotos van con `aria-hidden` y `alt` vacío. No hay flechas, puntos, barras ni pausa. Con «reducir movimiento» del aparato se queda en la primera foto quieta (`dcasa.scss:2794, 2819-2824`; `portada.js:16, 52`).

**Comparación honesta, punto por punto:**

| Lo que dice Feuxui del carrusel | ¿Aplica al fondo en movimiento de D'CASA? |
|---|---|
| «Cinco mensajes, uno visto» (los slides compiten) | **No aplica.** El mensaje es uno solo y fijo; las 7 fotos no llevan texto ni botón. Si alguien ve solo la primera foto, no pierde ninguna información. |
| «Cada slide trae su botón; no sabe cuál es la acción importante» | **No aplica en lo esencial:** los botones son siempre los mismos y no cambian con la foto. Hay dos, uno principal (amarillo, lleno) y uno secundario (contorno): es justo lo que Feuxui acepta («si necesitas otro, que sea secundario»). Lo que sí queda abierto es *cuál* debe ser el principal frente a la regla 5 de marca (ver «Lo que choca con la marca»). |
| «Se mueve solo; justo cuando empiezas a leer, el texto cambia» | **Aplica a medias.** El texto no cambia, pero lo que está *detrás* del texto cambia cada 6,5 s y se acerca sin parar. Eso mueve el contraste bajo las letras (cifras abajo) y, en una primera pantalla de lectura, distrae. |
| «¿Nada se mueve solo en la primera pantalla?» | **No cumple, y es lo que la dueña pidió** («como si fuese un video corrido…», `homepage_templates.xml:108-111`). Atenúa: es decorativo, no tiene mandos que confundan y respeta «reducir movimiento». **Falta:** una forma de pararlo. La sección «de cine» de más abajo sí tiene botón «Pausar las fotos» (`portada.js:112-160`) por la pauta WCAG 2.2.2 (todo lo que se mueve solo más de 5 s debe poder pararse); el hero no. |
| «¿El texto se lee bien sobre la imagen?» (paso 4: degradado o foto aparte) | **Aplica y es el punto más flojo.** D'CASA usa justo el remedio de Feuxui (un degradado azul de marca, `dcasa.scss:771-785`), pero no alcanza en todas las fotos (cifras abajo). Además ese degradado **choca con la regla 3 de marca** (sin degradados). |
| «Un hero fijo: titular que diga qué haces y para quién, línea de apoyo, botón con verbo claro, imagen que acompaña» | **Cumple.** Titular + frase + «Ver el catálogo» (verbo claro) + las secciones de beneficios, categorías y carriles más abajo. En ese sentido D'CASA está más cerca de un «hero fijo con foto viva» que de un carrusel. |

**Contraste real del texto blanco sobre las 7 fotos** (píxeles medidos detrás del texto; «peor 5 %» = el 5 % más claro de la zona; las letras necesitan 4,5:1, y 3:1 si son grandes como el titular):

| Texto | A 390 px (celular) | A 1440 px (escritorio) |
|---|---|---|
| Kicker «Mueblería en La Chorrera…» (14 px) | 2,3 a 3,3 (peor 5 %); promedio 2,7 a 5,8 | 2,8 a 7,4 (casi siempre 3 a 4) |
| Titular (48 px celular / 88 px escritorio) | 2,7 a 3,1 (peor 5 %); promedio 3,6 a 4,7 | 2,8 a 3,6; 4 de 7 fotos bajo 3:1 |
| Frase de apoyo (16,8 px) | 4,4 a 6,0 (al borde) | 2,4 a 5,2; 6 de 7 fotos bajo 4,5:1 |
| Botón «Escríbenos por WhatsApp» (contorno, 16 px) | **8,3 a 8,8** (cae sobre la banda azul de abajo) | **1,6 a 2,3** (peor 5 %); promedio 2,1 a 3,0: **las 7 fotos fallan** |

Con la captura se ve igual: a 1440 px el botón de WhatsApp cae sobre la sábana clara de la cama (`portada_1440_arriba.png`). **El único CTA de la marca es el que peor se lee en computadora.** Limitaciones de esta medida: usé la foto parada en el instante en que cargó (el zoom la mueve un poco) y el 5 % más claro, que es duro; el promedio es más amable. Aun así, el promedio del botón de WhatsApp (2,1 a 3,0) tampoco llega a 4,5.

- **Veredicto:** 🟡 cumple a medias. Lo que **no** aplica de la crítica: los cinco mensajes y los botones por slide. Lo que **sí** aplica: movimiento sin forma de parar y texto que no siempre se lee. ⚠ Choca con la marca: regla 3 (degradado) y, por otro lado, con una decisión de la dueña (sin mandos).
- **Qué haría** (de más a menos barato):
  1. **Botón de WhatsApp del hero con relleno plano azul noche** (por ejemplo `rgba(navy, .78)` con borde blanco) en lugar de solo contorno: pasa a más de 8:1 sobre cualquier foto, es plano (cumple regla 3) y no toca el blanco con amarillo. **Poco esfuerzo**, riesgo bajo; es solo un cambio de `.o_dcasa_btn_linea` dentro del hero.
  2. Para kicker, titular y frase: usar el halo de letras que el sitio ya acepta («no una sombra dramática», `dcasa.scss:710`) también en el hero nuevo; hoy solo lo lleva el hero viejo. **Poco.** Mejora la lectura aunque no sea un cálculo de contraste exacto.
  3. **Que el movimiento se detenga solo** después de una vuelta completa de fotos (≈ 45 s con 7 fotos de 6,5 s) o con un botón pequeño de pausa. Cumple la pauta WCAG sin dar «mandos» a la persona. **Poco/medio** (en `portada.js`), riesgo bajo; **decisión de la dueña**, porque dijo que no quería control.
  4. Si la dueña quiere ganar más contraste sin degradado, la única vía plana es una placa lisa detrás del texto, que ella rechazó antes (`dcasa.scss:601-603`, «sin placa ni tarjeta»). Se lo dejo como decisión con los números de arriba.
  5. Limpieza: el comentario de `dcasa.scss:714-722` todavía describe el hero de dos columnas (bloque azul a la izquierda); ya no es así.

### 4 · Enlaces descriptivos
- **La regla de Feuxui:** un enlace debe decir a dónde lleva aunque se lea solo («mira la guía de tallas», no «haz clic aquí» ni «ver más»); subrayado además del color; enlace si lleva a otra página, botón si hace una acción; avisar si descarga un archivo o abre otra pestaña («(PDF, 120 KB)» o ↗).
- **D'CASA hoy (medido en 9 páginas distintas, 14 cargas, 121 textos de enlace únicos):**
  - **Cero** enlaces con «aquí», «clic aquí», «ver más» ni «leer más».
  - Los «Ver todo» de los carriles llevan el nombre de la sección en texto oculto: lectores de pantalla oyen «Ver todo: Lo más buscado» (`homepage_templates.xml:95`). Es exactamente la técnica correcta.
  - Otros enlaces que ya se entienden solos: «Cómo llegar y más información», «Síguenos en Instagram →», «Regístrate con tu celular», «Abrir la ruta en Google Maps», «Buscar “cama” en todo el catálogo».
  - **Avisan la pestaña nueva** (texto oculto o `aria-label`): los dos botones de WhatsApp del hero, el aviso de arriba, las tarjetas, «Síguenos en Instagram», «Verlas en Google», la ruta de Maps y el teléfono de `/visitanos`.
  - **No avisan:** el botón «Pregunta por este mueble por WhatsApp» de la ficha (`layout_templates.xml:130-133`) y los tres enlaces del pie (WhatsApp, Instagram, TikTok, `layout_templates.xml:346-349`), todos con `target="_blank"`.
  - **Subrayado:** los enlaces de texto de `/socios` van subrayados (pestañas y «Regístrate con tu celular»); los de «Ver todo» llevan línea inferior (`dcasa.scss:119`). Los del pie van en azul noche **sin** subrayado hasta pasar el ratón (`dcasa.scss:2161-2170`): por ser listas de enlaces es aceptable, pero Feuxui los subrayaría.
  - **Enlace o botón:** en el chat, la tarjeta de producto trae un botón con el texto visible «Ver» y el nombre completo solo en el `aria-label` (`brian_tienda.js:1443`): bien para lectores, genérico a la vista (aunque queda dentro de la tarjeta del producto). El botón de enviar de la búsqueda se llama «Búsqueda» (un sustantivo), mejor «Buscar».
  - Las acciones de compra (`Agregar al carrito`, `−`, `+`, `Enviar`, `Ordenar por`) son enlaces `<a href="#">` de Odoo que actúan como botones: semántica de Odoo, no de D'CASA; bajo valor.
- **D'CASA hoy, panel interno:** por código y capturas, los accesos del Inicio llevan título + frase («Productos · Stock, precio y categoría»), «Ver por día», «¿Qué necesito hacer?»; no encontré «aquí» ni «ver más» en `inicio.xml` ni en el cajón. No audité el texto de cada lista de Odoo.
- **Veredicto:** ✅ cumple (con dos detalles).
- **Qué haría:** (1) agregar «(se abre en una pestaña nueva)» oculto al botón de WhatsApp de la ficha y a los tres enlaces del pie. **Poco**, riesgo nulo. (2) Llamar «Buscar» al botón de la lupa. **Poco.** Sin choque con la marca.

### 5 · Íconos con texto
- **La regla de Feuxui:** «un ícono sin texto solo funciona si es universal. Casi ninguno lo es»; solo la lupa, la X de cerrar, el play y «inicio» van solos; el corazón, la estrella, la flecha de subir, etc. necesitan una palabra. Barras de navegación de **máximo cinco** opciones, con ícono + palabra; acciones fuera de la barra; una sola familia de íconos del mismo trazo.
- **D'CASA hoy, sitio público (medido):**
  - **Cabecera a 390 px:** tres íconos sin texto visible: lupa (`aria` «Buscar en el catálogo»), carrito con número (`aria` «Carrito de comercio electrónico») y hamburguesa (`aria` «Alternar navegación»). Con la lectura estricta de Feuxui, solo la lupa va sola; carrito y hamburguesa son casi universales en tienda en línea y en celular, y son tres íconos, no una barra de cinco. A 1440 px el menú tiene texto, y el carrito y la lupa siguen siendo íconos.
  - **Aviso de arriba (celular):** WhatsApp solo con su ícono (el texto se oculta bajo 576 px).
  - **Tarjetas de producto de la portada:** «agregar» es un **carrito con un +** sin texto (80×48) y WhatsApp es el logo en un círculo (48×48). Fue un pedido de la dueña (`homepage_templates.xml:12-13`: «quien compra en línea lo reconoce sin la palabra»). El logo de WhatsApp es de marca reconocida; el «carrito con +» es razonable pero la ayuda (`title`) no se ve al tocar. En `/shop` ya es distinto: a 390 px un carrito de 44×44 sin texto, a 1440 px «**AGREGAR AL CARRITO**» con ícono y texto (mismo botón, dos criterios).
  - **Burbuja del chat de Andrés:** un robot sin ninguna palabra, 68×68 (`brian_tienda.scss:108`: «La burbuja (sin texto)»). No es un ícono universal; solo el `aria-label` «Abrir el chat de la tienda» lo dice.
  - **Cámara de «Busca con una foto»:** dentro de la caja de búsqueda, un ícono de cámara **azul y más llamativo que la lupa**, con el texto «Busca con una foto» oculto a propósito (`dcasa_buscar_foto/views/templates.xml:28-37`, `dcasa_foto_solo_icono=True`). Es la función menos conocida y la única con un ícono ambiguo (¿tomo una foto?, ¿adjunto algo?).
  - **Dentro del chat (captura anterior):** cabecera con WhatsApp, ampliar y cerrar (flecha hacia abajo), los tres sin texto; enviar (avión de papel) sin texto; el micrófono sí trae su frase «Si prefieres, mándame una nota de voz» debajo. Chips de respuesta rápida: solo texto, bien.
  - **Con texto, bien:** menú del cajón, «Filtros», «Ordenar por», carrito vacío, botones del hero y del pie (ícono + palabra). En el pie, WhatsApp, correo, Instagram y TikTok llevan ícono **y** texto.
  - **Familia de íconos:** mezcla de FontAwesome 4 (`fa-whatsapp`, `fa-truck`), SVG propios con trazo de 1,9-2,2 y los íconos del chat (trazo 2): cercanos pero no idénticos. Detalle menor.
- **D'CASA hoy, panel interno:**
  - **Inicio:** accesos con ícono + título + frase (bien). Header: «Ver la tienda» es un ícono solo (con `title`) (`inicio.xml:67`).
  - **Barra de arriba (celular y computadora):** globo de chat con número, **reloj** (actividades), **estrella de Brian** y la inicial de la persona: cuatro íconos sin texto (capturas `4_inicio_celular.png`, `barra_despues_390.png`). El chat y el reloj son de Odoo; ninguno es universal para una vendedora nueva.
  - **Computadora:** la barra lateral en modo «auto» es una franja de **17 íconos sin nombre** hasta pasar el ratón (ver concepto 2). Es el caso que Feuxui más critica: muchos íconos de apps de colores distintos que obligan a adivinar.
  - **Formularios:** «Nuevo» (con texto), pero engranaje, globo de chat y flechas del paginador solo con ícono (Odoo).
- **Veredicto:** 🟡 cumple a medias (sitio y panel).
- **Qué haría:**
  1. **Panel:** barra lateral con nombres a la vista (ver concepto 2). **Poco/medio.** Es el cambio de más efecto de todo el concepto.
  2. **Sitio:** en el celular, ponerle texto corto a la cámara del buscador la primera vez («Busca con una foto» como globo o texto bajo la caja) o cambiar el placeholder a «Escribe lo que buscas o sube una foto». **Poco.**
  3. **Sitio:** dar a la burbuja del chat una palabra el primer rato («Pregúntale a Andrés» como etiqueta que desaparece al hacer scroll). **Poco/medio**, y hay que cuidar que no tape botones; es decisión de la dueña porque la quiso «sin texto».
  4. `/shop` en celular: «agregar» con la palabra **o** que toda la tienda use el mismo ícono con `aria-label`; hoy usa dos criterios. **Poco.**
  5. Ninguno choca con la marca.

### 6 · Etiquetas de formulario
- **La regla de Feuxui:** «El placeholder no es etiqueta»: la **etiqueta siempre visible arriba del campo**; el placeholder, si existe, solo da un ejemplo. Cuatro piezas: etiqueta arriba, ayuda antes del error, error junto al campo, botón que dice qué va a pasar («Crear cuenta», «Enviar mensaje», no «Enviar» a secas). Campo con error marcado con algo más que color.
- **D'CASA hoy (medido en vivo; sin enviar nada):**
  - **Contacto (`/contactus`):** ✅ etiquetas visibles arriba de cada campo («Nombre *», «Número de teléfono», «Correo electrónico *», «Asunto *», «Pregunta *»), `autocomplete` correcto (`name`, `tel`, `email`), tipos `tel` y `email`, **sin placeholder**. Lo que falta: los campos miden **38 px** (360×38) y el botón es «**Enviar**» (77×38), un verbo suelto y pequeño; no hay ayuda antes del error ni se ve cómo son los errores (no los pude probar sin enviar).
  - **`/socios` (entrar):** ✅✅ el mejor formulario del sitio: «Tu celular» y «Tu PIN (6 números)» como etiqueta arriba, **placeholder solo como ejemplo** («6000-0000»), `inputmode="numeric"`, `autocomplete` correcto, campos de **48 px**, botón «Entrar» de 308×59 a todo el ancho y el enlace «¿Primera vez? Regístrate con tu celular» subrayado.
  - **Buscador (cabecera, cajón del celular y `/shop`):** ❌ el campo se llama solo por su placeholder «Escribe lo que buscas»: **sin `<label>`, sin `aria-label`** (medido: `aria` vacío en las 3 cajas). En el cajón del celular el placeholder se **corta**: «Escribe lo que bus…». El botón de enviar es un ícono con `aria` «Búsqueda» y la cámara va sin texto (concepto 5). Hay que decir en favor de D'CASA que en un buscador con lupa es el patrón corriente y que el placeholder cambia a «Escribe lo que buscas» en toda la tienda (`buscador_templates.xml:22-33`).
  - **Filtros de `/shop`:** los dos controles de precio (`input type=range`) **no tienen nombre** para el lector de pantalla; sí muestran los valores visibles («$15.99» y «$386.07»). Los títulos «Tamaño», «Color» y «Rango de precio» son acordeones de 52 px.
  - **Checkout público (`/shop/address`):** **no lo pude abrir en vivo**. Por código es el formulario de Odoo (`vendor/odoo/addons/portal/views/address_templates.xml:161-351`): `<label for>` visibles sobre cada campo y la marca «opcional» (`label-optional`), no placeholder. D'CASA retoca el texto «¿Ya tienes cuenta?» (`tienda_templates.xml:116-121`) y los pasos apagados del asistente (`dcasa.scss:2005-2008`). La auditoría anterior `docs/auditoria/sitio-web.md` (SW-08) cubre el campo de RUC. **Por verificar** con capturas en celular.
  - **Chat de Andrés:** el campo de texto tiene su etiqueta oculta («Escribe tu mensaje», `brian_tienda.js:1040`) y un placeholder que cambia según la pregunta («Barrio, PH o un punto de referencia», `:2377, 2391`), es decir, el placeholder lleva una instrucción que desaparece al escribir; queda cubierta porque Andrés la pregunta antes en un globo.
- **D'CASA hoy, panel interno:** los formularios de Odoo muestran la etiqueta arriba del campo en celular (capturas `est_despues_390_draft.png`: «Cliente»). Según la auditoría `docs/auditoria/ui-backend.md` (UI-22, 30/09; **no sé si se arregló**), los buscadores de reportes y conciliación llevan solo placeholder sin `aria-label`, y en `/socios` el cumpleaños tenía `<label>` sin `for` (UI-21). La pantalla de pago del portal (captura de pruebas `tilopay_v2/03_pedido_formas_de_pago_celular.png`) tiene botón «Pagar» ancho abajo, bien.
- **Veredicto:** 🟡 cumple a medias (contacto y `/socios` ✅; buscador ❌ por el nombre y el corte; checkout sin medir).
- **Qué haría:**
  1. Buscador: `aria-label="Buscar en el catálogo"` en las 3 cajas y botón «Buscar»; acortar el placeholder a «Busca un mueble» para que no se corte en el cajón. **Poco**, riesgo nulo.
  2. Contacto: «Enviar» → «**Enviar mensaje**», a todo el ancho en celular y 48 px, y campos de 44-48 px (copiar lo de `/socios`). **Poco** (es CSS de la plantilla `contactus_dcasa`).
  3. Filtros: `aria-label` en los dos controles de precio. **Poco.**
  4. Con una prueba que **no envíe**, escribir un correo mal formado en el contacto y ver el mensaje de error (Feuxui pide que salga junto al campo y diga cómo arreglarlo). **Poco** (de revisión, no de código).
  5. Sin choque con la marca.

### 7 · Jerarquía de botones
- **La regla de Feuxui:** **un solo botón principal por pantalla**; los demás, un escalón abajo. Cuatro niveles: principal (lleno y en color de acento), secundario (borde, sin relleno), terciario (solo texto) y destructivo (rojo, solo para lo que borra). Cada botón con un verbo; explicar la consecuencia antes del clic en acciones delicadas.
- **D'CASA hoy, sitio público (medido):**
  - **Portada:** 1 lleno amarillo («Ver el catálogo») + 1 contorno blanco («Escríbenos por WhatsApp») ✔ dos niveles. Más abajo, «Ver lo disponible» (lleno azul) + «Pregunta qué hay hoy» (contorno), «Ver mis puntos» (amarillo sobre azul noche) + «Cómo funciona» (contorno), «Cómo llegar y más información» (amarillo): **un par lleno + contorno por sección**, siempre separadas por bandas. La burbuja del chat es un círculo azul lleno **siempre presente**: en la primera pantalla de la portada es, además del botón amarillo, un segundo elemento lleno compitiendo.
  - **Ficha:** WhatsApp **lleno** («Pregunta por este mueble por WhatsApp», `layout_templates.xml:127-140`) y «Agregar al carrito» en **contorno** (`dcasa.scss:2889-2897`: «“Agregar al carrito” es la opción secundaria; WhatsApp va primero y lleno»). Es una jerarquía clara, pero a 390 px la **única acción visible en la primera pantalla** es la barra fija de «Agregar» (contorno), porque el botón lleno queda en y=858. (Hay un comentario viejo en `dcasa.scss:1981` que dice lo contrario, «“Agregar al carrito” manda»: contradice al de la línea 2889.)
  - **Carrito vacío:** «Ver el catálogo» lleno (360×59) + «Escríbenos por WhatsApp» contorno (360×61): ✔ modelo de jerarquía.
  - **Búsqueda sin resultados:** WhatsApp lleno a todo el ancho (346×59) y seis categorías en contorno: ✔.
  - **Contacto:** «Escríbenos por WhatsApp» lleno grande (274×59) arriba y «Enviar» lleno pequeño abajo: dos llenos en la misma página, pero a una pantalla de distancia entre sí, y el de WhatsApp es el principal.
  - **Destructivo:** el sitio público no tiene acciones que borren (no hay rojo en la paleta de marca).
  - **Verbos:** «Ver el catálogo», «Escríbenos por WhatsApp», «Agregar al carrito», «Entrar» ✔; «Enviar» ✘ (concepto 6).
- **D'CASA hoy, panel interno:**
  - **Inicio:** el encabezado tiene «¿Qué necesito hacer?» (contorno) y hasta **tres botones llenos azules iguales**: «Nueva cotización», «Nuevo cliente», «Registrar cobro», más «Ver la tienda» (ícono, también lleno) (`inicio.xml:46-71`; captura `4_inicio_computadora.png`). El propio comentario dice «Todos los botones del encabezado son azules (pedido del jefe, 2026-10-16)» y que «Nueva cotización es el botón principal», pero visualmente pesan igual. Debajo, **9 o 10 tarjetas azules llenas** de acceso (`4_inicio_celular.png`: en el celular la primera pantalla entera es una pared de tarjetas azules del mismo peso). Es el caso de «tres botones iguales» de Feuxui.
  - **Cotización en celular:** «Enviar por WhatsApp» lleno en la barra de estado, «Nuevo» y «Descuento»/«Agregar envío» en contorno, «Pedir descuento a Gerencia» en gris suave: **buena escala de cuatro niveles** (`t3_botones_vendedora_cel.png`, `est_despues_390_draft.png`).
  - **Destructivo:** la marca no define un rojo; en el panel el rojo ya existe para avisos (globo del chat). Las acciones de riesgo de Socios están restringidas a gerente y piden confirmación, según `ui-backend.md`.
- **Veredicto:** 🟡 sitio público (jerarquía buena en las pantallas pequeñas, con dos dudas); ❌ **Inicio del panel** (tres llenos iguales + tarjetas llenas).
- **Qué haría:**
  1. **Inicio del panel:** «Nueva cotización» lleno; «Nuevo cliente» y «Registrar cobro» en contorno; las tarjetas de acceso en blanco con borde azul y el ícono azul (hoy llenas). Es solo CSS/clases de `interfaz.scss` y `tablero.scss`. **Poco/medio**, riesgo bajo, y es **decisión del jefe** porque fue su pedido del 2026-10-16.
  2. **Portada:** decidir el principal (ver «Lo que choca con la marca», punto 2). **Poco.**
  3. **Ficha en celular:** poner también el botón lleno de WhatsApp dentro de la barra fija, o dejarlo a la vista sin bajar. **Medio** (hay que cuidar el espacio de la barra de 360 px, `dcasa.scss:2107-2128`).
  4. Escribir en `CLAUDE.md` la regla «un lleno por pantalla» (parte 1).

### 8 · Texto centrado
- **La regla de Feuxui:** centrar solo lo corto (titular, frase, botón); **desde la tercera línea, alinear a la izquierda** (con dos líneas va bien, tres es el límite). Que todo el texto de una tarjeta comparta un solo borde; el texto justificado abre huecos. En español, mayúscula solo en la primera palabra de un título.
- **D'CASA hoy (medido):**
  - **Titulares, frases, párrafos del hero, tarjetas de producto, reseñas, preguntas y pie: todo alineado a la izquierda** (`text-align: start` en todos los párrafos de 3 o más líneas medidos; las reseñas de 4 líneas a 390 px también). Las tarjetas (nombre, precio, botones) comparten un borde izquierdo: ✔ es el «después» de Feuxui.
  - **Lo centrado:** carrito vacío (título y una línea, 1 línea medida), el aviso del mapa («El mapa es de Google…», 2 líneas), los botones, y la búsqueda sin resultados (`.o_dcasa_sin_resultados`): título + frase de **3 líneas** a 390 px («Prueba con otra palabra o mira por espacio. Si no lo ves, escríbenos: te ayudamos a buscarlo.») + chips. Es **justo el límite** de Feuxui (a 1440 px la caja es más ancha y baja a menos líneas).
  - **Mayúsculas:** los nombres de producto salen en formato título («Cama de Felpa Twin Blanca con Cabecero Curvo»), contra el consejo de «solo la primera». Fue una **decisión de la dueña** (F5, 2026-10-22, `nombres_cliente_templates.xml:2-4`), así que no se toca sin su sí. Los titulares de marca van en mayúsculas sostenidas en Anton, por regla 2: Feuxui no los considera.
  - **Panel:** el Inicio y las listas van a la izquierda; el estado vacío («No hay cotizaciones abiertas», `sin_odoo.js`) es corto.
- **Veredicto:** ✅ cumple.
- **Qué haría:** nada urgente. Si se quiere afinar: en `.o_dcasa_sin_resultados` pasar la frase a alineada a la izquierda en celular (o partirla en dos líneas) para quedar a una línea del límite. **Poco**, riesgo nulo. El tema de mayúsculas es de la dueña (ver «Lo que choca»).

---

## Lo más importante (las 8 mejoras de mayor efecto y menor costo, en orden)

1. **Botón «Escríbenos por WhatsApp» del hero con relleno plano azul noche** (hoy contorno transparente: 1,6 a 2,3:1 en escritorio sobre las 7 fotos; con relleno pasa de 8:1). Concepto 3. *Poco esfuerzo.* Es el único CTA de la marca.
2. **Zonas táctiles de 44 px o más** en: hamburguesa (40×42), «Ordenar por» y «Filtros» (38), X del cajón (32), «Mi cuenta» del cajón (37), «Eliminar filtros» (34), «Enviar» del contacto (77×38) y campos de 38 px. Conceptos 1 y 6. *Poco* (extender el bloque `pointer: coarse` de `dcasa.scss:3186-3210`).
3. **La burbuja de Andrés deja de tapar** el cajón del menú y los chips de búsqueda y se separa del botón del hero. Concepto 1. *Poco.*
4. **Buscador con nombre para el lector de pantalla y sin cortarse**: `aria-label`, botón «Buscar», placeholder más corto, y una pista visible para la cámara «Busca con una foto». Conceptos 5 y 6. *Poco.*
5. **Contacto: «Enviar mensaje», ancho completo y 48 px**, copiando `/socios`. Concepto 6. *Poco.*
6. **Hero: que el movimiento se detenga solo tras una vuelta (≈45 s)** o con una pausa mínima; halo de letras en kicker, titular y frase. Concepto 3. *Poco/medio*; **decide la dueña** (pidió «sin control»).
7. **Panel: barra lateral con nombres desde 1200 px y un solo botón principal en el Inicio.** Conceptos 2, 5 y 7. *Poco/medio*; lo del Inicio lo decide el jefe.
8. **Escribir «Reglas de interfaz» en `CLAUDE.md`** (8 líneas, parte 1) y la lista «Antes de publicar» en la plantilla del PR. *Poco.* Lo que no queda escrito se pierde cuando el contexto se reinicia (regla del propio repositorio).

*(Detalle menor, sin número: aviso de «se abre en pestaña nueva» en el botón de WhatsApp de la ficha y en los 3 enlaces del pie; `aria-label` en los controles de precio.)*

## Lo que choca con la marca (para que decida Gerencia)

1. **Degradado en el hero (regla 3: sin degradados).** Feuxui recomienda justo un degradado o una foto aparte para que el texto se lea (concepto 3, paso 4; y «overlays y capas»). D'CASA ya usa un degradado azul de marca (`dcasa.scss:771-785`) y la dueña lo eligió entre cinco opciones. **No lo recomiendo ampliar.** Alternativas planas: relleno plano en el botón (mejora 1, sin choque) y halo de letras (ya aceptado). La placa lisa detrás del texto la rechazó antes la dueña.
2. **Cuál es el botón principal del hero (regla 5: «CTA único: Escríbenos por WhatsApp»).** El hero y el carrito vacío ponen *Ver el catálogo* como principal (lleno) y WhatsApp como secundario; la ficha, el contacto y la búsqueda sin resultados ponen WhatsApp lleno. Feuxui pide **uno** principal por pantalla. Gerencia debe decidir si la regla 5 manda también en la portada (WhatsApp lleno y catálogo en contorno) o si en la portada manda el catálogo; hoy se cumplen las dos a medias. No es un error del código: es una pregunta de marca.
3. **Fondo en movimiento sin mandos (decisión de la dueña, no regla de marca).** Choca con «nada se mueve solo» de Feuxui y con la pauta WCAG 2.2.2. Se resuelve sin quitarlo (se detiene solo o pausa mínima), pero toca lo que ella pidió.
4. **Mayúscula solo en la primera palabra (Feuxui) frente a nombres en formato título (decisión F5 de la dueña, 2026-10-22).** No es una regla de marca numerada; es un criterio suyo. No lo cambiaría.
5. **Rojo para lo destructivo (Feuxui) frente a la paleta (regla 1: azul y amarillo).** La marca no define un rojo. Si el panel va a tener acciones que borran, hay que decidir un rojo único y reservado para eso (hoy el rojo ya aparece en avisos del chat).
6. **Todos los botones del encabezado del Inicio azules (pedido del jefe, 2026-10-16) frente a «un principal por pantalla».** Otra decisión de persona, no de regla de marca.
7. **Texto sobre foto con halo oscuro** (ya aceptado en `dcasa.scss:710` como «no una sombra dramática»): lo marco para que Gerencia confirme que sigue entrando en la regla 3 al usarlo en el hero nuevo.

## Lo que D'CASA ya hace mejor o igual que Feuxui (con evidencia)

- **Menú:** hamburguesa solo en celular, 3 enlaces (Feuxui pide ≤5), menú a la vista en escritorio con la sección activa marcada, y el cajón del celular con filas de 55 px y buscador adentro (medido en vivo). El cajón del panel (`menu_celular.xml`) tiene «Inicio» y «Buscar» fijos y la lista con ícono **y** nombre.
- **Enlaces:** ni un solo «aquí», «clic aquí» ni «ver más» en 9 páginas (121 textos de enlace únicos revisados); «Ver todo: <sección>» con el nombre en texto oculto (`homepage_templates.xml:95`), avisos de pestaña nueva en casi todos los casos y enlaces subrayados en `/socios`.
- **Formularios:** `/socios` es un ejemplo de manual (etiqueta arriba, placeholder de ejemplo, `inputmode`, `autocomplete`, 48 px, botón de 59 px a todo el ancho). El contacto tiene etiquetas visibles y autocompletado. El campo del chat tiene su etiqueta oculta.
- **Zona del pulgar:** botones del hero entre el 79 % y el 93 % de la altura; barra de compra fija abajo en la ficha; tarjetas con botones de 48 px; carrito vacío y búsqueda sin resultados con botones a lo ancho; filtros en cajón con filas de 52 px. Ya hubo dos pasadas de «44 px» (sitio y panel) con tests (`dcasa.scss:3186-3210`; `global.scss:311-320`).
- **Texto centrado:** todo el texto largo, las tarjetas, el hero y el pie van a la izquierda; lo centrado es corto (carrito vacío 1 línea, mapa 2 líneas).
- **Jerarquía:** carrito vacío (lleno + contorno), ficha (WhatsApp lleno + «Agregar» contorno), cotización en el panel (cuatro niveles: lleno, contorno, gris suave, texto).
- **Hero frente al carrusel clásico:** sin flechas, sin puntos, sin textos que cambien, sin botones por foto; decorativo con `aria-hidden`; respeta «reducir movimiento» (`portada.js:52`); la sección «de cine» sí trae pausa (`portada.js:112-160`). Un solo `<h1>`.
- **Proceso:** capturas en celular y computadora antes de subir, revisión adversarial, contrato visual con pruebas (`test_contrato_visual.py`) y la bitácora: eso que Feuxui llama «ojo de diseñador» y «afinar» ya se practica, solo falta escribir el criterio de interfaz.

---

### Apéndice · Cifras sueltas medidas (390 px salvo que se diga)

| Qué | Medida |
|---|---|
| Hero: alto / fotos / tiempo por foto / fundido / ciclo de zoom | 844 px / 7 / 6,5 s / 1,8 s / 38 s |
| Hero: titular | Anton 48 px, interlineado 48,96 px, tracking 0,24 px |
| «Ver el catálogo» (amarillo sobre navy, texto navy) | 185×55, contraste 9,12:1 |
| «Escríbenos por WhatsApp» del hero | 282×55, contorno blanco al 90 %; contraste real 8,3-8,8 (390) y 1,6-2,3 (1440, peor 5 %) |
| Cabecera: lupa / carrito / hamburguesa | 44×44 / 44×44 / 40×42,4 |
| Burbuja del chat | 68×68 (celular), 78×78 (escritorio); contraste del círculo no aplica |
| Cajón del menú: filas / X / «Mi cuenta» | 342×55 / 32×32 / 310×37 |
| Ficha: barra fija | cantidad 44×44, «Agregar» 218×48 en y 784 |
| `/shop`: agregar / categorías / «Ordenar por» / «Filtros» | 44×44 / 52 de alto / 38 / 38 |
| Contacto: campos / «Enviar» | 360×38 / 77×38 |
| `/socios`: campos / «Entrar» | 308×48 / 308×59 |
| Carrito vacío: botones | 360×59 y 360×61 |
| Pie: enlaces | alto 43,2 px; «Cómo llegar» 91×20 |
| Texto del cuerpo | Inter 16 px, interlineado 24 px |
| Elementos que se tocan en la portada (390 / 1440) | 163 / 170; bajo 44 px en 390: 17 |
