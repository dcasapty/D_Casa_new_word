# Yappy directo: cobrar desde la tienda con el Botón de Pago de Yappy Comercial

Módulo `addons/dcasa_pago_yappy`. Es el hermano de [TILOPAY.md](TILOPAY.md): mismo cuidado con el dinero, otra puerta de
entrada. Este documento dice cómo funciona, qué tiene que hacer la dueña antes de cobrar, lo que Yappy **no** dejó escrito
y las trampas que ya se conocen.

> **En una frase:** la clienta escribe su número de Yappy en la tienda, toca el botón de Yappy y aprueba el cobro **en su
> app**. Yappy le avisa a Odoo de servidor a servidor con un aviso **firmado**; **solo ese aviso con la firma correcta**
> deja el pedido pagado. Lo que diga el navegador («pago exitoso») nunca decide nada.

## 1. Estado y alcance

| Pieza | Estado |
|---|---|
| Pago del **pedido completo** de la tienda web (carrito y `/my/orders`) con Yappy, sin salir de la tienda | Hecho (v1) |
| Nace **apagado** y sin publicar; sin las claves no se ofrece | Hecho |
| El equipo ve **qué compró** cada persona (pedido, líneas con modelo, entrega, origen, pago) | Hecho (§5) |
| Probado contra el servidor real de pruebas de Yappy | **No**: falta el acceso al programa de pruebas (§7). Todo se probó con un Yappy simulado |
| Abonos parciales de apartados con Yappy | **No** (siguiente paso, §12) |
| Reembolsos desde Odoo hacia Yappy | **No**: Yappy no publica una API de reembolso; se hacen en Yappy Comercial |
| Comisión de Yappy en la contabilidad | **No se modela**: la contadora decide cómo se trata. Aquí no hay ninguna cifra de comisión |
| Factura automática al pagar | **No** se enciende: es un acto fiscal que decide la dueña con la contadora |

## 2. Lo que se leyó y lo que NO

La documentación del Botón de Pago de Yappy Comercial se leyó en una transcripción hecha para otro proyecto de la misma
dueña (no se pudo contrastar con el sitio de Yappy desde esta máquina). Lo que sigue es lo que esa documentación dice **y**
lo que el código usa; lo que no dice está en §8 y **no se adivina**.

| | Qué | Detalle |
|---|---|---|
| 1 | Validar el comercio | `POST {API}/payments/validate/merchant` con `{merchantId, urlDomain}` → `body.token` |
| 2 | Crear la orden | `POST {API}/payments/payment-wc`, cabecera `Authorization: <token>` (sin `Bearer`, como lo muestra el ejemplo; ver §8), cuerpo: `merchantId`, `orderId` (1 a 15 letras y números), `domain`, `paymentDate`, `aliasYappy` (el celular), `ipnUrl`, `discount`, `taxes`, `subtotal`, `total` (textos con dos decimales; mínimo `0.01`) → `body.transactionId`, `body.token`, `body.documentName` |
| 3 | El botón | Un componente web (`<btn-yappy>`) que Yappy sirve desde su CDN. Con `eventPayment({transactionId, token, documentName})` le pide el cobro a la app de la clienta |
| 4 | El aviso (IPN) | Un `GET` **abierto** a nuestra `ipnUrl` con `orderId`, `status`, `domain`, `hash` (y, a veces, `confirmationNumber` que **no está firmado**). `status`: `E` ejecutado, `R` rechazado, `C` cancelado, `X` expirado |
| 5 | La firma | `hash` = HMAC-SHA256, en hexadecimal minúsculas, de `orderId + status + domain`. La llave es el **primer trozo** (antes del primer punto) de la clave secreta una vez decodificada de base64 |
| 6 | Servidores | Pruebas (UAT) y producción: cada uno con su API y su CDN (el código tiene los dos anfitriones; no acepta ningún otro) |

Lo que Yappy **no documenta** (según lo leído; puede existir y no estar escrito): una consulta del estado de un cobro y los
reembolsos. La API de «Integraciones» de Yappy Comercial (otra cosa que el Botón de Pago) podría leer movimientos: se pregunta
(§8). Mientras no se sepa, si el aviso no llega **nadie puede preguntarle a Yappy desde Odoo**: queda un pendiente para una
persona (§3.4).

## 3. Cómo funciona

### 3.1 El camino feliz

1. La clienta llega a la fila **Yappy** del pago (es la misma fila que ya veía; ahora es el pago directo). Aparece su
   campo «Tu número de Yappy» (ya viene con el celular del pedido si es de Panamá) y el botón de Yappy.
2. Toca el botón. Odoo crea la transacción, **guarda la orden de Yappy y confirma ese guardado ANTES de llamar a Yappy**
   (si algo se corta después, la orden ya está anotada), y llama a Yappy (validar + crear orden).
3. El navegador le entrega los tres datos al botón y Yappy le manda la solicitud a la app de la clienta.
4. Ella aprueba en su app. Yappy llama a `https://<dominio>/payment/yappy/ipn?orderId=…&status=E&domain=…&hash=…`.
5. Odoo verifica **el dominio primero y la firma después** (comparación en tiempo constante). Con las dos correctas y todo lo
   demás en orden (§3.3), el cobro queda **hecho** y el equipo recibe la nota «Qué compró» en el pedido (§5). Enseguida (se
   adelanta la tarea de Odoo que cierra los pagos, o apenas la clienta ve el estado de su pedido) el pedido se confirma y el pago
   cae en el diario **Yappy**.
6. El navegador, mientras tanto, solo muestra «estamos esperando que Yappy confirme» y consulta el estado de la
   transacción en Odoo (`/payment/status`). `eventSuccess` **solo** lleva a esa página: no marca nada.

### 3.2 Decisiones donde Odoo 19 manda

- **Un solo «Yappy» a la vista.** La tienda de Odoo 19 lista **métodos de pago**, no proveedores. El «Yappy» de siempre
  (website_dcasa: te escribimos por WhatsApp con el número) tiene el código de método `yappy`. El directo tiene el suyo,
  `yappy_directo`, y se llama también «Yappy». Cuando el directo está disponible, el proveedor directo **retira al manual**
  (`_get_compatible_providers`): la clienta nunca ve dos «Yappy». Si el directo se apaga o le falta algo, el de siempre
  vuelve solo. (Con el mismo código `yappy` website_dcasa lo habría reactivado y enlazado al proveedor equivocado.)
- **Flujo `direct` de Odoo 19.** El pago no redirige: se registra una pieza de JavaScript (`payment_form.js`, un parche a la
  interacción `payment.payment_form`) que monta el botón, llama a `/payment/yappy/iniciar` y se lo pasa al botón. El botón
  de «Pagar ahora» de Odoo no se usa para Yappy (su lugar lo ocupa el de Yappy); el CSS esconde la barra de «Pagar» vacía
  en el celular.
- **El mismo diario «Yappy».** `dcasa_base` ya crea un diario de banco llamado «Yappy» (código `YAPPY`). El proveedor lo
  reutiliza: los pagos manuales y los directos caen en el mismo diario y la conciliación (§10) es una sola.
- **La orden de Yappy empieza con el número del pedido.** `orderId` es de 1 a 15 letras y números, sin guiones: el número del
  pedido (hasta 10) + 5 caracteres al azar (sin 0/O/1/I confusos), en mayúsculas. Quien mire el reporte de Yappy Comercial
  ve «S00417…» y va directo al pedido. Los 5 caracteres hacen la orden única: un reintento no choca con el anterior.
- **El botón de Yappy es de Yappy.** Se carga solo cuando la clienta elige la fila «Yappy» (son ~545 KB de un tercero que además
  habla con Google y con el Firebase de Yappy). El componente se apaga solo al pulsarlo (`disable-btn`): después de un fallo antes
  de cobrar, la página **tira el botón y pone uno nuevo**. Para el teclado, la caja del botón reenvía Enter y Espacio.
- **Tema: `dark`, elegido por la dueña el 2026-11-20 viendo el componente real en nuestra pantalla.** Blanco sobre `#444c5e`, texto de
  16 px en negrita (no es «texto grande»: pide 4,5:1) con **8,60:1** en reposo, el mejor de los seis. Medidas de los seis con el
  componente **real** (script de pruebas de Yappy ejecutado en Chrome dentro de esta pantalla; WCAG 2.x sobre los colores que
  pinta el propio componente; el botón contra el fondo de la fila elegida, `#F2F5FC`):

  | Tema | Texto/fondo en reposo | Con el ratón encima | Presionado | Botón contra la fila |
  |---|---|---|---|---|
  | `blue` (blanco sobre `#1eb2f5`) | 2,40 | 2,40 | 4,50 | 2,2 |
  | `darkBlue` (blanco sobre `#1677d8`) | 4,50 | 8,47 | 4,56 | 4,1 |
  | `orange` (blanco sobre `#ff973c`) | 2,16 | 2,16 | 3,75 | 2,0 |
  | **`dark`** (blanco sobre `#444c5e`) | **8,60** | **2,44** | 4,62 | 7,9 |
  | `sky` (`#1677d8` sobre `#f4faff`) | 4,28 | 4,40 | 3,97 | 1,0 |
  | `light` (`#1677d8` sobre blanco) | 4,50 | 4,28 | 3,97 | 1,1 |

  **Punto débil conocido de `dark`:** la regla `:hover` del propio componente lo pinta de `#9fa6b7`, y el texto blanco queda en
  2,44:1 mientras el ratón está encima (solo escritorio; en el celular no hay «encima»). No es nuestro código. Si se quiere
  cerrar, la mitigación es una regla nuestra en `yappy.scss` que mantenga el fondo oscuro también con el ratón encima (el
  componente no usa shadow DOM: sus clases se pueden pisar) y, de paso, una prueba del contraste en ese estado. **Está propuesta,
  no hecha.** `rounded="true"` no tiene efecto aquí (nuestra esquina de 12 px la pisa a propósito), y en pantallas de hasta 823 px
  el componente impone su propio relleno y el botón mide 56 px en vez de nuestros 52.
- **Tres llaves para que se ofrezca** (la misma regla de Tilopay): claves cargadas y con la forma correcta, entorno
  coherente con el interruptor (`prueba` ↔ «Modo de prueba»; `produccion` ↔ «Habilitado»), y que Gerencia lo encienda.
  `produccion` solo se obedece en el servidor de producción (`DCASA_ENTORNO=produccion`). Sin publicar o en modo de prueba
  dentro de producción, solo lo ve el equipo con sesión.

### 3.3 Qué hace el aviso con cada caso

Cada fila es una prueba automática (`tests/test_flujo.py`).

| Llega | La transacción estaba | Resultado |
|---|---|---|
| `E` firmado | borrador / pendiente | **Pagada.** Pedido confirmado, pago en el diario Yappy, nota «Qué compró» |
| `E` firmado, repetido | ya pagada | Nada (idempotente). Un registro de avisos recuerda cada letra ya vista |
| `R`, `C`, `X` firmados | borrador / pendiente | **Cancelada**, cada una con su mensaje (rechazado, cancelado, expiró) |
| `R`, `C`, `X` | **ya pagada** | Se **conserva el pago** y se deja una alerta una sola vez (la contradicción la mira una persona) |
| `E` | ya cancelada / con error | **Revisión humana** (`dcasa_yappy_revision`): nunca se paga sola. Nota y pendiente para Gerencia |
| `E` | el pedido **cambió de total** desde que se abrió el cobro | **Revisión humana**: entró dinero que no cuadra con el pedido |
| `E` | el pedido **ya estaba pagado por otra vía** (un cobro a mano de Caja, otro cobro en línea) | **Revisión humana**, con alerta clara: **nunca se registra un segundo cobro** (el cobro a mano ya cuenta el dinero; si el cliente pagó dos veces, se devuelve uno desde Yappy Comercial) |
| `E` | el entorno del cobro no es el de hoy (prueba/real) | **Revisión humana**: un pago de prueba no paga un pedido real |
| `E` | el pedido fue **cancelado** (una vendedora, o el apartado que vence por la noche) y la transacción seguía abierta | **Revisión humana**: la transacción nunca queda «hecha», no se crea ningún cobro contable y a la clienta no se le dice «Confirmamos tu pedido» sino que el pedido ya no estaba vigente y el equipo le escribe |
| (Caja) botón «Confirmar que el dinero entró» | abierta (borrador o pendiente) | Pasa por **el mismo camino que el aviso** (mismas comprobaciones, **un solo cobro**), queda quién y cuándo, y el aviso tardío que llegue después **no hace nada** (§3.4) |
| firma o dominio malos, forma rara | cualquiera | **403** «no autorizado» (el mismo texto para todo motivo). Nada cambia. Si trae una orden nuestra que sigue abierta, queda anotado en su transacción (con tope de 5) y en el registro, **con el dominio que llegó** (nunca con la firma): puede ser un aviso real que no se pudo aceptar |
| firma buena, orden desconocida | — | **200** «ok» y un aviso en el registro (no tiene sentido que Yappy reintente) |
| error nuestro (base caída, etc.) | cualquiera | **500** «error» para que Yappy pueda reintentar (si reintenta: §8) |

Detalles que importan:

- **El orden de llegada no rompe nada.** `R` y luego `E` (o `E` y luego `R`, o dos `E`) terminan en un estado explicado, con
  la regla de arriba. El `E` siempre gana sobre un estado abierto; sobre uno cerrado, pide una persona.
- **El bloqueo es de espera, no de salto** (`SELECT … FOR UPDATE`): si dos avisos de la misma orden llegan juntos, el
  segundo espera al primero en vez de descartarse (con `SKIP LOCKED` un aviso se podía perder).
  Y como PostgreSQL puede contestar «no pude serializar» al que llegó segundo, el controlador **no atrapa** ese error: lo deja
  subir para que Odoo repita la petición entera (hasta 5 veces) con una foto nueva de la base, y el segundo aviso ve lo que hizo
  el primero. Atraparlo daba un `500` y un aviso que no se aplicaba (lo encontró escribir la prueba de concurrencia de §13).
- **La respuesta de rechazo no dice por qué** (firma, dominio o forma): el mismo `403` y el mismo texto; así no se le enseña a un
  atacante cuál de las dos comprobaciones falló. El motivo real queda en el registro, sin la firma recibida y, si fue el
  dominio, con el que llegó y el declarado (`dominio: llegó «http://…» y el declarado en YAPPY_DOMINIO es «…»`).
- **La firma nunca se «calcula» en el navegador ni se guarda.** Ni la clave, ni la llave derivada, ni el hash recibido salen de
  la comprobación.

### 3.4 El aviso que no llegó (y qué hace Caja: UNA sola instrucción)

Yappy no documenta una consulta de estado (§8). Pasados **15 minutos** sin aviso, una tarea (`Yappy: cobros sin aviso`, cada 10
minutos) deja **un solo pendiente** en el pedido para Caja (si no hay quien atienda, para Gerencia) con el detalle de lo que
compró y la orden de Yappy. **No paga ni cancela por sí sola.** Si sí llegó un aviso y se **rechazó** (el dominio escrito
distinto, la clave mal pegada, las claves que faltan), el pendiente lo dice («llegó un aviso y se rechazó: …») en vez de
«Yappy no avisó nada».

**Qué hace Caja (esto es lo que dicen el pendiente, la Guía y este documento; los tres iguales):**

1. Abre el reporte de **Yappy Comercial** y busca la orden (empieza con el número del pedido).
2. Si el dinero **entró**: abre la transacción en **Facturación › Clientes › Pagos con Yappy** y pulsa **«Confirmar que el dinero
   entró»**. Pasa por el **mismo camino que el aviso** (las mismas comprobaciones de pedido vivo, entorno, pedido sin pagar por
   otra vía y total): **un solo cobro**, en el diario Yappy, y queda anotado **quién lo confirmó y cuándo**. El pendiente se cierra
   solo. Si el aviso de Yappy llega tarde, **no hace nada** (ya estaba pagado).
3. Si el dinero **no entró**: no se hace nada; el pedido sigue guardado para retomarlo con el cliente.
4. **No se registra el cobro a mano en el diario Yappy** para una orden que sigue abierta: si el aviso llegara después se
   registraría el mismo dinero dos veces. (Si por error se hizo, el sistema **no** crea el segundo cobro: manda el aviso tardío a
   revisión humana con una alerta clara —«el pedido ya estaba pagado… si es el mismo dinero, no hay nada más que hacer»— y el
   pendiente «sin aviso» se cierra solo cuando llega el aviso, el que sea.)

*Por qué esta política y no «registra el pago a mano»:* era la instrucción que dejaba el cobro doble (a mano + aviso tardío) sin
ninguna alerta y con el pendiente todavía abierto invitando a repetirlo (revisión RV6, H2). El botón es simple y seguro porque
**no es un camino nuevo**: reutiliza el del aviso, así que el pedido, el cobro, la nota y las comprobaciones son los mismos. Los
casos de revisión de §3.3 (cobro que llegó a una transacción cerrada, pedido cambiado, entorno distinto, pedido cancelado) sí se
resuelven registrando el pago a mano **porque ahí el aviso ya llegó y está marcado** (un segundo aviso nunca paga nada).

## 4. Topes (para que un abusador no vacíe la tienda ni se cobre de más)

Antes de llamar a Yappy (`models/payment_transaction.py`):

| Tope | Valor | Qué pasa al pasarse |
|---|---|---|
| Cobros abiertos por pedido | 5 en 15 minutos (**estricto** aunque lleguen a la vez: antes de contar se «toca» la fila del pedido y el que llega después espera y cuenta con datos nuevos) | «Ya hay varios intentos…» y no se llama a Yappy |
| Cobros abiertos por conexión | 30 por hora (por huella de la conexión: un HMAC de la IP; **la IP no se guarda**). El equipo con sesión no cuenta | «Has abierto varios intentos…» |
| Cobros abiertos en total | 300 por hora | «Hay muchos pagos en curso…» |
| Llamadas a Yappy a la vez | 6 en todo el servidor (sin esperar) | «Hay muchos pagos en curso…» y la tienda sigue sirviendo |
| `/payment/yappy/iniciar` | 8 por minuto por conexión (responde HTTP 200 con un mensaje para la clienta, no un 429) | «Estás intentando pagar muchas veces seguidas…» |
| `/payment/yappy/ipn` | 120 por minuto (429) | Yappy reintenta |

Los topes son del código; no son cifras del negocio. **Riesgo aceptado (revisión RV6, H7):** el error `E005` («ese número no está
registrado en Yappy») deja averiguar qué celulares tienen Yappy, y cada intento con un celular registrado le manda una
solicitud de pago a esa persona; es inherente al diseño de Yappy y lo acotan los frenos de arriba (8 por minuto por conexión,
30 por hora por conexión, 300 por hora en total). Los intentos que terminan en error no cuentan para el tope por pedido. El ritmo se cuenta en memoria de cada proceso (si Odoo corre con varios,
cada uno cuenta aparte): es el primer freno, no el único (los topes por base de datos de arriba sí son globales).

## 5. Qué ve el equipo: «qué compró cada persona»

La API de Yappy **no manda el detalle de lo comprado** (solo el total). Por eso el detalle sale **de Odoo**, del pedido,
y se junta con el pago en un solo lugar. No hay canal nuevo ni datos del cliente fuera de Odoo.

- **En el pedido** (Ventas › Pedidos, y Caja/vendedora lo abren como siempre): un bloque **«Pago, entrega y origen»** justo
  arriba de las líneas, con *cómo pagó* (Yappy, estado, de cuánto, cuándo, la orden de Yappy y el número de confirmación
  marcado como informativo), *el origen* (Página web, enlace de vendedora…) y *la entrega* (retiro en tienda o envío con su
  dirección). El celular del cliente ya sale en «Sus datos». Las **líneas del pedido** traen el producto, el **modelo** (la
  variante), la cantidad, el precio y el descuento. Solo aparece si el pedido es de la web o tiene un pago en línea.
- **En la transacción** (Facturación › Clientes › **Pagos con Yappy**): lista con pedido, celular y orden de Yappy; filtros
  «Esperando el aviso» y «Para revisar»; al abrir una, el bloque **«Qué compró»** con la tabla de líneas (producto y modelo,
  cantidad, precio, descuento, total, «pieza de» si es un combo) y las mismas líneas de entrega y origen. Es de solo lectura.
- **En el chatter del pedido**, al llegar el `E`: una **nota interna** (no manda correo ni toca al cliente) con lo que compró,
  cómo recibe y cuánto pagó. El texto se escapa (un nombre de producto no puede inyectar HTML).
- **El pedido que no se pagó sigue mostrando lo que quedó** (las líneas no se borran): sirve para retomarlo. Los filtros
  «Pagados con Yappy» y «Yappy sin completar (para retomar)» están en la búsqueda de pedidos.
- **El equipo se entera donde ya se entera de los pedidos de la web**: las notas internas del pedido y la tarjeta
  «Compraron en la web y aún no se entregan». No hay canal nuevo ni correo; las claves nunca están en estas pantallas.
- **Permisos:** «Pagos con Yappy» es de **Caja, Gerencia y contabilidad**; la vendedora **no** lo ve (igual que «Cobros de hoy
  (caja)»: es la lista de los pagos de toda la tienda), pero sí el bloque «Pago, entrega y origen» en sus pedidos, que ya veía.
  **El celular de Yappy de quien paga (y el identificador de Yappy y la huella de la conexión) son de Caja y superiores a nivel
  de CAMPO**, no solo de menú: la vendedora tiene permiso de leer transacciones por Facturación y antes lo leía por RPC de
  todas las clientas. Ahora recibe un error de acceso, el pedido y su nota **no** llevan el celular de Yappy (solo el del
  cliente, que ya figura en el pedido) y el flujo de la clienta no cambia (el servidor lo escribe con `sudo`).
  Los campos del bloque son calculados (no hay datos nuevos guardados): arman el texto leyendo el pedido con permisos de
  sistema, así que **quien lee la transacción ve lo comprado aunque no tenga Ventas** (contabilidad ya ve esas mismas líneas
  en las facturas).

Las capturas antes/después de lo que ve Caja están en el scratchpad de la sesión (`capturas/yappy/`), no en el repositorio.

## 6. Qué poner en Cloudflare

Los datos de acceso se pegan **solo** en el panel de Cloudflare de cada Worker: no en GitHub, no en Odoo, no por el chat. Los
despliegues usan `--keep-vars` y no tocan lo que se pegó. Ninguna clave tiene campo en Odoo: ni en un campo, ni en un log, ni en
una vista, ni en una prueba, ni en este documento.

| Nombre (tal cual, en mayúsculas) | Tipo en Cloudflare | Qué dato es | Para qué sirve |
|---|---|---|---|
| `YAPPY_ID_COMERCIO` | **Secreto** | El «ID del comercio» (Merchant ID) del botón en Yappy Comercial | Identifica el comercio en cada cobro |
| `YAPPY_CLAVE_SECRETA` | **Secreto** | La «Clave secreta» del botón (Yappy la muestra **una sola vez**) | Firma los avisos: sin ella no se puede comprobar un pago |
| `YAPPY_DOMINIO` | Variable normal (Texto) | El dominio que se escribió al crear el botón, **letra por letra** | Viaja en cada cobro y entra en la firma del aviso |
| `YAPPY_ENTORNO` | Variable normal (Texto) | `prueba` o `produccion` | A qué servidor de Yappy se le habla y qué se espera. Sin ella, `prueba` |
| `YAPPY_URL_BASE` | Variable normal (Texto), **opcional** | La dirección pública `https://…` (sin ruta) a la que Yappy avisa. **Solo staging** (fijada en `edge/wrangler.jsonc`) | Manda sobre `web.base.url` al armar la `ipnUrl`. En producción Odoo la **ignora** |

- Staging lleva `YAPPY_ENTORNO=prueba` **fijado en el código** (`edge/wrangler.jsonc`): un despliegue siempre la deja así, y
  aunque alguien pegue `produccion`, el servidor de staging no es el de producción (`DCASA_ENTORNO`) y Odoo sigue en `prueba`.
- Producción **no** la fija: la dueña la pone en `produccion` cuando Yappy aprueba el botón.
- `YAPPY_URL_BASE` (H1 de la revisión RV6) existe porque `web.base.url` de staging es `https://staging.dcasapty.com`, que hoy **no
  apunta al Worker de staging** (`routes: []`): el aviso que Yappy mandara allí no llegaría y **ningún cobro de prueba podría
  quedar pagado** (todos terminarían en el pendiente de 15 minutos). Detalle y cómo comprobarlo en §7 B.
- Si falta cualquiera de las tres claves (o la clave secreta no tiene la forma de base64 que da Yappy), «Yappy directo» **no
  aparece**, sigue el «Yappy» de siempre y la pantalla del proveedor dice **qué variable falta, por su nombre** (nunca un valor).
- Los cambios llegan a Odoo al reiniciar o en el siguiente despliegue.

Pasos en el panel (uno por uno), en el Worker **`dcasa-staging`** primero: Cloudflare › Workers y Pages › el Worker ›
Configuración › Variables y secretos › **+ Agregar**: tipo **Secreto** para `YAPPY_ID_COMERCIO` y `YAPPY_CLAVE_SECRETA`, tipo
**Texto** para `YAPPY_DOMINIO` (y `YAPPY_ENTORNO` solo en producción). Luego, en Odoo: Facturación › Configuración ›
Proveedores de pago › **Yappy directo**: mira «Claves de Yappy cargadas», «Entorno de Yappy» y el dominio, y pulsa **Probar
conexión** (§7).

## 7. Lista para la dueña antes de cobrar (con dinero de mentiras primero)

**A. En Yappy Comercial** (con un usuario **administrador** de la cuenta):

1. Entrar a Yappy Comercial con un usuario **administrador** y crear el **Botón de Pago**.
2. Al crearlo, escribir el **dominio** del sitio. **Es lo que más falla:** se escribe letra por letra como se va a poner en
   `YAPPY_DOMINIO` (ver §9). Anotar exactamente cómo se escribió.
3. Yappy muestra el **ID del comercio** y la **clave secreta**. **La clave secreta se ve una sola vez:** copiarla y pegarla
   directo en Cloudflare (`YAPPY_CLAVE_SECRETA`), sin guardarla en un documento, un chat ni un correo. Si se perdió, se genera
   otra en Yappy Comercial.
4. Escribir a **botondepagoyappy@bgeneral.com** pidiendo el acceso al **programa de pruebas** del botón (el servidor UAT) y
   preguntar los puntos «sin documentar» de §8.

**B. En Cloudflare:** pegar las variables de §6 en `dcasa-staging` (el dominio de pruebas). Ver que Odoo diga «Claves
cargadas: Sí» y «Entorno: Prueba», y pulsar **Probar conexión** (Yappy valida el ID de comercio y el dominio; la clave
secreta se comprueba en el primer cobro de prueba porque Yappy no documenta una llamada solo para eso).

**La dirección a la que Yappy avisa en staging (sin esto la prueba termina siempre en el pendiente de 15 minutos).** Yappy avisa
de cada pago con un `GET` a la `ipnUrl` que Odoo le manda al abrir el cobro. Esa dirección sale de `web.base.url`, que en staging
es `https://staging.dcasapty.com` (`CANONICAL_HOST`), y ese dominio **todavía no apunta al Worker** (`"routes": []` en
`edge/wrangler.jsonc`). Por eso staging trae fijada, en el propio `edge/wrangler.jsonc`, la variable no secreta
`YAPPY_URL_BASE=https://dcasa-staging.dcasapty.workers.dev`: la dirección `workers.dev` del Worker de staging (`dcasa-staging`),
la misma que ya usa el aviso de la caché de páginas (`TIENDA_AVISO_URL`), viva porque `workers_dev` está en `true`. Con ella la
`ipnUrl` es `https://dcasa-staging.dcasapty.workers.dev/payment/yappy/ipn` y Odoo la muestra en el proveedor («Dirección del
aviso (ipnUrl)»). Cuando `staging.dcasapty.com` apunte al Worker (la línea de `routes` que ya está comentada), se borra
`YAPPY_URL_BASE` y vuelve `web.base.url`. En producción la variable **se ignora** aunque alguien la ponga.
  - **Comprobarlo una vez desde afuera** (un celular con datos, o `curl` desde otra máquina; las sesiones de Claude no llegan a
    `workers.dev`): `curl -i 'https://dcasa-staging.dcasapty.workers.dev/payment/yappy/ipn?orderId=PRUEBA&status=E&domain=x&hash=x'`
    debe contestar **`403` con el texto `no autorizado`** (llegó a Odoo y lo rechazó, que es lo correcto). Un `5xx`, un tiempo
    agotado o una página de Cloudflare («Just a moment…», «Sorry, you have been blocked») quiere decir que el aviso no llega: mirar
    *Seguridad › Eventos* de Cloudflare (WAF, Bot Fight Mode, Browser Integrity Check: pueden bloquear un `GET` de servidor sin
    navegador) y la puerta del equipo.
  - **Lo que NO se pudo comprobar** desde donde se escribió esto: que esa dirección `workers.dev` responda hoy, y si Yappy acepta una
    `ipnUrl` cuyo anfitrión no es el de `YAPPY_DOMINIO` (si la rechaza con `E011` —«error en los campos de URL»—, la salida es apuntar
    `staging.dcasapty.com` al Worker). Está entre las preguntas de §15.

**C. En Odoo (staging):** poner el proveedor en **Modo de prueba** y dejarlo **sin publicar**. Hacer la compra de ensayo: un
pedido de la tienda, elegir Yappy, tocar el botón y aprobar como indique Yappy para su servidor de pruebas. Comprobar: el pedido queda pagado, el pago cae
en el diario Yappy y la nota «Qué compró» aparece en el pedido. Repetir con un rechazo, una cancelación y una expiración. En
producción, la prueba con «Modo de prueba» queda **confirmada de verdad** (reserva inventario): se anula al terminar.

**D. A producción:** cuando todo salió bien, `YAPPY_ENTORNO=produccion` en Cloudflare, proveedor **Habilitado** y publicado.
Solo con el **sí** de la dueña a lo que vio (capturas antes/después del cambio visual).

## 8. Lo que Yappy no dejó escrito (preguntar por escrito; hasta entonces el código no lo supone)

| | Pregunta | Qué hace el código mientras tanto |
|---|---|---|
| 1 | ¿Cuánto vale el `token` de `validate/merchant`? ¿Se puede reusar? | Pide uno nuevo en cada cobro (dos llamadas por cobro) |
| 2 | ¿La cabecera lleva `Authorization: <token>` o `Bearer <token>`? | Manda el token solo, como el ejemplo; si Yappy dijera otra cosa, el cobro fallaría con un error claro y se cambia una línea |
| 3 | `paymentDate`: ¿segundos o milisegundos desde 1970? | Segundos |
| 4 | ¿Reintenta el aviso si respondemos error? ¿Cuántas veces? ¿Con qué código de respuesta da por entregado? | Responde 200 «ok» al recibido y válido; 500 si fallamos nosotros; 403 si no es de fiar. Si Yappy **no** reintenta, un aviso perdido lo cubre el pendiente de §3.4 |
| 5 | ¿Desde qué direcciones manda el aviso? | No se filtra por IP: la firma es la defensa |
| 6 | ¿En qué campo viene el código de error (`E0xx`) y qué otros hay? | Lo busca por patrón en el estado y el mensaje de la respuesta; lo desconocido es un error genérico, sin repetir texto del servidor |
| 7 | ¿El `domain` del aviso vuelve como se declaró o normalizado (sin `www`, sin `https://`, en minúsculas)? | Acepta nuestro sitio escrito con o sin `http://`/`https://`, con o sin `www.`, en mayúsculas o minúsculas, con el puerto por defecto y con barras al final (§9); un dominio ajeno nunca. Si rechaza un aviso por el dominio, deja en el registro cuál llegó y cuál está declarado |
| 8 | ¿Qué pasa con un cobro que la clienta no aprueba nunca (sin `X`)? | El pendiente de §3.4 a los 15 minutos |
| 9 | ¿Qué es exactamente `confirmationNumber` y cuándo viene? | Se guarda solo como informativo: **no está firmado**, no decide nada |
| 10 | ¿Hay límite de monto o de cobros por minuto? | No se asume ninguno; los topes de §4 son de nosotros |
| 11 | ¿Cuál es la regla de **cuadre de los importes**? | Manda `subtotal = total`, `taxes = 0.00` y `discount = 0.00` (el ITBMS, el envío y el descuento ya van dentro del total del pedido). Si Yappy exigiera el ITBMS aparte, contestaría `E010` y el cobro no abre |
| 12 | ¿`aliasYappy` es obligatorio en producción? ¿Qué teléfono vale en el programa de pruebas? | Siempre se manda el celular que escribe la clienta; si es obligatorio, ya cumple |
| 13 | ¿El programa de pruebas sirve con **iPhone** o solo con **Android**? (su documentación pide la versión de Android y no dice nada de iPhone) | Nada: sin un Android no hay ensayo; se pregunta antes de contar con la compra de prueba |
| 14 | ¿Hay una **consulta de estado o de movimientos** por API (la de «Integraciones» de Yappy Comercial) para recuperar un aviso perdido? | No se usa ninguna: el aviso perdido lo cubre el pendiente de §3.4 con el botón de Caja |
| 15 | ¿Yappy acepta una `ipnUrl` con un anfitrión distinto al de `YAPPY_DOMINIO`? (staging usa `workers.dev`, §7 B) | Si contestara `E011`, el cobro no abre y el mensaje a la clienta es el general; la salida es apuntar `staging.dcasapty.com` al Worker |
| 16 | **Cloudflare:** ¿alguna regla (WAF, Bot Fight Mode, Browser Integrity Check) bloquea el `GET` del aviso desde los servidores de Yappy? | No se sabe hasta probarlo desde afuera (§7 B); *Seguridad › Eventos* lo muestra. Es lo que Tilopay ya tiene escrito |

## 9. Trampas que ya se conocen

- **El anfitrión del botón.** El ejemplo de la documentación trae `bt-cdn.yappycloud.com`, que **no responde**. Los que sirven
  son `bt-cdn.yappy.cloud` (producción) y `bt-cdn-uat.yappycloud.com` (pruebas). El código carga solo esos dos y por `https`.
- **El dominio, letra por letra.** Con o sin `www`, con o sin `https://`, con o sin barra final: para Yappy son dominios
  distintos, y un descuido da un error al crear el cobro o un aviso que no cuadra. `YAPPY_DOMINIO` se manda **tal cual** y tiene
  que ser igual a lo escrito en Yappy Comercial. Del lado del aviso, como Yappy no dice cómo lo devuelve, se acepta
  nuestro propio sitio escrito de cualquiera de estas maneras: con o sin `http://` o `https://`, con o sin `www.`, en mayúsculas o
  minúsculas, con el puerto por defecto (`:443`, o `:80` con `http://`) y con barras al final (**no «16 maneras»: eran 8 y no
  cubrían `http://`, las mayúsculas ni `:443`**, y eso rechazaba con `403` un aviso real que viniera así). Se compara el anfitrión
  ya normalizado, en tiempo constante; **no pasa nada que no sea nuestro dominio** (ni `@`, ni subdominios, ni rutas, ni espacios;
  una batería de 813,375 candidatos hostiles no dejó pasar ninguno). La firma se calcula sobre el dominio **tal como llegó** y se
  comprueba igual. Cuando un aviso se rechaza por el dominio, el registro del servidor dice cuál llegó y cuál está declarado
  (nunca la firma), y el pendiente de Caja ya no dice «Yappy no avisó nada» sino «llegó un aviso y se rechazó».
- **`E007` no es un fallo.** Significa «esa orden ya estaba registrada». Se trata como «ya estaba» (el intento sigue abierto y se
  espera el aviso), no como un error para la clienta.
- **El número de confirmación (`confirmationNumber`) no está firmado.** Cualquiera puede agregarlo a una dirección. Nunca decide
  nada; solo se muestra como informativo.
- **El navegador nunca marca un pago.** `eventSuccess` solo lleva a la página de estado. Una prueba automática intenta pagar solo
  con el navegador y confirma que no pasa.
- **Una orden de más de 15 caracteres o con guion da `E009`:** por eso el código arma la orden y la valida antes de llamar.
- **`eventError` antes del primer pago no es un pago fallido.** El botón lo usa para decir que no está disponible; si se
  reconstruyera en cada `eventError` habría un ciclo infinito. Solo se reconstruye después de un intento.
- **El botón carga cosas de terceros.** Con el componente real (script de PRUEBAS de Yappy en Chrome, 2026-11-20) se vio llamar a:
  al **elegir** la fila «Yappy» (nunca antes: con la tienda y el pago sin elegir no sale ninguna llamada a otro dominio),
  `bt-cdn-uat.yappycloud.com` (el script y los logos), `fonts.googleapis.com` y `fonts.gstatic.com` (la letra Nunito Sans, de
  Google) y `api-comecom-uat.yappycloud.com` (`/handshake`: «¿Yappy está disponible?»); al **pulsar** el botón,
  `identitytoolkit.googleapis.com` (Firebase Auth, `signInWithCustomToken`), más el logo del contador. Deja en el navegador
  `sessionStorage.timerDuration` y dos bases (`firebase-heartbeat-database`, `firebaseLocalStorageDb`); ninguna cookie de terceros.
  En producción el código apunta a `bt-cdn.yappy.cloud`, `apipagosbg.bgeneral.cloud` y al proyecto Firebase `yappy-pa` (no se ejecutó
  contra producción). Con un token válido el componente también escucha el documento del pago en Firestore (Google), y su código
  nombra reCAPTCHA y `apis.google.com`, que con el token falso de las pruebas no se vieron. Eso es lo que hay que decir en la
  política de privacidad del sitio. No se puede quitar; si no carga (sin red, bloqueador de anuncios), la clienta ve un mensaje
  con «Volver a intentarlo» y «Escríbenos por WhatsApp».
- **La ventana de Yappy dentro de nuestra pantalla (medida con el componente real, 2026-11-20; capturas y guiones en el
  scratchpad de la sesión, no en el repositorio).** El componente **no usa shadow DOM**: se dibuja en la página, sus estilos se
  atan a sus propias etiquetas y los nuestros los pueden pisar (ya lo hacemos con el alto y la esquina del botón). La ventana es un
  `<dialog open>` **no modal** (sin capa superior): `position: fixed; inset: 0; z-index: 10`, puesta **junto** a `<btn-yappy>`
  dentro de la misma caja, con un fondo `fixed; z-index: 5`. Por eso: no atrapa el foco, Escape y el clic fuera no la cierran, la
  página de atrás sigue moviéndose con la rueda y el teclado, y mientras espera no tiene botón de cerrar (solo al terminar: error,
  vencida o pagada); al refrescar o volver atrás se cierra sola y avisa «No refresques el navegador». Lo que se arregló de
  NUESTRO lado:
  - La fila elegida crea su propio contexto de apilamiento (`z-index: 1`, `pago.scss`): la ventana quedaba **debajo** del resumen
    fijo de la derecha (1020) y de la barra de pagar del celular (1030); en la computadora el resumen tapaba la mitad de la ventana
    y su botón de cerrar. Con una ventana abierta, la fila sube a 1100 (`yappy.scss`).
  - En un celular acostado (844×390) la ventana (590 px) se cortaba arriba y abajo: ahora tiene alto máximo y se desplaza por dentro.
  - Tras un fallo, el botón nuevo avisaba «en línea» y **borraba el motivo** que la clienta no había leído: ahora solo borra su
    propio aviso de «Yappy no está disponible».
  - El contador de 5 minutos es del componente y, al llegar a cero, abre «Transacción expirada» **sin ningún evento**: al cerrarla
    el botón quedaba apagado para siempre con el mensaje «tienes 5 minutos». Ahora, al cerrarse la ventana sin evento, se pone un
    botón nuevo y se dice que venció.
  - El estado «ventana abierta» es compartido por todos los botones de la página: si la clienta no cerraba «Transacción cancelada» y
    pulsaba otra vez, la ventana del intento nuevo no abría y veía «cancelada» sobre «confirma el pago». Un intento nuevo cierra antes
    la ventana vieja; y con un intento vivo (Enter dos veces salta el `pointer-events: none` del botón) no se empieza otro.
  - Después de `eventSuccess` se usa `location.replace`: con «atrás» no se vuelve a un botón de Yappy listo para pagar otra vez.
  `eventError` también llega con valores que no son de la lista (`false` si Firebase rechaza el token; un error de red): mensaje
  general y botón nuevo.
- **Refrescar o cerrar a mitad, y pagar dos veces (pendiente de decisión, no es un fallo de dinero).** Con un cobro abierto el pedido
  queda `draft` con la transacción `pending` y Odoo suelta el carrito de la sesión: al refrescar o volver atrás la clienta cae en la
  tienda con el carrito vacío y «Mis pedidos» no lo lista; el aviso firmado sigue pudiendo pagarlo y `/payment/status` lo muestra.
  Propuestas: una guarda `beforeunload` mientras el intento está vivo, y mandar a `/payment/status` a quien vuelva a la tienda
  con un cobro de Yappy de menos de 5 minutos. Si abre dos cobros y paga los dos, los dos entran (`done`), el equipo recibe la
  actividad «Yappy: pedido pagado dos veces» y devuelve uno: se avisa, no se impide (Yappy no permite cancelar una orden).
  En «revisión» (llegó una `E` sobre una transacción ya cancelada) la pantalla de estado sigue ofreciendo «Intentar de nuevo»:
  conviene esconderlo mientras una persona mira el cobro.
- **La trampa de las etiquetas de prueba de Odoo.** `--test-tags /dcasa_pago_yappy` **no corre ninguna prueba**: la expresión
  regular de Odoo toma un nombre que termina en «py» por la ruta de un archivo `.py` (el punto sin escapar). Se usa la etiqueta
  sin barra (`dcasa_pago_yappy`) y `scripts/test.sh` ya lo hace solo. Un «0 pruebas, todo bien» en este módulo es un error.
- **Producto en MAYÚSCULAS.** D'CASA guarda los nombres en mayúsculas; las pruebas comparan sin distinguir mayúsculas.
- **Las claves nunca se imprimen.** `Credenciales` se muestra como `Credenciales(***)` si alguien la pone en un log.

## 10. Conciliar con el reporte de Yappy Comercial

Hay que conciliar a diario contra el reporte de **Yappy Comercial**: es la única fuente de verdad del dinero (Yappy no documenta una
consulta). Odoo ya lo facilita:

- Cada pago directo cae en el diario **Yappy** (el de siempre), y la **orden de Yappy** (empieza con el número del pedido) queda
  en la referencia de la transacción y en la nota del pago. Los pagos manuales caen en el mismo diario: la conciliación es una.
- El extracto del reporte se importa con **`dcasa_contabilidad`** (importación de extractos) contra ese diario.
- La comisión de Yappy **no está modelada**: la contadora decide su tratamiento (¿gasto bancario?, ¿cuenta aparte?). El módulo no
  trae ninguna cifra de comisión ni la inventa.
- Un cobro en «Para revisar» o «Esperando el aviso» se resuelve mirando ese reporte.

## 11. Qué revisar en Juan cuando se encienda Yappy directo (no se tocó Juan)

Juan no cambió. Cuando Yappy directo se encienda, quien lleve a Juan debería revisar que:

1. Si Juan explica **cómo pagar con Yappy**, ya no diga «te mandamos un número por WhatsApp»: con Yappy directo se paga **en la
   tienda**, desde la app (el apartado ya dice «pasa a pagarlo en la tienda»).
2. Siga sin **confirmar un pago** por su cuenta (las salvaguardas ya lo impiden). Un pago con Yappy directo lo confirma Odoo con
   el aviso firmado, no una captura que mande la clienta.
3. Cuando una clienta mande por WhatsApp la **captura de un Yappy**, quien la atienda mire primero si el pedido de la tienda ya
   dice «Yappy · pagado» (la nota «Qué compró» está en el pedido) antes de pedirle nada.
4. El texto de la tienda del «Yappy» manual (`website_dcasa/models/tienda.py`) sigue valiendo para cuando el directo esté apagado.

## 12. Pendientes y siguiente paso

1. **Acceso al programa de pruebas** de Yappy y la compra de ensayo (§7). Hasta entonces, todo se probó contra un Yappy
   simulado y con un `<btn-yappy>` simulado en el navegador.
2. Las preguntas de §8, por escrito.
3. **El cambio visual** (la fila «Yappy» con su campo y el botón, el bloque del pedido) está pendiente de que la dueña vea las
   capturas antes/después y diga que sí. Nada se une a la rama de trabajo ni se despliega hasta entonces.
4. Abonos parciales de apartados con Yappy; reembolsos (a mano en Yappy Comercial); comisión (la contadora).
5. Conciliación diaria contra Yappy Comercial (§10) desde el primer cobro real.
6. Revisión independiente (dinero): ver qué atacar abajo. **Hecha la segunda vuelta (RV6)** sobre `96bbd48`: sus hallazgos
   H1–H10 están arreglados o documentados (§14); lo que queda para cobrar de verdad es lo que solo Yappy y Cloudflare pueden
   confirmar (§15) y la decisión de la política de privacidad (§16).

### Qué debería atacar un revisor independiente

- El **aviso**: repetirlo, desordenarlo (`R` tras `E`), mandarlo en paralelo desde dos procesos, firmarlo para otro dominio,
  cambiar una letra de la orden, mandar la orden con espacios o saltos, partes duplicadas (`status=E&status=R`).
- El **dominio y el hash**: las formas aceptadas del dominio (¿alguna deja pasar uno ajeno?), la llave derivada (base64 raro, sin
  punto, con varios puntos, caracteres no UTF-8), la comparación en tiempo constante.
- Los **topes**: saltarlos con varias conexiones o varios pedidos; si la huella de la conexión se puede falsificar con
  `X-Forwarded-For` (el borde lo pisa con `CF-Connecting-IP`).
- `/payment/yappy/iniciar`: abrir el cobro de **otra persona** (la transacción tiene que ser la monitoreada en la sesión),
  un celular que no es de Panamá, un monto distinto, un `reference` ajeno.
- Los caminos de **revisión**: `E` sobre cobros cancelados, pedidos cambiados, pedido cancelado con cobro abierto, entorno cambiado,
  **pedido ya pagado a mano** (un cobro a mano y luego el aviso tardío: nunca un segundo cobro) y el botón «Confirmar que el dinero
  entró» (solo Caja; pasa por el mismo camino que el aviso).
- Un **corte** después de guardar la orden y antes de llamar a Yappy (la orden quedó anotada y Yappy no la tiene).
- El **CSS** que esconde la barra de pagar en el celular (`:has()`) y que el botón siga alcanzable; el puente de teclado.
- Que ninguna **clave** salga en un log, una vista, un campo, una nota o una respuesta (incluidos los errores de Yappy).

## 13. Cómo se probó

Con un Yappy falso (`tests/common.py`: `YappyFalso` sustituye a `requests.post`, sin red) y vectores de firma calculados
**aparte, con `openssl`**, no con el mismo código que se prueba. Hay pruebas de la API y la firma, del proveedor (nace
apagado, cuándo se ofrece, que retira al «Yappy» manual), del flujo y de cada estado, de las rutas (`/iniciar` y el aviso),
de «Qué compró», y once de navegador (Chrome con un `<btn-yappy>` simulado: celular y escritorio, un número malo, un fallo
de Yappy, el teclado, el botón que reaparece). Dos pruebas miran lo que una sola transacción no puede: `tests/test_concurrencia_real.py` lanza dos avisos
**al mismo tiempo con dos conexiones de verdad** (el segundo espera el candado del primero, y E+E, E+R y R+E terminan bien), pero
escribe datos de verdad, así que es **opt-in** (`DCASA_PRUEBA_CONCURRENCIA=1`, en una base de pruebas) y el CI no la corre; y
en `test_rutas.py` un choque de serialización simulado confirma que Odoo repite la petición y el aviso se aplica. Los conteos
exactos de la última corrida están en la bitácora
([LEEME_PRIMERO.md](LEEME_PRIMERO.md)). El borde: `edge/test/yappy.test.ts`.

## 14. Límites conocidos (documentados, no se cambian) y lo que arregló la segunda revisión

**Límites conocidos**

- **Se compara el total del pedido, no sus líneas** (RV6, H10). Si, mientras la clienta paga, se cambia el pedido por otros productos
  del **mismo precio total**, el aviso se paga: el dinero cuadra con el pedido. Lo que cambia el total sí va a revisión. El equipo
  ve las líneas de verdad en el pedido y en la nota «Qué compró».
- **«Qué compró» sirve a todos los proveedores de pago, pero vive en este módulo** (H10): los campos y las vistas del bloque «Pago,
  entrega y origen» del pedido y del bloque «Qué compró» de la transacción están en `dcasa_pago_yappy` (`models/sale_order.py`,
  `models/resumen.py`, `views/`). Si se desinstalara Yappy directo, el pedido perdería ese bloque aunque se pague con otro
  proveedor. Moverlos a un módulo común es un cambio aparte.
- **`E005` deja averiguar qué celulares tienen Yappy** y cada intento con un celular registrado le manda una solicitud de pago a
  esa persona (riesgo aceptado, §4).
- **El ritmo por conexión vive en memoria de cada proceso** (con `workers = 0` y una sola instancia es un solo proceso); los topes por
  base de datos sí son globales (§4).
- **Cuando faltan las claves en el servidor**, los avisos se rechazan con `403` y la tarea de «sin aviso» no deja pendientes hasta
  que vuelvan (sin claves no se ofrece nada y no se llama a nadie). Si pasara con cobros abiertos, el aviso rechazado queda anotado
  en su transacción y los pendientes salen cuando las claves regresan.
- **Mientras no haya compra de ensayo contra el Yappy real, todo lo de §8 son supuestos del código** (token, `Bearer`, unidad de
  `paymentDate`, reintentos y código de respuesta del aviso, IPs, campo del error, cuadre de importes). El diseño falla del lado
  seguro (nunca paga solo con algo dudoso), pero «cobrar de verdad» necesita confirmarlos (§15).

**Qué arregló la segunda revisión (RV6, sobre `96bbd48`)** — cada punto con su prueba, y la prueba cae sin el arreglo:

| | Qué era | Qué se hizo |
|---|---|---|
| H1 | El aviso de Yappy no llegaba a staging (`ipnUrl` = `staging.dcasapty.com`, sin ruta al Worker) | `YAPPY_URL_BASE` (§6, §7 B); el proveedor muestra la dirección del aviso |
| H2 | Cobro a mano + aviso tardío = dos cobros del mismo dinero, sin alerta; el pendiente seguía abierto; tres textos que se contradecían | Una política (§3.4): botón «Confirmar que el dinero entró»; un aviso sobre un pedido ya pagado por otra vía va a revisión y **nunca** crea otro cobro; el pendiente se cierra solo al llegar el aviso |
| H3 | Pedido cancelado con el cobro abierto + aviso `E` = transacción «hecha», cobro contable sobre un pedido anulado y «Confirmamos tu pedido» | Revisión humana con el mensaje correcto; el apartado que vence ya no anula un pedido con un cobro de Yappy abierto de menos de 15 minutos |
| H5 | La vendedora leía por RPC el celular de Yappy de todas las clientas | El campo es de Caja y superiores a nivel de modelo; el pedido y su nota no lo llevan |
| H6 | Un aviso real con el dominio escrito de otra forma (`http://`, mayúsculas, `:443`) se rechazaba y el pendiente decía «Yappy no avisó» | Normalización segura (§9), el registro dice qué dominio llegó, el pendiente dice «llegó un aviso y se rechazó» |
| H7 | El tope de 5 cobros por pedido no era estricto en paralelo (12 conexiones abrieron 6); Enter mantenida repetía el clic | El tope es estricto (§4); el botón no admite un segundo clic mientras hay uno en curso |
| H8 | Dos mutaciones sobrevivían (`eventSuccess` hacia otra página; el host de producción roto en la lista del JavaScript) | Pruebas que las matan (navegador y lectura del archivo) |
| H9 | Documentación: «16 maneras», «(429)», «no tiene consulta de estado», faltaban preguntas | Corregido (§2, §4, §8, §9) y la lista para la dueña en §15 |
| H4 | El botón mete terceros que la política de privacidad no menciona | Documentado en §16 para que la dueña decida; **el texto legal no se tocó** |
| H10 | Se compara el total, no las líneas; «Qué compró» vive en este módulo | Documentado arriba como límite conocido |

## 15. Preguntas para Yappy y Cloudflare (lista para la dueña)

Escribirlas **por escrito** a **botondepagoyappy@bgeneral.com** (dudas de la guía del botón) y, las de integración, a
**yappy@bgeneral.com**. Hasta que contesten, el código no supone nada de esto (§8) y falla del lado seguro. Se guarda cada respuesta
con su fecha en este documento.

1. **¿Cómo escribe Yappy el `domain` del aviso?** Con `http://` o sin él, en mayúsculas o minúsculas, con o sin barra final. Y si el
   `hash` lleva el dominio que declaramos o el ya normalizado.
2. **¿Reintenta el aviso?** Cuántas veces, pasado cuánto tiempo, y con qué respuesta da por entregado un aviso (hoy contestamos
   `200` «ok» / `403` / `500`).
3. **¿Desde qué direcciones (IP) manda el aviso y cuántos por minuto?** (Hoy hay un freno de 120 por minuto por conexión.)
4. **¿Cuánto dura el `token` de `validate/merchant`?** ¿La cabecera `Authorization` lleva la palabra `Bearer` o el token solo (hoy
   mandamos el token solo)?
5. **¿`paymentDate` va en segundos o en milisegundos?** (Hoy, segundos.) ¿`aliasYappy` es obligatorio en producción?
6. **¿Cuál es la regla de cuadre de los importes?** Hoy mandamos `subtotal` = `total` e impuestos y descuento en `0.00`; ¿el ITBMS
   tiene que ir aparte (`E010`)?
7. **¿En qué campo llega el código de error `E0xx` y cuáles otros existen?** (Hoy lo buscamos por patrón.)
8. **¿Qué es `confirmationNumber`?** ¿Hay una consulta de estado o de movimientos por API (la de «Integraciones») para recuperar un
   aviso perdido?
9. **Cloudflare (no es de Yappy, lo mira quien administra el dominio):** que ninguna regla de bots, WAF ni *Browser Integrity Check*
   bloquee el `GET` del aviso desde los servidores de Yappy (se prueba con el `curl` de §7 B y mirando *Seguridad › Eventos*).
10. **El programa de pruebas: ¿sirve con iPhone o solo con Android?** (Su guía pide la versión de Android y no dice nada de iPhone.)
    Y si Yappy acepta una `ipnUrl` cuyo anfitrión no es el de `YAPPY_DOMINIO` (staging usa `workers.dev`).

## 16. Política de privacidad: decisión de la dueña

**Qué pasa hoy y por qué importa.** La política de privacidad del sitio (`addons/website_dcasa/views/legal_templates.xml`, secciones
«Con quién los compartimos» y «Cookies») dice que se usan «solo cookies técnicas» y no menciona ni a Yappy ni al Banco General ni a
Google. Al elegir «Yappy» en el pago, el navegador de la clienta carga un script de ~545 KB **de un tercero** que habla con otros
servidores, y a Yappy / Banco General viajan el celular de la clienta, el total y la orden. **Qué decir y con qué palabras lo decide
la dueña con quien corresponda: este repositorio no cambió el texto legal.**

**Lo que se sabe del componente (por lectura del paquete y por la prueba con el componente real; sin ejecutar nada de producción).**
Se carga **solo al elegir** la fila «Yappy» (nunca antes). Los dominios, y qué hace cada uno:

| Dominio | De quién | Qué hace |
|---|---|---|
| `bt-cdn.yappy.cloud` (producción) · `bt-cdn-uat.yappycloud.com` (pruebas) | Yappy / Banco General | Sirve el script del botón y sus logos |
| `apipagosbg.bgeneral.cloud` (producción) · `api-comecom-uat.yappycloud.com` (pruebas) | Yappy / Banco General | La API a la que el botón le pregunta si Yappy está disponible y por el cobro |
| `identitytoolkit.googleapis.com` (y `securetoken.googleapis.com`) | Google (Firebase Authentication, proyecto `yappy-pa` de Yappy) | Autentica el cobro del botón con el token que da Yappy |
| `yappy-pa.firebaseapp.com` · `yappy-pa-default-rtdb.firebaseio.com` · Firestore | Google (Firebase, proyecto de Yappy) | Escucha el estado del pago en la nube de Yappy |
| `fonts.googleapis.com` y `fonts.gstatic.com` | Google | La letra «Nunito Sans» del botón |
| `www.google.com/recaptcha/…` y `apis.google.com` | Google | **Nombrados en el código** del componente (reCAPTCHA y la biblioteca de Google); con el token falso de las pruebas no se vieron cargarse: confirmarlo con la pestaña *Red* del navegador en la compra de ensayo |

Además deja en el navegador `sessionStorage.timerDuration` y dos bases locales (`firebase-heartbeat-database`,
`firebaseLocalStorageDb`); no se vio ninguna cookie de un tercero. **Esto se verifica de nuevo en la compra de ensayo** (pestaña
*Red* y *Aplicación* del navegador, con el script de pruebas y luego con el de producción): lo de arriba es lo leído, no una promesa.

**Borrador de párrafo — SOLO COMO PROPUESTA, SIN APLICAR** (la dueña lo reescribe, o no, con quien corresponda; no lleva cifras ni
citas legales a propósito):

> *Pago con Yappy.* Si pagas con Yappy, tu navegador carga el botón de pago que nos da Yappy (Banco General). Ese botón se comunica
> con los servidores de Yappy y con servicios de Google (para identificar el pago y para su letra) y puede guardar datos técnicos en
> tu navegador mientras pagas. A Yappy le llegan tu número de Yappy, el total y el número de tu pedido para cobrarlo; nosotros solo
> sabemos que el pago se hizo cuando Yappy nos lo avisa, y no vemos tu clave ni los datos de tu app. Eso no son cookies nuestras ni
> de publicidad. Si no quieres usarlo, puedes pagar de otra forma o escribirnos por WhatsApp.

**Lo que habría que ajustar si la dueña lo decide:** la lista «Con quién los compartimos» (agregar a Banco General / Yappy y a
Google) y la frase «Usamos solo cookies técnicas… No usamos cookies de publicidad ni de analítica de terceros» (el componente usa
almacenamiento del navegador que no son cookies). Si algún día el borde agregara una política de contenido (`script-src`), habría
que permitir el CDN de Yappy, Google reCAPTCHA y Firebase (hoy el borde solo manda `frame-ancestors 'self'`, así que no bloquea nada).
