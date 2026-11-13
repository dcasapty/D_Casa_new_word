# Los canales de Juan: WhatsApp, Telegram, Messenger e Instagram

Puesto al día el 2026-11-06. Por dónde le escriben los clientes a Juan y cómo se conecta cada canal. Cómo funciona Juan por
dentro: [JUAN.md](JUAN.md). Lo que ve el equipo en Odoo: [JUAN_ODOO.md](JUAN_ODOO.md).

Cada canal es un adaptador del Worker `dcasa-juan` (`juan/src/canales/`) y se enciende o se apaga en Odoo, en
*Conversaciones › Configuración › Ajustes de Juan › «Dónde contesta»*. Las claves **nunca** se mandan por chat (ni a
Claude): se pegan directo en Cloudflare (*Workers & Pages › `dcasa-juan` › Settings › Variables and Secrets*). Para saber
qué clave falta, abre `https://dcasa-juan.dcasapty.workers.dev/salud`: muestra solo **nombres**, nunca valores.

| Canal | Estado (2026-11-09) | Webhook en `dcasa-juan` |
|---|---|---|
| **WhatsApp por la API oficial de Meta** (`whatsapp_cloud`) | **En producción desde el 2026-11-02**, con el número de la tienda (+507 6026-1919). Del 9 nov 16:00 al 10 nov no salió ni entró nada (131070): se arregló en Meta con «redireccionar conversación» a «D'CASA Juan», ver §1 «131070» | `/webhooks/whatsapp-cloud` |
| **Telegram** (`telegram`) | Funciona: canal de pruebas y avisos al equipo | `/webhooks/telegram` |
| **Messenger** (`messenger`) | **Conectado el 2026-11-09** (página DCASA PTY): probado de punta a punta. Hasta la revisión de Meta solo contesta a quien tiene rol en la app | `/webhooks/meta` |
| **Instagram** (`instagram`) | **Conectado el 2026-11-10** (por la página DCASA PTY, misma app y misma llave que Messenger; ver §3) | `/webhooks/meta` |
| **WhatsApp por QR** (`whatsapp_qr`, el puente `puente-wa/`) | Construido y probado; **nunca se desplegó** en producción | `/webhooks/whatsapp-qr` (lo llama el puente) |

## 1. WhatsApp por la API oficial (el canal principal)

### Cómo quedó (2 de noviembre de 2026)

Juan contesta el WhatsApp de la tienda desde las 20:26 UTC del 2 nov (3:26 pm Panamá). Lo hizo la dueña desde su cuenta de
Meta, guiada paso a paso:

- App de Meta **«D'CASA Juan»** con el producto WhatsApp.
- Webhook `https://dcasa-juan.dcasapty.workers.dev/webhooks/whatsapp-cloud`, suscrito a los mensajes **solo en la tarjeta
  del número de la tienda** (no en la del número de prueba +1 555 que Meta trae).
- Secretos del Worker `dcasa-juan`: `META_VERIFY_TOKEN` (el token de verificación del webhook), `META_APP_SECRET` (la clave
  secreta de la app) y `WHATSAPP_CLOUD_TOKEN`: la **llave permanente** de un usuario del sistema de Meta (`juan-bot`, rol
  Administrador, control total de la app y de la cuenta de WhatsApp, caducidad «Nunca», permisos
  `whatsapp_business_messaging` y `whatsapp_business_management`).
- Variables del Worker: `WHATSAPP_PHONE_NUMBER_ID` (el identificador del número de la tienda que muestra Meta; no es el
  celular) y `URL_PUBLICA` (`https://dcasa-juan.dcasapty.workers.dev`, sin `/` al final: sin ella no se ven en Odoo las
  fotos que manda el cliente; pasó el 2 nov y `/salud` ahora lo marca).
- **Nunca** se deja puesta la llave del Explorador de la API Graph: vence en 1 o 2 horas y Juan dejaría de contestar.

### Reglas de Meta que hay que saber

- **24 horas.** Juan (y una vendedora desde Odoo) solo puede escribir con texto libre dentro de las 24 horas del último
  mensaje del cliente. Pasado eso, Meta solo deja escribir con una **plantilla aprobada** (y cobra por ella; ver los
  precios vigentes en Meta). El adaptador lo sabe y no manda nada fuera de la ventana. Sofía, pasadas las 24 horas,
  propone llamar al cliente ([SOFIA.md](SOFIA.md)).
- **Falta (código):** los seguimientos automáticos de Juan (n.º 1 a las 5 horas, n.º 2 a los 5 días) salen como texto
  libre; fuera de la ventana tendrían que salir como **plantilla**. Se hace cuando existan las plantillas aprobadas
  (están en [PRIORIDADES.md](PRIORIDADES.md)).
- **Escribirle primero** a un cliente que nunca escribió: solo con plantilla. Por eso el recordatorio del abono por
  WhatsApp sigue siendo un botón que abre WhatsApp con el mensaje listo ([CORREO.md](CORREO.md)).
- **Sin confirmar con un mensaje real:** si lo que el equipo escribe desde la app de WhatsApp del teléfono llega a Odoo
  como «escrito por una vendedora» (los «ecos» de la coexistencia). El adaptador ya los trata así, pero la forma exacta del
  aviso no se verificó contra la documentación de Meta.

### Citas, reenviados, reacciones y palomitas (2026-11-07)

Pedido de la dueña: «solamente vemos la palabra "este" y no vemos lo que realmente nos envió… no vemos si se entregó».
No hace falta tocar nada en Meta: todo llega por la misma suscripción a los mensajes (`messages`) del número.

| Qué manda Meta | Qué hace Juan | Qué se ve en Odoo |
|---|---|---|
| `messages[].context` con `{from, id}` (el cliente respondió a un mensaje) | El mensaje viaja con `cita.id`; Juan busca lo citado en su memoria (o se lo dice Odoo) y se lo muestra a la IA como `[El cliente responde a este mensaje de D'CASA: «…»]`, un **dato del cliente** (sin etiquetas ni marcas de confianza, tarjetas, cédulas y PIN tapados, hasta 300 letras; el cliente no puede escribir esa marca a mano, ni con espacios invisibles, espacios duros, corchetes de ancho completo o letras cirílicas, y lo citado no puede cerrarla antes: sus «» pasan a “”). Si lo citado está en su memoria no guarda copia: lo lee de la fila al armar el prompt. Para el anti-spam, «este» citando mensajes distintos no es un repetido | El recuadro de la cita sobre el texto |
| `context.forwarded` / `frequently_forwarded` | `reenviado: "una"/"muchas"`; la IA lo sabe | «Reenviado» / «Reenviado muchas veces» |
| `type: "reaction"` con `reaction: {message_id, emoji}` (sin emoji = la quitó) | **Evento**, no mensaje: no despierta a la IA ni cuenta para la ventana de 24 h | La carita en la esquina del mensaje |
| `statuses` (`sent`, `delivered`, `read`, `failed` con `errors`) | **Evento**: una tanda por aviso a Odoo (`POST /dcasa/juan/v1/eventos`) | Las palomitas; «No llegó» con el motivo, siempre terminado en «(código N)» (131047 = pasaron las 24 h; 131026 = no se pudo entregar; 131042 = método de pago de la cuenta; 131031 = cuenta bloqueada; 131048 = frenado por spam; los demás, con el texto de Meta). Los de la CUENTA (131042, 131031, 131048) avisan a Gerencia por Telegram, una vez cada 6 h por código (2026-11-09) |

- **Lo que se le contesta a Meta.** Los mensajes se siguen guardando en el Durable Object **antes** del 200 (Desplegar 49).
  Las palomitas y reacciones **no**: se contesta 200 y se le mandan a Odoo después, dentro del mismo `waitUntil`, con dos
  reintentos (2 s y 6 s: Odoo dormido despierta en unos 10 s). **Si Odoo está caído para un aviso de solo palomitas, Meta
  recibe 200 igual** y esa palomita se pierde. Por qué: un 500 haría que Meta reenviara el aviso (y los mensajes del mismo
  lote) por horas mientras Odoo no vuelva, con el webhook marcado como fallando, por algo que solo pinta una palomita; los
  mensajes del cliente ya están a salvo antes del 200. Perder una palomita no es perder un mensaje, y la siguiente la
  corrige (leído le gana a entregado, que le gana a enviado). Una reacción perdida así es el mismo costo (raro: solo con
  Odoo caído).
- **La palomita de «enviado» llega en un segundo**, a veces antes de que Odoo registre la respuesta de Juan. Odoo devuelve
  esos ids en `desconocidos` y Juan los vuelve a mandar a los 5 y a los 10 s. Si sigue sin conocerlos (un mensaje de antes
  de esta versión o mandado por fuera de Juan), se ignoran sin ruido. Un aviso con más de 100 se manda en tandas de 100 (no
  se pierde ninguno), y una reacción o un recibo con un id que no es texto se ignora sin romper el resto (revisión 2026-11-07).
- **Ids de cada burbuja.** WhatsApp da un id (`wamid`) a cada burbuja y a cada foto. Juan los guarda en su memoria (para
  saber qué citó el cliente) y se los manda a Odoo en `partes` con la respuesta del bot y en la respuesta de `/odoo/enviar`.
- **«Responder» desde Odoo**: `POST /odoo/enviar` acepta `responde_a` (el `wamid` del mensaje del cliente); sale como
  `context: {message_id}` en el **primer** mensaje. Si Meta rechaza justo la cita (un 400 con código 100 o 131009: el
  citado es muy viejo o ya no existe), sale otra vez **sin** la cita; cualquier otro rechazo (un 408, un 401, otro 400, un
  429 o un 5xx) no se maquilla, porque pudo haber salido o fallaría igual (revisión 2026-11-07).
- **Arreglado de paso:** si WhatsApp se caía a la mitad de una respuesta de varias burbujas, el reintento mandaba otra vez
  la primera (el cliente la veía dos veces). Ahora el adaptador dice cuánto salió (`EnvioParcialError`) y solo se manda lo
  que falta, como ya hacía Telegram.
- **Orden de despliegue:** primero Odoo (sabe recibir `cita`, `reenviado`, `partes` y `/eventos`), después Juan. Un Juan
  nuevo con un Odoo viejo funciona: Odoo ignora los campos que no conoce y `/eventos` le da 404, que Juan entiende como
  «todavía no» (no insiste y el mensaje del cliente nunca dependió de eso). Un Juan viejo con un Odoo nuevo, igual que antes.

### Si deja de contestar

1. Abre `/salud` de Juan: en `whatsapp_cloud`, `"faltan"` tiene que salir vacío.
2. Si `/salud` está bien y aun así no contesta: casi siempre es la llave. Revisa que `WHATSAPP_CLOUD_TOKEN` sea la
   permanente de `juan-bot` (no una del Explorador) y, si hace falta, genera otra en Meta Business › Usuarios del sistema ›
   `juan-bot` › Generar token ⚠, con los dos permisos de arriba, y pégala en Cloudflare.
3. En Odoo, *Conversaciones › Conexiones* muestra el estado de cada canal y el último problema de envío.
4. **El motivo exacto está en la burbuja del mensaje** que no salió («No se pudo enviar: …», con el código de Meta). El
   aviso «Quedó por enviar: el Worker no respondió y se reintenta solo» sale para CUALQUIER fallo, aunque Juan sí haya
   respondido (mostrar ahí el motivo real va en el próximo lote).
5. **Código 131070, «another app is controlling this thread now»** (2026-11-09, desde las 16:00): otra aplicación tiene
   el control de las conversaciones del número y Meta no deja contestar a Juan. Ese mismo día, en Configuración del
   negocio › Cuentas de WhatsApp, el número salía **«Conectado», calidad «Alta»**, pero con el aviso **«Add a Messaging
   account»** («Messaging limits: No disponible»): se había quedado sin la cuenta de mensajes de Callbell (la …764382,
   pagada con la línea de crédito de Callbell), probablemente porque Callbell la retiró cuando se le pidió. Arreglo (lo
   hace la dueña en Meta, **desde el portafolio DCasa Pty**, no desde BukoFlow): crear y ligar una cuenta de mensajes de
   DCasa Pty con su tarjeta. Si sigue el 131070, revisar en el Administrador de WhatsApp si quedó encendido el «Agente
   de negocios de Meta» (la IA de Meta toma las conversaciones y los mensajes llegan como `standby`) u otra app
   conectada al número. Las plantillas vivían en la cuenta de mensajes vieja: si se usan, hay que volver a crearlas.

   **Cómo se resolvió (2026-11-10):** en Meta, con una cuenta administradora del portafolio DCasa Pty, el botón
   **«redireccionar conversación»** (el Enrutamiento de conversaciones) se puso hacia «D'CASA Juan» y se eliminó a
   Callbell. Con eso volvieron a salir y entrar los mensajes (no hubo que esperar los «7 días» de soporte ni borrar el
   número, como proponía Callbell).

   **La causa (2026-11-10): el «Enrutamiento de conversaciones»** (Conversation Routing, de Meta desde
   septiembre de 2026). En la cuenta de WhatsApp, Meta Business Suite guarda qué app es la **principal** de cada punto de
   entrada (mensajes de servicio, Click-to-WhatsApp, respuestas a marketing y a utilidad). Solo la principal (la dueña
   del chat) puede contestar: cualquier otra recibe **131070**, aunque nadie más esté contestando. **Al quitar una app
   (Callbell), Meta no nombra otra principal**: hay que elegir a mano «D'CASA Juan» en cada punto de entrada. Sin API
   pública: se hace en Meta Business Suite › Configuración › la cuenta de WhatsApp › Enrutamiento de conversaciones (el
   nombre exacto del menú puede variar), con un administrador del portafolio dueño de la cuenta. Ahí mismo se ve si
   está el agente de IA de Meta.
   - **Juan pide el control solo** (Juan 17): si un envío da 131070, Juan le pide a Meta el control de ESE chat
     (`thread_control`, «take», en `api.facebook.com`) una vez cada media hora por cliente, y si Meta se lo da manda
     otra vez lo rechazado. Meta solo se lo da a la app nombrada «socio de escalamiento»; a las demás responde que no
     (2494191, según las guías de proveedores). Lo que Meta contesta queda en los registros de `dcasa-juan` en
     Cloudflare: «Juan pidió el control del chat y Meta dijo que no: HTTP … · código … · fbtrace_id …» (el
     `fbtrace_id` es lo que pide soporte de Meta). Tras un «no», nadie lo vuelve a pedir en 10 minutos.
   - **Campos del webhook `standby` y `messaging_handovers`** (WhatsApp › Configuración de la app): si se suscriben,
     Juan anota en el registro, sin datos de nadie, cuántos mensajes llegan por `standby` (es decir, otra app lleva
     esos chats) y quién tomó el control (`messaging_handovers`, con los ids de las apps). **Nunca contesta un
     `standby`**: Meta pide no hacerlo. El `standby` además necesita que el negocio le dé a la app «visibilidad en
     espera» en el enrutamiento (viene apagada).
   - **Para soporte de Meta:** WABA 1313438470854835 («DCasa Pty (Odoo)»), número 1254707667716067, app «D'CASA Juan»
     1694271085547708. Pedir que digan qué app tiene el control y que pongan a «D'CASA Juan» de principal.
   - **Lo que pasó el 10 nov:** enviar volvió antes que recibir (prueba desde el Explorador de la API Graph, llegó).
     Si los mensajes de los clientes no llegan a Odoo: (1) mirar en Cloudflare › `dcasa-juan` › Registros si hay POST a
     `/webhooks/whatsapp-cloud` a la hora en que se escribió; (2) si no hay, volver a suscribir la app a la WABA
     (`POST 1313438470854835/subscribed_apps` en el Explorador, sin parámetros); (3) si hay POST pero nada en Odoo,
     buscar en el registro «aviso sin mensajes ni palomitas» (Juan 18 dice qué traía). Soporte de Meta: tras cambiar de
     proveedor, hasta **7 días** para que el número se desvincule del anterior. **No eliminar ni volver a registrar el
     número** sin hablarlo con los dueños (lo propuso Callbell).

### Para otra instalación (o para conectar otro número)

1. Cuenta de **Meta Business** a nombre de la empresa, con sus datos reales. Meta puede pedir **verificar el negocio** con
   documentos: tarda días, conviene empezar primero. ⚠
2. En Meta for Developers, una *app* de tipo **Empresa** con el producto **WhatsApp**. ⚠
3. El **número**: uno que no esté en la app de WhatsApp (lo más seguro para empezar) o el de siempre con el modo de
   coexistencia de Meta (la app del teléfono y la API a la vez). ⚠ Confirmar disponibilidad y requisitos en Meta antes
   de tocar el número de siempre.
4. Un **usuario del sistema** con **llave permanente** y los permisos de mensajería y administración de WhatsApp Business.
5. Los cuatro datos en Cloudflare (tabla de arriba: `WHATSAPP_CLOUD_TOKEN`, `META_APP_SECRET`, `META_VERIFY_TOKEN` y la
   variable `WHATSAPP_PHONE_NUMBER_ID`), el webhook en Meta con el mismo `META_VERIFY_TOKEN` y la suscripción a los
   mensajes en la tarjeta del número.
6. En Odoo › *Ajustes de Juan*: encender **WhatsApp (API oficial)**.
7. Probar: texto, una foto, un PDF, una nota de voz, una respuesta desde Odoo y el «Atender» desde Telegram.

Los puntos con ⚠ dependen de pantallas de Meta que cambian seguido: confirmarlos ahí antes de darlos por ciertos.

## 2. Telegram (pruebas y avisos)

Telegram no necesita el número de la tienda ni a Meta. Es el canal de **pruebas** y, además, por donde le llegan los avisos
al equipo (con el bot de Brian, ver [BRIAN.md](BRIAN.md)).

1. En Telegram, escríbele a **@BotFather**, manda `/newbot` y sigue los pasos. Te da un **token**: es
   `TELEGRAM_BOT_TOKEN_JUAN`.
2. Inventa el **secreto del webhook**: una contraseña al azar de 24 a 64 caracteres, **solo letras sin tildes, números,
   guion y guion bajo** (Telegram no acepta otros). Es `TELEGRAM_WEBHOOK_SECRET_JUAN`.
3. Pega en el Worker (para ensayar, `dcasa-juan-staging`): `TELEGRAM_BOT_TOKEN_JUAN`, `TELEGRAM_WEBHOOK_SECRET_JUAN` y, si
   todavía no están, `JUAN_ODOO_TOKEN`, `JUAN_WORKER_TOKEN` y la clave de la IA ([JUAN.md §5](JUAN.md#5-qué-secreto-en-qué-worker-para-qué)).
4. Dile a Telegram a dónde mandar los mensajes. Abre en el navegador, cambiando lo que está entre `< >`:
   ```
   https://api.telegram.org/bot<TOKEN_DEL_BOT>/setWebhook?url=https://dcasa-juan-staging.dcasapty.workers.dev/webhooks/telegram&secret_token=<SECRETO_DEL_WEBHOOK>
   ```
   Debe contestar `{"ok":true,"result":true,...}`. (Para quitarlo: `.../deleteWebhook`.)
5. Escríbele «Hola» al bot. A los ~15 segundos contesta y se presenta como «Juan de D'CASA».
6. Escríbele `/miid`: te dice tu chat id. Pégalo como `ALERTA_TELEGRAM_CHAT_ID` si quieres que los avisos de salud te
   lleguen ahí.
7. Pruebas útiles: «persona» (pasa a una vendedora), «cuánto cuesta una cama queen» (usa el catálogo y dice «+ ITBMS»),
   «me lo entregan mañana» (dice que lo confirma una vendedora), mandar una foto.

Si no contesta: abre `/salud` y mira `secretos_faltantes` y `canales.telegram`; después `/odoo/salud` (con el token) para ver
el último fallo de la IA.

**Citas, reenviados y reacciones en Telegram (2026-11-07).** Las citas (`reply_to_message`, que trae también lo que decía el
mensaje citado, o el pedazo elegido en `quote`) y los reenviados (`forward_origin`) llegan solos. «Responder» desde Odoo sale
con `reply_parameters` (con `allow_sending_without_reply`: si el citado ya no existe, sale igual). **Las reacciones** solo
llegan si el webhook las pide: hay que registrarlo otra vez con `allowed_updates` (el mismo paso 4, con un dato más):
```
https://api.telegram.org/bot<TOKEN_DEL_BOT>/setWebhook?url=https://dcasa-juan.dcasapty.workers.dev/webhooks/telegram&secret_token=<SECRETO_DEL_WEBHOOK>&allowed_updates=%5B%22message%22%2C%22message_reaction%22%5D
```
Telegram **no** les da a los bots «entregado» ni «leído»: en Telegram no hay palomitas.

## 3. Messenger e Instagram (Messenger conectado el 2026-11-09; Instagram el 2026-11-10)

> **Corrección (2026-11-12): hoy a los clientes no les llega nada.** Las pruebas del 9 y 10 nov se hicieron con cuentas
> que tienen papel en la app o en el portafolio (los jefes, la agencia), y a esas sí les contesta. La dueña comprobó con
> otro Claude que los mensajes de clientes de verdad **nunca llegan** al webhook (cero POST a `/webhooks/meta` en los
> registros de Cloudflare). Es la regla de Meta: mientras la app no tenga la aprobación (acceso avanzado tras la
> revisión de la app y la verificación del negocio), Meta solo manda los avisos de quien tiene papel en la app
> ([Meta: webhooks de mensajes de Instagram](https://developers.facebook.com/docs/instagram-messaging/webhooks);
> [Messenger Platform e Instagram](https://developers.facebook.com/docs/messenger-platform/instagram)). El código no
> tiene error. Caminos: el paso 9 de abajo (revisión de la app; para Messenger es el único) y, para Instagram, probar
> «Instagram API con inicio de sesión de Instagram» con la cuenta propia de D'CASA en una app de su propio portafolio
> (Meta: si la app solo sirve la cuenta propia o una que se administra, basta el acceso estándar; hay fuentes que dicen
> lo contrario, así que se prueba). Ver PRIORIDADES.

**Cómo quedó Instagram (2026-11-10):** con la cuenta de los jefes (administradores de DCasa Pty) y Claude en Chrome:
`instagram_basic` e `instagram_manage_messages` agregados a la app «D'CASA Juan» (Meta los pone también en el caso de uso
de Messenger), «Añadir o suprimir páginas» con **solo** DCASA PTY y @dcasapty (la ventana de Meta se abre aparte: la
maneja la persona, Claude en Chrome no la alcanza), llave nueva de DCASA PTY pegada **encima** de `META_PAGE_TOKEN` (la
misma etiqueta: sirve para Messenger e Instagram; Messenger siguió funcionando), webhook de Instagram ya con la URL de
Juan y `messages` suscrito. Un «Hola buenas» desde otra cuenta: Juan contestó y salió en Odoo con el nombre. **Se
descartó** la guía de un conocido («inicio de sesión con Instagram»): pide otra llave (`IG…`, vence a los 60 días) y
otra clave secreta, y Juan habría tenido que cambiar; por la página no hizo falta tocar nada.
- **La foto no salía por Instagram** (el texto sí, «(#100) Error al subir el producto»), igual que Messenger el 9 nov.
  Juan 19 la subía aparte (`me/message_attachments`) y siguió fallando. Desde Juan 20 se prueba, en orden: (1) subir y
  enviar en la **misma** llamada, como Messenger (`me/messages` con `filedata`; la documentación de Meta lo da para
  Instagram), (2) subir aparte y mandar con `attachment_id`, (3) por URL. Si ninguno sale, «Por qué no salió» en Odoo
  dice qué contestó Meta a cada intento («Instagram no aceptó la foto · envío: … · aparte: … · URL: …»).
  **Confirmado por la dueña (11 nov):** con Juan 20 la foto llegó por Instagram (salió por el primer camino).

**Cómo quedó Messenger (2026-11-09):** con la cuenta de Facebook que tiene **control total** de la página (la que
abría Chrome solo tenía Contenido, Actividad de la comunidad y Estadísticas: sin «Mensajes» la página no sale al tocar
«Conectar»), webhook `…/webhooks/meta` verificado, la página **DCASA PTY** suscrita a `messages`, `message_echoes` y
`messaging_postbacks`, y `META_PAGE_TOKEN` en Cloudflare. Un «Hola buenas» desde Messenger: Juan contestó en segundos y
la conversación salió en Odoo («Messenger 2838…», con el número del cliente en vez del nombre). Desde el 2026-11-10 Juan
le pide el nombre a Meta una vez por conversación, antes de guardar el mensaje (Messenger: nombre y apellido; Instagram:
nombre o @usuario; `nombreDePerfil`, plazo de 3 s, a la hora si falla) y Odoo cambia el provisional por el real con el
siguiente mensaje del cliente. **El perfil (User Profile API) solo lo da Meta con el permiso «Business Asset User Profile
Access»** (revisión de la app; sin él, solo a quien tiene rol): el primer cliente real del 10 nov siguió saliendo como
«Messenger 2912…». Por eso, si el perfil no responde, Juan lo saca de la conversación de la página
(`me/conversations?platform=…&user_id=…&fields=participants`: Messenger da `name`, Instagram `username`), que pide los
permisos de mensajes de la página. Si ninguno da el nombre, el registro de Juan dice qué consulta y qué código dio Meta.
Al pedir la revisión de la app, agregar «Business Asset User Profile Access» (también da la foto de perfil). Trampas de ese día:
- **En «Generar identificadores de acceso» aparecen OTRAS páginas** de la misma cuenta (Smart TV Panama, Rofer Service):
  suscripciones y «Generar» SOLO en DCASA PTY, o Juan contestaría los mensajes de otros negocios.
- **Las fotos no salían por Messenger** («meta send 400: (#100) Error al subir el producto»; el texto sí): con
  `payload.url` Meta tiene que bajar la foto él mismo desde la URL firmada de dcasapty.com y no lo lograba (WhatsApp
  sí lo logra con la misma URL). Desde el 2026-11-10 Juan baja el archivo y **se lo sube a Meta** en la misma llamada
  (`filedata`, multipart, hasta 25 MB); si Juan no logra bajarlo, va por URL como antes. Instagram: ver arriba (se
  sube aparte y se manda con `attachment_id`).
- **El token de verificación de 2 nov se había perdido**: se puso uno nuevo en `META_VERIFY_TOKEN` (Cloudflare) y el
  mismo en Meta. No afecta a WhatsApp: solo se usa al verificar un webhook.
- **Instagram dio «Invalid Scopes: instagram_manage_messages, instagram_basic»** al tocar «Añadir o suprimir páginas»
  (Messenger › Configuración de Instagram): la app todavía no tiene esos permisos. Se agregan en «Permisos y funciones»
  (de Messenger o del caso de uso «API de Instagram»; NO «API setup with Unified login» ni «Crear nueva
  configuración», que es otra llave). Después: «Añadir o suprimir páginas» con DCASA PTY y @dcasapty, «Generar» y
  **reemplazar** `META_PAGE_TOKEN` por ese (sirve para los dos), suscribir `messages` y, en la app de Instagram,
  «Permitir el acceso a los mensajes». Quedó pendiente porque hace falta entrar con acceso al portafolio DCasa Pty
  (la cuenta usada solo ve BukoFlow).

El código está listo y probado (`juan/src/canales/meta.ts`): falta lo que solo se hace en Meta, Cloudflare y Odoo. Al terminar,
Juan contesta los mensajes de la página de Facebook y del Instagram de D'CASA y todo queda en *Odoo › Conversaciones*, igual que
WhatsApp.

> **Importante:** Juan usa **un solo** `META_APP_SECRET` y **un solo** `META_VERIFY_TOKEN` para WhatsApp, Messenger e
> Instagram (lo comprueba la firma de cada aviso de Meta). Desde el 2 nov esos dos ya están puestos con los de la app
> **«D'CASA Juan»**. Por eso Messenger e Instagram se agregan **a esa misma app** ⚠ y el webhook usa el **mismo** token de
> verificación. Si se creara otra app, su clave secreta no coincidiría y Juan rechazaría los mensajes. Lo único nuevo en
> Cloudflare es `META_PAGE_TOKEN`.

### Antes de empezar

1. Tu Facebook personal es **administrador** de la página de D'CASA y del portafolio de negocios (Meta Business) de D'CASA.
2. El Instagram de D'CASA es **cuenta profesional** y está **conectado a la página** de Facebook (Meta Business Suite ›
   Configuración › Cuentas de Instagram ⚠).
3. En la app de Instagram, con la cuenta de D'CASA: Configuración › Mensajes y respuestas a historias › Herramientas
   conectadas › **Permitir el acceso a los mensajes** ⚠. Sin esto, Instagram no le pasa los mensajes a Juan.
4. Abre `https://dcasapty.com/privacidad` y confirma que carga (Meta pide esa dirección).
5. Ten a mano el valor de `META_VERIFY_TOKEN` (en tu gestor de contraseñas): va otra vez en el webhook.

### Pasos

1. **Agregar Messenger a la app.** [developers.facebook.com](https://developers.facebook.com) › Mis apps › **D'CASA Juan** ›
   Casos de uso › agregar **Interactuar con los clientes en Messenger** ⚠ (y, si lo ofrece, el de **mensajes de
   Instagram** ⚠).
2. **Datos básicos** (Configuración de la app › Básica): URL de la política de privacidad `https://dcasapty.com/privacidad`
   (también sirve para «eliminación de datos»), el logo de D'CASA (1024 × 1024) y la categoría ⚠. Guardar.
3. **Conectar la página y sacar su llave.** Casos de uso › Messenger › Personalizar › **Configuración de la API de
   Messenger** ⚠ › «Generar tokens de acceso» › **Conectar** › la página de D'CASA › acepta los permisos › **Generar** ›
   copia el token y pégalo en Cloudflare como secreto **`META_PAGE_TOKEN`**.
4. **El webhook.** En la misma pantalla, «Configurar webhooks»: URL `https://dcasa-juan.dcasapty.workers.dev/webhooks/meta`
   y, como token de verificación, **el mismo valor de `META_VERIFY_TOKEN`**. **Verificar y guardar**. Al lado de la
   página: **Agregar suscripciones** › `messages`, `message_echoes` y `messaging_postbacks` › Guardar.
5. **Instagram.** En el caso de uso de Instagram ⚠: conecta la cuenta de Instagram de D'CASA; webhook con la **misma** URL
   y el **mismo** token; suscribe `messages`. No hace falta otra llave: Juan contesta Instagram con la de la página.
6. **Revisar.** En `/salud` de Juan, `messenger` e `instagram` con `"faltan": []`.
7. **Encender en Odoo.** *Ajustes de Juan › «Dónde contesta»*: marca **Messenger** e **Instagram** › Guardar.
8. **Probar antes de la aprobación.** Hasta que Meta apruebe la app, solo contesta a quien tiene **rol en la app** (tú y
   quien agregues en Roles de la app › Probadores ⚠). Escríbele «hola» a la página desde tu Facebook personal: Juan contesta y
   la conversación aparece en Odoo.
9. **Pedir la aprobación** (para que conteste a todos los clientes): con el negocio verificado, App › **Revisión de la app ›
   Permisos y funciones**: acceso avanzado para `pages_messaging`, `pages_manage_metadata`, `instagram_manage_messages`,
   `instagram_basic` y `pages_show_list` (Meta puede pedir también `business_management`) ⚠. Por cada permiso, el texto de
   abajo y un video corto (un cliente escribe a la página › Juan contesta › la conversación en Odoo). Cuando aprueben, poner
   la app **En vivo** ⚠.

Texto para Meta:

> D'CASA Panamá es una tienda de muebles en La Chorrera, Panamá. Usamos este permiso para recibir y responder los
> mensajes que los clientes nos escriben a nuestra página de Facebook y a nuestro Instagram, con nuestro asistente y
> nuestras vendedoras desde nuestro sistema (Odoo). Solo respondemos a quien nos escribe, dentro de las 24 horas de su
> último mensaje.

### Bueno saber

- Juan solo puede contestar dentro de las **24 horas** del último mensaje del cliente (regla de Meta). Pasado eso, se
  contesta desde Meta Business Suite.
- Si una vendedora contesta desde Meta Business Suite o la app, ese mensaje también queda en Odoo.
- Si Messenger e Instagram dejan de contestar de golpe y `/salud` está bien: suele ser la llave de la página (por ejemplo,
  tras cambiar la contraseña de Facebook). Se genera otra (paso 3) y se pega en Cloudflare.
- Detalle técnico: `GET/POST /webhooks/meta` (verificación con `META_VERIFY_TOKEN`, firma `X-Hub-Signature-256` con
  `META_APP_SECRET`), envío por la Send API con `META_PAGE_TOKEN`; un canal apagado en Odoo contesta 200 y no atiende.

## 3b. Instagram por «inicio de sesión de Instagram» (la segunda puerta, 2026-11-12)

La dueña aprobó probar esta puerta («me parece bien esa segunda puerta y que él inicie como una persona normal desde su
cuenta personal y que todo lo haga el jefe»). Juan ya la trae (Desplegar Juan 22, ruta `/webhooks/instagram`,
`juan/src/canales/instagramLogin.ts` e `instagramLlave.ts`), **apagada** hasta que se pongan `INSTAGRAM_TOKEN` e
`INSTAGRAM_APP_SECRET`; mientras tanto, Instagram sigue por la página como antes. La documentación de Meta se contradice
sobre si basta el acceso estándar para la cuenta propia: lo dice la prueba del último paso. Si no alcanza, el camino es la
revisión de la app (como Messenger).

Para que Juan conteste el Instagram de D'CASA (@dcasapty) a **todos** los clientes, no solo a quien tiene un papel en la
app. Se hace **desde la cuenta propia del jefe** (la de Facebook que es administradora del portafolio DCasa Pty), **no
desde la cuenta de la agencia**.

Lo que va marcado con ⚠ es el nombre de un menú o un botón de Meta que no se pudo ver en pantalla: Meta lo cambia seguido.
Si no aparece igual, busca uno parecido.

**Las llaves y claves nunca se pegan en un chat** (ni a Claude, ni por WhatsApp, ni por correo): solo en Cloudflare, en
el lugar que dice el paso 5.

---

#### Antes de empezar

1. Que el equipo técnico ya haya **desplegado la versión de Juan que trae `/webhooks/instagram`**. Para saberlo, abre
   `https://dcasa-juan.dcasapty.workers.dev/salud`: en `canales › instagram` debe aparecer `"puerta": "pagina_facebook"`.
   Si no aparece `puerta`, todavía no está: espera.
2. El Instagram de D'CASA es **cuenta profesional** y **pública**.
3. En la app de Instagram, entrando como @dcasapty: Configuración › Mensajes y respuestas a historias › Herramientas
   conectadas › **Permitir el acceso a los mensajes** encendido ⚠ (ya se hizo el 10 nov; solo confirma).
4. Abre `https://dcasapty.com/privacidad` y confirma que carga.
5. Ten a mano el valor de `META_VERIFY_TOKEN` (está en el gestor de contraseñas): va otra vez en el webhook.

#### Paso 1. ¿De quién es la app «D'CASA Juan»?

1. Entra a [developers.facebook.com](https://developers.facebook.com) › **Mis apps** › **D'CASA Juan**.
2. **Configuración de la app › Básica** ⚠ y mira **Portafolio comercial** (o «Business portfolio») ⚠.
   - Si dice **DCasa Pty**: bien, puedes seguir con esa app (paso 2, opción A).
   - Si dice **Juancito Ads** (el de la agencia) o no puedes verlo: **no la toques**: ahí corre el WhatsApp de la tienda
     y cualquier cambio puede cortarlo. Para Instagram usa una **app nueva** del portafolio de D'CASA (paso 2, opción B).
     Pasar «D'CASA Juan» al portafolio de D'CASA es otro trámite (la agencia tiene que soltarla y D'CASA reclamarla, en
     Configuración del negocio › Cuentas › Apps ⚠); hacerlo con calma y aparte, sin prisa por Instagram.

> **Por qué una app nueva sirve igual:** esta puerta de Instagram tiene **su propia clave secreta** y **su propio
> webhook**. Juan no necesita que sea la misma app que WhatsApp y Messenger. Meta además avisa que una app puede usar
> «inicio de sesión de Facebook» o «inicio de sesión de Instagram», **no los dos** ⚠: si «D'CASA Juan» no te ofrece la
> opción del paso 2 (o te advierte algo así), usa la opción B.

#### Paso 2. Agregar «API de Instagram con inicio de sesión de Instagram»

**Opción A — en «D'CASA Juan»** (solo si es de DCasa Pty): en el panel de la app › **Casos de uso** (o «Agregar
productos») › **Instagram** › **API setup with Instagram login** / «Configuración de la API con inicio de sesión de
Instagram» ⚠. **No** «API setup with Unified login» ni «API setup with Facebook login»: esas son otras puertas.

**Opción B — una app nueva** (recomendada si la otra es de la agencia):
1. **Mis apps › Crear app** ⚠.
2. Caso de uso: **Otro** ⚠ › tipo de app: **Negocio** («Business») ⚠.
3. Nombre: `D'CASA Instagram`; correo: `info@dcasapty.com`; portafolio: **DCasa Pty**.
4. En el panel de la app nueva, producto **Instagram** › **Configurar** ⚠. Meta agrega solo «API setup with Instagram
   login».

#### Paso 3. Agregar @dcasapty y generar la llave

1. **Instagram › API setup with Instagram login › 1. Generate access tokens** ⚠ › **Add account** / «Agregar cuenta» ⚠.
2. Se abre Instagram: entra **como @dcasapty** y acepta los permisos (mensajes y lo básico).
3. Si Meta pide que la cuenta sea **evaluadora de Instagram** ⚠: **Roles de la app › Roles › Agregar personas ›
   Evaluador de Instagram** («Instagram Tester») ⚠ › escribe `dcasapty`. Después, en el navegador, entra a Instagram como
   @dcasapty y abre `https://www.instagram.com/accounts/manage_access/` › **Invitaciones de evaluador** («Tester
   Invites») ⚠ › **Aceptar** (el botón puede verse gris y aun así funciona). Vuelve al punto 1.
4. Al lado de @dcasapty: **Generate token** / «Generar identificador» ⚠ › entra otra vez como @dcasapty si lo pide ›
   **copia la llave** (empieza casi siempre con `IG`). Esa llave dura **60 días**; Juan la renueva sola, no hay que volver
   a sacarla mientras Juan siga encendido.
5. En esa misma fila, enciende **Webhook subscription** / «Suscripción a webhooks» ⚠ para @dcasapty. Sin esto Meta no le
   avisa a Juan de los mensajes de esa cuenta.

#### Paso 4. La clave secreta de la app de Instagram

**Instagram › API setup with Instagram login › 3. Set up Instagram business login › Business login settings** ⚠ ›
**Instagram app secret** / «Clave secreta de la app de Instagram» ⚠ › **Mostrar** › cópiala.

> **Ojo:** NO es la «Clave secreta de la app» de *Configuración de la app › Básica* (esa es la de Facebook, la que ya
> tiene Juan como `META_APP_SECRET`). Son dos claves distintas; si se confunden, Juan rechaza los mensajes (sale «firma
> inválida» en los registros).

Si para ver la clave Meta te pide llenar «Business login settings» ⚠: como **OAuth redirect URI** pon
`https://dcasapty.com/`; como **Deauthorize callback URL** y **Data deletion request URL**,
`https://dcasapty.com/privacidad` ⚠. Guardar. (Juan no usa ese inicio de sesión: la llave del paso 3 basta.)

#### Paso 5. Pegar en Cloudflare (nunca en el chat)

**Cloudflare › Workers & Pages › `dcasa-juan` › Settings › Variables and Secrets › Add** ⚠ › tipo **Secret**:

| Nombre exacto | Valor |
|---|---|
| `INSTAGRAM_TOKEN` | La llave del paso 3 |
| `INSTAGRAM_APP_SECRET` | La clave secreta de la app de Instagram del paso 4 |

- **No borres** `META_PAGE_TOKEN`, `META_APP_SECRET` ni `META_VERIFY_TOKEN`: los usan Messenger y WhatsApp.
- `INSTAGRAM_ACCOUNT_ID` **no hace falta**: Juan averigua la cuenta solo. Solo si `/salud` dice «todavía no sé cuál es la
  cuenta de Instagram de D'CASA» se agrega (tipo *Text*, **solo números**) con el número de la cuenta de @dcasapty que
  muestra Meta al lado de la cuenta en el paso 3 ⚠. Si se pone mal, Juan lo ignora o lo avisa en `/salud`; no tira
  mensajes.
- Al guardar el primero de los dos, **Instagram pasa a esta puerta** (Messenger no cambia). Para volver como estaba,
  basta borrar `INSTAGRAM_TOKEN` e `INSTAGRAM_APP_SECRET`.
- **Va antes del webhook (paso 6):** sin `INSTAGRAM_APP_SECRET` puesta, Juan no deja verificar la dirección nueva (así
  Meta no la da por buena antes de que Juan pueda comprobar sus avisos).

#### Paso 6. El webhook (la dirección nueva)

1. **Instagram › API setup with Instagram login › 2. Configure webhooks** ⚠ › **Configure** / «Configurar» ⚠.
2. **Callback URL:** `https://dcasa-juan.dcasapty.workers.dev/webhooks/instagram` (ojo: termina en **/instagram**, no en
   /meta).
3. **Verify token:** el **mismo valor** de `META_VERIFY_TOKEN`.
4. **Verify and save** / «Verificar y guardar» ⚠. Si sale error: revisa que el valor sea idéntico (sin espacios) y que
   `INSTAGRAM_APP_SECRET` ya esté en Cloudflare (paso 5).
5. En la lista de campos («Webhook fields») ⚠, que estén suscritos **`messages`** y, si aparece aparte,
   **`message_echoes`** (con este se guarda en Odoo lo que una vendedora conteste desde la app de Instagram). Los demás
   (`comments`, `messaging_seen`, reacciones…) pueden quedar: Juan los ignora.

#### Paso 7. Poner la app «En vivo»

Meta solo manda los avisos de clientes reales con la app **publicada / En vivo** ⚠.
1. **Configuración de la app › Básica** ⚠: **URL de la política de privacidad** `https://dcasapty.com/privacidad`;
   **URL de eliminación de datos** (o «instrucciones») `https://dcasapty.com/privacidad` ⚠; **ícono** (el logo de
   D'CASA, 1024 × 1024); **categoría** (p. ej. «Negocios y páginas» o «Compras») ⚠; correo de contacto
   `info@dcasapty.com`. Guardar.
2. Arriba, el interruptor **Modo de la app: Desarrollo → En vivo** ⚠ (o «Publicar»). Si Meta pide algo más (verificación
   del negocio o revisión de la app) **anótalo tal cual** y avisa: eso decide si esta puerta alcanza o hay que ir a la
   revisión.
3. No pidas «acceso avanzado» ni la revisión todavía: primero se prueba si con el acceso estándar llegan los mensajes
   (para una app que solo atiende la cuenta propia, Meta dice que basta el estándar).

#### Paso 8. Revisar `/salud`

Abre `https://dcasa-juan.dcasapty.workers.dev/salud` y mira `canales › instagram`:

- `"puerta": "inicio_sesion_instagram"` y `"faltan": []`.
- `"cuenta": "@dcasapty"` (aparece al primer mensaje o en el siguiente cron, a los 23 minutos de cada hora).
- `"llave"`: `vence` (una fecha unos 60 días adelante), `renovacion: "pendiente"` el primer día y `"ok"` desde el día
  siguiente (Juan la renueva en cuanto Meta lo permite). **Nunca** sale la llave.
- `"suscripcion": "ok"` si Meta deja consultarla (si no aparece, Meta no la dejó ver: no es un error). Si dice `"no"`,
  vuelve al paso 3.5.
- Lo que haya que arreglar sale en `mensaje` (y por Telegram, si está configurado), con palabras:
  - «**Meta rechaza la llave de Instagram** … desde el …»: la llave pegada no sirve (vencida, revocada o mal copiada):
    genera otra (paso 3.4) y pégala encima de `INSTAGRAM_TOKEN`. Mientras tanto los mensajes llegan a Odoo, pero Juan no
    puede contestar.
  - «no se pudo renovar la llave…»: Juan lo reintenta cada día; con 7 días o menos para que venza pasa a ser un problema.
  - «todavía no sé cuál es la cuenta de Instagram de D'CASA»: Meta no contestó a Juan con esa llave; mientras tanto Juan
    atiende lo que Meta le firma. Revisa la llave o agrega `INSTAGRAM_ACCOUNT_ID` (paso 5).
  - «se ignoran avisos de Instagram de otra cuenta (…1234)»: llegan mensajes de una cuenta que Juan no reconoce como la
    de D'CASA (`ignorados` dice cuántos y cuándo). Si esa sí es la de D'CASA, borra o corrige `INSTAGRAM_ACCOUNT_ID`.

#### Paso 9. Probar con una cuenta que NO tenga ningún papel

La prueba de verdad es con alguien que **no** sea administrador, desarrollador ni evaluador de la app, **ni** esté en el
portafolio DCasa Pty **ni** en el de Juancito Ads (por ejemplo, el Instagram personal de un familiar o una cuenta nueva).
Las pruebas del 9 y 10 nov engañaron justamente por usar cuentas con papel.

1. Desde esa cuenta, escríbele a @dcasapty: «Hola, ¿tienen sofás?».
2. Debe pasar, en segundos: Juan contesta en Instagram, y en **Odoo › Conversaciones** aparece la conversación de
   **Instagram** con el nombre (o el @usuario) de esa persona y los dos mensajes.
3. Desde la app de Instagram (como @dcasapty) contesta algo a mano: en Odoo debe salir como de la **vendedora** y Juan se
   calla en esa conversación.
4. Si no pasa nada, en **Cloudflare › `dcasa-juan` › Logs** ⚠ busca `POST /webhooks/instagram`:
   - **No aparece ninguno:** Meta no está mandando los mensajes de clientes reales → con el acceso estándar no alcanza
     (o falta el paso 3.5 o el paso 7). Anotarlo: el siguiente camino es la revisión de la app.
   - **Aparece con 401:** la clave del paso 4 no es la correcta (¿se pegó la de Facebook?).
   - **Aparece con 200 pero no hay nada en Odoo:** mira `/salud` (paso 8: ¿«otra cuenta»?) y que Instagram esté encendido
     en Odoo (*Ajustes de Juan › «Dónde contesta»*).

#### Bueno saber

- Juan solo puede escribir dentro de las **24 horas** del último mensaje del cliente (regla de Meta).
- Por esta puerta Juan sí puede mandar la **cotización en PDF**; si Instagram no la acepta, manda el enlace, como antes.
- Un cliente que ya había escrito por la puerta vieja debería seguir en la **misma conversación** de Odoo (Meta dice que
  el número que identifica al cliente es el mismo en todas las apps). Si no fuera así, ese cliente aparecería **una vez**
  como conversación nueva; como a los clientes reales nunca les llegó nada por la página, solo pasaría con las cuentas de
  prueba.

## 3c. Comentarios de Instagram y Facebook (2026-11-13, apagado de fábrica)

Pedido de la dueña: «También me interesa el tema de los comentarios por Instagram o Facebook». Decisiones (tal cual):
«Solo los que preguntan», «Corto y lo demás por privado», «Apagado hasta que lo pruebes».

- **Qué hace Juan:** solo responde comentarios que preguntan (precio, medidas, colores, si hay, envío, ganas de
  comprar). Primero manda **una** respuesta privada (Meta permite una por comentario, dentro de 7 días) con la respuesta
  completa, armada con las mismas herramientas y la misma guardia de un mensaje normal; solo si la privada salió, pone en
  público la frase de Ajustes («¡Hola! Te escribimos por mensaje directo con los detalles.»). Lo público **nunca lleva
  el nombre** de quien comenta (decisión técnica tras la revisión: nadie puede usar su nombre o usuario para hacerle
  decir algo a la cuenta de D'CASA). No contesta etiquetas, emojis, saludos ni elogios. **Las quejas no se contestan:**
  quedan en el hilo y avisan a Gerencia por Telegram (como mucho un aviso por persona cada 24 h). Una pregunta con
  palabras de queja puede recibir la privada, pero nunca la pública. Si una vendedora ya atiende a esa persona, Juan no
  se mete.
- **Topes:** respuestas públicas por hora (30), por persona 1 pública y 3 privadas cada 24 h, y 60 privadas por hora en
  total.
- **Dónde se enciende:** Conversaciones › Configuración › Ajustes de Juan › «Comentarios de Instagram y Facebook»
  (Gerencia y administradores). Hace falta además el canal donde seguiría la conversación (Messenger para Facebook,
  Instagram para Instagram).
- **Cómo llegan:** campo `feed` de la página (Facebook) y `comments` (Instagram, por la página o por la segunda puerta),
  por los mismos webhooks. Solo se atienden los de la página y el Instagram de D'CASA (Juan lo averigua con `GET /me`;
  variable opcional `META_PAGE_ID` de respaldo). Cada comentario atendido queda en la conversación de esa persona con
  «Ver la publicación».
- **Igual que los mensajes, Meta solo los manda con la app aprobada** (acceso avanzado): hasta entonces, solo los de
  cuentas con papel. Permisos a pedir en la misma revisión: `pages_manage_engagement`, `pages_read_engagement`,
  `pages_read_user_content` (Facebook) e `instagram_manage_comments` / `instagram_business_manage_comments` (Instagram).
- **Por comprobar en la primera prueba real:** que el `recipient_id` de la privada sea el mismo que el `from.id` del
  comentario (`/salud` avisa si no) y que Meta acepte una segunda privada a la misma persona en otro comentario.

## 4. El puente de WhatsApp por QR (no se usa en producción)

`puente-wa/` es un Worker con su contenedor (Baileys) que mantiene una sesión de WhatsApp por QR, como un WhatsApp Web
en un servidor. Funciona y tiene sus pruebas, pero **no es una conexión oficial** (WhatsApp podría bloquear el número) y
**nunca se desplegó** en producción: desde el 2026-11-02 WhatsApp va por la API oficial. Queda como alternativa para otra
instalación o como plan de emergencia.

- Guía completa, seguridad de la sesión, copias y rotación de claves: [JUAN_PUENTE.md](JUAN_PUENTE.md) (se queda aparte
  porque el código y los flujos del puente la citan).
- Contrato con Juan (rutas y campos): [JUAN.md › Contrato Worker `juan` ↔ puente QR](JUAN.md#contrato-worker-juan--puente-qr-puente-wa).
- **Conectarlo a Juan**, si un día se usa:
  1. Publicar primero el puente (*Actions › Desplegar puente de WhatsApp*): Cloudflare rechaza un binding a un Worker que
     no existe.
  2. En `juan/wrangler.jsonc`, quitar el `//` de `{ "binding": "PUENTE", "service": "dcasa-puente-wa" }` (y de la línea
     de `env.staging`) y volver a desplegar Juan.
  3. Pegar `WA_TOKEN` (el mismo valor) en Juan y en el puente.
  4. `/salud` debe mostrar `whatsapp_qr` con `configurado: true`; en Odoo, *Conexiones* muestra el QR para vincular el
     teléfono.
- Mientras el puente no exista, `/salud` muestra el canal QR como «le falta PUENTE» y el resto de Juan funciona igual.
- **Citas, reacciones y palomitas: no** (2026-11-07). El puente no pasa hoy esos datos (su contrato `construirWebhook` no
  tiene cita, reacción ni recibos) y agregarlos es trabajo en el contenedor de Baileys, que no está en producción. Si un día
  se usa, se agregan al contrato del puente y Juan los traduce a `cita`, `reenviado` y `eventos` como en WhatsApp oficial.
