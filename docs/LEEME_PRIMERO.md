# Léeme primero (para quien retome el trabajo)

Este archivo existe para que, cuando una sesión de trabajo se reinicie y el contexto se pierda, quien siga (una persona o
Claude) entienda **en cinco minutos** cómo se trabaja aquí, qué está hecho y qué sigue, sin empezar de cero ni preguntarle
a la dueña lo que ya se contestó. `CLAUDE.md` apunta aquí.

> **Regla de oro de este archivo:** al terminar cada sesión se agrega una entrada arriba de la
> [Bitácora](#bitácora-de-sesiones) (qué entró, qué quedó en staging, qué sigue) y se actualiza
> [PRIORIDADES.md](PRIORIDADES.md). Si no se anota, la próxima sesión no lo sabe.

## 1. Con quién se trabaja y cómo hablarle

- La dueña **no es técnica**. Se le habla en español sencillo y corto, de tú, sin jerga ni siglas sin explicar; se usa
  a cada persona se le trata como la persona misma diga; si no lo dijo, en neutro («la persona», «quien»), sin adivinar por el
  nombre. Primero el resultado, después el detalle.
- Lo que pide un **jefe** (el dueño de la empresa) llega a través de ella: se trata como pedido de la dueña, y se le
  responde a ella con lo que pueda reenviarle.
- **Corrección (2026-10-26):** el responsable del negocio es **hombre**; en este repositorio «la dueña» es solo el nombre
  de siempre para quien trabaja con Claude. En todo lo que se imprime o se firma (actas, cartas, papeles para los jefes)
  nunca «dueña» ni «dueño»: un cargo neutral y profesional («Gerencia general», «CEO», o «Aprobado por» con una línea de
  Cargo para que cada uno escriba el suyo). Al hablarle, en neutro si no lo dijo.
- **Nunca se pide un secreto por el chat** (claves, tokens, contraseñas). Se le dice *dónde* ponerlo (secreto de
  Cloudflare o de GitHub) y se confirma que quedó cargado sin ver su valor.
- **Los datos de personas** (nombres, correos, celulares, cédulas, facturas de clientes) viven solo en Odoo: ni en el
  repositorio, ni en documentos, ni en pruebas. Tampoco se guarda en GitHub un PDF de una entrega o factura real.
- **Seguridad y menos fallas antes que velocidad** (dicho por la dueña el 2026-10-16): no importa esperar las pruebas; importa no tener fallas ni huecos. Nunca recortar pruebas para ir más rápido.
- **Criterio contable:** cuando una cifra puede mostrarse de varias formas (con o sin ITBMS, etc.), se decide por mejor práctica contable y se explica en la etiqueta; la preferencia de la persona no manda sobre eso. Regla vigente: ventas, costo y ganancia sin ITBMS; el dinero que se mueve (por cobrar, cobrado, caja) con ITBMS.
- **Contactos:** la limpieza de duplicados es de **clientes y proveedores**; las fichas de usuarios y empleados del sistema se respetan.
- Si una respuesta le va a servir a otra persona (el jefe, la contadora), se entrega como documento en Claude Docs, no
  solo en el chat.

## 2. Autorizaciones (lo que se puede y no se puede hacer solo)

| Acción | ¿Hace falta su «sí»? |
|---|---|
| Programar, probar y subir a la rama de trabajo | No (autorizado de forma permanente) |
| Desplegar a **staging** | **Antes, capturas a la dueña y su visto bueno** (regla del 2026-10-17: capturas → su filtro → pruebas → staging → producción). Capturas con datos de prueba, en computadora y celular, revisadas antes de mandarlas |
| Crear el PR hacia `main` | Solo cuando lo pide o ya dijo «pásalo a producción» |
| Unir a `main` y desplegar a **producción** | Permiso general desde el 2026-10-17 («súbelo en cuanto vayas terminando») para lo que pasó pruebas y revisión. **Desde el 2026-11-13 sin esperar su visto bueno a las capturas** («no esperes mi aprobación para pasar a producción. Apruébalo y punto»): se le muestran igual, pero no se espera. La revisión adversarial no se salta |
| Borrar datos, ramas, respaldos, secretos | Sí, y mirando primero qué se borra |
| Cifras de dinero, puntos, comisiones, impuestos | Nunca se inventan (ver `CLAUDE.md`: `puntos.json`, reglas de marca) |

## 3. Cómo se llega a producción (receta)

La receta completa, la que se usó en los despliegues 31 a 47, está en un solo lugar:
**[DESPLIEGUE.md › La receta de producción](DESPLIEGUE.md#la-receta-de-producción)**. En corto:

1. Cambio en la rama de trabajo con su prueba; en local, `scripts/test.sh <módulos>` (PostgreSQL local; si se cayó:
   `pg_ctlcluster 16 main start` y esperar la recuperación), `ruff check addons` y, si tocó un Worker, `npm test && npm run
   typecheck` en su carpeta.
2. **CI/CD** a mano en la rama con `desplegar_en = staging`: todas las pruebas y, si pasan, staging (unos **45 minutos**:
   ~25 de pruebas de Odoo y ~20 del despliegue a staging, CI #260 del 2026-11-05).
3. Con staging sano y el «sí» de la dueña: PR con `[skip ci]` en el título, *squash* con `expectedHeadSha` = el commit
   probado, y comprobar que el árbol de `main` es el del commit probado.
4. **Desplegar** desde `main` a `production` con el `imagen_digest` y el `app_version` probados: **`app_version` es el
   SHA de 40 de la rama que construyó el CI, nunca el del *squash*** (se repitió en Desplegar 55), y
   `respaldo_previo = true`: unos **15 minutos**, contando los 600 s de vigilancia del final (`esperar_salud.sh`).
5. Mirar `/dcasa/salud`, avisarle a la dueña qué cambió para ella (sin tecnicismos), cancelar el CI que abrió el PR y
   traer `main` a la rama con `git merge -s ours origin/main`. **Desplegar Juan** solo si cambió `juan/`.

## 4. Trampas ya conocidas (no volver a tropezar)

- **«Sano» no es «Odoo contesta» (incidente 1 del 2026-10-16, en CONTEXTO_AGENTICO).** El arranque decidía actualizar la base solo
  por la variable `APP_VERSION`, que puede llegar atrasada, y el despliegue daba por sano cualquier 200: producción
  quedó con el código nuevo sobre la base vieja (o con la imagen vieja) y el Inicio y otras pantallas fallaron. Ahora
  la imagen sabe su commit y la huella de su código, actualiza la base si no coinciden y el despliegue exige
  `version` y `base_al_dia` (ver `docs/DESPLIEGUE.md`). Después de cada despliegue igual se abre el Inicio.
- **`app_version` tiene que tener imagen en el registro.** El despliegue usa la etiqueta `dcasa-odoo:<app_version>`,
  que solo existe para los commits que construyó el CI (el de la rama, no el del *squash* en `main`). Con otro SHA
  falla con `IMAGE_REGISTRY_DOESNT_CONTAIN_IMAGE`, y aun así el Worker nuevo ya quedó activo (Cloudflare activa el
  Worker antes que la imagen).
- **Nunca inventar un SHA** (ni "completar" uno corto): se lee del PR o del run. Ya falló un merge por eso.
- `rerun_failed_jobs` da 403 mientras el run sigue en curso: esperar a que termine. Una prueba que falló en CI no se
  "pausa": se espera o se cancela el run y se corrige.
- Los botones de la cabecera de una lista llaman al método con la lista de ids (vacía si no hay selección): un método
  `@api.model` fallaría. Hay un test guardián en `dcasa_base/tests/test_superficie_rpc.py`.
- PyPDF2 reescribe los textos de un PDF fusionado con escapes octales; las pruebas de PDF usan `textos()` que los
  decodifica (`dcasa_invoice/tests/test_paquete.py`).
- Las variables del Worker (`VARIABLES_DEL_CONTENEDOR`) llegan al contenedor al arrancar: un cambio en el panel de
  Cloudflare se aplica al reiniciar o en el siguiente despliegue. Los IDs (p. ej. `BRIAN_TELEGRAM_CHATS`) son variables
  normales, no secretos.
- Las pruebas de Odoo tardan ~25 minutos en CI y el ciclo completo con staging ~45; un fallo cuesta un ciclo entero.
  Antes de subir, correr en local los módulos que se tocaron.
- El CLI `gh` existe en esta máquina y sirve para **leer** (runs, tiempos de cada job, issues). Lo que **escribe** en
  GitHub (PR, unir, lanzar flujos, comentar) va por las herramientas `mcp__github__*`.
- Cada función nueva de la plataforma debe poder usarla Brian (`docs/BRIAN.md`); el PR lo pregunta.
- **El `<body>` del panel es una rejilla (barra lateral + contenido).** Lo que Odoo o una librería cuelgan del
  `<body>` para medir cae en la columna de la barra (68 px) y mide mal: así se cortaban las fechas de todas las listas
  (2026-11-11). `barra_lateral.scss` hace que lo que no es de la rejilla ocupe el ancho entero; no quitar esa regla.

## 5. Dónde está cada cosa

| Quiero saber… | Voy a… |
|---|---|
| Qué falló antes, por qué y cómo se arregló (incidentes, despliegues, CI, trampas) | [CONTEXTO_AGENTICO.md](CONTEXTO_AGENTICO.md) |
| A qué versión segura volver si algo se rompe, y cómo | [VERSIONES_ESTABLES.md](VERSIONES_ESTABLES.md) |
| Qué se pidió y en qué orden se hace | [PRIORIDADES.md](PRIORIDADES.md) |
| Cómo está todo hoy y qué le toca decidir o hacer a la dueña | [PRIORIDADES.md](PRIORIDADES.md) (estado del día y «Lo que falta de la dueña») |
| Trabajo de desarrollo abierto | Los issues del repositorio (`mcp__github__list_issues`) |
| Cómo se despliega y se vuelve atrás | [DESPLIEGUE.md](DESPLIEGUE.md) (la receta) y [OPERACION.md](OPERACION.md) |
| Juan: cómo funciona, la bandeja y los canales | [JUAN.md](JUAN.md) · [JUAN_ODOO.md](JUAN_ODOO.md) · [JUAN_CANALES.md](JUAN_CANALES.md) |
| Qué ve cada rol | [PERMISOS.md](PERMISOS.md) |
| Cómo hablar con Brian y qué puede hacer | [BRIAN.md](BRIAN.md) |
| Todo lo demás | [README.md](README.md) (índice de `docs/`) |

## Bitácora de sesiones

> Más reciente arriba. Cada entrada: fecha, qué quedó en producción (con el commit), qué quedó solo en staging, qué
> sigue. Se guardan las diez más recientes; las viejas se resumen en una línea abajo y su texto completo pasa a
> [historico/BITACORA_ANTERIOR.md](historico/BITACORA_ANTERIOR.md).

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

### Entradas anteriores (una línea cada una; el texto completo en [historico/BITACORA_ANTERIOR.md](historico/BITACORA_ANTERIOR.md))

- **2026-11-11 (3):** Inicio nuevo, el celular al entrar, la caja del chat, entregas = Bodega, «Más datos» y modo oscuro, en producción (Desplegar 65, 66 y 67)
- **2026-11-11 (2):** auditoría visual del panel; 21 arreglos en producción (Desplegar 64); propuesta 2 del Inicio
- **2026-11-11:** versión estable 4; Instagram con fotos confirmado; enlace de choferes encendido; cierre de semana
- **2026-11-10:** WhatsApp 131070 RESUELTO («redireccionar conversación» a D'CASA Juan); Juan pide el control y anota todo
- **2026-11-09 (tarde y noche):** enlace para choferes; «Colchones» abre WhatsApp; Messenger conectado; WhatsApp bloqueado por Meta (131070)
- **2026-11-09:** «No llegó» por el pago de Meta (131042); preguntas sin respuesta para las vendedoras; videos con voz
- **2026-11-07 (3):** Camila: «Abrieron» y «Tocaron» en 0; remitente propio de las campañas y aviso de Resend, en producción
- **2026-11-07 (2):** issues #24 (Juan) y #25 (Conversaciones), lo que quedaba, en producción.
- **2026-11-07 (1):** citas, reenviados, reacciones y palomitas en el chat, en producción.
- **2026-11-06 (9):** Camila etapa 1b: la lista de las novedades crece sola.
- **2026-11-06 (8):** «Ver más» en la foto del catálogo y Dependabot, en producción.
- **2026-11-06 (7):** la pantalla de Sofía.
- **2026-11-06 (6):** Brian al día.
- **2026-11-06 (5):** Camila etapa 2 («a lo grande, todo conectado con todo»), en producción.
- **2026-11-06 (4):** Camila, la asistente del mail marketing (módulo nuevo `dcasa_camila`, etapa 1).
- **2026-11-06 (3):** la varita mágica («Sugerir») escribe siempre, o dice por qué y deja reintentar.
- **2026-11-06 (2):** la calculadora de envíos en el menú Envíos (módulo nuevo `dcasa_envios`).
- **2026-11-06 (1):** limpieza y mantenimiento; WhatsApp guarda antes de contestar; Camila (diseño).
- **2026-11-05 (4):** «Guardar y responderle».
- **2026-11-05 (3):** Sofía baja con scroll; «Guarda sus datos».
- **2026-11-05 (2):** Sofía, la asistente del CRM (módulo nuevo `dcasa_sofia`).
- **2026-11-05:** tasa de cierre en el Resumen de Juan; idea del agente del CRM.
- **2026-11-04:** tarifas de envío (propuesta, en pausa) y clientes repetidos (buscar por celular, «Es esta persona»).
- **2026-11-03 (tarde y noche):** tres paneles en el Inicio, CRM al chat, vendedoras activas, notas de voz y fotos.
- **2026-11-02 (tarde) y 2026-11-03 (madrugada):** Juan en el WhatsApp de la tienda, medios en el chat, origen y cotizaciones que vencen.
- **2026-11-02:** Valor del inventario y cobrado por forma de pago.
- **2026-10-27 (tarde):** «Rastrear inventario» bloqueado por la regla del motivo del ajuste; motivo del sistema y
  Desplegar 32 (PR #65).
- **2026-10-26 (noche) y 2026-10-27:** traslado de `dcasapty.com` al Cloudflare de D'CASA (Desplegar 29 a 31, PR #64) y
  correo con Resend (`info@` reenviado al Gmail de la empresa).
- **2026-10-23 (tarde):** lentitud resuelta (el Inicio y el panel de Bodega ya no miran el pago factura por factura),
  reintento del borde ante «Network connection lost», nota de entrega sin repetidos y scroll de Marketing (Desplegar 27,
  PR #62); combos cama + colchón con el descuento en su renglón y los 4 descuentos aprobados (Desplegar 28, PR #63); la
  dueña creó los diarios Visa, Mastercard, American Express, Clave y KrediYa y archivó «Tarjeta» y «Punto de venta BN».
- **2026-10-23 (madrugada):** datos limpios en producción: nombres en formato título para el cliente, productos repetidos,
  costo cerrado, clave de descuento por Telegram y abonos por vencer (Desplegar 26, PR #61). Desplegar 25 no tocó
  producción: Odoo estaba apagado (503; causa sin confirmar).
- **2026-10-22 (noche):** la tanda del 22 oct en producción (Desplegar 24, PR #60): panel de Bodega, Reponer con tiempo de
  llegada, ventas por día, app Marketing, combos, teléfono fijo, mermas y alertas de bodega, adelantos, comprobante de
  planilla y ZIP de comprobantes.
- **2026-10-22:** la dueña personalizó la pantalla de entrada de Cloudflare Access y confirmó que la cámara se ve en su
  iPhone; tanda grande en ocho ramas.
- **2026-10-19:** la cámara del lector se pinta en un lienzo (Desplegar 23, PR #59); las vendedoras cotizan y no facturan
  sueltas, la cámara se ve y Compras › Reponer (Desplegar 22, PR #58); las 14 preguntas que faltaban, para el jefe.
- **2026-10-18:** ticket promedio y unidades por tipo (Desplegar 21, PR #57); Ajustes se guarda, Inicio de Gerencia sobre
  facturas y reglas contables de la gerencia (Desplegar 19, PR #55); `/master` con diagnóstico, «Iniciar sesión» a Mi
  cuenta, documentación para replicar y Meta apagada (Desplegar 20, PR #56); respuestas I1–L8 del jefe.
- **2026-10-17:** barra del celular y menú con esquinas suaves (Desplegar 18, PR #54); abonos, Mi cuenta, celular y correo
  obligatorios, comparador de ventas y correos apagados (Desplegar 17, PR #53); comparación con el mes pasado y cámara del
  Escáner (Desplegar 15); 17 decisiones de la dueña; permisos de vendedoras y Meta en sus ramas.
- **2026-10-16:** incidente 1 (las Etapas 1 y 2 rompieron el Inicio; arreglo: la imagen sabe su commit y la salud es
  estricta, Desplegar 9); versiones estables 1 y 2; Desplegar 10 a 13 (Etapa 3, Inicio con cotizaciones arriba, bono por
  meta, pedidos repetidos, meta de la vendedora); decisiones sobre Juan; regla de revisión adversarial.
