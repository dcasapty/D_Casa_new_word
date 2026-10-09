# Juan en Odoo: la bandeja de conversaciones

Guía sencilla para la dueña y las vendedoras. El contrato técnico con el Worker está en [`JUAN.md`](JUAN.md); la
pantalla nueva de conversaciones (panel) está especificada en [`JUAN_PANEL.md`](JUAN_PANEL.md). Aquí solo está lo
que **ves y haces en Odoo**, y al final una parte corta para quien instala o programa.

## Qué es

**Juan** es el asistente que contesta a los clientes por WhatsApp (y Telegram, Messenger, Instagram) con el nombre
**«el equipo de D'CASA»**. Contesta a cualquier hora. Cuando un cliente necesita a una persona, el asistente se
calla y le toca a una vendedora. **Odoo es la memoria de todo**: cada conversación, cada cliente y cada oportunidad
quedan guardados aquí.

## Dónde está

Menú **Conversaciones** (el ícono del globo de chat).

| Opción | Quién | Para qué sirve |
|---|---|---|
| **Bandeja** | Ventas | Todas las conversaciones, en tres columnas: *Con el asistente*, *Con una vendedora* y *Cerrada*. |
| **Mensajes por enviar** | Ventas | Lo que escribiste desde Odoo y todavía no salió (ver «Si algo falla»). Normalmente está vacío. |
| **Preguntas sin respuesta** | Gerencia | Lo que los clientes preguntaron y el asistente no supo contestar (ver «El asistente aprende»). |
| **Conocimiento del bot** | Gerencia | Los textos que el asistente puede usar para contestar (horario, ubicación, Socios, garantía…). |
| **Configuración › Ajustes de Juan** | Gerencia | Cómo se presenta, cuándo contesta, qué IA usa y cuánto insiste. |
| **Configuración › Etiquetas** | Gerencia | Las etiquetas de colores para clasificar conversaciones. |
| **Configuración › Respuestas rápidas** | Gerencia | Los atajos con «/» (`/horario`, `/ubicacion`…). |

La tarjeta de cada conversación muestra a la persona, el canal, las etiquetas, el último mensaje y quién la atiende.
Una etiqueta azul **«Espera tu respuesta»** marca las que el cliente escribió y nadie ha contestado.

## Atender a un cliente

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

* las **notas internas** que escribimos entre vendedoras (borde punteado), que además quedan en la ficha del cliente;
* los **avisos del sistema**, una línea gris por cada cosa que pasó: «Ana tomó la conversación», «El asistente pasó la
  conversación a una vendedora. Motivo…», «Se creó la oportunidad…», «Seguimiento n.º 1 enviado», «Ana cerró la conversación».

**Nota para el asistente.** Al **devolver** la conversación puedes dejarle una nota corta (hasta 500 letras): «ya
quedó la visita del sábado». El asistente la lee en cada respuesta hasta que otra persona tome la conversación.

**Sin leer.** Cada persona del equipo lleva su propia lectura: lo que el cliente escribió y tú aún no abriste cuenta
como «sin leer» solo para ti. (Los contadores los muestra la pantalla nueva de conversaciones; el backend ya los lleva.)

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

A quien **preguntó y no volvió a escribir**, el asistente le escribe **como máximo dos veces**:

* la **primera**, 5 horas después del último mensaje, **solo en horario laboral** (8:00 a. m. a 5:00 p. m., todos los
  días, hora de Panamá; si cae fuera, espera al siguiente horario laboral);
* la **segunda**, 5 días después de la primera, también en horario laboral;
* **ninguna** si la persona **ya compró** (una factura suya pagada después de que empezó la conversación) o si
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
| Mensaje de bienvenida y aviso de privacidad | Textos propuestos: **están pendientes de tu aprobación** |
| Palabras prohibidas | remate, corre, ¡¡, !! |
| Responsable por defecto / avisos por Telegram | Administrador / todas las vendedoras con Telegram vinculado |

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

## Privacidad (Ley 81 de 2019)

Las conversaciones se guardan en Odoo mientras la persona sea cliente. Para atender un pedido de **borrado de datos**,
Gerencia puede borrar la conversación (se van sus mensajes y adjuntos). El texto corto de privacidad que dice el
asistente se edita en *Ajustes de Juan* y debe coincidir con la política del sitio (`/privacidad`).

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
| `GET /dcasa/juan/v1/config` | ajustes de la dueña | `dias`: `0 = domingo … 6 = sábado`. Incluye `proveedor_ia`, `proveedor_respaldo_ia`, `modelo_rapido`, `modelo_inteligente`, `modelos_por_defecto`, `precios` (`null` donde no hay precio) y `lecciones` |
| `GET /dcasa/juan/v1/herramientas` | definición de las 12 herramientas | cada una con `nombre/descripcion/parametros` y también `name/description/input_schema` |
| `POST /dcasa/juan/v1/herramienta` | ejecutar una herramienta | `422` = error de uso (el texto sirve para corregir); `404` = no existe |
| `POST /dcasa/juan/v1/seguimiento/hecho` | confirmar un seguimiento | `descartado` cierra el ciclo |

Las 12 herramientas, por su nombre público (en Brian llevan el prefijo `juan_` para no chocar con las de uso interno):
`buscar_productos`, `ver_producto`, `listar_categorias`, `reglas_socios`, `saldo_puntos`, `horario_y_tienda`,
`buscar_conocimiento`, `registrar_pregunta_sin_respuesta`, `crear_oportunidad`, `anotar_conversacion`,
`etiquetar_conversacion` y `pasar_a_vendedora`. Las de lectura leen con `sudo()` y filtros (publicados) y devuelven una lista
blanca de campos; el cliente sale **siempre** de la conversación (`juan_conversacion_id`), nunca de un argumento.

Códigos: `400` datos inválidos · `401` token · `404` no existe · `413` demasiado grande · `422` herramienta · `429` demasiados
intentos fallidos · `503` sin token configurado o Odoo arrancando · `500` error interno (sin detalles).

**Odoo → Worker** (`JUAN_WORKER_TOKEN`): `POST /odoo/enviar` (los adjuntos van con URL **firmada de 15 minutos**, ver más
abajo), `POST /odoo/estado` (al devolver con nota, trae `nota_para_el_bot`), `POST /odoo/seguimiento`, `GET /odoo/salud`.

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
[`JUAN_PANEL.md`](JUAN_PANEL.md). Todos exigen ser del equipo de ventas **en el servidor** y devuelven diccionarios JSON; la pantalla
OWL todavía no está hecha, pero todo su backend sí y está probado.

| Método | Qué hace |
|---|---|
| `lista(filtros, offset, limite)` | La bandeja: `{conversaciones, total, hay_mas, sin_leer_total}`, las más recientes primero, 30 por página (máx. 100). Filtros: `canal`, `estado` (`bot`/`humano`/`cerrada`/`necesita_atencion`), `etiqueta_id`, `asignada_a_mi`, `sin_leer`, `con_oportunidad`, `busqueda` (nombre, celular o texto de cualquier mensaje). Un filtro desconocido es error. |
| `hilo(conversacion_id, antes_de_id, limite)` | Un tramo de mensajes (50 por defecto) del más viejo al más nuevo; `antes_de_id` pide el tramo anterior; `hay_mas` dice si quedan. Incluye notas y avisos. |
| `enviar_respuesta(conversacion_id, texto, adjuntos_ids)` | Contesta (toma la conversación si hace falta). Hasta 5 adjuntos propios, de 10 MB. Si el Worker no responde queda «por enviar». |
| `tomar(conversacion_id, minutos)` · `devolver(conversacion_id, nota)` · `cerrar(conversacion_id)` | Lo mismo que los botones (una sola ruta de código). |
| `asignar(conversacion_id, usuario_id)` | Asigna a alguien de ventas (`null` = sin asignar). |
| `poner_etiquetas(conversacion_id, etiqueta_ids)` · `agregar_nota(conversacion_id, texto)` | Etiquetas (solo activas) y nota interna. |
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

### Cambios sobre el contrato `JUAN.md`

Todo lo del contrato se cumple. Se añadió, sin quitar nada: `ok: true` en las respuestas, `adjuntos` en la respuesta de `/mensaje`,
`adjuntos[].sensible`/`base64` aceptados, `nota_para_el_bot` en `/mensaje`, `/estado` y `POST /odoo/estado`, los campos de IA en
`/config`, claves duales en `/herramientas` y tres herramientas más (`buscar_conocimiento`, `registrar_pregunta_sin_respuesta`,
`etiquetar_conversacion`; el contrato tenía 9, ahora son 12). Decisiones donde el contrato dejaba margen: días `0 = domingo`; el
2.º seguimiento cuenta 5 días desde el primero y también espera al horario laboral; `descartado` cierra el ciclo; el catálogo se lee
directo de los productos publicados (`/dcasa/tienda/feed` no existe en este repositorio); tras `pasar_a_vendedora` la pausa es la de
los ajustes y luego el asistente retoma.
