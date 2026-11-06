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
| Unir a `main` y desplegar a **producción** | Permiso general desde el 2026-10-17 («súbelo en cuanto vayas terminando») **para lo que ella ya vio en capturas** y pasó pruebas y revisión. Si el código cambia después de su visto bueno, se le avisa antes |
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
  pantalla de Sofía (ya en la rama, sin desplegar).

### 2026-11-06 (7): la pantalla de Sofía

- Pedido de la dueña: «Sofía puede mejorar mucho, sobre todo la interfaz visual». **Solo la interfaz**
  (`dcasa_sofia/static/src/`): qué propone, los permisos y lo que hace cada botón no cambiaron. Ver
  [SOFIA.md](SOFIA.md) › «Cómo se ve y se usa».
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
  despliegue**: falta que la dueña vea las capturas. *(Después: le gustaron y «Descartar» queda sin confirmación.)*
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
- **Sin push ni despliegue.** Sigue: CI y staging.

### 2026-11-06 (5): Camila etapa 2 («a lo grande, todo conectado con todo»), en producción

- Decisiones de la dueña del mismo día ([CAMILA.md](CAMILA.md) §1b): **el tope de 15 días es por cliente** (por correo;
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

- Con las decisiones de la dueña del 2026-11-06 ([CAMILA.md](CAMILA.md)):
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
  Ver [ENVIOS.md](ENVIOS.md).
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
  ([REPLICAR.md](REPLICAR.md) y `docs/replicar/`) y la **versión estable 3**, ensayada en staging (el primer ensayo de
  volver que se hace).
- **WhatsApp oficial** (Desplegar 49 y Desplegar Juan 5, sano 05:59 UTC; PR #82): el webhook guarda el mensaje en el
  Durable Object antes de contestarle 200 a Meta; una alarma atiende a los 2 minutos lo que el Worker no alcanzó, en
  orden y sin contestar dos veces; «Borrar mis datos» suelta lo que estaba en curso; de lo recibido queda solo una
  huella SHA-256 del id (el `wamid` lleva el celular). Revisión adversarial: 6 hallazgos, corregidos con pruebas.
- **Documentación unida:** lo viejo a `docs/historico/`, Juan en 3 documentos, una sola receta de producción
  ([DESPLIEGUE.md](DESPLIEGUE.md)), bitácora corta, PRIORIDADES con una sola lista y sin datos de personas.
- **Camila** ([CAMILA.md](CAMILA.md)): el jefe propuso cuatro nombres para futuras herramientas (Daniela, Camila,
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

### Entradas anteriores (una línea cada una; el texto completo en [historico/BITACORA_ANTERIOR.md](historico/BITACORA_ANTERIOR.md))

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
