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

### 2026-11-19 y 2026-11-20: «Forma de pago» en facturas, ventas por día, carrusel y Andrés ampliado, Tilopay y la comisión web. En la rama de trabajo, probado, SIN subir (producción sigue en `d2ba8caf`)

**Nada de esto está en producción todavía.** Todo vive en `claude/merge-rama-to-main-ty3koz` (cada pieza en su rama
local `local/*`, unidas). Seis piezas hechas en paralelo, cada una con su **revisión adversarial independiente** (tres
vueltas la de Tilopay) y las pruebas del revisor copiadas al módulo sin debilitarlas. Orden de salida pensado: primero lo que no mueve
dinero, luego Tilopay (nace **apagado**), y la comisión **sin versión de reglas** (solo mide; nadie cobra nada) hasta que
Gerencia ponga cifras y la contadora diga cómo se trata.

- **Facturas** (`local/facturas`, `5405fc0a`): columna, filtro y «agrupar por» de **Forma de pago** (el diario de cada cobro;
  «Nota de crédito»; «Sin pago registrado» si Odoo la da por pagada sin pagos), y **Exportar a Excel** para Gerencia, que
  baja solo `account.move`, sus líneas, `account.payment`, `sale.order` y sus líneas (los administradores, todo). El xlsx escribe
  los textos como texto (nunca fórmula). Revisión: 6 hallazgos (idioma del texto guardado, fórmulas en el xlsx, exportar de
  más, columna ambigua, vistas de proveedor, calidad de pruebas), todos arreglados.
- **Ventas por día** (`local/ventasdia`, `378d2314`): una tarjeta «Cobrado por forma de pago» con **Día / Semana / Quincena /
  Mes** sobre la lista, `dcasa.tablero.cobros_del_periodo`, y las cifras **suben animadas** en todas las pantallas (`useCifrasQueSuben`).
  «Cobro» sigue teniendo una sola definición (`_dominio_de_cobros`, ahora solo clientes).
- **Portada y Andrés** (`local/retoques`, `58122eb1`): los **segundos del carrusel** los define Gerencia (3 de fábrica, de 2 a 15)
  en un modelo propio `dcasa.portada.ajustes`, **sin ningún permiso sobre `website`** (la revisión halló que escribir en `website`
  le abría a Gerencia, como superusuario, las acciones de servidor del sitio sin grupo); la vitrina pública tiene caché de
  60 s; el chat de **Andrés abre ampliado en escritorio** (≥ 1024×600, sin puntero táctil; la preferencia se recuerda).
- **Tilopay** (`local/tilopay`, `588c6363`, módulo `dcasa_pago_tilopay`): tarjeta, Yappy y más desde la tienda y el portal.
  Nace apagado y sin publicar; las claves viven solo en Cloudflare (`TILOPAY_API_KEY`, `TILOPAY_API_USER`,
  `TILOPAY_API_PASSWORD`; la variable `TILOPAY_ENTORNO`, «prueba» primero). 241 pruebas de Odoo, 299 del borde. Tres vueltas del
  revisor: tope global de llamadas a la vez (la tienda ya no se cae si Tilopay tarda), cobro que no cuadra con el pedido → revisión
  humana (nunca se paga sola), «Modo de prueba» en producción solo para el equipo. **Antes de cobrar de verdad** (lista en
  `docs/TILOPAY.md` §9.1): registrar el aviso `https://dcasapty.com/payment/tilopay/webhook` con Soporte, preguntar la vigencia de
  la página de pago, conciliar a diario contra el panel de Tilopay y las verificaciones de siempre. Todo se probó con un
  Tilopay simulado: **falta una compra de ensayo con la cuenta de pruebas de Tilopay**.
- **Comisión por ventas del sitio web** (`local/comision`, `766ee8b8`, módulo `dcasa_comision_web`): % fijo sobre las ventas del
  sitio (sin meta) y tarifa fija aparte, a empleados de Nómina elegidos por Gerencia, libro inmutable, reglas con versión
  hacia adelante, liquidación de periodo libre (quien cobra no aprueba lo suyo), no es salario. Gerencia respondió ocho preguntas y
  cuatro casos (2026-11-19 y 20; están en `docs/PLAN_COMISION_WEB.md`): VEN paga al dueño del enlace **y** cuenta para el sitio; la
  cotización armada por Juan cuenta; Andrés ya no cuenta siempre (si una vendedora atendió el chat de Juan en 30 días, no cuenta);
  las vendedoras nunca reciben nada por lo online. Primera revisión: 4 bloqueantes (origen forjable, aprobar lo propio editando la
  ficha, doble pago por concurrencia, dos cortes de fecha), 4 importantes y menores; todos arreglados. **Segunda revisión: en curso.**
- **Anotado, no hecho:** factura de emergencia sin conexión (un solo archivo HTML) en el issue
  [#129](https://github.com/dcasapty/D_Casa_new_word/issues/129).

**Lo que decidí yo (y se le dijo):** el permiso de exportar de Gerencia se limita por modelo (no «todo»); los segundos del carrusel
van en un modelo aparte; Tilopay nace apagado; la comisión sale sin cifras.

**Sigue:** batería completa sobre la rama, segunda revisión de la comisión, y subir por la receta (§3); Tilopay a staging con
claves de la cuenta de pruebas de Tilopay (no pasan por el chat); la contadora decide cómo se trata la comisión y el diario
«Tilopay» (se crea al desplegar aunque el proveedor siga apagado); confirmar que `web.json.enabled` no está puesto en producción.

### 2026-11-17 (3) y 2026-11-18: la segunda entrega completa en producción (CI/CD 380 y Juan 29)

**En producción desde el 2026-11-18, 00:5x UTC:** la segunda entrega entera (PR #128, squash `d2ba8caf`,
ejecución 380 de CI/CD a mano desde `main`) y **Desplegar Juan 29** (01:0x UTC, misma versión). Salud del borde
sana: `{"ok": true, "version": "d2ba8caff071", "base_al_dia": true, "humo": "ok"}`. El `/salud` de Juan responde con
`d2ba8caf` en `produccion`, la tienda lista y activa; las 4 «cosas por revisar» que lista son claves y canales que
**ya faltaban** (la `ANTHROPIC_API_KEY` de respaldo y el puente de WhatsApp por QR, que nunca se desplegó), no algo
que trajera esta subida.

**Lleva:** Andrés como mejor vendedor, las notas de voz (de Andrés y del panel de Brian), el micrófono del chat, la
pantalla «Armar combo» con los precios de verdad, los tres arreglos de las revisiones (el total negativo del
mostrador por los dos caminos, la guardia del Worker que se saltaba con «…ok?» y el premio que viajaba al chat) y la
regla nueva de Socios que va abajo.

**La decisión que la frenaba ya está tomada y programada.** La dueña eligió, entre dos opciones que se le
presentaron con las cifras: **«avisarle y no dejar canjear»**.

- **El problema** (lo encontró la revisión adversarial de Andrés vendedor): la línea del premio baja la compra medida
  (decisión M6 de la dueña), así que podía tirarla por debajo del mínimo de la promoción de envío y hacerle perder el
  envío gratis. Carrito de $205 sin ITBMS, premio de $10 → la compra queda en $195.65 y paga $45 de envío. **Gastaba
  puntos para pagar más.**
- **Lo que quedó:** antes de canjear se compara lo que pagaría de envío con lo que le descuenta el premio. Si iguala o
  pasa, se le avisa con las dos cifras y no se canjea (sus puntos no se mueven: el canje ni se pide). **Decidí yo (y
  se le dijo):** si el premio descuenta MÁS de lo que perdería, se deja pasar, porque ahí el socio sale ganando y
  bloquearlo sería quitarle un beneficio real.
- **Dos fallos míos que encontraron las pruebas y la revisión, los dos de dinero:**
  1. Yo medía la bajada por el **valor de cara** del premio; la línea rebaja la **base** sin impuesto ($9.35 para un
     premio de $10). El aviso habría dicho una cifra que no era y el bloqueo saltaba en el borde equivocado. La
     cuenta del impuesto quedó en un solo sitio para que no se vuelvan a separar.
  2. Al devolverle los puntos, **la promoción no volvía**: el sincronizador de envíos solo quita esa línea, nunca la
     repone. El socio quedaba sin el premio Y pagando el envío: peor que el problema original. Ahora, al quitar un
     premio —lo quite el sistema o el socio— la promoción se vuelve a ofrecer.
- **Un BLOQUEANTE de la revisión independiente:** la guarda vivía solo en el carrito web, y por «Cobrar premio» del
  **mostrador** el premio entraba directo: cobrar uno de $25 sobre una venta de $205 con envío gratis le hacía pagar
  $21.64 más, sin que nadie se lo dijera. Pasó a `_aplicar_en_venta`, por donde van los dos caminos (es la segunda vez
  que una guarda de dinero de premios se tiene que mover ahí; quedó anotado como regla). En el mostrador el código
  sigue valiendo para otra compra.
- **Dos hallazgos más de la revisión, arreglados:** el ahorro de la promoción es una base y el valor del premio va con
  ITBMS, así que al compararlos ahora el ahorro sube con los impuestos del envío (hoy va sin ellos, pero puede
  cambiar); y el carrito del chat no corría la limpieza de premios, así que podía seguir mostrando uno que ya no le
  convenía. También se probó el borde exacto que eligió la dueña («iguala» → no se canjea), que antes pasaba igual
  con `>` que con `>=`.
- **Sigue abierto, anotado:** el carrito le ofrece premios que el servidor va a rechazar (el aviso llega después del
  clic); y si lo que se pierde eran términos ya prometidos de una promoción vencida, esos no vuelven.

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

### Entradas anteriores (una línea cada una; el texto completo en [historico/BITACORA_ANTERIOR.md](historico/BITACORA_ANTERIOR.md))

- **2026-11-13 (2) y 2026-11-14:** avisos de Telegram ordenados, lote 1 de la web, «Busca con una foto», ícono de Brian y horario (Desplegar 71 y Juan 25); Brian de la tienda y lote 2 de la web (Desplegar 72 y Juan 26); la burbuja que cambia con el scroll (Desplegar 73); el 15, Brian siempre activo de noche (Juan 27 y Desplegar 74), en producción
- **2026-11-13:** Juan ya no dice «no lo manejamos» de lo que no está publicado (Desplegar 69 y Juan 23) y
  responde comentarios de Instagram y Facebook, apagado (Desplegar 70 y Juan 24), en producción
- **2026-11-12:** Juan cotiza envíos con la promoción, reparto justo de chats y Costos de IA con «Pagar», en
  producción (Desplegar 68 y Juan 21); se descubrió que Messenger e Instagram no les llegan a los clientes
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
