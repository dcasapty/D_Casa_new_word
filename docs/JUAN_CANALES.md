# Los canales de Juan: WhatsApp, Telegram, Messenger e Instagram

Puesto al día el 2026-11-06. Por dónde le escriben los clientes a Juan y cómo se conecta cada canal. Cómo funciona Juan por
dentro: [JUAN.md](JUAN.md). Lo que ve el equipo en Odoo: [JUAN_ODOO.md](JUAN_ODOO.md).

Cada canal es un adaptador del Worker `dcasa-juan` (`juan/src/canales/`) y se enciende o se apaga en Odoo, en
*Conversaciones › Configuración › Ajustes de Juan › «Dónde contesta»*. Las claves **nunca** se mandan por chat (ni a
Claude): se pegan directo en Cloudflare (*Workers & Pages › `dcasa-juan` › Settings › Variables and Secrets*). Para saber
qué clave falta, abre `https://dcasa-juan.dcasapty.workers.dev/salud`: muestra solo **nombres**, nunca valores.

| Canal | Estado (2026-11-06) | Webhook en `dcasa-juan` |
|---|---|---|
| **WhatsApp por la API oficial de Meta** (`whatsapp_cloud`) | **En producción desde el 2026-11-02**, con el número de la tienda (+507 6026-1919) | `/webhooks/whatsapp-cloud` |
| **Telegram** (`telegram`) | Funciona: canal de pruebas y avisos al equipo | `/webhooks/telegram` |
| **Messenger e Instagram** (`messenger`, `instagram`) | Código listo y probado; **sin conectar** | `/webhooks/meta` |
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

### Si deja de contestar

1. Abre `/salud` de Juan: en `whatsapp_cloud`, `"faltan"` tiene que salir vacío.
2. Si `/salud` está bien y aun así no contesta: casi siempre es la llave. Revisa que `WHATSAPP_CLOUD_TOKEN` sea la
   permanente de `juan-bot` (no una del Explorador) y, si hace falta, genera otra en Meta Business › Usuarios del sistema ›
   `juan-bot` › Generar token ⚠, con los dos permisos de arriba, y pégala en Cloudflare.
3. En Odoo, *Conversaciones › Conexiones* muestra el estado de cada canal y el último problema de envío.

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

## 3. Messenger e Instagram (por conectar)

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
