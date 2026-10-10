# Juan en Odoo: la bandeja de conversaciones

Guía sencilla para la dueña y las vendedoras. El contrato técnico con el Worker está en [`JUAN.md`](JUAN.md); la
pantalla de conversaciones (panel) estaba especificada en [`JUAN_PANEL.md`](JUAN_PANEL.md) y ya está construida. Aquí
solo está lo que **ves y haces en Odoo**, y al final una parte corta para quien instala o programa.

## Qué es

**Juan** es el asistente que contesta a los clientes por WhatsApp (y Telegram, Messenger, Instagram) con el nombre
**«el equipo de D'CASA»**. Contesta a cualquier hora. Cuando un cliente necesita a una persona, el asistente se
calla y le toca a una vendedora. **Odoo es la memoria de todo**: cada conversación, cada cliente y cada oportunidad
quedan guardados aquí.

## Dónde está

Menú **Conversaciones** (el ícono del globo de chat).

| Opción | Quién | Para qué sirve |
|---|---|---|
| **Conversaciones** | Ventas | **La pantalla de trabajo**: lista, chat y ficha del cliente en una sola vista (ver «La pantalla de Conversaciones»). |
| **Resumen** | Ventas | Los números del día, de 7 y de 30 días. |
| **Costos de IA** | Gerencia | Cuánto cuesta que el asistente conteste y cómo va el mes frente al tope. |
| **Conexiones** | Gerencia | Cómo está cada canal, el QR de WhatsApp, reiniciar y desvincular. |
| **Bandeja** | Ventas | La bandeja de siempre, en tres columnas: *Con el asistente*, *Con una vendedora* y *Cerrada*. |
| **Mensajes por enviar** | Ventas | Lo que escribiste desde Odoo y todavía no salió (ver «Si algo falla»). Normalmente está vacío. |
| **Preguntas sin respuesta** | Gerencia | Lo que los clientes preguntaron y el asistente no supo contestar (ver «El asistente aprende»). |
| **Conocimiento del bot** | Gerencia | Los textos que el asistente puede usar para contestar (horario, ubicación, Socios, garantía…). |
| **Configuración › Ajustes de Juan** | Gerencia | Cómo se presenta, cuándo contesta, qué IA usa y cuánto insiste. |
| **Configuración › Etiquetas** | Gerencia | Las etiquetas de colores para clasificar conversaciones. |
| **Configuración › Respuestas rápidas** | Gerencia | Los atajos con «/» (`/horario`, `/ubicacion`…). |

La tarjeta de cada conversación muestra a la persona, el canal, las etiquetas, el último mensaje y quién la atiende.
Una etiqueta azul **«Espera tu respuesta»** marca las que el cliente escribió y nadie ha contestado.

## La pantalla de Conversaciones

Es la pantalla de trabajo de las vendedoras: **todo en una sola vista**, como un WhatsApp Web pero dentro de Odoo y con la
ficha del cliente al lado. Se abre en *Conversaciones › Conversaciones*. Tiene tres columnas:

| Columna | Qué hay |
|---|---|
| **Izquierda: la lista** | Todas las conversaciones, las más recientes primero. Cada una muestra a la persona, el canal, las etiquetas, el último mensaje, quién la atiende y cuántos mensajes tienes sin leer. |
| **Centro: la conversación** | Los mensajes como un chat y, abajo, la caja para responder. |
| **Derecha: la ficha del cliente** | Quién es, si es Socio y cuántos puntos tiene, sus oportunidades y compras, las etiquetas y a quién se la asignaste. |

Se actualiza **sola**: cuando entra un mensaje, o alguien toma una conversación, aparece sin recargar nada.

### La lista

* **Buscar**: escribe un nombre, un celular o una palabra que dijo el cliente. Busca en todos los mensajes.
* **Filtros rápidos**: **Mías** (las que atiendes tú), **Sin leer**, **Con oportunidad** (ya tienen una venta anotada en CRM) y
  **Más filtros** (canal, estado y etiqueta). **Quitar filtros** deja todo como estaba.
* **Estados** (siempre con palabra, no solo color): **Necesita atención** (el cliente escribió y nadie ha contestado; franja azul
  oscuro con letras amarillas), **Asistente** (contesta Juan), **Una vendedora** (la atiende una persona) y **Cerrada**.
* Baja y cargan **30 más** solas. Con las flechas **↑ ↓** del teclado pasas de una conversación a otra.

### La conversación

* **Cada quien en su color**: el cliente a la izquierda; el asistente en azul claro; las vendedoras en azul fuerte. Las horas son de
  Panamá. Un renglón gris es un **aviso del sistema** («Ana tomó la conversación»).
* **Foto de perfil** del cliente, en la lista, en la cabecera de la conversación y en la ficha (si no hay foto, o el cliente no la
  deja ver, se ven sus iniciales). Ver «Privacidad» más abajo.
* **Notas internas**: burbuja con borde punteado y la leyenda **«El cliente no la ve»**. Sirven para hablar entre vendedoras.
* **Fotos**: salen como miniatura; un clic las **amplía** (flechas ← → para pasar de una a otra, **Esc** para cerrar). Los
  documentos (PDF, Word, Excel) se descargan. En un comprobante de pago o un documento de identidad que mandó el cliente puedes
  pulsar **Es un comprobante**: así el asistente nunca lo ve (**Ya no es sensible** lo deshace).
* **Ver mensajes anteriores** trae los 50 anteriores. Si estás leyendo mensajes viejos y entra uno nuevo, no te mueve la pantalla:
  aparece un botón **«1 mensaje nuevo»** (o «N mensajes nuevos») para bajar cuando quieras.
* Arriba: **Ficha** (muestra u oculta la ficha, útil en pantallas medianas y en el celular) y **Cerrar** la conversación.
* Si un mensaje tuyo no salió, dice **«Por enviar»** y tiene el botón **Reintentar**.
* Mientras el asistente trabaja se ve debajo del último mensaje. Primero, unos segundos de **«El asistente está preparando la
  respuesta…»** (espera a que el cliente termine de escribir; es una estimación) y, cuando el Worker avisa que de verdad empezó,
  **«El asistente está escribiendo…»**, que se apaga cuando termina o cuando llega su respuesta (y sola al minuto si el aviso
  de «terminó» se pierde). Si el asistente no contesta (pausa, apagado, una persona atendiendo), no aparece nada.

### La caja de respuesta

Arriba de la caja, una barra dice **quién atiende**:

* **Atiende el asistente** → botón **Atender**: la conversación pasa a ti y Juan se calla.
* **Atiendes tú. El asistente vuelve a las 4:30 p. m. (en 1 h 20 min)** → botón **Devolver al asistente**. Puedes dejarle una nota
  corta («ya quedó la visita del sábado»); la lee hasta que otra persona tome la conversación. Cada mensaje tuyo renueva la pausa.
* **Cerrada** → si escribes, se reabre y la atiendes tú.

Abajo, la caja y sus botones:

| Botón | Qué hace |
|---|---|
| **Respuesta / Nota interna** | Cambia entre hablarle al cliente y escribir una nota que el cliente no ve. La nota tiene otro color y su botón dice **Guardar nota**. |
| **Adjuntar** | Elige fotos o documentos (también puedes **arrastrarlos y soltarlos** sobre la conversación o **pegar** una imagen). Se ven en miniatura antes de enviar y se pueden quitar. Hasta 10 MB cada uno. Aceptados: fotos (JPG, PNG, WebP, GIF), PDF, Word, Excel, texto y CSV. |
| **Foto del catálogo** | Busca un producto por **nombre o código** y manda su foto. Ver abajo. |
| **Cotización** | Manda la cotización del cliente en PDF. Ver abajo. |
| **Rápidas** | Abre tus respuestas rápidas. También sirve escribir **/** en la caja: salen las que empiezan con lo que escribas; **↑ ↓** eligen, **Enter** o **Tab** usan la elegida y **Esc** cierra. El texto ya sale con el nombre del cliente. |
| **Programar** | Deja el mensaje escrito para que **salga solo** el día y la hora que elijas (de 1 minuto a 30 días; atajos «En 1 hora» y «Mañana 8:00 a. m.»). Con el selector abierto, el botón dice **Programar** y no deja enviar sin hora (no se manda «ya» por descuido). Lo programado se ve **aparte, arriba de la caja** («Se envía mañana 8:00 a. m.»), no en el hilo, con **Cancelar** (quien lo programó o Gerencia). Hasta su hora **no pasa nada**: el asistente sigue atendiendo y la conversación no cambia de dueña. A la hora (la revisión corre cada 5 minutos) sale como un mensaje nuevo, al final del hilo, la conversación pasa a quien lo programó y queda un aviso. Si el Worker no responde en ese momento, queda «por enviar» y se reintenta. |
| **Sugerir** | Le pide a Juan **un borrador** de respuesta. Lo deja escrito en la caja para que lo leas, lo cambies y lo envíes tú; **nunca se envía solo**. Si quitó algo que no debía (una foto, por ejemplo) o dejó algo por confirmar, te lo avisa. |
| **Enviar** | Manda el mensaje. **Enter** envía; **Mayús + Enter** salta de línea; **Ctrl + Enter** también envía. En el celular solo envía el botón. |

**Foto del catálogo.** Escribe lo que buscas («cama queen» o el código). Cada producto muestra su foto, el precio con **«+ ITBMS»**,
las medidas y si está **DISPONIBLE**, con **POCAS** unidades o **AGOTADO**. La pantalla **nunca** muestra cuántas unidades hay ni lo
que costó. Con **Enviar foto** sale la foto y, debajo, el pie ya armado (nombre, precio + ITBMS, medidas y enlace al producto).
**Galería** deja elegir varias fotos del mismo producto y **Revisar antes de enviar** no manda nada: deja las fotos y el pie en la
caja para que los edites. Solo salen productos **publicados**. Las fotos se mandan reducidas (1024 px) y con una dirección que
**vence a los 15 minutos**.

**Cotización.** Busca la **cotización abierta más reciente** de ese cliente y la muestra (productos, subtotal, ITBMS, total y hasta
cuándo vale). **Enviar el PDF** la manda con un mensaje que puedes cambiar. Si el cliente no tiene ninguna abierta, puedes **crear
un borrador** eligiendo productos del catálogo; el borrador **nunca se confirma**: eso lo decide una persona en Ventas. **Abrir en
Odoo** la abre completa. Cada vendedora ve las cotizaciones que ya podía ver en Ventas.

### La ficha del cliente

* **Socios D'CASA**: si es Socio y cuántos puntos tiene. **Solo lectura**: los puntos se mueven desde el programa de Socios, no desde
  aquí.
* **Atiende**: asigna la conversación a otra vendedora. Queda un aviso en el hilo.
* **Etiquetas**: pon o quita (un clic cada una).
* **Oportunidades**, **Compras recientes** y **Seguimiento** (con el botón para **cancelar** el seguimiento automático).
* **Crear oportunidad**: deja la venta anotada en CRM, ligada al cliente y a la conversación.
* **Notas internas** y **Qué sabe el asistente de esta persona**: nombre, productos por los que preguntó, etiquetas y la última vez
  que habló.

### En el celular

La pantalla se vuelve **una columna a la vez**: primero la lista; al tocar una conversación se ve solo el chat, con la **caja de
respuesta fija abajo**; el botón **Volver** regresa a la lista y **Ficha** abre la ficha a pantalla completa. Todos los botones miden
al menos 44 píxeles (cabe el pulgar). El catálogo y la cotización suben desde abajo como una hoja.

### Teclado: resumen

| Tecla | Dónde | Qué hace |
|---|---|---|
| **↑ ↓** | Lista | Pasa de una conversación a otra |
| **Enter** | Caja | Envía (en el celular, no) |
| **Mayús + Enter** | Caja | Salta de línea |
| **Ctrl + Enter** | Caja | Envía siempre |
| **/** | Caja | Abre las respuestas rápidas |
| **↑ ↓ · Enter · Tab · Esc** | Respuestas rápidas | Elegir · usar la elegida · cerrar |
| **← →** | Foto ampliada | Foto anterior o siguiente |
| **Esc** | Foto ampliada, catálogo y cotización | Cierra |
| **Tab** | Todas | Recorre los botones; el que tiene el foco se ve con un contorno azul |

### Resumen, Costos de IA y Conexiones

Tres pantallas hermanas, con la misma barra de arriba para pasar de una a otra.

* **Resumen** (todo el equipo de ventas). Los números de **Hoy**, **7 días** o **30 días** (hora de Panamá): **mensajes** (de
  clientes, del asistente y de vendedoras), **clientes únicos**, **resueltas sin una persona** (las que el asistente cerró solo),
  **oportunidades creadas**, **ventas atribuidas** (facturas pagadas, sin ITBMS, de clientes que hablaron con el asistente; es una
  atribución aproximada, no una prueba de que el asistente vendió) y **primera respuesta** (en cuánto tiempo, la mitad de los
  clientes recibe respuesta). Lo que no se puede calcular se muestra como «—»: no se inventa. Si hay conversaciones esperando
  respuesta, un aviso lleva directo a ellas.
* **Costos de IA** (**solo Gerencia**). El **gasto del mes** frente al **tope** (30 USD por defecto), con una barra que dice «Vas
  bien», «Vas a pasar el tope» o «Tope alcanzado» (con ícono y palabra). Debajo, la frase **«Si sigues a este ritmo, terminarás el mes
  en…»**, el gasto **por día** (un botón lo pasa a tabla) y **por modelo**. Al llegar al tope, el asistente baja al modelo económico;
  **nunca se queda sin contestar**. Si un modelo no tiene precio cargado en *Ajustes de Juan*, el gasto de ese modelo es una
  estimación alta y la pantalla lo dice. El **gasto por día** lo lleva el propio Worker, día a día (hora de Panamá), desde que se
  desplegó esta versión: no depende de que alguien abra la pantalla. Los días anteriores se arman con la foto del gasto que Odoo
  guarda cada noche; un día sin foto ni dato del Worker sale como «sin dato» y no se adivina.
* **Conexiones** (**solo Gerencia**). El estado **en vivo** de cada canal (Conectado, Desconectado, Faltan claves, Apagado), con
  ícono y palabra. En **WhatsApp (QR)**:
  * **Mostrar el QR para vincular**: aparece el código para escanearlo desde el teléfono de la tienda (*WhatsApp › Ajustes ›
    Dispositivos vinculados › Vincular un dispositivo*). Se renueva solo y se avisa cuando WhatsApp queda conectado. El código
    **no se guarda ni se escribe en ningún registro**.
  * **Reiniciar**: apaga y vuelve a prender el puente en menos de un minuto; la sesión se conserva (no pide QR). Antes pregunta.
  * **Desvincular**: cierra la sesión de WhatsApp; para volver hay que escanear un QR nuevo. Es el botón rojo y siempre pregunta.
  Quién reinició o desvinculó, y cuándo, queda en el historial de *Ajustes de Juan*. Además se ve qué **claves faltan en el Worker**
  (**solo sus nombres**, nunca su valor: la dueña las pega en el panel de Cloudflare) y lo que Odoo sabe de sí mismo.

**Si ves «Falta conectar el bot».** Odoo todavía no sabe dónde está el Worker de Juan o no tiene su clave. Quien instala carga las
variables `JUAN_URL` y `JUAN_WORKER_TOKEN` (ver «Para quien instala»). Mientras tanto, la lista y los chats funcionan igual con lo
que ya hay en Odoo; **Sugerir**, **Costos de IA** y **Conexiones** avisan que falta conectar el bot y el **Resumen** muestra los
números que sí tiene Odoo.

### Lo que todavía no hace

* El gasto de IA **por día** de antes de esta versión solo existe donde Odoo guardó su foto diaria.

## Atender a un cliente (en la bandeja de siempre)

1. Abre la conversación: la ves **como un chat**. A la izquierda lo que dice el cliente; a la derecha el
   asistente (azul claro) y las vendedoras (azul fuerte). Las horas son de Panamá. Las fotos y los archivos se abren con un clic.
2. Pulsa **Atender**. El asistente se queda **en silencio** con esa persona y la conversación pasa a ti.
3. Escribe abajo en **Tu respuesta** y pulsa **Enviar**. Puedes **adjuntar** una foto o un PDF (por ejemplo, una cotización).
   Si escribes sin haber pulsado «Atender», Odoo la toma por ti.
4. Cada mensaje tuyo **renueva la pausa** (por defecto 2 horas). Si te olvidas, cuando la pausa vence el asistente
   vuelve a contestar solo.
5. Cuando termines, pulsa **Devolver al asistente** (o **Cerrar** si ya no hay nada más). Si el cliente escribe
   de nuevo a una conversación cerrada, se reabre con el asistente.

Si escribes **desde el teléfono** (la app de WhatsApp), el asistente también se calla solo.

Otros botones: **Crear oportunidad** (deja la venta anotada en CRM, ligada al cliente y a la conversación;
si ya hay una abierta de los últimos 30 días, no crea otra) y **Reintentar envíos**.

**Notas internas y avisos.** Dentro de la conversación hay dos cosas que el cliente **nunca** ve:

* **Adjuntar un comprobante a una factura o a un pedido:** debajo de cada archivo que manda el cliente está el botón
  **Adjuntar a factura o pedido**. Se abre una lista con los pedidos y facturas **de ese cliente** (los más recientes); al elegir
  uno, el archivo se **copia** al historial de ese documento (con una nota de quién lo adjuntó) y queda un aviso en la
  conversación. El original se queda en el hilo, adjuntarlo dos veces no lo duplica, y la IA nunca lo ve. Para facturas hace
  falta el permiso de Facturación (el rol Vendedora lo trae). Un comprobante falso no se detecta mirando la imagen: **verifica
  el pago en el banco** antes de entregar;
* las **notas internas** que escribimos entre vendedoras (borde punteado), que además quedan en la ficha del cliente.
  **Mencionar con @:** en una nota, escribe `@` y elige a una compañera del equipo de ventas (con las flechas y Enter, o con
  un clic). Al guardar, a ella le llega un aviso en Odoo (su bandeja) y por Telegram (si vinculó el suyo con Brian); la nota
  muestra «Mencionó a…». Si pones una **fecha** en «Tarea para el…», además le queda una **tarea** con esa fecha en la
  conversación. Se puede mencionar hasta a 8 personas por nota, no a ti misma, y solo a gente de ventas;
* los **avisos del sistema**, una línea gris por cada cosa que pasó: «Ana tomó la conversación», «El asistente pasó la
  conversación a una vendedora. Motivo…», «Se creó la oportunidad…», «Seguimiento n.º 1 enviado», «Ana cerró la conversación».

**Nota para el asistente.** Al **devolver** la conversación puedes dejarle una nota corta (hasta 500 letras): «ya
quedó la visita del sábado». El asistente la lee en cada respuesta hasta que otra persona tome la conversación.

**Sin leer.** Cada persona del equipo lleva su propia lectura: lo que el cliente escribió y tú aún no abriste cuenta
como «sin leer» solo para ti. (Los contadores y el filtro **Sin leer** están en la pantalla de Conversaciones.)

Todo lo que se dice queda también en la **ficha del cliente** (Contactos), en el chatter, como nota interna. Los
**comprobantes de pago** y **documentos de identidad** se guardan ahí para que los revise una vendedora; **no se le muestran a la IA**
(un adjunto se marca como *sensible* y la burbuja lo dice).

## Qué hace el asistente por su cuenta

Consulta el catálogo real (solo productos **publicados**), dice el precio **«+ ITBMS»** y la disponibilidad solo como
*disponible*, *pocas* o *agotado* (nunca el número). Explica Socios con las cifras reales de `puntos.json` y,
si el cliente da su PIN, le dice su saldo. Busca en el **conocimiento del bot** lo que el equipo escribió. Deja anotada
la oportunidad. **Puede poner una etiqueta** a la conversación, pero solo de las que tú creaste. **No inventa**
precios, plazos ni promesas; entregas, flete, financiamiento, apartados y descuentos **siempre** los confirma una
vendedora. No puede tocar puntos, precios, existencias, facturas ni pagos.

Cuando el cliente escribe *persona* (o el asistente decide pasarlo), Odoo crea una **actividad** para la vendedora
responsable y avisa por **Telegram** a quienes tengan su Telegram vinculado con Brian. Dentro del horario el cliente
recibe «ya avisé a una vendedora»; fuera del horario, «te escribe mañana a primera hora, desde las 8:00 a. m.».

## Seguimiento (decisión de la dueña)

El seguimiento es **solo para quien quiso comprar y nunca compró**. «Quiso comprar» quiere decir que hay una
**oportunidad viva** en el CRM ligada a la conversación (ni ganada ni perdida): el asistente la crea solo cuando el
cliente muestra interés concreto (un mueble puntual, un presupuesto, quiere ir a la tienda) y tú puedes crearla con el
botón *Crear oportunidad*. Una persona que solo preguntó la hora o la dirección no recibe seguimiento. Si marcas la
oportunidad como **perdida** (o **ganada**), el seguimiento se cancela.

A quien tiene esa oportunidad y **no volvió a escribir**, el asistente le escribe **como máximo dos veces**:

* la **primera**, 5 horas después del último mensaje, **solo en horario laboral** (8:00 a. m. a 5:00 p. m., todos los
  días, hora de Panamá; si cae fuera, espera al siguiente horario laboral);
* la **segunda**, 5 días después de la primera, también en horario laboral;
* **ninguna** si la persona **ya es cliente** (tiene alguna factura pagada, de antes o de después de la
  conversación: a quien ya compra no se le hace seguimiento) o si
  **pidió que no la contacten** (se marca sola cuando lo escribe, y también la puedes marcar tú en la ficha:
  pestaña *Conversaciones › No contactar*);
* tampoco si la atiende una persona, si la conversación está cerrada o si el asistente está apagado.

Si el cliente vuelve a escribir, el conteo empieza de nuevo. En cada conversación, la pestaña **Seguimiento** muestra
cuántos se enviaron y cuándo toca el próximo. **Odoo decide quién y cuándo; el Worker redacta y envía.**

## El asistente aprende: conocimiento, preguntas sin respuesta y lecciones

**Conocimiento del bot** (*Conversaciones › Conocimiento del bot*). Es lo único que el asistente puede decir sobre
horario, ubicación, Socios, garantía, cómo comprar… cuando se lo preguntan. Cada entrada tiene un título, palabras
con las que la gente la pregunta y su texto. Dos vienen **automáticas** y no hay que editarlas: *Dónde estamos,
horario y WhatsApp* (se arma con la dirección de la empresa, el WhatsApp del sitio y el horario de Ajustes) y
*Socios D'CASA* (sale de `puntos.json`). Así no se quedan viejas ni repiten una cifra.

Las de **garantía** y **cómo se hace una compra** vienen **inactivas** y con la nota «pendiente de aprobación de la
dueña»: son textos provisionales de los términos del sitio, pendientes de revisión del abogado, y no traen ningún
plazo porque ninguno está aprobado. Tú decides si las activas (botón **Activar**) o las reescribes. Nada de
entregas, flete, financiamiento ni apartados: eso siempre lo confirma una vendedora. Cada cambio queda en el historial.

**Preguntas sin respuesta** (*Conversaciones › Preguntas sin respuesta*). Cuando el asistente no sabe, anota la pregunta
y le dice al cliente que una vendedora se la confirma. Las parecidas se **agrupan** y cuentan cuántas veces se
repitieron. Con el botón **Convertir en conocimiento** abres la pantalla de conocimiento ya con la pregunta; al guardar,
la pregunta queda *atendida* y el asistente la sabrá desde ese momento. También puedes **Descartar** una pregunta.

*Lo que ya contestó una vendedora.* Cada noche (03:10 de Panamá) Odoo busca, para cada pregunta *nueva*, lo que una vendedora le
escribió después al cliente en esa conversación (hasta 7 días, el mensaje que comparte más palabras con la pregunta; un saludo suelto
o un mensaje de otro tema no cuenta). Lo guarda en la pregunta, con **quién** lo escribió y **cuándo**, sin correos ni números largos
(celulares, cédulas, cuentas) y avisando si menciona **dinero o números** (hay que confirmarlos). Al apretar **Convertir en conocimiento**
la entrada nace con ese texto como **borrador inactivo**: el asistente no sabe nada de eso hasta que Gerencia lo revisa y lo **activa**.
No lo redacta ninguna IA: son las palabras de la vendedora, y por eso no inventa nada.

*Buscar por significado* (opcional, **apagado**; *Ajustes de Juan › Buscar en el conocimiento por significado*). Las palabras no
encuentran «¿Se llevan el colchón viejo?» si la entrada dice «Retiro de lo usado». Con esto encendido, cada hora Odoo le pide al Worker
(`POST /odoo/embeber`, modelo `@cf/baai/bge-m3` de Workers AI, dentro de la cuenta de Cloudflare de D'CASA) una «huella de
significado» de cada entrada **activa** nueva o editada (se guarda en `dcasa.conocimiento.vector`; solo la ve Gerencia) y, al buscar,
las **palabras mandan** y el significado solo **completa los lugares que quedaron vacíos** (de las 3 que devuelve la herramienta), con
las entradas cuya huella se parece lo suficiente a la pregunta (coseno ≥ 0.6). Si el Worker no tiene el binding `AI`, tarda más de 4
segundos o falla, se sigue por palabras y no se vuelve a intentar durante 5 minutos. Una huella cuyo texto cambió no cuenta hasta que
se recalcula. Nada de esto manda datos de clientes: viaja la pregunta del cliente recortada a 300 letras y los textos del equipo.

**Lecciones aprendidas** (*Ajustes de Juan*, campo «Lecciones aprendidas»). Una frase por línea (hasta 20, de 300 letras): normas cortas
como «si preguntan por Yappy, di que una vendedora lo confirma». El asistente las recibe junto con su configuración.

## Etiquetas y respuestas rápidas

**Etiquetas** (*Configuración › Etiquetas*). Las creas tú con el color que quieras («Pidió precio», «Comprobante
recibido»…). Vienen cuatro de ejemplo: *Pidió precio*, *Comprobante recibido*, *Socios* y *Reclamo*; edítalas o bórralas.
Las vendedoras las ponen a mano y el asistente puede ponerlas solo, **pero únicamente las que existen** (si pide una
que no existe, Odoo le dice cuáles hay; no inventa etiquetas). Una etiqueta que desactivas deja de poder ponerse, pero
se queda en las conversaciones que ya la tenían.

**Respuestas rápidas** (*Configuración › Respuestas rápidas*). Atajos que empiezan con «/» y que la pantalla
nueva de conversaciones convierte, al escribirlos en la caja de respuesta, en un texto completo (el formulario de hoy
todavía no los usa). Vienen `/ubicacion`, `/horario` y `/socios`. En el texto puedes usar
`{nombre}` (el nombre del cliente; si solo tenemos su número, la palabra se quita sola), `{horario}`, `{direccion}` y
`{whatsapp}`: se llenan con los datos de la tienda, así que si cambias el horario en Ajustes, la respuesta cambia sola.
Las de ejemplo no llevan cifras ni políticas.

## Ajustes de Juan (solo Gerencia)

*Conversaciones › Configuración › Ajustes de Juan.* Todo tiene ya el valor que decidiste:

| Ajuste | Valor ahora |
|---|---|
| Nombre público | el equipo de D'CASA |
| Asistente encendido (general y por canal) | Encendido. WhatsApp (QR) y Telegram encendidos; WhatsApp oficial, Messenger e Instagram apagados |
| Horario laboral | 8:00 a. m. a 5:00 p. m., todos los días (hora de Panamá) |
| Seguimiento | 1.º a las 5 h, 2.º a los 5 días, máximo 2, solo en horario laboral |
| Proveedor de IA | Anthropic (también se puede elegir **Meta** u **OpenAI**), con otro de respaldo opcional |
| Modelos | rápido: `claude-haiku-4-5` · inteligente: `claude-sonnet-5-5` (Meta: `muse-spark-1.3`; **OpenAI: sin modelo por defecto, lo escribes tú**) |
| Precios de la IA | **vacíos** a propósito: no se inventa ningún precio. Si los llenas (dólares por millón de tokens, por nivel: entrada, salida y caché), el Worker calcula el gasto con ellos |
| Tope de IA al mes | 30 USD (al llegar, baja al modelo barato; nunca se queda sin contestar) |
| Pausa al atender | 120 minutos (0 = hasta que la devuelvas) |
| Mensaje de bienvenida y aviso de privacidad | Bienvenida **corta** (una línea: es un asistente automático y cómo pedir una persona). El aviso de privacidad **no se manda por el chat** (queda vacío); el aviso completo va en la política del sitio y, para Telegram, en la descripción del bot (BotFather → `/setdescription`) |
| Palabras prohibidas | remate, corre, ¡¡, !! |
| Responsable por defecto / avisos por Telegram | Administrador / todas las vendedoras con Telegram vinculado |
| Guardar la foto de perfil del cliente | **Encendido** (decisión de la dueña, 2026-10-09). Se apaga en *Privacidad de los clientes* |

**Aviso importante sobre los modelos «contributor».** Si el nombre de un modelo lleva la palabra *contributor*, ese
modelo **entrena con las conversaciones de tus clientes**. Odoo te lo avisa en rojo al elegirlo, y entonces la
**política de privacidad del sitio tiene que decirlo**. Los modelos por defecto no son de ese tipo.

**Las claves de acceso a la IA no se guardan en Odoo**: viven solo en el Worker de Juan. Odoo solo guarda qué
proveedor y qué modelo usar.

Cada cambio queda en el historial de la pantalla (quién y cuándo). Si apagas **Asistente encendido**, nadie
recibe respuestas automáticas y las vendedoras siguen atendiendo.

## Si algo falla

* **El Worker no responde al enviar:** tu mensaje queda **«por enviar»** (se ve en la conversación y en *Mensajes por
  enviar*) y Odoo lo **reintenta solo cada 5 minutos durante una hora**. Nunca se pierde. Si no sale, queda en rojo
  con el motivo y un botón **Reintentar**.
* **El Worker no se entera de que tomaste la conversación:** no pasa nada grave. El Worker pregunta a Odoo justo antes de
  cada respuesta si puede hablar, y Odoo dice que no.
* **Odoo estaba dormido o reiniciando:** el Worker espera y reintenta; la API responde «arrancando» y no pierde mensajes.
* **Una foto o un archivo no se pudo traer:** el mensaje se guarda igual y la burbuja lo dice.
* **Probar la conexión:** en *Ajustes de Juan*, botón **Probar conexión**.

## Avisos en paralelo: comprobantes, documentos y fotos

Cuando un cliente manda un **comprobante de pago**, un **documento de identidad** o **una foto o archivo**, a las personas
elegidas en *Ajustes de Juan › Avisar por Telegram a* les llega un aviso por Telegram **al mismo tiempo**: el asistente
**sigue atendiendo** y esa persona decide si interviene (si lo hace, toma la conversación y el asistente calla).

* **Comprobante** (o algo con señal de pago): «Posible comprobante de pago de Karen por Telegram… Verifica el pago en el banco
  antes de entregar nada.» Siempre avisa (si *Avisar de comprobantes y documentos* está encendido).
* **Documento de identidad:** avisa y recuerda que el asistente no lo ve.
* **Cualquier otra foto o archivo** (por ejemplo la captura de un producto que el asistente ya entendió): avisa a lo más una vez
  cada 10 minutos por conversación; se apaga con *Avisar de fotos y archivos*.
* Si la conversación ya la atiende una persona, no se avisa. Las notas de voz no avisan.
* Quién recibe: las personas elegidas; si no eliges a nadie, todas las de ventas con su Telegram vinculado con Brian.

## Atender y contestar desde Telegram (sin abrir Odoo)

Los avisos de **un cliente que espera** (el asistente lo pasó a una vendedora, lleva rato sin respuesta, mandó un comprobante o un
archivo) traen un botón **Atender** y, al final, «Conversación n.º N». Los avisos de menciones en una nota **no** (esos son para ti,
no para el cliente). Para esto hay que tener el Telegram vinculado con Brian (*Mis preferencias › Vincular Telegram*).

* **Atender:** toma la conversación igual que el botón de la pantalla (el asistente calla y queda a tu nombre).
* **Responder al aviso** (en Telegram: mantén el dedo sobre el aviso › *Responder*, y escribe): el bot **no manda nada todavía**.
  Te enseña el texto tal cual, «Le voy a escribir a Karen por WhatsApp…», con los botones **Enviar** y **Cancelar**. Solo al pulsar
  *Enviar* sale por el canal del cliente, a tu nombre, por la misma ruta de la pantalla (si el canal no lo entrega, el mensaje queda
  «por enviar» y se reintenta; el bot te lo dice con la verdad, no dice «Enviado» si no salió).

Reglas (probadas en `tests/test_telegram_consola.py`): solo **texto** (una foto o un archivo se rechazan y se te manda a la pantalla);
solo en el **chat privado** con el bot y vinculado a tu usuario (no funciona en grupos); todo corre **como tú**: quien no es del equipo
de ventas, o ya no tiene permiso cuando pulsa *Enviar*, no manda nada; el borrador sirve **una sola vez**, **vence a los 15 minutos**
y **solo tú** puedes enviarlo o cancelarlo (aunque otra persona vea el botón); un doble toque no manda dos veces; el límite de
velocidad de Brian (20 mensajes por minuto) aplica igual. No se tocó Brian: la consola solo se engancha a dos puntos de su bot
(`_conversar` y `_procesar_callback`) y todo lo que no sea de Juan (botones `brian:…`, mensajes normales) sigue en manos de Brian.

## Privacidad (Ley 81 de 2019)

Las conversaciones se guardan en Odoo mientras la persona sea cliente. Para atender un pedido de **borrado de datos**,
Gerencia puede borrar la conversación (se van sus mensajes y adjuntos). El aviso completo vive en la política del sitio
(`/privacidad`); por decisión de la dueña el chat no lo repite en el primer mensaje. Si se quisiera mandar uno corto, se
escribe en *Ajustes de Juan › Aviso de privacidad (corto)* y debe coincidir con esa política.

**Foto de perfil.** Es un dato personal. El Worker la pide al canal (Telegram, WhatsApp por QR a través del puente, Messenger e
Instagram; WhatsApp oficial no la da) **a lo más una vez por semana por conversación** (una hora después si algo falló) y solo si
*Ajustes de Juan › Guardar la foto de perfil del cliente* está encendido. Odoo la valida (solo JPEG, PNG o WebP de verdad, hasta 300
KB y un número normal de píxeles), la reduce a 256 px en JPEG y la guarda **en la conversación, no en el contacto** (no pisa la foto
que una persona del equipo haya puesto). La ve quien atiende conversaciones; un cliente del portal o alguien sin sesión recibe solo
la imagen vacía de siempre. **Nunca viaja a la IA** y se borra con la conversación. Al apagar el ajuste se deja de pedir; las ya
guardadas se quedan hasta que se elimine la conversación. **La política de privacidad del sitio debe mencionarla** (pendiente de
revisión del abogado).

---

## Para quien instala (parte técnica)

**Secretos** (los carga la dueña en el panel de Cloudflare del Worker `dcasa`; **no** pasan por GitHub y los
despliegues no los borran): `JUAN_ODOO_TOKEN` y `JUAN_WORKER_TOKEN` (32 caracteres o más cada uno, distintos entre sí).
**Variable no secreta:** `JUAN_URL` (dirección del Worker `juan`; también sirve el parámetro de Odoo
`dcasa_conversaciones.juan_url`, ver abajo). Son opcionales: sin ellos Odoo arranca normal y toda la API
de Juan responde **503** («falta JUAN_ODOO_TOKEN»). El borde los pasa al contenedor (`VARIABLES_DEL_CONTENEDOR`) y Odoo los
lee de su entorno; el arranque (`docker/entrypoint.sh`) no los imprime y la pantalla de ajustes solo muestra si están puestos.

> Parámetro de Odoo equivalente a `JUAN_URL`: `dcasa_conversaciones.juan_url` (Ajustes › Técnico › Parámetros del sistema,
> o el campo «Dirección del Worker de Juan» de *Ajustes de Juan*). La variable de entorno manda sobre el parámetro.

**Entrada para el service binding** (para el agente del Worker `juan`). El Worker `dcasa` exporta una clase
`WorkerEntrypoint` con nombre, **`JuanEntrada`** (`edge/src/index.ts`). El Worker `juan` declara en su `wrangler`:

```jsonc
"services": [
  { "binding": "DCASA", "service": "dcasa-staging", "entrypoint": "JuanEntrada" }   // producción: "service": "dcasa"
]
```

y llama `env.DCASA.fetch(new Request("https://dcasa/dcasa/juan/v1/mensaje", { method: "POST", headers: { Authorization: "Bearer " + env.JUAN_ODOO_TOKEN, "Content-Type": "application/json" }, body }))`.
Solo se reenvían `GET`/`POST` a `/dcasa/juan/**` (cualquier otra ruta, 404); el host da igual (el borde usa el dominio
canónico). Desde internet esas mismas rutas dan **404** (`edge/src/routing.ts`). Mientras Odoo arranca, la respuesta es
JSON `503 {ok:false, error:"Odoo está arrancando.", reintentar_en:15}` con `Retry-After`.

**Rutas** (todas con `Authorization: Bearer <JUAN_ODOO_TOKEN>`, JSON UTF-8, errores `{ok:false, error}`):

| Ruta | Para qué | Notas |
|---|---|---|
| `POST /dcasa/juan/v1/mensaje` | registrar un mensaje | idempotente por `id_mensaje`; acepta `adjuntos[].sensible` y `base64` además de `url`. Responde también `nota_para_el_bot` |
| `GET /dcasa/juan/v1/estado?canal=&id_externo=` | ¿puede contestar el bot? | sin conversación: valores de los ajustes. Incluye `nota_para_el_bot` (`null` si no hay) |
| `GET /dcasa/juan/v1/config` | ajustes de la dueña | `dias`: `0 = domingo … 6 = sábado`. Incluye `proveedor_ia`, `proveedor_respaldo_ia`, `modelo_rapido`, `modelo_inteligente`, `modelos_por_defecto`, `precios` por nivel (`null` donde no hay precio), `precios_ia` por modelo (lo que lee el Worker) y `lecciones` |
| `GET /dcasa/juan/v1/herramientas` | definición de las 12 herramientas | cada una con `nombre/descripcion/parametros` y también `name/description/input_schema` |
| `POST /dcasa/juan/v1/herramienta` | ejecutar una herramienta | `422` = error de uso (el texto sirve para corregir); `404` = no existe |
| `POST /dcasa/juan/v1/seguimiento/hecho` | confirmar un seguimiento | `descartado` cierra el ciclo |
| `POST /dcasa/juan/v1/escribiendo` | «el asistente está escribiendo» | `{canal, id_externo, activo}`; solo avisa a las pantallas por el bus |
| `POST /dcasa/juan/v1/foto-perfil` | la foto de perfil de quien escribe | `{canal, id_externo, mime, base64}` → `{ok, guardada, motivo?}`; `guardada:false` si el ajuste está apagado o no es una foto válida; `404` si no existe la conversación |

Las 12 herramientas, por su nombre público (en Brian llevan el prefijo `juan_` para no chocar con las de uso interno):
`buscar_productos`, `ver_producto`, `listar_categorias`, `reglas_socios`, `saldo_puntos`, `horario_y_tienda`,
`buscar_conocimiento`, `registrar_pregunta_sin_respuesta`, `crear_oportunidad`, `anotar_conversacion`,
`etiquetar_conversacion` y `pasar_a_vendedora`. Las de lectura leen con `sudo()` y filtros (publicados) y devuelven una lista
blanca de campos; el cliente sale **siempre** de la conversación (`juan_conversacion_id`), nunca de un argumento.

Códigos: `400` datos inválidos · `401` token · `404` no existe · `413` demasiado grande · `422` herramienta · `429` demasiados
intentos fallidos · `503` sin token configurado o Odoo arrancando · `500` error interno (sin detalles).

**Odoo → Worker** (`JUAN_WORKER_TOKEN`): `POST /odoo/enviar` (los adjuntos van con URL **firmada de 15 minutos**, ver más
abajo), `POST /odoo/estado` (al devolver con nota, trae `nota_para_el_bot`), `POST /odoo/seguimiento`, `GET /odoo/salud` y, para la pantalla, `POST /odoo/sugerir`, `GET /odoo/costos`, `GET /odoo/qr`,
`POST /odoo/reiniciar` y `POST /odoo/desvincular` (ver «Lo que añadió la pantalla OWL»).

**Usuario técnico:** `juan.asistente`, de portal, con el grupo `Juan (asistente de clientes)` y sin ningún grupo interno ni
contraseña. Solo ve y ejecuta las herramientas de Juan (todas auditadas en *Brian › Acciones* con canal «Juan (clientes)» y la
conversación). Su tope es de 240 acciones por minuto (parámetro `dcasa_conversaciones.herramientas_por_minuto`) porque es un
solo usuario para todos los clientes.

**Datos para el agente del Worker:** `saldo_puntos` devuelve `verificado:false` con `motivo` cuando el PIN no sirve (sigue siendo
HTTP 200); el PIN nunca se guarda en la auditoría (queda como `***`). `buscar_conocimiento` devuelve las 3 mejores entradas
activas; si no hay ninguna, el asistente debe llamar a `registrar_pregunta_sin_respuesta` y decir que una vendedora lo confirma.

### Adjuntos: URL firmada de vida corta

Cuando una vendedora manda una foto o un PDF desde Odoo, el puente lo baja con una URL
`/dcasa/adjunto/<id>/<vence>/<firma>/<nombre>`: la firma (HMAC-SHA256 con `database.secret`) amarra el adjunto, la hora de
vencimiento y el **contenido** (su checksum). Vale **15 minutos** (parámetro `dcasa_conversaciones.url_adjunto_minutos`, tope 24 h)
y deja de valer si el archivo cambia. Solo sirve adjuntos de mensajes de conversaciones; todo lo demás da 404. No empieza por
`/dcasa/juan`, porque esa zona la bloquea el borde. Los tipos que un navegador podría ejecutar (HTML, SVG…) salen como descarga.

### API de la pantalla «Conversaciones» (panel)

Métodos públicos de `dcasa.conversacion` (RPC normal de Odoo, `call_kw`) para la pantalla OWL de
[`JUAN_PANEL.md`](JUAN_PANEL.md) (el código OWL está en `addons/dcasa_conversaciones/static/src`). Todos exigen ser del equipo de ventas
**en el servidor** y devuelven diccionarios JSON.

| Método | Qué hace |
|---|---|
| `lista(filtros, offset, limite)` | La bandeja: `{conversaciones, total, hay_mas, sin_leer_total}`, las más recientes primero, 30 por página (máx. 100). Filtros: `canal`, `estado` (`bot`/`humano`/`cerrada`/`necesita_atencion`), `etiqueta_id`, `asignada_a_mi`, `sin_leer`, `con_oportunidad`, `busqueda` (nombre, celular o texto de cualquier mensaje). Un filtro desconocido es error. |
| `hilo(conversacion_id, antes_de_id, limite)` | Un tramo de mensajes (50 por defecto) del más viejo al más nuevo; `antes_de_id` pide el tramo anterior; `hay_mas` dice si quedan. Incluye notas y avisos. |
| `enviar_respuesta(conversacion_id, texto, adjuntos_ids, programar_para=None)` | Contesta (toma la conversación si hace falta). Hasta 5 adjuntos propios, de 10 MB. Si el Worker no responde queda «por enviar». Con `programar_para` (fecha y hora ISO, entre 1 minuto y 30 días) queda «programado» y devuelve `programado: true`; no toca la conversación hasta su hora. |
| `cancelar_programado(mensaje_id)` | Borra un mensaje programado (y sus archivos) que aún no salió. Solo quien lo programó o Gerencia. `hilo()` devuelve los programados aparte, en `programados`. |
| `tomar(conversacion_id, minutos)` · `devolver(conversacion_id, nota)` · `cerrar(conversacion_id)` | Lo mismo que los botones (una sola ruta de código). |
| `asignar(conversacion_id, usuario_id)` | Asigna a alguien de ventas (`null` = sin asignar). |
| `documentos_del_cliente(conversacion_id)` · `adjuntar_a_documento(conversacion_id, adjunto_id, modelo, registro_id)` | Pedidos y facturas del cliente, y copia de un archivo suyo al chatter de uno de ellos (`sale.order` o `account.move`). |
| `poner_etiquetas(conversacion_id, etiqueta_ids)` · `agregar_nota(conversacion_id, texto, menciones=None, tarea_para=None)` | Etiquetas (solo activas) y nota interna; `menciones` (ids de compañeras del equipo) las avisa por Odoo y Telegram y `tarea_para` (`AAAA-MM-DD`) les deja una tarea. |
| `marcar_leida(conversacion_ids)` | Marca como leídas, para quien llama. |
| `ficha(conversacion_id)` | Cliente, si es Socio y su saldo (solo lectura), oportunidades abiertas, compras recientes, notas, seguimiento y **qué sabe el bot** (nombre, productos por los que preguntó, etiquetas, última vez que habló). |
| `dcasa.mensaje.marcar_sensible(adjunto_ids, valor)` | Marca o desmarca comprobantes y documentos de identidad. |
| `dcasa.conversacion.etiqueta.lista()` · `dcasa.respuesta.rapida.lista()` · `.texto_para(conversacion_id, atajo)` | Etiquetas activas; atajos con `/`; el texto del atajo ya armado para ese cliente. |

**Tiempo real.** Cada mensaje nuevo, cambio de estado, asignación o etiqueta se avisa por el bus de Odoo a todas las personas del
equipo de ventas con la notificación `dcasa_conversaciones/evento` y la carga `{evento, conversacion_id, estado, asignada_a,
ultima_actividad, mensaje_id, autor}`. **Nunca viaja el texto del mensaje** (el bus guarda lo que se envía): la pantalla pide el
detalle con `hilo`. Un fallo del bus nunca tumba el mensaje.

**Rendimiento.** Índices para la lista (`ultima_actividad DESC NULLS LAST, id DESC`; `estado, ultima_actividad`; asignada a) y para
el hilo (`conversacion_id, id`). Las consultas no dependen de cuántas filas se piden (probado), y con 5.000 conversaciones la lista
tarda bien por debajo de 1 s (probado en las pruebas del módulo).

**Lo que añadió la pantalla OWL** (más métodos de `dcasa.conversacion`, mismos permisos):

| Método | Qué hace |
|---|---|
| `iniciar_panel()` | Todo lo que la pantalla necesita al abrir: usuario, si el bot está configurado y encendido, límites (texto, nota, tamaño y número de adjuntos), canales, etiquetas, respuestas rápidas y equipo. |
| `subir_adjunto(conversacion_id, nombre, datos, mimetype)` · `descartar_adjunto(adjunto_id)` | Sube (base64, máx. 10 MB, máx. 10 pendientes por persona) o descarta un archivo antes de enviarlo. Se valida el **contenido** y la extensión (JPG, PNG, WebP, GIF, PDF, Word, Excel, TXT, CSV); el cron `Juan: limpiar archivos subidos y no enviados` borra a las 48 h los que nadie envió. |
| `equipo()` · `nueva_oportunidad(conversacion_id)` · `reintentar_envios_panel(conversacion_id)` | El equipo de ventas (para asignar), la oportunidad y los reintentos desde la ficha. |
| `resumir_conversacion(conversacion_id, regenerar=False)` | «Resumir»: unas viñetas de lo que pasó, para quien recibe la conversación (`POST /odoo/resumir`, mismos mensajes que «Sugerir» pero hasta 60). Se guarda en la conversación (`resumen_ia`) y **no gasta IA** si ya cubre el último mensaje o se pidió hace menos de un minuto. El hilo trae el guardado y si sigue al día (`resumen_ia.vigente`). Se apaga en Ajustes (`resumen_ia_activo`). |
| `refrescar(filtros, limite, conversacion_id, tramo)` | Lo que la pantalla pide cuando le avisan que algo cambió: `{lista, hilo}` en UNA llamada (antes eran dos). |
| `presencia(conversacion_id, escribiendo)` | El pulso de la pantalla (cada 20 s y al teclear): qué conversación tiene abierta esta persona. Devuelve quiénes más están viendo cuáles (`{presencia: {conversacion_id: [{usuario_id, escribiendo}]}}`) y avisa a las demás pantallas por el bus (solo ids). Una fila por persona en `dcasa.presencia`, que se borra a las 24 h. |
| `fijar_disponible(disponible)` | «Disponible / No disponible» de quien llama: con el reparto por turnos, solo a quien está disponible le tocan conversaciones nuevas. |
| `sugerir_respuesta(conversacion_id)` | Pide un **borrador** al Worker (`POST /odoo/sugerir`). Manda los últimos 14 mensajes sin notas internas ni avisos; los adjuntos sensibles viajan sin texto ni contenido. Nunca envía nada. |
| `buscar_catalogo(consulta, limite)` · `fotos_catalogo(producto_id)` | Productos **publicados** por nombre o código: miniatura WebP, precio «+ ITBMS», `DISPONIBLE`/`POCAS`/`AGOTADO` (nunca la cantidad ni el costo), medidas. |
| `preparar_foto_catalogo(...)` · `enviar_foto_catalogo(conversacion_id, producto_id, fotos, texto)` | Arma el pie (nombre, precio + ITBMS, medidas, enlace) y manda las fotos como JPEG de 1024 px con URL firmada de 15 minutos. |
| `cotizaciones_abiertas(conversacion_id)` · `crear_cotizacion(conversacion_id, lineas)` · `enviar_cotizacion(conversacion_id, orden_id, texto)` | La cotización abierta más reciente (con los permisos de Ventas de quien llama); un **borrador** nuevo con líneas del catálogo, sin confirmar; el PDF de `sale.action_report_saleorder` enviado como adjunto (la orden queda «enviada»). |
| `dcasa.juan.panel.por_persona(periodo)` | **Solo Gerencia.** Por cada persona: mensajes escritos en Odoo, conversaciones en que habló, mediana de cuánto tardó en contestar (desde que el cliente quedó sin respuesta, de quien fuera, hasta su primer mensaje) y cuántas le esperan ahora; más las que esperan y nadie tiene. Lo escrito desde el teléfono no dice quién lo escribió y no cuenta. |
| `dcasa.juan.panel.resumen(periodo)` | Los seis números del Resumen (`hoy`, `7_dias`, `30_dias`, en la hora de Panamá). |
| `dcasa.juan.panel.costos()` · `conexiones()` · `qr()` · `reiniciar_puente()` · `desvincular_puente()` | **Solo Gerencia** (se exige en el servidor). Hablan con el Worker por `GET /odoo/salud`, `GET /odoo/costos`, `GET /odoo/qr`, `POST /odoo/reiniciar` y `POST /odoo/desvincular`. Sin `JUAN_URL`/`JUAN_WORKER_TOKEN` contestan `configurado: false` («Falta conectar el bot») sin salir a ninguna parte. `qr()` solo deja pasar un PNG en base64 de hasta 200 KB, y **ni el QR ni las claves se escriben en ningún registro**. Reiniciar y desvincular dejan una nota en el historial de los ajustes. |

**Rutas nuevas del Worker `juan`** (`juan/src/odoo-panel*.ts`; todas con `Authorization: Bearer <JUAN_WORKER_TOKEN>` comparado en tiempo
constante, respuestas `Cache-Control: no-store`, errores genéricos sin detalles internos):

| Ruta | Qué hace |
|---|---|
| `POST /odoo/sugerir` | Recibe la conversación recortada y devuelve `{ok, texto, avisos}`. Usa solo herramientas de **lectura** (`buscar_productos`, `ver_producto`, `listar_categorias`, `reglas_socios`, `horario_y_tienda`, `buscar_conocimiento`), nivel inteligente (baja al rápido si se llegó al tope), registra el gasto y avisa de lo que quitó (fotos, enlaces) y de los `[CONFIRMAR…]`. |
| `POST /odoo/embeber` | `{textos:[…]}` (1 a 8, hasta 2000 letras cada uno) → `{ok, vectores:[[1024 números]], dimensiones, modelo}`. Lo usa la búsqueda por significado. Sin binding `AI`: 503 con `faltan:["AI"]`. No envía ni escribe nada y no pasa por el tope de gasto (cuesta centavos por millón de palabras). |
| `GET /odoo/costos` | Gasto del mes por modelo, turnos, tope y modelos sin precio cargado (desde el contador del Worker). |
| `GET /odoo/qr` | El QR del puente de WhatsApp (data URL PNG) y su estado: `necesita_qr`, `conectado`, `desconectado`, `desvinculada`, `arrancando`, `apagado`. No imprime el QR en logs. |
| `POST /odoo/reiniciar` · `POST /odoo/desvincular` | Reinicia o cierra la sesión del puente. |

**Tareas programadas** (`data/ir_cron_panel.xml`): «Juan: foto diaria del gasto de IA» (04:50 UTC; si el Worker no responde no pasa nada) y «Juan: limpiar archivos subidos y no
enviados» (07:10 UTC).

**Para que las fotos lleguen a WhatsApp:** el puente solo baja archivos de `https://dcasapty.com` y `https://dcasapty.workers.dev`
(`DOMINIOS_DEL_PUENTE` en `models/panel_calculos.py`). Si `web.base.url` de Odoo es otra dirección, *Conexiones* lo marca en rojo («Dirección de Odoo para las
fotos y documentos: no sirve»).

**Pruebas.** `tests/test_panel_extra.py`, `test_panel_catalogo.py`, `test_panel_juan.py` (modelos y controladores, con Worker falso);
`test_panel_interfaz.py` (Chrome de verdad: abrir la lista y un hilo, atender y devolver, enviar con Enter, adjuntar con botón y
arrastrando, documentos, notas, rápidas, sugerir, filtros, ficha, foto del catálogo, cotización, tiempo real, celular de 390 px, Resumen,
Costos y Conexiones) y `test_panel_visual.py` (**contrato visual**: sistema plano, amarillo solo sobre azul marino, contraste, foco visible
con Tab y capturas de referencia en `tests/referencia/panel-*.webp`, a 1440 y 390 px). Para regenerar las referencias a propósito:
`scripts/actualizar_referencias_visuales_juan.sh` (ver `docs/OPERACION.md`). Las capturas para la dueña se generan con
`DCASA_CAPTURAS_JUAN=<carpeta> scripts/test.sh dcasa_conversaciones` (se guardan en `docs/auditoria/ronda7/capturas/`).

### Cambios sobre el contrato `JUAN.md`

Todo lo del contrato se cumple. Se añadió, sin quitar nada: `ok: true` en las respuestas, `adjuntos` en la respuesta de `/mensaje`,
`adjuntos[].sensible`/`base64` aceptados, `nota_para_el_bot` en `/mensaje`, `/estado` y `POST /odoo/estado`, los campos de IA en
`/config` (con `precios` por nivel **y** `precios_ia` por modelo, que es el que lee el Worker), claves duales en `/herramientas` y tres herramientas más (`buscar_conocimiento`, `registrar_pregunta_sin_respuesta`,
`etiquetar_conversacion`; el contrato tenía 9, ahora son 12). Decisiones donde el contrato dejaba margen: días `0 = domingo`; el
2.º seguimiento cuenta 5 días desde el primero y también espera al horario laboral; `descartado` cierra el ciclo; el catálogo se lee
directo de los productos publicados (`/dcasa/tienda/feed` no existe en este repositorio); tras `pasar_a_vendedora` la pausa es la de
los ajustes y luego el asistente retoma.
