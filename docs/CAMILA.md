# Camila, la asistente del mail marketing (`dcasa_camila`)

**Estado (2026-11-06): etapas 1 y 2 en producción (Desplegar 54 y Juan 7); etapa 1b (la lista crece sola, §1c)
hecha en su rama, sin desplegar.** No envía nada todavía: para que salga la primera campaña falta que la clave de campañas de Resend entre al
contenedor (§6) y que alguien de Marketing o Gerencia la apruebe.

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
| Cada cuánto | **Una campaña cada 15 días como mucho.** El tope lo pone el servidor. *(Etapa 2: el tope es por cliente, §1b.)* |
| Precios | **El precio real de Odoo**: el mismo que ve el cliente en la tienda en línea, el día que se arma o se aprueba. Nunca un precio escrito por la IA ni a mano. |
| Por dónde sale | **El servicio de campañas de Resend (Broadcasts)**, aparte de los correos de factura, con su propia clave (`RESEND_CAMPANAS_API_KEY`). |
| Permiso | Solo a quien dijo que sí, con **cuándo, por dónde y con quién** (y a qué correo). Cuentan también los que dieron su correo cuando **Sofía** se lo pidió «para avisarles de promociones…», solo si el texto que de verdad se le mandó lo decía. **Una baja se respeta siempre** (por correo, en cualquier ficha). |
| Formas de decir que sí (etapa 1) | La **casilla** de la ficha (la vendedora), el enlace **«¿Te avisamos de lo nuevo? Sí, quiero»** al pie del correo de la factura y de la bienvenida, y lo de **Sofía**. Etapa 1b (§1c): **se activa sola al agregar el correo** (y se quita cuando el cliente dice que no); el cuadro al confirmar una venta o registrar un pago y **Juan** honran el «no». |
| Darse de baja | El enlace de Resend en cada campaña. Las bajas vuelven a Odoo cada hora y siempre justo antes de enviar; una baja hecha en Odoo también sube a Resend. |

Las redes sociales las llevan la dueña y su compañero de marketing: Camila no publica en redes.

## 1b. Decisiones de la dueña para la etapa 2 (2026-11-06)

«La quiero a lo grande, todo conectado con todo.» Lo que cambia respecto de la tabla de arriba:

| Qué | Decisión |
|---|---|
| El tope de 15 días | **Es por cliente** (por correo), no global: a una misma persona le llega como mucho un correo de campaña cada 15 días. Puede haber **varias campañas y varios borradores** a la vez, cada una con su público. El servidor lo cumple al enviar (también por RPC) y queda **registrado quién recibió qué y cuándo** (`dcasa.camila.destinatario`). |
| A quién va | **Chips del CRM** que se combinan, con su número en vivo: todos con permiso, compraron (90 días), compraron hace más de 6 meses, cotizaron o preguntaron y no compraron, tibios y calientes del CRM, recién agregados (30 días) y de hace más de un año. Siempre cruzados con el permiso, la baja y el tope por cliente; la pantalla dice cuántos quedan fuera y por qué. |
| Juan | **Juan sabe que el cliente viene del correo y lo usa**: el mensaje de WhatsApp ya viene escrito con naturalidad («Hola, vi el correo de novedades de D'CASA y me interesa (DCN-0007)») y, cuando llega, Juan tiene en su contexto la campaña y sus productos (sin precios: los da Odoo). La conversación queda con la etiqueta «Vino del correo» y la cotización con «Vino del correo: DCN-0007 · asunto». |
| Los botones del correo | **El correo puede llevar los dos botones**: «Escríbenos por WhatsApp» y «Visita nuestra tienda en línea» (a la tienda del sitio, `/shop`), o uno solo; se eligen en cada campaña. **Sin ningún botón no sale.** La regla «CTA único» de `CLAUDE.md` es del **sitio web**; para el correo la dueña decidió hoy, **2026-11-06**, que puede llevar los dos. |
| Enlaces a la tienda | La foto y el nombre de cada producto pueden llevar a su página en la tienda (se elige). Todo enlace a la web lleva `utm_source=correo`, `utm_medium=email` y `utm_campaign=<código de la campaña>` para que Odoo cuente las visitas y ventas de la web con su seguimiento de siempre (UTM); los resultados lo muestran. |
| Redes sociales | Al pie, **opcional** (se elige en cada campaña): solo las redes que el sitio tiene con enlace (Ajustes del sitio web › redes sociales), en pastillas planas azul marino con letra blanca sobre el fondo blanco. El amarillo nunca toca el blanco. |
| La IA | La misma IA de Juan y Brian **escribe con los datos reales del producto** (nombre, categoría, atributos, descripción, medidas, material) y con **la idea de la campaña** que escribe Marketing; puede **sugerir productos** para esa idea. Misma revisión de marca; si la IA falla, la pantalla lo dice y deja reintentar: nunca en silencio. A la IA no le llega ningún dato de clientes. |
| Desde el tablero | En el tablero de Marketing, «Crear campaña con estos» en Más stock, Más vendidos, Mayor movimiento y Más quietos abre Camila con un borrador nuevo de esos productos (solo los que se pueden ofrecer). En Camila, **«Nueva campaña»**: desde una idea, lo nuevo, lo más vendido, lo más quieto, lo que más hay en stock, lo de mayor movimiento o en blanco. |

## 1c. Decisiones de la dueña para la etapa 1b (2026-11-06): la lista crece sola

La dueña vio «0 clientes con permiso» de unos 3,000. No quiere marcar a nadie de golpe: que la lista crezca sola desde
ahora. Primero se hizo con una pregunta «Sí / No» en cada venta y Juan preguntando por WhatsApp; **ese mismo día
cambió el diseño**: «en el momento en el que se añade un correo, ya debe activarse automáticamente» (también cuando la
ficha recibe el correo por Sofía). La casilla queda activada por defecto y quien atiende la desactiva cuando el
cliente dice que no.

| Qué | Decisión |
|---|---|
| **Se activa sola al agregar el correo** | Cuando la ficha (la comercial) pasa de no tener un correo bien escrito a tenerlo, o a otro distinto, queda con permiso. Al crear la ficha, al escribirle el correo, con «Guarda sus datos» de Sofía y cuando Juan guarda el correo que el cliente le escribió. |
| **El origen honesto** | Queda **«Se activó sola al agregar su correo»** (`al_agregar_correo`), con quién agregó el correo (o Juan) y cuándo; **nunca «tienda»** (eso es «lo marcó la vendedora»). La ficha lo dice así («nadie le ha preguntado todavía») hasta que una persona lo confirma con **«El cliente dijo que sí»** (queda «tienda» con su nombre). |
| **El «no» queda anotado** | Desmarcar la casilla, desactivarla en la venta o decírselo a Juan anota el «no» con cuándo, dónde y quién (`dcasa_promos_no_fecha`, `_no_origen`, `_no_usuario_id`). Con un «no», **la casilla nunca se vuelve a activar sola** (ni aunque cambie de correo); solo una persona puede volver a marcarla si el cliente cambia de idea. El «no» no es la baja: la baja es final y sube a Resend. |
| **Nunca se activa sola** | Con baja o «no contactar» de ese correo en CUALQUIER ficha; después de un «no»; importando (`import_file`), instalando o actualizando módulos (sus datos), en una escritura de muchas fichas a la vez, por el sistema (crones, scripts y migraciones corren como `SUPERUSER_ID`), desde la web pública o el portal (alguien podría escribir el correo de otro en un formulario; el «sí» desde la web es la etapa siguiente), en la ficha de un usuario nuevo, de una empresa o del equipo. **Nada hacia atrás**: a los clientes que ya tenían correo no se les toca; solo desde ahora. |
| **En cada venta** | Cuando una persona del equipo **confirma una venta o registra un pago desde la pantalla**, sale un cuadro corto, sin «Cancelar» ni la X. **Con correo**: la casilla «Quiere recibir novedades por correo» ya viene activada y dice «Se le enviarán novedades a <correo>. Si el cliente dijo que no, desactívala»; «Listo». Desactivada, queda el «no» (en la venta). Si quedó activada y no tenía permiso (un cliente de antes), queda «En la venta» con la referencia «venía activada» (lo honesto: nadie le preguntó); si ya se había activado sola, sigue así. **Sin correo**: «Sí / No» y, con «Sí», el mismo cuadro pide el correo, lo revisa y lo guarda (queda «En la venta»: el cliente dijo que sí). |
| Cuándo NO sale el cuadro | Si una persona o el cliente ya lo confirmó con su correo de hoy (cualquier camino que no sea el automático); con baja o «no contactar»; si el cuadro ya salió para esa ficha, o dijo que no, hace menos de **180 días** (un ajuste: `dcasa_camila.dias_entre_preguntas`; pasado el plazo de un «no», sale con la casilla desactivada); a fichas del equipo o empresas. |
| **La regla de oro** | Esto **nunca traba ni hace fallar una venta o un pago**: el cuadro sale DESPUÉS de confirmar o de pagar (ya quedaron hechos), solo en la pantalla (la marca va en el botón «Confirmar» de la cotización y en «Crear pago» del asistente «Pagar») y para el equipo. Nunca en Juan, la web, Brian, los crones ni un RPC sin esa marca. Si armar el cuadro falla, no sale y la venta o el pago siguen igual. Y activar las novedades al guardar un correo va en un savepoint: si falla, el correo se guarda igual. |
| **Juan** | Nunca las activa por su cuenta ni pregunta si las quiere. Si el cliente le da su correo, lo guarda (`guardar_correo`: tiene que estar escrito por el cliente en el chat, y solo si la ficha no tiene uno) y le dice con claridad que le llegarán las novedades a ese correo y que puede decir que no cuando quiera. **Si el cliente dice que no, claro o con dudas, las quita** (`no_quiere_novedades`, origen «Se lo dijo a Juan en el chat»): siempre se honra un no. |
| **El pie de cada campaña** | Para todos (Resend manda el mismo contenido a todo el segmento): «Te llega porque nos diste tu correo en D'CASA. ¿No quieres más? **Date de baja aquí**». |
| En la pantalla de Camila | Cuántos llegaron por cada camino: al agregar su correo, en la venta, Juan, el enlace de la factura y el de la bienvenida, Sofía y la casilla de la ficha (solo cuántos). |

## 2. Para el equipo de marketing (en corto)

**Marketing › Camila.** Arriba ves **a cuántos clientes con permiso** les puede llegar algo (y por dónde: al agregar
su correo, en la venta, Juan, el enlace de la factura o la bienvenida, Sofía o la casilla), **la última campaña** y
el tope: **a cada cliente, un correo cada 15 días como mucho**. Si algo impide enviar (falta la clave, nadie dijo que
sí todavía, nadie de ese público puede recibirla ahora, no eligió ningún botón, estás en staging), la pantalla lo dice
en palabras sencillas y el botón de enviar queda apagado. Puede haber varias campañas abiertas: cada una es una
pestaña.

1. **«Nueva campaña»**: desde una idea (escribes lo que quieres contar y la IA escoge productos y escribe), lo nuevo,
   lo más vendido, lo más quieto, lo que más hay en stock, lo de mayor movimiento o en blanco. Solo entran productos en
   tienda, con foto, con precio y publicados en la web, con **su precio de hoy**. También desde el **tablero de
   Marketing**: «Crear campaña con estos» en Más stock, Más vendidos, Mayor movimiento y Más quietos.
2. **El constructor** ocupa toda la pantalla: **la idea de la campaña** (con «Escribir el asunto», «Escribir la
   entrada», «Escribir todo» y «Sugerir productos para esta idea»), el **asunto**, la **entrada** y cada producto con su
   línea y **«Escribir con IA»** (usa los datos reales del producto). **«Cambiar»** o **«Agregar un producto»** abren
   una ventana con buscador, filtros (categoría, en tienda, con foto, publicado) y tarjetas con foto, precio y
   existencias; lo que no se puede ofrecer sale con el motivo. Si la IA falla, lo dice y puedes **reintentar**.
3. **Los botones del correo**: «Escríbenos por WhatsApp», «Visita nuestra tienda en línea» o los dos (sin ninguno no
   sale); que la foto y el nombre de cada producto lleven a su página; y las redes sociales al pie (opcional).
4. **¿A quién va?**: toca los chips (se suman): todos con permiso, compraron en los últimos 90 días, compraron hace más
   de 6 meses, cotizaron o preguntaron y no compraron, tibios, calientes, recién agregados, de hace más de un año. Cada
   chip dice cuántos hay ahora; abajo, a cuántos les llegaría y **cuántos quedan fuera y por qué** (ya les llegó una
   campaña hace menos de 15 días, no han dicho que sí, se dieron de baja, sin correo bien escrito).
5. **«Previsualizar»**: abre el correo grande, tal como le llega al cliente, en **celular o computadora**, con el asunto.
6. **«Enviarme una prueba»**: te llega a tu correo (solo al tuyo, por los correos de siempre). Una cada 2 minutos y
   hasta 10 en 24 horas por persona: salen por el mismo cupo diario que los correos de las facturas.
7. **«Enviar a N clientes»**: pregunta antes y sale. Si un precio cambió o un producto se agotó desde que lo viste, **no
   sale**: te muestra la versión nueva. Si otra campaña se está enviando o todavía está saliendo en Resend, espera unos
   minutos y vuelve a tocar.
8. Abajo, **Campañas enviadas**: a cuántos se envió, cuántos lo abrieron y tocaron un enlace (lo que dice Resend),
   cuántos **chats** llegaron con la marca de la campaña, cuántas **ventas** por el chat y cuántas **en la web** (las
   que Odoo contó con el código de la campaña). Los montos los ve Gerencia.
9. **«Volver a armar»** escoge otra vez y escribe de nuevo (lo que cambiaste a mano se pierde; pregunta antes).
   **«Descartar borrador»** lo puede cualquiera del equipo. Una campaña ya **aprobada que quedó trabada** (Resend la
   canceló, quedó en borrador allá o el envío se cortó) solo la descartan **Gerencia o un administrador**, y solo si en
   Resend no salió ni va a salir.
10. Al final, **la línea «Sí, quiero» del pie** de la factura y la bienvenida: encendida de fábrica; Gerencia o un
    administrador la pueden apagar (apagada, la línea no va y los enlaces que ya salieron no anotan nada).

**Cuando un cliente escribe por el correo**, Juan ya sabe de qué campaña viene y qué productos llevaba; la conversación
queda con la etiqueta **«Vino del correo»** y la cotización que se le haga en los 30 días siguientes dice de qué campaña.

**En la ficha del cliente**, junto a las etiquetas: **«Quiere recibir novedades y promociones por correo»**. Se activa
sola cuando le agregas su correo y la ficha lo dice («Se activó sola al agregar su correo»); si el cliente te dijo que
sí de verdad, toca **«El cliente dijo que sí»**. Si te dice que no, desmárcala: queda anotado y ya no se activa sola
(desmarcarla no es la baja). Si pide que no le escriban más: **«Darle de baja»** (pide confirmación y es final, para
ese correo en cualquier ficha).

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

- `dcasa.camila.campana` (estados **borrador → aprobada → enviada**, o **cancelada**; desde la etapa 2 puede haber
  **varias abiertas**: la migración `19.0.2.0.0` borra el índice único de «una abierta»), con su `tema`, su `idea`, su
  `publico` (los chips) y los botones (`boton_whatsapp`, `boton_web`, `enlaces_productos`, `redes`);
  `dcasa.camila.linea` (producto, línea, grupo, el precio y su texto, la foto), `dcasa.camila.llegada` (chats que
  llegaron con la marca) y `dcasa.camila.destinatario` (quién recibió qué campaña y cuándo, §3.4). Solo lectura por RPC.
- **Los productos** (`_elegir`): en tienda (`dcasa_stock > 0`), con foto, publicados para el visitante anónimo de la
  tienda (`website._dcasa_dominio_publicado`), con precio > 0. Por turnos: **lo nuevo** (llegó de un proveedor o se creó
  en los últimos 30 días), **lo más vendido** y **lo quieto** (las cuentas de Marketing de los últimos 30 días, entre lo
  que se puede ofrecer); lo de la campaña anterior va al final; si faltan, lo demás «en tienda». Seis por campaña
  (ocho como mucho al editar). Con un **tema** (`_elegir_tema`) salen solo de ese grupo del tablero de Marketing (lo
  nuevo, más vendidos, más quietos, más stock, mayor movimiento); con una lista de ids (el tablero o «Sugerir
  productos», `_elegir_ids`) se filtran a lo que se puede ofrecer, en ese orden.
- **El precio** (`_precios`): el que ve el visitante anónimo de la tienda en línea, hoy: la tarifa del sitio (si las
  tarifas están encendidas, la misma regla de `website_sale` sin carrito), la posición fiscal del usuario público y
  los impuestos como los muestra la tienda (sin ITBMS, con «+ ITBMS» al lado, `_dcasa_mas_itbms`). Al enviar se vuelve
  a calcular todo.
- **El texto** (`_textos`): la IA que ya usa Brian y Juan (`brian.proveedores`, respeta los mismos topes de gasto del
  mes que Brian, el de todos y el de cada persona, Ajustes › Brian, y anota el consumo en `brian.uso`) con las reglas de marca (de tú, sin cifras, sin «remate», sin descuentos, sin «el mejor», sin
  presentarse como IA). A la IA **solo le llegan datos del producto y la idea de la campaña**: ningún dato de clientes.
  Al armar, el nombre, la categoría y el grupo; **el redactor** (etapa 2, `_escribir`, «Escribir con IA») le da además
  los **datos reales** del producto (`_datos_ia_producto`): atributos, la descripción de venta o de la web (en texto,
  hasta 600 letras), las medidas (`dcasa_medidas`) y el material. «Escribir el asunto», «la entrada» o «todo» usan la
  idea; **«Sugerir productos para esta idea»** (`_sugerir`) le pasa la idea y la lista de productos que se pueden
  ofrecer (id, nombre, categoría) y solo acepta ids de esa lista.
  Cada texto pasa por la **revisión de marca fija** (`reglas.problemas`): sin cifras, `%` ni `$`; sin números en letras
  («dos por uno», «seis personas», «mitad de precio»; «quincena» sí pasa); sin «remate»; sin «¡¡» ni signos repetidos;
  sin palabras en mayúsculas; sin trato de usted; sin descuentos, ofertas ni «gratis»; sin beneficios ni prisas que
  nadie aprobó («sin costo», «te regalamos», «cuotas sin intereses», «garantía», «precio de fábrica», «últimos días»,
  «aprovecha»); sin superlativos; sin letras de otro alfabeto (una «e» cirílica en «remate»); sin llaves ni etiquetas
  (Resend lee `{{{…}}}` como un dato del contacto). Desde la revisión del 2026-11-06 (etapa 2), además: sin prisas
  («quedan pocas», «corre», «no te lo pierdas», «antes de que vuele»), sin formas de pago («en partes», abonos, Tafi,
  Crediviva), sin «gratis» con otras palabras («sin pagar extra», «regalada»), sin «el más … de Panamá», «lo más top»
  ni «-ísimo», sin testimonios («nuestros clientes dicen», «les encanta»), sin «para toda la vida», sin «Black Friday»
  ni «precio de locura», sin usted («le va a encantar», «su familia») y sin direcciones web, correos ni teléfonos
  escritos. Antes, `reglas.limpiar` pasa el texto por NFKC y **quita** los
  caracteres invisibles (ancho cero, guion suave): «re·mate» con un invisible queda «remate» y no pasa. Al armar, lo
  que no pasa o si la IA falla queda con el **texto fijo** y la pantalla lo dice. En el redactor, lo que no pasa **no
  se guarda** y la pantalla dice por qué, con **«Reintentar»** (`ErrorIA`: «La IA no respondió (…)», «La IA no devolvió
  un texto que se pudiera leer», o el motivo de la revisión): nunca en silencio. Lo que edita una persona pasa por la
  misma revisión.
- **El HTML** (`views/correo_templates.xml`, `correo_campana`): tablas de 600 px con estilos en línea; logo; el asunto en
  una banda azul `#1340B1` con letra blanca (Anton → Impact/Arial); la entrada; cada producto con su **foto pública de la
  tienda** (`https://<sitio>/dcasa/img/product.template/<id>/image_1920/1024.jpg?v=<versión>`, JPEG para que se vea en
  todo correo; esa ruta solo sirve productos publicados), su nombre (Oswald → Arial Narrow), su línea y **el precio**;
  con «enlaces a cada producto», la foto y el nombre llevan a su página de la tienda. «Precios de la tienda en línea al
  dd/mm/aaaa»; **los botones elegidos** dentro de la banda azul: **«Escríbenos por WhatsApp»** amarillo (el amarillo
  nunca toca el blanco), con el mensaje ya escrito «Hola, vi el correo de novedades de D'CASA y me interesa
  (DCN-0007)», y/o **«Visita nuestra tienda en línea»** blanco con letra azul marino, a `<sitio>/shop`. Todo enlace a la
  web lleva `?utm_source=correo&utm_medium=email&utm_campaign=DCN-0007` (`_con_utm`; la dirección del sitio es la de
  `website.domain`, nunca escrita a mano). Al pie, si se eligió, **las redes del sitio** que tienen enlace
  (`website.social_facebook`, `social_instagram`, `social_tiktok`, `social_youtube`, `social_twitter`,
  `social_linkedin`; solo `http(s)`) en pastillas planas azul marino con letra blanca (texto, sin imágenes: se ven en
  todo correo); nombre, dirección, WhatsApp y correo de la empresa, y **«¿No quieres más? Date de baja aquí»** (con «Te llega porque nos diste tu correo en D'CASA», etapa 1b)
  (`{{{RESEND_UNSUBSCRIBE_URL}}}`). Sin degradados, sombras, `<style>` ni JavaScript. La regla «CTA único» de
  `CLAUDE.md` es del sitio; los dos botones en el correo los decidió la dueña el 2026-11-06 (§1b).
- **El cron diario** «Camila: preparar el borrador de la campaña»: si pasaron 15 días desde la última enviada (o nunca
  salió ninguna) y no hay ninguna abierta, deja un borrador. **Nunca envía.**

### 3.4 El envío (`models/envio.py`)

Al tocar «Enviar a N clientes», **el servidor revisa todo, aunque llegue por RPC**:

1. el grupo (rol Marketing, Gerencia o administradores);
2. producción (`DCASA_ENTORNO=produccion`; **staging nunca envía**, y un servidor que no lo dice tampoco);
3. que exista `RESEND_CAMPANAS_API_KEY`;
4. que el correo lleve **al menos un botón** (WhatsApp o la tienda en línea);
5. los precios, fotos y existencias **de ahora**: si algo cambió desde que la persona lo vio (la huella del HTML), no
   sale y se le muestra la versión nueva; lo agotado o sin publicar sale de la campaña;
6. **el público** (`_publico`, §3.8): los chips de la campaña cruzados con el permiso, la baja y **el tope de 15 días
   por cliente**; si no queda nadie, no sale;
7. **que las bajas se trajeron recién**: lee todos los contactos de Resend en ese mismo momento (abajo).

Luego toma **el turno de envío** (una campaña a la vez): un candado de **sesión** de la base (`pg_try_advisory_lock`,
que aguanta los COMMIT a mitad de la petición; el de transacción que había antes se soltaba con el primero y dos
campañas podían tocar el segmento a la vez) y se suelta en un `finally` al terminar (si el trabajador muere, PostgreSQL
lo suelta al cerrar la conexión). Además, ninguna otra «aprobada» enviándose en los últimos 10 minutos, mirado otra vez
**después** de confirmar «aprobada» (con la foto nueva de la base). Queda **aprobada** (con quién y cuándo) y se
confirma la base a mitad de la petición, como Sofía: un doble clic u otra persona la encuentran «enviándose» y no la
mandan dos veces. Si el *broadcast* de **cualquier** otra campaña con broadcast en los últimos 3 días **todavía está
saliendo** en Resend (`scheduled` o `queued`; se miran todas, las más recientes primero), no toca el segmento y pide
probar en unos minutos. Trae las bajas, vuelve a calcular el público, **deja el segmento de envío exactamente con esos
destinatarios** (por tandas de 300 salidas y 300 entradas por toque, para no pasar la ventana de «enviándose») y lo
**vuelve a listar**: si queda alguien suscrito que no va en esta campaña, no sale. Crea el *broadcast* (una sola vez;
queda su id), **registra a TODOS los que se dejaron en el segmento** (`dcasa.camila.destinatario`: campaña, correo,
ficha y cuándo; único por campaña y correo; un listado de Resend que tarda no deja a nadie fuera del registro), anota
`envio_intentado` y confirma la base **antes** de llamar a «send»: si otra campaña sale justo después, ya ve el
registro. Lo manda si sigue en borrador; si Resend dice que ya salió, no lo repite (y si esa campaña no tenía registro,
registra lo que hay en el segmento). Si falla antes de crear el *broadcast*, vuelve a borrador con el motivo; si falla
después, queda aprobada y «Reintentar el envío» usa el mismo. **Ningún error la deja a medias**: un error que no es de
Resend también la saca de «enviándose» (deshace lo de esa vuelta, anota el motivo y, sin *broadcast*, vuelve a
borrador). **El registro solo se borra si nunca se llamó a «send»** (`_soltar_destinatarios`): si se llamó, pudo salir
aunque Resend contestara un error o su estado todavía diga `draft`, y un `canceled` puede llegar con media campaña ya
enviada (mejor no mandarles otra que mandarles dos).

**«Reintentar el envío»** revisa primero el *broadcast* que quedó: si en Resend **ya no existe** (404: lo borraron en
su panel) se olvida, la campaña vuelve a borrador y se arma otro (el registro no se suelta); si está en **borrador** y
los precios, fotos o existencias de hoy cambian el correo (o los precios no son de hoy), se **borra en Resend**, vuelve
a borrador y pasa otra vez por la huella: nunca sale con el HTML viejo.

**Una aprobada que quedó trabada** ya no bloquea a las demás (pueden ir varias abiertas), pero no se puede editar. La
descartan **Gerencia o un administrador** (`_descartar`): sin *broadcast* y pasados los 10 minutos de «enviándose», o
con el *broadcast* `canceled`, `draft` o que ya no existe en Resend (el borrador se borra allá con
`DELETE /broadcasts/{id}` para que nadie lo mande). Si en Resend salió o va a salir, no se descarta. Un 404 de Resend
no traba nada: no está saliendo y se puede descartar.

**El diseño del segmento (etapa 2, y por qué).** Con varias campañas y públicos distintos hacía falta mandar a una
parte de los clientes. El plan gratis de Resend Marketing admite **3 segmentos** y **1,000 contactos** (contactos, no
envíos; revisado el 2026-11-06), así que un segmento por campaña o por chip no cabe. Se usa **un solo segmento de
envío, reusado** («D'CASA: campaña que sale (Odoo)»; el id queda en `dcasa_camila.segmento_id`, el mismo de la etapa
1, que se reaprovecha): antes de cada envío queda con los destinatarios de esa campaña y nadie más. Resend no documenta
en qué momento toma la lista de un *broadcast*, por eso: una campaña a la vez, se espera a que el *broadcast* anterior
termine de salir (`queued`/`scheduled`) y se revisa el segmento otra vez justo antes de mandar. Los contactos que
salen del segmento **siguen en Resend** (cuentan para los 1,000, con su baja si la tienen): así una baja hecha con el
enlace de cualquier campaña se lee siempre.

- `_preparar_segmento`: saca **por el id del contacto** a todo el que no va en esta campaña (también correos que Odoo
  no sabe leer, como «o'brien@…», y los dados de baja) y agrega a los que faltan (**solo su correo**: ni nombre ni nada
  más), hasta 300 por toque; si faltan más, pide tocar «Enviar» otra vez.
- `_sincronizar` (también cada hora con el cron «Camila: bajas y contactos con Resend»): lee **todos** los contactos de
  Resend (`GET /contacts`); cada uno dado de baja queda con **baja en todas las fichas con ese correo** (origen
  «correo»), y un contacto suscrito cuyo correo se dio de baja en cualquier ficha de Odoo queda dado de baja en Resend
  (`unsubscribed: true`), por su id (por el correo, otra grafía en Resend daba 404). El cron ya no sube contactos: cada
  campaña sube los suyos al enviar.

**La prueba** («Enviarme una prueba») sale por los correos de siempre (`dcasa_correo`, `RESEND_API_KEY`) con la clase
`prueba` de `politica.py`: solo a correos del equipo, aunque los correos a clientes estén apagados. Lleva una franja
«Prueba» arriba y el enlace de baja vacío. **Con tope** (`dcasa.camila.prueba`): una cada 2 minutos por persona y
hasta 10 en 24 horas, porque gasta el cupo diario de los correos de las facturas. La prueba no cuenta para el tope por
cliente.

### 3.5 Los resultados

- **Chats**: al entrar el mensaje del cliente a Conversaciones (`dcasa.conversacion._despues_de_mensaje`, del lado de
  Odoo), si **el primer mensaje del cliente desde que salió la campaña** trae su marca «DCN-0007» (de una campaña
  **enviada**), ese chat cuenta **una vez** para esa campaña y la conversación queda con la etiqueta **«Vino del
  correo»** (`data/etiqueta.xml`). La conversación de un cliente es una sola, de siempre: un cliente de antes que vuelve
  por el correo cuenta; una marca escrita después de otros mensajes, no. Un error aquí nunca frena el mensaje.
- **Ventas por el chat**: facturas **pagadas** de esos clientes con el chat en los 30 días antes de la factura (la
  misma ventana de las ventas atribuidas de Conversaciones), sin ITBMS.
- **Ventas en la web** (etapa 2, `_ventas_web`): pedidos confirmados de la tienda en línea cuyo `campaign_id` (el UTM
  que Odoo guarda solo cuando alguien llega con `utm_campaign=DCN-0007`) es el código de la campaña, sin ITBMS. Lo
  cuenta el seguimiento de siempre de Odoo; el informe de UTM de Odoo también lo ve.
- El rol Marketing ve **cuántas** ventas; **el monto**, Gerencia y administradores.
- **Entregados, aperturas, clics y bajas**: Resend **sí** los da por API (`GET /broadcasts/{id}/recipients?type=…`); se
  leen cada 6 horas durante 30 días después del envío, o con «Actualizar». Resend avisa que **las aperturas pueden no
  ser exactas** (los programas de correo abren las imágenes solos o las bloquean). Los que se dieron de baja con el
  enlace de esa campaña quedan además con la baja en Odoo.

### 3.6 Brian

`estado_campanas(cuantas?)` (lectura; rol Marketing, Gerencia y administradores): **las campañas abiertas** (nombre,
estado, asunto, a quién va, a cuántos les llegaría, cuántos quedan fuera y por qué, productos con su precio), cuántos
clientes tienen permiso, si está la clave, el tope de 15 días por cliente, por qué no puede salir ahora y los
resultados de las últimas campañas (chats, ventas y ventas en la web; el monto, solo a quien ve la ganancia). Brian no
arma ni envía campañas: eso se aprueba en la pantalla.

### 3.7 Seguridad y lo que no se rompe

- Por RPC (`dcasa_base/tests/test_superficie_rpc.py`): `dcasa.camila.panel`, `nueva`, `armar`, `guardar`,
  `escribir`, `sugerir_productos`, `buscar_productos`, `enviar_prueba`, `enviar`, `descartar`, `actualizar_resultados`
  y `ajustar_enlace_pie` exigen el grupo en el servidor antes de cualquier `sudo`, bloquean la campaña (`FOR UPDATE
  NOWAIT`) y validan cada argumento (ids enteros, chips y botones conocidos, textos con su largo; `ajustar_enlace_pie`
  y descartar una aprobada, además, Gerencia o administrador); `res.partner.action_dcasa_promos_baja` exige una sola
  ficha y poder escribirla; `sale.order.create` y `write` QUITAN «Vino del correo» de lo que se manda (solo lo
  escribe Camila, con una marca de contexto que es un objeto de Python y no viaja por RPC) y `create` lo anota, en un
  savepoint, de qué campaña vino el cliente.
- **Quién llegó por el correo** (`dcasa.camila.llegada`, con la ficha del cliente) lo leen por RPC solo Gerencia y los
  administradores (revisión del 2026-11-06): el rol Marketing ve cuántos chats, no quiénes (la pantalla y Brian cuentan
  con `sudo`). El registro del tope (`dcasa.camila.destinatario`), igual.
- La clave sale solo del entorno (`RESEND_CAMPANAS_API_KEY`): nunca en la base, en un log, en un error ni en `repr`. Los
  errores de Resend se tachan (sin la clave ni correos de personas).
- **A la IA no le llega ningún dato de clientes**: solo datos de productos y la idea que escribe el equipo. Los logs
  de Camila no llevan correos ni nombres (solo ids y cuántos).
- **Marketing no ve montos**: la pantalla, Brian y los resultados dan el monto solo a Gerencia y administradores.
- **Un error de Camila o de Resend nunca hace fallar una venta, un pago ni el correo de una factura**: nada de Camila
  corre dentro de esos flujos; el enlace del pie va en un savepoint; la marca del chat, el contexto para Juan y la marca
  de la cotización también.
- Las pruebas nunca llaman a Resend: `tests/comun.py` trae un Resend falso en memoria.

### 3.8 A quién va: los chips (`models/publico.py`, etapa 2)

Cada campaña guarda sus chips (`publico`, «a,b»; vacío = todos). Se suman (quien cae en cualquiera entra) y **siempre**
se cruzan con el permiso (`_dcasa_promos_con_permiso`: el correo al que dijo que sí, sin baja ni «no contactar» en
ninguna ficha con ese correo, sin el equipo) y con el tope por cliente. Se cuenta por correo: una persona, una vez.

| Chip | Quiénes |
|---|---|
| Todos con permiso | Todo el que dijo que sí. |
| Compraron (90 días) | Una factura de cliente publicada o una venta confirmada en los últimos 90 días. |
| Compraron hace más de 6 meses | Compraron alguna vez y la última compra fue hace más de 180 días. |
| Cotizaron o preguntaron y no compraron | Una cotización (borrador, enviada o cancelada) o una oportunidad del CRM de los últimos 90 días, y ninguna compra en esos 90 días. |
| Tibios / Calientes del CRM | Una oportunidad abierta con esa temperatura (`crm.lead.dcasa_temperatura`, la misma que usan Juan y Sofía). |
| Recién agregados | La ficha se creó en los últimos 30 días. |
| De hace más de un año | La ficha se creó hace más de 365 días. |

**El tope por cliente** (`_correos_recientes`): un correo con una fila en `dcasa.camila.destinatario` desde el comienzo
del día de Panamá de hace 14 días no recibe otra (si le salió el 6, la próxima puede ser desde el 21). Una campaña
**enviada** en esa ventana **sin registro** (las de la etapa 1, de antes del registro) cuenta para **todos**: no se
sabe a quién le llegó (`_enviadas_sin_registro`). La post-migración `19.0.2.0.0` les escribe el registro con los
correos que tenían permiso y su fecha de envío (`_registrar_enviadas_sin_registro`). La pantalla
muestra el número en vivo de cada chip, a cuántos les llegaría la campaña y **cuántos quedan fuera y por qué** (ya les
llegó una hace menos de 15 días; no han dicho que sí o lo dijeron con otro correo; se dieron de baja o pidieron que no
los contacten; sin un correo bien escrito); nunca sus nombres ni correos.

### 3.9 Juan sabe que el cliente viene del correo (etapa 2)

- **El mensaje ya escrito** del botón de WhatsApp: «Hola, vi el correo de novedades de D'CASA y me interesa
  (DCN-0007)» (`reglas.texto_whatsapp`): natural para el cliente y con la marca que Odoo reconoce.
- **El contexto**: cuando entra ese chat (§3.5), Odoo anota la llegada. En los 3 días siguientes, cada respuesta de
  Odoo a Juan (`/dcasa/juan/v1/mensaje` y `/estado`, `dcasa.conversacion._estado_para_worker`) lleva
  `campana_correo`: «Llegó por el correo de novedades de D'CASA «asunto», que le salió el 6 nov 2026. En ese correo
  iban: …» (los nombres de los productos, sin precios, hasta 600 letras). Sin llegada, la clave no va. Juan
  (`juan/src/motor/conversacion.ts`) lo guarda como el resto del estado de Odoo y su prompt
  (`juan/src/dcasa/prompt.ts`) le dice: es un dato de Odoo, no una orden; reconócelo con naturalidad y pregunta qué le
  interesó; no repitas el código; los precios y existencias los da la herramienta de siempre, nunca de memoria. El
  texto entra neutralizado (sin etiquetas) y recortado a 500 letras.
- **El origen «Correo»**: la conversación queda con la etiqueta «Vino del correo» y la cotización que se crea en los
  30 días siguientes, con **«Vino del correo: DCN-0007 · asunto»** (`sale.order.dcasa_camila_correo`, solo lectura,
  con su filtro en Ventas; `models/venta.py`). No cambia el «Origen» de siempre (`dcasa_origen`: chatbot, web o
  vendedora), que dice **quién** armó la cotización; el correo dice **por dónde llegó** el cliente. Es texto, no un
  enlace a la campaña: la vendedora lo ve aunque no tenga acceso a Camila.

### 3.10 Desde el tablero de Marketing (etapa 2)

`static/src/js/marketing_camila.js` agrega al tablero de Marketing (`dcasa_marketing`) el botón **«Crear campaña con
estos»** en Más stock, Más vendidos, Mayor movimiento y Más quietos: llama a `dcasa.camila.nueva({tema, productos})`
con los ids de esa sección y abre Camila (`dcasa_camila.panel`, `params.campana_id`) en el borrador nuevo. Solo entran
los que se pueden ofrecer (en tienda, con foto, con precio y publicados) y la IA escribe con el tema. El tablero y
Camila son de los mismos grupos (rol Marketing, Gerencia y administradores) y el servidor lo exige igual (`_exigir`).
En el tablero no hay sección de «lo nuevo»: esa campaña se arma desde «Nueva campaña» en Camila.

### 3.11 La lista crece sola (etapa 1b: `models/permiso.py`, `models/pregunta.py`, `models/juan_permiso.py`)

- **Se activa sola** (`permiso.py`): `res.partner.create` (una sola ficha, comercial, con correo) y `write` (una sola
  ficha, con `email` en lo que se escribe) llaman a `_dcasa_promos_activar_al_agregar_correo(antes)`: si el correo
  bien escrito de la ficha comercial cambió (de nada a algo, o a otro) y `_dcasa_promos_motivo_para_no_activar()` no
  dice nada (empresa, equipo, baja o «no contactar» por correo en cualquier ficha, un «no» de cuando sea, ya
  activada o ya confirmada), anota `al_agregar_correo` con quién lo agregó. Va en un savepoint: si falla, el correo se
  guarda igual. `_dcasa_promos_auto_permitido()` exige un `uid` del equipo (aunque el código use `sudo`) y que no sea
  `SUPERUSER_ID`, `import_file`, `install_mode`, el registro cargando ni `dcasa_promos_sin_auto` (lo pone
  `res.users.create`). Juan no es del equipo: su herramienta la llama aparte, con Juan como quien lo agregó.
- **Orígenes y campos**: `venta`, `juan_whatsapp`, `al_agregar_correo` (el automático; nunca `tienda`). Un «sí» que no
  es el automático reemplaza al automático con el mismo correo (es la persona que lo confirma; botón
  `action_dcasa_promos_confirmar` de la ficha) y borra el «no». El «no»: `_dcasa_promos_anotar_no(origen, usuario)`
  (orígenes `ficha`, `venta`, `juan_whatsapp`) quita el permiso y anota `dcasa_promos_no_fecha`, `_no_origen` y
  `_no_usuario_id`; desmarcar la casilla lo usa. `dcasa_promos_referencia` (la venta, el pago o «Chat N · mensaje M»)
  y `dcasa_promos_pregunta_fecha` (la última vez que salió el cuadro). Todos protegidos como los demás (solo el
  sistema). La fusión de fichas trae el «no» y el último cuadro más recientes; si quedan un «sí» y un «no», gana el
  más reciente.
- **En la venta** (`pregunta.py`): `sale.order.action_confirm` y `account.payment.register.action_create_payments`,
  DESPUÉS de `super()`, con la marca `dcasa_camila_preguntar` (solo la ponen los botones de la pantalla,
  `views/pregunta_views.xml`), una sola venta, un usuario del equipo y sin `sudo`, devuelven el cuadro
  `dcasa.camila.pregunta` según `_dcasa_promos_que_preguntar()`: `casilla` (con correo: `quiere` activada salvo un
  «no» viejo; «Listo» → `action_listo`) o `pregunta` (sin correo: «Sí», «No»; con «Sí», «Guardar el correo y anotar
  el sí» o «No dio su correo»). Armarlo va en un savepoint; si falla, devuelven lo de siempre. Lo que seguía (el
  cuadro «Imprimir documentos» después de pagar) sale al contestar. Antes de anotar, el servidor revisa que la venta
  esté confirmada o la factura publicada, que quien contesta pueda leerla y que la ficha sea la de ese cliente (el
  cuadro se podría crear por RPC). El correo se escribe en la ficha como lo haría la persona (las reglas de contactos).
- **Juan** (`juan_permiso.py`, solo para el usuario técnico de Juan): `guardar_correo` (en Brian
  `juan_guardar_correo`: el correo tiene que aparecer en lo que escribió el cliente en las últimas 24 horas, la ficha
  no puede tener otro, ni ser un correo del equipo ni el de otra ficha; lo guarda con las reglas de contactos y activa
  las novedades con la referencia del mensaje; la respuesta le dice a Juan qué contarle) y `no_quiere_novedades`
  (`juan_no_quiere_novedades`: anota el «no» `juan_whatsapp`, siempre). En `/mensaje` y `/estado` va
  `permiso_correo`: «activo» o «sin_correo» (si no, la clave no va); el prompt de Juan dice qué hacer con cada uno
  (`juan/src/dcasa/prompt.ts`).
- **El pie de la campaña** (`correo_templates.xml`): «Te llega porque nos diste tu correo en D'CASA. ¿No quieres más?
  Date de baja aquí» (el enlace de Resend).

## 4. Pruebas

`addons/dcasa_camila/tests/`: reglas puras (`test_reglas.py`), el cliente de Resend (`test_resend.py`), el permiso, la
baja, la fusión y lo de Sofía (`test_permiso.py`), la campaña y el envío (`test_campana.py`: productos, precio con y sin
tarifa, IA y texto fijo, la marca del correo, el cron, staging, sin clave, 15 días por cliente, varias abiertas, precio
cambiado, agotado, Resend que falla y reintento, la prueba), el enlace «Sí, quiero» (`test_enlace.py`, con el
servidor: GET no anota, POST con CSRF sí, firma, correo cambiado, baja), los resultados y Brian (`test_resultados.py`)
y en el navegador (`test_navegador.py`): **la pantalla baja con scroll** (`overflow-y: auto` y llega abajo con un
borrador largo) en la computadora y en el celular sin scroll de lado, «Previsualizar» en su ventana, editar y quitar,
«Cambiar» un producto en la ventana de productos, «Escribir con IA» (y el aviso con «Reintentar» si la IA falla), los
chips y los botones, «Crear campaña con estos» desde el tablero de Marketing y la casilla de la ficha.
`test_revision.py` tiene una prueba por cada hallazgo de la revisión adversarial del 2026-11-06 (la baja por correo y no
por ficha, el enlace solo a la ficha firmada y el interruptor, la frase exacta de Sofía, el permiso del correo, nadie de
más en el segmento, la campaña trabada, la casilla una a la vez, la revisión de marca más dura, los tokens raros, el
tope de pruebas, las bajas de los resultados y la marca en el primer mensaje); todas fallaron sobre el código de antes.
`test_etapa2.py` (etapa 2): el tope por cliente (el registro, que se suelta si Resend no la mandó, una a la vez,
esperar si la anterior sigue saliendo, el segmento exacto con un chip), los chips y los que quedan fuera, «Nueva
campaña» (cada tema, el tablero solo con lo elegible, desde una idea con y sin IA), el redactor (datos reales del
producto y ningún dato de clientes, la revisión de marca, la IA que falla), los botones del correo (por defecto, la
tienda, los dos, ninguno no sale, sin enlaces a productos, las redes del sitio, las ventas web por UTM con y sin monto)
y Juan (con el servidor: `campana_correo` en `/mensaje` y `/estado`, la etiqueta, nada sin campaña ni pasados los 3
días, la cotización con la marca). En `juan/`: `test/dcasa/campana-correo.test.ts`.
`test_revision2.py`: una prueba por hallazgo de la revisión adversarial de la etapa 2 (2026-11-06), todas en rojo sobre
el commit `49e5f87`: el turno de envío que aguanta los COMMIT (con dos conexiones de verdad) y se suelta siempre, el
segmento por tandas, las enviadas de la etapa 1 sin registro y su migración, el registro que no se suelta con
`canceled` ni si se llamó a «send», «ya salió» sin registro, «todavía saliendo» con todas las campañas, el 404 de
Resend, registrar a todos los del segmento, el reintento que no manda precios viejos, el tope de IA por persona,
«Vino del correo» por RPC, la revisión de marca y quién llegó por el correo.
`test_etapa1b.py` (etapa 1b, primero en rojo sobre el código de antes): se activa sola al crear la ficha con correo,
al agregarlo o cambiarlo y con «Guarda sus datos» de Sofía (con el origen honesto y quién); nada hacia atrás; nunca
con baja o «no contactar» en otra ficha, después de un «no» (desmarcar lo anota), importando, en bloque, instalando,
por el sistema, en la ficha de un usuario nuevo, una empresa o un contacto hijo; un fallo al activarla no traba
guardar el correo; confirmar lo que se activó solo. En la venta: la casilla activada y la venta ya hecha, desactivarla
anota el «no», la activada sola sigue diciéndolo y no vuelve a salir, pasado el plazo de un «no» sale desactivada (un
ajuste), sin la marca o con `sudo` no sale, a quién no le sale, sin correo lo pide y lo guarda o anota el «no», un
fallo al armarlo no traba la venta, el cuadro falso de otro cliente, al pagar sigue «Imprimir documentos». Juan:
guarda el correo que escribió el cliente y se activa (con Juan y el mensaje), nunca uno inventado ni cambia el que
tiene ni activa uno viejo, con un «no» o una baja guarda el correo sin activar, honra siempre un «no» (también antes
del correo), no tiene cómo activarlas, y de punta a punta por la API (como el Worker). Los conteos por camino y, en el
navegador, el cuadro al confirmar (sin la X y con la regla del scroll) con la casilla activada en la computadora y,
pidiendo el correo, en el celular. `test_campana.py`: el pie nuevo. En `juan/`: `test/dcasa/permiso-correo.test.ts`.

## 5. Lo que queda para después

- Volver a darse de alta después de una baja (lo hace el cliente; hoy la baja es final). El «sí» en la web (checkout y
  Mi cuenta: origen `web`; hoy la web pública y el portal no activan solas las novedades, §1c).
- **Después:** el saludo de **cumpleaños** con su beneficio de Socios (de `puntos.json`; si allí está `null` o
  `PENDIENTE`, no se menciona) y **«Tu cotización sigue aquí»** (estaban pensados para la etapa 2; la dueña pidió
  primero la etapa 2 «a lo grande» de §1b).
- **Etapa 3:** la página web (revisar cada mañana la tienda y proponer arreglos).
- La **política de privacidad** (`website_dcasa`, `/privacidad`) todavía no nombra las novedades por correo ni a Resend
  como proveedor: antes de la primera campaña, que la revise la dueña (y el abogado).
- Si los contactos pasan de 1,000 (plan gratis de Resend Marketing), Resend no deja enviar hasta subir de plan: los
  contactos que dejan de tener permiso podrían borrarse de Resend (hoy se quedan, con su baja).

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
- **Campañas (marketing):** plan gratis **hasta 1,000 contactos** y **3 segmentos**, sin tope de correos enviados; el
  siguiente cuesta **$40 al mes** (hasta 5,000 contactos, segmentos sin límite).

## 8. La API de Resend (revisada en la documentación oficial el 2026-11-06)

`https://resend.com/docs/llms.txt` › Broadcasts, Contacts, Segments («Audiences are now called Segments»):

| Para qué | Llamada |
|---|---|
| El segmento | `GET /segments`, `POST /segments {name}`, `GET /segments/{id}/contacts?limit=100&after=…` |
| Todos los contactos | `GET /contacts?limit=100&after=…` (sin `segment_id`: todos; así se leen las bajas de cualquier campaña) |
| Un contacto | `POST /contacts {email, segments: [{id}]}`; si ya existía, `POST /contacts/{email}/segments/{id}`; sacarlo, `DELETE /contacts/{id o email}/segments/{id}`; la baja, `PATCH /contacts/{id o email} {unsubscribed: true}` («Either id or email must be provided»: Camila usa el id que lista el segmento) |
| La campaña | `POST /broadcasts {segment_id, from, subject, html, reply_to, name}` (borrador), `POST /broadcasts/{id}/send`, `GET /broadcasts/{id}` (`status`: draft, scheduled, queued, sent, canceled; un 404 = ya no existe, lo borraron en el panel); `DELETE /broadcasts/{id}` solo si no salió (draft o scheduled) |
| Resultados | `GET /broadcasts/{id}/recipients?type=delivered\|opened\|clicked\|unsubscribed`, filas `{id (cursor), contact_id, email}` |
| Límite | 10 peticiones por segundo por equipo (429 con `retry-after`): pausa corta entre llamadas y reintentos |
| La baja | `{{{RESEND_UNSUBSCRIBE_URL}}}` en el HTML: Resend pone un enlace único por persona y campaña |
| Permiso de la clave | `sending_access` contesta 401 `restricted_api_key` en contactos y campañas: hace falta `full_access` |
