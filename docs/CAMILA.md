# Camila, la asistente del mail marketing (`dcasa_camila`)

**Estado (2026-11-06): etapa 1 en producción (Desplegar 52).** No envía nada todavía: para que salga la primera
campaña falta la clave de campañas de Resend (§6, paso a paso) y que alguien de Marketing o Gerencia la apruebe.

Pedido de la dueña (2026-11-06):

> «No olvidemos el mail marketing, ¿quién llevará esta tarea tan importante? Ya para el tema de las redes sociales
> estoy yo y está mi otro compañero de marketing. Pero una rama que estamos dejando por fuera es el tema de la página
> web. Y el mail marketing.» · «Solamente vamos a escoger uno de todos esos nombres puntualmente para esto.»

## 1. Decisiones de la dueña (2026-11-06)

| Qué | Decisión |
|---|---|
| Nombre | **Camila**. Los otros nombres reservados (Daniela, Alejandra, Andrés) se asignan más adelante a otras herramientas. |
| Quién es | Trabaja **por dentro** para el equipo de marketing: **propone y una persona aprueba** (rol «Marketing», Gerencia o administradores). Los clientes reciben los correos de **«D'CASA Panamá»**, nunca de «Camila». |
| Por dónde empieza | **Mail marketing**. La página web va después (etapa 3). |
| Cada cuánto | **Una campaña cada 15 días como mucho.** El tope lo pone el servidor. |
| Precios | **El precio real de Odoo**: el mismo que ve el cliente en la tienda en línea, el día que se arma o se aprueba. Nunca un precio escrito por la IA ni a mano. |
| Por dónde sale | **El servicio de campañas de Resend (Broadcasts)**, aparte de los correos de factura, con su propia clave (`RESEND_CAMPANAS_API_KEY`). |
| Permiso | Solo a quien dijo que sí, con **cuándo, por dónde y con quién** (y a qué correo). Cuentan también los que dieron su correo cuando **Sofía** se lo pidió «para avisarles de promociones…», solo si el texto que de verdad se le mandó lo decía. **Una baja se respeta siempre** (por correo, en cualquier ficha). |
| Formas de decir que sí (etapa 1) | La **casilla** de la ficha (la vendedora), el enlace **«¿Te avisamos de lo nuevo? Sí, quiero»** al pie del correo de la factura y de la bienvenida, y lo de **Sofía**. Que **Juan** lo pregunte por WhatsApp queda para la etapa 1b. |
| Darse de baja | El enlace de Resend en cada campaña. Las bajas vuelven a Odoo cada hora y siempre justo antes de enviar; una baja hecha en Odoo también sube a Resend. |

Las redes sociales las llevan la dueña y su compañero de marketing: Camila no publica en redes.

## 2. Para el equipo de marketing (en corto)

**Marketing › Camila.** Arriba ves **a cuántos clientes con permiso** les llegaría, **la última campaña** y **desde
cuándo puede salir la próxima**. Si algo impide enviar (falta la clave, no pasaron 15 días, nadie dijo que sí todavía,
estás en staging), la pantalla lo dice en palabras sencillas y el botón de enviar queda apagado.

1. **«Armar la campaña»** (o lo arma Camila sola cuando pasaron 15 días): escoge productos que hay en tienda, con foto y
   publicados en la web —lo nuevo, lo más vendido y lo que no se mueve—, con su precio de hoy, y escribe el asunto, una
   entrada corta y una línea por producto.
2. A la izquierda ves el correo **tal como le llega al cliente en el celular** (o en la computadora). A la derecha cambias
   el **asunto**, la **entrada** y la **línea** de cada producto; **subes, bajas, quitas o cambias** productos; o **«Agregar
   un producto»** (solo salen los que se pueden ofrecer). **«Guardar cambios»** pone la vista previa al día.
3. **«Volver a armar»**: Camila escoge otra vez y escribe de nuevo (lo que cambiaste a mano se pierde; pregunta antes).
4. **«Enviarme una prueba»**: te llega a tu correo (solo al tuyo, por los correos de siempre). Una cada 2 minutos y
   hasta 10 en 24 horas por persona: salen por el mismo cupo diario que los correos de las facturas.
5. **«Enviar a N clientes»**: pregunta antes y sale. Si un precio cambió o un producto se agotó desde que lo viste, **no
   sale**: te muestra la versión nueva para que la mires otra vez.
6. Abajo, **Campañas enviadas**: a cuántos se envió, cuántos lo abrieron y tocaron un enlace (lo que dice Resend), cuántos
   **chats** llegaron con la marca de la campaña y cuántas **ventas** (el monto lo ve Gerencia).
7. **«Descartar borrador»** lo puede cualquiera del equipo. Una campaña ya **aprobada que quedó trabada** (Resend la
   canceló, quedó en borrador allá o el envío se cortó) solo la descartan **Gerencia o un administrador**, y solo si en
   Resend no salió ni va a salir; así ya se puede armar otra.
8. Al final, **la línea «Sí, quiero» del pie** de la factura y la bienvenida: encendida de fábrica; Gerencia o un
   administrador la pueden apagar (apagada, la línea no va y los enlaces que ya salieron no anotan nada).

**En la ficha del cliente**, junto a las etiquetas: **«Quiere recibir novedades y promociones por correo»**. Márcalo
solo si el cliente dijo que sí y su ficha tiene su correo (queda con la fecha, tu nombre y ese correo; si después cambia
de correo, al nuevo no le llega nada hasta que vuelva a decir que sí). Desmarcarla quita el permiso, pero no es la baja.
Si pide que no le escriban más: **«Darle de baja»** (pide confirmación y es final, para ese correo en cualquier ficha).

## 3. Qué hace por dentro

### 3.1 El permiso del cliente (`models/permiso.py`)

Campos en la ficha comercial (`res.partner`, con historial): `dcasa_promos_fecha`, `dcasa_promos_origen` (`tienda`,
`factura`, `bienvenida`, `sofia_whatsapp`, `web`), `dcasa_promos_usuario_id`, `dcasa_promos_correo` (**el correo al
que dijo que sí**), `dcasa_promos_baja_fecha`, `dcasa_promos_baja_origen` (`correo` = el enlace de Resend, `ficha`) y
`dcasa_promos_baja_usuario_id`. Nadie los escribe a mano ni por RPC (`write`/`create` lo impiden sin `sudo`): solo la
casilla, el botón, el enlace y los crones.

- **El permiso es del correo**: solo se envía si el correo de hoy de la ficha (`correo_valido`) es el mismo
  `dcasa_promos_correo`. Si cambió, la ficha queda «Cambió de correo» y al nuevo no le llega nada hasta un «sí» nuevo.
  Sin un correo bien escrito no se marca.
- **La casilla** (`dcasa_promos`, calculada con inverso): la marca quien puede editar al cliente, **una ficha a la
  vez** (escribirla en varias por RPC o al importar falla); con baja ya no se marca. **Desmarcarla quita el permiso
  sin baja.** «Darle de baja» (`action_dcasa_promos_baja`, con confirmación, una ficha a la vez) exige poder escribir
  la ficha.
- **La baja se mira por correo, no ficha por ficha** (`_dcasa_promos_bloqueos_por_correo`): si CUALQUIER ficha con ese
  correo (otra repetida, una archivada, un contacto hijo o la de su empresa) se dio de baja, ese correo no recibe nada,
  no se vuelve a dar de alta (ni la casilla, ni el enlace, ni Sofía) y su baja sube a Resend. Lo mismo con «no
  contactar» (`dcasa_no_contactar`) en cualquier ficha con ese correo. **La baja es final** en esta etapa.
- **A quién se le escribe** (`_dcasa_promos_con_permiso`): fichas comerciales activas con permiso para su correo de hoy,
  sin baja ni «no contactar» en ninguna ficha con ese correo, y que no son del equipo (usuarios internos ni la empresa).
  Un correo, una vez.
- **La fusión de fichas** (`partner_merge.py`): el «sí» más reciente pasa entero (fecha, por dónde, quién y a qué
  correo) y **cualquier baja manda**.
- **Lo de Sofía** (`_dcasa_promos_de_sofia`, en el cron de cada hora y antes de enviar): se ata al **mensaje que de
  verdad salió de la propuesta** que pidió los datos: con «Enviar ya», el que se guardó al enviarlo
  (`dcasa_camila_mensaje_id`, `models/sofia.py`); con «Abrir el chat», el **primer** mensaje de la vendedora después
  de aprobarla. Ese mensaje tiene que haber salido, **pedir el correo** («tu correo») y tener **la frase de la
  plantilla** «te avisamos de promociones» sin negar (Gerencia puede cambiar las plantillas y la vendedora editar el
  texto: si la frase no está, no cuenta; «no es para promociones» o una promoción en otro mensaje tampoco). Además el
  cliente contestó en las 48 horas siguientes con **el mismo correo que hoy tiene su ficha**. Fecha: la de su
  respuesta; origen «WhatsApp (pidió Sofía)»; con quién: la persona que le escribió.

### 3.2 El enlace «Sí, quiero» (`models/envio.py`, `controllers/main.py`)

- Va **solo en los correos que arma D'CASA** con `dcasa.correo._postear` (`models/correo.py`, una marca en el
  contexto) y son la **factura** (también la de un abono) o la **bienvenida**. Nunca en el recordatorio del abono
  (decisión de la dueña: solo factura y bienvenida), ni en la cotización, ni en el asistente genérico «Enviar» o el
  chatter, ni a seguidores.
- Y solo cuando el correo va a **una sola persona y es la ficha comercial firmada**, con el mismo correo: si la
  factura va a un contacto hijo («Pepe, de la empresa»), el enlace de la empresa no le llega a él. Además la ficha no
  es del equipo, no dijo ya que sí con ese correo y su correo no tiene baja ni «no contactar» en ninguna ficha. Es
  **texto**, no botón: el botón del correo sigue siendo uno. Se arma en un savepoint: si falla, el correo de la
  factura sale igual, sin la línea.
- **Interruptor de Gerencia** (Marketing › Camila, al final; `ajustar_enlace_pie`, parámetro `dcasa_camila.enlace_pie`):
  encendido de fábrica. Apagado, la línea no va y los enlaces que ya salieron no anotan nada.
- El enlace (`/novedades/si?t=<ficha>.<f|b>.<momento>.<firma>`) va **firmado con HMAC** con el secreto de la base
  (`database.secret`, `odoo.tools.misc.hmac`), sobre la ficha, el origen, **el correo de la ficha** y el momento. Se
  lee con una expresión exacta (solo cifras ASCII y la firma en hexadecimal) y la firma se compara en bytes: un token
  raro contesta «Este enlace ya no sirve», nunca un error, exista o no la ficha. Si la ficha cambió de correo, la firma
  no coincide o pasaron más de 400 días, no sirve.
- **Abrir el enlace no anota nada**: muestra una página con la marca y el botón «Sí, quiero» (POST con el token CSRF de
  la sesión). **Decisión técnica:** los filtros de correo de muchas empresas abren los enlaces solos para revisarlos;
  si el GET anotara el permiso, quedaría un «sí» que nadie dio. Por eso son dos toques (el enlace y el botón). Página
  con `Cache-Control: no-store` y `noindex`.

### 3.3 La campaña (`models/camila.py`, `models/campana.py`)

- `dcasa.camila.campana` (estados **borrador → aprobada → enviada**, o **cancelada**; una sola abierta a la vez por un
  índice único), `dcasa.camila.linea` (producto, línea, grupo, el precio y su texto, la foto) y `dcasa.camila.llegada`
  (chats que llegaron con la marca). Solo lectura por RPC.
- **Los productos** (`_elegir`): en tienda (`dcasa_stock > 0`), con foto, publicados para el visitante anónimo de la
  tienda (`website._dcasa_dominio_publicado`), con precio > 0. Por turnos: **lo nuevo** (llegó de un proveedor o se creó
  en los últimos 30 días), **lo más vendido** y **lo quieto** (las cuentas de Marketing de los últimos 30 días, entre lo
  que se puede ofrecer); lo de la campaña anterior va al final; si faltan, lo demás «en tienda». Seis por campaña
  (ocho como mucho al editar).
- **El precio** (`_precios`): el que ve el visitante anónimo de la tienda en línea, hoy: la tarifa del sitio (si las
  tarifas están encendidas, la misma regla de `website_sale` sin carrito), la posición fiscal del usuario público y
  los impuestos como los muestra la tienda (sin ITBMS, con «+ ITBMS» al lado, `_dcasa_mas_itbms`). Al enviar se vuelve
  a calcular todo.
- **El texto** (`_textos`): la IA que ya usa Brian (`brian.proveedores`, respeta su tope de gasto y anota el consumo en
  `brian.uso`) con las reglas de marca (de tú, sin cifras, sin «remate», sin descuentos, sin «el mejor», sin presentarse
  como IA). A la IA **solo le llegan el nombre, la categoría y si es nuevo** de cada producto: ningún dato de clientes.
  Cada texto pasa por la **revisión de marca fija** (`reglas.problemas`): sin cifras, `%` ni `$`; sin números en letras
  («dos por uno», «seis personas», «mitad de precio»; «quincena» sí pasa); sin «remate»; sin «¡¡» ni signos repetidos;
  sin palabras en mayúsculas; sin trato de usted; sin descuentos, ofertas ni «gratis»; sin beneficios ni prisas que
  nadie aprobó («sin costo», «te regalamos», «cuotas sin intereses», «garantía», «precio de fábrica», «últimos días»,
  «aprovecha»); sin superlativos; sin letras de otro alfabeto (una «e» cirílica en «remate»); sin llaves ni etiquetas
  (Resend lee `{{{…}}}` como un dato del contacto). Antes, `reglas.limpiar` pasa el texto por NFKC y **quita** los
  caracteres invisibles (ancho cero, guion suave): «re·mate» con un invisible queda «remate» y no pasa. Lo que no pasa,
  o si la IA falla, queda con el **texto fijo** y la pantalla lo dice. Lo que edita una persona pasa por la misma
  revisión.
- **El HTML** (`views/correo_templates.xml`, `correo_campana`): tablas de 600 px con estilos en línea; logo; el asunto en
  una banda azul `#1340B1` con letra blanca (Anton → Impact/Arial); la entrada; cada producto con su **foto pública de la
  tienda** (`https://<sitio>/dcasa/img/product.template/<id>/image_1920/1024.jpg?v=<versión>`, JPEG para que se vea en
  todo correo; esa ruta solo sirve productos publicados), su nombre (Oswald → Arial Narrow), su línea y **el precio**;
  «Precios de la tienda en línea al dd/mm/aaaa»; un **solo botón «Escríbenos por WhatsApp»**, amarillo **dentro de la
  banda azul** (el amarillo nunca toca el blanco), con el mensaje «Hola D'CASA, vi el correo de novedades y me interesa.
  (Ref. DCN-0007)»; al pie, nombre, dirección, WhatsApp y correo de la empresa, y **«Darme de baja»**
  (`{{{RESEND_UNSUBSCRIBE_URL}}}`). Sin degradados, sombras, `<style>` ni JavaScript.
- **El cron diario** «Camila: preparar el borrador de la campaña»: si pasaron 15 días desde la última enviada (o nunca
  salió ninguna) y no hay una abierta, deja un borrador. **Nunca envía.**

### 3.4 El envío (`models/envio.py`)

Al tocar «Enviar a N clientes», **el servidor revisa todo, aunque llegue por RPC**:

1. el grupo (rol Marketing, Gerencia o administradores);
2. producción (`DCASA_ENTORNO=produccion`; **staging nunca envía**, y un servidor que no lo dice tampoco);
3. que exista `RESEND_CAMPANAS_API_KEY`;
4. los **15 días** (días de Panamá: si la última salió el 6, la próxima puede salir desde el 21);
5. los precios, fotos y existencias **de ahora**: si algo cambió desde que la persona lo vio (la huella del HTML), no
   sale y se le muestra la versión nueva; lo agotado o sin publicar sale de la campaña;
6. al menos un cliente con permiso;
7. **que las bajas se trajeron recién**: sincroniza el segmento en ese mismo momento (abajo) y, si faltan contactos por
   subir, no sale.

Luego queda **aprobada** (con quién y cuándo) y se confirma la base a mitad de la petición, como Sofía: un doble clic u
otra persona la encuentran «enviándose» y no la mandan dos veces. Crea el *broadcast* en Resend (una sola vez; queda su
id); justo antes de mandarlo **vuelve a listar el segmento y, si queda alguien suscrito que no está en la lista de
Odoo, no sale**; lo manda si sigue en borrador; si Resend dice que ya salió, no lo repite. Si falla antes de crear el
*broadcast*, vuelve a borrador con el motivo; si falla después, queda aprobada y «Reintentar el envío» usa el mismo.
**Ningún error la deja a medias**: un error que no es de Resend también la saca de «enviándose» (deshace lo de esa
vuelta, anota el motivo y, sin *broadcast*, vuelve a borrador).

**Una aprobada que quedó trabada** bloquearía a todas las demás (una abierta a la vez). La descartan **Gerencia o un
administrador** (`_descartar`): sin *broadcast* y pasados los 10 minutos de «enviándose», o con el *broadcast*
`canceled` o `draft` en Resend (el borrador se borra allá con `DELETE /broadcasts/{id}` para que nadie lo mande). Si en
Resend salió o va a salir, no se descarta.

**El segmento igual a Odoo** (`_sincronizar`, también cada hora con el cron «Camila: bajas y contactos con Resend»):

1. lee todo el segmento «D'CASA: clientes con permiso (Odoo)» (lo crea la primera vez y guarda su id en
   `dcasa_camila.segmento_id`); cada contacto dado de baja en Resend queda con **baja en todas las fichas con ese
   correo** (origen «correo»);
2. saca del segmento, **por el id del contacto**, a todo el que está suscrito y no está en la lista de Odoo (baja,
   ficha archivada, correo cambiado, pidió que no lo contacten, y también los correos que Odoo no sabe leer, como
   «o'brien@…», o lo que hubiera en un segmento reusado); si ese correo se dio de baja en cualquier ficha, también lo
   marca dado de baja en Resend (`unsubscribed: true`), por su id (por el correo, otra grafía en Resend daba 404);
3. agrega a quien tiene permiso y no está (**solo su correo**: ni nombre ni nada más).

**La prueba** («Enviarme una prueba») sale por los correos de siempre (`dcasa_correo`, `RESEND_API_KEY`) con la clase
`prueba` de `politica.py`: solo a correos del equipo, aunque los correos a clientes estén apagados. Lleva una franja
«Prueba» arriba y el enlace de baja vacío. **Con tope** (`dcasa.camila.prueba`): una cada 2 minutos por persona y
hasta 10 en 24 horas, porque gasta el cupo diario de los correos de las facturas.

### 3.5 Los resultados

- **Chats**: al entrar el mensaje del cliente a Conversaciones (`dcasa.conversacion._despues_de_mensaje`, del lado de
  Odoo; Juan no cambia), si **el primer mensaje del cliente desde que salió la campaña** trae su marca «DCN-0007» (de
  una campaña **enviada**), ese chat cuenta **una vez** para esa campaña. La conversación de un cliente es una sola, de
  siempre: un cliente de antes que vuelve por el correo cuenta; una marca escrita después de otros mensajes, no. Un
  error aquí nunca frena el mensaje.
- **Ventas**: facturas **pagadas** de esos clientes con el chat en los 30 días antes de la factura (la misma ventana de
  las ventas atribuidas de Conversaciones), sin ITBMS. El rol Marketing ve cuántas; el monto, Gerencia y administradores.
- **Entregados, aperturas, clics y bajas**: Resend **sí** los da por API (`GET /broadcasts/{id}/recipients?type=…`); se
  leen cada 6 horas durante 30 días después del envío, o con «Actualizar». Resend avisa que **las aperturas pueden no
  ser exactas** (los programas de correo abren las imágenes solos o las bloquean). Los que se dieron de baja con el
  enlace de esa campaña quedan además con la baja en Odoo.

### 3.6 Brian

`estado_campanas(cuantas?)` (lectura; rol Marketing, Gerencia y administradores): el borrador abierto (asunto,
productos con su precio), cuántos clientes tienen permiso, si está la clave, cuándo puede salir la próxima, por qué no
puede salir ahora y los resultados de las últimas campañas (el monto, solo a quien ve la ganancia). Brian no arma ni
envía campañas: eso se aprueba en la pantalla.

### 3.7 Seguridad y lo que no se rompe

- Por RPC (`dcasa_base/tests/test_superficie_rpc.py`): `dcasa.camila.panel`, `armar`, `guardar`, `buscar_productos`,
  `enviar_prueba`, `enviar`, `descartar`, `actualizar_resultados` y `ajustar_enlace_pie` exigen el grupo en el servidor
  antes de cualquier `sudo`, bloquean la campaña (`FOR UPDATE NOWAIT`) y validan cada argumento (`ajustar_enlace_pie`
  y descartar una aprobada, además, Gerencia o administrador); `res.partner.action_dcasa_promos_baja` exige una sola
  ficha y poder escribirla.
- La clave sale solo del entorno (`RESEND_CAMPANAS_API_KEY`): nunca en la base, en un log, en un error ni en `repr`. Los
  errores de Resend se tachan (sin la clave ni correos de personas).
- **Un error de Camila o de Resend nunca hace fallar una venta, un pago ni el correo de una factura**: nada de Camila
  corre dentro de esos flujos; el enlace del pie va en un savepoint; la marca del chat también.
- Las pruebas nunca llaman a Resend: `tests/comun.py` trae un Resend falso en memoria.

## 4. Pruebas

`addons/dcasa_camila/tests/`: reglas puras (`test_reglas.py`), el cliente de Resend (`test_resend.py`), el permiso, la
baja, la fusión y lo de Sofía (`test_permiso.py`), la campaña y el envío (`test_campana.py`: productos, precio con y sin
tarifa, IA y texto fijo, la marca del correo, el cron, staging, sin clave, 15 días, precio cambiado, agotado, Resend que
falla y reintento, la prueba), el enlace «Sí, quiero» (`test_enlace.py`, con el servidor: GET no anota, POST con CSRF
sí, firma, correo cambiado, baja), los resultados y Brian (`test_resultados.py`) y en el navegador
(`test_navegador.py`): **la pantalla baja con scroll** (`overflow-y: auto` y llega abajo con un borrador largo) en la
computadora y en el celular sin scroll de lado, editar y quitar, el aviso sin clave y la casilla de la ficha.
`test_revision.py` tiene una prueba por cada hallazgo de la revisión adversarial del 2026-11-06 (la baja por correo y no
por ficha, el enlace solo a la ficha firmada y el interruptor, la frase exacta de Sofía, el permiso del correo, nadie de
más en el segmento, la campaña trabada, la casilla una a la vez, la revisión de marca más dura, los tokens raros, el
tope de pruebas, las bajas de los resultados y la marca en el primer mensaje); todas fallaron sobre el código de antes.

## 5. Lo que queda para después

- **Etapa 1b:** que **Juan** pregunte por WhatsApp si quiere recibir novedades (en un buen momento, p. ej. cuando da su
  correo) y lo anote solo si contesta que sí (`juan/` no se tocó en esta etapa). Volver a darse de alta después de una
  baja (lo hace el cliente; hoy la baja es final). El «sí» en la web (checkout y Mi cuenta: origen `web`).
- **Etapa 2:** el saludo de **cumpleaños** con su beneficio de Socios (de `puntos.json`; si allí está `null` o
  `PENDIENTE`, no se menciona) y **«Tu cotización sigue aquí»**.
- **Etapa 3:** la página web (revisar cada mañana la tienda y proponer arreglos).
- La **política de privacidad** (`website_dcasa`, `/privacidad`) todavía no nombra las novedades por correo ni a Resend
  como proveedor: antes de la primera campaña, que la revise la dueña (y el abogado).

## 6. La clave de campañas de Resend (paso a paso para la dueña)

Resend tiene **dos tipos de clave**: «Sending access» (solo manda correos: la de hoy, `RESEND_API_KEY`, para las
facturas) y «Full access» (también contactos, segmentos y campañas). **Para campañas hace falta «Full access»**: es el
permiso mínimo que sirve (Resend no tiene uno intermedio). Por eso va **aparte** de la de facturas y nunca se pega en
el chat, en Odoo ni en un correo.

1. Entra a **resend.com** con la cuenta de D'CASA › menú **API Keys** › **Create API Key**.
2. **Name:** `Odoo campanas produccion`. **Permission:** **Full access**. Toca **Add**.
3. Copia la clave que aparece (empieza con `re_`). **Solo se ve una vez**: guárdala en tu gestor de contraseñas.
4. Entra a **Cloudflare** › **Workers & Pages** › **`dcasa`** › **Settings** › **Variables and Secrets** › **Add**:
   - **Type:** *Secret*.
   - **Variable name:** `RESEND_CAMPANAS_API_KEY` (exacto, en mayúsculas).
   - **Value:** pega la clave. Toca **Deploy** (o *Save*).
5. La clave entra a Odoo cuando el contenedor **arranca de nuevo**: producción no se duerme, así que hace falta un
   despliegue con **imagen nueva** (Desplegar con la misma imagen no reinicia el contenedor). La dueña la pegó el
   2026-11-06; entra con el despliegue que le sigue. Después, en **Marketing › Camila**, ya no sale «Todavía no está la clave de campañas de Resend».
6. **No la pongas en GitHub ni en staging.** Staging nunca envía campañas, con o sin clave.
7. En Resend, **Settings › Unsubscribe page**, puedes poner el logo y los colores de D'CASA en la página de «Darme de
   baja» (opcional).
8. Plan: el gratis de Resend Marketing admite **hasta 1,000 contactos** (precios en §7). Si se pasa, Resend no deja
   enviar la campaña hasta subir de plan o quitar contactos (la pantalla muestra el motivo).

Si la clave se filtra: en Resend › API Keys bórrala, crea otra igual y cámbiala en Cloudflare (paso 4).

## 7. Precios de Resend (resend.com/pricing, revisado el 2026-11-06)

- **Correos de factura y abono (transaccionales):** plan gratis con **3,000 al mes y 100 por día**; el Pro cuesta **$20
  al mes** (50,000 al mes, sin tope diario). No está confirmado qué plan tiene D'CASA hoy: se ve en resend.com.
- **Campañas (marketing):** plan gratis **hasta 1,000 contactos**, sin tope de correos enviados; el siguiente cuesta
  **$40 al mes** (hasta 5,000 contactos).

## 8. La API de Resend (revisada en la documentación oficial el 2026-11-06)

`https://resend.com/docs/llms.txt` › Broadcasts, Contacts, Segments («Audiences are now called Segments»):

| Para qué | Llamada |
|---|---|
| El segmento | `GET /segments`, `POST /segments {name}`, `GET /segments/{id}/contacts?limit=100&after=…` |
| Un contacto | `POST /contacts {email, segments: [{id}]}`; si ya existía, `POST /contacts/{email}/segments/{id}`; sacarlo, `DELETE /contacts/{id o email}/segments/{id}`; la baja, `PATCH /contacts/{id o email} {unsubscribed: true}` («Either id or email must be provided»: Camila usa el id que lista el segmento) |
| La campaña | `POST /broadcasts {segment_id, from, subject, html, reply_to, name}` (borrador), `POST /broadcasts/{id}/send`, `GET /broadcasts/{id}` (`status`: draft, scheduled, queued, sent, canceled); `DELETE /broadcasts/{id}` solo si no salió (draft o scheduled) |
| Resultados | `GET /broadcasts/{id}/recipients?type=delivered\|opened\|clicked\|unsubscribed`, filas `{id (cursor), contact_id, email}` |
| Límite | 10 peticiones por segundo por equipo (429 con `retry-after`): pausa corta entre llamadas y reintentos |
| La baja | `{{{RESEND_UNSUBSCRIBE_URL}}}` en el HTML: Resend pone un enlace único por persona y campaña |
| Permiso de la clave | `sending_access` contesta 401 `restricted_api_key` en contactos y campañas: hace falta `full_access` |
