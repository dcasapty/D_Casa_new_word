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
| **Cambios de diseño** (cómo se ve el sitio, el pago o el panel: colores, tamaños, tipografía, botones, márgenes, pantallas nuevas o rediseñadas) | **Sí, y viéndolos antes (2026-11-20).** Gerencia dijo: «antes de cualquier cosa o cambio en el diseño me gustaría verlo antes». Se muestran capturas **antes/después** (computadora y celular, con datos de prueba) y **no se sube a producción hasta su «sí» a lo que vio**. Esto **tiene prioridad** sobre «no esperes mi aprobación» (2026-11-13), que sigue valiendo para lo que no cambia cómo se ve (lógica, permisos, rendimiento) |
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

### 2026-11-23 (00:28 UTC): Rotación, Movimiento y Margen y rotación EN PRODUCCIÓN (`39ae8f26b178`, PR #131), con los cierres R9 de los pagos

**En producción desde el 2026-11-23 00:28 UTC:** `39ae8f26b178` (PR #131, squash `9e6b76df`, CI/CD de staging run 45078483833, **Desplegar a `production` run 45087461624**, digest `sha256:a86b76f9…e6338`).
Salud: `{"ok": true, "version": "39ae8f26b178", "base_al_dia": true, "humo": "ok"}`; la portada responde 200 y `/odoo` redirige al ingreso. Juan no cambió (no se desplegó).

- **Qué subió:** las tres pantallas de Inventario (Rotación, Movimiento, Margen y rotación), el atajo «Rotación» del Inicio, sus colores de modo oscuro, la Guía, las herramientas de Brian `rotacion_de_inventario` y `comparar_movimiento`,
  y los **cierres R9-1 a R9-5** de los permisos del pago en línea (Tilopay y Yappy siguen apagados). **Autorizaciones de la dueña ese día:** «pásalo a staging» (viendo las capturas), «si pasa staging, pásalo a producción» y, cuando se le
  preguntó aparte porque el paquete llevaba los R9, «sí, súbelo todo junto».
- **El camino fue tres CI, no uno:** el #386 (commit `0ef2ba4`) falló en `TestModoOscuroServidor.test_los_rellenos_propios_se_leen_de_noche` (las dos pantallas no tenían colores de noche: `dcasa_interfaz/static/src/oscuro/rotacion.dark.scss`);
  una corrida local de 814 pruebas halló además que la prueba del Inicio de Gerencia no conocía el atajo «Rotación». El segundo (45075867605, `e3a3cfe`) se **canceló a propósito** cuando llegó la revisión independiente; el tercero (45078483833, `39ae8f2`) pasó todo
  (Tests de Odoo 74 min) y desplegó a staging sano.
- **Revisión independiente (en paralelo al CI):** sin fuga de dinero; cuatro importantes arreglados y probados antes de subir (Excel con `{=...}`, búsqueda por producto al elegir categoría, nuevos y con pedido abierto fuera de los cuadros de margen, pruebas de las herramientas de Brian) y
  tres menores (año 0001, cruce con «año pasado», porcentaje bajo −100 %); pedidos y gráfica con la misma base que las unidades. Lo que quedó abierto: `dcasa_interfaz/models/reponer.py` tiene la misma debilidad de `{=...}` en su Excel.
- **Lo que enseñó:** CONTEXTO_AGENTICO › «Lo que enseñó «Margen y rotación» y su primer CI a staging» y «Lo que enseñó la revisión independiente de Rotación, Movimiento y Margen».
  Además: **antes de subir, comparar `git diff --stat origin/main HEAD`**: el paquete probado llevaba código que la dueña tenía esperando su «sí» (los R9) y por eso se le preguntó antes de unir.
- **Falta:** que la dueña abra las pantallas en producción y diga si algo se ve raro; las claves de Tilopay y Yappy en Cloudflare (nunca por el chat); lo que quedó de «lo que pidió el jefe»: las mediciones del Inicio (idea: «Lo más vendido» con su cambio y una tarjeta de «parado 90 días o más»).


### 2026-11-22 (tarde): «Movimiento» (comparar periodos) y un simulador de márgenes. En `claude/merge-rama-to-main-ty3koz`, SIN desplegar

La dueña pidió seguir con lo de ver los artículos de mayor y menor movimiento y rotación **por tiempos y comparando periodos**, para hacer campañas de publicidad y de redes más fácil. Detalle en [MOVIMIENTO.md](MOVIMIENTO.md):

- **Pantalla «Movimiento»** (`dcasa_marketing`: `models/movimiento.py`, `static/src/{js,xml,scss}/movimiento.*`, `controllers/movimiento.py`, `views/movimiento_views.xml`): se elige el periodo (7, 15, 30, 60, 90 días, este mes, el mes
  pasado o fechas) y contra qué se compara (el de justo antes, el mismo del año pasado o fechas). Muestra el resumen (unidades, pedidos y productos, ahora y antes; el dinero solo para Gerencia y administradores),
  una gráfica por día o semana y la lista con el estado de cada producto (subió, despertó, igual, bajó, se enfrió, quieto), lo vendido ahora y antes (unidades y pedidos), el cambio %, para cuántos días alcanza lo que hay,
  ancla, agotado y sin foto. «Crear campaña con los primeros 8» (Camila, en `dcasa_camila`), «Ver estos en Productos» y Excel. Entradas: Inventario › Movimiento, el botón «Comparar periodos» de Marketing y un enlace en Rotación.
  Brian: `comparar_movimiento`. Guía: `movimiento-productos`.
- **El modelo se llama `dcasa.movimiento_productos`**: `dcasa.movimiento` ya es el libro de puntos de Socios y chocó (la base no cargaba, `KeyError: 'partner_id'`). Ver CONTEXTO_AGENTICO.
- **Pruebas:** `TestMovimiento` 26 en verde (extremos exactos de los periodos, estados, cambio %, nota de crédito, pedidos, cobertura, listas y orden, resumen, gráfico, permisos, Excel), `TestMovimientoEnElNavegador` 3 en verde
  (390 y 1440 px con Chrome; Gerencia y el rol Marketing sin dinero) y el resto de `dcasa_marketing`, `dcasa_guia`, `dcasa_camila`, `dcasa_brian` y la lista blanca de RPC.
- **Simulador de márgenes** (un artefacto privado, no está en el repositorio): precio, costo, rebaja, programa de vendedores con código, pasarela de pago (Tilopay o Yappy, % que cobra) y comisión del empleado de la web, en cuatro
  pasos; la dueña lo encontró complicado y se simplificó a «¿nos conviene?». Los precios y porcentajes son de ejemplo. No cambia nada en el sistema.
- **«Margen y rotación» en Rotación** (solo Gerencia y administradores; parte del pedido del jefe: «los de mejor rotación o probar SKU que mejoren márgenes»): cuatro botones nuevos (estrellas, venden mucho/dejan poco,
  buen margen/se mueven poco, ni se mueven ni dejan margen) con cortes que son las **medianas de la propia tienda** (la pantalla dice los números), una etiqueta en cada fila y una columna en el Excel. Brian: `grupo=estrella|trafico|oportunidad|revisar`.
  Pruebas: `TestRotacionMargen` y `TestRotacionMargenEnElNavegador` (medianas con filas inventadas, el corte exacto, permisos, Excel, 390 y 1440 px).
- **Capturas y «sí» de la dueña a staging (2026-11-22):** vio las capturas de «Margen y rotación» y dijo «pásalo a staging». El CI #386 (commit `0ef2ba4`, `desplegar_en = staging`) salió en rojo en
  «Tests de Odoo»: `TestModoOscuroServidor.test_los_rellenos_propios_se_leen_de_noche` (Rotación y Movimiento no tenían colores de noche). Arreglo: `dcasa_interfaz/static/src/oscuro/rotacion.dark.scss`
  (con captura en modo oscuro) y, de la corrida local de 814 pruebas, la prueba del Inicio que no conocía el atajo «Rotación». Ver CONTEXTO_AGENTICO › «Lo que enseñó «Margen y rotación»».
- **Falta:** relanzar el CI a staging con el arreglo, verificar staging y avisarle; producción solo con su «sí» después de verlo en staging
  (`-u dcasa_marketing,dcasa_camila,dcasa_interfaz,dcasa_guia`).

### 2026-11-22: «Rotación» del inventario (pedido del jefe) y «Operación Sun Tzu». En `claude/merge-rama-to-main-ty3koz`, SIN subir y SIN desplegar

El jefe pidió (por la dueña) saber qué productos no rotan, en 30, 60, 90 días…, para rebajarlos y recuperar capital de trabajo, enfocarse en lo que mejor rota y en los
productos ancla, y mejorar las mediciones de Marketing y del Inicio. Detalle completo en [ROTACION.md](ROTACION.md):

- **Pantalla «Rotación»** (`dcasa_marketing`: `models/rotacion.py`, `static/src/{js,xml,scss}/rotacion.*`, `controllers/rotacion.py`, `views/rotacion_views.xml`): una barra por grupo de
  **días sin vender** (menos de 30, 30 a 59, 60 a 89, 90 a 179, 180 o más, nunca vendido, llegó hace poco, pedido abierto), los botones «30 / 60 / 90 / 180 días o más sin vender», la lista
  por producto (existencias, última venta, vendidas en 30·60·90 días, cuántos días alcanza, capital parado, precio y margen), **ancla** (los que juntos hacen el 80 % de las unidades de
  90 días), una **simulación de rebaja** (solo una cuenta: cuánto entra, cuánto queda sobre el costo y cuántos quedarían bajo el costo) y **Excel**. El capital es la valuación de «Valor
  del inventario». **El dinero es solo de Gerencia y administradores**; el rol Marketing ve unidades y días. Entradas: Inventario › Rotación, el botón de la pantalla Marketing y un
  acceso en el Inicio (`rotacion`). Brian: `rotacion_de_inventario`. Guía: `rotacion-inventario`.
- **Pruebas** (base nueva con el módulo, Python 3.12): `dcasa_marketing` 67 en verde (27 de Rotación, 3 de navegador a 390 y 1440 px con Chrome, y el resto de siempre); 10 mutaciones de
  Rotación (el dinero a todos, un corte movido, sin pedido abierto, un ajuste como llegada, el 80 % cambiado, el orden, el «bajo el costo», la nota de crédito, el tope de 100…): todas
  caen salvo una a propósito (la simulación tiene dos guardias para quien no ve dinero y se quitó una). `ruff check addons` limpio.
- **Falta, en este orden:** (1) las capturas antes/después con datos de prueba para la dueña (es una **pantalla nueva = cambio de diseño**: su «sí» antes de producción, LEEME §2); (2) lo que
  conteste sobre los cortes (30, 60, 90, 180), el «llegó hace poco» (30 días; los pedidos tardan 3 a 4 meses) y qué hacer con lo parado; (3) CI → staging → producción. No hace falta `-u` de
  otros módulos; sí `-u dcasa_marketing,dcasa_interfaz,dcasa_guia` (vista y acción nuevas, atajo del Inicio y entrada de la Guía).
- **«Operación Sun Tzu»** (estrategia contra el competidor, con el plan «Caballo de Troya» por diseñar): es un documento **privado en Claude Docs, no en el repositorio** (es público y habla de la
  competencia de la empresa). Quien lo retome lo pide a la dueña.
- **Lunes (pendiente de la dueña):** poner las claves de Tilopay y de Yappy Comercial en Cloudflare (**nunca por el chat**), y los cierres R9 a producción (siguen esperando su «sí»).
- **Entorno local:** el `.venv` no existía y el sistema no trae `babel`. Receta que funcionó: `python3.12 -m venv`, `pip install psycopg2-binary` y los requisitos de Odoo **sin** `psycopg2` ni
  `python-ldap` (necesitan compilar), más `docker/requirements-dcasa.txt`, `ruff` y `websocket-client`; PostgreSQL con `pg_ctlcluster 16 main start`. Las pruebas de Chrome corren con el
  `google-chrome` de `/usr/bin`.

### 2026-11-21 (tercera ronda): Yappy directo, quinta vuelta (RV8b): R9-1 a R9-5 arreglados o documentados. En `local/rv7-arreglos` (sobre `f81d669`), SIN subir y SIN desplegar

El revisor RV8b atacó `492fe22`: los 12 hallazgos de la vuelta anterior quedaron cerrados, sin regresiones, **pero el cierre de R8-1 estaba incompleto** (dos puertas más). Detalle y
tabla en [YAPPY.md](YAPPY.md) §14; cada punto con su prueba y su mutación:

- **R9-1:** el `create` del pedido miraba `vals` y no `default_transaction_ids` del contexto (Odoo lo aplica después): la vendedora creaba un pedido con un cobro ajeno y Bodega
  lo veía pagado. Ahora se mira lo que el pedido trae **después de crear**. **R9-2:** crear a mano un recibo (`out_receipt`) con el cobro de otro SÍ se podía (la regla «quien no
  cobra no hace facturas sueltas» solo mira `out_invoice`) y luego `write(move_type='out_invoice')` lo volvía factura: ahora la misma comprobación posterior en `AccountMove.create`
  y una guardia sobre `move_type` (cambiar el tipo de un documento de cliente es de Caja o Gerencia; lo que toque una nota de crédito, de Gerencia). **`sale._create_invoices` crea con
  `sudo` y no se afecta** (la prueba «la vendedora sigue creando la factura de un pedido ya cobrado» sigue en verde). **R9-3:** `action_refund`, `action_capture` y `action_void`
  (core, corren con `sudo` tras mirar solo el ACL) se niegan a quien no cobra. **R9-4:** `resumen.cita` quita los caracteres de formato y de control (`Cf`, `Cc`). **R9-5:** los
  textos que prometían de más, corregidos (incluida la lección de CONTEXTO_AGENTICO que decía que «otras dos reglas» cerraban el `create` de la factura: solo se había probado con
  `out_invoice`).
- **Dos cosas nuevas que costaron corridas de CI** (anotadas en CONTEXTO_AGENTICO): `scripts/test.sh` cuenta como falla toda línea de registro ERROR/CRITICAL aunque Odoo diga «0
  failed» (las pruebas que provocan un error a propósito lo capturan con `assertLogs`), y el CI usa Python 3.12 (no 3.11 como esta máquina).
- **Pruebas** (base nueva con los 32 módulos, `-u` de los módulos tocados): `dcasa_base` 450, `website_dcasa` 499, `dcasa_pago_yappy` 425 (con Chrome), `dcasa_pago_tilopay` 347 y
  `dcasa_guia` 97: **0 rojas, 0 con error y 0 líneas ERROR/CRITICAL** (contadas con la misma expresión regular que `scripts/test.sh` y el CI) en Python 3.11. Las mismas 1,404 pruebas corridas
  también con Python 3.12 (el del CI; entorno propio armado con los requisitos de Odoo): 0 rojas, 0 con error, 0 líneas ERROR. `ruff check addons` limpio. 6 mutaciones de esta vuelta, todas caen. No hace falta `-u` de
  ningún módulo nuevo al desplegar (todo es Python; sin campos ni datos nuevos).

### 2026-11-20 (noche, segunda ronda): Yappy directo, cuarta vuelta (RV8): R8-1 a R8-7 arreglados o documentados. En `local/rv7-arreglos` (sobre `2e23d3a`), SIN subir y SIN desplegar

El revisor independiente RV8 atacó `2e23d3a` y dijo: staging apagado, sí; encender en prueba, sí; cobrar de verdad, todavía no. Sin ninguna regresión (ningún
flujo legítimo de ningún rol dio `AccessError`). Lo que encontró y se hizo (detalle y tabla en [YAPPY.md](YAPPY.md) §14), cada pieza con su prueba y rompiendo el
arreglo a propósito:

- **R8-1 (la importante):** R7-1 había cerrado la transacción pero no **la otra mitad de la misma relación**: la vendedora escribía `sale.order.transaction_ids` y
  `account.move.transaction_ids` y ligaba un cobro ajeno a un pedido (Bodega lo veía pagado y soltaba la mercancía), lo aplicaba a la factura de otro cliente o escondía
  un pago. Ahora `transaction_ids` se niega a quien no cobra en `write` de pedido y factura y en `create` de pedido (`dcasa_base/models/cobros.py`).
  **Incompleto:** el `create` del pedido miraba solo `vals` y el `create` de la factura se había dejado sin guardia con un argumento falso: la vuelta siguiente (RV8b,
  abajo) cerró las dos puertas que faltaban. **R8-2 y R8-6:** la transacción pasa de lista negra a **lista blanca vacía** (quien no cobra no escribe
  NADA ni crea; antes escribía `partner_id`, `landing_route` —un `javascript:` en el navegador de la clienta— y `state_message`; y el `create` solo se negaba por casualidad).
- **R8-3 (solo texto):** cuando el cobro suelto es de OTRO pedido del mismo cliente, el pendiente de Caja dice las dos salidas («confirma ESTE pedido a mano y registra su pago»)
  y a la clienta ya no se le dice «tu pedido ya figuraba como pagado» si no se sabe. **Se valoró comparar el monto y no se hizo** (no distingue un cobro parcial de este pedido
  de un anticipo de otro; YAPPY.md §14). **R8-4:** en el pendiente de 15 minutos, lo que escribió la clienta (nombre, celular, valores personalizados de producto) va entre
  comillas y recortado a 60 caracteres. **R8-5:** aceptable, sin cambio. **R8-7:** textos que prometían de más corregidos (YAPPY.md §3.4 y §14, PERMISOS.md y un texto del pendiente
  con «esta frase» sin ninguna); la trampa de las pruebas de permisos (bajar la caché) está en CONTEXTO_AGENTICO, con un matiz: `assertRaises(AccessError)` de Odoo ya la limpia sola.
- **Pruebas** (base nueva con los 32 módulos, `-u` de los módulos tocados): `dcasa_base` 439, `website_dcasa` 499, `dcasa_pago_yappy` 410 (con las de Chrome), `dcasa_pago_tilopay`
  347, `dcasa_guia` 97 y `dcasa_comision_web` 621 (sin tocarlo) = **1,867, 0 rojas, 0 con error**; `ruff check addons` limpio. 9 mutaciones de esta vuelta, todas caen (y la
  décima, «la regla también contra `sudo`», tumba 35 pruebas de la tienda y del aviso). No hace falta `-u` de ningún módulo nuevo al desplegar.
- **Falta:** otra revisión independiente de estos arreglos, unirlo a la rama de trabajo, y lo de siempre antes de cobrar de verdad (compra de ensayo, respuestas de Yappy,
  política de privacidad, conciliación diaria, decisión R7-7).

### 2026-11-20 (noche): Yappy directo, tercera vuelta (RV7): los hallazgos R7-1 a R7-10 arreglados o documentados. En `local/rv7-arreglos` (sobre `a3bffac`), SIN subir y SIN desplegar

El segundo revisor independiente (RV7, sobre `9154bb2`) dijo: staging apagado, sí; encender en prueba, sí; cobrar de verdad, todavía no. Esto es lo que
se arregló (detalle y tabla en [YAPPY.md](YAPPY.md) §14), cada pieza de dinero o permisos con su prueba **y rompiendo el arreglo a propósito** (la prueba
cae):

- **R7-1 (dinero):** la vendedora (por Facturación) ya no puede escribir el estado, el monto, el entorno, el proveedor, el cobro, los pedidos y facturas
  ligados ni ningún `dcasa_*` de una `payment.transaction`; antes un `write(state='done')` dejaba un pedido pagado sin dinero. Vive en
  `dcasa_base/models/cobros.py` (módulo que ya está en el despliegue, sin dependencias nuevas; sirve a cualquier proveedor); lo del sistema corre con
  `sudo` y no cambia. **R7-2:** gancho `_dcasa_apartado_en_pausa`: el barrido nocturno salta el pedido con un cobro de Yappy abierto **sin borrarle la
  fecha**. **R7-3:** el texto que manda quien llama al aviso ya no llega a la transacción ni al pendiente de Caja (frase fija; el pendiente dice «no se
  pudo aceptar ningún aviso… Mira Yappy Comercial»). **R7-5:** un cobro suelto de Caja en el diario Yappy cuenta como dinero de otra vía (por cliente:
  regla gruesa, falla hacia la revisión). **R7-6:** el botón de Caja exige que Yappy haya recibido la orden (pendiente o con su identificador). **R7-8:**
  la guarda `beforeunload` se quita al cambiar a otro método.
- **Solo documentado:** R7-4 («Administra la nómina» entra por contabilidad: puede confirmar y leer el celular; no se cambió el permiso; YAPPY.md, la
  Guía y PERMISOS.md), R7-9 (qué dominio firma Yappy: supuesto a comprobar en la compra de ensayo, YAPPY.md §8 fila 17; no se aflojó la verificación) y R7-10
  (los textos que no decían lo que pasaba).
- **No se construyó (decisión de la dueña): R7-7**, el rastro del botón de Caja (aviso a Gerencia, filtro «confirmados a mano», motivo, y orden y monto
  en el cuadro de confirmar, que sería un cambio visual): YAPPY.md §14.
- **Pruebas** (base nueva con los 32 módulos, `-u` de los módulos tocados): las 126 de los hallazgos y las que las rodean, en verde; corrida completa de
  `dcasa_base`, `website_dcasa`, `dcasa_pago_tilopay`, `dcasa_pago_yappy`, `dcasa_guia` y `dcasa_comision_web` (1,835 en la primera pasada; las 2 rojas
  eran guardias de `dcasa_base` —la lista blanca de métodos públicos y la búsqueda de `sudo()` sobre pagos— que se arreglaron y se repitieron en verde);
  `ruff check addons` limpio. Mutaciones: 10, todas caen (a propósito). No se tocó `edge/`. **No hace falta `-u` de ningún módulo nuevo** al desplegar
  (`dcasa_base` ya estaba; no hay campos ni datos nuevos; el texto de ayuda de dos campos de Yappy se refresca con `-u dcasa_pago_yappy`).
- **Falta:** una revisión independiente de estos arreglos (la pide la jefa del proyecto), unirlo a la rama de trabajo, y todo lo de siempre antes de cobrar de
  verdad (compra de ensayo, respuestas de Yappy, política de privacidad, conciliación diaria, la decisión de R7-7).

### 2026-11-21 (02:24 UTC): la rama de trabajo unida está EN PRODUCCIÓN (`f81d669d4ca4`, PR #130, Desplegar #78), con Tilopay y Yappy apagados y la comisión web sin versión de reglas

- **Camino (receta de DESPLIEGUE.md):** CI/CD #381 y #382 salieron rojos por dos cosas que no eran del código de negocio y se corrigieron:
  una prueba de fecha de liquidación (un `dict` recortado con `[:10]` da `TypeError` en Python 3.11 —esta máquina— y `KeyError` en
  3.12 —CI e imagen—) y tres pruebas de avisos rechazados de Yappy que provocan a propósito una línea `ERROR` (el CI cuenta como falla
  toda línea `ERROR`/`CRITICAL`, aunque Odoo diga «0 failed»; ahora se capturan con `assertLogs`). **CI/CD #383 sobre `f81d669d4ca4`**:
  7,234 pruebas, 0 fallas, 0 líneas ERROR; borde, Juan, puente, integración, simulacro de restauración e imagen en verde; **staging sano**
  (`version` `f81d669d4ca4`, `base_al_dia` true, 600 s de vigilancia). Se trajo `main` con `merge -s ours` (mismo árbol `9fb0e975bb0b`).
- **PR #130** (squash `d3349ed1`, comprobado: el árbol de `main` = el del commit probado). El primer intento de unirlo lo bloqueó el
  clasificador de permisos hasta que la dueña dijo «sí» (unir y desplegar ahora). **Desplegar #78** a `production` desde `main`:
  `app_version` `f81d669d4ca4229d03fecda204deb5f843ce0fd2`, `imagen_digest` `sha256:706e79546da200b9cf7be5a2772724de4d0a8ae91abb00046d4e9afe75e5d7f3`,
  `respaldo_previo` true; terminó **success** a las 02:24 UTC; `https://dcasapty.com/dcasa/salud` con `version` `f81d669d4ca4`, `base_al_dia`
  true, `humo` ok; `/`, `/shop` y `/contactus` en 200. **No se desplegó Juan** (`juan/` y `puente-wa/` no cambiaron). Se canceló el CI que
  abrió el PR (corre aunque el título diga `[skip ci]`).
- **Qué quedó en producción:** «Forma de pago» en facturas y Exportar para Gerencia, ventas por día, segundos del carrusel configurables,
  Andrés ampliado en escritorio, el rediseño de la pasarela y el lote «legibilidad» (aprobados por la dueña: «Me gustó todo el trabajo»),
  retoques de la web, Tilopay y Yappy directo **instalados y apagados**, la comisión web **sin versión de reglas** (solo mide) y los candados
  de permisos del pago en línea de RV7 y RV8.
- **Revisiones independientes de este tramo:** RV7 y RV8 (Yappy) y RV8b encontraron huecos en los permisos del pago en línea; RV7/RV8 se
  cerraron antes de subir. **RV8b encontró dos puertas más (R9-1 y R9-2)**, ya arregladas en `local/rv7-arreglos` (`cdd25e11`) y en revisión
  RV8c; **no están en producción**. Con los pagos apagados no se explotan, pero **hay que cerrarlas antes de encender cualquier pago**.
- **Sigue:** unir R9 (si RV8c lo aprueba) → CI → staging → producción; luego lo que depende de otros (claves de Tilopay y Yappy en Cloudflare,
  programa de pruebas de Yappy, privacidad, cifras de la comisión web, contadora). La tabla «Historial de despliegues» de CONTEXTO_AGENTICO
  se quedó en Desplegar 15: el historial real vive en esta bitácora.

### 2026-11-20 (tarde): la rama de trabajo unida con todo lo pendiente (`960bf34`), el informe de ChatGPT contrastado con el código, y un audio y un video de 38 minutos para los jefes. SIN subir a producción (sigue `d2ba8caf`)

- **Rama unida y subida a `claude/merge-rama-to-main-ty3koz` (`960bf34`, igual que `origin`; subirla no despliega nada):** «Forma de pago» en facturas,
  ventas por día, retoques de la web, Tilopay (apagado), la comisión web (5 rondas de revisión; última unión `eaf2b33`, sin versión de reglas), el
  rediseño visual de la pasarela, el lote «legibilidad» y **Yappy directo (`4e84bef`, apagado) ya unido**. La dueña vio las capturas antes/después y dijo
  «Me gustó todo el trabajo» (vale como «sí» para la pasarela rediseñada, la legibilidad con el relleno del botón de WhatsApp, ventas por día,
  facturas, Andrés ampliado y las pantallas de comisión) y **eligió el botón gris `dark` de Yappy**; la portada (hero) queda exactamente como hoy.
- **Pruebas:** Workers en verde (borde 319, Juan 1,924 con 40 omitidas, puente-wa 667). La batería completa de Odoo sobre `960bf34` (32 módulos, base
  nueva) y la segunda revisión independiente de Yappy (RV7) estaban en curso al escribir esto: ver la línea «Resultado» de abajo.
- **El informe de ChatGPT** (la auditoría que la dueña hizo preguntándole a Brian): se leyó la conversación entera y se comparó con el código y con lo que
  Brian contestó. Lo aclarado, con el archivo donde vive cada cosa, está en [CONTEXTO_AGENTICO.md](CONTEXTO_AGENTICO.md) («Lo que enseñó contrastar el
  informe de ChatGPT con el código»). **Sigue abierto, para comprobar con el sistema en vivo:** si el interruptor del CRM automático está encendido y
  cuántas cotizaciones no están vinculadas a su oportunidad (de ahí las «cero ganadas»), 111 frente a 93 cotizaciones, el margen de octubre (34.3 % o
  35.9 %) y si los $44.96 de IA ya están dentro de los $111.93.
- **Para los jefes, sin PDF:** un tablero (Artifact «Data», privado) con las cifras claras, y **un audio y un video de 38 minutos** que narran el informe
  completo y resumen cada cuadro (63 diapositivas con la marca), hechos con una **voz local gratis**. La voz profesional (Emma, ElevenLabs, la de la
  marca) costaría ≈ US$7.30 en total: **descartada el 2026-11-23, la dueña ya envió el video a los jefes con la voz gratuita**. Cómo se hizo y qué trampas tuvo, en CONTEXTO_AGENTICO. Los archivos y el guion
  llevan cifras de la empresa: **no** van al repositorio (es público).
- **Falta, en este orden:** el resultado de la batería y de RV7 (arreglar lo que salga) → subir por la receta (§3): staging con todo apagado, verificar,
  producción (Tilopay y Yappy apagados, comisión web **sin** versión de reglas, `-u dcasa_base,dcasa_comision_web,website_dcasa,dcasa_guia` y los módulos
  de pago). Lo que depende de otros: las claves de Tilopay y Yappy en Cloudflare (**nunca por el chat**), el programa de pruebas de Yappy y la compra de
  ensayo, la política de privacidad (Google/Yappy), las cifras de la comisión web y el tratamiento contable (la voz profesional se descartó el 2026-11-23).
- **Resultado de la batería y de RV7:** (se anota abajo al terminar).

### 2026-11-20 (Yappy directo, segunda revisión independiente RV6): sus hallazgos H1–H10 arreglados o documentados, más cuatro retoques que salieron de probar el botón real. En `local/yappy-fix` (sobre `local/yappy`), SIN unir a la rama de trabajo y SIN desplegar

El revisor independiente atacó `96bbd48` y dijo: unir y subir a staging apagado, sí; encender en prueba, sí con una condición (H1); cobrar de verdad, no
todavía (H2, H3, H5, H6). Todo eso está hecho (detalle y tabla en [YAPPY.md](YAPPY.md) §14), y se sumó lo que salió de probar el componente
**real** de Yappy en Chrome (rama `local/yappy`, ya unida aquí). Cada arreglo con su prueba, y **cada prueba se comprobó rompiendo el arreglo a
propósito** (mutaciones en `scratchpad`).

- **Dinero (H2, H3):** nunca un segundo cobro. Un aviso `E` sobre un pedido que ya tiene dinero por otra vía (cobro a mano de Caja, otro cobro en
  línea) o que está **cancelado** va a revisión humana, con su alerta y un mensaje honesto a la clienta (no «Confirmamos tu pedido»). El
  pendiente «sin aviso» se cierra solo cuando llega el aviso. **Política única para Caja:** abrir Yappy Comercial y, si el dinero entró,
  pulsar **«Confirmar que el dinero entró»** en «Pagos con Yappy» (mismo camino que el aviso, un solo cobro, queda quién y cuándo); **no** registrar el
  cobro a mano. El pendiente, la Guía y YAPPY.md §3.4 dicen lo mismo. El apartado que vence por la noche **salta** (no anula) un pedido con un cobro de
  Yappy abierto de menos de 15 minutos, y **su fecha de vencimiento ya no se borra** (la tercera vuelta, RV7, R7-2: antes sí se borraba).
- **Privacidad (H5):** el celular de Yappy, el id de Yappy y la huella son de Caja y superiores **a nivel de campo**; la nota del pedido ya no lleva
  el celular de Yappy. **H4:** la lista exacta de dominios que carga el botón y un borrador de párrafo **sin aplicar** están en YAPPY.md §16 para que la
  dueña decida; el texto legal no se tocó.
- **Aviso (H6) y staging (H1):** el dominio del aviso se normaliza (`http://`, mayúsculas, `:443`, barras) sin dejar pasar uno ajeno (batería de
  813,375 candidatos: 503 aceptados, 0 ajenos); un aviso rechazado deja en el registro el dominio que llegó y el declarado, y el pendiente ya no dice
  «Yappy no avisó» si sí avisó. `YAPPY_URL_BASE` (staging la fija en `edge/wrangler.jsonc` con `https://dcasa-staging.dcasapty.workers.dev`; Odoo la
  ignora en producción) hace que el aviso llegue a staging: **comprobar con el `curl` de YAPPY.md §7 B** y ver si Yappy acepta esa `ipnUrl`.
- **Topes y botón (H7, H8):** el tope de 5 cobros por pedido es estricto en paralelo; Enter mantenida y varios clics no abren más cobros; pruebas que
  matan las dos mutaciones que sobrevivían (`eventSuccess` a otra página y el host de producción roto en el JavaScript).
- **Retoques del botón real:** el gris `dark` se mantiene oscuro con el ratón encima (contraste 6.48:1 y 5.41:1 al pulsar, antes 2.44:1); en «revisión»
  la pantalla de estado no ofrece «Intentar de nuevo»; con un cobro pendiente de menos de 5 minutos de la propia sesión, `/shop/cart` y `/shop/payment`
  mandan a `/payment/status`; aviso del navegador (`beforeunload`) solo mientras hay un intento vivo.
- **Pruebas (conteos exactos, base nueva con los 32 módulos, `scripts/test.sh`):** 1,730 pruebas (Odoo cuenta subpruebas): `dcasa_pago_yappy` 339,
  `website_dcasa` 496, `dcasa_pago_tilopay` 347, `dcasa_contabilidad` 187, `dcasa_guia` 97, `dcasa_base` 389, `dcasa_comision_web` 379; 0 rojas y 2
  errores de Chrome que pasaron al repetirlas solas (`website_dcasa test_pago_celular`, intermitente con y sin Yappy, y la de «atrás» de Yappy, que
  ahora aguanta el instante en que la página cambia: las 23 de navegador de Yappy en verde). Las de concurrencia real (opt-in): 4 de 4. Borde: **319**
  (317 + 2) y `typecheck` limpios; `ruff check addons` limpio.
- **Falta (no es de código):** compra de ensayo contra el Yappy real y las respuestas por escrito de §15; que la dueña decida la política de privacidad
  (§16); su «sí» a las capturas (cambio visual); conciliar a diario desde el primer cobro y la comisión (contadora); revisar a Juan (§11).

### 2026-11-20 (Yappy directo): el Botón de Pago de Yappy Comercial en la tienda, y «qué compró cada persona». En su propia rama (`local/yappy`), SIN unir a la rama de trabajo y SIN desplegar: espera el «sí» de la dueña a las capturas

**Nada de esto está en producción ni en la rama de trabajo.** Es un módulo nuevo, `dcasa_pago_yappy` (ver [YAPPY.md](YAPPY.md)), hermano
de Tilopay, que cobra con el **Botón de Pago de Yappy Comercial** sin sacar a la clienta de la tienda. Trae un cambio visual (la fila
«Yappy» del pago con su campo de celular y el botón de Yappy, y el bloque «Qué compró» en el pedido), así que por la regla del
2026-11-20 se hicieron capturas antes/después (computadora 1440×900 y celular 390, datos inventados, el botón de Yappy es un
**sustituto** con su aspecto documentado) y **no se une ni se despliega hasta su «sí»**.

- **Qué hace:** la clienta escribe su número de Yappy, toca el botón y aprueba en su app. **Solo el aviso firmado de Yappy** (HMAC-SHA256
  en tiempo constante, y el dominio nuestro comprobado **antes** del hash) paga el pedido; lo que diga el navegador no decide nada. Cada caso
  raro (aviso repetido, `R` tras `E`, pago a un cobro ya cancelado, pedido que cambió de total, entorno distinto) termina en un estado
  explicado y, si entró dinero que no cuadra, en **revisión humana** (nunca se paga solo). Si el aviso no llega, a los 15 minutos
  queda un pendiente para Caja (Yappy no tiene consulta de estado).
- **Nace apagado y sin publicar;** las claves solo en Cloudflare (`YAPPY_ID_COMERCIO` y `YAPPY_CLAVE_SECRETA` secretos; `YAPPY_DOMINIO` y
  `YAPPY_ENTORNO` normales; staging fijado en `prueba`). Cuando se ofrece, **reemplaza al «Yappy» manual** de siempre (la tienda lista
  métodos, no proveedores: método propio `yappy_directo`, también llamado «Yappy»), y el cobro cae en el mismo diario «Yappy».
- **Lo que pidió la dueña, «que el equipo vea con claridad qué compró cada persona»:** un bloque «Pago, entrega y origen» arriba de las
  líneas del pedido; una pantalla «Pagos con Yappy» con la tabla de lo que compró (producto y modelo, cantidad, precio, descuento); una
  nota interna en el pedido al entrar el pago; y un pendiente para Caja con el mismo detalle si el aviso no llega. La orden de Yappy empieza
  con el número del pedido, así que el reporte de Yappy Comercial lleva directo al pedido. Sin canal nuevo ni datos del cliente fuera de Odoo.
- **Pruebas (conteos exactos, `scripts/test.sh` en base nueva):** `dcasa_pago_yappy` **208 pruebas, 0 rojas**, con todos los módulos
  instalados (205 corren siempre; 3 de concurrencia real son opt-in con `DCASA_PRUEBA_CONCURRENCIA=1` y, con la variable, pasan);
  `website_dcasa` 382, `dcasa_pago_tilopay` 241, `dcasa_contabilidad` 145 (en verde; 3 de `website_dcasa` piden `dcasa_tienda_borde`
  y pasan con todos los módulos), `dcasa_guia` 81 y `dcasa_base:TestPermisosVendedora` 9 en verde; borde **317** (299 + 18 nuevas) y
  `typecheck` limpios; `ruff check addons` limpio. Las pruebas encontraron dos cosas reales: el menú de «Pagos con Yappy» lo veía la
  vendedora (lo atrapó una guardia de `dcasa_base`) y el controlador del aviso se tragaba el error de concurrencia de PostgreSQL
  (daba 500 en vez de dejar que Odoo repita la petición).
- **Lo que decidí yo (y va en el informe):** método propio `yappy_directo` y retirar al manual en vez de dos filas «Yappy»; reutilizar el
  diario «Yappy» que ya existía; bloqueo de espera (no `SKIP LOCKED`) para no perder un aviso; guardar la orden de Yappy y confirmarla antes
  de llamar a Yappy; 403 sin motivo para un aviso que no cuadra y 500 para un fallo nuestro; aceptar 16 maneras de escribir nuestro
  dominio (Yappy no documenta cómo lo devuelve) en vez de «sin https ni www ni barra»; los ayudantes de Tilopay copiados, no compartidos.
- **Trampa nueva, importante:** `--test-tags /dcasa_pago_yappy` **no corre ninguna prueba** (la expresión regular de Odoo toma «py» por un
  archivo). `scripts/test.sh` ya lo corrige; mirar siempre el conteo de pruebas (CONTEXTO_AGENTICO).
- **Falta:** el «sí» de la dueña a las capturas; la revisión independiente (es dinero); el acceso al programa de pruebas de Yappy
  (`botondepagoyappy@bgeneral.com`) y las preguntas de [YAPPY.md](YAPPY.md) §8; una compra de ensayo; conciliar a diario contra Yappy Comercial;
  la contadora decide la comisión de Yappy (no está modelada); revisar a Juan al encender (YAPPY.md §11, no se tocó).

### Entradas anteriores (una línea cada una; el texto completo en [historico/BITACORA_ANTERIOR.md](historico/BITACORA_ANTERIOR.md))

- **2026-11-19 y 2026-11-20:** «Forma de pago» en facturas, ventas por día, carrusel y Andrés ampliado, Tilopay y la comisión web, en la rama de trabajo
- **2026-11-17 (3) y 2026-11-18:** la segunda entrega completa en producción (CI/CD 380 y Juan 29)
- **2026-11-17 (2):** la portada nueva en producción (CI/CD 377), el hero como fondo en movimiento
- **2026-11-17:** la pantalla «Armar combo», tres arreglos de Socios y del chat, y los parches de IA de Juan
- **2026-11-16 (3):** el Black Friday en producción (Desplegar 77 y Juan 28)
- **2026-11-16 (2):** todo el plan Andrés, voz y portada subido a la rama, incluso lo que quedó a medias (traspaso a otra cuenta)
- **2026-11-16:** Black Friday y «Andrés» listos en la rama sin subir (pausa por límite de uso); plan de la ronda siguiente
- **2026-11-15 (3):** bandas en azul noche y pie claro, menú sin «Escríbenos», contacto y el carrito en el chat, en producción (Desplegar 76); Black Friday y «Andrés» en la rama
- **2026-11-15 (2):** portada v3 (paleta, espaciado, categorías y carriles en una fila, carrito como ícono, chat de vidrio), en producción (Desplegar 75)
- **2026-11-15:** alternativas para Messenger e Instagram sin la revisión de Meta (OpenReply y 14 repos más); solo investigación, ningún cambio
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
