# Camila, la asistente del mail marketing y la página web (diseño)

**Estado: diseño aprobado en sus decisiones; en construcción desde el 2026-11-06.** Pedido de la dueña (2026-11-06):

> «No olvidemos el mail marketing, ¿quién llevará esta tarea tan importante? Ya para el tema de las redes sociales
> estoy yo y está mi otro compañero de marketing. Pero una rama que estamos dejando por fuera es el tema de la página
> web. Y el mail marketing.» · «Solamente vamos a escoger uno de todos esos nombres puntualmente para esto.»

## Decisiones de la dueña (2026-11-06)

| Qué | Decisión |
|---|---|
| Nombre | **Camila**. Los otros nombres reservados (Daniela, Alejandra, Andrés) se asignan más adelante a otras herramientas. |
| Por dónde empieza | **Mail marketing**. La página web va después (etapa 3). |
| Cada cuánto sale una campaña | **Cada 15 días** a lo sumo (Camila la prepara; una persona la aprueba). |
| Precios en el correo | **Con el precio real de Odoo** del día del envío. Nunca un precio escrito a mano ni inventado. |
| Por dónde sale | **El servicio de campañas de Resend** (*Broadcasts*), aparte del de las facturas, para que una campaña nunca se coma el cupo de los correos de factura y abono. |
| Los correos que ya pidió Sofía | **Cuentan como permiso** (2026-11-06): el mensaje de Sofía decía que el correo era «para avisarles de promociones, del programa Socios y de los beneficios de cumpleaños». Queda anotado que aceptó por WhatsApp, con la fecha en que dio el correo; cada campaña trae «Darme de baja». |
| Cuándo se construye | **En paralelo con el arreglo de la varita mágica** (2026-11-06). |

Las redes sociales las llevan la dueña y su compañero de marketing: Camila no publica en redes.

## Quién es

- **Trabaja por dentro para el equipo de marketing**, como Sofía para las vendedoras: **propone y una persona aprueba**.
  Nada sale sin el toque de alguien del rol «Marketing» o de Gerencia.
- **Los clientes reciben los correos de «D'CASA Panamá»**, no de «Camila»: no se presenta ante los clientes como una
  persona.
- **Personalidad:** la que arma la vitrina. Creativa y al día con lo que llegó y con lo que hay en tienda. Escribe con la
  voz de la marca: tuteo, cercana, el pana que sabe de casas; nada de «remate» ni «¡¡CORRE!!».

## Etapa 1: mail marketing

### 1. El permiso del cliente (va primero)

Solo se le escribe a quien dijo **«sí, quiero recibir novedades por correo»**. Queda anotado **cuándo, por dónde y con
quién** (el mismo patrón que el consentimiento de Meta en `dcasa_meta_eventos`, incluida la fusión de fichas). El cliente
puede decir que sí:

- **por WhatsApp**: Juan se lo pregunta en un buen momento (por ejemplo, cuando el cliente da su correo) y lo anota
  solo si el cliente contesta que sí;
- **en la tienda**: la vendedora marca la casilla en la ficha del cliente cuando el cliente se lo dice;
- **en el correo de la factura**: una línea al pie, «¿Te avisamos de lo nuevo? Sí, quiero», que con un toque lo anota;
- más adelante, en la web (checkout y Mi cuenta).

Cada correo de campaña trae abajo **«Darme de baja»**. Con un toque no le vuelve a llegar ninguno, y la baja también
queda en su ficha de Odoo (Resend avisa y Odoo la anota). Una baja se respeta siempre: volver a decir que sí lo hace el
cliente, nunca el sistema.

### 2. La campaña de cada 15 días

1. Camila escoge productos **que sí hay en tienda y que tienen foto**: lo nuevo, lo más vendido y lo que no se mueve
   (las mismas cuentas de la app Marketing, [MARKETING.md](MARKETING.md)).
2. Escribe el asunto y un texto corto con la voz de D'CASA y arma el correo con el diseño de la marca: azul, sin
   degradados ni sombras, el amarillo nunca sobre blanco.
3. **Botón único: «Escríbenos por WhatsApp»** (+507 6026-1919, el del sitio). El enlace lleva un texto con la marca de
   la campaña, para que Juan sepa que ese chat vino del correo.
4. Cada producto lleva **su precio real de Odoo**, el del día del envío. Si un precio cambia o un producto se agota
   antes de aprobar, el correo se arma otra vez con lo de ese momento.

### 3. La aprobación

En la app Marketing, «Camila» muestra el correo **tal como se ve en el celular**, a cuántos clientes con permiso le
llegaría y la fecha de la última campaña. Quien aprueba puede cambiar el texto o los productos, **mandarse una prueba**
y tocar **«Enviar»**. El servidor no deja mandar una campaña si no han pasado 15 días desde la anterior, ni a nadie sin
permiso, ni desde staging.

### 4. Los resultados

Por campaña: a cuántos se envió, cuántos lo abrieron, cuántos tocaron el botón, **y cuántos chats y ventas salieron de
ese correo** (con la marca del enlace y el Origen que Juan ya anota en cada conversación).

## Etapa 2 (después)

- **Cumpleaños:** un saludo con su beneficio de Socios, solo a quien dio permiso y con su fecha guardada (la que Sofía
  ya está guardando). El beneficio sale de `puntos.json`; si allí está `null` o `PENDIENTE`, no se menciona.
- **«Tu cotización sigue aquí»** para las cotizaciones que no se cerraron.

## Etapa 3: la página web

Revisar cada mañana la tienda en línea y proponer arreglos: productos sin foto o con una sola, sin descripción,
agotados que siguen a la vista, lo nuevo que todavía no se ve, y la portada de la semana con lo que hay en tienda. Las
descripciones solo con datos reales del producto (medidas, material).

## Reglas que no se rompen

1. **Sin permiso no hay correo**, y una baja se respeta siempre.
2. **Ningún precio ni cifra inventados**: el precio es el de Odoo del día; nada de «el más vendido de Panamá» ni
   testimonios.
3. **Una persona aprueba cada campaña**; a lo sumo una cada 15 días (tope en el servidor).
4. **Staging nunca le escribe a un cliente** (igual que `dcasa_correo`).
5. **Las campañas no comparten cupo con las facturas**: salen por el servicio de campañas de Resend, con su propia
   clave.
6. Un error de Camila o de Resend **nunca** hace fallar una venta, un pago ni el correo de una factura.

## Cómo se arma (para quien programe)

- Módulo nuevo `dcasa_camila` (depende de `dcasa_correo`, `dcasa_marketing` y `dcasa_conversaciones`).
- Permiso en `res.partner`: `dcasa_promos_fecha`, `dcasa_promos_origen` (whatsapp, tienda, factura, web),
  `dcasa_promos_usuario_id` y `dcasa_promos_baja_fecha`; la fusión de fichas conserva el permiso más reciente y
  cualquier baja.
- Resend (API, revisada el 2026-11-06): los clientes con permiso se sincronizan como **contactos** de un **segmento**
  («Audiences are now called Segments»). La campaña se crea como borrador (`POST /broadcasts` con `segment_id`, `from`,
  `subject`, `html` y el enlace `{{{RESEND_UNSUBSCRIBE_URL}}}`) y se manda al aprobar (Send Broadcast). Las bajas
  vuelven a Odoo por el aviso de Resend o con una lectura periódica.
- **La clave:** la de hoy (`RESEND_API_KEY`) es de **solo envío** y no sirve para contactos ni campañas. Hace falta una
  clave nueva en Resend con acceso a contactos y campañas, como secreto `RESEND_CAMPANAS_API_KEY` en el panel de
  Cloudflare del Worker `dcasa`, igual que la otra. **Nunca en el chat ni en el repositorio.**
- El texto lo escribe la IA con las mismas reglas de marca de Juan; los productos, los precios y el enlace los pone el
  código, nunca la IA.
- Guía (`dcasa_guia`): «Camila» en Marketing y la casilla del permiso en la ficha del cliente.

## Precios de Resend (resend.com/pricing, revisado el 2026-11-06)

- **Correos de factura y abono (transaccionales):** plan gratis con **3,000 al mes y 100 por día**; el Pro cuesta **$20
  al mes** (50,000 al mes, sin tope diario). No está confirmado qué plan tiene D'CASA hoy: se ve en resend.com.
- **Campañas (marketing):** plan gratis **hasta 1,000 contactos**, sin tope de correos enviados; el siguiente cuesta
  **$40 al mes** (hasta 5,000 contactos).

## Lo que falta de la dueña

- Crear en Resend la clave nueva para campañas y pegarla como secreto en Cloudflare (la guía paso a paso irá en este
  documento cuando el módulo esté listo).
