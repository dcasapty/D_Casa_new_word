# Tilopay: cobrar con tarjeta, Yappy y más desde la tienda

Módulo `addons/dcasa_pago_tilopay` (tarea #111). Este documento es la investigación, la auditoría de seguridad que pidió
la dueña, lo que hay que poner en Cloudflare y el guion para probar con dinero de mentiras. Se escribió **antes** de
programar y se pone al día al terminar.

> **En una frase:** el cliente paga en una página de Tilopay (nosotros nunca vemos una tarjeta); cuando vuelve, o cuando
> Tilopay avisa, **Odoo le pregunta a Tilopay de servidor a servidor** si ese pago existe, de cuánto fue, en qué moneda
> y si fue de verdad o de prueba. Solo con las cuatro respuestas correctas el pedido queda pagado. Lo que llegue por el
> navegador o por un aviso nunca decide nada por sí solo.

## 1. Estado y alcance

| Pieza | Estado |
|---|---|
| Pago del **pedido completo** de la tienda web (carrito y `/my/orders`) con Tilopay | Hecho (v1) |
| Abonos parciales de apartados con Tilopay | **No** (siguiente paso, §9) |
| Reembolsos desde Odoo hacia Tilopay | **No**: se hacen en el panel de Tilopay (§9) |
| Comisiones de Tilopay en la contabilidad | **No**: lo decide la contadora (§9). Aquí no hay ninguna cifra de comisión |
| Factura automática al pagar | **No** se enciende: es un acto fiscal que decide la dueña con la contadora (§9) |

## 2. Lo que se leyó (fuentes oficiales, leídas el 2026-11-19)

Todo salió de `tilopay.com/developers` y de su especificación OpenAPI 3.1 (`/developers/openapi.json`), que el propio
sitio declara «fuente de verdad del API». Cada página trae su fecha de última verificación (la anoto). `docs.tilopay.com`
responde 403 desde esta máquina (curl y WebFetch) y la búsqueda web no encontró nada más: lo que no está en la página
oficial se marca **NO VERIFICADO** y **no se adivina**.

- Guía general: <https://tilopay.com/developers> (2026-08-29) · caminos: <https://tilopay.com/developers/api/caminos-de-integracion> (2026-10-20)
- Página de pago alojada: <https://tilopay.com/developers/hosted-payment-page> (2026-08-28) y su operación
  <https://tilopay.com/developers/api/hosted-payment-page/process-payment> (2026-10-20)
- Autenticación: <https://tilopay.com/developers/api/autenticacion> (2026-10-20)
- Consulta: <https://tilopay.com/developers/api/procesos-operativos/consult> (2026-10-20) · modificación (captura, reembolso, reverso):
  <https://tilopay.com/developers/api/procesos-operativos/process-modification> (2026-10-22)
- Errores: <https://tilopay.com/developers/api/procesos-operativos/errors> (2026-10-22) · reintentos:
  <https://tilopay.com/developers/reintentos-seguros> (2026-10-20) · webhooks: <https://tilopay.com/developers/api/webhooks> (2026-10-20)
- Entornos: <https://tilopay.com/developers/entornos> (2026-10-21) · tarjetas de prueba: <https://tilopay.com/developers/tarjetas-de-prueba>
  (2026-10-21) · registro de desarrollador: <https://tilopay.com/developers/registro> (2026-08-29)
- Yappy en Tilopay: <https://tilopay.com/guias/pasarelas/guia-yappy> (2026-10-26) · SDK (solo para el dato de Yappy, 7 minutos):
  <https://tilopay.com/developers/sdk>
- Tarifas: <https://tilopay.com/tarifas> (2026-08-29). **Se leyó pero no se usa**: ni el código ni este documento llevan cifras de comisión.
- De terceros, **solo para entender el flujo, sin copiar nada**: el módulo «TILOPAY PAYMENT GATEWAY» de apps.odoo.com. Su ficha dice
  que se pegan la llave, el usuario y la contraseña **en el formulario del proveedor** (o sea, en la base de datos) y que usa el SDK en
  la página del comercio. Las dos cosas son justo lo que aquí se evita.

### 2.1 Respuestas a las preguntas del encargo

| | Pregunta | Respuesta | Estado |
|---|---|---|---|
| a | Modos de integración | Cuatro: sin código (plugins), **página de pago alojada** (el servidor pide una URL y redirige), SDK JavaScript (los campos de tarjeta viven en nuestra página) y servidor a servidor (solo comercios con certificación PCI). **Elegido: la página alojada**: el cliente teclea la tarjeta en `secure.tilopay.com`; «vos nunca ves un número de tarjeta» (SAQ-A en lo normal; el alcance exacto lo confirma quien lleve el cumplimiento) | VERIFICADO |
| b | Autenticación | `POST https://app.tilopay.com/api/v1/login` con `{"apiuser", "password"}` → `access_token`, `token_type` («bearer»), `expires_in` (entero en segundos; 24 h). Luego `Authorization: bearer <token>`. Los tokens **no se pueden revocar** y no hay tope de tokens a la vez. La **llave** (`key`) va en el cuerpo de `processPayment` y `consult`. Las tres salen del panel «Integración con plataformas» | VERIFICADO |
| b' | URL de pruebas y de producción | **No hay.** Un solo host (`app.tilopay.com`) y **las mismas credenciales** en los dos modos. El modo (pruebas/real) se cambia **con un interruptor en el panel de Tilopay**, no desde el código | VERIFICADO |
| c | Crear el pago | `POST /api/v1/processPayment` → `{"type":"100","url":"https://secure.tilopay.com/htmls/…"}`. Campos: `redirect`, `key`, `amount` (texto, p. ej. `"1.00"`), `currency` (ISO: `USD`), `orderNumber`, `capture` (`"1"`), `billTo*` (nombre, apellidos, dirección, dirección 2, ciudad, estado, código postal, país ISO-2, teléfono, correo: **todos marcados obligatorios**), `shipTo*` (opcionales), `subscription` (`"0"`), `platform`, `returnData` (opcional, vuelve igual), `hashVersion`, `token_version` (`"v2"`). **`orderNumber` es único para siempre**: repetirlo da «Transacción duplicada». No hay campo para elegir el método de pago: el cliente lo elige en la página de Tilopay entre los que la cuenta tenga activos | VERIFICADO |
| d1 | Retorno del cliente | Redirección **GET** a `redirect` con `code` (`1` = aprobada), `description`, `auth`, `order`, `tpt` y `tilopay-transaction` (id), `crd`, `OrderHash`, `returnData`, `form_update`. El ejemplo oficial muestra `order=TPYS-…`, distinto del `orderNumber` de ese ejemplo: **no se confía en que `order` sea el nuestro** (ver §5) | VERIFICADO (el valor exacto de `order`: NO VERIFICADO) |
| d2 | Firma del retorno (`OrderHash`) | Su **algoritmo no es público**: «se solicita abriendo un caso en Soporte». Es «la única verificación de origen disponible» | VERIFICADO que no es público. **No se puede verificar la firma** hasta que Tilopay la entregue por escrito |
| d3 | Webhook de compras | Existe para `processPayment`, pero **«su especificación técnica te la entregamos cuando la solicitás»** (Soporte). Formato JSON; las compras tienen **1 solo intento** (sin reintentos) y se da por entregado con HTTP 200. No dicen desde qué IP vienen ni cómo se registra la URL | Existencia: VERIFICADO. Campos, firma, IP y registro: **NO VERIFICADO** |
| e | Consulta de una transacción | `POST /api/v1/consult` con `{"key","orderNumber"}` → `{"type":"200","response":[{id_tilopay, orderNumber, amount (texto), currency, code ("1" = aprobada), response (texto), auth, environment ("Test" en el ejemplo), type ("Payment"), capture ("Capture"), date, …}]}`. Devuelve **una lista** (puede haber varias filas por orden). La advertencia oficial: un HTTP 200 **no** significa éxito, hay cinco envolturas de error: se mira siempre el cuerpo. «Antes de entregar el producto … confirmá el estado … con `consult`» | VERIFICADO (valores exactos de `environment` en producción, `type` de un reembolso, `capture`: NO VERIFICADO) |
| f | Reembolsos y anulaciones | `POST /api/v1/processModification` con `orderNumber`, `type` (1 captura, 2 reembolso, 3 reverso), `amount`, `key`; `ReasonCode 1101` = aprobado. No se usa en la v1 | VERIFICADO |
| g | Métodos de pago | Los que la cuenta tenga **activados en el panel** de Tilopay (interruptor por método): tarjetas Visa/Mastercard/Amex, **Yappy** (solo Panamá), Tafi, Crediviva, Tasa Cero BAC… La documentación pública no dice con todas las letras que la página alojada muestre Yappy: se comprueba en la prueba (§7) | Panel: VERIFICADO. Que la página alojada ofrezca cada uno: NO VERIFICADO |
| h | Probar sin dinero | Interruptor «Modo Prueba» del panel + 27 tarjetas de prueba (`4111111111111111` aprobada sin fricción; `4012000000020071` aprobada con 3DS; `4112613451591116` fondos insuficientes; `4111111111119999` rechazada…). Vencimiento futuro cualquiera, CVV cualquiera, código 3DS `3ds2`. **No hay credenciales de pruebas compartidas**: cada desarrollador se registra y recibe las suyas (cuenta de pruebas aparte). El modo de prueba solo vale para pagos de contado | VERIFICADO |
| i | Límites, expiración, reintentos | Yappy: sin respuesta en **7 minutos** queda «Transacción expirada». El API de compras **no es idempotente**: ante un timeout no existe reintento seguro; se consulta antes de reintentar. Tope de monto, vigencia de la URL de pago y límites de llamadas del API de adquirencia: **no están publicados** | Lo dicho: VERIFICADO. El resto: NO VERIFICADO |

## 3. Lo que cambió el diseño (hallazgos)

1. **Mismas credenciales en pruebas y producción** y un solo host. El modo lo manda el interruptor del panel de Tilopay.
   Consecuencia: si el Worker de **staging** usara las credenciales de la cuenta real y alguien dejara la cuenta en modo real,
   una prueba cobraría dinero de verdad. Por eso: **staging usa una cuenta de pruebas de desarrollador**
   (<https://tilopay.com/developers/registro>), con sus propias tres claves, que **nunca** son las de la cuenta real.
2. **El servidor tiene que saber si el pago que le confirman fue de prueba o real**: `consult` trae `environment`. Se compara con
   lo que el Worker declara (`TILOPAY_ENTORNO`). Un pago «de prueba» **jamás** marca pagado un pedido en producción, y un pago
   real **jamás** se acepta en un entorno declarado de prueba.
3. **No hay forma de verificar la firma** (`OrderHash`) ni de saber de qué IPs viene el aviso. Entonces la firma no es la defensa:
   **lo es la consulta de servidor a servidor** (Tilopay lo recomienda así: «confirmá el estado contra el API»). El código deja el
   hueco listo (§5.4) para cuando llegue el algoritmo.
4. **El aviso de compras no se reintenta**: si se pierde, nadie lo vuelve a mandar, y el cliente puede cerrar la pestaña después de
   pagar. Por eso hay una tarea programada que **pregunta sola** por los pagos que quedaron sin confirmar.
5. **El API no es idempotente**, pero `processPayment` solo **crea la dirección** de la página (no cobra). Si esa llamada se cae,
   el cliente nunca vio una página de pago: se le avisa y se crea otra con otro `orderNumber`; no hay riesgo de cobrar dos veces.
6. **El portal de Odoo (`/my/orders/<id>/transaction`) acepta el monto que manda el navegador** (la tienda sí lo compara con el
   pedido; el portal no: así funciona el anticipo de Odoo). Para Tilopay v1 eso no vale: antes de abrir la página de pago se
   exige, **en el servidor**, que el monto sea exactamente el total del pedido y que el pedido no tenga pagos previos. Hay
   prueba (`test_el_monto_del_navegador_no_manda` y su gemela por HTTP).
7. **En una base nueva el plan contable se carga al final y borra los diarios que ya existían**: el diario «Tilopay» se crea
   después de ese plan y, si faltara, al encender el proveedor. Sin esto el cobro caía en el primer banco que hubiera.
8. **El proveedor solo lo enciende quien tiene «Ajustes técnicos» (hoy, el administrador, que además es Gerencia).** El modelo de
   proveedores de pago de Odoo solo lo lee y escribe ese grupo. Dejar que un Gerencia sin Ajustes técnicos lo encienda pide un
   permiso nuevo y un camino con `sudo()` dentro de un módulo de dinero: no se hizo en esta versión (§9). «Probar conexión»
   sí queda para Gerencia y administradores.
9. **Los textos de `state_message` los ve el cliente** (la página «Estado del pago» de Odoo los imprime): son amables, en español
   y sin datos internos. Lo técnico va a los registros (sin secretos) y a la nota del pedido (solo equipo).
10. **Odoo solo filtra los proveedores por «Publicado» al MOSTRARLOS**, no al crear la transacción: quien manda a mano el número
    del proveedor a `/my/orders/<id>/transaction` abre la página aunque nunca se le haya ofrecido. En «Modo de prueba» y sin
    publicar eso era pagar un pedido real con la tarjeta de prueba pública. Ahora el propio proveedor lo exige: **sin publicar,
    solo lo abre una persona del equipo con sesión** (la misma regla que Odoo aplica al mostrarlo).
11. **El total del pedido puede cambiar después de abrir la página de pago.** Con la transacción en «borrador» el carrito sigue
    editable (otra pestaña, o la vendedora) y, como el pago en línea no es obligatorio en esta base, Odoo confirma el pedido con
    cualquier transacción hecha. Por eso, antes de dar un pago por bueno se compara lo cobrado con lo que **vale el pedido
    ahora** (no con lo que valía al abrir). Si no coinciden NO se paga solo: el dinero entró, la transacción queda en error con un
    mensaje para el cliente y Gerencia recibe una **nota y una actividad** en el pedido (cobrado X, el pedido ahora vale Y).
    Hay una segunda comprobación justo antes de confirmar el pedido (otra vez, por si cambió entre medias).
12. **«Probar conexión» no comprueba la llave.** Solo abre sesión con usuario y contraseña; la llave se usa en el primer cobro.
    Tilopay no publica qué contesta a una llave mala (ni en `consult` ni en `processPayment`), y esta capa no inventa respuestas
    de Tilopay: la pantalla lo dice con todas las letras («la llave se comprueba en el primer cobro de prueba») y el campo se llama
    «Claves cargadas», no «Conectado».
13. **`TILOPAY_ENTORNO=produccion` solo vale en el servidor de producción** (`DCASA_ENTORNO=produccion`, que el Worker fija solo
    en `dcasa`): la misma regla de correos y de Meta. En staging o en una copia local, aunque alguien pegue «produccion», Tilopay
    solo cobra en prueba.
14. **Cada llamada a Tilopay retiene una conexión de la base** hasta 15 s si Tilopay está lento, y con `workers = 0` el grupo de
    conexiones (48) es de **toda** la tienda: un visitante que martillaba `/payment/tilopay/return?order=…` con sus propias
    órdenes podía agotarlo y dejar la tienda entera en error 500 (reproducido: §10). Se frena en capas: un **tope global de 6
    llamadas a Tilopay a la vez** (más 2 de reserva para la tarea programada; si está lleno, la consulta responde «saturada»
    al instante y no espera), las rutas web **solo consultan transacciones recientes** (3 h; lo viejo lo atiende la tarea,
    que pregunta primero por lo que recibió un retorno o un aviso), y un **freno de 120 peticiones por minuto por conexión** en el
    retorno y el aviso (la misma llave de conexión que «Busca con una foto»; el borde pone `X-Forwarded-For` con la IP real de
    Cloudflare, no la del visitante). El tope de llamadas también cubre abrir la página de pago.
15. **Un estado que el código no entiende no pasa en silencio.** Un `code` que no es numérico (o un estado intermedio de Yappy)
    deja la transacción pendiente; si sigue así pasada una hora, o al vencer a las 24 horas, Gerencia recibe una nota y una
    actividad (una sola por transacción): si ese estado resultara ser un pago aprobado, el dinero entró y nadie lo sabría.
16. **Un cobro que no cuadra con el pedido no se paga solo, nunca.** Después de «cobrado X, el pedido ahora vale Y» la
    transacción queda marcada para una persona (`dcasa_tilopay_revision`): aunque el pedido vuelva a valer lo cobrado, ni una
    consulta posterior ni la tarea la dan por pagada (el equipo pudo haber devuelto el cobro en el panel de Tilopay y que
    `consult` no lo muestre como fila aparte). Se resuelve a mano: devolver el cobro, o quedarse con él, ajustar el pedido y
    registrarlo como pago en el diario Tilopay.

## 4. Modelo de amenazas

| Qué podría intentar un atacante | Qué lo frena |
|---|---|
| Leer la llave, el usuario o la contraseña | Solo existen como **secretos del Worker de Cloudflare** y en el entorno del contenedor. No están en el repositorio, en GitHub, en la base, en un campo de pantalla, en un log ni en una respuesta. La pantalla del proveedor muestra solo «Claves cargadas: sí/no» y «Entorno». El token de Tilopay vive únicamente en la memoria del proceso. Una prueba comprueba con `assertLogs` que ningún registro trae claves ni tokens |
| Fingir un pago: abrir `/payment/tilopay/return?code=1&order=…` a mano | El `code` del navegador **no se usa**. Se busca la transacción por su número de orden, y se **consulta a Tilopay**: debe existir una fila aprobada de esa orden |
| Fingir el aviso: POST a `/payment/tilopay/webhook` con un cuerpo falso | Igual: el cuerpo solo sirve para saber **qué orden revisar**; la decisión sale de la consulta. Un cuerpo inventado no cambia nada |
| Pagar poco y que cuente por mucho (monto distinto) | El monto y la moneda salen **siempre** del pedido en el servidor (USD, 2 decimales, con ITBMS incluido). Si lo que Tilopay dice haber cobrado no es **exactamente** eso, el pago no se acepta y la transacción queda en error con aviso al equipo |
| Pagar con la orden de otro (referencia de otra transacción, otro proveedor u otra empresa) | La búsqueda es por la orden **que guardamos nosotros** (`dcasa_tilopay_orden`, única, aleatoria), filtrada por proveedor `tilopay`; la consulta se hace con **nuestra** orden guardada, nunca con la del navegador; la respuesta debe traer esa misma orden |
| Usar un pago de prueba en producción (o al revés) | Se compara `environment` de la respuesta con `TILOPAY_ENTORNO`; además, el proveedor solo se ofrece si el interruptor de Odoo (Habilitado/Modo de prueba) **coincide** con ese entorno |
| Repetir un aviso viejo (replay) o repetirlo muchas veces | Es idempotente: una transacción ya pagada no se vuelve a procesar ni duplica el cobro, el asiento ni los puntos. Cada transacción se consulta como mucho **una vez cada 5 segundos**, así que repetir no gasta llamadas a Tilopay |
| Tumbar TODA la tienda martillando el retorno con órdenes propias mientras Tilopay está lento (cada consulta retiene una conexión de la base) | Tope global de 6 llamadas a Tilopay a la vez (sin esperar: lo que sobra responde «saturada»), solo lo reciente se consulta desde la web, freno de 120 por minuto por conexión (§3, punto 14). La tarea programada tiene 2 lugares de reserva y presupuesto de 40 s |
| Mandar miles de avisos para gastar llamadas al API de Tilopay | **Nada se consulta antes de validar**: tamaño del cuerpo (tope 16 KB), forma de la orden (letras, números y guion, tope de largo), y que **exista** una transacción de Tilopay pendiente con esa orden (búsqueda por igualdad, sin SQL armado con texto). Orden inventada = no pasa nada y **no** se llama a Tilopay |
| Averiguar qué órdenes existen (enumerar) | La ruta contesta **lo mismo** exista o no (el aviso: `200 {"estado":"ok"}`; el retorno: la misma redirección a `/payment/status`). Sin trazas de error hacia afuera |
| Crear cientos de intentos de pago para saturar a Tilopay (cada página es una llamada a `processPayment` en la cuenta) | Máximo 5 intentos sin terminar por pedido en 15 minutos, **y un tope global de 300 páginas por hora** (`TOPE_PAGINAS_POR_HORA`; la tienda vende muy por debajo). Una sola conexión se topa antes, con **30 páginas por hora** (`TOPE_PAGINAS_POR_CONEXION_HORA`, por huella HMAC de la conexión, no la dirección; no cuenta al equipo), y el global no cuenta las páginas que ya se pagaron. Pasado el tope el cliente ve «Hay muchos pagos en curso…» y se le ofrece otra forma de pago. Además el borde limita los POST de `/shop/payment` por IP |
| Dejar sin servicio la tarea que rescata pagos con una ráfaga de intentos basura | La tarea pregunta primero por lo que recibió un retorno o un aviso (**señal de vida**), y luego por `coalesce(última consulta, creación)`: lo que lleva más tiempo esperando va primero y lo nuevo no se cuela. Lo reciente se pregunta cada 8 minutos; lo viejo cada hora si Tilopay ya tiene una fila de esa orden y cada 3 horas si nunca vio nada; lo rechazado o cancelado cada 3 horas; **lo que Tilopay nunca vio deja de preguntarse al día** (si luego llega un retorno o un aviso, vuelve a preguntarse). Trabaja por lotes hasta gastar 40 segundos; si Tilopay no contesta 3 veces seguidas, para |
| «Publicado» + «Modo de prueba» por error en el servidor de PRODUCCIÓN (cualquier visitante pagaría con la tarjeta de prueba pública) | En el servidor de producción (`DCASA_ENTORNO=produccion`) el «Modo de prueba» solo lo abre una persona del equipo, aunque esté publicado |
| Abrir a mano el proveedor de pruebas sin publicar (mandar `provider_id` a `/my/orders/…/transaction`) y pagar un pedido real con la tarjeta de prueba | Un proveedor sin publicar solo lo abre una persona del equipo con sesión (§3, punto 10). Aunque lo hiciera ella, el pedido queda con una nota «Pagado con una tarjeta de PRUEBA» |
| Cambiar el pedido mientras el cliente paga (pagar 107 y quedarse con un pedido de 535, o al revés) | Se compara lo cobrado con el total **actual** del pedido antes de dar el pago por bueno y otra vez antes de confirmarlo (§3, punto 11); si no coinciden, no se paga solo y Gerencia recibe nota y actividad |
| Pagar un pedido que ya se canceló | No se abre la página para un pedido cancelado; si se cancela mientras el cliente paga, el dinero entra y Gerencia recibe nota y actividad para devolverlo o reabrir el pedido |
| Tumbar la tienda haciendo caer a Tilopay | Timeout corto (10 s). Una falla de red o de Tilopay deja la transacción **pendiente** (nunca «pagada») y nunca tumba la venta ni el arranque. Los pendientes se vuelven a preguntar solos |
| Dos avisos a la vez sobre el mismo pago | Se bloquea la fila de la transacción (`FOR UPDATE SKIP LOCKED`): la segunda espera su turno o se salta |
| Cambiar de modo (prueba ↔ real) con pagos a medias para mezclarlos | La transacción recuerda el modo en que se creó (`is_live`): un pago aprobado solo vale si el modo que dice Tilopay es el mismo |
| Meter HTML o texto raro en las notas del pedido a través de un texto de Tilopay | Todo texto ajeno se limpia (largo, saltos, claves) y la nota se escapa (nunca es HTML) |
| Pagar $1 por un pedido grande a través del portal (que acepta el monto del navegador) | Tilopay exige en el servidor el total exacto del pedido (§3, punto 6) |
| Que un error de programación acepte datos del navegador como si fueran de Tilopay | `_apply_updates` **solo** acepta un objeto de la clase privada `DatosVerificados`, que se crea únicamente después de la consulta. Los parámetros del navegador son texto: no pueden ser esa clase |
| Robar datos de tarjeta | Jamás tocan nuestro servidor (página alojada por Tilopay). A Tilopay solo se le mandan los datos que el pedido ya tiene y que su documentación pide (nombre, dirección, teléfono, correo) |
| Los registros de acceso de Odoo guardan secretos que viajen en la URL | Nada secreto viaja en la URL. (Se descartó poner un secreto en la ruta del aviso porque Odoo registra la ruta de cada visita) |
| Que se cobre sin querer en pruebas | El proveedor **nace apagado**. Para ofrecerse hacen falta **tres llaves**: credenciales cargadas en Cloudflare, `TILOPAY_ENTORNO` coherente con el interruptor de Odoo y que **Gerencia lo active** |

**Lo que este diseño NO puede cubrir sin información de Tilopay** (queda en §8): comprobar la firma `OrderHash`, saber
las IP de origen del aviso, y los campos exactos del aviso. Mientras tanto la consulta de servidor a servidor es suficiente
para no pagar nada falso, y la tarea programada suple al aviso si no llega.

## 5. Cómo funciona

### 5.1 El camino feliz

1. El cliente elige **«Tarjeta, Yappy y más (Tilopay)»** (solo sale si Tilopay está activo, con las claves cargadas y coherente).
2. Odoo crea la transacción (monto y moneda del **pedido**, no del navegador) y le da un `orderNumber` propio:
   `<referencia>-<8 letras y números al azar>`. Se guarda en `dcasa_tilopay_orden` **antes** de llamar a Tilopay.
3. Odoo llama a `login` (token en memoria, se renueva solo) y a `processPayment`; Tilopay devuelve la dirección de su página.
4. Odoo manda al cliente a esa dirección. Allí elige el método (tarjeta, Yappy…) y paga.
5. Tilopay lo devuelve a `https://dcasapty.com/payment/tilopay/return` y, aparte, avisa a la ruta del aviso.
6. **Cualquiera de esas llegadas, o la tarea programada, o la página «Estado del pago» mientras espera, hace lo mismo:** busca
   la transacción por su orden, la bloquea, **consulta a Tilopay** y compara orden, **monto, moneda, aprobación (`code = 1`) y
   entorno**, y además que el **pedido siga valiendo lo cobrado**. Si todo coincide: `_set_done()`. Si algo no coincide: no se
   paga y se anota por qué.
7. `_set_done()` dispara el flujo normal de Odoo, el mismo que cualquier pago en línea: confirma el pedido (reserva el
   inventario), registra el cobro **en el diario «Tilopay»** y, cuando se factura y se publica la factura, Odoo la cruza sola
   con ese cobro; al quedar pagada la factura completa, Socios da sus puntos (solo con la compra completa).

### 5.2 Decisiones

- **Una sola opción de pago en la tienda** («Tarjeta, Yappy y más (Tilopay)»), porque el API no deja elegir el método: lo escoge
  el cliente en la página de Tilopay. Qué métodos aparecen se maneja en el panel de Tilopay (§6.4).
- **`orderNumber` propio, aleatorio y único**: Tilopay lo exige único para siempre, y así la orden de staging no choca con la de
  producción ni se puede adivinar contando.
- **Un rechazo no es el final.** El cliente puede reintentar en la misma página de Tilopay con otra tarjeta. Por eso **una consulta
  posterior que muestre un pago aprobado la pasa a pagada** (`error`, `cancel` o `draft` → `done`). Esa consulta posterior existe:
  la tarea programada pregunta por lo rechazado o cancelado de los últimos 3 días (cada 3 horas) y la página «Estado del pago»
  también pregunta mientras la transacción esté en `error`. A las 24 horas sin pago, lo que sigue sin confirmar se marca vencido.
- **Un estado que no es un rechazo claro no se da por rechazado.** Un rechazo del emisor trae un código **numérico** distinto de
  «1». Cualquier otra cosa (vacío, texto, un estado intermedio como el de un Yappy que aún no responde) queda **pendiente**, sin
  error, y la tarea vuelve a preguntar (§8, punto 11). Pasada una hora, o al vencer, deja nota y actividad para Gerencia.
- **Quién pregunta y cuándo.** El retorno del cliente, el aviso y el reloj de «Estado del pago» consultan solo transacciones de las
  últimas 3 horas; si llega uno de una más vieja, solo dejan la **señal de vida** y la tarea programada la atiende primero en su
  siguiente vuelta (cada 10 minutos). Si ya hay 6 llamadas a Tilopay en curso, la consulta se salta («saturada») sin gastar el
  turno de 5 segundos de esa transacción.
- **Presupuesto de la tarea: 40 segundos por vuelta** (antes 100). La tarea comparte el único hilo de tareas (`max_cron_threads = 1`)
  con otras, entre ellas la que termina los pagos de Odoo (`payment.cron_post_process_payment_tx`): 100 s más una consulta de
  15 s la retrasaban. Con ~0,5 s por consulta alcanza para ~80 preguntas por vuelta.
- **Los montos de $1,000 o más** pueden llegar como «1,250.00». Se acepta esa forma (coma de miles y siempre dos decimales) y la
  normal («1250.00»); cualquier otra forma rara no paga (queda como «monto distinto» con aviso al equipo). El monto que mandamos a
  Tilopay va siempre sin coma.
- **El diario «Tilopay»** (tipo banco, código `TLP`) se crea al instalar. Así, «Cobrado por forma de pago» y la Caja ven «Tilopay».
- **No se enciende la factura automática** (`sale.automatic_invoice`): cambia lo que pasa con todos los proveedores y emite
  documentos fiscales. Queda como decisión de la dueña (§9).
- **Solo pedidos de venta** en la v1: el proveedor no se ofrece para facturas sueltas ni para montos parciales.

### 5.3 Qué hace el código con cada caso raro

| Caso | Resultado |
|---|---|
| Retorno y aviso en cualquier orden, o repetidos | Una sola confirmación; los demás ven «ya pagada» y no hacen nada |
| Tilopay dice aprobado pero el monto o la moneda no son los del pedido | Error con mensaje para el equipo; **no** se paga |
| Tilopay dice aprobado pero en otro entorno (prueba vs real) | Se queda pendiente, se anota en el pedido y en el registro (sin secretos); **no** se paga |
| `consult` no trae esa orden | Sigue pendiente (puede que Tilopay tarde) |
| Varias filas aprobadas de la misma orden, o una fila de reembolso/reverso | No se paga automáticamente: el equipo lo revisa en el panel de Tilopay |
| Tilopay caído, lento o con respuesta rara | Pendiente; se reintenta con la tarea programada. Nunca «pagada» |
| El cliente abre dos páginas de pago y paga las dos | Los dos pagos son dinero real y los dos se aceptan; el pedido lleva una nota para el equipo: hay que devolverle uno desde el panel de Tilopay |
| Transacción ya cancelada o vencida y llega un pago aprobado y correcto | Se acepta (hay dinero real); queda anotado |
| El pedido cambió de total mientras el cliente pagaba | Error para esa transacción con un mensaje al cliente («Tu pedido cambió mientras pagabas…»); **no** se confirma el pedido; Gerencia recibe nota y actividad «cobrado X, el pedido ahora vale Y» (el dinero entró). Si el total vuelve a valer lo cobrado, una consulta posterior sí lo da por pagado |
| Llega un pago aprobado de un pedido que ya está cancelado | El cobro entra; el pedido sigue cancelado; Gerencia recibe nota y actividad para devolverlo o reabrir el pedido |
| El pago fue de prueba (`is_live` falso) y el pedido se confirmó | El pedido lleva la nota «Pagado con una tarjeta de PRUEBA…» (quien prepara la entrega lo ve) |
| El pedido pagado era un «apartado por página web» | Al confirmarse pagado completo deja de ser apartado (sin fecha de vencimiento) |
| Un código de estado raro o intermedio en `consult` | Pendiente, sin error ni nota; se vuelve a preguntar |
| Retorno o aviso de una transacción de más de 3 horas | No se consulta desde la web: queda la señal de vida y la tarea la atiende primero en su siguiente vuelta |
| Ya hay 6 llamadas a Tilopay en curso | La consulta responde «saturada» al instante (la tarea o el siguiente reloj la atienden); abrir una página de pago dice «Hay muchos pagos en curso…» |
| Una conexión manda más de 120 peticiones por minuto al retorno o al aviso | Lo de más no se procesa; la respuesta es la de siempre |
| Un cobro marcado para revisión (el pedido cambió) y el pedido vuelve a valer lo cobrado | NO se paga solo; la tarea ya no la pregunta; una persona la resuelve (§3, punto 16) |
| Orden desconocida, de otro proveedor, de otra empresa | No pasa nada y la respuesta es idéntica |
| Credenciales ausentes | Tilopay **no aparece** en la tienda; Odoo y el sitio siguen normales; el arranque no se entera |
| Proveedor apagado | Nada cambia: ni se ofrece ni responde a avisos con datos |

### 5.4 El hueco para la firma

`models/tilopay_api.py` tiene `verificar_hash(...)`, que **hoy no se usa** y devuelve «no verificable». Cuando Tilopay entregue el
algoritmo de `OrderHash` por escrito (§8) se programa ahí, con `hmac.compare_digest`, y se suma como una comprobación **más**
(nunca en lugar de la consulta).

## 6. Qué poner en Cloudflare

Los datos de acceso se pegan **solo** en el panel de Cloudflare de cada Worker, no en GitHub, no en Odoo y no por el chat.
Los despliegues usan `--keep-vars` y no tocan lo que se pegó en el panel.

### 6.1 La tabla (sin valores)

| Nombre (tal cual, en mayúsculas) | Tipo en Cloudflare | Worker `dcasa` (producción) | Worker `dcasa-staging` | Qué dato es | Para qué sirve |
|---|---|---|---|---|---|
| `TILOPAY_API_KEY` | **Secreto** | La **«Llave API»** de la cuenta **real** | La «Llave API» de la **cuenta de pruebas** de desarrollador | Panel de Tilopay › Integración con plataformas | Identifica el comercio en cada cobro y consulta |
| `TILOPAY_API_USER` | **Secreto** | El **«Usuario API»** de la cuenta real | El «Usuario API» de la cuenta de pruebas | Mismo panel | Abre sesión en la API |
| `TILOPAY_API_PASSWORD` | **Secreto** | La **«Contraseña API»** de la cuenta real | La «Contraseña API» de la cuenta de pruebas | Mismo panel | Abre sesión en la API |
| `TILOPAY_ENTORNO` | **Variable normal** (Texto) | `prueba` mientras se hacen las pruebas finales y **`produccion` solo cuando todo salió bien** | **No hace falta pegarla:** ya viene fijada en `prueba` en el código (`edge/wrangler.jsonc`) y un despliegue siempre la deja así | No es un dato de Tilopay: es lo que **tú dices que esperas** | Dice a Odoo si debe aceptar pagos de prueba o reales. Sin ella, Odoo asume `prueba` (lo seguro). `produccion` solo se obedece en el servidor de producción (`DCASA_ENTORNO=produccion`, que el Worker `dcasa` ya trae) |

Reglas:

- Los tres primeros son **secretos** (al guardarlos Cloudflare ya no deja volver a verlos). `TILOPAY_ENTORNO` no es secreto.
- **Staging nunca lleva las claves de la cuenta real.** Va con la cuenta de pruebas (registro en
  <https://tilopay.com/developers/registro>).
- Si falta cualquiera de los tres, Tilopay **no aparece** en la tienda y nada más se afecta.
- Las claves son las **mismas en prueba y en real**: lo que cambia es el interruptor «Modo Prueba» del panel de Tilopay y,
  del lado nuestro, `TILOPAY_ENTORNO`. Los dos tienen que decir lo mismo.

### 6.2 Pasos en el panel de Cloudflare (uno por uno)

1. Entra a <https://dash.cloudflare.com> y elige la cuenta de D'CASA.
2. En el menú de la izquierda: **Workers y Pages** (*Workers & Pages*).
3. Abre el Worker **`dcasa-staging`** (primero el de pruebas).
4. Pestaña **Configuración** (*Settings*) › sección **Variables y secretos** (*Variables and Secrets*) › botón **+ Agregar** (*Add*).
5. Tipo: **Secreto** · Nombre: `TILOPAY_API_KEY` · Valor: la «Llave API» **de la cuenta de pruebas**. Guardar.
6. Repite el paso 5 para `TILOPAY_API_USER` («Usuario API») y `TILOPAY_API_PASSWORD` («Contraseña API»).
7. Staging **no necesita** `TILOPAY_ENTORNO`: ya viene fijada en `prueba` en el código. (En producción sí se pega, en el paso 10.)
8. Pulsa **Implementar** (*Deploy*) si Cloudflare te lo pide. **Los cambios llegan a Odoo al reiniciar o en el siguiente despliegue**:
   avisa y se reinicia/despliega.
9. En Odoo de staging: *Facturación › Configuración › Proveedores de pago › Tilopay*. Debe decir «Claves cargadas: Sí» y
   «Entorno: Prueba». Pulsa **Probar conexión**: te dice si Tilopay aceptó el usuario y la contraseña, y avisa que la «Llave API» no
   se puede comprobar ahí (se comprueba en el primer cobro de prueba). (Hoy el dominio `staging.dcasapty.com` aún no apunta al Worker de staging, ver
   `edge/wrangler.jsonc`: el cliente de prueba no podrá volver a la tienda después de pagar; la confirmación llega igual por la
   tarea programada, hasta 10 minutos. Para ver el retorno completo hay que apuntar ese dominio primero.)
10. Para producción, mismo camino en el Worker **`dcasa`** con las claves de la cuenta **real**; además **+ Agregar** › Tipo: **Texto** ›
    Nombre: `TILOPAY_ENTORNO` › Valor: `prueba` (sin esta variable Odoo también asume `prueba`, pero queda escrito). Cuando las pruebas del §7 pasen **también en producción**, cambia `TILOPAY_ENTORNO` a `produccion`, apaga «Modo
    Prueba» en el panel de Tilopay y en Odoo cambia el proveedor a **Habilitado**.

### 6.3 Qué se registra en el panel de Tilopay (con el dominio `dcasapty.com`)

| Qué | Dirección | Dónde |
|---|---|---|
| **Retorno del cliente** (`redirect`) | `https://dcasapty.com/payment/tilopay/return` | **No se registra:** Odoo la manda dentro de cada pago |
| **Notificación del servidor (webhook)** | `https://dcasapty.com/payment/tilopay/webhook` | **Hay que pedirle a Tilopay (Soporte) que la registre**: el API público no tiene un campo para ella (§8). Staging: la misma ruta con el dominio de staging |

Sin el aviso el sistema funciona igual (retorno + tarea programada que pregunta sola); el aviso solo lo hace más rápido.

### 6.4 Qué métodos dejar activos en el panel de Tilopay

En **Métodos de Pago** del panel: **activa solo lo que D'CASA quiere ofrecer** y apaga el resto, porque la página de pago muestra
lo que esté activo. Propuesta: **tarjetas Visa y Mastercard** y **Yappy**. (Amex, Tafi, Crediviva y Tasa Cero BAC: solo si la
dueña y la contadora quieren ofrecerlos y entienden sus costos). Yappy exige agregarlo en «+ Agregar Método de Pago» y **activarlo**.
Las comisiones de cada método están en <https://tilopay.com/tarifas>: no se copian aquí; la contadora las toma de la fuente.

## 7. Guion de prueba (sandbox, con dinero de mentiras)

Se hace **en staging** con la **cuenta de pruebas de desarrollador**, o en producción con `TILOPAY_ENTORNO=prueba` y el «Modo
Prueba» **encendido** en el panel. Nunca con una tarjeta real. **En producción, solo con el proveedor «sin publicar» y con
personas del equipo con sesión iniciada**: un visitante no puede abrirlo (§3, punto 10), y el pedido que se pague así queda
**confirmado de verdad** (reserva inventario) con la nota «Pagado con una tarjeta de PRUEBA»: **anúlalo al terminar**.

0. Panel de Tilopay: «Modo Prueba» **encendido** (aparece un aviso arriba en todo el panel). Métodos de pago activos: tarjeta y Yappy.
1. Cloudflare (§6.2) con las claves de pruebas y `TILOPAY_ENTORNO=prueba`; reiniciar.
2. Odoo › *Facturación › Configuración › Proveedores de pago › Tilopay*: «Claves cargadas: Sí», «Entorno: Prueba». **Probar
   conexión**: debe decir que Tilopay aceptó el usuario y la contraseña (y que la llave se comprueba en el primer cobro: ése es
   el paso 4). Cambiar el estado a **Modo de prueba** y guardar. En modo de prueba Tilopay solo lo ve **y lo puede abrir** el
   equipo que tiene sesión (entra con tu usuario de administrador para probar). **En staging**, si quieres que también lo vea
   un visitante, pulsa **Publicado**. **En producción no pulses «Publicado» hasta el final**: así los clientes no ven una
   opción de pruebas y nadie puede abrirla a mano.
3. En la tienda: agrega un mueble barato, ve a pagar. Debe salir **«Tarjeta, Yappy y más (Tilopay)»**. Con Tilopay apagado en Odoo no debe salir.
4. **Pago aprobado:** elige Tilopay. Se abre la página de Tilopay. Tarjeta `4111111111111111`, vencimiento futuro, CVV cualquiera.
   Debe volver a la tienda y mostrar «¡Pago recibido!» y el pedido **confirmado**. En Odoo: la transacción en **Confirmado**, un cobro
   en el diario **Tilopay**, el pedido en «Pedido de venta». Anota qué trae `order` en la dirección de retorno.
5. **3DS:** tarjeta `4012000000020071`; en el desafío escribe `3ds2`. Debe quedar pagado igual.
6. **Fondos insuficientes:** `4112613451591116` (con desafío `3ds2`). No debe quedar pagado; el cliente ve un mensaje amable y puede reintentar.
7. **Rechazada:** `4111111111119999`. Igual: sin pago.
8. **Reintento en la misma página:** rechazada y luego aprobada con otra tarjeta, sin cerrar la página. Debe quedar **pagado** (la
   transacción pasa de error a confirmado).
9. **Cerrar la pestaña después de pagar** (sin volver a la tienda): en pocos minutos la tarea programada debe dejar el pedido pagado
   (o el aviso, si Tilopay ya lo registró).
10. **Yappy** (si está activo): elige Yappy en la página de Tilopay y completa la prueba. Mira si queda pagado. Sin respuesta en 7 min, expira.
11. **Mirar el entorno:** abre el pedido pagado y la transacción: debe decir que Tilopay respondió «prueba». Cambia `TILOPAY_ENTORNO` a
    `produccion` (con el «Modo Prueba» aún encendido): un pago nuevo **no debe** quedar pagado (se anota que Tilopay respondió «prueba»).
    Vuelve a `prueba`.
12. **Portal:** desde un pedido enviado por correo (`/my/orders/…`), paga con Tilopay: mismo resultado.
13. **Facturar:** crea y publica la factura del pedido pagado: debe quedar **pagada** sola y, si el cliente es Socio, dar sus puntos.
14. **Mirar los registros** del contenedor: no debe aparecer ninguna clave, usuario, contraseña ni token.
15. **Pedido de más de $1,000:** una compra con total mayor a mil dólares (por ejemplo varias unidades de un mueble barato). Debe
    quedar pagada igual. Anota **cómo trae `amount` Tilopay en `consult`** («1250.00» o «1,250.00»): el código acepta las dos.
16. **El pedido cambia mientras pagas:** abre la página de pago con un pedido; en otra pestaña cambia la cantidad; paga en la
    página de Tilopay. El pedido **no** debe confirmarse; la transacción queda en error con «Tu pedido cambió mientras
    pagabas»; Gerencia ve una actividad en el pedido («cobrado X, el pedido ahora vale Y»). Devuelve ese cobro de prueba desde el panel.
17. **Un pago de prueba no pasa en silencio:** el pedido pagado en el paso 4 lleva la nota «Pagado con una tarjeta de PRUEBA».
18. **Lo que hay que anotar y mandar** (para cerrar §8): el valor exacto que trae `order`, qué texto trae `environment` en `consult`
    para pruebas y para real, qué trae `consult` de una orden que no existe y con una llave equivocada, qué `code` trae un Yappy
    que todavía no responde, y si Yappy aparece en la página alojada.

**Para pasar a real:** repetir 3, 4 y 9 con **una compra pequeña de verdad** (reembolsable desde el panel) apenas se cambie a
`produccion` y se apague el «Modo Prueba»; revisar en el panel de Tilopay que la transacción dice «Producción».

## 8. Por verificar con Tilopay, por escrito (Soporte: <https://tilopay.com/soporte>)

1. El **algoritmo de `OrderHash`** (versiones V1 y V2) para comprobar la firma del retorno y del aviso.
2. La **especificación del webhook de `processPayment`**: campos, formato, firma y **cómo se registra la URL** de la cuenta.
3. Las **direcciones IP** desde las que salen esos avisos (para lista blanca, si se quiere).
4. Qué trae exactamente `order` en la redirección (¿nuestro `orderNumber` o un número de Tilopay como `TPYS-…`?).
5. Los valores de `environment` en `consult` (producción vs pruebas), el `type` de una fila de reembolso o reverso, y el de `capture`.
6. Si una orden **rechazada** puede reintentarse con el mismo `orderNumber` en la misma página (el diseño supone que sí).
7. **Largo máximo** de `orderNumber`, vigencia de la dirección de pago, tope de monto por transacción y límite de llamadas por minuto.
8. Si los campos `billTo*` aceptan valores vacíos o hace falta mandar algo (el código manda datos neutros cuando faltan).
9. Que la **página alojada** muestre Yappy y los demás métodos activos.
10. Que la cuenta de pruebas de desarrollador sea **permanentemente** de pruebas (sin el interruptor).
11. Los **códigos de estado de `consult`**: el ejemplo solo muestra «1» (aprobada); un rechazo trae «el código del emisor». Qué
    `code` y qué `response` trae una transacción **pendiente** (Yappy sin responder). El código solo da por rechazado un código
    numérico distinto de «1»; todo lo demás lo deja pendiente.
12. El **valor exacto de `environment`** en `consult` para pagos reales (el ejemplo solo muestra «Test»; «PROD» y «TEST» son del
    SDK). Hoy se aceptan, sin importar mayúsculas, `Test`/`prueba`/`sandbox` y `Production`/`produccion`/`prod`; cualquier otro
    texto **no paga** y deja una nota clara en el pedido (el pago real no se confirmaría hasta que se sepa el valor).
13. El **formato de `amount`** en montos de $1,000 o más («1250.00» o «1,250.00») y si alguna vez trae signo o separador distinto.
    Hoy se aceptan esas dos formas; cualquier otra no paga.
14. Los **campos exactos de `processPayment`** (cuáles son realmente obligatorios; que los `billTo*` neutros del código se acepten).
15. El **aviso de compras (webhook)** puede traer más de un campo con forma de orden (p. ej. `order` y `orderNumber`): hoy, si trae
    dos órdenes distintas, no se adivina y no se hace nada (la tarea programada y el retorno suplen).
16. **Cloudflare:** que una variable fijada en `wrangler.jsonc` gane sobre la del panel con `--keep-vars` (el staging confía en eso
    para quedar fijo en `prueba`). Se comprueba una vez en el panel tras el primer despliegue; la regla de que `produccion` exige
    `DCASA_ENTORNO=produccion` ya reduce el riesgo si no fuera así.
17. **Cómo aparece un reembolso en `consult`**: si como otra fila (tipo «Refund» u otro) o cambiando la fila del pago. El código
    trata cualquier fila que no sea un pago como «ambiguo» y no paga, pero un cobro ya marcado para revisión no depende de
    eso: nunca se paga solo (§3, punto 16).
18. **Con qué IP llegan los avisos de Tilopay** y cuántos por minuto como máximo (el freno de 120 por minuto por conexión del
    retorno y el aviso es generoso, pero si Tilopay mandara los avisos de muchas compras juntas desde una sola dirección habría
    que subirlo). El borde pone `X-Forwarded-For` con la IP real de Cloudflare (`edge/src/routing.ts`): ahí se apoya el freno.

## 9. Pendientes y siguiente paso

- **Abonos parciales de apartados con Tilopay.** Hace falta: que el pago en línea de un pedido acepte un monto menor al total
  (el marco `payment` de Odoo lo permite con `payment_amount` en el portal, pero el carrito de la tienda **exige** el total), que
  `dcasa_abonos` registre ese abono contra el apartado y que Socios siga dando puntos solo al liquidar. El proveedor ya compara
  el monto contra la **transacción** (no contra el pedido), así que ese cambio no toca la verificación.
- **Reembolsos.** `processModification` (tipo 2 reembolso, tipo 3 reverso) está documentado, pero mueve dinero: por ahora se
  hacen en el panel de Tilopay y se registran a mano en Odoo. Programarlo pide el «sí» de la dueña.
- **Comisiones de Tilopay.** No se registran. La contadora decide cómo (gasto bancario por transacción, o asiento al liquidar). El
  `consult` trae `commission`, `iva_commission`, `retention_*` y `net_to_liquidate` si algún día se quieren leer.
- **Factura automática al pagar** (`sale.automatic_invoice`): hoy el pago deja el pedido confirmado y el cobro en el diario Tilopay, y
  la vendedora factura como siempre (Odoo cruza solo el cobro al publicar). Encenderla factura sola a **todos** los proveedores: decisión
  fiscal de la dueña y la contadora.
- **Firma `OrderHash`**: cuando Tilopay la entregue (§8, punto 1).
- **Si el aviso no llega**: revisar *Seguridad › Eventos* en Cloudflare (una regla de bots del dominio podría frenar a Tilopay).
- **Que Gerencia sin «Ajustes técnicos» pueda encender Tilopay** (hoy solo el administrador): hace falta un permiso de lectura y
  escritura sobre ese proveedor y un menú para Gerencia; se dejó fuera a propósito en una versión que mueve dinero.
- **Hueco conocido (aceptado):** una orden que existe tarda más en contestar el aviso (porque se consulta a Tilopay) que una
  que no existe. Para adivinar una orden hace falta además su parte al azar (8 letras y números): no es práctico.
- **Aviso para la contadora:** al desplegar esta versión, Odoo crea el **diario bancario «Tilopay»** (código `TLP`) y su **cuenta
  contable**, **aunque el proveedor siga apagado**. Hay que avisarle para que revise esa cuenta y a qué rubro va.
- **Gerencia recibe las actividades** de cobros que no cuadran (pedido cambiado, pedido cancelado). Si nadie tiene el grupo
  Gerencia, las recibe quien administra el sistema.
- **Freno de ritmo en el borde para `/payment/tilopay/*`:** no se puso. El contador de ritmo del Worker (`edge/src/bots.ts`) es
  aproximado y, con los límites de Rate Limiting de Workers aún comentados en `wrangler.jsonc`, un freno por IP en una ruta que
  llama Tilopay podría frenar sus avisos. Hoy se protege con lo que hay en Odoo: tamaño de cuerpo, forma de la orden, ninguna
  llamada a Tilopay con una orden inventada y las consultas de 5 s por transacción. Si el aviso llegara a abusarse, se revisa con
  los números reales de *Seguridad › Eventos*.
- **Los topes de páginas de pago** (300 por hora en total, 30 por hora por conexión; `TOPE_PAGINAS_POR_HORA` y
  `TOPE_PAGINAS_POR_CONEXION_HORA` en `models/payment_transaction.py`) son límites técnicos, no cifras del negocio. Una sola conexión
  se topa con el suyo antes de gastar el global, y el global no cuenta lo ya pagado; pero quien junte varias conexiones y llegue a
  300 en una hora cierra Tilopay para todos hasta que pase la hora (los clientes ven «Hay muchos pagos en curso…» y las demás
  formas de pago siguen abiertas). Se acepta para la v1.
- **Una ráfaga sostenida de basura sí retrasa la confirmación de quien pagó sin dejar señal.** La tarea tiene 40 s por vuelta; con
  ~0,5 s por consulta son ~80 preguntas. Si alguien sostiene ~270 páginas nuevas por hora (necesita al menos 9 conexiones por el tope
  por conexión) un cliente que pagó, cerró la pestaña y cuyo aviso no llegó espera su turno (medido en simulación: 7 vueltas de
  la tarea, ~70 minutos, con ráfaga de 45 intentos por vuelta; con la señal de vida de su retorno o del aviso, una vuelta). Lo que
  Tilopay nunca vio deja de preguntarse al día para que la basura no se acumule. El arreglo de fondo es que el aviso de Tilopay esté
  registrado (§6.3): con el aviso, el cliente deja señal aunque haya cerrado la pestaña.
- **Brian** (`docs/BRIAN.md`): una herramienta de solo lectura «¿Tilopay está encendido y conectado?» (como `estado_de_meta`) no se
  hizo; la activación es del administrador por pantalla y no hay nada que Brian deba poder cambiar.

## 10. Cómo se probó

Todo con un **Tilopay simulado**, sin red real ni dinero: `tests/common.py` trae `SimuladorTilopay`, que sustituye a
`requests.post` y habla como el API documentado (inicio de sesión con 401 si las claves están mal, página de pago, orden duplicada,
consulta con la lista de filas, entornos «Test» y «Production»). Odoo además **bloquea cualquier llamada de red** que una prueba
no haya simulado. Las claves de las pruebas son inventadas y con forma reconocible (`LLAVE-DE-PRUEBA-…`) para buscarlas en
registros y pantallas.

| Dónde | Qué prueba |
|---|---|
| `tests/test_api.py` | Las claves no salen ni imprimiendo el objeto; formas de orden, retorno y aviso; la dirección de pago solo de `tilopay.com`; **`evaluar_consulta`** caso por caso (monto, moneda, orden ajena, rechazo, dos aprobadas, reembolsos, entorno, captura, formas raras); el cliente HTTP (token que se reutiliza, que se renueva, claves malas, tiempo agotado, red, basura, HTTP 500, ningún registro con claves) |
| `tests/test_proveedor.py` | Nace apagado y sin publicar; diario «Tilopay» (también si el plan contable lo borra); se ofrece solo con las tres llaves; solo USD y solo pedidos; los otros métodos no cambian; la pantalla y sus datos no traen claves; «Probar conexión» (bien, claves malas, caído, sin claves, quién puede) |
| `tests/test_flujo.py` | Pedido → página de pago → confirmación → pedido confirmado, cobro en el diario Tilopay, factura cruzada y compra en Socios; monto, moneda, entorno y modo distintos; orden de otra transacción o de otro proveedor; repeticiones, orden invertido y freno de 5 s; cancelada o vencida que luego paga; rechazo y reintento; Tilopay caído; dos pagos del mismo pedido; el monto del navegador; tope de páginas abiertas; la tarea programada |
| `tests/test_rutas.py` | Por HTTP de verdad: el aviso responde igual exista o no la orden y no llama a nadie con una orden inventada; solo POST; tope de 16 KB; JSON con cualquier tipo de contenido; el retorno inventado no paga; el retorno usa `returnData`; pagar desde `/my/orders` y esperar en «Estado del pago»; ningún registro con claves en todo el recorrido |
| `tests/test_revision.py` | Las pruebas de la **revisión independiente** (2026-11-19), tal cual las escribió quien intentó romperlo: proveedor sin publicar abierto por un visitante, total del pedido que cambia mientras se paga (sube y baja), tarea programada saturada con intentos basura, pago de un pedido cancelado, rechazo o cancelación seguidos de un pago aprobado, apartado, diario borrado, `evaluar_consulta` con formas raras, rutas con la orden de otro, servidor que no es de producción, pago de prueba sin marca y «Probar conexión» |
| `tests/test_correcciones.py` | Lo que esas correcciones piden además: nota y actividad para Gerencia (sin repetirse), el total que vuelve a coincidir, la última comprobación antes de confirmar, lo rechazado o cancelado cada 3 horas y solo 3 días, estado intermedio que queda pendiente, ritmo de la tarea (8 min / 1 h), orden por antigüedad, lotes, paro tras 3 fallas, presupuesto de tiempo, tope de 300 páginas por hora, montos de más de mil dólares y apartado |
| `edge/test/tilopay.test.ts` | Las variables viajan al contenedor y no impiden el arranque; la ruta pasa a Odoo, sin caché, sin freno de ritmo, sin bloqueo (también con la puerta del equipo en modo obligatorio); un POST cortado no se repite desde el borde; staging fijado en `prueba` |
| `edge/test/tilopay_revision.test.ts` | De la revisión independiente: variantes raras de la ruta (`.css`, `..`, `%70`, doble barra, con idioma) que nunca se vuelven cacheables ni caen en una ruta bloqueada, una respuesta «public» de Odoo que no se guarda, y claves vacías o con espacios que no inventan nada |


**Experimento de carga** (la tienda con la configuración de producción: `workers = 0`, `db_maxconn = 48`; un Tilopay de mentira
que tarda 4 s en contestar; 60 hilos martillando `/payment/tilopay/return` con órdenes REALES durante 45 s mientras una sonda pide
`/web/login` cada medio segundo; antes de medir se calienta el sitio —la primera vez Odoo compila los paquetes de CSS y JS y eso
solo, sin Tilopay, ya agota el grupo—; el control son las mismas 60 peticiones con órdenes que no existen, que no consultan a
Tilopay). La máquina estaba cargada por otras corridas (carga 9 a 11), así que se mide siempre el control:

| | Antes (`43e2569`) | Después, solo tope de llamadas y rutas web con lo reciente | Después, con el freno por conexión |
|---|---|---|---|
| Sondeos a `/web/login` que fallan | **71 de 80** | 0 de 35 | 0 de 33 |
| Errores `PoolError` durante el ataque | **38 012** | 0 | 0 |
| Llamadas a Tilopay a la vez (máximo) | **48** | 6 | 6 |
| Llamadas a Tilopay en los 45 s | 515 | 72 | 6 |
| Peticiones del ataque que dan error | 18 935 de 19 172 | 0 de 1 650 | 0 de 1 759 |
| Control: sondeos que fallan / `PoolError` | 0 de 33 / 0 | 0 de 34 / 12 | 0 de 34 / 10 |

Los 10 a 12 `PoolError` del control son de la propia carga de la máquina (60 hilos sin consultas a Tilopay, con otras corridas
encima), no de Tilopay; no crecen durante el ataque. Los scripts (`fake_tilopay.py`, `crear_txs.py`, `atacar.py`) son los del
revisor; el experimento solo les añade un servidor con el freno por conexión apagado para ver qué hace cada capa por separado.

**Resultado de la última corrida completa** (instalando todos los módulos del `Makefile` y corriendo `dcasa_pago_tilopay`, la lista de
llamadas permitidas de `dcasa_base`, `dcasa_guia`, la tienda configurada de `website_dcasa` y `dcasa_socios`), después de la revisión
independiente: **690 pruebas, 0 fallan, 0 con error**; de ellas **176 son de Tilopay**. En el Worker: `npx vitest run` **296 pruebas
pasan** (14 son de Tilopay) y `tsc --noEmit` sin errores. `ruff check addons` limpio.

**Capturas** (Odoo con un Tilopay simulado y datos inventados; la dueña las ve antes de producción): la pantalla del proveedor y
«Probar conexión», y la opción en el pago real de la tienda, sin elegir y elegida, a 1440 px y a 390 px. Al mirarlas salieron dos
fallas reales que ya se corrigieron: el aviso decía «Pagar con tarjeta o Yappy» cuando la tienda dice «Tarjeta, Yappy y más (Tilopay)», y
«Última prueba» no se actualizaba tras «Probar conexión». El triángulo amarillo junto al nombre del método en la tienda es el aviso de
Odoo mientras el proveedor está en **Modo de prueba**; desaparece al pasarlo a **Habilitado**.
