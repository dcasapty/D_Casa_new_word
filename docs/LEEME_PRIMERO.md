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

### 2026-11-13 (2) y 2026-11-14: avisos de Telegram ordenados, lote 1 de la web, «Busca con una foto», ícono de Brian y horario de la tienda (Desplegar 71 y Juan 25); Brian de la tienda y lote 2 de la web (Desplegar 72 y Juan 26) y la burbuja que cambia con el scroll (Desplegar 73), en producción

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

### Entradas anteriores (una línea cada una; el texto completo en [historico/BITACORA_ANTERIOR.md](historico/BITACORA_ANTERIOR.md))

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
