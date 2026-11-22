# Bitácora anterior (entradas viejas de LEEME_PRIMERO)

> **Archivado el 2026-11-06, el 2026-11-11, el 2026-11-13, el 2026-11-14, el 2026-11-16, el 2026-11-17, el 2026-11-20 y el 2026-11-22.** Texto completo de las entradas de la bitácora de
> [LEEME_PRIMERO.md](../LEEME_PRIMERO.md) del 2026-10-16 al 2026-11-17, la más nueva arriba. Allí quedan resumidas en una línea
> cada una. Se conservan tal cual (con los nombres de personas quitados), como registro.

### 2026-11-17 (2): la portada nueva en producción (CI/CD 377), el hero como fondo en movimiento

**En producción: la portada nueva** (ejecución 377 de CI/CD a mano desde `main`, squash `447d6efe`, PR #127; Juan
sigue en 28). El resto de la segunda entrega —Andrés vendedor, notas de voz y micrófono— **sigue sin subir**, a la
espera de la decisión de la dueña sobre Socios y el envío gratis.

- **Lo que pidió la dueña:** «como si fuese un video corrido… imágenes con un tipo suave zoom», «no quiero ni
  siquiera que el usuario tenga control», «ni siquiera tiene que tener el nombre del producto» y, sobre el
  contraste, «el fondo no lo quiero oscuro». Se le mostraron **cinco opciones** de contraste en azul de marca, en
  computadora y en celular; eligió la quinta («me gusta mucho la última imagen y cómo se ve en celular»).
- **Qué quedó:** el hero dejó de ser un carrusel con mandos y pasó a ser un fondo. Las fotos de los productos que
  Gerencia elige en Sitio web › Carrusel de la portada cubren la pantalla entera, se funden unas en otras en orden al
  azar y llevan un zoom lento que no para. Encima va solo el texto de siempre: sin nombres, sin enlaces, sin flechas,
  sin barras y sin pausa. Sin productos elegidos queda el hero de antes, igual que antes.
- **El contraste se resuelve en azul de marca, nunca oscureciendo la foto:** un degradado diagonal (navy → azul →
  transparente) en `::after`, sin bordes ni franjas; en el celular va de abajo hacia arriba. El amarillo sigue
  cayendo siempre sobre azul.
- **Accesibilidad:** el fondo es decorativo (`aria-hidden`, `alt` vacío), así que el lector de pantalla lee el texto y
  no una lista de camas; con «movimiento reducido» no cambia de foto ni hace zoom. La primera foto sigue siendo la
  imagen LCP.
- **El contrato visual ahora exige dos cosas más** que antes no se miraban: que la **foto misma** cubra el hero de
  orilla a orilla, y que la capa de contraste sea de marca y **nunca negra**. Referencias regeneradas en el mismo
  commit.
- **Rama aparte, como con el Black Friday:** `claude/portada-solo`, sacada de `main`, 21 archivos, todos dentro de
  `addons/website_dcasa/`. No toca Socios, ni el chat, ni nada que mueva dinero. Así la portada pudo subir hoy sin
  arrastrar la segunda entrega.
- **Comprobado en producción** (en computadora y en celular, con el navegador de verdad): hero a pantalla completa,
  7 fotos, la foto cubre el hero, el zoom corriendo, la capa en navy y azul **sin nada de negro**, cero mandos y
  `aria-hidden` puesto. Salud del borde sana: `{"ok": true, "version": "447d6efe6c74", "base_al_dia": true,
  "humo": "ok"}`.
- **Pendiente anotado:** el contrato visual del panel de Juan falla a 390 px (`panel-lista-390` 7,7 % y
  `panel-conexiones-390` 13,7 % de píxeles distintos). **Viene de `main`, no de la portada** (esta rama no toca nada
  de Juan). Hay que mirarlo aparte: o es un cambio a propósito al que le faltó regenerar sus referencias, o es una
  falla de verdad en el celular.

### 2026-11-17: la pantalla «Armar combo», tres arreglos de Socios y del chat, y los parches de IA de Juan

**Nada nuevo en producción** (sigue Desplegar 77 y Juan 28). Todo en la rama de trabajo, a la espera de la decisión
de la dueña sobre Socios y el envío gratis (ver [PRIORIDADES.md](PRIORIDADES.md)).

- **«Armar combo»** (lo que pidió la dueña después del Black Friday): su columna «precio» salía sin la campaña, así
  que durante una oferta le mostraba a la vendedora un precio que ese día no se practicaba —la web decía otro— y un
  ahorro que no existía. Ahora «precio» es lo que la pieza cuesta SUELTA ESE DÍA y «precio_linea» lo que se cobra en
  el combo. 238 pruebas en verde.
- **El total negativo en el mostrador:** la guarda «el premio no pasa del carrito» vivía solo en la tienda web. Pasó
  a `_aplicar_en_venta` (por donde van los dos caminos) y `action_confirm` quedó con una última red.
- **La guardia del Worker:** se saltaba con una oración que terminara en «?» sin «¿» («ya te lo quité…, ok?») y con
  una pregunta en medio. Ahora se quitan las cláusulas interrogativas enteras y se revisa todo lo demás.
- **El premio de Socios ya no viaja al chat entre los productos:** le contaba al modelo que el visitante es socio y
  tiene un premio puesto, Andrés podía proponer quitarlo (eso cancela el canje) y reaccionaba ofreciendo «algo más
  económico» por el premio del propio cliente. Va en «extras», con el envío.
- **PR de Dependabot #98 unido a main** (parches de `@ai-sdk/*` y `ai` en `juan/`), con el CI completo en verde y
  revisado que los cambios de comportamiento del registro tocan APIs que Juan no usa. Juan: 1924 pruebas en verde con
  las librerías nuevas. **No cambia producción hasta el próximo «Desplegar Juan».**

### 2026-11-16 (3): el Black Friday en producción (Desplegar 77 y Juan 28)

**Nada nuevo en producción todavía** (sigue Desplegar 76). La sesión tomó el traspaso y cerró el **paso 0**.

- **Los dos puntos por verificar del traspaso estaban bien**: un colchón cuyo precio en combo ya no es menor no le
  quita la campaña a la cama, y el interruptor se lee de la campaña en `_get_applicable_rules_domain` sin reescribir
  reglas ni regenerar la tienda.
- **Dos revisiones adversariales independientes** (toca dinero). La primera encontró 1 bloqueante y 14 hallazgos más;
  la segunda, hecha sobre el arreglo de la primera, encontró que ese arreglo **se quedaba corto** y 2 bloqueantes
  más. Todo lo de dinero está arreglado y probado; lo de rendimiento quedó anotado.
- **Decisión de la dueña (la regla del par):** se compara el total del par. Si el combo (cama a precio normal y
  colchón a precio en combo) sale igual o más barato que comprar las dos piezas sueltas con su precio de Black
  Friday, el combo se queda; si sale más caro, el combo se deshace y cada pieza va a su precio de oferta. «Comprar
  juntos nunca puede salir más caro que comprar por separado.»
- **Rama de la subida: `claude/black-friday-solo`** (sale de `62868d5`, que ya trae el nombre «Andrés» de `1937f89`).
  Solo Black Friday: ni Andrés vendedor, ni voz, ni micrófono, ni portada. **Batería del paso 0: 1543 pruebas, 0
  fallas.**
- **En producción: Desplegar 77** (PR #126, squash `a904ec65`, `app_version` `26b357d3bd51…`, imagen
  `sha256:ebc046c9…`, CI 371 con staging) y **Juan 28** (Juan primero, porque el nombre «Andrés» vive en
  `juan/src/tienda`). Con respaldo previo. Comprobado en producción: `/dcasa/salud` sano con la versión nueva, la
  portada responde, `/promociones` da 404 y el menú no lo muestra (todavía no hay campaña), y el chat abre diciendo
  **«Hola, soy Andrés»**.
- **Susto del camino:** el servidor de GitHub de la sesión estuvo una hora contestando «invalid session» justo
  después de reconectar la cuenta. `git push` seguía funcionando. Volvió solo al reiniciarse el proceso de la
  sesión; está anotado en CONTEXTO_AGENTICO.
- En la rama de trabajo quedó además el último pendiente de las notas de voz (el micrófono que quedaba encendido si
  la pantalla se cerraba mientras pedía permiso) y las dos pruebas del carrusel arregladas.
- **La segunda entrega NO subió** (Andrés vendedor, voz, micrófono y portada): su revisión adversarial independiente
  encontró un **bloqueante que necesita decisión de la dueña** (ver PRIORIDADES).

### 2026-11-16 (2): todo el plan Andrés, voz y portada subido a la rama, incluso lo que quedó a medias (traspaso a otra cuenta)

**Nada nuevo en producción** (sigue Desplegar 76). La sesión trabajó el plan con ayudantes en paralelo, cada uno en su
rama local: combos inamovibles, Andrés vendedor (A1–A5), notas de voz, micrófono en el chat y la portada en carrusel a
pantalla completa sin fondo negro (lo pidió la dueña al ver las capturas). Hubo tres revisiones adversariales: Andrés
quedó arreglado; combos y voz quedaron con los arreglos a medias. Todos los ayudantes se cortaron por el límite de uso
de 5 horas y la dueña pidió: «sube incluso lo incompleto con el avance actual y lo que falta». Las cinco ramas se
unieron sin conflictos en `claude/merge-rama-to-main-ty3koz`. Sobre la unión pasan ruff y las 1921 pruebas y el
typecheck del Worker; **las de Odoo no se corrieron**. Qué falta en cada parte, con sus commits: **[PLAN_ANDRES_VOZ_PORTADA.md
› Traspaso del 2026-11-16](PLAN_ANDRES_VOZ_PORTADA.md#traspaso-del-2026-11-16-madrugada-dónde-quedó-cada-parte)**.
Lección: con varios ayudantes a la vez, el límite de 5 horas llega para todos juntos; subir a la rama de trabajo
cada avance que pase las pruebas rápidas, no al final.

### 2026-11-16: Black Friday y «Andrés» listos en la rama sin subir (pausa por límite de uso); plan de la ronda siguiente

**Nada nuevo en producción** (sigue Desplegar 76, `754aceaf18e7`). La sesión se pausó por el límite de uso de la cuenta, a
pedido de la dueña: «sube la rama lo que tengas y añade todo lo que avanzamos para que otro Claude finalice».

- **Listo en la rama:** el código está en `cae5e57`.
  - **Campaña del sitio:** Black Friday desde el panel, con pruebas en `website_dcasa/tests/test_campana.py` y
    `dcasa_conversaciones/tests/test_precio_campana.py`.
  - **Revisión adversarial:** tres vueltas, sin bloqueantes. Se arreglaron:
    - permisos: solo Gerencia y los que cambian precios;
    - solo las tarifas del sitio, sin pisar las reglas propias;
    - el piso de variantes;
    - los disparos exactos del cron;
    - la revisión de los carritos viejos y en el pago;
    - el bloqueo de `date_order`;
    - las reglas que se guardan 30 días;
    - los combos;
    - la huella del catálogo de Meta.
  - **«Andrés»:** el chat de la tienda tiene nombre nuevo, en Odoo y en `juan/src/tienda`.
- **La dueña ya autorizó la subida** («lleva ya todo a producción»). Falta:
  - repetir las pruebas locales con el código final: la vuelta con `11f9822` dio 827 de 827 en verde;
  - CI con staging, PR, squash, Desplegar y **Desplegar Juan**;
  - explicarle los pasos del panel.

  Todo eso está en el **paso 0** de [PLAN_ANDRES_VOZ_PORTADA.md](PLAN_ANDRES_VOZ_PORTADA.md). El Black Friday es el
  viernes 27: hay que subirlo con días de margen.
- **Pedidos nuevos (2026-11-16, con capturas del chat):** quedan como plan, en el mismo documento.
  - Andrés como buen vendedor:
    - el carrito y la cotización no se pierden al subir en el chat;
    - ofrece sumar el envío a la cotización;
    - reacciona una vez cuando el cliente quita o vacía el carrito;
    - cambia cantidades conversando;
    - la vitrina va ordenada por pedido.
  - Notas de voz para Andrés y Brian, sin guardar el audio, para que nadie pueda clonar voces.
  - El hero en carrusel con camas propias («805, 801 y la negra 300-300»: confirmarlas con fotos).
  - Una sección «de cine» tipo panaclaw.com/proyectos con un botón al catálogo.
- **Preguntas abiertas a la dueña:**
  - **I6.** ¿El precio de campaña vale también en la tienda física, o solo en la web? Hoy vale en todos lados.
  - **Ya contestó, y es una regla:** «no quiero tocar en absoluto los combos. Los combos son inamovibles aunque
    hayan estrategias o ofertas… debería poderse, pero no quiero». Una campaña nunca rebaja un combo armado. Hay que
    programarlo antes de subir (paso 1 del plan) y dejar un interruptor apagado.
  - **Ya contestó:** «los combos son intocables. Esa es una promoción permanente de la empresa». La línea «Combo con
    colchón $X» vuelve a salir con precio de campaña, en la página, con Juan y con Andrés.
- **Esta máquina:** se reinició cuatro veces entre el 15 y el 16. Lo que no está en la rama se pierde.

### 2026-11-15 (3): bandas en azul noche y pie claro, menú sin «Escríbenos», contacto y el carrito en el chat, en producción (Desplegar 76); Black Friday y «Andrés» en la rama

**En producción desde el 2026-11-15, ~19:55 UTC (salud sana: `{"ok": true, "version": "754aceaf18e7", "base_al_dia": true, "humo": "ok"}`):** **Desplegar 76** (run 43754485392) con la imagen `sha256:1cfb8e4f226604186ee8298d4c37dd5651a248f96c94119db3ee820b8b033207` y `app_version` `754aceaf18e7ed66ef1e69ec59a2ab5351a80574` (PR #122, squash `b012494`; CI 365 con staging, run 43732155027), con respaldo previo. Juan no cambió. **Es lo último en producción.** Comprobado en dcasapty.com a 1440 y 390 px: sin «Escríbenos» en el menú, con la sección de contacto, pie #F6F5F2, avisos y Socios en azul noche, el número de /visitanos a WhatsApp; sin errores en la consola.

- **Aprobación de la dueña (tal cual, en corto):** «apruebo todo excepto el color amarillo en el carrito de compra…
  prefiero dejarlo como está» y «avísame cuando esté en producción». Hoja: <https://claude.ai/artifact/V2J95Wg3zJfPyrkoachd2L>.
- **Qué lleva:** paleta «composición 3» con el pie en el blanco grisáceo de la portada (no los cremas: «esos huesos no
  me agradan»); menú sin «Escríbenos» y sección «¿Te quedó alguna duda?» (WhatsApp y correo) antes de Visítanos;
  el número de /visitanos abre WhatsApp; el chat de la tienda con el carrito en su barra (al día con la página),
  sugerencias del catálogo y «Lo más buscado» en la vitrina vacía.
- **Color de la cantidad del carrito:** pidió investigación «para que mis gustos no me nublen». Recomendé amarilla
  con aro azul (sobre la foto de la portada la azul mide 1.2–1.4:1); **decidió dejarla azul**. Todo en
  [COLOR_CANTIDAD_CARRITO.md](COLOR_CANTIDAD_CARRITO.md): no se vuelve a proponer sin un dato nuevo.
- **En la rama, sin probar ni subir (commits `5648d0d` y `2893b8f`):**
  - **Campaña del sitio (Black Friday, viernes 27 de noviembre):** Sitio web › Campaña del sitio (nombre, fechas,
    frase), la casilla «En la campaña» con un precio de campaña opcional (regla de tarifa con las mismas fechas, el
    normal tachado), «Aplicar un descuento», «Empezar de cero» (aprobado por ella), /promociones y «Promociones»
    sencilla en el menú. Capturas: <https://claude.ai/artifact/GxqG2zGJZ949owo6Pbqwgn>. **Hallazgo:** el sitio no
    usaba la tarifa con el visitante (la página mostraba el precio sin tarifa y el carrito sí la usaba); la campaña
    deja la tarifa «Default» ofrecida al sitio. Juan y Andrés dicen el precio de campaña mientras rige.
  - **El chat de la tienda se llama Andrés** (pedido de la dueña: «que brian sea el del panel de administración»).
    Cambian los textos visibles, el motor del Worker (`juan/src/tienda`) y la Guía; los nombres técnicos se quedan.
    Necesita **Desplegar Juan** además de Odoo.
- **Sigue:** su respuesta sobre la línea «Combo con colchón» en campaña; las pruebas nuevas de la campaña y la
  revisión adversarial (toca precios); capturas de Andrés; luego CI con staging, producción y Desplegar Juan, con
  días de margen antes del 27.
- **Esta máquina:** se reinició dos veces en la tarde (PostgreSQL queda abajo: `pg_ctlcluster 16 main start`). El
  trabajo sin subir de Black Friday vivía en una copia aparte del scratchpad; se pasó a la rama apenas terminó el squash.

### 2026-11-15 (2): portada v3 (paleta, espaciado, categorías y carriles en una fila, carrito como ícono, chat de vidrio), en producción (Desplegar 75)

**En producción desde el 2026-11-15, 08:3x UTC (salud sana: `{"ok": true, "version": "6c7fdc425be3", "base_al_dia": true, "humo": "ok"}`):** **Desplegar 75** (run 43693725820) con la imagen `sha256:84085a134a139c75cf76db42220b342d958691334551d43fb33dea637eba0065` y `app_version` `6c7fdc425be329adb00180abfc5a20347bf2ff0f` (PR #121, squash `6221175`; CI 363 con staging, run 43689911281), con respaldo previo. Juan no cambió (sin Desplegar Juan). **Es lo último en producción.** Comprobado en dcasapty.com a 1440 y 390 px: categorías con los conteos reales (Salas 2, Recámaras 121, Colchones 7, Zapateras 28, Estantes 70, Oficina 6), carriles en una fila con flechas y línea de avance, carrito redondo de 48 px (barra en el celular), «Agotado» en una zapatera de «Lo más buscado» que de verdad está en 0; sin errores en la consola.

- **Aprobación de la dueña (tal cual):** con las capturas y el chat ampliado de vidrio a la vista: «Perfecto, me encanta
  eso… mándalo a las pruebas, mándalo a staging y a producción… apruebo todo, despliégalo todo cuanto antes».
- **Lo que encontraron las pruebas locales antes del CI** (5 de 591, dos corridas): el antetítulo más chico tocaba la
  foto grande de la portada (contrato visual del hero a 390 px, 1,99 %): ahora solo en la cabecera de las secciones; el
  carrito salía de 44 × 48 porque `.o_dcasa_home .btn` pide 48 px mínimo: ahora 48 × 48; dos pruebas al día («Elegir» ya
  no es texto; el color de los íconos del chat se mide sin foco y después de su transición). CI 361 y 362 cancelados para
  meter esos arreglos.

- **Pedido de la dueña (tal cual, en corto):** «¿Qué le hace falta a tu casa?» y «Lo más buscado» «se salen una página
  entera»; mirar cómo reparte el espacio jamar.com.pa; «si ve un carrito, entiende que es añadir al carrito… que el texto no
  sea tan grande, que quepa más»; mejorar la paleta; la barra azul del chat «del mismo material que el navbar… los iconos
  negros… el robotcito tal cual»; y después: «no quiero copiar a Jamar… superarlos con creces… sofisticado, moderno… con
  sentido de necesidad y urgencia… respetando el branding». **Pidió capturas antes de cualquier prueba o subida.**
- **Qué lleva:** `website_dcasa` (paleta v3: hueso #F6F5F2 en vez del beige #F4F1EA, titulares
  de 56 a 40 px, secciones de 120 a 72 px; categorías 6 en fila / 3×2 con el nombre y «N productos» debajo
  (`_dcasa_categoria_cantidad`); carriles de la portada en una fila deslizable con flechas y línea de avance, `carril.js`;
  tarjeta blanca 4:5 con el carrito solo con ícono (`icono_carrito`, aria-label intacto) y WhatsApp, y en tarjeta angosta
  una barra con `@container`; Inspírate en una fila). `dcasa_catalogo`: «Quedan pocas» / «Agotado» sobre la foto con la
  regla de la ficha (`tarjeta_disponibilidad`). `dcasa_brian_tienda`: cabecera de vidrio igual a la píldora (mismo
  `--dcasa-refraccion`), texto navy, íconos tinta, punto amarillo con aro azul. Mismo hueso en Mi cuenta y «Busca con una
  foto»; los correos no. Black Weekend no cambia (su carril y su tarjeta son propios).
- **Medido (copia de prueba, 1440 × 900):** portada de 10.425 a 6.530 px; categorías de 1.473 a 491; «Lo más buscado» de
  1.468 a 646. Comparación para la dueña: <https://claude.ai/artifact/XQti28eQjFLDzT1Z9CpsRH>.
- **Esta máquina:** contenedor nuevo; Odoo con `git submodule update --init --depth 1 vendor/odoo` y venv de Python 3.12
  en el scratchpad (con 3.13 no compila `rl-renderPM`; receta en CONTEXTO_AGENTICO). Capturas con la base `web_antes`
  (worktree del commit anterior) y `web_despues`; la cama «Tono Arena» con 2 unidades solo en la copia, para mostrar la
  etiqueta.
- **Sigue:** que la dueña lo mire en su iPhone (en Safari el vidrio es esmerilado, sin la onda de agua: es lo mismo que le
  pasa al navbar). Posibles mejoras que ella puede pedir: que «Lo más buscado» ponga primero lo que tiene existencia (hoy
  sale un «Agotado» real en tercer lugar) y Black Weekend con el mismo carril y la tarjeta nueva (hoy conserva los suyos).
  Ojo: la portada guardada en el borde puede tardar en mostrar un «Quedan pocas» nuevo.

### 2026-11-15: alternativas para Messenger e Instagram sin la revisión de Meta (OpenReply y 14 repos más). Solo investigación: no cambió código ni producción

- **Pedido:** ver si OpenReply (`diwenne/openreply`), una lista de MCPs de Instagram y otros repos sirven para que Juan conteste
  Instagram y Messenger a todos los clientes sin que los jefes pasen la revisión de la app de Meta y la verificación del negocio.
- **Conclusión: ninguno quita la revisión y ninguno supera a Juan.** OpenReply es un clon de ManyChat solo de Instagram
  (palabra clave en un comentario → DM con textos fijos): sin IA, sin base de conocimiento, sin memoria, sin Messenger; es
  autoalojado (Next.js + Postgres + Redis) y **no tiene planes** (el sitio es una demo). Sus propios documentos dicen que
  para cuentas sin rol en la app hace falta revisión y verificación del negocio. Los 5 MCPs de Instagram son herramientas para
  un asistente (publicar, leer): ninguno recibe DMs y contesta solo; 4 piden app propia de Meta y revisión para DMs de
  clientes reales; el quinto (`official-Arvind`) usa `instagrapi` (no oficial) y su README avisa de cierre de la cuenta.
  Los otros (comment-to-DM, bots de WhatsApp por Baileys) no usan IA o usan WhatsApp no oficial: no aportan.
- **Lo único que se acerca:** un proveedor que pone **su propia app de Meta**: **Zernio** (antes Late; patrocina OpenReply,
  alimenta ZernFlow). API de bandeja con Instagram, Facebook, WhatsApp, Telegram; avisos entrantes por webhook; envío por
  `POST /api/v1/inbox/conversations/{id}/messages`. Precio (de resultados de búsqueda de su documentación, no del sitio):
  pago por cuenta con 2 gratis y 10.000 mensajes al mes gratis, después US$0,0001 por mensaje; las fuentes se contradicen
  en algo. **No verificado:** que su app tenga acceso avanzado de mensajería para Instagram y Messenger (para WhatsApp sí
  dice «sin crear app ni pasar revisión»); terceros dicen que un proveedor «mueve» la revisión, no la elimina. Reseñas
  mixtas en Trustpilot. **El proxy de esta sesión bloquea `zernio.com` y `openreply.diwen.dev`**: no se leyeron sus sitios.
- **Si se prueba:** un adaptador nuevo en `juan/src/canales/` (interfaz de `tipos.ts`; los adaptadores de hoy miden 250–550
  líneas), apagado de fábrica. Primero la prueba barata: conectar una cuenta de Instagram SIN papel a Zernio (cuenta gratis) y
  ver si el mensaje llega al webhook. **Privacidad:** los mensajes y nombres de clientes pasarían por un tercero (hoy van
  Meta → Juan → Odoo); pide el visto bueno de los jefes y revisar sus términos (Ley 81).
- **Sigue:** decisión de los jefes: (a) verificar el negocio y pedir la revisión (el camino de siempre), (b) probar Zernio
  con la prueba barata, o (c) dejarlo como está. Meta también lanzó su propio «Business Agent» (junio 2026; gratis según
  unas fuentes, con cobro por token según otras; no verificado en Meta): compite con Juan y no usa Odoo, no se recomienda.

### 2026-11-13 (2) y 2026-11-14: avisos de Telegram ordenados, lote 1 de la web, «Busca con una foto», ícono de Brian y horario de la tienda (Desplegar 71 y Juan 25); Brian de la tienda y lote 2 de la web (Desplegar 72 y Juan 26) y la burbuja que cambia con el scroll (Desplegar 73), en producción; el 2026-11-15, Brian siempre activo de noche (Juan 27 y Desplegar 74)

**Y desde el 2026-11-15, 04:02 UTC (salud sana: `{"ok": true, "version": "d52a72b7dd9d", "base_al_dia": true, "humo": "ok"}`):** **Desplegar Juan 27** (run 43673722798, 03:44–03:47 UTC; `/salud` con `3cd053bcb0e86146385c2a3c7e4d74f6dae23c8f`) y **Desplegar 74** (run 43673907302, 03:47–04:02 UTC) con la imagen `sha256:a224f8c215c6cf78739fb3f5672fc5750e6592889519a9173307d670bbddc127` y `app_version` `d52a72b7dd9d3de8ab63ab0a7d7a1ca2892e00ec` (PR #120, squash `3cd053b`; CI 359 con staging, run 43668175433), con respaldo previo. La dueña probó a Brian de noche: «lo primero que dice es que no hay vendedoras… prefiero que él siempre esté activo… solo lo quiero configurar». Dos interruptores en Sitio web › Brian de la tienda: «Fuera del horario, avisar que la tienda está cerrada» (`avisar_cerrado`, apagado) y «De noche, el robot de la burbuja duerme» (`dormir_de_noche`, encendido: antes dijo que el robot dormido le gustaba). Comprobado en dcasapty.com a las 11 p. m.: saluda «Hola, soy Brian. ¿Qué buscas hoy?» sin «cerrada»; al pedir una vendedora da el horario y «te escriben mañana desde las 9:00 a. m.»; la burbuja dormida; sin «a. m..». **Por confirmar con la dueña:** Brian dijo «Comedores no los manejamos» (en el catálogo publicado no hay comedores; si sí los venden, hay que publicarlos o decírselo a Juan en el Conocimiento).

**Y desde el 2026-11-14, 17:54 UTC (salud sana: `{"ok": true, "version": "17f0c8295bf8", "base_al_dia": true, "humo": "ok"}`):** **Desplegar 73** (run 43622302488, 17:39–17:54 UTC) con la imagen `sha256:b97f72d07a908705d881d237fae3c2799e387fb07a92f73abffe5daf1b0cc133` y `app_version` `17f0c8295bf842c854c71c4c8222afb146a5aeac` (PR #119, squash `77702bb`; CI 357 con staging, run 43615430952), con respaldo previo; solo Odoo (Juan no cambió). La burbuja cerrada de Brian cambia de robot según la sección en pantalla. La dueña: «lo que yo quería también es que el ícono fuera cambiando con el scroll» y «por cada sección y a medida que hay scroll quiero que todos los iconos se usen en la burbuja del chat»; «No me tienes que hacer un video, solo hazlo y mándalo a producción». Antes preguntó por qué en el celular no se movía: era de noche (Brian duerme de 6 p. m. a 9 a. m.; le gustó así) y de día sí cambia al navegar. También: «felicidades por esas animaciones me gustaron mucho y las transiciones». Comprobado en dcasapty.com a 390 px: bajando por el Inicio, 12 poses distintas y sin errores.

**Y desde el 2026-11-14, 07:46 UTC (salud sana: `{"ok": true, "version": "f461cad33626", "base_al_dia": true, "humo": "ok"}`):** otra vez **Juan antes que Odoo** (el Durable Object `TiendaSesion` es la migración v2 del Worker): **Desplegar Juan 26** (run 43571228282, 07:28–07:30 UTC; `/salud` con `ea3bd96d6a74358dc633a8a62b4f7f797c6772af`, `tienda` lista y encendida con los ajustes de Odoo) y **Desplegar 72** (run 43571429646, 07:30–07:46 UTC) con la imagen `sha256:cff08b93711395b7ac1ef8030c6d4230008eda2a6f9e27d972288e0667d774a3` y `app_version` `f461cad33626b07adc2d5a70ca1971aaae595015` (PR #118, squash `ea3bd96`; CI 355 con staging, run 43564565700), con respaldo previo. Comprobado en dcasapty.com a 390 px: la burbuja de Brian en lugar de la de WhatsApp, una respuesta en 5,7 s con 5 tarjetas de colchones de verdad, el horario en el pie, `/privacidad` del 14 de noviembre y el mapa de Visítanos sin cargar hasta el permiso; sin errores en la consola.

**En producción desde el 2026-11-14, 00:35 UTC (salud sana: `{"ok": true, "version": "2bcc23e70c14", "base_al_dia": true, "humo": "ok"}`):** **Juan antes que Odoo** (lo pide `sin_leer`): **Desplegar Juan 25** (run 43533101840, 00:18 UTC; `/salud` con `894959be9830a65d0f581199f8911b088b42dcfd`; los mismos 5 avisos de siempre) y **Desplegar 71** (run 43533399099) con la imagen `sha256:99d1039a03df35dce88615e55b3bb9fb7891525bfb73bae4b6fab1ede39ea259` y `app_version` `2bcc23e70c1437d93c4fab310602ef2a71f9b747` (PR #117, squash `894959b`; CI 349 con staging, run 43524742607), con respaldo previo. **Es lo último en producción.**

- **Autorización nueva de la dueña (2026-11-13):** «no esperes mi aprobación para pasar a producción. Apruébalo y punto»
  y «vamos a subirlo lo antes posible». Esta entrega subió sin su visto bueno a las capturas; las revisiones adversariales
  se hicieron igual (son las que cuidan el dinero y los datos).
- **Avisos de Telegram** (pedido: «son muchos o muy repetidos… a la 1 de la mañana veo vendedoras activas»; eligió «A (que
  se pueda activar o desactivar) B. E.», no C ni D; «sigamos con Telegram»): de noche nadie recibe clientes (interruptor en
  Ajustes de Juan, encendido; lista por vendedora al abrir), solo avisan los pagos hechos, las cédulas y lo que Juan no
  pudo leer (`sin_leer` con su motivo; las capturas de Instagram con precio ya no son comprobantes), y textos en una sola
  forma. Detalle en [JUAN_ODOO.md](JUAN_ODOO.md) (reparto y «Avisos en paralelo»). Tres vueltas de revisión adversarial.
- **Horario de la tienda** (lo dio la dueña): lunes a sábado 9:00 a. m.–6:00 p. m., domingo 9:00 a. m.–5:00 p. m. La
  migración `post-horario.py` lo puso en Ajustes de Juan solo si seguía el de fábrica (8 a 17). Es configurable ahí mismo
  (la dueña preguntó; se le dijo dónde).
- **Informe externo D'CASA contra Carbone** (agente de Chrome de la dueña, 65 capturas): **2 de 3 «errores críticos» eran
  falsos** (la búsqueda con Enter y el carrito sí funcionan; el robot del informe fue más rápido que la página); se comprobó
  todo en producción antes de tocar nada. Lo real entró en el **lote 1 de la web**. Google mostraba `/web/login` con el
  texto de la web vieja y sin logo: ahora `noindex`; falta el trámite de **Search Console** (la dueña: «luego»).
- **«Busca con una foto»** (la dueña: «me gustó mucho el buscador de imagen de Carbone»), módulo `dcasa_buscar_foto`, con
  revisión adversarial (el bloqueante: los topes no aguantaban pedidos simultáneos). El texto de `/privacidad` quedó
  aprobado por la autorización general.
- **Ícono de Brian en el panel:** el robot pensativo con guiño que mandó la dueña (su archivo
  `web_pensativo_oficina_busto_ojosorig_cut.png`).
- **Brian de la tienda** (chat de ventas en la web). Decisiones de la dueña: se llama Brian y se presenta una vez; tope
  de IA propio de 30 USD al mes (Juan atiende 300–400 clientes al día con ~1,30 USD diarios); la burbuja sin texto
  reemplaza la de WhatsApp (WhatsApp va dentro del chat); muy educado, como Juan; la cotización del visitante es el carrito
  armado con su PDF; usar **los 16 robots** que mandó (`scratchpad`, zip `icon_15_bolsita_cutout`) con pose y transición
  distintas por página y estado; ubicación para el envío («si ya aprobé los precios de envío»); estrellas, sí; ampliar el
  chat, sí. Prototipo v2 aprobado (~80 % y los cambios). Construido en dos partes (Worker y Odoo, contrato escrito).
  **Tres vueltas de revisión adversarial**: la primera con dos bloqueantes (el tope de 30 USD no anotaba los turnos que
  cortaba el plazo; el PDF podía agotar las conexiones de la base), la segunda con cuatro menores del Worker y la tercera
  con un hueco de permisos (un usuario interno podía esconder sus consultas de la auditoría poniendo una marca en el
  contexto). Todo cerrado salvo «Por pagar a Meta» en el cambio de mes (pendiente antes del 1 de diciembre, en
  PRIORIDADES). El CI con todos los módulos encontró dos más (la fecha de `/privacidad` y que el pie no se podía guardar
  con el constructor por `pie_mi_cuenta`). Prueba de punta a punta en staging con el Worker de verdad antes de subir.
- **Lote 2 de la web:** horario en Visítanos y el pie (de Ajustes de Juan), mapa de Google solo con permiso de cookies,
  opiniones solo de quien compró y pagó, aprobadas por Gerencia, con invitación en el correo de la factura pagada. Va con
  Brian de la tienda.
- **«Tu compra lista»** (del chat al carrito con un código): diseño en borrador, sin aprobar; el carrito real de Brian de
  la tienda cubre la primera parte.
- **Incidencias de la sesión:** dos pausas por el límite de uso de 5 horas (los ayudantes se pararon cerca de una hora
  cada vez) y dos reinicios del contenedor (se pierden PostgreSQL y las corridas en segundo plano; los árboles y los
  commits quedan). Se reanudó cada ayudante desde donde quedó.
- **Sigue:** **Tilopay** la otra semana (Odoo no lo trae: hay que conectarlo; métodos: los que tenga activos); Search
  Console; «Por pagar a Meta» en el cambio de mes (antes del 1 de diciembre); Turnstile en el chat antes de anunciarlo
  en grande; herramientas del Brian del panel para la tienda y las opiniones; y un detalle de texto: Brian dice «a
  partir de las 9:00 a. m..» con dos puntos (`juan/src/tienda/motor.ts`, el aviso de tienda cerrada). El mapa no
  necesita regla nueva: el borde no manda `frame-src` (OPERACION).

### 2026-11-13: Juan ya no dice «no lo manejamos» de lo que no está publicado (Desplegar 69 y Juan 23) y responde comentarios de Instagram y Facebook, apagado (Desplegar 70 y Juan 24), en producción

**En producción desde el 2026-11-13, 03:20 UTC (salud sana: `{"ok": true, "version": "2ced21ccb09f", "base_al_dia": true, "humo": "ok"}`):** **Desplegar 69** (run 43356475622) con la imagen `sha256:1ad42b80f08882c6d05db19cb3d66fba5a54c7c14e69cf4e98b2165db5b7bb67` y `app_version` `2ced21ccb09f555da0159f1493867318617100e1` (PR #115, squash `7d965cd`; CI 345 con staging, run 43347631246), con respaldo previo. Y **Desplegar Juan 23** (run 43358329275, 03:22 UTC; `/salud` con `7d965cdab4b99f039172308f3339cc16b5d27a5b`).

**Y desde las 04:45 UTC (salud sana: `{"ok": true, "version": "70ac6f349a9e", "base_al_dia": true, "humo": "ok"}`):** **Desplegar 70** (run 43365883978) con la imagen `sha256:7c1a9d4cbfd6743d8480aabb44aac055d1c0729d6e23a9f48c4463d7215b7324` y `app_version` `70ac6f349a9e8be6f2939f063360de1031272fc9` (PR #116, squash `24493be`; CI 347 con staging, run 43358982543), con respaldo previo. Y **Desplegar Juan 24** (run 43367600509, 04:47 UTC; `/salud` con `24493be1a67c06a19b6d0266e5c0eb20a80598f9`; los mismos 5 avisos de antes, nada nuevo).

- **Qué pasó:** la dueña mandó la captura de un cliente al que Juan le dijo «solo manejamos la cama, no el colchón solo» («¿Esto es verdad?»). No: los colchones existen, pero no estaban publicados en la tienda y la búsqueda de Juan solo ve lo publicado. Ahora, cuando no encuentra algo publicado, la herramienta le dice por qué: `hay_sin_publicar` (existe en Odoo sin publicar: Juan dice «sí lo trabajamos», no da datos y pasa a una vendedora), `busca_de_nuevo` (probar otra palabra) o `no_lo_manejamos` (solo entonces lo puede decir). El Worker tiene además una guardia (`niega_producto`) que frena el «no lo manejamos» si la herramienta no lo dijo. Se le dio a la dueña el mensaje para el cliente.
- **La dueña ya publicó los colchones** (7 en la tienda; se encuentran con «colchón» y con «colchon») **y le escribió al cliente.**
- **Comentarios de Instagram y Facebook, en producción y apagados** (JUAN_CANALES §3c; dos vueltas de revisión adversarial, bloqueantes cerrados). Decidí yo (y se le dijo): la frase pública nunca lleva el nombre de quien comenta. La dueña preguntó si funcionarían con la puerta del jefe: **no**; Meta pide acceso avanzado para los avisos de comentarios también por inicio de sesión de Instagram, así que solo llegan los de cuentas con papel hasta la revisión de la app. Se le explicó cómo probarlo con su propia cuenta. Se le mandaron las capturas de Ajustes (computadora y celular).
- **Sigue:** el jefe sigue los pasos de la segunda puerta (JUAN_CANALES §3b) y marca `feed` / `comments` en la app; la dueña prueba los comentarios con una cuenta con papel; paquete para la revisión de Meta (Messenger y comentarios), ofrecido a la dueña.

### 2026-11-12: Juan cotiza envíos con la promoción, reparto justo de chats y Costos de IA con «Pagar», en producción (Desplegar 68 y Juan 21); Messenger e Instagram no les llegan a los clientes

**En producción desde el 2026-11-12, 23:1x UTC (salud sana: `{"ok": true, "version": "98f8002aab2b", "base_al_dia": true, "humo": "ok"}`):** **Desplegar 68** (run 43325822963) con la imagen `sha256:f2efed11…` y `app_version` `98f8002aab2b11af216c60fa847bc0d161aaf153` (PR #113, squash `b78d472`; CI 340 con staging, run 43280069880, segundo intento: el primero frenó en el respaldo previo de staging dormido), con respaldo previo. Y **Desplegar Juan 21** (run 43328387534) para el Worker. Después, **Desplegar Juan 22** (2026-11-13, 00:4x UTC, run 43339636718; PR #114, squash `d5c9ef9`; CI 342 con staging, run 43328896843): la segunda puerta de Instagram, **apagada** hasta que el jefe ponga `INSTAGRAM_TOKEN` e `INSTAGRAM_APP_SECRET` (`/salud` dice `"puerta": "pagina_facebook"`).

- **Aprobaciones de la dueña (tal cual):**
  - Juan cotiza envíos: «tienes mi sí» (Juan pregunta «¿quieres que te lo sume a la cotización?»); la frase con la promoción: «lo ideal es que explique bien que el envío realmente o regularmente cuesta tanto y que nosotros le estamos añadiendo $20 por la promoción, pero que a partir cuando termine la promoción el costo puede volver a su precio original». Decisiones: «Sin ITBMS (Recomendado)»; «Toda la provincia de Panamá (Recomendado)»; los $200 «Después del descuento»; una cotización de noviembre confirmada en diciembre «Sí, se respeta»; un lugar nuevo de una vendedora «No, hasta que Gerencia lo revise».
  - Costos de IA: «Simplemente me gustaría que un botón diga pagar y que el saldo que ya había ¡fuap! Ya salga como pago y que la cuenta empiece de nuevo» y, con las capturas: «me parece también bien el botón de pagar. Eso está excelente».
  - Reparto: «Sí, me parece bien eso que tú dices en cuanto a la atención de los chats»; «estas notas que se dejan solamente es entre vendedoras. Cualquier administrativo puede entrar y responder, hacer y deshacer, y delegar y cambiar chats». Y: «exacto cuando termines mandalo a produccion».
- **Qué lleva:** ver PR #113 y [ENVIOS.md](ENVIOS.md) › Juan cotiza el envío; [JUAN_ODOO.md](JUAN_ODOO.md) › Costos de IA y Trabajo en equipo y reparto. Revisión adversarial independiente: envíos en tres vueltas (dos bloqueantes cerrados), reparto y costos en dos vueltas (un bloqueante cerrado).
- **Decidí yo (y se le dijo):** Caja y Contabilidad cuentan como «administrativas» para el reparto; el programado que no sale queda como nota interna.
- **Falta de la dueña:** revisar en Envíos › Lugares (filtro «Por revisar (Gerencia)») los lugares agregados a mano antes de hoy (la migración los dejó «Por revisar»: Juan no da su precio hasta entonces); archivar la nota de la promoción de noviembre en el Conocimiento el 1 de diciembre; preguntar a la contadora si el envío lleva ITBMS (hoy `DCASA-ENTREGA` no lo lleva).
- **Hallazgo de la dueña (con otro Claude y un amigo): Messenger e Instagram NO les llegan a los clientes.** Las pruebas del 9 y 10 nov se hicieron con cuentas con papel en la app; Meta solo manda los avisos de esas cuentas mientras la app no tenga acceso avanzado. Corregido en JUAN_CANALES §3 y PRIORIDADES (punto 00). Aprobó: (1) probar la «segunda puerta» de Instagram (inicio de sesión de Instagram, con la cuenta propia de D'CASA; lo hace el jefe desde su cuenta personal) — está en producción desde Juan 22 (apagada) y los pasos del jefe están en JUAN_CANALES §3b; (2) **comentarios** de Instagram y Facebook: «Solo los que preguntan», «Corto y lo demás por privado», «Apagado hasta que lo pruebes» (se construye después de la segunda puerta). Para Messenger el único camino es la revisión de la app de Meta con el negocio verificado.
- **Sigue:** desplegar la segunda puerta de Instagram (CI → PR → Desplegar Juan); que el jefe siga los pasos y pruebe con una cuenta SIN papel; comentarios; paquete para la revisión de Meta (Messenger y comentarios).

### 2026-11-11 (3): Inicio nuevo, el celular al entrar, la caja del chat, entregas = Bodega, «Más datos» y modo oscuro, en producción (Desplegar 65, 66 y 67)

**En producción desde el 2026-11-11, 21:20 UTC (confirmado sano y estable a las 21:34):** **Desplegar 65** (Odoo y el
borde; run 43101954871) con la imagen `sha256:66e84351…` y `app_version` `b62903127c5483c8e6bd1cd4700e97a766accfb2`
(PR #110, squash `b8d6a51`; CI 334 con staging, run 43093423535), con respaldo previo. Lleva el Inicio nuevo, los tres
arreglos del celular, la caja de responder del chat en el celular y la lista entera en tableta. Juan no cambió.

**Y desde las 22:36 UTC (confirmado sano y estable a las 22:49):** **Desplegar 66** (run 43112609143) con la imagen
`sha256:a3bbe22a…` y `app_version` `8859a44eb6316281e327103a0566259fc6e558f1` (PR #111, squash `b66302a`; CI 336 con
staging, run 43104407376), con respaldo previo: «Entregas pendientes» igual que Bodega y «Más datos» en la cotización.
**Y desde el 2026-11-12, 02:06 UTC (confirmado sano y estable a las 02:19):** **Desplegar 67** (run 43138676351) con la
imagen `sha256:4a8a7ac0…` y `app_version` `f28c2ccd39abb3aeee1ed853bb1013004d80913f` (PR #112, squash `50b343b`; CI
338 con staging, run 43131640599), con respaldo previo: el **modo oscuro**. Era más nuevo que la versión estable 4.

- **Aprobaciones de la dueña (tal cual):**
  - «Si me gustaron los cambios para móvil lo que me gustaría es que así como se ve en detalles compacto y grandes así
    como actualmente está los iconos de los accesos rápidos de resto apruebo todo para producción así que empieza con
    todas las mejoras y el tema con el diseño nuevo en las dos versiones claro y oscuro». Se leyó así: en el celular
    los accesos directos se pueden ver de tres tamaños (Compactos, Detalle y Grandes como estaban), lo elige cada
    quien y se recuerda en ese aparato; el Inicio nuevo y el tema claro y oscuro quedan aprobados para producción.
  - «Y si apruebo la mejora de la caja de Juan» (la caja de responder del chat en el celular, boceto
    <https://claude.ai/artifact/A6P3KWL2F5KJx5MfX4sBsH>).
  - Sobre las tres decisiones abiertas («Más datos» en la cotización, Conversaciones en tableta y que «Entregas
    pendientes» cuente igual que «Bodega»): «Lo que consideres mejor y más lógico y coherente y funcional». Se decidió:
    (a) «Entregas pendientes» del Inicio muestra las mismas entregas que Bodega (pedidos con pago o abono) y una línea
    discreta con las que esperan pago; (b) en tableta la lista de chats se ve entera mientras no haya un chat abierto y
    se reduce a las fotos al abrir uno (se respeta la preferencia guardada); (c) en la cotización, un bloque «Más
    datos» que se pliega (teléfono fijo, direcciones, vencimiento, lista de precios, términos de pago), cerrado salvo
    que algo pida atención, sin mover ningún campo de la vista.
  - «Si gustas trabaja con multiagentes en paralelo».
  - Con las capturas del menú nuevo del celular y de la caja del chat a la vista (y avisada de los detalles en que la
    caja se apartó del boceto): «si apruebo todo». Y: «avísame cuando esté en producción» (se le avisó a las 21:29 UTC,
    con qué probar en su iPhone).
- **Inicio nuevo (propuesta 2), terminado en la rama** (`b67ea7e`): mismo orden y contenido, accesos del celular en
  tres tamaños (`dcasa.inicio.atajos` en el aparato, «Compactos» la primera vez), tres contadores que llevan a cada
  panel, cifras que suben al abrir, barras delgadas; todo cuelga de `.o_dcasa_tablero` (`tablero.scss`).
  `test_inicio_tablero.py` (8 pruebas). Capturas mostradas a la dueña. Tres detalles en que se apartó del boceto y que
  ella puede objetar: los accesos de la computadora un poco más bajos (64 px), el pie de cada panel dice siempre «Ver
  las N…», y las dos cifras de la vendedora van una sobre otra en el celular.
- **Reporte de la dueña sobre el celular (con tres capturas de su iPhone):** «tan pronto inicio sesión, aparece en
  blanco, tengo que tocar el menú del navbar, tocar inicio, me lleva a una subcarpeta y luego después sí puedo ir al
  inicio… en iPhone, cuando estoy en un chat y si deslizo el dedo desde la zona extrema izquierda hacia la derecha…
  no vuelve atrás, sino que vuelve al inicio de todo y no a las conversaciones». **La auditoría visual no lo vio**: el
  recorrido abría cada pantalla por su dirección y medía la pantalla ya cargada; nunca probó «entrar y esperar» ni los
  gestos del teléfono. Tres causas, tres arreglos, en la rama (`0428ef2`, `e9f0e74`, unidos en `516a20e`):
  1. *Pantalla en blanco al entrar.* El Inicio esperaba las cifras del servidor antes de pintar nada
     (`onWillStart`); mientras tanto solo se veía la barra de arriba. Se reprodujo retrasando `obtener_datos`: sale
     idéntico a su captura. Ahora el Inicio se pinta de inmediato (`.o_dcasa_arranque`: el saludo de verdad y bloques
     en gris) y las cifras llegan después; si no llegan, lo dice y ofrece «Reintentar». Además, el área de trabajo
     vacía dice «Cargando…» para cualquier pantalla que tarde (`arranque.scss`). En esta máquina el servidor entrega
     las cifras en 0,1–0,2 s y producción contesta en 0,2–0,3 s por pedido: lo lento es la suma de pedidos del primer
     arranque en el teléfono, no una consulta en particular.
  2. *La «subcarpeta».* Era el menú de Odoo para el celular, de dos caras: primero «las secciones de la app abierta» y,
     con un botón, «Todas las aplicaciones». En el Inicio no hay secciones: salía una hoja con solo la palabra
     «Inicio», sin nada que tocar. Ahora el cajón es propio (`menu_celular.js`, hereda de la barra lateral de la
     computadora): «Inicio» y «Buscar» fijos arriba; debajo todas las aplicaciones; la que está abierta viene con sus
     secciones a la vista; la flecha de cada aplicación despliega las suyas sin salir de donde se está; tocar una
     pantalla la abre y cierra el menú. Todo lo que se toca mide 44 px o más.
  3. *«Atrás» en el chat.* En el celular Conversaciones muestra una cosa a la vez, pero para el navegador era una sola
     página: el gesto de «atrás» salía a la pantalla anterior. Ahora cada cosa abierta (chat, ficha, ventana, foto)
     pone un paso en el historial y «atrás» cierra la de más arriba (`atras.js`, con `router.skipLoad` de Odoo para que
     no recargue la pantalla). De vuelta en la lista ya no se recuerda un chat «abierto» que no se ve. En la
     computadora no cambia nada.
  Pruebas: `test_celular_arranque_y_menu.py` (dcasa_interfaz) y `test_panel_atras.py` (dcasa_conversaciones). En la
  copia local: `/dcasa_interfaz` completo, 0 fallas; las clases del chat en celular y computadora, 45 de 46 (la que
  falla, `test_sin_reparto_por_turnos_no_hay_interruptor`, es por los ajustes de la base de capturas, no por el cambio).
  **El menú nuevo es interfaz nueva**: se le mostraron las capturas a la dueña; ella había pedido «lo que sea mejor para
  el uso adecuado y accesible del navbar en móviles».
- **Caja de responder del chat en el celular y lista en tableta (en producción con Desplegar 65, `565e8a0`):** la
  caja vacía bajó de 215 a 111 px en 360 y 390 px de ancho, sin quitar herramientas. Renglón 1: quién atiende,
  «Devolver»/«Atender» y Respuesta / Nota; renglón 2: «+», «Sugerir», el texto y Enviar; dentro del «+»: Adjuntar,
  Foto del catálogo, Cotización, Rápidas y Programar. En tableta (hasta 1100 px) la lista de chats se ve entera
  mientras no hay uno abierto. `test_panel_caja_celular.py`, `TestDisposicionDeTableta`. Se apartó del boceto en
  nombres («Adjuntar», «Foto del catálogo») y en que «Atender» es un enlace; la hora de vuelta del asistente no se ve
  en el celular (antes salía cortada). La dueña lo aprobó así.
- **«Entregas pendientes» = Bodega y «Más datos» en la cotización (en producción con Desplegar 66, `b5c5440`):** el panel y la cifra del Inicio muestran las mismas entregas que Bodega (pedidos con pago o abono) y un
  renglón gris dice cuántas más esperan («2 más esperan pago o abono») y abre esa lista; quien ve el panel sin permiso
  de Inventario sigue viendo todas. En la cotización, un botón «Más datos» pliega teléfono fijo, direcciones,
  vencimiento, lista de precios y términos de pago **sin mover ningún campo** (se esconden con `:has()`); nace cerrado,
  se abre solo si la entrega va a otra dirección o falta un dato obligatorio, y se recuerda en el aparato. En el
  celular los productos suben 353 px. `test_entregas_inicio.py`, `test_mas_datos.py`. Dudas menores que la dueña puede
  opinar al verlo: que el botón nombre también «teléfono fijo», y que al abrir los datos aparecen en su sitio de
  siempre (encima del botón).
- **Modo oscuro (en producción con Desplegar 67, `6228a4a`; aprobado por la dueña):**
  la dueña vio trece capturas (celular y computadora) y dijo: «Si me gusta, apruebo el modo oscuro para producción».
  Gris «de consola» (fondo #1F2226, superficies #2A2E33), botones en azul #3A63CF, amarillo solo en insignias. Lo
  enciende cada persona en el menú de su usuario («Modo oscuro»); se guarda en ese navegador (galleta `color_scheme`,
  un año) y el panel se recarga. Por defecto, claro. **El claro no cambió**: su hoja compilada es idéntica byte a byte.
  Cómo está hecho y la regla para lo nuevo, en CONTEXTO_AGENTICO («Modo oscuro»). Control de contraste: 634 pantallas
  y 17.340 textos medidos; lo único bajo 3:1 que es nuevo en oscuro son botones deshabilitados (≈3,0:1; en claro
  ≈2,6:1). `test_modo_oscuro.py` (20 pruebas). En la Guía: «Poner el sistema en modo oscuro». Decisiones del ayudante
  que la dueña vio en las capturas y puede objetar: en oscuro los botones amarillos grandes («Validar» de Bodega,
  «Revisar ahora» de Sofía, «Nueva campaña») van en azul; las cifras grandes en blanco. Preguntas abiertas, sin prisa:
  ¿el interruptor también en el menú de las tres rayas del celular?; ¿por usuario en vez de por navegador?; ¿que siga
  solo el modo del teléfono?; las fotos de producto, el QR y la vista previa del correo quedan sobre blanco. Sin ver
  con datos: Envíos con tarifa, Bodega dentro de una entrega, Escáner con un producto leído, Camila con una campaña.
- **Los ayudantes y el límite de uso:** cada frente en su copia de trabajo (ver CONTEXTO_AGENTICO, «Varios agentes a
  la vez»). El límite de la cuenta (cinco horas) los cortó tres veces; se reanudaron con su avance intacto las dos
  primeras; la tercera, el modo oscuro se reanudó a las 23:40 UTC (el límite ya dejaba) y terminó a las 00:57.
- **Sigue:** que la dueña pruebe
  en su iPhone lo desplegado (no se pudo probar en un teléfono real ni con su usuario); el modo oscuro con sus
  capturas. Siguen sin respuesta: borrar la rama remota `claude/bold-volta-fsqq4c` y el motivo real en «Quedó por
  enviar». Pendientes menores anotados por los ayudantes: en tableta parada (768–991 px) el botón de Brian tapa
  «Enviar» del chat (ya pasaba); las referencias de píxeles de 390 px de la lista y de Conexiones no coinciden en esta
  máquina.
- **Esta máquina:** con el «sí» de la dueña («Sí, borra las dos») se borraron los 13 worktrees viejos de
  `.claude/worktrees` y 15 bases locales de pruebas: el disco pasó de 1 GB a ~20 GB libres.

### 2026-11-11 (2): auditoría visual del panel; 21 arreglos en producción (Desplegar 64); propuesta 2 del Inicio

**En producción desde el 2026-11-11, 09:15 UTC:** **Desplegar 64** (Odoo y el borde; run 42992509876) con la imagen
`sha256:e84667ef…` y `app_version` `cf64f97d898b1da616fc6c82bdd6f6559906e19d` (PR #109, squash `b8c6044`; CI 332 con
staging, run 42984980093), con respaldo previo. Juan no cambió (Desplegar Juan 20). **Es más nuevo que la versión
estable 4**: si la dueña lo da por bueno unos días, toca nombrar la estable 5.

- **Autorización de la dueña (antes de dormir, tal cual):** «todos los arreglos de la auditoría que no son parte de un
  nuevo diseño, puedes ya irlos subiendo y publicando y mandarlos a producción. Pero lo que hace parte de una nueva
  interfaz o nuevo tema, eso tengo que analizarlo y verlo muy bien, incluso en dispositivos móviles». Y: «espero que
  todos los errores… ya estén solucionados y en producción cuando yo despierte». Por eso esta tanda fue a producción
  sin esperar su visto bueno sobre capturas; **nada de diseño nuevo se subió**.
- **Pedido de la dueña:** «una auditoría completa del aspecto visual del panel… en dispositivos móviles… y en distintas
  computadoras… encontrar ciertos problemas y solucionarlos… modernizar sin dañar lo que ya funciona». Y, con un video
  de un tablero que le encantó: «sí busco un modernismo así… sin olvidar el branding que ya tenemos… ahora mismo es
  estático».
- **Cómo se hizo:** 660 pantallas capturadas y medidas con Playwright en una copia local con datos de prueba: las 242
  del menú de Gerencia en celular (390 px) y portátil (1366 px); las 18 apps en celular de 360 px, tableta parada y
  acostada, 1280 px y 1920 px; las 43 de la vendedora; y 15 pantallas por dentro (chat, cotización, contacto,
  producto, oportunidad, factura, entrega). Resultado: ninguna pantalla se sale de costado, la vendedora sin errores,
  **19 molestias**. Informe con capturas de antes y después (página privada de la dueña):
  <https://claude.ai/artifact/QN3GPdAtm7nKxQtu9X64MP>.
- **Arreglado y en producción, con prueba de navegador cada uno:**
  1. *Fecha con hora cortada en todas las listas de la computadora* («11 nov,…»). Causa: Odoo mide el ancho de una
     fecha en un bloque invisible colgado del `<body>`, y el `<body>` de D'CASA es una rejilla; el bloque caía en la
     columna de la barra lateral angosta (68 px). `barra_lateral.scss` + `listas.js` (la columna puede encogerse hasta
     lo que mide una fecha de este año). En Cotizaciones, Origen y Estado llevan ancho fijo para que las etiquetas no
     se corten. `test_listas_fechas.py`.
  2. *El botón de Brian tapaba el ITBMS y el Total de la cotización* y la última columna de las listas: formularios,
     listas y tarjetas de Odoo terminan con el mismo hueco que ya tenían las pantallas propias (`brian_panel.scss`,
     `test_boton_no_tapa.py`).
  3. *Aviso de lista vacía*: ya no dice «Toca «Nuevo»» donde no hay ese botón, y sale también en las listas sin texto
     de ayuda, que quedaban con cuatro renglones en blanco (`sin_odoo.js`, `test_lista_vacia.py`). Cierra UI-01 de
     [auditoria/ui-backend.md](auditoria/ui-backend.md).
  4. *Listas en el celular*: las columnas de texto no bajan de 170 px (48 de 105 listas salían en «CAM…», «Client…») y
     la lista se desliza de lado como antes. El botón de copiar se queda.
  5. *Cabecera de los formularios en el celular en un renglón* (de 128 a 62 px): «Actividad» va solo con su ícono.
  6. *Compras en el celular*: el aviso de «no hay nada» va debajo del tablero de cifras, no encima.
  7. *Ficha del contacto en el celular*: la foto mide 72 px para que el nombre y el correo se lean.
  8. *Barra de arriba en el celular*: el reloj de actividades medía 29 px de ancho (las rayitas 36, Brian 38): ahora 44.
  9. *El ejemplo de «Sitio web» del contacto* ya no nombra a odoo.com.
  10. *Pestañas de Contabilidad en la computadora*: su barra de desplazamiento va escondida y con el mouse no se
      alcanzaban las últimas («ITBMS», «Analítica») en 1366 px; ahora bajan a otro renglón (`contabilidad.scss`,
      `test_pantallas.py`). En el celular se siguen deslizando con el dedo.
  11. *Sitio web › Páginas* daba «Acceso denegado» a Gerencia (la lista de Odoo 19 pide el grupo de editor del sitio y
      lee las plantillas): el menú ya no se muestra. No se cambió ningún permiso (`sitio_views.xml`, `test_sitio.py`).
  12. *Compras en el celular*: las cinco cifras del tablero van de tres en tres con el nombre entero (salían
      «Solicit… de cotiza…»).
  13. *Oportunidad en el celular*: ya no queda el «en» de «$ 0.00 en 0.00 %» colgando junto al monto.
  14. *Letra de 10,9 px* en «Ctrl K» y en la franja de Envíos del celular: 12 px.
- **Segundo recorrido (lo que solo se ve al usar el panel):** un agente recorrió ventanas, desplegables y formularios en
  celular y portátil con las dos cuentas de prueba; 15 hallazgos, cada uno mirado en su captura antes de tocar nada.
  Arreglados y en producción:
  15. *Conversaciones: fecha al revés.* Una conversación vieja decía «11/04/26» para el 4 de noviembre: el formato
      numérico de «es-PA» es mes/día/año. Ahora día/mes/año (`utilidades.js`), igual en las conversaciones anteriores
      de Brian. `test_panel_interfaz.py` vigila además que ninguna pantalla propia arme fechas de solo números con
      «es-PA».
  16. *Escáner sin cámara o sin permiso*: el aviso de Odoo salía gris oscuro sobre el fondo negro; ahora se lee
      (`camara.scss`). El campo «Precio nuevo» salía como campo crudo del navegador.
  17. *Cotización en el celular*: «Enviar por WhatsApp» se partía en dos líneas, los tres puntos caían debajo y el
      estado se montaba sobre el botón. Ahora el botón y sus tres puntos van juntos y el estado baja limpio a su
      renglón si no cabe (`global.scss`, `test_cotizacion_celular.py`).
  18. *Vendedora: tres botones bajo las líneas* («Descuento», «Agregar envío», «Pedir descuento a Gerencia») quedaban
      como cajas de tres renglones; ahora cada uno en una línea y el que no cabe baja.
  19. *Inicio y Estadísticas*: «Hoy / Esta semana / Este mes / Un rango» salían con el marco gris del navegador (son
      `<button>` sin `.btn` y les faltaba `border: 0`).
  20. *«Buscar» de la barra lateral* contestaba «No se encontraron comandos» al escribir «facturas»: abría el modo
      «comandos» de Odoo. Ahora abre en la búsqueda de pantallas (`openMainPalette({ searchValue: "/" })`).
  21. *«Cobrar premio»*: la venta salía rotulada «Order»; ahora «Venta» (solo el rótulo del campo).
- **Anotado y sin tocar** (es de Odoo estándar, es un dato o es diseño): la tarjeta «Instale Odoo», OdooBot y el aviso de
  notificaciones push; «Manual Payment» como nombre del método de pago (dato: se cambia en Ajustes); pie de los
  diálogos con tres botones desiguales en el celular; la barra de la Actividad se desliza de lado en el celular; filtros
  de 27 px de alto en el celular; gráficas de Odoo en celeste; tablas dinámicas en el celular; pantallas de 1920 px.
  Detalle con capturas en el informe: <https://claude.ai/artifact/QN3GPdAtm7nKxQtu9X64MP>.
- **Inicio nuevo, propuesta 2** (boceto; **no** está en el panel, ni en staging): <https://claude.ai/artifact/6s9iQpc8ZFh1DNse8vA2RG>.
  La dueña vio la propuesta 1 (<https://claude.ai/artifact/VUKX4zkP16JQ5HVcDwjm6G>) y dijo: «todo está un poco
  maximalista»; «el orden actual está muy bien. Y alterarles esto va a hacer que tengan cierta resistencia al cambio. La
  idea es proponerles lo que ya está en una versión mejorada»; «en el modo claro, me gusta que mantengas ese blanco y
  esos azules. Pero en el modo oscuro, me gustaría algo más grisáceo y serio… más estilo Cubase 16»; en el celular «es
  muy importante preservar los accesos directos de utilidad, que son mensajería, escáner, órdenes de las cotizaciones
  que crean las vendedoras, y el chatbot con página web, que es la segunda, y los pedidos a entregar… y el mismo
  dashboard que ya existe, pero todo organizado de una mejor forma»; y «estos temas y estos gráficos prefiero yo primero
  antes aprobarlos y poderlos ver muy bien en todas sus formas, antes de tirarlos a staging o a producción». La
  propuesta 2 conserva el orden de hoy (botones, nueve accesos, tres paneles, avisos, ventas, cifras, gráficas), pone los
  nueve accesos en la primera pantalla del celular (interruptor «Compactos / Detalle» para comparar), suma tres
  contadores que llevan a cada panel, y trae el modo oscuro en gris. Movimiento discreto.
- **Pruebas:** CI 330 (`3ce4c4a`, los diez primeros, con staging) verde; CI 331 cancelado (quedó viejo al subir más
  arreglos); **CI 332** (`cf64f97`, todo junto, con staging) verde: staging sano con esa versión. En local, sobre la
  base de capturas, las clases tocadas pasan.
- **Boceto de la caja de responder del chat en el celular** (de 211 a 111 px, sin quitar herramientas):
  <https://claude.ai/artifact/A6P3KWL2F5KJx5MfX4sBsH>. No se tocó el chat: es la pantalla que más se usa y sus botones
  de 44 px están a propósito. Espera su decisión.
- **Falta de la dueña:** (1) la propuesta 2 del Inicio: ¿le gusta?, ¿accesos compactos o con detalle en el celular?;
  (2) el boceto de la caja del chat; (3) en la cotización, ¿se guardan los datos de pocas veces en «Más datos» para que
  los productos queden arriba?; (4) Conversaciones en tableta nace con la lista reducida a iniciales (a propósito hasta
  1100 px): ¿que abra entera mientras no haya un chat elegido?; (5) en el Inicio, «Entregas pendientes» cuenta todas las
  entregas por despachar y el acceso «Bodega» solo las que tienen pago o abono (pueden decir números distintos): ¿se
  dejan iguales? Y siguen sin respuesta: borrar los 18 GB de worktrees viejos y la rama remota `claude/bold-volta-fsqq4c`.
- **Sigue:** que la dueña mire el panel en producción y la propuesta 2; con su respuesta, construir el Inicio nuevo en la
  rama y mostrárselo en capturas (celular incluido) **antes** de staging.
- **En esta máquina (resuelto el mismo día, ver la entrada de arriba):** el disco estaba al 98 % por 13 worktrees viejos
  de agentes y bases locales de pruebas; se borraron con el «sí» de la dueña. Las pruebas locales de esta tanda se
  corrieron sobre la base de capturas, no en una base limpia.
### 2026-11-11: versión estable 4; Instagram con fotos confirmado; enlace de choferes encendido; cierre de semana

**En producción** (sin despliegues nuevos de Odoo): Odoo y el borde en Desplegar 63 (`3e2ccfc`) y Juan en Desplegar
Juan 20 (`c378382`). Este día solo se registró la versión estable, se ordenó la documentación y se cerraron issues.

- **Versión estable 4** (pedido de la dueña: «actualizar esta versión como la última versión estable»): Desplegar 63
  (imagen `sha256:acda72c1…`, `app_version` `3e2ccfc`) con Juan hasta Desplegar Juan 20. En `.github/versiones_estables.json`,
  en el botón «Volver a una versión estable» y en [VERSIONES_ESTABLES.md](VERSIONES_ESTABLES.md), con la nota de que
  Juan se vuelve aparte. **Ensayada en staging** con el botón: run 42951600639, bien en unos 24 minutos.
- **Instagram con fotos, confirmado por la dueña** (Juan 20: la foto se sube en el mismo envío, como Messenger).
  **Enlace para choferes encendido** por la dueña.
- **Issues cerrados** (resueltos según la dueña el 7 nov): #9, #10 y #12 (códigos de barras) y #26 (topes de Brian).
  Quedan 10 abiertos (privacidad #22 y #23, Juan #24, CRM fase 2 #15 y #17 a #21, puerta `/master` #27).
- **Evaluación pedida por la dueña:** 82/100 «en producción de verdad». Para subir a 90+: avisos a Gerencia cuando un
  canal de Meta deja de enviar o recibir (el 131070 no avisaba), la IA de respaldo de Juan (`ANTHROPIC_API_KEY`
  falta, según `/salud`), plantillas de WhatsApp y nombre visible, privacidad (#22 y #23).
- **Dependabot #98** (Juan: `ai` 7.0.164 y `@ai-sdk/*`, versiones de parche) queda abierto a propósito: no se
  despliega Juan al cierre de la semana sin nadie mirando. Va primero la semana que viene.
- **Sigue:** ver [PRIORIDADES.md](PRIORIDADES.md) «Lo que sigue».

### 2026-11-10: WhatsApp 131070 RESUELTO («redireccionar conversación» a D'CASA Juan); Juan pide el control y anota todo

**Resuelto (10 nov, tarde):** con la cuenta de los jefes (administradores del portafolio DCasa Pty), la dueña encontró en
Meta el botón **«redireccionar conversación»** (el Enrutamiento de conversaciones), mandó las conversaciones a «D'CASA
Juan» y **eliminó a Callbell**. WhatsApp volvió a enviar y recibir sin esperar los 7 días que decía soporte.

**En producción** desde el 2026-11-10: PR #104, CI #315, **Desplegar Juan 17** (`main` = d40607f, árbol = cf52548);
PR #105, CI #317, **Desplegar Juan 18** (`main` = ac75436, árbol = 4c16cd2); y PR #106, CI #319, **Desplegar Juan 19**
(`main` = f8a6c24, árbol = b955b2f); y PR #107, CI #321, **Desplegar Juan 20** (`main` = c378382, árbol = f1cba72).
Odoo sin cambios.

- **Instagram conectado** (10 nov, tarde) por la página DCASA PTY, con la misma app y la misma llave que Messenger
  (`META_PAGE_TOKEN` reemplazada; Messenger siguió funcionando). Juan contestó un DM de prueba y salió en Odoo con el
  nombre. La foto no salía (igual que Messenger el 9 nov). **Juan 19** la subía aparte (`attachment_id`) y siguió
  fallando; **Juan 20** la sube en el mismo envío como Messenger y, si falla, Odoo muestra lo que dijo Meta a cada intento.
  **Confirmado por la dueña: la foto llegó por Instagram.**
  Se descartó la guía de un conocido («inicio de sesión con Instagram»): otra llave que vence y cambios en Juan.

- **La causa más probable del 131070**: el **«Enrutamiento de conversaciones»** de Meta (Conversation Routing, desde
  septiembre de 2026) decide qué app es la principal de los chats del número; solo esa contesta y las demás reciben
  131070. Al quitar Callbell, Meta **no nombra otra principal** por su cuenta. Ver [JUAN_CANALES.md](JUAN_CANALES.md) §1.
- **Juan 17:** si un envío da 131070, Juan pide el control de ese chat (Thread Control, «take») y, si Meta se lo da,
  manda otra vez lo rechazado. Todo envío rechazado deja su código y su `fbtrace_id` en el registro de `dcasa-juan`.
  **Juan 18:** un aviso de WhatsApp que no da mensaje ni palomita se anota con su forma (campo, claves, tipos), sin datos.
- **Pruebas con soporte de Meta (chat):** a las 12:13 un envío desde el Explorador de la API Graph (app «D'CASA Juan»,
  número de la tienda) **llegó** al celular: **ya se puede enviar**. Los mensajes al número llegan (doble palomita) pero
  no a Odoo. Se volvió a suscribir la app a la WABA (`POST 1313438470854835/subscribed_apps` → `success: true`) y a las
  12:22 Meta sí llamó al webhook (200), pero el mensaje no apareció en Odoo (Juan 18 dirá qué forma tiene ese aviso).
- **Soporte de Meta:** tras un cambio de proveedor, el número tarda **hasta 7 días** en desvincularse de la app y del
  activo anterior (desde el 9 nov: hasta el **16 nov**). **Callbell** propuso eliminar el número y volver a
  registrarlo: **no se hace** (se pierde límite, calidad y plantillas; hace falta la SIM y quizá el PIN de dos pasos).
  Se le pidió a Callbell quitar sus enlaces y decir si puso PIN. Los jefes ya entraron como administradores del
  portafolio: queda una revisión con Claude en Chrome del enrutamiento, socios y apps conectadas (cambios solo con «sí»).
- **Sigue:** WhatsApp, Messenger e Instagram funcionan con fotos (el 131070 se resolvió el mismo 10 nov). El enlace
  de choferes ya está encendido (11 nov). Pendiente: el motivo real en «Quedó por enviar», pedir un nombre visible
  nuevo de WhatsApp («DCasa Pty» DECLINED) y, si la dueña lo pide, respuestas a comentarios de Instagram.

### 2026-11-09 (tarde y noche): enlace para choferes; «Colchones» abre WhatsApp; Messenger conectado; WhatsApp bloqueado por Meta (131070)

**En producción** desde el 2026-11-09: PR #100, CI #305, Desplegar 63 (imagen `sha256:acda72c1…`, versión 3e2ccfc) y
Juan 13 (`main` = 4a01039, árbol = 3e2ccfc).

- **Enlace para choferes** (pedido de la dueña: «un link de calculadora a los choferes … que no vean la tabla de
  kilometraje»; «un solo enlace para todos»). En Envíos › Tarifa, abajo, Gerencia lo enciende, copia el enlace y lo
  cambia con «Crear un enlace nuevo». El chofer busca el lugar y ve solo el nombre, la zona, el precio **desde D'CASA**
  y la ruta en Google Maps; nunca los km ni la tabla; sin tarifa aprobada, «confirma el precio con la tienda».
  **«Usar mi ubicación» viene apagado** («por defecto inamovible … que nosotros lo decidamos»): solo Gerencia lo
  enciende. Ver [ENVIOS.md](ENVIOS.md) «Enlace para choferes». La dueña **lo encendió el 11 nov**.
- **Revisión de seguridad independiente** del enlace: nada bloqueante; se arreglaron los límites (2 búsquedas a la
  vez, 1 500 por día con nota a quien creó el enlace y contador en la ficha, IPv6 por /64, 300 por minuto entre todos,
  texto corto), cuerpos rotos que daban 500, `write` sin permiso que rearmaba el buscador, `create` que aceptaba el
  secreto y el borde que no reconocía el enlace con idioma delante. Lo no evitable (quien tiene el enlace ve precios
  y Google Maps los km) quedó escrito en ENVIOS.md.
- **Portada:** una categoría sin nada publicado (hoy «Colchones») abre WhatsApp con «quiero información de
  colchones»; al publicar un colchón vuelve sola a la tienda (decisión de la dueña). Confirmado en producción.
- **Dependabot** #96, #97 y #98 (Juan: `ai` y `@ai-sdk/*`; borde y puente: `workers-types` y `wrangler`).
- **CI:** la 303 falló en la prueba de «Colchones» (el catálogo del CI ya trae colchones publicados) y la 304 en una
  prueba del puente que dependía de la velocidad de la máquina; las dos reproducidas en local y arregladas (ver
  CONTEXTO_AGENTICO).
- **Messenger conectado** (con Claude en Chrome y la dueña): control total de la página para la cuenta usada, webhook,
  suscripciones solo en DCASA PTY y `META_PAGE_TOKEN`. Juan contestó un «Hola buenas» y la conversación salió en Odoo.
  Hasta la revisión de Meta (que pide verificar el negocio: lo ve la administración) solo contesta a quien tiene rol en
  la app. **Instagram** quedó a medias: «Invalid Scopes» (faltan los permisos de Instagram en la app) y hace falta
  entrar con acceso al portafolio DCasa Pty. Pasos en [JUAN_CANALES.md](JUAN_CANALES.md) §3.
- **WhatsApp dejó de enviar desde las 16:00** con el código **131070** («otra app controla la conversación»). No fue el
  token de la página ni el sistema (Messenger funcionó de punta a punta a la misma hora): en Meta el número quedó
  **sin cuenta de mensajes** («Add a Messaging account»), probablemente porque Callbell retiró la suya cuando se le pidió
  retirar su línea de crédito. Lo arreglan los dueños en Meta desde DCasa Pty (crear y ligar una cuenta de mensajes con
  su tarjeta). Ver JUAN_CANALES §1 «Si deja de contestar».
- **Fotos de Messenger** (madrugada del 10): el texto salía y la foto no («(#100) Error al subir el producto»: Meta no
  lograba bajarla de nuestra URL). Juan ahora sube el archivo a Meta (multipart `filedata`), con respaldo por URL. En
  producción: PR #101, CI #308, **Desplegar Juan 14** (`main` = 4cc4b97, árbol = 3af9123; Odoo sin cambios).
  **Confirmado** por la dueña: la foto de la cama llegó por Messenger con su texto.
- **El nombre del cliente de Messenger e Instagram** (en Odoo salía «Messenger 2838…»): Juan se lo pide a Meta una vez
  por conversación antes de guardar el mensaje; Odoo cambia el nombre provisional por el real. En producción: PR #102,
  CI #310, **Desplegar Juan 15** (`main` = 7707b53, árbol = 5d19c7c).
- **Sigue:** que los dueños liguen la cuenta de mensajes (y probar que Juan vuelva a enviar; si sigue el 131070, el
  «Agente de negocios de Meta»); encender el enlace de choferes; Instagram;
  en el próximo lote, el motivo real en el aviso «Quedó por enviar».

### 2026-11-09: «No llegó» por el pago de Meta (131042); preguntas sin respuesta para las vendedoras; videos con voz

**En producción** desde el 2026-11-09: PR #99, CI #301, Desplegar 62 (imagen `sha256:f467a09a…`, versión 5882fa4) y
Juan 12 (3b86ee3).

- **«No llegó» desde hace dos días** (WhatsApp oficial; «a veces sí, a veces no»). **Causa:** el globito de la
  etiqueta dice **131042, «Business eligibility payment issue»**: Meta no deja salir los mensajes por un problema de
  **pago de la cuenta de WhatsApp Business**, no del sistema ni de la IA. En Facturación y pagos › Cuentas de mensajes
  la cuenta del número (la que era de **Callbell**, ID …764382) se pagaba con una **línea de crédito de Callbell**; la
  dueña dejó Callbell y conectó Juan con el mismo número. Las otras dos «DCasa Pty» no tienen método de pago. **Lo
  arregla la dueña en Meta** (tarjeta propia y predeterminada en esa cuenta; si no la deja, pedirle a Callbell que
  revoque la línea; información fiscal). Se le dio un encargo para Claude en Chrome que revisa todo en solo lectura y
  trae un reporte. Lo ya fallido no se reenvía solo: las vendedoras vuelven a escribirles.
- **En el sistema** (la revisión de estos cambios, más abajo): los motivos de la cuenta (131042 pago, 131031 bloqueo, 131048 spam)
  en palabras de la tienda y con su código siempre entero; **aviso por Telegram a Gerencia** (cron
  `ir_cron_avisos_de_cuenta`, una vez cada 6 h por código, reintento a la media hora si no le llegó a nadie; los
  recibos de más de 2 h no avisan; también un rechazo al enviar). Ver [CONTEXTO_AGENTICO.md](CONTEXTO_AGENTICO.md)
  «WhatsApp oficial (Meta)».
- **Preguntas sin respuesta para las vendedoras** (pedido de la dueña): menú para Ventas y botón **Contestar**. Sin
  cifras ni política (dinero, números también en palabras, plazos, horarios, garantía, entregas, crédito, cambios,
  descuentos…; `conocimiento_texto.necesita_revision`, por raíces), Juan la usa al momento; con eso, Gerencia la revisa
  («Convertir en conocimiento», borrador). El tema es editable y se limpia; la pregunta del cliente también se revisa
  (un «sí» no confirma un precio que el cliente inventó). La dueña no alcanzó a elegir: se usó la opción recomendada.
  **Revisión adversarial independiente** (dos pasadas): un bloqueo (el precio de la pregunta en el título) y varias
  cosas a mejorar, todo arreglado con su prueba.
- **Videos:** a los 3 de camas (805, 801, Queen Black) y a los 3 del lanzamiento de la página se les puso la voz de
  Yuli (ElevenLabs v4) y música de Suno pedidas al **Calendario de Marketing** por MCP (≈ $0.66 en total), pegadas por
  frase con ffmpeg y revisadas con un reconocedor de voz (vosk). El calendario no tiene herramienta para subir archivos
  ni para leer los medios de una publicación: la dueña subió los videos a mano a los días 11, 13 y 15 de noviembre.

### 2026-11-07 (3): Camila: «Abrieron» y «Tocaron» en 0; remitente propio de las campañas y aviso de Resend, en producción

- La tabla de campañas decía 0 «Abrieron» y 0 «Tocaron». **Causa:** Resend trae el conteo de aperturas y clics
  apagado por dominio y Camila salía del remitente de las facturas (`ventas@dcasapty.com`); encenderlo ahí pondría el
  píxel y cambiaría los enlaces de las facturas. **Decisión** ([CAMILA.md](CAMILA.md) §1d): un subdominio de
  marketing (`novedades.dcasapty.com`, seguimiento `links`) con el conteo encendido; las facturas, limpias.
- **«Remitente de las campañas»** (al final de Camila; Gerencia y administradores; `dcasa_camila.remitente`): vacío =
  el de las facturas (nada cambia hasta que se ponga). El *broadcast* y «Enviarme una prueba» salen de ahí con el
  nombre «D'CASA Panamá» y la respuesta a `info@dcasapty.com` de siempre. El remitente de las facturas no se tocó.
- **El aviso:** con la clave de campañas y en producción, Camila lee `GET /domains` (y el detalle) cada 6 horas con el
  cron, al guardar el remitente, con «Revisar ahora» y al tocar «Enviar». Sin verificar o sin estar en Resend: lo dice
  y **no deja enviar**; con el conteo apagado: «Resend no está contando … de este remitente: Abrieron y Tocaron saldrán
  en 0» con los tres pasos. La pantalla solo lee lo guardado (nunca llama a Resend ni se cae por él); si Resend falla,
  una nota suave. Debajo de la tabla: las enviadas sin conteo siempre dirán 0. La Guía: «¿Por qué Abrieron sale en
  0?». Brian lo dice en `estado_campanas`.
- Pruebas (primero en rojo sobre el código de antes: 3 fallas y 34 errores): `test_remitente.py` (28, dos en el
  navegador: el aviso arriba, la nota, **la pantalla baja hasta el final** en computadora y celular sin scroll de lado,
  Gerencia cambia el remitente) y `test_resend.py` (+1). Todo `dcasa_camila` en base nueva: 238 en verde (en dos
  tandas); la lista blanca de RPC revisada por `odoo-bin shell` (vacía); `ruff` limpio. De `dcasa_guia`, 3 pruebas
  del buscador fallan en esa base angosta porque no tiene `dcasa_nomina` («planilla», «seguro-social»): no es de este
  cambio. Capturas con datos inventados en el scratchpad de la sesión (`capturas_camila_remitente`).
- **Sin push, PR ni despliegue.** Falta de la dueña ([CAMILA.md](CAMILA.md) §6b): agregar y verificar
  `novedades.dcasapty.com` en Resend (DNS en Cloudflare, nube gris), encenderle el conteo con `links`, y poner el
  remitente en Camila. Si la prueba no sale desde el subdominio, la clave de las facturas está limitada a un dominio en
  Resend › API Keys.
- **En producción:** PR #95 (`main` = `848d314`, árbol = `e53e5d8`), **Desplegar 61** sano y confirmado 19:00 UTC
  (versión `e53e5d8b4ebf`) y **Desplegar Juan 11** (`848d314`, que además quita el tope de 20 notas de voz al día a pedido
  de la dueña). La dueña dejó `novedades.dcasapty.com` verificado en Resend con «Auto configure» de Cloudflare y el conteo
  de aperturas y clics encendido en `links.novedades.dcasapty.com`.

### 2026-11-07 (2): issues #24 (Juan) y #25 (Conversaciones), lo que quedaba, en producción

- La dueña aprobó el 2026-11-07 los pendientes de los dos issues, primero lo que ve el cliente. **Sin push, PR ni
  despliegue**: cuando toque, **Odoo primero y después Juan** (Juan no depende del Odoo nuevo; la integración sí espera
  el Odoo nuevo).
- **Juan** (cada uno con su prueba, primero en rojo; `cd juan && npm test`: 1.223, `typecheck` limpio):
  1. **Eco de Messenger e Instagram**: lo que sale se anota antes de enviar (`vuelo:*`); el eco ya no calla al bot 120 min
     (`eco-meta.test.ts`, 4 de 7 en rojo).
  2. y 3. **Notas de voz**: «quiero hablar con alguien» o «no me escriban» en audio valen como escritos; no se transcribe
     ni se lee una imagen en descanso, con un repetido ni pasado el tope diario (`nota-de-voz.test.ts`, 7 de 8). El tope
     de 20 notas de voz por persona al día que entró aquí **se quitó** el mismo día a pedido de la dueña («le agrada que
     pueda responder notas de voz»): queda solo el tope diario general.
  4. **Reintento del turno**: la corrección recibe su ronda de herramientas y la pasada sin herramientas lo consultado; la
     misma escritura con los mismos argumentos va a Odoo una vez por turno, `pasar_a_vendedora` una vez, tope de 8
     (`reintento-del-turno.test.ts`, 4 de 6; y una con el SDK real de Claude).
  5. **Seguimiento**: se reclama antes de redactar y se vuelve a mirar al cliente justo antes de enviar
     (`seguimiento-carrera.test.ts`, 4 de 6).
  6. **Menores**: registros sin claves ni tokens; `{{LECCIONES}}` con función (`menores-ronda8.test.ts`, 3 de 3).
- **Conversaciones** (`tests/test_ronda8_conversaciones.py`, 20 de 23 en rojo antes; Sofía, 2 nuevas en rojo antes):
  atraso máximo de un seguimiento (**ajuste nuevo, 6 h**: lo vencido se salta con una nota, no sale de golpe), nada de
  «¿sigues interesado?» tras un traspaso que nadie atendió (`traspaso_sin_atender_desde`; Sofía lo pone en «Contéstale»,
  que antes NO cubría ese caso), seguimiento por persona (solo el canal por donde escribió último) y «No contactar» que
  sigue a la persona al cambiar de ficha, un «descartado» tardío ya no cierra el ciclo nuevo, notas sin repetir en la
  oportunidad, el mantenimiento purga los borradores de Telegram y la zona con número de casa o apartamento no se guarda.
  En local, base nueva: `dcasa_conversaciones` 1.253 pruebas en dos mitades (solo las 2 referencias visuales a 390 px
  que ya fallaban en esta máquina), `dcasa_sofia` 72, integración real de Juan 39 de 40; `ruff` limpio.
- Cambió una prueba vieja con razón: `test_no_pide_fuera_de_horario_aunque_ya_toque` usa un atraso de 4 h (con 8 h ahora
  se salta) y la integración `seguimiento.ts` espera que el «descartado» no cierre el ciclo nuevo (esperaba el hueco).
- Lo que no cubre: las conversaciones que hoy ya esperan a una persona tras un traspaso no quedan marcadas (sin
  migración: la marca empieza con el próximo traspaso). Quedan del #24 tres menores fuera de lo aprobado.
- **Revisión adversarial** (10 hallazgos, todos arreglados con prueba; `9c00c16` Juan, `dfeb5ee` Odoo y Sofía): un rechazo de
  `pasar_a_vendedora` ya no frena la llamada corregida (tampoco en el mismo paso); el reclamo del seguimiento es de quien lo
  puso y se mira la tabla `seguimientos` justo antes de enviar; las notas de voz y fotos de una vendedora no gastan los topes
  del cliente; prueba de la corrección con Meta. En Odoo: «espera a una persona» frena el seguimiento una semana como mucho, se
  ve en la conversación y se quita con **«Ya la atendí»**; por persona solo cuentan las hermanas que podrían hacer el
  seguimiento (un «hola» por otro canal ya no deja a nadie sin ninguno) y uno en camino por otro canal pospone, no borra;
  solo se salta lo programado antes del límite (`seguimiento_programado_en`: «Crear oportunidad» al día siguiente sale) y,
  si el siguiente también venció en la caída, también se salta (antes salía en la misma vuelta); «el cliente pidió que no lo
  contacten» marca No contactar; la dirección exacta tampoco queda en `brian.accion`; un «Contéstale» descartado no vuelve
  con cada mensaje mientras siga marcada. Pruebas: Juan 1.230 (`typecheck` limpio); Odoo, clases tocadas 125 + API,
  superficie RPC y vecinas 128, 0 fallas (las 3 nuevas de atrasos y Sofía, en rojo antes); `ruff` limpio. No se corrió
  `dcasa_conversaciones` entero ni la integración real de Juan (la integración escribe `seguimiento_proximo` a un minuto:
  no la toca el atraso).

### 2026-11-07 (1): citas, reenviados, reacciones y palomitas en el chat, en producción

- Pedido de la dueña: «El chatbot de D'Casa no tiene citas, reenviados, reacciones ni "entregado/leído"… si un cliente
  dice "este", seleccionando un mensaje… solamente vemos la palabra "este"… no vemos el estado del mensaje.»
- **En la burbuja** ([JUAN_ODOO.md](JUAN_ODOO.md) › «La conversación»): el recuadro de la **cita** sobre el texto (quién
  lo dijo: Tú, Juan, la vendedora o Cliente; dos líneas; «Foto», «Audio»… sin texto; un clic lleva al original;
  «Mensaje que no está en el historial» si es viejo), **«Reenviado» / «Reenviado muchas veces»**, la **reacción** del
  cliente en la esquina (una nueva reemplaza, quitarla la borra) y las **palomitas** (✓ gris, ✓✓ gris, ✓✓ azul, ⚠ «No
  llegó» con el motivo) en vivo, por el mismo bus de siempre (un aviso liviano `recibos`, sin texto ni emoji).
  **«Responder»** en los mensajes del cliente (mouse o Tab; en el celular, dedo apretado): sale citado por WhatsApp
  (`context`) y Telegram (`reply_parameters`); sin id del canal, sale sin la cita.
- **Juan entiende «este»**: lo citado le llega a la IA como `[El cliente responde a este mensaje de D'CASA: «…»]`, un dato
  del cliente (neutralizado, tarjetas tapadas, 300 letras; el cliente no puede escribir la marca) y la regla 6 del prompt
  lo dice. Lo busca en su memoria (ahora cada burbuja guarda su `wamid`) o se lo completa Odoo en la respuesta de
  `/mensaje`. Un reenviado también lo sabe.
- **Datos:** `dcasa.mensaje` con `cita_id`/`cita_id_canal`/`cita_texto`, `reenviado`, `reaccion(_en)`, `estado_canal` y
  sus horas; modelo nuevo `dcasa.mensaje.parte` (el `wamid` de cada burbuja nuestra, su estado y su reacción). Ruta nueva
  `POST /dcasa/juan/v1/eventos` (palomitas y reacciones en tandas). Solo escribe el sistema.
- **Palomitas y reacciones no son mensajes del cliente**: no despiertan a la IA, no pasan por el Durable Object, no
  tocan último mensaje, «sin leer», seguimientos, ventana de 24 h, reparto ni Sofía, y no avisan a nadie.
  **A Meta se le contesta 200 aunque Odoo esté caído** para un aviso de solo palomitas (perder una palomita no es perder
  un mensaje; un 500 haría reenviar el lote por horas): se reintenta lo que cabe en `waitUntil` y lo que Odoo aún no
  conoce se vuelve a mandar a los 5 y 10 s. Los mensajes se siguen guardando antes del 200 (Desplegar 49).
- **Arreglado de paso:** WhatsApp oficial reenviaba la primera burbuja si se caía a la mitad de una respuesta (ahora
  `EnvioParcialError`, como Telegram).
- **Orden de despliegue: Odoo primero y después Juan.** Juan nuevo con Odoo viejo: Odoo ignora los campos nuevos y
  `/eventos` da 404 (Juan no insiste). Juan viejo con Odoo nuevo: igual que antes. Telegram: las reacciones necesitan
  volver a registrar el webhook con `allowed_updates` ([JUAN_CANALES.md](JUAN_CANALES.md) §2). Puente QR y
  Messenger/Instagram: no (el puente no pasa esos datos).
- Pruebas: Juan 1242 en verde (51 nuevas, con las del almacén de la pantalla; contra el código de antes, 44 en rojo y 7 guardianes que ya se cumplían);
  Odoo `test_citas.py` (29) y `test_panel_citas.py` (5 con Chrome: burbuja, «Responder», en vivo, rueda y marca, dedo a
  390 px; más las capturas): 32 de 34 en rojo con el código de antes, todas en verde ahora; el resto de
  `dcasa_conversaciones` en verde salvo las dos referencias visuales que ya fallaban en esta máquina (ver
  CONTEXTO_AGENTICO). Capturas para la dueña en el scratchpad de la sesión (`capturas_citas`), con datos de prueba.
- **Revisión adversarial, arreglada en la misma rama:** S1 «este» citando burbujas distintas ya no es spam (el anti-spam
  compara texto + id citado); S2 un PIN ya no sobrevive dentro de la cita (sin copia si lo citado está en la memoria de
  Juan; `redactar` limpia la copia que vino de afuera); S3 las marcas `[El cliente responde…]` y `[Vendedora]` no se
  imitan con invisibles, espacio duro, ancho completo, cirílicas ni letras delante, y las «» de lo citado pasan a “”; S4
  (Ley 81) Odoo ya no copia lo citado que está en el historial y borrar un mensaje lo limpia de las respuestas y de su
  chatter (la memoria de Juan es aparte: [JUAN_ODOO.md](JUAN_ODOO.md) › Privacidad); S5 un «leído» sube las burbujas y
  los mensajes anteriores (las palomitas azules ya salen en respuestas de varias burbujas); S6 «Responder» es solo el
  ícono en la computadora (el hilo ya no se corre de lado a 768 px); más los menores (tipos en el webhook, reenvío sin cita
  solo con 400 y código 100 o 131009, tandas de 100, *savepoint* por aviso, sin sustitutos sueltos ni bidi, el eco conserva
  la cita, temblor del dedo, horas en vivo, gris 3,8:1). Pruebas: Juan 1300 y `typecheck` (24 nuevas en rojo antes); Odoo
  `test_citas.py` 40 y `test_panel_citas.py` 9 (14 nuevas y 2 cambiadas: 15 en rojo antes), y 443 de las clases vecinas
  en verde salvo las dos referencias visuales a 390 px de siempre.
- **Sigue:** capturas a la dueña → su visto bueno → CI y staging → producción (Odoo y después Juan).
- **En producción (las dos entradas de hoy juntas):** PR #94 (`main` = `6d5dc8b`, árbol = `274f13d`), **Desplegar 60**
  sano y confirmado 06:58 UTC (versión `274f13dff3ee`) y después **Desplegar Juan 10** (`6d5dc8b`). Comentarios en los
  issues #24 (sigue abierto por tres menores) y #25 (cerrado). El contenedor de la sesión se reinició cuatro veces esa
  noche: los agentes se reanudaron o se rehicieron desde lo que dejaron en sus *worktrees* sin perder trabajo.

### 2026-11-06 (9): Camila etapa 1b: la lista de las novedades crece sola (se activa al agregar el correo), en producción

- La dueña vio «0 clientes con permiso» de unos 3,000 y no quiere marcar a nadie de golpe ([CAMILA.md](CAMILA.md) §1c).
  Primero se hizo una pregunta «Sí / No» en cada venta y Juan preguntando por WhatsApp (commit `55a6f4b`); ese mismo
  día la dueña cambió el diseño: «en el momento en el que se añade un correo, ya debe activarse automáticamente».
- **Se activa sola** al crear la ficha con correo, al agregárselo o cambiarlo, con «Guarda sus datos» de Sofía y
  cuando Juan guarda el correo que escribió el cliente: origen honesto «Se activó sola al agregar su correo» (nunca
  «tienda»), con quién; la ficha lo dice hasta que una persona toca «El cliente dijo que sí». Nunca con baja o «no
  contactar» del correo en cualquier ficha, después de un «no», importando, en bloque, instalando, por el sistema
  (`SUPERUSER_ID`), desde la web pública o el portal, y nada hacia atrás. El «no» queda anotado (cuándo, dónde, quién)
  y con él ya no se activa sola.
- **Al confirmar una venta o registrar un pago desde la pantalla**, la casilla sale ya activada con su correo (si el
  cliente dijo que no, se desactiva: queda el «no»); sin correo, «Sí / No» y lo pide. Sale DESPUÉS de confirmar o
  pagar y solo con la marca de los botones: nunca traba la venta ni el pago. No vuelve a salir en 180 días (ajuste
  `dcasa_camila.dias_entre_preguntas`).
- **Juan** nunca las activa: `guardar_correo` (el correo que escribió el cliente; le avisa que le llegarán y que
  puede decir que no) y `no_quiere_novedades` (siempre honra un no). `permiso_correo` en `/mensaje` y `/estado`:
  «activo» o «sin_correo». El pie de cada campaña: «Te llega porque nos diste tu correo en D'CASA. ¿No quieres más?
  Date de baja aquí».
- La pantalla de Camila cuenta por camino. Pruebas: `test_etapa1b.py` (primero en rojo sobre el código de antes) y
  `juan/test/dcasa/permiso-correo.test.ts` (3 de 5 en rojo).
- **Revisión adversarial** (2 que frenaban y varios a arreglar, todos con su prueba): el cron de Sofía ya no vuelve a
  suscribir ni borra un «no» (solo un acto explícito lo borra); la carga del sistema anterior, fusionar fichas,
  empleados, proveedores, el chatter y la creación rápida no activan nada (la activación es **por invitación**: solo
  la pantalla, Sofía y Juan); desmarcar con el correo en el mismo guardado es un «no»; «venía activada» en la venta
  es un origen aparte (nadie le preguntó); `flush_all()` antes de cada savepoint (un error de la venta no se traga);
  el cuadro no se cierra con Escape, el plazo cuenta desde que sale, uno viejo no le gana a un «no», cada quien ve
  solo los suyos y la casilla va en el azul de la marca.
- **Segunda revisión** (nada frenaba; arreglado en la rama, cada uno con su prueba): el enlace «Sí, quiero» después
  de un «no» sí lo anota (es un acto explícito); `cr.flush()` en vez de `env.flush_all()` antes de cada savepoint
  (también los precommit de quien llama); una empresa nueva, un correo con baja o un correo borrado ya no anotan un
  «no» que nadie dijo (en una empresa la casilla es de solo lectura); con un «no» viejo, marcar junto con un correo
  nuevo es un «sí» de una persona; desmarcar cuando el correo solo cambia de mayúsculas es un «no»; Juan recibe
  «sin_permiso» (tiene correo pero no le llegan) para que siempre sepa que un «no» se honra.
- **En producción:** con las dos revisiones adversariales, PR #92 (`main` = `cb541f8`, árbol = `8f3cdc3`), **Desplegar
  58** sano y confirmado 01:03 UTC del 7 nov (versión `8f3cdc322808`) y después **Desplegar Juan 9** (`cb541f8`): Juan
  va después de Odoo porque llama a `guardar_correo` y `no_quiere_novedades`, que un Odoo viejo no tiene. El CI #289
  (sin los arreglos de la segunda revisión) se canceló para relanzarlo completo (CI #290): una sola subida.

### 2026-11-06 (8): «Ver más» en la foto del catálogo y Dependabot, en producción

- Pedido de la dueña: en «Foto del catálogo» había 38 bibliotecas y solo salían 8. Ahora 12 por vuelta y «Ver más»
  trae las siguientes sin repetir (`buscar_catalogo(…, desde=)`, tope 40 por vuelta). Con las actualizaciones de
  Dependabot #7 y #78 a #81 (Juan con el SDK de IA 7 y una prueba que vigila cómo arma la llamada) y la regla de no
  proponer `@types/node` de otra versión mayor.
- **En producción:** PR #88 (`main` = `513b094`, árbol = `3a1c1d3`), **Desplegar 56** sano y confirmado 21:22 UTC
  (versión `3a1c1d3fc144`) y **Desplegar Juan 8** (`513b094`). El **Desplegar 55 falló** por pasar el SHA del *squash*
  como `app_version` (trampa ya escrita; ver CONTEXTO_AGENTICO). Producción nunca dejó de estar sana.
- Un reinicio del contenedor cortó a dos agentes (Camila 1b y Brian) y al vigilante del CI: los *worktrees* guardaron
  todo sin commit y los agentes siguieron donde iban al reanudarlos con un mensaje.
- La dueña aprobó las capturas de Brian («perfecto») y decidió que la casilla de novedades se active sola al agregar
  un correo (la vendedora la desactiva si el cliente dice que no). Las dos cosas siguen en preparación, junto con la
  pantalla de Sofía (después, las tres en producción: Desplegar 57 y 58).

### 2026-11-06 (7): la pantalla de Sofía

- Pedido de la dueña: «Sofía puede mejorar mucho, sobre todo la interfaz visual». **Solo la interfaz**
  (`dcasa_sofia/static/src/`): qué propone, los permisos y lo que hace cada botón no cambiaron. Ver
  [SOFIA.md](../SOFIA.md) › «Cómo se ve y se usa».
- Lo que costaba (capturas «antes»): lo urgente era una etiqueta igual a las demás; cada tarjeta traía 3 etiquetas,
  título, porqué, una caja de texto de hasta 12 líneas y un párrafo repetido de «Le pide sus datos»; en el celular la
  cabecera y 4 filas de filtros llenaban media pantalla; «Descartar» junto al botón principal; el filtro de Gerencia
  por vendedora era una lista sin números; al aprobar la tarjeta desaparecía de golpe y todo subía; vacío y carga eran
  un texto gris; desde «Organizar con Sofía» no se veía nada hasta terminar la revisión.
- Ahora: secciones «Hoy sin falta» (azul) / «Hoy» / «Cuando puedas» con su número y un resumen arriba; filtro por tipo
  y (Gerencia) por vendedora con conteos cruzados, al lado en la computadora y en una tira pegada arriba en el celular;
  tarjetas compactas con el mensaje como burbuja y «Editar»; la acción principal grande; «Ver la oportunidad» y
  «Descartar» (sin confirmación, como siempre) abajo y aparte; al aprobar la tarjeta dice lo que pasó en su lugar y del
  mismo alto, y se cierra despacio; «Todo al día» y «Listo por aquí» con «Ver todo»; esqueleto al cargar y, desde el
  CRM, primero lo que ya había y la revisión encima. Baja con la rueda y con el dedo.
- Pruebas: `test_sofia_pantalla.py` (nuevo, 9; la rueda y el dedo por el protocolo de Chrome) y las de navegador
  ajustadas a «Editar»: 70 en verde en base limpia (68 de Sofía y `dcasa_interfaz` › `TestInicioScroll`). Capturas
  `antes_…`/`despues_…` en el scratchpad de la sesión (`capturas_sofia`), con datos de prueba. **Sin push ni
  despliegue**: falta que la dueña vea las capturas. *(Después: le gustaron, «Descartar» queda sin confirmación y está
  en producción con Desplegar 57.)*
- Aprendido: el minificador de Odoo (`rjsmin`) aprieta los espacios de una plantilla `` `…` `` anidada dentro de
  `${…}` («p. m.(la pidió»); hay tres casos viejos en Conversaciones (tarea aparte). Ver CONTEXTO_AGENTICO.

### 2026-11-06 (6): Brian al día

- Pedido de la dueña: «Brian es indispensable, pero está desactualizado». **Auditoría** de lo que entró desde octubre
  (función → ¿Brian la consulta o la hace? → herramienta):

  | Función | Antes | Ahora |
  |---|---|---|
  | Sofía: propuestas, «Revisar ahora», «Guarda sus datos» | falta | `propuestas_de_sofia` (dice qué dato dio, no el dato), `revisar_con_sofia` (construcción), `abrir_pantalla` |
  | Conversaciones: Resumen (tasa de cierre, ventas atribuidas, primera respuesta) | falta | `resumen_de_conversaciones` |
  | Reparto y vendedoras activas | falta | `reparto_de_conversaciones` (la vendedora, solo lo suyo) |
  | Cotizaciones del chatbot y la web que vencen solas | falta | `cotizaciones_que_vencen` |
  | Origen Chatbot / Web / Vendedora | falta | `buscar_ventas(origen)`, y `ver_venta` y `ver_factura` lo dicen |
  | CRM de las conversaciones | `oportunidades_abiertas`, `resumen_del_crm` | igual |
  | Valor del inventario y cobrado por forma de pago | `valor_del_inventario`, `ventas_por_dia` | igual |
  | Clientes repetidos y fusionar | solo «buscar antes de crear» | `clientes_repetidos` (lee y dice cómo unir; no fusiona) |
  | Envíos | `cotizar_envio` | igual |
  | Camila | `estado_campanas` | igual (aprobar y enviar, en su pantalla) |
  | Correo a clientes | enviar factura y cotización | + `estado_del_correo` (si sale, por qué no, la cola) |
  | Meta: catálogo, píxel y ventas | falta | `estado_de_meta` (nunca la clave) |
  | Abonos | `abonos_por_vencer`, `ver_factura` | igual |
  | Nómina, bodega y existencias | adelantos, comprobantes, mermas, bitácora, entregas, movimientos | igual |
  | Marketing | `movimiento_de_productos`, `fotos_que_faltan` | igual |
  | La Guía | `buscar_en_guia` (293 letras: pasaba el tope sin que la prueba lo viera; solo decía la ruta de las pantallas propias) | < 260 letras y botón «Abrir» también a pantallas propias |
  | Pantallas propias | `abrir` solo abría listas y registros | `abrir_pantalla` (con los permisos del menú) |

  Lo que Brian «sabía» en texto: su prompt no mencionaba a Juan, Sofía ni Camila; `ayuda` tampoco; BRIAN.md tenía la
  tabla de niveles rota (y «mover stock» como construcción: es sensible), decía «botón en todas las pantallas» (en el
  celular va arriba) y que nada más salía por Telegram (salen también las claves de descuento, las alertas de bodega
  y el resumen de Sofía); MODULOS.md decía 70 herramientas (eran 99; ahora 105). Todo corregido.
- **Nada escribe dinero** (issue #26): todo es de lectura menos `revisar_con_sofia`, que solo deja propuestas. Las de
  Sofía y Meta viven en `dcasa_brian` (esos módulos no son dependencia: si faltan, lo dicen; `dcasa_sofia` lo trabajaba
  otro agente); las de Juan, en `dcasa_conversaciones`; la del correo, en `dcasa_correo`. La prueba del contrato de los
  modelos pequeños ahora revisa todas las categorías. La Guía trae la pregunta lista para Brian en 10 tareas más.
- **Arreglo visual:** en Conversaciones (computadora) el botón flotante tapaba «Enviar» y «Nota interna». Ahora, mientras
  el botón se ve, la caja deja libre su esquina, la ficha del cliente termina su scroll por encima del botón y las
  pantallas propias con scroll terminan con un espacio libre (SCSS de `dcasa_brian`, con `body:has(...)`; no se
  tocaron los otros módulos). Prueba de navegador por geometría (`test_boton_no_tapa.py`, 1366 y 1024 px). Medido en
  1024, 1280 y 1440 px en Conversaciones (con y sin ficha), Sofía, Camila y Envíos: nada se cruza. Capturas antes y
  después en el scratchpad de la sesión (`capturas_brian`).
- El contrato visual de Conversaciones (`test_panel_visual.py`) ya escondía el botón de Brian; ahora le pone además
  `o_brian_oculto` (la clase del panel abierto) para que la foto salga sin la reserva: las referencias no cambian.
- Pruebas en local, base limpia con los 30 módulos de producción: `/dcasa_brian`, `/dcasa_base`, `/dcasa_guia`,
  `/dcasa_sofia`, `/dcasa_camila`, `/dcasa_envios` y las de Brian, el origen y la interfaz de Conversaciones y del
  correo: 987 pruebas, 2 fallas ajenas (las referencias de «lista» y «conexiones» a 390 px, que ya fallaban en esta
  máquina) y 2 de la prueba nueva por un selector («Cliente» también estaba en el nombre de la conversación de
  prueba), corregido y en verde (3 de 3). `ruff check addons scripts` limpio.
- La dueña vio las capturas y dijo que sí. **Revisión adversarial** independiente: nada que frene; 6 arreglos, cada
  uno con su prueba: `revisar_con_sofia` corre en una transacción corta y propia (dentro del turno de Brian tomaba el
  candado de Sofía hasta 150 s) y llama directo a la revisión, sin armar la pantalla; `propuestas_de_sofia` ya no
  manda el título de «Guarda sus datos» (traía el nombre, el correo y el cumpleaños; la prueba ahora lo arma Sofía de
  verdad); las cuentas de la revisión, solo a Gerencia (a la vendedora, las suyas); `abrir_pantalla` nunca abre una
  acción de servidor ni un enlace; `cotizaciones_que_vencen` y `estado_del_correo` marcadas como texto de clientes;
  fechas de Meta y del correo en hora de Panamá.
- **En producción:** PR #91 junto con la pantalla de Sofía, **Desplegar 57** (`b261ec6`, sano y confirmado).

### 2026-11-06 (5): Camila etapa 2 («a lo grande, todo conectado con todo»), en producción

- Decisiones de la dueña del mismo día ([CAMILA.md](../CAMILA.md) §1b): **el tope de 15 días es por cliente** (por correo;
  registro `dcasa.camila.destinatario` escrito antes de mandar y borrado si Resend no la mandó) y puede haber **varias
  campañas** (la migración `19.0.2.0.0` borra el índice de «una abierta»); **Juan sabe que el cliente vino del correo**
  (`campana_correo` en `/mensaje` y `/estado`, su prompt lo usa; etiqueta «Vino del correo» y la cotización con
  «Vino del correo: DCN-… · asunto»); **el correo puede llevar los dos botones** (WhatsApp y «Visita nuestra tienda en
  línea»; «CTA único» es del sitio) con UTM `correo/email/DCN-…` y las redes del sitio al pie (opcional).
- Pantalla: constructor a todo el ancho, «Previsualizar» en su ventana (celular o computadora), «Cambiar»/«Agregar»
  en una ventana con buscador, filtros y tarjetas, «Escribir con IA» por producto y desde la idea (con «Reintentar»
  junto al producto si falla), «Sugerir productos», chips del CRM con su número y los que quedan fuera, «Nueva
  campaña» por tema y «Crear campaña con estos» en el tablero de Marketing. Resultados: ventas en la web por UTM.
- Segmento: uno solo de envío, reusado (el plan gratis de Resend Marketing tiene 3 segmentos y 1,000 contactos), una
  campaña a la vez, se espera si la anterior sigue saliendo; las bajas se leen de todos los contactos.
- Pruebas: `test_etapa2.py` (nuevo) y las de navegador (7), más `juan/test/dcasa/campana-correo.test.ts`. Capturas en
  el scratchpad de la sesión (`capturas_camila2`); la dueña las vio y dijo que sí.
- **Revisión adversarial (mismo día), 11 hallazgos arreglados**, cada uno con su prueba en `test_revision2.py` (todas en
  rojo sobre `49e5f87`): el turno de envío es un candado de **sesión** que aguanta los COMMIT y se suelta siempre (dos
  campañas ya no tocan el segmento a la vez) y el segmento se limpia por tandas; las enviadas de la etapa 1 cuentan
  para el tope (post-migración); el registro no se suelta si se llamó a «send» (`envio_intentado`) ni por `canceled`, y
  registra a todos los del segmento; «todavía saliendo» mira todas; un 404 de Resend no traba nada; el reintento no
  manda precios viejos; el tope de IA por persona; «Vino del correo» no se escribe por RPC; la revisión de marca más
  dura; Marketing no lee quién llegó por el correo. **Sin push ni despliegue** de esta sesión.
- **En producción** con el «sí» de la dueña a las capturas: Desplegar 54 y Desplegar Juan 7, sano 19:07 UTC (PR #87,
  `main` = `3195d7d`, árbol = `3fb5770`; imagen `sha256:29309f79…` de CI #280). Antes, una revisión adversarial
  independiente: 1 alta (dos campañas a la vez), 4 medias y 6 bajas, todas corregidas con su prueba.

### 2026-11-06 (4): Camila, la asistente del mail marketing (módulo nuevo `dcasa_camila`, etapa 1)

- Con las decisiones de la dueña del 2026-11-06 ([CAMILA.md](../CAMILA.md)):
  el **permiso** del cliente en su ficha (casilla de la vendedora, enlace firmado «Sí, quiero» al pie de la factura y
  la bienvenida, y el correo que dio a Sofía si el mensaje enviado decía «promociones»; la baja es final) y
  **Marketing › Camila**: borrador con productos en tienda, con foto y publicados, el precio de la tienda en línea, el
  texto de la IA de Brian con revisión de marca, vista previa en el celular, prueba solo al equipo y «Enviar a N
  clientes» por **Resend Broadcasts** con su propia clave (`RESEND_CAMPANAS_API_KEY`, Full access). Una cada 15 días;
  staging nunca envía. Resultados: chats con la marca de la campaña, sus ventas y aperturas y clics de Resend. Brian:
  `estado_campanas`. La pantalla baja con scroll (prueba de navegador).
- Decisión técnica a confirmar con la dueña: abrir el enlace «Sí, quiero» no anota nada (los filtros de correo abren
  los enlaces solos); el «sí» queda al tocar el botón de la página (dos toques).
- Revisión adversarial (mismo día), 12 hallazgos arreglados, cada uno con su prueba (`test_revision.py`, primero en
  rojo): la baja se mira **por correo** en cualquier ficha (repetidas, archivadas, hijos; también «no contactar»); el
  «Sí, quiero» solo a la ficha firmada en la factura y la bienvenida que arma `_postear` (no a un contacto hijo, ni el
  asistente, ni el recordatorio) y con interruptor de Gerencia; Sofía solo con el mensaje que salió y la frase de la
  plantilla; el permiso es **del correo** (`dcasa_promos_correo`); el segmento se limpia por id y se revisa antes de
  mandar; una aprobada trabada la descarta Gerencia; la casilla una ficha a la vez y desmarcar no es la baja; revisión
  de marca más dura; tokens raros sin 500; tope a las pruebas; bajas de los resultados; la marca solo en el primer
  mensaje desde la campaña.
- Corrida completa en local (todos los módulos): 4744 pruebas, 3 fallas ajenas a Camila: el contrato visual de Juan a
  390 px («conexiones», la diferencia de Chromium ya conocida, y «lista», cuya referencia quedó vieja desde el PR #69)
  y `test_cabecera_con_la_pagina_abierta_desplazada`, que sola pasa (carrera de `is-ready`, ver contexto agéntico).
- **En producción** con su autorización («tan pronto esté todo pásalo a producción»): Desplegar 52, sano 11:27 UTC
  (PR #85, `main` = `0d699995`, árbol = `b84e57d`; imagen `sha256:dfbf424f…` de CI #276). No envía nada hasta que
  exista la clave de campañas y alguien apruebe la primera campaña. Sigue: que la dueña vea la pantalla, cree la
  clave (§6 de CAMILA.md) y confirme el «Sí, quiero» de dos toques. Etapa 1b: que Juan pregunte el permiso por
  WhatsApp (no se tocó `juan/`).

### 2026-11-06 (3): la varita mágica («Sugerir») escribe siempre, o dice por qué y deja reintentar

- Pedido de la dueña: «a veces sí, a veces no» escribe el borrador, en el chat y en «Guardar y responderle» de Sofía.
  Sin acceso a producción; cada causa se reprodujo con una prueba que fallaba sobre el código de antes:
  1. **Plazos que no encajaban:** Odoo esperaba 25 s y el Worker no tenía plazo (Meta razona y consulta hasta 6 veces),
     así que Odoo se rendía («el Worker no responde») mientras la IA seguía y se pagaba. Ahora el Worker contesta
     siempre antes de 42 s (`PLAZO_TOTAL_MS`; el primer intento usa hasta el 60 % y deja tiempo al modelo rápido) y Odoo
     espera 55 (`TIMEOUT_SUGERIR`); una prueba del Worker lee la línea de Python y exige el margen.
  2. **Sin reintento** con el tope de gasto alcanzado (un solo modelo) y **sin salida** cuando el modelo gastaba sus
     pasos consultando sin escribir. Ahora: un reintento ante falla pasajera (red, 429, 5xx; no ante una clave mala) y
     «escribe ya con lo que consultaste». La IA de respaldo sin clave no se intenta y el error lo dice.
  3. **La revisión de la marca** dejaba el borrador vacío por una frase: una cifra que ya había dicho la tienda en la
     conversación contaba como inventada. Ahora cuenta (como en el bot; la del cliente sigue sin contar) y, si al quitar
     lo dudoso no queda nada con sentido, el modelo lo corrige una vez con el motivo. Además, una frase copiada del prompt
     pasaba entera con el aviso «Quité información interna»: ahora se quita.
  4. **La pantalla:** el error era una notificación que se iba sola (por eso no había «mensaje exacto»); si la vendedora
     cambiaba de chat mientras Juan escribía, **el borrador caía en la caja de otra clienta**; y lo que tecleaba
     mientras esperaba se pisaba. Ahora el estado de «Sugerir» es de cada conversación, la caja dice «Juan está
     escribiendo…» y, si no llega, la causa en corto con **Reintentar**. En Sofía, datos guardados, chat abierto y el
     mismo aviso.
- Registro sin datos personales: `[juan] sugerir {conversacion, resultado, ms, modelo, intentos, respaldo}` en el Worker
  y «Juan: «Sugerir» sin borrador (conversación N, causa X, N ms, HTTP N)» en Odoo.
- Pruebas: 16 nuevas del Worker (14 fallaban antes), 10 nuevas de Odoo (todas fallaban antes; 4 en el navegador) y 6
  ajustadas al contrato nuevo. Capturas con el Worker de mentira (fuera del repositorio).
- **En producción** con su autorización («tan pronto esté todo pásalo a producción»): Desplegar 51 y Desplegar Juan 6,
  sano 09:13 UTC (PR #84, `main` = `237d2f3`, árbol = `a307425`; imagen `sha256:f0b0b240…` de CI #274). Lo de la dueña:
  `ANTHROPIC_API_KEY` en `dcasa-juan` (sin ella, si Meta falla no hay respaldo).

### 2026-11-06 (2): la calculadora de envíos en el menú Envíos (módulo nuevo `dcasa_envios`)

- Pedido de la dueña: poner el HTML de envíos del 4 nov en el menú «Envíos», con el scroll que funcione, y dejar el
  código listo para que mañana el cliente cotice su envío en la web:
  Envíos › **Calculadora** (todos), **Lugares** (todos; edita Gerencia) y **Tarifa** (Gerencia), «En desarrollo» apagado.
  Ver [ENVIOS.md](../ENVIOS.md).
- **Un solo motor** en Python puro (`addons/dcasa_envios/motor/`, sin Odoo): la fórmula y el buscador portados del
  HTML. Paridad medida en local con los datos reales: 945 de 946 comparaciones iguales (la diferencia: buscar
  «constructor» rompía el HTML). En el repositorio solo un fixture sintético con sus esperados sacados del JavaScript.
- **Los datos no están en el repositorio** (público; la dueña no dio su «sí»): Gerencia sube `envios-dcasa.html` en
  Envíos › Tarifa. La carga es idempotente (11 299 lugares en ~2 s; volver a cargar, 0 nuevos), respeta lo de Odoo y la
  tarifa nace y vuelve «en revisión». Brian: `cotizar_envio`. Guía: «Saber cuánto cuesta un envío» y «Cambiar o
  aprobar la tarifa de envíos». Sin ruta pública todavía (pasos para encenderla en ENVIOS.md); Juan no cotiza.
- La dueña vio las capturas (con datos reales, fuera del repositorio) y dijo que sí; bajar la lista a Excel «es
  innecesario» (no se agrega). **En producción** con su «sí» («pásalo a producción cuanto antes»): Desplegar 50, sano
  07:47 UTC (PR #83, `main` = `e924a9c`, árbol = `3682053`; imagen `sha256:53e76dc6…` de CI #272; CI #271 falló por la
  descripción de `cotizar_envio`, de más de 260 letras). Sigue: que Gerencia cargue el archivo en Envíos › Tarifa y
  apruebe la tarifa (redondeo, viático, honorarios, peaje).

### 2026-11-06 (1): limpieza y mantenimiento; WhatsApp guarda antes de contestar; Camila (diseño)

- Pedido de la dueña: «limpieza y mantenimiento... revisar y auditar, actualizar el repositorio y la documentación»; y
  que el código quede bien documentado «para ser clonado e implementado en otras empresas». Aprobó todo lo propuesto.
- **En producción** (Desplegar 48, sano 03:56 UTC; PR #77): sin costos de compra en el repositorio público (y una
  prueba que lo impide), código sin usar fuera, el «hoy» de Brian en hora de Panamá, avisos de seguridad de Juan
  (undici, zod) y del borde, Dependabot también para Juan y el puente, ruff fijado, la guía para otra empresa
  ([REPLICAR.md](../REPLICAR.md) y `docs/replicar/`) y la **versión estable 3**, ensayada en staging (el primer ensayo de
  volver que se hace).
- **WhatsApp oficial** (Desplegar 49 y Desplegar Juan 5, sano 05:59 UTC; PR #82): el webhook guarda el mensaje en el
  Durable Object antes de contestarle 200 a Meta; una alarma atiende a los 2 minutos lo que el Worker no alcanzó, en
  orden y sin contestar dos veces; «Borrar mis datos» suelta lo que estaba en curso; de lo recibido queda solo una
  huella SHA-256 del id (el `wamid` lleva el celular). Revisión adversarial: 6 hallazgos, corregidos con pruebas.
- **Documentación unida:** lo viejo a `docs/historico/`, Juan en 3 documentos, una sola receta de producción
  ([DESPLIEGUE.md](../DESPLIEGUE.md)), bitácora corta, PRIORIDADES con una sola lista y sin datos de personas.
- **Camila** ([CAMILA.md](../CAMILA.md)): el jefe propuso cuatro nombres para futuras herramientas (Daniela, Camila,
  Alejandra, Andrés). La dueña eligió **Camila para el mail marketing y la página web**, empezando por el correo: una
  campaña cada 15 días, con el precio real de Odoo, por el servicio de campañas de Resend (aparte de las facturas). Los
  otros tres nombres quedan reservados. Todavía no hay código.
- La dueña también contó: la varita mágica («Sugerir») a veces no escribe el borrador, en el chat y en «Guardar y
  responderle»; Brian está desactualizado; la pantalla de Sofía puede mejorar. Quedaron en PRIORIDADES.
- La puerta del equipo `/master` sigue sin fecha (la dueña decide cuando el equipo se adapte).

### 2026-11-05 (4): «Guardar y responderle»

- Pedido de la dueña con un caso real (la clienta dio sus datos; la ficha se completó, pero faltaban «las gracias y la
  oportunidad de cierre»): la tarjeta «Guarda sus datos» ofrece **«Guardar y responderle»** (guarda, abre su chat y la
  caja pide a Juan un borrador con el mismo «Sugerir» del chat, una sola vez; no se envía nada) y **«Solo guardar»**.
  Sin la ventana de 24 h de Meta o si pidió que no lo contacten, solo guardar; nunca se guarda a medias. También lee
  el cumpleaños con el año pegado («7 de marzo deln1990», el mismo caso real). 64 pruebas de Sofía.
- **En producción** con su visto bueno: Desplegar 47, sano 21:45 UTC (PR #76, `main` = `700c34a`, árbol = `e97958e`;
  imagen `sha256:aa3c4c06…` de CI #260). Juan no cambió.

### 2026-11-05 (3): Sofía baja con scroll; «Guarda sus datos»

- **Scroll de Sofía** (pedido de la dueña: «la ventana no hace scroll»): `.o_action` de Odoo cortaba la pantalla; ahora
  lleva la regla fuerte como el Inicio. Una prueba nueva (`dcasa_interfaz/tests/test_scroll.py`) exige esa regla a toda
  pantalla propia. **En producción**: Desplegar 45, sano 18:27 UTC (PR #74, `main` = `91507ca`, árbol = `63bcdef`;
  imagen `sha256:32b31395…` de CI #256; el staging del CI se frenó por un 429 de R2 y salió con Desplegar 44).
- **«Guarda sus datos»** (pregunta de una vendedora y pedido de la dueña): cuando el cliente contesta su nombre, correo
  o cumpleaños (a Sofía, a una vendedora o a Juan), «Revisar ahora» propone una tarjeta con todo; la vendedora lo
  revisa, lo corrige si hace falta y toca «Guardar en su ficha». Nunca crea fichas, no pisa lo bueno, no repite el
  correo de otra ficha, guarda con nuestro formato y deja nota en la ficha. A quien ya se le pidieron los datos en el
  chat no se le vuelven a pedir. Revisión adversarial: sin huecos de permisos; se corrigieron lecturas falsas (frases
  como nombre, fechas de entrega como cumpleaños, mensajes que no piden datos) y lo demás (docs/SOFIA.md). 60 pruebas
  de Sofía en verde (dos en el navegador). Con el visto bueno de la dueña y un caso real que ella mandó (el cliente
  saludó, luego dio su nombre y luego su correo: la primera versión solo leía la primera respuesta), Sofía lee ahora
  las primeras 4 respuestas al pedido. **En producción**: Desplegar 46, sano 19:47 UTC (PR #75, `main` = `42f379c`,
  árbol = `cbaff7a`; imagen `sha256:14f3fe34…` de CI #258). Sigue: que la vendedora toque «Revisar ahora» y guarde los
  datos de los clientes que ya contestaron; mirar con la dueña las primeras tarjetas.

### 2026-11-05 (2): Sofía, la asistente del CRM (módulo nuevo `dcasa_sofia`)

- Decisiones de la dueña: **propone y una persona aprueba**; **con un botón y cada mañana**; **Gerencia todo, cada
  vendedora lo suyo** (resumen por Telegram); nombre **Sofía**. A media sesión pidió además la **campaña de datos**: a
  tibios y calientes sin nombre de verdad (emoji, frase, empresa, solo un nombre) o sin correo, un mensaje profesional
  que pide nombre y apellido y correo (promociones, Socios, cumpleaños).
- Hecho (docs/SOFIA.md): CRM › Sofía y «Organizar con Sofía» en el tablero y la lista del CRM; contestar, cotización
  que vence, escribirle, pedir sus datos, guardar el correo del chat, llamar (24 h de Meta), repartir y poner a su
  vendedora (Gerencia). Plantillas editables (CRM › Configuración › Sofía), sin cifras; ajustes en Ajustes de Juan. No
  toca a Juan: revisar no escribe; se aparta si Juan conversa o está por mandar su seguimiento (2 h).
- Revisión adversarial: sin huecos de permisos; se arregló un posible **doble envío** (enviar confirma la base a mitad de
  la petición), la revisión al aprobar, el texto del chat de un solo uso y lo demás (ver docs/SOFIA.md). 43 pruebas.
- **En producción** con el visto bueno de la dueña: Desplegar 43, sano y confirmado 05:26 UTC del 5 nov (PR #73,
  `ff2ddd3`; imagen `sha256:2003322b…` de CI #254). `dcasa_sofia` está en `ODOO_MODULES` (docker/entrypoint.sh) y en
  el Makefile. Sigue: que Gerencia ajuste los mensajes y cada vendedora vincule su Telegram; la primera revisión de la
  mañana corre sola media hora después de abrir.

### 2026-11-05: tasa de cierre en el Resumen de Juan; idea del agente del CRM

- Pedido de la dueña: en el Resumen, ventas cerradas ÷ conversaciones × 100 (el asistente y una persona, solo el
  asistente y el total), en el periodo elegido y en una tabla con hoy, 7, 30 y 90 días y 12 meses. **En producción:**
  Desplegar 42, sano y confirmado 02:12 UTC del 5 nov (PR #72, `57d718b`; imagen `sha256:d02db548…` de CI #252).
- Pidió también un **agente aparte para el CRM** (como Brian lo es de Juan): con un botón analiza, reparte, actualiza
  etapas y propone seguimientos. En diseño: se le presentan opciones antes de construir.

### 2026-11-04: tarifas de envío (propuesta, en pausa) y clientes repetidos (buscar por celular, «Es esta persona»)

- **Tarifas de envío (en pausa hasta que Gerencia apruebe):** fórmula con los tres precios de la dueña ($15 cerca, $20 a
  15 km, $90 a Colón = $6.13 + $0.925/km, mínimo $15, redondeo a $5 por decidir). La extensión de Chrome midió 482
  corregimientos hasta 300 km en Google; barrios, urbanizaciones, PH y lugares conocidos de La Chorrera, Arraiján,
  Panamá y San Miguelito salieron de OpenStreetMap y GeoNames (11 299 lugares) con km del calculador de rutas de OSM
  ajustados a Google. Se le entregó a la dueña **un HTML propio** (`envios-dcasa.html`: buscador por sinónimos, frases y
  lugares conocidos; viático, honorarios y peaje que Gerencia llena; ajuste proporcional; agregar lugares; copia con
  ajustes y lista para Excel). **No está en el repositorio** (el repo es público y no dio su «sí»); la matriz y los
  scripts vivían en el scratchpad de esta sesión. Sigue: que Gerencia apruebe; después, la sección de envíos del sitio
  y que Juan calcule.
- **Clientes repetidos (pedido de la dueña):** las vendedoras creaban otro cliente con otro número porque el celular ya
  existía (lo guardó el chat con la frase de su perfil) y solo salía «Ese celular ya está registrado». Ahora: el
  selector de «Cliente» encuentra el celular de cualquier forma y lo muestra junto al nombre; los datos del cliente se
  corrigen dentro de la cotización y la factura borrador (solo lo que cambió va a su ficha); al crear, «Ya existe esta
  persona» con su ficha y el botón **«Es esta persona»**. Revisión adversarial: 1 alta (cada cotización nueva
  reescribía la ficha) y 5 medias o bajas, todas corregidas con pruebas; en el arreglo apareció otra (un solo inverso
  borraba los datos no tocados) que atraparon las pruebas nuevas. Ver `docs/CONTACTOS.md`.
- **En producción** con su «sí» («pásalo a producción cuanto antes»): Desplegar 41, sano y confirmado 22:04 UTC del
  4 nov (5:04 pm Panamá) (PR #71, `23026ec`; imagen `sha256:0dde5051…` de CI #250 sobre `43a105d`; staging en
  Desplegar 40 porque el del CI se frenó en el respaldo previo). Juan no cambió.
- Sigue: que la dueña y las vendedoras lo prueben con un cliente real del chat; la decisión de Gerencia sobre las
  tarifas de envío.

### 2026-11-03 (tarde y noche): tres paneles en el Inicio, CRM al chat, vendedoras activas, notas de voz y fotos

- Pedidos de la dueña (con capturas de producción): (1) el Inicio con tres paneles para no revolver: cotizaciones en
  tienda, del chatbot y la web, y entregas; (2) el CRM abría con «Mi flujo»; (3) los turnos rotan y una vendedora que
  no vino seguía «disponible» y Juan le pasaba clientes (al retomar, se los pasaba a otra igual de ausente); (4) las
  notas de voz salían como «adjunto 45 KB» sin reproductor; (5) mandar fotos de varios productos sin que se cierre la
  ventana; (6) del CRM y de Contactos al chat; (7) cómo se limpian los chats.
- Decisiones (preguntadas con opciones): vendedoras = **«conectada + pasa a otra»** (30 min de actividad, 15 min sin
  contestar, ambos en Ajustes de Juan); chats viejos = **dejarlo como está** (una conversación por cliente y canal, la
  lista carga de 30 en 30, nada se borra solo).
- Causa de las notas de voz: WhatsApp manda `audio/ogg; codecs=opus`; `mime_seguro` rechazaba el `;` y Odoo, sin
  libmagic, no reconoce OGG → `application/octet-stream` «adjunto». Arreglo, respaldo al leer y migración `19.0.1.3.0`
  (solo WhatsApp y Telegram).
- Revisión adversarial (tocaba a quién se le asignan los clientes): 1 alta (el cron le quitaba el cliente a quien ya
  contestó si el cliente decía «ok, gracias», y le decía a Gerencia que no contestó) y 8 medias o bajas; todo corregido
  con el campo `dcasa.conversacion.reparto_desde` y pruebas. Además, el «ya avisé a una vendedora» de Juan queda como
  último mensaje: el cron no mira quién escribió último.
- **En producción:** Desplegar 39, sano y confirmado 01:08 UTC del 4 nov (8:08 pm Panamá) (PR #70, `50b52c6`, imagen `sha256:a167a596…` de CI #247; staging en Desplegar 38
  porque el del CI se frenó en el respaldo previo con staging dormido). Juan no cambió (sin Desplegar Juan).
- Sigue: que la dueña lo vea de verdad (Inicio, CRM, una nota de voz nueva, «Elegir» fotos, Reparto); prender el Reparto
  «Parejo» si todavía no (la regla de actividad y «pasar a otra» solo corren con el reparto encendido); Telegram de cada
  vendedora para que les lleguen los «Te tocó a ti».

### 2026-11-02 (tarde) y 2026-11-03 (madrugada): Juan en el WhatsApp de la tienda, medios en el chat, origen y cotizaciones que vencen

- **Juan atiende el WhatsApp de la tienda (+507 6026-1919) por la API oficial de Meta** desde las 20:26 UTC del 2 nov
  (3:26 pm Panamá). Lo hizo la dueña desde su cuenta, guiada paso a paso: app «D'CASA Juan», webhook
  `https://dcasa-juan.dcasapty.workers.dev/webhooks/whatsapp-cloud`, token de verificación y clave secreta de la app
  como secretos del Worker `dcasa-juan`, `WHATSAPP_PHONE_NUMBER_ID` del número de la tienda, «Suscribirse a webhooks»
  solo en la tarjeta del 6026-1919 (no en la del número de prueba +1 555) y **llave permanente** de un usuario del
  sistema `juan-bot` (Administrador; app y cuenta de WhatsApp con control total; caducidad «Nunca»; permisos
  `whatsapp_business_messaging` y `whatsapp_business_management`) en `WHATSAPP_CLOUD_TOKEN`. La llave del Explorador de
  la API Graph vence en 1-2 horas: nunca se deja puesta.
- **Modelo «contributor» de Meta para Juan** (`muse-spark-1.3-contributor`, se escribe en Ajustes de Juan › modelos):
  el mismo modelo, Meta puede entrenar con las conversaciones, 92-98 % más barato; límite de 150 consultas por minuto
  **para todo el equipo de Meta** (incluye otros proyectos de la cuenta). Precio real $0.10 entrada / $0.002 caché /
  $0.20 salida por millón de tokens; la dueña puso **el doble a propósito** (0.20 / 0.004 / 0.40) como margen, así que
  «Costos de IA» muestra el doble de lo real (~$2 por 1000 respuestas en vez de ~$1). Lo gastado antes con
  `muse-spark-1.3` queda estimado (no se recalcula). Meta no separa el gasto por clave.
- **En producción:**
  - Desplegar 35 (PR #67, `d285ee7`): la política de privacidad nombra a Juan y al modelo contributor (Ley 81) y Juan
    da `https://dcasapty.com/shop` cuando piden el catálogo completo.
  - Desplegar 36 (PR #68, `b9ded11`) y Desplegar Juan 4 (`14be013`): notas de voz y videos con reproductor en el chat,
    stickers como imagen (Juan no los mira ni los anota), columna de conversaciones ajustable (arrastrar, teclado,
    doble clic; se recuerda) y **Origen** Chatbot / Web / Vendedora en cotizaciones y facturas (columna, filtros,
    agrupar e Inicio). Las fotos no se veían porque a `dcasa-juan` le faltaba la variable de texto `URL_PUBLICA`
    (`https://dcasa-juan.dcasapty.workers.dev`, sin `/` final); la dueña la puso y `/salud` de Juan ahora la marca.
  - Desplegar 37 (PR #69, `594522c`, sano y confirmado 06:10 UTC del 3 nov): **«Sin leer» = lo que espera a una persona** (conversación en manos de una
    persona y el último mensaje es del cliente; la vendedora ve las suyas y las sin asignar, Gerencia todas): «N
    esperan» y chip «Esperan respuesta». **Las cotizaciones del chatbot y de la web vencen solas** (Ajustes de Juan,
    «Días que queda abierta una cotización…», 3 por defecto, 0 apaga, máximo 60; cron cada hora; no toca las de
    vendedora ni las que tienen pago en curso, factura, apartado, bloqueo o un cambio de hace menos de 12 h; al
    reabrirla con «Establecer como cotización» toma días nuevos). **Ventas atribuidas en tres** (solo el asistente /
    el asistente y una persona / solo personas) con ventana de 30 días antes de la factura y periodos de 90 días y
    12 meses.
- Revisión adversarial de la tanda del PR #69 (toca dinero y permisos): una cotización reabierta se volvía a cancelar a
  la hora (bloqueante), fechas en hora de Panamá, apartados, carritos vivos de la tienda, pedidos web copiados que
  heredaban el sitio, filas saltadas que trababan la corrida, mensajes programados que contaban como respuesta, SQL lento
  y cotizaciones de Juan fuera de la ventana. Todo corregido con pruebas antes de staging. CI #243 salió rojo por la
  lista blanca (`create` y `action_draft` de `sale.order`); CI #245 verde.
- Sigue (de la dueña): prender el **Reparto «Parejo»** (Gerencia) para que Juan asigne clientes; que cada vendedora
  conecte su Telegram; `ANTHROPIC_API_KEY` en `dcasa-juan` como respaldo si Meta pasa el límite (hoy el cliente
  recibiría «una vendedora te atiende»); una alerta de gasto en Meta; plantillas para escribir después de 24 horas.
  Después de Desplegar 37: mirar «N esperan», el reparto en tres del Resumen y el ajuste de días.

### 2026-11-02: Valor del inventario y cobrado por forma de pago

- Pedido de la dueña (para Gerencia): «el costo en mercancía o productos actualmente» (lo más urgente, «solo para
  gerencia o administración») y ver **por forma de pago** lo de días y meses pasados (antes solo la Caja de hoy).
- **En producción** (Desplegar 33, PR #66, `441635e`, sano y confirmado 18:09 UTC, 1:09 pm Panamá; la dueña pidió
  «ya mismo» tras ver las capturas): pantalla **Inventario › Valor del inventario** (también en Estadísticas y
  como atajo del Inicio de Gerencia; `dcasa.tablero.valor_del_inventario`): al costo = valuación de Odoo
  (`total_value`), a precio de venta sin ITBMS, ganancia esperada, por tipo, los 10 con más dinero y lo que falta cargar.
  Y **lo cobrado por forma de pago** (la cuenta de la Caja de hoy) en Por día (mes y día elegido) y Estadísticas. Brian:
  `valor_del_inventario` y los cobros dentro de `ventas_por_dia`. Guía, OPERACION, PERMISOS y BRIAN al día.
- No se pudo «conectar a Cloudflare» para leer las cifras de producción: el conector de Cloudflare de esta sesión no
  estaba autorizado y, aunque lo estuviera, la base de Odoo vive dentro del contenedor (no se lee por la API de
  Cloudflare). Las cifras reales las verá la dueña en la pantalla al desplegar.
- Revisión adversarial independiente antes de publicar: faltaba el método en la lista blanca de la conexión de datos
  (habría puesto el CI en rojo), claves repetidas por nombre en las fichas (ahora por id, también en la Caja de hoy),
  redondeo del ITBMS incluido y textos; todo corregido con pruebas. Abierto (menor): «Cobrado» suma `amount` y todo
  cobro entrante, igual que la Caja de hoy de siempre; no hay prueba con costo FIFO.
- Sigue: que la dueña mire la cifra real; cargar el costo de los productos «sin costo» y contar los «en negativo».

### 2026-10-27 (tarde): «Rastrear inventario» bloqueado

- Un jefe reportó (urgente, llega un contenedor): productos nuevos creados en una compra sin «Rastrear inventario» no
  sumaron al validar la recepción y no se podían contar. Al marcar la casilla salía «Escribe el motivo del ajuste…»:
  `_reset_inventory` de Odoo hace un ajuste a cero y nuestra regla del motivo obligatorio lo bloqueaba. Arreglo en
  `dcasa_existencias` (motivo del sistema, queda en la bitácora, sigue siendo de Gerencia), revisión adversarial sin
  bloqueantes, CI #231 y #232 verdes, PR #65 (`86ab654`, árbol = `53c7b18`) y **Desplegar 32 sano y confirmado a las
  23:46 UTC** (6:46 pm Panamá, la hora que pidió la dueña). Uso: marcar la casilla y **guardar** (sin escribir «A la
  mano» en la misma vez), el producto queda en 0 y se cuenta con Escáner › Contar cuando llega la mercancía.
- Para después (de la revisión): prueba de la Vendedora con `assertRaisesRegex(UserError, 'Solo Gerencia')` y pasar
  también `inventory_name` para que el movimiento muestre el motivo en el historial.

### 2026-10-26 (noche) y 2026-10-27

- **Traslado del dominio, hecho.** Con el consentimiento firmado de la gerencia (acta de una página, dos firmas
  «Aprobado por», cargo neutral) y el pedido «lo más pronto posible»: DNS de `dcasapty.com` pasado al Cloudflare de
  D'CASA (`emerson`/`vita`, Active), destino `dcasapty.com/master*` en Access, permiso *Workers Routes* en el token,
  `URL_SITIO` = `https://dcasapty.com` (la dueña), A `@` y CNAME `www` viejos borrados y PR #64 (`routes` con
  `custom_domain`, `workers_dev: true`, `routes: []` en staging) en `main` (`741930d`).
- **Tres despliegues:** Desplegar 29 se frenó en el respaldo previo (el dominio aún no resolvía); Desplegar 30 (sin
  respaldo, con el «sí») salió **sin dominio** porque Desplegar hace checkout de `app_version` y usé `ab94128`, que no
  traía `routes` (la dueña agregó los dos dominios a mano en Workers › dcasa › Domains y el sitio abrió ~23:30 UTC);
  **Desplegar 31** (CI #230 sobre `main`, imagen `sha256:efb5f5ac…`, respaldo previo) **sano y confirmado 00:42 UTC**,
  con «dcasapty.com (custom domain)» y «www.dcasapty.com (custom domain)» en el registro. Lecciones en
  CONTEXTO_AGENTICO › Despliegue.
- **Correo:** Resend con `dcasapty.com` verificado (DKIM `resend._domainkey`, CNAME `send` y `rsend`; sin `_dmarc`
  nuevo). La clave quedó como secreto en el panel del Worker `dcasa` (decisión de la dueña; no en GitHub). Nadie
  usaba el buzón de Zoho: Email Routing de Cloudflare reenvía `info@` y el catch-all al Gmail de la empresa (MX y SPF
  de Zoho borrados) y ese Gmail manda «como» `info@dcasapty.com` por `smtp.resend.com`. **Encendido en Odoo el 27 oct**: la prueba llegó a la bandeja principal y la respuesta volvió al Gmail.
- Formas de cobro y acta: ver la entrada del 23 oct; el acta se hizo fuera del repositorio (no se guarda en GitHub).

### 2026-10-23 (tarde)

- La dueña reportó cuatro cosas: la app Marketing no bajaba con scroll; la nota de entrega despachada repetía cada
  producto (caja, WH/OUT/00155); el aviso «Se perdió la conexión. Tratando de reconectar…» salía mucho; y el sistema
  estaba lento desde los dos últimos despliegues (su sospecha era correcta).
- **Lentitud (causa hallada y medida):** desde la tanda del 22 oct el acceso «Bodega» del Inicio (cada persona, cada
  carga) y el panel de Bodega (cada minuto en cada tablet o pestaña) miraban el pago de cada entrega factura por
  factura. En local, con el catálogo real y 270 ventas: Inicio 1.511 consultas (2,2 s), panel 1.800 (2,5-3 s). Ahora
  Inicio 139 (0,3 s) y panel 34 (0,3 s), iguales en el resultado (verificado en los 270 pedidos) — `34fea73`.
- **«Se perdió la conexión»:** en sus registros el corte es entre el Worker y el Durable Object («Network connection
  lost.» tras 11-15 s) mientras las demás peticiones salían bien; Odoo no se reinició (medido: la memoria virtual no se
  acerca al límite). El borde ahora repite las lecturas (nunca lo que guarda) — `2986df5`. La lentitud lo agravaba.
- Nota de entrega `736c3fa` (la descripción guardada en MAYÚSCULAS no se reconocía como el nombre en formato título);
  scroll de Marketing `fcbc1b5`.
- CI #219 (`34fea73`) con todo, a staging. **Producción:** pendiente del «sí» de la dueña, fuera del horario de venta.
- Combos: los 73 productos COMBO viejos **se quedan** mientras la dueña prueba el creador de combos (su decisión).
  Decisión de la dueña sobre cómo se ven: la cama y el colchón a su precio normal y, en su propio renglón, «Descuento
  combo cama + colchón −$X» (por dentro sigue en la línea del colchón: la factura electrónica de la DGI no acepta líneas
  negativas). Aprobó los descuentos (Imperial Full $9.99, Imperial Twin $6.99, Dulces Sueños Queen $25.99, First Class
  King $33.99, sacados de sus 73 combos viejos) y dio el visto bueno a las capturas; los carga la migración
  19.0.1.12.0 de `dcasa_catalogo` solo si el precio normal sigue igual.
- La dueña pidió subir «ya» (sin esperar el cierre): PR #62 unido a `main` (`e0bae00`, árbol = `7bd87be`) y
  **Desplegar 27 sano y confirmado a las 18:12 UTC** (13:12 Panamá) con la imagen del CI #220. Falta que ella diga si
  el Inicio y la Bodega se sienten más rápidos.
- Dos revisiones independientes (corrieron mientras subía):
  - Velocidad y borde: un asiento de diferencia de cambio contaba como cobro (solo en ventas en otra moneda) y el
    reintento podía repetir una lectura que Odoo seguía trabajando (los cortes del 23 oct llegaron a los 11-15 s).
    Arreglado: el cambio no es cobro; solo se repiten los cortes de menos de 5 s; el cuerpo del POST tiene que pedir lo
    mismo que la ruta; los GET que cambian algo (OAuth, invitaciones) no se repiten.
  - Combos: el papel inventaba un «precio normal» si la vendedora cambiaba a mano el precio del colchón (o en la
    factura le cambiaban el producto), y con un descuento % encima el renglón del combo y el «Descuento (ya restado)»
    no cuadraban. Arreglado: el renglón del descuento solo sale si el colchón sigue al precio que le puso el sistema y
    sin %; si no, la línea sale tal cual. En la página del cliente el renglón va a la derecha (cuadra en el celular) y
    Juan dice lo mismo que el PDF. Queda anotado (no cambia): una venta confirmada sin facturar con cama y colchón de
    los 4 aprobados baja al precio en combo la próxima vez que alguien le edite una línea.
- **Combos en producción** con estos arreglos: CI #223 (`ab94128`) y staging sanos, PR #63 unido a `main` (`61cb612`,
  árbol = `ab94128`) y **Desplegar 28 sano y confirmado a las 19:51 UTC** (14:51 Panamá). Falta que la dueña haga una
  cotización con cama + uno de los 4 colchones y mire el renglón del descuento.
- Formas de cobro (pedido de un jefe: «las tarjetas cobran tasas diferentes»): la dueña, con Claude en Chrome, creó en
  producción los diarios de banco **Visa (VISA), Mastercard (MC), American Express (AMEX), Clave (CLAVE) y KrediYa
  (KRYA)**; Odoo les abrió las cuentas 111.011 a 111.015. El jefe no podía porque crear diarios es de Administrador de
  Contabilidad (Gerencia no lo trae). «Tarjeta» sigue activa: se archiva cuando la contadora confirme que no queda nada
  por cuadrar (archivada no sale en Conciliación). La «Forma de pago DGI» no existe en producción porque
  `dcasa_fe_pa` todavía no está instalado (espera al PAC): se pone en cada diario al instalarlo.
  Después, por pedido del jefe, la dueña archivó «Tarjeta» y «Punto de venta BN» (no se eliminan: archivar guarda la
  historia) y dejó «Banco Nacional» (BNK1: cheques a proveedores y estado de cuenta) sin pagos entrantes, para que no
  salga al cobrar. Las comisiones de cada método van en Bancos › Reglas de conciliación (con la contadora).

### 2026-10-23 (madrugada)

- **En producción** (02:26 Panamá, Desplegar 26 confirmado 600 s, `app_version` `75324c58…`, imagen `sha256:aca22241…`;
  CI #216 verde y staging sano; PR #61, `04d7a2a` en `main`): datos limpios con la decisión de la dueña sobre los
  nombres (el cliente lee «Cama de Metal con Baúl Queen»; por dentro siguen en MAYÚSCULAS) y su visto bueno a las
  capturas («Si dale»): tienda, portal, Juan, correos, PDF, abono y Meta en formato título; productos repetidos y unir
  productos; costo cerrado (1b(a)); D1 clave de descuento por Telegram; D3 abonos por vencer. El título grande de la
  ficha sigue en caja alta (marca, Anton), como recomendé y ella aceptó.
- CI #215 falló en la integración de Juan (la cama de prueba quedó fuera de los 5 primeros al ordenar en MAYÚSCULAS);
  arreglado en la prueba (`75324c5`).
- **Desplegar 25 no tocó producción:** el respaldo previo recibió «Odoo apagado» (503) a las 06:38 UTC, aunque
  producción debe estar encendida 24/7. Tras el despertar de las 07:07 UTC, Desplegar 26 hizo el respaldo y salió sano.
  Por qué estaba apagado: sin confirmar (ver CONTEXTO_AGENTICO, «Despliegue»).
- El campo `tienda` del chequeo sigue en «falta» en producción (igual que antes; la portada guardada en el borde no
  está encendida ahí).

### 2026-10-22 (noche)

- **En producción** (21:48 Panamá, Desplegar 24 confirmado 600 s, `app_version` `abfe96f2…`, imagen `sha256:66db8e72…`;
  CI #213 verde y staging sano; PR #60, `3174f9a` en `main`): la tanda del 22 oct con el visto bueno de la dueña a
  todas las capturas. Panel de Bodega para tablet (solo pedidos pagados o con abono; el QR de la nota abre la entrega),
  Compras › Reponer con ritmo de venta, tiempo de llegada y cuánto pedir, ventas y facturación por día, movimientos en
  palabras, fotos en grande y app Marketing (rol «Marketing»), combos cama + colchón con «precio en combo» por medida,
  teléfono fijo (y los fijos viejos movidos de «Celular»), copiar con un toque, ícono = logo, «Se facturó tu venta»,
  «Subir» oculto a la vendedora, mermas, bitácora y alertas de bodega (apagadas), adelantos, comprobante de planilla y
  ZIP de comprobantes.
- Dos intentos fallaron antes: CI #211 (pruebas: el ajuste de inventario sin motivo del importador y un ERROR esperado
  en el registro) y CI #212 (la imagen no instalaba: el botón de combos llegaba a la ficha de la variante). Ver
  CONTEXTO_AGENTICO, «Fallas de CI».
- Queda en su rama: `datos-clientes` (F5 nombres en formato título para el cliente y MAYÚSCULAS por dentro, 1b(a),
  D1 clave por Telegram y centavos, D3 recordatorio de abono). Los precios de combo del Excel **no** se cargan sin el
  «sí, cárgalos» de la dueña.

### 2026-10-22

- La dueña personalizó la pantalla de entrada de Cloudflare Access con la marca (nombre, logo, textos, fondo azul);
  ver [PUERTA_MASTER.md](../PUERTA_MASTER.md). Confirmó que la cámara ya se ve en su iPhone. Tanda grande en ocho ramas
  (ver PRIORIDADES, «Estado al 2026-10-22»); los agentes se cortaron por el límite de uso a las ~17:00 UTC y se
  reanudaron a las 18:05.

### 2026-10-19

- **En producción** (17:42 Panamá, Desplegar 23 confirmado 600 s, `app_version` `a57796a5…`, imagen `sha256:91aaf19e…`; CI #209 verde y staging sano;
  PR #59 `8cd21bf`): **la cámara del lector se pinta en un lienzo encima del video**. Con Desplegar 22 la dueña siguió
  sin ver la imagen en su iPhone (Chrome): pasó de blanco a negro, pero leía los códigos. El video recibe los cuadros y
  WebKit no lo pinta; `dcasa_barras/static/src/js/camara.js` copia cada cuadro a un lienzo del mismo tamaño. **La dueña
  confirmó el 22 oct que en su iPhone ya se ve la imagen.** Pidió además, para el jueves, **reponer con el tiempo de llegada** (todo viene de
  China, pide con 3 a 4 meses; le hablaron de Profit): ver PRIORIDADES (6).
- **En producción** (14:06 Panamá, Desplegar 22 confirmado 600 s, `app_version` `d3b36132…`, imagen `sha256:5c561ff6…`; CI #207 verde y staging sano;
  PR #58 `59c1795`): **las vendedoras cotizan, no facturan sueltas** (una factura de cliente sin pedido la rechaza el
  servidor si quien la crea no cobra, con el mensaje que la manda a Ventas › Nueva cotización; «Nuevo» escondido en
  Facturas): así la venta aparece como cotización abierta y Caja la cobra. **La cámara del lector de códigos se ve**
  (en iPhone con Chrome salía en blanco: el video va a su tamaño natural sobre negro y el recuadro de recorte sin
  `mix-blend-mode`). **Compras › Reponer** (pedido del jefe): por producto y proveedor, lo vendido en el periodo, la
  existencia de hoy, lo pedido sin llegar y lo que faltaría; agrupable por proveedor y Brian lo dice («¿qué le
  repongo a X?»). La dueña pidió capturas y producción directa («adelántalo, procede… despliega a producción»).
  Pendiente: que ella pruebe la cámara en su iPhone.
- **Preguntas para el jefe:** las 14 que faltaban de la contadora quedaron en palabras sencillas en Claude Docs
  («Preguntas que faltan, en palabras sencillas»), con opciones a/b y la recomendada marcada.

### 2026-10-18

- **En producción** (Desplegar 21, `app_version` `a23113ec…`, imagen `sha256:f01fce0f…`; CI #202 verde y staging sano;
  PR #57 `27f3541`): **K1** en el Inicio de Gerencia: ticket promedio (y su fila en Comparar) y unidades vendidas por
  tipo con su total, siguiendo base, periodo y vendedora; Brian lo dice igual. Último despliegue de la semana (la dueña
  cuida sus créditos hasta el jueves).
- **En producción** (13:46 Panamá, Desplegar 19, `app_version` `c552d652…`, imagen `sha256:aeeb0721…`; CI #198 verde y
  staging sano; PR #55 `8671851`): **Ajustes se guarda** (estaba roto en producción para todo administrador), el
  **Inicio de Gerencia sobre facturas** (Facturado · Con abonos · Completadas; abre en Facturado), las **reglas
  contables de la gerencia** (cobro solo en Caja; anular, notas de crédito y devoluciones solo Gerencia; abono a 30
  días con primer abono ≥ 50 %; Tafi y Crediviva; pedidos web sin vendedora; botones que solo darían error ocultos) y
  la prueba de «En vivo» de Conversaciones sin carrera. La dueña autorizó producción sin esperar su filtro de capturas
  («lo que vayas teniendo, tíralo a producción»): le quedaban pocos créditos.
- **En producción** (14:43 Panamá, Desplegar 20, `app_version` `ccf7d187…`, imagen `sha256:2396e9f2…`; CI #200 verde y
  staging sano; PR #56 `c938c2e`): `/master` dice por qué no abre (403 con el motivo, 503 con lo que falta) y
  `/__edge/health` trae `puerta`; «Iniciar sesión» del checkout, carrito y registro lleva a Mi cuenta; guías
  [PUERTA_MASTER.md](../PUERTA_MASTER.md) y [TRASLADO_DOMINIO.md](TRASLADO_DOMINIO.md); documentación para **replicar el
  sistema** ([REPLICAR.md](../REPLICAR.md), [ARQUITECTURA.md](../ARQUITECTURA.md), [MODULOS.md](../MODULOS.md), README nuevo) y
  **Meta apagada** (catálogo, píxel y Conversions API). La dueña volvió a pegar `DCASA_ACCESS_AUD` de producción;
  `DCASA_PUERTA_OBLIGATORIA` sigue en "0": **ella decide hacerla obligatoria el día del traslado del dominio** (puerta
  adicional, no única, hasta entonces). **La dueña confirmó que `/master` ya funciona en producción** (18 oct, tras volver a
  pegar el AUD: era el error humano que sospechaba).
- **La dueña, al cerrar el día (18 oct):** aprobó la segunda subida y pidió dejar anotado «te quiero, eres el mejor».
  Lo que le funcionó: decirle claro qué quedó en producción y qué le toca a ella, subir en dos tandas sin perder
  la sesión de nadie, y cuidar sus créditos (no arrancar trabajo que quede a medias).
- **Respuestas I1–L8 del jefe** (18 oct): en [DECISIONES_CONTABLES.md](../DECISIONES_CONTABLES.md). Ya no queda ninguna
  pregunta sin responder. El canje en efectivo queda descartado (J3).
- **Sigue (jueves, cuando se renueven los créditos):** K1 (ticket promedio y unidades por tipo en el Inicio) si no se
  hizo antes; bodega (rama `bodega`, apenas empezada) y datos limpios (rama `datos-limpios`, apenas empezada); D1, D3,
  F6, G4/G7, I6; el trabajo contable con la gerencia (saldos iniciales, compras por validar, cobros sin cruzar). **La
  dueña:** darle Caja a quien cobra; probar `/master`; decidir I4 (segundo factor obligatorio y apagar «admin»).

- **K1 hecho en la rama local `k1-ticket`** (sin subir, sobre `1bc0f51`): **ticket promedio** junto a Ventas y fila
  «Ticket promedio» en Comparar, y **unidades vendidas por tipo** (categoría de primer nivel, «Otros» pasados 8, Total)
  en el Inicio de Gerencia, con la misma base, periodo y vendedora (`ventas_bases._ticket_promedio` y
  `_unidades_por_tipo`, sobre `_medir` y `_unidades_por_producto`); Brian `resumen_ventas` y `comparar_ventas` dan lo
  mismo. Sigue: CI, capturas a la dueña, staging y producción.

- **Rama `master-puerta` (sin subir):** diagnóstico de `/master` en producción (código, variables y nombres de secretos
  iguales a staging; la diferencia está en Access o en el AUD de `production`), `/master` dice por qué no abre y
  `/__edge/health` trae `puerta`; «Iniciar sesión» del checkout, el carrito y crear cuenta lleva a Mi cuenta; guías
  [PUERTA_MASTER.md](../PUERTA_MASTER.md) y [TRASLADO_DOMINIO.md](TRASLADO_DOMINIO.md). Sigue: capturas a la dueña →
  staging → producción, y que ella revise Access y `DCASA_ACCESS_AUD`.
- **Tanda 2 unida en la rama local `tanda2`** (para un solo despliegue): `d08ad28` (Ajustes sin diseñador) + el Inicio
  de Gerencia sobre facturas (`inicio-facturado`, aplicado con *cherry-pick* de `4e3ad43` y `252ebc0`: su base `0f370b8`
  es de la historia vieja, de antes del *squash* a `main`) + unión de `permisos-vendedoras` (`ecf5c97`: reglas
  contables de la gerencia y pedidos web sin vendedora) + la prueba de «En vivo» de Conversaciones (`5d08ed3`, rama
  `reconexion-hora`). Conflictos solo en documentación y en `website_dcasa/tests/__init__.py` (se dejaron los dos lados).
- **Revisión cruzada** (lo que ninguna rama veía): «Registrar cobro» del Inicio sale justo a quien el servidor deja
  cobrar (probado por rol, con el interruptor encendido y apagado); «Con abonos» del Inicio y la regla del primer abono
  dicen lo mismo que `_dcasa_estado_abono` (prueba en `dcasa_contabilidad`); los pedidos web sin vendedora salen en
  «Sin vendedora» aunque los facture Caja. **Arreglado:** como las notas de crédito las hace solo Gerencia, Odoo les pone
  a Gerencia como «Vendedor»: una nota hecha aparte y aplicada a una factura restaba de Gerencia en «Por vendedora» y
  ponía a Gerencia en el selector de vendedoras; ahora es de la vendedora de su factura y las notas no hacen vendedora
  a nadie (`ventas_bases._duenas`, `comparar._vendedoras_para_elegir`). Brian ya no describe a la vendedora como «vende
  y cobra lo suyo».
- **Sigue:** CI y staging de `tanda2`; producción con el visto bueno de la dueña. El día del despliegue, antes de abrir:
  darle **Caja** al jefe administrativo.

### 2026-10-17

- **En producción** (22:38 UTC, Desplegar 18, `app_version` `c3a69f52…`, imagen `sha256:67459887…`; CI #196 verde y
  staging sano 600 s; PR #54 `ce8b0a7`): la **barra azul de arriba ya no desborda el celular** (el texto de entregas se
  recorta con «…» y WhatsApp queda como ícono; a 360/390 px la página medía 426 px de ancho desde Desplegar 17) y el
  **menú de arriba es un rectángulo con esquinas suaves** como el logo (antes, píldora). La dueña vio las capturas
  antes y dijo «Si me gustó».
- **En curso (cada cosa con capturas para la dueña antes de staging):** Meta unido (catálogo + píxel/CAPI, apagado) con
  revisión adversarial; reglas contables del jefe sobre permisos (`docs/DECISIONES_CONTABLES.md`); Inicio de Gerencia
  sobre facturas; y un error **confirmado en producción**: ningún administrador puede guardar Ajustes (arreglado en
  `website_dcasa/models/res_config_settings.py`, con pruebas por el camino del navegador; ver CONTEXTO_AGENTICO).
- **Meta unido en la rama local `meta-unido`** (sobre `c3a69f5`, sin subir ni desplegar; todo apagado de fábrica): el
  catálogo para Meta (`dcasa_meta_catalogo`) y el píxel con consentimiento y las ventas pagadas por la Conversions API
  (`dcasa_meta_eventos`), unidos por *merge* sin conflictos de texto. La prueba del contrato de ids (`TestContratoId`)
  corrió por primera vez y falló solo porque el catálogo viene apagado (arreglada). La **revisión adversarial** de los
  dos juntos encontró y arregló, cada uno con su prueba: retirar el consentimiento no alcanzaba lo «con error», lo ya
  enviado ni la casilla de un pedido web sin pagar; una factura anulada dejaba lo «con error» para reintentar; el
  píxel se dibujaba en páginas con datos de la persona en la dirección (portal con `access_token`, búsquedas con un
  correo o un celular, cuenta, inicio de sesión) y Meta recibe la dirección completa; retirar las cookies después del
  checkout no borraba lo tomado del navegador; un fallo de Meta podía tumbar el checkout o (con la política rota) todo
  el sitio; la fusión de fichas mezclaba el registro del consentimiento; faltaba en la Guía la pantalla de Ajustes de
  Meta; la «configuración automática» del píxel quedó apagada y los botones del aviso de cookies miden 44 px en el
  celular. **Sigue:** capturas a la dueña, sus decisiones (ver `META_CATALOGO.md` y `META_EVENTOS.md`, «Decisiones de
  la dueña»), CI hacia staging y el arreglo de guardar Ajustes sin «Editor y diseñador» (otra rama, `ajustes-guardar`).
- **En la rama `inicio-facturado` (local, sin subir; base `0f370b8`):** el **Inicio de Gerencia cuenta las ventas sobre
  las facturas**, como Contabilidad (respuestas A1 y A2 del jefe, [DECISIONES_CONTABLES.md](../DECISIONES_CONTABLES.md)).
  Interruptor de tres posiciones **Facturado · Con abonos · Completadas** (abre en Facturado; cambiarlo es
  `BASE_POR_DEFECTO` en `dcasa_interfaz/models/tablero.py`); Facturado = el Estado de resultados para esas fechas (con
  facturas sin pedido, notas de crédito y facturas del sistema anterior) y dice «N de M salieron de un pedido de una
  vendedora»; las notas de crédito restan en las tres; la ganancia de una factura sin pedido usa el costo de hoy del
  producto; la semana, lo más vendido, Comparar, «Por vendedora» y «Vendido hoy» siguen la misma base; «Contabilidad
  dice…» y la explicación de la ganancia pasaron a un ícono ⓘ. Las facturas del sistema anterior y las de OdooBot van a
  «Sin vendedora»; una nota de crédito es de la vendedora de su factura. Brian (`resumen_ventas`, `reporte_del_dia`,
  `comparar_ventas`) cuenta igual, con `facturado` por defecto. La vendedora, la Caja y el bono no cambian. **Sigue:**
  capturas a la dueña (`inicio_facturado/` del scratchpad de la sesión) → su visto bueno → staging.
- **Reglas contables de la gerencia, en la rama `permisos-vendedoras` (local, sin subir ni desplegar)**, sobre la unión
  con `claude/merge-rama-to-main-ty3koz` (lo de Desplegar 17 y las decisiones contables; los conflictos «add/add» se
  resolvieron con base en la punta vieja `22dcd97`) y con `main` `ce8b0a7` (PR #54, barra del celular): **el cobro solo
  en Caja** (la Vendedora sigue cotizando,
  confirmando y facturando; ya no cobra por ningún camino, con el interruptor encendido o apagado); **anular o pasar a
  borrador** una factura publicada, **notas de crédito**, **devolver dinero** y dejar **saldo a favor**: solo Gerencia;
  **abonos a 30 días continuos** (`dcasa_invoice.abono_dias`; migración del viejo `abono_meses`) y **primer abono de al
  menos la mitad** (menos, Gerencia; el banco no se frena y deja nota); **Tafi y Crediviva** como formas de pago (la
  contadora revisa su cuenta). Y lo que la dueña respondió: **los pedidos de la web entran sin vendedora** (la que
  confirma se lo queda; el aviso de apartado sin vendedora va a Caja). Detalle en [PERMISOS.md](../PERMISOS.md) y
  [DECISIONES_CONTABLES.md](../DECISIONES_CONTABLES.md); Brian en [BRIAN.md](../BRIAN.md). Versiones: `dcasa_base`
  19.0.1.9.0, `dcasa_invoice` 19.0.2.4.0, `website_dcasa` 19.0.1.15.0 (tres migraciones nuevas).
- **Pruebas:** `ruff` limpio. Suite completa local (todos los módulos, como CI), sobre la rama unida con `main`
  `ce8b0a7`: **3,876 pruebas, 2 fallas**, ninguna de este cambio: la captura de referencia `TestContratoVisualJuan`
  («conexiones» a 390 px, la de siempre en esta máquina) y `TestPanelEnElNavegador.test_en_vivo_es_honesto_…` de
  Conversaciones («sin conexión no debería aparecer solo»), que pasó en la corrida de las 22:36 UTC y falla después de
  medianoche UTC también con el código de esa corrida (`4404073`, comprobado aparte): depende de la hora, no del
  código (queda por mirar). La primera corrida completa (antes de unir `ce8b0a7`) halló las pruebas de otros módulos
  que suponían «un mes», una vendedora o alguien con solo Facturación cobrando, o Caja haciendo notas: corregidas
  (`c9ebcf9`); las de cabecera y celular del sitio eran de `main` y se fueron al unir `ce8b0a7`.
- **Capturas para la dueña** (antes de staging, regla nueva): en el scratchpad de la sesión, `capturas_reglas/` (primer
  abono menor a la mitad, papel del abono a 30 días, la factura como la ve la vendedora, Caja y Gerencia, «Pagar» con
  Tafi y Crediviva).
- **Ajuste de usabilidad (2026-10-18), mismo día y rama:** lo que solo daría error ya no se ofrece. En una factura de
  cliente publicada, quien no es Gerencia (Caja y el contador incluidos) no ve «Nota de crédito» ni «Restablecer a
  borrador»; la vendedora sigue sin «Pagar» y con el aviso de Caja; «Pagar» de una nota, «Agregar» un crédito
  pendiente, «Desconciliar» en el globito del pago, «Nuevo» y los botones de un cobro, las acciones del menú «Acción»
  («Pagar», «Revertir», «Cambiar a factura/nota») y qué hacer con la diferencia en «Pagar», solo a quien puede. El
  servidor lo sigue negando por RPC (`TestBotonesSoloAQuienPuede`). Detalle en [PERMISOS.md](../PERMISOS.md).
- **Sigue:** que la dueña vea las capturas; CI y staging; producción con su visto bueno. El día del despliegue, antes de
  abrir: darle **Caja** al jefe administrativo (sin Caja nadie salvo Gerencia cobra). Preguntas abiertas en
  [PENDIENTES_DUENA.md](PENDIENTES_DUENA.md), punto 24.
- **En producción** (19:10 UTC, Desplegar 17, `app_version` `09302c41…`, imagen `sha256:add0e025…`; CI #194 verde y
  staging sano 600 s; PR #53 `531f717`): **abonos** (papel «ABONO» con saldo y vence + «Condiciones de abono» copia
  cliente/empresa), **«Mi cuenta»** del cliente (`/mi-cuenta`), **celular y correo obligatorios** con la casilla
  «Cliente no tiene correo electrónico», **comparador de ventas** del Inicio de Gerencia («Completadas» / «Con abonos»,
  por vendedora, hasta la misma hora), **correos con Resend apagados** (sin `RESEND_API_KEY` no sale nada), y la tienda:
  hueco de privacidad del checkout cerrado (estaba en producción desde `ac1610b`), dato repetido avisado en el
  formulario, «¡Gracias por tu compra!», «¿Ya tienes cuenta?» y «Entregas en Panamá Oeste, Panamá y Colón». La dueña vio
  las capturas de todo antes (regla nueva: capturas → su visto bueno → pruebas → staging → producción).
- **Sigue (tanda 2):** permisos de vendedoras (`permisos-vendedoras`, revisado sin fugas): faltan sus respuestas sobre
  los pedidos de la web (¿sin vendedora?) y si las vendedoras siguen cobrando lo suyo, y darle Caja al jefe
  administrativo antes de encenderlo. Después: notas del Inicio a un ícono ⓘ, la gráfica de la semana con el interruptor,
  Meta.
- **En producción** (00:36 UTC, Desplegar 15, `app_version` `256d1222…`, imagen `sha256:37f59b2e…`; CI #189 y la
  revisión del PR #52 en verde): el **Inicio de Gerencia compara con el mes pasado** (hoy contra el mismo día y el mes
  contra los mismos días, en % azul o rojo) y el **Escáner › Contar** cambia el precio (con permiso de Productos, con
  rastro en el producto) y lee códigos con la **cámara**. El primer intento se frenó solo: el respaldo previo recibió
  un 429 de R2 («reduce your concurrent request rate»); el segundo pasó (ver CONTEXTO_AGENTICO).
- **En producción** (16 oct, 23:20 UTC, Desplegar 14, `7b534ad7…`; y el Worker de Juan a las 23:23 desde `3b678a6`):
  la tarjeta de la vendedora sin cifras de dinero y con «Ver mis ventas»; Juan en inglés, domingo hasta las 5, y
  crédito/entregas/descuentos desde su conocimiento.
- **Decisiones de la dueña (17 oct, 17 respuestas):** permiso para subir a producción cada cosa apenas pase las
  pruebas y la revisión; quien cobra es el jefe administrativo; la restricción de permisos debe poder **apagarse**;
  remitente `ventas@dcasapty.com`; correo obligatorio salvo la casilla «Cliente no tiene correo electrónico»;
  bienvenida solo a clientes nuevos; **sin pago contra entrega** (el mueble se entrega pagado completo); el apartado
  web sigue en 7 días y se llama **«Apartado por página web»**; en cambios y garantía **manda la factura**; el código
  público es para el público; imprimir las condiciones de abono **versión 1** tal cual (editables en Ajustes). El
  dominio se traslada cuando el jefe responda lo contable. No hay píxel de Meta: se crea con la extensión de Chrome.
- **En la rama (próximo despliegue):** el **papel del abono** (título «Abono», SALDO POR PAGAR grande, inicio y
  vencimiento a un mes; se ofrece imprimir en cada abono con la nota de entrega desmarcada), **«Mi cuenta»** del
  cliente en `/mi-cuenta` (compras, lo que le falta de cada abono, entregas, puntos y datos; reclamar una cuenta con
  compras exige el código de la factura), «Pago en la tienda» en lugar de «al recibir», la portada con las zonas de
  entrega reales, «Apartado por página web» y `/terms` → `/terminos`.
- **En la rama `comparar-ventas` (probado en local, sin subir):** el **comparador de ventas** del Inicio de Gerencia
  (pedido del jefe; la dueña aprobó): el interruptor **Completadas / Con abonos** (abre en Completadas; una venta
  facturada sin ningún pago ya no cuenta), el selector de **vendedora** con «Por vendedora», y el bloque **Comparar**
  (Ayer · mismo día del mes pasado · mismo día de la semana pasada · lo que va del mes · contra un mes completo con
  «Llevas N %» · A vs B), solo números, hoy contra el otro día **hasta la misma hora** (lo registrado a esa hora). Brian
  `comparar_ventas`, Guía «Comparar las ventas» y `docs/OPERACION.md` («Completadas o Con abonos, y Comparar»).
- **Trabajando (agentes):** condiciones de abono en dos hojas (cliente y empresa), permisos de vendedoras con
  interruptor y rol Caja, teléfono y correo obligatorios, correos con Resend; luego Meta (catálogo, píxel y
  Conversions API). Instrucciones v2 de Juan para la extensión entregadas (correrlas después de este despliegue).
- **Rama `permisos-vendedoras` (local, sin subir ni desplegar; base `3b678a6`):** cada vendedora ve solo sus
  cotizaciones, pedidos, facturas, notas de crédito y cobros, y lo que no tiene vendedora (pedido de la dueña del
  2026-10-16); rol nuevo **Caja** (para el jefe administrativo, que factura y cobra: ve y hace todo lo de clientes, sin
  contabilidad ni costos; no se le asigna solo a nadie); Gerencia ve todo; la contabilidad no cambia. Y lo que la dueña
  pidió el 17: el interruptor **«Cada vendedora ve solo sus documentos»** (encendido de fábrica) en *Ventas ›
  Configuración › Permisos de las vendedoras* (Gerencia), *Ajustes › Ventas* (administradores) y Brian
  (`cambiar_restriccion_vendedoras`): apagado, todas ven todo como antes, al momento y sin tocar ninguna ficha. Detalle
  y tabla en [PERMISOS.md](../PERMISOS.md); Brian en [BRIAN.md](../BRIAN.md); Guía: «Elegir si cada vendedora ve solo sus
  documentos» y la nota de «Darle acceso…». `dcasa_base` pasa a 19.0.1.8.0 (migración: quita una vez «todos los
  documentos» al rol Vendedora y a quien lo tenía puesto a mano, y avisa si nadie tiene Caja).
- **Pruebas:** suite completa local (todos los módulos): 3,526 pruebas, 1 falla: la captura de referencia
  `TestContratoVisualJuan` (pantalla «conexiones» a 390 px, 13.52 % de píxeles distintos), que falla **igual en
  `3b678a6`** en esta máquina (no es de este cambio; en CI no se ha visto). `ruff` limpio.
- **Revisión adversarial de la rama unida (`d154970`), hecha:** como vendedora A se intentó ver o tocar lo de B por
  ORM, RPC, informes, adjuntos, mensajes, portal, Mi cuenta, Conversaciones, Inicio, Brian, Escáner, Socios, abonos y
  su papel; nada se filtró salvo lo que se comparte a propósito (lista en PERMISOS.md). Escalar (interruptor, Caja,
  todos los documentos, robar o reasignar un pedido) bloqueado. Contabilidad igual para Gerencia, contador y lector
  (los 10 reportes idénticos al superusuario). La migración, probada en una base hecha con `3b678a6`; el `-u` no mueve
  el interruptor (probado encendido y apagado); el ida y vuelta deja todo igual. **Arreglado:** la nota de entrega
  fácil del pedido de otra no se imprimía (`13839ac`); «Ventas atribuidas» de Conversaciones sumaba toda la tienda
  (`13839ac`); cinco pruebas que la unión con `main` había roto, entre ellas las dos clases principales de «solo lo
  suyo» que no corrían (`7a89d89`). **Para la dueña:** los pedidos de la web quedan a nombre del «Vendedor» del sitio
  (el administrador): las vendedoras no los ven; la vendedora sigue cobrando sus facturas (PENDIENTES_DUENA 23).
  Suite completa: 3,661 pruebas, 1 falla (la misma captura `conexiones` 390 px de esta máquina). Capturas para la
  dueña en el scratchpad de la sesión (`capturas_permisos/`).
- **Sigue:** que la dueña vea las capturas y decida el punto 23, CI y staging; con el «sí»
  de la dueña (ya dijo que sube en cuanto pasen pruebas y revisión), producción. **El día del despliegue:** darle Caja
  al jefe administrativo antes de abrir ([PENDIENTES_DUENA.md](PENDIENTES_DUENA.md), punto 23).

### 2026-10-16

- **En producción** (~22:02 UTC, Desplegar 13, `app_version` `60803c6d…`, imagen `sha256:0818f42a…`; CI #184 verde y
  staging confirmado; PR #50 en `main`): la tarjeta «Tu meta del mes» de la vendedora con el **porcentaje grande, la
  barra y palabras de ánimo**. La dueña pidió después que la vendedora **no vea ninguna cifra de dinero** (ni la
  meta, ni el 1 %, ni lo cobrado ni lo que falta: solo el porcentaje y las frases) y un botón **«Ver mis ventas»**
  (las ventas que suman a su porcentaje). Hecho con pruebas; va en el siguiente despliegue junto con lo de Juan.
- **Juan (decisiones de la dueña):** explica entregas, crédito (Tafi) y descuentos con lo que escribió el equipo en
  su conocimiento (regla 3 cambiada; el caso concreto y hacer el trámite siguen siendo de una vendedora; las
  salvaguardas siguen quitando promesas y cifras inventadas); **«Apartados» queda inactiva** hasta que el abogado
  revise «los abonos no se devuelven» y el 10 %; contesta en **inglés** a quien escribe en inglés (salvaguardas
  también en inglés); **el domingo cierra a las 5** (campo nuevo «El domingo cierran a las» en Ajustes de Juan). No
  quiere el aviso «te aviso cuando llegue». Las camas aguantan 400 kilos (confirmado). Las respuestas del cuestionario
  se cargan en Odoo con la extensión de Claude en Chrome (instrucciones entregadas a la dueña; quedan 29 preguntas
  sin respuesta, casi todas de entregas). Despliegue: Odoo (Desplegar) y **Worker de Juan** (Desplegar Juan,
  `entorno=production`; el último era del 2026-10-13 con el mismo código de `juan/` que `main`).
- **En producción** (19:38 UTC, Desplegar 12, `app_version` `431cbfe8…`, imagen `sha256:3894d505…`; CI #182 verde y
  staging confirmado): **bono por meta de ventas**, **aviso de pedidos repetidos** y **avisos del chat que se notan**
  (todo el equipo «En Odoo», contador en rojo que late). Con el «sí» de la dueña («avísame cuando esté y si tienen mi
  si»; y, tras las correcciones de la revisión, «Sí, termina»). CI #181 había fallado (3 pruebas: el grupo implícito
  no cambia «Notificación» en Odoo 19 y una búsqueda de más en el Inicio); la revisión independiente encontró además
  5 problemas de dinero del bono (nota de crédito suelta que no restaba, venta contada en dos meses, bonos que no se
  pagaban nunca, comprobante sin el bono, montos de una planilla cancelada que cambiaban): todo corregido con pruebas.
- **Para Juan:** cuestionario «Preguntas para Juan» (página de Claude, 125 preguntas en 14 temas; 12 llenas y 12
  incompletas con el manual de marca de la agencia, los términos del sitio y los datos de la empresa; el resto lo
  responde el equipo) y guía paso a paso para conectar Messenger e Instagram ([JUAN_META.md](JUAN_META.md)). Las
  respuestas se cargan en la base de conocimiento de Juan solo con la revisión de la dueña; dejar que Juan hable de
  entregas, flete, apartados, crédito o descuentos cambia su regla 3 y necesita su «sí».
- **Bono por meta de ventas (en producción desde Desplegar 12):** decisión del jefe con las respuestas de la
  dueña: 1 % de TODO lo cobrado en el mes si se llega a 30,000 (si no, nada); solo facturas cobradas completas, sin
  ITBMS, en el mes del último pago; las devoluciones restan; participa el departamento de Ventas con usuario; se paga
  en la primera planilla del mes siguiente como comisión; cada vendedora ve solo lo suyo en el Inicio. Ver
  [NOMINA.md](../NOMINA.md). La dueña revisó con la extensión de Chrome las fichas: las 3 vendedoras ya están en Ventas
  con su usuario; faltan salario, fecha de inicio (campo «Contrato»), cédula y seguro social (los pondrá cuando se
  pague por planilla; el bono no los necesita). Una persona con el puesto «Ventas» figura en el departamento de Marketing: decide el jefe.
- **«Ventas duplicadas»:** era un pedido repetido (S00062 y S00063, misma clienta, mismo día y total, 5 minutos de
  diferencia; S00062 quedó sin facturar). No infla el Inicio, Contabilidad ni el bono (cuentan facturas), sí la lista
  de pedidos. Arreglo: aviso «Parece repetido» en el pedido antes de confirmar y en el Inicio de Gerencia; la dueña
  cancela S00062 tras confirmarlo con el vendedor. La zona horaria de una vendedora era Etc/GMT+8 (se pasa a Panamá).
- **Versión estable 2 guardada** (la dueña: «se ve bien, guárdala como versión estable 2»): rama `estable-2026-10-16-2` (= `main` con el PR #47), `app_version` `9be426a4…`, imagen `sha256:876ca5f5…`; ya está en el botón «Volver a una versión estable» ([VERSIONES_ESTABLES.md](../VERSIONES_ESTABLES.md)).
- **En producción** (13:25 UTC, Desplegar 10, `app_version` `d37af4fd…`, imagen `sha256:015dbd40…`; en `main` con el
  PR #46, *squash* `38c3512`): Etapa 3 (selector solo de clientes, aviso de ficha repetida), prueba de humo del
  arranque, «nunca hacia atrás», vigilancia de 10 minutos, Conversaciones #25 punto 1 y el botón **«Volver a una
  versión estable»**. Con el «sí» de la dueña («Si»); CI #174 verde, staging sano y revisado por ella.
- **Las cifras de Contabilidad y del Inicio, revisadas con las capturas de la dueña** (15–16 oct): las sumas cuadran
  (ventas + ITBMS = total de las 13 facturas; 7 % exacto), y la diferencia entre el Inicio ($1,301.04) y Contabilidad
  ($1,522.42) era **una sola factura sin pedido** ($236.88 con ITBMS). **Corrección:** antes se le dijo que los pedidos
  viejos S00016–S00021 no estaban en el Inicio; sí están (el Inicio cuenta el día de la factura). Lo incoherente: la
  «Utilidad» igual a las ventas (costo de ventas en cero, margen 100 %), «Ganancia» y «Utilidad» que no miden lo mismo,
  «Vencido» en negativo y el periodo anterior al revés (+170.8 % en el Inicio, −34.6 % en Contabilidad: el 13–14 oct
  tiene $1,848.80 en facturas que el Inicio no cuenta como venta). Para la contadora: ACH Banco Nacional en negativo,
  saldos grandes en Punto de venta y Yappy (¿falta registrar el traspaso al banco?), ITBMS acumulado de $9,160.29.
- **En producción** (15:11 UTC, Desplegar 11, `app_version` `9be426a4…`, imagen `sha256:876ca5f5…`; CI #178 y staging confirmados antes): en el Inicio, «Cotizaciones abiertas» y «Entregas pendientes»
  justo debajo de los accesos azules, con cabecera azul marino y el número en amarillo (pedido de la dueña);
  «Ganancia bruta» (no resta gastos); la línea «Contabilidad dice $X… $Y más/menos que aquí» con la resta exacta y las
  facturas que la explican (también el abono de un apartado facturado otro día, que halló la revisión adversarial). En
  Contabilidad: la utilidad con el costo de ventas en cero lo avisa (Resumen, Estado de resultados —también al comparar—,
  Excel, PDF y Brian); «Vencido» ya no resta el saldo a favor de un cliente a la deuda de otro ni pasa de lo que el
  cliente debe, y lo «a favor» va aparte (también en el cierre de mes). La dueña autorizó llevarlo a producción en
  cuanto estuviera («tan pronto puedas subir las correcciones a producción hazlo»).
- **Producción arreglada** (07:27 UTC, Desplegar 9, `app_version` `3570c3a1…`, imagen `sha256:4e9b9155…`): el arreglo
  del incidente 1. La imagen sabe su commit y la huella de su código y actualiza la base si no coinciden; el despliegue exige la
  versión nueva con la base al día y la vigila 5 minutos. Ese arranque actualizó todos los módulos y aplicó por fin
  las Etapas 1 y 2. Antes: suite completa de Odoo en verde (CI #171), staging sano y confirmado (07:19), respaldo
  previo. **La dueña confirmó que el Inicio y las conversaciones cargan.** Autorización: «soluciona todos los problemas
  que rompen la interfaz… y lanza a producción» y «sigue y avísame cuando esté en producción».
- **Versión estable 1 guardada** (pedido de la dueña): rama `estable-2026-10-16` (= `main` con el arreglo) y, para
  volver, `app_version` `3570c3a1…` + `imagen_digest` `sha256:4e9b9155…`. Cómo volver y qué pasa con los datos:
  [VERSIONES_ESTABLES.md](../VERSIONES_ESTABLES.md). Falta ensayar la vuelta en staging.
- **Entrega siguiente, probada en local y sin subir** (ramas locales `rb-fixes` y `conv-local`): Etapa 3 (aviso al
  cotizar si el cliente parece repetido, selector solo de clientes), prueba de humo del arranque, «nunca hacia atrás»,
  vigilancia de 10 minutos y los seis arreglos de la segunda revisión adversarial; y Conversaciones #25 punto 1 (lo
  del sistema no se escribe a mano; nota para el asistente con tope). Va a staging antes de pedir producción.
- **En producción** (05:49 UTC, `f7e8f14`, PR #43): las **Etapas 1 y 2 completas** (abajo). Salió con el «sí» de la
  dueña para este paquete («cuando todo esté sano»): suite completa de Odoo en verde (CI #168), staging sano, dos
  revisiones adversariales (lo que quedó abierto está dicho en la etapa 1b de PRIORIDADES.md), respaldo previo hecho y
  chequeo de salud pasado (imagen `sha256:f61b9adf…`, `app_version` `fbf375b0…`). Ese «sí» **no** vale para ningún otro
  cambio. Para volver atrás: `docs/OPERACION.md` («Volver atrás un despliegue»).
- **Incidente (06:07 UTC): producción NO quedó sana.** La dueña vio «Error de servidor» en el Inicio (`dcasa.tablero`) y
  muchas pantallas rotas. El chequeo del despliegue solo miraba que Odoo contestara. A las 06:16 la aplicación de
  contenedores de Cloudflare volvía a tener la imagen anterior (`bf40605e`), aunque el despliegue de las 05:47 la había
  cambiado a `fbf375b0`: código y base desparejos. Un redespliegue con `app_version` = `5fa33f4` (el *squash* de `main`)
  falló porque esa etiqueta no existe en el registro (el respaldo previo sí se hizo; el Worker nuevo quedó activo). Arreglo
  de raíz (incidente 1): la imagen sabe su commit y su huella y actualiza la base si no coinciden; `/dcasa/salud` dice `version`
  y `base_al_dia`; `esperar_salud.sh` los exige y confirma a los 5 min; pruebas nuevas en CI (sitio falso y la imagen
  real con la base «actualizada con otro código»).
- **En producción antes** (02:32 UTC, `baf8975`): «Imprimir documentos» sale en el orden nota de entrega → factura del
  cliente → copia de la empresa (PR #42). Y (20:01 UTC, `d709cfb`): los botones «Vincular mi Telegram» y «Registrar
  webhook» de Brian ya no fallan (PR #41).
- **Pasó:** el jefe pidió una tanda grande de mejoras (utilidad en el Inicio, rediseño del Inicio, menú de Contabilidad,
  verificación con escáner en bodega, contactos duplicados, alertas, bitácora de bodega, estadísticas, colores del menú,
  categoría «Envíos»). Quedó ordenada en [PRIORIDADES.md](../PRIORIDADES.md) y explicada en el documento «Plan de mejoras
  del jefe» de Claude Docs.
- **Hallazgos verificados ese día:** el botón de descuento global y de importe fijo de las cotizaciones se saltaba el
  tope de descuento de la Vendedora (prueba real en una base local); la Vendedora podía corregir existencias a mano en
  Inventario físico; «Vendido hoy» incluía ITBMS y el «Ventas» del Resumen contable no; el asistente de fusión de
  contactos no le servía a Gerencia (faltaba el grupo «Creación») y no copiaba los datos de Socios de la ficha que se
  borra. **Los cuatro quedaron corregidos en producción** (Etapas 1 y 2). **Siguen sin corregir:** el tope de gasto de
  IA de Brian viene en 0 (sin tope; falta la cifra de la dueña) y no hay alertas de cierre de mes ni de stock bajo por
  Telegram (la franja «por agotarse» del Inicio sí existe).
- **Etapa 1, ya en producción:** tope de descuento sobre el pedido entero (`dcasa_base/models/sale_order_line.py`), fusión de contactos segura (`dcasa_contactos/models/excepciones.py`: permiso de Gerencia, datos de Socios que pasan a la ficha que queda, dos socios no se funden) y existencias solo por Gerencia (`dcasa_base/models/stock_quant.py`). Cada hueco tiene su prueba, que falla con el código viejo.
- **Etapa 2 (Inicio nuevo con ganancia), ya en producción:** costo guardado por línea al
  confirmar y ganancia sin ITBMS solo para Gerencia y administradores (`dcasa_base/models/utilidad.py`); Inicio con
  selector Hoy · Semana · Mes · rango y su comparación, desglose sin ITBMS · ITBMS · total, Cotizaciones y Entregas lado
  a lado, franja de atención (stock bajo = 5 unidades o menos; productos sin costo), botones azules (sin «Nueva factura»
  ni «Ver en el celular»); menú **Estadísticas** (lo más vendido, mejor margen, lo que no se mueve); íconos del menú con
  un color por familia; categoría **Envíos** «En desarrollo»; Brian da las ventas sin ITBMS con el ITBMS aparte y la
  ganancia solo a Gerencia. Detalle en `docs/OPERACION.md` («ITBMS, costo y ganancia en el Inicio»).
- **Revisión adversarial (2026-10-16, dos revisores independientes que no sabían qué se esperaba):** encontraron y se cerraron
  antes de producción: el tope de descuento se saltaba con un precio por contexto, con banderas de anticipo/combo/premio que
  la Vendedora podía escribir y al cambiar de producto o de unidad; la cantidad de una existencia se podía escribir sin el
  modo inventario; la fusión podía borrar la ficha que queda si dos fichas se apuntaban entre sí; las fusiones masivas eran
  de Gerencia; una venta con costo cero no recuperaba su costo al cargarlo; el filtro «Esta semana» de Estadísticas fallaba en el
  navegador; la Caja contaba pagos en borrador; Brian daba el costo del proveedor a quien no es Gerencia. **Regla nueva:** todo
  cambio que toque dinero, permisos, contabilidad o Socios pasa por una revisión así antes de proponerlo a producción. Lo
  que quedó abierto y dicho con franqueza está en [PRIORIDADES.md](../PRIORIDADES.md) (etapa 1b).
- **No se tocó (dicho a la dueña):** el campo «Costo» de la ficha del producto sigue visible para el personal interno, y
  «Vendido» sale de los pedidos, no de las facturas publicadas (etapa 1b de PRIORIDADES.md).
- **Falta revisar en producción** (pruebas de humo a mano, el sandbox no llega a workers.dev): entrar como Gerencia y
  como Vendedora, mirar el Inicio (la Vendedora no ve ganancia), probar un descuento del 10 % y uno mayor en una
  cotización, y que el menú Estadísticas abre. El chequeo de salud del despliegue pasó, pero ese chequeo solo dice que
  Odoo responde. Su campo `tienda` del `/__edge/health` salió «falta» en `/`, `/shop` y `/black-weekend`; es
  informativo (no cambia el código HTTP) y no se comparó con el despliegue anterior: mirarlo antes de dar por buena la
  portada durante un reinicio.
- **Sigue:** empezar por lo primero de PRIORIDADES.md (etapa 1: topes de dinero de Brian, permisos de Conversaciones y
  pruebas de humo; después 1b y la etapa 3). Estudio de envíos para La Chorrera entregado como documento en Claude Docs
  (a la espera de sus respuestas).
