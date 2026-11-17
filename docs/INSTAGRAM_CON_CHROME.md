# Conectar el Instagram de D'CASA a Juan con Claude in Chrome

> **Qué es esto:** la guía que dio resultado con un cliente de un conocido (16 y 17 de octubre de 2026), adaptada a
> D'CASA. Se usa la misma puerta de Meta, «API de Instagram con inicio de sesión de Instagram», que Juan ya trae lista
> desde Juan 22, apagada (ver [JUAN_CANALES.md §3b](JUAN_CANALES.md#3b-instagram-por-inicio-de-sesión-de-instagram-la-segunda-puerta-2026-11-12)).
> **No hay que programar ni desplegar nada:** solo hacer los pasos en Meta y pegar dos claves en Cloudflare.
>
> **Escrita el 2026-11-17.** Antes, Juan atendía Instagram por la página de Facebook; así solo llegaban los mensajes de
> las cuentas con algún papel en la app.

## Antes de pegar el prompt (para la persona)

**Qué cambia frente a la guía del conocido:**

| En la guía del conocido | En D'CASA |
|---|---|
| Panel `bot.emprendemosenfe.com` → tarjeta «Instagram» | **Cloudflare** › Worker `dcasa-juan` › Variables y secretos |
| Campo «1. El App Secret» | Secreto `INSTAGRAM_APP_SECRET` |
| Campo «2. El token de la cuenta» | Secreto `INSTAGRAM_TOKEN` |
| Botón «Copiar» del token de verificación | El valor de `META_VERIFY_TOKEN` (del gestor de contraseñas). Si se perdió, se crea otro: paso B3 |
| `…/api/webhooks/instagram` | `https://dcasa-juan.dcasapty.workers.dev/webhooks/instagram` |
| `…/privacidad` y `…/privacidad#borrar` | `https://dcasapty.com/privacidad` (sirve para las dos) |
| El bot enciende solo la suscripción de la cuenta | Juan **no** la enciende: se enciende en Meta (paso B4) |
| La tarjeta dice «Conectado a @cuenta» | `https://dcasa-juan.dcasapty.workers.dev/salud` dice `"puerta": "inicio_sesion_instagram"` |
| La tarjeta «Comentarios de Instagram» | Odoo › Ajustes de Juan › «Comentarios de Instagram y Facebook». **Se deja apagado** hoy (decisión de la dueña) |

**Lo que hace falta tener a mano:**

- [ ] Tu Facebook, con acceso a `developers.facebook.com` y al portafolio comercial **DCasa Pty**.
- [ ] En el **mismo Chrome**, la sesión de Instagram de **@dcasapty** abierta en `instagram.com`. Así la invitación y la
      llave salen sin pedir contraseña.
- [ ] Acceso a **Cloudflare**, a la cuenta donde vive el Worker `dcasa-juan`. Si no lo tienes, los pasos B1, B2 y B3
      los hace quien sí lo tenga, con esta guía.
- [ ] El valor de **`META_VERIFY_TOKEN`**, del gestor de contraseñas. Si no está, no pasa nada: el paso B3 explica cómo
      poner uno nuevo.
- [ ] El celular con la app de Instagram, entrando como @dcasapty.
- [ ] Una cuenta de Instagram **sin ningún papel** para la prueba final, por ejemplo la de un familiar. Que no sea
      administradora ni evaluadora de ninguna app, y que no esté en el portafolio de D'CASA ni en el de Juancito Ads.

**Tiempo:** de 30 a 45 minutos. **Costo:** $0.

Copia todo lo que va desde la línea de abajo hasta el final y pégalo en Claude in Chrome.

---

# PROMPT PARA CLAUDE IN CHROME

Vas a ayudarme a conectar el Instagram de mi tienda, **D'CASA Panamá (@dcasapty)**, a **Juan**, nuestro asistente.
Juan ya contesta WhatsApp y tiene lista una entrada para Instagram «con inicio de sesión de Instagram»: solo falta
configurarla en Meta y en Cloudflare. Cada paso dice **qué se busca**, porque Meta cambia sus pantallas seguido: si un
botón no se llama igual, busca el que haga lo mismo y dime cuál usaste.

## 🚦 Reglas que no se rompen

1. **Tú no pegas ni escribes secretos.** Eso incluye las dos claves secretas de la app, la de Instagram y la de
   Facebook, la llave de la cuenta (empieza por `IG…`), el token de verificación y cualquier valor de Cloudflare. Cuando
   llegue uno, para y dime: «Ahora copia tú X y pégalo en Y». Tampoco los repitas ni los resumas en el
   chat.
2. **Tú no escribes contraseñas.** Si Meta, Instagram o Cloudflare piden una, para y la escribo yo.
3. **No toques la app «D'CASA Juan»** ni ninguna otra app, página o portafolio. Ahí corre el WhatsApp de la tienda y un
   cambio puede cortarlo. Todo se hace en una **app nueva** llamada **D'CASA Instagram**. Antes de cada cambio en Meta,
   mira el nombre de la app arriba a la izquierda: si no dice «D'CASA Instagram», para.
4. **En Cloudflare no borres ni cambies ninguna variable** que no sea de las que nombra esta guía. `META_APP_SECRET`,
   `META_PAGE_TOKEN`, `WHATSAPP_…` y las demás se quedan como están.
5. **Pídeme el sí antes de:** aceptar las condiciones de Meta (al crear la app), pulsar **Publicar** la app y pulsar
   **Deploy** o «Guardar» en Cloudflare. El clic de Publicar lo doy yo.
6. **Si un paso falla, no lo repitas igual.** A la segunda, copia el mensaje exacto de Meta, para y dímelo.
7. **Las ventanas emergentes** (el inicio de sesión de Instagram que abre Meta) las manejo yo. Si no las alcanzas,
   dímelo y espera.

## 📋 Datos de D'CASA

| Qué | Valor |
|---|---|
| Cuenta de Instagram | `@dcasapty` (la cuenta exacta: ojo con cuentas de nombre parecido) |
| Nombre de la app nueva | `D'CASA Instagram` |
| Portafolio comercial | `DCasa Pty` |
| Correo de contacto de la app | `info@dcasapty.com` |
| Dominio de la app | `dcasapty.com` |
| Política de privacidad | `https://dcasapty.com/privacidad` |
| Eliminación de datos (URL de instrucciones) | `https://dcasapty.com/privacidad` |
| Categoría | Bots de Messenger para empresas |
| URL de devolución de llamada (webhook) | `https://dcasa-juan.dcasapty.workers.dev/webhooks/instagram` |
| Estado de Juan (no muestra secretos) | `https://dcasa-juan.dcasapty.workers.dev/salud` |
| Worker en Cloudflare | `dcasa-juan` |

---

## 0. Comprobaciones antes de empezar

1. **Abre** `https://dcasa-juan.dcasapty.workers.dev/salud` y busca `canales` › `instagram`. Debe decir
   `"puerta": "pagina_facebook"`: es lo esperado, porque todavía no se conecta. Si no aparece la palabra `puerta`, para
   y avísame.
2. **Abre** `https://dcasapty.com/privacidad` y confirma que carga. Meta la visita.
3. **Me lo pides a mí, en el teléfono:** app de Instagram como @dcasapty › Configuración › Mensajes y respuestas a
   historias › Herramientas conectadas › **«Permitir acceso a los mensajes»: ACTIVADO**. Ya se hizo el 10 de noviembre;
   solo hay que confirmarlo. Sin esto no entra ningún mensaje.

## 🅰️ Parte A: en Meta (lo haces tú casi todo)

### A1. Crear la app nueva

1. Entra a `https://developers.facebook.com/apps` › **Crear app**. Si sale el aviso «Hay una nueva manera de crear
   apps», sigue con **Crear app**.
2. **Detalles:** nombre `D'CASA Instagram`; correo de contacto `info@dcasapty.com`, o el que venga puesto si no deja
   cambiarlo. › **Siguiente**.
3. **Casos de uso:** filtra por **«Mensajes comerciales»** › marca **«Administrar mensajes y contenido en Instagram»**
   › **Siguiente**. **No** marques Messenger ni WhatsApp.
4. **Negocio:** si aparece **DCasa Pty**, elígelo. Si dice «No hay negocios disponibles», o Meta pone una traba por el
   portafolio, sigue **sin portafolio**: se puede añadir después, y para esto no hace falta. › **Siguiente**.
5. **Requisitos:** si dice «No se identificaron requisitos», sigue. › **Siguiente**.
6. **Resumen:** al pulsar **Crear app** se aceptan las Condiciones de la plataforma de Meta. **Pídeme el sí antes de
   pulsarlo.**
7. Meta pide la contraseña de Facebook: **la escribo yo**.

**✅ Salió bien si** se abre el **Panel** de la app con el nombre «D'CASA Instagram».

### A2. Permisos

1. Panel › **«Personalizar el caso de uso Administrar mensajes y contenido en Instagram»**. Si sale un recorrido de
   ayuda › **OK**.
2. Debe quedar elegida **«Configuración de la API con inicio de sesión con Instagram»**. **No** la de «inicio de sesión
   con Facebook» ni la «unificada».
3. Sección **«1. Agregar los permisos necesarios para los mensajes»** › **Add all required permissions** (o «Agregar
   todos los permisos necesarios»).
4. Deben quedar estos tres:
   - `instagram_business_basic`
   - `instagram_business_manage_messages`
   - `instagram_business_manage_comments`

**✅ Salió bien si** sale el aviso «Se agregaron todos los permisos disponibles».

### A3. Hacer a @dcasapty «Evaluador de Instagram»

Mientras la app no está publicada, Meta exige este rol antes de dejar añadir la cuenta.

1. En **«2. Generar tokens de acceso»**, enlace **Roles**. También se llega por el menú **Roles de la app › Roles**.
2. **Agregar personas** › marca **«Evaluador de Instagram»**. Está en «Roles adicionales»: no es el «Evaluador» normal.
3. Escribe `dcasapty` y **elige la cuenta exacta** de la lista. Si hay dos parecidas, para y pregúntame.
4. **Agregar**.
5. Acepta la invitación con la sesión de @dcasapty abierta:
   - en la computadora: `https://www.instagram.com/accounts/manage_access/` › pestaña **«Invitaciones para
     evaluadores»** › **Aceptar**. El botón puede verse gris y aun así funciona;
   - si Chrome no tiene abierta la sesión de @dcasapty, para: entro yo, o la acepto en el teléfono (Configuración ›
     Sitios web y apps › Invitaciones de evaluador).

**✅ Salió bien si:**

- en esa pestaña de Instagram aparece «D'CASA Instagram… · Autorizado por ti el …»;
- al volver a Meta, en «2. Generar tokens de acceso», **dcasapty ya aparece en la tabla** con su número y el botón
  «Generar token». No hace falta pulsar «Agregar cuenta» otra vez. Si no aparece, recarga la página una vez.

### A4. Configuración básica (no hay secretos: lo haces tú)

Menú **Configuración de la app › Básica**. Llena solo estos campos:

| Campo | Qué va |
|---|---|
| Dominios de la app | `dcasapty.com` (elige la sugerencia) |
| URL de la política de privacidad | `https://dcasapty.com/privacidad` |
| Eliminación de datos de usuario | Elige «URL de instrucciones…» › `https://dcasapty.com/privacidad` |
| Categoría | **Bots de Messenger para empresas** |
| Correo de contacto | `info@dcasapty.com`, si no estaba |
| Ícono | Opcional. Si quiero ponerlo, subo yo el logo |

- En esta pantalla también está **«Clave secreta de la app»**. **No la abras.** Solo se usa si falla la prueba final
  (paso B7).
- La sección del delegado de protección de datos (RGPD) **no hace falta**: déjala vacía.
- **Guardar cambios**.

**✅ Salió bien si** sale el aviso «Se guardaron los cambios».

---

## 🅱️ Parte B: Cloudflare + Meta (yo pego los secretos)

Deja **dos pestañas** abiertas:

- **Meta:** la app D'CASA Instagram › Casos de uso › Instagram › **Configuración de la API con inicio de sesión con
  Instagram**.
- **Cloudflare:** `https://dash.cloudflare.com` › **Workers & Pages** (en el menú puede salir dentro de «Compute») ›
  **`dcasa-juan`** › **Settings** › **Variables and Secrets**. Si Cloudflare pide entrar, entro yo.

**El orden importa:** primero las dos claves en Cloudflare (B1 y B2), después el webhook (B3). Sin la clave de
Instagram puesta, Juan no deja verificar el webhook, a propósito.

### B1. La clave secreta de la app de Instagram → `INSTAGRAM_APP_SECRET` (la pego yo)

1. **Tú:** en Meta, arriba en la pantalla de la configuración de la API, señálame **«Clave secreta de la app de
   Instagram»** y su botón **Mostrar**. No la abras ni la copies.
2. **Yo:** la muestro y la copio. Si Meta pide la contraseña, la escribo yo.
3. **Tú:** en Cloudflare, **+ Add** (o «Agregar variable»). Tipo **Secret** (no Text). Nombre: escribe exactamente
   `INSTAGRAM_APP_SECRET`. Después **para**.
4. **Yo:** pego el valor y pulso **Deploy** (o «Guardar e implementar»).

> **Ojo:** es la clave **de Instagram**, la de la pantalla de la API de Instagram. **No** es la «Clave secreta de la
> app» de Configuración › Básica.

**✅ Salió bien si** en la lista de Cloudflare aparece `INSTAGRAM_APP_SECRET` como **Secret**, con el valor oculto.

### B2. La llave de la cuenta → `INSTAGRAM_TOKEN` (la pego yo)

1. **Tú:** en Meta, sección **«2. Generar tokens de acceso»**, al lado de dcasapty, señálame **Generar token**.
2. **Yo:** lo pulso, entro como @dcasapty si lo pide (es una ventana aparte), acepto, marco «Entiendo» si sale, y
   copio la llave. Es larga y empieza por `IG`.
3. **Tú:** en Cloudflare, **+ Add** › tipo **Secret** › nombre exacto `INSTAGRAM_TOKEN`. Después **para**.
4. **Yo:** pego la llave y pulso **Deploy**.
5. **Tú:** espera un minuto y abre `https://dcasa-juan.dcasapty.workers.dev/salud` › `canales` › `instagram`.

**✅ Salió bien si** `/salud` dice:

- `"puerta": "inicio_sesion_instagram"`;
- `"faltan": []`;
- ningún problema que diga «**Meta rechaza la llave de Instagram**». Si lo dice, la llave se cortó al copiarla o es de
  Facebook (`EAA…`): repetimos B2 con una llave nueva.

La línea `llave` (vence en unos 60 días) y la de `cuenta` (`@dcasapty`) pueden tardar en salir: aparecen con el primer
mensaje o en la revisión de Juan, al minuto 23 de cada hora. Juan renueva la llave solo: no hay que volver a sacarla.

### B3. El webhook

1. **Tú:** en Meta, sección **«3. Configurar webhooks»**, campo **URL de devolución de llamada**, escribe
   `https://dcasa-juan.dcasapty.workers.dev/webhooks/instagram`. Termina en **/instagram**, no en /meta.
2. **Yo:** en el campo **Token de verificación** pego el valor de `META_VERIFY_TOKEN` y pulso **Verificar y guardar**.
   - Siempre copiado y pegado, nunca escrito a mano: un espacio de más y la verificación falla.
   - **Si no tengo ese valor:** creo uno nuevo, una frase larga sin espacios, de letras y números, con el generador
     del gestor de contraseñas. En Cloudflare, en la variable `META_VERIFY_TOKEN` existente, pulso **Edit**, pego el
     nuevo y **Deploy**. Espero 30 segundos y pego **el mismo** en Meta. Es seguro: Juan solo lo usa cuando Meta
     verifica un webhook, así que WhatsApp y Messenger siguen funcionando. Lo guardo en el gestor de contraseñas.
3. **Tú:** al guardar aparece la lista de campos. Revisa que **`messages`** y **`comments`** estén **suscritos**. Los
   demás (`message_reactions`, `messaging_seen`…) pueden quedar: Juan los ignora. Los comentarios siguen apagados en
   Odoo hasta que la dueña los encienda.

**✅ Salió bien si** aparece la lista de campos del webhook con sus interruptores y `messages` está suscrito.

**Si Meta dice que la verificación falló:** el token no es idéntico (hay espacios o es otro), o `INSTAGRAM_APP_SECRET`
todavía no está en Cloudflare (B1). No lo repitas igual: dime qué dijo Meta.

### B4. Encender la suscripción de la cuenta (lo haces tú: no hay secretos)

En **«2. Generar tokens de acceso»**, en la fila de dcasapty, enciende el interruptor **«Suscripción a webhooks»**
(«Webhook subscription»). Juan **no** lo enciende solo. Sin esto, Meta no avisa de los mensajes de esa cuenta.

**✅ Salió bien si** el interruptor queda encendido después de recargar la página.

### B5. Publicar la app (el clic lo doy yo)

1. **Tú:** menú izquierdo › **Publicar**. Debe decir «Se completó toda la configuración obligatoria de la app».
   - Si falta algo, dime qué: suele ser un campo de A4.
   - Si pide **verificación del negocio** o **revisión de la app**, copia el texto exacto y para. Ese dato decide el
     camino.
2. **Yo:** pulso **Publicar**.

Esto **no es la revisión de Meta**: es un interruptor. Mientras la app no está publicada, Meta no manda los avisos.

**✅ Salió bien si** junto a «Publicar», en el menú, el estado cambia de «Sin publicar» a **«Publicada»**.

### B6. Revisar `/salud`

Abre `https://dcasa-juan.dcasapty.workers.dev/salud` › `canales` › `instagram`:

- `"puerta": "inicio_sesion_instagram"` y `"faltan": []`;
- si aparece `"suscripcion": "no"`, vuelve a B4. Si no aparece, no es un error: sale después de la revisión del
  minuto 23;
- cópiame cualquier línea de `problemas`.

### B7. La prueba de verdad: con una cuenta SIN ningún papel

1. **Yo, desde esa cuenta:** le escribo a @dcasapty «Hola, ¿tienen camas?».
2. Debe pasar en segundos:
   - Juan contesta en Instagram;
   - en **Odoo › Conversaciones** aparece una conversación de **Instagram** con el nombre o el @usuario de esa persona.
3. **Yo, desde la app de Instagram como @dcasapty:** contesto algo a mano. En Odoo debe salir como de la vendedora, y
   Juan se calla en esa conversación.

**Si Juan no contesta en 2 minutos, tú:** abre Cloudflare › `dcasa-juan` › **Observability** (o **Logs**), últimos 15
minutos, y busca `/webhooks/instagram`. Dime qué ves:

| Lo que aparece | Qué significa y qué se hace |
|---|---|
| **Ningún** `POST /webhooks/instagram` | Meta no está mandando el mensaje. Revisar B4 (interruptor), B5 («Publicada») y el paso 0.3 («Permitir acceso a los mensajes»). Si todo está bien, con el acceso estándar no alcanza para clientes reales: el camino siguiente es la revisión de Meta (ver notas) |
| `POST` con **401** | Meta firma con la otra clave de la app. **Yo**: en Meta › Configuración › Básica › «Clave secreta de la app» › Mostrar y copiar; en Cloudflare › `INSTAGRAM_APP_SECRET` › **Edit**, pego esa en lugar de la anterior › Deploy. El webhook no se vuelve a verificar. Repetimos la prueba |
| `POST` con **200**, pero nada en Odoo | Mira `/salud` › `instagram` › `problemas` (por ejemplo «otra cuenta») y que en Odoo › Conversaciones › Configuración › Ajustes de Juan › «Dónde contesta» esté marcado **Instagram** |

### B8. Comentarios: hoy no

En D'CASA los comentarios se encienden en **Odoo › Conversaciones › Configuración › Ajustes de Juan › «Comentarios de
Instagram y Facebook»**, y la dueña decidió dejarlos **apagados hasta probarlos**. Juan solo contesta los comentarios
que preguntan: primero por privado y después, en público, una frase fija sin el nombre de la persona. **No lo
enciendas.** Con B3 ya quedó suscrito `comments` para cuando ella lo decida.

---

## 🩺 Si algo sale mal

| Síntoma | Causa casi segura |
|---|---|
| No deja añadir @dcasapty, o da un error de rol o de «evaluador» | Falta A3: el rol de Evaluador de Instagram y aceptar la invitación |
| Meta dice «La URL de devolución de llamada o el token de verificación no se pudieron validar» | El token no es idéntico, falta `INSTAGRAM_APP_SECRET` en Cloudflare (B1) o la URL no termina en `/webhooks/instagram` |
| `/salud` dice «Meta rechaza la llave de Instagram» | La llave se cortó al copiarla o es de Facebook (`EAA…`) y no de Instagram (`IG…`). Otra vez B2 |
| `/salud` dice «se ignoran avisos de Instagram de otra cuenta» | La llave es de otra cuenta, no de @dcasapty. Otra vez A3 y B2 con la cuenta exacta |
| `/salud` sigue en `"puerta": "pagina_facebook"` | Las variables no se guardaron con **Deploy**, o el nombre está mal escrito (debe ser `INSTAGRAM_TOKEN` e `INSTAGRAM_APP_SECRET`, en mayúsculas) |
| Conectado, pero el mensaje de prueba no llega | La app sigue «Sin publicar» (B5), está apagada la suscripción (B4) o falta «Permitir acceso a los mensajes» (paso 0.3) |
| Llegan las pruebas con cuentas con papel, pero no las de clientes reales | Falta el **acceso avanzado** del permiso de mensajes (ver notas) |
| WhatsApp dejó de contestar | No debería pasar con esta guía. Revisa que no se haya tocado la app «D'CASA Juan» ni las variables `META_…` / `WHATSAPP_…` de Cloudflare, y avisa al equipo técnico |

## 📝 Notas

- **Para volver a como estaba:** borrar `INSTAGRAM_TOKEN` e `INSTAGRAM_APP_SECRET` en Cloudflare. Instagram vuelve a
  ir por la página de Facebook. Messenger y WhatsApp no cambian en ningún caso.
- **Ventana de 24 horas:** Juan solo puede escribirle a alguien en las 24 horas que siguen a su último mensaje, y no
  puede escribir primero.
- **La llave dura 60 días y Juan la renueva sola.** Solo hay que sacar otra si `/salud` dice que Meta la rechaza, por
  ejemplo después de cambiar la contraseña de Instagram.
- **Si los clientes reales no llegan (la primera fila de B7):** hay que pedir el **acceso avanzado** de
  `instagram_business_manage_messages` en la revisión de la app. Eso pide el portafolio **DCasa Pty verificado**, un
  video del flujo y unos días de espera. Es el mismo trámite pendiente para Messenger (PRIORIDADES, punto 00).
- **Para que la app no dependa de una sola persona:** en Roles de la app › Roles › Agregar personas › Administrador,
  agrega a otra persona de la empresa.
- **Nunca compartir en un chat ni en un documento:** las claves secretas, la llave `IG…`, el token de verificación ni
  ningún valor de Cloudflare.
