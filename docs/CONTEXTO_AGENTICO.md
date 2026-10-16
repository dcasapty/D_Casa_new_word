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

---

## Incidentes de producción

### 1. 2026-10-16 · Etapas 1 y 2: «Error de servidor» en el Inicio y en Conversaciones (el despliegue dijo «sano») · #97

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
- **Lección:** «el primer despliegue de una versión deja la base sin actualizar» (#97 en PRIORIDADES) ya había pasado
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
  cada despliegue, comprobar la etiqueta de la imagen activa además de `/__edge/health`. El arreglo #97 ayuda (la salud
  dice qué versión responde y la imagen vieja no baja una base nueva), pero no impide la reversión.

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
| Desplegar 9 | 2026-10-16 07:20 | `3570c3a1` | Arreglo #97 (imagen con commit y huella; chequeo estricto) | **Sí**: la huella de la base no existía, así que actualizó todo (aplicó por fin las Etapas 1 y 2) | **Sano y confirmado** 07:22 → 07:27 (versión `3570c3a12e55`, `base_al_dia` true, 5 min de vigilancia) | El primer minuto respondía la instancia anterior (sin versión) y el chequeo nuevo **no** la dio por sana. La dueña confirmó Inicio y conversaciones. Staging igual en CI #171. digest `4e9b9155…` |

**Qué puede no haberse aplicado nunca en producción:**

1. **PR #43 (Etapas 1 y 2): aplicado desde Desplegar 9** (07:22). Entre las 05:47 y las 07:22 no lo estuvo
   (columnas inexistentes a las 06:07-06:16 e imagen revertida a `bf40605e`). PR #44 es solo documentación.
2. **PR #42, #40, #36 y #30:** necesitaban `-u`; ningún registro de GitHub prueba si el primer arranque lo hizo. El
   chequeo viejo solo fallaba si la columna que falta la usa `/dcasa/salud` (p. ej. `res_users`), así que un «sano» no
   lo garantiza (sin confirmar). Los despliegues siguientes cambiaron `APP_VERSION` y probablemente pusieron la base al
   día en algún reinicio; el primer despliegue con #97 hará `-u` completo y debería cerrar cualquier hueco.
3. **Reversiones (incidente 5):** el código de PR #35 (CI #138→#147), PR #36 (CI #147→#150) y PR #40 (Desplegar 4→5)
   pudo dejar de correr durante horas; quedó cubierto por el despliegue siguiente, que lo incluía.
4. Desde Desplegar 9 (arreglo #97) `/__edge/health` dice `version` y `base_al_dia`, y ese primer arranque actualizó
   **todos** los módulos (no había huella en la base): lo que hubiera quedado sin aplicar de PR #42, #40, #36 y #30
   quedó aplicado ahí. Igual, después de cada despliegue se abren el Inicio, Conversaciones e «Imprimir documentos».

---

## Fallas de CI y cómo se arreglaron

Últimos 60 runs de CI/CD (#112 a #171). Fallaron: #112, #139, #140, #151, #152, #153, #155, #156, #158, #167
(cancelados: #109, #116, motivo sin confirmar). Truco para leer los registros de «Tests de Odoo»: las últimas ~500 líneas
son el log del PostgreSQL de servicio (`FATAL: role "root" does not exist`, duplicados y *checks* que las pruebas
provocan a propósito: ruido). El resultado real está en la línea `✖ Fallaron la instalación o los tests. Detalle:` y las
`FAIL:`/`ERROR:` que la siguen.

### Tests de Odoo

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

- **CI #151** · 7 de 40 pruebas de `juan/test/integracion/flujo.test.ts` fallaron (`«conversacion_id» tiene que ser un
  número entero`, «petición 3 sin paso en el guion», actividades vacías). Arreglo: `2c6e978e` →
  `juan/test/integracion/historia.ts` («la foto de Juan se pide con el código público»). Relación exacta entre
  síntomas y arreglo: sin confirmar.

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

---

## Trampas de Odoo 19 / Cloudflare / GitHub ya conocidas

### Odoo 19

- Campo, vista o dato nuevo sin `odoo -u` = `UndefinedColumn` y pantallas rotas: nunca dar por buena una versión sin
  comprobar que la base se actualizó con **ese** código.
- `-u` con código más viejo que la base borra columnas y tablas nuevas y sus datos: nunca desplegar una imagen vieja
  sin restaurar antes la base.
- Botones de cabecera de lista llaman con la lista de ids: un método `@api.model` falla (incidente 3).
- Método público + `sudo()` = puerta abierta por RPC; todo método público nuevo va a la lista blanca de
  `test_superficie_rpc.py` con su motivo.
- SCSS `min(%, px)` rompe el bundle entero: usar `unquote()`.
- `.o_action` tiene `overflow:hidden`: las pantallas propias necesitan la regla fuerte para hacer scroll.
- wkhtmltopdf pide estilos a `web.base.url`: en el contenedor debe ser `127.0.0.1`.
- PyPDF2 deja escapes octales al fusionar PDF: comparar con `textos()`.
- Panamá es UTC−5: el día cambia a las 05:00 UTC; las pruebas con fecha se congelan.
- El asistente de fusión copia datos mientras la ficha que se borra existe: la que queda también necesita la excepción
  del candado; y si dos fichas se apuntan entre sí, Odoo borraba la que queda.
- `read_group` está deprecado: usar `_read_group`.
- Enviar por Telegram hace `COMMIT` y destruye los savepoints.
- `limit_memory_soft` mide memoria virtual (VMS), no RSS: no dimensionarlo con el tamaño del contenedor.

### Cloudflare

- Cloudflare puede arrancar la imagen nueva con las variables del arranque anterior (`APP_VERSION` atrasada).
- `wrangler deploy` activa el Worker antes que la imagen: si la imagen falla, el Worker nuevo ya quedó.
- La app de contenedores apareció 5 veces con la imagen anterior (incidente 5): comprobar la etiqueta activa.
- Un 200 de la salud justo después del despliegue puede ser de la instancia vieja; un «sano» a segundos del corte es
  sospechoso.
- La portada sale de la copia del borde y no despierta a Odoo: la espera debe tocar `/web/login`.
- En Containers, stderr es un socket: no reabrir `/dev/stderr` por ruta.
- `CANONICAL_HOST` tiene que ser donde el sitio responde de verdad.
- Las variables del panel se aplican al reiniciar; desplegar con `--keep-vars` para no borrarlas.
- `DCASA_PIN_PEPPER` y `PGBACKREST_CIPHER_PASS` nunca se rotan; si la consulta de secretos falla, abortar.
- Puerta del equipo en «1» dejó `/master` en «Not Found»: subir por pasos «0» → «avisar» → «1».

### GitHub

- `app_version` tiene que tener imagen en el registro: el SHA de la rama que construyó el CI, nunca el del *squash*.
- Nunca inventar ni «completar» un SHA: copiarlo del PR o del run.
- La cuota de artefactos se llena: «Limpiar copias temporales» y esperar 6-12 h a que GitHub recalcule.
- «Required reviewers» no está disponible en el plan actual para repos privados: producción solo a mano desde `main`.
- `rerun_failed_jobs` da 403 mientras el run sigue en curso.
- El runner usa shellcheck 0.9 (SC2317 en funciones de `trap`).
- No hay `gh` CLI: todo por `mcp__github__*`; un log muy largo se guarda en archivo y se busca con un script.
- Los avisos «Node.js 20 is deprecated» y el log del PostgreSQL de servicio son ruido, no la falla.
