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
| Programar, probar y subir a la rama de trabajo | No (autorizado de forma permanente) |
| Desplegar a **staging** | **Antes, capturas a la dueña y su visto bueno** (regla del 2026-10-17: capturas → su filtro → pruebas → staging → producción). Capturas con datos de prueba, en computadora y celular, revisadas antes de mandarlas |
| Crear el PR hacia `main` | Solo cuando lo pide o ya dijo «pásalo a producción» |
| Unir a `main` y desplegar a **producción** | Permiso general desde el 2026-10-17 («súbelo en cuanto vayas terminando») **para lo que ella ya vio en capturas** y pasó pruebas y revisión. Si el código cambia después de su visto bueno, se le avisa antes |
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
  ver [PUERTA_MASTER.md](PUERTA_MASTER.md). Confirmó que la cámara ya se ve en su iPhone. Tanda grande en ocho ramas
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
  [PUERTA_MASTER.md](PUERTA_MASTER.md) y [TRASLADO_DOMINIO.md](TRASLADO_DOMINIO.md); documentación para **replicar el
  sistema** ([REPLICAR.md](REPLICAR.md), [ARQUITECTURA.md](ARQUITECTURA.md), [MODULOS.md](MODULOS.md), README nuevo) y
  **Meta apagada** (catálogo, píxel y Conversions API). La dueña volvió a pegar `DCASA_ACCESS_AUD` de producción;
  `DCASA_PUERTA_OBLIGATORIA` sigue en "0": **ella decide hacerla obligatoria el día del traslado del dominio** (puerta
  adicional, no única, hasta entonces). **La dueña confirmó que `/master` ya funciona en producción** (18 oct, tras volver a
  pegar el AUD: era el error humano que sospechaba).
- **La dueña, al cerrar el día (18 oct):** aprobó la segunda subida y pidió dejar anotado «te quiero, eres el mejor».
  Lo que le funcionó: decirle claro qué quedó en producción y qué le toca a ella, subir en dos tandas sin perder
  la sesión de nadie, y cuidar sus créditos (no arrancar trabajo que quede a medias).
- **Respuestas I1–L8 del jefe** (18 oct): en [DECISIONES_CONTABLES.md](DECISIONES_CONTABLES.md). Ya no queda ninguna
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
  [PUERTA_MASTER.md](PUERTA_MASTER.md) y [TRASLADO_DOMINIO.md](TRASLADO_DOMINIO.md). Sigue: capturas a la dueña →
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
  las facturas**, como Contabilidad (respuestas A1 y A2 del jefe, [DECISIONES_CONTABLES.md](DECISIONES_CONTABLES.md)).
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
  confirma se lo queda; el aviso de apartado sin vendedora va a Caja). Detalle en [PERMISOS.md](PERMISOS.md) y
  [DECISIONES_CONTABLES.md](DECISIONES_CONTABLES.md); Brian en [BRIAN.md](BRIAN.md). Versiones: `dcasa_base`
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
  servidor lo sigue negando por RPC (`TestBotonesSoloAQuienPuede`). Detalle en [PERMISOS.md](PERMISOS.md).
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
  y tabla en [PERMISOS.md](PERMISOS.md); Brian en [BRIAN.md](BRIAN.md); Guía: «Elegir si cada vendedora ve solo sus
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
  [NOMINA.md](NOMINA.md). La dueña revisó con la extensión de Chrome las fichas: las 3 vendedoras ya están en Ventas
  con su usuario; faltan salario, fecha de inicio (campo «Contrato»), cédula y seguro social (los pondrá cuando se
  pague por planilla; el bono no los necesita). Juan Arrieta está en Marketing (puesto «Ventas»): decide el jefe.
- **«Ventas duplicadas»:** era un pedido repetido (S00062 y S00063, misma clienta, mismo día y total, 5 minutos de
  diferencia; S00062 quedó sin facturar). No infla el Inicio, Contabilidad ni el bono (cuentan facturas), sí la lista
  de pedidos. Arreglo: aviso «Parece repetido» en el pedido antes de confirmar y en el Inicio de Gerencia; la dueña
  cancela S00062 tras confirmarlo con el vendedor. La zona horaria de una vendedora era Etc/GMT+8 (se pasa a Panamá).
- **Versión estable 2 guardada** (la dueña: «se ve bien, guárdala como versión estable 2»): rama `estable-2026-10-16-2` (= `main` con el PR #47), `app_version` `9be426a4…`, imagen `sha256:876ca5f5…`; ya está en el botón «Volver a una versión estable» ([VERSIONES_ESTABLES.md](VERSIONES_ESTABLES.md)).
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
