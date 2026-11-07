# Sofía, la asistente del CRM (`dcasa_sofia`)

Pedido de la dueña (2026-11-05): un agente independiente para el CRM, como Brian lo es del administrador. Que reparta,
proponga mensajes y seguimientos según el estado de cada cliente, mantenga el CRM al día y diga las prioridades del día,
**sin dañar el proceso de respuesta de Juan**. Decisiones de la dueña:

* **Propone y una persona aprueba.** Sofía no cambia nada por su cuenta.
* **Con un botón y cada mañana.** «Organizar con Sofía» arriba del tablero (y de la lista) del CRM, y una revisión
  automática media hora después de abrir.
* **Gerencia ve y aprueba todo; cada vendedora lo suyo**, con un resumen por Telegram cada mañana.
* **Campaña de datos** (mismo día): a los tibios y calientes que llegaron por WhatsApp o redes con un emoji, una frase o
  una empresa como nombre, o sin correo, un mensaje profesional que les pide su nombre y apellido y su correo para
  avisarles de promociones, del programa Socios y de los beneficios de cumpleaños.

## Dónde está

* **CRM › Sofía** (y el botón «Organizar con Sofía» del tablero y de la lista del CRM, que revisa al entrar).
* **CRM › Configuración › Sofía**: «Mensajes de Sofía» (los textos, los cambia Gerencia) e «Historial de Sofía» (qué
  propuso, quién lo aprobó o descartó y qué pasó).
* **Conversaciones › Configuración › Ajustes de Juan**, grupo «Sofía»: revisar cada mañana (sí), resumen por Telegram
  (sí), lo descartado no vuelve en (7 días), no volver a pedir sus datos en (30 días).

## Cómo se ve y se usa (la pantalla, 2026-11-06)

Pedido de la dueña: «Sofía puede mejorar mucho, sobre todo la interfaz visual». Pensada para la vendedora con el
celular entre clientes y para Gerencia en la computadora. **Solo cambió la interfaz**: lo que Sofía propone, los
permisos y lo que hace cada botón son los mismos de antes (`static/src/`; el servidor no se tocó).

* **Arriba, en azul:** «Revisar ahora» (amarillo), cuándo revisó y quién lo pidió («Revisó hoy a las 2:53 p. m. (la
  pidió Ana)») y cuántas hay de cada prioridad («12 hoy sin falta · 13 hoy · 4 cuando puedas»).
* **Lo urgente primero, por secciones:** «Hoy sin falta» (franja azul con el número en amarillo y tarjetas con borde
  azul), «Hoy» y «Cuando puedas», cada una con su número.
* **Filtro rápido con conteos:** «Qué mirar», por tipo (Contestarle, Cotización vence, Escribirle, Pedir sus datos,
  Guardar sus datos, Llamarlo, Darle vendedora, Poner su vendedora; solo los que hay) y, para Gerencia, «Para quién»
  (cada vendedora y «Sin vendedora»). Los números se cruzan: con un tipo elegido, cada vendedora dice cuántas de ese
  tipo tiene, y al revés. En la computadora van a la izquierda y se quedan a la vista al bajar; en el celular son una
  tira que se desliza de lado y se queda pegada arriba.
* **La tarjeta, compacta:** el cliente y su canal, la temperatura, qué hacer (con su ícono), el porqué y, para
  Gerencia, para quién es. El mensaje se lee como en el chat (una burbuja) y se cambia con **«Editar»** («Listo» lo
  cierra; si se cambió, dice «lo cambiaste»). La primera acción es la grande (a todo el ancho en el celular) y las
  demás van al lado. «Ver la oportunidad» y «Descartar» van abajo, aparte y discretos (lejos del botón principal).
* **«Descartar» como siempre:** un toque, sin pregunta (nunca tuvo confirmación y no se le agregó; la dueña lo decidió
  así el 2026-11-06: «no quiero, déjalo así»); la tarjeta dice «Descartada…» en su lugar.
* **Al aprobar, la pantalla no salta:** la tarjeta se queda en su lugar y del mismo alto diciendo lo que pasó («Tarea
  creada para Ana.», «Guardado en su ficha.», o en ámbar lo que «ya no hacía falta») durante 2,5 segundos, y después se
  cierra despacio. Nada nuevo queda bajo el dedo. Lo que abre el chat («Abrir el chat…», «Guardar y responderle») se
  va al chat como antes, con su aviso; un error sale en un aviso y la tarjeta se queda.
* **Todo al día:** sin nada pendiente, «Todo al día» y cuándo vuelve a revisar. Si el filtro elegido se quedó vacío,
  «Listo por aquí» con «Ver todo (N)»; el filtro elegido se queda (en 0) para que la tira no salte.
* **Mientras carga:** la forma de las tarjetas. Desde «Organizar con Sofía» se ven primero las que ya había y Sofía
  revisa encima (una franja dice «Sofía está revisando el CRM…»); lo que se resolvió en la pantalla mientras tanto no
  vuelve a aparecer.
* **Baja con la rueda y con el dedo** (la regla fuerte de `.o_action`, como el Inicio; prueba con eventos de verdad).
* Marca: azul `#1340B1`; el amarillo solo sobre azul (avatar, «Revisar ahora», el número de «Hoy sin falta», el conteo
  del filtro elegido y el ícono de «Todo al día»); Anton, Oswald e Inter; plano, sin sombras.

## Qué propone (en este orden; un solo mensaje por cliente por revisión)

| Tipo | Cuándo | Qué se aprueba |
|---|---|---|
| Contestarle | Una vendedora tiene el chat y el cliente le escribió hace más de 1 hora (y menos de 7 días) sin respuesta. También: Juan se lo pasó a una persona hace más de 1 hora y nadie del equipo le ha escrito, aunque la pausa ya venció y el chat volvió a Juan (issue #25: Juan ya no le manda su seguimiento). Descartada en ese caso, no vuelve con cada mensaje nuevo del cliente mientras siga esperando por ese traspaso; vuelve con el siguiente traspaso. | Abrir el chat. |
| Su cotización vence | Cotización sin confirmar (borrador o enviada) que vence hoy o mañana y el cliente tiene chat. | Mensaje de recordatorio (abrir el chat con él, enviarlo ya o crear tarea). |
| Escribirle | Tibio o caliente al que ninguna vendedora le escribió en 24 horas («A quién escribirle hoy»). | Mensaje de seguimiento según su estado: tiene cotización, dijo para cuándo, o le interesó algo. |
| Pedir sus datos | Tibio o caliente cuya ficha no tiene nombre y apellido de verdad o no tiene correo. Si además toca escribirle, va al final del mismo mensaje. | El mensaje que pide los datos. |
| Guarda sus datos | El cliente escribió en el chat (últimos 30 días) su nombre y apellido, su correo o su cumpleaños, y su ficha no los tiene. Ver «Guarda sus datos» abajo. | Revisar (y corregir si hace falta) y «Guardar y responderle» (guarda y abre el chat con el borrador de Juan) o «Solo guardar». |
| Llamarlo | Por WhatsApp oficial, Messenger o Instagram ya pasaron 24 horas desde su último mensaje (Meta no deja escribirle) y tiene celular. | Crear una tarea de llamada. |
| Darle una vendedora (Gerencia) | Tibia o caliente sin vendedora: a su vendedora de siempre (los días del reparto de Juan) o a quien lleva menos oportunidades abiertas. | Asignar la oportunidad. |
| Poner a su vendedora en la oportunidad (Gerencia) | La vendedora que atiende su chat no es la de la oportunidad. | Asignar la oportunidad. |

Prioridad: «Hoy sin falta» (contestar, cotización que vence hoy, escribirle a un caliente, repartir un caliente), «Hoy»
y «Cuando puedas». La pantalla las ordena así; por tipo muestra hasta 150 (las demás se cuentan y Gerencia lo ve).

### Qué es «sin nombre de verdad»

Reglas fijas (`models/reglas.py`, `falta_el_nombre`): sin nombre o el provisional del canal; solo emojis o símbolos;
con emojis o números; más de 5 palabras (una frase); palabras de frase o de empresa («Dios», «bendiga», «amor»,
«tienda», «S.A.»…, lista corta y prudente: «Jesús», «Luz» o «Paz» son nombres); o un solo nombre (falta el apellido).
El saludo usa el nombre de pila solo si es un nombre: nunca «Hola 🙏».

## Guarda sus datos (pedido de la dueña, 2026-11-05)

Cuando el cliente contesta lo que se le pidió, al tocar «Revisar ahora» Sofía muestra **una tarjeta con todo** («Guarda
sus datos: Marisol Pérez · marisol@… · cumpleaños 12/03»). La vendedora ve lo que escribió y lo que hoy dice su ficha,
puede corregir o borrar cualquier dato, y toca:

* **«Guardar y responderle»** (pedido de la dueña, 2026-11-05: «se completa la ficha, pero falta las gracias y la
  oportunidad de cierre»): guarda, abre su chat y Juan deja en la caja un borrador según su conversación (el mismo
  «Sugerir» del chat: le da las gracias y sigue con lo que le interesa). **No se envía nada**: la vendedora lo lee, lo
  ajusta y lo envía ella. Solo si se le puede escribir (las 24 horas de Meta, no pidió que no lo contacten); si no,
  la tarjeta ofrece solo guardar. Si no se puede abrir su chat, no se guarda a medias. Si Juan no alcanza a escribir
  el borrador, los datos ya quedaron guardados y el chat abierto: la caja dice por qué, en corto, y ofrece
  **Reintentar** (2026-11-06; ver JUAN_ODOO.md › Sugerir).
* **«Solo guardar»**: guarda y sigue con la siguiente tarjeta.

* **Qué lee** (`reglas.datos_en`, del mensaje más nuevo al más viejo). Siempre: «me llamo …», «mi nombre es …»,
  «nombre: …», un correo bien escrito, y el cumpleaños si el mensaje habla de él («cumplo el 12 de marzo», «mi
  cumpleaños es…», «nací el 12/03/1990»). Solo en sus primeros mensajes después de que alguien le pidió sus datos
  —Sofía, una vendedora o Juan— (hasta 4 mensajes y 48 horas; la gente contesta por partes: «Hola buenas tardes»,
  «Ana Pérez», su correo), también «soy …» o una línea que es solo un nombre y apellido, y una línea que es solo la
  fecha («12/03») si el pedido incluía el día y el mes del cumpleaños (la plantilla «Pedir sus datos» lo pide). Nunca
  un saludo, una frase («Muy amable», «Te aviso»), una dirección, un mueble o un color, una fecha de entrega, el
  cumpleaños de otra persona ni un mensaje con precio.
* **Nuestro formato.** Nombre con mayúscula inicial y las partículas en minúscula («María de los Ángeles Pérez»,
  «O'Neill», «José-Luis»); correo en minúsculas; cumpleaños como lo guarda Socios (`MM-DD`, sin año), elegido en la
  tarjeta con día y mes.
* **Nunca pisa lo bueno.** El nombre solo si el de la ficha no sirve (emoji, frase, empresa, solo un nombre o el
  provisional del canal) y el nuevo es mejor (un nombre solo nunca reemplaza a otro nombre de pila); el de una empresa
  nunca se cambia. El correo solo si falta o está mal escrito. El cumpleaños solo si falta.
* **Nunca duplica.** No crea fichas. Si el correo ya es de otra ficha, no se propone: la tarjeta lo avisa («Gerencia
  las une en Posibles duplicados»). Un correo del equipo de D'CASA nunca se guarda en un cliente.
* **Al aprobar se revisa todo otra vez** (alguien pudo escribirlo a mano o otra ficha pudo quedarse con ese correo).
  Lo que la ficha ya tiene se salta («Ya tenía su correo»); si ya tenía todo, queda «Ya no hacía falta». Un dato mal
  escrito no se guarda: la vendedora lo corrige o lo borra. Se guarda con los permisos de quien aprueba y pasa por las
  reglas de Contactos; en la ficha queda una nota con el antes y el después.
* **No vuelve a pedir lo que ya se pidió.** Si alguien del equipo (o Juan) ya le pidió sus datos en ese chat en los
  días de Ajustes, Sofía no propone pedírselos otra vez: si contestó, propone guardarlos.

## Lo que no hace (y por qué)

* **No toca el proceso de Juan.** Revisar no escribe en conversaciones ni en oportunidades. No se mete con un cliente que
  está conversando con Juan ahora (escribió hace menos de 2 horas y lo atiende Juan), ni con quien Juan está por
  mandarle su seguimiento automático (en las próximas 2 horas, o ya lo está mandando). Si Juan lo tenía para más
  adelante, la propuesta lo dice: al escribirle una persona, la conversación pasa a ella y ese seguimiento ya no sale
  (como siempre que una vendedora escribe). Repartir asigna la **oportunidad**, nunca el chat.
* **No escribe sola.** «Enviar ya» manda el mensaje por la misma ruta que la pantalla de Conversaciones
  (`enviar_respuesta`), con quien lo aprueba como autora: la conversación pasa a ella y Juan calla, como siempre.
  «Abrir el chat con este mensaje» deja el texto escrito en la caja del chat, sin enviarlo. El texto pasa al chat una
  sola vez (por el almacenamiento de la pestaña, no por la dirección): recargar la página no lo vuelve a poner.
* **Nunca dos veces.** Enviar confirma la base a mitad de la petición (antes de llamar al Worker): la propuesta queda
  aprobada en esa misma confirmación. Un doble clic, otra persona o Odoo repitiendo la petición la encuentran resuelta;
  si fue la misma persona hace un momento, contesta «ya quedó» en vez de un error.
* **No inventa cifras.** Los mensajes salen de plantillas (CRM › Configuración › Sofía) con datos que Odoo ya sabe: el
  nombre de pila, lo que le interesó, el número de su cotización y hasta cuándo vale. Una plantilla no acepta claves
  que Sofía no sabe llenar. Sin precios ni cifras del programa Socios: eso lo confirma la vendedora. Si lo que anotó
  Juan («lo que le interesó») o lo que dijo el cliente («para cuándo») trae un monto, no se usa.
* **No escribe a quien pidió que no lo contacten**, ni a empleados, usuarios o la empresa propia. Fuera de las 24 horas
  de Meta no ofrece escribir (Meta lo rechazaría): propone llamar.
* **No gasta IA.** Esta etapa es de reglas y plantillas. Para un mensaje más a la medida está el botón «Sugerir» del
  chat (lo redacta Juan).

## Seguridad

* `dcasa.sofia.propuesta` y `dcasa.sofia.corrida` son de solo lectura por RPC (ACL). Regla de registro: la vendedora
  solo ve las propuestas que son para ella y nunca las de repartir; Gerencia ve todas.
* Los métodos de la pantalla (`panel`, `analizar`, `aplicar`, `descartar`) exigen el grupo de ventas en el servidor,
  leen la propuesta como el usuario (la regla de registro manda), la bloquean antes de resolverla (`FOR UPDATE NOWAIT`)
  y validan cada argumento. Cada acción corre con los permisos de quien la aprueba (sin `sudo`): asignar exige
  Gerencia; guardar sus datos pasa por las reglas de Contactos (sin repetir el correo de otra ficha).
* Antes de hacer algo se revisa otra vez lo mismo que miró la revisión, porque entre la revisión y el clic pasa el día:
  que el cliente no pidió que no lo contacten, que el chat sigue siendo de esa ficha, que no está conversando con Juan
  ni Juan está por escribirle, que nadie del equipo le escribió (escribirle), que la cotización sigue sin confirmar y
  con la misma fecha (su cotización vence), que todavía faltan sus datos (pedirlos), que sigue esperando (contestar),
  que nadie cambió la vendedora y que el chat lo sigue atendiendo ella (repartir), y que a la ficha todavía le faltan
  esos datos y nadie más tiene ese correo (guardar). Si no, la propuesta queda «Ya no hacía falta» y no se hace nada.
* «Pedir sus datos» solo cuenta como pedido (para no repetirlo en 30 días) si el mensaje salió: con «Enviar ya», o con
  «Abrir el chat» y una vendedora escribió después en ese chat. Si alguien descarta «Escribirle», tampoco se le piden
  los datos aparte en esos días.
* Una sola revisión a la vez (candado de la base) y el botón no vuelve a revisar si alguien lo hizo hace menos de un
  minuto. Si dos revisiones se cruzan, la segunda no duplica: lo que ya existe se salta. Una revisión solo reescribe
  lo que cambió de una propuesta pendiente (menos choques con quien la está aprobando) y lo que pasa del tope de la
  pantalla queda pendiente (no se marca «ya no hacía falta»).
* Revisión adversarial (2026-11-05): ningún hueco de permisos; se arreglaron el doble envío, la revisión al aprobar, el
  texto en el chat de un solo uso, el conteo de datos pedidos, montos en los mensajes, contestar a quien ya compró, lo
  descartado que tapaba lo demás y el conteo de avisos de Telegram. Pendiente a propósito: si Gerencia envía una
  propuesta de una vendedora, sale con su nombre y la conversación pasa a Gerencia (como en el chat).

## Cada mañana

El cron «Sofía: revisión del CRM de cada mañana» corre cada 30 minutos y solo hace algo una vez al día: dentro del
horario de Ajustes de Juan, media hora después de abrir. Si «Resumen por Telegram» está encendido, cada vendedora con
Telegram vinculado recibe cuántas cosas tiene y las 5 más urgentes, y Gerencia el resumen (lo de repartir y cuántas
tiene cada vendedora). El aviso nunca hace fallar la revisión.

## Pruebas

`addons/dcasa_sofia/tests/`: reglas puras (`test_reglas.py`), motor, permisos, aprobar cada acción, lo que ya no hace
falta, descartar, la revisión de la mañana y Telegram (`test_sofia.py`), y en el navegador revisar, descartar y abrir el
chat con el mensaje escrito (`test_sofia_navegador.py`). La pantalla (`test_sofia_pantalla.py`): lo urgente arriba y
en azul, el filtro por tipo y por vendedora con conteos que cuadran, «Todo al día», «Listo por aquí» con «Ver todo»,
que no salte al aprobar o descartar, y el scroll con la rueda (computadora) y con el dedo (celular) mandados por el
protocolo de Chrome, con los filtros a la vista.

## Siguientes etapas (ideas, sin hacer)

* Mensajes redactados con IA a partir de la conversación (con tope de gasto propio y sin cifras).
* Plantillas aprobadas de WhatsApp para escribir fuera de las 24 horas.
* Leer el nombre que el cliente contesta y proponer corregir su ficha.
