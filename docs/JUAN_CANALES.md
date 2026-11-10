# Los canales de Juan: WhatsApp, Telegram, Messenger e Instagram

Puesto al día el 2026-11-06. Por dónde le escriben los clientes a Juan y cómo se conecta cada canal. Cómo funciona Juan por
dentro: [JUAN.md](JUAN.md). Lo que ve el equipo en Odoo: [JUAN_ODOO.md](JUAN_ODOO.md).

Cada canal es un adaptador del Worker `dcasa-juan` (`juan/src/canales/`) y se enciende o se apaga en Odoo, en
*Conversaciones › Configuración › Ajustes de Juan › «Dónde contesta»*. Las claves **nunca** se mandan por chat (ni a
Claude): se pegan directo en Cloudflare (*Workers & Pages › `dcasa-juan` › Settings › Variables and Secrets*). Para saber
qué clave falta, abre `https://dcasa-juan.dcasapty.workers.dev/salud`: muestra solo **nombres**, nunca valores.

| Canal | Estado (2026-11-09) | Webhook en `dcasa-juan` |
|---|---|---|
| **WhatsApp por la API oficial de Meta** (`whatsapp_cloud`) | **En producción desde el 2026-11-02**, con el número de la tienda (+507 6026-1919). Desde el 2026-11-09 16:00 **no sale nada** (código 131070 y el número sin «cuenta de mensajes»): lo arregla la dueña en Meta, ver §1 «131070» | `/webhooks/whatsapp-cloud` |
| **Telegram** (`telegram`) | Funciona: canal de pruebas y avisos al equipo | `/webhooks/telegram` |
| **Messenger** (`messenger`) | **Conectado el 2026-11-09** (página DCASA PTY): probado de punta a punta. Hasta la revisión de Meta solo contesta a quien tiene rol en la app | `/webhooks/meta` |
| **Instagram** (`instagram`) | Código listo; **por conectar** (faltan los permisos de Instagram en la app y el acceso al portafolio DCasa Pty, ver §3) | `/webhooks/meta` |
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

   **La causa más probable (2026-11-10): el «Enrutamiento de conversaciones»** (Conversation Routing, de Meta desde
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

## 3. Messenger e Instagram (Messenger conectado el 2026-11-09; Instagram por conectar)

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
  (`filedata`, multipart, hasta 25 MB); si Juan no logra bajarlo, va por URL como antes. Instagram no acepta archivos
  subidos: sigue por URL (si falla igual, ver ahí).
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
