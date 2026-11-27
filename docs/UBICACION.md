# Ubicación exacta de entrega (`dcasa_ubicacion`)

Nació en Baby Caleb (2026-11-25, con la idea de Nébula y sus fallas corregidas) y se trajo a D'CASA el 2026-11-26
(diseño aprobado en [superpowers/specs/2026-11-26-ubicacion-dcasa-diseno.md](superpowers/specs/2026-11-26-ubicacion-dcasa-diseno.md)).
El pedido de origen: que el cliente ponga su ubicación en tiempo real desde el chat, desde la página o por texto, que haya
algo que confirme que la dirección está bien puesta y que el comprobante lleve un QR que abra Waze y Google Maps al chofer.
Mapa: **Google Maps**.

## Cómo quedó en D'CASA (lo que cambia frente a Baby Caleb)

- **Chofer, no motorizado.** D'CASA no trabaja con motorizados: todos los textos dicen «chofer», sin ícono ni palabra de moto.
- **Sin corredores.** Los choferes de D'CASA no usan corredores (autopistas de peaje). **No se afirma** que los enlaces de
  Waze o Google Maps evitan peajes (no se confirmó): cada chofer activa «Evitar peajes» en su teléfono, la página del chofer
  muestra «Ruta sin corredores» y la Guía lo explica. Los km de la tabla de envíos se midieron en carro, por corredores:
  volver a medirlos sin corredores está pendiente (ver `PRIORIDADES.md` y «Medir el archivo para otro punto de salida» en
  `docs/ENVIOS.md` de Baby Caleb).
- **Retiro en tienda.** D'CASA tiene tienda física. Si el cliente marca su casa en el mapa, se elige sola la entrega a
  domicilio (no si hay un pago en curso); «Retiro en tienda» sigue disponible y no pide mapa, ni saca QR, ni recibe los
  avisos de entrega (`models/delivery.py`, `_dcasa_ubic_elegir_domicilio`; `tests/test_retiro_en_tienda.py`).
- **Avisos encendidos:** pedir la ubicación al confirmar una venta a domicilio y «🚚 Sale hoy».
- **Juan sin emojis.** El asistente de D'CASA escribe sin emojis; las líneas que copia tal cual de una frase escrita por Odoo
  (los pasos 1️⃣ 2️⃣ 3️⃣, el 📍) conservan los suyos (`juan/src/dcasa/salvaguardas.ts`, `limpiarForma`).
- **Marca, voz y datos de D'CASA:** azul `#1340B1`, amarillo `#FED00F` (nunca sobre blanco), Anton/Oswald/Inter, tuteo, ITBMS.
- **Lo que no se trajo:** `dcasa_correo` de Baby Caleb, `docker/negocio.env` y todo `dcasa_envios` (punto de salida propio y
  límite de km: `dcasa_ubicacion` no los necesita).
- **Tarifa:** hoy «en revisión»: el mapa dice «por cotizar» hasta que Gerencia la apruebe.

## En palabras sencillas

- **En la web**, al poner la dirección de entrega el cliente elige **«Marcar en el mapa»** (con «Usar mi ubicación» o
  moviendo el mapa debajo de un pin fijo, con un buscador de barriadas, PH y lugares conocidos) o **«Escribirla»**. Con el punto, la barriada, el
  corregimiento, el distrito y la provincia se llenan solos con la tabla de la calculadora de envíos y el **precio del
  envío sale solo**. Antes de seguir ve **«¿Es aquí?»** con el mapa de cerca.
- **En el chat**:
  - **WhatsApp y Telegram**: el cliente comparte su ubicación con el clip (📎 › Ubicación). Juan la guarda como su punto
    de entrega y le dice el precio del envío.
  - **Un enlace de Google Maps o de Waze** pegado en cualquier chat también sirve: Juan saca el punto del enlace.
  - **Instagram y Messenger** (no comparten ubicación): Juan manda un **enlace de un solo uso**
    (`https://dcasapty.com/u/…`) amarrado a esa conversación. El cliente marca su punto en el mapa y Juan le escribe
    solo con el precio: **no copia ni pega nada**.
- **El comprobante** lleva un **QR para el chofer**: abre una página con **«Abrir en Waze»**, **«Abrir en Google
  Maps»**, la dirección, la referencia, quién recibe, la foto de la casa, «Llamar» y «💬 Avisar que llegué». Sirve
  mientras el pedido no se entregue, se cierra 3 días después de entregado (o al cancelar) y no deja cambiar nada.
- **El panel y Brian (MCP)**: la venta muestra el punto con sus dos botones; Brian da la ubicación de una venta, crea
  el enlace para mandarlo a mano y guarda un enlace de Google Maps que el cliente mandó por otro lado.

## Cerrar la brecha del envío (2026-11-25, segunda vuelta)

Gerencia (Baby Caleb): «el dolor número uno son los pedidos devueltos». Lo que se agregó:

- **El número de casa y las indicaciones van siempre**, como en PedidosYa: en el checkout (con el mapa o escrita), en la
  página del enlace y en el chat (Juan las pregunta y las guarda con `guardar_indicaciones`; Andrés muestra un campo
  «🏠 Número de casa e indicaciones»).
- **Andrés (chat de la web)**: «Usar mi ubicación actual» ahora es precisa (antes, a propósito, unos 100 m: solo para el
  precio). Si el cliente escribe el número de casa, el punto y las indicaciones se guardan en SU carrito
  (`POST /dcasa/brian/v1/carrito/ubicacion`) y el checkout los trae: solo toca «Sí, aquí es».
- **El link de pago** (la página del pedido) y **«¡Gracias por su compra!»**: si va a domicilio y falta la casa (sin
  punto confiable o sin número de casa), una tarjeta «📍 Marcar mi casa en el mapa» (`/u/pedido/<id>?access_token=…`,
  con el permiso del pedido). Al confirmar, el envío del pedido se recalcula **solo si es un carrito o una cotización
  sin pago en curso (también uno recién abierto que la pasarela tiene en borrador, como Tilopay) y sin un envío que
  puso una persona**; si no, el equipo recibe una nota con el precio de la tabla.
  «Volver a mi pedido» solo sale si llegó desde la página del pedido.
- **El enlace del chat**: el mensaje trae tres pasos (1️⃣ abra, 2️⃣ «Mi ubicación» y permita, 3️⃣ casa y «Sí, aquí es»),
  la vista previa muestra un pin en un mapa y, en WhatsApp de la API oficial, además sale el **botón nativo «Enviar
  ubicación»** (`location_request_message`). Si algo falla, la página ofrece **«Copiar mi ubicación»** y **«Mandarla por
  WhatsApp»** (un enlace de Google Maps que Juan sabe leer).
- **El equipo lo ve en el chat de Odoo**: cuando llega la ubicación, un aviso interno con la zona, la calle, la casa, el
  envío y de dónde salió el punto (sin coordenadas: la ruta está en la ficha y en la venta).
- **Sin mapa no se acepta un GPS impreciso** (más de 100 m: en una computadora el «GPS» sale de la conexión a internet y
  puede errar por kilómetros): «📍 Su teléfono no da la ubicación exacta. Active la ubicación precisa y toque «Mi
  ubicación» en su puerta, o busque su barriada 👇», y no se muestra el precio. Andrés tampoco guarda un GPS impreciso.
- **En el checkout, «Confirmar» cuenta como el «Sí, aquí es»** si el punto es bueno; si falta algo, la página baja al
  bloque, dice qué falta y lleva el foco. El bloque solo sale (y solo se exige) en la dirección de entrega, no en la de
  facturación. «Escribir» no borra un punto confiable guardado, salvo que lo escrito nombre otro distrito o sea otra
  calle (se mudó: el punto viejo ya no es su casa).

| Canal | Ubicación fija | En tiempo real | Botón «Enviar ubicación» | Enlace de Maps o Waze | Enlace de un solo uso |
|---|---|---|---|---|---|
| WhatsApp (API oficial) | Sí | No (Meta no la entrega) | Sí (nativo) | Sí | Sí |
| WhatsApp (QR) | Sí | Sí (el primer punto) | No (sin botones) | Sí | Sí |
| Telegram | Sí | Sí | No | Sí | Sí |
| Instagram / Messenger | No | No | No | Sí | Sí |
| Chat de la web (Andrés) | — | — | «Usar mi ubicación actual» | — | — |

## Lo que vive el cliente en el navegador (2026-11-25, auditoría 2)

- **El aviso de cruce ya no se salta**: si escribió otro distrito (el regalo para la mamá en San Miguelito) y el punto
  cae en otro (tocó «Mi ubicación» en La Chorrera), «Confirmar» baja a la tarjeta con **«📍 Es aquí» / «🏠 Es otra
  casa»** en lugar de «Sí, aquí es». El servidor también lo exige (`dcasa_ubic_cruce_ok`). Bajo «Mi ubicación», «¿Es
  para otra casa? Búsquela 👇». Sin mapa, el aviso dice «busque la barriada», no «mueva el mapa».
- **Un arrastre sin querer no cambia la casa**: en el teléfono el mapa se mueve con dos dedos (`cooperative`; con uno
  baja la página), es más bajo (300 px como mucho) y tras el GPS o una búsqueda la página deja el pin y la tarjeta
  encima de la barra fija de «Confirmar». Si el pin se movió más de 30 m después de un «Sí» o de un GPS bueno,
  «Confirmar» pregunta «👆 Movió el pin. ¿Es aquí?». Cambiar a Satélite no quita el «sí».
- **Sin señal no se traba**: «📶 Sin señal. Toque para reintentar»; «Confirmar» y volver la conexión piden la zona otra
  vez. En `/u`, «Ese punto no sirve» solo cuando de verdad no sirve. Pasado el tope de visitas, las páginas salen con
  su plantilla, «Reintentar» y WhatsApp.
- **Con cuenta, el punto del chat de la tienda llega**: Odoo no pasa por el formulario si ya tiene dirección, así que
  `/shop/checkout` pregunta arriba «¿Le entregamos ahí?» («Sí» abre su dirección con ese punto; «No» lo olvida).
  «Agregar dirección» no lo trae. Andrés ya no promete «al pagar ya estará marcada», y con un GPS impreciso guarda al
  menos la casa que escribió.
- **WhatsApp sin «�»**: todos los enlaces del sistema son `api.whatsapp.com/send` (`dcasa_base/whatsapp.py`: también
  los de abonos, «Enviar por WhatsApp» de la cotización, Mi cuenta y Socios); `wa.me` cambiaba los
  emojis en WhatsApp Web y en Instagram.
- **Sin callejones**: sin permiso de ubicación, lo que falta es buscar la barriada (y una línea de cómo permitirla); si
  la barriada no está en la tabla, «💬 Mándenos su dirección por WhatsApp» con lo que buscó y su casa.
- **La invitada que vuelve atrás** desde «Método de entrega» vuelve a SU dirección (con el punto, la casa y quién
  recibe), no a una vacía.
- **El link de pago**: «Marcar mi casa» va antes de «Aceptar y firmar» / «Pagar»; «Cambiar» es un botón de 48 px.
- **«Escribir»**: la calle se llama «Barriada o calle» (el número va aparte), el número de casa se pide después de la
  ciudad y «Departamento, suite» vacío no sale.
- **El chofer**: con un punto aproximado, «Llamar» arriba como sin punto; de usted y sin «tienda».
- **Lo que encontró la compra en staging (2026-11-26)**: (1) con un punto «Fuera de nuestra lista» (lejos de todos
  los lugares, o sin tabla de lugares) el mapa no llena «Barriada o calle» ni «Ciudad»; «Confirmar» no avanzaba y el
  aviso del navegador quedaba detrás de la barra fija. Ahora la página trae ese campo al centro con el foco. (2) Si
  escribía la calle justo antes de «Confirmar», la página volvía a mirar la zona («⏳ Un momento») y había que tocar
  «Confirmar» otra vez; ahora sigue sola cuando llega la zona. **Sin la tabla de lugares cargada, todo punto sale
  «Fuera de nuestra lista» y el envío «se lo confirmamos»**: se carga en Envíos › Tarifa › «Cargar lugares y tarifa
  desde el archivo» (`docs/ENVIOS.md`).

## De dónde sale cada punto (y qué tan fiable es)

| Origen | Cómo se ve | Fiable |
|---|---|---|
| `gps` | «Ubicación del teléfono (±N m)» | Sí, si la precisión es de 100 m o menos |
| `pin` | «Marcada en el mapa» | Sí |
| `whatsapp` | «Compartida por WhatsApp» (o Telegram) | Sí |
| `enlace` | «De un enlace de Google Maps o Waze» | Sí |
| `busqueda` | «Buscada en el mapa» (una dirección de Google sin mover el pin) | Regular: se le pide confirmar |
| `escrita` | «Escrita a mano» | No: el chofer llama antes |

## Cómo se confirma que está bien puesta

1. **«¿Es aquí?»**: el mapa a nivel de calle con el pin, la zona deducida y el precio. Hasta que el cliente toca «Sí,
   aquí es», el punto no cuenta como confirmado.
2. **Precisión del GPS**: si el teléfono da más de 100 m de error, se le pide mover el mapa hasta su puerta.
3. **Lo escrito contra el punto**: si escribió una barriada o un distrito y el pin cae en otro distrito, se le avisa
   («Su punto está en San Miguelito y escribió Arraiján: ¿cuál es?»).
4. **Dentro de Panamá y de la cobertura**: fuera de Panamá no se acepta; más lejos de lo que se envía («Cotizar aparte
   desde»), se acepta pero el envío se confirma por WhatsApp.
5. **La referencia** («casa verde de portón negro, frente al chino») es obligatoria con el mapa.

## Los avisos de la entrega (2026-11-25, tercera vuelta: `models/avisos.py`)

Criterio: la gente no lee: íconos y pocas palabras, y lo más fácil para el cliente.

- **Al comprar, si su casa no está en el mapa** (escrita a mano, buscada sin mover el pin, GPS de más de 100 m o sin
  punto) y la venta va a domicilio, al confirmarla se le pide **una vez**: el asistente le escribe «🛍️ ¡Gracias por su
  compra! 📍 Para que el chofer llegue directo a su casa, márquela aquí: …» con el enlace de un solo uso ligado a la
  venta. Si no puede escribirle, la vendedora (o el responsable por defecto de Ajustes de Juan) recibe el pendiente
  «📍 Pedirle la ubicación de entrega» y en la venta tiene **«📲 Pedir ubicación por WhatsApp»** (WhatsApp con el
  mismo texto). El pendiente se cierra solo cuando el cliente marca un punto confiable. Nunca hace fallar la venta ni el pago.
- **Con la venta ya confirmada**, el «listo» no habla de precio: «✅ ¡Listo! Ya tenemos su casa: Villa Lucre, San
  Miguelito. 🏠 Casa 24. Su pedido S00042 irá a esa dirección.» Lo cobrado no se cambia: si la tabla da otro envío
  para esa zona, queda una nota en la venta para que el equipo decida.
- **Antes de comprar**, el «listo» del enlace dice el precio de la tabla solo si no hay promoción de envío para esa
  zona; si la promoción ya aplica (con la cotización abierta del chat), no dice cifra («🚚 Su envío tiene promoción:
  ¿le confirmo cuánto le queda?») y Juan la da con su frase; si depende de la compra, dice «(precio normal)» y que hay
  promoción.
- **El día de la entrega**, una persona toca **«🚚 Sale hoy: avisarle»** (en la venta, en la entrega, para varias desde
  Acciones de la lista, o Brian): «🚚 ¡Hoy le llega su pedido S00042 a Villa Lucre! ¿Habrá alguien en casa para
  recibirlo? ✅ Sí / 📍 Cambiar» (sin punto, con el enlace del mapa). Una vez por venta y por día. Juan entiende la
  respuesta: si dice que sí, agradece; si no habrá nadie o quiere otro día u hora, la pasa a una vendedora (la fecha la
  confirma siempre una vendedora); si quiere cambiar el lugar, le manda el enlace, que queda ligado a esa venta, y el
  equipo recibe un pendiente para que el chofer abra otra vez la ruta. Si el mensaje no se pudo enviar (Worker
  caído), se puede volver a avisar ese mismo día.
- **¿Cuándo le escribe sola?** WhatsApp por QR y Telegram, siempre; WhatsApp de la API oficial, Instagram y Messenger,
  solo dentro de las 24 horas desde su último mensaje (fuera de eso Meta pide una plantilla aprobada, que no hay; se
  deja una hora de margen). Además: el canal y el asistente encendidos, el Worker configurado y el cliente sin «No
  contactar». Si no, la persona lo manda por WhatsApp. El mensaje va a nombre del asistente (`autor: "bot"`) y queda «por
  enviar»: sale con el cron que manda lo pendiente (que se adelanta), nunca dentro de la confirmación de la venta (ni
  dentro de la petición de la página del enlace: antes hacía COMMIT a mitad). Los avisos le escriben a quien compró,
  nunca a la persona que recibe un regalo. Cancelar la venta cierra el pendiente «📍 Pedirle la ubicación».
- **Brian / MCP**: `pedir_ubicacion_al_cliente` y `avisar_que_sale_hoy` (dicen qué pasó: por el chat o el enlace de
  WhatsApp para abrir), sin coordenadas.

## La casa: quién recibe, otro teléfono, la foto y «para otra casa» (2026-11-25)

- **Quién recibe y un teléfono de respaldo** (opcionales, chicos, debajo del número de casa) en el checkout y en
  `/u/`; Juan los guarda con `guardar_quien_recibe` solo si el cliente los dice (no los pregunta: más preguntas, más
  fricción); Brian con `poner_quien_recibe`. Los ve el chofer (con «Llamar» y WhatsApp al respaldo), el
  comprobante, la venta y la ficha.
- **La foto de la fachada** (opcional, en `/u/`: cámara o galería). El servidor la abre con PIL, rechaza lo que pase de
  12,6 MP antes de decodificar (una «foto» de 190 KB podía ocupar cientos de MB), la endereza, la deja en 1280 px y
  guarda un JPEG nuevo **sin EXIF ni GPS**; dos a la vez por proceso y cinco por enlace. La ve el chofer por
  `/entrega/<secreto>/fachada` (sin caché, `noindex`, CSP `sandbox`) y el equipo en la ficha («Quitar la foto»).
- **«💬 Avisar que llegué»** en la página del chofer: WhatsApp al cliente con «Hola Rosa, soy el chofer de
  D'CASA. Ya llegué con su pedido S00042 📦». Sin punto, primero «Llamar» y «🔎 Buscar la dirección en Google
  Maps» con lo escrito.
- **«Para otra casa»** (un regalo, la abuela, el trabajo): `enlace_de_ubicacion(para_otra_casa=true)` crea una
  **dirección aparte** («Otra casa de Ana», hija del cliente, **de tipo «otra»** y con `dcasa_otra_casa`) y el punto
  va ahí: su casa no se toca (antes la pisaba y el QR de su venta ya confirmada mandaba al chofer a la casa de la
  mamá). No es de tipo «entrega» a propósito: Odoo la tomaría como la dirección por defecto de toda venta nueva de la
  cliente. Una por regalo pendiente; al marcarla se llama «Otra casa de Ana (Villa Lucre)». Sin botón nativo (mandaría
  la ubicación del teléfono). Durante 24 horas, lo que Juan cotiza sin lugar, el número de casa y quién recibe van a esa
  ficha (`dcasa.conversacion._dcasa_ubic_destino`); un punto nuevo del clip, solo mientras el enlace siga sin usar
  (después, la ubicación que comparte es la suya). El aviso al equipo dice que elijan esa dirección en la venta.

## Privacidad (cambia una regla de D'CASA)

D'CASA, a propósito, **nunca guardaba la dirección exacta** (issue #25: Juan solo pide el barrio). Con el «sí» de la
persona responsable (2026-11-26) el punto de entrega **sí se guarda**, porque sin él no hay QR para el chofer. Reglas:

- Se guarda solo en la **dirección de entrega** del cliente (`res.partner`) y en la entrega de esa venta
  (`dcasa.ubicacion.entrega`). Nunca en el texto de la conversación, en el registro del servidor ni en lo que ve el
  modelo de IA: el modelo solo recibe la zona («Brisas del Golf, San Miguelito») y el precio. El Worker tapa **todo**
  enlace de mapa con el punto escrito y las coordenadas escritas a mano dentro de Panamá antes del modelo.
- **La auditoría de Brian** (`brian.accion`, no se edita ni se borra): las herramientas de la ubicación van marcadas
  `privado=True` (`dcasa_brian/models/registro.py`): al cerrarse la acción, argumentos, resultado, error y resumen se
  guardan pasados por `tapar` (sin coordenadas —también `!3d…!4d…` de Google y el geohash de Waze—, secretos de `/u/` y
  `/entrega/`, teléfonos ni lo escrito de la casa).
  Mientras espera confirmación los argumentos siguen enteros (con ellos se corre). `ubicacion_de_entrega` no le da al
  modelo los botones de Waze/Maps (llevan el punto) ni la página del chofer: un «abrir» a la venta.
- El enlace de un solo uso vence a las 24 horas y hay uno vivo por pedido; la página del chofer sirve mientras haya
  una salida sin entregar (nunca más de 90 días desde la compra), se cierra a los 3 días de entregada o al cancelar
  (con secreto nuevo) y, cerrada, no revive. Fotos de la casa: cinco por enlace y diez por ficha y día. El punto que
  dio en el chat de la tienda se borra de un carrito abandonado a los 30 días. Los
  secretos del enlace se guardan como huella (SHA-256); el de la entrega, en un campo que solo lee ventas y contabilidad.
- `Referrer-Policy: strict-origin` (Google valida la clave del mapa por el dominio y el secreto del camino nunca sale).
- **La política de privacidad** (`website_dcasa/views/legal_templates.xml`) lo dice: qué se guarda del punto de entrega, para
  qué, que el punto no pasa por la IA (lo que el cliente escribe, como el número de casa, sí) y que lo ve Google (mapa y
  la calle). El modelo de IA no recibe el punto; Google sí.
- **Riesgo aceptado**: los registros de invocación de Cloudflare (Workers Logs, 7 días) guardan la URL de cada visita,
  con el secreto. Solo los ve quien administra la cuenta y los secretos vencen solos; apagarlos dejaría sin cómo investigar
  una caída.

## Las claves de Google

| Nombre (Cloudflare, Workers `dcasa-staging` y después `dcasa`) | Para qué | Límites que se le ponen en Google Cloud |
|---|---|---|
| `GOOGLE_MAPS_CLAVE_NAVEGADOR` | El mapa en el navegador (se ve en la página: es normal) | Sitios: `dcasapty.com/*`, `www.dcasapty.com/*`, `staging.dcasapty.com/*`, `dcasa.dcasapty.workers.dev/*` y `dcasa-staging.dcasapty.workers.dev/*` (staging responde hoy en workers.dev; la guía de Baby Caleb olvidaba las dos últimas) · APIs: Maps JavaScript |
| `GOOGLE_MAPS_CLAVE_SERVIDOR` | La dirección de calle a partir del punto (Geocoding), desde Odoo | APIs: solo Geocoding |

Las claves las crea la persona responsable (con Claude en Chrome) en un proyecto de Google Cloud de D'CASA con facturación,
cuota diaria y alerta de presupuesto, y las guarda solo como secretos del Worker en Cloudflare: **nunca por el chat ni en
el repositorio**. Después de guardarlas hay que desplegar o reiniciar para que el contenedor las lea. **Estado
(2026-11-27): todavía no están creadas; el mapa real queda sin probar.**

El buscador del mapa **no usa Google**: busca en la tabla de lugares de la calculadora (barriadas, PH, lugares
conocidos, como los dice la gente). Google ya no da su buscador viejo a proyectos nuevos y el nuevo (Places API New)
no hace falta; si un día se quiere, se activa aparte.

**Sin claves, todo sigue funcionando**: «Usar mi ubicación» (GPS) y la dirección escrita no las necesitan; la zona y
el precio salen de la tabla de la calculadora, nunca de Google. Sin la clave del navegador no se ve el mapa; sin la del
servidor no se llena la calle.

## Contrato entre Odoo y el Worker de Juan

Lo que el Worker de Juan (`juan/`, `puente-wa/`) le manda a Odoo y lo que recibe. Las coordenadas viajan del canal a
Odoo **sin pasar por el modelo**.

### 1. `POST /dcasa/juan/v1/ubicacion` (nuevo)

Misma autenticación que `/herramienta` (`Authorization: Bearer <JUAN_ODOO_TOKEN>`). Lo llama el Worker cuando entra un
mensaje con ubicación (WhatsApp, Telegram, Messenger) o con un enlace de mapa que ya resolvió a coordenadas.

```json
{"conversacion_id": 123, "lat": 9.0012345, "lon": -79.5123456, "origen": "whatsapp",
 "nombre_lugar": "Super 99 Brisas", "direccion": "Vía Domingo Díaz"}
```

- `origen`: `whatsapp` (también Telegram y Messenger: ubicación compartida en el chat) o `enlace` (un enlace de Google
  Maps, Waze o Apple Maps). `nombre_lugar` y `direccion` (opcionales, hasta 120 y 200 letras) son los que trae WhatsApp
  cuando el cliente elige un lugar en vez de su ubicación actual.
- Respuesta `200`: `{"ok": true, "resultado": {"guardada": true, "zona": "Brisas del Golf · Rufina Alfaro · San
  Miguelito", "envio": {…}}}`. `envio` tiene **la misma forma que el resultado de `cotizar_envio`** (con
  `por_ubicacion: true`): el Worker lo pone como consulta previa de `cotizar_envio` para que el modelo conteste con el
  precio, igual que «Usar mi ubicación» del chat de la tienda.
- `422` `{"ok": false, "error": "…", "motivo": "fuera_de_panama" | "coordenadas"}`: el punto no sirve; el Worker le
  dice al modelo «(la ubicación que mandó no es de Panamá)» y el modelo le pide otra.
- `404`: no existe la conversación. Envíos apagados: `200` con `envio` = la respuesta de apagado.
- Odoo nunca escribe las coordenadas en el registro ni en la auditoría.

### 2. La herramienta `enlace_de_ubicacion` (nueva, la usa el modelo)

Parámetro opcional `para_otra_casa` (booleano); necesita conversación. Devuelve `{"enlace": "https://…/u/<token>",
"vence_en_horas": 24, "frase_para_el_cliente": "…", "instruccion": "…"}` (los tres pasos, uno por línea) y, en el
WhatsApp de la API oficial y si no es para otra casa, `"boton_whatsapp": true`: el Worker manda además el botón nativo
«Enviar ubicación» (`location_request_message`) y el modelo nunca ve esa clave. Cuando el cliente confirma su punto en esa página, **Odoo** le escribe por el mismo canal
(`POST /odoo/enviar` del Worker con `"autor": "bot"`) con la zona y el precio del envío, y deja el punto guardado.
Con `autor: "bot"` el Worker lo manda **como el asistente**: no da la conversación por tomada (sin eso, Juan se callaría
como cuando escribe una vendedora) y lo guarda en la historia como mensaje del asistente, para que el modelo lo vea en el
siguiente turno. Cualquier otro valor (o ninguno) es una vendedora, como siempre.

### 3. `cotizar_envio` sin lugar

Si el cliente ya tiene un punto de entrega guardado y confirmado (o, en las últimas 24 horas, el de la otra dirección
que marcó por un enlace de esta conversación), `cotizar_envio()` sin `lugar` ni `lugar_id` cotiza con ese punto
(`por_ubicacion: true`, y `ubicacion_guardada` con la zona para ofrecer «¿Se lo llevamos a …, como la vez pasada?»).
Sin punto devuelve `{"estado": "sin_ubicacion"}` (no es un error: que le pida la ubicación según el canal). Así, cuando contesta «sí, súmelo» al mensaje del enlace, el modelo vuelve a
cotizar sin pedirle nada y llama a `agregar_envio` con el `lugar_id` que sale.

### 4. Enlaces de mapa en el texto (lo resuelve el Worker)

Se reconocen: `maps.app.goo.gl/…`, `goo.gl/maps/…`, `google.com/maps/…` (`@lat,lon`, `?q=lat,lon`, `ll=`,
`!3dLAT!4dLON`), `waze.com/ul?ll=lat,lon` y `maps.apple.com/?ll=` o `?q=`. Los cortos se siguen **solo** a hosts de
Google (`maps.app.goo.gl`, `goo.gl`, `maps.google.com`, `www.google.com`, `google.com`), como mucho 3 saltos, 5 s y sin
leer el cuerpo; solo 3 cortos por mensaje se siguen por la red, pero **todos** los que traen el punto escrito se tapan.
Del lado de Odoo (Brian), cada salto se revisa con el mismo analizador que hace la petición (urllib3): https, sin
usuario, sin puerto raro ni «\\». Un enlace sin coordenadas (una búsqueda por nombre) no se adivina.

### 5. `guardar_indicaciones(texto)` y `guardar_quien_recibe(nombre?, telefono?)`

Las usa el modelo; guardan en la ficha de destino de la conversación. Devuelven `{guardado, indicaciones|recibe,
instruccion}`; el Worker las trata como escritura (dos llamadas iguales en un turno van a Odoo una vez).

## Qué mejora frente a Nébula

| Nébula | Aquí |
|---|---|
| Teselas de CARTO sin clave (su propio admin dice que no aguantan una tienda pública) | Google Maps con clave limitada a los sitios |
| Dirección de Nominatim (calle y ciudad); sin distrito, corregimiento ni barriada | Zona de la tabla de la calculadora (la misma que pone el precio) y la calle de Google |
| Sin paso de confirmar; la precisión del GPS no se usa | «¿Es aquí?» obligatorio, precisión ≤ 100 m o mover el pin, aviso si lo escrito no cuadra |
| Un punto fuera de Panamá es solo un aviso | No se acepta |
| Nada para el chat | Ubicación de WhatsApp y Telegram, enlaces de mapa y enlace de un solo uso amarrado a la conversación |
| El QR abre una página **permanente** que deja marcar «entregado» sin iniciar sesión | La página se cierra tras la entrega y no cambia nada |
| El precio de la zona no entra en la cotización | El precio del envío del checkout sale del punto |

## Dónde está cada cosa

| Pieza | Archivo |
|---|---|
| Motor (punto, zona, avisos, botones, enlaces de mapa) | `addons/dcasa_ubicacion/motor/geo.py`, `motor/enlaces_mapa.py` |
| Zona, precio y calle de Google | `models/zona.py` (`dcasa.ubicacion`) |
| El punto en la ficha | `models/res_partner.py` |
| Enlace de un solo uso | `models/enlace.py` (`dcasa.ubicacion.enlace`), página `/u/<secreto>` en `controllers/publico.py` y `views/paginas_templates.xml` |
| Entrega y QR del chofer | `models/entrega.py` (`dcasa.ubicacion.entrega`), `views/reporte_templates.xml`, página `/entrega/<secreto>` |
| Precio en el checkout | `models/delivery.py`, `controllers/checkout.py`, `views/checkout_templates.xml`, `static/src/interactions/checkout_ubicacion.js` |
| El mapa (navegador) | `static/src/lib/mapa_entrega.js` |
| Juan y Brian | `models/herramientas.py`, `models/herramientas_casa.py`, `controllers/juan.py`; la auditoría tapada en `dcasa_brian/models/{registro,accion}.py` |
| Quién recibe, teléfono, foto y «Avisar que llegué» | `motor/casa.py`, `models/res_partner.py`, `views/casa_views.xml`, `views/casa_iconos_templates.xml` |
| Pruebas | `tests/` (`test_motor`, `test_modelos`, `test_rutas`, `test_brecha_envio`, `test_avisos`, `test_casa_chofer`, `test_auditoria_datos`, `test_auditoria_cliente` con el checkout por HTTP y el navegador) |
| Los avisos de la entrega (pedir el punto al comprar, «🚚 Sale hoy») | `models/avisos.py`, `models/herramientas_avisos.py`, `views/avisos_views.xml`, `data/avisos_data.xml`; la respuesta en `juan/src/dcasa/prompt.ts` |
| Borde | `edge/src/routing.ts` (sin caché, secreto fuera del registro), `edge/src/handler.ts` (las dos claves) |
| Diseño y plan de esta adaptación | [superpowers/specs/2026-11-26-ubicacion-dcasa-diseno.md](superpowers/specs/2026-11-26-ubicacion-dcasa-diseno.md), [superpowers/plans/2026-11-26-ubicacion-dcasa-plan.md](superpowers/plans/2026-11-26-ubicacion-dcasa-plan.md) |
