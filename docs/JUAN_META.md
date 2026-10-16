# Conectar Facebook (Messenger) e Instagram a Juan

Guía para la dueña (2026-10-16). El código ya está listo y probado (`juan/src/canales/meta.ts`): falta lo que solo se
hace en las cuentas de Meta, Cloudflare y Odoo. Al terminar, Juan contesta los mensajes de la página de Facebook y del
Instagram de D'CASA y todo queda en **Odoo › Conversaciones**, igual que WhatsApp.

> **Honestidad:** Meta cambia los nombres de sus pantallas seguido. Donde dice ⚠, el botón puede llamarse un poco
> distinto: busca el más parecido. Las claves **nunca** se mandan por chat (ni a Claude): se pegan directo en
> Cloudflare.

## Antes de empezar

1. Tu Facebook personal es **administrador** de la página de D'CASA y del portafolio de negocios (Meta Business) de
   D'CASA.
2. El Instagram de D'CASA es **cuenta profesional** y está **conectado a la página** de Facebook (Meta Business Suite ›
   Configuración › Cuentas de Instagram ⚠).
3. En la app de Instagram, con la cuenta de D'CASA: Configuración › Mensajes y respuestas a historias › Herramientas
   conectadas › **Permitir el acceso a los mensajes** ⚠. Sin esto, Instagram no le pasa los mensajes a Juan.
4. Abre `https://dcasapty.com/privacidad` y confirma que carga (Meta pide esa dirección).

## 1. Crear la app en Meta

1. [developers.facebook.com](https://developers.facebook.com) › **Mis apps** › **Crear app**.
2. Nombre: `D'CASA Juan`. Correo: `info@dcasapty.com`.
3. Caso de uso: **Interactuar con los clientes en Messenger** ⚠. Si deja agregar otro, agrega también el de
   **mensajes de Instagram** ⚠.
4. Portafolio de negocios: el de **D'CASA Panamá** › **Crear app**.

## 2. Datos básicos (Meta los exige)

Configuración de la app › **Básica**:

* URL de la política de privacidad: `https://dcasapty.com/privacidad` (también sirve para «eliminación de datos»: dice
  cómo pedir que se borren).
* Ícono: el logo de D'CASA (1024 × 1024). Categoría: Compras / Empresas ⚠. **Guardar cambios**.
* Ahí mismo está la **Clave secreta de la app** (botón «Mostrar»): es `META_APP_SECRET`.

## 3. Las tres claves, en Cloudflare

Cloudflare › **Workers & Pages** › `dcasa-juan` › **Settings** › **Variables and Secrets** › **Add**, tipo **Secret**:

| Nombre | Qué pegar |
|---|---|
| `META_APP_SECRET` | La clave secreta de la app (paso 2). |
| `META_VERIFY_TOKEN` | Una contraseña que **inventas tú**: 24 a 64 letras y números, sin espacios ni símbolos. Anótala: va otra vez en el paso 5. |
| `META_PAGE_TOKEN` | La llave de la página (sale en el paso 4: vuelve aquí a pegarla). |

## 4. Conectar la página y sacar su llave

En la app: Casos de uso › Messenger › **Personalizar** › **Configuración de la API de Messenger** ⚠.

1. En «Generar tokens de acceso»: **Conectar** (o «Agregar página») › elige la página de D'CASA › acepta los permisos.
2. Al lado de la página: **Generar** › copia el token (es largo) › pégalo en Cloudflare como `META_PAGE_TOKEN`.

## 5. El webhook (por dónde Meta le avisa a Juan)

En la misma pantalla, «Configurar webhooks»:

* URL de devolución de llamada: `https://dcasa-juan.dcasapty.workers.dev/webhooks/meta`
* Token de verificación: la contraseña que inventaste para `META_VERIFY_TOKEN`.
* **Verificar y guardar**. Si da error: revisa que `META_VERIFY_TOKEN` esté guardado en Cloudflare igualito (sin
  espacios).
* Al lado de la página: **Agregar suscripciones** › marca `messages`, `message_echoes` y `messaging_postbacks` ›
  Guardar.

## 6. Instagram

En el caso de uso de Instagram (o «Configuración de la API de Messenger para Instagram») ⚠:

* Conecta la cuenta de Instagram de D'CASA.
* Webhook: la **misma** URL y el **mismo** token de verificación del paso 5. Suscribe el campo `messages`.
* No hace falta otra llave: Juan contesta Instagram con la llave de la página.

## 7. Revisar que Juan ve las claves

Abre `https://dcasa-juan.dcasapty.workers.dev/salud`. En `messenger` e `instagram`, `"faltan"` debe salir vacío
(`[]`). Si sale un nombre, ese falta en Cloudflare. Esa página nunca muestra las claves, solo los nombres.

## 8. Encender en Odoo

Odoo › **Conversaciones › Configuración › Ajustes de Juan** › «Dónde contesta»: marca **Messenger** e **Instagram** ›
Guardar.

## 9. Probar (antes de que Meta apruebe la app)

Hasta la aprobación, Meta solo deja contestarle a quien tiene **rol en la app** (tú y quien agregues en Roles de la
app › Probadores ⚠).

* Desde tu Facebook personal, escríbele «hola» a la página de D'CASA: Juan contesta y la conversación aparece en Odoo.
* Instagram: escribe desde una cuenta de Instagram de alguien con rol en la app.

## 10. Pedir la aprobación (para que conteste a todos los clientes)

1. **Verificación del negocio**, si no está hecha: Meta Business › Configuración del negocio › Centro de seguridad ›
   Verificación del negocio, con los documentos de la empresa (RUC). Puede tardar días.
2. App › **Revisión de la app › Permisos y funciones**: pide **acceso avanzado** para `pages_messaging`,
   `pages_manage_metadata`, `instagram_manage_messages`, `instagram_basic` y `pages_show_list` (Meta puede pedir
   también `business_management`). ⚠ Si pide otro distinto, se revisa antes de seguir.
3. Por cada permiso: el texto de abajo y un video corto de la pantalla (un cliente escribe a la página › Juan contesta
   › la conversación en Odoo).
4. Enviar. Cuando aprueben: poner la app **En vivo** (Publicar) ⚠.

Texto para Meta:

> D'CASA Panamá es una tienda de muebles en La Chorrera, Panamá. Usamos este permiso para recibir y responder los
> mensajes que los clientes nos escriben a nuestra página de Facebook y a nuestro Instagram, con nuestro asistente y
> nuestras vendedoras desde nuestro sistema (Odoo). Solo respondemos a quien nos escribe, dentro de las 24 horas de su
> último mensaje.

## Bueno saber

* Juan solo puede contestar dentro de las **24 horas** del último mensaje del cliente (regla de Meta). Pasado eso, se
  contesta desde Meta Business Suite.
* Si una vendedora contesta desde Meta Business Suite o la app, ese mensaje también queda en Odoo.
* Si un día Messenger e Instagram dejan de contestar de golpe y `/salud` está bien: puede ser la llave de la página
  (por ejemplo, tras cambiar la contraseña de Facebook). Se genera otra (paso 4) y se pega en Cloudflare.
* Detalle técnico: webhook `GET/POST /webhooks/meta` (verificación con `META_VERIFY_TOKEN`, firma
  `X-Hub-Signature-256` con `META_APP_SECRET`), envío por la Send API con `META_PAGE_TOKEN`; un canal apagado en Odoo
  contesta 200 y no atiende. Ver `docs/JUAN_WORKER.md` §5.
