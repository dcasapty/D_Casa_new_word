# Plan B de Juan: pasar de WhatsApp por QR a WhatsApp oficial (Meta)

**Para qué sirve este papel.** Hoy Juan atiende WhatsApp por el *puente QR*: es como tener WhatsApp Web abierto en un
servidor. Funciona, es barato y no necesita permiso de nadie, pero **no es una conexión oficial**: WhatsApp podría bloquear el
número si lo considera «automatizado no autorizado». Este plan B es lo que se hace **antes** de que eso pase (o el mismo día,
si pasa). El código ya está escrito y probado con datos de mentira (`juan/src/canales/whatsappCloud.ts`); lo que falta son
cosas que solo la dueña puede hacer en la cuenta de Meta.

> **Honestidad:** Meta no se pudo consultar desde aquí (su sitio de documentación está bloqueado en este entorno). Los pasos
> de abajo son los que se conocen de la plataforma; **cada punto marcado con ⚠ hay que confirmarlo en la pantalla de Meta**
> antes de darlo por cierto. Ningún precio está escrito aquí: Meta publica los suyos y cambian.

## 1. Lo que NO cambia
* Los clientes, las conversaciones, las etiquetas, las notas y todo el historial de Odoo se quedan igual.
* La pantalla Conversaciones es la misma. Cambia solo **por dónde** viaja el mensaje.
* Un cliente y un socio siguen siendo la misma ficha; la llave sigue siendo el celular.

## 2. Lo que SÍ cambia
| | Puente QR (hoy) | WhatsApp oficial (plan B) |
|---|---|---|
| Permiso de WhatsApp | No es oficial | Sí |
| Riesgo de bloqueo del número | Existe | Mucho menor |
| Escribir primero a un cliente | Libre | Solo con **plantilla aprobada por Meta** ⚠ (dentro de las 24 h del último mensaje del cliente sí hay texto libre) |
| La app de WhatsApp en el teléfono | Sigue funcionando | Depende de si el número queda en «coexistencia» ⚠ |
| Costo | Unos centavos al mes de servidor | Meta cobra por conversación/mensaje de plantilla ⚠ (ver precios vigentes en Meta) |
| Seguimientos de Juan (n.º 1 y 2) | Texto libre | Tienen que ser **plantillas aprobadas** |

## 3. Lo que tiene que hacer la dueña (no se puede delegar a Claude)
1. Tener (o crear) una cuenta de **Meta Business** a nombre de D'CASA Panamá, con los datos reales de la empresa
   (RUC 155779346-2-2026 DV7, dirección de La Chorrera). ⚠ Meta pide **verificar el negocio** con documentos: es lo que más tarda
   (días). Conviene empezarlo ya, aunque no se use todavía.
2. Crear en Meta for Developers una *app* de tipo **Empresa** con el producto **WhatsApp**. ⚠
3. Decidir el **número**: 
   * **Opción A, número nuevo** (recomendada para empezar): un número que no esté en la app de WhatsApp. Cero riesgo para el
     actual, y se prueba todo antes de mover a nadie.
   * **Opción B, el número de hoy**: ⚠ Meta tiene un modo de **coexistencia** (la app del teléfono y la API a la vez) y un modo de
     migración que desconecta la app. Disponibilidad por país y requisitos (versión de la app, etc.): confirmar en Meta antes de
     tocar el número de hoy.
4. En el panel de Meta: crear un **usuario del sistema** y un **token permanente** con permisos de mensajería y administración de
   WhatsApp Business ⚠ (el token provisional de prueba vence en horas y **no sirve**).
5. Aprobar las **plantillas** que Juan necesita (hay que escribirlas con Gerencia; sin inventar precios ni promesas):
   un saludo para volver a escribirle a un cliente, y los dos seguimientos. ⚠ La aprobación puede tardar de minutos a un par de días.

## 4. Lo que se carga en Cloudflare (la dueña pega los secretos; no pasan por el chat ni por GitHub)
En el Worker `dcasa-juan` (o `dcasa-juan-staging` para ensayar), *Settings › Variables and Secrets*:

| Nombre | Tipo | De dónde sale |
|---|---|---|
| `WHATSAPP_CLOUD_TOKEN` | Secreto | El token permanente del paso 4 |
| `WHATSAPP_PHONE_NUMBER_ID` | Variable | El «identificador del número» que muestra Meta (no es el celular) |
| `META_APP_SECRET` | Secreto | La «clave secreta de la app» (firma de los avisos de Meta) |
| `META_VERIFY_TOKEN` | Secreto | Una frase larga que **tú inventas** y pones igual en Meta y aquí |

En Meta, en la configuración del webhook de WhatsApp: dirección
`https://<tu-worker>/webhooks/whatsapp-cloud` y el mismo `META_VERIFY_TOKEN`; suscribirse al campo de **mensajes** ⚠.
Si se usa coexistencia, también al de los **ecos** de lo que escribe el equipo desde el teléfono ⚠ (Juan ya sabe tratarlos
como «escrito por una vendedora», pero la forma exacta del aviso **no está verificada contra Meta**: probar con un mensaje real
antes de confiar).

## 5. Encender (en este orden, sin prisa)
1. Pegar los secretos y desplegar (`/salud` debe mostrar `whatsapp_cloud` con `configurado: true`).
2. En Odoo › *Ajustes de Juan*: encender **WhatsApp (API oficial)**. El de QR se deja encendido mientras se prueba.
3. Con el **número nuevo**, escribirle desde tu celular: tiene que llegar a *Conversaciones* y Juan contestar.
4. Probar: texto, una foto, un PDF, una nota de voz, una respuesta tuya desde Odoo, y el «Atender» desde Telegram.
5. Probar que, pasadas 24 h, Juan **no** intente mandar texto libre (debe pedir plantilla o avisarte).
6. Solo entonces: avisar a los clientes del número nuevo, o migrar el número de hoy (opción B) y **apagar** el puente QR en
   *Conversaciones › Conexiones › Desvincular*.

## 6. Si WhatsApp bloquea el número del QR ANTES de tener esto listo
No se pierde nada de Odoo. Mientras tanto: Telegram sigue funcionando; las vendedoras pueden contestar desde la app de WhatsApp
Business en otro teléfono; y se avanza el paso 3 con el número nuevo. Por eso conviene **tener la verificación del negocio
hecha antes** — es lo único que no se puede acelerar el día que se necesita.

## 7. Pendiente de código si se decide pasar a oficial
* Los seguimientos automáticos (n.º 1 y 2) mandan texto libre: con la API oficial tienen que salir como **plantilla**. Hoy el
  adaptador lo sabe (`ventana24h: true`) y no manda fuera de ventana, pero **falta** enviar la plantilla aprobada en su lugar.
  Se hace cuando existan las plantillas del paso 3.5.
* Probar el aviso de «eco» de la coexistencia contra un mensaje real (ver arriba).
