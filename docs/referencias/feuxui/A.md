# Informe A · Color, profundidad y criterio (Feuxui contra D'CASA)

Conceptos que cubre este informe (13): contraste, paleta de color, color y fondo, temperatura de color, saturación, caída de luz,
sombras, overlays y capas, ruido y grano, efectos, ojo de diseñador, principio KISS y «rompe las reglas».

## Cómo medí (para que se pueda creer en los números)

- **Sitio en vivo** (`https://dcasapty.com`, solo lectura): 26 cargas de página en total, con 1 s de pausa; no escribí en el chat de
  Andrés, no envié formularios ni toqué el panel. Páginas: portada, categoría Recámaras, ficha «Cama King Black 2806», carrito vacío,
  contacto y Socios; a 1440 px y a 390 px (Socios solo a 1440 px).
- **Ratio de contraste** = la fórmula exacta de WCAG: `(L1 + 0.05) / (L2 + 0.05)`, con la luminancia calculada canal por canal.
  Lo comprobé contra el ejemplo de Feuxui: su azul `#1417FB` da **6.99:1** sobre `#ECECEE` y **2.47:1** sobre `#050505` (ellos dicen 7.0 y
  2.5). Para leer los números: 1:1 es no verse; **4.5:1** es el mínimo para texto normal; **3:1** para titulares grandes; 21:1 es negro sobre blanco.
- **Texto sobre fondo liso:** para cada texto visible de cada página calculé su color real y el color real de lo que tiene detrás
  (sumando capas con transparencia y la opacidad de los padres).
- **Texto sobre las fotos del hero:** el navegador no puede «saber» el fondo cuando hay foto y degradado, así que **oculté el texto,
  fotografié el fondo real y medí cada píxel que queda detrás de cada línea de texto**, en 20 fotogramas seguidos (34 s: las 7 fotos del
  carrusel, con su zoom y sus fundidos). Probé la simulación del degradado contra el sitio real: se desvía 0.45 de 255 por canal.
- **Reparto de color (regla 60-30-10):** pinté las fotos de magenta en mi copia local de la página, la fotografié entera y clasifiqué cada
  píxel por color de marca (tolerancia ±3). Todo cambio de prueba (por ejemplo el degradado nuevo) lo puse **solo en mi navegador**: producción no se tocó.
- **Panel interno:** solo código (`tokens.scss`, `interfaz.scss`, oscuro) y la captura del Inicio del 2 de noviembre
  (`$S/capturas/4_inicio_*.png`; el código de esas tarjetas sigue igual). No medí el panel en vivo.
- Capturas y scripts: `$S/feux/capturas_A/` y `$S/feux/scripts_A/` (`$S` = `/tmp/claude-0/-home-user-D-Casa-new-word/df109763-bd03-5083-be8c-fbf5e389a556/scratchpad`).

### Ratios exactos de los pares de la marca

| Texto sobre fondo | Ratio | Uso |
|---|---|---|
| Blanco sobre azul `#1340B1` | 8.76:1 | botones, barras |
| Blanco sobre navy `#0E2A6B` | 13.44:1 | bandas, barra de anuncios |
| Amarillo `#FED00F` sobre azul | 5.94:1 | botón amarillo sobre azul |
| Amarillo sobre navy | 9.12:1 | cifras de Socios, etiquetas de las fotos |
| Navy sobre amarillo (texto del botón) | 9.12:1 | botón «Ver el catálogo» |
| Azul sobre blanco / hueso `#F6F5F2` | 8.76 / 8.04:1 | titulares, precios, enlaces |
| Navy sobre hueso | 12.33:1 | menú, categorías |
| Tinta `#1B2233` sobre blanco / hueso | 15.87 / 14.56:1 | texto de cuerpo |
| Gris `#4A5163` sobre blanco / hueso / hueso-2 | 7.93 / 7.27 / 6.41:1 | textos de apoyo (el comentario de `dcasa.scss:17` dice 7.4 sobre hueso: hoy es 7.27) |
| **Blanco sobre amarillo** | **1.47:1** | la combinación que la regla 1 prohíbe: la prohibición está bien puesta |
| Azul sobre navy | 1.53:1 | no se usa |

---

### 1 · Contraste
- **La regla de Feuxui:** el texto debe tener **4.5:1** (normal) o **3:1** (titular grande: unos 24 px, o 19 px en negrilla) contra lo que
  tiene detrás; brillo opuesto; el titular al menos el doble de grande que el texto; «mide, no adivines» y revísalo en el celular con poco brillo.
- **D'CASA hoy:**
  - **Fondos lisos: muy bien.** En portada, categoría, ficha, carrito, contacto y Socios, y dejando aparte las tres excepciones de abajo, el texto más bajo es la línea de derechos
    reservados: `#5D5F60` sobre `#E9E7E1` = **5.18:1**. Todo lo importante está entre 7.27 y 15.87:1.
  - **Tres fallas reales fuera de las fotos:**
    1. Las marcas de relleno (placeholder) de los campos: la búsqueda «Buscar en Recámaras» es `#909294` sobre `#F6F5F2` = **2.86:1** (16 px),
       y el celular de «Mis puntos» (`6000-0000`) es **3.12:1** sobre blanco. No hay ninguna regla propia: es el gris por defecto de Odoo
       (en el repo no hay `::placeholder` salvo en el chat).
    2. Los pasos del carrito que aún no tocan («Dirección», «Pago»): el sitio ya pidió gris oscuro (`dcasa.scss:2005-2009`, `#4A5163` =
       7.93:1), pero Odoo deja esos pasos al 50 % de opacidad (`vendor/odoo/addons/web/static/src/scss/ui.scss:10-13`) y lo que ve la persona
       es `#A5A8B1` sobre blanco = **2.38:1** (medido en vivo en `/shop/cart`). El arreglo quedó neutralizado.
    3. El «…» de la paginación: `#909294` sobre blanco = 3.12:1. Es un botón apagado: es lo de menor importancia.
  - **Texto sobre las fotos del hero de la portada (el punto débil), medido en píxeles reales, 20 fotogramas:**

    | Texto | Pantalla | Mediana | Peor píxel | Píxeles bajo el mínimo | Mínimo que pide Feuxui |
    |---|---|---|---|---|---|
    | Titular «Tu casa, bien amueblada.» (104 px) | 1440 | 4.60:1 | 2.39:1 | 9.1 % bajo 3:1 | 3:1 |
    | Subtítulo «Salas, recámaras…» (20 px) | 1440 | **4.43:1** | 2.17:1 | **51 % bajo 4.5:1** | 4.5:1 |
    | Antetítulo «Mueblería en La Chorrera…» (14 px) | 1440 | 5.25:1 | 2.69:1 | 37.5 % bajo 4.5:1 | 4.5:1 |
    | Titular (48 px) | 390 | 3.88:1 | 2.46:1 | 6.1 % bajo 3:1 | 3:1 |
    | Subtítulo (17 px) | 390 | 5.30:1 | 4.21:1 | 2 % bajo 4.5:1 | 4.5:1 |
    | **Antetítulo (14 px)** | 390 | **3.10:1** | 2.07:1 | **71 % bajo 4.5:1** | 4.5:1 |

    En computadora, el subtítulo tiene la mediana bajo 4.5:1 en 15 de los 20 fotogramas; en el celular, el antetítulo en 15 de 20. Pasa
    justo cuando la foto del momento es la cama blanca (fotos 4 y 5 de las 7; ver `capturas_A/hero_antes_hoja_1440.png` y
    `hero_portada_1440_peor_fondo_marcado.png`, donde el rojo marca los píxeles bajo 3:1). **El titular se lee** (es enorme y blanco), pero el
    subtítulo y el antetítulo quedan lavados sobre la tela blanca.
  - **Hero de páginas interiores** (velo negro plano al 55 %): Contacto **4.75:1** el peor píxel del titular y **5.28:1** el del antetítulo;
    Socios **4.84** y **7.46:1**. Aprobado en todos los píxeles medidos.
  - **Cabecera de vidrio sobre foto:** el texto del menú queda alrededor de 10:1 (tinta sobre vidrio claro) y 10-16:1 (blanco sobre vidrio
    ahumado), medido a ojo sobre la captura (percentiles de luminancia, no la fórmula por píxel de letra).
  - **Titular contra texto (≥ 2×):** hero 104/20 = 5.2×; secciones 40/16 = 2.5×; ficha 32/16 = **2.0×** (justo en el límite).
  - **Por qué el problema pasó sin verse:** una prueba del sitio (`tests/test_diseno.py:125-188`) sí mide contraste en píxeles, pero solo del
    hero **antiguo** (`.o_dcasa_hero`) y con la **mediana**; el hero nuevo en carrusel (`.o_dcasa_vitrina`, 17 nov) solo se comprueba que el
    degradado sea azul y no negro (`test_contrato_visual.py:480-509`), no cuánto contraste da. Y un verificador automático que lee solo el
    HTML ve el fondo base `#E9E7E1` y declara «1.24:1» (falsa alarma): no ve el degradado ni las fotos.
- **Veredicto:** 🟡 cumple a medias. Fondos lisos: ✅ (mínimo 5.18:1 salvo 3 excepciones). Hero sobre foto: ❌ en subtítulo y antetítulo.
- **Qué haría:**
  1. **Hero** (ver concepto 8, que trae los valores): subir la capa azul donde va el texto. Esfuerzo **poco** (4 números), riesgo **medio**
     (cambia el aspecto; la dueña dijo «el fondo no lo quiero oscuro», así que se le muestra antes con capturas, como siempre).
  2. **Placeholders:** `::placeholder { color: $dcasa-gris; opacity: 1; }` en `dcasa.scss` (7.27:1 sobre hueso, 7.93 sobre blanco).
     Esfuerzo **poco**, riesgo **bajo**.
  3. **Pasos del carrito:** añadir `opacity: 1` a la regla de `dcasa.scss:2006` (`.o_wizard .o_disabled`): pasaría de 2.38 a 7.93:1.
     Esfuerzo **poco**, riesgo **bajo**.
  4. **Panel y chat:** el gris `--dc-tinta-3` `#6B7690` (`tokens.scss:32`; `brian_tienda.scss:15`) da 4.55:1 sobre blanco pero **4.20** sobre
     niebla `#F4F6FA`, 3.97 sobre perla y 3.84 sobre azul-100 (el código ya lo usa sobre niebla en `pantallas.scss:207`). Oscurecerlo a
     `#5F6A84` da 5.41 / 5.00 / 4.73 / 4.56:1. Esfuerzo **poco**, riesgo **bajo** (un tono más oscuro en textos secundarios; el modo oscuro no cambia).
  5. **Una prueba nueva** que mida los píxeles del hero en carrusel con cada foto del carrusel (peor píxel, no mediana), para que un cambio de
     fotos en el panel no vuelva a romper el contraste. Esfuerzo **medio**, riesgo ninguno.

### 2 · Paleta de color
- **La regla de Feuxui:** tres colores (principal, secundario, acento) más neutros; reparto **60-30-10**; el acento aparece en una o dos
  cosas «porque es escaso»; anota los tres códigos y repítelos; si agregas un color, saca otro.
- **D'CASA hoy:**
  - Los tres códigos están escritos una vez y se repiten: azul `#1340B1`, amarillo `#FED00F`, navy `#0E2A6B` (`primary_variables.scss:15-19`,
    `dcasa.scss:6-17`), con neutros hueso `#F6F5F2`, blanco, tinta `#1B2233` y gris `#4A5163`; el panel y el chat los repiten (`tokens.scss`, `brian_tienda.scss:11-16`).
  - **Reparto real por área** (sin contar fotos; el hero cuenta como foto), a 1440 px:

    | Página | Neutros (blanco + hueso) | Azul + navy | Amarillo | Otros (letras, bordes) |
    |---|---|---|---|---|
    | Portada (34 % de la página son fotos y hero) | **80.7 %** | **15.3 %** (navy 12.9 + azul 2.4) | **0.8 %** | 3.3 % |
    | Ficha de producto (16 % son fotos) | 85.5 % | 5.7 % | **0 %** | 8.9 % |
    | Categoría Recámaras (19 % son fotos) | 92.2 % | 4.6 % | 0 % | 3.2 % |

    No es 60-30-10: en la portada es más bien **80-15-1**, y en la ficha **85-6-0**. Es más sobrio que lo que enseña Feuxui, no más ruidoso. El
    documento de diseño (`docs/historico/REDISENO.md`) decía «fondo base hueso cálido 60 %»: el hueso solo es el 31.7 %; con el blanco, 80 %.
  - **El acento (amarillo) es escaso de verdad:** 0.8 % del área de la portada, siempre sobre azul o navy (regla 1). Pero en la ficha y la
    categoría **no hay amarillo** (la regla 1 lo impide sobre fondo claro): ahí el azul hace de secundario (títulos, precio, enlaces, iconos,
    «Disponible», migas) **y** de acento (botones). En la ficha medí al menos nueve textos o piezas en azul; el botón «Pregunta por este
    mueble por WhatsApp» se destaca por tamaño y relleno, no por ser el único azul.
  - **Colores de más (todos explicables):** estrellas ámbar de Google `#F5B300` (excepción escrita en `dcasa.scss:2451-2452`); en el chat, verde
    `#17663A`, café `#8A3B05` y rojo `#A1260D` para estados; en el panel `--dc-bien`/`--dc-falta` y un globo rojo; y los íconos de la barra
    lateral del panel (imágenes propias de cada app) usan unos cinco o seis tonos (azul, violeta, verde, naranja, rojo; ver `4_inicio_computadora.png`).
  - **Grises de texto de sobra:** en la portada y la ficha conviven `#1B2233` (tinta), `#212529` (el negro por defecto de Bootstrap), `#4A5163`,
    `#5D5F60` y `#595C5F`: cinco grises oscuros donde la marca definió dos (tinta y gris).
  - **Panel (captura del 2 nov, no en vivo):** el Inicio en el celular son nueve tarjetas azules (`.o_dcasa_atajo`, `interfaz.scss:148-163`,
    `background: var(--dc-azul-600)`): **67 % de la primera pantalla es azul `#1340B1`**; en computadora, 16.7 % azul + 5.7 % navy y 52 % blanco.
- **Veredicto:** ✅ en el sitio público (tres colores, códigos fijos, acento escaso); 🟡 en las páginas claras (secundario y acento son el mismo
  azul) y en el Inicio del celular (el principal es el azul, no el neutro).
- **Qué haría:**
  - No forzar 60-30-10. Anotar el reparto real («80-15-1 en portada») en el documento de diseño. Costo cero.
  - Unificar los cinco grises de texto: fijar el color base de texto de Odoo/Bootstrap en tinta y los secundarios en gris, en
    `primary_variables.scss` (esfuerzo **poco-medio**; riesgo **medio** porque mueve levemente todas las páginas de Odoo y las imágenes de referencia de las pruebas visuales).
  - Inicio del celular: probar tarjetas claras (fondo `--dc-azul-50`, ícono azul, texto navy) y dejar el azul lleno para la acción principal.
    Esfuerzo **medio**; riesgo **medio** (la dueña aprobó este Inicio; hay que mostrarle capturas y regenerar las del modo oscuro).
  - Ficha: opcional, probar el precio y los datos secundarios en navy (13.44:1 sobre blanco, igual de permitido por la regla 1) para que el
    azul lleno quede solo en los botones. Esfuerzo poco; lo decide Gerencia: el titular y el precio en azul son parte de la firma visual.

### 3 · Color y fondo
- **La regla de Feuxui:** un color no tiene contraste por sí solo, depende de su fondo; decide el fondo primero; si falla, **cambia la luz,
  no el tono**; el color de acento debe tener una versión clara y otra oscura. Su ejemplo: el azul `#1417FB` da 7.0:1 sobre claro y 2.5:1 sobre oscuro.
- **D'CASA hoy:** ya lo resuelve, y mejor que el ejemplo:
  - **Sitio:** el azul va solo sobre claro (8.76:1 blanco, 8.04:1 hueso); sobre oscuro la marca usa **amarillo** (9.12:1 sobre navy, 5.94:1 sobre azul) y blanco
    (13.44:1 / 8.76:1). El azul sobre navy (1.53:1) nunca aparece. La regla 1 («el amarillo nunca toca el blanco») es exactamente esta lección
    escrita como ley: blanco sobre amarillo mide 1.47:1.
  - **Panel en modo oscuro** (`oscuro/tokens.dark.scss:20-36`): el azul de tinta se aclara a `#9DB8F5` (**6.90:1** sobre `#2A2E33`, 8.07:1
    sobre `#1F2226`) y el azul de relleno pasa a `#3A63CF` con texto blanco (5.43:1). Sin aclararlo, el azul de marca daría 1.56:1. Separan «azul
    como letra» de «azul como relleno»: más fino que lo que enseña Feuxui.
  - **Un hueco:** el fondo base del hero en carrusel es **hueso-2 claro** (`dcasa.scss:756`, `background: $dcasa-hueso-2`) y el texto es blanco.
    Mientras cargan las fotos, o si una conexión lenta no las trae, el texto blanco queda sobre beige claro con una niebla azul. Lo probé bloqueando
    las imágenes: subtítulo, mediana **3.48:1** (80 % de píxeles bajo 4.5:1); titular, mediana 4.02:1 (16 % bajo 3:1); captura
    `capturas_A/hero_sinfotos_1440_real.png`.
  - Estrellas de Google (ámbar `#F5B300` sobre blanco = 1.85:1): excepción acordada y escrita; la calificación también está en texto (5.0).
- **Veredicto:** ✅ cumple (con el hueco del hero sin fotos).
- **Qué haría:** cambiar el fondo base del hero a navy: `.o_dcasa_vitrina { background: $dcasa-navy; }` (`dcasa.scss:756`). Esfuerzo **poco**,
  riesgo **bajo** (solo se ve mientras la foto no ha cargado; la prueba `test_contrato_visual.py` mide el fondo de la sección, no el de esta capa).

### 4 · Temperatura de color
- **La regla de Feuxui:** cálidos adelante, fríos atrás; el protagonista (botón, producto, oferta) cálido sobre un fondo frío; una
  temperatura manda y la otra va de acento; los grises deben ir con esa temperatura.
- **D'CASA hoy:**
  - **Frío dominante + cálido de acento, tal cual la receta:** azul tono 223° y navy 222° (fríos) y amarillo 48° (cálido). En el hero, el botón
    «Ver el catálogo» (amarillo, cálido) va sobre la niebla azul (fría): el protagonista cálido sobre fondo frío (`capturas_A/portada_1440_arriba.png`).
    Las fotos aportan el calor (madera, lámparas) y el degradado azul enfría la mitad izquierda donde va el texto.
  - **Grises con la temperatura:** tinta y gris tienen tono 223° (azulados) ✅. Los grises por defecto de Odoo (`#212529` tono 210°, `#5D5F60`
    y `#595C5F` casi neutros, 3 % de saturación) no desentonan. El hueso `#F6F5F2` es casi neutro (tono 45°, 2 % de saturación): la dueña lo pidió así el 15 nov.
    El panel usa blancos fríos (`#F4F6FA`, tono 220°): por dentro es más frío que por fuera.
  - **En las páginas claras** el botón principal es azul lleno (frío) sobre blanco: no es cálido. Es lo que obliga la regla 1 (amarillo sobre blanco no se permite).
- **Veredicto:** ✅ en portada y bandas; 🟡 en ficha y categoría (protagonista frío sobre neutro), pero eso viene de la regla 1.
- **Qué haría:** nada obligatorio. Si Gerencia quiere un protagonista cálido en la ficha: una franja navy con el botón amarillo (el amarillo
  solo toca navy, así que cumple la regla 1). Esfuerzo **medio**, riesgo **medio** (no hay datos de conversión; habría que probarlo). Un botón
  amarillo sobre fondo claro sí **choca con la marca (regla 1)**: no se recomienda.

### 5 · Saturación
- **La regla de Feuxui:** un solo color a tope (el acento); la interfaz al 60-80 %; los fondos grandes al 20-40 %; bajar de a 10 % hasta
  que deje de gritar; bajar un poco la saturación de las fotos.
- **D'CASA hoy:**
  - La marca es muy saturada por diseño: azul `#1340B1` (saturación HSL 81 %), navy 77 %, amarillo 99 %.
  - **Las superficies grandes son calmadas:** blanco y hueso (2 % de saturación) ocupan el 80 % de la portada; el navy de las bandas es saturado
    pero oscuro y solo el 12.9 %. La dueña ya aplicó esta lección el 15 nov: pie de página en hueso porque «el azul puro en un bloque grande cansaba la vista»
    (`primary_variables.scss:18-21`, `dcasa.scss:9-12`).
  - **Acento escaso:** el amarillo, el color más saturado, es el 0.8 % del área.
  - **Fotos sin neón** (portada, fuera del hero, 2.4 millones de píxeles): saturación media **19.5 %** (mediana 5.8 %); solo el **0.71 %** de los píxeles pasa de 80 % de saturación con
    brillo alto. Las fotos de catálogo son de estudio, grises y calmadas ✅.
  - **Dos puntos donde sube:** (1) el hero lava la mitad izquierda de la foto de azul al 62 % (el píxel a la izquierda mide saturación 82 %), por diseño y es la
    «capa de color de marca» que Feuxui recomienda; (2) la píldora de la cabecera tiene `saturate(210%)` en su vidrio (`dcasa.scss:348`), pero el resultado visible es
    pálido (`#ABC2FB`, 32 % de saturación), así que no grita. (3) El Inicio del celular: nueve losas del azul de marca pleno (ver concepto 2).
- **Veredicto:** ✅ en el sitio público; 🟡 en el Inicio del celular del panel.
- **Qué haría:** no tocar el azul de la marca. Para reference, la escala de Feuxui aplicada a `#1340B1` (tono y luz fijos) daría 80 % → `#2347A1`,
  60 % → `#334E91`, 40 % → `#425482`: **cambiarlo choca con la marca (regla 1: el azul es el color madre)**, no lo recomiendo. Sí aliviar el Inicio del celular (concepto 2).

### 6 · Caída de luz
- **La regla de Feuxui:** la luz se desvanece, no se corta; degradados con cinco puntos (opacidad 100 / 60 / 25 / 8 / 0 a las posiciones 0 / 15 / 40 / 70 / 100 %); sombra en dos capas
  (contacto Y2 blur4 20 % + ambiente Y24 blur48 12 %); nunca negro puro; una sola fuente de luz.
- **D'CASA hoy:** la marca es plana a propósito, así que casi no usa caída de luz. Hay dos excepciones:
  - **El degradado del hero** (`dcasa.scss:771-776`): navy 90 % en 0 % → azul 62 % en 30 % → azul 18 % en 58 % → 0 en 80 %. Es una curva de
    «cae rápido y se estira al final», parecida a la receta de Feuxui, con colores de marca y **sin negro** (la prueba `test_contrato_visual.py:508-509` lo exige). En el celular
    sube desde abajo (92 / 55 / 0 %, `dcasa.scss:782-786`). No se ven bandas (ni siquiera en mi captura sin fotos, `hero_sinfotos_1440_real.png`).
  - **Las sombras de las capas flotantes** (ver concepto 7).
  - Las tarjetas de producto no tienen sombra: borde de 1 px `#E3E1DB` (`dcasa.scss:1163`).
- **Veredicto:** ⚠ choca con la marca (regla 3, «sin degradados»): el degradado existe porque la dueña lo eligió el 17 nov entre cinco opciones (`docs/LEEME_PRIMERO.md`, sesión del hero en carrusel)
  y una prueba lo exige, pero la regla escrita en `CLAUDE.md` sigue diciendo «sin degradados». Para todo lo demás, ➖ no aplica (la marca es plana).
- **Qué haría:** nada nuevo. **Decisión de Gerencia:** cambiar la regla 3 a «sin degradados decorativos; la única capa permitida es la azul de contraste sobre las fotos del hero»,
  para que lo escrito y lo real coincidan. Costo cero, riesgo ninguno.

### 7 · Sombras
- **La regla de Feuxui:** una sola fuente de luz y todas las sombras hacia el mismo lado; desenfoque de 2 a 3 veces la altura (Y); opacidad 10-25 %; **nunca negro puro** (usa un tono oscuro del fondo); tres niveles:
  baja (Y2 · blur6 · 12 %), media (Y8 · blur24 · 15 %), alta (Y24 · blur60 · 20 %); una sombra por elemento.
- **D'CASA hoy (sitio):** las tarjetas, botones y la ficha **no llevan sombra**. Solo la tienen las capas que flotan, todas con tinte navy `rgba(14, 42, 107, …)`, nunca negro:

  | Pieza | Sombra | Contra Feuxui |
  |---|---|---|
  | Panel del chat (`brian_tienda.scss:259`) | `0 8px 24px` · 16 % | casi el nivel «media» (Y8 · blur24 · 15 %) |
  | Flecha redonda del chat (`brian_tienda.scss:1143`, `.o_dcbt_flecha`) | `0 2px 6px` · 12 % | exactamente el nivel «baja» (Y2 · blur6 · 12 %) |
  | Aviso del chat (`:1590`, `.o_dcbt_aviso`) | `0 4px 12px` · 20 % | dentro del rango |
  | Burbuja del chat (`:123`) | anillo blanco + `0 6px 16px` · 26 % | un punto sobre el 25 % |
  | Hoja inferior del chat (`:1781`) | `0 -6px 18px` · 12 % | cae hacia arriba (va pegada al borde de abajo; es la única excepción a «todas hacia el mismo lado») |
  | Píldora de la cabecera (`dcasa.scss:355`) | `0 16px 40px -24px` · 55 % navy | recogida por el -24 de extensión; cae hacia abajo |
  | Píldora sobre foto (`dcasa.scss:526`) | `0 16px 40px -24px` · **negro 60 %** | la única de negro puro |

  Medido en vivo: ficha y categoría, 3 elementos con sombra (la píldora, su «gota» y la burbuja del chat); en la categoría, además, un `text-shadow` de 1.6 px en la página activa de la paginación (no lo ubiqué en el código propio); ninguna dramática.
- **D'CASA hoy (panel):** `--dc-sombra-1: 0 1px 2px` 5 % y `--dc-sombra-2: 0 8px 24px` 6 % (`tokens.scss:46-47`), tinte navy y siempre hacia abajo: más suaves que el rango de Feuxui, a propósito («sombras casi imperceptibles»).
  En modo oscuro son negras al 25-45 % (`oscuro/primary_variables.dark.scss:95-98`), normal en una interfaz oscura.
- **Veredicto:** ✅ cumple. Una dirección, tinte de marca, suaves, una por elemento; D'CASA ya usa los niveles de Feuxui sin conocerlos.
- **Qué haría:** cambiar el negro de `dcasa.scss:526` por `rgba($dcasa-navy, .55)` (la misma de la píldora clara). Esfuerzo **poco**, riesgo **mínimo** (casi invisible).
  Nada más.

### 8 · Overlays y capas
- **La regla de Feuxui:** foto abajo, capa en medio, texto arriba; texto claro con capa oscura; para degradado, de 0 a 70-80 % **solo donde va el texto**;
  un color de la marca vale más que un gris plano; mide el contraste **sobre la zona más clara de la foto** y apunta a 4.5:1; arréglalo sin cambiar la fuente.
- **D'CASA hoy:**
  - **Hero en carrusel:** el método es el correcto (capa de color de marca, solo en la zona del texto, sin cambiar la fuente, `dcasa.scss:771`), pero el **tamaño de la capa se queda corto** (números en el concepto 1).
    Con el degradado actual, el peor píxel del subtítulo es 2.13:1 (el del titular 2.37, el del antetítulo 2.69).
  - **Simulé tres capas sobre los mismos 20 fotogramas** (sin degradado, desde `crudo_1440`/`crudo_390`) y medí el peor píxel de cada texto:

    | Capa | Antetítulo (14 px) | Titular (104 px) | Subtítulo (20 px) | Resultado |
    |---|---|---|---|---|
    | **Actual** (navy .90 · azul .62 a 30 % · azul .18 a 58 % · 0 a 80 %) | 2.69 | 2.37 | 2.13 | ❌ bajo el mínimo |
    | **A** (navy .92 · navy .80 a 30 % · azul .55 a 55 % · 0 a 80 %) | 5.28 | 4.70 | 4.16 (1 % de píxeles bajo 4.5) | casi |
    | **B** (navy .88 · navy .78 a 40 % · azul 0 a 75 %) | 6.94 | 5.66 | **4.54** | ✅ todo pasa |
    | **C** velo plano de navy al 40 % sobre toda la foto | 2.46 | 2.33 | 2.35 | ❌ peor: no alcanza porque las fotos son claras |

    Lo que confirma lo que dice Feuxui: **un velo plano no arregla una foto clara; el degradado concentrado donde va el texto, sí**. En el celular (390 px), con el degradado actual el peor
    píxel es 2.09 (antetítulo), 2.47 (titular) y 4.26 (subtítulo); con navy .92 · navy .80 a 45 % · azul .45 a 70 % · azul 0 a 90 % pasan todos (4.94 · 6.24 · 8.73).
    Antes y después reales, con la capa puesta **solo en mi navegador**: `capturas_A/hero_1440_antes_despues_foto4.png`, `hero_1440_antes_despues_foto3.png` y
    `hero_390_antes_despues_foto3.png` (izquierda actual, derecha propuesta).
  - **Hero de páginas interiores** (Contacto, Socios): foto al 45 % sobre negro, es decir un velo negro plano del 55 %, el «sólida 40-60 %» de Feuxui: pasa en todos los píxeles (≥ 4.75:1).
  - **Etiquetas sobre fotos** («Recámaras», «Oficina» en «Date una vuelta»): pastilla navy con letra amarilla (9.12:1): sin depender de la foto ✅.
  - La capa nueva **quitó el halo** que el hero anterior sí tenía (`text-shadow` de `dcasa.scss:710`; medido: el hero en carrusel tiene `text-shadow: none`).
- **Veredicto:** 🟡 cumple a medias (método ✅, magnitud ❌ en subtítulo y antetítulo).
- **Qué haría:** en `dcasa.scss`:
  - computadora (líneas 771-776): `linear-gradient(118deg, rgba($dcasa-navy, .88) 0%, rgba($dcasa-navy, .78) 40%, rgba($dcasa-azul, 0) 75%)`;
  - celular (líneas 782-786): `linear-gradient(to top, rgba($dcasa-navy, .92) 0%, rgba($dcasa-navy, .80) 45%, rgba($dcasa-azul, .45) 70%, rgba($dcasa-azul, 0) 90%)`.
  Ambas siguen siendo azul de marca, sin negro (cumplen el contrato de la prueba). Oscurecen más la zona del texto (el 40 % izquierdo en computadora); la derecha queda igual. Esfuerzo **poco**; riesgo **medio**
  (aspecto: la dueña dijo «el fondo no lo quiero oscuro» y hay que enseñarle estas capturas; hay que regenerar las imágenes de referencia). Variante más suave: la **A** de la tabla (pasa el titular y el antetítulo, el subtítulo
  casi). Alternativa sin tocar el aspecto: que Gerencia escoja para el carrusel fotos con la parte izquierda calmada u oscura (en el panel: Sitio web › Carrusel de la portada).

### 9 · Ruido y grano
- **La regla de Feuxui:** una capa de ruido gris en modo Superposición: 0-2 % en texto e interfaz, 2-4 % en fondos lisos, 4-6 % en degradados (esconde las bandas), 6-8 % en fotos; pasado el 8 %, sucio.
- **D'CASA hoy:** no usa grano en ninguna parte (busqué en el sitio, la tienda, el chat, Mi cuenta, Socios y el panel). Lo único parecido es el `feTurbulence` del filtro de refracción de la cabecera
  (`layout_templates.xml:150`), que es un efecto de agua que se mueve, no una textura de grano. No hay fondos lisos ni degradados sin foto que muestren bandas: el único degradado va sobre foto (que lo esconde) y
  en mi captura sin fotos se ve continuo.
- **Veredicto:** ➖ no aplica. Si algún día se propusiera añadir textura, **choca con la marca (regla 3, sistema plano)**.
- **Qué haría:** nada.

### 10 · Efectos
- **La regla de Feuxui:** un efecto por diseño y con un motivo; «si apagarlo no te hace falta nada, sobraba»; brillo, borde, sombra y degradado juntos hacen que se vea barato; el efecto sí vale cuando separa (sombra),
  enfoca (desenfoque), indica «en vivo» (brillo) o texturiza (grano).
- **D'CASA hoy:**
  - **El resto del sitio es limpio:** tarjetas con borde fino, botones planos, nada de brillos ni bordes dobles ✅. Las sombras del chat separan lo flotante (efecto con motivo).
  - **La cabecera de «vidrio líquido» apila unos ocho efectos en una sola pieza:** desenfoque 16 px (`dcasa.scss:347-349`) + saturación 210 % + brillo 1.08 + filtro SVG de refracción que se mueve
    (`feTurbulence` + `feDisplacementMap` con escala 38, `layout_templates.xml:149-152`, `animaciones.js:117-175`: «mover el ruido repinta la píldora en cada cuadro») + tres filos de luz interiores + sombra exterior (`dcasa.scss:347-356`) + un
    reflejo que cruza al pasar el puntero (`:369-376`) + una «gota» de vidrio con rebote (`:481-482`, curva `cubic-bezier(.34, 1.56, .64, 1)`) + encoge a 97 % al bajar (`:435`).
  - **En la primera pantalla del hero se suman:** zoom lento y continuo (de 1.06 a 1.16 con deriva de ±1.2 %, en ciclos de 18 s) + fundido entre 7 fotos + el degradado.
  - Hecho bien: respeta «reducir movimiento» (`dcasa.scss:588`, `:2794`, `portada.js:16`: sin movimiento el hero no cambia de foto ni hace zoom) y tiene botones de pausa en las cintas.
  - No medí el costo de rendimiento (el filtro de refracción y el desenfoque trabajan en cada cuadro; en celulares sencillos podría notarse): no tengo cómo medirlo desde aquí.
- **Veredicto:** 🟡 cumple a medias · ⚠ choca con la marca (regla 3, «sistema plano»): la cabecera de vidrio y el zoom son decisiones de la dueña (`docs/historico/REDISENO.md:147-157`, «inspirada en BYS y Safetory»; «la píldora es una sola en todo el sitio»).
- **Qué haría:** no quitar nada sin ella. Proponerle la «prueba de quitar» sobre la cabecera: apagar (a) la refracción animada y (b) el reflejo al pasar el puntero, que son lo menos visible. Esfuerzo **poco**,
  riesgo **bajo** (se pierde un matiz; ahorra trabajo del dispositivo). Primero capturas; decide Gerencia.

### 11 · Ojo de diseñador
- **La regla de Feuxui:** no preguntes «me gusta», pregunta «por qué funciona»: cinco preguntas (¿qué miro primero?, ¿cuántos colores?, ¿cuántas fuentes y pesos?, ¿dónde está el espacio vacío?, ¿qué se alinea con qué?);
  guarda tres referentes al día; copia el principio, no la imagen.
- **D'CASA hoy:** ya lo hace, por escrito. `docs/historico/REDISENO.md:20-27` trae la tabla «Qué tomamos de las referencias»: Case (aire, fondo cálido casi blanco, fotos a sangre), Burrow (hero con promesa
  y un solo CTA, fila de beneficios) y West Elm (ritmo editorial), cada una con «qué hace bien» y «cómo lo aplicamos»: es «ver, notar, entender, probar» con otro nombre. La cabecera de vidrio cita BYS y Safetory
  (`dcasa.scss:299`); el contraste del hero se decidió mostrando cinco opciones; el chat salió de un prototipo aprobado.
  Lo que falta: las cinco preguntas con cifras (cuántos colores, cuántas fuentes) y un lugar para guardar referentes nuevos (no lo encontré en el repositorio; puede existir fuera).
- **Veredicto:** ✅ cumple.
- **Qué haría:** añadir al documento de diseño una plantilla de cinco preguntas para analizar cada referente y usarla en el próximo cambio (por ejemplo el hero). Esfuerzo **poco** (media página), riesgo ninguno.

### 12 · Principio KISS
- **La regla de Feuxui:** corto y simple; máximo **2 fuentes y 3 colores** con un solo acento; un mensaje por pieza que se entienda en 3 s; quita sombras, marcos, estrellas y degradados que no ayuden; «antes de agregar algo, pregunta qué pasa si lo quitas».
- **D'CASA hoy:**
  - **Colores:** tres más neutros ✅ (concepto 2).
  - **Fuentes:** tres familias, Anton, Oswald e Inter (`primary_variables.scss:28-40`), una más que el máximo de Feuxui. Son la regla 2 de la marca.
  - **Mensaje:** el titular «Tu casa, bien amueblada.» son cuatro palabras y se entiende de inmediato ✅. El resto de la portada es ordenado: doce secciones que alternan hueso y blanco, un titular y una idea por sección,
    sin marcos ni adornos.
  - **Sobras en la primera pantalla** (conteo a ojo sobre la captura): unos 16 elementos en computadora (3 avisos arriba, la píldora con 7 piezas, antetítulo, titular, subtítulo, 2 botones, la burbuja del chat) y 12 en
    celular. **«Entregas en Panamá Oeste, Panamá y Colón» sale dos veces** (barra de arriba y antetítulo del hero, `homepage_templates.xml:149`) y el pedido por WhatsApp sale dos veces (barra y botón de contorno), además de la burbuja de Andrés.
    En el celular ese antetítulo ocupa dos renglones de 14 px en mayúsculas sobre la foto, y es el texto con peor contraste (concepto 1).
  - La portada mide 7 514 px en computadora y 9 280 px en celular; hay cuatro cosas que se mueven solas (hero, cinta «Date una vuelta», cinta de opiniones y los carriles). Las dos cintas tienen botón de pausa.
- **Veredicto:** 🟡 cumple a medias.
- **Qué haría:** dejar el antetítulo del hero en «Mueblería en La Chorrera» (la entrega ya está en la barra de arriba y en la franja de beneficios). Cabe en un renglón, quita un elemento repetido y arregla el peor contraste del celular. Esfuerzo **poco**
  (`homepage_templates.xml:149`; es un texto, no inventa nada), riesgo **bajo**. Las tres fuentes no se tocan: **choca con la marca (regla 2)**.

### 13 · Rompe las reglas
- **La regla de Feuxui:** domina la regla, rompe **una sola**, exagérala para que se note y ten un motivo que puedas decir en una frase; la diferencia entre error y decisión es la intención.
- **D'CASA hoy:**
  - **Lo que hace muy bien:** las reglas de marca están escritas (`CLAUDE.md`) y vigiladas por pruebas (`test_contrato_visual.py`), y **cada ruptura lleva su motivo y su fecha**: las estrellas ámbar
    («una estrella azul no se lee como calificación. Excepción acordada a la regla del amarillo», `dcasa.scss:2451`), el degradado azul del hero (elegido por la dueña entre cinco opciones el 17 nov) y la cabecera de vidrio
    («corrección de la dueña: la píldora es una sola en todo el sitio»). Eso es romper a propósito.
  - **Dónde se rompió sin querer** (error, no decisión): los pasos del carrito (el arreglo de color quedó anulado por la opacidad: 2.38:1), los placeholders de Odoo y el contraste del hero nuevo, que nadie midió en píxeles.
  - **«Rompe solo una»:** la primera pantalla de la portada junta cuatro rupturas a la vez (degradado + vidrio líquido con refracción + zoom continuo + texto sin placa sobre foto). Feuxui pide una y todo lo demás en orden; el resto del sitio sí está en orden (plano, ordenado), así que el efecto es de una portada «más intensa» que el resto.
  - **Lo escrito y lo real se separaron:** `CLAUDE.md` regla 3 dice «sin degradados ni sombras dramáticas»; la práctica tiene dos excepciones aprobadas.
- **Veredicto:** ✅ cumple (excepciones con motivo y vigiladas), con 🟡 por la acumulación de rupturas en el hero.
- **Qué haría:** pasar a `CLAUDE.md` una lista corta de «excepciones aprobadas» con su motivo y fecha (estrellas ámbar, capa azul del hero, cabecera de vidrio), y reformular la regla 3 en consecuencia. Esfuerzo **poco**, riesgo ninguno. Y,
  al tocar el hero, no sumar otra ruptura.

---

## Lo más importante (las 8 mejoras de mayor efecto y menor costo, en orden)

1. **Subir la capa azul del hero donde va el texto** (`dcasa.scss:771-776` y `782-786`; valores en el concepto 8). El peor píxel del subtítulo pasa de 2.13 a 4.54:1 y el del antetítulo del celular de 2.09 a 4.94:1. Poco esfuerzo; riesgo medio de aspecto: mostrar capturas antes (hay un antes/después listo).
2. **Fondo base del hero en navy** en vez de hueso-2 (`dcasa.scss:756`): sin fotos, el subtítulo pasaba de 3.48:1 a leerse sobre azul oscuro. Poco esfuerzo, riesgo bajo.
3. **Placeholders con el gris de la marca** (`::placeholder`): de 2.86 y 3.12:1 a 7.27:1 en la búsqueda del catálogo y el celular de Socios. Poco esfuerzo, riesgo bajo.
4. **Pasos del carrito legibles:** `opacity: 1` junto a `dcasa.scss:2006`: de 2.38 a 7.93:1. Poco esfuerzo, riesgo bajo.
5. **Antetítulo del hero más corto** («Mueblería en La Chorrera», `homepage_templates.xml:149`): quita una repetición y el texto con peor contraste del celular. Poco esfuerzo, riesgo bajo.
6. **`--dc-tinta-3` del panel y del chat a `#5F6A84`** (`tokens.scss:32`, `brian_tienda.scss:15`): sobre niebla de 4.20 a 5.00:1, sobre azul-100 de 3.84 a 4.56:1. Poco esfuerzo, riesgo bajo.
7. **Una prueba automática de contraste en píxeles para el hero en carrusel** (peor píxel con cada foto, no mediana; 4.5:1 en texto normal, 3:1 en titular): hoy esa prueba solo existe para el hero antiguo. Esfuerzo medio, riesgo ninguno.
8. **Poner por escrito** las excepciones aprobadas (regla 3 de `CLAUDE.md`), el reparto real de color (80-15-1) y una plantilla de cinco preguntas para analizar referentes. Esfuerzo poco, riesgo ninguno.

## Lo que choca con la marca (para que decida Gerencia)

- **Degradado en el hero (regla 3, «sin degradados»):** Feuxui lo recomienda (capa de color de marca solo donde va el texto) y la dueña ya lo aprobó el 17 nov, pero la regla escrita no lo dice. Decidir: reformular la regla 3 (recomendado) o volver al velo plano, que según mi simulación **no alcanza** con estas fotos (un velo navy plano del 40 % deja el peor píxel en 2.3-2.5:1).
- **Oscurecer más la zona del texto del hero** (mejora 1): arregla el contraste, pero la dueña pidió «el fondo no lo quiero oscuro». Decidir con capturas.
- **Cabecera de vidrio líquido y zoom del hero (regla 3, «sistema plano»; Feuxui: un efecto por diseño):** son decisiones de la dueña. Propuesta: la «prueba de quitar» solo a la refracción animada y al reflejo.
- **Tres tipografías (regla 2; Feuxui: máximo 2):** es la identidad de marca; no recomiendo cambiar.
- **Bajar la saturación del azul o del navy (Feuxui, saturación) y un botón cálido/amarillo sobre fondo claro (Feuxui, temperatura):** chocan con la regla 1 (el azul es el color madre; el amarillo nunca toca el blanco). No los recomiendo.
- **Grano o textura (Feuxui, ruido y grano):** choca con la regla 3 (plano) y no arregla ningún problema que D'CASA tenga. No lo adoptaría.
- **Estrellas ámbar de Google `#F5B300` sobre blanco (1.85:1):** ya es una excepción acordada a la regla 1; solo conviene seguir dejándola escrita.

## Lo que D'CASA ya hace mejor o igual que Feuxui

- **Mide, no adivina, y lo deja escrito.** Los ratios están en el código (`dcasa.scss:17`, `:408` «SW-07: 4.33:1 / 3.27:1») y en auditorías (`docs/auditoria/ronda6/diseno.md`): Feuxui solo dice «usa un verificador».
- **Texto sobre fondos lisos:** el más bajo mide 5.18:1 y todo lo principal entre 7.27 y 15.87:1, muy por encima del 4.5 que pide Feuxui.
- **Color en modo oscuro, mejor que el ejemplo de Feuxui:** el panel separa el azul de letra (`#9DB8F5`, 6.90-8.07:1) del azul de relleno (`#3A63CF` con blanco, 5.43:1); sin aclarar daría 1.56:1.
- **Sombras:** las del chat coinciden con los niveles de Feuxui (Y2 · blur6 · 12 % y Y8 · blur24 · 16 %), con tinte navy y no negro; las tarjetas usan un borde fino en vez de sombra.
- **Acento escaso:** el amarillo es el 0.8 % del área y siempre cae sobre azul o navy. La regla 1 está respaldada por el número (blanco sobre amarillo = 1.47:1).
- **Superficies grandes calmadas:** blanco y hueso casi neutro (2 % de saturación) y el pie de página en hueso, pedido por la dueña porque el azul puro «cansaba la vista»; fotos sin neón (0.71 % de píxeles muy saturados).
- **Páginas interiores (Contacto, Socios):** velo negro plano al 55 %, ≥ 4.75:1 en cada píxel medido.
- **Excepciones con motivo y vigiladas por pruebas** (estrellas ámbar, capa azul del hero): es la «regla rota a propósito» de Feuxui.
- **Referentes analizados por escrito** (Case, Burrow, West Elm: qué hace bien y cómo se aplica).
- **Accesibilidad que Feuxui no menciona:** respeta «reducir movimiento», botones de pausa en las cintas, foco visible de 3 px en toda la cabecera.

## Lo que no pude medir o conviene saber

- **Rendimiento** de la cabecera de vidrio y del zoom: no medible desde aquí.
- **Panel en vivo:** no tengo acceso; usé el código y la captura del Inicio del 2 de noviembre.
- **Hero:** 20 fotogramas durante 34 s cubren las 7 fotos, pero con el orden al azar que usa el sitio; otro orden o otras fotos cambian los porcentajes. Los números de «peor píxel» son sensibles a un solo píxel; usar también la mediana y el porcentaje bajo el mínimo.
- **Falsos positivos de mi medición automática:** en Contacto y Socios, el menú blanco sobre el vidrio ahumado se calculó como «1:1»; es una limitación del método (el vidrio y la foto no están en el HTML). Con la captura se ve claro (≈ 10:1, estimación por percentiles).
- **Cobertura:** una sola ficha (Cama King Black 2806) y una sola categoría (Recámaras); Black Weekend y las pantallas de Mi cuenta no se cargaron; el reparto de color de la ficha se midió solo a 1440 px.
- **Cargas a producción:** 26 en total (1 s de pausa), todas GET.

## Archivos

- Capturas: `$S/feux/capturas_A/` (`portada_*`, `ficha_*`, `categoria_*`, `carrito_*`, `contacto_*` a 1440 y 390; `hero_*_antes_despues_*`, `hero_*_fondo_marcado`, `hero_sinfotos_1440_real`).
- Scripts y resultados: `$S/feux/scripts_A/` (`lib_contraste.cjs`, `rerun.cjs`, `analiza_hero.py`, `simula_velo.py`, `clasifica.py`, `colores.cjs`, `antes_despues.cjs`, `r2_*.json`, `hero_*_res.json`).
