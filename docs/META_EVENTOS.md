# Meta: píxel y ventas (Conversions API)

Módulo `addons/dcasa_meta_eventos` (Paquete 2 del diseño de Meta del 17 oct 2026; el Paquete 1 es el catálogo,
`addons/dcasa_meta_catalogo`, en [META_CATALOGO.md](META_CATALOGO.md)). **Todo viene apagado.** Mientras la dueña no
lo encienda, el sitio y el sistema se comportan igual que antes: ninguna página lleva nada de Meta y no sale ningún
dato.

## En corto (para la dueña)

- **El píxel** mide en la web qué productos se ven, qué se agrega al carrito, quién empieza a pagar, qué se busca y
  quién toca «Escríbenos por WhatsApp». Solo de quien acepta las cookies en el aviso. Nunca reporta la compra: eso lo
  hace el sistema cuando la factura queda pagada.
- **Las ventas** (la Conversions API) le avisan a Meta cuando una factura queda **pagada completa** (un abono no
  cuenta), de la web o de la tienda, para que Meta sepa qué anuncio terminó en venta. El correo y el celular viajan
  **cifrados** (no se pueden leer) y solo de quien aceptó.
- **Nada sale hacia Meta** sin estas cuatro cosas: (1) el interruptor encendido; (2) la sección de Meta en la
  política de privacidad, aprobada por el abogado y publicada; (3) para las ventas, el token de Meta cargado en el
  servidor; (4) que la persona haya aceptado.
- **Un fallo de Meta nunca frena un cobro.** El pago se registra siempre; el aviso a Meta sale después, solo, y se
  reintenta si Meta no contesta.
- En **staging** no hay píxel, y a Meta solo salen eventos con el «código de prueba».

## Dónde se ve

| Pantalla | Quién | Qué hace |
|---|---|---|
| Ajustes › **Meta (Facebook e Instagram)** › Meta: píxel y ventas (también Sitio web › Configuración › **Meta: píxel y ventas**) | administradores | ID del píxel, los tres interruptores («Píxel en el sitio», «Ventas de la web», «Ventas de la tienda»), el código de prueba, la versión de la API, el estado («Token de Meta: cargado / falta», si el token no funciona, si el servidor no es producción) y el botón **«Enviar evento de prueba»** |
| Sitio web › eCommerce › **Eventos enviados a Meta** | Gerencia y administradores | cada factura pagada: enviada, pendiente, con error o «no se envía» y por qué (sin consentimiento, solo anticipo, muy vieja…). Botón **«Reintentar ahora»**. En el celular abre en tarjetas (estado y motivo a la vista) |
| Ficha del cliente › **Anuncios en Meta** | la Vendedora la marca; Gerencia la retira | «Aceptó que compartamos sus compras con Meta (anuncios)», con fecha, dónde y quién lo registró (queda en el historial). Solo aparece con «Ventas de la tienda» o «de la web» encendido |
| Tienda en línea › checkout | el cliente | la misma casilla, **desmarcada**, solo con «Ventas de la web» encendido |
| Sitio público | todos | el **aviso de cookies** (Aceptar / Solo las necesarias) y, en el pie, «Preferencias de cookies» para cambiar de opinión. Solo con el píxel encendido |

Dos cambios de lugar respecto del diseño, para que cada quien lo vea de verdad:

- Los Ajustes no van dentro de «Ajustes › Sitio web»: esa sección es del grupo «Editor y diseñador», que en D'CASA
  nadie tiene (ni la dueña; `dcasa_interfaz` lo retira en cada actualización). Van en su propia sección, «Meta
  (Facebook e Instagram)», que ve cualquier administrador, y en el menú Sitio web › Configuración.
- La lista «Eventos enviados a Meta» no va en Sitio web › Configuración (solo administradores) sino en **Sitio web ›
  eCommerce**, para que Gerencia también la vea (la Guía la encuentra por su `xmlid`,
  `dcasa_meta_eventos.menu_meta_eventos`).

**Hallazgo previo, no de este módulo (comprobado en una base de pruebas con todos los módulos y SIN este módulo):**
un administrador sin «Editor y diseñador» no puede **guardar** ninguna pantalla de Ajustes: Odoo responde «Error de
acceso: No tienes permiso para modificar registros "Sitio web"». La causa: el campo `group_gmc_feed` de `website_sale`
(«Google Merchant Center») es a la vez un grupo y un campo relacionado con `website.enabled_gmc_src`; como es un
grupo, siempre viaja al guardar, y su escritura en el sitio pide «Editor y diseñador», que `dcasa_interfaz` le quita a
todos. Mientras no se arregle (por ejemplo, en `dcasa_interfaz`: no escribir `group_gmc_feed` si no cambió), tampoco se
pueden guardar los Ajustes de Meta ni usar el botón «Enviar evento de prueba» desde la pantalla.

## Cómo funciona

### Contrato con el catálogo (diseño §2, no se cambia sin cambiar los dos módulos)

- `content_ids` = `str(product.product.id)` (la variante), igual que el `id` del catálogo; `content_type` siempre
  `"product"`. Nunca la referencia del proveedor, el código de barras ni el código DC.
- `value` = sin ITBMS (la página muestra «+ ITBMS»; el Purchase usa `amount_untaxed` de la factura). `currency` sale
  de la moneda de la factura o de la tarifa.
- `event_id`: en el navegador `<evento>-<uuid4>`; la compra `factura-<id de la factura>`; la prueba `prueba-<uuid4>`;
  reservado `pedido-<id del pedido>` (para un futuro «Purchase al hacer el pedido»).
- Graph API: `dcasa_meta.graph_version` (por defecto `v26.0`, la de Juan).

### Píxel (`views/templates.xml`, `static/src/js/meta_pixel.js`)

- El servidor solo escribe `data-dcasa-meta-pixel="<id>"` en `#wrapwrap` cuando: el píxel está encendido con un ID
  válido, `DCASA_ENTORNO=produccion`, la política tiene `id="privacidad-meta"`, el sitio muestra el aviso de cookies,
  quien visita **no** es del personal y la página no lleva datos de la persona. Nunca `<script
  src=connect.facebook.net>` ni `<noscript>`.
- **Páginas sin píxel** (`website.pagina_sin_pixel`): el píxel de Meta le manda la dirección COMPLETA de la página en
  cada evento (y la de la anterior como «de dónde vino»). Por eso no se dibuja en `/my` (el portal: sus enlaces llevan
  `?access_token=` y abren el pedido o la factura con nombre, dirección y celular), `/mi-cuenta`, `/socios`, `/web`
  (inicio de sesión y claves), `/payment`, `/brian`, `/contactus` y `/shop/address` (formularios con correo y celular),
  ni cuando un parámetro se llama `*token*` o trae un correo o un celular (por ejemplo `/shop?search=6000-1234`); los
  de campaña (`utm_*`, `fbclid`, `gclid`…) sí miden. Con el píxel encendido esas páginas llevan `<meta name="referrer"
  content="origin">`: la página siguiente solo sabe que vino «de dcasapty.com». El aviso de cookies nombra a Meta en
  todas las páginas (también en esas), porque lo que se acepta ahí vale para las demás.
- **«Política de cookies»**: al encender el aviso, Odoo publica `/cookie-policy` con su texto genérico (Google
  Analytics, anuncios de Google, chat en vivo) y su JS pone ese enlace en el pie. `/cookie-policy` lleva (301) a la
  política de D'CASA, `/privacidad#cookies`.
- **Sin la «configuración automática» de Meta**: antes de `init` el JS llama `fbq('set', 'autoConfig', false, id)`, así
  el píxel no manda por su cuenta los clics de los botones ni los datos de la página; solo los eventos de aquí.
- El JS deja los eventos en una cola en memoria hasta el consentimiento A (la cookie `website_cookies_bar` con
  `optional: true` o el evento `optionalCookiesAccepted`). Al aceptar: carga `fbevents.js`, `fbq('init')`,
  `PageView` y la cola. «Solo las necesarias» la descarta. Si `window.fbq` ya existe (las pruebas) no pide nada.
- El vigilante de terceros de Odoo (`cookie_watcher.js`, «bloquear servicios de terceros») frena el script porque
  Odoo guarda la cookie del aviso **después** del evento «aceptar»; el JS lo suelta por la misma vía que usa el
  vigilante (`_src`), solo cuando la persona ya aceptó (lo prueba `test_pixel_navegador`).
- Eventos: `ViewContent` (ficha, `data-*` iguales para todos: sirven con la página guardada en el borde),
  `AddToCart` (el carrito de Odoo por `add_to_cart_event` + `dcasa_meta_id` en `tracking_info`, y el «Agregar» de un
  clic de la portada y Black Weekend por `data-dcasa-meta-id`), `InitiateCheckout` (checkout) y `AddPaymentInfo`
  (confirmación) desde `<script type="application/json" id="dcasa-meta-datos">`, `Search` (`/shop?search=`, hasta 100
  caracteres) y `Contact` (clic en `wa.me/` o `/whatsapp`). **Nunca `Purchase`.**
- Aviso de cookies: el de Odoo, en español y tuteo, azul sobre blanco (`static/src/scss/meta.scss`), con «Política de
  privacidad» y «Preferencias de cookies» en el pie (borra la elección y las cookies `_fbp`/`_fbc` y recarga).

### Ventas (`models/account_move.py`, `models/meta_evento.py`, `models/meta_api.py`)

1. **Al quedar pagada** una factura de cliente (`_invoice_paid_hook`: `paid` o `in_payment`), dentro de un
   **savepoint** y sin HTTP: se inserta **una** fila `factura-<id>` en `dcasa.meta.evento`. Si algo falla queda en el
   registro y el cobro sigue. No entran: facturas históricas (`dcasa_historica`), notas de crédito, monto sin ITBMS en
   0, pagos parciales, ni con el interruptor de su origen apagado.
2. **Origen**: web si la factura viene de un pedido con sitio web («Ventas de la web»); si no, tienda («Ventas de la
   tienda»).
3. **Consentimiento** (diseño 2.5):
   - A (navegador, aviso de cookies): en el checkout y la confirmación se guardan en el pedido `_fbp`, `_fbc`, IP,
     navegador y página (campos técnicos, solo administradores, sin vista).
   - B (persona): la casilla de la ficha o la del checkout de ese pedido. Solo con B viajan `em` y `ph` cifrados.
   - Web con A → `action_source=website` con el navegador. Web solo con B (sin datos del navegador) →
     `physical_store`: Meta exige el navegador en los eventos `website` y esa venta se cobra en la tienda.
   - Tienda → solo con B, `physical_store`.
   - Sin consentimiento → fila `omitido`, sin datos. Con B pero sin correo ni celular → `omitido` («sin datos para
     emparejar»). Una factura sin productos (solo anticipo, servicios o envío) → `omitido`.
4. **Qué viaja** (`user_data`): `em` = SHA-256 del correo normalizado (minúsculas, sin espacios: la llave de
   Contactos); `ph` = SHA-256 de `507` + 8 dígitos (o los dígitos completos si es de otro país); `external_id` =
   SHA-256 de `dcasa-<id de la ficha comercial>`; `country` = SHA-256 de `pa` solo si el país es Panamá; en la web
   además `fbp`, `fbc`, `client_ip_address` y `client_user_agent` (sin hash, como pide Meta) y `event_source_url`. Sin
   nombre ni apellido. `custom_data`: `currency`, `value` (sin ITBMS), `content_ids`, `contents` (`id`, `quantity`,
   `item_price` sin ITBMS) de las líneas de producto almacenable o combo (sin servicios, descuentos, anticipos ni
   envíos), `num_items`, `order_id` (número de factura) y `content_type`.
5. **El cron** «Meta: enviar las ventas pagadas» (cada 10 minutos, y lo despierta el cobro al confirmar la
   transacción) manda lotes de hasta 100, cada uno en su propia transacción:
   - no manda nada sin token, sin ID, sin la sección de privacidad o con los interruptores apagados;
   - fuera de producción solo con el código de prueba; sin código, lo pendiente queda `omitido` («entorno de
     pruebas»);
   - 400 del lote entero → uno por uno para aislar el malo; otro 4xx → `error` al segundo intento;
   - 5xx, 429, red o tiempo agotado → espera de 1, 5 y 15 minutos, 1 hora y 6 horas;
   - 401/403 o código de token → todo queda pendiente y Ajustes dice «El token de Meta no funciona»;
   - más de 6 días desde la compra → `descartado` (Meta rechaza lo de más de 7).
6. **Borrador o cancelación** de la factura: lo pendiente **y lo que quedó con error** pasa a `cancelado` (así
   «Reintentar ahora» no puede reportar una venta anulada). Lo ya enviado no se retracta (Meta no
   tiene cómo). Si se vuelve a pagar, la misma fila vuelve a la cola, sin duplicar.
7. **Retirar el consentimiento** (Gerencia, botón de la ficha): borra la fecha, cancela lo pendiente **y lo que quedó
   con error** de esa persona, borra los datos cifrados de todas sus filas (también de lo ya enviado), quita la casilla
   del checkout de sus pedidos web todavía sin pagar y borra los datos del navegador tomados en ellos. La Vendedora
   puede marcarlo pero no retirarlo. Desmarcar la casilla del checkout lo quita de esa compra (y de la ficha, si la
   ficha es de ese carrito y lo dio en la web).
8. **Quien retira las cookies después** («Preferencias de cookies» › «Solo las necesarias») y vuelve al checkout o
   llega a la confirmación sin la casilla marcada: se borra lo que se había tomado de su navegador en ese pedido.
9. **Nada de Meta tumba la tienda**: tomar los datos del navegador, preparar los datos del píxel del checkout y marcar
   el id en el carrito van en un savepoint; si fallan, la página sigue y el registro guarda el error limpio (sin IP,
   correo, cookies de Meta ni token). Si la política de privacidad no se puede dibujar sola (por ejemplo, un cambio le
   agrega una variable), la compuerta responde «no está lista» (sin píxel ni ventas) en vez de tumbar todas las
   páginas.

### El token (`META_CAPI_TOKEN`)

- Vive solo como secreto: GitHub › Settings › Secrets and variables › Actions › `META_CAPI_TOKEN` (uno por entorno).
  `desplegar.yml` lo pasa a `.github/scripts/secretos_despliegue.sh`, que lo sube al Worker con cada despliegue
  (vacío: no se sube); el Worker lo pasa al contenedor (`edge/src/handler.ts`, `VARIABLES_DEL_CONTENEDOR`); Odoo lo
  lee del entorno **en el momento de enviar** (`meta_api.token()`).
- Va en el **cuerpo** del POST, nunca en la URL. Todo texto de error pasa por `limpiar_error` (quita el token,
  `access_token=…`, hashes y correos). Nunca se registran los datos del evento ni los hashes.
- Ajustes solo dice «cargado» o «falta». No hay campo para pegarlo.
- Contrato: `edge/CONTRATO_CONTENEDOR.md` §3 y [DESPLIEGUE.md](DESPLIEGUE.md).

## Qué se guarda y cuánto (valores técnicos, ajustables con `dcasa_meta.dias_*`)

| Dato | Dónde | Se borra |
|---|---|---|
| JSON del evento (con los hashes, IP y navegador) | `dcasa.meta.evento.datos` (solo administradores, sin vista) | 7 días después de dejar de estar pendiente (`dias_datos`); al instante si se descarta, se omite o la persona retira el consentimiento |
| La fila (estado, motivo, monto, factura) | `dcasa.meta.evento` | 180 días (`dias_filas`) |
| `_fbp`, `_fbc`, IP, navegador, página | el pedido web (solo administradores, sin vista) | al encolar la compra, o a los 30 días si nunca se pagó (`dias_navegador`) |
| Consentimiento (fecha, dónde, quién) | la ficha del cliente, con historial | hasta que se retira |

Al fusionar dos fichas de la misma persona, el consentimiento pasa **entero** (fecha, dónde y quién) a la que queda si
esa no lo tenía (el más reciente); si ya lo tenía, se queda con el suyo sin mezclar (`models/partner_merge.py`). Al
duplicar una ficha no se copia.

## Paso a paso para encenderlo (la dueña, con nosotros)

1. Terminar la verificación del negocio en Meta (ya pendiente por Juan).
2. En **Administrador de eventos**, conectar un origen «Web» y crear el píxel «D'CASA web». Copiar su número en Odoo ›
   Sitio web › Configuración › Meta: píxel y ventas › «ID del píxel». **No** encender nada todavía. En el píxel ›
   Configuración, dejar **apagada la «Coincidencia avanzada automática»** (si está encendida, el píxel lee el correo y
   el celular de los formularios; el aviso de cookies no lo dice y el diseño lo deja para cuando el abogado lo
   permita).
3. En el píxel › Configuración › Conversions API › «Generar token de acceso». **No mandarlo por el chat**: guardarlo
   en GitHub como `META_CAPI_TOKEN` y avisarnos para desplegar. Ajustes pasará a decir «Token de Meta: cargado».
4. En Administrador de eventos › **Probar eventos**, copiar el código de prueba, pegarlo en Ajustes y apretar
   **«Enviar evento de prueba»**: tiene que aparecer en Meta (Odoo dice «Meta recibió el evento de prueba» y el
   número de rastreo).
5. Cuando el abogado apruebe la sección de privacidad y la publiquemos (un paso aparte que edita
   `website_dcasa/views/legal_templates.xml`), encender en este orden: el píxel, «Ventas de la web» y, al final,
   «Ventas de la tienda». Antes de eso Odoo no deja encender nada («Todavía no se puede encender…»).
6. Mirar Sitio web › eCommerce › Eventos enviados a Meta los primeros días.

## Borrador de privacidad (para el abogado; NO está publicado)

Va en `website_dcasa/views/legal_templates.xml` como una sección nueva con `id="privacidad-meta"`, quitando la frase
«No usamos cookies de publicidad ni de analítica de terceros» y cambiando la fecha «actualizado». Mientras no se
publique, el módulo no deja encender el píxel ni las ventas.

> **Anuncios y medición con Meta**
>
> **Qué usamos.** El píxel de Meta en nuestra web y su Conversions API desde nuestro sistema, para medir y mostrar
> anuncios de nuestros muebles en Facebook e Instagram.
>
> **Qué datos, solo si aceptas.** Identificadores de cookie de Meta (`_fbp`, `_fbc`), las páginas y productos que
> viste, tu carrito, tu dirección IP y tu navegador. Si marcas la casilla (en la web o en la tienda): tus compras,
> con tu correo y tu celular cifrados con SHA-256 (no viajan en claro).
>
> **A quién y dónde.** A Meta Platforms, fuera de Panamá (Estados Unidos).
>
> **Base.** Tu consentimiento, con fecha registrada.
>
> **Cómo retirarlo.** En «Preferencias de cookies», en el pie de página; en la tienda, o escribiendo a
> info@dcasapty.com. Ahí mismo ejerces tus derechos de acceso, rectificación, cancelación, oposición y portabilidad.
>
> **Conservación.** Los datos técnicos se guardan en nuestro sistema solo hasta enviarlos, y como máximo 30 días.

Textos cortos (ya puestos en el sitio, también borradores):

- Aviso de cookies: «Usamos cookies propias para que la tienda funcione. Si aceptas, también usamos las de Meta
  (Facebook e Instagram) para medir y mostrarte anuncios de nuestros muebles. [Aceptar] [Solo las necesarias] ·
  Política de privacidad».
- Casilla del checkout y guion de la ficha: «Acepto que D'CASA comparta mis compras con Meta (Facebook e Instagram),
  con mi correo y celular cifrados, para medir sus anuncios. Puedo retirarlo cuando quiera».

### Preguntas para el abogado (diseño §9.4)

1. ¿El aviso de cookies con «Aceptar» (y nada cargado antes de aceptar) basta para el píxel según la Ley 81 de 2019 y
   el Decreto 285 de 2021? ¿Y para la transferencia a EE. UU.?
2. Ventas de la tienda: ¿hace falta consentimiento expreso o hay otra base legal? ¿Basta que la vendedora marque la
   casilla tras preguntar de palabra, con fecha y usuario registrados?
3. Los textos de arriba y la entidad de Meta que se nombra.
4. Plazos para responder a los derechos ARCO (las fuentes dicen 10 y 5 días hábiles, o 15 y 10).
5. ¿Un anuncio puede mostrar el precio sin ITBMS si la página lo aclara con «+ ITBMS»?
6. ¿Hace falta firmar los términos de tratamiento de datos de Meta o algún registro ante la ANTAI?
7. ¿Es razonable conservar 30 días los datos técnicos (IP y navegador)? ¿Y que en staging, con el código de prueba,
   salgan eventos de prueba a la herramienta «Probar eventos» de Meta?

## Decisiones de la dueña (construido con la recomendación; no se cambian a ojo)

| Decisión | Construido así (recomendado) | Estado |
|---|---|---|
| Momento de la compra web | al quedar **pagada** (no al hacer el pedido; `pedido-<id>` queda reservado) | pendiente de su «sí» |
| Ventas de la tienda | solo de clientes que aceptaron, después del abogado | pendiente de su «sí» y del abogado |
| Staging | sin píxel; las ventas solo con el código de prueba | pendiente de su «sí» |
| Compra web aceptada solo en la tienda (sin datos del navegador) | se reporta como venta de tienda física | decisión técnica (Meta exige el navegador en `website`) |
| Retirar el consentimiento | Gerencia (botón) o la propia persona pidiéndolo; la Vendedora solo lo marca | pendiente de su «sí» |

## Sin verificar con Meta (se comprueba al conectar)

- El parámetro `test_event_code` y que el evento de prueba aparezca en «Probar eventos».
- `country` con hash (solo se manda `pa`).
- Que las compras de la CAPI cuenten como coincidencias del catálogo (Catálogo › Orígenes de eventos).
- Que convenga el mismo conjunto de datos (píxel) para la tienda y la web.
- Los códigos de error de la Graph API que se tratan como «token malo» (102, 190, 10, 200) o «demasiadas llamadas»
  (4, 17, 32, 613, 80004).
- Que la deduplicación por `event_id` funcione igual si el evento del servidor llega antes que el del navegador (hoy
  no se duplica nada: el navegador nunca manda `Purchase`).
- En staging (con la caché de páginas encendida): que el aviso de cookies se porte bien con las páginas guardadas.

## Brian

Esta ronda no trae herramienta nueva de Brian (diseño §7.9): «estado de lo enviado a Meta» y «marcar campaña» quedan
para después. Mientras tanto Brian encuentra las pantallas con `buscar_en_guia` por las tareas de la Guía `meta-eventos`
(«Ver qué ventas se reportaron a Meta», Gerencia) y `meta-pixel` («Conectar el píxel de Meta y mandar un evento de
prueba», administradores). Lo prueba `tests/test_revision_union.py`.

## Pruebas

`addons/dcasa_meta_eventos/tests/` (ninguna llama a Meta; `requests.post` siempre sustituido; personas inventadas):

- `test_meta_api.py`: normalización y hash (correo, `+507`, otros países, nunca doble hash), `limpiar_error`, el
  token en el cuerpo y nunca en la URL.
- `test_compra.py`: apagado de fábrica, un fallo de la cola no rompe el pago, sin HTTP en el cobro, tienda con y sin
  consentimiento, web con solo el navegador o con la casilla, pago parcial, sin duplicados, históricas, notas de
  crédito, monto cero, borrador y cancelación, historial de quién marcó, permisos para retirar.
- `test_cola.py`: sin token, interruptores, sección de privacidad, staging con y sin código, 400 de lote, 500, sin
  red, 401, más de 6 días, el token y el correo nunca en el registro, «Reintentar ahora», ACL y retención.
- `test_ajustes.py`: compuertas, aviso de cookies, el token nunca en la base ni en la pantalla, el botón de prueba y
  que solo un administrador lo usa.
- `test_render.py`: con todo apagado ninguna página lleva nada de Meta; encendido solo el atributo; staging y personal
  sin píxel; `data-*` de la ficha con la variante; `tracking_info`; checkout con y sin consentimiento; la casilla.
- `test_pixel_navegador.py` (Chrome): sin aceptar no se llama nada; al aceptar `init`, `PageView`, `ViewContent`;
  `AddToCart` por los dos caminos, `Search`, `Contact`, `InitiateCheckout`; nunca `Purchase`; `fbevents.js` solo
  después de aceptar.
- `test_contrato_id.py`: el `id` del catálogo = el de la ficha = el del Purchase (solo con `dcasa_meta_catalogo`
  instalado; corre en la unión de los paquetes y enciende el catálogo, que viene apagado).
- `test_revision_union.py` (revisión de la unión, 17 oct): retirar el consentimiento alcanza lo «con error», lo enviado
  y la casilla de pedidos sin pagar; borrador o cancelación también cancela lo «con error»; páginas sin píxel y su
  `referrer`; retirar las cookies después del checkout; un fallo de Meta no tumba el checkout; una política que no se
  dibuja sola no tumba el sitio; la fusión no mezcla el consentimiento; la Guía y Brian encuentran las pantallas;
  `/cookie-policy` lleva a la política de D'CASA; en el celular los eventos abren en tarjetas.
- `test_aviso_celular.py` (Chrome como teléfono, 360 y 390 px): el aviso de cookies entero a la vista, sin salirse de
  lado y con botones de 44 px.
- `edge/test/meta-capi.test.ts`: el token llega al contenedor, es opcional y nunca sale en una respuesta.

## Para después (diseño §7)

Copia por servidor de los eventos del navegador desde el Worker (mismo `eventID`) y la cookie `_fbc` de 90 días;
coincidencia avanzada del píxel y públicos por lista de clientes (si el abogado lo permite); «Purchase al hacer el
pedido» (`pedido-<id>`); WhatsApp oficial (`ctwa_clid`); interruptor en `/mi-cuenta` para retirar el consentimiento;
herramientas de Brian; si se endurece el CSP, permitir `connect.facebook.net` (`script-src`) y `www.facebook.com`
(`img-src`, `connect-src`).
