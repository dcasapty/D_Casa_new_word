# Correo a clientes (Resend)

Módulo `dcasa_correo`. Puesto al día el 2026-10-17.

## 1. Qué hace y qué no

Cuando esté encendido, a cada cliente le llega:

| Correo | Cuándo | Qué lleva |
|---|---|---|
| **Su factura o su abono** | En cuanto alguien registra un pago de su factura (el botón «Pagar», Brian o la conciliación del banco) | El PDF nuevo, el mismo papel y el mismo nombre que «Imprimir». **Si todavía debe algo es el correo del abono**: el asunto dice «Recibimos tu abono», el correo dice el total, lo que ya pagó, **lo que le falta** y hasta cuándo tiene, y va el papel de ABONO («Abono INV_…pdf», con SALDO POR PAGAR). **Si quedó pagada es el de la factura pagada** (nunca dice «abono») y, si la compra sumó puntos, cuántos (del libro de Socios). Un botón «Ver en Mi cuenta» |
| **El recordatorio del abono** (D3, desde el 2026-10-22) | **5 días antes** de que venza un abono (la cifra de la gerencia; `dcasa_abonos.aviso_dias`). Lo arma el cron de cada mañana. **Uno solo por abono y vencimiento**: no se repite si el cron corre otra vez, y si el cliente no tenía correo vuelve a intentarse cuando se lo escriban (si sigue dentro del plazo) | «Tu abono vence el dd/mm/aaaa · Factura INV/…»: el total, lo que ya pagó, **lo que le falta** y hasta cuándo (de `_dcasa_estado_abono`, la misma fuente del papel de ABONO). Sin PDF. El botón «Ver en Mi cuenta». Si se paga antes de armarlo, no sale |
| **La bienvenida** | Una sola vez por persona, **solo a clientes nuevos**, cuando ya puede entrar a Mi cuenta (si su primera compra va en abono, con el pago que la termina: su código de socio llega con la factura pagada) | Corta: «¡Te damos la bienvenida, Ana!», «Gracias por tu compra. En Mi cuenta ves tus compras, tus pagos y tus puntos», una línea de cómo entra la primera vez (con PIN: celular y PIN; con cuenta de la tienda en línea: su correo; si no: «¿Primera vez? Hazte socio» con su celular, el código de socio de su factura y un PIN que elige; si su celular no sirve: que escriba por WhatsApp) y el botón «Entrar a Mi cuenta». **Sin reglas de puntos, sin abonos y sin cifras** |
| **La factura cuando la mandas tú** | Abres la factura › «Enviar» › dejas marcada la casilla de correo | La factura con la marca D'CASA |
| **La cotización** | Abres la venta › «Enviar», o en Conversaciones › Cotización › **«Enviar por correo»** | La cotización en PDF |
| **El correo de prueba** | Ajustes › Correo a clientes › «Enviar correo de prueba» | Te llega a ti, para ver cómo se ve |

Todos salen limpios (lo pidió la dueña el 17/10/2026): el logo arriba con la dirección pública del sitio, el titular en
azul, pocas líneas, **un solo botón azul con letra blanca** («Entrar a Mi cuenta» en la bienvenida, «Ver en Mi cuenta» en
la factura y el abono, «Escríbenos por WhatsApp» en la cotización y la prueba), debajo, si el botón no es el de WhatsApp,
solo el enlace de texto **«¿Dudas? Escríbenos por WhatsApp»**, y un pie corto (nombre, dirección y WhatsApp de la
empresa). Sin amarillo, sin degradados ni sombras. Salen desde **D'CASA Panamá &lt;ventas@dcasapty.com&gt;**; si el cliente
contesta, la respuesta llega a **info@dcasapty.com**. (En el correo, el botón principal lleva a Mi cuenta por pedido de
la dueña; WhatsApp sigue siendo el CTA único del sitio.)

Además, **el comprobante de pago de la planilla** (Nómina, desde el 2026-10-22) sale por el mismo camino y con el
mismo interruptor: con los correos apagados, en staging o sin clave, no le llega a nadie (ver [NOMINA.md](NOMINA.md)).

Lo que **no** hace:

- **No manda nada mientras no lo enciendas.** Viene apagado, y sin la clave de Resend no sale ningún correo.
- **Nunca hace fallar un pago.** El correo se prepara después; si Resend no responde, el pago queda igual y el correo se
  reintenta solo.
- **No manda la bienvenida a los clientes de antes.** Cuentan como nuevos los clientes que se crean desde que se instaló
  el correo (la fecha se ve en Ajustes). Los que vinieron del sistema anterior o tienen facturas viejas cargadas, nunca;
  tampoco una ficha nueva a la que se le fusionó la de un cliente de antes (trae sus facturas, ventas o contactos
  viejos). Y si la misma persona tiene dos fichas (repetida o fusionada), le llega una sola.
- **No manda los correos automáticos de Odoo** (confirmación de un pedido web, pago recibido, carrito abandonado). Están
  bloqueados hasta que tú digas que sí.
- **Staging nunca le escribe a un cliente**, aunque sea una copia con todo encendido. Ahí solo sale la prueba. Lo mismo
  cualquier servidor que no diga que es producción (`DCASA_ENTORNO=produccion`, que el Worker siempre pone): una copia
  en otra máquina no le escribe a nadie más que al equipo.
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

**Hecho el 2026-10-26:** `dcasapty.com` está **Verified** en Resend (DKIM `resend._domainkey` y los CNAME `send` y
`rsend`, en gris; no se agregó otro `_dmarc`: ya había uno). La clave de producción quedó como secreto
`RESEND_API_KEY` en el panel de Cloudflare del Worker `dcasa` (no en GitHub; si un día se pone en GitHub, esa manda);
staging no tiene clave.

### Recibir en info@dcasapty.com

**Hecho el 2026-10-26:** nadie usaba el buzón de Zoho, así que se borraron sus MX y su SPF y Cloudflare Email Routing
reenvía `info@dcasapty.com` y cualquier otra dirección del dominio (catch-all) al Gmail de la empresa. Ese Gmail
responde «como» `info@dcasapty.com` (Gmail › Cuentas › Enviar como, servidor `smtp.resend.com`, puerto 465, SSL,
usuario `resend`, una clave de Resend propia llamada «Gmail»). Para volver a Zoho: borrar los MX/SPF de Cloudflare y
poner otra vez `mx.zoho.com` (10), `mx2.zoho.com` (20), `mx3.zoho.com` (50) y `v=spf1 include:zohomail.com ~all`.

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

Las otras tres casillas vienen marcadas: **«Mandar la factura al registrar un pago»**, **«Recordar el abono antes de que
venza»** y **«Bienvenida a clientes nuevos»**. Desmárcalas si no quieres alguna.

**Ojo, con el correo encendido también salen los correos de acceso de Odoo**: al crear un usuario que tenga correo le
llega de verdad la invitación para elegir su clave, y «Cambiar contraseña» o «Olvidé mi contraseña» mandan su correo
(Mi cuenta los necesita para quien entra con su correo). Hoy, sin correo, no le llega nada a nadie (docs/EQUIPO.md).

Para apagarlo todo de un golpe: desmarca **«Enviar correos a clientes»**. Lo que estaba por salir ya no sale (queda
anotado «Se apagaron los correos antes de enviarlo»). Si desmarcas solo **«Mandar la factura al registrar un pago»** o
**«Bienvenida a clientes nuevos»**, lo de eso que estaba por salir tampoco sale; lo que alguien pide a mano («Enviar»,
Brian) sí.

## 6b. El recordatorio del abono y WhatsApp (D3)

La gerencia pidió el recordatorio por correo **y, si se puede, por WhatsApp**. Lo que quedó:

- **Por correo:** listo y apagado como todo lo demás (arriba). Respeta el interruptor general, la clave de Resend y
  su propia casilla.
- **La lista Facturación › Clientes › Abonos por vencer** (Caja, Gerencia y contabilidad): los abonos que vencen en
  los próximos 5 días y los ya vencidos, del más urgente al menos, con lo que le falta a cada cliente, si ya salió el
  recordatorio por correo y un botón **WhatsApp** que abre WhatsApp (en el teléfono o en WhatsApp Web) **con el mensaje
  listo para ese cliente**: lo manda la persona, desde el teléfono de la tienda. Brian: `abonos_por_vencer`.
- **WhatsApp automático: apagado a propósito.** Hoy WhatsApp va por el puente con código QR (camino no oficial,
  `docs/JUAN_PUENTE.md`): escribirle **primero** a un cliente, sin que haya escrito, es justo lo que más riesgo de
  bloqueo del número da (sección 6 y 8 de esa guía). La forma segura es la API oficial de Meta (el plan B ya preparado),
  que para escribir primero exige **plantillas aprobadas por Meta** (y cobra unos centavos por mensaje) y la
  verificación del negocio, que sigue pendiente. Cuando Meta esté aprobado, el recordatorio por WhatsApp se agrega con
  una plantilla («Hola {nombre}, tu abono de la factura {número} vence el {fecha}: te faltan {saldo}») sobre esta misma
  lista y la misma regla de uno por vencimiento.

## 7. Si algo falla

- **Ventas › Configuración › Correos a clientes (enviados)** (Gerencia y administradores): cada correo, a quién, si
  salió y, si no, por qué. Los filtros «Por enviar», «Enviados» y «No enviados» ayudan a encontrarlos.
- **«Falta el correo de … o está mal escrito»**: corrige el correo en la ficha del cliente. Queda también una nota en la
  factura. La bienvenida se vuelve a intentar con su siguiente pago.
- **Resend no respondió o pidió esperar**: Odoo lo reintenta solo (a los 5, 15, 60 y 240 minutos, hasta 5 veces).
- **No se pudo armar el PDF**: se vuelve a intentar en las siguientes vueltas (cada 10 minutos); al tercer intento queda
  «Falló» con el motivo, y se manda a mano desde la factura con «Enviar».
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
  documento, acceso, prueba u odoo). El contexto `dcasa_correo_tipo` solo lo respeta si quien publica es del equipo
  (`env.uid`, no `env.su`): `/mail/message/post` publica con `sudo()` y deja pasar el `context` del navegador. La prueba solo sale a correos del equipo; apagado o en staging no sale nada más;
  `odoo` nunca. Lo que la política frena se marca «no enviado» (`DCASA_NO_ENVIADO:`) en `mail.mail.send` antes de
  intentarlo: no se llama a Resend ni se llena el log de errores; el transporte vuelve a revisar lo mismo.
- **Gancho del pago** (`models/account_move_line.py`): `_reconcile_pre_hook`/`_reconcile_post_hook`, en un savepoint,
  solo encola en `dcasa.correo.envio` (único por `(tipo, huella)`; huella `factura:saldo en centavos`). Apagado, el
  pago no hace nada del correo. Si el saldo vuelve a quedar igual por un pago (desconciliar y volver a conciliar) y el
  correo de ese saldo se había omitido sin salir, vuelve a la cola; uno que ya salió, nunca. El cron
  `ir_cron_dcasa_correo_cola` arma el PDF nuevo y publica en el chatter con `layout_correo`; la cola de Odoo lo manda.
  Contexto `dcasa_sin_correo_auto`: no encola. Contexto `dcasa_correo_sin_token`: sin `access_token`.
- **Parámetros**: `dcasa_correo.remitente`, `.nombre`, `.responder_a`, `.enviar_a_clientes` (apagado),
  `.al_pagar` y `.bienvenida` (encendidos al instalar), `.bienvenida_desde` (fecha de instalación: quién es nuevo).
- **Brian**: `enviar_factura_por_correo` y `enviar_cotizacion_por_correo` (ver docs/BRIAN.md).
- **Por confirmar en la primera prueba real en staging**: que Resend acepte la cabecera `Idempotency-Key` y los nombres
  de los campos del JSON, y cómo se ve el correo en Gmail en el celular.
