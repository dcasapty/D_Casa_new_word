# Contexto agéntico: errores, incidentes y cómo se resolvieron

Para cualquier agente (o persona) que retome el trabajo en D'CASA. Se lee **antes de desplegar, tocar el arranque
(`docker/entrypoint.sh`), el borde (`edge/`) o los flujos de GitHub** — junto con `docs/LEEME_PRIMERO.md` (cómo se
trabaja con la dueña) y `docs/PRIORIDADES.md` (qué sigue). Casi todo lo que falló es de la misma familia: **código nuevo
sobre una base vieja**, o **una imagen distinta de la que se cree**. Lo marcado **(sin confirmar)** es una deducción de
los registros, no un hecho comprobado.

Armado el 2026-10-16 a partir de `docs/`, los commits y los registros de GitHub Actions (runs de «Desplegar» y de
«CI/CD»). Al terminar cada sesión con algo nuevo que aprender, se agrega aquí (incidente, falla de CI o trampa).

## Reglas que salen de todo esto

1. **«Sano» = la versión desplegada responde, la base está al día con su código y la prueba de humo pasó.** No basta un
   200. `/__edge/health` trae `version`, `base_al_dia` y `humo`; `esperar_salud.sh` los exige. Igual se abre el Inicio
   después de cada despliegue.
2. **El código y la base van juntos.** Código nuevo + base vieja = columnas que faltan (`UndefinedColumn`). Código viejo +
   base nueva = vistas con campos desconocidos, y con `-u` el código viejo **borra** columnas y tablas nuevas con sus
   datos. Nunca bajar una imagen sin restaurar antes la base.
3. **`app_version` es el SHA que construyó el CI** (el de la rama, el de la etiqueta de la imagen), nunca el del *squash*
   en `main`.
4. **Cloudflare activa el Worker antes que la imagen** y puede arrancar la instancia con variables de un arranque
   anterior: la versión que manda es la de la imagen (`/opt/dcasa/COMMIT`).
5. **Toda prueba con fechas congela el reloj** (Panamá es UTC−5: el día cambia a las 05:00 UTC).
6. **Todo método público nuevo va a la lista blanca** de `addons/dcasa_base/tests/test_superficie_rpc.py` con su motivo.
7. **Antes de explicarle a la dueña por qué dos cifras no cuadran, hacer la cuenta con los números de sus capturas y con
   el código que las calcula.** El 2026-10-16 se le dijo que el Inicio no contaba los pedidos viejos S00016–S00021; la
   cuenta (total de facturas − total del Inicio = $236.88, una sola factura sin pedido) mostró que sí los contaba, y hubo
   que corregirlo. Una explicación «razonable» sin la resta es una suposición.
8. **Si después del «sí» de la dueña cambia el código (por ejemplo, por una revisión), decírselo antes de unir a `main`.** El 2026-10-16 el «sí» fue antes de que la revisión independiente encontrara 5 fallas de dinero del bono; se desplegó lo corregido y se le explicó qué cambió antes de cerrar («Sí, termina»).
9. **Lo que corre en el Inicio o en un sondeo (`setInterval`) se mide en consultas con datos de tamaño real antes de
   subir, y lleva una prueba de que no crece con los registros.** El 2026-10-23 un acceso nuevo del Inicio y el panel de
   Bodega (cada minuto) hacían 1.500-1.800 consultas por carga y volvieron lento todo el sistema (incidente 6). En un
   servidor de ½ vCPU con un solo proceso de Odoo, una pantalla pesada frena a todas las demás.
10. **Cuando uno llama a otro (Odoo → Worker → IA), el que llama espera MÁS que el plazo del que contesta, y una prueba
   lo exige.** La varita («Sugerir», 2026-11-06): Odoo se rendía a los 25 s y el Worker no tenía plazo (Meta con
   herramientas tarda más), así que «a veces» la vendedora veía «el Worker no responde» mientras la IA seguía (y se
   pagaba). Ahora el Worker contesta antes de 42 s (`PLAZO_TOTAL_MS`, con el borrador o con un error claro) y Odoo espera
   55 (`TIMEOUT_SUGERIR`); `juan/test/odoo-panel-sugerir.test.ts` lee la línea de Python y exige el margen.
11. **Un fallo que la persona necesita ver no va en una notificación que se va sola**: queda en la pantalla, dice la
   causa en corto y ofrece «Reintentar». La dueña no pudo decir qué salía en pantalla porque el aviso duraba segundos.

---

## Incidentes de producción

### 1. 2026-10-16 · Etapas 1 y 2: «Error de servidor» en el Inicio y en Conversaciones (el despliegue dijo «sano»)

> En notas y comentarios viejos este incidente sale como `#97`: era un número de una lista interna, **no** un issue
> de GitHub.

**Qué vio la dueña** (06:07–06:16 UTC, recién subidas las Etapas 1 y 2): «Error de servidor de Odoo» en el Inicio
(`dcasa.tablero`), en el panel de cada conversación y en todo lo que lee pedidos de venta. La traza decía
`psycopg2.errors.UndefinedColumn: column sale_order.dcasa_utilidad does not exist` (y `dcasa_sin_costo`).

**Qué pasó, con los datos que hay:**

1. El despliegue de las 05:47 (run 7 de «Desplegar», `app_version` `fbf375b0…`) subió el Worker y cambió la
   aplicación de contenedores a la imagen nueva («SUCCESS Modified application»). El chequeo de salud vio un 200 a
   las 05:49 y dijo «sano».
2. A las 06:14 la traza muestra el **código nuevo** (`tablero.py`, `_ganancia_de`) sobre una base **sin las
   columnas nuevas**: el arranque no corrió `odoo -u`.
3. Causa raíz: el arranque decidía actualizar comparando `dcasa.deployed_version` de la base con la variable
   `APP_VERSION`. Cloudflare puede arrancar (o reemplazar en un *rollout*) la instancia con las variables de un
   arranque anterior: la imagen nueva recibió la versión vieja, «coincidía», y no actualizó. Y el chequeo del
   despliegue aceptaba cualquier 200 (el de la instancia vieja o el de la nueva sin actualizar).
4. A las 06:16 un redespliegue con `app_version` = `5fa33f4…` (el *squash* de `main`) falló con
   `IMAGE_REGISTRY_DOESNT_CONTAIN_IMAGE`: la etiqueta de la imagen es el SHA que construyó el CI (el de la rama), y
   ese de `main` no existe en el registro. El Worker nuevo igual quedó activo (Cloudflare activa el Worker antes que
   la imagen) y el registro de la aplicación mostraba otra vez la imagen anterior (`bf40605e…`).

**Cómo se resolvió (de raíz), en dos entregas:**

*Arreglo `3570c3a` (el que arregló producción el 2026-10-16, «Desplegar 9»):*

* La imagen sabe quién es: guarda su commit (`/opt/dcasa/COMMIT`) y la huella de su código (`/opt/dcasa/CODIGO`,
  Odoo + addons). El arranque usa la versión de la **imagen**, no la variable, y actualiza si la huella no coincide
  con la de la base (`dcasa.codigo_desplegado`).
* `/dcasa/salud` dice `version` y `base_al_dia`; `.github/scripts/esperar_salud.sh` exige la versión desplegada con
  la base al día y vuelve a mirar a los 5 minutos (si Cloudflare vuelve a la imagen anterior, el despliegue falla).
* Pruebas: `probar_esperar_salud.sh` (el chequeo viejo daba «sano» en falso en 5 casos), `/dcasa/salud`, y en CI la
  imagen real con la base «actualizada con otro código».

*Entrega siguiente (revisión adversarial del arreglo; en pruebas, todavía no en producción):*

* Nunca hacia atrás: con otro código, una imagen más vieja (fecha del commit, `/opt/dcasa/ORDEN`) que la que
  actualizó la base no la «actualiza» (con `-u` del código viejo Odoo borra columnas y tablas nuevas con sus datos)
  ni toca sus módulos. Para volver atrás: restaurar y desplegar la versión vieja en **una sola operación**
  (`docs/OPERACION.md`); salidas de emergencia `DCASA_PERMITIR_BAJAR` y `DCASA_HUMO=0`.
* Huella vieja: si una imagen anterior a este control marcó la versión después de la huella, la huella no vale.
* Prueba de humo en cada arranque (`dcasa_base/models/humo.py`): cada campo guardado con su columna y el Inicio y
  las listas de cotizaciones y conversaciones armados de verdad. Si faltan columnas, actualiza otra vez (también el
  módulo de Odoo que define el campo).
* `/dcasa/salud` suma `humo`; el despliegue lo exige y vigila 10 minutos sin dar por sano un sitio caído al final.
* Pruebas: `test_humo.py` y en CI la imagen real con una columna borrada con los marcadores «al día», una imagen
  más vieja que la base y `APP_VERSION` atrasada en un contenedor nuevo.

**Lo que hay que recordar:**

* «Sano» = la versión desplegada responde, la base está al día con su código y la prueba de humo pasó. Después de
  cada despliegue igual se abre el Inicio.
* `app_version` siempre es el SHA que construyó el CI (el de la rama, el mismo de la etiqueta de la imagen), nunca
  el del *squash* en `main`.
* El código y la base tienen que ir juntos: código nuevo + base vieja = columnas que faltan; código viejo + base
  nueva = vistas con campos que el código no conoce.

### 2. 2026-10-15 · CI #158 a producción: Odoo respondió 500 durante 20 minutos

- **Qué se vio:** CI/CD #158 (main `b09fdc48` = PR #38 + PR #39) desplegó a las 06:30 UTC; tras el corte de la
  instancia vieja (06:31:55), `/__edge/health` dio `salud_http: 500` (Odoo «Internal Server Error») hasta el límite de
  20 min (06:51:06). Producción quedó con error hasta que Desplegar run 3 la sanó a las 06:58:45 (unos 27 min; no
  consta que la dueña lo viera, era de madrugada en Panamá).
- **Causa raíz (sin confirmar, muy probable):** la misma del incidente 1. PR #38 traía ~56 campos nuevos, 18 vistas,
  datos y una migración. Ese mismo código en staging (CI #153, `22119f35`) dejó el diagnóstico `odoo.sql_db: bad
  query: SELECT "res_users"."id", …` (una columna de `res_users` que no existe = base sin actualizar).
- **Cómo se resolvió:** Desplegar run 3 con la imagen de la rama `5a99f129` (mismo código de PR #38): primero 500 unos
  2,5 min, luego un reinicio («arrancando») y recién ahí sano. El segundo arranque sí actualizó la base (sin
  confirmar).
- **Lección:** «el primer despliegue de una versión deja la base sin actualizar» (este mismo incidente, en la lista vieja de PRIORIDADES) ya había pasado
  aquí y en staging, un día antes del incidente 1.

### 3. 2026-10-15 · Botones de Brian en Telegram fallaban en producción

- **Qué vio la dueña:** «Vincular mi Telegram» y «Registrar webhook» daban `takes 1 positional argument but 2 were
  given`; sin webhook, Brian no recibía nada de Telegram.
- **Causa raíz:** los botones de la cabecera de una lista llaman al método con la lista de ids; los métodos eran
  `@api.model`.
- **Arreglo:** commit `b3e75807` (PR #41, en producción con Desplegar run 5): sin `@api.model`, prueba por `call_kw`
  con `[[]]` y `[[id]]`, y prueba guardia en `addons/dcasa_base/tests/test_superficie_rpc.py`.

### 4. 2026-10-13 · Puerta del equipo en «1»: el personal se quedó sin entrada

- **Qué se vio:** tras CI #132 (18:20 UTC, `30d08696`, PR #32) con `DCASA_PUERTA_OBLIGATORIA = 1`, `/master` respondía
  «Not Found» después del PIN de Access (el borde rechazó el pase) y por `/web/login` ya no se podía entrar.
- **Cómo se resolvió:** PR #33 (`1fc7caa5`, CI #134, 19:21 UTC) volvió a «0».
- **Qué falta:** el motivo nunca se aclaró (ver `puerta_token_rechazado`, campo `motivo`, en los logs del Worker de
  producción). Volver a encender por pasos «0» → «avisar» → «1» (`docs/SEGURIDAD_ACCESO.md` §8).

### 5. Varias fechas · La app de contenedores aparece «revertida» a la imagen anterior (sin confirmar la causa)

Cada `wrangler deploy` imprime el diff de la app `dcasa-odoocontainer` (`- image` = lo que había, `+ image` = lo
nuevo). En **5 de 16** despliegues de producción, lo que había **no** era la imagen del despliegue anterior sino la de
uno antes:

| Despliegue | Esperado en «-» | Encontrado en «-» |
|---|---|---|
| CI #136 (2026-10-14 03:17) | `1fc7caa5` (CI #134) | `30d08696` (mismo contenido, otra etiqueta) |
| CI #147 (2026-10-14 19:12) | `f7dfa349` (CI #138) | `88c54ddd` |
| CI #150 (2026-10-14 21:04) | `228a2bac` (CI #147) | `f7dfa349` |
| Desplegar run 5 (2026-10-15 19:58) | `86d98566` (run 4) | `5a99f129` |
| Desplegar run 8 (2026-10-16 06:16) | `fbf375b0` (run 7) | `bf40605e` |

- **Riesgo:** después de un despliegue «sano», un reinicio posterior del contenedor podía levantar la **imagen
  anterior**; si la base ya estaba actualizada por la nueva, era código viejo sobre base nueva (DESPLIEGUE.md lo prohíbe:
  puede romper vistas y datos; con `-u`, el código viejo borra columnas nuevas).
- **Causa:** desconocida (puede ser un rollout de Cloudflare que se deshace, un *rollback* manual en el panel, u otra
  cosa). No hay en GitHub ningún workflow que lo explique (Desplegar Juan solo tiene 2 runs del 2026-10-13; el del
  puente, ninguno).
- **Qué falta:** que alguien con acceso a Cloudflare mire el historial de *rollouts* de `dcasa-odoocontainer`; y, tras
  cada despliegue, comprobar la etiqueta de la imagen activa además de `/__edge/health`. El arreglo del incidente 1 ayuda (la salud
  dice qué versión responde y la imagen vieja no baja una base nueva), pero no impide la reversión.

### 6. 2026-10-23 · Sistema lento y «Se perdió la conexión» tras la tanda del 22 oct

- **Síntoma:** la dueña: «el sistema está bastante lento», y el aviso «Se perdió la conexión. Tratando de
  reconectar…» seguido. En sus registros del Worker (15:36-15:40 UTC): fotos que contestan 304 tardando 1-21 s, el
  Inicio 2,5-26 s, y tres `reenvio_fallido` «Error: Network connection lost.» tras 11-15 s.
- **Causa de la lentitud (medida):** `dcasa_barras` (`3174f9a`) agregó al Inicio el acceso «Bodega» con cuántas
  entregas esperan; para saber cuáles tienen pago armaba `invoice_payments_widget` factura por factura, y el panel de
  Bodega hacía lo mismo cada minuto. En local (catálogo real + 270 ventas): 1.511 consultas el Inicio, 1.800 el panel.
  Con un solo proceso de Odoo y ½ vCPU, eso frena todas las demás peticiones (hasta un 304 de una foto).
- **El corte de conexión:** entre el Worker y el Durable Object (los eventos con «stateless» no tienen su evento de
  `OdooContainer`); las peticiones a la par salían bien, así que **no** fue Odoo reiniciándose: medido en local, la
  memoria virtual con 60 peticiones a la vez llega a ~600 MiB (límite suave 1,5 GiB) y `MALLOC_ARENA_MAX` no cambia
  nada. Cloudflare recomienda reintentar ese error.
- **Arreglo:** `_pagos_de_pedidos` saca los cobros de todas las facturas en una búsqueda (Inicio 139 consultas, panel
  34; igual resultado en los 270 pedidos) y el borde repite las lecturas (GET/HEAD y lecturas de Odoo conocidas, nunca
  lo que guarda) hasta 2 veces (`2986df5`, `34fea73`). En producción con Desplegar 27 (18:12 UTC).
- **Después, por la revisión independiente:** solo se repite un corte que llega antes de 5 s (`CORTE_RAPIDO_MS`): uno
  más tardío quiere decir que Odoo ya estaba trabajando en esa petición (con `workers = 0` la termina aunque nadie
  espere) y repetirla le suma carga a un servidor ocupado. El registro `reenvio_fallido` anota `ms`: si los cortes de
  producción siguen llegando tarde, el reintento no los cubre y hay que buscar la causa (no subir el límite a ciegas).
- **Cómo se halló:** una revisión del diff `8cd21bf..04d7a2a` en paralelo con una base local con todos los módulos y
  datos de tamaño real, cronometrando cada pantalla lenta del registro (tiempo, CPU y `cr.sql_log_count`) y
  `cProfile` sobre la peor. La pista de la dueña («algo de lo último que implementamos») era correcta.

### Incidentes anteriores (staging o antes de producción), en una línea cada uno

- **2026-10-01** · El contenedor no arrancaba en Cloudflare: `pg_ctl -l /dev/stderr` falla con ENXIO porque ahí stderr
  es un socket → `1db6348` (no reabrir `/dev/stderr`; el lint del CI lo vigila).
- **2026-10-02** · Staging dormido: la página cacheada salía sin estilos (CSS/JS de Odoo daban 503 al despertar) →
  `5668ac4` (staging 24/7 en ese momento; hoy la doc dice que duerme tras 1 h — sin confirmar el valor vigente).
- **2026-10-02** · `rootMargin: "--85px"` → SyntaxError y «¡Vaya! Ocurrió un error» al abrir una página ya desplazada →
  `724da06`, `2c8318e`.
- **2026-10-07** · Factura PDF sin diseño en staging: wkhtmltopdf pedía estilos a `web.base.url` (pública, inalcanzable
  desde el contenedor) → `c2cc756` (pide a `127.0.0.1`).
- **2026-10-09** · SCSS con `min(%, px)` dejó todo el backend sin los estilos de D'CASA («Incompatible units») →
  `4e7768d` (`unquote()`); lo atrapó la batería completa.
- **2026-10-10** · Fotos y PDF no llegaban por Telegram en staging: `CANONICAL_HOST` apuntaba a un dominio sin ruta →
  `46e675d` (por defecto, el anfitrión de `URL_SITIO`).
- **2026-10-10** · Fusionar contactos fallaba («ya es de…») si la ficha que queda no tenía los datos → `497f0fd`.
- **2026-10-12/13** · Una factura real de un cliente y sus datos estaban en el repositorio (en un test) → `d903035`
  (PR #29).
- **2026-10-13** · Riesgo: con los secretos de producción cargados, un push a `main` habría desplegado sin aprobación
  («Required reviewers» no está disponible en el plan para repos privados) → `04e9bd6` (producción solo a mano y desde `main`).
- **2026-10-14** · Pantallas propias (Contabilidad, Guía, Inicio, Juan) no bajaban con scroll en computador: Odoo pone
  `overflow:hidden` en `.o_action` → `77e5f4e` (PR #35) y `64beb7d` (PR #37).
- **2026-10-14 y 15** · Staging dio 500/503 en la salud tras desplegar código con campos nuevos: CI #140 y Desplegar
  run 2 (`b83f515d`, vendedores) y CI #153 (`22119f35`, PR #38; diagnóstico «bad query» en `res_users`). Misma
  familia que los incidentes 1 y 2 (para el 2026-10-14, sin confirmar). Se agregó el diagnóstico de staging
  (`a1e89e41`, `5a99f129`).
- **Despliegue 95 (staging, fecha sin confirmar)** · 20 min con `contenedor: stopped`: la espera visitaba la portada,
  que sale de la copia del borde y no despierta a Odoo → `esperar_salud.sh` visita `/web/login`
  (`docs/auditoria/ronda8/crm-juan-brian.md`).

---

## Historial de despliegues a producción

Antes del 2026-10-13 no hubo producción (el intento del 2026-10-02 se omitió por falta de secretos). Hasta el
2026-10-15 06:30 se desplegó con **CI/CD** (`ci.yml`, «Run workflow» en `main`, `desplegar_en = produccion`, que llama a
`desplegar.yml` y usa la imagen construida de `main`); desde entonces con **Desplegar** (`desplegar.yml`, imagen ya
probada en staging, `app_version` = SHA de la rama). «¿Base?» = si el cambio traía campos, vistas, datos, seguridad o
módulos nuevos (o sea, si necesitaba `odoo -u`). Conteos hechos con `git diff` entre las imágenes desplegadas.

| Run | Fecha UTC | app_version | PR / cambio | ¿Necesitaba actualizar la base? | Resultado | Notas |
|---|---|---|---|---|---|---|
| CI #117 | 2026-10-13 02:02 | `651a9a11` | PR #28 «Unir la rama de trabajo a main: sistema completo» (+ commit de up media) | Sí: instalación inicial (base nueva, `-i`) | Sano (~10 min) | Primer despliegue; sin respaldo previo (el Worker no existía) |
| Desplegar 1 | 2026-10-13 02:54 | `651a9a11` | Lanzado sobre PR #29, pero con la imagen de antes | No | Sano con aviso «En 5 min no vi el cambio de instancia» | Contenedor «no changes»; no cambió nada. digest `2b294d1e…` |
| CI #119 | 2026-10-13 04:54 | `0cb45043` | PR #29 privacidad (solo un test de `dcasa_invoice`) | No | Sano (~25 s tras el corte) | digest `7c292678…` |
| CI #128 | 2026-10-13 16:12 | `af8a902f` | PR #30 importador del sistema anterior | **Sí**: módulo nuevo `dcasa_migracion`, ~32 campos, vistas, seguridad | Sano (~2,7 min) | No hay registro de si el primer arranque hizo `-u` (sin confirmar). digest `e1a4570a…` |
| CI #132 | 2026-10-13 18:20 | `30d08696` | PR #32 puerta del equipo «1» (+ PR #31: pagos con su número) | No (variable del Worker; `dcasa_migracion` sin campos) | Sano, pero `/master` daba «Not Found» | Incidente 4. digest `4fe124c9…` |
| CI #134 | 2026-10-13 19:21 | `1fc7caa5` | PR #33 puerta vuelve a «0» | No (misma imagen que #132) | Sano | Rescate. digest `4fe124c9…` |
| CI #136 | 2026-10-14 03:17 | `88c54ddd` | PR #34 importador: clientes repetidos; Brian edita varios productos | No (solo `.py`, sin campos) | Sano | Antes había `30d08696`, no `1fc7caa5` (incidente 5, mismo contenido). digest `4346ed43…` |
| CI #138 | 2026-10-14 07:02 | `f7dfa349` | PR #35 Contabilidad: pantallas vuelven a bajar (SCSS) + docs | No (solo estáticos) | Sano | digest `9932dafa…` |
| CI #147 | 2026-10-14 19:12 | `228a2bac` | PR #36 combos nativos, chat, plan de vendedores, Guía, permisos | **Sí**: módulo nuevo `dcasa_guia`, ~121 líneas de campos, 9 vistas, datos, seguridad | Sano (~2,5 min) | Antes había `88c54ddd`, no `f7dfa349` (incidente 5). El mismo código de vendedores dio 500 en staging. digest `5d81ffc3…` |
| CI #150 | 2026-10-14 21:04 | `9596b8c9` | PR #37 scroll de pantallas propias | No (solo estáticos) | Sano | Antes había `f7dfa349`, no `228a2bac` (incidente 5): pudo correr código viejo sobre la base de PR #36 (sin confirmar). digest `1c7cf1c1…` |
| CI #158 | 2026-10-15 06:30 | `b09fdc48` | PR #38 «Ronda de mejoras» + PR #39 (solo prueba) | **Sí**: ~56 campos, 18 vistas, datos, seguridad, 1 migración | **Falló**: 500 de Odoo 20 min | Incidente 2. Las pruebas de main (CI #156) habían fallado antes por la fecha (ver CI) |
| Desplegar 3 | 2026-10-15 06:55 | `5a99f129` | Mismo código de PR #38 (imagen de la rama) | Sí | Sano 06:58 tras 500 y un reinicio | El reinicio sí actualizó (sin confirmar). digest `d8badcc4…` |
| Desplegar 4 | 2026-10-15 18:43 | `86d98566` | PR #40 Inicio de vendedoras, Actividad, Escáner, nota de entrega fácil, Brian solo para el jefe | **Sí**: campo `dcasa_entrega_facil` (empresa), 2 vistas, datos | Sano (~2,5 min) | Una hora después la app volvía a tener `5a99f129` (incidente 5). digest `378b46b3…` |
| Desplegar 5 | 2026-10-15 19:58 | `b3e75807` | PR #41 botones de Brian en Telegram (incluye PR #40) | No por sí mismo; arrastra lo de PR #40 | Sano (~2,5 min) | Incidente 3 resuelto. digest `213aa34f…` |
| Desplegar 6 | 2026-10-16 02:29 | `bf40605e` | PR #42 orden de impresión: entrega → factura → copia | **Sí**: campo `incluir_entrega` en el asistente de impresión, 2 vistas, datos | Sano (~2,4 min) | Si el primer arranque no actualizó, abrir «Imprimir documentos» fallaría (sin confirmar). digest `2912bb69…` |
| Desplegar 7 | 2026-10-16 05:47 | `fbf375b0` | PR #43 Etapas 1 y 2 | **Sí**: ~12 campos (`dcasa_utilidad`, `dcasa_sin_costo`…), 4 vistas, datos, seguridad | «Sano» **en falso** (7 s tras el corte) | Incidente 1 a las 06:07. digest `f61b9adf…` |
| Desplegar 8 | 2026-10-16 06:16 | `5fa33f4c` | PR #44 (solo docs): SHA del *squash* de `main` | — | **Falló**: `IMAGE_REGISTRY_DOESNT_CONTAIN_IMAGE` | Respaldo previo hecho; el Worker nuevo quedó activo; la app seguía en `bf40605e` |
| Desplegar 9 | 2026-10-16 07:20 | `3570c3a1` | Arreglo del incidente 1 (imagen con commit y huella; chequeo estricto) | **Sí**: la huella de la base no existía, así que actualizó todo (aplicó por fin las Etapas 1 y 2) | **Sano y confirmado** 07:22 → 07:27 (versión `3570c3a12e55`, `base_al_dia` true, 5 min de vigilancia) | El primer minuto respondía la instancia anterior (sin versión) y el chequeo nuevo **no** la dio por sana. La dueña confirmó Inicio y conversaciones. Staging igual en CI #171. digest `4e9b9155…` |
| Desplegar 10 | 2026-10-16 13:12 | `d37af4fd` | Etapa 3, prueba de humo del arranque, «nunca hacia atrás», Conversaciones #25 punto 1, botón «Volver a una versión estable» (PR #46) | **Sí** (Etapa 3 y Conversaciones; la huella cambió y actualizó) | **Sano y confirmado** 13:25 (versión `d37af4fde5b2`, base al día, humo ok, tras 10 min de vigilancia) | Con el «sí» de la dueña. Staging igual en CI #174. digest `015dbd40…` |
| Desplegar 11 | 2026-10-16 14:57 | `9be426a4` | Inicio: cotizaciones y entregas arriba con acento, «Ganancia bruta», cuadre exacto con Contabilidad; Contabilidad: aviso de utilidad sin costo de ventas, «Vencido» sin negativos | No (vistas, plantillas y estilos; sin campos nuevos) | **Sano y confirmado** 15:11 (versión `9be426a46e15`, base al día, humo ok, tras 10 min de vigilancia) | Con el «sí» de la dueña («tan pronto puedas subir las correcciones a producción hazlo»). Staging igual en CI #178. digest `876ca5f5…` |
| Desplegar 12 | 2026-10-16 19:25 | `431cbfe8` | Bono por meta de ventas (1 % si se llega a la meta; a la primera planilla del mes siguiente), aviso de pedidos repetidos, avisos del chat «En Odoo» y contador en rojo | **Sí** (modelos y campos nuevos de Nómina, `comision_meta` en la línea; la huella cambió y actualizó) | **Sano y confirmado** 19:38 (versión `431cbfe80d88`, base al día, humo ok, tras 10 min de vigilancia) | Con el «sí» de la dueña («avísame cuando esté y si tienen mi si») y, tras las correcciones de la revisión, «Sí, termina». Staging igual en CI #182. digest `3894d505…` |
| Desplegar 13 | 2026-10-16 21:49 | `60803c6d` | Inicio de la vendedora: porcentaje de la meta grande, barra y palabras de ánimo (PR #50) | No (plantilla, estilos y datos del Inicio; sin campos nuevos) | **Sano y confirmado** ~22:02 (versión `60803c6d50e3`, base al día, tras 10 min de vigilancia) | Con el pedido de la dueña («sube … a producción en cuanto puedas»). Staging igual en CI #184. Todavía mostraba la meta en dinero y el 1 %: la dueña pidió quitarlos (va en el despliegue siguiente). digest `0818f42a…` |
| Desplegar 14 | 2026-10-16 23:07 | `7b534ad7` | Vendedora sin cifras de dinero y «Ver mis ventas»; Juan: domingo hasta las 5, inglés, crédito/entregas/descuentos (PR #51) | Sí: campo del domingo en Ajustes de Juan | **Sano y confirmado** 23:20. El Worker de Juan se desplegó aparte (Desplegar Juan, `entorno=production`) a las 23:23 desde `3b678a6` | digest `165e71c3…` |
| Desplegar 15 | 2026-10-17 00:21 | `256d1222` | Inicio de Gerencia contra el mes pasado; precio y cámara en el Escáner (PR #52) | No (métodos, plantillas, estilos) | **Falló sin tocar nada**: el respaldo previo recibió un 429 de R2 («Reduce your concurrent request rate for the same object») en pgBackRest; el volcado lógico sí se hizo. **Segundo intento sano y confirmado** 00:36 | El script de respaldo previo no reintenta un 500; ante un 429 de R2 basta volver a lanzar «Desplegar». digest `37f59b2e…` |

**Qué puede no haberse aplicado nunca en producción:**

1. **PR #43 (Etapas 1 y 2): aplicado desde Desplegar 9** (07:22). Entre las 05:47 y las 07:22 no lo estuvo
   (columnas inexistentes a las 06:07-06:16 e imagen revertida a `bf40605e`). PR #44 es solo documentación.
2. **PR #42, #40, #36 y #30:** necesitaban `-u`; ningún registro de GitHub prueba si el primer arranque lo hizo. El
   chequeo viejo solo fallaba si la columna que falta la usa `/dcasa/salud` (p. ej. `res_users`), así que un «sano» no
   lo garantiza (sin confirmar). Los despliegues siguientes cambiaron `APP_VERSION` y probablemente pusieron la base al
   día en algún reinicio; el primer despliegue con el arreglo del incidente 1 hará `-u` completo y debería cerrar cualquier hueco.
3. **Reversiones (incidente 5):** el código de PR #35 (CI #138→#147), PR #36 (CI #147→#150) y PR #40 (Desplegar 4→5)
   pudo dejar de correr durante horas; quedó cubierto por el despliegue siguiente, que lo incluía.
4. Desde Desplegar 9 (arreglo del incidente 1) `/__edge/health` dice `version` y `base_al_dia`, y ese primer arranque actualizó
   **todos** los módulos (no había huella en la base): lo que hubiera quedado sin aplicar de PR #42, #40, #36 y #30
   quedó aplicado ahí. Igual, después de cada despliegue se abren el Inicio, Conversaciones e «Imprimir documentos».

---

## Fallas de CI y cómo se arreglaron

- **CI #181** (`05be252`, 2026-10-16) · 3 FAIL en `dcasa_interfaz`: (a) `test_avisos` ×2: hacer que `base.group_user` implique `mail.group_mail_notification_type_inbox` no cambia `notification_type` (Odoo 19 lo calcula con `group_ids`, los grupos asignados directo, no con `all_group_ids`). Arreglo `132c5ec`: `res.users.create` deja «En Odoo» al usuario interno nuevo y una función de una sola vez pasa a los que ya existían. (b) `test_tablero_lee_la_semana_de_una_vez`: los pedidos repetidos del Inicio hacían un `search` de `sale.order`; ahora `search_fetch` con los campos que usa (una lectura). El log de la API llega cortado (las ~3,000 últimas líneas son del PostgreSQL de servicio): reproducir en local con `scripts/test.sh <módulo>` es más rápido que buscar el traceback.

Últimos 60 runs de CI/CD (#112 a #171). Fallaron: #112, #139, #140, #151, #152, #153, #155, #156, #158, #167
(cancelados: #109, #116, motivo sin confirmar). Truco para leer los registros de «Tests de Odoo»: las últimas ~500 líneas
son el log del PostgreSQL de servicio (`FATAL: role "root" does not exist`, duplicados y *checks* que las pruebas
provocan a propósito: ruido). El resultado real está en la línea `✖ Fallaron la instalación o los tests. Detalle:` y las
`FAIL:`/`ERROR:` que la siguen.

### Tests de Odoo

- **CI #271** (`98f6c51`, 2026-11-06) · La calculadora de envíos: 1 falla en 4674,
  `TestHerramientas.test_contrato_para_modelos_pequenos` («269 not less than 260 : cotizar_envio»). La descripción de
  una herramienta de Brian tiene que tener **menos de 260 letras** y como mucho 5 parámetros (para los modelos
  pequeños). El agente que la hizo corrió «como el CI» sus módulos, pero no las pruebas de `dcasa_brian`. Arreglo:
  `3682053` (227 letras). **Regla:** toda herramienta nueva de Brian se prueba con `TEST_TAGS=/dcasa_brian:TestHerramientas`.
- **CI #211** (`52fa1ec`, 2026-10-22) · Tanda del 22 oct unida (ocho ramas). El registro no se pudo bajar (la API da
  la dirección del blob y el proxy de esta máquina la bloquea con 403; `get_job_logs` del MCP de GitHub con
  `tail_lines` sí funciona). Una corrida completa en local halló las causas: (a) `dcasa_existencias` exige motivo en
  todo ajuste de inventario y el importador (`dcasa_catalogo/inventario_anterior.py`) y las existencias de prueba no lo
  daban → `74d7099` (`inventory_name` en el contexto); (b) la prueba de «Telegram caído» de las alertas deja a propósito
  un `ERROR` en el registro y `scripts/test.sh` falla con cualquier `ERROR` → `5c1a96f` (`assertLogs`). **Regla:** un
  módulo que agrega una exigencia (motivo, grupo, candado) rompe a los demás que escriben ese modelo; buscarlos con
  `grep` antes de unir, y toda prueba que provoca un `ERROR` lo atrapa con `assertLogs`.
- **CI #212** (`5c1a96f`) · Las pruebas de Odoo pasaron, pero «Imagen Docker» falló al instalar: `ParseError …
  copiar_views.xml … action_dcasa_precios_combo no es una acción válida en product.product`. Causa: la rama de combos
  agregó el botón a `product.product_template_form_view`, y la ficha de la variante (`product_normal_form_view`,
  `mode=primary`) hereda de ella; el método solo existe en `product.template`. Se notó recién cuando otra rama
  (copiar) heredó la ficha de la variante y Odoo la validó entera. Arreglo `abfe96f`: el botón hereda de
  `product.product_template_only_form_view`, con prueba de que la variante carga sin él. **Regla:** un botón
  `type="object"` en la ficha del producto va en `product_template_only_form_view` salvo que el método exista también
  en `product.product`.

- **CI #139** (`b1cf3c4d`, 2026-10-14) · Síntoma: `FAIL: TestSuperficieRpc.test_metodos_publicos_en_lista_blanca`
  (1 de 2440). Causa: métodos públicos nuevos de Vendedores sin anotar. Arreglo: `b83f515d` →
  `addons/dcasa_base/tests/test_superficie_rpc.py` (lista blanca con motivo; cada acción exige grupo en el servidor).
- **CI #151** (`2a2e1d2d`, 2026-10-15) · Síntomas: `FAIL` en `dcasa_guia` `test_guia` [cotizacion] y `test_llevame`
  («lo que más usas»), `ERROR` en `dcasa_conversaciones` `test_atajos_inicio` (×2). Causas: la búsqueda sin tilde no
  encontraba «cotización»; prueba que dependía del reloj; el atajo de Oportunidades es de Gerencia. Arreglos: `66ab466`
  (búsqueda), `2c6e978e` (`addons/dcasa_guia/tests/test_llevame.py`), `22119f35`
  (`addons/dcasa_conversaciones/tests/test_atajos_inicio.py`).
- **CI #152** (`2c6e978e`) · Quedaban los 2 `ERROR` de `test_atajos_inicio` → `22119f35`.
- **CI #155 (PR #38) y #156 (main `e717a91d`)**, 2026-10-15 05:33 UTC · Síntoma: 3 `FAIL` en
  `TestDocumentosIntactos` (`test_factura_simple_pagada_igual`, `test_pedido_confirmado_igual`,
  `test_pedido_de_compra_igual_salvo_el_qr`). Causa: el HTML aprobado llevaba la fecha del día en que se generó y
  falló en cuanto Panamá pasó al 15 de octubre (05:00 UTC); CI #154 (04:46) había pasado. Arreglo: `b8b03c0` (PR #39)
  → `addons/dcasa_invoice/tests/documentos.py` y `tests/aprobado/pedido_confirmado.html` (reloj fijo).
- **CI #167** (`6bae4798`, 2026-10-16) · Síntoma: `FAIL: TestEquipo.test_el_menu_empleados_tiene_el_icono_de_la_marca`
  (1 de 3391). Arreglo: `fbf375b0` → `addons/dcasa_equipo/tests/test_equipo.py` («ícono de Empleados»); CI #168 en verde.

### Integración Juan (Odoo real + Worker real)

- **CI #215** (`9541408`, 2026-10-23) · 7 de 40 fallaron: la primera («bienvenida y pregunta por camas queen») con
  «(sin guion)», y las demás en cadena (`sinGuion` se acumula entre pruebas y sin la primera no hay `convId`: «conversacion_id
  tiene que ser un número entero»). Causa: desde F5 los nombres se guardan en MAYÚSCULAS y `juan_buscar_productos`
  desempata por nombre; con el catálogo real cargado, «cama queen» trajo otras cinco camas antes que la de la prueba.
  Arreglo `75324c5`: el guion busca «cama roble queen». **Regla:** cuando la primera prueba de la historia falla, las
  otras son ruido; arreglar esa y volver a correr.
- En esta máquina, `scripts/integracion_juan.sh` se corre **sin** `$S/bin` en el `PATH`: esa carpeta del scratchpad tiene
  un `curl` y un `npx` falsos de otra prueba y la integración «pasa» sin correr nada (el 23 oct dio «✔ OK» en falso).
  Con el `curl` y el `npx` de verdad (y `PYTHONPATH` con PyPDF2 2.12.1) corre completa: 40/40.

- **CI #151** · 7 de 40 pruebas de `juan/test/integracion/flujo.test.ts` fallaron (`«conversacion_id» tiene que ser un
  número entero`, «petición 3 sin paso en el guion», actividades vacías). Arreglo: `2c6e978e` →
  `juan/test/integracion/historia.ts` («la foto de Juan se pide con el código público»). Relación exacta entre
  síntomas y arreglo: sin confirmar.

- **CI #173 (2026-10-16)** · 6 de 40 fallaron con «Eso de la conversación no se cambia a mano (seguimiento_proximo)»: el
  candado nuevo de Conversaciones (#25) bloqueaba a las pruebas, que preparan sus casos escribiendo como **admin**
  por RPC. Al revisarlo apareció un hueco del candado: se saltaba con la clave del sistema en el contexto, y el
  contexto lo manda el cliente. Arreglo `6e031e9`: solo sudo o el administrador del sistema cambian esos campos.
  **Regla:** una clave en el contexto no es seguridad en un modelo donde el usuario tiene permiso de escritura (sí
  lo es donde el permiso de escritura es 0, como `dcasa.mensaje` y `brian.accion`). Antes de un candado nuevo,
  buscar quién escribe ese modelo en `juan/test/integracion/`.
- En local, 2 pruebas de «cotización automática» fallan por la versión de PyPDF2 de esta máquina (3.0.1; Odoo usa
  2.12.1 en CI): no es del código.

### Lint

- `7b3aef2` (2026-10-03): shellcheck SC2015 («A && B || C») en `archivar_fuentes.sh`.
- `fb563c7` (2026-10-01): el runner usa shellcheck 0.9, que marca SC2317 en la función del `trap EXIT` (las versiones
  nuevas la llaman SC2329).
- `0e2e9e2` (2026-10-09): línea de importaciones más larga de lo permitido (probablemente ruff).
- (Los runs exactos de estas tres fallas son anteriores a #112: sin confirmar.)
- Parecido, pero lo vigila una prueba y no el lint: descripciones de herramientas de Brian/Juan por encima del tope
  (`6bae4798`, tope de 260 caracteres; `ecd76f5`, contrato de herramientas de Juan). Run sin confirmar.

### Imagen y artefactos

- **CI #112** (`04e9bd6d`, 2026-10-13 00:35) · Síntoma: `Failed to CreateArtifact: Artifact storage quota has been
  hit` (job «Simulacro de restauración»). Causa: cada despliegue guardaba la imagen (~420 MB) como artefacto. Arreglo:
  `433c873` → `.github/workflows/limpiar-artefactos.yml`, `.github/scripts/limpiar_artefactos.sh`, copias de 1 día y
  los registros de diagnóstico ya no ponen el run en rojo (`docs/OPERACION.md`).
- `1db6348` (2026-10-01): imagen que no arrancaba en Cloudflare por `/dev/stderr` (ver incidentes anteriores).

### Despliegue

- **Desplegar 29** (producción, misma imagen `ab94128`, 2026-10-26 22:58 UTC, traslado a `dcasapty.com`) · El respaldo
  previo pidió `https://dcasapty.com/__edge/respaldo` y dio `curl: (6) Could not resolve host`: `URL_SITIO` ya era el
  dominio y sus registros A y CNAME ya estaban borrados, pero el dominio propio del Worker solo se crea en el paso
  «wrangler deploy», que va después. No se desplegó nada. Con el «sí» de la dueña, **Desplegar 30** con
  `respaldo_previo = false` (misma imagen: la base no cambia). **Regla:** el día que cambia `URL_SITIO` a un dominio
  nuevo, el respaldo previo no puede pasar; o se despliega sin él (con el «sí») o antes se respalda con la dirección
  vieja.
- **Desplegar 30** (23:04 UTC) · `wrangler deploy` salió bien pero **sin el dominio**: «Deployed dcasa triggers» solo
  listó workers.dev y los cron. Causa: **Desplegar hace checkout de `app_version`**, no de `main` («HEAD is now at
  ab94128» en el registro), y `edge/wrangler.jsonc` de `ab94128` no tenía `routes` (entraron en `de1fb04`). «Misma
  imagen, otro commit» no sirve para cambios de `wrangler.jsonc`. Arreglo inmediato: la dueña agregó los dos dominios a
  mano (Workers › dcasa › Domains › Add Domain, que es lo mismo que haría wrangler); arreglo de fondo: CI #230 sobre
  `main` (`741930d`, árbol = `de1fb04`) a staging y Desplegar con ese `app_version`. **Regla:** un cambio del borde
  (rutas, `vars`, `workers_dev`) se despliega con un `app_version` que lo contenga, o sea con una imagen construida
  de ese commit.
- **Desplegar 54 y Desplegar Juan 7** (18:52 UTC del 6 nov, `3fb5770`, imagen `sha256:29309f79…` de CI #280, respaldo
  previo) · Odoo sano y confirmado 19:07 (versión `3fb5770cdf1a`, base al día, humo ok): Camila etapa 2 con los 11
  arreglos de su revisión adversarial (PR #87, `main` = `3195d7d`, árbol = `3fb5770`; migración `19.0.2.0.0`). Juan
  desde `main` a la vez (`campana_correo` en su prompt): `/salud` con la versión `3195d7d`. El CI del PR (#281) se canceló.
- **Desplegar 53** (16:15 UTC del 6 nov, `61d5c44`, imagen `sha256:14d30d8e…` de CI #278, respaldo previo) · sano y
  confirmado 16:30 (versión `61d5c442dffa`, base al día, humo ok): solo documentación (PR #86, `main` = `dc45e48`),
  desplegada con imagen nueva para que el contenedor arrancara con `RESEND_CAMPANAS_API_KEY`, que la dueña pegó en el
  panel. El CI del PR (#279) se canceló.
- **Desplegar 52** (11:13 UTC del 6 nov, `b84e57d`, imagen `sha256:dfbf424f…` de CI #276, respaldo previo) · sano y
  confirmado 11:27 (versión `b84e57d2dacb`, base al día, humo ok): Camila etapa 1, módulo nuevo `dcasa_camila`, con
  los 12 arreglos de su revisión adversarial (PR #85, `main` = `0d69999`, árbol = `b84e57d`). Incluye `edge/` (la
  variable `RESEND_CAMPANAS_API_KEY` en la lista blanca del contenedor). El CI del PR (#277) se canceló. Juan no cambió.
- **Desplegar 51 y Desplegar Juan 6** (08:59 UTC del 6 nov, `a307425`, imagen `sha256:f0b0b240…` de CI #274, respaldo
  previo) · Odoo sano y confirmado 09:13 (versión `a30742505947`, base al día, humo ok): la varita («Sugerir») escribe
  siempre o dice por qué (PR #84, `main` = `237d2f3`, árbol = `a307425`). Juan desde `main` a la vez: `/salud` con la
  versión `237d2f3` y `whatsapp_cloud` configurado. El CI del PR (#275) se canceló.
- **Desplegar 50** (07:33 UTC del 6 nov, `3682053`, imagen `sha256:53e76dc6…` de CI #272, respaldo previo) · sano y
  confirmado 07:47 (versión `3682053cbbbc`, base al día, humo ok): la calculadora de envíos, módulo nuevo
  `dcasa_envios` (PR #83, `main` = `e924a9c`, árbol = `3682053`). CI #271 había fallado por la descripción de una
  herramienta de Brian (ver Tests de Odoo). El CI del PR (#273) se canceló. Juan no cambió.
- **Desplegar 49 y Desplegar Juan 5** (05:46 UTC del 6 nov, `8701e17`, imagen `sha256:64ae4de1…` de CI #264, respaldo
  previo) · Odoo sano y confirmado 05:59 (versión `8701e17f1afa`, base al día, humo ok): WhatsApp oficial guarda el
  mensaje antes del 200 a Meta y la documentación unida (PR #82, `main` = `24d3207`, árbol = `8701e17`). Juan desde
  `main` (`desplegar-juan.yml`, `entorno = production`, `dry_run = false`), a la vez: `wrangler deploy` bien;
  `/salud` con `whatsapp_cloud` configurado y la versión `24d3207`; el único aviso es el de siempre (falta
  `ANTHROPIC_API_KEY` de respaldo). El CI del PR (#270) se canceló.
- **Desplegar 48** (03:42 UTC del 6 nov, `ca5f98f`, imagen `sha256:46c5231f…` de CI #262, respaldo previo) · sano y
  confirmado 03:56 (versión `ca5f98f69b51`, base al día, humo ok): el mantenimiento (PR #77, `main` = `4f66c2c`,
  árbol = `ca5f98f`). El CI del PR (#263) se canceló. Las dependencias nuevas de Juan entraron con Desplegar Juan 5.
- **Primer ensayo de «Volver a una versión estable»** (staging, `estable-3`, run 42149850218, 6 nov) · sano en unos
  12 minutos, ya con las acciones nuevas de Dependabot. Ver [VERSIONES_ESTABLES.md](VERSIONES_ESTABLES.md).
- **Desplegar 47** (21:31 UTC del 5 nov, `e97958e`, imagen `sha256:aa3c4c06…` de CI #260, respaldo previo) · sano
  21:45 (versión `e97958e01847`, base al día, humo ok): «Guardar y responderle» (PR #76, `main` = `700c34a`, árbol =
  `e97958e`). El CI del PR (#261) se canceló. Juan no cambió.
- **Desplegar 46** (19:33 UTC del 5 nov, `cbaff7a`, imagen `sha256:14f3fe34…` de CI #258, respaldo previo) · sano
  19:47 (versión `cbaff7ab9c2d`, base al día, humo ok): Sofía «Guarda sus datos» (PR #75, `main` = `42f379c`, árbol =
  `cbaff7a`). El staging del CI pasó el respaldo previo; el CI del PR (#259) se canceló. Juan no cambió.
- **Desplegar 45** (18:12 UTC del 5 nov, `63bcdef`, imagen `sha256:32b31395…` de CI #256, respaldo previo) · sano
  18:27 (versión `63bcdef9ebbe`, base al día, humo ok): Sofía baja con scroll y la prueba de scroll de toda pantalla
  propia (PR #74, `main` = `91507ca`, árbol = `63bcdef`). El staging del CI #256 se frenó en el respaldo previo por un
  **429 de R2**; **Desplegar 44** (staging, mismo digest) salió sano. El PR se unió con los tests ya verdes y antes de
  que terminara staging, para poder subir la rama sin colar código sin probar; el CI del PR (#257) se canceló.
- **Desplegar 43** (05:12 UTC del 5 nov, `a1d4b7d`, imagen `sha256:2003322b…` de CI #254, respaldo previo) · sano y
  confirmado 05:26 (versión `a1d4b7d62fc6`, base al día, humo ok): **módulo nuevo `dcasa_sofia`** (Sofía, la asistente
  del CRM; PR #73, `main` = `ff2ddd3`, árbol = `2de05a8`). El módulo se instaló solo en el arranque porque ya estaba en
  `ODOO_MODULES` (docker/entrypoint.sh) en esa misma imagen. El CI que abrió el PR (#255) se canceló: era el mismo árbol.
  Después, la rama se puso al día con un merge de `main` (el clasificador no deja `reset` + `push --force`).
- **Desplegar 42** (01:57 UTC del 5 nov, `71d0040`, imagen `sha256:d02db548…` de CI #252, respaldo previo) · sano y
  confirmado 02:12 (versión `71d0040c988b`, base al día, humo ok): tasa de cierre en el Resumen de Juan (PR #72, `main`
  = `57d718b`, árbol = `43eed13`). Esta vez el staging del CI sí pasó el respaldo previo.
- **Desplegar 41** (21:50 UTC del 4 nov, `43a105d`, imagen `sha256:0dde5051…` de CI #250, respaldo previo) · sano y
  confirmado 22:04 (versión `43a105db925a`, base al día, humo ok): clientes repetidos (buscar por celular, datos del
  cliente en la cotización y la factura, «Es esta persona»; PR #71, `main` = `23026ec`, árbol = `0350a3d`). **Tercera
  vez** que el staging del CI se frena en el respaldo previo con staging dormido (61 s); **Desplegar 40** (staging
  directo con el mismo digest) salió sano. Hace falta que el respaldo previo de staging despierte el sitio y espere.
- **Desplegar 39** (00:55 UTC del 4 nov, `50b52c6`, imagen `sha256:a167a596…` de CI #247, respaldo previo) · sano y
  confirmado 01:08 (versión `50b52c6c6247`, base al día, humo ok): Inicio con
  tres paneles, CRM al chat, vendedoras activas, notas de voz, fotos de varios productos (PR #70). El staging del CI #247
  se frenó otra vez en el respaldo previo (61 s, staging dormido); **Desplegar 38** (staging directo con el mismo digest)
  salió sano. Ya van dos veces: si se repite, que el respaldo previo de staging despierte el sitio y espere antes de
  pedir el volcado.
- **Desplegar 37** (05:56 UTC del 3 nov, `594522c`, imagen `sha256:fb452fb7…` de CI #245, respaldo previo) · sano
  05:59 y confirmado 06:10 (versión `594522c77c27`, base al día, humo ok): «Sin leer» = lo que espera a una persona, cotizaciones del
  chatbot y la web que vencen solas, ventas atribuidas en tres (PR #69). CI #243 salió **rojo** en `TestSuperficieRpc`:
  el módulo sobrescribía `create` y `action_draft` de `sale.order` sin entrada en `LISTA_BLANCA`. **Regla:** también un
  *override* de un método público de Odoo (`create`, `write`, `action_*`) en un módulo nuestro va a `LISTA_BLANCA`
  con el motivo «OVERRIDE …».
- **Desplegar 36** (04:15 UTC del 3 nov, `b9ded11`, imagen `sha256:25018016…` de CI #240) · sano y confirmado 04:29:
  notas de voz, stickers, columna ajustable y Origen (PR #68). **Desplegar Juan 4** (04:15, `14be013`) en paralelo,
  porque cambió `juan/`; Desplegar Juan solo se lanza cuando cambia `juan/`.
- **Desplegar 35** (03:26 UTC del 3 nov, `d285ee7`, imagen `sha256:710e9d2c…`) · sano y confirmado 03:40: privacidad
  con Juan y enlace del catálogo (PR #67). El staging de esa imagen salió de **Desplegar 34** (staging directo, 03:10):
  el despliegue a staging del CI #239 se frenó en el respaldo previo con HTTP 000 a los ~63 s porque staging estaba
  dormido. **Regla:** si el respaldo previo de staging da HTTP 000 (no 429 ni 503), la imagen ya está construida y
  probada: lanzar «Desplegar» a staging con su `imagen_digest` en vez de repetir todo el CI.
- **Desplegar 33** (17:55 UTC del 2 nov, `441635e`, imagen `sha256:c3efff19…` de CI #237, respaldo previo) · sano
  17:59 y confirmado 18:09 (versión `441635e5b372`, base al día, humo ok): Valor del inventario y lo cobrado por forma
  de pago (PR #66). En horario de tienda porque la dueña lo pidió «ya mismo»: ~2 min de 503 mientras arrancaba la
  imagen nueva. El CI #236 se canceló a propósito: la revisión adversarial encontró que faltaba el método en la lista
  blanca de `test_superficie_rpc.py` (habría salido rojo). **Regla:** todo método público nuevo de un modelo `dcasa`
  va a `LISTA_BLANCA` con su motivo en el mismo commit.
- **Desplegar 32** (23:31 UTC del 27, `53c7b18`, imagen `sha256:da338f12…` de CI #231, respaldo previo) · sano y
  confirmado 23:46: arreglo de «Rastrear inventario» (PR #65).
- **Desplegar 31** (00:26 UTC del 27, `741930d`, imagen `sha256:efb5f5ac…` de CI #230 sobre `main`, respaldo previo
  hecho) · sano y confirmado 00:42 (versión `741930d52e2c`, base al día, humo ok, 600 s de vigilancia). «Deployed dcasa
  triggers» ya lista `dcasapty.com (custom domain)` y `www.dcasapty.com (custom domain)`: los que la dueña agregó a
  mano quedaron adoptados sin conflicto.

- **Desplegar 25** (producción, `75324c5`, 2026-10-23 06:38 UTC) · El respaldo previo recibió HTTP 503 («Odoo de
  producción está apagado») y no se desplegó: producción quedó como estaba. El respaldo no enciende el contenedor
  (`respaldar` sale si Odoo no está listo) y en producción un 503 es fallo. Esperé al cron que despierta a Odoo
  (`7 * * * *`) y **Desplegar 26** (07:12 UTC) hizo el respaldo y salió sano y confirmado. Por qué Odoo estaba apagado
  de madrugada si es 24/7 (después de Desplegar 24, sano a las 02:48): **sin confirmar**; mirar los registros del
  contenedor en Cloudflare de esa hora. **Regla:** ante ese 503, esperar el minuto 7 de la hora siguiente y relanzar;
  no desplegar sin respaldo salvo que la dueña lo pida para arreglar una caída.

- **CI #140** (staging, `b83f515d`, 2026-10-14) y **Desplegar run 2** (staging, mismo commit, digest `efbdeae2…`) ·
  Odoo 500 en `/dcasa/salud` 20 min. Causa probable: base sin actualizar (sin confirmar). Siguiente: `a1e89e41`
  (diagnóstico solo en staging: `addons/dcasa_sesiones/diagnostico.py`); CI #142 terminó en verde (sin confirmar que
  ese run desplegó a staging).
- **CI #153** (staging, `22119f35`, 2026-10-15) · 503 con `odoo.sql_db: bad query: SELECT "res_users"…` (columna
  inexistente). Arreglo del diagnóstico: `5a99f129` (guarda la causa de PostgreSQL; `esperar_salud.sh` muestra 1500
  caracteres). Desplegar de nuevo (CI #154) salió sano.
- **CI #158** (producción) · incidente 2. **Desplegar run 8** · incidente 1 (`IMAGE_REGISTRY_DOESNT_CONTAIN_IMAGE`).

### Flakes (fallas que no eran del código)

- **CI #162** (`b3e75807`) · La prueba «vinculado» del puente de WhatsApp leía el estado antes de que WebCrypto guardara
  la sesión; pasó al repetir. Arreglo: `ac76ef40` → `puente-wa/test/integracion.test.ts` (espera con sondeo).
- Pruebas que dependen del reloj: `c2fd4a9` (pasar_a_vendedora, fallaba solo un día después de las 17:00 UTC),
  `2c6e978e` y `b8b03c0` (arriba). Regla: congelar el reloj en toda prueba con fechas.
- **Local, 2026-10-17** · `dcasa_conversaciones` `TestContratoVisualJuan.test_03_capturas_de_referencia` (pantalla
  «conexiones» a 390 px) falla en esta máquina con 13.52 % de píxeles distintos **también en `3b678a6`** (sin cambios):
  es del entorno local (Chromium/fuentes), no del código. La de «hilo» a 390 px dio 2.02 % una vez y pasó en la
  siguiente corrida. Antes de culpar a un cambio, correrla en la base sin el cambio.
- 2026-10-18 · `test_en_vivo_es_honesto_y_al_reconectar_se_trae_lo_que_se_perdio` («sin conexión no debería aparecer
  solo») parecía «falla después de medianoche UTC» y no era la hora: era una carrera de la prueba. Al suscribirse por
  primera vez, el bus de Odoo repite los avisos de los últimos 50 s (`bus.bus._poll` con `last=0`), y las filas de
  `bus.bus` de los datos de ejemplo llevan la hora de inicio de la transacción de la CLASE: corrida sola (o entre las
  primeras de la clase) la pantalla recibía esos 7 avisos ~30 ms antes o después de `bus.stop()` y su refresco (350
  ms) caía después del POST; en la suite, casi nunca. Arreglo: `PanelUiCase.avisos_anteriores_ya_viejos()` (lo llama
  `navegador()`) envejece esas filas un día, y `test_al_abrir_la_pantalla_el_bus_no_repite_…` lo comprueba con el reloj
  congelado 5 s y 10 min después. Regla: una prueba con navegador que afirma que algo NO aparece no puede dejar avisos
  del bus de antes de abrir la página; y «pasó a una hora y falla a otra» con el mismo commit se repite 3–5 veces
  antes de culpar al reloj (aquí, sin el arreglo, falló 4 de 10 corridas seguidas entre 01:06 y 01:49 UTC).

---

## Trampas de Odoo 19 / Cloudflare / GitHub ya conocidas

### Esta máquina (sesiones de Claude)

- **El worktree de un agente (`isolation: worktree`) nace de `main` (la rama por defecto de origin), no de la rama de
  la sesión** (2026-11-06: los dos agentes salieron de `700c34a` aunque la rama tenía 10 commits más sin unir). Al unir
  su rama hay conflictos en lo que la sesión cambió mientras tanto (docs) y sus pruebas no vieron el resto de la rama.
  Decirle al agente que haga `git merge <rama>` al empezar, o esperar los conflictos y dejar que el CI pruebe la unión.
- **El proxy bloquea `git push --delete` de otra rama** (2026-11-06). Para borrar una rama ya unida: la dueña, en GitHub
  › Branches › el ícono de la papelera.
- **`npm audit fix --omit=dev` poda las `devDependencies` de `node_modules`** (vitest, wrangler, tsc desaparecen y las
  pruebas no corren): después, `npm ci`.
- **`pkill -n -f <patrón>` mata el proceso MÁS NUEVO** que calza, que puede ser el vigilante que se acaba de lanzar en
  segundo plano y no el viejo. Matar por PID.
- `$!` después de `nohup cd … && python3 odoo-bin … &` es el PID de la subshell, no el de Odoo: al «matarlo» Odoo sigue
  vivo en el puerto y el siguiente arranque falla con «Address already in use» (y las capturas salen con el código
  viejo). Arrancar con un script que haga `exec python3 odoo-bin …` o matar por el PID real (`ps -eo pid,args | grep
  <puerto>`) (2026-10-17).
- `pkill -f "<patrón>"` mata también la propia shell si el patrón aparece en el comando (sale con código 144 y se
  pierden las tareas en segundo plano de esa llamada). Matar por PID (`ps -eo pid,args | grep odoo-bin`).
- Las pruebas de navegador de Odoo se saltan en local («Chrome executable not found»). Para correrlas: un enlace
  `chromium` → `/opt/pw-browsers/chromium-1194/chrome-linux/chrome` en una carpeta del `PATH` del comando.
- Un `scripts/test.sh` que arrancó antes de editar el código prueba una mezcla (Python viejo, plantillas nuevas): si se
  edita durante la corrida, se vuelve a correr.
- **Disco compartido:** los worktrees viejos (`.claude/worktrees/agent-*`, `/home/user/wt-*`) y las bases de prueba
  llenan el disco (llegó al 97 % y cortó corridas de agentes con «No space left on device»). Antes de lanzar varios
  agentes: `df -h /`, quitar worktrees limpios (`git worktree remove`; las ramas quedan) y borrar bases
  (`PGPASSWORD=odoo dropdb -h localhost -U odoo <base>`).
- **PostgreSQL local puede quedar apagado** tras una pausa larga de la sesión: `service postgresql start`.
- **Varios agentes a la vez** comparten 4 CPU y el límite de uso de la sesión: si el límite corta a los agentes, su
  trabajo queda SIN commit en sus worktrees; se retoma con un agente nuevo que continúe ese worktree (no se borra).
- **Un 429 de R2** en el respaldo previo frena «Desplegar» sin tocar producción: volver a lanzarlo. Le pasó también
  al staging del CI #256 (2026-11-05): Desplegar 44 a staging con el mismo digest salió sano.
- **No subir la rama entre el CI y el *squash* del PR:** el PR toma la punta de la rama, y lo nuevo (sin probar) se
  colaría a `main`. Mientras tanto se hace commit local; o, si los tests del CI ya están verdes, se une el PR (con
  `expectedHeadSha` = el commit probado) antes de que termine staging: unirlo no despliega nada, y producción sigue
  esperando a que staging quede sano (2026-11-05, PR #74).
- **`main` se une por *squash*:** al traer `main` a una rama que ya tiene ese mismo árbol (p. ej. la integración que
  se acaba de subir), `git merge` normal choca en decenas de archivos falsos; `git merge -s ours origin/main` lo deja
  en la historia sin tocar nada (comprobar antes que el árbol de `main` es igual al de un commit de la rama) (2026-10-23).
- **Monitor y las esperas largas:** un Monitor que vence a los 30 min mata su comando (se perdió así una corrida de
  pruebas). Las corridas largas van con `nohup` o `run_in_background` y se espera su archivo de resultado.
- **Medir velocidad en local:** base con todos los módulos (`-i` con la lista del `Makefile`, ~10 min: carga el
  catálogo real) + ventas, facturas y cobros creados con `odoo-bin shell` (superusuario: con un usuario normal la venta
  exige celular y correo), y cronometrar con `time.perf_counter`, `time.process_time` y `env.cr.sql_log_count`.
  Comparar con el código viejo poniendo el archivo de `git show <commit>:<ruta>` y restaurándolo. Una base con datos
  extra hace fallar pruebas de navegador que dependen de la base limpia (p. ej. el Escáner): confirmar en CI.
- **El gancho de parada** exige que la rama no tenga cambios sin commit ni commits sin subir. Si hay trabajo que aún
  no debe ir en la rama (sin aprobar, o la rama está en CI para una subida), se guarda en una rama local
  (`git checkout -b algo-local`) y en un parche (`git format-patch -1 -o <scratchpad>/parches/`), y la rama designada
  queda limpia. Cuando toca, se trae con `cherry-pick`.
- **PDF con estilos en local:** `_render_qweb_pdf` sin servidor sale sin CSS. Levantar Odoo con `--http-port` y poner
  `report.url=http://127.0.0.1:<puerto>` (parámetro del sistema) antes de imprimir.
- **Staging puede tardar ~27 min en quedar sano** después de un despliegue (restaurar desde R2 + actualizar módulos):
  la espera del flujo aguanta 20 min de arranque + 10 de vigilancia; no cancelar antes.
- El registro completo de un job de Actions no se baja desde aquí (la dirección del blob da 403 en el proxy): usar
  `get_job_logs` del MCP de GitHub con `tail_lines` (unas 330 líneas alcanzan para ver las pruebas antes del log del
  PostgreSQL de servicio).

- **Contenedor nuevo, sin Odoo ni dependencias (2026-11-02):** `vendor/odoo` puede venir sin bajar (`git submodule
  status` empieza con `-`): `git submodule update --init --depth 1 vendor/odoo` (unos minutos). Las dependencias van en
  un venv del scratchpad con `psycopg2-binary` y sin `python-ldap` (no compilan sin las librerías del sistema):
  `grep -v -i "^psycopg2\|^python-ldap" vendor/odoo/requirements.txt > req.txt`. El rol `odoo` de PostgreSQL hay que
  crearlo (`CREATE ROLE odoo LOGIN SUPERUSER PASSWORD 'odoo'`) y Chromium está en `/opt/pw-browsers/chromium` (enlace
  `chromium` en el `bin` del venv para las pruebas de navegador). Correr con `PATH=<venv>/bin:$PATH PYTHON=<venv>/bin/python`.
- **Referencias del contrato visual (`dcasa_conversaciones/tests/referencia/panel-*.webp`): nunca se regeneran en
  esta máquina** (2026-11-03). Chromium y las fuentes de aquí pintan distinto (la de «conexiones» a 390 px sale 13.7 %
  distinta sin cambiar código); el CI compara con 6 % de tolerancia y en local con 1.5 %. Se regeneraron una vez y hubo
  que devolver las de siempre; con las viejas el CI pasó. Desde el PR #69 (`[skip ci]`, «sin leer» pasó a «espera» y
  «Esperan respuesta») la de «lista» a 390 px quedó vieja de verdad (7.7 % local, 2026-11-06): hay que regenerarla
  donde pinta como el CI.
- **`odoo.__WOWL_DEBUG__.root` en el sitio público no está listo cuando `body[is-ready]`** (2026-11-06): en
  `public_root.js` el `is-ready` puede llegar antes de que `app.mount` termine y se asigne `__WOWL_DEBUG__`. Una
  prueba de navegador que use el `root` espera las dos cosas; si no, falla a veces en corridas largas («Cannot read
  properties of undefined (reading 'root')», `test_cabecera_con_la_pagina_abierta_desplazada`).
- **Juan y las fotos del chat:** el Worker `dcasa-juan` necesita la variable de texto `URL_PUBLICA` (su propia
  dirección `https://dcasa-juan.dcasapty.workers.dev`, sin `/` final) para que Odoo pueda bajar las fotos, notas de voz y
  stickers; sin ella salía «No se pudo traer 1 archivo». `/salud` de Juan la marca como problema desde el PR #68.
- **SCSS de Odoo (libsass) no acepta `min()`/`max()` de CSS con unidades mezcladas** (`min(100%, 300px)` → «Incompatible
  units: 'px' and '%'»): el bundle del backend entero sale con un error y TODAS las pantallas quedan sin estilo (falla
  `test_bundle_backend_con_la_marca` y, detrás, las pruebas con navegador). Escribirlo como cadena (`#{"min(100%, 300px)"}`,
  como ya hace `panel.scss`) o evitarlo (2026-11-03).
- **El servidor de capturas guarda los estilos compilados:** después de cambiar un `.scss`, reiniciar `servidor.sh` antes
  de repetir las capturas (si no, salen con el estilo viejo).
- **Un *override* nuevo de un método público de Odoo** (`crm.team.action_your_pipeline`) también va a `LISTA_BLANCA`
  (`test_superficie_rpc.py`), como `create`/`action_draft` en la tanda anterior.
- **«Conéctate a Cloudflare y mira las cifras»:** las cifras de Odoo (ventas, inventario) viven en el PostgreSQL del
  contenedor; ningún conector de Cloudflare las lee. Se responden con una pantalla o con Brian, no desde aquí.

### Odoo 19

- **Camila (2026-11-06, `dcasa_camila`), lo aprendido:**
  - **Una casilla con `readonly="<el mismo campo>"` no se guarda nunca.** Al marcarla, el modificador se cumple al
    instante y el formulario deja fuera del guardado los campos de solo lectura: el botón de la nube no se enciende, el
    `web_save` no lleva el campo y la casilla vuelve a quedar sin marcar. El `readonly` tiene que depender de lo
    guardado (un campo calculado aparte, p. ej. `dcasa_promos_estado != 'sin'`). La casilla de Meta
    (`dcasa_meta_eventos`) usa ese patrón: revisar.
  - **Un booleano calculado con inverso no comparte el método de cálculo con otro campo** que el inverso lee: leer el
    otro dentro del inverso vuelve a calcular los dos y borra lo que la persona marcó. La prueba con el ORM pasaba
    porque el otro ya estaba en memoria; con `self.env.invalidate_all()` antes del `write` (como el formulario) falla.
  - En el navegador, `.o_form_button_save` existe siempre (oculto con `visibility: hidden`, así que `offsetParent` no
    sirve): para saber si hay un cambio sin guardar, mirar que `.o_form_status_indicator_buttons` no tenga `invisible`.
  - Una `<iframe srcdoc>` con `sandbox="allow-same-origin …"` (sin `allow-scripts`) deja medir su alto desde la
    pantalla y no corre nada del correo: así la vista previa crece entera y la pantalla baja con su propio scroll.
  - `lxml.html.cssselect` necesita el paquete `cssselect`, que no está en las dependencias: en las pruebas, `xpath`.
  - La base de pruebas trae el catálogo con existencias y fotos: una prueba que escoge productos «elegibles» tiene que
    despublicar los demás en su `setUpClass`.
  - Otros agentes usan los puertos 8191 y 8192 en esta máquina: mirar `ps` antes de levantar Odoo (`--http-port`).
  - **Revisión adversarial del mismo día (12 hallazgos):** un consentimiento o una baja **se mira por correo, no ficha
    por ficha** (la misma persona tiene fichas repetidas, archivadas o como contacto hijo); un enlace firmado del pie
    va solo si el destinatario único ES la ficha firmada (si no, quien recibe el correo da el «sí» de otro); un
    permiso guarda **el correo** al que se dio; con Resend, sacar y dar de baja **por el id** del contacto (por el
    correo, otra grafía da 404 y se traga); antes de mandar un *broadcast*, volver a listar el segmento; una revisión
    de texto tiene que quitar (no volver espacio) los caracteres invisibles y rechazar letras de otro alfabeto; un
    token de URL se valida con una expresión ASCII antes de `int()` o `compare_digest` (si no, 500).
  - La herramienta Edit escribe `​` como el carácter invisible (no como la secuencia): para dejar escapes en una
    prueba, un script de Python en el scratchpad que reemplace `chr(…)`.
  - **Etapa 2 (mismo día), lo aprendido:**
    - `crm.lead.dcasa_temperatura` guarda `'1'`, `'2'`, `'3'` (frío, tibio, caliente: `crm_reglas.FRIO/TIBIO/CALIENTE`),
      no `'tibio'`/`'caliente'`. Usar las constantes: con el texto, el filtro no encuentra a nadie y un `create` con ese
      valor da «Wrong value».
    - En Odoo 19 la línea de venta usa `tax_ids` (no `tax_id`). `JUAN_ODOO_TOKEN` en las pruebas necesita 32
      caracteres o más (si no, `/dcasa/juan/v1/*` contesta 503 «Juan no está configurado»).
    - **OWL borra el texto que es solo espacio entre dos nodos con salto de línea**: `a <strong t-esc="n"/>⏎<t>clientes</t>`
      sale «5clientes». Poner el espacio dentro del `t-esc` (`' clientes.'`).
    - **El diálogo de Odoo en el celular va a pantalla completa y no tiene `.btn-close`** (cierra con
      `.oi-arrow-left`), y su `aria-label` se traduce («Cerrar»): en las pruebas, `.btn-close, .oi-arrow-left`.
    - En una prueba de navegador, esperar `.o_camila_guardar.disabled` justo después de tocar «Guardar» se cumple al
      instante (el botón se apaga mientras guarda): esperar a que el siguiente botón (Previsualizar) se encienda.
    - Volver a cargar la pantalla para deshacer una casilla que el servidor rechazó **borra el aviso del motivo y lo
      que la persona escribió sin guardar**: devolver la casilla a su estado en el mismo evento (`ev.target.checked`).
    - `_dcasa_nombre_cliente` cambia «ZZCM SILLÓN» por «Zzcm Sillón»: comparar sin mayúsculas en el navegador.
    - Para capturas, `scrollIntoView` mueve también los contenedores con `overflow: hidden` de Odoo (la barra de arriba
      desaparece y queda una franja gris): bajar solo el contenedor con scroll de la pantalla (`scrollTop`). Para ver
      «Camila está escribiendo…», un servidor de capturas que arranca con la IA de prueba lenta (`time.sleep`) y su
      guion fijado antes de `server.start` (mismo proceso); `page.route` con `sleep` del API síncrono no sirve.
    - El PostgreSQL de esta máquina puede quedar apagado tras un reinicio del contenedor: `service postgresql start`.
  - **Revisión adversarial de la etapa 2 (mismo día), lo aprendido:**
    - **`pg_try_advisory_xact_lock` se suelta con el primer COMMIT** (`transaccion.confirmar` a mitad de la petición):
      no sirve de turno para algo que confirma por el camino. Y una búsqueda hecha en la misma transacción usa la
      «foto» de REPEATABLE READ del comienzo: no ve a la otra campaña que confirmó después. Turno = candado de
      **sesión** (`pg_try_advisory_lock`) + volver a mirar después del COMMIT.
    - **Un candado de sesión que no se suelta queda pegado a la conexión del grupo de Odoo** (Odoo no hace
      `DISCARD ALL` al devolverla): ninguna campaña podría volver a salir hasta que esa conexión se cierre. Soltarlo
      SIEMPRE en un `finally` (y, si la transacción quedó con error, ROLLBACK y luego soltar). Una prueba que lo toma
      con un cursor aparte tiene que hacer `pg_advisory_unlock_all()` antes de cerrarlo.
    - Con un servicio externo que procesa en segundo plano (Resend), «contestó error» no es «no salió», y «canceled» no
      es «nadie lo recibió»: el registro de a quién le salió se suelta solo si nunca se llamó a «send». Un 404 al
      preguntar el estado es «ya no existe» (lo borraron allá), no un error que trabe todo.
    - Un campo «de solo lectura» en la vista se escribe igual por RPC: si solo lo debe escribir el código, quitarlo en
      `create`/`write` salvo una marca de contexto que sea un objeto de Python (lo que llega por RPC es JSON).
- **Calculadora de envíos (2026-11-06, `dcasa_envios`), lo aprendido:**
  - Un `<input type="number" step="0.1">` dentro de un `<form>` **bloquea el envío** si el valor no es múltiplo del paso
    (7.04): el navegador no llama al `submit` y no hay error visible. Lo atrapó la prueba en el navegador; ahora
    `step="any"` (el servidor redondea).
  - Un `fields.Float` guarda `0.0` cuando se le escribe `None` (no `NULL`): «sin medir» no se puede distinguir de «0 km».
    Va un booleano aparte (`km_medido`); las coordenadas (0, 0) se leen como «sin coordenadas» (es el golfo de Guinea).
  - Leer por SQL algo que el ORM acaba de escribir (p. ej. un `ir.config_parameter` con `set_param`) necesita
    `flush_model()` antes: si no, se lee el valor viejo.
  - `export_data` (el «Exportar» de las listas) exige `base.group_allow_export` (o administrador): ni Gerencia lo
    trae. Un campo calculado no guardado sí sale en la exportación.
  - Portar fórmulas de JavaScript: `round()` de Python redondea los medios al par (`Math.round` hacia arriba),
    `toFixed` mira el valor exacto, `toLocaleString('es-PA')` pone la coma de miles también en 4 cifras, `.length`
    cuenta en UTF-16 (un emoji vale 2) y `sum()` de Python 3.12 compensa los decimales (el CI usa 3.12): sumar con un
    bucle. La paridad se prueba corriendo el JavaScript real en node (`scripts/envios/paridad.mjs`).
  - En JavaScript, `objeto[palabra]` lee el prototipo: el HTML de envíos se caía al buscar «constructor»
    (`ABREV['constructor']` es una función). En Python, `dict.get` no tiene ese problema.
  - `TEST_TAGS=/dcasa_interfaz:TestScroll` no corre nada: la clase es `TestInicioScroll` (un filtro que no calza no da
    error, da cero pruebas). Revisar en el registro que las pruebas pedidas aparecen como «Starting …».
- **Plantillas OWL: no hay `String()`, `Number()` ni otros globales de JavaScript** (`ctx.String is not a function`
  rompe la pantalla entera). Un número en `t-att-value` ya sale como texto. Y **`<select t-model>` no marca la opción
  al dibujar** (pone el valor antes de que existan las opciones): cada `<option>` lleva también `t-att-selected`, como
  en Conversaciones. Las dos las atrapó la prueba en el navegador de «Guarda sus datos» (2026-11-05), no las de Python.
- **Leer datos de lo que escribe la gente (nombres, fechas, correos) da falsos positivos que no se ven en las pruebas
  felices:** «Muy amable» o «Calle Principal» parecen un nombre; «entréguenmelo el 15/11», «cama 3/4» o «el cumpleaños
  de mi mamá» parecen un cumpleaños; «te envié la cotización a tu correo, ¿la recibiste?» parece un pedido de datos.
  Una revisión adversarial con frases reales de chat los encontró todos (Sofía, 2026-11-05). **Regla:** lo que se lee
  de un chat se propone, nunca se guarda solo; la lectura suelta solo vale para la respuesta directa a un pedido; y
  cada regla de lectura lleva pruebas de lo que NO debe leer.
- **`enviar_respuesta` (y todo lo que llama a `dcasa.mensaje._enviar`) confirma la base A MITAD de la petición**
  (`transaccion.confirmar` antes de llamar al Worker): suelta los candados `FOR UPDATE` y deja escrito lo de antes. Si
  después algo choca, Odoo repite la petición entera y el cliente puede recibir el mensaje dos veces. Lo que marque
  «ya se hizo» (Sofía: la propuesta aprobada) se escribe ANTES de enviar, con `flush_all()`, para que quede en la misma
  confirmación (revisión adversarial, 2026-11-05). Las pruebas no lo ven: en pruebas no se confirma nada.
- **Probar en el navegador algo que llama al Worker de Juan:** en `HttpCase` el servidor corre en el mismo proceso,
  así que basta `patch.object(type(self.env['dcasa.juan.cliente']), 'sugerir', return_value=...)` (y `configurado`)
  alrededor de `browser_js`. Para capturas en la base de prueba (sin Worker), Playwright `page.route` sobre
  `/web/dataset/call_kw/dcasa.conversacion/sugerir_respuesta` (y decirle a la dueña que ese texto es de ejemplo).
- **Lo que llega tarde se guarda donde se pidió, no donde se está mirando** (la varita, 2026-11-06): la caja escribía
  el borrador en `almacen.borrador` (= la conversación a la vista) al volver la respuesta; si la vendedora cambiaba de
  chat mientras Juan escribía, el borrador de una clienta caía en la caja de otra, y lo que ella tecleaba mientras
  esperaba se pisaba. El estado de «Sugerir» vive en el almacén por conversación (`sugerencias[id]`, `borradorDe(id)`),
  no en el componente. Pruebas en el navegador con un Worker de mentira que tarda (`self.rutas[...] = función`).
- **La revisión de la marca: `quitarGraves` no quita fugas** (`analizarOracion` no mira `fuga`, y `analizar` se detiene en
  la primera fuga sin buscar lo demás). En el bot da igual (una fuga se cambia por `TEXTO_FUGA`), pero en el borrador de
  «Sugerir» la frase copiada del prompt pasaba entera con el aviso «Quité información interna». `revisarBorrador` ahora
  quita las oraciones con fuga (`detectarFuga`) y revisa el resto.
- **Pasar un texto de una pantalla a otra (Sofía → chat): nunca en `params` de la acción.** Odoo guarda la acción en la
  pestaña y en la dirección: al recargar volvía a aparecer el mensaje ya enviado, y cualquiera podía armar un enlace con
  un texto. Va por `sessionStorage`, se lee una vez y se borra, con vencimiento y solo para esa conversación.
- **Botón arriba del tablero o de la lista sin JS:** `<header><button ... display="always"/></header>` dentro de
  `<kanban>` (o en el `<header>` de la `<list>`); el método recibe un recordset vacío y devuelve una acción.
- **El servidor de capturas corre los crons** (el CRM automático enfría los clientes inventados y Juan les programa
  seguimientos): `servidor.sh` ahora va con `--max-cron-threads=0`, y los datos de prueba del CRM con `dcasa_auto_off`.
  Y en Playwright, mover el puntero lejos del menú lateral antes de cada captura (si no, el menú queda abierto encima).
- **Datos de otra ficha editables en un documento (2026-11-04, `dcasa_contactos/models/datos_del_cliente.py`):**
  (1) un `related` con `readonly=False` reescribe la ficha **en cada guardado que lo incluye**, y el formulario manda
  todos los campos no-readonly al crear el documento o al cambiar el many2one, aunque estén invisibles: con datos
  viejos mal escritos ya no se guardaba ni una cotización nueva. (2) Con `compute` + `inverse`, **un solo método para
  varios campos borra datos**: mientras Odoo corre el inverso, todos los campos de ese mismo cálculo quedan protegidos
  y se leen vacíos (el inverso los «ve» cambiados a `False` y los escribe). Cada campo con su propio cálculo e inverso
  (fábrica `metodos_del_dato`), y los booleanos que el inverso necesita, en otro cálculo. (3) `vat` de un contacto con
  `parent_id` sube a la empresa (campo comercial). Lo encontró la revisión adversarial; las pruebas que crean con
  `Form` y datos viejos malos lo cubren.
- **Un `@api.onchange` sobrescrito sin el decorador deja de ser onchange** (Odoo los junta con `getmembers` buscando el
  atributo `_onchange`): al sobrescribir uno, repetir `@api.onchange(...)` con los mismos campos.
- **Cambiar de registro dentro de un `FormViewDialog`** (p. ej. «Crear y editar» → «Es esta persona»): desde un widget,
  `record.model.load({resId, resIds})` y luego `model.root.update(cambios)`. Al guardar, el diálogo llama
  `onRecordSaved(record)` con el registro cargado y el many2one queda con ese id (`relational_utils.js`,
  `update([{...record.data, id: record.resId}])`); «Descartar» lo deja vacío.

- **Valuación del inventario en Odoo 19:** ya no existe `stock.valuation.layer`. El valor oficial es
  `product.product.total_value` (y `avg_cost`), calculado según el método de costo (estándar o promedio: unidades ×
  `standard_price`; FIFO: lo que queda de cada entrada) y medido en
  `products._with_valuation_context()` (ubicaciones propias que se valoran, sin mercancía de terceros). Lo usa
  *Valor del inventario* (`dcasa_interfaz/models/inventario_valor.py`) (2026-11-02).
- Marcar «Rastrear inventario» (`is_storable`) en un producto que ya tuvo movimientos corre `_reset_inventory`: crea
  quants del historial y los aplica a cero **en el entorno del usuario**. Cualquier regla nuestra sobre
  `stock.quant._apply_inventory` (motivo, Gerencia) le aplica: por eso `dcasa_existencias` le pasa su motivo
  (2026-10-27, PR #65). Escribir «A la mano» en el mismo guardado es otro ajuste, humano, y sigue pidiendo motivo.
- `invoice_payments_widget` / `_dcasa_pagos()` es caro (una consulta y varias lecturas por factura): nunca en un bucle
  sobre muchas facturas; para «¿tiene cobro?» buscar `account.partial.reconcile` de todas las líneas por cobrar a la vez
  (`dcasa_barras/models/bodega.py`, `_facturas_con_cobro`) (2026-10-23). Ojo: ni la nota de crédito ni el asiento
  de diferencia de cambio (`exchange_move_id` de una conciliación) son cobro; el globito los marca `is_refund` e
  `is_exchange`.
- **`/web/dataset/call_kw/<modelo>/<método>` obedece al cuerpo** (`params.model` / `params.method`), no a la URL: lo que
  decida por la ruta (el borde, una lista blanca) tiene que comprobar que el cuerpo pide lo mismo.
- **Un precio puesto a mano en una línea de venta** se nota porque `technical_price_unit` (lo que calculó el sistema)
  ya no es igual a `price_unit`. Lo que se muestre a partir de un valor guardado al armar la línea (un ahorro, un
  «precio normal») solo vale mientras la línea siga al precio del sistema; si no, se muestra la línea tal cual
  (combos, 2026-10-23).
- `producto.with_context(...).display_name` dentro de un bucle calcula cada nombre por separado (con `website_sale` y
  variantes, varias consultas cada uno): sacar el recordset con el contexto una vez y leerlos todos juntos.
- Contar consultas en una prueba: `env.flush_all()` antes (si no, cuenta lo pendiente de guardar) y una vuelta de
  calentamiento después de crear productos (crear productos limpia cachés de Odoo).

- **La cámara del lector de códigos de Odoo puede salir en blanco en iOS** (Chrome en iPhone es WebKit): el video pide
  el 100 % de una grilla que mide lo que mide el video (WebKit lo resuelve a cero de alto) y, fuera de `isIOS()`, el
  recuadro usa un `::after` blanco con `mix-blend-mode`, que WebKit no mezcla con la cámara. Arreglo en
  `dcasa_barras/static/src/scss/camara.scss`: video a su tamaño natural, fondo negro y recuadro con borde y sombra, sin
  mezclas. Para probarlo, Playwright con WebKit o el agente de usuario de un iPhone (2026-10-19). **No bastó**: en el
  iPhone pasó de blanco a negro, leyendo códigos igual. WebKit no pinta ese video aunque le llegan los cuadros (el
  lector los saca con `drawImage`); `camara.js` los copia a un lienzo encima del video (Desplegar 23). Lección: si el
  lector lee pero no se ve, el problema es de pintado, no de la cámara; y en esta máquina no hay WebKit (solo
  Chromium), así que la prueba final es el iPhone de la dueña (lo confirmó el 2026-10-22: ya se ve).
- **Una factura de cliente creada sin pedido no aparece como cotización abierta** y Caja no la encuentra para cobrar:
  `account.move.create` rechaza una `out_invoice` sin `sale_line_ids` si quien la crea no cobra
  (`_dcasa_puede_cobrar`), y «Nuevo» se esconde en Facturas con `get_view` (2026-10-19). Las pruebas o datos que crean
  facturas sueltas tienen que hacerlo como alguien que cobra.
- **Una prueba que cruza dos módulos solo corre en la unión** (`skipUnless` del otro módulo): la de los ids de Meta
  (`TestContratoId`) falló la primera vez que corrió, en la unión, porque el otro paquete había agregado después un
  interruptor apagado de fábrica. Al unir paquetes, mirar qué pruebas dejan de saltarse (2026-10-17).
- **El píxel de Meta manda la dirección completa de la página** (y la anterior como «de dónde vino»): un enlace del
  portal lleva `?access_token=`. Las páginas con datos de la persona no llevan píxel y, con el píxel encendido, llevan
  `<meta name="referrer" content="origin">` (`dcasa_meta_eventos/models/website.py`, 2026-10-17).
- **Algo que se evalúa en el layout de todas las páginas no puede lanzar**: si falla, cae todo el sitio. La compuerta
  de la política de privacidad de Meta renderiza una plantilla; si no se puede, responde «no está lista» (2026-10-17).
- **Al fusionar fichas, Contactos copia campo por campo** los datos `dcasa_*` con `copy=False`: un registro de varios
  campos que deben ir juntos (fecha, dónde y quién) se saca de esa lista y se pasa entero (`partner_merge.py` de Meta).
- Los *bundles* de assets no se vuelven a armar con el servidor andando: tras cambiar SCSS o JS, reiniciar Odoo antes
  de mirar o capturar (2026-10-17).
- **Unir dos ramas que no se veían** (tanda 2, 2026-10-18): una rama cuya base es de la historia vieja (antes del
  *squash* a `main`) se trae con `git cherry-pick` de sus commits, no con `merge`. Y después de unir, revisar lo que
  cruza: las notas de crédito, que ahora hace solo Gerencia, llevan a Gerencia como «Vendedor» (Odoo pone a quien la
  hace si la ficha del cliente no dice otra, `_compute_invoice_default_sale_person`). Todo lo que reparte ventas por
  vendedora mira el pedido y, en una nota, su factura (la que revierte o la conciliada), nunca el «Vendedor» de la nota
  (`ventas_bases._duenas`).
- **Al revertir una factura** (`_reverse_moves`), Odoo no copia el «Vendedor» (`invoice_user_id` es `copy=False`): la nota
  de crédito queda a nombre de quien la hace (Gerencia). Para saber de quién es una nota, mirar la factura que revierte
  (`reversed_entry_id`). `_reverse_moves(valores)` deja la nota en borrador y **sin conciliar**; con `cancel=True` la
  publica y la concilia (la factura queda `reversed`). Las líneas de la nota sí copian `sale_line_ids` (2026-10-17).
- **Una factura sin «Vendedor» elegido** toma el vendedor del cliente o, si no tiene, a quien la crea
  (`_compute_invoice_default_sale_person`): lo cargado por un script queda a nombre de quien lo corre (OdooBot en un
  `odoo-bin shell`). Por eso el Inicio manda las facturas del sistema anterior (`dcasa_historica`) a «Sin vendedora».
- **«Ventas» de Contabilidad = apuntes de cuentas de tipo `income`**, por su fecha contable (`date`). Las facturas lo igualan
  con `amount_untaxed_signed` solo si todas sus líneas van a ingresos y el ITBMS tiene su cuenta: en una prueba, un
  impuesto sin cuenta deja el ITBMS en ingresos y Contabilidad «suma» el impuesto.

- `notification_type` («Por correo» / «En Odoo») sale del grupo `mail.group_mail_notification_type_inbox` asignado **directo** al usuario (`group_ids`); un grupo implícito no lo cambia. Para cambiarlo se escribe `notification_type` (su inverso pone el grupo).
- Campo, vista o dato nuevo sin `odoo -u` = `UndefinedColumn` y pantallas rotas: nunca dar por buena una versión sin
  comprobar que la base se actualizó con **ese** código.
- `-u` con código más viejo que la base borra columnas y tablas nuevas y sus datos: nunca desplegar una imagen vieja
  sin restaurar antes la base.
- Botones de cabecera de lista llaman con la lista de ids: un método `@api.model` falla (incidente 3).
- Método público + `sudo()` = puerta abierta por RPC; todo método público nuevo va a la lista blanca de
  `test_superficie_rpc.py` con su motivo.
- SCSS `min(%, px)` rompe el bundle entero: usar `unquote()`.
- `.o_action` tiene `overflow:hidden`: las pantallas propias necesitan la regla fuerte para hacer scroll. Volvió a pasar con Sofía (2026-11-05): ahora `dcasa_interfaz/tests/test_scroll.py` revisa TODA plantilla cuya raíz lleva `o_action` y falla si no tiene `.o_web_client > .o_action_manager > .<clase>.o_action { overflow-y: auto; > * { flex-shrink: 0; } }` (excepciones con su porqué: Conversaciones, Vista previa, Armar combo en diálogo). En el navegador, `scrollTop = N` funciona aunque la pantalla tenga `overflow: hidden` (lo bloqueado es la rueda y el dedo): la prueba mira `getComputedStyle(...).overflowY`.
- wkhtmltopdf pide estilos a `web.base.url`: en el contenedor debe ser `127.0.0.1`.
- PyPDF2 deja escapes octales al fusionar PDF: comparar con `textos()`.
- Panamá es UTC−5: el día cambia a las 05:00 UTC; las pruebas con fecha se congelan.
- El asistente de fusión copia datos mientras la ficha que se borra existe: la que queda también necesita la excepción
  del candado; y si dos fichas se apuntan entre sí, Odoo borraba la que queda.
- `read_group` está deprecado: usar `_read_group`.
- Owl solo deja usar en las plantillas los globales `Math`, `Array`, `Object`, `Date`, `RegExp`, `console` y `window`:
  `String(x)` en un `t-att-*` falla en el navegador. Hacerlo en un método del componente (2026-10-17).
- Un archivo que hereda un modelo (`_inherit`) se importa después del que lo define: si `tablero.py` importa constantes
  de `ventas_bases.py` (que hereda `dcasa.tablero`), el registro dice «Model 'dcasa.tablero' does not exist». Las
  constantes van en el archivo que define el modelo (2026-10-17).
- Para probar algo «hasta la misma hora», la hora de registro (`create_date`) se pone por SQL en la prueba (Odoo no deja
  escribirla) y el reloj se pasa como argumento (`_comparar(..., ahora=...)`): nada depende de la hora real.
- Enviar por Telegram hace `COMMIT` y destruye los savepoints.
- `with cr.savepoint():` primero hace `cr.flush()`, que **corre** los `precommit` pendientes (seguimiento del chatter,
  avisos del bus); si después se deshace, `cr.clear()` borra solo lo que se agregó adentro. No es una pérdida (una
  revisión del 2026-10-17 lo creyó y su propia prueba lo desmintió); sí es que esos `precommit` corren antes del commit.
  `savepoint(flush=False)` no corre nada pero tampoco limpia la caché: no usarlo para «que esto nunca falle».
- `/mail/message/post` (chatter, también del portal) publica con `sudo()` y deja pasar el `context` del navegador: un
  permiso que mire `env.su` ahí lo tiene cualquiera; se mira `env.uid`/`env.user`.
- `limit_memory_soft` mide memoria virtual (VMS), no RSS: no dimensionarlo con el tamaño del contenedor.
- Un `xpath` que busca por texto (`//h3[text()='…']`) falla con el sitio en `es_419` (el texto ya viene traducido) y
  rompe la página: anclar por estructura (`//a[@href='/shop/print']/preceding-sibling::h3[1]`). En la prueba,
  `_get_combined_arch()` devuelve un `Element`: compararlo con `etree.tostring(...)` (2026-10-17).
- Un texto más largo en la barra de anuncios desbordó el celular en producción (426 px a 360/390) con CI #194 en verde;
  la misma `TestMovilSinDesborde` falla en local con ese código. **(sin confirmar)** la diferencia es el entorno del
  CI (fuentes); mientras tanto, todo cambio de texto en la cabecera se prueba en local a 360 y 390 antes de subir
  (2026-10-17).
- Sin el grupo «Editor y diseñador» del sitio (nadie lo tiene: el sitio se edita por código) **ninguna** pantalla de
  Ajustes se guardaba («No tienes permiso para modificar registros "Sitio web"»): `group_gmc_feed` de website_sale es
  campo de grupo (recibe valor de `default_get`) y related a `website_id.enabled_gmc_src`; ese valor por defecto entra
  después del filtro de `res.config.settings.create()` y el ORM lo escribe en el sitio como el usuario aunque no cambie.
  Arreglo en `website_dcasa/models/res_config_settings.py` (si no cambia no se escribe; no abre permisos). Las pruebas
  de Ajustes como superusuario (`self.env['res.config.settings'].create({})`) no lo ven: probar como administrador sin
  diseñador y por el camino del navegador (`website_dcasa/tests/ajustes_navegador.py`) (2026-10-17).
- **Quitar una implicación de grupo en una base que ya existe**: borrar la línea `(4, ref(…))` del XML no la quita (el
  `-u` solo agrega); hace falta `(3, ref(…))` o una migración. Y si esa implicación es un **interruptor de Ajustes**
  (como «Cada vendedora ve solo sus documentos», 2026-10-17), el XML del rol **no la nombra nunca** (ni `(4)` ni `(3)`):
  cada despliegue la volvería a poner o a quitar. Se quita una sola vez en la migración (`dcasa_base` 19.0.1.8.0).
- `res.groups._remove_group(g)` (lo que usan los campos `group_*` de Ajustes) quita `g` de **todos** los grupos que el
  grupo implica y que lo tengan directo: para mover la implicación de un solo rol, escribir `implied_ids` de ese rol
  con `Command.unlink`/`Command.link`. Odoo 19 calcula los grupos implícitos al vuelo (`all_group_ids`): cambiar lo que
  implica un rol cambia al instante lo que ve cada persona, sin tocar su ficha.
- Las reglas de registro de grupo se suman con «o»: una sola `[(1, '=', 1)]` (las de Facturación) abre todo. Para
  «solo lo suyo» hay que estrechar las de fábrica (`<function … write>`, son `noupdate`) y colgar las de «toda la
  tienda» de otro grupo (`sales_team.group_sale_salesman_all_leads`).
- Con «solo sus documentos», si la ficha del cliente dice «Vendedor: B», Odoo pone a B como dueña de la cotización o
  factura que crea A y la creación **falla por permisos** (A no puede leer lo que acaba de crear): `dcasa_base` fija como
  dueña a quien crea si solo ve lo suyo. Despachar la entrega del pedido de otra vendedora sí funciona (comprobado).
- Las pruebas que crean pedidos o facturas como superusuario y luego los leen **como vendedora** fallan con «solo lo
  suyo» (quedan a nombre del superusuario): crearlos con `user_id` / `invoice_user_id` de ella.
- **Una rama unida con `main` se vuelve a probar entera, no se hereda el verde de antes de unir** (revisión del
  2026-10-17): la suite de `permisos-vendedoras` estaba verde *antes* de unir `main`; después de la unión (celular y
  correo obligatorios, `dcasa_contactos`) `TestSoloLoSuyo` y `TestInterruptorSoloLoSuyo` fallaban en `setUpClass` —
  las pruebas principales de permisos no corrían— y otras tres de las dos ramas chocaban (clientes sin celular ni
  correo; una vendedora cobrando o imprimiendo una factura que no era suya). Arreglo `7a89d89` (solo datos de prueba).
- **Lo compartido que lee lo restringido** (revisión adversarial del 2026-10-17): una plantilla o un cálculo de algo que
  ven todas (la entrega) que lee el pedido o la factura **sin `sudo`** revienta con «solo lo suyo» para la vendedora que
  no es la dueña. Pasó con la nota de entrega fácil (`stock.picking._dcasa_facturas_para_entrega`): imprimir la nota del
  pedido de otra daba error de permisos. Se lee con `sudo` **solo** lo que se imprime (como hace Odoo con
  `o.sudo().sale_id.client_order_ref`). Probarlo siempre *como la otra vendedora*, no como superusuario.
- **Una suma por SQL (`cr.execute`) no pasa por las reglas de registro**: «Ventas atribuidas» del Resumen de
  Conversaciones le daba a la vendedora la suma de toda la tienda. Toda suma nueva por SQL de facturas o pedidos se
  acota a mano con `res.users._dcasa_solo_lo_suyo()` (lo suyo y lo sin vendedora).
- **Los pedidos de la web** (`website_sale`) se asignan al confirmarse (o al quedar el pago pendiente) con
  `_compute_user_id` y `force_user_recomputation` al `website.salesperson_id` (en una base nueva, `base.user_admin`) o a
  la vendedora de la ficha. Desde el 2026-10-17 `website_dcasa/models/pedido_web.py` los deja **sin vendedora** (salvo
  la vendedora que confirma, o un «Vendedor» del sitio puesto a mano). Una prueba con `user_id: False` sin `website_id`
  no imita la web: se crea con `website_id` y se confirma como superusuario o como la persona.
- **«Solo Gerencia» o «solo Caja» no se puede hacer con reglas de registro** (se suman con «o», y Caja y la Vendedora
  con el interruptor apagado comparten «todos los documentos»): va en Python, en el servidor, antes de `super()`
  (`dcasa_base/models/cobros.py`). Odoo crea el `account.payment` y **después** revisa las reglas: para que el mensaje
  claro salga antes que el «no tienes permiso» genérico, se mira el tipo en los `vals` (con los `default_` del contexto)
  antes de crear. Y `account.move.write({'state': 'draft'})` por RPC pasa a borrador sin el botón: también se vigila.
- **Odoo cruza solo** el pago en línea de un pedido con su factura al publicarla (`sale` `_post` →
  `js_assign_outstanding_line`, como quien publica). Una regla que frene cruzar cobros tiene que dejar pasar ese caso
  (`pago_en_linea_de_su_factura`: el pago es de una transacción de esa misma factura), o la vendedora no podría
  facturar. Con «solo lo suyo» encendido la vendedora no ve ese pago y Odoo no lo cruza: la factura se publica por
  cobrar y Caja le aplica el cobro desde la factura (comprobado en una base de prueba el 2026-10-17).
- **`assertRaisesRegex` no deshace nada en las pruebas de Odoo** (es el de `unittest`); `self.assertRaises` sí abre un
  savepoint. Si el error salta después de escribir (una revisión al final de un pago), con `assertRaisesRegex` lo escrito
  se queda y la prueba ve un estado que en la vida real se deshizo: usar `assertRaises` y mirar el mensaje
  (`negado(...)` en `test_reglas_gerencia.py`), y `invalidate_all()` antes de releer.
- **Unir `main` cuando `main` trae en un *squash* lo que la rama ya había unido** da conflictos «add/add» en muchos
  archivos: resolver con una fusión de tres vías cuya base sea la punta vieja que la rama unió
  (`git merge-file` o `git merge-tree --merge-base=<punta vieja>`), y comparar el árbol resultante (2026-10-17).
- **Los ganchos de conciliación** (`_reconcile_pre_hook` / `_reconcile_post_hook` de `account.move.line`) ven todos los
  caminos que cruzan cobros (asistente, banco, saldo a favor, Brian): sirven para avisos que no deben frenar (el primer
  abono menor a la mitad que entra por el banco). Un aviso en el gancho va en `savepoint` y nunca hace fallar el pago.
- **Esconder un botón según quién mira** (2026-10-18): la caché de vistas de Odoo es la misma para todos los usuarios
  (`_get_view_cache`), así que no se decide en el XML con Python: se usa un campo calculado con
  `@api.depends_context('uid')` (`dcasa_es_gerencia`, `dcasa_puede_cobrar`, `account.payment.dcasa_puede_tocar`) en
  `invisible`, `groups` en el botón o en la acción (`group_ids` saca la acción del menú «Acción»), o se cambia el arch
  **después** de la caché en `get_view` (`account.payment`: `create="0"` para quien no cobra). En la prueba se mira como
  el navegador: el nodo tiene que venir en `get_views` y ni él ni lo que lo contiene pueden estar invisibles con los
  valores del registro vistos por ese usuario (`TestBotonesSoloAQuienPuede._se_ve`).
- **Un cobro de Odoo 19 sin cuenta de cobros por depositar no deja asiento** (`payment_method_line_id.payment_account_id`
  vacío): no queda como «Créditos pendientes» y el asistente «Pagar» no muestra la diferencia
  (`show_payment_difference`). En una prueba que necesite eso, ponerle la cuenta al método del diario.
  `invoice_has_outstanding` se calcula con las reglas de quien mira: con «solo lo suyo» encendido la vendedora no ve el
  cobro de otro y le da `False`.

### Cloudflare

- **Un secreto nuevo del panel del Worker `dcasa` no llega a Odoo hasta que el contenedor arranca otra vez**
  (`edge/src/index.ts`: `envVars` se arma en el constructor y solo se usa al arrancar; producción no se duerme). Guardar
  el secreto en el panel no basta, y Desplegar con la **misma** imagen tampoco: el contenedor queda «no changes». Hace
  falta un despliegue con imagen nueva (2026-11-06, `RESEND_CAMPANAS_API_KEY` de Camila). Además, el nombre tiene que
  estar en la lista blanca de `variablesDelContenedor` (`edge/src/handler.ts`).
- «Network connection lost.» en `reenvio_fallido` = se cortó el enlace Worker → Durable Object (el evento «stateless»
  no tiene par en `OdooContainer`); no implica que Odoo se cayó. Las lecturas se repiten en `reenviar` (2026-10-23).
- Cloudflare puede arrancar la imagen nueva con las variables del arranque anterior (`APP_VERSION` atrasada).
- `wrangler deploy` activa el Worker antes que la imagen: si la imagen falla, el Worker nuevo ya quedó.
- La app de contenedores apareció 5 veces con la imagen anterior (incidente 5): comprobar la etiqueta activa.
- Un 200 de la salud justo después del despliegue puede ser de la instancia vieja; un «sano» a segundos del corte es
  sospechoso.
- La portada sale de la copia del borde y no despierta a Odoo: la espera debe tocar `/web/login`.
- En Containers, stderr es un socket: no reabrir `/dev/stderr` por ruta.
- `CANONICAL_HOST` tiene que ser donde el sitio responde de verdad.
- **Dominio propio del Worker (`routes` con `custom_domain: true`, 2026-10-26):** `routes` se **hereda** en los
  entornos con nombre (staging necesita `"routes": []` o se lleva el dominio); con `routes` y sin `workers_dev`, wrangler
  apaga workers.dev (poner `"workers_dev": true`); no se crea si el nombre ya tiene un A o CNAME (se borran justo antes);
  el token necesita *Zone › Workers Routes › Edit* (el de GitHub, `dcasa-github-deploy`, está en *My Profile › API
  Tokens*). Cloudflare crea solo el registro DNS y el certificado.
- Las variables del panel se aplican al reiniciar; desplegar con `--keep-vars` para no borrarlas.
- `DCASA_PIN_PEPPER` y `PGBACKREST_CIPHER_PASS` nunca se rotan; si la consulta de secretos falla, abortar.
- Puerta del equipo en «1» dejó `/master` en «Not Found»: subir por pasos «0» → «avisar» → «1».
- **`/master` de producción (incidente 4), revisado el 2026-10-18:** código, variables y nombres de los cuatro secretos
  iguales en staging y producción (registros «Secretos a subir…» de Desplegar 18 y CI #196), y la ruta de producción es
  `/master` (GitHub tapó «/master» con `***` en el título del commit del CI #132: el enmascarado de secretos sirve de
  prueba sin leer el valor). Lo distinto solo puede ser la aplicación de Access de producción (dirección) o su AUD en
  `production` (lo más probable: el de staging, o la app puesta en `dcasapty.com` como decía SEGURIDAD_ACCESO §8.4). El
  rechazo del borde era el mismo 404 en «0» y en «1». Desde `a7725a2` `/master` dice el motivo (código `audiencia`,
  `sin token`…) y `/__edge/health` trae `puerta`. Guía: docs/PUERTA_MASTER.md.

### GitHub

- **Dependabot: dos PR que tocan el mismo `package-lock.json` chocan** (2026-11-06, #7 y #8 de `edge/`): se juntan a mano
  en `package.json`, luego `npm install --package-lock-only` y `npm ci`, y se prueba. Cambiar `.github/dependabot.yml`
  en `main` lanza Dependabot enseguida: al unir el PR #77 abrió los PR #78 a #81 (Juan y el puente).
- **`up-media.yml` corre con todo push a `main` que toque `up media/**`** y puede subir a `main` un commit propio
  («[skip up-media] [skip ci]») que reescribe `RESUMEN.md`. Un *squash* con «[skip ci]» en el título no lo dispara. Si
  aparece ese commit, la rama se pone al día con un `merge` normal, no con `-s ours`.
- **Un PR que trae commits ya unidos por *squash* sale «con conflictos»** aunque el contenido sea el mismo (2026-10-18,
  PR #56 tras el #55). Si `git diff origin/main <punta probada del lote anterior>` está vacío, unir `main` en la rama
  con `git merge -s ours origin/main`, comprobar que el árbol sigue igual al probado (`git diff --quiet HEAD <sha
  probado>`) y desplegar con ese `app_version`. Mejor aún: reiniciar la rama a `main` después de cada despliegue.

- `app_version` tiene que tener imagen en el registro: el SHA de la rama que construyó el CI, nunca el del *squash*.
- Nunca inventar ni «completar» un SHA: copiarlo del PR o del run.
- La cuota de artefactos se llena: «Limpiar copias temporales» y esperar 6-12 h a que GitHub recalcule.
- «Required reviewers» no se usa (cuando se decidió, el repositorio era privado y el plan no lo daba; es público desde
  el 2026-10-13): producción solo a mano desde `main`, con la receta de [DESPLIEGUE.md](DESPLIEGUE.md#la-receta-de-producción).
- `rerun_failed_jobs` da 403 mientras el run sigue en curso.
- El runner usa shellcheck 0.9 (SC2317 en funciones de `trap`).
- El CLI `gh` existe en la máquina (2026-11-06) y sirve para leer (runs, tiempos de cada job: `gh run view <id> --json
  jobs`). Lo que escribe en GitHub (PR, unir, lanzar flujos, comentar) va por `mcp__github__*`. Un log muy largo se
  guarda en archivo y se busca con un script.
- Los avisos «Node.js 20 is deprecated» y el log del PostgreSQL de servicio son ruido, no la falla.
