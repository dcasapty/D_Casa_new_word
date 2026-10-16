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
| Programar, probar, subir a la rama de trabajo, desplegar a **staging** | No (autorizado de forma permanente) |
| Crear el PR hacia `main` | Solo cuando lo pide o ya dijo «pásalo a producción» |
| Unir a `main` y desplegar a **producción** | **Sí, un «sí» explícito por cada cambio.** Un «sí» no se arrastra al siguiente cambio |
| Borrar datos, ramas, respaldos, secretos | Sí, y mirando primero qué se borra |
| Cifras de dinero, puntos, comisiones, impuestos | Nunca se inventan (ver `CLAUDE.md`: `puntos.json`, reglas de marca) |

## 3. Cómo se llega a producción (receta)

1. Cambio en la rama `claude/...` con su prueba. Corre `scripts/test.sh <módulos>` en local (PostgreSQL local; si se
   cayó: `pg_ctlcluster 16 main start` y esperar la recuperación), `ruff check addons` y, si tocó Worker, `npm test &&
   npm run typecheck` en la carpeta.
2. Subir la rama. Disparar **CI/CD** (`.github/workflows/ci.yml`) a mano con `desplegar_en = staging`: corre todas las
   pruebas y, si pasan, despliega a staging (unos 14 minutos en total si todo va bien).
3. Con staging **sano**, avisarle. Si dice «sí, pásalo a producción»: crear el PR (plantilla
   `.github/pull_request_template.md`, con su sección de Brian) y unir con *squash* y el título terminado en
   ` [skip ci]` (las pruebas ya pasaron en la rama; no se repiten en `main`).
4. Disparar `.github/workflows/desplegar.yml` en `main` con: `entorno = production`, `imagen_digest` (el `sha256:…` del
   resumen del despliegue de staging de esa misma imagen), `app_version` (el SHA de 40 caracteres del commit que se
   probó) y `respaldo_previo = true`. Tarda unos 3 minutos; el último paso espera a que el sitio responda sano.
5. Avisarle cuando esté sano y qué cambió para ella (sin tecnicismos). Los contenedores reiniciados toman las variables
   nuevas de Cloudflare.

## 4. Trampas ya conocidas (no volver a tropezar)

- **«Sano» no es «Odoo contesta» (#97, incidente del 2026-10-16).** El arranque decidía actualizar la base solo
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
- Las pruebas de Odoo tardan ~27 minutos; un fallo cuesta un ciclo entero. Antes de subir, correr en local los módulos
  que se tocaron.
- No existe el `gh` CLI aquí: todo GitHub va por las herramientas `mcp__github__*`.
- Cada función nueva de la plataforma debe poder usarla Brian (`docs/BRIAN.md`); el PR lo pregunta.

## 5. Dónde está cada cosa

| Quiero saber… | Voy a… |
|---|---|
| Qué falló antes, por qué y cómo se arregló (incidentes, despliegues, CI, trampas) | [CONTEXTO_AGENTICO.md](CONTEXTO_AGENTICO.md) |
| A qué versión segura volver si algo se rompe, y cómo | [VERSIONES_ESTABLES.md](VERSIONES_ESTABLES.md) |
| Qué se pidió y en qué orden se hace | [PRIORIDADES.md](PRIORIDADES.md) |
| Cómo está todo (nota y fallas) | [ESTADO.md](ESTADO.md) *(fecha en su primera línea; si es vieja, manda este archivo)* |
| Qué le toca decidir o hacer a la dueña | [PENDIENTES_DUENA.md](PENDIENTES_DUENA.md) |
| Trabajo de desarrollo abierto | Los issues del repositorio (`mcp__github__list_issues`) |
| Cómo se despliega y se vuelve atrás | [DESPLIEGUE.md](DESPLIEGUE.md) y [OPERACION.md](OPERACION.md) |
| Qué ve cada rol | [PERMISOS.md](PERMISOS.md) |
| Cómo hablar con Brian y qué puede hacer | [BRIAN.md](BRIAN.md) |
| Todo lo demás | [README.md](README.md) (índice de `docs/`) |

## Bitácora de sesiones

> Más reciente arriba. Cada entrada: fecha, qué quedó en producción (con el commit), qué quedó solo en staging, qué
> sigue. Se guardan unas diez; las viejas se resumen en una línea.

### 2026-10-16

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
  #97. La imagen sabe su commit y la huella de su código y actualiza la base si no coinciden; el despliegue exige la
  versión nueva con la base al día y la vigila 5 minutos. Ese arranque actualizó todos los módulos y aplicó por fin
  las Etapas 1 y 2. Antes: suite completa de Odoo en verde (CI #171), staging sano y confirmado (07:19), respaldo
  previo. **La dueña confirmó que el Inicio y las conversaciones cargan.** Autorización: «soluciona todos los problemas
  que rompen la interfaz… y lanza a producción» y «sigue y avísame cuando esté en producción».
- **Versión estable 1 guardada** (pedido de la dueña): rama `estable-2026-10-16` (= `main` con el arreglo) y, para
  volver, `app_version` `3570c3a1…` + `imagen_digest` `sha256:4e9b9155…`. Cómo volver y qué pasa con los datos:
  [VERSIONES_ESTABLES.md](VERSIONES_ESTABLES.md). Falta ensayar la vuelta en staging.
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
  de raíz (#97): la imagen sabe su commit y su huella y actualiza la base si no coinciden; `/dcasa/salud` dice `version`
  y `base_al_dia`; `esperar_salud.sh` los exige y confirma a los 5 min; pruebas nuevas en CI (sitio falso y la imagen
  real con la base «actualizada con otro código»).
- **En producción antes** (02:32 UTC, `baf8975`): «Imprimir documentos» sale en el orden nota de entrega → factura del
  cliente → copia de la empresa (PR #42). Y (20:01 UTC, `d709cfb`): los botones «Vincular mi Telegram» y «Registrar
  webhook» de Brian ya no fallan (PR #41).
- **Pasó:** el jefe pidió una tanda grande de mejoras (utilidad en el Inicio, rediseño del Inicio, menú de Contabilidad,
  verificación con escáner en bodega, contactos duplicados, alertas, bitácora de bodega, estadísticas, colores del menú,
  categoría «Envíos»). Quedó ordenada en [PRIORIDADES.md](PRIORIDADES.md) y explicada en el documento «Plan de mejoras
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
  que quedó abierto y dicho con franqueza está en [PRIORIDADES.md](PRIORIDADES.md) (etapa 1b).
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
