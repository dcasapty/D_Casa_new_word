# Correo a clientes (Resend)

Módulo `dcasa_correo`. Puesto al día el 2026-10-17.

## 1. Qué hace y qué no

Cuando esté encendido, a cada cliente le llega:

| Correo | Cuándo | Qué lleva |
|---|---|---|
| **Su factura** | En cuanto alguien registra un pago de su factura (el botón «Pagar», Brian o la conciliación del banco) | El PDF de la factura con lo pagado hasta ese momento. Si todavía debe algo, el correo dice **«pagaste $X, te falta $Y, vence el …»** y cada abono con su fecha. Si quedó pagada, cuántos puntos sumó |
| **La bienvenida** | Una sola vez, con el primer pago, **solo a clientes nuevos** | Cómo entrar a Mi cuenta (con su celular y su PIN, o con su correo si compró en la tienda en línea), dónde ver lo que le falta de un abono y cómo funcionan sus puntos. Las cifras de los puntos salen solo de `puntos.json` |
| **La factura cuando la mandas tú** | Abres la factura › «Enviar» › dejas marcada la casilla de correo | La factura con la marca D'CASA |
| **La cotización** | Abres la venta › «Enviar», o en Conversaciones › Cotización › **«Enviar por correo»** | La cotización en PDF |
| **El correo de prueba** | Ajustes › Correo a clientes › «Enviar correo de prueba» | Te llega a ti, para ver cómo se ve |

Todos salen con el logo, la banda azul y un solo botón amarillo **«Escríbenos por WhatsApp»**, desde
**D'CASA Panamá &lt;ventas@dcasapty.com&gt;**. Si el cliente contesta, la respuesta llega a **info@dcasapty.com**.

Lo que **no** hace:

- **No manda nada mientras no lo enciendas.** Viene apagado, y sin la clave de Resend no sale ningún correo.
- **Nunca hace fallar un pago.** El correo se prepara después; si Resend no responde, el pago queda igual y el correo se
  reintenta solo.
- **No manda la bienvenida a los clientes de antes.** Cuentan como nuevos los clientes que se crean desde que se instaló
  el correo (la fecha se ve en Ajustes). Los que vinieron del sistema anterior o tienen facturas viejas cargadas, nunca.
- **No manda los correos automáticos de Odoo** (confirmación de un pedido web, pago recibido, carrito abandonado). Están
  bloqueados hasta que tú digas que sí.
- **Staging nunca le escribe a un cliente**, aunque sea una copia con todo encendido. Ahí solo sale la prueba.
- Ningún enlace del correo abre la factura sin permiso: el cliente entra a Mi cuenta con su celular y su PIN.

## 2. La cuenta de Resend y la clave

Resend es el servicio que entrega los correos. **Antes de encender, mira en Resend qué plan tienes y cuántos correos
por día y por mes deja.** Cada pago manda uno o dos correos (la factura y, la primera vez, la
bienvenida).

1. Entra a **resend.com** y crea la cuenta con **tu** correo (el de la dueña). Ese correo importa: mientras el dominio
   no esté verificado, Resend solo deja mandar correos de prueba a ese correo.
2. En Resend, menú **API Keys** › **Create API Key**:
   - Nombre: `Odoo produccion`.
   - Permiso: el que dice **solo envío** (*Sending access*), no el de acceso completo.
   - Copia la clave que muestra (empieza con `re_`). **Solo se ve una vez.** Guárdala en tu gestor de contraseñas.
3. Haz otra igual con el nombre `Odoo staging` (para probar sin tocar producción).
4. **Nunca la pegues en el chat, en Odoo ni en un correo.** Solo va en GitHub (paso 3).

## 3. Dónde se pega la clave

**En GitHub**, una vez por entorno:

1. Entra al repositorio en GitHub › **Settings** (arriba a la derecha) › en el menú de la izquierda, **Environments**.
2. Toca **production** › en **Environment secrets**, **Add environment secret**:
   - **Name**: `RESEND_API_KEY` (así, con mayúsculas y guiones bajos).
   - **Value**: la clave `Odoo produccion` del paso 2.
   - **Add secret**.
3. Vuelve a **Environments**, toca **staging** y haz lo mismo con la clave `Odoo staging`.

**En Cloudflare no se pega nada para la clave.** Cada despliegue la sube sola al Worker y de ahí llega a Odoo. Si
quieres comprobar que llegó (después del despliegue): Cloudflare › **Workers & Pages** › `dcasa` (o `dcasa-staging`) ›
**Settings** › **Variables and Secrets**: tiene que aparecer `RESEND_API_KEY` (el valor no se ve, y está bien). No la
pegues también ahí: el siguiente despliegue la reemplaza con la de GitHub.

**Para que entre**, hace falta un despliegue: staging se despliega cuando se pida; producción, con tu «sí», como siempre.
Después, en Odoo › Ventas › Configuración › **Correo a clientes**, el «Estado» dice **«Clave cargada (…xxxx)»** con las
cuatro últimas letras de tu clave.

## 4. La prueba (todavía sin dominio)

Mientras `dcasapty.com` no esté verificado en Resend, Resend solo deja mandar desde `onboarding@resend.dev` y solo al
correo dueño de la cuenta. Para probar:

1. Revisa que tu usuario de Odoo tenga **el mismo correo de tu cuenta de Resend** (tu perfil › Mis preferencias).
2. Odoo › Ventas › Configuración › **Correo a clientes**. En **Remitente** pon por ahora `onboarding@resend.dev` y
   guarda.
3. Toca **«Enviar correo de prueba»**. Te tiene que llegar «Correo de prueba de D'CASA». Ábrelo **en el celular**: tiene
   que verse el logo, el azul y el botón amarillo de WhatsApp. Si no llega, mira también en spam.
4. Si sale un error, la pantalla lo dice con las palabras de Resend (por ejemplo, que el dominio no está verificado).
5. **El interruptor «Enviar correos a clientes» se queda apagado.** Sin dominio, a los clientes no les llegaría.

## 5. Cuando el dominio pase a Cloudflare

1. En Resend › **Domains** › **Add Domain** › escribe `dcasapty.com`.
2. Resend te muestra una lista de registros DNS (para que los correos no lleguen a spam: SPF, DKIM y el de rebotes).
   Cópialos **exactamente como los muestra Resend** en Cloudflare › tu dominio `dcasapty.com` › **DNS** › **Records** ›
   **Add record**: el tipo, el nombre, el contenido y la prioridad si la pide. En cada uno, el «Proxy status» va en
   **DNS only** (la nube gris). Si Resend ofrece configurarlo solo con Cloudflare, usa eso: es lo mismo, sin copiar a
   mano.
3. Si Resend también te muestra un registro DMARC (su nombre es `_dmarc` y su contenido empieza con `v=DMARC1`), cópialo
   igual, tal cual.
4. En Resend toca **Verify** y espera a que el dominio diga **Verified** (puede tardar un rato).

### Recibir en info@dcasapty.com

Las respuestas de los clientes van a `info@dcasapty.com`. Si hoy ese correo no recibe en ningún lado, Cloudflare puede
reenviarlo gratis a tu Gmail:

1. **Antes**, revisa si `info@dcasapty.com` ya recibe correo en otro lado (el sistema viejo o el hosting): encender esto
   cambia por dónde llega el correo del dominio y aquello dejaría de recibir.
2. Cloudflare › tu dominio › **Email** › **Email Routing** › actívalo. Cloudflare agrega solo sus registros.
3. Crea la dirección `info` y que reenvíe a tu Gmail. Cloudflare te manda un correo para confirmar ese Gmail: ábrelo y
   confirma.

## 6. Encender

En Odoo › Ventas › Configuración › **Correo a clientes**:

1. **Remitente**: `ventas@dcasapty.com` (no necesita buzón). **Nombre**: `D'CASA Panamá`. **Las respuestas llegan a**:
   `info@dcasapty.com`. Guarda.
2. **«Enviar correo de prueba»** otra vez: ahora sale desde `ventas@dcasapty.com`.
3. Revisa el tope de tu plan de Resend (paso 2).
4. Marca **«Enviar correos a clientes»** y guarda. Desde ese momento, cada pago manda su factura.

Las otras dos casillas vienen marcadas: **«Mandar la factura al registrar un pago»** y **«Bienvenida a clientes
nuevos»**. Desmárcalas si no quieres alguno de los dos.

**Ojo, con el correo encendido también salen los correos de acceso de Odoo**: al crear un usuario que tenga correo le
llega de verdad la invitación para elegir su clave, y «Cambiar contraseña» o «Olvidé mi contraseña» mandan su correo
(Mi cuenta los necesita para quien entra con su correo). Hoy, sin correo, no le llega nada a nadie (docs/EQUIPO.md).

Para apagarlo todo de un golpe: desmarca **«Enviar correos a clientes»**. Lo que estaba por salir ya no sale (queda
anotado «Se apagaron los correos antes de enviarlo»).

## 7. Si algo falla

- **Ventas › Configuración › Correos a clientes (enviados)** (Gerencia y administradores): cada correo, a quién, si
  salió y, si no, por qué. Los filtros «Por enviar», «Enviados» y «No enviados» ayudan a encontrarlos.
- **«Falta el correo de … o está mal escrito»**: corrige el correo en la ficha del cliente. Queda también una nota en la
  factura. La bienvenida se vuelve a intentar con su siguiente pago.
- **Resend no respondió o pidió esperar**: Odoo lo reintenta solo (a los 5, 15, 60 y 240 minutos, hasta 5 veces).
- **Resend lo rechazó** (por ejemplo, un correo que no existe): no se reintenta; corrige el correo y mándalo de nuevo
  desde la factura con «Enviar».
- **En staging** nunca le llega nada a un cliente: es a propósito.

## 8. Para quien programa

- **La clave** viene solo de la variable `RESEND_API_KEY`: secreto de GitHub › `.github/scripts/secretos_despliegue.sh`
  › Worker (`VARIABLES_DEL_CONTENEDOR`) › contenedor › Odoo. Nunca en `ir.config_parameter`, en un campo, en un log ni en
  una respuesta (hay pruebas que lo revisan en la base y en los logs). Sin ella, `ir.mail_server._connect__` se comporta
  exactamente como Odoo.
- **Transporte** (`models/resend.py`, puro): `SesionResend` hace de conexión SMTP y manda `POST
  https://api.resend.com/emails` con `Idempotency-Key`. 429, 5xx y sin red → `DCASA_REINTENTAR:` (cron cada 15 min);
  la política → `DCASA_NO_ENVIADO:`. Nunca lanza `SMTPServerDisconnected`.
- **Política** (`models/politica.py`): cada `mail.mail` lleva `X-Dcasa-Clase` (factura, abono, bienvenida, cotizacion,
  documento, acceso, prueba u odoo). La prueba solo sale a correos del equipo; apagado o en staging no sale nada más;
  `odoo` nunca.
- **Gancho del pago** (`models/account_move_line.py`): `_reconcile_pre_hook`/`_reconcile_post_hook`, en un savepoint,
  solo encola en `dcasa.correo.envio` (único por `(tipo, huella)`; huella `factura:saldo en centavos`). El cron
  `ir_cron_dcasa_correo_cola` arma el PDF nuevo y publica en el chatter con `layout_correo`; la cola de Odoo lo manda.
  Contexto `dcasa_sin_correo_auto`: no encola. Contexto `dcasa_correo_sin_token`: sin `access_token`.
- **Parámetros**: `dcasa_correo.remitente`, `.nombre`, `.responder_a`, `.enviar_a_clientes` (apagado),
  `.al_pagar` y `.bienvenida` (encendidos al instalar), `.bienvenida_desde` (fecha de instalación: quién es nuevo).
- **Brian**: `enviar_factura_por_correo` y `enviar_cotizacion_por_correo` (ver docs/BRIAN.md).
- **Por confirmar en la primera prueba real en staging**: que Resend acepte la cabecera `Idempotency-Key` y los nombres
  de los campos del JSON, y cómo se ve el correo en Gmail en el celular.
