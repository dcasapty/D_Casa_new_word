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

Lo que Yappy **no tiene** (según lo leído): consulta del estado de un cobro y reembolsos. Por eso, si el aviso no llega,
**nadie puede preguntarle a Yappy**: queda un pendiente para una persona (§3.4).

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
- **El botón de Yappy es de Yappy.** Se carga solo cuando la clienta elige la fila «Yappy» (son ~545 KB de un tercero). De sus
  seis temas se usa `dark` (blanco sobre `#444c5e`, contraste 8,6:1; los otros cinco quedan entre 2,2 y 4,5:1), medido leyendo el
  paquete real, sin ejecutarlo. El componente se apaga solo al pulsarlo (`disable-btn`): después de un fallo la página **tira el botón
  y pone uno nuevo**. Para el teclado, la caja del botón reenvía Enter y Espacio. Las capturas usan un **sustituto** con ese aspecto
  documentado (el original carga reCAPTCHA y Firebase y no corre sin conexión ni sin sus claves): así se dice en cada captura.
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
| `E` | el entorno del cobro no es el de hoy (prueba/real) | **Revisión humana**: un pago de prueba no paga un pedido real |
| `E` | el pedido fue cancelado y la transacción seguía abierta | La transacción queda hecha y se **alerta** (el dinero entró), como en Tilopay |
| firma o dominio malos, forma rara | cualquiera | **403** «no autorizado» (el mismo texto para todo motivo). Nada cambia |
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
  atacante cuál de las dos comprobaciones falló. El motivo real queda en el registro, sin la firma recibida.
- **La firma nunca se «calcula» en el navegador ni se guarda.** Ni la clave, ni la llave derivada, ni el hash recibido salen de
  la comprobación.

### 3.4 El aviso que no llegó

Yappy no tiene consulta de estado. Pasados **15 minutos** sin aviso, una tarea (`Yappy: cobros sin aviso`, cada 10 minutos)
deja **un solo pendiente** en el pedido para Caja (si no hay quien atienda, para Gerencia) con el detalle de lo que compró y
la orden de Yappy. **No paga ni cancela por sí sola**: la persona abre el reporte de Yappy Comercial y confirma ahí si el
dinero entró; si entró y el pedido sigue sin pagar, avisa a quien programa (no se marca a mano).

## 4. Topes (para que un abusador no vacíe la tienda ni se cobre de más)

Antes de llamar a Yappy (`models/payment_transaction.py`):

| Tope | Valor | Qué pasa al pasarse |
|---|---|---|
| Cobros abiertos por pedido | 5 en 15 minutos | «Ya hay varios intentos…» y no se llama a Yappy |
| Cobros abiertos por conexión | 30 por hora (por huella de la conexión: un HMAC de la IP; **la IP no se guarda**). El equipo con sesión no cuenta | «Has abierto varios intentos…» |
| Cobros abiertos en total | 300 por hora | «Hay muchos pagos en curso…» |
| Llamadas a Yappy a la vez | 6 en todo el servidor (sin esperar) | «Hay muchos pagos en curso…» y la tienda sigue sirviendo |
| `/payment/yappy/iniciar` | 8 por minuto por conexión (429) | espera |
| `/payment/yappy/ipn` | 120 por minuto (429) | Yappy reintenta |

Los topes son del código; no son cifras del negocio. El ritmo se cuenta en memoria de cada proceso (si Odoo corre con varios,
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

- Staging lleva `YAPPY_ENTORNO=prueba` **fijado en el código** (`edge/wrangler.jsonc`): un despliegue siempre la deja así, y
  aunque alguien pegue `produccion`, el servidor de staging no es el de producción (`DCASA_ENTORNO`) y Odoo sigue en `prueba`.
- Producción **no** la fija: la dueña la pone en `produccion` cuando Yappy aprueba el botón.
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
secreta se comprueba en el primer cobro de prueba porque Yappy no tiene una llamada solo para eso).

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
| 7 | ¿El `domain` del aviso vuelve como se declaró o normalizado (sin `www`, sin `https://`)? | Acepta 16 maneras de escribir **nuestro** sitio (§9); un dominio ajeno nunca |
| 8 | ¿Qué pasa con un cobro que la clienta no aprueba nunca (sin `X`)? | El pendiente de §3.4 a los 15 minutos |
| 9 | ¿Qué es exactamente `confirmationNumber` y cuándo viene? | Se guarda solo como informativo: **no está firmado**, no decide nada |
| 10 | ¿Hay límite de monto o de cobros por minuto? | No se asume ninguno; los topes de §4 son de nosotros |

## 9. Trampas que ya se conocen

- **El anfitrión del botón.** El ejemplo de la documentación trae `bt-cdn.yappycloud.com`, que **no responde**. Los que sirven
  son `bt-cdn.yappy.cloud` (producción) y `bt-cdn-uat.yappycloud.com` (pruebas). El código carga solo esos dos y por `https`.
- **El dominio, letra por letra.** Con o sin `www`, con o sin `https://`, con o sin barra final: para Yappy son dominios
  distintos, y un descuido da un error al crear el cobro o un aviso que no cuadra. `YAPPY_DOMINIO` se manda **tal cual** y tiene
  que ser igual a lo escrito en Yappy Comercial. Del lado del aviso, como Yappy no dice cómo lo devuelve, se aceptan las 16
  maneras de escribir nuestro propio sitio; la firma se comprueba igual.
- **`E007` no es un fallo.** Significa «esa orden ya estaba registrada». Se trata como «ya estaba» (el intento sigue abierto y se
  espera el aviso), no como un error para la clienta.
- **El número de confirmación (`confirmationNumber`) no está firmado.** Cualquiera puede agregarlo a una dirección. Nunca decide
  nada; solo se muestra como informativo.
- **El navegador nunca marca un pago.** `eventSuccess` solo lleva a la página de estado. Una prueba automática intenta pagar solo
  con el navegador y confirma que no pasa.
- **Una orden de más de 15 caracteres o con guion da `E009`:** por eso el código arma la orden y la valida antes de llamar.
- **`eventError` antes del primer pago no es un pago fallido.** El botón lo usa para decir que no está disponible; si se
  reconstruyera en cada `eventError` habría un ciclo infinito. Solo se reconstruye después de un intento.
- **El botón carga cosas de terceros** (reCAPTCHA, Firebase, fuentes de Google). Es del componente de Yappy; no se puede quitar.
  Si no carga (sin red, bloqueador de anuncios), la clienta ve un mensaje con «Volver a intentarlo» y «Escríbenos por WhatsApp».
- **La trampa de las etiquetas de prueba de Odoo.** `--test-tags /dcasa_pago_yappy` **no corre ninguna prueba**: la expresión
  regular de Odoo toma un nombre que termina en «py» por la ruta de un archivo `.py` (el punto sin escapar). Se usa la etiqueta
  sin barra (`dcasa_pago_yappy`) y `scripts/test.sh` ya lo hace solo. Un «0 pruebas, todo bien» en este módulo es un error.
- **Producto en MAYÚSCULAS.** D'CASA guarda los nombres en mayúsculas; las pruebas comparan sin distinguir mayúsculas.
- **Las claves nunca se imprimen.** `Credenciales` se muestra como `Credenciales(***)` si alguien la pone en un log.

## 10. Conciliar con el reporte de Yappy Comercial

Hay que conciliar a diario contra el reporte de **Yappy Comercial**: es la única fuente de verdad del dinero (Yappy no tiene
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
6. Revisión independiente (dinero): ver qué atacar abajo.

### Qué debería atacar un revisor independiente

- El **aviso**: repetirlo, desordenarlo (`R` tras `E`), mandarlo en paralelo desde dos procesos, firmarlo para otro dominio,
  cambiar una letra de la orden, mandar la orden con espacios o saltos, partes duplicadas (`status=E&status=R`).
- El **dominio y el hash**: los 16 dominios aceptados (¿alguno deja pasar uno ajeno?), la llave derivada (base64 raro, sin
  punto, con varios puntos, caracteres no UTF-8), la comparación en tiempo constante.
- Los **topes**: saltarlos con varias conexiones o varios pedidos; si la huella de la conexión se puede falsificar con
  `X-Forwarded-For` (el borde lo pisa con `CF-Connecting-IP`).
- `/payment/yappy/iniciar`: abrir el cobro de **otra persona** (la transacción tiene que ser la monitoreada en la sesión),
  un celular que no es de Panamá, un monto distinto, un `reference` ajeno.
- Los caminos de **revisión**: `E` sobre cobros cancelados, pedidos cambiados, pedido cancelado con cobro abierto, entorno cambiado.
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
